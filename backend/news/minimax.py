import json
from pathlib import Path
import shutil
import subprocess
from typing import Any, Dict, List, Optional

from backend.config import Settings


class MiniMaxError(RuntimeError):
    """MiniMax CLI 调用失败。"""


class MiniMaxClient:
    def __init__(
        self,
        settings: Settings,
        executable: Optional[str] = None,
    ) -> None:
        self.settings = settings
        self.executable = executable or shutil.which("mmx")

    def search(self, query: str) -> Dict[str, Any]:
        return self._run_json(
            [
                "search",
                "query",
                "--q",
                query,
            ],
            timeout=self.settings.minimax_search_timeout_seconds,
        )

    def choose_candidate(
        self,
        query: str,
        target_date: str,
        candidates: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        compact = [
            {
                "index": item["index"],
                "title": item.get("title", ""),
                "snippet": item.get("snippet", ""),
                "date": item.get("date", ""),
                "link": item.get("link", ""),
            }
            for item in candidates
        ]
        prompt = (
            "你负责从MiniMax Search返回的新闻候选中识别财联社发布的A股收评。"
            "候选数据直接取自搜索响应的raw.organic数组，"
            "代码只额外增加了index字段，没有补全、改写或合并其他搜索结果。"
            "只能使用候选JSON中实际存在的字段判断，不补充外部事实。"
            "字段与raw.organic对齐："
            "index是代码增加的候选序号，选择时必须原样返回；"
            "title是raw.organic.title；"
            "link是raw.organic.link；"
            "snippet是raw.organic.snippet，可能从正文中间截断；"
            "date是raw.organic.date。"
            "不能仅凭link域名判断文章来源。"
            "候选已由代码过滤，保证date与目标日期一致且title包含“收评”。"
            "请重点检查："
            "一、title是否描述A股收盘表现，而非期货、港股、美股或其他市场；"
            "二、snippet任意位置是否出现“财联社X月X日电”或"
            "“财联社X月X日讯”，不要求位于snippet开头；"
            "三、snippet是否包含A股指数收盘涨跌、沪深两市成交额、"
            "盘面或板块表现等收盘综述信息。"
            "如果没有符合条件的候选，selected_index必须为null。"
            "返回严格JSON，不要Markdown或额外文字："
            '{"selected_index":整数或null,"confidence":0到1,'
            '"reason":"简短理由"}。'
            f"\n查询词：{query}\n目标日期：{target_date}"
            f"\n候选：{json.dumps(compact, ensure_ascii=False)}"
        )
        response = self._run_json(
            [
                "text",
                "chat",
                "--model",
                "MiniMax-M2.7-highspeed",
                "--system",
                "你是严谨的财经新闻筛选器，只输出JSON。",
                "--message",
                prompt,
                "--temperature",
                "0.1",
                "--max-tokens",
                "800",
            ],
            timeout=self.settings.minimax_chat_timeout_seconds,
        )
        decision = self._find_decision(response)
        if decision is None:
            raise MiniMaxError("MiniMax 候选判断结果中没有可解析的 JSON 决策")
        return decision

    def _run_json(self, arguments: List[str], timeout: int) -> Dict[str, Any]:
        if not self.executable:
            raise MiniMaxError("未找到 mmx，请先安装 mmx-cli")
        api_key = self.settings.require_minimax_api_key()
        command = [
            self.executable,
            *arguments,
            "--output",
            "json",
            "--api-key",
            api_key,
            "--region",
            self.settings.minimax_region,
            "--non-interactive",
            "--no-color",
        ]
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise MiniMaxError(f"MiniMax 调用超过 {timeout} 秒") from exc
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip()
            detail = detail.replace(api_key, "<已隐藏>")
            raise MiniMaxError(
                f"MiniMax 调用失败（退出码 {completed.returncode}）：{detail}"
            )
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise MiniMaxError(
                f"MiniMax 未返回合法 JSON：{completed.stdout[:300]}"
            ) from exc
        if not isinstance(payload, dict):
            return {"data": payload}
        return payload

    @classmethod
    def _find_decision(cls, value: Any) -> Optional[Dict[str, Any]]:
        if isinstance(value, dict):
            if "selected_index" in value:
                return value
            for nested in value.values():
                decision = cls._find_decision(nested)
                if decision is not None:
                    return decision
        elif isinstance(value, list):
            for nested in value:
                decision = cls._find_decision(nested)
                if decision is not None:
                    return decision
        elif isinstance(value, str):
            text = value.strip()
            if text.startswith("```"):
                text = text.strip("`")
                if text.startswith("json"):
                    text = text[4:].strip()
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                start = text.find("{")
                end = text.rfind("}")
                if start < 0 or end <= start:
                    return None
                try:
                    parsed = json.loads(text[start : end + 1])
                except json.JSONDecodeError:
                    return None
            return cls._find_decision(parsed)
        return None

import json
import shutil
import subprocess
from datetime import datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from backend.config import Settings


SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


class MiniMaxError(RuntimeError):
    """MiniMax CLI 调用失败。"""


class MiniMaxClient:
    """MiniMax Search 与文本模型的通用客户端。"""

    def __init__(
        self,
        settings: Settings,
        executable: Optional[str] = None,
    ) -> None:
        self.settings = settings
        self.executable = executable or shutil.which("mmx")

    def search(self, query: str) -> Dict[str, Any]:
        payload = self._run_json(
            [
                "search",
                "query",
                "--q",
                query,
            ],
            timeout=self.settings.minimax_search_timeout_seconds,
        )
        organic = payload.get("organic")
        if not isinstance(organic, list):
            raise MiniMaxError("MiniMax Search 返回中缺少 organic 数组")

        items = []
        for item in organic:
            if not isinstance(item, dict):
                continue
            items.append(
                {
                    "title": str(item.get("title") or ""),
                    "link": str(item.get("link") or ""),
                    "snippet": str(item.get("snippet") or ""),
                    "date": str(item.get("date") or ""),
                }
            )
        return {
            "query": query,
            "searchedAt": datetime.now(SHANGHAI_TZ).isoformat(),
            "items": items,
        }

    def chat_json(
        self,
        system: str,
        prompt: str,
        *,
        model: str = "MiniMax-M2.7-highspeed",
        temperature: float = 0.1,
        max_tokens: int = 800,
    ) -> Dict[str, Any]:
        response = self._run_json(
            [
                "text",
                "chat",
                "--model",
                model,
                "--system",
                system,
                "--message",
                prompt,
                "--temperature",
                str(temperature),
                "--max-tokens",
                str(max_tokens),
            ],
            timeout=self.settings.minimax_chat_timeout_seconds,
        )
        result = self._find_json_object(response)
        if result is None:
            raise MiniMaxError("MiniMax 文本模型结果中没有可解析的 JSON 对象")
        return result

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
    def _find_json_object(cls, value: Any) -> Optional[Dict[str, Any]]:
        if isinstance(value, dict):
            for nested in value.values():
                result = cls._find_json_object(nested)
                if result is not None:
                    return result
            wrapper_keys = {
                "id", "type", "role", "model", "content", "usage",
                "stop_reason", "base_resp", "thinking", "signature", "text",
            }
            if value and not set(value).intersection(wrapper_keys):
                return value
        elif isinstance(value, list):
            for nested in value:
                result = cls._find_json_object(nested)
                if result is not None:
                    return result
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
            if isinstance(parsed, dict):
                return parsed
        return None

from dataclasses import asdict, dataclass
from datetime import date, datetime
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

import pandas as pd

from backend.collector.client import TushareClient
from backend.collector.storage import write_csv_atomic
from backend.config import Settings
from backend.integrations.minimax import MiniMaxClient
from backend.news.article import fetch_article, validate_public_url


SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


@dataclass(frozen=True)
class Candidate:
    index: int
    title: str
    link: str
    snippet: str
    date: str


class MarketReviewCollector:
    def __init__(
        self,
        settings: Settings,
        tushare_client: Optional[TushareClient] = None,
        minimax_client: Optional[MiniMaxClient] = None,
    ) -> None:
        self.settings = settings
        self.tushare = tushare_client or TushareClient(settings)
        self.minimax = minimax_client or MiniMaxClient(settings)

    def collect(
        self,
        target_date: str,
        force: bool = False,
    ) -> Dict[str, Any]:
        parsed_date = datetime.strptime(target_date, "%Y%m%d").date()
        output = self.quarter_path(parsed_date)
        existing_records = self.read_quarter_records(output)
        existing = next(
            (
                item
                for item in existing_records
                if item.get("tradeDate") == target_date
            ),
            None,
        )
        if existing is not None and not force:
            result = dict(existing)
            result["file"] = str(output)
            return result

        calendar = self.get_calendar_day(target_date)
        if calendar["is_open"] != "1":
            return {
                "status": "skipped",
                "reason": "非A股交易日",
                "tradeDate": target_date,
                "calendar": calendar,
            }

        query = self.build_query(parsed_date)
        search_result = self.minimax.search(query)
        candidates = self.filter_candidates(
            search_result.get("items", []),
            parsed_date,
        )
        selected = self.select_candidate(
            query,
            target_date,
            candidates,
        )
        article = self.fetch_article(selected.link)
        if article["content"]:
            source = article["source"].strip()
            if source != "财联社":
                raise RuntimeError(
                    f"候选页面来源不是财联社：{source or '未知'}"
                )
            if not any(
                marker in article["content"]
                for marker in ("截至收盘", "成交额", "三大指数")
            ):
                raise RuntimeError("候选页面正文不具备A股收评特征")
        status = "success" if article["content"] else "partial"
        if not article["content"]:
            article["content"] = selected.snippet
            article["contentSource"] = "search_snippet"

        payload = {
            "status": status,
            "tradeDate": target_date,
            "publishedAt": selected.date,
            "source": article["source"] or "财联社",
            "title": article["title"] or selected.title,
            "url": selected.link,
            "content": article["content"],
            "contentSource": article["contentSource"],
            "collectedAt": datetime.now(SHANGHAI_TZ).isoformat(),
        }
        records = [
            item
            for item in existing_records
            if item.get("tradeDate") != target_date
        ]
        records.append(payload)
        records.sort(key=lambda item: str(item.get("tradeDate", "")))
        self.write_quarter_records(output, records)
        result = dict(payload)
        result["file"] = str(output)
        return result

    def quarter_path(self, target: date) -> Path:
        quarter = (target.month - 1) // 3 + 1
        return (
            self.settings.data_dir
            / "raw"
            / "market_review"
            / f"{target.year}-Q{quarter}.json"
        )

    @staticmethod
    def read_quarter_records(path: Path) -> List[Dict[str, Any]]:
        if not path.exists():
            return []
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"无法读取季度收评文件：{path}") from exc
        if not isinstance(value, list):
            raise RuntimeError(f"季度收评文件必须是 JSON 数组：{path}")
        return [item for item in value if isinstance(item, dict)]

    @staticmethod
    def write_quarter_records(
        path: Path,
        records: List[Dict[str, Any]],
    ) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(records, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)

    def get_calendar_day(self, target_date: str) -> Dict[str, str]:
        path = self.settings.data_dir / "raw" / "trade_cal" / "SSE.csv"
        existing = (
            pd.read_csv(path, dtype=str)
            if path.exists()
            else pd.DataFrame()
        )
        if not existing.empty and "cal_date" in existing.columns:
            matched = existing.loc[existing["cal_date"] == target_date]
            if not matched.empty:
                return self._calendar_record(matched.iloc[-1])

        fetched = self.tushare.call(
            "trade_cal",
            exchange="SSE",
            start_date=target_date,
            end_date=target_date,
            fields="exchange,cal_date,is_open,pretrade_date",
        )
        if fetched is None or fetched.empty:
            raise RuntimeError(f"trade_cal 未返回 {target_date} 的日历数据")
        combined = pd.concat([existing, fetched], ignore_index=True)
        combined = combined.drop_duplicates(
            ["exchange", "cal_date"],
            keep="last",
        ).sort_values(["exchange", "cal_date"])
        write_csv_atomic(combined, path)
        matched = combined.loc[combined["cal_date"].astype(str) == target_date]
        return self._calendar_record(matched.iloc[-1])

    @staticmethod
    def _calendar_record(row: pd.Series) -> Dict[str, str]:
        return {
            "exchange": str(row.get("exchange", "SSE")),
            "cal_date": str(row["cal_date"]),
            "is_open": str(row["is_open"]),
            "pretrade_date": (
                ""
                if pd.isna(row.get("pretrade_date"))
                else str(row.get("pretrade_date"))
            ),
        }

    @staticmethod
    def build_query(target: date) -> str:
        return (
            f"财联社 收评 财联社{target.month}月{target.day}日电"
        )

    @staticmethod
    def filter_candidates(
        items: List[Dict[str, Any]],
        target: date,
    ) -> List[Candidate]:
        date_iso = target.strftime("%Y-%m-%d")
        candidates = []
        for index, item in enumerate(items):
            title = str(item.get("title") or item.get("name") or "")
            snippet = str(
                item.get("snippet")
                or item.get("description")
                or ""
            )
            link = str(item.get("link") or "")
            published = str(item.get("date") or "")
            if not published.startswith(date_iso) or "收评" not in title:
                continue
            candidates.append(
                Candidate(
                    index=index,
                    title=title,
                    link=link,
                    snippet=snippet,
                    date=published,
                )
            )
        return candidates

    def select_candidate(
        self,
        query: str,
        target_date: str,
        candidates: List[Candidate],
    ) -> Candidate:
        if not candidates:
            raise RuntimeError(
                f"没有找到 {target_date} 当日标题含“收评”的候选"
            )
        compact = [asdict(item) for item in candidates]
        prompt = self.build_selection_prompt(
            query,
            target_date,
            compact,
        )
        decision = self.minimax.chat_json(
            "你是严谨的财经新闻筛选器，只输出JSON。",
            prompt,
            temperature=0.1,
            max_tokens=800,
        )
        selected_index = decision.get("selected_index")
        selected = next(
            (
                item
                for item in candidates
                if item.index == selected_index
            ),
            None,
        )
        confidence = float(decision.get("confidence", 0))
        if selected is None:
            raise RuntimeError("MiniMax 返回的候选序号无效")
        if confidence < 0.55:
            raise RuntimeError(
                f"MiniMax 候选判断置信度不足：{confidence:.2f}"
            )
        return selected

    @staticmethod
    def build_selection_prompt(
        query: str,
        target_date: str,
        candidates: List[Dict[str, Any]],
    ) -> str:
        return (
            "你负责从通用搜索结果中识别财联社发布的A股收评。"
            "候选数据来自MiniMax Search，经通用客户端统一为"
            "index、title、link、snippet、date五个字段。"
            "只能使用候选JSON中实际存在的字段判断，不补充外部事实。"
            "index是候选序号，选择时必须原样返回；"
            "title是搜索结果标题；link是结果链接；"
            "snippet是搜索摘要，可能从正文中间截断；date是发布时间。"
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
            f"\n候选：{json.dumps(candidates, ensure_ascii=False)}"
        )

    def fetch_article(self, url: str) -> Dict[str, Any]:
        return fetch_article(url)

    @staticmethod
    def _validate_public_url(url: str) -> None:
        validate_public_url(url)


def default_trade_date() -> str:
    return datetime.now(SHANGHAI_TZ).strftime("%Y%m%d")

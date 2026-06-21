from dataclasses import asdict
from datetime import date, datetime
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.config import Settings
from backend.integrations.minimax import MiniMaxClient

from .market_review import Candidate, MarketReviewCollector, SHANGHAI_TZ


class MorningNewsCollector(MarketReviewCollector):
    """采集财联社“早间新闻精选”。"""

    def __init__(
        self,
        settings: Settings,
        minimax_client: Optional[MiniMaxClient] = None,
    ) -> None:
        self.settings = settings
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
                if item.get("newsDate") == target_date
            ),
            None,
        )
        if existing is not None and not force:
            result = dict(existing)
            result["file"] = str(output)
            return result

        query = self.build_query(parsed_date)
        search_result = self.minimax.search(query)
        candidates = self.filter_candidates(
            search_result.get("items", []),
            parsed_date,
        )
        selected = self.select_candidate(query, target_date, candidates)
        article = self.fetch_article(selected.link)
        if article["content"]:
            source = article["source"].strip()
            if source != "财联社":
                raise RuntimeError(
                    f"候选页面来源不是财联社：{source or '未知'}"
                )

        status = "success" if article["content"] else "partial"
        if not article["content"]:
            article["content"] = selected.snippet
            article["contentSource"] = "search_snippet"

        payload = {
            "status": status,
            "newsType": "morningNews",
            "newsDate": target_date,
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
            if item.get("newsDate") != target_date
        ]
        records.append(payload)
        records.sort(key=lambda item: str(item.get("newsDate", "")))
        self.write_quarter_records(output, records)

        result = dict(payload)
        result["file"] = str(output)
        return result

    def quarter_path(self, target: date) -> Path:
        quarter = (target.month - 1) // 3 + 1
        return (
            self.settings.data_dir
            / "raw"
            / "morning_news"
            / f"{target.year}-Q{quarter}.json"
        )

    @staticmethod
    def build_query(target: date) -> str:
        return f"财联社{target.month}月{target.day}日早间新闻精选"

    @staticmethod
    def filter_candidates(
        items: List[Dict[str, Any]],
        target: date,
    ) -> List[Candidate]:
        date_iso = target.strftime("%Y-%m-%d")
        candidates = []
        for index, item in enumerate(items):
            title = str(item.get("title") or item.get("name") or "")
            published = str(item.get("date") or "")
            if (
                not published.startswith(date_iso)
                or "早间新闻精选" not in title
            ):
                continue
            candidates.append(
                Candidate(
                    index=index,
                    title=title,
                    link=str(item.get("link") or ""),
                    snippet=str(
                        item.get("snippet")
                        or item.get("description")
                        or ""
                    ),
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
                f"没有找到 {target_date} 当日标题含“早间新闻精选”的候选"
            )
        decision = self.minimax.chat_json(
            "你是严谨的财经新闻筛选器，只输出JSON。",
            self.build_selection_prompt(
                query,
                target_date,
                [asdict(item) for item in candidates],
            ),
            temperature=0.1,
            max_tokens=600,
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
            "你负责从通用搜索结果中识别财联社在指定日期发布的"
            "“早间新闻精选”。候选JSON只包含index、title、link、"
            "snippet、date五个字段，只能依据这些字段判断。"
            "候选已由代码过滤，保证date与目标日期一致且title包含"
            "“早间新闻精选”。请确认title或snippet表明内容来自财联社，"
            "并且是当天的早间新闻汇总，而不是对该新闻的转载评论、"
            "单条新闻或其他日期的合集。不能仅凭link域名判断文章来源。"
            "如果没有符合条件的候选，selected_index必须为null。"
            "返回严格JSON，不要Markdown或额外文字："
            '{"selected_index":整数或null,"confidence":0到1,'
            '"reason":"简短理由"}。'
            f"\n查询词：{query}\n目标日期：{target_date}"
            f"\n候选：{json.dumps(candidates, ensure_ascii=False)}"
        )

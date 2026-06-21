from dataclasses import asdict, dataclass
from datetime import date, datetime
from html.parser import HTMLParser
import ipaddress
import json
from pathlib import Path
import re
import socket
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import pandas as pd

from backend.collector.client import TushareClient
from backend.collector.storage import write_csv_atomic
from backend.config import Settings
from .minimax import MiniMaxClient


SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
PROXY_BENCHMARK_NETWORK = ipaddress.ip_network("198.18.0.0/15")
BENCHMARK_PROXY_HOSTS = {"so.html5.qq.com"}


@dataclass(frozen=True)
class Candidate:
    index: int
    title: str
    link: str
    snippet: str
    date: str


class ArticleParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: List[tuple] = []
        self.title_parts: List[str] = []
        self.source_parts: List[str] = []
        self.content_parts: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[tuple]) -> None:
        classes = set(dict(attrs).get("class", "").split())
        if tag in {"br"} and self._inside("article-content"):
            self.content_parts.append("\n")
        if tag not in {
            "area", "base", "br", "col", "embed", "hr", "img",
            "input", "link", "meta", "param", "source", "track", "wbr",
        }:
            self.stack.append((tag, classes))
        if tag in {"p", "div"} and self._inside("article-content"):
            self.content_parts.append("\n")

    def handle_startendtag(self, tag: str, attrs: List[tuple]) -> None:
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break

    def handle_data(self, data: str) -> None:
        if self._inside("article-title"):
            self.title_parts.append(data)
        if self._inside("article-user-right-title"):
            self.source_parts.append(data)
        if self._inside("article-content"):
            self.content_parts.append(data)

    def _inside(self, class_name: str) -> bool:
        return any(class_name in classes for _, classes in self.stack)

    def result(self) -> Dict[str, str]:
        return {
            "title": _clean_text("".join(self.title_parts)),
            "source": _clean_text("".join(self.source_parts)),
            "content": _clean_text("".join(self.content_parts)),
        }


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


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
        output = (
            self.settings.data_dir
            / "raw"
            / "market_review"
            / f"{target_date}.json"
        )
        if output.exists() and not force:
            return json.loads(output.read_text(encoding="utf-8"))

        calendar = self.get_calendar_day(target_date)
        if calendar["is_open"] != "1":
            return {
                "status": "skipped",
                "reason": "非A股交易日",
                "tradeDate": target_date,
                "calendar": calendar,
            }

        query = self.build_query(parsed_date)
        raw_search = self.minimax.search(query)
        raw_items = self.raw_organic_items(raw_search)
        candidates = self.filter_candidates(raw_items, parsed_date)
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
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(output)
        payload["file"] = str(output)
        return payload

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
    def raw_organic_items(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        values: Any = payload.get("organic")
        if not isinstance(values, list):
            raise RuntimeError("MiniMax Search 返回中缺少 raw.organic 数组")
        return [item for item in values if isinstance(item, dict)]

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
        decision = self.minimax.choose_candidate(
            query,
            target_date,
            [asdict(item) for item in candidates],
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

    def fetch_article(self, url: str) -> Dict[str, Any]:
        self._validate_public_url(url)
        request = Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 Chrome/126 Safari/537.36"
                )
            },
        )
        try:
            with urlopen(request, timeout=20) as response:
                content_type = response.headers.get_content_type()
                if content_type not in {"text/html", "application/xhtml+xml"}:
                    raise RuntimeError(f"不支持的正文类型：{content_type}")
                raw = response.read(2_000_001)
                if len(raw) > 2_000_000:
                    raise RuntimeError("网页内容超过 2MB 限制")
                charset = response.headers.get_content_charset() or "utf-8"
                html = raw.decode(charset, errors="replace")
        except Exception as exc:
            return {
                "url": url,
                "fetchStatus": "failed",
                "error": str(exc),
                "title": "",
                "source": "",
                "content": "",
                "contentSource": "none",
            }
        parser = ArticleParser()
        parser.feed(html)
        article = parser.result()
        article.update(
            {
                "url": url,
                "fetchStatus": (
                    "success" if article["content"] else "empty"
                ),
                "contentSource": (
                    "webpage" if article["content"] else "none"
                ),
            }
        )
        return article

    @staticmethod
    def _validate_public_url(url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise RuntimeError("候选链接不是有效的 HTTP(S) 地址")
        hostname = parsed.hostname.lower()
        if hostname in {"localhost"} or hostname.endswith(".local"):
            raise RuntimeError("不允许访问本地地址")
        try:
            default_port = 443 if parsed.scheme == "https" else 80
            addresses = socket.getaddrinfo(hostname, parsed.port or default_port)
        except socket.gaierror as exc:
            raise RuntimeError(f"无法解析候选链接域名：{hostname}") from exc
        for address in addresses:
            ip = ipaddress.ip_address(address[4][0])
            if (
                hostname in BENCHMARK_PROXY_HOSTS
                and ip in PROXY_BENCHMARK_NETWORK
            ):
                continue
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_multicast
                or ip.is_unspecified
            ):
                raise RuntimeError("候选链接解析到不安全的本地或私有地址")


def default_trade_date() -> str:
    return datetime.now(SHANGHAI_TZ).strftime("%Y%m%d")

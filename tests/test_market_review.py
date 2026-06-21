from datetime import date
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import pandas as pd

from backend.config import Settings
from backend.news.minimax import MiniMaxClient
from backend.news.market_review import ArticleParser, MarketReviewCollector


class FakeTushare:
    def __init__(self, is_open="1"):
        self.is_open = is_open
        self.calls = []

    def call(self, endpoint, **params):
        self.calls.append((endpoint, params))
        return pd.DataFrame(
            [
                {
                    "exchange": "SSE",
                    "cal_date": params["start_date"],
                    "is_open": self.is_open,
                    "pretrade_date": "20260617",
                }
            ]
        )


class FakeMiniMax:
    def __init__(self):
        self.search_calls = []
        self.choose_calls = []

    def search(self, query):
        self.search_calls.append(query)
        return {
            "organic": [
                {
                    "title": "无关资讯",
                    "link": "https://example.com/other",
                    "snippet": "普通新闻",
                    "date": "2026-06-18 10:00:00",
                },
                {
                    "title": "收评：科创50指数大涨",
                    "link": "https://example.com/review",
                    "snippet": (
                        "财联社6月18日电，三大指数涨跌不一，"
                        "沪深两市成交额放量。截至收盘，沪指下跌。"
                    ),
                    "date": "2026-06-18 15:12:00",
                },
            ]
        }

    def choose_candidate(self, query, target_date, candidates):
        self.choose_calls.append((query, target_date, candidates))
        return {
            "selected_index": 1,
            "confidence": 0.98,
            "reason": "标题和电头均匹配",
        }


class TestCollector(MarketReviewCollector):
    def fetch_article(self, url):
        return {
            "url": url,
            "fetchStatus": "success",
            "title": "收评：科创50指数大涨",
            "source": "财联社",
            "content": "三大指数震荡，截至收盘，沪深两市成交额放量。",
            "contentSource": "webpage",
        }


class MarketReviewTests(unittest.TestCase):
    def make_settings(self, directory):
        return Settings(
            tushare_token="test",
            data_dir=Path(directory),
            request_interval_seconds=0,
            retry_times=1,
            minimax_api_key="test",
        )

    def test_build_query_uses_month_and_day(self):
        query = MarketReviewCollector.build_query(date(2026, 6, 18))
        self.assertEqual(query, "财联社 收评 财联社6月18日电")

    def test_article_parser_extracts_tencent_article(self):
        parser = ArticleParser()
        parser.feed(
            """
            <div class="article-title">测试标题</div>
            <div class="article-user-right-title"><div>财联社</div></div>
            <div class="article-content"><p>第一段。</p><p>第二段。</p></div>
            """
        )
        result = parser.result()
        self.assertEqual(result["title"], "测试标题")
        self.assertEqual(result["source"], "财联社")
        self.assertEqual(result["content"], "第一段。 第二段。")

    def test_minimax_decision_parser_accepts_cli_message_shape(self):
        payload = {
            "content": [
                {"type": "thinking", "thinking": "分析候选"},
                {
                    "type": "text",
                    "text": (
                        '{"selected_index":8,"confidence":0.95,'
                        '"reason":"匹配"}'
                    ),
                },
            ]
        }
        decision = MiniMaxClient._find_decision(payload)
        self.assertEqual(decision["selected_index"], 8)

    def test_minimax_candidate_payload_uses_documented_fields(self):
        minimax = FakeMiniMax()
        candidates = [
            {
                "index": 7,
                "title": "收评：科创50指数大涨",
                "snippet": "摘要中部出现财联社6月18日电，沪深两市成交额放量。",
                "date": "2026-06-18 15:12:57",
                "link": "https://example.com/review",
            }
        ]
        decision = minimax.choose_candidate(
            "财联社 收评 财联社6月18日电",
            "20260618",
            candidates,
        )
        self.assertEqual(decision["selected_index"], 1)
        sent_candidates = minimax.choose_calls[0][2]
        self.assertEqual(
            set(sent_candidates[0]),
            {"index", "title", "snippet", "date", "link"},
        )

    def test_filter_candidates_keeps_only_matching_date_and_title(self):
        candidates = MarketReviewCollector.filter_candidates(
            FakeMiniMax().search("")["organic"],
            date(2026, 6, 18),
        )
        self.assertEqual([item.index for item in candidates], [1])

    def test_candidate_filter_only_requires_date_and_review_title(self):
        minimax = FakeMiniMax()
        collector = MarketReviewCollector(
            self.make_settings("/tmp"),
            tushare_client=FakeTushare(),
            minimax_client=minimax,
        )
        candidates = MarketReviewCollector.filter_candidates(
            [
                {
                    "title": "历史收评",
                    "link": "https://example.com/history",
                    "snippet": "历史结果",
                    "date": "2024-06-18 15:00:00",
                },
                {
                    "title": "收评：科创板走强",
                    "link": "https://example.com/review",
                    "snippet": "没有财联社字样的摘要",
                    "date": "2026-06-18 15:10:00",
                },
                {
                    "title": "午间涨停分析",
                    "link": "https://example.com/noon",
                    "snippet": "财联社6月18日电",
                    "date": "2026-06-18 12:00:00",
                },
            ],
            date(2026, 6, 18),
        )
        selected = collector.select_candidate(
            "测试",
            "20260618",
            candidates,
        )
        self.assertEqual(selected.title, "收评：科创板走强")

    @patch(
        "backend.news.market_review.socket.getaddrinfo",
        return_value=[(2, 1, 6, "", ("192.168.1.10", 443))],
    )
    def test_url_validation_rejects_private_address(self, _getaddrinfo):
        with self.assertRaisesRegex(RuntimeError, "不安全"):
            MarketReviewCollector._validate_public_url(
                "https://example.com/article"
            )

    @patch(
        "backend.news.market_review.socket.getaddrinfo",
        return_value=[(2, 1, 6, "", ("192.0.0.8", 443))],
    )
    def test_url_validation_allows_publicly_routable_special_cdn(
        self,
        _getaddrinfo,
    ):
        MarketReviewCollector._validate_public_url(
            "https://example.com/article"
        )

    @patch(
        "backend.news.market_review.socket.getaddrinfo",
        return_value=[(2, 1, 6, "", ("198.18.0.139", 443))],
    )
    def test_url_validation_allows_known_host_through_proxy_benchmark_range(
        self,
        _getaddrinfo,
    ):
        MarketReviewCollector._validate_public_url(
            "https://so.html5.qq.com/page/real/search_news?docid=1"
        )

    @patch(
        "backend.news.market_review.socket.getaddrinfo",
        return_value=[(2, 1, 6, "", ("198.18.0.139", 443))],
    )
    def test_url_validation_rejects_unknown_host_on_proxy_benchmark_range(
        self,
        _getaddrinfo,
    ):
        with self.assertRaisesRegex(RuntimeError, "不安全"):
            MarketReviewCollector._validate_public_url(
                "https://example.com/article"
            )

    def test_non_trading_day_does_not_call_minimax(self):
        with TemporaryDirectory() as directory:
            minimax = FakeMiniMax()
            collector = TestCollector(
                self.make_settings(directory),
                tushare_client=FakeTushare(is_open="0"),
                minimax_client=minimax,
            )
            result = collector.collect("20260620")
            self.assertEqual(result["status"], "skipped")
            self.assertEqual(minimax.search_calls, [])

    def test_trading_day_collects_and_saves_json(self):
        with TemporaryDirectory() as directory:
            minimax = FakeMiniMax()
            collector = TestCollector(
                self.make_settings(directory),
                tushare_client=FakeTushare(is_open="1"),
                minimax_client=minimax,
            )
            result = collector.collect("20260618")
            path = (
                Path(directory)
                / "raw"
                / "market_review"
                / "20260618.json"
            )
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(result["status"], "success")
            self.assertEqual(result["source"], "财联社")
            self.assertEqual(result["title"], "收评：科创50指数大涨")
            self.assertEqual(
                result["content"],
                "三大指数震荡，截至收盘，沪深两市成交额放量。",
            )
            self.assertEqual(result["contentSource"], "webpage")
            self.assertNotIn("searchResults", saved)
            self.assertNotIn("selected", saved)
            self.assertNotIn("selection", saved)
            self.assertNotIn("calendar", saved)
            self.assertNotIn("query", saved)
            self.assertEqual(len(minimax.search_calls), 1)


if __name__ == "__main__":
    unittest.main()

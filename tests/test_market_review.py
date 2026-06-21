from datetime import date
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import pandas as pd

from backend.config import Settings
from backend.integrations.minimax import MiniMaxClient
from backend.news.market_review import MarketReviewCollector


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
        self.chat_calls = []

    def search(self, query):
        self.search_calls.append(query)
        return {
            "query": query,
            "searchedAt": "2026-06-18T16:00:00+08:00",
            "items": [
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

    def chat_json(self, system, prompt, **options):
        self.chat_calls.append((system, prompt, options))
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

    def test_market_review_prompt_uses_standardized_fields(self):
        minimax = FakeMiniMax()
        prompt = MarketReviewCollector.build_selection_prompt(
            "财联社 收评 财联社6月18日电",
            "20260618",
            [
            {
                "index": 7,
                "title": "收评：科创50指数大涨",
                "snippet": "摘要中部出现财联社6月18日电，沪深两市成交额放量。",
                "date": "2026-06-18 15:12:57",
                "link": "https://example.com/review",
            }
            ],
        )
        self.assertIn('"index": 7', prompt)
        self.assertIn('"title": "收评：科创50指数大涨"', prompt)
        self.assertIn('"link": "https://example.com/review"', prompt)
        self.assertNotIn("raw.organic", prompt)

    def test_filter_candidates_keeps_only_matching_date_and_title(self):
        candidates = MarketReviewCollector.filter_candidates(
            FakeMiniMax().search("")["items"],
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
        self.assertEqual(len(minimax.chat_calls), 1)

    @patch(
        "backend.news.article.socket.getaddrinfo",
        return_value=[(2, 1, 6, "", ("192.168.1.10", 443))],
    )
    def test_url_validation_rejects_private_address(self, _getaddrinfo):
        with self.assertRaisesRegex(RuntimeError, "不安全"):
            MarketReviewCollector._validate_public_url(
                "https://example.com/article"
            )

    @patch(
        "backend.news.article.socket.getaddrinfo",
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
        "backend.news.article.socket.getaddrinfo",
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
        "backend.news.article.socket.getaddrinfo",
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
                / "2026-Q2.json"
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
            self.assertIsInstance(saved, list)
            self.assertEqual(len(saved), 1)
            self.assertEqual(saved[0]["tradeDate"], "20260618")
            self.assertNotIn("searchResults", saved[0])
            self.assertNotIn("selected", saved[0])
            self.assertNotIn("selection", saved[0])
            self.assertNotIn("calendar", saved[0])
            self.assertNotIn("query", saved[0])
            self.assertEqual(len(minimax.search_calls), 1)

    def test_quarter_file_reuses_and_force_replaces_trade_date(self):
        with TemporaryDirectory() as directory:
            minimax = FakeMiniMax()
            collector = TestCollector(
                self.make_settings(directory),
                tushare_client=FakeTushare(is_open="1"),
                minimax_client=minimax,
            )
            first = collector.collect("20260618")
            cached = collector.collect("20260618")
            replaced = collector.collect("20260618", force=True)
            path = Path(first["file"])
            saved = json.loads(path.read_text(encoding="utf-8"))

            self.assertEqual(first["file"], cached["file"])
            self.assertEqual(replaced["file"], first["file"])
            self.assertEqual(len(saved), 1)
            self.assertEqual(saved[0]["tradeDate"], "20260618")
            self.assertEqual(len(minimax.search_calls), 2)

    def test_quarter_path(self):
        with TemporaryDirectory() as directory:
            collector = TestCollector(
                self.make_settings(directory),
                tushare_client=FakeTushare(),
                minimax_client=FakeMiniMax(),
            )
            self.assertEqual(
                collector.quarter_path(date(2026, 6, 18)).name,
                "2026-Q2.json",
            )
            self.assertEqual(
                collector.quarter_path(date(2026, 7, 1)).name,
                "2026-Q3.json",
            )


if __name__ == "__main__":
    unittest.main()

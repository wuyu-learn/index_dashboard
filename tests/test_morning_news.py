from datetime import date
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from backend.config import Settings
from backend.news.morning_news import MorningNewsCollector


class FakeMiniMax:
    def __init__(self):
        self.search_calls = []
        self.chat_calls = []

    def search(self, query):
        self.search_calls.append(query)
        return {
            "query": query,
            "searchedAt": "2026-06-18T08:00:00+08:00",
            "items": [
                {
                    "title": "财联社6月18日早间新闻精选",
                    "link": "https://example.com/morning",
                    "snippet": "财联社早间新闻精选，今日重要消息一览。",
                    "date": "2026-06-18 08:03:00",
                },
                {
                    "title": "财联社6月17日早间新闻精选",
                    "link": "https://example.com/yesterday",
                    "snippet": "昨日早间新闻。",
                    "date": "2026-06-17 08:03:00",
                },
            ],
        }

    def chat_json(self, system, prompt, **options):
        self.chat_calls.append((system, prompt, options))
        return {
            "selected_index": 0,
            "confidence": 0.99,
            "reason": "日期、标题和来源均匹配",
        }


class TestMorningNewsCollector(MorningNewsCollector):
    def fetch_article(self, url):
        return {
            "url": url,
            "fetchStatus": "success",
            "title": "财联社6月18日早间新闻精选",
            "source": "财联社",
            "content": "今日值得关注的财经新闻如下。",
            "contentSource": "webpage",
        }


class MorningNewsTests(unittest.TestCase):
    @staticmethod
    def make_settings(directory):
        return Settings(
            tushare_token="test",
            data_dir=Path(directory),
            request_interval_seconds=0,
            retry_times=1,
            minimax_api_key="test",
        )

    def test_build_query(self):
        self.assertEqual(
            MorningNewsCollector.build_query(date(2026, 6, 18)),
            "财联社6月18日早间新闻精选",
        )

    def test_filter_requires_matching_date_and_title(self):
        candidates = MorningNewsCollector.filter_candidates(
            FakeMiniMax().search("")["items"],
            date(2026, 6, 18),
        )
        self.assertEqual([item.index for item in candidates], [0])

    def test_collect_saves_quarter_json(self):
        with TemporaryDirectory() as directory:
            minimax = FakeMiniMax()
            collector = TestMorningNewsCollector(
                self.make_settings(directory),
                minimax_client=minimax,
            )
            result = collector.collect("20260618")
            path = (
                Path(directory)
                / "raw"
                / "morning_news"
                / "2026-Q2.json"
            )
            saved = json.loads(path.read_text(encoding="utf-8"))

            self.assertEqual(result["status"], "success")
            self.assertEqual(result["newsType"], "morningNews")
            self.assertEqual(result["newsDate"], "20260618")
            stored_result = {
                key: value
                for key, value in result.items()
                if key != "file"
            }
            self.assertEqual(saved, [stored_result])
            self.assertEqual(
                minimax.search_calls,
                ["财联社6月18日早间新闻精选"],
            )
            self.assertEqual(len(minimax.chat_calls), 1)

    def test_existing_record_is_reused_unless_forced(self):
        with TemporaryDirectory() as directory:
            minimax = FakeMiniMax()
            collector = TestMorningNewsCollector(
                self.make_settings(directory),
                minimax_client=minimax,
            )
            first = collector.collect("20260618")
            cached = collector.collect("20260618")
            replaced = collector.collect("20260618", force=True)
            saved = json.loads(Path(first["file"]).read_text(encoding="utf-8"))

            self.assertEqual(cached["file"], first["file"])
            self.assertEqual(replaced["file"], first["file"])
            self.assertEqual(len(saved), 1)
            self.assertEqual(len(minimax.search_calls), 2)


if __name__ == "__main__":
    unittest.main()

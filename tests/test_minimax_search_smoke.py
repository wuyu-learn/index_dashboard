import json
import subprocess
import unittest
from unittest.mock import patch

from scripts.minimax_search_smoke import (
    MiniMaxSearchError,
    normalize_results,
    search,
)


class MiniMaxSearchSmokeTests(unittest.TestCase):
    def test_normalize_results_accepts_nested_data(self):
        payload = {
            "data": {
                "results": [
                    {
                        "title": "示例标题",
                        "url": "https://example.com/a",
                        "snippet": "示例摘要",
                    }
                ]
            }
        }

        results = normalize_results(payload)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].title, "示例标题")
        self.assertEqual(results[0].url, "https://example.com/a")
        self.assertEqual(results[0].snippet, "示例摘要")

    def test_normalize_results_accepts_mmx_organic_shape(self):
        payload = {
            "organic": [
                {
                    "title": "MiniMax 搜索结果",
                    "link": "https://example.com/mmx",
                    "snippet": "真实 CLI 返回结构",
                    "date": "2026-06-20",
                }
            ]
        }

        results = normalize_results(payload)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].title, "MiniMax 搜索结果")
        self.assertEqual(results[0].url, "https://example.com/mmx")

    @patch.dict(
        "scripts.minimax_search_smoke.os.environ",
        {"MINIMAX_API_KEY": "test-key", "MINIMAX_REGION": "cn"},
        clear=False,
    )
    @patch("scripts.minimax_search_smoke.load_project_env")
    @patch("scripts.minimax_search_smoke.shutil.which", return_value="/usr/bin/mmx")
    @patch("scripts.minimax_search_smoke.subprocess.run")
    def test_search_calls_cli_without_shell(self, run, _which, _load_env):
        run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=json.dumps(
                [
                    {
                        "name": "MiniMax",
                        "link": "https://example.com",
                        "description": "搜索结果",
                    }
                ]
            ),
            stderr="",
        )

        output = search("MiniMax 搜索")

        command = run.call_args.args[0]
        self.assertEqual(
            command,
            [
                "/usr/bin/mmx",
                "search",
                "query",
                "--q",
                "MiniMax 搜索",
                "--output",
                "json",
                "--api-key",
                "test-key",
                "--region",
                "cn",
                "--non-interactive",
                "--no-color",
            ],
        )
        self.assertNotIn("shell", run.call_args.kwargs)
        self.assertEqual(output["resultCount"], 1)
        self.assertNotIn("results", output)
        self.assertEqual(output["raw"][0]["name"], "MiniMax")

    @patch("scripts.minimax_search_smoke.load_project_env")
    @patch("scripts.minimax_search_smoke.shutil.which", return_value=None)
    def test_search_reports_missing_cli(self, _which, _load_env):
        with self.assertRaisesRegex(MiniMaxSearchError, "未找到 mmx"):
            search("测试")


if __name__ == "__main__":
    unittest.main()

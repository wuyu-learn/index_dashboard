import json
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from backend.config import Settings
from backend.integrations.minimax import MiniMaxClient, MiniMaxError


class MiniMaxClientTests(unittest.TestCase):
    def make_settings(self) -> Settings:
        return Settings(
            tushare_token="test",
            data_dir=Path("/tmp"),
            request_interval_seconds=0,
            retry_times=1,
            minimax_api_key="test-key",
            minimax_region="cn",
        )

    @patch("backend.integrations.minimax.subprocess.run")
    def test_search_returns_standardized_items(self, run):
        run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=json.dumps(
                {
                    "organic": [
                        {
                            "title": "示例标题",
                            "link": "https://example.com",
                            "snippet": "示例摘要",
                            "date": "2026-06-18 15:00:00",
                            "extra": "不进入通用结果",
                        }
                    ]
                }
            ),
            stderr="",
        )
        client = MiniMaxClient(self.make_settings(), executable="/usr/bin/mmx")

        result = client.search("测试查询")

        self.assertEqual(result["query"], "测试查询")
        self.assertIn("searchedAt", result)
        self.assertEqual(
            result["items"],
            [
                {
                    "title": "示例标题",
                    "link": "https://example.com",
                    "snippet": "示例摘要",
                    "date": "2026-06-18 15:00:00",
                }
            ],
        )
        self.assertNotIn("raw", result)
        command = run.call_args.args[0]
        self.assertEqual(command[:5], [
            "/usr/bin/mmx", "search", "query", "--q", "测试查询",
        ])
        self.assertNotIn("shell", run.call_args.kwargs)

    @patch("backend.integrations.minimax.subprocess.run")
    def test_chat_json_extracts_json_from_cli_message(self, run):
        run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=json.dumps(
                {
                    "content": [
                        {"type": "thinking", "thinking": "分析"},
                        {
                            "type": "text",
                            "text": '{"selected_index":2,"confidence":0.9}',
                        },
                    ]
                }
            ),
            stderr="",
        )
        client = MiniMaxClient(self.make_settings(), executable="/usr/bin/mmx")

        result = client.chat_json("只输出JSON", "选择候选")

        self.assertEqual(result["selected_index"], 2)
        self.assertEqual(result["confidence"], 0.9)

    def test_missing_cli_is_reported(self):
        client = MiniMaxClient(self.make_settings(), executable="")
        client.executable = None
        with self.assertRaisesRegex(MiniMaxError, "未找到 mmx"):
            client.search("测试")

    def test_find_json_object_accepts_markdown_fence(self):
        value = {"text": '```json\n{"ok":true}\n```'}
        self.assertEqual(
            MiniMaxClient._find_json_object(value),
            {"ok": True},
        )


if __name__ == "__main__":
    unittest.main()

"""独立验证 MiniMax CLI 网络搜索能力。

用法：
    python3 scripts/minimax_search_smoke.py "半导体行业最新政策"

前置条件：
    1. 已安装 mmx-cli
    2. 已执行 mmx auth login
"""

import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.config import Settings
from backend.integrations.minimax import MiniMaxClient, MiniMaxError


def main() -> int:
    parser = argparse.ArgumentParser(description="验证 MiniMax 网络搜索")
    parser.add_argument("query", help="搜索关键词")
    parser.add_argument("--timeout", type=int, default=45, help="超时秒数")
    parser.add_argument("--out", type=Path, help="将完整结果保存为 JSON 文件")
    args = parser.parse_args()

    try:
        settings = Settings.from_env()
        settings = replace(
            settings,
            minimax_search_timeout_seconds=args.timeout,
        )
        result = MiniMaxClient(settings).search(args.query)
    except MiniMaxError as exc:
        print(f"验证失败：{exc}", file=sys.stderr)
        return 1

    output = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(output, encoding="utf-8")
        print(f"saved: {args.out}")
    else:
        print(output, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

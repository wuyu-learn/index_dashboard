import argparse
import json
import sys

from backend.config import Settings
from .market_review import MarketReviewCollector, default_trade_date


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="采集财联社 A 股收评")
    parser.add_argument(
        "--date",
        default=default_trade_date(),
        help="目标日期 YYYYMMDD，默认上海时区当天",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="覆盖已有结果并重新执行搜索与正文抓取",
    )
    args = parser.parse_args(argv)

    try:
        result = MarketReviewCollector(Settings.from_env()).collect(
            args.date,
            force=args.force,
        )
    except Exception as exc:
        print(f"收评采集失败：{exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

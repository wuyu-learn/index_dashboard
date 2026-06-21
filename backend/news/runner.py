import argparse
import json
import sys

from backend.config import Settings
from .market_review import MarketReviewCollector, default_trade_date
from .morning_news import MorningNewsCollector


COLLECTORS = {
    "market-review": MarketReviewCollector,
    "morning-news": MorningNewsCollector,
}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="采集财联社新闻")
    parser.add_argument(
        "--type",
        choices=sorted(COLLECTORS),
        default="market-review",
        help="新闻类型，默认 market-review",
    )
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
        collector = COLLECTORS[args.type](Settings.from_env())
        result = collector.collect(
            args.date,
            force=args.force,
        )
    except Exception as exc:
        print(f"{args.type} 采集失败：{exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

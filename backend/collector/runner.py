import argparse
import sys
from typing import List

from backend.config import Settings
from .service import SyncResult, TushareCollector


def _print_results(results: List[SyncResult]) -> None:
    for result in results:
        date_text = f" date={result.trade_date}" if result.trade_date else ""
        scope_text = f" scope={result.scope}" if result.scope else ""
        file_text = f" file={result.file_path}" if result.file_path else ""
        print(
            f"{result.dataset}: {result.status} rows={result.row_count}"
            f"{date_text}{scope_text}{file_text}"
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Tushare ETF CSV 数据采集器")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser(
        "sync-basic",
        help="从本地 Excel 重建目标指数池",
    )

    weekly = subparsers.add_parser(
        "sync-index-weekly",
        help="增量同步当前 ETF 跟踪指数的周线",
    )
    weekly.add_argument(
        "--end-date",
        help="同步截止日期 YYYYMMDD，默认今天",
    )
    weekly.add_argument(
        "--index-code",
        action="append",
        dest="index_codes",
        help="只同步指定指数，可重复传入；指数必须属于当前跟踪池",
    )

    pipeline = subparsers.add_parser(
        "sync-weekly",
        help="重建指数池并按交易日分页同步全市场周线",
    )
    pipeline.add_argument(
        "--end-date",
        help="周线同步截止日期 YYYYMMDD，默认今天",
    )
    return parser


def main(argv: List[str] = None) -> int:
    args = build_parser().parse_args(argv)
    collector = TushareCollector(Settings.from_env())

    try:
        if args.command == "sync-basic":
            _print_results(collector.sync_basic())
        elif args.command == "sync-index-weekly":
            _print_results(
                collector.sync_tracked_index_weekly(
                    end_date=args.end_date,
                    index_codes=args.index_codes,
                )
            )
        elif args.command == "sync-weekly":
            _print_results(
                collector.sync_weekly_pipeline(end_date=args.end_date)
            )
        return 0
    except Exception as exc:
        print(f"同步失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

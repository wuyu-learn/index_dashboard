import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parent.parent
TRACKED = ROOT / "data" / "processed" / "tracked_indices.csv"
MAPPING = ROOT / "data" / "processed" / "index_weekly_code_map.csv"
WEEKLY_DIR = ROOT / "data" / "raw" / "index_weekly_by_date"
OUTPUT = ROOT / "designs" / "weekly-index-dashboard" / "data.js"
VISIBLE_CATEGORIES = ("行业主题", "规模指数")


def as_number(value):
    if pd.isna(value):
        return None
    return float(value)


def ranking_item(row, return_value):
    subcategory = row.get("category_secondary")
    short_name = row.get("index_short_name")
    return {
        "code": row["index_code"],
        "name": row["index_name"],
        "shortName": None if pd.isna(short_name) else short_name,
        "subcategory": None if pd.isna(subcategory) else subcategory,
        "return": float(return_value),
    }


def ranked(items, reverse, limit):
    return sorted(
        items,
        key=lambda item: (
            -item["return"] if reverse else item["return"],
            item["name"],
        ),
    )[:limit]


def main() -> None:
    tracked = pd.read_csv(TRACKED, dtype=str)
    mapping = pd.read_csv(MAPPING, dtype=str)
    tracked = tracked.merge(
        mapping[["index_code", "weekly_ts_code"]],
        on="index_code",
        how="left",
    )
    tracked = tracked[
        tracked["category_primary"].isin(VISIBLE_CATEGORIES)
        & tracked["weekly_ts_code"].notna()
    ]

    files = sorted(WEEKLY_DIR.glob("20*.csv"))
    if not files:
        raise RuntimeError("没有可用的按日期周线 CSV")

    quotes = [
        pd.read_csv(path, dtype={"ts_code": str, "trade_date": str})
        for path in files
    ]
    market = pd.concat(quotes, ignore_index=True)
    market = market.sort_values(["ts_code", "trade_date"])
    dates = sorted(market["trade_date"].dropna().unique().tolist())
    first_date = dates[0]
    latest_date = dates[-1]
    quote_groups = {code: group for code, group in market.groupby("ts_code")}

    category_payloads = []
    total_indices = 0
    for category in VISIBLE_CATEGORIES:
        category_rows = tracked[tracked["category_primary"] == category]
        period_items = {date: [] for date in dates}
        interval_items = []
        valid_codes = set()

        for _, row in category_rows.iterrows():
            weekly_code = row["weekly_ts_code"]
            if weekly_code not in quote_groups:
                continue

            history = (
                quote_groups[weekly_code]
                .drop_duplicates("trade_date", keep="last")
                .sort_values("trade_date")
            )
            has_period_data = False
            for _, quote in history.iterrows():
                trade_date = quote.get("trade_date")
                if trade_date not in period_items:
                    continue
                weekly_return = as_number(quote.get("pct_chg"))
                if weekly_return is None:
                    pre_close = as_number(quote.get("pre_close"))
                    close = as_number(quote.get("close"))
                    if pre_close in (None, 0) or close is None:
                        continue
                    weekly_return = close / pre_close - 1
                period_items[trade_date].append(ranking_item(row, weekly_return))
                has_period_data = True

            first_rows = history[history["trade_date"] == first_date]
            latest_rows = history[history["trade_date"] == latest_date]
            if not first_rows.empty and not latest_rows.empty:
                first_quote = first_rows.iloc[-1]
                latest_quote = latest_rows.iloc[-1]
                base = as_number(first_quote.get("pre_close"))
                if base in (None, 0):
                    base = as_number(first_quote.get("open"))
                close = as_number(latest_quote.get("close"))
                if base not in (None, 0) and close is not None:
                    interval_items.append(ranking_item(row, close / base - 1))

            if has_period_data:
                valid_codes.add(row["index_code"])

        latest_items = period_items[latest_date]
        periods = [
            {
                "date": date,
                "gainTop": ranked(period_items[date], True, 5),
                "lossTop": ranked(period_items[date], False, 5),
            }
            for date in dates
        ]
        category_payloads.append(
            {
                "name": category,
                "count": len(valid_codes),
                "latest": {
                    "gainTop": ranked(latest_items, True, 3),
                    "lossTop": ranked(latest_items, False, 3),
                },
                "interval": {
                    "gainTop": ranked(interval_items, True, 3),
                    "lossTop": ranked(interval_items, False, 3),
                },
                "periods": periods,
            }
        )
        total_indices += len(valid_codes)

    payload = {
        "categories": category_payloads,
        "dates": dates,
        "latestDate": latest_date,
        "firstDate": first_date,
        "indexCount": total_indices,
        "generatedAt": pd.Timestamp.now(tz="Asia/Shanghai").isoformat(),
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        "window.DASHBOARD_DATA = "
        + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        + ";\n",
        encoding="utf-8",
    )
    print(f"generated: {OUTPUT}")
    print(
        f"categories: {len(category_payloads)}, indices: {total_indices}, "
        f"periods: {len(dates)}, range: {first_date} - {latest_date}"
    )


if __name__ == "__main__":
    main()

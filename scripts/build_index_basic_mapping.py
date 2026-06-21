import json
import re
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parent.parent
WORKBOOK = ROOT / "data" / "data_result_fixed.xlsx"
INDEX_BASIC = ROOT / "data" / "raw" / "index_basic" / "index_basic.csv"
OUTPUT_JSON = ROOT / "data" / "metadata" / "index_basic_mapping.json"
OUTPUT_CSV = ROOT / "data" / "metadata" / "index_basic_match_report.csv"


def normalize_name(value: object) -> str:
    text = "" if pd.isna(value) else str(value)
    text = re.sub(r"\((CSI|SH|SZ)\)$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"指数$", "", text)
    return text.replace(" ", "").upper()


def main() -> None:
    source = pd.read_excel(WORKBOOK, dtype=str)
    index_basic = pd.read_csv(INDEX_BASIC, dtype=str)

    index_basic["code_upper"] = index_basic["ts_code"].str.upper()
    index_basic["stem_upper"] = (
        index_basic["ts_code"].str.rsplit(".", n=1).str[0].str.upper()
    )
    index_basic["name_normalized"] = index_basic["name"].map(normalize_name)

    results = []
    for row_number, row in source.iterrows():
        source_code = str(row["f_code"]).strip()
        code_upper = source_code.upper()
        stem_upper = code_upper.rsplit(".", 1)[0]
        name_normalized = normalize_name(row["f_name"])

        candidates = index_basic.loc[index_basic["code_upper"] == code_upper]
        method = "exact_code"

        if len(candidates) != 1:
            candidates = index_basic.loc[
                (index_basic["stem_upper"] == stem_upper)
                & (index_basic["name_normalized"] == name_normalized)
            ]
            method = "same_symbol_and_name"

        if len(candidates) != 1:
            candidates = index_basic.loc[
                index_basic["name_normalized"] == name_normalized
            ]
            method = "unique_name"

        if len(candidates) == 1:
            ts_code = str(candidates.iloc[0]["ts_code"])
            candidate_count = 1
        else:
            ts_code = None
            candidate_count = len(candidates)
            method = "unmatched" if candidate_count == 0 else "ambiguous"

        results.append(
            {
                "excel_row": row_number + 2,
                "f_name": row["f_name"],
                "f_code": source_code,
                "ts_code": ts_code,
                "match_method": method,
                "candidate_count": candidate_count,
            }
        )

    report = pd.DataFrame(results)
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(
        json.dumps(results, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    report.to_csv(OUTPUT_CSV, index=False, encoding="utf-8")

    print(f"rows: {len(report)}")
    print(f"matched: {report['ts_code'].notna().sum()}")
    print(f"unmatched: {report['ts_code'].isna().sum()}")
    print(report["match_method"].value_counts().to_string())


if __name__ == "__main__":
    main()

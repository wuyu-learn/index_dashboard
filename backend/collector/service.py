from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import List, Optional, Sequence

import pandas as pd

from backend.config import Settings
from .client import TushareClient
from .storage import SyncStateStore, write_csv_atomic


INDEX_WEEKLY_FIELDS = (
    "ts_code,trade_date,close,open,high,low,pre_close,"
    "change,pct_chg,vol,amount"
)
INDEX_WEEKLY_PAGE_SIZE = 1000
INDEX_WEEKLY_CALENDAR_CODE = "000001.SH"


@dataclass(frozen=True)
class SyncResult:
    dataset: str
    status: str
    row_count: int
    file_path: Optional[Path] = None
    trade_date: Optional[str] = None
    scope: Optional[str] = None


class TushareCollector:
    def __init__(
        self,
        settings: Settings,
        client: Optional[TushareClient] = None,
    ) -> None:
        self.settings = settings
        self.client = client or TushareClient(settings)
        self.state = SyncStateStore(settings.data_dir)

    def sync_basic(self) -> List[SyncResult]:
        return [self.build_tracked_index_pool()]

    def sync_weekly_pipeline(
        self,
        end_date: Optional[str] = None,
    ) -> List[SyncResult]:
        """Rebuild the index pool, then download weekly bars by trade date."""
        results = self.sync_basic()
        results.extend(self.sync_market_index_weekly(end_date=end_date))
        return results

    def build_tracked_index_pool(self) -> SyncResult:
        source = self.settings.index_pool_file
        if not source.exists():
            raise RuntimeError(f"缺少本地指数池文件：{source}")
        try:
            data = pd.read_excel(source, dtype=str)
        except ImportError as exc:
            raise RuntimeError(
                "读取 xlsx 需要 openpyxl，请执行：pip install -r requirements.txt"
            ) from exc

        required = {
            "f_name",
            "f_code",
            "f_short_name",
            "f_pro_type",
            "Q",
            "P",
        }
        missing = required - set(data.columns)
        if missing:
            raise ValueError(
                f"{source.name} 缺少字段：{', '.join(sorted(missing))}"
            )

        source_columns = [
            "f_code",
            "f_name",
            "f_short_name",
            "f_pro_type",
            "Q",
            "P",
        ]
        if "ts_code" in data.columns:
            source_columns.append("ts_code")
        tracked = data[source_columns].copy()
        tracked = tracked.rename(
            columns={
                "f_code": "source_index_code",
                "f_name": "index_name",
                "f_short_name": "index_short_name",
                "f_pro_type": "product_type",
                "Q": "category_primary",
                "P": "category_secondary",
            }
        )
        if "ts_code" in tracked.columns:
            mapped_code = tracked["ts_code"].astype("string").str.strip()
            tracked["index_code"] = mapped_code.where(
                mapped_code.notna() & mapped_code.ne(""),
                tracked["source_index_code"],
            )
        else:
            tracked["index_code"] = tracked["source_index_code"]
        tracked["index_code"] = tracked["index_code"].astype("string").str.strip()
        tracked = tracked.loc[
            tracked["index_code"].notna() & tracked["index_code"].ne("")
        ]
        tracked = tracked.drop_duplicates(["index_code"], keep="last")
        tracked["ts_code_matched"] = (
            tracked.get("ts_code", pd.Series(pd.NA, index=tracked.index))
            .astype("string")
            .str.strip()
            .notna()
        )
        tracked["has_weekly_data"] = tracked["index_code"].map(
            lambda code: self._weekly_path(str(code)).exists()
        )
        tracked["last_weekly_trade_date"] = tracked["index_code"].map(
            self._last_weekly_trade_date
        )
        tracked["source_file"] = source.name
        tracked["updated_at"] = datetime.now().astimezone().isoformat(
            timespec="seconds"
        )
        tracked = tracked.sort_values("index_code").reset_index(drop=True)
        return self._save(
            "tracked_indices",
            tracked,
            self.settings.data_dir / "processed" / "tracked_indices.csv",
        )

    def sync_tracked_index_weekly(
        self,
        end_date: Optional[str] = None,
        index_codes: Optional[Sequence[str]] = None,
    ) -> List[SyncResult]:
        end = end_date or date.today().strftime("%Y%m%d")
        self._validate_date(end)
        tracked = self._load_or_build_tracked_indices()
        available_codes = set(tracked["index_code"].dropna().astype(str))
        codes = sorted(set(index_codes or available_codes))
        unknown = set(codes) - available_codes
        if unknown:
            raise ValueError(
                "以下指数不在当前 ETF 跟踪指数池中："
                + ", ".join(sorted(unknown))
            )

        results: List[SyncResult] = []
        for index_code in codes:
            results.append(self.sync_index_weekly(index_code, end))
        self.build_tracked_index_pool()
        return results

    def sync_market_index_weekly(
        self,
        end_date: Optional[str] = None,
    ) -> List[SyncResult]:
        end = end_date or date.today().strftime("%Y%m%d")
        self._validate_date(end)
        tracked = self._load_or_build_tracked_indices()
        start = self._market_weekly_start_date(tracked, end)
        trade_dates = self._discover_weekly_trade_dates(start, end)
        if not trade_dates:
            result = SyncResult(
                "index_weekly_market", "empty", 0, scope=f"{start}:{end}"
            )
            self.state.record(
                "index_weekly_market",
                "empty",
                0,
                scope=f"{start}:{end}",
            )
            return [result]

        market_frames: List[pd.DataFrame] = []
        results: List[SyncResult] = []
        for trade_date in trade_dates:
            market_data, page_count = self._download_weekly_trade_date(trade_date)
            market_frames.append(market_data)
            raw_path = self._market_weekly_path(trade_date)
            results.append(
                SyncResult(
                    "index_weekly_market_date",
                    "success",
                    len(market_data),
                    raw_path,
                    trade_date=trade_date,
                    scope=f"{page_count} pages",
                )
            )
            self.state.record(
                "index_weekly_market_date",
                "success",
                len(market_data),
                file_path=raw_path,
                trade_date=trade_date,
                scope=f"{page_count} pages",
            )

        market_all = pd.concat(market_frames, ignore_index=True)
        mapping = self._build_weekly_code_mapping(tracked, market_all)
        mapping_path = (
            self.settings.data_dir
            / "processed"
            / "index_weekly_code_map.csv"
        )
        write_csv_atomic(mapping, mapping_path)
        results.append(
            SyncResult(
                "index_weekly_code_map",
                "success",
                len(mapping),
                mapping_path,
            )
        )

        saved_count = 0
        saved_rows = 0
        matched = mapping.loc[mapping["weekly_ts_code"].notna()].copy()
        for _, map_row in matched.iterrows():
            index_code = str(map_row["index_code"])
            weekly_code = str(map_row["weekly_ts_code"])
            rows = market_all.loc[
                market_all["ts_code"].astype(str).str.upper()
                == weekly_code.upper()
            ].copy()
            if rows.empty:
                continue
            rows["source_ts_code"] = rows["ts_code"]
            rows["ts_code"] = index_code
            path = self._weekly_path(index_code)
            existing = self._read_optional_csv(path)
            combined = pd.concat([existing, rows], ignore_index=True)
            combined = self._normalize(
                combined,
                required=("ts_code", "trade_date"),
                unique=("ts_code", "trade_date"),
                sort_by=("trade_date",),
            )
            write_csv_atomic(combined, path)
            saved_count += 1
            saved_rows += len(rows)
            self.state.record(
                "index_weekly",
                "success",
                len(rows),
                file_path=path,
                scope=index_code,
            )

        self.build_tracked_index_pool()
        result = SyncResult(
            "index_weekly_market",
            "success",
            saved_rows,
            scope=(
                f"{len(trade_dates)} dates, {saved_count} indices, "
                f"{mapping['weekly_ts_code'].isna().sum()} unmatched"
            ),
        )
        self.state.record(
            "index_weekly_market",
            "success",
            saved_rows,
            scope=result.scope,
        )
        results.append(result)
        return results

    def sync_index_weekly(self, index_code: str, end_date: str) -> SyncResult:
        self._validate_date(end_date)
        path = self._weekly_path(index_code)
        existing = self._read_optional_csv(path)
        start_date = self._weekly_start_date(existing, end_date)
        try:
            data = self.client.call(
                "index_weekly",
                ts_code=index_code,
                start_date=start_date,
                end_date=end_date,
                fields=INDEX_WEEKLY_FIELDS,
            )
            if data is None or data.empty:
                result = SyncResult(
                    "index_weekly", "empty", 0, path if path.exists() else None,
                    scope=index_code,
                )
                self.state.record(
                    "index_weekly", "empty", 0,
                    file_path=path if path.exists() else None,
                    scope=index_code,
                )
                return result

            data = self._normalize(
                data,
                required=("ts_code", "trade_date"),
                unique=("ts_code", "trade_date"),
                sort_by=("trade_date",),
            )
            returned_codes = set(data["ts_code"].astype(str))
            returned_codes_normalized = {code.upper() for code in returned_codes}
            if returned_codes_normalized != {index_code.upper()}:
                raise ValueError(
                    f"index_weekly({index_code}) 返回了其他指数："
                    f"{sorted(returned_codes)}"
                )
            # Tushare may normalize an h-prefixed CSI code to uppercase.
            # Keep the pool's canonical code so filenames and CSV keys agree.
            data["ts_code"] = index_code

            combined = pd.concat([existing, data], ignore_index=True)
            combined = self._normalize(
                combined,
                required=("ts_code", "trade_date"),
                unique=("ts_code", "trade_date"),
                sort_by=("trade_date",),
            )
            write_csv_atomic(combined, path)
            result = SyncResult(
                "index_weekly", "success", len(data), path, scope=index_code
            )
            self.state.record(
                "index_weekly", "success", len(data),
                file_path=path, scope=index_code,
            )
            return result
        except Exception as exc:
            self._record_failure("index_weekly", exc, scope=index_code)
            raise

    def _save(
        self,
        dataset: str,
        data: pd.DataFrame,
        path: Path,
        trade_date: str = None,
    ) -> SyncResult:
        write_csv_atomic(data, path)
        result = SyncResult(dataset, "success", len(data), path, trade_date)
        self.state.record(
            dataset,
            "success",
            len(data),
            file_path=path,
            trade_date=trade_date,
        )
        return result

    def _record_failure(
        self,
        dataset: str,
        error: Exception,
        trade_date: str = None,
        scope: str = None,
    ) -> None:
        self.state.record(
            dataset,
            "failed",
            0,
            trade_date=trade_date,
            scope=scope,
            error=str(error),
        )

    def _load_or_build_tracked_indices(self) -> pd.DataFrame:
        path = self.settings.data_dir / "processed" / "tracked_indices.csv"
        if not path.exists():
            self.build_tracked_index_pool()
        tracked = self._read_required_csv(path)
        if "index_code" not in tracked.columns:
            raise ValueError("tracked_indices.csv 缺少 index_code 字段")
        return tracked

    def _weekly_start_date(
        self,
        existing: pd.DataFrame,
        end_date: str,
    ) -> str:
        configured_start = self.settings.index_weekly_start_date
        self._validate_date(configured_start)
        if configured_start > end_date:
            raise ValueError(
                f"指数周线起始日期 {configured_start} 晚于截止日期 {end_date}"
            )

        if not existing.empty and "trade_date" in existing.columns:
            valid_dates = pd.to_datetime(
                existing["trade_date"].astype(str),
                format="%Y%m%d",
                errors="coerce",
            ).dropna()
            if not valid_dates.empty:
                start = valid_dates.max().date() - timedelta(
                    days=self.settings.index_weekly_lookback_days
                )
                return max(start.strftime("%Y%m%d"), configured_start)

        return configured_start

    def _market_weekly_start_date(
        self,
        tracked: pd.DataFrame,
        end_date: str,
    ) -> str:
        configured_start = self.settings.index_weekly_start_date
        self._validate_date(configured_start)
        if configured_start > end_date:
            raise ValueError(
                f"指数周线起始日期 {configured_start} 晚于截止日期 {end_date}"
            )
        mapping_path = (
            self.settings.data_dir
            / "processed"
            / "index_weekly_code_map.csv"
        )
        if not mapping_path.exists():
            return configured_start
        dates = pd.to_datetime(
            tracked.get("last_weekly_trade_date", pd.Series(dtype=str)),
            format="%Y%m%d",
            errors="coerce",
        ).dropna()
        if dates.empty:
            return configured_start
        start = dates.max().date() - timedelta(
            days=self.settings.index_weekly_lookback_days
        )
        return max(start.strftime("%Y%m%d"), configured_start)

    def _discover_weekly_trade_dates(
        self,
        start_date: str,
        end_date: str,
    ) -> List[str]:
        data = self.client.call(
            "index_weekly",
            ts_code=INDEX_WEEKLY_CALENDAR_CODE,
            start_date=start_date,
            end_date=end_date,
            fields="ts_code,trade_date",
        )
        if data is None or data.empty:
            return []
        if "trade_date" not in data.columns:
            raise ValueError("index_weekly 日期探测结果缺少 trade_date")
        dates = data["trade_date"].dropna().astype(str).unique()
        return sorted(date for date in dates if start_date <= date <= end_date)

    def _download_weekly_trade_date(
        self,
        trade_date: str,
    ) -> tuple:
        frames: List[pd.DataFrame] = []
        offset = 0
        while True:
            page = self.client.call(
                "index_weekly",
                trade_date=trade_date,
                fields=INDEX_WEEKLY_FIELDS,
                limit=INDEX_WEEKLY_PAGE_SIZE,
                offset=offset,
            )
            if page is None:
                page = pd.DataFrame()
            frames.append(page)
            if len(page) < INDEX_WEEKLY_PAGE_SIZE:
                break
            offset += INDEX_WEEKLY_PAGE_SIZE
            if offset > 100000:
                raise RuntimeError(
                    f"index_weekly({trade_date}) 分页超过安全上限"
                )

        data = (
            pd.concat(frames, ignore_index=True)
            if frames
            else pd.DataFrame(columns=INDEX_WEEKLY_FIELDS.split(","))
        )
        if not data.empty:
            data = self._normalize(
                data,
                required=("ts_code", "trade_date"),
                unique=("ts_code", "trade_date"),
                sort_by=("ts_code",),
            )
            unexpected = set(data["trade_date"].astype(str)) - {trade_date}
            if unexpected:
                raise ValueError(
                    f"按日期获取周线时返回其他日期：{sorted(unexpected)}"
                )
        path = self._market_weekly_path(trade_date)
        write_csv_atomic(data, path)
        return data, len(frames)

    def _build_weekly_code_mapping(
        self,
        tracked: pd.DataFrame,
        market_data: pd.DataFrame,
    ) -> pd.DataFrame:
        available = sorted(market_data["ts_code"].dropna().astype(str).unique())
        available_by_upper = {code.upper(): code for code in available}
        names = self._load_index_basic_names()
        market_names = pd.DataFrame({"weekly_ts_code": available})
        market_names["index_name"] = market_names["weekly_ts_code"].map(names)
        market_names["name_normalized"] = market_names["index_name"].map(
            self._normalize_name
        )
        name_counts = market_names.groupby("name_normalized")[
            "weekly_ts_code"
        ].nunique()
        unique_names = set(name_counts.loc[name_counts == 1].index)
        name_to_code = dict(
            zip(
                market_names.loc[
                    market_names["name_normalized"].isin(unique_names),
                    "name_normalized",
                ],
                market_names.loc[
                    market_names["name_normalized"].isin(unique_names),
                    "weekly_ts_code",
                ],
            )
        )

        rows = []
        for _, row in tracked.iterrows():
            index_code = str(row["index_code"])
            direct = available_by_upper.get(index_code.upper())
            if direct:
                weekly_code = direct
                method = "exact_code"
            else:
                normalized_name = self._normalize_name(row.get("index_name"))
                weekly_code = name_to_code.get(normalized_name)
                method = "unique_name" if weekly_code else "unmatched"
            rows.append(
                {
                    "index_code": index_code,
                    "index_name": row.get("index_name"),
                    "weekly_ts_code": weekly_code,
                    "match_method": method,
                }
            )
        return pd.DataFrame(rows).sort_values("index_code").reset_index(drop=True)

    def _load_index_basic_names(self) -> dict:
        path = (
            self.settings.data_dir
            / "raw"
            / "index_basic"
            / "index_basic.csv"
        )
        data = self._read_optional_csv(path)
        if data.empty or not {"ts_code", "name"}.issubset(data.columns):
            return {}
        return dict(
            zip(data["ts_code"].astype(str), data["name"])
        )

    @staticmethod
    def _normalize_name(value: object) -> str:
        if pd.isna(value):
            return ""
        text = str(value).strip().upper().replace(" ", "")
        for suffix in ("(CSI)", "(SH)", "(SZ)"):
            if text.endswith(suffix):
                text = text[: -len(suffix)]
        if text.endswith("指数"):
            text = text[:-2]
        return text

    def _weekly_path(self, index_code: str) -> Path:
        safe_code = index_code.replace("/", "_")
        return self.settings.data_dir / "raw" / "index_weekly" / f"{safe_code}.csv"

    def _market_weekly_path(self, trade_date: str) -> Path:
        return (
            self.settings.data_dir
            / "raw"
            / "index_weekly_by_date"
            / f"{trade_date}.csv"
        )

    def _last_weekly_trade_date(self, index_code: object) -> object:
        data = self._read_optional_csv(self._weekly_path(str(index_code)))
        if data.empty or "trade_date" not in data.columns:
            return pd.NA
        values = data["trade_date"].dropna().astype(str)
        return values.max() if not values.empty else pd.NA

    @staticmethod
    def _read_required_csv(path: Path) -> pd.DataFrame:
        if not path.exists():
            raise RuntimeError(f"缺少必要数据文件：{path}")
        return pd.read_csv(path, dtype=str, keep_default_na=True)

    @staticmethod
    def _read_optional_csv(path: Path) -> pd.DataFrame:
        if not path.exists():
            return pd.DataFrame()
        return pd.read_csv(path, dtype=str, keep_default_na=True)

    @staticmethod
    def _normalize(
        data: pd.DataFrame,
        required: tuple,
        unique: tuple,
        sort_by: tuple,
    ) -> pd.DataFrame:
        missing = [column for column in required if column not in data.columns]
        if missing:
            raise ValueError(f"接口返回缺少必要字段：{', '.join(missing)}")

        normalized = data.copy()
        for column in (
            "ts_code", "trade_date", "setup_date", "list_date",
            "pub_date", "base_date", "exp_date", "index_code",
        ):
            if column in normalized.columns:
                normalized[column] = normalized[column].astype("string")

        normalized = normalized.drop_duplicates(list(unique), keep="last")
        return normalized.sort_values(list(sort_by)).reset_index(drop=True)

    @staticmethod
    def _validate_date(value: str) -> None:
        if len(value) != 8 or not value.isdigit():
            raise ValueError("日期必须使用 YYYYMMDD 格式，例如 20260619")
        try:
            datetime.strptime(value, "%Y%m%d")
        except ValueError as exc:
            raise ValueError(f"无效日期：{value}") from exc

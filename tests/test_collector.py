from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import pandas as pd

from backend.collector.client import TushareClient
from backend.collector.service import TushareCollector
from backend.config import Settings


class FakePro:
    def __init__(self):
        self.calls = []

    def index_weekly(
        self,
        ts_code=None,
        start_date=None,
        end_date=None,
        trade_date=None,
        fields=None,
        limit=None,
        offset=None,
    ):
        self.calls.append(
            (
                "index_weekly",
                ts_code,
                start_date,
                end_date,
                trade_date,
                limit,
                offset,
            )
        )
        if trade_date:
            if offset:
                return pd.DataFrame()
            return pd.DataFrame(
                [
                    {
                        "ts_code": "000300.SH",
                        "trade_date": trade_date,
                        "close": 3920.0,
                    },
                    {
                        "ts_code": "399608.SZ",
                        "trade_date": trade_date,
                        "close": 1200.0,
                    },
                ]
            )
        return pd.DataFrame(
            [
                {
                    "ts_code": ts_code,
                    "trade_date": "20260612",
                    "close": 3900.0,
                },
                {
                    "ts_code": ts_code,
                    "trade_date": "20260619",
                    "close": 3920.0,
                },
            ]
        )


class UppercaseCodePro(FakePro):
    def index_weekly(self, **kwargs):
        data = super().index_weekly(**kwargs)
        ts_code = kwargs.get("ts_code")
        if not ts_code:
            return data
        data["ts_code"] = ts_code.upper()
        return data


class CollectorTests(unittest.TestCase):
    def make_collector(self, directory: str, pro=None) -> TushareCollector:
        index_pool_file = Path(directory) / "data_result_fixed.xlsx"
        pd.DataFrame(
            [
                {
                    "f_name": "沪深300指数",
                    "f_code": "000300.SH",
                    "f_short_name": "沪深300",
                    "f_pro_type": "221",
                    "Q": "规模指数",
                    "P": "大盘",
                    "ts_code": "000300.SH",
                },
                {
                    "f_name": "沪深300指数",
                    "f_code": "000300.SH",
                    "f_short_name": "沪深300",
                    "f_pro_type": "221",
                    "Q": "规模指数",
                    "P": "大盘",
                    "ts_code": "000300.SH",
                },
            ]
        ).to_excel(index_pool_file, index=False)
        settings = Settings(
            tushare_token="test",
            data_dir=Path(directory),
            request_interval_seconds=0,
            retry_times=1,
            index_pool_file=index_pool_file,
        )
        client = TushareClient(settings, pro_api=pro or FakePro(), sleep=lambda _: None)
        return TushareCollector(settings, client)

    def test_sync_all_datasets(self):
        with TemporaryDirectory() as directory:
            collector = self.make_collector(directory)
            basic = collector.sync_basic()

            self.assertEqual(
                [result.dataset for result in basic],
                ["tracked_indices"],
            )
            self.assertTrue(
                (Path(directory) / "metadata/sync_state.json").exists()
            )
            tracked = pd.read_csv(
                Path(directory) / "processed/tracked_indices.csv",
                dtype=str,
            )
            self.assertEqual(tracked["index_code"].tolist(), ["000300.SH"])
            self.assertEqual(tracked["category_primary"].tolist(), ["规模指数"])
            self.assertEqual(tracked["category_secondary"].tolist(), ["大盘"])

    def test_sync_tracked_index_weekly_merges_by_index(self):
        with TemporaryDirectory() as directory:
            collector = self.make_collector(directory)
            collector.sync_basic()

            first = collector.sync_tracked_index_weekly(end_date="20260619")
            second = collector.sync_tracked_index_weekly(end_date="20260619")

            self.assertEqual(len(first), 1)
            self.assertEqual(first[0].scope, "000300.SH")
            self.assertEqual(second[0].status, "success")
            weekly_path = Path(directory) / "raw/index_weekly/000300.SH.csv"
            weekly = pd.read_csv(weekly_path, dtype={"trade_date": str})
            self.assertEqual(len(weekly), 2)
            self.assertEqual(
                weekly["trade_date"].tolist(),
                ["20260612", "20260619"],
            )

            tracked = pd.read_csv(
                Path(directory) / "processed/tracked_indices.csv",
                dtype=str,
            )
            self.assertEqual(
                tracked.loc[0, "last_weekly_trade_date"],
                "20260619",
            )

    def test_weekly_rejects_index_outside_current_pool(self):
        with TemporaryDirectory() as directory:
            collector = self.make_collector(directory)
            collector.sync_basic()
            with self.assertRaises(ValueError):
                collector.sync_tracked_index_weekly(
                    end_date="20260619",
                    index_codes=["000001.SH"],
                )

    def test_weekly_accepts_tushare_code_case_normalization(self):
        with TemporaryDirectory() as directory:
            collector = self.make_collector(directory, UppercaseCodePro())
            collector.settings.index_pool_file
            pool = pd.read_excel(collector.settings.index_pool_file, dtype=str)
            pool["f_code"] = "h00846.CSI"
            pool["ts_code"] = "h00846.CSI"
            pool.to_excel(collector.settings.index_pool_file, index=False)
            collector.sync_basic()

            result = collector.sync_index_weekly("h00846.CSI", "20260619")

            self.assertEqual(result.status, "success")
            saved = pd.read_csv(result.file_path, dtype=str)
            self.assertEqual(set(saved["ts_code"]), {"h00846.CSI"})

    def test_weekly_pipeline_rebuilds_pool_before_weekly_sync(self):
        with TemporaryDirectory() as directory:
            pro = FakePro()
            collector = self.make_collector(directory, pro)

            collector.sync_weekly_pipeline(end_date="20260619")

            weekly_call = pro.calls[0]
            self.assertEqual(weekly_call[2], "20260501")
            self.assertTrue(
                any(call[4] == "20260612" for call in pro.calls)
            )
            self.assertTrue(
                any(call[4] == "20260619" for call in pro.calls)
            )
            self.assertTrue(
                (Path(directory) / "processed/tracked_indices.csv").exists()
            )
            self.assertTrue(
                (
                    Path(directory)
                    / "raw/index_weekly_by_date/20260619.csv"
                ).exists()
            )

    def test_market_weekly_maps_unique_name_to_alternate_code(self):
        with TemporaryDirectory() as directory:
            collector = self.make_collector(directory)
            pool = pd.read_excel(collector.settings.index_pool_file, dtype=str)
            pool["f_name"] = "科技100"
            pool["f_short_name"] = "科技100"
            pool["f_code"] = "931187.CSI"
            pool["ts_code"] = "931187.CSI"
            pool.to_excel(collector.settings.index_pool_file, index=False)
            index_basic = Path(directory) / "raw/index_basic/index_basic.csv"
            index_basic.parent.mkdir(parents=True)
            pd.DataFrame(
                [{"ts_code": "399608.SZ", "name": "科技100"}]
            ).to_csv(index_basic, index=False)

            collector.sync_weekly_pipeline(end_date="20260619")

            mapping = pd.read_csv(
                Path(directory) / "processed/index_weekly_code_map.csv",
                dtype=str,
            )
            self.assertEqual(mapping.loc[0, "weekly_ts_code"], "399608.SZ")
            self.assertEqual(mapping.loc[0, "match_method"], "unique_name")
            weekly = pd.read_csv(
                Path(directory) / "raw/index_weekly/931187.CSI.csv",
                dtype=str,
            )
            self.assertEqual(set(weekly["source_ts_code"]), {"399608.SZ"})

    def test_rejects_invalid_date(self):
        with TemporaryDirectory() as directory:
            collector = self.make_collector(directory)
            with self.assertRaises(ValueError):
                collector.sync_tracked_index_weekly(end_date="2026-06-19")
            with self.assertRaises(ValueError):
                collector.sync_tracked_index_weekly(end_date="20261340")


if __name__ == "__main__":
    unittest.main()

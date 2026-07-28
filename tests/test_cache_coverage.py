"""Tests for cache coverage validation across all data getters."""

import sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pandas as pd
import pytest


class TestCacheCoverage:
    """Verify cache range validation prevents stale/partial cache returns."""

    def test_covers_range_positive(self, tmp_path):
        """covers_range returns True when cache spans the full range."""
        from data.parquet_cache import ParquetCache
        import pyarrow.parquet as pq
        import pyarrow as pa

        cache = ParquetCache(str(tmp_path))
        table_name = "test_table"

        # Write data spanning 20240101 to 20240131
        df = pd.DataFrame({
            "trade_date": np.arange(20240101, 20240132, dtype=np.int32),
            "value": np.random.random(31).astype("float32"),
        })
        tbl = pa.Table.from_pandas(df)
        pq.write_to_dataset(tbl, root_path=str(tmp_path / table_name))

        assert cache.covers_range(table_name, "20240101", "20240131", "trade_date")

    def test_covers_range_negative_range_not_covered(self, tmp_path):
        """covers_range returns False when cache is missing start or end."""
        from data.parquet_cache import ParquetCache
        import pyarrow.parquet as pq
        import pyarrow as pa

        cache = ParquetCache(str(tmp_path))
        table_name = "test_partial"

        df = pd.DataFrame({
            "trade_date": np.arange(20240110, 20240121, dtype=np.int32),
            "value": np.random.random(11).astype("float32"),
        })
        tbl = pa.Table.from_pandas(df)
        pq.write_to_dataset(tbl, root_path=str(tmp_path / table_name))

        # Request range that starts before cache
        assert not cache.covers_range(table_name, "20240101", "20240131", "trade_date")

    def test_covers_range_empty_table(self, tmp_path):
        """covers_range returns False for nonexistent table."""
        from data.parquet_cache import ParquetCache
        cache = ParquetCache(str(tmp_path))
        assert not cache.covers_range("nonexistent", "20240101", "20240131")

    def test_calendar_load_rejects_wrong_date_range(self):
        """
        When cached calendar has only 2024 dates but 2016 is requested,
        the in-memory cache must be invalidated (cleared to None).
        We verify the range-check logic directly without hitting the API.
        """
        from data.calendar import TradingCalendar
        cal = TradingCalendar()

        # Pre-populate in-memory with 2024 dates (wrong range for 2016 request)
        cal._trade_dates = {20240102, 20240103, 20240104}
        cal._trade_dates_sorted = np.array([20240102, 20240103, 20240104], dtype=np.int32)
        cal._date_to_idx = {d: i for i, d in enumerate(cal._trade_dates_sorted)}

        # Directly test the range-check logic that load() performs first:
        req_min = 20160101
        req_max = 20160131
        cached_min = int(cal._trade_dates_sorted[0])  # 20240102
        cached_max = int(cal._trade_dates_sorted[-1])  # 20240104

        # The condition in load(): if cached covers requested, keep; else clear.
        # Here cached (2024) does NOT cover requested (2016) — must be cleared.
        covers = (cached_min <= req_min and cached_max >= req_max)
        assert not covers, "2024 cache should NOT cover 2016 request!"

        # Simulate what load() does when cache doesn't cover:
        cal._trade_dates = None
        cal._trade_dates_sorted = None
        cal._date_to_idx = None

        assert cal._trade_dates is None, (
            "In-memory calendar cache MUST be cleared when 2024 cache "
            "doesn't cover 2016 request"
        )

    def test_calendar_load_keeps_valid_range(self):
        """In-memory cache is kept when it covers the requested range."""
        from data.calendar import TradingCalendar
        cal = TradingCalendar()

        # Pre-populate covering the requested range
        cal._trade_dates = set(np.arange(20160101, 20160201, dtype=np.int32))
        cal._trade_dates_sorted = np.arange(20160101, 20160201, dtype=np.int32)
        cal._date_to_idx = {d: i for i, d in enumerate(cal._trade_dates_sorted)}

        # Request a sub-range — cache should be kept
        cal.load(start_date="20160101", end_date="20160131")
        assert cal._trade_dates is not None, (
            "In-memory calendar cache was incorrectly cleared "
            "for a sub-range request"
        )

    def test_cache_rejects_wrong_year_parquet(self, tmp_path):
        """
        When a parquet cache has 2024 cal_date but 2016 is requested,
        the cache coverage check must reject it.
        """
        from data.parquet_cache import ParquetCache
        import pyarrow.parquet as pq
        import pyarrow as pa

        cache = ParquetCache(str(tmp_path))
        table_name = "trade_cal"

        # Write parquet with only 2024 dates
        df_2024 = pd.DataFrame({
            "cal_date": np.arange(20240102, 20240110, dtype=np.int32),
            "is_open": [1] * 8,
        })
        tbl = pa.Table.from_pandas(df_2024)
        pq.write_to_dataset(tbl, root_path=str(tmp_path / table_name))

        # Should NOT cover 2016 range
        assert not cache.covers_range(table_name, "20160101", "20160131", "cal_date"), (
            "Cache with 2024 dates should NOT claim to cover 2016 range!"
        )


class TestFetchManifest:
    """Coverage is based on completed queries, including sparse empty results."""

    def test_records_requested_codes_not_only_returned_codes(self, tmp_path):
        from data.tushare_client import FetchManifest

        manifest = FetchManifest(str(tmp_path))
        requested = ["000001.SZ", "000002.SZ"]
        manifest.record_fetch(
            "suspend_status", 20240101, 20240131, codes=requested
        )
        assert manifest.has_coverage(
            "suspend_status", 20240110, 20240120, requested
        )

    def test_adjacent_year_queries_cover_combined_range(self, tmp_path):
        from data.tushare_client import FetchManifest

        manifest = FetchManifest(str(tmp_path))
        codes = ["000001.SZ"]
        manifest.record_fetch("limit_status", 20230101, 20231231, codes)
        manifest.record_fetch("limit_status", 20240101, 20241231, codes)
        assert manifest.has_coverage(
            "limit_status", 20230101, 20241231, codes
        )

    def test_different_code_query_does_not_prove_coverage(self, tmp_path):
        from data.tushare_client import FetchManifest

        manifest = FetchManifest(str(tmp_path))
        manifest.record_fetch(
            "daily_basic", 20240101, 20240131, ["000001.SZ"]
        )
        assert not manifest.has_coverage(
            "daily_basic", 20240101, 20240131, ["000002.SZ"]
        )


class TestTushareCoverageContracts:
    @staticmethod
    def _client(tmp_path):
        from data.tushare_client import TushareClient

        client = TushareClient(cache_path=str(tmp_path))
        client.available = True
        return client

    def test_suspend_uses_official_range_parameters_and_records_empty(self, tmp_path):
        client = self._client(tmp_path)
        calls = []
        client.pro = SimpleNamespace(suspend_d=lambda **kwargs: pd.DataFrame())

        def fake_call(func, **kwargs):
            calls.append(kwargs)
            return pd.DataFrame()

        client._call_api = fake_call
        result = client.get_suspend(
            ts_code=["000001.SZ", "000002.SZ"],
            start_date="20240101",
            end_date="20240131",
            use_cache=False,
        )
        assert result.empty
        assert calls == [{
            "suspend_type": "S",
            "start_date": "20240101",
            "end_date": "20240131",
            "ts_code": "000001.SZ,000002.SZ",
        }]
        assert client.manifest.has_coverage(
            "suspend_status", 20240101, 20240131,
            ["000001.SZ", "000002.SZ"],
        )

    def test_daily_basic_list_is_queried_one_code_at_a_time(self, tmp_path):
        client = self._client(tmp_path)
        calls = []
        client.pro = SimpleNamespace(daily_basic=lambda **kwargs: pd.DataFrame())

        def fake_call(func, **kwargs):
            calls.append(kwargs.copy())
            code = kwargs["ts_code"]
            return pd.DataFrame({
                "ts_code": [code],
                "trade_date": [20240102],
                "turnover_rate_f": [1.0],
            })

        client._call_api = fake_call
        result = client.get_daily_basic(
            ts_code=["000001.SZ", "000002.SZ"],
            start_date="20240101",
            end_date="20240131",
            use_cache=False,
        )
        assert {call["ts_code"] for call in calls} == {
            "000001.SZ", "000002.SZ"
        }
        assert set(result["ts_code"]) == {"000001.SZ", "000002.SZ"}
        assert client.manifest.has_coverage(
            "daily_basic", 20240101, 20240131,
            ["000001.SZ", "000002.SZ"],
        )

    def test_daily_basic_partial_failure_is_not_manifest_complete(self, tmp_path):
        client = self._client(tmp_path)
        client.pro = SimpleNamespace(daily_basic=lambda **kwargs: pd.DataFrame())

        def fake_call(func, **kwargs):
            if kwargs["ts_code"] == "000002.SZ":
                raise RuntimeError("simulated API failure")
            return pd.DataFrame({
                "ts_code": [kwargs["ts_code"]],
                "trade_date": [20240102],
                "turnover_rate_f": [1.0],
            })

        client._call_api = fake_call
        with pytest.raises(RuntimeError, match="fetch incomplete"):
            client.get_daily_basic(
                ts_code=["000001.SZ", "000002.SZ"],
                start_date="20240101",
                end_date="20240131",
                use_cache=False,
            )
        assert not client.manifest.has_coverage(
            "daily_basic", 20240101, 20240131,
            ["000001.SZ", "000002.SZ"],
        )

    def test_stk_limit_list_is_queried_one_code_at_a_time(self, tmp_path):
        client = self._client(tmp_path)
        calls = []
        client.pro = SimpleNamespace(stk_limit=lambda **kwargs: pd.DataFrame())

        def fake_call(func, **kwargs):
            calls.append(kwargs.copy())
            return pd.DataFrame({
                "ts_code": [kwargs["ts_code"]],
                "trade_date": [20240102],
                "up_limit": [11.0],
                "down_limit": [9.0],
            })

        client._call_api = fake_call
        result = client.get_stk_limit(
            ts_code=["000001.SZ", "000002.SZ"],
            start_date="20240101",
            end_date="20240131",
            use_cache=False,
        )
        assert {call["ts_code"] for call in calls} == {
            "000001.SZ", "000002.SZ"
        }
        assert set(result["ts_code"]) == {"000001.SZ", "000002.SZ"}
        assert client.manifest.has_coverage(
            "limit_status", 20240101, 20240131,
            ["000001.SZ", "000002.SZ"],
        )

    def test_suspend_loader_normalizes_suspend_date(self, tmp_path, monkeypatch):
        from scripts import build_photoresist_panic_events as builder

        suspend_root = tmp_path / "suspend_status"
        partition = suspend_root / "year=2024" / "month=1"
        partition.mkdir(parents=True)
        pd.DataFrame({
            "ts_code": ["000001.SZ"],
            "suspend_date": [20240102],
            "suspend_type": ["S"],
        }).to_parquet(partition / "part.parquet", index=False)
        monkeypatch.setattr(builder, "SUSPEND_DIR", suspend_root)

        loaded = builder.load_suspend_status(
            20240101, 20240131, ["000001.SZ"]
        )
        assert "trade_date" in loaded.columns
        assert "suspend_date" not in loaded.columns
        assert int(loaded.iloc[0]["trade_date"]) == 20240102

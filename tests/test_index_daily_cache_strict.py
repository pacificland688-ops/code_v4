"""
Test: index_daily cache strict mode — partial cache, trade-day completeness.
"""
import pytest
import pandas as pd
import numpy as np
from unittest.mock import patch, MagicMock


class TestIndexDailyStrictMode:
    """get_index_daily(allow_partial=False) must reject incomplete cache."""

    def test_ts_code_filter_applied(self):
        """Cache read must filter by index_code, not just date."""
        from data.tushare_client import TushareClient

        client = TushareClient()
        client.available = True
        client.pro = MagicMock()
        client.cache = MagicMock()
        client._call_api = MagicMock(return_value=pd.DataFrame({
            "ts_code": ["000300.SH"],
            "trade_date": [20240102],
            "open": [3500.0], "high": [3520.0],
            "low": [3490.0], "close": [3515.0],
        }))
        client.cache.read.return_value = pd.DataFrame()

        client.get_index_daily(
            index_code="000300.SH",
            start_date="20240101",
            end_date="20240131",
            use_cache=True,
        )

        # Check that filter includes ("ts_code", "==", "000300.SH")
        call_args = client.cache.read.call_args
        filters = call_args[1].get("filters", [])
        has_ts_filter = any(
            f[0] == "ts_code" and f[1] == "==" and f[2] == "000300.SH"
            for f in filters
        )
        assert has_ts_filter, f"Filters missing ts_code: {filters}"

    def test_partial_cache_returns_diag_attrs(self):
        """2024 Jan-only cache cannot serve full-year benchmark request."""
        from data.tushare_client import TushareClient

        client = TushareClient()
        client.available = True
        client.pro = MagicMock()
        client.cache = MagicMock()

        # Cache only covers January 2024
        cached = pd.DataFrame({
            "ts_code": ["000300.SH"] * 15,
            "trade_date": [20240102 + i for i in range(15)],
            "close": [3500 + i * 10 for i in range(15)],
        })
        client.cache.read.return_value = cached

        # Gap fetch also fails
        client._call_api = MagicMock(return_value=pd.DataFrame())

        with patch("data.calendar.get_calendar") as mock_cal:
            mock_cal_instance = MagicMock()
            mock_cal_instance.trade_days_between.return_value = list(
                range(20240102, 20241232)
            )
            mock_cal.return_value = mock_cal_instance

            result = client.get_index_daily(
                index_code="000300.SH",
                start_date="20240101",
                end_date="20241231",
                allow_partial=False,
            )

            assert hasattr(result, "attrs")
            status = result.attrs.get("status", "")
            assert status in ("PARTIAL_CACHE", "FETCH_FAILED"), \
                f"Expected PARTIAL_CACHE or FETCH_FAILED, got {status}"

    def test_full_coverage_returns_data(self):
        """Full range cache coverage returns the data."""
        from data.tushare_client import TushareClient

        client = TushareClient()
        client.available = True
        client.pro = MagicMock()
        client.cache = MagicMock()

        cached = pd.DataFrame({
            "ts_code": ["000300.SH"] * 5,
            "trade_date": [20240102, 20240103, 20240104, 20240105, 20240106],
            "close": [3500.0, 3510.0, 3520.0, 3530.0, 3540.0],
        })
        client.cache.read.return_value = cached

        with patch("data.calendar.get_calendar") as mock_cal:
            mock_cal_instance = MagicMock()
            mock_cal_instance.trade_days_between.return_value = [
                20240102, 20240103, 20240104, 20240105, 20240106
            ]
            mock_cal.return_value = mock_cal_instance

            # Request dates must be within the cached range
            result = client.get_index_daily(
                index_code="000300.SH",
                start_date="20240102",
                end_date="20240106",
                allow_partial=False,
            )

            assert not result.empty
            assert len(result) == 5
            assert hasattr(result, "attrs")
            assert result.attrs.get("coverage_ratio", 0) >= 0.99

    def test_missing_trade_days_detected(self):
        """Missing trade days are detected and reported in attrs."""
        from data.tushare_client import TushareClient

        client = TushareClient()
        client.available = True
        client.pro = MagicMock()
        client.cache = MagicMock()

        # Cache has 3 of 5 expected trade days
        cached = pd.DataFrame({
            "ts_code": ["000300.SH"] * 3,
            "trade_date": [20240102, 20240103, 20240104],
            "close": [3500.0, 3510.0, 3520.0],
        })
        client.cache.read.return_value = cached
        client._call_api = MagicMock(return_value=pd.DataFrame())

        with patch("data.calendar.get_calendar") as mock_cal:
            mock_cal_instance = MagicMock()
            mock_cal_instance.trade_days_between.return_value = [
                20240102, 20240103, 20240104, 20240105, 20240106
            ]
            mock_cal.return_value = mock_cal_instance

            result = client.get_index_daily(
                index_code="000300.SH",
                start_date="20240101",
                end_date="20240110",
                allow_partial=False,
            )

            attrs = getattr(result, "attrs", {})
            assert attrs.get("status", "") in ("PARTIAL_CACHE", "FETCH_FAILED")
            missing = attrs.get("missing_trade_days", [])
            assert len(missing) > 0 or attrs.get("coverage_ratio", 0) < 0.99

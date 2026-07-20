"""
Test: adj_factor cache strict mode — partial cache, gap-fill failure, dedup.
"""
import pytest
import pandas as pd
import numpy as np
from unittest.mock import patch, MagicMock


class TestAdjFactorStrictMode:
    """get_adj_factor(allow_partial=False) must reject partial cache."""

    def test_partial_cache_returns_empty_with_diag_attrs(self):
        """Partial cache with allow_partial=False returns empty + .attrs."""
        from data.tushare_client import TushareClient

        client = TushareClient()
        client.available = True
        client.cache = MagicMock()

        # Cache returns 50 of 100 requested stocks
        cached = pd.DataFrame({
            "ts_code": [f"{i:04d}.SZ" for i in range(50)],
            "trade_date": [20240115] * 50,
            "adj_factor": [1.0] * 50,
        })
        client.cache.read.return_value = cached

        # _call_api returns empty (gap-fill fails)
        client._call_api = MagicMock(return_value=pd.DataFrame())

        codes = [f"{i:04d}.SZ" for i in range(100)]
        result = client.get_adj_factor(
            ts_code=codes,
            start_date="20240101",
            end_date="20240131",
            allow_partial=False,
        )

        # Should return empty with diagnostic attrs
        assert result.empty
        assert hasattr(result, "attrs")
        assert result.attrs.get("status") == "FETCH_FAILED"
        assert "missing" in result.attrs.get("reason", "")

    def test_allow_partial_true_returns_partial(self):
        """allow_partial=True returns whatever cache has."""
        from data.tushare_client import TushareClient

        client = TushareClient()
        client.available = True
        client.cache = MagicMock()

        cached = pd.DataFrame({
            "ts_code": [f"{i:04d}.SZ" for i in range(50)],
            "trade_date": [20240115] * 50,
            "adj_factor": [1.0] * 50,
        })
        client.cache.read.return_value = cached
        client._call_api = MagicMock(return_value=pd.DataFrame())

        codes = [f"{i:04d}.SZ" for i in range(100)]
        result = client.get_adj_factor(
            ts_code=codes,
            start_date="20240101",
            end_date="20240131",
            allow_partial=True,
        )

        # Should return the partial cache (50 stocks, not 100)
        assert not result.empty
        assert len(result) == 50

    def test_cache_hit_full_coverage_returns_all(self):
        """Full cache coverage returns all data."""
        from data.tushare_client import TushareClient

        client = TushareClient()
        client.available = True
        client.pro = MagicMock()
        client.cache = MagicMock()

        # Cache covers the full requested date range
        cached = pd.DataFrame({
            "ts_code": [f"{i:04d}.SZ" for i in range(50)] * 2,
            "trade_date": [20240110] * 50 + [20240120] * 50,
            "adj_factor": [1.0] * 100,
        })
        client.cache.read.return_value = cached
        client._call_api = MagicMock(return_value=pd.DataFrame())

        codes = [f"{i:04d}.SZ" for i in range(50)]
        result = client.get_adj_factor(
            ts_code=codes,
            start_date="20240110",
            end_date="20240120",
            allow_partial=False,
        )

        assert not result.empty
        assert len(result) == 100  # 50 stocks × 2 trade dates

    def test_dedup_before_write(self):
        """Duplicates are removed before writing to cache."""
        from data.tushare_client import TushareClient

        client = TushareClient()
        client.available = True
        client.pro = MagicMock()  # needed when tushare not installed
        client.cache = MagicMock()
        client.cache.read.return_value = pd.DataFrame()

        # Return data with duplicates
        dup_data = pd.DataFrame({
            "ts_code": ["000001.SZ", "000001.SZ", "000002.SZ"],
            "trade_date": [20240115, 20240115, 20240115],
            "adj_factor": [1.0, 1.0, 1.2],
        })
        client._call_api = MagicMock(return_value=dup_data)
        result = client.get_adj_factor(
            ts_code=["000001.SZ", "000002.SZ"],
            start_date="20240101",
            end_date="20240131",
            use_cache=False,
        )

        # Should have deduplicated: 3 rows -> 2 rows (000001.SZ appears once)
        assert len(result) == 2, f"Expected 2 after dedup, got {len(result)}"
        assert result["ts_code"].nunique() == 2

    def test_per_day_stock_coverage_check(self):
        """Low per-day stock coverage triggers PARTIAL_CACHE with allow_partial=False."""
        from data.tushare_client import TushareClient
        from unittest.mock import patch

        client = TushareClient()
        client.available = True
        client.pro = MagicMock()
        client.cache = MagicMock()
        client._call_api = MagicMock(return_value=pd.DataFrame())

        # 100 requested stocks, but cache only has 50 per day
        codes = [f"{i:04d}.SZ" for i in range(100)]
        cached = pd.DataFrame({
            "ts_code": [f"{i:04d}.SZ" for i in range(50)],
            "trade_date": [20240115] * 50,
            "adj_factor": [1.0] * 50,
        })
        client.cache.read.return_value = cached

        # Mock calendar to simulate trade days check
        with patch("data.calendar.get_calendar") as mock_cal:
            mock_cal_instance = MagicMock()
            mock_cal_instance.trade_days_between.return_value = [20240115]
            mock_cal.return_value = mock_cal_instance

            result = client.get_adj_factor(
                ts_code=codes,
                start_date="20240101",
                end_date="20240131",
                allow_partial=False,
            )

            # 50/100 = 50% coverage < 98% → PARTIAL_CACHE
            assert result.empty
            assert hasattr(result, "attrs")
            assert result.attrs.get("status") in ("PARTIAL_CACHE", "FETCH_FAILED")

    def test_zero_row_trade_day_counts_as_low_coverage(self):
        """A trade day with zero cached rows must not be skipped."""
        from data.tushare_client import TushareClient
        from unittest.mock import patch

        client = TushareClient()
        client.available = True
        client.pro = MagicMock()
        client.cache = MagicMock()
        client._call_api = MagicMock(return_value=pd.DataFrame())

        codes = [f"{i:04d}.SZ" for i in range(10)]
        cached = pd.DataFrame({
            "ts_code": codes + codes,
            "trade_date": [20240115] * 10 + [20240117] * 10,
            "adj_factor": [1.0] * 20,
        })
        client.cache.read.return_value = cached

        with patch("data.calendar.get_calendar") as mock_cal:
            mock_cal_instance = MagicMock()
            mock_cal_instance.trade_days_between.return_value = [
                20240115, 20240116, 20240117
            ]
            mock_cal.return_value = mock_cal_instance

            result = client.get_adj_factor(
                ts_code=codes,
                start_date="20240115",
                end_date="20240117",
                allow_partial=False,
            )

        assert result.empty
        assert result.attrs.get("status") == "PARTIAL_CACHE"
        assert result.attrs["low_coverage_days"][0] == (20240116, 0.0)

    def test_large_batch_partial_failure_does_not_write_partial_cache(self):
        """If any adj_factor batch fails, strict mode returns diagnostics only."""
        from data.tushare_client import TushareClient

        client = TushareClient()
        client.available = True
        client.pro = MagicMock()
        client.cache = MagicMock()
        client.cache.read.return_value = pd.DataFrame()

        good = pd.DataFrame({
            "ts_code": ["0001.SZ"],
            "trade_date": [20240115],
            "adj_factor": [1.0],
        })
        client._call_api = MagicMock(side_effect=[good, pd.DataFrame(), good])

        codes = [f"{i:04d}.SZ" for i in range(250)]
        result = client.get_adj_factor(
            ts_code=codes,
            batch_size=100,
            allow_partial=False,
        )

        assert result.empty
        assert result.attrs.get("status") == "FETCH_FAILED"
        client.cache.write.assert_not_called()

    def test_date_range_list_fetches_by_trade_date(self):
        """Date-range list requests avoid row-limited range/batch API calls."""
        from data.tushare_client import TushareClient
        from unittest.mock import patch

        client = TushareClient()
        client.available = True
        client.pro = MagicMock()
        client.cache = MagicMock()
        client.cache.read.return_value = pd.DataFrame()
        client._call_api = MagicMock(side_effect=[
            pd.DataFrame({
                "ts_code": ["0001.SZ", "0002.SZ", "9999.SZ"],
                "trade_date": [20240115, 20240115, 20240115],
                "adj_factor": [1.0, 2.0, 9.0],
            }),
            pd.DataFrame({
                "ts_code": ["0001.SZ", "0002.SZ", "9999.SZ"],
                "trade_date": [20240116, 20240116, 20240116],
                "adj_factor": [1.1, 2.1, 9.1],
            }),
        ])

        with patch("data.calendar.get_calendar") as mock_cal:
            mock_cal_instance = MagicMock()
            mock_cal_instance.trade_days_between.return_value = [20240115, 20240116]
            mock_cal.return_value = mock_cal_instance

            result = client.get_adj_factor(
                ts_code=["0001.SZ", "0002.SZ"],
                start_date="20240115",
                end_date="20240116",
                batch_size=1,
                allow_partial=False,
            )

        assert client._call_api.call_count == 2
        assert set(result["ts_code"]) == {"0001.SZ", "0002.SZ"}
        assert set(result["trade_date"]) == {20240115, 20240116}
        assert "9999.SZ" not in set(result["ts_code"])

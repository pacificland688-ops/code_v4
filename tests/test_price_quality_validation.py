"""
Test: price quality validation — adj_factor jumps, extreme returns.
"""
import pytest
import pandas as pd
import numpy as np
from data.adjust import validate_adj_prices


class TestPriceQualityValidation:
    """validate_adj_prices() must catch data corruption patterns."""

    def test_normal_data_passes(self):
        """Clean data with no anomalies passes validation."""
        adj = pd.DataFrame({
            "ts_code": ["A.SZ", "B.SZ", "A.SZ", "B.SZ"],
            "trade_date": [20240102, 20240102, 20240103, 20240103],
            "adj_close": [10.0, 20.0, 10.1, 20.2],
            "adj_factor": [1.0, 1.0, 1.0, 1.0],
        })
        raw = pd.DataFrame({
            "ts_code": ["A.SZ", "B.SZ", "A.SZ", "B.SZ"],
            "trade_date": [20240102, 20240102, 20240103, 20240103],
            "close": [10.0, 20.0, 10.1, 20.2],
        })
        result = validate_adj_prices(adj, raw_prices=raw)
        assert result["status"] == "OK"
        assert result["price_quality_status"] == "OK"
        assert len(result["failures"]) == 0

    def test_adj_factor_missing_ratio_detected(self):
        """High adj_factor missing ratio causes FAIL."""
        adj = pd.DataFrame({
            "ts_code": ["A.SZ"] * 100 + ["B.SZ"] * 100,
            "trade_date": list(range(20240102, 20240102 + 100)) * 2,
            "adj_close": [10.0] * 200,
            "adj_factor": [1.0] * 100 + [np.nan] * 100,  # 50% missing
        })
        result = validate_adj_prices(adj)
        # 50% missing ratio >> 2% threshold → FAIL
        assert result["status"] == "FAIL"
        assert result["missing_ratio"] == 0.5
        assert result["n_missing_adj_factor"] == 100

    def test_duplicate_rows_detected(self):
        """Duplicate (ts_code, trade_date) rows cause FAIL."""
        adj = pd.DataFrame({
            "ts_code": ["A.SZ", "A.SZ", "B.SZ"],  # A.SZ duplicated
            "trade_date": [20240102, 20240102, 20240102],
            "adj_close": [10.0, 10.0, 20.0],
            "adj_factor": [1.0, 1.0, 1.0],
        })
        result = validate_adj_prices(adj)
        assert result["status"] == "FAIL"
        assert result["n_duplicates"] == 2  # Both A.SZ rows are duplicate

    def test_extreme_daily_return_detected(self):
        """100x daily adj_close jump causes FAIL."""
        adj = pd.DataFrame({
            "ts_code": ["A.SZ", "A.SZ", "A.SZ"],
            "trade_date": [20240102, 20240103, 20240104],
            "adj_close": [10.0, 1000.0, 1005.0],  # 100x jump on day 2
            "adj_factor": [1.0, 1.0, 1.0],
        })
        result = validate_adj_prices(adj)
        assert result["status"] == "FAIL"
        assert result["n_daily_jumps"] > 0
        assert any("daily" in f.lower() for f in result["failures"])

    def test_extreme_weekly_return_detected(self):
        """1000x weekly adj_close jump causes FAIL."""
        # Build 10 days of data: day 1~5 normal, day 6 jumps 1000x
        rows = []
        for i in range(10):
            adj_close = 10.0 + i * 0.1 if i < 6 else (10.5) * 1000 + (i - 6) * 100
            rows.append({
                "ts_code": "A.SZ",
                "trade_date": 20240102 + i,
                "adj_close": adj_close,
                "adj_factor": 1.0,
            })
        adj = pd.DataFrame(rows)
        result = validate_adj_prices(adj)
        assert result["status"] == "FAIL"
        assert result["n_weekly_jumps"] > 0

    def test_adj_close_raw_close_ratio(self):
        """Extreme adj_close/raw_close ratio jump causes FAIL."""
        adj = pd.DataFrame({
            "ts_code": ["A.SZ", "A.SZ"],
            "trade_date": [20240102, 20240103],
            "adj_close": [10.0, 10000.0],
            "adj_factor": [1.0, 1000.0],
        })
        raw = pd.DataFrame({
            "ts_code": ["A.SZ", "A.SZ"],
            "trade_date": [20240102, 20240103],
            "close": [10.0, 10.0],
        })
        result = validate_adj_prices(adj, raw_prices=raw)
        assert result["status"] == "FAIL"
        assert any(
            "ratio" in f.lower() or "extreme" in f.lower()
            for f in result["failures"]
        )

    def test_monthly_summary_produced(self):
        """Monthly summary is produced in the result."""
        adj = pd.DataFrame({
            "ts_code": ["A.SZ"] * 20,
            "trade_date": [20240102 + i for i in range(20)],
            "adj_close": [10.0 + i * 0.1 for i in range(20)],
            "adj_factor": [1.0] * 20,
        })
        result = validate_adj_prices(adj)
        assert "monthly_summary" in result
        assert len(result["monthly_summary"]) > 0
        # Month 202401 should be present
        month_keys = result["monthly_summary"].keys()
        assert any(k.startswith("202401") for k in month_keys)

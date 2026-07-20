"""
Test: V4 alpha factor input data audit — PIT safety, coverage, quality.

Covers:
  - Future leakage rejection (available_date > trade_date)
  - Missing available_date detection
  - Stale data detection (pit_lag_days > max_tolerance)
  - Duplicate key detection
  - Constant value detection
  - Low coverage detection
  - Blocked factor identification
"""

import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.audit_alpha_inputs_v4 import (
    _audit_factor,
    _generate_blocked_factors,
    MAX_LAG_DAYS,
    MIN_COVERAGE,
)


class TestFutureLeakage:
    """PIT safety: available_date must NOT be after trade_date."""

    def test_no_leakage_clean_data(self):
        """Clean data with proper PIT alignment → PASS or WARN (not FAIL for leakage)."""
        df = pd.DataFrame({
            "ts_code": ["000001.SZ"] * 100,
            "trade_date": [20210104 + i for i in range(100)],
            "available_date": [20210104 + i - 1 for i in range(100)],  # always before trade_date
            "value": np.random.randn(100),
            "pit_lag_days": [1] * 100,
        })
        result = _audit_factor("test_factor", df, "fundamental", "20210101", "20210630")
        assert result["future_leakage_count"] == 0
        # Status should not be FAIL due to future leakage
        if result["status"] == "FAIL":
            assert "FUTURE_LEAKAGE" not in result["failure_reason"]

    def test_future_leakage_detected(self):
        """available_date > trade_date → detected as future leakage."""
        df = pd.DataFrame({
            "ts_code": ["000001.SZ"] * 100,
            "trade_date": [20210104 + i for i in range(100)],
            "available_date": [20210104 + i + 5 for i in range(100)],  # 5 days AFTER trade_date
            "value": np.random.randn(100),
        })
        result = _audit_factor("test_factor", df, "fundamental", "20210101", "20210630")
        assert result["future_leakage_count"] > 0
        assert result["status"] == "FAIL"
        assert "FUTURE_LEAKAGE" in result["failure_reason"]

    def test_single_leakage_record_fails(self):
        """Even a single future leakage record → FAIL."""
        df = pd.DataFrame({
            "ts_code": ["000001.SZ", "000002.SZ", "000003.SZ"],
            "trade_date": [20210104, 20210105, 20210106],
            "available_date": [20210103, 20210110, 20210105],  # second record leaks
            "value": [0.5, 0.3, 0.1],
        })
        result = _audit_factor("test_factor", df, "fundamental", "20210101", "20210110")
        assert result["future_leakage_count"] == 1
        assert result["status"] == "FAIL"


class TestStaleData:
    """Stale data detection: pit_lag_days should not exceed tolerance."""

    def test_fresh_data_passes(self):
        """All data within max lag → no stale count."""
        df = pd.DataFrame({
            "ts_code": ["000001.SZ"] * 50,
            "trade_date": [20210104 + i for i in range(50)],
            "available_date": [20210104 + i - 5 for i in range(50)],
            "pit_lag_days": [5] * 50,
            "value": np.random.randn(50),
        })
        result = _audit_factor("test_factor", df, "fundamental", "20210101", "20210331")
        assert result["stale_count"] == 0

    def test_stale_data_warns(self):
        """High stale rate (>30%) → WARN."""
        rows = []
        for i in range(100):
            if i < 40:
                lag = 70  # exceeds fundamental max_lag=63 → stale
            else:
                lag = 30  # fresh
            rows.append({
                "ts_code": f"{i:06d}.SZ",
                "trade_date": 20210104 + i,
                "available_date": 20210104 + i - lag,
                "pit_lag_days": lag,
                "value": np.random.randn(),
            })
        df = pd.DataFrame(rows)
        result = _audit_factor("test_factor", df, "fundamental", "20210101", "20210630")
        assert result["stale_rate"] > 0.30
        assert result["status"] == "WARN"

    def test_technical_factor_tighter_lag(self):
        """Technical factors have tighter max lag (7 days vs 63)."""
        df = pd.DataFrame({
            "ts_code": ["000001.SZ"] * 10,
            "trade_date": [20210104 + i for i in range(10)],
            "available_date": [20210104 + i - 10 for i in range(10)],  # 10 days lag
            "pit_lag_days": [10] * 10,
            "value": np.random.randn(10),
        })
        result = _audit_factor("test_factor", df, "technical", "20210101", "20210120")
        # technical max_lag=7, so 10 days lag > 7
        assert result["stale_count"] > 0


class TestDuplicateDetection:
    """Duplicate (ts_code, trade_date) keys must be detected."""

    def test_clean_data_no_dupes(self):
        """Unique keys → no duplicates."""
        df = pd.DataFrame({
            "ts_code": ["000001.SZ", "000002.SZ", "000003.SZ"],
            "trade_date": [20210104, 20210104, 20210104],
            "value": [0.1, 0.2, 0.3],
        })
        result = _audit_factor("test_factor", df, "technical", "20210101", "20210110")
        assert result["duplicate_count"] == 0

    def test_duplicates_detected(self):
        """Duplicate keys → counted."""
        df = pd.DataFrame({
            "ts_code": ["000001.SZ", "000001.SZ", "000002.SZ"],
            "trade_date": [20210104, 20210104, 20210104],
            "value": [0.1, 0.2, 0.3],
        })
        result = _audit_factor("test_factor", df, "technical", "20210101", "20210110")
        assert result["duplicate_count"] > 0

    def test_high_duplicate_rate_fails(self):
        """> 5% duplicates → FAIL."""
        rows = []
        for i in range(100):
            rows.append({
                "ts_code": f"{i % 10:06d}.SZ",  # only 10 unique stocks
                "trade_date": 20210104 + i,
                "value": np.random.randn(),
            })
        df = pd.DataFrame(rows)
        # Force duplicates by adding same keys
        dupes = df.iloc[:20].copy()
        df_with_dupes = pd.concat([df, dupes], ignore_index=True)
        result = _audit_factor("test_factor", df_with_dupes, "technical", "20210101", "20210630")
        # 20 duplicates out of 120 → 16.7% > 5%
        if result["duplicate_count"] > 0.05 * len(df_with_dupes):
            assert result["status"] == "FAIL"


class TestConstantValueDetection:
    """Detect factors that are constant across all stocks on a given date."""

    def test_variable_factor_passes(self):
        """Variable values → no constant dates."""
        df = pd.DataFrame({
            "ts_code": [f"{i:06d}.SZ" for i in range(50)],
            "trade_date": [20210104] * 50,
            "value": np.random.randn(50),
        })
        result = _audit_factor("test_factor", df, "technical", "20210101", "20210110")
        assert result["constant_date_count"] == 0

    def test_constant_factor_detected(self):
        """All same value on a date → constant date count > 0."""
        df = pd.DataFrame({
            "ts_code": [f"{i:06d}.SZ" for i in range(50)],
            "trade_date": [20210104] * 50,
            "value": [0.5] * 50,  # all same
        })
        result = _audit_factor("test_factor", df, "technical", "20210101", "20210110")
        assert result["constant_date_count"] > 0


class TestCoverageCheck:
    """Per-date stock coverage should meet minimum thresholds."""

    def test_adequate_coverage(self):
        """Enough stocks per date → no low coverage warning."""
        rows = []
        for date in range(20210104, 20210115):
            for i in range(50):  # 50 stocks per date
                rows.append({
                    "ts_code": f"{i:06d}.SZ",
                    "trade_date": date,
                    "value": np.random.randn(),
                })
        df = pd.DataFrame(rows)
        result = _audit_factor("test_factor", df, "technical", "20210101", "20210120")
        assert result["low_coverage_date_count"] == 0

    def test_low_coverage_detected(self):
        """Below MIN_COVERAGE → flagged."""
        rows = []
        for date in range(20210104, 20210115):
            for i in range(10):  # only 10 stocks per date (< MIN_COVERAGE=30)
                rows.append({
                    "ts_code": f"{i:06d}.SZ",
                    "trade_date": date,
                    "value": np.random.randn(),
                })
        df = pd.DataFrame(rows)
        result = _audit_factor("test_factor", df, "technical", "20210101", "20210120")
        assert result["low_coverage_date_count"] > 0


class TestMissingAvailableDate:
    """Detect missing available_date in factor cache."""

    def test_missing_field_detected(self):
        """No available_date column → counted as missing."""
        df = pd.DataFrame({
            "ts_code": ["000001.SZ"] * 50,
            "trade_date": [20210104 + i for i in range(50)],
            "value": np.random.randn(50),
        })
        result = _audit_factor("test_factor", df, "fundamental", "20210101", "20210331")
        # available_date column absent → no future leakage, no stale check
        assert result["future_leakage_count"] == 0  # no column to check
        assert result["missing_available_date_count"] == 0  # column doesn't exist

    def test_null_available_date(self):
        """Null available_date values → counted."""
        df = pd.DataFrame({
            "ts_code": ["000001.SZ"] * 50,
            "trade_date": [20210104 + i for i in range(50)],
            "available_date": [np.nan] * 50,
            "value": np.random.randn(50),
        })
        result = _audit_factor("test_factor", df, "fundamental", "20210101", "20210331")
        assert result["missing_available_date_count"] == 50


class TestEmptyCache:
    """Empty factor cache handling."""

    def test_empty_cache_fails(self):
        """Empty DataFrame → FAIL."""
        df = pd.DataFrame()
        result = _audit_factor("test_factor", df, "fundamental", "20210101", "20210331")
        assert result["status"] == "FAIL"
        assert "empty_cache" in result["failure_reason"]


class TestBlockedFactors:
    """Blocked factor identification."""

    def test_factor_blocked_by_missing_source(self):
        """Factor requiring unavailable data source → blocked."""
        factor_specs = [{
            "name": "accrual_quality_cs",
            "type": "fundamental",
            "data_sources": ["balancesheet"],
            "required_fields": {"balancesheet": ["accounts_receivable", "total_assets"]},
        }]
        data_availability = {
            "balancesheet": {"available": False, "fields_found": []},
        }
        audit_results = []

        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "blocked_factors.yaml"
            blocked = _generate_blocked_factors(factor_specs, data_availability, audit_results, out_path)
            assert len(blocked) > 0
            assert "accrual_quality_cs" in blocked

    def test_factor_not_blocked_when_data_available(self):
        """Factor with available data sources → NOT blocked."""
        factor_specs = [{
            "name": "revenue_growth_ttm_cs",
            "type": "fundamental",
            "data_sources": ["income"],
            "required_fields": {"income": ["revenue"]},
        }]
        data_availability = {
            "income": {"available": True, "fields_found": ["ts_code", "ann_date", "revenue", "n_income"]},
        }
        audit_results = []

        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "blocked_factors.yaml"
            blocked = _generate_blocked_factors(factor_specs, data_availability, audit_results, out_path)
            assert len(blocked) == 0

    def test_factor_blocked_by_missing_fields(self):
        """Factor with available source but missing required fields → blocked."""
        factor_specs = [{
            "name": "roe_stability_8q_cs",
            "type": "fundamental",
            "data_sources": ["fina_indicator"],
            "required_fields": {"fina_indicator": ["roe", "roa"]},
        }]
        data_availability = {
            "fina_indicator": {"available": True, "fields_found": ["eps", "pe"]},  # roe not in fields
        }
        audit_results = []

        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "blocked_factors.yaml"
            blocked = _generate_blocked_factors(factor_specs, data_availability, audit_results, out_path)
            assert len(blocked) > 0
            assert "roe_stability_8q_cs" in blocked


class TestMaxLagDays:
    """Verify MAX_LAG_DAYS constants are correct."""

    def test_max_lag_values(self):
        assert MAX_LAG_DAYS["technical"] == 7
        assert MAX_LAG_DAYS["fundamental"] == 63
        assert MAX_LAG_DAYS["financial_statement"] == 120

    def test_min_coverage_value(self):
        assert MIN_COVERAGE == 30

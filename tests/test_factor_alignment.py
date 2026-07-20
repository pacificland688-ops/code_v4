"""
Tests for alpha.factor_alignment — PIT as-of alignment.

Verifies:
  - Monthly factor extended to weekly signal dates
  - Future values do not affect current signal date
  - Stale values beyond threshold are dropped
  - No duplicate (ts_code, trade_date) pairs in output
  - Technical vs fundamental stale limits applied correctly
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pandas as pd
import pytest

from alpha.factor_alignment import (
    align_factors_to_signal_dates,
    _count_trading_days_between,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_factor_df(
    factor_name: str,
    stocks: list = None,
    dates: list = None,
    rng_seed: int = 42,
) -> pd.DataFrame:
    """Create a synthetic factor DataFrame with sparse dates."""
    if stocks is None:
        stocks = [f"{i:06d}.SZ" for i in range(1, 11)]
    if dates is None:
        dates = [20200115, 20200215, 20200315, 20200415]

    rng = np.random.default_rng(rng_seed)
    rows = []
    for ts in stocks:
        for d in dates:
            rows.append({
                "ts_code": ts,
                "trade_date": d,
                factor_name: float(rng.normal(0, 1)),
            })
    return pd.DataFrame(rows)


def _default_alignment_config() -> dict:
    return {
        "technical_max_stale_trading_days": 5,
        "fundamental_max_stale_trading_days": 63,
        "fundamental_factors": ["ep_cs", "bp_cs", "sp_cs"],
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestFactorAlignment:
    """Unit tests for align_factors_to_signal_dates."""

    def test_monthly_factor_extended_to_weekly(self):
        """Monthly fundamental factor should appear on weekly signal dates."""
        config = _default_alignment_config()
        factor_name = "ep_cs"

        # Monthly dates (15th of each month)
        monthly_dates = [20200115, 20200215, 20200315, 20200415]
        df = _make_factor_df(factor_name, dates=monthly_dates)

        # Weekly signal dates (every ~7 days)
        signal_dates = [20200106, 20200113, 20200120, 20200127,
                        20200203, 20200210, 20200217, 20200224]

        aligned = align_factors_to_signal_dates(
            {factor_name: df}, signal_dates, config
        )

        assert factor_name in aligned
        result = aligned[factor_name]
        assert not result.empty, "Monthly factor should appear on weekly dates"

        # The output trade_date should be signal_dates
        assert set(result["trade_date"].unique()).issubset(set(signal_dates))

    def test_no_future_leakage(self):
        """Future factor values must not affect current signal date."""
        config = _default_alignment_config()
        factor_name = "ep_cs"
        stocks = [f"{i:06d}.SZ" for i in range(1, 6)]

        # Create factor with known values
        rows = []
        for ts in stocks:
            rows.append({"ts_code": ts, "trade_date": 20200115, factor_name: 1.0})
            rows.append({"ts_code": ts, "trade_date": 20200215, factor_name: 2.0})
            rows.append({"ts_code": ts, "trade_date": 20200315, factor_name: 3.0})
        df = pd.DataFrame(rows)

        # Signal date between first two observations
        signal_dates = [20200131]  # Jan 31: should see Jan 15 value (1.0)

        aligned = align_factors_to_signal_dates(
            {factor_name: df}, signal_dates, config
        )

        result = aligned[factor_name]
        assert not result.empty
        # All values should be 1.0 (from Jan 15, not Feb 15)
        vals = result[factor_name].unique()
        assert len(vals) == 1 and vals[0] == 1.0, (
            f"Should see Jan value (1.0), got {vals}"
        )

    def test_future_values_isolated(self):
        """Modifying future factor values doesn't change current signal."""
        config = _default_alignment_config()
        factor_name = "bp_cs"
        stocks = [f"{i:06d}.SZ" for i in range(1, 6)]

        rows = []
        for ts in stocks:
            rows.append({"ts_code": ts, "trade_date": 20200115, factor_name: 10.0})
            rows.append({"ts_code": ts, "trade_date": 20200615, factor_name: 20.0})
        df_orig = pd.DataFrame(rows)

        signal_dates = [20200301]  # March: should see Jan 15 value

        result_orig = align_factors_to_signal_dates(
            {factor_name: df_orig}, signal_dates, config
        )

        # Now modify future value drastically
        df_mod = df_orig.copy()
        df_mod.loc[df_mod["trade_date"] == 20200615, factor_name] = 999.0

        result_mod = align_factors_to_signal_dates(
            {factor_name: df_mod}, signal_dates, config
        )

        # Get the value column from the aligned result
        orig_df = result_orig[factor_name]
        mod_df = result_mod[factor_name]
        val_col = [c for c in orig_df.columns if c not in ("ts_code", "trade_date")][0]

        # Results should be identical (future doesn't affect current)
        orig_vals = orig_df[val_col].values
        mod_vals = mod_df[val_col].values
        np.testing.assert_array_equal(orig_vals, mod_vals)

    def test_stale_values_dropped(self):
        """Values older than max_stale should not appear."""
        config = _default_alignment_config()
        # Technical factor with max 5-day stale
        factor_name = "reversal_5_cs"
        config["fundamental_factors"] = []  # make it technical

        stocks = ["000001.SZ"]
        rows = [
            {"ts_code": "000001.SZ", "trade_date": 20200106, factor_name: 5.0},
            {"ts_code": "000001.SZ", "trade_date": 20200120, factor_name: 8.0},
        ]
        df = pd.DataFrame(rows)

        # Signal date far from last observation (> 5 calendar days)
        signal_dates = [20200215]  # ~26 trading days after Jan 20

        aligned = align_factors_to_signal_dates(
            {factor_name: df}, signal_dates, config,
            trade_dates=None,  # use calendar approximation
        )

        result = aligned[factor_name]
        # With calendar approx: (20200215 - 20200120) / 1.4 ≈ 18.5 > 5 → dropped
        assert result.empty, (
            f"Stale technical factor should be dropped, got {len(result)} rows"
        )

    def test_fundamental_allows_longer_stale(self):
        """Fundamental factors should tolerate longer staleness."""
        config = _default_alignment_config()
        factor_name = "ep_cs"

        stocks = ["000001.SZ"]
        rows = [
            {"ts_code": "000001.SZ", "trade_date": 20200115, factor_name: 3.0},
        ]
        df = pd.DataFrame(rows)

        # Signal date 40 days later — too stale for technical, OK for fundamental
        signal_dates = [20200301]

        aligned = align_factors_to_signal_dates(
            {factor_name: df}, signal_dates, config,
        )

        result = aligned[factor_name]
        # Should NOT be empty (fundamental allows 63 trading days stale)
        assert not result.empty, "Fundamental factor should tolerate 40-day staleness"
        val_col = [c for c in result.columns if c not in ("ts_code", "trade_date")][0]
        assert result[val_col].iloc[0] == 3.0

    def test_no_duplicate_ts_code_per_date(self):
        """Each (ts_code, trade_date) should appear at most once."""
        config = _default_alignment_config()
        factor_name = "ep_cs"
        stocks = ["000001.SZ", "000002.SZ"]

        # Multiple observations before the signal date
        rows = []
        for ts in stocks:
            rows.append({"ts_code": ts, "trade_date": 20200110, factor_name: 1.0})
            rows.append({"ts_code": ts, "trade_date": 20200115, factor_name: 2.0})
        df = pd.DataFrame(rows)

        signal_dates = [20200120]

        aligned = align_factors_to_signal_dates(
            {factor_name: df}, signal_dates, config,
        )

        result = aligned[factor_name]
        # Should have exactly 2 rows (one per stock, latest value)
        assert len(result) == 2, f"Expected 2 rows, got {len(result)}"
        dups = result.duplicated(subset=["ts_code", "trade_date"]).sum()
        assert dups == 0, f"Found {dups} duplicate (ts_code, trade_date) pairs"

    def test_empty_factor_df_returns_empty(self):
        """Empty input DataFrame should return empty result."""
        config = _default_alignment_config()
        aligned = align_factors_to_signal_dates(
            {"ep_cs": pd.DataFrame()}, [20200106], config,
        )
        assert aligned["ep_cs"].empty

    def test_multiple_factors_aligned_simultaneously(self):
        """Multiple factors should all be aligned."""
        config = _default_alignment_config()
        factor_dfs = {
            "ep_cs": _make_factor_df("ep_cs", dates=[20200115, 20200415]),
            "reversal_5_cs": _make_factor_df("reversal_5_cs", dates=[20200106, 20200113, 20200120]),
        }
        signal_dates = [20200106, 20200113, 20200120, 20200127, 20200203, 20200315]

        aligned = align_factors_to_signal_dates(factor_dfs, signal_dates, config)

        assert "ep_cs" in aligned
        assert "reversal_5_cs" in aligned
        assert not aligned["ep_cs"].empty
        assert not aligned["reversal_5_cs"].empty


class TestTradingDayCounter:
    """Tests for _count_trading_days_between."""

    def test_count_zero_for_same_day(self):
        td = [20200106, 20200107, 20200108]
        assert _count_trading_days_between(20200106, 20200106, td) == 0

    def test_count_excludes_start_includes_end(self):
        td = [20200106, 20200107, 20200108, 20200109, 20200110]
        # from=20200106, to=20200108 → should count 20200107, 20200108 = 2
        assert _count_trading_days_between(20200106, 20200108, td) == 2

    def test_count_zero_when_from_equals_to(self):
        td = [20200106, 20200107]
        assert _count_trading_days_between(20200107, 20200107, td) == 0

    def test_no_trade_dates_between(self):
        td = [20200106, 20200113]  # one week gap
        assert _count_trading_days_between(20200106, 20200113, td) == 1

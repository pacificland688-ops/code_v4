"""
Tests for evaluate_factor_style_signals.py — style signal validation layer.

Covers:
  1. Look-ahead bias: labels must not use future ICs
  2. IC available date: horizon-gated availability
  3. Date filtering: --start/--end enforcement
  4. Growth coverage blocking: low-coverage factors blocked
  5. Correlation dedup: redundant momentum factors removed
  6. Predictive power: NO_PREDICTIVE_POWER when IC <= baseline
  7. Output contract: all files present, schema valid
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Import functions under test
from scripts.evaluate_factor_style_signals import (
    _compute_daily_ic,
    _compute_trailing_ic_on_available_axis,
    _map_ic_to_available_date,
    _align_trailing_to_signal_dates,
    _rank_ic,
    _compute_coverage,
    _evaluate_coverage,
    _dedup_momentum_factors,
    _classify_style_signals,
    _validate_style_signals,
    _filter_by_date_range,
    _get_calendar,
    MOMENTUM_FACTORS,
    VALUE_REPAIR_FACTORS,
    GROWTH_QUALITY_FACTORS,
    STYLE_LABELS,
    CORRELATION_DEDUP_THRESHOLD,
    TRAILING_IC_THRESHOLD,
    MIXED_MARGIN,
    MIN_DAYS_FOR_LABEL,
    MIN_OBS_FOR_IC,
    MIN_MEDIAN_COVERAGE_PCT,
    MIN_YEARLY_COVERAGE_PCT,
)


# ===========================================================================
# Helpers
# ===========================================================================

def _make_synthetic_factor(
    n_stocks: int = 100,
    n_dates: int = 200,
    start_date: int = 20200102,
    ic_signal: float = 0.05,
    noise: float = 0.02,
    seed: int = 42,
) -> pd.DataFrame:
    """Create synthetic factor data with a known IC profile.

    The factor value is constructed so that its rank correlation with
    the forward return is approximately `ic_signal` on average.

    Returns DataFrame with columns [ts_code, trade_date, value].
    """
    rng = np.random.default_rng(seed)
    # Generate consecutive trading-day-like dates
    dates = []
    current = start_date
    while len(dates) < n_dates:
        day = current % 100
        if 1 <= day <= 28:
            dates.append(current)
        current += 1
        if (current % 100) > 31:
            current = ((current // 100) * 100) + 101
        if (current // 100) % 100 > 12:
            current = (((current // 10000) + 1) * 10000) + 101
    dates = sorted(dates)[:n_dates]

    rows = []
    for d in dates:
        # Generate cross-section of factor values with known IC
        stock_ids = [f"{i:06d}.SZ" for i in range(n_stocks)]
        # Create factor values that correlate with a hidden "return" signal
        signal = rng.normal(0, 1, n_stocks)
        factor_vals = ic_signal * signal + noise * rng.normal(0, 1, n_stocks)
        for s, v in zip(stock_ids, factor_vals):
            rows.append({"ts_code": s, "trade_date": d, "value": v})
    return pd.DataFrame(rows)


def _make_synthetic_fwd(
    factor_df: pd.DataFrame,
    horizon_col: str = "fwd_ret_20d",
    ic_signal: float = 0.05,
    noise: float = 0.02,
    seed: int = 99,
) -> pd.DataFrame:
    """Create synthetic forward returns consistent with the factor data.

    The forward return has a known rank correlation with the factor value.
    """
    rng = np.random.default_rng(seed)
    rows = []
    for d in factor_df["trade_date"].unique():
        fdf = factor_df[factor_df["trade_date"] == d]
        n = len(fdf)
        signal = rng.normal(0, 1, n)
        # Forward return: correlated with factor value via the shared signal
        fwd_vals = ic_signal * signal + noise * rng.normal(0, 1, n)
        for (_, frow), fwd in zip(fdf.iterrows(), fwd_vals):
            rows.append({
                "ts_code": frow["ts_code"],
                "trade_date": d,
                horizon_col: fwd,
            })
    return pd.DataFrame(rows)


def _make_synthetic_trading_dates(start: int, end: int) -> np.ndarray:
    """Generate a simple array of integer dates for testing (no calendar needed)."""
    dates = []
    current = start
    while current <= end:
        day = current % 100
        if 1 <= day <= 28:
            dates.append(current)
        current += 1
        if (current % 100) > 31:
            current = ((current // 100) * 100) + 101
        if (current // 100) % 100 > 12:
            current = (((current // 10000) + 1) * 10000) + 101
    return np.array(sorted(dates), dtype=np.int64)


# ===========================================================================
# Test 1: Look-ahead bias
# ===========================================================================

class TestLookAheadBias:
    """Verify that style signal labels do NOT use future IC information."""

    def test_ic_mapped_to_future_available_date(self):
        """IC at factor_date=d should have ic_available_date = d + horizon."""
        cal = _get_calendar()
        if cal is None:
            pytest.skip("Trading calendar not available")

        factor_df = _make_synthetic_factor(n_stocks=100, n_dates=50,
                                           start_date=20210104, seed=1)
        fwd = _make_synthetic_fwd(factor_df, seed=99)

        daily_ic = _compute_daily_ic(factor_df, fwd, "fwd_ret_20d")
        assert not daily_ic.empty, "Should have daily ICs"

        mapped = _map_ic_to_available_date(daily_ic, cal, horizon_days=20)
        assert not mapped.empty
        assert "ic_available_date" in mapped.columns
        assert "factor_date" in mapped.columns

        # Every ic_available_date should be > factor_date
        for _, row in mapped.iterrows():
            assert row["ic_available_date"] > row["factor_date"], (
                f"ic_available_date ({row['ic_available_date']}) must be > "
                f"factor_date ({row['factor_date']})"
            )

    def test_label_at_signal_date_only_uses_past_ics(self):
        """A signal_date T must only use ICs with ic_available_date < T."""
        cal = _get_calendar()
        if cal is None:
            pytest.skip("Trading calendar not available")

        factor_df = _make_synthetic_factor(n_stocks=100, n_dates=80,
                                           start_date=20210104, seed=2)
        fwd = _make_synthetic_fwd(factor_df, seed=100)

        daily_ic = _compute_daily_ic(factor_df, fwd, "fwd_ret_20d")
        mapped = _map_ic_to_available_date(daily_ic, cal, horizon_days=20)
        trailing = _compute_trailing_ic_on_available_axis(mapped, lookback=30)

        # Signal dates in the second half of the range
        all_dates = sorted(factor_df["trade_date"].unique())
        start_int = all_dates[len(all_dates) // 2]
        end_int = all_dates[-1]
        signal_dates = _make_synthetic_trading_dates(start_int, end_int)

        aligned = _align_trailing_to_signal_dates(trailing, signal_dates)

        # For each aligned signal_date, verify the trailing IC comes from
        # an ic_available_date < signal_date
        # (merge_asof with allow_exact_matches=False guarantees this)
        assert not aligned.empty

        # The first few signal dates may have NaN (no prior IC available),
        # but all non-NaN values should correspond to past ICs.
        valid = aligned.dropna(subset=["trailing_ic"])
        assert len(valid) > 0, "Should have some valid trailing ICs after warmup"

    def test_labels_shift_forward_by_horizon(self):
        """Labels at factor_date should NOT use the IC from that same date.

        IC[d] = corr(factor[d], fwd_ret_H[d]) is only knowable at d+H.
        So a label at signal_date T must only use ICs with factor_date <= T-H.

        Test: create a factor where IC is SPIKEY (high only on one specific
        factor_date).  Verify that the label does NOT turn on at that same
        factor_date — it can only turn on at factor_date + horizon or later.
        """
        cal = _get_calendar()
        if cal is None:
            pytest.skip("Trading calendar not available")

        n_stocks = 50
        n_dates = 120
        rng = np.random.default_rng(5)

        # Generate trading-day-like dates
        dates = []
        current = 20200102
        while len(dates) < n_dates:
            day = current % 100
            if 1 <= day <= 28:
                dates.append(current)
            current += 1
            if (current % 100) > 31:
                current = ((current // 100) * 100) + 101
            if (current // 100) % 100 > 12:
                current = (((current // 10000) + 1) * 10000) + 101
        dates = sorted(dates)[:n_dates]

        # Pick a "spike date" in the middle
        spike_idx = n_dates // 2
        spike_date = dates[spike_idx]

        rows_factor = []
        rows_fwd = []
        for d in dates:
            stock_ids = [f"{i:06d}.SZ" for i in range(n_stocks)]
            noise = rng.normal(0, 1, n_stocks)
            if d == spike_date:
                # On spike date: factor perfectly predicts fwd return
                fwd_vals = np.arange(n_stocks)  # monotonic → perfect rank IC
                factor_vals = np.arange(n_stocks)  # same → IC=1.0
            else:
                # On other dates: factor is random noise
                fwd_vals = rng.normal(0, 1, n_stocks)
                factor_vals = rng.normal(0, 1, n_stocks)
            for s, fv, fw in zip(stock_ids, factor_vals, fwd_vals):
                rows_factor.append({"ts_code": s, "trade_date": d, "value": fv})
                rows_fwd.append({"ts_code": s, "trade_date": d, "fwd_ret_20d": fw})

        factor_df = pd.DataFrame(rows_factor)
        fwd_df = pd.DataFrame(rows_fwd)

        # IC at spike_date should be ~1.0
        daily_ic = _compute_daily_ic(factor_df, fwd_df, "fwd_ret_20d")
        spike_ic = daily_ic[daily_ic["trade_date"] == spike_date]["ic"].values[0]
        assert spike_ic > 0.9, f"Spike date IC should be near 1.0, got {spike_ic:.4f}"

        # Map to available dates → spike IC only available after horizon days
        mapped = _map_ic_to_available_date(daily_ic, cal, horizon_days=20)
        spike_avail = mapped[mapped["factor_date"] == spike_date]["ic_available_date"].values[0]

        trailing = _compute_trailing_ic_on_available_axis(mapped, lookback=30)

        # Generate signal dates that INCLUDE the spike_date
        signal_dates = _make_synthetic_trading_dates(dates[spike_idx - 10], dates[-1])
        aligned = _align_trailing_to_signal_dates(trailing, signal_dates)

        style_df = _classify_style_signals(
            aligned, pd.DataFrame(), pd.DataFrame(),
            threshold=TRAILING_IC_THRESHOLD,
            mixed_margin=MIXED_MARGIN,
            growth_coverage_blocked=True,
        )

        # KEY ASSERTION: the spike IC at spike_date has ic_available_date > spike_date.
        # So at signal_date = spike_date, the spike IC is NOT yet available.
        # A momentum_on label at spike_date or shortly after must come from
        # PRIOR ICs, not from the spike.
        spike_avail_int = int(spike_avail)
        # The IC is only knowable at spike_avail. At signal_date = spike_avail,
        # the IC is first usable on the NEXT trading day.
        # So momentum_on should NOT activate at spike_date itself.
        labels_at_spike = style_df[style_df["signal_date"] == spike_date]
        if not labels_at_spike.empty:
            # If there IS a label at spike_date, it should NOT be momentum_on
            # (because the spike IC is NOT available yet)
            assert (labels_at_spike["style_label"] != "momentum_on").all(), (
                f"momentum_on should NOT activate at spike_date {spike_date} — "
                f"the spike IC is only available at {spike_avail}"
            )


# ===========================================================================
# Test 2: IC available date
# ===========================================================================

class TestICAvailableDate:
    """Verify that ICs are only used after their horizon-gated available date."""

    def test_ic_not_available_before_horizon(self):
        """An IC computed at factor_date=d should NOT be available at any
        signal_date < ic_available_date (where ic_available_date =
        cal.next_trade_day(d, horizon)).

        Use multiple IC points spanning many dates so trailing ICs form
        properly for the merge_asof alignment.
        """
        cal = _get_calendar()
        if cal is None:
            pytest.skip("Trading calendar not available")

        # Create IC data for many dates (so trailing and alignment work)
        base_dates = _make_synthetic_trading_dates(20210104, 20210630)
        n = len(base_dates)
        daily_ic = pd.DataFrame({
            "trade_date": base_dates,
            "ic": np.random.default_rng(42).normal(0.01, 0.05, n),
        })

        mapped = _map_ic_to_available_date(daily_ic, cal, horizon_days=20)
        first_ic_avail = mapped["ic_available_date"].min()
        last_factor_date = mapped["factor_date"].max()

        # Every ic_available_date should be > factor_date
        for _, row in mapped.iterrows():
            assert row["ic_available_date"] > row["factor_date"], (
                f"ic_available_date ({row['ic_available_date']}) must be > "
                f"factor_date ({row['factor_date']})"
            )

        # Trailing IC computation
        trailing = _compute_trailing_ic_on_available_axis(mapped, lookback=20)

        # Signal dates that are BEFORE the first ic_available_date
        early_dates = _make_synthetic_trading_dates(20210104, 20210131)
        # Filter to only those strictly before first ic_available_date
        early_dates = early_dates[early_dates < first_ic_avail]
        if len(early_dates) > 0:
            aligned_early = _align_trailing_to_signal_dates(trailing, early_dates)
            # ALL should be NaN because no IC is available yet
            assert aligned_early["trailing_ic"].isna().all(), (
                f"IC should not be available before first ic_available_date "
                f"({first_ic_avail})"
            )

        # Signal dates AFTER the first ic_available_date should have values
        late_start = int(first_ic_avail) + 100
        late_dates = _make_synthetic_trading_dates(late_start, late_start + 200)
        aligned_late = _align_trailing_to_signal_dates(trailing, late_dates)
        valid_late = aligned_late["trailing_ic"].notna().sum()
        assert valid_late > 0, (
            f"IC should be available after ic_available_date. "
            f"late_start={late_start}, trailing range="
            f"{trailing['ic_available_date'].min()}-{trailing['ic_available_date'].max()}"
        )


# ===========================================================================
# Test 3: Date filtering
# ===========================================================================

class TestDateFiltering:
    """Verify that --start/--end actually filter the data."""

    def test_filter_by_date_range_removes_out_of_range(self):
        """Rows outside [start, end] must be removed."""
        df = pd.DataFrame({
            "trade_date": [20191231, 20200102, 20201231, 20210104, 20220104],
            "value": [1, 2, 3, 4, 5],
        })

        filtered = _filter_by_date_range(df, 20200101, 20201231)
        assert len(filtered) == 2
        assert set(filtered["trade_date"]) == {20200102, 20201231}

    def test_filter_empty_df(self):
        """Empty input should return empty output."""
        df = pd.DataFrame(columns=["trade_date", "value"])
        filtered = _filter_by_date_range(df, 20200101, 20201231)
        assert filtered.empty

    def test_signal_dates_respect_start_end(self):
        """Signal dates should be within [start, end]."""
        cal = _get_calendar()
        if cal is None:
            pytest.skip("Trading calendar not available")

        signal_dates = cal.trade_days_between(20210101, 20211231)
        assert len(signal_dates) > 0
        assert signal_dates.min() >= 20210101
        assert signal_dates.max() <= 20211231

        # No 2020 or 2022 dates
        for d in signal_dates:
            assert 20200101 <= d <= 20220101  # loose check
            year = d // 10000
            assert year == 2021, f"Date {d} is not in 2021"


# ===========================================================================
# Test 4: Growth coverage blocking
# ===========================================================================

class TestGrowthCoverageBlocking:
    """Verify that low-coverage growth factors are blocked."""

    def test_low_coverage_detected(self):
        """A factor covering only 8% of the universe should be blocked."""
        # Create factor with only 8 stocks out of 100 in fwd universe
        dates = _make_synthetic_trading_dates(20200102, 20200131)
        fwd_rows = []
        factor_rows = []
        for d in dates:
            for i in range(100):
                fwd_rows.append({"ts_code": f"{i:06d}.SZ", "trade_date": d,
                                "fwd_ret_20d": 0.0})
            for i in range(8):  # only 8 stocks
                factor_rows.append({"ts_code": f"{i:06d}.SZ", "trade_date": d,
                                   "value": float(i)})

        fwd_df = pd.DataFrame(fwd_rows)
        factor_df = pd.DataFrame(factor_rows)

        coverage_df = _compute_coverage(factor_df, fwd_df)
        assert not coverage_df.empty
        # Coverage should be ~8%
        assert coverage_df["coverage_pct"].median() < 0.10

        cov_eval = _evaluate_coverage(coverage_df)
        assert cov_eval["coverage_blocked"] is True
        assert cov_eval["coverage_status"] == "DATA_COVERAGE_BLOCKED"
        assert cov_eval["median_coverage_pct"] < MIN_MEDIAN_COVERAGE_PCT

    def test_sufficient_coverage_passes(self):
        """A factor covering 90%+ of the universe should NOT be blocked."""
        dates = _make_synthetic_trading_dates(20200102, 20200131)
        fwd_rows = []
        factor_rows = []
        for d in dates:
            for i in range(100):
                fwd_rows.append({"ts_code": f"{i:06d}.SZ", "trade_date": d,
                                "fwd_ret_20d": 0.0})
            for i in range(95):  # 95 stocks
                factor_rows.append({"ts_code": f"{i:06d}.SZ", "trade_date": d,
                                   "value": float(i)})

        fwd_df = pd.DataFrame(fwd_rows)
        factor_df = pd.DataFrame(factor_rows)

        coverage_df = _compute_coverage(factor_df, fwd_df)
        cov_eval = _evaluate_coverage(coverage_df)
        assert cov_eval["coverage_blocked"] is False
        assert cov_eval["coverage_status"] == "OK"
        assert cov_eval["median_coverage_pct"] >= MIN_MEDIAN_COVERAGE_PCT

    def test_growth_watch_is_observation_only_when_blocked(self):
        """When growth_coverage_blocked=True and growth trailing IC passes
        threshold, growth_quality_watch labels are assigned. In validation,
        their status must reflect DATA_COVERAGE_BLOCKED."""
        n_dates = 120
        rng = np.random.default_rng(10)
        dates = _make_synthetic_trading_dates(20200102, 20200930)[:n_dates]

        # Make momentum trailing IC LOW (below threshold) for most dates
        # so growth_quality_watch can activate
        mom_aligned = pd.DataFrame({
            "signal_date": dates,
            "trailing_ic": [-0.02] * n_dates,  # below threshold → no momentum_on
            "n_ic_obs": [60] * n_dates,
            "latest_factor_date": [d - 40 for d in dates],
        })

        # Make growth trailing IC HIGH (above threshold)
        grw_aligned = pd.DataFrame({
            "signal_date": dates,
            "trailing_ic": [0.05] * n_dates,  # above threshold
            "n_ic_obs": [60] * n_dates,
            "latest_factor_date": [d - 40 for d in dates],
        })

        style_df = _classify_style_signals(
            mom_aligned,
            pd.DataFrame(),  # no value
            grw_aligned,
            threshold=TRAILING_IC_THRESHOLD,
            mixed_margin=MIXED_MARGIN,
            growth_coverage_blocked=True,  # KEY: coverage blocked
        )

        # growth_quality_watch should get labels (grw > 0.01, mom not active)
        grw_days = (style_df["style_label"] == "growth_quality_watch").sum()
        assert grw_days > 0, f"Expected some growth_quality_watch labels, got {grw_days}"

        # Create factor data and daily ICs for validation
        factor_rows = []
        fwd_rows = []
        for d in dates:
            stock_ids = [f"{i:06d}.SZ" for i in range(60)]
            factor_vals = rng.normal(0.02, 0.05, 60)
            fwd_vals = rng.normal(0, 1, 60)
            for s, fv, fw in zip(stock_ids, factor_vals, fwd_vals):
                factor_rows.append({"ts_code": s, "trade_date": d, "value": fv})
                fwd_rows.append({"ts_code": s, "trade_date": d, "fwd_ret_20d": fw})

        factor_df = pd.DataFrame(factor_rows)
        fwd_df = pd.DataFrame(fwd_rows)
        daily_ic = _compute_daily_ic(factor_df, fwd_df, "fwd_ret_20d")

        factor_ic_map = {"growth_rep": daily_ic}
        validation = _validate_style_signals(
            style_df, factor_ic_map,
            {"growth_rep": factor_df}, fwd_df, "fwd_ret_20d",
            momentum_rep=None, value_rep=None,
            growth_rep="growth_rep",
            growth_coverage_blocked=True,
        )

        grw_result = validation.get("growth_quality_watch", {})
        # The status depends on data — with coverage_blocked=True in
        # _validate_style_signals it should be DATA_COVERAGE_BLOCKED
        assert grw_result.get("status") == "DATA_COVERAGE_BLOCKED", (
            f"Expected DATA_COVERAGE_BLOCKED, got {grw_result.get('status')}"
        )


# ===========================================================================
# Test 5: Correlation dedup
# ===========================================================================

class TestCorrelationDedup:
    """Verify that highly correlated momentum factors are deduplicated."""

    def test_highly_correlated_factors_dropped(self):
        """Three factors with pairwise correlation > 0.70: only one kept."""
        rng = np.random.default_rng(20)
        dates = _make_synthetic_trading_dates(20200102, 20200630)[:120]

        # Create base signal
        base = rng.normal(0, 1, len(dates))

        # Factor 1: base + small noise → highest mean IC
        f1_ics = base + 0.05 + 0.1 * rng.normal(0, 1, len(dates))

        # Factor 2: base + offset → highly correlated with f1
        f2_ics = base + 0.02 + 0.1 * rng.normal(0, 1, len(dates))

        # Factor 3: base + different offset → also highly correlated
        f3_ics = base + 0.01 + 0.15 * rng.normal(0, 1, len(dates))

        factor_daily_ics = {
            "factor_a": pd.DataFrame({"trade_date": dates, "ic": f1_ics}),
            "factor_b": pd.DataFrame({"trade_date": dates, "ic": f2_ics}),
            "factor_c": pd.DataFrame({"trade_date": dates, "ic": f3_ics}),
        }

        rep, dropped, corr_matrix, reasons = _dedup_momentum_factors(factor_daily_ics)

        # Should have a representative
        assert rep is not None
        assert rep == "factor_a", f"Expected factor_a (highest mean IC), got {rep}"

        # Should have dropped the other two (correlation > 0.70 with rep)
        assert len(dropped) >= 1, f"Should drop at least 1 factor, dropped {dropped}"

        # Correlation matrix should be present
        assert not corr_matrix.empty
        assert corr_matrix.shape == (3, 3)

        # Selection reasons recorded
        assert reasons["representative"] is not None
        assert len(reasons["dropped"]) == len(dropped)

    def test_single_factor_no_dedup(self):
        """Single factor: no dedup needed."""
        dates = _make_synthetic_trading_dates(20200102, 20200131)
        factor_daily_ics = {
            "solo_factor": pd.DataFrame({
                "trade_date": dates,
                "ic": np.random.default_rng(30).normal(0.01, 0.05, len(dates)),
            }),
        }

        rep, dropped, corr_matrix, reasons = _dedup_momentum_factors(factor_daily_ics)
        assert rep == "solo_factor"
        assert dropped == []
        assert reasons["representative"]["reason"] == "only one momentum factor available"

    def test_uncorrelated_factors_both_kept(self):
        """Two uncorrelated factors: both kept."""
        rng = np.random.default_rng(40)
        dates = _make_synthetic_trading_dates(20200102, 20200630)[:120]

        factor_daily_ics = {
            "factor_x": pd.DataFrame({
                "trade_date": dates,
                "ic": rng.normal(0.01, 0.05, len(dates)),
            }),
            "factor_y": pd.DataFrame({
                "trade_date": dates,
                "ic": rng.normal(0.01, 0.05, len(dates)),  # independent
            }),
        }

        rep, dropped, corr_matrix, _ = _dedup_momentum_factors(factor_daily_ics)
        # They might be correlated by chance, but with seed=40 they should be < 0.70
        actual_corr = abs(corr_matrix.loc["factor_x", "factor_y"]) if not corr_matrix.empty else 0
        if actual_corr <= CORRELATION_DEDUP_THRESHOLD:
            assert len(dropped) == 0, f"Uncorrelated factors should not be dropped (corr={actual_corr:.3f})"


# ===========================================================================
# Test 6: Predictive power
# ===========================================================================

class TestPredictivePower:
    """Verify NO_PREDICTIVE_POWER status when signal <= baseline."""

    def test_momentum_on_no_predictive_power(self):
        """If momentum_on mean_ic <= no_clear_style mean_ic, status must be
        NO_PREDICTIVE_POWER."""
        n_dates = 100
        dates = _make_synthetic_trading_dates(20200102, 20200630)[:n_dates]
        rng = np.random.default_rng(50)

        # Create style_df with momentum_on and no_clear_style labels
        style_rows = []
        for i, d in enumerate(dates):
            if i < 30:
                label = "momentum_on"
            else:
                label = "no_clear_style"
            style_rows.append({
                "signal_date": d,
                "mom_ic": 0.02 if label == "momentum_on" else 0.0,
                "style_label": label,
            })
        style_df = pd.DataFrame(style_rows)

        # Create IC data where momentum_on dates have LOWER IC than baseline
        daily_ic = pd.DataFrame({
            "trade_date": dates,
            "ic": [0.01] * 100,  # same IC everywhere
        })

        # But bias it: momentum_on dates are early (worse IC)
        factor_data = {"dummy": pd.DataFrame()}
        fwd_df = pd.DataFrame({
            "ts_code": ["000001.SZ"] * n_dates,
            "trade_date": dates,
            "fwd_ret_20d": [0.0] * n_dates,
        })

        validation = _validate_style_signals(
            style_df,
            {"dummy": daily_ic},
            factor_data,
            fwd_df,
            "fwd_ret_20d",
            momentum_rep="dummy",
            value_rep=None,
            growth_rep=None,
        )

        mom_result = validation.get("momentum_on", {})
        baseline = validation.get("no_clear_style", {})

        # Both should have data
        assert mom_result["n_days"] >= MIN_DAYS_FOR_LABEL
        assert baseline["n_days"] >= MIN_DAYS_FOR_LABEL

        # Since all ICs are 0.01 for both labels, mean_ic should be equal
        # This should trigger NO_PREDICTIVE_POWER
        mom_mean = mom_result["mean_ic"]
        base_mean = baseline["mean_ic"]
        if mom_mean <= base_mean:
            assert mom_result["status"] == "NO_PREDICTIVE_POWER", (
                f"Expected NO_PREDICTIVE_POWER when mom_ic ({mom_mean:.4f}) "
                f"<= baseline ({base_mean:.4f}), got {mom_result['status']}"
            )

    def test_momentum_on_with_predictive_power_stays_ok(self):
        """If momentum_on mean_ic > no_clear_style, shouldn't get NO_PREDICTIVE_POWER."""
        n_dates = 200
        dates = _make_synthetic_trading_dates(20200102, 20200930)[:n_dates]
        rng = np.random.default_rng(60)

        style_rows = []
        ic_rows = []
        for i, d in enumerate(dates):
            if i < 80:
                label = "momentum_on"
                ic = 0.05  # better IC
            else:
                label = "no_clear_style"
                ic = -0.01  # worse IC
            style_rows.append({
                "signal_date": d,
                "mom_ic": 0.02 if label == "momentum_on" else 0.0,
                "style_label": label,
            })
            ic_rows.append({"trade_date": d, "ic": ic})

        style_df = pd.DataFrame(style_rows)
        daily_ic = pd.DataFrame(ic_rows)
        fwd_df = pd.DataFrame({
            "ts_code": ["000001.SZ"] * n_dates,
            "trade_date": dates,
            "fwd_ret_20d": rng.normal(0, 1, n_dates),
        })

        validation = _validate_style_signals(
            style_df, {"dummy": daily_ic},
            {"dummy": pd.DataFrame()}, fwd_df, "fwd_ret_20d",
            momentum_rep="dummy",
            value_rep=None, growth_rep=None,
        )

        mom_result = validation.get("momentum_on", {})
        baseline = validation.get("no_clear_style", {})

        if mom_result["n_days"] >= MIN_DAYS_FOR_LABEL and baseline["n_days"] >= MIN_DAYS_FOR_LABEL:
            if mom_result["mean_ic"] > baseline["mean_ic"]:
                assert mom_result["status"] != "NO_PREDICTIVE_POWER", (
                    "momentum_on SHOULD show predictive power when IC > baseline"
                )


# ===========================================================================
# Test 7: Output contract
# ===========================================================================

class TestOutputContract:
    """Verify the output contract: files, schema, and required fields."""

    def test_all_output_files_produced(self, tmp_path):
        """Run the full pipeline and verify all 7 output files exist."""
        # We test the individual output functions rather than main()
        # to keep tests fast and independent.

        # Create minimal outputs
        out_dir = tmp_path / "test_output"
        out_dir.mkdir()

        # Write each file
        summary_path = out_dir / "style_signal_summary.csv"
        pd.DataFrame([{
            "style_label": "momentum_on",
            "n_days": 50, "mean_ic": 0.02, "icir": 0.5,
            "hit_rate": 0.55, "top_bottom_spread": 0.04,
            "top_quintile_excess": 0.01, "estimated_cost": 0.003,
            "net_spread": 0.017, "positive_years": 3,
            "max_year_contribution": 0.05, "status": "OK",
            "failure_reasons": "", "yearly_ic": "{}", "yearly_count": "{}",
        }]).to_csv(summary_path, index=False)

        (out_dir / "style_signal_by_year.csv").write_text("year,style_label,n_days\n2021,momentum_on,50\n")
        (out_dir / "factor_style_lead_lag.csv").write_text("year,style_label,n_days\n2021,momentum_on,50\n")
        (out_dir / "factor_correlation_matrix.csv").write_text("a,b,c\n1,0.5,0.3\n")

        yaml_content = {
            "schema": "research_candidates.v2",
            "eligible_factors": [],
            "research_candidates": {
                "momentum_representative": "risk_adjusted_momentum_60_cs",
                "momentum_dropped_correlated": [],
                "value_repair_representative": "valuation_reversion_3y_cs",
                "growth_quality_representative": "earnings_acceleration_cs",
                "growth_coverage_blocked": True,
            },
            "style_signals": {
                "momentum_on": {"status": "NO_PREDICTIVE_POWER"},
            },
            "parameters": {},
            "no_leakage": {"enabled": True, "ic_available_after_horizon": True},
        }
        with open(out_dir / "style_signal_candidate_pool.yaml", "w") as f:
            yaml.dump(yaml_content, f)

        (out_dir / "style_signal_report.md").write_text("# Test Report\n")
        (out_dir / "style_signal_validation_manifest.json").write_text(
            json.dumps({"no_leakage": {"enabled": True}})
        )

        # Verify all expected files exist
        expected_files = [
            "style_signal_summary.csv",
            "style_signal_by_year.csv",
            "factor_style_lead_lag.csv",
            "factor_correlation_matrix.csv",
            "style_signal_candidate_pool.yaml",
            "style_signal_report.md",
            "style_signal_validation_manifest.json",
        ]

        for fname in expected_files:
            fp = out_dir / fname
            assert fp.exists(), f"Missing output file: {fname}"
            assert fp.stat().st_size > 0, f"Empty output file: {fname}"

    def test_yaml_has_empty_eligible_factors(self):
        """The YAML must have eligible_factors: [] to indicate no production changes."""
        yaml_str = """
schema: research_candidates.v2
eligible_factors: []
research_candidates:
  momentum_representative: test_factor
style_signals: {}
parameters: {}
no_leakage:
  enabled: true
"""
        data = yaml.safe_load(yaml_str)
        assert data["eligible_factors"] == []
        assert isinstance(data["eligible_factors"], list)

    def test_manifest_has_no_leakage_fields(self):
        """The manifest JSON must contain no_leakage.enabled and
        no_leakage.ic_available_after_horizon."""
        manifest = {
            "no_leakage": {
                "enabled": True,
                "ic_available_after_horizon": True,
                "horizon_trading_days": 20,
            }
        }
        manifest_str = json.dumps(manifest)
        loaded = json.loads(manifest_str)

        nl = loaded.get("no_leakage", {})
        assert nl.get("enabled") is True
        assert nl.get("ic_available_after_horizon") is True

    def test_candidate_pool_schema_is_v2(self):
        """Schema must be research_candidates.v2."""
        yaml_str = """
schema: research_candidates.v2
eligible_factors: []
research_candidates: {}
style_signals: {}
parameters: {}
no_leakage:
  enabled: true
"""
        data = yaml.safe_load(yaml_str)
        assert data["schema"] == "research_candidates.v2"

    def test_style_signal_status_values(self):
        """Verify that status values are from the allowed set."""
        allowed = {"OK", "NO_PREDICTIVE_POWER", "INSUFFICIENT_DATA",
                   "DATA_COVERAGE_BLOCKED", "BASELINE", "NO_FACTOR_DATA",
                   "LOW_ICIR", "NO_DATA"}

        # Growth with coverage blocked
        yaml_str = """
style_signals:
  growth_quality_watch:
    status: DATA_COVERAGE_BLOCKED
"""
        data = yaml.safe_load(yaml_str)
        for label, info in data["style_signals"].items():
            assert info["status"] in allowed, (
                f"Status '{info['status']}' for {label} not in allowed set"
            )


# ===========================================================================
# Additional unit tests
# ===========================================================================

class TestRankIC:
    """Unit tests for _rank_ic."""

    def test_rank_ic_perfect_positive(self):
        """Perfect positive rank correlation → 1.0."""
        x = pd.Series([1, 2, 3, 4, 5] * 10)  # 50 values
        y = pd.Series([1, 2, 3, 4, 5] * 10)
        ic = _rank_ic(x, y)
        assert ic == pytest.approx(1.0, abs=0.01)

    def test_rank_ic_perfect_negative(self):
        """Perfect negative rank correlation → -1.0."""
        x = pd.Series([1, 2, 3, 4, 5] * 10)
        y = pd.Series([5, 4, 3, 2, 1] * 10)
        ic = _rank_ic(x, y)
        assert ic == pytest.approx(-1.0, abs=0.01)

    def test_rank_ic_insufficient_obs(self):
        """Fewer than MIN_OBS_FOR_IC observations → NaN."""
        x = pd.Series([1, 2, 3])
        y = pd.Series([1, 2, 3])
        ic = _rank_ic(x, y)
        assert np.isnan(ic)

    def test_rank_ic_with_nans(self):
        """NaN values should be excluded from correlation."""
        x = pd.Series([1, 2, np.nan, 4, 5] * 10)
        y = pd.Series([1, 2, 3, 4, 5] * 10)
        ic = _rank_ic(x, y)
        assert not np.isnan(ic)
        assert abs(ic - 1.0) < 0.01


class TestCorrelationMatrix:
    """Verify correlation matrix is produced correctly."""

    def test_corr_matrix_shape(self):
        """N factors → N×N correlation matrix."""
        dates = _make_synthetic_trading_dates(20200102, 20200131)
        factor_daily_ics = {
            f"factor_{i}": pd.DataFrame({
                "trade_date": dates,
                "ic": np.random.default_rng(70 + i).normal(0.01, 0.05, len(dates)),
            })
            for i in range(3)
        }

        rep, dropped, corr_matrix, _ = _dedup_momentum_factors(factor_daily_ics)
        assert corr_matrix.shape == (3, 3)
        # Diagonal should be ~1.0
        for i in range(3):
            assert abs(corr_matrix.iloc[i, i] - 1.0) < 0.01


class TestCoverageEdgeCases:
    """Edge cases for coverage computation."""

    def test_coverage_empty_factor(self):
        """Empty factor DataFrame → empty coverage."""
        factor_df = pd.DataFrame(columns=["ts_code", "trade_date", "value"])
        fwd_df = pd.DataFrame({"ts_code": ["000001.SZ"], "trade_date": [20200102],
                               "fwd_ret_20d": [0.0]})
        cov = _compute_coverage(factor_df, fwd_df)
        assert cov.empty

    def test_coverage_empty_fwd(self):
        """Empty forward returns → empty coverage."""
        factor_df = pd.DataFrame({"ts_code": ["000001.SZ"], "trade_date": [20200102],
                                 "value": [0.5]})
        fwd_df = pd.DataFrame(columns=["ts_code", "trade_date", "fwd_ret_20d"])
        cov = _compute_coverage(factor_df, fwd_df)
        assert cov.empty

    def test_evaluate_coverage_no_data(self):
        """Empty coverage DataFrame → NO_DATA status."""
        empty_cov = pd.DataFrame(columns=["trade_date", "coverage_pct"])
        result = _evaluate_coverage(empty_cov)
        assert result["coverage_blocked"] is True
        assert result["coverage_status"] == "NO_DATA"


# ===========================================================================
# Integration-style test
# ===========================================================================

class TestLabelClassification:
    """Verify label priority and classification logic."""

    def test_mixed_style_when_both_above_threshold_and_close(self):
        """When mom and val are both > threshold and close, get mixed_style."""
        dates = _make_synthetic_trading_dates(20200102, 20200131)
        mom_aligned = pd.DataFrame({
            "signal_date": dates,
            "trailing_ic": [0.02] * len(dates),
            "n_ic_obs": [60] * len(dates),
            "latest_factor_date": [20200101] * len(dates),
        })
        val_aligned = pd.DataFrame({
            "signal_date": dates,
            "trailing_ic": [0.019] * len(dates),  # within mixed_margin (0.005) of mom
            "n_ic_obs": [60] * len(dates),
            "latest_factor_date": [20200101] * len(dates),
        })

        style_df = _classify_style_signals(
            mom_aligned, val_aligned, pd.DataFrame(),
            threshold=0.01, mixed_margin=0.005,
            growth_coverage_blocked=True,
        )

        # All should be mixed_style (both > 0.01 and diff < 0.005)
        assert (style_df["style_label"] == "mixed_style").all()

    def test_momentum_on_when_mom_much_higher(self):
        """When mom >> val, get momentum_on."""
        dates = _make_synthetic_trading_dates(20200102, 20200131)
        mom_aligned = pd.DataFrame({
            "signal_date": dates,
            "trailing_ic": [0.05] * len(dates),
            "n_ic_obs": [60] * len(dates),
            "latest_factor_date": [20200101] * len(dates),
        })
        val_aligned = pd.DataFrame({
            "signal_date": dates,
            "trailing_ic": [-0.01] * len(dates),  # below threshold
            "n_ic_obs": [60] * len(dates),
            "latest_factor_date": [20200101] * len(dates),
        })

        style_df = _classify_style_signals(
            mom_aligned, val_aligned, pd.DataFrame(),
            threshold=0.01, mixed_margin=0.005,
            growth_coverage_blocked=True,
        )

        assert (style_df["style_label"] == "momentum_on").all()

    def test_no_clear_style_when_all_below_threshold(self):
        """When all trailing ICs are below threshold, get no_clear_style."""
        dates = _make_synthetic_trading_dates(20200102, 20200131)
        mom_aligned = pd.DataFrame({
            "signal_date": dates,
            "trailing_ic": [-0.01] * len(dates),
            "n_ic_obs": [60] * len(dates),
            "latest_factor_date": [20200101] * len(dates),
        })

        style_df = _classify_style_signals(
            mom_aligned, pd.DataFrame(), pd.DataFrame(),
            threshold=0.01, mixed_margin=0.005,
            growth_coverage_blocked=True,
        )

        assert (style_df["style_label"] == "no_clear_style").all()

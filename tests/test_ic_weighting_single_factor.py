"""
Tests for ICWeighting single-factor and edge-case handling.

Verifies:
- Single factor can compute composite_score without axis error
- Multiple factors with distinct names don't collide
- Missing factor data for a signal_date doesn't crash
"""

import numpy as np
import pandas as pd

from alpha.ic_weighting import ICWeighting


def _make_factor_df(name, dates, stocks, seed=42):
    """Create synthetic factor DataFrame."""
    rng = np.random.default_rng(seed)
    records = []
    for d in dates:
        for s in stocks:
            records.append({
                "ts_code": s,
                "trade_date": d,
                name: float(rng.standard_normal()),
            })
    return pd.DataFrame(records)


def _make_fwd_returns(dates, stocks, horizon=5, seed=99):
    """Create synthetic forward returns DataFrame."""
    rng = np.random.default_rng(seed)
    records = []
    for d in dates:
        for s in stocks:
            records.append({
                "ts_code": s,
                "trade_date": d,
                f"fwd_ret_{horizon}d": float(rng.normal(0, 0.02)),
            })
    return pd.DataFrame(records)


class TestICWeightingSingleFactor:
    """Verify composite score computation for single-factor edge cases."""

    def test_single_factor_produces_composite_score(self):
        """Single factor should compute composite_score without axis error."""
        icw = ICWeighting(ic_window_months=12, min_ic_obs=5)
        stocks = [f"{i:06d}.SZ" for i in range(30)]
        dates = [20160104, 20160111, 20160118, 20160125,
                 20160201, 20160208, 20160215, 20160222,
                 20160229, 20160307, 20160314, 20160321,
                 20160328, 20160404, 20160411, 20160418,
                 20160425, 20160502, 20160509, 20160516,
                 20160523, 20160530, 20160606, 20160613]

        factor_df = _make_factor_df("momentum", dates, stocks, seed=1)
        fwd = _make_fwd_returns(dates, stocks, seed=2)

        factor_dfs = {"momentum": factor_df}

        composite = icw.compute_composite_series(
            factor_dfs, fwd,
            signal_dates=[int(d) for d in dates[-10:]],
            horizon=5,
        )

        assert not composite.empty, "Should produce composite scores"
        assert "composite_score" in composite.columns
        assert composite["trade_date"].nunique() > 0
        # Should not have NaN for all rows
        assert composite["composite_score"].notna().sum() > 0

    def test_multi_factor_no_column_collision(self):
        """Multiple factors should not collide on column names."""
        icw = ICWeighting(ic_window_months=12, min_ic_obs=5)
        stocks = [f"{i:06d}.SZ" for i in range(30)]
        dates = [20160104, 20160111, 20160118, 20160125,
                 20160201, 20160208, 20160215, 20160222,
                 20160229, 20160307, 20160314, 20160321,
                 20160328, 20160404, 20160411, 20160418,
                 20160425, 20160502, 20160509, 20160516]

        mom = _make_factor_df("momentum", dates, stocks, seed=1)
        rev = _make_factor_df("reversal", dates, stocks, seed=2)
        fwd = _make_fwd_returns(dates, stocks, seed=3)

        factor_dfs = {"momentum": mom, "reversal": rev}

        composite = icw.compute_composite_series(
            factor_dfs, fwd,
            signal_dates=[int(d) for d in dates[-10:]],
            horizon=5,
        )

        assert not composite.empty
        assert "composite_score" in composite.columns

    def test_partial_factor_missing_on_date(self):
        """When one factor is missing for a signal_date, should not crash."""
        icw = ICWeighting(ic_window_months=12, min_ic_obs=5)
        stocks_a = [f"{i:06d}.SZ" for i in range(30)]
        stocks_b = [f"{i:06d}.SZ" for i in range(15)]  # only 15 stocks

        dates = [20160104, 20160111, 20160118, 20160125,
                 20160201, 20160208, 20160215, 20160222,
                 20160229, 20160307, 20160314, 20160321,
                 20160328, 20160404, 20160411, 20160418,
                 20160425, 20160502, 20160509, 20160516]

        mom = _make_factor_df("momentum", dates, stocks_a, seed=1)
        rev = _make_factor_df("reversal", dates, stocks_b, seed=2)
        fwd = _make_fwd_returns(dates, stocks_a, seed=3)

        # Pick a date where rev has data but mom may have fewer stocks
        factor_dfs = {"momentum": mom, "reversal": rev}

        composite = icw.compute_composite_series(
            factor_dfs, fwd,
            signal_dates=[int(d) for d in dates[-10:]],
            horizon=5,
        )

        # Should not crash — empty result is acceptable if IC data insufficient
        # but we should not get an exception
        assert isinstance(composite, pd.DataFrame)

    def test_single_factor_compute_score_direct(self):
        """Direct compute_composite_score with single factor."""
        icw = ICWeighting(min_ic_obs=2)
        stocks = [f"{i:06d}.SZ" for i in range(30)]
        signal_date = 20160516

        # Build factor df with enough dates for IC
        dates = [20160104, 20160111, 20160118, 20160125,
                 20160201, 20160208, 20160215, 20160222,
                 20160229, 20160307, 20160314, 20160321,
                 20160328, 20160404, 20160411, 20160418,
                 20160425, 20160502, 20160509, 20160516]

        factor_df = _make_factor_df("momentum", dates, stocks, seed=1)
        fwd = _make_fwd_returns(dates, stocks, seed=2)

        factor_dfs = {"momentum": factor_df}

        # Compute IC first
        ic_df = icw.compute_rolling_ic(factor_dfs, fwd, horizon=5, min_stocks=10)

        if ic_df.empty:
            # Not enough IC data — that's fine, the method should return empty
            result = icw.compute_composite_score(factor_dfs, ic_df, signal_date)
            assert isinstance(result, pd.DataFrame)
        else:
            result = icw.compute_composite_score(factor_dfs, ic_df, signal_date)
            if not result.empty:
                assert "composite_score" in result.columns
                assert "ts_code" in result.columns
                assert "trade_date" in result.columns

    def test_compute_weights_without_trade_dates_returns_empty(self):
        """Missing trade_dates → compute_weights returns {} (no silent leak)."""
        icw = ICWeighting(horizon=5, ic_window_months=12, min_ic_obs=3)
        # Create IC data but DON'T pass trade_dates
        dates = [
            20240102, 20240103, 20240104, 20240105, 20240108,
            20240109, 20240110, 20240111, 20240112, 20240115,
        ]
        stocks = [f"{i:06d}.SZ" for i in range(30)]
        factor = _make_factor_df("test_factor", dates, stocks, seed=1)
        fwd = _make_fwd_returns(dates, stocks, seed=2)
        ic_df = ICWeighting().compute_rolling_ic(
            {"test_factor": factor}, fwd, horizon=5,
        )
        # No trade_dates → should return empty dict
        weights = icw.compute_weights(ic_df, dates[-1], trade_dates=None)
        assert weights == {}, (
            f"Expected empty dict without trade_dates, got {weights}"
        )

    def test_cross_year_lookback_includes_previous_year(self):
        """Signal in Jan 2024 must include Dec 2023 IC history."""
        icw = ICWeighting(horizon=5, ic_window_months=2, min_ic_obs=3)
        stocks = [f"{i:06d}.SZ" for i in range(30)]

        # IC history from late 2023
        dec_dates = [
            20231201, 20231204, 20231205, 20231206, 20231207,
            20231208, 20231211, 20231212, 20231213, 20231214,
            20231215, 20231218, 20231219, 20231220, 20231221,
        ]
        jan_dates = [20240102, 20240103, 20240104, 20240105, 20240108]
        all_dates = sorted(dec_dates + jan_dates)
        trade_dates = all_dates

        factor = _make_factor_df("test_factor", all_dates, stocks, seed=3)
        fwd = _make_fwd_returns(all_dates, stocks, seed=4)

        ic_df = icw.compute_rolling_ic(
            {"test_factor": factor}, fwd, horizon=5,
        )

        # Signal on a Jan 2024 date — should include Dec 2023 ICs
        weights = icw.compute_weights(ic_df, 20240108, trade_dates=trade_dates)
        assert isinstance(weights, dict)
        # With 2-month lookback, Dec 2023 ICs should be included
        assert len(weights) > 0, (
            "Empty weights — cross-year lookback may be broken"
        )

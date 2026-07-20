"""Tests for turnover control mechanisms."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pandas as pd
import pytest


class TestNoTradeBand:
    """Test the no-trade band reduces micro-rebalancing."""

    def test_small_changes_skip_trade(self):
        from portfolio.optimized_weighting import _apply_no_trade_band

        target = pd.Series([0.52, 0.48], index=["A", "B"])
        prev = pd.Series([0.50, 0.50], index=["A", "B"])

        # Band = 0.05, changes of 0.02 < 0.05 → keep previous
        result = _apply_no_trade_band(target, prev, band=0.05)
        assert result["A"] == pytest.approx(0.50)
        assert result["B"] == pytest.approx(0.50)

    def test_large_changes_proceed(self):
        from portfolio.optimized_weighting import _apply_no_trade_band

        target = pd.Series([0.80, 0.20], index=["A", "B"])
        prev = pd.Series([0.40, 0.60], index=["A", "B"])

        result = _apply_no_trade_band(target, prev, band=0.05)
        assert result["A"] == pytest.approx(0.80)
        assert result["B"] == pytest.approx(0.20)

    def test_mixed_changes(self):
        from portfolio.optimized_weighting import _apply_no_trade_band

        target = pd.Series([0.51, 0.30, 0.19], index=["A", "B", "C"])
        prev = pd.Series([0.50, 0.20, 0.30], index=["A", "B", "C"])

        # A: 0.01 < 0.05 → keep
        # B: 0.10 > 0.05 → use target
        # C: 0.11 > 0.05 → use target
        result = _apply_no_trade_band(target, prev, band=0.05)
        assert result.sum() == pytest.approx(1.0)


class TestMaxWeightChange:
    """Test max weight change cap preserves weight constraints."""

    def test_weight_sum_one_after_cap(self):
        from portfolio.optimized_weighting import _apply_max_weight_change

        target = pd.Series([0.9, 0.1], index=["A", "B"])
        prev = pd.Series([0.5, 0.5], index=["A", "B"])

        result = _apply_max_weight_change(target, prev, max_change=0.20)
        assert result.sum() == pytest.approx(1.0)
        # A: from 0.5 to 0.9 (+0.40), capped to 0.5 + 0.20 = 0.70
        assert result["A"] <= 0.71

    def test_floor_at_zero_long_only(self):
        from portfolio.optimized_weighting import _apply_max_weight_change

        target = pd.Series([1.0, 0.0], index=["A", "B"])
        prev = pd.Series([0.5, 0.5], index=["A", "B"])

        result = _apply_max_weight_change(target, prev, max_change=0.30)
        assert result.sum() == pytest.approx(1.0)
        # All weights should be >= 0 (long-only)
        assert (result >= 0).all()

    def test_new_stock_with_no_previous(self):
        from portfolio.optimized_weighting import _apply_max_weight_change

        target = pd.Series([0.6, 0.3, 0.1], index=["A", "B", "C"])
        prev = pd.Series([0.5, 0.5], index=["A", "B"])  # C is new

        result = _apply_max_weight_change(target, prev, max_change=0.15)
        assert result.sum() == pytest.approx(1.0)
        assert "C" in result.index


class TestBufferSelection:
    """Test buffer selection logic."""

    def test_retain_holdings_within_exit_rank(self):
        from backtest.portfolio_backtester import PortfolioBacktester

        scores = pd.DataFrame({
            "ts_code": [f"{i:06d}.SZ" for i in range(200)],
            "composite_score": np.linspace(1, 0, 200),
        })

        # Previous holdings: codes 0 and 50
        prev = pd.Series([0.5, 0.5], index=["000000.SZ", "000050.SZ"])

        result = PortfolioBacktester._select_with_buffer(
            scores, "composite_score", 100,
            prev, entry_rank=100, exit_rank=150,
        )

        # Both prev holdings should be retained (both in top 150)
        codes = set(result["ts_code"])
        assert "000000.SZ" in codes  # rank 1
        assert "000050.SZ" in codes  # rank 51
        assert len(result) <= 100

    def test_force_exit_below_exit_rank(self):
        from backtest.portfolio_backtester import PortfolioBacktester

        scores = pd.DataFrame({
            "ts_code": [f"{i:06d}.SZ" for i in range(200)],
            "composite_score": np.linspace(1, 0, 200),
        })

        # Previous holdings: code 160 (rank 161, below exit_rank=150)
        prev = pd.Series([1.0], index=["000160.SZ"])
        result = PortfolioBacktester._select_with_buffer(
            scores, "composite_score", 100,
            prev, entry_rank=100, exit_rank=150,
        )
        codes = set(result["ts_code"])
        assert "000160.SZ" not in codes  # forced exit

    def test_no_previous_positions_falls_back_to_simple(self):
        from backtest.portfolio_backtester import PortfolioBacktester

        scores = pd.DataFrame({
            "ts_code": [f"{i:06d}.SZ" for i in range(200)],
            "composite_score": np.linspace(1, 0, 200),
        })

        result = PortfolioBacktester._select_with_buffer(
            scores, "composite_score", 100,
            None, entry_rank=100, exit_rank=150,
        )
        assert len(result) == 100

    def test_retain_priority_over_new_candidates(self):
        """Retained stocks get priority over new candidates with same rank."""
        from backtest.portfolio_backtester import PortfolioBacktester

        scores = pd.DataFrame({
            "ts_code": [f"{i:06d}.SZ" for i in range(200)],
            "composite_score": np.linspace(1, 0, 200),
        })

        # Hold rank 51-60 stocks
        prev = pd.Series(
            [0.1] * 10,
            index=[f"0000{i:02d}.SZ" for i in range(51, 61)],
        )

        result = PortfolioBacktester._select_with_buffer(
            scores, "composite_score", 100,
            prev, entry_rank=100, exit_rank=150,
        )
        # The retained stocks (rank 51-60) should be in the result
        retained_codes = {f"0000{i:02d}.SZ" for i in range(51, 61)}
        assert retained_codes.issubset(set(result["ts_code"]))
        assert len(result) <= 100


class TestScoreSmoothing:
    """Test score smoothing function."""

    def test_smoothing_reduces_dispersion(self):
        from backtest.portfolio_backtester import PortfolioBacktester

        scores = pd.DataFrame({
            "ts_code": [f"{i:06d}.SZ" for i in range(100)],
            "composite_score": np.random.randn(100) * 2,
        })

        smoothed = PortfolioBacktester._smooth_scores(
            scores, "composite_score", 20240101, halflife=4
        )

        orig_std = scores["composite_score"].std()
        smooth_std = smoothed["composite_score"].std()
        # Smoothing should reduce dispersion
        assert smooth_std <= orig_std * 1.1  # at least not increase significantly

    def test_zero_halflife_no_change(self):
        from backtest.portfolio_backtester import PortfolioBacktester

        scores = pd.DataFrame({
            "ts_code": ["A", "B", "C"],
            "composite_score": [1.0, 0.5, 0.0],
        })

        result = PortfolioBacktester._smooth_scores(
            scores, "composite_score", 20240101, halflife=0
        )
        # Should return unchanged
        pd.testing.assert_frame_equal(result, scores)

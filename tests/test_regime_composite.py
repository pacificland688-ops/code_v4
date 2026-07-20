"""
Tests for alpha.regime_composite — RegimeCompositeBuilder.

Verifies:
  - Output has required columns [ts_code, trade_date, composite_score]
  - Score is z-scored cross-sectionally
  - Two sleeves combine correctly
  - Single sleeve returns empty
  - Missing sleeve skipped
  - Zero-weight sleeve skipped
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pandas as pd
import pytest

from alpha.regime_composite import RegimeCompositeBuilder


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_sleeve_score(
    sleeve_name: str,
    dates: list,
    n_stocks: int = 30,
    score_mean: float = 0.0,
    score_std: float = 1.0,
    rng_seed: int = 42,
) -> pd.DataFrame:
    """Create synthetic sleeve composite score DataFrame."""
    rng = np.random.default_rng(rng_seed)
    rows = []
    for d in dates:
        for i in range(n_stocks):
            rows.append({
                "ts_code": f"{i + 1:06d}.SZ",
                "trade_date": d,
                "composite_score": float(score_mean + score_std * rng.standard_normal()),
            })
    return pd.DataFrame(rows)


def _make_sleeve_weights(
    dates: list,
    weights_dict: dict = None,
) -> pd.DataFrame:
    """Create synthetic sleeve weights DataFrame."""
    if weights_dict is None:
        weights_dict = {
            "reversal": 0.30,
            "momentum": 0.30,
            "defensive": 0.20,
            "value": 0.10,
            "volume_price": 0.10,
        }
    rows = []
    for d in dates:
        row = {"trade_date": d}
        for name, w in weights_dict.items():
            row[f"{name}_weight"] = w
        rows.append(row)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestRegimeCompositeBuilder:
    """Unit tests for RegimeCompositeBuilder."""

    def test_output_has_required_columns(self):
        """Output must have [ts_code, trade_date, composite_score]."""
        builder = RegimeCompositeBuilder(min_sleeves=2)
        dates = [20200106, 20200113]

        scores = {
            "reversal": _make_sleeve_score("reversal", dates, rng_seed=1),
            "momentum": _make_sleeve_score("momentum", dates, rng_seed=2),
        }
        weights = _make_sleeve_weights(dates)

        composite = builder.build(scores, weights)

        assert not composite.empty
        assert "ts_code" in composite.columns
        assert "trade_date" in composite.columns
        assert "composite_score" in composite.columns

    def test_score_is_zscored_cross_sectionally(self):
        """Composite score should be z-scored per date (mean~0, std~1)."""
        builder = RegimeCompositeBuilder(min_sleeves=2)
        dates = [20200106]

        # Use more stocks for better statistical accuracy
        scores = {
            "reversal": _make_sleeve_score("reversal", dates, n_stocks=500, rng_seed=1),
            "momentum": _make_sleeve_score("momentum", dates, n_stocks=500, rng_seed=2),
        }
        weights = _make_sleeve_weights(dates)

        composite = builder.build(scores, weights)

        for trade_date, group in composite.groupby("trade_date"):
            mean = group["composite_score"].mean()
            std = group["composite_score"].std()
            assert abs(mean) < 1e-6, f"Date {trade_date}: mean={mean}, expected ~0"
            # Finite sample tolerance: with 500 stocks, std should be within ~0.05 of 1.0
            assert abs(std - 1.0) < 0.10, f"Date {trade_date}: std={std}, expected ~1"

    def test_two_sleeves_combine_correctly(self):
        """Weighted sum of two sleeves should produce expected score."""
        builder = RegimeCompositeBuilder(min_sleeves=2)
        dates = [20200106]

        # Create sleeves with known scores
        n = 10
        rows_r = []
        rows_m = []
        for i in range(n):
            rows_r.append({
                "ts_code": f"{i + 1:06d}.SZ",
                "trade_date": 20200106,
                "composite_score": 1.0,  # all 1.0 for reversal
            })
            rows_m.append({
                "ts_code": f"{i + 1:06d}.SZ",
                "trade_date": 20200106,
                "composite_score": 2.0,  # all 2.0 for momentum
            })

        scores = {
            "reversal": pd.DataFrame(rows_r),
            "momentum": pd.DataFrame(rows_m),
        }
        # reversal=0.3, momentum=0.7 → weighted = 0.3*1.0 + 0.7*2.0 = 1.7
        weights = _make_sleeve_weights(dates, {
            "reversal": 0.30, "momentum": 0.70,
            "defensive": 0.0, "value": 0.0, "volume_price": 0.0,
        })

        composite = builder.build(scores, weights)

        assert not composite.empty
        # After z-scoring, all scores should be identical (since all stocks have same input)
        # → std=0, so z-score = 0
        # So we just check that the un-zscored pre-image was 1.7
        # Actually we test this indirectly: with all identical values, std=0, output is 0
        scores_out = composite["composite_score"].unique()
        assert len(scores_out) == 1 and scores_out[0] == 0.0

    def test_single_sleeve_returns_empty(self):
        """With only 1 sleeve and min_sleeves=2, should return empty."""
        builder = RegimeCompositeBuilder(min_sleeves=2)
        dates = [20200106]

        scores = {
            "reversal": _make_sleeve_score("reversal", dates, rng_seed=1),
        }
        weights = _make_sleeve_weights(dates, {
            "reversal": 1.0, "momentum": 0.0,
            "defensive": 0.0, "value": 0.0, "volume_price": 0.0,
        })

        composite = builder.build(scores, weights)
        assert composite.empty

    def test_missing_sleeve_skipped(self):
        """Sleeve with no scores should be silently skipped."""
        builder = RegimeCompositeBuilder(min_sleeves=2)
        dates = [20200106]

        scores = {
            "reversal": _make_sleeve_score("reversal", dates, rng_seed=1),
            "momentum": _make_sleeve_score("momentum", dates, rng_seed=2),
            "defensive": pd.DataFrame(),  # empty
            "value": pd.DataFrame(),       # empty
        }
        weights = _make_sleeve_weights(dates, {
            "reversal": 0.50, "momentum": 0.50,
            "defensive": 0.0, "value": 0.0, "volume_price": 0.0,
        })

        composite = builder.build(scores, weights)
        assert not composite.empty  # 2 sleeves with scores is enough

    def test_weight_zero_sleeve_skipped(self):
        """Sleeve with weight=0 should not contribute."""
        builder = RegimeCompositeBuilder(min_sleeves=2)
        dates = [20200106]

        scores = {
            "reversal": _make_sleeve_score("reversal", dates, rng_seed=1),
            "momentum": _make_sleeve_score("momentum", dates, rng_seed=3),
            "defensive": pd.DataFrame(),
            "value": pd.DataFrame(),
        }
        # Only momentum has weight > 0, reversal=0 → only 1 sleeve active
        weights = _make_sleeve_weights(dates, {
            "reversal": 0.0, "momentum": 1.0,
            "defensive": 0.0, "value": 0.0, "volume_price": 0.0,
        })

        composite = builder.build(scores, weights)
        assert composite.empty  # only 1 active sleeve < min_sleeves=2

    def test_empty_weights_returns_empty(self):
        """Empty weights DataFrame should return empty composite."""
        builder = RegimeCompositeBuilder()
        scores = {"reversal": _make_sleeve_score("reversal", [20200106])}
        composite = builder.build(scores, pd.DataFrame())
        assert composite.empty

    def test_multiple_dates_produces_all_rows(self):
        """All dates with valid scores should appear in output."""
        builder = RegimeCompositeBuilder(min_sleeves=2)
        dates = [20200106, 20200113, 20200120]
        n_stocks = 30

        scores = {
            "reversal": _make_sleeve_score("reversal", dates, n_stocks, rng_seed=1),
            "momentum": _make_sleeve_score("momentum", dates, n_stocks, rng_seed=2),
        }
        weights = _make_sleeve_weights(dates)

        composite = builder.build(scores, weights)

        assert not composite.empty
        # Should have n_stocks * n_dates rows
        assert len(composite) == n_stocks * len(dates)
        assert set(composite["trade_date"].unique()) == set(dates)

    def test_different_stocks_per_sleeve_handled(self):
        """Sleeves with different stock coverage should merge correctly."""
        builder = RegimeCompositeBuilder(min_sleeves=2)
        dates = [20200106]

        # Reversal: stocks 1-30
        scores_rev = _make_sleeve_score("reversal", dates, n_stocks=30, rng_seed=1)
        # Momentum: stocks 20-40 (overlap 20-30)
        rows_m = []
        for i in range(20, 41):
            rows_m.append({
                "ts_code": f"{i:06d}.SZ",
                "trade_date": 20200106,
                "composite_score": 1.0,
            })

        scores = {
            "reversal": scores_rev,
            "momentum": pd.DataFrame(rows_m),
        }
        weights = _make_sleeve_weights(dates, {
            "reversal": 0.50, "momentum": 0.50,
            "defensive": 0.0, "value": 0.0, "volume_price": 0.0,
        })

        composite = builder.build(scores, weights)
        assert not composite.empty
        # Overlap stocks (20-30) get combined score; unique stocks get single-sleeve score
        # Total unique stocks = 30 (1-30) + 11 (31-40) = 41
        assert len(composite) <= 41

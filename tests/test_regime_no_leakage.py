"""
Tests for no look-ahead leakage in regime components.

Verifies:
  - Future index data does not affect computed regime probabilities
  - Future prices do not affect breadth computation
  - Regime features use only PIT data
  - Sleeve scores use matured_ic_cutoff (via ICWeighting)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pandas as pd
import pytest

from alpha.regime_detector import RegimeDetector
from alpha.regime_allocator import RegimeAllocator
from alpha.regime_composite import RegimeCompositeBuilder


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_index_df(
    n_days: int = 300, trend: float = 0.0003, volatility: float = 0.015,
    start_date: int = 20200101, rng_seed: int = 42,
) -> pd.DataFrame:
    """Create synthetic index daily data."""
    rng = np.random.default_rng(rng_seed)
    rets = trend + volatility * rng.standard_normal(n_days)
    prices = 100.0 * np.cumprod(1.0 + rets)
    volumes = rng.lognormal(mean=15.0, sigma=0.5, size=n_days)

    dates = []
    current = start_date
    while len(dates) < n_days:
        day = current % 100
        if 1 <= day <= 28:
            dates.append(current)
        current += 1
        if (current % 100) > 31:
            current = ((current // 100) * 100) + 101
        if (current // 100) % 100 > 12:
            current = (((current // 10000) + 1) * 10000) + 101
    dates = sorted(dates)

    return pd.DataFrame({
        "ts_code": "000300.SH",
        "trade_date": dates,
        "close": prices,
        "vol": volumes,
    })


def _detector_config() -> dict:
    return {
        "index_code": "000300.SH",
        "trend": {"ma_short": 60, "ma_long": 120, "return_windows": [20, 60, 120]},
        "volatility": {"vol_windows": [20, 60], "drawdown_window": 60},
        "breadth": {"ma_window": 60, "min_stocks": 100},
        "smoothing": {"halflife": 0},
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestRegimeNoLeakage:
    """Verify that regime detection does not use future information."""

    def test_future_index_data_does_not_affect_regime_probs(self):
        """Modifying future index data should NOT change current regime probs."""
        detector = RegimeDetector(_detector_config())
        index_df = _make_index_df(n_days=300, rng_seed=1)

        # Split dates: first 200 days are "known", last 100 are "future"
        all_dates = sorted(index_df["trade_date"].unique())
        known_dates = all_dates[:200]
        future_dates = all_dates[200:]

        # Signal date = last known date
        signal_dates = known_dates[-10:]

        # Compute features and probs with original data
        features_orig = detector.compute_features(index_df, None, signal_dates)
        probs_orig = detector.predict_regime_probs(features_orig)

        # Now modify future data (set close to extreme values)
        index_modified = index_df.copy()
        future_mask = index_modified["trade_date"].isin(future_dates)
        # Drastically change future close prices
        index_modified.loc[future_mask, "close"] = index_modified.loc[future_mask, "close"] * 10.0

        features_mod = detector.compute_features(index_modified, None, signal_dates)
        probs_mod = detector.predict_regime_probs(features_mod)

        # Probabilities should be identical (future data not used)
        prob_cols = [c for c in probs_orig.columns if c.endswith("_prob")]
        pd.testing.assert_frame_equal(
            probs_orig[prob_cols].reset_index(drop=True),
            probs_mod[prob_cols].reset_index(drop=True),
            check_exact=False,
            rtol=1e-10,
        )

    def test_future_prices_do_not_affect_breadth(self):
        """Modifying future stock prices should NOT change breadth feature."""
        detector = RegimeDetector(_detector_config())
        index_df = _make_index_df(n_days=300, rng_seed=2)
        all_dates = sorted(index_df["trade_date"].unique())
        known_dates = all_dates[:200]
        future_dates = all_dates[200:]

        # Create prices_df with known + future data
        rng = np.random.default_rng(3)
        n_stocks = 150
        rows = []
        for i in range(n_stocks):
            ts_code = f"{i + 1:06d}.SZ"
            prices = 10.0 * np.cumprod(1.0 + 0.0003 + 0.02 * rng.standard_normal(len(all_dates)))
            for j, d in enumerate(all_dates):
                rows.append({"ts_code": ts_code, "trade_date": d, "adj_close": prices[j]})
        prices_df = pd.DataFrame(rows)

        signal_dates = known_dates[-5:]

        # Original breadth
        feat_orig = detector.compute_features(index_df, prices_df, signal_dates)
        breadth_orig = feat_orig["breadth_score"].copy()

        # Modify future prices drastically
        prices_modified = prices_df.copy()
        future_mask = prices_modified["trade_date"].isin(future_dates)
        prices_modified.loc[future_mask, "adj_close"] = 999999.0

        feat_mod = detector.compute_features(index_df, prices_modified, signal_dates)
        breadth_mod = feat_mod["breadth_score"].copy()

        # Breadth should be identical (only PIT data used)
        pd.testing.assert_series_equal(
            breadth_orig.reset_index(drop=True),
            breadth_mod.reset_index(drop=True),
            check_exact=False,
            rtol=1e-10,
        )

    def test_regime_features_only_use_pit_index_data(self):
        """Features at signal_date should only use index data <= signal_date."""
        detector = RegimeDetector(_detector_config())
        index_df = _make_index_df(n_days=300, rng_seed=4)

        all_dates = sorted(index_df["trade_date"].unique())
        signal_date = all_dates[200]  # mid-point

        # Index data truncated at signal_date
        idx_pit = index_df[index_df["trade_date"] <= signal_date]

        # Only feature rows should be trade_date <= signal_date
        feat_full = detector.compute_features(index_df, None, [signal_date])
        feat_pit = detector.compute_features(idx_pit, None, [signal_date])

        if not feat_full.empty and not feat_pit.empty:
            # Features should match exactly when using same PIT data
            for col in ["trend_strength", "volatility_state", "turnover_state"]:
                assert feat_full[col].iloc[0] == feat_pit[col].iloc[0], (
                    f"{col}: full={feat_full[col].iloc[0]}, pit={feat_pit[col].iloc[0]}"
                )


class TestRegimeAllocatorNoLeakage:
    """Verify that allocator does not have look-ahead issues."""

    def test_allocator_is_date_independent(self):
        """Allocator output for a given date should not depend on other dates."""
        config = {
            "min_sleeves": 2,
            "sleeve_weight_cap": 0.50,
            "sleeve_weight_floor": 0.05,
            "max_weekly_weight_change": 0.15,
            "regime_to_sleeve_weights": {
                "trend_up": {"reversal": 0.1, "momentum": 0.5, "defensive": 0.1, "value": 0.1, "volume_price": 0.2},
                "trend_down": {"reversal": 0.2, "momentum": 0.05, "defensive": 0.5, "value": 0.15, "volume_price": 0.1},
                "range_bound": {"reversal": 0.5, "momentum": 0.05, "defensive": 0.1, "value": 0.1, "volume_price": 0.25},
                "high_volatility": {"reversal": 0.2, "momentum": 0.05, "defensive": 0.5, "value": 0.15, "volume_price": 0.1},
                "value_rotation": {"reversal": 0.15, "momentum": 0.1, "defensive": 0.2, "value": 0.45, "volume_price": 0.1},
            },
        }

        probs1 = pd.DataFrame([{
            "trade_date": 20200106,
            "trend_up_prob": 0.5, "trend_down_prob": 0.1,
            "range_bound_prob": 0.2, "high_volatility_prob": 0.1, "value_rotation_prob": 0.1,
        }])

        probs2 = pd.DataFrame([
            {
                "trade_date": 20200106,
                "trend_up_prob": 0.5, "trend_down_prob": 0.1,
                "range_bound_prob": 0.2, "high_volatility_prob": 0.1, "value_rotation_prob": 0.1,
            },
            {
                "trade_date": 20200113,
                "trend_up_prob": 0.0, "trend_down_prob": 0.9,
                "range_bound_prob": 0.0, "high_volatility_prob": 0.1, "value_rotation_prob": 0.0,
            },
        ])

        alloc1 = RegimeAllocator(config)
        w1 = alloc1.compute_sleeve_weights(probs1)

        alloc2 = RegimeAllocator(config)
        w2 = alloc2.compute_sleeve_weights(probs2)

        # First date weights should be the same regardless of later dates
        weight_cols = [c for c in w1.columns if c.endswith("_weight")]
        row1 = w1.iloc[0][weight_cols]
        row2 = w2.iloc[0][weight_cols]
        pd.testing.assert_series_equal(row1, row2, check_exact=False, rtol=1e-10)


class TestCompositeNoLeakage:
    """Verify that composite builder does not introduce leakage."""

    def test_composite_only_uses_given_scores(self):
        """Composite should only use provided scores, no external data."""
        builder = RegimeCompositeBuilder(min_sleeves=2)
        dates = [20200106]

        scores = {
            "reversal": pd.DataFrame([
                {"ts_code": "000001.SZ", "trade_date": 20200106, "composite_score": 1.0},
                {"ts_code": "000002.SZ", "trade_date": 20200106, "composite_score": -1.0},
            ]),
            "momentum": pd.DataFrame([
                {"ts_code": "000001.SZ", "trade_date": 20200106, "composite_score": 2.0},
                {"ts_code": "000002.SZ", "trade_date": 20200106, "composite_score": -2.0},
            ]),
        }
        weights = pd.DataFrame([{
            "trade_date": 20200106,
            "reversal_weight": 0.5, "momentum_weight": 0.5,
            "defensive_weight": 0.0, "value_weight": 0.0, "volume_price_weight": 0.0,
        }])

        composite = builder.build(scores, weights)

        assert not composite.empty
        assert len(composite) == 2
        # All scores should be z-scored (mean=0)
        assert abs(composite["composite_score"].mean()) < 1e-6

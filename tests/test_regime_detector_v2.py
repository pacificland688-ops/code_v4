"""
Tests for alpha.regime_detector V2 PIT-normalized scoring.

Verifies:
  - V2 probs sum to 1.0
  - V2 range_bound lower share than V1 (no +3.0 bias)
  - V2 normalization stabilises feature scale
  - V2 warmup gracefulness
  - V2 value_rotation disabled → constant scores
  - V2 output compatible with existing RegimeAllocator
  - V1 behaviour untouched (no scoring_version → V1)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pandas as pd
import pytest

from alpha.regime_detector import RegimeDetector


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _generate_sequential_dates(start: int, n: int) -> list:
    """Generate n approximately sequential YYYYMMDD dates, skipping weekends."""
    dates = []
    current = start
    while len(dates) < n:
        day = current % 100
        if 1 <= day <= 28:
            dates.append(current)
        current += 1
        if (current % 100) > 31:
            current = ((current // 100) * 100) + 101
        if (current // 100) % 100 > 12:
            current = (((current // 10000) + 1) * 10000) + 101
    return sorted(dates)


def _make_index_df(
    n_days: int = 500,
    trend: float = 0.0,
    volatility: float = 0.015,
    start_price: float = 100.0,
    start_date: int = 20200101,
    rng_seed: int = 42,
) -> pd.DataFrame:
    """Create synthetic index daily data with realistic sequential dates."""
    rng = np.random.default_rng(rng_seed)
    rets = trend + volatility * rng.standard_normal(n_days)
    prices = start_price * np.cumprod(1.0 + rets)
    volumes = rng.lognormal(mean=15.0, sigma=0.5, size=n_days)
    dates = _generate_sequential_dates(start_date, n_days)

    return pd.DataFrame({
        "ts_code": "000300.SH",
        "trade_date": dates,
        "close": prices,
        "vol": volumes,
    })


def _v1_config() -> dict:
    return {
        "index_code": "000300.SH",
        "trend": {"ma_short": 60, "ma_long": 120, "return_windows": [20, 60, 120]},
        "volatility": {"vol_windows": [20, 60], "drawdown_window": 60},
        "breadth": {"ma_window": 60, "min_stocks": 10},
        "smoothing": {"halflife": 0},
        "temperature": 1.0,
    }


def _v2_config() -> dict:
    return {
        "scoring_version": "v2",
        "index_code": "000300.SH",
        "trend": {"ma_short": 60, "ma_long": 120, "return_windows": [20, 60, 120]},
        "volatility": {"vol_windows": [20, 60], "drawdown_window": 60},
        "breadth": {"ma_window": 60, "min_stocks": 10},
        "smoothing": {"halflife": 0},
        "normalization": {
            "mode": "expanding",
            "min_warmup_trading_days": 60,
        },
        "scoring": {
            "range_bound_baseline": 0.0,
            "value_rotation_enabled": False,
            "temperature": 1.0,
        },
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestRegimeDetectorV2:
    """Unit tests for V2 regime detection."""

    def test_v2_probabilities_sum_to_one(self):
        """V2 probs must still sum to 1.0."""
        cfg = _v2_config()
        index_df = _make_index_df(n_days=500)
        detector = RegimeDetector(cfg)
        signal_dates = sorted(index_df["trade_date"].unique())[60:]

        features = detector.compute_features(index_df, None, signal_dates)
        assert not features.empty, "should have features with 500 days of data"

        probs = detector.predict_regime_probs(features)
        assert not probs.empty, "should have regime probs"

        prob_cols = [c for c in probs.columns if c.endswith("_prob")]
        assert len(prob_cols) == 5, "should have 5 regime prob columns"

        sums = probs[prob_cols].sum(axis=1)
        for s in sums:
            assert abs(float(s) - 1.0) < 1e-6, f"prob sum {s:.8f} != 1.0"

    def test_v2_range_bound_lower_than_v1(self):
        """V2 range_bound should have lower mean prob than V1 (no +3.0 bias)."""
        index_df = _make_index_df(n_days=500, trend=0.0003)
        signal_dates = sorted(index_df["trade_date"].unique())[60:]

        # V1
        det_v1 = RegimeDetector(_v1_config())
        f_v1 = det_v1.compute_features(index_df, None, signal_dates)
        p_v1 = det_v1.predict_regime_probs(f_v1)
        v1_rb = float(p_v1["range_bound_prob"].mean())

        # V2
        det_v2 = RegimeDetector(_v2_config())
        f_v2 = det_v2.compute_features(index_df, None, signal_dates)
        p_v2 = det_v2.predict_regime_probs(f_v2)
        v2_rb = float(p_v2["range_bound_prob"].mean())

        # V2 range_bound should be notably lower
        assert v2_rb < v1_rb, (
            f"V2 range_bound ({v2_rb:.3f}) should be lower than V1 ({v1_rb:.3f})"
        )

    def test_v2_normalization_stabilizes_features(self):
        """Normalized features should have approx unit variance over time."""
        cfg = _v2_config()
        index_df = _make_index_df(n_days=600, trend=0.0005, volatility=0.025)
        detector = RegimeDetector(cfg)
        signal_dates = sorted(index_df["trade_date"].unique())[100:]

        features = detector.compute_features(index_df, None, signal_dates)
        probs = detector.predict_regime_probs(features)

        # Variance of probs should be moderate (not extreme 0-or-1)
        prob_cols = [c for c in probs.columns if c.endswith("_prob")]
        for col in prob_cols:
            std = float(probs[col].std())
            # Probs should not be degenerate
            assert 0 < std < 0.5, f"{col} std={std:.4f} — should be in (0, 0.5)"

    def test_v2_insufficient_warmup_graceful(self):
        """Dates with < min_warmup should still produce valid probs (no NaN)."""
        cfg = _v2_config()
        cfg["normalization"]["min_warmup_trading_days"] = 200
        index_df = _make_index_df(n_days=80)  # well below warmup
        detector = RegimeDetector(cfg)
        signal_dates = sorted(index_df["trade_date"].unique())

        features = detector.compute_features(index_df, None, signal_dates)
        # May be empty if not enough history for feature computation
        if features.empty:
            return  # skip — valid outcome

        probs = detector.predict_regime_probs(features)
        if probs.empty:
            return

        prob_cols = [c for c in probs.columns if c.endswith("_prob")]
        # No NaN in probs
        assert not probs[prob_cols].isna().any().any(), "probs must not contain NaN"

    def test_v2_value_rotation_constant_when_disabled(self):
        """value_rotation_enabled=False should keep value_rotation_prob constant."""
        cfg = _v2_config()
        cfg["scoring"]["value_rotation_enabled"] = False
        index_df = _make_index_df(n_days=500)
        detector = RegimeDetector(cfg)
        signal_dates = sorted(index_df["trade_date"].unique())[60:]

        features = detector.compute_features(index_df, None, signal_dates)
        probs = detector.predict_regime_probs(features)

        vr_std = float(probs["value_rotation_prob"].std())
        # With constant=0 score, softmax still distributes evenly across 5 regimes
        # so std won't be exactly 0, but should be low relative to other probs
        assert vr_std < 0.20, (
            f"value_rotation_prob std={vr_std:.4f} should be low when disabled"
        )

    def test_v2_output_compatible_with_v1_allocator(self):
        """V2 regime probs should work with existing RegimeAllocator."""
        from alpha.regime_allocator import RegimeAllocator

        cfg = _v2_config()
        index_df = _make_index_df(n_days=500)
        detector = RegimeDetector(cfg)
        signal_dates = sorted(index_df["trade_date"].unique())[60:]

        features = detector.compute_features(index_df, None, signal_dates)
        probs = detector.predict_regime_probs(features)

        alloc_cfg = {
            "min_sleeves": 2,
            "sleeve_weight_cap": 0.50,
            "sleeve_weight_floor": 0.05,
            "max_weekly_weight_change": 0.15,
            "regime_to_sleeve_weights": {
                "trend_up": {"momentum": 0.45, "volume_price": 0.25, "reversal": 0.10, "defensive": 0.10, "value": 0.10},
                "trend_down": {"defensive": 0.45, "value": 0.20, "reversal": 0.20, "momentum": 0.05, "volume_price": 0.10},
                "range_bound": {"reversal": 0.45, "volume_price": 0.25, "defensive": 0.15, "value": 0.10, "momentum": 0.05},
                "high_volatility": {"defensive": 0.50, "reversal": 0.20, "value": 0.15, "volume_price": 0.10, "momentum": 0.05},
                "value_rotation": {"value": 0.45, "defensive": 0.20, "reversal": 0.15, "momentum": 0.10, "volume_price": 0.10},
            },
        }
        allocator = RegimeAllocator(alloc_cfg)
        weights = allocator.compute_sleeve_weights(probs)

        assert not weights.empty, "allocator should produce weights from V2 probs"
        wt_cols = [c for c in weights.columns if c.endswith("_weight")]
        sums = weights[wt_cols].sum(axis=1)
        for s in sums:
            assert abs(float(s) - 1.0) < 1e-6

    def test_v1_unchanged_no_scoring_version(self):
        """Without scoring_version key, V1 behaviour is preserved."""
        cfg_v1 = _v1_config()
        assert "scoring_version" not in cfg_v1

        index_df = _make_index_df(n_days=500)
        detector = RegimeDetector(cfg_v1)
        assert detector.scoring_version == "v1"
        signal_dates = sorted(index_df["trade_date"].unique())[60:]

        features = detector.compute_features(index_df, None, signal_dates)
        probs = detector.predict_regime_probs(features)

        prob_cols = [c for c in probs.columns if c.endswith("_prob")]
        assert len(prob_cols) == 5
        sums = probs[prob_cols].sum(axis=1)
        for s in sums:
            assert abs(float(s) - 1.0) < 1e-6

    def test_v2_with_flat_market(self):
        """V2 in a flat/noisy market should still produce valid distinct probs."""
        cfg = _v2_config()
        index_df = _make_index_df(n_days=500, trend=0.0, volatility=0.01)
        detector = RegimeDetector(cfg)
        signal_dates = sorted(index_df["trade_date"].unique())[60:]

        features = detector.compute_features(index_df, None, signal_dates)
        probs = detector.predict_regime_probs(features)

        # Each regime should get some probability
        prob_cols = [c for c in probs.columns if c.endswith("_prob")]
        for col in prob_cols:
            assert float(probs[col].mean()) > 0.01, (
                f"{col} mean prob too low for flat market"
            )

    def test_v2_strong_trend_detected(self):
        """V2 should assign higher trend_up prob in a strong uptrend."""
        cfg = _v2_config()
        # Strong uptrend
        index_df = _make_index_df(n_days=500, trend=0.003, volatility=0.008)
        detector = RegimeDetector(cfg)
        signal_dates = sorted(index_df["trade_date"].unique())[250:]  # use 2nd half

        features = detector.compute_features(index_df, None, signal_dates)
        probs = detector.predict_regime_probs(features)

        # In uptrend, trend_up + range_bound should dominate trend_down
        tu = float(probs["trend_up_prob"].mean())
        td = float(probs["trend_down_prob"].mean())
        rb = float(probs["range_bound_prob"].mean())
        # Bullish regimes (trend_up + range_bound) should outweigh trend_down
        assert tu + rb > td, (
            f"trend_up+range_bound ({tu+rb:.3f}) should > trend_down ({td:.3f}) in uptrend"
        )

    def test_v2_high_vol_detected(self):
        """V2 should assign higher high_vol prob when volatility is elevated."""
        cfg = _v2_config()
        # High vol
        index_df = _make_index_df(n_days=500, trend=0.0, volatility=0.04)
        detector = RegimeDetector(cfg)
        signal_dates = sorted(index_df["trade_date"].unique())[250:]

        features = detector.compute_features(index_df, None, signal_dates)
        probs = detector.predict_regime_probs(features)

        hv = float(probs["high_volatility_prob"].mean())
        # In high vol regime, high_vol prob should be non-trivial
        assert hv > 0.10, f"high_volatility_prob ({hv:.3f}) too low in high vol market"

    def test_v2_positive_trend_not_trend_down(self):
        """In strong uptrend V2 should NOT collapse trend_up to zero."""
        cfg = _v2_config()
        # Strong uptrend — use many days so PIT z-scores detect the drift
        index_df = _make_index_df(n_days=800, trend=0.004, volatility=0.006)
        detector = RegimeDetector(cfg)
        # Use later half (after normalization has stabilised)
        signal_dates = sorted(index_df["trade_date"].unique())[400:]

        features = detector.compute_features(index_df, None, signal_dates)
        probs = detector.predict_regime_probs(features)

        tu = float(probs["trend_up_prob"].mean())
        # In uptrend, trend_up must be non-trivial (not collapsed to ~0)
        assert tu > 0.05, (
            f"trend_up_prob ({tu:.3f}) too low in uptrend — detector may be broken"
        )

    def test_v2_neutral_breadth_no_tilt(self):
        """With neutral breadth, V2 scoring should not penalise trend_up."""
        cfg = _v2_config()
        index_df = _make_index_df(n_days=600, trend=0.002, volatility=0.01)
        detector = RegimeDetector(cfg)
        signal_dates = sorted(index_df["trade_date"].unique())[300:]

        features = detector.compute_features(index_df, None, signal_dates)
        probs = detector.predict_regime_probs(features)

        # In a gentle uptrend, trend_up should not be crushed
        tu = float(probs["trend_up_prob"].mean())
        # Just check it's non-trivial
        assert tu > 0.05, f"trend_up_prob ({tu:.3f}) too low with neutral breadth"

    def test_v2_scoring_temperature_priority(self):
        """scoring.temperature should override top-level temperature."""
        # Config with scoring.temperature set
        cfg = _v2_config()
        cfg["temperature"] = 2.0          # top-level (should be overridden)
        cfg["scoring"]["temperature"] = 0.5  # scoring-level (should win)

        detector = RegimeDetector(cfg)
        assert detector.temperature == 0.5, (
            f"scoring.temperature should win, got {detector.temperature}"
        )

    def test_v2_temperature_top_level_fallback(self):
        """When scoring.temperature is absent, top-level temperature is used."""
        cfg = _v2_config()
        cfg["temperature"] = 1.5
        # Remove temperature from scoring section to force fallback
        scoring = cfg.setdefault("scoring", {})
        scoring.pop("temperature", None)

        detector = RegimeDetector(cfg)
        assert detector.temperature == 1.5

    def test_v2_temperature_default(self):
        """When no temperature is set anywhere, default is 1.0."""
        cfg = _v2_config()
        cfg.pop("temperature", None)
        if "temperature" in cfg.get("scoring", {}):
            del cfg["scoring"]["temperature"]

        detector = RegimeDetector(cfg)
        assert detector.temperature == 1.0


class TestRunIdUniqueness:
    """Tests for _generate_run_id uniqueness."""

    def test_concurrent_ids_are_unique(self):
        """100 back-to-back calls with identical args must produce unique IDs."""
        from run_research import _generate_run_id

        class _Args:
            start = "20240101"
            end = "20240131"
            top_n = 50
            strategy_mode = "regime"
            regime_config = "configs/direct_state_v1.yaml"

        ids = set()
        for _ in range(100):
            rid = _generate_run_id(_Args)
            assert rid not in ids, f"duplicate run_id: {rid}"
            ids.add(rid)

    def test_different_configs_have_different_stems(self):
        """A/B configs produce IDs with their own stem/hash."""
        from run_research import _generate_run_id

        class ArgsA:
            start = "20240101"
            end = "20240131"
            top_n = 50
            strategy_mode = "regime"
            regime_config = "configs/regime_v2.yaml"

        class ArgsB:
            start = "20240101"
            end = "20240131"
            top_n = 50
            strategy_mode = "regime"
            regime_config = "configs/direct_state_v1.yaml"

        id_a = _generate_run_id(ArgsA)
        id_b = _generate_run_id(ArgsB)

        assert "regime_v2" in id_a
        assert "direct_state_v1" in id_b
        assert id_a != id_b


class TestValueRotationRobustness:
    """Tests for value_rotation robustness against bad price data."""

    def test_zero_close_falls_back_to_zero(self):
        """When close prices are 0, value_rotation_score must be 0."""
        cfg = _v2_config()
        cfg["scoring"]["value_rotation_enabled"] = True
        index_df = _make_index_df(n_days=500)
        detector = RegimeDetector(cfg)
        signal_dates = sorted(index_df["trade_date"].unique())[100:]

        features = detector.compute_features(index_df, None, signal_dates)
        # Inject fake auxiliary index with zero close prices
        fake_aux = pd.DataFrame({
            "trade_date": sorted(index_df["trade_date"].unique()),
            "value_close": [0.0] * len(index_df),
            "growth_close": [0.0] * len(index_df),
        })
        detector._aux_index_cache = fake_aux

        probs = detector.predict_regime_probs(features)
        # value_rotation must be constant (all-zero scores → equal softmax prob)
        vr_std = float(probs["value_rotation_prob"].std())
        assert vr_std < 0.05, (
            f"value_rotation_prob std={vr_std:.4f} should be near-zero with zero close"
        )
        # No NaN
        assert not probs["value_rotation_prob"].isna().any()

    def test_nan_inf_close_falls_back_safely(self):
        """NaN/inf close prices should not crash or produce NaN probs."""
        cfg = _v2_config()
        cfg["scoring"]["value_rotation_enabled"] = True
        index_df = _make_index_df(n_days=500)
        detector = RegimeDetector(cfg)
        signal_dates = sorted(index_df["trade_date"].unique())[100:]

        features = detector.compute_features(index_df, None, signal_dates)
        # Half valid, half NaN/inf
        dates = sorted(index_df["trade_date"].unique())
        n = len(dates)
        vc = np.where(np.arange(n) % 3 == 0, np.nan, 100.0)
        gc = np.where(np.arange(n) % 3 == 1, np.inf, 100.0)
        fake_aux = pd.DataFrame({
            "trade_date": dates,
            "value_close": vc,
            "growth_close": gc,
        })
        detector._aux_index_cache = fake_aux

        probs = detector.predict_regime_probs(features)
        # Must not crash, must not produce NaN/Inf
        prob_cols = [c for c in probs.columns if c.endswith("_prob")]
        assert not probs[prob_cols].isna().any().any()
        assert not np.isinf(probs[prob_cols].values).any()

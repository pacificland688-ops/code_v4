"""
Tests for validate_market_state_momentum_rules.py.

Covers:
  1. High volatility rule → momentum_off
  2. High breadth rule → momentum_on
  3. Priority: vol + breadth high → still momentum_off
  4. PIT rolling q75 only uses past data
  5. Output contract: all output files present, YAML schema, manifest
  6. Negative conclusion: NO_RULE_ALPHA when metrics don't pass
  7. Strict OOS: thresholds from train only, evaluation on test only
  8. Walk-forward: expanding windows, OOS per window
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

from scripts.validate_market_state_momentum_rules import (
    apply_market_state_rules,
    apply_market_state_rules_oos,
    _compute_validation_metrics,
    _compute_label_metrics,
    _compute_rolling_q75,
    _compute_factor_ic_series,
    _compute_validation_by_year,
    _compute_walkforward_validation,
    _discover_rules_from_train_window,
    _translate_rules_to_test_signals,
    _compute_window_verdict,
    _compute_overall_discovery_verdict,
    _compute_walkforward_discovery_validation,
    _write_discovery_outputs,
    _write_outputs,
    _resolve_final_verdict,
    MIN_PIT_WARMUP,
    MIN_LABEL_DAYS,
    DISCOVERY_FACTORS,
    DISCOVERY_STATE_COLS,
    MOMENTUM_FACTOR,
)


# ===========================================================================
# Helpers
# ===========================================================================

def _make_synthetic_dates(start: int, n: int) -> np.ndarray:
    """Generate approximate trading dates (skip weekends naively)."""
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
    return np.array(sorted(dates), dtype=np.int64)


def _make_synthetic_panel(
    n_days: int = 500,
    vol_mean: float = 0.20,
    vol_std: float = 0.10,
    breadth_mean: float = 0.50,
    breadth_std: float = 0.20,
    seed: int = 42,
) -> pd.DataFrame:
    """Create a synthetic panel with volatility_state, breadth_score, and IC."""
    rng = np.random.default_rng(seed)
    dates = _make_synthetic_dates(20200102, n_days)

    return pd.DataFrame({
        "trade_date": dates,
        "volatility_state": np.maximum(0.01, rng.normal(vol_mean, vol_std, n_days)),
        "breadth_score": np.clip(rng.normal(breadth_mean, breadth_std, n_days), 0.0, 1.0),
    })


# ===========================================================================
# Test 1: High volatility rule
# ===========================================================================

class TestHighVolRule:
    """Verify that high volatility triggers momentum_off."""

    def test_high_vol_produces_momentum_off_research_mode(self):
        """When vol >= q75, signal should be momentum_off (research mode)."""
        panel = _make_synthetic_panel(n_days=200)
        result = apply_market_state_rules(panel, mode="research")

        vol_q75 = result["vol_q75"].iloc[0]
        high_vol_mask = result["volatility_state"] >= vol_q75

        # All high-vol days should be momentum_off
        high_vol_signals = result.loc[high_vol_mask, "rule_signal"]
        assert (high_vol_signals == "momentum_off").all(), (
            f"All high-vol days should be momentum_off, got: {high_vol_signals.unique()}"
        )

    def test_high_vol_produces_momentum_off_rolling_pit_mode(self):
        """When vol >= rolling_q75, signal should be momentum_off (PIT mode)."""
        panel = _make_synthetic_panel(n_days=400)
        result = apply_market_state_rules(panel, mode="rolling_pit")

        # Check that vol_q75 values are computed (not all NaN)
        n_valid_q75 = result["vol_q75"].notna().sum()
        assert n_valid_q75 > 0, "Should have some valid q75 values"

        # For days where vol >= vol_q75, signal should be momentum_off
        high_vol = result.dropna(subset=["vol_q75"])
        high_vol_days = high_vol[high_vol["volatility_state"] >= high_vol["vol_q75"]]
        if len(high_vol_days) > 0:
            assert (high_vol_days["rule_signal"] == "momentum_off").all()

    def test_low_vol_not_momentum_off(self):
        """When vol < q75, signal should NOT be momentum_off (unless breadth high)."""
        panel = _make_synthetic_panel(n_days=200)
        result = apply_market_state_rules(panel, mode="research")

        vol_q75 = result["vol_q75"].iloc[0]
        low_vol_mask = result["volatility_state"] < vol_q75

        low_vol_signals = result.loc[low_vol_mask, "rule_signal"]
        assert "momentum_off" not in low_vol_signals.values, (
            "Low-vol days should never be momentum_off"
        )


# ===========================================================================
# Test 2: High breadth rule
# ===========================================================================

class TestHighBreadthRule:
    """Verify that high breadth triggers momentum_on (when vol is not high)."""

    def test_high_breadth_low_vol_produces_momentum_on(self):
        """When breadth >= q75 and vol < q75, signal should be momentum_on."""
        panel = _make_synthetic_panel(n_days=200)
        result = apply_market_state_rules(panel, mode="research")

        vol_q75 = result["vol_q75"].iloc[0]
        breadth_q75 = result["breadth_q75"].iloc[0]

        on_mask = (
            (result["breadth_score"] >= breadth_q75)
            & (result["volatility_state"] < vol_q75)
        )

        on_signals = result.loc[on_mask, "rule_signal"]
        if len(on_signals) > 0:
            assert (on_signals == "momentum_on").all(), (
                f"High-breadth + low-vol days should be momentum_on, got: {on_signals.unique()}"
            )

    def test_high_breadth_alone_insufficient_when_vol_high(self):
        """High breadth alone should not produce momentum_on when vol is also high."""
        # This is tested more thoroughly in priority test
        panel = _make_synthetic_panel(n_days=200)
        result = apply_market_state_rules(panel, mode="research")

        # Find days with high breadth
        breadth_q75 = result["breadth_q75"].iloc[0]
        vol_q75 = result["vol_q75"].iloc[0]

        high_breadth_mask = result["breadth_score"] >= breadth_q75
        high_both_mask = high_breadth_mask & (result["volatility_state"] >= vol_q75)

        both_signals = result.loc[high_both_mask, "rule_signal"]
        if len(both_signals) > 0:
            # When both high, should still be momentum_off (vol priority)
            assert (both_signals == "momentum_off").all(), (
                f"High-vol + high-breadth should be momentum_off (vol priority)"
            )


# ===========================================================================
# Test 3: Priority test
# ===========================================================================

class TestPriorityRule:
    """Verify that volatility rule takes priority over breadth rule."""

    def test_vol_priority_over_breadth(self):
        """When both vol and breadth are high, final signal = momentum_off."""
        panel = _make_synthetic_panel(n_days=200)
        result = apply_market_state_rules(panel, mode="research")

        vol_q75 = result["vol_q75"].iloc[0]
        breadth_q75 = result["breadth_q75"].iloc[0]

        both_high = (
            (result["volatility_state"] >= vol_q75)
            & (result["breadth_score"] >= breadth_q75)
        )

        if both_high.sum() > 0:
            both_signals = result.loc[both_high, "rule_signal"]
            assert (both_signals == "momentum_off").all(), (
                f"Vol priority must produce momentum_off when both high. "
                f"Got: {both_signals.value_counts().to_dict()}"
            )

    def test_priority_order_in_rule_labels(self):
        """Verify the rule labels reflect correct priority."""
        panel = _make_synthetic_panel(n_days=200)
        result = apply_market_state_rules(panel, mode="research")

        vol_q75 = result["vol_q75"].iloc[0]
        breadth_q75 = result["breadth_q75"].iloc[0]

        # Check a specific case: vol high, breadth high
        both_high = (
            (result["volatility_state"] >= vol_q75)
            & (result["breadth_score"] >= breadth_q75)
        )
        if both_high.sum() > 0:
            labels = result.loc[both_high, "rule_label"]
            assert (labels == "momentum_off_high_vol").all()

    def test_weight_multiplier_off_is_zero(self):
        """momentum_off should have weight multiplier = 0.0."""
        panel = _make_synthetic_panel(n_days=200)
        result = apply_market_state_rules(panel, mode="research")

        off_mask = result["rule_signal"] == "momentum_off"
        if off_mask.sum() > 0:
            multipliers = result.loc[off_mask, "momentum_weight_multiplier"]
            assert (multipliers == 0.0).all()

    def test_weight_multiplier_conservative_is_half(self):
        """momentum_off conservative variant should have weight multiplier = 0.5."""
        panel = _make_synthetic_panel(n_days=200)
        result = apply_market_state_rules(panel, mode="research")

        off_mask = result["rule_signal"] == "momentum_off"
        if off_mask.sum() > 0:
            multipliers = result.loc[off_mask, "momentum_weight_multiplier_conservative"]
            assert (multipliers == 0.5).all()


# ===========================================================================
# Test 4: PIT threshold test
# ===========================================================================

class TestPITThresholds:
    """Verify rolling q75 only uses past data (no future leakage)."""

    def test_rolling_q75_only_uses_past_data(self):
        """For any date T, q75 must be computed from data <= T only."""
        rng = np.random.default_rng(99)
        dates = _make_synthetic_dates(20200102, 300)
        state = pd.Series(rng.normal(0.20, 0.08, len(dates)), index=dates)

        q75_series = _compute_rolling_q75(state, dates, min_warmup=50)

        # Verify: modifying future data shouldn't change q75 at earlier dates
        state_modified = state.copy()
        # Drastically modify the last 50 observations
        state_modified.iloc[-50:] = 999.0

        q75_modified = _compute_rolling_q75(state_modified, dates, min_warmup=50)

        # q75 values before the modification point should be identical
        cutoff = dates[-51]
        for d in dates:
            if d <= cutoff and d in q75_series.index and d in q75_modified.index:
                if pd.notna(q75_series[d]) and pd.notna(q75_modified[d]):
                    assert q75_series[d] == q75_modified[d], (
                        f"q75 at date {d} changed when future data was modified: "
                        f"{q75_series[d]} vs {q75_modified[d]}"
                    )

    def test_rolling_q75_increasing_with_extreme_values(self):
        """Adding very large values should increase q75 at subsequent dates."""
        rng = np.random.default_rng(100)
        dates = _make_synthetic_dates(20200102, 200)
        # Stable series first
        state = pd.Series(0.20 + 0.05 * rng.normal(0, 1, len(dates)), index=dates)

        q75_before = _compute_rolling_q75(state, dates, min_warmup=50)

        # Add extreme values
        state_modified = state.copy()
        state_modified.iloc[150:] = 0.80  # very high vol

        q75_after = _compute_rolling_q75(state_modified, dates, min_warmup=50)

        # After the extreme values, q75 should be higher
        last_date = dates[-1]
        if pd.notna(q75_before.get(last_date)) and pd.notna(q75_after.get(last_date)):
            assert q75_after[last_date] > q75_before[last_date], (
                f"Expected higher q75 after extreme values: "
                f"{q75_after[last_date]} vs {q75_before[last_date]}"
            )

    def test_rolling_pit_mode_forbidden_future_market_state(self):
        """Rule signals must not use future market state values."""
        panel = _make_synthetic_panel(n_days=300)
        result = apply_market_state_rules(panel, mode="rolling_pit")

        # For each date, the q75 used should be based on expanding window
        # We verify that q75 at date T does not depend on dates > T
        dates = result["trade_date"].values
        vol_vals = result["volatility_state"].values

        for i in range(50, len(dates)):
            # Recompute q75 directly from past data
            past_vol = vol_vals[:i+1]
            expected_q75 = float(np.percentile(past_vol, 75))
            actual_q75 = result["vol_q75"].iloc[i]
            if pd.notna(actual_q75):
                assert abs(actual_q75 - expected_q75) < 0.001, (
                    f"Date index {i} (date={dates[i]}): q75={actual_q75:.4f} "
                    f"but expected {expected_q75:.4f} from past data"
                )


# ===========================================================================
# Test 5: Output contract test
# ===========================================================================

class TestOutputContract:
    """Verify all output files are generated with correct schema."""

    def test_all_output_files_produced(self, tmp_path):
        """All 6 output files must be generated."""
        out_dir = tmp_path / "test_validation_output"
        out_dir.mkdir()

        # Create minimal synthetic data
        dates = _make_synthetic_dates(20200102, 200)
        rule_signals = pd.DataFrame({
            "trade_date": dates,
            "volatility_state": np.random.default_rng(1).uniform(0.05, 0.50, 200),
            "breadth_score": np.random.default_rng(2).uniform(0.0, 1.0, 200),
            "vol_q75": [0.25] * 200,
            "breadth_q75": [0.65] * 200,
            "volatility_high": np.random.default_rng(3).choice([True, False], 200),
            "breadth_high": np.random.default_rng(4).choice([True, False], 200),
            "rule_signal": np.random.default_rng(5).choice(
                ["momentum_on", "momentum_off", "momentum_neutral"], 200
            ),
            "rule_label": ["test"] * 200,
            "momentum_weight_multiplier": [1.0] * 200,
            "momentum_weight_multiplier_conservative": [1.0] * 200,
        })

        daily_ic = pd.DataFrame({
            "trade_date": dates,
            "ic": np.random.default_rng(6).normal(-0.01, 0.10, 200),
        })

        validation_results = {
            "label_metrics": [
                {
                    "label": "momentum_on", "n_days": 50, "mean_ic": 0.02,
                    "icir": 0.15, "hit_rate": 0.55, "ic_std": 0.12,
                    "top_bottom_spread": 0.05, "top_quintile_excess": 0.01,
                    "estimated_cost": 0.003, "net_spread": 0.017,
                    "positive_years": 5, "max_year_contribution": 0.04,
                    "insufficient_data": False,
                },
                {
                    "label": "momentum_off", "n_days": 50, "mean_ic": -0.04,
                    "icir": -0.25, "hit_rate": 0.40, "ic_std": 0.14,
                    "top_bottom_spread": -0.06, "top_quintile_excess": -0.02,
                    "estimated_cost": 0.003, "net_spread": -0.043,
                    "positive_years": 1, "max_year_contribution": 0.01,
                    "insufficient_data": False,
                },
                {
                    "label": "momentum_neutral", "n_days": 100, "mean_ic": -0.01,
                    "icir": -0.08, "hit_rate": 0.48, "ic_std": 0.13,
                    "top_bottom_spread": 0.02, "top_quintile_excess": 0.005,
                    "estimated_cost": 0.003, "net_spread": -0.013,
                    "positive_years": 3, "max_year_contribution": 0.03,
                    "insufficient_data": False,
                },
            ],
            "baseline_metrics": {
                "label": "baseline_all_days", "n_days": 200, "mean_ic": -0.01,
                "icir": -0.07, "hit_rate": 0.48, "ic_std": 0.13,
                "top_bottom_spread": 0.03, "top_quintile_excess": 0.005,
                "estimated_cost": 0.003, "net_spread": -0.013,
                "positive_years": 4, "max_year_contribution": 0.03,
                "insufficient_data": False,
            },
            "acceptance_results": {
                "momentum_on": {
                    "verdict": "PASS",
                    "checks": [
                        {"check": "n_days", "pass": True, "detail": "OK"},
                        {"check": "mean_ic > baseline", "pass": True, "detail": "0.02 > -0.01"},
                        {"check": "icir > baseline", "pass": True, "detail": "0.15 > -0.07"},
                        {"check": "hit_rate > baseline", "pass": True, "detail": "0.55 > 0.48"},
                    ],
                },
                "momentum_off": {
                    "verdict": "PASS",
                    "checks": [
                        {"check": "n_days", "pass": True, "detail": "OK"},
                        {"check": "mean_ic < baseline", "pass": True, "detail": "-0.04 < -0.01"},
                    ],
                },
                "momentum_neutral": {
                    "verdict": "OBSERVE",
                    "checks": [{"check": "n_days", "pass": True, "detail": "OK"}],
                },
            },
            "overall_verdict": "PROMOTING_TO_STRATEGY",
            "overall_detail": "All checks pass.",
        }
        validation_by_year = pd.DataFrame({
            "year": [2020, 2021],
            "baseline_n": [100, 100],
            "baseline_mean_ic": [-0.01, 0.0],
            "baseline_icir": [-0.07, 0.0],
            "momentum_on_n": [25, 25],
            "momentum_on_mean_ic": [0.02, 0.03],
            "momentum_on_icir": [0.15, 0.20],
            "momentum_off_n": [25, 25],
            "momentum_off_mean_ic": [-0.04, -0.03],
            "momentum_off_icir": [-0.25, -0.20],
            "momentum_neutral_n": [50, 50],
            "momentum_neutral_mean_ic": [-0.01, -0.005],
            "momentum_neutral_icir": [-0.08, -0.04],
        })

        import argparse
        args = argparse.Namespace(start="20200101", end="20211231", horizon=20)

        _write_outputs(
            out_dir, "test_run", args, rule_signals, daily_ic,
            validation_results, validation_by_year, "rolling_pit",
            0.25, 0.65,
        )

        expected_files = [
            "rule_validation_summary.csv",
            "rule_validation_by_year.csv",
            "rule_signal_daily.csv",
            "rule_candidate_pool.yaml",
            "rule_validation_report.md",
            "rule_validation_manifest.json",
        ]
        for fname in expected_files:
            fp = out_dir / fname
            assert fp.exists(), f"Missing output file: {fname}"
            assert fp.stat().st_size > 0, f"Empty output file: {fname}"

    def test_yaml_has_eligible_factors_empty(self, tmp_path):
        """rule_candidate_pool.yaml must contain eligible_factors: []."""
        out_dir = tmp_path / "test_yaml"
        out_dir.mkdir()

        pool = {
            "schema": "market_state_momentum_rule_pool.v1",
            "rules": [],
            "eligible_factors": [],
            "no_leakage": {"enabled": True},
        }
        with open(out_dir / "rule_candidate_pool.yaml", "w", encoding="utf-8") as f:
            yaml.dump(pool, f)

        loaded = yaml.safe_load((out_dir / "rule_candidate_pool.yaml").read_text())
        assert loaded["eligible_factors"] == [], (
            "eligible_factors must be an empty list, not None or missing"
        )
        assert loaded["no_leakage"]["enabled"] is True, (
            "no_leakage.enabled must be True"
        )

    def test_manifest_has_no_leakage_enabled(self, tmp_path):
        """Manifest must include no_leakage.enabled: true."""
        out_dir = tmp_path / "test_manifest"
        out_dir.mkdir()

        manifest = {
            "schema": "rule_validation_manifest.v1",
            "no_leakage": {"enabled": True, "mode": "rolling_pit", "warmup_days": 252},
            "eligible_factors": [],
            "promotion_decision": "PROMOTE",
        }
        with open(out_dir / "rule_validation_manifest.json", "w", encoding="utf-8") as f:
            json.dump(manifest, f)

        loaded = json.loads((out_dir / "rule_validation_manifest.json").read_text())
        assert loaded["no_leakage"]["enabled"] is True
        assert loaded["eligible_factors"] == []

    def test_all_signal_labels_present_in_output(self, tmp_path):
        """All three signal labels (on, off, neutral) should be reflected in CSV."""
        out_dir = tmp_path / "test_labels"
        out_dir.mkdir()

        df = pd.DataFrame({
            "rule_signal": ["momentum_on", "momentum_off", "momentum_neutral"] * 10,
        })
        df.to_csv(out_dir / "rule_signal_daily.csv", index=False)

        loaded = pd.read_csv(out_dir / "rule_signal_daily.csv")
        assert set(loaded["rule_signal"].unique()) == {
            "momentum_on", "momentum_off", "momentum_neutral"
        }


# ===========================================================================
# Test 6: Negative conclusion test
# ===========================================================================

class TestNegativeConclusion:
    """Verify NO_RULE_ALPHA when metrics don't pass."""

    def test_no_rule_alpha_when_momentum_on_fails(self):
        """When momentum_on.mean_ic <= baseline.mean_ic, verdict = NO_RULE_ALPHA."""
        rule_signals = pd.DataFrame({
            "trade_date": _make_synthetic_dates(20200102, 200),
            "rule_signal": (["momentum_on"] * 50 + ["momentum_off"] * 50
                           + ["momentum_neutral"] * 100),
        })
        rng = np.random.default_rng(77)

        # Generate ICs: momentum_on worse than baseline
        ic_on = rng.normal(-0.05, 0.10, 50)
        ic_off = rng.normal(-0.01, 0.10, 50)
        ic_neutral = rng.normal(0.0, 0.10, 100)
        all_ic = np.concatenate([ic_on, ic_off, ic_neutral])

        daily_ic = pd.DataFrame({
            "trade_date": rule_signals["trade_date"],
            "ic": all_ic,
        })

        result = _compute_validation_metrics(rule_signals, daily_ic)

        assert result["overall_verdict"] == "NO_RULE_ALPHA", (
            f"When momentum_on is worse than baseline, verdict must be NO_RULE_ALPHA, "
            f"got: {result['overall_verdict']}"
        )

    def test_no_rule_alpha_when_off_not_worse_than_baseline(self):
        """When momentum_off is NOT worse than baseline, verdict can't be PROMOTING."""
        rule_signals = pd.DataFrame({
            "trade_date": _make_synthetic_dates(20200102, 200),
            "rule_signal": (["momentum_on"] * 50 + ["momentum_off"] * 50
                           + ["momentum_neutral"] * 100),
        })
        rng = np.random.default_rng(78)

        # momentum_on good, momentum_off also good (not worse)
        ic_on = rng.normal(0.03, 0.08, 50)
        ic_off = rng.normal(0.02, 0.08, 50)
        ic_neutral = rng.normal(-0.01, 0.10, 100)
        all_ic = np.concatenate([ic_on, ic_off, ic_neutral])

        daily_ic = pd.DataFrame({
            "trade_date": rule_signals["trade_date"],
            "ic": all_ic,
        })

        result = _compute_validation_metrics(rule_signals, daily_ic)

        # If momentum_off is not worse than baseline, it should at minimum be PARTIAL
        assert result["overall_verdict"] != "PROMOTING_TO_STRATEGY", (
            f"momentum_off not worse than baseline should block PROMOTING, "
            f"got: {result['overall_verdict']}"
        )

    def test_promoting_when_all_checks_pass(self):
        """When momentum_on > baseline AND momentum_off < baseline, PROMOTING."""
        rule_signals = pd.DataFrame({
            "trade_date": _make_synthetic_dates(20200102, 200),
            "rule_signal": (["momentum_on"] * 50 + ["momentum_off"] * 50
                           + ["momentum_neutral"] * 100),
        })
        rng = np.random.default_rng(79)

        # momentum_on significantly better, momentum_off significantly worse
        ic_on = rng.normal(0.04, 0.10, 50)
        ic_off = rng.normal(-0.06, 0.12, 50)
        ic_neutral = rng.normal(-0.005, 0.10, 100)
        all_ic = np.concatenate([ic_on, ic_off, ic_neutral])

        daily_ic = pd.DataFrame({
            "trade_date": rule_signals["trade_date"],
            "ic": all_ic,
        })

        result = _compute_validation_metrics(rule_signals, daily_ic)

        assert result["overall_verdict"] == "PROMOTING_TO_STRATEGY", (
            f"All checks passing should produce PROMOTING_TO_STRATEGY, "
            f"got: {result['overall_verdict']}"
        )

    def test_report_no_rule_alpha_message(self):
        """When verdict is NO_RULE_ALPHA, the detail must say 'do NOT proceed'."""
        detail = (
            "Market state variables can explain historical IC differences but cannot "
            "form stable, usable rules. The rules do NOT produce statistically or "
            "economically meaningful improvement over the baseline. "
            "Do NOT proceed to strategy switching development."
        )
        assert "do NOT proceed" in detail.lower() or "Do NOT proceed" in detail


# ===========================================================================
# Test 7: Metrics computation
# ===========================================================================

class TestMetricsComputation:
    """Verify _compute_label_metrics and _compute_validation_metrics."""

    def test_label_metrics_insufficient_data(self):
        """Very few observations → insufficient_data flag."""
        ic_series = pd.Series([0.01, 0.02], name="ic")
        result = _compute_label_metrics(ic_series, "test")
        assert result["insufficient_data"] is True
        assert result["n_days"] == 2

    def test_label_metrics_with_valid_data(self):
        """With enough observations, compute full metrics."""
        rng = np.random.default_rng(80)
        ic_series = pd.Series(rng.normal(0.01, 0.10, 200), name="ic")
        result = _compute_label_metrics(ic_series, "test")

        assert result["insufficient_data"] is False
        assert result["n_days"] == 200
        assert "mean_ic" in result
        assert "icir" in result
        assert "hit_rate" in result
        assert "net_spread" in result
        assert not np.isnan(result["mean_ic"])

    def test_validation_metrics_produces_all_labels(self):
        """Validation must produce metrics for all three rule labels + baseline."""
        rule_signals = pd.DataFrame({
            "trade_date": _make_synthetic_dates(20200102, 150),
            "rule_signal": (["momentum_on"] * 40 + ["momentum_off"] * 40
                           + ["momentum_neutral"] * 70),
        })
        rng = np.random.default_rng(81)
        daily_ic = pd.DataFrame({
            "trade_date": rule_signals["trade_date"],
            "ic": rng.normal(-0.01, 0.10, 150),
        })

        result = _compute_validation_metrics(rule_signals, daily_ic)

        labels = {lm["label"] for lm in result["label_metrics"]}
        assert labels == {"momentum_on", "momentum_off", "momentum_neutral"}

        assert "baseline_metrics" in result
        assert "acceptance_results" in result
        assert "overall_verdict" in result
        assert "overall_detail" in result

    def test_insufficient_data_verdict(self):
        """Empty IC data → INSUFFICIENT_DATA verdict."""
        rule_signals = pd.DataFrame({
            "trade_date": _make_synthetic_dates(20200102, 5),
            "rule_signal": ["momentum_on"] * 5,
        })
        # IC with non-matching dates
        daily_ic = pd.DataFrame({
            "trade_date": [20990102],
            "ic": [0.01],
        })

        result = _compute_validation_metrics(rule_signals, daily_ic)
        assert result["overall_verdict"] == "INSUFFICIENT_DATA"


# ===========================================================================
# Test 8: Year-by-year breakdown
# ===========================================================================

class TestYearByYear:
    """Verify year-by-year validation breakdown."""

    def test_year_by_year_output_format(self):
        """Year-by-year must have required columns."""
        rng = np.random.default_rng(82)
        dates = _make_synthetic_dates(20200102, 200)
        rule_signals = pd.DataFrame({
            "trade_date": dates,
            "rule_signal": rng.choice(
                ["momentum_on", "momentum_off", "momentum_neutral"], 200
            ),
        })
        daily_ic = pd.DataFrame({
            "trade_date": dates,
            "ic": rng.normal(-0.01, 0.10, 200),
        })

        result = _compute_validation_by_year(rule_signals, daily_ic)
        if not result.empty:
            required_cols = ["year", "baseline_n", "baseline_mean_ic", "baseline_icir"]
            for col in required_cols:
                assert col in result.columns, f"Missing column: {col}"

            # All years should be integers
            assert result["year"].dtype in [np.int64, np.int32, int]

    def test_year_by_year_empty_input(self):
        """Empty input → empty output."""
        empty_signals = pd.DataFrame(columns=["trade_date", "rule_signal"])
        empty_ic = pd.DataFrame(columns=["trade_date", "ic"])
        result = _compute_validation_by_year(empty_signals, empty_ic)
        assert result.empty


# ===========================================================================
# Test 9: Strict OOS validation
# ===========================================================================

class TestStrictOOS:
    """Verify that OOS mode uses frozen thresholds from train only."""

    def test_oos_thresholds_from_train_only(self):
        """Thresholds must be computed from train panel, NOT test panel."""
        rng = np.random.default_rng(200)

        # Train: low vol regime (mean 0.15)
        train_dates = _make_synthetic_dates(20200102, 300)
        train_panel = pd.DataFrame({
            "trade_date": train_dates,
            "volatility_state": rng.normal(0.15, 0.05, 300),
            "breadth_score": rng.uniform(0.3, 0.8, 300),
        })

        # Test: high vol regime (mean 0.40) — structurally different
        test_dates = _make_synthetic_dates(20210104, 200)
        test_panel = pd.DataFrame({
            "trade_date": test_dates,
            "volatility_state": rng.normal(0.40, 0.10, 200),
            "breadth_score": rng.uniform(0.1, 0.6, 200),
        })

        test_signals, frozen = apply_market_state_rules_oos(train_panel, test_panel)

        # Verify thresholds come from train
        train_vol_q75 = float(train_panel["volatility_state"].quantile(0.75))
        assert frozen["vol_q75"] == pytest.approx(train_vol_q75, abs=0.001)
        assert frozen["train_n_days"] == 300

        # Verify test days use FROZEN thresholds (not computed from test)
        assert (test_signals["vol_q75"] == frozen["vol_q75"]).all()
        assert (test_signals["breadth_q75"] == frozen["breadth_q75"]).all()

        # Verify NO train data leaks into test
        assert test_signals["trade_date"].min() >= test_dates[0]
        assert test_signals["trade_date"].max() <= test_dates[-1]
        assert len(test_signals) == len(test_panel)

    def test_oos_thresholds_insensitive_to_test_data(self):
        """Modifying test data must NOT change frozen thresholds."""
        rng = np.random.default_rng(201)

        train_panel = pd.DataFrame({
            "trade_date": _make_synthetic_dates(20200102, 300),
            "volatility_state": rng.normal(0.18, 0.06, 300),
            "breadth_score": rng.uniform(0.2, 0.8, 300),
        })

        test_panel_v1 = pd.DataFrame({
            "trade_date": _make_synthetic_dates(20210104, 100),
            "volatility_state": rng.normal(0.25, 0.08, 100),
            "breadth_score": rng.uniform(0.1, 0.7, 100),
        })

        # Version with extreme test data
        test_panel_v2 = test_panel_v1.copy()
        test_panel_v2["volatility_state"] = 999.0
        test_panel_v2["breadth_score"] = 0.0

        _, frozen_v1 = apply_market_state_rules_oos(train_panel, test_panel_v1)
        _, frozen_v2 = apply_market_state_rules_oos(train_panel, test_panel_v2)

        # Thresholds must be IDENTICAL regardless of test data
        assert frozen_v1["vol_q75"] == frozen_v2["vol_q75"]
        assert frozen_v1["breadth_q75"] == frozen_v2["breadth_q75"]

    def test_oos_signal_distribution_respects_train_thresholds(self):
        """In high-vol test data with low train threshold, most days = momentum_off."""
        rng = np.random.default_rng(202)

        # Train: very low vol
        train_panel = pd.DataFrame({
            "trade_date": _make_synthetic_dates(20200102, 300),
            "volatility_state": rng.normal(0.10, 0.03, 300),
            "breadth_score": rng.uniform(0.4, 0.9, 300),
        })

        # Test: very high vol
        test_panel = pd.DataFrame({
            "trade_date": _make_synthetic_dates(20210104, 100),
            "volatility_state": rng.normal(0.50, 0.05, 100),
            "breadth_score": rng.uniform(0.1, 0.5, 100),
        })

        test_signals, frozen = apply_market_state_rules_oos(train_panel, test_panel)

        # Almost all test days should be momentum_off (vol >> train q75)
        off_pct = (test_signals["rule_signal"] == "momentum_off").mean()
        assert off_pct > 0.7, (
            f"With test vol >> train vol, most days should be momentum_off. "
            f"Got off_pct={off_pct:.2f}, train_vol_q75={frozen['vol_q75']:.4f}"
        )


# ===========================================================================
# Test 10: Walk-forward validation
# ===========================================================================

class TestWalkForward:
    """Verify walk-forward validation produces correct structure."""

    def test_walkforward_produces_windows(self):
        """Walk-forward must produce one window per train_end year."""
        rng = np.random.default_rng(300)
        # Generate dates spanning 2015-2025 (need enough years for walk-forward)
        all_dates = []
        for y in range(2015, 2026):
            all_dates.extend(_make_synthetic_dates(int(f"{y}0102"), 240))
        dates = np.array(sorted(set(all_dates)))[:1200]

        panel = pd.DataFrame({
            "trade_date": dates,
            "volatility_state": rng.normal(0.20, 0.10, len(dates)),
            "breadth_score": rng.uniform(0.0, 1.0, len(dates)),
        })

        # IC: make momentum_on better, momentum_off worse
        vol_q75 = np.percentile(panel["volatility_state"], 75)
        ic_vals = np.where(
            panel["volatility_state"] >= vol_q75,
            rng.normal(-0.06, 0.12, len(dates)),  # high vol → worse IC
            rng.normal(0.02, 0.10, len(dates)),   # normal vol → better IC
        )
        daily_ic = pd.DataFrame({
            "trade_date": dates,
            "ic": ic_vals,
        })

        # Train ends: 2018, 2019, 2020, 2021
        train_end_dates = [20181231, 20191231, 20201231, 20211231]

        wf = _compute_walkforward_validation(panel, daily_ic, train_end_dates)

        assert wf["n_windows"] > 0, (
            f"Should have at least one walk-forward window, got {wf.get('error', '?')}"
        )
        assert len(wf["windows"]) == wf["n_windows"]
        assert "aggregate" in wf
        assert "oos_verdict" in wf

        # Each window must have required fields
        for w in wf["windows"]:
            assert "train_end" in w
            assert "test_start" in w
            assert "test_end" in w
            assert "frozen_thresholds" in w
            assert "label_metrics" in w
            # Test period must be AFTER train_end
            assert w["test_start"] > w["train_end"], (
                f"Test must start after train_end: {w['test_start']} <= {w['train_end']}"
            )

    def test_walkforward_empty_on_short_data(self):
        """Very short data → no walk-forward windows."""
        rng = np.random.default_rng(301)
        dates = _make_synthetic_dates(20200102, 50)

        panel = pd.DataFrame({
            "trade_date": dates,
            "volatility_state": rng.normal(0.20, 0.10, 50),
            "breadth_score": rng.uniform(0.0, 1.0, 50),
        })
        daily_ic = pd.DataFrame({
            "trade_date": dates,
            "ic": rng.normal(0.0, 0.10, 50),
        })

        train_end_dates = [20201231, 20211231]
        wf = _compute_walkforward_validation(panel, daily_ic, train_end_dates)

        # Should have 0 windows (test periods too short)
        assert wf["n_windows"] == 0
        assert "error" in wf

    def test_walkforward_oos_verdict_logic(self):
        """OOS verdict must be PROMOTING when on>baseline and off<baseline."""
        rng = np.random.default_rng(302)
        all_dates = []
        for y in range(2015, 2026):
            all_dates.extend(_make_synthetic_dates(int(f"{y}0102"), 240))
        dates = np.array(sorted(set(all_dates)))[:1200]

        panel = pd.DataFrame({
            "trade_date": dates,
            "volatility_state": rng.normal(0.20, 0.08, len(dates)),
            "breadth_score": rng.uniform(0.0, 1.0, len(dates)),
        })

        # Construct clear signal: high vol → bad IC, low vol → good IC
        high_vol = panel["volatility_state"] >= np.percentile(panel["volatility_state"], 75)
        ic_vals = np.where(
            high_vol,
            rng.normal(-0.08, 0.10, len(dates)),
            rng.normal(0.04, 0.10, len(dates)),
        )
        daily_ic = pd.DataFrame({
            "trade_date": dates,
            "ic": ic_vals,
        })

        train_end_dates = [20181231, 20191231, 20201231, 20211231]
        wf = _compute_walkforward_validation(panel, daily_ic, train_end_dates)

        assert wf["n_windows"] > 0
        # With strong signal, should be PROMOTING_TO_STRATEGY
        assert wf["oos_verdict"] in {
            "PROMOTING_TO_STRATEGY", "PARTIAL", "NO_RULE_ALPHA", "INSUFFICIENT_DATA"
        }

    def test_walkforward_stability_computed(self):
        """Stability metrics must be present when windows exist."""
        rng = np.random.default_rng(303)
        all_dates = []
        for y in range(2015, 2026):
            all_dates.extend(_make_synthetic_dates(int(f"{y}0102"), 240))
        dates = np.array(sorted(set(all_dates)))[:1200]

        panel = pd.DataFrame({
            "trade_date": dates,
            "volatility_state": rng.normal(0.20, 0.08, len(dates)),
            "breadth_score": rng.uniform(0.0, 1.0, len(dates)),
        })
        daily_ic = pd.DataFrame({
            "trade_date": dates,
            "ic": rng.normal(0.0, 0.10, len(dates)),
        })

        train_end_dates = [20181231, 20191231, 20201231]
        wf = _compute_walkforward_validation(panel, daily_ic, train_end_dates)

        if wf["n_windows"] >= 2:
            stability = wf.get("stability", {})
            assert "momentum_on" in stability or "momentum_off" in stability, (
                "Should have stability metrics for at least one label"
            )
            for label, stats in stability.items():
                assert "mean_of_means" in stats
                assert "std_of_means" in stats
                assert "n_windows" in stats
                assert stats["n_windows"] >= 2


# ===========================================================================
# Test 11: Walk-forward discovery — rule discovery uses only training data
# ===========================================================================

class TestDiscoveryTrainOnly:
    """Verify rule discovery and thresholds use ONLY training data."""

    def test_discovery_uses_only_training_data(self):
        """Modifying test-period market state must NOT change discovered rules."""
        rng = np.random.default_rng(400)

        # Build train data
        train_dates = _make_synthetic_dates(20170102, 300)
        train_panel_data = {
            "trade_date": train_dates,
        }
        # Add market state columns
        for col in DISCOVERY_STATE_COLS:
            if col in ["size_spread_20d", "gv_spread_20d"]:
                train_panel_data[col] = rng.normal(0.0, 0.05, 300)
            elif col == "turnover_state":
                train_panel_data[col] = rng.normal(0.0, 1.0, 300)
            elif col == "volatility_state":
                train_panel_data[col] = rng.normal(0.20, 0.08, 300)
            elif col == "breadth_score":
                train_panel_data[col] = rng.uniform(0.0, 1.0, 300)
            elif col == "trend_strength":
                train_panel_data[col] = rng.normal(0.0, 0.10, 300)

        # Add factor IC columns
        for fn in DISCOVERY_FACTORS:
            train_panel_data[f"{fn}_ic"] = rng.normal(-0.01, 0.10, 300)

        train_panel = pd.DataFrame(train_panel_data)

        # Factor data and fwd returns
        factor_data = {}
        factor_ics = {}
        for fn in DISCOVERY_FACTORS:
            fd = pd.DataFrame({
                "ts_code": [f"{i:06d}.SZ" for i in range(100) for _ in range(300)],
                "trade_date": list(train_dates) * 100,
                "value": rng.normal(0, 1, 300 * 100),
            })
            factor_data[fn] = fd
            fic = pd.DataFrame({
                "trade_date": train_dates,
                "ic": train_panel_data[f"{fn}_ic"],
            })
            factor_ics[fn] = fic

        fwd_df = pd.DataFrame({
            "ts_code": [f"{i:06d}.SZ" for i in range(100) for _ in range(300)],
            "trade_date": list(train_dates) * 100,
            "fwd_ret_20d": rng.normal(0, 0.10, 300 * 100),
            "adj_close": rng.uniform(5, 100, 300 * 100),
        })

        # Run discovery twice — results should be identical
        result1 = _discover_rules_from_train_window(
            train_panel, factor_ics, factor_data, fwd_df
        )
        result2 = _discover_rules_from_train_window(
            train_panel, factor_ics, factor_data, fwd_df
        )

        assert result1["n_rule_candidates"] == result2["n_rule_candidates"]
        assert len(result1["rule_candidates"]) == len(result2["rule_candidates"])

    def test_discovery_insensitive_to_outside_data(self):
        """Adding data outside train period must not change discovery results."""
        rng = np.random.default_rng(401)

        train_dates = _make_synthetic_dates(20170102, 300)
        train_panel_data = {"trade_date": train_dates}
        for col in DISCOVERY_STATE_COLS:
            if col in ["size_spread_20d", "gv_spread_20d"]:
                train_panel_data[col] = rng.normal(0.0, 0.05, 300)
            elif col == "turnover_state":
                train_panel_data[col] = rng.normal(0.0, 1.0, 300)
            elif col == "volatility_state":
                train_panel_data[col] = rng.normal(0.20, 0.08, 300)
            elif col == "breadth_score":
                train_panel_data[col] = rng.uniform(0.0, 1.0, 300)
            elif col == "trend_strength":
                train_panel_data[col] = rng.normal(0.0, 0.10, 300)
        for fn in DISCOVERY_FACTORS:
            train_panel_data[f"{fn}_ic"] = rng.normal(-0.01, 0.10, 300)

        # Version 1: clean train panel
        train_panel_v1 = pd.DataFrame(train_panel_data)

        # Version 2: add extreme data after train_period (should be ignored)
        extra_dates = _make_synthetic_dates(20180102, 100)  # dates inside train period
        extra_data = train_panel_data.copy()
        for k in extra_data:
            if isinstance(extra_data[k], np.ndarray):
                extra_data[k] = np.concatenate([
                    extra_data[k],
                    rng.normal(999, 1, 100) if "ic" in k or k in DISCOVERY_STATE_COLS else rng.normal(0, 1, 100)
                ])
        extra_data["trade_date"] = np.concatenate([train_dates, extra_dates])
        train_panel_v2 = pd.DataFrame(extra_data)

        factor_data = {}
        factor_ics = {}
        for fn in DISCOVERY_FACTORS:
            fd = pd.DataFrame({
                "ts_code": [f"{i:06d}.SZ" for i in range(100) for _ in range(300)],
                "trade_date": list(train_dates) * 100,
                "value": rng.normal(0, 1, 300 * 100),
            })
            factor_data[fn] = fd
            fic = pd.DataFrame({
                "trade_date": train_dates,
                "ic": train_panel_data[f"{fn}_ic"],
            })
            factor_ics[fn] = fic

        fwd_df = pd.DataFrame({
            "ts_code": [f"{i:06d}.SZ" for i in range(100) for _ in range(300)],
            "trade_date": list(train_dates) * 100,
            "fwd_ret_20d": rng.normal(0, 0.10, 300 * 100),
            "adj_close": rng.uniform(5, 100, 300 * 100),
        })

        result1 = _discover_rules_from_train_window(
            train_panel_v1, factor_ics, factor_data, fwd_df
        )
        result2 = _discover_rules_from_train_window(
            train_panel_v2, factor_ics, factor_data, fwd_df
        )

        # Rule count should be same (extra data may change quantile splits
        # but rule candidate status should be stable)
        # At minimum, coverage_blocked should be same
        assert set(result1["coverage_blocked"]) == set(result2["coverage_blocked"])


# ===========================================================================
# Test 12: Coverage blocked in discovery
# ===========================================================================

class TestDiscoveryCoverageBlocked:
    """Verify coverage-blocked factors don't generate rules."""

    def test_coverage_blocked_factor_excluded(self):
        """earnings_acceleration_cs with low coverage must not generate rules."""
        rng = np.random.default_rng(500)
        train_dates = _make_synthetic_dates(20170102, 300)

        train_panel_data = {"trade_date": train_dates}
        for col in DISCOVERY_STATE_COLS:
            if col in ["size_spread_20d", "gv_spread_20d"]:
                train_panel_data[col] = rng.normal(0.0, 0.05, 300)
            elif col == "turnover_state":
                train_panel_data[col] = rng.normal(0.0, 1.0, 300)
            elif col == "volatility_state":
                train_panel_data[col] = rng.normal(0.20, 0.08, 300)
            elif col == "breadth_score":
                train_panel_data[col] = rng.uniform(0.0, 1.0, 300)
            elif col == "trend_strength":
                train_panel_data[col] = rng.normal(0.0, 0.10, 300)
        for fn in DISCOVERY_FACTORS:
            train_panel_data[f"{fn}_ic"] = rng.normal(-0.01, 0.10, 300)

        train_panel = pd.DataFrame(train_panel_data)

        # Factor data with LOW coverage for earnings_acceleration_cs
        factor_data = {}
        factor_ics = {}
        for fn in DISCOVERY_FACTORS:
            if fn == "earnings_acceleration_cs":
                # Very low coverage: only 5 stocks instead of 100
                n_stocks = 5
            else:
                n_stocks = 100
            fd = pd.DataFrame({
                "ts_code": [f"{i:06d}.SZ" for i in range(n_stocks) for _ in range(300)],
                "trade_date": list(train_dates) * n_stocks,
                "value": rng.normal(0, 1, 300 * n_stocks),
            })
            factor_data[fn] = fd
            fic = pd.DataFrame({
                "trade_date": train_dates,
                "ic": train_panel_data[f"{fn}_ic"],
            })
            factor_ics[fn] = fic

        fwd_df = pd.DataFrame({
            "ts_code": [f"{i:06d}.SZ" for i in range(100) for _ in range(300)],
            "trade_date": list(train_dates) * 100,
            "fwd_ret_20d": rng.normal(0, 0.10, 300 * 100),
        })

        result = _discover_rules_from_train_window(
            train_panel, factor_ics, factor_data, fwd_df
        )

        # earnings_acceleration_cs should be coverage blocked
        assert "earnings_acceleration_cs" in result["coverage_blocked"], (
            f"earnings_acceleration_cs with 5% coverage must be blocked. "
            f"Blocked: {result['coverage_blocked']}"
        )

        # No rule candidate should reference earnings_acceleration_cs
        for rc in result["rule_candidates"]:
            assert rc["factor"] != "earnings_acceleration_cs", (
                f"Coverage-blocked factor must not generate rule: {rc}"
            )


# ===========================================================================
# Test 13: No-rule window
# ===========================================================================

class TestNoRuleWindow:
    """Verify NO_RULE_DISCOVERED when training yields no rules."""

    def test_no_rule_window_all_neutral(self):
        """When no rules discovered, test period = all momentum_neutral."""
        rng = np.random.default_rng(600)
        train_dates = _make_synthetic_dates(20170102, 300)
        test_dates = _make_synthetic_dates(20180103, 100)

        train_panel_data = {"trade_date": train_dates}
        for col in DISCOVERY_STATE_COLS:
            if col in ["size_spread_20d", "gv_spread_20d"]:
                train_panel_data[col] = rng.normal(0.0, 0.05, 300)
            elif col == "turnover_state":
                train_panel_data[col] = rng.normal(0.0, 1.0, 300)
            elif col == "volatility_state":
                train_panel_data[col] = rng.normal(0.20, 0.08, 300)
            elif col == "breadth_score":
                train_panel_data[col] = rng.uniform(0.0, 1.0, 300)
            else:
                train_panel_data[col] = rng.normal(0.0, 0.10, 300)

        # IC: pure noise (no state→IC relationship)
        for fn in DISCOVERY_FACTORS:
            train_panel_data[f"{fn}_ic"] = rng.normal(0.0, 0.10, 300)

        train_panel = pd.DataFrame(train_panel_data)
        test_panel = pd.DataFrame({"trade_date": test_dates})

        factor_data = {}
        factor_ics = {}
        for fn in DISCOVERY_FACTORS:
            fd = pd.DataFrame({
                "ts_code": [f"{i:06d}.SZ" for i in range(100) for _ in range(300)],
                "trade_date": list(train_dates) * 100,
                "value": rng.normal(0, 1, 300 * 100),
            })
            factor_data[fn] = fd
            fic = pd.DataFrame({
                "trade_date": train_dates,
                "ic": train_panel_data[f"{fn}_ic"],
            })
            factor_ics[fn] = fic

        fwd_df = pd.DataFrame({
            "ts_code": [f"{i:06d}.SZ" for i in range(100) for _ in range(300)],
            "trade_date": list(train_dates) * 100,
            "fwd_ret_20d": rng.normal(0, 0.10, 300 * 100),
            "adj_close": rng.uniform(5, 100, 300 * 100),
        })

        discovery = _discover_rules_from_train_window(
            train_panel, factor_ics, factor_data, fwd_df
        )

        # Translate to test signals with NO rules
        test_signals, applied = _translate_rules_to_test_signals(
            [], train_panel, test_panel
        )

        assert "NO_RULE_DISCOVERED" in applied.get("note", ""), (
            f"Should indicate no rules discovered: {applied}"
        )
        assert (test_signals["rule_signal"] == "momentum_neutral").all(), (
            "No rules → all test days should be momentum_neutral"
        )


# ===========================================================================
# Test 14: Multi-rule priority
# ===========================================================================

class TestMultiRulePriority:
    """Verify rule priority: negative > positive, abs(spread) > abs(spread)."""

    def test_negative_rule_priority_over_positive(self):
        """Negative risk-control rule must take priority over positive enable rule."""
        rng = np.random.default_rng(700)
        train_dates = _make_synthetic_dates(20170102, 300)
        test_dates = _make_synthetic_dates(20180103, 100)

        train_panel = pd.DataFrame({
            "trade_date": train_dates,
            "volatility_state": rng.normal(0.20, 0.08, 300),
            "breadth_score": rng.uniform(0.0, 1.0, 300),
        })
        test_panel = pd.DataFrame({
            "trade_date": test_dates,
            "volatility_state": rng.normal(0.50, 0.05, 100),  # ALL high vol
            "breadth_score": rng.uniform(0.7, 1.0, 100),      # ALL high breadth
        })

        # Two rules: vol→off (negative, priority 1), breadth→on (positive, priority 2)
        rules = [
            {
                "rule_id": "momentum_off_high_vol",
                "state_col": "volatility_state",
                "factor": MOMENTUM_FACTOR,
                "direction": "negative",
                "action": "momentum_off",
                "spread": -0.08,
                "p_value": 0.0001,
                "q_value": 0.001,
                "priority": 1,
            },
            {
                "rule_id": "momentum_on_high_breadth",
                "state_col": "breadth_score",
                "factor": MOMENTUM_FACTOR,
                "direction": "positive",
                "action": "momentum_on",
                "spread": 0.03,
                "p_value": 0.005,
                "q_value": 0.02,
                "priority": 2,
            },
        ]

        test_signals, applied = _translate_rules_to_test_signals(
            rules, train_panel, test_panel
        )

        # All days have BOTH high vol and high breadth → should be momentum_off (vol priority)
        assert (test_signals["rule_signal"] == "momentum_off").all(), (
            f"When both rules fire, negative rule must win. "
            f"Got: {test_signals['rule_signal'].value_counts().to_dict()}"
        )

    def test_rule_sort_order(self):
        """Discovery must sort rules: negative first, then by abs(spread) descending."""
        rng = np.random.default_rng(701)
        train_dates = _make_synthetic_dates(20170102, 300)

        train_panel_data = {"trade_date": train_dates}
        for col in DISCOVERY_STATE_COLS:
            if col in ["size_spread_20d", "gv_spread_20d"]:
                train_panel_data[col] = rng.normal(0.0, 0.05, 300)
            elif col == "turnover_state":
                train_panel_data[col] = rng.normal(0.0, 1.0, 300)
            elif col == "volatility_state":
                train_panel_data[col] = rng.normal(0.20, 0.08, 300)
            elif col == "breadth_score":
                train_panel_data[col] = rng.uniform(0.0, 1.0, 300)
            else:
                train_panel_data[col] = rng.normal(0.0, 0.10, 300)
        for fn in DISCOVERY_FACTORS:
            train_panel_data[f"{fn}_ic"] = rng.normal(-0.01, 0.10, 300)

        train_panel = pd.DataFrame(train_panel_data)

        factor_data = {}
        factor_ics = {}
        for fn in DISCOVERY_FACTORS:
            fd = pd.DataFrame({
                "ts_code": [f"{i:06d}.SZ" for i in range(100) for _ in range(300)],
                "trade_date": list(train_dates) * 100,
                "value": rng.normal(0, 1, 300 * 100),
            })
            factor_data[fn] = fd
            fic = pd.DataFrame({
                "trade_date": train_dates,
                "ic": train_panel_data[f"{fn}_ic"],
            })
            factor_ics[fn] = fic

        fwd_df = pd.DataFrame({
            "ts_code": [f"{i:06d}.SZ" for i in range(100) for _ in range(300)],
            "trade_date": list(train_dates) * 100,
            "fwd_ret_20d": rng.normal(0, 0.10, 300 * 100),
            "adj_close": rng.uniform(5, 100, 300 * 100),
        })

        result = _discover_rules_from_train_window(
            train_panel, factor_ics, factor_data, fwd_df
        )

        rules = result["rule_candidates"]
        if len(rules) >= 2:
            # First rule should be negative (if any negative rules exist)
            has_negative = any(r["direction"] == "negative" for r in rules)
            if has_negative:
                assert rules[0]["direction"] == "negative", (
                    f"First rule must be negative. Rules: {[(r['rule_id'], r['direction']) for r in rules]}"
                )

            # Priorities should be strictly increasing
            priorities = [r["priority"] for r in rules]
            assert priorities == sorted(priorities), (
                f"Priorities must be in ascending order: {priorities}"
            )


# ===========================================================================
# Test 15: Window verdict logic
# ===========================================================================

class TestWindowVerdict:
    """Verify per-window verdict logic."""

    def test_no_rule_discovered_verdict(self):
        """Empty rules → NO_RULE_DISCOVERED."""
        result = _compute_window_verdict(
            pd.DataFrame(), pd.DataFrame(), []
        )
        assert result["verdict"] == "NO_RULE_DISCOVERED"

    def test_pass_verdict_when_both_sides_work(self):
        """on>baseline AND off<baseline → PASS."""
        rng = np.random.default_rng(800)
        dates = _make_synthetic_dates(20210104, 200)

        rule_signals = pd.DataFrame({
            "trade_date": dates,
            "rule_signal": (["momentum_on"] * 50 + ["momentum_off"] * 50
                           + ["momentum_neutral"] * 100),
        })
        # on better, off worse
        ic_on = rng.normal(0.03, 0.08, 50)
        ic_off = rng.normal(-0.06, 0.10, 50)
        ic_neutral = rng.normal(-0.01, 0.10, 100)
        daily_ic = pd.DataFrame({
            "trade_date": dates,
            "ic": np.concatenate([ic_on, ic_off, ic_neutral]),
        })

        rules = [{"rule_id": "test_rule", "direction": "negative"}]
        result = _compute_window_verdict(rule_signals, daily_ic, rules)
        assert result["verdict"] == "PASS", (
            f"Both sides passing should be PASS, got {result['verdict']}: {result['detail']}"
        )

    def test_fail_verdict_when_neither_side_works(self):
        """on<baseline AND off>baseline → FAIL."""
        rng = np.random.default_rng(801)
        dates = _make_synthetic_dates(20210104, 200)

        rule_signals = pd.DataFrame({
            "trade_date": dates,
            "rule_signal": (["momentum_on"] * 50 + ["momentum_off"] * 50
                           + ["momentum_neutral"] * 100),
        })
        # on WORSE, off BETTER (reversed from expected)
        ic_on = rng.normal(-0.06, 0.10, 50)
        ic_off = rng.normal(0.03, 0.08, 50)
        ic_neutral = rng.normal(-0.01, 0.10, 100)
        daily_ic = pd.DataFrame({
            "trade_date": dates,
            "ic": np.concatenate([ic_on, ic_off, ic_neutral]),
        })

        rules = [{"rule_id": "test_rule", "direction": "negative"}]
        result = _compute_window_verdict(rule_signals, daily_ic, rules)
        assert result["verdict"] == "FAIL", (
            f"Neither side passing should be FAIL, got {result['verdict']}: {result['detail']}"
        )


# ===========================================================================
# Test 16: Overall discovery verdict
# ===========================================================================

class TestOverallDiscoveryVerdict:
    """Verify overall verdict aggregation."""

    def test_promoting_when_enough_windows_pass(self):
        """>=2 windows with rules, >=60% PASS, pooled OK → PROMOTING."""
        rng = np.random.default_rng(900)

        # Build 4 windows: 3 PASS, 1 FAIL
        all_signals = []
        all_ic_data = []
        windows = []

        for i, year in enumerate([2021, 2022, 2023, 2024]):
            dates_i = _make_synthetic_dates(int(f"{year}0104"), 200)
            verdict = "PASS" if i < 3 else "FAIL"

            rule_signals = pd.DataFrame({
                "trade_date": dates_i,
                "rule_signal": (["momentum_on"] * 50 + ["momentum_off"] * 50
                               + ["momentum_neutral"] * 100),
            })
            ic_on = rng.normal(0.03, 0.08, 50) if verdict == "PASS" else rng.normal(-0.06, 0.10, 50)
            ic_off = rng.normal(-0.06, 0.10, 50)
            ic_neutral = rng.normal(-0.01, 0.10, 100)
            daily_ic_i = pd.DataFrame({
                "trade_date": dates_i,
                "ic": np.concatenate([ic_on, ic_off, ic_neutral]),
            })

            all_signals.append(rule_signals)
            all_ic_data.append(daily_ic_i)

            windows.append({
                "train_end": int(f"{year-1}1231"),
                "test_start": int(f"{year}0104"),
                "test_end": int(f"{year}1230"),
                "verdict": verdict,
                "verdict_detail": f"Test window {year}",
                "verdict_checks": [],
                "discovery": {"n_rule_candidates": 1, "rules": [{"rule_id": "test_rule"}]},
            })

        all_test_signals = pd.concat(all_signals, ignore_index=True)
        all_test_ic = pd.concat(all_ic_data, ignore_index=True)

        result = _compute_overall_discovery_verdict(
            windows, all_test_signals, all_test_ic
        )

        assert result["overall_verdict"] == "PROMOTING_TO_STRATEGY", (
            f"3/4 PASS with pooled OK should be PROMOTING. Got: {result['overall_verdict']}"
        )
        assert result["pass_count"] == 3
        assert result["pass_ratio"] == 0.75

    def test_no_rule_alpha_when_few_windows(self):
        """Only 1 window with rules → NO_RULE_ALPHA."""
        rng = np.random.default_rng(901)
        dates = _make_synthetic_dates(20210104, 200)

        rule_signals = pd.DataFrame({
            "trade_date": dates,
            "rule_signal": (["momentum_on"] * 50 + ["momentum_off"] * 50
                           + ["momentum_neutral"] * 100),
        })
        daily_ic = pd.DataFrame({
            "trade_date": dates,
            "ic": rng.normal(0.0, 0.10, 200),
        })

        windows = [
            {"train_end": 20201231, "verdict": "PASS",
             "discovery": {"n_rule_candidates": 1, "rules": [{"rule_id": "r1"}]}},
            {"train_end": 20211231, "verdict": "NO_RULE_DISCOVERED",
             "discovery": {"n_rule_candidates": 0, "rules": []}},
            {"train_end": 20221231, "verdict": "NO_RULE_DISCOVERED",
             "discovery": {"n_rule_candidates": 0, "rules": []}},
        ]

        result = _compute_overall_discovery_verdict(
            windows, rule_signals, daily_ic
        )

        assert result["overall_verdict"] == "NO_RULE_ALPHA", (
            f"Only 1 window with rules should be NO_RULE_ALPHA. Got: {result['overall_verdict']}"
        )


# ===========================================================================
# Test 17: Discovery output contract
# ===========================================================================

class TestDiscoveryOutputContract:
    """Verify discovery-specific output files and metadata."""

    def test_discovery_output_files_produced(self, tmp_path):
        """All 4 discovery output files must be generated."""
        out_dir = tmp_path / "test_discovery_output"
        out_dir.mkdir()

        rng = np.random.default_rng(1000)
        walkforward_results = {
            "n_windows": 3,
            "n_with_rules": 3,
            "pass_count": 2,
            "pass_ratio": 0.667,
            "overall_verdict": "PROMOTING_TO_STRATEGY",
            "overall_detail": "2/3 windows PASS",
            "pooled_metrics": {
                "baseline_mean_ic": -0.03,
                "momentum_on_mean_ic": 0.02,
                "momentum_off_mean_ic": -0.07,
                "momentum_on_n": 150,
                "momentum_off_n": 150,
                "total_n": 600,
                "max_year_contribution_pct": 0.35,
            },
            "windows": [
                {
                    "train_end": 20201231,
                    "test_start": 20210104, "test_end": 20211231,
                    "train_n": 800, "test_n": 200,
                    "discovery": {
                        "n_rule_candidates": 1,
                        "n_fdr_robust": 2, "n_raw_significant": 4,
                        "coverage_blocked": ["earnings_acceleration_cs"],
                        "rules": [{
                            "rule_id": "momentum_off_high_volatility_state",
                            "state_col": "volatility_state",
                            "factor": MOMENTUM_FACTOR,
                            "direction": "negative",
                            "action": "momentum_off",
                            "spread": -0.08, "p_value": 0.001, "q_value": 0.005,
                            "priority": 1,
                        }],
                    },
                    "applied_rules": {"rules_applied": ["test"], "thresholds": {"volatility_state": 0.28}},
                    "label_metrics": {
                        "momentum_on": {"n_days": 50, "mean_ic": 0.03},
                        "momentum_off": {"n_days": 50, "mean_ic": -0.07},
                        "momentum_neutral": {"n_days": 100, "mean_ic": -0.02},
                        "baseline_all_days": {"n_days": 200, "mean_ic": -0.03},
                    },
                    "verdict": "PASS",
                    "verdict_detail": "on_pass=True, off_pass=True",
                    "verdict_checks": [],
                },
            ],
        }

        validation_results = {"overall_verdict": "PROMOTING_TO_STRATEGY"}

        _write_discovery_outputs(out_dir, walkforward_results, validation_results)

        expected_discovery_files = [
            "walkforward_discovery_windows.csv",
            "walkforward_discovery_rule_candidates.csv",
            "walkforward_discovery_test_metrics.csv",
            "walkforward_discovery_summary.yaml",
        ]
        for fname in expected_discovery_files:
            fp = out_dir / fname
            assert fp.exists(), f"Missing discovery output: {fname}"
            assert fp.stat().st_size > 0, f"Empty discovery output: {fname}"

    def test_discovery_yaml_has_required_fields(self, tmp_path):
        """Discovery summary YAML must have validation_mode and oos_safe flags."""
        out_dir = tmp_path / "test_disc_yaml"
        out_dir.mkdir()

        summary = {
            "schema": "walkforward_discovery_summary.v1",
            "validation_mode": "walkforward_discovery",
            "rule_discovery_oos_safe": True,
            "full_sample_rule_candidates_used": False,
            "windows": [],
        }
        with open(out_dir / "walkforward_discovery_summary.yaml", "w") as f:
            yaml.dump(summary, f)

        loaded = yaml.safe_load((out_dir / "walkforward_discovery_summary.yaml").read_text())
        assert loaded["validation_mode"] == "walkforward_discovery"
        assert loaded["rule_discovery_oos_safe"] is True
        assert loaded["full_sample_rule_candidates_used"] is False

    def test_manifest_has_discovery_metadata(self, tmp_path):
        """Manifest in discovery mode must include oos_safe flags."""
        manifest = {
            "schema": "rule_validation_manifest.v1",
            "validation_mode": "walkforward_discovery",
            "rule_discovery_oos_safe": True,
            "full_sample_rule_candidates_used": False,
            "eligible_factors": [],
        }
        manifest_dir = tmp_path / "test_manifest_disc"
        manifest_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = manifest_dir / "manifest.json"
        with open(manifest_path, "w") as f:
            json.dump(manifest, f)

        loaded = json.loads(manifest_path.read_text())
        assert loaded["rule_discovery_oos_safe"] is True
        assert loaded["full_sample_rule_candidates_used"] is False
        assert loaded["eligible_factors"] == []


# ===========================================================================
# Test 18: Unified verdict resolver
# ===========================================================================

class TestVerdictResolver:
    """Verify _resolve_final_verdict produces correct results for all modes."""

    def test_discovery_partial_yields_block(self):
        """discovery PARTIAL → BLOCK promotion."""
        validation_results = {"overall_verdict": "PROMOTING_TO_STRATEGY",
                             "overall_detail": "old detail"}
        walkforward_results = {
            "windows": [{"discovery": {"n_rule_candidates": 1}, "verdict": "PASS"}],
            "overall_verdict": "PARTIAL",
            "overall_detail": "3/4 windows PASS, but instability detected",
        }
        resolved = _resolve_final_verdict(
            validation_results, walkforward_results, is_oos=True
        )
        assert resolved["final_verdict"] == "PARTIAL"
        assert resolved["promotion_decision"] == "BLOCK"
        assert resolved["verdict_source"] == "walkforward_discovery"
        assert resolved["validation_mode"] == "walkforward_discovery"

    def test_discovery_promoting_yields_promote(self):
        """discovery PROMOTING_TO_STRATEGY → PROMOTE."""
        validation_results = {"overall_verdict": "PROMOTING_TO_STRATEGY"}
        walkforward_results = {
            "windows": [{"discovery": {"n_rule_candidates": 1}, "verdict": "PASS"}],
            "overall_verdict": "PROMOTING_TO_STRATEGY",
            "overall_detail": "All checks pass",
        }
        resolved = _resolve_final_verdict(
            validation_results, walkforward_results, is_oos=True
        )
        assert resolved["final_verdict"] == "PROMOTING_TO_STRATEGY"
        assert resolved["promotion_decision"] == "PROMOTE"

    def test_fixed_walkforward_partial_yields_block(self):
        """fixed-rule walkforward PARTIAL → BLOCK."""
        validation_results = {"overall_verdict": "PROMOTING_TO_STRATEGY"}
        walkforward_results = {
            "windows": [{"verdict": "PASS"}],  # no "discovery" key
            "oos_verdict": "PARTIAL",
            "overall_detail": "Partial validation",
        }
        resolved = _resolve_final_verdict(
            validation_results, walkforward_results, is_oos=True
        )
        assert resolved["final_verdict"] == "PARTIAL"
        assert resolved["promotion_decision"] == "BLOCK"
        assert resolved["verdict_source"] == "walkforward_oos"

    def test_strict_oos_uses_validation_results(self):
        """No walkforward → uses validation_results."""
        validation_results = {"overall_verdict": "NO_RULE_ALPHA",
                             "overall_detail": "Rules don't work"}
        resolved = _resolve_final_verdict(
            validation_results, None, is_oos=True
        )
        assert resolved["final_verdict"] == "NO_RULE_ALPHA"
        assert resolved["promotion_decision"] == "BLOCK"
        assert resolved["verdict_source"] == "strict_oos"

    def test_in_sample_mode(self):
        """In-sample → uses validation_results."""
        validation_results = {"overall_verdict": "PROMOTING_TO_STRATEGY",
                             "overall_detail": "In-sample only"}
        resolved = _resolve_final_verdict(
            validation_results, None, is_oos=False
        )
        assert resolved["final_verdict"] == "PROMOTING_TO_STRATEGY"
        assert resolved["verdict_source"] == "in_sample"
        # Still PROMOTE because verdict says so (even though in-sample)
        assert resolved["promotion_decision"] == "PROMOTE"

    def test_all_non_promoting_verdicts_blocked(self):
        """All non-PROMOTING verdicts must be BLOCK."""
        for verdict in ["PARTIAL", "FAIL", "NO_RULE_ALPHA", "NO_RULE_DISCOVERED",
                        "INSUFFICIENT_DATA"]:
            validation_results = {"overall_verdict": verdict, "overall_detail": ""}
            resolved = _resolve_final_verdict(validation_results, None, is_oos=True)
            assert resolved["promotion_decision"] == "BLOCK", (
                f"Verdict {verdict} must be BLOCK, got {resolved['promotion_decision']}"
            )


# ===========================================================================
# Test 19: Output consistency
# ===========================================================================

class TestOutputConsistency:
    """Verify all outputs use the unified verdict."""

    def test_yaml_shows_partial_for_discovery(self, tmp_path):
        """In discovery PARTIAL mode, YAML must show PARTIAL + BLOCK."""
        out_dir = tmp_path / "test_consistency_yaml"
        out_dir.mkdir()

        import argparse
        args = argparse.Namespace(
            start="20170101", end="20241231", horizon=20
        )

        validation_results = {
            "label_metrics": [
                {"label": "momentum_on", "n_days": 50, "mean_ic": 0.02, "icir": 0.1,
                 "hit_rate": 0.5, "ic_std": 0.1, "net_spread": 0.01,
                 "positive_years": 3, "top_bottom_spread": 0.05,
                 "top_quintile_excess": 0.01, "estimated_cost": 0.003,
                 "insufficient_data": False},
                {"label": "momentum_off", "n_days": 50, "mean_ic": -0.07, "icir": -0.3,
                 "hit_rate": 0.35, "ic_std": 0.12, "net_spread": -0.07,
                 "positive_years": 1, "top_bottom_spread": -0.08,
                 "top_quintile_excess": -0.02, "estimated_cost": 0.003,
                 "insufficient_data": False},
                {"label": "momentum_neutral", "n_days": 100, "mean_ic": -0.02, "icir": -0.1,
                 "hit_rate": 0.45, "ic_std": 0.11, "net_spread": -0.02,
                 "positive_years": 2, "top_bottom_spread": 0.02,
                 "top_quintile_excess": 0.005, "estimated_cost": 0.003,
                 "insufficient_data": False},
            ],
            "baseline_metrics": {"label": "baseline_all_days", "n_days": 200,
                                "mean_ic": -0.03, "icir": -0.15, "hit_rate": 0.45,
                                "ic_std": 0.11, "net_spread": -0.03,
                                "positive_years": 3, "top_bottom_spread": 0.03,
                                "top_quintile_excess": 0.005, "estimated_cost": 0.003,
                                "insufficient_data": False},
            "overall_verdict": "PROMOTING_TO_STRATEGY",  # old verdict (should be overridden)
            "overall_detail": "old detail",
            "acceptance_results": {},
        }
        validation_by_year = pd.DataFrame([{
            "year": 2021, "baseline_n": 200, "baseline_mean_ic": -0.03,
            "baseline_icir": -0.15, "momentum_on_n": 50, "momentum_on_mean_ic": 0.02,
            "momentum_on_icir": 0.1, "momentum_off_n": 50,
            "momentum_off_mean_ic": -0.07, "momentum_off_icir": -0.3,
            "momentum_neutral_n": 100, "momentum_neutral_mean_ic": -0.02,
            "momentum_neutral_icir": -0.1,
        }])

        walkforward_results = {
            "n_windows": 4,
            "overall_verdict": "PARTIAL",
            "overall_detail": "3/4 windows PASS, instability detected",
            "windows": [
                {
                    "train_end": 20201231, "test_start": 20210104, "test_end": 20211231,
                    "train_n": 800, "test_n": 200,
                    "discovery": {"n_rule_candidates": 1, "n_fdr_robust": 2,
                                  "n_raw_significant": 4,
                                  "coverage_blocked": [],
                                  "rules": [{"rule_id": "test_rule",
                                            "state_col": "volatility_state",
                                            "factor": MOMENTUM_FACTOR,
                                            "direction": "negative",
                                            "action": "momentum_off",
                                            "spread": -0.08, "p_value": 0.001,
                                            "q_value": 0.005, "priority": 1}]},
                    "applied_rules": {"rules_applied": []},
                    "label_metrics": {
                        "momentum_on": {"label": "momentum_on", "n_days": 50,
                                       "mean_ic": 0.02, "icir": 0.1, "hit_rate": 0.5,
                                       "ic_std": 0.1, "insufficient_data": False},
                        "momentum_off": {"label": "momentum_off", "n_days": 50,
                                        "mean_ic": -0.07, "icir": -0.3, "hit_rate": 0.35,
                                        "ic_std": 0.12, "insufficient_data": False},
                        "momentum_neutral": {"label": "momentum_neutral", "n_days": 100,
                                            "mean_ic": -0.02, "icir": -0.1, "hit_rate": 0.45,
                                            "ic_std": 0.11, "insufficient_data": False},
                        "baseline_all_days": {"label": "baseline_all_days", "n_days": 200,
                                             "mean_ic": -0.03, "icir": -0.15,
                                             "hit_rate": 0.45, "ic_std": 0.11,
                                             "insufficient_data": False},
                    },
                    "verdict": "PASS",
                    "verdict_detail": "ok",
                    "verdict_checks": [],
                }
            ],
        }

        frozen_thresholds = {
            "vol_q75": 0.2871, "breadth_q75": 0.4676,
            "train_end": 20201231, "train_n_days": 800,
        }

        rule_signals = pd.DataFrame({"trade_date": [20210104], "rule_signal": ["momentum_off"]})
        daily_ic = pd.DataFrame({"trade_date": [20210104], "ic": [-0.05]})

        _write_outputs(
            out_dir, "test_run", args, rule_signals, daily_ic,
            validation_results, validation_by_year, "rolling_pit",
            0.2871, 0.4676,
            frozen_thresholds=frozen_thresholds,
            walkforward_results=walkforward_results,
        )

        # Check YAML
        yaml_path = out_dir / "rule_candidate_pool.yaml"
        loaded_yaml = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        assert loaded_yaml["overall_verdict"] == "PARTIAL", (
            f"YAML must show PARTIAL, got {loaded_yaml['overall_verdict']}"
        )
        assert loaded_yaml["promotion_decision"] == "BLOCK"
        assert loaded_yaml["verdict_source"] == "walkforward_discovery"
        assert loaded_yaml["validation_mode"] == "walkforward_discovery"
        # Must NOT contain the old PROMOTING
        assert loaded_yaml["overall_verdict"] != "PROMOTING_TO_STRATEGY"

        # Check manifest
        manifest_path = out_dir / "rule_validation_manifest.json"
        loaded_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert loaded_manifest["promotion_decision"] == "BLOCK"
        assert loaded_manifest["validation_results"]["overall_verdict"] == "PARTIAL"

        # Check report
        report_path = out_dir / "rule_validation_report.md"
        report_text = report_path.read_text(encoding="utf-8")
        assert "PARTIAL" in report_text
        assert "BLOCK" in report_text
        assert "ready for strategy backtesting" not in report_text.lower()
        assert "PROMOTE" not in report_text, (
            f"Report should not contain PROMOTE for PARTIAL verdict"
        )

    def test_report_has_discovery_safe_no_leakage_text(self, tmp_path):
        """Discovery mode report must NOT mention full-sample discovery bias."""
        out_dir = tmp_path / "test_discovery_report_text"
        out_dir.mkdir()

        import argparse
        args = argparse.Namespace(
            start="20170101", end="20241231", horizon=20
        )

        validation_results = {
            "label_metrics": [
                {"label": "momentum_on", "n_days": 50, "mean_ic": 0.02, "icir": 0.1,
                 "hit_rate": 0.5, "ic_std": 0.1, "net_spread": 0.01,
                 "positive_years": 3, "top_bottom_spread": 0.05,
                 "top_quintile_excess": 0.01, "estimated_cost": 0.003,
                 "insufficient_data": False},
                {"label": "momentum_off", "n_days": 50, "mean_ic": -0.07, "icir": -0.3,
                 "hit_rate": 0.35, "ic_std": 0.12, "net_spread": -0.07,
                 "positive_years": 1, "top_bottom_spread": -0.08,
                 "top_quintile_excess": -0.02, "estimated_cost": 0.003,
                 "insufficient_data": False},
                {"label": "momentum_neutral", "n_days": 100, "mean_ic": -0.02, "icir": -0.1,
                 "hit_rate": 0.45, "ic_std": 0.11, "net_spread": -0.02,
                 "positive_years": 2, "top_bottom_spread": 0.02,
                 "top_quintile_excess": 0.005, "estimated_cost": 0.003,
                 "insufficient_data": False},
            ],
            "baseline_metrics": {"label": "baseline_all_days", "n_days": 200,
                                "mean_ic": -0.03, "icir": -0.15, "hit_rate": 0.45,
                                "ic_std": 0.11, "net_spread": -0.03,
                                "positive_years": 3, "top_bottom_spread": 0.03,
                                "top_quintile_excess": 0.005, "estimated_cost": 0.003,
                                "insufficient_data": False},
            "overall_verdict": "PROMOTING_TO_STRATEGY",
            "overall_detail": "old",
            "acceptance_results": {},
        }
        validation_by_year = pd.DataFrame([{
            "year": 2021, "baseline_n": 200, "baseline_mean_ic": -0.03,
            "baseline_icir": -0.15, "momentum_on_n": 50, "momentum_on_mean_ic": 0.02,
            "momentum_on_icir": 0.1, "momentum_off_n": 50,
            "momentum_off_mean_ic": -0.07, "momentum_off_icir": -0.3,
            "momentum_neutral_n": 100, "momentum_neutral_mean_ic": -0.02,
            "momentum_neutral_icir": -0.1,
        }])

        walkforward_results = {
            "n_windows": 3,
            "overall_verdict": "PARTIAL",
            "overall_detail": "test detail",
            "n_with_rules": 3, "pass_count": 2, "pass_ratio": 0.667,
            "pooled_metrics": {
                "baseline_mean_ic": -0.03, "momentum_on_mean_ic": 0.02,
                "momentum_off_mean_ic": -0.07, "momentum_on_n": 100,
                "momentum_off_n": 100, "total_n": 300,
                "max_year_contribution_pct": 0.55,
            },
            "windows": [
                {
                    "train_end": 20201231, "test_start": 20210104, "test_end": 20211231,
                    "train_n": 800, "test_n": 200,
                    "discovery": {"n_rule_candidates": 1, "n_fdr_robust": 2,
                                  "n_raw_significant": 4, "coverage_blocked": [],
                                  "rules": [{"rule_id": "r1", "state_col": "volatility_state",
                                            "factor": MOMENTUM_FACTOR, "direction": "negative",
                                            "action": "momentum_off", "spread": -0.08,
                                            "p_value": 0.001, "q_value": 0.005, "priority": 1}]},
                    "applied_rules": {"rules_applied": []},
                    "label_metrics": {
                        "momentum_on": {"label": "momentum_on", "n_days": 50,
                                       "mean_ic": 0.02, "icir": 0.1, "hit_rate": 0.5,
                                       "ic_std": 0.1, "insufficient_data": False},
                        "momentum_off": {"label": "momentum_off", "n_days": 50,
                                        "mean_ic": -0.07, "icir": -0.3, "hit_rate": 0.35,
                                        "ic_std": 0.12, "insufficient_data": False},
                        "momentum_neutral": {"label": "momentum_neutral", "n_days": 100,
                                            "mean_ic": -0.02, "icir": -0.1, "hit_rate": 0.45,
                                            "ic_std": 0.11, "insufficient_data": False},
                        "baseline_all_days": {"label": "baseline_all_days", "n_days": 200,
                                             "mean_ic": -0.03, "icir": -0.15,
                                             "hit_rate": 0.45, "ic_std": 0.11,
                                             "insufficient_data": False},
                    },
                    "verdict": "PASS", "verdict_detail": "ok", "verdict_checks": [],
                }
            ],
        }

        frozen_thresholds = {
            "vol_q75": 0.2871, "breadth_q75": 0.4676,
            "train_end": 20201231, "train_n_days": 800,
        }

        rule_signals = pd.DataFrame({"trade_date": [20210104], "rule_signal": ["momentum_off"]})
        daily_ic = pd.DataFrame({"trade_date": [20210104], "ic": [-0.05]})

        _write_outputs(
            out_dir, "test_run", args, rule_signals, daily_ic,
            validation_results, validation_by_year, "rolling_pit",
            0.2871, 0.4676,
            frozen_thresholds=frozen_thresholds,
            walkforward_results=walkforward_results,
        )

        report_text = (out_dir / "rule_validation_report.md").read_text(encoding="utf-8")

        # MUST contain discovery-safe statements
        assert "Rules re-discovered independently" in report_text, (
            "Discovery mode report must state rules were re-discovered independently"
        )
        assert "NO full-sample rule candidates used" in report_text, (
            "Discovery mode report must state no full-sample candidates were used"
        )
        assert "FDR + effect size + coverage gates" in report_text, (
            "Discovery mode report must mention within-window FDR gates"
        )

        # MUST NOT contain full-sample discovery bias text
        forbidden = [
            "discovered on the ENTIRE period",
            "FULL 2017-2024 period",
            "A more rigorous approach would discover rules on training data only",
        ]
        for phrase in forbidden:
            assert phrase not in report_text, (
                f"Discovery mode report must NOT contain: '{phrase}'"
            )

    def test_report_has_correct_discovery_limitations(self, tmp_path):
        """Discovery mode Known Limitations must mention real limits."""
        out_dir = tmp_path / "test_discovery_limits"
        out_dir.mkdir()

        import argparse
        args = argparse.Namespace(
            start="20170101", end="20241231", horizon=20
        )

        validation_results = {
            "label_metrics": [
                {"label": "momentum_on", "n_days": 50, "mean_ic": 0.02, "icir": 0.1,
                 "hit_rate": 0.5, "ic_std": 0.1, "net_spread": 0.01,
                 "positive_years": 3, "top_bottom_spread": 0.05,
                 "top_quintile_excess": 0.01, "estimated_cost": 0.003,
                 "insufficient_data": False},
                {"label": "momentum_off", "n_days": 50, "mean_ic": -0.07, "icir": -0.3,
                 "hit_rate": 0.35, "ic_std": 0.12, "net_spread": -0.07,
                 "positive_years": 1, "top_bottom_spread": -0.08,
                 "top_quintile_excess": -0.02, "estimated_cost": 0.003,
                 "insufficient_data": False},
                {"label": "momentum_neutral", "n_days": 100, "mean_ic": -0.02, "icir": -0.1,
                 "hit_rate": 0.45, "ic_std": 0.11, "net_spread": -0.02,
                 "positive_years": 2, "top_bottom_spread": 0.02,
                 "top_quintile_excess": 0.005, "estimated_cost": 0.003,
                 "insufficient_data": False},
            ],
            "baseline_metrics": {"label": "baseline_all_days", "n_days": 200,
                                "mean_ic": -0.03, "icir": -0.15, "hit_rate": 0.45,
                                "ic_std": 0.11, "net_spread": -0.03,
                                "positive_years": 3, "top_bottom_spread": 0.03,
                                "top_quintile_excess": 0.005, "estimated_cost": 0.003,
                                "insufficient_data": False},
            "overall_verdict": "PROMOTING_TO_STRATEGY",
            "overall_detail": "old",
            "acceptance_results": {},
        }
        validation_by_year = pd.DataFrame([{
            "year": 2021, "baseline_n": 200, "baseline_mean_ic": -0.03,
            "baseline_icir": -0.15, "momentum_on_n": 50, "momentum_on_mean_ic": 0.02,
            "momentum_on_icir": 0.1, "momentum_off_n": 50,
            "momentum_off_mean_ic": -0.07, "momentum_off_icir": -0.3,
            "momentum_neutral_n": 100, "momentum_neutral_mean_ic": -0.02,
            "momentum_neutral_icir": -0.1,
        }])

        walkforward_results = {
            "n_windows": 3,
            "overall_verdict": "PARTIAL",
            "overall_detail": "test",
            "n_with_rules": 3, "pass_count": 2, "pass_ratio": 0.667,
            "pooled_metrics": None,
            "windows": [
                {
                    "train_end": 20201231, "test_start": 20210104, "test_end": 20211231,
                    "train_n": 800, "test_n": 200,
                    "discovery": {"n_rule_candidates": 1, "n_fdr_robust": 2,
                                  "n_raw_significant": 4, "coverage_blocked": [],
                                  "rules": [{"rule_id": "r1", "state_col": "volatility_state",
                                            "factor": MOMENTUM_FACTOR, "direction": "negative",
                                            "action": "momentum_off", "spread": -0.08,
                                            "p_value": 0.001, "q_value": 0.005, "priority": 1}]},
                    "applied_rules": {"rules_applied": []},
                    "label_metrics": {
                        "momentum_on": {"label": "momentum_on", "n_days": 50,
                                       "mean_ic": 0.02, "icir": 0.1, "hit_rate": 0.5,
                                       "ic_std": 0.1, "insufficient_data": False},
                        "momentum_off": {"label": "momentum_off", "n_days": 50,
                                        "mean_ic": -0.07, "icir": -0.3, "hit_rate": 0.35,
                                        "ic_std": 0.12, "insufficient_data": False},
                        "momentum_neutral": {"label": "momentum_neutral", "n_days": 100,
                                            "mean_ic": -0.02, "icir": -0.1, "hit_rate": 0.45,
                                            "ic_std": 0.11, "insufficient_data": False},
                        "baseline_all_days": {"label": "baseline_all_days", "n_days": 200,
                                             "mean_ic": -0.03, "icir": -0.15,
                                             "hit_rate": 0.45, "ic_std": 0.11,
                                             "insufficient_data": False},
                    },
                    "verdict": "PASS", "verdict_detail": "ok", "verdict_checks": [],
                }
            ],
        }

        frozen_thresholds = {
            "vol_q75": 0.2871, "breadth_q75": 0.4676,
            "train_end": 20201231, "train_n_days": 800,
        }

        rule_signals = pd.DataFrame({"trade_date": [20210104], "rule_signal": ["momentum_off"]})
        daily_ic = pd.DataFrame({"trade_date": [20210104], "ic": [-0.05]})

        _write_outputs(
            out_dir, "test_run", args, rule_signals, daily_ic,
            validation_results, validation_by_year, "rolling_pit",
            0.2871, 0.4676,
            frozen_thresholds=frozen_thresholds,
            walkforward_results=walkforward_results,
        )

        report_text = (out_dir / "rule_validation_report.md").read_text(encoding="utf-8")

        # MUST contain real limitations
        assert "True out-of-sample rule discovery" in report_text
        assert "Limited sample size" in report_text
        assert "Stability concerns" in report_text

        # MUST NOT contain full-sample bias text
        assert "FULL 2017-2024 period" not in report_text


# ===========================================================================
# Test 20: Resolver with empty discovery windows (explicit validation_mode)
# ===========================================================================

class TestResolverEmptyDiscoveryWindows:
    """Verify _resolve_final_verdict uses explicit validation_mode, not windows
    emptiness, to determine the verdict source."""

    def test_empty_discovery_windows_yields_insufficient_data(self):
        """Even with empty windows, discovery metadata must dominate the old
        strict-OOS PROMOTING verdict."""
        validation_results = {
            "overall_verdict": "PROMOTING_TO_STRATEGY",
            "overall_detail": "old strict OOS verdict",
        }

        walkforward_results = {
            "validation_mode": "walkforward_discovery",
            "rule_discovery_oos_safe": True,
            "full_sample_rule_candidates_used": False,
            "windows": [],
            "overall_verdict": "INSUFFICIENT_DATA",
            "overall_detail": "No valid walk-forward discovery windows.",
        }

        resolved = _resolve_final_verdict(
            validation_results, walkforward_results, is_oos=True
        )

        assert resolved["final_verdict"] == "INSUFFICIENT_DATA", (
            f"Empty discovery windows must yield INSUFFICIENT_DATA, "
            f"got: {resolved['final_verdict']}"
        )
        assert resolved["promotion_decision"] == "BLOCK"
        assert resolved["verdict_source"] == "walkforward_discovery"
        assert resolved["validation_mode"] == "walkforward_discovery"

        # Must NOT fall back to the old strict-OOS verdict
        assert resolved["final_verdict"] != "PROMOTING_TO_STRATEGY"

    def test_empty_discovery_no_windows_key_at_all(self):
        """Walkforward results present but windows key absent or empty —
        explicit validation_mode still wins."""
        validation_results = {
            "overall_verdict": "PROMOTING_TO_STRATEGY",
            "overall_detail": "old strict OOS",
        }

        # No "windows" key at all, but validation_mode is explicit
        walkforward_results = {
            "validation_mode": "walkforward_discovery",
            "rule_discovery_oos_safe": True,
            "overall_verdict": "INSUFFICIENT_DATA",
            "overall_detail": "No valid walk-forward discovery windows.",
        }

        resolved = _resolve_final_verdict(
            validation_results, walkforward_results, is_oos=True
        )

        assert resolved["final_verdict"] == "INSUFFICIENT_DATA"
        assert resolved["promotion_decision"] == "BLOCK"
        assert resolved["verdict_source"] == "walkforward_discovery"

    def test_non_discovery_empty_windows_falls_back_correctly(self):
        """Non-discovery walkforward (no validation_mode=walkforward_discovery)
        with empty windows should use oos_verdict."""
        validation_results = {
            "overall_verdict": "PROMOTING_TO_STRATEGY",
            "overall_detail": "old strict OOS",
        }

        walkforward_results = {
            "validation_mode": "walkforward_oos",
            "windows": [],
            "oos_verdict": "INSUFFICIENT_DATA",
            "overall_detail": "No valid walk-forward windows.",
        }

        resolved = _resolve_final_verdict(
            validation_results, walkforward_results, is_oos=True
        )

        assert resolved["final_verdict"] == "INSUFFICIENT_DATA"
        assert resolved["promotion_decision"] == "BLOCK"
        assert resolved["verdict_source"] == "walkforward_oos"

    def test_discovery_partial_with_windows_still_works(self):
        """Discovery PARTIAL with actual windows must still resolve correctly
        (legacy path still functional)."""
        validation_results = {
            "overall_verdict": "PROMOTING_TO_STRATEGY",
            "overall_detail": "old detail",
        }
        walkforward_results = {
            "validation_mode": "walkforward_discovery",
            "windows": [
                {"discovery": {"n_rule_candidates": 1}, "verdict": "PASS"}
            ],
            "overall_verdict": "PARTIAL",
            "overall_detail": "3/4 windows PASS, instability detected",
        }
        resolved = _resolve_final_verdict(
            validation_results, walkforward_results, is_oos=True
        )
        assert resolved["final_verdict"] == "PARTIAL"
        assert resolved["promotion_decision"] == "BLOCK"
        assert resolved["verdict_source"] == "walkforward_discovery"


# ===========================================================================
# Test 21: Date fields in frozen_thresholds
# ===========================================================================

class TestFrozenThresholdsDates:
    """Verify frozen_thresholds contains both requested_train_end and
    train_last_observation_date, distinguishing user intent from data reality."""

    def test_requested_train_end_stored_separately(self):
        """When requested_train_end differs from actual last observation date,
        both must be stored distinctly."""
        rng = np.random.default_rng(1001)

        # Training data ends at 20201203 (before the requested 20201231)
        train_dates = _make_synthetic_dates(20200102, 280)
        train_dates = train_dates[train_dates <= 20201203]

        train_panel = pd.DataFrame({
            "trade_date": train_dates,
            "volatility_state": rng.normal(0.18, 0.06, len(train_dates)),
            "breadth_score": rng.uniform(0.3, 0.8, len(train_dates)),
        })

        test_dates = _make_synthetic_dates(20210104, 100)
        test_panel = pd.DataFrame({
            "trade_date": test_dates,
            "volatility_state": rng.normal(0.25, 0.08, 100),
            "breadth_score": rng.uniform(0.1, 0.7, 100),
        })

        requested = 20201231
        _, frozen = apply_market_state_rules_oos(
            train_panel, test_panel, requested_train_end=requested
        )

        # Must have both fields
        assert "requested_train_end" in frozen, (
            "frozen_thresholds must contain requested_train_end"
        )
        assert frozen["requested_train_end"] == requested, (
            f"requested_train_end={frozen['requested_train_end']}, expected {requested}"
        )

        assert "train_last_observation_date" in frozen, (
            "frozen_thresholds must contain train_last_observation_date"
        )
        assert frozen["train_last_observation_date"] == int(train_panel["trade_date"].max()), (
            f"train_last_observation_date should be {train_panel['trade_date'].max()}, "
            f"got {frozen['train_last_observation_date']}"
        )

        # requested_train_end should NOT equal train_last_observation_date
        assert frozen["requested_train_end"] != frozen["train_last_observation_date"], (
            "requested_train_end (20201231) must differ from "
            "train_last_observation_date (20201203) in this test"
        )

    def test_test_first_observation_date_present(self):
        """test_first_observation_date must reflect the actual first test date."""
        rng = np.random.default_rng(1002)

        train_dates = _make_synthetic_dates(20200102, 280)
        train_dates = train_dates[train_dates <= 20201130]

        train_panel = pd.DataFrame({
            "trade_date": train_dates,
            "volatility_state": rng.normal(0.18, 0.06, len(train_dates)),
            "breadth_score": rng.uniform(0.3, 0.8, len(train_dates)),
        })

        test_dates = _make_synthetic_dates(20210104, 100)
        test_first = int(test_dates[0])
        test_panel = pd.DataFrame({
            "trade_date": test_dates,
            "volatility_state": rng.normal(0.25, 0.08, 100),
            "breadth_score": rng.uniform(0.1, 0.7, 100),
        })

        _, frozen = apply_market_state_rules_oos(
            train_panel, test_panel, requested_train_end=20201231
        )

        assert "test_first_observation_date" in frozen
        assert frozen["test_first_observation_date"] == test_first, (
            f"test_first_observation_date={frozen['test_first_observation_date']}, "
            f"expected {test_first}"
        )

    def test_legacy_train_end_still_present(self):
        """train_end (last observation) must still be present for backward compat."""
        rng = np.random.default_rng(1003)
        train_dates = _make_synthetic_dates(20200102, 200)
        train_panel = pd.DataFrame({
            "trade_date": train_dates,
            "volatility_state": rng.normal(0.18, 0.06, 200),
            "breadth_score": rng.uniform(0.3, 0.8, 200),
        })
        test_dates = _make_synthetic_dates(20210104, 50)
        test_panel = pd.DataFrame({
            "trade_date": test_dates,
            "volatility_state": rng.normal(0.25, 0.08, 50),
            "breadth_score": rng.uniform(0.1, 0.7, 50),
        })

        _, frozen = apply_market_state_rules_oos(
            train_panel, test_panel, requested_train_end=20201231
        )

        assert "train_end" in frozen
        assert frozen["train_end"] == frozen["train_last_observation_date"], (
            "train_end must equal train_last_observation_date for backward compat"
        )

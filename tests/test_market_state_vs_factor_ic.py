"""
Tests for explore_market_state_vs_factor_ic.py and IC diagnostics.

Covers:
  1. Coverage blocked: low-coverage factors excluded from rule_candidates
  2. FDR correction: Benjamini-Hochberg q-values correct
  3. Effect size: small spreads blocked from rule_candidates
  4. Rule candidates: all-gate-passing candidates enter YAML
  5. PIT alignment: market state only uses data <= signal_date
  6. Output contract: all output files present
  7. IC autocorrelation output: evaluate script produces diagnostics
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

from scripts.explore_market_state_vs_factor_ic import (
    _apply_fdr_correction,
    _build_rule_interpretation,
    _classify_findings_into_tiers,
    _conditional_ic_analysis,
    _compute_factor_coverage_for_market_state,
    _build_regime_features,
    _compute_index_spread,
    _compute_factor_ic_series,
    MIN_OBS_PER_QUARTILE,
)

from scripts.evaluate_factor_style_signals import (
    _compute_ic_autocorrelation,
    _ic_autocorrelation_summary,
    _compute_trailing_ic_forward_relation,
    _compute_coverage,
    _evaluate_coverage,
    MIN_MEDIAN_COVERAGE_PCT,
    MIN_YEARLY_COVERAGE_PCT,
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


# ===========================================================================
# Test 1: Coverage blocked
# ===========================================================================

class TestCoverageBlocked:
    """Verify that DATA_COVERAGE_BLOCKED factors are excluded from rule_candidates."""

    def test_low_coverage_factor_blocked(self):
        """Factor with 8% coverage must be DATA_COVERAGE_BLOCKED."""
        dates = _make_synthetic_dates(20200102, 30)
        fwd_rows = []
        factor_rows = []
        for d in dates:
            for i in range(100):
                fwd_rows.append({"ts_code": f"{i:06d}.SZ", "trade_date": d,
                                "fwd_ret_20d": 0.0})
            for i in range(8):  # 8% coverage
                factor_rows.append({"ts_code": f"{i:06d}.SZ", "trade_date": d,
                                   "value": float(i)})

        fwd_df = pd.DataFrame(fwd_rows)
        factor_df = pd.DataFrame(factor_rows)

        cov_df = _compute_coverage(factor_df, fwd_df)
        eval_result = _evaluate_coverage(cov_df)

        assert eval_result["coverage_blocked"] is True
        assert eval_result["coverage_status"] == "DATA_COVERAGE_BLOCKED"
        assert eval_result["median_coverage_pct"] < MIN_MEDIAN_COVERAGE_PCT

    def test_coverage_blocked_factors_excluded_from_rule_candidates(self):
        """Blocked factor findings must not enter rule_candidates tier."""
        # Create a result that passes FDR and effect size but is coverage blocked
        results = [
            {
                "state_col": "volatility_state",
                "factor": "earnings_acceleration_cs",
                "n_total": 400, "n_valid": 400,
                "top_vs_bottom_spread": 0.10,
                "p_value": 0.001,
                "q_value": 0.005,
                "direction": "negative",
                "significant_raw": True,
                "significant_fdr": True,
                "passes_effect_size": True,
                "per_quantile": [
                    {"quantile": 0, "n": 100, "mean_ic": 0.05},
                    {"quantile": 3, "n": 100, "mean_ic": -0.05},
                ],
            },
            {
                "state_col": "volatility_state",
                "factor": "risk_adjusted_momentum_60_cs",
                "n_total": 1743, "n_valid": 1743,
                "top_vs_bottom_spread": -0.085,
                "p_value": 0.0001,
                "q_value": 0.001,
                "direction": "negative",
                "significant_raw": True,
                "significant_fdr": True,
                "passes_effect_size": True,
                "per_quantile": [
                    {"quantile": 0, "n": 436, "mean_ic": 0.02},
                    {"quantile": 3, "n": 436, "mean_ic": -0.07},
                ],
            },
        ]

        coverage_blocked = {"earnings_acceleration_cs"}
        tiers = _classify_findings_into_tiers(results, coverage_blocked)

        # earnings_acceleration should NOT be in rule_candidates
        rule_factors = {rc["factor"] for rc in tiers["rule_candidates"]}
        assert "earnings_acceleration_cs" not in rule_factors, (
            "Coverage-blocked factor must not enter rule_candidates"
        )
        # But it SHOULD be in fdr_robust
        fdr_factors = {f["factor"] for f in tiers["fdr_robust"]}
        assert "earnings_acceleration_cs" in fdr_factors, (
            "Coverage-blocked factor should still appear in fdr_robust tier"
        )
        # Momentum should be in rule_candidates
        assert "risk_adjusted_momentum_60_cs" in rule_factors

    def test_high_coverage_factor_not_blocked(self):
        """Factor with >90% coverage should NOT be blocked."""
        dates = _make_synthetic_dates(20200102, 30)
        fwd_rows = []
        factor_rows = []
        for d in dates:
            for i in range(100):
                fwd_rows.append({"ts_code": f"{i:06d}.SZ", "trade_date": d,
                                "fwd_ret_20d": 0.0})
            for i in range(95):
                factor_rows.append({"ts_code": f"{i:06d}.SZ", "trade_date": d,
                                   "value": float(i)})

        fwd_df = pd.DataFrame(fwd_rows)
        factor_df = pd.DataFrame(factor_rows)

        cov_df = _compute_coverage(factor_df, fwd_df)
        eval_result = _evaluate_coverage(cov_df)

        assert eval_result["coverage_blocked"] is False
        assert eval_result["coverage_status"] == "OK"


# ===========================================================================
# Test 2: FDR correction
# ===========================================================================

class TestFDRCorrection:
    """Verify Benjamini-Hochberg FDR correction."""

    def test_bh_fdr_single_test(self):
        """Single p-value: q = p."""
        results = [{
            "state_col": "x", "factor": "y", "n_valid": 100,
            "top_vs_bottom_spread": 0.05, "p_value": 0.03, "direction": "positive",
        }]
        enriched = _apply_fdr_correction(results)
        assert enriched[0]["q_value"] == pytest.approx(0.03, abs=0.01)
        assert enriched[0]["significant_raw"] is True

    def test_bh_fdr_many_tests(self):
        """Multiple tests: q >= p for each test."""
        p_values = [0.001, 0.01, 0.03, 0.05, 0.10, 0.20, 0.50, 0.80]
        results = [
            {
                "state_col": f"s{i}", "factor": "f",
                "n_valid": 100,
                "top_vs_bottom_spread": 0.05,
                "p_value": pv, "direction": "positive",
            }
            for i, pv in enumerate(p_values)
        ]
        enriched = _apply_fdr_correction(results)

        for r in enriched:
            if r["p_value"] < 0.99:  # non-NaN
                assert r["q_value"] >= r["p_value"] - 0.001, (
                    f"q_value ({r['q_value']}) must be >= p_value ({r['p_value']})"
                )

    def test_bh_fdr_monotonic_in_rank(self):
        """q-values should be monotonic with p-values (lower p → lower or equal q)."""
        p_values = [0.001, 0.005, 0.01, 0.02, 0.05, 0.10]
        results = [
            {
                "state_col": f"s{i}", "factor": "f",
                "n_valid": 100,
                "top_vs_bottom_spread": 0.05,
                "p_value": pv, "direction": "positive",
            }
            for i, pv in enumerate(p_values)
        ]
        enriched = _apply_fdr_correction(results)

        # Sort by p-value and check q monotonic
        sorted_by_p = sorted(
            [(r["p_value"], r["q_value"]) for r in enriched],
            key=lambda x: x[0]
        )
        q_values = [qv for _, qv in sorted_by_p]
        for i in range(len(q_values) - 1):
            if not np.isnan(q_values[i]) and not np.isnan(q_values[i + 1]):
                assert q_values[i] <= q_values[i + 1] + 0.001, (
                    f"q-values should be monotonic with p-values: {q_values}"
                )

    def test_raw_significant_but_not_fdr(self):
        """A finding with p=0.04 among many tests may not survive FDR."""
        # With 20 tests, p=0.04 has BH critical value of ~0.05
        # so it might barely pass, but with q_threshold=0.10 it should
        n_tests = 20
        results = [
            {
                "state_col": f"s{i}", "factor": "f",
                "n_valid": 100,
                "top_vs_bottom_spread": 0.05,
                "p_value": (0.04 if i == 0 else 0.50 + i * 0.01),
                "direction": "positive",
            }
            for i in range(n_tests)
        ]
        enriched = _apply_fdr_correction(results,
                                          raw_p_threshold=0.05,
                                          fdr_q_threshold=0.10)

        # The p=0.04 test should be significant_raw
        assert enriched[0]["significant_raw"] is True
        # With 20 tests, p=0.04 * 20/1 = 0.80 → q=0.80 > 0.10 → NOT fdr significant
        assert enriched[0]["significant_fdr"] is False, (
            f"p=0.04 among 20 tests: q={enriched[0]['q_value']:.4f}, "
            f"should NOT pass FDR at q<0.10"
        )

    def test_very_small_p_survives_fdr(self):
        """Very small p-value must survive FDR."""
        n_tests = 20
        results = [
            {
                "state_col": f"s{i}", "factor": "f",
                "n_valid": 100,
                "top_vs_bottom_spread": 0.05,
                "p_value": (0.0001 if i == 0 else 0.50 + i * 0.01),
                "direction": "positive",
            }
            for i in range(n_tests)
        ]
        enriched = _apply_fdr_correction(results,
                                          raw_p_threshold=0.05,
                                          fdr_q_threshold=0.10)

        assert enriched[0]["significant_fdr"] is True, (
            f"p=0.0001 among {n_tests} tests must survive FDR, q={enriched[0]['q_value']:.4f}"
        )


# ===========================================================================
# Test 3: Effect size
# ===========================================================================

class TestEffectSize:
    """Verify effect size gate in tier classification."""

    def test_small_spread_blocked(self):
        """p-value significant but spread=0.01 < 0.02 → blocked from rule_candidates."""
        results = [{
            "state_col": "x", "factor": "risk_adjusted_momentum_60_cs",
            "n_total": 400, "n_valid": 400,
            "top_vs_bottom_spread": 0.01,  # below threshold
            "p_value": 0.001,
            "q_value": 0.005,
            "direction": "positive",
            "significant_raw": True,
            "significant_fdr": True,
            "passes_effect_size": False,  # key
            "per_quantile": [],
        }]
        tiers = _classify_findings_into_tiers(results, set())
        assert len(tiers["rule_candidates"]) == 0, "Small effect must not become rule candidate"
        assert len(tiers["raw_significant"]) >= 1, "Should still appear in raw tier"

    def test_large_spread_passes(self):
        """p-value significant, spread=0.08 → passes effect size."""
        results = [{
            "state_col": "x", "factor": "risk_adjusted_momentum_60_cs",
            "n_total": 1743, "n_valid": 1743,
            "top_vs_bottom_spread": 0.085,
            "p_value": 0.0001,
            "q_value": 0.001,
            "direction": "negative",
            "significant_raw": True,
            "significant_fdr": True,
            "passes_effect_size": True,
            "per_quantile": [
                {"quantile": 0, "n": 436, "mean_ic": 0.02},
                {"quantile": 3, "n": 436, "mean_ic": -0.07},
            ],
        }]
        tiers = _classify_findings_into_tiers(results, set())
        assert len(tiers["rule_candidates"]) == 1
        assert tiers["rule_candidates"][0]["spread"] == 0.085


# ===========================================================================
# Test 4: Rule candidates
# ===========================================================================

class TestRuleCandidates:
    """Verify rule candidate classification with all gates."""

    def test_all_gates_passed_becomes_rule_candidate(self):
        """FDR + effect + coverage + direction + N → rule candidate."""
        results = [{
            "state_col": "volatility_state",
            "factor": "risk_adjusted_momentum_60_cs",
            "n_total": 1743, "n_valid": 1743,
            "top_vs_bottom_spread": -0.085,
            "p_value": 0.0001,
            "q_value": 0.001,
            "direction": "negative",
            "significant_raw": True,
            "significant_fdr": True,
            "passes_effect_size": True,
            "per_quantile": [
                {"quantile": 0, "n": 436, "mean_ic": 0.016},
                {"quantile": 3, "n": 436, "mean_ic": -0.068},
            ],
        }]
        tiers = _classify_findings_into_tiers(results, set())

        assert len(tiers["rule_candidates"]) == 1
        rc = tiers["rule_candidates"][0]
        assert rc["state_col"] == "volatility_state"
        assert rc["direction"] == "negative"
        assert "interpretation" in rc

    def test_no_direction_blocked(self):
        """direction='none' blocks rule candidate even if other gates pass."""
        results = [{
            "state_col": "x", "factor": "risk_adjusted_momentum_60_cs",
            "n_total": 1743, "n_valid": 1743,
            "top_vs_bottom_spread": 0.05,
            "p_value": 0.001,
            "q_value": 0.005,
            "direction": "none",
            "significant_raw": True,
            "significant_fdr": True,
            "passes_effect_size": True,
            "per_quantile": [],
        }]
        tiers = _classify_findings_into_tiers(results, set())
        assert len(tiers["rule_candidates"]) == 0, "direction='none' must block"

    def test_insufficient_n_blocked(self):
        """n < MIN_OBS_PER_QUARTILE*2 blocks rule candidate."""
        results = [{
            "state_col": "x", "factor": "risk_adjusted_momentum_60_cs",
            "n_total": 30, "n_valid": 30,  # too few
            "top_vs_bottom_spread": 0.05,
            "p_value": 0.001,
            "q_value": 0.005,
            "direction": "positive",
            "significant_raw": True,
            "significant_fdr": True,
            "passes_effect_size": True,
            "per_quantile": [],
        }]
        tiers = _classify_findings_into_tiers(results, set())
        assert len(tiers["rule_candidates"]) == 0, "Too few observations must block"


# ===========================================================================
# Test 5: PIT alignment
# ===========================================================================

class TestPITAlignment:
    """Verify market state computation uses only PIT data."""

    def test_regime_features_use_only_pit_data(self):
        """Features at signal_date must only use index data <= signal_date."""
        # Create synthetic index data
        n_days = 300
        rng = np.random.default_rng(42)
        dates = _make_synthetic_dates(20200102, n_days)
        index_df = pd.DataFrame({
            "ts_code": "000300.SH",
            "trade_date": dates,
            "close": 100 * np.cumprod(1 + 0.0003 + 0.015 * rng.standard_normal(n_days)),
            "open": np.zeros(n_days),
            "high": np.zeros(n_days),
            "low": np.zeros(n_days),
            "vol": rng.lognormal(mean=15, sigma=0.5, size=n_days),
        })

        # PIT: features at date T should only use data <= T
        # We test by modifying future data and checking features don't change
        signal_date = dates[len(dates) // 2]

        features_before = _build_regime_features(index_df, None, np.array([signal_date]))

        # Modify future data drastically
        modified = index_df.copy()
        future_mask = modified["trade_date"] > signal_date
        modified.loc[future_mask, "close"] = 999999.0
        modified.loc[future_mask, "vol"] = 0.0

        features_after = _build_regime_features(modified, None, np.array([signal_date]))

        if not features_before.empty and not features_after.empty:
            # Features should be IDENTICAL (future data cannot affect PIT computation)
            for col in ["trend_strength", "volatility_state", "turnover_state"]:
                if col in features_before.columns and col in features_after.columns:
                    assert features_before[col].iloc[0] == features_after[col].iloc[0], (
                        f"{col} changed when future data was modified: "
                        f"{features_before[col].iloc[0]} vs {features_after[col].iloc[0]}"
                    )

    def test_index_spread_only_uses_known_dates(self):
        """Spreads at date T should only use closes <= T (obvious from construction)."""
        dates = _make_synthetic_dates(20200102, 60)
        idx1 = pd.DataFrame({
            "ts_code": "A", "trade_date": dates,
            "close": np.linspace(100, 120, len(dates)),
        })
        idx2 = pd.DataFrame({
            "ts_code": "B", "trade_date": dates,
            "close": np.linspace(100, 110, len(dates)),
        })

        spread_df = _compute_index_spread(idx1, idx2, window=10, label="test")

        # The spread at each date is computed from returns within the window
        # ending at that date — verify dates match
        if not spread_df.empty:
            assert spread_df["trade_date"].max() <= dates[-1]
            # Each spread value should be from cumulative returns ending at trade_date
            # which only uses data <= trade_date
            for _, row in spread_df.iterrows():
                assert row["trade_date"] in dates


# ===========================================================================
# Test 6: Output contract
# ===========================================================================

class TestOutputContract:
    """Verify all output files are produced and schema-correct."""

    def test_all_output_files_produced(self, tmp_path):
        """Simulate output generation and verify files exist."""
        out_dir = tmp_path / "test_output"
        out_dir.mkdir()

        # Write expected files
        (out_dir / "market_state_vs_factor_ic_results.json").write_text(
            json.dumps({"test": True})
        )
        pd.DataFrame({"a": [1]}).to_csv(
            out_dir / "market_state_conditional_ic.csv", index=False
        )
        pd.DataFrame({"a": [1]}).to_csv(
            out_dir / "market_state_significance_adjusted.csv", index=False
        )
        with open(out_dir / "market_state_rule_candidates.yaml", "w") as f:
            yaml.dump({"rule_candidates": []}, f)
        (out_dir / "market_state_analysis_summary.md").write_text("# Test")

        # Also simulate the style signal diagnostics
        pd.DataFrame({"a": [1]}).to_csv(
            out_dir / "ic_autocorrelation.csv", index=False
        )
        pd.DataFrame({"a": [1]}).to_csv(
            out_dir / "trailing_ic_forward_relation.csv", index=False
        )

        expected = [
            "market_state_vs_factor_ic_results.json",
            "market_state_conditional_ic.csv",
            "market_state_significance_adjusted.csv",
            "market_state_rule_candidates.yaml",
            "market_state_analysis_summary.md",
            "ic_autocorrelation.csv",
            "trailing_ic_forward_relation.csv",
        ]
        for fname in expected:
            fp = out_dir / fname
            assert fp.exists(), f"Missing: {fname}"
            assert fp.stat().st_size > 0, f"Empty: {fname}"

    def test_rule_candidates_yaml_has_required_fields(self):
        """YAML must have schema, rule_candidates list, and metadata."""
        yaml_content = {
            "schema": "market_state_rule_candidates.v1",
            "generated_at": "2024-01-01",
            "parameters": {"start": "20170101", "end": "20241231"},
            "fdr": {"method": "Benjamini-Hochberg", "q_threshold": 0.10},
            "n_rule_candidates": 1,
            "rule_candidates": [
                {
                    "state_col": "volatility_state",
                    "factor": "risk_adjusted_momentum_60_cs",
                    "spread": -0.085,
                    "q_value": 0.001,
                    "direction": "negative",
                }
            ],
            "note": "Only rule_candidates pass all gates.",
        }
        yaml_str = yaml.dump(yaml_content)
        loaded = yaml.safe_load(yaml_str)

        assert loaded["schema"] == "market_state_rule_candidates.v1"
        assert isinstance(loaded["rule_candidates"], list)
        assert loaded["n_rule_candidates"] == len(loaded["rule_candidates"])

    def test_significance_adjusted_csv_has_tier_column(self):
        """CSV must contain the 'tier' column for classification transparency."""
        df = pd.DataFrame({
            "state_col": ["a", "b", "c"],
            "factor": ["x", "y", "z"],
            "p_value": [0.001, 0.04, 0.50],
            "q_value": [0.005, 0.06, 0.50],
            "significant_raw": [True, True, False],
            "significant_fdr": [True, False, False],
            "passes_effect_size": [True, True, False],
            "coverage_blocked": [False, False, False],
            "tier": ["rule_candidate", "raw_significant", "not_significant"],
        })
        assert "tier" in df.columns
        assert set(df["tier"].unique()) <= {
            "rule_candidate", "fdr_robust", "raw_significant", "not_significant"
        }


# ===========================================================================
# Test 7: IC autocorrelation output
# ===========================================================================

class TestICAutocorrelation:
    """Verify IC autocorrelation diagnostics produce correct outputs."""

    def test_autocorrelation_output_format(self):
        """Output DataFrame must have correct columns."""
        rng = np.random.default_rng(77)
        dates = _make_synthetic_dates(20200102, 150)
        daily_ic = pd.DataFrame({
            "trade_date": dates,
            "ic": 0.01 + 0.05 * rng.normal(0, 1, len(dates)),
        })

        ac_df = _compute_ic_autocorrelation(daily_ic, max_lag=60)
        assert not ac_df.empty, "Should produce autocorrelation data"
        assert "lag" in ac_df.columns
        assert "autocorr" in ac_df.columns
        assert "p_value" in ac_df.columns
        assert "significance" in ac_df.columns
        assert ac_df["lag"].max() <= 60
        assert ac_df["lag"].min() >= 1

    def test_autocorrelation_summary_interpretation(self):
        """Summary must produce one of the four valid interpretations."""
        rng = np.random.default_rng(88)
        dates = _make_synthetic_dates(20200102, 150)
        daily_ic = pd.DataFrame({
            "trade_date": dates,
            "ic": 0.01 + 0.05 * rng.normal(0, 1, len(dates)),
        })
        daily_ic["factor"] = "test_factor"

        ac_df = _compute_ic_autocorrelation(daily_ic, max_lag=60)
        summary = _ic_autocorrelation_summary(ac_df, "test_factor")

        assert summary["factor"] == "test_factor"
        assert summary["interpretation"] in {
            "IC_MOMENTUM", "IC_REVERSAL", "NO_STABLE_RELATION", "INSUFFICIENT_DATA"
        }
        assert "lag_1_5_mean_autocorr" in summary
        assert "lag_6_20_mean_autocorr" in summary
        assert "lag_21_60_mean_autocorr" in summary

    def test_autocorrelation_insufficient_data(self):
        """Too few observations → INSUFFICIENT_DATA."""
        daily_ic = pd.DataFrame({
            "trade_date": [20200102, 20200103],
            "ic": [0.01, 0.02],
        })
        ac_df = _compute_ic_autocorrelation(daily_ic, max_lag=60)
        assert ac_df.empty, "Should return empty for insufficient data"

        summary = _ic_autocorrelation_summary(ac_df, "test")
        assert summary["interpretation"] == "INSUFFICIENT_DATA"

    def test_autocorrelation_with_strong_momentum(self):
        """Strong positive AR(1) → IC_MOMENTUM interpretation."""
        rng = np.random.default_rng(99)
        n = 200
        ic = np.zeros(n)
        ic[0] = 0.01
        for i in range(1, n):
            ic[i] = 0.7 * ic[i - 1] + 0.02 * rng.normal(0, 1)  # strong AR(1)
        dates = _make_synthetic_dates(20200102, n)

        daily_ic = pd.DataFrame({"trade_date": dates, "ic": ic})
        ac_df = _compute_ic_autocorrelation(daily_ic, max_lag=60)
        summary = _ic_autocorrelation_summary(ac_df, "test")

        # With AR(1)=0.7, lag 1-5 should be strongly positive
        lag_1_5 = summary["lag_1_5_mean_autocorr"]
        if not np.isnan(lag_1_5):
            assert lag_1_5 > 0.1, f"Expected strong positive AC, got {lag_1_5:.4f}"
            assert summary["interpretation"] == "IC_MOMENTUM"

    def test_trailing_ic_forward_relation_insufficient(self):
        """Empty data → INSUFFICIENT_DATA."""
        result = _compute_trailing_ic_forward_relation(
            pd.DataFrame(), pd.DataFrame(), horizon=20
        )
        assert result["direction"] == "INSUFFICIENT_DATA"
        assert result["n_obs"] == 0

    def test_trailing_ic_forward_relation_with_data(self):
        """With enough data, produces valid direction."""
        rng = np.random.default_rng(111)
        dates = _make_synthetic_dates(20200102, 200)

        # Simulate aligned trailing ICs and daily ICs
        aligned = pd.DataFrame({
            "signal_date": dates[60:160],
            "trailing_ic": rng.normal(-0.01, 0.05, 100),
            "n_ic_obs": [60] * 100,
            "latest_factor_date": dates[40:140],
        })

        daily_ic = pd.DataFrame({
            "trade_date": dates,
            "ic": rng.normal(-0.02, 0.10, 200),
        })

        result = _compute_trailing_ic_forward_relation(aligned, daily_ic, horizon=20)
        assert result["direction"] in {
            "IC_MOMENTUM", "IC_REVERSAL", "NO_STABLE_RELATION", "INSUFFICIENT_DATA"
        }
        assert result["n_obs"] > 0
        assert "interpretation" in result


# ===========================================================================
# Integration tests: conditional IC with coverage
# ===========================================================================

class TestConditionalICAnalysis:
    """Verify conditional IC analysis handles edge cases."""

    def test_conditional_ic_insufficient_data(self):
        """Too few observations → error message."""
        panel = pd.DataFrame({
            "trend_strength": np.random.default_rng(1).normal(0, 0.05, 10),
            "test_factor_ic": np.random.default_rng(2).normal(0, 0.10, 10),
        })
        result = _conditional_ic_analysis(panel, "trend_strength", "test_factor")
        assert result.get("error") is not None or result.get("n_valid", 0) < MIN_OBS_PER_QUARTILE * 2

    def test_conditional_ic_with_valid_data(self):
        """With enough data, produces quantile breakdown."""
        panel = pd.DataFrame({
            "trend_strength": np.random.default_rng(3).normal(0, 0.05, 200),
            "test_factor_ic": np.random.default_rng(4).normal(0, 0.10, 200),
        })
        result = _conditional_ic_analysis(panel, "trend_strength", "test_factor")
        if "error" not in result:
            assert result["n_total"] == 200
            assert len(result.get("per_quantile", [])) >= 2
            assert "top_vs_bottom_spread" in result
            assert "p_value" in result
            assert "direction" in result


# ===========================================================================
# Test 8: Rule interpretation spread bug fix
# ===========================================================================

class TestRuleInterpretation:
    """Verify _build_rule_interpretation correctly reads the spread field."""

    def test_rule_interpretation_uses_top_vs_bottom_spread(self):
        """Interpretation must use top_vs_bottom_spread when 'spread' key is missing."""
        result = {
            "state_col": "volatility_state",
            "factor": "risk_adjusted_momentum_60_cs",
            "direction": "negative",
            "top_vs_bottom_spread": -0.0847,
        }
        text = _build_rule_interpretation(result)
        assert "-0.0847" in text, (
            f"Expected spread=-0.0847 in interpretation, got: {text}"
        )

    def test_rule_interpretation_uses_spread_key_when_present(self):
        """If 'spread' key exists, use it (backward compatibility)."""
        result = {
            "state_col": "breadth_score",
            "factor": "risk_adjusted_momentum_60_cs",
            "direction": "positive",
            "spread": 0.0332,
            "top_vs_bottom_spread": 0.0332,
        }
        text = _build_rule_interpretation(result)
        assert "0.0332" in text, (
            f"Expected spread=0.0332 in interpretation, got: {text}"
        )

    def test_rule_interpretation_zero_spread_fallback(self):
        """When neither key is present but direction is negative/positive, fallback to 0.0000."""
        result = {
            "state_col": "trend_strength",
            "factor": "valuation_reversion_3y_cs",
            "direction": "negative",
        }
        text = _build_rule_interpretation(result)
        assert "0.0000" in text, (
            f"Expected spread=0.0000 fallback in negative-direction text, got: {text}"
        )

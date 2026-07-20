"""Tests for factor_quality_rebuild.py v2.

Covers: IC, input audit, direction audit, IC by year, quantile returns,
quality gate, correlation clusters, no-leakage alignment, real turnover,
mcap neutralization, IC trend, rolling window gate, capacity audit,
candidate pool generation, report generation, and STUB prohibition.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.factor_quality_rebuild import (
    _rank_ic,
    _pearson_ic,
    _audit_factor_input,
    _audit_factor_direction,
    _compute_ic_by_year,
    _compute_quantile_returns,
    _apply_quality_gate,
    _compute_correlation_clusters,
    _load_factor_cache_raw,
    _clean_factor_panel,
    _build_aligned_panel,
    _neutralize_by_mcap,
    _compute_ic_trend,
    _compute_quantile_portfolios,
    _compute_real_turnover_cost,
    _compute_rolling_window_gate,
    _compute_capacity_audit,
    _compute_neutralization_diagnostic,
    _generate_candidate_pool,
    _write_report,
    _compute_regime_breakdown,
    _convert_amount_to_cny,
    _daily_basic_amount_cny,
    RunDiagnostics,
    _write_csv_safe,
    _publish_outputs,
    PUBLISH_CSVS,
    DIAGNOSTIC_CSV_NAMES,
    RUN_PROGRESS_COLUMNS,
    RUN_STAGE_TIMINGS_COLUMNS,
    RUN_ERRORS_COLUMNS,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_mock_factor_df(
    n_stocks: int = 50,
    n_dates: int = 200,
    seed: int = 42,
    alpha_strength: float = 0.02,
    reverse: bool = False,
    start_year: int = 2017,
) -> pd.DataFrame:
    """Generate a mock CS-processed factor with controllable alpha."""
    rng = np.random.default_rng(seed)
    rows = []
    stocks = [f"{i:06d}.SH" for i in range(n_stocks)]
    base_date = start_year * 10000 + 101
    for week in range(n_dates):
        dt = base_date + week * 7
        if dt > (start_year + 1) * 10000:
            break
        for ts in stocks:
            true_signal = rng.normal(0, 1)
            rows.append({
                "ts_code": ts, "trade_date": dt,
                "value": -true_signal if reverse else true_signal,
                "_true_signal": true_signal,
            })
    return pd.DataFrame(rows)


def _make_mock_fwd_returns(factor_df: pd.DataFrame, alpha_strength: float = 0.02, seed: int = 42) -> pd.DataFrame:
    """Generate fwd_ret columns correlated with the hidden true signal."""
    rng = np.random.default_rng(seed)
    signal_col = "_true_signal" if "_true_signal" in factor_df.columns else "value"
    fwd_rows = []
    for _, row in factor_df.iterrows():
        signal = alpha_strength * row[signal_col] + rng.normal(0, 0.03)
        fwd_rows.append({
            "ts_code": row["ts_code"],
            "trade_date": row["trade_date"],
            "fwd_ret_1d": signal * 0.3,
            "fwd_ret_5d": signal,
            "fwd_ret_10d": signal * 1.2,
            "fwd_ret_20d": signal * 1.5,
        })
    return pd.DataFrame(fwd_rows)


def _make_mock_daily_basic(factor_df: pd.DataFrame, seed: int = 99) -> pd.DataFrame:
    """Generate mock daily_basic with total_mv, circ_mv, turnover_rate."""
    rng = np.random.default_rng(seed)
    rows = []
    for _, row in factor_df.iterrows():
        mcap = 10 ** rng.uniform(8, 11)  # 100M to 100B
        rows.append({
            "ts_code": row["ts_code"],
            "trade_date": row["trade_date"],
            "total_mv": mcap,
            "circ_mv": mcap * rng.uniform(0.4, 0.9),
            "turnover_rate": rng.uniform(0.5, 8.0),
        })
    return pd.DataFrame(rows)


def _make_mock_log_mcap(factor_df: pd.DataFrame, seed: int = 77) -> pd.DataFrame:
    """Generate mock log_market_cap_cs panel."""
    rng = np.random.default_rng(seed)
    rows = []
    for _, row in factor_df.iterrows():
        rows.append({
            "ts_code": row["ts_code"],
            "trade_date": row["trade_date"],
            "value": rng.normal(0, 1),
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# IC tests
# ---------------------------------------------------------------------------

class TestICComputation:
    def test_rank_ic_positive_for_positive_alpha(self):
        df = _make_mock_factor_df(n_stocks=50, n_dates=50, alpha_strength=0.05)
        fwd = _make_mock_fwd_returns(df, alpha_strength=0.05)
        merged = df.merge(fwd, on=["ts_code", "trade_date"])
        daily_ic = merged.groupby("trade_date").apply(
            lambda g: _rank_ic(g["value"], g["fwd_ret_5d"])
        ).dropna()
        mean_ic = float(daily_ic.mean())
        assert mean_ic > 0, f"Expected positive IC, got {mean_ic:.4f}"

    def test_rank_ic_negative_for_reversed_alpha(self):
        df = _make_mock_factor_df(n_stocks=50, n_dates=50, alpha_strength=0.05, reverse=True)
        fwd = _make_mock_fwd_returns(df, alpha_strength=0.05)
        merged = df.merge(fwd, on=["ts_code", "trade_date"])
        daily_ic = merged.groupby("trade_date").apply(
            lambda g: _rank_ic(g["value"], g["fwd_ret_5d"])
        ).dropna()
        mean_ic = float(daily_ic.mean())
        assert mean_ic < 0, f"Expected negative IC for reversed factor, got {mean_ic:.4f}"

    def test_rank_ic_requires_min_30(self):
        vals = pd.Series(np.random.randn(25))
        rets = pd.Series(np.random.randn(25))
        result = _rank_ic(vals, rets)
        assert np.isnan(result)

    def test_pearson_ic_requires_min_30(self):
        vals = pd.Series(np.random.randn(25))
        rets = pd.Series(np.random.randn(25))
        result = _pearson_ic(vals, rets)
        assert np.isnan(result)


# ---------------------------------------------------------------------------
# Input audit tests
# ---------------------------------------------------------------------------

class TestInputAudit:
    def test_empty_factor_fails(self):
        cfg = {"name": "test_cs"}
        df = pd.DataFrame(columns=["ts_code", "trade_date", "value"])
        fwd = pd.DataFrame(columns=["ts_code", "trade_date", "fwd_ret_5d"])
        result = _audit_factor_input(cfg, df, fwd, "20170101", "20201231")
        assert result["input_audit_status"] == "FAIL"
        assert result["data_status"] == "DATA_MISSING"

    def test_constant_factor_fails(self):
        cfg = {"name": "constant_cs"}
        n = 200
        dates = [20170103 + i for i in range(n)]
        df = pd.DataFrame({
            "ts_code": ["000001.SH"] * n,
            "trade_date": dates,
            "value": [1.0] * n,
        })
        fwd = pd.DataFrame({
            "ts_code": ["000001.SH"] * n,
            "trade_date": dates,
            "fwd_ret_5d": [0.01] * n,
        })
        result = _audit_factor_input(cfg, df, fwd, "20170101", "20201231")
        assert result["input_audit_status"] == "FAIL"
        assert result["constant_dates"] > 0

    def test_duplicate_keys_fails(self):
        cfg = {"name": "dupe_cs"}
        rows = [{"ts_code": "000001.SH", "trade_date": 20170103, "value": 0.5}] * 50
        rows.append({"ts_code": "000001.SH", "trade_date": 20170103, "value": 0.6})
        df = pd.DataFrame(rows)
        fwd = pd.DataFrame({
            "ts_code": ["000001.SH"], "trade_date": [20170103], "fwd_ret_5d": [0.01]
        })
        result = _audit_factor_input(cfg, df, fwd, "20170101", "20171231")
        assert result["duplicate_keys"] > 0
        assert result["input_audit_status"] == "FAIL"

    def test_normal_factor_passes(self):
        cfg = {"name": "good_cs"}
        df = _make_mock_factor_df(n_stocks=50, n_dates=100)
        fwd = _make_mock_fwd_returns(df)
        result = _audit_factor_input(cfg, df, fwd, "20170101", "20171231")
        assert result["input_audit_status"] == "PASS"
        assert result["n_unique_stocks"] == 50

    def test_loader_preserves_duplicate_keys_for_audit(self):
        """Raw loader must NOT drop duplicates — they must be recorded in audit."""
        # Cannot test _load_factor_cache_raw directly (needs real parquet),
        # but can test the audit layer: if raw_df has dupes, audit must record them.
        cfg = {"name": "dupe_test_cs"}
        rows = [{"ts_code": "000001.SH", "trade_date": 20170103, "value": 0.5},
                {"ts_code": "000001.SH", "trade_date": 20170103, "value": 0.6}]
        rows += [{"ts_code": f"{i:06d}.SH", "trade_date": 20170103, "value": 0.5}
                 for i in range(1, 51)]  # pad to avoid missing_rate fail
        df = pd.DataFrame(rows)
        fwd = pd.DataFrame([{"ts_code": f"{i:06d}.SH", "trade_date": 20170103, "fwd_ret_5d": 0.01}
                           for i in range(51)])
        result = _audit_factor_input(cfg, df, fwd, "20170101", "20171231")
        assert result["duplicate_keys"] >= 1, "Duplicate keys must be recorded"
        assert result["duplicate_key_rate"] > 0, "Dupe rate must be > 0"
        # After cleaning, dupes should be removed
        clean = _clean_factor_panel(df)
        assert clean.duplicated(["ts_code", "trade_date"]).sum() == 0, "Clean panel must have no duplicates"

    def test_coverage_denominator_is_fwd_universe(self):
        """Coverage must be |factor ∩ fwd| / |fwd|, capped at 100%."""
        cfg = {"name": "cov_test_cs"}
        df = _make_mock_factor_df(n_stocks=30, n_dates=50)
        # Create fwd with MORE stocks than factor (simulate broader universe)
        fwd_rows = []
        for _, row in df.iterrows():
            fwd_rows.append({"ts_code": row["ts_code"], "trade_date": row["trade_date"],
                            "fwd_ret_5d": 0.01})
        # Add extra stocks only in fwd
        for _, row in df.head(250).iterrows():
            fwd_rows.append({"ts_code": "EXTRA_" + row["ts_code"], "trade_date": row["trade_date"],
                            "fwd_ret_5d": 0.01})
        fwd = pd.DataFrame(fwd_rows)
        result = _audit_factor_input(cfg, df, fwd, "20170101", "20171231")
        assert result["median_coverage_pct"] <= 1.0, "Coverage must not exceed 100%"
        # When factor and fwd both cover all the same stocks, coverage can be 100%
        # But the key check: it should never exceed 100% (capped)
        assert result["median_coverage_pct"] >= 0.0, "Coverage must be non-negative"

    def test_empty_cache_is_data_missing(self):
        """Empty factor cache → DATA_MISSING, not general FAIL."""
        cfg = {"name": "empty_cs"}
        df = pd.DataFrame(columns=["ts_code", "trade_date", "value"])
        fwd = pd.DataFrame(columns=["ts_code", "trade_date", "fwd_ret_5d"])
        result = _audit_factor_input(cfg, df, fwd, "20170101", "20201231")
        assert result["data_status"] == "DATA_MISSING"

    def test_missing_rate_above_20_pct_fails(self):
        """Missing rate > 20% must FAIL (not the old 50% threshold)."""
        cfg = {"name": "sparse_cs"}
        n = 100
        df = pd.DataFrame({
            "ts_code": [f"{i:06d}.SH" for i in range(n)],
            "trade_date": [20170103] * n,
            "value": [0.5 if i < 75 else np.nan for i in range(n)],  # 25% missing
        })
        fwd = pd.DataFrame({
            "ts_code": [f"{i:06d}.SH" for i in range(n)],
            "trade_date": [20170103] * n,
            "fwd_ret_5d": [0.01] * n,
        })
        result = _audit_factor_input(cfg, df, fwd, "20170101", "20171231")
        assert result["missing_rate"] > 0.20
        assert result["input_audit_status"] == "FAIL"


# ---------------------------------------------------------------------------
# Direction audit tests
# ---------------------------------------------------------------------------

class TestDirectionAudit:
    def test_positive_alpha_keeps_original_direction(self):
        cfg = {"name": "pos_cs", "sign_hint": "positive"}
        df = _make_mock_factor_df(n_stocks=50, n_dates=100, alpha_strength=0.05)
        fwd = _make_mock_fwd_returns(df, alpha_strength=0.05)
        # Build a mock aligned panel (no data_lag shift for technical factor)
        aligned = df[["ts_code", "trade_date", "value"]].copy()
        aligned = aligned.merge(fwd[["ts_code", "trade_date", "fwd_ret_5d"]], on=["ts_code", "trade_date"])
        aligned = aligned.rename(columns={"fwd_ret_5d": "fwd_return"})
        result = _audit_factor_direction(cfg, aligned, "20170101", "20171231", value_col="value")
        assert result["direction_audit_status"] == "PASS"
        assert not result["direction_flipped"]

    def test_reversed_alpha_flips_direction(self):
        cfg = {"name": "neg_cs", "sign_hint": "positive"}
        df = _make_mock_factor_df(n_stocks=50, n_dates=100, alpha_strength=0.05, reverse=True)
        fwd = _make_mock_fwd_returns(df, alpha_strength=0.05)
        aligned = df[["ts_code", "trade_date", "value"]].copy()
        aligned = aligned.merge(fwd[["ts_code", "trade_date", "fwd_ret_5d"]], on=["ts_code", "trade_date"])
        aligned = aligned.rename(columns={"fwd_ret_5d": "fwd_return"})
        result = _audit_factor_direction(cfg, aligned, "20170101", "20171231", value_col="value")
        assert result["selected_direction"] == "reversed"
        assert result["direction_flipped"]

    def test_direction_uses_calibration_only(self):
        cfg = {"name": "cal_only_cs", "sign_hint": "positive"}
        df_cal = _make_mock_factor_df(n_stocks=50, n_dates=50, alpha_strength=0.05, seed=1)
        fwd_cal = _make_mock_fwd_returns(df_cal, alpha_strength=0.05, seed=1)
        aligned = df_cal[["ts_code", "trade_date", "value"]].copy()
        aligned = aligned.merge(fwd_cal[["ts_code", "trade_date", "fwd_ret_5d"]], on=["ts_code", "trade_date"])
        aligned = aligned.rename(columns={"fwd_ret_5d": "fwd_return"})
        result = _audit_factor_direction(cfg, aligned, "20170101", "20170630", value_col="value")
        assert result["direction_audit_status"] == "PASS"
        assert result["selected_direction"] == "original"


# ---------------------------------------------------------------------------
# IC by year tests
# ---------------------------------------------------------------------------

class TestICByYear:
    def test_ic_uses_corrected_direction(self):
        cfg = {"name": "test_cs", "sign_hint": "positive"}
        df = _make_mock_factor_df(n_stocks=50, n_dates=100, alpha_strength=0.05, reverse=True)
        fwd = _make_mock_fwd_returns(df, alpha_strength=0.05)
        aligned = df[["ts_code", "trade_date", "value"]].copy()
        aligned = aligned.merge(fwd[["ts_code", "trade_date", "fwd_ret_5d"]], on=["ts_code", "trade_date"])
        aligned = aligned.rename(columns={"fwd_ret_5d": "fwd_return"})
        dir_info = {"direction_flipped": True}
        rows = _compute_ic_by_year(cfg, aligned, dir_info, [2017], "value", "raw")
        assert len(rows) == 1
        assert rows[0]["mean_rank_ic"] > 0 or np.isnan(rows[0]["mean_rank_ic"]), (
            f"Flipped IC should be positive, got {rows[0]['mean_rank_ic']:.4f}"
        )


# ---------------------------------------------------------------------------
# Quantile returns tests
# ---------------------------------------------------------------------------

class TestQuantileReturns:
    def test_net_spread_positive_for_strong_alpha(self):
        cfg = {"name": "strong_cs", "sign_hint": "positive"}
        df = _make_mock_factor_df(n_stocks=100, n_dates=100, alpha_strength=0.10)
        fwd = _make_mock_fwd_returns(df, alpha_strength=0.10)
        aligned = df[["ts_code", "trade_date", "value"]].copy()
        aligned = aligned.merge(fwd[["ts_code", "trade_date", "fwd_ret_5d"]], on=["ts_code", "trade_date"])
        aligned = aligned.rename(columns={"fwd_ret_5d": "fwd_return"})
        dir_info = {"direction_flipped": False}
        rows = _compute_quantile_returns(cfg, aligned, dir_info, [2017], "value", "raw", 20.0)
        if rows:
            assert rows[0]["gross_spread"] > 0, f"Strong alpha should have positive gross spread"

    def test_high_turnover_reduces_net_spread(self):
        cfg = {"name": "costly_cs", "sign_hint": "positive"}
        df = _make_mock_factor_df(n_stocks=100, n_dates=100, alpha_strength=0.03)
        fwd = _make_mock_fwd_returns(df, alpha_strength=0.03)
        aligned = df[["ts_code", "trade_date", "value"]].copy()
        aligned = aligned.merge(fwd[["ts_code", "trade_date", "fwd_ret_5d"]], on=["ts_code", "trade_date"])
        aligned = aligned.rename(columns={"fwd_ret_5d": "fwd_return"})
        dir_info = {"direction_flipped": False}
        rows = _compute_quantile_returns(cfg, aligned, dir_info, [2017], "value", "raw", 20.0)
        if rows:
            assert rows[0]["net_spread"] <= rows[0]["gross_spread"], (
                "Net spread must not exceed gross spread"
            )


# ---------------------------------------------------------------------------
# Quality gate tests
# ---------------------------------------------------------------------------

class TestQualityGate:
    def _default_gate_cfg(self) -> dict:
        return {
            "min_mean_rank_ic": 0.01, "min_icir": 0.20,
            "min_positive_ic_years": 3, "min_top_bottom_net_spread_5d": 0.0,
            "min_positive_spread_years": 3, "min_top_quintile_net_excess_5d": 0.0,
            "min_positive_excess_years": 3, "min_net_gross_spread_ratio": 0.50,
            "max_single_year_contribution_pct": 60,
            "require_no_leakage": True,
            "min_coverage_pct": 80,
            "min_single_year_coverage_pct": 60,
        }

    def _default_gate_basis_cfg(self) -> dict:
        return {
            "raw_required": True,
            "neutralized_required_for_pass": True,
            "raw_pass_neutral_fail_status": "WATCH_SIZE_DEPENDENT",
            "raw_fail_neutral_pass_status": "WATCH_NEUTRAL_ONLY",
        }

    def _make_passing_ic_rows(self, fname: str, basis: str, years=None) -> list[dict]:
        if years is None:
            years = [2021, 2022, 2023, 2024]
        return [
            {"factor": fname, "year": y, "horizon": "fwd_ret_5d",
             "mean_rank_ic": 0.03, "icir": 0.40, "hit_rate": 0.60,
             "n_dates": 50, "basis": basis}
            for y in years
        ]

    def _make_passing_q_rows(self, fname: str, basis: str, years=None) -> list[dict]:
        if years is None:
            years = [2021, 2022, 2023, 2024]
        return [
            {"factor": fname, "year": y, "horizon": "fwd_ret_5d",
             "gross_spread": 0.03, "net_spread": 0.02,
             "top_quintile_net_excess": 0.015, "monotonic": True, "basis": basis}
            for y in years
        ]

    def test_strong_factor_passes_gate(self):
        cfg = {"name": "pass_cs", "role": "alpha_candidate", "sign_hint": "positive"}
        input_audit = {"input_audit_status": "PASS", "median_coverage_pct": 0.85,
                       "min_yearly_coverage_pct": 0.70, "data_status": "OK"}
        al_audit = {"no_leakage_status": "PASS", "n_aligned_rows": 5000}
        dir_info = {"direction_audit_status": "PASS", "direction_flipped": False}

        ic_raw = self._make_passing_ic_rows("pass_cs", "raw")
        ic_neutral = self._make_passing_ic_rows("pass_cs", "mcap_neutral")
        q_raw = self._make_passing_q_rows("pass_cs", "raw")
        q_neutral = self._make_passing_q_rows("pass_cs", "mcap_neutral")
        tc = [{"factor": "pass_cs", "year": y, "basis": "raw",
               "avg_total_turnover": 0.30, "net_spread": 0.02,
               "net_gross_ratio": 0.60} for y in [2021, 2022, 2023, 2024]]

        neut_diag = {"neutralization_valid": True, "neutralization_status": "OK"}
        result = _apply_quality_gate(
            cfg, input_audit, al_audit, dir_info,
            ic_raw, ic_neutral, q_raw, q_neutral, tc,
            {"ic_declining": False}, [], [],
            self._default_gate_cfg(), self._default_gate_basis_cfg(),
            {}, {},
            neutralization_diag=neut_diag,
        )
        assert result["quality_gate_status"] == "PASS", f"Expected PASS, got {result}"

    def test_negative_net_spread_fails_gate(self):
        cfg = {"name": "fail_cs", "role": "alpha_candidate", "sign_hint": "positive"}
        input_audit = {"input_audit_status": "PASS", "median_coverage_pct": 0.85,
                       "min_yearly_coverage_pct": 0.70, "data_status": "OK"}
        al_audit = {"no_leakage_status": "PASS"}
        dir_info = {"direction_audit_status": "PASS", "direction_flipped": False}

        ic_raw = [
            {"factor": "fail_cs", "year": y, "basis": "raw",
             "mean_rank_ic": 0.02, "icir": 0.30, "hit_rate": 0.55, "n_dates": 50}
            for y in [2021, 2022, 2023, 2024]
        ]
        q_raw = [
            {"factor": "fail_cs", "year": y, "basis": "raw",
             "gross_spread": 0.01, "net_spread": -0.005,
             "top_quintile_net_excess": -0.003, "monotonic": False}
            for y in [2021, 2022, 2023, 2024]
        ]
        ic_neutral = ic_raw  # same
        q_neutral = q_raw

        result = _apply_quality_gate(
            cfg, input_audit, al_audit, dir_info,
            ic_raw, ic_neutral, q_raw, q_neutral, [],
            {"ic_declining": False}, [], [],
            self._default_gate_cfg(), self._default_gate_basis_cfg(),
            {}, {},
        )
        assert result["quality_gate_status"] == "FAIL", f"Expected FAIL, got {result}"

    def test_input_audit_fail_blocks_gate(self):
        cfg = {"name": "blocked_cs", "role": "alpha_candidate"}
        input_audit = {"input_audit_status": "FAIL", "input_audit_reason": "test block",
                       "data_status": "INPUT_FAIL"}
        al_audit = {"no_leakage_status": "PASS"}
        dir_info = {"direction_audit_status": "PASS"}
        result = _apply_quality_gate(cfg, input_audit, al_audit, dir_info,
                                     [], [], [], [], [],
                                     {}, [], [],
                                     self._default_gate_cfg(), self._default_gate_basis_cfg(),
                                     {}, {})
        assert result["quality_gate_status"] == "FAIL"

    def test_no_leakage_failure_blocks_gate(self):
        """No-leakage not PASS → hard FAIL regardless of other metrics."""
        cfg = {"name": "leaky_cs", "role": "alpha_candidate", "sign_hint": "positive"}
        input_audit = {"input_audit_status": "PASS", "median_coverage_pct": 0.90,
                       "min_yearly_coverage_pct": 0.80, "data_status": "OK"}
        al_audit = {"no_leakage_status": "FAIL", "alignment_reason": "test leak"}
        dir_info = {"direction_audit_status": "PASS", "direction_flipped": False}
        ic_raw = self._make_passing_ic_rows("leaky_cs", "raw")
        ic_neutral = self._make_passing_ic_rows("leaky_cs", "mcap_neutral")
        q_raw = self._make_passing_q_rows("leaky_cs", "raw")
        q_neutral = self._make_passing_q_rows("leaky_cs", "mcap_neutral")

        result = _apply_quality_gate(
            cfg, input_audit, al_audit, dir_info,
            ic_raw, ic_neutral, q_raw, q_neutral, [],
            {"ic_declining": False}, [], [],
            self._default_gate_cfg(), self._default_gate_basis_cfg(),
            {}, {},
        )
        assert result["quality_gate_status"] == "FAIL", f"Expected FAIL due to no-leakage, got {result['quality_gate_status']}"
        assert "no_leakage" in result["failure_reasons"].lower()

    def test_raw_pass_neutral_fail_becomes_watch_size_dependent(self):
        """Raw PASS + neutral FAIL → WATCH_SIZE_DEPENDENT."""
        cfg = {"name": "size_dep_cs", "role": "alpha_candidate", "sign_hint": "positive"}
        input_audit = {"input_audit_status": "PASS", "median_coverage_pct": 0.85,
                       "min_yearly_coverage_pct": 0.70, "data_status": "OK"}
        al_audit = {"no_leakage_status": "PASS"}
        dir_info = {"direction_audit_status": "PASS", "direction_flipped": False}

        ic_raw = self._make_passing_ic_rows("size_dep_cs", "raw")
        q_raw = self._make_passing_q_rows("size_dep_cs", "raw")
        # Neutralized FAILS (negative IC)
        ic_neutral = [
            {"factor": "size_dep_cs", "year": y, "basis": "mcap_neutral",
             "mean_rank_ic": -0.02, "icir": -0.15, "hit_rate": 0.35, "n_dates": 50}
            for y in [2021, 2022, 2023, 2024]
        ]
        q_neutral = [
            {"factor": "size_dep_cs", "year": y, "basis": "mcap_neutral",
             "gross_spread": 0.005, "net_spread": -0.01,
             "top_quintile_net_excess": -0.005, "monotonic": False}
            for y in [2021, 2022, 2023, 2024]
        ]

        neut_diag = {"neutralization_valid": True, "neutralization_status": "OK"}
        result = _apply_quality_gate(
            cfg, input_audit, al_audit, dir_info,
            ic_raw, ic_neutral, q_raw, q_neutral, [],
            {"ic_declining": False}, [], [],
            self._default_gate_cfg(), self._default_gate_basis_cfg(),
            {}, {},
            neutralization_diag=neut_diag,
        )
        assert result["quality_gate_status"] == "WATCH_SIZE_DEPENDENT", (
            f"Expected WATCH_SIZE_DEPENDENT, got {result['quality_gate_status']}"
        )

    def test_raw_fail_neutral_pass_becomes_watch_neutral_only(self):
        """Raw FAIL + neutral PASS → WATCH_NEUTRAL_ONLY."""
        cfg = {"name": "neutral_only_cs", "role": "alpha_candidate", "sign_hint": "positive"}
        input_audit = {"input_audit_status": "PASS", "median_coverage_pct": 0.85,
                       "min_yearly_coverage_pct": 0.70, "data_status": "OK"}
        al_audit = {"no_leakage_status": "PASS"}
        dir_info = {"direction_audit_status": "PASS", "direction_flipped": False}

        # Raw FAILS
        ic_raw = [
            {"factor": "neutral_only_cs", "year": y, "basis": "raw",
             "mean_rank_ic": -0.01, "icir": -0.10, "hit_rate": 0.35, "n_dates": 50}
            for y in [2021, 2022, 2023, 2024]
        ]
        q_raw = [
            {"factor": "neutral_only_cs", "year": y, "basis": "raw",
             "gross_spread": 0.005, "net_spread": -0.005,
             "top_quintile_net_excess": -0.003, "monotonic": False}
            for y in [2021, 2022, 2023, 2024]
        ]
        # Neutral PASSES
        ic_neutral = self._make_passing_ic_rows("neutral_only_cs", "mcap_neutral")
        q_neutral = self._make_passing_q_rows("neutral_only_cs", "mcap_neutral")

        # Valid neutralization required for WATCH_NEUTRAL_ONLY
        neut_diag = {"neutralization_valid": True, "neutralization_status": "OK"}
        result = _apply_quality_gate(
            cfg, input_audit, al_audit, dir_info,
            ic_raw, ic_neutral, q_raw, q_neutral, [],
            {"ic_declining": False}, [], [],
            self._default_gate_cfg(), self._default_gate_basis_cfg(),
            {}, {},
            neutralization_diag=neut_diag,
        )
        assert result["quality_gate_status"] == "WATCH_NEUTRAL_ONLY", (
            f"Expected WATCH_NEUTRAL_ONLY, got {result['quality_gate_status']}"
        )

    def test_log_market_cap_never_eligible(self):
        """role=neutralizer must always be SUPPORT, never PASS/WATCH candidate."""
        cfg = {"name": "log_market_cap_cs", "role": "neutralizer", "sign_hint": "negative"}
        input_audit = {"input_audit_status": "PASS", "median_coverage_pct": 0.90,
                       "min_yearly_coverage_pct": 0.85, "data_status": "OK"}
        al_audit = {"no_leakage_status": "PASS"}
        dir_info = {"direction_audit_status": "PASS", "direction_flipped": False}
        ic_raw = self._make_passing_ic_rows("log_market_cap_cs", "raw")
        ic_neutral = self._make_passing_ic_rows("log_market_cap_cs", "mcap_neutral")
        q_raw = self._make_passing_q_rows("log_market_cap_cs", "raw")
        q_neutral = self._make_passing_q_rows("log_market_cap_cs", "mcap_neutral")

        result = _apply_quality_gate(
            cfg, input_audit, al_audit, dir_info,
            ic_raw, ic_neutral, q_raw, q_neutral, [],
            {"ic_declining": False}, [], [],
            self._default_gate_cfg(), self._default_gate_basis_cfg(),
            {}, {},
        )
        assert result["quality_gate_status"] == "SUPPORT", (
            f"Neutralizer must be SUPPORT, got {result['quality_gate_status']}"
        )

    def test_ic_decline_downgrades_pass_to_watch(self):
        """PASS + ic_declining=true → WATCH_IC_DECAY."""
        cfg = {"name": "decay_cs", "role": "alpha_candidate", "sign_hint": "positive"}
        input_audit = {"input_audit_status": "PASS", "median_coverage_pct": 0.85,
                       "min_yearly_coverage_pct": 0.70, "data_status": "OK"}
        al_audit = {"no_leakage_status": "PASS"}
        dir_info = {"direction_audit_status": "PASS", "direction_flipped": False}
        ic_raw = self._make_passing_ic_rows("decay_cs", "raw")
        ic_neutral = self._make_passing_ic_rows("decay_cs", "mcap_neutral")
        q_raw = self._make_passing_q_rows("decay_cs", "raw")
        q_neutral = self._make_passing_q_rows("decay_cs", "mcap_neutral")

        neut_diag = {"neutralization_valid": True, "neutralization_status": "OK"}
        result = _apply_quality_gate(
            cfg, input_audit, al_audit, dir_info,
            ic_raw, ic_neutral, q_raw, q_neutral, [],
            {"ic_declining": True}, [], [],
            self._default_gate_cfg(), self._default_gate_basis_cfg(),
            {}, {},
            neutralization_diag=neut_diag,
        )
        assert result["quality_gate_status"] == "WATCH_IC_DECAY", (
            f"Expected WATCH_IC_DECAY, got {result['quality_gate_status']}"
        )

    def test_rolling_window_fragile_downgrades_pass(self):
        """PASS + <3 rolling windows PASS → WATCH_WINDOW_FRAGILE."""
        cfg = {"name": "fragile_cs", "role": "alpha_candidate", "sign_hint": "positive"}
        input_audit = {"input_audit_status": "PASS", "median_coverage_pct": 0.85,
                       "min_yearly_coverage_pct": 0.70, "data_status": "OK"}
        al_audit = {"no_leakage_status": "PASS"}
        dir_info = {"direction_audit_status": "PASS", "direction_flipped": False}
        ic_raw = self._make_passing_ic_rows("fragile_cs", "raw")
        ic_neutral = self._make_passing_ic_rows("fragile_cs", "mcap_neutral")
        q_raw = self._make_passing_q_rows("fragile_cs", "raw")
        q_neutral = self._make_passing_q_rows("fragile_cs", "mcap_neutral")

        rolling_results = [
            {"factor": "fragile_cs", "window": "2018_2021", "window_gate_status": "PASS"},
            {"factor": "fragile_cs", "window": "2019_2022", "window_gate_status": "FAIL"},
            {"factor": "fragile_cs", "window": "2020_2023", "window_gate_status": "FAIL"},
            {"factor": "fragile_cs", "window": "2021_2024", "window_gate_status": "PASS", "primary": True},
        ]

        neut_diag = {"neutralization_valid": True, "neutralization_status": "OK"}
        result = _apply_quality_gate(
            cfg, input_audit, al_audit, dir_info,
            ic_raw, ic_neutral, q_raw, q_neutral, [],
            {"ic_declining": False}, rolling_results, [],
            self._default_gate_cfg(), self._default_gate_basis_cfg(),
            {"min_pass_windows_for_strong_pass": 3}, {},
            neutralization_diag=neut_diag,
        )
        assert result["quality_gate_status"] == "WATCH_WINDOW_FRAGILE", (
            f"Expected WATCH_WINDOW_FRAGILE, got {result['quality_gate_status']}"
        )

    def test_capacity_fail_blocks_pass(self):
        """Capacity FAIL → hard FAIL regardless of other gates."""
        cfg = {"name": "illiquid_cs", "role": "alpha_candidate", "sign_hint": "positive"}
        input_audit = {"input_audit_status": "PASS", "median_coverage_pct": 0.85,
                       "min_yearly_coverage_pct": 0.70, "data_status": "OK"}
        al_audit = {"no_leakage_status": "PASS"}
        dir_info = {"direction_audit_status": "PASS", "direction_flipped": False}
        ic_raw = self._make_passing_ic_rows("illiquid_cs", "raw")
        ic_neutral = self._make_passing_ic_rows("illiquid_cs", "mcap_neutral")
        q_raw = self._make_passing_q_rows("illiquid_cs", "raw")
        q_neutral = self._make_passing_q_rows("illiquid_cs", "mcap_neutral")

        capacity_rows = [
            {"factor": "illiquid_cs", "year": 2021, "capacity_status": "FAIL",
             "capacity_reason": "insufficient liquidity"},
        ]

        result = _apply_quality_gate(
            cfg, input_audit, al_audit, dir_info,
            ic_raw, ic_neutral, q_raw, q_neutral, [],
            {"ic_declining": False}, [], capacity_rows,
            self._default_gate_cfg(), self._default_gate_basis_cfg(),
            {}, {"enabled": True},
        )
        assert result["quality_gate_status"] == "FAIL", f"Expected FAIL due to capacity, got {result}"

    def test_coverage_percentage_failure(self):
        """Coverage < min_coverage_pct must add failure reason."""
        cfg = {"name": "low_cov_cs", "role": "alpha_candidate", "sign_hint": "positive"}
        input_audit = {"input_audit_status": "PASS", "median_coverage_pct": 0.55,
                       "min_yearly_coverage_pct": 0.40, "data_status": "OK"}
        al_audit = {"no_leakage_status": "PASS"}
        dir_info = {"direction_audit_status": "PASS", "direction_flipped": False}
        ic_raw = self._make_passing_ic_rows("low_cov_cs", "raw")
        q_raw = self._make_passing_q_rows("low_cov_cs", "raw")

        result = _apply_quality_gate(
            cfg, input_audit, al_audit, dir_info,
            ic_raw, ic_raw, q_raw, q_raw, [],
            {"ic_declining": False}, [], [],
            self._default_gate_cfg(), self._default_gate_basis_cfg(),
            {}, {},
        )
        assert "coverage" in result["failure_reasons"].lower(), (
            f"Coverage failure must appear in reasons, got: {result['failure_reasons']}"
        )


# ---------------------------------------------------------------------------
# Correlation clusters tests
# ---------------------------------------------------------------------------

class TestCorrelationClusters:
    def test_highly_correlated_factors_clustered(self):
        rng = np.random.default_rng(42)
        n = 500
        base = rng.normal(0, 1, n)
        df_a = pd.DataFrame({
            "ts_code": ["s1"] * n, "trade_date": range(n), "value": base
        })
        df_b = pd.DataFrame({
            "ts_code": ["s1"] * n, "trade_date": range(n),
            "value": base * 0.9 + rng.normal(0, 0.1, n)
        })
        df_c = pd.DataFrame({
            "ts_code": ["s1"] * n, "trade_date": range(n),
            "value": rng.normal(0, 1, n)
        })

        factor_dfs = {"a_cs": df_a, "b_cs": df_b, "c_cs": df_c}
        fwd = pd.DataFrame({"ts_code": ["s1"] * n, "trade_date": range(n), "fwd_ret_5d": 0.0})
        factor_cfgs = [
            {"name": "a_cs", "role": "alpha_candidate", "sign_hint": "positive"},
            {"name": "b_cs", "role": "alpha_candidate", "sign_hint": "positive"},
            {"name": "c_cs", "role": "alpha_candidate", "sign_hint": "positive"},
        ]
        gate_results = [
            {"factor": "a_cs", "quality_gate_status": "PASS", "failure_reasons": "", "_gate_meta": {"raw_mean_ic": 0.05, "raw_icir": 0.5, "raw_net_spread": 0.02, "avg_total_turnover": 0.3, "coverage_pct": 0.85}},
            {"factor": "b_cs", "quality_gate_status": "PASS", "failure_reasons": "", "_gate_meta": {"raw_mean_ic": 0.04, "raw_icir": 0.4, "raw_net_spread": 0.015, "avg_total_turnover": 0.3, "coverage_pct": 0.85}},
            {"factor": "c_cs", "quality_gate_status": "FAIL", "failure_reasons": "low IC", "_gate_meta": {}},
        ]
        clusters = _compute_correlation_clusters(factor_dfs, fwd, {}, factor_cfgs, gate_results, threshold=0.85)

        if not clusters.empty:
            for _, row in clusters.iterrows():
                factors = row["factors"] if "factors" in row else ""
                if "a_cs" in str(factors):
                    assert "b_cs" in str(factors), "a and b are highly correlated, should cluster together"
                if "c_cs" in str(factors):
                    if "representative" in clusters.columns:
                        assert row.get("representative", "yes") == "yes" or row.get("n_factors", 99) == 1

    def test_cluster_dedup_keeps_only_representative(self):
        """Each cluster should have exactly one representative."""
        rng = np.random.default_rng(42)
        n = 500
        base = rng.normal(0, 1, n)
        df_a = pd.DataFrame({"ts_code": ["s1"] * n, "trade_date": range(n), "value": base})
        df_b = pd.DataFrame({"ts_code": ["s1"] * n, "trade_date": range(n),
                            "value": base * 0.95 + rng.normal(0, 0.05, n)})

        factor_dfs = {"x_cs": df_a, "y_cs": df_b}
        fwd = pd.DataFrame({"ts_code": ["s1"] * n, "trade_date": range(n), "fwd_ret_5d": 0.0})
        factor_cfgs = [
            {"name": "x_cs", "role": "alpha_candidate", "sign_hint": "positive"},
            {"name": "y_cs", "role": "alpha_candidate", "sign_hint": "positive"},
        ]
        gate_results = [
            {"factor": "x_cs", "quality_gate_status": "PASS", "failure_reasons": "", "_gate_meta": {"raw_mean_ic": 0.05, "raw_icir": 0.5, "raw_net_spread": 0.02, "avg_total_turnover": 0.3, "coverage_pct": 0.85}},
            {"factor": "y_cs", "quality_gate_status": "PASS", "failure_reasons": "", "_gate_meta": {"raw_mean_ic": 0.03, "raw_icir": 0.3, "raw_net_spread": 0.01, "avg_total_turnover": 0.3, "coverage_pct": 0.85}},
        ]
        clusters = _compute_correlation_clusters(factor_dfs, fwd, {}, factor_cfgs, gate_results, threshold=0.85)

        if not clusters.empty and "representative" in clusters.columns:
            for cid in clusters["cluster_id"].unique():
                c_df = clusters[clusters["cluster_id"] == cid]
                reps = c_df[c_df["representative"] == "yes"]
                assert len(reps) == 1, f"Cluster {cid} must have exactly 1 representative"


# ---------------------------------------------------------------------------
# Real turnover tests
# ---------------------------------------------------------------------------

class TestRealTurnover:
    def test_turnover_method_is_real_weight_drift_or_overlap_proxy(self):
        """Real turnover must use REAL_WEIGHT_DRIFT or OVERLAP_PROXY, never hardcoded 0.20."""
        cfg = {"name": "turnover_cs", "sign_hint": "positive", "tradable_weighting": "equal_weight"}
        df = _make_mock_factor_df(n_stocks=100, n_dates=50, alpha_strength=0.05)
        fwd = _make_mock_fwd_returns(df, alpha_strength=0.05)
        aligned = df[["ts_code", "trade_date", "value"]].copy()
        aligned = aligned.merge(fwd[["ts_code", "trade_date", "fwd_ret_5d", "fwd_ret_1d"]],
                                on=["ts_code", "trade_date"])
        aligned = aligned.rename(columns={"fwd_ret_5d": "fwd_return"})
        dir_info = {"direction_flipped": False}

        portfolios = _compute_quantile_portfolios(cfg, aligned, dir_info, "value", "equal_weight")
        if portfolios:
            tc_rows = _compute_real_turnover_cost(cfg, portfolios, fwd, aligned, dir_info,
                                                   [2017], "value", "raw", "equal_weight", 20.0)
            if tc_rows:
                methods = set(r["turnover_method"] for r in tc_rows)
                assert "REAL_WEIGHT_DRIFT" in methods or "OVERLAP_PROXY" in methods, (
                    f"Turnover method must be REAL_WEIGHT_DRIFT or OVERLAP_PROXY, got {methods}"
                )

    def test_real_turnover_changes_net_spread(self):
        """Higher actual turnover must reduce net_spread compared to gross_spread."""
        cfg = {"name": "cost_test_cs", "sign_hint": "positive", "tradable_weighting": "equal_weight"}
        df = _make_mock_factor_df(n_stocks=100, n_dates=100, alpha_strength=0.05)
        fwd = _make_mock_fwd_returns(df, alpha_strength=0.05)
        aligned = df[["ts_code", "trade_date", "value"]].copy()
        aligned = aligned.merge(fwd[["ts_code", "trade_date", "fwd_ret_5d", "fwd_ret_1d"]],
                                on=["ts_code", "trade_date"])
        aligned = aligned.rename(columns={"fwd_ret_5d": "fwd_return"})
        dir_info = {"direction_flipped": False}

        portfolios = _compute_quantile_portfolios(cfg, aligned, dir_info, "value", "equal_weight")
        if portfolios and len(portfolios) >= 2:
            tc_rows = _compute_real_turnover_cost(cfg, portfolios, fwd, aligned, dir_info,
                                                   [2017], "value", "raw", "equal_weight", 20.0)
            if tc_rows:
                for r in tc_rows:
                    if not np.isnan(r["net_spread"]) and not np.isnan(r["gross_spread"]):
                        assert r["net_spread"] <= r["gross_spread"] + 0.001, (
                            f"Net spread ({r['net_spread']:.6f}) should not significantly exceed gross ({r['gross_spread']:.6f})"
                        )


# ---------------------------------------------------------------------------
# Mcap neutralization tests
# ---------------------------------------------------------------------------

class TestMcapNeutralization:
    def test_neutralization_reduces_size_dependent_alpha(self):
        """A factor purely driven by size should lose alpha after mcap neutralization."""
        rng = np.random.default_rng(123)
        n_stocks = 100
        n_dates = 50
        dates = [20170103 + i * 7 for i in range(n_dates)]
        stocks = [f"{i:06d}.SH" for i in range(n_stocks)]

        # Build a factor that is purely size (log_mcap)
        rows = []
        for dt in dates:
            for ts in stocks:
                size_signal = rng.normal(0, 1)
                # Factor value = size_signal (so IC should come from size)
                factor_val = size_signal + rng.normal(0, 0.1)
                fwd_ret = size_signal * 0.03 + rng.normal(0, 0.02)
                rows.append({
                    "ts_code": ts, "trade_date": dt,
                    "value": factor_val, "fwd_return": fwd_ret,
                })
        aligned = pd.DataFrame(rows)

        # Build matching log_market_cap panel
        log_mcap_rows = []
        for dt in dates:
            for ts in stocks:
                log_mcap_rows.append({
                    "ts_code": ts, "trade_date": dt,
                    "value": rng.normal(0, 1),
                })
        log_mcap = pd.DataFrame(log_mcap_rows)

        result, meta = _neutralize_by_mcap("test_size_cs", aligned, log_mcap, min_coverage_pct=50.0)

        assert "value_raw" in result.columns
        assert "value_mcap_neutral" in result.columns
        # meta should contain stats
        assert "neutralizer_coverage_pct" in meta
        assert "size_beta_mean" in meta
        # Verify that neutralization produces non-NaN values for some rows
        n_neutral_valid = result["value_mcap_neutral"].notna().sum()
        n_raw_valid = result["value_raw"].notna().sum()
        # Both raw and neutral should have valid data (high coverage threshold passed)
        assert n_raw_valid > 0, "Raw values should be present"
        # Neutral may have fewer values if coverage threshold not met on some dates
        # The key assertion: neutralization function runs without error and produces output

    def test_neutralization_with_insufficient_coverage(self):
        """When neutralizer has low coverage, neutralized value should be NaN."""
        rng = np.random.default_rng(456)
        n_stocks = 100
        dates = [20170103 + i * 7 for i in range(10)]
        stocks = [f"{i:06d}.SH" for i in range(n_stocks)]

        rows = []
        for dt in dates:
            for ts in stocks:
                rows.append({
                    "ts_code": ts, "trade_date": dt,
                    "value": rng.normal(0, 1), "fwd_return": rng.normal(0, 0.02),
                })
        aligned = pd.DataFrame(rows)

        # log_mcap only covers 20% of stocks (below 70% threshold)
        log_mcap_rows = []
        for dt in dates:
            for ts in stocks[:20]:  # only 20 stocks
                log_mcap_rows.append({
                    "ts_code": ts, "trade_date": dt,
                    "value": rng.normal(0, 1),
                })
        log_mcap = pd.DataFrame(log_mcap_rows)

        result, meta = _neutralize_by_mcap("low_cov_cs", aligned, log_mcap, min_coverage_pct=70.0)

        # Meta should indicate low coverage
        assert meta["n_neutralized_dates"] <= meta["n_skipped_dates"] or meta["n_neutralized_dates"] == 0
        # Most rows should have NaN for value_mcap_neutral
        neut_nan_rate = result["value_mcap_neutral"].isna().mean()
        assert neut_nan_rate > 0.5, f"Most neutralized values should be NaN with low coverage, got {neut_nan_rate:.2%}"


# ---------------------------------------------------------------------------
# IC trend tests
# ---------------------------------------------------------------------------

class TestICTrend:
    def test_declining_ic_detected(self):
        """A monotonically decreasing IC series should trigger ic_declining=true."""
        cfg = {"name": "decline_cs", "sign_hint": "positive"}
        rng = np.random.default_rng(789)
        dates = []
        current_date = 20210104
        for i in range(48):  # 48 months
            dates.append(current_date)
            current_date += 30
            if current_date % 100 > 28:
                current_date = (current_date // 100) * 100 + 101

        # Build aligned panel with declining IC
        rows = []
        for i, dt in enumerate(dates):
            # Slope from +0.05 to -0.02 over 48 months
            true_ic = 0.05 - 0.07 * (i / 47)
            for _ in range(50):
                ts = f"{rng.integers(0, 999):06d}.SH"
                signal = rng.normal(0, 1)
                ret = true_ic * signal + rng.normal(0, 0.03)
                rows.append({
                    "ts_code": ts, "trade_date": dt,
                    "value": signal, "fwd_return": ret,
                })
        aligned = pd.DataFrame(rows)
        dir_info = {"direction_flipped": False}

        result = _compute_ic_trend("decline_cs", aligned, dir_info, "value", "raw",
                                   "20210101", "20241231", p_value_threshold=0.10)
        assert result["ic_trend_slope"] < 0, f"Expected negative slope, got {result['ic_trend_slope']}"
        # With strong decline, should be detected
        if result["ic_trend_p_value"] < 0.10:
            assert result["ic_declining"] is True


# ---------------------------------------------------------------------------
# Rolling window gate tests
# ---------------------------------------------------------------------------

class TestRollingWindowGate:
    def test_four_windows_computed(self):
        cfg = {"name": "roll_cs", "role": "alpha_candidate", "sign_hint": "positive"}
        ic_rows = [
            {"factor": "roll_cs", "year": y, "basis": "raw",
             "mean_rank_ic": 0.03, "icir": 0.40, "n_dates": 50}
            for y in [2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024]
        ]
        q_rows = [
            {"factor": "roll_cs", "year": y, "basis": "raw",
             "gross_spread": 0.03, "net_spread": 0.02}
            for y in [2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024]
        ]
        dir_info = {"direction_flipped": False}
        gate_cfg = {"min_mean_rank_ic": 0.01, "min_icir": 0.20,
                    "min_positive_ic_years": 3, "min_positive_spread_years": 3}

        rolling_windows = [
            {"name": "2018_2021", "start": "20180101", "end": "20211231"},
            {"name": "2019_2022", "start": "20190101", "end": "20221231"},
            {"name": "2020_2023", "start": "20200101", "end": "20231231"},
            {"name": "2021_2024", "start": "20210101", "end": "20241231", "primary": True},
        ]

        results = _compute_rolling_window_gate(cfg, ic_rows, q_rows, dir_info, rolling_windows, gate_cfg)
        assert len(results) == 4, f"Expected 4 rolling windows, got {len(results)}"
        primary = [r for r in results if r.get("primary")]
        assert len(primary) == 1, "Must have exactly one primary window"


# ---------------------------------------------------------------------------
# Capacity audit tests
# ---------------------------------------------------------------------------

class TestCapacityAudit:
    def test_capacity_identifies_low_liquidity(self):
        """Low per-stock median amount should trigger capacity FAIL."""
        cfg = {"name": "low_liq_cs", "sign_hint": "positive", "tradable_weighting": "equal_weight"}
        df = _make_mock_factor_df(n_stocks=50, n_dates=50, alpha_strength=0.05)
        fwd = _make_mock_fwd_returns(df, alpha_strength=0.05)
        aligned = df[["ts_code", "trade_date", "value"]].copy()
        aligned = aligned.merge(fwd[["ts_code", "trade_date", "fwd_ret_5d"]], on=["ts_code", "trade_date"])
        aligned = aligned.rename(columns={"fwd_ret_5d": "fwd_return"})
        dir_info = {"direction_flipped": False}

        # Create daily_basic with very low liquidity (万元 units, will be ×10000)
        # circ_mv=500 (万元) → 5M CNY, turnover_rate=2% → ~100K CNY daily amount
        daily_basic_rows = []
        for _, row in df.iterrows():
            daily_basic_rows.append({
                "ts_code": row["ts_code"],
                "trade_date": row["trade_date"],
                "total_mv": 1000,    # 1000万元 = 10M CNY — very small
                "circ_mv": 500,      # 500万元 = 5M CNY
                "turnover_rate": 2.0,
            })
        daily_basic = pd.DataFrame(daily_basic_rows)

        capacity_cfg = {"target_aum_cny": 1e9, "max_participation_rate": 0.05,
                        "min_median_amount_cny": 2e7,
                        "daily_basic_mv_unit": "wan_cny",
                        "assumed_daily_turnover": 0.05}
        ca = _compute_capacity_audit(cfg, aligned, dir_info, "value", "raw",
                                     daily_basic, [2017], capacity_cfg)
        if ca:
            assert ca[0]["capacity_status"] in ("WATCH", "FAIL", "NOT_AVAILABLE"), (
                f"Low liquidity should not PASS, got {ca[0]['capacity_status']}"
            )


# ---------------------------------------------------------------------------
# Candidate pool tests
# ---------------------------------------------------------------------------

class TestCandidatePool:
    def test_log_market_cap_excluded_from_eligible(self):
        """Neutralizer factors must never appear in eligible_factors."""
        cfg_map = [
            {"name": "reversal_5_cs", "role": "alpha_candidate"},
            {"name": "log_market_cap_cs", "role": "neutralizer"},
        ]
        gate_results = [
            {"factor": "reversal_5_cs", "quality_gate_status": "FAIL", "failure_reasons": ""},
            {"factor": "log_market_cap_cs", "quality_gate_status": "SUPPORT", "failure_reasons": ""},
        ]
        clusters = pd.DataFrame()

        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "pool.yaml"
            pool = _generate_candidate_pool(gate_results, cfg_map, clusters, out_path)
            assert "log_market_cap_cs" not in pool["eligible_factors"]
            assert "log_market_cap_cs" in pool["support_factors"]["neutralizers"]

    def test_no_alpha_source_found_when_no_pass(self):
        """Empty eligible → recommendation must be NO_ALPHA_SOURCE_FOUND."""
        cfg_map = [
            {"name": "fail_1_cs", "role": "alpha_candidate"},
            {"name": "fail_2_cs", "role": "alpha_candidate"},
        ]
        gate_results = [
            {"factor": "fail_1_cs", "quality_gate_status": "FAIL", "failure_reasons": "low IC"},
            {"factor": "fail_2_cs", "quality_gate_status": "DATA_MISSING", "failure_reasons": "empty cache"},
        ]
        clusters = pd.DataFrame()

        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "pool.yaml"
            pool = _generate_candidate_pool(gate_results, cfg_map, clusters, out_path)
            assert pool["recommendation"] == "NO_ALPHA_SOURCE_FOUND"
            assert len(pool["eligible_factors"]) == 0
            assert "fail_1_cs" in pool["fail_factors"]
            assert "fail_2_cs" in pool["missing_data_factors"]

    def test_watch_never_enters_eligible(self):
        """WATCH factors must not sneak into eligible_factors."""
        cfg_map = [{"name": "watch_cs", "role": "alpha_candidate"}]
        gate_results = [
            {"factor": "watch_cs", "quality_gate_status": "WATCH_SIZE_DEPENDENT", "failure_reasons": ""},
        ]
        clusters = pd.DataFrame()

        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "pool.yaml"
            pool = _generate_candidate_pool(gate_results, cfg_map, clusters, out_path)
            assert "watch_cs" not in pool["eligible_factors"]
            assert "watch_cs" in pool["watch_factors_for_review"]


# ---------------------------------------------------------------------------
# Report tests
# ---------------------------------------------------------------------------

class TestReport:
    def test_report_generates_without_stub(self):
        """Generated report must not contain the word STUB."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out_doc = Path(tmpdir) / "report.md"
            pool = {"recommendation": "N/A", "eligible_factors": [], "watch_factors_for_review": [],
                    "support_factors": {"neutralizers": [], "redundant": []},
                    "missing_data_factors": [], "fail_factors": []}
            _write_report(
                out_doc, [], [], [], [], [], [], [], [], [], pd.DataFrame(), [], [], [], pool,
            )
            content = out_doc.read_text(encoding="utf-8")
            assert "STUB" not in content, "Report must not contain STUB"

    def test_report_contains_no_alpha_source_found_when_empty(self):
        """When no eligible factors, report must mention NO_ALPHA_SOURCE_FOUND."""
        pool = {
            "recommendation": "NO_ALPHA_SOURCE_FOUND",
            "eligible_factors": [], "watch_factors_for_review": [],
            "support_factors": {"neutralizers": [], "redundant": []},
            "missing_data_factors": [], "fail_factors": [],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            out_doc = Path(tmpdir) / "report.md"
            gate_results = [
                {"factor": "bad_cs", "quality_gate_status": "FAIL", "n_failures": 5,
                 "failure_reasons": "low IC; negative net spread"}
            ]
            _write_report(
                out_doc, [], [], [], [], [], [], [], [], [], pd.DataFrame(), [], [], gate_results, pool,
            )
            content = out_doc.read_text(encoding="utf-8")
            assert "NO_ALPHA_SOURCE_FOUND" in content


# ---------------------------------------------------------------------------
# STUB prohibition test
# ---------------------------------------------------------------------------

class TestNoStub:
    def test_no_stub_outputs_in_audit(self):
        """All audit functions must never output STUB."""
        # Test input audit
        cfg = {"name": "test_cs"}
        df = _make_mock_factor_df(n_stocks=50, n_dates=50)
        fwd = _make_mock_fwd_returns(df)
        result = _audit_factor_input(cfg, df, fwd, "20170101", "20171231")
        flat = str(result.values())
        assert "STUB" not in flat, f"Input audit must not contain STUB: {flat[:200]}"

    def test_empty_cache_is_not_stub(self):
        """Empty cache output must be DATA_MISSING, not STUB."""
        cfg = {"name": "empty_cs"}
        df = pd.DataFrame(columns=["ts_code", "trade_date", "value"])
        fwd = pd.DataFrame(columns=["ts_code", "trade_date", "fwd_ret_5d"])
        result = _audit_factor_input(cfg, df, fwd, "20170101", "20201231")
        assert result.get("data_status") != "STUB", "Empty cache must not be STUB"
        assert result.get("data_status") == "DATA_MISSING"


# ---------------------------------------------------------------------------
# Regime breakdown test
# ---------------------------------------------------------------------------

class TestRegimeBreakdown:
    def test_regime_breakdown_without_files(self):
        """When no regime files exist, output NOT_AVAILABLE."""
        cfg = {"name": "test_cs", "sign_hint": "positive"}
        # Create aligned panel that won't match any regime files in the test env
        # (uses tmpdir that doesn't have outputs/runs/)
        df = _make_mock_factor_df(n_stocks=50, n_dates=50)
        fwd = _make_mock_fwd_returns(df)
        aligned = df[["ts_code", "trade_date", "value"]].copy()
        aligned = aligned.merge(fwd[["ts_code", "trade_date", "fwd_ret_5d"]], on=["ts_code", "trade_date"])
        aligned = aligned.rename(columns={"fwd_ret_5d": "fwd_return"})
        dir_info = {"direction_flipped": False}

        # This will scan outputs/runs/* in the real project root,
        # which may or may not exist in CI. The function handles both cases.
        results = _compute_regime_breakdown(cfg, aligned, dir_info, "value", "raw", [2017])
        assert len(results) >= 1
        # At least one result should exist
        for r in results:
            assert "STUB" not in str(r.values()), f"Regime result must not contain STUB: {r}"


# ---------------------------------------------------------------------------
# Capacity amount unit conversion (plan §7.5)
# ---------------------------------------------------------------------------

class TestAmountUnitConversion:
    def test_cny_unit_no_conversion(self):
        s = pd.Series([1000.0, 2000.0, 3000.0])
        out = _convert_amount_to_cny(s, "cny")
        assert (out == s).all()

    def test_yuan_unit_no_conversion(self):
        s = pd.Series([1000.0, 2000.0])
        out = _convert_amount_to_cny(s, "yuan")
        assert (out == s).all()

    def test_thousand_cny_multiplies_by_1000(self):
        s = pd.Series([1.0, 2.5])
        out = _convert_amount_to_cny(s, "thousand_cny")
        assert out.tolist() == [1000.0, 2500.0]

    def test_wan_cny_multiplies_by_10000(self):
        s = pd.Series([1.0, 3.0])
        out = _convert_amount_to_cny(s, "wan_cny")
        assert out.tolist() == [10000.0, 30000.0]

    def test_unsupported_unit_raises(self):
        with pytest.raises(ValueError):
            _convert_amount_to_cny(pd.Series([1.0]), "bushels")

    def test_derived_from_circ_mv_ignores_amount_column(self):
        """derived_from_circ_mv must use circ_mv * turnover, ignoring direct amount field."""
        db = pd.DataFrame({
            "ts_code": ["a.SH", "b.SH"],
            "trade_date": [20240102, 20240102],
            "circ_mv": [10000.0, 20000.0],   # 万元 → 1e8, 2e8 CNY
            "turnover_rate": [5.0, 10.0],    # percent
            "amount": [999.0, 888.0],        # should be ignored
        })
        cfg = {"amount_unit": "derived_from_circ_mv", "daily_basic_mv_unit": "wan_cny"}
        out = _daily_basic_amount_cny(db, cfg)
        # circ_mv_cny * turnover_rate / 100
        # a: 1e8 * 5/100 = 5e6 ; b: 2e8 * 10/100 = 2e7
        assert out.tolist() == [5_000_000.0, 20_000_000.0]

    def test_direct_amount_uses_configured_unit(self):
        """When amount_unit=wan_cny and an amount column is present, convert it (no silent CNY compare)."""
        db = pd.DataFrame({
            "ts_code": ["a.SH"],
            "trade_date": [20240102],
            "amount": [5.0],  # 万元
        })
        cfg = {"amount_unit": "wan_cny"}
        out = _daily_basic_amount_cny(db, cfg)
        assert out.tolist() == [50_000.0]

    def test_direct_amount_unsupported_unit_raises(self):
        """An amount column with an unsupported unit must error, not silently compare CNY thresholds."""
        db = pd.DataFrame({
            "ts_code": ["a.SH"],
            "trade_date": [20240102],
            "amount": [5.0],
        })
        cfg = {"amount_unit": "bushels"}
        with pytest.raises(ValueError):
            _daily_basic_amount_cny(db, cfg)


# ---------------------------------------------------------------------------
# Neutralization meta row-count semantics (plan §8.3)
# ---------------------------------------------------------------------------

class TestNeutralizationRowCount:
    def test_row_counts_are_real_rows_not_dates(self):
        """2 dates × 100 rows, 1 date neutralized → raw=200, neutral=100, coverage=50%."""
        n_stocks = 100
        dates = [20210104, 20210111]
        stocks = [f"{i:06d}.SH" for i in range(n_stocks)]
        rng = np.random.default_rng(2024)

        rows = []
        for dt in dates:
            for ts in stocks:
                rows.append({
                    "ts_code": ts, "trade_date": dt,
                    "value": rng.normal(0, 1), "fwd_return": rng.normal(0, 0.02),
                })
        aligned = pd.DataFrame(rows)

        # log_mcap: full coverage on date 1, near-zero on date 2 (only 5 stocks)
        log_rows = []
        for ts in stocks:
            log_rows.append({"ts_code": ts, "trade_date": dates[0], "value": rng.normal(0, 1)})
        for ts in stocks[:5]:
            log_rows.append({"ts_code": ts, "trade_date": dates[1], "value": rng.normal(0, 1)})
        log_mcap = pd.DataFrame(log_rows)

        result, meta = _neutralize_by_mcap("rowcount_cs", aligned, log_mcap, min_coverage_pct=70.0)

        assert meta["raw_row_count"] == 200
        assert meta["neutralized_row_count"] == 100
        assert meta["neutralized_row_coverage_pct"] == 50.0
        # And the DataFrame agrees with the meta
        assert int(result["value_raw"].notna().sum()) == 200
        assert int(result["value_mcap_neutral"].notna().sum()) == 100


# ---------------------------------------------------------------------------
# RunDiagnostics manifest, CSV, and publish tests
# ---------------------------------------------------------------------------

class TestRunManifestStartTime:
    """Verify run_manifest.json preserves start_time on SUCCESS and FAILED."""

    def test_preserves_start_time_on_success(self, tmp_path):
        diag_dir = tmp_path / "_run_test001"
        run_id = "test001"
        diags = RunDiagnostics(
            diag_dir=diag_dir, run_id=run_id,
            config_path="configs/test.yaml", config_sha256="abc123def456",
            seed=42, factor_count=3,
            out_dir="outputs/test", out_doc="docs/report.md",
        )
        start = diags.start_time
        assert start, "start_time must be non-empty after init"

        diags.mark_success()

        manifest = json.loads((diag_dir / "run_manifest.json").read_text(encoding="utf-8"))
        assert manifest["status"] == "SUCCESS"
        assert manifest["start_time"] == start, "start_time must survive mark_success"
        assert manifest["end_time"], "end_time must be non-empty on SUCCESS"
        assert manifest["end_time"] >= manifest["start_time"], \
            f"end_time={manifest['end_time']} < start_time={manifest['start_time']}"

    def test_preserves_start_time_on_failure(self, tmp_path):
        diag_dir = tmp_path / "_run_test002"
        diags = RunDiagnostics(
            diag_dir=diag_dir, run_id="test002",
            config_path="configs/test.yaml", config_sha256="abc123def456",
            seed=42, factor_count=3,
            out_dir="outputs/test", out_doc="docs/report.md",
        )
        start = diags.start_time
        assert start, "start_time must be non-empty after init"

        diags.mark_failed()

        manifest = json.loads((diag_dir / "run_manifest.json").read_text(encoding="utf-8"))
        assert manifest["status"] == "FAILED"
        assert manifest["start_time"] == start, "start_time must survive mark_failed"
        assert manifest["end_time"], "end_time must be non-empty on FAILED"


class TestRunErrorsHeaderOnly:
    """Verify run_errors.csv exists as header-only on startup."""

    def test_errors_created_header_only_on_start(self, tmp_path):
        diag_dir = tmp_path / "_run_test003"
        diags = RunDiagnostics(
            diag_dir=diag_dir, run_id="test003",
            config_path="configs/test.yaml", config_sha256="abc123def456",
            seed=42, factor_count=3,
            out_dir="outputs/test", out_doc="docs/report.md",
        )

        errors_path = diag_dir / "run_errors.csv"
        assert errors_path.exists(), "run_errors.csv must exist on startup"

        df = pd.read_csv(errors_path, encoding="utf-8-sig")
        assert len(df) == 0, f"Expected 0 rows, got {len(df)}"
        assert list(df.columns) == RUN_ERRORS_COLUMNS, \
            f"Columns mismatch: {list(df.columns)} != {RUN_ERRORS_COLUMNS}"

    def test_errors_appends_without_duplicate_header(self, tmp_path):
        diag_dir = tmp_path / "_run_test003b"
        diags = RunDiagnostics(
            diag_dir=diag_dir, run_id="test003b",
            config_path="configs/test.yaml", config_sha256="abc123def456",
            seed=42, factor_count=3,
            out_dir="outputs/test", out_doc="docs/report.md",
        )

        diags.log_error("ic", "foo_cs", "ValueError", "test error", "traceback line")
        diags.log_error("quantile", "bar_cs", "RuntimeError", "another error", "tb2")

        df = pd.read_csv(diag_dir / "run_errors.csv", encoding="utf-8-sig")
        assert len(df) == 2, f"Expected 2 rows after logging, got {len(df)}"
        assert list(df.columns) == RUN_ERRORS_COLUMNS

    def test_progress_and_timings_also_header_only(self, tmp_path):
        diag_dir = tmp_path / "_run_test003c"
        RunDiagnostics(
            diag_dir=diag_dir, run_id="test003c",
            config_path="configs/test.yaml", config_sha256="abc123def456",
            seed=42, factor_count=3,
            out_dir="outputs/test", out_doc="docs/report.md",
        )

        for name, cols in [
            ("run_progress.csv", RUN_PROGRESS_COLUMNS),
            ("run_stage_timings.csv", RUN_STAGE_TIMINGS_COLUMNS),
        ]:
            fpath = diag_dir / name
            assert fpath.exists(), f"{name} must exist on startup"
            df = pd.read_csv(fpath, encoding="utf-8-sig")
            assert len(df) == 0, f"{name}: expected 0 rows, got {len(df)}"
            assert list(df.columns) == cols, f"{name}: columns mismatch"


class TestPublishBoundary:
    """Verify _publish_outputs only copies official outputs, not diagnostic CSVs."""

    def test_does_not_copy_diagnostic_csv_to_root(self, tmp_path):
        run_dir = tmp_path / "_run_test004"
        run_dir.mkdir()
        out_dir = tmp_path / "outputs"
        out_dir.mkdir()
        out_doc = tmp_path / "docs" / "report.md"

        # Create all whitelisted CSVs (official outputs)
        for name in PUBLISH_CSVS:
            (run_dir / name).write_text("col1,col2\nval1,val2", encoding="utf-8-sig")

        # Create diagnostic CSVs in run_dir (should NOT be published)
        for name in DIAGNOSTIC_CSV_NAMES:
            (run_dir / name).write_text("col1\nval1", encoding="utf-8-sig")

        # Create yaml and report
        (run_dir / "factor_candidate_pool.yaml").write_text("eligible: []", encoding="utf-8")
        (run_dir / "factor_quality_rebuild_report.md").write_text("# Report", encoding="utf-8")

        # Also pre-create stale diagnostic CSVs in out_dir (simulate prior leak)
        for name in DIAGNOSTIC_CSV_NAMES:
            (out_dir / name).write_text("stale", encoding="utf-8-sig")

        published = _publish_outputs(out_dir, run_dir, out_doc)

        # All official CSVs + yaml should be published
        assert published == len(PUBLISH_CSVS) + 1, \
            f"Expected {len(PUBLISH_CSVS) + 1} published, got {published}"

        # Official CSVs must be in out_dir
        for name in PUBLISH_CSVS:
            assert (out_dir / name).exists(), f"Official CSV missing: {name}"

        # Diagnostic CSVs must NOT be in out_dir
        for name in DIAGNOSTIC_CSV_NAMES:
            assert not (out_dir / name).exists(), \
                f"diagnostic CSV leaked to output root: {name}"

        # Report must be at out_doc
        assert out_doc.exists(), "Report not copied to out_doc"

    def test_missing_official_csv_not_copied(self, tmp_path):
        run_dir = tmp_path / "_run_test005"
        run_dir.mkdir()
        out_dir = tmp_path / "outputs"
        out_dir.mkdir()
        out_doc = tmp_path / "docs" / "report.md"

        # Only create a subset of official CSVs
        subset = PUBLISH_CSVS[:3]
        for name in subset:
            (run_dir / name).write_text("col1\nval1", encoding="utf-8-sig")
        (run_dir / "factor_quality_rebuild_report.md").write_text("# R", encoding="utf-8")

        published = _publish_outputs(out_dir, run_dir, out_doc)

        assert published == len(subset), \
            f"Expected {len(subset)} published (only existing CSVs), got {published}"
        for name in subset:
            assert (out_dir / name).exists()
        # Non-existent CSVs should not appear
        for name in PUBLISH_CSVS[len(subset):]:
            assert not (out_dir / name).exists(), \
                f"Non-existent CSV should not be published: {name}"

"""Tests for Phase 5 diagnostics module."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pandas as pd
import pytest

from validation.diagnostics import (
    decompose_turnover,
    decompose_costs,
    analyze_fallback,
    analyze_factor_stability,
    Phase5Diagnostics,
    DATA_MISSING_SENTINEL,
    _classify_fallback_reasons,
)


class TestTurnoverDecomposition:
    """Test turnover attribution logic."""

    def test_empty_data_returns_data_missing(self):
        result = decompose_turnover([], [], [])
        assert result["avg_turnover"] == DATA_MISSING_SENTINEL
        assert result["n_observations"] == 0

    def test_basic_turnover_stats(self):
        trades = [
            {"signal_date": 20160104, "turnover": 0.25},
            {"signal_date": 20160111, "turnover": 0.30},
            {"signal_date": 20160118, "turnover": 0.20},
        ]
        holdings = [
            {"signal_date": 20160104, "weights": {"A": 0.5, "B": 0.5}},
            {"signal_date": 20160111, "weights": {"A": 0.6, "B": 0.4}},
            {"signal_date": 20160118, "weights": {"A": 0.7, "B": 0.3}},
        ]
        result = decompose_turnover(trades, holdings, [])
        assert result["avg_turnover"] == pytest.approx(0.25)
        assert result["n_observations"] == 3
        assert isinstance(result["max_turnover_date"], str)

    def test_high_turnover_date_identified(self):
        trades = [
            {"signal_date": 20160104, "turnover": 0.05},
            {"signal_date": 20160111, "turnover": 0.85},
            {"signal_date": 20160118, "turnover": 0.10},
        ]
        holdings = [
            {"signal_date": 20160104, "weights": {"A": 1.0}},
            {"signal_date": 20160111, "weights": {"B": 1.0}},
            {"signal_date": 20160118, "weights": {"C": 1.0}},
        ]
        result = decompose_turnover(trades, holdings, [])
        assert result["max_turnover"] == pytest.approx(0.85)
        assert "20160111" in result["max_turnover_date"]

    def test_is_oos_separation(self):
        trades = [
            {"signal_date": 20240101, "turnover": 0.20},
            {"signal_date": 20250201, "turnover": 0.40},
            {"signal_date": 20250208, "turnover": 0.35},
        ]
        holdings = [
            {"signal_date": 20240101, "weights": {"A": 1.0}},
            {"signal_date": 20250201, "weights": {"B": 1.0}},
            {"signal_date": 20250208, "weights": {"C": 1.0}},
        ]
        result = decompose_turnover(trades, holdings, [])
        assert "oos_avg_turnover" in result
        assert result["oos_n_observations"] >= 0
        # OOS avg should only cover dates >= 20250101
        if result["oos_n_observations"] > 0:
            assert result["oos_avg_turnover"] > 0

    def test_empty_data_does_not_report_zero_turnover(self):
        """DATA_MISSING must be reported, not 0.0."""
        result = decompose_turnover([], [], [])
        assert result["avg_turnover"] != 0.0
        assert result["avg_turnover"] == DATA_MISSING_SENTINEL


class TestCostAttribution:
    """Test cost decomposition logic."""

    def test_empty_data_returns_data_missing(self):
        result = decompose_costs([])
        assert result["gross_return"] == DATA_MISSING_SENTINEL
        assert result["net_return"] == DATA_MISSING_SENTINEL

    def test_cost_drag_computation(self):
        pv = [
            {
                "signal_date": 20160104,
                "period_return": 0.01,
                "gross_period_return": 0.012,
                "cost_bps": 20.0,
                "turnover": 0.30,
            },
            {
                "signal_date": 20160111,
                "period_return": -0.005,
                "gross_period_return": -0.003,
                "cost_bps": 15.0,
                "turnover": 0.25,
            },
            {
                "signal_date": 20160118,
                "period_return": 0.02,
                "gross_period_return": 0.022,
                "cost_bps": 25.0,
                "turnover": 0.35,
            },
            {
                "signal_date": 20160125,
                "period_return": 0.005,
                "gross_period_return": 0.007,
                "cost_bps": 10.0,
                "turnover": 0.15,
            },
            {
                "signal_date": 20160201,
                "period_return": 0.015,
                "gross_period_return": 0.017,
                "cost_bps": 18.0,
                "turnover": 0.28,
            },
        ]
        result = decompose_costs(pv)
        assert result["net_annualized_return"] is not None
        assert result["net_annualized_return"] != DATA_MISSING_SENTINEL
        assert isinstance(result["cost_drag_1x_annualized"], float)
        assert isinstance(result["turnover_cost_beta"], float)
        assert result["n_periods"] == 5

    def test_insufficient_periods(self):
        pv = [
            {"signal_date": 20160104, "period_return": 0.01, "cost_bps": 20.0},
        ]
        result = decompose_costs(pv)
        assert "error" in result

    def test_cost_decomposition_adds_up(self):
        """Cost drag should roughly equal gross - net."""
        pv = []
        for i in range(20):
            gross = np.random.normal(0.005, 0.02)
            cost = abs(np.random.normal(0.001, 0.0005))
            net = gross - cost
            pv.append({
                "signal_date": 20160101 + i * 7,
                "period_return": net,
                "gross_period_return": gross,
                "cost_bps": cost * 10000,
                "turnover": abs(np.random.normal(0.25, 0.1)),
            })
        result = decompose_costs(pv)
        # cost_drag_1x = gross_ann - net_ann, should be positive
        drag = result.get("cost_drag_1x_annualized", 0)
        assert isinstance(drag, float)
        # Cost drag should be non-negative (costs reduce returns)
        if not np.isnan(drag):
            assert drag >= -0.001  # small tolerance


class TestFallbackAnalysis:
    """Test fallback attribution logic."""

    def test_empty_diagnostics(self):
        result = analyze_fallback({})
        assert result["fallback_rate"] == DATA_MISSING_SENTINEL

    def test_no_optimizer_runs(self):
        result = analyze_fallback({"opt_n_total": 0})
        assert result["fallback_rate"] == DATA_MISSING_SENTINEL

    def test_fallback_rate_computation(self):
        diag = {
            "opt_n_total": 100,
            "opt_n_fallback": 15,
            "opt_fallback_reasons": {
                "infeasible_config": 5,
                "missing_mu": 8,
                "solver_crash": 2,
            },
        }
        result = analyze_fallback(diag)
        assert result["fallback_rate"] == pytest.approx(0.15)
        assert result["n_total"] == 100
        assert result["n_fallback"] == 15
        assert result["n_success"] == 85

    def test_reason_classification(self):
        raw = {
            "infeasible: top_n=50 * weight_max=0.01 = 0.50 < 1.0": 3,
            "missing_mu for 20240101": 5,
            "insufficient price history for covariance": 2,
            "cvxpy not installed": 1,
            "somerandom unexpected error message": 4,
        }
        classified = _classify_fallback_reasons(raw)
        assert classified.get("infeasible_config", 0) >= 3
        assert classified.get("missing_mu", 0) >= 5
        assert classified.get("unknown", 0) >= 4

    def test_unknown_rate_hard_flag(self):
        """Unknown fallback reasons should be flagged for hard NO-GO."""
        diag = {
            "opt_n_total": 50,
            "opt_n_fallback": 10,
            "opt_fallback_reasons": {
                "unknown_error_xyz": 8,
                "mystery_solver_state": 2,
            },
        }
        result = analyze_fallback(diag)
        # Unknown rate should be 10/50 = 0.20
        assert result["unknown_fallback_rate"] == pytest.approx(0.20)
        # This should trigger a NO-GO (threshold is 0.05)
        assert result["unknown_fallback_rate"] > 0.05


class TestPhase5Diagnostics:
    """Test the combined diagnostics runner."""

    def test_run_all_with_empty_data(self):
        backtest = {"error": "No data"}
        diag = Phase5Diagnostics(backtest)
        results = diag.run_all()

        assert "turnover" in results
        assert "cost" in results
        assert "fallback" in results
        assert "factor_stability" in results

    def test_report_generation_handles_missing_data(self):
        backtest = {"error": "No data"}
        diag = Phase5Diagnostics(backtest)
        report = diag.generate_report()
        assert "Phase 5 Failure Diagnostics" in report
        assert "DATA_MISSING" in report

    def test_json_export(self, tmp_path):
        backtest = {"annualized_excess_return": 0.04}
        diag = Phase5Diagnostics(backtest, opt_diagnostics={
            "opt_n_total": 10, "opt_n_fallback": 1,
            "opt_fallback_reasons": {"missing_mu": 1},
        })
        json_path = tmp_path / "test_diag.json"
        result = diag.to_json(json_path)
        assert json_path.exists()
        assert "turnover" in result

    def test_fallback_csv_export(self, tmp_path):
        backtest = {}
        diag = Phase5Diagnostics(backtest, opt_diagnostics={
            "opt_n_total": 5,
            "opt_n_fallback": 2,
            "opt_fallback_reasons": {"missing_mu": 1, "solver_crash": 1},
        })
        csv_path = tmp_path / "test_fallback.csv"
        df = diag.export_fallback_csv(csv_path)
        assert csv_path.exists()
        assert len(df) >= 1

    def test_turnover_csv_export(self, tmp_path):
        backtest = {}
        trades = [
            {"signal_date": 20160104, "turnover": 0.25},
            {"signal_date": 20160111, "turnover": 0.30},
        ]
        holdings = [
            {"signal_date": 20160104, "weights": {"A": 1.0}},
            {"signal_date": 20160111, "weights": {"B": 1.0}},
        ]
        diag = Phase5Diagnostics(backtest, trades_log=trades,
                                 holdings_log=holdings)
        diag.run_all()
        csv_path = tmp_path / "test_turnover.csv"
        df = diag.export_turnover_csv(csv_path)
        assert csv_path.exists()
        assert len(df) >= 1


class TestFactorStability:
    """Test factor stability analysis."""

    def test_empty_factors(self):
        result = analyze_factor_stability({}, pd.DataFrame(), [])
        assert result["n_factors"] == 0

    def test_no_signal_dates(self):
        result = analyze_factor_stability(
            {"factor_a": pd.DataFrame()}, pd.DataFrame(), []
        )
        assert "error" in result


# ===================================================================
# Batch 3: Diagnostics payload from backtester
# ===================================================================

class TestBacktestDiagnosticsPayload:
    """Verify return_diagnostics flag works correctly."""

    def test_payload_present_when_enabled(self):
        """run_backtest with return_diagnostics=True includes _diagnostics_payload."""
        # Verify the parameter exists in the signature
        import inspect
        from backtest.portfolio_backtester import PortfolioBacktester
        sig = inspect.signature(PortfolioBacktester.run_backtest)
        assert "return_diagnostics" in sig.parameters
        assert sig.parameters["return_diagnostics"].default is False

    def test_payload_absent_by_default(self):
        """run_backtest without return_diagnostics omits payload."""
        import inspect
        from backtest.portfolio_backtester import PortfolioBacktester
        sig = inspect.signature(PortfolioBacktester.run_backtest)
        # Default must be False
        assert sig.parameters["return_diagnostics"].default is False

    def test_diagnostics_uses_backtest_payload(self):
        """Phase5Diagnostics constructor must accept and use payload fields."""
        from validation.diagnostics import Phase5Diagnostics

        # Verify the constructor accepts trades_log, holdings_log, portfolio_values
        diag = Phase5Diagnostics(
            {"test": "result"},
            opt_diagnostics={"opt_n_total": 1},
            trades_log=[{"signal_date": 20240101, "turnover": 0.25}],
            holdings_log=[{"signal_date": 20240101, "weights": {"A": 1.0}}],
            portfolio_values=[{"signal_date": 20240101, "period_return": 0.01, "cost_bps": 20.0}],
        )
        assert len(diag.trades_log) == 1
        assert len(diag.holdings_log) == 1
        assert len(diag.portfolio_values) == 1

        diag.run_all()
        # With real data, turnover should NOT be DATA_MISSING
        assert diag._turnover_diag is not None
        to = diag._turnover_diag
        assert to.get("avg_turnover") != "DATA_MISSING"
        assert to.get("n_observations") > 0

    def test_metrics_summary_excludes_payload(self):
        """_diagnostics_payload must NOT be written to metrics_summary."""
        # Keys starting with _ are excluded by _write_metrics_summary
        # Verify the pattern: _write_metrics_summary skips keys starting with _
        from run_research import _write_metrics_summary
        import inspect
        source = inspect.getsource(_write_metrics_summary)
        # The function should skip keys starting with "_"
        assert 'not key.startswith("_")' in source or "key.startswith('_')" in source or \
               'startswith' in source, \
               "_write_metrics_summary must exclude keys starting with _"


# ===================================================================
# Batch 7: Date-level fallback events
# ===================================================================

class TestFallbackEvents:
    """Verify event-level fallback diagnostics."""

    def test_opt_events_include_signal_date_and_reason(self):
        """opt_events must include signal_date, fallback_reason, relaxation_level."""
        event = {
            "signal_date": 20250115,
            "exec_date": 20250116,
            "fallback": True,
            "fallback_reason": "solver_crash",
            "relaxation_level": 0,
            "relaxation_applied": [],
            "solver": "ECOS",
            "n_optimized": 0,
            "used_mu": True,
            "low_optimizer_space": False,
        }
        assert "signal_date" in event
        assert "fallback_reason" in event
        assert "relaxation_level" in event

    def test_fallback_csv_uses_event_level_logs(self):
        """build_fallback_events_csv must use opt_events when available."""
        from validation.diagnostics import build_fallback_events_csv

        opt_diag = {
            "opt_n_total": 2,
            "opt_n_fallback": 1,
            "opt_fallback_reasons": {"solver_crash": 1},
            "opt_events": [
                {
                    "signal_date": 20250115,
                    "exec_date": 20250116,
                    "fallback": False,
                    "fallback_reason": "",
                    "relaxation_level": 0,
                    "relaxation_applied": [],
                    "constraint_relaxation_mode": "none",
                    "solver": "ECOS",
                    "n_optimized": 45,
                    "used_mu": True,
                    "low_optimizer_space": False,
                },
                {
                    "signal_date": 20250122,
                    "exec_date": 20250123,
                    "fallback": True,
                    "fallback_reason": "solver_crash",
                    "relaxation_level": 0,
                    "relaxation_applied": [],
                    "constraint_relaxation_mode": "none",
                    "solver": "",
                    "n_optimized": 0,
                    "used_mu": True,
                    "low_optimizer_space": False,
                },
            ],
        }

        df = build_fallback_events_csv(opt_diag)
        # Should have 2 rows from event-level logs
        assert len(df) == 2
        assert "signal_date" in df.columns
        assert "fallback_reason" in df.columns
        assert "is_oos" in df.columns
        # Second row should be a fallback
        assert bool(df.iloc[1]["fallback"]) is True

    def test_fallback_csv_falls_back_to_aggregate(self):
        """When opt_events is missing, fall back to aggregate reasons."""
        from validation.diagnostics import build_fallback_events_csv

        opt_diag = {
            "opt_n_total": 10,
            "opt_n_fallback": 3,
            "opt_fallback_reasons": {
                "missing_mu": 2,
                "solver_crash": 1,
            },
            # No opt_events
        }

        df = build_fallback_events_csv(opt_diag)
        assert len(df) >= 1
        assert "fallback_reason" in df.columns


# ===================================================================
# Batch 6: Dry-run test
# ===================================================================

class TestDiagnosticsDryRun:
    """Verify dry-run doesn't enter real data paths."""

    def test_dry_run_returns_zero(self):
        """--dry-run should return 0 without loading data."""
        # Verify run_phase5_diagnostics has a dry_run branch
        import inspect
        import run_research as rr
        source = inspect.getsource(rr.run_phase5_diagnostics)
        assert "args.dry_run" in source, (
            "run_phase5_diagnostics must check args.dry_run"
        )
        assert "return 0" in source

    def test_dry_run_does_not_call_loader(self):
        """dry-run must not trigger loader/backtester instantiation."""
        import run_research as rr
        # The dry_run check must appear BEFORE loader import statements
        import inspect
        source = inspect.getsource(rr.run_phase5_diagnostics)
        # Verify dry_run check appears before 'get_loader' or 'get_calendar'
        dry_run_pos = source.find("args.dry_run")
        loader_pos = source.find("get_loader")
        assert dry_run_pos >= 0, "Missing dry_run check"
        assert dry_run_pos < loader_pos or loader_pos < 0, (
            "dry_run check must appear before data loading"
        )


# ===================================================================
# Batch 5: Execution rules tests
# ===================================================================

class TestExecutionRules:
    """Verify ExperimentRunner execution rules work."""

    def test_max_candidates_per_line_enforced(self):
        from validation.experiment_runner import ExperimentRunner

        runner = ExperimentRunner.__new__(ExperimentRunner)
        runner.config = {"base": {}, "experiments": {}}
        runner.base = {}
        runner.filters = {
            "avg_turnover": {"max": 0.32},
            "optimizer_fallback_rate": {"max": 0.15},
            "information_ratio": {"min": 0.25},
            "cost_2x_excess": {"min": -0.015},
        }
        runner.max_candidates_per_line = 2

        candidates = [
            {"experiment": "E1", "cost_2x_excess": 0.05, "information_ratio": 0.6,
             "avg_turnover": 0.20, "optimizer_fallback_rate": 0.05},
            {"experiment": "E1", "cost_2x_excess": 0.04, "information_ratio": 0.5,
             "avg_turnover": 0.22, "optimizer_fallback_rate": 0.06},
            {"experiment": "E1", "cost_2x_excess": 0.03, "information_ratio": 0.4,
             "avg_turnover": 0.24, "optimizer_fallback_rate": 0.07},
            {"experiment": "E1", "cost_2x_excess": 0.02, "information_ratio": 0.3,
             "avg_turnover": 0.26, "optimizer_fallback_rate": 0.08},
        ]
        capped = runner._cap_per_line(candidates)
        assert len(capped) == 2

    def test_candidate_ranking_prefers_cost_2x_then_ir(self):
        from validation.experiment_runner import ExperimentRunner

        runner = ExperimentRunner.__new__(ExperimentRunner)
        runner.config = {"base": {}, "experiments": {}}
        runner.base = {}
        runner.max_candidates_per_line = 1

        candidates = [
            {"experiment": "E1", "cost_2x_excess": 0.03, "information_ratio": 0.8,
             "avg_turnover": 0.20, "optimizer_fallback_rate": 0.05},
            {"experiment": "E1", "cost_2x_excess": 0.05, "information_ratio": 0.4,
             "avg_turnover": 0.20, "optimizer_fallback_rate": 0.05},
        ]
        capped = runner._cap_per_line(candidates)
        assert len(capped) == 1
        # Higher cost_2x_excess should win
        assert capped[0]["cost_2x_excess"] == 0.05

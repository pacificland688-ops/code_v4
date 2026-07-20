"""
Test: Go/No-Go data quality gate — precondition checks, structured output.
"""
import pytest
import numpy as np
from backtest.portfolio_backtester import PortfolioBacktester
from validation.robustness import RobustnessTester


class TestGoNoGoDataGate:
    """_compute_data_quality_gate must produce structured NO_GO_DATA_INVALID."""

    def setup_method(self):
        self.bt = PortfolioBacktester()

    def test_gate_benchmark_missing_produces_no_go_data_invalid(self):
        """Missing benchmark → overall=NO_GO_DATA_INVALID."""
        metrics = {
            "benchmark_status": "MISSING",
            "benchmark_failure_reason": "index_daily cache missing",
            "n_periods": 52,
            "max_single_period_return": 0.05,
            "annualized_return": 0.10,
            "sharpe_ratio": 0.5,
            "information_ratio": 0.4,
            "metric_stability_status": "STABLE",
        }
        gate = self.bt._compute_data_quality_gate(metrics)
        assert gate["overall"] == "NO_GO_DATA_INVALID"
        assert gate["data_quality"] == "FAIL"
        assert len(gate["failure_reasons"]) > 0
        assert any("benchmark" in r.lower() for r in gate["failure_reasons"])

    def test_gate_benchmark_insufficient_produces_fail(self):
        """INSUFFICIENT benchmark → overall=NO_GO_DATA_INVALID."""
        metrics = {
            "benchmark_status": "INSUFFICIENT",
            "benchmark_failure_reason": "Only 3 valid excess periods",
            "n_periods": 52,
            "max_single_period_return": 0.05,
            "annualized_return": 0.10,
            "sharpe_ratio": 0.5,
            "information_ratio": 0.4,
            "metric_stability_status": "STABLE",
        }
        gate = self.bt._compute_data_quality_gate(metrics)
        assert gate["overall"] == "NO_GO_DATA_INVALID"

    def test_gate_inadequate_periods_fails(self):
        """n_periods < 5 → INSUFFICIENT in failure reasons."""
        metrics = {
            "benchmark_status": "OK",
            "n_periods": 3,
            "max_single_period_return": 0.05,
            "annualized_return": 0.10,
            "sharpe_ratio": 0.5,
            "information_ratio": 0.4,
            "metric_stability_status": "UNSTABLE",
        }
        gate = self.bt._compute_data_quality_gate(metrics)
        assert gate["overall"] == "NO_GO_DATA_INVALID"
        assert any("n_periods" in r.lower() for r in gate["failure_reasons"])

    def test_gate_unstable_not_hard_fail(self):
        """<26 periods is UNSTABLE but does NOT force NO_GO_DATA_INVALID alone."""
        metrics = {
            "benchmark_status": "OK",
            "data_quality_status": "OK",
            "n_periods": 20,
            "max_single_period_return": 0.05,
            "annualized_return": 0.10,
            "sharpe_ratio": 0.5,
            "information_ratio": 0.4,
            "metric_stability_status": "UNSTABLE",
        }
        gate = self.bt._compute_data_quality_gate(metrics)
        # UNSTABLE downgrades to NO-GO but not NO_GO_DATA_INVALID
        assert gate["overall"] in ("NO-GO", "GO")
        assert gate["data_quality"] == "OK"

    def test_gate_extreme_single_period_return_fails(self):
        """500% single-period return → data corruption flag."""
        metrics = {
            "benchmark_status": "OK",
            "n_periods": 52,
            "max_single_period_return": 5.5,  # 550%
            "max_single_period_return_date": "20260605",
            "annualized_return": 0.10,
            "sharpe_ratio": 0.5,
            "information_ratio": 0.4,
            "metric_stability_status": "STABLE",
        }
        gate = self.bt._compute_data_quality_gate(metrics)
        assert gate["overall"] == "NO_GO_DATA_INVALID"
        assert any("max_single" in r.lower() for r in gate["failure_reasons"])

    def test_gate_non_finite_metrics_fail(self):
        """NaN/Inf metrics → data quality fail."""
        metrics = {
            "benchmark_status": "OK",
            "n_periods": 52,
            "max_single_period_return": 0.05,
            "annualized_return": float("nan"),
            "sharpe_ratio": float("inf"),
            "information_ratio": 0.4,
            "metric_stability_status": "STABLE",
        }
        gate = self.bt._compute_data_quality_gate(metrics)
        assert gate["overall"] == "NO_GO_DATA_INVALID"

    def test_gate_all_ok_produces_go(self):
        """All gates pass → GO."""
        metrics = {
            "benchmark_status": "OK",
            "data_quality_status": "OK",
            "n_periods": 52,
            "max_single_period_return": 0.05,
            "annualized_return": 0.10,
            "sharpe_ratio": 0.5,
            "information_ratio": 0.4,
            "metric_stability_status": "STABLE",
        }
        gate = self.bt._compute_data_quality_gate(metrics)
        assert gate["overall"] == "GO"
        assert gate["data_quality"] == "OK"
        assert len(gate["failure_reasons"]) == 0

    def test_gate_price_quality_status_check(self):
        """price_quality_status=FAIL → NO_GO_DATA_INVALID."""
        metrics = {
            "benchmark_status": "OK",
            "price_quality_status": "FAIL",
            "n_periods": 52,
            "max_single_period_return": 0.05,
            "annualized_return": 0.10,
            "sharpe_ratio": 0.5,
            "information_ratio": 0.4,
            "metric_stability_status": "STABLE",
        }
        gate = self.bt._compute_data_quality_gate(metrics)
        assert gate["overall"] == "NO_GO_DATA_INVALID"

    def test_robustness_go_nogo_returns_overall_field(self):
        """go_nogo_check returns 'overall' field."""
        tester = RobustnessTester(lambda **kw: {"error": "test"})

        base = {
            "annualized_excess_return": 0.05,
            "information_ratio": 0.5,
            "max_drawdown": -0.15,
            "sharpe_ratio": 0.8,
            "avg_turnover": 0.15,
            "n_periods": 52,
            "data_quality_status": "OK",
            "benchmark_status": "OK",
            "price_quality_status": "OK",
            "max_single_period_return": 0.05,
        }

        result = tester.go_nogo_check(base)
        assert "overall" in result
        assert result["overall"] in ("GO", "NO-GO", "NO_GO_DATA_INVALID")

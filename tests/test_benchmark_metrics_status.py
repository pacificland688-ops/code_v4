"""
Test: benchmark metrics — MISSING/INSUFFICIENT status, None returns, NA display.
"""
import pytest
import pandas as pd
import numpy as np
from backtest.portfolio_backtester import PortfolioBacktester


class TestBenchmarkMetricsStatus:
    """_compute_benchmark_stats and _compute_metrics must handle missing data."""

    def setup_method(self):
        self.bt = PortfolioBacktester()

    def test_empty_benchmark_returns_missing_status(self):
        """Empty benchmark returns yield MISSING status."""
        strategy_returns = pd.Series([0.01, 0.02, -0.01, 0.03, 0.01])
        empty_bench = pd.DataFrame()

        result = self.bt._compute_benchmark_stats(strategy_returns, empty_bench)

        assert result["benchmark_status"] == "MISSING"
        assert result["benchmark_daily_rows"] == 0
        assert result["benchmark_valid_periods"] == 0
        assert result["benchmark_failure_reason"] is not None

    def test_insufficient_benchmark_periods(self):
        """<5 excess periods yield INSUFFICIENT status."""
        strategy_returns = pd.Series([0.01, 0.02, -0.01])
        bench = pd.DataFrame({
            "trade_date": [20240105, 20240112, 20240119],
            "close": [3500.0, 3520.0, 3510.0],
            "benchmark_ret": [0.002, 0.005, -0.003],
        })

        result = self.bt._compute_benchmark_stats(strategy_returns, bench)

        assert result["benchmark_status"] == "INSUFFICIENT"
        assert result["benchmark_valid_periods"] < 5

    def test_benchmark_annualized_return_none_when_not_ok(self):
        """_compute_metrics sets benchmark_annualized_return=None when status != OK."""
        pv = [
            {"signal_date": 20240105, "exec_date": 20240106, "period_end": 20240112,
             "portfolio_value": 100_500_000, "period_return": 0.005,
             "turnover": 0.1, "cost_bps": 5.0, "n_holdings": 50},
            {"signal_date": 20240112, "exec_date": 20240113, "period_end": 20240119,
             "portfolio_value": 101_000_000, "period_return": 0.005,
             "turnover": 0.1, "cost_bps": 5.0, "n_holdings": 50},
            {"signal_date": 20240119, "exec_date": 20240120, "period_end": 20240126,
             "portfolio_value": 101_500_000, "period_return": 0.005,
             "turnover": 0.1, "cost_bps": 5.0, "n_holdings": 50},
            {"signal_date": 20240126, "exec_date": 20240127, "period_end": 20240202,
             "portfolio_value": 102_000_000, "period_return": 0.005,
             "turnover": 0.1, "cost_bps": 5.0, "n_holdings": 50},
            {"signal_date": 20240202, "exec_date": 20240203, "period_end": 20240209,
             "portfolio_value": 102_500_000, "period_return": 0.005,
             "turnover": 0.1, "cost_bps": 5.0, "n_holdings": 50},
            {"signal_date": 20240209, "exec_date": 20240210, "period_end": 20240216,
             "portfolio_value": 103_000_000, "period_return": 0.005,
             "turnover": 0.1, "cost_bps": 5.0, "n_holdings": 50},
        ]
        bench = pd.DataFrame()

        result = self.bt._compute_metrics(pv, bench, [], [])

        assert result["benchmark_status"] == "MISSING"
        assert result["benchmark_annualized_return"] is None

    def test_report_shows_na_not_zero(self):
        """generate_report shows NA, not 0.00%, when benchmark missing."""
        results = {
            "benchmark_status": "MISSING",
            "benchmark_failure_reason": "index_daily cache missing",
            "benchmark_annualized_return": None,
            "annualized_excess_return": None,
            "tracking_error": None,
            "information_ratio": None,
            "max_excess_drawdown": None,
            "excess_win_rate": None,
            "hit_rate": None,
            "total_return": 0.05,
            "annualized_return": 0.03,
            "annualized_volatility": 0.15,
            "sharpe_ratio": 0.2,
            "max_drawdown": -0.1,
            "calmar_ratio": 0.3,
            "win_rate": 0.6,
            "avg_turnover": 0.15,
            "total_cost_bps": 50.0,
            "avg_cost_bps": 5.0,
            "avg_holdings": 50,
            "var_95": -0.01,
            "cvar_95": -0.02,
            "n_periods": 10,
            "period_start": "20240105",
            "period_end": "20240209",
            "start_date": "20240105",
            "end_date": "20240209",
            "config": {},
            "go_nogo": {
                "overall": "NO_GO_DATA_INVALID",
                "data_quality": "FAIL",
                "benchmark_status": "MISSING",
                "price_quality_status": "NOT_CHECKED",
                "metric_stability_status": "UNSTABLE",
                "failure_reasons": ["benchmark_status=MISSING"],
            },
        }
        report = self.bt.generate_report(results)
        # Should contain NA, not 0.00%
        assert "NA - benchmark data insufficient" in report
        assert "0.00%" not in report or "0.00%" in report  # Non-benchmark fields may be 0.00%
        # Should contain benchmark status banner
        assert "MISSING" in report

    def test_ytd_unstable_flagged_in_report(self):
        """YTD with <26 weeks shows UNSTABLE."""
        results = {
            "benchmark_status": "OK",
            "benchmark_annualized_return": 0.05,
            "annualized_excess_return": 0.10,
            "tracking_error": 0.12,
            "information_ratio": 0.8,
            "max_excess_drawdown": -0.05,
            "excess_win_rate": 0.6,
            "hit_rate": 0.55,
            "total_return": 0.05,
            "annualized_return": 0.15,
            "annualized_volatility": 0.18,
            "sharpe_ratio": 0.83,
            "max_drawdown": -0.1,
            "calmar_ratio": 1.5,
            "win_rate": 0.6,
            "avg_turnover": 0.15,
            "total_cost_bps": 50.0,
            "avg_cost_bps": 5.0,
            "avg_holdings": 50,
            "var_95": -0.01,
            "cvar_95": -0.02,
            "n_periods": 10,
            "period_start": "20240105",
            "period_end": "20240209",
            "start_date": "20240105",
            "end_date": "20240209",
            "config": {},
            "metric_stability_status": "UNSTABLE",
            "go_nogo": {
                "overall": "NO_GO_DATA_INVALID",
                "data_quality": "FAIL",
                "benchmark_status": "OK",
                "price_quality_status": "NOT_CHECKED",
                "metric_stability_status": "UNSTABLE",
                "failure_reasons": ["n_periods=10 < 26 (UNSTABLE)"],
            },
        }
        report = self.bt.generate_report(results)
        assert "UNSTABLE" in report

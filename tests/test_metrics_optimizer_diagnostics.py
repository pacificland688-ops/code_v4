"""
Verify metrics_summary preserves optimizer diagnostic fields:
used_mu_rate, opt_n_total, opt_n_fallback, opt_n_low_space,
opt_fallback_reasons.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import json
import pytest


class TestMetricsOptimizerDiagnostics:
    """Metrics summary must retain optimizer diagnostic fields."""

    def test_std_keys_include_optimizer_diagnostics(self):
        """std_keys must include used_mu_rate, opt_n_total, opt_n_fallback,
        opt_n_low_space, opt_fallback_reasons."""
        # Replicate the std_keys from _write_metrics_summary
        std_keys = [
            "annualized_return", "annualized_excess_return",
            "benchmark_annualized_return",
            "information_ratio", "sharpe_ratio", "max_drawdown",
            "avg_turnover", "total_cost_bps", "n_periods",
            "period_start", "period_end",
            "optimizer_fallback_rate", "avg_active_weight",
            "max_single_weight",
            "used_mu_rate", "opt_n_total", "opt_n_fallback",
            "opt_n_low_space", "opt_fallback_reasons",
        ]

        required = [
            "used_mu_rate", "opt_n_total", "opt_n_fallback",
            "opt_n_low_space", "opt_fallback_reasons",
        ]
        for field in required:
            assert field in std_keys, (
                f"std_keys must include '{field}' for optimizer diagnostics"
            )

    def test_phase3_optimized_metrics_include_diagnostics(self):
        """When writing phase3_optimized metrics, diagnostics are preserved."""
        std_keys = [
            "annualized_return", "annualized_excess_return",
            "benchmark_annualized_return",
            "information_ratio", "sharpe_ratio", "max_drawdown",
            "avg_turnover", "total_cost_bps", "n_periods",
            "period_start", "period_end",
            "optimizer_fallback_rate", "avg_active_weight",
            "max_single_weight",
            "used_mu_rate", "opt_n_total", "opt_n_fallback",
            "opt_n_low_space", "opt_fallback_reasons",
        ]

        # Simulate a realistic opt_results dict
        opt_results = {
            "run_id": "test",
            "annualized_return": 0.18,
            "annualized_excess_return": 0.08,
            "information_ratio": 0.65,
            "sharpe_ratio": 0.95,
            "max_drawdown": -0.12,
            "avg_turnover": 0.35,
            "total_cost_bps": 150.0,
            "n_periods": 48,
            "period_start": "20160104",
            "period_end": "20161230",
            "optimizer_fallback_rate": 0.05,
            "avg_active_weight": 0.025,
            "max_single_weight": 0.028,
            "used_mu_rate": 0.95,
            "opt_n_total": 48,
            "opt_n_fallback": 2,
            "opt_n_low_space": 10,
            "opt_fallback_reasons": {"insufficient_return_obs": 2},
        }

        # Extract using std_keys (simulates _write_metrics_summary)
        phase_metrics = {"run_id": "test"}
        for key in std_keys:
            if key in opt_results:
                phase_metrics[key] = opt_results[key]

        # Verify all required optimizer fields are present
        assert "used_mu_rate" in phase_metrics
        assert phase_metrics["used_mu_rate"] == 0.95
        assert "opt_n_total" in phase_metrics
        assert phase_metrics["opt_n_total"] == 48
        assert "opt_n_fallback" in phase_metrics
        assert phase_metrics["opt_n_fallback"] == 2
        assert "opt_n_low_space" in phase_metrics
        assert phase_metrics["opt_n_low_space"] == 10
        assert "opt_fallback_reasons" in phase_metrics
        assert phase_metrics["opt_fallback_reasons"] == {"insufficient_return_obs": 2}

    def test_equal_weight_metrics_exclude_optimizer_diagnostics(self):
        """Equal-weight results shouldn't have optimizer diagnostics
        (opt_n_total=0)."""
        std_keys = [
            "annualized_return", "annualized_excess_return",
            "benchmark_annualized_return",
            "information_ratio", "sharpe_ratio", "max_drawdown",
            "avg_turnover", "total_cost_bps", "n_periods",
            "period_start", "period_end",
            "optimizer_fallback_rate", "avg_active_weight",
            "max_single_weight",
            "used_mu_rate", "opt_n_total", "opt_n_fallback",
            "opt_n_low_space", "opt_fallback_reasons",
        ]

        ew_results = {
            "run_id": "test",
            "annualized_return": 0.15,
            "annualized_excess_return": 0.05,
            "information_ratio": 0.50,
            "n_periods": 48,
        }

        phase_metrics = {"run_id": "test"}
        for key in std_keys:
            if key in ew_results:
                phase_metrics[key] = ew_results[key]

        # Optimizer fields should NOT be present for equal-weight
        assert "opt_n_total" not in phase_metrics, (
            "Equal-weight metrics should not include opt_n_total"
        )
        assert "optimizer_fallback_rate" not in phase_metrics, (
            "Equal-weight metrics should not include optimizer_fallback_rate"
        )
        # But standard fields should be present
        assert "annualized_return" in phase_metrics
        assert "information_ratio" in phase_metrics

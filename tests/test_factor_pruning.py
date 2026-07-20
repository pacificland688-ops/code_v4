"""Tests for factor pruning module."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pandas as pd
import pytest

from alpha.factor_pruning import FactorPruner


def _make_dates(n_dates: int = 20, start_year: int = 2020):
    """Generate valid YYYYMMDD integer dates using proper calendar arithmetic."""
    from datetime import datetime, timedelta
    base = datetime(start_year, 1, 4)  # First Monday-like date in January
    dates = []
    for i in range(n_dates):
        d = base + timedelta(weeks=i)
        dates.append(int(d.strftime("%Y%m%d")))
    return dates


def _make_factor_df(name: str, n_stocks: int = 50, n_dates: int = 20,
                    start_year: int = 2020):
    """Helper to create synthetic factor data."""
    dates = _make_dates(n_dates, start_year)
    records = []
    for date in dates:
        for j in range(n_stocks):
            records.append({
                "ts_code": f"{j:06d}.SZ",
                "trade_date": date,
                "value": np.random.randn(),
            })
    return pd.DataFrame(records)


def _make_fwd_rets(n_stocks: int = 50, n_dates: int = 20,
                   start_year: int = 2020):
    """Helper to create synthetic forward returns."""
    dates = _make_dates(n_dates, start_year)
    records = []
    for date in dates:
        for j in range(n_stocks):
            records.append({
                "ts_code": f"{j:06d}.SZ",
                "trade_date": date,
                "fwd_ret_5d": np.random.normal(0.001, 0.02),
            })
    return pd.DataFrame(records)


class TestFactorPrunerBasic:
    """Test basic pruner functionality."""

    def test_empty_factors(self):
        pruner = FactorPruner({}, pd.DataFrame(), [])
        result = pruner.analyze()
        assert result["n_analyzed"] == 0

    def test_no_enabled_factors(self):
        pruner = FactorPruner(
            {"factor_a": _make_factor_df("a")},
            _make_fwd_rets(),
            [20200101 + i * 7 for i in range(20)],
            enabled_factors=[],
        )
        result = pruner.analyze()
        assert result["n_analyzed"] == 0

    def test_single_factor_analysis(self):
        factor_df = _make_factor_df("test_factor", n_stocks=30, n_dates=15)
        fwd_rets = _make_fwd_rets(n_stocks=30, n_dates=15)
        signal_dates = _make_dates(15, start_year=2020)

        pruner = FactorPruner(
            {"test_factor": factor_df},
            fwd_rets,
            signal_dates,
        )
        result = pruner.analyze()

        assert result["n_analyzed"] == 1
        assert "test_factor" in result["analysis"]

    def test_analysis_includes_required_fields(self):
        factor_df = _make_factor_df("f1", n_stocks=30, n_dates=15)
        fwd_rets = _make_fwd_rets(n_stocks=30, n_dates=15)
        signal_dates = _make_dates(15, start_year=2020)

        pruner = FactorPruner({"f1": factor_df}, fwd_rets, signal_dates)
        result = pruner.analyze()

        analysis = result["analysis"]["f1"]
        assert "annual_ic" in analysis
        assert "coverage_ratio" in analysis
        assert "rank_autocorrelation" in analysis
        assert "decay_2025" in analysis
        assert "negative_ic_year_ratio" in analysis

    def test_removal_reasons_are_explicit(self):
        """Every removed factor must have an explicit reason."""
        factor_df = _make_factor_df("bad_factor", n_stocks=5, n_dates=3)
        fwd_rets = _make_fwd_rets(n_stocks=5, n_dates=3)
        signal_dates = _make_dates(3, start_year=2020)

        pruner = FactorPruner(
            {"bad_factor": factor_df},
            fwd_rets,
            signal_dates,
        )
        result = pruner.analyze()

        # Check that any removal has a reason
        for removal in result.get("removals", []):
            assert "reason" in removal
            assert removal["reason"] != ""
            assert removal["action"] == "remove"

    def test_downweight_reasons_are_explicit(self):
        """Every down-weighted factor must have an explicit reason."""
        # Create a factor with unstable coverage to trigger downweight
        factor_df = _make_factor_df("unstable", n_stocks=30, n_dates=15)
        fwd_rets = _make_fwd_rets(n_stocks=30, n_dates=15)
        signal_dates = _make_dates(15, start_year=2020)

        pruner = FactorPruner(
            {"unstable": factor_df},
            fwd_rets,
            signal_dates,
        )
        result = pruner.analyze()

        for dw in result.get("downweights", []):
            assert "reason" in dw
            assert dw["reason"] != ""
            assert dw["action"] == "downweight"


class TestFactorPrunerDecisions:
    """Test pruning decision rules."""

    def test_2025_decay_not_used_for_removal(self):
        """2025+ OOS decay should ONLY be diagnostic, not for removal decisions."""
        # This is verified by checking that the pruner's _decide_action
        # explicitly excludes decay_2025 from the decision logic.
        from alpha.factor_pruning import FactorPruner

        pruner = FactorPruner.__new__(FactorPruner)
        # Create analysis with strong decay but good IS metrics
        analysis = {
            "annual_ic": {
                "2020": {"mean_ic": 0.05, "ic_positive_rate": 0.7, "n_dates": 40},
                "2021": {"mean_ic": 0.04, "ic_positive_rate": 0.65, "n_dates": 40},
                "2022": {"mean_ic": 0.03, "ic_positive_rate": 0.6, "n_dates": 40},
                "2023": {"mean_ic": 0.05, "ic_positive_rate": 0.7, "n_dates": 40},
                "2024": {"mean_ic": 0.04, "ic_positive_rate": 0.6, "n_dates": 40},
            },
            "negative_ic_year_ratio": 0.0,
            "coverage_ratio": 0.9,
            "coverage_instability": 0.05,
            "rank_autocorrelation": 0.6,
            "decay_2025": True,  # Strong OOS decay
            "pre_2025_mean_ic": 0.04,
            "post_2025_mean_ic": 0.005,
        }

        action, reason = pruner._decide_action("test_factor", analysis)
        # Should be KEPT despite OOS decay
        assert action == "keep", (
            f"Factor with strong IS IC but OOS decay should be KEPT, "
            f"not {action}. Reason: {reason}"
        )

    def test_negative_ic_majority_removed(self):
        """Factors with majority negative IC years should be removed."""
        pruner = FactorPruner.__new__(FactorPruner)

        analysis = {
            "annual_ic": {
                "2020": {"mean_ic": -0.02, "ic_positive_rate": 0.3, "n_dates": 40},
                "2021": {"mean_ic": -0.01, "ic_positive_rate": 0.35, "n_dates": 40},
                "2022": {"mean_ic": -0.03, "ic_positive_rate": 0.25, "n_dates": 40},
                "2023": {"mean_ic": 0.01, "ic_positive_rate": 0.55, "n_dates": 40},
                "2024": {"mean_ic": -0.02, "ic_positive_rate": 0.3, "n_dates": 40},
            },
            "negative_ic_year_ratio": 0.8,  # 4/5 negative
            "coverage_ratio": 0.9,
            "coverage_instability": 0.05,
            "rank_autocorrelation": 0.5,
            "decay_2025": False,
        }

        action, reason = pruner._decide_action("bad_factor", analysis)
        assert action == "remove", f"Expected remove, got {action}: {reason}"
        assert "negative" in reason.lower()

    def test_low_coverage_removed(self):
        pruner = FactorPruner.__new__(FactorPruner)

        analysis = {
            "annual_ic": {
                "2020": {"mean_ic": 0.02, "ic_positive_rate": 0.55, "n_dates": 40},
                "2021": {"mean_ic": 0.02, "ic_positive_rate": 0.55, "n_dates": 40},
            },
            "negative_ic_year_ratio": 0.0,
            "coverage_ratio": 0.3,  # < 0.5
            "coverage_instability": 0.1,
            "rank_autocorrelation": 0.5,
            "decay_2025": False,
        }

        action, reason = pruner._decide_action("sparse_factor", analysis)
        assert action == "remove", f"Expected remove, got {action}: {reason}"
        assert "coverage" in reason.lower()


class TestFactorPrunerReport:
    """Test report generation."""

    def test_report_includes_removals(self):
        factor_dfs = {
            "f1": _make_factor_df("f1", n_stocks=30, n_dates=15),
            "f2": _make_factor_df("f2", n_stocks=30, n_dates=15),
        }
        fwd_rets = _make_fwd_rets(n_stocks=30, n_dates=15)
        signal_dates = _make_dates(15, start_year=2020)

        pruner = FactorPruner(factor_dfs, fwd_rets, signal_dates)
        pruner.analyze()
        report = pruner.generate_report()

        assert "Factor Pruning Report" in report
        assert "Factors Analyzed" in report

    def test_pruned_config_structure(self):
        factor_dfs = {
            "f1": _make_factor_df("f1", n_stocks=30, n_dates=15),
        }
        fwd_rets = _make_fwd_rets(n_stocks=30, n_dates=15)
        signal_dates = _make_dates(15, start_year=2020)

        pruner = FactorPruner(factor_dfs, fwd_rets, signal_dates)
        pruner.analyze()
        config = pruner.generate_pruned_config()

        assert "enabled_factors" in config
        assert "removed_factors" in config
        assert "downweighted_factors" in config
        assert "n_original" in config
        assert "n_kept" in config

    def test_oos_disclaimer_in_config(self):
        """Generated config must note OOS is diagnostic only."""
        factor_dfs = {"f1": _make_factor_df("f1", n_stocks=30, n_dates=15)}
        fwd_rets = _make_fwd_rets(n_stocks=30, n_dates=15)
        signal_dates = _make_dates(15, start_year=2020)

        pruner = FactorPruner(factor_dfs, fwd_rets, signal_dates)
        pruner.analyze()
        config = pruner.generate_pruned_config()

        note = config.get("note", "")
        assert "diagnostic" in note.lower() or "OOS" in note

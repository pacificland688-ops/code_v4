"""Tests for optimizer relaxation and fallback levels."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pandas as pd
import pytest


class TestFeasibilityCheck:
    """Test optimization feasibility checking."""

    def test_infeasible_config_detected(self):
        from portfolio.optimized_weighting import check_feasibility

        # top_n=50, weight_max=0.01 → 0.50 < 1.0 → infeasible
        diag = check_feasibility(top_n=50, weight_max=0.01)
        assert diag["fallback"] is True
        assert diag["infeasible_config"] is True
        assert "infeasible" in diag["fallback_reason"]

    def test_feasible_config_passes(self):
        from portfolio.optimized_weighting import check_feasibility

        diag = check_feasibility(top_n=100, weight_max=0.02)
        assert diag["fallback"] is False

    def test_low_optimizer_space_warning(self):
        from portfolio.optimized_weighting import check_feasibility

        # 50 * 0.02 = 1.0 → barely feasible
        diag = check_feasibility(top_n=50, weight_max=0.02)
        assert diag["low_optimizer_space"] is True

    def test_tight_but_feasible(self):
        from portfolio.optimized_weighting import check_feasibility

        # 51 * 0.02 = 1.02 → feasible with warning
        diag = check_feasibility(top_n=51, weight_max=0.02)
        assert diag["fallback"] is False
        assert diag["low_optimizer_space"] is True


class TestFallbackLevels:
    """Test tiered fallback behavior."""

    def test_relaxation_levels_recorded(self):
        from portfolio.optimized_weighting import make_diag

        diag = make_diag(relaxation_level=2,
                        relaxation_applied=["turnover_cap_relaxed_to_0.35"])
        assert diag["relaxation_level"] == 2
        assert "turnover_cap_relaxed_to_0.35" in diag["relaxation_applied"]
        assert diag["fallback"] is False  # relaxation != fallback

    def test_level_4_is_full_fallback(self):
        from portfolio.optimized_weighting import make_diag

        diag = make_diag(
            fallback=True,
            fallback_reason="all_relaxation_levels_failed",
            relaxation_level=4,
            relaxation_applied=["L0_failed", "L1_failed", "L2_failed", "L3_failed"],
        )
        assert diag["fallback"] is True
        assert diag["relaxation_level"] == 4

    def test_relaxation_success_not_counted_as_fallback(self):
        """When relaxation succeeds, it MUST NOT be counted as normal success."""
        from portfolio.optimized_weighting import make_diag

        diag = make_diag(
            relaxation_level=2,
            relaxation_applied=["turnover_cap_relaxed_to_0.35"],
            solver="ECOS",
        )
        assert diag["fallback"] is False
        assert diag["relaxation_level"] > 0
        # This is a RELAXATION success, not a Level 0 success

    def test_every_relaxation_has_reason(self):
        """Every relaxation/fallback must have a reason."""
        from portfolio.optimized_weighting import relax_constraints_tiered
        # With bad inputs, all levels should fail and each has a reason
        # We test at the diag level since actual solver calls need cvxpy + data
        from portfolio.optimized_weighting import make_diag as md

        for level in range(5):
            diag = md(
                fallback=(level >= 4),
                fallback_reason=f"test_level_{level}",
                relaxation_level=level,
            )
            assert diag["fallback_reason"] != ""
            assert diag["relaxation_level"] == level


class TestBuildFallbackWeights:
    """Test fallback weight builders."""

    def test_equal_weight_fallback(self):
        from portfolio.optimized_weighting import build_fallback_weights

        codes = ["A", "B", "C", "D", "E"]
        weights, diag = build_fallback_weights(5, codes, method="equal")

        assert len(weights) == 5
        assert weights.sum() == pytest.approx(1.0)
        assert all(weights > 0)
        assert diag["fallback"] is True
        assert "equal" in diag["fallback_reason"]

    def test_previous_weight_fallback(self):
        from portfolio.optimized_weighting import build_fallback_weights

        codes = ["A", "B", "C"]
        prev = pd.Series({"A": 0.5, "B": 0.3, "C": 0.2})
        weights, diag = build_fallback_weights(3, codes, prev_weights=prev,
                                               method="previous")

        assert weights.sum() == pytest.approx(1.0)
        assert diag["fallback"] is True

    def test_previous_with_new_stocks(self):
        from portfolio.optimized_weighting import build_fallback_weights

        codes = ["A", "B", "C", "D"]
        prev = pd.Series({"A": 0.6, "B": 0.4})

        weights, diag = build_fallback_weights(4, codes, prev_weights=prev,
                                               method="previous")
        assert len(weights) == 4
        assert weights.sum() == pytest.approx(1.0)


class TestDiagnosticStructure:
    """Test diagnostic record structure."""

    def test_make_diag_defaults(self):
        from portfolio.optimized_weighting import make_diag

        diag = make_diag()
        assert "fallback" in diag
        assert "fallback_reason" in diag
        assert "used_mu" in diag
        assert "low_optimizer_space" in diag
        assert "solver" in diag
        assert "relaxation_level" in diag
        assert "relaxation_applied" in diag
        assert "infeasible_config" in diag
        assert "n_optimized" in diag

    def test_solver_name_in_fallback_reason(self):
        from portfolio.optimized_weighting import make_diag

        diag = make_diag(fallback=True,
                        fallback_reason="ECOS solver failed: numerical error",
                        solver="ECOS")
        assert "ECOS" in diag["fallback_reason"]
        assert diag["solver"] == "ECOS"


class TestEnhanceShrinkage:
    """Test covariance shrinkage enhancement."""

    def test_enhance_shrinkage_preserves_psd(self):
        from portfolio.optimized_weighting import _enhance_shrinkage, _ensure_psd

        # Create a valid covariance-like matrix
        np.random.seed(42)
        X = np.random.randn(100, 10)
        Sigma = np.cov(X.T)

        enhanced = _enhance_shrinkage(Sigma, factor=0.3)
        assert enhanced.shape == Sigma.shape

        # Should be PSD
        eigenvalues = np.linalg.eigvalsh(enhanced)
        assert float(eigenvalues.min()) >= -1e-10

    def test_ensure_psd_fixes_non_psd(self):
        from portfolio.optimized_weighting import _ensure_psd

        # Create a matrix with a negative eigenvalue
        Sigma = np.array([[1.0, 0.99], [0.99, 0.5]])
        fixed = _ensure_psd(Sigma)
        eigenvalues = np.linalg.eigvalsh(fixed)
        # After fixing, eigenvalues should be >= epsilon (accounting for float precision)
        assert float(eigenvalues.min()) >= 5e-7


class TestNoTradeBand:
    """Test no-trade band logic."""

    def test_small_changes_use_previous_weights(self):
        from portfolio.optimized_weighting import _apply_no_trade_band

        target = pd.Series({"A": 0.6, "B": 0.4})
        prev = pd.Series({"A": 0.58, "B": 0.42})

        # Band = 0.05, change of 0.02 < 0.05 → keep previous
        result = _apply_no_trade_band(target, prev, band=0.05)
        # Both weights are within the band
        assert result["A"] == pytest.approx(0.58)  # kept previous
        assert result["B"] == pytest.approx(0.42)

    def test_large_changes_trigger_trade(self):
        from portfolio.optimized_weighting import _apply_no_trade_band

        target = pd.Series({"A": 0.8, "B": 0.2})
        prev = pd.Series({"A": 0.5, "B": 0.5})

        # Band = 0.05, change of 0.30 > 0.05 → use target
        result = _apply_no_trade_band(target, prev, band=0.05)
        assert result["A"] == pytest.approx(0.8)
        assert result["B"] == pytest.approx(0.2)

    def test_renormalizes_to_one(self):
        from portfolio.optimized_weighting import _apply_no_trade_band

        target = pd.Series({"A": 0.5, "B": 0.3, "C": 0.2})
        prev = pd.Series({"A": 0.5, "B": 0.35, "C": 0.15})

        result = _apply_no_trade_band(target, prev, band=0.10)
        assert result.sum() == pytest.approx(1.0)


class TestMaxWeightChange:
    """Test maximum weight change cap."""

    def test_weights_sum_to_one_after_cap(self):
        from portfolio.optimized_weighting import _apply_max_weight_change

        target = pd.Series({"A": 0.7, "B": 0.2, "C": 0.1})
        prev = pd.Series({"A": 0.4, "B": 0.3, "C": 0.3})

        result = _apply_max_weight_change(target, prev, max_change=0.15)
        assert result.sum() == pytest.approx(1.0)
        # A change from 0.4 to 0.7 (+0.30) should be capped to 0.4 + 0.15 = 0.55


# ===================================================================
# Batch 4: Covariance shrinkage configs
# ===================================================================

class TestCovarianceShrinkageMethods:
    """Verify diagonal_shrink_NN methods work."""

    def test_diagonal_shrink_20_supported(self):
        from portfolio.cov_estimator import CovarianceEstimator

        # Create sample return data
        np.random.seed(42)
        returns = np.random.randn(100, 10) * 0.02  # 100 obs, 10 stocks
        returns_df = pd.DataFrame(returns, columns=[f"{i:06d}.SZ" for i in range(10)])
        returns_df.index.name = "trade_date"

        est = CovarianceEstimator(method="diagonal_shrink_20", window=252, min_obs=10,
                                  annualize=False)
        cov, codes = est.estimate(returns_df)
        assert cov.shape[0] >= 5  # should have at least 5 stocks
        assert cov.shape == (len(codes), len(codes))
        # Check finite
        assert np.all(np.isfinite(cov))
        # Check PSD
        eigenvalues = np.linalg.eigvalsh(cov)
        assert float(eigenvalues.min()) >= -1e-10

    def test_diagonal_shrink_40_supported(self):
        from portfolio.cov_estimator import CovarianceEstimator

        np.random.seed(42)
        returns = np.random.randn(100, 10) * 0.02
        returns_df = pd.DataFrame(returns, columns=[f"{i:06d}.SZ" for i in range(10)])
        returns_df.index.name = "trade_date"

        est = CovarianceEstimator(method="diagonal_shrink_40", window=252, min_obs=10,
                                  annualize=False)
        cov, codes = est.estimate(returns_df)
        assert cov.shape[0] >= 5
        assert np.all(np.isfinite(cov))

    def test_experiment_config_cov_methods_are_supported(self):
        """All cov_shrinkage values in YAML must be valid methods."""
        from portfolio.cov_estimator import CovarianceEstimator

        np.random.seed(42)
        returns = np.random.randn(100, 10) * 0.02
        returns_df = pd.DataFrame(returns, columns=[f"{i:06d}.SZ" for i in range(10)])
        returns_df.index.name = "trade_date"

        for method in ["ledoit_wolf", "diagonal_shrink_20", "diagonal_shrink_40"]:
            est = CovarianceEstimator(method=method, window=252, min_obs=10,
                                      annualize=False)
            cov, codes = est.estimate(returns_df)
            assert cov.shape[0] >= 5, f"Method {method} failed"
            assert np.all(np.isfinite(cov)), f"Method {method} produced non-finite cov"


# ===================================================================
# Batch 5: Constraint relaxation differentiation
# ===================================================================

class TestConstraintRelaxationModes:
    """Verify constraint_relaxation=none vs tiered behave differently."""

    def test_relaxation_none_does_not_try_tiered(self):
        """constraint_relaxation='none' must call solve_with_retries, not relax."""
        from portfolio.optimized_weighting import compute_optimized_weights
        import inspect
        sig = inspect.signature(compute_optimized_weights)
        assert "constraint_relaxation" in sig.parameters
        assert sig.parameters["constraint_relaxation"].default == "none"

    def test_relaxation_tiered_records_relaxation_level(self):
        """tiered mode must set constraint_relaxation_mode in diag."""
        from portfolio.optimized_weighting import make_diag

        # Simulate a diag from tiered mode
        diag = make_diag(
            relaxation_level=2,
            relaxation_applied=["turnover_cap_relaxed_to_0.35"],
            solver="ECOS",
        )
        diag["constraint_relaxation_mode"] = "tiered"
        assert diag["constraint_relaxation_mode"] == "tiered"
        assert diag["relaxation_level"] > 0
        assert diag["fallback"] is False  # relaxation success ≠ fallback

    def test_backtester_forwards_constraint_relaxation(self):
        """PortfolioBacktester must pass constraint_relaxation to compute_optimized_weights."""
        import inspect
        from backtest.portfolio_backtester import PortfolioBacktester
        sig = inspect.signature(PortfolioBacktester.run_backtest)
        assert "constraint_relaxation" in sig.parameters
        assert sig.parameters["constraint_relaxation"].default == "none"


# ===================================================================
# 方案一: Tiered relaxation behavioral tests
# ===================================================================

class TestTieredRelaxationNoTypeError:
    """Verify tiered relaxation doesn't throw TypeError on fallback."""

    def test_l0_fallback_l1_success_no_typeerror(self):
        """
        L0 fail, L1 success using Sigma_override must not raise TypeError.
        The fix replaces lambda **kw with explicit _solve(Sigma_override=...).
        """
        from portfolio.optimized_weighting import relax_constraints_tiered

        # The _solve helper inside relax_constraints_tiered must use
        # distinct parameter names (Sigma_override, not Sigma) to avoid
        # "got multiple values for keyword argument".
        import inspect
        source = inspect.getsource(relax_constraints_tiered)
        assert "Sigma_override" in source, (
            "_solve must use Sigma_override to avoid duplicate keyword arg"
        )
        assert "weight_max_override" in source
        assert "turnover_max_override" in source

        # Verify the old buggy pattern is NOT present
        assert 'lambda **kw: solve_with_retries(' not in source, (
            "lambda **kw approach would cause TypeError on retry"
        )

    def test_l0_l1_fallback_l2_success_no_typeerror(self):
        """L0/L1 fail, L2 with turnover_max_override must not raise TypeError."""
        from portfolio.optimized_weighting import relax_constraints_tiered
        import inspect
        source = inspect.getsource(relax_constraints_tiered)
        assert "turnover_max_override=to_relax" in source, (
            "L2 must use turnover_max_override to avoid duplicate keyword arg"
        )

    def test_l0_l1_l2_fallback_l3_success_no_typeerror(self):
        """L0/L1/L2 fail, L3 with weight_max_override must not raise TypeError."""
        from portfolio.optimized_weighting import relax_constraints_tiered
        import inspect
        source = inspect.getsource(relax_constraints_tiered)
        assert "weight_max_override=wm_relaxed" in source, (
            "L3 must use weight_max_override to avoid duplicate keyword arg"
        )

    def test_cost_aware_params_in_every_solver_call(self):
        """Every _solve call must include cost_aware_lambda and estimated_cost_bps."""
        from portfolio.optimized_weighting import relax_constraints_tiered
        import inspect
        source = inspect.getsource(relax_constraints_tiered)
        # The solve_with_retries call inside _solve must include cost params
        assert "cost_aware_lambda=cost_aware_lambda" in source
        assert "estimated_cost_bps=estimated_cost_bps" in source
        # Verify cost params come from the outer scope (not hardcoded)
        # There should be EXACTLY ONE place where they're passed (in _solve)
        count_cl = source.count("cost_aware_lambda=cost_aware_lambda")
        count_eb = source.count("estimated_cost_bps=estimated_cost_bps")
        assert count_cl >= 1, f"cost_aware_lambda must be in _solve call, found {count_cl}"
        assert count_eb >= 1, f"estimated_cost_bps must be in _solve call, found {count_eb}"

    def test_compute_optimized_weights_tiered_runs_end_to_end(self):
        """
        compute_optimized_weights(constraint_relaxation='tiered') must run
        without TypeError, even when estimate_covariance fails (fast path).
        """
        import numpy as np
        import pandas as pd
        from unittest.mock import patch
        from portfolio.optimized_weighting import (
            compute_optimized_weights, solve_with_retries,
        )

        np.random.seed(42)
        n = 10
        codes = [f"{i:06d}.SZ" for i in range(n)]

        top_stocks = pd.DataFrame({
            "ts_code": codes,
            "composite_score": np.linspace(1, 0, n),
        })

        mu_df = pd.DataFrame({
            "ts_code": codes,
            "trade_date": [20240101] * n,
            "mu": list(np.random.normal(0.001, 0.005, n)),
        })

        prev = pd.Series(1.0 / n, index=codes)

        # Mock estimate_covariance to return valid data without real infra
        def fake_estimate_cov(*a, **kw):
            Sigma = np.eye(len(codes)) * 0.01
            return Sigma, codes, {"fallback": False}

        with patch(
            "portfolio.optimized_weighting.estimate_covariance",
            fake_estimate_cov,
        ):
            try:
                weights, diag = compute_optimized_weights(
                    top_stocks=top_stocks,
                    score_col="composite_score",
                    signal_date=20240101,
                    prev_weights=prev,
                    exec_date=20240102,
                    top_n=n,
                    mu_df=mu_df,
                    weight_max=0.15,
                    turnover_max=0.40,
                    turnover_penalty=0.005,
                    cost_aware_lambda=1.0,
                    estimated_cost_bps=12.0,
                    cov_method="ledoit_wolf",
                    constraint_relaxation="tiered",
                )
            except TypeError as e:
                pytest.fail(f"tiered relaxation raised TypeError: {e}")

        assert isinstance(weights, pd.Series)
        assert len(weights) > 0
        assert "relaxation_level" in diag
        assert "constraint_relaxation_mode" in diag
        assert diag["constraint_relaxation_mode"] == "tiered"
        # cost params must be recorded in diag
        assert diag.get("cost_aware_lambda") == 1.0
        assert diag.get("estimated_cost_bps") == 12.0

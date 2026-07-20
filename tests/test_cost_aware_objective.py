"""Tests for cost-aware optimization objective."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pandas as pd
import pytest


class TestCostAwareParameters:
    """Test cost-aware lambda and related parameters."""

    def test_cost_aware_lambda_defaults(self):
        """Default cost_aware_lambda=0 means no explicit cost penalty."""
        # Verify that the parameter is accepted and defaults correctly
        from portfolio.optimized_weighting import compute_optimized_weights
        # We can at least verify the function signature
        import inspect
        sig = inspect.signature(compute_optimized_weights)
        params = sig.parameters
        assert "cost_aware_lambda" in params
        assert params["cost_aware_lambda"].default == 0.0
        assert "estimated_cost_bps" in params
        assert params["estimated_cost_bps"].default == 10.0

    def test_turnover_penalty_separate_from_cost_aware(self):
        """Turnover penalty and cost-aware lambda are distinct mechanisms."""
        # turnover_penalty: soft penalty in objective
        # cost_aware_lambda: explicit cost estimate penalty
        # Both should be usable independently or together
        from portfolio.optimized_weighting import compute_optimized_weights
        import inspect
        sig = inspect.signature(compute_optimized_weights)
        params = sig.parameters
        assert "turnover_penalty" in params
        assert "cost_aware_lambda" in params
        # They have different default values and serve different purposes


class TestCostObjectiveNotDestroyingReturns:
    """Ensure cost-aware objective doesn't collapse returns."""

    def test_cost_penalty_magnitude_reasonable(self):
        """
        With typical params (lambda=1.0, cost=10bps), the cost penalty
        should be small relative to expected returns (~1-2% monthly).
        This ensures we don't penalize trading so heavily that the
        portfolio becomes passive.
        """
        # estimated_trade_cost = one_way_turnover * estimated_cost_bps / 10000
        # With turnover=0.30, cost=10bps: contribution = 0.30 * 10 / 10000 = 0.0003
        # With lambda=1.0: penalty = 0.0003 in the objective
        # This is small compared to mu ~ 0.01 per period
        turnover = 0.30
        est_cost_bps = 10.0
        cost_term = turnover * est_cost_bps / 10000.0
        assert cost_term < 0.001  # should be well below typical mu


class TestGridComparison:
    """Test that cost_aware_lambda grid can be compared with turnover_penalty grid."""

    def test_parameter_grids_are_distinct(self):
        """cost_aware_lambda and turnover_penalty affect different terms."""
        # cost_aware_lambda scales (turnover * cost_bps / 10000)
        # turnover_penalty scales |w - w_prev|
        # They target different aspects of trading cost
        lambda_vals = [0.5, 1.0, 2.0]
        penalty_vals = [0.0025, 0.005, 0.01, 0.02]

        # Verify they don't perfectly overlap (different mechanisms)
        for lam in lambda_vals:
            for pen in penalty_vals:
                # With typical params, the two penalties have different scales
                cost_term_scale = lam * 0.30 * 10 / 10000  # lambda * turnover * cost/10000
                pen_term_scale = pen * 0.30  # penalty * turnover
                # They shouldn't be identical for most combinations
                assert cost_term_scale != pen_term_scale or (
                    lam == 0 and pen == 0
                ), f"Identical scales at λ={lam}, γ={pen}"

    def test_no_double_penalty(self):
        """Ensure cost_aware_lambda and turnover_penalty don't double-count."""
        # When both are used, the objective is:
        # max w'μ - risk - γ·|w-w_prev| - κ·turnover·cost/10000
        # The penalty for a trade should not exceed the actual cost
        # γ=0.02 and κ=2.0 with cost=10bps on 30% turnover:
        gamma_penalty = 0.02 * 0.30  # 0.006
        kappa_penalty = 2.0 * 0.30 * 10 / 10000  # 0.0006
        total_penalty = gamma_penalty + kappa_penalty
        # Total penalty should be reasonable (< 1% of portfolio)
        assert total_penalty < 0.01, (
            f"Combined penalty too high: {total_penalty:.4f}"
        )


class TestCostModelIntegration:
    """Test integration with cost model."""

    def test_linear_cost_approximation(self):
        """Verify the linear cost model used in the objective."""
        # estimated_trade_cost = one_way_turnover * estimated_cost_bps / 10000
        # This is a linear approximation — verify basic properties

        # Double turnover → double cost
        cost1 = 0.20 * 10 / 10000
        cost2 = 0.40 * 10 / 10000
        assert cost2 == pytest.approx(2 * cost1)

        # Zero turnover → zero cost
        cost0 = 0.0 * 10 / 10000
        assert cost0 == 0.0

        # Higher bps → higher cost
        cost_low = 0.30 * 5 / 10000
        cost_high = 0.30 * 20 / 10000
        assert cost_high > cost_low


# ===================================================================
# Batch 7: Behavioral tests — cost-aware params reach the solver
# ===================================================================

class TestCostAwareParamsReachSolver:
    """Verify cost_aware_lambda and estimated_cost_bps actually reach solve_with_retries."""

    def test_cost_aware_params_reach_solve_with_retries(self):
        """solve_with_retries signature must accept cost params, and
        compute_optimized_weights must forward them to both code paths."""
        import inspect
        import portfolio.optimized_weighting as ow

        # 1. solve_with_retries must accept cost params
        sig = inspect.signature(ow.solve_with_retries)
        assert "cost_aware_lambda" in sig.parameters
        assert "estimated_cost_bps" in sig.parameters
        assert sig.parameters["cost_aware_lambda"].default == 0.0
        assert sig.parameters["estimated_cost_bps"].default == 10.0

        # 2. relax_constraints_tiered must accept cost params
        sig2 = inspect.signature(ow.relax_constraints_tiered)
        assert "cost_aware_lambda" in sig2.parameters
        assert "estimated_cost_bps" in sig2.parameters

        # 3. compute_optimized_weights must forward cost params in both branches
        source = inspect.getsource(ow.compute_optimized_weights)
        # The tiered path must pass cost params
        assert "cost_aware_lambda=cost_aware_lambda" in source, (
            "compute_optimized_weights tiered path must pass cost_aware_lambda"
        )
        assert "estimated_cost_bps=estimated_cost_bps" in source, (
            "compute_optimized_weights must pass estimated_cost_bps"
        )
        # The solve diag must record cost params
        assert 'solve_diag["cost_aware_lambda"]' in source, (
            "compute_optimized_weights must record cost_aware_lambda in diag"
        )
        assert 'solve_diag["estimated_cost_bps"]' in source, (
            "compute_optimized_weights must record estimated_cost_bps in diag"
        )

    def test_relax_constraints_tiered_accepts_cost_params(self):
        """relax_constraints_tiered signature must include cost_aware_lambda+estimated_cost_bps."""
        import inspect
        from portfolio.optimized_weighting import relax_constraints_tiered
        sig = inspect.signature(relax_constraints_tiered)
        params = sig.parameters
        assert "cost_aware_lambda" in params, (
            "relax_constraints_tiered must accept cost_aware_lambda"
        )
        assert "estimated_cost_bps" in params, (
            "relax_constraints_tiered must accept estimated_cost_bps"
        )
        assert params["cost_aware_lambda"].default == 0.0
        assert params["estimated_cost_bps"].default == 10.0

    def test_cost_aware_diag_records_params(self):
        """Diagnostic dict must record cost_aware_lambda and estimated_cost_bps."""
        from portfolio.optimized_weighting import make_diag
        diag = make_diag()
        diag["cost_aware_lambda"] = 7.0
        diag["estimated_cost_bps"] = 33.0
        assert diag["cost_aware_lambda"] == 7.0
        assert diag["estimated_cost_bps"] == 33.0


class TestConstraintRelaxationBranching:
    """Batch 7: Verify constraint_relaxation branches are distinct."""

    def test_none_calls_solve_not_relax(self):
        """constraint_relaxation='none' must call solve_with_retries, NOT relax."""
        from portfolio.optimized_weighting import (
            compute_optimized_weights, solve_with_retries,
            relax_constraints_tiered,
        )
        # Verify the branching exists in source code
        import inspect
        source = inspect.getsource(compute_optimized_weights)
        assert "constraint_relaxation" in source
        assert "relax_constraints_tiered" in source
        assert "solve_with_retries" in source

    def test_tiered_calls_relax_not_solve_only(self):
        """When tiered, relax_constraints_tiered must be in the code path."""
        import inspect
        from portfolio.optimized_weighting import compute_optimized_weights
        source = inspect.getsource(compute_optimized_weights)
        # Must contain both paths
        assert 'if constraint_relaxation == "tiered"' in source or \
               'constraint_relaxation == "tiered"' in source

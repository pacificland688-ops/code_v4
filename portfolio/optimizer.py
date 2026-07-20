"""
Mean-variance portfolio optimizer for CSI 300.

Implements:
- max w'μ - (λ/2) w'Σw  subject to constraints
- Risk parity (equal risk contribution)
- Min variance
- Max Sharpe (tangency portfolio)

Uses cvxpy for convex optimization with A-share constraints.

Memory: optimization variable is O(300) — negligible.
"""

import logging
from typing import Optional, List, Dict, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

try:
    import cvxpy as cp
    _HAS_CVXPY = True
except ImportError:
    _HAS_CVXPY = False
    logger.warning("cvxpy not installed — optimizer unavailable. "
                   "Install with: pip install cvxpy")


class PortfolioOptimizer:
    """
    Mean-variance portfolio optimizer with A-share constraints.

    Parameters
    ----------
    constraint_builder : ConstraintBuilder
        Constraint configuration.
    solver_name : str
        cvxpy solver: "ECOS", "OSQP", "SCS".
    max_iter : int
        Maximum solver iterations.
    """

    def __init__(self,
                 constraint_builder=None,
                 solver_name: str = "ECOS",
                 max_iter: int = 10000,
                 tolerance: float = 1e-6):
        self._constraints = constraint_builder
        self.solver_name = solver_name
        self.max_iter = max_iter
        self.tolerance = tolerance

    @property
    def constraints(self):
        if self._constraints is None:
            from portfolio.constraints import ConstraintBuilder
            self._constraints = ConstraintBuilder()
        return self._constraints

    # ------------------------------------------------------------------
    # Mean-variance optimization
    # ------------------------------------------------------------------
    def optimize_mean_variance(self,
                                mu: np.ndarray,
                                Sigma: np.ndarray,
                                risk_aversion: float = 1.0,
                                prev_weights: Optional[np.ndarray] = None,
                                can_trade: Optional[np.ndarray] = None,
                                industry_exposures: Optional[np.ndarray] = None,
                                benchmark_ind_weights: Optional[np.ndarray] = None,
                                turnover_penalty: float = 0.0
                                ) -> Optional[np.ndarray]:
        """
        Mean-variance optimization.

        Objective: max w'μ - (λ/2) w'Σw - γ * ||w - w_prev||_1

        Parameters
        ----------
        mu : np.ndarray (n_stocks,)
            Expected return vector.
        Sigma : np.ndarray (n_stocks, n_stocks)
            Covariance matrix.
        risk_aversion : float
            λ parameter.
        prev_weights : np.ndarray, optional
            Previous weights for turnover penalty.
        can_trade : np.ndarray (bool), optional
            Tradable stock mask.
        industry_exposures : np.ndarray, optional
            Industry dummy matrix.
        benchmark_ind_weights : np.ndarray, optional
            Benchmark industry weights.
        turnover_penalty : float
            γ parameter for turnover cost in objective.

        Returns
        -------
        np.ndarray of optimal weights, or None if optimization fails.
        """
        if not _HAS_CVXPY:
            raise ImportError("cvxpy required for optimization")

        n = len(mu)

        # Validate inputs
        if n < 5:
            logger.warning(f"Too few stocks for optimization: {n}")
            return None

        if Sigma.shape != (n, n):
            logger.error(f"Sigma shape mismatch: {Sigma.shape} vs ({n},{n})")
            return None

        # Phase 2: Hard check — if top_n * weight_max <= 1.05, warn about
        # optimization space being insufficient. The optimizer will still
        # run, but the result will be near-equal-weight.
        from portfolio.constraints import ConstraintBuilder
        cb = self._constraints if self._constraints is not None else ConstraintBuilder()
        w_max = cb.weight_max
        if n * w_max <= 1.05:
            logger.warning(
                f"Optimization space insufficient: "
                f"n={n} * weight_max={w_max:.2f} = {n * w_max:.2f} <= 1.05. "
                f"Portfolio will be locked near equal-weight. "
                f"Consider: increase weight_max or increase top_n."
            )

        # Ensure Sigma is PSD
        Sigma = self._ensure_psd(Sigma)

        # Decision variable
        w = cp.Variable(n)

        # Objective
        expected_return = mu @ w
        risk = cp.quad_form(w, Sigma)
        objective = expected_return - (risk_aversion / 2.0) * risk

        # Turnover penalty in objective
        if turnover_penalty > 0 and prev_weights is not None:
            turnover = cp.sum(cp.abs(w - prev_weights))
            objective = objective - turnover_penalty * turnover

        # Build constraints
        constraint_list = self.constraints.build_constraints(
            w, n,
            prev_weights=prev_weights,
            can_trade=can_trade,
            industry_exposures=industry_exposures,
            benchmark_industry_weights=benchmark_ind_weights,
        )

        # Solve
        problem = cp.Problem(cp.Maximize(objective), constraint_list)

        try:
            problem.solve(
                solver=self.solver_name,
                max_iters=self.max_iter,
                eps=self.tolerance,
                verbose=False,
            )
        except Exception as e:
            logger.error(f"Solver failed: {e}")
            # Fallback: try OSQP
            try:
                problem.solve(
                    solver="OSQP",
                    max_iter=self.max_iter,
                    eps_abs=self.tolerance,
                    eps_rel=self.tolerance,
                    verbose=False,
                )
            except Exception as e2:
                logger.error(f"OSQP fallback also failed: {e2}")
                return None

        if w.value is None:
            logger.warning("Optimization did not converge")
            return None

        weights = w.value
        # Clean up: zero out very small weights
        weights[np.abs(weights) < 1e-6] = 0.0
        # Re-normalize
        if weights.sum() > 0:
            weights = weights / weights.sum()

        return weights

    # ------------------------------------------------------------------
    # Risk parity
    # ------------------------------------------------------------------
    def optimize_risk_parity(self,
                              Sigma: np.ndarray,
                              risk_budget: Optional[np.ndarray] = None,
                              prev_weights: Optional[np.ndarray] = None,
                              can_trade: Optional[np.ndarray] = None
                              ) -> Optional[np.ndarray]:
        """
        Risk parity: equal risk contribution from each asset.

        Minimizes: Σ_i (w_i * (Σw)_i - b_i * σ_p²)²

        Uses a convex formulation via cvxpy.
        """
        if not _HAS_CVXPY:
            raise ImportError("cvxpy required for optimization")

        n = Sigma.shape[0]

        if risk_budget is None:
            risk_budget = np.ones(n) / n

        Sigma = self._ensure_psd(Sigma)

        w = cp.Variable(n)
        portfolio_risk = cp.quad_form(w, Sigma)
        budget = cp.multiply(risk_budget, portfolio_risk)

        # Marginal risk contribution = Σw
        mrc = Sigma @ w
        rc = cp.multiply(w, mrc)  # risk contribution

        objective = cp.sum_squares(rc - budget)

        constraint_list = [cp.sum(w) == 1, w >= 0]
        if can_trade is not None and prev_weights is not None:
            frozen = ~can_trade.astype(bool)
            if frozen.any():
                constraint_list.append(w[frozen] == prev_weights[frozen])

        problem = cp.Problem(cp.Minimize(objective), constraint_list)

        try:
            problem.solve(solver=self.solver_name, max_iters=self.max_iter,
                          verbose=False)
        except Exception as e:
            logger.error(f"Risk parity optimization failed: {e}")
            return None

        if w.value is None:
            return None

        weights = w.value
        weights[np.abs(weights) < 1e-6] = 0.0
        if weights.sum() > 0:
            weights = weights / weights.sum()
        return weights

    # ------------------------------------------------------------------
    # Min variance
    # ------------------------------------------------------------------
    def optimize_min_variance(self,
                               Sigma: np.ndarray,
                               prev_weights: Optional[np.ndarray] = None,
                               can_trade: Optional[np.ndarray] = None
                               ) -> Optional[np.ndarray]:
        """Minimum variance portfolio."""
        if not _HAS_CVXPY:
            raise ImportError("cvxpy required")

        n = Sigma.shape[0]
        Sigma = self._ensure_psd(Sigma)

        w = cp.Variable(n)
        objective = cp.quad_form(w, Sigma)

        constraint_list = self.constraints.build_constraints(
            w, n, prev_weights=prev_weights, can_trade=can_trade
        )

        problem = cp.Problem(cp.Minimize(objective), constraint_list)

        try:
            problem.solve(solver=self.solver_name, max_iters=self.max_iter,
                          verbose=False)
        except Exception as e:
            logger.error(f"Min variance optimization failed: {e}")
            return None

        if w.value is None:
            return None

        weights = w.value
        weights[np.abs(weights) < 1e-6] = 0.0
        if weights.sum() > 0:
            weights = weights / weights.sum()
        return weights

    # ------------------------------------------------------------------
    # Max Sharpe (tangency)
    # ------------------------------------------------------------------
    def optimize_max_sharpe(self,
                             mu: np.ndarray,
                             Sigma: np.ndarray,
                             risk_free_rate: float = 0.0,
                             prev_weights: Optional[np.ndarray] = None,
                             can_trade: Optional[np.ndarray] = None
                             ) -> Optional[np.ndarray]:
        """
        Maximum Sharpe ratio (tangency) portfolio.

        Reformulated as convex QP with a normalization constraint.
        """
        if not _HAS_CVXPY:
            raise ImportError("cvxpy required")

        n = len(mu)
        Sigma = self._ensure_psd(Sigma)
        excess_mu = mu - risk_free_rate

        # Use the convex formulation:
        # min y'Σy s.t. excess_mu'y = 1, y >= 0
        # Then w = y / sum(y)
        y = cp.Variable(n)
        objective = cp.quad_form(y, Sigma)

        constraint_list = [
            excess_mu @ y == 1,
            y >= 0,
        ]

        problem = cp.Problem(cp.Minimize(objective), constraint_list)

        try:
            problem.solve(solver=self.solver_name, max_iters=self.max_iter,
                          verbose=False)
        except Exception as e:
            logger.error(f"Max Sharpe optimization failed: {e}")
            return None

        if y.value is None or y.value.sum() <= 0:
            # Fallback: try without excess return constraint
            return self.optimize_min_variance(Sigma, prev_weights, can_trade)

        weights = y.value / y.value.sum()
        weights[np.abs(weights) < 1e-6] = 0.0
        return weights

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _ensure_psd(Sigma: np.ndarray, epsilon: float = 1e-6) -> np.ndarray:
        """
        Ensure matrix is positive semi-definite.

        Adds a small diagonal term if eigenvalues are negative.
        """
        eigenvalues = np.linalg.eigvalsh(Sigma)
        min_eig = eigenvalues.min()
        if min_eig < 0:
            Sigma = Sigma + np.eye(Sigma.shape[0]) * (abs(min_eig) + epsilon)
        return Sigma

"""
Portfolio optimization constraints.

Defines A-share portfolio constraints for cvxpy optimization:
- Long-only: w >= 0
- Fully invested: sum(w) = 1 (or <= 1 if allowing cash)
- Single stock bounds: w_min <= w_i <= w_max
- Industry exposure limits
- Turnover limits
- Untradable stock freezing

Constraints are assembled as a list of cvxpy constraint objects
for the optimizer.
"""

import logging
from typing import Optional, List, Dict, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# cvxpy is imported lazily (only when optimizer is used)
try:
    import cvxpy as cp
    _HAS_CVXPY = True
except ImportError:
    _HAS_CVXPY = False


class ConstraintBuilder:
    """
    Build optimization constraints for CSI 300 portfolios.

    Constraints are assembled per-rebalance based on current
    market conditions and tradable status.
    """

    def __init__(self,
                 long_only: bool = True,
                 leverage: float = 1.0,
                 weight_min: float = 0.0,
                 weight_max: float = 0.02,
                 industry_deviation_max: float = 0.05,
                 stock_deviation_max: float = 0.02,
                 turnover_max: float = 0.30,
                 min_holdings: int = 30,
                 max_holdings: int = 100,
                 freeze_untradable: bool = True):
        self.long_only = long_only
        self.leverage = leverage
        self.weight_min = weight_min
        self.weight_max = weight_max
        self.industry_deviation_max = industry_deviation_max
        self.stock_deviation_max = stock_deviation_max
        self.turnover_max = turnover_max
        self.min_holdings = min_holdings
        self.max_holdings = max_holdings
        self.freeze_untradable = freeze_untradable

    # ------------------------------------------------------------------
    # Build constraint set
    # ------------------------------------------------------------------
    def build_constraints(self, w, n_stocks: int,
                          prev_weights: Optional[np.ndarray] = None,
                          can_trade: Optional[np.ndarray] = None,
                          industry_exposures: Optional[np.ndarray] = None,
                          benchmark_industry_weights: Optional[np.ndarray] = None,
                          ) -> list:
        """
        Build list of cvxpy constraints.

        Parameters
        ----------
        w : cvxpy.Variable
            Weight variable (n_stocks,).
        n_stocks : int
            Number of stocks.
        prev_weights : np.ndarray, optional
            Previous portfolio weights for turnover constraint.
        can_trade : np.ndarray (bool), optional
            Which stocks are tradable. Untradable = weight frozen.
        industry_exposures : np.ndarray (n_stocks, n_industries), optional
            Industry dummy matrix for industry constraint.
        benchmark_industry_weights : np.ndarray (n_industries,), optional
            Benchmark industry weights.

        Returns
        -------
        list of cvxpy constraints.
        """
        if not _HAS_CVXPY:
            raise ImportError("cvxpy required for constraint building")

        constraints = []

        # 1. Weight sum = leverage (fully invested if leverage=1)
        constraints.append(cp.sum(w) == self.leverage)

        # 2. Long-only: all weights >= 0
        if self.long_only:
            constraints.append(w >= 0)

        # 3. Individual stock bounds
        constraints.append(w <= self.weight_max)
        if self.weight_min > 0:
            constraints.append(w >= self.weight_min)

        # 4. Freeze untradable stocks
        if self.freeze_untradable and can_trade is not None and prev_weights is not None:
            frozen = ~can_trade.astype(bool)
            if frozen.any():
                constraints.append(w[frozen] == prev_weights[frozen])

        # 5. Turnover constraint
        if self.turnover_max < 1.0 and prev_weights is not None:
            turnover = cp.sum(cp.abs(w - prev_weights)) / 2.0
            constraints.append(turnover <= self.turnover_max)

        # 6. Industry deviation constraint
        if (industry_exposures is not None and
                benchmark_industry_weights is not None and
                self.industry_deviation_max < 1.0):
            portfolio_ind_weight = w @ industry_exposures
            ind_dev = cp.sum(cp.abs(portfolio_ind_weight - benchmark_industry_weights)) / 2.0
            constraints.append(ind_dev <= self.industry_deviation_max)

        # 7. Cardinality constraint (min/max holdings) — not convex, skip for QP
        # These are approximated through weight_max constraints

        return constraints

    # ------------------------------------------------------------------
    # Build tradable freeze mask
    # ------------------------------------------------------------------
    @staticmethod
    def build_can_trade_mask(can_buy: pd.Series, can_sell: pd.Series,
                             codes: List[str]) -> np.ndarray:
        """
        Build boolean array indicating which stocks can be traded.

        A stock is tradable if both can_buy and can_sell are True.
        """
        can_buy_aligned = can_buy.reindex(codes, fill_value=False)
        can_sell_aligned = can_sell.reindex(codes, fill_value=False)
        return (can_buy_aligned.values & can_sell_aligned.values)

    # ------------------------------------------------------------------
    # Build industry exposure matrix
    # ------------------------------------------------------------------
    @staticmethod
    def build_industry_matrix(industry_classifier,
                              codes: List[str], date: int) -> np.ndarray:
        """
        Build (n_stocks × n_industries) dummy matrix.

        Each stock gets a 1 in its industry column.
        """
        dummies = industry_classifier.get_industry_dummies(codes, date)
        if dummies.empty:
            return np.array([])
        return dummies.reindex(codes, fill_value=0).values.astype("float64")

    # ------------------------------------------------------------------
    # Benchmark industry weights
    # ------------------------------------------------------------------
    @staticmethod
    def get_benchmark_industry_weights(industry_classifier,
                                       universe: List[str],
                                       date: int,
                                       method: str = "equal") -> np.ndarray:
        """
        Get benchmark industry weights for the current universe.

        Parameters
        ----------
        method : str
            "equal": equal weight across constituent stocks
            "market_cap": market-cap weighted (requires daily_basic)
        """
        if method == "equal":
            industries = industry_classifier.get_industries(universe, date)
            if not industries:
                return np.array([])

            # Count stocks per industry
            ind_series = pd.Series(industries)
            counts = ind_series.value_counts()
            weights = counts / counts.sum()
            return weights.values.astype("float64")
        else:
            # market_cap weighted — needs daily_basic data
            logger.warning("Market-cap benchmark weights not implemented; using equal")
            return ConstraintBuilder.get_benchmark_industry_weights(
                industry_classifier, universe, date, "equal"
            )

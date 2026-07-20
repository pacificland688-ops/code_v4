"""
Trade execution simulation for A-share portfolios.

Handles:
- T+1 execution: signal at t, trade at t+1 open
- Round lot constraints (100-share lots)
- Tradable mask filtering (can_buy/can_sell/can_hold)
- Weight freezing for untradable stocks
- Execution price: raw open (from prices_raw)

Memory: processes one rebalance date at a time.
"""

import logging
from typing import Optional, List, Dict, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class ExecutionSimulator:
    """
    Simulate A-share trade execution with realistic constraints.

    Signal date t → execute at t+1 open price.
    """

    def __init__(self,
                 cost_model=None,
                 tradable_mask=None,
                 execution_price: str = "open",
                 round_lot: bool = True,
                 min_unit: int = 100,
                 t1_sell_restriction: bool = True):
        self._cost_model = cost_model
        self._tradable = tradable_mask
        self.execution_price = execution_price
        self.round_lot = round_lot
        self.min_unit = min_unit
        self.t1_sell_restriction = t1_sell_restriction

    @property
    def cost_model(self):
        if self._cost_model is None:
            from backtest.cost_model import CostModel
            self._cost_model = CostModel()
        return self._cost_model

    @property
    def tradable(self):
        if self._tradable is None:
            from data.tradable import get_tradable
            self._tradable = get_tradable()
        return self._tradable

    # ------------------------------------------------------------------
    # Single rebalance execution
    # ------------------------------------------------------------------
    def execute_rebalance(self,
                          signal_date: int,
                          target_weights: pd.Series,
                          prev_holdings: pd.Series,
                          prices: pd.DataFrame,
                          portfolio_value: float,
                          can_buy: Optional[pd.Series] = None,
                          can_sell: Optional[pd.Series] = None) -> Dict:
        """
        Execute a single rebalance.

        Parameters
        ----------
        signal_date : int
            Signal date YYYYMMDD (weights computed at close of this date).
        target_weights : pd.Series (index=ts_code)
            Target portfolio weights.
        prev_holdings : pd.Series (index=ts_code)
            Previous portfolio weights.
        prices : pd.DataFrame
            Execution prices with columns: ts_code, open (raw).
        portfolio_value : float
            Pre-rebalance portfolio value.
        can_buy, can_sell : pd.Series, optional
            Pre-computed tradable flags (index=ts_code, bool).

        Returns
        -------
        dict with:
            executed_weights: pd.Series — actual post-rebalance weights
            frozen_weights: pd.Series — weights that couldn't be traded
            costs: dict — total transaction costs
            turnover: float — one-way turnover
            cash_drag: float — residual cash weight
        """
        # Align
        all_codes = target_weights.index.union(prev_holdings.index)
        target = target_weights.reindex(all_codes, fill_value=0.0)
        prev = prev_holdings.reindex(all_codes, fill_value=0.0)
        target = target.where(np.isfinite(target), 0.0)
        prev = prev.where(np.isfinite(prev), 0.0)

        # Save the ORIGINAL target before any freezing/normalization
        # so we can report genuinely frozen weight changes.
        original_target = target.copy()

        # Deduplicate prices before set_index
        prices = prices.drop_duplicates(["ts_code"], keep="last")
        prices = prices.dropna(subset=[self.execution_price])
        px = prices.set_index("ts_code")[self.execution_price].reindex(all_codes)

        # Flag invalid prices (NaN, zero, negative, inf)
        valid_price_mask = px.notna() & np.isfinite(px) & (px > 0)
        invalid = ~valid_price_mask

        # Track which stocks are frozen (can't be traded).
        # Frozen stocks keep their previous weight and do NOT participate
        # in normalization — the budget is scaled only over tradable stocks.
        frozen_mask = pd.Series(False, index=all_codes)

        # Freeze stocks without valid execution prices.
        # Rule: invalid-price stocks with existing holdings keep their
        # previous weight; invalid-price stocks without holdings get
        # target 0.  Neither participates in normalization.
        if invalid.any():
            n_invalid = invalid.sum()
            logger.debug(
                f"execute_rebalance: {n_invalid} stocks with "
                f"invalid prices frozen: {list(all_codes[invalid][:5])}"
            )
            # For ALL invalid-price stocks, target = prev (hold what you have,
            # don't buy what you don't have)
            target.loc[invalid] = prev.loc[invalid]

            # Mark as frozen: any stock with an invalid price AND a non-zero
            # previous position must stay frozen (we can't price it to trade).
            frozen_mask.loc[invalid] = prev.loc[invalid].abs() > 1e-12

            # Set px to 0 for invalid-price stocks so cost model skips them
            px.loc[invalid] = 0.0

        # Apply tradable mask: can't buy stocks where can_buy=False
        if can_buy is not None:
            cant_buy = ~can_buy.reindex(all_codes, fill_value=True)
            # Where we can't buy and target > prev, freeze to prev weight
            need_buy = target > prev
            freeze_buy = cant_buy & need_buy
            target = target.where(~freeze_buy, prev)
            frozen_mask = frozen_mask | freeze_buy

        # Apply tradable mask: can't sell stocks where can_sell=False
        if can_sell is not None:
            cant_sell = ~can_sell.reindex(all_codes, fill_value=True)
            # Where we can't sell and target < prev, freeze to prev weight
            need_sell = target < prev
            freeze_sell = cant_sell & need_sell
            target = target.where(~freeze_sell, prev)
            frozen_mask = frozen_mask | freeze_sell

        # Normalize ONLY non-frozen weights to fill the remaining budget.
        # Frozen stocks keep their exact previous weights.
        frozen_weight_sum = prev[frozen_mask].sum()
        remaining_budget = max(0.0, 1.0 - frozen_weight_sum)
        tradable_idx = ~frozen_mask
        tradable_weight_sum = target[tradable_idx].sum()

        if tradable_weight_sum > 1e-10 and remaining_budget > 1e-10:
            scale = remaining_budget / tradable_weight_sum
            target.loc[tradable_idx] = target.loc[tradable_idx] * scale
        elif remaining_budget <= 1e-10:
            # No budget left — zero out all non-frozen weights
            target.loc[tradable_idx] = 0.0

        executed_weights = target.where(np.isfinite(target), 0.0)

        # Compute turnover
        weight_change = executed_weights - prev
        one_way_turnover = weight_change.abs().sum() / 2.0

        # frozen_weights = difference between what we WANTED (original_target)
        # and what we GOT (executed_weights), for frozen stocks only.
        # Non-frozen stocks' weight differences are from normalization, not freezing.
        frozen = original_target - executed_weights
        frozen = frozen.where(frozen_mask, 0.0)
        frozen_weights = frozen.where(abs(frozen) > 1e-8, 0.0)

        # Compute costs
        cost_result = self.cost_model.compute_turnover_cost(
            prev, executed_weights, px, portfolio_value
        )

        return {
            "executed_weights": executed_weights,
            "frozen_weights": frozen_weights,
            "costs": cost_result,
            "turnover": one_way_turnover,
            "cash_drag": max(0, 1.0 - executed_weights.sum()),
        }

    # ------------------------------------------------------------------
    # Compute portfolio return for one period
    # ------------------------------------------------------------------
    def compute_period_return(self,
                              weights: pd.Series,
                              prices_start: pd.Series,
                              prices_end: pd.Series,
                              dividends: Optional[pd.Series] = None) -> float:
        """
        Compute portfolio return for a holding period.

        Parameters
        ----------
        weights : pd.Series (index=ts_code)
            Portfolio weights at start of period.
        prices_start : pd.Series (index=ts_code)
            Entry prices (raw open at t+1).
        prices_end : pd.Series (index=ts_code)
            Exit prices (raw close at next rebalance or adj_close).
        dividends : pd.Series, optional
            Dividend amounts per share.

        Returns
        -------
        float: Portfolio period return.
        """
        # Align
        common = weights.index.intersection(prices_start.index).intersection(prices_end.index)
        if len(common) == 0:
            return 0.0

        w = weights.reindex(common, fill_value=0.0)
        p0 = prices_start.reindex(common)
        p1 = prices_end.reindex(common)

        # Per-stock return
        stock_ret = (p1 / p0 - 1.0).fillna(0.0)

        # Portfolio return = weighted sum of stock returns
        portfolio_ret = (w * stock_ret).sum()

        return float(portfolio_ret)

    # ------------------------------------------------------------------
    # Generate trade orders
    # ------------------------------------------------------------------
    def generate_orders(self,
                        signal_date: int,
                        prev_weights: pd.Series,
                        target_weights: pd.Series,
                        prices: pd.DataFrame,
                        portfolio_value: float) -> pd.DataFrame:
        """
        Generate discrete trade orders from weight changes.

        Returns DataFrame with columns:
            ts_code, side, target_weight, weight_change, shares, price, amount
        """
        all_codes = target_weights.index.union(prev_weights.index)
        target = target_weights.reindex(all_codes, fill_value=0.0)
        prev = prev_weights.reindex(all_codes, fill_value=0.0)
        px = prices.set_index("ts_code")[self.execution_price].reindex(all_codes)

        orders = []
        for code in all_codes:
            dw = target[code] - prev[code]
            if abs(dw) < 1e-6:
                continue

            side = "buy" if dw > 0 else "sell"
            amount = abs(dw) * portfolio_value
            price = px[code]
            shares = int(amount / price) if price and price > 0 else 0

            if self.round_lot:
                shares = (shares // self.min_unit) * self.min_unit

            if shares > 0:
                orders.append({
                    "ts_code": code,
                    "side": side,
                    "target_weight": target[code],
                    "weight_change": dw,
                    "shares": shares,
                    "price": price,
                    "amount": shares * price,
                    "signal_date": signal_date,
                })

        return pd.DataFrame(orders)

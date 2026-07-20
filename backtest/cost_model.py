"""
A-share transaction cost model.

Explicit costs:
- Commission: 2.5bp (万2.5), min 5 CNY per order, both sides
- Stamp duty: 5bp (千0.5), sell only
- Transfer fee: 0.2bp (万0.2), both sides

Implicit costs:
- Slippage: configurable fixed basis points at open
- Market impact: optional volume-aligned model

All cost computations use raw (unadjusted) prices and amounts.
"""

import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class CostConfig:
    """Transaction cost parameters."""
    # Explicit costs
    commission_rate: float = 0.00025      # 2.5bp
    commission_min: float = 5.0           # min 5 CNY
    commission_apply: str = "both"        # "buy", "sell", "both"

    stamp_duty_rate: float = 0.0005       # 5bp
    stamp_duty_apply: str = "sell"

    transfer_fee_rate: float = 0.00002    # 0.2bp
    transfer_fee_apply: str = "both"

    # Implicit costs
    slippage_model: str = "fixed_bps"     # "fixed_bps" or "none"
    slippage_bps: float = 5.0             # 5bp

    # Execution
    min_unit: int = 100                   # 1 lot = 100 shares
    round_lot: bool = True

    @classmethod
    def from_yaml(cls, config: dict) -> "CostConfig":
        """Create CostConfig from YAML config dict."""
        costs = config.get("costs", config)
        commission = costs.get("commission", {})
        stamp = costs.get("stamp_duty", {})
        transfer = costs.get("transfer_fee", {})
        slippage = costs.get("slippage", {})
        execution = costs.get("execution", {})

        return cls(
            commission_rate=commission.get("rate", 0.00025),
            commission_min=commission.get("min_per_order", 5.0),
            commission_apply=commission.get("apply_to", "both"),
            stamp_duty_rate=stamp.get("rate", 0.0005),
            stamp_duty_apply=stamp.get("apply_to", "sell"),
            transfer_fee_rate=transfer.get("rate", 0.00002),
            transfer_fee_apply=transfer.get("apply_to", "both"),
            slippage_model=slippage.get("model", "fixed_bps"),
            slippage_bps=slippage.get("basis_points", 5.0),
            min_unit=execution.get("min_unit", 100),
            round_lot=execution.get("round_lot", True),
        )

    def stress_2x(self) -> "CostConfig":
        """Return a 2x cost stress scenario."""
        return CostConfig(
            commission_rate=self.commission_rate * 2,
            commission_min=self.commission_min,
            commission_apply=self.commission_apply,
            stamp_duty_rate=self.stamp_duty_rate * 2,
            stamp_duty_apply=self.stamp_duty_apply,
            transfer_fee_rate=self.transfer_fee_rate * 2,
            transfer_fee_apply=self.transfer_fee_apply,
            slippage_model=self.slippage_model,
            slippage_bps=self.slippage_bps * 2,
            min_unit=self.min_unit,
            round_lot=self.round_lot,
        )


class CostModel:
    """
    A-share transaction cost calculator.

    All costs are computed per-trade using raw (unadjusted) prices.
    """

    def __init__(self, config: Optional[CostConfig] = None):
        self.config = config or CostConfig()

    # ------------------------------------------------------------------
    # Per-trade cost computation
    # ------------------------------------------------------------------
    def compute_trade_cost(self, ts_code: str,
                           side: str,  # "buy" or "sell"
                           price: float,
                           shares: int,
                           amount: Optional[float] = None) -> Dict[str, float]:
        """
        Compute transaction costs for a single trade.

        Parameters
        ----------
        ts_code : str
            Stock code.
        side : str
            "buy" or "sell".
        price : float
            Execution price per share (raw).
        shares : int
            Number of shares.
        amount : float, optional
            Trade amount (price * shares). Computed if not provided.

        Returns
        -------
        dict with cost breakdown in CNY.
        """
        if amount is None:
            amount = price * shares

        costs = {
            "amount": amount,
            "shares": shares,
            "price": price,
            "commission": 0.0,
            "stamp_duty": 0.0,
            "transfer_fee": 0.0,
            "slippage": 0.0,
            "total_cost": 0.0,
        }

        # Commission
        if self.config.commission_apply in (side, "both"):
            costs["commission"] = max(
                amount * self.config.commission_rate,
                self.config.commission_min
            )

        # Stamp duty (sell only)
        if side == "sell" and self.config.stamp_duty_apply == "sell":
            costs["stamp_duty"] = amount * self.config.stamp_duty_rate

        # Transfer fee
        if self.config.transfer_fee_apply in (side, "both"):
            costs["transfer_fee"] = amount * self.config.transfer_fee_rate

        # Slippage (in basis points of trade amount)
        if self.config.slippage_model == "fixed_bps":
            costs["slippage"] = amount * (self.config.slippage_bps / 10000.0)

        costs["total_cost"] = (
            costs["commission"] +
            costs["stamp_duty"] +
            costs["transfer_fee"] +
            costs["slippage"]
        )

        return costs

    # ------------------------------------------------------------------
    # Portfolio-level cost computation
    # ------------------------------------------------------------------
    def compute_turnover_cost(self,
                              prev_weights: pd.Series,
                              new_weights: pd.Series,
                              prices: pd.Series,
                              portfolio_value: float) -> Dict[str, float]:
        """
        Compute total transaction cost for a portfolio rebalance.

        Parameters
        ----------
        prev_weights : pd.Series (index=ts_code)
            Previous portfolio weights.
        new_weights : pd.Series (index=ts_code)
            Target portfolio weights.
        prices : pd.Series (index=ts_code)
            Current execution prices (raw open).
        portfolio_value : float
            Total portfolio value in CNY.

        Returns
        -------
        dict with total costs and turnover.
        """
        # Align all series
        common_codes = prev_weights.index.intersection(
            new_weights.index
        ).intersection(prices.index)

        prev = prev_weights.reindex(common_codes, fill_value=0.0)
        new = new_weights.reindex(common_codes, fill_value=0.0)
        px = prices.reindex(common_codes)

        # Weight changes
        weight_change = new - prev

        # Sell orders (negative weight change)
        sell_mask = weight_change < 0
        buy_mask = weight_change > 0

        total_cost = 0.0
        total_turnover = 0.0
        buy_cost = 0.0
        sell_cost = 0.0

        for code in common_codes:
            dw = weight_change[code]
            if pd.isna(dw) or not np.isfinite(dw) or abs(dw) < 1e-8:
                continue

            trade_price = px[code]
            # Guard: skip invalid prices
            if pd.isna(trade_price) or trade_price <= 0 or not np.isfinite(trade_price):
                continue

            side = "buy" if dw > 0 else "sell"
            trade_amount = abs(dw) * portfolio_value
            trade_shares = int(trade_amount / trade_price)

            if self.config.round_lot:
                trade_shares = (trade_shares // self.config.min_unit) * self.config.min_unit
            if trade_shares <= 0:
                continue

            actual_amount = trade_shares * trade_price
            c = self.compute_trade_cost(code, side, trade_price, trade_shares, actual_amount)

            total_cost += c["total_cost"]
            total_turnover += abs(dw)

            if side == "buy":
                buy_cost += c["total_cost"]
            else:
                sell_cost += c["total_cost"]

        return {
            "total_cost_cny": total_cost,
            "total_cost_bps": (total_cost / portfolio_value * 10000) if portfolio_value > 0 else 0,
            "one_way_turnover": total_turnover,
            "buy_cost": buy_cost,
            "sell_cost": sell_cost,
        }

    # ------------------------------------------------------------------
    # Cost-burdened return
    # ------------------------------------------------------------------
    def compute_net_return(self, gross_return: float,
                           buy_cost_bps: float,
                           sell_cost_bps: float) -> float:
        """
        Compute net return after costs.

        Parameters
        ----------
        gross_return : float
            Portfolio gross return over the period.
        buy_cost_bps : float
            Buy-side cost in basis points.
        sell_cost_bps : float
            Sell-side cost in basis points.

        Returns
        -------
        float: Net return.
        """
        return gross_return - (buy_cost_bps + sell_cost_bps) / 10000.0

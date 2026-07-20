#!/usr/bin/env python
"""
Paper Broker — simulated trade execution with fill tracking.

Simulates execution at next-day open prices, tracks:
- Fill rate (what % of target shares were executed)
- Slippage vs assumed price
- Execution delay

Usage:
    python -m live.paper_broker --date 20260105
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("live.paper_broker")


class PaperBroker:
    """Simulated execution with fill tracking."""

    def __init__(self, date_str: str, slippage_tolerance_bps: float = 10.0):
        self.date_str = date_str
        self.date_int = int(date_str)
        self.slippage_tolerance_bps = slippage_tolerance_bps

    def execute(self) -> pd.DataFrame:
        """
        Simulate execution of orders at next-day open prices.

        Returns DataFrame with columns:
            ts_code, side, target_shares, filled_shares, fill_rate,
            assumed_price, actual_price, slippage_bps, cost_cny, status
        """
        orders = self._load_orders()
        if orders.empty:
            logger.info("No orders to execute")
            return pd.DataFrame()

        ready_orders = orders[orders["status"] == "READY"]
        if ready_orders.empty:
            logger.info("No ready orders to execute")
            return pd.DataFrame()

        # Get actual execution prices (next trading day open)
        codes = list(ready_orders["ts_code"].unique())
        actual_prices = self._get_actual_prices(codes)

        if actual_prices.empty:
            logger.error("No actual prices available — cannot execute")
            return pd.DataFrame()

        actual_px = actual_prices.set_index("ts_code")["open"]

        fills = []
        for _, order in ready_orders.iterrows():
            code = order["ts_code"]
            side = order["side"]
            target_shares = int(order["shares"])
            assumed_price = order["price"]
            actual_price = actual_px.get(code, np.nan)

            if pd.isna(actual_price) or actual_price <= 0:
                fills.append({
                    "ts_code": code, "side": side,
                    "target_shares": target_shares,
                    "filled_shares": 0, "fill_rate": 0.0,
                    "assumed_price": assumed_price,
                    "actual_price": 0.0,
                    "slippage_bps": 0.0,
                    "cost_cny": 0.0,
                    "status": "NO_PRICE"
                })
                continue

            # Simulate execution: assume full fill for liquid CSI 300 stocks
            filled_shares = target_shares
            fill_rate = 1.0

            # Compute slippage
            if assumed_price > 0:
                slippage = (actual_price / assumed_price - 1) * 10000
                if side == "buy":
                    slippage = slippage  # positive = paid more
                else:
                    slippage = -slippage  # positive = received less
            else:
                slippage = 0.0

            notional_cny = filled_shares * actual_price

            # Check slippage tolerance
            status = "FILLED"
            if abs(slippage) > self.slippage_tolerance_bps:
                status = "HIGH_SLIPPAGE"

            fills.append({
                "ts_code": code, "side": side,
                "target_shares": target_shares,
                "filled_shares": filled_shares,
                "fill_rate": fill_rate,
                "assumed_price": assumed_price,
                "actual_price": actual_price,
                "slippage_bps": round(slippage, 2),
                "notional_cny": round(notional_cny, 2),
                "cost_cny": round(notional_cny, 2),  # deprecated alias
                "status": status,
            })

        df = pd.DataFrame(fills)
        self._log_summary(df)
        return df

    def _load_orders(self) -> pd.DataFrame:
        """Load orders file."""
        path = Path(f"outputs/live/orders_{self.date_str}.csv")
        if not path.exists():
            logger.error(f"Orders file not found: {path}")
            return pd.DataFrame()
        return pd.read_csv(path)

    def _get_actual_prices(self, ts_codes: list) -> pd.DataFrame:
        """Get next-day open prices for execution.

        Returns empty DataFrame when execution prices are unavailable
        (DATA_INSUFFICIENT).  Callers should check for empty result and
        mark the execution as FAIL rather than silently skipping.
        """
        from data.calendar import get_calendar
        from data.panel_loader import get_loader

        cal = get_calendar()
        cal.load(start_date=self.date_str, end_date=self.date_str)
        exec_date = cal.next_trade_day(self.date_int, 1)
        exec_date_str = str(exec_date)

        # Detect no-next-trade-day edge case
        if exec_date == self.date_int:
            logger.error(
                f"DATA_INSUFFICIENT: no next trade day after {self.date_str} "
                f"— cannot determine execution date"
            )
            return pd.DataFrame()

        loader = get_loader()
        prices = loader.query_prices(
            start_date=exec_date_str, end_date=exec_date_str,
            ts_codes=ts_codes,
            fields=["ts_code", "trade_date", "open"],
            price_type="raw"
        )

        if prices.empty:
            logger.error(
                f"DATA_INSUFFICIENT: no raw prices for exec date "
                f"{exec_date_str} (signal date {self.date_str}). "
                f"Run: python run_research.py phase0 --start 20150101 "
                f"--end {exec_date_str}"
            )

        return prices

    def _log_summary(self, fills: pd.DataFrame):
        """Log execution summary.

        Distinguishes between:
          - executed (FILLED + HIGH_SLIPPAGE) — trades that actually occurred
          - clean (FILLED) — trades within slippage tolerance
          - high_slippage (HIGH_SLIPPAGE) — trades that filled but with high slippage
          - failed (NO_PRICE) — trades that could not execute
        """
        if fills.empty:
            return

        n_clean = len(fills[fills["status"] == "FILLED"])
        n_high_slip = len(fills[fills["status"] == "HIGH_SLIPPAGE"])
        n_executed = n_clean + n_high_slip
        n_failed = len(fills[fills["status"] == "NO_PRICE"])
        avg_fill = fills["fill_rate"].mean()
        # Slippage only for orders with a valid assumed price
        slip_mask = fills["slippage_bps"] != 0
        has_slip = fills[slip_mask]
        avg_slip = has_slip["slippage_bps"].mean() if len(has_slip) > 0 else 0.0
        total_notional = fills["cost_cny"].sum()

        logger.info(
            f"Execution: executed={n_executed} (clean={n_clean}, "
            f"high_slippage={n_high_slip}), failed={n_failed} | "
            f"avg fill={avg_fill:.1%}, "
            f"avg slip={avg_slip:.1f}bp, "
            f"total notional={total_notional:,.0f}"
        )

    def save_fills(self, fills: pd.DataFrame, output_dir: str = None):
        """Save fill report to CSV."""
        out_dir = Path(output_dir or "outputs/live")
        out_dir.mkdir(parents=True, exist_ok=True)

        filepath = out_dir / f"fills_{self.date_str}.csv"
        fills.to_csv(filepath, index=False)
        logger.info(f"Fills saved to {filepath}")
        return str(filepath)


def main():
    parser = argparse.ArgumentParser(
        description="Simulated trade execution"
    )
    parser.add_argument("--date", type=str, required=True,
                       help="Signal date YYYYMMDD")
    parser.add_argument("--slippage-tolerance", type=float, default=10.0,
                       help="Max slippage tolerance in bps")

    args = parser.parse_args()
    broker = PaperBroker(
        date_str=args.date,
        slippage_tolerance_bps=args.slippage_tolerance,
    )

    fills = broker.execute()

    if fills.empty:
        print("No fills generated")
        return 0

    broker.save_fills(fills)
    print(f"\nFills ({len(fills)} executions):")
    print(fills.to_string(index=False))

    # Summary
    filled = fills[fills["status"] == "FILLED"]
    print(f"\nFilled: {len(filled)}, "
          f"Avg fill rate: {fills['fill_rate'].mean():.1%}, "
          f"Total cost: {fills['cost_cny'].sum():,.0f} CNY")

    return 0


if __name__ == "__main__":
    sys.exit(main())

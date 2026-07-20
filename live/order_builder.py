#!/usr/bin/env python
"""
Order Builder — convert target signals to trade orders.

Loads signals from the signal service, compares with previous holdings,
and generates executable orders with constraint checks.

Usage:
    python -m live.order_builder --date 20260105
    python -m live.order_builder --date 20260105 --capital 100000000
"""

import argparse
import json
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
logger = logging.getLogger("live.order_builder")


class OrderBuilder:
    """Convert target weights to executable orders."""

    def __init__(self, date_str: str, capital: float = 100_000_000.0,
                 min_trade_amount: float = 5000.0,
                 round_lot: int = 100):
        self.date_str = date_str
        self.date_int = int(date_str)
        self.capital = capital
        self.min_trade_amount = min_trade_amount
        self.round_lot = round_lot
        self._signals_dir = Path("outputs/live")
        self._orders_dir = Path("outputs/live")

    def load_signals(self) -> pd.DataFrame:
        """Load signals for this date."""
        signal_path = self._signals_dir / f"signals_{self.date_str}.csv"
        if not signal_path.exists():
            logger.error(f"Signals file not found: {signal_path}")
            return pd.DataFrame()
        return pd.read_csv(signal_path)

    def load_previous_holdings(self) -> pd.Series:
        """
        Load previous holdings from the most recent order file.

        Returns pd.Series with index=ts_code, values=weight.
        """
        # Find the most recent orders file before this date
        order_files = sorted(self._orders_dir.glob("orders_*.csv"))
        prev_orders = None
        for f in order_files:
            file_date = f.stem.replace("orders_", "")
            if file_date < self.date_str:
                prev_orders = f

        if prev_orders is None:
            logger.info("No previous orders found — starting fresh")
            return pd.Series(dtype="float64")

        df = pd.read_csv(prev_orders)
        if df.empty:
            return pd.Series(dtype="float64")

        # Build holdings from executed orders
        holdings = df.set_index("ts_code")["target_weight"]
        return holdings

    def get_assumed_prices(self, ts_codes: list) -> pd.DataFrame:
        """
        Get signal-date close prices as assumed execution price.

        The order is placed at signal-date close (best estimate of next-day
        execution price). The paper broker will fill at next-day open, and the
        difference becomes real slippage.

        Falls back to latest available close if signal date has no data.
        """
        from data.calendar import get_calendar
        from data.panel_loader import get_loader

        cal = get_calendar()
        loader = get_loader()

        # Use signal-date close as assumed price
        cal.load(start_date=self.date_str, end_date=self.date_str)
        prices = loader.query_prices(
            start_date=self.date_str, end_date=self.date_str,
            ts_codes=ts_codes,
            fields=["ts_code", "trade_date", "close"],
            price_type="adj"
        )
        # Fallback: try previous trading day if signal date has no data
        if prices.empty:
            prev_date = cal.prev_trade_day(self.date_int, 1)
            prev_date_str = str(prev_date)
            prices = loader.query_prices(
                start_date=prev_date_str, end_date=prev_date_str,
                ts_codes=ts_codes,
                fields=["ts_code", "trade_date", "close"],
                price_type="adj"
            )
        if not prices.empty and "close" in prices.columns:
            prices = prices.rename(columns={"close": "assumed_price"})
        return prices

    def check_tradable(self, ts_codes: list) -> pd.DataFrame:
        """Check tradable status (limit, suspend, ST)."""
        from data.tradable import get_tradable
        from data.calendar import get_calendar
        from data.panel_loader import get_loader

        cal = get_calendar()
        cal.load(start_date=self.date_str, end_date=self.date_str)
        exec_date = cal.next_trade_day(self.date_int, 1)
        exec_date_str = str(exec_date)

        tradable = get_tradable()
        tradable.load(start_date=exec_date_str, end_date=exec_date_str)

        loader = get_loader()
        raw_prices = loader.query_prices(
            start_date=exec_date_str, end_date=exec_date_str,
            ts_codes=ts_codes,
            fields=["ts_code", "open"],
            price_type="raw"
        )

        limit_data = loader.query_limit_data(exec_date_str, ts_codes=ts_codes)

        mask = tradable.get_mask(
            ts_codes, exec_date,
            raw_prices=raw_prices,
            limit_data=limit_data,
        )
        return mask

    def build_orders(self) -> pd.DataFrame:
        """
        Build trade orders from signal vs current holdings delta.

        Returns DataFrame with columns:
            ts_code, side, target_weight, current_weight,
            weight_change, shares, price, amount, status
        """
        signals = self.load_signals()
        if signals.empty:
            logger.error("No signals to build orders from")
            return pd.DataFrame()

        current_holdings = self.load_previous_holdings()
        target_weights = signals.set_index("ts_code")["target_weight"]

        # All stocks involved
        all_codes = list(
            set(target_weights.index) | set(current_holdings.index)
        )

        # Get assumed prices (signal-date close)
        prices = self.get_assumed_prices(all_codes)
        if prices.empty:
            logger.warning(f"No assumed prices for {self.date_str}")
            return pd.DataFrame()

        px = prices.set_index("ts_code")["assumed_price"]

        # Check tradable status
        mask = self.check_tradable(all_codes)
        can_buy = (
            mask.set_index("ts_code")["can_buy"]
            if not mask.empty else None
        )
        can_sell = (
            mask.set_index("ts_code")["can_sell"]
            if not mask.empty else None
        )

        orders = []
        for code in all_codes:
            target = target_weights.get(code, 0.0)
            current = current_holdings.get(code, 0.0)
            dw = target - current

            if abs(dw) < 1e-8:
                continue

            side = "buy" if dw > 0 else "sell"
            amount = abs(dw) * self.capital
            price = px.get(code, 0.0)

            if pd.isna(price) or price <= 0:
                orders.append({
                    "ts_code": code, "side": side,
                    "target_weight": target, "current_weight": current,
                    "weight_change": dw, "shares": 0,
                    "price": 0.0, "amount": 0.0,
                    "status": "NO_PRICE"
                })
                continue

            # Round lot adjustment
            shares = int(amount / price)
            shares = (shares // self.round_lot) * self.round_lot

            if shares <= 0:
                orders.append({
                    "ts_code": code, "side": side,
                    "target_weight": target, "current_weight": current,
                    "weight_change": dw, "shares": 0,
                    "price": price, "amount": 0.0,
                    "status": "TOO_SMALL"
                })
                continue

            actual_amount = shares * price

            # Min trade amount filter
            if actual_amount < self.min_trade_amount:
                orders.append({
                    "ts_code": code, "side": side,
                    "target_weight": target, "current_weight": current,
                    "weight_change": dw, "shares": shares,
                    "price": price, "amount": actual_amount,
                    "status": "BELOW_MIN"
                })
                continue

            # Tradable checks
            if side == "buy" and can_buy is not None:
                if not can_buy.get(code, True):
                    orders.append({
                        "ts_code": code, "side": side,
                        "target_weight": target, "current_weight": current,
                        "weight_change": dw, "shares": 0,
                        "price": price, "amount": 0.0,
                        "status": "CANNOT_BUY"
                    })
                    continue

            if side == "sell" and can_sell is not None:
                if not can_sell.get(code, True):
                    orders.append({
                        "ts_code": code, "side": side,
                        "target_weight": target, "current_weight": current,
                        "weight_change": dw, "shares": 0,
                        "price": price, "amount": 0.0,
                        "status": "CANNOT_SELL"
                    })
                    continue

            # Cash constraint (rough check)
            if side == "buy" and actual_amount > self.capital * 0.30:
                orders.append({
                    "ts_code": code, "side": side,
                    "target_weight": target, "current_weight": current,
                    "weight_change": dw, "shares": shares,
                    "price": price, "amount": actual_amount,
                    "status": "CASH_LIMIT"
                })
                continue

            orders.append({
                "ts_code": code, "side": side,
                "target_weight": target, "current_weight": current,
                "weight_change": dw, "shares": shares,
                "price": price, "amount": actual_amount,
                "status": "READY"
            })

        df = pd.DataFrame(orders)
        if df.empty:
            logger.info("No orders needed — portfolio unchanged")
        else:
            n_ready = len(df[df["status"] == "READY"])
            n_blocked = len(df[df["status"] != "READY"])
            logger.info(
                f"Orders: {n_ready} ready, {n_blocked} blocked"
            )

        return df

    def save_orders(self, orders: pd.DataFrame):
        """Save orders to CSV."""
        out_dir = Path(self._orders_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        filepath = out_dir / f"orders_{self.date_str}.csv"
        orders.to_csv(filepath, index=False)
        logger.info(f"Orders saved to {filepath}")
        return str(filepath)


def main():
    parser = argparse.ArgumentParser(
        description="Build trade orders from target signals"
    )
    parser.add_argument("--date", type=str, required=True,
                       help="Signal date YYYYMMDD")
    parser.add_argument("--capital", type=float, default=100_000_000.0,
                       help="Portfolio capital in CNY")

    args = parser.parse_args()
    builder = OrderBuilder(date_str=args.date, capital=args.capital)
    orders = builder.build_orders()

    if orders.empty:
        print("No orders generated")
        return 0

    builder.save_orders(orders)
    print(f"\nOrders ({len(orders)} entries):")
    print(orders.to_string(index=False))

    # Summary
    ready = orders[orders["status"] == "READY"]
    blocked = orders[orders["status"] != "READY"]
    print(f"\nReady: {len(ready)}, Blocked: {len(blocked)}")
    if len(blocked) > 0:
        print("Blocked orders:")
        for _, row in blocked.iterrows():
            print(f"  {row['ts_code']} {row['side']}: {row['status']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

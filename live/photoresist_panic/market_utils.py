"""Package-local market-data helpers used by the live pipeline."""
from __future__ import annotations

import numpy as np
import pandas as pd


def build_trading_calendar(prices: pd.DataFrame) -> np.ndarray:
    """Return the sorted exchange-date grid represented by the price panel."""
    if prices.empty or "trade_date" not in prices.columns:
        return np.array([], dtype=int)
    return np.array(sorted(int(d) for d in prices["trade_date"].dropna().unique()))


def is_st_stock(ts_code: str, stock_status: pd.DataFrame | None) -> bool:
    """Check ST/*ST status without importing a CLI script module."""
    if stock_status is None or stock_status.empty:
        return False
    stock_row = stock_status[stock_status["ts_code"].astype(str) == str(ts_code)]
    if stock_row.empty:
        return False
    for col in stock_row.columns:
        if "st" in col.lower() or "name" in col.lower():
            value = str(stock_row[col].iloc[0]).upper()
            if "ST" in value or "*ST" in value:
                return True
    return False


def compute_amount_rolling_avg(
    prices: pd.DataFrame, window: int = 20, min_periods: int = 10
) -> pd.Series:
    """Average amount indexed by (ts_code, trade_date), matching frozen eligibility."""
    if prices.empty or "amount" not in prices.columns:
        return pd.Series(dtype=float)
    frame = prices[["ts_code", "trade_date", "amount"]].copy()
    frame = frame.sort_values(["ts_code", "trade_date"])
    frame["amount_rolling_avg"] = frame.groupby("ts_code")["amount"].transform(
        lambda values: values.rolling(window, min_periods=min_periods).mean()
    )
    return frame.set_index(["ts_code", "trade_date"])["amount_rolling_avg"]

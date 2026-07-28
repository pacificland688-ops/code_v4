"""Package-local market-data helpers used by the live pipeline."""
from __future__ import annotations

import numpy as np
import pandas as pd


def build_trading_calendar(prices: pd.DataFrame) -> np.ndarray:
    """Return the sorted exchange-date grid represented by the price panel."""
    if prices.empty or "trade_date" not in prices.columns:
        return np.array([], dtype=int)
    return np.array(sorted(int(d) for d in prices["trade_date"].dropna().unique()))


def is_st_stock(ts_code: str, stock_status: pd.DataFrame | None,
                trade_date: int | None = None,
                namechange: pd.DataFrame | None = None) -> bool:
    """Check ST/*ST status at a specific trade_date (PIT).

    Resolution order:
    1. namechange (股票曾用名) — historical names with start_date/end_date.
       If available, this provides true PIT ST detection including 摘帽.
    2. stock_status with trade_date column — historical records, sorted by date.
    3. stock_status without trade_date — current name only (best-effort, may
       miss historical ST→normal transitions).

    PIT note: without namechange data, stocks that were ST historically and
    later had ST removed (摘帽) will be misclassified as never-ST.
    """
    if stock_status is None or stock_status.empty:
        return False

    code_str = str(ts_code)

    # ── Priority 1: namechange historical data ──────────────────────────
    if namechange is not None and not namechange.empty:
        nc = namechange[namechange["ts_code"].astype(str) == code_str].copy()
        if not nc.empty:
            # namechange typically has start_date, end_date, name columns
            date_col = None
            for c in ["start_date", "trade_date", "ann_date"]:
                if c in nc.columns:
                    date_col = c
                    break
            if date_col is not None and trade_date is not None:
                nc[date_col] = pd.to_numeric(nc[date_col], errors="coerce")
                nc = nc.sort_values(date_col)
                # Find the name effective at trade_date
                applicable = nc[nc[date_col] <= trade_date]
                if not applicable.empty:
                    latest = applicable.iloc[-1]
                    for col in latest.index:
                        if "name" in col.lower():
                            val = str(latest[col]).upper()
                            if "ST" in val or "*ST" in val:
                                return True
                    return False

    # ── Priority 2/3: stock_status ─────────────────────────────────────
    mask = stock_status["ts_code"].astype(str) == code_str
    if trade_date is not None and "trade_date" in stock_status.columns:
        mask = mask & (stock_status["trade_date"].astype(int) <= trade_date)
    stock_rows = stock_status[mask]
    if stock_rows.empty:
        return False
    # Sort by date descending so iloc[-1] gives the latest record
    if trade_date is not None and "trade_date" in stock_rows.columns:
        stock_rows = stock_rows.sort_values("trade_date")
    stock_row = stock_rows.iloc[-1:] if trade_date is not None else stock_rows.iloc[:1]
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

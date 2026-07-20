"""
Point-in-time (PIT) as-of alignment for factor data.

Monthly fundamental factors (ep_cs, bp_cs, sp_cs, etc.) have sparse
trade_date coverage — they only appear on financial reporting dates.
This module carries forward the latest known value to weekly signal dates
so that fundamental factors can participate in weekly rebalancing.

Alignment rules
---------------
- For each ``(ts_code, signal_date)``, use the latest factor value whose
  ``trade_date <= signal_date``.
- **Stale limits**: technical/price factors max 5 trading days stale;
  fundamental factors max 63 trading days (≈ 1 quarter) stale.
- **No future leakage**: never use ``factor.trade_date > signal_date``.
- **No duplicates**: each ``(ts_code, signal_date)`` appears at most once.
- **Schema**: output columns are ``[ts_code, trade_date, <factor_col>]``
  where ``trade_date`` is the **signal_date** (not the original factor date).
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Set

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Default fundamental factors (overridable via config)
DEFAULT_FUNDAMENTAL_FACTORS = {"ep_cs", "bp_cs", "sp_cs", "log_market_cap_cs"}


def align_factors_to_signal_dates(
    factor_dfs: Dict[str, pd.DataFrame],
    signal_dates: List[int],
    alignment_config: Optional[dict] = None,
    trade_dates: Optional[List[int]] = None,
) -> Dict[str, pd.DataFrame]:
    """Align all factor DataFrames to signal dates via PIT as-of merge.

    Parameters
    ----------
    factor_dfs : dict
        ``{factor_name: DataFrame}`` with columns ``[ts_code, trade_date, <value>]``.
        The ``trade_date`` column is the original factor observation date.
    signal_dates : list of int
        Target signal dates YYYYMMDD to align to.
    alignment_config : dict, optional
        Configuration with keys:
        - ``technical_max_stale_trading_days``: int (default 5)
        - ``fundamental_max_stale_trading_days``: int (default 63)
        - ``fundamental_factors``: list[str] (default DEFAULT_FUNDAMENTAL_FACTORS)
    trade_dates : list of int, optional
        Sorted list of all trading dates for stale-day counting.
        If not provided, stale checks use calendar-day difference as approximation.

    Returns
    -------
    dict[str, pd.DataFrame]
        Aligned factor DataFrames with ``trade_date`` set to signal_date.
        Each DataFrame has columns ``[ts_code, trade_date, <factor_col>]``.
    """
    if alignment_config is None:
        alignment_config = {}

    tech_max_stale = int(alignment_config.get("technical_max_stale_trading_days", 5))
    fund_max_stale = int(alignment_config.get("fundamental_max_stale_trading_days", 63))
    fundamental_factors = set(
        alignment_config.get("fundamental_factors", list(DEFAULT_FUNDAMENTAL_FACTORS))
    )

    if not signal_dates:
        logger.warning("No signal dates provided — returning empty dict")
        return {}

    signal_dates_sorted = sorted(int(d) for d in signal_dates)
    trade_dates_sorted = (
        sorted(int(d) for d in trade_dates) if trade_dates else None
    )

    aligned: Dict[str, pd.DataFrame] = {}

    for factor_name, df in factor_dfs.items():
        if df is None or df.empty:
            aligned[factor_name] = pd.DataFrame()
            continue

        # Determine factor category
        is_fundamental = factor_name in fundamental_factors
        max_stale = fund_max_stale if is_fundamental else tech_max_stale

        # Find the value column
        value_col = _find_value_column(df, factor_name)
        if value_col is None:
            logger.warning("Factor '%s': no value column found — skipping", factor_name)
            aligned[factor_name] = pd.DataFrame()
            continue

        try:
            aligned_df = _align_single_factor(
                df, value_col, signal_dates_sorted, max_stale,
                trade_dates_sorted, factor_name,
            )
            aligned[factor_name] = aligned_df
        except Exception as exc:
            logger.error("Factor '%s': alignment failed: %s", factor_name, exc)
            aligned[factor_name] = pd.DataFrame()

    # Report coverage
    for name, adf in aligned.items():
        if adf.empty:
            logger.info("Factor '%s': aligned → EMPTY", name)
        else:
            logger.info(
                "Factor '%s': aligned → %d rows, %d dates, %d stocks",
                name, len(adf), adf["trade_date"].nunique(),
                adf["ts_code"].nunique() if "ts_code" in adf.columns else 0,
            )

    return aligned


def _align_single_factor(
    df: pd.DataFrame,
    value_col: str,
    signal_dates: List[int],
    max_stale_days: int,
    trade_dates: Optional[List[int]],
    factor_name: str = "",
) -> pd.DataFrame:
    """Align a single factor to signal dates.

    For each (ts_code, signal_date), find the latest factor observation
    with ``trade_date <= signal_date`` and ``signal_date - trade_date <= max_stale``.

    Uses an efficient sort-merge approach:
    1. Sort factor data by (ts_code, trade_date)
    2. For each signal_date, use searchsorted to find the latest observation
    3. Apply stale threshold
    """
    df = df.copy()
    df["trade_date"] = df["trade_date"].astype(int)

    # --- Categorical hygiene: remove unused categories to prevent
    #     groupby errors on real parquet data with categorical ts_code ---
    if hasattr(df["ts_code"], "cat"):
        try:
            df["ts_code"] = df["ts_code"].cat.remove_unused_categories()
        except Exception:
            pass  # best-effort; if it fails, groupby with observed=True handles it

    # Drop rows with NaN factor values
    df = df.dropna(subset=[value_col])
    if df.empty:
        return pd.DataFrame()

    # Sort by ts_code, trade_date
    df = df.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)

    rows = []
    for sd in signal_dates:
        sd_int = int(sd)

        # For each stock, find the latest observation <= signal_date
        mask = df["trade_date"] <= sd_int
        if not mask.any():
            continue

        candidate = df[mask].copy()

        # Re-remove unused categories after filtering
        if hasattr(candidate["ts_code"], "cat"):
            try:
                candidate["ts_code"] = candidate["ts_code"].cat.remove_unused_categories()
            except Exception:
                pass

        # Per stock, take the row with the max trade_date.
        # observed=True + sort=False: safe with categorical ts_code
        # that may have unused category levels.
        idx = candidate.groupby("ts_code", observed=True, sort=False)["trade_date"].idxmax()
        latest = candidate.loc[idx]

        # Apply stale threshold
        if trade_dates is not None:
            # Count trading days between observation and signal_date
            latest["_stale_days"] = latest["trade_date"].apply(
                lambda td: _count_trading_days_between(td, sd_int, trade_dates)
            )
        else:
            # Fallback: convert to datetime for calendar day difference,
            # then divide by ~1.4 to approximate trading days
            latest["_stale_days"] = latest["trade_date"].apply(
                lambda td: _calendar_days_between(td, sd_int) / 1.4
            )

        latest = latest[latest["_stale_days"] <= max_stale_days]

        if latest.empty:
            continue

        # Build output rows
        for _, row in latest.iterrows():
            rows.append({
                "ts_code": row["ts_code"],
                "trade_date": sd_int,  # signal_date becomes the output trade_date
                value_col: row[value_col],
            })

    if not rows:
        return pd.DataFrame()

    result = pd.DataFrame(rows)
    # Ensure no duplicates
    result = result.drop_duplicates(subset=["ts_code", "trade_date"], keep="last")

    return result


def _count_trading_days_between(
    from_date: int, to_date: int, trade_dates: List[int]
) -> int:
    """Count trading days in (from_date, to_date] using a sorted trade date list."""
    from bisect import bisect_right, bisect_left

    lo = bisect_right(trade_dates, from_date)
    hi = bisect_left(trade_dates, to_date + 1)
    return max(0, hi - lo)


def _calendar_days_between(from_date: int, to_date: int) -> int:
    """Compute calendar days between two YYYYMMDD dates.

    Uses proper datetime parsing — NOT integer subtraction.
    """
    from datetime import datetime
    d1 = datetime.strptime(str(from_date), "%Y%m%d")
    d2 = datetime.strptime(str(to_date), "%Y%m%d")
    return (d2 - d1).days


def _find_value_column(df: pd.DataFrame, factor_name: str = "") -> Optional[str]:
    """Find the factor value column, excluding metadata columns."""
    meta = {"ts_code", "trade_date"}
    candidates = [c for c in df.columns if c not in meta]
    if not candidates:
        return None
    # Prefer columns that match the factor name
    for c in candidates:
        if factor_name.replace("_cs", "") in c.lower():
            return c
    return candidates[0]

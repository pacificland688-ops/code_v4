"""
Shared time utilities for factor evaluation.

Provides a strictly correct ``matured_ic_cutoff`` that uses real
trading dates (via ``bisect_left``) instead of YYYYMMDD integer
subtraction, which leaks future information across month boundaries.

Rules
-----
- NEVER use ``signal_date - 8`` or ``pd.DateOffset(days=...)``
  as a final cutoff.
- NEVER use ``signal_date - xxx`` or ``date - xxx`` for date-window
  arithmetic — use ``calendar_month_lookback_start()`` instead.
- The cutoff MUST be the ``horizon``-th trading day strictly before
  the signal date, measured on the actual trading calendar.
- All IC, coverage, and merge checks use ``trade_date <= cutoff_date``.
"""

from __future__ import annotations

from bisect import bisect_left
from typing import List, Optional, Sequence, Tuple

import pandas as pd


def matured_ic_cutoff(
    signal_date: int,
    horizon: int,
    trade_dates: Sequence[int],
) -> Optional[int]:
    """Return the latest trade_date whose forward return has fully matured.

    For a forward return of ``horizon`` trading days, a factor measured
    on date ``T`` uses prices through ``T + horizon``.  To be usable at
    ``signal_date`` we need ``T + horizon < signal_date``, i.e.
    ``T`` must be at least ``horizon + 1`` trading days before
    ``signal_date``.

    Parameters
    ----------
    signal_date : int
        Signal date YYYYMMDD.
    horizon : int
        Forward-return horizon in **trading days** (e.g. 5).
    trade_dates : sequence of int
        All known trading dates, sorted ascending.

    Returns
    -------
    int or None
        The latest trade_date that is safe to use, or ``None`` if no
        such date exists (lookback too short).
    """
    dates = sorted({int(d) for d in trade_dates})
    if not dates:
        return None

    pos = bisect_left(dates, int(signal_date))
    # We need strict inequality: trade_date + horizon < signal_date,
    # which means the LATEST safe trade_date is the one at position
    # (pos - horizon - 1).
    cutoff_pos = pos - int(horizon) - 1
    if cutoff_pos < 0:
        return None
    return dates[cutoff_pos]


def trading_days_in_window(
    trade_dates: Sequence[int],
    start_date: int,
    end_date: int,
) -> List[int]:
    """Return trading dates in [start_date, end_date] (inclusive).

    Parameters
    ----------
    trade_dates : sequence of int
        All known trading dates, sorted ascending.
    start_date : int
        Start date YYYYMMDD (inclusive).
    end_date : int
        End date YYYYMMDD (inclusive).

    Returns
    -------
    list[int]
    """
    dates = sorted({int(d) for d in trade_dates})
    lo = bisect_left(dates, int(start_date))
    hi = bisect_left(dates, int(end_date) + 1)  # inclusive upper bound
    return dates[lo:hi]


# ---------------------------------------------------------------------------
# Calendar-aware date window helpers
# ---------------------------------------------------------------------------

def calendar_month_lookback_start(signal_date: int, months: int) -> int:
    """Return the YYYYMMDD date ``months`` calendar months before signal_date.

    Uses ``pd.DateOffset(months=...)`` — no YYYYMMDD integer arithmetic.

    Parameters
    ----------
    signal_date : int
        Reference date YYYYMMDD.
    months : int
        Number of calendar months to go back.

    Returns
    -------
    int
        Start date YYYYMMDD.
    """
    dt = pd.to_datetime(str(signal_date), format="%Y%m%d")
    start = dt - pd.DateOffset(months=months)
    return int(start.strftime("%Y%m%d"))


def matured_lookback_window(
    signal_date: int,
    horizon: int,
    lookback_months: int,
    trade_dates: Sequence[int],
) -> Tuple[int, int]:
    """Return ``(lookback_start, ic_cutoff)`` for a signal date.

    - ``lookback_start`` = ``signal_date`` minus ``lookback_months``
      calendar months (via ``pd.DateOffset``).
    - ``ic_cutoff`` = latest trade_date whose forward return has fully
      matured before ``signal_date`` (via ``matured_ic_cutoff``).

    Both values are computed from the real trading calendar — no
    YYYYMMDD integer subtraction.

    Parameters
    ----------
    signal_date : int
        Signal date YYYYMMDD.
    horizon : int
        Forward-return horizon in trading days.
    lookback_months : int
        Number of calendar months to look back.
    trade_dates : sequence of int
        Sorted trading dates.

    Returns
    -------
    (int, int)
        ``(lookback_start_ymd, ic_cutoff_ymd)``.
    """
    start = calendar_month_lookback_start(signal_date, lookback_months)
    cutoff = matured_ic_cutoff(signal_date, horizon, trade_dates)
    if cutoff is None:
        raise ValueError(
            f"Cannot compute matured IC cutoff for signal_date={signal_date}, "
            f"horizon={horizon}: insufficient trading-date history"
        )
    return start, cutoff

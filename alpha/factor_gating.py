"""
Historical coverage gate for factor eligibility.

Evaluates each factor at each signal_date using ONLY data that was
knowable at that point in time — no future information leakage.

Gate dimensions
---------------
1. **Date coverage** — fraction of expected trading days in the
   matured lookback window that have factor data.
2. **Per-date stock count** — on >= 50 % of those dates, at least
   ``min_stocks_per_date`` stocks have non-NaN factor values.
3. **Merge survival rate** — when the factor is merged with
   forward returns (on the SAME trade_date), >= ``min_merge_rate``
   of the factor rows survive.

ALL checks use the MATURED window (``trade_date <= ic_cutoff``)
where ``ic_cutoff`` is computed from the real trading calendar via
``matured_ic_cutoff()`` — no YYYYMMDD integer subtraction, no
``pd.DateOffset(days=...)`` as a final cutoff.
"""

from __future__ import annotations

import logging
from typing import Optional, Sequence

import pandas as pd

logger = logging.getLogger(__name__)


def evaluate_factor_coverage_at_date(
    factor_df: pd.DataFrame,
    fwd_returns_df: pd.DataFrame,
    signal_date: int,
    lookback_months: int = 12,
    horizon: int = 5,
    trade_dates: Optional[Sequence[int]] = None,
    min_date_coverage: float = 0.70,
    min_stocks_per_date: int = 30,
    min_merge_rate: float = 0.30,
    expected_dates: Optional[Sequence[int]] = None,
) -> bool:
    """Evaluate whether a factor has sufficient PIT data quality.

    Parameters
    ----------
    factor_df : pd.DataFrame
        Factor panel with columns ``[ts_code, trade_date, <factor_col>]``.
    fwd_returns_df : pd.DataFrame
        Forward returns panel with columns ``[ts_code, trade_date, fwd_ret_*d]``.
    signal_date : int
        Signal date YYYYMMDD.  Only matured data is used.
    lookback_months : int
        Number of calendar months to look back.
    horizon : int
        Forward-return horizon in **trading days** (e.g. 5).
    trade_dates : sequence of int, optional
        Sorted trading dates for the real calendar cutoff.  If not
        provided, returns ``False`` instead of using unsafe date arithmetic.
    min_date_coverage : float
        Minimum fraction of expected trading days with factor data.
    min_stocks_per_date : int
        Minimum number of stocks per date that must have non-NaN values.
    min_merge_rate : float
        Minimum fraction of factor rows that survive a merge with
        forward returns on the same trade_date.
    expected_dates : sequence of int, optional
        Expected signal dates (e.g. weekly rebalance dates).  If provided,
        only those falling within the matured window are used as the
        denominator for date coverage.  This prevents daily-frequency
        factor denominators from rejecting weekly-aligned factors.
        If None, falls back to ``lookback_months * 21`` (legacy behaviour).

    Returns
    -------
    bool
        True if the factor passes all three coverage dimensions.
    """
    # ------------------------------------------------------------------
    # 0. Fast-fail guards
    # ------------------------------------------------------------------
    if factor_df is None or factor_df.empty:
        return False

    value_cols = [
        c for c in factor_df.columns if c not in ("ts_code", "trade_date")
    ]
    if not value_cols:
        return False
    value_col = value_cols[0]

    # ------------------------------------------------------------------
    # 1. Compute the matured cutoff date (real trading calendar)
    # ------------------------------------------------------------------
    from alpha.time_utils import matured_ic_cutoff

    if not trade_dates:
        logger.warning(
            "trade_dates required for leakage-safe coverage gate "
            "(signal=%d) — returning False", signal_date,
        )
        return False

    ic_cutoff = matured_ic_cutoff(signal_date, horizon, trade_dates)

    if ic_cutoff is None:
        logger.debug(
            "factor=%s signal=%d: no matured cutoff (horizon=%d)",
            value_col, signal_date, horizon,
        )
        return False

    # ------------------------------------------------------------------
    # 2. Define the PIT lookback window (real calendar, no integer math)
    # ------------------------------------------------------------------
    from alpha.time_utils import calendar_month_lookback_start
    lookback_start = calendar_month_lookback_start(signal_date, lookback_months)

    # ALL checks use ONLY dates <= ic_cutoff (matured window).
    window = factor_df[
        (factor_df["trade_date"] <= ic_cutoff) &
        (factor_df["trade_date"] >= lookback_start)
    ]
    if window.empty or window["trade_date"].nunique() == 0:
        return False

    # ------------------------------------------------------------------
    # Dimension 1 — Date coverage (in the *matured* window)
    # ------------------------------------------------------------------
    n_dates = window["trade_date"].nunique()

    if expected_dates is not None:
        # Use the caller's signal-frequency dates as denominator.
        # Only count dates that fall within the PIT matured window.
        expected_window_dates = [
            d for d in expected_dates
            if lookback_start <= int(d) <= ic_cutoff
        ]
        expected_dates_count = len(expected_window_dates)
        if expected_dates_count == 0:
            logger.debug(
                "factor=%s signal=%d: no expected_dates in matured window",
                value_col, signal_date,
            )
            return False
    else:
        # Legacy: approximate daily frequency denominator
        expected_dates_count = lookback_months * 21  # approx trading days

    if n_dates / expected_dates_count < min_date_coverage:
        logger.debug(
            "factor=%s signal=%d: date coverage %.2f < %.2f "
            "(n_dates=%d, expected=%d)",
            value_col, signal_date,
            n_dates / expected_dates_count, min_date_coverage,
            n_dates, expected_dates_count,
        )
        return False

    # ------------------------------------------------------------------
    # Dimension 2 — Per-date stock count (in the *matured* window)
    # ------------------------------------------------------------------
    per_date_stocks = window.groupby("trade_date")[value_col].apply(
        lambda s: s.notna().sum()
    )
    sufficient_dates = (per_date_stocks >= min_stocks_per_date).sum()
    if sufficient_dates < len(per_date_stocks) * 0.50:
        logger.debug(
            "factor=%s signal=%d: sufficient-stock dates %d/%d < 50%%",
            value_col, signal_date, sufficient_dates, len(per_date_stocks),
        )
        return False

    # ------------------------------------------------------------------
    # Dimension 3 — Merge survival with forward returns (matured only)
    # ------------------------------------------------------------------
    if fwd_returns_df is not None and not fwd_returns_df.empty:
        ret_col = _find_fwd_ret_col(fwd_returns_df)
        if ret_col is not None:
            test_dates = sorted(window["trade_date"].unique())
            if not test_dates:
                return False

            merge_total = 0
            merge_survived = 0

            for date in test_dates:
                day_factor = window[window["trade_date"] == date]
                n_valid = day_factor[value_col].notna().sum()
                if n_valid == 0:
                    continue

                day_fwd = fwd_returns_df[
                    fwd_returns_df["trade_date"] == date
                ]
                if day_fwd.empty:
                    merge_total += n_valid
                    continue

                merged = (
                    day_factor[["ts_code", value_col]]
                    .dropna()
                    .merge(
                        day_fwd[["ts_code", ret_col]].dropna(),
                        on="ts_code",
                    )
                )
                merge_total += n_valid
                merge_survived += len(merged)

            if merge_total > 0 and merge_survived / merge_total < min_merge_rate:
                logger.debug(
                    "factor=%s signal=%d: merge rate %.3f < %.3f",
                    value_col, signal_date,
                    merge_survived / merge_total, min_merge_rate,
                )
                return False

    return True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_fwd_ret_col(fwd_returns_df: pd.DataFrame) -> Optional[str]:
    """Return the first fwd_ret_* column name, or None."""
    for c in fwd_returns_df.columns:
        if c.startswith("fwd_ret_") and c not in ("ts_code", "trade_date"):
            return c
    return None

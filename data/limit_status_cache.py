"""
limit_status cache merge-write helper.

Prevents short-window Phase 0 runs from overwriting broader
limit_status cache with partial data.  Read-modify-write per
affected year/month partition.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)


def _normalize_limit_status_df(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure trade_date is int and year/month partition columns exist."""
    df = df.copy()
    df["trade_date"] = df["trade_date"].astype(int)
    if "year" not in df.columns:
        df["year"] = df["trade_date"] // 10000
    if "month" not in df.columns:
        df["month"] = (df["trade_date"] % 10000) // 100
    return df


def _month_bounds(year: int, month: int) -> tuple[str, str]:
    """Return start/end date strings for a given year/month."""
    start = f"{year}{month:02d}01"
    if month == 12:
        end = f"{year}1231"
    else:
        next_month = datetime(year, month + 1, 1)
        end_dt = next_month - timedelta(days=1)
        end = end_dt.strftime("%Y%m%d")
    return start, end


def write_limit_status_merged(loader, lim_df: pd.DataFrame) -> int:
    """
    Merge new limit_status rows into existing year/month partitions.

    Rules:
    - Derive year/month from trade_date
    - For each affected month, read existing partition data
    - Concat existing + new month data
    - drop_duplicates(["ts_code", "trade_date"], keep="last")
    - Replace the affected month partition with merged data

    This preserves existing dates in the same month that are not
    in the new data — short-window Phase 0 runs no longer shrink
    the limit_status cache.

    Parameters
    ----------
    loader : PanelLoader
    lim_df : pd.DataFrame
        New limit_status rows (must have ts_code, trade_date, up_limit, down_limit).

    Returns
    -------
    int: Number of rows written across all affected partitions.
    """
    if lim_df.empty:
        return 0

    lim_df = _normalize_limit_status_df(lim_df)
    total_written = 0

    for (year, month), new_month in lim_df.groupby(["year", "month"]):
        month_start, month_end = _month_bounds(int(year), int(month))

        # Read existing data for this month
        existing = loader.query(
            "limit_status",
            start_date=month_start,
            end_date=month_end,
        )

        if not existing.empty:
            existing = _normalize_limit_status_df(existing)
            combined = pd.concat([existing, new_month], ignore_index=True)
        else:
            combined = new_month.copy()

        # Deduplicate: keep last (new data wins)
        n_before = len(combined)
        combined = combined.drop_duplicates(
            ["ts_code", "trade_date"], keep="last"
        )
        n_dropped = n_before - len(combined)
        if n_dropped > 0:
            logger.debug(
                f"write_limit_status_merged({year}/{month:02d}): "
                f"dropped {n_dropped} duplicate rows"
            )

        # Ensure partition columns are correct
        combined = _normalize_limit_status_df(combined)

        # Write merged partition
        loader.write_data(
            combined,
            "limit_status",
            partition_cols=["year", "month"],
            dedupe_keys=["ts_code", "trade_date"],
            replace_partitions=True,
        )
        total_written += len(combined)

    logger.info(
        f"write_limit_status_merged: input={len(lim_df)} new rows, "
        f"written={total_written} total rows across {lim_df['month'].nunique()} months"
    )
    return total_written

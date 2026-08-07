"""Pure computation for the sector-panic holding-period sensitivity study.

Exploratory, post-hoc analysis (status EXPLORATORY_POST_HOC).  It freezes
every parameter except ``execution.hold_days``: events, entries, stops,
costs, and the next-event boundary are identical to the frozen 20-day
contract.  The functions in this module read or write no data; they take
ledger frames, paths, and calendars as arguments so the methodology stays
directly testable.

Statistical conventions (pre-registered before any run):

- Primary table is per (sector, rule, hold, frozen sample split).
- The paired view compares each arm to the 20-day baseline on the COMMON
  support set (events realized in both arms); the full-sample strategy
  view is reported alongside so complete-case selection bias does not
  drive the conclusion.
- Bootstrap: event-level paired resampling with a fixed seed (primary);
  moving-block bootstrap with pre-fixed block sizes {2, 3} (auxiliary).
- No parameter is promoted from historical data: the only adjudication
  window is the data frozen after 2026-08-05.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .backtest import REALIZED_STATUSES

MAX_CURVE_DAY = 40
SPLIT_ORDER = ["train", "validation", "locked_oos", "pre_registration_holdout"]


def _position_map(calendar: np.ndarray) -> dict[int, int]:
    return {int(date): position for position, date in enumerate(calendar)}


def cell_metrics(
    ledger_cell: pd.DataFrame,
    calendar: np.ndarray,
) -> dict:
    """Summarize one (sector, rule, hold, split) cell of the trade ledger.

    Primary: event-sequence cumulative return, mean/median event return,
    win rate, max drawdown (pseudo-nav over sorted event order), realizable
    rate, stop rate, truncation rate.  Auxiliary: actual holding-day
    distribution, per-holding-day return, and (for R2) second-add rate and
    average invested weight.
    """
    nan_row = {
        "n_signals": 0, "n_realized": 0, "n_censored": 0, "n_untradable": 0,
        "realizable_rate": np.nan, "stop_rate": np.nan, "truncation_rate": np.nan,
        "mean_return": np.nan, "median_return": np.nan, "win_rate": np.nan,
        "cumulative_return": np.nan, "max_drawdown": np.nan,
        "avg_hold_days": np.nan, "hold_days_p25": np.nan,
        "hold_days_p50": np.nan, "hold_days_p75": np.nan,
        "per_day_return": np.nan,
        "r2_add_rate": np.nan, "avg_invested_weight": np.nan,
    }
    if ledger_cell is None or ledger_cell.empty:
        return nan_row
    frame = ledger_cell.copy()
    n_signals = int(len(frame))
    realized = frame[
        frame["status"].isin(REALIZED_STATUSES)
        & frame["net_return"].notna()
    ].sort_values(["event_date", "entry_date"])
    n_realized = int(len(realized))
    row = {
        "n_signals": n_signals,
        "n_realized": n_realized,
        "n_censored": int((frame["status"] == "RIGHT_CENSORED").sum()),
        "n_untradable": int((frame["status"] == "UNTRADABLE").sum()),
        "realizable_rate": n_realized / n_signals if n_signals else np.nan,
        "stop_rate": float((frame["status"] == "STOPPED_OUT").mean())
        if n_signals else np.nan,
        "truncation_rate": float((frame["status"] == "TRUNCATED_EXIT").mean())
        if n_signals else np.nan,
    }
    if n_realized:
        values = realized["net_return"].to_numpy(dtype=float)
        row["mean_return"] = float(np.mean(values))
        row["median_return"] = float(np.median(values))
        row["win_rate"] = float(np.mean(values > 0))
        nav = np.cumprod(1.0 + values)
        peaks = np.maximum.accumulate(np.r_[1.0, nav])
        row["cumulative_return"] = float(nav[-1] - 1.0)
        row["max_drawdown"] = float(np.min(np.r_[1.0, nav] / peaks - 1.0))

        positions = _position_map(calendar)
        hold_days = np.asarray([
            positions.get(int(exit_date), np.nan) - positions.get(int(entry_date), np.nan)
            for exit_date, entry_date in zip(
                realized["exit_date"], realized["entry_date"]
            )
        ], dtype=float)
        hold_days = hold_days[np.isfinite(hold_days) & (hold_days > 0)]
        if len(hold_days):
            row["avg_hold_days"] = float(np.mean(hold_days))
            row["hold_days_p25"] = float(np.percentile(hold_days, 25))
            row["hold_days_p50"] = float(np.percentile(hold_days, 50))
            row["hold_days_p75"] = float(np.percentile(hold_days, 75))
            row["per_day_return"] = float(np.mean(values / hold_days))

        rule_id = str(frame["rule_id"].iloc[0])
        if rule_id == "R2":
            row["r2_add_rate"] = float(
                realized["second_entry_date"].notna().mean()
            )
            row["avg_invested_weight"] = float(
                realized["invested_weight"].to_numpy(dtype=float).mean()
            )
    return row


def hold_day_distribution(
    realized: pd.DataFrame,
    calendar: np.ndarray,
) -> dict:
    """Actual trading-day holding duration quantiles for realized trades."""
    if realized is None or realized.empty:
        return {"n": 0, "mean": np.nan, "p25": np.nan, "p50": np.nan,
                "p75": np.nan, "min": np.nan, "max": np.nan}
    positions = _position_map(calendar)
    hold_days = np.asarray([
        positions.get(int(exit_date), np.nan) - positions.get(int(entry_date), np.nan)
        for exit_date, entry_date in zip(realized["exit_date"], realized["entry_date"])
    ], dtype=float)
    hold_days = hold_days[np.isfinite(hold_days) & (hold_days > 0)]
    if not len(hold_days):
        return {"n": 0, "mean": np.nan, "p25": np.nan, "p50": np.nan,
                "p75": np.nan, "min": np.nan, "max": np.nan}
    return {
        "n": int(len(hold_days)),
        "mean": float(np.mean(hold_days)),
        "p25": float(np.percentile(hold_days, 25)),
        "p50": float(np.percentile(hold_days, 50)),
        "p75": float(np.percentile(hold_days, 75)),
        "min": float(np.min(hold_days)),
        "max": float(np.max(hold_days)),
    }


def bootstrap_stat(
    diffs: np.ndarray,
    seed: int,
    n_boot: int = 5000,
    block_size: int | None = None,
    stat=np.mean,
) -> tuple[float, float, float]:
    """Bootstrap (point, ci_low, ci_high) of ``stat`` over event diffs.

    Block sizes >= n fall back to i.i.d. resampling.  The seed is fixed so
    a re-run is bit-identical; block sizes must be chosen BEFORE any run.
    """
    values = np.asarray(diffs, dtype=float)
    n = len(values)
    if n == 0:
        return np.nan, np.nan, np.nan
    rng = np.random.default_rng(int(seed))
    if block_size is None or block_size <= 1 or block_size >= n:
        index = rng.integers(0, n, size=(n_boot, n))
    else:
        n_blocks = int(np.ceil(n / block_size))
        starts = rng.integers(0, n - block_size + 1, size=(n_boot, n_blocks))
        index = (
            starts[..., None] + np.arange(block_size)
        ).reshape(n_boot, n_blocks * block_size)[:, :n]
    sample = stat(values[index], axis=1)
    return (
        float(np.mean(sample)),
        float(np.percentile(sample, 2.5)),
        float(np.percentile(sample, 97.5)),
    )


def _realized_frame(frame: pd.DataFrame) -> pd.DataFrame:
    return frame[
        frame["status"].isin(REALIZED_STATUSES)
        & frame["net_return"].notna()
    ].sort_values(["event_date", "entry_date"])


def _status_breakdown(frame: pd.DataFrame) -> dict[str, int]:
    return {
        str(status): int(count)
        for status, count in frame["status"].value_counts().items()
    }


def paired_diff_stats(
    base: pd.DataFrame,
    arm: pd.DataFrame,
    seed: int,
    n_boot: int = 5000,
    block_sizes: tuple[int, ...] = (2, 3),
) -> dict:
    """Paired holding-period comparison vs the 20-day baseline.

    Computed on the COMMON support set: events realized in both arms.
    Excluded events are reported per arm with their status breakdown so
    complete-case bias is visible, not hidden.  Bootstrap CIs are
    percentile intervals on the mean and median of the paired diffs.
    """
    base_realized = _realized_frame(base)
    arm_realized = _realized_frame(arm)
    base_ids = set(base_realized["signal_id"])
    arm_ids = set(arm_realized["signal_id"])
    common = sorted(base_ids & arm_ids)
    result = {
        "n_common": len(common),
        "n_only_base": int(len(base_ids - arm_ids)),
        "n_only_arm": int(len(arm_ids - base_ids)),
        "only_base_by_status": _status_breakdown(
            base_realized[~base_realized["signal_id"].isin(common)]
        ),
        "only_arm_by_status": _status_breakdown(
            arm_realized[~arm_realized["signal_id"].isin(common)]
        ),
        "mean_diff": np.nan, "median_diff": np.nan,
        "ci_mean_low": np.nan, "ci_mean_high": np.nan,
        "ci_median_low": np.nan, "ci_median_high": np.nan,
        "block_cis": {},
    }
    if not common:
        return result
    merged = base_realized[base_realized["signal_id"].isin(common)][
        ["signal_id", "net_return"]
    ].merge(
        arm_realized[arm_realized["signal_id"].isin(common)][
            ["signal_id", "net_return"]
        ],
        on="signal_id", suffixes=("_base", "_arm"),
    )
    diffs = (
        merged["net_return_arm"].to_numpy(dtype=float)
        - merged["net_return_base"].to_numpy(dtype=float)
    )
    result["mean_diff"] = float(np.mean(diffs))
    result["median_diff"] = float(np.median(diffs))
    mean_point, lo, hi = bootstrap_stat(diffs, seed, n_boot, stat=np.mean)
    result["ci_mean_low"], result["ci_mean_high"] = lo, hi
    _, lo_med, hi_med = bootstrap_stat(diffs, seed, n_boot, stat=np.median)
    result["ci_median_low"], result["ci_median_high"] = lo_med, hi_med
    for block_size in sorted(set(int(b) for b in block_sizes)):
        _, lo_b, hi_b = bootstrap_stat(
            diffs, seed, n_boot, block_size=block_size, stat=np.mean
        )
        result["block_cis"][block_size] = (lo_b, hi_b)
    return result


def equal_weight_aggregate(rows: list[dict]) -> dict:
    """Equal-weight mean of per-sector paired mean diffs (secondary tier).

    Sectors are averaged equally — a sector with more events must not
    dominate the aggregate.
    """
    values = np.asarray(
        [row["mean_diff"] for row in rows if np.isfinite(row["mean_diff"])],
        dtype=float,
    )
    return {
        "n_sectors": int(len(values)),
        "agg_mean_diff": float(np.mean(values)) if len(values) else np.nan,
        "n_positive": int(np.sum(values > 0)) if len(values) else 0,
    }


def direction_check(per_split_mean_diffs: dict[str, float | None]) -> dict:
    """Mechanical sign consistency of the paired mean diff across splits.

    Only train / validation / locked_oos are consulted: the 2026 holdout is
    diagnostic, never a parameter-selection input.
    """
    signs = {}
    for split in ("train", "validation", "locked_oos"):
        value = per_split_mean_diffs.get(split)
        if value is None or not np.isfinite(value):
            signs[split] = 0
        else:
            signs[split] = int(np.sign(value))
    reference = signs.get("locked_oos", 0)
    if reference == 0:
        consistent = 0
    else:
        consistent = int(sum(s == reference for s in signs.values()))
    return {
        "signs": signs,
        "n_consistent_with_oos": consistent,
        "all_agree": consistent == 3 and reference != 0,
    }


def raw_path_curve(
    event_paths: list[np.ndarray],
    boundary_days: list[int | None],
    max_day: int = MAX_CURVE_DAY,
) -> pd.DataFrame:
    """Mean/median frozen-basket cumulative return by day after entry.

    ``boundary_days`` are RELATIVE day indices (0 = entry day) of the next
    event's entry, matching simulate_rule's truncation exit.  An event
    contributes day k when k is on or before its boundary day and the
    frozen path is fully finite through that day — a NaN gap excludes the
    event entirely, mirroring the RIGHT_CENSORED discipline of the
    backtest.
    """
    rows = []
    for day in range(max_day + 1):
        values = []
        for path, boundary in zip(event_paths, boundary_days):
            path = np.asarray(path, dtype=float)
            if boundary is None:
                limit = len(path) - 1
            else:
                limit = min(int(boundary), len(path) - 1)
            if day > limit or day >= len(path):
                continue
            if not np.isfinite(path[day]):
                continue
            if not np.isfinite(path[1 : limit + 1]).all():
                continue
            values.append(float(path[day]))
        if values:
            rows.append({
                "day": day, "n": len(values), "mean": float(np.mean(values)),
                "median": float(np.median(values)),
                "p25": float(np.percentile(values, 25)),
                "p75": float(np.percentile(values, 75)),
            })
        else:
            rows.append({"day": day, "n": 0, "mean": np.nan, "median": np.nan,
                         "p25": np.nan, "p75": np.nan})
    return pd.DataFrame(rows, columns=["day", "n", "mean", "median", "p25", "p75"])


def strategy_net_curves(
    event_paths: list[np.ndarray],
    exit_positions: list[int | None],
    exit_returns: list[float | None],
    weights: list[float | None] | None = None,
    add_positions: list[int | None] | None = None,
    max_day: int = MAX_CURVE_DAY,
) -> pd.DataFrame:
    """Mean/median realized strategy NAV path; flat at the net exit afterward.

    Positions are RELATIVE day indices (0 = entry day).  The NAV is rebuilt
    from the actual position sizing, mirroring simulate_rule: R0 holds the
    full basket; R2 starts at 50% and adds the second W-leg at
    ``add_positions`` when one fired (value = 0.5*path[k] before the add,
    then 0.5*path[k] + 0.5*((1+path[k])/(1+path[add]) - 1)).  From the exit
    day onward the trade sits flat at its ledger net return (costs
    included).  Unrealized trades are excluded, matching the ledger
    discipline.
    """
    rows = []
    for day in range(max_day + 1):
        values = []
        for path, exit_pos, exit_return, weight, add_pos in zip(
            event_paths, exit_positions, exit_returns,
            weights if weights is not None else [1.0] * len(event_paths),
            add_positions if add_positions is not None
            else [None] * len(event_paths),
        ):
            if exit_pos is None or exit_return is None:
                continue
            path = np.asarray(path, dtype=float)
            if day >= len(path):
                if exit_pos <= len(path) - 1:
                    values.append(float(exit_return))
                continue
            if day >= int(exit_pos):
                values.append(float(exit_return))
                continue
            if not np.isfinite(path[day]):
                continue
            if add_pos is not None:
                # R2 with a fired second leg: leg 1 is always 50% from
                # entry; from the add day on, the second leg is layered in
                # (mirrors simulate_rule exactly).
                add_index = int(add_pos)
                if add_index >= len(path) or not np.isfinite(path[add_index]):
                    continue
                if path[add_index] <= -1.0:
                    continue
                if day < add_index:
                    value = 0.5 * float(path[day])
                else:
                    value = 0.5 * float(path[day]) + 0.5 * (
                        (1.0 + float(path[day]))
                        / (1.0 + float(path[add_index])) - 1.0
                    )
            else:
                # R0 (full weight) or R2 that never fired its second leg.
                value = float(weight if weight is not None else 1.0) * float(path[day])
            values.append(value)
        if values:
            rows.append({
                "day": day, "n": len(values), "mean": float(np.mean(values)),
                "median": float(np.median(values)),
                "p25": float(np.percentile(values, 25)),
                "p75": float(np.percentile(values, 75)),
            })
        else:
            rows.append({"day": day, "n": 0, "mean": np.nan, "median": np.nan,
                         "p25": np.nan, "p75": np.nan})
    return pd.DataFrame(rows, columns=["day", "n", "mean", "median", "p25", "p75"])


def stop_day_counts(
    ledger_cell: pd.DataFrame,
    calendar: np.ndarray,
    max_day: int = MAX_CURVE_DAY,
) -> pd.DataFrame:
    """Histogram of the exit-day (trading days after entry) of stop-outs."""
    frame = ledger_cell[ledger_cell["status"] == "STOPPED_OUT"]
    positions = _position_map(calendar)
    counts = {}
    for exit_date, entry_date in zip(frame["exit_date"], frame["entry_date"]):
        exit_pos = positions.get(int(exit_date))
        entry_pos = positions.get(int(entry_date))
        if exit_pos is None or entry_pos is None:
            continue
        day = exit_pos - entry_pos
        if 1 <= day <= max_day:
            counts[day] = counts.get(day, 0) + 1
    return pd.DataFrame(
        [{"day": day, "n": counts.get(day, 0)} for day in range(1, max_day + 1)],
        columns=["day", "n"],
    )

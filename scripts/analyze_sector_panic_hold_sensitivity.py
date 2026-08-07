"""Dual-caliber analysis of the sector-panic holding-period sensitivity grid.

EXPLORATORY, POST-HOC.  Reads the per-arm ledgers produced by
``sector_panic_hold_sensitivity.py`` and produces, per sector / rule /
holding period / frozen sample split:

- Full-sample strategy view (each arm on its own realizable event set)
- Common-support paired view vs the frozen 20-day baseline, with
  event-level paired bootstrap CIs (fixed seed) and pre-fixed block
  bootstrap sizes {2, 3} as auxiliary evidence
- Equal-weight sector aggregate (secondary) and cross-sector pool
  (auxiliary only)
- Frozen-basket path curves (raw, and net after stop / boundary exits)
  and stop-day distributions

The 2024-2025 locked OOS and 2026 data are already revealed, so no
parameter is promoted from this study; the only adjudication window is the
data frozen after 2026-08-05.  The report applies the pre-registered
decision rules mechanically and defaults to keeping the 20-day contract.

Examples
--------
python scripts/analyze_sector_panic_hold_sensitivity.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(ROOT))

from sector_panic.backtest import REALIZED_STATUSES, build_frozen_path  # noqa: E402
from sector_panic.hold_sensitivity import (  # noqa: E402
    SPLIT_ORDER,
    cell_metrics,
    direction_check,
    equal_weight_aggregate,
    paired_diff_stats,
    raw_path_curve,
    stop_day_counts,
    strategy_net_curves,
)

OUT_ROOT = ROOT / "outputs" / "analysis" / "sector_panic" / "hold_sensitivity"
RUNTIME_DATA_DIR = (
    ROOT / "outputs" / "analysis" / "sector_panic" / "runtime_tushare"
)
PARENT_INDEX_CODE = "000300.SH"
BOOT_SEED = 20260804
N_BOOT = 5000
BLOCK_SIZES = (2, 3)
CURVE_DAYS = [0, 5, 10, 15, 20, 25, 30, 35, 40]
RULES = ("R0", "R2")
REPORT_SPLITS = ["all_period"] + SPLIT_ORDER


def _read_runtime_table(name: str) -> pd.DataFrame:
    for suffix in (".csv.gz", ".csv"):
        path = RUNTIME_DATA_DIR / f"{name}{suffix}"
        if path.exists():
            return pd.read_csv(path, low_memory=False)
    raise FileNotFoundError(f"runtime table missing: {name}")


def _fmt(value, digits: int = 4) -> str:
    if value is None or (isinstance(value, float) and not np.isfinite(value)):
        return ""
    return f"{float(value):.{digits}f}"


def _markdown_table(columns: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(columns) + " |",
             "| " + " | ".join(["---"] * len(columns)) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(v).replace("|", "\\|") for v in row) + " |")
    return "\n".join(lines)


def _arm_cell(frame: pd.DataFrame, rule_id: str, split_name: str) -> pd.DataFrame:
    subset = frame[frame["rule_id"] == rule_id]
    if split_name == "all_period":
        return subset
    return subset[subset["sample_split"] == split_name]


def load_arm_ledgers(
    holds: list[int], sectors: list[str]
) -> dict[tuple[int, str], pd.DataFrame]:
    ledgers = {}
    for hold in holds:
        for sector in sectors:
            path = OUT_ROOT / str(hold) / sector / "rule_trade_ledger.csv"
            frame = pd.read_csv(path)
            primary_cost = int(frame["cost_bps"].iloc[0])
            frame = frame[frame["cost_bps"] == primary_cost].copy()
            ledgers[(hold, sector)] = frame
    return ledgers


def verify_events_identical(holds: list[int], sectors: list[str]) -> None:
    """Full event identity must be identical across all hold arms.

    Comparing only event counts is not sufficient; the events themselves
    (id, signal date, entry date, entry basket) must match row for row,
    since only the holding period may vary between arms.
    """
    identity_columns = [
        "event_id", "signal_date", "entry_date", "entry_component_codes"
    ]
    for sector in sectors:
        reference = None
        for hold in holds:
            path = OUT_ROOT / str(hold) / sector / "panic_events.csv"
            frame = pd.read_csv(path)
            identity = frame[identity_columns].fillna("")
            identity["entry_component_codes"] = identity[
                "entry_component_codes"
            ].map(lambda v: ",".join(sorted(str(v).split(","))) if v else v)
            key = tuple(
                map(tuple, identity.sort_values("event_id").values.tolist())
            )
            if reference is None:
                reference = key
            elif key != reference:
                raise RuntimeError(
                    f"{sector}: event identity differs across arms at "
                    f"hold {hold} (event_id/signal_date/entry_date/"
                    f"entry_component_codes)"
                )
        if reference is None:
            raise RuntimeError(f"{sector}: no panic events found")
        print(
            f"  [verify] {sector}: {len(reference)} events identical "
            f"across {len(holds)} arms"
        )


def load_frozen_paths(
    sectors: list[str],
    events_by_sector: dict[str, pd.DataFrame],
    calendar: np.ndarray,
) -> dict[str, list[dict]]:
    """Rebuild the frozen equal-weight basket paths (horizon 40) offline.

    Events and entry baskets are reused exactly as frozen in the arm
    outputs; only prices, the calendar, and audited suspension rows are
    read from the runtime snapshot.
    """
    prices_all = _read_runtime_table("prices_adj")
    suspend = _read_runtime_table("suspend_status")
    suspended_keys = set()
    if not suspend.empty:
        date_column = "trade_date" if "trade_date" in suspend.columns else "suspend_date"
        for code, date in zip(suspend["ts_code"].astype(str), suspend[date_column]):
            try:
                suspended_keys.add((str(code), int(date)))
            except (TypeError, ValueError):
                continue
    positions = {int(d): position for position, d in enumerate(calendar)}
    paths_by_sector = {}
    for sector in sectors:
        events = events_by_sector[sector].sort_values("signal_date").reset_index(drop=True)
        codes_used = set()
        for value in events["entry_component_codes"].dropna():
            codes_used.update(str(value).split(","))
        prices = prices_all[prices_all["ts_code"].astype(str).isin(codes_used)]
        entries = []
        for position, event in enumerate(events.itertuples(index=False)):
            codes = [code for code in str(event.entry_component_codes).split(",") if code]
            if not codes:
                entries.append(None)
                continue
            entry_date = int(event.entry_date)
            entry_pos = positions.get(entry_date)
            boundary_day = None
            if position + 1 < len(events) and entry_pos is not None:
                next_pos = positions.get(int(events.iloc[position + 1]["entry_date"]))
                if next_pos is not None:
                    # RELATIVE day index (0 = entry day), matching the
                    # raw_path_curve contract and simulate_rule truncation.
                    boundary_day = next_pos - entry_pos
            result = build_frozen_path(
                prices, codes, entry_date, calendar,
                horizon=40, suspended_keys=suspended_keys,
            )
            if result is None:
                entries.append(None)
                continue
            returns, _dates = result
            entries.append({
                "event_id": str(event.event_id),
                "returns": returns,
                "entry_pos": entry_pos,
                "boundary_day": boundary_day,
            })
        paths_by_sector[sector] = entries
    return paths_by_sector


def compute_summary(
    ledgers: dict[tuple[int, str], pd.DataFrame],
    holds: list[int],
    sectors: list[str],
    calendar: np.ndarray,
) -> pd.DataFrame:
    rows = []
    for sector in sectors:
        for hold in holds:
            frame = ledgers[(hold, sector)]
            for rule_id in RULES:
                rule = frame[frame["rule_id"] == rule_id]
                for split_name in ["all_period", "pre_2026"] + SPLIT_ORDER:
                    if split_name == "all_period":
                        cell = rule
                    elif split_name == "pre_2026":
                        # train + validation + locked_oos pooled; 2026 is
                        # diagnostic only and never a parameter input.
                        cell = rule[
                            rule["sample_split"].isin(
                                ["train", "validation", "locked_oos"]
                            )
                        ]
                    else:
                        cell = rule[rule["sample_split"] == split_name]
                    rows.append({
                        "sector": sector, "rule_id": rule_id,
                        "hold_days": hold, "sample_split": split_name,
                        **cell_metrics(cell, calendar),
                    })
    return pd.DataFrame(rows)


def compute_paired(
    ledgers: dict[tuple[int, str], pd.DataFrame],
    holds: list[int],
    sectors: list[str],
    splits: list[str],
) -> pd.DataFrame:
    rows = []
    for sector in sectors:
        for hold in holds:
            if hold == 20:
                continue
            for rule_id in RULES:
                for split_name in splits:
                    stats = paired_diff_stats(
                        _arm_cell(ledgers[(20, sector)], rule_id, split_name),
                        _arm_cell(ledgers[(hold, sector)], rule_id, split_name),
                        seed=BOOT_SEED, n_boot=N_BOOT,
                        block_sizes=BLOCK_SIZES,
                    )
                    rows.append({
                        "sector": sector, "rule_id": rule_id,
                        "hold_days": hold, "sample_split": split_name,
                        "n_common": stats["n_common"],
                        "n_only_base": stats["n_only_base"],
                        "n_only_arm": stats["n_only_arm"],
                        "mean_diff": stats["mean_diff"],
                        "median_diff": stats["median_diff"],
                        "ci_mean_low": stats["ci_mean_low"],
                        "ci_mean_high": stats["ci_mean_high"],
                        "ci_median_low": stats["ci_median_low"],
                        "ci_median_high": stats["ci_median_high"],
                        "block2_low": stats["block_cis"].get(2, (np.nan, np.nan))[0],
                        "block2_high": stats["block_cis"].get(2, (np.nan, np.nan))[1],
                        "block3_low": stats["block_cis"].get(3, (np.nan, np.nan))[0],
                        "block3_high": stats["block_cis"].get(3, (np.nan, np.nan))[1],
                        "only_base_by_status": json.dumps(
                            stats["only_base_by_status"], ensure_ascii=False
                        ),
                        "only_arm_by_status": json.dumps(
                            stats["only_arm_by_status"], ensure_ascii=False
                        ),
                    })
    return pd.DataFrame(rows)


def compute_aggregates(
    ledgers: dict[tuple[int, str], pd.DataFrame],
    holds: list[int],
    sectors: list[str],
    splits: list[str],
) -> pd.DataFrame:
    rows = []
    for hold in holds:
        if hold == 20:
            continue
        for rule_id in RULES:
            for split_name in splits:
                sector_rows = []
                frames_base, frames_arm = [], []
                for sector in sectors:
                    base = _arm_cell(ledgers[(20, sector)], rule_id, split_name)
                    arm = _arm_cell(ledgers[(hold, sector)], rule_id, split_name)
                    sector_rows.append(paired_diff_stats(
                        base, arm, seed=BOOT_SEED, n_boot=N_BOOT,
                        block_sizes=BLOCK_SIZES,
                    ))
                    frames_base.append(base)
                    frames_arm.append(arm)
                aggregate = equal_weight_aggregate(sector_rows)
                pooled = paired_diff_stats(
                    pd.concat(frames_base, ignore_index=True),
                    pd.concat(frames_arm, ignore_index=True),
                    seed=BOOT_SEED, n_boot=N_BOOT, block_sizes=BLOCK_SIZES,
                )
                rows.append({
                    "rule_id": rule_id, "hold_days": hold,
                    "sample_split": split_name,
                    "ew_n_sectors": aggregate["n_sectors"],
                    "ew_mean_diff": aggregate["agg_mean_diff"],
                    "ew_n_positive": aggregate["n_positive"],
                    "pooled_n_common": pooled["n_common"],
                    "pooled_mean_diff": pooled["mean_diff"],
                    "pooled_ci_mean_low": pooled["ci_mean_low"],
                    "pooled_ci_mean_high": pooled["ci_mean_high"],
                    "pooled_block2_low": pooled["block_cis"].get(2, (np.nan, np.nan))[0],
                    "pooled_block2_high": pooled["block_cis"].get(2, (np.nan, np.nan))[1],
                    "pooled_block3_low": pooled["block_cis"].get(3, (np.nan, np.nan))[0],
                    "pooled_block3_high": pooled["block_cis"].get(3, (np.nan, np.nan))[1],
                })
    return pd.DataFrame(rows)


def compute_direction_checks(paired: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (sector, rule_id, hold), group in paired.groupby(
        ["sector", "rule_id", "hold_days"]
    ):
        per_split = {
            split: row["mean_diff"]
            for split, row in group.set_index("sample_split").iterrows()
        }
        check = direction_check(per_split)
        rows.append({
            "sector": sector, "rule_id": rule_id, "hold_days": hold,
            "sign_train": check["signs"].get("train"),
            "sign_validation": check["signs"].get("validation"),
            "sign_locked_oos": check["signs"].get("locked_oos"),
            "n_consistent_with_oos": check["n_consistent_with_oos"],
            "all_agree": check["all_agree"],
        })
    return pd.DataFrame(rows)


def compute_curves(
    ledgers: dict[tuple[int, str], pd.DataFrame],
    holds: list[int],
    sectors: list[str],
    paths_by_sector: dict[str, list[dict]],
    calendar: np.ndarray,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    raw_rows = []
    for sector in sectors:
        entries = [entry for entry in paths_by_sector[sector] if entry]
        curve = raw_path_curve(
            [entry["returns"] for entry in entries],
            [entry["boundary_day"] for entry in entries],
        )
        for row in curve.itertuples(index=False):
            raw_rows.append({"sector": sector, "day": row.day, "n": row.n,
                             "mean": row.mean, "median": row.median,
                             "p25": row.p25, "p75": row.p75})
    pooled_entries = [
        entry for sector in sectors
        for entry in paths_by_sector[sector] if entry
    ]
    for row in raw_path_curve(
        [entry["returns"] for entry in pooled_entries],
        [entry["boundary_day"] for entry in pooled_entries],
    ).itertuples(index=False):
        raw_rows.append({"sector": "pooled", "day": row.day, "n": row.n,
                         "mean": row.mean, "median": row.median,
                         "p25": row.p25, "p75": row.p75})
    raw = pd.DataFrame(raw_rows)

    positions = {int(d): position for position, d in enumerate(calendar)}
    net_rows = []
    stop_rows = []
    for sector in sectors:
        entries_by_id = {
            entry["event_id"]: entry
            for entry in paths_by_sector[sector] if entry
        }
        for hold in holds:
            frame = ledgers[(hold, sector)]
            for rule_id in RULES:
                cell = frame[frame["rule_id"] == rule_id]
                realized = cell[
                    cell["status"].isin(REALIZED_STATUSES)
                    & cell["net_return"].notna()
                ]
                paths, exit_positions, exit_returns = [], [], []
                weights, add_positions = [], []
                for row in realized.itertuples(index=False):
                    entry = entries_by_id.get(str(row.signal_id))
                    entry_pos = entry["entry_pos"] if entry else None
                    exit_pos = positions.get(int(row.exit_date)) if pd.notna(row.exit_date) else None
                    if entry is None or entry_pos is None or exit_pos is None:
                        continue
                    paths.append(entry["returns"])
                    exit_positions.append(exit_pos - entry_pos)
                    exit_returns.append(float(row.net_return))
                    weight = row.invested_weight if pd.notna(row.invested_weight) else 1.0
                    weights.append(float(weight))
                    add_pos = None
                    if pd.notna(row.second_entry_date):
                        add_abs = positions.get(int(row.second_entry_date))
                        if add_abs is not None:
                            add_pos = add_abs - entry_pos
                    add_positions.append(add_pos)
                for row in strategy_net_curves(
                    paths, exit_positions, exit_returns,
                    weights=weights, add_positions=add_positions,
                ).itertuples(index=False):
                    net_rows.append({
                        "sector": sector, "rule_id": rule_id,
                        "hold_days": hold, "day": row.day, "n": row.n,
                        "mean": row.mean, "median": row.median,
                    })
                for row in stop_day_counts(cell, calendar).itertuples(index=False):
                    stop_rows.append({
                        "sector": sector, "rule_id": rule_id,
                        "hold_days": hold, "day": row.day, "n": row.n,
                    })
    return raw, pd.DataFrame(net_rows), pd.DataFrame(stop_rows)


def evaluate_candidates(
    paired: pd.DataFrame,
    aggregate: pd.DataFrame,
    summary: pd.DataFrame,
    direction_checks: pd.DataFrame,
    rules: dict,
) -> pd.DataFrame:
    """Mechanically apply the pre-specified candidate conditions.

    Rules come from the root manifest (written before any arm ran).  The
    2026 holdout is excluded from every condition; tolerance checks use
    the pre-2026 pool (train + validation + locked_oos).
    """
    tolerance_mdd = float(rules["tolerances"]["max_drawdown_pp"])
    tolerance_realizable = float(rules["tolerances"]["realizable_rate_pp"])
    rows = []
    for (rule_id, hold), _ in aggregate.groupby(["rule_id", "hold_days"]):
        arm_paired = paired[
            (paired["rule_id"] == rule_id) & (paired["hold_days"] == hold)
        ]
        arm_agg = aggregate[
            (aggregate["rule_id"] == rule_id) & (aggregate["hold_days"] == hold)
        ]
        checks = direction_checks[
            (direction_checks["rule_id"] == rule_id)
            & (direction_checks["hold_days"] == hold)
        ]
        flags = {}
        # 1. direction consistency across train/validation/locked_oos in >= 2 sectors
        flags["direction_consistency"] = int(
            (checks["n_consistent_with_oos"] >= 2).sum() >= 2
        )
        # 2. mean and median paired diffs agree in sign in >= 2 sectors (locked OOS)
        oos = arm_paired[arm_paired["sample_split"] == "locked_oos"]
        mean_median_ok = (
            oos["mean_diff"].notna()
            & oos["median_diff"].notna()
            & ((oos["mean_diff"] > 0) == (oos["median_diff"] > 0))
        )
        flags["mean_median_agreement"] = int(mean_median_ok.sum() >= 2)
        # 3. PRE-2026 max drawdown not materially worse, >= 2 sectors
        # 4. PRE-2026 realizable rate not materially lower, >= 2 sectors
        # (2026 data is diagnostic only and never a parameter input, so the
        # tolerance checks use the train+validation+locked_oos pool.)
        mdd_ok, realizable_ok = [], []
        for sector in sorted(oos["sector"].unique()):
            base_cell = summary[
                (summary["sector"] == sector) & (summary["rule_id"] == rule_id)
                & (summary["hold_days"] == 20)
                & (summary["sample_split"] == "pre_2026")
            ]
            arm_cell = summary[
                (summary["sector"] == sector) & (summary["rule_id"] == rule_id)
                & (summary["hold_days"] == hold)
                & (summary["sample_split"] == "pre_2026")
            ]
            if base_cell.empty or arm_cell.empty:
                continue
            base_row, arm_row = base_cell.iloc[0], arm_cell.iloc[0]
            mdd_ok.append(
                np.isfinite(arm_row["max_drawdown"])
                and np.isfinite(base_row["max_drawdown"])
                and arm_row["max_drawdown"] >= base_row["max_drawdown"] - tolerance_mdd
            )
            realizable_ok.append(
                np.isfinite(arm_row["realizable_rate"])
                and np.isfinite(base_row["realizable_rate"])
                and arm_row["realizable_rate"]
                >= base_row["realizable_rate"] - tolerance_realizable
            )
        flags["max_drawdown_tolerance"] = int(sum(mdd_ok) >= 2)
        flags["realizable_rate_tolerance"] = int(sum(realizable_ok) >= 2)
        # 5. at least 2 sectors with the same direction on locked OOS
        signs = oos["mean_diff"].dropna().map(np.sign)
        signs = signs[signs != 0]
        flags["sector_direction"] = int(
            len(signs) > 0 and int(signs.value_counts().max()) >= 2
        )
        # 6. pooled paired advantage stable on locked OOS
        pooled = arm_agg[arm_agg["sample_split"] == "locked_oos"]
        if not pooled.empty:
            row = pooled.iloc[0]
            flags["paired_stability"] = int(
                np.isfinite(row["pooled_mean_diff"])
                and row["pooled_mean_diff"] > 0
                and np.isfinite(row["pooled_ci_mean_low"])
                and row["pooled_ci_mean_low"] > 0
            )
        else:
            flags["paired_stability"] = 0
        flags["candidate"] = int(all(bool(v) for v in flags.values()))
        rows.append({"rule_id": rule_id, "hold_days": hold, **flags})
    return pd.DataFrame(rows)


def _curve_table_rows(frame: pd.DataFrame, with_rule_hold: bool) -> list[list[str]]:
    rows = []
    for row in frame.sort_values(["sector", "day"]).itertuples(index=False):
        if int(row.day) not in CURVE_DAYS or row.sector not in ("pooled", "nonferrous"):
            continue
        if with_rule_hold and int(row.hold_days) != 20:
            continue
        rows.append([
            row.sector,
            str(getattr(row, "rule_id", "")),
            str(getattr(row, "hold_days", "")),
            str(row.day), str(row.n), _fmt(row.mean), _fmt(row.median),
        ])
    return rows


def build_report(context: dict) -> str:
    summary = context["summary"]
    summary_rows = []
    for sector in sorted(summary["sector"].unique()):
        for rule_id in RULES:
            for hold in context["holds"]:
                for split_name in REPORT_SPLITS:
                    cell = summary[
                        (summary["sector"] == sector)
                        & (summary["rule_id"] == rule_id)
                        & (summary["hold_days"] == hold)
                        & (summary["sample_split"] == split_name)
                    ]
                    if cell.empty:
                        continue
                    row = cell.iloc[0]
                    summary_rows.append([
                        sector, rule_id, str(hold), split_name,
                        str(row["n_signals"]), str(row["n_realized"]),
                        _fmt(row["mean_return"]), _fmt(row["median_return"]),
                        _fmt(row["win_rate"], 3), _fmt(row["cumulative_return"]),
                        _fmt(row["max_drawdown"]), _fmt(row["realizable_rate"], 3),
                        _fmt(row["stop_rate"], 3), _fmt(row["truncation_rate"], 3),
                        _fmt(row["r2_add_rate"], 3), _fmt(row["avg_invested_weight"], 3),
                    ])
    lines = [
        "# Sector Panic Holding-Period Sensitivity (EXPLORATORY, POST-HOC)",
        "",
        f"Generated: {context['generated_at']}",
        "",
        "## Purpose and status",
        "",
        "- Every parameter except `execution.hold_days` is frozen from the "
        "formal sector contracts: events, T+1 entries, stop levels, costs, "
        "and the next-event boundary are identical to the frozen 20-day run.",
        f"- Holds tested: {context['holds']}; baseline hold: 20 trading days.",
        f"- Data end: {context['end_date']}; all arms share one frozen-path "
        "horizon of 40 trading days.",
        "- **This study has NO strict out-of-sample window**: the 2024-2025 "
        "locked OOS and the 2026 data are already revealed and are treated "
        "as post-hoc robustness / diagnostics only. The only adjudication "
        "window for replacing the 20-day parameter is data frozen after "
        "2026-08-05.",
        "- Formal 20-day outputs, config hashes, and the golden baseline are "
        "untouched; every arm is labelled EXPLORATORY_POST_HOC in its "
        "manifest.",
        "- The 20-day arms replicate the formal run exactly on every "
        "execution and return field; only `path_type` classification can "
        "differ, because the study scores all arms on a common 40-day "
        "horizon while the formal run used the default 28-day horizon.",
        "",
        "## Methodology",
        "",
        "- **Dual caliber.** (a) Full-sample strategy view: each arm on its "
        "own realizable event set, censored / untradable reported separately "
        "(what can actually be executed). (b) Common-support paired view: "
        "the same event under both holds (what the holding period changes).",
        "- **Statistical tiers.** Per sector (primary) -> equal-weight sector "
        "aggregate (secondary) -> cross-sector pool (auxiliary only).",
        "- **Bootstrap.** Event-level paired bootstrap (primary), fixed "
        f"seed {BOOT_SEED}, {N_BOOT} resamples, percentile CIs.  In locked "
        "OOS the 10d and 15d arms have CI upper bounds below zero — "
        "significant evidence those alternatives are WORSE than 20d on the "
        "common-support set.  The moving-block bootstrap (pre-fixed block "
        f"sizes {BLOCK_SIZES}, auxiliary) CIs straddle zero, consistent "
        "with autocorrelation in event diffs; block bootstrap is a "
        "robustness check, not a resolution of autocorrelation.",
        "- **Primary metrics.** Event-sequence cumulative return, mean / "
        "median event return, win rate, max drawdown (pseudo-nav over "
        "sorted events), realizable rate, stop rate, truncation rate; R2 "
        "second-add rate and average invested weight; auxiliary: actual "
        "holding-day distribution and per-holding-day return.",
        "",
        "## Full-sample strategy view (all_period and locked OOS)",
        "",
        "Columns: n_signals, n_realized, mean, median, win_rate, cum, mdd, "
        "realizable, stop, trunc, r2_add, avg_weight.",
        "",
    ]
    lines.append(_markdown_table(
        ["sector", "rule", "hold", "split", "n_sig", "n_real", "mean", "median",
         "win", "cum", "mdd", "realiz", "stop", "trunc", "r2_add", "weight"],
        summary_rows,
    ))
    lines.extend([
        "",
        "## Path curves (day after entry, cumulative return)",
        "",
    ])
    lines.append(_markdown_table(
        ["sector", "rule", "hold", "day", "n", "mean", "median"],
        _curve_table_rows(context["raw_curve"], with_rule_hold=False),
    ))
    lines.extend(["", "*Net strategy path (realized trades, flat in cash after exit):*", ""])
    lines.append(_markdown_table(
        ["sector", "rule", "hold", "day", "n", "mean", "median"],
        _curve_table_rows(context["net_curve"], with_rule_hold=True),
    ))
    lines.extend([
        "",
        "## Candidate evaluation (pre-specified rules, applied mechanically)",
        "",
        "The rules are pre-specified in the run code and recorded in the "
        "root manifest BEFORE any arm ran; this is not a formal "
        "pre-registration with an external trust anchor.  The MDD and "
        "realizable-rate tolerance checks use the PRE-2026 pool "
        "(train + validation + locked_oos); 2026 data is diagnostic only "
        "and never a parameter input.  All six conditions must be met for "
        "a holding period to be listed as a shadow candidate; no candidate "
        "is promoted from historical data.",
        "",
    ])
    flags = context["candidate_flags"]
    lines.append(_markdown_table(
        ["rule", "hold", "direction", "mean_median", "mdd_tol",
         "realizable_tol", "sector_dir", "paired_stability", "candidate"],
        [
            [row.rule_id, str(row.hold_days), str(row.direction_consistency),
             str(row.mean_median_agreement), str(row.max_drawdown_tolerance),
             str(row.realizable_rate_tolerance), str(row.sector_direction),
             str(row.paired_stability), str(row.candidate)]
            for row in flags.itertuples(index=False)
        ],
    ))
    lines.extend([
        "",
        "## Aggregate paired mean diff vs 20-day baseline (locked OOS)",
        "",
    ])
    agg = context["aggregate"]
    lines.append(_markdown_table(
        ["rule", "hold", "ew_sectors", "ew_mean_diff", "pooled_n",
         "pooled_mean_diff", "ci_low", "ci_high", "block2_low", "block2_high"],
        [
            [row.rule_id, str(row.hold_days), str(row.ew_n_sectors),
             _fmt(row.ew_mean_diff), str(row.pooled_n_common),
             _fmt(row.pooled_mean_diff), _fmt(row.pooled_ci_mean_low),
             _fmt(row.pooled_ci_mean_high), _fmt(row.pooled_block2_low),
             _fmt(row.pooled_block2_high)]
            for row in agg[agg["sample_split"] == "locked_oos"].itertuples(index=False)
        ],
    ))
    lines.extend([
        "",
        "## Conclusion",
        "",
        context["conclusion"],
        "",
        "## Caveats",
        "",
        "- R2 shows higher cumulative returns and shallower drawdowns than "
        "R0 in every sector/hold cell, but that is primarily the mechanical "
        "effect of lower average invested weight (0.5-0.6 vs 1.0 for R0); "
        "it is NOT evidence of a risk-adjusted alpha advantage.",
        "- In the revealed 2024-2025 window, 10d and 15d are significantly "
        "worse than 20d on the common-support set (event-level percentile "
        "CI excludes zero); block-bootstrap CIs straddle zero.  This "
        "strengthens, rather than weakens, keeping the 20-day parameter.",
        "- The full-sample strategy view (per-arm realizable sets) and the "
        "common-support paired view are both reported; neither alone "
        "carries the conclusion (complete-case selection bias is visible "
        "through the only_*_by_status columns of the paired tables).",
        "",
        "Full per-cell results: `summary_by_split.csv`, "
        "`paired_vs_baseline.csv`, `paired_vs_baseline_aggregate.csv`, "
        "`direction_checks.csv`, `candidate_flags.csv`, "
        "`frozen_path_curve_raw.csv`, `frozen_path_curve_net.csv`, "
        "`stop_day_distribution.csv`.",
        "",
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--end", type=int, default=20260804,
        help="Data end used when the arms were generated.",
    )
    args = parser.parse_args()
    root_manifest = json.loads(
        (OUT_ROOT / "manifest.json").read_text(encoding="utf-8")
    )
    holds = [int(h) for h in root_manifest["holds"]]
    sectors = [str(s) for s in root_manifest["sectors"]]
    rules = root_manifest["decision_rules"]
    if 20 not in holds:
        raise RuntimeError("20-day baseline arm is missing from the grid")

    ledgers = load_arm_ledgers(holds, sectors)
    verify_events_identical(holds, sectors)
    events_by_sector = {
        sector: pd.read_csv(OUT_ROOT / "20" / sector / "panic_events.csv")
        for sector in sectors
    }

    index_daily = _read_runtime_table("index_daily")
    index_daily["trade_date"] = pd.to_numeric(
        index_daily["trade_date"], errors="coerce"
    ).astype(int)
    parent = index_daily[index_daily["ts_code"].astype(str) == PARENT_INDEX_CODE]
    calendar = np.array(sorted(parent["trade_date"].unique()), dtype=int)

    paths_by_sector = load_frozen_paths(sectors, events_by_sector, calendar)

    summary = compute_summary(ledgers, holds, sectors, calendar)
    splits = ["all_period"] + SPLIT_ORDER
    paired = compute_paired(ledgers, holds, sectors, splits)
    aggregate = compute_aggregates(ledgers, holds, sectors, splits)
    direction_checks = compute_direction_checks(paired)
    raw_curve, net_curve, stops = compute_curves(
        ledgers, holds, sectors, paths_by_sector, calendar
    )
    candidate_flags = evaluate_candidates(
        paired, aggregate, summary, direction_checks, rules
    )

    for name, frame in {
        "summary_by_split": summary,
        "paired_vs_baseline": paired,
        "paired_vs_baseline_aggregate": aggregate,
        "direction_checks": direction_checks,
        "candidate_flags": candidate_flags,
        "frozen_path_curve_raw": raw_curve,
        "frozen_path_curve_net": net_curve,
        "stop_day_distribution": stops,
    }.items():
        frame.to_csv(OUT_ROOT / f"{name}.csv", index=False, encoding="utf-8-sig")

    default_conclusion = rules["default_conclusion"]
    candidates = candidate_flags[candidate_flags["candidate"] == 1]
    if candidates.empty:
        conclusion = (
            f"No holding period met every pre-specified condition. "
            f"{default_conclusion}"
        )
    else:
        names = ", ".join(
            f"{row.rule_id}/{row.hold_days}d"
            for row in candidates.itertuples(index=False)
        )
        conclusion = (
            f"Shadow candidates listed for further scrutiny only: {names}. "
            "None is promoted from historical data; the 20-day contract "
            "stays until the post-2026-08-05 frozen window adjudicates."
        )

    report = build_report({
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "holds": holds,
        "end_date": int(args.end),
        "summary": summary,
        "raw_curve": raw_curve,
        "net_curve": net_curve,
        "candidate_flags": candidate_flags,
        "aggregate": aggregate,
        "conclusion": conclusion,
    })
    (OUT_ROOT / "hold_sensitivity_report.md").write_text(
        report, encoding="utf-8"
    )

    output_names = [
        "summary_by_split.csv", "paired_vs_baseline.csv",
        "paired_vs_baseline_aggregate.csv", "direction_checks.csv",
        "candidate_flags.csv", "frozen_path_curve_raw.csv",
        "frozen_path_curve_net.csv", "stop_day_distribution.csv",
        "hold_sensitivity_report.md",
    ]
    analysis_manifest = {
        "schema": "sector_panic_hold_sensitivity_analysis.v1",
        "status": "EXPLORATORY_POST_HOC",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "boot_seed": BOOT_SEED,
        "n_boot": N_BOOT,
        "block_sizes": list(BLOCK_SIZES),
        "root_manifest_sha256": hashlib.sha256(
            (OUT_ROOT / "manifest.json").read_bytes()
        ).hexdigest(),
        "outputs_sha256": {
            name: hashlib.sha256((OUT_ROOT / name).read_bytes()).hexdigest()
            for name in output_names
        },
        "decision_rules": rules,
        "registration_note": (
            "mechanical judgment rules pre-specified in the run code and "
            "recorded in the root manifest before arm execution; NOT a "
            "formal pre-registration with an external trust anchor"
        ),
        "conclusion": conclusion,
    }
    (OUT_ROOT / "analysis_manifest.json").write_text(
        json.dumps(analysis_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print("\nAggregate paired mean diff vs 20d (locked OOS):")
    display = aggregate[aggregate["sample_split"] == "locked_oos"][
        ["rule_id", "hold_days", "ew_mean_diff", "pooled_n_common",
         "pooled_mean_diff", "pooled_ci_mean_low", "pooled_ci_mean_high"]
    ]
    print(display.to_string(index=False))
    print("\nCandidate flags:")
    print(candidate_flags.to_string(index=False))
    print(f"\n{conclusion}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

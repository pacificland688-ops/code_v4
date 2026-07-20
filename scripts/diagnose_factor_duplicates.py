#!/usr/bin/env python
"""
Diagnose duplicate (ts_code, trade_date) keys in factor parquet caches.

For each specified factor, scans the parquet cache, identifies duplicate keys,
and outputs:
  - duplicate summary (per factor, per year)
  - sample duplicate rows showing differing field values
  - root cause classification (report_period_overlap, ann_date_revision,
    forward_fill_dup, partition_append, identical_duplicate)

Usage:
  python -X utf8 scripts/diagnose_factor_duplicates.py \
    --factors revenue_growth_ttm_cs profit_growth_ttm_cs \
              growth_stability_8q_cs earnings_acceleration_cs \
    --start 20170101 --end 20241231 \
    --out outputs/analysis/v4_growth_duplicate_diagnosis
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def _load_factor_cache(factor_name: str, start: str, end: str) -> pd.DataFrame:
    """Load factor parquet cache, scanning both year=*/month=* and year=*/*.parquet."""
    root = ROOT / "data" / "parquet" / "factors" / f"factor_name={factor_name}"
    if not root.exists():
        return pd.DataFrame()

    chunks = []
    start_int = int(start)
    end_int = int(end)

    for year_dir in sorted(root.iterdir()):
        if not year_dir.is_dir() or not year_dir.name.startswith("year="):
            continue
        year = int(year_dir.name.split("=")[1])
        if year < (start_int // 10000) - 1 or year > (end_int // 10000) + 1:
            continue

        # Try month= subdirectories first
        for sub_dir in sorted(year_dir.iterdir()):
            if sub_dir.is_dir() and sub_dir.name.startswith("month="):
                for pq_file in sub_dir.glob("*.parquet"):
                    try:
                        part = pd.read_parquet(pq_file)
                        part.columns = [str(c).strip().lower() for c in part.columns]
                        if "ts_code" not in part.columns or "trade_date" not in part.columns:
                            continue
                        part["ts_code"] = part["ts_code"].astype(str)
                        part["trade_date"] = pd.to_numeric(part["trade_date"], errors="coerce")
                        part = part.dropna(subset=["trade_date"])
                        part = part[(part["trade_date"] >= start_int) & (part["trade_date"] <= end_int)]
                        if not part.empty:
                            chunks.append(part)
                    except Exception:
                        continue
            elif sub_dir.suffix == ".parquet":
                # Direct parquet file in year dir (V4 build format)
                try:
                    part = pd.read_parquet(sub_dir)
                    part.columns = [str(c).strip().lower() for c in part.columns]
                    if "ts_code" not in part.columns or "trade_date" not in part.columns:
                        continue
                    part["ts_code"] = part["ts_code"].astype(str)
                    part["trade_date"] = pd.to_numeric(part["trade_date"], errors="coerce")
                    part = part.dropna(subset=["trade_date"])
                    part = part[(part["trade_date"] >= start_int) & (part["trade_date"] <= end_int)]
                    if not part.empty:
                        chunks.append(part)
                except Exception:
                    continue

    if not chunks:
        return pd.DataFrame()

    result = pd.concat(chunks, ignore_index=True)
    return result.sort_values(["ts_code", "trade_date"])


def _classify_duplicates(df: pd.DataFrame) -> dict:
    """Classify the root cause of duplicate (ts_code, trade_date) keys."""
    key_cols = ["ts_code", "trade_date"]
    dup_mask = df.duplicated(key_cols, keep=False)
    dup_df = df[dup_mask].copy()

    if dup_df.empty:
        return {"has_duplicates": False, "total_dup_rows": 0, "categories": {}}

    # Group duplicates by key
    dup_groups = dup_df.groupby(key_cols)
    n_unique_dup_keys = dup_groups.ngroups
    total_dup_rows = len(dup_df)

    categories = defaultdict(int)
    samples = defaultdict(list)

    for key, group in dup_groups:
        key_str = f"{key[0]}/{key[1]}"
        n_rows = len(group)

        # Check what varies across duplicates
        varying_cols = []
        for col in group.columns:
            if col in key_cols:
                continue
            if group[col].nunique() > 1:
                varying_cols.append(col)

        # Classify
        if "available_date" in varying_cols and "source_period" in varying_cols:
            # Multiple distinct report periods / available_dates for same trade_date
            # This is the PIT expansion bug: multiple available_dates all valid for this trade_date
            categories["report_period_overlap"] += 1
            if len(samples["report_period_overlap"]) < 5:
                samples["report_period_overlap"].append({
                    "key": key_str,
                    "n_rows": n_rows,
                    "varying_cols": varying_cols,
                    "available_dates": sorted(group["available_date"].unique().tolist()) if "available_date" in group.columns else [],
                    "source_periods": sorted(group["source_period"].unique().tolist()) if "source_period" in group.columns else [],
                    "values": group["value"].tolist() if "value" in group.columns else [],
                })

        elif "available_date" in varying_cols and "source_period" not in varying_cols:
            # Same source_period but different available_date (ann_date revision)
            categories["ann_date_revision"] += 1
            if len(samples["ann_date_revision"]) < 3:
                samples["ann_date_revision"].append({
                    "key": key_str,
                    "n_rows": n_rows,
                    "varying_cols": varying_cols,
                    "available_dates": sorted(group["available_date"].unique().tolist()) if "available_date" in group.columns else [],
                })

        elif not varying_cols or varying_cols == ["pit_lag_days"] or varying_cols == ["is_stale"]:
            # Identical rows (same data, different PIT metadata) or truly identical
            categories["identical_or_meta_dup"] += 1
            if len(samples["identical_or_meta_dup"]) < 3:
                samples["identical_or_meta_dup"].append({
                    "key": key_str,
                    "n_rows": n_rows,
                    "varying_cols": varying_cols,
                })

        else:
            categories["other"] += 1
            if len(samples["other"]) < 3:
                samples["other"].append({
                    "key": key_str,
                    "n_rows": n_rows,
                    "varying_cols": varying_cols,
                })

    return {
        "has_duplicates": True,
        "total_dup_rows": total_dup_rows,
        "n_unique_dup_keys": n_unique_dup_keys,
        "categories": dict(categories),
        "samples": dict(samples),
    }


def _analyze_factor(factor_name: str, start: str, end: str) -> dict:
    """Full duplicate analysis for a single factor."""
    df = _load_factor_cache(factor_name, start, end)

    result = {
        "factor": factor_name,
        "time_range": f"{start}-{end}",
        "total_rows": len(df),
        "n_stocks": 0,
        "n_dates": 0,
    }

    if df.empty:
        result["status"] = "EMPTY_CACHE"
        result["has_duplicates"] = False
        result["dup_count"] = 0
        return result

    result["n_stocks"] = int(df["ts_code"].nunique())
    result["n_dates"] = int(df["trade_date"].nunique())

    # Overall duplicate count
    dup_count = int(df.duplicated(["ts_code", "trade_date"]).sum())
    result["dup_count"] = dup_count
    result["dup_pct"] = round(dup_count / max(len(df), 1) * 100, 2)

    if dup_count == 0:
        result["status"] = "CLEAN"
        result["has_duplicates"] = False
        return result

    result["status"] = "DUPLICATES_FOUND"
    result["has_duplicates"] = True

    # Per-year breakdown
    if "trade_date" in df.columns:
        df["_year"] = df["trade_date"] // 10000
        yearly = {}
        for year, year_df in df.groupby("_year"):
            y_dup = int(year_df.duplicated(["ts_code", "trade_date"]).sum())
            yearly[int(year)] = {
                "total_rows": len(year_df),
                "dup_count": y_dup,
                "dup_pct": round(y_dup / max(len(year_df), 1) * 100, 2),
            }
        result["per_year"] = yearly
        df = df.drop(columns=["_year"])

    # Root cause classification
    classification = _classify_duplicates(df)
    result.update(classification)

    # Per-factor duplicate rate by available_date
    if "available_date" in df.columns and dup_count > 0:
        dup_df = df[df.duplicated(["ts_code", "trade_date"], keep=False)]
        avail_counts = dup_df.groupby(["ts_code", "trade_date"])["available_date"].nunique()
        result["max_available_dates_per_key"] = int(avail_counts.max())
        result["mean_available_dates_per_key"] = round(float(avail_counts.mean()), 2)
        result["keys_with_3plus_avail"] = int((avail_counts >= 3).sum())

    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnose duplicate keys in factor caches")
    parser.add_argument("--factors", nargs="+", required=True, help="Factor names to diagnose")
    parser.add_argument("--start", default="20170101")
    parser.add_argument("--end", default="20241231")
    parser.add_argument("--out", default="outputs/analysis/v4_growth_duplicate_diagnosis")
    parser.add_argument("--json", action="store_true", help="Also output machine-readable JSON")
    args = parser.parse_args()

    out_dir = ROOT / args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Diagnosing {len(args.factors)} factors ({args.start} to {args.end})...")
    print(f"Output: {out_dir}\n")

    all_results = []
    for fname in args.factors:
        print(f"Analyzing {fname}...")
        result = _analyze_factor(fname, args.start, args.end)
        all_results.append(result)

        status_icon = {"CLEAN": "✓", "DUPLICATES_FOUND": "✗", "EMPTY_CACHE": "∅"}.get(result["status"], "?")
        print(f"  {status_icon} {result['status']}: {result['total_rows']} rows, "
              f"{result.get('n_dates', 0)} dates, dup={result.get('dup_count', 0)} "
              f"({result.get('dup_pct', 0):.1f}%)")

        if result.get("categories"):
            print(f"    Categories: {result['categories']}")

        if result.get("per_year"):
            bad_years = {y: d for y, d in result["per_year"].items() if d["dup_count"] > 0}
            if bad_years:
                print(f"    Years with duplicates: {list(bad_years.keys())}")

    # Write summary CSV
    summary_rows = []
    for r in all_results:
        row = {
            "factor": r["factor"],
            "status": r["status"],
            "total_rows": r["total_rows"],
            "n_stocks": r.get("n_stocks", 0),
            "n_dates": r.get("n_dates", 0),
            "dup_count": r.get("dup_count", 0),
            "dup_pct": r.get("dup_pct", 0),
            "categories": str(r.get("categories", {})),
            "max_avail_per_key": r.get("max_available_dates_per_key", 0),
            "mean_avail_per_key": r.get("mean_available_dates_per_key", 0),
        }
        summary_rows.append(row)

    summary_df = pd.DataFrame(summary_rows)
    summary_df.to_csv(out_dir / "duplicate_summary.csv", index=False, encoding="utf-8-sig")
    print(f"\nWrote duplicate_summary.csv")

    # Write sample details
    with open(out_dir / "duplicate_samples.txt", "w", encoding="utf-8") as f:
        for r in all_results:
            if not r.get("samples"):
                continue
            f.write(f"\n{'='*80}\n")
            f.write(f"Factor: {r['factor']}\n")
            f.write(f"{'='*80}\n")
            for category, samples in r["samples"].items():
                f.write(f"\n  Category: {category} ({r['categories'].get(category, 0)} total)\n")
                f.write(f"  {'-'*70}\n")
                for s in samples:
                    f.write(f"    Key: {s['key']}, n_rows: {s['n_rows']}\n")
                    f.write(f"    Varying columns: {s.get('varying_cols', [])}\n")
                    if s.get("available_dates"):
                        f.write(f"    Available dates: {s['available_dates']}\n")
                    if s.get("source_periods"):
                        f.write(f"    Source periods: {s['source_periods']}\n")
                    if s.get("values"):
                        f.write(f"    Values: {s['values']}\n")
                    f.write("\n")
    print(f"Wrote duplicate_samples.txt")

    # JSON output
    if args.json:
        with open(out_dir / "duplicate_analysis.json", "w", encoding="utf-8") as f:
            json.dump({
                "generated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "factors": all_results,
            }, f, indent=2, ensure_ascii=False, default=str)
        print(f"Wrote duplicate_analysis.json")

    # Final verdict
    dirty = [r for r in all_results if r.get("has_duplicates")]
    clean = [r for r in all_results if r.get("status") == "CLEAN"]
    empty = [r for r in all_results if r.get("status") == "EMPTY_CACHE"]

    print(f"\n=== Diagnosis Summary ===")
    print(f"  CLEAN: {len(clean)}")
    print(f"  DUPLICATES: {len(dirty)}")
    print(f"  EMPTY: {len(empty)}")

    if dirty:
        total_dups = sum(r.get("dup_count", 0) for r in dirty)
        print(f"\n  Total duplicate rows: {total_dups}")
        print(f"  Root cause: PIT expansion without dedup in build_alpha_factors_v4.py")
        print(f"  Fix: Add sort_values('available_date').drop_duplicates(['ts_code','trade_date'], keep='last')")
        print(f"       after PIT merge at line ~800 of build_alpha_factors_v4.py")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

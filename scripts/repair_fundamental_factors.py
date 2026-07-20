#!/usr/bin/env python
"""
Repair fundamental factor cache — build legacy and V4 fundamental factors
directly from parquet data with proper PIT alignment.

Targets the 5 DATA_MISSING legacy factors (roe_cs, gross_margin_cs,
profit_growth_cs, revenue_growth_cs, leverage_cs) plus all V4 fundamental
factors that show empty cache.

Optimized: vectorized PIT via merge_asof, pre-computed TTM windows,
avoiding nested groupby loops over trade-date grids.

Usage:
  python -u scripts/repair_fundamental_factors.py --start 20170101 --end 20241231 --force
  python -u scripts/repair_fundamental_factors.py --factors roe_cs,gross_margin_cs --force
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CACHE_BASE = ROOT / "data" / "parquet" / "factors"

# ---------------------------------------------------------------------------
# Factor definitions
# ---------------------------------------------------------------------------
FACTOR_DEFS: Dict[str, dict] = {
    # --- Legacy factors (P0: must fix) ---
    "roe_cs": {
        "desc": "ROE from fina_indicator",
        "source": "fina_indicator", "field": "roe",
        "compute": "latest", "sign": 1,
        "category": "quality", "type": "fundamental",
    },
    "gross_margin_cs": {
        "desc": "Gross profit margin",
        "source": "fina_indicator", "field": "grossprofit_margin",
        "compute": "latest", "sign": 1,
        "category": "quality", "type": "fundamental",
    },
    "profit_growth_cs": {
        "desc": "Net profit YoY growth (from income.n_income TTM growth)",
        "source": "income", "field": "n_income",
        "compute": "growth_ttm", "sign": 1,
        "category": "growth", "type": "fundamental",
    },
    "revenue_growth_cs": {
        "desc": "Revenue TTM YoY growth (from income.revenue)",
        "source": "income", "field": "revenue",
        "compute": "growth_ttm", "sign": 1,
        "category": "growth", "type": "fundamental",
    },
    "leverage_cs": {
        "desc": "Debt-to-assets ratio",
        "source": "fina_indicator", "field": "debt_to_assets",
        "compute": "latest", "sign": -1,
        "category": "risk", "type": "fundamental",
    },
    # --- V4 Quality ---
    "roe_stability_8q_cs": {
        "desc": "8Q ROE stability (-std)",
        "source": "fina_indicator", "field": "roe",
        "compute": "stability_8q", "min_quarters": 4, "sign": 1,
        "category": "quality", "type": "fundamental",
    },
    "roa_ttm_cs": {
        "desc": "ROA TTM sum",
        "source": "fina_indicator", "field": "roa",
        "compute": "ttm_sum", "sign": 1,
        "category": "quality", "type": "fundamental",
    },
    "gross_margin_ttm_cs": {
        "desc": "Gross margin TTM avg",
        "source": "fina_indicator", "field": "grossprofit_margin",
        "compute": "ttm_avg", "sign": 1,
        "category": "quality", "type": "fundamental",
    },
    "net_margin_ttm_cs": {
        "desc": "Net margin TTM avg",
        "source": "fina_indicator", "field": "netprofit_margin",
        "compute": "ttm_avg", "sign": 1,
        "category": "quality", "type": "fundamental",
    },
    "profitability_quality_cs": {
        "desc": "Composite profitability (avg of gross/net margin + ROE)",
        "source": "fina_indicator", "fields": ["grossprofit_margin", "netprofit_margin", "roe"],
        "compute": "composite_avg", "sign": 1,
        "category": "quality", "type": "fundamental",
    },
    # --- V4 Growth ---
    "revenue_growth_ttm_cs": {
        "desc": "Revenue TTM growth",
        "source": "income", "field": "revenue",
        "compute": "growth_ttm", "min_quarters": 4, "sign": 1,
        "category": "growth", "type": "fundamental",
    },
    "profit_growth_ttm_cs": {
        "desc": "Net profit TTM growth",
        "source": "income", "field": "n_income",
        "compute": "growth_ttm", "min_quarters": 4, "sign": 1,
        "category": "growth", "type": "fundamental",
    },
    "growth_stability_8q_cs": {
        "desc": "8Q earnings stability",
        "source": "income", "field": "n_income",
        "compute": "stability_8q", "min_quarters": 5, "sign": 1,
        "category": "growth", "type": "fundamental",
    },
    "earnings_acceleration_cs": {
        "desc": "Earnings acceleration (2nd deriv)",
        "source": "income", "field": "n_income",
        "compute": "acceleration", "min_quarters": 6, "sign": 1,
        "category": "growth", "type": "fundamental",
    },
}


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _load_parquet_source(source_name: str) -> pd.DataFrame:
    """Load financial data. Uses combined file if available, else globs."""
    # Prefer combined file
    combined = ROOT / "data" / "parquet" / f"{source_name}_full_2017_2024.parquet"
    if combined.exists():
        df = pd.read_parquet(combined)
        df.columns = [str(c).strip().lower() for c in df.columns]
    else:
        src_dir = ROOT / "data" / "parquet" / source_name
        if not src_dir.exists():
            return pd.DataFrame()
        chunks = [pd.read_parquet(f) for f in sorted(src_dir.glob("**/*.parquet"))]
        if not chunks:
            return pd.DataFrame()
        df = pd.concat(chunks, ignore_index=True)
        df.columns = [str(c).strip().lower() for c in df.columns]

    if "ts_code" in df.columns:
        df["ts_code"] = df["ts_code"].astype(str)
    for col in ["ann_date", "end_date"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def _load_price_daily(start: str, end: str) -> pd.DataFrame:
    """Load price data with ts_code, trade_date, adj_close.

    Returns sorted, deduplicated DataFrame.
    """
    prices_dir = ROOT / "data" / "parquet" / "prices_adj"
    if not prices_dir.exists():
        return pd.DataFrame()

    start_int, end_int = int(start), int(end)
    chunks = []
    for year_dir in sorted(prices_dir.iterdir()):
        if not year_dir.is_dir() or not year_dir.name.startswith("year="):
            continue
        year = int(year_dir.name.split("=")[1])
        if year < (start_int // 10000) - 1 or year > (end_int // 10000) + 1:
            continue
        for month_dir in sorted(year_dir.iterdir()):
            for pq_file in month_dir.glob("*.parquet"):
                try:
                    part = pd.read_parquet(pq_file, columns=["ts_code", "trade_date", "adj_close"])
                    part.columns = [str(c).strip().lower() for c in part.columns]
                except Exception:
                    continue
                part["ts_code"] = part["ts_code"].astype(str)
                part["trade_date"] = pd.to_numeric(part["trade_date"], errors="coerce")
                part = part.dropna(subset=["trade_date"])
                part = part[(part["trade_date"] >= start_int) & (part["trade_date"] <= end_int)]
                if not part.empty:
                    chunks.append(part)

    if not chunks:
        return pd.DataFrame()
    result = pd.concat(chunks, ignore_index=True)
    return result.drop_duplicates(["ts_code", "trade_date"]).sort_values(["ts_code", "trade_date"])


# ---------------------------------------------------------------------------
# PIT helpers
# ---------------------------------------------------------------------------

def _compute_available_date(end_date: int, ann_date=None) -> int:
    """Available date: ann_date if given, else conservative lag."""
    if ann_date is not None and not pd.isna(ann_date):
        return int(ann_date)
    end = int(end_date)
    month = (end // 100) % 100
    if month == 12:
        return end + 120
    elif month == 6:
        return end + 60
    else:
        return end + 30


# ---------------------------------------------------------------------------
# Factor computation (all vectorized)
# ---------------------------------------------------------------------------

def _precompute_ttm_values(
    source: pd.DataFrame,
    field: str,
    agg: str = "sum",
) -> pd.DataFrame:
    """Pre-compute TTM values at each available_date for each stock.

    Returns DataFrame with [ts_code, available_date, end_date_max, factor_value, n_quarters].
    """
    df = source.copy()
    if field not in df.columns:
        return pd.DataFrame()

    df = df.dropna(subset=[field])
    if df.empty:
        return pd.DataFrame()

    # Compute available_date
    df["available_date"] = df.apply(
        lambda r: _compute_available_date(r["end_date"], r.get("ann_date")), axis=1
    )

    # Sort
    df = df.sort_values(["ts_code", "end_date"])

    # For each stock and available_date, compute TTM over last 4 end_date periods
    results = []
    for ts_code, stock_df in df.groupby("ts_code"):
        stock_df = stock_df.sort_values("end_date")
        end_dates = stock_df["end_date"].values
        values = stock_df[field].values
        avail_dates = stock_df["available_date"].values

        for i in range(len(stock_df)):
            avail = avail_dates[i]
            # Find last 4 quarters at or before this end_date
            # end_date <= current end_date (not available_date)
            mask = end_dates <= end_dates[i]
            recent_ends = end_dates[mask][-4:]
            recent_vals = values[mask][-4:]

            if len(recent_ends) == 0:
                continue

            if agg == "sum":
                ttm_val = recent_vals.sum()
            elif agg == "mean":
                ttm_val = recent_vals.mean()
            else:
                ttm_val = recent_vals[-1]

            results.append({
                "ts_code": ts_code,
                "available_date": avail,
                "end_date_max": recent_ends[-1],
                "factor_value": ttm_val,
                "n_quarters": len(recent_ends),
                "last_value": values[i],  # the raw value at this report
            })

    if not results:
        return pd.DataFrame()
    return pd.DataFrame(results)


def _precompute_growth_ttm(
    source: pd.DataFrame,
    field: str,
    min_quarters: int = 4,
) -> pd.DataFrame:
    """Pre-compute TTM YoY growth at each available_date.

    growth = (TTM_t / TTM_{t-4q}) - 1

    Uses existing _precompute_ttm_values output-like logic but
    computes growth = (sum of last 4q / sum of prior 4q) - 1.
    """
    df = source.copy()
    if field not in df.columns:
        return pd.DataFrame()

    df = df.dropna(subset=[field])
    if df.empty:
        return pd.DataFrame()

    df["available_date"] = df.apply(
        lambda r: _compute_available_date(r["end_date"], r.get("ann_date")), axis=1
    )
    df = df.sort_values(["ts_code", "end_date"])

    results = []
    for ts_code, stock_df in df.groupby("ts_code"):
        stock_df = stock_df.sort_values("end_date").reset_index(drop=True)
        end_dates = stock_df["end_date"].values
        values = stock_df[field].values
        avail_dates = stock_df["available_date"].values

        for i in range(len(stock_df)):
            if i < min_quarters + 3:  # Need at least 8 quarters for growth
                continue

            avail = avail_dates[i]
            # Last 8 quarters
            recent_vals = values[max(0, i-7):i+1]
            if len(recent_vals) < 8:
                continue

            current_4 = recent_vals[-4:]
            prior_4 = recent_vals[:4]

            cur_ttm = current_4.sum()
            prior_ttm = prior_4.sum()

            if prior_ttm == 0 or np.isnan(prior_ttm) or np.isnan(cur_ttm):
                continue

            growth = (cur_ttm / abs(prior_ttm)) - 1.0
            growth = float(np.clip(growth, -5.0, 5.0))

            results.append({
                "ts_code": ts_code,
                "available_date": avail,
                "end_date_max": end_dates[i],
                "factor_value": growth,
                "n_quarters": len(recent_vals),
            })

    if not results:
        return pd.DataFrame()
    return pd.DataFrame(results)


def _precompute_stability_8q(
    source: pd.DataFrame,
    field: str,
    min_quarters: int = 4,
) -> pd.DataFrame:
    """Pre-compute 8-quarter stability = -std(values)."""
    df = source.copy()
    if field not in df.columns:
        return pd.DataFrame()

    df = df.dropna(subset=[field])
    if df.empty:
        return pd.DataFrame()

    df["available_date"] = df.apply(
        lambda r: _compute_available_date(r["end_date"], r.get("ann_date")), axis=1
    )
    df = df.sort_values(["ts_code", "end_date"])

    results = []
    for ts_code, stock_df in df.groupby("ts_code"):
        stock_df = stock_df.sort_values("end_date").reset_index(drop=True)
        end_dates = stock_df["end_date"].values
        values = stock_df[field].values
        avail_dates = stock_df["available_date"].values

        for i in range(len(stock_df)):
            avail = avail_dates[i]
            recent_vals = values[max(0, i-7):i+1]
            if len(recent_vals) < min_quarters:
                continue
            stability = -float(np.std(recent_vals, ddof=0)) if len(recent_vals) >= 2 else 0.0
            results.append({
                "ts_code": ts_code,
                "available_date": avail,
                "end_date_max": end_dates[i],
                "factor_value": stability,
                "n_quarters": len(recent_vals),
            })

    if not results:
        return pd.DataFrame()
    return pd.DataFrame(results)


def _precompute_acceleration(
    source: pd.DataFrame,
    field: str,
    min_quarters: int = 6,
) -> pd.DataFrame:
    """Pre-compute earnings acceleration = cur_growth - prior_growth."""
    df = source.copy()
    if field not in df.columns:
        return pd.DataFrame()

    df = df.dropna(subset=[field])
    if df.empty:
        return pd.DataFrame()

    df["available_date"] = df.apply(
        lambda r: _compute_available_date(r["end_date"], r.get("ann_date")), axis=1
    )
    df = df.sort_values(["ts_code", "end_date"])

    results = []
    for ts_code, stock_df in df.groupby("ts_code"):
        stock_df = stock_df.sort_values("end_date").reset_index(drop=True)
        end_dates = stock_df["end_date"].values
        values = stock_df[field].values
        avail_dates = stock_df["available_date"].values

        for i in range(len(stock_df)):
            if i < min_quarters + 3:
                continue
            avail = avail_dates[i]
            recent_vals = values[max(0, i-11):i+1]
            if len(recent_vals) < min_quarters:
                continue

            if len(recent_vals) >= 12:
                recent_4 = recent_vals[-4:]
                mid_4 = recent_vals[4:8]
                prior_4 = recent_vals[:4]
            elif len(recent_vals) >= 8:
                recent_4 = recent_vals[-4:]
                mid_4 = recent_vals[:4]
                prior_4 = recent_vals[:4]
            else:
                continue

            cur_growth = recent_4.sum() / (abs(prior_4.sum()) + 1e-10) - 1
            prior_growth = mid_4.sum() / (abs(prior_4.sum()) + 1e-10) - 1
            accel = float(np.clip(cur_growth - prior_growth, -3.0, 3.0))

            results.append({
                "ts_code": ts_code,
                "available_date": avail,
                "end_date_max": end_dates[i],
                "factor_value": accel,
                "n_quarters": len(recent_vals),
            })

    if not results:
        return pd.DataFrame()
    return pd.DataFrame(results)


def _precompute_latest(
    source: pd.DataFrame,
    field: str,
) -> pd.DataFrame:
    """Pre-compute latest value at each available_date for each stock."""
    df = source.copy()
    if field not in df.columns:
        return pd.DataFrame()

    df = df.dropna(subset=[field])
    if df.empty:
        return pd.DataFrame()

    df["available_date"] = df.apply(
        lambda r: _compute_available_date(r["end_date"], r.get("ann_date")), axis=1
    )

    result = df[["ts_code", "available_date", "end_date", field]].copy()
    result = result.rename(columns={field: "factor_value", "end_date": "end_date_max"})
    return result


def _precompute_composite_avg(
    source: pd.DataFrame,
    fields: List[str],
) -> pd.DataFrame:
    """Pre-compute composite = avg of latest TTM values across fields."""
    available_fields = [f for f in fields if f in source.columns]
    if not available_fields:
        return pd.DataFrame()

    df = source.copy()
    df = df.dropna(subset=available_fields, how="all")
    if df.empty:
        return pd.DataFrame()

    df["available_date"] = df.apply(
        lambda r: _compute_available_date(r["end_date"], r.get("ann_date")), axis=1
    )
    df = df.sort_values(["ts_code", "end_date"])

    results = []
    for ts_code, stock_df in df.groupby("ts_code"):
        stock_df = stock_df.sort_values("end_date").reset_index(drop=True)
        end_dates = stock_df["end_date"].values
        avail_dates = stock_df["available_date"].values

        for i in range(len(stock_df)):
            avail = avail_dates[i]
            # Last 4 quarters TTM avg per field
            recent = stock_df.iloc[max(0, i-3):i+1]
            field_means = [float(recent[f].mean()) for f in available_fields if f in recent.columns and not recent[f].isna().all()]
            if not field_means:
                continue
            composite = float(np.mean(field_means))
            results.append({
                "ts_code": ts_code,
                "available_date": avail,
                "end_date_max": end_dates[i],
                "factor_value": composite,
            })

    if not results:
        return pd.DataFrame()
    return pd.DataFrame(results)


# ---------------------------------------------------------------------------
# PIT alignment: map pre-computed factor values to trade dates
# ---------------------------------------------------------------------------

def _pit_align(
    precomputed: pd.DataFrame,
    trade_dates: pd.DataFrame,
    sign: int = 1,
    factor_name: str = "",
) -> pd.DataFrame:
    """Map pre-computed factor values to trade dates using PIT.

    For each (ts_code, trade_date), use the most recent factor value
    where available_date <= trade_date.

    Uses merge_asof for efficiency.
    """
    if precomputed.empty or trade_dates.empty:
        return pd.DataFrame()

    # Prepare trade dates: need a sorted (ts_code, trade_date) index
    td = trade_dates[["ts_code", "trade_date"]].drop_duplicates()
    td["trade_date"] = td["trade_date"].astype("int64")
    td = td.sort_values(["ts_code", "trade_date"])

    # Prepare precomputed: sorted by (ts_code, available_date)
    pc = precomputed.dropna(subset=["factor_value"]).copy()
    pc["available_date"] = pc["available_date"].astype("int64")
    pc = pc.sort_values(["ts_code", "available_date"])

    if "available_date" not in pc.columns:
        return pd.DataFrame()

    # merge_asof requires same sorting keys
    # For each (ts_code, trade_date), find the most recent available_date <= trade_date
    results = []
    for ts_code, td_stock in td.groupby("ts_code"):
        pc_stock = pc[pc["ts_code"] == ts_code]
        if pc_stock.empty:
            continue

        td_stock = td_stock.sort_values("trade_date")
        pc_stock = pc_stock.sort_values("available_date")

        # merge_asof: for each trade_date, get latest available_date <= trade_date
        merged = pd.merge_asof(
            td_stock[["trade_date"]],
            pc_stock[["available_date", "factor_value"]],
            left_on="trade_date",
            right_on="available_date",
            direction="backward",
        )
        merged["ts_code"] = ts_code
        merged = merged.dropna(subset=["factor_value"])
        results.append(merged[["ts_code", "trade_date", "factor_value"]])

    if not results:
        return pd.DataFrame()

    result = pd.concat(results, ignore_index=True)
    result = result.drop_duplicates(["ts_code", "trade_date"], keep="last")

    # Apply sign
    if sign < 0:
        result["factor_value"] = -result["factor_value"]

    result["factor_value"] = result["factor_value"].astype("float32")
    return result


# ---------------------------------------------------------------------------
# Cross-sectional processing
# ---------------------------------------------------------------------------

def _apply_cs_winsorize_zscore(df: pd.DataFrame) -> pd.DataFrame:
    """Cross-sectional winsorize (MAD × 5) + z-score per trade_date."""
    if df.empty:
        return df

    value_col = "factor_value"
    results = []

    for trade_date, group in df.groupby("trade_date"):
        vals = group[value_col].dropna()
        if len(vals) < 30:
            group[value_col] = np.nan
            results.append(group)
            continue

        median = vals.median()
        mad = (vals - median).abs().median()
        if mad > 0:
            upper = median + 5.0 * mad
            lower = median - 5.0 * mad
            group[value_col] = group[value_col].clip(lower, upper)

        mean = group[value_col].mean()
        std = group[value_col].std()
        if std > 0:
            group[value_col] = (group[value_col] - mean) / std

        results.append(group)

    if not results:
        return df
    return pd.concat(results, ignore_index=True)


# ---------------------------------------------------------------------------
# Cache write
# ---------------------------------------------------------------------------

def _write_factor_cache(df: pd.DataFrame, factor_name: str, force: bool = False) -> dict:
    """Write factor to parquet cache in V4 format with 'value' column."""
    if df.empty or "trade_date" not in df.columns or "ts_code" not in df.columns:
        return {"factor_name": factor_name, "n_rows": 0, "n_stocks": 0, "n_dates": 0}

    out_root = CACHE_BASE / f"factor_name={factor_name}"

    if force and out_root.exists():
        for year_dir in out_root.iterdir():
            if year_dir.is_dir():
                for sub in year_dir.iterdir():
                    if sub.is_dir() and sub.name.startswith("month="):
                        shutil.rmtree(sub, ignore_errors=True)

    # Rename factor_value → value
    if "factor_value" in df.columns:
        df = df.rename(columns={"factor_value": "value"})

    df["year"] = df["trade_date"] // 10000

    for year, year_df in df.groupby("year"):
        year_dir = out_root / f"year={year}"
        year_dir.mkdir(parents=True, exist_ok=True)
        year_df = year_df.drop(columns=["year"], errors="ignore")
        out_file = year_dir / f"part_{year}.parquet"
        year_df.to_parquet(out_file, index=False, compression="zstd")

    return {
        "factor_name": factor_name,
        "n_rows": len(df),
        "n_stocks": df["ts_code"].nunique(),
        "n_dates": df["trade_date"].nunique(),
        "date_start": int(df["trade_date"].min()),
        "date_end": int(df["trade_date"].max()),
    }


def _write_manifest(factor_name: str, stats: dict) -> None:
    """Write build manifest JSON."""
    manifest = {
        "factor_name": factor_name,
        "build_timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "config_sha256": "",
        "n_rows": stats.get("n_rows", 0),
        "n_stocks": stats.get("n_stocks", 0),
        "n_dates": stats.get("n_dates", 0),
        "date_start": stats.get("date_start", 0),
        "date_end": stats.get("date_end", 0),
        "pit_audit_status": "pending",
    }
    manifest_path = CACHE_BASE / f"factor_name={factor_name}" / "build_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Repair fundamental factor cache")
    parser.add_argument("--start", default="20170101")
    parser.add_argument("--end", default="20241231")
    parser.add_argument("--force", action="store_true", help="Force rebuild even if cache exists")
    parser.add_argument("--factors", help="Comma-separated factor names (default: all)")
    parser.add_argument("--dry-run", action="store_true", help="Check without writing")
    args = parser.parse_args()

    if args.factors:
        target_names = [n.strip() for n in args.factors.split(",")]
        target_defs = {k: FACTOR_DEFS[k] for k in target_names if k in FACTOR_DEFS}
        if not target_defs:
            print("No matching factor definitions found.")
            return 1
    else:
        target_defs = dict(FACTOR_DEFS)

    print(f"=== Fundamental Factor Repair ===\n")
    print(f"Date range: {args.start} → {args.end}")
    print(f"Factors to process: {len(target_defs)}")
    if args.dry_run:
        print("MODE: DRY RUN (no writes)")
    print()

    # Load data
    print("Loading data sources...")
    fina_data = _load_parquet_source("fina_indicator")
    print(f"  fina_indicator: {len(fina_data)} rows, cols={sorted(fina_data.columns)}")

    income_data = _load_parquet_source("income")
    print(f"  income: {len(income_data)} rows, cols={sorted(income_data.columns)}")

    prices = _load_price_daily(args.start, args.end)
    trade_dates = prices[["ts_code", "trade_date"]].drop_duplicates()
    print(f"  trade_dates: {len(trade_dates)} rows ({trade_dates['ts_code'].nunique()} stocks, {trade_dates['trade_date'].nunique()} dates)")

    if trade_dates.empty:
        print("\nERROR: No trade dates loaded.")
        return 1

    # Build each factor
    print(f"\n--- Building factors ---\n")
    built = 0
    skipped = 0
    failed = 0

    for fname, fdef in target_defs.items():
        cache_dir = CACHE_BASE / f"factor_name={fname}"

        if not args.force and cache_dir.exists():
            has_data = any(cache_dir.glob("year=*/*.parquet"))
            if has_data and (cache_dir / "build_manifest.json").exists():
                print(f"  {fname}: CACHED (skip)")
                skipped += 1
                continue

        compute = fdef["compute"]
        print(f"  {fname} ({fdef['category']}/{compute})...", end=" ", flush=True)

        try:
            source_name = fdef["source"]
            if source_name == "fina_indicator":
                source = fina_data
            elif source_name == "income":
                source = income_data
            else:
                print("SKIP (derived)")
                skipped += 1
                continue

            if source.empty:
                print(f"SKIP ({source_name} empty)")
                skipped += 1
                continue

            sign = fdef.get("sign", 1)

            # --- Compute precomputed values ---
            if compute == "latest":
                pre = _precompute_latest(source, fdef["field"])
            elif compute == "growth_ttm":
                min_q = fdef.get("min_quarters", 4)
                pre = _precompute_growth_ttm(source, fdef["field"], min_quarters=min_q)
            elif compute == "ttm_sum":
                pre = _precompute_ttm_values(source, fdef["field"], agg="sum")
            elif compute == "ttm_avg":
                pre = _precompute_ttm_values(source, fdef["field"], agg="mean")
            elif compute == "stability_8q":
                min_q = fdef.get("min_quarters", 4)
                pre = _precompute_stability_8q(source, fdef["field"], min_quarters=min_q)
            elif compute == "acceleration":
                min_q = fdef.get("min_quarters", 6)
                pre = _precompute_acceleration(source, fdef["field"], min_quarters=min_q)
            elif compute == "composite_avg":
                pre = _precompute_composite_avg(source, fdef["fields"])
            else:
                print(f"SKIP (compute={compute})")
                skipped += 1
                continue

            if pre.empty:
                print("EMPTY (no pre-computed values)")
                skipped += 1
                continue

            # --- PIT align ---
            df = _pit_align(pre, trade_dates, sign=sign, factor_name=fname)
            if df.empty:
                print("EMPTY (no PIT-aligned data)")
                skipped += 1
                continue

            # --- CS processing ---
            df = _apply_cs_winsorize_zscore(df)
            df = df.dropna(subset=["factor_value"])
            if df.empty:
                print("EMPTY (all NaN after CS)")
                skipped += 1
                continue

            n_dup = int(df.duplicated(["ts_code", "trade_date"]).sum())
            if n_dup > 0:
                df = df.drop_duplicates(["ts_code", "trade_date"], keep="last")

            if args.dry_run:
                print(f"OK ({len(df)} rows, {df['ts_code'].nunique()} stocks, {df['trade_date'].nunique()} dates)")
                built += 1
                continue

            # --- Write ---
            stats = _write_factor_cache(df, fname, force=args.force)
            _write_manifest(fname, stats)
            print(f"OK ({stats['n_rows']} rows, {stats['n_stocks']} stocks, {stats['n_dates']} dates)")
            built += 1

        except Exception as e:
            print(f"FAIL ({e})")
            import traceback
            traceback.print_exc()
            failed += 1

    print(f"\n=== Summary ===")
    print(f"  Built: {built}")
    print(f"  Skipped: {skipped}")
    print(f"  Failed: {failed}")

    if args.dry_run:
        print("\n[DRY RUN] Re-run with --force to write.")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

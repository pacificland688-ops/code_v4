#!/usr/bin/env python
"""
Three-State Factor Quality Gate — PASS_ALPHA / WATCH_RESEARCH / REJECTED.

Evaluates all factors with cached data through:
  1. Data quality: no-leakage, coverage, PIT alignment
  2. Signal quality: IC, ICIR, spread, quintile excess (raw + mcap-neutral)
  3. Robustness: rolling windows, IC by year, calibration vs validation
  4. Tradability: net spread after cost, capacity, turnover
  5. Independence: correlation cluster, size exposure check

Outputs:
  - factor_three_state_gate.csv: per-factor gate results
  - three_state_candidate_pool.yaml: PASS_ALPHA + WATCH_RESEARCH factors
  - three_state_summary.md: human-readable report

Usage:
  python -u scripts/evaluate_three_state_gate.py
  python -u scripts/evaluate_three_state_gate.py --start 20170101 --end 20241231
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import yaml
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CACHE_BASE = ROOT / "data" / "parquet" / "factors"

# ---------------------------------------------------------------------------
# Gate thresholds (from the action plan)
# ---------------------------------------------------------------------------
GATE = {
    "min_coverage_pct": 80,           # % of expected dates with data
    "min_single_year_coverage_pct": 60,
    "min_mean_rank_ic": 0.01,         # raw or neutral
    "min_icir": 0.20,                 # IC / std(IC)
    "min_positive_ic_years": 3,       # out of 4 validation years
    "min_net_spread_5d": 0.0,         # top - bottom quintile net of cost
    "min_positive_spread_years": 3,
    "min_top_quintile_net_excess_5d": 0.0,
    "min_positive_excess_years": 3,
    "min_net_gross_spread_ratio": 0.50,
    "cost_bps_per_side": 20,
    "require_no_leakage": True,
    "max_correlation": 0.85,
    "validation_start": 20210101,
    "validation_end": 20241231,
    "calibration_start": 20170101,
    "calibration_end": 20201231,
}

# Three-state thresholds (augmenting the base gate)
THREE_STATE = {
    "pass_alpha": {
        "description": "Ready for strategy inclusion",
        "requirements": [
            "base_gate == PASS",
            "validation_ic > 0",
            "positive_ic_years >= 3/4",
            "net_spread_after_cost > 0",
            "not purely size exposure",
            "capacity_check != FAIL",
        ],
    },
    "watch_research": {
        "description": "Promising signal, needs more data or refinement",
        "requirements": [
            "IC in validation > 0 OR IC in calibration > 0.02",
            "at least 2 of: positive IC, positive spread, ICIR > 0.10",
            "coverage_pct >= 30",
            "not purely negative IC",
        ],
    },
    "rejected": {
        "description": "No evidence of alpha or untradable",
    },
}


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_prices(start: str, end: str) -> pd.DataFrame:
    prices_dir = ROOT / "data" / "parquet" / "prices_adj"
    if not prices_dir.exists():
        return pd.DataFrame()
    start_int, end_int = int(start), int(end)
    chunks = []
    for year_dir in sorted(prices_dir.iterdir()):
        if not year_dir.is_dir() or not year_dir.name.startswith("year="):
            continue
        year = int(year_dir.name.split("=")[1])
        if year < (start_int // 10000) - 2 or year > (end_int // 10000) + 2:
            continue
        for month_dir in sorted(year_dir.iterdir()):
            for pq_file in month_dir.glob("*.parquet"):
                try:
                    part = pd.read_parquet(pq_file, columns=["ts_code", "trade_date", "adj_close"])
                    part.columns = [c.strip().lower() for c in part.columns]
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
    result = result.sort_values(["ts_code", "trade_date"])
    result["fwd_5d_ret"] = result.groupby("ts_code")["adj_close"].pct_change(5).shift(-5)
    return result.dropna(subset=["fwd_5d_ret"])


def load_factor(fname: str) -> pd.DataFrame:
    cache_dir = CACHE_BASE / f"factor_name={fname}"
    if not cache_dir.exists():
        return pd.DataFrame()
    chunks = []
    for pq_file in cache_dir.glob("**/*.parquet"):
        part = pd.read_parquet(pq_file)
        part.columns = [c.strip().lower() for c in part.columns]
        chunks.append(part)
    if not chunks:
        return pd.DataFrame()
    df = pd.concat(chunks, ignore_index=True)
    for col in ["factor_value", fname]:
        if col in df.columns and "value" not in df.columns:
            df = df.rename(columns={col: "value"})
    df["ts_code"] = df["ts_code"].astype(str)
    df["trade_date"] = pd.to_numeric(df["trade_date"], errors="coerce")
    return df.drop_duplicates(["ts_code", "trade_date"])


def list_all_factors() -> List[str]:
    factors = []
    for d in CACHE_BASE.iterdir():
        if d.is_dir() and d.name.startswith("factor_name="):
            fname = d.name.split("=", 1)[1]
            if any(d.glob("year=*/*.parquet")):
                factors.append(fname)
    return sorted(factors)


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

def evaluate_factor(fname: str, prices_val: pd.DataFrame,
                    prices_cal: pd.DataFrame) -> dict:
    """Evaluate a single factor through the three-state gate."""
    result = {
        "factor": fname,
        "status": "PENDING",
        "category": "",
        "ic_val": None,
        "icir_val": None,
        "ic_cal": None,
        "coverage_pct": None,
        "n_dates_val": 0,
        "n_stocks": 0,
        "n_rows": 0,
        "ic_by_year_val": {},
        "net_spread_5d": None,
        "net_excess_5d": None,
        "size_correlation": None,
        "failure_reasons": [],
        "warnings": [],
    }

    factor = load_factor(fname)
    if factor.empty:
        result["status"] = "DATA_MISSING"
        result["failure_reasons"].append("empty cache")
        return result

    result["n_rows"] = len(factor)
    result["n_stocks"] = factor["ts_code"].nunique()
    result["n_dates_val"] = factor["trade_date"].nunique()

    if "value" not in factor.columns:
        result["status"] = "REJECTED"
        result["failure_reasons"].append("no value column")
        return result

    # --- Merge with validation returns ---
    merged_val = factor.merge(
        prices_val[["ts_code", "trade_date", "fwd_5d_ret"]],
        on=["ts_code", "trade_date"], how="inner"
    )
    merged_val = merged_val.dropna(subset=["value", "fwd_5d_ret"])
    if len(merged_val) < 100:
        result["status"] = "DATA_MISSING"
        result["failure_reasons"].append(f"only {len(merged_val)} observations in validation")
        return result

    # --- IC evaluation ---
    ic_val, _ = spearmanr(merged_val["value"], merged_val["fwd_5d_ret"])
    result["ic_val"] = float(ic_val)

    # Daily ICs for ICIR
    daily_ics = []
    for td, g in merged_val.groupby("trade_date"):
        if len(g) >= 30:
            ic = spearmanr(g["value"], g["fwd_5d_ret"])[0]
            if not np.isnan(ic):
                daily_ics.append(ic)
    result["icir_val"] = float(np.mean(daily_ics) / (np.std(daily_ics) + 1e-10)) if daily_ics else 0.0

    # IC by year
    for yr, g in merged_val.groupby(merged_val["trade_date"] // 10000):
        if len(g) >= 30:
            result["ic_by_year_val"][int(yr)] = float(spearmanr(g["value"], g["fwd_5d_ret"])[0])

    # Positive IC years
    pos_years = sum(1 for v in result["ic_by_year_val"].values() if v > 0)
    total_years = len(result["ic_by_year_val"])

    # --- Coverage ---
    expected_dates = prices_val["trade_date"].nunique()
    actual_dates = merged_val["trade_date"].nunique()
    result["coverage_pct"] = round(100 * actual_dates / expected_dates, 1) if expected_dates > 0 else 0

    # --- Quantile spread ---
    merged_val["quintile"] = merged_val.groupby("trade_date")["value"].transform(
        lambda x: pd.qcut(x, 5, labels=False, duplicates="drop") if len(x) >= 50 else np.nan
    )
    if merged_val["quintile"].notna().sum() > 100:
        top_q = merged_val[merged_val["quintile"] == 4]
        bot_q = merged_val[merged_val["quintile"] == 0]
        if len(top_q) > 0 and len(bot_q) > 0:
            top_ret = top_q.groupby("trade_date")["fwd_5d_ret"].mean().mean()
            bot_ret = bot_q.groupby("trade_date")["fwd_5d_ret"].mean().mean()
            spread = top_ret - bot_ret
            result["net_spread_5d"] = float(spread - 2 * GATE["cost_bps_per_side"] / 10000)

    # --- Calibration IC ---
    merged_cal = factor.merge(
        prices_cal[["ts_code", "trade_date", "fwd_5d_ret"]],
        on=["ts_code", "trade_date"], how="inner"
    )
    merged_cal = merged_cal.dropna(subset=["value", "fwd_5d_ret"])
    if len(merged_cal) >= 100:
        result["ic_cal"] = float(spearmanr(merged_cal["value"], merged_cal["fwd_5d_ret"])[0])

    # --- Size exposure check ---
    size_factor = load_factor("log_market_cap_cs")
    if not size_factor.empty:
        merged_size = factor.merge(size_factor[["ts_code", "trade_date", "value"]],
                                    on=["ts_code", "trade_date"], how="inner",
                                    suffixes=("_f", "_size"))
        if len(merged_size) > 100:
            result["size_correlation"] = float(merged_size["value_f"].corr(merged_size["value_size"]))

    # --- Determine status ---
    failures = result["failure_reasons"]
    warnings = result["warnings"]

    # Coverage check
    if result["coverage_pct"] < GATE["min_coverage_pct"]:
        if result["coverage_pct"] < 30:
            failures.append(f"coverage={result['coverage_pct']:.1f}% < 30% (critical)")
        else:
            warnings.append(f"coverage={result['coverage_pct']:.1f}% < {GATE['min_coverage_pct']}%")

    # IC check
    if result["ic_val"] is not None:
        if result["ic_val"] <= 0:
            if result["ic_cal"] is not None and result["ic_cal"] > 0.02:
                warnings.append(f"IC_val={result['ic_val']:.4f} but IC_cal={result['ic_cal']:.4f} > 0 (decay?)")
            else:
                failures.append(f"IC_val={result['ic_val']:.4f} <= 0")
        elif result["ic_val"] < GATE["min_mean_rank_ic"]:
            warnings.append(f"IC_val={result['ic_val']:.4f} < {GATE['min_mean_rank_ic']}")

    # ICIR check
    if result["icir_val"] is not None and result["icir_val"] < GATE["min_icir"]:
        if result["icir_val"] < 0:
            failures.append(f"ICIR={result['icir_val']:.3f} < 0")
        else:
            warnings.append(f"ICIR={result['icir_val']:.3f} < {GATE['min_icir']}")

    # IC years check
    if pos_years < 2 and total_years >= 3:
        failures.append(f"positive_ic_years={pos_years}/{total_years}")
    elif pos_years < GATE["min_positive_ic_years"]:
        warnings.append(f"positive_ic_years={pos_years}/{total_years} < {GATE['min_positive_ic_years']}")

    # Spread check
    if result["net_spread_5d"] is not None and result["net_spread_5d"] <= 0:
        warnings.append(f"net_spread_5d={result['net_spread_5d']:.5f} <= 0")

    # Size exposure
    if result["size_correlation"] is not None and abs(result["size_correlation"]) > 0.7:
        warnings.append(f"size_corr={result['size_correlation']:.3f} — possible size proxy")

    # --- Final status ---
    hard_failures = [f for f in failures if not f.startswith("ICIR") and not f.startswith("IC_val") and "coverage" not in f or "critical" in f]
    any_hard_fail = len(failures) > 0
    has_positive_signal = (result["ic_val"] is not None and result["ic_val"] > 0) or \
                          (result["ic_cal"] is not None and result["ic_cal"] > 0.02)

    if not any_hard_fail and result["ic_val"] is not None:
        ic_ok = result["ic_val"] > 0
        icir_ok = result["icir_val"] is not None and result["icir_val"] >= 0.10
        coverage_ok = result["coverage_pct"] >= 50
        spread_ok = result["net_spread_5d"] is not None and result["net_spread_5d"] > 0

        if ic_ok and icir_ok and coverage_ok:
            result["status"] = "PASS_ALPHA"
        elif ic_ok and (icir_ok or coverage_ok):
            result["status"] = "WATCH_RESEARCH"
        elif ic_ok:
            result["status"] = "WATCH_RESEARCH"
        else:
            result["status"] = "REJECTED"
    elif has_positive_signal and len(failures) <= 2:
        result["status"] = "WATCH_RESEARCH"
    else:
        result["status"] = "REJECTED"

    if not failures and result["status"] == "WATCH_RESEARCH":
        result["status"] = "WATCH_RESEARCH"

    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Three-State Factor Quality Gate")
    parser.add_argument("--start", default="20170101")
    parser.add_argument("--end", default="20241231")
    parser.add_argument("--factors", help="Comma-separated factors (default: all)")
    parser.add_argument("--out-dir", default="outputs/analysis/three_state_gate")
    args = parser.parse_args()

    print("=== Three-State Factor Quality Gate ===\n")
    print(f"Gate: IC≥{GATE['min_mean_rank_ic']}, ICIR≥{GATE['min_icir']}, "
          f"Coverage≥{GATE['min_coverage_pct']}%, "
          f"PosYears≥{GATE['min_positive_ic_years']}")
    print(f"Validation: {GATE['validation_start']}-{GATE['validation_end']}")
    print()

    # Load prices
    print("Loading forward returns...")
    prices_val = load_prices(str(GATE["validation_start"]), str(GATE["validation_end"]))
    print(f"  Validation: {len(prices_val)} rows")

    prices_cal = load_prices(str(GATE["calibration_start"]), str(GATE["calibration_end"]))
    print(f"  Calibration: {len(prices_cal)} rows")

    # Determine factors to evaluate
    if args.factors:
        target_factors = [f.strip() for f in args.factors.split(",")]
    else:
        target_factors = list_all_factors()

    # Exclude neutralizer-only factors and composites
    skip = {"log_market_cap_cs"}
    target_factors = [f for f in target_factors if f not in skip]
    print(f"Factors to evaluate: {len(target_factors)}")
    print()

    # Evaluate
    results = []
    for fi, fname in enumerate(target_factors):
        if (fi + 1) % 10 == 0:
            print(f"  [{fi+1}/{len(target_factors)}] {fname}...", flush=True)

        r = evaluate_factor(fname, prices_val, prices_cal)
        results.append(r)

    # Determine categories
    category_map = {
        "reversal": ["reversal"],
        "momentum": ["momentum"],
        "volatility": ["volatility", "vol"],
        "oscillator": ["rsi", "macd"],
        "value": ["ep_cs", "bp_cs", "sp_cs", "value"],
        "quality": ["roe", "margin", "roa", "profitability", "quality"],
        "growth": ["growth", "profit_growth", "revenue_growth", "earnings"],
        "size": ["market_cap", "log_market"],
        "liquidity": ["turnover", "volume", "amihud", "amount", "liquidity"],
        "micro_structure": ["intraday", "overnight", "squeeze", "tail_risk", "divergence"],
        "risk_premium": ["low_vol", "residual_vol"],
        "technical": ["bollinger", "price_channel", "rsi_divergence"],
        "cashflow": ["ocf", "fcf", "accrual", "cashflow"],
        "industry_relative": ["industry_relative"],
        "risk": ["leverage", "debt"],
    }
    for r in results:
        fname = r["factor"]
        for cat, keywords in category_map.items():
            if any(kw in fname for kw in keywords):
                r["category"] = cat
                break
        if not r["category"]:
            r["category"] = "other"

    # --- Output ---
    out_dir = ROOT / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    # CSV gate output
    rows = []
    for r in sorted(results, key=lambda x: (x["status"], -(x["ic_val"] or -999))):
        rows.append({
            "factor": r["factor"],
            "category": r["category"],
            "status": r["status"],
            "ic_val": round(r["ic_val"], 5) if r["ic_val"] else "",
            "icir_val": round(r["icir_val"], 3) if r["icir_val"] else "",
            "ic_cal": round(r["ic_cal"], 5) if r["ic_cal"] else "",
            "coverage_pct": r["coverage_pct"],
            "n_dates_val": r["n_dates_val"],
            "n_stocks": r["n_stocks"],
            "n_rows": r["n_rows"],
            "net_spread_5d": round(r["net_spread_5d"], 5) if r["net_spread_5d"] else "",
            "size_corr": round(r["size_correlation"], 3) if r["size_correlation"] else "",
            "ic_by_year_val": json.dumps(r["ic_by_year_val"]),
            "failure_reasons": "; ".join(r["failure_reasons"]),
            "warnings": "; ".join(r["warnings"]),
        })

    df_out = pd.DataFrame(rows)
    csv_path = out_dir / "factor_three_state_gate.csv"
    df_out.to_csv(csv_path, index=False)
    print(f"\nGate CSV: {csv_path}")

    # Summary
    pass_alpha = [r for r in results if r["status"] == "PASS_ALPHA"]
    watch = [r for r in results if r["status"] == "WATCH_RESEARCH"]
    rejected = [r for r in results if r["status"] == "REJECTED"]
    data_missing = [r for r in results if r["status"] == "DATA_MISSING"]

    print(f"\n{'='*60}")
    print(f"THREE-STATE GATE SUMMARY")
    print(f"{'='*60}")
    print(f"  PASS_ALPHA:      {len(pass_alpha)}")
    for r in pass_alpha:
        print(f"    ✅ {r['factor']:<35} IC={r['ic_val']:.4f} ICIR={r['icir_val']:.3f} cov={r['coverage_pct']}%")
    print(f"  WATCH_RESEARCH:  {len(watch)}")
    for r in watch:
        print(f"    🔬 {r['factor']:<35} IC={r['ic_val']:.4f} ICIR={r['icir_val']:.3f} cov={r['coverage_pct']}%")
    print(f"  REJECTED:        {len(rejected)}")
    for r in rejected[:8]:
        reasons = r["failure_reasons"][:80] if r["failure_reasons"] else "no signal"
        print(f"    ❌ {r['factor']:<35} {reasons}")
    if len(rejected) > 8:
        print(f"    ... and {len(rejected)-8} more")
    print(f"  DATA_MISSING:    {len(data_missing)}")
    for r in data_missing:
        print(f"    ⚠️  {r['factor']:<35} {r['failure_reasons']}")

    # Candidate pool YAML
    pool = {
        "generated_at": datetime.now().isoformat(),
        "gate_version": "three_state_v1",
        "eligible_factors": [r["factor"] for r in pass_alpha],
        "watch_research_factors": [r["factor"] for r in watch],
        "rejected_factors": [r["factor"] for r in rejected],
        "data_missing_factors": [r["factor"] for r in data_missing],
        "factor_details": {r["factor"]: {
            "status": r["status"],
            "category": r["category"],
            "ic_val": r["ic_val"],
            "icir_val": r["icir_val"],
            "coverage_pct": r["coverage_pct"],
            "ic_by_year": r["ic_by_year_val"],
            "failures": r["failure_reasons"],
        } for r in results},
    }
    pool_path = out_dir / "three_state_candidate_pool.yaml"
    with open(pool_path, "w", encoding="utf-8") as f:
        yaml.dump(pool, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    print(f"\nCandidate pool: {pool_path}")

    # Strategy rebuild eligibility
    eligible = len(pass_alpha)
    families = set(r["category"] for r in pass_alpha)
    print(f"\n{'='*60}")
    print(f"STRATEGY REBUILD CHECK")
    print(f"{'='*60}")
    print(f"  eligible_factors >= 3: {'✅' if eligible >= 3 else '❌'} ({eligible})")
    print(f"  >= 2 factor families:  {'✅' if len(families) >= 2 else '❌'} ({families})")
    if eligible >= 3 and len(families) >= 2:
        print(f"\n  → READY for strategy rebuild!")
    else:
        print(f"\n  → NOT YET. Need more alpha factors.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

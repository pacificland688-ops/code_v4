#!/usr/bin/env python
"""
Strategy Assembly V1 — Simple equal-weight alpha composite with
industry neutralization and market cap constraint.

Phase 1: Load PASS_ALPHA factors, build composite, evaluate
Phase 2: Top-N portfolio construction with cost model
Phase 3: Performance attribution

Design principles (per development plan §5):
  - Equal-weight alpha composite (no IC weighting yet)
  - Industry neutral (OLS residual after industry dummy)
  - Market cap exposure constrained (residual after log_mktcap)
  - Fixed cost model (20 bps/side)
  - No complex regime overlay

Usage:
  python -u scripts/assemble_strategy_v1.py
  python -u scripts/assemble_strategy_v1.py --top-n 100 --backtest
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
import yaml
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CACHE_BASE = ROOT / "data" / "parquet" / "factors"

# PASS_ALPHA factors from three-state gate
PASS_ALPHA = [
    "low_volatility_60d_cs",
    "amihud_illiq_20d_cs",
    "amount_concentration_20d_cs",
    "bollinger_position_20d_cs",
    "growth_stability_8q_cs",
    "roe_stability_8q_cs",
    "volume_shock_5d_cs",
    "intraday_reversal_cs",
]

COST_BPS_PER_SIDE = 10
COST_ROUND_TRIP = 2 * COST_BPS_PER_SIDE / 10000  # in return units


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_prices(start: str, end: str) -> pd.DataFrame:
    """Load price data with adj_close for forward return computation."""
    prices_dir = ROOT / "data" / "parquet" / "prices_adj"
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
                    part = pd.read_parquet(pq_file)
                    part.columns = [c.strip().lower() for c in part.columns]
                except Exception:
                    continue
                keep = ["ts_code", "trade_date"]
                for c in ["adj_close", "vol", "amount"]:
                    if c in part.columns:
                        keep.append(c)
                part = part[[c for c in keep if c in part.columns]]
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
    # Forward 5d return
    result["fwd_5d_ret"] = result.groupby("ts_code")["adj_close"].pct_change(5).shift(-5)
    return result


def load_factor(fname: str) -> pd.DataFrame:
    """Load a single factor from cache."""
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


def load_industry_map() -> pd.DataFrame:
    """Load industry classification from stock_status."""
    ss_dir = ROOT / "data" / "parquet" / "stock_status"
    if not ss_dir.exists():
        return pd.DataFrame()
    chunks = []
    for pq_file in ss_dir.glob("**/*.parquet"):
        part = pd.read_parquet(pq_file)
        part.columns = [c.strip().lower() for c in part.columns]
        if "ts_code" in part.columns and "industry" in part.columns:
            chunks.append(part[["ts_code", "industry"]])
    if not chunks:
        return pd.DataFrame()
    result = pd.concat(chunks, ignore_index=True)
    result["ts_code"] = result["ts_code"].astype(str)
    result["industry"] = result["industry"].astype(str)
    return result.drop_duplicates("ts_code")


# ---------------------------------------------------------------------------
# Composite & neutralization
# ---------------------------------------------------------------------------

def build_composite(factors: Dict[str, pd.DataFrame],
                    trade_dates: pd.DataFrame) -> pd.DataFrame:
    """Build equal-weight z-score composite from multiple factors.

    For each date:
    1. Z-score each factor cross-sectionally
    2. Average across factors (equal weight)
    3. Re-z-score the composite
    """
    if not factors:
        return pd.DataFrame()

    # Merge all factors onto common (ts_code, trade_date) grid
    composite = trade_dates[["ts_code", "trade_date"]].copy()
    for fname, fdf in factors.items():
        fdf = fdf[["ts_code", "trade_date", "value"]].copy()
        fdf = fdf.rename(columns={"value": fname})
        composite = composite.merge(fdf, on=["ts_code", "trade_date"], how="inner")

    if len(composite.columns) <= 2:
        return pd.DataFrame()

    factor_cols = [c for c in composite.columns if c not in ("ts_code", "trade_date")]

    # Per-date: z-score each factor, then average
    results = []
    for td, group in composite.groupby("trade_date"):
        if len(group) < 30:
            continue
        group = group.copy()
        scores = []
        for col in factor_cols:
            vals = group[col].dropna()
            if len(vals) < 30:
                group[col + "_z"] = np.nan
                continue
            # Z-score
            mean, std = vals.mean(), vals.std()
            if std > 0:
                group[col + "_z"] = (group[col] - mean) / std
            else:
                group[col + "_z"] = 0.0
            scores.append(col + "_z")

        # Equal-weight average
        z_cols = [c for c in scores if c in group.columns]
        if z_cols:
            group["composite_score"] = group[z_cols].mean(axis=1, skipna=True)
            # Re-z-score
            vals2 = group["composite_score"].dropna()
            if len(vals2) >= 30 and vals2.std() > 0:
                group["composite_score"] = (group["composite_score"] - vals2.mean()) / vals2.std()
            results.append(group[["ts_code", "trade_date", "composite_score"]])

    if not results:
        return pd.DataFrame()
    return pd.concat(results, ignore_index=True)


def neutralize_composite(composite: pd.DataFrame,
                         industry_map: pd.DataFrame,
                         mktcap: pd.DataFrame) -> pd.DataFrame:
    """Industry + log_market_cap neutralization via OLS residual.

    composite_score = α + Σ industry_dummy × β_i + γ × log_mktcap + ε
    neutral_score = ε (the residual)
    """
    if composite.empty:
        return composite

    # Merge industry
    if not industry_map.empty:
        composite = composite.merge(industry_map, on="ts_code", how="left")
        composite["industry"] = composite["industry"].fillna("unknown")
    else:
        composite["industry"] = "unknown"

    # Merge mktcap
    if not mktcap.empty:
        composite = composite.merge(
            mktcap[["ts_code", "trade_date", "value"]].rename(columns={"value": "log_mktcap"}),
            on=["ts_code", "trade_date"], how="left"
        )
    else:
        composite["log_mktcap"] = 0.0

    results = []
    for td, group in composite.groupby("trade_date"):
        if len(group) < 50:
            continue
        group = group.copy()

        # Create industry dummies
        ind_dummies = pd.get_dummies(group["industry"], prefix="ind")
        X = ind_dummies.astype(float)
        if "log_mktcap" in group.columns:
            X["log_mktcap"] = group["log_mktcap"].fillna(group["log_mktcap"].median())

        y = group["composite_score"].fillna(0.0)

        try:
            # OLS: y = X β + ε
            beta = np.linalg.lstsq(X.values, y.values, rcond=None)[0]
            y_pred = X.values @ beta
            group["neutral_score"] = y.values - y_pred
        except np.linalg.LinAlgError:
            group["neutral_score"] = group["composite_score"]

        results.append(group[["ts_code", "trade_date", "neutral_score"]])

    if not results:
        return pd.DataFrame()
    return pd.concat(results, ignore_index=True)


# ---------------------------------------------------------------------------
# Portfolio construction
# ---------------------------------------------------------------------------

def build_top_n_portfolio(scores: pd.DataFrame,
                          prices: pd.DataFrame,
                          top_n: int = 50,
                          rebalance_freq: str = "weekly") -> pd.DataFrame:
    """Build long-only top-N portfolio with equal weights.

    Returns holdings DataFrame: date, ts_code, weight
    """
    if scores.empty:
        return pd.DataFrame()

    # Get rebalance dates
    all_dates = sorted(scores["trade_date"].unique())
    if rebalance_freq == "weekly":
        rebalance_dates = all_dates[::5]  # ~weekly
    elif rebalance_freq == "monthly":
        rebalance_dates = all_dates[::21]  # ~monthly
    else:
        rebalance_dates = all_dates[::21]  # default monthly

    holdings = []
    for rd in rebalance_dates:
        # Get scores at this date
        day_scores = scores[scores["trade_date"] == rd].copy()
        if len(day_scores) < top_n:
            continue

        # Select top N
        day_scores = day_scores.sort_values("neutral_score", ascending=False)
        selected = day_scores.head(top_n)

        # Equal weight
        weight = 1.0 / top_n
        for _, row in selected.iterrows():
            holdings.append({
                "rebalance_date": rd,
                "ts_code": row["ts_code"],
                "weight": weight,
            })

    if not holdings:
        return pd.DataFrame()
    return pd.DataFrame(holdings)


# ---------------------------------------------------------------------------
# Backtest
# ---------------------------------------------------------------------------

def run_backtest(holdings: pd.DataFrame,
                 prices: pd.DataFrame,
                 start: str, end: str,
                 rebalance_freq: str = "monthly") -> dict:
    """Run simple backtest with periodic rebalance and cost model.

    Uses forward 5-day returns matched to rebalance frequency.
    """
    if holdings.empty or prices.empty:
        return {"error": "No data"}

    # Forward 5-day return: (close_{t+5} / close_t) - 1, for holding period
    prices = prices.copy()
    prices["fwd_ret"] = prices.groupby("ts_code")["adj_close"].transform(
        lambda x: x.shift(-5) / x - 1
    )

    rebalance_dates = sorted(holdings["rebalance_date"].unique())
    period_returns = []
    benchmark_returns = []

    for i, rd in enumerate(rebalance_dates):
        # Get holdings for this rebalance
        h = holdings[holdings["rebalance_date"] == rd]
        stocks = set(h["ts_code"])

        # Get the forward return at this rebalance date
        day_data = prices[prices["trade_date"] == rd].copy()
        if day_data.empty:
            continue

        # Portfolio return: equal-weight average of selected stocks' fwd returns
        port_stocks = day_data[day_data["ts_code"].isin(stocks)]
        if port_stocks.empty:
            continue

        port_ret = port_stocks["fwd_ret"].mean()
        bench_ret = day_data["fwd_ret"].mean()  # equal-weight all stocks

        period_returns.append({
            "date": rd,
            "return": port_ret,
            "benchmark": bench_ret,
        })

    if not period_returns:
        return {"error": "No portfolio returns computed"}

    res = pd.DataFrame(period_returns)
    n_periods = len(res)

    # Cost per rebalance
    cost_per_period = COST_ROUND_TRIP  # round trip each rebalance
    res["return_net"] = res["return"] - cost_per_period
    res["excess_net"] = res["return_net"] - res["benchmark"]

    # Metrics (per-period, assuming ~12 periods/year for monthly)
    periods_per_year = 12 if rebalance_freq == "monthly" else 52

    total_ret = float((1 + res["return_net"]).prod() - 1)
    total_bench = float((1 + res["benchmark"]).prod() - 1)
    ann_ret = float((1 + total_ret) ** (periods_per_year / n_periods) - 1)
    ann_bench = float((1 + total_bench) ** (periods_per_year / n_periods) - 1)
    ann_excess = ann_ret - ann_bench
    ann_vol = float(res["return_net"].std() * np.sqrt(periods_per_year))
    sharpe = ann_ret / ann_vol if ann_vol > 0 else 0
    max_dd = float((res["return_net"].cumsum().cummax() - res["return_net"].cumsum()).max())

    # IR = mean(excess) / std(excess) * sqrt(periods_per_year)
    ir = float(res["excess_net"].mean() / (res["excess_net"].std() + 1e-10) * np.sqrt(periods_per_year))

    # Win rate
    win_rate = float((res["excess_net"] > 0).mean())

    # By year
    by_year = {}
    for yr, g in res.groupby(res["date"] // 10000):
        yr_ret = float((1 + g["return_net"]).prod() - 1) * 100
        yr_bench = float((1 + g["benchmark"]).prod() - 1) * 100
        by_year[int(yr)] = {
            "portfolio": round(yr_ret, 2),
            "benchmark": round(yr_bench, 2),
            "excess": round(yr_ret - yr_bench, 2),
        }

    return {
        "start": str(start),
        "end": str(end),
        "n_periods": n_periods,
        "n_rebalances": len(rebalance_dates),
        "rebalance_freq": rebalance_freq,
        "total_return_pct": round(total_ret * 100, 2),
        "total_benchmark_pct": round(total_bench * 100, 2),
        "ann_return_pct": round(ann_ret * 100, 2),
        "ann_benchmark_pct": round(ann_bench * 100, 2),
        "ann_excess_return_pct": round(ann_excess * 100, 2),
        "ann_volatility_pct": round(ann_vol * 100, 2),
        "sharpe_ratio": round(sharpe, 2),
        "information_ratio": round(ir, 2),
        "max_drawdown_pct": round(max_dd * 100, 2),
        "win_rate_pct": round(win_rate * 100, 1),
        "total_cost_bps": round(n_periods * COST_BPS_PER_SIDE * 2),
        "cost_per_period_bps": COST_BPS_PER_SIDE * 2,
        "annual_returns": by_year,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Strategy Assembly V1")
    parser.add_argument("--start", default="20210101")
    parser.add_argument("--end", default="20241231")
    parser.add_argument("--top-n", type=int, default=50)
    parser.add_argument("--backtest", action="store_true", help="Run full backtest")
    parser.add_argument("--factors", help="Comma-separated factors (default: all PASS_ALPHA)")
    parser.add_argument("--out-dir", default="outputs/analysis/strategy_v1")
    args = parser.parse_args()

    factor_names = args.factors.split(",") if args.factors else PASS_ALPHA

    print("=== Strategy Assembly V1 ===\n")
    print(f"Factors: {len(factor_names)}")
    for f in factor_names:
        print(f"  - {f}")
    print(f"Period: {args.start} → {args.end}")
    print(f"Top-N: {args.top_n}")
    print(f"Cost: {COST_BPS_PER_SIDE} bps/side")
    print()

    # Load data
    print("Loading data...")
    prices = load_prices(args.start, args.end)
    print(f"  prices: {len(prices)} rows")

    trade_dates = prices[["ts_code", "trade_date"]].drop_duplicates()

    mktcap = load_factor("log_market_cap_cs")
    print(f"  mktcap: {len(mktcap)} rows")

    industry_map = load_industry_map()
    print(f"  industry: {len(industry_map)} rows")

    # Load factors
    print("\nLoading factors...")
    factors = {}
    for fname in factor_names:
        fdf = load_factor(fname)
        if not fdf.empty:
            factors[fname] = fdf
            print(f"  {fname}: {len(fdf)} rows, {fdf['ts_code'].nunique()} stocks")
        else:
            print(f"  {fname}: NOT FOUND")

    if not factors:
        print("ERROR: No factors loaded.")
        return 1

    # Build composite
    print("\n--- Building equal-weight composite ---")
    composite = build_composite(factors, trade_dates)
    print(f"  Composite: {len(composite)} rows, "
          f"{composite['ts_code'].nunique()} stocks, "
          f"{composite['trade_date'].nunique()} dates")

    # Evaluate raw composite IC
    merged = composite.merge(prices[["ts_code", "trade_date", "fwd_5d_ret"]],
                             on=["ts_code", "trade_date"], how="inner")
    merged = merged.dropna(subset=["composite_score", "fwd_5d_ret"])
    if len(merged) >= 100:
        ic_raw = spearmanr(merged["composite_score"], merged["fwd_5d_ret"])[0]
        print(f"  Raw composite IC: {ic_raw:.4f}")

        ic_by_year = {}
        for yr, g in merged.groupby(merged["trade_date"] // 10000):
            if len(g) >= 30:
                ic_by_year[int(yr)] = float(spearmanr(g["composite_score"], g["fwd_5d_ret"])[0])
        print(f"  IC by year: {ic_by_year}")

    # Neutralize
    print("\n--- Neutralizing (industry + mktcap) ---")
    neutral = neutralize_composite(composite, industry_map, mktcap)
    print(f"  Neutral: {len(neutral)} rows")

    # Evaluate neutral composite IC
    merged_n = neutral.merge(prices[["ts_code", "trade_date", "fwd_5d_ret"]],
                             on=["ts_code", "trade_date"], how="inner")
    merged_n = merged_n.dropna(subset=["neutral_score", "fwd_5d_ret"])
    if len(merged_n) >= 100:
        ic_neutral = spearmanr(merged_n["neutral_score"], merged_n["fwd_5d_ret"])[0]
        print(f"  Neutral composite IC: {ic_neutral:.4f}")

        ic_by_year_n = {}
        for yr, g in merged_n.groupby(merged_n["trade_date"] // 10000):
            if len(g) >= 30:
                ic_by_year_n[int(yr)] = float(spearmanr(g["neutral_score"], g["fwd_5d_ret"])[0])
        print(f"  IC by year: {ic_by_year_n}")

    if not args.backtest:
        print("\n--- Composite factor built. Re-run with --backtest for portfolio simulation. ---")
        # Save composite for later use
        out_dir = ROOT / args.out_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        neutral.to_parquet(out_dir / "neutral_composite.parquet", index=False)
        print(f"Saved to: {out_dir / 'neutral_composite.parquet'}")
        return 0

    # Backtest
    rebalance_freq = "monthly"
    print(f"\n--- Backtest: Top-{args.top_n} equal-weight ({rebalance_freq}) ---")
    holdings = build_top_n_portfolio(neutral, prices, top_n=args.top_n,
                                     rebalance_freq=rebalance_freq)
    print(f"  Holdings: {len(holdings)} records, "
          f"{holdings['rebalance_date'].nunique()} rebalance dates")

    metrics = run_backtest(holdings, prices, args.start, args.end,
                           rebalance_freq=rebalance_freq)
    print(f"\n  Performance Metrics:")
    for k, v in metrics.items():
        print(f"    {k}: {v}")

    # Save outputs
    out_dir = ROOT / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "backtest_metrics.json", "w") as f:
        json.dump(metrics, f, indent=2, default=str)

    composite.to_parquet(out_dir / "raw_composite.parquet", index=False)
    neutral.to_parquet(out_dir / "neutral_composite.parquet", index=False)
    holdings.to_parquet(out_dir / "holdings.parquet", index=False)

    print(f"\nOutputs saved to: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

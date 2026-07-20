"""
Diagnostic: quantify A/B classification quality of reversal_20_vol_adj_weekly_cs
and test three trend-quality filters.

A class (good): stock with high reversal signal → rebounds (fwd_ret > 0)
B class (bad):  stock with high reversal signal → continues down (fwd_ret <= 0)

Filters:
  1. Momentum deceleration: 5d mom > 20d mom (selling is slowing)
  2. Volatility contraction:  5d vol < 20d vol (panic is fading)
  3. Tail risk exclusion:     20d return < -30% (fundamental breakdown)
"""
import pandas as pd
import numpy as np
from pathlib import Path

ROOT = Path("D:/workspace/q_project/code_v4")
FACTOR_DIR = ROOT / "data" / "parquet" / "factors" / "factor_name=reversal_20_vol_adj_weekly_cs"
FWD_DIR = ROOT / "data" / "parquet" / "factors" / "factor_name=fwd_returns"
PRICES_DIR = ROOT / "data" / "parquet" / "prices_adj"


def load_factor_data(years=range(2017, 2025)):
    """Load factor values for reversal_20_vol_adj_weekly_cs."""
    chunks = []
    for yr in years:
        yr_dir = FACTOR_DIR / f"year={yr}"
        for pq in sorted(yr_dir.glob("*.parquet")):
            df = pd.read_parquet(pq)
            df.columns = [str(c).strip().lower() for c in df.columns]
            df["ts_code"] = df["ts_code"].astype(str)
            df["trade_date"] = pd.to_numeric(df["trade_date"], errors="coerce")
            chunks.append(df)
    result = pd.concat(chunks, ignore_index=True)
    result = result.dropna(subset=["trade_date"])
    print(f"  Factor data: {len(result):,} rows, {result['ts_code'].nunique():,} stocks, "
          f"{result['trade_date'].nunique():,} dates")
    return result


def load_fwd_returns(start=20170224, end=20250101):
    """Load 5-day forward returns."""
    chunks = []
    for yr_dir in sorted(FWD_DIR.iterdir()):
        if not yr_dir.is_dir() or not yr_dir.name.startswith("year="):
            continue
        yr = int(yr_dir.name.split("=")[1])
        if yr < start // 10000 - 1 or yr > end // 10000 + 1:
            continue
        for month_dir in sorted(yr_dir.iterdir()):
            if not month_dir.is_dir():
                continue
            for pq in month_dir.glob("*.parquet"):
                df = pd.read_parquet(pq)
                df.columns = [str(c).strip().lower() for c in df.columns]
                df["ts_code"] = df["ts_code"].astype(str)
                df["trade_date"] = pd.to_numeric(df["trade_date"], errors="coerce")
                df = df.dropna(subset=["trade_date"])
                df = df[(df["trade_date"] >= start) & (df["trade_date"] <= end)]
                if not df.empty:
                    # Keep only fwd_ret_5d
                    keep = ["ts_code", "trade_date"]
                    for c in df.columns:
                        if "5" in c or "fwd" in c:
                            keep.append(c)
                    chunks.append(df[keep])
    if not chunks:
        return pd.DataFrame()
    result = pd.concat(chunks, ignore_index=True)
    result = result.drop_duplicates(["ts_code", "trade_date"])
    fwd_col = [c for c in result.columns if "5" in c][0]
    print(f"  Fwd returns: {len(result):,} rows, forward_col={fwd_col}")
    return result, fwd_col


def compute_momentum_features(prices_df):
    """
    prices_df: columns [ts_code, trade_date, adj_close]
    Returns per-stock: mom_5d, mom_20d, vol_5d, vol_20d, tail_risk
    Computed at signal_date using data up to and including signal_date.
    """
    prices = prices_df.sort_values(["ts_code", "trade_date"]).copy()
    prices["trade_date_dt"] = pd.to_datetime(prices["trade_date"], format="%Y%m%d")

    # Daily log return
    prices["ret_1d"] = prices.groupby("ts_code")["adj_close"].transform(
        lambda x: np.log(x / x.shift(1))
    )

    # Momentum: cumulative log return over lookback
    prices["mom_5d"] = prices.groupby("ts_code")["ret_1d"].transform(
        lambda x: x.rolling(5, min_periods=3).sum()
    )
    prices["mom_20d"] = prices.groupby("ts_code")["ret_1d"].transform(
        lambda x: x.rolling(20, min_periods=10).sum()
    )

    # Volatility: rolling std of daily returns
    prices["vol_5d"] = prices.groupby("ts_code")["ret_1d"].transform(
        lambda x: x.rolling(5, min_periods=3).std()
    )
    prices["vol_20d"] = prices.groupby("ts_code")["ret_1d"].transform(
        lambda x: x.rolling(20, min_periods=10).std()
    )

    # Tail risk: 20d cumulative return < -30%
    prices["tail_risk"] = prices["mom_20d"] < np.log(0.70)  # -30% ≈ log(0.70)

    # Filter columns
    out = prices[["ts_code", "trade_date", "mom_5d", "mom_20d", "vol_5d", "vol_20d", "tail_risk"]].copy()
    return out


def load_prices_for_signal_dates(signal_dates, lookback_days=100):
    """Load price data covering signal dates plus lookback."""
    date_ints = sorted(set(signal_dates))
    min_date = date_ints[0]
    max_date = date_ints[-1]

    # Convert to datetime for lookback
    min_dt = pd.to_datetime(str(min_date), format="%Y%m%d") - pd.Timedelta(days=lookback_days)
    min_lookback = int(min_dt.strftime("%Y%m%d"))

    chunks = []
    for yr_dir in sorted(PRICES_DIR.iterdir()):
        if not yr_dir.is_dir() or not yr_dir.name.startswith("year="):
            continue
        yr = int(yr_dir.name.split("=")[1])
        if yr < min_lookback // 10000 or yr > max_date // 10000 + 1:
            continue
        for month_dir in sorted(yr_dir.iterdir()):
            if not month_dir.is_dir():
                continue
            for pq in month_dir.glob("*.parquet"):
                df = pd.read_parquet(pq)
                df.columns = [str(c).strip().lower() for c in df.columns]
                df["ts_code"] = df["ts_code"].astype(str)
                df["trade_date"] = pd.to_numeric(df["trade_date"], errors="coerce")
                df = df.dropna(subset=["trade_date"])
                df = df[(df["trade_date"] >= min_lookback) & (df["trade_date"] <= max_date)]
                if not df.empty:
                    # Keep ts_code, trade_date, adj_close
                    keep_cols = ["ts_code", "trade_date"]
                    for c in df.columns:
                        if "close" in c.lower() or "adj" in c.lower():
                            keep_cols.append(c)
                            break
                    chunks.append(df[keep_cols])
    if not chunks:
        raise RuntimeError("No price data found")
    result = pd.concat(chunks, ignore_index=True)
    result = result.drop_duplicates(["ts_code", "trade_date"])
    close_col = [c for c in result.columns if "close" in c.lower()][0]
    result = result.rename(columns={close_col: "adj_close"})
    print(f"  Prices loaded: {len(result):,} rows, {result['ts_code'].nunique():,} stocks, "
          f"{result['trade_date'].nunique():,} dates")
    return result


def compute_filters(mom_features):
    """Compute three binary filter masks."""
    # Filter 1: Momentum deceleration (5d > 20d means short-term > long-term, i.e. slowing decline)
    mom_decel = mom_features["mom_5d"] > mom_features["mom_20d"]

    # Filter 2: Volatility contraction
    vol_contract = mom_features["vol_5d"] < mom_features["vol_20d"]

    # Filter 3: Tail risk exclusion (NOT tail risk)
    not_tail = ~mom_features["tail_risk"]

    return pd.DataFrame({
        "filter_mom_decel": mom_decel,
        "filter_vol_contract": vol_contract,
        "filter_not_tail": not_tail,
    })


def main():
    print("=" * 70)
    print("DIAGNOSTIC: A/B Classification Quality & Filter Effectiveness")
    print("Factor: reversal_20_vol_adj_weekly_cs")
    print("=" * 70)

    # 1. Load factor data
    print("\n[1/5] Loading factor data...")
    factor = load_factor_data()
    signal_dates = factor["trade_date"].unique()
    print(f"  Signal date range: {signal_dates.min()} ~ {signal_dates.max()}")

    # 2. Load forward returns
    print("\n[2/5] Loading forward returns...")
    fwd, fwd_col = load_fwd_returns()

    # 3. Load prices and compute momentum/vol features
    print("\n[3/5] Loading prices & computing features...")
    prices = load_prices_for_signal_dates(signal_dates)
    print("  Computing momentum/volatility features...")
    mom_features = compute_momentum_features(prices)
    print(f"  Features: {len(mom_features):,} rows")

    # 4. Merge factor + fwd_ret + features
    print("\n[4/5] Merging datasets...")
    merged = factor.merge(fwd, on=["ts_code", "trade_date"], how="inner")
    print(f"  After factor+fwd merge: {len(merged):,} rows")
    merged = merged.merge(mom_features, on=["ts_code", "trade_date"], how="left")
    # Drop rows where we don't have features (early dates before lookback)
    before = len(merged)
    merged = merged.dropna(subset=["mom_5d", "mom_20d", "vol_5d", "vol_20d"])
    print(f"  After feature merge (dropna): {len(merged):,} rows (dropped {before - len(merged):,})")

    factor_col = "value"
    merged = merged.rename(columns={fwd_col: "fwd_ret_5d", factor_col: "factor_value"})

    # 5. Classify A vs B
    print("\n[5/5] Classifying A/B and testing filters...")

    # For a reversal factor: high factor_value = expected to rebound (A if actually rebounds)
    # We look at the top quintile of factor (long candidates)
    merged["factor_quintile"] = merged.groupby("trade_date")["factor_value"].transform(
        lambda x: pd.qcut(x, 5, labels=False, duplicates="drop")
    )
    # Top quintile = 4
    top_q = merged[merged["factor_quintile"] == 4].copy()

    # A class: top quintile, fwd_ret > 0 (correctly identified rebound)
    # B class: top quintile, fwd_ret <= 0 (wrong, continued to fall)
    top_q["is_A"] = top_q["fwd_ret_5d"] > 0
    top_q["is_B"] = ~top_q["is_A"]

    # Compute filters for top quintile
    top_q["f1_mom_decel"] = top_q["mom_5d"] > top_q["mom_20d"]
    top_q["f2_vol_contract"] = top_q["vol_5d"] < top_q["vol_20d"]
    top_q["f3_not_tail"] = ~top_q["tail_risk"]

    # Combined filters
    top_q["f_any"] = top_q["f1_mom_decel"] | top_q["f2_vol_contract"] | top_q["f3_not_tail"]
    top_q["f_all"] = top_q["f1_mom_decel"] & top_q["f2_vol_contract"] & top_q["f3_not_tail"]

    # --- Section A: Overall A/B statistics ---
    print("\n" + "=" * 70)
    print("SECTION A: A/B Classification Baseline")
    print("=" * 70)

    total_top = len(top_q)
    n_A = top_q["is_A"].sum()
    n_B = top_q["is_B"].sum()

    print(f"\n  Top quintile samples: {total_top:,}")
    print(f"  A class (rebound, fwd_ret>0): {n_A:,} ({n_A/total_top*100:.1f}%)")
    print(f"  B class (continue down):      {n_B:,} ({n_B/total_top*100:.1f}%)")
    print(f"  A/B ratio: {n_A/n_B:.2f}")

    avg_A_ret = top_q[top_q["is_A"]]["fwd_ret_5d"].mean()
    avg_B_ret = top_q[top_q["is_B"]]["fwd_ret_5d"].mean()
    print(f"  Avg A fwd_ret: {avg_A_ret:.5f}")
    print(f"  Avg B fwd_ret: {avg_B_ret:.5f}")
    print(f"  Avg ALL top_q fwd_ret: {top_q['fwd_ret_5d'].mean():.5f}")

    # Breakdown by year
    print("\n  --- By year ---")
    top_q["year"] = top_q["trade_date"] // 10000
    yearly = top_q.groupby("year").agg(
        n_samples=("is_A", "count"),
        n_A=("is_A", "sum"),
        n_B=("is_B", "sum"),
        avg_fwd_ret=("fwd_ret_5d", "mean"),
        avg_A_ret=("fwd_ret_5d", lambda x: x[top_q.loc[x.index, "is_A"]].mean()),
        avg_B_ret=("fwd_ret_5d", lambda x: x[top_q.loc[x.index, "is_B"]].mean()),
    )
    yearly["pct_A"] = yearly["n_A"] / yearly["n_samples"] * 100
    yearly["ab_ratio"] = yearly["n_A"] / yearly["n_B"]
    print(yearly.to_string(float_format=lambda x: f"{x:.3f}"))

    # --- Section B: Filter Effectiveness ---
    print("\n" + "=" * 70)
    print("SECTION B: Individual Filter Effectiveness")
    print("=" * 70)

    filters = {
        "F1: mom_decel (5d>20d)": "f1_mom_decel",
        "F2: vol_contract (5d<20d)": "f2_vol_contract",
        "F3: not_tail (20d_ret>-30%)": "f3_not_tail",
    }

    for name, col in filters.items():
        pass_mask = top_q[col]
        fail_mask = ~top_q[col]

        n_pass = pass_mask.sum()
        n_fail = fail_mask.sum()

        a_rate_pass = top_q.loc[pass_mask, "is_A"].mean() if n_pass > 0 else 0
        a_rate_fail = top_q.loc[pass_mask, "is_A"].mean() if n_fail > 0 else 0  # intentional, but let me fix
        a_rate_fail = top_q.loc[fail_mask, "is_A"].mean() if n_fail > 0 else 0

        avg_ret_pass = top_q.loc[pass_mask, "fwd_ret_5d"].mean() if n_pass > 0 else 0
        avg_ret_fail = top_q.loc[fail_mask, "fwd_ret_5d"].mean() if n_fail > 0 else 0

        # Coverage: what % of top quintile passes
        coverage = n_pass / total_top * 100

        # Precision gain: how much A% improves when filter passes vs baseline
        baseline_a_rate = n_A / total_top
        precision_gain = (a_rate_pass - baseline_a_rate) / baseline_a_rate * 100

        print(f"\n  {name}")
        print(f"    Coverage:      {coverage:.1f}% ({n_pass:,}/{total_top:,})")
        print(f"    A-rate PASS:   {a_rate_pass*100:.1f}%  (baseline: {baseline_a_rate*100:.1f}%)")
        print(f"    A-rate FAIL:   {a_rate_fail*100:.1f}%")
        print(f"    Precision gain: {precision_gain:+.1f}%")
        print(f"    Avg ret PASS:  {avg_ret_pass:.5f}")
        print(f"    Avg ret FAIL:  {avg_ret_fail:.5f}")

    # --- Section C: Filter Combinations ---
    print("\n" + "=" * 70)
    print("SECTION C: Filter Combinations")
    print("=" * 70)

    combos = [
        ("F1 only (mom_decel)", top_q["f1_mom_decel"]),
        ("F2 only (vol_contract)", top_q["f2_vol_contract"]),
        ("F1 AND F2", top_q["f1_mom_decel"] & top_q["f2_vol_contract"]),
        ("F1 AND F2 AND F3", top_q["f1_mom_decel"] & top_q["f2_vol_contract"] & top_q["f3_not_tail"]),
        ("F1 OR F2", top_q["f1_mom_decel"] | top_q["f2_vol_contract"]),
    ]

    baseline_a_rate = n_A / total_top
    baseline_ret = top_q["fwd_ret_5d"].mean()

    for cname, cmask in combos:
        n_pass = cmask.sum()
        coverage = n_pass / total_top * 100
        a_rate = top_q.loc[cmask, "is_A"].mean() if n_pass > 0 else 0
        avg_ret = top_q.loc[cmask, "fwd_ret_5d"].mean() if n_pass > 0 else 0
        precision_gain = (a_rate - baseline_a_rate) / baseline_a_rate * 100
        ret_improve = avg_ret - baseline_ret

        # Also compute: what's the A-rate of the EXCLUDED samples (B class concentration)
        excluded = ~cmask
        n_excl = excluded.sum()
        a_rate_excl = top_q.loc[excluded, "is_A"].mean() if n_excl > 0 else 0

        print(f"\n  {cname}")
        print(f"    Coverage:        {coverage:.1f}% ({n_pass:,})")
        print(f"    A-rate (kept):   {a_rate*100:.1f}%  → precision +{precision_gain:+.1f}%")
        print(f"    A-rate (excl):   {a_rate_excl*100:.1f}%  (B class concentrated here)")
        print(f"    Avg ret (kept):  {avg_ret:.5f}  (Δ{ret_improve:+.5f} vs baseline)")

    # --- Section D: Simulated improvement ---
    print("\n" + "=" * 70)
    print("SECTION D: Simulated Gross Spread Improvement")
    print("=" * 70)

    # Simulate: apply filter to ALL data (not just top quintile), compute new top quintile returns
    # This means: we compute factor values, then mask B-class candidates to NaN, then re-rank
    merged["f1_mom_decel"] = merged["mom_5d"] > merged["mom_20d"]
    merged["f2_vol_contract"] = merged["vol_5d"] < merged["vol_20d"]
    merged["f3_not_tail"] = ~merged["tail_risk"]

    # Apply combined filter: F1 AND F2
    merged["filtered_factor"] = merged["factor_value"].where(
        merged["f1_mom_decel"] & merged["f2_vol_contract"],
        other=np.nan
    )

    # Re-rank on each date (only among passing stocks)
    def re_rank_quintile(grp):
        valid = grp["filtered_factor"].notna()
        if valid.sum() < 10:
            grp["filtered_quintile"] = np.nan
            return grp
        grp.loc[valid, "filtered_quintile"] = pd.qcut(
            grp.loc[valid, "filtered_factor"], 5, labels=False, duplicates="drop"
        )
        grp.loc[~valid, "filtered_quintile"] = np.nan
        return grp

    merged = merged.groupby("trade_date", group_keys=False).apply(re_rank_quintile)

    # Compute before/after by year
    print("\n  Comparison: ORIGINAL vs FILTERED (F1+F2) top quintile 5d returns\n")

    merged["year"] = merged["trade_date"] // 10000
    results = []
    for yr in range(2017, 2025):
        yr_data = merged[merged["year"] == yr]

        # Original top quintile
        orig_top = yr_data[yr_data["factor_quintile"] == 4]
        orig_ret = orig_top["fwd_ret_5d"].mean()

        # Filtered top quintile
        filt_top = yr_data[yr_data["filtered_quintile"] == 4]
        filt_ret = filt_top["fwd_ret_5d"].mean() if len(filt_top) > 0 else np.nan

        # Coverage
        orig_n = len(orig_top)
        filt_n = len(filt_top)
        cov = filt_n / orig_n * 100 if orig_n > 0 else 0

        results.append({
            "year": yr,
            "orig_ret": orig_ret,
            "filt_ret": filt_ret,
            "improvement": filt_ret - orig_ret if not np.isnan(filt_ret) else np.nan,
            "orig_n": orig_n,
            "filt_n": filt_n,
            "coverage_pct": cov,
        })

    res_df = pd.DataFrame(results)
    print(res_df.to_string(float_format=lambda x: f"{x:.5f}"))

    print(f"\n  Overall original top_q avg ret:  {merged[merged['factor_quintile']==4]['fwd_ret_5d'].mean():.5f}")
    print(f"  Overall filtered top_q avg ret:  {merged[merged['filtered_quintile']==4]['fwd_ret_5d'].mean():.5f}")

    # --- Section E: Recommendation ---
    print("\n" + "=" * 70)
    print("SECTION E: SUMMARY & RECOMMENDATION")
    print("=" * 70)
    # Will be filled after seeing results

    return merged, top_q, res_df


if __name__ == "__main__":
    merged, top_q, res_df = main()

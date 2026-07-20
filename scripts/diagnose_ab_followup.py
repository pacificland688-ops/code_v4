"""
Follow-up diagnostic: What actually distinguishes A from B in the top quintile?
Tests: signal strength, feature distributions, inverse filters, volume data.
"""
import pandas as pd
import numpy as np
from pathlib import Path

ROOT = Path("D:/workspace/q_project/code_v4")
FACTOR_DIR = ROOT / "data" / "parquet" / "factors" / "factor_name=reversal_20_vol_adj_weekly_cs"
FWD_DIR = ROOT / "data" / "parquet" / "factors" / "factor_name=fwd_returns"
PRICES_DIR = ROOT / "data" / "parquet" / "prices_adj"


def load_all_data():
    """Load factor, fwd returns, and prices with features."""
    # Factor
    chunks = []
    for yr in range(2017, 2025):
        for pq in sorted((FACTOR_DIR / f"year={yr}").glob("*.parquet")):
            df = pd.read_parquet(pq)
            df.columns = [str(c).strip().lower() for c in df.columns]
            df["ts_code"] = df["ts_code"].astype(str)
            df["trade_date"] = pd.to_numeric(df["trade_date"], errors="coerce")
            chunks.append(df)
    factor = pd.concat(chunks, ignore_index=True)

    # Fwd returns
    fwd_chunks = []
    for yr_dir in sorted(FWD_DIR.iterdir()):
        if not yr_dir.is_dir() or not yr_dir.name.startswith("year="):
            continue
        yr = int(yr_dir.name.split("=")[1])
        if yr < 2016 or yr > 2025:
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
                keep = ["ts_code", "trade_date", "fwd_ret_5d"]
                fwd_chunks.append(df[keep])
    fwd = pd.concat(fwd_chunks, ignore_index=True)
    fwd = fwd.drop_duplicates(["ts_code", "trade_date"])

    # Prices with features
    prices_chunks = []
    date_range = (factor["trade_date"].min(), factor["trade_date"].max())
    min_dt = pd.to_datetime(str(date_range[0]), format="%Y%m%d") - pd.Timedelta(days=100)
    min_lb = int(min_dt.strftime("%Y%m%d"))
    max_d = date_range[1]
    for yr_dir in sorted(PRICES_DIR.iterdir()):
        if not yr_dir.is_dir() or not yr_dir.name.startswith("year="):
            continue
        yr = int(yr_dir.name.split("=")[1])
        if yr < min_lb // 10000 or yr > max_d // 10000 + 1:
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
                df = df[(df["trade_date"] >= min_lb) & (df["trade_date"] <= max_d)]
                cols = ["ts_code", "trade_date"]
                for c in df.columns:
                    if "close" in c.lower():
                        cols.append(c)
                        break
                if not df.empty:
                    chunks.append(df[cols])
    prices = pd.concat(chunks, ignore_index=True)
    prices = prices.drop_duplicates(["ts_code", "trade_date"])
    close_c = [c for c in prices.columns if "close" in c.lower()][0]
    prices = prices.rename(columns={close_c: "adj_close"})
    prices = prices.sort_values(["ts_code", "trade_date"])

    # Compute features
    prices["ret_1d"] = prices.groupby("ts_code")["adj_close"].transform(
        lambda x: np.log(x / x.shift(1)))
    for w in [5, 10, 20]:
        prices[f"mom_{w}d"] = prices.groupby("ts_code")["ret_1d"].transform(
            lambda x, ww=w: x.rolling(ww, min_periods=max(3, ww//2)).sum())
        prices[f"vol_{w}d"] = prices.groupby("ts_code")["ret_1d"].transform(
            lambda x, ww=w: x.rolling(ww, min_periods=max(3, ww//2)).std())
    # Consecutive down days
    prices["down_day"] = prices["ret_1d"] < 0
    prices["consec_down"] = prices.groupby("ts_code")["down_day"].transform(
        lambda x: x.groupby((x != x.shift()).cumsum()).cumcount() + 1)
    prices.loc[~prices["down_day"], "consec_down"] = 0

    # Merge all
    merged = factor.merge(fwd, on=["ts_code", "trade_date"], how="inner")
    feat_cols = ["ts_code", "trade_date", "mom_5d", "mom_10d", "mom_20d",
                  "vol_5d", "vol_10d", "vol_20d", "consec_down"]
    merged = merged.merge(prices[feat_cols], on=["ts_code", "trade_date"], how="left")
    merged = merged.dropna(subset=["mom_5d"])

    # Quintile assignment
    merged["quintile"] = merged.groupby("trade_date")["value"].transform(
        lambda x: pd.qcut(x, 5, labels=False, duplicates="drop"))
    merged["year"] = merged["trade_date"] // 10000
    return merged


def main():
    print("=" * 70)
    print("FOLLOW-UP: What distinguishes A from B?")
    print("=" * 70)

    merged = load_all_data()
    top_q = merged[merged["quintile"] == 4].copy()
    top_q["is_A"] = top_q["fwd_ret_5d"] > 0
    top_q["is_B"] = ~top_q["is_A"]

    # ============================================================
    # Test 1: Signal strength within top quintile
    # ============================================================
    print("\n[Test 1] Signal strength gradient within top quintile")
    # Split top quintile into sub-groups by factor value rank
    top_q["factor_rank"] = top_q.groupby("trade_date")["value"].rank(pct=True)
    top_q["factor_tier"] = pd.cut(top_q["factor_rank"], bins=[0, 0.33, 0.67, 1.0],
                                   labels=["low", "mid", "high"])
    for tier in ["low", "mid", "high"]:
        tier_data = top_q[top_q["factor_tier"] == tier]
        a_rate = tier_data["is_A"].mean()
        avg_ret = tier_data["fwd_ret_5d"].mean()
        n = len(tier_data)
        print(f"  {tier:6s}: n={n:6,}  A-rate={a_rate*100:.1f}%  avg_ret={avg_ret:.5f}")

    # ============================================================
    # Test 2: Feature distribution A vs B
    # ============================================================
    print("\n[Test 2] Feature means: A class vs B class")
    features = ["mom_5d", "mom_10d", "mom_20d", "vol_5d", "vol_10d", "vol_20d",
                "consec_down", "value"]
    for feat in features:
        a_mean = top_q[top_q["is_A"]][feat].mean()
        b_mean = top_q[top_q["is_B"]][feat].mean()
        diff = a_mean - b_mean
        print(f"  {feat:15s}: A={a_mean:.5f}  B={b_mean:.5f}  Δ={diff:+.5f}")

    # ============================================================
    # Test 3: Inverse filters (the OPPOSITE of original hypothesis)
    # ============================================================
    print("\n[Test 3] INVERSE filters (capitulation hypothesis)")
    # Hypothesis: panic selling → reversal. Keep stocks with vol EXPANSION + sharp decline
    inv_filters = {
        "vol_expand (5d>20d)": top_q["vol_5d"] > top_q["vol_20d"],
        "sharp_drop (mom_5d<-5%)": top_q["mom_5d"] < -0.05,
        "consec_down>=3": top_q["consec_down"] >= 3,
        "vol_expand + sharp_drop": (top_q["vol_5d"] > top_q["vol_20d"]) & (top_q["mom_5d"] < -0.05),
        "vol_expand + consec_down>=3": (top_q["vol_5d"] > top_q["vol_20d"]) & (top_q["consec_down"] >= 3),
    }
    baseline = top_q["is_A"].mean()
    baseline_ret = top_q["fwd_ret_5d"].mean()
    for name, mask in inv_filters.items():
        n = mask.sum()
        cov = n / len(top_q) * 100
        a_rate = top_q.loc[mask, "is_A"].mean() if n > 0 else 0
        ret = top_q.loc[mask, "fwd_ret_5d"].mean() if n > 0 else 0
        gain = (a_rate - baseline) / baseline * 100
        print(f"  {name:30s}: cov={cov:5.1f}%  A-rate={a_rate*100:.1f}%  gain={gain:+.1f}%  ret={ret:.5f}")

    # ============================================================
    # Test 4: Sequential filtering (strongest signal first)
    # ============================================================
    print("\n[Test 4] Factor value decile analysis (tighten threshold)")
    top_q["decile"] = top_q.groupby("trade_date")["value"].transform(
        lambda x: pd.qcut(x, 10, labels=False, duplicates="drop"))
    for d in [9, 8, 7, 6, 5]:  # top decile, top 2 deciles, etc.
        d_data = top_q[top_q["decile"] >= d]
        a_rate = d_data["is_A"].mean()
        ret = d_data["fwd_ret_5d"].mean()
        cov = len(d_data) / len(top_q) * 100
        print(f"  top {10-d}0% (decile>={d}): cov={cov:.0f}%  A-rate={a_rate*100:.1f}%  ret={ret:.5f}  n={len(d_data):,}")

    # ============================================================
    # Test 5: Feature percentiles — find optimal thresholds
    # ============================================================
    print("\n[Test 5] Optimal threshold scan for key features")
    for feat in ["mom_5d", "mom_20d", "vol_5d", "vol_20d", "consec_down", "value"]:
        print(f"\n  --- {feat} ---")
        for pct in [10, 20, 30, 40, 50, 60, 70, 80, 90]:
            thresh = top_q[feat].quantile(pct / 100)
            # Keep ABOVE threshold
            above = top_q[top_q[feat] >= thresh]
            a_above = above["is_A"].mean() if len(above) > 0 else 0
            ret_above = above["fwd_ret_5d"].mean() if len(above) > 0 else 0
            # Keep BELOW threshold
            below = top_q[top_q[feat] <= thresh]
            a_below = below["is_A"].mean() if len(below) > 0 else 0
            ret_below = below["fwd_ret_5d"].mean() if len(below) > 0 else 0
            print(f"    p{pct:2d} (thresh={thresh:+.4f}): "
                  f"above A={a_above*100:.1f}% ret={ret_above:.5f} | "
                  f"below A={a_below*100:.1f}% ret={ret_below:.5f}")

    # ============================================================
    # Test 6: By-year filter effectiveness for best candidate
    # ============================================================
    print("\n[Test 6] Best filter candidate by year")
    # Use vol_expand + sharp_drop as it matches capitulation hypothesis
    best_mask = (top_q["vol_5d"] > top_q["vol_20d"]) & (top_q["mom_5d"] < -0.05)
    for yr in range(2017, 2025):
        yr_data = top_q[top_q["year"] == yr]
        yr_pass = yr_data[best_mask]
        yr_fail = yr_data[~best_mask]
        a_pass = yr_pass["is_A"].mean() if len(yr_pass) > 0 else 0
        a_fail = yr_fail["is_A"].mean() if len(yr_fail) > 0 else 0
        ret_pass = yr_pass["fwd_ret_5d"].mean() if len(yr_pass) > 0 else 0
        ret_fail = yr_fail["fwd_ret_5d"].mean() if len(yr_fail) > 0 else 0
        cov = len(yr_pass) / len(yr_data) * 100
        print(f"  {yr}: cov={cov:.0f}%  A_pass={a_pass*100:.1f}%  A_fail={a_fail*100:.1f}%  "
              f"ret_pass={ret_pass:.5f}  ret_fail={ret_fail:.5f}")

    # ============================================================
    # Test 7: Bottom quintile analysis (short side filter)
    # ============================================================
    print("\n[Test 7] Bottom quintile analysis (short side)")
    bot_q = merged[merged["quintile"] == 0].copy()
    # For bottom quintile: "good short" = fwd_ret < 0 (continues to fall)
    bot_q["is_good_short"] = bot_q["fwd_ret_5d"] < 0
    bot_baseline = bot_q["is_good_short"].mean()
    print(f"  Bottom quintile samples: {len(bot_q):,}")
    print(f"  Good short rate (fwd_ret<0): {bot_baseline*100:.1f}%")
    print(f"  Avg fwd_ret: {bot_q['fwd_ret_5d'].mean():.5f}")

    # Same filters for short side
    bot_q["vol_5d"] = bot_q.groupby("trade_date")["value"].transform(lambda x: x)  # placeholder, will use from merge
    # Actually we need the features on bot_q too
    # Let me just compute on merged directly
    merged_bot = merged[merged["quintile"] == 0].copy()
    merged_bot["is_good_short"] = merged_bot["fwd_ret_5d"] < 0
    baseline_short = merged_bot["is_good_short"].mean()
    print(f"  Baseline good-short rate: {baseline_short*100:.1f}%")

    short_filters = {
        "vol_expand": merged_bot["vol_5d"] > merged_bot["vol_20d"],
        "sharp_up (mom_5d>+5%)": merged_bot["mom_5d"] > 0.05,
        "consec_up>=3": merged_bot["consec_down"] == 0,  # not ideal but proxy
    }
    for name, mask in short_filters.items():
        n = mask.sum()
        gs_rate = merged_bot.loc[mask, "is_good_short"].mean() if n > 0 else 0
        ret = merged_bot.loc[mask, "fwd_ret_5d"].mean() if n > 0 else 0
        cov = n / len(merged_bot) * 100
        gain = (gs_rate - baseline_short) / baseline_short * 100
        print(f"  {name:25s}: cov={cov:.1f}%  good_short={gs_rate*100:.1f}%  gain={gain:+.1f}%  ret={ret:.5f}")

    print("\n" + "=" * 70)
    print("KEY FINDINGS")
    print("=" * 70)


if __name__ == "__main__":
    main()

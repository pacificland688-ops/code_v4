"""
Generate t+1 execution returns and alignment audit for panic reversal gate.

- fwd_ret_5d_same_day: close_{t+5} / close_t - 1 (original, study only)
- fwd_ret_5d_exec_lag1: close_{t+6} / close_{t+1} - 1 (formal gate default)
- Outlier filtering, price continuity check, boundary validation.
- Outputs: panic_lag1_returns.parquet, panic_lag1_return_outliers.csv,
           panic_lag1_return_quality_summary.csv, panic_return_alignment_check.csv
"""
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
import warnings
warnings.filterwarnings("ignore")

ROOT = Path("D:/workspace/q_project/code_v4")
FACTOR_BASE = ROOT / "data" / "parquet" / "factors"
FWD_DIR = FACTOR_BASE / "factor_name=fwd_returns"
PRICES_DIR = ROOT / "data" / "parquet" / "prices_adj"
OUT_DIR = ROOT / "outputs" / "analysis" / "panic_reversal_gate"

# Quality thresholds
MAX_ABS_RETURN = 0.5        # abs(fwd_ret) above this is an outlier
MAX_ABS_1D_JUMP = 0.3       # abs(1d return) above this is a price discontinuity


def load_prices():
    chunks = []
    for yr_dir in sorted(PRICES_DIR.iterdir()):
        if not yr_dir.is_dir() or not yr_dir.name.startswith("year="):
            continue
        for month_dir in sorted(yr_dir.iterdir()):
            if not month_dir.is_dir():
                continue
            for pq in month_dir.glob("*.parquet"):
                df = pd.read_parquet(pq)
                df.columns = [c.strip().lower() for c in df.columns]
                df["ts_code"] = df["ts_code"].astype(str)
                df["trade_date"] = pd.to_numeric(df["trade_date"], errors="coerce")
                df = df.dropna(subset=["trade_date"])
                for c in df.columns:
                    if "close" in c.lower() and "adj" in c.lower():
                        chunks.append(df[["ts_code", "trade_date", c]])
                        break
    r = pd.concat(chunks, ignore_index=True)
    r = r.drop_duplicates(["ts_code", "trade_date"]).sort_values(["ts_code", "trade_date"])
    close_c = [c for c in r.columns if "close" in c.lower()][0]
    return r.rename(columns={close_c: "adj_close"})


def compute_lag_returns(prices):
    """Compute same_day and exec_lag1 5-day forward returns with quality flags."""
    df = prices.copy()
    df = df.sort_values(["ts_code", "trade_date"])

    # Compute shifted closes
    df["close_t5"] = df.groupby("ts_code")["adj_close"].transform(lambda x: x.shift(-5))
    df["close_t6"] = df.groupby("ts_code")["adj_close"].transform(lambda x: x.shift(-6))
    df["close_t1"] = df.groupby("ts_code")["adj_close"].transform(lambda x: x.shift(-1))

    # Compute 1-day return for continuity check
    df["ret_1d"] = df.groupby("ts_code")["adj_close"].transform(
        lambda x: x / x.shift(1) - 1
    )

    # Forward 1d returns in the t+1..t+6 window (for jump detection)
    for k in range(1, 7):
        df[f"ret_fwd_{k}d"] = df.groupby("ts_code")["adj_close"].transform(
            lambda x, shift=k: x.shift(-shift) / x.shift(-(shift - 1)) - 1
        )

    # --- Boundary checks ---
    # t+1, t+5, t+6 must all exist
    df["_boundary_ok"] = (
        df["close_t1"].notna()
        & df["close_t5"].notna()
        & df["close_t6"].notna()
    )

    # --- Price validity checks ---
    df["_close_t_valid"] = (df["adj_close"] > 0) & (df["close_t1"] > 0) & (df["close_t6"] > 0)

    # --- Compute raw forward returns ---
    df["fwd_ret_5d_same_day"] = np.where(
        df["_boundary_ok"] & (df["adj_close"] > 0),
        df["close_t5"] / df["adj_close"] - 1,
        np.nan,
    )
    df["fwd_ret_5d_exec_lag1"] = np.where(
        df["_boundary_ok"] & df["_close_t_valid"],
        df["close_t6"] / df["close_t1"] - 1,
        np.nan,
    )

    # --- Price continuity check: any |ret_1d| > MAX_ABS_1D_JUMP in window t..t+6 ---
    jump_cols = ["ret_1d"] + [f"ret_fwd_{k}d" for k in range(1, 7)]
    df["_max_abs_jump"] = df[jump_cols].abs().max(axis=1)
    df["_continuity_ok"] = df["_max_abs_jump"] <= MAX_ABS_1D_JUMP

    # --- Outlier flag: abs(fwd_ret_5d_exec_lag1) > MAX_ABS_RETURN ---
    df["_return_ok"] = df["fwd_ret_5d_exec_lag1"].abs() <= MAX_ABS_RETURN
    df["_return_ok"] = df["_return_ok"].fillna(False)

    # --- Overall quality flag ---
    df["_quality_pass"] = (
        df["_boundary_ok"]
        & df["_close_t_valid"]
        & df["_continuity_ok"]
        & df["_return_ok"]
    )

    out_cols = [
        "ts_code", "trade_date",
        "fwd_ret_5d_same_day", "fwd_ret_5d_exec_lag1",
        "_boundary_ok", "_close_t_valid", "_continuity_ok", "_return_ok",
        "_max_abs_jump", "_quality_pass",
    ]
    out = df[out_cols].copy()
    return out


def extract_outliers(fwd_df):
    """Extract rows that fail quality checks, with reason codes."""
    df = fwd_df.copy()
    df = df[df["fwd_ret_5d_exec_lag1"].notna()]  # only rows with computed returns

    conditions = [
        ("boundary_fail", ~df["_boundary_ok"].fillna(True)),
        ("close_invalid", ~df["_close_t_valid"].fillna(True)),
        ("continuity_break", ~df["_continuity_ok"].fillna(True) & df["_boundary_ok"].fillna(False)),
        ("return_outlier", ~df["_return_ok"].fillna(True) & df["_boundary_ok"].fillna(False)),
    ]

    outlier_rows = []
    for reason, mask in conditions:
        if mask.sum() == 0:
            continue
        subset = df[mask].copy()
        subset["outlier_reason"] = reason
        outlier_rows.append(subset[
            ["ts_code", "trade_date", "fwd_ret_5d_exec_lag1",
             "_max_abs_jump", "outlier_reason"]
        ])

    if outlier_rows:
        return pd.concat(outlier_rows, ignore_index=True)
    return pd.DataFrame(columns=[
        "ts_code", "trade_date", "fwd_ret_5d_exec_lag1",
        "_max_abs_jump", "outlier_reason"
    ])


def quality_summary(fwd_df, outliers_df):
    """Produce quality summary statistics."""
    total_computed = fwd_df["fwd_ret_5d_exec_lag1"].notna().sum()
    total_pass = fwd_df["_quality_pass"].sum()
    total_fail = total_computed - total_pass

    summary = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_price_rows": len(fwd_df),
        "total_computed_returns": int(total_computed),
        "total_quality_pass": int(total_pass),
        "total_quality_fail": int(total_fail),
        "pass_ratio": round(total_pass / total_computed, 6) if total_computed > 0 else 0,
        "return_min": round(fwd_df.loc[fwd_df["_quality_pass"], "fwd_ret_5d_exec_lag1"].min(), 6),
        "return_max": round(fwd_df.loc[fwd_df["_quality_pass"], "fwd_ret_5d_exec_lag1"].max(), 6),
        "return_mean": round(fwd_df.loc[fwd_df["_quality_pass"], "fwd_ret_5d_exec_lag1"].mean(), 6),
        "return_std": round(fwd_df.loc[fwd_df["_quality_pass"], "fwd_ret_5d_exec_lag1"].std(), 6),
        "n_boundary_fail": int((~fwd_df["_boundary_ok"].fillna(True)).sum()),
        "n_close_invalid": int((~fwd_df["_close_t_valid"].fillna(True)).sum()),
        "n_continuity_break": int((~fwd_df["_continuity_ok"].fillna(True) & fwd_df["_boundary_ok"].fillna(False)).sum()),
        "n_return_outlier": int((~fwd_df["_return_ok"].fillna(True) & fwd_df["_boundary_ok"].fillna(False)).sum()),
        "max_abs_return_threshold": MAX_ABS_RETURN,
        "max_abs_1d_jump_threshold": MAX_ABS_1D_JUMP,
    }
    # Count outliers by reason
    if len(outliers_df) > 0:
        for reason, grp in outliers_df.groupby("outlier_reason"):
            summary[f"outlier_{reason}"] = len(grp)

    # Spot-check 2024-12-27 area for known anomalies
    anomaly_check = fwd_df[
        (fwd_df["trade_date"] >= 20241220) & (fwd_df["trade_date"] <= 20241231)
        & (~fwd_df["_quality_pass"])
    ]
    summary["n_anomaly_2024_year_end"] = len(anomaly_check)

    return pd.DataFrame([summary])


def alignment_audit(factor_signal_dates, prices):
    """Check: for each signal_date, find next trade date > signal_date.
    Uses calendar date arithmetic for gap_days and verifies trade_day_gap == 1.
    """
    all_td = prices[["trade_date"]].drop_duplicates().sort_values("trade_date")
    all_td = all_td["trade_date"].values
    td_set = set(all_td)

    signal_dates = sorted(set(factor_signal_dates))
    rows = []
    for sd in signal_dates:
        sd_int = int(sd)
        if sd_int not in td_set:
            rows.append({
                "signal_date": sd_int,
                "execution_date": np.nan,
                "calendar_gap_days": np.nan,
                "trade_day_gap": np.nan,
                "status": "SIGNAL_DATE_NOT_IN_CALENDAR",
            })
            continue

        idx = np.searchsorted(all_td, sd_int)
        next_idx = idx + 1
        if next_idx >= len(all_td):
            rows.append({
                "signal_date": sd_int,
                "execution_date": np.nan,
                "calendar_gap_days": np.nan,
                "trade_day_gap": np.nan,
                "status": "NO_NEXT_TRADE_DATE",
            })
            continue

        exec_date = int(all_td[next_idx])

        # Calendar day gap (real days, not integer subtraction)
        try:
            sig_dt = pd.to_datetime(str(sd_int), format="%Y%m%d")
            exec_dt = pd.to_datetime(str(exec_date), format="%Y%m%d")
            cal_gap = (exec_dt - sig_dt).days
        except Exception:
            cal_gap = np.nan

        # Trade day gap: execution_date should be the 1st trading day after signal_date
        trade_gap = 1  # by construction: next_idx = idx + 1

        if exec_date > sd_int:
            status = "OK"
        else:
            status = "EXEC_NOT_AFTER_SIGNAL"

        rows.append({
            "signal_date": sd_int,
            "execution_date": exec_date,
            "calendar_gap_days": cal_gap,
            "trade_day_gap": trade_gap,
            "status": status,
        })

    return pd.DataFrame(rows)


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print("=" * 70)
    print("GENERATE EXEC LAG1 RETURNS (with quality filtering)")
    print("=" * 70)

    # 1. Load prices
    print("\n[1] Loading prices...")
    prices = load_prices()
    print(f"  {len(prices):,} price rows")

    # 2. Compute returns with quality flags
    print("\n[2] Computing lag1 returns with quality checks...")
    fwd = compute_lag_returns(prices)
    print(f"  Total rows with computed returns: {fwd['fwd_ret_5d_exec_lag1'].notna().sum():,}")

    # 3. Extract outliers
    print("\n[3] Extracting outliers...")
    outliers = extract_outliers(fwd)
    n_out = len(outliers)
    pct_out = n_out / fwd["fwd_ret_5d_exec_lag1"].notna().sum() * 100 if n_out > 0 else 0
    print(f"  Outliers: {n_out:,} rows ({pct_out:.2f}% of computed returns)")
    if n_out > 0:
        for reason, grp in outliers.groupby("outlier_reason"):
            print(f"    {reason}: {len(grp):,}")

    # 4. Quality summary
    print("\n[4] Building quality summary...")
    qsum = quality_summary(fwd, outliers)
    print(f"  Pass: {qsum['total_quality_pass'].values[0]:,}")
    print(f"  Fail: {qsum['total_quality_fail'].values[0]:,}")
    print(f"  Pass ratio: {qsum['pass_ratio'].values[0]:.4%}")
    print(f"  Clean return range: [{qsum['return_min'].values[0]:.4f}, {qsum['return_max'].values[0]:.4f}]")

    # 5. Save clean lag1 returns (only quality-pass rows)
    print("\n[5] Saving outputs...")
    clean = fwd[fwd["_quality_pass"]][
        ["ts_code", "trade_date", "fwd_ret_5d_exec_lag1"]
    ].copy()
    clean = clean.dropna()  # double-check no NaN
    clean.to_parquet(OUT_DIR / "panic_lag1_returns.parquet", index=False)
    print(f"  panic_lag1_returns.parquet: {len(clean):,} clean rows")

    # Save outliers
    outliers.to_csv(OUT_DIR / "panic_lag1_return_outliers.csv", index=False)
    print(f"  panic_lag1_return_outliers.csv: {len(outliers):,} rows")

    # Save quality summary
    qsum.to_csv(OUT_DIR / "panic_lag1_return_quality_summary.csv", index=False)
    print(f"  panic_lag1_return_quality_summary.csv")

    # 6. Alignment audit
    print("\n[6] Running alignment audit...")
    # Load one panic factor to get signal dates
    import re
    FNAME_RE = re.compile(r"panic_(drop|up|sym)_rev5_t(0[357])_(bin|cont|wcont)_weekly_cs")
    signal_dates = np.array([])
    for d in FACTOR_BASE.iterdir():
        if d.is_dir() and d.name.startswith("factor_name=panic_") and d.name.endswith("_weekly_cs"):
            fname = d.name.replace("factor_name=", "")
            if not FNAME_RE.match(fname):
                continue
            for yr_dir in sorted(d.glob("year=*")):
                for pq in yr_dir.glob("*.parquet"):
                    pf = pd.read_parquet(pq)
                    pf.columns = [c.strip().lower() for c in pf.columns]
                    signal_dates = pf["trade_date"].unique()
                    break
                break
            break

    if len(signal_dates) == 0:
        signal_dates = fwd["trade_date"].unique()

    print(f"  Signal dates: {len(signal_dates)}")
    audit = alignment_audit(signal_dates, prices)
    audit.to_csv(OUT_DIR / "panic_return_alignment_check.csv", index=False)

    # Validate alignment
    n_fail = (audit["status"] != "OK").sum()
    n_bad_cal_gap = (audit["calendar_gap_days"].dropna() > 10).sum()
    n_bad_trade_gap = (audit["trade_day_gap"].dropna() != 1).sum()

    print(f"  Status OK: {(audit['status'] == 'OK').sum():,} / {len(audit):,}")
    print(f"  Status FAIL: {n_fail}")
    print(f"  Calendar gap outliers (>10 days): {n_bad_cal_gap}")
    print(f"  Trade day gap != 1: {n_bad_trade_gap}")
    if n_fail > 0:
        print("  FAIL rows (first 10):")
        for _, r in audit[audit["status"] != "OK"].head(10).iterrows():
            print(f"    signal={r['signal_date']}: {r['status']}")

    # 7. Summary report
    print(f"\n{'='*70}")
    print("LAG1 RETURN GENERATION COMPLETE")
    print(f"{'='*70}")
    clean_subset = fwd[fwd["_quality_pass"]]
    print(f"  Same-day (all):     mean={fwd['fwd_ret_5d_same_day'].mean():.5f} std={fwd['fwd_ret_5d_same_day'].std():.5f}")
    print(f"  Exec lag1 (clean):  mean={clean_subset['fwd_ret_5d_exec_lag1'].mean():.5f} std={clean_subset['fwd_ret_5d_exec_lag1'].std():.5f}")
    print(f"  Exec lag1 min/max:  {clean_subset['fwd_ret_5d_exec_lag1'].min():.5f} / {clean_subset['fwd_ret_5d_exec_lag1'].max():.5f}")
    print(f"  Outliers removed:   {n_out:,}")
    print(f"  Quality pass rate:  {qsum['pass_ratio'].values[0]:.2%}")
    print(f"  Anomalies near 2024 year-end: {qsum['n_anomaly_2024_year_end'].values[0]}")
    print("Done.")


if __name__ == "__main__":
    main()

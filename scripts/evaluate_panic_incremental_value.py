"""
Panic Reversal Incremental Value Assessment
============================================
Tests whether panic reversal factors provide value beyond baseline reversal_5_cs.

Methods:
  1. Residual IC: cross-sectional regression panic ~ baseline_factors, use residual
  2. Composite uplift: baseline vs baseline+panic rank IC / net_spread / hit_rate
  3. Event uplift (binary): within panic_event=True, does baseline explain returns?

Outputs:
  outputs/analysis/panic_reversal_gate/panic_incremental_value.csv
  outputs/analysis/panic_reversal_gate/panic_incremental_by_year.csv
"""
import pandas as pd
import numpy as np
from pathlib import Path
from scipy.stats import spearmanr
import re, sys, warnings
warnings.filterwarnings("ignore")

ROOT = Path("D:/workspace/q_project/code_v4")
FACTOR_BASE = ROOT / "data" / "parquet" / "factors"
LAG1_PATH = ROOT / "outputs/analysis/panic_reversal_gate/panic_lag1_returns.parquet"
OUT_DIR = ROOT / "outputs/analysis/panic_reversal_gate"
OUT_DIR.mkdir(parents=True, exist_ok=True)

FNAME_RE = re.compile(r"panic_(drop|up|sym)_rev5_t(0[357])_(bin|cont|wcont)_weekly_cs")
BASELINE_FACTORS = ["reversal_5_cs", "reversal_5_liquidity_adj_weekly_cs"]
COST = 20 / 10000


def load_factor(fname):
    d = FACTOR_BASE / f"factor_name={fname}"
    if not d.exists():
        return pd.DataFrame()
    chunks = []
    for yr_dir in sorted(d.glob("year=*")):
        if not yr_dir.is_dir():
            continue
        parquets = list(yr_dir.glob("*.parquet"))
        if not parquets:
            parquets = list(yr_dir.glob("month=*/*.parquet"))
        for pq in parquets:
            df = pd.read_parquet(pq)
            df.columns = [str(c).strip().lower() for c in df.columns]
            # Detect value column
            keep_cols = ["ts_code", "trade_date"]
            if "value" in df.columns:
                keep_cols.append("value")
            elif fname in df.columns:
                df = df.rename(columns={fname: "value"})
                keep_cols.append("value")
            else:
                other = [c for c in df.columns if c not in ("ts_code", "trade_date")]
                if other:
                    df = df.rename(columns={other[0]: "value"})
                    keep_cols.append("value")
            chunks.append(df[keep_cols])
    if not chunks:
        return pd.DataFrame()
    r = pd.concat(chunks, ignore_index=True)
    r["ts_code"] = r["ts_code"].astype(str)
    r["trade_date"] = pd.to_numeric(r["trade_date"], errors="coerce")
    return r.dropna(subset=["trade_date"])


def load_fwd():
    df = pd.read_parquet(LAG1_PATH)
    df["ts_code"] = df["ts_code"].astype(str)
    df["trade_date"] = pd.to_numeric(df["trade_date"], errors="coerce")
    return df[["ts_code", "trade_date", "fwd_ret_5d_exec_lag1"]].rename(
        columns={"fwd_ret_5d_exec_lag1": "fwd_ret_5d"})


def compute_ic(merged, value_col="value"):
    valid = merged.dropna(subset=[value_col, "fwd_ret_5d"])
    if len(valid) < 30:
        return {}
    def _ic(grp):
        m = grp[value_col].notna() & grp["fwd_ret_5d"].notna()
        return spearmanr(grp.loc[m, value_col], grp.loc[m, "fwd_ret_5d"])[0] if m.sum() >= 10 else np.nan
    ics = valid.groupby("trade_date").apply(_ic).dropna()
    if len(ics) < 10:
        return {}
    return {"mean_rank_ic": ics.mean(), "icir": ics.mean() / ics.std() if ics.std() > 0 else 0,
            "hit_rate": (ics > 0).mean(), "n_ic_dates": len(ics)}


def event_net_spread(merged, direction, sig_type):
    m = merged.dropna(subset=["value", "fwd_ret_5d"])
    if sig_type == "bin":
        if direction == "drop": ev = m["value"] > 0
        elif direction == "up": ev = m["value"] < 0
        else: ev = m["value"] != 0
    else:
        ev = m["value"] != 0
    if ev.sum() < 20:
        return np.nan
    ev_ret = m.loc[ev, "fwd_ret_5d"].mean()
    no_ret = m.loc[~ev, "fwd_ret_5d"].mean()
    if direction == "drop": spread = ev_ret - no_ret
    elif direction == "up": spread = no_ret - ev_ret
    else:
        dr = m.loc[m["value"] > 0, "fwd_ret_5d"].mean() if (m["value"] > 0).sum() >= 10 else np.nan
        ur = m.loc[m["value"] < 0, "fwd_ret_5d"].mean() if (m["value"] < 0).sum() >= 10 else np.nan
        spread = dr - ur
    er = ev.sum() / len(m)
    return spread - 2 * COST * er


# ===========================================================================
# Main
# ===========================================================================
print("=" * 70)
print("PANIC REVERSAL INCREMENTAL VALUE ASSESSMENT")
print("=" * 70)

print("\n[1] Loading data...", flush=True)
fwd = load_fwd()
print(f"  fwd: {len(fwd):,}")

# Load baseline factors
baseline = {}
for bf in BASELINE_FACTORS:
    bf_df = load_factor(bf)
    baseline[bf] = bf_df
    print(f"  {bf}: {'OK' if not bf_df.empty else 'MISSING'} ({len(bf_df):,})")
    if bf_df.empty:
        print(f"    WARNING: {bf} unavailable — incremental tests will be limited")

# Build combined baseline frame
bl_dfs = []
for bf, bdf in baseline.items():
    if bdf.empty: continue
    bl_dfs.append(bdf.rename(columns={"value": bf}))
if bl_dfs:
    bl_all = bl_dfs[0]
    for bdf in bl_dfs[1:]:
        bl_all = bl_all.merge(bdf, on=["ts_code", "trade_date"], how="outer")
else:
    bl_all = pd.DataFrame(columns=["ts_code", "trade_date"])
print(f"  Combined baseline: {len(bl_all):,} rows")

# Discover panic factors
panic_factors = sorted([
    d.name.replace("factor_name=", "") for d in FACTOR_BASE.iterdir()
    if d.is_dir() and d.name.startswith("factor_name=panic_")
    and d.name.endswith("_weekly_cs")
    and any(d.glob("year=*/part_*.parquet"))
])
print(f"\n[2] Evaluating {len(panic_factors)} panic factors...")

inc_rows = []
inc_yearly_rows = []

for pf in panic_factors:
    m = FNAME_RE.match(pf)
    if not m: continue
    info = {"direction": m.group(1), "threshold": int(m.group(2))/100.0, "signal_type": m.group(3)}
    pf_df = load_factor(pf)
    if pf_df.empty: continue

    # Merge with baseline and fwd
    merged = pf_df.merge(fwd, on=["ts_code", "trade_date"], how="inner")
    merged = merged.merge(bl_all, on=["ts_code", "trade_date"], how="left")

    # --- 1. Residual IC ---
    # Cross-sectional regression per date: panic_value ~ baseline_factors
    bl_cols = [c for c in BASELINE_FACTORS if c in merged.columns]
    if len(bl_cols) >= 1:
        merged_resid = merged.dropna(subset=["value", "fwd_ret_5d"] + bl_cols)
        residuals = []
        for td, g in merged_resid.groupby("trade_date"):
            if len(g) < 20: continue
            X = g[bl_cols].values
            y = g["value"].values
            try:
                # OLS: y = X·beta + resid
                beta = np.linalg.lstsq(X, y, rcond=None)[0]
                y_pred = X @ beta
                resid = y - y_pred
                residuals.append(pd.DataFrame({
                    "ts_code": g["ts_code"].values,
                    "trade_date": td,
                    "residual": resid,
                    "fwd_ret_5d": g["fwd_ret_5d"].values,
                    "value": y,
                }))
            except Exception:
                continue
        if residuals:
            resid_df = pd.concat(residuals, ignore_index=True)
            resid_df["residual"] = resid_df["residual"].astype(float)
            resid_df["fwd_ret_5d"] = resid_df["fwd_ret_5d"].astype(float)
            resid_ic = compute_ic(resid_df, value_col="residual")
            resid_for_ns = resid_df.drop(columns=["value"]).rename(columns={"residual": "value"})
            resid_ns = event_net_spread(resid_for_ns, info["direction"], info["signal_type"])
        else:
            resid_ic, resid_ns = {}, np.nan
    else:
        resid_ic, resid_ns = {}, np.nan

    # --- 2. Composite uplift ---
    # baseline IC (using first available baseline factor as proxy)
    bl_proxy = bl_cols[0] if bl_cols else None
    bl_ic = {}
    if bl_proxy and bl_proxy in merged.columns:
        bl_ic = compute_ic(merged.drop(columns=["value"]).rename(columns={bl_proxy: "value"}))
    pf_ic = compute_ic(merged)
    pf_ns = event_net_spread(merged, info["direction"], info["signal_type"])

    # --- 3. Yearly uplift ---
    merged["year"] = merged["trade_date"] // 10000
    pf_icir_rank = 0
    bl_icir_rank = 0
    uplift_years = 0
    n_years = 0
    for yr, g in merged.groupby("year"):
        if len(g) < 100: continue
        n_years += 1
        yr_pf_ic = compute_ic(g)
        yr_pf_icir = yr_pf_ic.get("icir", np.nan)
        yr_bl_icir = np.nan
        if bl_proxy and bl_proxy in g.columns:
            g_bl = g.drop(columns=["value"]).rename(columns={bl_proxy: "value"})
            yr_bl = compute_ic(g_bl)
            yr_bl_icir = yr_bl.get("icir", np.nan)
        yr_pf_ns = event_net_spread(g, info["direction"], info["signal_type"])

        # Residual IC per year
        yr_resid_icir = np.nan
        g_resid = g.dropna(subset=["value", "fwd_ret_5d"] + bl_cols)
        if len(g_resid) >= 100 and len(bl_cols) >= 1:
            X = g_resid[bl_cols].values
            y = g_resid["value"].values
            try:
                beta = np.linalg.lstsq(X, y, rcond=None)[0]
                resid = y - X @ beta
                g_resid["residual"] = resid
                yr_ric = compute_ic(g_resid, value_col="residual")
                yr_resid_icir = yr_ric.get("icir", np.nan)
            except Exception:
                pass

        icir_uplift = yr_pf_icir - yr_bl_icir if not (np.isnan(yr_pf_icir) or np.isnan(yr_bl_icir)) else np.nan
        if not np.isnan(icir_uplift) and icir_uplift > 0:
            uplift_years += 1
        if not np.isnan(yr_pf_icir): pf_icir_rank += 1 if yr_pf_icir > 0 else 0
        if not np.isnan(yr_bl_icir): bl_icir_rank += 1 if yr_bl_icir > 0 else 0

        inc_yearly_rows.append({
            "factor": pf, "year": yr,
            "panic_icir": yr_pf_icir,
            "baseline_icir": yr_bl_icir,
            "icir_uplift": icir_uplift,
            "panic_net_spread": yr_pf_ns,
            "residual_icir": yr_resid_icir,
        })

    resid_icir = resid_ic.get("icir", np.nan)
    icir_uplift_total = pf_ic.get("icir", np.nan) - bl_ic.get("icir", np.nan) if (not np.isnan(pf_ic.get("icir", np.nan)) and not np.isnan(bl_ic.get("icir", np.nan))) else np.nan

    # Judgment
    if len(bl_cols) == 0:
        verdict = "BASELINE_MISSING"
    elif not np.isnan(resid_icir) and resid_icir > 0 and uplift_years >= n_years * 0.5:
        verdict = "INCREMENTAL_PASS"
    elif not np.isnan(resid_icir) and resid_icir <= 0:
        verdict = "REDUNDANT_WITH_REVERSAL_5"
    else:
        verdict = "INCONCLUSIVE"

    inc_rows.append({
        "factor": pf, **info,
        "panic_icir": pf_ic.get("icir", np.nan),
        "baseline_icir": bl_ic.get("icir", np.nan),
        "icir_uplift": icir_uplift_total,
        "panic_net_spread": pf_ns,
        "residual_icir": resid_icir,
        "residual_ic": resid_ic.get("mean_rank_ic", np.nan),
        "residual_net_spread": resid_ns,
        "uplift_years": uplift_years,
        "n_years": n_years,
        "incremental_verdict": verdict,
    })
    print(f"  {pf}: resid_ICIR={resid_icir:.4f}" if not np.isnan(resid_icir) else f"  {pf}: resid_ICIR=N/A",
          f"uplift_yr={uplift_years}/{n_years} -> {verdict}", flush=True)

# Save
inc_df = pd.DataFrame(inc_rows)
inc_df.to_csv(OUT_DIR / "panic_incremental_value.csv", index=False)
inc_yr = pd.DataFrame(inc_yearly_rows)
inc_yr.to_csv(OUT_DIR / "panic_incremental_by_year.csv", index=False)
print(f"\nSaved: panic_incremental_value.csv ({len(inc_df)} rows)")
print(f"Saved: panic_incremental_by_year.csv ({len(inc_yr)} rows)")

print("\nDone.")

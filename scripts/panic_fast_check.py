"""Fast panic reversal diagnostic — verify signal direction fix.
Uses t+1 execution returns (exec_lag1) as default for formal gate.
Same-day returns loaded as study-only comparison.
"""
import pandas as pd, numpy as np
from pathlib import Path
from scipy.stats import spearmanr
import re, warnings
warnings.filterwarnings("ignore")

ROOT = Path("D:/workspace/q_project/code_v4")
BASE = ROOT / "data" / "parquet" / "factors"
FWD_DIR = BASE / "factor_name=fwd_returns"
LAG1_PATH = ROOT / "outputs/analysis/panic_reversal_gate/panic_lag1_returns.parquet"

FNAME_RE = re.compile(r"panic_(drop|up|sym)_rev5_t(0[357])_(bin|cont|wcont)_weekly_cs")
COST = 20/10000
EXEC_LAG = 1  # execution lag in days
FWD_COL = "fwd_ret_5d_exec_lag1"  # default: t+1 execution

def load_fwd():
    """Try lag1 first, fall back to same-day fwd_returns."""
    if LAG1_PATH.exists():
        df = pd.read_parquet(LAG1_PATH)
        df["ts_code"] = df["ts_code"].astype(str)
        df["trade_date"] = pd.to_numeric(df["trade_date"], errors="coerce")
        if FWD_COL in df.columns:
            print(f"  Using exec_lag1 returns ({LAG1_PATH})")
            return df[["ts_code", "trade_date", FWD_COL]].rename(columns={FWD_COL: "fwd_ret_5d"})
    # Fallback
    chunks = []
    for yr_dir in sorted(FWD_DIR.iterdir()):
        if not yr_dir.is_dir() or not yr_dir.name.startswith("year="): continue
        for month_dir in sorted(yr_dir.iterdir()):
            if not month_dir.is_dir(): continue
            for pq in month_dir.glob("*.parquet"):
                df = pd.read_parquet(pq)
                df.columns = [c.strip().lower() for c in df.columns]
                df["ts_code"] = df["ts_code"].astype(str)
                df["trade_date"] = pd.to_numeric(df["trade_date"], errors="coerce")
                df = df.dropna(subset=["trade_date"])
                if "fwd_ret_5d" in df.columns:
                    chunks.append(df[["ts_code", "trade_date", "fwd_ret_5d"]])
    print("  WARNING: using same-day returns (lag1 not available)")
    return pd.concat(chunks, ignore_index=True).drop_duplicates(["ts_code", "trade_date"])

def load_factor(fname):
    d = BASE / f"factor_name={fname}"
    if not d.exists(): return pd.DataFrame()
    chunks = []
    for yr_dir in sorted(d.glob("year=*")):
        if not yr_dir.is_dir(): continue
        for pq in yr_dir.glob("*.parquet"):
            df = pd.read_parquet(pq)
            df.columns = [c.strip().lower() for c in df.columns]
            chunks.append(df[["ts_code", "trade_date", "value"]])
    if not chunks: return pd.DataFrame()
    r = pd.concat(chunks, ignore_index=True)
    r["ts_code"] = r["ts_code"].astype(str)
    r["trade_date"] = pd.to_numeric(r["trade_date"], errors="coerce")
    return r.dropna(subset=["trade_date"])

def compute_ic(merged):
    valid = merged.dropna(subset=["value", "fwd_ret_5d"])
    if len(valid) < 30: return {}
    def _ic(grp):
        m = grp["value"].notna() & grp["fwd_ret_5d"].notna()
        return spearmanr(grp.loc[m, "value"], grp.loc[m, "fwd_ret_5d"])[0] if m.sum() >= 10 else np.nan
    ics = valid.groupby("trade_date").apply(_ic).dropna()
    if len(ics) < 10: return {}
    return {"mean_rank_ic": ics.mean(), "icir": ics.mean() / ics.std() if ics.std() > 0 else 0,
            "hit_rate": (ics > 0).mean(), "n_ic": len(ics)}

def event_spread(merged, direction, sig_type):
    """Event vs no-event spread, direction-aware."""
    m = merged.dropna(subset=["value", "fwd_ret_5d"])
    if sig_type == "bin":
        if direction == "drop": ev = m["value"] > 0
        elif direction == "up": ev = m["value"] < 0
        else: ev = m["value"] != 0
    else:
        ev = m["value"] != 0
    if ev.sum() < 20: return {}
    ev_ret = m.loc[ev, "fwd_ret_5d"].mean()
    no_ret = m.loc[~ev, "fwd_ret_5d"].mean()
    if direction == "drop": spread = ev_ret - no_ret
    elif direction == "up": spread = no_ret - ev_ret
    else:
        dr = m.loc[m["value"] > 0, "fwd_ret_5d"].mean() if (m["value"] > 0).sum() >= 10 else np.nan
        ur = m.loc[m["value"] < 0, "fwd_ret_5d"].mean() if (m["value"] < 0).sum() >= 10 else np.nan
        spread = dr - ur if not (np.isnan(dr) or np.isnan(ur)) else np.nan
    er = ev.sum() / len(m)
    return {"ev_spread": spread, "ev_net": spread - 2*COST*er, "ev_rate": er}

def val_pos_years(merged, direction, sig_type):
    """Count validation years with positive event net spread."""
    val = merged[merged["trade_date"] // 10000 >= 2021]
    if len(val) < 100: return 0, 4
    pos = 0
    years = sorted((val["trade_date"] // 10000).dropna().astype(int).unique())
    for yr in years:
        yd = val[val["trade_date"] // 10000 == yr]
        es = event_spread(yd, direction, sig_type)
        if es.get("ev_net", -999) > 0: pos += 1
    return pos, len(years)

print("Loading fwd returns...")
fwd = load_fwd()
print(f"  {len(fwd):,} rows")

# Discover panic factors
factors = sorted([d.name.replace("factor_name=", "") for d in BASE.iterdir()
                  if d.is_dir() and d.name.startswith("factor_name=panic_")
                  and d.name.endswith("_weekly_cs") and any(d.glob("year=*/part_*.parquet"))])
print(f"Found {len(factors)} factors")

results = []
for i, pf in enumerate(factors):
    m = FNAME_RE.match(pf)
    if not m: continue
    info = {"direction": m.group(1), "threshold": int(m.group(2))/100.0, "signal_type": m.group(3)}
    pf_df = load_factor(pf)
    merged = pf_df.merge(fwd, on=["ts_code", "trade_date"], how="inner")
    ic = compute_ic(merged)
    es = event_spread(merged, info["direction"], info["signal_type"])
    vpy, vny = val_pos_years(merged, info["direction"], info["signal_type"])
    results.append({**info, "factor": pf,
        "mean_rank_ic": ic.get("mean_rank_ic", np.nan),
        "icir": ic.get("icir", np.nan),
        "ev_spread": es.get("ev_spread", np.nan),
        "ev_net_spread": es.get("ev_net", np.nan),
        "ev_rate": es.get("ev_rate", np.nan),
        "val_pos_years": vpy, "val_n_years": vny,
    })
    print(f"[{i+1}/{len(factors)}] {pf}: IC={ic.get('mean_rank_ic', 0):.4f} "
          f"ICIR={ic.get('icir', 0):.3f} ev_net={es.get('ev_net', 0):.5f} "
          f"vpos={vpy}/{vny}")

df = pd.DataFrame(results)
# Fast check output goes to debug/, NEVER overwrites formal panic_variant_summary.csv
debug_dir = ROOT / "outputs/analysis/panic_reversal_gate/debug"
debug_dir.mkdir(parents=True, exist_ok=True)
df.to_csv(debug_dir / "panic_fast_check_summary.csv", index=False)
print(f"\nSaved to {debug_dir / 'panic_fast_check_summary.csv'}")

# Show winners
print("\n=== RESULTS BY SIGNAL TYPE ===")
for st in ["bin", "cont", "wcont"]:
    d = df[df["signal_type"] == st]
    print(f"\n{st}: avg_ICIR={d['icir'].mean():.3f}, pos_IC={ (d['mean_rank_ic'] > 0).sum()}/{len(d)}")

print("\n=== TOP CANDIDATES (ICIR > 0.1, ev_net > 0, val_pos >= 3) ===")
top = df[(df["icir"] > 0.1) & (df["ev_net_spread"] > 0) & (df["val_pos_years"] >= 3)]
for _, r in top.sort_values("icir", ascending=False).iterrows():
    print(f"  {r['factor']}: ICIR={r['icir']:.3f} ev_net={r['ev_net_spread']:.5f} vpos={int(r['val_pos_years'])}")

print(f"\nexecution_lag={EXEC_LAG}, fwd_col={FWD_COL}")
print("Done.")

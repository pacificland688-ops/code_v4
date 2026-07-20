"""
Walk-forward validation + frozen holdout + multiple testing check for panic reversal.

Per-window: select best candidate in train (frozen choice), evaluate on test only.
Outputs:
  panic_walkforward_candidates.csv              — all 27 candidates per window
  panic_walkforward_selected.csv                — per-window frozen choice
  panic_frozen_holdout.csv                      — train/val/holdout per candidate
  panic_multiple_testing_check.csv              — permutation summary + audit
  panic_multiple_testing_permutation_detail.csv — per-permutation detail
"""
import pandas as pd
import numpy as np
from pathlib import Path
from scipy.stats import spearmanr
import re, sys, warnings
warnings.filterwarnings("ignore")

ROOT = Path("D:/workspace/q_project/code_v4")
BASE = ROOT / "data" / "parquet" / "factors"
LAG1_PATH = ROOT / "outputs/analysis/panic_reversal_gate/panic_lag1_returns.parquet"
OUT_DIR = ROOT / "outputs/analysis/panic_reversal_gate"
OUT_DIR.mkdir(parents=True, exist_ok=True)

FNAME_RE = re.compile(r"panic_(drop|up|sym)_rev5_t(0[357])_(bin|cont|wcont)_weekly_cs")
COST = 20 / 10000
N_PERM = 500
QUICK_MODE = False
RANDOM_SEED = 42

if "--quick" in sys.argv:
    QUICK_MODE = True
    N_PERM = 10
    print(f"NOTE: Quick mode -- N_PERM={N_PERM}. Remove --quick for full N=500 run.")


def load_fwd():
    if not LAG1_PATH.exists():
        raise RuntimeError("lag1 returns not available")
    df = pd.read_parquet(LAG1_PATH)
    df["ts_code"] = df["ts_code"].astype(str)
    df["trade_date"] = pd.to_numeric(df["trade_date"], errors="coerce")
    fwd_col = "fwd_ret_5d_exec_lag1"
    if fwd_col not in df.columns:
        raise RuntimeError(f"Column '{fwd_col}' not in lag1 returns")
    return df[["ts_code", "trade_date", fwd_col]].rename(columns={fwd_col: "fwd_ret_5d"})


def load_factor(fname):
    d = BASE / f"factor_name={fname}"
    if not d.exists():
        return pd.DataFrame()
    chunks = []
    for yr_dir in sorted(d.glob("year=*")):
        if not yr_dir.is_dir():
            continue
        for pq in yr_dir.glob("*.parquet"):
            df = pd.read_parquet(pq)
            df.columns = [c.strip().lower() for c in df.columns]
            chunks.append(df[["ts_code", "trade_date", "value"]])
    if not chunks:
        return pd.DataFrame()
    r = pd.concat(chunks, ignore_index=True)
    r["ts_code"] = r["ts_code"].astype(str)
    r["trade_date"] = pd.to_numeric(r["trade_date"], errors="coerce")
    return r.dropna(subset=["trade_date"])


def compute_ic(merged):
    valid = merged.dropna(subset=["value", "fwd_ret_5d"])
    if len(valid) < 30:
        return {}
    def _ic(grp):
        m = grp["value"].notna() & grp["fwd_ret_5d"].notna()
        return spearmanr(grp.loc[m, "value"], grp.loc[m, "fwd_ret_5d"])[0] if m.sum() >= 10 else np.nan
    ics = valid.groupby("trade_date").apply(_ic).dropna()
    if len(ics) < 10:
        return {}
    return {"mean_rank_ic": ics.mean(), "icir": ics.mean() / ics.std() if ics.std() > 0 else 0}


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
# Load data
# ===========================================================================
print("Loading data...", flush=True)
fwd = load_fwd()
print(f"  fwd: {len(fwd):,}", flush=True)

factors = sorted([
    d.name.replace("factor_name=", "") for d in BASE.iterdir()
    if d.is_dir() and d.name.startswith("factor_name=panic_")
    and d.name.endswith("_weekly_cs") and any(d.glob("year=*/part_*.parquet"))
])
print(f"  factors: {len(factors)}")

all_data = {}
for pf in factors:
    m = FNAME_RE.match(pf)
    if not m: continue
    info = {"direction": m.group(1), "threshold": float(m.group(2))/100, "signal_type": m.group(3)}
    pf_df = load_factor(pf)
    if pf_df.empty: continue
    merged = pf_df.merge(fwd, on=["ts_code", "trade_date"], how="inner")
    all_data[pf] = {"info": info, "merged": merged}

# ===========================================================================
# 1. Frozen Holdout
# ===========================================================================
print("\n=== FROZEN HOLDOUT ===", flush=True)
holdout_rows = []
for pf, data in all_data.items():
    info, merged = data["info"], data["merged"]
    train = merged[merged["trade_date"] // 10000 <= 2020]
    val = merged[(merged["trade_date"]//10000 >= 2021) & (merged["trade_date"]//10000 <= 2022)]
    holdout = merged[merged["trade_date"] // 10000 >= 2023]
    t_ic = compute_ic(train)
    v_ns = event_net_spread(val, info["direction"], info["signal_type"])
    h_ns = event_net_spread(holdout, info["direction"], info["signal_type"])
    holdout_rows.append({
        "factor": pf, **info,
        "train_icir": t_ic.get("icir", np.nan),
        "val_net_spread": v_ns,
        "holdout_net_spread": h_ns,
        "holdout_pass": h_ns > 0 if not np.isnan(h_ns) else False,
    })

hd = pd.DataFrame(holdout_rows)
hd.to_csv(OUT_DIR / "panic_frozen_holdout.csv", index=False)
n_pass = hd["holdout_pass"].sum()
print(f"  Pass: {n_pass}/{len(hd)}")
for _, r in hd.nlargest(5, "holdout_net_spread").iterrows():
    print(f"    {r['factor']}: ICIR={r['train_icir']:.3f} holdout_ns={r['holdout_net_spread']:.5f}")

# ===========================================================================
# 2. Expanding Walk-Forward (Frozen Selection)
# ===========================================================================
print("\n=== EXPANDING WALK-FORWARD ===", flush=True)
windows = [(2017,2020,2021,2021),(2017,2021,2022,2022),(2017,2022,2023,2023),(2017,2023,2024,2024)]
candidate_rows, selected_rows = [], []

for tr_start, tr_end, ts_start, ts_end in windows:
    wname = f"train_{tr_start}_{tr_end}_test_{ts_start}_{ts_end}"
    wicirs = {}
    for pf, data in all_data.items():
        info, merged = data["info"], data["merged"]
        train = merged[(merged["trade_date"]//10000 >= tr_start) & (merged["trade_date"]//10000 <= tr_end)]
        test = merged[(merged["trade_date"]//10000 >= ts_start) & (merged["trade_date"]//10000 <= ts_end)]
        if len(train) < 100 or len(test) < 20: continue
        t_ic = compute_ic(train)
        t_icir = t_ic.get("icir", np.nan)
        t_ns = event_net_spread(train, info["direction"], info["signal_type"])
        ts_ns = event_net_spread(test, info["direction"], info["signal_type"])
        ts_er = (test["value"] != 0).mean() if len(test) > 0 else np.nan
        candidate_rows.append({
            "window": wname, "train_start": tr_start, "train_end": tr_end,
            "test_start": ts_start, "test_end": ts_end,
            "factor": pf, **info,
            "train_icir": t_icir, "train_net_spread": t_ns,
            "test_net_spread": ts_ns, "test_event_rate": ts_er,
        })
        wicirs[pf] = t_icir
    # Frozen selection
    if wicirs:
        valid = {k:v for k,v in wicirs.items() if not np.isnan(v)}
        best_pf = max(valid, key=valid.get) if valid else list(wicirs.keys())[0]
        bd = all_data[best_pf]; bi = bd["info"]; bm = bd["merged"]
        bt = bm[(bm["trade_date"]//10000 >= tr_start) & (bm["trade_date"]//10000 <= tr_end)]
        bts = bm[(bm["trade_date"]//10000 >= ts_start) & (bm["trade_date"]//10000 <= ts_end)]
        s_ns = event_net_spread(bts, bi["direction"], bi["signal_type"])
        s_ic = compute_ic(bts)
        selected_rows.append({
            "window": wname, "train_start": tr_start, "train_end": tr_end,
            "test_start": ts_start, "test_end": ts_end,
            "selected_factor": best_pf, "selection_metric": "train_icir",
            "train_icir": wicirs.get(best_pf, np.nan),
            "train_net_spread": event_net_spread(bt, bi["direction"], bi["signal_type"]),
            "test_net_spread": s_ns, "test_icir": s_ic.get("icir", np.nan),
            "test_event_rate": (bts["value"] != 0).mean() if len(bts) > 0 else np.nan,
            "test_pass": s_ns > 0 if not np.isnan(s_ns) else False,
        })

wf_candidates = pd.DataFrame(candidate_rows)
wf_selected = pd.DataFrame(selected_rows)
wf_candidates.to_csv(OUT_DIR / "panic_walkforward_candidates.csv", index=False)
wf_selected.to_csv(OUT_DIR / "panic_walkforward_selected.csv", index=False)
wf_all = pd.DataFrame(candidate_rows)
wf_all.to_csv(OUT_DIR / "panic_walkforward_validation.csv", index=False)

print(f"  Selected: {len(wf_selected)} windows")
for _, r in wf_selected.iterrows():
    print(f"    {r['window']}: {r['selected_factor']} test_ns={r['test_net_spread']:.5f} pass={r['test_pass']}")
sr = wf_selected["test_pass"].mean()
print(f"  Selected pass ratio: {wf_selected['test_pass'].sum()}/{len(wf_selected)} = {sr:.1%}", flush=True)

# ===========================================================================
# 3. Multiple Testing Check — CORRECTED SHUFFLE
# ===========================================================================
print(f"\n=== MULTIPLE TESTING (N={N_PERM}) ===", flush=True)

# Best real net_spread
best_real_ns = -999
best_real_pf = None
for pf, data in all_data.items():
    info, merged = data["info"], data["merged"]
    ns = event_net_spread(merged, info["direction"], info["signal_type"])
    if not np.isnan(ns) and ns > best_real_ns:
        best_real_ns = ns
        best_real_pf = pf
print(f"  Best real: {best_real_ns:.6f} ({best_real_pf})", flush=True)

# Build return universe from representative factor
rep_pf = list(all_data.keys())[0]
rep_merged = all_data[rep_pf]["merged"][["ts_code", "trade_date", "fwd_ret_5d"]].copy()
rep_merged["_key"] = rep_merged["ts_code"].astype(str) + "|" + rep_merged["trade_date"].astype(str)
key_to_rep_idx = {k: i for i, k in enumerate(rep_merged["_key"].values)}

# Group row positions by trade_date (integer positions into rep_merged)
td_positions = {}
for td, g in rep_merged.groupby("trade_date"):
    td_positions[td] = g.index.values.astype(int)
all_tds = sorted(td_positions.keys())

# Pre-compute per-factor: values + aligned indices into rep_merged
factor_data = {}
for pf, data in all_data.items():
    m = data["merged"][["ts_code", "trade_date", "value"]].copy()
    m["_key"] = m["ts_code"].astype(str) + "|" + m["trade_date"].astype(str)
    rep_indices = np.array([key_to_rep_idx.get(k, -1) for k in m["_key"].values])
    valid = rep_indices >= 0
    if valid.sum() < 50:
        continue
    factor_data[pf] = {
        "info": data["info"],
        "values": m["value"].values[valid],
        "rep_indices": rep_indices[valid],
    }

perm_details = []
perm_maxes = []
rng = np.random.RandomState(RANDOM_SEED)
shuf_arr = rep_merged["fwd_ret_5d"].values.copy()
orig_arr = shuf_arr.copy()
n_shuf_total = len(shuf_arr)
n_factors = len(factor_data)

print(f"  Rep: {rep_pf} ({n_shuf_total:,} rows, {len(all_tds)} dates, {n_factors} factors)", flush=True)
print(f"  Running {N_PERM} permutations...", flush=True)

for i in range(N_PERM):
    if i % max(1, N_PERM // 10) == 0:
        print(f"    perm {i}/{N_PERM}...", flush=True)

    # CORRECTED SHUFFLE: extract -> shuffle -> assign back
    # (numpy fancy-indexing returns a COPY, so rng.shuffle(shuf[idx]) is a no-op on the original)
    n_changed = 0
    for td in all_tds:
        idx_arr = td_positions[td]
        if len(idx_arr) > 1:
            vals = shuf_arr[idx_arr].copy()
            rng.shuffle(vals)
            shuf_arr[idx_arr] = vals
            n_changed += (vals != orig_arr[idx_arr]).sum()

    best_perm = -999
    best_perm_pf = None
    for pf, fd in factor_data.items():
        info = fd["info"]
        mapped = shuf_arr[fd["rep_indices"]]
        m2 = pd.DataFrame({"value": fd["values"], "fwd_ret_5d": mapped})
        ns = event_net_spread(m2, info["direction"], info["signal_type"])
        if not np.isnan(ns) and ns > best_perm:
            best_perm = ns
            best_perm_pf = pf
    perm_maxes.append(best_perm)
    perm_details.append({
        "perm_id": i,
        "best_perm_net_spread": best_perm,
        "best_perm_factor": best_perm_pf,
        "shuffle_changed_rows": int(n_changed),
    })

perm_maxes = np.array(perm_maxes)
p_value = (perm_maxes >= best_real_ns).mean()
unique_count = len(set(np.round(perm_maxes, 10)))
changed_arr = np.array([d["shuffle_changed_rows"] for d in perm_details])

# Audit
perm_status = "OK" if (unique_count > 1 and perm_maxes.std() > 0 and changed_arr.min() > 0) else "FAIL_CONSTANT_PERMUTATION"

print(f"  perm_max: mean={perm_maxes.mean():.6f} std={perm_maxes.std():.6f} "
      f"min={perm_maxes.min():.6f} max={perm_maxes.max():.6f} unique={unique_count}", flush=True)
print(f"  shuffle_changed: mean={changed_arr.mean():.0f} min={changed_arr.min():.0f}", flush=True)
print(f"  Real best={best_real_ns:.6f}, empirical p={p_value:.4f}", flush=True)
print(f"  permutation_status={perm_status}", flush=True)

mt_df = pd.DataFrame({
    "metric": ["best_real_net_spread", "perm_max_mean", "perm_max_std",
               "perm_max_min", "perm_max_max", "perm_max_unique_count",
               "perm_p95", "empirical_p_value", "n_candidates", "n_permutations",
               "shuffle_changed_rows_mean", "shuffle_changed_rows_min",
               "permutation_status", "random_seed"],
    "value": [best_real_ns, perm_maxes.mean(), perm_maxes.std(),
              perm_maxes.min(), perm_maxes.max(), unique_count,
              np.percentile(perm_maxes, 95), p_value, len(all_data), N_PERM,
              changed_arr.mean(), changed_arr.min(),
              perm_status, RANDOM_SEED],
})
mt_df.to_csv(OUT_DIR / "panic_multiple_testing_check.csv", index=False)
pd.DataFrame(perm_details).to_csv(
    OUT_DIR / "panic_multiple_testing_permutation_detail.csv", index=False)
print("  Saved panic_multiple_testing_check.csv + _permutation_detail.csv", flush=True)

if perm_status == "FAIL_CONSTANT_PERMUTATION":
    print("\n*** FATAL: Permutation produced constant results -- multiple_testing INVALID ***", flush=True)

print("\nDone.")

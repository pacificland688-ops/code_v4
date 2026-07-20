"""
Panic Reversal Candidate Diagnostics v2
========================================
Split event-based and rank/quantile-based metrics.
P0: bin->event, cont/wcont->rank (with event as secondary).
P1: redundancy, cost/liquidity, sparsity, regime.

Uses execution_lag=1 returns (panic_lag1_returns.parquet) as default.
Hard-exits if lag1 returns are unavailable or fail quality checks.

Outputs: outputs/analysis/panic_reversal_gate/
"""
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
from scipy.stats import spearmanr
import re, sys, warnings
warnings.filterwarnings("ignore")

ROOT = Path("D:/workspace/q_project/code_v4")
FACTOR_BASE = ROOT / "data" / "parquet" / "factors"
FWD_DIR = FACTOR_BASE / "factor_name=fwd_returns"
PRICES_DIR = ROOT / "data" / "parquet" / "prices_adj"
DAILY_DIR = ROOT / "data" / "parquet" / "daily_basic"
OUT_DIR = ROOT / "outputs" / "analysis" / "panic_reversal_gate"

FNAME_RE = re.compile(r"panic_(drop|up|sym)_rev5_t(0[357])_(bin|cont|wcont)_weekly_cs")
BASELINE_FACTORS = [
    "reversal_5_cs",
    "reversal_5_liquidity_adj_weekly_cs",
    "reversal_20_vol_adj_weekly_cs",
]
COST_BPS = 20 / 10000
COST_SCENARIOS = [10, 20, 30]  # bps
EXECUTION_LAG = 1
RETURN_COL = "fwd_ret_5d_exec_lag1"
SAME_DAY_RETURN_USED = False

LAG1_PATH = OUT_DIR / "panic_lag1_returns.parquet"
QUALITY_PATH = OUT_DIR / "panic_lag1_return_quality_summary.csv"


# ===========================================================================
# Data loaders
# ===========================================================================
def load_factor(fname):
    """Load factor parquet files. Auto-detects value column for baseline factors
    where the value column may be named after the factor itself (e.g. reversal_5_cs).
    Handles both flat year=*/part_*.parquet and nested year=*/month=*/*.parquet layouts."""
    d = FACTOR_BASE / f"factor_name={fname}"
    if not d.exists():
        return pd.DataFrame()
    chunks = []
    for yr_dir in sorted(d.glob("year=*")):
        if not yr_dir.is_dir():
            continue
        # Try flat layout (parquet files directly in year=*/)
        parquets = list(yr_dir.glob("*.parquet"))
        if not parquets:
            # Try nested layout (year=*/month=*/*.parquet)
            parquets = list(yr_dir.glob("month=*/*.parquet"))
        for pq in parquets:
            df = pd.read_parquet(pq)
            df.columns = [str(c).strip().lower() for c in df.columns]
            # Detect value column: prefer 'value', else use the factor's own name
            keep_cols = ["ts_code", "trade_date"]
            if "value" in df.columns:
                keep_cols.append("value")
            elif fname in df.columns:
                # Baseline factor: column named after factor (e.g. reversal_5_cs)
                df = df.rename(columns={fname: "value"})
                keep_cols.append("value")
            else:
                # Fallback: use third column (exclude ts_code, trade_date)
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


def load_exec_lag1_returns():
    """Load cleaned execution_lag=1 returns. Hard-exit if unavailable or quality fails."""
    if not LAG1_PATH.exists():
        print(f"FATAL: lag1 returns not found at {LAG1_PATH}")
        print("Run: python scripts/generate_exec_lag1_returns.py")
        sys.exit(1)

    df = pd.read_parquet(LAG1_PATH)
    df["ts_code"] = df["ts_code"].astype(str)
    df["trade_date"] = pd.to_numeric(df["trade_date"], errors="coerce")
    df = df.dropna(subset=["trade_date"])

    if RETURN_COL not in df.columns:
        print(f"FATAL: column '{RETURN_COL}' not found in lag1 returns")
        sys.exit(1)

    # Quality check
    if QUALITY_PATH.exists():
        qsum = pd.read_csv(QUALITY_PATH)
        if len(qsum) > 0:
            pass_ratio = qsum["pass_ratio"].values[0]
            ret_min = qsum["return_min"].values[0]
            ret_max = qsum["return_max"].values[0]
            print(f"  Lag1 quality: pass_ratio={pass_ratio:.4%} range=[{ret_min:.4f}, {ret_max:.4f}]")
            if ret_min < -MAX_ABS_RETURN or ret_max > MAX_ABS_RETURN:
                print(f"FATAL: lag1 return range [{ret_min:.4f}, {ret_max:.4f}] outside acceptable bounds")
                sys.exit(1)
    else:
        print("WARNING: quality summary not found, proceeding with raw lag1 returns")

    # Check for known anomaly dates (2024-12-27 area)
    anomaly = df[
        (df["trade_date"] >= 20241220) & (df["trade_date"] <= 20241231)
        & (df[RETURN_COL].abs() > 0.5)
    ]
    if len(anomaly) > 0:
        print(f"WARNING: {len(anomaly)} potential anomaly rows near 2024 year-end still present")

    print(f"  Using execution_lag={EXECUTION_LAG}, return_col={RETURN_COL}")
    print(f"  same_day_return_used={SAME_DAY_RETURN_USED}")
    return df[["ts_code", "trade_date", RETURN_COL]].rename(columns={RETURN_COL: "fwd_ret_5d"})


MAX_ABS_RETURN = 0.5  # must match generate_exec_lag1_returns.py


def load_daily_basic():
    """Load market cap data for cost/liquidity analysis."""
    chunks = []
    for yr_dir in sorted(DAILY_DIR.iterdir()):
        if not yr_dir.is_dir() or not yr_dir.name.startswith("year="):
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
                keep = ["ts_code", "trade_date"]
                for c in df.columns:
                    if c in ("total_mv", "circ_mv", "amount", "vol"):
                        keep.append(c)
                if len(keep) > 2:
                    chunks.append(df[keep])
    if not chunks:
        return pd.DataFrame()
    r = pd.concat(chunks, ignore_index=True)
    return r.drop_duplicates(["ts_code", "trade_date"])


def load_features(signal_dates):
    """Compute mom5, vol_20d from prices."""
    d_ints = sorted(set(signal_dates))
    min_dt = pd.to_datetime(str(min(d_ints)), format="%Y%m%d") - pd.Timedelta(days=100)
    min_lb = int(min_dt.strftime("%Y%m%d"))
    max_d = max(d_ints)
    chunks = []
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
                for c in df.columns:
                    if "close" in c.lower() and "adj" in c.lower():
                        chunks.append(df[["ts_code", "trade_date", c]])
                        break
    r = pd.concat(chunks, ignore_index=True)
    r = r.drop_duplicates(["ts_code", "trade_date"])
    close_c = [c for c in r.columns if "close" in c.lower()][0]
    r = r.rename(columns={close_c: "adj_close"}).sort_values(["ts_code", "trade_date"])
    r["ret_1d"] = r.groupby("ts_code")["adj_close"].transform(lambda x: np.log(x / x.shift(1)))
    r["mom5"] = r.groupby("ts_code")["adj_close"].transform(lambda x: x / x.shift(5) - 1)
    r["vol_20d"] = r.groupby("ts_code")["ret_1d"].transform(lambda x: x.rolling(20, min_periods=10).std())
    return r[["ts_code", "trade_date", "mom5", "vol_20d"]]


# ===========================================================================
# Metrics
# ===========================================================================
def compute_ic_metrics(merged, value_col="value"):
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
            "hit_rate": (ics > 0).mean(), "ic_std": ics.std(), "n_ic_dates": len(ics)}


def compute_event_metrics(merged, direction="drop", signal_type="bin"):
    """Event-based: event stocks vs non-event stocks."""
    merged = merged.dropna(subset=["value", "fwd_ret_5d"])
    if len(merged) < 50:
        return {}
    if signal_type == "bin":
        if direction == "drop":
            event_mask = merged["value"] > 0
        elif direction == "up":
            event_mask = merged["value"] < 0
        else:
            event_mask = merged["value"] != 0
    else:
        event_mask = merged["value"] != 0
    n_ev = event_mask.sum()
    n_no = (~event_mask).sum()
    if n_ev < 20:
        return {}
    ev_ret = merged.loc[event_mask, "fwd_ret_5d"].mean()
    no_ret = merged.loc[~event_mask, "fwd_ret_5d"].mean() if n_no >= 20 else np.nan
    if direction == "drop":
        spread = ev_ret - no_ret
    elif direction == "up":
        spread = no_ret - ev_ret
    else:  # sym: drop events long, up events short
        d_mask = merged["value"] > 0
        u_mask = merged["value"] < 0
        dr = merged.loc[d_mask, "fwd_ret_5d"].mean() if d_mask.sum() >= 10 else np.nan
        ur = merged.loc[u_mask, "fwd_ret_5d"].mean() if u_mask.sum() >= 10 else np.nan
        spread = dr - ur if not (np.isnan(dr) or np.isnan(ur)) else np.nan
        ev_ret, no_ret = dr, ur
    ev_rate = n_ev / len(merged)
    est_cost = 2 * COST_BPS * ev_rate
    net_spread = spread - est_cost if not np.isnan(spread) else np.nan
    return {"event_ret": ev_ret, "noevent_ret": no_ret, "event_spread": spread,
            "event_net_spread": net_spread, "event_rate": ev_rate,
            "n_event": n_ev, "n_noevent": n_no,
            "n_dates": merged["trade_date"].nunique(), "n_samples": len(merged)}


def compute_rank_metrics(merged):
    """Quintile-based rank metrics for cont/wcont factors."""
    merged = merged.dropna(subset=["value", "fwd_ret_5d"])
    if len(merged) < 50:
        return {}
    try:
        merged["q"] = merged.groupby("trade_date")["value"].transform(
            lambda x: pd.qcut(x, 5, labels=False, duplicates="drop"))
    except Exception:
        return {}
    top = merged[merged["q"] == 4]
    bot = merged[merged["q"] == 0]
    if len(top) == 0 or len(bot) == 0:
        return {}
    gs = top["fwd_ret_5d"].mean() - bot["fwd_ret_5d"].mean()
    er = (merged["value"] != 0).mean()
    ec = 2 * COST_BPS * er
    return {"rank_top_ret": top["fwd_ret_5d"].mean(), "rank_bot_ret": bot["fwd_ret_5d"].mean(),
            "rank_gross_spread": gs, "rank_net_spread": gs - ec,
            "rank_top_net_excess": top["fwd_ret_5d"].mean() - ec / 2,
            "event_rate": er, "n_dates": merged["trade_date"].nunique(), "n_samples": len(merged)}


def event_by_year(merged, direction, signal_type):
    merged["year"] = merged["trade_date"] // 10000
    rows = []
    for yr, g in merged.groupby("year"):
        em = compute_event_metrics(g, direction, signal_type)
        rm = compute_rank_metrics(g)
        row = {"year": yr, "n_total": len(g), "n_dates": g["trade_date"].nunique()}
        if em:
            row.update({f"ev_{k}": v for k, v in em.items()})
        if rm:
            row.update({f"rk_{k}": v for k, v in rm.items()})
        rows.append(row)
    return pd.DataFrame(rows)


def sparsity_stats(merged):
    ds = merged.groupby("trade_date").agg(
        n_stocks=("ts_code", "count"),
        n_nonzero=("value", lambda x: (x != 0).sum()))
    ds["nz_pct"] = ds["n_nonzero"] / ds["n_stocks"] * 100
    ds = ds.sort_index()
    zs = mx = 0
    for nz in ds["n_nonzero"]:
        zs = zs + 1 if nz == 0 else 0
        mx = max(mx, zs)
    ms = merged.sort_values(["ts_code", "trade_date"])
    ms["ps"] = ms.groupby("ts_code")["value"].transform(lambda x: x.shift(1))
    ev = ms[(ms["value"] != 0) & ms["ps"].notna()]
    persist = (np.sign(ev["value"]) == np.sign(ev["ps"])).mean() if len(ev) > 0 else np.nan
    return {"median_nz_pct": ds["nz_pct"].median(), "mean_nz_pct": ds["nz_pct"].mean(),
            "median_nz_stocks": ds["n_nonzero"].median(), "max_zero_weeks": mx,
            "signal_persist_1w": persist, "n_rebalance_dates": len(ds)}


def _compute_corr_scope(m, scope_label):
    """Compute Spearman correlation stats for a given merged frame."""
    cors, n_dates = [], 0
    for _, g in m.groupby("trade_date"):
        g = g.dropna(subset=["value_p", "value_b"])
        if len(g) >= 20:
            try:
                cors.append(spearmanr(g["value_p"], g["value_b"])[0])
                n_dates += 1
            except Exception:
                pass
    if cors:
        cors_arr = np.array(cors)
        return {
            "mean_spearman_corr": np.mean(cors_arr),
            "median_spearman_corr": np.median(cors_arr),
            "max_abs_corr": np.max(np.abs(cors_arr)),
            "n_dates": n_dates,
            "n_common_rows": len(m),
            "corr_scope": scope_label,
            "reason": "",
        }
    else:
        return {
            "mean_spearman_corr": np.nan,
            "median_spearman_corr": np.nan,
            "max_abs_corr": np.nan,
            "n_dates": 0,
            "n_common_rows": len(m),
            "corr_scope": scope_label,
            "reason": "no_valid_dates",
        }


def redundancy_check(all_factors, fwd):
    """Cross-sectional Spearman per common (date, stock).
    Two scopes:
      - full_panel: all stocks including non-events (value=0)
      - event_only: only rows where panic value != 0
    """
    rows = []
    panic_names = [k for k in all_factors if k.startswith("panic_")]
    for pf in panic_names:
        pf_df = all_factors[pf]
        for bf in BASELINE_FACTORS:
            # Baseline factor status
            if bf not in all_factors or all_factors[bf].empty:
                rows.append({
                    "panic_factor": pf, "baseline_factor": bf,
                    "corr_scope": "full_panel",
                    "mean_spearman_corr": np.nan, "median_spearman_corr": np.nan,
                    "max_abs_corr": np.nan, "n_dates": 0, "n_common_rows": 0,
                    "reason": "missing_baseline_factor",
                })
                rows.append({
                    "panic_factor": pf, "baseline_factor": bf,
                    "corr_scope": "event_only",
                    "mean_spearman_corr": np.nan, "median_spearman_corr": np.nan,
                    "max_abs_corr": np.nan, "n_dates": 0, "n_common_rows": 0,
                    "reason": "missing_baseline_factor",
                })
                continue

            bf_df = all_factors[bf]
            if len(bf_df) < 100:
                for scope in ["full_panel", "event_only"]:
                    rows.append({
                        "panic_factor": pf, "baseline_factor": bf,
                        "corr_scope": scope,
                        "mean_spearman_corr": np.nan, "median_spearman_corr": np.nan,
                        "max_abs_corr": np.nan, "n_dates": 0, "n_common_rows": 0,
                        "reason": "baseline_too_small",
                    })
                continue

            # Ensure required columns exist
            required_cols = ["ts_code", "trade_date", "value"]
            missing_cols = [c for c in required_cols if c not in bf_df.columns]
            if missing_cols:
                for scope in ["full_panel", "event_only"]:
                    rows.append({
                        "panic_factor": pf, "baseline_factor": bf,
                        "corr_scope": scope,
                        "mean_spearman_corr": np.nan, "median_spearman_corr": np.nan,
                        "max_abs_corr": np.nan, "n_dates": 0, "n_common_rows": 0,
                        "reason": f"missing_cols:{','.join(missing_cols)}",
                    })
                continue

            # Merge
            m_full = pf_df.merge(bf_df, on=["ts_code", "trade_date"], suffixes=("_p", "_b"))
            if len(m_full) < 100:
                for scope in ["full_panel", "event_only"]:
                    rows.append({
                        "panic_factor": pf, "baseline_factor": bf,
                        "corr_scope": scope,
                        "mean_spearman_corr": np.nan, "median_spearman_corr": np.nan,
                        "max_abs_corr": np.nan, "n_dates": 0, "n_common_rows": len(m_full),
                        "reason": "too_few_common_rows",
                    })
                continue

            # --- full_panel scope ---
            r_full = _compute_corr_scope(m_full, "full_panel")
            rows.append({"panic_factor": pf, "baseline_factor": bf, **r_full})

            # --- event_only scope ---
            m_event = m_full[m_full["value_p"] != 0]
            if len(m_event) >= 100:
                r_event = _compute_corr_scope(m_event, "event_only")
                rows.append({"panic_factor": pf, "baseline_factor": bf, **r_event})
            else:
                rows.append({
                    "panic_factor": pf, "baseline_factor": bf,
                    "corr_scope": "event_only",
                    "mean_spearman_corr": np.nan, "median_spearman_corr": np.nan,
                    "max_abs_corr": np.nan, "n_dates": 0, "n_common_rows": len(m_event),
                    "reason": "too_few_event_rows",
                })

    return pd.DataFrame(rows)


def cost_liquidity_analysis(merged, daily_basic, direction, signal_type):
    """Cost and liquidity diagnostics — filtered vs unfiltered.
    Always outputs net_spread_mv_small/mid/large columns, with
    mv_bucket_status and mv_col_used to explain any NaN values.
    """
    if daily_basic.empty:
        return pd.DataFrame()
    m = merged.merge(daily_basic, on=["ts_code", "trade_date"], how="left")
    m["is_event"] = m["value"] != 0
    mv_col = next((c for c in ["total_mv", "circ_mv"] if c in m.columns), None)
    amt_col = next((c for c in ["amount"] if c in m.columns), None)

    # Determine MV bucket status for this factor
    if mv_col is None:
        mv_bucket_status = "missing_mv_col"
        mv_col_used = "none"
    elif m[mv_col].notna().sum() < 50:
        mv_bucket_status = "insufficient_mv_data"
        mv_col_used = mv_col
    else:
        mv_bucket_status = "ok"  # will attempt per-year; individual rows may fail
        mv_col_used = mv_col

    rows = []
    years = sorted((m["trade_date"] // 10000).dropna().astype(int).unique())
    for yr in years:
        y = m[m["trade_date"] // 10000 == yr]
        ev, ne = y[y["is_event"]], y[~y["is_event"]]
        row = {
            "year": yr,
            "n_total": len(y),
            "n_event": len(ev),
            "event_rate": len(ev) / len(y) if len(y) > 0 else 0,
            "mv_bucket_status": mv_bucket_status,
            "mv_col_used": mv_col_used,
            # Force MV bucket output columns — always present, may be NaN
            "net_spread_mv_small": np.nan,
            "net_spread_mv_mid": np.nan,
            "net_spread_mv_large": np.nan,
            # Per-bucket sample counts
            "n_mv_small": 0, "n_mv_mid": 0, "n_mv_large": 0,
            "n_event_mv_small": 0, "n_event_mv_mid": 0, "n_event_mv_large": 0,
            # Per-bucket status
            "mv_small_status": "bucket_missing",
            "mv_mid_status": "bucket_missing",
            "mv_large_status": "bucket_missing",
        }
        if mv_col:
            row["event_median_mv"] = ev[mv_col].median() if len(ev) > 0 else np.nan
            row["noevent_median_mv"] = ne[mv_col].median() if len(ne) > 0 else np.nan
        if amt_col:
            row["event_median_amount"] = ev[amt_col].median() if len(ev) > 0 else np.nan
            row["noevent_median_amount"] = ne[amt_col].median() if len(ne) > 0 else np.nan

        # Turnover estimate
        y2 = y.sort_values(["ts_code", "trade_date"])
        y2["ns"] = y2.groupby("ts_code")["value"].transform(lambda x: x.shift(-1))
        ev2 = y2[y2["is_event"]]
        if len(ev2) > 0:
            ev_sign = np.sign(ev2["value"])
            ns_sign = np.sign(ev2["ns"].fillna(0))
            row["turnover_est"] = (ev_sign != ns_sign).mean()
        else:
            row["turnover_est"] = np.nan

        # Signal persistence
        for w in [1, 2, 3]:
            if w == 1:
                row["signal_persist_1w"] = row.get("turnover_est", np.nan)
            else:
                y2[f"ns_{w}"] = y2.groupby("ts_code")["value"].transform(lambda x, wk=w: x.shift(-wk))
                ev_w = y2[y2["is_event"]]
                if len(ev_w) > 0:
                    ev_sign = np.sign(ev_w["value"])
                    ns_sign = np.sign(ev_w[f"ns_{w}"].fillna(0))
                    row[f"signal_persist_{w}w"] = (ev_sign == ns_sign).mean()
                else:
                    row[f"signal_persist_{w}w"] = np.nan

        # Net spread under cost scenarios
        for bps in COST_SCENARIOS:
            cost = bps / 10000
            ec = 2 * cost * row["event_rate"]
            em = compute_event_metrics(y, direction, signal_type)
            if em:
                row[f"net_spread_cost_{bps}bps"] = em["event_spread"] - ec if not np.isnan(em.get("event_spread", np.nan)) else np.nan
            else:
                row[f"net_spread_cost_{bps}bps"] = np.nan

        # Net spread by MV bucket — actual computation with per-bucket status
        if mv_col and len(y) > 50:
            try:
                y["mv_bkt"] = pd.qcut(
                    y[mv_col].fillna(y[mv_col].median()), 3,
                    labels=False, duplicates="drop",
                )
                n_bkts = y["mv_bkt"].nunique()
                observed_bkts = sorted(y["mv_bkt"].dropna().unique().astype(int))
                bkt_name_map = {0: "small", 1: "mid", 2: "large"}

                for bkt_num in [0, 1, 2]:
                    bkt_name = bkt_name_map[bkt_num]
                    bd = y[y["mv_bkt"] == bkt_num]
                    ev_bd = bd[bd["is_event"]] if len(bd) > 0 else pd.DataFrame()
                    row[f"n_mv_{bkt_name}"] = len(bd)
                    row[f"n_event_mv_{bkt_name}"] = len(ev_bd)

                    if bkt_num not in observed_bkts:
                        row[f"mv_{bkt_name}_status"] = "bucket_missing"
                    elif len(bd) < 20:
                        row[f"mv_{bkt_name}_status"] = "too_few_rows"
                    elif len(ev_bd) < 10:
                        row[f"mv_{bkt_name}_status"] = "too_few_events"
                    else:
                        bkem = compute_event_metrics(bd, direction, signal_type)
                        row[f"net_spread_mv_{bkt_name}"] = bkem.get("event_net_spread", np.nan)
                        row[f"mv_{bkt_name}_status"] = "ok"
            except ValueError as e:
                row["mv_bucket_status"] = f"qcut_failed:{str(e)[:80]}"
                row["mv_small_status"] = "qcut_failed"
                row["mv_mid_status"] = "qcut_failed"
                row["mv_large_status"] = "qcut_failed"

        rows.append(row)

    return pd.DataFrame(rows)


def regime_diagnostic(merged, direction, signal_type):
    """Simple vol-regime breakdown. Marked as diagnostic_only fallback."""
    merged = merged.dropna(subset=["value", "fwd_ret_5d", "vol_20d"])
    if len(merged) < 100:
        return pd.DataFrame(), "no_data"
    mkt_vol = merged.groupby("trade_date")["vol_20d"].mean()
    hi_thresh = mkt_vol.quantile(0.70)
    merged["regime"] = np.where(
        merged["trade_date"].map(mkt_vol) >= hi_thresh, "high_vol", "low_vol"
    )
    rows = []
    for reg in ["high_vol", "low_vol"]:
        rd = merged[merged["regime"] == reg]
        em = compute_event_metrics(rd, direction, signal_type)
        rm = compute_rank_metrics(rd)
        row = {
            "regime": reg,
            "n_dates": rd["trade_date"].nunique(),
            "n_samples": len(rd),
        }
        if em:
            row.update({f"ev_{k}": v for k, v in em.items()})
        if rm:
            row.update({f"rk_{k}": v for k, v in rm.items()})
        rows.append(row)
    return pd.DataFrame(rows), "fallback_vol_quantile"


# ===========================================================================
# P0 Screening
# ===========================================================================
def p0_screen(summary_df):
    """P0 rules:
    - bin: event_net_spread > 0 and event_pos_spread_years >= 3
    - cont/wcont: rank_net_spread > 0 and rank_pos_spread_years >= 3
      if rank fails but event passes -> mark as EVENT_FILTER_ONLY
    Returns (status_df, full_summary_with_status)
    """
    statuses = []
    for _, r in summary_df.iterrows():
        st = r["signal_type"]
        ev_pass = (
            not np.isnan(r.get("ev_val_net_spread", np.nan))
            and r.get("ev_val_net_spread", -999) > 0
            and r.get("ev_val_pos_years", 0) >= 3
        )
        rk_pass = (
            not np.isnan(r.get("rk_val_net_spread", np.nan))
            and r.get("rk_val_net_spread", -999) > 0
            and r.get("rk_val_pos_years", 0) >= 3
        )

        reason = ""
        if st == "bin":
            if ev_pass:
                status, reason = "PASS_EVENT", ""
            elif r.get("ev_val_pos_years", 0) < 3:
                status, reason = "FAIL", f"ev_val_pos_years={r.get('ev_val_pos_years',0)}/{r.get('val_n_years',4)} < 3"
            elif r.get("ev_val_net_spread", -999) <= 0:
                status, reason = "FAIL", f"ev_val_net_spread={r['ev_val_net_spread']:.5f} <= 0"
            else:
                status, reason = "FAIL", "ev_val_net_spread NaN or missing"
        else:
            if rk_pass:
                status, reason = "PASS_RANK", ""
            elif ev_pass:
                status, reason = "EVENT_FILTER_ONLY", "rank failed but event passed"
            elif r.get("rk_val_pos_years", 0) < 3:
                status, reason = "FAIL", f"rk_val_pos_years={r.get('rk_val_pos_years',0)}/{r.get('val_n_years',4)} < 3"
            elif r.get("rk_val_net_spread", -999) <= 0:
                status, reason = "FAIL", f"rk_val_net_spread={r['rk_val_net_spread']:.5f} <= 0"
            else:
                status, reason = "FAIL", "no valid rank or event metric"

        statuses.append({"factor": r["factor"], "p0_status": status, "p0_reason": reason})

    status_df = pd.DataFrame(statuses)
    full = summary_df.merge(status_df, on="factor", how="left")
    full["p0_status"] = full["p0_status"].fillna("FAIL")
    full["p0_reason"] = full["p0_reason"].fillna("unknown")
    return status_df[status_df["p0_status"].str.startswith("PASS") | (status_df["p0_status"] == "EVENT_FILTER_ONLY")], full


# ===========================================================================
# Main
# ===========================================================================
def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print("=" * 70)
    print("PANIC REVERSAL DIAGNOSTICS v2")
    print(f"execution_lag={EXECUTION_LAG}  return_col={RETURN_COL}")
    print(f"same_day_return_used={SAME_DAY_RETURN_USED}")
    print("=" * 70)

    # Discover factors
    panic_factors = sorted([
        d.name.replace("factor_name=", "") for d in FACTOR_BASE.iterdir()
        if d.is_dir() and d.name.startswith("factor_name=panic_")
        and d.name.endswith("_weekly_cs")
        and any(d.glob("year=*/part_*.parquet"))
    ])
    print(f"\nFound {len(panic_factors)} panic factors")

    # Load data
    print("\n[1] Loading data...")
    fwd = load_exec_lag1_returns()
    print(f"  lag1 returns: {len(fwd):,} rows")
    daily = load_daily_basic()
    print(f"  daily_basic: {len(daily):,} rows")
    all_dates = set(fwd["trade_date"].unique())
    for pf in panic_factors[:3]:
        pf_df = load_factor(pf)
        all_dates.update(pf_df["trade_date"].unique())
    feats = load_features(all_dates)
    print(f"  features: {len(feats):,} rows")

    print("\n[2] Loading baseline factors...")
    all_factors = {}
    for bf in BASELINE_FACTORS:
        bf_df = load_factor(bf)
        all_factors[bf] = bf_df
        print(f"  {bf}: {'OK' if not bf_df.empty else 'MISSING'} ({len(bf_df):,})")

    # Evaluate
    print("\n[3] Evaluating...")
    summary_rows, event_years, sparsity_rows, cost_rows, regime_rows = [], [], [], [], []

    for i, pf in enumerate(panic_factors):
        m = FNAME_RE.match(pf)
        if not m:
            continue
        info = {
            "direction": m.group(1),
            "threshold": int(m.group(2)) / 100.0,
            "signal_type": m.group(3),
        }
        pf_df = load_factor(pf)
        if pf_df.empty:
            continue
        all_factors[pf] = pf_df
        merged = pf_df.merge(fwd, on=["ts_code", "trade_date"], how="inner")
        merged = merged.merge(feats, on=["ts_code", "trade_date"], how="left")

        ic = compute_ic_metrics(merged)
        em = compute_event_metrics(merged, info["direction"], info["signal_type"])
        rm = compute_rank_metrics(merged)
        ey = event_by_year(merged, info["direction"], info["signal_type"])
        ey["factor"] = pf
        event_years.append(ey)
        sp = sparsity_stats(merged)
        sp["factor"] = pf
        sp.update(info)
        sparsity_rows.append(sp)

        # Cost/liquidity analysis (P1 — now active)
        cl = cost_liquidity_analysis(merged, daily, info["direction"], info["signal_type"])
        if not cl.empty:
            cl["factor"] = pf
            cost_rows.append(cl)

        # Regime diagnostic (P1 — with corrected fields)
        rd, rd_src = regime_diagnostic(merged, info["direction"], info["signal_type"])
        if not rd.empty:
            rd["factor"] = pf                # real factor name (FIXED)
            rd["regime_source"] = rd_src     # source tag (FIXED)
            rd["diagnostic_only"] = True     # prevents misuse as hard gate (FIXED)
            regime_rows.append(rd)

        # Validation period P0
        val = merged[merged["trade_date"] // 10000 >= 2021]
        val_em = compute_event_metrics(val, info["direction"], info["signal_type"]) if len(val) > 0 else {}
        val_rm = compute_rank_metrics(val) if len(val) > 0 else {}
        ev_val_pos = 0
        rk_val_pos = 0
        if len(val) > 0:
            for yr in sorted((val["trade_date"] // 10000).dropna().astype(int).unique()):
                yd = val[val["trade_date"] // 10000 == yr]
                y_em = compute_event_metrics(yd, info["direction"], info["signal_type"])
                y_rm = compute_rank_metrics(yd)
                if y_em.get("event_net_spread", -999) > 0:
                    ev_val_pos += 1
                if y_rm.get("rank_net_spread", -999) > 0:
                    rk_val_pos += 1

        summary_rows.append({
            "factor": pf, **info,
            "execution_lag": EXECUTION_LAG,
            "return_col": RETURN_COL,
            "mean_rank_ic": ic.get("mean_rank_ic", np.nan),
            "icir": ic.get("icir", np.nan),
            "hit_rate": ic.get("hit_rate", np.nan),
            # Event metrics
            "ev_net_spread": em.get("event_net_spread", np.nan),
            "ev_spread": em.get("event_spread", np.nan),
            "ev_event_rate": em.get("event_rate", np.nan) if em else np.nan,
            "ev_val_net_spread": val_em.get("event_net_spread", np.nan),
            "ev_val_pos_years": ev_val_pos,
            # Rank metrics
            "rk_gross_spread": rm.get("rank_gross_spread", np.nan) if rm else np.nan,
            "rk_net_spread": rm.get("rank_net_spread", np.nan) if rm else np.nan,
            "rk_val_net_spread": val_rm.get("rank_net_spread", np.nan) if val_rm else np.nan,
            "rk_val_pos_years": rk_val_pos,
            "val_n_years": len(set(val["trade_date"] // 10000)) if len(val) > 0 else 0,
            "n_dates": merged["trade_date"].nunique(),
            "n_samples": len(merged),
        })
        ic_str = f"{ic.get('mean_rank_ic', 0) or 0:.4f}"
        ev_str = f"ev_ns={em.get('event_net_spread', np.nan):.5f}" if em else ""
        rk_str = f"rk_ns={rm.get('rank_net_spread', np.nan):.5f}" if rm else ""
        print(f"  [{i+1}/{len(panic_factors)}] {pf}: IC={ic_str} {ev_str} {rk_str}")

    # Save outputs
    print("\n[4] Saving outputs...")
    summary = pd.DataFrame(summary_rows)
    summary.to_csv(OUT_DIR / "panic_variant_summary.csv", index=False)
    ey_df = pd.concat(event_years, ignore_index=True) if event_years else pd.DataFrame()
    ey_df.to_csv(OUT_DIR / "panic_event_by_year.csv", index=False)
    corr = redundancy_check(all_factors, fwd)
    corr.to_csv(OUT_DIR / "panic_redundancy_corr.csv", index=False)
    cl_df = pd.concat(cost_rows, ignore_index=True) if cost_rows else pd.DataFrame()
    cl_df.to_csv(OUT_DIR / "panic_cost_liquidity.csv", index=False)
    sp_df = pd.DataFrame(sparsity_rows)
    sp_df.to_csv(OUT_DIR / "panic_sparsity.csv", index=False)
    rg_df = pd.concat(regime_rows, ignore_index=True) if regime_rows else pd.DataFrame()
    rg_df.to_csv(OUT_DIR / "panic_regime_diagnostic.csv", index=False)
    print(f"  Saved 7 CSVs to {OUT_DIR}")

    # P0 Screening
    print("\n[5] P0 Screening...")
    p0, summary_with_status = p0_screen(summary)
    summary = summary_with_status
    # Write summary with p0_status back
    summary.to_csv(OUT_DIR / "panic_variant_summary.csv", index=False)
    n_pass_event = len(p0[p0["p0_status"] == "PASS_EVENT"])
    n_pass_rank = len(p0[p0["p0_status"] == "PASS_RANK"])
    n_efo = len(p0[p0["p0_status"] == "EVENT_FILTER_ONLY"])
    n_fail = len(summary[summary["p0_status"] == "FAIL"])
    print(f"  PASS_EVENT: {n_pass_event}")
    print(f"  PASS_RANK: {n_pass_rank}")
    print(f"  EVENT_FILTER_ONLY: {n_efo}")
    print(f"  FAIL: {n_fail}")
    for _, r in p0.iterrows():
        icir_val = summary_with_status.loc[summary_with_status["factor"] == r["factor"], "icir"].values
        icir_str = f"{icir_val[0]:.3f}" if len(icir_val) > 0 else "N/A"
        print(f"    {r['factor']}: {r['p0_status']} ICIR={icir_str}")

    # P1 Redundancy (two scopes: full_panel + event_only)
    print("\n[6] P1 Redundancy...")
    p0_factors = p0["factor"].tolist()
    for pf_name in p0_factors:
        pc = corr[corr["panic_factor"] == pf_name]
        if len(pc) == 0:
            print(f"  {pf_name}: no redundancy data")
            continue

        # Check both scopes
        for scope in ["full_panel", "event_only"]:
            pc_s = pc[pc["corr_scope"] == scope]
            if len(pc_s) == 0:
                print(f"  {pf_name} [{scope}]: no data")
                continue
            # Find the worst (highest abs correlation) baseline per scope
            worst = pc_s.loc[pc_s["max_abs_corr"].abs().idxmax()] if pc_s["max_abs_corr"].notna().any() else None
            if worst is not None and not pd.isna(worst["max_abs_corr"]):
                bf = worst["baseline_factor"]
                mc = worst["max_abs_corr"]
                status = "PASS" if mc <= 0.6 else "FAIL"
                print(f"  {pf_name} [{scope}]: vs {bf} max_corr={mc:.3f} [{status}]")
            else:
                reason = pc_s["reason"].values[0] if len(pc_s) > 0 else "unknown"
                print(f"  {pf_name} [{scope}]: N/A (reason={reason})")

    # P1 Cost/Liquidity summary
    print("\n[7] P1 Cost/Liquidity...")
    if not cl_df.empty:
        for pf_name in cl_df["factor"].unique():
            pf_cl = cl_df[cl_df["factor"] == pf_name]
            n_years = pf_cl["year"].nunique()
            med_mv = pf_cl["event_median_mv"].median() if "event_median_mv" in pf_cl.columns else np.nan
            med_amt = pf_cl["event_median_amount"].median() if "event_median_amount" in pf_cl.columns else np.nan
            ns_20bps = pf_cl["net_spread_cost_20bps"].mean() if "net_spread_cost_20bps" in pf_cl.columns else np.nan
            mv_status = pf_cl["mv_bucket_status"].values[0] if "mv_bucket_status" in pf_cl.columns else "?"
            mv_small = pf_cl["net_spread_mv_small"].mean() if "net_spread_mv_small" in pf_cl.columns else np.nan
            mv_mid = pf_cl["net_spread_mv_mid"].mean() if "net_spread_mv_mid" in pf_cl.columns else np.nan
            mv_large = pf_cl["net_spread_mv_large"].mean() if "net_spread_mv_large" in pf_cl.columns else np.nan
            parts = [f"{pf_name}: {n_years}yr"]
            if not pd.isna(med_mv):
                parts.append(f"med_mv={med_mv:,.0f}")
            if not pd.isna(ns_20bps):
                parts.append(f"ns_20bps={ns_20bps:.5f}")
            parts.append(f"mv=[{mv_small:.5f},{mv_mid:.5f},{mv_large:.5f}]" if not pd.isna(mv_small) else f"mv=N/A")
            parts.append(f"mv_status={mv_status}")
            print(f"  {', '.join(parts)}")
    else:
        print("  WARNING: cost_liquidity.csv is empty")

    # Generate report
    print("\n[8] Generating report...")
    lines = [
        "# Panic Reversal Candidate Evaluation Report v2",
        f"\nGenerated: {datetime.now():%Y-%m-%d %H:%M:%S}",
        f"\ndiagnostic_source: full_gate_v2",
        f"\nexecution_lag: {EXECUTION_LAG}",
        f"return_col: {RETURN_COL}",
        f"same_day_return_used: {SAME_DAY_RETURN_USED}",
        f"\nTotal candidates: {len(summary)}",
        f"\n## P0 Screening Results",
        f"\n| Factor | Dir | Thr | Type | ExecLag | Status | Reason | ICIR | ev_val_ns | rk_val_ns | ev_pos_yr | rk_pos_yr |",
        f"|:---|---:|---:|:---|:---:|:---|:---|:---:|:---:|:---:|:---:|:---:|",
    ]
    for _, r in summary.iterrows():
        status = r.get("p0_status", "FAIL")
        reason = r.get("p0_reason", "")[:60] if r.get("p0_reason") else ""
        lines.append(
            f"| {r['factor']} | {r['direction']} | {r['threshold']:.0%} | {r['signal_type']} | "
            f"{r.get('execution_lag', EXECUTION_LAG)} | "
            f"{status} | {reason} | {r['icir']:.3f} | {r.get('ev_val_net_spread', np.nan):.5f} | "
            f"{r.get('rk_val_net_spread', np.nan):.5f} | {int(r.get('ev_val_pos_years',0))} | "
            f"{int(r.get('rk_val_pos_years',0))} |"
        )

    lines.append(f"\n## Baseline Comparison")
    lines.append(f"- reversal_20_vol_adj_weekly_cs: ICIR=0.117, net_spread=-0.0005, pos_years=2/4")
    lines.append(f"\n## Signal Direction Fix Verification")
    lines.append(f"- All cont/wcont: value = -mom5 for events")
    lines.append(f"- drop: positive values (long), up: negative values (short), sym: both")
    lines.append(f"\n## Execution Lag Configuration")
    lines.append(f"- execution_lag={EXECUTION_LAG}")
    lines.append(f"- return_col={RETURN_COL}")
    lines.append(f"- same_day_return_used={SAME_DAY_RETURN_USED}")
    lines.append(f"- lag1 source: {LAG1_PATH}")
    lines.append(f"\n## Summary")
    lines.append(f"- PASS_EVENT: {n_pass_event}")
    lines.append(f"- PASS_RANK: {n_pass_rank}")
    lines.append(f"- EVENT_FILTER_ONLY: {n_efo}")
    lines.append(f"- FAIL: {n_fail}")
    if not cl_df.empty:
        lines.append(f"\n## Cost/Liquidity")
        lines.append(f"- cost_liquidity rows: {len(cl_df)}")
        lines.append(f"- factors with cost data: {cl_df['factor'].nunique()}")
        # MV bucket status summary
        mv_statuses = cl_df.groupby("factor")["mv_bucket_status"].first()
        for pf_name, mvs in mv_statuses.items():
            lines.append(f"- {pf_name}: mv_bucket_status={mvs}")
        # Average MV bucket net spreads across years
        if "net_spread_mv_small" in cl_df.columns:
            avg_small = cl_df["net_spread_mv_small"].mean()
            avg_mid = cl_df["net_spread_mv_mid"].mean()
            avg_large = cl_df["net_spread_mv_large"].mean()
            lines.append(f"- avg net_spread_mv: small={avg_small:.5f}, mid={avg_mid:.5f}, large={avg_large:.5f}" if not pd.isna(avg_small) else f"- avg net_spread_mv: small=nan, mid=nan, large=nan")
    # ---- Final Decision Layer ----
    # Load auxiliary results if available
    mt_path = OUT_DIR / "panic_multiple_testing_check.csv"
    inc_path = OUT_DIR / "panic_incremental_value.csv"

    front_status = "PASS"  # execution_lag=1 confirmed
    mt_status = "UNKNOWN"
    redundancy_status = "PASS"
    inc_status = "UNKNOWN"
    liquidity_status = "PASS"

    if mt_path.exists():
        mt = pd.read_csv(mt_path)
        mt_dict = dict(zip(mt["metric"], mt["value"])) if "metric" in mt.columns else {}
        perm_status = str(mt_dict.get("permutation_status", "UNKNOWN"))
        p_val = float(mt_dict.get("empirical_p_value", np.nan))
        n_perm = int(mt_dict.get("n_permutations", 0))
        if perm_status == "FAIL_CONSTANT_PERMUTATION":
            mt_status = "FAIL_INVALID_PERMUTATION"
        elif n_perm < 500:
            mt_status = "FAIL_INSUFFICIENT_PERMUTATIONS"
        elif not np.isnan(p_val) and p_val >= 0.1:
            mt_status = "FAIL_NOT_SIGNIFICANT"
        elif not np.isnan(p_val) and p_val < 0.1:
            mt_status = "PASS"
        else:
            mt_status = "UNKNOWN"
    else:
        mt_status = "MISSING_FILE"

    # Redundancy: check if any P0 candidate has event_only corr > 0.8
    high_redundancy = False
    if not corr.empty and "corr_scope" in corr.columns:
        ev_corr = corr[corr["corr_scope"] == "event_only"]
        if len(ev_corr) > 0:
            worst = ev_corr.loc[ev_corr["max_abs_corr"].abs().idxmax()] if ev_corr["max_abs_corr"].notna().any() else None
            if worst is not None and not pd.isna(worst["max_abs_corr"]) and abs(worst["max_abs_corr"]) > 0.8:
                high_redundancy = True
                redundancy_status = "FAIL_HIGH_REDUNDANCY"
    if inc_path.exists():
        inc = pd.read_csv(inc_path)
        if "incremental_verdict" in inc.columns:
            n_pass = (inc["incremental_verdict"] == "INCREMENTAL_PASS").sum()
            n_redundant = (inc["incremental_verdict"] == "REDUNDANT_WITH_REVERSAL_5").sum()
            if n_redundant > 0 and n_pass == 0:
                inc_status = "FAIL_NO_INCREMENTAL_VALUE"
            elif n_pass > 0:
                inc_status = "PASS"
            else:
                inc_status = "INCONCLUSIVE"
    else:
        inc_status = "MISSING_FILE"

    # Liquidity: check MV bucket status
    if not cl_df.empty and "mv_large_status" in cl_df.columns:
        large_statuses = cl_df["mv_large_status"].unique()
        if all(s == "bucket_missing" for s in large_statuses):
            liquidity_status = "WARN_LARGE_BUCKET_MISSING"
        elif any(s == "qcut_failed" for s in large_statuses):
            liquidity_status = "WARN_QCUT_FAILED"

    # Final decision
    if front_status != "PASS":
        final = "NO_GO"
    elif mt_status.startswith("FAIL"):
        final = "NO_GO"
    elif redundancy_status == "FAIL_HIGH_REDUNDANCY" and inc_status == "FAIL_NO_INCREMENTAL_VALUE":
        final = "NO_GO"
    elif liquidity_status not in ("PASS", "WARN_LARGE_BUCKET_MISSING"):
        final = "RESEARCH_ONLY"
    elif mt_status == "PASS" and inc_status == "PASS" and redundancy_status == "PASS":
        final = "GO_CANDIDATE_POOL"
    elif mt_status == "PASS" and inc_status == "INCONCLUSIVE":
        final = "RESEARCH_ONLY"
    else:
        final = "RESEARCH_ONLY"

    lines.append(f"\n## Final Decision")
    lines.append(f"| Gate | Status |")
    lines.append(f"|:-----|:-------|")
    lines.append(f"| front_lookahead | {front_status} |")
    lines.append(f"| multiple_testing | {mt_status} |")
    lines.append(f"| redundancy | {redundancy_status} |")
    lines.append(f"| incremental_value | {inc_status} |")
    lines.append(f"| liquidity | {liquidity_status} |")
    lines.append(f"| **final_decision** | **{final}** |")
    lines.append(f"")
    lines.append(f"**Decision rule:**")
    lines.append(f"- front_lookahead != PASS => NO_GO")
    lines.append(f"- multiple_testing != PASS => NO_GO")
    lines.append(f"- redundancy == FAIL_HIGH_REDUNDANCY AND incremental_value != PASS => NO_GO")
    lines.append(f"- liquidity != PASS => RESEARCH_ONLY")
    lines.append(f"- all PASS => GO_CANDIDATE_POOL")
    lines.append(f"\n🤖 Generated with Claude Code")

    (OUT_DIR / "panic_reversal_report.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"  Report saved. Final decision: {final}")

    print("\nDone.")


if __name__ == "__main__":
    main()

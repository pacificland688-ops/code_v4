"""
Panic Reversal A/B/M Classification — ORACLE Evaluation (Phase 1)
=================================================================
THIS IS AN ORACLE (EX-POST) STUDY. A/B/M labels use future information
(fwd_ret_20d, new_low_20d, new_high_20d) that is NOT available at t0.
Action evaluations (A only / A+0.5M / exclude B) represent oracle upper
bounds — they show what IS possible, not what a live filter achieves.

Phase 2 (separate workstream) will use t0-available features to predict
A/B/M, followed by walk-forward validation of executable filters.

Design principles:
  - All metrics use exec_lag=1 reference (close_t1 entry, not close_t0).
  - value == 0 events → UNCLASSIFIED (excluded from A/B/M proportions).
  - Long and short sides have symmetric metric definitions.
  - Retention thresholds are scanned (0.2 / 0.3 / 0.5).
  - Acceptance criteria avoid tautologies (no "A has fewer new_low than B").

Inputs:
  - Panic factor parquet files (drop / up / sym × t05, bin/cont/wcont)
  - Price data (adjusted close, daily)
  - panic_lag1_returns.parquet (fwd_ret_5d_exec_lag1)

Outputs (→ outputs/analysis/panic_reversal_gate/):
  - panic_ab_label_summary.csv
  - panic_ab_by_year.csv
  - panic_ab_action_eval.csv
  - panic_ab_quality_diagnostics.csv
  - panic_ab_classification_report.md
"""
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
from scipy.stats import spearmanr
from numpy.lib.stride_tricks import sliding_window_view
import re, sys, warnings
warnings.filterwarnings("ignore")

ROOT = Path("D:/workspace/q_project/code_v4")
FACTOR_BASE = ROOT / "data" / "parquet" / "factors"
PRICES_DIR = ROOT / "data" / "parquet" / "prices_adj"
OUT_DIR = ROOT / "outputs" / "analysis" / "panic_reversal_gate"
LAG1_PATH = OUT_DIR / "panic_lag1_returns.parquet"

# ── config ─────────────────────────────────────────────────────────────
RETENTION_THRESHOLDS = [0.2, 0.3, 0.5]
FWD_WINDOW = 20                    # trading days for 20d horizon
FWD_WINDOW_5 = 5                   # trading days for 5d horizon
EXECUTION_LAG = 1                  # days from signal to entry
COST_BPS = 20 / 10000
MIN_STOCKS_PER_DATE = 5            # min stocks needed for cross-sectional ops
STUDY_YEARS = range(2017, 2026)    # evaluation window

# Primary factor variants to evaluate
PRIMARY_VARIANTS = [
    # (factor_name, direction)
    ("panic_drop_rev5_t05_bin_weekly_cs",   "drop"),
    ("panic_up_rev5_t05_bin_weekly_cs",     "up"),
    ("panic_sym_rev5_t05_bin_weekly_cs",    "sym"),
]

# ───────────────────────────────────────────────────────────────────────
# 1. DATA LOADING
# ───────────────────────────────────────────────────────────────────────

def load_prices():
    """Load adjusted close prices, sorted by ts_code, trade_date.

    Priority: adj_close > close_adj > any column containing both 'adj' and 'close'.
    Falls back to any column containing 'close' with a warning.
    """
    chunks = []
    for yr_dir in sorted(PRICES_DIR.iterdir()):
        if not yr_dir.is_dir() or not yr_dir.name.startswith("year="):
            continue
        yr = int(yr_dir.name.split("=")[1])
        if yr < 2014 or yr > 2027:
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
                # Prefer adj_close, fallback to any close column
                cols_lower = [c.lower() for c in df.columns]
                selected = None
                for candidate in df.columns:
                    cl = candidate.lower()
                    if cl == "adj_close":
                        selected = candidate
                        break
                if selected is None:
                    for candidate in df.columns:
                        cl = candidate.lower()
                        if "adj" in cl and "close" in cl:
                            selected = candidate
                            break
                if selected is None:
                    for candidate in df.columns:
                        cl = candidate.lower()
                        if "close" in cl:
                            selected = candidate
                            break
                if selected:
                    chunks.append(df[["ts_code", "trade_date", selected]])
    if not chunks:
        raise RuntimeError("No price data found")
    # Verify we're using adj_close
    sample_col = chunks[0].columns[2]
    if "adj" not in sample_col.lower():
        print(f"  WARNING: no adj_close column found, using '{sample_col}' as close price")
    r = pd.concat(chunks, ignore_index=True)
    r = r.drop_duplicates(["ts_code", "trade_date"])
    close_col = [c for c in r.columns if "close" in c.lower()][0]
    r = r.rename(columns={close_col: "adj_close"})
    r = r.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)
    print(f"  Prices: {len(r):,} rows, {r['ts_code'].nunique():,} stocks, "
          f"{r['trade_date'].nunique():,} dates")
    return r


def load_factor(factor_name):
    """Load a single panic factor variant."""
    d = FACTOR_BASE / f"factor_name={factor_name}"
    if not d.exists():
        print(f"  WARNING: {factor_name} not found at {d}")
        return pd.DataFrame()
    chunks = []
    for yr_dir in sorted(d.glob("year=*")):
        for pq in yr_dir.glob("*.parquet"):
            df = pd.read_parquet(pq)
            df.columns = [c.strip().lower() for c in df.columns]
            df["ts_code"] = df["ts_code"].astype(str)
            df["trade_date"] = pd.to_numeric(df["trade_date"], errors="coerce")
            keep = ["ts_code", "trade_date", "value"]
            chunks.append(df[keep])
    if not chunks:
        return pd.DataFrame()
    r = pd.concat(chunks, ignore_index=True)
    r = r.dropna(subset=["trade_date"])
    return r


def load_lag1_returns():
    """Load pre-computed exec_lag=1 5d returns."""
    if not LAG1_PATH.exists():
        print(f"  WARNING: lag1 returns not found at {LAG1_PATH}")
        return pd.DataFrame()
    df = pd.read_parquet(LAG1_PATH)
    df["ts_code"] = df["ts_code"].astype(str)
    df["trade_date"] = pd.to_numeric(df["trade_date"], errors="coerce")
    df = df.dropna(subset=["trade_date"])
    print(f"  Lag1 returns: {len(df):,} rows")
    return df


# ───────────────────────────────────────────────────────────────────────
# 2. FORWARD METRICS COMPUTATION (exec_lag=1 reference)
# ───────────────────────────────────────────────────────────────────────

def compute_forward_metrics(prices):
    """Compute all forward-looking metrics at every (ts_code, trade_date).

    All metrics are referenced to this trade_date as the POTENTIAL EXECUTION
    DATE (t1). They answer: "if we enter at close of this date, what happens
    over the next 5/20 trading days?"

    Drop-specific path metrics (v2):
      - future_min_1_5  = min(close_t1 ... close_t5)
      - future_min_6_20 = min(close_t6 ... close_t20)
      - early_new_low_1_5 = future_min_1_5 < entry_close
      - post_rebound_new_low_6_20 = future_min_6_20 <= entry_close
      - rough_repair = early_new_low AND fwd_ret_5d>0 AND fwd_ret_20d>0 AND NOT post_rebound_new_low
      - pullback_after_5 = future_min_6_20 / close_t5 - 1

    Returns DataFrame with all core + auxiliary columns.
    """
    df = prices.sort_values(["ts_code", "trade_date"]).copy()

    # -- Forward endpoint closes (shift within each stock group) --
    df["close_p1"] = df.groupby("ts_code")["adj_close"].shift(-1)
    df["close_p5"] = df.groupby("ts_code")["adj_close"].shift(-FWD_WINDOW_5)
    df["close_p6"] = df.groupby("ts_code")["adj_close"].shift(-6)
    df["close_p20"] = df.groupby("ts_code")["adj_close"].shift(-FWD_WINDOW)

    # -- fwd_ret_5d, fwd_ret_20d (from this date as entry) --
    df["fwd_ret_5d"] = df["close_p5"] / df["adj_close"] - 1.0
    df["fwd_ret_20d"] = df["close_p20"] / df["adj_close"] - 1.0

    # ── Helper: forward min/max over arbitrary window size ──────────
    # NO partial windows. If the full window is unavailable, result is NaN.
    def _fwd_min_window(grp, window):
        """Forward min over `window` FULL days starting at current position."""
        vals = np.asarray(grp.values, dtype=float)
        n = len(vals)
        result = np.full(n, np.nan)
        w = window
        if n >= w:
            windows = sliding_window_view(vals, w)
            result[:n - w + 1] = windows.min(axis=1)
        # No tail fill — positions without a full window stay NaN
        return result

    def _fwd_max_window(grp, window):
        """Forward max over `window` FULL days starting at current position."""
        vals = np.asarray(grp.values, dtype=float)
        n = len(vals)
        result = np.full(n, np.nan)
        w = window
        if n >= w:
            windows = sliding_window_view(vals, w)
            result[:n - w + 1] = windows.max(axis=1)
        return result

    # ── Full 20-day window min/max (for existing metrics) ──────────
    df["future_min_20d"] = df.groupby("ts_code")["close_p1"].transform(
        lambda x: _fwd_min_window(x, FWD_WINDOW))
    df["future_max_20d"] = df.groupby("ts_code")["close_p1"].transform(
        lambda x: _fwd_max_window(x, FWD_WINDOW))

    # ── Split-window min: t1-t5 and t6-t20 (drop-specific) ────────
    df["future_min_1_5"] = df.groupby("ts_code")["close_p1"].transform(
        lambda x: _fwd_min_window(x, FWD_WINDOW_5))
    WINDOW_6_20 = 15  # trading days from t+6 to t+20 inclusive
    df["future_min_6_20"] = df.groupby("ts_code")["close_p6"].transform(
        lambda x: _fwd_min_window(x, WINDOW_6_20))

    print(f"    future_min_20d coverage: {df['future_min_20d'].notna().mean():.1%}")
    print(f"    future_min_1_5  coverage: {df['future_min_1_5'].notna().mean():.1%}")
    print(f"    future_min_6_20 coverage: {df['future_min_6_20'].notna().mean():.1%}")

    # ── Derived drop-side path flags ───────────────────────────────
    entry = df["adj_close"]
    df["early_new_low_1_5"] = df["future_min_1_5"] < entry
    df["post_rebound_new_low_6_20"] = df["future_min_6_20"] <= entry
    df["swallowed_by_close20"] = df["fwd_ret_20d"] <= 0.0

    # rough_repair: early dip but recovers, no post-rebound new low
    df["rough_repair"] = (
        df["early_new_low_1_5"]
        & (df["fwd_ret_5d"] > 0)
        & (df["fwd_ret_20d"] > 0)
        & (~df["post_rebound_new_low_6_20"])
    )

    # ── Keep existing new_low_20d / new_high_20d for reference ────
    df["new_low_20d"] = df["future_min_20d"] < entry
    df["new_high_20d"] = df["future_max_20d"] > entry

    # ── trough/peak from full 20d window ───────────────────────────
    df["trough_ret_20d"] = df["future_min_20d"] / entry - 1.0
    df["peak_ret_20d"] = df["future_max_20d"] / entry - 1.0

    # ── MAE: properly signed ───────────────────────────────────────
    # Long MAE is always <= 0 (worst drawdown magnitude); short MAE always >= 0
    df["mae_long_20d"] = np.minimum(df["trough_ret_20d"], 0.0)
    df["mae_short_20d"] = np.maximum(df["peak_ret_20d"], 0.0)

    # ── giveback_ratio ─────────────────────────────────────────────
    eps = 0.001
    peak_pos = df["peak_ret_20d"].clip(lower=eps)
    df["giveback_ratio_long"] = np.where(
        df["peak_ret_20d"] > 0,
        (df["peak_ret_20d"] - df["fwd_ret_20d"]) / peak_pos,
        np.nan,
    )
    trough_neg = df["trough_ret_20d"].clip(upper=-eps)
    df["giveback_ratio_short"] = np.where(
        df["trough_ret_20d"] < 0,
        (df["fwd_ret_20d"] - df["trough_ret_20d"]) / (-trough_neg),
        np.nan,
    )

    # ── 20-DAY QUALITY FILTER ──────────────────────────────────────
    MAX_ABS_1D_JUMP_20D = 0.30
    MAX_ABS_RETURN_20D = 1.0

    # Boundary check: all required forward prices and path metrics exist
    df["_boundary_ok_20d"] = (
        df["close_p1"].notna()
        & df["close_p5"].notna()
        & df["close_p6"].notna()
        & df["close_p20"].notna()
        & df["future_min_1_5"].notna()
        & df["future_min_6_20"].notna()
        & df["future_min_20d"].notna()
        & df["future_max_20d"].notna()
    )

    # Close validity
    df["_close_valid_20d"] = (
        (df["adj_close"] > 0) & (df["close_p1"] > 0)
        & (df["close_p5"] > 0) & (df["close_p6"] > 0)
        & (df["close_p20"] > 0)
    )

    # Continuity: max abs 1d return in t+1..t+20 <= 0.30
    df["ret_1d_fwd"] = df.groupby("ts_code")["adj_close"].transform(
        lambda x: x.shift(-1) / x - 1)
    df["_max_abs_1d_fwd20"] = df.groupby("ts_code")["ret_1d_fwd"].transform(
        lambda x: _fwd_max_window(x, FWD_WINDOW))
    df["_continuity_ok_20d"] = (
        df["_max_abs_1d_fwd20"].notna()
        & (df["_max_abs_1d_fwd20"] <= MAX_ABS_1D_JUMP_20D)
    )

    # Return outlier: abs(20d return) <= 1.0 (100%)
    df["_return_ok_20d"] = (
        df["fwd_ret_20d"].notna()
        & (df["fwd_ret_20d"].abs() <= MAX_ABS_RETURN_20D)
    )

    # Overall 20d quality pass
    df["quality_pass_20d"] = (
        df["_boundary_ok_20d"]
        & df["_close_valid_20d"]
        & df["_continuity_ok_20d"]
        & df["_return_ok_20d"]
    )
    print(f"    20d quality pass rate: {df['quality_pass_20d'].mean():.3%}")

    # ── post-rebound metrics ───────────────────────────────────────
    # post_5_to_20_ret = close_t20 / close_t5 - 1
    df["post_5_to_20_ret"] = np.where(
        df["close_p5"].notna() & df["close_p20"].notna() & (df["close_p5"] > 0),
        df["close_p20"] / df["close_p5"] - 1.0,
        np.nan,
    )
    # pullback_after_5 = future_min_6_20 / close_t5 - 1
    df["pullback_after_5"] = np.where(
        df["close_p5"].notna() & df["future_min_6_20"].notna() & (df["close_p5"] > 0),
        df["future_min_6_20"] / df["close_p5"] - 1.0,
        np.nan,
    )

    # ── Placeholders (full-path computation needs daily closes) ────
    df["positive_days_20d"] = np.nan
    df["negative_days_20d"] = np.nan
    # Legacy alias for backward compat in report code
    df["post_rebound_ret_5_to_20"] = df["post_5_to_20_ret"]

    # ── Output column set ──────────────────────────────────────────
    out_cols = [
        "ts_code", "trade_date",
        "fwd_ret_5d", "fwd_ret_20d",
        "new_low_20d", "new_high_20d",
        "early_new_low_1_5", "post_rebound_new_low_6_20",
        "swallowed_by_close20", "rough_repair",
        "future_min_1_5", "future_min_6_20",
        "future_min_20d", "future_max_20d",
        "mae_long_20d", "mae_short_20d",
        "peak_ret_20d", "trough_ret_20d",
        "giveback_ratio_long", "giveback_ratio_short",
        "post_5_to_20_ret", "pullback_after_5",
        "positive_days_20d", "negative_days_20d",
        "post_rebound_ret_5_to_20",
        # 20d quality filter columns
        "quality_pass_20d",
        "_boundary_ok_20d", "_close_valid_20d",
        "_continuity_ok_20d", "_return_ok_20d",
    ]
    return df[[c for c in out_cols if c in df.columns]].copy()


# ───────────────────────────────────────────────────────────────────────
# 3. EXECUTION DATE MAPPING
# ───────────────────────────────────────────────────────────────────────

def build_exec_date_map(prices):
    """Build mapping: trade_date → exec_date (next trading day).

    Returns dict: {trade_date_int: exec_date_int}
    """
    all_dates = sorted(prices["trade_date"].unique())
    exec_map = {}
    for i, d in enumerate(all_dates):
        if i + EXECUTION_LAG < len(all_dates):
            exec_map[int(d)] = int(all_dates[i + EXECUTION_LAG])
    print(f"  Exec date map: {len(exec_map):,} dates mapped (lag={EXECUTION_LAG})")
    return exec_map


# ───────────────────────────────────────────────────────────────────────
# 4. A/B/M CLASSIFICATION
# ───────────────────────────────────────────────────────────────────────

def classify_long(row, retention_threshold):
    """Classify a single row (drop/long side) as A, B, M, or UNCLASSIFIED.

    A: effective repair
       fwd_ret_5d > 0
       AND fwd_ret_20d > 0
       AND fwd_ret_20d >= fwd_ret_5d * retention_threshold
       AND new_low_20d == False

    B: false repair / bad trend
       fwd_ret_5d <= 0
       OR (fwd_ret_5d > 0 AND fwd_ret_20d <= 0)
       OR (fwd_ret_5d > 0 AND new_low_20d == True)

    M: middle ground
       fwd_ret_5d > 0 AND fwd_ret_20d > 0
       AND fwd_ret_20d < fwd_ret_5d * retention_threshold
       AND new_low_20d == False
    """
    r5 = row["fwd_ret_5d"]
    r20 = row["fwd_ret_20d"]
    nl = row["new_low_20d"]

    if pd.isna(r5) or pd.isna(r20) or pd.isna(nl):
        return "UNCLASSIFIED"

    if r5 > 0 and r20 > 0 and r20 >= r5 * retention_threshold and not nl:
        return "A"
    elif r5 <= 0:
        return "B"
    elif r5 > 0 and r20 <= 0:
        return "B"
    elif r5 > 0 and nl:
        return "B"
    elif r5 > 0 and r20 > 0 and r20 < r5 * retention_threshold and not nl:
        return "M"
    else:
        return "UNCLASSIFIED"


def classify_short(row, retention_threshold):
    """Classify a single row (up/short side) as A, B, M, or UNCLASSIFIED.

    A: effective pullback
       fwd_ret_5d < 0
       AND fwd_ret_20d < 0
       AND abs(fwd_ret_20d) >= abs(fwd_ret_5d) * retention_threshold
       AND new_high_20d == False

    B: false pullback / strong trend continuation
       fwd_ret_5d >= 0
       OR (fwd_ret_5d < 0 AND fwd_ret_20d >= 0)
       OR (fwd_ret_5d < 0 AND new_high_20d == True)

    M: middle ground
       fwd_ret_5d < 0 AND fwd_ret_20d < 0
       AND abs(fwd_ret_20d) < abs(fwd_ret_5d) * retention_threshold
       AND new_high_20d == False
    """
    r5 = row["fwd_ret_5d"]
    r20 = row["fwd_ret_20d"]
    nh = row["new_high_20d"]

    if pd.isna(r5) or pd.isna(r20) or pd.isna(nh):
        return "UNCLASSIFIED"

    if r5 < 0 and r20 < 0 and abs(r20) >= abs(r5) * retention_threshold and not nh:
        return "A"
    elif r5 >= 0:
        return "B"
    elif r5 < 0 and r20 >= 0:
        return "B"
    elif r5 < 0 and nh:
        return "B"
    elif r5 < 0 and r20 < 0 and abs(r20) < abs(r5) * retention_threshold and not nh:
        return "M"
    else:
        return "UNCLASSIFIED"


def apply_labels(merged, direction, retention_threshold):
    """Apply A/B/M labels to the merged dataset based on direction.

    Drop (v2 — post-rebound swallow logic):
      A = value > 0, r5 > 0, r20 > 0, r20 >= r5 * rt, post_rebound_new_low_6_20 == False
      B = value > 0 AND (r5 <= 0 OR r20 <= 0 OR post_rebound_new_low_6_20 == True)
      M = value > 0, r5 > 0, r20 > 0, r20 < r5 * rt, post_rebound_new_low_6_20 == False

    Up / sym: unchanged (still use new_low_20d / new_high_20d).

    Also handles:
      - value == 0 → UNCLASSIFIED (non-event)
      - sym factor: value > 0 uses long rules, value < 0 uses short rules
    """
    df = merged.copy()
    r5 = df["fwd_ret_5d"].values
    r20 = df["fwd_ret_20d"].values
    nl = df["new_low_20d"].values
    nh = df["new_high_20d"].values
    val = df["value"].values
    rt = retention_threshold

    labels = np.full(len(df), "UNCLASSIFIED", dtype=object)

    if direction == "drop":
        event = val > 0
        # v2: use post_rebound_new_low_6_20, NOT new_low_20d
        post_nl = df["post_rebound_new_low_6_20"].values
        cond_A = event & (r5 > 0) & (r20 > 0) & (r20 >= r5 * rt) & (~post_nl)
        cond_B = event & ((r5 <= 0) | (r20 <= 0) | post_nl)
        cond_M = event & (r5 > 0) & (r20 > 0) & (r20 < r5 * rt) & (~post_nl)
        labels[cond_A] = "A"
        labels[cond_B] = "B"
        labels[cond_M] = "M"

    elif direction == "up":
        event = val < 0
        # Unchanged: new_high_20d
        cond_A = event & (r5 < 0) & (r20 < 0) & (np.abs(r20) >= np.abs(r5) * rt) & (~nh)
        cond_B = event & ((r5 >= 0) | ((r5 < 0) & (r20 >= 0)) | ((r5 < 0) & nh))
        cond_M = event & (r5 < 0) & (r20 < 0) & (np.abs(r20) < np.abs(r5) * rt) & (~nh)
        labels[cond_A] = "A"
        labels[cond_B] = "B"
        labels[cond_M] = "M"

    elif direction == "sym":
        mask_long = val > 0
        mask_short = val < 0
        # Sym uses old new_low_20d / new_high_20d (unchanged)
        cond_A_long = mask_long & (r5 > 0) & (r20 > 0) & (r20 >= r5 * rt) & (~nl)
        cond_B_long = mask_long & ((r5 <= 0) | ((r5 > 0) & (r20 <= 0)) | ((r5 > 0) & nl))
        cond_M_long = mask_long & (r5 > 0) & (r20 > 0) & (r20 < r5 * rt) & (~nl)
        cond_A_short = mask_short & (r5 < 0) & (r20 < 0) & (np.abs(r20) >= np.abs(r5) * rt) & (~nh)
        cond_B_short = mask_short & ((r5 >= 0) | ((r5 < 0) & (r20 >= 0)) | ((r5 < 0) & nh))
        cond_M_short = mask_short & (r5 < 0) & (r20 < 0) & (np.abs(r20) < np.abs(r5) * rt) & (~nh)
        labels[cond_A_long | cond_A_short] = "A"
        labels[cond_B_long | cond_B_short] = "B"
        labels[cond_M_long | cond_M_short] = "M"
    else:
        raise ValueError(f"Unknown direction: {direction}")

    df["ab_label"] = labels
    return df


# ───────────────────────────────────────────────────────────────────────
# 4b. ROUTE CLASSIFICATION (drop-side path decomposition)
# ───────────────────────────────────────────────────────────────────────

def classify_drop_routes(df):
    """Assign a rebound route to every drop event (value > 0).

    Routes (mutually exclusive, priority order):
      no_5d_rebound               — fwd_ret_5d <= 0
      rebound_swallowed_after_day5 — r5 > 0, post_rebound_new_low_6_20 == True
      rebound_failed_by_close20    — r5 > 0, post_nl == False, r20 <= 0
      rebound_retained_clean       — r5 > 0, r20 > 0, post_nl == False,
                                     early_new_low == False,
                                     r20 >= r5 * retention_threshold
      rebound_retained_rough       — r5 > 0, r20 > 0, post_nl == False,
                                     early_new_low == True,
                                     r20 >= r5 * retention_threshold
      middle_retention_insufficient— r5 > 0, r20 > 0, post_nl == False,
                                     r20 < r5 * retention_threshold
    """
    r5 = df["fwd_ret_5d"].values
    r20 = df["fwd_ret_20d"].values
    post_nl = df["post_rebound_new_low_6_20"].values
    early_nl = df["early_new_low_1_5"].values
    val = df["value"].values

    routes = np.full(len(df), "non_event", dtype=object)
    evt = val > 0

    # Priority 1: no 5d rebound
    mask = evt & (r5 <= 0)
    routes[mask] = "no_5d_rebound"

    # Priority 2: swallowed after day 5
    mask = evt & (r5 > 0) & post_nl
    routes[mask] = "rebound_swallowed_after_day5"

    # Priority 3: failed by close20 (r20 <= 0 but never went below entry after day 5)
    mask = evt & (r5 > 0) & (~post_nl) & (r20 <= 0)
    routes[mask] = "rebound_failed_by_close20"

    # Priority 4-6: rebound retained (clean, rough) or middle
    # A/M split depends on retention_threshold, handled per-threshold
    # Here we assign base route; retention check done in summary
    mask_clean = evt & (r5 > 0) & (r20 > 0) & (~post_nl) & (~early_nl)
    routes[mask_clean] = "rebound_retained_clean"

    mask_rough = evt & (r5 > 0) & (r20 > 0) & (~post_nl) & early_nl
    routes[mask_rough] = "rebound_retained_rough"

    df["rebound_route"] = routes
    return df


def compute_route_summary(df, retention_threshold):
    """Produce A/B/M × route cross-tabulation for drop events."""
    r5 = df["fwd_ret_5d"].values
    r20 = df["fwd_ret_20d"].values
    post_nl = df["post_rebound_new_low_6_20"].values
    early_nl = df["early_new_low_1_5"].values
    val = df["value"].values
    rt = retention_threshold
    evt = val > 0

    # Refresh route assignment with retention info
    routes = np.full(len(df), "non_event", dtype=object)

    mask = evt & (r5 <= 0)
    routes[mask] = "no_5d_rebound"

    mask = evt & (r5 > 0) & post_nl
    routes[mask] = "rebound_swallowed_after_day5"

    mask = evt & (r5 > 0) & (~post_nl) & (r20 <= 0)
    routes[mask] = "rebound_failed_by_close20"

    mask = evt & (r5 > 0) & (r20 > 0) & (~post_nl) & (~early_nl) & (r20 >= r5 * rt)
    routes[mask] = "rebound_retained_clean"

    mask = evt & (r5 > 0) & (r20 > 0) & (~post_nl) & early_nl & (r20 >= r5 * rt)
    routes[mask] = "rebound_retained_rough"

    mask = evt & (r5 > 0) & (r20 > 0) & (~post_nl) & (r20 < r5 * rt)
    routes[mask] = "middle_retention_insufficient"

    df["_route"] = routes
    evt_df = df[evt].copy()

    results = []
    route_order = [
        "no_5d_rebound", "rebound_swallowed_after_day5",
        "rebound_failed_by_close20", "rebound_retained_clean",
        "rebound_retained_rough", "middle_retention_insufficient",
    ]
    for route in route_order:
        subset = evt_df[evt_df["_route"] == route]
        n = len(subset)
        if n == 0:
            continue
        # Map to A/B/M
        a_n = (subset["ab_label"] == "A").sum()
        b_n = (subset["ab_label"] == "B").sum()
        m_n = (subset["ab_label"] == "M").sum()
        results.append({
            "retention_threshold": rt,
            "route": route,
            "n": n,
            "pct_of_events": round(n / len(evt_df) * 100, 2),
            "n_A": int(a_n),
            "n_B": int(b_n),
            "n_M": int(m_n),
            "mean_fwd_ret_5d": subset["fwd_ret_5d"].mean(),
            "mean_fwd_ret_20d": subset["fwd_ret_20d"].mean(),
            "mean_post_5_to_20_ret": subset["post_5_to_20_ret"].mean(),
            "median_pullback_after_5": subset["pullback_after_5"].median(),
            "rough_repair_rate": subset["rough_repair"].mean() if "rough_repair" in subset.columns else 0,
            "early_new_low_rate": subset["early_new_low_1_5"].mean(),
        })
    return results


# ───────────────────────────────────────────────────────────────────────
# 5. ACTION EVALUATION
# ───────────────────────────────────────────────────────────────────────

def evaluate_actions(labeled_df, direction, retention_threshold):
    """Evaluate three oracle actions: A only, A+0.5M, exclude B.

    All use the ex-post labels directly → these are ORACLE UPPER BOUNDS.

    Returns list of dicts with action metrics.
    """
    df = labeled_df.copy()
    df["year"] = df["trade_date"] // 10000

    results = []
    # All actions operate on the EVENT UNIVERSE ONLY (value != 0).
    # Non-event stocks (UNCLASSIFIED) are excluded from action evaluation.
    events_df = df[df["ab_label"] != "UNCLASSIFIED"].copy()
    n_events = len(events_df)

    actions = {
        "A_only": lambda d: d[d["ab_label"] == "A"],
        "A_plus_half_M": lambda d: d[d["ab_label"].isin(["A", "M"])],
        "exclude_B": lambda d: d[d["ab_label"].isin(["A", "M"])],  # A + M = events minus B
        "raw_events": lambda d: d,  # all events, no filtering
    }

    for action_name, filter_fn in actions.items():
        filtered = filter_fn(events_df)
        if len(filtered) == 0:
            continue

        # Coverage: % of event samples retained
        coverage = len(filtered) / n_events * 100 if n_events > 0 else 0

        # Mean forward returns
        mean_r5 = filtered["fwd_ret_5d"].mean()
        mean_r20 = filtered["fwd_ret_20d"].mean()

        # Gross spread (for drop: mean of long book; for up: mean of short book)
        if direction in ("drop", "sym"):
            gross_spread = mean_r20  # long book return
        else:
            gross_spread = -mean_r20  # short book: flip sign

        # Cost-adjusted net spread
        net_spread = gross_spread - COST_BPS

        # IC (simple rank IC against fwd_ret_20d within filtered universe)
        valid = filtered.dropna(subset=["value", "fwd_ret_20d"])
        ic_vals = []
        for _, g in valid.groupby("trade_date"):
            if len(g) >= MIN_STOCKS_PER_DATE:
                try:
                    ic, _ = spearmanr(g["value"], g["fwd_ret_20d"])
                    ic_vals.append(ic)
                except Exception:
                    pass
        mean_ic = np.mean(ic_vals) if ic_vals else np.nan
        icir = mean_ic / np.std(ic_vals) if ic_vals and np.std(ic_vals) > 0 else np.nan

        # Annual stats
        yearly = filtered.groupby("year").agg(
            n=("ts_code", "count"),
            mean_ret_20d=("fwd_ret_20d", "mean"),
        )
        n_years = len(yearly)
        if direction == "up":
            # Short side: profitable when mean_ret_20d < 0
            pos_years = (yearly["mean_ret_20d"] < 0).sum()
        else:
            pos_years = (yearly["mean_ret_20d"] > 0).sum()

        results.append({
            "factor": "",
            "direction": direction,
            "retention_threshold": retention_threshold,
            "action": action_name,
            "n_samples": len(filtered),
            "coverage_pct": round(coverage, 2),
            "mean_fwd_ret_5d": round(mean_r5, 6),
            "mean_fwd_ret_20d": round(mean_r20, 6),
            "gross_spread": round(gross_spread, 6),
            "net_spread_20bps": round(net_spread, 6),
            "ic": round(mean_ic, 6) if not np.isnan(mean_ic) else np.nan,
            "icir": round(icir, 6) if not np.isnan(icir) else np.nan,
            "pos_years": int(pos_years),
            "n_years": int(n_years),
        })

    return results


# ───────────────────────────────────────────────────────────────────────
# 6. QUALITY DIAGNOSTICS
# ───────────────────────────────────────────────────────────────────────

def compute_quality_diagnostics(labeled_df, direction, retention_threshold):
    """Compute auxiliary quality metrics by label.

    These are DESCRIPTIVE only — they do not affect A/B/M classification.
    """
    df = labeled_df[labeled_df["ab_label"] != "UNCLASSIFIED"].copy()
    if len(df) == 0:
        return []

    # Drop-only: quality diagnostics only filled for direction == "drop"
    is_drop = (direction == "drop" and "rough_repair" in df.columns
               and "post_rebound_new_low_6_20" in df.columns)

    results = []
    for label in ["A", "B", "M"]:
        subset = df[df["ab_label"] == label]
        if len(subset) == 0:
            continue

        row = {
            "factor": "",
            "direction": direction,
            "retention_threshold": retention_threshold,
            "label": label,
            "n": len(subset),
            "mae_long_mean": subset["mae_long_20d"].mean(),
            "mae_long_p10": subset["mae_long_20d"].quantile(0.10),
            "mae_short_mean": subset["mae_short_20d"].mean(),
            "mae_short_p90": subset["mae_short_20d"].quantile(0.90),
            "giveback_long_mean": subset["giveback_ratio_long"].mean(),
            "giveback_long_p90": subset["giveback_ratio_long"].quantile(0.90),
            "giveback_short_mean": subset["giveback_ratio_short"].mean(),
            "giveback_short_p90": subset["giveback_ratio_short"].quantile(0.90),
            "post_rebound_ret_mean": subset["post_rebound_ret_5_to_20"].mean(),
        }
        if is_drop:
            row["rough_repair_rate"] = subset["rough_repair"].mean()
            row["post_rebound_swallow_rate"] = subset["post_rebound_new_low_6_20"].mean()
            row["swallowed_by_close20_rate"] = subset["swallowed_by_close20"].mean()
            row["mean_post_5_to_20_ret"] = subset["post_5_to_20_ret"].mean()
            row["median_pullback_after_5"] = subset["pullback_after_5"].median()
        else:
            row["rough_repair_rate"] = np.nan
            row["post_rebound_swallow_rate"] = np.nan
            row["swallowed_by_close20_rate"] = np.nan
            row["mean_post_5_to_20_ret"] = np.nan
            row["median_pullback_after_5"] = np.nan
        results.append(row)

    return results


# ───────────────────────────────────────────────────────────────────────
# 7. SUMMARY STATISTICS
# ───────────────────────────────────────────────────────────────────────

def compute_label_summary(labeled_df, direction, retention_threshold):
    """Compute A/B/M label proportions and key metrics."""
    df = labeled_df.copy()
    total = len(df)
    n_unclassified = (df["ab_label"] == "UNCLASSIFIED").sum()
    n_events = total - n_unclassified

    # Drop-only fields: only fill for direction == "drop", else NaN
    is_drop = (direction == "drop" and "rough_repair" in df.columns
               and "post_rebound_new_low_6_20" in df.columns)

    results = []
    for label in ["A", "B", "M", "UNCLASSIFIED"]:
        subset = df[df["ab_label"] == label]
        n = len(subset)
        coverage = n / total * 100 if total > 0 else 0
        event_coverage = n / n_events * 100 if n_events > 0 and label != "UNCLASSIFIED" else np.nan

        row = {
            "factor": "",
            "direction": direction,
            "retention_threshold": retention_threshold,
            "label": label,
            "n_samples": n,
            "coverage_pct": round(coverage, 2),
            "event_coverage_pct": round(event_coverage, 2) if not np.isnan(event_coverage) else np.nan,
            "mean_fwd_ret_5d": subset["fwd_ret_5d"].mean() if n > 0 else np.nan,
            "mean_fwd_ret_20d": subset["fwd_ret_20d"].mean() if n > 0 else np.nan,
            "new_low_rate": subset["new_low_20d"].mean() if n > 0 and direction != "up" else np.nan,
            "new_high_rate": subset["new_high_20d"].mean() if n > 0 and direction != "drop" else np.nan,
            "mae_long_mean": subset["mae_long_20d"].mean() if n > 0 else np.nan,
            "mae_short_mean": subset["mae_short_20d"].mean() if n > 0 else np.nan,
            "giveback_long_mean": subset["giveback_ratio_long"].mean() if n > 0 else np.nan,
            "giveback_short_mean": subset["giveback_ratio_short"].mean() if n > 0 else np.nan,
            "post_rebound_ret_mean": subset["post_rebound_ret_5_to_20"].mean() if n > 0 else np.nan,
        }
        # Drop-specific v2 fields (NaN for up/sym)
        if is_drop:
            row["rough_repair_rate"] = subset["rough_repair"].mean() if n > 0 else np.nan
            row["post_rebound_swallow_rate"] = subset["post_rebound_new_low_6_20"].mean() if n > 0 else np.nan
            row["swallowed_by_close20_rate"] = subset["swallowed_by_close20"].mean() if n > 0 else np.nan
            row["mean_post_5_to_20_ret"] = subset["post_5_to_20_ret"].mean() if n > 0 else np.nan
            row["median_pullback_after_5"] = subset["pullback_after_5"].median() if n > 0 else np.nan
        else:
            row["rough_repair_rate"] = np.nan
            row["post_rebound_swallow_rate"] = np.nan
            row["swallowed_by_close20_rate"] = np.nan
            row["mean_post_5_to_20_ret"] = np.nan
            row["median_pullback_after_5"] = np.nan
        results.append(row)

    return results


def compute_by_year_summary(labeled_df, direction, retention_threshold):
    """Compute A/B/M proportions by year."""
    df = labeled_df.copy()
    df["year"] = df["trade_date"] // 10000

    results = []
    for yr in sorted(df["year"].unique()):
        yr_data = df[df["year"] == yr]
        total_yr = len(yr_data)
        n_events_yr = (yr_data["ab_label"] != "UNCLASSIFIED").sum()

        for label in ["A", "B", "M"]:
            subset = yr_data[yr_data["ab_label"] == label]
            n = len(subset)
            rate = n / n_events_yr * 100 if n_events_yr > 0 else 0

            results.append({
                "year": int(yr),
                "factor": "",
                "direction": direction,
                "retention_threshold": retention_threshold,
                "label": label,
                "n_samples": n,
                "label_rate_pct": round(rate, 2),
                "mean_fwd_ret_20d": subset["fwd_ret_20d"].mean() if n > 0 else np.nan,
                "new_low_rate": subset["new_low_20d"].mean() if n > 0 else np.nan,
                "new_high_rate": subset["new_high_20d"].mean() if n > 0 else np.nan,
            })

    return results


# ───────────────────────────────────────────────────────────────────────
# 8. REPORT GENERATION
# ───────────────────────────────────────────────────────────────────────

def generate_report(all_summaries, all_actions, all_quality, all_by_year,
                    all_route_summaries=None, all_filter_summaries=None):
    """Generate markdown report."""
    lines = []
    lines.append("# Panic Reversal A/B/M Classification — Oracle Evaluation Report")
    lines.append(f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("\n---")
    lines.append("\n## ⚠️ 重要说明：这是事后 (Oracle) 研究 (Drop v2)")
    lines.append("\n**本轮修正范围：仅 drop / long 侧。** up / short 和 sym 仍使用 v1 标签")
    lines.append("（`new_low_20d` / `new_high_20d`），后续再做对称化。")
    lines.append("\nDrop 侧 v2 变更：用 `post_rebound_new_low_6_20`（day6-day20 吞没判断）")
    lines.append("替代 `new_low_20d`（全窗口 20 日新低）。")
    lines.append("\"先挖坑后修复\"不再打入 B，归入 A 或 M，并通过 `rough_repair` 字段标记。")
    lines.append("\n**收益口径：** fwd_ret_5d 使用 clean lag1 版本（质量过滤后），")
    lines.append("fwd_ret_20d 经过 20 日路径质量过滤（边界/连续性/异常值）。")
    lines.append("\nA/B/M 标签使用未来信息，Phase 2 将训练 t0 可得预测器。")
    lines.append("\n---")

    # Summaries
    lines.append("\n## 1. A/B/M 标签分布")
    if all_summaries:
        df_sum = pd.DataFrame(all_summaries)
        lines.append(f"\n{df_sum.to_markdown(index=False, floatfmt='.4f')}")

    # Actions
    lines.append("\n## 2. Oracle Action 评估")
    lines.append("\n(上限估计，不可直接用于实盘)")
    if all_actions:
        df_act = pd.DataFrame(all_actions)
        lines.append(f"\n{df_act.to_markdown(index=False, floatfmt='.4f')}")

    # By year stability
    lines.append("\n## 3. 年度稳定性")
    if all_by_year:
        df_yr = pd.DataFrame(all_by_year)
        # Pivot for readability
        for direction in df_yr["direction"].unique():
            for thresh in df_yr["retention_threshold"].unique():
                subset = df_yr[(df_yr["direction"] == direction) &
                               (df_yr["retention_threshold"] == thresh)]
                if len(subset) > 0:
                    lines.append(f"\n### {direction}, retention={thresh}")
                    lines.append(f"\n{subset.to_markdown(index=False, floatfmt='.4f')}")

    # Quality
    lines.append("\n## 4. 交易质量诊断")
    if all_quality:
        df_qual = pd.DataFrame(all_quality)
        lines.append(f"\n{df_qual.to_markdown(index=False, floatfmt='.4f')}")

    # Route summary (drop only)
    if all_route_summaries:
        lines.append("\n## 5. Drop 反弹路径分解 (Route Summary)")
        lines.append("\n路径定义：")
        lines.append("- `no_5d_rebound`: fwd_ret_5d <= 0")
        lines.append("- `rebound_swallowed_after_day5`: r5 > 0, day6-20 跌破入场价")
        lines.append("- `rebound_failed_by_close20`: r5 > 0, r20 <= 0, day6-20 未破入场")
        lines.append("- `rebound_retained_clean`: r5 > 0, r20 > 0, 无早期挖坑, retention 充足")
        lines.append("- `rebound_retained_rough`: r5 > 0, r20 > 0, day1-5 挖坑但 day6-20 修复, retention 充足")
        lines.append("- `middle_retention_insufficient`: r5 > 0, r20 > 0, 无吞没, retention 不足")
        df_route = pd.DataFrame(all_route_summaries)
        lines.append(f"\n{df_route.to_markdown(index=False, floatfmt='.4f')}")

    # Quality filter summary
    if all_filter_summaries:
        lines.append("\n## 6. 质量过滤统计 (Quality Filter)")
        df_filt = pd.DataFrame(all_filter_summaries)
        lines.append(f"\n{df_filt.to_markdown(index=False, floatfmt='.4f')}")
        lines.append("\n过滤步骤：")
        lines.append("1. lag1 inner join: 仅保留有 clean 5 日收益的样本")
        lines.append("2. 20d boundary: entry/t+5/t+6/t+20/future min/max 全部存在")
        lines.append("3. 20d close_valid: 所有关键价格 > 0")
        lines.append("4. 20d continuity: t+1..t+20 单日 |ret| ≤ 0.30")
        lines.append("5. 20d return_ok: |fwd_ret_20d| ≤ 1.0")

    # Decision framework
    lines.append("\n---")
    lines.append("\n## 7. 决策框架")
    lines.append("\n```")
    lines.append("如果 A 类覆盖率过低 (< 10% of events):")
    lines.append("    → 不采用 A only，优先评估 exclude B")
    lines.append("")
    lines.append("如果 exclude B 的 net_spread > raw events:")
    lines.append("    → 可作为 reversal_5_cs 的候选过滤器")
    lines.append("")
    lines.append("如果 A/B/M 无法明显拉开收益差距:")
    lines.append("    → 保持 RESEARCH_ONLY")
    lines.append("")
    lines.append("如果 A 类收益好但交易质量差 (MAE 深 / giveback 高):")
    lines.append("    → 用作降权/过滤，不独立入池")
    lines.append("```")

    lines.append("\n---")
    lines.append("\n## 8. 下一步")
    lines.append("\n1. 本报告确认 drop v2 oracle ceiling 后，对 up/short 做对称化修正")
    lines.append("2. Phase 2: 用 t0 可得特征训练 A/B 预测模型 (drop 和 up 分开)")
    lines.append("3. Walk-forward 验证可执行过滤器")
    lines.append("4. 与 reversal_5_cs 做增量验证")
    lines.append("\n**当前 drop 侧 v2 标签定义:**")
    lines.append("\n- A = value > 0, fwd_ret_5d > 0, fwd_ret_20d > 0,")
    lines.append("  fwd_ret_20d >= fwd_ret_5d * retention_threshold,")
    lines.append("  post_rebound_new_low_6_20 == False")
    lines.append("- B = value > 0 AND (fwd_ret_5d <= 0 OR fwd_ret_20d <= 0")
    lines.append("  OR post_rebound_new_low_6_20 == True)")
    lines.append("- M = value > 0, fwd_ret_5d > 0, fwd_ret_20d > 0,")
    lines.append("  fwd_ret_20d < fwd_ret_5d * retention_threshold,")
    lines.append("  post_rebound_new_low_6_20 == False")
    lines.append("- rough_repair = early_new_low_1_5 AND fwd_ret_5d > 0")
    lines.append("  AND fwd_ret_20d > 0 AND NOT post_rebound_new_low_6_20")
    lines.append("  (不改变主标签，仅进入诊断输出)")

    return "\n".join(lines)


# ───────────────────────────────────────────────────────────────────────
# 9. MAIN PIPELINE
# ───────────────────────────────────────────────────────────────────────

def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print("=" * 70)
    print("PANIC REVERSAL A/B/M CLASSIFICATION — ORACLE EVALUATION")
    print("=" * 70)
    print("*** This is an ex-post (oracle) study. Labels use future information.")
    print("    Action evaluations represent oracle upper bounds only.")
    print()

    # ── Step 1: Load prices ──
    print("[1/7] Loading prices...")
    prices = load_prices()

    # ── Step 2: Compute forward metrics at every price date ──
    print("\n[2/7] Computing forward metrics (exec_lag=1 reference)...")
    fwd_metrics = compute_forward_metrics(prices)
    print(f"  Forward metrics: {len(fwd_metrics):,} rows, "
          f"{fwd_metrics['fwd_ret_20d'].notna().sum():,} with valid 20d ret")

    # ── Step 3: Build exec date map ──
    print("\n[3/7] Building execution date map...")
    exec_map = build_exec_date_map(prices)

    # ── Step 4: Load lag1 returns and merge ──
    print("\n[4/7] Loading lag1 returns...")
    lag1 = load_lag1_returns()

    # ── Step 5-7: Process each factor variant ──
    all_summaries = []
    all_actions = []
    all_quality = []
    all_by_year = []
    all_route_summaries = []
    all_filter_summaries = []

    for factor_name, direction in PRIMARY_VARIANTS:
        print(f"\n{'='*70}")
        print(f"[5/7] Processing: {factor_name} (direction={direction})")
        print(f"{'='*70}")

        # Load factor
        factor = load_factor(factor_name)
        if factor.empty:
            print(f"  SKIP: no data for {factor_name}")
            continue
        n_raw = len(factor)
        print(f"  Factor rows: {n_raw:,}")

        # Map signal_date → exec_date
        factor["exec_date"] = factor["trade_date"].map(exec_map)
        n_after_exec = len(factor.dropna(subset=["exec_date"]))
        factor = factor.dropna(subset=["exec_date"])
        print(f"  After exec_date mapping: {n_after_exec:,} (dropped {n_raw - n_after_exec:,})")

        # Step A: Inner join with lag1 returns on signal_date
        # This ensures we only use clean, quality-filtered 5d returns
        if not lag1.empty:
            factor = factor.merge(
                lag1[["ts_code", "trade_date", "fwd_ret_5d_exec_lag1"]],
                on=["ts_code", "trade_date"],
                how="inner",
            )
            n_after_lag1 = len(factor)
            print(f"  After lag1 inner join: {n_after_lag1:,} (dropped {n_after_exec - n_after_lag1:,})")
            # Keep price-calculated version for audit; overwrite primary
            factor["fwd_ret_5d_price_calc"] = np.nan  # will be filled after merge
        else:
            print("  WARNING: lag1 returns unavailable, using price-calc 5d returns")
            n_after_lag1 = n_after_exec

        # Merge with forward metrics on (ts_code, exec_date)
        merged = factor.merge(
            fwd_metrics,
            left_on=["ts_code", "exec_date"],
            right_on=["ts_code", "trade_date"],
            how="inner",
            suffixes=("", "_fwd"),
        )
        n_after_merge = len(merged)
        print(f"  After metrics merge: {n_after_merge:,}")

        # Overwrite primary fwd_ret_5d with clean lag1 version
        if not lag1.empty and "fwd_ret_5d_exec_lag1" in merged.columns:
            # Save price-calc version for audit
            if "fwd_ret_5d_price_calc" not in merged.columns or merged["fwd_ret_5d_price_calc"].isna().all():
                merged["fwd_ret_5d_price_calc"] = merged["fwd_ret_5d"].copy()
            merged["fwd_ret_5d"] = merged["fwd_ret_5d_exec_lag1"]
            print(f"  fwd_ret_5d: switched to clean lag1 version")
            print(f"    lag1 mean={merged['fwd_ret_5d'].mean():.5f}  "
                  f"price_calc mean={merged['fwd_ret_5d_price_calc'].mean():.5f}")

        # Apply 20d quality filter
        if "quality_pass_20d" in merged.columns:
            n_before_qf = len(merged)
            merged = merged[merged["quality_pass_20d"]].copy()
            n_after_qf = len(merged)
            n_removed = n_before_qf - n_after_qf
            removed_rate = n_removed / n_before_qf * 100 if n_before_qf > 0 else 0
            print(f"  After 20d quality filter: {n_after_qf:,} "
                  f"(removed {n_removed:,}, {removed_rate:.2f}%)")
        else:
            n_after_qf = n_after_merge
            n_removed = 0
            removed_rate = 0

        # Track filter counts
        all_filter_summaries.append({
            "factor": factor_name,
            "direction": direction,
            "raw_rows": n_raw,
            "after_exec_map": n_after_exec,
            "after_lag1_inner_join": n_after_lag1,
            "after_metric_merge": n_after_merge,
            "after_20d_quality_filter": n_after_qf,
            "removed_by_20d_quality": n_removed,
            "removed_rate": round(removed_rate, 4),
        })

        # Exclude rows where core metrics are still NaN (after quality filter)
        merged = merged.dropna(subset=["fwd_ret_5d", "fwd_ret_20d"])
        print(f"  After dropna (core metrics): {len(merged):,}")

        # Add year
        merged["year"] = merged["trade_date"] // 10000

        # Route classification (drop-side only, done once before threshold loop)
        if direction == "drop":
            merged = classify_drop_routes(merged)

        for rt in RETENTION_THRESHOLDS:
            print(f"\n  --- retention_threshold = {rt} ---")

            # Classify
            labeled = apply_labels(merged, direction, rt)

            # Value=0 check
            n_value_zero = (labeled["value"] == 0).sum()
            n_unclass = (labeled["ab_label"] == "UNCLASSIFIED").sum()
            print(f"    value==0: {n_value_zero:,}  |  UNCLASSIFIED: {n_unclass:,}")

            # Label distribution
            label_counts = labeled["ab_label"].value_counts()
            for lbl in ["A", "B", "M", "UNCLASSIFIED"]:
                cnt = label_counts.get(lbl, 0)
                pct = cnt / len(labeled) * 100
                print(f"    {lbl}: {cnt:,} ({pct:.1f}%)")

            # Additional drop-side diagnostics
            if direction == "drop":
                a_mask = labeled["ab_label"] == "A"
                b_mask = labeled["ab_label"] == "B"
                if a_mask.sum() > 0:
                    print(f"    A: rough_repair_rate={labeled.loc[a_mask, 'rough_repair'].mean():.3f}  "
                          f"swallowed_rate={labeled.loc[a_mask, 'swallowed_by_close20'].mean():.3f}")
                if b_mask.sum() > 0:
                    print(f"    B: post_rebound_swallow_rate={labeled.loc[b_mask, 'post_rebound_new_low_6_20'].mean():.3f}  "
                          f"swallowed_by_close20_rate={labeled.loc[b_mask, 'swallowed_by_close20'].mean():.3f}")

            # Summaries
            summaries = compute_label_summary(labeled, direction, rt)
            for s in summaries:
                s["factor"] = factor_name
            all_summaries.extend(summaries)

            # By year
            by_year = compute_by_year_summary(labeled, direction, rt)
            for b in by_year:
                b["factor"] = factor_name
            all_by_year.extend(by_year)

            # Action evaluation (oracle)
            actions = evaluate_actions(labeled, direction, rt)
            for a in actions:
                a["factor"] = factor_name
            all_actions.extend(actions)
            if actions:
                print(f"    Actions evaluated: {len(actions)}")

            # Quality diagnostics
            quality = compute_quality_diagnostics(labeled, direction, rt)
            for q in quality:
                q["factor"] = factor_name
            all_quality.extend(quality)

            # Route summary (drop only)
            if direction == "drop":
                route_rows = compute_route_summary(labeled, rt)
                for rr in route_rows:
                    rr["factor"] = factor_name
                    rr["direction"] = direction
                all_route_summaries.extend(route_rows)

    # ── Save outputs ──
    print(f"\n{'='*70}")
    print("[6/7] Saving outputs...")

    def save_csv(data, filename):
        if data:
            df = pd.DataFrame(data)
            path = OUT_DIR / filename
            df.to_csv(path, index=False)
            print(f"  {filename}: {len(df):,} rows → {path}")
        else:
            print(f"  {filename}: NO DATA")

    save_csv(all_summaries, "panic_ab_label_summary.csv")
    save_csv(all_by_year, "panic_ab_by_year.csv")
    save_csv(all_actions, "panic_ab_action_eval.csv")
    save_csv(all_quality, "panic_ab_quality_diagnostics.csv")
    save_csv(all_route_summaries, "panic_drop_rebound_route_summary.csv")
    save_csv(all_filter_summaries, "panic_ab_quality_filter_summary.csv")

    # ── Generate report ──
    print(f"\n[7/7] Generating report...")
    report = generate_report(all_summaries, all_actions, all_quality, all_by_year,
                             all_route_summaries, all_filter_summaries)
    report_path = OUT_DIR / "panic_ab_classification_report.md"
    report_path.write_text(report, encoding="utf-8")
    print(f"  Report: {report_path}")

    print(f"\n{'='*70}")
    print("A/B/M CLASSIFICATION COMPLETE")
    print(f"{'='*70}")
    print(f"Total label summaries:      {len(all_summaries):,}")
    print(f"Total action evaluations:   {len(all_actions):,}")
    print(f"Total quality rows:         {len(all_quality):,}")
    print(f"Total by-year rows:         {len(all_by_year):,}")
    print(f"Total route summary rows:   {len(all_route_summaries):,}")
    print(f"Total filter summary rows:  {len(all_filter_summaries):,}")

    return (all_summaries, all_actions, all_quality, all_by_year,
            all_route_summaries, all_filter_summaries)


if __name__ == "__main__":
    (all_summaries, all_actions, all_quality, all_by_year,
     all_routes, all_filters) = main()

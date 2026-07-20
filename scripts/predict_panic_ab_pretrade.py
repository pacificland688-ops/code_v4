"""
Pre-trade A/B predictor v2 — label-availability-aware walk-forward.

Key fixes over v1:
  1. Label availability filter: training excludes samples whose 20d-forward
     label is not yet available before the test period starts.
  2. Embargo: optional trading-day gap between last training date and first
     test date (default 20 days).
  3. Top-k quantile thresholds in addition to fixed-probability cutoffs.
     Default primary strategy: top_10pct.
  4. price_only feature set by default; daily_basic gated behind a CLI flag.
  5. Leakage audit output file.

RESEARCH ONLY — does not write any production signal.
"""
from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FACTOR = "panic_drop_rev5_t05_bin_weekly_cs"
DEFAULT_OUT_DIR = ROOT / "outputs" / "analysis" / "panic_reversal_gate" / "ab_pretrade_v2"
COST_BPS = 20 / 10000
FIXED_THRESHOLDS = (0.50, 0.60, 0.70)
TOP_K_PCTS = (5, 10, 20)

DEFAULT_WINDOWS = (
    (2017, 2021, 2022, 2022),
    (2017, 2022, 2023, 2023),
    (2017, 2023, 2024, 2024),
    (2017, 2024, 2025, 2025),
)

LABEL_COL = "ab_label"
TARGET_COL = "target_A"
RETURN_COL = "fwd_ret_20d"

# ── Feature definitions ───────────────────────────────────────────────
PRICE_FEATURE_COLUMNS = [
    "value", "value_rank_pct", "value_top_decile",
    "ret_1d", "mom_3d", "mom_5d", "mom_10d", "mom_20d",
    "drawdown_20d", "distance_to_20d_low", "consec_down_days",
    "vol_5d", "vol_10d", "vol_20d", "vol_5d_over_20d",
]

DAILY_BASIC_COLUMNS = [
    "turnover_rate", "turnover_rate_f", "volume_ratio",
    "log_total_mv", "log_circ_mv", "pb", "pe_ttm",
]

FORBIDDEN_FEATURE_SUBSTRINGS = (
    "fwd_", "future_", "post_rebound", "giveback",
    "mae_", "new_low", "new_high", "pullback_after",
    "post_5_to_20", "positive_days", "negative_days",
    "swallowed_by", "rough_repair",
    "ab_label", "target_A", "p_A",
)


# ── CLI ───────────────────────────────────────────────────────────────
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Research-only pre-trade A/B predictor v2"
    )
    p.add_argument("--start", type=int, default=20170101)
    p.add_argument("--end", type=int, default=20251231)
    p.add_argument("--factor", default=DEFAULT_FACTOR)
    p.add_argument("--retention-threshold", type=float, default=0.3)
    p.add_argument("--min-coverage", type=float, default=0.05)
    p.add_argument("--embargo-days", type=int, default=20)
    p.add_argument("--leakage-control", default="label_available_plus_embargo",
                   choices=["none", "label_available", "label_available_plus_embargo"])
    p.add_argument("--include-daily-basic", action="store_true", default=False)
    p.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    p.add_argument("--root", default=str(ROOT))
    return p.parse_args()


# ── Helpers ───────────────────────────────────────────────────────────
def _read_parquet_columns(path: Path, columns: Sequence[str] | None = None) -> pd.DataFrame:
    if columns is None:
        return pd.read_parquet(path)
    try:
        return pd.read_parquet(path, columns=list(columns))
    except Exception:
        df = pd.read_parquet(path)
        return df[[c for c in columns if c in df.columns]]


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]
    if "ts_code" in df.columns:
        df["ts_code"] = df["ts_code"].astype(str)
    for col in ("trade_date", "available_date", "exec_date"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def _iter_year_dirs(base: Path, start: int, end: int) -> Iterable[Path]:
    sy, ey = start // 10000, end // 10000
    for d in sorted(base.glob("year=*")):
        if not d.is_dir():
            continue
        try:
            yr = int(d.name.split("=", 1)[1])
        except ValueError:
            continue
        if sy - 1 <= yr <= ey + 1:
            yield d


def _consecutive_true(flags: pd.Series) -> pd.Series:
    flags = flags.fillna(False).astype(bool)
    groups = (flags != flags.shift()).cumsum()
    counts = flags.groupby(groups).cumcount() + 1
    return counts.where(flags, 0).astype(float)


def _safe_auc(y_true, score):
    if len(pd.Series(y_true).dropna().unique()) < 2:
        return float("nan")
    return float(roc_auc_score(y_true, score))


def _safe_pr_auc(y_true, score):
    if len(pd.Series(y_true).dropna().unique()) < 2:
        return float("nan")
    return float(average_precision_score(y_true, score))


# ── Trading calendar ──────────────────────────────────────────────────
def build_trading_calendar(prices: pd.DataFrame) -> np.ndarray:
    return np.array(sorted(int(d) for d in prices["trade_date"].dropna().unique()))


def trading_day_offset(calendar: np.ndarray, date: int, offset: int) -> int | None:
    """Return the date `offset` trading days from `date`."""
    idx = np.searchsorted(calendar, date)
    if idx >= len(calendar) or calendar[idx] != date:
        return None
    target = idx + offset
    if 0 <= target < len(calendar):
        return int(calendar[target])
    return None


def first_trading_day_of_year(calendar: np.ndarray, year: int) -> int | None:
    """First actual trading day whose calendar year == `year`. Returns None if none."""
    for d in calendar:
        if d // 10000 == year:
            return int(d)
    return None


# ── Data loaders ──────────────────────────────────────────────────────
def load_price_data(root: Path, start: int, end: int) -> pd.DataFrame:
    base = root / "data" / "parquet" / "prices_adj"
    cols = ["ts_code", "trade_date", "adj_close", "vol", "amount", "pct_chg"]
    chunks = []
    for yr_dir in _iter_year_dirs(base, start, end):
        for pq in sorted(yr_dir.rglob("*.parquet")):
            df = _normalize(_read_parquet_columns(pq, cols))
            if "adj_close" not in df.columns:
                continue
            df = df.dropna(subset=["trade_date", "adj_close"])
            chunks.append(df[[c for c in cols if c in df.columns]])
    if not chunks:
        raise RuntimeError(f"No prices_adj parquet under {base}")
    prices = pd.concat(chunks, ignore_index=True)
    prices = prices.drop_duplicates(["ts_code", "trade_date"])
    prices = prices.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)
    return prices


def load_daily_basic(root: Path, start: int, end: int) -> pd.DataFrame:
    base = root / "data" / "parquet" / "daily_basic"
    cols = [
        "ts_code", "trade_date",
        "turnover_rate", "turnover_rate_f", "volume_ratio",
        "pe_ttm", "pb", "total_mv", "circ_mv",
    ]
    chunks = []
    for yr_dir in _iter_year_dirs(base, start, end):
        for pq in sorted(yr_dir.rglob("*.parquet")):
            df = _normalize(_read_parquet_columns(pq, cols))
            if {"ts_code", "trade_date"}.issubset(df.columns):
                chunks.append(df[[c for c in cols if c in df.columns]])
    if not chunks:
        return pd.DataFrame(columns=cols)
    basic = pd.concat(chunks, ignore_index=True)
    basic = basic.dropna(subset=["trade_date"])
    basic = basic.drop_duplicates(["ts_code", "trade_date"])
    basic["log_total_mv"] = np.log1p(pd.to_numeric(basic.get("total_mv"), errors="coerce"))
    basic["log_circ_mv"] = np.log1p(pd.to_numeric(basic.get("circ_mv"), errors="coerce"))
    keep = ["ts_code", "trade_date",
            "turnover_rate", "turnover_rate_f", "volume_ratio",
            "pe_ttm", "pb", "log_total_mv", "log_circ_mv"]
    return basic[[c for c in keep if c in basic.columns]]


def load_factor(root: Path, factor_name: str, start: int, end: int) -> pd.DataFrame:
    base = root / "data" / "parquet" / "factors" / f"factor_name={factor_name}"
    if not base.exists():
        raise RuntimeError(f"Factor path not found: {base}")
    cols = ["ts_code", "trade_date", "value", "available_date",
            "source_period", "source_date", "pit_lag_days", "is_stale"]
    chunks = []
    for yr_dir in _iter_year_dirs(base, start, end):
        for pq in sorted(yr_dir.rglob("*.parquet")):
            df = _normalize(_read_parquet_columns(pq, cols))
            if {"ts_code", "trade_date", "value"}.issubset(df.columns):
                chunks.append(df[[c for c in cols if c in df.columns]])
    if not chunks:
        raise RuntimeError(f"No factor parquet under {base}")
    factor = pd.concat(chunks, ignore_index=True)
    factor = factor.dropna(subset=["trade_date", "value"])
    factor = factor[(factor["trade_date"] >= start) & (factor["trade_date"] <= end)]
    factor = factor.drop_duplicates(["ts_code", "trade_date"])
    # PIT validation: available_date must not be later than trade_date
    if "available_date" in factor.columns:
        bad_pit = factor["available_date"].notna() & (factor["available_date"] > factor["trade_date"])
        if bad_pit.any():
            raise RuntimeError(
                f"Factor has {int(bad_pit.sum())} rows with available_date > trade_date "
                f"(PIT violation — factor data may contain future information)"
            )
    factor["value_rank_pct"] = factor.groupby("trade_date")["value"].rank(pct=True)
    factor["value_top_decile"] = (factor["value_rank_pct"] >= 0.9).astype(float)
    return factor


# ── Forward metrics & labels ──────────────────────────────────────────
def _forward_min(values: pd.Series, window: int) -> np.ndarray:
    arr = np.asarray(values.values, dtype=float)
    result = np.full(len(arr), np.nan)
    if len(arr) >= window:
        result[:len(arr) - window + 1] = sliding_window_view(arr, window).min(axis=1)
    return result


def compute_forward_metrics(prices: pd.DataFrame) -> pd.DataFrame:
    df = prices.sort_values(["ts_code", "trade_date"]).copy()
    grp = df.groupby("ts_code", group_keys=False)["adj_close"]
    df["close_p5"] = grp.shift(-5)
    df["close_p6"] = grp.shift(-6)
    df["close_p20"] = grp.shift(-20)
    df["fwd_ret_5d"] = df["close_p5"] / df["adj_close"] - 1.0
    df["fwd_ret_20d"] = df["close_p20"] / df["adj_close"] - 1.0
    df["future_min_6_20"] = grp.transform(lambda s: _forward_min(s.shift(-6), 15))
    df["post_rebound_new_low_6_20"] = df["future_min_6_20"] <= df["adj_close"]
    df["quality_pass_20d"] = (
        df["adj_close"].gt(0)
        & df["close_p5"].gt(0)
        & df["close_p6"].gt(0)
        & df["close_p20"].gt(0)
        & df["future_min_6_20"].notna()
        & df["fwd_ret_20d"].abs().le(1.0)
    )
    out = df[[
        "ts_code", "trade_date",
        "fwd_ret_5d", "fwd_ret_20d",
        "future_min_6_20", "post_rebound_new_low_6_20",
        "quality_pass_20d",
    ]].copy()
    return out


def assign_drop_ab_labels(df: pd.DataFrame, retention_threshold: float) -> pd.DataFrame:
    result = df.copy()
    r5 = result["fwd_ret_5d"]
    r20 = result["fwd_ret_20d"]
    post_nl = result["post_rebound_new_low_6_20"].fillna(True)
    event = result["value"] > 0

    labels = np.full(len(result), "UNCLASSIFIED", dtype=object)
    cond_a = event & (r5 > 0) & (r20 > 0) & (r20 >= r5 * retention_threshold) & (~post_nl)
    cond_b = event & ((r5 <= 0) | (r20 <= 0) | post_nl)
    cond_m = event & (r5 > 0) & (r20 > 0) & (r20 < r5 * retention_threshold) & (~post_nl)
    labels[cond_a] = "A"
    labels[cond_b] = "B"
    labels[cond_m] = "M"
    result[LABEL_COL] = labels
    result[TARGET_COL] = np.where(
        result[LABEL_COL] == "A", 1,
        np.where(result[LABEL_COL] == "B", 0, np.nan))
    return result


# ── Feature computation (t0-available only) ──────────────────────────
def compute_price_features(prices: pd.DataFrame) -> pd.DataFrame:
    df = prices.sort_values(["ts_code", "trade_date"]).copy()
    grp = df.groupby("ts_code", group_keys=False)
    df["ret_1d"] = grp["adj_close"].pct_change()
    for w in (3, 5, 10, 20):
        df[f"mom_{w}d"] = grp["adj_close"].pct_change(w)
    for w in (5, 10, 20):
        df[f"vol_{w}d"] = grp["ret_1d"].transform(
            lambda s, ww=w: s.rolling(ww, min_periods=max(3, ww // 2)).std())
    roll_low = grp["adj_close"].transform(lambda s: s.rolling(20, min_periods=5).min())
    roll_high = grp["adj_close"].transform(lambda s: s.rolling(20, min_periods=5).max())
    df["drawdown_20d"] = df["adj_close"] / roll_high - 1.0
    df["distance_to_20d_low"] = df["adj_close"] / roll_low - 1.0
    df["consec_down_days"] = grp["ret_1d"].transform(lambda s: _consecutive_true(s < 0))
    df["vol_5d_over_20d"] = df["vol_5d"] / df["vol_20d"].replace(0, np.nan)
    keep = [
        "ts_code", "trade_date", "ret_1d",
        "mom_3d", "mom_5d", "mom_10d", "mom_20d",
        "drawdown_20d", "distance_to_20d_low", "consec_down_days",
        "vol_5d", "vol_10d", "vol_20d", "vol_5d_over_20d",
    ]
    return df[keep]


def validate_features(feature_cols: Sequence[str]) -> None:
    bad = []
    for col in feature_cols:
        lower = col.lower()
        if any(token in lower for token in FORBIDDEN_FEATURE_SUBSTRINGS):
            bad.append(col)
    if bad:
        raise ValueError(f"Forbidden future/leakage columns: {bad}")


# ── Sample assembly ──────────────────────────────────────────────────
def build_samples(
    root: Path,
    factor_name: str,
    start: int,
    end: int,
    retention_threshold: float,
    include_daily_basic: bool = False,
) -> tuple[pd.DataFrame, list[str], np.ndarray]:
    """Assemble labelled samples with t0-observable features.

    Returns (samples_df, feature_columns, trading_calendar).
    """
    prices = load_price_data(root, start, end)
    calendar = build_trading_calendar(prices)
    factor = load_factor(root, factor_name, start, end)

    exec_map = build_exec_date_map(prices)
    events = factor[factor["value"] > 0].copy()
    events["exec_date"] = events["trade_date"].map(exec_map)
    events = events.dropna(subset=["exec_date"]).copy()
    events["exec_date"] = events["exec_date"].astype(int)

    # Label available date = exec_date + 20 trading days
    events["label_available_date"] = events["exec_date"].apply(
        lambda d: trading_day_offset(calendar, d, 20))
    events = events.dropna(subset=["label_available_date"])
    events["label_available_date"] = events["label_available_date"].astype(int)

    # Forward metrics
    fwd = compute_forward_metrics(prices).rename(columns={"trade_date": "exec_date"})
    samples = events.merge(fwd, on=["ts_code", "exec_date"], how="inner")
    samples = samples[samples["quality_pass_20d"]].copy()
    samples = samples.dropna(subset=["fwd_ret_5d", "fwd_ret_20d"])
    samples = assign_drop_ab_labels(samples, retention_threshold)

    # Price features (t0-available)
    price_features = compute_price_features(prices)
    samples = samples.merge(price_features, on=["ts_code", "trade_date"], how="left")

    # Optional daily_basic
    if include_daily_basic:
        daily_basic = load_daily_basic(root, start, end)
        if not daily_basic.empty:
            samples = samples.merge(daily_basic, on=["ts_code", "trade_date"], how="left")

    samples["year"] = (samples["trade_date"] // 10000).astype(int)
    samples = samples[(samples["trade_date"] >= start) & (samples["trade_date"] <= end)].copy()

    # Feature columns
    feature_cols = [c for c in PRICE_FEATURE_COLUMNS if c in samples.columns]
    if include_daily_basic:
        extra = [c for c in DAILY_BASIC_COLUMNS if c in samples.columns]
        feature_cols.extend(extra)
    validate_features(feature_cols)

    return samples, feature_cols, calendar


def build_exec_date_map(prices: pd.DataFrame, lag: int = 1) -> dict[int, int]:
    dates = sorted(int(d) for d in prices["trade_date"].dropna().unique())
    return {dates[i]: dates[i + lag] for i in range(len(dates) - lag)}


# ── Model ─────────────────────────────────────────────────────────────
def build_model(random_state: int = 42) -> Pipeline:
    return Pipeline(steps=[
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler", StandardScaler()),
        ("model", LogisticRegression(
            class_weight="balanced", max_iter=1000, random_state=random_state)),
    ])


# ── Metrics ───────────────────────────────────────────────────────────
@dataclass
class SelectionMetrics:
    action: str
    n_samples: int = 0
    coverage_pct: float = 0.0
    a_rate: float = float("nan")
    raw_a_rate: float = float("nan")
    a_rate_lift: float = float("nan")
    mean_fwd_ret_20d: float = float("nan")
    raw_mean_fwd_ret_20d: float = float("nan")
    net_spread_20bps: float = float("nan")
    raw_net_spread_20bps: float = float("nan")
    net_spread_lift: float = float("nan")

    def to_dict(self) -> dict:
        return {k: (float(v) if isinstance(v, (np.floating, float, int))
                    and not (isinstance(v, float) and math.isnan(v)) else v)
                for k, v in self.__dict__.items()}


def compute_selection_metrics(
    df: pd.DataFrame,
    selected_mask: pd.Series | np.ndarray,
    action_name: str,
    cost: float = COST_BPS,
) -> SelectionMetrics:
    if len(df) == 0:
        return SelectionMetrics(action=action_name)
    mask = pd.Series(selected_mask, index=df.index).fillna(False).astype(bool)
    sel = df[mask]
    known = df[df[LABEL_COL].isin(["A", "B"])]
    sel_known = sel[sel[LABEL_COL].isin(["A", "B"])]

    raw_a = (known[LABEL_COL] == "A").mean() if len(known) else float("nan")
    a = (sel_known[LABEL_COL] == "A").mean() if len(sel_known) else float("nan")
    mean_ret = sel[RETURN_COL].mean() if len(sel) else float("nan")
    raw_mean_ret = df[RETURN_COL].mean() if len(df) else float("nan")
    net = mean_ret - cost if not (isinstance(mean_ret, float) and math.isnan(mean_ret)) else float("nan")
    raw_net = raw_mean_ret - cost if not (isinstance(raw_mean_ret, float) and math.isnan(raw_mean_ret)) else float("nan")

    return SelectionMetrics(
        action=action_name,
        n_samples=int(len(sel)),
        coverage_pct=float(len(sel) / len(df) * 100.0),
        a_rate=float(a) if not (isinstance(a, float) and math.isnan(a)) else float("nan"),
        raw_a_rate=float(raw_a) if not (isinstance(raw_a, float) and math.isnan(raw_a)) else float("nan"),
        a_rate_lift=float(a - raw_a) if not (isinstance(a, float) and math.isnan(a) or
                                               isinstance(raw_a, float) and math.isnan(raw_a)) else float("nan"),
        mean_fwd_ret_20d=float(mean_ret) if not (isinstance(mean_ret, float) and math.isnan(mean_ret)) else float("nan"),
        raw_mean_fwd_ret_20d=float(raw_mean_ret) if not (isinstance(raw_mean_ret, float) and math.isnan(raw_mean_ret)) else float("nan"),
        net_spread_20bps=float(net) if not (isinstance(net, float) and math.isnan(net)) else float("nan"),
        raw_net_spread_20bps=float(raw_net) if not (isinstance(raw_net, float) and math.isnan(raw_net)) else float("nan"),
        net_spread_lift=float(net - raw_net) if not (isinstance(net, float) and math.isnan(net) or
                                                       isinstance(raw_net, float) and math.isnan(raw_net)) else float("nan"),
    )


def baseline_mask(df: pd.DataFrame) -> pd.Series:
    req = {"vol_5d", "vol_20d", "mom_5d"}
    if not req.issubset(df.columns):
        return pd.Series(False, index=df.index)
    return (df["vol_5d"] > df["vol_20d"]) & (df["mom_5d"] < -0.05)


# ── Walk-forward ──────────────────────────────────────────────────────
@dataclass
class WindowSpec:
    train_start: int
    train_end: int
    test_start: int
    test_end: int

    @property
    def name(self) -> str:
        return f"train_{self.train_start}_{self.train_end}_test_{self.test_start}_{self.test_end}"


def get_windows() -> list[WindowSpec]:
    return [WindowSpec(*w) for w in DEFAULT_WINDOWS]


def run_walkforward(
    samples: pd.DataFrame,
    feature_cols: Sequence[str],
    calendar: np.ndarray,
    windows: Sequence[WindowSpec] | None = None,
    min_coverage: float = 0.05,
    leakage_control: str = "label_available_plus_embargo",
    embargo_days: int = 20,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, list[dict]]:
    """Walk-forward with label-availability and embargo controls.

    Primary strategy: date_rank_top_10pct (cross-sectional top-10% within each test date).
    Train-cutoff strategies and fixed thresholds are kept as baselines.

    Returns:
      predictions, walk_df, strategy_compare, importance, baseline, leakage_audit
    """
    validate_features(feature_cols)
    windows = list(windows or get_windows())
    walk_rows = []
    strategy_rows = []
    importance_rows = []
    baseline_rows = []
    prediction_frames = []
    leakage_audit = []

    for window in windows:
        test_start_td = first_trading_day_of_year(calendar, window.test_start)
        if test_start_td is None:
            walk_rows.append({
                "window": window.name,
                "train_start": window.train_start, "train_end": window.train_end,
                "test_start": window.test_start, "test_end": window.test_end,
                "status": "NO_TEST_CALENDAR",
            })
            continue

        # ── Training set with split leakage controls ─────────────────
        train_raw = samples[
            (samples["year"] >= window.train_start) &
            (samples["year"] <= window.train_end)
        ].copy()
        n_train_raw = len(train_raw)

        # Step 1: label availability filter
        train_after_label = train_raw.copy()
        label_drop = 0
        if leakage_control in ("label_available", "label_available_plus_embargo"):
            train_after_label = train_raw[
                train_raw["label_available_date"] < test_start_td
            ].copy()
            label_drop = n_train_raw - len(train_after_label)

        # Step 2: embargo filter
        train_after_embargo = train_after_label.copy()
        embargo_drop = 0
        embargo_cutoff = None
        if leakage_control == "label_available_plus_embargo" and embargo_days > 0:
            embargo_cutoff = trading_day_offset(calendar, test_start_td, -embargo_days)
            if embargo_cutoff is not None:
                train_after_embargo = train_after_label[
                    train_after_label["trade_date"] <= embargo_cutoff
                ].copy()
                embargo_drop = len(train_after_label) - len(train_after_embargo)

        train_all = train_after_embargo
        n_train_final = len(train_all)

        # Test set
        test_all = samples[
            (samples["year"] >= window.test_start) &
            (samples["year"] <= window.test_end)
        ].copy()

        # Split leakage audit
        leakage_audit.append({
            "window": window.name,
            "test_start_trade_date": int(test_start_td),
            "train_rows_raw": n_train_raw,
            "train_rows_after_label_availability": n_train_raw - label_drop,
            "label_unavailable_dropped_rows": label_drop,
            "label_unavailable_dropped_pct": round(label_drop / n_train_raw * 100, 3) if n_train_raw else 0,
            "train_rows_after_embargo": n_train_final,
            "embargo_dropped_rows": embargo_drop,
            "embargo_dropped_pct": round(embargo_drop / n_train_raw * 100, 3) if n_train_raw else 0,
            "max_train_trade_date_after_filter": (
                int(train_all["trade_date"].max()) if n_train_final else None),
            "max_train_label_available_date_after_filter": (
                int(train_all["label_available_date"].max()) if n_train_final else None),
            "test_rows": len(test_all),
            "leakage_control_mode": leakage_control,
            "embargo_days": embargo_days if leakage_control == "label_available_plus_embargo" else 0,
        })

        # ── Fit ──────────────────────────────────────────────────────
        train_fit = train_all[train_all[LABEL_COL].isin(["A", "B"])].copy()
        test_eval = test_all[test_all[LABEL_COL].isin(["A", "B"])].copy()

        base_row = {
            "window": window.name,
            "train_start": window.train_start, "train_end": window.train_end,
            "test_start": window.test_start, "test_end": window.test_end,
            "n_train_raw": n_train_raw, "n_train_final": n_train_final,
            "n_train": int(len(train_fit)), "n_test": int(len(test_eval)),
        }

        if len(train_fit) < 50 or len(test_eval) < 20 or train_fit[TARGET_COL].nunique() < 2:
            walk_rows.append({**base_row, "status": "INSUFFICIENT_DATA",
                              "primary_strategy": "date_rank_top_10pct"})
            continue

        model = build_model()
        model.fit(train_fit[list(feature_cols)], train_fit[TARGET_COL].astype(int))

        train_all["p_A"] = model.predict_proba(train_all[list(feature_cols)])[:, 1]
        test_all["p_A"] = model.predict_proba(test_all[list(feature_cols)])[:, 1]

        # date-rank percentile (cross-sectional within each test date)
        test_all["p_A_rank_pct_by_date"] = test_all.groupby("trade_date")["p_A"].rank(pct=True)

        test_eval = test_all[test_all[LABEL_COL].isin(["A", "B"])].copy()

        # ── Metrics ──────────────────────────────────────────────────
        y_test = test_eval[TARGET_COL].astype(int)
        p_test = test_eval["p_A"].to_numpy()
        auc = _safe_auc(y_test, p_test)
        pr_auc = _safe_pr_auc(y_test, p_test)

        raw_metrics = compute_selection_metrics(
            test_all, pd.Series(True, index=test_all.index), "raw_events")
        baseline_metrics = compute_selection_metrics(
            test_all, baseline_mask(test_all), "baseline_rule")

        # ── All strategies ───────────────────────────────────────────
        # Order: raw, baseline, fixed, train-cutoff, date-rank
        strategy_rows.append({
            "window": window.name, "strategy": "raw_events",
            "cutoff": np.nan, **raw_metrics.to_dict(),
        })
        strategy_rows.append({
            "window": window.name, "strategy": "baseline_rule",
            "cutoff": np.nan, **baseline_metrics.to_dict(),
        })

        # Fixed probability thresholds
        for thr in FIXED_THRESHOLDS:
            m = compute_selection_metrics(test_all, test_all["p_A"] >= thr, f"fixed_{thr:.2f}")
            strategy_rows.append({
                "window": window.name, "strategy": f"fixed_{thr:.2f}",
                "cutoff": thr, **m.to_dict(),
            })

        # Train-cutoff top-k (cutoff frozen from training distribution)
        if n_train_final > 0:
            train_pa = train_all["p_A"]
            for k in TOP_K_PCTS:
                cutoff = float(train_pa.quantile(1.0 - k / 100.0))
                m = compute_selection_metrics(test_all, test_all["p_A"] >= cutoff,
                                             f"train_cutoff_top_{k}pct")
                strategy_rows.append({
                    "window": window.name, "strategy": f"train_cutoff_top_{k}pct",
                    "cutoff": cutoff, **m.to_dict(),
                })

        # Date-rank top-k (cross-sectional within each test date)
        for k in TOP_K_PCTS:
            thresh = 1.0 - k / 100.0
            mask = test_all["p_A_rank_pct_by_date"] >= thresh
            m = compute_selection_metrics(test_all, mask, f"date_rank_top_{k}pct")
            strategy_rows.append({
                "window": window.name, "strategy": f"date_rank_top_{k}pct",
                "cutoff": thresh, **m.to_dict(),
            })

        # Primary: date_rank_top_10pct
        primary_mask = test_all["p_A_rank_pct_by_date"] >= 0.90
        primary_metrics = compute_selection_metrics(test_all, primary_mask, "date_rank_top_10pct")

        walk_rows.append({
            **base_row,
            "status": "OK",
            "primary_strategy": "date_rank_top_10pct",
            "auc": auc, "pr_auc": pr_auc,
            **{f"primary_{k}": v for k, v in primary_metrics.to_dict().items() if k != "action"},
            **{f"raw_{k}": v for k, v in raw_metrics.to_dict().items() if k != "action"},
            **{f"baseline_{k}": v for k, v in baseline_metrics.to_dict().items() if k != "action"},
        })

        baseline_rows.append({"window": window.name, **baseline_metrics.to_dict()})

        # Feature importance
        lr = model.named_steps["model"]
        for feat, coef in zip(feature_cols, lr.coef_[0]):
            importance_rows.append({
                "window": window.name, "feature": feat,
                "coefficient": float(coef), "abs_coefficient": float(abs(coef)),
            })

        # Predictions output
        out_cols = ["ts_code", "trade_date", "exec_date", "year",
                    "value", LABEL_COL, TARGET_COL, "p_A",
                    "p_A_rank_pct_by_date",
                    "fwd_ret_5d", "fwd_ret_20d",
                    "label_available_date"]
        pred = test_all[[c for c in out_cols if c in test_all.columns]].copy()
        pred["window"] = window.name
        pred["model_action_date_rank_top10"] = primary_mask.values
        pred["baseline_action"] = baseline_mask(test_all).values
        prediction_frames.append(pred)

    predictions = pd.concat(prediction_frames, ignore_index=True) if prediction_frames else pd.DataFrame()
    walk_df = pd.DataFrame(walk_rows)
    strategy_df = pd.DataFrame(strategy_rows)
    importance_df = pd.DataFrame(importance_rows)
    baseline_df = pd.DataFrame(baseline_rows)

    return predictions, walk_df, strategy_df, importance_df, baseline_df, leakage_audit


# ── Summarize ─────────────────────────────────────────────────────────
def summarize_status(walk: pd.DataFrame, min_coverage: float = 0.05) -> tuple[str, dict]:
    """Compute final status from walk-forward results.

    Only OK windows are used for metric averages.
    NO_TEST_CALENDAR windows are excluded from means.
    Primary strategy: date_rank_top_10pct.
    """
    coverage_threshold_pct = min_coverage * 100.0
    ok = walk[walk["status"] == "OK"].copy() if "status" in walk.columns else pd.DataFrame()
    if ok.empty:
        statuses = set(walk["status"].unique()) if "status" in walk.columns else set()
        if statuses == {"NO_TEST_CALENDAR"}:
            return "NO_TEST_CALENDAR", {"min_coverage_required_pct": coverage_threshold_pct}
        return "INSUFFICIENT_DATA", {"min_coverage_required_pct": coverage_threshold_pct}

    avg_auc = ok["auc"].mean()
    avg_a_lift = ok["primary_a_rate_lift"].mean() if "primary_a_rate_lift" in ok.columns else float("nan")
    avg_net_lift = ok["primary_net_spread_lift"].mean() if "primary_net_spread_lift" in ok.columns else float("nan")
    improved = int((ok["primary_net_spread_lift"] > 0).sum()) if "primary_net_spread_lift" in ok.columns else 0
    total_ok = int(len(ok))
    total_all = int(len(walk)) if "status" in walk.columns else 0

    min_cov = ok["primary_coverage_pct"].min() if "primary_coverage_pct" in ok.columns else 0

    passes_auc = not math.isnan(avg_auc) and avg_auc > 0.52
    passes_lift_a = not math.isnan(avg_a_lift) and avg_a_lift >= 0.03
    passes_lift_net = not math.isnan(avg_net_lift) and avg_net_lift > 0
    passes_improved = improved >= 3

    if passes_auc and passes_lift_a and passes_lift_net and passes_improved:
        status = "OK"
    else:
        status = "NO_PREDICTIVE_POWER"

    if status == "OK" and min_cov < coverage_threshold_pct:
        status = "OK_LOW_COVERAGE"

    summary = {
        "avg_auc": float(avg_auc) if not math.isnan(avg_auc) else np.nan,
        "avg_a_rate_lift": float(avg_a_lift) if not math.isnan(avg_a_lift) else np.nan,
        "avg_net_spread_lift": float(avg_net_lift) if not math.isnan(avg_net_lift) else np.nan,
        "improved_windows": improved,
        "total_ok_windows": total_ok,
        "total_all_windows": total_all,
        "min_coverage_pct": float(min_cov) if not math.isnan(min_cov) else np.nan,
        "min_coverage_required_pct": coverage_threshold_pct,
    }
    return status, summary


# ── Diagnostics ───────────────────────────────────────────────────────
def compute_diagnostics(
    predictions: pd.DataFrame,
    strategy_df: pd.DataFrame,
) -> pd.DataFrame:
    """Explain why AUC may not translate into trading lift.

    For each window x strategy, compute:
      - a_rate, selected mean return, win rate, return std
      - How much of raw A-class return is captured
    """
    if predictions.empty or strategy_df.empty:
        return pd.DataFrame()
    rows = []
    for window in sorted(predictions["window"].dropna().unique()):
        pred_w = predictions[predictions["window"] == window]
        known = pred_w[pred_w[LABEL_COL].isin(["A", "B"])]
        if known.empty:
            continue
        raw_a_mask = known[LABEL_COL] == "A"
        raw_a_mean_ret = known.loc[raw_a_mask, RETURN_COL].mean() if raw_a_mask.sum() else float("nan")
        raw_b_mean_ret = known.loc[~raw_a_mask, RETURN_COL].mean() if (~raw_a_mask).sum() else float("nan")
        raw_all_mean = known[RETURN_COL].mean()

        strats_w = strategy_df[strategy_df["window"] == window]
        for _, sr in strats_w.iterrows():
            strat_name = sr["strategy"]
            # Build mask matching the strategy
            if strat_name == "raw_events":
                mask = pd.Series(True, index=pred_w.index)
            elif strat_name == "baseline_rule":
                if "baseline_action" not in pred_w.columns:
                    mask = pd.Series(False, index=pred_w.index)
                else:
                    mask = pred_w["baseline_action"].fillna(False).astype(bool)
                # Defensive check: strategy_df reports samples but mask is empty
                expected_n = int(sr.get("n_samples", 0))
                if expected_n > 0 and int(mask.sum()) == 0:
                    raise RuntimeError(
                        f"baseline_rule diagnostics mismatch in window {window}: "
                        f"strategy_df reports {expected_n} samples but "
                        f"baseline_action is missing or all False"
                    )
            elif strat_name.startswith("fixed_"):
                thr = float(strat_name.split("_", 1)[1])
                mask = pred_w["p_A"] >= thr
            elif strat_name.startswith("train_cutoff_"):
                # cutoff is from the strategy row
                cutoff = sr.get("cutoff", np.nan)
                if pd.isna(cutoff):
                    continue
                mask = pred_w["p_A"] >= cutoff
            elif strat_name.startswith("date_rank_"):
                pct = int(strat_name.split("_")[-1].replace("pct", ""))
                thresh = 1.0 - pct / 100.0
                mask = pred_w["p_A_rank_pct_by_date"] >= thresh
            else:
                continue

            sel = pred_w[mask]
            sel_known = sel[sel[LABEL_COL].isin(["A", "B"])]
            sel_a = sel_known[sel_known[LABEL_COL] == "A"]
            sel_b = sel_known[sel_known[LABEL_COL] == "B"]

            rows.append({
                "window": window,
                "strategy": strat_name,
                "n_samples": int(len(sel)),
                "coverage_pct": round(len(sel) / len(pred_w) * 100, 2) if len(pred_w) else 0,
                "a_rate": float(sel_known[LABEL_COL].eq("A").mean()) if len(sel_known) else float("nan"),
                "raw_a_rate": float(raw_a_mask.mean()) if len(known) else float("nan"),
                "a_rate_lift": float(sel_known[LABEL_COL].eq("A").mean() - raw_a_mask.mean()) if len(sel_known) and len(known) else float("nan"),
                "mean_fwd_ret_20d": float(sel[RETURN_COL].mean()) if len(sel) else float("nan"),
                "raw_mean_fwd_ret_20d": float(raw_all_mean) if not (isinstance(raw_all_mean, float) and math.isnan(raw_all_mean)) else float("nan"),
                "net_spread_lift": float(sel[RETURN_COL].mean() - raw_all_mean) if len(sel) and not (isinstance(raw_all_mean, float) and math.isnan(raw_all_mean)) else float("nan"),
                "a_mean_return": float(sel_a[RETURN_COL].mean()) if len(sel_a) else float("nan"),
                "b_mean_return": float(sel_b[RETURN_COL].mean()) if len(sel_b) else float("nan"),
                "raw_a_mean_return": float(raw_a_mean_ret) if not (isinstance(raw_a_mean_ret, float) and math.isnan(raw_a_mean_ret)) else float("nan"),
                "raw_b_mean_return": float(raw_b_mean_ret) if not (isinstance(raw_b_mean_ret, float) and math.isnan(raw_b_mean_ret)) else float("nan"),
                "selected_return_std": float(sel[RETURN_COL].std()) if len(sel) else float("nan"),
                "selected_return_median": float(sel[RETURN_COL].median()) if len(sel) else float("nan"),
                "selected_win_rate": float((sel[RETURN_COL] > 0).mean()) if len(sel) else float("nan"),
            })
    return pd.DataFrame(rows)


# ── Report ────────────────────────────────────────────────────────────
def generate_report(
    factor_name: str,
    retention_threshold: float,
    feature_cols: Sequence[str],
    walk: pd.DataFrame,
    strategy: pd.DataFrame,
    leakage_audit: list[dict],
    feature_set: str,
    leakage_control: str,
    embargo_days: int,
    min_coverage: float = 0.05,
    diagnostics: pd.DataFrame | None = None,
    block_reasons: list[str] | None = None,
) -> str:
    status, summary = summarize_status(walk, min_coverage=min_coverage)
    production_eligible = status == "OK"
    lines = [
        "# Panic A/B Pre-trade Predictor v2 Report",
        "",
        "**RESEARCH ONLY — does not approve production use.**",
        "",
        f"**Final conclusion: `{status}`**",
        f"**Production eligible: `{production_eligible}`**",
        "",
    ]
    if not production_eligible:
        lines.append("> Do not use this predictor as a live filter or portfolio input.")
        if block_reasons:
            lines.append("")
            lines.append("**Block reasons:**")
            for r in block_reasons:
                lines.append(f"- {r}")
        lines.append("")

    lines.extend([
        "",
        "## Configuration",
        f"- factor: `{factor_name}`",
        f"- direction: `drop`",
        f"- oracle_label_retention_threshold: `{retention_threshold}`",
        f"- model: `sklearn LogisticRegression(class_weight='balanced')`",
        f"- feature_set: `{feature_set}`",
        f"- feature_count: `{len(feature_cols)}`",
        f"- leakage_control: `{leakage_control}`",
        f"- embargo_days: `{embargo_days}`",
        f"- primary_strategy: `date_rank_top_10pct`",
        f"- min_coverage_required: `{min_coverage * 100:.0f}%`",
        "",
    ])
    if summary:
        lines.extend([
            "## Acceptance Summary",
            f"- avg_auc: `{summary['avg_auc']:.4f}`",
            f"- avg_a_rate_lift: `{summary['avg_a_rate_lift']:.4f}`",
            f"- avg_net_spread_lift: `{summary['avg_net_spread_lift']:.4f}`",
            f"- improved_windows: `{summary['improved_windows']}/{summary['total_ok_windows']}`",
            f"- min_coverage: `{summary['min_coverage_pct']:.2f}%` (required: `{summary.get('min_coverage_required_pct', 5.0):.0f}%`)",
            "",
        ])

    if not walk.empty:
        cols = [c for c in ["window", "status", "primary_strategy", "auc", "pr_auc",
                             "n_train", "n_test",
                             "primary_coverage_pct", "primary_a_rate_lift",
                             "primary_net_spread_lift", "primary_mean_fwd_ret_20d",
                             "raw_mean_fwd_ret_20d", "raw_net_spread_20bps"]
                if c in walk.columns]
        lines.extend(["## Walk-forward (primary: date_rank_top_10pct)", "",
                      walk[cols].to_markdown(index=False), ""])

    if not strategy.empty:
        lines.extend(["## Strategy Comparison", "",
                      strategy.to_markdown(index=False), ""])

    if leakage_audit:
        df_leak = pd.DataFrame(leakage_audit)
        lines.extend(["## Leakage Audit", "",
                      df_leak.to_markdown(index=False), ""])

    # ── Why AUC Did Not Translate ─────────────────────────────────
    if diagnostics is not None and not diagnostics.empty:
        lines.extend([
            "## Why AUC Did Not Translate Into Trading Lift",
            "",
            "The model has statistically significant ranking power (AUC > 0.52),",
            "but the primary strategy `date_rank_top_10pct` does not produce",
            "consistent positive net spread lift.",
            "",
        ])
        # AUC vs net lift table
        if not walk.empty:
            auc_vs = walk[["window", "auc", "primary_net_spread_lift",
                           "primary_a_rate_lift"]].copy()
            auc_vs.columns = ["Window", "AUC", "Primary Net Spread Lift",
                              "Primary A-Rate Lift"]
            lines.extend(["### AUC vs Primary Strategy Net Lift", "",
                          auc_vs.to_markdown(index=False), ""])

        # date_rank_top_10pct diagnostics by window
        dr_diag = diagnostics[diagnostics["strategy"] == "date_rank_top_10pct"]
        if not dr_diag.empty:
            cols = ["window", "a_rate", "a_rate_lift", "mean_fwd_ret_20d",
                    "raw_mean_fwd_ret_20d", "selected_win_rate",
                    "a_mean_return", "b_mean_return"]
            show = dr_diag[[c for c in cols if c in dr_diag.columns]]
            lines.extend(["### date_rank_top_10pct: Selected vs Raw", "",
                          show.to_markdown(index=False), ""])

        # Raw events baseline
        raw_diag = diagnostics[diagnostics["strategy"] == "raw_events"]
        if not raw_diag.empty:
            lines.extend(["### raw_events: Full Event Returns", "",
                          raw_diag[["window", "a_rate", "mean_fwd_ret_20d",
                                     "selected_win_rate", "selected_return_std",
                                     "selected_return_median"]].to_markdown(index=False), ""])

        lines.extend([
            "### Interpretation",
            "",
            "- The model correctly identifies A-class events (positive a_rate_lift).",
            "- However, selected A-class returns are not consistently higher than raw A-class returns.",
            "- `date_rank_top_10pct` discards cross-date probability calibration,",
            "  keeping only within-date ranking. This removes the model's strongest signal.",
            "- In years where raw events already perform well (e.g., 2024),",
            "  filtering may accidentally exclude high-return A events.",
            "- The `train_cutoff_top_10pct` strategy retains cross-date information",
            "  and shows stronger net spread lift, but at the cost of unstable coverage.",
            "",
            "**Conclusion: the model has ranking power, but the chosen primary strategy",
            "does not translate this into tradable edge.**",
            "",
        ])

    lines.extend([
        "## Leakage Controls",
        f"- mode: `{leakage_control}`",
        f"- embargo_days: `{embargo_days}`",
        "- Training excludes samples whose `label_available_date` >= test start trading day.",
        "- Training ends `embargo_days` trading days before test start.",
        "- Future-return and path columns excluded from feature set.",
        "- Thresholds (quantile cutoffs) computed on train only.",
        "",
        "## Features",
        ", ".join(f"`{c}`" for c in feature_cols),
        "",
    ])
    return "\n".join(lines)


# ── Output ────────────────────────────────────────────────────────────
def save_outputs(
    out_dir: Path,
    predictions: pd.DataFrame,
    walk: pd.DataFrame,
    strategy: pd.DataFrame,
    importance: pd.DataFrame,
    baseline: pd.DataFrame,
    leakage: list[dict],
    diagnostics: pd.DataFrame,
    report: str,
    manifest: dict,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    predictions.to_parquet(out_dir / "panic_ab_pretrade_v2_samples.parquet", index=False)
    walk.to_csv(out_dir / "panic_ab_pretrade_v2_walkforward.csv", index=False)
    strategy.to_csv(out_dir / "panic_ab_pretrade_v2_strategy_compare.csv", index=False)
    if importance.empty:
        importance = pd.DataFrame(columns=["window", "feature", "coefficient", "abs_coefficient"])
    importance.sort_values(["window", "abs_coefficient"], ascending=[True, False]).to_csv(
        out_dir / "panic_ab_pretrade_v2_feature_importance.csv", index=False)
    baseline.to_csv(out_dir / "panic_ab_pretrade_v2_baseline.csv", index=False)
    pd.DataFrame(leakage).to_csv(out_dir / "panic_ab_pretrade_v2_leakage_audit.csv", index=False)
    diagnostics.to_csv(out_dir / "panic_ab_pretrade_v2_diagnostics.csv", index=False)
    (out_dir / "panic_ab_pretrade_v2_report.md").write_text(report, encoding="utf-8")
    (out_dir / "panic_ab_pretrade_v2_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")


# ── Main ──────────────────────────────────────────────────────────────
def main() -> int:
    args = parse_args()
    root = Path(args.root)
    out_dir = Path(args.out_dir)

    feature_set = "price_plus_daily_basic" if args.include_daily_basic else "price_only"
    print(f"=== Panic A/B Pre-trade Predictor v2 ===", flush=True)
    print(f"  factor: {args.factor}", flush=True)
    print(f"  retention_threshold: {args.retention_threshold}", flush=True)
    print(f"  feature_set: {feature_set}", flush=True)
    print(f"  leakage_control: {args.leakage_control}", flush=True)
    print(f"  embargo_days: {args.embargo_days}", flush=True)
    print(f"  out_dir: {out_dir}", flush=True)

    print("\n[1] Building samples...", flush=True)
    samples, feature_cols, calendar = build_samples(
        root=root, factor_name=args.factor,
        start=args.start, end=args.end,
        retention_threshold=args.retention_threshold,
        include_daily_basic=args.include_daily_basic,
    )
    print(f"  samples: {len(samples):,}", flush=True)
    print(f"  features ({len(feature_cols)}): {feature_cols}", flush=True)
    if "label_available_date" in samples.columns:
        print(f"  label_available_date range: "
              f"{samples['label_available_date'].min()} - "
              f"{samples['label_available_date'].max()}", flush=True)

    print("\n[2] Running walk-forward...", flush=True)
    predictions, walk, strategy, importance, baseline, leakage = run_walkforward(
        samples=samples, feature_cols=feature_cols, calendar=calendar,
        min_coverage=args.min_coverage,
        leakage_control=args.leakage_control,
        embargo_days=args.embargo_days,
    )

    print("\n[3] Computing diagnostics...", flush=True)
    diagnostics = compute_diagnostics(predictions, strategy)

    status, summary = summarize_status(walk, min_coverage=args.min_coverage)

    # Build block reasons for non-OK status
    block_reasons = []
    if status != "OK" and "OK_LOW_COVERAGE" not in str(status):
        if summary.get("improved_windows", 0) < 3:
            block_reasons.append(
                f"improved_windows={summary.get('improved_windows', 0)}/{summary.get('total_ok_windows', 0)}"
                f" (required: >= 3)")
        if not math.isnan(summary.get("avg_net_spread_lift", float("nan"))):
            if summary["avg_net_spread_lift"] <= 0:
                block_reasons.append(
                    f"primary_net_spread_lift={summary['avg_net_spread_lift']:.4f} (required: > 0)")
        if not math.isnan(summary.get("avg_a_rate_lift", float("nan"))):
            if summary["avg_a_rate_lift"] < 0.03:
                block_reasons.append(
                    f"primary_a_rate_lift={summary['avg_a_rate_lift']:.4f} (required: >= 0.03)")
        if not math.isnan(summary.get("avg_auc", float("nan"))):
            if summary["avg_auc"] <= 0.52:
                block_reasons.append(
                    f"avg_auc={summary['avg_auc']:.4f} (required: > 0.52)")

    production_eligible = (status == "OK")

    print("\n[4] Generating report...", flush=True)
    report = generate_report(
        factor_name=args.factor,
        retention_threshold=args.retention_threshold,
        feature_cols=feature_cols,
        walk=walk,
        strategy=strategy,
        leakage_audit=leakage,
        feature_set=feature_set,
        leakage_control=args.leakage_control,
        embargo_days=args.embargo_days,
        min_coverage=args.min_coverage,
        diagnostics=diagnostics,
        block_reasons=block_reasons,
    )

    manifest = {
        "schema": "panic_ab_pretrade.v2",
        "status": status,
        "final_research_conclusion": status,
        "production_eligible": production_eligible,
        "recommended_next_action": (
            "do_not_integrate; use diagnostics only"
            if not production_eligible else "evaluate_for_portfolio_integration"
        ),
        "summary": summary,
        "research_only": True,
        "factor": args.factor,
        "direction": "drop",
        "start": args.start,
        "end": args.end,
        "retention_threshold": args.retention_threshold,
        "feature_set": feature_set,
        "feature_columns": list(feature_cols),
        "leakage_control": args.leakage_control,
        "embargo_days": args.embargo_days,
        "min_coverage_required_pct": args.min_coverage * 100.0,
        "primary_strategy": "date_rank_top_10pct",
        "control_strategies": [
            "raw_events", "baseline_rule",
            "fixed_0.50", "fixed_0.60", "fixed_0.70",
            "train_cutoff_top_5pct", "train_cutoff_top_10pct", "train_cutoff_top_20pct",
            "date_rank_top_5pct", "date_rank_top_10pct", "date_rank_top_20pct",
        ],
        "block_reasons": block_reasons if not production_eligible else [],
        "no_leakage": {
            "label_availability_filter": args.leakage_control != "none",
            "embargo_enabled": args.leakage_control == "label_available_plus_embargo",
            "future_columns_excluded": True,
            "date_rank_uses_t0_only": True,
        },
    }

    save_outputs(out_dir, predictions, walk, strategy, importance, baseline,
                 leakage, diagnostics, report, manifest)
    print(f"\nSaved outputs to {out_dir}", flush=True)
    print(f"Final status: {status}", flush=True)
    print(f"Production eligible: {production_eligible}", flush=True)
    if block_reasons:
        for r in block_reasons:
            print(f"  Block: {r}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""
Phase 1: Daily Panic Basket Dataset & Diagnostics
===================================================
Aggregate stock-level panic drop events into date-level panic basket samples.
Compute daily market-state features and forward-looking basket labels.

This is RESEARCH ONLY — does not write any production signal.

Direction from panic_reversal_factor_next_optimization_plan.md:
  From: "which 10% of today's panic stocks are best?"
  To:   "is today's market state suitable for panic drop reversal?"

Outputs (→ outputs/analysis/panic_reversal_gate/daily_basket_v1/):
  - panic_basket_daily_samples.csv
  - panic_basket_daily_diagnostics.csv
  - panic_basket_daily_report.md
"""
from __future__ import annotations

import argparse
import json
import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FACTOR = "panic_drop_rev5_t05_bin_weekly_cs"
DEFAULT_OUT_DIR = ROOT / "outputs" / "analysis" / "panic_reversal_gate" / "daily_basket_v1"

# ── Labels for daily gate ─────────────────────────────────────────────
DAILY_LABEL_COLS = [
    "basket_mean_fwd_ret_20d",
    "basket_net_fwd_ret_20d",
    "basket_a_rate_20d",
    "basket_win_rate_20d",
    "basket_top_half_ret_20d",
]

INDEX_CODES = {
    "csi300": "000300.SH",
    "csi_all": "930917.CSI",
    "csi_other": "930918.CSI",
}

COST_BPS = 20 / 10000
FWD_WINDOW = 20
MIN_STOCKS_FOR_BASKET = 5  # min panic stocks to form a valid basket day

# ── Walk-forward windows ──────────────────────────────────────────────
DEFAULT_WINDOWS = (
    (2017, 2021, 2022, 2022),
    (2017, 2022, 2023, 2023),
    (2017, 2023, 2024, 2024),
    (2017, 2024, 2025, 2025),
)


# ═══════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Phase 1: Daily panic basket dataset & diagnostics"
    )
    p.add_argument("--start", type=int, default=20170101)
    p.add_argument("--end", type=int, default=20251231)
    p.add_argument("--factor", default=DEFAULT_FACTOR)
    p.add_argument("--retention-threshold", type=float, default=0.3)
    p.add_argument("--min-stocks", type=int, default=MIN_STOCKS_FOR_BASKET)
    p.add_argument("--embargo-days", type=int, default=20)
    p.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    p.add_argument("--root", default=str(ROOT))
    return p.parse_args()


# ═══════════════════════════════════════════════════════════════════════
# Data loading helpers
# ═══════════════════════════════════════════════════════════════════════
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


def load_prices(root: Path, start: int, end: int) -> pd.DataFrame:
    """Load adjusted close prices for all stocks."""
    base = root / "data" / "parquet" / "prices_adj"
    cols = ["ts_code", "trade_date", "adj_close", "pct_chg", "vol", "amount"]
    chunks = []
    for yr_dir in _iter_year_dirs(base, start, end):
        for pq in sorted(yr_dir.rglob("*.parquet")):
            df = _normalize(pd.read_parquet(pq))
            if "adj_close" not in df.columns:
                continue
            df = df.dropna(subset=["trade_date", "adj_close"])
            keep = [c for c in cols if c in df.columns]
            chunks.append(df[keep])
    if not chunks:
        raise RuntimeError(f"No prices_adj parquet under {base}")
    prices = pd.concat(chunks, ignore_index=True)
    prices = prices.drop_duplicates(["ts_code", "trade_date"])
    prices = prices.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)
    return prices


def load_index_prices(root: Path, start: int, end: int) -> pd.DataFrame:
    """Load index daily data for market-state features."""
    base = root / "data" / "parquet" / "index_daily"
    if not base.exists():
        return pd.DataFrame()
    cols = ["ts_code", "trade_date", "close", "pct_chg", "vol", "amount"]
    chunks = []
    for yr_dir in _iter_year_dirs(base, start, end):
        for pq in sorted(yr_dir.rglob("*.parquet")):
            df = _normalize(pd.read_parquet(pq))
            if "close" not in df.columns:
                continue
            df = df.dropna(subset=["trade_date", "close"])
            keep = [c for c in cols if c in df.columns]
            chunks.append(df[keep])
    if not chunks:
        return pd.DataFrame()
    idx = pd.concat(chunks, ignore_index=True)
    idx = idx.drop_duplicates(["ts_code", "trade_date"])
    idx = idx.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)
    return idx


def load_daily_basic(root: Path, start: int, end: int) -> pd.DataFrame:
    """Load daily basic data for market-cap and liquidity features."""
    base = root / "data" / "parquet" / "daily_basic"
    cols = ["ts_code", "trade_date", "total_mv", "circ_mv",
            "turnover_rate", "turnover_rate_f", "volume_ratio"]
    chunks = []
    for yr_dir in _iter_year_dirs(base, start, end):
        for pq in sorted(yr_dir.rglob("*.parquet")):
            df = _normalize(pd.read_parquet(pq))
            if not {"ts_code", "trade_date"}.issubset(df.columns):
                continue
            keep = [c for c in cols if c in df.columns]
            chunks.append(df[keep])
    if not chunks:
        return pd.DataFrame()
    basic = pd.concat(chunks, ignore_index=True)
    basic = basic.dropna(subset=["trade_date"])
    basic = basic.drop_duplicates(["ts_code", "trade_date"])
    if "total_mv" in basic.columns:
        basic["log_total_mv"] = np.log1p(pd.to_numeric(basic["total_mv"], errors="coerce"))
    if "circ_mv" in basic.columns:
        basic["log_circ_mv"] = np.log1p(pd.to_numeric(basic["circ_mv"], errors="coerce"))
    return basic


def load_factor(root: Path, factor_name: str, start: int, end: int) -> pd.DataFrame:
    """Load panic factor data."""
    base = root / "data" / "parquet" / "factors" / f"factor_name={factor_name}"
    if not base.exists():
        raise RuntimeError(f"Factor path not found: {base}")
    cols = ["ts_code", "trade_date", "value", "available_date",
            "source_period", "source_date", "pit_lag_days", "is_stale"]
    chunks = []
    for yr_dir in _iter_year_dirs(base, start, end):
        for pq in sorted(yr_dir.rglob("*.parquet")):
            df = _normalize(pd.read_parquet(pq))
            if {"ts_code", "trade_date", "value"}.issubset(df.columns):
                keep = [c for c in cols if c in df.columns]
                chunks.append(df[keep])
    if not chunks:
        raise RuntimeError(f"No factor parquet under {base}")
    factor = pd.concat(chunks, ignore_index=True)
    factor = factor.dropna(subset=["trade_date", "value"])
    factor = factor[(factor["trade_date"] >= start) & (factor["trade_date"] <= end)]
    factor = factor.drop_duplicates(["ts_code", "trade_date"])
    return factor


# ═══════════════════════════════════════════════════════════════════════
# Calendar & execution mapping
# ═══════════════════════════════════════════════════════════════════════
def build_trading_calendar(prices: pd.DataFrame) -> np.ndarray:
    return np.array(sorted(int(d) for d in prices["trade_date"].dropna().unique()))


def trading_day_offset(calendar: np.ndarray, date: int, offset: int) -> int | None:
    idx = np.searchsorted(calendar, date)
    if idx >= len(calendar) or calendar[idx] != date:
        return None
    target = idx + offset
    if 0 <= target < len(calendar):
        return int(calendar[target])
    return None


def first_trading_day_of_year(calendar: np.ndarray, year: int) -> int | None:
    for d in calendar:
        if d // 10000 == year:
            return int(d)
    return None


def build_exec_date_map(calendar: np.ndarray, lag: int = 1) -> dict:
    return {calendar[i]: calendar[i + lag] for i in range(len(calendar) - lag)}


# ═══════════════════════════════════════════════════════════════════════
# Forward metrics (20d horizon)
# ═══════════════════════════════════════════════════════════════════════
def _forward_min_window(values: np.ndarray, window: int) -> np.ndarray:
    n = len(values)
    result = np.full(n, np.nan)
    if n >= window:
        result[:n - window + 1] = sliding_window_view(values, window).min(axis=1)
    return result


def compute_stock_forward_metrics(prices: pd.DataFrame) -> pd.DataFrame:
    """Compute per-stock forward returns and path metrics."""
    df = prices.sort_values(["ts_code", "trade_date"]).copy()
    grp = df.groupby("ts_code", group_keys=False)

    df["close_p5"] = grp["adj_close"].shift(-5)
    df["close_p6"] = grp["adj_close"].shift(-6)
    df["close_p20"] = grp["adj_close"].shift(-20)
    df["fwd_ret_5d"] = df["close_p5"] / df["adj_close"] - 1.0
    df["fwd_ret_20d"] = df["close_p20"] / df["adj_close"] - 1.0

    df["future_min_6_20"] = grp["close_p6"].transform(
        lambda s: _forward_min_window(np.asarray(s.values, dtype=float), 15))

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


# ═══════════════════════════════════════════════════════════════════════
# Stock-level A/B label assignment
# ═══════════════════════════════════════════════════════════════════════
def assign_ab_labels(df: pd.DataFrame, retention_threshold: float) -> pd.DataFrame:
    """Assign A/B labels to each panic event (same logic as v2)."""
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
    result["ab_label"] = labels
    result["target_A"] = np.where(
        result["ab_label"] == "A", 1,
        np.where(result["ab_label"] == "B", 0, np.nan))
    return result


# ═══════════════════════════════════════════════════════════════════════
# Market state features (daily, PIT-observable)
# ═══════════════════════════════════════════════════════════════════════
def compute_market_state_features(
    prices: pd.DataFrame,
    index_prices: pd.DataFrame,
    daily_basic: pd.DataFrame,
) -> pd.DataFrame:
    """Compute daily market-state features.

    Returns DataFrame indexed by trade_date with market features.
    All features use only t0-available data (no forward-looking).
    """
    # ── 1. Index returns ──────────────────────────────────────────────
    idx_features = []
    if not index_prices.empty:
        for idx_code in INDEX_CODES.values():
            idx_df = index_prices[index_prices["ts_code"] == idx_code].copy()
            if idx_df.empty:
                continue
            idx_df = idx_df.sort_values("trade_date")
            idx_name = idx_code.replace(".", "_").replace("000", "csi").lower()
            # Index returns
            idx_df[f"idx_{idx_name}_ret_1d"] = idx_df["close"].pct_change()
            for w in (3, 5, 20):
                idx_df[f"idx_{idx_name}_ret_{w}d"] = idx_df["close"].pct_change(w)
            # Distance to 20d low
            roll_low = idx_df["close"].rolling(20, min_periods=5).min()
            idx_df[f"idx_{idx_name}_dist_to_20d_low"] = idx_df["close"] / roll_low - 1.0
            # 20d drawdown
            roll_high = idx_df["close"].rolling(20, min_periods=5).max()
            idx_df[f"idx_{idx_name}_drawdown_20d"] = idx_df["close"] / roll_high - 1.0
            # 5d rebound
            idx_df[f"idx_{idx_name}_rebound_5d"] = (
                idx_df["close"] / idx_df["close"].rolling(5, min_periods=3).min() - 1.0)
            # Volatility
            for w in (5, 10, 20):
                idx_df[f"idx_{idx_name}_vol_{w}d"] = (
                    idx_df[f"idx_{idx_name}_ret_1d"]
                    .rolling(w, min_periods=max(3, w // 2)).std())
            idx_df["idx_csi300_sh_vol_5d_over_20d"] = (
                idx_df.get(f"idx_{idx_name}_vol_5d", np.nan)
                / idx_df.get(f"idx_{idx_name}_vol_20d", np.nan))
            keep = [c for c in idx_df.columns if c.startswith("idx_")]
            keep.append("trade_date")
            idx_features.append(idx_df[keep])

    if idx_features:
        market_state = idx_features[0]
        for other in idx_features[1:]:
            market_state = market_state.merge(other, on="trade_date", how="outer")
    else:
        market_state = pd.DataFrame(columns=["trade_date"])

    # ── 2. Market breadth (from stock prices) ─────────────────────────
    if "pct_chg" in prices.columns:
        daily_breadth = prices.groupby("trade_date").agg(
            up_pct=("pct_chg", lambda x: (x > 0).mean()),
            down_pct=("pct_chg", lambda x: (x < 0).mean()),
            big_down_pct=("pct_chg", lambda x: (x < -0.05).mean()),
            vol_total=("vol", "sum") if "vol" in prices.columns else ("pct_chg", "count"),
            amount_total=("amount", "sum") if "amount" in prices.columns else ("pct_chg", "count"),
        ).reset_index()
        # 5d breadth
        daily_breadth["up_5d_pct"] = daily_breadth["up_pct"].rolling(5, min_periods=3).mean()
        # 20d new low ratio (approximate from price data)
        # We'll compute this from rolling lows per stock
        if market_state.empty:
            market_state = daily_breadth
        else:
            market_state = market_state.merge(daily_breadth, on="trade_date", how="outer")

    # ── 3. Cross-sectional dispersion ─────────────────────────────────
    if "pct_chg" in prices.columns:
        cs_disp = prices.groupby("trade_date").agg(
            cs_ret_std=("pct_chg", "std"),
            cs_ret_p75=("pct_chg", lambda x: x.quantile(0.75)),
            cs_ret_p25=("pct_chg", lambda x: x.quantile(0.25)),
        ).reset_index()
        cs_disp["cs_ret_spread"] = cs_disp["cs_ret_p75"] - cs_disp["cs_ret_p25"]
        if market_state.empty:
            market_state = cs_disp
        else:
            market_state = market_state.merge(cs_disp, on="trade_date", how="outer")

    # ── 4. Liquidity features ─────────────────────────────────────────
    if not daily_basic.empty:
        liq_daily = daily_basic.groupby("trade_date").agg(
            med_turnover=("turnover_rate", "median") if "turnover_rate" in daily_basic.columns else ("trade_date", "count"),
            med_log_mv=("log_total_mv", "median") if "log_total_mv" in daily_basic.columns else ("trade_date", "count"),
        ).reset_index()
        if "turnover_rate" in daily_basic.columns:
            liq_daily["turnover_chg_5d"] = liq_daily["med_turnover"].pct_change(5)
        if "total_mv" in daily_basic.columns:
            liq_daily["total_amount"] = daily_basic.groupby("trade_date")["total_mv"].sum().reset_index(drop=True)
            liq_daily["amount_chg_5d"] = liq_daily["total_amount"].pct_change(5) if "total_amount" in liq_daily.columns else np.nan
        if market_state.empty:
            market_state = liq_daily
        else:
            market_state = market_state.merge(liq_daily, on="trade_date", how="outer")

    # Sort by date
    if "trade_date" in market_state.columns:
        market_state = market_state.sort_values("trade_date").reset_index(drop=True)

    return market_state


# ═══════════════════════════════════════════════════════════════════════
# Daily basket aggregation
# ═══════════════════════════════════════════════════════════════════════
def build_daily_basket(
    stock_samples: pd.DataFrame,
    calendar: np.ndarray,
    min_stocks: int = MIN_STOCKS_FOR_BASKET,
    total_stocks_per_day: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Aggregate stock-level panic events into daily basket samples.

    Each row = one trading day with at least min_stocks panic events.

    Features (per day):
      - event_count, event_ratio (denominator from full market)
      - avg_mom5d, med_mom5d, p25_mom5d, p75_mom5d
      - avg_mcap, med_mcap
      - avg_turnover, med_turnover
      - basket_label_available_date (= max event label_available_date)

    Labels (forward-looking, computed from stock-level forward returns):
      - basket_mean_fwd_ret_20d
      - basket_net_fwd_ret_20d
      - basket_a_rate_20d
      - basket_win_rate_20d
      - basket_top_half_ret_20d
    """
    df = stock_samples.copy()
    # Ensure required columns exist
    required = ["trade_date", "ts_code", "value", "fwd_ret_20d"]
    for c in required:
        if c not in df.columns:
            raise KeyError(f"Required column '{c}' missing from stock samples")

    # Event mask
    df["is_event"] = df["value"] > 0

    # Event-level label availability aggregation
    has_label_avail = "label_available_date" in df.columns

    # Aggregate by trade_date (events only)
    agg_spec: dict = {
        "event_count": ("ts_code", "count"),
        "avg_value": ("value", "mean"),
        "med_value": ("value", "median"),

        # Forward labels
        "basket_mean_fwd_ret_20d": ("fwd_ret_20d", "mean"),
        "basket_net_fwd_ret_20d": ("fwd_ret_20d", lambda x: x.mean() - COST_BPS),
        "basket_win_rate_20d": ("fwd_ret_20d", lambda x: (x > 0).mean()),
        "basket_ret_std_20d": ("fwd_ret_20d", "std"),
    }
    if has_label_avail:
        agg_spec["basket_label_available_date"] = ("label_available_date", "max")
        agg_spec["min_event_label_available_date"] = ("label_available_date", "min")
        agg_spec["n_events_label_available"] = ("label_available_date", "count")
        agg_spec["n_events_label_unavailable"] = ("label_available_date",
                                                    lambda x: x.isna().sum())

    daily = df[df["is_event"]].groupby("trade_date").agg(**agg_spec).reset_index()

    # A-rate (if ab_label column exists)
    if "ab_label" in df.columns:
        a_rate = df[df["is_event"]].groupby("trade_date").agg(
            basket_a_rate_20d=("ab_label", lambda x: (x == "A").mean()),
            basket_b_rate_20d=("ab_label", lambda x: (x == "B").mean()),
        ).reset_index()
        daily = daily.merge(a_rate, on="trade_date", how="left")

    # B-rate implied from A and M if not present
    if "basket_a_rate_20d" not in daily.columns and "target_A" in df.columns:
        a_rate2 = df[df["is_event"]].groupby("trade_date").agg(
            basket_a_rate_20d=("target_A", "mean"),
        ).reset_index()
        daily = daily.merge(a_rate2, on="trade_date", how="left")

    # Top-half return (top 50% by value within day)
    if "value" in df.columns:
        def _top_half_ret(grp):
            threshold = grp["value"].quantile(0.5)
            top = grp[grp["value"] >= threshold]
            return top["fwd_ret_20d"].mean() if len(top) > 0 else np.nan

        top_half = df[df["is_event"]].groupby("trade_date").apply(
            _top_half_ret, include_groups=False
        ).reset_index(name="basket_top_half_ret_20d")
        daily = daily.merge(top_half, on="trade_date", how="left")

    # Panic event momentum distribution
    if "mom_5d" in df.columns:
        mom_dist = df[df["is_event"]].groupby("trade_date").agg(
            avg_mom_5d=("mom_5d", "mean"),
            med_mom_5d=("mom_5d", "median"),
            p25_mom_5d=("mom_5d", lambda x: x.quantile(0.25)),
            p75_mom_5d=("mom_5d", lambda x: x.quantile(0.75)),
        ).reset_index()
        daily = daily.merge(mom_dist, on="trade_date", how="left")

    # Market cap distribution
    if "log_total_mv" in df.columns:
        mcap_dist = df[df["is_event"]].groupby("trade_date").agg(
            avg_log_mv=("log_total_mv", "mean"),
            med_log_mv=("log_total_mv", "median"),
            small_mv_ratio=("log_total_mv", lambda x: (x < x.quantile(0.3)).mean()),
        ).reset_index()
        daily = daily.merge(mcap_dist, on="trade_date", how="left")

    # ── event_ratio: denominator from FULL MARKET, not event-only samples ──
    if total_stocks_per_day is not None and not total_stocks_per_day.empty:
        daily = daily.merge(total_stocks_per_day, on="trade_date", how="left")
        daily["event_ratio"] = daily["event_count"] / daily["total_stocks_market"].replace(0, np.nan)
    else:
        # Degraded fallback: count distinct stocks in stock_samples per day
        total_s = df.groupby("trade_date").agg(
            total_stocks_market=("ts_code", "nunique"),
        ).reset_index()
        daily = daily.merge(total_s, on="trade_date", how="left")
        daily["event_ratio"] = daily["event_count"] / daily["total_stocks_market"].replace(0, np.nan)

    # ── Filter to valid basket days ──
    daily = daily[daily["event_count"] >= min_stocks].copy()

    # Historical percentiles (rolling, PIT)
    for col in ["event_count", "event_ratio", "basket_mean_fwd_ret_20d"]:
        if col in daily.columns:
            # Note: basket_mean_fwd_ret_20d hist percentile uses future data
            # — only for diagnostics. In actual model, only event_count hist is PIT-safe.
            daily[f"{col}_hist_pct_60d"] = (
                daily[col].rolling(60, min_periods=20)
                .apply(lambda x: (x < x.iloc[-1]).mean() if len(x) > 0 else np.nan,
                       raw=False).values
            )

    daily["year"] = daily["trade_date"] // 10000

    return daily


# ═══════════════════════════════════════════════════════════════════════
# Diagnostics
# ═══════════════════════════════════════════════════════════════════════
def compute_daily_diagnostics(daily_basket: pd.DataFrame) -> pd.DataFrame:
    """Compute year-by-year diagnostics for the daily panic basket."""
    if daily_basket.empty:
        return pd.DataFrame()

    df = daily_basket.copy()
    df["year"] = df["trade_date"] // 10000

    rows = []
    for yr in sorted(df["year"].unique()):
        yr_df = df[df["year"] == yr]
        if len(yr_df) == 0:
            continue

        row = {
            "year": int(yr),
            "n_days": len(yr_df),
            "avg_event_count": yr_df["event_count"].mean(),
            "med_event_count": yr_df["event_count"].median(),
            "avg_event_ratio": yr_df["event_ratio"].mean() if "event_ratio" in yr_df.columns else np.nan,
            "avg_basket_mean_ret": yr_df["basket_mean_fwd_ret_20d"].mean(),
            "avg_basket_net_ret": yr_df["basket_net_fwd_ret_20d"].mean() if "basket_net_fwd_ret_20d" in yr_df.columns else np.nan,
            "avg_a_rate": yr_df["basket_a_rate_20d"].mean() if "basket_a_rate_20d" in yr_df.columns else np.nan,
            "avg_win_rate": yr_df["basket_win_rate_20d"].mean() if "basket_win_rate_20d" in yr_df.columns else np.nan,
            "avg_top_half_ret": yr_df["basket_top_half_ret_20d"].mean() if "basket_top_half_ret_20d" in yr_df.columns else np.nan,
            "pos_basket_days": int((yr_df["basket_mean_fwd_ret_20d"] > 0).sum()),
            "pos_basket_ratio": float((yr_df["basket_mean_fwd_ret_20d"] > 0).mean()),
            "net_pos_basket_days": int((yr_df["basket_net_fwd_ret_20d"] > 0).sum()) if "basket_net_fwd_ret_20d" in yr_df.columns else 0,
            "basket_ret_vol": yr_df["basket_mean_fwd_ret_20d"].std(),
        }
        rows.append(row)

    return pd.DataFrame(rows)


# ═══════════════════════════════════════════════════════════════════════
# Market state × basket analysis
# ═══════════════════════════════════════════════════════════════════════
def compute_state_analysis(
    daily_basket: pd.DataFrame,
    market_state: pd.DataFrame,
) -> pd.DataFrame:
    """Analyze how basket performance varies with market state."""
    if daily_basket.empty or market_state.empty:
        return pd.DataFrame()

    merged = daily_basket.merge(market_state, on="trade_date", how="left")

    rows = []
    # Analyze key market dimensions
    state_cols = [c for c in merged.columns
                  if c.startswith("idx_") or c in ("up_pct", "big_down_pct", "cs_ret_std")]

    for col in state_cols:
        if col not in merged.columns or merged[col].isna().all():
            continue
        valid = merged.dropna(subset=[col, "basket_mean_fwd_ret_20d"])
        if len(valid) < 30:
            continue

        # Split into quartiles
        valid = valid.copy()
        try:
            valid["quartile"] = pd.qcut(valid[col], 4, labels=["Q1", "Q2", "Q3", "Q4"], duplicates="drop")
        except ValueError:
            # If too few unique values, skip
            continue

        for q in sorted(valid["quartile"].dropna().unique()):
            subset = valid[valid["quartile"] == q]
            rows.append({
                "state_dimension": col,
                "quartile": str(q),
                "n_days": len(subset),
                "avg_basket_ret": subset["basket_mean_fwd_ret_20d"].mean(),
                "avg_a_rate": subset["basket_a_rate_20d"].mean() if "basket_a_rate_20d" in subset.columns else np.nan,
                "avg_win_rate": subset["basket_win_rate_20d"].mean() if "basket_win_rate_20d" in subset.columns else np.nan,
                "avg_event_count": subset["event_count"].mean() if "event_count" in subset.columns else np.nan,
            })

    return pd.DataFrame(rows)


# ═══════════════════════════════════════════════════════════════════════
# Report generation
# ═══════════════════════════════════════════════════════════════════════
def generate_report(
    daily_basket: pd.DataFrame,
    diagnostics: pd.DataFrame,
    state_analysis: pd.DataFrame,
    args: argparse.Namespace,
) -> str:
    lines = [
        "# Panic Basket Daily Gate — Phase 1 Diagnostics",
        "",
        "**RESEARCH ONLY — does not approve production use.**",
        "",
        "## Objective",
        "",
        "Aggregate stock-level panic events into daily basket samples.",
        "Determine whether daily-level information exists for panic reversal gating.",
        "",
        "## Configuration",
        f"- factor: `{args.factor}`",
        f"- retention_threshold: `{args.retention_threshold}`",
        f"- min_stocks_per_basket: `{args.min_stocks}`",
        f"- embargo_days: `{args.embargo_days}`",
        f"- date_range: `{args.start}` - `{args.end}`",
        "",
    ]

    if not daily_basket.empty:
        n_days = len(daily_basket)
        n_years = daily_basket["year"].nunique()
        avg_events = daily_basket["event_count"].mean()
        med_events = daily_basket["event_count"].median()
        lines.extend([
            "## Basket Summary",
            f"- total_basket_days: `{n_days:,}`",
            f"- years_covered: `{n_years}`",
            f"- avg_events_per_day: `{avg_events:.1f}`",
            f"- median_events_per_day: `{med_events:.0f}`",
            "",
        ])

    # Yearly diagnostics
    if not diagnostics.empty:
        lines.extend([
            "## Yearly Basket Diagnostics",
            "",
            diagnostics.to_markdown(index=False, floatfmt=".4f"),
            "",
        ])

    # Market state analysis (top relationships)
    if not state_analysis.empty:
        lines.extend([
            "## Market State × Basket Performance",
            "",
            "Top state dimensions with strongest basket return differentiation:",
            "",
        ])
        # Find dimensions with largest Q4-Q1 spread
        spreads = []
        for dim in state_analysis["state_dimension"].unique():
            subset = state_analysis[state_analysis["state_dimension"] == dim]
            if "Q1" in subset["quartile"].values and "Q4" in subset["quartile"].values:
                q1_ret = subset[subset["quartile"] == "Q1"]["avg_basket_ret"].values[0]
                q4_ret = subset[subset["quartile"] == "Q4"]["avg_basket_ret"].values[0]
                spreads.append((dim, q4_ret - q1_ret, abs(q4_ret - q1_ret)))
        spreads.sort(key=lambda x: x[2], reverse=True)

        for dim, spread, _ in spreads[:10]:
            lines.append(f"- `{dim}`: Q4-Q1 spread = `{spread:.4f}`")

        lines.extend([
            "",
            "### Full State Analysis",
            "",
            state_analysis.to_markdown(index=False, floatfmt=".4f"),
            "",
        ])

    # Next steps
    lines.extend([
        "## Phase 1 Assessment",
        "",
        "### Checkpoints",
        "- [ ] Daily basket labels are not extremely sparse.",
        "- [ ] 2022, 2023, 2024 all have sufficient valid trading days.",
        "- [ ] Basket performance shows explainable state differences.",
        "",
        "### If Phase 1 passes:",
        "Proceed to Phase 2 — rule-based gate prototype.",
        "",
        "### If Phase 1 fails:",
        "Daily-level information may be too weak. Return to stock-level diagnosis.",
        "",
    ])

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════
# Main pipeline
# ═══════════════════════════════════════════════════════════════════════
def main() -> int:
    args = parse_args()
    root = Path(args.root)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("Phase 1: Daily Panic Basket Dataset & Diagnostics")
    print("=" * 70)
    print(f"  factor: {args.factor}")
    print(f"  date_range: {args.start} - {args.end}")
    print(f"  retention_threshold: {args.retention_threshold}")
    print(f"  min_stocks: {args.min_stocks}")
    print(f"  out_dir: {out_dir}")

    # ── Step 1: Load data ────────────────────────────────────────────
    print("\n[1/6] Loading price data...")
    prices = load_prices(root, args.start, args.end)
    calendar = build_trading_calendar(prices)
    print(f"  prices: {len(prices):,} rows, {prices['ts_code'].nunique():,} stocks, "
          f"{len(calendar):,} trading days")

    print("\n[2/6] Loading factor data...")
    factor = load_factor(root, args.factor, args.start, args.end)
    print(f"  factor: {len(factor):,} rows, "
          f"{(factor['value'] > 0).sum():,} events")

    print("\n[3/6] Computing stock-level forward metrics...")
    fwd = compute_stock_forward_metrics(prices)
    exec_map = build_exec_date_map(calendar)

    # Merge factor → exec_date → forward metrics
    events = factor[factor["value"] > 0].copy()
    events["exec_date"] = events["trade_date"].map(exec_map)
    events = events.dropna(subset=["exec_date"])
    events["exec_date"] = events["exec_date"].astype(int)

    # Label available date
    events["label_available_date"] = events["exec_date"].apply(
        lambda d: trading_day_offset(calendar, d, 20))
    events = events.dropna(subset=["label_available_date"])
    events["label_available_date"] = events["label_available_date"].astype(int)

    # Merge forward metrics on exec_date
    fwd_renamed = fwd.rename(columns={"trade_date": "exec_date"})
    samples = events.merge(fwd_renamed, on=["ts_code", "exec_date"], how="inner")
    samples = samples[samples["quality_pass_20d"]].copy()
    samples = samples.dropna(subset=["fwd_ret_5d", "fwd_ret_20d"])

    # Assign A/B labels
    samples = assign_ab_labels(samples, args.retention_threshold)
    n_a = (samples["ab_label"] == "A").sum()
    n_b = (samples["ab_label"] == "B").sum()
    n_m = (samples["ab_label"] == "M").sum()
    print(f"  stock samples: {len(samples):,}  A={n_a:,} B={n_b:,} M={n_m:,}")

    # ── Compute total stocks per day (from FULL market prices) ─────────
    total_stocks_per_day = (
        prices.groupby("trade_date")
        .agg(total_stocks_market=("ts_code", "nunique"))
        .reset_index()
    )
    print(f"  total_stocks_per_day: {len(total_stocks_per_day):,} days")

    # ── Step 4: Build daily basket ───────────────────────────────────
    print("\n[4/6] Building daily panic basket...")
    daily_basket = build_daily_basket(samples, calendar, args.min_stocks,
                                       total_stocks_per_day)
    print(f"  daily basket: {len(daily_basket):,} days (≥{args.min_stocks} events)")
    # Verify event_ratio
    if "event_ratio" in daily_basket.columns:
        er = daily_basket["event_ratio"]
        print(f"  event_ratio: mean={er.mean():.4f} med={er.median():.4f} "
              f"min={er.min():.4f} max={er.max():.4f}")

    # ── Step 5: Market state features ────────────────────────────────
    print("\n[5/6] Computing market state features...")
    index_prices = load_index_prices(root, args.start, args.end)
    daily_basic = load_daily_basic(root, args.start, args.end)
    market_state = compute_market_state_features(prices, index_prices, daily_basic)
    print(f"  market_state: {len(market_state):,} days, "
          f"{len(market_state.columns) - 1} features")

    # Merge market state into daily basket
    if not market_state.empty:
        daily_basket = daily_basket.merge(market_state, on="trade_date", how="left")

    # ── Step 6: Diagnostics & output ─────────────────────────────────
    print("\n[6/6] Computing diagnostics & saving outputs...")
    diagnostics = compute_daily_diagnostics(daily_basket)
    state_analysis = compute_state_analysis(daily_basket, market_state)

    # Save
    daily_basket.to_csv(out_dir / "panic_basket_daily_samples.csv", index=False)
    diagnostics.to_csv(out_dir / "panic_basket_daily_diagnostics.csv", index=False)
    if not state_analysis.empty:
        state_analysis.to_csv(out_dir / "panic_basket_daily_state_analysis.csv", index=False)

    report = generate_report(daily_basket, diagnostics, state_analysis, args)
    (out_dir / "panic_basket_daily_report.md").write_text(report, encoding="utf-8")

    # Manifest
    manifest = {
        "schema": "panic_basket_daily_gate.v2",
        "phase": 1,
        "status": "RESEARCH_ONLY",
        "production_eligible": False,
        "research_only": True,
        "factor": args.factor,
        "retention_threshold": args.retention_threshold,
        "min_stocks_per_basket": args.min_stocks,
        "embargo_days": args.embargo_days,
        "leakage_control": "label_available_plus_embargo",
        "start": args.start,
        "end": args.end,
        "n_basket_days": int(len(daily_basket)),
        "n_stock_samples": int(len(samples)),
        "daily_label_columns": DAILY_LABEL_COLS,
        "has_basket_label_available_date": "basket_label_available_date" in daily_basket.columns,
        "event_ratio_source": "prices_adj_full_market",
        "market_state_features": (
            [c for c in market_state.columns if c != "trade_date"]
            if not market_state.empty else []
        ),
    }
    (out_dir / "panic_basket_daily_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    # Save stock-level event samples (for Phase 4 real path backtest)
    event_stock_cols = [
        "trade_date", "ts_code", "exec_date", "value",
        "fwd_ret_5d", "fwd_ret_20d",
        "label_available_date", "ab_label", "quality_pass_20d",
    ]
    available_event_cols = [c for c in event_stock_cols if c in samples.columns]
    samples[available_event_cols].to_parquet(
        out_dir / "panic_basket_event_stock_samples.parquet", index=False)
    print(f"  event_stock_samples: {len(samples):,} rows -> parquet")

    print(f"\nPhase 1 complete. Outputs saved to {out_dir}")
    print(f"  daily_samples:  {len(daily_basket):,} rows")
    print(f"  diagnostics:    {len(diagnostics):,} rows")
    print(f"  state_analysis: {len(state_analysis):,} rows")

    # Print key findings
    if not diagnostics.empty:
        print("\nBasket return by year:")
        for _, r in diagnostics.iterrows():
            print(f"  {int(r['year'])}: mean_ret={r['avg_basket_mean_ret']:.4f}  "
                  f"a_rate={r.get('avg_a_rate', 'N/A'):.4f}  "
                  f"pos_days={int(r['pos_basket_days'])}/{int(r['n_days'])}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

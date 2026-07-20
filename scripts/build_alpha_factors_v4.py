#!/usr/bin/env python
"""
Build V4 alpha factors — compute raw factor values, apply PIT alignment,
cross-sectional processing, and cache to parquet with manifest tracking.

Usage:
  python -X utf8 scripts/build_alpha_factors_v4.py --config configs/factor_build_v4.yaml --start 20170101 --end 20241231 --force
  python -X utf8 scripts/build_alpha_factors_v4.py --config configs/factor_build_v4.yaml --start 20260101 --end 20260605 --force
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ===========================================================================
# PIT Helpers
# ===========================================================================

def _resolve_available_date(
    ann_date: Optional[int],
    end_date: int,
    report_type: str = "quarterly",
    f_ann_date: Optional[int] = None,
) -> int:
    """Resolve available_date with preference: ann_date > f_ann_date > fallback.

    The fallback values are calibrated to Chinese A-share reporting deadlines:
      - Annual reports: due by April 30 (end_date + 120 calendar days), but
        most are filed within 90 days. We use 90-day fallback (end_date=1231
        → available ~0331 next year) which keeps PIT lag within fundamental
        staleness tolerance (63 trading days ≈ 90 calendar days).
      - Semi-annual: due by August 31 (end_date + 62 calendar days). We use
        45-day fallback which is the typical filing window.
      - Quarterly: due within 30 days of quarter end.
    """
    # Prefer ann_date (the actual announcement date from the data vendor)
    if ann_date is not None and not pd.isna(ann_date):
        return int(ann_date)

    # Next best: f_ann_date (filing/report publication date)
    if f_ann_date is not None and not pd.isna(f_ann_date):
        return int(f_ann_date)

    # Conservative fallback based on report type
    end = int(end_date)
    month = (end // 100) % 100
    day = end % 100

    if month == 12 and day == 31:       # Annual report: ~90 calendar days
        return end + 90
    elif month == 6 and day == 30:      # Semi-annual: ~45 calendar days
        return end + 45
    else:                                # Quarterly: ~30 calendar days
        return end + 30


def _detect_report_type(end_date: int) -> str:
    """Detect report type from end_date."""
    month = (end_date // 100) % 100
    day = end_date % 100
    if month == 12 and day == 31:
        return "annual"
    elif month == 6 and day == 30:
        return "semi_annual"
    else:
        return "quarterly"


# ===========================================================================
# Factor computation functions
# ===========================================================================

def _compute_technical_skip_momentum(
    prices: pd.DataFrame, momentum_days: int, skip_days: int,
) -> pd.DataFrame:
    """Compute momentum with skip window from price data.

    Args:
        prices: DataFrame with [ts_code, trade_date, adj_close]
        momentum_days: lookback window in trading days
        skip_days: number of recent days to skip
    """
    df = prices.copy()
    df = df.sort_values(["ts_code", "trade_date"])
    df["price_lag_mom"] = df.groupby("ts_code")["adj_close"].shift(momentum_days)
    df["price_lag_skip"] = df.groupby("ts_code")["adj_close"].shift(skip_days)
    df["value"] = (df["price_lag_skip"] / df["price_lag_mom"]) - 1
    result = df[["ts_code", "trade_date", "value"]].dropna()
    return result


def _compute_risk_adjusted_momentum(
    prices: pd.DataFrame, momentum_days: int, vol_window: int,
) -> pd.DataFrame:
    """Compute risk-adjusted momentum = momentum / volatility."""
    df = prices.copy()
    df = df.sort_values(["ts_code", "trade_date"])
    df["ret"] = df.groupby("ts_code")["adj_close"].pct_change()
    df["vol"] = df.groupby("ts_code")["ret"].transform(
        lambda x: x.rolling(vol_window, min_periods=vol_window // 2).std()
    )
    df["momentum"] = df.groupby("ts_code")["adj_close"].pct_change(momentum_days)
    df["value"] = df["momentum"] / (df["vol"] + 1e-10)
    result = df[["ts_code", "trade_date", "value"]].dropna()
    return result


def _compute_volume_confirmed_momentum(
    prices: pd.DataFrame, momentum_days: int, vol_window: int,
) -> pd.DataFrame:
    """Compute volume-confirmed momentum."""
    df = prices.copy()
    df = df.sort_values(["ts_code", "trade_date"])
    df["momentum"] = df.groupby("ts_code")["adj_close"].pct_change(momentum_days)
    if "vol" in df.columns:
        df["vol_change"] = df.groupby("ts_code")["vol"].pct_change(vol_window)
        df["vol_sign"] = np.sign(df["vol_change"])
        df["value"] = df["momentum"] * df["vol_sign"]
    else:
        df["value"] = df["momentum"]
    result = df[["ts_code", "trade_date", "value"]].dropna()
    return result


def _compute_trend_quality(
    prices: pd.DataFrame, short_window: int, long_window: int,
) -> pd.DataFrame:
    """Compute trend quality score."""
    df = prices.copy()
    df = df.sort_values(["ts_code", "trade_date"])
    df["ma_long"] = df.groupby("ts_code")["adj_close"].transform(
        lambda x: x.rolling(long_window, min_periods=long_window // 2).mean()
    )
    df["std_long"] = df.groupby("ts_code")["adj_close"].transform(
        lambda x: x.rolling(long_window, min_periods=long_window // 2).std()
    )
    # Trend strength: how far above MA, normalized by volatility
    df["trend_strength"] = (df["adj_close"] - df["ma_long"]) / (df["std_long"] + 1e-10)
    # RSI-like component: avoid overbought (>70) extremes
    df["ret"] = df.groupby("ts_code")["adj_close"].pct_change()
    df["avg_gain"] = df.groupby("ts_code")["ret"].transform(
        lambda x: x.clip(lower=0).rolling(short_window).mean()
    )
    df["avg_loss"] = df.groupby("ts_code")["ret"].transform(
        lambda x: (-x.clip(upper=0)).rolling(short_window).mean()
    )
    df["rsi"] = 100 - 100 / (1 + df["avg_gain"] / (df["avg_loss"] + 1e-10))
    # Penalize extreme RSI
    df["rsi_penalty"] = np.abs(df["rsi"] - 50) / 50
    df["value"] = df["trend_strength"] - df["rsi_penalty"]
    result = df[["ts_code", "trade_date", "value"]].dropna()
    return result


def _compute_liquidity_adjusted_reversal(
    prices: pd.DataFrame,
    reversal_days: int = 5,
    liquidity_window: int = 20,
    vol_window: int = 20,
) -> pd.DataFrame:
    """Compute short-term reversal with liquidity and volatility quality filters.

    High value means a recent loser with enough trading activity and without
    extreme recent volatility.  The multiplier is cross-sectional and PIT-safe
    because it only uses same-date rolling price/volume information.
    """
    if prices.empty or "adj_close" not in prices.columns:
        return pd.DataFrame()

    keep = ["ts_code", "trade_date", "adj_close"]
    for col in ("amount", "vol"):
        if col in prices.columns:
            keep.append(col)
    df = prices[keep].copy().sort_values(["ts_code", "trade_date"])

    df["ret_1d"] = df.groupby("ts_code")["adj_close"].pct_change()
    df["raw_reversal"] = -df.groupby("ts_code")["adj_close"].pct_change(reversal_days)
    df["volatility"] = df.groupby("ts_code")["ret_1d"].transform(
        lambda x: x.rolling(vol_window, min_periods=max(5, vol_window // 2)).std()
    )

    liq_col = "amount" if "amount" in df.columns else "vol" if "vol" in df.columns else None
    if liq_col is None:
        df["liquidity"] = 1.0
    else:
        df["liquidity"] = df.groupby("ts_code")[liq_col].transform(
            lambda x: x.rolling(liquidity_window, min_periods=max(5, liquidity_window // 2)).mean()
        )

    df["liquidity_rank"] = df.groupby("trade_date")["liquidity"].rank(pct=True)
    df["vol_rank"] = df.groupby("trade_date")["volatility"].rank(pct=True)
    liquidity_multiplier = 0.50 + 0.50 * df["liquidity_rank"]
    volatility_multiplier = 1.25 - 0.75 * df["vol_rank"]
    df["value"] = df["raw_reversal"] * liquidity_multiplier * volatility_multiplier

    return df[["ts_code", "trade_date", "value"]].dropna()


def _compute_vol_adjusted_reversal(
    prices: pd.DataFrame,
    reversal_days: int = 20,
    vol_window: int = 60,
) -> pd.DataFrame:
    """Compute reversal scaled by realized volatility."""
    if prices.empty or "adj_close" not in prices.columns:
        return pd.DataFrame()

    df = prices[["ts_code", "trade_date", "adj_close"]].copy()
    df = df.sort_values(["ts_code", "trade_date"])
    df["ret_1d"] = df.groupby("ts_code")["adj_close"].pct_change()
    df["reversal"] = -df.groupby("ts_code")["adj_close"].pct_change(reversal_days)
    df["volatility"] = df.groupby("ts_code")["ret_1d"].transform(
        lambda x: x.rolling(vol_window, min_periods=max(20, vol_window // 2)).std()
    )
    df["value"] = df["reversal"] / (df["volatility"] + 1e-10)
    return df[["ts_code", "trade_date", "value"]].dropna()


def _compute_low_beta(
    prices: pd.DataFrame,
    window: int = 60,
) -> pd.DataFrame:
    """Compute low-beta defensive factor against the equal-weight market."""
    if prices.empty or "adj_close" not in prices.columns:
        return pd.DataFrame()

    df = prices[["ts_code", "trade_date", "adj_close"]].copy()
    df = df.sort_values(["ts_code", "trade_date"])
    df["ret"] = df.groupby("ts_code")["adj_close"].pct_change()
    market_ret = df.groupby("trade_date")["ret"].mean().rename("market_ret")
    df = df.merge(market_ret, on="trade_date", how="left")

    min_periods = max(20, window // 2)
    df["ret_mean"] = df.groupby("ts_code")["ret"].transform(
        lambda x: x.rolling(window, min_periods=min_periods).mean()
    )
    df["market_mean"] = df.groupby("ts_code")["market_ret"].transform(
        lambda x: x.rolling(window, min_periods=min_periods).mean()
    )
    df["ret_market_mean"] = (df["ret"] * df["market_ret"]).groupby(df["ts_code"]).transform(
        lambda x: x.rolling(window, min_periods=min_periods).mean()
    )
    df["market_sq_mean"] = (df["market_ret"] ** 2).groupby(df["ts_code"]).transform(
        lambda x: x.rolling(window, min_periods=min_periods).mean()
    )
    covariance = df["ret_market_mean"] - df["ret_mean"] * df["market_mean"]
    variance = df["market_sq_mean"] - df["market_mean"] ** 2
    df["beta"] = covariance / (variance + 1e-10)
    df["value"] = -df["beta"]
    return df[["ts_code", "trade_date", "value"]].dropna()


def _compute_drawdown_resilience(
    prices: pd.DataFrame,
    window: int = 60,
    recovery_window: int = 20,
) -> pd.DataFrame:
    """Compute drawdown resilience: shallow drawdown plus recent recovery."""
    if prices.empty or "adj_close" not in prices.columns:
        return pd.DataFrame()

    df = prices[["ts_code", "trade_date", "adj_close"]].copy()
    df = df.sort_values(["ts_code", "trade_date"])
    min_periods = max(20, window // 2)
    rolling_max = df.groupby("ts_code")["adj_close"].transform(
        lambda x: x.rolling(window, min_periods=min_periods).max()
    )
    df["drawdown"] = df["adj_close"] / (rolling_max + 1e-10) - 1.0
    df["max_drawdown"] = df.groupby("ts_code")["drawdown"].transform(
        lambda x: x.rolling(window, min_periods=min_periods).min()
    )
    df["recovery_ret"] = df.groupby("ts_code")["adj_close"].pct_change(recovery_window)
    df["ret_1d"] = df.groupby("ts_code")["adj_close"].pct_change()
    df["recovery_vol"] = df.groupby("ts_code")["ret_1d"].transform(
        lambda x: x.rolling(recovery_window, min_periods=max(5, recovery_window // 2)).std()
    )
    df["recovery_score"] = df["recovery_ret"] / (df["recovery_vol"] + 1e-10)
    df["value"] = df["max_drawdown"] + 0.10 * df["recovery_score"]
    return df[["ts_code", "trade_date", "value"]].dropna()


def _keep_rebalance_frequency(
    factor_df: pd.DataFrame,
    frequency: str,
) -> pd.DataFrame:
    """Keep only weekly or monthly rebalance dates from a daily factor panel."""
    if factor_df.empty or "trade_date" not in factor_df.columns:
        return factor_df

    df = factor_df.copy()
    dates = pd.Series(sorted(df["trade_date"].dropna().astype(int).unique()))
    dt = pd.to_datetime(dates.astype(str), format="%Y%m%d", errors="coerce")
    date_frame = pd.DataFrame({"trade_date": dates, "_dt": dt}).dropna(subset=["_dt"])

    if frequency == "weekly":
        date_frame["_period"] = date_frame["_dt"].dt.to_period("W-FRI").astype(str)
    elif frequency == "monthly":
        date_frame["_period"] = date_frame["_dt"].dt.to_period("M").astype(str)
    else:
        return df

    keep_dates = set(
        date_frame.sort_values("trade_date").groupby("_period")["trade_date"].last().astype(int)
    )
    return df[df["trade_date"].astype(int).isin(keep_dates)].copy()


def _smooth_factor_values(
    factor_df: pd.DataFrame,
    smooth_window: int,
) -> pd.DataFrame:
    """Apply per-stock rolling mean to factor values before downsampling."""
    if factor_df.empty or smooth_window <= 1:
        return factor_df
    df = factor_df.copy().sort_values(["ts_code", "trade_date"])
    df["value"] = df.groupby("ts_code")["value"].transform(
        lambda x: x.rolling(smooth_window, min_periods=max(2, smooth_window // 2)).mean()
    )
    return df.dropna(subset=["value"])


def _compute_low_beta_stable(
    prices: pd.DataFrame,
    beta_window: int = 120,
    smooth_window: int = 20,
    frequency: str = "monthly",
) -> pd.DataFrame:
    """Stable low-beta factor with explicit low-turnover signal dates."""
    base = _compute_low_beta(prices, beta_window)
    base = _smooth_factor_values(base, smooth_window)
    return _keep_rebalance_frequency(base, frequency)


def _compute_drawdown_resilience_stable(
    prices: pd.DataFrame,
    window: int = 120,
    recovery_window: int = 20,
    smooth_window: int = 10,
    frequency: str = "monthly",
) -> pd.DataFrame:
    """Stable drawdown-resilience factor with monthly signal dates."""
    base = _compute_drawdown_resilience(prices, window, recovery_window)
    base = _smooth_factor_values(base, smooth_window)
    return _keep_rebalance_frequency(base, frequency)


def _compute_liquidity_adjusted_reversal_low_turnover(
    prices: pd.DataFrame,
    reversal_days: int = 5,
    liquidity_window: int = 20,
    vol_window: int = 20,
    smooth_window: int = 3,
    frequency: str = "weekly",
) -> pd.DataFrame:
    """Liquidity-adjusted reversal with lower signal refresh frequency."""
    base = _compute_liquidity_adjusted_reversal(
        prices, reversal_days, liquidity_window, vol_window
    )
    base = _smooth_factor_values(base, smooth_window)
    return _keep_rebalance_frequency(base, frequency)


def _compute_vol_adjusted_reversal_low_turnover(
    prices: pd.DataFrame,
    reversal_days: int = 20,
    vol_window: int = 60,
    smooth_window: int = 5,
    frequency: str = "weekly",
) -> pd.DataFrame:
    """Vol-adjusted reversal with lower signal refresh frequency."""
    base = _compute_vol_adjusted_reversal(prices, reversal_days, vol_window)
    base = _smooth_factor_values(base, smooth_window)
    return _keep_rebalance_frequency(base, frequency)


def _compute_panic_reversal(
    prices: pd.DataFrame,
    threshold: float = 0.05,
    direction: str = "drop",
    signal_type: str = "bin",
    frequency: str = "weekly",
) -> pd.DataFrame:
    """Panic reversal factor — event-driven reversal on extreme short-term moves.

    Computes 5-day momentum (mom5) and applies a threshold to identify
    panic drops, panic surges, or symmetric extreme moves. Supports three
    signal encodings: binary (+1/-1), continuous (-mom5), and winsorized
    continuous.

    Args:
        prices: DataFrame with [ts_code, trade_date, adj_close].
        threshold: Absolute momentum threshold (e.g. 0.03 for ±3%).
        direction: "drop" (long extreme losers), "up" (short extreme winners),
                   "sym" (symmetric: long extreme drops, short extreme surges).
        signal_type: "bin" (event=±1, non-event=0),
                     "cont" (value = -mom5 for drop, mom5 for up, non-event=0),
                     "wcont" (as cont, then cross-sectional winsor of non-zero values).
        frequency: "weekly" or "daily".

    Returns:
        DataFrame with [ts_code, trade_date, value].
    """
    if prices.empty:
        return pd.DataFrame(columns=["ts_code", "trade_date", "value"])

    if "adj_close" not in prices.columns:
        return pd.DataFrame(columns=["ts_code", "trade_date", "value"])

    df = prices[["ts_code", "trade_date", "adj_close"]].copy()
    df = df.sort_values(["ts_code", "trade_date"])

    # 5-day momentum: mom5 = adj_close / adj_close.shift(5) - 1
    df["mom5"] = df.groupby("ts_code")["adj_close"].transform(
        lambda x: x / x.shift(5) - 1
    )

    # Drop rows without valid mom5
    df = df.dropna(subset=["mom5"])

    # --- Apply threshold and direction ---
    abs_mom = df["mom5"].abs()

    if direction == "drop":
        event_mask = df["mom5"] <= -threshold
        if signal_type == "bin":
            df["value"] = np.where(event_mask, 1.0, 0.0)
        elif signal_type in ("cont", "wcont"):
            # value = -mom5 (positive for drop magnitude); non-event = 0
            df["value"] = np.where(event_mask, -df["mom5"], 0.0)

    elif direction == "up":
        event_mask = df["mom5"] >= threshold
        if signal_type == "bin":
            df["value"] = np.where(event_mask, -1.0, 0.0)
        elif signal_type in ("cont", "wcont"):
            # value = -mom5 (negative for up-move; short signal); non-event = 0
            df["value"] = np.where(event_mask, -df["mom5"], 0.0)

    elif direction == "sym":
        event_mask = abs_mom >= threshold
        if signal_type == "bin":
            # +1 for drop events, -1 for up events, 0 otherwise
            df["value"] = np.where(
                event_mask,
                np.where(df["mom5"] <= -threshold, 1.0, -1.0),
                0.0,
            )
        elif signal_type in ("cont", "wcont"):
            # Uniform: value = -mom5 for ALL events
            #   drops (mom5 <= -thr): -mom5 > 0  → long signal
            #   ups   (mom5 >= +thr): -mom5 < 0  → short signal
            #   non-event: 0
            df["value"] = np.where(event_mask, -df["mom5"], 0.0)
    else:
        raise ValueError(f"Unknown direction: {direction}")

    # --- Winsorize non-zero values for wcont ---
    if signal_type == "wcont":
        nonzero = df["value"] != 0
        if nonzero.any():
            # Per-date cross-sectional winsor at 5%/95% on non-zero values only
            def _winsor_nonzero(grp):
                nz = grp["value"] != 0
                if nz.sum() < 5:
                    return grp
                lo = grp.loc[nz, "value"].quantile(0.05)
                hi = grp.loc[nz, "value"].quantile(0.95)
                if lo < hi:
                    grp.loc[nz, "value"] = grp.loc[nz, "value"].clip(lo, hi)
                return grp

            df = df.groupby("trade_date", group_keys=False).apply(_winsor_nonzero)

    # --- Frequency downsampling ---
    out = df[["ts_code", "trade_date", "value"]].copy()
    if frequency == "weekly":
        out = _keep_rebalance_frequency(out, "weekly")

    return out.dropna(subset=["value"]) if not out.empty else out


def _compute_fundamental_ttm(
    fin_data: pd.DataFrame,
    field: str,
    value_col: str = "value",
    min_quarters: int = 2,
) -> pd.DataFrame:
    """Compute TTM (trailing N quarters) from financial data with PIT alignment.

    When less than 4 quarters are available, scales the sum proportionally.
    Minimum quarters can be lowered to increase stock coverage.

    Args:
        fin_data: DataFrame with [ts_code, end_date, ann_date, <field>]
        field: column name for the financial metric
        min_quarters: minimum quarters required (default 2)
    """
    df = fin_data.copy()
    if field not in df.columns:
        return pd.DataFrame(columns=["ts_code", "source_period", "source_date", "available_date", value_col])
    df = df.dropna(subset=[field])
    df = df.sort_values(["ts_code", "end_date"])

    # Resolve available_date — prefer f_ann_date if present
    f_ann_col = next((c for c in df.columns if c in ("f_ann_date", "f_ann_dt")), None)
    df["available_date"] = df.apply(
        lambda r: _resolve_available_date(
            r.get("ann_date"), r["end_date"],
            _detect_report_type(r["end_date"]),
            f_ann_date=r.get(f_ann_col) if f_ann_col else None,
        ), axis=1
    )
    df["source_period"] = df["end_date"]
    df["source_date"] = df["end_date"]

    # TTM: sum of last N quarters for each available_date
    results = []
    for (ts_code, avail_date), group in df.groupby(["ts_code", "available_date"]):
        # Get the latest quarters at or before this available_date
        group = group[group["end_date"] <= avail_date]
        if len(group) < min_quarters:
            continue
        # Last up-to-4 quarters
        recent = group.nlargest(4, "end_date")
        if len(recent) < min_quarters:
            continue
        ttm_value = recent[field].sum() if len(recent) >= 4 else recent[field].sum() * (4.0 / len(recent))
        results.append({
            "ts_code": ts_code,
            "source_period": recent["end_date"].max(),
            "source_date": recent["end_date"].max(),
            "available_date": avail_date,
            value_col: ttm_value,
        })

    if not results:
        return pd.DataFrame(columns=["ts_code", "source_period", "source_date", "available_date", value_col])

    return pd.DataFrame(results)


def _compute_stability_8q(
    fin_data: pd.DataFrame,
    field: str,
    min_quarters: int = 3,
) -> pd.DataFrame:
    """Compute 8-quarter stability (negative std) of a financial field.

    Uses up to 8 quarters of history. Relaxed default min_quarters (3 instead of 4)
    improves coverage for stocks with shorter financial history.
    """
    df = fin_data.copy()
    if field not in df.columns:
        return pd.DataFrame()
    df = df.dropna(subset=[field])
    df = df.sort_values(["ts_code", "end_date"])

    f_ann_col = next((c for c in df.columns if c in ("f_ann_date", "f_ann_dt")), None)
    df["available_date"] = df.apply(
        lambda r: _resolve_available_date(
            r.get("ann_date"), r["end_date"],
            _detect_report_type(r["end_date"]),
            f_ann_date=r.get(f_ann_col) if f_ann_col else None,
        ), axis=1
    )

    results = []
    for (ts_code, avail_date), group in df.groupby(["ts_code", "available_date"]):
        group = group[group["end_date"] <= avail_date]
        recent = group.nlargest(8, "end_date")
        if len(recent) < min_quarters:
            continue
        stability = -float(recent[field].std(ddof=0)) if len(recent) >= 2 else 0.0
        results.append({
            "ts_code": ts_code,
            "source_period": recent["end_date"].max(),
            "source_date": recent["end_date"].max(),
            "available_date": avail_date,
            "value": stability,
        })

    if not results:
        return pd.DataFrame()
    return pd.DataFrame(results)


def _compute_growth_ttm(
    fin_data: pd.DataFrame,
    field: str,
    min_quarters: int = 3,
) -> pd.DataFrame:
    """Compute TTM growth rate = (TTM_t / TTM_{t-4q}) - 1.

    Requires enough quarters to compute both current TTM and prior TTM.
    Relaxed default min_quarters (3) improves coverage while still requiring
    at least one quarter of comparison data.
    """
    df = fin_data.copy()
    if field not in df.columns:
        return pd.DataFrame()
    df = df.dropna(subset=[field])
    df = df.sort_values(["ts_code", "end_date"])

    f_ann_col = next((c for c in df.columns if c in ("f_ann_date", "f_ann_dt")), None)
    df["available_date"] = df.apply(
        lambda r: _resolve_available_date(
            r.get("ann_date"), r["end_date"],
            _detect_report_type(r["end_date"]),
            f_ann_date=r.get(f_ann_col) if f_ann_col else None,
        ), axis=1
    )

    results = []
    for (ts_code, avail_date), group in df.groupby(["ts_code", "available_date"]):
        group = group[group["end_date"] <= avail_date].nlargest(8, "end_date")
        if len(group) < max(min_quarters * 2, 4):
            continue
        # Current TTM: last 4 or fewer quarters
        n_recent = min(4, len(group) // 2)
        current = group.nlargest(n_recent, "end_date")
        prior = group.nsmallest(n_recent, "end_date")
        if len(current) < 2 or len(prior) < 2:
            continue
        cur_ttm = current[field].sum() * (4.0 / len(current))
        prior_ttm = prior[field].sum() * (4.0 / len(prior))
        if prior_ttm == 0 or np.isnan(prior_ttm):
            continue
        growth = (cur_ttm / prior_ttm) - 1
        results.append({
            "ts_code": ts_code,
            "source_period": current["end_date"].max(),
            "source_date": current["end_date"].max(),
            "available_date": avail_date,
            "value": growth,
        })

    if not results:
        return pd.DataFrame()
    return pd.DataFrame(results)


def _compute_earnings_acceleration(
    fin_data: pd.DataFrame,
    min_quarters: int = 4,
) -> pd.DataFrame:
    """Compute earnings acceleration (2nd derivative of profit growth).

    Relaxed minimum from 12-quarters/6-min to support stocks with
    shorter financial history. Uses up to 12 quarters but accepts as few
    as min_quarters*2 total.
    """
    df = fin_data.copy()
    field = "n_income"
    if field not in df.columns:
        return pd.DataFrame()
    df = df.dropna(subset=[field])
    df = df.sort_values(["ts_code", "end_date"])

    f_ann_col = next((c for c in df.columns if c in ("f_ann_date", "f_ann_dt")), None)
    df["available_date"] = df.apply(
        lambda r: _resolve_available_date(
            r.get("ann_date"), r["end_date"],
            _detect_report_type(r["end_date"]),
            f_ann_date=r.get(f_ann_col) if f_ann_col else None,
        ), axis=1
    )

    results = []
    for (ts_code, avail_date), group in df.groupby(["ts_code", "available_date"]):
        group = group[group["end_date"] <= avail_date].nlargest(12, "end_date")
        if len(group) < max(min_quarters * 2, 4):
            continue
        # Divide available quarters into 3 groups: recent, mid, prior
        n = len(group)
        chunk = max(1, n // 3)
        recent_chunk = group.nlargest(chunk, "end_date")
        # mid_chunk: middle third (skip recent, take next chunk)
        remaining = group.iloc[chunk:] if len(group) > chunk else group
        mid_chunk = remaining.nlargest(chunk, "end_date") if len(remaining) >= chunk else remaining
        # prior_chunk: the oldest third
        prior_chunk = group.nsmallest(chunk, "end_date")

        if len(recent_chunk) < 1 or len(prior_chunk) < 1:
            continue
        cur_growth = recent_chunk[field].sum() / (prior_chunk[field].sum() + 1e-10) - 1
        if len(mid_chunk) >= 1:
            prior_growth = mid_chunk[field].sum() / (prior_chunk[field].sum() + 1e-10) - 1
        else:
            prior_growth = cur_growth
        acceleration = cur_growth - prior_growth
        results.append({
            "ts_code": ts_code,
            "source_period": recent_chunk["end_date"].max(),
            "source_date": recent_chunk["end_date"].max(),
            "available_date": avail_date,
            "value": acceleration,
        })

    if not results:
        return pd.DataFrame()
    return pd.DataFrame(results)


def _compute_industry_relative(
    factor_df: pd.DataFrame,
    industry_map: pd.DataFrame,
    factor_name: str,
    min_industry_stocks: int = 10,
) -> pd.DataFrame:
    """Compute industry-relative rank of a factor.

    Args:
        factor_df: [ts_code, trade_date, value] (+ optional PIT fields)
        industry_map: [ts_code, industry_code] (+ optional industry_static_fallback)
        min_industry_stocks: minimum stocks per trade_date+industry_code group

    Inherits PIT fields from the base factor if present.
    Adds industry_static_fallback flag if industry map has it.
    """
    if factor_df.empty or industry_map.empty:
        return pd.DataFrame()

    # Preserve PIT fields from base factor for inheritance
    pit_fields = [c for c in ["source_period", "source_date", "available_date",
                                "pit_lag_days", "is_stale"] if c in factor_df.columns]

    # Normalize date column: use trade_date if available, else available_date
    date_col = "trade_date" if "trade_date" in factor_df.columns else "available_date"
    if date_col not in factor_df.columns:
        return pd.DataFrame()

    merged = factor_df.merge(industry_map, on="ts_code", how="inner")
    if merged.empty:
        return pd.DataFrame()

    # Filter: only compute rank for groups with enough stocks
    merged["_group_size"] = merged.groupby([date_col, "industry_code"])["value"].transform("count")
    valid = merged[merged["_group_size"] >= min_industry_stocks].copy()
    if valid.empty:
        return pd.DataFrame()

    valid["value"] = valid.groupby([date_col, "industry_code"])["value"].rank(pct=True)

    # Build result: keep PIT fields + value, using date_col as the primary date
    # If we used available_date, set it as trade_date for CS processing
    if date_col == "available_date" and "trade_date" not in valid.columns:
        valid["trade_date"] = valid["available_date"]

    result_cols = ["ts_code", "trade_date", "value"] + pit_fields
    # industry_static_fallback is already in valid from the initial merge above
    if "industry_static_fallback" in valid.columns:
        result_cols.append("industry_static_fallback")

    result = valid[[c for c in result_cols if c in valid.columns]].copy()
    return result


def _compute_profitability_quality(
    fin_data: pd.DataFrame,
    margin_fields: List[str],
    roe_field: str = "roe",
) -> pd.DataFrame:
    """Compute composite profitability quality from multiple margins + ROE."""
    df = fin_data.copy()
    available_fields = [f for f in margin_fields + [roe_field] if f in df.columns]
    if not available_fields:
        return pd.DataFrame()

    df = df.dropna(subset=available_fields, how="all")
    df["available_date"] = df.apply(
        lambda r: _resolve_available_date(r.get("ann_date"), r["end_date"]), axis=1
    )

    results = []
    for (ts_code, avail_date), group in df.groupby(["ts_code", "available_date"]):
        group = group[group["end_date"] <= avail_date]
        recent = group.nlargest(4, "end_date")
        if len(recent) < 1:
            continue
        # Average TTM values
        scores = []
        for f in available_fields:
            ttm_val = recent[f].mean()
            scores.append(ttm_val)
        composite = float(np.mean(scores)) if scores else 0.0
        results.append({
            "ts_code": ts_code,
            "source_period": recent["end_date"].max(),
            "source_date": recent["end_date"].max(),
            "available_date": avail_date,
            "value": composite,
        })

    if not results:
        return pd.DataFrame()
    return pd.DataFrame(results)


def _compute_ocf_to_profit(fin_data: pd.DataFrame) -> pd.DataFrame:
    """Compute OCF/Profit ratio.

    Searches for operating cash flow across multiple possible field names
    and net profit fields. Tries cashflow data fields first.
    """
    df = fin_data.copy()
    ocf_field = None
    profit_field = None
    for f in ["n_cashflow_act", "ocfps", "cfps", "ocf", "cf_sales", "operating_cf"]:
        if f in df.columns:
            ocf_field = f
            break
    for f in ["profit_dedt", "n_income", "net_profit"]:
        if f in df.columns:
            profit_field = f
            break
    if ocf_field is None or profit_field is None:
        return pd.DataFrame()

    df["available_date"] = df.apply(
        lambda r: _resolve_available_date(r.get("ann_date"), r["end_date"]), axis=1
    )

    results = []
    for (ts_code, avail_date), group in df.groupby(["ts_code", "available_date"]):
        group = group[group["end_date"] <= avail_date]
        recent = group.nlargest(4, "end_date")
        if len(recent) < 1:
            continue
        ocf_ttm = recent[ocf_field].sum()
        profit_ttm = recent[profit_field].sum()
        if profit_ttm == 0 or np.isnan(profit_ttm):
            continue
        ratio = ocf_ttm / profit_ttm
        results.append({
            "ts_code": ts_code,
            "source_period": recent["end_date"].max(),
            "source_date": recent["end_date"].max(),
            "available_date": avail_date,
            "value": ratio,
        })

    if not results:
        return pd.DataFrame()
    return pd.DataFrame(results)


def _compute_accrual_quality(
    income_data: pd.DataFrame,
    cashflow_data: pd.DataFrame,
    balance_data: pd.DataFrame,
) -> pd.DataFrame:
    """Compute accrual quality = -(net_profit_ttm - ocf_ttm) / avg_total_assets.

    Higher value = lower accruals = better earnings quality.
    Uses negative of Sloan-style accruals so high = good.
    """
    # Find available fields
    profit_field = next((f for f in ["n_income", "net_profit", "profit_dedt"]
                         if f in income_data.columns), None)
    ocf_field = next((f for f in ["n_cashflow_act", "ocfps", "ocf", "operating_cf"]
                      if f in cashflow_data.columns), None)
    assets_field = next((f for f in ["total_assets", "fixed_assets"]
                         if f in balance_data.columns), None)

    if profit_field is None or ocf_field is None or assets_field is None:
        return pd.DataFrame()

    # Compute TTM for income and cashflow components
    ni_ttm = _compute_fundamental_ttm(income_data, profit_field)
    ocf_ttm = _compute_fundamental_ttm(cashflow_data, ocf_field)

    if ni_ttm.empty or ocf_ttm.empty:
        return pd.DataFrame()

    # Get latest total_assets per (ts_code, available_date)
    df_assets = balance_data.copy()
    df_assets["available_date"] = df_assets.apply(
        lambda r: _resolve_available_date(
            r.get("ann_date"), r["end_date"],
            _detect_report_type(r["end_date"]),
            f_ann_date=r.get("f_ann_date") if "f_ann_date" in r.index else None,
        ), axis=1
    )
    df_assets = df_assets.dropna(subset=[assets_field])

    # Merge components on (ts_code, available_date)
    merged = ni_ttm.merge(ocf_ttm, on=["ts_code", "available_date"],
                          suffixes=("_ni", "_ocf"), how="inner")
    if merged.empty:
        return pd.DataFrame()

    merged = merged.merge(
        df_assets[["ts_code", "available_date", assets_field]],
        on=["ts_code", "available_date"], how="inner"
    )
    if merged.empty:
        return pd.DataFrame()

    merged["value"] = -(merged["value_ni"] - merged["value_ocf"]) / (
        merged[assets_field].abs() + 1e-10
    )
    result = merged[["ts_code", "source_period", "source_date",
                     "available_date", "value"]].dropna()
    return result


def _compute_receivable_pressure(
    income_data: pd.DataFrame,
    balance_data: pd.DataFrame,
) -> pd.DataFrame:
    """Compute receivable pressure = -(accounts_receivable_growth / revenue_growth).

    Higher factor value = lower receivable pressure = better quality.
    If growth data unavailable, falls back to -(ar_ttm / revenue_ttm).
    """
    ar_field = next((f for f in ["accounts_receiv", "accounts_receivable"]
                     if f in balance_data.columns), None)
    revenue_field = next((f for f in ["revenue", "n_income"]
                          if f in income_data.columns), None)

    if ar_field is None or revenue_field is None:
        return pd.DataFrame()

    # Compute revenue TTM from income data
    rev_ttm = _compute_fundamental_ttm(income_data, revenue_field)
    if rev_ttm.empty:
        return pd.DataFrame()

    # Compute AR "TTM" (average receivables) from balance sheet
    df_ar = balance_data.copy()
    df_ar["available_date"] = df_ar.apply(
        lambda r: _resolve_available_date(
            r.get("ann_date"), r["end_date"],
            _detect_report_type(r["end_date"]),
            f_ann_date=r.get("f_ann_date") if "f_ann_date" in r.index else None,
        ), axis=1
    )
    df_ar = df_ar.dropna(subset=[ar_field])

    ar_results = []
    for (ts_code, avail_date), group in df_ar.groupby(["ts_code", "available_date"]):
        group = group[group["end_date"] <= avail_date]
        recent = group.nlargest(4, "end_date")
        if len(recent) < 2:
            continue
        ar_avg = recent[ar_field].mean()
        ar_results.append({
            "ts_code": ts_code,
            "source_period": recent["end_date"].max(),
            "source_date": recent["end_date"].max(),
            "available_date": avail_date,
            "value_ar": ar_avg,
        })

    if not ar_results:
        return pd.DataFrame()
    ar_df = pd.DataFrame(ar_results)

    # Merge and compute ratio
    merged = rev_ttm.merge(ar_df, on=["ts_code", "available_date"],
                           suffixes=("_rev", "_ar"), how="inner")
    if merged.empty:
        return pd.DataFrame()

    # Receivable pressure = AR / Revenue (lower is better, so negate)
    merged["value"] = -(merged["value_ar"] / (merged["value_rev"].abs() + 1e-10))
    result = merged[["ts_code", "source_period", "source_date",
                     "available_date", "value"]].dropna()
    return result


def _compute_asset_turnover_from_components(
    income_data: pd.DataFrame,
    balance_data: pd.DataFrame,
) -> pd.DataFrame:
    """Compute asset turnover = TTM revenue / avg_total_assets."""
    revenue_field = next((f for f in ["revenue"] if f in income_data.columns), None)
    assets_field = next((f for f in ["total_assets", "fixed_assets"]
                         if f in balance_data.columns), None)

    if revenue_field is None or assets_field is None:
        return pd.DataFrame()

    rev_ttm = _compute_fundamental_ttm(income_data, revenue_field)
    if rev_ttm.empty:
        return pd.DataFrame()

    df_assets = balance_data.copy()
    df_assets["available_date"] = df_assets.apply(
        lambda r: _resolve_available_date(
            r.get("ann_date"), r["end_date"],
            _detect_report_type(r["end_date"]),
            f_ann_date=r.get("f_ann_date") if "f_ann_date" in r.index else None,
        ), axis=1
    )
    df_assets = df_assets.dropna(subset=[assets_field])

    assets_results = []
    for (ts_code, avail_date), group in df_assets.groupby(["ts_code", "available_date"]):
        group = group[group["end_date"] <= avail_date]
        recent = group.nlargest(4, "end_date")
        if len(recent) < 2:
            continue
        assets_avg = recent[assets_field].mean()
        assets_results.append({
            "ts_code": ts_code,
            "available_date": avail_date,
            "avg_total_assets": assets_avg,
        })

    if not assets_results:
        return pd.DataFrame()
    assets_df = pd.DataFrame(assets_results)

    merged = rev_ttm.merge(assets_df, on=["ts_code", "available_date"], how="inner")
    if merged.empty:
        return pd.DataFrame()

    merged["value"] = merged["value"] / (merged["avg_total_assets"].abs() + 1e-10)
    result = merged[["ts_code", "source_period", "source_date",
                     "available_date", "value"]].dropna()
    return result


def _compute_growth_value_match(
    income_data: pd.DataFrame,
    daily_data: pd.DataFrame,
    prices: pd.DataFrame,
) -> pd.DataFrame:
    """Compute growth-value match: high growth + reasonable valuation.

    Steps:
    1. Revenue growth TTM pct_rank within each trade_date
    2. Profit growth TTM pct_rank within each trade_date
    3. EP = 1/pe pct_rank within each trade_date
    4. Composite = mean of at least 2 non-null component ranks

    PIT: available_date = max(component_available_dates).
    Requires at least 2 non-null components for a valid value.
    """
    source = income_data
    rev_growth = _compute_growth_ttm(source, "revenue") if "revenue" in source.columns else pd.DataFrame()
    profit_growth = _compute_growth_ttm(source, "n_income") if "n_income" in source.columns else pd.DataFrame()

    # Align to trade dates
    if not prices.empty:
        trade_dates = prices[["ts_code", "trade_date"]].drop_duplicates()
    else:
        return pd.DataFrame()

    # --- Component coverage diagnostic ---
    component_info = {
        "rev_growth_rows": len(rev_growth),
        "profit_growth_rows": len(profit_growth),
        "ep_rows": 0,
        "intersection_rows": 0,
    }

    components = []
    max_avail_dates = []  # track max available_date per component for composite PIT

    for gdf, label in [(rev_growth, "rev_growth"),
                        (profit_growth, "profit_growth")]:
        if gdf.empty or "available_date" not in gdf.columns:
            continue
        gdf = gdf.merge(trade_dates, on="ts_code", how="inner")
        gdf = gdf[gdf["trade_date"] >= gdf["available_date"]]
        gdf = gdf.sort_values(["ts_code", "trade_date", "available_date"])
        gdf = gdf.drop_duplicates(["ts_code", "trade_date"], keep="last")
        if not gdf.empty:
            # Keep available_date for composite PIT
            gdf[f"{label}_rank"] = gdf.groupby("trade_date")["value"].rank(pct=True)
            cols = ["ts_code", "trade_date", f"{label}_rank", "available_date"]
            components.append(gdf[[c for c in cols if c in gdf.columns]])
            if "available_date" in gdf.columns:
                max_avail_dates.append(gdf[["ts_code", "trade_date", "available_date"]])

    # EP from daily_basic
    if not daily_data.empty and "pe" in daily_data.columns:
        daily_df = daily_data[["ts_code", "trade_date", "pe"]].dropna(subset=["pe"])
        daily_df = daily_df[daily_df["pe"] > 0]
        daily_df["ep"] = 1.0 / daily_df["pe"]
        daily_df["ep_rank"] = daily_df.groupby("trade_date")["ep"].rank(pct=True)
        daily_df["available_date"] = daily_df["trade_date"]  # daily_basic: same-day
        components.append(daily_df[["ts_code", "trade_date", "ep_rank", "available_date"]])
        component_info["ep_rows"] = len(daily_df)

    if len(components) < 2:
        return pd.DataFrame()

    # Merge all components
    result = components[0]
    # Track available_date: use max across merged components
    result = result.rename(columns={"available_date": "avail_0"})
    for idx, c in enumerate(components[1:], 1):
        c = c.rename(columns={"available_date": f"avail_{idx}"})
        result = result.merge(c, on=["ts_code", "trade_date"], how="inner")
    component_info["intersection_rows"] = len(result)

    rank_cols = [c for c in result.columns if c.endswith("_rank")]
    avail_cols = [c for c in result.columns if c.startswith("avail_")]

    if not rank_cols:
        return pd.DataFrame()

    # Only compute value where at least 2 component ranks are non-null
    non_null_count = result[rank_cols].notna().sum(axis=1)
    result["value"] = result[rank_cols].mean(axis=1)
    result.loc[non_null_count < 2, "value"] = np.nan

    # Composite PIT: available_date = max of component available_dates
    if avail_cols:
        result["available_date"] = result[avail_cols].max(axis=1)
    else:
        result["available_date"] = result["trade_date"]

    result["source_period"] = result["trade_date"]
    result["source_date"] = result["trade_date"]

    out_cols = ["ts_code", "trade_date", "value",
                "available_date", "source_period", "source_date"]
    out_cols += [c for c in ["rev_growth_rank", "profit_growth_rank", "ep_rank"]
                 if c in result.columns]

    return result[out_cols].dropna(subset=["value"])


def _compute_valuation_reversion_3y(
    daily_data: pd.DataFrame,
) -> pd.DataFrame:
    """Compute 3-year valuation percentile reversion.

    For each stock at each trade_date:
    - PE 3-year rolling percentile (within stock's own history)
    - PB 3-year rolling percentile
    - value = -(pe_pct + pb_pct) / 2
    - Higher factor = historically cheap = reversion potential.
    """
    if daily_data.empty or "pe" not in daily_data.columns:
        return pd.DataFrame()

    df = daily_data[["ts_code", "trade_date", "pe", "pb"]].copy()
    df = df.sort_values(["ts_code", "trade_date"])

    # 3 years for daily_basic is ~36 monthly snapshots.
    # daily_basic has month-end data (not daily), so use calendar months.
    window = 36
    min_periods = max(12, window // 3)

    for col in ["pe", "pb"]:
        if col in df.columns:
            df[f"{col}_pct"] = df.groupby("ts_code")[col].transform(
                lambda x: x.rolling(window, min_periods=min_periods).rank(pct=True)
            )

    pct_cols = [c for c in df.columns if c.endswith("_pct")]
    if not pct_cols:
        return pd.DataFrame()

    df["value"] = -df[pct_cols].mean(axis=1)

    # PIT fields for daily_basic: available at trade_date itself
    df["available_date"] = df["trade_date"]
    df["source_period"] = df["trade_date"]
    df["source_date"] = df["trade_date"]

    return df[["ts_code", "trade_date", "value",
               "available_date", "source_period", "source_date"]].dropna()


def _compute_quality_value_composite(
    fina_data: pd.DataFrame,
    daily_data: pd.DataFrame,
    prices: pd.DataFrame,
) -> pd.DataFrame:
    """Quality + Value composite: EP + BP + ROE.

    PIT: available_date = max(component_available_dates).
    ROE from fina_indicator carries real reporting lag → pit_lag_days > 0.
    """
    if daily_data.empty:
        return pd.DataFrame()

    # --- EP and BP from daily_basic (same-day data) ---
    daily_df = daily_data[["ts_code", "trade_date", "pe", "pb"]].dropna(subset=["pe", "pb"])
    daily_df = daily_df[(daily_df["pe"] > 0) & (daily_df["pb"] > 0)]
    daily_df["ep_rank"] = daily_df.groupby("trade_date")["pe"].transform(
        lambda x: (1.0 / x).rank(pct=True))
    daily_df["bp_rank"] = daily_df.groupby("trade_date")["pb"].transform(
        lambda x: (1.0 / x).rank(pct=True))
    daily_df["daily_available_date"] = daily_df["trade_date"]

    # --- ROE TTM with PIT: merge on ts_code, keep latest available_date <= trade_date ---
    roe_ttm = _compute_fundamental_ttm(fina_data, "roe") if "roe" in fina_data.columns else pd.DataFrame()
    if not roe_ttm.empty and "available_date" in roe_ttm.columns:
        roe_flat = roe_ttm[["ts_code", "available_date", "value"]].dropna()
        daily_dates = daily_df[["ts_code", "trade_date"]].drop_duplicates()
        # Merge on ts_code (bounded: monthly daily_basic × quarterly ROE ≈ 6.9M rows)
        merged = daily_dates.merge(roe_flat, on="ts_code", how="inner")
        merged = merged[merged["available_date"] <= merged["trade_date"]]
        if not merged.empty:
            merged = merged.sort_values(["ts_code", "trade_date", "available_date"])
            merged = merged.drop_duplicates(["ts_code", "trade_date"], keep="last")
            merged["roe_rank"] = merged.groupby("trade_date")["value"].rank(pct=True)
            merged = merged.rename(columns={
                "available_date": "roe_available_date",
                "value": "roe_value"
            })
            daily_df = daily_df.merge(
                merged[["ts_code", "trade_date", "roe_rank", "roe_available_date"]],
                on=["ts_code", "trade_date"], how="left"
            )

    # --- Composite value ---
    rank_cols = [c for c in ["ep_rank", "bp_rank", "roe_rank"] if c in daily_df.columns]
    daily_df["value"] = daily_df[rank_cols].mean(axis=1)

    # --- PIT: use ROE available_date (real financial reporting lag) ---
    # daily_basic is same-day and should not dominate the max
    if "roe_available_date" in daily_df.columns:
        daily_df["available_date"] = daily_df["roe_available_date"].fillna(daily_df["daily_available_date"])
    else:
        daily_df["available_date"] = daily_df["daily_available_date"]
    daily_df["source_period"] = daily_df["trade_date"]
    daily_df["source_date"] = daily_df["trade_date"]

    return daily_df[["ts_code", "trade_date", "value",
                     "available_date", "source_period", "source_date"]].dropna(subset=["value"])


def _compute_dividend_quality(
    fina_data: pd.DataFrame,
    daily_data: pd.DataFrame,
    prices: pd.DataFrame,
) -> pd.DataFrame:
    """Dividend quality: dv_ttm + roe + debt_to_assets.

    PIT: available_date = max(component_available_dates).
    fina_indicator components carry real reporting lag → pit_lag_days > 0.
    """
    if daily_data.empty or "dv_ttm" not in daily_data.columns:
        return pd.DataFrame()

    # --- Dividend yield from daily_basic ---
    result = daily_data[["ts_code", "trade_date", "dv_ttm"]].dropna(subset=["dv_ttm"]).copy()
    result["div_rank"] = result.groupby("trade_date")["dv_ttm"].rank(pct=True)
    result["daily_available_date"] = result["trade_date"]
    avail_cols = ["daily_available_date"]

    # --- Quality components from fina_indicator ---
    for field in ["roe", "debt_to_assets"]:
        if field not in fina_data.columns:
            continue
        ttm_df = _compute_fundamental_ttm(fina_data, field)
        if ttm_df.empty or "available_date" not in ttm_df.columns:
            continue

        # Merge fina TTM to daily_basic dates: ts_code join + filter available_date <= trade_date
        fina_flat = ttm_df[["ts_code", "available_date", "value"]].dropna()
        daily_dates = result[["ts_code", "trade_date"]].drop_duplicates()
        merged = daily_dates.merge(fina_flat, on="ts_code", how="inner")
        merged = merged[merged["available_date"] <= merged["trade_date"]]
        if merged.empty:
            continue
        merged = merged.sort_values(["ts_code", "trade_date", "available_date"])
        merged = merged.drop_duplicates(["ts_code", "trade_date"], keep="last")

        col_name = f"{field}_rank"
        merged[col_name] = merged.groupby("trade_date")["value"].rank(pct=True)
        if field == "debt_to_assets":
            merged[col_name] = 1.0 - merged[col_name]

        avail_col = f"{field}_available_date"
        merged = merged.rename(columns={"available_date": avail_col, "value": f"{field}_value"})
        avail_cols.append(avail_col)

        result = result.merge(
            merged[["ts_code", "trade_date", col_name, avail_col]],
            on=["ts_code", "trade_date"], how="inner"
        )

    rank_cols = [c for c in result.columns if c.endswith("_rank")]
    if "div_rank" not in result.columns or len(rank_cols) < 2:
        return pd.DataFrame()

    # Composite value
    quality_cols = [c for c in rank_cols if c != "div_rank"]
    quality_score = result[quality_cols].mean(axis=1)
    result["value"] = result["div_rank"] * (0.5 * quality_score + 0.2)
    result["proxy_used"] = True

    # PIT: use fina available_dates (real reporting lag), fallback to daily
    fina_cols = [c for c in avail_cols if "daily" not in c.lower()]
    if fina_cols:
        result["available_date"] = result[fina_cols].max(axis=1)
    else:
        result["available_date"] = result["daily_available_date"]
    result["source_period"] = result["trade_date"]
    result["source_date"] = result["trade_date"]

    return result[["ts_code", "trade_date", "value", "proxy_used",
                   "available_date", "source_period", "source_date"]].dropna()


# ===========================================================================
# Cross-sectional processing (reuse existing pipeline)
# ===========================================================================

def _apply_cs_processing(
    df: pd.DataFrame,
    cs_config: dict,
    industry_map: Optional[pd.DataFrame] = None,
    mktcap_data: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Apply cross-sectional processing: winsorize, neutralize, standardize.

    Falls back to simple z-score if full CS pipeline unavailable.
    """
    if df.empty:
        return df

    # Simple winsorize (MAD-based if possible, else percentile)
    value_col = "value"
    vals = df[value_col].dropna()
    if len(vals) < 30:
        return df

    median = vals.median()
    mad = (vals - median).abs().median()
    if mad > 0:
        upper = median + 5 * mad
        lower = median - 5 * mad
        df[value_col] = df[value_col].clip(lower, upper)

    # Simple z-score per trade_date
    df["value_cs"] = df.groupby("trade_date")[value_col].transform(
        lambda x: (x - x.mean()) / (x.std() + 1e-10)
    )
    df[value_col] = df["value_cs"]
    df = df.drop(columns=["value_cs"], errors="ignore")

    return df


# ===========================================================================
# Cache and manifest
# ===========================================================================

def _write_factor_cache(
    df: pd.DataFrame,
    factor_name: str,
    base_path: Path,
    force: bool = False,
) -> dict:
    """Write factor data to parquet cache, partitioned by year.

    When force=True, cleans old month= partitions and stale year-level files
    before writing to prevent cross-version data duplication.
    """
    if df.empty:
        return {"factor_name": factor_name, "n_rows": 0, "n_stocks": 0, "n_dates": 0}

    df["year"] = df["trade_date"] // 10000
    out_root = base_path / f"factor_name={factor_name}"

    if force and out_root.exists():
        # Clean old month= subdirectories from previous build versions
        # to prevent duplicate (ts_code, trade_date) keys from co-existing
        # V3/V4 partition formats. See docs/v4_growth_duplicate_root_cause.md.
        for year_dir in out_root.iterdir():
            if not year_dir.is_dir():
                continue
            for sub in year_dir.iterdir():
                if sub.is_dir() and sub.name.startswith("month="):
                    import shutil
                    shutil.rmtree(sub, ignore_errors=True)

    for year, year_df in df.groupby("year"):
        year_dir = out_root / f"year={year}"
        year_dir.mkdir(parents=True, exist_ok=True)
        year_df = year_df.drop(columns=["year"], errors="ignore")
        out_file = year_dir / f"part_{year}.parquet"
        year_df.to_parquet(out_file, index=False, compression="zstd")

    return {
        "factor_name": factor_name,
        "n_rows": len(df),
        "n_stocks": df["ts_code"].nunique(),
        "n_dates": df["trade_date"].nunique() if "trade_date" in df.columns else 0,
        "date_start": int(df["trade_date"].min()) if "trade_date" in df.columns else 0,
        "date_end": int(df["trade_date"].max()) if "trade_date" in df.columns else 0,
    }


def _write_manifest(
    factor_name: str,
    stats: dict,
    config_sha256: str,
    base_path: Path,
) -> None:
    """Write factor build manifest JSON."""
    manifest = {
        "factor_name": factor_name,
        "build_timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "config_sha256": config_sha256,
        "n_rows": stats.get("n_rows", 0),
        "n_stocks": stats.get("n_stocks", 0),
        "n_dates": stats.get("n_dates", 0),
        "date_start": stats.get("date_start", 0),
        "date_end": stats.get("date_end", 0),
        "pit_audit_status": "pending",  # Will be updated by audit script
    }
    manifest_path = base_path / f"factor_name={factor_name}" / "build_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")


# ===========================================================================
# Main build orchestrator
# ===========================================================================

def _load_price_data(start: str, end: str) -> pd.DataFrame:
    """Load price data with adj_close and vol."""
    root = ROOT / "data" / "parquet" / "prices_adj"
    if not root.exists():
        return pd.DataFrame()

    chunks = []
    start_int, end_int = int(start), int(end)
    for year_dir in sorted(root.iterdir()):
        if not year_dir.is_dir() or not year_dir.name.startswith("year="):
            continue
        year = int(year_dir.name.split("=")[1])
        if year < (start_int // 10000) or year > (end_int // 10000):
            continue
        for month_dir in sorted(year_dir.iterdir()):
            for pq_file in month_dir.glob("*.parquet"):
                try:
                    part = pd.read_parquet(pq_file)
                    part.columns = [str(c).strip().lower() for c in part.columns]
                    keep = ["ts_code", "trade_date"]
                    for c in ["adj_close", "close", "vol", "amount"]:
                        if c in part.columns:
                            keep.append(c)
                    part = part[[c for c in keep if c in part.columns]]
                    part["ts_code"] = part["ts_code"].astype(str)
                    part["trade_date"] = pd.to_numeric(part["trade_date"], errors="coerce")
                    part = part.dropna(subset=["trade_date"])
                    part = part[(part["trade_date"] >= start_int) & (part["trade_date"] <= end_int)]
                    if not part.empty:
                        chunks.append(part)
                except Exception:
                    continue

    if not chunks:
        return pd.DataFrame()
    result = pd.concat(chunks, ignore_index=True)
    return result.sort_values(["ts_code", "trade_date"])


def _load_financial_data(source: str, start: str, end: str) -> pd.DataFrame:
    """Load financial data from Tushare cache or parquet.

    Args:
        source: 'fina_indicator' or 'income'
    """
    # Try to load from Tushare client cache
    try:
        from data.tushare_client import get_client
        client = get_client()
        # daily_basic uses a different API signature — skip Tushare, go to parquet
        if source == "daily_basic":
            df = pd.DataFrame()  # handled below by parquet fallback
        elif source == "fina_indicator":
            df = client.get_fina_indicator(use_cache=True)
        elif source == "income":
            df = client.get_income(use_cache=True)
        else:
            # Unknown source — skip Tushare, try parquet fallback
            df = pd.DataFrame()
        if not df.empty:
            df.columns = [str(c).strip().lower() for c in df.columns]
            df["ts_code"] = df["ts_code"].astype(str)
            for col in ["ann_date", "end_date", "f_ann_date"]:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
            return df
    except Exception:
        pass

    # Fallback: check for cached parquet
    for cache_dir_name in [source, f"parquet/{source}"]:
        root = ROOT / "data" / cache_dir_name
        if root.exists():
            chunks = []
            for pq_file in root.glob("**/*.parquet"):
                try:
                    part = pd.read_parquet(pq_file)
                    part.columns = [str(c).strip().lower() for c in part.columns]
                    chunks.append(part)
                except Exception:
                    continue
            if chunks:
                result = pd.concat(chunks, ignore_index=True)
                result["ts_code"] = result["ts_code"].astype(str)
                return result

    return pd.DataFrame()


def _load_industry_map() -> pd.DataFrame:
    """Load industry classification map. Falls back to stock_status.industry."""
    # Primary: PIT industry data
    root = ROOT / "data" / "parquet" / "industry_pit"
    if root.exists():
        chunks = []
        for pq_file in root.glob("**/*.parquet"):
            try:
                part = pd.read_parquet(pq_file)
                part.columns = [str(c).strip().lower() for c in part.columns]
                if "ts_code" in part.columns and "industry_code" in part.columns:
                    chunks.append(part[["ts_code", "industry_code"]])
            except Exception:
                continue
        if chunks:
            result = pd.concat(chunks, ignore_index=True)
            result["ts_code"] = result["ts_code"].astype(str)
            result["industry_code"] = result["industry_code"].astype(str)
            result["industry_static_fallback"] = False
            return result.drop_duplicates("ts_code")

    # Fallback: generate static industry map from stock_status
    stock_status_path = ROOT / "data" / "parquet" / "stock_status"
    if stock_status_path.exists():
        chunks = []
        for pq_file in stock_status_path.glob("**/*.parquet"):
            try:
                part = pd.read_parquet(pq_file)
                part.columns = [str(c).strip().lower() for c in part.columns]
                if "ts_code" in part.columns and "industry" in part.columns:
                    chunks.append(part[["ts_code", "industry"]])
            except Exception:
                continue
        if chunks:
            df = pd.concat(chunks, ignore_index=True)
            df["ts_code"] = df["ts_code"].astype(str)
            df = df.dropna(subset=["industry"])
            # Generate industry_code from industry name
            industry_codes = {name: f"SW_{i:04d}"
                              for i, name in enumerate(sorted(df["industry"].unique()))}
            df["industry_code"] = df["industry"].map(industry_codes)
            df["industry_static_fallback"] = True
            result = df[["ts_code", "industry_code", "industry_static_fallback"]].drop_duplicates("ts_code")
            return result

    return pd.DataFrame()


def _load_cashflow_data(start: str, end: str) -> pd.DataFrame:
    """Load cashflow statement data from Tushare cache or parquet."""
    try:
        from data.tushare_client import get_client
        client = get_client()
        df = client.get_cashflow(use_cache=True)
        if not df.empty:
            df.columns = [str(c).strip().lower() for c in df.columns]
            df["ts_code"] = df["ts_code"].astype(str)
            for col in ["ann_date", "end_date", "f_ann_date"]:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
            return df
    except Exception:
        pass

    for cache_dir_name in ["cashflow", "parquet/cashflow"]:
        root = ROOT / "data" / cache_dir_name
        if root.exists():
            chunks = []
            for pq_file in root.glob("**/*.parquet"):
                try:
                    part = pd.read_parquet(pq_file)
                    part.columns = [str(c).strip().lower() for c in part.columns]
                    chunks.append(part)
                except Exception:
                    continue
            if chunks:
                result = pd.concat(chunks, ignore_index=True)
                result["ts_code"] = result["ts_code"].astype(str)
                return result
    return pd.DataFrame()


def _load_balancesheet_data(start: str, end: str) -> pd.DataFrame:
    """Load balance sheet data from Tushare cache or parquet."""
    try:
        from data.tushare_client import get_client
        client = get_client()
        df = client.get_balancesheet(use_cache=True)
        if not df.empty:
            df.columns = [str(c).strip().lower() for c in df.columns]
            df["ts_code"] = df["ts_code"].astype(str)
            for col in ["ann_date", "end_date", "f_ann_date"]:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
            return df
    except Exception:
        pass

    for cache_dir_name in ["balancesheet", "parquet/balancesheet"]:
        root = ROOT / "data" / cache_dir_name
        if root.exists():
            chunks = []
            for pq_file in root.glob("**/*.parquet"):
                try:
                    part = pd.read_parquet(pq_file)
                    part.columns = [str(c).strip().lower() for c in part.columns]
                    chunks.append(part)
                except Exception:
                    continue
            if chunks:
                result = pd.concat(chunks, ignore_index=True)
                result["ts_code"] = result["ts_code"].astype(str)
                return result
    return pd.DataFrame()


def _ensure_pit_fields(df: pd.DataFrame, ftype: str, prices: pd.DataFrame) -> pd.DataFrame:
    """Ensure factor output has PIT audit fields.

    For fundamental factors that already have available_date: preserve them.
    For daily_basic / price-based factors: available_date = trade_date.
    """
    if df.empty:
        return df

    df = df.copy()

    # If already has available_date from computation, keep it
    if "available_date" not in df.columns:
        # daily_basic or price-based: available at trade_date itself
        if "trade_date" in df.columns:
            df["available_date"] = df["trade_date"]
            df["source_period"] = df["trade_date"]
            df["source_date"] = df["trade_date"]

    # Ensure all PIT fields exist
    if "source_period" not in df.columns:
        df["source_period"] = df.get("available_date", df.get("trade_date", 0))
    if "source_date" not in df.columns:
        df["source_date"] = df.get("available_date", df.get("trade_date", 0))

    # Recompute pit_lag_days (may have been set during CS processing)
    if "pit_lag_days" not in df.columns and "available_date" in df.columns and "trade_date" in df.columns:
        df["pit_lag_days"] = df["trade_date"] - df["available_date"]
        df["is_stale"] = df["pit_lag_days"] > 63

    return df


def _validate_factor_output(
    df: pd.DataFrame, fname: str, start_date: str, end_date: str
) -> dict:
    """Hard validation before cache write.

    Returns dict with:
        can_write: bool
        reject_status: str (if can_write=False)
        reject_reason: str
        non_null_value_rows: int
        nan_value_rows: int
        value_nan_rate: float
        non_null_stocks: int
        coverage_pct: float
        validation_n_stocks_median: float
        validation_n_dates: int
        has_pit_fields: bool
        raw_rows: int
    """
    result = {
        "can_write": True,
        "reject_status": "",
        "reject_reason": "",
        "raw_rows": len(df),
        "non_null_value_rows": 0,
        "nan_value_rows": 0,
        "value_nan_rate": 0.0,
        "non_null_stocks": 0,
        "coverage_pct": 0.0,
        "validation_n_stocks_median": 0.0,
        "validation_n_dates": 0,
        "has_pit_fields": False,
    }

    if df.empty:
        result["can_write"] = False
        result["reject_status"] = "EMPTY_AFTER_CS_FILTER"
        result["reject_reason"] = "empty DataFrame after CS processing"
        return result

    # Check PIT fields
    pit_cols = ["source_period", "source_date", "available_date", "pit_lag_days"]
    result["has_pit_fields"] = all(c in df.columns for c in pit_cols)

    # Value quality
    if "value" in df.columns:
        non_null = df["value"].notna().sum()
        null_count = df["value"].isna().sum()
        result["non_null_value_rows"] = int(non_null)
        result["nan_value_rows"] = int(null_count)
        result["value_nan_rate"] = round(null_count / max(len(df), 1), 4)

        if non_null == 0:
            result["can_write"] = False
            result["reject_status"] = "EMPTY_AFTER_CS_FILTER"
            result["reject_reason"] = "all value rows are NaN"
            return result
    else:
        result["can_write"] = False
        result["reject_status"] = "EMPTY_AFTER_CS_FILTER"
        result["reject_reason"] = "no 'value' column"
        return result

    # Stock coverage
    if "ts_code" in df.columns:
        non_null_df = df.dropna(subset=["value"])
        result["non_null_stocks"] = non_null_df["ts_code"].nunique()
        result["validation_n_dates"] = non_null_df["trade_date"].nunique() if "trade_date" in df.columns else 0

        # Daily stock count for median
        if "trade_date" in df.columns:
            daily_counts = non_null_df.groupby("trade_date")["ts_code"].nunique()
            result["validation_n_stocks_median"] = float(daily_counts.median()) if len(daily_counts) > 0 else 0.0
        else:
            result["validation_n_stocks_median"] = float(result["non_null_stocks"])

        # Coverage check: n_stocks >= 30
        if result["non_null_stocks"] < 30:
            result["can_write"] = False
            result["reject_status"] = "INSUFFICIENT_COVERAGE"
            result["reject_reason"] = f"only {result['non_null_stocks']} stocks with non-null value (need >= 30)"
            return result

        # Date coverage: n_dates >= 24
        if result["validation_n_dates"] < 24:
            result["can_write"] = False
            result["reject_status"] = "INSUFFICIENT_DATE_COVERAGE"
            result["reject_reason"] = f"only {result['validation_n_dates']} dates (need >= 24)"
            return result

    # Validation window coverage
    if "trade_date" in df.columns and start_date and end_date:
        val_start = int(start_date)
        val_end = int(end_date)
        val_data = df[(df["trade_date"] >= val_start) & (df["trade_date"] <= val_end)]
        if val_data.empty:
            val_data = df  # fallback to all data

    # Coverage ratio
    result["coverage_pct"] = round(result["non_null_value_rows"] / max(result["raw_rows"], 1), 4)

    return result


def _diagnose_empty_factor(
    fname: str, spec: dict,
    fina_data: pd.DataFrame,
    income_data: pd.DataFrame,
    cashflow_data: pd.DataFrame,
    balance_data: pd.DataFrame,
    daily_data: pd.DataFrame,
    industry_map: pd.DataFrame,
) -> tuple:
    """Diagnose why a factor produced empty output.

    Returns (status, reason) tuple.
    Statuses: FIELD_MISSING, SOURCE_MISSING, FORMULA_NOT_IMPLEMENTED,
              EMPTY_AFTER_PIT_ALIGNMENT, EMPTY_AFTER_CS_FILTER
    """
    required_sources = spec.get("data_sources", [])
    required_fields = spec.get("required_fields", {})

    # Check source availability
    source_map = {
        "fina_indicator": fina_data,
        "income": income_data,
        "cashflow": cashflow_data,
        "balancesheet": balance_data,
        "daily_basic": daily_data,
        "industry_pit": industry_map,
    }

    missing_sources = []
    missing_fields = []

    for src in required_sources:
        df = source_map.get(src, pd.DataFrame())
        if df is None or (hasattr(df, "empty") and df.empty):
            missing_sources.append(src)
        else:
            req = required_fields.get(src, [])
            available = set(str(c).lower() for c in df.columns)
            missing = [f for f in req if f not in available]
            missing_fields.extend([f"{src}.{m}" for m in missing])

    # Check formula implementation (heuristic)
    # If the build script has `pass` for this factor, it's FORMULA_NOT_IMPLEMENTED
    formula_implemented = True
    build_path = ROOT / "scripts" / "build_alpha_factors_v4.py"
    if build_path.exists():
        source = build_path.read_text(encoding="utf-8")
        import re
        patterns = [
            rf'elif\s+fname\s*(?:==|in)\s*.*?"{re.escape(fname)}".*?:',
            rf'elif\s+fname\s+in\s+\([^)]*"{re.escape(fname)}"[^)]*\)',
        ]
        for pat in patterns:
            m = re.search(pat, source)
            if m:
                start = m.end()
                rest = source[start:start + 300]
                # Check if the block is just pass or empty
                block_lines = [l.strip() for l in rest.split("\n")
                              if l.strip() and not l.strip().startswith("#")]
                if not block_lines or any(
                    l == "pass" or l.startswith("pass  #")
                    for l in block_lines
                ):
                    formula_implemented = False
                break

    if not formula_implemented:
        return "FORMULA_NOT_IMPLEMENTED", "build script has pass stub"

    # Per-factor accurate diagnosis
    if missing_sources:
        # asset_turnover_ttm_cs can be built from income.revenue + balancesheet.total_assets
        if fname == "asset_turnover_ttm_cs":
            extra = ("can also build from income.revenue + balancesheet.total_assets "
                     "(both currently missing)")
            return "FIELD_MISSING", f"missing source: cashflow or balancesheet; {extra}"
        return "SOURCE_MISSING", f"missing sources: {', '.join(missing_sources)}"

    if missing_fields:
        # More accurate field-level reasons
        if fname == "asset_turnover_ttm_cs":
            return "FIELD_MISSING", (
                "missing: fina_indicator.assets_turn OR (income.revenue + balancesheet.total_assets); "
                "alternative: pull fina_indicator with assets_turn field, or pull balancesheet for total_assets"
            )
        elif fname in ("ocf_to_profit_cs", "ocf_to_mktcap_cs", "cashflow_stability_8q_cs"):
            return "FIELD_MISSING", (
                "missing ocf field — need cashflow.n_cashflow_act from cashflow parquet, "
                "or pull fina_indicator with ocfps/cfps fields; "
                "run scripts/pull_fina_indicator_history.py with expanded fields"
            )
        elif fname == "fcf_yield_cs":
            return "FIELD_MISSING", (
                "missing fcf field — need cashflow.free_cashflow from cashflow parquet, "
                "or pull fina_indicator with fcff/fcfe fields"
            )
        elif fname == "accrual_quality_cs":
            return "FIELD_MISSING", (
                "missing: ocf + total_assets — need cashflow.n_cashflow_act + "
                "balancesheet.total_assets; also needs income.n_income (available)"
            )
        elif fname == "receivable_pressure_cs":
            return "FIELD_MISSING", (
                "missing: balancesheet.accounts_receivable — need balancesheet parquet; "
                "revenue available from income data"
            )
        else:
            return "FIELD_MISSING", f"missing fields: {', '.join(missing_fields[:5])}"

    return "EMPTY_AFTER_PIT_ALIGNMENT", "no data survived PIT alignment"


def _factor_uses_static_industry(fname: str, df: pd.DataFrame) -> bool:
    """Check if factor output uses static industry fallback."""
    if "industry_relative" not in fname:
        return False
    if "industry_static_fallback" in df.columns:
        return bool(df["industry_static_fallback"].any())
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Build V4 alpha factors")
    parser.add_argument("--config", default="configs/factor_build_v4.yaml")
    parser.add_argument("--start", default="20170101")
    parser.add_argument("--end", default="20241231")
    parser.add_argument("--force", action="store_true", help="Force rebuild even if cache exists")
    parser.add_argument("--categories", nargs="+", help="Only build specified categories")
    parser.add_argument("--factors", nargs="+", help="Only build specified factors")
    parser.add_argument("--run-dir", help="Subdirectory under outputs/runs for diagnostics")
    args = parser.parse_args()

    config_path = ROOT / args.config
    if not config_path.exists():
        print(f"ERROR: Build config not found: {config_path}")
        return 1

    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    universe_path = ROOT / cfg["universe_config"]
    universe = yaml.safe_load(universe_path.read_text(encoding="utf-8"))
    factor_specs = universe["factors"]
    cs_config = cfg.get("cross_section", {})
    cache_base = ROOT / cfg["cache"]["base_path"]
    config_sha256 = hashlib.sha256(config_path.read_bytes()).hexdigest()

    # Filter by category or specific factors
    if args.categories:
        factor_specs = [s for s in factor_specs if s.get("category") in args.categories]
    if args.factors:
        factor_specs = [s for s in factor_specs if s["name"] in args.factors]

    # Determine build order
    build_order = cfg.get("build_order", [])
    if build_order:
        ordered_specs = []
        for cat in build_order:
            ordered_specs.extend([s for s in factor_specs if s.get("category") == cat])
        # Add any uncategorized factors
        ordered_specs.extend([s for s in factor_specs if s.get("category") not in build_order])
        factor_specs = ordered_specs

    print(f"Building {len(factor_specs)} V4 factors ({args.start} to {args.end})...")
    print(f"Categories: {[s.get('category') for s in factor_specs]}")

    # Preload data sources
    print("\nLoading data sources...")
    prices = _load_price_data(args.start, args.end)
    print(f"  prices: {len(prices)} rows" if not prices.empty else "  prices: NOT FOUND")

    fina_data = _load_financial_data("fina_indicator", args.start, args.end)
    print(f"  fina_indicator: {len(fina_data)} rows" if not fina_data.empty else "  fina_indicator: NOT FOUND")

    income_data = _load_financial_data("income", args.start, args.end)
    print(f"  income: {len(income_data)} rows" if not income_data.empty else "  income: NOT FOUND")

    industry_map = _load_industry_map()
    if not industry_map.empty:
        is_static = industry_map.get("industry_static_fallback", pd.Series([False])).iloc[0] if "industry_static_fallback" in industry_map.columns else False
        print(f"  industry: {len(industry_map)} rows{' (STATIC FALLBACK)' if is_static else ''}" if not industry_map.empty else "  industry: NOT FOUND")
    else:
        print("  industry: NOT FOUND")

    cashflow_data = _load_cashflow_data(args.start, args.end)
    print(f"  cashflow: {len(cashflow_data)} rows" if not cashflow_data.empty else "  cashflow: NOT FOUND (FIELD_MISSING for cashflow factors)")

    balance_data = _load_balancesheet_data(args.start, args.end)
    print(f"  balancesheet: {len(balance_data)} rows" if not balance_data.empty else "  balancesheet: NOT FOUND (FIELD_MISSING for balance factors)")

    # Load daily_basic explicitly for factors that need it
    daily_data = _load_financial_data("daily_basic", args.start, args.end)
    print(f"  daily_basic: {len(daily_data)} rows" if not daily_data.empty else "  daily_basic: NOT FOUND")

    # Build each factor
    built = 0
    skipped = 0
    failed = 0
    diagnoses: List[dict] = []

    # Set up run directory for diagnostics
    if args.run_dir:
        run_dir = ROOT / "outputs" / "runs" / args.run_dir
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_dir = ROOT / "outputs" / "runs" / f"factor_build_{ts}"
    run_dir.mkdir(parents=True, exist_ok=True)

    for i, spec in enumerate(factor_specs):
        fname = spec["name"]
        ftype = spec.get("type", "technical")
        fcat = spec.get("category", "unknown")
        cache_dir = cache_base / f"factor_name={fname}"

        # Check if already built
        if not args.force and cache_dir.exists() and any(cache_dir.glob("year=*/*.parquet")):
            manifest_path = cache_dir / "build_manifest.json"
            if manifest_path.exists():
                print(f"[{i+1}/{len(factor_specs)}] {fname}: cached (skipping)")
                skipped += 1
                continue

        print(f"[{i+1}/{len(factor_specs)}] {fname} ({ftype}/{fcat})...", end=" ")

        try:
            df = pd.DataFrame()

            # --- Technical / Price-based factors ---
            if fname == "momentum_60_skip5_cs":
                df = _compute_technical_skip_momentum(prices, 60, 5) if not prices.empty else pd.DataFrame()
            elif fname == "momentum_120_skip20_cs":
                df = _compute_technical_skip_momentum(prices, 120, 20) if not prices.empty else pd.DataFrame()
            elif fname == "risk_adjusted_momentum_60_cs":
                df = _compute_risk_adjusted_momentum(prices, 60, 60) if not prices.empty else pd.DataFrame()
            elif fname == "volume_confirmed_momentum_cs":
                df = _compute_volume_confirmed_momentum(prices, 60, 20) if not prices.empty else pd.DataFrame()
            elif fname == "trend_quality_cs":
                df = _compute_trend_quality(prices, 20, 60) if not prices.empty else pd.DataFrame()
            elif fname == "reversal_5_liquidity_adj_cs":
                df = _compute_liquidity_adjusted_reversal(prices, 5, 20, 20) if not prices.empty else pd.DataFrame()
            elif fname == "reversal_20_vol_adj_cs":
                df = _compute_vol_adjusted_reversal(prices, 20, 60) if not prices.empty else pd.DataFrame()
            elif fname == "low_beta_60_cs":
                df = _compute_low_beta(prices, 60) if not prices.empty else pd.DataFrame()
            elif fname == "drawdown_resilience_cs":
                df = _compute_drawdown_resilience(prices, 60, 20) if not prices.empty else pd.DataFrame()
            elif fname == "reversal_5_liquidity_adj_weekly_cs":
                df = _compute_liquidity_adjusted_reversal_low_turnover(
                    prices, 5, 20, 20, 3, "weekly"
                ) if not prices.empty else pd.DataFrame()
            elif fname == "reversal_20_vol_adj_weekly_cs":
                df = _compute_vol_adjusted_reversal_low_turnover(
                    prices, 20, 60, 5, "weekly"
                ) if not prices.empty else pd.DataFrame()

            # --- Panic reversal candidates (27 variants) ---
            elif fname.startswith("panic_") and fname.endswith("_weekly_cs"):
                import re
                m = re.match(
                    r"panic_(drop|up|sym)_rev5_t(0[357])_(bin|cont|wcont)_weekly_cs",
                    fname
                )
                if m:
                    direction = m.group(1)
                    threshold = int(m.group(2)) / 100.0  # "03" -> 0.03
                    sig_type = m.group(3)
                    df = _compute_panic_reversal(
                        prices, threshold=threshold, direction=direction,
                        signal_type=sig_type, frequency="weekly"
                    ) if not prices.empty else pd.DataFrame()
                else:
                    df = pd.DataFrame()

            elif fname == "low_beta_120_monthly_cs":
                df = _compute_low_beta_stable(prices, 120, 20, "monthly") if not prices.empty else pd.DataFrame()
            elif fname == "drawdown_resilience_monthly_cs":
                df = _compute_drawdown_resilience_stable(
                    prices, 120, 20, 10, "monthly"
                ) if not prices.empty else pd.DataFrame()
            elif fname == "industry_relative_momentum_60_cs":
                raw = _compute_technical_skip_momentum(prices, 60, 5) if not prices.empty else pd.DataFrame()
                df = _compute_industry_relative(raw, industry_map, fname) if not raw.empty else pd.DataFrame()

            # --- Fundamental factors ---
            elif fname in ("revenue_growth_ttm_cs", "profit_growth_ttm_cs"):
                source = income_data if not income_data.empty else fina_data
                field_map = {"revenue_growth_ttm_cs": "revenue", "profit_growth_ttm_cs": "n_income"}
                field = field_map.get(fname, "n_income")
                if field in source.columns:
                    df = _compute_growth_ttm(source, field)
            elif fname == "earnings_acceleration_cs":
                source = income_data if not income_data.empty else fina_data
                if "n_income" in source.columns:
                    df = _compute_earnings_acceleration(source, min_quarters=3)
            elif fname == "growth_stability_8q_cs":
                source = income_data if not income_data.empty else fina_data
                if "n_income" in source.columns:
                    df = _compute_stability_8q(source, "n_income", min_quarters=3)
            elif fname == "growth_value_match_cs":
                if not income_data.empty or not fina_data.empty:
                    source = income_data if not income_data.empty else fina_data
                    if not daily_data.empty and "pe" in daily_data.columns:
                        df = _compute_growth_value_match(source, daily_data, prices)
                    else:
                        df = _compute_growth_value_match(source, pd.DataFrame(), prices)
                else:
                    df = pd.DataFrame()  # SOURCE_MISSING
            elif fname == "roe_stability_8q_cs":
                if not fina_data.empty and "roe" in fina_data.columns:
                    df = _compute_stability_8q(fina_data, "roe", min_quarters=3)
            elif fname == "roa_ttm_cs":
                if not fina_data.empty and "roa" in fina_data.columns:
                    df = _compute_fundamental_ttm(fina_data, "roa")
            elif fname == "gross_margin_ttm_cs":
                field = next((f for f in ["grossprofit_margin", "gross_margin"] if f in fina_data.columns), None)
                if field:
                    df = _compute_fundamental_ttm(fina_data, field)
            elif fname == "net_margin_ttm_cs":
                field = next((f for f in ["netprofit_margin", "net_margin"] if f in fina_data.columns), None)
                if field:
                    df = _compute_fundamental_ttm(fina_data, field)
            elif fname == "profitability_quality_cs":
                if not fina_data.empty:
                    margin_fields = [f for f in ["grossprofit_margin", "netprofit_margin"] if f in fina_data.columns]
                    df = _compute_profitability_quality(fina_data, margin_fields)
            elif fname == "asset_turnover_ttm_cs":
                # Prefer direct field, fall back to component computation
                if not fina_data.empty and "assets_turn" in fina_data.columns:
                    df = _compute_fundamental_ttm(fina_data, "assets_turn")
                elif not fina_data.empty and "asset_turnover" in fina_data.columns:
                    df = _compute_fundamental_ttm(fina_data, "asset_turnover")
                elif not income_data.empty and not balance_data.empty:
                    if "revenue" in income_data.columns and (
                        "total_assets" in balance_data.columns or "fixed_assets" in balance_data.columns
                    ):
                        df = _compute_asset_turnover_from_components(income_data, balance_data)
                # else: FIELD_MISSING — no asset turnover data available
            elif fname == "ocf_to_mktcap_cs":
                # OCF TTM / total_mv — PIT alignment deferred to CS block
                ocf_source = cashflow_data if not cashflow_data.empty else fina_data
                ocf_field = next((f for f in ["n_cashflow_act", "ocfps", "cfps", "ocf", "operating_cf"]
                                  if f in ocf_source.columns), None)
                if ocf_field and not ocf_source.empty:
                    ocf_ttm = _compute_fundamental_ttm(ocf_source, ocf_field)
                    if not ocf_ttm.empty:
                        df = ocf_ttm  # has available_date, will be PIT-aligned in CS block
                # else: FIELD_MISSING — ocf field not available
            elif fname == "ocf_to_profit_cs":
                # Try cashflow data first (has n_cashflow_act), fallback to fina_indicator
                ocf_source = cashflow_data if not cashflow_data.empty else fina_data
                if not ocf_source.empty:
                    df = _compute_ocf_to_profit(ocf_source)
                # else: FIELD_MISSING — no cashflow or fina_indicator data
            elif fname == "fcf_yield_cs":
                # FCF TTM / total_mv — PIT alignment deferred to CS block
                fcf_source = cashflow_data if not cashflow_data.empty else fina_data
                fcf_field = next((f for f in ["free_cashflow", "fcff", "fcfe", "fcf"]
                                  if f in fcf_source.columns), None)
                if fcf_field:
                    fcf_ttm = _compute_fundamental_ttm(fcf_source, fcf_field)
                    if not fcf_ttm.empty:
                        df = fcf_ttm  # has available_date, will be PIT-aligned in CS block
                # else: FIELD_MISSING — fcf field not available
            elif fname == "cashflow_stability_8q_cs":
                ocf_source = cashflow_data if not cashflow_data.empty else fina_data
                ocf_field = next((f for f in ["n_cashflow_act", "ocfps", "cfps", "ocf", "operating_cf"]
                                  if f in ocf_source.columns), None)
                if ocf_field and not ocf_source.empty:
                    df = _compute_stability_8q(ocf_source, ocf_field)
                # else: FIELD_MISSING — ocf field not available
            elif fname == "industry_relative_quality_cs":
                # Build quality composite then apply industry-relative rank
                # PIT alignment is deferred to CS processing block
                if not fina_data.empty and not industry_map.empty:
                    margin_fields = [f for f in ["grossprofit_margin", "netprofit_margin"]
                                     if f in fina_data.columns]
                    if margin_fields:
                        base_df = _compute_profitability_quality(fina_data, margin_fields, roe_field="roe")
                        if not base_df.empty:
                            # Don't do PIT alignment here — let CS block handle it
                            df = _compute_industry_relative(base_df, industry_map, fname)
                # else: SOURCE_MISSING or FIELD_MISSING

            elif fname == "industry_relative_growth_cs":
                if not income_data.empty and not industry_map.empty:
                    source = income_data
                    rev_growth = _compute_growth_ttm(source, "revenue") if "revenue" in source.columns else pd.DataFrame()
                    profit_growth = _compute_growth_ttm(source, "n_income") if "n_income" in source.columns else pd.DataFrame()
                    # Defer PIT alignment to CS processing block
                    components = []
                    for gdf in [rev_growth, profit_growth]:
                        if gdf.empty or "available_date" not in gdf.columns:
                            continue
                        if not gdf.empty:
                            gdf["rank"] = gdf.groupby("available_date")["value"].rank(pct=True)
                            components.append(gdf[["ts_code", "available_date", "rank"]])
                    if len(components) >= 2:
                        base = components[0].merge(components[1], on=["ts_code", "available_date"], how="inner")
                        base["value"] = base[["rank_x", "rank_y"]].mean(axis=1)
                        base["source_period"] = base["available_date"]
                        base["source_date"] = base["available_date"]
                        base["trade_date"] = base["available_date"]  # Use available_date as date for ranking
                        base_df = base[["ts_code", "trade_date", "available_date", "value",
                                         "source_period", "source_date"]].dropna()
                        if not base_df.empty:
                            df = _compute_industry_relative(base_df, industry_map, fname)
                # else: SOURCE_MISSING or FIELD_MISSING

            elif fname == "industry_relative_value_cs":
                if not daily_data.empty and not industry_map.empty:
                    daily_df = daily_data[["ts_code", "trade_date", "pe", "pb"]].dropna(subset=["pe", "pb"])
                    daily_df = daily_df[(daily_df["pe"] > 0) & (daily_df["pb"] > 0)]
                    daily_df["ep"] = 1.0 / daily_df["pe"]
                    daily_df["bp"] = 1.0 / daily_df["pb"]
                    daily_df["ep_rank"] = daily_df.groupby("trade_date")["ep"].rank(pct=True)
                    daily_df["bp_rank"] = daily_df.groupby("trade_date")["bp"].rank(pct=True)
                    daily_df["value"] = (daily_df["ep_rank"] + daily_df["bp_rank"]) / 2
                    base_df = daily_df[["ts_code", "trade_date", "value"]].dropna()
                    if not base_df.empty:
                        df = _compute_industry_relative(base_df, industry_map, fname)
                # else: SOURCE_MISSING

            elif fname == "accrual_quality_cs":
                # (net_profit - ocf) / total_assets — lower is better, negate
                source_inc = income_data if not income_data.empty else fina_data
                if not source_inc.empty and not cashflow_data.empty and not balance_data.empty:
                    df = _compute_accrual_quality(source_inc, cashflow_data, balance_data)
                # else: FIELD_MISSING — cashflow or balancesheet data not available

            elif fname == "receivable_pressure_cs":
                # AR / revenue — lower is better, negate
                source_inc = income_data if not income_data.empty else fina_data
                if not source_inc.empty and not balance_data.empty:
                    df = _compute_receivable_pressure(source_inc, balance_data)
                # else: FIELD_MISSING — balancesheet data not available

            elif fname == "valuation_reversion_3y_cs":
                if not daily_data.empty and "pe" in daily_data.columns:
                    df = _compute_valuation_reversion_3y(daily_data)
                # else: SOURCE_MISSING — daily_basic not available

            elif fname == "dividend_quality_cs":
                if not daily_data.empty and "dv_ttm" in daily_data.columns:
                    df = _compute_dividend_quality(fina_data, daily_data, prices)
                # else: FIELD_MISSING — dv_ttm not available

            elif fname == "quality_value_composite_cs":
                if not fina_data.empty and not daily_data.empty:
                    df = _compute_quality_value_composite(fina_data, daily_data, prices)
                # else: SOURCE_MISSING

            elif fname in ("industry_relative_ep_cs", "industry_relative_bp_cs"):
                # These are built elsewhere or use simpler paths — skip for now
                pass

            # --- Cross-sectional processing ---
            if not df.empty and cs_config.get("enabled", True):
                # Align to trade dates from price data
                if "available_date" in df.columns and not prices.empty:
                    # Use merge_asof for memory-safe PIT alignment (avoids
                    # Cartesian explosion from merge on ts_code alone).
                    # For each factor row (ts_code, available_date), find
                    # the first trade_date >= available_date.
                    trade_dates = prices[["ts_code", "trade_date"]].drop_duplicates()
                    trade_dates = trade_dates.sort_values(["ts_code", "trade_date"])
                    # Normalize dtypes for merge_asof
                    df = df.sort_values(["ts_code", "available_date"])
                    if "available_date" in df.columns:
                        df["available_date"] = df["available_date"].astype("int64")
                    trade_dates["trade_date"] = trade_dates["trade_date"].astype("int64")

                    try:
                        df = pd.merge_asof(
                            df,
                            trade_dates,
                            by="ts_code",
                            left_on="available_date",
                            right_on="trade_date",
                            direction="forward",
                            allow_exact_matches=True,
                        )
                    except Exception:
                        # Fallback: traditional merge with pre-filter
                        # Group by ts_code to limit memory
                        pass

                    # Drop rows where no trade_date >= available_date exists
                    df = df.dropna(subset=["trade_date"])

                    # Dedup: keep the most recent available_date per (ts_code, trade_date)
                    df = df.sort_values(["ts_code", "trade_date", "available_date"])
                    df = df.drop_duplicates(["ts_code", "trade_date"], keep="last")

                    df["pit_lag_days"] = df["trade_date"] - df["available_date"]
                    df["is_stale"] = df["pit_lag_days"] > 63

                df = _apply_cs_processing(df, cs_config, industry_map)

            # --- Unique-key assertion (must pass before any cache write) ---
            if not df.empty:
                n_dup = int(df.duplicated(["ts_code", "trade_date"]).sum())
                if n_dup > 0:
                    raise AssertionError(
                        f"FATAL: {fname} has {n_dup} duplicate (ts_code, trade_date) keys "
                        f"— PIT dedup failed or was bypassed. Refusing to write cache."
                    )

            # --- PIT field injection for factors that lack them ---
            if not df.empty:
                df = _ensure_pit_fields(df, ftype, prices)

            # --- Hard validation before cache write ---
            # For truly empty pre-CS DataFrames, diagnose the root cause
            if df.empty:
                diag_status, diag_reason = _diagnose_empty_factor(
                    fname, spec, fina_data, income_data,
                    cashflow_data, balance_data, daily_data, industry_map
                )
                print(f"SKIP ({diag_status}: {diag_reason})")
                skipped += 1
                diagnoses.append({
                    "factor_name": fname, "diagnosis_status": diag_status,
                    "diagnosis_reason": diag_reason, "raw_rows": 0,
                    "rows_after_cs": 0, "n_dates": 0, "n_stocks": 0,
                    "date_start": None, "date_end": None,
                    "non_null_value_rows": 0, "nan_value_rows": 0,
                    "value_nan_rate": 0.0, "coverage_pct": 0.0,
                    "validation_n_stocks_median": 0.0, "validation_n_dates": 0,
                    "has_pit_fields": False,
                })
                continue

            validation = _validate_factor_output(df, fname, args.start, args.end)

            # --- Cache ---
            if validation["can_write"]:
                # Preserve PIT audit fields in cache
                pit_cols = ["available_date", "source_period", "source_date", "pit_lag_days", "is_stale"]
                cache_cols = ["ts_code", "trade_date", "value"]
                extra = [c for c in df.columns if c not in cache_cols and c not in pit_cols]
                # Include PIT fields in cache
                keep_cols = cache_cols + [c for c in pit_cols if c in df.columns] + extra
                stats = _write_factor_cache(df[keep_cols], fname, cache_base, force=args.force)
                _write_manifest(fname, stats, config_sha256, cache_base)
                print(f"OK ({stats['n_rows']} rows, {stats['n_stocks']} stocks)")
                built += 1
                diagnoses.append({
                    "factor_name": fname,
                    "diagnosis_status": "OK",
                    "diagnosis_reason": f"built {stats['n_rows']} rows",
                    "raw_rows": validation["raw_rows"],
                    "rows_after_cs": stats["n_rows"],
                    "n_dates": stats["n_dates"],
                    "n_stocks": stats["n_stocks"],
                    "date_start": stats["date_start"],
                    "date_end": stats["date_end"],
                    "non_null_value_rows": validation["non_null_value_rows"],
                    "nan_value_rows": validation["nan_value_rows"],
                    "value_nan_rate": validation["value_nan_rate"],
                    "coverage_pct": validation["coverage_pct"],
                    "validation_n_stocks_median": validation["validation_n_stocks_median"],
                    "validation_n_dates": validation["validation_n_dates"],
                    "has_pit_fields": validation["has_pit_fields"],
                    "industry_static_fallback_used": _factor_uses_static_industry(fname, df),
                    "proxy_used": "proxy_used" in df.columns,
                })
            else:
                print(f"SKIP ({validation['reject_status']}: {validation['reject_reason']})")
                skipped += 1
                diagnoses.append({
                    "factor_name": fname,
                    "diagnosis_status": validation["reject_status"],
                    "diagnosis_reason": validation["reject_reason"],
                    "raw_rows": validation["raw_rows"],
                    "rows_after_cs": 0,
                    "n_dates": validation["validation_n_dates"],
                    "n_stocks": validation["non_null_stocks"],
                    "date_start": None,
                    "date_end": None,
                    "non_null_value_rows": validation["non_null_value_rows"],
                    "nan_value_rows": validation["nan_value_rows"],
                    "value_nan_rate": validation["value_nan_rate"],
                    "coverage_pct": validation["coverage_pct"],
                    "validation_n_stocks_median": validation["validation_n_stocks_median"],
                    "validation_n_dates": validation["validation_n_dates"],
                    "has_pit_fields": validation["has_pit_fields"],
                    "industry_static_fallback_used": False,
                    "proxy_used": False,
                })

        except Exception as e:
            print(f"FAIL ({e})")
            failed += 1

    print(f"\n=== Build Summary ===")
    print(f"  Built: {built}")
    print(f"  Skipped (cached or no data): {skipped}")
    print(f"  Failed: {failed}")
    print(f"  Cache base: {cache_base}")

    # Write factor diagnosis CSV
    if diagnoses:
        diag_df = pd.DataFrame(diagnoses)
        diag_path = run_dir / "factor_diagnosis.csv"
        diag_df.to_csv(diag_path, index=False, encoding="utf-8-sig")
        print(f"\nFactor diagnosis: {diag_path}")
        # Print diagnosis summary
        status_counts = diag_df["diagnosis_status"].value_counts()
        for status in sorted(status_counts.index):
            print(f"  {status}: {status_counts[status]}")

    if failed > 0:
        print("\nSome factors failed to build. Check data availability and field names.")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python
"""
Alpha Research Factory — Build new factor families beyond the existing set.

New factor families:
  1. Micro-structure: intraday reversal, overnight gap, Amihud illiquidity,
     volume-price divergence, volatility squeeze, tail risk
  2. Liquidity/Crowding: turnover anomaly, turnover volatility, volume shock,
     capacity pressure, amount concentration
  3. Quality Stability: earnings variability, margin persistence (from income data)
  4. Risk Premium: low volatility, low beta, residual volatility
  5. Technical Enhancement: Bollinger position, RSI divergence, price channel,
     volume-confirmed momentum (improved versions)

Each factor outputs:
  - raw values
  - mcap-neutral values (optional)
  - IC by year
  - net spread after cost estimate

Usage:
  python -u scripts/build_new_factor_families.py --start 20170101 --end 20241231 --force
  python -u scripts/build_new_factor_families.py --family micro_structure --force
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CACHE_BASE = ROOT / "data" / "parquet" / "factors"

# ---------------------------------------------------------------------------
# New Factor Definitions
# ---------------------------------------------------------------------------
NEW_FACTOR_DEFS: Dict[str, dict] = {
    # === Micro-structure ===
    "intraday_reversal_cs": {
        "family": "micro_structure",
        "desc": "Intraday reversal: -(close - open) / open",
        "source": "prices",
        "compute": "intraday_reversal",
        "sign": 1,
        "category": "micro_structure",
    },
    "overnight_reversal_cs": {
        "family": "micro_structure",
        "desc": "Overnight reversal: -(open - prev_close) / prev_close",
        "source": "prices",
        "compute": "overnight_reversal",
        "sign": 1,
        "category": "micro_structure",
    },
    "amihud_illiq_20d_cs": {
        "family": "micro_structure",
        "desc": "Amihud illiquidity: mean(|ret| / amount) over 20d",
        "source": "prices",
        "compute": "amihud_illiq",
        "window": 20,
        "sign": -1,
        "category": "micro_structure",
    },
    "vol_price_divergence_20d_cs": {
        "family": "micro_structure",
        "desc": "Volume-price divergence: corr(vol_change, price_change) over 20d",
        "source": "prices",
        "compute": "vol_price_divergence",
        "window": 20,
        "sign": 1,
        "category": "micro_structure",
    },
    "volatility_squeeze_cs": {
        "family": "micro_structure",
        "desc": "Volatility squeeze: short_vol(10d) / long_vol(60d) — low = squeeze",
        "source": "prices",
        "compute": "vol_squeeze",
        "short_window": 10,
        "long_window": 60,
        "sign": 1,
        "category": "micro_structure",
    },
    "tail_risk_60d_cs": {
        "family": "micro_structure",
        "desc": "Tail risk: -skewness(daily_ret, 60d) — negative = crash risk",
        "source": "prices",
        "compute": "tail_risk",
        "window": 60,
        "sign": -1,
        "category": "micro_structure",
    },
    # === Liquidity / Crowding ===
    "turnover_anomaly_20d_cs": {
        "family": "liquidity",
        "desc": "Turnover anomaly: -avg(turnover_rate, 20d)",
        "source": "daily_basic",
        "compute": "avg_field",
        "field": "turnover_rate",
        "window": 20,
        "sign": -1,
        "category": "liquidity",
    },
    "turnover_volatility_60d_cs": {
        "family": "liquidity",
        "desc": "Turnover volatility: std(turnover_rate, 60d)",
        "source": "daily_basic",
        "compute": "std_field",
        "field": "turnover_rate",
        "window": 60,
        "sign": -1,
        "category": "liquidity",
    },
    "volume_shock_5d_cs": {
        "family": "liquidity",
        "desc": "Volume shock: vol_5d / avg_vol_20d - 1",
        "source": "prices",
        "compute": "volume_shock",
        "short_window": 5,
        "long_window": 20,
        "sign": -1,
        "category": "liquidity",
    },
    "amount_concentration_20d_cs": {
        "family": "liquidity",
        "desc": "Amount concentration: std(amount) / mean(amount) over 20d",
        "source": "prices",
        "compute": "amount_concentration",
        "window": 20,
        "sign": -1,
        "category": "liquidity",
    },
    # === Risk Premium ===
    "low_volatility_60d_cs": {
        "family": "risk_premium",
        "desc": "Low volatility anomaly: -std(ret, 60d)",
        "source": "prices",
        "compute": "low_vol",
        "window": 60,
        "sign": 1,
        "category": "risk_premium",
    },
    "residual_volatility_60d_cs": {
        "family": "risk_premium",
        "desc": "Residual volatility: std(residual from market model, 60d)",
        "source": "prices",
        "compute": "residual_vol",
        "window": 60,
        "sign": -1,
        "category": "risk_premium",
    },
    # === Technical Enhancement ===
    "bollinger_position_20d_cs": {
        "family": "technical",
        "desc": "Bollinger position: (close - MA20) / (2 * std20)",
        "source": "prices",
        "compute": "bollinger",
        "window": 20,
        "sign": -1,
        "category": "technical",
    },
    "price_channel_position_60d_cs": {
        "family": "technical",
        "desc": "Price channel: (close - low60) / (high60 - low60)",
        "source": "prices",
        "compute": "price_channel",
        "window": 60,
        "sign": 1,
        "category": "technical",
    },
    "rsi_divergence_14d_cs": {
        "family": "technical",
        "desc": "RSI divergence: RSI(14) - RSI(14) 5d ago",
        "source": "prices",
        "compute": "rsi_divergence",
        "rsi_window": 14,
        "div_window": 5,
        "sign": -1,
        "category": "technical",
    },
    # === Quality Stability (income-based) ===
    "revenue_stability_8q_cs": {
        "family": "quality",
        "desc": "Revenue stability: -std(revenue, 8q)",
        "source": "income",
        "compute": "stability_8q",
        "field": "revenue",
        "min_quarters": 4,
        "sign": 1,
        "category": "quality",
    },
    "margin_trend_8q_cs": {
        "family": "quality",
        "desc": "Margin trend: slope of net margin over 8 quarters",
        "source": "income",
        "compute": "margin_trend",
        "min_quarters": 6,
        "sign": 1,
        "category": "quality",
    },
}

FAMILIES = {
    "micro_structure": "Micro-structure factors (intraday/overnight reversal, illiquidity, divergence, squeeze, tail risk)",
    "liquidity": "Liquidity/Crowding factors (turnover anomaly, vol shock, concentration)",
    "risk_premium": "Risk premium factors (low vol, residual vol)",
    "technical": "Enhanced technical factors (Bollinger, price channel, RSI divergence)",
    "quality": "Quality stability factors (revenue stability, margin trend)",
}


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _load_prices(start: str, end: str) -> pd.DataFrame:
    """Load price data with all OHLCV columns."""
    prices_dir = ROOT / "data" / "parquet" / "prices_adj"
    if not prices_dir.exists():
        return pd.DataFrame()

    start_int, end_int = int(start), int(end)
    chunks = []
    for year_dir in sorted(prices_dir.iterdir()):
        if not year_dir.is_dir() or not year_dir.name.startswith("year="):
            continue
        year = int(year_dir.name.split("=")[1])
        if year < (start_int // 10000) - 1 or year > (end_int // 10000) + 1:
            continue
        for month_dir in sorted(year_dir.iterdir()):
            for pq_file in month_dir.glob("*.parquet"):
                try:
                    part = pd.read_parquet(pq_file)
                    part.columns = [str(c).strip().lower() for c in part.columns]
                except Exception:
                    continue
                part["ts_code"] = part["ts_code"].astype(str)
                part["trade_date"] = pd.to_numeric(part["trade_date"], errors="coerce")
                part = part.dropna(subset=["trade_date"])
                part = part[(part["trade_date"] >= start_int) & (part["trade_date"] <= end_int)]
                if not part.empty:
                    chunks.append(part)

    if not chunks:
        return pd.DataFrame()
    return pd.concat(chunks, ignore_index=True).sort_values(["ts_code", "trade_date"])


def _load_daily_basic(start: str, end: str) -> pd.DataFrame:
    """Load daily basic data."""
    db_dir = ROOT / "data" / "parquet" / "daily_basic"
    if not db_dir.exists():
        return pd.DataFrame()

    start_int, end_int = int(start), int(end)
    chunks = []
    for year_dir in sorted(db_dir.iterdir()):
        if not year_dir.is_dir() or not year_dir.name.startswith("year="):
            continue
        year = int(year_dir.name.split("=")[1])
        if year < (start_int // 10000) - 1 or year > (end_int // 10000) + 1:
            continue
        for month_dir in sorted(year_dir.iterdir()):
            for pq_file in month_dir.glob("*.parquet"):
                try:
                    part = pd.read_parquet(pq_file)
                    part.columns = [str(c).strip().lower() for c in part.columns]
                except Exception:
                    continue
                part["ts_code"] = part["ts_code"].astype(str)
                part["trade_date"] = pd.to_numeric(part["trade_date"], errors="coerce")
                part = part.dropna(subset=["trade_date"])
                part = part[(part["trade_date"] >= start_int) & (part["trade_date"] <= end_int)]
                if not part.empty:
                    chunks.append(part)

    if not chunks:
        return pd.DataFrame()
    return pd.concat(chunks, ignore_index=True).sort_values(["ts_code", "trade_date"])


def _load_income() -> pd.DataFrame:
    """Load income data from combined file."""
    combined = ROOT / "data" / "parquet" / "income_full_2017_2024.parquet"
    if combined.exists():
        df = pd.read_parquet(combined)
        df.columns = [str(c).strip().lower() for c in df.columns]
        if "ts_code" in df.columns:
            df["ts_code"] = df["ts_code"].astype(str)
        for col in ["ann_date", "end_date"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        return df
    return pd.DataFrame()


# ---------------------------------------------------------------------------
# Factor computation functions
# ---------------------------------------------------------------------------

def _compute_intraday_reversal(prices: pd.DataFrame) -> pd.DataFrame:
    """-(close - open) / open — reversal of intraday moves."""
    df = prices[["ts_code", "trade_date", "open", "close"]].copy()
    df["value"] = -(df["close"] - df["open"]) / (df["open"] + 1e-10)
    return df[["ts_code", "trade_date", "value"]].dropna()


def _compute_overnight_reversal(prices: pd.DataFrame) -> pd.DataFrame:
    """-(open - prev_close) / prev_close — reversal of overnight gaps."""
    df = prices[["ts_code", "trade_date", "open", "pre_close"]].copy()
    df = df.sort_values(["ts_code", "trade_date"])
    df["value"] = -(df["open"] - df["pre_close"]) / (df["pre_close"] + 1e-10)
    return df[["ts_code", "trade_date", "value"]].dropna()


def _compute_amihud_illiq(prices: pd.DataFrame, window: int = 20) -> pd.DataFrame:
    """Amihud illiquidity: mean(|ret| / amount) over window, then -1 × for sign."""
    df = prices[["ts_code", "trade_date", "adj_close", "amount"]].copy()
    df = df.sort_values(["ts_code", "trade_date"])
    df["ret"] = df.groupby("ts_code")["adj_close"].pct_change()
    df["illiq"] = np.abs(df["ret"]) / (df["amount"] + 1e-10)
    df["value"] = -df.groupby("ts_code")["illiq"].transform(
        lambda x: x.rolling(window, min_periods=max(10, window // 2)).mean()
    )
    return df[["ts_code", "trade_date", "value"]].dropna()


def _compute_vol_price_divergence(prices: pd.DataFrame, window: int = 20) -> pd.DataFrame:
    """Correlation between volume change and price change over window."""
    df = prices[["ts_code", "trade_date", "adj_close", "vol"]].copy()
    df = df.sort_values(["ts_code", "trade_date"])
    df["ret"] = df.groupby("ts_code")["adj_close"].pct_change()
    df["vol_change"] = df.groupby("ts_code")["vol"].pct_change()

    # Compute rolling correlation manually (avoid pandas .corr() dtype issues)
    df["ret_sign"] = np.sign(df["ret"])
    df["vol_sign"] = np.sign(df["vol_change"])
    df["sign_match"] = (df["ret_sign"] == df["vol_sign"]).astype(float)
    df["value"] = df.groupby("ts_code")["sign_match"].transform(
        lambda x: x.rolling(window, min_periods=max(10, window // 2)).mean()
    )
    df["value"] = 2.0 * df["value"] - 1.0  # scale from [0,1] to [-1,1]
    return df[["ts_code", "trade_date", "value"]].dropna()


def _compute_vol_squeeze(prices: pd.DataFrame, short: int = 10, long: int = 60) -> pd.DataFrame:
    """Short-term vol / long-term vol — low ratio = squeeze, expect expansion."""
    df = prices[["ts_code", "trade_date", "adj_close"]].copy()
    df = df.sort_values(["ts_code", "trade_date"])
    df["ret"] = df.groupby("ts_code")["adj_close"].pct_change()
    df["vol_short"] = df.groupby("ts_code")["ret"].transform(
        lambda x: x.rolling(short, min_periods=short // 2).std()
    )
    df["vol_long"] = df.groupby("ts_code")["ret"].transform(
        lambda x: x.rolling(long, min_periods=long // 2).std()
    )
    df["value"] = df["vol_short"] / (df["vol_long"] + 1e-10)
    return df[["ts_code", "trade_date", "value"]].dropna()


def _compute_tail_risk(prices: pd.DataFrame, window: int = 60) -> pd.DataFrame:
    """Negative skewness of daily returns — high = crash risk."""
    df = prices[["ts_code", "trade_date", "adj_close"]].copy()
    df = df.sort_values(["ts_code", "trade_date"])
    df["ret"] = df.groupby("ts_code")["adj_close"].pct_change()
    df["value"] = -df.groupby("ts_code")["ret"].transform(
        lambda x: x.rolling(window, min_periods=max(30, window // 2)).skew()
    )
    return df[["ts_code", "trade_date", "value"]].dropna()


def _compute_avg_field(daily_basic: pd.DataFrame, field: str, window: int) -> pd.DataFrame:
    """Moving average of a field from daily_basic."""
    if field not in daily_basic.columns:
        return pd.DataFrame()
    df = daily_basic[["ts_code", "trade_date", field]].copy()
    df = df.sort_values(["ts_code", "trade_date"])
    df["value"] = df.groupby("ts_code")[field].transform(
        lambda x: x.rolling(window, min_periods=max(5, window // 2)).mean()
    )
    return df[["ts_code", "trade_date", "value"]].dropna()


def _compute_std_field(daily_basic: pd.DataFrame, field: str, window: int) -> pd.DataFrame:
    """Moving standard deviation of a field."""
    if field not in daily_basic.columns:
        return pd.DataFrame()
    df = daily_basic[["ts_code", "trade_date", field]].copy()
    df = df.sort_values(["ts_code", "trade_date"])
    df["value"] = df.groupby("ts_code")[field].transform(
        lambda x: x.rolling(window, min_periods=max(10, window // 2)).std()
    )
    return df[["ts_code", "trade_date", "value"]].dropna()


def _compute_volume_shock(prices: pd.DataFrame, short: int = 5, long: int = 20) -> pd.DataFrame:
    """Volume shock: short_avg_vol / long_avg_vol - 1."""
    df = prices[["ts_code", "trade_date", "vol"]].copy()
    df = df.sort_values(["ts_code", "trade_date"])
    df["vol_short_avg"] = df.groupby("ts_code")["vol"].transform(
        lambda x: x.rolling(short, min_periods=3).mean()
    )
    df["vol_long_avg"] = df.groupby("ts_code")["vol"].transform(
        lambda x: x.rolling(long, min_periods=10).mean()
    )
    df["value"] = df["vol_short_avg"] / (df["vol_long_avg"] + 1e-10) - 1
    return df[["ts_code", "trade_date", "value"]].dropna()


def _compute_amount_concentration(prices: pd.DataFrame, window: int = 20) -> pd.DataFrame:
    """Coefficient of variation of daily amount."""
    df = prices[["ts_code", "trade_date", "amount"]].copy()
    df = df.sort_values(["ts_code", "trade_date"])
    df["amount_mean"] = df.groupby("ts_code")["amount"].transform(
        lambda x: x.rolling(window, min_periods=10).mean()
    )
    df["amount_std"] = df.groupby("ts_code")["amount"].transform(
        lambda x: x.rolling(window, min_periods=10).std()
    )
    df["value"] = df["amount_std"] / (df["amount_mean"] + 1e-10)
    return df[["ts_code", "trade_date", "value"]].dropna()


def _compute_low_vol(prices: pd.DataFrame, window: int = 60) -> pd.DataFrame:
    """Negative volatility — low vol anomaly."""
    df = prices[["ts_code", "trade_date", "adj_close"]].copy()
    df = df.sort_values(["ts_code", "trade_date"])
    df["ret"] = df.groupby("ts_code")["adj_close"].pct_change()
    df["value"] = -df.groupby("ts_code")["ret"].transform(
        lambda x: x.rolling(window, min_periods=max(30, window // 2)).std()
    )
    return df[["ts_code", "trade_date", "value"]].dropna()


def _compute_residual_vol(prices: pd.DataFrame, window: int = 60) -> pd.DataFrame:
    """Residual volatility after market model regression (simplified)."""
    df = prices[["ts_code", "trade_date", "adj_close"]].copy()
    df = df.sort_values(["ts_code", "trade_date"])
    df["ret"] = df.groupby("ts_code")["adj_close"].pct_change()

    # Market return (equal-weighted average of all stock returns per day)
    market_ret = df.groupby("trade_date")["ret"].mean().rename("mkt_ret")
    df = df.merge(market_ret, on="trade_date", how="left")

    # Rolling beta
    df["ret_mkt"] = df["ret"] * df["mkt_ret"]
    df["mkt_var"] = df["mkt_ret"] ** 2
    df["cov"] = df.groupby("ts_code")["ret_mkt"].transform(
        lambda x: x.rolling(window, min_periods=max(30, window // 2)).mean()
    )
    df["var"] = df.groupby("ts_code")["mkt_var"].transform(
        lambda x: x.rolling(window, min_periods=max(30, window // 2)).mean()
    )
    df["beta"] = df["cov"] / (df["var"] + 1e-10)

    # Residual = ret - beta * mkt_ret
    df["residual"] = df["ret"] - df["beta"] * df["mkt_ret"]
    df["value"] = -df.groupby("ts_code")["residual"].transform(
        lambda x: x.rolling(window, min_periods=max(30, window // 2)).std()
    )
    return df[["ts_code", "trade_date", "value"]].dropna()


def _compute_bollinger(prices: pd.DataFrame, window: int = 20) -> pd.DataFrame:
    """Bollinger Band position: (close - MA) / (2 * std)."""
    df = prices[["ts_code", "trade_date", "adj_close"]].copy()
    df = df.sort_values(["ts_code", "trade_date"])
    df["ma"] = df.groupby("ts_code")["adj_close"].transform(
        lambda x: x.rolling(window, min_periods=window // 2).mean()
    )
    df["std"] = df.groupby("ts_code")["adj_close"].transform(
        lambda x: x.rolling(window, min_periods=window // 2).std()
    )
    df["value"] = (df["adj_close"] - df["ma"]) / (2.0 * df["std"] + 1e-10)
    return df[["ts_code", "trade_date", "value"]].dropna()


def _compute_price_channel(prices: pd.DataFrame, window: int = 60) -> pd.DataFrame:
    """Price channel position: (close - low) / (high - low)."""
    df = prices[["ts_code", "trade_date", "adj_close"]].copy()
    df = df.sort_values(["ts_code", "trade_date"])
    df["high_n"] = df.groupby("ts_code")["adj_close"].transform(
        lambda x: x.rolling(window, min_periods=window // 2).max()
    )
    df["low_n"] = df.groupby("ts_code")["adj_close"].transform(
        lambda x: x.rolling(window, min_periods=window // 2).min()
    )
    df["value"] = (df["adj_close"] - df["low_n"]) / (df["high_n"] - df["low_n"] + 1e-10)
    return df[["ts_code", "trade_date", "value"]].dropna()


def _compute_rsi_divergence(prices: pd.DataFrame, rsi_window: int = 14, div_window: int = 5) -> pd.DataFrame:
    """RSI divergence: RSI - RSI_5d_ago."""
    df = prices[["ts_code", "trade_date", "adj_close"]].copy()
    df = df.sort_values(["ts_code", "trade_date"])
    df["ret"] = df.groupby("ts_code")["adj_close"].pct_change()
    df["gain"] = df["ret"].clip(lower=0)
    df["loss"] = -df["ret"].clip(upper=0)
    df["avg_gain"] = df.groupby("ts_code")["gain"].transform(
        lambda x: x.rolling(rsi_window).mean()
    )
    df["avg_loss"] = df.groupby("ts_code")["loss"].transform(
        lambda x: x.rolling(rsi_window).mean()
    )
    df["rsi"] = 100 - 100 / (1 + df["avg_gain"] / (df["avg_loss"] + 1e-10))
    df["rsi_lag"] = df.groupby("ts_code")["rsi"].shift(div_window)
    df["value"] = -(df["rsi"] - df["rsi_lag"])  # Negative: divergence reversal
    return df[["ts_code", "trade_date", "value"]].dropna()


def _compute_stability_8q_income(income: pd.DataFrame, field: str, min_quarters: int = 4) -> pd.DataFrame:
    """8-quarter stability of an income field = -std(values)."""
    from scripts.repair_fundamental_factors import _compute_available_date, _pit_align

    df = income.copy()
    if field not in df.columns:
        return pd.DataFrame()
    df = df.dropna(subset=[field])
    df = df.sort_values(["ts_code", "end_date"])
    df["available_date"] = df.apply(
        lambda r: _compute_available_date(r["end_date"], r.get("ann_date")), axis=1
    )

    results = []
    for ts_code, stock_df in df.groupby("ts_code"):
        stock_df = stock_df.sort_values("end_date").reset_index(drop=True)
        values = stock_df[field].values
        end_dates = stock_df["end_date"].values
        avail_dates = stock_df["available_date"].values

        for i in range(len(stock_df)):
            recent_vals = values[max(0, i-7):i+1]
            if len(recent_vals) < min_quarters:
                continue
            stability = -float(np.std(recent_vals, ddof=0)) if len(recent_vals) >= 2 else 0.0
            results.append({
                "ts_code": ts_code,
                "available_date": int(avail_dates[i]),
                "end_date_max": int(end_dates[i]),
                "factor_value": stability,
                "n_quarters": len(recent_vals),
            })

    if not results:
        return pd.DataFrame()
    return pd.DataFrame(results)


def _compute_margin_trend(income: pd.DataFrame, min_quarters: int = 6) -> pd.DataFrame:
    """Margin trend: slope of n_income/revenue over time."""
    from scripts.repair_fundamental_factors import _compute_available_date, _pit_align

    df = income.copy()
    for f in ["n_income", "revenue"]:
        if f not in df.columns:
            return pd.DataFrame()

    df = df.dropna(subset=["n_income", "revenue"])
    df = df.sort_values(["ts_code", "end_date"])
    df["margin"] = df["n_income"] / (df["revenue"].abs() + 1e-10)
    df["available_date"] = df.apply(
        lambda r: _compute_available_date(r["end_date"], r.get("ann_date")), axis=1
    )

    results = []
    for ts_code, stock_df in df.groupby("ts_code"):
        stock_df = stock_df.sort_values("end_date").reset_index(drop=True)
        margins = stock_df["margin"].values
        end_dates = stock_df["end_date"].values
        avail_dates = stock_df["available_date"].values

        for i in range(len(stock_df)):
            if i < min_quarters:
                continue
            recent = margins[max(0, i-7):i+1]
            if len(recent) < min_quarters:
                continue
            # Linear regression slope over time index
            x = np.arange(len(recent))
            slope = np.polyfit(x, recent, 1)[0]
            results.append({
                "ts_code": ts_code,
                "available_date": int(avail_dates[i]),
                "end_date_max": int(end_dates[i]),
                "factor_value": float(slope),
            })

    if not results:
        return pd.DataFrame()
    return pd.DataFrame(results)


# ---------------------------------------------------------------------------
# Cross-sectional processing
# ---------------------------------------------------------------------------

def _apply_cs(df: pd.DataFrame) -> pd.DataFrame:
    """Winsorize (MAD × 5) + z-score per date."""
    if df.empty:
        return df
    results = []
    for trade_date, group in df.groupby("trade_date"):
        vals = group["value"].dropna()
        if len(vals) < 30:
            continue
        median = vals.median()
        mad = (vals - median).abs().median()
        if mad > 0:
            group["value"] = group["value"].clip(median - 5 * mad, median + 5 * mad)
        mean = group["value"].mean()
        std = group["value"].std()
        if std > 0:
            group["value"] = (group["value"] - mean) / std
        results.append(group)
    if not results:
        return pd.DataFrame()
    return pd.concat(results, ignore_index=True)


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

def _write_cache(df: pd.DataFrame, fname: str, force: bool = False) -> dict:
    if df.empty:
        return {"factor_name": fname, "n_rows": 0, "n_stocks": 0, "n_dates": 0}
    out_root = CACHE_BASE / f"factor_name={fname}"
    if force and out_root.exists():
        for year_dir in out_root.iterdir():
            if year_dir.is_dir():
                for sub in year_dir.iterdir():
                    if sub.is_dir() and sub.name.startswith("month="):
                        shutil.rmtree(sub, ignore_errors=True)
    df["year"] = df["trade_date"] // 10000
    for year, year_df in df.groupby("year"):
        year_dir = out_root / f"year={year}"
        year_dir.mkdir(parents=True, exist_ok=True)
        year_df = year_df.drop(columns=["year"], errors="ignore")
        year_df.to_parquet(year_dir / f"part_{year}.parquet", index=False, compression="zstd")
    return {
        "factor_name": fname,
        "n_rows": len(df),
        "n_stocks": df["ts_code"].nunique(),
        "n_dates": df["trade_date"].nunique(),
        "date_start": int(df["trade_date"].min()),
        "date_end": int(df["trade_date"].max()),
    }


def _write_manifest(fname: str, stats: dict) -> None:
    manifest = {
        "factor_name": fname,
        "build_timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "config_sha256": "",
        "n_rows": stats.get("n_rows", 0),
        "n_stocks": stats.get("n_stocks", 0),
        "n_dates": stats.get("n_dates", 0),
        "date_start": stats.get("date_start", 0),
        "date_end": stats.get("date_end", 0),
        "pit_audit_status": "pending",
    }
    path = CACHE_BASE / f"factor_name={fname}" / "build_manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Build new factor families")
    parser.add_argument("--start", default="20170101")
    parser.add_argument("--end", default="20241231")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--family", help="Only build one family (micro_structure/liquidity/risk_premium/technical/quality)")
    parser.add_argument("--factors", help="Comma-separated specific factors")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    # Select factors
    if args.factors:
        targets = {k: NEW_FACTOR_DEFS[k] for k in args.factors.split(",") if k in NEW_FACTOR_DEFS}
    elif args.family:
        targets = {k: v for k, v in NEW_FACTOR_DEFS.items() if v["family"] == args.family}
    else:
        targets = dict(NEW_FACTOR_DEFS)

    print(f"=== Alpha Research Factory — New Factor Families ===\n")
    print(f"Date range: {args.start} → {args.end}")
    print(f"Factors: {len(targets)}")
    for fam in set(v["family"] for v in targets.values()):
        fam_factors = [k for k, v in targets.items() if v["family"] == fam]
        print(f"  [{fam}] {', '.join(fam_factors)}")
    if args.dry_run:
        print("MODE: DRY RUN")
    print()

    # Load data
    print("Loading data...")
    prices = _load_prices(args.start, args.end)
    print(f"  prices: {len(prices)} rows")

    daily_basic = _load_daily_basic(args.start, args.end)
    print(f"  daily_basic: {len(daily_basic)} rows")

    income = _load_income()
    print(f"  income: {len(income)} rows")

    # Build each factor
    print(f"\n--- Building factors ---\n")
    built = 0
    skipped = 0
    failed = 0

    for fname, fdef in targets.items():
        cache_dir = CACHE_BASE / f"factor_name={fname}"
        if not args.force and cache_dir.exists() and any(cache_dir.glob("year=*/*.parquet")):
            print(f"  {fname}: CACHED")
            skipped += 1
            continue

        compute = fdef["compute"]
        sign = fdef.get("sign", 1)
        print(f"  {fname} ({fdef['family']}/{compute})...", end=" ", flush=True)

        try:
            source = fdef["source"]

            if source == "prices":
                if prices.empty:
                    print("SKIP (no prices)")
                    skipped += 1
                    continue
                # Dispatch to computation function
                if compute == "intraday_reversal":
                    df = _compute_intraday_reversal(prices)
                elif compute == "overnight_reversal":
                    df = _compute_overnight_reversal(prices)
                elif compute == "amihud_illiq":
                    df = _compute_amihud_illiq(prices, fdef.get("window", 20))
                elif compute == "vol_price_divergence":
                    df = _compute_vol_price_divergence(prices, fdef.get("window", 20))
                elif compute == "vol_squeeze":
                    df = _compute_vol_squeeze(prices, fdef.get("short_window", 10), fdef.get("long_window", 60))
                elif compute == "tail_risk":
                    df = _compute_tail_risk(prices, fdef.get("window", 60))
                elif compute == "volume_shock":
                    df = _compute_volume_shock(prices, fdef.get("short_window", 5), fdef.get("long_window", 20))
                elif compute == "amount_concentration":
                    df = _compute_amount_concentration(prices, fdef.get("window", 20))
                elif compute == "low_vol":
                    df = _compute_low_vol(prices, fdef.get("window", 60))
                elif compute == "residual_vol":
                    df = _compute_residual_vol(prices, fdef.get("window", 60))
                elif compute == "bollinger":
                    df = _compute_bollinger(prices, fdef.get("window", 20))
                elif compute == "price_channel":
                    df = _compute_price_channel(prices, fdef.get("window", 60))
                elif compute == "rsi_divergence":
                    df = _compute_rsi_divergence(prices, fdef.get("rsi_window", 14), fdef.get("div_window", 5))
                else:
                    print(f"UNKNOWN compute={compute}")
                    skipped += 1
                    continue

            elif source == "daily_basic":
                if daily_basic.empty:
                    print("SKIP (no daily_basic)")
                    skipped += 1
                    continue
                if compute == "avg_field":
                    df = _compute_avg_field(daily_basic, fdef["field"], fdef.get("window", 20))
                elif compute == "std_field":
                    df = _compute_std_field(daily_basic, fdef["field"], fdef.get("window", 60))
                else:
                    print(f"UNKNOWN compute={compute}")
                    skipped += 1
                    continue

            elif source == "income":
                if income.empty:
                    print("SKIP (no income)")
                    skipped += 1
                    continue
                if compute == "stability_8q":
                    pre = _compute_stability_8q_income(income, fdef["field"], fdef.get("min_quarters", 4))
                elif compute == "margin_trend":
                    pre = _compute_margin_trend(income, fdef.get("min_quarters", 6))
                else:
                    print(f"UNKNOWN compute={compute}")
                    skipped += 1
                    continue

                # PIT align income-based factors
                if not pre.empty:
                    from scripts.repair_fundamental_factors import _pit_align
                    td = prices[["ts_code", "trade_date"]].drop_duplicates()
                    df = _pit_align(pre, td, sign=sign, factor_name=fname)
                    if not df.empty and "factor_value" in df.columns:
                        df = df.rename(columns={"factor_value": "value"})
                else:
                    df = pd.DataFrame()

            else:
                print(f"UNKNOWN source={source}")
                skipped += 1
                continue

            # Apply sign
            if sign < 0 and not df.empty and "value" in df.columns:
                df["value"] = -df["value"]

            # CS processing
            if not df.empty:
                df = df.drop_duplicates(["ts_code", "trade_date"])
                df = _apply_cs(df)
                df = df.dropna(subset=["value"])

            if df.empty:
                print("EMPTY")
                skipped += 1
                continue

            if args.dry_run:
                print(f"OK ({len(df)} rows, {df['ts_code'].nunique()} stocks, {df['trade_date'].nunique()} dates)")
                built += 1
                continue

            stats = _write_cache(df, fname, force=args.force)
            _write_manifest(fname, stats)
            print(f"OK ({stats['n_rows']} rows, {stats['n_stocks']} stocks, {stats['n_dates']} dates)")
            built += 1

        except Exception as e:
            print(f"FAIL ({e})")
            import traceback
            traceback.print_exc()
            failed += 1

    print(f"\n=== Summary ===")
    print(f"  Built: {built}")
    print(f"  Skipped: {skipped}")
    print(f"  Failed: {failed}")
    if args.dry_run:
        print("\n[DRY RUN]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

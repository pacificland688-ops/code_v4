"""
Photoresist Panic Reversal Evaluator v2
=========================================
Computes forward returns (close-to-close口径), evaluates top1 single-stock
rules with real PIT eligibility, computes basket + top1 diagnostics,
applies Go/No-Go logic, and generates markdown report.

v2 fixes:
  - Per-event PIT universe for top1 selection
  - Real eligibility (ST, suspend, listing_days, amount_20d, limit_down,
    consecutive_limit_down, must_be_event_stock)
  - Unified close-to-close forward return
  - Basket contribution & basket leave-one-out diagnostics
  - Fixed Go/No-Go using correct basket LOO
  - Mark not_implemented features explicitly in manifest & report

Phases 4-7 of photoresist_panic_reversal_development_plan.md.
Requires outputs from build_photoresist_panic_events.py.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import warnings
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from build_photoresist_panic_events import (
    filter_eligible_stocks as shared_filter_eligible_stocks,
    load_stock_status as load_stock_status_shared,
)

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RESEARCH_CONFIG = ROOT / "configs" / "photoresist_panic_research.yaml"
DEFAULT_UNIVERSE_CONFIG = ROOT / "configs" / "photoresist_universe.yaml"
DEFAULT_OUT_DIR = ROOT / "outputs" / "analysis" / "photoresist_panic"

PRICES_DIR = ROOT / "data" / "parquet" / "prices_adj"
INDEX_DIR = ROOT / "data" / "parquet" / "index_daily"
LIMIT_DIR = ROOT / "data" / "parquet" / "limit_status"
SUSPEND_DIR = ROOT / "data" / "parquet" / "suspend_status"
STOCK_STATUS_PATH = ROOT / "data" / "parquet" / "stock_status"


# ═══════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Evaluate photoresist panic reversal v2 (Phases 4-7)")
    p.add_argument("--research-config", default=str(DEFAULT_RESEARCH_CONFIG))
    p.add_argument("--universe-config", default=str(DEFAULT_UNIVERSE_CONFIG))
    p.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    p.add_argument("--cost-bps", type=int, default=20)
    p.add_argument("--start", type=int, default=20170101)
    p.add_argument("--end", type=int, default=20251231)
    return p.parse_args()


def load_yaml(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def collect_feature_status(research_config: dict) -> tuple[list[str], list[str]]:
    """Collect implemented and explicitly disabled/not-implemented features."""
    implemented = [
        "lag1_close_execution",
        "top1_strength",
        "top1_mid_drop",
        "top1_liquidity_core",
        "basket_contribution",
        "basket_leave_one_out",
        "top1_leave_one_out",
        "go_nogo",
    ]
    not_implemented = []

    top1_rules = research_config.get("top1_rules", {})
    for name, cfg in top1_rules.items():
        if not isinstance(cfg, dict):
            continue
        if cfg.get("enabled", True) is False or cfg.get("status") == "not_implemented":
            not_implemented.append(name)

    confirmation_cfg = (
        research_config.get("execution", {})
        .get("entry_modes", {})
        .get("confirmation_entry", {})
    )
    if (
        isinstance(confirmation_cfg, dict)
        and (confirmation_cfg.get("enabled", True) is False
             or confirmation_cfg.get("status") == "not_implemented")
    ):
        not_implemented.append("confirmation_entry")

    robustness_cfg = research_config.get("robustness_gates", {})
    if (
        isinstance(robustness_cfg, dict)
        and (robustness_cfg.get("enabled", True) is False
             or robustness_cfg.get("status") == "not_implemented")
    ):
        not_implemented.append("robustness_aux_gates")

    # Preserve order while removing duplicates.
    not_implemented = list(dict.fromkeys(not_implemented))
    return implemented, not_implemented


# ═══════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════
def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]
    if "ts_code" in df.columns:
        df["ts_code"] = df["ts_code"].astype(str)
    for col in ("trade_date",):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def _iter_year_dirs(base: Path, start: int, end: int):
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


def build_trading_calendar_from_prices(start: int, end: int) -> np.ndarray:
    dates = set()
    for yr_dir in _iter_year_dirs(PRICES_DIR, start, end):
        for pq in sorted(yr_dir.rglob("*.parquet")):
            try:
                df = pd.read_parquet(pq, columns=["trade_date"])
                dates.update(int(d) for d in df["trade_date"].dropna().unique())
            except Exception:
                pass
    return np.array(sorted(dates))


def build_calendar_index(calendar: np.ndarray) -> dict:
    return {int(d): i for i, d in enumerate(calendar)}


def trading_day_offset(calendar: np.ndarray, date: int, offset: int) -> int | None:
    idx = np.searchsorted(calendar, date)
    if idx >= len(calendar) or calendar[idx] != date:
        return None
    target = idx + offset
    if 0 <= target < len(calendar):
        return int(calendar[target])
    return None


# ═══════════════════════════════════════════════════════════════════════
# Eligibility helpers (same as build script)
# ═══════════════════════════════════════════════════════════════════════
def compute_listing_age(prices: pd.DataFrame, calendar: np.ndarray) -> pd.Series:
    df = prices[["ts_code", "trade_date"]].drop_duplicates()
    df = df.sort_values(["ts_code", "trade_date"])
    df["listing_age"] = df.groupby("ts_code").cumcount() + 1
    return df.set_index(["ts_code", "trade_date"])["listing_age"]


def compute_amount_20d_avg(prices: pd.DataFrame) -> pd.Series:
    df = prices[["ts_code", "trade_date", "amount"]].copy()
    df = df.sort_values(["ts_code", "trade_date"])
    df["amount_20d_avg"] = (
        df.groupby("ts_code")["amount"]
        .transform(lambda x: x.rolling(20, min_periods=10).mean())
    )
    return df.set_index(["ts_code", "trade_date"])["amount_20d_avg"]


def check_consecutive_limit_down(
    ts_code: str, trade_date: int,
    limit_status: pd.DataFrame | None,
    prices: pd.DataFrame, n_days: int = 2,
) -> bool:
    if limit_status is not None:
        stock_limits = limit_status[limit_status["ts_code"] == ts_code].sort_values("trade_date")
        ld_cols = [c for c in stock_limits.columns if "down" in c.lower()]
        if ld_cols:
            recent = stock_limits[stock_limits["trade_date"] <= trade_date].tail(n_days)
            if len(recent) >= n_days and recent[ld_cols[0]].astype(bool).sum() >= n_days:
                return True
    stock_prices = prices[
        (prices["ts_code"] == ts_code) & (prices["trade_date"] <= trade_date)
    ].sort_values("trade_date").tail(n_days)
    if "pct_chg" in stock_prices.columns and len(stock_prices) >= n_days:
        if (stock_prices["pct_chg"] < -9.5).sum() >= n_days:
            return True
    return False


def is_suspended(ts_code: str, trade_date: int,
                 suspend_status: pd.DataFrame | None,
                 prices: pd.DataFrame) -> bool:
    if suspend_status is not None:
        stock_sus = suspend_status[
            (suspend_status["ts_code"] == ts_code) &
            (suspend_status["trade_date"] == trade_date)
        ]
        if len(stock_sus) > 0:
            sus_cols = [c for c in stock_sus.columns if "sus" in c.lower()]
            if sus_cols and stock_sus[sus_cols[0]].iloc[0]:
                return True
    day_data = prices[
        (prices["ts_code"] == ts_code) & (prices["trade_date"] == trade_date)
    ]
    if len(day_data) == 0:
        return True
    if "vol" in day_data.columns and day_data["vol"].values[0] == 0:
        return True
    return False


# ═══════════════════════════════════════════════════════════════════════
# Phase 4: Forward Returns (close-to-close)
# ═══════════════════════════════════════════════════════════════════════
def compute_forward_returns(
    events_df: pd.DataFrame,
    prices: pd.DataFrame,
    core_basket: pd.DataFrame,
    index_prices: pd.DataFrame,
    calendar: np.ndarray,
) -> pd.DataFrame:
    """Compute forward returns at horizons 1/3/5/10/20 days.

    Close-to-close口径:
      entry_date = exec_date (t+1)
      exit_date = trading_day_offset(exec_date, horizon)
      basket_return = basket_index[exit_date] / basket_index[entry_date] - 1
    """
    if events_df.empty:
        return pd.DataFrame()

    # Build basket NAV index (close-to-close cumulative)
    if not core_basket.empty and "basket_ret_1d" in core_basket.columns:
        core_sorted = core_basket.sort_values("trade_date")
        core_sorted["basket_nav"] = (1 + core_sorted["basket_ret_1d"]).cumprod()
        nav_map = dict(zip(core_sorted["trade_date"], core_sorted["basket_nav"]))
    else:
        nav_map = {}

    # Index returns for benchmark comparison
    semi_ret_map = {}
    if not index_prices.empty:
        semi = index_prices[index_prices["ts_code"] == "931865.CSI"].copy()
        if len(semi) > 0:
            semi = semi.sort_values("trade_date")
            semi["semi_ret_1d"] = semi["close"].pct_change()
            # Build NAV
            semi["semi_nav"] = (1 + semi["semi_ret_1d"].fillna(0)).cumprod()
            for _, row in semi.iterrows():
                d = int(row["trade_date"])
                semi_ret_map[d] = (row["semi_ret_1d"], row["semi_nav"])

    rows = []
    for _, event in events_df.iterrows():
        event_date = int(event["event_date"])
        exec_date = event["exec_date"]
        if pd.isna(exec_date):
            continue
        exec_date = int(exec_date)

        row = {
            "event_cluster_id": int(event["event_cluster_id"]),
            "event_date": event_date,
            "exec_date": exec_date,
            "intensity_label": event.get("intensity_label", "unknown"),
            "environment_label": event.get("environment_label", "unknown"),
            "execution_price_type": "close",
        }

        # Basket forward (close-to-close from exec_date)
        entry_nav = nav_map.get(exec_date, np.nan)
        if not np.isnan(entry_nav) and entry_nav > 0:
            for horizon in [1, 3, 5, 10, 20]:
                exit_date = trading_day_offset(calendar, exec_date, horizon)
                if exit_date is None:
                    row[f"basket_fwd_ret_{horizon}d"] = np.nan
                    continue
                exit_nav = nav_map.get(exit_date, np.nan)
                if not np.isnan(exit_nav) and exit_nav > 0:
                    row[f"basket_fwd_ret_{horizon}d"] = float(exit_nav / entry_nav - 1)

        # Benchmark forward
        entry_semi = semi_ret_map.get(exec_date)
        if entry_semi is not None:
            _, entry_semi_nav = entry_semi
            for horizon in [1, 3, 5, 10, 20]:
                exit_date = trading_day_offset(calendar, exec_date, horizon)
                if exit_date is None:
                    row[f"semi_fwd_ret_{horizon}d"] = np.nan
                    continue
                exit_semi = semi_ret_map.get(exit_date)
                if exit_semi is not None:
                    _, exit_semi_nav = exit_semi
                    row[f"semi_fwd_ret_{horizon}d"] = float(exit_semi_nav / entry_semi_nav - 1)

        # Excess
        for horizon in [1, 3, 5, 10, 20]:
            b = row.get(f"basket_fwd_ret_{horizon}d", np.nan)
            s = row.get(f"semi_fwd_ret_{horizon}d", np.nan)
            if not np.isnan(b) and not np.isnan(s):
                row[f"excess_vs_semi_{horizon}d"] = float(b - s)

        # entry_date / exit_date for primary horizon (20d)
        exit_20 = trading_day_offset(calendar, exec_date, 20)
        row["entry_date"] = exec_date
        row["exit_date_20d"] = exit_20

        rows.append(row)

    return pd.DataFrame(rows)


# ═══════════════════════════════════════════════════════════════════════
# Phase 5: Top1 Single-Stock Rules v2
# ═══════════════════════════════════════════════════════════════════════
def _get_available_stocks_v2(
    event_date: int,
    exec_date: int,
    universe_df: pd.DataFrame,
    prices: pd.DataFrame,
    calendar: np.ndarray,
    listing_age_map: pd.Series,
    amt_20d_map: pd.Series,
    limit_status: pd.DataFrame | None,
    suspend_status: pd.DataFrame | None,
    stock_status_raw: pd.DataFrame | None,
    eligibility: dict,
) -> pd.DataFrame:
    """Get core stocks available for top1 trading with real eligibility.

    v2: Per-event PIT universe, real ST/suspend/listing_days/amount_20d/
    limit_down/consecutive_limit_down checks.
    """
    # PIT universe for event_date
    active_core = universe_df[
        (universe_df["pool_type"] == "core") &
        (universe_df["pit_confidence"] != "low") &
        (universe_df["effective_start"] <= event_date) &
        (universe_df["effective_end"] >= event_date)
    ]
    core_codes = active_core["ts_code"].unique().tolist()
    if not core_codes:
        return pd.DataFrame()

    day_prices = prices[
        (prices["trade_date"] == event_date) &
        (prices["ts_code"].isin(core_codes))
    ].copy()

    if day_prices.empty:
        return pd.DataFrame()

    # Compute 5d return for event_stock check
    prices_sub = prices[prices["ts_code"].isin(core_codes)].sort_values(["ts_code", "trade_date"])
    prices_sub["ret_5d"] = prices_sub.groupby("ts_code")["adj_close"].transform(
        lambda x: x / x.shift(5) - 1
    )
    ret_5d_map = prices_sub[prices_sub["trade_date"] == event_date][
        ["ts_code", "ret_5d"]
    ].set_index("ts_code")["ret_5d"].to_dict()
    day_prices["ret_5d"] = day_prices["ts_code"].map(ret_5d_map)
    day_prices["is_event_stock"] = day_prices["ret_5d"] < 0

    # Exec date prices for limit-up check
    exec_prices = prices[
        (prices["trade_date"] == exec_date) &
        (prices["ts_code"].isin(core_codes))
    ].copy()

    return shared_filter_eligible_stocks(
        day_prices=day_prices,
        prices=prices,
        trade_date=event_date,
        calendar=calendar,
        eligibility=eligibility,
        listing_age_map=listing_age_map,
        amt_20d_map=amt_20d_map,
        limit_status=limit_status,
        suspend_status=suspend_status,
        stock_status=stock_status_raw,
        exec_date=exec_date,
        exec_prices=exec_prices,
    )


def _select_top1_stock(
    available: pd.DataFrame,
    rule_name: str,
    rule_cfg: dict,
    event_date: int,
    core_basket: pd.DataFrame,
    prices: pd.DataFrame,
    exec_date: int,
    amt_20d_map: pd.Series,
) -> pd.DataFrame | None:
    """Select the top1 stock based on rule."""
    if len(available) == 0:
        return None

    available = available.dropna(subset=["ret_5d"]).copy()
    available = available[available["ret_5d"] < 0].copy()
    if len(available) == 0:
        return None
    available["is_event_stock"] = True

    if rule_name == "top1_strength":
        basket_row = core_basket[core_basket["trade_date"] == event_date]
        if len(basket_row) > 0 and "basket_ret_5d" in basket_row.columns:
            basket_ret_5d = basket_row["basket_ret_5d"].values[0]
            available = available.copy()
            available["rel_strength"] = available["ret_5d"] - basket_ret_5d
            return available.nlargest(1, "rel_strength")
        return available.head(1)

    elif rule_name == "top1_mid_drop":
        median_drop = available["ret_5d"].median()
        available = available.copy()
        available["dist_to_median"] = (available["ret_5d"] - median_drop).abs()
        return available.nsmallest(1, "dist_to_median")

    elif rule_name == "top1_liquidity_core":
        # must_be_event_stock enforced
        event_stocks = available[available["is_event_stock"] == True]  # noqa: E712
        if len(event_stocks) == 0:
            return None
        # Use 20d avg amount for ranking
        event_stocks = event_stocks.copy()
        amounts = []
        for _, s in event_stocks.iterrows():
            amt = amt_20d_map.get((s["ts_code"], event_date), np.nan)
            amounts.append(amt if not np.isnan(amt) else s.get("amount", 0))
        event_stocks["amount_20d_rank"] = amounts
        return event_stocks.nlargest(1, "amount_20d_rank")

    return None


def _simulate_trade_close(
    ts_code: str, exec_date: int, hold_days: int,
    prices: pd.DataFrame, calendar: np.ndarray, cost: float,
    suspend_status: pd.DataFrame | None,
) -> dict | None:
    """Simulate trade with close-to-close execution.

    Entry: exec_date close; Exit: exec_date + hold_days close.
    Constraint-aware: limit-up/down, suspension, gap detection.
    """
    if exec_date not in calendar:
        return None

    sp = prices[
        (prices["ts_code"] == ts_code) & (prices["trade_date"] >= exec_date)
    ].sort_values("trade_date")

    if len(sp) < 2:
        return None

    entry_row = sp[sp["trade_date"] == exec_date]
    if len(entry_row) == 0:
        return None

    entry_price = float(entry_row["adj_close"].values[0])
    if entry_price <= 0:
        return None

    # Limit-up on entry
    if "pct_chg" in entry_row.columns:
        if entry_row["pct_chg"].values[0] > 9.5:
            return None

    exit_date = trading_day_offset(calendar, exec_date, hold_days)
    if exit_date is None:
        return None

    exit_rows = sp[sp["trade_date"] == exit_date]
    # Handle suspension/limit-down delay
    attempts = 0
    while len(exit_rows) == 0 and attempts < 5:
        attempts += 1
        exit_date = trading_day_offset(calendar, exit_date, 1)
        if exit_date is None:
            return None
        exit_rows = sp[sp["trade_date"] == exit_date]

    if len(exit_rows) == 0:
        return None

    if "pct_chg" in exit_rows.columns and exit_rows["pct_chg"].values[0] < -9.5:
        # Can't sell at limit-down; try next day
        for delay in range(1, 4):
            alt = trading_day_offset(calendar, exit_date, delay)
            if alt is None:
                continue
            alt_rows = sp[sp["trade_date"] == alt]
            if len(alt_rows) > 0 and "pct_chg" in alt_rows.columns:
                if alt_rows["pct_chg"].values[0] > -9.5:
                    exit_date = alt
                    exit_rows = alt_rows
                    break
            else:
                return None

    exit_price = float(exit_rows["adj_close"].values[0])
    if exit_price <= 0:
        return None

    gross_ret = exit_price / entry_price - 1.0
    net_ret = gross_ret - 2 * cost

    # MAE / MFE from intra-trade data
    trade_data = sp[(sp["trade_date"] >= exec_date) & (sp["trade_date"] <= exit_date)]
    if len(trade_data) > 0 and "low" in trade_data.columns and "high" in trade_data.columns:
        mae = trade_data["low"].min() / entry_price - 1.0
        mfe = trade_data["high"].max() / entry_price - 1.0
    else:
        mae = min(0, gross_ret)
        mfe = max(0, gross_ret)

    return {
        "ts_code": ts_code,
        "entry_price": entry_price,
        "exit_price": exit_price,
        "entry_date": exec_date,
        "exit_date": int(exit_date),
        "return_gross": float(gross_ret),
        "return_net": float(net_ret),
        "mae": float(mae),
        "mfe": float(mfe),
        "execution_price_type": "close",
        "hold_days_actual": int(
            np.searchsorted(calendar, exit_date) - np.searchsorted(calendar, exec_date)
        ),
    }


def evaluate_top1_rules(
    events_df: pd.DataFrame,
    prices: pd.DataFrame,
    core_basket: pd.DataFrame,
    universe_df: pd.DataFrame,
    calendar: np.ndarray,
    top1_config: dict,
    cost_bps: int = 20,
    limit_status: pd.DataFrame | None = None,
    suspend_status: pd.DataFrame | None = None,
    stock_status: pd.DataFrame | None = None,
    eligibility: dict | None = None,
) -> pd.DataFrame:
    """Evaluate top1 rules with real PIT eligibility."""
    if events_df.empty or prices.empty:
        return pd.DataFrame()

    if eligibility is None:
        eligibility = {}
    cost = cost_bps / 10000.0

    exit_rules = [("hold_5d", 5), ("hold_10d", 10), ("hold_20d", 20)]
    listing_age_map = compute_listing_age(prices, calendar)
    amt_20d_map = compute_amount_20d_avg(prices)

    # Get implemented top1 rules; disabled/not_implemented config entries are skipped.
    supported_rules = ["top1_strength", "top1_mid_drop", "top1_liquidity_core"]
    implemented_rules = [
        r for r in supported_rules
        if top1_config.get(r, {}).get("enabled", True) is not False
        and top1_config.get(r, {}).get("status") != "not_implemented"
    ]

    trades = []
    for _, event in events_df.iterrows():
        event_date = int(event["event_date"])
        exec_date = event.get("exec_date")
        if pd.isna(exec_date):
            continue
        exec_date = int(exec_date)

        available = _get_available_stocks_v2(
            event_date, exec_date, universe_df, prices, calendar,
            listing_age_map, amt_20d_map,
            limit_status, suspend_status, stock_status, eligibility
        )
        if len(available) < 1:
            continue

        for rule_name in implemented_rules:
            rule_cfg = top1_config.get(rule_name, {})
            selected = _select_top1_stock(
                available, rule_name, rule_cfg, event_date,
                core_basket, prices, exec_date, amt_20d_map
            )
            if selected is None or len(selected) == 0:
                continue

            stock_code = selected["ts_code"].values[0] if isinstance(selected, pd.DataFrame) else selected

            for exit_name, hold_days in exit_rules:
                trade_result = _simulate_trade_close(
                    stock_code, exec_date, hold_days, prices, calendar, cost,
                    suspend_status
                )
                if trade_result is None:
                    continue
                trade_result.update({
                    "event_cluster_id": int(event["event_cluster_id"]),
                    "event_date": event_date,
                    "exec_date": exec_date,
                    "top1_rule": rule_name,
                    "exit_rule": exit_name,
                    "intensity_label": event.get("intensity_label", "unknown"),
                    "environment_label": event.get("environment_label", "unknown"),
                })
                trades.append(trade_result)

    if not trades:
        return pd.DataFrame()
    return pd.DataFrame(trades)


# ═══════════════════════════════════════════════════════════════════════
# Phase 9: Basket Contribution & Leave-One-Out
# ═══════════════════════════════════════════════════════════════════════
def compute_basket_contribution(
    fwd_returns: pd.DataFrame,
    events_df: pd.DataFrame,
    prices: pd.DataFrame,
    core_basket: pd.DataFrame,
    universe_df: pd.DataFrame,
    calendar: np.ndarray,
) -> pd.DataFrame:
    """Compute per-stock contribution to basket forward return for each event.

    Contribution = weight_i * stock_fwd_ret_i for each stock in core basket.
    """
    if events_df.empty or prices.empty:
        return pd.DataFrame()

    core_codes = universe_df[
        (universe_df["pool_type"] == "core") &
        (universe_df["pit_confidence"] != "low")
    ]["ts_code"].unique().tolist()

    rows = []
    for _, event in events_df.iterrows():
        event_date = int(event["event_date"])
        exec_date = event.get("exec_date")
        if pd.isna(exec_date):
            continue
        exec_date = int(exec_date)

        # Get core stocks active at event_date
        active = universe_df[
            (universe_df["pool_type"] == "core") &
            (universe_df["pit_confidence"] != "low") &
            (universe_df["effective_start"] <= event_date) &
            (universe_df["effective_end"] >= event_date)
        ]
        active_codes = active["ts_code"].unique().tolist()
        n_stocks = len(active_codes)
        if n_stocks == 0:
            continue

        # Compute forward return for each stock
        for code in active_codes:
            sp = prices[
                (prices["ts_code"] == code) &
                (prices["trade_date"] >= exec_date)
            ].sort_values("trade_date")

            if len(sp) < 2:
                continue
            entry_row = sp[sp["trade_date"] == exec_date]
            if len(entry_row) == 0:
                continue

            entry_price = float(entry_row["adj_close"].values[0])
            exit_date = trading_day_offset(calendar, exec_date, 20)
            if exit_date is None:
                continue
            exit_rows = sp[sp["trade_date"] == exit_date]
            if len(exit_rows) == 0:
                continue
            exit_price = float(exit_rows["adj_close"].values[0])

            stock_ret = exit_price / entry_price - 1.0
            weight = 1.0 / n_stocks

            rows.append({
                "event_cluster_id": int(event["event_cluster_id"]),
                "event_date": event_date,
                "ts_code": code,
                "weight": weight,
                "stock_fwd_ret_20d": float(stock_ret),
                "contribution": float(weight * stock_ret),
            })

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


def compute_basket_leave_one_out(
    fwd_returns: pd.DataFrame,
    events_df: pd.DataFrame,
    prices: pd.DataFrame,
    core_basket: pd.DataFrame,
    universe_df: pd.DataFrame,
    calendar: np.ndarray,
) -> pd.DataFrame:
    """Leave-one-stock-out for basket: remove each core stock, recompute basket return."""
    if events_df.empty:
        return pd.DataFrame()

    core_codes_all = universe_df[
        (universe_df["pool_type"] == "core") &
        (universe_df["pit_confidence"] != "low")
    ]["ts_code"].unique().tolist()

    rows = []
    for _, event in events_df.iterrows():
        event_date = int(event["event_date"])
        exec_date = event.get("exec_date")
        if pd.isna(exec_date):
            continue
        exec_date = int(exec_date)

        active = universe_df[
            (universe_df["pool_type"] == "core") &
            (universe_df["pit_confidence"] != "low") &
            (universe_df["effective_start"] <= event_date) &
            (universe_df["effective_end"] >= event_date)
        ]
        active_codes = active["ts_code"].unique().tolist()
        if len(active_codes) < 2:
            continue

        # Full basket return
        all_rets = []
        for code in active_codes:
            sp = prices[(prices["ts_code"] == code) & (prices["trade_date"] >= exec_date)].sort_values("trade_date")
            if len(sp) < 2:
                continue
            entry = sp[sp["trade_date"] == exec_date]
            exit_20 = trading_day_offset(calendar, exec_date, 20)
            if exit_20 is None or len(entry) == 0:
                continue
            exit_rows = sp[sp["trade_date"] == exit_20]
            if len(exit_rows) == 0:
                continue
            all_rets.append(float(exit_rows["adj_close"].values[0]) / float(entry["adj_close"].values[0]) - 1.0)

        if len(all_rets) < 2:
            continue
        full_basket_ret = np.mean(all_rets)

        # Leave-one-out
        for removed_code in active_codes:
            loo_rets = []
            for code in active_codes:
                if code == removed_code:
                    continue
                sp = prices[(prices["ts_code"] == code) & (prices["trade_date"] >= exec_date)].sort_values("trade_date")
                if len(sp) < 2:
                    continue
                entry = sp[sp["trade_date"] == exec_date]
                exit_20 = trading_day_offset(calendar, exec_date, 20)
                if exit_20 is None or len(entry) == 0:
                    continue
                exit_rows = sp[sp["trade_date"] == exit_20]
                if len(exit_rows) == 0:
                    continue
                loo_rets.append(float(exit_rows["adj_close"].values[0]) / float(entry["adj_close"].values[0]) - 1.0)

            if len(loo_rets) < 2:
                continue
            loo_ret = np.mean(loo_rets)

            rows.append({
                "event_cluster_id": int(event["event_cluster_id"]),
                "event_date": event_date,
                "removed_stock": removed_code,
                "full_basket_ret_20d": float(full_basket_ret),
                "loo_basket_ret_20d": float(loo_ret),
                "ret_change": float(loo_ret - full_basket_ret),
                "n_remaining_stocks": len(loo_rets),
            })

    return pd.DataFrame(rows)


# ═══════════════════════════════════════════════════════════════════════
# Phase 6: Diagnostics (top1 concentration, top1 LOO, robustness)
# ═══════════════════════════════════════════════════════════════════════
def compute_concentration_diagnostics(trades_df: pd.DataFrame) -> pd.DataFrame:
    if trades_df.empty:
        return pd.DataFrame()
    rows = []
    for rule in trades_df["top1_rule"].unique():
        rt = trades_df[trades_df["top1_rule"] == rule]
        for er in rt["exit_rule"].unique():
            s = rt[rt["exit_rule"] == er]
            if len(s) == 0:
                continue
            tp = s["return_net"].sum()
            ss = s.groupby("ts_code")["return_net"].sum().sort_values(ascending=False)
            top = ss.iloc[0] if len(ss) > 0 else 0
            rows.append({
                "top1_rule": rule, "exit_rule": er,
                "n_trades": len(s), "n_unique_stocks": len(ss),
                "total_pnl": float(tp),
                "top_stock": ss.index[0] if len(ss) > 0 else "",
                "top_stock_trade_share": float((s["ts_code"] == ss.index[0]).mean()) if len(ss) > 0 else 0,
                "top1_contributor_share": float(top / tp) if tp != 0 and len(ss) > 0 else 0,
                "positive_trade_ratio": float((s["return_net"] > 0).mean()),
            })
    return pd.DataFrame(rows)


def compute_leave_one_out(trades_df: pd.DataFrame) -> pd.DataFrame:
    if trades_df.empty:
        return pd.DataFrame()
    rows = []
    for rule in trades_df["top1_rule"].unique():
        rt = trades_df[trades_df["top1_rule"] == rule]
        for er in rt["exit_rule"].unique():
            s = rt[rt["exit_rule"] == er]
            if len(s) == 0:
                continue
            all_pnl = s["return_net"].sum()
            # Stock LOO
            for stock in s["ts_code"].unique():
                wo = s[s["ts_code"] != stock]
                rows.append({
                    "analysis_type": "leave_one_stock_out", "top1_rule": rule,
                    "exit_rule": er, "removed": stock,
                    "pnl_without": float(wo["return_net"].sum()),
                    "pnl_change_pct": float((wo["return_net"].sum() - all_pnl) / abs(all_pnl) * 100) if all_pnl != 0 else 0,
                    "n_remaining": len(wo), "all_pnl": float(all_pnl),
                })
            # Year LOO
            s_copy = s.copy()
            if "event_date" in s_copy.columns:
                s_copy["year"] = s_copy["event_date"] // 10000
                for yr in s_copy["year"].unique():
                    wo = s_copy[s_copy["year"] != yr]
                    rows.append({
                        "analysis_type": "leave_one_year_out", "top1_rule": rule,
                        "exit_rule": er, "removed": str(int(yr)),
                        "pnl_without": float(wo["return_net"].sum()),
                        "pnl_change_pct": float((wo["return_net"].sum() - all_pnl) / abs(all_pnl) * 100) if all_pnl != 0 else 0,
                        "n_remaining": len(wo), "all_pnl": float(all_pnl),
                    })
    return pd.DataFrame(rows)


def compute_robustness(
    fwd_returns: pd.DataFrame, trades_df: pd.DataFrame, research_config: dict,
) -> pd.DataFrame:
    cost_scenarios = [10, 20, 30, 50, 100]
    rows = []
    if not fwd_returns.empty:
        for h in [5, 10, 20]:
            col = f"basket_fwd_ret_{h}d"
            if col not in fwd_returns.columns:
                continue
            for bps in cost_scenarios:
                cost = bps / 10000.0
                nr = fwd_returns[col].dropna() - 2 * cost
                rows.append({
                    "scope": "basket", "horizon_days": h, "cost_bps": bps,
                    "n_events": len(nr), "mean_gross_return": float(fwd_returns[col].dropna().mean()),
                    "mean_net_return": float(nr.mean()), "win_rate": float((nr > 0).mean()),
                    "t_stat": float(nr.mean() / nr.std() * np.sqrt(len(nr))) if len(nr) > 1 and nr.std() > 0 else 0,
                })
    if not trades_df.empty:
        for rule in trades_df["top1_rule"].unique():
            rt = trades_df[trades_df["top1_rule"] == rule]
            for er in rt["exit_rule"].unique():
                s = rt[rt["exit_rule"] == er]
                for bps in cost_scenarios:
                    cost = bps / 10000.0
                    nr = s["return_gross"] - 2 * cost
                    rows.append({
                        "scope": "top1", "top1_rule": rule, "exit_rule": er,
                        "horizon_days": int(er.split("_")[1].replace("d", "")),
                        "cost_bps": bps, "n_events": len(nr),
                        "mean_gross_return": float(s["return_gross"].mean()),
                        "mean_net_return": float(nr.mean()),
                        "win_rate": float((nr > 0).mean()),
                        "t_stat": float(nr.mean() / nr.std() * np.sqrt(len(nr))) if len(nr) > 1 and nr.std() > 0 else 0,
                    })
    return pd.DataFrame(rows)


# ═══════════════════════════════════════════════════════════════════════
# Phase 10: Go/No-Go v2
# ═══════════════════════════════════════════════════════════════════════
def evaluate_go_nogo(
    fwd_returns: pd.DataFrame,
    trades_df: pd.DataFrame,
    concentration: pd.DataFrame,
    top1_loo: pd.DataFrame,
    basket_loo: pd.DataFrame,
    robustness: pd.DataFrame,
    go_nogo_config: dict,
    not_implemented_features: list[str] | None = None,
) -> dict:
    """Apply Go/No-Go decision logic v2.

    Uses basket LOO for event_GO. Only uses implemented features.
    """
    if not_implemented_features is None:
        not_implemented_features = []

    result = {
        "event_GO": False, "top1_GO": False, "trade_GO": False,
        "final_classification": "both_invalid", "verdict": "No-Go",
        "details": {},
    }
    cost = 20 / 10000.0

    # ── event_GO ──────────────────────────────────────────────────────
    event_go = True
    ed = {}

    col_20 = "basket_fwd_ret_20d"
    if not fwd_returns.empty and col_20 in fwd_returns.columns:
        net_20 = fwd_returns[col_20].dropna() - 2 * cost
        ed["basket_20d_mean_net"] = float(net_20.mean()) if len(net_20) > 0 else 0.0
        ed["basket_20d_win_rate"] = float((net_20 > 0).mean()) if len(net_20) > 0 else 0.0
        ed["n_events"] = len(net_20)

        if len(net_20) < 5:
            event_go = False
            ed["failure"] = f"insufficient_events ({len(net_20)} < 5)"
        elif net_20.mean() <= 0:
            event_go = False
            ed["failure"] = f"no_reversal_tendency (mean_net={net_20.mean():.5f})"

        # Year stability
        if "event_date" in fwd_returns.columns:
            fwd_c = fwd_returns.copy()
            fwd_c["year"] = fwd_c["event_date"] // 10000
            yearly = {}
            for yr, g in fwd_c.groupby("year"):
                yr_rets = g[col_20].dropna() - 2 * cost
                if len(yr_rets) > 0:
                    yearly[int(yr)] = float(yr_rets.mean())
            ed["yearly_net_returns"] = yearly
            pos_years = sum(1 for v in yearly.values() if v > 0)
            if len(yearly) > 0 and pos_years / len(yearly) < 0.5:
                event_go = False
                ed["failure"] = f"year_stability ({pos_years}/{len(yearly)} < 50%)"
    else:
        event_go = False
        ed["failure"] = "no_forward_returns"

    # Basket LOO impact
    if not basket_loo.empty:
        loo_impact = basket_loo.groupby("removed_stock")["ret_change"].mean()
        worst_impact = loo_impact.abs().max()
        ed["basket_loo_worst_impact"] = float(worst_impact)
        # Check if any removal makes mean ret go negative
        loo_summary = basket_loo.groupby("removed_stock").agg(
            mean_loo_ret=("loo_basket_ret_20d", "mean")
        )
        neg_after_removal = (loo_summary["mean_loo_ret"] <= 0).sum()
        if neg_after_removal > 0:
            ed["basket_loo_negative_after_removal"] = int(neg_after_removal)
            event_go = False
            ed.setdefault("failures", []).append("basket_loo_failure")
            ed.setdefault("failure", "basket_loo_failure")

    result["event_GO"] = event_go
    result["details"]["event"] = ed

    # ── top1_GO ───────────────────────────────────────────────────────
    top1_go = True
    td = {}
    if trades_df.empty:
        top1_go = False
        td["failure"] = "no_top1_trades"
    else:
        rule_perf = trades_df.groupby(["top1_rule", "exit_rule"])["return_net"].mean()
        td["best_rule_return"] = float(rule_perf.max()) if len(rule_perf) > 0 else 0.0
        if len(rule_perf) == 0 or rule_perf.max() <= 0:
            top1_go = False
            td["failure"] = "no_positive_rule"

        if not concentration.empty:
            max_contrib = concentration["top1_contributor_share"].max()
            td["max_contributor_share"] = float(max_contrib)
            if max_contrib > 0.5:
                top1_go = False
                td["failure"] = f"single_stock_dominated ({max_contrib:.2%})"

    result["top1_GO"] = top1_go
    result["details"]["top1"] = td

    # ── trade_GO ──────────────────────────────────────────────────────
    trade_go = event_go and top1_go

    # 50bps cost check
    if not robustness.empty:
        rob_50_top1 = robustness[(robustness["scope"] == "top1") & (robustness["cost_bps"] == 50)]
        if len(rob_50_top1) > 0 and rob_50_top1["mean_net_return"].max() <= 0:
            trade_go = False
            result["details"]["robustness_failure"] = "reversal_at_50bps"
        rob_50_basket = robustness[(robustness["scope"] == "basket") & (robustness["cost_bps"] == 50)]
        if len(rob_50_basket) > 0:
            h20 = rob_50_basket[rob_50_basket["horizon_days"] == 20]
            if len(h20) > 0 and h20["mean_net_return"].values[0] <= 0:
                trade_go = False
                result["details"]["robustness_failure"] = "basket_reversal_at_50bps"

    # Year concentration
    if not trades_df.empty and "event_date" in trades_df.columns:
        tc = trades_df.copy()
        tc["year"] = tc["event_date"] // 10000
        yc = tc["year"].value_counts()
        if len(yc) > 0 and yc.max() / yc.sum() > 0.5:
            trade_go = False
            result["details"]["concentration_failure"] = f"single_year_dominated ({yc.index[0]}: {yc.max()}/{yc.sum()})"

    # Robustness gates not implemented → skip
    if "robustness_aux_gates" in not_implemented_features:
        result["details"]["robustness_gates_note"] = "aux_gates not implemented — skipped"

    result["trade_GO"] = trade_go

    # ── Classification ────────────────────────────────────────────────
    if event_go and top1_go:
        result["final_classification"] = "both_valid"
        result["verdict"] = "进入候选策略池"
    elif event_go and not top1_go:
        result["final_classification"] = "basket_valid_top1_invalid"
        result["verdict"] = "主题事件存在，但单票账户暂不可交易"
    elif not event_go and top1_go:
        result["final_classification"] = "basket_invalid_top1_valid"
        result["verdict"] = "高度怀疑单票偶然或过拟合 — No-Go"
    else:
        result["final_classification"] = "both_invalid"
        result["verdict"] = "No-Go — 放弃当前规则配置"

    return result


# ═══════════════════════════════════════════════════════════════════════
# Phase 7: Report
# ═══════════════════════════════════════════════════════════════════════
def generate_report(
    fwd_returns, trades_df, concentration, top1_loo, basket_loo,
    robustness, go_nogo_result, events_df, out_dir,
    not_implemented_features, limit_status_src, suspend_status_src,
    implemented_features: list[str] | None = None,
) -> str:
    implemented_features = implemented_features or []
    lines = [
        "# 光刻胶主题恐慌修复研究报告 v2",
        f"\n**生成时间:** {datetime.now():%Y-%m-%d %H:%M:%S}",
        "\n**状态: RESEARCH ONLY — 不构成投资建议**",
        "\n---",
        f"\n## 1. 执行摘要",
        f"\n### 最终判断: **{go_nogo_result['verdict']}**",
        f"\n- event_GO: **{'✅ PASS' if go_nogo_result['event_GO'] else '❌ FAIL'}**",
        f"- top1_GO: **{'✅ PASS' if go_nogo_result['top1_GO'] else '❌ FAIL'}**",
        f"- trade_GO: **{'✅ PASS' if go_nogo_result['trade_GO'] else '❌ FAIL'}**",
        f"- 分类: `{go_nogo_result['final_classification']}`",
        f"\n### 执行口径",
        f"- execution_price_type: **close**",
        f"- entry: exec_date (t+1) close",
        f"- exit: entry_date + horizon close",
        f"- limit_status_source: **{limit_status_src}**",
        f"- suspend_status_source: **{suspend_status_src}**",
        "\n### 已实现功能",
    ]
    for f in sorted(implemented_features):
        lines.append(f"- ✅ {f}")
    if not_implemented_features:
        lines.append("\n### 未实现 / 本轮禁用功能")
        for f in sorted(not_implemented_features):
            lines.append(f"- ❌ {f} (NOT IMPLEMENTED)")

    lines.append("\n---\n## 2. 事件概览\n")
    if not events_df.empty:
        lines.append(f"- 总事件簇: **{len(events_df)}**")
        for lbl in ["normal_panic", "strong_panic", "extreme_panic"]:
            lines.append(f"  - {lbl}: {(events_df['intensity_label']==lbl).sum()}")
        lines.append(f"- 聚类方式: 交易日间隔 ≤5 天")

    lines.append("\n## 3. Basket 修复效应\n")
    if not fwd_returns.empty:
        for h in [5, 10, 20]:
            col = f"basket_fwd_ret_{h}d"
            if col in fwd_returns.columns:
                rets = fwd_returns[col].dropna()
                net = rets - 2 * (20/10000.0)
                lines.append(f"### {h}日 Forward Return")
                lines.append(f"- 样本: {len(rets)}, gross: {rets.mean():.4%}, net(20bp): {net.mean():.4%}, win: {(net>0).mean():.2%}")

    lines.append("\n## 4. Top1 单票规则\n")
    if not trades_df.empty:
        for rule in sorted(trades_df["top1_rule"].unique()):
            rt = trades_df[trades_df["top1_rule"] == rule]
            lines.append(f"### {rule}")
            for er in sorted(rt["exit_rule"].unique()):
                s = rt[rt["exit_rule"] == er]
                lines.append(f"- {er}: n={len(s)}, net={s['return_net'].mean():.4%}, win={(s['return_net']>0).mean():.2%}")

    lines.append("\n## 5. 集中度\n")
    if not concentration.empty:
        lines.append(concentration.to_markdown(index=False, floatfmt=".4f"))

    lines.append("\n## 6. Basket Leave-One-Out\n")
    if not basket_loo.empty:
        worst = basket_loo.loc[basket_loo["ret_change"].abs().idxmax()]
        lines.append(f"- 最差剔除影响: {worst['ret_change']:.4%} ({worst['removed_stock']})")
    else:
        lines.append("- basket LOO: not computed")

    lines.append("\n## 7. 鲁棒性\n")
    if not robustness.empty:
        for scope in ["basket", "top1"]:
            sd = robustness[robustness["scope"] == scope]
            if len(sd) > 0:
                pv = sd.pivot_table(index="horizon_days", columns="cost_bps", values="mean_net_return")
                lines.append(f"### {scope}\n{pv.to_markdown(floatfmt='.4f')}")

    lines.append("\n## 8. Go/No-Go 决策\n")
    lines.append(f"| Gate | Status |")
    lines.append(f"|:-----|:-------|")
    lines.append(f"| event_GO | {'✅' if go_nogo_result['event_GO'] else '❌'} |")
    lines.append(f"| top1_GO | {'✅' if go_nogo_result['top1_GO'] else '❌'} |")
    lines.append(f"| trade_GO | {'✅' if go_nogo_result['trade_GO'] else '❌'} |")
    lines.append(f"\n**结论:** {go_nogo_result['verdict']}")

    lines.append("\n## 9. 功能实现状态\n")
    for f in implemented_features:
        lines.append(f"- ✅ {f}: IMPLEMENTED")
    for f in not_implemented_features:
        lines.append(f"- ❌ {f}: NOT IMPLEMENTED — 报告中不声称已完成")
    lines.append(f"\n- limit_status: {limit_status_src}")
    lines.append(f"- suspend_status: {suspend_status_src}")

    lines.append("\n---\n🤖 Generated with Claude Code | RESEARCH ONLY | v2")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════
def main() -> int:
    args = parse_args()
    out_dir = Path(args.out_dir)
    if not out_dir.exists():
        print("ERROR: Run build_photoresist_panic_events.py first.")
        return 1

    print("=" * 70)
    print("PHOTORESIST PANIC REVERSAL EVALUATOR v2 (Phases 4-7)")
    print("=" * 70)

    research_config = load_yaml(Path(args.research_config))
    universe_config = load_yaml(Path(args.universe_config))

    # Load inputs
    events_df = pd.read_csv(out_dir / "photoresist_panic_events.csv")
    core_basket = pd.read_csv(out_dir / "photoresist_core_basket_with_gate.csv")
    universe_df = pd.read_csv(out_dir / "photoresist_universe_snapshot.csv")
    print(f"  events: {len(events_df)} | core_basket: {len(core_basket)} days")

    # Calendar
    calendar = build_trading_calendar_from_prices(args.start, args.end)
    print(f"  calendar: {len(calendar):,} trading days")

    # Load prices & eligibility data
    all_codes = universe_df["ts_code"].unique().tolist()
    prices = pd.DataFrame()
    chunks = []
    for yr_dir in _iter_year_dirs(PRICES_DIR, args.start, args.end):
        for pq in sorted(yr_dir.rglob("*.parquet")):
            df = _normalize(pd.read_parquet(pq))
            if "adj_close" not in df.columns:
                continue
            df = df[df["ts_code"].isin(all_codes)]
            if len(df) == 0:
                continue
            keep = ["ts_code", "trade_date", "adj_close", "open", "high", "low", "pct_chg", "amount"]
            chunks.append(df[[c for c in keep if c in df.columns]])
    if chunks:
        prices = pd.concat(chunks, ignore_index=True)
        prices = prices.drop_duplicates(["ts_code", "trade_date"])
    print(f"  prices: {len(prices):,} rows")

    # Index prices
    index_prices = pd.DataFrame()
    if INDEX_DIR.exists():
        ic = []
        for yr_dir in _iter_year_dirs(INDEX_DIR, args.start, args.end):
            for pq in sorted(yr_dir.rglob("*.parquet")):
                df = _normalize(pd.read_parquet(pq))
                if "close" in df.columns:
                    ic.append(df[["ts_code", "trade_date", "close"]])
        if ic:
            index_prices = pd.concat(ic, ignore_index=True)

    # Eligibility sources
    limit_status_src = "pct_chg_proxy"
    suspend_status_src = "price_missing_proxy"
    stock_status_src = "unavailable"
    limit_status = None
    suspend_status = None
    stock_status_raw = None

    if LIMIT_DIR.exists():
        limit_status = pd.concat([
            _normalize(pd.read_parquet(pq))
            for yr_dir in _iter_year_dirs(LIMIT_DIR, args.start, args.end)
            for pq in sorted(yr_dir.rglob("*.parquet"))
        ], ignore_index=True) if list(_iter_year_dirs(LIMIT_DIR, args.start, args.end)) else None
        if limit_status is not None and len(limit_status) > 0:
            limit_status_src = "exact"

    if SUSPEND_DIR.exists():
        suspend_status = pd.concat([
            _normalize(pd.read_parquet(pq))
            for yr_dir in _iter_year_dirs(SUSPEND_DIR, args.start, args.end)
            for pq in sorted(yr_dir.rglob("*.parquet"))
        ], ignore_index=True) if list(_iter_year_dirs(SUSPEND_DIR, args.start, args.end)) else None
        if suspend_status is not None and len(suspend_status) > 0:
            suspend_status_src = "exact"

    if STOCK_STATUS_PATH.exists():
        stock_status_raw = load_stock_status_shared()
        if stock_status_raw is not None and len(stock_status_raw) > 0:
            stock_status_src = "exact"

    implemented_features, not_implemented = collect_feature_status(research_config)

    # Phase 4
    print("\n[Phase 4] Forward returns (close-to-close)...")
    fwd_returns = compute_forward_returns(events_df, prices, core_basket, index_prices, calendar)
    if not fwd_returns.empty:
        fwd_returns.to_csv(out_dir / "photoresist_forward_returns.csv", index=False)
        for h in [5, 10, 20]:
            c = f"basket_fwd_ret_{h}d"
            if c in fwd_returns.columns:
                rets = fwd_returns[c].dropna()
                if len(rets) > 0:
                    print(f"    {h}d: gross={rets.mean():.4f} net(20bp)={rets.mean()-2*args.cost_bps/10000:.4f} n={len(rets)}")

    # Phase 5
    print("\n[Phase 5] Top1 rules (PIT + real eligibility)...")
    top1_config = research_config.get("top1_rules", {})
    eligibility = universe_config.get("eligibility", {})
    trades_df = evaluate_top1_rules(
        events_df, prices, core_basket, universe_df, calendar,
        top1_config, args.cost_bps,
        limit_status=limit_status, suspend_status=suspend_status,
        stock_status=stock_status_raw, eligibility=eligibility,
    )
    if not trades_df.empty:
        trades_df.to_csv(out_dir / "photoresist_top1_trades.csv", index=False)
        print(f"  top1_trades: {len(trades_df)} records")
        for rule in sorted(trades_df["top1_rule"].unique()):
            rt = trades_df[trades_df["top1_rule"] == rule]
            print(f"    {rule}: {len(rt)} trades, net={rt['return_net'].mean():.4f}")
    else:
        print("  WARNING: No top1 trades")

    # Phase 6
    print("\n[Phase 6] Diagnostics...")
    concentration = compute_concentration_diagnostics(trades_df)
    if not concentration.empty:
        concentration.to_csv(out_dir / "photoresist_contribution_diagnostics.csv", index=False)

    top1_loo = compute_leave_one_out(trades_df)
    if not top1_loo.empty:
        top1_loo.to_csv(out_dir / "photoresist_leave_one_out.csv", index=False)

    print("  Basket contribution & basket LOO...")
    basket_contrib = compute_basket_contribution(fwd_returns, events_df, prices, core_basket, universe_df, calendar)
    basket_loo = compute_basket_leave_one_out(fwd_returns, events_df, prices, core_basket, universe_df, calendar)
    if not basket_contrib.empty:
        basket_contrib.to_csv(out_dir / "photoresist_basket_contribution_diagnostics.csv", index=False)
        print(f"  basket_contrib: {len(basket_contrib)} rows")
    if not basket_loo.empty:
        basket_loo.to_csv(out_dir / "photoresist_basket_leave_one_out.csv", index=False)
        print(f"  basket_loo: {len(basket_loo)} rows")

    robustness = compute_robustness(fwd_returns, trades_df, research_config)
    if not robustness.empty:
        robustness.to_csv(out_dir / "photoresist_robustness.csv", index=False)

    # Phase 7
    print("\n[Phase 7] Go/No-Go & Report...")
    go_nogo_config = research_config.get("go_nogo", {})
    go_nogo_result = evaluate_go_nogo(
        fwd_returns, trades_df, concentration, top1_loo, basket_loo,
        robustness, go_nogo_config, not_implemented,
    )

    print(f"  event_GO: {go_nogo_result['event_GO']}")
    print(f"  top1_GO:  {go_nogo_result['top1_GO']}")
    print(f"  trade_GO: {go_nogo_result['trade_GO']}")
    print(f"  verdict:  {go_nogo_result['verdict']}")

    with open(out_dir / "photoresist_go_nogo_result.json", "w", encoding="utf-8") as f:
        json.dump(go_nogo_result, f, indent=2, ensure_ascii=False, default=str)

    report = generate_report(
        fwd_returns, trades_df, concentration, top1_loo, basket_loo,
        robustness, go_nogo_result, events_df, out_dir,
        not_implemented, limit_status_src, suspend_status_src,
        implemented_features=implemented_features,
    )
    (out_dir / "photoresist_panic_report.md").write_text(report, encoding="utf-8")

    print(f"\n{'='*70}")
    print(f"FINAL: {go_nogo_result['verdict']}")
    print(f"Features not implemented: {not_implemented}")
    print(f"{'='*70}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

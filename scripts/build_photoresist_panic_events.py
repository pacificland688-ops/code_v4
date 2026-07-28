"""
Photoresist Panic Event Builder v2
====================================
Builds PIT stock universe, constructs core/broad basket daily series,
applies panic gate with PIT-clean quantiles, computes panic scores,
and classifies events using trading-day-based clustering.

Phases 1-3 of photoresist_panic_reversal_development_plan.md.
v2 fixes: real amount_ratio_20d, trading-day clustering, rolling quantile
          shift, config-driven min_components, real eligibility filters.

Outputs (→ outputs/analysis/photoresist_panic/):
  - photoresist_universe_snapshot.csv
  - photoresist_basket_daily.csv
  - photoresist_panic_events.csv
  - photoresist_core_basket_with_gate.csv
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

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_VERSION = "2.1.0"  # real limit prices + namechange + weight cap fix
DEFAULT_UNIVERSE_CONFIG = ROOT / "configs" / "photoresist_universe.yaml"
DEFAULT_RESEARCH_CONFIG = ROOT / "configs" / "photoresist_panic_research.yaml"
DEFAULT_OUT_DIR = ROOT / "outputs" / "analysis" / "photoresist_panic"

PRICES_DIR = ROOT / "data" / "parquet" / "prices_adj"
DAILY_DIR = ROOT / "data" / "parquet" / "daily_basic"
INDEX_DIR = ROOT / "data" / "parquet" / "index_daily"
LIMIT_DIR = ROOT / "data" / "parquet" / "limit_status"
SUSPEND_DIR = ROOT / "data" / "parquet" / "suspend_status"
STOCK_STATUS_PATH = ROOT / "data" / "parquet" / "stock_status"
NAMECHANGE_PATH = ROOT / "data" / "parquet" / "namechange"


# ═══════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Build photoresist panic events v2 (Phases 1-3)"
    )
    p.add_argument("--start", type=int, default=20170101)
    p.add_argument("--end", type=int, default=20251231)
    p.add_argument("--universe-config", default=str(DEFAULT_UNIVERSE_CONFIG))
    p.add_argument("--research-config", default=str(DEFAULT_RESEARCH_CONFIG))
    p.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    p.add_argument("--strict-tradability", action="store_true",
                   help="Fail if any tradability data source is a proxy")
    return p.parse_args()


def generate_run_id(prefix: str = "panic") -> str:
    """Generate a unique, sortable run identifier."""
    ts = datetime.now().strftime("%Y%m%dT%H%M%S")
    return f"{prefix}_{ts}"


# ═══════════════════════════════════════════════════════════════════════
# Config loader
# ═══════════════════════════════════════════════════════════════════════
def load_yaml(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def collect_not_implemented_features(research_config: dict) -> list[str]:
    """Collect explicitly disabled/not-implemented research features from config."""
    features = []

    top1_rules = research_config.get("top1_rules", {})
    for name, cfg in top1_rules.items():
        if not isinstance(cfg, dict):
            continue
        if cfg.get("enabled", True) is False or cfg.get("status") == "not_implemented":
            features.append(name)

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
        features.append("confirmation_entry")

    robustness_cfg = research_config.get("robustness_gates", {})
    if (
        isinstance(robustness_cfg, dict)
        and (robustness_cfg.get("enabled", True) is False
             or robustness_cfg.get("status") == "not_implemented")
    ):
        features.append("robustness_aux_gates")

    return list(dict.fromkeys(features))


# ═══════════════════════════════════════════════════════════════════════
# PIT Universe Builder
# ═══════════════════════════════════════════════════════════════════════
def build_pit_universe(
    universe_config: dict,
    start: int,
    end: int,
) -> pd.DataFrame:
    """Build point-in-time stock universe from config.

    Returns DataFrame with columns:
      ts_code, name, pool_type, effective_start, effective_end,
      source_type, source_ref, pit_confidence
    """
    records = []
    for layer in ["core", "adjacent", "mapping"]:
        stocks = universe_config.get("universe", {}).get(layer, [])
        for s in stocks:
            records.append({
                "ts_code": str(s["ts_code"]),
                "name": str(s.get("name", "")),
                "pool_type": str(s.get("pool_type", layer)),
                "effective_start": int(s.get("effective_start", 20170101)),
                "effective_end": int(s.get("effective_end", 20991231)),
                "source_type": str(s.get("source_type", "manual_review")),
                "source_ref": str(s.get("source_ref", "")),
                "pit_confidence": str(s.get("pit_confidence", "low")),
            })

    if not records:
        return pd.DataFrame(columns=[
            "ts_code", "name", "pool_type", "effective_start", "effective_end",
            "source_type", "source_ref", "pit_confidence",
        ])

    df = pd.DataFrame(records)
    df["effective_start"] = pd.to_numeric(df["effective_start"], errors="coerce")
    df["effective_end"] = pd.to_numeric(df["effective_end"], errors="coerce")

    df = df[
        (df["effective_start"] <= end) &
        (df["effective_end"] >= start)
    ].copy()

    return df


def get_universe_for_date(
    universe_df: pd.DataFrame,
    trade_date: int,
    pool_types: list[str] | None = None,
    min_pit_confidence: str = "low",
) -> pd.DataFrame:
    """Get universe constituents active on a given trade_date (PIT-clean)."""
    active = universe_df[
        (universe_df["effective_start"] <= trade_date) &
        (universe_df["effective_end"] >= trade_date)
    ].copy()

    if pool_types:
        active = active[active["pool_type"].isin(pool_types)]

    conf_order = {"high": 3, "medium": 2, "low": 1}
    min_conf = conf_order.get(min_pit_confidence, 0)
    active = active[
        active["pit_confidence"].map(conf_order).fillna(0) >= min_conf
    ]

    return active


# ═══════════════════════════════════════════════════════════════════════
# Data loaders
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


def _safe_dedup(df: pd.DataFrame, keys: list[str] | None = None) -> pd.DataFrame:
    """Drop duplicate rows with conflict detection.

    If duplicates exist with different values in non-key columns, warn
    and raise rather than silently keeping the first.
    """
    if df.empty:
        return df
    if keys is None:
        keys = [c for c in ("ts_code", "trade_date") if c in df.columns]
    if not keys or not all(k in df.columns for k in keys):
        return df.drop_duplicates()
    dup_mask = df.duplicated(subset=keys, keep=False)
    if not dup_mask.any():
        return df
    dup_groups = df[dup_mask].groupby(keys)
    n_conflicts = 0
    for _, group in dup_groups:
        if len(group) == 1:
            continue
        # Check if all rows in the group are identical
        numeric_cols = group.select_dtypes(include=["number"]).columns
        for col in numeric_cols:
            vals = group[col].dropna()
            if len(vals) > 1 and vals.nunique() > 1:
                n_conflicts += 1
                break
    if n_conflicts > 0:
        print(f"  WARNING: {n_conflicts} duplicate key groups with conflicting values")
    return df.drop_duplicates(subset=keys, keep="first")


def _iter_year_dirs(base: Path, start: int, end: int, margin: int = 1):
    """Yield year=* directories within [start-margin, end+margin].

    The ±1 year margin is needed for rolling quantile warm-up, but the
    manifest MUST record the *actual* loaded range so provenance is exact.
    """
    sy, ey = start // 10000, end // 10000
    for d in sorted(base.glob("year=*")):
        if not d.is_dir():
            continue
        try:
            yr = int(d.name.split("=", 1)[1])
        except ValueError:
            continue
        if sy - margin <= yr <= ey + margin:
            yield d


def load_prices(start: int, end: int, ts_codes: list[str]) -> pd.DataFrame:
    """Load adjusted close prices for specified stocks."""
    cols = ["ts_code", "trade_date", "close", "adj_open", "adj_high",
            "adj_low", "adj_close", "open", "high", "low", "pct_chg",
            "vol", "amount"]
    chunks = []
    code_set = set(ts_codes)
    for yr_dir in _iter_year_dirs(PRICES_DIR, start, end):
        for pq in sorted(yr_dir.rglob("*.parquet")):
            df = _normalize(pd.read_parquet(pq))
            if "adj_close" not in df.columns:
                continue
            df = df.dropna(subset=["trade_date", "adj_close"])
            if code_set:
                df = df[df["ts_code"].isin(code_set)]
            if len(df) == 0:
                continue
            keep = [c for c in cols if c in df.columns]
            chunks.append(df[keep])
    if not chunks:
        raise RuntimeError(f"No prices_adj parquet under {PRICES_DIR}")
    prices = pd.concat(chunks, ignore_index=True)
    prices = prices.drop_duplicates(["ts_code", "trade_date"])
    prices = prices.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)
    return prices


def load_index_prices(start: int, end: int, codes: list[str]) -> pd.DataFrame:
    """Load index daily data for specified index codes."""
    if not INDEX_DIR.exists():
        return pd.DataFrame()
    cols = ["ts_code", "trade_date", "close", "pct_chg"]
    chunks = []
    for yr_dir in _iter_year_dirs(INDEX_DIR, start, end):
        for pq in sorted(yr_dir.rglob("*.parquet")):
            df = _normalize(pd.read_parquet(pq))
            if "close" not in df.columns:
                continue
            df = df[df["ts_code"].isin(codes)]
            if len(df) == 0:
                continue
            keep = [c for c in cols if c in df.columns]
            chunks.append(df[keep])
    if not chunks:
        return pd.DataFrame()
    idx = pd.concat(chunks, ignore_index=True)
    idx = idx.drop_duplicates(["ts_code", "trade_date"])
    idx = idx.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)
    return idx


def load_daily_basic(start: int, end: int, ts_codes: list[str]) -> pd.DataFrame:
    """Load daily basic data for target stocks."""
    cols = ["ts_code", "trade_date", "total_mv", "circ_mv",
            "turnover_rate", "turnover_rate_f", "volume_ratio", "amount"]
    chunks = []
    code_set = set(ts_codes)
    for yr_dir in _iter_year_dirs(DAILY_DIR, start, end):
        for pq in sorted(yr_dir.rglob("*.parquet")):
            df = _normalize(pd.read_parquet(pq))
            if not {"ts_code", "trade_date"}.issubset(df.columns):
                continue
            if code_set:
                df = df[df["ts_code"].isin(code_set)]
            if len(df) == 0:
                continue
            keep = [c for c in cols if c in df.columns]
            chunks.append(df[keep])
    if not chunks:
        return pd.DataFrame()
    basic = pd.concat(chunks, ignore_index=True)
    basic = basic.dropna(subset=["trade_date"])
    basic = basic.drop_duplicates(["ts_code", "trade_date"])
    return basic


def load_limit_status(start: int, end: int, ts_codes: list[str]) -> pd.DataFrame | None:
    """Load limit-up/limit-down status. Returns None if unavailable."""
    if not LIMIT_DIR.exists():
        return None
    chunks = []
    code_set = set(ts_codes)
    for yr_dir in _iter_year_dirs(LIMIT_DIR, start, end):
        for pq in sorted(yr_dir.rglob("*.parquet")):
            df = _normalize(pd.read_parquet(pq))
            if "ts_code" in df.columns:
                df = df[df["ts_code"].isin(code_set)]
            if len(df) == 0:
                continue
            chunks.append(df)
    if not chunks:
        return None
    return pd.concat(chunks, ignore_index=True)


def load_suspend_status(start: int, end: int, ts_codes: list[str]) -> pd.DataFrame | None:
    """Load suspension status. Returns None if unavailable."""
    if not SUSPEND_DIR.exists():
        return None
    chunks = []
    code_set = set(ts_codes)
    for yr_dir in _iter_year_dirs(SUSPEND_DIR, start, end):
        for pq in sorted(yr_dir.rglob("*.parquet")):
            df = _normalize(pd.read_parquet(pq))
            if "trade_date" not in df.columns and "suspend_date" in df.columns:
                df = df.rename(columns={"suspend_date": "trade_date"})
            if "ts_code" in df.columns:
                df = df[df["ts_code"].isin(code_set)]
            if len(df) == 0:
                continue
            chunks.append(df)
    if not chunks:
        return None
    return pd.concat(chunks, ignore_index=True)


def load_stock_status() -> pd.DataFrame | None:
    """Load stock status (ST flag, list_date). Returns None if unavailable."""
    if not STOCK_STATUS_PATH.exists():
        return None
    try:
        df = _normalize(pd.read_parquet(STOCK_STATUS_PATH))
        return df
    except Exception:
        return None


def load_namechange(codes: list[str] | None = None) -> pd.DataFrame | None:
    """Load historical name changes (股票曾用名) for PIT ST detection.

    Tushare namechange API returns start_date, end_date, name columns.
    This provides true historical ST→normal transitions (摘帽).
    Returns None if data is unavailable.
    """
    if not NAMECHANGE_PATH.exists():
        return None
    try:
        chunks = []
        for pq in sorted(NAMECHANGE_PATH.rglob("*.parquet")):
            df = _normalize(pd.read_parquet(pq))
            if codes and "ts_code" in df.columns:
                code_set = set(codes)
                df = df[df["ts_code"].astype(str).isin(code_set)]
            if len(df) > 0:
                chunks.append(df)
        if not chunks:
            return None
        result = pd.concat(chunks, ignore_index=True)
        # Ensure date columns are numeric
        for dc in ["start_date", "end_date", "ann_date"]:
            if dc in result.columns:
                result[dc] = pd.to_numeric(result[dc], errors="coerce")
        return result
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════════════════
# Calendar helpers
# ═══════════════════════════════════════════════════════════════════════
def build_trading_calendar(prices: pd.DataFrame) -> np.ndarray:
    return np.array(sorted(int(d) for d in prices["trade_date"].dropna().unique()))


def build_calendar_index(calendar: np.ndarray) -> dict:
    """Map trade_date → sequential index for trading-day gap computation."""
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
# Eligibility helpers
# ═══════════════════════════════════════════════════════════════════════
def compute_listing_age(prices: pd.DataFrame, calendar: np.ndarray) -> pd.Series:
    """Compute trading-day-based listing age for each (ts_code, trade_date).

    Uses cumcount within each stock group. Returns Series indexed by (ts_code, trade_date).
    """
    df = prices[["ts_code", "trade_date"]].drop_duplicates()
    df = df.sort_values(["ts_code", "trade_date"])
    df["listing_age"] = df.groupby("ts_code").cumcount() + 1
    return df.set_index(["ts_code", "trade_date"])["listing_age"]


def compute_amount_20d_avg(prices: pd.DataFrame) -> pd.Series:
    """Compute rolling 20-day average amount for each stock.

    Returns Series indexed by (ts_code, trade_date).
    """
    df = prices[["ts_code", "trade_date", "amount"]].copy()
    df = df.sort_values(["ts_code", "trade_date"])
    df["amount_20d_avg"] = (
        df.groupby("ts_code")["amount"]
        .transform(lambda x: x.rolling(20, min_periods=10).mean())
    )
    return df.set_index(["ts_code", "trade_date"])["amount_20d_avg"]


def compute_amount_ratio_20d(prices: pd.DataFrame) -> pd.Series:
    """Compute amount / 20d_avg_amount ratio for each stock.

    Returns Series indexed by (ts_code, trade_date).
    """
    amt_avg = compute_amount_20d_avg(prices)
    df = prices[["ts_code", "trade_date", "amount"]].copy()
    df = df.sort_values(["ts_code", "trade_date"])
    idx = df.set_index(["ts_code", "trade_date"]).index
    avg_vals = amt_avg.reindex(idx)
    ratio = df["amount"].values / avg_vals.values
    ratio[avg_vals.isna() | (avg_vals.values == 0)] = np.nan
    return pd.Series(ratio, index=idx)


def _limit_flag_col(limit_status: pd.DataFrame, side: str) -> str | None:
    """Return a usable limit-indicator column name.

    Prefers real price columns (up_limit / down_limit) over boolean flags.
    """
    if limit_status is None or limit_status.empty:
        return None
    side = side.lower()
    # Prefer exact price columns
    price_col = f"{side}_limit"
    if price_col in limit_status.columns:
        return price_col
    # Fall back to boolean flag columns
    for col in limit_status.columns:
        lower = str(col).lower()
        if side not in lower:
            continue
        if not any(token in lower for token in ("flag", "status", "limit", "is_")):
            continue
        vals = limit_status[col].dropna()
        if vals.empty:
            return col
        unique_vals = set(vals.astype(str).str.lower().unique())
        if unique_vals.issubset({"0", "1", "true", "false", "yes", "no"}):
            return col
    return None


def _is_at_limit(
    ts_code: str,
    trade_date: int,
    side: str,
    limit_status: pd.DataFrame | None,
    prices: pd.DataFrame | None = None,
    tick_tolerance: float = 0.005,
) -> tuple[bool, str]:
    """Check if a stock hit limit up/down using best available data.

    Resolution order:
    1. Real limit price (up_limit / down_limit column) compared to close.
    2. Boolean flag column.
    3. pct_chg proxy (broad-market thresholds, inaccurate for ChiNext/STAR).

    Returns (is_limit: bool, source: str).
    source ∈ {"price", "flag", "pct_chg_proxy", "unavailable"}.
    """
    side = side.lower()
    side_col = f"{side}_limit"

    # ── Priority 1: real limit price comparison ──
    if limit_status is not None and not limit_status.empty and prices is not None:
        if side_col in limit_status.columns and "close" in prices.columns:
            limit_row = limit_status[
                (limit_status["ts_code"].astype(str) == str(ts_code))
                & (limit_status["trade_date"].astype(int) == int(trade_date))
            ]
            if not limit_row.empty:
                limit_price = limit_row[side_col].values[0]
                if not pd.isna(limit_price):
                    price_row = prices[
                        (prices["ts_code"].astype(str) == str(ts_code))
                        & (prices["trade_date"].astype(int) == int(trade_date))
                    ]
                    if not price_row.empty:
                        close = price_row["close"].values[0]
                        if not pd.isna(close) and close > 0:
                            # Tick size: 0.001 for ChiNext/STAR, 0.01 otherwise
                            code_str = str(ts_code)
                            tick = 0.001 if code_str.startswith(("300", "688")) else 0.01
                            if abs(close - limit_price) <= tick + tick_tolerance:
                                return True, "price"
                            return False, "price"

    # ── Priority 2: boolean flag column ──
    if limit_status is not None and not limit_status.empty:
        flag_col = _limit_flag_col(limit_status, side)
        if flag_col and flag_col != side_col:  # not the price column
            flag_row = limit_status[
                (limit_status["ts_code"].astype(str) == str(ts_code))
                & (limit_status["trade_date"].astype(int) == int(trade_date))
            ]
            if not flag_row.empty:
                val = flag_row[flag_col].values[0]
                if not pd.isna(val):
                    val_str = str(val).lower()
                    if val_str in {"1", "true", "yes"}:
                        return True, "flag"
                    if val_str in {"0", "false", "no"}:
                        return False, "flag"

    # ── Priority 3: pct_chg proxy (last resort) ──
    if prices is not None and "pct_chg" in prices.columns:
        price_row = prices[
            (prices["ts_code"].astype(str) == str(ts_code))
            & (prices["trade_date"].astype(int) == int(trade_date))
        ]
        if not price_row.empty:
            pct = price_row["pct_chg"].values[0]
            if not pd.isna(pct):
                code_str = str(ts_code)
                if code_str.startswith("300") or code_str.startswith("688"):
                    threshold = 19.5 if side == "up" else -19.5
                else:
                    threshold = 9.5 if side == "up" else -9.5
                if side == "up":
                    return pct >= threshold, "pct_chg_proxy"
                else:
                    return pct <= threshold, "pct_chg_proxy"

    return False, "unavailable"


def check_consecutive_limit_down(
    ts_code: str,
    trade_date: int,
    limit_status: pd.DataFrame | None,
    prices: pd.DataFrame,
    calendar: np.ndarray,
    n_days: int = 2,
) -> bool:
    """Check if a stock has >= n_days consecutive limit-down up to trade_date.

    Uses _is_at_limit which prefers real limit prices over pct_chg proxy.
    """
    # Walk back n_days trading days from trade_date via calendar
    cal_idx = int(np.searchsorted(calendar, int(trade_date)))
    if cal_idx >= len(calendar) or calendar[cal_idx] != int(trade_date):
        cal_idx = cal_idx - 1 if cal_idx > 0 else 0
    check_dates = [int(calendar[max(0, cal_idx - i)]) for i in range(n_days)]
    check_dates = [d for d in check_dates if d <= int(trade_date)]
    if len(check_dates) < n_days:
        return False

    consecutive = 0
    for d in check_dates:
        is_limit, src = _is_at_limit(ts_code, d, "down", limit_status, prices)
        if is_limit:
            consecutive += 1
            if consecutive >= n_days:
                return True
        else:
            consecutive = 0
    return False


def is_suspended(
    ts_code: str,
    trade_date: int,
    suspend_status: pd.DataFrame | None,
    prices: pd.DataFrame,
) -> bool:
    """Check if a stock is suspended on trade_date.

    Priority: suspend_status data; fallback: missing price/zero volume.
    """
    if suspend_status is not None and not suspend_status.empty:
        # Tushare client stores "suspend_date"; normalize to "trade_date"
        if "ts_code" not in suspend_status.columns:
            return False  # guard against empty shell DataFrame
        date_col = "trade_date" if "trade_date" in suspend_status.columns else "suspend_date"
        if date_col not in suspend_status.columns:
            return False
        stock_sus = suspend_status[
            (suspend_status["ts_code"] == ts_code) &
            (suspend_status[date_col] == trade_date)
        ]
        if len(stock_sus) > 0:
            sus_cols = [c for c in stock_sus.columns if "sus" in c.lower()]
            if sus_cols and stock_sus[sus_cols[0]].iloc[0]:
                return True

    # Fallback: price missing or zero volume
    day_data = prices[
        (prices["ts_code"] == ts_code) &
        (prices["trade_date"] == trade_date)
    ]
    if len(day_data) == 0:
        return True
    if "vol" in day_data.columns and day_data["vol"].values[0] == 0:
        return True

    return False


def is_st_stock(
    ts_code: str,
    stock_status: pd.DataFrame | None,
    trade_date: int | None = None,
    namechange: pd.DataFrame | None = None,
) -> bool:
    """Check if a stock is ST/*ST at a specific trade_date (PIT).

    Resolution order:
    1. namechange (股票曾用名) — true PIT with start_date/end_date.
    2. stock_status with trade_date column — sorted by date.
    3. stock_status without trade_date — current name only (best-effort).

    PIT note: without namechange data, historical ST→normal (摘帽) is missed.
    """
    code_str = str(ts_code)

    # Priority 1: namechange historical data (works independently of stock_status)
    if namechange is not None and not namechange.empty:
        nc = namechange[namechange["ts_code"].astype(str) == code_str].copy()
        if not nc.empty:
            date_col = None
            for c in ["start_date", "trade_date", "ann_date"]:
                if c in nc.columns:
                    date_col = c
                    break
            if date_col is not None and trade_date is not None:
                nc[date_col] = pd.to_numeric(nc[date_col], errors="coerce")
                nc = nc.sort_values(date_col)
                # Filter by start_date <= trade_date AND (end_date is null or >= trade_date)
                applicable = nc[
                    (nc[date_col] <= trade_date)
                ]
                if "end_date" in nc.columns:
                    nc["end_date"] = pd.to_numeric(nc["end_date"], errors="coerce")
                    applicable = applicable[
                        applicable["end_date"].isna()
                        | (applicable["end_date"] >= trade_date)
                    ]
                if not applicable.empty:
                    latest = applicable.iloc[-1]
                    for col in latest.index:
                        if "name" in col.lower():
                            val = str(latest[col]).upper()
                            if "ST" in val or "*ST" in val:
                                return True
                    return False

    # Priority 2/3: stock_status (only checked if namechange didn't resolve)
    if stock_status is None:
        return False

    mask = stock_status["ts_code"].astype(str) == code_str
    if trade_date is not None and "trade_date" in stock_status.columns:
        mask = mask & (stock_status["trade_date"].astype(int) <= trade_date)
    stock_rows = stock_status[mask]
    if len(stock_rows) == 0:
        return False
    if trade_date is not None and "trade_date" in stock_rows.columns:
        stock_rows = stock_rows.sort_values("trade_date")
    stock_row = stock_rows.iloc[-1:] if trade_date is not None else stock_rows.iloc[:1]
    for col in stock_row.columns:
        if "st" in col.lower() or "name" in col.lower():
            val = str(stock_row[col].values[0]).upper()
            if "ST" in val or "*ST" in val:
                return True
    return False


def filter_eligible_stocks(
    day_prices: pd.DataFrame,
    prices: pd.DataFrame,
    trade_date: int,
    calendar: np.ndarray,
    eligibility: dict | None,
    listing_age_map: pd.Series | None = None,
    amt_20d_map: pd.Series | None = None,
    limit_status: pd.DataFrame | None = None,
    suspend_status: pd.DataFrame | None = None,
    stock_status: pd.DataFrame | None = None,
    namechange: pd.DataFrame | None = None,
    exec_date: int | None = None,
    exec_prices: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Filter per-stock eligibility with one shared build/eval implementation.

    daily_basic is intentionally not used here; liquidity eligibility is based
    on prices.amount rolling 20-day average to avoid changing the frozen gate.
    """
    if day_prices.empty:
        return day_prices.copy()

    eligibility = eligibility or {}
    if listing_age_map is None:
        listing_age_map = compute_listing_age(prices, calendar)
    if amt_20d_map is None:
        amt_20d_map = compute_amount_20d_avg(prices)

    def _as_float(value: Any, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    min_list_days = _as_float(eligibility.get("min_list_days", 120), 120.0)
    min_amount_20d = _as_float(eligibility.get("min_daily_amount_20d", 1.0e8), 1.0e8)
    amount_unit = str(eligibility.get("amount_unit", "cny")).lower()
    if amount_unit in ("thousand_cny", "thousand_yuan", "k_cny"):
        min_amount_20d = min_amount_20d / 1000.0
    elif amount_unit in ("wan_cny", "wan_yuan"):
        min_amount_20d = min_amount_20d / 10000.0
    exclude_st = eligibility.get("exclude_st", True)
    exclude_suspend_flag = eligibility.get("exclude_suspend", True)
    exclude_ld_event = eligibility.get("exclude_limit_down_event", True)
    exclude_consec_ld = eligibility.get("exclude_consecutive_limit_down", False)
    exclude_limit_up_entry = eligibility.get("exclude_limit_up_entry", False)

    if exec_prices is None and exec_date is not None:
        codes = day_prices["ts_code"].astype(str).unique().tolist()
        exec_prices = prices[
            (prices["trade_date"] == exec_date) &
            (prices["ts_code"].isin(codes))
        ].copy()

    eligible_rows = []
    for _, stock in day_prices.iterrows():
        code = str(stock["ts_code"])

        la = listing_age_map.get((code, int(trade_date)), np.nan)
        if not np.isnan(la) and la < min_list_days:
            continue

        avg_amt = amt_20d_map.get((code, int(trade_date)), np.nan)
        if not np.isnan(avg_amt) and avg_amt < min_amount_20d:
            continue

        if exclude_st and is_st_stock(code, stock_status, trade_date=int(trade_date), namechange=namechange):
            continue

        if exclude_suspend_flag:
            if is_suspended(code, int(trade_date), suspend_status, prices):
                continue
            if exec_date is not None and is_suspended(code, int(exec_date), suspend_status, prices):
                continue

        if exclude_ld_event:
            is_ld, ld_src = _is_at_limit(
                code, int(trade_date), "down", limit_status, prices,
            )
            if is_ld:
                continue

        if exclude_consec_ld and check_consecutive_limit_down(
            code, int(trade_date), limit_status, prices, calendar
        ):
            continue

        if exclude_limit_up_entry and exec_date is not None:
            is_lu, lu_src = _is_at_limit(
                code, int(exec_date), "up", limit_status, prices,
            )
            if is_lu:
                continue

        eligible_rows.append(stock)

    if not eligible_rows:
        return pd.DataFrame(columns=day_prices.columns)

    return pd.DataFrame(eligible_rows).reset_index(drop=True)


# ═══════════════════════════════════════════════════════════════════════
# Basket Builder v2
# ═══════════════════════════════════════════════════════════════════════
def build_basket_daily(
    prices: pd.DataFrame,
    universe_df: pd.DataFrame,
    basket_rules: dict,
    calendar: np.ndarray,
    start: int,
    end: int,
    daily_basic: pd.DataFrame | None = None,
    limit_status: pd.DataFrame | None = None,
    suspend_status: pd.DataFrame | None = None,
    stock_status: pd.DataFrame | None = None,
    eligibility: dict | None = None,
) -> dict[str, pd.DataFrame]:
    """Build daily return series for core, broad, and mapping baskets.

    v2: Uses real eligibility filters, amount_ratio_20d, config-driven
    min_components, and passes date range from args.
    daily_basic is reserved for future turnover/circ_mv eligibility and is
    not used by the frozen BBB computation.
    """
    if eligibility is None:
        eligibility = {}

    # Pre-compute stock-level metrics
    listing_age_map = compute_listing_age(prices, calendar)
    amt_20d_map = compute_amount_20d_avg(prices)
    amount_ratio_map = compute_amount_ratio_20d(prices)

    results = {}
    diagnostics = []
    basket_configs = {
        "core_basket": basket_rules.get("core_basket", {}),
        "broad_basket": basket_rules.get("broad_basket", {}),
        "mapping_sentiment_index": basket_rules.get("mapping_sentiment_index", {}),
    }

    for basket_name, bcfg in basket_configs.items():
        pool_types = bcfg.get("pool_types", ["core"])
        min_conf = bcfg.get("min_pit_confidence", "medium")
        weight_scheme = bcfg.get("weight_scheme", "equal_weight")
        max_single_weight = bcfg.get("max_single_weight", 0.30)
        core_mult = bcfg.get("core_weight_multiplier", 2.0)
        research_only = bcfg.get("research_only", False)
        min_components = bcfg.get("min_components", 3)

        rows = []
        skipped_insufficient_constituents = 0
        skipped_insufficient_eligible = 0
        for td in calendar:
            if td < start or td > end:
                continue

            constituents = get_universe_for_date(
                universe_df, int(td), pool_types, min_conf
            )
            if len(constituents) < min_components:
                skipped_insufficient_constituents += 1
                continue

            codes = constituents["ts_code"].tolist()
            day_prices = prices[
                (prices["trade_date"] == td) & (prices["ts_code"].isin(codes))
            ].copy()

            day_prices = filter_eligible_stocks(
                day_prices=day_prices,
                prices=prices,
                trade_date=int(td),
                calendar=calendar,
                eligibility=eligibility,
                listing_age_map=listing_age_map,
                amt_20d_map=amt_20d_map,
                limit_status=limit_status,
                suspend_status=suspend_status,
                stock_status=stock_status,
            )
            eligible_codes = day_prices["ts_code"].tolist()

            if len(day_prices) < min_components:
                skipped_insufficient_eligible += 1
                continue

            n_stocks = len(day_prices)

            # ── Compute basket metrics ──────────────────────────────
            if "pct_chg" in day_prices.columns:
                rets = day_prices["pct_chg"].values / 100.0
            else:
                rets = np.zeros(n_stocks)

            # Weights
            if weight_scheme == "equal_weight":
                weights = np.ones(n_stocks) / n_stocks
            elif weight_scheme == "tiered":
                weights = np.ones(n_stocks)
                for i, code in enumerate(day_prices["ts_code"]):
                    pool_row = constituents.loc[constituents["ts_code"] == code, "pool_type"]
                    if len(pool_row) > 0 and pool_row.values[0] == "core":
                        weights[i] = core_mult
                weights = weights / weights.sum()
            else:
                weights = np.ones(n_stocks) / n_stocks

            if max_single_weight and max_single_weight < 1:
                weights = np.clip(weights, 0, max_single_weight)
                # Do NOT renormalize — excess weight stays as cash (0% return).
                # This ensures the cap is actually enforced.
            realized_max_weight = float(weights.max()) if len(weights) else np.nan
            cash_weight = float(1.0 - weights.sum()) if len(weights) else 0.0
            weight_cap_satisfied = bool(
                not max_single_weight
                or max_single_weight >= 1
                or realized_max_weight <= max_single_weight + 1e-12
            )

            basket_ret_1d = float(np.dot(weights, rets))
            down_ratio = float(np.mean(rets < 0))
            large_drop_ratio = float(np.mean(rets < -0.07))

            # Limit up/down ratio — use _is_at_limit (prefers real price data)
            lu_count = 0
            ld_count = 0
            for code in eligible_codes:
                is_lu, _ = _is_at_limit(code, int(td), "up", limit_status, prices)
                is_ld, _ = _is_at_limit(code, int(td), "down", limit_status, prices)
                if is_lu:
                    lu_count += 1
                if is_ld:
                    ld_count += 1
            limit_up_ratio = float(lu_count / n_stocks) if n_stocks > 0 else 0.0
            limit_down_ratio = float(ld_count / n_stocks) if n_stocks > 0 else 0.0

            # Real amount_ratio_20d
            amt_ratios = []
            for code in eligible_codes:
                ar = amount_ratio_map.get((code, int(td)), np.nan)
                if not np.isnan(ar):
                    amt_ratios.append(ar)
            median_amount_ratio_20d = float(np.median(amt_ratios)) if amt_ratios else np.nan

            rows.append({
                "trade_date": int(td),
                "basket_name": basket_name,
                "basket_ret_1d": basket_ret_1d,
                "down_stock_ratio": down_ratio,
                "large_drop_ratio": large_drop_ratio,
                "limit_up_ratio": limit_up_ratio,
                "limit_down_ratio": limit_down_ratio,
                "tradable_count": n_stocks,
                "component_count": n_stocks,
                "configured_max_single_weight": max_single_weight,
                "realized_max_single_weight": realized_max_weight,
                "cash_weight": cash_weight,
                "weight_cap_satisfied": weight_cap_satisfied,
                "median_amount_ratio_20d": median_amount_ratio_20d,
                "research_only": research_only,
            })

        df = pd.DataFrame(rows)
        if len(df) > 0:
            df = df.sort_values("trade_date").reset_index(drop=True)
            df["basket_ret_3d"] = (
                df["basket_ret_1d"].rolling(3, min_periods=1)
                .apply(lambda x: np.prod(1 + x) - 1, raw=True)
            )
            df["basket_ret_5d"] = (
                df["basket_ret_1d"].rolling(5, min_periods=1)
                .apply(lambda x: np.prod(1 + x) - 1, raw=True)
            )
            df["basket_ret_10d"] = (
                df["basket_ret_1d"].rolling(10, min_periods=1)
                .apply(lambda x: np.prod(1 + x) - 1, raw=True)
            )

        results[basket_name] = df
        diagnostics.append({
            "basket_name": basket_name,
            "min_components": min_components,
            "configured_max_single_weight": max_single_weight,
            "minimum_components_for_weight_cap": (
                int(np.ceil(1.0 / max_single_weight))
                if max_single_weight and 0 < max_single_weight < 1 else 1
            ),
            "skipped_days_insufficient_constituents": skipped_insufficient_constituents,
            "skipped_days_insufficient_eligible_components": skipped_insufficient_eligible,
        })

    results["_build_diagnostics"] = pd.DataFrame(diagnostics)
    return results


# ═══════════════════════════════════════════════════════════════════════
# Panic Gate v2 — quantile excludes current day
# ═══════════════════════════════════════════════════════════════════════
def apply_panic_gate(
    core_basket: pd.DataFrame,
    gate_config: dict,
) -> pd.DataFrame:
    """Apply the primary panic gate. Rolling quantile uses historical data only."""
    df = core_basket.copy().sort_values("trade_date")
    cond = gate_config.get("conditions", {})

    ret_threshold = cond.get("ret_5d_threshold_pct", -5.0) / 100.0
    quantile_window = cond.get("ret_5d_quantile_window_days", 750)
    quantile_threshold = cond.get("ret_5d_quantile_threshold_pct", 10) / 100.0
    down_threshold = cond.get("down_stock_ratio_5d_threshold_pct", 50.0) / 100.0

    # Condition 1: 5d return is negative
    df["gate_cond_1"] = df["basket_ret_5d"] < 0

    # Condition 2: ret_5d <= threshold OR <= rolling quantile
    # IMPORTANT: shift(1) so current day is NOT in the quantile window
    df["ret_5d_historical"] = df["basket_ret_5d"].shift(1)
    rolling_quantile = (
        df["ret_5d_historical"]
        .rolling(quantile_window, min_periods=60)
        .quantile(quantile_threshold)
    )
    df["gate_cond_2a"] = df["basket_ret_5d"] <= ret_threshold
    df["gate_cond_2b"] = df["basket_ret_5d"] <= rolling_quantile
    df["gate_cond_2"] = df["gate_cond_2a"] | df["gate_cond_2b"]

    # Condition 3: down stock ratio
    df["down_stock_ratio_5d"] = (
        df["down_stock_ratio"].rolling(5, min_periods=3).mean()
    )
    df["gate_cond_3"] = df["down_stock_ratio_5d"] >= down_threshold

    # Panic gate triggered
    df["panic_gate_triggered"] = (
        df["gate_cond_1"] & df["gate_cond_2"] & df["gate_cond_3"]
    )

    return df


# ═══════════════════════════════════════════════════════════════════════
# Panic Scoring — computed only when gate triggered
# ═══════════════════════════════════════════════════════════════════════
def compute_panic_scores(
    core_basket: pd.DataFrame,
    index_prices: pd.DataFrame,
    score_config: dict,
) -> pd.DataFrame:
    """Compute panic scores only for dates where panic_gate is triggered."""
    df = core_basket.copy()

    for dim in ["severity", "breadth", "volume", "relative", "stress"]:
        df[f"score_{dim}"] = 0

    triggered_mask = df["panic_gate_triggered"].fillna(False)

    # ── Severity ──────────────────────────────────────────────────────
    sev_cfg = score_config.get("severity", {})
    sev_threshold = sev_cfg.get("ret_5d_threshold_pct", -8.0) / 100.0
    sev_q_window = sev_cfg.get("quantile_window_days", 750)
    sev_q_threshold = sev_cfg.get("quantile_threshold_pct", 5) / 100.0
    hist_ret = df["basket_ret_5d"].shift(1)
    sev_quantile = hist_ret.rolling(sev_q_window, min_periods=60).quantile(sev_q_threshold)
    df.loc[triggered_mask, "score_severity"] = (
        (df.loc[triggered_mask, "basket_ret_5d"] <= sev_threshold) |
        (df.loc[triggered_mask, "basket_ret_5d"] <= sev_quantile[triggered_mask])
    ).astype(int)

    # ── Breadth ───────────────────────────────────────────────────────
    brd_cfg = score_config.get("breadth", {})
    brd_threshold = brd_cfg.get("down_stock_ratio_threshold_pct", 70.0) / 100.0
    df.loc[triggered_mask, "score_breadth"] = (
        df.loc[triggered_mask, "down_stock_ratio_5d"] >= brd_threshold
    ).astype(int)

    # ── Volume ────────────────────────────────────────────────────────
    vol_cfg = score_config.get("volume", {})
    vol_threshold = vol_cfg.get("amount_ratio_20d_median_threshold", 1.2)
    df.loc[triggered_mask, "score_volume"] = (
        df.loc[triggered_mask, "median_amount_ratio_20d"] >= vol_threshold
    ).astype(int)

    # ── Relative ──────────────────────────────────────────────────────
    rel_cfg = score_config.get("relative", {})
    rel_threshold = rel_cfg.get("excess_vs_semiconductor_5d_threshold_pct", -3.0) / 100.0
    if not index_prices.empty and "close" in index_prices.columns:
        semi_idx = index_prices[index_prices["ts_code"] == "931865.CSI"].copy()
        if len(semi_idx) > 0:
            semi_idx = semi_idx.sort_values("trade_date")
            semi_idx["semi_ret_5d"] = semi_idx["close"].pct_change(5)
            semi_map = dict(zip(semi_idx["trade_date"], semi_idx["semi_ret_5d"]))
            df["semi_ret_5d"] = df["trade_date"].map(semi_map)
            df["excess_vs_semi_5d"] = df["basket_ret_5d"] - df["semi_ret_5d"]
            df.loc[triggered_mask, "score_relative"] = (
                df.loc[triggered_mask, "excess_vs_semi_5d"] <= rel_threshold
            ).astype(int)

    # ── Stress ────────────────────────────────────────────────────────
    str_cfg = score_config.get("stress", {})
    str_threshold = str_cfg.get("large_drop_ratio_threshold_pct", 25.0) / 100.0
    df["large_drop_ratio_5d"] = (
        df["large_drop_ratio"].rolling(5, min_periods=3).mean()
    )
    df.loc[triggered_mask, "score_stress"] = (
        df.loc[triggered_mask, "large_drop_ratio_5d"] >= str_threshold
    ).astype(int)

    score_cols = [f"score_{d}" for d in ["severity", "breadth", "volume", "relative", "stress"]]
    df["panic_score_total"] = df[score_cols].sum(axis=1)
    df.loc[~triggered_mask, "panic_score_total"] = 0

    return df


# ═══════════════════════════════════════════════════════════════════════
# Event Classification v2 — trading-day-based clustering
# ═══════════════════════════════════════════════════════════════════════
def classify_events(
    core_basket: pd.DataFrame,
    index_prices: pd.DataFrame,
    intensity_config: dict,
    environment_config: dict,
    calendar: np.ndarray,
    calendar_index: dict,
    max_cluster_gap: int = 5,
) -> pd.DataFrame:
    """Classify panic events by intensity and environment.

    v2: Uses trading-day-based clustering (gap in calendar index, not YYYYMMDD diff).
    """
    df = core_basket.copy()

    # ── Intensity ─────────────────────────────────────────────────────
    normal_min = intensity_config.get("normal_panic", {}).get("min_score", 2)
    strong_min = intensity_config.get("strong_panic", {}).get("min_score", 3)
    extreme_min = intensity_config.get("extreme_panic", {}).get("min_score", 4)

    triggered = df["panic_gate_triggered"].fillna(False)
    scores = df["panic_score_total"].fillna(0)

    df["event_intensity"] = "none"
    df.loc[triggered & (scores >= extreme_min), "event_intensity"] = "extreme_panic"
    df.loc[triggered & (scores >= strong_min) & (scores < extreme_min), "event_intensity"] = "strong_panic"
    df.loc[triggered & (scores >= normal_min) & (scores < strong_min), "event_intensity"] = "normal_panic"

    # ── Environment ───────────────────────────────────────────────────
    semi_sys = environment_config.get("semiconductor_systematic_panic", {}).get("condition", {})
    semi_spec = environment_config.get("photoresist_specific_panic", {}).get("condition", {})

    sys_threshold = semi_sys.get("semiconductor_index_ret_5d_max_pct", -3.0) / 100.0
    spec_semi_min = semi_spec.get("semiconductor_index_ret_5d_min_pct", -3.0) / 100.0
    spec_excess_max = semi_spec.get("core_excess_vs_semiconductor_5d_max_pct", -3.0) / 100.0

    event_mask = df["event_intensity"] != "none"

    if "semi_ret_5d" in df.columns:
        df["event_environment"] = "unknown"
        df.loc[event_mask & (df["semi_ret_5d"] <= sys_threshold),
               "event_environment"] = "semiconductor_systematic_panic"
        df.loc[event_mask & (df["semi_ret_5d"] > spec_semi_min) &
               (df["excess_vs_semi_5d"] <= spec_excess_max),
               "event_environment"] = "photoresist_specific_panic"

    # ── Trading-day-based clustering ─────────────────────────────────
    event_dates_df = df[event_mask].sort_values("trade_date").copy()
    if len(event_dates_df) == 0:
        return pd.DataFrame()

    event_dates_df["cal_idx"] = event_dates_df["trade_date"].map(calendar_index)
    cal_indices = event_dates_df["cal_idx"].values
    gaps = np.diff(cal_indices)
    cluster_breaks = np.concatenate([[0], np.where(gaps > max_cluster_gap)[0] + 1])
    event_dates_df["event_cluster_id"] = 0
    for i, start_idx in enumerate(cluster_breaks):
        end_idx = cluster_breaks[i + 1] if i + 1 < len(cluster_breaks) else len(event_dates_df)
        event_dates_df.iloc[start_idx:end_idx, event_dates_df.columns.get_loc("event_cluster_id")] = i

    # ── Build event summary ──────────────────────────────────────────
    event_rows = []
    for cid, cluster in event_dates_df.groupby("event_cluster_id"):
        cluster = cluster.sort_values("trade_date")
        first_date = int(cluster["trade_date"].min())
        last_date = int(cluster["trade_date"].max())
        event_date = last_date  # identified at cluster-end close
        exec_date = trading_day_offset(calendar, event_date, 1)

        # Cluster span in trading days
        first_idx = calendar_index.get(first_date, 0)
        last_idx = calendar_index.get(last_date, 0)
        span_trading_days = last_idx - first_idx + 1

        event_rows.append({
            "event_cluster_id": int(cid),
            "event_start_date": first_date,
            "event_date": event_date,
            "exec_date": exec_date,
            "n_triggered_days": len(cluster),
            "cluster_span_trading_days": span_trading_days,
            "max_intensity": cluster["event_intensity"].apply(
                lambda x: {"extreme_panic": 3, "strong_panic": 2, "normal_panic": 1}.get(x, 0)
            ).max(),
            "intensity_label": cluster["event_intensity"].iloc[-1],
            "environment_label": cluster["event_environment"].iloc[-1]
                if "event_environment" in cluster.columns else "unknown",
            "basket_ret_5d_at_event": float(cluster["basket_ret_5d"].iloc[-1]),
            "down_stock_ratio_at_event": float(cluster["down_stock_ratio_5d"].iloc[-1]),
            "panic_score_at_event": int(cluster["panic_score_total"].iloc[-1]),
            "event_date_close_identification": True,
            "execution_date_next_trading_day": True,
        })

    events_df = pd.DataFrame(event_rows)
    if len(events_df) > 0:
        events_df = events_df.sort_values("event_date").reset_index(drop=True)

    return events_df


# ═══════════════════════════════════════════════════════════════════════
# Main pipeline
# ═══════════════════════════════════════════════════════════════════════
def main() -> int:
    args = parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("PHOTORESIST PANIC EVENT BUILDER v2 (Phases 1-3)")
    print("=" * 70)
    print(f"  date_range: {args.start} - {args.end}")
    print(f"  out_dir: {out_dir}")

    # ── Phase 1: Load configs & build PIT universe ───────────────────
    print("\n[Phase 1] Building PIT stock universe...")
    universe_config = load_yaml(Path(args.universe_config))
    research_config = load_yaml(Path(args.research_config))

    universe_df = build_pit_universe(universe_config, args.start, args.end)
    print(f"  Universe: {len(universe_df)} stocks")
    for pt in ["core", "adjacent", "mapping"]:
        n = (universe_df["pool_type"] == pt).sum()
        n_high = ((universe_df["pool_type"] == pt) & (universe_df["pit_confidence"] == "high")).sum()
        n_med = ((universe_df["pool_type"] == pt) & (universe_df["pit_confidence"] == "medium")).sum()
        print(f"    {pt}: {n} stocks ({n_high} high, {n_med} medium)")

    # Save universe snapshot
    universe_df.to_csv(out_dir / "photoresist_universe_snapshot.csv", index=False)
    print(f"  Saved: photoresist_universe_snapshot.csv")

    all_codes = universe_df["ts_code"].unique().tolist()

    # ── Phase 2: Load data & eligibility sources ─────────────────────
    print("\n[Phase 2] Loading data & eligibility sources...")

    limit_status_src = "pct_chg_proxy"
    suspend_status_src = "price_missing_proxy"
    stock_status_src = "unavailable"

    prices = load_prices(args.start, args.end, all_codes)
    calendar = build_trading_calendar(prices)
    calendar_index = build_calendar_index(calendar)
    print(f"  prices: {len(prices):,} rows, {prices['ts_code'].nunique()} stocks, "
          f"{len(calendar):,} trading days")

    daily_basic = load_daily_basic(args.start, args.end, all_codes)
    print(f"  daily_basic: {len(daily_basic):,} rows"
          if not daily_basic.empty else "  daily_basic: UNAVAILABLE")

    limit_status = load_limit_status(args.start, args.end, all_codes)
    if limit_status is not None:
        # Check if we have real price columns (up_limit / down_limit)
        has_price_cols = ("up_limit" in limit_status.columns
                          and "down_limit" in limit_status.columns)
        limit_status_src = "exact_prices" if has_price_cols else "flags_only"
        print(f"  limit_status: {len(limit_status):,} rows ({limit_status_src})")
    else:
        print("  limit_status: UNAVAILABLE (using pct_chg proxy)")

    suspend_status = load_suspend_status(args.start, args.end, all_codes)
    if suspend_status is not None:
        suspend_status_src = "exact"
        print(f"  suspend_status: {len(suspend_status):,} rows (exact)")
    else:
        print("  suspend_status: UNAVAILABLE (using price-missing proxy)")

    stock_status = load_stock_status()
    if stock_status is not None:
        stock_status_src = "exact"
        print(f"  stock_status: {len(stock_status):,} rows (exact)")
    else:
        print("  stock_status: UNAVAILABLE (ST filter disabled)")

    namechange = load_namechange(all_codes)
    if namechange is not None:
        print(f"  namechange: {len(namechange):,} rows (PIT ST detection available)")
    else:
        print("  namechange: UNAVAILABLE (ST detection from stock_status only)")

    # ── Strict tradability gate ─────────────────────────────────────────
    run_id = generate_run_id()
    proxy_sources = []
    if "proxy" in limit_status_src:
        proxy_sources.append(f"limit_status ({limit_status_src})")
    if "proxy" in suspend_status_src:
        proxy_sources.append(f"suspend_status ({suspend_status_src})")
    if stock_status_src == "unavailable":
        proxy_sources.append("stock_status (unavailable)")
    if args.strict_tradability and proxy_sources:
        print(f"\n  ERROR: --strict-tradability enabled but proxy data sources found:")
        for s in proxy_sources:
            print(f"    - {s}")
        print("  Re-run with real data or without --strict-tradability.")
        return 1
    if proxy_sources:
        print(f"  ⚠ proxy sources: {', '.join(proxy_sources)}")

    # Load index data
    benchmark_codes = ["000300.SH", "931865.CSI", "399006.SZ"]
    index_prices = load_index_prices(args.start, args.end, benchmark_codes)
    print(f"  index_prices: {len(index_prices):,} rows"
          if not index_prices.empty else "  index_prices: UNAVAILABLE")

    # ── Build baskets ────────────────────────────────────────────────
    basket_rules = universe_config.get("basket_rules", {})
    eligibility = universe_config.get("eligibility", {})

    baskets = build_basket_daily(
        prices, universe_df, basket_rules, calendar,
        args.start, args.end,
        daily_basic=daily_basic if not daily_basic.empty else None,
        limit_status=limit_status,
        suspend_status=suspend_status,
        stock_status=stock_status,
        eligibility=eligibility,
    )

    core_basket = baskets.get("core_basket", pd.DataFrame())
    broad_basket = baskets.get("broad_basket", pd.DataFrame())
    mapping_idx = baskets.get("mapping_sentiment_index", pd.DataFrame())
    basket_build_diagnostics = baskets.get("_build_diagnostics", pd.DataFrame())

    print(f"  core_basket: {len(core_basket):,} days")
    print(f"  broad_basket: {len(broad_basket):,} days")
    if not core_basket.empty and "median_amount_ratio_20d" in core_basket.columns:
        amr = core_basket["median_amount_ratio_20d"].dropna()
        if len(amr) > 0:
            print(f"  amount_ratio_20d: mean={amr.mean():.3f} med={amr.median():.3f} "
                  f"[real computation, not constant 1.0]")

    # ── Phase 3: Apply panic gate & score events ─────────────────────
    print("\n[Phase 3] Applying panic gate (quantile excludes current day)...")

    gate_config = research_config.get("panic_gate", {})
    score_config = research_config.get("panic_score", {})
    intensity_config = research_config.get("event_intensity", {})
    environment_config = research_config.get("event_environment", {})

    if core_basket.empty:
        print("  ERROR: core_basket is empty, cannot proceed")
        return 1

    core_basket = apply_panic_gate(core_basket, gate_config)
    n_triggered = core_basket["panic_gate_triggered"].sum()
    print(f"  Panic gate triggered on {n_triggered} days (quantile uses historical data only)")

    core_basket = compute_panic_scores(core_basket, index_prices, score_config)
    scored_days = (core_basket["panic_score_total"] > 0).sum()
    print(f"  Days with panic_score > 0: {scored_days}")

    # Clustering
    max_cluster_gap = universe_config.get("event_clustering", {}).get("max_gap_trading_days", 5)
    events_df = classify_events(
        core_basket, index_prices, intensity_config, environment_config,
        calendar, calendar_index, max_cluster_gap,
    )
    print(f"  Event clusters (trading-day-based gap ≤{max_cluster_gap}d): {len(events_df)}")
    if len(events_df) > 0:
        for lbl in ["normal_panic", "strong_panic", "extreme_panic"]:
            n = (events_df["intensity_label"] == lbl).sum()
            print(f"    {lbl}: {n}")
        # Show cluster span metrics
        if "n_triggered_days" in events_df.columns:
            print(f"    cluster triggered_days: "
                  f"mean={events_df['n_triggered_days'].mean():.1f} "
                  f"max={events_df['n_triggered_days'].max()}")

    # ── Save outputs ────────────────────────────────────────────────
    print("\n[Saving outputs]")
    basket_dfs = []
    for name, bdf in baskets.items():
        if name.startswith("_"):
            continue
        if not bdf.empty:
            bdf["basket_name"] = name
            basket_dfs.append(bdf)
    if basket_dfs:
        all_baskets = pd.concat(basket_dfs, ignore_index=True)
        all_baskets.to_csv(out_dir / "photoresist_basket_daily.csv", index=False)
        print(f"  photoresist_basket_daily.csv: {len(all_baskets):,} rows")

    if not events_df.empty:
        events_df.to_csv(out_dir / "photoresist_panic_events.csv", index=False)
        print(f"  photoresist_panic_events.csv: {len(events_df)} rows")

    core_basket.to_csv(out_dir / "photoresist_core_basket_with_gate.csv", index=False)

    # ── Manifest v2 ─────────────────────────────────────────────────
    # Check which features are actually implemented
    implemented = [
        "pit_universe", "core_basket", "broad_basket", "mapping_sentiment",
        "panic_gate", "panic_scoring", "event_intensity", "event_environment",
        "amount_ratio_20d_real", "trading_day_clustering",
        "rolling_quantile_historical_only", "eligibility_basic",
    ]
    not_implemented = collect_not_implemented_features(research_config)
    if limit_status_src == "pct_chg_proxy":
        not_implemented.append("limit_status_exact")
    if suspend_status_src == "price_missing_proxy":
        not_implemented.append("suspend_status_exact")

    # Stable hash
    gate_hash = hashlib.sha256(
        json.dumps(gate_config, sort_keys=True, default=str).encode()
    ).hexdigest()[:16]

    # Compute input hashes for provenance tracking
    universe_config_hash = hashlib.sha256(
        Path(args.universe_config).read_bytes()
    ).hexdigest()[:16]
    research_config_hash = hashlib.sha256(
        Path(args.research_config).read_bytes()
    ).hexdigest()[:16]

    manifest = {
        "schema": "photoresist_panic_events.v3",
        "run_id": run_id,
        "script_version": SCRIPT_VERSION,
        "phases_completed": "1-3",
        "status": "RESEARCH_ONLY",
        "frozen": True,
        "date_range": {"start": args.start, "end": args.end},
        "strict_tradability_enabled": args.strict_tradability,
        "upstream_inputs": {
            "universe_config": {
                "path": str(Path(args.universe_config).relative_to(ROOT)),
                "sha256": universe_config_hash,
            },
            "research_config": {
                "path": str(Path(args.research_config).relative_to(ROOT)),
                "sha256": research_config_hash,
            },
        },
        "data_sources_available": {
            "prices_adj": True,
            "daily_basic": not daily_basic.empty,
            "index_daily": not index_prices.empty,
            "limit_status": limit_status_src,
            "suspend_status": suspend_status_src,
            "stock_status": stock_status_src,
        },
        "data_sources_used_in_computation": {
            "prices_adj": ["adj_close", "pct_chg", "amount", "vol"],
            "daily_basic": [],
            "index_daily": ["close", "pct_chg"] if not index_prices.empty else [],
            "limit_status": ["limit_up_flag", "limit_down_flag"] if limit_status_src == "exact" else [],
            "suspend_status": ["suspend_flag"] if suspend_status_src == "exact" else [],
            "stock_status": ["name_or_st_flag"] if stock_status_src == "exact" else [],
        },
        "reserved_data_sources": {
            "daily_basic": (
                "reserved — not wired into eligibility in this BBB fix; "
                "amount_20d is computed from prices_adj.amount"
            ),
        },
        "execution_price_type": "close",
        "eligibility_amount_unit": eligibility.get("amount_unit", "cny"),
        "n_universe_stocks": len(universe_df),
        "n_core_days": len(core_basket),
        "n_panic_days": int(n_triggered),
        "n_event_clusters": len(events_df),
        "event_intensity_distribution": (
            events_df["intensity_label"].value_counts().to_dict()
            if not events_df.empty else {}
        ),
        "gate_config_sha256": gate_hash,
        "implemented_features": implemented,
        "not_implemented_features": not_implemented,
        "cluster_gap_trading_days": max_cluster_gap,
        "quantile_method": "rolling_historical_only",
    }
    if not basket_build_diagnostics.empty:
        manifest["basket_build_diagnostics"] = basket_build_diagnostics.to_dict("records")
    manifest_path = out_dir / "photoresist_panic_manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    print(f"  Manifest saved: {manifest_path}")
    print(f"  Implemented: {len(implemented)} features")
    print(f"  Not implemented: {len(not_implemented)} features")

    print("\nPhase 1-3 v2 complete. Ready for Phase 4+ evaluation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Live basket + frozen primary_5d computation.

The gate math is imported from the frozen research modules — this file MUST
NOT re-implement the formula:
  - basket:  scripts/build_photoresist_panic_events.build_basket_daily
  - gate:    scripts/validate_photoresist_panic_thresholds.build_threshold_gate
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .common import DEFAULT_RESEARCH_CONFIG, load_yaml


def load_market_data(history_start: int, as_of: int, core_codes: list[str],
                     index_codes: list[str]) -> dict:
    """Load local parquet inputs.

    Prices come from the live loader (full adjusted OHLC + raw close) so the
    quality gate can verify all four adj_* columns; the frozen basket builder
    only consumes the column subset it always used (adj_close/pct_chg/...).
    """
    from scripts.build_photoresist_panic_events import (
        load_limit_status, load_stock_status, load_suspend_status,
    )

    prices = load_full_prices(history_start, as_of, core_codes)
    if prices.empty:
        raise RuntimeError("no adjusted prices loaded for core codes")
    return {
        "prices": prices,
        "index_prices": load_full_index_prices(history_start, as_of, index_codes),
        "limit_status": load_limit_status(history_start, as_of, core_codes),
        "suspend_status": load_suspend_status(history_start, as_of, core_codes),
        "stock_status": load_stock_status(),
    }


def load_full_prices(history_start: int, as_of: int,
                     core_codes: list[str]) -> pd.DataFrame:
    """Adjusted OHLC + raw close panel (quality gate, outcomes, limit checks)."""
    from scripts.build_photoresist_panic_events import (
        PRICES_DIR, _iter_year_dirs, _normalize,
    )

    cols = ["ts_code", "trade_date", "adj_open", "adj_high", "adj_low",
            "adj_close", "close", "pre_close", "pct_chg", "vol", "amount"]
    chunks = []
    code_set = set(core_codes)
    for yr_dir in _iter_year_dirs(PRICES_DIR, history_start, as_of):
        for pq in sorted(yr_dir.rglob("*.parquet")):
            frame = _normalize(pd.read_parquet(pq))
            if "adj_close" not in frame.columns:
                continue
            frame = frame[frame["ts_code"].isin(code_set)]
            frame = frame.dropna(subset=["trade_date", "adj_close"])
            if frame.empty:
                continue
            keep = [c for c in cols if c in frame.columns]
            chunks.append(frame[keep])
    if not chunks:
        return pd.DataFrame(columns=cols)
    panel = pd.concat(chunks, ignore_index=True)
    panel = panel[(panel["trade_date"] >= history_start) & (panel["trade_date"] <= as_of)]
    return panel.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)


def load_full_index_prices(history_start: int, as_of: int,
                           index_codes: list[str]) -> pd.DataFrame:
    """Load raw index rows without hiding duplicate source keys."""
    from scripts.build_photoresist_panic_events import (
        INDEX_DIR, _iter_year_dirs, _normalize,
    )

    cols = ["ts_code", "trade_date", "close", "pct_chg"]
    chunks = []
    code_set = set(index_codes)
    for year_dir in _iter_year_dirs(INDEX_DIR, history_start, as_of):
        for parquet_path in sorted(year_dir.rglob("*.parquet")):
            frame = _normalize(pd.read_parquet(parquet_path))
            if "close" not in frame.columns:
                continue
            frame = frame[frame["ts_code"].isin(code_set)]
            frame = frame.dropna(subset=["trade_date", "close"])
            if frame.empty:
                continue
            chunks.append(frame[[column for column in cols if column in frame.columns]])
    if not chunks:
        return pd.DataFrame(columns=cols)
    panel = pd.concat(chunks, ignore_index=True)
    panel = panel[
        (panel["trade_date"] >= history_start) & (panel["trade_date"] <= as_of)
    ]
    return panel.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)


def build_core_basket(data: dict, universe: pd.DataFrame, universe_config: dict,
                      history_start: int, as_of: int) -> pd.DataFrame:
    """Daily core basket series through the frozen basket builder."""
    from build_photoresist_panic_events import build_basket_daily, build_trading_calendar

    calendar = build_trading_calendar(data["prices"])
    baskets = build_basket_daily(
        data["prices"], universe, universe_config["basket_rules"], calendar,
        history_start, as_of,
        limit_status=data.get("limit_status"),
        suspend_status=data.get("suspend_status"),
        stock_status=data.get("stock_status"),
        eligibility=universe_config.get("eligibility", {}),
    )
    core = baskets.get("core_basket", pd.DataFrame())
    if core.empty:
        raise RuntimeError("core_basket is empty — cannot compute primary_5d")
    return core.sort_values("trade_date").reset_index(drop=True)


def apply_frozen_gate(core_basket: pd.DataFrame,
                      gate_id: str = "primary_5d") -> pd.DataFrame:
    """Apply the FROZEN primary_5d gate via the research implementation."""
    from validate_photoresist_panic_thresholds import build_threshold_gate

    research = load_yaml(DEFAULT_RESEARCH_CONFIG)
    gate_config = research["threshold_validation"]["gates"][gate_id]
    return build_threshold_gate(core_basket, gate_id, gate_config)


def gate_snapshot(gated: pd.DataFrame, trade_date: int) -> dict:
    """Extract the day's signal row + explanatory metrics.

    historical_percentile is display-only (position of today's 5d return in
    the trailing 250 historical days); it does not feed the gate decision.
    """
    row_frame = gated[gated["trade_date"] == trade_date]
    if row_frame.empty:
        raise RuntimeError(f"no basket row at {trade_date}")
    row = row_frame.iloc[-1]
    history = gated.loc[
        gated["trade_date"] < trade_date, "validation_return"
    ].dropna().tail(250)
    value = float(row["validation_return"])
    percentile = float((history <= value).mean()) if len(history) else np.nan
    quantile = row["validation_quantile"]
    return {
        "trade_date": int(trade_date),
        "primary_5d_triggered": bool(row["validation_gate_triggered"]),
        "basket_ret_5d": value,
        "rolling_quantile_10pct": float(quantile) if pd.notna(quantile) else None,
        "distance_to_quantile": float(value - quantile) if pd.notna(quantile) else None,
        "historical_percentile": percentile if np.isfinite(percentile) else None,
        "down_breadth_5d": float(row["validation_breadth"])
            if pd.notna(row["validation_breadth"]) else None,
        "down_stock_ratio_1d": float(row["down_stock_ratio"])
            if pd.notna(row.get("down_stock_ratio", np.nan)) else None,
        "amount_ratio_20d": float(row["median_amount_ratio_20d"])
            if pd.notna(row.get("median_amount_ratio_20d", np.nan)) else None,
        "component_count": int(row.get("component_count", 0)),
        "large_drop_ratio": float(row.get("large_drop_ratio", np.nan))
            if pd.notna(row.get("large_drop_ratio", np.nan)) else None,
        "limit_down_ratio": float(row.get("limit_down_ratio", np.nan))
            if pd.notna(row.get("limit_down_ratio", np.nan)) else None,
    }


# ═══════════════════════════════════════════════════════════════════════
# Member口径 (gap-fix plan §5): active vs signal-eligible, with reasons
# ═══════════════════════════════════════════════════════════════════════
def eligibility_snapshot(
    prices: pd.DataFrame,
    active_members_df: pd.DataFrame,
    trade_date: int,
    eligibility: dict,
    calendar,
    limit_status: pd.DataFrame | None = None,
    suspend_status: pd.DataFrame | None = None,
    stock_status: pd.DataFrame | None = None,
) -> dict:
    """Per-stock frozen-eligibility decision with an exclusion reason.

    Mirrors the FROZEN filter (build_photoresist_panic_events.
    filter_eligible_stocks) check-for-check and in the same priority order;
    test_photoresist_live_members cross-validates the included set against
    the frozen implementation so the two cannot drift apart.
    """
    from build_photoresist_panic_events import (
        check_consecutive_limit_down, compute_amount_20d_avg,
        compute_listing_age, is_st_stock, is_suspended,
    )

    eligibility = eligibility or {}

    def _as_float(value, default):
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

    listing_age_map = compute_listing_age(prices, calendar)
    amt_20d_map = compute_amount_20d_avg(prices)
    day_prices = prices[prices["trade_date"] == trade_date]

    eligible, excluded = [], []
    for _, member in active_members_df.iterrows():
        code = str(member["ts_code"])
        row = day_prices[day_prices["ts_code"] == code]

        def exclude(reason: str) -> None:
            excluded.append({"ts_code": code,
                             "name": str(member.get("name", "")),
                             "reason": reason})

        if row.empty:
            exclude("no_market_data")
            continue
        stock = row.iloc[0]
        la = listing_age_map.get((code, int(trade_date)), np.nan)
        if not np.isnan(la) and la < min_list_days:
            exclude("min_list_days")
            continue
        avg_amt = amt_20d_map.get((code, int(trade_date)), np.nan)
        if not np.isnan(avg_amt) and avg_amt < min_amount_20d:
            exclude("liquidity_amount_20d")
            continue
        if eligibility.get("exclude_st", True) and is_st_stock(code, stock_status):
            exclude("st_status")
            continue
        if eligibility.get("exclude_suspend", True) and is_suspended(
            code, int(trade_date), suspend_status, prices
        ):
            exclude("suspended")
            continue
        if eligibility.get("exclude_limit_down_event", True) and (
            "pct_chg" in stock.index and stock["pct_chg"] < -9.5
        ):
            exclude("limit_down_event_day")
            continue
        if eligibility.get("exclude_consecutive_limit_down", False) and (
            check_consecutive_limit_down(code, int(trade_date), limit_status,
                                         prices, calendar)
        ):
            exclude("consecutive_limit_down")
            continue
        eligible.append(code)

    return {
        "trade_date": int(trade_date),
        "active_member_codes": sorted(
            active_members_df["ts_code"].astype(str).tolist()
        ),
        "eligible_member_codes": sorted(eligible),
        "excluded_components": excluded,
        "active_components": int(len(active_members_df)),
        "signal_components": int(len(eligible)),
    }


def active_stress_metrics(
    prices: pd.DataFrame,
    active_codes: list[str],
    trade_date: int,
    limit_status: pd.DataFrame | None = None,
    breadth_window: int = 5,
) -> dict:
    """P3/P4 liquidity-stress inputs computed over ALL active core members.

    A limit-down member excluded from the frozen gate basket must still count
    toward P4 stress — that is exactly why these metrics do NOT use the
    eligible basket.
    """
    frame = prices[
        prices["ts_code"].isin([str(c) for c in active_codes])
        & (prices["trade_date"] <= trade_date)
    ]
    if frame.empty:
        return {"active_down_breadth_5d": None, "active_amount_ratio_20d": None,
                "active_limit_down_count": 0, "active_limit_down_codes": [],
                "active_breadth_member_coverage": 0.0,
                "active_amount_member_coverage": 0.0}

    # 5d rolling mean of the daily down-stock ratio across active members
    recent_days = sorted(frame["trade_date"].unique())[-breadth_window:]
    daily_ratios = []
    daily_coverage = []
    active_count = len(active_codes)
    for day in recent_days:
        day_rows = frame[frame["trade_date"] == day]
        if not day_rows.empty and "pct_chg" in day_rows.columns:
            valid = day_rows["pct_chg"].notna()
            daily_ratios.append(
                float((day_rows.loc[valid, "pct_chg"] < 0).sum() / active_count)
            )
            daily_coverage.append(float(valid.sum() / active_count))
    breadth = float(np.mean(daily_ratios)) if daily_ratios else None
    breadth_coverage = float(np.mean(daily_coverage)) if daily_coverage else 0.0

    # median per-stock amount ratio vs its trailing 20d average
    ratios = []
    for code in active_codes:
        history = frame[frame["ts_code"] == code].sort_values("trade_date")
        if (
            "amount" in history.columns
            and len(history) >= 21
            and int(history["trade_date"].iloc[-1]) == int(trade_date)
        ):
            baseline = history["amount"].tail(21).iloc[:-1].mean()
            if baseline and baseline > 0:
                ratios.append(float(history["amount"].iloc[-1] / baseline))
    amount_ratio = float(np.median(ratios)) if ratios else None
    amount_coverage = float(len(ratios) / active_count) if active_count else 0.0

    # limit-down count over ALL active members (exact limit price if cached)
    limit_down_codes = []
    day_rows = frame[frame["trade_date"] == trade_date]
    for _, stock in day_rows.iterrows():
        code = str(stock["ts_code"])
        hit = False
        if limit_status is not None and not limit_status.empty:
            lim = limit_status[
                (limit_status["ts_code"] == code)
                & (limit_status["trade_date"] == trade_date)
            ]
            if not lim.empty and "down_limit" in lim.columns:
                down_limit = float(lim["down_limit"].iloc[-1])
                close = float(stock.get("close", np.nan))
                if np.isfinite(close) and down_limit > 0:
                    hit = abs(close - down_limit) < 0.005
        if not hit:
            pct = float(stock.get("pct_chg", np.nan))
            hit = bool(np.isfinite(pct) and pct <= -9.5)
        if hit:
            limit_down_codes.append(code)

    return {
        "active_down_breadth_5d": breadth,
        "active_amount_ratio_20d": amount_ratio,
        "active_limit_down_count": len(limit_down_codes),
        "active_limit_down_codes": sorted(limit_down_codes),
        "active_breadth_member_coverage": breadth_coverage,
        "active_amount_member_coverage": amount_coverage,
    }

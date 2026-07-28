"""Forward outcome tracking v2 — tradability-aware, calendar-aligned.

Two-phase signal registration (plan §6.1):
  SIGNAL_REGISTERED   trigger day: active members recorded
  ENTRY_RESOLVED      next trading day close: suspension / limit-up / ST /
                      liquidity / data-completeness checks freeze the actual
                      entry_component_codes with per-stock exclusion reasons
  NO_TRADABLE_BASKET  fewer than 3 tradable members: no formal forward returns

Valuation (plan §6.2/§6.3):
  - all stocks are mapped onto ONE trading-day grid (the exchange calendar);
    "each stock's own Nth row" averaging is forbidden;
  - a suspended holding carries its last valid close; its high/low equal that
    carried close (no resumption-day misalignment);
  - the entry basket is FROZEN for the 20-day window: missing members are
    carried, never silently dropped; the denominator never changes; the
    actually-valued component count is reported per day.

Intraday note (plan §6.4): per-component highs peak at different times, so the
old target_hit_intraday is renamed component_high_upper_bound — an upper bound,
not an achievable basket fill. The conservative primary metric remains the
close-basis target hit.
"""
from __future__ import annotations

import hashlib
import json

import numpy as np
import pandas as pd

from .market_utils import compute_amount_rolling_avg, is_st_stock

SIGNAL_REGISTERED = "SIGNAL_REGISTERED"
ENTRY_RESOLVED = "ENTRY_RESOLVED"
NO_TRADABLE_BASKET = "NO_TRADABLE_BASKET"
PENDING_ENTRY = "PENDING_ENTRY"
OUTCOME_DATA_BLOCKED = "OUTCOME_DATA_BLOCKED"
INVALID_DATA_GAP = "INVALID_DATA_GAP"

OUTCOME_COLUMNS = [
    "signal_id", "live_signal_date", "entry_date", "entry_status",
    "n_entry_components", "status", "days_tracked", "min_valued_components",
    "min_valuation_coverage", "min_real_data_coverage",
    "unexplained_gap_count", "daily_valuation_coverage", "data_gap_reasons",
    "ret_5d_net", "ret_10d_net", "ret_20d_net", "ret_end_net",
    "target_hit_close", "component_high_upper_bound_hit", "days_to_target",
    "mae", "mfe",
    "first_stop_hit", "first_stop_level", "first_stop_day",
    "stop_before_target", "path_ambiguous",
]

ENTRY_ELIGIBILITY_COLUMNS = [
    "signal_id", "live_signal_date", "entry_date", "ts_code",
    "included", "reason",
]


# ═══════════════════════════════════════════════════════════════════════
# Phase 2: entry resolution (next trading day close)
# ═══════════════════════════════════════════════════════════════════════
def resolve_entry(
    prices: pd.DataFrame,
    calendar: np.ndarray,
    signal: dict,
    limit_status: pd.DataFrame | None = None,
    stock_status: pd.DataFrame | None = None,
    namechange: pd.DataFrame | None = None,
    min_components: int = 3,
    entry_liquidity: dict | None = None,
) -> dict:
    """Resolve the tradable entry basket on the day after live_signal_date.

    Returns {'entry_status', 'entry_date', 'entry_component_codes',
    'exclusions': [{ts_code, reason}]}.
    """
    live_signal_date = int(signal["live_signal_date"])
    active_codes = [str(c) for c in signal.get("active_member_codes", [])]
    idx = np.searchsorted(calendar, live_signal_date)
    if idx >= len(calendar) or calendar[idx] != live_signal_date:
        return {"entry_status": "SIGNAL_DATE_NOT_IN_CALENDAR",
                "entry_date": None, "entry_component_codes": [],
                "exclusions": []}
    if idx + 1 >= len(calendar):
        return {"entry_status": PENDING_ENTRY, "entry_date": None,
                "entry_component_codes": [], "exclusions": []}
    entry_date = int(calendar[idx + 1])
    data_max = int(prices["trade_date"].max()) if not prices.empty else 0
    if data_max < entry_date:
        return {"entry_status": PENDING_ENTRY, "entry_date": entry_date,
                "entry_component_codes": [], "exclusions": []}

    day_rows = prices[prices["trade_date"] == entry_date]
    liquidity_policy = _normalize_liquidity_policy(entry_liquidity)
    amount_average = (
        compute_amount_rolling_avg(
            prices,
            window=liquidity_policy["window"],
            min_periods=liquidity_policy["min_periods"],
        )
        if liquidity_policy else pd.Series(dtype=float)
    )
    included, exclusions = [], []
    liquidity_checks = []
    for code in active_codes:
        row = day_rows[day_rows["ts_code"] == code]
        if row.empty:
            exclusions.append({"ts_code": code, "reason": "no_entry_day_data"})
            continue
        stock = row.iloc[0]
        if "vol" in stock.index and float(stock.get("vol", 0) or 0) == 0:
            exclusions.append({"ts_code": code, "reason": "suspended_entry_day"})
            continue
        if is_st_stock(code, stock_status, trade_date=entry_date, namechange=namechange):
            exclusions.append({"ts_code": code, "reason": "st_status"})
            continue
        if _hit_limit_up(stock, code, entry_date, limit_status):
            exclusions.append({"ts_code": code, "reason": "limit_up_cannot_buy"})
            continue
        if "amount" in stock.index and (
            pd.isna(stock["amount"]) or float(stock["amount"]) <= 0
        ):
            exclusions.append({"ts_code": code, "reason": "amount_missing"})
            continue
        if liquidity_policy:
            average = amount_average.get((code, entry_date), np.nan)
            check = {
                "ts_code": code,
                "amount_20d_avg": float(average) if pd.notna(average) else None,
                "minimum_amount": liquidity_policy["minimum_amount_data_units"],
                "amount_unit": liquidity_policy["amount_unit"],
            }
            liquidity_checks.append(check)
            if pd.isna(average):
                exclusions.append({
                    **check, "reason": "liquidity_amount_20d_unavailable",
                })
                continue
            if float(average) < liquidity_policy["minimum_amount_data_units"]:
                exclusions.append({
                    **check, "reason": "liquidity_amount_20d",
                })
                continue
        if pd.isna(stock.get("adj_close")) or float(stock["adj_close"]) <= 0:
            exclusions.append({"ts_code": code, "reason": "bad_adj_close"})
            continue
        included.append(code)

    status = ENTRY_RESOLVED if len(included) >= min_components else NO_TRADABLE_BASKET
    return {
        "entry_status": status,
        "entry_date": entry_date,
        "entry_component_codes": sorted(included),
        "exclusions": exclusions,
        "input_digest": _entry_input_digest(
            prices, signal, entry_date, limit_status, stock_status,
            liquidity_policy,
        ),
        "data_version": f"prices_max_trade_date={data_max}",
        "liquidity_policy": liquidity_policy,
        "liquidity_checks": liquidity_checks,
    }


def _normalize_liquidity_policy(policy: dict | None) -> dict | None:
    if not policy or not policy.get("enabled", True):
        return None
    minimum = float(policy.get("min_daily_amount_20d", 0.0))
    unit = str(policy.get("amount_unit", "cny")).lower()
    if unit in ("thousand_cny", "thousand_yuan", "k_cny"):
        minimum /= 1000.0
    elif unit in ("wan_cny", "wan_yuan"):
        minimum /= 10000.0
    return {
        "source": str(policy.get("source", "frozen_universe_eligibility")),
        "window": int(policy.get("window", 20)),
        "min_periods": int(policy.get("min_periods", 10)),
        "min_daily_amount_20d": float(policy.get("min_daily_amount_20d", 0.0)),
        "minimum_amount_data_units": minimum,
        "amount_unit": unit,
    }


def _entry_input_digest(
    prices: pd.DataFrame,
    signal: dict,
    entry_date: int,
    limit_status: pd.DataFrame | None,
    stock_status: pd.DataFrame | None,
    liquidity_policy: dict | None,
) -> str:
    """Hash exactly the inputs that determine entry-basket membership."""
    codes = sorted(str(c) for c in signal.get("active_member_codes", []))
    digest = hashlib.sha256()
    digest.update(json.dumps(codes, ensure_ascii=False).encode("utf-8"))
    digest.update(
        json.dumps(liquidity_policy, sort_keys=True, ensure_ascii=False).encode("utf-8")
    )
    price_history = prices[
        (prices["trade_date"] <= entry_date)
        & (prices["ts_code"].astype(str).isin(codes))
    ].sort_values(["ts_code", "trade_date"]).groupby("ts_code").tail(
        int((liquidity_policy or {}).get("window", 1))
    )
    inputs = [
        ("prices", price_history),
        ("limit_status", limit_status[
            (limit_status["trade_date"] == entry_date)
            & (limit_status["ts_code"].astype(str).isin(codes))
        ] if limit_status is not None and not limit_status.empty else pd.DataFrame()),
        ("stock_status", stock_status[
            stock_status["ts_code"].astype(str).isin(codes)
        ] if stock_status is not None and not stock_status.empty else pd.DataFrame()),
    ]
    for name, frame in inputs:
        digest.update(name.encode("ascii"))
        if frame.empty:
            digest.update(b"[]")
            continue
        ordered = frame.reindex(sorted(frame.columns), axis=1).sort_values(
            [c for c in ("ts_code", "trade_date") if c in frame.columns]
        )
        digest.update(
            ordered.to_json(orient="records", date_format="iso").encode("utf-8")
        )
    return digest.hexdigest()


def _hit_limit_up(stock_row, code: str, trade_date: int,
                  limit_status: pd.DataFrame | None) -> bool:
    if limit_status is not None and not limit_status.empty:
        lim = limit_status[
            (limit_status["ts_code"] == code)
            & (limit_status["trade_date"] == trade_date)
        ]
        if not lim.empty and "up_limit" in lim.columns:
            up_limit = float(lim["up_limit"].iloc[-1])
            close = float(stock_row.get("close", np.nan))
            if np.isfinite(close) and up_limit > 0:
                return bool(abs(close - up_limit) < 0.005)
    pct = float(stock_row.get("pct_chg", np.nan))
    return bool(np.isfinite(pct) and pct >= 9.5)


# ═══════════════════════════════════════════════════════════════════════
# Calendar-aligned valuation grid
# ═══════════════════════════════════════════════════════════════════════
def _valuation_grid(prices: pd.DataFrame, codes: list[str], entry_date: int,
                    calendar: np.ndarray, horizon: int,
                    suspend_status: pd.DataFrame | None = None,
                    ) -> pd.DataFrame | None:
    """Equal-weight FROZEN basket paths on the unified trading-day grid.

    Index: day_index 1..horizon (grid days after entry). Columns: trade_date,
    close_ret / low_ret / high_ret (cumulative vs entry close, averaged over
    the frozen basket) and n_valued (components with real data that day).
    """
    idx = np.searchsorted(calendar, entry_date)
    if idx >= len(calendar) or calendar[idx] != entry_date:
        return None
    grid = [int(d) for d in calendar[idx: idx + horizon + 1]]  # entry + horizon
    if len(grid) < 2:
        return None

    suspended_keys: set[tuple[str, int]] = set()
    if suspend_status is not None and not suspend_status.empty:
        suspended_keys = set(zip(
            suspend_status["ts_code"].astype(str),
            suspend_status["trade_date"].astype(int),
        ))

    per_stock = []
    for code in codes:
        rows = prices[
            (prices["ts_code"] == code)
            & (prices["trade_date"].isin(grid))
        ].set_index("trade_date").sort_index()
        if entry_date not in rows.index:
            return None  # resolve_entry guarantees entry-day data; fail loud
        entry_close = float(rows.at[entry_date, "adj_close"])
        if not np.isfinite(entry_close) or entry_close <= 0:
            return None
        frame = pd.DataFrame(index=pd.Index(grid, name="trade_date"))
        frame["has_row"] = frame.index.isin(rows.index)
        for col in ("adj_close", "adj_low", "adj_high"):
            frame[col] = rows[col] if col in rows.columns else np.nan
        frame["has_data"] = frame[["adj_close", "adj_low", "adj_high"]].notna().all(axis=1)
        frame["audited_suspension"] = [
            (str(code), int(day)) in suspended_keys for day in frame.index
        ]
        frame["is_carried"] = (~frame["has_data"]) & frame["audited_suspension"]
        prior_close = frame["adj_close"].ffill()
        frame["val_close"] = frame["adj_close"].where(frame["has_data"])
        frame.loc[frame["is_carried"], "val_close"] = prior_close
        frame["val_low"] = frame["adj_low"].where(frame["has_data"])
        frame["val_high"] = frame["adj_high"].where(frame["has_data"])
        frame.loc[frame["is_carried"], "val_low"] = frame.loc[
            frame["is_carried"], "val_close"
        ]
        frame.loc[frame["is_carried"], "val_high"] = frame.loc[
            frame["is_carried"], "val_close"
        ]
        frame["valuation_ok"] = frame[
            ["val_close", "val_low", "val_high"]
        ].notna().all(axis=1)
        frame["missing_reason"] = ""
        missing = ~frame["valuation_ok"]
        frame.loc[missing & ~frame["has_row"], "missing_reason"] = (
            "unexplained_missing_price"
        )
        frame.loc[missing & frame["has_row"], "missing_reason"] = "invalid_ohlc"
        frame["close_ret"] = frame["val_close"] / entry_close - 1.0
        frame["low_ret"] = frame["val_low"] / entry_close - 1.0
        frame["high_ret"] = frame["val_high"] / entry_close - 1.0
        frame["ts_code"] = code
        per_stock.append(frame.reset_index())
    stacked = pd.concat(per_stock, ignore_index=True)
    stacked = stacked[stacked["trade_date"] > entry_date]
    if stacked.empty:
        return None
    grid_map = {d: i for i, d in enumerate(grid)}
    stacked["day_index"] = stacked["trade_date"].map(grid_map)
    # FROZEN denominator: mean over the full entry basket every day
    out = stacked.groupby("day_index").agg(
        trade_date=("trade_date", "max"),
        close_ret=("close_ret", lambda values: values.mean(skipna=False)),
        low_ret=("low_ret", lambda values: values.mean(skipna=False)),
        high_ret=("high_ret", lambda values: values.mean(skipna=False)),
        n_valued=("has_data", "sum"),
        n_carried=("is_carried", "sum"),
        n_valuation=("valuation_ok", "sum"),
    ).reset_index()
    out["n_components"] = len(codes)
    out["valuation_coverage"] = out["n_valuation"] / len(codes)
    out["real_data_coverage"] = out["n_valued"] / len(codes)
    gap_rows = stacked[~stacked["valuation_ok"]][
        ["trade_date", "ts_code", "missing_reason"]
    ]
    gaps = [
        {
            "trade_date": int(row["trade_date"]),
            "ts_code": str(row["ts_code"]),
            "reason": str(row["missing_reason"] or INVALID_DATA_GAP),
        }
        for _, row in gap_rows.iterrows()
    ]
    gap_by_day: dict[int, list[dict]] = {}
    for gap in gaps:
        gap_by_day.setdefault(gap["trade_date"], []).append({
            "ts_code": gap["ts_code"], "reason": gap["reason"],
        })
    out["missing_reasons"] = [
        gap_by_day.get(int(day), []) for day in out["trade_date"]
    ]
    out.attrs["unexplained_gaps"] = gaps
    return out


# ═══════════════════════════════════════════════════════════════════════
# Outcome evaluation for one signal
# ═══════════════════════════════════════════════════════════════════════
def evaluate_signal_outcome(
    prices: pd.DataFrame,
    calendar: np.ndarray,
    signal: dict,
    config: dict,
    limit_status: pd.DataFrame | None = None,
    stock_status: pd.DataFrame | None = None,
    suspend_status: pd.DataFrame | None = None,
) -> tuple[dict, list[dict]]:
    """Compute (outcome record, entry-eligibility rows) for one signal."""
    horizons = sorted(int(h) for h in config.get("horizons_trading_days", [5, 10, 20]))
    max_horizon = max(horizons)
    target = float(config.get("target_net_gain", 0.05))
    cost = float(config.get("round_trip_cost_bps", 100)) / 10000.0
    stops = sorted(
        (float(s) for s in config.get("stop_levels", [-0.05, -0.08, -0.10])),
        reverse=True,
    )
    min_components = int(config.get("min_entry_components", 3))

    record: dict = {c: None for c in OUTCOME_COLUMNS}
    record.update({
        "signal_id": signal["signal_id"],
        "live_signal_date": int(signal["live_signal_date"]),
        "status": PENDING_ENTRY, "days_tracked": 0,
        "unexplained_gap_count": 0,
    })

    if signal.get("entry_resolution_idempotency_key"):
        resolution = {
            "entry_status": signal.get("entry_status"),
            "entry_date": signal.get("entry_date"),
            "entry_component_codes": signal.get("entry_component_codes") or [],
            "exclusions": signal.get("entry_exclusions") or [],
            "input_digest": signal.get("entry_input_digest"),
            "data_version": signal.get("entry_data_version"),
        }
    else:
        resolution = resolve_entry(
            prices,
            calendar,
            signal,
            limit_status=limit_status,
            stock_status=stock_status,
            min_components=min_components,
            entry_liquidity=config.get("entry_liquidity"),
        )
    record["entry_status"] = resolution["entry_status"]
    record["entry_date"] = resolution["entry_date"]
    eligibility_rows = [
        {"signal_id": signal["signal_id"],
         "live_signal_date": int(signal["live_signal_date"]),
         "entry_date": resolution["entry_date"],
         "ts_code": code, "included": True, "reason": ""}
        for code in resolution["entry_component_codes"]
    ] + [
        {"signal_id": signal["signal_id"],
         "live_signal_date": int(signal["live_signal_date"]),
         "entry_date": resolution["entry_date"],
         "ts_code": row["ts_code"], "included": False, "reason": row["reason"]}
        for row in resolution["exclusions"]
    ]

    if resolution["entry_status"] != ENTRY_RESOLVED:
        record["status"] = resolution["entry_status"]
        return record, eligibility_rows

    entry_codes = resolution["entry_component_codes"]
    record["n_entry_components"] = len(entry_codes)
    paths = _valuation_grid(prices, entry_codes, resolution["entry_date"],
                            calendar, max_horizon, suspend_status=suspend_status)
    if paths is None or paths.empty:
        record["status"] = PENDING_ENTRY
        return record, eligibility_rows
    record["days_tracked"] = int(len(paths))
    record["min_valued_components"] = int(paths["n_valued"].min())
    record["min_valuation_coverage"] = float(paths["valuation_coverage"].min())
    record["min_real_data_coverage"] = float(paths["real_data_coverage"].min())
    coverage = paths[[
        "trade_date", "n_components", "n_valued", "n_carried",
        "n_valuation", "valuation_coverage", "real_data_coverage",
        "missing_reasons",
    ]].to_dict("records")
    record["daily_valuation_coverage"] = json.dumps(
        coverage, ensure_ascii=False, default=str
    )
    gaps = paths.attrs.get("unexplained_gaps", [])
    record["unexplained_gap_count"] = len(gaps)
    record["data_gap_reasons"] = json.dumps(gaps, ensure_ascii=False)
    if gaps:
        record["status"] = OUTCOME_DATA_BLOCKED
        return record, eligibility_rows

    record["status"] = "COMPLETE" if len(paths) >= max_horizon else "PARTIAL"
    record.update({
        "target_hit_close": False,
        "component_high_upper_bound_hit": False,
        "first_stop_hit": False,
        "stop_before_target": False,
        "path_ambiguous": False,
    })

    for horizon in horizons:
        row = paths[paths["day_index"] == horizon]
        if not row.empty:
            record[f"ret_{horizon}d_net"] = float(row["close_ret"].iloc[0]) - cost
    record["ret_end_net"] = float(paths["close_ret"].iloc[-1]) - cost

    record["mae"] = float(paths["low_ret"].min())
    record["mfe"] = float(paths["high_ret"].max())

    close_hits = paths[paths["close_ret"] - cost >= target]
    upper_bound_hits = paths[paths["high_ret"] - cost >= target]
    record["target_hit_close"] = not close_hits.empty
    record["component_high_upper_bound_hit"] = not upper_bound_hits.empty
    if not close_hits.empty:
        record["days_to_target"] = int(close_hits["day_index"].iloc[0])

    first_stop_day, first_stop_level = None, None
    for _, row in paths.iterrows():
        for level in stops:  # shallowest first: report the first level crossed
            if row["low_ret"] <= level:
                first_stop_day = int(row["day_index"])
                first_stop_level = float(level)
                break
        if first_stop_day is not None:
            break
    record["first_stop_hit"] = first_stop_day is not None
    record["first_stop_level"] = first_stop_level
    record["first_stop_day"] = first_stop_day

    # Conservative same-day rule: daily bars cannot order TP vs SL touches —
    # count the stop first and flag the path as ambiguous.
    if first_stop_day is not None and not upper_bound_hits.empty:
        first_target_day = int(upper_bound_hits["day_index"].iloc[0])
        if first_stop_day < first_target_day:
            record["stop_before_target"] = True
        elif first_stop_day == first_target_day:
            record["stop_before_target"] = True
            record["path_ambiguous"] = True
    elif first_stop_day is not None:
        record["stop_before_target"] = True
    return record, eligibility_rows


def update_outcomes(
    outcomes_path,
    eligibility_path,
    prices: pd.DataFrame,
    calendar: np.ndarray,
    signals: list[dict],
    config: dict,
    limit_status: pd.DataFrame | None = None,
    stock_status: pd.DataFrame | None = None,
    suspend_status: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Recompute all signal outcomes and persist forward_outcomes.csv +
    entry_eligibility.csv. Deterministic from prices — idempotent refresh."""
    records, eligibility_rows = [], []
    for signal in signals:
        record, rows = evaluate_signal_outcome(
            prices, calendar, signal, config, limit_status, stock_status,
            suspend_status,
        )
        records.append(record)
        eligibility_rows.extend(rows)
    frame = pd.DataFrame(records, columns=OUTCOME_COLUMNS)
    outcomes_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(outcomes_path, index=False, encoding="utf-8-sig")
    pd.DataFrame(
        eligibility_rows, columns=ENTRY_ELIGIBILITY_COLUMNS
    ).to_csv(eligibility_path, index=False, encoding="utf-8-sig")
    return frame

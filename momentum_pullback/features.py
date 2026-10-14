"""Price-observation clocks and market-session liquidity clocks stay separate."""
from __future__ import annotations

import math
from collections import deque

import numpy as np
import pandas as pd

from momentum_pullback.contracts import Contract, GateError
from momentum_pullback.data_adapter import KEYS, unique_keys, validate_calendar_binding, validate_normalized_panel

PERCENTILE_COVARIATES = ["momentum63", "volatility20", "circ_mv_cny", "adv20_cny"]
ROSTER_COLUMNS = ["trade_date", "ts_code", "required_for_rank", "track_identity"]


def _finite(value) -> bool:
    return value is not None and bool(np.isfinite(float(value)))


def _boolean_mask(values: pd.Series, column: str) -> None:
    if not values.map(lambda value: isinstance(value, (bool, np.bool_))).all():
        raise GateError("ROSTER_BOOLEAN_INVALID", column)


def average_rank_percentiles(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """One denominator definition: average rank, scaled to the unit interval."""
    return frame[columns].rank(method="average", pct=True)


def validate_roster(roster: pd.DataFrame, frame: pd.DataFrame) -> pd.DataFrame:
    """Require an external daily roster. Observed price rows are not that roster."""
    if any(column not in roster for column in ROSTER_COLUMNS):
        raise GateError("ROSTER_SCHEMA_MISSING", sorted(set(ROSTER_COLUMNS) - set(roster)))
    if roster.empty:
        raise GateError("ROSTER_EMPTY")
    unique_keys(roster, ["trade_date", "ts_code"], "roster")
    for column in ["required_for_rank", "track_identity"]:
        _boolean_mask(roster[column], column)
    if (roster["required_for_rank"] & ~roster["track_identity"]).any():
        raise GateError("ROSTER_ROLE_INVALID")
    missing_dates = sorted(set(frame.trade_date) - set(roster.trade_date))
    if missing_dates:
        raise GateError("ROSTER_DATE_MISSING", {"missing_count": len(missing_dates), "missing": missing_dates[:10]})
    return roster[roster.trade_date.isin(set(frame.trade_date))].copy()


def _ema_ready(ema_support, ema_trend) -> bool:
    return ema_support is not None and ema_trend is not None and _finite(ema_support) and _finite(ema_trend)


def assign_local_eligibility(frame: pd.DataFrame, contract: Contract) -> pd.DataFrame:
    """Row facts only. Without a certified roster this cannot elect anyone."""
    cfg = contract.section("features")
    frame = frame.copy()
    frame["strong_status"] = "UNKNOWN"
    frame["rank_denominator_complete"] = False
    frame["momentum_rank"] = np.nan
    for column in PERCENTILE_COVARIATES:
        frame["pct_" + column] = np.nan
    for _, day in frame.groupby("trade_date", sort=True):
        known_ineligible = (day["membership_known"] & ~day["is_member"]) | (day["st_known"] & day["is_st"]) | (day["price_history_known"] & day["valid_observations"].lt(cfg["min_price_observations"]))
        price_fail = day["price_known"] & ((day["adj_close"] <= day["ema50"]) | (day["ema21"] <= day["ema21_lag5"]))
        frame.loc[day.index[known_ineligible | price_fail], "strong_status"] = "KNOWN_INELIGIBLE"
    return frame


def apply_cross_section(frame: pd.DataFrame, roster: pd.DataFrame, contract: Contract) -> pd.DataFrame:
    """Rank once, after every required name for these sessions is present."""
    cfg = contract.section("features")
    roster = validate_roster(roster, frame)
    frame = frame.copy()
    frame["strong_status"] = "UNKNOWN"
    frame["rank_denominator_complete"] = False
    frame["momentum_rank"] = np.nan
    for column in PERCENTILE_COVARIATES:
        frame["pct_" + column] = np.nan
    for date, day_roster in roster.groupby("trade_date", sort=True):
        required = set(day_roster.loc[day_roster.required_for_rank, "ts_code"].astype(str))
        tracked = set(day_roster.loc[day_roster.track_identity, "ts_code"].astype(str))
        day = frame.loc[frame.trade_date.eq(date)]
        present = set(day.ts_code.astype(str))
        missing_required = sorted(required - present)
        if missing_required:
            raise GateError("REQUIRED_MEMBER_MISSING", {"trade_date": int(date), "missing_count": len(missing_required), "missing": missing_required[:10]})
        missing_tracked = sorted(tracked - present)
        if missing_tracked:
            raise GateError("IDENTITY_TRACKING_MEMBER_MISSING", {"trade_date": int(date), "missing_count": len(missing_tracked), "missing": missing_tracked[:10]})
        required_rows = day[day.ts_code.astype(str).isin(required)]
        eligibility_known = required_rows["membership_known"] & (~required_rows["is_member"] | required_rows["st_known"])
        universe = required_rows[required_rows["is_member"] & required_rows["st_known"] & ~required_rows["is_st"]]
        history_unknown = universe[~universe["price_history_known"]]
        eligible = universe[universe["price_history_known"] & universe["valid_observations"].ge(cfg["min_price_observations"])]
        complete = bool(eligibility_known.all() and history_unknown.empty and not eligible.empty and eligible["momentum63"].map(_finite).all())
        frame.loc[day.index, "rank_denominator_complete"] = complete
        known_ineligible = (day["membership_known"] & ~day["is_member"]) | (day["st_known"] & day["is_st"]) | (day["price_history_known"] & day["valid_observations"].lt(cfg["min_price_observations"]))
        price_fail = day["price_known"] & ((day["adj_close"] <= day["ema50"]) | (day["ema21"] <= day["ema21_lag5"]))
        frame.loc[day.index[known_ineligible | price_fail], "strong_status"] = "KNOWN_INELIGIBLE"
        if not complete:
            continue
        ranked = eligible.sort_values(["momentum63", "ts_code"], ascending=[False, True], kind="stable")
        n_top = math.ceil(len(ranked) * cfg["top_fraction"])
        frame.loc[ranked.index, "momentum_rank"] = np.arange(1, len(ranked) + 1)
        frame.loc[ranked.index, "strong_status"] = "KNOWN_INELIGIBLE"
        percentages = average_rank_percentiles(ranked, PERCENTILE_COVARIATES)
        for column in PERCENTILE_COVARIATES:
            frame.loc[percentages.index, "pct_" + column] = percentages[column]
        top = ranked.head(n_top)
        passed = top["price_known"] & top["adj_close"].gt(top["ema50"]) & top["ema21"].gt(top["ema21_lag5"])
        frame.loc[top.index[passed], "strong_status"] = "KNOWN_ELIGIBLE"
    return frame


def build_features(panel: pd.DataFrame, calendar: list[int], contract: Contract, *, states: dict | None = None, return_states: bool = False, roster: pd.DataFrame | None = None, rank: bool = True, certified_calendar: list[int] | None = None) -> pd.DataFrame | dict:
    """Input is a normalized full market-session grid, not raw cache guesses."""
    required = set(KEYS + ["adj_open", "adj_high", "adj_low", "adj_close", "amount_cny", "circ_mv_cny", "price_status", "membership_known", "is_member", "st_known", "is_st", "signal_cutoff", "price_available_at", "membership_available_at", "st_available_at", "amount_available_at", "basic_available_at", "industry_code", "industry_available_at"] + [f"{prefix}_effective_{edge}" for prefix in ["membership", "st", "industry"] for edge in ["from", "to"]])
    if not required.issubset(panel):
        raise GateError("NORMALIZED_INPUT_SCHEMA_MISSING", sorted(required - set(panel)))
    if certified_calendar is not None:
        validate_calendar_binding(calendar, certified_calendar)
    active_calendar = sorted(panel.trade_date.unique().tolist())
    validate_normalized_panel(panel, active_calendar)
    if not calendar or calendar != sorted(set(calendar)) or not set(active_calendar).issubset(calendar):
        raise GateError("FEATURE_CALENDAR_INVALID")
    cfg = contract.section("features")
    positions = {date: position for position, date in enumerate(calendar)}
    if [positions[date] for date in active_calendar] != list(range(positions[active_calendar[0]], positions[active_calendar[-1]] + 1)):
        raise GateError("FEATURE_CALENDAR_GAP")
    if states is None and active_calendar[0] != calendar[0]:
        raise GateError("FEATURE_ORIGIN_NOT_REPLAYED")
    if states is not None and set(states) != set(panel.ts_code):
        raise GateError("FEATURE_STATE_UNIVERSE_MISMATCH")
    result = []
    next_states = {}
    for code, stock in panel.groupby("ts_code", sort=True):
        stock = stock.set_index("trade_date").sort_index()
        if list(stock.index) != active_calendar:
            raise GateError("MARKET_GRID_INCOMPLETE", str(code))
        saved = (states or {}).get(code, {})
        if states is not None and (not saved or saved.get("contract_hash") != contract.hash or saved.get("last_market_index") != positions[active_calendar[0]] - 1 or saved.get("last_date") != calendar[positions[active_calendar[0]] - 1]):
            raise GateError("FEATURE_CHECKPOINT_IDENTITY_MISMATCH", code)
        prices = list(saved.get("prices", []))
        highs = list(saved.get("highs", []))
        ema_support, ema_trend = saved.get("ema_support"), saved.get("ema_trend")
        support_history = list(saved.get("support_history", []))
        liquidity = deque(saved.get("liquidity", []), maxlen=cfg["adv_market_sessions"])
        history_known = saved.get("price_history_known", True)
        valid_observations = saved.get("valid_observations", 0)
        feature_ready = False
        reset_ready = False
        for date, source in stock.iterrows():
            row = source.to_dict()
            row.update(ts_code=str(code), trade_date=int(date), market_index=positions[int(date)])
            cut = pd.to_datetime(row["signal_cutoff"], utc=True)
            known = lambda column: pd.notna(row.get(column)) and pd.to_datetime(row[column], utc=True) <= cut
            def effective(prefix):
                start, end = row[prefix + "_effective_from"], row[prefix + "_effective_to"]
                return _finite(start) and int(start) <= int(date) and (pd.isna(end) or int(date) <= int(end))
            status = row["price_status"]
            previous_high = max(highs[-cfg["prior_high_observations"]:]) if len(highs) >= cfg["prior_high_observations"] else np.nan
            seeded_before = _ema_ready(ema_support, ema_trend)
            valid_price = status == "TRADED" and known("price_available_at")
            verified_halt_known = status == "VERIFIED_FULL_DAY_HALT" and known("price_available_at") and history_known
            if valid_price:
                o, h, l, c = (float(row[column]) for column in ["adj_open", "adj_high", "adj_low", "adj_close"])
                if not all(_finite(value) and float(value) > 0 for value in [o, h, l, c]) or not (l <= min(o, c) <= max(o, c) <= h):
                    raise GateError("NORMALIZED_PRICE_INVALID", {"code": str(code), "date": int(date)})
                c = float(c)
                row.update(adj_open=o, adj_high=h, adj_low=l, adj_close=c)
                prices.append(c)
                highs.append(float(h))
                valid_observations += 1
                prices = prices[-1 - max(cfg["momentum_intervals"], cfg["volatility_intervals"]):]
                highs = highs[-cfg["prior_high_observations"]:]
                alpha = 2.0 / (cfg["ema_support"] + 1)
                beta = 2.0 / (cfg["ema_trend"] + 1)
                ema_support = c if ema_support is None else alpha * c + (1 - alpha) * ema_support
                ema_trend = c if ema_trend is None else beta * c + (1 - beta) * ema_trend
                support_history.append(ema_support)
                support_history = support_history[-1 - cfg["slope_lag"]:]
            elif status != "VERIFIED_FULL_DAY_HALT" or not known("price_available_at"):
                history_known = False
            amount = row["amount_cny"]
            if status == "VERIFIED_FULL_DAY_HALT" and known("price_available_at"):
                if _finite(amount) and float(amount) != 0:
                    raise GateError("HALT_AMOUNT_CONFLICT", {"code": str(code), "date": int(date)})
                liquidity.append((0.0, "VERIFIED_HALT_ZERO"))
            elif known("amount_available_at") and _finite(amount) and float(amount) >= 0:
                liquidity.append((float(amount), "OBSERVED_AMOUNT"))
            else:
                liquidity.append((None, "UNKNOWN_AMOUNT"))
            full_liquidity = len(liquidity) == cfg["adv_market_sessions"] and all(_finite(value) for value, _ in liquidity)
            adv = sum(value for value, _ in liquidity) / cfg["adv_market_sessions"] if full_liquidity else np.nan
            n = valid_observations
            momentum = prices[-1] / prices[-1 - cfg["momentum_intervals"]] - 1 if n > cfg["momentum_intervals"] and history_known else np.nan
            volatility = np.nan
            if n > cfg["volatility_intervals"] and history_known:
                window = np.array(prices[-1 - cfg["volatility_intervals"]:], dtype=float)
                volatility = float(np.std(window[1:] / window[:-1] - 1, ddof=1))
            feature_ready = bool(history_known and _ema_ready(ema_support, ema_trend) and n >= cfg["min_price_observations"])
            reset_ready = bool(feature_ready and valid_price and seeded_before)
            row.update(price_known=bool(valid_price and history_known), verified_halt_known=bool(verified_halt_known), price_history_known=history_known, valid_observations=n, feature_ready=feature_ready, reset_ready=reset_ready, ema21=ema_support if history_known and valid_price else np.nan, ema50=ema_trend if history_known and valid_price else np.nan, ema21_lag5=support_history[-1 - cfg["slope_lag"]] if len(support_history) > cfg["slope_lag"] and history_known and valid_price else np.nan, prior_high20=previous_high if history_known and valid_price else np.nan, momentum63=momentum, volatility20=volatility, adv20_cny=adv, liquidity_known=full_liquidity, verified_halt_days=sum(origin == "VERIFIED_HALT_ZERO" for _, origin in liquidity), unknown_amount_days=sum(origin == "UNKNOWN_AMOUNT" for _, origin in liquidity), adv_window_start=calendar[max(0, positions[int(date)] - cfg["adv_market_sessions"] + 1)])
            row["membership_known"] = bool(row["membership_known"] and known("membership_available_at"))
            if not _finite(row["membership_effective_from"]):
                row["membership_known"] = False
            elif row["membership_known"] and not effective("membership"):
                row["is_member"] = False
            row["st_known"] = bool(row["st_known"] and known("st_available_at") and effective("st"))
            if not known("basic_available_at"):
                row["circ_mv_cny"] = np.nan
            if not known("industry_available_at") or not effective("industry"):
                row["industry_code"] = None
            result.append(row)
        next_states[str(code)] = {"contract_hash": contract.hash, "last_date": active_calendar[-1], "last_market_index": positions[active_calendar[-1]], "prices": prices, "highs": highs, "ema_support": ema_support, "ema_trend": ema_trend, "support_history": support_history, "liquidity": list(liquidity), "price_history_known": bool(history_known), "valid_observations": valid_observations, "feature_ready": bool(feature_ready), "reset_ready": bool(reset_ready), "ema_seeded": _ema_ready(ema_support, ema_trend)}
    frame = pd.DataFrame(result).sort_values(["trade_date", "ts_code"], kind="stable").reset_index(drop=True)
    frame["contract_hash"] = contract.hash
    if roster is not None and rank:
        frame = apply_cross_section(frame, roster, contract)
    elif rank:
        frame = assign_local_eligibility(frame, contract)
    else:
        frame["strong_status"] = "UNKNOWN"
        frame["rank_denominator_complete"] = False
        frame["momentum_rank"] = np.nan
        for column in PERCENTILE_COVARIATES:
            frame["pct_" + column] = np.nan
    return {"features": frame, "states": next_states} if return_states else frame

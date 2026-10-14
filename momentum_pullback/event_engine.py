"""Causal state transitions retain identity through output-window boundaries."""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from momentum_pullback.contracts import Contract, GateError, fingerprint
from momentum_pullback.data_adapter import KEYS, unique_keys

EVENT_COLUMNS = ["event_id", "ts_code", "trend_id", "breakout_id", "root_date", "signal_date", "root_age_sessions", "touch_no", "reclaim_pass", "event_status", "is_primary_first", "signal_cutoff", "contract_hash"]
ROOT_COLUMNS = ["trend_id", "ts_code", "root_date", "root_market_index", "reset_observed_at"]
BREAKOUT_COLUMNS = ["breakout_id", "ts_code", "trade_date", "trend_id", "is_root", "strong_status", "identity_known", "contract_hash"]


@dataclass
class TrendState:
    identity_known: bool = False
    reset_observed_at: int | None = None
    root_date: int | None = None
    root_index: int | None = None
    trend_id: str | None = None
    touch_no: int = 0
    in_touch_segment: bool = False
    window_closed: bool = False
    last_date: int | None = None
    last_market_index: int | None = None
    uncertainty_reason: str | None = "LEFT_CENSORED"


def _finite(*values) -> bool:
    return all(pd.notna(value) and np.isfinite(float(value)) for value in values)


def build_events(features: pd.DataFrame, contract: Contract, *, states: dict | None = None) -> dict:
    required = set(KEYS + ["price_known", "adj_low", "adj_close", "ema21", "ema50", "prior_high20", "strong_status", "market_index", "signal_cutoff", "contract_hash"])
    if not required.issubset(features) or features.empty:
        raise GateError("EVENT_INPUT_UNEVALUABLE", sorted(required - set(features)))
    unique_keys(features, KEYS, "features")
    if not features.contract_hash.eq(contract.hash).all():
        raise GateError("FEATURE_CONTRACT_MISMATCH")
    if not features.strong_status.isin(["KNOWN_ELIGIBLE", "KNOWN_INELIGIBLE", "UNKNOWN"]).all():
        raise GateError("STRONG_STATUS_INVALID")
    if not features.price_known.map(lambda value: isinstance(value, (bool, np.bool_))).all():
        raise GateError("PRICE_KNOWN_STATE_INVALID")
    known_rows = features.loc[features.price_known, ["adj_low", "adj_close", "ema21", "ema50"]]
    if not np.isfinite(known_rows.to_numpy(dtype=float)).all() or (known_rows <= 0).any().any():
        raise GateError("KNOWN_PRICE_FEATURE_INVALID")
    scope, cfg = contract.section("scope"), contract.section("events")
    state_map = {code: TrendState(**state) for code, state in (states or {}).items()}
    events, transitions, roots, observed, breakouts = [], [], {}, [], []
    grid = features[["trade_date", "market_index"]].drop_duplicates()
    if grid.trade_date.duplicated().any() or grid.market_index.duplicated().any():
        raise GateError("EVENT_CALENDAR_CONFLICT")
    expected_grid = grid.sort_values("trade_date")
    if not expected_grid.market_index.is_monotonic_increasing:
        raise GateError("EVENT_CALENDAR_CONFLICT")
    for code, stock in features.groupby("ts_code"):
        if set(stock.trade_date) != set(grid.trade_date):
            raise GateError("EVENT_MARKET_GRID_INCOMPLETE", code)
    for _, row in features.sort_values(["trade_date", "ts_code"], kind="stable").iterrows():
        code, date, index = str(row.ts_code), int(row.trade_date), int(row.market_index)
        state = state_map.setdefault(code, TrendState())
        if state.last_date is not None and date <= state.last_date:
            raise GateError("NON_MONOTONIC_EVENT_REPLAY", code)
        if state.last_market_index is not None and index != state.last_market_index + 1:
            raise GateError("EVENT_CALENDAR_GAP", code)
        state.last_date = date
        state.last_market_index = index
        price_known = bool(row.price_known) and _finite(row.adj_low, row.adj_close, row.ema21, row.ema50)
        action = "MONITOR"
        if not price_known:
            if row.get("verified_halt_known") is True or isinstance(row.get("verified_halt_known"), np.bool_) and bool(row.verified_halt_known):
                action = "VERIFIED_HALT_NO_PRICE_OBSERVATION"
            else:
                state.identity_known = False
                state.uncertainty_reason = "PRICE_PATH_UNKNOWN"
                action = "IDENTITY_UNKNOWN"
        elif row.adj_close <= row.ema50:
            state.identity_known = True
            state.reset_observed_at = date
            state.root_date = state.root_index = state.trend_id = None
            state.touch_no = 0
            state.in_touch_segment = False
            state.window_closed = False
            state.uncertainty_reason = None
            action = "VALID_RESET"
        else:
            breakout = _finite(row.prior_high20) and row.adj_close > row.prior_high20
            if state.root_date is None and breakout:
                if row.strong_status == "UNKNOWN":
                    state.identity_known = False
                    state.uncertainty_reason = "ROOT_QUALIFICATION_UNKNOWN"
                    action = "ROOT_IDENTITY_UNCERTAIN"
                elif state.identity_known and row.strong_status == "KNOWN_ELIGIBLE":
                    state.root_date, state.root_index = date, index
                    state.trend_id = fingerprint([contract.hash, code, state.reset_observed_at, date])[:24]
                    action = "ROOT_OPENED"
            if breakout:
                breakouts.append({"breakout_id": fingerprint([contract.hash, code, date, "breakout"])[:24], "ts_code": code, "trade_date": date, "trend_id": state.trend_id, "is_root": action == "ROOT_OPENED", "strong_status": row.strong_status, "identity_known": state.identity_known, "contract_hash": contract.hash})
            elif state.root_date is not None and not state.identity_known:
                action = "IDENTITY_UNKNOWN"
            if state.root_date is not None and state.identity_known:
                roots[state.trend_id] = {"trend_id": state.trend_id, "ts_code": code, "root_date": state.root_date, "root_market_index": state.root_index, "reset_observed_at": state.reset_observed_at}
                age = index - state.root_index
                if age > 0:
                    touch = row.adj_low <= row.ema21
                    first_day = touch and not state.in_touch_segment
                    if first_day:
                        state.touch_no += 1
                        reclaim = bool(row.adj_close > row.ema21)
                        eligible = row.strong_status == "KNOWN_ELIGIBLE"
                        if not reclaim or row.strong_status == "KNOWN_INELIGIBLE":
                            event_status = "FAILED_FIRST_DAY"
                        elif row.strong_status == "UNKNOWN":
                            event_status = "QUALIFICATION_UNKNOWN"
                        elif state.touch_no == 1 and age <= cfg["wait_sessions"]:
                            event_status = "FIRST_CANDIDATE"
                        elif state.touch_no == 1:
                            event_status = "EXPIRED_FIRST_DIAGNOSTIC"
                        else:
                            event_status = "LATER_CANDIDATE"
                        event = {"event_id": fingerprint([contract.hash, code, state.trend_id, date, state.touch_no])[:24], "ts_code": code, "trend_id": state.trend_id, "breakout_id": fingerprint([contract.hash, code, state.root_date, "breakout"])[:24], "root_date": state.root_date, "signal_date": date, "root_age_sessions": age, "touch_no": state.touch_no, "reclaim_pass": reclaim, "event_status": event_status, "is_primary_first": event_status == "FIRST_CANDIDATE", "signal_cutoff": row.signal_cutoff, "contract_hash": contract.hash}
                        if scope["output_start"] <= date <= scope["output_end"]:
                            events.append(event)
                    state.in_touch_segment = touch
                    if age >= cfg["wait_sessions"]:
                        state.window_closed = True
        transitions.append({"ts_code": code, "trade_date": date, "action": action, "identity_known": state.identity_known, "root_date": state.root_date, "touch_no": state.touch_no, "uncertainty_reason": state.uncertainty_reason})
        if state.root_index is not None and index - state.root_index >= cfg["wait_sessions"]:
            state.window_closed = True
        # Ordinary controls exclude price touches even without a trend root.
        observed.append({"ts_code": code, "trade_date": date, "in_touch_segment": bool(row.adj_low <= row.ema21) if price_known and state.identity_known else None, "identity_known": state.identity_known, "root_date": state.root_date, "touch_no": state.touch_no})
    event_frame = pd.DataFrame(events, columns=EVENT_COLUMNS)
    states_frame = pd.DataFrame(observed)
    window = states_frame[states_frame.trade_date.between(scope["output_start"], scope["output_end"])]
    unknown = int((~window.identity_known).sum())
    unknown_qualification = int(event_frame.event_status.eq("QUALIFICATION_UNKNOWN").sum())
    if window.empty or int(features.trade_date.max()) < scope["output_end"]:
        status = "OUTPUT_WINDOW_NOT_COVERED"
    elif unknown:
        status = "PARTIAL_IDENTITY_UNEVALUABLE"
    elif unknown_qualification:
        status = "PARTIAL_QUALIFICATION_UNEVALUABLE"
    elif event_frame.empty:
        status = "EVALUATED_ZERO_EVENTS"
    else:
        status = "EVENTS_BUILT"
    return {"status": status, "events": event_frame, "transitions": pd.DataFrame(transitions), "observations": states_frame, "roots": pd.DataFrame(list(roots.values()), columns=ROOT_COLUMNS), "breakouts": pd.DataFrame(breakouts, columns=BREAKOUT_COLUMNS), "states": {code: asdict(state) for code, state in state_map.items()}, "unknown_identity_rows": unknown, "unknown_qualification_events": unknown_qualification}

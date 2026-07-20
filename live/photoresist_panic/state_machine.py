"""Online first-trigger state machine: IDLE -> ACTIVE -> COOLDOWN -> IDLE.

Rules (frozen, see plan §7):
  IDLE:     first primary_5d trigger records live_signal_date, emits the
            first alert, and enters ACTIVE.
  ACTIVE:   at most `active_max_trading_days` (20) trading days. No new
            events; repeated triggers only refresh severity; a P2->P3/P4
            upgrade emits an upgrade notification; the first trigger date is
            never rewritten.
  COOLDOWN: after the observation window, `cooldown_clear_days` (5)
            consecutive non-triggered days are required to re-arm. A trigger
            during cooldown resets the counter but creates no new event;
            severity upgrades still notify against the existing signal ID.

State is persisted to panic_state.json. Re-processing an already-processed
trade date is idempotent: the state does not advance and no alert is emitted.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

IDLE = "IDLE"
ACTIVE = "ACTIVE"
COOLDOWN = "COOLDOWN"

_SEVERITY_RANK = {"P0": 0, "P1": 1, "P2": 2, "P3": 3, "P4": 4}


@dataclass
class PanicState:
    state: str = IDLE
    live_signal_date: int | None = None      # first trigger day of current event
    signal_id: str | None = None
    active_days_elapsed: int = 0             # trading days spent in ACTIVE
    cooldown_clear_count: int = 0            # consecutive non-trigger days in COOLDOWN
    max_severity: str = "P0"                 # highest severity within current event
    last_processed_date: int | None = None
    event_counter: int = 0
    history_dates: list[int] = field(default_factory=list)  # trigger days in event

    @classmethod
    def load(cls, path: Path) -> "PanicState":
        if not path.exists():
            return cls()
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise RuntimeError(f"panic_state.json corrupted: {exc}") from exc
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in payload.items() if k in known})

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        tmp.replace(path)


def step(
    state: PanicState,
    trade_date: int,
    triggered: bool,
    severity: str,
    active_max_trading_days: int = 20,
    cooldown_clear_days: int = 5,
) -> tuple[PanicState, dict]:
    """Advance the state machine by one trading day.

    Returns (new_state, transition). The transition carries a FULL snapshot of
    the event identity at that day (signal_id, live_signal_date,
    event_counter, counters) — downstream writers must use these snapshot
    fields and never re-read the final state to explain historical days.

      kind: none | duplicate_run | first_trigger | severity_upgrade |
            still_active | enter_cooldown | cooldown_reset | rearmed
    """
    transition = {
        "kind": "none",
        "trade_date": int(trade_date),
        "state_before": state.state,
        "state_after": state.state,
        "emit_alert": False,
        "is_new_event": False,
        "triggered": bool(triggered),
        "severity": severity,
    }

    # Idempotency: same or older date -> no state advance, no re-notification
    if state.last_processed_date is not None and trade_date <= state.last_processed_date:
        transition["kind"] = "duplicate_run"
        transition["detail"] = (
            f"trade_date {trade_date} already processed "
            f"(last={state.last_processed_date}); state unchanged"
        )
        transition.update(_snapshot_fields(state))
        return state, transition

    if state.state == IDLE:
        if triggered:
            state.state = ACTIVE
            state.live_signal_date = int(trade_date)
            state.event_counter += 1
            state.signal_id = f"PANIC_{trade_date}_{state.event_counter:03d}"
            state.active_days_elapsed = 1
            state.max_severity = severity
            state.history_dates = [int(trade_date)]
            transition.update(
                kind="first_trigger", emit_alert=True, is_new_event=True,
            )
    elif state.state == ACTIVE:
        state.active_days_elapsed += 1
        if triggered:
            state.history_dates.append(int(trade_date))
            if _SEVERITY_RANK.get(severity, 0) > _SEVERITY_RANK.get(state.max_severity, 0):
                state.max_severity = severity
                transition.update(kind="severity_upgrade", emit_alert=True)
            else:
                transition["kind"] = "still_active"
        else:
            transition["kind"] = "still_active"
        if state.active_days_elapsed >= active_max_trading_days:
            state.state = COOLDOWN
            state.cooldown_clear_count = 0
            transition["kind"] = (
                transition["kind"] if transition["emit_alert"] else "enter_cooldown"
            )
    elif state.state == COOLDOWN:
        if triggered:
            state.cooldown_clear_count = 0
            state.history_dates.append(int(trade_date))
            if _SEVERITY_RANK.get(severity, 0) > _SEVERITY_RANK.get(
                state.max_severity, 0
            ):
                state.max_severity = severity
                transition.update(kind="severity_upgrade", emit_alert=True)
            else:
                transition["kind"] = "cooldown_reset"
        else:
            state.cooldown_clear_count += 1
            if state.cooldown_clear_count >= cooldown_clear_days:
                # Snapshot the closing event's identity BEFORE clearing it, so
                # the rearmed transition still explains which event ended.
                transition["closed_signal_id"] = state.signal_id
                state.state = IDLE
                state.live_signal_date = None
                state.signal_id = None
                state.active_days_elapsed = 0
                state.cooldown_clear_count = 0
                state.max_severity = "P0"
                state.history_dates = []
                transition["kind"] = "rearmed"

    state.last_processed_date = int(trade_date)
    transition["state_after"] = state.state
    transition.update(_snapshot_fields(state))
    return state, transition


def _snapshot_fields(state: PanicState) -> dict:
    """Post-transition event-identity snapshot embedded in every transition."""
    return {
        "signal_id": state.signal_id,
        "live_signal_date": state.live_signal_date,
        "event_counter": state.event_counter,
        "active_days_elapsed": state.active_days_elapsed,
        "cooldown_clear_count": state.cooldown_clear_count,
        "max_severity": state.max_severity,
    }

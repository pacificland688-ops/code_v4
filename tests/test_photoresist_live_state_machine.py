"""Unit tests for the photoresist live alert state machine."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from live.photoresist_panic.state_machine import (  # noqa: E402
    ACTIVE, COOLDOWN, IDLE, PanicState, step,
)


def advance(state, day, triggered, severity="P2", **kwargs):
    return step(state, day, triggered, severity,
                active_max_trading_days=kwargs.get("active_max", 20),
                cooldown_clear_days=kwargs.get("cooldown", 5))


def test_first_trigger_records_live_signal_date_and_emits():
    state = PanicState()
    state, transition = advance(state, 20240102, True)
    assert state.state == ACTIVE
    assert state.live_signal_date == 20240102
    assert state.signal_id is not None
    assert transition["kind"] == "first_trigger"
    assert transition["emit_alert"] is True
    assert transition["is_new_event"] is True


def test_no_new_event_while_active():
    state = PanicState()
    state, _ = advance(state, 20240102, True)
    first_id = state.signal_id
    state, transition = advance(state, 20240103, True)
    assert state.state == ACTIVE
    assert state.signal_id == first_id
    assert state.live_signal_date == 20240102  # never rewritten
    assert transition["is_new_event"] is False
    assert transition["emit_alert"] is False  # same severity: no re-alert


def test_severity_upgrade_emits_notification():
    state = PanicState()
    state, _ = advance(state, 20240102, True, severity="P2")
    state, transition = advance(state, 20240103, True, severity="P3")
    assert transition["kind"] == "severity_upgrade"
    assert transition["emit_alert"] is True
    assert state.max_severity == "P3"
    # downgrade back to P2 must NOT re-alert
    state, transition = advance(state, 20240104, True, severity="P2")
    assert transition["emit_alert"] is False
    assert state.max_severity == "P3"


def test_active_window_expires_into_cooldown():
    state = PanicState()
    state, _ = advance(state, 20240101, True)
    for offset in range(1, 20):
        state, _ = advance(state, 20240101 + offset, False)
    assert state.state == COOLDOWN


def test_cooldown_requires_consecutive_clear_days():
    state = PanicState(state=COOLDOWN, last_processed_date=20240101,
                       signal_id="PANIC_X", live_signal_date=20231201,
                       max_severity="P2")
    for day in (20240102, 20240103):
        state, _ = advance(state, day, False)
    # re-trigger resets the counter, creates no new event
    state, transition = advance(state, 20240104, True)
    assert transition["kind"] == "cooldown_reset"
    assert transition["is_new_event"] is False
    assert state.cooldown_clear_count == 0
    for day in (20240105, 20240106, 20240107, 20240108):
        state, _ = advance(state, day, False)
    assert state.state == COOLDOWN  # only 4 clear days
    state, transition = advance(state, 20240109, False)
    assert state.state == IDLE
    assert transition["kind"] == "rearmed"
    assert state.signal_id is None


def test_cooldown_severity_upgrade_notifies_without_new_event():
    state = PanicState(
        state=COOLDOWN,
        last_processed_date=20240101,
        signal_id="PANIC_20231201_001",
        live_signal_date=20231201,
        event_counter=1,
        max_severity="P2",
        history_dates=[20231201],
    )
    original_id = state.signal_id
    state, transition = advance(state, 20240102, True, severity="P4")
    assert transition["kind"] == "severity_upgrade"
    assert transition["emit_alert"] is True
    assert transition["is_new_event"] is False
    assert state.state == COOLDOWN
    assert state.signal_id == original_id
    assert state.event_counter == 1
    assert state.max_severity == "P4"
    assert state.history_dates[-1] == 20240102

    state, transition = advance(state, 20240103, True, severity="P3")
    assert transition["kind"] == "cooldown_reset"
    assert transition["emit_alert"] is False


def test_duplicate_run_is_idempotent():
    state = PanicState()
    state, _ = advance(state, 20240102, True)
    snapshot = dict(state.__dict__)
    state, transition = advance(state, 20240102, True)
    assert transition["kind"] == "duplicate_run"
    assert transition["emit_alert"] is False
    assert dict(state.__dict__) == snapshot


def test_state_persistence_roundtrip(tmp_path):
    path = tmp_path / "panic_state.json"
    state = PanicState()
    state, _ = advance(state, 20240102, True, severity="P3")
    state.save(path)
    loaded = PanicState.load(path)
    assert loaded == state


def test_corrupt_state_file_raises(tmp_path):
    path = tmp_path / "panic_state.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(RuntimeError, match="corrupted"):
        PanicState.load(path)


def test_new_event_after_full_cycle_gets_new_signal_id():
    state = PanicState()
    state, first = advance(state, 20240102, True)
    first_id = state.signal_id
    for offset in range(1, 20):  # exhaust ACTIVE
        state, _ = advance(state, 20240102 + offset, False)
    for offset in range(20, 25):  # clear COOLDOWN
        state, _ = advance(state, 20240102 + offset, False)
    assert state.state == IDLE
    state, transition = advance(state, 20240130, True)
    assert transition["is_new_event"] is True
    assert state.signal_id != first_id

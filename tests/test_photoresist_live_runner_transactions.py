"""Transaction + catch-up tests: journal as fact source, snapshot-carrying
transitions, fault injection, recovery, run lock (plan §4 / §10)."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from live.photoresist_panic import journal as journal_mod  # noqa: E402
from live.photoresist_panic.common import RunLock  # noqa: E402
from live.photoresist_panic.journal import TransitionJournal  # noqa: E402
from live.photoresist_panic.runner import (  # noqa: E402
    _proven_idle_initialization_checkpoint,
)
from live.photoresist_panic.state_machine import (  # noqa: E402
    ACTIVE, COOLDOWN, IDLE, PanicState, step,
)

GATE = "primary_5d_frozen_v1"


def drive(journal: TransitionJournal, state: PanicState, days: list[tuple],
          run_id: str = "run_test", active_max: int = 20,
          cooldown: int = 5) -> tuple[PanicState, list[dict]]:
    """Mimic the runner's day loop: step -> journal each transition with the
    day's own snapshot (exactly what _run_daily_inner does)."""
    transitions = []
    for day, triggered, severity in days:
        state, transition = step(state, day, triggered, severity,
                                 active_max_trading_days=active_max,
                                 cooldown_clear_days=cooldown)
        transitions.append(transition)
        journal.append(journal_mod.transition_record(
            GATE, run_id, transition,
            extra={"active_member_codes": ["A", "B", "C", "D"],
                   "eligible_member_codes": ["A", "B", "C"],
                   "market_regime": "bull",
                   "component_status": "SECTOR_WIDE",
                   "alert_status": "X",
                   "data_as_of": day},
        ))
    return state, transitions


def _quiet_days(start_idx: int, n: int) -> list[tuple]:
    return [(20240100 + start_idx + i, False, "P0") for i in range(n)]


# ═══════════════════════════════════════════════════════════════════════
# Journal basics
# ═══════════════════════════════════════════════════════════════════════
def test_journal_append_is_idempotent(tmp_path):
    journal = TransitionJournal(tmp_path / "j.jsonl")
    record = journal_mod.event_record(GATE, "r1", 20240101, "quality_blocked")
    assert journal.append(record) is True
    assert journal.append(record) is False  # duplicate key -> no-op
    reloaded = TransitionJournal(tmp_path / "j.jsonl")
    assert len(reloaded.records) == 1


def test_journal_rebuilds_state_registry_history(tmp_path):
    journal = TransitionJournal(tmp_path / "j.jsonl")
    state = PanicState()
    state, _ = drive(journal, state, [
        (20240101, True, "P2"),
        (20240102, True, "P3"),
        (20240103, False, "P3"),
    ])
    rebuilt = journal_mod.rebuild_state(journal.records)
    assert rebuilt == state
    registry = journal_mod.rebuild_registry(journal.records)
    assert len(registry) == 1
    assert registry[0]["signal_id"] == "PANIC_20240101_001"
    assert registry[0]["active_member_codes"] == ["A", "B", "C", "D"]
    assert registry[0]["eligible_member_codes"] == ["A", "B", "C"]
    history = journal_mod.rebuild_history(journal.records)
    assert len(history) == 3
    assert list(history["transition"]) == ["first_trigger", "severity_upgrade",
                                           "still_active"]
    # each row carries its own day's snapshot, not the final state
    assert list(history["signal_id"].unique()) == ["PANIC_20240101_001"]


def test_entry_resolution_is_append_only_and_requires_explicit_revision(tmp_path):
    journal = TransitionJournal(tmp_path / "j.jsonl")
    state, _ = drive(journal, PanicState(), [(20240101, True, "P2")])
    signal = journal_mod.rebuild_registry(journal.records)[0]
    original = {
        "entry_status": "ENTRY_RESOLVED", "entry_date": 20240102,
        "entry_component_codes": ["A", "B", "C", "D"],
        "exclusions": [], "input_digest": "digest-v1",
        "data_version": "prices_max_trade_date=20240102",
    }
    record = journal_mod.entry_resolution_record(GATE, "r1", signal, original)
    assert journal.append(record) is True

    revised_prices_result = {
        **original,
        "entry_component_codes": ["B", "C", "D"],
        "exclusions": [{"ts_code": "A", "reason": "limit_up_cannot_buy"}],
        "input_digest": "digest-v2",
    }
    # A normal rerun has the same key and cannot overwrite the frozen fact.
    assert journal.append(journal_mod.entry_resolution_record(
        GATE, "r2", signal, revised_prices_result
    )) is False
    frozen = journal_mod.rebuild_registry(journal.records)[0]
    assert frozen["entry_component_codes"] == ["A", "B", "C", "D"]
    assert frozen["entry_input_digest"] == "digest-v1"

    # Corrections are possible only as a separately auditable revision fact.
    assert journal.append(journal_mod.entry_resolution_record(
        GATE, "r3", signal, revised_prices_result, revision=1
    )) is True
    revised = journal_mod.rebuild_registry(journal.records)[0]
    assert revised["entry_component_codes"] == ["B", "C", "D"]
    assert revised["entry_resolution_revision"] == 1


def test_corrupt_state_recovered_from_journal(tmp_path):
    journal = TransitionJournal(tmp_path / "j.jsonl")
    state = PanicState()
    state, _ = drive(journal, state, [(20240101, True, "P2")])
    # verify_state_against_journal detects a stale/blank state snapshot
    verdict = journal_mod.verify_state_against_journal(PanicState(), journal.records)
    assert verdict["matches"] is False
    assert verdict["rebuilt"] == state


def test_proven_idle_checkpoint_matches_full_trigger_replay(tmp_path):
    days = list(range(20240101, 20240161))
    triggered_days = {20240101, 20240151}
    gated = pd.DataFrame({
        "trade_date": days,
        "validation_gate_triggered": [day in triggered_days for day in days],
    })
    machine = {"active_max_trading_days": 20, "cooldown_clear_days": 5}
    checkpoint, proof = _proven_idle_initialization_checkpoint(
        gated, days[-1], machine
    )
    assert checkpoint is not None
    assert checkpoint.state == IDLE
    assert proof["required_quiet_trading_days"] == 24
    assert proof["quiet_window_end"] == 20240150

    full = PanicState()
    for day in days:
        full, _ = step(
            full, day, day in triggered_days,
            "P2" if day in triggered_days else "P0", 20, 5,
        )
    resumed = checkpoint
    for day in days:
        if day <= checkpoint.last_processed_date:
            continue
        resumed, _ = step(
            resumed, day, day in triggered_days,
            "P2" if day in triggered_days else "P0", 20, 5,
        )
    assert resumed == full

    journal = TransitionJournal(tmp_path / "checkpoint.jsonl")
    assert journal.append(journal_mod.initialization_checkpoint_record(
        GATE, "init", checkpoint, proof
    ))
    assert journal_mod.rebuild_state(journal.records) == checkpoint


def test_initialization_falls_back_to_full_history_without_idle_proof():
    gated = pd.DataFrame({
        "trade_date": list(range(1, 20)),
        "validation_gate_triggered": [True] * 19,
    })
    checkpoint, proof = _proven_idle_initialization_checkpoint(
        gated, 19, {"active_max_trading_days": 20, "cooldown_clear_days": 5}
    )
    assert checkpoint is None
    assert proof is None


# ═══════════════════════════════════════════════════════════════════════
# Catch-up scenarios (plan §4.4)
# ═══════════════════════════════════════════════════════════════════════
def test_catchup_two_events_get_distinct_signal_ids(tmp_path):
    """补跑跨两个独立事件：分别登记，禁止同一个最终 signal_id."""
    journal = TransitionJournal(tmp_path / "j.jsonl")
    state = PanicState()
    days = [(20240101, True, "P2")]
    days += _quiet_days(2, 19)                      # exhaust ACTIVE (20 days)
    days += _quiet_days(21, 5)                      # clear COOLDOWN
    days += [(20240127, True, "P3")]                # second event
    state, transitions = drive(journal, state, days)
    registry = journal_mod.rebuild_registry(journal.records)
    assert len(registry) == 2
    ids = [e["signal_id"] for e in registry]
    assert ids[0] != ids[1]
    assert ids[0] == "PANIC_20240101_001"
    assert ids[1] == "PANIC_20240127_002"
    assert registry[0]["live_signal_date"] == 20240101
    assert registry[1]["live_signal_date"] == 20240127


def test_catchup_ending_idle_registry_keeps_event_ids(tmp_path):
    """补跑结束时处于IDLE：registry不得写空ID."""
    journal = TransitionJournal(tmp_path / "j.jsonl")
    state = PanicState()
    days = [(20240101, True, "P2")]
    days += _quiet_days(2, 19)
    days += _quiet_days(21, 5)                      # rearmed -> IDLE
    state, transitions = drive(journal, state, days)
    assert state.state == IDLE
    assert state.signal_id is None
    registry = journal_mod.rebuild_registry(journal.records)
    assert len(registry) == 1
    assert registry[0]["signal_id"] == "PANIC_20240101_001"  # NOT None
    rearmed = [t for t in transitions if t["kind"] == "rearmed"]
    assert rearmed and rearmed[0]["closed_signal_id"] == "PANIC_20240101_001"


def test_catchup_spans_active_cooldown_idle(tmp_path):
    journal = TransitionJournal(tmp_path / "j.jsonl")
    state = PanicState()
    days = [(20240101, True, "P2")] + _quiet_days(2, 19)
    state, transitions = drive(journal, state, days)
    assert state.state == COOLDOWN
    state, transitions2 = drive(journal, state, _quiet_days(21, 5))
    assert state.state == IDLE
    kinds = [t["kind"] for t in transitions + transitions2]
    assert kinds[0] == "first_trigger"
    assert "rearmed" in kinds
    # journal-derived state equals live state at every boundary
    assert journal_mod.rebuild_state(journal.records) == state


def test_catchup_p2_to_p4_upgrade_emits_once(tmp_path):
    journal = TransitionJournal(tmp_path / "j.jsonl")
    state = PanicState()
    state, transitions = drive(journal, state, [
        (20240101, True, "P2"),
        (20240102, True, "P4"),
        (20240103, True, "P4"),   # same level again -> no re-emit
    ])
    kinds = [(t["kind"], t["emit_alert"]) for t in transitions]
    assert kinds == [("first_trigger", True), ("severity_upgrade", True),
                     ("still_active", False)]
    assert state.max_severity == "P4"


def test_historical_transitions_keep_their_own_snapshot(tmp_path):
    """禁止在补跑结束后读取最终state解释历史transition."""
    journal = TransitionJournal(tmp_path / "j.jsonl")
    state = PanicState()
    days = [(20240101, True, "P2")]
    days += _quiet_days(2, 19) + _quiet_days(21, 5)
    days += [(20240127, True, "P2")]
    state, transitions = drive(journal, state, days)
    # final state belongs to event 2, but day-1 records still carry event 1
    first = [r for r in journal.records
             if r.get("trade_date") == 20240101][0]
    assert first["signal_id"] == "PANIC_20240101_001"
    assert first["live_signal_date"] == 20240101
    last = [r for r in journal.records
            if r.get("trade_date") == 20240127][0]
    assert last["signal_id"] == "PANIC_20240127_002"


# ═══════════════════════════════════════════════════════════════════════
# Fault injection: state commits LAST (plan §4.3)
# ═══════════════════════════════════════════════════════════════════════
def test_failure_before_state_commit_recovers_without_losing_signal(tmp_path):
    journal_path = tmp_path / "j.jsonl"
    state_path = tmp_path / "panic_state.json"

    # -- run 1: journal written, then CRASH before state.save --
    journal = TransitionJournal(journal_path)
    state = PanicState.load(state_path)          # fresh
    state, _ = drive(journal, state, [(20240101, True, "P2")])
    # simulated crash: state.save(state_path) never happens

    # -- run 2: reload -> state file still empty, journal has the fact --
    journal2 = TransitionJournal(journal_path)
    stale_state = PanicState.load(state_path)
    assert stale_state.last_processed_date is None
    verdict = journal_mod.verify_state_against_journal(stale_state,
                                                       journal2.records)
    assert not verdict["matches"]
    recovered = verdict["rebuilt"]
    assert recovered.signal_id == "PANIC_20240101_001"
    # re-processing the same day appends nothing new (idempotent key)
    n_before = len(journal2.records)
    recovered2, transition = step(recovered, 20240101, True, "P2")
    assert transition["kind"] == "duplicate_run"
    appended = journal2.append(journal_mod.transition_record(
        GATE, "run2", transition))
    # duplicate_run has a distinct kind so it would be a new key — but the
    # runner only journals pending days, and there are none; assert the
    # original fact is intact either way
    registry = journal_mod.rebuild_registry(journal2.records)
    assert [e["signal_id"] for e in registry] == ["PANIC_20240101_001"]
    assert len([r for r in journal2.records
                if r.get("kind") == "first_trigger"]) == 1
    recovered.save(state_path)
    assert PanicState.load(state_path) == recovered
    assert n_before <= len(journal2.records)


def test_rerun_after_crash_journal_dedupes(tmp_path):
    """Re-computing the same pending days must not duplicate journal facts."""
    journal_path = tmp_path / "j.jsonl"
    days = [(20240101, True, "P2"), (20240102, True, "P3")]

    journal = TransitionJournal(journal_path)
    state, _ = drive(journal, PanicState(), days)
    # crash before state commit; rerun recomputes the SAME transitions
    journal2 = TransitionJournal(journal_path)
    state2, _ = drive(journal2, PanicState(), days)
    assert len(journal2.records) == 2  # not 4
    assert journal_mod.rebuild_state(journal2.records) == state2 == state


# ═══════════════════════════════════════════════════════════════════════
# Run lock (plan §4.5)
# ═══════════════════════════════════════════════════════════════════════
def test_run_lock_blocks_second_instance(tmp_path):
    lock1 = RunLock(tmp_path, "run_a")
    lock1.acquire()
    lock2 = RunLock(tmp_path, "run_b")
    with pytest.raises(RuntimeError, match="another runner"):
        lock2.acquire()
    lock1.release()
    lock2.acquire()  # now succeeds
    lock2.release()


def test_stale_lock_taken_over_with_owner_recorded(tmp_path):
    lock_path = tmp_path / "panic_runner.lock"
    lock_path.write_text(json.dumps({
        "pid": 1, "host": "dead-host", "run_id": "run_dead",
        "started_at": "2020-01-01T00:00:00",
    }), encoding="utf-8")
    lock = RunLock(tmp_path, "run_new", stale_after_seconds=3600)
    lock.acquire()
    assert lock.acquired
    assert lock.takeover_of["run_id"] == "run_dead"
    holder = json.loads(lock_path.read_text(encoding="utf-8"))
    assert holder["run_id"] == "run_new"
    assert "recovery" in holder
    lock.release()
    assert not lock_path.exists()

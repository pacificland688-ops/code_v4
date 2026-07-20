"""Append-only transition journal — the system's source of truth.

panic_transition_journal.jsonl holds one record per (state-machine transition
| quality block | pipeline failure). Idempotency key:

    gate_version + trade_date + signal_id + transition_kind

The journal is append-only; duplicate keys are silently skipped so crash
re-runs converge. panic_state.json, signals_registry.json and
panic_alert_history.csv are all REBUILDABLE projections of this file.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd

from .state_machine import PanicState

JOURNAL_FILENAME = "panic_transition_journal.jsonl"

HISTORY_COLUMNS = [
    "signal_id", "run_id", "event_date", "data_as_of", "universe_version",
    "gate_version", "config_hash", "state_before", "state_after",
    "panic_level", "market_regime", "component_status", "alert_status",
    "transition", "emitted",
]


def idempotency_key(gate_version: str, trade_date: int | None,
                    signal_id: str | None, transition_kind: str) -> str:
    return f"{gate_version}|{trade_date}|{signal_id or 'none'}|{transition_kind}"


class TransitionJournal:
    """Append-only JSONL journal with idempotent appends and atomic flushes."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._keys: set[str] = set()
        self._records: list[dict] = []
        if self.path.exists():
            self._load()

    def _load(self) -> None:
        for line_no, line in enumerate(
            self.path.read_text(encoding="utf-8").splitlines(), 1
        ):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    f"journal corrupted at line {line_no}: {exc}"
                ) from exc
            self._records.append(record)
            self._keys.add(record["idempotency_key"])

    @property
    def records(self) -> list[dict]:
        return list(self._records)

    def has(self, key: str) -> bool:
        return key in self._keys

    def append(self, record: dict) -> bool:
        """Append one record; returns False (no-op) if the key already exists.

        The write is flush+fsync'd before returning: once append() returns
        True the fact is durable regardless of later pipeline failures.
        """
        key = record.get("idempotency_key")
        if not key:
            raise ValueError("journal record requires idempotency_key")
        if key in self._keys:
            return False
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, ensure_ascii=False, default=str)
        with open(self.path, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        self._records.append(record)
        self._keys.add(key)
        return True


def transition_record(gate_version: str, run_id: str, transition: dict,
                      extra: dict | None = None) -> dict:
    """Build a journal record from a state-machine transition snapshot."""
    record = {
        "idempotency_key": idempotency_key(
            gate_version, transition.get("trade_date"),
            transition.get("signal_id"), transition["kind"],
        ),
        "record_type": "transition",
        "gate_version": gate_version,
        "run_id": run_id,
        **{k: transition.get(k) for k in (
            "trade_date", "signal_id", "live_signal_date", "event_counter",
            "state_before", "state_after", "kind", "severity", "triggered",
            "is_new_event", "emit_alert", "active_days_elapsed",
            "cooldown_clear_count", "max_severity", "closed_signal_id",
        )},
    }
    if extra:
        record.update(extra)
    return record


def event_record(gate_version: str, run_id: str, trade_date: int | None,
                 kind: str, detail: dict | None = None) -> dict:
    """Non-transition fact (quality_blocked / pipeline_failure)."""
    return {
        "idempotency_key": idempotency_key(gate_version, trade_date, None, kind),
        "record_type": "event",
        "gate_version": gate_version,
        "run_id": run_id,
        "trade_date": trade_date,
        "kind": kind,
        "detail": detail or {},
    }


def entry_resolution_record(
    gate_version: str,
    run_id: str,
    signal: dict,
    resolution: dict,
    revision: int = 0,
) -> dict:
    """Build an append-only frozen entry-basket fact.

    Normal production resolution always uses revision zero.  Any later
    correction must be an explicitly numbered revision, leaving the original
    fact intact and auditable.
    """
    signal_id = str(signal["signal_id"])
    entry_date = resolution.get("entry_date")
    kind = "entry_resolved" if revision == 0 else f"entry_resolved_revision_{revision}"
    return {
        "idempotency_key": idempotency_key(
            gate_version, entry_date, signal_id, kind
        ),
        "record_type": "entry_resolution",
        "kind": kind,
        "gate_version": gate_version,
        "run_id": run_id,
        "signal_id": signal_id,
        "live_signal_date": signal.get("live_signal_date"),
        "entry_date": entry_date,
        "entry_status": resolution.get("entry_status"),
        "entry_component_codes": sorted(
            str(code) for code in resolution.get("entry_component_codes", [])
        ),
        "entry_exclusions": resolution.get("exclusions", []),
        "input_digest": resolution.get("input_digest"),
        "data_version": resolution.get("data_version"),
        "liquidity_policy": resolution.get("liquidity_policy"),
        "liquidity_checks": resolution.get("liquidity_checks") or [],
        "revision": int(revision),
    }


def initialization_checkpoint_record(
    gate_version: str,
    run_id: str,
    state: PanicState,
    proof: dict,
) -> dict:
    """Persist a proven-IDLE initialization boundary and its proof metadata."""
    trade_date = state.last_processed_date
    return {
        "idempotency_key": idempotency_key(
            gate_version, trade_date, None, "initialization_checkpoint"
        ),
        "record_type": "checkpoint",
        "kind": "initialization_checkpoint",
        "gate_version": gate_version,
        "run_id": run_id,
        "trade_date": trade_date,
        "state_snapshot": {
            field: getattr(state, field) for field in PanicState.__dataclass_fields__
        },
        "proof": proof,
    }


# ═══════════════════════════════════════════════════════════════════════
# Projections — state / registry / history are rebuilt from the journal
# ═══════════════════════════════════════════════════════════════════════
def _transitions(records: list[dict]) -> list[dict]:
    rows = [r for r in records if r.get("record_type") == "transition"]
    return sorted(rows, key=lambda r: (int(r["trade_date"]), r.get("event_counter") or 0))


def rebuild_state(records: list[dict]) -> PanicState:
    """Reconstruct PanicState from the last transition's embedded snapshot."""
    checkpoints = [r for r in records if r.get("record_type") == "checkpoint"]
    checkpoint = max(
        checkpoints, key=lambda r: int(r.get("trade_date") or 0), default=None
    )
    base = (
        PanicState(**checkpoint["state_snapshot"])
        if checkpoint is not None else PanicState()
    )
    transitions = [
        row for row in _transitions(records)
        if checkpoint is None
        or int(row["trade_date"]) > int(checkpoint.get("trade_date") or 0)
    ]
    if not transitions:
        return base
    last = transitions[-1]
    history_dates = [
        int(t["trade_date"]) for t in transitions
        if t.get("triggered")
        and t.get("signal_id") is not None
        and t.get("signal_id") == last.get("signal_id")
    ]
    return PanicState(
        state=str(last["state_after"]),
        live_signal_date=last.get("live_signal_date"),
        signal_id=last.get("signal_id"),
        active_days_elapsed=int(last.get("active_days_elapsed") or 0),
        cooldown_clear_count=int(last.get("cooldown_clear_count") or 0),
        max_severity=str(last.get("max_severity") or "P0"),
        last_processed_date=int(last["trade_date"]),
        event_counter=int(last.get("event_counter") or 0),
        history_dates=history_dates,
    )


def rebuild_registry(records: list[dict]) -> list[dict]:
    """One registry entry per first_trigger — each event keeps ITS OWN
    signal_id and member snapshot; a final IDLE state cannot blank them."""
    entries = []
    for record in _transitions(records):
        if record.get("is_new_event") and record.get("signal_id"):
            entries.append({
                "signal_id": record["signal_id"],
                "live_signal_date": record.get("live_signal_date"),
                "event_counter": record.get("event_counter"),
                "active_member_codes": record.get("active_member_codes") or [],
                "eligible_member_codes": record.get("eligible_member_codes") or [],
                "created_run_id": record.get("run_id"),
                "entry_status": "SIGNAL_REGISTERED",
            })
    by_signal = {entry["signal_id"]: entry for entry in entries}
    resolutions = sorted(
        (r for r in records if r.get("record_type") == "entry_resolution"),
        key=lambda r: (
            str(r.get("signal_id") or ""), int(r.get("revision") or 0)
        ),
    )
    for record in resolutions:
        entry = by_signal.get(record.get("signal_id"))
        if entry is None:
            continue
        entry.update({
            "entry_status": record.get("entry_status"),
            "entry_date": record.get("entry_date"),
            "entry_component_codes": record.get("entry_component_codes") or [],
            "entry_exclusions": record.get("entry_exclusions") or [],
            "entry_input_digest": record.get("input_digest"),
            "entry_data_version": record.get("data_version"),
            "entry_liquidity_policy": record.get("liquidity_policy"),
            "entry_liquidity_checks": record.get("liquidity_checks") or [],
            "entry_resolution_revision": int(record.get("revision") or 0),
            "entry_resolution_idempotency_key": record.get("idempotency_key"),
        })
    return entries


def rebuild_history(records: list[dict], default_as_of: int | None = None) -> pd.DataFrame:
    """panic_alert_history.csv as a deterministic projection of the journal."""
    rows = []
    for record in sorted(
        (r for r in records if r.get("record_type") in ("transition", "event")),
        key=lambda r: (int(r.get("trade_date") or 0),
                       0 if r.get("record_type") == "event" else 1,
                       r.get("event_counter") or 0),
    ):
        if record["record_type"] == "event":
            rows.append({
                "signal_id": None, "run_id": record.get("run_id"),
                "event_date": record.get("trade_date"),
                "data_as_of": record.get("detail", {}).get("as_of", default_as_of),
                "universe_version": record.get("detail", {}).get("universe_version"),
                "gate_version": record.get("gate_version"),
                "config_hash": record.get("detail", {}).get("config_hash"),
                "state_before": "-", "state_after": "-",
                "panic_level": "-",
                "market_regime": "-", "component_status": "-",
                "alert_status": record.get("kind", "").upper(),
                "transition": record.get("kind"), "emitted": True,
            })
        else:
            rows.append({
                "signal_id": record.get("signal_id"),
                "run_id": record.get("run_id"),
                "event_date": record.get("trade_date"),
                "data_as_of": record.get("data_as_of", default_as_of),
                "universe_version": record.get("universe_version"),
                "gate_version": record.get("gate_version"),
                "config_hash": record.get("config_hash"),
                "state_before": record.get("state_before"),
                "state_after": record.get("state_after"),
                "panic_level": record.get("severity"),
                "market_regime": record.get("market_regime"),
                "component_status": record.get("component_status"),
                "alert_status": record.get("alert_status"),
                "transition": record.get("kind"),
                "emitted": bool(record.get("emit_alert")),
            })
    return pd.DataFrame(rows, columns=HISTORY_COLUMNS)


def verify_state_against_journal(state: PanicState, records: list[dict]) -> dict:
    """Compare a loaded state snapshot with the journal-derived state.

    Used at startup: a corrupted/stale panic_state.json is rebuilt from the
    journal instead of trusted."""
    rebuilt = rebuild_state(records)
    matches = rebuilt == state
    return {
        "matches": matches,
        "rebuilt": rebuilt,
        "differences": {} if matches else {
            field: {"state_file": getattr(state, field),
                    "journal": getattr(rebuilt, field)}
            for field in PanicState.__dataclass_fields__
            if getattr(state, field) != getattr(rebuilt, field)
        },
    }

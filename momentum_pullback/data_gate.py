"""Consume one validated snapshot. A READY flag in a file is not the check."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from momentum_pullback.contracts import (
    CHECKPOINT_SCHEMA, LEGACY_CHECKPOINT_SCHEMAS, ROOT, Contract, GateError, checkpoint, file_hash, fingerprint, restore_checkpoint, write_json,
)
from momentum_pullback.data_adapter import input_history_hash, roster_history_hash
from momentum_pullback.event_engine import build_events
from momentum_pullback.features import build_features
from momentum_pullback.matching import lock_matches
from momentum_pullback.runtime import create_run, implementation_hash, verify_run_inputs
from momentum_pullback.snapshot import BuiltSnapshot, build_snapshot, read_snapshot
from momentum_pullback.source_bindings import INDEX_RELATIVE, SnapshotPolicy, SourcePackage, load_source_package, source_history_prefix

BINDING_SCHEMA = "momentum_pullback.snapshot_state_binding.v1"
VALIDATION_SCHEMA = "momentum_pullback.snapshot_validation.v1"
HAND_CASE_ID = "HAND-20x155"
HAND_ORACLE = ROOT / "momentum_pullback/fixtures/hand_expected.json"
CORE_KEYS = ("schema", "contract_hash", "code_hash", "feature_origin", "processed_cutoff", "consumed_history_hash", "consumed_roster_hash", "state_hash")
DAILY_TABLES = ("prices_raw", "prices_adj", "amount", "circ_mv", "halts")
EVENT_TABLES = ("membership", "st_status", "industry")


def load_checked_snapshot(manifest_path: Path, *, contract: Contract, policy: SnapshotPolicy, mode: str | None) -> BuiltSnapshot:
    """One reader for build, validate, and smoke. Mode is never inferred."""
    if mode not in {"SYNTHETIC", "REAL"}:
        raise GateError("SNAPSHOT_MODE_MISMATCH", "MODE_REQUIRED")
    return read_snapshot(manifest_path, contract=contract, policy=policy, mode=mode)


def build_checked_snapshot(manifest_path: Path, *, contract: Contract, policy: SnapshotPolicy, mode: str | None, root: Path = ROOT, oracle_files: list[Path] | None = None, offline: bool = False, outcomes_disabled: bool = False, before_commit: Callable[[Path], None] | None = None) -> BuiltSnapshot:
    """Build, then read the committed manifest back through the same checker."""
    if mode not in {"SYNTHETIC", "REAL"}:
        raise GateError("SNAPSHOT_MODE_MISMATCH", "MODE_REQUIRED")
    built = build_snapshot(manifest_path, contract=contract, policy=policy, mode=mode, root=root, oracle_files=oracle_files, before_commit=before_commit)
    checked = load_checked_snapshot(built.folder / "snapshot_manifest.json", contract=contract, policy=policy, mode=mode)
    _copy_source_bindings(checked)
    _write_policy_snapshot(checked.folder, policy)
    write_json(checked.folder / "command_constraints.json", {"offline": bool(offline), "outcomes_disabled_flag": bool(outcomes_disabled), "outcomes_enabled": False, "network_requests": 0, "parameter_status": "PROPOSED"})
    verify_run_inputs(json.loads((checked.folder / "run_manifest.json").read_text(encoding="utf-8")))
    _write_artifact_hashes(checked.folder)
    verify_run_inputs(json.loads((checked.folder / "run_manifest.json").read_text(encoding="utf-8")))
    return checked


def validate_snapshot(manifest_path: Path, *, contract: Contract, policy: SnapshotPolicy, mode: str | None, root: Path = ROOT, offline: bool = False, outcomes_disabled: bool = False) -> tuple[Path, dict]:
    """Record a separate validation run. Do not rewrite the snapshot gate report."""
    checked = load_checked_snapshot(manifest_path, contract=contract, policy=policy, mode=mode)
    snapshot_report = checked.folder / "data_gate_report.json"
    snapshot_manifest = checked.folder / "snapshot_manifest.json"
    report_hash = file_hash(snapshot_report)
    manifest_hash = file_hash(snapshot_manifest)
    package = _reload_package(checked, contract, policy)
    folder, run_manifest = create_run(contract, "validate_snapshot", _consumer_inputs(checked, package, policy, []), root=root, logical_inputs=_constraints(mode, checked, offline, outcomes_disabled, manifest_hash))
    _copy_source_bindings(checked, folder)
    _write_policy_snapshot(folder, policy)
    report = {
        "schema": VALIDATION_SCHEMA,
        "status": checked.gate["status"],
        "mode": checked.manifest["mode"],
        "quality_status": checked.manifest["quality_status"],
        "diagnostic_only": checked.manifest["diagnostic_only"],
        "integrity_status": "SEPARATE_VALIDATION_RUN",
        "checked_snapshot_manifest_sha256": manifest_hash,
        "snapshot_id": checked.manifest["snapshot_id"],
        "source_authority": checked.gate["source_authority"],
        "coverage_status": checked.gate["coverage_status"],
        "permitted_consumers": checked.gate["permitted_consumers"],
        "outcomes_enabled": False,
        "outcomes_generated": False,
        "network_requests": 0,
        "parameter_status": "PROPOSED",
        "offline": bool(offline),
        "outcomes_disabled_flag": bool(outcomes_disabled),
        "artifact_dir": str(folder),
        "snapshot_dir": str(checked.folder),
    }
    if report["status"] == "DATA_READY_FOR_ENGINEERING":
        raise GateError("REVIEW_RECEIPT_UNTRUSTED", "DATA_READY_FOR_ENGINEERING")
    write_json(folder / "validation_report.json", report)
    verify_run_inputs(run_manifest)
    _write_artifact_hashes(folder)
    verify_run_inputs(run_manifest)
    if file_hash(snapshot_report) != report_hash or file_hash(snapshot_manifest) != manifest_hash:
        raise GateError("SNAPSHOT_CONTENT_CHANGED", "VALIDATION_REWROTE_SNAPSHOT")
    if (checked.folder / "validation_report.json").exists():
        raise GateError("SNAPSHOT_CONTENT_CHANGED", "VALIDATION_REWROTE_SNAPSHOT")
    return folder, report


def run_snapshot_smoke(manifest_path: Path, *, contract: Contract, policy: SnapshotPolicy, mode: str | None, root: Path = ROOT, offline: bool = False, outcomes_disabled: bool = False, before_accept: Callable[[Path], None] | None = None) -> tuple[Path, dict]:
    """Drive the existing engine from the snapshot tables. Do not rebuild the panel."""
    checked = load_checked_snapshot(manifest_path, contract=contract, policy=policy, mode=mode)
    if checked.gate["status"] != "SYNTHETIC_SNAPSHOT_READY" or checked.manifest.get("diagnostic_only") is not False or "SYNTHETIC_ENGINEERING" not in checked.gate.get("permitted_consumers", []):
        return checked.folder, {
            "status": "SYNTHETIC_SNAPSHOT_PARTIAL",
            "data_status": checked.gate["status"],
            "event_status": None,
            "matching_status": None,
            "accepted": False,
            "diagnostic_only": True,
            "outcomes_enabled": False,
            "outcomes_generated": False,
            "network_requests": 0,
            "parameter_status": "PROPOSED",
            "artifact_dir": str(checked.folder),
            "snapshot_id": checked.manifest.get("snapshot_id"),
        }
    package = _reload_package(checked, contract, policy)
    panel = checked.panel
    roster = checked.roster
    calendar = [int(value) for value in checked.calendar["trade_date"].tolist()]
    features = build_features(panel, calendar, contract, roster=roster)
    full = build_events(features, contract)
    paired = lock_matches(full["events"], features, full["observations"], contract)
    case_id = str(package.manifest.get("case_id"))
    oracle = HAND_ORACLE if case_id == HAND_CASE_ID else None
    if oracle is not None:
        _assert_hand_oracle(full, paired, oracle)
    cutoff = _resume_cutoff(calendar, contract)
    prefix = build_features(panel.loc[panel.trade_date.le(cutoff)].copy(), calendar, contract, roster=roster, return_states=True)
    early = build_events(prefix["features"], contract)
    saved = checkpoint({"event_states": early["states"], "feature_states": prefix["states"]}, contract=contract, code_hash=implementation_hash(), feature_origin=calendar[0], processed_cutoff=cutoff, history_hash=input_history_hash(panel, calendar, cutoff, roster), roster_hash=roster_history_hash(roster, cutoff))
    binding = make_snapshot_binding(checked, saved, contract=contract, policy=policy)
    state = resume_bound_state(checked, saved, binding, contract=contract, policy=policy)
    resumed_features = build_features(panel.loc[panel.trade_date.gt(cutoff)].copy(), calendar, contract, roster=roster, states=state["feature_states"])
    _assert_replay(features.loc[features.trade_date.gt(cutoff)], resumed_features)
    resumed = build_events(resumed_features, contract, states=state["event_states"])
    _assert_replay(full["events"], resumed["events"])
    if full["states"] != resumed["states"]:
        raise GateError("SEGMENTED_STATE_MISMATCH")
    resumed_pairs = lock_matches(resumed["events"], features, resumed["observations"], contract)
    _assert_replay(paired["matches"], resumed_pairs["matches"])
    status = _engineering_status(case_id, full, paired)
    if status == "DATA_READY_FOR_ENGINEERING":
        raise GateError("REVIEW_RECEIPT_UNTRUSTED", "DATA_READY_FOR_ENGINEERING")
    folder = None
    try:
        extra = [oracle] if oracle is not None else []
        folder, run_manifest = create_run(contract, "snapshot_smoke", _consumer_inputs(checked, package, policy, extra), root=root, logical_inputs=_constraints(mode, checked, offline, outcomes_disabled, file_hash(checked.folder / "snapshot_manifest.json")))
        _copy_source_bindings(checked, folder)
        _write_policy_snapshot(folder, policy)
        if before_accept is not None:
            before_accept(folder)
        verify_run_inputs(run_manifest)
        features.to_parquet(folder / "features.parquet", index=False)
        for name in ("events", "roots", "observations"):
            full[name].to_parquet(folder / f"{name}.parquet", index=False)
        paired["matches"].to_parquet(folder / "matching_matches.parquet", index=False)
        paired["failures"].to_parquet(folder / "matching_failures.parquet", index=False)
        write_json(folder / "checkpoint.json", saved)
        write_json(folder / "snapshot_state_binding.json", binding)
        summary = {
            "status": status,
            "data_status": "SYNTHETIC_SNAPSHOT_READY",
            "event_status": full["status"],
            "matching_status": paired["status"],
            "authority": "SYNTHETIC_ONLY_NOT_MARKET_EVIDENCE",
            "case_id": case_id,
            "events": int(len(full["events"])),
            "roots": int(len(full["roots"])),
            "controls": int(len(paired["matches"])),
            "coverage": paired["coverage"],
            "unknown_identity_rows": int(full["unknown_identity_rows"]),
            "failure_reasons": sorted(set(paired["failures"]["reason"].astype(str))) if not paired["failures"].empty else [],
            "snapshot_prefix_replay": "PASS",
            "processed_cutoff": cutoff,
            "snapshot_id": checked.manifest["snapshot_id"],
            "snapshot_dir": str(checked.folder),
            "outcomes_enabled": False,
            "outcomes_generated": False,
            "network_requests": 0,
            "parameter_status": "PROPOSED",
            "offline": bool(offline),
            "outcomes_disabled_flag": bool(outcomes_disabled),
            "run_id": run_manifest["run_id"],
            "artifact_dir": str(folder),
        }
        if cutoff == 20171229:
            summary["december_to_january_checkpoint"] = "PASS"
        if oracle is not None:
            summary["hand_event_oracle"] = "PASS"
            summary["hand_match_oracle"] = "PASS"
        write_json(folder / "data_gate_report.json", {"schema": "momentum_pullback.data_gate_report.v1", "status": status, "data_status": "SYNTHETIC_SNAPSHOT_READY", "event_status": full["status"], "matching_status": paired["status"], "mode": "SYNTHETIC", "integrity_status": "VALIDATED_SNAPSHOT_CONSUMER", "source_authority": checked.gate["source_authority"], "coverage_status": checked.gate["coverage_status"], "checked_snapshot_manifest_sha256": file_hash(checked.folder / "snapshot_manifest.json"), "outcomes_enabled": False, "network_requests": 0, "parameter_status": "PROPOSED"})
        write_json(folder / "acceptance_summary.json", summary)
        verify_run_inputs(run_manifest)
        _write_artifact_hashes(folder)
        verify_run_inputs(run_manifest)
        return folder, summary
    except GateError as error:
        if folder is not None and not (folder / "acceptance_summary.json").exists():
            details = error.details if isinstance(error.details, dict) else {"details": error.details}
            write_json(folder / "blocked.json", {"status": "BLOCKED", "reason": error.code, "details": details, "outcomes_generated": False, "outcomes_enabled": False, "network_requests": 0})
        wrapped = error.details if isinstance(error.details, dict) else {"details": error.details}
        raise GateError(error.code, {**wrapped, "artifact_dir": None if folder is None else str(folder)}) from error


def make_snapshot_binding(checked: BuiltSnapshot, saved: dict[str, Any], *, contract: Contract, policy: SnapshotPolicy) -> dict[str, Any]:
    """Bind the consumed prefix. An old implementation cannot receive a current binding."""
    _require_current_checkpoint(saved)
    current = implementation_hash()
    if saved.get("code_hash") != current:
        raise GateError("CHECKPOINT_IDENTITY_MISMATCH", "code_hash")
    cutoff = int(saved["processed_cutoff"])
    identity = prefix_identity(checked, contract=contract, policy=policy, cutoff=cutoff)
    if saved.get("contract_hash") != contract.hash or saved.get("consumed_history_hash") != identity["normalized_history_hash"] or saved.get("consumed_roster_hash") != identity["roster_history_hash"]:
        raise GateError("SNAPSHOT_PREFIX_MISMATCH", "CHECKPOINT_FIELDS")
    return {
        "schema": BINDING_SCHEMA,
        "checkpoint_core_hash": _checkpoint_core_hash(saved),
        "contract_hash": contract.hash,
        "code_hash": current,
        "processed_cutoff": cutoff,
        "snapshot_policy_hash": identity["snapshot_policy_hash"],
        "source_prefix": identity["source_prefix"],
        "normalized_history_hash": identity["normalized_history_hash"],
        "roster_history_hash": identity["roster_history_hash"],
        "calendar_prefix": identity["calendar_prefix"],
        "approved_source_range_prefix": identity["approved_source_range_prefix"],
        "snapshot_id": checked.manifest["snapshot_id"],
    }


def resume_bound_state(checked: BuiltSnapshot, saved: dict[str, Any], binding: dict[str, Any] | None, *, contract: Contract, policy: SnapshotPolicy) -> dict[str, Any]:
    """Validate the snapshot, the prefix, then the binding, and only then restore."""
    if not isinstance(binding, dict) or binding.get("schema") != BINDING_SCHEMA:
        raise GateError("SNAPSHOT_STATE_BINDING_MISSING", None if not isinstance(binding, dict) else binding.get("schema"))
    if isinstance(saved, dict) and saved.get("schema") in LEGACY_CHECKPOINT_SCHEMAS:
        raise GateError("CHECKPOINT_NOT_UPGRADABLE", saved.get("schema"))
    _require_current_checkpoint(saved)
    if not isinstance(binding.get("processed_cutoff"), int):
        raise GateError("SNAPSHOT_STATE_BINDING_MISSING", "CUTOFF")
    cutoff = int(binding["processed_cutoff"])
    identity = prefix_identity(checked, contract=contract, policy=policy, cutoff=cutoff)
    if binding.get("snapshot_policy_hash") != identity["snapshot_policy_hash"]:
        raise GateError("SNAPSHOT_PREFIX_MISMATCH", "POLICY")
    for key in ("source_prefix", "normalized_history_hash", "roster_history_hash", "calendar_prefix", "approved_source_range_prefix"):
        if binding.get(key) != identity[key]:
            raise GateError("SNAPSHOT_PREFIX_MISMATCH", key.upper())
    if binding.get("checkpoint_core_hash") != _checkpoint_core_hash(saved):
        raise GateError("SNAPSHOT_PREFIX_MISMATCH", "CHECKPOINT_CORE")
    if binding.get("contract_hash") != contract.hash or binding.get("code_hash") != saved.get("code_hash"):
        raise GateError("SNAPSHOT_PREFIX_MISMATCH", "CONTRACT_OR_CODE")
    current = implementation_hash()
    if saved.get("code_hash") != current:
        raise GateError("CHECKPOINT_IDENTITY_MISMATCH", "code_hash")
    if int(saved.get("processed_cutoff")) != cutoff:
        raise GateError("SNAPSHOT_PREFIX_MISMATCH", "CUTOFF")
    return restore_checkpoint(saved, contract=contract, code_hash=current, feature_origin=int(saved["feature_origin"]), processed_cutoff=cutoff, history_hash=identity["normalized_history_hash"], roster_hash=identity["roster_history_hash"])


def prefix_identity(checked: BuiltSnapshot, *, contract: Contract, policy: SnapshotPolicy, cutoff: int) -> dict[str, Any]:
    package = _reload_package(checked, contract, policy)
    calendar = [int(value) for value in checked.calendar["trade_date"].tolist()]
    if cutoff not in calendar:
        raise GateError("SNAPSHOT_PREFIX_MISMATCH", {"reason": "CUTOFF_NOT_IN_CALENDAR", "processed_cutoff": int(cutoff)})
    return {
        "source_prefix": _source_prefix(package, checked.roster, calendar, cutoff),
        "normalized_history_hash": input_history_hash(checked.panel, calendar, cutoff, checked.roster),
        "roster_history_hash": roster_history_hash(checked.roster, cutoff),
        "calendar_prefix": [date for date in calendar if date <= cutoff],
        "approved_source_range_prefix": _approved_range(package, checked.roster, cutoff),
        "snapshot_policy_hash": policy.file_hash,
    }


def _assert_replay(left: pd.DataFrame, right: pd.DataFrame) -> None:
    """A suffix rebuilt from a checkpoint must match the full replay values."""
    pd.testing.assert_frame_equal(left.reset_index(drop=True), right.reset_index(drop=True), check_dtype=False)


def _engineering_status(case_id: str, full: dict, paired: dict) -> str:
    if case_id == HAND_CASE_ID:
        return "SYNTHETIC_ENGINEERING_PASS"
    if full["status"] == "EVALUATED_ZERO_EVENTS":
        return "EVALUATED_ZERO_EVENTS"
    if full["status"] == "PARTIAL_IDENTITY_UNEVALUABLE":
        return "PARTIAL_IDENTITY_UNEVALUABLE"
    if paired["status"] == "MATCHING_UNEVALUABLE":
        return "MATCHING_UNEVALUABLE"
    return str(full["status"])


def _plain(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if hasattr(value, "item") and not isinstance(value, (str, bytes)):
        try:
            return _plain(value.item())
        except (ValueError, AttributeError):
            return str(value)
    return value


def _assert_hand_oracle(full: dict, paired: dict, oracle_path: Path) -> None:
    expected = json.loads(oracle_path.read_text(encoding="utf-8"))
    events = full["events"]
    actual = _plain(events[list(expected["events"][0])].to_dict("records"))
    if actual != expected["events"] or len(full["roots"]) != expected["roots"] or full["status"] != "EVENTS_BUILT":
        raise GateError("HAND_EVENT_ORACLE_MISMATCH", actual)
    if paired["matches"].empty:
        raise GateError("HAND_MATCH_ORACLE_MISMATCH", "NO_MATCHES")
    for event_id, cohort in paired["matches"].groupby("event_id", sort=False):
        if cohort.control_code.tolist() != expected["controls_each_event"] or not cohort.distance.eq(expected["control_distance"]).all():
            raise GateError("HAND_MATCH_ORACLE_MISMATCH", str(event_id))
    if paired["coverage"] != {"candidate_events": 2, "matched_events": 2, "failed_events": 0} or len(paired["matches"]) != 6:
        raise GateError("HAND_MATCH_COVERAGE_MISMATCH", paired["coverage"])


def _resume_cutoff(calendar: list[int], contract: Contract) -> int:
    start = int(contract.section("scope")["output_start"])
    prior = [date for date in calendar if date < start]
    if not prior:
        raise GateError("SNAPSHOT_STATE_BINDING_MISSING", "NO_PREFIX_DATE")
    return prior[-1]


def _require_current_checkpoint(saved: dict[str, Any]) -> None:
    if not isinstance(saved, dict) or saved.get("schema") != CHECKPOINT_SCHEMA:
        raise GateError("SNAPSHOT_STATE_BINDING_MISSING", saved.get("schema") if isinstance(saved, dict) else "CHECKPOINT")
    if any(key not in saved for key in CORE_KEYS):
        raise GateError("SNAPSHOT_STATE_BINDING_MISSING", "CHECKPOINT_CORE")


def _checkpoint_core_hash(saved: dict[str, Any]) -> str:
    _require_current_checkpoint(saved)
    return fingerprint({key: saved[key] for key in CORE_KEYS})


def _constraints(mode: str | None, checked: BuiltSnapshot, offline: bool, outcomes_disabled: bool, manifest_hash: str) -> dict[str, Any]:
    return {
        "mode": mode,
        "schema": checked.manifest.get("schema"),
        "snapshot_id": checked.manifest.get("snapshot_id"),
        "consumed_calendar": [int(value) for value in checked.calendar["trade_date"].tolist()],
        "source_manifest_sha256": checked.manifest.get("source_manifest_sha256"),
        "review_receipt_sha256": checked.manifest.get("review_receipt_sha256"),
        "checked_snapshot_manifest_sha256": manifest_hash,
        "offline": bool(offline),
        "outcomes_disabled_flag": bool(outcomes_disabled),
        "outcomes_enabled": False,
        "network_requests": 0,
    }


def _reload_package(checked: BuiltSnapshot, contract: Contract, policy: SnapshotPolicy) -> SourcePackage:
    source = Path(checked.manifest["source_manifest_path"])
    if not source.is_file() or file_hash(source) != checked.manifest["source_manifest_sha256"]:
        raise GateError("SNAPSHOT_CONTENT_CHANGED", "SOURCE_MANIFEST")
    return load_source_package(source, policy=policy, contract=contract, allowed_roots=[source.parent.resolve()])


def _consumer_inputs(checked: BuiltSnapshot, package: SourcePackage, policy: SnapshotPolicy, extra: list[Path]) -> list[Path]:
    source = Path(checked.manifest["source_manifest_path"])
    files = [checked.folder / "snapshot_manifest.json", source, package.input_root / package.manifest["review_receipt_ref"], Path(policy.source_path), ROOT / policy.payload["documents"][0]["path"], ROOT / INDEX_RELATIVE]
    files.extend(package.input_root / spec["relative_path"] for spec in package.manifest["tables"])
    files.extend(extra)
    return files


def _copy_source_bindings(checked: BuiltSnapshot, folder: Path | None = None) -> None:
    target_root = checked.folder if folder is None else folder
    source = Path(checked.manifest["source_manifest_path"])
    package_root = source.parent
    receipt_name = json.loads(source.read_text(encoding="utf-8"))["review_receipt_ref"]
    _copy_bytes(source, target_root / "source_manifest.json")
    _copy_bytes(package_root / receipt_name, target_root / "source_review_receipt.json")


def _copy_bytes(source: Path, target: Path) -> None:
    payload = source.read_bytes()
    if target.exists():
        if target.read_bytes() != payload:
            raise GateError("ARTIFACT_ALREADY_EXISTS", target.name)
        return
    target.write_bytes(payload)


def _write_policy_snapshot(folder: Path, policy: SnapshotPolicy) -> None:
    write_json(folder / "snapshot_policy_snapshot.json", {"snapshot_policy_hash": policy.file_hash, "source_definition_sha256": policy.document_hash, "parameter_status": "PROPOSED", "outcomes_enabled": False})


def _write_artifact_hashes(folder: Path) -> None:
    rows = [{"path": path.name, "sha256": file_hash(path)} for path in sorted(folder.iterdir()) if path.is_file() and path.name != "artifact_hashes.json"]
    write_json(folder / "artifact_hashes.json", rows)


def _empty_daily() -> pd.DataFrame:
    return pd.DataFrame(columns=["ts_code", "trade_date", "revision_id"])


def _empty_events() -> pd.DataFrame:
    return pd.DataFrame(columns=["available_at", "effective_from", "ts_code"])


def _source_prefix(package: SourcePackage, roster: pd.DataFrame, calendar: list[int], cutoff: int) -> str:
    parts: dict[str, Any] = {}
    empty_events = _empty_events()
    empty_daily = _empty_daily()
    for name in DAILY_TABLES:
        frame = package.tables.get(name)
        daily = empty_daily if frame is None or frame.empty or "trade_date" not in frame.columns else frame
        parts[name] = source_history_prefix(daily, empty_events, calendar, roster, cutoff)
    for name in EVENT_TABLES:
        frame = package.tables.get(name)
        events = empty_events if frame is None or frame.empty else frame
        parts[name] = source_history_prefix(empty_daily, events, calendar, roster, cutoff)
    lifecycle = package.tables.get("lifecycle")
    if lifecycle is None or lifecycle.empty:
        parts["lifecycle"] = []
    else:
        ordered = lifecycle.sort_values(["ts_code"], kind="stable") if "ts_code" in lifecycle.columns else lifecycle
        parts["lifecycle"] = json.loads(ordered.to_json(orient="records", double_precision=15))
    return fingerprint(parts)


def _approved_range(package: SourcePackage, roster: pd.DataFrame, cutoff: int) -> str:
    calendar = [int(date) for date in package.manifest["calendar_dates"] if int(date) <= cutoff]
    consumed = roster.loc[roster["trade_date"].le(cutoff), "ts_code"].astype(str)
    return fingerprint({"calendar_prefix": calendar, "roster_codes": sorted(set(consumed))})

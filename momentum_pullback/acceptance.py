"""A positive, independent hand oracle plus segmented replay acceptance."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from momentum_pullback.casebook import declare_synthetic_roster, hand_contract, hand_panel
from momentum_pullback.contracts import ROOT, Contract, GateError, checkpoint, file_hash, restore_checkpoint, write_json
from momentum_pullback.data_adapter import frame_hash, input_history_hash, roster_history_hash
from momentum_pullback.event_engine import build_events
from momentum_pullback.features import build_features
from momentum_pullback.matching import lock_matches
from momentum_pullback.runtime import create_run, verify_run_inputs


def run_hand_acceptance(contract: Contract, *, root: Path = ROOT) -> tuple[Path, dict]:
    draft = hand_contract(contract)
    panel, calendar = hand_panel()
    oracle_path = ROOT / "momentum_pullback/fixtures/hand_expected.json"
    expected = json.loads(oracle_path.read_text(encoding="utf-8"))
    inputs = [oracle_path] + ([Path(contract.source_path)] if contract.source_path else [])
    folder, manifest = create_run(draft, "hand_acceptance", inputs, root=root, logical_inputs={"normalized_panel_hash": frame_hash(panel), "calendar": calendar, "parent_contract_hash": contract.hash, "synthetic": True})
    roster = declare_synthetic_roster(panel)
    features = build_features(panel, calendar, draft, roster=roster)
    full = build_events(features, draft)
    events = full["events"]
    actual = events[list(expected["events"][0])].to_dict("records")
    if actual != expected["events"] or len(full["roots"]) != expected["roots"] or full["status"] != "EVENTS_BUILT":
        raise GateError("HAND_EVENT_ORACLE_MISMATCH", actual)
    prefix_feature_result = build_features(panel[panel.trade_date.le(20171229)], calendar, draft, roster=roster, return_states=True)
    prefix = prefix_feature_result["features"]
    early = build_events(prefix, draft)
    consumed = input_history_hash(panel, calendar, 20171229, roster)
    roster_hash = roster_history_hash(roster, 20171229)
    saved = checkpoint({"event_states": early["states"], "feature_states": prefix_feature_result["states"]}, contract=draft, code_hash=manifest["code_hash"], feature_origin=calendar[0], processed_cutoff=20171229, history_hash=consumed, roster_hash=roster_hash)
    state = restore_checkpoint(saved, contract=draft, code_hash=manifest["code_hash"], feature_origin=calendar[0], processed_cutoff=20171229, history_hash=input_history_hash(panel, calendar, 20171229, roster), roster_hash=roster_hash)
    resumed_features = build_features(panel[panel.trade_date.gt(20171229)], calendar, draft, roster=roster, states=state["feature_states"])
    pd.testing.assert_frame_equal(features[features.trade_date.gt(20171229)].reset_index(drop=True), resumed_features)
    resumed = build_events(resumed_features, draft, states=state["event_states"])
    pd.testing.assert_frame_equal(events, resumed["events"])
    if full["states"] != resumed["states"]:
        raise GateError("SEGMENTED_STATE_MISMATCH")
    paired = lock_matches(events, features, full["observations"], draft)
    for event_id, cohort in paired["matches"].groupby("event_id", sort=False):
        if cohort.control_code.tolist() != expected["controls_each_event"] or not cohort.distance.eq(expected["control_distance"]).all():
            raise GateError("HAND_MATCH_ORACLE_MISMATCH", event_id)
    if paired["coverage"] != {"candidate_events": 2, "matched_events": 2, "failed_events": 0}:
        raise GateError("HAND_MATCH_COVERAGE_MISMATCH")
    verify_run_inputs(manifest)
    panel.to_parquet(folder / "synthetic_input.parquet", index=False)
    features.to_parquet(folder / "features.parquet", index=False)
    for name in ["events", "roots", "breakouts", "observations", "transitions"]:
        full[name].to_parquet(folder / (name + ".parquet"), index=False)
    for name in ["matches", "failures", "reuse", "balance"]:
        paired[name].to_parquet(folder / ("matching_" + name + ".parquet"), index=False)
    write_json(folder / "checkpoint.json", saved)
    summary = {"status": "HAND_ENGINEERING_ACCEPTED", "authority": "SYNTHETIC_ONLY_NOT_MARKET_EVIDENCE", "event_status": full["status"], "matching_status": paired["status"], "events": len(events), "roots": len(full["roots"]), "controls": len(paired["matches"]), "coverage": paired["coverage"], "hand_event_oracle": "PASS", "hand_match_oracle": "PASS", "december_to_january_checkpoint": "PASS", "unknown_identity_rows": full["unknown_identity_rows"], "outcomes_generated": False, "network_requests": 0, "run_id": manifest["run_id"]}
    write_json(folder / "acceptance_summary.json", summary)
    write_json(folder / "artifacts.json", [{"path": path.name, "sha256": file_hash(path)} for path in sorted(folder.iterdir()) if path.is_file()])
    verify_run_inputs(manifest)
    return folder, summary


def run_snapshot_acceptance(manifest_path: Path, contract: Contract, *, policy, mode: str, root: Path = ROOT, offline: bool = False, outcomes_disabled: bool = False, before_accept=None, before_compute=None, before_final_commit=None) -> tuple[Path, dict]:
    """Read a validated snapshot and drive the existing engine. The hand panel is not rebuilt."""
    from momentum_pullback.data_gate import run_snapshot_smoke

    return run_snapshot_smoke(manifest_path, contract=contract, policy=policy, mode=mode, root=root, offline=offline, outcomes_disabled=outcomes_disabled, before_accept=before_accept, before_compute=before_compute, before_final_commit=before_final_commit)

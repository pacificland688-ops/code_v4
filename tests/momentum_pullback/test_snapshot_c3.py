"""Counterexamples for frozen inputs and the last-published acceptance marker."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pandas as pd
import pytest
import yaml

from momentum_pullback.contracts import ROOT, GateError, load_contract
from momentum_pullback.data_gate import (
    build_checked_snapshot, read_committed_acceptance, run_snapshot_smoke, validate_snapshot,
)
from momentum_pullback.runtime import create_run
from momentum_pullback.source_bindings import load_snapshot_policy
from scripts import run_momentum_pullback
from tests.momentum_pullback.snapshot_sources import commit_tables, flat_package, hand_tables, narrow_contract
from momentum_pullback.casebook import hand_contract

POLICY_PATH = ROOT / "configs/momentum_pullback/snapshot_policy_v0_1.yaml"
DATES = [20180102, 20180103, 20180104]
COMPARED = ("features.parquet", "events.parquet", "roots.parquet", "observations.parquet", "matching_matches.parquet")


@pytest.fixture(scope="module")
def policy():
    return load_snapshot_policy(POLICY_PATH)


@pytest.fixture(scope="module")
def parent():
    return load_contract(ROOT / "configs/momentum_pullback/research_contract_v0_2.yaml")


def _ready(tmp_path, policy, parent, case_id="C3"):
    contract = narrow_contract(parent, DATES[0], DATES[-1], DATES[-1])
    tables = flat_package(DATES, ["X"], close=10.0, factor=2.0, amount=12.5, amount_unit="THOUSAND_CNY", circ=3.0, circ_unit="TEN_THOUSAND_CNY", industry_from=DATES[-1], circ_dates=[DATES[-1]])
    manifest = commit_tables(tmp_path / "src", tables, policy=policy, contract=contract, parent_hash=parent.hash, case_id=case_id, amount_unit="THOUSAND_CNY", circ_unit="TEN_THOUSAND_CNY")
    checked = build_checked_snapshot(manifest, contract=contract, policy=policy, mode="SYNTHETIC", root=tmp_path / "build")
    return manifest, contract, checked


def _directory_bytes(folder: Path) -> dict[str, bytes]:
    return {path.name: path.read_bytes() for path in folder.iterdir() if path.is_file()}


def _recorded(folder: Path, name: str) -> str:
    manifest = json.loads((folder / "run_manifest.json").read_text(encoding="utf-8"))
    target = name.lower()
    matches = [item["sha256"] for item in manifest["inputs"] if Path(item["path"]).name.lower() == target]
    assert len(matches) == 1
    return matches[0]


def _assert_rejected(folder: Path) -> None:
    assert folder is not None
    assert not (folder / "acceptance_summary.json").exists()
    assert not (folder / "acceptance_summary.pending.json").exists()
    blocked = json.loads((folder / "blocked.json").read_text(encoding="utf-8"))
    assert blocked["outcomes_generated"] is False
    assert blocked["status"] == "BLOCKED"
    with pytest.raises(GateError) as rejected:
        read_committed_acceptance(folder)
    assert rejected.value.code == "ACCEPTANCE_REVOKED"


def test_c3_01_source_mutation_before_compute_cannot_publish_old_features(tmp_path, policy, parent):
    manifest, contract, checked = _ready(tmp_path, policy, parent, "C3-01")
    circ = manifest.parent / "circ_mv.json"
    original = circ.read_bytes()

    def tamper(_folder):
        circ.write_bytes(original + b"\n")

    with pytest.raises(GateError) as caught:
        run_snapshot_smoke(checked.folder / "snapshot_manifest.json", contract=contract, policy=policy, mode="SYNTHETIC", root=tmp_path / "smoke", before_compute=tamper)
    assert caught.value.code == "INPUT_CONTENT_CHANGED_DURING_RUN"
    folder = Path(caught.value.details["artifact_dir"])
    assert not (folder / "features.parquet").exists()
    assert _recorded(folder, "circ_mv.json") == hashlib.sha256(original).hexdigest()
    assert circ.read_bytes() != original
    _assert_rejected(folder)


def test_c3_02_each_consumed_input_is_blocked_after_identity_is_fixed(tmp_path, policy, parent):
    manifest, contract, checked = _ready(tmp_path, policy, parent, "C3-02")
    targets = {
        "source_manifest": manifest,
        "source_table": manifest.parent / "prices_raw.json",
        "policy": Path(policy.source_path),
        "snapshot_artifact": checked.folder / "normalized_panel.parquet",
    }
    originals = {name: path.read_bytes() for name, path in targets.items()}
    try:
        for name, path in targets.items():
            def tamper(_folder, victim=path, payload=originals[name]):
                victim.write_bytes(payload + b"\n")

            with pytest.raises(GateError) as caught:
                run_snapshot_smoke(checked.folder / "snapshot_manifest.json", contract=contract, policy=policy, mode="SYNTHETIC", root=tmp_path / name, before_compute=tamper)
            assert caught.value.code == "INPUT_CONTENT_CHANGED_DURING_RUN"
            _assert_rejected(Path(caught.value.details["artifact_dir"]))
            path.write_bytes(originals[name])
        oracle = ROOT / "momentum_pullback/fixtures/hand_expected.json"
        oracle_bytes = oracle.read_bytes()
        tables, _dates = hand_tables(2.0)
        hand = hand_contract(parent)
        hand_manifest = commit_tables(tmp_path / "hand-src", tables, policy=policy, contract=hand, parent_hash=parent.hash, case_id="HAND-20x155")
        hand_checked = build_checked_snapshot(hand_manifest, contract=hand, policy=policy, mode="SYNTHETIC", root=tmp_path / "hand-build")

        def tamper_oracle(_folder):
            oracle.write_bytes(oracle_bytes + b"\n")

        with pytest.raises(GateError) as oracle_error:
            run_snapshot_smoke(hand_checked.folder / "snapshot_manifest.json", contract=hand, policy=policy, mode="SYNTHETIC", root=tmp_path / "oracle", before_compute=tamper_oracle)
        assert oracle_error.value.code == "INPUT_CONTENT_CHANGED_DURING_RUN"
        _assert_rejected(Path(oracle_error.value.details["artifact_dir"]))
    finally:
        for name, path in targets.items():
            path.write_bytes(originals[name])
        oracle = ROOT / "momentum_pullback/fixtures/hand_expected.json"
        if "oracle_bytes" in locals():
            oracle.write_bytes(oracle_bytes)


def test_c3_03_pending_summary_is_not_an_acceptance_marker(monkeypatch, tmp_path, policy, parent, capsys):
    manifest, contract, checked = _ready(tmp_path, policy, parent, "C3-03")
    source = manifest
    original = source.read_bytes()

    def tamper(_folder):
        source.write_bytes(original + b"\n")

    try:
        with pytest.raises(GateError) as caught:
            run_snapshot_smoke(checked.folder / "snapshot_manifest.json", contract=contract, policy=policy, mode="SYNTHETIC", root=tmp_path / "direct", before_final_commit=tamper)
        assert caught.value.code == "INPUT_CONTENT_CHANGED_DURING_RUN"
        _assert_rejected(Path(caught.value.details["artifact_dir"]))
        source.write_bytes(original)
        config = tmp_path / "contract.yaml"
        config.write_text(yaml.safe_dump(contract.payload, sort_keys=False), encoding="utf-8")

        def wrapped(manifest_path, **kwargs):
            kwargs["before_final_commit"] = tamper
            return run_snapshot_smoke(manifest_path, **kwargs)

        def redirected(bound_contract, phase, files, logical_inputs=None, **kwargs):
            del kwargs
            return create_run(bound_contract, phase, files, root=tmp_path / "cli-root", logical_inputs=logical_inputs)

        monkeypatch.setattr("momentum_pullback.data_gate.run_snapshot_smoke", wrapped)
        monkeypatch.setattr("momentum_pullback.snapshot.create_run", redirected)
        monkeypatch.setattr("momentum_pullback.data_gate.create_run", redirected)
        code = run_momentum_pullback.main(["engineering-smoke", "--config", str(config), "--policy", str(POLICY_PATH), "--mode", "SYNTHETIC", "--input-manifest", str(checked.folder / "snapshot_manifest.json")])
        assert code == 2
        payload = json.loads(capsys.readouterr().out)
        assert payload["reason"] == "INPUT_CONTENT_CHANGED_DURING_RUN"
        folders = list((tmp_path / "cli-root").rglob("blocked.json"))
        assert len(folders) == 1
        _assert_rejected(folders[0].parent)
    finally:
        source.write_bytes(original)


def test_c3_04_catchable_io_faults_publish_no_acceptance(monkeypatch, tmp_path, policy, parent):
    manifest, contract, checked = _ready(tmp_path, policy, parent, "C3-04")
    snapshot_before = _directory_bytes(checked.folder)
    first, summary = run_snapshot_smoke(checked.folder / "snapshot_manifest.json", contract=contract, policy=policy, mode="SYNTHETIC", root=tmp_path / "ok")
    assert summary["status"] in {"PARTIAL_IDENTITY_UNEVALUABLE", "EVALUATED_ZERO_EVENTS", "EVENTS_BUILT"}
    assert read_committed_acceptance(first)["artifact_hashes_sha256"]
    first_bytes = _directory_bytes(first)

    def outputs(*args, **kwargs):
        del args, kwargs
        raise OSError("outputs")

    monkeypatch.setattr(pd.DataFrame, "to_parquet", outputs)
    with pytest.raises(GateError) as output_error:
        run_snapshot_smoke(checked.folder / "snapshot_manifest.json", contract=contract, policy=policy, mode="SYNTHETIC", root=tmp_path / "outputs")
    assert output_error.value.code == "ACCEPTANCE_COMMIT_FAILED"
    assert output_error.value.details["stage"] == "OUTPUTS"
    _assert_rejected(Path(output_error.value.details["artifact_dir"]))
    monkeypatch.undo()

    def hash_index(_folder):
        raise OSError("index")

    monkeypatch.setattr("momentum_pullback.data_gate._write_artifact_hashes", hash_index)
    with pytest.raises(GateError) as index_error:
        run_snapshot_smoke(checked.folder / "snapshot_manifest.json", contract=contract, policy=policy, mode="SYNTHETIC", root=tmp_path / "index")
    assert index_error.value.details["stage"] == "HASH_INDEX"
    _assert_rejected(Path(index_error.value.details["artifact_dir"]))
    monkeypatch.undo()

    real_replace = os.replace

    def fail_replace(source, destination):
        if str(destination).endswith("acceptance_summary.json"):
            raise OSError("replace")
        return real_replace(source, destination)

    monkeypatch.setattr("momentum_pullback.data_gate.os.replace", fail_replace)
    with pytest.raises(GateError) as marker_error:
        run_snapshot_smoke(checked.folder / "snapshot_manifest.json", contract=contract, policy=policy, mode="SYNTHETIC", root=tmp_path / "marker")
    assert marker_error.value.details["stage"] == "ACCEPTANCE_MARKER"
    _assert_rejected(Path(marker_error.value.details["artifact_dir"]))
    monkeypatch.undo()

    assert _directory_bytes(checked.folder) == snapshot_before
    assert _directory_bytes(first) == first_bytes
    second, _summary = run_snapshot_smoke(checked.folder / "snapshot_manifest.json", contract=contract, policy=policy, mode="SYNTHETIC", root=tmp_path / "retry")
    assert second != first
    assert read_committed_acceptance(second)["status"] == summary["status"]


def test_c3_05_repeated_runs_match_on_consumed_tables(tmp_path, policy, parent):
    _manifest, contract, checked = _ready(tmp_path, policy, parent, "C3-05")
    left, left_summary = run_snapshot_smoke(checked.folder / "snapshot_manifest.json", contract=contract, policy=policy, mode="SYNTHETIC", root=tmp_path / "left")
    right, right_summary = run_snapshot_smoke(checked.folder / "snapshot_manifest.json", contract=contract, policy=policy, mode="SYNTHETIC", root=tmp_path / "right")
    assert left != right
    assert left_summary["run_id"] != right_summary["run_id"]
    names = {Path(item["path"]).name for item in json.loads((left / "run_manifest.json").read_text(encoding="utf-8"))["inputs"]}
    for required in ("normalized_panel.parquet", "universe_daily.parquet", "calendar.parquet", "lineage.parquet", "coverage_report.json", "data_gate_report.json", "snapshot_manifest.json", "source_manifest.json"):
        assert required in names
    for name in COMPARED:
        pd.testing.assert_frame_equal(pd.read_parquet(left / name), pd.read_parquet(right / name), check_dtype=False)
    assert read_committed_acceptance(left)["snapshot_id"] == read_committed_acceptance(right)["snapshot_id"]


def test_c3_06_validation_freezes_inputs_and_old_smoke_is_not_a_snapshot_gate(monkeypatch, tmp_path, policy, parent, capsys):
    _manifest, contract, checked = _ready(tmp_path, policy, parent, "C3-06")
    panel = checked.folder / "normalized_panel.parquet"
    manifest_bytes = (checked.folder / "snapshot_manifest.json").read_bytes()
    report_bytes = (checked.folder / "data_gate_report.json").read_bytes()

    def tamper(_folder):
        panel.write_bytes(panel.read_bytes() + b" ")

    with pytest.raises(GateError) as caught:
        validate_snapshot(checked.folder / "snapshot_manifest.json", contract=contract, policy=policy, mode="SYNTHETIC", root=tmp_path / "validate", before_reread=tamper)
    assert caught.value.code == "INPUT_CONTENT_CHANGED_DURING_RUN"
    assert (checked.folder / "snapshot_manifest.json").read_bytes() == manifest_bytes
    assert not (checked.folder / "validation_report.json").exists()
    panel.write_bytes(panel.read_bytes()[:-1])
    assert (checked.folder / "data_gate_report.json").read_bytes() == report_bytes

    def hand(bound):
        del bound
        return tmp_path / "hand", {"status": "HAND_ENGINEERING_ACCEPTED", "outcomes_generated": False, "outcomes_enabled": False}

    monkeypatch.setattr(run_momentum_pullback, "run_hand_acceptance", hand)
    monkeypatch.setattr(run_momentum_pullback, "run_snapshot_acceptance", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("snapshot smoke")))
    assert run_momentum_pullback.main(["engineering-smoke"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "HAND_ENGINEERING_ACCEPTED"

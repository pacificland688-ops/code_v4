"""CLI exits for the snapshot gate. Old commands stay on their existing paths."""
from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest
import yaml

from momentum_pullback.acceptance import run_snapshot_acceptance
from momentum_pullback.contracts import ROOT, load_contract
from momentum_pullback.runtime import create_run
from momentum_pullback.source_bindings import load_snapshot_policy
from scripts import run_momentum_pullback
from tests.momentum_pullback.snapshot_sources import commit_tables, flat_package

POLICY_PATH = ROOT / "configs/momentum_pullback/snapshot_policy_v0_1.yaml"
DATES = [20180102, 20180103, 20180104]


@pytest.fixture(scope="module")
def policy():
    return load_snapshot_policy(POLICY_PATH)


@pytest.fixture(scope="module")
def parent():
    return load_contract(ROOT / "configs/momentum_pullback/research_contract_v0_2.yaml")


def _redirect(monkeypatch, root: Path) -> None:
    def wrapped(contract, phase, files, logical_inputs=None, **kwargs):
        del kwargs
        return create_run(contract, phase, files, root=root, logical_inputs=logical_inputs)

    monkeypatch.setattr("momentum_pullback.snapshot.create_run", wrapped)
    monkeypatch.setattr("momentum_pullback.data_gate.create_run", wrapped)


def _write_contract(path: Path, parent, origin: int, start: int, end: int):
    payload = parent.payload
    payload["scope"] = {"purpose": "ENGINEERING_ONLY", "feature_origin": origin, "output_start": start, "output_end": end}
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return load_contract(path)


def _package(directory: Path, policy, contract, parent, case_id: str, **overrides) -> Path:
    tables = flat_package(DATES, ["X"], close=10.0, factor=2.0, amount=12.5, amount_unit="THOUSAND_CNY", circ=3.0, circ_unit="TEN_THOUSAND_CNY", industry_from=DATES[-1], circ_dates=[DATES[-1]])
    for name, rows in overrides.items():
        tables[name] = rows
    return commit_tables(directory, tables, policy=policy, contract=contract, parent_hash=parent.hash, case_id=case_id, amount_unit="THOUSAND_CNY", circ_unit="TEN_THOUSAND_CNY")


def test_new_acceptance_entry_does_not_rebuild_the_hand_panel():
    source = inspect.getsource(run_snapshot_acceptance)
    assert "hand_panel" not in source
    text = (ROOT / "momentum_pullback/data_gate.py").read_text(encoding="utf-8")
    assert "hand_panel" not in text
    assert "bdate_range" not in text
    assert "tushare" not in text
    assert "import requests" not in text


def test_snapshot_commands_require_an_explicit_mode(capsys):
    assert run_momentum_pullback.main(["build-snapshot", "--source-manifest", "missing.json"]) == 2
    response = json.loads(capsys.readouterr().out)
    assert response["reason"] == "SNAPSHOT_MODE_MISMATCH"
    assert response["outcomes_enabled"] is False
    assert run_momentum_pullback.main(["validate-snapshot", "--input-manifest", "missing.json"]) == 2
    assert json.loads(capsys.readouterr().out)["reason"] == "SNAPSHOT_MODE_MISMATCH"


def test_old_smoke_stays_on_the_hand_path_and_build_events_ignores_snapshots(monkeypatch, tmp_path, capsys):
    def hand(contract):
        del contract
        return tmp_path, {"status": "HAND_ENGINEERING_ACCEPTED", "outcomes_generated": False, "outcomes_enabled": False}

    monkeypatch.setattr(run_momentum_pullback, "run_hand_acceptance", hand)
    monkeypatch.setattr(run_momentum_pullback, "run_snapshot_acceptance", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("snapshot smoke")))
    assert run_momentum_pullback.main(["engineering-smoke"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "HAND_ENGINEERING_ACCEPTED"
    monkeypatch.setattr(run_momentum_pullback, "build_checked_snapshot", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("snapshot build")))
    monkeypatch.setattr(run_momentum_pullback, "local_audit_files", lambda *args: [])
    monkeypatch.setattr(run_momentum_pullback, "audit_local_prices", lambda *args: ({"status": "DATA_BLOCKED", "gates": [], "network_requests": 0}, []))
    monkeypatch.setattr(run_momentum_pullback, "create_run", lambda contract, phase, files: create_run(contract, phase, files, root=tmp_path))
    assert run_momentum_pullback.main(["build-events", "--mode", "SYNTHETIC", "--input-manifest", "ignored.json", "--offline", "--outcomes-disabled"]) == 2
    blocked = json.loads(capsys.readouterr().out)
    assert blocked["reason"] == "REAL_EVENT_DATA_GATE_BLOCKED"
    assert not list(tmp_path.rglob("events.parquet"))
    assert not list(tmp_path.rglob("matching_matches.parquet"))


def test_cli_ready_partial_and_real_exits(monkeypatch, tmp_path, policy, parent, capsys):
    _redirect(monkeypatch, tmp_path)
    config = _write_contract(tmp_path / "synthetic_contract.yaml", parent, DATES[0], DATES[-1], DATES[-1])
    manifest = _package(tmp_path / "ready-src", policy, config, parent, "B-CLI-READY")
    assert run_momentum_pullback.main(["build-snapshot", "--config", str(tmp_path / "synthetic_contract.yaml"), "--mode", "SYNTHETIC", "--source-manifest", str(manifest)]) == 0
    built = json.loads(capsys.readouterr().out)
    assert built["status"] == "SYNTHETIC_SNAPSHOT_READY"
    assert built["outcomes_enabled"] is False
    assert built["network_requests"] == 0
    assert built["diagnostic_only"] is False
    snapshot = Path(built["artifact_dir"]) / "snapshot_manifest.json"
    report_hash_before = (Path(built["artifact_dir"]) / "data_gate_report.json").read_bytes()
    assert run_momentum_pullback.main(["validate-snapshot", "--config", str(tmp_path / "synthetic_contract.yaml"), "--mode", "SYNTHETIC", "--input-manifest", str(snapshot), "--offline", "--outcomes-disabled"]) == 0
    validated = json.loads(capsys.readouterr().out)
    assert validated["status"] == "SYNTHETIC_SNAPSHOT_READY"
    assert validated["checked_snapshot_manifest_sha256"]
    assert (Path(built["artifact_dir"]) / "data_gate_report.json").read_bytes() == report_hash_before
    assert not (Path(built["artifact_dir"]) / "validation_report.json").exists()
    unknown = flat_package(DATES, ["X"], close=10.0, factor=2.0, amount=12.5, amount_unit="THOUSAND_CNY", circ=3.0, circ_unit="TEN_THOUSAND_CNY", industry_from=DATES[-1], circ_dates=[DATES[-1]], industry_status="UNKNOWN")
    partial_manifest = commit_tables(tmp_path / "partial-src", unknown, policy=policy, contract=config, parent_hash=parent.hash, case_id="B-CLI-PARTIAL", amount_unit="THOUSAND_CNY", circ_unit="TEN_THOUSAND_CNY")
    assert run_momentum_pullback.main(["build-snapshot", "--config", str(tmp_path / "synthetic_contract.yaml"), "--mode", "SYNTHETIC", "--source-manifest", str(partial_manifest), "--offline", "--outcomes-disabled"]) == 2
    partial = json.loads(capsys.readouterr().out)
    assert partial["status"] == "SYNTHETIC_SNAPSHOT_PARTIAL"
    assert partial["diagnostic_only"] is True
    assert partial["status"] != "DATA_READY_FOR_ENGINEERING"
    real_tables = flat_package(DATES, ["X"], close=10.0, factor=2.0, amount=12.5, amount_unit="THOUSAND_CNY", circ=3.0, circ_unit="TEN_THOUSAND_CNY", industry_from=DATES[-1], circ_dates=[DATES[-1]])
    real_manifest = commit_tables(tmp_path / "real-src", real_tables, policy=policy, contract=config, parent_hash=parent.hash, case_id="B-CLI-REAL", amount_unit="THOUSAND_CNY", circ_unit="TEN_THOUSAND_CNY", mode="REAL", review_kind="REAL_CERTIFIED", real_flag=True)
    assert run_momentum_pullback.main(["build-snapshot", "--config", str(tmp_path / "synthetic_contract.yaml"), "--mode", "REAL", "--source-manifest", str(real_manifest)]) == 2
    refused = json.loads(capsys.readouterr().out)
    assert refused["reason"] == "REVIEW_RECEIPT_UNTRUSTED"
    assert not list(tmp_path.rglob("events.parquet"))
    assert not list(tmp_path.rglob("matching_matches.parquet"))
    assert run_momentum_pullback.main(["engineering-smoke", "--config", str(tmp_path / "synthetic_contract.yaml"), "--mode", "SYNTHETIC", "--input-manifest", str(Path(partial["artifact_dir"]) / "snapshot_manifest.json")]) == 2
    smoke = json.loads(capsys.readouterr().out)
    assert smoke["status"] == "SYNTHETIC_SNAPSHOT_PARTIAL"
    assert smoke["outcomes_enabled"] is False
    assert not list(tmp_path.rglob("acceptance_summary.json"))

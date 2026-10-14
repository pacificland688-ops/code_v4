from __future__ import annotations

import json
import subprocess
import sys
import socket

import pandas as pd
import pytest

from momentum_pullback.contracts import ROOT, GateError
from momentum_pullback.data_adapter import audit_local_prices
from momentum_pullback.runtime import create_run
from scripts import run_momentum_pullback


def test_adversarial_local_cache_reports_failure_instead_of_empty_success(tmp_path):
    raw_dir = tmp_path / "data/parquet/prices_raw/year=2018/month=1"
    adj_dir = tmp_path / "data/parquet/prices_adj/year=2018/month=1"
    raw_dir.mkdir(parents=True)
    adj_dir.mkdir(parents=True)
    raw = pd.DataFrame({"ts_code": ["X"], "trade_date": [20180102], "open": [10.0], "high": [10.0], "low": [10.0], "close": [10.0], "vol": [1.0], "amount": [1.0]})
    adj = raw.rename(columns={column: "adj_" + column for column in ["open", "high", "low", "close"]})
    adj["adj_factor"] = None
    raw.to_parquet(raw_dir / "part-a.parquet", index=False)
    raw.to_parquet(raw_dir / "part-b.parquet", index=False)
    adj.to_parquet(adj_dir / "part-a.parquet", index=False)
    report, _ = audit_local_prices(tmp_path, 20180101, 20180330)
    assert report["status"] == "DATA_BLOCKED"
    assert report["real_event_generation"] == "NOT_PERMITTED"
    assert any(gate.get("reason") == "DUPLICATE_OR_CONFLICTING_KEYS" for gate in report["gates"])
    assert report["network_requests"] == 0


@pytest.mark.parametrize("command", ["conditional-study", "compare-policies", "portfolio-replay"])
def test_cli_refuses_all_outcome_work(command):
    process = subprocess.run([sys.executable, str(ROOT / "scripts/run_momentum_pullback.py"), command], capture_output=True, text=True, cwd=ROOT)
    assert process.returncode == 2
    response = json.loads(process.stdout)
    assert response["reason"] == "OUTCOMES_NOT_IMPLEMENTED_OR_AUTHORIZED"
    assert not response["outcomes_generated"]


def test_failed_gate_never_emits_real_events_or_matches(tmp_path, monkeypatch, capsys):
    def no_network(*args, **kwargs):
        raise AssertionError("Network is forbidden in first delivery")
    monkeypatch.setattr(socket.socket, "connect", no_network)
    monkeypatch.setattr(run_momentum_pullback, "local_audit_files", lambda *args: [])
    monkeypatch.setattr(run_momentum_pullback, "audit_local_prices", lambda *args: ({"status": "DATA_BLOCKED", "gates": [{"status": "FAIL", "reason": "UNVERIFIED_PIT"}], "network_requests": 0}, []))
    monkeypatch.setattr(run_momentum_pullback, "create_run", lambda contract, phase, files: create_run(contract, phase, files, root=tmp_path))
    assert run_momentum_pullback.main(["build-events", "--offline", "--outcomes-disabled"]) == 2
    response = json.loads(capsys.readouterr().out)
    assert response["reason"] == "REAL_EVENT_DATA_GATE_BLOCKED"
    assert list(tmp_path.rglob("blocked.json"))
    assert list(tmp_path.rglob("data_gate_report.json"))
    assert not list(tmp_path.rglob("*.parquet"))

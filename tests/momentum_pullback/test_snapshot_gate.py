"""Snapshot consumers: engine status, prefix resume, and the hand oracle."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pandas as pd
import pytest

from momentum_pullback.casebook import hand_contract
from momentum_pullback.contracts import ROOT, GateError, checkpoint, fingerprint, load_contract, restore_checkpoint
from momentum_pullback.data_adapter import input_history_hash, roster_history_hash
from momentum_pullback.data_gate import (
    build_checked_snapshot, load_checked_snapshot, make_snapshot_binding, prefix_identity, resume_bound_state, run_snapshot_smoke, validate_snapshot,
)
from momentum_pullback.event_engine import build_events
from momentum_pullback.features import build_features
from momentum_pullback.runtime import implementation_hash
from momentum_pullback.source_bindings import load_snapshot_policy
from tests.momentum_pullback.snapshot_sources import commit_tables, flat_package, hand_tables, narrow_contract

POLICY_PATH = ROOT / "configs/momentum_pullback/snapshot_policy_v0_1.yaml"
DATES = [20180102, 20180103, 20180104]


@pytest.fixture(scope="module")
def policy():
    return load_snapshot_policy(POLICY_PATH)


@pytest.fixture(scope="module")
def parent():
    return load_contract(ROOT / "configs/momentum_pullback/research_contract_v0_2.yaml")


def _tiny(directory: Path, policy, parent, case_id: str, **overrides):
    contract = narrow_contract(parent, DATES[0], DATES[-1], DATES[-1])
    tables = flat_package(DATES, ["X"], close=10.0, factor=2.0, amount=12.5, amount_unit="THOUSAND_CNY", circ=3.0, circ_unit="TEN_THOUSAND_CNY", industry_from=DATES[-1], circ_dates=[DATES[-1]])
    for name, rows in overrides.items():
        tables[name] = rows
    manifest = commit_tables(directory, tables, policy=policy, contract=contract, parent_hash=parent.hash, case_id=case_id, amount_unit="THOUSAND_CNY", circ_unit="TEN_THOUSAND_CNY")
    return manifest, contract


def _declared(periods: int, end: str) -> list[int]:
    return [int(value.strftime("%Y%m%d")) for value in pd.bdate_range(end=end, periods=periods)]


def _scale_rows(tables: dict, dates: list[int], close_at) -> None:
    for row in tables["prices_raw"]:
        price = close_at(dates.index(row["trade_date"]))
        row["open"] = row["high"] = row["low"] = row["close"] = price / 2.0
    for row in tables["prices_adj"]:
        price = close_at(dates.index(row["trade_date"]))
        row["adj_open"] = row["adj_high"] = row["adj_low"] = row["adj_close"] = price
        row["adj_factor"] = 2.0


@pytest.fixture(scope="module")
def hand_ready(tmp_path_factory, policy, parent):
    root = tmp_path_factory.mktemp("hand-gate")
    tables, _dates = hand_tables(2.0)
    contract = hand_contract(parent)
    manifest = commit_tables(root / "source", tables, policy=policy, contract=contract, parent_hash=parent.hash, case_id="HAND-20x155")
    checked = build_checked_snapshot(manifest, contract=contract, policy=policy, mode="SYNTHETIC", root=root / "build")
    folder, summary = run_snapshot_smoke(checked.folder / "snapshot_manifest.json", contract=contract, policy=policy, mode="SYNTHETIC", root=root / "smoke")
    return {"root": root, "tables": tables, "contract": contract, "manifest": manifest, "checked": checked, "smoke": folder, "summary": summary}


def test_build_validate_and_smoke_share_one_reader(monkeypatch, tmp_path, policy, parent):
    calls = []
    real = load_checked_snapshot

    def spy(path, **kwargs):
        calls.append(kwargs["mode"])
        return real(path, **kwargs)

    monkeypatch.setattr("momentum_pullback.data_gate.load_checked_snapshot", spy)
    manifest, contract = _tiny(tmp_path / "src", policy, parent, "B-READER")
    checked = build_checked_snapshot(manifest, contract=contract, policy=policy, mode="SYNTHETIC", root=tmp_path / "build", offline=False, outcomes_disabled=False)
    validate_snapshot(checked.folder / "snapshot_manifest.json", contract=contract, policy=policy, mode="SYNTHETIC", root=tmp_path / "validate")
    run_snapshot_smoke(checked.folder / "snapshot_manifest.json", contract=contract, policy=policy, mode="SYNTHETIC", root=tmp_path / "smoke")
    assert calls == ["SYNTHETIC", "SYNTHETIC", "SYNTHETIC"]
    assert checked.manifest["outcomes_enabled"] is False
    constraints = json.loads((checked.folder / "command_constraints.json").read_text(encoding="utf-8"))
    assert constraints == {"offline": False, "outcomes_disabled_flag": False, "outcomes_enabled": False, "network_requests": 0, "parameter_status": "PROPOSED"}
    names = {item["path"] for item in json.loads((checked.folder / "artifact_hashes.json").read_text(encoding="utf-8"))}
    assert "artifact_hashes.json" not in names
    assert "source_manifest.json" in names
    assert "snapshot_manifest.json" in names


def test_partial_snapshot_does_not_drive_the_engine(monkeypatch, tmp_path, policy, parent):
    def forbidden(*args, **kwargs):
        del args, kwargs
        raise AssertionError("partial snapshot must not drive the engine")

    monkeypatch.setattr("momentum_pullback.data_gate.build_events", forbidden)
    tables = flat_package(DATES, ["X"], close=10.0, factor=2.0, amount=12.5, amount_unit="THOUSAND_CNY", circ=3.0, circ_unit="TEN_THOUSAND_CNY", industry_from=DATES[-1], circ_dates=[DATES[-1]], industry_status="UNKNOWN")
    contract = narrow_contract(parent, DATES[0], DATES[-1], DATES[-1])
    manifest = commit_tables(tmp_path / "src", tables, policy=policy, contract=contract, parent_hash=parent.hash, case_id="B-PARTIAL", amount_unit="THOUSAND_CNY", circ_unit="TEN_THOUSAND_CNY")
    checked = build_checked_snapshot(manifest, contract=contract, policy=policy, mode="SYNTHETIC", root=tmp_path / "build")
    _folder, summary = run_snapshot_smoke(checked.folder / "snapshot_manifest.json", contract=contract, policy=policy, mode="SYNTHETIC", root=tmp_path / "smoke")
    assert summary["status"] == "SYNTHETIC_SNAPSHOT_PARTIAL"
    assert summary["accepted"] is False
    assert summary["data_status"] != "DATA_READY_FOR_ENGINEERING"
    assert not list((tmp_path / "smoke").rglob("acceptance_summary.json"))
    assert not list(tmp_path.rglob("events.parquet"))


def test_a_structural_block_is_not_reported_as_zero_events(tmp_path, policy, parent):
    contract = narrow_contract(parent, DATES[0], DATES[-1], DATES[-1])
    tables = flat_package(DATES, ["X", "Y"], close=10.0, factor=2.0, amount=10.0, amount_unit="CNY", circ=3.0, circ_unit="TEN_THOUSAND_CNY", industry_from=DATES[-1], circ_dates=[DATES[-1]])
    tables["prices_raw"] = [row for row in tables["prices_raw"] if row["ts_code"] != "Y"]
    tables["prices_adj"] = [row for row in tables["prices_adj"] if row["ts_code"] != "Y"]
    manifest = commit_tables(tmp_path / "src", tables, policy=policy, contract=contract, parent_hash=parent.hash, case_id="B-BLOCK", circ_unit="TEN_THOUSAND_CNY")
    with pytest.raises(GateError) as caught:
        build_checked_snapshot(manifest, contract=contract, policy=policy, mode="SYNTHETIC", root=tmp_path / "build")
    assert caught.value.code == "SNAPSHOT_COVERAGE_INCOMPLETE"
    assert caught.value.code != "EVALUATED_ZERO_EVENTS"
    assert "Y" in str(caught.value.details)
    assert not list(tmp_path.rglob("acceptance_summary.json"))
    assert not list(tmp_path.rglob("snapshot_manifest.json"))
    assert not list(tmp_path.rglob("events.parquet"))


def test_short_series_reports_unknown_identity_rather_than_zero_events(tmp_path, policy, parent):
    manifest, contract = _tiny(tmp_path / "src", policy, parent, "B-SHORT")
    checked = build_checked_snapshot(manifest, contract=contract, policy=policy, mode="SYNTHETIC", root=tmp_path / "build")
    _folder, summary = run_snapshot_smoke(checked.folder / "snapshot_manifest.json", contract=contract, policy=policy, mode="SYNTHETIC", root=tmp_path / "smoke")
    assert len(checked.calendar) < 150
    assert summary["data_status"] == "SYNTHETIC_SNAPSHOT_READY"
    assert summary["status"] == "PARTIAL_IDENTITY_UNEVALUABLE"
    assert summary["event_status"] == "PARTIAL_IDENTITY_UNEVALUABLE"
    assert summary["status"] != "EVALUATED_ZERO_EVENTS"
    assert summary["outcomes_enabled"] is False


def test_complete_flat_series_is_a_normal_zero_event_result(tmp_path, policy, parent):
    dates = _declared(160, "2018-06-29")
    contract = narrow_contract(parent, dates[0], dates[149], dates[-1])
    tables = flat_package(dates, ["A", "B"], close=10.0, factor=2.0, amount=100_000_000.0, amount_unit="CNY", circ=1_000_000_000.0, circ_unit="CNY")
    manifest = commit_tables(tmp_path / "src", tables, policy=policy, contract=contract, parent_hash=parent.hash, case_id="B-EMPTY")
    checked = build_checked_snapshot(manifest, contract=contract, policy=policy, mode="SYNTHETIC", root=tmp_path / "build")
    _folder, summary = run_snapshot_smoke(checked.folder / "snapshot_manifest.json", contract=contract, policy=policy, mode="SYNTHETIC", root=tmp_path / "smoke")
    assert len(dates) >= 150
    assert summary["data_status"] == "SYNTHETIC_SNAPSHOT_READY"
    assert summary["status"] == "EVALUATED_ZERO_EVENTS"
    assert summary["event_status"] == "EVALUATED_ZERO_EVENTS"
    assert summary["events"] == 0
    assert summary["unknown_identity_rows"] == 0
    assert summary["outcomes_generated"] is False
    features = pd.read_parquet(_folder / "features.parquet")
    assert int(features["valid_observations"].max()) >= 150


def test_complete_rising_series_keeps_unknown_identity(tmp_path, policy, parent):
    dates = _declared(160, "2018-06-29")
    contract = narrow_contract(parent, dates[0], dates[149], dates[-1])
    tables = flat_package(dates, ["A", "B"], close=10.0, factor=2.0, amount=100_000_000.0, amount_unit="CNY", circ=1_000_000_000.0, circ_unit="CNY")
    _scale_rows(tables, dates, lambda index: 10.0 + index)
    manifest = commit_tables(tmp_path / "src", tables, policy=policy, contract=contract, parent_hash=parent.hash, case_id="B-IDENTITY")
    checked = build_checked_snapshot(manifest, contract=contract, policy=policy, mode="SYNTHETIC", root=tmp_path / "build")
    folder, summary = run_snapshot_smoke(checked.folder / "snapshot_manifest.json", contract=contract, policy=policy, mode="SYNTHETIC", root=tmp_path / "smoke")
    assert summary["data_status"] == "SYNTHETIC_SNAPSHOT_READY"
    assert summary["status"] == "PARTIAL_IDENTITY_UNEVALUABLE"
    assert summary["status"] != "EVALUATED_ZERO_EVENTS"
    events = pd.read_parquet(folder / "events.parquet")
    assert events.empty
    observations = pd.read_parquet(folder / "observations.parquet")
    window = observations[observations.trade_date.ge(dates[149])]
    assert not bool(window.identity_known.all())
    assert set(window.touch_no) == {0}


def test_verified_halt_keeps_the_price_clock_and_the_amount_clock_apart(tmp_path, policy, parent):
    dates = [int(value.strftime("%Y%m%d")) for value in pd.date_range("2018-02-01", periods=25, freq="D")]
    halt = dates[10]
    contract = narrow_contract(parent, dates[0], dates[0], dates[-1])
    tables = flat_package(dates, ["H"], close=10.0, factor=2.0, amount=100_000_000.0, amount_unit="CNY", circ=1_000_000_000.0, circ_unit="CNY", price_dates=[date for date in dates if date != halt], amount_dates=[date for date in dates if date != halt])
    tables["halts"] = [{"ts_code": "H", "trade_date": halt, "revision_id": "1", "halt_scope": "FULL_DAY", "available_at": "2018-02-15T17:00:00+08:00"}]
    # The available_at above is replaced with the halt session's own clock below.
    day = pd.Timestamp(str(halt)).strftime("%Y-%m-%d")
    tables["halts"][0]["available_at"] = f"{day}T17:00:00+08:00"
    manifest = commit_tables(tmp_path / "src", tables, policy=policy, contract=contract, parent_hash=parent.hash, case_id="B-HALT-CLOCK")
    checked = build_checked_snapshot(manifest, contract=contract, policy=policy, mode="SYNTHETIC", root=tmp_path / "build")
    halted = checked.panel.loc[checked.panel.trade_date.eq(halt)].iloc[0]
    assert halted.price_status == "VERIFIED_FULL_DAY_HALT"
    assert halted.amount_derivation == "VERIFIED_HALT_ZERO"
    assert float(halted.amount_cny) == 0.0
    calendar = [int(value) for value in checked.calendar.trade_date.tolist()]
    features = build_features(checked.panel, calendar, contract, roster=checked.roster)
    halt_row = features.loc[features.trade_date.eq(halt)].iloc[0]
    previous = features.loc[features.trade_date.eq(dates[9])].iloc[0]
    following = features.loc[features.trade_date.eq(dates[11])].iloc[0]
    last = features.loc[features.trade_date.eq(dates[-1])].iloc[0]
    assert bool(previous.price_known) is True
    assert bool(halt_row.price_known) is False
    assert bool(halt_row.verified_halt_known) is True
    assert int(halt_row.valid_observations) == int(previous.valid_observations)
    assert int(following.valid_observations) == int(halt_row.valid_observations) + 1
    assert int(last.valid_observations) == 24
    assert int(last.verified_halt_days) >= 1
    assert last.adv20_cny == pytest.approx(19 / 20 * 100_000_000.0)


def test_hand_snapshot_reproduces_four_roots_two_events_and_six_matches(hand_ready):
    summary = hand_ready["summary"]
    assert summary["status"] == "SYNTHETIC_ENGINEERING_PASS"
    assert summary["data_status"] == "SYNTHETIC_SNAPSHOT_READY"
    assert summary["event_status"] == "EVENTS_BUILT"
    assert summary["matching_status"] == "MATCHES_LOCKED"
    assert summary["roots"] == 4
    assert summary["events"] == 2
    assert summary["controls"] == 6
    assert summary["coverage"] == {"candidate_events": 2, "matched_events": 2, "failed_events": 0}
    assert summary["december_to_january_checkpoint"] == "PASS"
    assert summary["outcomes_generated"] is False
    expected = json.loads((ROOT / "momentum_pullback/fixtures/hand_expected.json").read_text(encoding="utf-8"))
    events = pd.read_parquet(hand_ready["smoke"] / "events.parquet")
    columns = list(expected["events"][0])
    actual = [{key: value.item() if hasattr(value, "item") else value for key, value in row.items()} for row in events[columns].to_dict("records")]
    assert actual == expected["events"]
    matches = pd.read_parquet(hand_ready["smoke"] / "matching_matches.parquet")
    assert len(matches) == 6
    assert set(matches.control_code) == {"B", "C", "D"}
    assert matches.distance.eq(0).all()
    binding = json.loads((hand_ready["smoke"] / "snapshot_state_binding.json").read_text(encoding="utf-8"))
    assert binding["schema"] == "momentum_pullback.snapshot_state_binding.v1"
    assert binding["processed_cutoff"] == 20171229
    assert binding["code_hash"] == implementation_hash()
    assert binding["snapshot_id"] == summary["snapshot_id"]
    features = pd.read_parquet(hand_ready["smoke"] / "features.parquet")
    signal = features.loc[features.trade_date.eq(20180102)]
    assert signal.rank_denominator_hash.nunique() == 1
    codes = sorted(signal.ts_code.astype(str))
    assert signal.rank_denominator_hash.iloc[0] == fingerprint(codes)
    half_codes = list("ABCDEFGHIJ")
    panel = hand_ready["checked"].panel
    half_panel = panel.loc[panel.ts_code.isin(half_codes)].copy()
    half_roster = hand_ready["checked"].roster.loc[hand_ready["checked"].roster.ts_code.isin(half_codes)].copy()
    calendar = [int(value) for value in hand_ready["checked"].calendar.trade_date.tolist()]
    half = build_features(half_panel, calendar, hand_ready["contract"], roster=half_roster)
    half_hash = half.loc[half.trade_date.eq(20180102), "rank_denominator_hash"].iloc[0]
    assert half_hash != signal.rank_denominator_hash.iloc[0]


def test_a_legal_price_revision_cannot_keep_the_original_hand_success(tmp_path, policy, parent):
    tables, _dates = hand_tables(2.0)
    for row in tables["prices_adj"]:
        if row["ts_code"] == "A" and row["trade_date"] == 20180102:
            row["adj_low"] = 12.0
    for row in tables["prices_raw"]:
        if row["ts_code"] == "A" and row["trade_date"] == 20180102:
            row["low"] = 6.0
    contract = hand_contract(parent)
    manifest = commit_tables(tmp_path / "src", tables, policy=policy, contract=contract, parent_hash=parent.hash, case_id="HAND-20x155")
    checked = build_checked_snapshot(manifest, contract=contract, policy=policy, mode="SYNTHETIC", root=tmp_path / "build")
    assert checked.gate["status"] == "SYNTHETIC_SNAPSHOT_READY"
    changed = checked.panel.loc[checked.panel.ts_code.eq("A") & checked.panel.trade_date.eq(20180102)].iloc[0]
    assert float(changed.adj_low) == 12.0
    with pytest.raises(GateError) as caught:
        run_snapshot_smoke(checked.folder / "snapshot_manifest.json", contract=contract, policy=policy, mode="SYNTHETIC", root=tmp_path / "smoke")
    assert caught.value.code == "HAND_EVENT_ORACLE_MISMATCH"
    assert not list(tmp_path.rglob("acceptance_summary.json"))
    assert not list(tmp_path.rglob("matching_matches.parquet"))
    assert not list(tmp_path.rglob("*SYNTHETIC_ENGINEERING_PASS*"))


def _binding_at_cutoff(checked, contract, policy, cutoff: int):
    panel = checked.panel
    roster = checked.roster
    calendar = [int(value) for value in checked.calendar.trade_date.tolist()]
    prefix = build_features(panel.loc[panel.trade_date.le(cutoff)].copy(), calendar, contract, roster=roster, return_states=True)
    early = build_events(prefix["features"], contract)
    saved = checkpoint({"event_states": early["states"], "feature_states": prefix["states"]}, contract=contract, code_hash=implementation_hash(), feature_origin=calendar[0], processed_cutoff=cutoff, history_hash=input_history_hash(panel, calendar, cutoff, roster), roster_hash=roster_history_hash(roster, cutoff))
    return saved, make_snapshot_binding(checked, saved, contract=contract, policy=policy)


def test_future_only_append_resumes_and_historical_change_does_not(hand_ready, tmp_path, policy, parent):
    saved, binding = _binding_at_cutoff(hand_ready["checked"], hand_ready["contract"], policy, 20171229)
    original_id = binding["snapshot_id"]
    assert original_id == json.loads((hand_ready["smoke"] / "snapshot_state_binding.json").read_text(encoding="utf-8"))["snapshot_id"]
    future_tables, _dates = hand_tables(2.0)
    future_tables["membership"].append({"ts_code": "A", "revision_id": "2", "is_member": True, "effective_from": 20180108, "effective_to": None, "available_at": "2018-01-08T17:00:00+08:00"})
    future_manifest = commit_tables(tmp_path / "future", future_tables, policy=policy, contract=hand_ready["contract"], parent_hash=parent.hash, case_id="HAND-20x155")
    future = build_checked_snapshot(future_manifest, contract=hand_ready["contract"], policy=policy, mode="SYNTHETIC", root=tmp_path / "future-build")
    assert future.manifest["snapshot_id"] != original_id
    assert binding["snapshot_id"] == original_id
    cutoff = 20171229
    before = prefix_identity(hand_ready["checked"], contract=hand_ready["contract"], policy=policy, cutoff=cutoff)
    after = prefix_identity(future, contract=hand_ready["contract"], policy=policy, cutoff=cutoff)
    assert before["source_prefix"] == after["source_prefix"]
    assert before["normalized_history_hash"] == after["normalized_history_hash"]
    state = resume_bound_state(future, saved, binding, contract=hand_ready["contract"], policy=policy)
    calendar = [int(value) for value in future.calendar.trade_date.tolist()]
    replay = build_features(future.panel, calendar, hand_ready["contract"], roster=future.roster)
    resumed = build_features(future.panel.loc[future.panel.trade_date.gt(cutoff)].copy(), calendar, hand_ready["contract"], roster=future.roster, states=state["feature_states"])
    pd.testing.assert_frame_equal(replay.loc[replay.trade_date.gt(cutoff)].reset_index(drop=True), resumed.reset_index(drop=True), check_dtype=False)
    original = build_features(hand_ready["checked"].panel, calendar, hand_ready["contract"], roster=hand_ready["checked"].roster)
    pd.testing.assert_frame_equal(original.loc[original.trade_date.le(cutoff)].reset_index(drop=True), replay.loc[replay.trade_date.le(cutoff)].reset_index(drop=True), check_dtype=False)
    replay_events = build_events(replay, hand_ready["contract"])
    resumed_events = build_events(resumed, hand_ready["contract"], states=state["event_states"])
    pd.testing.assert_frame_equal(replay_events["events"].reset_index(drop=True), resumed_events["events"].reset_index(drop=True), check_dtype=False)
    assert len(replay_events["roots"]) == 4
    assert len(replay_events["events"]) == 2
    historical, _dates = hand_tables(2.0)
    for name in ("prices_raw", "prices_adj"):
        for row in historical[name]:
            if row["ts_code"] == "A" and row["trade_date"] == 20171229:
                if name == "prices_raw":
                    row["open"] = row["high"] = row["low"] = row["close"] = 5.5
                else:
                    row["adj_open"] = row["adj_high"] = row["adj_low"] = row["adj_close"] = 11.0
    historical_manifest = commit_tables(tmp_path / "historical", historical, policy=policy, contract=hand_ready["contract"], parent_hash=parent.hash, case_id="HAND-20x155")
    changed = build_checked_snapshot(historical_manifest, contract=hand_ready["contract"], policy=policy, mode="SYNTHETIC", root=tmp_path / "historical-build")
    stamped = copy.deepcopy(saved)
    with pytest.raises(GateError) as caught:
        resume_bound_state(changed, stamped, binding, contract=hand_ready["contract"], policy=policy)
    assert caught.value.code == "SNAPSHOT_PREFIX_MISMATCH"
    assert "snapshot_id" not in stamped
    assert json.loads((hand_ready["smoke"] / "snapshot_state_binding.json").read_text(encoding="utf-8"))["snapshot_id"] == original_id
    assert input_history_hash(changed.panel, calendar, cutoff, changed.roster) != before["normalized_history_hash"]


def test_missing_binding_does_not_stamp_a_new_snapshot_id(hand_ready):
    saved = json.loads((hand_ready["smoke"] / "checkpoint.json").read_text(encoding="utf-8"))
    original = json.dumps(saved)
    with pytest.raises(GateError) as caught:
        resume_bound_state(hand_ready["checked"], saved, None, contract=hand_ready["contract"], policy=load_snapshot_policy(POLICY_PATH))
    assert caught.value.code == "SNAPSHOT_STATE_BINDING_MISSING"
    assert json.dumps(saved) == original
    assert "snapshot_id" not in saved
    legacy = dict(saved)
    legacy["schema"] = "momentum_pullback.checkpoint.v3"
    with pytest.raises(GateError) as legacy_error:
        resume_bound_state(hand_ready["checked"], legacy, {"schema": "momentum_pullback.snapshot_state_binding.v1"}, contract=hand_ready["contract"], policy=load_snapshot_policy(POLICY_PATH))
    assert legacy_error.value.code == "CHECKPOINT_NOT_UPGRADABLE"


def test_input_mutation_during_smoke_rejects_acceptance(tmp_path, policy, parent):
    manifest, contract = _tiny(tmp_path / "src", policy, parent, "B-MUTATE")

    def tamper(_folder):
        manifest.write_bytes(manifest.read_bytes() + b"\n")

    with pytest.raises(GateError) as caught:
        run_snapshot_smoke(build_checked_snapshot(manifest, contract=contract, policy=policy, mode="SYNTHETIC", root=tmp_path / "build").folder / "snapshot_manifest.json", contract=contract, policy=policy, mode="SYNTHETIC", root=tmp_path / "smoke", before_accept=tamper)
    assert caught.value.code == "INPUT_CONTENT_CHANGED_DURING_RUN"
    assert not list((tmp_path / "smoke").rglob("acceptance_summary.json"))
    blocked = list((tmp_path / "smoke").rglob("blocked.json"))
    assert blocked
    payload = json.loads(blocked[0].read_text(encoding="utf-8"))
    assert payload["reason"] == "INPUT_CONTENT_CHANGED_DURING_RUN"
    assert payload["outcomes_generated"] is False


def test_unavailable_industry_makes_matching_unevaluable_without_replacing_controls(tmp_path, policy, parent):
    tables, dates = hand_tables(2.0)
    for row in tables["industry"]:
        row["effective_from"] = 20180108
        row["available_at"] = f"{pd.Timestamp(str(dates[0])).strftime('%Y-%m-%d')}T17:00:00+08:00"
    contract = hand_contract(parent)
    manifest = commit_tables(tmp_path / "src", tables, policy=policy, contract=contract, parent_hash=parent.hash, case_id="B-MATCH")
    checked = build_checked_snapshot(manifest, contract=contract, policy=policy, mode="SYNTHETIC", root=tmp_path / "build")
    assert checked.gate["status"] == "SYNTHETIC_SNAPSHOT_READY"
    signal = checked.panel.loc[checked.panel.trade_date.eq(20180102)].iloc[0]
    assert bool(signal.price_status == "TRADED")
    assert pd.isna(signal.industry_code)
    folder, summary = run_snapshot_smoke(checked.folder / "snapshot_manifest.json", contract=contract, policy=policy, mode="SYNTHETIC", root=tmp_path / "smoke")
    assert summary["data_status"] == "SYNTHETIC_SNAPSHOT_READY"
    assert summary["event_status"] == "EVENTS_BUILT"
    assert summary["status"] == "MATCHING_UNEVALUABLE"
    assert summary["matching_status"] == "MATCHING_UNEVALUABLE"
    assert summary["controls"] == 0
    assert summary["unknown_identity_rows"] == 0
    assert "MATCH_INFORMATION_UNAVAILABLE_AT_CUTOFF" in summary["failure_reasons"]
    assert pd.read_parquet(folder / "matching_matches.parquet").empty
    failures = pd.read_parquet(folder / "matching_failures.parquet")
    assert set(failures.reason) == {"MATCH_INFORMATION_UNAVAILABLE_AT_CUTOFF"}


def test_real_read_stays_blocked_and_validation_does_not_rewrite_the_snapshot(tmp_path, policy, parent):
    manifest, contract = _tiny(tmp_path / "src", policy, parent, "B-VALIDATE")
    checked = build_checked_snapshot(manifest, contract=contract, policy=policy, mode="SYNTHETIC", root=tmp_path / "build")
    report = (checked.folder / "data_gate_report.json").read_bytes()
    manifest_bytes = (checked.folder / "snapshot_manifest.json").read_bytes()
    folder, validated = validate_snapshot(checked.folder / "snapshot_manifest.json", contract=contract, policy=policy, mode="SYNTHETIC", root=tmp_path / "validate", offline=False, outcomes_disabled=False)
    assert validated["status"] == "SYNTHETIC_SNAPSHOT_READY"
    assert validated["outcomes_enabled"] is False
    assert (checked.folder / "data_gate_report.json").read_bytes() == report
    assert (checked.folder / "snapshot_manifest.json").read_bytes() == manifest_bytes
    assert (folder / "validation_report.json").is_file()
    assert validated["checked_snapshot_manifest_sha256"]
    with pytest.raises(GateError, match="SNAPSHOT_MODE_MISMATCH"):
        load_checked_snapshot(checked.folder / "snapshot_manifest.json", contract=contract, policy=policy, mode="REAL")
    real_tables = flat_package(DATES, ["X"], close=10.0, factor=2.0, amount=12.5, amount_unit="THOUSAND_CNY", circ=3.0, circ_unit="TEN_THOUSAND_CNY", industry_from=DATES[-1], circ_dates=[DATES[-1]])
    real_manifest = commit_tables(tmp_path / "real", real_tables, policy=policy, contract=contract, parent_hash=parent.hash, case_id="B-REAL-READ", amount_unit="THOUSAND_CNY", circ_unit="TEN_THOUSAND_CNY", mode="REAL", review_kind="REAL_CERTIFIED", real_flag=True)
    with pytest.raises(GateError, match="REVIEW_RECEIPT_UNTRUSTED"):
        build_checked_snapshot(real_manifest, contract=contract, policy=policy, mode="REAL", root=tmp_path / "real-build")
    assert not list(tmp_path.rglob("events.parquet"))
    assert not list(tmp_path.rglob("matching_matches.parquet"))


def _foreign_checkpoint(checked, contract, policy, code_hash: str):
    """Build a v4 checkpoint whose only foreign field is the implementation identity."""
    panel = checked.panel
    roster = checked.roster
    calendar = [int(value) for value in checked.calendar.trade_date.tolist()]
    cutoff = calendar[0]
    saved = checkpoint({"event_states": {}, "feature_states": {}}, contract=contract, code_hash=code_hash, feature_origin=calendar[0], processed_cutoff=cutoff, history_hash=input_history_hash(panel, calendar, cutoff, roster), roster_hash=roster_history_hash(roster, cutoff))
    identity = prefix_identity(checked, contract=contract, policy=policy, cutoff=cutoff)
    core = fingerprint({key: saved[key] for key in ("schema", "contract_hash", "code_hash", "feature_origin", "processed_cutoff", "consumed_history_hash", "consumed_roster_hash", "state_hash")})
    binding = {
        "schema": "momentum_pullback.snapshot_state_binding.v1",
        "checkpoint_core_hash": core,
        "contract_hash": saved["contract_hash"],
        "code_hash": code_hash,
        "processed_cutoff": cutoff,
        "snapshot_policy_hash": identity["snapshot_policy_hash"],
        "source_prefix": identity["source_prefix"],
        "normalized_history_hash": identity["normalized_history_hash"],
        "roster_history_hash": identity["roster_history_hash"],
        "calendar_prefix": identity["calendar_prefix"],
        "approved_source_range_prefix": identity["approved_source_range_prefix"],
        "snapshot_id": checked.manifest["snapshot_id"],
    }
    return saved, binding


def test_c1_old_implementation_is_refused_even_when_its_binding_is_self_consistent(tmp_path, policy, parent):
    manifest, contract = _tiny(tmp_path / "src", policy, parent, "C1-01")
    checked = build_checked_snapshot(manifest, contract=contract, policy=policy, mode="SYNTHETIC", root=tmp_path / "build")
    foreign = "a" * 64
    assert foreign != implementation_hash()
    saved, binding = _foreign_checkpoint(checked, contract, policy, foreign)
    assert binding["checkpoint_core_hash"] == fingerprint({key: saved[key] for key in ("schema", "contract_hash", "code_hash", "feature_origin", "processed_cutoff", "consumed_history_hash", "consumed_roster_hash", "state_hash")})
    with pytest.raises(GateError) as resume_error:
        resume_bound_state(checked, saved, binding, contract=contract, policy=policy)
    assert resume_error.value.code == "CHECKPOINT_IDENTITY_MISMATCH"
    assert resume_error.value.details == "code_hash"
    with pytest.raises(GateError) as direct:
        restore_checkpoint(saved, contract=contract, code_hash=implementation_hash(), feature_origin=int(saved["feature_origin"]), processed_cutoff=int(saved["processed_cutoff"]), history_hash=saved["consumed_history_hash"], roster_hash=saved["consumed_roster_hash"])
    assert direct.value.code == "CHECKPOINT_IDENTITY_MISMATCH"
    assert direct.value.details == "code_hash"
    with pytest.raises(GateError) as binding_error:
        make_snapshot_binding(checked, saved, contract=contract, policy=policy)
    assert binding_error.value.code == "CHECKPOINT_IDENTITY_MISMATCH"
    assert binding_error.value.details == "code_hash"
    current, current_binding = _binding_at_cutoff(checked, contract, policy, int(saved["processed_cutoff"]))
    restored = resume_bound_state(checked, current, current_binding, contract=contract, policy=policy)
    assert restored == current["state"]
    assert current_binding["code_hash"] == implementation_hash()
    legacy = dict(saved)
    legacy["schema"] = "momentum_pullback.checkpoint.v2"
    legacy["code_hash"] = implementation_hash()
    with pytest.raises(GateError) as legacy_error:
        resume_bound_state(checked, legacy, current_binding, contract=contract, policy=policy)
    assert legacy_error.value.code == "CHECKPOINT_NOT_UPGRADABLE"

"""Hand expectations for source time, units, revisions, and authority."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from momentum_pullback.contracts import ROOT, GateError, load_contract
from momentum_pullback.source_bindings import (
    convert_to_cny, load_real_review_index, load_snapshot_policy, load_source_package,
    require_real_bools, require_supported_lifecycle, required_dates, select_asof, source_history_prefix,
)

POLICY_PATH = ROOT / "configs/momentum_pullback/snapshot_policy_v0_1.yaml"
EXPECTED_PATH = ROOT / "momentum_pullback/fixtures/snapshot_expected_v0_1.json"


@pytest.fixture(scope="module")
def policy():
    return load_snapshot_policy(POLICY_PATH)


@pytest.fixture(scope="module")
def contract():
    return load_contract(ROOT / "configs/momentum_pullback/research_contract_v0_2.yaml")


@pytest.fixture(scope="module")
def expected():
    return json.loads(EXPECTED_PATH.read_text(encoding="utf-8"))


def test_policy_binds_definition_and_stays_proposed(policy):
    assert policy.payload["parameter_status"] == "PROPOSED"
    assert policy.payload["outcomes_enabled"] is False
    assert policy.payload["date_only_announcement_policy"]["status"] == "PROPOSED_NOT_APPLIED"
    assert policy.file_hash == hashlib.sha256(POLICY_PATH.read_bytes()).hexdigest()
    assert load_real_review_index()["entries"] == []


def test_late_available_fact_is_not_selected(expected):
    case = expected["cases"]["B-TIME-01"]
    frame = pd.DataFrame(case["rows"])
    selected = select_asof(frame, business_keys=case["business_keys"], revision_column="revision_id", order_columns=["available_at", "revision_id"], cutoff=expected["signal_cutoff"], available_column="available_at")
    assert selected.revision_id.tolist() == [case["expected_revision_id"]]
    assert selected.raw_close.tolist() == [case["expected_raw_close"]]
    late = select_asof(pd.DataFrame(case["late_only_rows"]), business_keys=case["business_keys"], revision_column="revision_id", order_columns=["available_at", "revision_id"], cutoff=expected["signal_cutoff"], available_column="available_at")
    assert len(late) == case["late_only_selected_rows"]
    for column in case["rejected_available_at_columns"]:
        with pytest.raises(GateError, match=case["rejected_error"]):
            from momentum_pullback.source_bindings import validate_time_mapping
            validate_time_mapping(column, "EXPLICIT_TIMEZONE_TIMESTAMP")
    with pytest.raises(GateError, match=case["rejected_error"]):
        from momentum_pullback.source_bindings import validate_time_mapping
        validate_time_mapping("available_at", "DATE_ONLY")
        validate_time_mapping("available_at", "FILE_MTIME")


def test_revisions_select_order_and_reject_ties(expected):
    case = expected["cases"]["B-REV-01"]
    selected = select_asof(pd.DataFrame(case["legal_rows"]), business_keys=["ts_code", "trade_date"], revision_column="revision_id", order_columns=["available_at", "revision_id"], cutoff="2018-01-02T18:00:00+08:00", available_column="available_at")
    assert selected.revision_id.tolist() == [case["expected_revision_id"]]
    assert float(selected.raw_close.iloc[0]) == case["expected_raw_close"]
    with pytest.raises(GateError, match=case["duplicate_error"]):
        select_asof(pd.DataFrame(case["duplicate_rows"]), business_keys=["ts_code", "trade_date"], revision_column="revision_id", order_columns=["available_at", "revision_id"], cutoff="2018-01-02T18:00:00+08:00", available_column="available_at")
    with pytest.raises(GateError, match=case["ambiguous_error"]):
        select_asof(pd.DataFrame(case["ambiguous_rows"]), business_keys=["ts_code", "trade_date"], revision_column="revision_id", order_columns=case["ambiguous_order"], cutoff="2018-01-02T18:00:00+08:00", available_column="available_at")


def test_units_use_only_the_policy_table(policy, expected):
    case = expected["cases"]["B-UNIT-01"]
    for item in case["conversions"]:
        assert convert_to_cny(item["value"], item["unit"], case["field"], policy) == item["expected_cny"]
    with pytest.raises(GateError, match=case["error"]):
        convert_to_cny(12.5, case["missing_unit"], case["field"], policy)
    with pytest.raises(GateError, match=case["error"]):
        convert_to_cny(12.5, case["unknown_unit"], case["field"], policy)


def _package(directory: Path, rows: list[dict], policy, contract, **overrides) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(rows).encode("utf-8")
    (directory / "prices.json").write_bytes(payload)
    manifest = {
        "schema": "momentum_pullback.source_manifest.v1",
        "mode": overrides.get("mode", "SYNTHETIC"),
        "case_id": "B-MIN",
        "parent_contract_hash": contract.hash,
        "engineering_contract_hash": contract.hash,
        "snapshot_policy_hash": policy.file_hash,
        "source_definition_sha256": policy.document_hash,
        "parameter_status": "PROPOSED",
        "outcomes_enabled": False,
        "date_only_announcement_policy": policy.payload["date_only_announcement_policy"],
        "input_root": overrides.get("input_root", "."),
        "calendar_dates": [20180102],
        "roster_codes": ["X"],
        "review_receipt_ref": "receipt.json",
        "tables": [{
            "table_id": "prices_raw",
            "relative_path": "prices.json",
            "sha256": overrides.get("table_hash", hashlib.sha256(payload).hexdigest()),
            "primary_key": ["ts_code", "trade_date", "revision_id"],
            "fields": {"raw_close": {"canonical": "raw_close", "available_at_column": "available_at", "available_at_semantics": "EXPLICIT_TIMEZONE_TIMESTAMP"}},
        }],
    }
    if overrides.get("date_policy"):
        manifest["date_only_announcement_policy"] = overrides["date_policy"]
    manifest_path = directory / "source_manifest.json"
    manifest_bytes = json.dumps(manifest).encode("utf-8")
    manifest_path.write_bytes(manifest_bytes)
    receipt = {
        "schema": "momentum_pullback.source_review_receipt.v1",
        "mode": overrides.get("receipt_mode", manifest["mode"]),
        "review_kind": overrides.get("review_kind", "SYNTHETIC_DECLARATION"),
        "source_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "snapshot_policy_hash": policy.file_hash,
        "case_id": overrides.get("case_id", "B-MIN"),
        "calendar_dates": overrides.get("receipt_calendar", [20180102]),
        "roster_codes": overrides.get("receipt_roster", ["X"]),
        "reviewed_at": "2026-10-16T12:00:00+08:00",
        "real_events_permitted": overrides.get("real_flag", False),
        "open_items": ["REAL_CERTIFICATION_NOT_CLAIMED"],
    }
    (directory / "receipt.json").write_bytes(json.dumps(receipt).encode("utf-8"))
    return manifest_path


def test_synthetic_declaration_does_not_grant_real_authority(tmp_path, policy, contract, expected):
    case = expected["cases"]["B-AUTH-01"]
    rows = expected["cases"]["B-TIME-01"]["rows"]
    manifest = _package(tmp_path, rows, policy, contract)
    package = load_source_package(manifest, policy=policy, contract=contract, allowed_roots=[tmp_path])
    assert package.authority == case["synthetic_authority"]
    assert package.manifest["parameter_status"] == "PROPOSED"
    with pytest.raises(GateError, match=case["real_mode_error"]):
        load_source_package(_package(tmp_path / "real", rows, policy, contract, mode="REAL", review_kind="REAL_CERTIFIED"), policy=policy, contract=contract, allowed_roots=[tmp_path / "real"])
    with pytest.raises(GateError, match=case["real_events_flag_error"]):
        load_source_package(_package(tmp_path / "flag", rows, policy, contract, real_flag=True), policy=policy, contract=contract, allowed_roots=[tmp_path / "flag"])
    with pytest.raises(GateError, match=case["review_kind_mismatch_error"]):
        load_source_package(_package(tmp_path / "kind", rows, policy, contract, review_kind="REAL_CERTIFIED"), policy=policy, contract=contract, allowed_roots=[tmp_path / "kind"])
    with pytest.raises(GateError, match=case["scope_mismatch_error"]):
        load_source_package(_package(tmp_path / "scope", rows, policy, contract, receipt_calendar=[20180103]), policy=policy, contract=contract, allowed_roots=[tmp_path / "scope"])


def test_escaped_root_wrong_hash_and_applied_date_policy_are_rejected(tmp_path, policy, contract, expected):
    rows = expected["cases"]["B-TIME-01"]["rows"]
    with pytest.raises(GateError, match="SOURCE_MANIFEST_INVALID"):
        load_source_package(_package(tmp_path / "escape", rows, policy, contract, input_root=".."), policy=policy, contract=contract, allowed_roots=[tmp_path / "escape"])
    with pytest.raises(GateError, match="SOURCE_MANIFEST_INVALID"):
        load_source_package(_package(tmp_path / "hash", rows, policy, contract, table_hash="0" * 64), policy=policy, contract=contract, allowed_roots=[tmp_path / "hash"])
    with pytest.raises(GateError, match="SOURCE_MANIFEST_INVALID"):
        load_source_package(_package(tmp_path / "date", rows, policy, contract, date_policy={"id": "DATE_ONLY_ANNOUNCEMENT_ASIA_SHANGHAI_END_OF_DAY", "status": "APPLIED"}), policy=policy, contract=contract, allowed_roots=[tmp_path / "date"])


def test_textual_false_is_not_a_boolean_fact():
    with pytest.raises(GateError, match="BOOLEAN_STATE_INVALID"):
        require_real_bools(pd.DataFrame({"is_member": ["False"]}), ["is_member"])
    require_real_bools(pd.DataFrame({"is_member": [False, True]}), ["is_member"])


def test_lifecycle_and_consumer_windows_follow_the_policy(expected):
    case = expected["cases"]["B-LIFE-01"]
    require_supported_lifecycle([case["supported"]], feature_origin=20180102, output_end=20180105)
    with pytest.raises(GateError, match=case["error"]):
        require_supported_lifecycle([case["lists_after_origin"]], feature_origin=20180102, output_end=20180105)
    with pytest.raises(GateError, match=case["error"]):
        require_supported_lifecycle([case["delists_inside_window"]], feature_origin=20180102, output_end=20180105)
    calendar = list(range(20180101, 20180131))
    amount_dates = required_dates("NINETEEN_CERTIFIED_SESSIONS_BEFORE_OUTPUT_THROUGH_OUTPUT_END", calendar=calendar, feature_origin=20180101, output_start=20180120, output_end=20180130)
    industry_dates = required_dates("OUTPUT_WINDOW_AND_REQUIRED_CROSS_SECTIONS", calendar=calendar, feature_origin=20180101, output_start=20180120, output_end=20180130)
    assert amount_dates[0] == 20180101 and 20180119 in amount_dates and 20180130 in amount_dates
    assert 20180101 not in industry_dates and industry_dates[0] == 20180120


def test_future_append_keeps_prefix_and_late_revision_changes_it(expected):
    case = expected["cases"]["B-PREFIX-01"]
    past = pd.DataFrame([case["past_price"]])
    future = pd.DataFrame([case["past_price"], case["future_price"]])
    late = pd.DataFrame([case["past_price"], case["late_past_revision"]])
    empty_events = pd.DataFrame(columns=["ts_code", "available_at", "effective_from"])
    roster = pd.DataFrame({"trade_date": [20180102], "ts_code": ["X"], "required_for_rank": [True], "track_identity": [True]})
    future_roster = pd.concat([roster, pd.DataFrame({"trade_date": [20180103], "ts_code": ["X"], "required_for_rank": [True], "track_identity": [True]})], ignore_index=True)
    base = source_history_prefix(past, empty_events, [20180102, 20180103], roster, case["cutoff"])
    assert source_history_prefix(future, empty_events, [20180102, 20180103], future_roster, case["cutoff"]) == base
    assert source_history_prefix(late, empty_events, [20180102, 20180103], roster, case["cutoff"]) != base

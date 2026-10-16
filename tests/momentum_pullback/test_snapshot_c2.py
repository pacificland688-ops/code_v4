"""Counterexamples for halt selection, industry coverage, and source keys."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from momentum_pullback.contracts import ROOT, GateError, load_contract
from momentum_pullback.data_gate import run_snapshot_smoke
from momentum_pullback.snapshot import build_snapshot
from momentum_pullback.source_bindings import load_snapshot_policy
from tests.momentum_pullback.snapshot_sources import commit_tables, flat_package, narrow_contract

POLICY_PATH = ROOT / "configs/momentum_pullback/snapshot_policy_v0_1_r1.yaml"
DATES = [20180102, 20180103, 20180104]


@pytest.fixture(scope="module")
def policy():
    loaded = load_snapshot_policy(POLICY_PATH)
    assert loaded.payload["policy_id"] == "momentum_pullback.snapshot_policy.v0_1_r1"
    assert loaded.payload["parameter_status"] == "PROPOSED"
    assert loaded.payload["outcomes_enabled"] is False
    return loaded


@pytest.fixture(scope="module")
def parent():
    return load_contract(ROOT / "configs/momentum_pullback/research_contract_v0_2.yaml")


def _contract(parent):
    return narrow_contract(parent, DATES[0], DATES[-1], DATES[-1])


def _base(dates_with_price=None, dates_with_amount=None):
    return flat_package(
        DATES, ["X"], close=10.0, factor=2.0, amount=100.0, amount_unit="CNY", circ=3.0, circ_unit="TEN_THOUSAND_CNY",
        industry_from=DATES[-1], circ_dates=[DATES[-1]], price_dates=dates_with_price, amount_dates=dates_with_amount,
    )


def _commit(directory, tables, policy, contract, parent, case_id, **kwargs):
    return commit_tables(directory, tables, policy=policy, contract=contract, parent_hash=parent.hash, case_id=case_id, circ_unit="TEN_THOUSAND_CNY", **kwargs)


def _hits(directory: Path, table: str, key_text: str) -> list[dict]:
    key = json.loads(key_text)
    rows = json.loads((directory / f"{table}.json").read_text(encoding="utf-8"))
    return [row for row in rows if all(row.get(name) == value for name, value in key.items())]


def test_c2_h01_unknown_full_day_halt_does_not_verify_or_zero_amount(tmp_path, policy, parent):
    contract = _contract(parent)
    blocked = _base([DATES[0], DATES[-1]], [DATES[0], DATES[-1]])
    blocked["halts"] = [{"ts_code": "X", "trade_date": DATES[1], "revision_id": "1", "halt_scope": "FULL_DAY", "fact_status": "UNKNOWN", "available_at": "2018-01-03T17:00:00+08:00"}]
    manifest = _commit(tmp_path / "blocked", blocked, policy, contract, parent, "C2-H01")
    with pytest.raises(GateError) as caught:
        build_snapshot(manifest, contract=contract, policy=policy, mode="SYNTHETIC", root=tmp_path / "blocked-out")
    assert caught.value.code == "SNAPSHOT_COVERAGE_INCOMPLETE"
    assert not list(tmp_path.rglob("normalized_panel.parquet"))
    kept = _base([DATES[0], DATES[-1]], DATES)
    kept["halts"] = blocked["halts"]
    built = build_snapshot(_commit(tmp_path / "kept", kept, policy, contract, parent, "C2-H01-AMOUNT"), contract=contract, policy=policy, mode="SYNTHETIC", root=tmp_path / "kept-out")
    row = built.panel.loc[built.panel.trade_date.eq(DATES[1])].iloc[0]
    assert built.gate["status"] == "SYNTHETIC_SNAPSHOT_PARTIAL"
    assert row.price_status == "UNKNOWN"
    assert row.price_status != "VERIFIED_FULL_DAY_HALT"
    assert row.amount_derivation != "VERIFIED_HALT_ZERO"
    assert float(row.amount_cny) == 100.0
    unknown = built.lineage.loc[lambda frame: frame.trade_date.eq(DATES[1]) & frame.field_group.eq("price_raw")].iloc[0]
    assert unknown.source_primary_key == ""
    assert unknown.selection_reason == "EXCLUDED_NOT_USABLE_AT_CUTOFF"


def test_c2_h02_later_partial_day_replaces_an_earlier_full_day(tmp_path, policy, parent):
    contract = _contract(parent)
    halts = [
        {"ts_code": "X", "trade_date": DATES[1], "revision_id": "1", "halt_scope": "FULL_DAY", "fact_status": "KNOWN", "available_at": "2018-01-03T16:00:00+08:00"},
        {"ts_code": "X", "trade_date": DATES[1], "revision_id": "2", "halt_scope": "PARTIAL_DAY", "fact_status": "KNOWN", "available_at": "2018-01-03T17:00:00+08:00"},
    ]
    traded = _base()
    traded["halts"] = halts
    built = build_snapshot(_commit(tmp_path / "traded", traded, policy, contract, parent, "C2-H02"), contract=contract, policy=policy, mode="SYNTHETIC", root=tmp_path / "traded-out")
    row = built.panel.loc[built.panel.trade_date.eq(DATES[1])].iloc[0]
    assert row.price_status == "TRADED"
    assert row.amount_derivation == "POLICY_UNIT_FACTOR"
    assert float(row.amount_cny) == 100.0
    assert built.lineage.loc[built.lineage.field_group.eq("halt")].empty
    missing = _base([DATES[0], DATES[-1]], [DATES[0], DATES[-1]])
    missing["halts"] = halts
    with pytest.raises(GateError) as caught:
        build_snapshot(_commit(tmp_path / "missing", missing, policy, contract, parent, "C2-H02-MISS"), contract=contract, policy=policy, mode="SYNTHETIC", root=tmp_path / "missing-out")
    assert caught.value.code == "SNAPSHOT_COVERAGE_INCOMPLETE"


def test_c2_h03_revision_published_after_cutoff_keeps_the_earlier_full_day(tmp_path, policy, parent):
    contract = _contract(parent)
    tables = _base([DATES[0], DATES[-1]], [DATES[0], DATES[-1]])
    tables["halts"] = [
        {"ts_code": "X", "trade_date": DATES[1], "revision_id": "1", "halt_scope": "FULL_DAY", "fact_status": "KNOWN", "available_at": "2018-01-03T16:00:00+08:00"},
        {"ts_code": "X", "trade_date": DATES[1], "revision_id": "2", "halt_scope": "PARTIAL_DAY", "fact_status": "KNOWN", "available_at": "2018-01-03T19:00:00+08:00"},
    ]
    built = build_snapshot(_commit(tmp_path / "src", tables, policy, contract, parent, "C2-H03"), contract=contract, policy=policy, mode="SYNTHETIC", root=tmp_path / "out")
    row = built.panel.loc[built.panel.trade_date.eq(DATES[1])].iloc[0]
    assert row.price_status == "VERIFIED_FULL_DAY_HALT"
    assert row.amount_derivation == "VERIFIED_HALT_ZERO"
    assert float(row.amount_cny) == 0.0
    halt = built.lineage.loc[built.lineage.field_group.eq("halt")].iloc[0]
    assert halt.revision_id == "1"
    assert json.loads(halt.source_primary_key)["revision_id"] == "1"


def test_c2_h04_verified_halt_zero_traces_to_the_halt_fact(tmp_path, policy, parent):
    contract = _contract(parent)
    tables = _base([DATES[0], DATES[-1]], [DATES[0], DATES[-1]])
    tables["halts"] = [{"ts_code": "X", "trade_date": DATES[1], "revision_id": "1", "halt_scope": "FULL_DAY", "fact_status": "KNOWN", "available_at": "2018-01-03T17:00:00+08:00"}]
    directory = tmp_path / "src"
    built = build_snapshot(_commit(directory, tables, policy, contract, parent, "C2-H04"), contract=contract, policy=policy, mode="SYNTHETIC", root=tmp_path / "out")
    amount = built.lineage.loc[lambda frame: frame.trade_date.eq(DATES[1]) & frame.field_group.eq("amount")].iloc[0]
    assert amount.source_table == "halts"
    assert amount.derivation == "VERIFIED_HALT_ZERO"
    hits = _hits(directory, "halts", amount.source_primary_key)
    assert len(hits) == 1 and hits[0]["halt_scope"] == "FULL_DAY"
    assert not any(row.get("amount") == 0 for row in json.loads((directory / "amount.json").read_text(encoding="utf-8")))
    revoked = _base()
    revoked["halts"] = [{"ts_code": "X", "trade_date": DATES[1], "revision_id": "1", "halt_scope": "REVOKED", "available_at": "2018-01-03T17:00:00+08:00"}]
    with pytest.raises(GateError) as caught:
        build_snapshot(_commit(tmp_path / "revoked", revoked, policy, contract, parent, "C2-H04-REVOKED"), contract=contract, policy=policy, mode="SYNTHETIC", root=tmp_path / "revoked-out")
    assert caught.value.code == "SOURCE_MANIFEST_INVALID"


def test_c2_i01_industry_gaps_are_partial_and_do_not_pass_smoke(tmp_path, policy, parent):
    contract = _contract(parent)
    cases = {
        "VALUE_ABSENT": {"industry_code": "", "effective_from": DATES[0], "effective_to": None, "fact_status": "KNOWN", "available_at": "2018-01-02T17:00:00+08:00"},
        "INTERVAL_ENDED": {"industry_code": "SYNTHETIC_INDUSTRY", "effective_from": DATES[0], "effective_to": DATES[0], "fact_status": "KNOWN", "available_at": "2018-01-02T17:00:00+08:00"},
        "NOT_YET_EFFECTIVE": {"industry_code": "SYNTHETIC_INDUSTRY", "effective_from": 20180108, "effective_to": None, "fact_status": "KNOWN", "available_at": "2018-01-02T17:00:00+08:00"},
        "EXPLICIT_UNKNOWN": {"industry_code": "SYNTHETIC_INDUSTRY", "effective_from": DATES[0], "effective_to": None, "fact_status": "UNKNOWN", "available_at": "2018-01-02T17:00:00+08:00"},
        "LATE_EXCLUDED": {"industry_code": "SYNTHETIC_INDUSTRY", "effective_from": DATES[0], "effective_to": None, "fact_status": "KNOWN", "available_at": "2018-01-04T19:00:00+08:00"},
    }
    for reason, fields in cases.items():
        tables = flat_package(DATES, ["X"], close=10.0, factor=2.0, amount=100.0, amount_unit="CNY", circ=3.0, circ_unit="TEN_THOUSAND_CNY", industry_from=DATES[-1], circ_dates=[DATES[-1]])
        tables["industry"] = [{"ts_code": "X", "revision_id": "1", **fields}]
        built = build_snapshot(_commit(tmp_path / reason, tables, policy, contract, parent, f"C2-I01-{reason}"), contract=contract, policy=policy, mode="SYNTHETIC", root=tmp_path / f"{reason}-out")
        assert built.gate["status"] == "SYNTHETIC_SNAPSHOT_PARTIAL"
        assert built.gate["coverage_status"] == "PARTIAL"
        assert built.coverage["unknown_state_count"] > 0
        assert built.coverage["schema"] == "momentum_pullback.coverage_report.v2"
        gaps = [item for item in built.coverage["field_gaps"] if item["field"] == "industry" and item["trade_date"] == DATES[-1]]
        assert {item["reason"] for item in gaps} == {reason}
        assert built.panel.loc[built.panel.trade_date.eq(DATES[-1])].iloc[0].price_status == "TRADED"
        _folder, summary = run_snapshot_smoke(built.folder / "snapshot_manifest.json", contract=contract, policy=policy, mode="SYNTHETIC", root=tmp_path / f"{reason}-smoke")
        assert summary["status"] == "SYNTHETIC_SNAPSHOT_PARTIAL"
        assert summary["accepted"] is False
        assert summary["status"] != "SYNTHETIC_ENGINEERING_PASS"


def test_c2_i03_warmup_industry_stays_not_required_and_a_covered_value_is_complete(tmp_path, policy, parent):
    contract = _contract(parent)
    covered = flat_package(DATES, ["X"], close=10.0, factor=2.0, amount=100.0, amount_unit="CNY", circ=3.0, circ_unit="TEN_THOUSAND_CNY", industry_from=DATES[-1], circ_dates=[DATES[-1]])
    built = build_snapshot(_commit(tmp_path / "covered", covered, policy, contract, parent, "C2-I03"), contract=contract, policy=policy, mode="SYNTHETIC", root=tmp_path / "covered-out")
    assert built.gate["status"] == "SYNTHETIC_SNAPSHOT_READY"
    assert built.gate["coverage_status"] == "COMPLETE"
    assert built.coverage["unknown_state_count"] == 0
    assert built.coverage["consumers"]["industry_circ_mv"]["not_required"] > 0
    assert built.coverage["field_gaps"] == []
    assert pd.isna(built.panel.loc[built.panel.trade_date.eq(DATES[0])].iloc[0].industry_code)


def test_c2_lineage_keys_hit_one_source_row_and_keep_the_event_effective_date(tmp_path, policy, parent):
    contract = _contract(parent)
    tables = _base([DATES[0], DATES[-1]], [DATES[0], DATES[-1]])
    tables["halts"] = [{"ts_code": "X", "trade_date": DATES[1], "revision_id": "4", "halt_scope": "FULL_DAY", "fact_status": "KNOWN", "available_at": "2018-01-03T17:00:00+08:00"}]
    tables["industry"] = [
        {"ts_code": "X", "revision_id": "1", "industry_code": "OLD", "effective_from": DATES[-1], "effective_to": None, "available_at": "2018-01-04T16:00:00+08:00"},
        {"ts_code": "X", "revision_id": "2", "industry_code": "SYNTHETIC_INDUSTRY", "effective_from": DATES[-1], "effective_to": None, "available_at": "2018-01-04T17:00:00+08:00"},
    ]
    directory = tmp_path / "src"
    built = build_snapshot(_commit(directory, tables, policy, contract, parent, "C2-L01"), contract=contract, policy=policy, mode="SYNTHETIC", root=tmp_path / "out")
    populated = built.lineage.loc[built.lineage.source_primary_key.ne("")]
    assert not populated.empty
    for record in populated.itertuples(index=False):
        hits = _hits(directory, record.source_table, record.source_primary_key)
        assert len(hits) == 1
        assert str(hits[0]["revision_id"]) == str(record.revision_id)
        assert record.source_file_sha256 == hashlib.sha256((directory / f"{record.source_table}.json").read_bytes()).hexdigest()
    industry = built.lineage.loc[lambda frame: frame.field_group.eq("industry") & frame.trade_date.eq(DATES[-1])].iloc[0]
    industry_key = json.loads(industry.source_primary_key)
    assert industry_key == {"effective_from": DATES[-1], "revision_id": "2", "ts_code": "X"}
    assert "trade_date" not in industry_key
    assert int(industry.trade_date) == DATES[-1]
    assert industry.available_at.startswith("2018-01-04T17:00:00")
    membership = built.lineage.loc[lambda frame: frame.field_group.eq("membership") & frame.trade_date.eq(DATES[-1])].iloc[0]
    membership_key = json.loads(membership.source_primary_key)
    assert membership_key["effective_from"] == DATES[0]
    assert membership_key["effective_from"] != int(membership.trade_date)
    assert built.lineage.loc[lambda frame: frame.trade_date.eq(DATES[1]) & frame.field_group.eq("price_raw")].empty
    derived = built.lineage.loc[lambda frame: frame.trade_date.eq(DATES[1]) & frame.field_group.eq("amount")].iloc[0]
    assert derived.source_table == "halts" and derived.derivation == "VERIFIED_HALT_ZERO"


def test_c2_l02_unresolved_or_duplicate_primary_keys_are_rejected(tmp_path, policy, parent):
    contract = _contract(parent)
    tables = _base()
    with pytest.raises(GateError) as missing:
        build_snapshot(_commit(tmp_path / "missing", tables, policy, contract, parent, "C2-L02-MISSING", primary_keys={"industry": ["ts_code", "trade_date", "revision_id"]}), contract=contract, policy=policy, mode="SYNTHETIC", root=tmp_path / "missing-out")
    assert missing.value.code == "SOURCE_MANIFEST_INVALID"
    assert missing.value.details["reason"] == "PRIMARY_KEY_COLUMN_MISSING"
    tables["prices_raw"].append(dict(tables["prices_raw"][0]))
    with pytest.raises(GateError) as duplicate:
        build_snapshot(_commit(tmp_path / "duplicate", tables, policy, contract, parent, "C2-L02-DUP"), contract=contract, policy=policy, mode="SYNTHETIC", root=tmp_path / "duplicate-out")
    assert duplicate.value.code == "DUPLICATE_OR_CONFLICTING_KEYS"

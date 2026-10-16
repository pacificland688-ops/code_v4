"""Normalized snapshot: hand values, blocking grids, and commit-last reads."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from momentum_pullback.casebook import hand_contract, hand_panel
from momentum_pullback.contracts import ROOT, GateError, file_hash, load_contract
from momentum_pullback.features import build_features
from momentum_pullback.snapshot import build_snapshot, read_snapshot
from momentum_pullback.source_bindings import load_snapshot_policy
from tests.momentum_pullback.snapshot_sources import commit_tables, flat_package, hand_tables, narrow_contract

POLICY_PATH = ROOT / "configs/momentum_pullback/snapshot_policy_v0_1.yaml"
EXPECTED_PATH = ROOT / "momentum_pullback/fixtures/snapshot_expected_v0_1.json"
DATES = [20180102, 20180103, 20180104]


@pytest.fixture(scope="module")
def policy():
    return load_snapshot_policy(POLICY_PATH)


@pytest.fixture(scope="module")
def parent():
    return load_contract(ROOT / "configs/momentum_pullback/research_contract_v0_2.yaml")


@pytest.fixture(scope="module")
def expected():
    return json.loads(EXPECTED_PATH.read_text(encoding="utf-8"))


def _minimal(directory: Path, policy, parent, case, **overrides):
    contract = narrow_contract(parent, DATES[0], DATES[-1], DATES[-1])
    tables = flat_package(
        DATES, ["X"], close=case["expected_adj_close"], factor=case["stored_factor"],
        amount=case["amount_value"], amount_unit=case["amount_unit"], circ=case["circ_mv_value"], circ_unit=case["circ_mv_unit"],
        industry_from=DATES[-1], industry_available=DATES[-1], circ_dates=[DATES[-1]],
    )
    tables.update(overrides.pop("tables", {}))
    for name, rows in overrides.pop("replace", {}).items():
        tables[name] = rows
    manifest = commit_tables(directory, tables, policy=policy, contract=contract, parent_hash=parent.hash, case_id="B-SNAP-01", amount_unit=case["amount_unit"], circ_unit=case["circ_mv_unit"], **overrides)
    return manifest, contract


def _blocked(call):
    with pytest.raises(GateError) as caught:
        call()
    folder = Path(caught.value.details["artifact_dir"])
    assert not (folder / "snapshot_manifest.json").exists()
    assert not (folder / "normalized_panel.parquet").exists()
    blocked = json.loads((folder / "blocked.json").read_text(encoding="utf-8"))
    assert blocked["status"] == "DATA_BLOCKED"
    assert blocked["reason"] == caught.value.code
    assert blocked["outcomes_enabled"] is False
    assert blocked["consumable_panel"] is False
    assert blocked["quality_status"] != "DATA_READY_FOR_ENGINEERING"
    return caught.value, folder


def test_snapshot_code_does_not_invent_a_calendar_or_hand_panel():
    text = (ROOT / "momentum_pullback/snapshot.py").read_text(encoding="utf-8")
    assert "bdate_range" not in text
    assert "hand_panel" not in text
    assert "tushare" not in text
    assert "import requests" not in text
    assert "urllib" not in text


def test_minimal_conversion_matches_the_hand_numbers(tmp_path, policy, parent, expected):
    case = expected["cases"]["B-SNAP-01"]
    manifest, contract = _minimal(tmp_path / "min", policy, parent, case)
    built = build_snapshot(manifest, contract=contract, policy=policy, mode="SYNTHETIC", root=tmp_path / "out")
    row = built.panel.loc[built.panel.trade_date.eq(DATES[-1])].iloc[0]
    assert built.gate["status"] == case["quality_status"]
    assert built.manifest["diagnostic_only"] is False
    assert built.manifest["outcomes_enabled"] is False
    assert built.gate["status"] != "DATA_READY_FOR_ENGINEERING"
    assert float(row.adj_close) == case["expected_adj_close"]
    assert float(row.raw_close) == case["raw_close"]
    assert float(row.amount_cny) == case["expected_amount_cny"]
    assert float(row.circ_mv_cny) == case["expected_circ_mv_cny"]
    assert row.price_status == "TRADED"
    lineage = built.lineage.loc[lambda frame: frame.ts_code.eq("X") & frame.trade_date.eq(DATES[-1]) & frame.field_group.eq("price_adj")].iloc[0]
    assert lineage.selection_reason == case["selection_reason"]
    assert lineage.derivation == case["price_derivation"]
    assert json.loads(lineage.source_primary_key) == {"ts_code": "X", "trade_date": DATES[-1], "revision_id": "1"}
    assert lineage.source_file_sha256 == file_hash(manifest.parent / "prices_adj.json")
    warmup = built.panel.loc[built.panel.trade_date.eq(DATES[0])].iloc[0]
    assert warmup.price_status == "TRADED" and pd.isna(warmup.industry_code) and pd.isna(warmup.industry_available_at)


def test_hand_case_normalized_values_match_the_declared_panel(tmp_path, policy, parent, expected):
    case = expected["cases"]["B-HAND-01"]
    tables, dates = hand_tables(case["stored_factor"])
    draft = hand_contract(parent)
    manifest = commit_tables(tmp_path / "hand", tables, policy=policy, contract=draft, parent_hash=parent.hash, case_id="HAND-20x155", amount_unit=case["amount_unit"], circ_unit=case["circ_mv_unit"])
    built = build_snapshot(manifest, contract=draft, policy=policy, mode="SYNTHETIC", root=tmp_path / "out", oracle_files=[EXPECTED_PATH])
    panel, _ = hand_panel()
    merged = panel.merge(built.panel, on=["ts_code", "trade_date"], suffixes=("_hand", "_snapshot"))
    for column in ["adj_open", "adj_high", "adj_low", "adj_close", "amount_cny", "circ_mv_cny"]:
        pd.testing.assert_series_equal(merged[column + "_hand"], merged[column + "_snapshot"], check_names=False)
    assert built.panel.price_status.eq("TRADED").all()
    assert built.gate["status"] == case["quality_status"]
    assert len(built.panel) == len(panel)
    for cell in case["cells"]:
        actual = built.panel.loc[lambda frame: frame.ts_code.eq(cell["ts_code"]) & frame.trade_date.eq(cell["trade_date"])].iloc[0]
        for key, value in cell.items():
            if key in {"ts_code", "trade_date", "industry_code", "price_status"}:
                assert actual[key] == value
            else:
                assert float(actual[key]) == value
    features = build_features(built.panel, dates, draft, roster=built.roster, certified_calendar=dates)
    assert len(features) == len(panel)
    assert "run_id" not in json.dumps({"snapshot_id": built.manifest["snapshot_id"]})


def test_missing_security_or_trade_row_blocks_without_a_consumable_panel(tmp_path, policy, parent, expected):
    code = expected["cases"]["B-GRID-01"]["error"]
    contract = narrow_contract(parent, DATES[0], DATES[-1], DATES[-1])
    full = flat_package(DATES, ["X", "Y"], close=10.0, factor=2.0, amount=12.5, amount_unit="THOUSAND_CNY", circ=3.0, circ_unit="TEN_THOUSAND_CNY", industry_from=DATES[-1], circ_dates=[DATES[-1]])
    full["prices_raw"] = [row for row in full["prices_raw"] if row["ts_code"] != "Y"]
    full["prices_adj"] = [row for row in full["prices_adj"] if row["ts_code"] != "Y"]
    manifest = commit_tables(tmp_path / "grid", full, policy=policy, contract=contract, parent_hash=parent.hash, case_id="B-GRID", amount_unit="THOUSAND_CNY", circ_unit="TEN_THOUSAND_CNY")
    error, _ = _blocked(lambda: build_snapshot(manifest, contract=contract, policy=policy, mode="SYNTHETIC", root=tmp_path / "out1"))
    assert error.code == code and "Y" in error.details["missing_codes"]
    one = flat_package(DATES, ["X"], close=10.0, factor=2.0, amount=12.5, amount_unit="THOUSAND_CNY", circ=3.0, circ_unit="TEN_THOUSAND_CNY", industry_from=DATES[-1], circ_dates=[DATES[-1]])
    one["prices_raw"] = [row for row in one["prices_raw"] if row["trade_date"] != DATES[1]]
    one["prices_adj"] = [row for row in one["prices_adj"] if row["trade_date"] != DATES[1]]
    manifest = commit_tables(tmp_path / "row", one, policy=policy, contract=contract, parent_hash=parent.hash, case_id="B-GRID-ROW", amount_unit="THOUSAND_CNY", circ_unit="TEN_THOUSAND_CNY")
    error, _ = _blocked(lambda: build_snapshot(manifest, contract=contract, policy=policy, mode="SYNTHETIC", root=tmp_path / "out2"))
    assert error.code == code and error.details["missing"][0]["trade_date"] == DATES[1]


def test_bad_prices_and_unpaired_keys_do_not_write_ready(tmp_path, policy, parent, expected):
    case = expected["cases"]["B-PRICE-01"]
    base = expected["cases"]["B-SNAP-01"]
    contract = narrow_contract(parent, DATES[0], DATES[-1], DATES[-1])

    def run(mutate, label):
        tables = flat_package(DATES, ["X"], close=10.0, factor=2.0, amount=12.5, amount_unit="THOUSAND_CNY", circ=3.0, circ_unit="TEN_THOUSAND_CNY", industry_from=DATES[-1], circ_dates=[DATES[-1]])
        mutate(tables)
        manifest = commit_tables(tmp_path / label, tables, policy=policy, contract=contract, parent_hash=parent.hash, case_id=label, amount_unit="THOUSAND_CNY", circ_unit="TEN_THOUSAND_CNY")
        error, _ = _blocked(lambda: build_snapshot(manifest, contract=contract, policy=policy, mode="SYNTHETIC", root=tmp_path / (label + "-out")))
        return error

    duplicate = run(lambda tables: tables["prices_raw"].append(dict(tables["prices_raw"][0])), "duplicate")
    assert duplicate.code == case["duplicate_error"]
    mismatch = run(lambda tables: tables["prices_adj"].pop(), "mismatch")
    assert mismatch.code == case["key_mismatch_error"]
    def _ohlc(tables):
        tables["prices_raw"][0]["low"] = 9
        tables["prices_adj"][0]["adj_low"] = 18
    ohlc = run(_ohlc, "ohlc")
    assert ohlc.code == case["ohlc_error"]
    def _bad_scale(tables):
        for raw, adj in zip(tables["prices_raw"], tables["prices_adj"]):
            for name in ["open", "high", "low", "close"]:
                adj["adj_" + name] = raw[name]
            adj["adj_factor"] = 2.0
    scale = run(_bad_scale, "scale")
    assert scale.code == case["scale_error"]
    missing = run(lambda tables: [row.pop("adj_factor") for row in tables["prices_adj"]], "factor")
    assert missing.code == case["factor_missing_error"]
    def _zero(tables):
        for raw, adj in zip(tables["prices_raw"], tables["prices_adj"]):
            raw.update(open=0.0, high=0.0, low=0.0, close=0.0)
            adj.update(adj_open=0.0, adj_high=0.0, adj_low=0.0, adj_close=0.0)
    nonpositive = run(_zero, "nonpositive")
    assert nonpositive.code == case["nonpositive_error"]
    assert base["quality_status"] == "SYNTHETIC_SNAPSHOT_READY"


def test_repeated_snapshots_keep_one_identity(tmp_path, policy, parent, expected):
    case = expected["cases"]["B-SNAP-01"]
    manifest, contract = _minimal(tmp_path / "same", policy, parent, case)
    first = build_snapshot(manifest, contract=contract, policy=policy, mode="SYNTHETIC", root=tmp_path / "a")
    second = build_snapshot(manifest, contract=contract, policy=policy, mode="SYNTHETIC", root=tmp_path / "b")
    assert first.manifest["snapshot_id"] == second.manifest["snapshot_id"]
    assert first.manifest["logical_hashes"] == second.manifest["logical_hashes"]
    assert first.manifest["run_id"] != second.manifest["run_id"]
    for name in ["normalized_panel.parquet", "universe_daily.parquet", "calendar.parquet", "lineage.parquet"]:
        assert (first.folder / name).read_bytes() == (second.folder / name).read_bytes()
    restored = read_snapshot(first.folder / "snapshot_manifest.json", contract=contract, policy=policy, mode="SYNTHETIC")
    assert restored.manifest["snapshot_id"] == first.manifest["snapshot_id"]


def test_failed_commit_is_unreadable_and_leaves_the_previous_snapshot(tmp_path, policy, parent, expected):
    case = expected["cases"]["B-SNAP-01"]
    codes = expected["cases"]["B-WRITE-01"]
    manifest, contract = _minimal(tmp_path / "keep", policy, parent, case)
    original = build_snapshot(manifest, contract=contract, policy=policy, mode="SYNTHETIC", root=tmp_path / "original")
    before = {path.name: file_hash(path) for path in original.folder.iterdir() if path.is_file()}

    def _fail(folder: Path) -> None:
        raise GateError("SNAPSHOT_COVERAGE_INCOMPLETE", "INJECTED")

    error, folder = _blocked(lambda: build_snapshot(manifest, contract=contract, policy=policy, mode="SYNTHETIC", root=tmp_path / "retry", before_commit=_fail))
    assert error.code == "SNAPSHOT_COVERAGE_INCOMPLETE"
    assert folder != original.folder
    with pytest.raises(GateError, match="SOURCE_MANIFEST_INVALID") as caught:
        read_snapshot(folder / "snapshot_manifest.json", contract=contract, policy=policy, mode="SYNTHETIC")
    assert caught.value.details == codes["unreadable"]
    assert {path.name: file_hash(path) for path in original.folder.iterdir() if path.is_file()} == before
    retried = build_snapshot(manifest, contract=contract, policy=policy, mode="SYNTHETIC", root=tmp_path / "retry-ok")
    assert retried.folder != folder
    assert retried.manifest["snapshot_id"] == original.manifest["snapshot_id"]


def test_edited_snapshot_cannot_bypass_the_source_calendar(tmp_path, policy, parent, expected):
    case = expected["cases"]["B-SNAP-01"]
    manifest, contract = _minimal(tmp_path / "cal", policy, parent, case)
    built = build_snapshot(manifest, contract=contract, policy=policy, mode="SYNTHETIC", root=tmp_path / "out")
    panel = built.folder / "normalized_panel.parquet"
    panel.write_bytes(panel.read_bytes() + b" ")
    with pytest.raises(GateError, match=expected["cases"]["B-HASH-01"]["error"]):
        read_snapshot(built.folder / "snapshot_manifest.json", contract=contract, policy=policy, mode="SYNTHETIC")
    short = flat_package(DATES[:-1], ["X"], close=10.0, factor=2.0, amount=12.5, amount_unit="THOUSAND_CNY", circ=3.0, circ_unit="TEN_THOUSAND_CNY", industry_from=DATES[1], industry_available=DATES[1], circ_dates=[DATES[1]])
    short_contract = narrow_contract(parent, DATES[0], DATES[1], DATES[1])
    claimed = commit_tables(tmp_path / "claimed", short, policy=policy, contract=short_contract, parent_hash=parent.hash, case_id="B-CAL", amount_unit="THOUSAND_CNY", circ_unit="TEN_THOUSAND_CNY", calendar_dates=DATES)
    error, _ = _blocked(lambda: build_snapshot(claimed, contract=short_contract, policy=policy, mode="SYNTHETIC", root=tmp_path / "claimed-out"))
    assert error.code == expected["cases"]["B-CAL-01"]["error"]


def test_verified_halt_is_zero_and_a_late_halt_is_not(tmp_path, policy, parent, expected):
    case = expected["cases"]["B-HALT-01"]
    contract = narrow_contract(parent, DATES[0], DATES[-1], DATES[-1])
    tables = flat_package(DATES, ["X"], close=10.0, factor=2.0, amount=100.0, amount_unit="CNY", circ=3.0, circ_unit="TEN_THOUSAND_CNY", industry_from=DATES[-1], circ_dates=[DATES[-1]], price_dates=[DATES[0], DATES[-1]], amount_dates=[DATES[0], DATES[-1]])
    tables["halts"] = [{"ts_code": "X", "trade_date": DATES[1], "revision_id": "1", "halt_scope": "FULL_DAY", "available_at": "2018-01-03T17:00:00+08:00"}]
    manifest = commit_tables(tmp_path / "halt", tables, policy=policy, contract=contract, parent_hash=parent.hash, case_id="B-HALT", circ_unit="TEN_THOUSAND_CNY")
    built = build_snapshot(manifest, contract=contract, policy=policy, mode="SYNTHETIC", root=tmp_path / "halt-out")
    row = built.panel.loc[built.panel.trade_date.eq(DATES[1])].iloc[0]
    assert row.price_status == case["price_status"]
    assert float(row.amount_cny) == case["amount_cny"]
    assert row.amount_derivation == case["derivation"]
    assert set(built.panel.trade_date) == set(DATES)
    late = flat_package(DATES, ["X"], close=10.0, factor=2.0, amount=100.0, amount_unit="CNY", circ=3.0, circ_unit="TEN_THOUSAND_CNY", industry_from=DATES[-1], circ_dates=[DATES[-1]], price_dates=[DATES[0], DATES[-1]], amount_dates=DATES)
    late["halts"] = [{"ts_code": "X", "trade_date": DATES[1], "revision_id": "1", "halt_scope": "FULL_DAY", "available_at": "2018-01-03T19:00:00+08:00"}]
    late_manifest = commit_tables(tmp_path / "late", late, policy=policy, contract=contract, parent_hash=parent.hash, case_id="B-HALT-LATE", circ_unit="TEN_THOUSAND_CNY")
    late_built = build_snapshot(late_manifest, contract=contract, policy=policy, mode="SYNTHETIC", root=tmp_path / "late-out")
    late_row = late_built.panel.loc[late_built.panel.trade_date.eq(DATES[1])].iloc[0]
    assert late_built.manifest["diagnostic_only"] is True
    assert late_row.price_status != case["price_status"]
    assert float(late_row.amount_cny) == 100.0
    assert late_row.amount_derivation != case["derivation"]
    partial = flat_package(DATES, ["X"], close=10.0, factor=2.0, amount=100.0, amount_unit="CNY", circ=3.0, circ_unit="TEN_THOUSAND_CNY", industry_from=DATES[-1], circ_dates=[DATES[-1]], price_dates=[DATES[0], DATES[-1]], amount_dates=[DATES[0], DATES[-1]])
    partial["halts"] = [{"ts_code": "X", "trade_date": DATES[1], "revision_id": "1", "halt_scope": "PARTIAL_DAY", "available_at": "2018-01-03T17:00:00+08:00"}]
    partial_manifest = commit_tables(tmp_path / "partial", partial, policy=policy, contract=contract, parent_hash=parent.hash, case_id="B-HALT-PARTIAL", circ_unit="TEN_THOUSAND_CNY")
    error, _ = _blocked(lambda: build_snapshot(partial_manifest, contract=contract, policy=policy, mode="SYNTHETIC", root=tmp_path / "partial-out"))
    assert error.code == "SNAPSHOT_COVERAGE_INCOMPLETE"


def test_explicit_unknown_inside_the_window_is_partial_and_warmup_industry_is_not_required(tmp_path, policy, parent, expected):
    case = expected["cases"]["B-COV-01"]
    snap = expected["cases"]["B-SNAP-01"]
    manifest, contract = _minimal(tmp_path / "warm", policy, parent, snap)
    built = build_snapshot(manifest, contract=contract, policy=policy, mode="SYNTHETIC", root=tmp_path / "warm-out")
    assert built.gate["status"] == case["quality_status"]
    assert built.coverage["consumers"]["industry_circ_mv"]["not_required"] > 0
    assert built.panel.loc[built.panel.trade_date.lt(DATES[-1]), "price_status"].eq("TRADED").all()
    unknown = flat_package(DATES, ["X"], close=10.0, factor=2.0, amount=12.5, amount_unit="THOUSAND_CNY", circ=3.0, circ_unit="TEN_THOUSAND_CNY", industry_from=DATES[-1], circ_dates=[DATES[-1]], industry_status="UNKNOWN")
    unknown_manifest = commit_tables(tmp_path / "unknown", unknown, policy=policy, contract=contract, parent_hash=parent.hash, case_id="B-COV-UNKNOWN", amount_unit="THOUSAND_CNY", circ_unit="TEN_THOUSAND_CNY")
    partial = build_snapshot(unknown_manifest, contract=contract, policy=policy, mode="SYNTHETIC", root=tmp_path / "unknown-out")
    assert partial.gate["status"] == case["explicit_unknown_status"]
    assert partial.manifest["diagnostic_only"] is True
    reread = read_snapshot(partial.folder / "snapshot_manifest.json", contract=contract, policy=policy, mode="SYNTHETIC")
    assert reread.gate["status"] == case["explicit_unknown_status"] and reread.manifest["diagnostic_only"] is True
    output = partial.panel.loc[partial.panel.trade_date.eq(DATES[-1])].iloc[0]
    assert output.price_status == "TRADED" and pd.isna(output.industry_code)


def test_membership_intervals_follow_availability_and_effective_dates(tmp_path, policy, parent, expected):
    case = expected["cases"]["B-PIT-01"]
    contract = narrow_contract(parent, DATES[0], DATES[-1], DATES[-1])
    tables = flat_package(DATES, ["X"], close=10.0, factor=2.0, amount=10.0, amount_unit="CNY", circ=3.0, circ_unit="TEN_THOUSAND_CNY", industry_from=DATES[-1], circ_dates=[DATES[-1]])
    tables["membership"] = [
        {"ts_code": "X", "revision_id": "1", "is_member": True, "effective_from": 20180102, "effective_to": 20180102, "available_at": "2018-01-02T17:00:00+08:00"},
        {"ts_code": "X", "revision_id": "1", "is_member": True, "effective_from": 20180104, "effective_to": None, "available_at": "2018-01-04T17:00:00+08:00"},
    ]
    manifest = commit_tables(tmp_path / "pit", tables, policy=policy, contract=contract, parent_hash=parent.hash, case_id="B-PIT", circ_unit="TEN_THOUSAND_CNY")
    built = build_snapshot(manifest, contract=contract, policy=policy, mode="SYNTHETIC", root=tmp_path / "pit-out")
    flags = {int(row.trade_date): bool(row.is_member) for row in built.panel.itertuples(index=False)}
    known = {int(row.trade_date): bool(row.membership_known) for row in built.panel.itertuples(index=False)}
    assert flags[case["member_dates"][0]] is True and flags[case["reentry_date"]] is True
    assert flags[case["gap_date"]] is False and known[case["gap_date"]] is True
    future = flat_package(DATES, ["X"], close=10.0, factor=2.0, amount=10.0, amount_unit="CNY", circ=3.0, circ_unit="TEN_THOUSAND_CNY", industry_from=DATES[-1], circ_dates=[DATES[-1]])
    future["membership"] = [{"ts_code": "X", "revision_id": "1", "is_member": True, "effective_from": 20180104, "effective_to": None, "available_at": "2018-01-02T17:00:00+08:00"}]
    future_manifest = commit_tables(tmp_path / "future", future, policy=policy, contract=contract, parent_hash=parent.hash, case_id="B-PIT-FUTURE", circ_unit="TEN_THOUSAND_CNY")
    future_built = build_snapshot(future_manifest, contract=contract, policy=policy, mode="SYNTHETIC", root=tmp_path / "future-out")
    early = future_built.panel.loc[future_built.panel.trade_date.eq(case["not_yet_effective_date"])].iloc[0]
    assert bool(early.membership_known) is True and bool(early.is_member) is False and int(early.membership_effective_from) == 20180104
    late = flat_package(DATES, ["X"], close=10.0, factor=2.0, amount=10.0, amount_unit="CNY", circ=3.0, circ_unit="TEN_THOUSAND_CNY", industry_from=DATES[-1], circ_dates=[DATES[-1]])
    late["membership"] = [{"ts_code": "X", "revision_id": "1", "is_member": True, "effective_from": 20180102, "effective_to": None, "available_at": "2018-01-04T17:00:00+08:00"}]
    late_manifest = commit_tables(tmp_path / "late-member", late, policy=policy, contract=contract, parent_hash=parent.hash, case_id="B-PIT-LATE", circ_unit="TEN_THOUSAND_CNY")
    late_built = build_snapshot(late_manifest, contract=contract, policy=policy, mode="SYNTHETIC", root=tmp_path / "late-member-out")
    hidden = late_built.panel.loc[late_built.panel.trade_date.eq(case["not_yet_available_date"])].iloc[0]
    assert bool(hidden.membership_known) is False and late_built.manifest["diagnostic_only"] is True


def test_unsupported_listing_and_real_mode_publish_no_panel(tmp_path, policy, parent, expected):
    contract = narrow_contract(parent, DATES[0], DATES[-1], DATES[-1])
    tables = flat_package(DATES, ["Y"], close=10.0, factor=2.0, amount=10.0, amount_unit="CNY", circ=3.0, circ_unit="TEN_THOUSAND_CNY", industry_from=DATES[-1], circ_dates=[DATES[-1]])
    tables["lifecycle"] = [{"ts_code": "Y", "listed_on": 20180103, "delisted_on": None}]
    manifest = commit_tables(tmp_path / "life", tables, policy=policy, contract=contract, parent_hash=parent.hash, case_id="B-LIFE", circ_unit="TEN_THOUSAND_CNY")
    error, _ = _blocked(lambda: build_snapshot(manifest, contract=contract, policy=policy, mode="SYNTHETIC", root=tmp_path / "life-out"))
    assert error.code == expected["cases"]["B-LIFE-01"]["error"]
    assert error.details["details"] == "Y" or error.details.get("details") == "Y" or "Y" in str(error.details)
    with pytest.raises(GateError, match="SNAPSHOT_MODE_MISMATCH"):
        build_snapshot(manifest, contract=contract, policy=policy, mode="REAL", root=tmp_path / "real-command")
    real = commit_tables(tmp_path / "real", tables, policy=policy, contract=contract, parent_hash=parent.hash, case_id="B-REAL", circ_unit="TEN_THOUSAND_CNY", mode="REAL", review_kind="REAL_CERTIFIED")
    with pytest.raises(GateError, match="REVIEW_RECEIPT_UNTRUSTED"):
        build_snapshot(real, contract=contract, policy=policy, mode="REAL", root=tmp_path / "real-out")
    assert not list(tmp_path.glob("**/normalized_panel.parquet"))

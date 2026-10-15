from __future__ import annotations

import copy

import numpy as np
import pandas as pd
import pytest

from momentum_pullback.casebook import hand_panel
from momentum_pullback.contracts import GateError, checkpoint, file_hash, load_contract, require_outcome_permission, restore_checkpoint, validate_contract
from momentum_pullback.data_adapter import frame_hash, validate_join
from momentum_pullback.features import build_features
from momentum_pullback.runtime import create_run, verify_run_inputs


def price_pair():
    raw = pd.DataFrame({"ts_code": ["X"], "trade_date": [20180102], "open": [10.0], "high": [12.0], "low": [9.0], "close": [11.0]})
    adjusted = raw.rename(columns={column: "adj_" + column for column in ["open", "high", "low", "close"]})
    adjusted[["adj_open", "adj_high", "adj_low", "adj_close"]] *= 2
    adjusted["adj_factor"] = 2.0
    return raw, adjusted


@pytest.mark.parametrize("side,conflict", [("raw", False), ("raw", True), ("adjusted", False), ("adjusted", True)])
def test_duplicate_and_conflicting_keys_never_keep_last(side, conflict):
    raw, adjusted = price_pair()
    source = raw if side == "raw" else adjusted
    duplicate = source.copy()
    if conflict:
        duplicate.loc[0, "open" if side == "raw" else "adj_open"] += 0.01
    source = pd.concat([source, duplicate], ignore_index=True)
    with pytest.raises(GateError, match="DUPLICATE_OR_CONFLICTING_KEYS"):
        validate_join(source if side == "raw" else raw, source if side == "adjusted" else adjusted)


@pytest.mark.parametrize("column,value,reason", [("open", np.nan, "NONFINITE"), ("high", np.inf, "NONFINITE"), ("low", 0.0, "NONFINITE"), ("close", -1.0, "NONFINITE"), ("open", 13.0, "OHLC")])
def test_invalid_raw_prices_block(column, value, reason):
    raw, adjusted = price_pair()
    raw.loc[0, column] = value
    with pytest.raises(GateError, match=reason):
        validate_join(raw, adjusted)


@pytest.mark.parametrize("value", [None, 0.0, -1.0, np.inf])
def test_invalid_factor_blocks_without_inference(value):
    raw, adjusted = price_pair()
    adjusted.loc[0, "adj_factor"] = value
    with pytest.raises(GateError, match="ADJUSTMENT_FACTOR_INVALID"):
        validate_join(raw, adjusted)


def test_scale_and_exact_keysets():
    raw, adjusted = price_pair()
    assert len(validate_join(raw, adjusted)) == 1
    adjusted.loc[0, "adj_factor"] = 3.0
    with pytest.raises(GateError, match="ADJUSTED_PRICE_SCALE_MISMATCH"):
        validate_join(raw, adjusted)
    adjusted.loc[0, "trade_date"] = 20180103
    with pytest.raises(GateError, match="RAW_ADJUSTED_KEY_SET_MISMATCH"):
        validate_join(raw, adjusted)


def test_document_change_requires_new_binding(base_contract, tmp_path):
    payload = base_contract.payload
    doc = tmp_path / "rule.md"
    doc.write_text("first draft", encoding="utf-8")
    payload["documents"] = [{"path": "rule.md", "sha256": file_hash(doc)}]
    validate_contract(payload, root=tmp_path)
    doc.write_text("another draft", encoding="utf-8")
    with pytest.raises(GateError, match="DOCUMENT_BINDING_CHANGED"):
        validate_contract(payload, root=tmp_path)


@pytest.mark.parametrize("changed", ["contract", "code", "history", "roster", "origin", "cutoff"])
def test_checkpoint_identity_mismatch_blocks(base_contract, changed):
    args = dict(contract=base_contract, code_hash="implementation-A", feature_origin=20150105, processed_cutoff=20171229, history_hash="history-A", roster_hash="roster-A")
    saved = checkpoint({"X": {"touch_no": 1}}, **args)
    newer = args.copy()
    if changed == "contract":
        payload = base_contract.payload
        payload["matching"]["caliper"] = 0.19
        newer["contract"] = validate_contract(payload)
    elif changed == "code":
        newer["code_hash"] = "implementation-B"
    elif changed == "history":
        newer["history_hash"] = "history-B"
    elif changed == "roster":
        newer["roster_hash"] = "roster-B"
    elif changed == "origin":
        newer["feature_origin"] = 20150106
    else:
        newer["processed_cutoff"] = 20180102
    with pytest.raises(GateError, match="CHECKPOINT_IDENTITY_MISMATCH"):
        restore_checkpoint(saved, **newer)
    assert restore_checkpoint(saved, **args) == saved["state"]


def test_history_prefix_append_and_repair_are_different():
    panel, _ = hand_panel()
    prefix = panel[panel.trade_date.le(20171229)]
    assert frame_hash(prefix) == frame_hash(panel, cutoff=20171229)
    changed = panel.copy()
    changed.loc[changed.trade_date.eq(20180105), "adj_close"] += 0.1
    assert frame_hash(changed, cutoff=20171229) == frame_hash(prefix)
    changed.loc[changed.trade_date.eq(20171229), "adj_close"] += 0.1
    assert frame_hash(changed, cutoff=20171229) != frame_hash(prefix)


def test_run_inputs_are_immutable_and_draft_ids_are_distinct(base_contract, tmp_path):
    source = tmp_path / "source.json"
    source.write_text("one", encoding="utf-8")
    _, first = create_run(base_contract, "unit", [source], root=tmp_path)
    _, again = create_run(base_contract, "unit", [source], root=tmp_path)
    assert first["content_id"] == again["content_id"]
    assert first["run_id"] != again["run_id"]
    assert first["contract_status"] == "DRAFT"
    verify_run_inputs(first)
    source.write_text("two", encoding="utf-8")
    with pytest.raises(GateError, match="INPUT_CONTENT_CHANGED_DURING_RUN"):
        verify_run_inputs(first)


def test_outcomes_cannot_be_opened_by_proposed_status(base_contract):
    with pytest.raises(GateError, match="OUTCOMES_NOT_IMPLEMENTED_OR_AUTHORIZED"):
        require_outcome_permission(base_contract)
    payload = copy.deepcopy(base_contract.payload)
    payload["outcomes_enabled"] = True
    with pytest.raises(GateError, match="ENGINEERING_ONLY_CONTRACT_REQUIRED"):
        validate_contract(payload)


def test_duplicate_yaml_key_is_not_keep_last(tmp_path):
    path = tmp_path / "contract.yaml"
    path.write_text("status: DRAFT\nstatus: FROZEN\n", encoding="utf-8")
    with pytest.raises(GateError, match="DUPLICATE_CONTRACT_KEY"):
        load_contract(path)


def test_checkpoint_state_content_is_protected(base_contract):
    args = dict(contract=base_contract, code_hash="code", feature_origin=20150105, processed_cutoff=20171229, history_hash="history", roster_hash="roster")
    saved = checkpoint({"touch_no": 1}, **args)
    saved["state"]["touch_no"] = 0
    with pytest.raises(GateError, match="CHECKPOINT_STATE_CONTENT_CHANGED"):
        restore_checkpoint(saved, **args)


@pytest.mark.parametrize("section,key,value", [("features", "top_fraction", "0.2"), ("matching", "caliper", True), ("matching", "distance", "OTHER"), ("scope", "output_start", None)])
def test_unimplemented_or_ambiguous_contract_is_blocked(base_contract, section, key, value):
    payload = base_contract.payload
    payload[section][key] = value
    with pytest.raises(GateError):
        validate_contract(payload)


@pytest.mark.parametrize("kind", ["boolean", "timezone", "grid", "covariate"])
def test_normalized_foundation_errors_block(hand_draft, kind):
    panel, calendar = hand_panel()
    panel = panel[panel.ts_code.eq("A")].copy().reset_index(drop=True)
    if kind == "boolean":
        panel["membership_known"] = panel["membership_known"].astype(object)
        panel.loc[0, "membership_known"] = np.nan
    elif kind == "timezone":
        panel.loc[0, "price_available_at"] = "2017-06-02T17:00:00"
    elif kind == "grid":
        panel = panel.iloc[1:]
    else:
        panel.loc[0, "amount_cny"] = np.inf
    with pytest.raises(GateError):
        build_features(panel, calendar, hand_draft)

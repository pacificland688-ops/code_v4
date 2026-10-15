"""Source labels come from evidence. Missing PIT proof stays unknown."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from momentum_pullback.contracts import GateError, file_hash
from momentum_pullback.source_adjudication import (
    adjudicate, build_issue_rows, classify_scope, publication_status, resolve_stored_factor,
)


def test_missing_pit_proof_is_not_out_of_pool():
    scope, reason = classify_scope(False, None)
    assert scope == "ELIGIBILITY_UNKNOWN"
    assert reason == "NO_CERTIFIED_PIT_MEMBERSHIP_INTERVAL"
    assert classify_scope(True, False)[0] == "PROVEN_OUT_OF_POOL"
    assert classify_scope(True, True)[0] == "NECESSARY_RESEARCH_SCOPE"


def test_trade_date_is_not_a_publication_time():
    assert publication_status(["ts_code", "trade_date", "adj_factor"]) == "UNKNOWN"
    assert publication_status(["ann_date"]) == "FIELD_PRESENT_SEMANTICS_UNVERIFIED"


def test_price_ratio_does_not_become_a_factor():
    resolved = resolve_stored_factor(np.nan, np.nan, 10.0, 25.0)
    assert resolved["factor"] is None
    assert resolved["state"] == "UNRESOLVED_NOT_INFERRED"
    sibling = resolve_stored_factor(np.nan, 2.5, 10.0, 25.0)
    assert sibling["factor"] is None
    assert sibling["treatment"] == "DO_NOT_ADOPT_UNVERIFIED_SIBLING"


def test_ledger_keeps_unknown_scope_when_weight_file_misses_the_name():
    invalid = pd.DataFrame({"ts_code": ["300537.SZ"], "trade_date": [20180131], "close": [10.0], "adj_close": [12.0], "stored_factor": [np.nan], "audit_slice": ["OUTPUT_WINDOW"]})
    sibling = pd.DataFrame({"ts_code": ["300537.SZ"], "trade_date": [20180131], "adj_factor": [1.2]})
    ledger = build_issue_rows(invalid, sibling, set())
    assert ledger.scope_class.tolist() == ["ELIGIBILITY_UNKNOWN"]
    assert bool(ledger.seen_in_unverified_000300_weight_file.iloc[0]) is False
    assert ledger.publication_time_status.tolist() == ["UNKNOWN"]
    assert bool(ledger.sibling_matches_adjusted_price.iloc[0]) is True


def test_runner_does_not_rewrite_source_bytes(tmp_path):
    cache = tmp_path / "data" / "parquet"
    price = cache / "prices_adj" / "year=2018" / "month=1"
    price.mkdir(parents=True)
    raw = pd.DataFrame({"ts_code": ["300537.SZ"], "trade_date": [20180102], "close": [10.0], "adj_close": [12.0], "adj_factor": [np.nan]})
    pq.write_table(pa.Table.from_pandas(raw), price / "cache.parquet")
    before = (price / "cache.parquet").read_bytes()
    factor = cache / "adj_factor" / "year=2018"
    factor.mkdir(parents=True)
    pq.write_table(pa.Table.from_pandas(pd.DataFrame({"ts_code": ["300537.SZ"], "trade_date": [20180102], "adj_factor": [1.2]})), factor / "cache.parquet")
    calendar = cache / "trade_cal"
    calendar.mkdir(parents=True)
    cal = pd.DataFrame({"exchange": ["SSE"], "cal_date": [20180102], "is_open": [1], "pretrade_date": [20171229]})
    pq.write_table(pa.Table.from_pandas(cal), calendar / "calendar.parquet")
    pq.write_table(pa.Table.from_pandas(cal.assign(cal_date=[20180103])), calendar / "cache.parquet")
    evidence = tmp_path / "momentum_pullback" / "evidence" / "source_adjudication"
    # The real scanner also looks at 2015-2017. Empty years are valid absences.
    result = adjudicate(tmp_path, evidence)
    assert (price / "cache.parquet").read_bytes() == before
    assert result["summary"]["public_cache_modified"] is False
    assert result["manifest"]["output_window_invalid_rows"] == 1
    assert result["summary"]["scope_class_counts"] == {"ELIGIBILITY_UNKNOWN": 1}
    names = ["source_catalog.json", "factor_issue_ledger.parquet", "source_feasibility_report.md", "adjudication_manifest.json"]
    targets = [evidence / name for name in names]
    targets.append(tmp_path / "data/research/momentum_pullback/source_adjudication_r3/unverified_sibling_factor_keys.parquet")
    first = {path.name: file_hash(path) for path in targets}
    first_bytes = {path.name: path.read_bytes() for path in targets}
    adjudicate(tmp_path, evidence)
    assert {path.name: path.read_bytes() for path in targets} == first_bytes
    raw.loc[0, "adj_close"] = 13.0
    pq.write_table(pa.Table.from_pandas(raw), price / "cache.parquet")
    with pytest.raises(GateError, match="ARTIFACT_ALREADY_EXISTS"):
        adjudicate(tmp_path, evidence)
    assert {path.name: file_hash(path) for path in targets} == first
    assert {path.name: path.read_bytes() for path in targets} == first_bytes


def test_duplicate_sibling_keys_do_not_multiply_the_ledger():
    invalid = pd.DataFrame({"ts_code": ["X"], "trade_date": [20180102], "close": [10.0], "adj_close": [12.0], "stored_factor": [np.nan], "audit_slice": ["OUTPUT_WINDOW"]})
    siblings = pd.DataFrame({"ts_code": ["X", "X"], "trade_date": [20180102, 20180102], "adj_factor": [1.2, 1.3]})
    with pytest.raises(GateError, match="DUPLICATE_OR_CONFLICTING_KEYS"):
        build_issue_rows(invalid, siblings, set())

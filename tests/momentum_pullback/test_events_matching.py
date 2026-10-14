from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from momentum_pullback.acceptance import run_hand_acceptance
from momentum_pullback.contracts import ROOT, GateError, validate_contract
from momentum_pullback.event_engine import build_events
from momentum_pullback.matching import lock_matches


def manual_path(contract, dates=None):
    dates = dates or [20171228, 20171229, 20180102, 20180103, 20180104, 20180105, 20180108]
    payload = contract.payload
    payload["scope"] = {"purpose": "ENGINEERING_ONLY", "feature_origin": dates[0], "output_start": dates[2], "output_end": dates[-1]}
    draft = validate_contract(payload)
    rows = []
    for index, date in enumerate(dates):
        day = pd.to_datetime(str(date), format="%Y%m%d").strftime("%Y-%m-%d")
        rows.append({"ts_code": "X", "trade_date": date, "market_index": index, "price_known": True, "feature_ready": True, "reset_ready": True, "price_status": "TRADED", "verified_halt_known": False, "adj_close": 12.0, "adj_low": 11.8, "ema21": 11.5, "ema50": 10.0, "prior_high20": 20.0, "strong_status": "KNOWN_ELIGIBLE", "signal_cutoff": f"{day}T18:00:00+08:00", "contract_hash": draft.hash})
    frame = pd.DataFrame(rows)
    frame.loc[0, ["adj_close", "adj_low", "ema21"]] = [10, 10, 10]
    frame.loc[1, "prior_high20"] = 11.0
    return frame, draft


def test_complete_pipeline_matches_independent_hand_oracle(base_contract, tmp_path):
    folder, summary = run_hand_acceptance(base_contract, root=tmp_path)
    assert summary["status"] == "HAND_ENGINEERING_ACCEPTED"
    assert summary["events"] == 2
    assert summary["controls"] == 6
    assert not summary["outcomes_generated"]
    assert (folder / "checkpoint.json").exists()
    manifest = json.loads((folder / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["logical_inputs"]["synthetic"] is True
    assert manifest["contract_status"] == "DRAFT"
    assert manifest["sample_authority"] == "ENGINEERING_ONLY_NOT_OOS"
    assert all(not path.name.startswith("label") for path in folder.iterdir())


def test_first_identity_is_left_censored_without_observed_reset(hand_draft):
    path, draft = manual_path(hand_draft)
    path.loc[0, ["adj_close", "adj_low", "ema21"]] = [12, 11.8, 11.5]
    path.loc[2, "adj_low"] = 11
    out = build_events(path, draft)
    assert out["events"].empty
    assert out["status"] == "PARTIAL_IDENTITY_UNEVALUABLE"
    assert not out["states"]["X"]["identity_known"]


def test_failed_touch_consumes_first_and_rebreakout_keeps_identity(hand_draft):
    path, draft = manual_path(hand_draft)
    path.loc[2, ["adj_low", "adj_close"]] = [11, 11.4]
    path.loc[3, ["adj_low", "adj_close"]] = [11, 12]
    path.loc[4, "prior_high20"] = 11
    path.loc[5, "adj_low"] = 11
    out = build_events(path, draft)
    assert out["events"].signal_date.tolist() == [20180102, 20180105]
    assert out["events"].touch_no.tolist() == [1, 2]
    assert out["events"].event_status.tolist() == ["FAILED_FIRST_DAY", "LATER_CANDIDATE"]
    assert out["events"].root_date.eq(20171229).all()
    assert out["breakouts"].is_root.tolist() == [True, False]


def test_continuous_touch_three_days_is_one_segment(hand_draft):
    path, draft = manual_path(hand_draft)
    path.loc[[2, 3, 4, 6], "adj_low"] = 11
    out = build_events(path, draft)
    assert out["events"].touch_no.tolist() == [1, 2]
    assert out["events"].signal_date.tolist() == [20180102, 20180108]


@pytest.mark.parametrize("age,status", [(20, "FIRST_CANDIDATE"), (21, "EXPIRED_FIRST_DIAGNOSTIC")])
def test_wait_boundary_evaluates_touch_before_expiry(hand_draft, age, status):
    dates = [int(date.strftime("%Y%m%d")) for date in pd.bdate_range("2017-11-01", periods=age + 2)]
    path, draft = manual_path(hand_draft, dates)
    path.loc[age + 1, "adj_low"] = 11
    out = build_events(path, draft)
    assert len(out["events"]) == 1
    assert out["events"].iloc[0].root_age_sessions == age
    assert out["events"].iloc[0].event_status == status
    assert out["states"]["X"]["window_closed"]


def test_reset_has_priority_over_touch(hand_draft):
    path, draft = manual_path(hand_draft)
    path.loc[2, ["adj_close", "adj_low"]] = [10, 9.8]
    out = build_events(path, draft)
    assert out["events"].empty
    assert out["transitions"].query("trade_date == 20180102").iloc[0].action == "VALID_RESET"
    assert out["status"] == "EVALUATED_ZERO_EVENTS"


def test_unknown_root_eligibility_persists_until_valid_reset(hand_draft):
    path, draft = manual_path(hand_draft)
    path.loc[1, "strong_status"] = "UNKNOWN"
    path.loc[2, "prior_high20"] = 11
    path.loc[3, "adj_low"] = 11
    path.loc[4, ["adj_close", "adj_low"]] = [10, 9.8]
    path.loc[5, "prior_high20"] = 11
    path.loc[6, "adj_low"] = 11
    out = build_events(path, draft)
    assert out["events"].signal_date.tolist() == [20180108]
    assert out["events"].root_date.tolist() == [20180105]
    assert out["events"].touch_no.tolist() == [1]
    assert out["transitions"].query("trade_date in [20180102, 20180103]").identity_known.eq(False).all()
    assert out["status"] == "PARTIAL_IDENTITY_UNEVALUABLE"


def test_known_root_keeps_touch_count_on_unknown_rank_day(hand_draft):
    path, draft = manual_path(hand_draft)
    path.loc[2, ["adj_low", "strong_status"]] = [11, "UNKNOWN"]
    path.loc[3, "adj_low"] = 11
    path.loc[5, "adj_low"] = 11
    out = build_events(path, draft)
    assert out["events"].event_status.tolist() == ["QUALIFICATION_UNKNOWN", "LATER_CANDIDATE"]
    assert out["events"].touch_no.tolist() == [1, 2]
    assert out["states"]["X"]["identity_known"]


@pytest.mark.parametrize("verified", [True, False])
def test_only_known_halt_preserves_price_path(hand_draft, verified):
    path, draft = manual_path(hand_draft)
    path.loc[2, "adj_low"] = 11
    path.loc[3, ["price_known", "price_status", "verified_halt_known"]] = [False, "VERIFIED_FULL_DAY_HALT", verified]
    path.loc[4, "adj_low"] = 11
    out = build_events(path, draft)
    assert out["states"]["X"]["identity_known"] is verified
    assert out["states"]["X"]["touch_no"] == 1
    assert (out["status"] == "PARTIAL_IDENTITY_UNEVALUABLE") is (not verified)


def test_checkpoint_inherits_root_and_count_across_quarter(hand_features, hand_draft):
    prefix = build_events(hand_features.query("trade_date <= 20171229"), hand_draft)
    resumed = build_events(hand_features.query("trade_date > 20171229"), hand_draft, states=prefix["states"])
    assert resumed["events"].root_date.tolist() == [20171229, 20171229]
    assert resumed["events"].touch_no.tolist() == [1, 2]
    assert len(resumed["roots"]) == 4
    assert resumed["roots"].root_date.lt(hand_draft.section("scope")["output_start"]).all()


def test_missing_session_does_not_claim_complete_replay(hand_draft):
    path, draft = manual_path(hand_draft)
    with pytest.raises(GateError, match="EVENT_CALENDAR_GAP"):
        build_events(path.drop(index=3), draft)


def test_zero_and_uncovered_are_different(hand_draft):
    path, draft = manual_path(hand_draft)
    assert build_events(path, draft)["status"] == "EVALUATED_ZERO_EVENTS"
    assert build_events(path.iloc[:-1], draft)["status"] == "OUTPUT_WINDOW_NOT_COVERED"


def test_matching_precedes_and_ignores_future_outcomes(hand_features, hand_draft):
    state = build_events(hand_features, hand_draft)
    first = lock_matches(state["events"], hand_features, state["observations"], hand_draft)
    changed = hand_features.copy()
    changed["future_return10"] = np.nan
    changed["future_filled"] = False
    changed["next_open"] = 0.01
    second = lock_matches(state["events"], changed, state["observations"], hand_draft)
    pd.testing.assert_frame_equal(first["matches"], second["matches"])
    assert first["matches"].control_code.tolist() == list("BCDBCD")
    assert first["balance"].percentile_difference.eq(0).all()


@pytest.mark.parametrize("problem,reason", [("one_control", "INSUFFICIENT_CONTROLS"), ("covariate", "COVARIATES_INCOMPLETE"), ("late_industry", "INFORMATION_UNAVAILABLE"), ("rank", "DENOMINATOR_INCOMPLETE")])
def test_matching_failures_do_not_relax_or_shrink(hand_features, hand_draft, problem, reason):
    state = build_events(hand_features, hand_draft)
    changed = hand_features.copy()
    if problem == "one_control":
        changed.loc[changed.ts_code.eq("D"), "strong_status"] = "KNOWN_INELIGIBLE"
    elif problem == "covariate":
        changed.loc[changed.ts_code.eq("T"), "circ_mv_cny"] = np.nan
    elif problem == "late_industry":
        changed.loc[changed.ts_code.eq("T"), "industry_available_at"] = "2018-01-06T00:00:00+08:00"
    else:
        changed["rank_denominator_complete"] = False
    paired = lock_matches(state["events"], changed, state["observations"], hand_draft)
    assert paired["status"] == "MATCHING_UNEVALUABLE"
    assert paired["matches"].empty
    assert paired["failures"].reason.str.contains(reason).all()


def test_matching_caliper_boundary_ties_and_same_day_reuse(hand_features, hand_draft):
    state = build_events(hand_features, hand_draft)
    events = state["events"].iloc[[0]].copy()
    features = hand_features.copy()
    features.loc[features.ts_code.eq("B"), "momentum63"] = 0.19
    for caliper, expected in [(0.10, "MATCHES_LOCKED"), (0.099, "MATCHING_UNEVALUABLE")]:
        payload = hand_draft.payload
        payload["matching"]["caliper"] = caliper
        draft = validate_contract(payload)
        features["contract_hash"] = draft.hash
        events["contract_hash"] = draft.hash
        result = lock_matches(events, features, state["observations"], draft)
        assert result["status"] == expected
        if caliper == 0.1:
            assert result["matches"].control_code.tolist() == list("CDB")
    duplicates = pd.concat([state["events"].iloc[[0]], state["events"].iloc[[0]].assign(event_id="different_event_same_date")], ignore_index=True)
    paired = lock_matches(duplicates, hand_features, state["observations"], hand_draft)
    assert paired["reuse"].reuse_count.eq(2).all()

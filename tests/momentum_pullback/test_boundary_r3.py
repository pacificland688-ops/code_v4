"""Boundary expectations are fixed in fixtures/boundary_expected.json before judging code."""
from __future__ import annotations

import json

import pandas as pd
import pytest

from momentum_pullback.casebook import declare_synthetic_roster, hand_panel
from momentum_pullback.contracts import ROOT, GateError, checkpoint, restore_checkpoint, validate_contract
from momentum_pullback.data_adapter import input_history_hash, roster_history_hash, validate_calendar_binding
from momentum_pullback.event_engine import build_events
from momentum_pullback.features import apply_cross_section, build_features

EXPECTED = json.loads((ROOT / "momentum_pullback/fixtures/boundary_expected.json").read_text(encoding="utf-8"))


def _draft(contract, dates, output_start, output_end):
    payload = contract.payload
    payload["scope"] = {"purpose": "ENGINEERING_ONLY", "feature_origin": int(dates[0]), "output_start": int(output_start), "output_end": int(output_end)}
    return validate_contract(payload)


def _panel(code, dates, closes, lows=None):
    lows = closes if lows is None else lows
    rows = []
    for date, close, low in zip(dates, closes, lows):
        day = pd.to_datetime(str(int(date)), format="%Y%m%d").strftime("%Y-%m-%d")
        available = f"{day}T17:00:00+08:00"
        close, low = float(close), float(low)
        row = {"ts_code": code, "trade_date": int(date), "adj_open": close, "adj_high": max(close, low), "adj_low": min(close, low), "adj_close": close, "amount_cny": 100_000_000.0, "circ_mv_cny": 1_000_000_000.0, "price_status": "TRADED", "membership_known": True, "is_member": True, "st_known": True, "is_st": False, "industry_code": "SYNTHETIC_INDUSTRY", "signal_cutoff": f"{day}T18:00:00+08:00"}
        for field in ["price", "membership", "st", "amount", "basic", "industry"]:
            row[field + "_available_at"] = available
        for field in ["membership", "st", "industry"]:
            row[field + "_effective_from"] = int(dates[0])
            row[field + "_effective_to"] = None
        rows.append(row)
    return pd.DataFrame(rows)


def _dates(periods):
    # Declared synthetic sessions. They are not a market calendar.
    return [int(date.strftime("%Y%m%d")) for date in pd.bdate_range("2016-01-04", periods=periods)]


def test_warm_01_monotonic_rise_never_clears_left_censor(hand_draft):
    spec = EXPECTED["WARM-01"]
    dates = _dates(170)
    closes = [10.0 + index for index in range(len(dates))]
    lows = closes.copy()
    lows[-1] = 0.01
    panel = _panel("RISE", dates, closes, lows)
    draft = _draft(hand_draft, dates, dates[-5], dates[-1])
    features = build_features(panel, dates, draft, roster=declare_synthetic_roster(panel))
    first = features.iloc[0]
    assert first.ema50 == pytest.approx(first.adj_close)
    assert bool(first.reset_ready) is spec["seed_reset_ready"]
    assert bool(first.feature_ready) is False
    ready = features[features.feature_ready]
    assert not ready.empty
    assert (ready.adj_close > ready.ema50).all()
    touched = features[features.feature_ready & features.adj_low.le(features.ema21) & features.adj_close.gt(features.ema50)]
    assert not touched.empty
    assert touched.strong_status.eq("KNOWN_ELIGIBLE").all()
    events = build_events(features, draft)
    assert int(events["transitions"].action.eq("VALID_RESET").sum()) == spec["valid_reset_actions"]
    assert int(events["events"].event_status.eq("FIRST_CANDIDATE").sum()) == spec["first_candidate_events"]
    assert bool(events["observations"].identity_known.any()) is spec["identity_known_any"]
    assert events["states"]["RISE"]["uncertainty_reason"] == spec["terminal_reason"]
    assert events["status"] == spec["status"]


def test_warm_02_only_a_post_ready_reset_can_open_touch_one(hand_draft):
    spec = EXPECTED["WARM-02"]
    dates = _dates(180)
    closes = [50.0 + index for index in range(len(dates))]
    closes[30] = 5.0
    closes[160] = closes[159] - 40.0
    closes[161] = closes[159] + 30.0
    for index in range(162, len(dates)):
        closes[index] = closes[161] + (index - 161)
    lows = closes.copy()
    lows[162] = 0.01
    panel = _panel("DIP", dates, closes, lows)
    draft = _draft(hand_draft, dates, dates[161], dates[165])
    features = build_features(panel, dates, draft, roster=declare_synthetic_roster(panel))
    events = build_events(features, draft)
    pre_ready = events["transitions"].iloc[30]
    assert pre_ready.action == spec["pre_ready_action"]
    assert bool(pre_ready.identity_known) is spec["pre_ready_is_seed"]
    assert events["transitions"].iloc[:150].action.ne("VALID_RESET").all()
    ready_reset = events["transitions"][events["transitions"].action.eq("VALID_RESET")]
    assert not ready_reset.empty
    assert ready_reset.iloc[0].action == spec["post_ready_action"]
    assert int(ready_reset.iloc[0].trade_date) > int(dates[30])
    assert int(ready_reset.iloc[0].trade_date) >= int(features.loc[features.feature_ready].iloc[0].trade_date)
    assert len(events["events"]) == spec["event_count"]
    assert int(events["events"].iloc[0].touch_no) == spec["touch_no"]
    assert events["events"].iloc[0].event_status == spec["event_status"]
    assert int(events["events"].iloc[0].root_date) > int(ready_reset.iloc[0].trade_date)
    assert events["states"]["DIP"]["reset_observed_at"] != int(dates[30])


def test_pool_01_missing_required_member_is_not_known_short_history(hand_draft):
    spec = EXPECTED["POOL-01"]
    panel, calendar = hand_panel()
    roster = declare_synthetic_roster(panel)
    damaged = panel[panel.ts_code.ne("T")].copy()
    with pytest.raises(GateError, match=spec["error"]) as caught:
        build_features(damaged, calendar, hand_draft, roster=roster)
    assert caught.value.code == spec["error"]
    assert "T" in caught.value.details["missing"]
    assert spec["forbidden_status"] != "REQUIRED_MEMBER_MISSING"


def test_pool_02_batches_rank_once_after_the_full_roster(hand_draft):
    spec = EXPECTED["POOL-02"]
    panel, calendar = hand_panel()
    roster = declare_synthetic_roster(panel)
    left = panel[panel.ts_code.isin(list("ABCDEFGHIJ"))].copy()
    right = panel[panel.ts_code.isin(list("KLMNOPQRST"))].copy()
    with pytest.raises(GateError, match=spec["batch_error"]):
        build_features(left, calendar, hand_draft, roster=roster, rank=True)
    parts = [build_features(batch, calendar, hand_draft, rank=False) for batch in (left, right)]
    combined = apply_cross_section(pd.concat(parts, ignore_index=True), roster, hand_draft)
    full = build_features(panel, calendar, hand_draft, roster=roster)
    columns = ["ts_code", "trade_date", "momentum_rank", "rank_denominator_complete", "strong_status", "pct_momentum63", "pct_volatility20", "pct_circ_mv_cny", "pct_adv20_cny"]
    combined = combined.sort_values(["trade_date", "ts_code"], kind="stable")[columns].reset_index(drop=True)
    ranked = full.sort_values(["trade_date", "ts_code"], kind="stable")[columns].reset_index(drop=True)
    pd.testing.assert_frame_equal(combined, ranked)
    assert spec["single_ranking"]
    day = full[full.trade_date.eq(20180102)]
    assert day.momentum_rank.nunique(dropna=True) == day.momentum_rank.notna().sum()
    assert day.query("strong_status == 'KNOWN_ELIGIBLE'").ts_code.tolist() == list("ABCD")


def test_cal_01_short_calendar_cannot_certify_itself(hand_draft):
    spec = EXPECTED["CAL-01"]
    panel, calendar = hand_panel()
    roster = declare_synthetic_roster(panel)
    removed = calendar[40]
    damaged = panel[panel.trade_date.ne(removed)].copy()
    with pytest.raises(GateError, match=spec["missing_session_error"]):
        build_features(damaged, calendar, hand_draft, roster=roster, certified_calendar=calendar)
    claimed = [date for date in calendar if date != removed]
    with pytest.raises(GateError, match=spec["short_calendar_error"]) as caught:
        validate_calendar_binding(claimed, calendar)
    assert caught.value.code == spec["short_calendar_error"]
    assert removed in caught.value.details["missing"]
    with pytest.raises(GateError, match=spec["short_calendar_error"]):
        build_features(damaged, claimed, hand_draft, roster=roster[roster.trade_date.ne(removed)], certified_calendar=calendar)


def test_tracked_reentry_does_not_zero_touch_count(hand_draft):
    dates = [20171228, 20171229, 20180102, 20180103, 20180104, 20180105]
    payload = hand_draft.payload
    payload["scope"] = {"purpose": "ENGINEERING_ONLY", "feature_origin": dates[0], "output_start": dates[2], "output_end": dates[-1]}
    draft = validate_contract(payload)
    rows = []
    for index, date in enumerate(dates):
        day = pd.to_datetime(str(date), format="%Y%m%d").strftime("%Y-%m-%d")
        rows.append({"ts_code": "X", "trade_date": date, "market_index": index, "price_known": True, "feature_ready": True, "reset_ready": True, "price_status": "TRADED", "verified_halt_known": False, "adj_close": 12.0, "adj_low": 11.8, "ema21": 11.5, "ema50": 10.0, "prior_high20": 11.0, "strong_status": "KNOWN_ELIGIBLE", "signal_cutoff": f"{day}T18:00:00+08:00", "contract_hash": draft.hash})
    frame = pd.DataFrame(rows)
    frame.loc[0, ["adj_close", "adj_low", "ema21"]] = [10, 10, 10]
    frame.loc[2, "adj_low"] = 11
    frame.loc[3, "strong_status"] = "KNOWN_INELIGIBLE"
    frame.loc[4, "adj_low"] = 11.6
    frame.loc[5, "adj_low"] = 11
    out = build_events(frame, draft)
    assert out["events"].touch_no.tolist() == [1, 2]
    assert out["events"].signal_date.tolist() == [20180102, 20180105]
    assert out["states"]["X"]["touch_no"] == 2


@pytest.mark.parametrize("schema", ["momentum_pullback.checkpoint.v2", "momentum_pullback.checkpoint.v3"])
def test_legacy_checkpoint_is_not_upgraded(base_contract, schema):
    saved = {"schema": schema, "state": {"touch_no": 1}, "state_hash": "ignored"}
    with pytest.raises(GateError, match="CHECKPOINT_NOT_UPGRADABLE"):
        restore_checkpoint(saved, contract=base_contract, code_hash="code", feature_origin=20150105, processed_cutoff=20171229, history_hash="history", roster_hash="roster")


def test_consumed_roster_rejects_past_edits_and_accepts_future_append(hand_draft):
    panel, calendar = hand_panel()
    panel.loc[panel.ts_code.eq("B") & panel.trade_date.eq(20180102), "adj_low"] = 10.1
    roster = declare_synthetic_roster(panel)
    cutoff = 20171229
    prefix = build_features(panel[panel.trade_date.le(cutoff)], calendar, hand_draft, roster=roster, return_states=True)
    before = build_events(prefix["features"], hand_draft)
    history = input_history_hash(panel, calendar, cutoff, roster)
    roster_hash = roster_history_hash(roster, cutoff)
    saved = checkpoint({"feature_states": prefix["states"], "event_states": before["states"]}, contract=hand_draft, code_hash="code", feature_origin=calendar[0], processed_cutoff=cutoff, history_hash=history, roster_hash=roster_hash)
    assert saved["schema"] == "momentum_pullback.checkpoint.v4"
    assert saved["consumed_roster_hash"] == roster_hash
    future = pd.concat([roster, roster[roster.trade_date.eq(roster.trade_date.max())].assign(trade_date=20180108)], ignore_index=True)
    assert input_history_hash(panel, calendar, cutoff, future) == history
    restored = restore_checkpoint(saved, contract=hand_draft, code_hash="code", feature_origin=calendar[0], processed_cutoff=cutoff, history_hash=input_history_hash(panel, calendar, cutoff, future), roster_hash=roster_history_hash(future, cutoff))
    resumed = build_events(build_features(panel[panel.trade_date.gt(cutoff)], calendar, hand_draft, roster=future, states=restored["feature_states"]), hand_draft, states=restored["event_states"])
    full = build_events(build_features(panel, calendar, hand_draft, roster=future), hand_draft)
    pd.testing.assert_frame_equal(resumed["events"].reset_index(drop=True), full["events"].reset_index(drop=True))
    changed = roster.copy()
    changed.loc[changed.trade_date.le(cutoff) & changed.ts_code.eq("T"), "required_for_rank"] = False
    with pytest.raises(GateError, match="CHECKPOINT_IDENTITY_MISMATCH"):
        restore_checkpoint(saved, contract=hand_draft, code_hash="code", feature_origin=calendar[0], processed_cutoff=cutoff, history_hash=input_history_hash(panel, calendar, cutoff, changed), roster_hash=roster_history_hash(changed, cutoff))
    with pytest.raises(GateError, match="ROSTER_MEMBERSHIP_CONFLICT"):
        build_features(panel, calendar, hand_draft, roster=changed)


def test_rank_and_match_share_one_denominator(hand_draft):
    from momentum_pullback.event_engine import build_events
    from momentum_pullback.matching import lock_matches
    panel, calendar = hand_panel()
    roster = declare_synthetic_roster(panel)
    baseline = build_features(panel, calendar, hand_draft, roster=roster, rank=False)
    conflict = roster.copy()
    conflict.loc[conflict.ts_code.eq("T"), "required_for_rank"] = False
    with pytest.raises(GateError, match="ROSTER_MEMBERSHIP_CONFLICT"):
        apply_cross_section(baseline, conflict, hand_draft)
    tracked = baseline.copy()
    tracked.loc[tracked.ts_code.eq("T"), "is_member"] = False
    ranked = apply_cross_section(tracked, conflict, hand_draft)
    day = ranked[ranked.trade_date.eq(20180102)]
    assert day.loc[day.in_rank_denominator, "ts_code"].nunique() == 19
    assert "T" not in set(day.loc[day.in_rank_denominator, "ts_code"])
    assert day.rank_denominator_hash.nunique() == 1
    events = build_events(ranked, hand_draft)
    paired = lock_matches(events["events"], ranked, events["observations"], hand_draft)
    if paired["status"] == "MATCHES_LOCKED":
        signal = day[day.ts_code.eq("A")].iloc[0]
        balance = paired["balance"][paired["balance"].covariate.eq("momentum63")].iloc[0]
        assert balance.event_percentile == pytest.approx(float(signal.pct_momentum63))
    widened = ranked.copy()
    widened.loc[widened.ts_code.eq("T") & widened.trade_date.eq(20180102), "is_member"] = True
    with pytest.raises(GateError, match="MATCH_DENOMINATOR_MISMATCH"):
        lock_matches(events["events"], widened, events["observations"], hand_draft)


def test_overlapping_batches_never_rank(hand_draft):
    panel, calendar = hand_panel()
    roster = declare_synthetic_roster(panel)
    baseline = build_features(panel, calendar, hand_draft, roster=roster, rank=False)
    extra = baseline[baseline.ts_code.eq("B") & baseline.trade_date.eq(20180102)]
    identical = pd.concat([baseline, extra], ignore_index=True)
    conflicting = identical.copy()
    conflicting.loc[conflicting.index[-1], "momentum63"] = 9.0
    for frame in (identical, conflicting):
        with pytest.raises(GateError, match="DUPLICATE_OR_CONFLICTING_KEYS"):
            apply_cross_section(frame, roster, hand_draft)

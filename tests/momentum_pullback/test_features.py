from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from momentum_pullback.casebook import hand_panel
from momentum_pullback.contracts import GateError
from momentum_pullback.features import build_features
from momentum_pullback.contracts import canonical_bytes
from momentum_pullback.data_adapter import input_history_hash


def one_stock():
    panel, dates = hand_panel()
    return panel[panel.ts_code.eq("A")].copy().reset_index(drop=True), dates


def test_price_features_have_hand_expected_values(hand_features):
    root = hand_features[(hand_features.ts_code == "A") & (hand_features.trade_date == 20171229)].iloc[0]
    assert root.valid_observations == 151
    assert root.ema21 == pytest.approx(10 + 2 / 11)
    assert root.ema50 == pytest.approx(10 + 4 / 51)
    assert root.prior_high20 == 10
    assert root.momentum63 == pytest.approx(0.2)
    assert root.ema21_lag5 == 10
    # One +20% return and nineteen zero returns, sample standard deviation.
    assert root.volatility20 == pytest.approx(np.sqrt(0.038 / 19))
    assert root.strong_status == "KNOWN_ELIGIBLE"
    assert hand_features[hand_features.trade_date.eq(20180102)].query("strong_status == 'KNOWN_ELIGIBLE'").ts_code.tolist() == list("ABCD")


def test_verified_halt_adv_uses_twenty_market_sessions(hand_draft):
    panel, calendar = one_stock()
    day = 140
    panel.loc[day, "price_status"] = "VERIFIED_FULL_DAY_HALT"
    panel.loc[day, ["adj_open", "adj_high", "adj_low", "adj_close", "amount_cny"]] = np.nan
    out = build_features(panel, calendar, hand_draft)
    final = out.iloc[-1]
    assert final.valid_observations == 154
    assert final.adv20_cny == pytest.approx(19 * 100_000_000 / 20)
    assert final.verified_halt_days == 1
    assert final.unknown_amount_days == 0
    assert out.iloc[day].verified_halt_known
    assert out.iloc[day].price_history_known
    assert out.iloc[day].valid_observations == out.iloc[day - 1].valid_observations


def test_unknown_amount_is_never_halt_zero(hand_draft):
    panel, calendar = one_stock()
    panel.loc[140, "amount_cny"] = np.nan
    final = build_features(panel, calendar, hand_draft).iloc[-1]
    assert np.isnan(final.adv20_cny)
    assert final.unknown_amount_days == 1
    assert final.verified_halt_days == 0
    assert final.price_history_known


def test_unknown_price_is_not_skipped_as_valid_history(hand_draft):
    panel, calendar = one_stock()
    panel.loc[140, "price_status"] = "UNKNOWN"
    panel.loc[140, ["adj_open", "adj_high", "adj_low", "adj_close"]] = np.nan
    final = build_features(panel, calendar, hand_draft).iloc[-1]
    assert not final.price_history_known
    assert not final.rank_denominator_complete
    assert np.isnan(final.momentum63)
    assert final.strong_status == "UNKNOWN"


def test_halt_nonzero_amount_is_conflict(hand_draft):
    panel, calendar = one_stock()
    panel.loc[140, "price_status"] = "VERIFIED_FULL_DAY_HALT"
    with pytest.raises(GateError, match="HALT_AMOUNT_CONFLICT"):
        build_features(panel, calendar, hand_draft)


def test_rank_denominator_does_not_shrink_for_unknown_member(hand_draft):
    panel, calendar = hand_panel()
    panel = panel[panel.ts_code.isin(["A", "B"])].copy()
    panel.loc[(panel.ts_code == "B") & (panel.trade_date == 20171229), "membership_known"] = False
    day = build_features(panel, calendar, hand_draft).query("trade_date == 20171229")
    assert not day.rank_denominator_complete.any()
    assert day.strong_status.eq("UNKNOWN").all()
    assert day.momentum_rank.isna().all()


def test_announcement_and_effective_date_are_separate(hand_draft):
    panel, calendar = one_stock()
    panel.loc[150, "membership_available_at"] = "2017-12-29T18:00:01+08:00"
    panel.loc[151, "membership_effective_from"] = 20180103
    panel.loc[152, "industry_effective_from"] = 20180104
    out = build_features(panel, calendar, hand_draft)
    assert not out.iloc[150].membership_known
    assert not out.iloc[151].is_member
    assert out.iloc[151].strong_status == "KNOWN_INELIGIBLE"
    assert pd.isna(out.iloc[152].industry_code)


def test_signal_cutoff_masks_late_information_and_future_edits(hand_draft):
    panel, calendar = one_stock()
    panel.loc[151, "basic_available_at"] = "2018-01-02T18:00:01+08:00"
    panel.loc[151, "industry_available_at"] = "2018-01-02T18:00:01+08:00"
    first = build_features(panel, calendar, hand_draft)
    changed = panel.copy()
    changed.loc[151, "circ_mv_cny"] *= 123
    changed.loc[151, "industry_code"] = "LATE_OTHER_INDUSTRY"
    changed.loc[154, ["adj_open", "adj_high", "adj_low", "adj_close"]] = [20, 21, 19, 20]
    second = build_features(changed, calendar, hand_draft)
    pd.testing.assert_frame_equal(first[first.trade_date.le(20180102)], second[second.trade_date.le(20180102)])


def test_feature_checkpoint_inherits_ema_liquidity_and_history(hand_draft):
    panel, calendar = one_stock()
    panel.loc[140, "price_status"] = "VERIFIED_FULL_DAY_HALT"
    panel.loc[140, ["adj_open", "adj_high", "adj_low", "adj_close", "amount_cny"]] = np.nan
    full = build_features(panel, calendar, hand_draft)
    first = build_features(panel[panel.trade_date.le(20171229)], calendar, hand_draft, return_states=True)
    later = build_features(panel[panel.trade_date.gt(20171229)], calendar, hand_draft, states=first["states"])
    pd.testing.assert_frame_equal(full[full.trade_date.gt(20171229)].reset_index(drop=True), later)
    assert later.iloc[0].verified_halt_days == 1
    assert later.iloc[0].valid_observations == 151
    assert first["states"]["A"]["ema_support"] == pytest.approx(10 + 2 / 11)


def test_unknown_liquidity_checkpoint_is_json_safe(hand_draft):
    panel, calendar = one_stock()
    panel.loc[140, "amount_cny"] = np.nan
    built = build_features(panel, calendar, hand_draft, return_states=True)
    assert b"UNKNOWN_AMOUNT" in canonical_bytes(built["states"])


def test_calendar_history_change_invalidates_consumed_prefix():
    panel, calendar = one_stock()
    original = input_history_hash(panel, calendar, 20171229)
    assert input_history_hash(panel, calendar + [20180108], 20171229) == original
    assert input_history_hash(panel, calendar[1:], 20171229) != original


def test_no_resume_from_empty_state_or_wrong_origin(hand_draft):
    panel, calendar = one_stock()
    suffix = panel[panel.trade_date.gt(20171229)]
    with pytest.raises(GateError, match="FEATURE_ORIGIN_NOT_REPLAYED"):
        build_features(suffix, calendar, hand_draft)
    with pytest.raises(GateError, match="FEATURE_CHECKPOINT_IDENTITY_MISMATCH"):
        build_features(suffix, calendar, hand_draft, states={"A": {}})

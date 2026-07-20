"""Outcome tradability tests — two-phase entry, calendar grid, frozen basket
(plan §6 / §10)."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from live.photoresist_panic.outcome_tracker import (  # noqa: E402
    ENTRY_RESOLVED, NO_TRADABLE_BASKET, OUTCOME_DATA_BLOCKED, PENDING_ENTRY,
    _valuation_grid, evaluate_signal_outcome, resolve_entry,
)

CONFIG = {
    "horizons_trading_days": [5, 10, 20],
    "target_net_gain": 0.05,
    "round_trip_cost_bps": 100,
    "stop_levels": [-0.05, -0.08, -0.10],
    "min_entry_components": 3,
}

CODES = ["A.SZ", "B.SZ", "C.SZ", "D.SZ"]


def _panel(days, codes=CODES, overrides=None, drop=None):
    """Flat panel: default flat 10.0 prices. overrides: {(code, day): {col: v}}.
    drop: {(code, day)} rows omitted entirely (suspension without record)."""
    overrides = overrides or {}
    drop = drop or set()
    rows = []
    for code in codes:
        for day in days:
            if (code, day) in drop:
                continue
            row = {
                "ts_code": code, "trade_date": day,
                "adj_open": 10.0, "adj_high": 10.1, "adj_low": 9.9,
                "adj_close": 10.0, "close": 10.0, "pct_chg": 0.0,
                "vol": 1000.0, "amount": 5000.0,
            }
            row.update(overrides.get((code, day), {}))
            rows.append(row)
    return pd.DataFrame(rows)


def _signal(date=2, codes=CODES):
    return {"signal_id": "SIG1", "live_signal_date": date,
            "active_member_codes": codes}


def _suspends(*keys):
    return pd.DataFrame([
        {"ts_code": code, "trade_date": day, "suspend_type": "S"}
        for code, day in keys
    ])


DAYS = list(range(1, 40))
CAL = np.array(DAYS)


# ═══════════════════════════════════════════════════════════════════════
# Two-phase entry resolution (plan §6.1)
# ═══════════════════════════════════════════════════════════════════════
def test_entry_resolves_and_freezes_components():
    resolution = resolve_entry(_panel(DAYS), CAL, _signal())
    assert resolution["entry_status"] == ENTRY_RESOLVED
    assert resolution["entry_date"] == 3
    assert resolution["entry_component_codes"] == sorted(CODES)
    assert resolution["exclusions"] == []


def test_outcome_uses_frozen_entry_resolution_after_price_revision():
    panel = _panel(DAYS, overrides={("A.SZ", 3): {"pct_chg": 10.0}})
    signal = {
        **_signal(),
        "entry_status": ENTRY_RESOLVED,
        "entry_date": 3,
        "entry_component_codes": CODES,
        "entry_exclusions": [],
        "entry_resolution_idempotency_key": "frozen-entry-fact",
    }
    record, rows = evaluate_signal_outcome(panel, CAL, signal, CONFIG)
    assert record["n_entry_components"] == 4
    included = {row["ts_code"] for row in rows if row["included"]}
    assert "A.SZ" in included


def test_limit_up_on_entry_day_excluded():
    panel = _panel(DAYS, overrides={("A.SZ", 3): {"pct_chg": 10.0}})
    resolution = resolve_entry(panel, CAL, _signal())
    assert resolution["entry_status"] == ENTRY_RESOLVED
    assert "A.SZ" not in resolution["entry_component_codes"]
    assert {"ts_code": "A.SZ", "reason": "limit_up_cannot_buy"} in resolution["exclusions"]


def test_suspended_on_entry_day_excluded():
    panel = _panel(DAYS, overrides={("A.SZ", 3): {"vol": 0.0}})
    resolution = resolve_entry(panel, CAL, _signal())
    assert {"ts_code": "A.SZ", "reason": "suspended_entry_day"} in resolution["exclusions"]


def test_missing_entry_day_row_excluded():
    panel = _panel(DAYS, drop={("A.SZ", 3)})
    resolution = resolve_entry(panel, CAL, _signal())
    assert {"ts_code": "A.SZ", "reason": "no_entry_day_data"} in resolution["exclusions"]


def test_entry_uses_frozen_20d_liquidity_threshold():
    panel = _panel(DAYS)
    panel["amount"] = 200_000.0  # Tushare thousand-CNY units
    panel.loc[panel["ts_code"] == "A.SZ", "amount"] = 100.0
    policy = {
        "enabled": True,
        "source": "frozen_universe_eligibility",
        "window": 20,
        "min_periods": 10,
        "min_daily_amount_20d": 1.0e8,
        "amount_unit": "thousand_cny",
    }
    resolution = resolve_entry(
        panel, CAL, _signal(date=20), entry_liquidity=policy
    )
    assert resolution["entry_status"] == ENTRY_RESOLVED
    assert resolution["entry_component_codes"] == ["B.SZ", "C.SZ", "D.SZ"]
    exclusion = next(
        row for row in resolution["exclusions"] if row["ts_code"] == "A.SZ"
    )
    assert exclusion["reason"] == "liquidity_amount_20d"
    assert exclusion["amount_20d_avg"] == 100.0
    assert exclusion["minimum_amount"] == 100_000.0
    assert resolution["liquidity_policy"]["source"] == (
        "frozen_universe_eligibility"
    )


def test_entry_liquidity_fails_closed_without_minimum_history():
    policy = {
        "window": 20, "min_periods": 10,
        "min_daily_amount_20d": 1.0e8, "amount_unit": "thousand_cny",
    }
    resolution = resolve_entry(
        _panel(DAYS), CAL, _signal(date=2), entry_liquidity=policy
    )
    assert resolution["entry_status"] == NO_TRADABLE_BASKET
    assert {row["reason"] for row in resolution["exclusions"]} == {
        "liquidity_amount_20d_unavailable"
    }


def test_fewer_than_three_tradable_is_no_tradable_basket():
    panel = _panel(DAYS, overrides={
        ("A.SZ", 3): {"pct_chg": 10.0},
        ("B.SZ", 3): {"vol": 0.0},
    })
    resolution = resolve_entry(panel, CAL, _signal())
    assert resolution["entry_status"] == NO_TRADABLE_BASKET
    record, rows = evaluate_signal_outcome(panel, CAL, _signal(), CONFIG)
    assert record["status"] == NO_TRADABLE_BASKET
    assert record["ret_5d_net"] is None  # no formal forward returns
    reasons = {r["ts_code"]: r["reason"] for r in rows if not r["included"]}
    assert reasons == {"A.SZ": "limit_up_cannot_buy", "B.SZ": "suspended_entry_day"}


def test_pending_before_entry_data():
    panel = _panel([1, 2])
    record, _ = evaluate_signal_outcome(panel, np.array([1, 2, 3]),
                                        _signal(date=2), CONFIG)
    assert record["status"] == PENDING_ENTRY


# ═══════════════════════════════════════════════════════════════════════
# Calendar-aligned grid + frozen basket (plan §6.2 / §6.3)
# ═══════════════════════════════════════════════════════════════════════
def test_suspension_carries_last_close_on_unified_grid():
    """持有期内停牌3日后复牌：停牌日估值=上一收盘, 复牌日不错配day_index."""
    overrides = {("A.SZ", 4): {"adj_close": 12.0, "adj_high": 12.0,
                               "adj_low": 12.0}}
    drop = {("A.SZ", d) for d in (5, 6, 7)}   # 3-day suspension
    overrides[("A.SZ", 8)] = {"adj_close": 8.0, "adj_high": 8.0, "adj_low": 8.0}
    panel = _panel(DAYS, overrides=overrides, drop=drop)
    suspends = _suspends(*[("A.SZ", day) for day in (5, 6, 7)])
    grid = _valuation_grid(
        panel, ["A.SZ"], 3, CAL, 10, suspend_status=suspends
    )
    by_day = grid.set_index("day_index")
    # day 4 (index 1): 12.0 -> +20%
    assert by_day.at[1, "close_ret"] == pytest.approx(0.20)
    # suspended days 5-7 (index 2-4): carried at 12.0, high/low = carried close
    for i in (2, 3, 4):
        assert by_day.at[i, "close_ret"] == pytest.approx(0.20)
        assert by_day.at[i, "low_ret"] == pytest.approx(0.20)
        assert by_day.at[i, "high_ret"] == pytest.approx(0.20)
        assert by_day.at[i, "n_valued"] == 0
    # resumption day 8 lands on grid index 5, NOT the stock's own 3rd row
    assert by_day.at[5, "close_ret"] == pytest.approx(-0.20)
    assert by_day.at[5, "n_valued"] == 1


def test_unexplained_partial_gap_blocks_formal_outcome():
    """成员后续缺失且无停牌记录：阻断正式收益，不能伪装成停牌。"""
    drop = {("D.SZ", d) for d in range(10, 40)}    # D disappears after day 9
    panel = _panel(DAYS, drop=drop)
    record, _ = evaluate_signal_outcome(panel, CAL, _signal(), CONFIG)
    assert record["entry_status"] == ENTRY_RESOLVED
    assert record["n_entry_components"] == 4       # frozen at entry
    assert record["min_valued_components"] == 3    # actual valuation coverage
    assert record["status"] == OUTCOME_DATA_BLOCKED
    assert record["unexplained_gap_count"] > 0
    assert record["min_valuation_coverage"] == pytest.approx(0.75)
    assert record["ret_5d_net"] is None
    assert record["ret_end_net"] is None
    assert record["mae"] is None
    assert record["mfe"] is None
    assert record["target_hit_close"] is None


def test_calendar_alignment_across_members():
    """两只股票各自缺不同日期时, 收益仍按统一trade_date对齐平均."""
    overrides = {
        ("A.SZ", 5): {"adj_close": 11.0, "adj_high": 11.0, "adj_low": 11.0},
        ("B.SZ", 5): {"adj_close": 9.0, "adj_high": 9.0, "adj_low": 9.0},
    }
    drop = {("A.SZ", 4), ("B.SZ", 6)}
    panel = _panel(DAYS, codes=["A.SZ", "B.SZ", "C.SZ"], overrides=overrides,
                   drop=drop)
    grid = _valuation_grid(
        panel, ["A.SZ", "B.SZ", "C.SZ"], 3, CAL, 5,
        suspend_status=_suspends(("A.SZ", 4), ("B.SZ", 6)),
    )
    by_day = grid.set_index("day_index")
    # grid day 5 = day_index 2 for EVERY stock: (+10% -10% 0%)/3 = 0
    assert by_day.at[2, "close_ret"] == pytest.approx(0.0)


def test_all_components_unexplained_missing_blocks_outcome():
    drop = {(code, day) for code in CODES for day in range(10, 40)}
    panel = _panel(DAYS, drop=drop)
    record, _ = evaluate_signal_outcome(panel, CAL, _signal(), CONFIG)
    assert record["status"] == OUTCOME_DATA_BLOCKED
    assert record["min_valuation_coverage"] == 0.0
    assert record["unexplained_gap_count"] >= len(CODES)
    assert record["first_stop_hit"] is None


def test_audited_suspension_then_resumption_can_complete():
    drop = {("D.SZ", day) for day in (10, 11, 12)}
    panel = _panel(DAYS, drop=drop)
    suspends = _suspends(*[("D.SZ", day) for day in (10, 11, 12)])
    record, _ = evaluate_signal_outcome(
        panel, CAL, _signal(), CONFIG, suspend_status=suspends
    )
    assert record["status"] == "COMPLETE"
    assert record["unexplained_gap_count"] == 0
    assert record["min_valuation_coverage"] == 1.0
    assert record["min_real_data_coverage"] == pytest.approx(0.75)


def test_target_and_upper_bound_metrics():
    overrides = {}
    for code in CODES:
        overrides[(code, 6)] = {"adj_close": 10.7, "adj_high": 10.9,
                                "adj_low": 10.5}
    panel = _panel(DAYS, overrides=overrides)
    record, _ = evaluate_signal_outcome(panel, CAL, _signal(), CONFIG)
    # close 10.7/10.0 - 1 - 1% cost = 6% >= 5% target at grid index 3
    assert record["target_hit_close"] is True
    assert record["days_to_target"] == 3
    # renamed intraday metric present; legacy name gone
    assert record["component_high_upper_bound_hit"] is True
    assert "target_hit_intraday" not in record


def test_same_day_tp_sl_conservative_and_flagged():
    overrides = {}
    for code in CODES:
        overrides[(code, 4)] = {"adj_high": 10.7, "adj_low": 9.4,
                                "adj_close": 10.0}
    panel = _panel(DAYS, overrides=overrides)
    record, _ = evaluate_signal_outcome(panel, CAL, _signal(), CONFIG)
    assert record["first_stop_hit"] is True
    assert record["first_stop_level"] == -0.05
    assert record["stop_before_target"] is True
    assert record["path_ambiguous"] is True


def test_mae_mfe_from_adjusted_extremes():
    overrides = {}
    for code in CODES:
        overrides[(code, 7)] = {"adj_low": 8.9, "adj_high": 10.1,
                                "adj_close": 10.0}
        overrides[(code, 9)] = {"adj_high": 11.2, "adj_low": 9.9,
                                "adj_close": 10.0}
    panel = _panel(DAYS, overrides=overrides)
    record, _ = evaluate_signal_outcome(panel, CAL, _signal(), CONFIG)
    assert record["mae"] == pytest.approx(-0.11)
    assert record["mfe"] == pytest.approx(0.12)

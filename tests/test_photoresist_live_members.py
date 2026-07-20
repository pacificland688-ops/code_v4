"""Member-scope tests: eligibility_snapshot cross-validated against the FROZEN
filter, active-member stress metrics (plan §5 / §10)."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from live.photoresist_panic.signal_engine import (  # noqa: E402
    active_stress_metrics, eligibility_snapshot,
)

ELIGIBILITY = {
    "min_list_days": 120,
    "min_daily_amount_20d": 1.0e8,
    "amount_unit": "thousand_cny",
    "exclude_st": True,
    "exclude_suspend": True,
    "exclude_limit_down_event": True,
    "exclude_consecutive_limit_down": True,
}

CODES = ["A.SZ", "B.SZ", "C.SZ", "D.SZ"]


def _members(codes=CODES):
    return pd.DataFrame({"ts_code": codes, "name": codes})


def _panel(n_days=260, codes=CODES, overrides=None):
    overrides = overrides or {}
    days = [int(d.strftime("%Y%m%d"))
            for d in pd.bdate_range(end="2026-07-15", periods=n_days)]
    rows = []
    for code in codes:
        for day in days:
            row = {
                "ts_code": code, "trade_date": day,
                "adj_close": 10.0, "close": 10.0, "pct_chg": 0.0,
                "vol": 1000.0, "amount": 500000.0,  # 5亿 (thousand CNY units)
            }
            row.update(overrides.get((code, day), {}))
            rows.append(row)
    return pd.DataFrame(rows), days


def test_four_active_three_eligible_with_limit_down_reason():
    """Plan §5 regression shape: 4 active, 3 eligible, limit-down exclusion."""
    overrides = None
    panel, days = _panel()
    last = days[-1]
    panel.loc[(panel.ts_code == "D.SZ") & (panel.trade_date == last),
              "pct_chg"] = -10.54
    calendar = np.array(sorted(panel["trade_date"].unique()))
    snap = eligibility_snapshot(panel, _members(), last, ELIGIBILITY, calendar)
    assert snap["active_components"] == 4
    assert snap["signal_components"] == 3
    assert snap["eligible_member_codes"] == ["A.SZ", "B.SZ", "C.SZ"]
    assert snap["excluded_components"] == [
        {"ts_code": "D.SZ", "name": "D.SZ", "reason": "limit_down_event_day"}
    ]


def test_eligibility_snapshot_matches_frozen_filter():
    """Included set must equal the FROZEN filter_eligible_stocks output —
    drift between explanation and computation is a hard failure."""
    from build_photoresist_panic_events import (
        build_trading_calendar, filter_eligible_stocks,
    )

    overrides = {}
    panel, days = _panel()
    last = days[-1]
    # limit-down member, suspended member, low-liquidity member
    panel.loc[(panel.ts_code == "D.SZ") & (panel.trade_date == last),
              "pct_chg"] = -9.9
    panel.loc[(panel.ts_code == "C.SZ") & (panel.trade_date == last),
              "vol"] = 0.0
    panel.loc[panel.ts_code == "B.SZ", "amount"] = 10.0  # far below 1亿
    calendar = build_trading_calendar(panel)

    snap = eligibility_snapshot(panel, _members(), last, ELIGIBILITY, calendar)
    frozen = filter_eligible_stocks(
        day_prices=panel[panel["trade_date"] == last].copy(),
        prices=panel, trade_date=last, calendar=calendar,
        eligibility=ELIGIBILITY,
    )
    frozen_codes = sorted(frozen["ts_code"].astype(str).tolist())
    assert snap["eligible_member_codes"] == frozen_codes == ["A.SZ"]
    reasons = {e["ts_code"]: e["reason"] for e in snap["excluded_components"]}
    assert reasons == {"B.SZ": "liquidity_amount_20d", "C.SZ": "suspended",
                       "D.SZ": "limit_down_event_day"}


def test_active_stress_counts_limit_down_excluded_from_gate():
    """跌停成员被gate排除, 但必须进入P4流动性压力统计."""
    panel, days = _panel()
    last = days[-1]
    panel.loc[(panel.ts_code == "D.SZ") & (panel.trade_date == last),
              "pct_chg"] = -10.54
    stress = active_stress_metrics(panel, CODES, last)
    assert stress["active_limit_down_count"] == 1
    assert stress["active_limit_down_codes"] == ["D.SZ"]


def test_active_stress_exact_limit_price_beats_proxy():
    panel, days = _panel()
    last = days[-1]
    # -9.4% would fail the pct proxy, but the exact down-limit price matches
    panel.loc[(panel.ts_code == "A.SZ") & (panel.trade_date == last),
              ["pct_chg", "close"]] = [-9.4, 9.06]
    limit_status = pd.DataFrame({
        "ts_code": ["A.SZ"], "trade_date": [last],
        "up_limit": [11.0], "down_limit": [9.06],
    })
    stress = active_stress_metrics(panel, CODES, last, limit_status=limit_status)
    assert stress["active_limit_down_codes"] == ["A.SZ"]


def test_active_stress_breadth_over_all_active_members():
    panel, days = _panel()
    for day in days[-5:]:
        for code in CODES:
            panel.loc[(panel.ts_code == code) & (panel.trade_date == day),
                      "pct_chg"] = -1.0
    stress = active_stress_metrics(panel, CODES, days[-1])
    assert stress["active_down_breadth_5d"] == 1.0

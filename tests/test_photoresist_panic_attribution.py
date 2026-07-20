import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from diagnose_photoresist_panic_attribution import (  # noqa: E402
    add_backward_features, select_non_overlapping, summarize_event_returns,
)


def test_select_non_overlapping_removes_shared_holding_windows():
    events = pd.DataFrame([
        {"event_date": 20240101, "entry_date": 20240102, "exit_date_20d": 20240201},
        {"event_date": 20240110, "entry_date": 20240111, "exit_date_20d": 20240210},
        {"event_date": 20240205, "entry_date": 20240206, "exit_date_20d": 20240306},
    ])
    selected = select_non_overlapping(events, 20)
    assert selected["event_date"].tolist() == [20240101, 20240205]


def test_backward_features_are_shifted_before_event_date():
    dates = [20240101 + i for i in range(30)]
    core = pd.DataFrame({"trade_date": dates, "basket_ret_1d": [0.01] * 30})
    index = pd.DataFrame({"ts_code": ["931865.CSI"] * 30,
                          "trade_date": dates, "close": range(100, 130)})
    event = pd.DataFrame({"event_date": [dates[-1]]})
    before = add_backward_features(event, core, index)
    changed = index.copy()
    changed.loc[changed.index[-1], "close"] = 10000
    after = add_backward_features(event, core, changed)
    assert before.loc[0, "semi_pre_20d"] == after.loc[0, "semi_pre_20d"]
    assert before.loc[0, "semi_vol_20d"] == after.loc[0, "semi_vol_20d"]


def test_summary_reports_semiconductor_excess_and_non_overlap():
    events = pd.DataFrame([
        {"gate_id": "primary_5d", "event_date": 1, "entry_date": 2, "exit_date_20d": 30,
         "basket_fwd_ret_5d": .05, "basket_fwd_ret_10d": .06, "basket_fwd_ret_20d": .08,
         "semi_fwd_ret_5d": .02, "semi_fwd_ret_10d": .03, "semi_fwd_ret_20d": .04},
        {"gate_id": "primary_5d", "event_date": 3, "entry_date": 4, "exit_date_20d": 32,
         "basket_fwd_ret_5d": .03, "basket_fwd_ret_10d": .04, "basket_fwd_ret_20d": .05,
         "semi_fwd_ret_5d": .02, "semi_fwd_ret_10d": .02, "semi_fwd_ret_20d": .03},
    ])
    result = summarize_event_returns(events, "primary_5d", 20)
    all_20 = result[(result["sample"] == "all_events") & (result["horizon_days"] == 20)].iloc[0]
    non_overlap = result[(result["sample"] == "non_overlapping") & (result["horizon_days"] == 20)].iloc[0]
    assert round(all_20["excess_mean"], 6) == 0.03
    assert non_overlap["n_events_total"] == 1

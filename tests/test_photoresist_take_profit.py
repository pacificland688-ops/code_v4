import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from analyze_photoresist_take_profit import (  # noqa: E402
    _wilson_interval, build_online_first_trigger_signals, simulate_take_profit,
)


def test_online_signal_uses_first_trigger_and_cooldown():
    calendar = np.array([20240101 + i for i in range(40)])
    flags = [False, True, True] + [False] * 22 + [True] + [False] * 14
    gated = pd.DataFrame({"trade_date": calendar, "validation_gate_triggered": flags})
    signals = build_online_first_trigger_signals(gated, calendar, 10, 5)
    assert signals.iloc[0]["event_date"] == calendar[1]
    assert len(signals) == 2


def test_take_profit_starts_after_entry_and_uses_adjusted_high():
    calendar = np.array([20240101, 20240102, 20240103, 20240104])
    prices = pd.DataFrame({"ts_code": ["A"] * 4, "trade_date": calendar,
                           "adj_close": [9.0, 10.0, 10.2, 10.4],
                           "adj_high": [9.1, 20.0, 10.7, 10.5]})
    result = simulate_take_profit("A", pd.Series({"exec_date": 20240102}),
                                  prices, calendar, 2, 0.05, 0.0, "intraday_high")
    assert result["target_hit"]
    assert result["hit_date"] == 20240103


def test_net_five_percent_target_includes_round_trip_cost():
    calendar = np.array([20240101, 20240102, 20240103])
    prices = pd.DataFrame({"ts_code": ["A"] * 3, "trade_date": calendar,
                           "adj_close": [9.0, 10.0, 10.55], "adj_high": [9.0, 10.0, 10.55]})
    result = simulate_take_profit("A", pd.Series({"exec_date": 20240102}),
                                  prices, calendar, 1, 0.05, 0.01, "close")
    assert not result["target_hit"]


def test_wilson_interval_contains_observed_rate():
    low, high = _wilson_interval(16, 21)
    assert low < 16 / 21 < high

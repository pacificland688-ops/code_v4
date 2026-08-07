"""Tests for the sector-panic holding-period sensitivity study.

The critical property under test is the R2 no-look-ahead guarantee: a
second W-pattern breakout observed after the planned exit must never add
the second leg.  Also covered: common-path-horizon invariance, the pure
statistics of the dual-caliber comparison (common support, paired
bootstrap, block bootstrap, equal-weight aggregate), and the frozen path
curves.
"""

import numpy as np
import pandas as pd
import pytest

from sector_panic.backtest import parse_second_breakout, simulate_rule
from sector_panic.hold_sensitivity import (
    bootstrap_stat,
    cell_metrics,
    direction_check,
    equal_weight_aggregate,
    paired_diff_stats,
    raw_path_curve,
    stop_day_counts,
    strategy_net_curves,
)

# A frozen W-repair path: bounce at day 4, retest at day 9, second
# breakout at day 11.  The trough stays above the -5% stop so the 5-day
# arm exits cleanly at the planned horizon.
W_RETURNS = np.array([
    0.00, -0.02, -0.04, -0.045, -0.02, -0.01, 0.02, 0.04,
    0.015, 0.005, 0.01, 0.045, 0.05, 0.05, 0.05, 0.05,
    0.05, 0.06, 0.06, 0.06, 0.06, 0.06, 0.06, 0.06, 0.06,
])
W_DATES = np.arange(100, 100 + len(W_RETURNS))


def test_r2_never_uses_a_second_breakout_after_the_exit():
    path = parse_second_breakout(W_RETURNS, W_DATES)
    assert path["path_type"] == "W_RECOVERY"
    assert path["second_breakout_date"] == W_DATES[11]

    short = simulate_rule(
        "R2", W_RETURNS, W_DATES, hold_days=5,
        stop_levels=[-0.05], round_trip_bps=100,
    )
    # The day-11 breakout is future information for the 5-day arm: the
    # position must stay half-size and the leg-2 return must be absent.
    assert short.status == "COMPLETED"
    assert short.invested_weight == 0.5
    assert short.second_entry_date is None
    assert short.net_return == pytest.approx(0.5 * W_RETURNS[5] - 0.005)

    full = simulate_rule(
        "R2", W_RETURNS, W_DATES, hold_days=20,
        stop_levels=[-0.05], round_trip_bps=100,
    )
    assert full.second_entry_date == W_DATES[12]
    assert full.invested_weight == 1.0
    expected = 0.5 * W_RETURNS[20] + 0.5 * (
        (1.0 + W_RETURNS[20]) / (1.0 + W_RETURNS[12]) - 1.0
    ) - 0.01
    assert full.net_return == pytest.approx(expected)


def test_r2_breakout_on_the_exit_day_does_not_add():
    # Breakout at day 11 with a planned exit at day 11: the add would
    # settle on day 12, which is after the exit, so it must not fire.
    result = simulate_rule(
        "R2", W_RETURNS, W_DATES, hold_days=11,
        stop_levels=[-0.05], round_trip_bps=100,
    )
    assert result.status == "COMPLETED"
    assert result.invested_weight == 0.5
    assert result.second_entry_date is None
    assert result.net_return == pytest.approx(0.5 * W_RETURNS[11] - 0.005)


def test_common_path_horizon_does_not_change_outcomes():
    # The same prefix under a 41-day path and a 21-day path must produce
    # identical trade outcomes: censoring differences may only come from
    # the hold rule, never from the path length supplied to the sim.
    long_returns = np.concatenate([W_RETURNS, np.full(41 - len(W_RETURNS), 0.12)])
    long_dates = np.arange(100, 100 + len(long_returns))
    base = simulate_rule(
        "R2", long_returns[:21], long_dates[:21], hold_days=20,
        stop_levels=[-0.05], round_trip_bps=100,
    )
    extended = simulate_rule(
        "R2", long_returns, long_dates, hold_days=20,
        stop_levels=[-0.05], round_trip_bps=100,
    )
    assert base.status == extended.status
    assert base.exit_date == extended.exit_date
    assert base.net_return == extended.net_return
    assert base.invested_weight == extended.invested_weight


def test_bootstrap_stat_is_deterministic_and_bounded():
    diffs = np.array([0.01, -0.02, 0.03, 0.005, -0.01, 0.02, 0.015, -0.005])
    first = bootstrap_stat(diffs, seed=42, n_boot=2000)
    second = bootstrap_stat(diffs, seed=42, n_boot=2000)
    assert first == second
    assert first[1] <= first[0] <= first[2]
    block = bootstrap_stat(diffs, seed=42, n_boot=2000, block_size=3)
    assert block[1] <= block[0] <= block[2]
    tight = bootstrap_stat(np.full(20, 0.1), seed=1, n_boot=2000)
    assert abs(tight[0] - 0.1) < 1e-9
    assert abs(tight[1] - 0.1) < 1e-9
    assert all(np.isnan(value) for value in bootstrap_stat(np.array([]), seed=1))


def test_paired_diff_stats_uses_only_the_common_support_set():
    columns = ["signal_id", "rule_id", "event_date", "entry_date",
               "sample_split", "status", "net_return"]
    base = pd.DataFrame([
        {"signal_id": "E1", "rule_id": "R0", "event_date": 20260105,
         "entry_date": 20260106, "sample_split": "train",
         "status": "COMPLETED", "net_return": 0.05},
        {"signal_id": "E2", "rule_id": "R0", "event_date": 20260205,
         "entry_date": 20260206, "sample_split": "train",
         "status": "COMPLETED", "net_return": -0.02},
        {"signal_id": "E3", "rule_id": "R0", "event_date": 20260305,
         "entry_date": 20260306, "sample_split": "train",
         "status": "COMPLETED", "net_return": 0.01},
        {"signal_id": "E4", "rule_id": "R0", "event_date": 20260405,
         "entry_date": 20260406, "sample_split": "train",
         "status": "RIGHT_CENSORED", "net_return": np.nan},
    ])[columns]
    arm = pd.DataFrame([
        {"signal_id": "E1", "rule_id": "R0", "event_date": 20260105,
         "entry_date": 20260106, "sample_split": "train",
         "status": "COMPLETED", "net_return": 0.08},
        {"signal_id": "E2", "rule_id": "R0", "event_date": 20260205,
         "entry_date": 20260206, "sample_split": "train",
         "status": "COMPLETED", "net_return": -0.05},
        {"signal_id": "E3", "rule_id": "R0", "event_date": 20260305,
         "entry_date": 20260306, "sample_split": "train",
         "status": "COMPLETED", "net_return": 0.03},
        {"signal_id": "E5", "rule_id": "R0", "event_date": 20260505,
         "entry_date": 20260506, "sample_split": "train",
         "status": "COMPLETED", "net_return": 0.10},
    ])[columns]

    stats = paired_diff_stats(base, arm, seed=7, n_boot=1000)

    assert stats["n_common"] == 3
    assert stats["n_only_base"] == 0
    assert stats["n_only_arm"] == 1
    assert stats["only_base_by_status"] == {}
    assert stats["only_arm_by_status"] == {"COMPLETED": 1}
    assert stats["mean_diff"] == pytest.approx((0.03 - 0.03 + 0.02) / 3)
    assert stats["median_diff"] == pytest.approx(0.02)
    assert stats["ci_mean_low"] <= stats["mean_diff"] <= stats["ci_mean_high"]
    assert 2 in stats["block_cis"] and 3 in stats["block_cis"]


def test_cell_metrics_counts_and_rates():
    calendar = np.array([20260105, 20260106, 20260107, 20260108, 20260109,
                         20260112])
    columns = ["signal_id", "rule_id", "event_date", "entry_date", "exit_date",
               "sample_split", "status", "net_return", "second_entry_date",
               "invested_weight"]
    cell = pd.DataFrame([
        {"signal_id": "E1", "rule_id": "R2", "event_date": 20260104,
         "entry_date": 20260105, "exit_date": 20260108,
         "sample_split": "train", "status": "COMPLETED", "net_return": 0.05,
         "second_entry_date": 20260107, "invested_weight": 1.0},
        {"signal_id": "E2", "rule_id": "R2", "event_date": 20260105,
         "entry_date": 20260105, "exit_date": 20260106,
         "sample_split": "train", "status": "STOPPED_OUT", "net_return": -0.05,
         "second_entry_date": np.nan, "invested_weight": 0.5},
        {"signal_id": "E3", "rule_id": "R2", "event_date": 20260106,
         "entry_date": 20260107, "exit_date": 20260109,
         "sample_split": "train", "status": "TRUNCATED_EXIT",
         "net_return": 0.01, "second_entry_date": 20260108,
         "invested_weight": 1.0},
        {"signal_id": "E4", "rule_id": "R2", "event_date": 20260107,
         "entry_date": 20260108, "exit_date": np.nan,
         "sample_split": "train", "status": "RIGHT_CENSORED",
         "net_return": np.nan, "second_entry_date": np.nan,
         "invested_weight": 0.5},
        {"signal_id": "E5", "rule_id": "R2", "event_date": 20260108,
         "entry_date": 20260109, "exit_date": np.nan,
         "sample_split": "train", "status": "UNTRADABLE",
         "net_return": np.nan, "second_entry_date": np.nan,
         "invested_weight": 0.5},
    ])[columns]

    metrics = cell_metrics(cell, calendar)

    assert metrics["n_signals"] == 5
    assert metrics["n_realized"] == 3
    assert metrics["n_censored"] == 1
    assert metrics["n_untradable"] == 1
    assert metrics["realizable_rate"] == pytest.approx(0.6)
    assert metrics["stop_rate"] == pytest.approx(0.2)
    assert metrics["truncation_rate"] == pytest.approx(0.2)
    assert metrics["mean_return"] == pytest.approx((0.05 - 0.05 + 0.01) / 3)
    assert metrics["win_rate"] == pytest.approx(2 / 3)
    assert metrics["cumulative_return"] == pytest.approx(
        1.05 * 0.95 * 1.01 - 1.0
    )
    assert metrics["avg_hold_days"] == pytest.approx(2.0)
    assert metrics["per_day_return"] == pytest.approx(
        (0.05 / 3 - 0.05 / 1 + 0.01 / 2) / 3
    )
    assert metrics["r2_add_rate"] == pytest.approx(2 / 3)
    assert metrics["avg_invested_weight"] == pytest.approx((1.0 + 0.5 + 1.0) / 3)


def test_direction_check_is_mechanical():
    agree = direction_check({"train": 0.01, "validation": 0.02, "locked_oos": 0.03})
    assert agree["signs"] == {"train": 1, "validation": 1, "locked_oos": 1}
    assert agree["n_consistent_with_oos"] == 3
    assert agree["all_agree"] is True

    partial = direction_check({"train": -0.01, "validation": 0.02, "locked_oos": 0.03})
    assert partial["n_consistent_with_oos"] == 2
    assert partial["all_agree"] is False

    flat = direction_check({"train": None, "validation": 0.01, "locked_oos": 0.0})
    assert flat["signs"]["train"] == 0
    assert flat["n_consistent_with_oos"] == 0


def test_equal_weight_aggregate_ignores_missing_sectors():
    rows = [
        {"mean_diff": 0.02}, {"mean_diff": -0.01},
        {"mean_diff": np.nan}, {"mean_diff": 0.05},
    ]
    aggregate = equal_weight_aggregate(rows)
    assert aggregate["n_sectors"] == 3
    assert aggregate["agg_mean_diff"] == pytest.approx((0.02 - 0.01 + 0.05) / 3)
    assert aggregate["n_positive"] == 2


def test_raw_path_curve_censors_at_the_next_event_boundary():
    path_a = np.array([0.00, 0.01, 0.02, 0.03, 0.04, 0.05])
    path_b = np.array([0.00, -0.01, -0.02, -0.03, -0.04, -0.05])
    path_c = np.array([0.00, 0.05, np.nan, 0.10, 0.10, 0.10])
    curve = raw_path_curve(
        [path_a, path_b, path_c],
        [3, None, None],  # boundaries are RELATIVE day indices after entry
        max_day=5,
    ).set_index("day")

    # Path A is cut at the boundary day 3; path C is excluded entirely by
    # its unexplained gap (mirrors RIGHT_CENSORED discipline).  The
    # boundary must be a day index, not an absolute calendar position: an
    # absolute position (e.g. 400) would NOT truncate a 6-day path.
    assert curve.loc[1, "n"] == 2
    assert curve.loc[1, "mean"] == pytest.approx(0.0)
    assert curve.loc[3, "n"] == 2
    assert curve.loc[4, "n"] == 1
    assert curve.loc[4, "mean"] == pytest.approx(-0.04)
    uncut = raw_path_curve([path_a], [400], max_day=5).set_index("day")
    assert uncut.loc[5, "n"] == 1


def test_strategy_net_curve_is_flat_in_cash_after_exit():
    curve = strategy_net_curves(
        [np.array([0.00, 0.02, 0.05, 0.06]), np.array([0.00, -0.03, -0.02, -0.01])],
        [2, 1],
        [0.05, -0.03],
        weights=[1.0, 1.0],
        add_positions=[None, None],
        max_day=3,
    ).set_index("day")
    assert curve.loc[1, "mean"] == pytest.approx((0.02 - 0.03) / 2)
    assert curve.loc[2, "mean"] == pytest.approx((0.05 - 0.03) / 2)
    assert curve.loc[3, "mean"] == pytest.approx((0.05 - 0.03) / 2)


def test_strategy_net_curve_rebuilds_r2_position_sizing():
    # R2 entry: 50% of the basket, second W-leg added at day 12.  Before
    # the add the NAV is half the basket return; after the add it mirrors
    # simulate_rule's leg formula; from the exit day on it sits at the
    # ledger net return (costs included).
    curve = strategy_net_curves(
        [W_RETURNS],
        [20],
        [0.5 * W_RETURNS[20] + 0.5 * (
            (1.0 + W_RETURNS[20]) / (1.0 + W_RETURNS[12]) - 1.0
        ) - 0.01],
        weights=[1.0],
        add_positions=[12],
        max_day=25,
    ).set_index("day")
    assert curve.loc[5, "n"] == 1
    assert curve.loc[5, "mean"] == pytest.approx(0.5 * W_RETURNS[5])
    day15 = 0.5 * W_RETURNS[15] + 0.5 * (
        (1.0 + W_RETURNS[15]) / (1.0 + W_RETURNS[12]) - 1.0
    )
    assert curve.loc[15, "mean"] == pytest.approx(day15)
    assert curve.loc[20, "mean"] == pytest.approx(0.5 * W_RETURNS[20] + 0.5 * (
        (1.0 + W_RETURNS[20]) / (1.0 + W_RETURNS[12]) - 1.0
    ) - 0.01)
    assert curve.loc[25, "mean"] == curve.loc[20, "mean"]


def test_strategy_net_curve_half_weight_without_add():
    # R2 that never fires its second leg: stays at 50% invested.
    curve = strategy_net_curves(
        [W_RETURNS],
        [5],
        [0.5 * W_RETURNS[5] - 0.005],
        weights=[0.5],
        add_positions=[None],
        max_day=10,
    ).set_index("day")
    assert curve.loc[3, "mean"] == pytest.approx(0.5 * W_RETURNS[3])
    assert curve.loc[5, "mean"] == pytest.approx(0.5 * W_RETURNS[5] - 0.005)
    assert curve.loc[10, "mean"] == pytest.approx(0.5 * W_RETURNS[5] - 0.005)


def test_stop_day_counts_histogram():
    calendar = np.array([20260105, 20260106, 20260107, 20260108])
    columns = ["signal_id", "rule_id", "entry_date", "exit_date", "status",
               "sample_split", "net_return"]
    cell = pd.DataFrame([
        {"signal_id": "E1", "rule_id": "R0", "entry_date": 20260105,
         "exit_date": 20260107, "status": "STOPPED_OUT",
         "sample_split": "train", "net_return": -0.05},
        {"signal_id": "E2", "rule_id": "R0", "entry_date": 20260105,
         "exit_date": 20260108, "status": "STOPPED_OUT",
         "sample_split": "train", "net_return": -0.05},
        {"signal_id": "E3", "rule_id": "R0", "entry_date": 20260105,
         "exit_date": 20260106, "status": "COMPLETED",
         "sample_split": "train", "net_return": 0.02},
    ])[columns]
    counts = stop_day_counts(cell, calendar, max_day=4)
    by_day = counts.set_index("day")["n"]
    assert by_day[2] == 1
    assert by_day[3] == 1
    assert by_day[1] == 0

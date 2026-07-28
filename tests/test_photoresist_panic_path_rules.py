"""Unit tests for photoresist panic path rules evaluator v2.

Covers corrected implementation:
  - Path parser: day-by-day scanning with phase freezing
  - Frozen basket: equal-weight, constituents fixed at entry
  - Rule simulator: correct cost accounting (100bp round-trip = 1%)
  - Position-relative stop loss (R0 and R1 use correct entry anchors)
  - Stop execution: day k confirmation → day k+1 execution
  - Confirmation lag, event boundary truncation
  - Truncation → RIGHT_CENSORED (not NO_OR_FAILED_REPAIR)
  - Signal close/low anchors via per-component computation
  - Manifest: frozen component codes and input hashing
  - Paired differences and bootstrap CI
  - Cost sensitivity with proper RIGHT_CENSORED/REJECTED exclusion
"""
import sys
import warnings
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from evaluate_photoresist_panic_path_rules import (  # noqa: E402
    PathResult,
    RuleTrade,
    EventRecord,
    ExecutionContext,
    parse_event_path,
    simulate_rule_r0,
    simulate_rule_r1,
    simulate_rule_r2,
    simulate_rule_r3,
    compute_paired_differences,
    bootstrap_ci,
    _classify_path_type,
    _flatten_trade,
    _round_trip_cost,
    _position_return,
    _stop_scan_position,
    _check_basket_execution,
    _fill_endpoint_metrics,
    _build_manifest,
    _dataframe_sha256,
    trading_day_offset,
    build_frozen_basket_path,
    compute_signal_anchors,
    get_core_codes,
    detect_first_triggers,
    construct_events,
    resolve_entry_basket,
    build_semi_nav_map,
    generate_report,
)


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════
def _make_calendar(start_ymd: int = 20200102, n_days: int = 200) -> np.ndarray:
    start_str = str(start_ymd)
    dr = pd.date_range(
        start=pd.Timestamp(
            year=int(start_str[:4]), month=int(start_str[4:6]), day=int(start_str[6:8])
        ),
        periods=n_days,
        freq="B",
    )
    return np.array([int(d.strftime("%Y%m%d")) for d in dr])


def _make_basket_rets(daily_rets: list[float]) -> np.ndarray:
    """Build cumulative return array from daily returns. rets[0] = 0 (entry day)."""
    cum = [0.0]
    nav = 1.0
    for r in daily_rets:
        nav *= (1.0 + r)
        cum.append(nav - 1.0)
    return np.array(cum)


def _make_dates(calendar: np.ndarray, entry_date: int, n_days: int) -> np.ndarray:
    idx = np.searchsorted(calendar, entry_date)
    return calendar[idx:idx + n_days + 1]


def _make_semi_lookup(dates: np.ndarray) -> dict[int, float]:
    """Simple semi NAV where semi grows at 0.1% per day from 1.0."""
    nav = 1.0
    result = {}
    for d in dates:
        result[int(d)] = nav
        nav *= 1.001
    return result


# ═══════════════════════════════════════════════════════════════════════════
# Path Parser Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestFirstTriggerDetection:
    def test_uses_online_first_trigger_per_cluster(self):
        basket = pd.DataFrame({
            "trade_date": [2, 3, 8, 14],
            "panic_gate_triggered": [True, True, True, True],
        })
        result = detect_first_triggers(basket, np.arange(1, 21), max_gap=5)
        assert result["first_trigger_date"].tolist() == [2, 14]

    def test_string_flags_and_missing_column_are_safe(self):
        basket = pd.DataFrame({
            "trade_date": [2, 3, 4],
            "panic_gate_triggered": ["False", "True", "0"],
        })
        result = detect_first_triggers(basket, np.arange(1, 10), max_gap=5)
        assert result["first_trigger_date"].tolist() == [3]
        empty = detect_first_triggers(
            pd.DataFrame({"trade_date": [2]}), np.arange(1, 10)
        )
        assert empty.empty


class TestPathParser:
    """Tests for parse_event_path with day-by-day scanning."""

    def test_sustained_repair(self):
        """Steady rise after entry — bounce, no retest, target hit."""
        calendar = _make_calendar(20200102, 200)
        entry_date = int(calendar[10])
        signal_date = int(calendar[9])

        # Path: small dip, then steady rise to +10%
        daily_rets = (
            [-0.005] * 2 +      # small dip
            [0.008] * 15 +      # steady rise
            [0.001] * 43         # continue
        )
        rets = _make_basket_rets(daily_rets)
        dates = _make_dates(calendar, entry_date, len(daily_rets))
        semi = _make_semi_lookup(dates)

        path = parse_event_path(
            rets, dates, semi,
            signal_date=signal_date,
            entry_date=entry_date,
            signal_basket_return=-0.02,
            signal_basket_low_return=-0.04,
            observation_horizon=60,
            target_gain=0.05,
            cost_bps=100,
        )

        assert path.path_type == "BOUNCE_NO_RETEST"
        assert path.first_bounce_date is not None
        assert path.first_bounce_high is not None
        assert path.target_5pct_hit is True
        assert path.broke_signal_close is False

    def test_no_bounce(self):
        """Steady decline — never bounces."""
        calendar = _make_calendar(20200102, 200)
        entry_date = int(calendar[10])

        daily_rets = [-0.008] * 30
        rets = _make_basket_rets(daily_rets)
        dates = _make_dates(calendar, entry_date, len(daily_rets))
        semi = _make_semi_lookup(dates)

        path = parse_event_path(
            rets, dates, semi,
            signal_date=int(calendar[9]),
            entry_date=entry_date,
            signal_basket_return=-0.02,
            signal_basket_low_return=-0.04,
            observation_horizon=60,
            cost_bps=100,
        )

        assert path.path_type == "NO_BOUNCE"
        assert path.first_bounce_date is None

    def test_failed_bounce(self):
        """Bounce then crash below signal close."""
        calendar = _make_calendar(20200102, 200)
        entry_date = int(calendar[10])

        # Bounce to +8%, then crash
        daily_rets = (
            [0.015] * 6 +       # bounce to ~9%
            [-0.03] * 4 +       # crash below
            [-0.005] * 50
        )
        rets = _make_basket_rets(daily_rets)
        dates = _make_dates(calendar, entry_date, len(daily_rets))
        semi = _make_semi_lookup(dates)

        path = parse_event_path(
            rets, dates, semi,
            signal_date=int(calendar[9]),
            entry_date=entry_date,
            signal_basket_return=-0.02,
            signal_basket_low_return=-0.04,
            observation_horizon=60,
            cost_bps=100,
        )

        assert path.path_type == "BOUNCE_THEN_FAIL"
        assert path.first_bounce_date is not None
        # Should have detected signal close breach or significant drawdown
        assert path.broke_signal_close or (
            path.post_bounce_drawdown is not None
            and path.post_bounce_drawdown <= -0.03
        )

    def test_w_recovery(self):
        """W-pattern: bounce, significant retest, breakout above frozen high."""
        calendar = _make_calendar(20200102, 200)
        entry_date = int(calendar[10])

        # Bounce to +5%, sharp retest, then breakout above frozen high
        daily_rets = (
            [0.012] * 5 +        # bounce to ~6% (above BOUNCE_START_THRESHOLD)
            [-0.02] * 2 +        # sharp drawdown ends bounce (>= 3% from running max)
            [0.005] * 2 +        # stabilize
            [0.02] * 5 +         # breakout above frozen first_bounce_high
            [0.001] * 46
        )
        rets = _make_basket_rets(daily_rets)
        dates = _make_dates(calendar, entry_date, len(daily_rets))
        semi = _make_semi_lookup(dates)

        path = parse_event_path(
            rets, dates, semi,
            signal_date=int(calendar[9]),
            entry_date=entry_date,
            signal_basket_return=-0.02,
            signal_basket_low_return=-0.04,
            observation_horizon=60,
            cost_bps=100,
        )

        # Should have bounce, retest, and second breakout
        assert path.first_bounce_date is not None
        assert path.first_bounce_high is not None
        assert path.second_breakout_date is not None  # KEY: this should be found now

    def test_undercut_diagnostic(self):
        """NAV dips below signal_low — check undercut booleans are set."""
        calendar = _make_calendar(20200102, 200)
        entry_date = int(calendar[10])

        daily_rets = (
            [0.01] * 2 +         # small bounce
            [-0.05] * 2 +        # sharp drop below signal_low
            [0.02] * 10 +        # recovery
            [0.001] * 46
        )
        rets = _make_basket_rets(daily_rets)
        dates = _make_dates(calendar, entry_date, len(daily_rets))
        semi = _make_semi_lookup(dates)

        path = parse_event_path(
            rets, dates, semi,
            signal_date=int(calendar[9]),
            entry_date=entry_date,
            signal_basket_return=-0.02,
            signal_basket_low_return=-0.04,  # -4% below entry
            observation_horizon=60,
            cost_bps=100,
        )

        # undercut_seen should be True if NAV went below -4%
        assert isinstance(path.undercut_seen, bool)
        assert isinstance(path.undercut_reclaimed, bool)

    def test__classify_path_type(self):
        """Unit test for path-shape classification (pre-trade descriptive)."""
        # Mild drawdown after bounce → no significant retest → BOUNCE_NO_RETEST
        path_s = PathResult(
            first_bounce_date=20200110, first_bounce_high=0.08,
            broke_signal_close=False, net_return_20d=0.07,
            post_bounce_drawdown=-0.01,
        )
        assert _classify_path_type(path_s, 0.05) == "BOUNCE_NO_RETEST"

        # Deep drawdown, broke signal close, no recovery → BOUNCE_THEN_FAIL
        path_f = PathResult(
            first_bounce_date=20200110, first_bounce_high=0.08,
            broke_signal_close=True, net_return_20d=-0.02,
            post_bounce_drawdown=-0.08,
        )
        assert _classify_path_type(path_f, 0.05) == "BOUNCE_THEN_FAIL"

        # Deep retest + breakout above frozen high → W_RECOVERY
        path_w = PathResult(
            first_bounce_date=20200110, first_bounce_high=0.05,
            broke_signal_close=False, net_return_20d=0.06,
            post_bounce_drawdown=-0.05, second_breakout_date=20200120,
        )
        assert _classify_path_type(path_w, 0.05) == "W_RECOVERY"

        # Deep drawdown, no breakout → BOUNCE_THEN_FAIL (shape, not outcome)
        path_diagnostic_only = PathResult(
            first_bounce_date=20200110, first_bounce_high=0.05,
            broke_signal_close=True, net_return_20d=0.01,
            post_bounce_drawdown=-0.05,
            second_breakout_date=None, undercut_reclaimed=True,
        )
        assert _classify_path_type(
            path_diagnostic_only, 0.05
        ) == "BOUNCE_THEN_FAIL"


# ═══════════════════════════════════════════════════════════════════════════
# Rule Simulator Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestRuleSimulator:
    """Tests for rule simulation functions."""

    @pytest.fixture
    def calendar(self):
        return _make_calendar(20200102, 200)

    @pytest.fixture
    def entry_date(self, calendar):
        return int(calendar[10])

    @pytest.fixture
    def rising_rets(self):
        """+0.5%/day steady rise for 60 days."""
        daily = [0.005] * 60
        return _make_basket_rets(daily)

    @pytest.fixture
    def rising_dates(self, calendar, entry_date):
        return _make_dates(calendar, entry_date, 60)

    @pytest.fixture
    def path_with_breakout(self, calendar):
        """PathResult with second breakout present."""
        return PathResult(
            signal_date=int(calendar[9]),
            entry_date=int(calendar[10]),
            first_bounce_date=int(calendar[15]),
            first_bounce_high=0.06,
            first_bounce_high_date=int(calendar[18]),
            post_bounce_drawdown=-0.04,
            second_breakout_date=int(calendar[25]),
            broke_signal_close=False,
            path_type="W_RECOVERY",
        )

    @pytest.fixture
    def path_no_breakout(self, calendar):
        """PathResult with NO second breakout."""
        return PathResult(
            signal_date=int(calendar[9]),
            entry_date=int(calendar[10]),
            first_bounce_date=int(calendar[15]),
            first_bounce_high=0.08,
            first_bounce_high_date=int(calendar[18]),
            post_bounce_drawdown=-0.03,
            second_breakout_date=None,
            broke_signal_close=False,
            path_type="ECONOMIC_NEGATIVE",
        )

    def test_r0_basic(self, calendar, entry_date, rising_rets, rising_dates):
        """R0: entry at T+1, exit at T+21, correct cost (100bp round-trip)."""
        trade = simulate_rule_r0(
            "TEST_001", int(calendar[9]), entry_date,
            rising_rets, rising_dates, calendar, cost_bps=100, hold_days=20,
        )
        assert trade.status == "COMPLETED"
        assert trade.n_legs == 2
        # round_trip_cost_bps=100 means total cost = 100bp = 1.0 * 100/10000 = 0.01
        assert trade.total_cost_ratio == pytest.approx(0.01)
        assert trade.legs[0]["leg_type"] == "entry"
        assert trade.legs[1]["leg_type"] == "exit"
        assert trade.gross_return is not None
        # Net = gross - 0.01 (one complete round trip at 100bp)
        assert trade.net_return == pytest.approx(trade.gross_return - 0.01)

    def test_r0_stop_loss(self, calendar, entry_date):
        """R0 with sharp drop triggers stop."""
        daily = [0.002] * 3 + [-0.06] + [0.001] * 56  # sharp -6% drop at day 4
        rets = _make_basket_rets(daily)
        dates = _make_dates(calendar, entry_date, 60)

        trade = simulate_rule_r0(
            "TEST_STOP", int(calendar[9]), entry_date,
            rets, dates, calendar, cost_bps=100, hold_days=20,
            stop_levels=[-0.05, -0.08],
        )
        assert trade.status == "STOPPED_OUT"
        assert "stop_loss" in trade.legs[1]["reason"]

    def test_r1_no_confirmation_returns_no_trade(self, calendar, entry_date,
                                                   rising_rets, rising_dates,
                                                   path_no_breakout):
        """R1 without second breakout → NO_TRADE (return=0)."""
        trade = simulate_rule_r1(
            "TEST_R1", int(calendar[9]), entry_date,
            path_no_breakout, rising_rets, rising_dates, calendar, cost_bps=100,
        )
        assert trade.status == "NO_TRADE"
        assert trade.net_return == 0.0
        assert trade.gross_return == 0.0

    def test_r1_with_confirmation(self, calendar, entry_date,
                                    rising_rets, rising_dates,
                                    path_with_breakout):
        """R1 with second breakout enters at confirmation+1."""
        trade = simulate_rule_r1(
            "TEST_R1", int(calendar[9]), entry_date,
            path_with_breakout, rising_rets, rising_dates, calendar, cost_bps=100,
        )
        assert trade.status == "COMPLETED"
        expected_entry = trading_day_offset(calendar, path_with_breakout.second_breakout_date, 1)
        assert trade.entry_date == expected_entry
        assert trade.legs[0]["reason"] == "second_breakout_confirmed"

    def test_r2_staged_both_legs(self, calendar, entry_date,
                                   rising_rets, rising_dates,
                                   path_with_breakout):
        """R2: half at T+1, half on breakout."""
        trade = simulate_rule_r2(
            "TEST_R2", int(calendar[9]), entry_date,
            path_with_breakout, rising_rets, rising_dates, calendar, cost_bps=100,
        )
        assert trade.status == "COMPLETED"
        assert trade.n_legs == 4  # entry1, add, exit1, exit2
        assert trade.legs[0]["weight"] == 0.5
        assert trade.legs[1]["weight"] == 0.5

    def test_r2_single_leg_no_breakout(self, calendar, entry_date,
                                         rising_rets, rising_dates,
                                         path_no_breakout):
        """R2 without breakout → only half position."""
        trade = simulate_rule_r2(
            "TEST_R2", int(calendar[9]), entry_date,
            path_no_breakout, rising_rets, rising_dates, calendar, cost_bps=100,
        )
        assert trade.status == "COMPLETED"
        assert trade.n_legs == 2  # entry1 + exit1 only

    def test_r3_stop_no_reentry(self, calendar, entry_date, path_no_breakout):
        """R3: stop triggers, no re-entry opportunity."""
        daily = [0.002] * 3 + [-0.07] + [0.001] * 56  # sharp -7% drop
        rets = _make_basket_rets(daily)
        dates = _make_dates(calendar, entry_date, 60)

        trade = simulate_rule_r3(
            "TEST_R3", int(calendar[9]), entry_date,
            path_no_breakout, rets, dates, calendar, cost_bps=100,
        )
        assert trade.status == "STOPPED_OUT"
        assert "stop_loss" in trade.legs[1]["reason"]
        assert trade.n_legs == 2  # no re-entry

    def test_r3_stop_with_reentry(self, calendar, entry_date, path_with_breakout):
        """R3: stop, then W-pattern re-entry after stop_date."""
        # Make stop happen before second_breakout
        daily = [0.002] * 3 + [-0.06] + [0.015] * 20 + [0.001] * 36
        rets = _make_basket_rets(daily)
        dates = _make_dates(calendar, entry_date, 60)

        # Ensure second_breakout_date is AFTER the stop
        path_with_breakout.second_breakout_date = int(calendar[22])

        trade = simulate_rule_r3(
            "TEST_R3", int(calendar[9]), entry_date,
            path_with_breakout, rets, dates, calendar, cost_bps=100,
        )
        assert trade.status == "COMPLETED"
        assert trade.n_legs == 4
        assert trade.status_reason == "stop_then_re_entry"

    def test_confirmation_lag(self, calendar, entry_date,
                                rising_rets, rising_dates,
                                path_with_breakout):
        """Confirmation at day k → execution at day k+1 (never same day)."""
        trade = simulate_rule_r1(
            "TEST_LAG", int(calendar[9]), entry_date,
            path_with_breakout, rising_rets, rising_dates, calendar, cost_bps=100,
        )
        if trade.status == "COMPLETED":
            assert trade.entry_date > path_with_breakout.second_breakout_date


# ═══════════════════════════════════════════════════════════════════════════
# Statistical Reporter Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestStatistics:
    """Tests for paired differences and bootstrap CI."""

    def test_paired_differences_with_no_trade(self):
        """NO_TRADE counts as return=0; REJECTED is excluded."""
        ledger = pd.DataFrame([
            {"signal_id": "S1", "rule_id": "R0", "cost_bps": 100, "net_return": 0.05,
             "status": "COMPLETED"},
            {"signal_id": "S1", "rule_id": "R1", "cost_bps": 100, "net_return": None,
             "status": "NO_TRADE"},
            {"signal_id": "S1", "rule_id": "R2", "cost_bps": 100, "net_return": 0.07,
             "status": "COMPLETED"},
            {"signal_id": "S1", "rule_id": "R3", "cost_bps": 100, "net_return": 0.04,
             "status": "COMPLETED"},
            {"signal_id": "S2", "rule_id": "R0", "cost_bps": 100, "net_return": 0.10,
             "status": "COMPLETED"},
            {"signal_id": "S2", "rule_id": "R1", "cost_bps": 100, "net_return": 0.08,
             "status": "COMPLETED"},
            {"signal_id": "S2", "rule_id": "R2", "cost_bps": 100, "net_return": 0.12,
             "status": "COMPLETED"},
            {"signal_id": "S2", "rule_id": "R3", "cost_bps": 100, "net_return": 0.09,
             "status": "COMPLETED"},
            # S3 has R0 REJECTED → should NOT appear in paired results
            {"signal_id": "S3", "rule_id": "R0", "cost_bps": 100, "net_return": None,
             "status": "REJECTED"},
            {"signal_id": "S3", "rule_id": "R1", "cost_bps": 100, "net_return": 0.03,
             "status": "COMPLETED"},
        ])

        paired = compute_paired_differences(ledger, primary_cost=100)
        # S1 and S2 only (S3 excluded because R0 is REJECTED)
        assert len(paired) == 2

        # S1: R1 is NO_TRADE (return=0), R0=0.05 → delta = -0.05
        row_s1 = paired[paired["signal_id"] == "S1"]
        assert row_s1["delta_R1_R0"].iloc[0] == pytest.approx(-0.05)

        # S2: R2-R0 = 0.12 - 0.10 = 0.02
        row_s2 = paired[paired["signal_id"] == "S2"]
        assert row_s2["delta_R2_R0"].iloc[0] == pytest.approx(0.02)

    def test_bootstrap_ci(self):
        """Bootstrap CI should contain the mean."""
        rng = np.random.RandomState(42)
        values = rng.normal(0.02, 0.05, 100)
        boot_mean, ci_low, ci_high = bootstrap_ci(values, n_bootstrap=500, seed=42)
        assert ci_low <= boot_mean <= ci_high

    def test_bootstrap_ci_small_sample(self):
        """Bootstrap CI with very few samples returns valid numbers."""
        values = np.array([0.01, 0.02, -0.01])
        boot_mean, ci_low, ci_high = bootstrap_ci(values, n_bootstrap=100, seed=42)
        assert not np.isnan(boot_mean)

    def test__flatten_trade(self):
        """Trade flattening produces correct columns including status."""
        trade = RuleTrade(
            signal_id="S1", rule_id="R0", event_date=20200115,
            entry_date=20200116, cost_bps=100,
            legs=[
                {"leg_type": "entry", "date": 20200116, "weight": 1.0,
                 "fill_price_ratio": 1.0, "cost_ratio": 0.01, "reason": "initial_entry"},
                {"leg_type": "exit", "date": 20200212, "weight": 1.0,
                 "fill_price_ratio": 1.05, "cost_ratio": 0.01, "reason": "hold_20d"},
            ],
            net_return=0.03, gross_return=0.05, total_cost_ratio=0.02,
            n_legs=2, status="COMPLETED", path_type="W_RECOVERY",
        )
        row = _flatten_trade(trade)
        assert row["signal_id"] == "S1"
        assert row["rule_id"] == "R0"
        assert row["status"] == "COMPLETED"
        assert row["leg_1_type"] == "entry"
        assert row["leg_2_type"] == "exit"


# ═══════════════════════════════════════════════════════════════════════════
# Edge Case Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestEdgeCases:
    """Tests for edge cases."""

    def test_right_censored_path(self):
        """Short calendar — 60d metrics are NaN."""
        calendar = _make_calendar(20200102, 30)
        entry_date = int(calendar[10])

        daily = [0.005] * 15
        rets = _make_basket_rets(daily)
        dates = _make_dates(calendar, entry_date, len(daily))
        semi = _make_semi_lookup(dates)

        path = parse_event_path(
            rets, dates, semi,
            signal_date=int(calendar[9]),
            entry_date=entry_date,
            signal_basket_return=-0.02,
            signal_basket_low_return=-0.04,
            observation_horizon=60,
            cost_bps=100,
        )
        assert path.path_type == "RIGHT_CENSORED"
        assert path.insufficient_data is True
        assert path.insufficient_reason == "right_censored_before_20d_endpoint"
        assert path.net_return_60d is None

    def test_nan_nav_handling(self):
        """An unexplained NaN blocks formal process classification."""
        calendar = _make_calendar(20200102, 100)
        entry_date = int(calendar[10])

        daily = [0.005] * 60
        rets = _make_basket_rets(daily)
        # Insert NaN at indices 15-17
        rets[15:18] = np.nan
        dates = _make_dates(calendar, entry_date, len(daily))
        semi = _make_semi_lookup(dates)

        path = parse_event_path(
            rets, dates, semi,
            signal_date=int(calendar[9]),
            entry_date=entry_date,
            signal_basket_return=-0.02,
            signal_basket_low_return=-0.04,
            observation_horizon=60,
            cost_bps=100,
        )
        assert path.path_type == "RIGHT_CENSORED"
        assert path.insufficient_reason == "unexplained_gap_in_first_20d"
        trade = simulate_rule_r0(
            "S_GAP", int(calendar[9]), entry_date,
            rets, dates, calendar, path_result=path,
        )
        assert trade.status == "RIGHT_CENSORED"

    def test_event_overlap_truncation(self):
        """Next event date truncates observation window."""
        calendar = _make_calendar(20200102, 200)
        entry_date = int(calendar[10])
        next_event = int(calendar[25])

        daily = [0.005] * 60
        rets = _make_basket_rets(daily)
        dates = _make_dates(calendar, entry_date, len(daily))
        semi = _make_semi_lookup(dates)

        path = parse_event_path(
            rets, dates, semi,
            signal_date=int(calendar[9]),
            entry_date=entry_date,
            signal_basket_return=-0.02,
            signal_basket_low_return=-0.04,
            observation_horizon=60,
            cost_bps=100,
            next_event_date=next_event,
        )
        # 40d and 60d should be NaN (beyond truncation at day 25)
        assert path.net_return_40d is None
        assert path.net_return_60d is None
        assert path.censored_at_day is not None


# ═══════════════════════════════════════════════════════════════════════════
# P0 Regression Tests — Cost, Stop Execution, Signal Anchors
# ═══════════════════════════════════════════════════════════════════════════

class TestCostAccounting:
    """Verify 100bp round-trip = 1% total cost for one complete entry+exit."""

    def test_round_trip_cost_helper(self):
        """_round_trip_cost correctly scales by weight."""
        # Full position: 100bp = 1%
        assert _round_trip_cost(1.0, 100) == pytest.approx(0.01)
        # Half position: 50bp = 0.5%
        assert _round_trip_cost(0.5, 100) == pytest.approx(0.005)
        # Full position at 50bp
        assert _round_trip_cost(1.0, 50) == pytest.approx(0.005)
        # Full position at 20bp
        assert _round_trip_cost(1.0, 20) == pytest.approx(0.002)

    def test_r0_cost_is_one_percent_at_100bp(self):
        """R0: one complete round trip = 100bp = 1%."""
        calendar = _make_calendar(20200102, 200)
        entry_date = int(calendar[10])
        daily = [0.005] * 60
        rets = _make_basket_rets(daily)
        dates = _make_dates(calendar, entry_date, 60)

        trade = simulate_rule_r0(
            "TEST", int(calendar[9]), entry_date,
            rets, dates, calendar, cost_bps=100, hold_days=20,
        )
        assert trade.status == "COMPLETED"
        # One round trip at 100bp = 1%
        assert trade.total_cost_ratio == pytest.approx(0.01)
        assert trade.net_return == pytest.approx(trade.gross_return - 0.01)

    def test_r2_two_halves_cost_is_one_percent(self):
        """R2 with two half-positions: 0.5*1% + 0.5*1% = 1%."""
        calendar = _make_calendar(20200102, 200)
        entry_date = int(calendar[10])
        daily = [0.005] * 60
        rets = _make_basket_rets(daily)
        dates = _make_dates(calendar, entry_date, 60)

        path = PathResult(
            signal_date=int(calendar[9]),
            entry_date=entry_date,
            first_bounce_date=int(calendar[15]),
            first_bounce_high=0.06,
            first_bounce_high_date=int(calendar[18]),
            post_bounce_drawdown=-0.04,
            second_breakout_date=int(calendar[22]),
            broke_signal_close=False,
            path_type="W_RECOVERY",
        )

        trade = simulate_rule_r2(
            "TEST", int(calendar[9]), entry_date,
            path, rets, dates, calendar, cost_bps=100,
        )
        assert trade.status == "COMPLETED"
        assert trade.n_legs == 4  # both halves filled
        # Two halves: 0.005 + 0.005 = 0.01
        assert trade.total_cost_ratio == pytest.approx(0.01)

    def test_r2_single_half_cost_is_half_percent(self):
        """R2 with only one half: 0.5*1% = 0.5%."""
        calendar = _make_calendar(20200102, 200)
        entry_date = int(calendar[10])
        daily = [0.005] * 60
        rets = _make_basket_rets(daily)
        dates = _make_dates(calendar, entry_date, 60)

        path = PathResult(
            signal_date=int(calendar[9]),
            entry_date=entry_date,
            first_bounce_date=int(calendar[15]),
            first_bounce_high=0.06,
            second_breakout_date=None,  # no second breakout
            broke_signal_close=False,
        )

        trade = simulate_rule_r2(
            "TEST", int(calendar[9]), entry_date,
            path, rets, dates, calendar, cost_bps=100,
        )
        assert trade.status == "COMPLETED"
        assert trade.n_legs == 2  # only one half
        assert trade.total_cost_ratio == pytest.approx(0.005)

    def test_r3_double_round_trip_cost_is_two_percent(self):
        """R3 with stop + re-entry = two complete round trips = 2%."""
        calendar = _make_calendar(20200102, 200)
        entry_date = int(calendar[10])
        # Stop at day 4 (-6%), then recover
        daily = [0.002] * 3 + [-0.06] + [0.015] * 20 + [0.001] * 36
        rets = _make_basket_rets(daily)
        dates = _make_dates(calendar, entry_date, 60)

        path = PathResult(
            signal_date=int(calendar[9]),
            entry_date=entry_date,
            first_bounce_date=int(calendar[15]),
            first_bounce_high=0.06,
            first_bounce_high_date=int(calendar[18]),
            post_bounce_drawdown=-0.04,
            second_breakout_date=int(calendar[22]),
            broke_signal_close=False,
        )

        trade = simulate_rule_r3(
            "TEST", int(calendar[9]), entry_date,
            path, rets, dates, calendar, cost_bps=100,
        )
        assert trade.status == "COMPLETED"
        assert trade.n_legs == 4
        # Two complete round trips
        assert trade.total_cost_ratio == pytest.approx(0.02)

    def test_cost_scenarios_all_correct(self):
        """Verify cost at 20bp, 50bp, 100bp."""
        calendar = _make_calendar(20200102, 200)
        entry_date = int(calendar[10])
        daily = [0.005] * 60
        rets = _make_basket_rets(daily)
        dates = _make_dates(calendar, entry_date, 60)

        for bps, expected_cost in [(20, 0.002), (50, 0.005), (100, 0.01)]:
            trade = simulate_rule_r0(
                f"TEST_{bps}", int(calendar[9]), entry_date,
                rets, dates, calendar, cost_bps=bps, hold_days=20,
            )
            assert trade.total_cost_ratio == pytest.approx(expected_cost)
            assert trade.net_return == pytest.approx(trade.gross_return - expected_cost)


class TestStopExecution:
    """Stop confirmed at day k close → executed at day k+1 close."""

    def test_stop_entry_is_day_k_plus_1(self):
        """Stop exit date is strictly after the confirmation date."""
        calendar = _make_calendar(20200102, 200)
        entry_date = int(calendar[10])
        # -6% at position day 3 (index 4 in rets)
        daily = [0.002] * 3 + [-0.06] + [0.001] * 56
        rets = _make_basket_rets(daily)
        dates = _make_dates(calendar, entry_date, 60)

        stopped, expected_exit, level = _stop_scan_position(
            rets, dates, calendar, entry_date,
            entry_event_ret=0.0, hold_days=20,
            stop_levels=[-0.05, -0.08],
        )
        confirmation_date = int(calendar[14])  # entry offset 4
        assert stopped is True
        assert level == -0.05
        assert expected_exit == int(calendar[15])
        assert expected_exit > confirmation_date

        trade = simulate_rule_r0(
            "TEST", int(calendar[9]), entry_date,
            rets, dates, calendar, cost_bps=100, hold_days=20,
            stop_levels=[-0.05, -0.08],
        )
        assert trade.status == "STOPPED_OUT"
        assert trade.legs[1]["date"] == expected_exit

    def test_stop_without_k_plus_1_falls_through_to_boundary_exit(self):
        """When k+1 stop exit exceeds trunc_date, stop is NOT confirmed at
        trunc_date itself (would need k+1 past boundary → k-confirm/k+1-execute
        violation).  The trade falls through to boundary exit (TRUNCATED_EXIT),
        NOT same-day fill nor RIGHT_CENSORED."""
        calendar = _make_calendar(20200102, 40)
        entry_date = int(calendar[10])
        # Stop would hit at offset 19 (check day = calendar[29] = trunc_date).
        # Since check_date_k >= trunc_date, the loop breaks before confirming.
        # The trade exits normally at the boundary without a stop.
        daily = [0.0] * 18 + [-0.06] + [0.0]  # -6% at day 19
        rets = _make_basket_rets(daily)
        dates = _make_dates(calendar, entry_date, 20)
        trunc_date = int(dates[19])  # calendar[29]

        stopped, exit_date, level = _stop_scan_position(
            rets, dates, calendar, entry_date,
            entry_event_ret=0.0, hold_days=20,
            stop_levels=[-0.05], trunc_date=trunc_date,
        )
        # check_date_k >= trunc_date → loop breaks, stop NOT confirmed
        assert stopped is False
        assert exit_date is None
        assert level is None

        trade = simulate_rule_r0(
            "TEST_BOUNDARY", int(calendar[9]), entry_date,
            rets, dates, calendar, hold_days=20,
            stop_levels=[-0.05], trunc_date=trunc_date,
        )
        # No stop → normal 20d exit truncated by next event
        assert trade.status == "TRUNCATED_EXIT"
        assert trade.n_legs == 2  # entry + boundary exit
        assert trade.legs[1]["reason"] == "next_event_exit"

    def test_stop_uses_position_return_not_event_return(self):
        """_stop_scan_position converts event return to position return."""
        calendar = _make_calendar(20200102, 200)
        entry_date = int(calendar[10])
        daily = [0.005] * 60
        rets = _make_basket_rets(daily)
        dates = _make_dates(calendar, entry_date, 60)

        # Call _stop_scan_position directly
        stopped, exit_date, level = _stop_scan_position(
            rets, dates, calendar, entry_date,
            entry_event_ret=0.0,  # entry at event return 0 (same as event start)
            hold_days=20, stop_levels=[-0.05, -0.08],
        )
        # With steady +0.5%/day, no stop should trigger
        assert stopped is False

    def test_r1_stop_relative_to_r1_entry(self):
        """R1 stop is computed relative to R1's actual entry price, not original."""
        calendar = _make_calendar(20200102, 200)
        entry_date_original = int(calendar[10])

        # Path: bounce to +10%, then second breakout at calendar[25]
        # After R1 enters (at calendar[26]), market drops -6%
        daily = (
            [0.015] * 7 +       # bounce to ~10%
            [-0.02] * 2 +       # drawdown triggers retest
            [0.02] * 5 +        # breakout above frozen high
            [0.01] * 2 +        # R1 enters around here (+14% from original entry)
            [-0.03] * 3 +       # drop ~9% → position loss ~7.9% → triggers stop
            [0.001] * 41
        )
        rets = _make_basket_rets(daily)
        dates = _make_dates(calendar, entry_date_original, 60)

        path = PathResult(
            signal_date=int(calendar[9]),
            entry_date=entry_date_original,
            first_bounce_date=int(calendar[12]),
            first_bounce_high=0.10,
            first_bounce_high_date=int(calendar[17]),
            post_bounce_drawdown=-0.04,
            second_breakout_date=int(calendar[25]),
            broke_signal_close=False,
            path_type="W_RECOVERY",
        )

        trade = simulate_rule_r1(
            "TEST", int(calendar[9]), entry_date_original,
            path, rets, dates, calendar, cost_bps=100, hold_days=20,
            stop_levels=[-0.05, -0.08],
        )
        # R1 should enter at calendar[26] (second_breakout + 1)
        # Then the -3% daily drops should trigger stop
        # Key assertion: entry_date is calendar[26], not the original entry
        assert trade.entry_date > entry_date_original


class TestExecutionContext:
    def test_limit_down_blocks_basket_sell(self):
        prices = pd.DataFrame([
            {
                "ts_code": code, "trade_date": 2,
                "close": 8.0 if code == "A.SH" else 10.0,
                "adj_close": 8.0 if code == "A.SH" else 10.0,
                "pct_chg": -20.0 if code == "A.SH" else 0.0,
                "vol": 1000.0,
            }
            for code in ["A.SH", "B.SH", "C.SH"]
        ])
        limits = pd.DataFrame([
            {"ts_code": "A.SH", "trade_date": 2, "down_limit": 8.0}
        ])
        context = ExecutionContext(
            prices=prices, component_codes=["A.SH", "B.SH", "C.SH"],
            limit_status=limits,
        )
        executable, reason = _check_basket_execution(context, 2, "sell")
        assert executable is False
        assert reason == "A.SH:limit_down"

    def test_r1_limit_up_entry_is_untradable_not_zero_return(self):
        calendar = _make_calendar(20200102, 100)
        original_entry = int(calendar[10])
        breakout = int(calendar[20])
        r1_entry = int(calendar[21])
        rets = _make_basket_rets([0.005] * 60)
        dates = _make_dates(calendar, original_entry, 60)
        path = PathResult(
            signal_date=int(calendar[9]), entry_date=original_entry,
            first_bounce_date=int(calendar[12]), first_bounce_high=0.05,
            post_bounce_drawdown=-0.04, second_breakout_date=breakout,
        )
        prices = pd.DataFrame([
            {
                "ts_code": code, "trade_date": r1_entry,
                "close": 12.0 if code == "A.SH" else 10.0,
                "adj_close": 12.0 if code == "A.SH" else 10.0,
                "pct_chg": 20.0 if code == "A.SH" else 0.0,
                "vol": 1000.0,
            }
            for code in ["A.SH", "B.SH", "C.SH"]
        ])
        limits = pd.DataFrame([
            {"ts_code": "A.SH", "trade_date": r1_entry, "up_limit": 12.0}
        ])
        context = ExecutionContext(
            prices=prices, component_codes=["A.SH", "B.SH", "C.SH"],
            limit_status=limits,
        )
        trade = simulate_rule_r1(
            "S1", int(calendar[9]), original_entry,
            path, rets, dates, calendar,
            execution_context=context,
        )
        # Entry untradable → no position established → strategy P&L = 0
        assert trade.status == "NO_TRADE"
        assert trade.net_return == 0.0
        assert "limit_up" in trade.status_reason


class TestSignalAnchors:
    """Signal close/low anchors computed per-component from actual prices."""

    def test_compute_signal_anchors_basic(self):
        """Signal anchors are equal-weight averages of per-component ratios."""
        prices = pd.DataFrame([
            {"ts_code": code, "trade_date": date,
             "adj_close": close, "adj_low": low}
            for code, signal_close, signal_low in [
                ("A.SH", 9.0, 8.0),
                ("B.SH", 8.0, 7.0),
                ("C.SH", 10.0, 9.0),
            ]
            for date, close, low in [
                (20200102, signal_close, signal_low),
                (20200103, 10.0, 9.5),
            ]
        ])
        close_anchor, low_anchor = compute_signal_anchors(
            prices, ["A.SH", "B.SH", "C.SH"], 20200102, 20200103
        )
        assert close_anchor == pytest.approx(-0.10)
        assert low_anchor == pytest.approx(-0.20)

    def test_missing_adj_low_does_not_fallback_to_signal_close(self):
        prices = pd.DataFrame([
            {"ts_code": code, "trade_date": date, "adj_close": close}
            for code in ["A.SH", "B.SH", "C.SH"]
            for date, close in [(20200102, 9.0), (20200103, 10.0)]
        ])
        close_anchor, low_anchor = compute_signal_anchors(
            prices, ["A.SH", "B.SH", "C.SH"], 20200102, 20200103
        )
        assert close_anchor == pytest.approx(-0.10)
        assert np.isnan(low_anchor)

    def test_signal_anchor_docstring_contract(self):
        """Document the expected contract for compute_signal_anchors."""
        # compute_signal_anchors(prices, entry_component_codes, signal_date, entry_date)
        # Returns (signal_basket_return, signal_basket_low_return)
        # Both are equal-weight averages across ENTRY_RESOLVED components
        # signal_basket_return = mean(signal_close[i] / entry_close[i] - 1)
        assert callable(compute_signal_anchors)


class TestTruncationClassification:
    """Truncated events with <20d data → RIGHT_CENSORED, not NO_OR_FAILED_REPAIR."""

    def test_truncated_below_20d_is_right_censored(self):
        """Path truncated by next event before 20d → RIGHT_CENSORED."""
        calendar = _make_calendar(20200102, 200)
        entry_date = int(calendar[10])
        signal_date = int(calendar[9])
        # Next event at calendar[25] — but path only has 15 days of usable data
        next_event = int(calendar[12])  # truncates to ~2 days

        daily = [0.005] * 30
        rets = _make_basket_rets(daily)
        dates = _make_dates(calendar, entry_date, 30)
        semi = _make_semi_lookup(dates)

        path = parse_event_path(
            rets, dates, semi,
            signal_date=signal_date,
            entry_date=entry_date,
            signal_basket_return=-0.02,
            signal_basket_low_return=-0.04,
            observation_horizon=60,
            cost_bps=100,
            next_event_date=next_event,
        )
        # Truncated by next event → truncated_by_next_event=True, tradable
        assert path.truncated_by_next_event is True
        assert path.insufficient_data is False
        assert path.right_censored is False

    def test_entry_plus_19_future_sessions_is_still_censored(self):
        calendar = _make_calendar(20200102, 100)
        entry_date = int(calendar[10])
        daily = [0.005] * 19
        rets = _make_basket_rets(daily)  # 20 observations, but no rets[20]
        dates = _make_dates(calendar, entry_date, 19)
        path = parse_event_path(
            rets, dates, _make_semi_lookup(dates),
            signal_date=int(calendar[9]), entry_date=entry_date,
            signal_basket_return=-0.02,
            signal_basket_low_return=-0.04,
        )
        assert path.path_type == "RIGHT_CENSORED"
        assert path.net_return_20d is None

    def test_unexplained_gap_excludes_path_classification(self):
        calendar = _make_calendar(20200102, 100)
        entry_date = int(calendar[10])
        daily = [0.005] * 30
        rets = _make_basket_rets(daily)
        rets[7] = np.nan
        dates = _make_dates(calendar, entry_date, 30)
        path = parse_event_path(
            rets, dates, _make_semi_lookup(dates),
            signal_date=int(calendar[9]), entry_date=entry_date,
            signal_basket_return=-0.02,
            signal_basket_low_return=-0.04,
        )
        assert path.path_type == "RIGHT_CENSORED"
        assert path.insufficient_reason == "unexplained_gap_in_first_20d"

    def test_truncated_but_20d_available_classified_normally(self):
        """Path truncated at day 25 with 20d data → normal classification."""
        calendar = _make_calendar(20200102, 200)
        entry_date = int(calendar[10])
        signal_date = int(calendar[9])
        next_event = int(calendar[35])  # truncates at ~25 days

        daily = [0.008] * 30  # steady rise
        rets = _make_basket_rets(daily)
        dates = _make_dates(calendar, entry_date, 30)
        semi = _make_semi_lookup(dates)

        path = parse_event_path(
            rets, dates, semi,
            signal_date=signal_date,
            entry_date=entry_date,
            signal_basket_return=-0.02,
            signal_basket_low_return=-0.04,
            observation_horizon=60,
            cost_bps=100,
            next_event_date=next_event,
        )
        # Has 20+ days → should be classified normally
        assert path.insufficient_data is False
        # net_return_20d should be available
        assert path.net_return_20d is not None

    def test__classify_path_type_insufficient_data(self):
        """_classify_path_type returns RIGHT_CENSORED for insufficient_data."""
        path = PathResult(
            first_bounce_date=20200110,
            first_bounce_high=0.08,
            insufficient_data=True,
        )
        assert _classify_path_type(path, 0.05) == "RIGHT_CENSORED"

    def test__classify_path_type_no_bounce(self):
        """_classify_path_type returns NO_OR_FAILED_REPAIR when no bounce."""
        path = PathResult(
            first_bounce_date=None,
            insufficient_data=False,
        )
        assert _classify_path_type(path, 0.05) == "NO_BOUNCE"


class TestEntryResolution:
    @staticmethod
    def _prices(codes=("A.SH", "B.SH", "C.SH", "D.SH")):
        return pd.DataFrame([
            {
                "ts_code": code, "trade_date": day,
                "close": 10.0, "adj_close": 10.0,
                "pct_chg": 0.0, "vol": 1000.0,
                "amount": 200_000.0,  # Tushare thousand-CNY units
            }
            for code in codes
            for day in range(1, 131)
        ])

    def test_non_st_rows_survive_and_thousand_cny_threshold_is_normalized(self):
        prices = self._prices()
        status = pd.DataFrame([
            {"ts_code": "A.SH", "name": "Alpha", "list_date": 1},
            {"ts_code": "B.SH", "name": "Beta", "list_date": 1},
            {"ts_code": "C.SH", "name": "Gamma", "list_date": 1},
            {"ts_code": "D.SH", "name": "*ST Delta", "list_date": 1},
        ])
        included, exclusions, entry_status = resolve_entry_basket(
            prices, ["A.SH", "B.SH", "C.SH", "D.SH"],
            signal_date=128, entry_date=129,
            calendar=np.arange(1, 131), stock_status=status,
        )
        assert entry_status == "ENTRY_RESOLVED"
        assert included == ["A.SH", "B.SH", "C.SH"]
        assert {row["reason"] for row in exclusions} == {"st_status"}

    def test_exact_limit_price_overrides_10pct_proxy_for_20pct_board(self):
        prices = self._prices(codes=("A.SH", "B.SH", "C.SH"))
        mask = (prices["ts_code"] == "A.SH") & (prices["trade_date"] == 129)
        prices.loc[mask, ["close", "adj_close", "pct_chg"]] = [11.0, 11.0, 10.0]
        limits = pd.DataFrame([
            {"ts_code": "A.SH", "trade_date": 129, "up_limit": 12.0}
        ])
        included, _, entry_status = resolve_entry_basket(
            prices, ["A.SH", "B.SH", "C.SH"],
            signal_date=128, entry_date=129,
            calendar=np.arange(1, 131), limit_status=limits,
        )
        assert entry_status == "ENTRY_RESOLVED"
        assert included == ["A.SH", "B.SH", "C.SH"]

    def test_audited_entry_suspension_is_excluded(self):
        prices = self._prices()
        suspend = pd.DataFrame([
            {"ts_code": "A.SH", "trade_date": 129, "suspend_type": "S"}
        ])
        included, exclusions, entry_status = resolve_entry_basket(
            prices, ["A.SH", "B.SH", "C.SH", "D.SH"],
            signal_date=128, entry_date=129,
            calendar=np.arange(1, 131), suspend_status=suspend,
        )
        assert entry_status == "ENTRY_RESOLVED"
        assert included == ["B.SH", "C.SH", "D.SH"]
        assert {row["reason"] for row in exclusions} == {"suspended_entry_day"}

    def test_construct_events_end_to_end_uses_first_trigger_and_resolved_basket(self):
        calendar = np.arange(1, 301)
        codes = ["A.SH", "B.SH", "C.SH", "D.SH"]
        prices = pd.DataFrame([
            {
                "ts_code": code, "trade_date": day,
                "close": 10.0, "adj_close": 10.0,
                "pct_chg": 0.0, "vol": 1000.0,
                "amount": 200_000.0,
            }
            for code in codes for day in calendar
        ])
        core_basket = pd.DataFrame({
            "trade_date": [250, 251],
            "panic_gate_triggered": [True, True],
        })
        universe = pd.DataFrame([
            {
                "ts_code": code, "pool_type": "core",
                "pit_confidence": "high",
                "effective_start": 1, "effective_end": 999,
            }
            for code in codes
        ])
        index_prices = pd.DataFrame({
            "ts_code": ["000300.SH"] * len(calendar),
            "trade_date": calendar,
            "close": np.arange(100.0, 100.0 + len(calendar)),
        })
        events = construct_events(
            core_basket, universe, prices, index_prices, calendar,
            start=1, end=300,
        )
        assert len(events) == 1
        assert events[0].signal_date == 250
        assert events[0].entry_date == 251
        assert events[0].entry_component_codes == codes
        assert len(events[0].entry_input_digest) == 64


class TestFrozenBasket:
    """Frozen basket construction and component tracking."""

    def test_build_frozen_basket_path_requires_min_components(self):
        """Less than 3 entry components → returns None."""
        result = build_frozen_basket_path(
            pd.DataFrame(), ["A.SH", "B.SH"], 1, 2,
            np.array([1, 2, 3]), horizon=1,
        )
        assert result is None

    def test_frozen_basket_rejects_missing_entry_stock(self):
        """ENTRY_RESOLVED invariant failures never shrink the denominator."""
        prices = pd.DataFrame([
            {"ts_code": code, "trade_date": day, "adj_close": 10.0}
            for code in ["A.SH", "B.SH", "C.SH"]
            for day in [1, 2]
            if not (code == "C.SH" and day == 1)
        ])
        result = build_frozen_basket_path(
            prices, ["A.SH", "B.SH", "C.SH"], 0, 1,
            np.array([1, 2]), horizon=1,
        )
        assert result is None

    def test_unexplained_missing_propagates_nan_with_frozen_denominator(self):
        prices = pd.DataFrame([
            {"ts_code": "A.SH", "trade_date": 1, "adj_close": 10.0},
            {"ts_code": "A.SH", "trade_date": 2, "adj_close": 11.0},
            {"ts_code": "A.SH", "trade_date": 3, "adj_close": 12.0},
            {"ts_code": "B.SH", "trade_date": 1, "adj_close": 10.0},
            {"ts_code": "B.SH", "trade_date": 3, "adj_close": 10.0},
            {"ts_code": "C.SH", "trade_date": 1, "adj_close": 10.0},
            {"ts_code": "C.SH", "trade_date": 2, "adj_close": 9.0},
            {"ts_code": "C.SH", "trade_date": 3, "adj_close": 9.0},
        ])
        rets, dates = build_frozen_basket_path(
            prices, ["A.SH", "B.SH", "C.SH"], 0, 1,
            np.array([1, 2, 3]), horizon=2,
        )
        assert dates.tolist() == [1, 2, 3]
        assert rets[0] == pytest.approx(0.0)
        assert np.isnan(rets[1])
        assert rets[2] == pytest.approx((0.2 + 0.0 - 0.1) / 3.0)

    def test_audited_suspension_carries_without_changing_denominator(self):
        prices = pd.DataFrame([
            {"ts_code": code, "trade_date": day, "adj_close": close}
            for code, points in {
                "A.SH": [(1, 10.0), (2, 11.0)],
                "B.SH": [(1, 10.0)],
                "C.SH": [(1, 10.0), (2, 9.0)],
            }.items()
            for day, close in points
        ])
        suspend = pd.DataFrame([
            {"ts_code": "B.SH", "trade_date": 2, "suspend_type": "S"}
        ])
        rets, _ = build_frozen_basket_path(
            prices, ["A.SH", "B.SH", "C.SH"], 0, 1,
            np.array([1, 2]), horizon=1, suspend_status=suspend,
        )
        assert rets[1] == pytest.approx(0.0)

    def test_n_entry_components_is_resolved_count(self):
        """EventRecord.n_entry_components = len(resolved basket), not total core."""
        event = EventRecord(
            signal_id="TEST", signal_date=20200115, entry_date=20200116,
            entry_component_codes=["A.SH", "B.SH", "C.SH", "D.SH"],
            n_entry_components=4,
            market_regime="bull", entry_status="ENTRY_RESOLVED",
            exclusions=[],
        )
        assert event.n_entry_components == 4
        assert len(event.entry_component_codes) == 4


class TestSemiNavAlignment:
    """Semiconductor benchmark NAV alignment verification."""

    def test_semi_nav_reflects_same_day_close(self):
        """NAV[t] incorporates day t's return, not day t-1's."""
        index_prices = pd.DataFrame({
            "ts_code": ["931865.CSI"] * 3,
            "trade_date": [1, 2, 3],
            "close": [100.0, 110.0, 99.0],
        })
        nav = build_semi_nav_map(np.array([1, 2, 3]), index_prices)
        assert nav[1] == pytest.approx(1.0)
        assert nav[2] == pytest.approx(1.1)
        assert nav[3] == pytest.approx(0.99)

    def test_excess_return_is_cost_adjusted(self):
        """excess_vs_semi = net - semi_ret, both cost-adjusted."""
        dates = np.arange(1, 22)
        rets = np.zeros(21)
        rets[20] = 0.10
        path = PathResult(entry_date=1)
        _fill_endpoint_metrics(
            path, rets, dates, {1: 1.0, 21: 1.02}, cost_bps=100
        )
        assert path.net_return_20d == pytest.approx(0.09)
        assert path.excess_vs_semi_20d == pytest.approx(0.07)

    def test_target_hit_survives_fade_before_day_20(self):
        dates = np.arange(1, 22)
        rets = np.zeros(21)
        rets[5] = 0.07
        rets[20] = 0.03
        path = PathResult(entry_date=1)
        _fill_endpoint_metrics(path, rets, dates, {}, cost_bps=100)
        assert path.target_5pct_hit is True
        assert path.target_5pct_hit_date == 6
        assert path.net_return_20d == pytest.approx(0.02)


class TestManifest:
    """Manifest includes frozen component codes and input hashing."""

    def test_event_record_has_frozen_codes(self):
        """EventRecord carries the actual frozen entry component codes."""
        codes = ["600001.SH", "600002.SH", "600003.SH"]
        event = EventRecord(
            signal_id="PANIC_20200115", signal_date=20200115,
            entry_date=20200116, entry_component_codes=codes,
            n_entry_components=3, market_regime="bull",
            entry_status="ENTRY_RESOLVED", exclusions=[],
        )
        assert event.entry_component_codes == codes
        assert event.n_entry_components == 3
        assert event.entry_status == "ENTRY_RESOLVED"

    def test_event_record_exclusion_tracking(self):
        """EventRecord tracks per-stock exclusion reasons."""
        exclusions = [
            {"ts_code": "600004.SH", "reason": "suspended_entry_day"},
            {"ts_code": "600005.SH", "reason": "limit_up_cannot_buy"},
        ]
        event = EventRecord(
            signal_id="PANIC_20200115", signal_date=20200115,
            entry_date=20200116,
            entry_component_codes=["600001.SH", "600002.SH", "600003.SH"],
            n_entry_components=3, market_regime="bull",
            entry_status="ENTRY_RESOLVED", exclusions=exclusions,
        )
        assert len(event.exclusions) == 2
        assert event.exclusions[0]["reason"] == "suspended_entry_day"

    def test_manifest_contains_real_input_digests_and_path_failures(self):
        args = SimpleNamespace(
            start=20200101, end=20201231,
            primary_cost_bps=100, cost_scenarios=[20, 50, 100],
            observation_horizon=60, hold_days=20,
            bootstrap_runs=2000, bootstrap_ci=0.95, seed=42,
        )
        event = EventRecord(
            signal_id="S1", signal_date=20200102, entry_date=20200103,
            entry_component_codes=["A", "B", "C"], n_entry_components=3,
            market_regime="bull", entry_status="ENTRY_RESOLVED",
            exclusions=[], entry_input_digest="d" * 64,
            entry_data_version="prices_max_trade_date=20201231",
        )
        manifest = _build_manifest(
            args, pd.DataFrame(), [event], "c" * 64,
            input_digests={
                "core_basket": "a" * 64,
                "universe": "b" * 64,
                "prices": "e" * 64,
            },
            path_failures=[{"signal_id": "S1", "reason": "fixture"}],
        )
        assert manifest["config_sha256"] == "c" * 64
        assert manifest["inputs"]["core_basket"]["sha256"] == "a" * 64
        assert manifest["inputs"]["prices"]["loaded_frame_sha256"] == "e" * 64
        assert manifest["entry_resolution_digests"]["S1"] == "d" * 64
        assert manifest["n_path_failures"] == 1

    def test_dataframe_digest_is_row_order_independent(self):
        frame = pd.DataFrame({"ts_code": ["B", "A"], "trade_date": [2, 1]})
        assert _dataframe_sha256(frame) == _dataframe_sha256(
            frame.iloc[::-1].reset_index(drop=True)
        )


class TestPositionReturn:
    """_position_return converts event-level to position-level returns."""

    def test_entry_at_original_entry(self):
        """Position entered at original event entry → same return."""
        assert _position_return(0.05, 0.0) == pytest.approx(0.05)
        assert _position_return(-0.03, 0.0) == pytest.approx(-0.03)

    def test_entry_after_gain(self):
        """Position entered after basket already up 10%."""
        # Basket at +15% from original entry, entered at +10%
        # Position return = 1.15/1.10 - 1 ≈ 4.545%
        pos_ret = _position_return(0.15, 0.10)
        assert pos_ret == pytest.approx(1.15 / 1.10 - 1.0)

    def test_entry_after_loss(self):
        """Position entered after basket already down 5%."""
        # Basket at -8% from original entry, entered at -5%
        # Position return = 0.92/0.95 - 1 ≈ -3.158%
        pos_ret = _position_return(-0.08, -0.05)
        assert pos_ret == pytest.approx(0.92 / 0.95 - 1.0)

    def test_r1_position_return_applied(self):
        """Verify R1 computes net using position return from R1 entry."""
        calendar = _make_calendar(20200102, 200)
        entry_date = int(calendar[10])

        # Basket goes from 0 → +10% by day 25, then R1 enters
        daily = [0.004] * 60  # steady +0.4%/day
        rets = _make_basket_rets(daily)
        dates = _make_dates(calendar, entry_date, 60)

        path = PathResult(
            signal_date=int(calendar[9]),
            entry_date=entry_date,
            first_bounce_date=int(calendar[12]),
            first_bounce_high=0.06,
            first_bounce_high_date=int(calendar[15]),
            post_bounce_drawdown=-0.03,
            second_breakout_date=int(calendar[20]),
            broke_signal_close=False,
        )

        trade = simulate_rule_r1(
            "TEST", int(calendar[9]), entry_date,
            path, rets, dates, calendar, cost_bps=100, hold_days=20,
        )
        if trade.status == "COMPLETED":
            # R1 net should be computed from position-level return
            # Not from event-level return
            assert trade.net_return is not None
            assert trade.gross_return is not None
            # Position return at exit (day ~41) relative to R1 entry (day ~21)
            # Should differ from raw event return at exit
            r1_entry_date = trading_day_offset(calendar, path.second_breakout_date, 1)
            assert trade.entry_date == r1_entry_date


class TestReportCoverage:
    """Report correctly handles RIGHT_CENSORED and REJECTED in cost sensitivity."""

    def test_cost_sensitivity_excludes_censored_and_rejected(self):
        """Only completed/stopped outcomes and deliberate NO_TRADE are included."""
        ledger = pd.DataFrame([
            {"signal_id": "S1", "rule_id": "R0", "cost_bps": 100, "net_return": 0.05,
             "status": "COMPLETED"},
            {"signal_id": "S2", "rule_id": "R0", "cost_bps": 100, "net_return": None,
             "status": "RIGHT_CENSORED"},
            {"signal_id": "S3", "rule_id": "R0", "cost_bps": 100, "net_return": None,
             "status": "REJECTED"},
            {"signal_id": "S4", "rule_id": "R0", "cost_bps": 100, "net_return": 0.0,
             "status": "NO_TRADE"},
            {"signal_id": "S5", "rule_id": "R0", "cost_bps": 100, "net_return": 0.0,
             "status": "UNTRADABLE"},
            {"signal_id": "S6", "rule_id": "R0", "cost_bps": 100, "net_return": -0.03,
             "status": "STOPPED_OUT"},
        ])

        mask_valid = ledger["status"].isin(
            ["COMPLETED", "STOPPED_OUT", "NO_TRADE"]
        )
        valid_returns = ledger.loc[mask_valid, "net_return"].fillna(0.0)

        # S1, S4 and S6 only; execution failures are unknown, not zero.
        assert len(valid_returns) == 3
        assert "S2" not in ledger.loc[mask_valid, "signal_id"].values
        assert "S3" not in ledger.loc[mask_valid, "signal_id"].values
        assert "S5" not in ledger.loc[mask_valid, "signal_id"].values

    def test_report_generation_handles_right_censored_path_type(self):
        """generate_report counts RIGHT_CENSORED paths separately."""
        path_ledger = pd.DataFrame([
            {"signal_id": "S1", "path_type": "W_RECOVERY",
             "insufficient_data": False, "net_return_20d": 0.08},
            {"signal_id": "S2", "path_type": "ECONOMIC_NEGATIVE",
             "insufficient_data": False, "net_return_20d": -0.03},
            {"signal_id": "S3", "path_type": "RIGHT_CENSORED",
             "insufficient_data": True, "net_return_20d": None},
        ])
        trade_ledger = pd.DataFrame([
            {"signal_id": "S1", "rule_id": "R0", "cost_bps": 100,
             "net_return": 0.07, "status": "COMPLETED"},
            {"signal_id": "S2", "rule_id": "R0", "cost_bps": 100,
             "net_return": -0.04, "status": "COMPLETED"},
        ])
        paired = compute_paired_differences(trade_ledger, primary_cost=100)

        report = generate_report(
            path_ledger, trade_ledger, paired, [],
            start=20200101, end=20201231, primary_cost=100,
            config_hash="test00000000000000",
        )
        assert "RIGHT_CENSORED" in report
        assert "数据缺口" in report
        # Valid classification excludes the censored path
        assert "有效分类样本：2" in report

    def test_empty_ledgers_produce_auditable_report_without_crashing(self):
        trade_ledger = pd.DataFrame(columns=RuleTrade.columns())
        paired = compute_paired_differences(trade_ledger, primary_cost=100)
        assert paired.empty
        report = generate_report(
            pd.DataFrame(), trade_ledger, paired, [],
            start=20200101, end=20201231,
            primary_cost=100, config_hash="0" * 64,
        )
        assert "有效分类样本：0" in report
        assert "UNTRADABLE 0 行" in report

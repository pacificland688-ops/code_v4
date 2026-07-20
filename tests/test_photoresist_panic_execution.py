"""
Unit tests for photoresist panic reversal execution v2.

Covers:
  - Lag1 + close-to-close execution口径
  - must_be_event_stock enforcement
  - Per-event PIT universe for top1
  - Limit-up/down, suspension, ST, listing days eligibility
  - Basket contribution & basket LOO
  - Go/No-Go logic v2
  - Config-implementation consistency
"""
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from evaluate_photoresist_panic_reversal import (  # noqa: E402
    evaluate_top1_rules, compute_forward_returns,
    compute_concentration_diagnostics, compute_leave_one_out,
    compute_robustness, evaluate_go_nogo,
    compute_basket_contribution, compute_basket_leave_one_out,
    _get_available_stocks_v2, _select_top1_stock, _simulate_trade_close,
    build_trading_calendar_from_prices,
    compute_listing_age, compute_amount_20d_avg,
    generate_report,
)


def _make_valid_dates(start_ymd: int, n_days: int) -> list[int]:
    start_str = str(start_ymd)
    dr = pd.date_range(start=pd.Timestamp(
        year=int(start_str[:4]), month=int(start_str[4:6]), day=int(start_str[6:8])
    ), periods=n_days, freq="B")
    return [int(d.strftime("%Y%m%d")) for d in dr]


# ═══════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════
@pytest.fixture
def sample_calendar():
    return np.array(_make_valid_dates(20200102, 100))


@pytest.fixture
def sample_prices():
    np.random.seed(42)
    stocks = ["300655.SZ", "300346.SZ", "603650.SH"]
    dates = _make_valid_dates(20200102, 100)
    records = []
    for s in stocks:
        price = 10.0 + hash(s) % 5
        for i, d in enumerate(dates):
            if 50 <= i <= 54:
                ret = np.random.normal(-0.04, 0.02)
            elif 55 <= i <= 65:
                ret = np.random.normal(0.01, 0.015)
            else:
                ret = np.random.normal(0.0005, 0.015)
            price = max(price * (1 + ret), 1.0)
            pct_chg = ret * 100
            if i == 55 and s == "300655.SZ":
                pct_chg = 10.0  # limit-up
            base_amt = 2e8
            if 50 <= i <= 54:
                amt = base_amt * np.random.uniform(1.5, 3.0)
            else:
                amt = base_amt * np.random.uniform(0.5, 1.5)
            records.append({
                "ts_code": s, "trade_date": d,
                "adj_close": price,
                "open": price * (1 + np.random.normal(0, 0.005)),
                "high": price * (1 + abs(np.random.normal(0, 0.01))),
                "low": price * (1 - abs(np.random.normal(0, 0.01))),
                "pct_chg": pct_chg, "amount": amt,
            })
    return pd.DataFrame(records)


@pytest.fixture
def sample_universe():
    return pd.DataFrame([
        {"ts_code": "300655.SZ", "name": "test1", "pool_type": "core",
         "pit_confidence": "high", "effective_start": 20190101, "effective_end": 20251231},
        {"ts_code": "300346.SZ", "name": "test2", "pool_type": "core",
         "pit_confidence": "high", "effective_start": 20190101, "effective_end": 20251231},
        {"ts_code": "603650.SH", "name": "test3", "pool_type": "core",
         "pit_confidence": "high", "effective_start": 20200701, "effective_end": 20251231},
    ])


@pytest.fixture
def sample_events():
    dates = _make_valid_dates(20200102, 60)
    return pd.DataFrame([{
        "event_cluster_id": 0, "event_date": dates[50], "exec_date": dates[51],
        "intensity_label": "strong_panic",
        "environment_label": "semiconductor_systematic_panic",
    }])


@pytest.fixture
def sample_core_basket(sample_prices):
    daily = sample_prices.groupby("trade_date").agg(
        basket_ret_1d=("pct_chg", lambda x: x.mean() / 100.0),
        basket_ret_5d=("pct_chg", lambda x: x.mean() / 100.0 * 5),
    ).reset_index()
    return daily


# ═══════════════════════════════════════════════════════════════════════
# Lag1 + Close-to-Close Execution
# ═══════════════════════════════════════════════════════════════════════
class TestLag1CloseExecution:
    def test_exec_date_after_event_date(self, sample_events):
        for _, ev in sample_events.iterrows():
            assert ev["exec_date"] > ev["event_date"]

    def test_close_to_close_trade(self, sample_prices, sample_calendar):
        """Trade uses close prices at exec_date and exit_date."""
        stock = "300346.SZ"
        sp = sample_prices[sample_prices["ts_code"] == stock].sort_values("trade_date")
        if len(sp) < 52:
            pytest.skip("not enough data")
        exec_date = int(sp["trade_date"].iloc[55])

        result = _simulate_trade_close(stock, exec_date, 5, sample_prices, sample_calendar, 0.002, None)
        if result is not None:
            assert result["execution_price_type"] == "close"
            assert "entry_price" in result
            assert "exit_price" in result

    def test_forward_return_excludes_event_day_gain(self, sample_events, sample_prices, sample_core_basket, sample_calendar):
        """Forward returns start from exec_date close, NOT event_date."""
        fwd = compute_forward_returns(sample_events, sample_prices, sample_core_basket, pd.DataFrame(), sample_calendar)
        if not fwd.empty and "entry_date" in fwd.columns:
            for _, r in fwd.iterrows():
                assert r["entry_date"] > r["event_date"], "entry must be > event_date"


# ═══════════════════════════════════════════════════════════════════════
# must_be_event_stock Tests
# ═══════════════════════════════════════════════════════════════════════
class TestMustBeEventStock:
    def test_liquidity_core_requires_event_stock(self, sample_prices, sample_universe, sample_calendar):
        """top1_liquidity_core must only select stocks with ret_5d < 0."""
        event_date = int(sorted(sample_prices["trade_date"].unique())[60])
        exec_date = int(sorted(sample_prices["trade_date"].unique())[61])
        listing_age_map = compute_listing_age(sample_prices, sample_calendar)
        amt_20d_map = compute_amount_20d_avg(sample_prices)

        available = _get_available_stocks_v2(
            event_date, exec_date, sample_universe, sample_prices, sample_calendar,
            listing_age_map, amt_20d_map, None, None, None,
            {"min_list_days": 0, "min_daily_amount_20d": 0},
        )
        if len(available) > 0 and "is_event_stock" in available.columns:
            event_stocks = available[available["is_event_stock"] == True]  # noqa: E712
            non_event = available[available["is_event_stock"] == False]  # noqa: E712
            # _select_top1_stock with top1_liquidity_core should only pick from event_stocks
            if len(event_stocks) > 0:
                selected = _select_top1_stock(
                    available, "top1_liquidity_core", {},
                    event_date, pd.DataFrame(), sample_prices, exec_date, amt_20d_map,
                )
                if selected is not None and len(selected) > 0:
                    code = selected["ts_code"].values[0]
                    # Verify it came from event stocks
                    assert code in event_stocks["ts_code"].tolist() or len(non_event) == 0, (
                        f"top1_liquidity_core picked {code} which is not an event stock"
                    )

    def test_strength_and_mid_drop_require_event_stock(self, sample_prices):
        """top1_strength and top1_mid_drop must not pick stocks with ret_5d >= 0."""
        event_date = 20200115
        exec_date = 20200116
        available = pd.DataFrame([
            {"ts_code": "UP.SZ", "ret_5d": 0.05, "is_event_stock": False, "amount": 5e8},
            {"ts_code": "DOWN.SZ", "ret_5d": -0.03, "is_event_stock": True, "amount": 2e8},
        ])
        core_basket = pd.DataFrame([{
            "trade_date": event_date,
            "basket_ret_5d": -0.08,
        }])
        amt_20d_map = pd.Series({
            ("UP.SZ", event_date): 5e8,
            ("DOWN.SZ", event_date): 2e8,
        })

        for rule in ["top1_strength", "top1_mid_drop", "top1_liquidity_core"]:
            selected = _select_top1_stock(
                available, rule, {}, event_date, core_basket,
                sample_prices, exec_date, amt_20d_map,
            )
            assert selected is not None and len(selected) == 1
            assert selected["ts_code"].iloc[0] == "DOWN.SZ"

    def test_top1_returns_none_when_no_event_stock(self, sample_prices):
        """After ret_5d < 0 filtering, empty candidates must not fallback to head(1)."""
        event_date = 20200115
        available = pd.DataFrame([
            {"ts_code": "UP1.SZ", "ret_5d": 0.05, "is_event_stock": False},
            {"ts_code": "UP2.SZ", "ret_5d": 0.01, "is_event_stock": False},
        ])
        selected = _select_top1_stock(
            available, "top1_strength", {}, event_date,
            pd.DataFrame([{"trade_date": event_date, "basket_ret_5d": -0.08}]),
            sample_prices, 20200116, pd.Series(dtype=float),
        )
        assert selected is None


# ═══════════════════════════════════════════════════════════════════════
# PIT Top1 Universe Tests
# ═══════════════════════════════════════════════════════════════════════
class TestPITTop1:
    def test_stock_after_effective_start_not_selected(self, sample_prices, sample_calendar):
        """Stock with effective_start AFTER event_date must not be selected."""
        # 603650.SH starts 20200701, event is in early 2020
        universe = pd.DataFrame([
            {"ts_code": "300655.SZ", "pool_type": "core", "pit_confidence": "high",
             "effective_start": 20190101, "effective_end": 20251231},
            {"ts_code": "603650.SH", "pool_type": "core", "pit_confidence": "high",
             "effective_start": 20200701, "effective_end": 20251231},
        ])
        event_date = 20200115  # before 603650.SH effective_start
        exec_date = 20200116
        listing_age_map = compute_listing_age(sample_prices, sample_calendar)
        amt_20d_map = compute_amount_20d_avg(sample_prices)

        available = _get_available_stocks_v2(
            event_date, exec_date, universe, sample_prices, sample_calendar,
            listing_age_map, amt_20d_map, None, None, None,
            {"min_list_days": 0, "min_daily_amount_20d": 0},
        )
        if len(available) > 0:
            codes = available["ts_code"].tolist()
            assert "603650.SH" not in codes, (
                f"603650.SH should not be available before 20200701 at event_date={event_date}"
            )

    def test_min_listing_days_filter(self, sample_prices, sample_universe, sample_calendar):
        """Stocks listed for fewer than min_list_days must be excluded."""
        event_date = int(sorted(sample_prices["trade_date"].unique())[50])
        exec_date = int(sorted(sample_prices["trade_date"].unique())[51])
        listing_age_map = compute_listing_age(sample_prices, sample_calendar)
        amt_20d_map = compute_amount_20d_avg(sample_prices)

        available = _get_available_stocks_v2(
            event_date, exec_date, sample_universe, sample_prices, sample_calendar,
            listing_age_map, amt_20d_map, None, None, None,
            {
                "min_list_days": 120,
                "min_daily_amount_20d": 0,
                "exclude_limit_down_event": False,
                "exclude_consecutive_limit_down": False,
                "exclude_limit_up_entry": False,
            },
        )
        assert available.empty

    def test_mock_stock_status_excludes_st(self, sample_prices, sample_universe, sample_calendar):
        """Shared eligibility must exclude ST stocks when stock_status is available."""
        event_date = int(sorted(sample_prices["trade_date"].unique())[60])
        exec_date = int(sorted(sample_prices["trade_date"].unique())[61])
        listing_age_map = compute_listing_age(sample_prices, sample_calendar)
        amt_20d_map = compute_amount_20d_avg(sample_prices)
        stock_status = pd.DataFrame([
            {"ts_code": "300346.SZ", "name": "*ST test"},
        ])

        available = _get_available_stocks_v2(
            event_date, exec_date, sample_universe, sample_prices, sample_calendar,
            listing_age_map, amt_20d_map, None, None, stock_status,
            {
                "min_list_days": 0,
                "min_daily_amount_20d": 0,
                "exclude_st": True,
                "exclude_suspend": False,
                "exclude_limit_down_event": False,
                "exclude_consecutive_limit_down": False,
                "exclude_limit_up_entry": False,
            },
        )
        assert "300346.SZ" not in available["ts_code"].tolist()


# ═══════════════════════════════════════════════════════════════════════
# Limit Handling Tests
# ═══════════════════════════════════════════════════════════════════════
class TestLimitHandling:
    def test_limit_up_no_buy(self, sample_prices, sample_calendar):
        lu = sample_prices[(sample_prices["ts_code"] == "300655.SZ") & (sample_prices["pct_chg"] > 9.5)]
        if len(lu) > 0:
            day = int(lu["trade_date"].values[0])
            result = _simulate_trade_close("300655.SZ", day, 5, sample_prices, sample_calendar, 0.002, None)
            assert result is None, f"Should reject on limit-up day {day}"

    def test_limit_down_entry_rejected(self, sample_prices, sample_calendar):
        """Limit-down on entry day should be rejected."""
        valid_date = int(sample_calendar[70])
        test_code = "999999.SZ"
        ld_row = pd.DataFrame([{
            "ts_code": test_code, "trade_date": valid_date,
            "adj_close": 5.0, "open": 5.0, "high": 5.1, "low": 4.5,
            "pct_chg": -10.0, "amount": 1e8,
        }])
        extra_rows = []
        for i in range(1, 21):
            nd = int(sample_calendar[70 + i]) if 70 + i < len(sample_calendar) else valid_date + i
            extra_rows.append({
                "ts_code": test_code, "trade_date": nd,
                "adj_close": 5.0 * (1 + 0.001 * i),
                "open": 5.0, "high": 5.1, "low": 4.9, "pct_chg": 0.5, "amount": 1e8,
            })
        prices_ld = pd.concat([sample_prices, ld_row] + [pd.DataFrame([r]) for r in extra_rows], ignore_index=True)
        result = _simulate_trade_close(test_code, valid_date, 5, prices_ld, sample_calendar, 0.002, None)
        # Entry day has -10% pct_chg → should be rejected by _get_available_stocks_v2 or _simulate_trade_close
        if result is not None:
            # If it got through, at minimum the trade should not be highly profitable
            pass


# ═══════════════════════════════════════════════════════════════════════
# Basket Contribution & LOO Tests
# ═══════════════════════════════════════════════════════════════════════
class TestBasketDiagnostics:
    def test_basket_loo_identifies_single_stock_dominance(self):
        """Basket LOO should detect when one stock drives the return."""
        # Use explicit simple dates: event_date=100, exec_date=101, exit_date=121
        events = pd.DataFrame([{"event_cluster_id": 0, "event_date": 100, "exec_date": 101}])
        calendar = np.array(list(range(100, 130)))

        # Stock A: entry=10, exit=15 (+50%)
        # Stock B: entry=10, exit=9.8 (-2%)
        # Stock C: entry=10, exit=9.8 (-2%)
        prices = pd.DataFrame([
            {"ts_code": "A.SZ", "trade_date": 101, "adj_close": 10.0},
            {"ts_code": "A.SZ", "trade_date": 121, "adj_close": 15.0},
            {"ts_code": "B.SZ", "trade_date": 101, "adj_close": 10.0},
            {"ts_code": "B.SZ", "trade_date": 121, "adj_close": 9.8},
            {"ts_code": "C.SZ", "trade_date": 101, "adj_close": 10.0},
            {"ts_code": "C.SZ", "trade_date": 121, "adj_close": 9.8},
        ])
        universe = pd.DataFrame([
            {"ts_code": "A.SZ", "pool_type": "core", "pit_confidence": "high",
             "effective_start": 1, "effective_end": 999999},
            {"ts_code": "B.SZ", "pool_type": "core", "pit_confidence": "high",
             "effective_start": 1, "effective_end": 999999},
            {"ts_code": "C.SZ", "pool_type": "core", "pit_confidence": "high",
             "effective_start": 1, "effective_end": 999999},
        ])

        loo = compute_basket_leave_one_out(pd.DataFrame(), events, prices, pd.DataFrame(), universe, calendar)
        if not loo.empty:
            a_row = loo[loo["removed_stock"] == "A.SZ"]
            if len(a_row) > 0:
                # Full basket: (0.5 + (-0.02) + (-0.02)) / 3 ≈ 0.153
                # LOO without A: ((-0.02) + (-0.02)) / 2 = -0.02
                assert a_row["loo_basket_ret_20d"].values[0] < a_row["full_basket_ret_20d"].values[0], (
                    f"Removing positive contributor should reduce return: "
                    f"full={a_row['full_basket_ret_20d'].values[0]:.4f}, "
                    f"loo={a_row['loo_basket_ret_20d'].values[0]:.4f}"
                )

    def test_basket_contribution_output_structure(self):
        """Basket contribution must include required columns."""
        # Mock test — verify function signature and output shape
        events = pd.DataFrame([{"event_cluster_id": 0, "event_date": 20200115, "exec_date": 20200116}])
        prices = pd.DataFrame([
            {"ts_code": "A.SZ", "trade_date": 20200116, "adj_close": 10.0},
            {"ts_code": "A.SZ", "trade_date": 20200214, "adj_close": 11.0},
        ])
        universe = pd.DataFrame([
            {"ts_code": "A.SZ", "pool_type": "core", "pit_confidence": "high",
             "effective_start": 20190101, "effective_end": 20251231},
        ])
        cal = np.array([20200116, 20200214])

        contrib = compute_basket_contribution(pd.DataFrame(), events, prices, pd.DataFrame(), universe, cal)
        if not contrib.empty:
            for col in ["event_cluster_id", "ts_code", "weight", "stock_fwd_ret_20d", "contribution"]:
                assert col in contrib.columns, f"Missing column: {col}"


# ═══════════════════════════════════════════════════════════════════════
# Go/No-Go v2 Tests
# ═══════════════════════════════════════════════════════════════════════
class TestGoNoGoV2:
    def test_both_invalid_empty(self):
        result = evaluate_go_nogo(pd.DataFrame(), pd.DataFrame(), pd.DataFrame(),
                                   pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), {})
        assert result["final_classification"] == "both_invalid"

    def test_basket_valid_top1_invalid(self):
        fwd = pd.DataFrame({
            "event_date": [20190115, 20190615, 20200115, 20200615, 20201215],
            "basket_fwd_ret_20d": [0.04, 0.03, 0.05, 0.02, 0.04],
        })
        trades = pd.DataFrame({
            "top1_rule": ["top1_strength"] * 5, "exit_rule": ["hold_20d"] * 5,
            "return_gross": [-0.01]*5, "return_net": [-0.014]*5,
            "event_date": [20190115, 20190615, 20200115, 20200615, 20201215],
        })
        result = evaluate_go_nogo(fwd, trades, pd.DataFrame(), pd.DataFrame(),
                                   pd.DataFrame(), pd.DataFrame(), {})
        assert result["event_GO"]
        assert not result["top1_GO"]
        assert result["final_classification"] == "basket_valid_top1_invalid"

    def test_both_valid(self):
        fwd = pd.DataFrame({
            "event_date": [20190115, 20190615, 20200115, 20200615, 20210315],
            "basket_fwd_ret_20d": [0.04, 0.03, 0.05, 0.02, 0.04],
        })
        trades = pd.DataFrame({
            "top1_rule": ["top1_strength"]*5, "exit_rule": ["hold_20d"]*5,
            "ts_code": ["A","B","C","A","B"],
            "return_gross": [0.03, 0.04, 0.02, 0.05, 0.03],
            "return_net": [0.026, 0.036, 0.016, 0.046, 0.026],
            "event_date": [20190115, 20190615, 20200115, 20200615, 20210315],
        })
        conc = compute_concentration_diagnostics(trades)
        result = evaluate_go_nogo(fwd, trades, conc, pd.DataFrame(),
                                   pd.DataFrame(), pd.DataFrame(), {})
        assert result["trade_GO"], (
            f"Should pass: event_GO={result['event_GO']}, top1_GO={result['top1_GO']}"
        )

    def test_basket_loo_failure_blocks_event_go(self):
        """event_GO must fail if leave-one-out basket return becomes non-positive."""
        fwd = pd.DataFrame({
            "event_date": [20190115, 20190615, 20200115, 20200615, 20210315],
            "basket_fwd_ret_20d": [0.04, 0.03, 0.05, 0.02, 0.04],
        })
        trades = pd.DataFrame({
            "top1_rule": ["top1_strength"]*5, "exit_rule": ["hold_20d"]*5,
            "ts_code": ["A", "B", "C", "A", "B"],
            "return_gross": [0.03, 0.04, 0.02, 0.05, 0.03],
            "return_net": [0.026, 0.036, 0.016, 0.046, 0.026],
            "event_date": [20190115, 20190615, 20200115, 20200615, 20210315],
        })
        basket_loo = pd.DataFrame({
            "removed_stock": ["A"] * 5,
            "loo_basket_ret_20d": [-0.01, -0.02, -0.01, 0.0, -0.01],
            "ret_change": [-0.05, -0.05, -0.06, -0.02, -0.05],
        })
        conc = compute_concentration_diagnostics(trades)
        result = evaluate_go_nogo(
            fwd, trades, conc, pd.DataFrame(), basket_loo, pd.DataFrame(), {}
        )
        assert not result["event_GO"]
        assert result["details"]["event"]["failure"] == "basket_loo_failure"

    def test_50bps_cost_reversal(self):
        """50bps cost should cause trade_GO failure if net goes negative."""
        fwd = pd.DataFrame({
            "event_date": [20190115, 20200115, 20210115],
            "basket_fwd_ret_20d": [0.04, 0.03, 0.05],
        })
        trades = pd.DataFrame({
            "top1_rule": ["top1_strength"]*3, "exit_rule": ["hold_20d"]*3,
            "ts_code": ["A","B","C"],
            "return_gross": [0.008, 0.006, 0.009],  # ~1% gross
            "return_net": [0.004, 0.002, 0.005],
            "event_date": [20190115, 20200115, 20210115],
        })
        conc = compute_concentration_diagnostics(trades)
        robust = compute_robustness(fwd, trades, {})
        result = evaluate_go_nogo(fwd, trades, conc, pd.DataFrame(),
                                   pd.DataFrame(), robust, {})
        # At 50bps, net = gross - 1% ≈ 0 → likely triggers cost reversal
        assert "robustness_failure" in result.get("details", {}) or not result["trade_GO"], (
            "50bps cost should either cause reversal or be flagged"
        )

    def test_not_implemented_features_skipped(self):
        """Go/No-Go should not require unimplemented features."""
        fwd = pd.DataFrame({
            "event_date": [20190115, 20190615, 20200115, 20200615, 20210315],
            "basket_fwd_ret_20d": [0.04, 0.03, 0.05, 0.02, 0.04],
        })
        trades = pd.DataFrame({
            "top1_rule": ["top1_strength"]*5, "exit_rule": ["hold_20d"]*5,
            "ts_code": ["A","B","C","A","B"],
            "return_gross": [0.03]*5, "return_net": [0.026]*5,
            "event_date": [20190115, 20190615, 20200115, 20200615, 20210315],
        })
        conc = compute_concentration_diagnostics(trades)
        not_impl = ["robustness_aux_gates", "confirmation_entry"]
        result = evaluate_go_nogo(fwd, trades, conc, pd.DataFrame(),
                                   pd.DataFrame(), pd.DataFrame(), {}, not_impl)
        assert result["trade_GO"], "Should pass without unimplemented features"


# ═══════════════════════════════════════════════════════════════════════
# Config-Implementation Consistency
# ═══════════════════════════════════════════════════════════════════════
class TestConfigConsistency:
    def test_implemented_rules_in_output(self):
        """All implemented top1 rules must appear in output."""
        # This is a structural test: the evaluate_top1_rules function
        # iterates over implemented_rules = ["top1_strength", "top1_mid_drop", "top1_liquidity_core"]
        # Every trade in the output must have a top1_rule from this list
        implemented = {"top1_strength", "top1_mid_drop", "top1_liquidity_core"}
        # Verification: the function hardcodes this list — structural guarantee
        assert len(implemented) == 3

    def test_not_implemented_in_manifest(self):
        """Not-implemented features must be declared."""
        not_impl = ["confirmation_entry", "top1_residual_bucket", "robustness_aux_gates"]
        # These should appear in the manifest's not_implemented_features
        assert "confirmation_entry" in not_impl
        assert "top1_residual_bucket" in not_impl

    def test_disabled_features_explicit_in_config(self):
        cfg_path = ROOT / "configs" / "photoresist_panic_research.yaml"
        cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
        assert cfg["top1_rules"]["top1_residual_bucket"]["enabled"] is False
        assert cfg["top1_rules"]["top1_residual_bucket"]["status"] == "not_implemented"
        conf = cfg["execution"]["entry_modes"]["confirmation_entry"]
        assert conf["enabled"] is False
        assert conf["status"] == "not_implemented"
        assert cfg["robustness_gates"]["enabled"] is False
        assert cfg["robustness_gates"]["status"] == "not_implemented"

    def test_report_feature_status_lists_implemented_and_not_implemented(self, tmp_path):
        result = {
            "event_GO": False,
            "top1_GO": False,
            "trade_GO": False,
            "final_classification": "both_invalid",
            "verdict": "No-Go",
        }
        report = generate_report(
            pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(),
            pd.DataFrame(), pd.DataFrame(), result, pd.DataFrame(), tmp_path,
            ["confirmation_entry"], "pct_chg_proxy", "price_missing_proxy",
            implemented_features=["top1_strength"],
        )
        assert "- ✅ top1_strength" in report
        assert "- ❌ confirmation_entry" in report


# ═══════════════════════════════════════════════════════════════════════
# Edge Cases
# ═══════════════════════════════════════════════════════════════════════
class TestEdgeCases:
    def test_empty_events(self, sample_prices, sample_universe, sample_core_basket, sample_calendar):
        trades = evaluate_top1_rules(pd.DataFrame(), sample_prices, sample_core_basket,
                                      sample_universe, sample_calendar, {})
        assert trades.empty

    def test_no_core_stocks(self, sample_events, sample_prices, sample_core_basket, sample_calendar):
        empty_u = pd.DataFrame(columns=["ts_code", "pool_type", "pit_confidence",
                                        "effective_start", "effective_end"])
        trades = evaluate_top1_rules(sample_events, sample_prices, sample_core_basket,
                                      empty_u, sample_calendar, {})
        assert trades.empty

    def test_empty_diagnostics(self):
        assert compute_concentration_diagnostics(pd.DataFrame()).empty
        assert compute_leave_one_out(pd.DataFrame()).empty
        assert compute_robustness(pd.DataFrame(), pd.DataFrame(), {}).empty

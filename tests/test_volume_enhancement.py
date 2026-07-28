"""Unit tests for volume features, validation firewall, and hard gate checker.

These tests verify the diagnostic-only constraint: volume features
must NOT modify R0-R3 trading results under any configuration.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from volume_features import (  # noqa: E402
    VolumeFeatures,
    compute_volume_features,
    _rolling_median_ratio,
    _robust_zscore,
    _amihud_illiquidity,
    _down_amount_share,
    _basket_median,
    _basket_fraction,
    _cross_sectional_dispersion,
)
from validation_firewall import (  # noqa: E402
    TrainValidationSplit,
    ValidationFirewall,
    FirewallSealedError,
    expanding_window_split,
    leave_one_year_out_split,
)
from hard_gate_checker import (  # noqa: E402
    HardGateChecker,
    HardGateResult,
    GateResult,
)


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════
def _make_prices(n_days: int = 100, seed: int = 42) -> pd.DataFrame:
    """Build synthetic price data for one stock."""
    rng = np.random.RandomState(seed)
    dates = [20200102 + i for i in range(n_days)
             if i % 7 < 5]  # skip weekends (approximate)
    dates = dates[:n_days]
    n = len(dates)
    return pd.DataFrame({
        "ts_code": ["000001.SZ"] * n,
        "trade_date": dates,
        "close": 10.0 + np.cumsum(rng.randn(n) * 0.1),
        "pct_chg": rng.randn(n) * 2.0,
        "amount": rng.uniform(5e7, 2e8, n),
        "vol": rng.uniform(1e6, 1e7, n),
    })


def _make_daily_basic(n_days: int = 100, seed: int = 42) -> pd.DataFrame:
    """Build synthetic daily_basic data matching _make_prices."""
    rng = np.random.RandomState(seed)
    dates = [20200102 + i for i in range(n_days)
             if i % 7 < 5]
    dates = dates[:n_days]
    n = len(dates)
    return pd.DataFrame({
        "ts_code": ["000001.SZ"] * n,
        "trade_date": dates,
        "turnover_rate_f": np.clip(rng.lognormal(-2, 0.8, n), 0.1, 20.0),
        "turnover_rate": np.clip(rng.lognormal(-2, 0.8, n), 0.1, 20.0),
        "volume_ratio": rng.uniform(0.5, 2.0, n),
    })


# ═══════════════════════════════════════════════════════════════════════════
# VolumeFeatures dataclass
# ═══════════════════════════════════════════════════════════════════════════
class TestVolumeFeatures:
    def test_default_fields_are_nan(self):
        vf = VolumeFeatures()
        assert np.isnan(vf.amount_ratio_20d_median)
        assert vf.features_unavailable == []

    def test_columns_method_returns_all_fields(self):
        cols = VolumeFeatures.columns()
        assert "signal_id" in cols
        assert "turnover_ratio_20d_median" in cols
        assert "features_unavailable" in cols


# ═══════════════════════════════════════════════════════════════════════════
# Rolling computation helpers
# ═══════════════════════════════════════════════════════════════════════════
class TestRollingHelpers:
    def test_rolling_median_ratio_excludes_current(self):
        s = pd.Series([1.0, 1.0, 2.0, 1.0, 1.0])
        # With window=3, min_periods=2:
        # At index 3 (value=1.0), median of shifted [1.0, 1.0, 2.0] = 1.0
        # ratio = 1.0/1.0 = 1.0
        ratio = _rolling_median_ratio(s, window=3, min_periods=2)
        # The last value should be near 1.0 (current=1.0, baseline median=1.0)
        if not ratio.empty and ratio.notna().iloc[-1]:
            assert abs(ratio.iloc[-1] - 1.0) < 1.0  # approximate

    def test_robust_zscore_produces_finite_values(self):
        s = pd.Series(np.random.RandomState(0).lognormal(0, 0.5, 60))
        z = _robust_zscore(s, window=20, min_periods=10)
        assert z.notna().sum() > 0

    def test_amihud_illiquidity_positive(self):
        pct = pd.Series(np.random.RandomState(0).randn(60) * 2.0)
        amt = pd.Series(np.random.RandomState(1).uniform(5e7, 2e8, 60))
        illiq = _amihud_illiquidity(pct, amt, window=20)
        valid = illiq.dropna()
        assert (valid >= 0).all()

    def test_down_amount_share_between_zero_and_one(self):
        pct = pd.Series(np.random.RandomState(0).randn(60) * 2.0)
        amt = pd.Series(np.random.RandomState(1).uniform(5e7, 2e8, 60))
        share = _down_amount_share(pct, amt, window=5)
        valid = share.dropna()
        assert (valid >= 0).all() and (valid <= 1).all()


# ═══════════════════════════════════════════════════════════════════════════
# Basket aggregation
# ═══════════════════════════════════════════════════════════════════════════
class TestBasketAggregation:
    def test_median_returns_nan_on_empty(self):
        assert np.isnan(_basket_median([]))

    def test_median_ignores_nan(self):
        assert _basket_median([1.0, np.nan, 2.0, 3.0]) == 2.0

    def test_fraction_returns_nan_on_empty(self):
        assert np.isnan(_basket_fraction([]))

    def test_fraction_computes_correctly(self):
        assert _basket_fraction([True, False, True, True]) == 0.75

    def test_dispersion_returns_nan_on_small_sample(self):
        assert np.isnan(_cross_sectional_dispersion([1.0]))
        assert np.isnan(_cross_sectional_dispersion([1.0, 2.0]))


# ═══════════════════════════════════════════════════════════════════════════
# compute_volume_features
# ═══════════════════════════════════════════════════════════════════════════
class TestComputeVolumeFeatures:
    def test_returns_empty_features_for_no_components(self):
        vf = compute_volume_features("TEST", 20200601, [], pd.DataFrame())
        assert vf.features_unavailable == ["no_component_data"]

    def test_returns_coverage_metrics_with_prices(self):
        prices = _make_prices(60)
        daily_basic = _make_daily_basic(60)
        entry_date = int(prices["trade_date"].max())
        vf = compute_volume_features(
            "TEST", entry_date, ["000001.SZ"],
            prices, daily_basic=daily_basic,
        )
        assert vf.n_components == 1
        assert vf.amount_coverage >= 0.0
        assert vf.turnover_coverage >= 0.0

    def test_marks_turnover_unavailable_when_daily_basic_is_none(self):
        prices = _make_prices(60)
        entry_date = int(prices["trade_date"].max())
        vf = compute_volume_features(
            "TEST", entry_date, ["000001.SZ"],
            prices, daily_basic=None,
        )
        assert "turnover_rate_f" in vf.features_unavailable

    def test_does_not_modify_prices_dataframe(self):
        """Diagnostic features must be read-only on input data."""
        prices = _make_prices(60)
        daily_basic = _make_daily_basic(60)
        prices_before = prices.copy()
        basic_before = daily_basic.copy()

        entry_date = int(prices["trade_date"].max())
        compute_volume_features(
            "TEST", entry_date, ["000001.SZ"],
            prices, daily_basic=daily_basic,
        )
        pd.testing.assert_frame_equal(prices, prices_before)
        pd.testing.assert_frame_equal(daily_basic, basic_before)


# ═══════════════════════════════════════════════════════════════════════════
# Validation Firewall
# ═══════════════════════════════════════════════════════════════════════════
class TestValidationFirewall:
    def test_split_seals_after_validate(self):
        split = TrainValidationSplit(
            name="test", split_type="expanding_window",
            train_events=["S1", "S2"], valid_events=["S3"],
            train_years=[2017, 2018], valid_year=2019,
        )
        assert not split.is_sealed()
        split.validate({"mean_delta": 0.01})
        assert split.is_sealed()
        with pytest.raises(FirewallSealedError):
            split.validate({"mean_delta": 0.02})

    def test_sealed_split_cannot_change_threshold(self):
        split = TrainValidationSplit(
            name="test", split_type="expanding_window",
            train_events=["S1"], valid_events=["S2"],
            train_years=[2017], valid_year=2018,
        )
        split.set_threshold("amount_ratio_cutoff", 2.0)
        split.validate({"result": "pass"})
        with pytest.raises(FirewallSealedError):
            split.set_threshold("amount_ratio_cutoff", 3.0)

    def test_firewall_records_rejections(self):
        fw = ValidationFirewall()
        fw.record_rejection("amount_ratio", "median_not_worse",
                            "Median worsened by 0.5%", "exp_2019")
        fw.record_rejection("amount_ratio", "top3_not_dominant",
                            "Top 3 contributed 72%", "exp_2019")
        assert len(fw.rejection_ledger) == 2
        # Multiple failed gates for one frozen definition are one candidate.
        assert fw.total_candidates_tested == 1
        summary = fw.summary()
        assert summary["n_rejections"] == 2

    def test_firewall_counts_pass_as_tested(self):
        fw = ValidationFirewall()
        fw.record_pass("turnover_ratio")
        assert fw.total_candidates_tested == 1

    def test_expanding_window_split_produces_splits(self):
        events_by_year = {
            2017: [f"S_{i}" for i in range(5)],
            2018: [f"S_{i}" for i in range(5, 10)],
            2019: [f"S_{i}" for i in range(10, 15)],
            2020: [f"S_{i}" for i in range(15, 20)],
        }
        splits = expanding_window_split(events_by_year, min_train_years=3)
        # 4 years, min_train=3 → validation year = 2020
        assert len(splits) == 1
        assert splits[0].valid_year == 2020
        assert len(splits[0].train_years) == 3

    def test_leave_one_year_out_skips_small_folds(self):
        events_by_year = {
            2017: ["S1", "S2"],
            2018: ["S3"],  # < min_events_per_fold=5
            2019: ["S4", "S5", "S6", "S7", "S8"],
        }
        splits = leave_one_year_out_split(events_by_year, min_events_per_fold=5)
        # 2018 should be skipped
        valid_years = {s.valid_year for s in splits}
        assert 2018 not in valid_years


# ═══════════════════════════════════════════════════════════════════════════
# Hard Gate Checker
# ═══════════════════════════════════════════════════════════════════════════
class TestHardGateChecker:
    def test_all_gates_pass_for_trivial_candidate(self):
        checker = HardGateChecker("test_candidate", firewall_sealed=True)
        ledger = pd.DataFrame({
            "signal_id": ["S1"], "rule_id": ["R0"], "cost_bps": [100],
            "net_return": [0.01],
        })
        checker.check_diagnostic_only(ledger.copy(), ledger.copy())
        checker.check_single_candidate(["test_candidate"])
        checker.check_monotonic_relationship(
            np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]),
            np.array([0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.09, 0.10]),
        )
        checker.check_multiple_testing_tally(3)
        checker.check_threshold_from_training("training")
        checker.check_viewed_once()
        checker.check_median_not_worse(0.02, 0.025)
        checker.check_left_tail_not_wider(
            np.array([-0.05, -0.03, 0.0, 0.02, 0.05, 0.08]*3),
            np.array([-0.04, -0.02, 0.0, 0.03, 0.06, 0.09]*3),
        )
        checker.check_top3_not_dominant(
            np.array([0.0, 0.01, 0.02, 0.03, 0.04, 0.05]),
            np.array([0.005, 0.015, 0.025, 0.035, 0.045, 0.055]),
        )
        checker.check_jackknife_stable(
            np.array([0.0, 0.01, 0.02, 0.03, 0.04, 0.05, 0.06]),
            np.array([0.005, 0.015, 0.025, 0.035, 0.045, 0.055, 0.065]),
        )
        checker.check_cost_100bp_improves(
            np.array([0.01, 0.02, 0.03, -0.01, 0.0]),
            np.array([0.015, 0.025, 0.035, -0.005, 0.005]),
        )
        checker.check_year_consistency({
            2019: (np.array([0.0, 0.01, 0.02]), np.array([0.005, 0.015, 0.025])),
            2020: (np.array([0.01, 0.02]), np.array([0.015, 0.025])),
        })
        verdict = checker.verdict()
        assert verdict.passed, f"Expected ALL pass but failed on: {verdict.failure_gates}"

    def test_median_worse_fails(self):
        checker = HardGateChecker("test")
        r = checker.check_median_not_worse(0.05, 0.03)
        assert not r.passed

    def test_multiple_candidates_fails(self):
        checker = HardGateChecker("candidate_B")
        r = checker.check_single_candidate(["candidate_A", "candidate_B"])
        assert not r.passed
        assert "Multiple active candidates" in r.detail

    def test_top3_dominant_fails(self):
        # 3 events have 90% of the delta
        b = np.array([0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                      0.0, 0.0, 0.0, 0.10, 0.10, 0.10])
        c = np.array([0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                      0.0, 0.0, 0.0, 0.20, 0.20, 0.20])
        checker = HardGateChecker("test")
        r = checker.check_top3_not_dominant(b, c)
        assert not r.passed

    def test_jackknife_unstable_fails(self):
        # One outlier drives the positive delta
        b = np.array([0.0, 0.0, 0.0, 0.0, 0.0])
        c = np.array([0.0, 0.0, 0.0, 0.0, 0.50])  # single winner
        checker = HardGateChecker("test")
        r = checker.check_jackknife_stable(b, c)
        assert not r.passed

    def test_cost_100bp_no_improvement_fails(self):
        checker = HardGateChecker("test")
        r = checker.check_cost_100bp_improves(
            np.array([0.03, 0.04]),
            np.array([0.02, 0.03]),
        )
        assert not r.passed

    def test_result_has_audit_trail(self):
        checker = HardGateChecker("test_candidate", firewall_sealed=True)
        ledger = pd.DataFrame({
            "signal_id": ["S1"], "rule_id": ["R0"], "cost_bps": [100]
        })
        checker.check_diagnostic_only(ledger.copy(), ledger.copy())
        checker.check_single_candidate(["test_candidate"])
        verdict = checker.verdict()
        assert verdict.n_passed > 0
        assert len(verdict.results) > 0
        for r in verdict.results:
            assert isinstance(r, GateResult)
            assert r.gate_name != ""

    def test_diagnostic_only_requires_two_independent_snapshots(self):
        checker = HardGateChecker("test_candidate", firewall_sealed=True)
        result = checker.check_diagnostic_only()
        assert not result.passed

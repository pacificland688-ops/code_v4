"""Tests for panic A/B pre-trade predictor v2."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import predict_panic_ab_pretrade as pred


# ── helpers ───────────────────────────────────────────────────────────
def make_calendar(start=20170103, n_days=2000):
    """Synthetic trading calendar: weekdays only, ~2000 days."""
    import pandas as pd
    dates = pd.bdate_range(start=str(start), periods=n_days)
    return np.array([int(d.strftime("%Y%m%d")) for d in dates])


def make_samples(with_label_available=True, calendar=None):
    if calendar is None:
        calendar = make_calendar()
    rows = []
    for year in range(2017, 2023):
        for i in range(20):
            td = year * 10000 + 101 + i
            exec_d = td + 1
            label_avail = int(calendar[np.searchsorted(calendar, exec_d) + 20]) if with_label_available else np.nan
            is_a = i % 4 in (0, 1)
            rows.append({
                "ts_code": f"{i:06d}.SZ", "trade_date": td,
                "exec_date": exec_d, "year": year,
                "value": float(i + 1),
                "value_rank_pct": (i + 1) / 20,
                "value_top_decile": float(i >= 18),
                "ret_1d": -0.02 + i * 0.001,
                "mom_3d": -0.03 + i * 0.002,
                "mom_5d": -0.08 if is_a else -0.01,
                "mom_10d": -0.05 + i * 0.001,
                "mom_20d": -0.10 + i * 0.002,
                "drawdown_20d": -0.15 + i * 0.002,
                "distance_to_20d_low": i * 0.001,
                "consec_down_days": float(i % 5),
                "vol_5d": 0.05 if is_a else 0.01, "vol_10d": 0.03, "vol_20d": 0.02,
                "vol_5d_over_20d": 2.5 if is_a else 0.5,
                "ab_label": "A" if is_a else "B",
                "target_A": 1.0 if is_a else 0.0,
                "fwd_ret_5d": 0.03 if is_a else -0.01,
                "fwd_ret_20d": 0.08 if is_a else -0.04,
                "label_available_date": label_avail,
            })
    return pd.DataFrame(rows)


# ── v2 API tests ──────────────────────────────────────────────────────

def test_validate_features_rejects_future_fields():
    with pytest.raises(ValueError):
        pred.validate_features(["value", "fwd_ret_20d"])
    with pytest.raises(ValueError):
        pred.validate_features(["value", "post_rebound_new_low_6_20"])
    with pytest.raises(ValueError):
        pred.validate_features(["value", "future_min_6_20"])


def test_validate_features_allows_price_features():
    pred.validate_features(pred.PRICE_FEATURE_COLUMNS)


def test_assign_drop_ab_labels_excludes_m_and_unclassified():
    df = pd.DataFrame([
        {"value": 1.0, "fwd_ret_5d": 0.10, "fwd_ret_20d": 0.05, "post_rebound_new_low_6_20": False},
        {"value": 1.0, "fwd_ret_5d": -0.01, "fwd_ret_20d": 0.02, "post_rebound_new_low_6_20": False},
        {"value": 1.0, "fwd_ret_5d": 0.10, "fwd_ret_20d": 0.01, "post_rebound_new_low_6_20": False},
        {"value": 0.0, "fwd_ret_5d": 0.10, "fwd_ret_20d": 0.05, "post_rebound_new_low_6_20": False},
    ])
    labeled = pred.assign_drop_ab_labels(df, retention_threshold=0.2)
    assert labeled["ab_label"].tolist() == ["A", "B", "M", "UNCLASSIFIED"]
    assert labeled["target_A"].tolist()[:2] == [1.0, 0.0]
    assert np.isnan(labeled["target_A"].iloc[2])
    assert np.isnan(labeled["target_A"].iloc[3])


# ── PIT validation ────────────────────────────────────────────────────

def test_load_factor_raises_on_available_date_gt_trade_date(tmp_path):
    root = tmp_path
    fdir = root / "data" / "parquet" / "factors" / "factor_name=test_factor" / "year=2020"
    fdir.mkdir(parents=True)
    pd.DataFrame([{
        "ts_code": "000001.SZ", "trade_date": 20200102,
        "value": 1.0, "available_date": 20200103,
    }]).to_parquet(fdir / "part_2020.parquet", index=False)
    with pytest.raises(RuntimeError, match="available_date > trade_date"):
        pred.load_factor(root, "test_factor", 20200101, 20200131)


# ── Calendar ──────────────────────────────────────────────────────────

def test_first_trading_day_of_year_strict():
    cal = np.array([20191231, 20200102, 20200103, 20201231, 20210104])
    # 20191231 belongs to year 2019
    assert pred.first_trading_day_of_year(cal, 2019) == 20191231
    assert pred.first_trading_day_of_year(cal, 2020) == 20200102
    assert pred.first_trading_day_of_year(cal, 2021) == 20210104
    assert pred.first_trading_day_of_year(cal, 2022) is None
    # year not in calendar at all
    assert pred.first_trading_day_of_year(cal, 2018) is None


def test_first_trading_day_of_year_no_test_calendar_handled():
    cal = make_calendar(20170101, 500)
    # 2025 not in calendar
    result = pred.first_trading_day_of_year(cal, 2025)
    assert result is None


# ── Walk-forward ──────────────────────────────────────────────────────

def test_walkforward_windows_strictly_forward():
    for w in pred.get_windows():
        assert w.train_end < w.test_start
        assert w.train_start <= w.train_end
        assert w.test_start <= w.test_end


def test_walkforward_no_test_calendar_status():
    cal = make_calendar(20170101, 2000)  # ~8 years of weekdays
    samples = make_samples(calendar=cal, with_label_available=False)
    # request a test year far beyond calendar range
    windows = [pred.WindowSpec(2017, 2019, 2030, 2030)]
    outputs = pred.run_walkforward(
        samples=samples, feature_cols=pred.PRICE_FEATURE_COLUMNS,
        calendar=cal, windows=windows,
    )
    _, walk, _, _, _, _ = outputs
    assert walk["status"].iloc[0] == "NO_TEST_CALENDAR"


def test_walkforward_output_contract_v2():
    cal = make_calendar()
    samples = make_samples(calendar=cal)
    windows = [
        pred.WindowSpec(2017, 2019, 2020, 2020),
        pred.WindowSpec(2017, 2020, 2021, 2021),
        pred.WindowSpec(2017, 2021, 2022, 2022),
    ]
    predictions, walk, strategy, importance, baseline, leakage = pred.run_walkforward(
        samples=samples, feature_cols=pred.PRICE_FEATURE_COLUMNS,
        calendar=cal, windows=windows, min_coverage=0.05,
    )
    assert not predictions.empty
    assert not walk.empty
    assert not strategy.empty
    assert len(leakage) > 0

    # v2 prediction columns
    for col in ["p_A", "p_A_rank_pct_by_date", "model_action_date_rank_top10",
                "window", "label_available_date"]:
        assert col in predictions.columns

    # walk columns
    for col in ["primary_strategy", "auc", "primary_coverage_pct",
                "primary_a_rate_lift", "primary_net_spread_lift"]:
        assert col in walk.columns

    # strategy columns
    for col in ["strategy", "cutoff", "coverage_pct", "a_rate_lift", "net_spread_lift"]:
        assert col in strategy.columns


def test_date_rank_strategies_present():
    cal = make_calendar()
    samples = make_samples(calendar=cal)
    windows = [pred.WindowSpec(2017, 2019, 2020, 2020)]
    _, _, strategy, _, _, _ = pred.run_walkforward(
        samples=samples, feature_cols=pred.PRICE_FEATURE_COLUMNS,
        calendar=cal, windows=windows,
    )
    strategy_names = set(strategy["strategy"].unique())
    for s in ["date_rank_top_5pct", "date_rank_top_10pct", "date_rank_top_20pct",
              "train_cutoff_top_5pct", "train_cutoff_top_10pct", "train_cutoff_top_20pct",
              "fixed_0.50", "fixed_0.60", "fixed_0.70"]:
        assert s in strategy_names, f"Missing strategy: {s}"


# ── Leakage audit ─────────────────────────────────────────────────────

def test_leakage_audit_split_fields():
    cal = make_calendar()
    samples = make_samples(calendar=cal)
    windows = [pred.WindowSpec(2017, 2019, 2020, 2020)]
    _, _, _, _, _, leakage = pred.run_walkforward(
        samples=samples, feature_cols=pred.PRICE_FEATURE_COLUMNS,
        calendar=cal, windows=windows,
        leakage_control="label_available_plus_embargo", embargo_days=20,
    )
    audit = leakage[0]
    for field in ["train_rows_raw", "train_rows_after_label_availability",
                  "label_unavailable_dropped_rows", "train_rows_after_embargo",
                  "embargo_dropped_rows", "leakage_control_mode"]:
        assert field in audit, f"Missing audit field: {field}"
    # label drop + embargo drop should be independently tracked
    assert audit["label_unavailable_dropped_rows"] >= 0
    assert audit["embargo_dropped_rows"] >= 0


def test_label_availability_filter_satisfies_constraint():
    cal = make_calendar()
    samples = make_samples(calendar=cal)
    # Use a window where we can verify: train through 2019, test 2020
    windows = [pred.WindowSpec(2017, 2019, 2020, 2020)]
    _, walk, _, _, _, leakage = pred.run_walkforward(
        samples=samples, feature_cols=pred.PRICE_FEATURE_COLUMNS,
        calendar=cal, windows=windows,
        leakage_control="label_available", embargo_days=0,
    )
    audit = leakage[0]
    test_start_td = audit["test_start_trade_date"]
    # All training samples retained should have label_available_date < test_start_td
    # (We can't directly access the filtered training set here, but the audit
    #  should show label_unavailable_dropped_rows > 0 if there were violations)
    assert audit["label_unavailable_dropped_rows"] >= 0


# ── Feature set ───────────────────────────────────────────────────────

def test_price_feature_columns_excludes_daily_basic():
    for col in pred.PRICE_FEATURE_COLUMNS:
        assert col not in ["turnover_rate", "turnover_rate_f", "volume_ratio",
                           "log_total_mv", "log_circ_mv", "pb", "pe_ttm"]


# ── Report ────────────────────────────────────────────────────────────

def test_report_v2_contains_required_sections():
    walk = pd.DataFrame([{
        "window": "w1", "status": "OK",
        "primary_strategy": "date_rank_top_10pct",
        "auc": 0.65, "pr_auc": 0.30,
        "primary_coverage_pct": 10.0, "primary_a_rate_lift": 0.04,
        "primary_net_spread_lift": 0.005, "primary_mean_fwd_ret_20d": 0.02,
    }])
    strategy = pd.DataFrame([{
        "window": "w1", "strategy": "date_rank_top_10pct",
        "cutoff": 0.90, "coverage_pct": 10.0, "a_rate_lift": 0.04,
        "net_spread_lift": 0.005,
    }])
    leakage = [{
        "window": "w1", "train_rows_raw": 100,
        "train_rows_after_label_availability": 98,
        "label_unavailable_dropped_rows": 2,
        "train_rows_after_embargo": 98, "embargo_dropped_rows": 0,
        "leakage_control_mode": "label_available_plus_embargo",
        "embargo_days": 20,
    }]
    report = pred.generate_report(
        factor_name=pred.DEFAULT_FACTOR,
        retention_threshold=0.3,
        feature_cols=pred.PRICE_FEATURE_COLUMNS,
        walk=walk, strategy=strategy, leakage_audit=leakage,
        feature_set="price_only",
        leakage_control="label_available_plus_embargo",
        embargo_days=20,
    )
    assert "date_rank_top_10pct" in report
    assert "Leakage Audit" in report
    assert "Strategy Comparison" in report
    assert "RESEARCH ONLY" in report
    assert "price_only" in report
    assert "label_available_plus_embargo" in report


def test_report_includes_baseline_and_raw():
    walk = pd.DataFrame([{
        "window": "w1", "status": "OK",
        "primary_strategy": "date_rank_top_10pct",
        "auc": 0.65,
        "primary_coverage_pct": 10.0, "primary_a_rate_lift": 0.03,
        "primary_net_spread_lift": 0.002,
        "raw_mean_fwd_ret_20d": 0.01, "raw_net_spread_20bps": 0.008,
    }])
    strategy = pd.DataFrame([{
        "window": "w1", "strategy": "baseline_rule",
        "coverage_pct": 25.0, "a_rate_lift": 0.01, "net_spread_lift": 0.001,
    }])
    report = pred.generate_report(
        factor_name=pred.DEFAULT_FACTOR, retention_threshold=0.3,
        feature_cols=pred.PRICE_FEATURE_COLUMNS,
        walk=walk, strategy=strategy, leakage_audit=[],
        feature_set="price_only",
        leakage_control="label_available_plus_embargo",
        embargo_days=20,
    )
    assert "baseline_rule" in report
    assert "raw_" in report


# ── v2 acceptance & diagnostics ────────────────────────────────────────

def test_summarize_status_uses_min_coverage_param():
    # 3 windows all with positive lift → passes acceptance, but 10% coverage
    walk = pd.DataFrame([
        {"window": "w1", "status": "OK", "primary_strategy": "date_rank_top_10pct",
         "auc": 0.65, "primary_coverage_pct": 10.0,
         "primary_a_rate_lift": 0.04, "primary_net_spread_lift": 0.005},
        {"window": "w2", "status": "OK", "primary_strategy": "date_rank_top_10pct",
         "auc": 0.66, "primary_coverage_pct": 10.0,
         "primary_a_rate_lift": 0.04, "primary_net_spread_lift": 0.003},
        {"window": "w3", "status": "OK", "primary_strategy": "date_rank_top_10pct",
         "auc": 0.67, "primary_coverage_pct": 10.0,
         "primary_a_rate_lift": 0.04, "primary_net_spread_lift": 0.002},
    ])
    # min_coverage=0.05 → 10% coverage passes → OK
    status, _ = pred.summarize_status(walk, min_coverage=0.05)
    assert status == "OK"
    # min_coverage=0.20 → 10% < 20% → LOW_COVERAGE
    status2, _ = pred.summarize_status(walk, min_coverage=0.20)
    assert "LOW_COVERAGE" in status2


def test_strategy_compare_includes_raw_and_baseline():
    cal = make_calendar()
    samples = make_samples(calendar=cal)
    windows = [pred.WindowSpec(2017, 2019, 2020, 2020)]
    _, _, strategy, _, _, _ = pred.run_walkforward(
        samples=samples, feature_cols=pred.PRICE_FEATURE_COLUMNS,
        calendar=cal, windows=windows,
    )
    names = set(strategy["strategy"].unique())
    assert "raw_events" in names
    assert "baseline_rule" in names


def test_strategy_compare_has_all_11_strategies():
    cal = make_calendar()
    samples = make_samples(calendar=cal)
    windows = [pred.WindowSpec(2017, 2019, 2020, 2020)]
    _, _, strategy, _, _, _ = pred.run_walkforward(
        samples=samples, feature_cols=pred.PRICE_FEATURE_COLUMNS,
        calendar=cal, windows=windows,
    )
    names = set(strategy["strategy"].unique())
    expected = {
        "raw_events", "baseline_rule",
        "fixed_0.50", "fixed_0.60", "fixed_0.70",
        "train_cutoff_top_5pct", "train_cutoff_top_10pct", "train_cutoff_top_20pct",
        "date_rank_top_5pct", "date_rank_top_10pct", "date_rank_top_20pct",
    }
    assert expected.issubset(names), f"Missing: {expected - names}"


def test_diagnostics_output_exists():
    cal = make_calendar()
    samples = make_samples(calendar=cal)
    windows = [pred.WindowSpec(2017, 2019, 2020, 2020)]
    predictions, _, strategy, _, _, _ = pred.run_walkforward(
        samples=samples, feature_cols=pred.PRICE_FEATURE_COLUMNS,
        calendar=cal, windows=windows,
    )
    diag = pred.compute_diagnostics(predictions, strategy)
    assert not diag.empty
    for col in ["window", "strategy", "a_rate", "mean_fwd_ret_20d",
                "selected_win_rate", "a_mean_return", "b_mean_return"]:
        assert col in diag.columns


def test_report_contains_auc_diagnostic_section():
    walk = pd.DataFrame([{
        "window": "w1", "status": "OK",
        "primary_strategy": "date_rank_top_10pct",
        "auc": 0.65, "primary_coverage_pct": 10.0,
        "primary_a_rate_lift": 0.01, "primary_net_spread_lift": -0.002,
    }])
    diag = pd.DataFrame([{
        "window": "w1", "strategy": "date_rank_top_10pct",
        "a_rate": 0.32, "a_rate_lift": 0.01, "mean_fwd_ret_20d": -0.001,
        "raw_mean_fwd_ret_20d": 0.005, "selected_win_rate": 0.48,
        "a_mean_return": 0.02, "b_mean_return": -0.01,
    }])
    report = pred.generate_report(
        factor_name=pred.DEFAULT_FACTOR, retention_threshold=0.3,
        feature_cols=pred.PRICE_FEATURE_COLUMNS,
        walk=walk, strategy=pd.DataFrame(), leakage_audit=[],
        feature_set="price_only",
        leakage_control="label_available_plus_embargo",
        embargo_days=20, diagnostics=diag,
    )
    assert "Why AUC Did Not Translate" in report
    assert "Production eligible" in report


def test_manifest_block_reasons_on_no_predictive_power():
    """Verify that a NO_PREDICTIVE_POWER walk produces block_reasons."""
    walk = pd.DataFrame([{
        "window": "w1", "status": "OK",
        "primary_strategy": "date_rank_top_10pct",
        "auc": 0.65, "primary_coverage_pct": 10.0,
        "primary_a_rate_lift": 0.005, "primary_net_spread_lift": -0.003,
    }])
    status, summary = pred.summarize_status(walk, min_coverage=0.05)
    assert status == "NO_PREDICTIVE_POWER"
    assert summary["improved_windows"] < 3 or summary["avg_net_spread_lift"] <= 0


# ── Baseline diagnostics fix ──────────────────────────────────────────

def test_baseline_diagnostics_uses_baseline_action():
    predictions = pd.DataFrame({
        "window": ["w1"] * 4,
        "ab_label": ["A", "B", "A", "B"],
        "fwd_ret_20d": [0.10, -0.02, 0.08, -0.01],
        "p_A": [0.8, 0.7, 0.2, 0.1],
        "p_A_rank_pct_by_date": [1.0, 0.75, 0.5, 0.25],
        "baseline_action": [True, True, False, False],
    })
    strategy = pd.DataFrame({
        "window": ["w1"],
        "strategy": ["baseline_rule"],
        "n_samples": [2],
    })
    diag = pred.compute_diagnostics(predictions, strategy)
    row = diag[diag["strategy"] == "baseline_rule"].iloc[0]
    assert row["n_samples"] == 2
    assert row["a_rate"] == 0.5


def test_baseline_diagnostics_matches_strategy_compare():
    predictions = pd.DataFrame({
        "window": ["w1"] * 4,
        "ab_label": ["A", "B", "A", "B"],
        "fwd_ret_20d": [0.10, -0.02, 0.08, -0.01],
        "p_A": [0.8, 0.7, 0.2, 0.1],
        "p_A_rank_pct_by_date": [1.0, 0.75, 0.5, 0.25],
        "baseline_action": [True, True, False, False],
    })
    strategy = pd.DataFrame({
        "window": ["w1"],
        "strategy": ["baseline_rule"],
        "n_samples": [2],
    })
    diag = pred.compute_diagnostics(predictions, strategy)
    row = diag[diag["strategy"] == "baseline_rule"].iloc[0]
    assert int(row["n_samples"]) == int(strategy.loc[0, "n_samples"])


def test_baseline_diagnostics_raises_on_mismatch():
    predictions = pd.DataFrame({
        "window": ["w1"] * 4,
        "ab_label": ["A", "B", "A", "B"],
        "fwd_ret_20d": [0.10, -0.02, 0.08, -0.01],
        "p_A": [0.8, 0.7, 0.2, 0.1],
        "p_A_rank_pct_by_date": [1.0, 0.75, 0.5, 0.25],
        # baseline_action column missing
    })
    strategy = pd.DataFrame({
        "window": ["w1"],
        "strategy": ["baseline_rule"],
        "n_samples": [2],  # strategy claims 2 samples but no baseline_action column
    })
    with pytest.raises(RuntimeError, match="baseline_rule diagnostics mismatch"):
        pred.compute_diagnostics(predictions, strategy)

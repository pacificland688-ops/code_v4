"""Tests for the independent photoresist panic threshold validator."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from validate_photoresist_panic_thresholds import (  # noqa: E402
    _event_exclusion_dates,
    build_threshold_gate,
    cluster_threshold_events,
    compute_market_regime,
    evaluate_threshold_acceptance,
    generate_report,
    run_bootstrap_tests,
    run_placebo_tests,
)


def _dates(start: str, periods: int) -> np.ndarray:
    return np.array([
        int(date.strftime("%Y%m%d"))
        for date in pd.date_range(start, periods=periods, freq="B")
    ])


def _gate_config(**overrides) -> dict:
    config = {
        "return_window_days": 5,
        "absolute_threshold_pct": -5.0,
        "quantile_window_days": 60,
        "quantile_threshold_pct": 10.0,
        "breadth_window_days": 5,
        "breadth_threshold_pct": 50.0,
    }
    config.update(overrides)
    return config


def test_rolling_quantile_excludes_current_day():
    dates = _dates("2020-01-02", 61)
    basket = pd.DataFrame({
        "trade_date": dates,
        "basket_ret_5d": [-0.01] * 60 + [-0.50],
        "basket_ret_1d": [0.0] * 61,
        "down_stock_ratio": [1.0] * 61,
        "median_amount_ratio_20d": [1.0] * 61,
    })
    gated = build_threshold_gate(basket, "primary_5d", _gate_config())
    assert gated.iloc[-1]["validation_quantile"] == -0.01


def test_all_configured_gates_can_be_built_without_best_gate_selection():
    dates = _dates("2020-01-02", 80)
    basket = pd.DataFrame({
        "trade_date": dates,
        "basket_ret_1d": [-0.01] * 80,
        "down_stock_ratio": [0.8] * 80,
        "median_amount_ratio_20d": [1.0] * 80,
    })
    gates = {
        "relaxed_5d": _gate_config(absolute_threshold_pct=-3.0),
        "primary_5d": _gate_config(),
        "strict_10d": _gate_config(
            return_window_days=10, absolute_threshold_pct=-10.0
        ),
    }
    outputs = {name: build_threshold_gate(basket, name, config) for name, config in gates.items()}
    assert set(outputs) == set(gates)
    assert {frame["gate_id"].iloc[0] for frame in outputs.values()} == set(gates)


def test_event_clustering_uses_trading_day_positions():
    calendar = _dates("2024-01-02", 12)
    triggered_dates = [calendar[0], calendar[2], calendar[8]]
    gated = pd.DataFrame({
        "trade_date": triggered_dates,
        "validation_gate_triggered": [True, True, True],
        "gate_id": ["primary_5d"] * 3,
        "validation_return": [-0.06, -0.07, -0.08],
        "validation_quantile": [-0.04] * 3,
        "validation_breadth": [0.8] * 3,
        "median_amount_ratio_20d": [1.2] * 3,
    })
    events = cluster_threshold_events(gated, calendar, max_gap=3)
    assert len(events) == 2
    assert events.iloc[0]["n_triggered_days"] == 2
    assert events.iloc[0]["event_date"] == calendar[2]


def test_market_regime_does_not_change_when_future_prices_change():
    dates = _dates("2020-01-02", 140)
    close = np.linspace(100.0, 150.0, len(dates))
    index_prices = pd.DataFrame({
        "ts_code": "000300.SH", "trade_date": dates, "close": close,
    })
    config = {"primary_index": "000300.SH", "ma_window_days": 60, "return_window_days": 20}
    baseline = compute_market_regime(index_prices, config)
    changed = index_prices.copy()
    changed.loc[changed.index[-10:], "close"] = 1.0
    mutated = compute_market_regime(changed, config)
    cutoff = dates[-11]
    left = baseline[baseline["trade_date"] <= cutoff].reset_index(drop=True)
    right = mutated[mutated["trade_date"] <= cutoff].reset_index(drop=True)
    pd.testing.assert_frame_equal(left, right)


def test_placebo_excludes_event_buffer_and_matches_year_and_regime():
    calendar = _dates("2024-01-02", 80)
    real_dates = [calendar[20], calendar[50]]
    real = pd.DataFrame({
        "event_date": real_dates,
        "market_regime": ["bull", "bear"],
        "basket_fwd_ret_5d": [0.05, 0.04],
        "basket_fwd_ret_10d": [0.06, 0.05],
        "basket_fwd_ret_20d": [0.08, 0.07],
    })
    excluded = _event_exclusion_dates(real, calendar, buffer_days=5)
    assert all(date in excluded for date in real_dates)
    candidate_dates = [calendar[5], real_dates[0], calendar[70]]
    candidates = pd.DataFrame({
        "event_date": candidate_dates,
        "market_regime": ["bull", "bull", "bear"],
        "basket_fwd_ret_5d": [0.0, 9.0, 0.0],
        "basket_fwd_ret_10d": [0.0, 9.0, 0.0],
        "basket_fwd_ret_20d": [0.0, 9.0, 0.0],
    })
    result = run_placebo_tests(
        "primary_5d", real, candidates, calendar,
        {"n_runs": 50, "match_by_year": True, "match_by_market_regime": True},
        random_seed=7,
    )
    assert set(result["n_matched_events"]) == {2}
    assert set(result["match_coverage"]) == {1.0}
    assert (result["placebo_mean_return"] == 0.0).all()


def test_bootstrap_returns_reproducible_confidence_interval():
    forward = pd.DataFrame({
        "basket_fwd_ret_5d": [0.02, 0.03, 0.04],
        "basket_fwd_ret_10d": [0.03, 0.04, 0.05],
        "basket_fwd_ret_20d": [0.04, 0.05, 0.06],
    })
    first = run_bootstrap_tests(
        "primary_5d", forward, {"n_runs": 200, "confidence_level": 0.90}, 11, 20
    )
    second = run_bootstrap_tests(
        "primary_5d", forward, {"n_runs": 200, "confidence_level": 0.90}, 11, 20
    )
    pd.testing.assert_frame_equal(first, second)
    row_20 = first[first["horizon_days"] == 20].iloc[0]
    assert row_20["ci_low"] > 0
    assert not bool(row_20["ci_contains_zero"])


def test_acceptance_rejects_significance_and_match_coverage_failures():
    gate_summary = pd.DataFrame([{
        "gate_id": "primary_5d", "n_event_clusters": 10,
        "mean_net_ret_20d": 0.05, "win_rate_20d": 0.7,
    }])
    market = pd.DataFrame([
        {"gate_id": "primary_5d", "market_regime": "bull", "mean_net_ret_20d": 0.05},
        {"gate_id": "primary_5d", "market_regime": "bear", "mean_net_ret_20d": 0.01},
    ])
    placebo = pd.DataFrame([{
        "gate_id": "primary_5d", "horizon_days": 20,
        "permutation_p_value": 0.20, "match_coverage": 0.50,
    }])
    bootstrap = pd.DataFrame([{
        "gate_id": "primary_5d", "horizon_days": 20, "ci_low": 0.01,
    }])
    config = {
        "primary_gate_id": "primary_5d",
        "acceptance": {
            "min_event_clusters": 5, "min_win_rate_20d": 0.5,
            "max_placebo_p_value": 0.10, "min_placebo_match_coverage": 0.80,
            "require_bootstrap_ci_low_positive": True, "min_non_negative_regimes": 2,
        },
    }
    result = evaluate_threshold_acceptance(
        gate_summary, market, placebo, bootstrap, pd.DataFrame(),
        {"top1_GO": True}, config,
    )
    assert result["event_GO"] is False
    assert result["trade_GO"] is False
    assert "placebo_significance_failure" in result["reasons"]


def test_report_contains_all_gates_and_acceptance_result():
    gates = pd.DataFrame([
        {"gate_id": "relaxed_5d", "n_event_clusters": 10},
        {"gate_id": "primary_5d", "n_event_clusters": 8},
        {"gate_id": "strict_5d", "n_event_clusters": 5},
    ])
    acceptance = {
        "event_GO": False, "top1_GO": False, "trade_GO": False,
        "classification": "both_invalid", "reasons": ["test_failure"],
    }
    report = generate_report(
        gates, pd.DataFrame(), pd.DataFrame(), pd.DataFrame(),
        pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(),
        pd.DataFrame(), pd.DataFrame(), acceptance,
    )
    assert "relaxed_5d" in report
    assert "primary_5d" in report
    assert "strict_5d" in report
    assert "both_invalid" in report

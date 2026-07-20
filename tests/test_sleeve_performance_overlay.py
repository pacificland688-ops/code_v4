"""
Tests for PIT-safe sleeve performance overlay.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pandas as pd

from alpha.sleeve_performance_overlay import SleevePerformanceOverlay


def _make_dates(n: int = 40) -> list[int]:
    return [int(d.strftime("%Y%m%d")) for d in pd.bdate_range("2024-01-02", periods=n)]


def _make_scores_and_returns(
    dates: list[int],
    n_stocks: int = 60,
    seed: int = 7,
) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    rng = np.random.default_rng(seed)
    stocks = [f"{i:06d}.SZ" for i in range(n_stocks)]
    base_rank = np.linspace(-1.0, 1.0, n_stocks)

    fwd_rows = []
    value_rows = []
    reversal_rows = []
    for d in dates:
        noise = rng.normal(0.0, 0.025, n_stocks)
        fwd = 0.05 * base_rank + noise
        for stock, rank_score, ret in zip(stocks, base_rank, fwd):
            fwd_rows.append({
                "ts_code": stock,
                "trade_date": d,
                "fwd_ret_1d": float(ret),
            })
            value_rows.append({
                "ts_code": stock,
                "trade_date": d,
                "composite_score": float(rank_score),
            })
            reversal_rows.append({
                "ts_code": stock,
                "trade_date": d,
                "composite_score": float(-rank_score),
            })

    return (
        {
            "value": pd.DataFrame(value_rows),
            "reversal": pd.DataFrame(reversal_rows),
        },
        pd.DataFrame(fwd_rows),
    )


def _overlay_config(**overrides) -> dict:
    cfg = {
        "enabled": True,
        "lookback_months": 12,
        "horizon": 1,
        "min_obs": 5,
        "min_stocks": 30,
        "icir_weight": 0.70,
        "hit_rate_weight": 0.30,
        "icir_scale": 0.50,
        "strength": 0.50,
        "multiplier_min": 0.60,
        "multiplier_max": 1.60,
    }
    cfg.update(overrides)
    return cfg


def test_positive_sleeve_is_amplified_and_negative_sleeve_is_compressed():
    dates = _make_dates()
    sleeve_scores, fwd_returns = _make_scores_and_returns(dates)

    overlay = SleevePerformanceOverlay(_overlay_config())
    multipliers, metrics = overlay.compute_multipliers(
        sleeve_scores,
        fwd_returns,
        signal_dates=dates,
        trade_dates=dates,
    )

    assert not multipliers.empty
    late = multipliers[multipliers["trade_date"] == dates[-1]].iloc[0]
    assert late["value_multiplier"] > 1.10
    assert late["reversal_multiplier"] < 0.90

    late_metrics = metrics[metrics["trade_date"] == dates[-1]]
    value_metric = late_metrics[late_metrics["sleeve"] == "value"].iloc[0]
    reversal_metric = late_metrics[late_metrics["sleeve"] == "reversal"].iloc[0]
    assert value_metric["icir"] > 0
    assert reversal_metric["icir"] < 0


def test_insufficient_history_uses_neutral_multiplier():
    dates = _make_dates(8)
    sleeve_scores, fwd_returns = _make_scores_and_returns(dates)

    overlay = SleevePerformanceOverlay(_overlay_config(min_obs=20))
    multipliers, metrics = overlay.compute_multipliers(
        sleeve_scores,
        fwd_returns,
        signal_dates=[dates[-1]],
        trade_dates=dates,
    )

    row = multipliers.iloc[0]
    assert row["value_multiplier"] == 1.0
    assert row["reversal_multiplier"] == 1.0
    assert set(metrics["status"]) == {"insufficient_history"}


def test_future_forward_returns_do_not_affect_current_multiplier():
    dates = _make_dates()
    sleeve_scores, fwd_returns = _make_scores_and_returns(dates)
    signal_date = dates[25]

    overlay = SleevePerformanceOverlay(_overlay_config())
    base, _ = overlay.compute_multipliers(
        sleeve_scores,
        fwd_returns,
        signal_dates=[signal_date],
        trade_dates=dates,
    )

    perturbed = fwd_returns.copy()
    perturbed.loc[perturbed["trade_date"] > signal_date, "fwd_ret_1d"] *= -100.0
    changed, _ = overlay.compute_multipliers(
        sleeve_scores,
        perturbed,
        signal_dates=[signal_date],
        trade_dates=dates,
    )

    pd.testing.assert_frame_equal(base, changed)


def test_disabled_overlay_returns_empty_frames():
    dates = _make_dates()
    sleeve_scores, fwd_returns = _make_scores_and_returns(dates)

    overlay = SleevePerformanceOverlay(_overlay_config(enabled=False))
    multipliers, metrics = overlay.compute_multipliers(
        sleeve_scores,
        fwd_returns,
        signal_dates=dates,
        trade_dates=dates,
    )

    assert multipliers.empty
    assert metrics.empty

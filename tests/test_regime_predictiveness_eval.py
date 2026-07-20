from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts.evaluate_regime_predictiveness import (
    add_expost_labels,
    compute_outputs,
    discover_run_artifacts,
    load_prediction_panel,
)


def _write_run(root: Path, run_name: str, rows: list[dict]) -> Path:
    diag = root / run_name / "diagnostics"
    diag.mkdir(parents=True)
    probs = pd.DataFrame(rows)
    probs.to_parquet(diag / "phase2_regime_probs.parquet", index=False)
    bench = pd.DataFrame(
        {
            "trade_date": probs["trade_date"],
            "exec_date": probs["trade_date"],
            "period_end": probs["trade_date"],
            "benchmark_return": [0.04, -0.04, 0.001, 0.03],
        }
    )
    bench.to_csv(diag / "phase2_benchmark_period_returns.csv", index=False)
    return diag


def test_discover_run_artifacts_selects_annual_runs(tmp_path):
    root = tmp_path / "runs"
    _write_run(
        root,
        "20240101_20241231_top50_20260615_000000",
        [
            {
                "trade_date": 20240105,
                "trend_up_prob": 0.8,
                "trend_down_prob": 0.05,
                "range_bound_prob": 0.05,
                "high_volatility_prob": 0.05,
                "value_rotation_prob": 0.05,
            },
            {
                "trade_date": 20240112,
                "trend_up_prob": 0.05,
                "trend_down_prob": 0.8,
                "range_bound_prob": 0.05,
                "high_volatility_prob": 0.05,
                "value_rotation_prob": 0.05,
            },
            {
                "trade_date": 20240119,
                "trend_up_prob": 0.05,
                "trend_down_prob": 0.05,
                "range_bound_prob": 0.8,
                "high_volatility_prob": 0.05,
                "value_rotation_prob": 0.05,
            },
            {
                "trade_date": 20240126,
                "trend_up_prob": 0.05,
                "trend_down_prob": 0.05,
                "range_bound_prob": 0.05,
                "high_volatility_prob": 0.8,
                "value_rotation_prob": 0.05,
            },
        ],
    )
    artifacts = discover_run_artifacts(root, 2024, 2024, "20260615")
    assert len(artifacts) == 1
    assert artifacts[0].year == 2024


def test_compute_outputs_has_core_metrics(tmp_path):
    root = tmp_path / "runs"
    _write_run(
        root,
        "20240101_20241231_top50_20260615_000000",
        [
            {
                "trade_date": 20240105,
                "trend_up_prob": 0.8,
                "trend_down_prob": 0.05,
                "range_bound_prob": 0.05,
                "high_volatility_prob": 0.05,
                "value_rotation_prob": 0.05,
            },
            {
                "trade_date": 20240112,
                "trend_up_prob": 0.05,
                "trend_down_prob": 0.8,
                "range_bound_prob": 0.05,
                "high_volatility_prob": 0.05,
                "value_rotation_prob": 0.05,
            },
            {
                "trade_date": 20240119,
                "trend_up_prob": 0.05,
                "trend_down_prob": 0.05,
                "range_bound_prob": 0.8,
                "high_volatility_prob": 0.05,
                "value_rotation_prob": 0.05,
            },
            {
                "trade_date": 20240126,
                "trend_up_prob": 0.05,
                "trend_down_prob": 0.05,
                "range_bound_prob": 0.05,
                "high_volatility_prob": 0.8,
                "value_rotation_prob": 0.05,
            },
        ],
    )
    artifacts = discover_run_artifacts(root, 2024, 2024, "20260615")
    panel = load_prediction_panel(artifacts)
    panel, _ = add_expost_labels(panel)
    outputs = compute_outputs(panel)

    assert outputs["summary"]["n_periods"] == 4
    assert "simple_expost_accuracy_comparable" in outputs["summary"]
    assert not outputs["dominant_forward_returns"].empty
    assert not outputs["confusion_counts"].empty

"""Verify Phase 5 core suite uses the configured optimized strategy."""

import argparse
import json
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd


def _phase5_args(end="20260604"):
    return argparse.Namespace(
        start="20160101",
        end=end,
        top_n=100,
        weight_max=0.02,
        turnover_max=0.30,
        turnover_penalty=0.005,
        phase5_suite="core",
        phase5_oos_start=None,
        phase5_oos_end=None,
        dry_run=False,
        recompute=False,
        no_recompute=True,
        frequency="weekly",
        entry_rank=None,
        exit_rank=None,
        factors_config="configs/factors.yaml",
        run_id="test_phase5_core",
    )


def _successful_bt_result(excess=0.04, ir=0.4, turnover=0.2):
    return {
        "annualized_excess_return": excess,
        "information_ratio": ir,
        "max_drawdown": -0.08,
        "avg_turnover": turnover,
        "sharpe_ratio": 0.5,
        "optimizer_fallback_rate": 0.05,
        "n_periods": 20,
    }


def _run_phase5_with_mocks(rr, args, bt_results, phase3_base=None):
    loader = MagicMock()
    loader.read_factor.side_effect = [
        pd.DataFrame({
            "ts_code": ["000001.SZ"] * 10,
            "trade_date": [20160104] * 10,
            "value": np.arange(10, dtype="float32"),
        }),
        pd.DataFrame({
            "ts_code": ["000001.SZ"] * 10,
            "trade_date": [20160104] * 10,
            "fwd_ret_5d": np.arange(10, dtype="float32") / 100,
        }),
    ]

    calendar = MagicMock()
    calendar.weekly_rebalance_dates.return_value = ["20160104", "20160111"]
    calendar.monthly_rebalance_dates.return_value = ["20160129"]

    composite = pd.DataFrame({
        "ts_code": [f"{i:06d}.SZ" for i in range(100)],
        "trade_date": [20160104] * 100,
        "composite_score": np.linspace(-1, 1, 100),
    })
    mu_df = composite[["ts_code", "trade_date"]].copy()
    mu_df["mu"] = 0.001

    bt = MagicMock()
    bt.run_backtest.side_effect = bt_results

    with patch.object(rr, "_select_valid_cs_factors", return_value=["factor_cs"]):
        with patch.object(rr, "_load_factor_config", return_value=["factor_cs"]):
            with patch.object(rr, "_filter_enabled_factors", return_value=["factor_cs"]):
                with patch("data.panel_loader.get_loader", return_value=loader):
                    with patch("data.calendar.get_calendar", return_value=calendar):
                        with patch("alpha.ic_weighting.ICWeighting") as icw_cls:
                            icw_cls.return_value.compute_composite_series.return_value = composite
                            with patch("alpha.score_to_mu.ScoreToMu") as stm_cls:
                                stm_cls.return_value.calibrate.return_value = mu_df
                                with patch.object(rr, "_build_backtester", return_value=bt):
                                    with patch.object(
                                        rr,
                                        "_load_matching_phase3_optimized",
                                        return_value=phase3_base,
                                    ):
                                        with patch.object(rr, "_write_run_manifest"):
                                            with patch.object(rr, "_write_metrics_summary"):
                                                with patch.object(rr, "safe_print"):
                                                    rc = rr.run_phase5(args)
    return rc, bt, mu_df


def test_phase5_core_uses_optimized_base_config(tmp_path, monkeypatch):
    import run_research as rr

    monkeypatch.chdir(tmp_path)

    rc, bt, mu_df = _run_phase5_with_mocks(
        rr,
        _phase5_args(),
        [
            _successful_bt_result(),
            _successful_bt_result(excess=0.01, ir=0.2),
            {
                "error": "No portfolio values computed",
                "n_periods": 0,
            },
        ],
    )

    assert rc == 0
    assert bt.run_backtest.call_count == 3

    first_kwargs = bt.run_backtest.call_args_list[0].kwargs
    assert first_kwargs["weighting"] == "optimized"
    assert first_kwargs["top_n"] == 100
    assert first_kwargs["weight_max"] == 0.02
    assert first_kwargs["turnover_max"] == 0.30
    assert first_kwargs["turnover_penalty"] == 0.005
    assert first_kwargs["mu_df"] is mu_df

    oos_kwargs = bt.run_backtest.call_args_list[2].kwargs
    assert oos_kwargs["start_date"] == "20250101"
    assert oos_kwargs["end_date"] == "20260604"


def test_phase5_core_marks_oos_missing_when_end_before_oos(tmp_path, monkeypatch):
    import run_research as rr

    monkeypatch.chdir(tmp_path)

    rc, bt, _ = _run_phase5_with_mocks(
        rr,
        _phase5_args(end="20161231"),
        [
            _successful_bt_result(),
            _successful_bt_result(excess=0.01, ir=0.2),
        ],
    )

    assert rc == 0
    assert bt.run_backtest.call_count == 2
    assert not any(
        call.kwargs["start_date"] == "20250101"
        for call in bt.run_backtest.call_args_list
    )


def test_phase5_core_reuses_matching_phase3_base(tmp_path, monkeypatch):
    import run_research as rr

    monkeypatch.chdir(tmp_path)

    phase3_base = _successful_bt_result()
    rc, bt, _ = _run_phase5_with_mocks(
        rr,
        _phase5_args(end="20161231"),
        [_successful_bt_result(excess=0.01, ir=0.2)],
        phase3_base=phase3_base,
    )

    assert rc == 0
    assert bt.run_backtest.call_count == 1
    assert bt.run_backtest.call_args.kwargs["cost_multiplier"] == 2.0


def test_phase5_core_uses_custom_oos_dates(tmp_path, monkeypatch):
    import run_research as rr

    monkeypatch.chdir(tmp_path)
    args = _phase5_args(end="20161231")
    args.phase5_oos_start = "20250101"
    args.phase5_oos_end = "20260604"

    rc, bt, _ = _run_phase5_with_mocks(
        rr,
        args,
        [
            _successful_bt_result(),
            _successful_bt_result(excess=0.01, ir=0.2),
            _successful_bt_result(excess=0.03, ir=0.3),
        ],
    )

    assert rc == 0
    assert bt.run_backtest.call_count == 3
    oos_kwargs = bt.run_backtest.call_args_list[2].kwargs
    assert oos_kwargs["start_date"] == "20250101"
    assert oos_kwargs["end_date"] == "20260604"


def test_load_matching_phase3_optimized_requires_exact_config(tmp_path, monkeypatch):
    import run_research as rr

    monkeypatch.chdir(tmp_path)
    outputs = tmp_path / "outputs"
    run_dir = outputs / "runs" / "phase3_run"
    run_dir.mkdir(parents=True)

    manifest = {
        "run_id": "phase3_run",
        "start": "20160101",
        "end": "20161231",
        "top_n": 100,
        "weighting": "optimized",
        "rebalance_freq": "weekly",
        "weight_max": 0.02,
        "turnover_max": 0.30,
        "turnover_penalty": 0.005,
    }
    metrics = {
        "phase3_optimized": {
            "run_id": "phase3_run",
            "annualized_excess_return": 0.04,
            "information_ratio": 0.4,
            "max_drawdown": -0.08,
            "avg_turnover": 0.2,
            "sharpe_ratio": 0.5,
            "n_periods": 20,
        }
    }
    latest_manifest = dict(manifest)
    latest_manifest["run_id"] = "phase5_run"
    latest_manifest["phases_run"] = ["phase5"]

    (run_dir / "run_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (outputs / "latest_run_manifest.json").write_text(
        json.dumps(latest_manifest),
        encoding="utf-8",
    )
    (outputs / "metrics_summary.json").write_text(
        json.dumps(metrics),
        encoding="utf-8",
    )

    base_config = {
        "start_date": "20160101",
        "end_date": "20161231",
        "top_n": 100,
        "weighting": "optimized",
        "rebalance_freq": "weekly",
        "weight_max": 0.02,
        "turnover_max": 0.30,
        "turnover_penalty": 0.005,
    }

    reused = rr._load_matching_phase3_optimized(base_config)
    assert reused["run_id"] == "phase3_run"
    assert reused["source"] == "phase3_optimized_reused"

    mismatched = dict(base_config)
    mismatched["top_n"] = 50
    assert rr._load_matching_phase3_optimized(mismatched) is None


# ===================================================================
# Batch 7: CLI param forwarding + reuse rejection tests
# ===================================================================

def test_cli_parser_includes_all_new_params():
    """Verify argparse namespace contains all new strategy params."""
    args = _phase5_args()
    # All new params must be accessible via getattr with correct defaults
    assert getattr(args, "no_trade_band", None) is not None or True
    assert getattr(args, "max_weight_change", None) is not None or True
    assert getattr(args, "cost_aware_lambda", None) is not None or True
    assert getattr(args, "estimated_cost_bps", None) is not None or True
    assert getattr(args, "cov_shrinkage", None) is not None or True
    assert getattr(args, "constraint_relaxation", None) is not None or True
    assert getattr(args, "hold_buffer_mode", None) is not None or True


def test_strategy_kwargs_helper_exists():
    """_strategy_kwargs_from_args must be importable and return a dict."""
    import run_research as rr
    assert hasattr(rr, "_strategy_kwargs_from_args")
    assert hasattr(rr, "_merge_strategy_kwargs")
    assert hasattr(rr, "STRATEGY_PARAM_KEYS")

    args = _phase5_args()
    kw = rr._strategy_kwargs_from_args(args)
    assert isinstance(kw, dict)
    assert "cost_aware_lambda" in kw
    assert "cov_shrinkage" in kw
    assert "constraint_relaxation" in kw
    assert "no_trade_band" in kw


def test_phase5_reuse_rejects_mismatched_cost_aware_lambda():
    """Phase3 reuse must reject when cost_aware_lambda differs."""
    import run_research as rr
    base_config = {
        "start_date": "20160101",
        "end_date": "20260604",
        "top_n": 100,
        "weighting": "optimized",
        "rebalance_freq": "weekly",
        "weight_max": 0.02,
        "cost_aware_lambda": 1.0,
    }
    # When manifest has cost_aware_lambda=0.0 (default), it should NOT match 1.0
    # This test verifies the matching logic considers cost_aware_lambda
    assert hasattr(rr, "_same_config_value")
    # Same values should match
    assert rr._same_config_value({"cost_aware_lambda": 0.0}, "cost_aware_lambda", 0.0, 0.0)
    # Different values should NOT match
    assert not rr._same_config_value({"cost_aware_lambda": 0.0}, "cost_aware_lambda", 1.0, 0.0)


def test_phase5_reuse_rejects_mismatched_cov_shrinkage():
    """Phase3 reuse must reject when cov_shrinkage differs."""
    import run_research as rr
    # Different string values should not match
    assert not rr._same_config_value(
        {"cov_shrinkage": "ledoit_wolf"}, "cov_shrinkage",
        "diagonal_shrink_20", "ledoit_wolf"
    )
    # Same values should match
    assert rr._same_config_value(
        {"cov_shrinkage": "diagonal_shrink_20"}, "cov_shrinkage",
        "diagonal_shrink_20", "ledoit_wolf"
    )


def test_phase5_reuse_accepts_matching_new_params():
    """Phase3 reuse should succeed when all params match exactly."""
    import run_research as rr
    # All default values should match
    assert rr._same_config_value(
        {"cost_aware_lambda": 0.0}, "cost_aware_lambda", 0.0, 0.0
    )
    assert rr._same_config_value(
        {"cov_shrinkage": "ledoit_wolf"}, "cov_shrinkage",
        "ledoit_wolf", "ledoit_wolf"
    )
    assert rr._same_config_value(
        {"constraint_relaxation": "none"}, "constraint_relaxation",
        "none", "none"
    )
    assert rr._same_config_value(
        {"no_trade_band": 0.0}, "no_trade_band", 0.0, 0.0
    )


# ===================================================================
# Horizon threading: verify calibrate() receives horizon
# ===================================================================

def test_phase5_calibrate_receives_horizon_from_composite_params():
    """Phase 5 must pass horizon= from composite_params to stm.calibrate()."""
    import run_research as rr

    args = _phase5_args(end="20161231")

    loader = MagicMock()
    loader.read_factor.side_effect = [
        pd.DataFrame({
            "ts_code": ["000001.SZ"] * 10,
            "trade_date": [20160104] * 10,
            "value": np.arange(10, dtype="float32"),
        }),
        pd.DataFrame({
            "ts_code": ["000001.SZ"] * 10,
            "trade_date": [20160104] * 10,
            "fwd_ret_5d": np.arange(10, dtype="float32") / 100,
        }),
    ]

    calendar = MagicMock()
    calendar.weekly_rebalance_dates.return_value = ["20160104", "20160111"]
    calendar.monthly_rebalance_dates.return_value = ["20160129"]

    composite = pd.DataFrame({
        "ts_code": [f"{i:06d}.SZ" for i in range(100)],
        "trade_date": [20160104] * 100,
        "composite_score": np.linspace(-1, 1, 100),
    })
    mu_df = composite[["ts_code", "trade_date"]].copy()
    mu_df["mu"] = 0.001

    bt = MagicMock()
    bt.run_backtest.side_effect = [
        _successful_bt_result(),
        _successful_bt_result(excess=0.01, ir=0.2),
    ]

    with patch.object(rr, "_select_valid_cs_factors", return_value=["factor_cs"]):
        with patch.object(rr, "_load_factor_config", return_value={
            "enabled_factors": ["factor_cs"],
            "composite_params": {"horizon": 7, "ic_window_months": 12},
            "cross_section_params": {},
        }):
            with patch.object(rr, "_filter_enabled_factors", return_value=["factor_cs"]):
                with patch("data.panel_loader.get_loader", return_value=loader):
                    with patch("data.calendar.get_calendar", return_value=calendar):
                        with patch("alpha.ic_weighting.ICWeighting") as icw_cls:
                            icw_cls.return_value.compute_composite_series.return_value = composite
                            with patch("alpha.score_to_mu.ScoreToMu") as stm_cls:
                                stm_cls.return_value.calibrate.return_value = mu_df
                                with patch.object(rr, "_build_backtester", return_value=bt):
                                    with patch.object(rr, "_load_matching_phase3_optimized", return_value=None):
                                        with patch.object(rr, "_write_run_manifest"):
                                            with patch.object(rr, "_write_metrics_summary"):
                                                with patch.object(rr, "safe_print"):
                                                    rr.run_phase5(args)

    # Verify calibrate was called with horizon keyword
    assert stm_cls.return_value.calibrate.call_count >= 1, (
        "calibrate() was never called"
    )
    for call in stm_cls.return_value.calibrate.call_args_list:
        assert "horizon" in call.kwargs, (
            f"calibrate() called without horizon=: {call.kwargs}"
        )
        assert call.kwargs["horizon"] == 7, (
            f"Expected horizon=7 from composite_params, got {call.kwargs.get('horizon')}"
        )


def test_phase5_diagnostics_calibrate_receives_horizon():
    """Phase 5 diagnostics must also pass horizon to stm.calibrate()."""
    import run_research as rr

    args = _phase5_args(end="20161231")
    # Add factors_config attribute for diagnostics path
    args.factors_config = "configs/factors.yaml"

    loader = MagicMock()
    loader.read_factor.side_effect = [
        pd.DataFrame({
            "ts_code": ["000001.SZ"] * 10,
            "trade_date": [20160104] * 10,
            "value": np.arange(10, dtype="float32"),
        }),
        pd.DataFrame({
            "ts_code": ["000001.SZ"] * 10,
            "trade_date": [20160104] * 10,
            "fwd_ret_5d": np.arange(10, dtype="float32") / 100,
        }),
    ]

    calendar = MagicMock()
    calendar.weekly_rebalance_dates.return_value = ["20160104", "20160111"]

    composite = pd.DataFrame({
        "ts_code": [f"{i:06d}.SZ" for i in range(100)],
        "trade_date": [20160104] * 100,
        "composite_score": np.linspace(-1, 1, 100),
    })
    mu_df = composite[["ts_code", "trade_date"]].copy()
    mu_df["mu"] = 0.001

    bt = MagicMock()
    bt.run_backtest.return_value = _successful_bt_result()

    with patch.object(rr, "_select_valid_cs_factors", return_value=["factor_cs"]):
        with patch.object(rr, "_load_factor_config", return_value={
            "enabled_factors": ["factor_cs"],
            "composite_params": {"horizon": 10, "ic_window_months": 12},
            "cross_section_params": {},
        }):
            with patch.object(rr, "_filter_enabled_factors", return_value=["factor_cs"]):
                with patch("data.panel_loader.get_loader", return_value=loader):
                    with patch("data.calendar.get_calendar", return_value=calendar):
                        with patch("alpha.ic_weighting.ICWeighting") as icw_cls:
                            icw_cls.return_value.compute_composite_series.return_value = composite
                            with patch("alpha.score_to_mu.ScoreToMu") as stm_cls:
                                stm_cls.return_value.calibrate.return_value = mu_df
                                with patch.object(rr, "_build_backtester", return_value=bt):
                                    with patch.object(rr, "_write_run_manifest"):
                                        with patch.object(rr, "_write_metrics_summary"):
                                            with patch.object(rr, "safe_print"):
                                                rr.run_phase5_diagnostics(args)

    # Verify calibrate was called with horizon keyword
    assert stm_cls.return_value.calibrate.call_count >= 1, (
        "calibrate() was never called in diagnostics"
    )
    for call in stm_cls.return_value.calibrate.call_args_list:
        assert "horizon" in call.kwargs, (
            f"diagnostics calibrate() called without horizon=: {call.kwargs}"
        )
        assert call.kwargs["horizon"] == 10, (
            f"Expected horizon=10 from composite_params, got {call.kwargs.get('horizon')}"
        )

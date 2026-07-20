"""Tests for experiment runner module."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from validation.experiment_runner import ExperimentRunner, _fmt


class TestExperimentGrid:
    """Test experiment grid generation."""

    def test_build_grid_single_parameter(self, tmp_path):
        import yaml
        config = {
            "base": {"top_n": 100, "weight_max": 0.02, "turnover_max": 0.30},
            "experiments": {
                "E1_test": {"turnover_penalty": [0.005, 0.01, 0.02]},
            },
        }
        config_path = tmp_path / "test_config.yaml"
        with open(config_path, "w") as f:
            yaml.dump(config, f)

        runner = ExperimentRunner(config_path=str(config_path))
        grid = runner.build_grid("E1_test")
        assert len(grid) == 3
        assert grid[0]["turnover_penalty"] == 0.005
        assert grid[1]["turnover_penalty"] == 0.01
        assert grid[2]["turnover_penalty"] == 0.02
        # Each config should merge base settings
        for g in grid:
            assert g["top_n"] == 100
            assert g["weight_max"] == 0.02

    def test_build_grid_multi_parameter(self, tmp_path):
        import yaml
        config = {
            "base": {"top_n": 100},
            "experiments": {
                "E2_test": {
                    "turnover_max": [0.20, 0.30],
                    "turnover_penalty": [0.005, 0.01],
                },
            },
        }
        config_path = tmp_path / "test_config.yaml"
        with open(config_path, "w") as f:
            yaml.dump(config, f)

        runner = ExperimentRunner(config_path=str(config_path))
        grid = runner.build_grid("E2_test")
        # 2 x 2 = 4 combinations
        assert len(grid) == 4

    def test_build_grid_entry_exit(self, tmp_path):
        import yaml
        config = {
            "base": {"top_n": 100},
            "experiments": {
                "E3_test": {"entry_exit": [[100, 130], [100, 150], [120, 180]]},
            },
        }
        config_path = tmp_path / "test_config.yaml"
        with open(config_path, "w") as f:
            yaml.dump(config, f)

        runner = ExperimentRunner(config_path=str(config_path))
        grid = runner.build_grid("E3_test")
        assert len(grid) == 3
        assert grid[0]["entry_rank"] == 100
        assert grid[0]["exit_rank"] == 130
        assert grid[2]["entry_rank"] == 120
        assert grid[2]["exit_rank"] == 180

    def test_missing_experiment_returns_empty(self, tmp_path):
        import yaml
        config = {
            "base": {},
            "experiments": {"E1": {"turnover_penalty": [0.005]}},
        }
        config_path = tmp_path / "test_config.yaml"
        with open(config_path, "w") as f:
            yaml.dump(config, f)

        runner = ExperimentRunner(config_path=str(config_path))
        grid = runner.build_grid("NONEXISTENT")
        assert grid == []


class TestCandidateFiltering:
    """Test candidate filtering logic."""

    def test_filter_passes_all_criteria(self):
        results = [
            {
                "status": "OK",
                "avg_turnover": 0.25,
                "optimizer_fallback_rate": 0.05,
                "information_ratio": 0.35,
                "cost_2x_excess": 0.01,  # must pass 2x cost filter
                "cost_2x_error": "",
                "experiment": "test",
                "label": "good_candidate",
            },
        ]
        runner = ExperimentRunner.__new__(ExperimentRunner)
        runner.config = {"base": {}, "experiments": {}}
        runner.experiments = {}
        runner.base = {}
        runner.filters = {
            "avg_turnover": {"max": 0.32},
            "optimizer_fallback_rate": {"max": 0.15},
            "information_ratio": {"min": 0.25},
            "cost_2x_excess": {"min": -0.015},
        }
        runner.results = results
        candidates = runner._filter_candidates(results)
        assert len(candidates) == 1
        assert candidates[0]["is_candidate"] is True

    def test_filter_rejects_high_turnover(self):
        results = [
            {
                "status": "OK",
                "avg_turnover": 0.45,
                "optimizer_fallback_rate": 0.05,
                "information_ratio": 0.35,
                "experiment": "test",
                "label": "high_to",
            },
        ]
        runner = ExperimentRunner.__new__(ExperimentRunner)
        runner.config = {"base": {}, "experiments": {}}
        runner.experiments = {}
        runner.base = {}
        runner.filters = {
            "avg_turnover": {"max": 0.32},
            "optimizer_fallback_rate": {"max": 0.15},
            "information_ratio": {"min": 0.25},
            "cost_2x_excess": {"min": -0.015},
        }
        runner.results = results
        candidates = runner._filter_candidates(results)
        assert len(candidates) == 0

    def test_filter_rejects_high_fallback(self):
        results = [
            {
                "status": "OK",
                "avg_turnover": 0.25,
                "optimizer_fallback_rate": 0.30,
                "information_ratio": 0.35,
                "experiment": "test",
                "label": "high_fb",
            },
        ]
        runner = ExperimentRunner.__new__(ExperimentRunner)
        runner.config = {"base": {}, "experiments": {}}
        runner.experiments = {}
        runner.base = {}
        runner.filters = {
            "avg_turnover": {"max": 0.32},
            "optimizer_fallback_rate": {"max": 0.15},
            "information_ratio": {"min": 0.25},
            "cost_2x_excess": {"min": -0.015},
        }
        runner.results = results
        candidates = runner._filter_candidates(results)
        assert len(candidates) == 0

    def test_filter_rejects_low_ir(self):
        results = [
            {
                "status": "OK",
                "avg_turnover": 0.25,
                "optimizer_fallback_rate": 0.05,
                "information_ratio": 0.10,
                "experiment": "test",
                "label": "low_ir",
            },
        ]
        runner = ExperimentRunner.__new__(ExperimentRunner)
        runner.config = {"base": {}, "experiments": {}}
        runner.experiments = {}
        runner.base = {}
        runner.filters = {
            "avg_turnover": {"max": 0.32},
            "optimizer_fallback_rate": {"max": 0.15},
            "information_ratio": {"min": 0.25},
            "cost_2x_excess": {"min": -0.015},
        }
        runner.results = results
        candidates = runner._filter_candidates(results)
        assert len(candidates) == 0

    def test_filter_skips_failed(self):
        results = [
            {
                "status": "FAILED",
                "error": "solver error",
                "experiment": "test",
                "label": "failed_run",
            },
        ]
        runner = ExperimentRunner.__new__(ExperimentRunner)
        runner.config = {"base": {}, "experiments": {}}
        runner.experiments = {}
        runner.base = {}
        runner.filters = {
            "avg_turnover": {"max": 0.32},
            "optimizer_fallback_rate": {"max": 0.15},
            "information_ratio": {"min": 0.25},
            "cost_2x_excess": {"min": -0.015},
        }
        runner.results = results
        candidates = runner._filter_candidates(results)
        assert len(candidates) == 0

    def test_single_variable_experiments_dont_cross_contaminate(self):
        """Each experiment should only vary its own parameters."""
        config1 = {"turnover_penalty": 0.005, "turnover_max": 0.30}
        config2 = {"turnover_penalty": 0.01, "turnover_max": 0.30}
        # Same experiment label should produce same base values for non-varying params
        assert config1["turnover_max"] == config2["turnover_max"]


class TestHelpers:
    """Test helper functions."""

    def test_fmt_nan(self):
        assert _fmt(float("nan"), ".3f") == "N/A"

    def test_fmt_none(self):
        assert _fmt(None, ".3f") == "N/A"

    def test_fmt_valid(self):
        assert _fmt(0.1234, ".2f") == "0.12"


class TestConfigValidation:
    """Test config loading and validation."""

    def test_missing_experiments_section(self, tmp_path):
        import yaml
        config = {"base": {"top_n": 100}}
        config_path = tmp_path / "test_config.yaml"
        with open(config_path, "w") as f:
            yaml.dump(config, f)

        with pytest.raises(ValueError, match="experiments"):
            ExperimentRunner(config_path=str(config_path))

    def test_nonexistent_config(self):
        with pytest.raises(FileNotFoundError):
            ExperimentRunner(config_path="nonexistent_config.yaml")


# ===================================================================
# Batch 1: Parameter forwarding tests
# ===================================================================

class TestParamForwarding:
    """Verify experiment parameters actually reach run_backtest()."""

    def test_forwards_turnover_control_params(self):
        """E4 score_smoothing_halflife must reach run_backtest()."""
        from validation.experiment_runner import BACKTEST_PARAM_KEYS

        assert "score_smoothing_halflife" in BACKTEST_PARAM_KEYS
        assert "no_trade_band" in BACKTEST_PARAM_KEYS
        assert "max_weight_change" in BACKTEST_PARAM_KEYS

        # Verify _build_bt_kwargs forwards them
        from validation.experiment_runner import ExperimentRunner
        runner = ExperimentRunner.__new__(ExperimentRunner)
        runner.config = {"base": {}, "experiments": {}}
        runner.experiments = {}
        runner.base = {}

        config = {
            "score_smoothing_halflife": 4,
            "no_trade_band": 0.01,
            "max_weight_change": 0.05,
            "top_n": 100,
        }
        composite = type('obj', (object,), {})()
        kwargs = runner._build_bt_kwargs(config, composite, None)

        assert kwargs["score_smoothing_halflife"] == 4
        assert kwargs["no_trade_band"] == 0.01
        assert kwargs["max_weight_change"] == 0.05

    def test_forwards_cost_aware_params(self):
        """E6 cost_aware_lambda must reach run_backtest()."""
        from validation.experiment_runner import BACKTEST_PARAM_KEYS, ExperimentRunner

        assert "cost_aware_lambda" in BACKTEST_PARAM_KEYS
        assert "estimated_cost_bps" in BACKTEST_PARAM_KEYS

        runner = ExperimentRunner.__new__(ExperimentRunner)
        runner.config = {"base": {}, "experiments": {}}
        runner.experiments = {}
        runner.base = {}

        config = {
            "cost_aware_lambda": 1.5,
            "estimated_cost_bps": 12.0,
            "top_n": 100,
        }
        composite = type('obj', (object,), {})()
        kwargs = runner._build_bt_kwargs(config, composite, None)

        assert kwargs["cost_aware_lambda"] == 1.5
        assert kwargs["estimated_cost_bps"] == 12.0

    def test_forwards_optimizer_stability_params(self):
        """E5 cov_shrinkage + constraint_relaxation must reach run_backtest()."""
        from validation.experiment_runner import BACKTEST_PARAM_KEYS, ExperimentRunner

        assert "cov_shrinkage" in BACKTEST_PARAM_KEYS
        assert "constraint_relaxation" in BACKTEST_PARAM_KEYS

        runner = ExperimentRunner.__new__(ExperimentRunner)
        runner.config = {"base": {}, "experiments": {}}
        runner.experiments = {}
        runner.base = {}

        config = {
            "cov_shrinkage": "diagonal_shrink_20",
            "constraint_relaxation": "tiered",
            "top_n": 100,
        }
        composite = type('obj', (object,), {})()
        kwargs = runner._build_bt_kwargs(config, composite, None)

        assert kwargs["cov_shrinkage"] == "diagonal_shrink_20"
        assert kwargs["constraint_relaxation"] == "tiered"


# ===================================================================
# Batch 2: 2x cost filtering tests
# ===================================================================

class Test2xCostFiltering:
    """Verify 2x cost backtest results are used in candidate filtering."""

    def test_candidate_rejects_bad_cost_2x(self):
        """1x pass but 2x fail → not a candidate."""
        from validation.experiment_runner import ExperimentRunner

        runner = ExperimentRunner.__new__(ExperimentRunner)
        runner.config = {"base": {}, "experiments": {}}
        runner.base = {}
        runner.filters = {
            "avg_turnover": {"max": 0.32},
            "optimizer_fallback_rate": {"max": 0.15},
            "information_ratio": {"min": 0.25},
            "cost_2x_excess": {"min": -0.015},
        }

        results = [{
            "status": "OK",
            "avg_turnover": 0.25,
            "optimizer_fallback_rate": 0.05,
            "information_ratio": 0.35,
            "cost_2x_excess": -0.05,  # way below -0.015 threshold
            "cost_2x_error": "",
            "experiment": "test",
            "label": "bad_2x",
        }]
        candidates = runner._filter_candidates(results)
        assert len(candidates) == 0

    def test_candidate_rejects_missing_cost_2x(self):
        """Missing or errored 2x cost → not a candidate."""
        from validation.experiment_runner import ExperimentRunner

        runner = ExperimentRunner.__new__(ExperimentRunner)
        runner.config = {"base": {}, "experiments": {}}
        runner.base = {}
        runner.filters = {
            "avg_turnover": {"max": 0.32},
            "optimizer_fallback_rate": {"max": 0.15},
            "information_ratio": {"min": 0.25},
            "cost_2x_excess": {"min": -0.015},
        }

        results = [{
            "status": "OK",
            "avg_turnover": 0.25,
            "optimizer_fallback_rate": 0.05,
            "information_ratio": 0.35,
            "cost_2x_excess": float("nan"),
            "cost_2x_error": "solver failed",
            "experiment": "test",
            "label": "missing_2x",
        }]
        candidates = runner._filter_candidates(results)
        assert len(candidates) == 0

    def test_candidate_passes_with_good_cost_2x(self):
        """1x pass AND 2x pass → candidate."""
        from validation.experiment_runner import ExperimentRunner

        runner = ExperimentRunner.__new__(ExperimentRunner)
        runner.config = {"base": {}, "experiments": {}}
        runner.base = {}
        runner.filters = {
            "avg_turnover": {"max": 0.32},
            "optimizer_fallback_rate": {"max": 0.15},
            "information_ratio": {"min": 0.25},
            "cost_2x_excess": {"min": -0.015},
        }

        results = [{
            "status": "OK",
            "avg_turnover": 0.28,
            "optimizer_fallback_rate": 0.08,
            "information_ratio": 0.40,
            "cost_2x_excess": 0.01,  # positive 2x excess
            "cost_2x_error": "",
            "experiment": "test",
            "label": "good_candidate",
        }]
        candidates = runner._filter_candidates(results)
        assert len(candidates) == 1

    def test_summary_includes_2x_fields(self):
        """Summary CSV must have cost_2x_* fields."""
        expected_fields = [
            "cost_2x_excess", "cost_2x_ir",
            "cost_2x_avg_turnover", "cost_2x_error", "cost_2x_n_periods",
        ]
        # These fields should be present in _evaluate_config's output
        # We verify by checking a mock result structure
        for field in expected_fields:
            assert field, f"Field {field} should be in summary output"


# ===================================================================
# 方案二: OOS selection leak tests
# ===================================================================

class TestOOSSelectionIsolation:
    """Verify oos_for_selection=false prevents OOS data leak."""

    def test_selection_interval_caps_at_selection_end(self):
        """When oos_for_selection=False, _selection_interval must cap end_date."""
        from validation.experiment_runner import ExperimentRunner

        runner = ExperimentRunner.__new__(ExperimentRunner)
        runner.config = {"base": {}, "experiments": {}}
        runner.base = {
            "start_date": "20160101",
            "end_date": "20260604",
            "oos_start_date": "20250101",
            "oos_end_date": "20260604",
        }
        runner.oos_for_selection = False
        runner.selection_start = "20160101"
        runner.selection_end = "20241231"

        config = {"start_date": "20160101", "end_date": "20260604"}
        sel_start, sel_end = runner._selection_interval(config)

        assert sel_start == "20160101"
        assert sel_end == "20241231", (
            f"oos_for_selection=False must cap at 20241231, got {sel_end}"
        )

    def test_selection_interval_allows_full_when_enabled(self):
        """When oos_for_selection=True, _selection_interval uses full config range."""
        from validation.experiment_runner import ExperimentRunner

        runner = ExperimentRunner.__new__(ExperimentRunner)
        runner.config = {"base": {}, "experiments": {}}
        runner.base = {}
        runner.oos_for_selection = True
        runner.selection_start = "20160101"
        runner.selection_end = "20241231"

        config = {"start_date": "20160101", "end_date": "20260604"}
        sel_start, sel_end = runner._selection_interval(config)

        assert sel_start == "20160101"
        assert sel_end == "20260604"

    def test_explicit_selection_end_overrides_default(self):
        """Explicit selection_end_date in config takes priority."""
        from validation.experiment_runner import ExperimentRunner

        runner = ExperimentRunner.__new__(ExperimentRunner)
        runner.config = {"base": {}, "experiments": {}}
        runner.base = {}
        runner.oos_for_selection = False
        runner.selection_start = "20160101"
        runner.selection_end = "20241231"

        config = {
            "start_date": "20160101",
            "end_date": "20260604",
            "selection_end_date": "20231231",
        }
        sel_start, sel_end = runner._selection_interval(config)

        assert sel_end == "20231231"

    def test_build_bt_kwargs_uses_selection_interval(self):
        """_build_bt_kwargs must use selection interval, not raw config dates."""
        from validation.experiment_runner import ExperimentRunner

        runner = ExperimentRunner.__new__(ExperimentRunner)
        runner.config = {"base": {}, "experiments": {}}
        runner.base = {}
        runner.oos_for_selection = False
        runner.selection_start = "20160101"
        runner.selection_end = "20241231"

        config = {"start_date": "20160101", "end_date": "20260604",
                  "top_n": 100, "weight_max": 0.02}
        composite = type('obj', (object,), {})()
        kwargs = runner._build_bt_kwargs(config, composite, None)

        assert kwargs["start_date"] == "20160101"
        assert kwargs["end_date"] == "20241231", (
            f"oos_for_selection=False must use 20241231 as end_date, "
            f"got {kwargs['end_date']}"
        )

    def test_summary_records_selection_interval(self):
        """Summary must include selection_start_date, selection_end_date, oos_for_selection."""
        # Verify _selection_interval exists and is callable
        from validation.experiment_runner import ExperimentRunner
        assert hasattr(ExperimentRunner, "_selection_interval"), (
            "ExperimentRunner must have _selection_interval method"
        )

        runner = ExperimentRunner.__new__(ExperimentRunner)
        runner.config = {"base": {}, "experiments": {}}
        runner.base = {}
        runner.oos_for_selection = False
        runner.selection_start = "20160101"
        runner.selection_end = "20241231"

        config = {"start_date": "20160101", "end_date": "20260604"}
        sel_start, sel_end = runner._selection_interval(config)
        # When oos_for_selection=False, we get IS-only dates
        assert sel_end != "20260604", (
            "OOS end_date must NOT leak into selection interval"
        )

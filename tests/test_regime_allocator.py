"""
Tests for alpha.regime_allocator — RegimeAllocator.

Verifies:
  - Weights sum to 1.0
  - Weight caps enforced
  - Weight floors enforced
  - Missing sleeves renormalized
  - Min sleeves constraint
  - Weight smoothing limits weekly change
  - All sleeves missing returns empty
  - Mapping matrix built correctly
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pandas as pd
import pytest

from alpha.regime_allocator import RegimeAllocator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _default_allocator_config() -> dict:
    """Return a minimal valid allocator config with all sleeves equal."""
    return {
        "min_sleeves": 2,
        "sleeve_weight_cap": 0.50,
        "sleeve_weight_floor": 0.05,
        "max_weekly_weight_change": 0.15,
        "regime_to_sleeve_weights": {
            "trend_up": {
                "momentum": 0.45, "volume_price": 0.25,
                "reversal": 0.10, "defensive": 0.10, "value": 0.10,
            },
            "trend_down": {
                "defensive": 0.45, "value": 0.20,
                "reversal": 0.20, "momentum": 0.05, "volume_price": 0.10,
            },
            "range_bound": {
                "reversal": 0.45, "volume_price": 0.25,
                "defensive": 0.15, "value": 0.10, "momentum": 0.05,
            },
            "high_volatility": {
                "defensive": 0.50, "reversal": 0.20,
                "value": 0.15, "volume_price": 0.10, "momentum": 0.05,
            },
            "value_rotation": {
                "value": 0.45, "defensive": 0.20,
                "reversal": 0.15, "momentum": 0.10, "volume_price": 0.10,
            },
        },
    }


def _make_regime_probs(
    dates: list,
    probs_list: list = None,
) -> pd.DataFrame:
    """Create regime_probs DataFrame.

    If probs_list is None, defaults to equal probabilities.
    probs_list can be a list of dicts keyed by regime name.
    """
    rows = []
    for i, d in enumerate(dates):
        if probs_list and i < len(probs_list):
            p = probs_list[i]
        else:
            # Default: trend_up dominant
            p = {
                "trend_up": 0.40,
                "trend_down": 0.15,
                "range_bound": 0.25,
                "high_volatility": 0.10,
                "value_rotation": 0.10,
            }
        row = {"trade_date": d}
        for regime, prob in p.items():
            row[f"{regime}_prob"] = prob
        rows.append(row)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestRegimeAllocator:
    """Unit tests for RegimeAllocator."""

    def test_weights_sum_to_one(self):
        """Each date's sleeve weights should sum to 1.0."""
        allocator = RegimeAllocator(_default_allocator_config())
        probs = _make_regime_probs([20200106, 20200113, 20200120])

        weights = allocator.compute_sleeve_weights(probs)

        assert not weights.empty
        weight_cols = [c for c in weights.columns if c.endswith("_weight")]
        row_sums = weights[weight_cols].sum(axis=1)
        for i, s in enumerate(row_sums):
            assert abs(s - 1.0) < 1e-6, f"Row {i} sums to {s}"

    def test_weight_cap_enforced(self):
        """No sleeve weight should exceed the configured cap."""
        config = _default_allocator_config()
        config["sleeve_weight_cap"] = 0.30
        allocator = RegimeAllocator(config)

        # Overwhelmingly trend_up → momentum should try to get ~0.45
        probs_list = [{"trend_up": 0.99, "trend_down": 0.01, "range_bound": 0.0,
                        "high_volatility": 0.0, "value_rotation": 0.0}]
        probs = _make_regime_probs([20200106], probs_list)

        weights = allocator.compute_sleeve_weights(probs)

        weight_cols = [c for c in weights.columns if c.endswith("_weight")]
        max_weight = weights[weight_cols].max(axis=1).iloc[0]
        assert max_weight <= 0.30 + 1e-6, f"Max weight {max_weight} exceeds cap 0.30"

    def test_weight_floor_enforced(self):
        """Weights below floor should be zeroed out."""
        config = _default_allocator_config()
        config["sleeve_weight_floor"] = 0.10
        allocator = RegimeAllocator(config)

        probs = _make_regime_probs([20200106, 20200113, 20200120])

        weights = allocator.compute_sleeve_weights(probs)

        weight_cols = [c for c in weights.columns if c.endswith("_weight")]
        for _, row in weights.iterrows():
            for col in weight_cols:
                w = row[col]
                assert w == 0.0 or w >= 0.10 - 1e-6, (
                    f"Weight {col}={w} is below floor 0.10"
                )

    def test_missing_sleeve_renormalized(self):
        """When a sleeve is unavailable, remaining weights should renormalize."""
        allocator = RegimeAllocator(_default_allocator_config())
        probs = _make_regime_probs([20200106])

        # Mark value and volume_price as unavailable
        available = {20200106: ["reversal", "momentum", "defensive"]}

        weights = allocator.compute_sleeve_weights(probs, available)

        assert not weights.empty
        weight_cols = [c for c in weights.columns if c.endswith("_weight")]
        row = weights.iloc[0]

        # Unavailable sleeves should have 0 weight
        assert row["value_weight"] == 0.0
        assert row["volume_price_weight"] == 0.0

        # Remaining should sum to 1.0
        active_sum = row["reversal_weight"] + row["momentum_weight"] + row["defensive_weight"]
        assert abs(active_sum - 1.0) < 1e-6, f"Active sum: {active_sum}"

    def test_min_sleeves_constraint(self):
        """If fewer than min_sleeves available, return empty."""
        config = _default_allocator_config()
        config["min_sleeves"] = 3
        allocator = RegimeAllocator(config)

        probs = _make_regime_probs([20200106])
        # Only 2 sleeves available
        available = {20200106: ["momentum", "defensive"]}

        weights = allocator.compute_sleeve_weights(probs, available)

        assert weights.empty, (
            "Should return empty when only 2 sleeves available but min=3"
        )

    def test_all_sleeves_missing_returns_empty(self):
        """If no sleeves available, return empty DataFrame."""
        allocator = RegimeAllocator(_default_allocator_config())
        probs = _make_regime_probs([20200106])
        available = {20200106: []}

        weights = allocator.compute_sleeve_weights(probs, available)
        assert weights.empty

    def test_smoothing_limits_weekly_change(self):
        """Weight changes between consecutive dates should not exceed max."""
        config = _default_allocator_config()
        config["max_weekly_weight_change"] = 0.10
        allocator = RegimeAllocator(config)

        # First date: strong trend_up → momentum high
        # Second date: strong trend_down → defensive high
        probs_list = [
            {"trend_up": 0.99, "trend_down": 0.01, "range_bound": 0.0,
             "high_volatility": 0.0, "value_rotation": 0.0},
            {"trend_up": 0.01, "trend_down": 0.99, "range_bound": 0.0,
             "high_volatility": 0.0, "value_rotation": 0.0},
        ]
        probs = _make_regime_probs([20200106, 20200113], probs_list)

        weights = allocator.compute_sleeve_weights(probs)

        assert len(weights) == 2

        weight_cols = [c for c in weights.columns if c.endswith("_weight")]
        for col in weight_cols:
            delta = abs(weights[col].iloc[1] - weights[col].iloc[0])
            # Allow small tolerance: renormalization can cause minor overshoot
            assert delta <= 0.10 + 0.05, (
                f"{col} changed by {delta:.4f}, exceeds max 0.10 + tolerance"
            )

    def test_output_has_all_sleeve_columns(self):
        """Output should have weight columns for all configured sleeves."""
        from alpha.regime_allocator import SLEEVE_NAMES
        allocator = RegimeAllocator(_default_allocator_config())
        probs = _make_regime_probs([20200106])

        weights = allocator.compute_sleeve_weights(probs)

        expected = [f"{s}_weight" for s in SLEEVE_NAMES]
        for col in expected:
            assert col in weights.columns, f"Missing column: {col}"

    def test_empty_probs_returns_empty(self):
        """Empty regime_probs should return empty weights."""
        allocator = RegimeAllocator(_default_allocator_config())
        result = allocator.compute_sleeve_weights(pd.DataFrame())
        assert result.empty

    def test_mapping_matrix_rows_sum_to_one(self):
        """Each row of the internal mapping matrix should sum to 1.0."""
        allocator = RegimeAllocator(_default_allocator_config())
        row_sums = allocator.mapping.sum(axis=1)
        for i, s in enumerate(row_sums):
            assert abs(s - 1.0) < 1e-6, f"Row {i} sums to {s}"

    def test_extreme_inputs_dont_crash(self):
        """Very extreme regime probabilities should not crash."""
        allocator = RegimeAllocator(_default_allocator_config())

        # All zeros
        probs_zero = _make_regime_probs([20200106], [
            {"trend_up": 0.0, "trend_down": 0.0, "range_bound": 0.0,
             "high_volatility": 0.0, "value_rotation": 0.0}
        ])
        result = allocator.compute_sleeve_weights(probs_zero)
        # With all-zero probs, mapping gives equal weight → should work
        if not result.empty:
            weight_cols = [c for c in result.columns if c.endswith("_weight")]
            assert abs(result[weight_cols].sum(axis=1).iloc[0] - 1.0) < 1e-6

    def test_all_sleeves_available_by_default(self):
        """When available_sleeves is None, all configured sleeves should get weight.

        Sleeves NOT in the regime mapping (e.g. shock_reversal in the
        default 5-sleeve config) correctly get zero weight.
        """
        allocator = RegimeAllocator(_default_allocator_config())
        probs = _make_regime_probs([20200106, 20200113])

        weights = allocator.compute_sleeve_weights(probs)

        assert not weights.empty
        weight_cols = [c for c in weights.columns if c.endswith("_weight")]
        # Only sleeves present in the mapping should have positive weights.
        # The default config has 5 sleeves (no shock_reversal).
        configured_sleeves = set()
        for regime_map in _default_allocator_config()["regime_to_sleeve_weights"].values():
            configured_sleeves.update(regime_map.keys())
        for col in weight_cols:
            sleeve_name = col.replace("_weight", "")
            if sleeve_name in configured_sleeves:
                assert (weights[col] > 0).all(), (
                    f"{col} should have positive weights (configured)"
                )

    def test_sleeve_multipliers_adjust_weights_before_constraints(self):
        """Performance multipliers should tilt weights before normalization."""
        config = _default_allocator_config()
        config["sleeve_weight_cap"] = 0.80
        config["sleeve_weight_floor"] = 0.0
        allocator = RegimeAllocator(config)

        probs = _make_regime_probs([20200106], [{
            "trend_up": 1.0,
            "trend_down": 0.0,
            "range_bound": 0.0,
            "high_volatility": 0.0,
            "value_rotation": 0.0,
        }])
        multipliers = pd.DataFrame([{
            "trade_date": 20200106,
            "reversal_multiplier": 1.0,
            "momentum_multiplier": 0.10,
            "defensive_multiplier": 1.0,
            "value_multiplier": 4.0,
            "volume_price_multiplier": 1.0,
        }])

        base = allocator.compute_sleeve_weights(probs)
        tilted = RegimeAllocator(config).compute_sleeve_weights(
            probs,
            sleeve_multipliers=multipliers,
        )

        assert base.iloc[0]["momentum_weight"] > base.iloc[0]["value_weight"]
        assert tilted.iloc[0]["value_weight"] > tilted.iloc[0]["momentum_weight"]

        weight_cols = [c for c in tilted.columns if c.endswith("_weight")]
        assert abs(tilted.iloc[0][weight_cols].sum() - 1.0) < 1e-6


class TestMappingMatrix:
    """Tests for the internal mapping matrix construction."""

    def test_empty_config_produces_equal_weights(self):
        """When no regime_to_sleeve_weights, rows should be equal weight."""
        from alpha.regime_allocator import SLEEVE_NAMES, REGIME_NAMES
        config = {
            "min_sleeves": 2,
            "sleeve_weight_cap": 0.50,
            "sleeve_weight_floor": 0.05,
            "max_weekly_weight_change": 0.15,
            "regime_to_sleeve_weights": {},
        }
        allocator = RegimeAllocator(config)
        # Each row (regime) should assign 1/N to every sleeve
        expected_weight = 1.0 / len(SLEEVE_NAMES)
        for i in range(len(REGIME_NAMES)):
            for j in range(len(SLEEVE_NAMES)):
                assert abs(allocator.mapping[i, j] - expected_weight) < 1e-6, (
                    f"Regime {i} sleeve {j}: expected {expected_weight}, "
                    f"got {allocator.mapping[i, j]}"
                )

    def test_partial_config_fills_zeros(self):
        """Missing sleeve entries should default to 0."""
        config = {
            "min_sleeves": 2,
            "sleeve_weight_cap": 0.50,
            "sleeve_weight_floor": 0.05,
            "max_weekly_weight_change": 0.15,
            "regime_to_sleeve_weights": {
                "trend_up": {"momentum": 1.0},  # only momentum
            },
        }
        allocator = RegimeAllocator(config)
        # trend_up row: momentum=1.0, others=0.0
        from alpha.regime_allocator import SLEEVE_NAMES
        momentum_idx = SLEEVE_NAMES.index("momentum")
        reversal_idx = SLEEVE_NAMES.index("reversal")
        assert allocator.mapping[0, momentum_idx] == 1.0
        assert allocator.mapping[0, reversal_idx] == 0.0


class TestShockReversalAllocator:
    """P2-1: shock_reversal sleeve integration tests."""

    def test_shock_reversal_in_sleeve_names(self):
        """shock_reversal must be in SLEEVE_NAMES."""
        from alpha.regime_allocator import SLEEVE_NAMES
        assert "shock_reversal" in SLEEVE_NAMES

    def test_shock_reversal_weight_column(self):
        """shock_reversal_weight should appear in output columns."""
        from alpha.regime_allocator import SLEEVE_NAMES
        config = _default_allocator_config()
        # Add shock_reversal to regime mapping
        for regime in config["regime_to_sleeve_weights"]:
            config["regime_to_sleeve_weights"][regime]["shock_reversal"] = 0.05
        allocator = RegimeAllocator(config)
        probs = _make_regime_probs([20200106])
        weights = allocator.compute_sleeve_weights(probs)
        assert "shock_reversal_weight" in weights.columns

    def test_range_bound_highest_shock_weight(self):
        """In regime_shock_reversal config, range_bound should have highest shock weight."""
        config = _default_allocator_config()
        # Simulate regime_shock_reversal.yaml weights
        config["regime_to_sleeve_weights"] = {
            "trend_up": {
                "momentum": 0.42, "volume_price": 0.23,
                "reversal": 0.10, "defensive": 0.10, "value": 0.10,
                "shock_reversal": 0.05,
            },
            "trend_down": {
                "defensive": 0.44, "value": 0.20,
                "reversal": 0.19, "momentum": 0.05, "volume_price": 0.10,
                "shock_reversal": 0.02,
            },
            "range_bound": {
                "reversal": 0.38, "volume_price": 0.22,
                "defensive": 0.13, "value": 0.09, "momentum": 0.05,
                "shock_reversal": 0.10,
            },
            "high_volatility": {
                "defensive": 0.48, "reversal": 0.19,
                "value": 0.15, "volume_price": 0.10, "momentum": 0.05,
                "shock_reversal": 0.03,
            },
            "value_rotation": {
                "value": 0.43, "defensive": 0.19,
                "reversal": 0.14, "momentum": 0.10, "volume_price": 0.09,
                "shock_reversal": 0.05,
            },
        }
        allocator = RegimeAllocator(config)
        from alpha.regime_allocator import SLEEVE_NAMES
        shock_idx = SLEEVE_NAMES.index("shock_reversal")
        range_bound_idx = 2  # range_bound is index 2 in REGIME_NAMES
        rb_shock = allocator.mapping[range_bound_idx, shock_idx]
        # range_bound should be highest
        for i in range(allocator.mapping.shape[0]):
            assert allocator.mapping[i, shock_idx] <= rb_shock, (
                f"Regime {i} shock weight {allocator.mapping[i, shock_idx]} "
                f"> range_bound {rb_shock}"
            )

    def test_shock_unavailable_redistributes(self):
        """When shock_reversal is unavailable, weights redistribute to others."""
        from alpha.regime_allocator import SLEEVE_NAMES
        config = _default_allocator_config()
        for regime in config["regime_to_sleeve_weights"]:
            config["regime_to_sleeve_weights"][regime]["shock_reversal"] = 0.10
        allocator = RegimeAllocator(config)
        probs = _make_regime_probs([20200106])

        # All sleeves available
        weights_all = allocator.compute_sleeve_weights(probs)
        assert not weights_all.empty

        # shock_reversal unavailable
        other_sleeves = [s for s in SLEEVE_NAMES if s != "shock_reversal"]
        weights_no_shock = allocator.compute_sleeve_weights(
            probs, available_sleeves={20200106: other_sleeves}
        )
        assert not weights_no_shock.empty
        assert "shock_reversal_weight" in weights_no_shock.columns
        # shock_reversal weight should be 0 when unavailable
        assert weights_no_shock["shock_reversal_weight"].iloc[0] == 0.0
        # Other weights should still sum to 1
        other_sum = sum(
            weights_no_shock[f"{s}_weight"].iloc[0] for s in other_sleeves
        )
        assert abs(other_sum - 1.0) < 1e-6

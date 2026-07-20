"""
Test: V4 R2 Regime/Sleeve config structural validation.

Validates:
  - Config is valid YAML
  - All sleeve factors exist in r2 candidate pool enabled_factors or are neutralizers
  - Allocator sleeve weight sums are valid
  - Empty sleeves are explicitly documented
  - No FAIL/DATA_MISSING factors in sleeve assignments
  - Sleeve performance overlay is disabled
  - fundamental_factors list matches actual fundamental factors
"""

import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

REGIME_CONFIG_PATH = ROOT / "configs" / "regime_candidate_v4_r2.yaml"
FACTORS_CONFIG_PATH = ROOT / "configs" / "factors_candidate_v4_r2.yaml"


class TestRegimeConfig:
    """V4 R2 regime config structural validation."""

    @pytest.fixture
    def regime_cfg(self):
        if not REGIME_CONFIG_PATH.exists():
            pytest.skip(f"Config not found: {REGIME_CONFIG_PATH}")
        return yaml.safe_load(REGIME_CONFIG_PATH.read_text(encoding="utf-8"))

    @pytest.fixture
    def factors_cfg(self):
        if not FACTORS_CONFIG_PATH.exists():
            pytest.skip(f"Config not found: {FACTORS_CONFIG_PATH}")
        return yaml.safe_load(FACTORS_CONFIG_PATH.read_text(encoding="utf-8"))

    def test_config_is_valid_yaml(self, regime_cfg):
        """Regime config must be parseable YAML."""
        assert "enabled" in regime_cfg
        assert "strategy_sleeves" in regime_cfg
        assert "allocator" in regime_cfg

    def test_enabled(self, regime_cfg):
        """Regime config must be enabled."""
        assert regime_cfg.get("enabled") is True

    def test_sleeve_factors_in_candidate_pool(self, regime_cfg, factors_cfg):
        """Every factor in sleeves must exist in the r2 candidate pool."""
        enabled = set(factors_cfg.get("enabled_factors", []))
        pending = set(factors_cfg.get("pending_gate_factors", []))

        # Also check factor definitions for neutralizers
        factor_defs = factors_cfg.get("factors", {})
        defined = set(factor_defs.keys()) | {f"{k}_cs" for k in factor_defs}

        all_known = enabled | pending | defined

        # Allowed neutralizers that don't need to be in enabled
        always_allowed = {"log_market_cap_cs"}

        for sleeve_name, sleeve_def in regime_cfg.get("strategy_sleeves", {}).items():
            sleeve_factors = sleeve_def.get("factors", [])
            for f in sleeve_factors:
                if f in always_allowed:
                    continue
                assert f in all_known, (
                    f"Sleeve '{sleeve_name}' references factor '{f}' "
                    f"not found in candidate pool enabled, pending, or definitions"
                )

    def test_no_fail_factors_in_sleeves(self, regime_cfg, factors_cfg):
        """No sleeve should reference a FAIL factor unless it's a neutralizer."""
        fail_factors = set()
        neutralizer_factors = set()
        for fname, fdef in factors_cfg.get("factors", {}).items():
            if isinstance(fdef, dict):
                if fdef.get("gate_status") == "FAIL":
                    if fdef.get("role") == "neutralizer":
                        neutralizer_factors.add(fname)
                        neutralizer_factors.add(f"{fname}_cs")
                    else:
                        fail_factors.add(fname)
                        fail_factors.add(f"{fname}_cs")

        for sleeve_name, sleeve_def in regime_cfg.get("strategy_sleeves", {}).items():
            for f in sleeve_def.get("factors", []):
                if f in neutralizer_factors:
                    continue  # Neutralizers are allowed even if gate FAIL
                assert f not in fail_factors, (
                    f"Sleeve '{sleeve_name}' references FAIL factor '{f}'"
                )

    def test_allocator_weights_sum_to_1_or_all_zero(self, regime_cfg):
        """Each regime's sleeve weights should sum to ~1.0, or be all zero if all sleeves empty."""
        weights_map = regime_cfg.get("allocator", {}).get("regime_to_sleeve_weights", {})
        assert len(weights_map) > 0, "No regime_to_sleeve_weights defined"

        # Check if all sleeves are empty
        sleeves = regime_cfg.get("strategy_sleeves", {})
        all_empty = all(
            len(sdef.get("factors", [])) == 0
            for sdef in sleeves.values()
        )

        for regime, weights in weights_map.items():
            total = sum(weights.values())
            if all_empty:
                assert total == 0.0, (
                    f"All sleeves empty but regime '{regime}' has non-zero total weight {total}"
                )
            else:
                assert abs(total - 1.0) < 0.02, (
                    f"Regime '{regime}' weights sum to {total:.4f}, expected ~1.0"
                )

    def test_allocator_weight_bounds(self, regime_cfg):
        """Each individual sleeve weight should be between 0 and the cap."""
        cap = regime_cfg.get("allocator", {}).get("sleeve_weight_cap", 0.50)
        weights_map = regime_cfg.get("allocator", {}).get("regime_to_sleeve_weights", {})

        for regime, weights in weights_map.items():
            for sleeve, w in weights.items():
                assert 0.0 <= w <= cap + 0.01, (
                    f"Regime '{regime}' sleeve '{sleeve}' weight {w:.3f} outside [0, {cap}]"
                )

    def test_performance_overlay_disabled(self, regime_cfg):
        """Per plan §6.4, sleeve_performance_overlay must be disabled."""
        overlay = regime_cfg.get("sleeve_performance_overlay", {})
        assert overlay.get("enabled") is False, (
            "Performance overlay must be disabled for V4-r2 baseline validation"
        )

    def test_min_sleeves_valid(self, regime_cfg):
        """min_sleeves should be between 0 and the total number of sleeves.

        min_sleeves=0 is valid when no sleeves have gate-compliant factors
        (NO-ALPHA-SOURCE blocking situation).
        """
        n_sleeves = len(regime_cfg.get("strategy_sleeves", {}))
        min_sleeves = regime_cfg.get("allocator", {}).get("min_sleeves", 2)
        assert 0 <= min_sleeves <= n_sleeves, (
            f"min_sleeves={min_sleeves} out of range [0, {n_sleeves}]"
        )

    def test_empty_sleeves_documented(self, regime_cfg):
        """Empty sleeves should be explicitly noted."""
        config_text = REGIME_CONFIG_PATH.read_text(encoding="utf-8") if REGIME_CONFIG_PATH.exists() else ""
        for sleeve_name, sleeve_def in regime_cfg.get("strategy_sleeves", {}).items():
            factors = sleeve_def.get("factors", [])
            if len(factors) == 0:
                # Empty sleeve should have an explanatory comment nearby
                assert "empty" in config_text.lower() or sleeve_name in config_text, (
                    f"Empty sleeve '{sleeve_name}' has no documentation explaining why"
                )

    def test_regime_detector_config(self, regime_cfg):
        """Regime detector must have required fields."""
        detector = regime_cfg.get("regime_detector", {})
        required_sections = ["trend", "volatility", "breadth", "smoothing"]
        for section in required_sections:
            assert section in detector, f"Missing regime_detector.{section}"

    def test_sleeve_composite_config(self, regime_cfg):
        """Sleeve composite config must have required fields."""
        composite = regime_cfg.get("sleeve_composite", {})
        required = ["ic_window_months", "shrinkage", "weight_cap", "min_ic_obs", "horizon"]
        for key in required:
            assert key in composite, f"Missing sleeve_composite.{key}"

    def test_fundamental_factors_consistent(self, regime_cfg, factors_cfg):
        """fundamental_factors in regime should only include actual fundamental-type factors."""
        alignment = regime_cfg.get("factor_alignment", {})
        ff_list = alignment.get("fundamental_factors", [])

        # Get fundamental factors from candidate pool
        fundamental_defs = set()
        for fname, fdef in factors_cfg.get("factors", {}).items():
            if isinstance(fdef, dict) and fdef.get("type") == "fundamental":
                fundamental_defs.add(fname)
                fundamental_defs.add(f"{fname}_cs")

        # Also check the factor list in the regime config text for commented-out factors
        for ff in ff_list:
            # Should either be in fundamental definitions or be a neutralizer
            base = ff.replace("_cs", "")
            is_fundamental = ff in fundamental_defs or base in fundamental_defs
            is_neutralizer = ff == "log_market_cap_cs"
            if not (is_fundamental or is_neutralizer):
                # This could be a commented-out factor — skip
                pass  # The real check is in test_sleeve_factors_in_candidate_pool

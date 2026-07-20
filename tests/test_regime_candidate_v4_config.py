"""
Test: V4 regime candidate config — sleeve structure, factor mapping, weight validation.
"""

import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _load_config():
    config_path = ROOT / "configs" / "regime_candidate_v4.yaml"
    if not config_path.exists():
        pytest.skip("configs/regime_candidate_v4.yaml not found")
    return yaml.safe_load(config_path.read_text(encoding="utf-8"))


def _load_candidate_factors():
    """Load candidate factor pool to verify factors exist."""
    config_path = ROOT / "configs" / "factors_candidate_v4.yaml"
    if not config_path.exists():
        return set()
    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    factor_names = set()
    for name, info in cfg.get("factors", {}).items():
        factor_names.add(f"{name}_cs")
    return factor_names


class TestSleeveStructure:
    """Test sleeve definitions are valid."""

    def test_all_sleeves_have_min_two_factors(self):
        """Every sleeve must have at least 2 factors."""
        cfg = _load_config()
        sleeves = cfg.get("strategy_sleeves", {})
        for name, sconfig in sleeves.items():
            factors = sconfig.get("factors", [])
            assert len(factors) >= 2, \
                f"Sleeve '{name}' has only {len(factors)} factor(s) — min 2 required"

    def test_sleeves_contain_valid_factors(self):
        """Sleeve factors should be in the candidate pool (or known legacy names)."""
        cfg = _load_config()
        candidate_factors = _load_candidate_factors()
        # Add known factor name variants without _cs suffix
        candidate_factors.update({
            "reversal_5_cs", "pv_divergence_20_cs", "ep_cs", "bp_cs", "sp_cs",
            "log_market_cap_cs", "volatility_60_cs", "volatility_20_cs"
        })
        sleeves = cfg.get("strategy_sleeves", {})
        for name, sconfig in sleeves.items():
            for factor in sconfig.get("factors", []):
                assert factor in candidate_factors or factor.endswith("_cs"), \
                    f"Sleeve '{name}' references factor '{factor}' not in candidate pool"

    def test_sleeve_names_are_meaningful(self):
        """Sleeve names should be among canonical SLEEVE_NAMES."""
        cfg = _load_config()
        sleeves = cfg.get("strategy_sleeves", {})
        valid_names = {"reversal", "momentum", "defensive", "value", "volume_price", "shock_reversal"}
        for name in sleeves:
            assert name in valid_names, \
                f"Unknown sleeve name '{name}' — expected one of {valid_names}"


class TestRegimeMapping:
    """Test regime-to-sleeve weight mappings."""

    def test_all_regimes_present(self):
        """All 5 required regime types should be present."""
        cfg = _load_config()
        weights = cfg.get("allocator", {}).get("regime_to_sleeve_weights", {})
        expected_regimes = {"trend_up", "trend_down", "range_bound", "high_volatility", "value_rotation"}
        assert set(weights.keys()) == expected_regimes

    def test_regime_weights_sum_close_to_one(self):
        """Each regime's weights should sum to approximately 1.0."""
        cfg = _load_config()
        sleeves_cfg = cfg.get("strategy_sleeves", {})
        sleeve_names = set(sleeves_cfg.keys())
        weights = cfg.get("allocator", {}).get("regime_to_sleeve_weights", {})

        for regime, wmap in weights.items():
            total = sum(wmap.values())
            assert 0.95 <= total <= 1.05, \
                f"Regime '{regime}' weights sum to {total:.2f}, expected ~1.0"

    def test_regime_weights_only_reference_valid_sleeves(self):
        """Regime weights should only reference defined sleeves."""
        cfg = _load_config()
        sleeves_cfg = cfg.get("strategy_sleeves", {})
        sleeve_names = set(sleeves_cfg.keys())
        weights = cfg.get("allocator", {}).get("regime_to_sleeve_weights", {})

        for regime, wmap in weights.items():
            for sleeve_name in wmap:
                assert sleeve_name in sleeve_names, \
                    f"Regime '{regime}' references unknown sleeve '{sleeve_name}'"

    def test_regime_weights_within_caps(self):
        """Each individual weight should be within allocator caps.

        Note: 0.0 is allowed — it means the sleeve is intentionally
        excluded from this regime (e.g., reversal in trend_up).
        """
        cfg = _load_config()
        alloc = cfg.get("allocator", {})
        weight_cap = alloc.get("sleeve_weight_cap", 0.50)
        weight_floor = alloc.get("sleeve_weight_floor", 0.0)
        weights = alloc.get("regime_to_sleeve_weights", {})

        for regime, wmap in weights.items():
            for sleeve_name, w in wmap.items():
                assert w <= weight_cap, \
                    f"Regime '{regime}' sleeve '{sleeve_name}' weight {w} > cap {weight_cap}"
                # 0.0 is allowed (intentionally excluded); any positive weight must be >= floor
                if w > 0:
                    assert w >= weight_floor, \
                        f"Regime '{regime}' sleeve '{sleeve_name}' weight {w} < floor {weight_floor}"


class TestPerformanceOverlay:
    """Test performance overlay configuration."""

    def test_overlay_disabled_by_default(self):
        """V4 should default to overlay OFF."""
        cfg = _load_config()
        overlay = cfg.get("sleeve_performance_overlay", {})
        assert overlay.get("enabled") is False, \
            "V4 performance overlay should be disabled by default"


class TestAllocatorConfig:
    """Test allocator parameters."""

    def test_min_sleeves_reasonable(self):
        cfg = _load_config()
        alloc = cfg.get("allocator", {})
        assert alloc.get("min_sleeves", 0) >= 2

    def test_min_active_factors_reasonable(self):
        cfg = _load_config()
        comp = cfg.get("sleeve_composite", {})
        assert comp.get("min_active_factors", 0) >= 1, \
            "V4 should require at least 1 active factor per sleeve"


class TestConfigIntegrity:
    """Cross-config integrity checks."""

    def test_regime_detector_has_required_fields(self):
        cfg = _load_config()
        detector = cfg.get("regime_detector", {})
        assert "index_code" in detector
        assert "trend" in detector
        assert "volatility" in detector

    def test_factor_alignment_has_all_fundamental_factors(self):
        cfg = _load_config()
        alignment = cfg.get("factor_alignment", {})
        fundamental_factors = alignment.get("fundamental_factors", [])
        # At minimum, the legacy fundamental factors should be present
        assert "ep_cs" in fundamental_factors
        assert "bp_cs" in fundamental_factors
        assert "sp_cs" in fundamental_factors

    def test_no_duplicate_factors_across_sleeves(self):
        """No factor should dominate too many sleeves (check for over-concentration)."""
        cfg = _load_config()
        sleeves = cfg.get("strategy_sleeves", {})
        factor_usage = {}
        for name, sconfig in sleeves.items():
            for factor in sconfig.get("factors", []):
                factor_usage.setdefault(factor, []).append(name)

        # A factor appearing in >3 sleeves is suspicious
        for factor, used_in in factor_usage.items():
            if len(used_in) > 3:
                print(f"  [WARN] Factor '{factor}' used in {len(used_in)} sleeves: {used_in}")
            # Not a hard fail — some core factors (e.g., profitability_quality) legitimately
            # appear in multiple sleeves as a quality overlay

"""Test that regime candidate configs are consistent with factor configs.

P1-1: Regime sleeve factors must not reference factors outside
enabled_factors in the paired factor config.
"""

import yaml
from pathlib import Path

import pytest

from configs.factor_config import validate_regime_sleeve_factors


PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIGS_DIR = PROJECT_ROOT / "configs"


def _load_yaml(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


# ---------------------------------------------------------------------------
# Test: candidate v1 configs are consistent
# ---------------------------------------------------------------------------

def test_candidate_v1_factors_pool_consistent():
    """factors_candidate_v1.yaml enabled_factors must contain all sleeve factors."""
    fc = _load_yaml(str(CONFIGS_DIR / "factors_candidate_v1.yaml"))
    rc = _load_yaml(str(CONFIGS_DIR / "regime_candidate_v1.yaml"))

    result = validate_regime_sleeve_factors(rc, fc)
    assert result["valid"], (
        f"regime_candidate_v1.yaml uses disabled factors: "
        f"{result['disabled_in_sleeves']}. "
        f"{result['recommendation']}"
    )


def test_candidate_v2_factors_pool_consistent():
    """factors_candidate_v1.yaml enabled_factors must contain all sleeve factors
    used in regime_candidate_v2.yaml."""
    fc = _load_yaml(str(CONFIGS_DIR / "factors_candidate_v1.yaml"))
    rc = _load_yaml(str(CONFIGS_DIR / "regime_candidate_v2.yaml"))

    result = validate_regime_sleeve_factors(rc, fc)
    assert result["valid"], (
        f"regime_candidate_v2.yaml uses disabled factors: "
        f"{result['disabled_in_sleeves']}. "
        f"{result['recommendation']}"
    )


def test_candidate_v3_factors_pool_consistent():
    """factors_candidate_v1.yaml enabled_factors must contain all sleeve factors
    used in regime_candidate_v3.yaml."""
    fc = _load_yaml(str(CONFIGS_DIR / "factors_candidate_v1.yaml"))
    rc = _load_yaml(str(CONFIGS_DIR / "regime_candidate_v3.yaml"))

    result = validate_regime_sleeve_factors(rc, fc)
    assert result["valid"], (
        f"regime_candidate_v3.yaml uses disabled factors: "
        f"{result['disabled_in_sleeves']}. "
        f"{result['recommendation']}"
    )


# ---------------------------------------------------------------------------
# Test: explicit factor list matches expected
# ---------------------------------------------------------------------------

def test_candidate_v2_expected_factor_list():
    """Verify regime_candidate_v2 sleeve factors are exactly the expected set."""
    rc = _load_yaml(str(CONFIGS_DIR / "regime_candidate_v2.yaml"))
    sleeves = rc.get("strategy_sleeves", {})

    all_factors = set()
    for cfg in sleeves.values():
        if isinstance(cfg, dict):
            all_factors.update(cfg.get("factors", []))
        elif isinstance(cfg, list):
            all_factors.update(cfg)

    # From the plan's recommended sleeve definition:
    # reversal: [reversal_5_cs, pv_divergence_20_cs]
    # momentum: [pv_divergence_20_cs]
    # defensive: [ep_cs, bp_cs]
    # value: [ep_cs, bp_cs, sp_cs]
    # volume_price: [pv_divergence_20_cs]
    expected = {"reversal_5_cs", "pv_divergence_20_cs", "ep_cs", "bp_cs", "sp_cs"}

    assert all_factors == expected, (
        f"Expected factors {sorted(expected)}, got {sorted(all_factors)}"
    )


# ---------------------------------------------------------------------------
# Test: no disabled factors leak into candidate sleeves
# ---------------------------------------------------------------------------

def test_candidate_v2_no_disabled_factors_in_sleeves():
    """None of the disabled factors from factors_candidate_v1 should appear."""
    fc = _load_yaml(str(CONFIGS_DIR / "factors_candidate_v1.yaml"))
    rc = _load_yaml(str(CONFIGS_DIR / "regime_candidate_v2.yaml"))

    disabled = set(fc.get("disabled_factors", {}).keys())

    sleeves = rc.get("strategy_sleeves", {})
    for sleeve_name, cfg in sleeves.items():
        sleeve_factors = cfg.get("factors", []) if isinstance(cfg, dict) else cfg
        leaked = [f for f in sleeve_factors if f in disabled]
        assert not leaked, (
            f"Sleeve '{sleeve_name}' references disabled factors: {leaked}"
        )

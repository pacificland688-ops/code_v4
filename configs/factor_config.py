"""
Shared factor configuration loader.

Centralises YAML config reading so that run_research.py,
validation/experiment_runner.py, and live/signal_service.py
all use the same logic.  No module should import from
run_research.py for config loading.

Default values EXACTLY match the current hardcoded values in
ICWeighting.__init__ and CrossSectionProcessor.__init__ so
that switching to this loader is a zero-behaviour-change
operation.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_factor_config(
    config_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Load factor and composite configuration from a YAML file.

    Parameters
    ----------
    config_path : str or Path, optional
        Path to a factors YAML file.  Defaults to ``configs/factors.yaml``.

    Returns
    -------
    dict
        Keys
        ----
        enabled_factors : list[str]
            Explicit whitelist.  Empty list = full candidate pool.
        composite_params : dict
            Parameters forwarded to ``ICWeighting.__init__``.
        cross_section_params : dict
            Parameters forwarded to ``CrossSectionProcessor`` factory.
    """
    path = Path(config_path or "configs/factors.yaml")

    if not path.exists():
        logger.warning("%s not found — using all factors + defaults", path)
        return _default_config()

    try:
        import yaml
        with open(path, "r", encoding="utf-8") as fh:
            config = yaml.safe_load(fh) or {}
    except Exception as exc:
        logger.warning("Failed to load %s: %s — using defaults", path, exc)
        return _default_config()

    enabled = config.get("enabled_factors", [])

    composite_params = _build_composite_params(config.get("composite", {}))
    cross_section_params = config.get("cross_section", {})
    candidate_policy = config.get("candidate_policy", {})

    return {
        "enabled_factors": enabled,
        "composite_params": composite_params,
        "cross_section_params": cross_section_params,
        "candidate_policy": candidate_policy,
    }


# ---------------------------------------------------------------------------
# Defaults (must match current hardcoded values)
# ---------------------------------------------------------------------------

def _default_config() -> Dict[str, Any]:
    return {
        "enabled_factors": [],
        "composite_params": _default_composite_params(),
        "cross_section_params": {},
    }


def _default_composite_params() -> Dict[str, Any]:
    """Default composite params — must match ICWeighting.__init__ defaults."""
    return {
        "ic_window_months": 12,
        "shrinkage": 0.3,
        "weight_cap": 0.3,
        "min_ic_obs": 20,
        "min_icir": 0.0,
        "hard_cap": False,
        "horizon": 5,
        "min_active_factors": 1,
        "coverage_gate_enabled": False,
        "sign_stability_check": True,
        "ic_method": "rank",
    }


def _build_composite_params(raw: dict) -> Dict[str, Any]:
    """Build composite_params from YAML, filling missing keys from defaults."""
    defaults = _default_composite_params()
    result = {}
    for key, default_val in defaults.items():
        result[key] = raw.get(key, default_val)
    # Also forward any extra keys the YAML may define (e.g. min_date_coverage)
    for key in raw:
        if key not in result:
            result[key] = raw[key]
    return result


# ---------------------------------------------------------------------------
# Config consistency validation
# ---------------------------------------------------------------------------

def validate_regime_sleeve_factors(
    regime_config: Dict[str, Any],
    factor_config: Dict[str, Any],
) -> Dict[str, Any]:
    """Check that regime sleeve factors are consistent with enabled_factors.

    Returns a dict with:
        valid: bool — True if all sleeve factors are in enabled_factors
        disabled_in_sleeves: List[str] — factors in sleeves but NOT enabled
        sleeves_using_disabled: Dict[str, List[str]] — per-sleeve breakdown
        recommendation: str — human-readable action

    This is used to catch the P1-1 issue: regime configs referencing
    factors that have been removed from the candidate factor pool.
    """
    enabled_factors = factor_config.get("enabled_factors", [])
    if not enabled_factors:
        return {
            "valid": True,
            "disabled_in_sleeves": [],
            "sleeves_using_disabled": {},
            "recommendation": "No enabled_factors defined — cannot validate (non-blocking)",
        }

    enabled_set = set(enabled_factors)
    sleeves = regime_config.get("strategy_sleeves", {})

    disabled_in_sleeves = []
    sleeves_using_disabled: Dict[str, List[str]] = {}

    for sleeve_name, cfg in sleeves.items():
        if isinstance(cfg, dict):
            sleeve_factors = cfg.get("factors", [])
        elif isinstance(cfg, list):
            sleeve_factors = cfg
        else:
            continue

        for fname in sleeve_factors:
            if fname not in enabled_set:
                disabled_in_sleeves.append(fname)
                sleeves_using_disabled.setdefault(sleeve_name, []).append(fname)

    disabled_in_sleeves = sorted(set(disabled_in_sleeves))

    if disabled_in_sleeves:
        recommendation = (
            f"Remove {len(disabled_in_sleeves)} disabled factor(s) from regime sleeves "
            f"or add them to enabled_factors in the factor config. "
            f"Affected sleeves: {list(sleeves_using_disabled.keys())}"
        )
        return {
            "valid": False,
            "disabled_in_sleeves": disabled_in_sleeves,
            "sleeves_using_disabled": sleeves_using_disabled,
            "recommendation": recommendation,
        }

    return {
        "valid": True,
        "disabled_in_sleeves": [],
        "sleeves_using_disabled": {},
        "recommendation": "All sleeve factors are in enabled_factors — OK",
    }


def validate_candidate_policy(
    factor_config: Dict[str, Any],
) -> Dict[str, Any]:
    """Check formal candidate policy compliance.

    When ``candidate_policy.formal_candidate`` is true:
        - ``enabled_factors`` MUST be non-empty.
        - If ``require_non_empty_enabled_factors`` is true, an empty
          enabled list is a hard block.

    Returns
    -------
    dict
        ``valid``: bool — True if candidate policy is satisfied
        ``blocked_reason``: str or None — explanation when invalid
        ``min_gate_pass_alpha_factors``: int — threshold from config
    """
    policy = factor_config.get("candidate_policy", {})
    if not policy:
        return {
            "valid": True,
            "blocked_reason": None,
            "min_gate_pass_alpha_factors": 3,
        }

    formal = policy.get("formal_candidate", False)
    require_nonempty = policy.get("require_non_empty_enabled_factors", False)
    min_pass = policy.get("min_gate_pass_alpha_factors", 3)

    if not formal:
        return {
            "valid": True,
            "blocked_reason": None,
            "min_gate_pass_alpha_factors": min_pass,
        }

    enabled = factor_config.get("enabled_factors", [])

    if not enabled and require_nonempty:
        return {
            "valid": False,
            "blocked_reason": (
                "NO_ALPHA_SOURCE: formal_candidate=true but "
                "enabled_factors is empty. At least "
                f"{min_pass} gate-PASS alpha factors required."
            ),
            "min_gate_pass_alpha_factors": min_pass,
        }

    if len(enabled) < min_pass:
        return {
            "valid": False,
            "blocked_reason": (
                f"INSUFFICIENT_ALPHA_SOURCE: formal_candidate=true "
                f"requires >= {min_pass} gate-PASS alpha factors, "
                f"but enabled_factors has only {len(enabled)}."
            ),
            "min_gate_pass_alpha_factors": min_pass,
        }

    return {
        "valid": True,
        "blocked_reason": None,
        "min_gate_pass_alpha_factors": min_pass,
    }

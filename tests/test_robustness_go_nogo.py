"""Go/No-Go robustness checklist coverage — Batch 6 severity tests."""

import numpy as np
from validation.robustness import RobustnessTester


def test_go_nogo_checks_recent_oos_optimizer_fallback():
    tester = RobustnessTester(lambda **kwargs: {})
    base = {
        "annualized_excess_return": 0.05,
        "information_ratio": 0.5,
        "max_drawdown": -0.10,
        "avg_turnover": 0.20,
        "sharpe_ratio": 0.8,
        "optimizer_fallback_rate": 0.05,
    }
    cost_2x = {
        "annualized_excess_return": 0.01,
    }
    recent_oos = {
        "annualized_excess_return": 0.04,
        "n_periods": 20,
        "optimizer_fallback_rate": 0.30,
    }

    result = tester.go_nogo_check(
        base,
        cost_2x_result=cost_2x,
        recent_oos_result=recent_oos,
    )

    check = result["checks"]["recent_oos_optimizer_fallback"]
    assert check["pass"] is False
    assert check["value"] == 0.30
    assert result["verdict"] == "NO-GO"


# ===================================================================
# Batch 6: Warning/hard severity semantics
# ===================================================================

def test_warning_check_does_not_force_no_go():
    """A failing WARNING check must not cause NO-GO."""
    tester = RobustnessTester(lambda **kwargs: {})

    # All hard checks pass, but warning fails
    base = {
        "annualized_excess_return": 0.05,
        "information_ratio": 0.5,
        "max_drawdown": -0.10,
        "avg_turnover": 0.20,
        "sharpe_ratio": 0.8,
        "optimizer_fallback_rate": 0.05,
        "optimizer_relaxation_rate": 0.30,  # > 0.20 → WARNING fail
    }
    cost_2x = {"annualized_excess_return": 0.01}

    result = tester.go_nogo_check(base, cost_2x_result=cost_2x)

    # Warning check should be present and failing
    warn_check = result["checks"].get("optimizer_relaxation")
    assert warn_check is not None
    assert warn_check["pass"] is False
    assert warn_check["severity"] == "warning"

    # But verdict must still be GO (hard checks all pass)
    assert result["verdict"] == "GO", (
        f"Warning checks should not force NO-GO, got {result['verdict']}"
    )

    # Warning checks should be in separate dict
    assert "warning_checks" in result
    assert "optimizer_relaxation" in result["warning_checks"]

    # warning_fail count
    assert result.get("n_warning_fail", 0) >= 1


def test_unknown_fallback_rate_remains_hard_no_go():
    """Unknown fallback rate must be HARD severity → forces NO-GO."""
    tester = RobustnessTester(lambda **kwargs: {})

    base = {
        "annualized_excess_return": 0.05,
        "information_ratio": 0.5,
        "max_drawdown": -0.10,
        "avg_turnover": 0.20,
        "sharpe_ratio": 0.8,
        "optimizer_fallback_rate": 0.05,
        "opt_fallback_reasons": {
            "mystery_error_xyz": 8,  # unknown reason
            "weird_solver_thing": 2,  # unknown reason
        },
        "opt_n_total": 50,
    }

    result = tester.go_nogo_check(base)

    # The unknown rate check should exist and be hard
    unknown_check = result["checks"].get("fallback_unknown_rate")
    assert unknown_check is not None, "fallback_unknown_rate check must exist"
    assert unknown_check["severity"] == "hard", (
        f"Unknown fallback rate must be HARD, got {unknown_check.get('severity')}"
    )
    # 10/50 = 0.20 > 0.05 → should fail
    assert unknown_check["pass"] is False

    # This should force NO-GO
    assert result["verdict"] == "NO-GO", (
        "Unknown fallback rate fail must force NO-GO"
    )


def test_all_checks_have_severity():
    """Every check in the result must have a 'severity' field."""
    tester = RobustnessTester(lambda **kwargs: {})

    base = {
        "annualized_excess_return": 0.05,
        "information_ratio": 0.5,
        "max_drawdown": -0.10,
        "avg_turnover": 0.20,
        "sharpe_ratio": 0.8,
        "optimizer_fallback_rate": 0.05,
        "opt_fallback_reasons": {"missing_mu": 1},
        "opt_n_total": 10,
    }

    result = tester.go_nogo_check(base)

    for check_name, check_data in result["checks"].items():
        assert "severity" in check_data, (
            f"Check '{check_name}' missing severity field"
        )
        assert check_data["severity"] in ("hard", "warning"), (
            f"Check '{check_name}' has invalid severity: {check_data['severity']}"
        )


def test_hard_checks_separated_from_warnings():
    """hard_checks and warning_checks must be separate dicts."""
    tester = RobustnessTester(lambda **kwargs: {})

    base = {
        "annualized_excess_return": 0.05,
        "information_ratio": 0.5,
        "max_drawdown": -0.10,
        "avg_turnover": 0.20,
        "sharpe_ratio": 0.8,
        "optimizer_fallback_rate": 0.05,
        "optimizer_relaxation_rate": 0.15,
        "turnover_p95": 0.55,
    }

    result = tester.go_nogo_check(base)

    assert "hard_checks" in result
    assert "warning_checks" in result
    assert len(result["hard_checks"]) > 0
    # Verify warning checks are NOT in hard_checks
    for wkey in result["warning_checks"]:
        assert wkey not in result["hard_checks"], (
            f"Warning check '{wkey}' leaked into hard_checks"
        )
    # Verify all hard checks have severity='hard'
    for hkey, hcheck in result["hard_checks"].items():
        assert hcheck["severity"] == "hard", (
            f"Hard check '{hkey}' has severity={hcheck.get('severity')}"
        )


def test_nan_guard_causes_no_go():
    """NaN in key metrics must force NO-GO."""
    tester = RobustnessTester(lambda **kwargs: {})

    base = {
        "annualized_excess_return": float("nan"),
        "information_ratio": float("nan"),
        "max_drawdown": -0.10,
        "avg_turnover": 0.20,
        "sharpe_ratio": float("nan"),
    }

    result = tester.go_nogo_check(base)
    assert result["verdict"] == "NO-GO", (
        "NaN in key metrics must force NO-GO"
    )

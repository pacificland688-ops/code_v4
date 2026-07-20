"""Unit tests: severity ladder (active-member P4), dual commonality,
reversal context, frozen-gate identity."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from live.photoresist_panic.commonality import (  # noqa: E402
    INSUFFICIENT_DATA, MIXED, SECTOR_WIDE, STOCK_DRIVEN, classify_commonality,
    dual_commonality,
)
from live.photoresist_panic.common import (  # noqa: E402
    load_yaml, validate_frozen_gate, wilson_interval,
)
from live.photoresist_panic.reversal import assess_reversal_context  # noqa: E402
from live.photoresist_panic.severity import classify_severity  # noqa: E402
from live.photoresist_panic.signal_engine import active_stress_metrics  # noqa: E402

SEVERITY_CONFIG = {
    "p1_watch_percentile": 0.20,
    "p3_absolute_return": -0.08,
    "p3_percentile": 0.05,
    "p4_breadth": 0.75,
    "p4_amount_ratio": 1.5,
    "p4_requires_limit_down_or_volume": True,
}

COMMONALITY_CONFIG = {
    "sector_wide_min_down": 3,
    "stock_driven_contribution_cap": 0.50,
    "stock_driven_dominance_ratio": 2.0,
    "min_valid_components": 3,
}

REVERSAL_CONFIG = {
    "eligible_regimes": ["bull", "neutral"],
    "blocked_regimes": ["bear", "unknown"],
    "historical_reference": {
        "label": "test", "sample_size": 21, "hits_low": 14, "hits_high": 16,
        "wilson_confidence": 0.95, "evidence_grade": "初步", "note": "n/a",
    },
}


# ── Severity ────────────────────────────────────────────────────────────
def _sev(triggered, ret5, pct, breadth=0.5, amount=1.0, limit_down=0):
    return classify_severity(triggered, ret5, pct,
                             active_down_breadth_5d=breadth,
                             active_amount_ratio_20d=amount,
                             active_limit_down_count=limit_down,
                             config=SEVERITY_CONFIG)


def test_severity_p0_p1_p2_p3_p4_ladder():
    assert _sev(False, 0.01, 0.9)["level"] == "P0"
    assert _sev(False, -0.02, 0.15)["level"] == "P1"
    assert _sev(True, -0.055, 0.08)["level"] == "P2"
    assert _sev(True, -0.09, 0.08)["level"] == "P3"       # absolute leg
    assert _sev(True, -0.055, 0.03)["level"] == "P3"      # percentile leg
    assert _sev(True, -0.09, 0.03, breadth=0.80)["level"] == "P3"
    assert _sev(True, -0.09, 0.03, amount=1.6)["level"] == "P4"
    assert _sev(True, -0.09, 0.03, limit_down=1)["level"] == "P4"


def test_p4_breadth_alone_allowed_only_when_confirmation_disabled():
    config = {**SEVERITY_CONFIG, "p4_requires_limit_down_or_volume": False}
    result = classify_severity(
        True, -0.09, 0.03, 0.80, 1.0, 0, config
    )
    assert result["level"] == "P4"


def test_severity_never_reclassifies_gate():
    # a non-triggered day can never be P2+ regardless of magnitude
    assert _sev(False, -0.12, 0.001)["level"] == "P1"
    # a triggered day is at least P2 even with benign percentile
    assert _sev(True, -0.051, 0.5)["level"] == "P2"


def test_p4_stress_from_active_members_even_if_gate_excluded_them():
    """A limit-down member filtered out of the eligible basket still drives P4."""
    result = _sev(True, -0.087, 0.024, breadth=0.70, amount=0.46, limit_down=1)
    assert result["level"] == "P4"
    assert any("跌停" in reason for reason in result["reasons"])


def test_active_stress_keeps_denominator_and_ignores_stale_suspension_amount():
    codes = ["A.SZ", "B.SZ", "C.SZ", "D.SZ"]
    rows = []
    for code in codes:
        last_day = 21 if code == "D.SZ" else 22
        for day in range(1, last_day + 1):
            rows.append({
                "ts_code": code,
                "trade_date": day,
                "pct_chg": -1.0 if day == 22 else 0.0,
                "amount": 10_000.0 if code == "D.SZ" and day == 21 else 100.0,
                "close": 10.0,
            })
    result = active_stress_metrics(
        pd.DataFrame(rows), codes, 22, breadth_window=1
    )
    assert result["active_down_breadth_5d"] == pytest.approx(0.75)
    assert result["active_breadth_member_coverage"] == pytest.approx(0.75)
    assert result["active_amount_ratio_20d"] == pytest.approx(1.0)
    assert result["active_amount_member_coverage"] == pytest.approx(0.75)


# ── Commonality ─────────────────────────────────────────────────────────
def _snapshot(rets, codes=None, valid=None):
    codes = codes or [f"S{i}.SZ" for i in range(len(rets))]
    valid = valid if valid is not None else [np.isfinite(r) for r in rets]
    return pd.DataFrame({
        "ts_code": codes,
        "name": [f"s{i}" for i in range(len(rets))],
        "ret_5d": rets,
        "valid": valid,
    })


def test_commonality_sector_wide():
    result = classify_commonality(
        _snapshot([-0.06, -0.05, -0.055, -0.04]), -0.05, COMMONALITY_CONFIG)
    assert result["classification"] == SECTOR_WIDE
    assert result["down_count"] == 4
    assert result["reversal_credibility_downgraded"] is False


def test_commonality_mixed():
    result = classify_commonality(
        _snapshot([-0.06, -0.05, 0.02, 0.03]), -0.015, COMMONALITY_CONFIG)
    assert result["classification"] == MIXED


def test_commonality_stock_driven():
    result = classify_commonality(
        _snapshot([-0.20, -0.02, -0.01, -0.015]), -0.06, COMMONALITY_CONFIG)
    assert result["classification"] == STOCK_DRIVEN
    assert result["max_contributor"] == "S0.SZ"
    assert result["max_contribution_share"] > 0.5
    assert result["reversal_credibility_downgraded"] is True


def test_commonality_insufficient_data():
    result = classify_commonality(
        _snapshot([-0.06, np.nan, np.nan, np.nan]), -0.06, COMMONALITY_CONFIG)
    assert result["classification"] == INSUFFICIENT_DATA


def test_dual_commonality_two_scopes():
    """theme uses ALL active members; signal uses only gate-eligible ones."""
    snapshot = _snapshot([-0.13, -0.10, -0.10, -0.06],
                         codes=["A.SZ", "B.SZ", "C.SZ", "D.SZ"])
    result = dual_commonality(snapshot, ["A.SZ", "B.SZ", "C.SZ"], -0.087,
                              COMMONALITY_CONFIG)
    theme, signal = result["theme_commonality"], result["signal_commonality"]
    assert theme["scope"] == "all_active_members"
    assert theme["down_count"] == 4
    assert theme["n_valid_components"] == 4
    assert theme["classification"] == SECTOR_WIDE
    assert signal["scope"] == "signal_eligible_members"
    assert signal["n_valid_components"] == 3
    assert signal["down_count"] == 3
    assert signal["basket_ret_5d"] == -0.087


def test_dual_commonality_insufficient_signal_members():
    snapshot = _snapshot([-0.06, -0.05, -0.04, -0.03],
                         codes=["A.SZ", "B.SZ", "C.SZ", "D.SZ"])
    result = dual_commonality(snapshot, ["A.SZ", "B.SZ"], -0.05,
                              COMMONALITY_CONFIG)
    assert result["signal_commonality"]["classification"] == INSUFFICIENT_DATA
    assert result["theme_commonality"]["classification"] == SECTOR_WIDE


# ── Reversal context ────────────────────────────────────────────────────
def test_reversal_status_by_regime():
    assert assess_reversal_context("bull", True, REVERSAL_CONFIG)[
        "reversal_status"] == "REVERSAL_CANDIDATE"
    assert assess_reversal_context("neutral", True, REVERSAL_CONFIG)[
        "reversal_status"] == "REVERSAL_CANDIDATE_LOW_SAMPLE"
    assert assess_reversal_context("bear", True, REVERSAL_CONFIG)[
        "reversal_status"] == "REVERSAL_DISABLED"
    assert assess_reversal_context("unknown", True, REVERSAL_CONFIG)[
        "reversal_status"] == "REVERSAL_DISABLED"
    assert assess_reversal_context("bull", False, REVERSAL_CONFIG)[
        "reversal_status"] == "NOT_APPLICABLE"


def test_reversal_reports_wilson_interval_not_point_probability():
    result = assess_reversal_context("bull", True, REVERSAL_CONFIG)
    evidence = result["historical_evidence"]
    lo, hi = evidence["wilson_ci_95"]
    assert 0.40 < lo < 0.50
    assert 0.85 < hi < 0.95
    assert evidence["sample_size"] == 21
    assert "probability" not in result


def test_wilson_interval_bounds():
    lo, hi = wilson_interval(0, 10)
    assert lo == 0.0 and hi < 0.35
    lo, hi = wilson_interval(10, 10)
    assert hi == 1.0 and lo > 0.65


# ── Frozen gate identity ────────────────────────────────────────────────
def test_live_config_matches_frozen_research_gate():
    live = load_yaml(ROOT / "configs" / "photoresist_panic_live.yaml")
    research = load_yaml(ROOT / "configs" / "photoresist_panic_research.yaml")
    validate_frozen_gate(live, research)  # must not raise


def test_frozen_gate_drift_detected():
    live = load_yaml(ROOT / "configs" / "photoresist_panic_live.yaml")
    research = load_yaml(ROOT / "configs" / "photoresist_panic_research.yaml")
    live["frozen_gate"]["absolute_threshold_pct"] = -4.0
    with pytest.raises(ValueError, match="drift"):
        validate_frozen_gate(live, research)


def test_rolling_quantile_uses_shifted_history_only():
    """The gate quantile at day t must exclude day t (strict shift(1))."""
    from validate_photoresist_panic_thresholds import build_threshold_gate

    n = 300
    basket = pd.DataFrame({
        "trade_date": range(20240001, 20240001 + n),
        "basket_ret_1d": [0.0] * n,
        "basket_ret_5d": [0.01] * (n - 1) + [-0.50],  # extreme crash on last day
        "down_stock_ratio": [1.0] * n,
        "median_amount_ratio_20d": [1.0] * n,
    })
    gate_config = {
        "return_window_days": 5, "absolute_threshold_pct": -5.0,
        "quantile_window_days": 250, "quantile_threshold_pct": 10.0,
        "breadth_window_days": 5, "breadth_threshold_pct": 50.0,
    }
    gated = build_threshold_gate(basket, "primary_5d", gate_config)
    last = gated.iloc[-1]
    assert last["validation_quantile"] == pytest.approx(0.01)
    assert bool(last["validation_gate_triggered"]) is True

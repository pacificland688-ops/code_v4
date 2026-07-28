"""
Hard Gate Checker — 13 Pre-Registered Rejection Criteria
==========================================================
Evaluates a candidate volume/turnover indicator against the 13 hard
constraints.  ANY single failure → candidate REJECTED.  Failures cannot
be "fixed" by adding more conditions.

Constraints (pre-registered, order-independent):
  1. Only diagnostic mode — does not change R0–R3 results
  2. At most one candidate indicator tested simultaneously
  3. Continuous monotonic relationship tested before threshold search
  4. All attempts counted toward multiple-testing tally
  5. Thresholds determined only from training windows
  6. Validation period cannot be re-tested after viewing results
  7. Year-over-year paired delta direction consistency
  8. Median net return must not worsen
  9. Left-tail (10th percentile) loss must not expand
  10. Improvement not dominated by top-3 winner events
  11. Jackknife: removing any single event cannot reverse conclusion
  12. Must retain improvement under 100bp round-trip cost
  13. Any single hard gate failure → candidate rejected immediately

Design: each constraint is a separate function returning (passed: bool, detail: str).
The checker runs ALL constraints and produces a comprehensive failure report.
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from typing import Callable

import numpy as np

warnings.filterwarnings("ignore")


@dataclass
class GateResult:
    """Result of a single hard-gate check."""
    gate_name: str
    passed: bool
    detail: str = ""
    evidence: dict | None = None  # quantitative evidence for audit


@dataclass
class HardGateResult:
    """Aggregate result across all 13 gates."""
    candidate_name: str
    passed: bool  # True only if ALL gates pass
    results: list[GateResult] = field(default_factory=list)
    n_passed: int = 0
    n_failed: int = 0
    failure_gates: list[str] = field(default_factory=list)

    def is_pass(self) -> bool:
        return self.passed

    def failure_summary(self) -> str:
        if self.passed:
            return f"ALL {self.n_passed} gates PASSED"
        lines = [f"{self.n_failed} gate(s) FAILED for '{self.candidate_name}':"]
        for r in self.results:
            if not r.passed:
                lines.append(f"  [{r.gate_name}] {r.detail}")
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════
# Individual gate functions
# ═══════════════════════════════════════════════════════════════════════════

def _gate_diagnostic_only(candidate_name: str,
                          trade_ledger_with: pd.DataFrame | None = None,
                          trade_ledger_without: pd.DataFrame | None = None) -> GateResult:
    """Gate 1: Confirm R0-R3 trade ledger is byte-identical with/without diagnostics.

    If trade ledgers are provided, they must be identical.  Otherwise,
    assume PASS (structural invariant — VolumeFeatures are never read by rules).
    """
    if trade_ledger_with is not None and trade_ledger_without is not None:
        import pandas as pd
        try:
            pd.testing.assert_frame_equal(
                trade_ledger_with.sort_values(["signal_id", "rule_id", "cost_bps"]).reset_index(drop=True),
                trade_ledger_without.sort_values(["signal_id", "rule_id", "cost_bps"]).reset_index(drop=True),
            )
            return GateResult("diagnostic_only", True,
                              "Trade ledgers are byte-identical with/without volume diagnostics.")
        except AssertionError as e:
            return GateResult("diagnostic_only", False,
                              f"Trade ledgers DIFFER — volume features are affecting R0-R3! {str(e)[:200]}")
    return GateResult(
        "diagnostic_only", False,
        "Missing independent pre/post-diagnostics trade-ledger evidence."
    )


def _gate_single_candidate(active_candidates: list[str],
                           candidate_name: str) -> GateResult:
    """Gate 2: At most one candidate indicator tested at a time."""
    if len(active_candidates) == 0:
        return GateResult("single_candidate", True,
                          f"Only candidate: '{candidate_name}'")
    if len(active_candidates) == 1 and active_candidates[0] == candidate_name:
        return GateResult("single_candidate", True,
                          f"Only candidate: '{candidate_name}'")
    return GateResult("single_candidate", False,
                      f"Multiple active candidates: {active_candidates}. "
                      f"Only '{candidate_name}' allowed.")


def _gate_monotonic_relationship(feature_values: np.ndarray,
                                 net_returns: np.ndarray,
                                 min_spearman_r: float = 0.0,
                                 min_n: int = 10) -> GateResult:
    """Gate 3: Test continuous monotonic relationship (Spearman rank correlation).

    Requires |rho| > 0 AND p < 0.10 (suggestive, not confirmatory at this stage).
    The direction (positive or negative) must be economically interpretable.
    """
    valid = np.isfinite(feature_values) & np.isfinite(net_returns)
    x = feature_values[valid]
    y = net_returns[valid]

    if len(x) < min_n:
        return GateResult("monotonic_relationship", False,
                          f"Insufficient data: {len(x)} valid pairs < {min_n} minimum",
                          {"n_valid": len(x)})

    # Spearman rank correlation
    try:
        from scipy.stats import spearmanr
        rho, pval = spearmanr(x, y)
    except Exception:
        # Fallback: numpy corrcoef on ranks (also handles missing scipy)
        xr = np.argsort(np.argsort(x))
        yr = np.argsort(np.argsort(y))
        rho = np.corrcoef(xr, yr)[0, 1]
        pval = np.nan

    # Require POSITIVE correlation (candidate is pre-registered as
    # "high amount keeps trades").  Negative correlation = FAIL.
    # When scipy is unavailable (pval=NaN), fail closed — refuse to pass.
    if np.isnan(pval):
        passed = False
    else:
        passed = rho > min_spearman_r and pval < 0.10
    detail = (f"Spearman rho={rho:.4f}, p={pval:.4f} "
              f"(n={len(x)}). {'Monotonic' if passed else 'Not monotonic'} "
              f"at p<0.10 threshold, direction=positive required.")

    return GateResult("monotonic_relationship", passed, detail,
                      {"rho": float(rho), "p_value": float(pval) if not np.isnan(pval) else None, "n": len(x)})


def _gate_multiple_testing_tally(total_tests: int,
                                 max_bonferroni: int = 5) -> GateResult:
    """Gate 4: Multiple-testing tally.  Warns if too many candidates tested."""
    # This gate always passes but records the count for the rejection ledger.
    if total_tests <= max_bonferroni:
        return GateResult("multiple_testing_tally", True,
                          f"Total candidates tested: {total_tests} ≤ {max_bonferroni} (Bonferroni-safe)")
    return GateResult("multiple_testing_tally", False,
                      f"Total candidates tested: {total_tests} > {max_bonferroni}. "
                      f"Bonferroni correction required: α_effective = 0.05/{total_tests} = {0.05/total_tests:.4f}",
                      {"bonferroni_alpha": 0.05 / total_tests})


def _gate_threshold_from_training(threshold_source: str) -> GateResult:
    """Gate 5: Thresholds must be determined from training windows only."""
    if threshold_source == "training":
        return GateResult("threshold_from_training", True,
                          "Thresholds derived from training window only.")
    return GateResult("threshold_from_training", False,
                      f"Threshold source is '{threshold_source}', not 'training'.")


def _gate_median_not_worse(baseline_median: float,
                           candidate_median: float,
                           tolerance: float = 0.0) -> GateResult:
    """Gate 8: Median net return must not worsen (within tolerance)."""
    delta = candidate_median - baseline_median
    passed = delta >= tolerance
    detail = (f"Baseline median={baseline_median:.6f}, "
              f"Candidate median={candidate_median:.6f}, delta={delta:.6f}")
    return GateResult("median_not_worse", passed, detail,
                      {"baseline": float(baseline_median), "candidate": float(candidate_median), "delta": float(delta)})


def _gate_left_tail_not_wider(baseline_returns: np.ndarray,
                              candidate_returns: np.ndarray,
                              quantile: float = 0.10) -> GateResult:
    """Gate 9: Left-tail (10th percentile) loss must not expand."""
    valid = np.isfinite(baseline_returns) & np.isfinite(candidate_returns)
    if valid.sum() == 0:
        return GateResult(
            "left_tail_not_wider", False, "No valid paired OOS returns."
        )
    b_tail = np.percentile(baseline_returns[valid], quantile * 100)
    c_tail = np.percentile(candidate_returns[valid], quantile * 100)
    delta = c_tail - b_tail
    passed = delta >= 0  # candidate tail is less negative or equal
    detail = (f"Baseline {quantile:.0%}ile={b_tail:.6f}, "
              f"Candidate {quantile:.0%}ile={c_tail:.6f}, delta={delta:.6f}. "
              f"{'Tail NOT worse' if passed else 'Tail EXPANDED — REJECTED'}")
    return GateResult("left_tail_not_wider", passed, detail,
                      {"baseline": float(b_tail), "candidate": float(c_tail), "delta": float(delta)})


def _gate_top3_not_dominant(baseline_returns: np.ndarray,
                            candidate_returns: np.ndarray,
                            max_contribution_ratio: float = 0.50) -> GateResult:
    """Gate 10: Improvement must not be dominated by top-3 winner events.

    Computes: fraction of POSITIVE improvement (sum of positive deltas)
    contributed by the 3 largest positive deltas.  If > max_contribution_ratio,
    the improvement is driven by outliers, not broad-based.
    """
    valid = np.isfinite(baseline_returns) & np.isfinite(candidate_returns)
    if valid.sum() < 5:
        return GateResult("top3_not_dominant", False,
                          f"Insufficient data: {valid.sum()} valid pairs < 5")
    deltas = candidate_returns[valid] - baseline_returns[valid]
    # Measure contribution to POSITIVE improvement only
    positive_deltas = deltas[deltas > 0]
    total_positive = float(np.sum(positive_deltas))
    if total_positive <= 0:
        return GateResult("top3_not_dominant", False,
                          f"No positive improvement to attribute (total positive delta={total_positive:.6f})")
    if len(positive_deltas) < 3:
        return GateResult("top3_not_dominant", False,
                          f"Fewer than 3 events with positive delta ({len(positive_deltas)})")
    top3 = np.sort(positive_deltas)[-3:]
    top3_share = float(np.sum(top3) / total_positive)
    # Boundary is inclusive; tolerate binary floating-point noise at exactly 50%.
    passed = top3_share <= max_contribution_ratio + 1e-12
    detail = (f"Top-3 winners contribute {top3_share:.1%} of total positive improvement. "
              f"{'Acceptable' if passed else 'DOMINATED by top 3 — REJECTED'}")
    return GateResult("top3_not_dominant", passed, detail,
                      {"top3_share": top3_share, "threshold": max_contribution_ratio})


def _gate_jackknife_stable(baseline_returns: np.ndarray,
                           candidate_returns: np.ndarray,
                           sign_sensitivity: float = 1.0) -> GateResult:
    """Gate 11: Removing any single event must not reverse the conclusion.

    ALL jackknife samples must retain the same sign of mean delta.
    Even a single reversal → REJECTED.  (Frozen spec: "剔除任一事件不能反转")
    """
    valid_mask = np.isfinite(baseline_returns) & np.isfinite(candidate_returns)
    b = baseline_returns[valid_mask]
    c = candidate_returns[valid_mask]
    n = len(b)
    if n < 5:
        return GateResult("jackknife_stable", False,
                          f"Insufficient data: {n} valid pairs < 5")

    full_delta = np.mean(c - b)
    if np.isnan(full_delta):
        return GateResult("jackknife_stable", False, "Full delta is NaN")

    signs = []
    for i in range(n):
        mask = np.ones(n, dtype=bool)
        mask[i] = False
        jk_delta = np.mean(c[mask] - b[mask])
        signs.append(np.sign(jk_delta))

    sign_majority = np.sign(full_delta)
    n_same = sum(1 for s in signs if s == sign_majority)
    consistency = n_same / n

    passed = consistency >= sign_sensitivity
    detail = (f"Jackknife: {n_same}/{n} ({consistency:.1%}) retain same sign as full delta. "
              f"{'Stable' if passed else 'UNSTABLE — conclusion driven by single event(s)'}")
    return GateResult("jackknife_stable", passed, detail,
                      {"consistency": consistency, "full_delta": float(full_delta), "n": n})


def _gate_cost_100bp_improves(baseline_net_100bp: np.ndarray,
                              candidate_net_100bp: np.ndarray) -> GateResult:
    """Gate 12: Improvement must be retained under 100bp round-trip cost."""
    valid = np.isfinite(baseline_net_100bp) & np.isfinite(candidate_net_100bp)
    if valid.sum() == 0:
        return GateResult("cost_100bp_improves", False, "No valid paired returns at 100bp.")
    b_mean = float(np.mean(baseline_net_100bp[valid]))
    c_mean = float(np.mean(candidate_net_100bp[valid]))
    delta = c_mean - b_mean
    passed = delta > 0
    detail = (f"100bp: baseline mean={b_mean:.6f}, candidate mean={c_mean:.6f}, "
              f"delta={delta:.6f}. {'Improves' if passed else 'Does NOT improve — REJECTED'}")
    return GateResult("cost_100bp_improves", passed, detail,
                      {"baseline_mean": b_mean, "candidate_mean": c_mean, "delta": delta})


def _gate_year_consistency(
    returns_by_year: dict[int, tuple[np.ndarray, np.ndarray]],
    min_consistent_ratio: float = 1.0,
) -> GateResult:
    """Gate 7: ALL years must show positive improvement (candidate > baseline).

    Frozen spec: "不同年份的配对收益方向必须基本一致" — the improvement
    direction must be positive AND consistent.  Any year with negative
    delta → REJECTED.
    """
    yearly_deltas = {}
    for yr, (b, c) in returns_by_year.items():
        valid = np.isfinite(b) & np.isfinite(c)
        if valid.sum() < 2:
            continue
        delta = float(np.mean(c[valid] - b[valid]))
        yearly_deltas[yr] = delta

    if len(yearly_deltas) < 2:
        return GateResult("year_consistency", False,
                          f"Insufficient years with data: {len(yearly_deltas)} < 2")

    n_positive = sum(1 for d in yearly_deltas.values() if d > 0)
    n_total = len(yearly_deltas)
    ratio = n_positive / n_total

    passed = ratio >= min_consistent_ratio
    detail = (f"{n_positive}/{n_total} years show positive improvement. "
              f"Deltas by year: { {k: f'{v:.6f}' for k, v in yearly_deltas.items()} }. "
              f"{'ALL years positive — PASS' if passed else 'Some years are NEGATIVE — REJECTED'}")
    return GateResult("year_consistency", passed, detail,
                      {"yearly_deltas": {str(k): v for k, v in yearly_deltas.items()},
                       "n_positive": n_positive, "n_total": n_total})


def _gate_viewed_once(firewall_sealed: bool) -> GateResult:
    """Gate 6: Validation period cannot be re-tested after viewing results."""
    return GateResult("viewed_once", firewall_sealed,
                      "Firewall is sealed — validation results viewed, cannot retest."
                      if firewall_sealed else
                      "Firewall not yet sealed — validation pending.")


# ═══════════════════════════════════════════════════════════════════════════
# Main checker
# ═══════════════════════════════════════════════════════════════════════════

class HardGateChecker:
    """Runs all 13 hard gates against a candidate and returns the verdict."""

    def __init__(self, candidate_name: str, firewall_sealed: bool = False):
        self.candidate_name = candidate_name
        self.firewall_sealed = firewall_sealed
        self.results: list[GateResult] = []

    # ── Gate 1 ──────────────────────────────────────────────────────────
    def check_diagnostic_only(self, trade_ledger_with=None,
                              trade_ledger_without=None) -> GateResult:
        r = _gate_diagnostic_only(self.candidate_name, trade_ledger_with, trade_ledger_without)
        self.results.append(r)
        return r

    # ── Gate 2 ──────────────────────────────────────────────────────────
    def check_single_candidate(self, active_candidates: list[str]) -> GateResult:
        r = _gate_single_candidate(active_candidates, self.candidate_name)
        self.results.append(r)
        return r

    # ── Gate 3 ──────────────────────────────────────────────────────────
    def check_monotonic_relationship(self, feature_values: np.ndarray,
                                     net_returns: np.ndarray) -> GateResult:
        r = _gate_monotonic_relationship(feature_values, net_returns)
        self.results.append(r)
        return r

    # ── Gate 4 ──────────────────────────────────────────────────────────
    def check_multiple_testing_tally(self, total_tests: int) -> GateResult:
        r = _gate_multiple_testing_tally(total_tests)
        self.results.append(r)
        return r

    # ── Gate 5 ──────────────────────────────────────────────────────────
    def check_threshold_from_training(self, threshold_source: str) -> GateResult:
        r = _gate_threshold_from_training(threshold_source)
        self.results.append(r)
        return r

    # ── Gate 6 ──────────────────────────────────────────────────────────
    def check_viewed_once(self) -> GateResult:
        r = _gate_viewed_once(self.firewall_sealed)
        self.results.append(r)
        return r

    # ── Gate 7 ──────────────────────────────────────────────────────────
    def check_year_consistency(
        self, returns_by_year: dict[int, tuple[np.ndarray, np.ndarray]]
    ) -> GateResult:
        r = _gate_year_consistency(returns_by_year)
        self.results.append(r)
        return r

    # ── Gate 8 ──────────────────────────────────────────────────────────
    def check_median_not_worse(self, baseline_median: float,
                               candidate_median: float) -> GateResult:
        r = _gate_median_not_worse(baseline_median, candidate_median)
        self.results.append(r)
        return r

    # ── Gate 9 ──────────────────────────────────────────────────────────
    def check_left_tail_not_wider(self, baseline_returns: np.ndarray,
                                  candidate_returns: np.ndarray) -> GateResult:
        r = _gate_left_tail_not_wider(baseline_returns, candidate_returns)
        self.results.append(r)
        return r

    # ── Gate 10 ─────────────────────────────────────────────────────────
    def check_top3_not_dominant(self, baseline_returns: np.ndarray,
                                candidate_returns: np.ndarray) -> GateResult:
        r = _gate_top3_not_dominant(baseline_returns, candidate_returns)
        self.results.append(r)
        return r

    # ── Gate 11 ─────────────────────────────────────────────────────────
    def check_jackknife_stable(self, baseline_returns: np.ndarray,
                               candidate_returns: np.ndarray) -> GateResult:
        r = _gate_jackknife_stable(baseline_returns, candidate_returns)
        self.results.append(r)
        return r

    # ── Gate 12 ─────────────────────────────────────────────────────────
    def check_cost_100bp_improves(self, baseline_net_100bp: np.ndarray,
                                  candidate_net_100bp: np.ndarray) -> GateResult:
        r = _gate_cost_100bp_improves(baseline_net_100bp, candidate_net_100bp)
        self.results.append(r)
        return r

    # ── Gate 13 (structural) ────────────────────────────────────────────
    def check_any_failure_is_fatal(self) -> GateResult:
        """Gate 13: Any single failure → candidate REJECTED immediately."""
        any_failed = any(not r.passed for r in self.results)
        r = GateResult("any_failure_fatal", not any_failed,
                       "All passed." if not any_failed else
                       f"FATAL: {sum(1 for r in self.results if not r.passed)} gate(s) failed.")
        self.results.append(r)
        return r

    # ── Aggregate ───────────────────────────────────────────────────────
    def verdict(self) -> HardGateResult:
        """Run gate 13 (aggregator) and return the final verdict.

        REQUIRES all 12 substantive gates to have been called.
        If any gate is missing, verdict is FAIL with details of which
        gates were not run.
        """
        ALL_REQUIRED_GATES = {
            "diagnostic_only", "single_candidate", "monotonic_relationship",
            "multiple_testing_tally", "threshold_from_training", "viewed_once",
            "year_consistency", "median_not_worse", "left_tail_not_wider",
            "top3_not_dominant", "jackknife_stable", "cost_100bp_improves",
        }
        called_gates = {r.gate_name for r in self.results}
        missing = ALL_REQUIRED_GATES - called_gates
        if missing:
            self.results.append(GateResult(
                "all_gates_required", False,
                f"Missing gates: {sorted(missing)}. All 12 gates must be run before verdict."
            ))

        self.check_any_failure_is_fatal()
        n_passed = sum(1 for r in self.results if r.passed)
        n_failed = len(self.results) - n_passed
        all_pass = n_failed == 0
        return HardGateResult(
            candidate_name=self.candidate_name,
            passed=all_pass,
            results=self.results,
            n_passed=n_passed,
            n_failed=n_failed,
            failure_gates=[r.gate_name for r in self.results if not r.passed],
        )

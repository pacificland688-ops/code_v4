"""
Optimized Weighting Module.

Structured mean-variance optimization with tiered fallback levels.
Extracted from PortfolioBacktester._compute_optimized_weights into a
testable module with clear diagnostic output.

Fallback Levels:
- Level 0: Normal optimization with all constraints.
- Level 1: Enhanced covariance shrinkage (stronger regularization).
- Level 2: Relax turnover cap (0.30 → 0.35 → 0.45).
- Level 3: Relax weight_max slightly (0.02 → 0.025) — DIAGNOSTIC ONLY.
- Level 4: Fallback to previous weights or equal weight.

Key Requirements:
- Every relaxation is recorded in diagnostics.
- Relaxed successes are NOT counted as normal successes.
- Solver failures include solver name and status.
"""

import logging
from copy import deepcopy
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

try:
    import cvxpy as cp

    _HAS_CVXPY = True
except ImportError:
    _HAS_CVXPY = False
    logger.warning("cvxpy not installed")


# ---------------------------------------------------------------------------
# Diagnostic result structure
# ---------------------------------------------------------------------------

def make_diag(fallback: bool = False, fallback_reason: str = "",
              used_mu: bool = False, low_optimizer_space: bool = False,
              solver: str = "", relaxation_level: int = 0,
              relaxation_applied: Optional[List[str]] = None) -> Dict[str, Any]:
    """Create a standardized optimizer diagnostic dict."""
    return {
        "fallback": fallback,
        "fallback_reason": fallback_reason,
        "used_mu": used_mu,
        "low_optimizer_space": low_optimizer_space,
        "solver": solver,
        "relaxation_level": relaxation_level,
        "relaxation_applied": relaxation_applied or [],
        "infeasible_config": False,
        "n_optimized": 0,
    }


# ---------------------------------------------------------------------------
# Preparation functions
# ---------------------------------------------------------------------------

def prepare_mu(mu_df: Optional[pd.DataFrame], signal_date: int,
               stock_codes: List[str]) -> Tuple[Optional[pd.Series], Dict[str, Any]]:
    """
    Extract expected return vector from mu calibration DataFrame.

    Returns (mu_series, diag).
    """
    if mu_df is None or mu_df.empty:
        diag = make_diag(fallback=True, fallback_reason="missing_mu — no mu_df provided")
        return None, diag

    mu_day = mu_df[
        (mu_df["trade_date"] == signal_date) &
        (mu_df["ts_code"].isin(stock_codes))
    ]

    if mu_day.empty or "mu" not in mu_day.columns:
        diag = make_diag(fallback=True,
                         fallback_reason=f"missing_mu for {signal_date}")
        return None, diag

    mu_series = (
        mu_day.set_index("ts_code")["mu"]
        .astype("float64")
        .replace([np.inf, -np.inf], np.nan)
        .fillna(0.0)
    )

    diag = make_diag(used_mu=True)
    return mu_series, diag


def estimate_covariance(stock_codes: List[str], exec_date: int,
                        method: str = "ledoit_wolf",
                        min_obs: int = 60) -> Tuple[Optional[np.ndarray], Optional[List[str]], Dict[str, Any]]:
    """
    Estimate covariance matrix from historical price data.

    Parameters
    ----------
    stock_codes : list of str
        Stock codes to include.
    exec_date : int
        Execution date.
    method : str
        Covariance estimation method.
    min_obs : int
        Minimum observations per stock.

    Returns
    -------
    (Sigma, codes, diag)
    """
    from data.panel_loader import get_loader
    from data.calendar import get_calendar
    from portfolio.cov_estimator import CovarianceEstimator

    loader_ = get_loader()
    cal = get_calendar()

    lookback_start = str(cal.prev_trade_day(exec_date, 252))
    price_window = loader_.pivot_for_window(
        start_date=lookback_start,
        end_date=str(exec_date),
        ts_codes=stock_codes,
        field="adj_close",
    )

    if price_window.empty or price_window.shape[1] < 5:
        diag = make_diag(fallback=True,
                         fallback_reason="insufficient price history for covariance")
        return None, None, diag

    # Compute log returns
    ret_matrix = np.log(price_window / price_window.shift(1))
    ret_matrix = ret_matrix.replace([np.inf, -np.inf], np.nan)
    ret_matrix = ret_matrix.dropna(how="all")

    if ret_matrix.shape[0] < 60:
        diag = make_diag(fallback=True,
                         fallback_reason=f"only {ret_matrix.shape[0]} return observations")
        return None, None, diag

    # Estimate
    cov_est = CovarianceEstimator(method=method, window=252, min_obs=min_obs)
    Sigma, codes = cov_est.estimate(ret_matrix)

    if len(codes) < 5:
        diag = make_diag(fallback=True,
                         fallback_reason=f"only {len(codes)} valid stocks after cov estimation")
        return None, None, diag

    # Ensure PSD
    Sigma = _ensure_psd(Sigma)

    diag = make_diag()
    return Sigma, codes, diag


def _ensure_psd(Sigma: np.ndarray, epsilon: float = 1e-6) -> np.ndarray:
    """Ensure matrix is positive semi-definite."""
    Sigma = np.asarray(Sigma, dtype="float64")
    Sigma = np.nan_to_num(Sigma, nan=0.0, posinf=0.0, neginf=0.0)
    Sigma = (Sigma + Sigma.T) / 2.0

    eigenvalues = np.linalg.eigvalsh(Sigma)
    min_eig = float(eigenvalues.min()) if len(eigenvalues) else 0.0
    if min_eig < epsilon:
        Sigma = Sigma + np.eye(Sigma.shape[0]) * (epsilon - min_eig)
    return Sigma


# ---------------------------------------------------------------------------
# Feasibility check
# ---------------------------------------------------------------------------

def check_feasibility(top_n: int, weight_max: float) -> Dict[str, Any]:
    """
    Check if the optimization problem is feasible.

    Returns diag with infeasibility reason or empty diag if feasible.
    """
    opt_space = top_n * weight_max
    if opt_space < 1.0:
        diag = make_diag(
            fallback=True,
            fallback_reason=(
                f"infeasible: top_n={top_n} * weight_max={weight_max} "
                f"= {opt_space:.2f} < 1.0"
            ),
        )
        diag["infeasible_config"] = True
        return diag

    diag = make_diag()
    if opt_space <= 1.05:
        diag["low_optimizer_space"] = True
    return diag


# ---------------------------------------------------------------------------
# Solver with retries
# ---------------------------------------------------------------------------

def solve_with_retries(
    mu_aligned: np.ndarray,
    Sigma: np.ndarray,
    codes: List[str],
    prev_aligned: np.ndarray,
    weight_max: float,
    turnover_max: float,
    turnover_penalty: float = 0.0,
    risk_aversion: float = 1.0,
    cost_aware_lambda: float = 0.0,
    estimated_cost_bps: float = 10.0,
) -> Tuple[Optional[np.ndarray], Dict[str, Any]]:
    """
    Solve mean-variance optimization with solver fallback chain.

    Returns (optimal_weights, diag).
    """
    if not _HAS_CVXPY:
        diag = make_diag(fallback=True, fallback_reason="cvxpy not installed")
        return None, diag

    n = len(codes)
    w = cp.Variable(n)

    # Objective: max w'μ - (λ/2) w'Σw - γ·|w - w_prev| - κ·estimated_cost
    objective = cp.Maximize(
        mu_aligned @ w
        - (risk_aversion / 2) * cp.quad_form(w, Sigma)
    )

    # Turnover penalty in objective
    if turnover_penalty > 0 and prev_aligned.sum() > 0:
        objective = cp.Maximize(
            mu_aligned @ w
            - (risk_aversion / 2) * cp.quad_form(w, Sigma)
            - turnover_penalty * cp.sum(cp.abs(w - prev_aligned))
        )

    # Cost-aware term
    if cost_aware_lambda > 0 and prev_aligned.sum() > 0 and estimated_cost_bps > 0:
        est_cost = cp.sum(cp.abs(w - prev_aligned)) * estimated_cost_bps / 10000.0
        # Rebuild objective with cost term (add to turnover penalty if both used)
        cost_term = cost_aware_lambda * est_cost
        base = mu_aligned @ w - (risk_aversion / 2) * cp.quad_form(w, Sigma)
        if turnover_penalty > 0:
            base = base - turnover_penalty * cp.sum(cp.abs(w - prev_aligned))
        objective = cp.Maximize(base - cost_term)

    # Constraints
    constraints = [
        cp.sum(w) == 1.0,
        w >= 0,
        w <= weight_max,
    ]

    # Turnover constraint
    _to_max = turnover_max if turnover_max is not None else 0.60
    if prev_aligned.sum() > 0 and _to_max < 1.0:
        constraints.append(cp.sum(cp.abs(w - prev_aligned)) / 2.0 <= _to_max)

    # Solver chain
    installed = set(cp.installed_solvers())
    solver_attempts = [
        ("ECOS", {"max_iters": 10000}),
        ("CLARABEL", {}),
        ("OSQP", {"max_iter": 20000, "eps_abs": 1e-6, "eps_rel": 1e-6}),
    ]

    last_reason = "optimization did not converge"
    acceptable_status = {"optimal", "optimal_inaccurate"}

    for solver_name, solver_kwargs in solver_attempts:
        if solver_name not in installed:
            continue

        problem = cp.Problem(objective, constraints)
        try:
            problem.solve(solver=solver_name, verbose=False, **solver_kwargs)
        except Exception as e:
            last_reason = f"{solver_name} solver failed: {str(e)[:60]}"
            continue

        if problem.status not in acceptable_status or w.value is None:
            last_reason = f"{solver_name} status {problem.status}"
            continue

        candidate = np.asarray(w.value, dtype="float64").reshape(-1)
        if candidate.shape[0] != n or not np.all(np.isfinite(candidate)):
            last_reason = f"{solver_name} returned non-finite weights"
            continue

        candidate[candidate < 1e-6] = 0.0
        weight_sum = float(candidate.sum())
        if not np.isfinite(weight_sum) or weight_sum <= 1e-12:
            last_reason = f"{solver_name} returned zero weights"
            continue

        optimal = candidate / weight_sum
        diag = make_diag(solver=solver_name)
        diag["n_optimized"] = int((optimal > 1e-6).sum())
        return optimal, diag

    diag = make_diag(fallback=True, fallback_reason=last_reason)
    return None, diag


# ---------------------------------------------------------------------------
# Tiered constraint relaxation
# ---------------------------------------------------------------------------

def relax_constraints_tiered(
    mu_aligned: np.ndarray,
    Sigma: np.ndarray,
    codes: List[str],
    prev_aligned: np.ndarray,
    weight_max: float,
    turnover_max: float,
    turnover_penalty: float = 0.0,
    risk_aversion: float = 1.0,
    original_Sigma: Optional[np.ndarray] = None,
    cost_aware_lambda: float = 0.0,
    estimated_cost_bps: float = 10.0,
) -> Tuple[Optional[np.ndarray], Dict[str, Any]]:
    """
    Attempt optimization with tiered relaxation of constraints.

    Levels:
    1. Enhanced covariance shrinkage.
    2. Relax turnover cap.
    3. Relax weight_max (diagnostic only).
    4. Give up → fallback to equal weight.

    Returns (weights, diag) where diag records full relaxation path.
    """
    all_relaxations = []

    # Explicit override helper — only overrides parameters that are
    # passed, avoiding the "multiple values for keyword argument" error
    # that a **kw lambda would cause when combined with closure-captured
    # defaults of the same name.
    def _solve(
        Sigma_override: Optional[np.ndarray] = None,
        weight_max_override: Optional[float] = None,
        turnover_max_override: Optional[float] = None,
    ):
        _Sigma = Sigma_override if Sigma_override is not None else Sigma
        _weight_max = weight_max_override if weight_max_override is not None else weight_max
        _turnover_max = turnover_max_override if turnover_max_override is not None else turnover_max
        return solve_with_retries(
            mu_aligned=mu_aligned, Sigma=_Sigma, codes=codes,
            prev_aligned=prev_aligned,
            weight_max=_weight_max, turnover_max=_turnover_max,
            turnover_penalty=turnover_penalty, risk_aversion=risk_aversion,
            cost_aware_lambda=cost_aware_lambda,
            estimated_cost_bps=estimated_cost_bps,
        )

    # Level 0: Try normal optimization first
    optimal, diag = _solve()
    if optimal is not None and not diag.get("fallback"):
        diag["relaxation_level"] = 0
        return optimal, diag

    all_relaxations.append(f"L0_failed: {diag.get('fallback_reason', 'unknown')}")

    # Level 1: Enhanced covariance shrinkage
    if original_Sigma is not None:
        Sigma_L1 = _enhance_shrinkage(Sigma)
        optimal, diag = _solve(Sigma_override=Sigma_L1)
        if optimal is not None and not diag.get("fallback"):
            diag["relaxation_level"] = 1
            diag["relaxation_applied"] = ["cov_shrinkage_enhanced"]
            all_relaxations.append("L1_cov_shrinkage: success")
            return optimal, diag
        all_relaxations.append(f"L1_cov_shrinkage_failed: {diag.get('fallback_reason', 'unknown')}")

    # Level 2: Relax turnover cap in stages
    for to_relax in [0.35, 0.45]:
        if turnover_max < to_relax:
            optimal, diag = _solve(turnover_max_override=to_relax)
            if optimal is not None and not diag.get("fallback"):
                diag["relaxation_level"] = 2
                diag["relaxation_applied"] = [f"turnover_cap_relaxed_to_{to_relax}"]
                all_relaxations.append(f"L2_to_relax_{to_relax}: success")
                return optimal, diag
            all_relaxations.append(f"L2_to_relax_{to_relax}_failed: {diag.get('fallback_reason', 'unknown')}")

    # Level 3: Relax weight_max slightly (DIAGNOSTIC ONLY)
    wm_relaxed = min(weight_max * 1.25, 0.03)  # cap at 3%
    if wm_relaxed > weight_max:
        optimal, diag = _solve(weight_max_override=wm_relaxed)
        if optimal is not None and not diag.get("fallback"):
            diag["relaxation_level"] = 3
            diag["relaxation_applied"] = [
                f"weight_max_relaxed_{weight_max}_to_{wm_relaxed:.4f}_DIAGNOSTIC_ONLY"
            ]
            all_relaxations.append(f"L3_wm_relax: success (DIAGNOSTIC)")
            return optimal, diag
        all_relaxations.append(f"L3_wm_relax_failed: {diag.get('fallback_reason', 'unknown')}")

    # Level 4: All relaxation failed
    diag = make_diag(
        fallback=True,
        fallback_reason=f"all_relaxation_levels_failed: {'; '.join(all_relaxations)}",
        relaxation_level=4,
        relaxation_applied=all_relaxations,
    )
    return None, diag


def _enhance_shrinkage(Sigma: np.ndarray, factor: float = 0.3) -> np.ndarray:
    """
    Enhance shrinkage by pushing the covariance toward the diagonal.

    Sigma_enhanced = (1 - factor) * Sigma + factor * diag(diag(Sigma))
    """
    Sigma = np.asarray(Sigma, dtype="float64")
    diag_vals = np.diag(Sigma).copy()
    # Ensure non-negative
    diag_vals = np.maximum(diag_vals, 1e-8)
    enhanced = (1 - factor) * Sigma + factor * np.diag(diag_vals)
    return _ensure_psd(enhanced)


# ---------------------------------------------------------------------------
# Fallback weight builders
# ---------------------------------------------------------------------------

def build_fallback_weights(top_n: int, stock_codes: List[str],
                           prev_weights: Optional[pd.Series] = None,
                           method: str = "equal") -> Tuple[pd.Series, Dict[str, Any]]:
    """
    Build fallback weights when optimization fails at all levels.

    Parameters
    ----------
    top_n : int
        Number of stocks in portfolio.
    stock_codes : list of str
        Current stock universe.
    prev_weights : pd.Series, optional
        Previous period weights.
    method : str
        "equal" or "previous".

    Returns
    -------
    (weights_series, diag)
    """
    if method == "previous" and prev_weights is not None and len(prev_weights) > 0:
        # Reuse previous weights where possible, equal weight for new stocks
        weights = pd.Series(0.0, index=stock_codes, dtype="float64")
        for code in stock_codes:
            if code in prev_weights.index:
                weights[code] = prev_weights.get(code, 0.0)
        if weights.sum() > 0:
            weights = weights / weights.sum()
        else:
            weights = pd.Series(1.0 / len(stock_codes), index=stock_codes, dtype="float64")
        diag = make_diag(fallback=True, fallback_reason="previous_weights_reused")
        return weights, diag

    # Equal weight
    weights = pd.Series(1.0 / len(stock_codes), index=stock_codes, dtype="float64")
    diag = make_diag(fallback=True, fallback_reason="equal_weight_fallback")
    return weights, diag


# ===================================================================
# Main entry point: compute optimized weights with full pipeline
# ===================================================================

def compute_optimized_weights(
    top_stocks: pd.DataFrame,
    score_col: str,
    signal_date: int,
    prev_weights: Optional[pd.Series],
    exec_date: int,
    top_n: int,
    mu_df: Optional[pd.DataFrame] = None,
    weight_max: float = 0.02,
    turnover_max: Optional[float] = None,
    turnover_penalty: Optional[float] = None,
    cost_aware_lambda: float = 0.0,
    estimated_cost_bps: float = 10.0,
    cov_method: str = "ledoit_wolf",
    no_trade_band: float = 0.0,
    max_weight_change: Optional[float] = None,
    constraint_relaxation: str = "none",
) -> Tuple[pd.Series, Dict[str, Any]]:
    """
    Compute optimized portfolio weights with full diagnostic pipeline.

    Parameters
    ----------
    top_stocks : DataFrame
        Top-ranked stocks with ts_code, score_col.
    score_col : str
        Score column name (unused in optimized weighting, for API compatibility).
    signal_date : int
        Signal date.
    prev_weights : pd.Series, optional
        Previous portfolio weights.
    exec_date : int
        Execution date for covariance lookback.
    top_n : int
        Target number of stocks.
    mu_df : DataFrame, optional
        Expected return calibration.
    weight_max : float
        Maximum single stock weight (default 2%).
    turnover_max : float, optional
        Maximum one-way turnover (default 0.30 if None).
    turnover_penalty : float, optional
        Turnover penalty in objective.
    cost_aware_lambda : float
        Weight for explicit cost penalty term.
    estimated_cost_bps : float
        Estimated trading cost in bps for cost-aware term.
    cov_method : str
        Covariance estimation method.
    no_trade_band : float
        Minimum weight change to trigger trade (0 = always trade).
    max_weight_change : float, optional
        Maximum individual stock weight change per rebalance.

    Returns
    -------
    (weights_series, diag_dict)
    """
    _to_max = turnover_max if turnover_max is not None else 0.60
    _to_penalty = turnover_penalty if turnover_penalty is not None else 0.0

    stock_codes = list(top_stocks["ts_code"])
    equal_weights = pd.Series(1.0 / top_n, index=stock_codes, dtype="float64")

    # Step 1: Feasibility check
    feas_diag = check_feasibility(top_n, weight_max)
    if feas_diag.get("fallback"):
        return equal_weights, feas_diag

    low_space = feas_diag.get("low_optimizer_space", False)

    # Step 2: Prepare mu
    mu_series, mu_diag = prepare_mu(mu_df, signal_date, stock_codes)
    if mu_diag.get("fallback"):
        return equal_weights, mu_diag

    # Step 3: Estimate covariance
    Sigma, codes, cov_diag = estimate_covariance(stock_codes, exec_date, method=cov_method)
    if cov_diag.get("fallback"):
        return equal_weights, cov_diag

    # Step 4: Align mu to covariance codes
    mu_aligned = np.array([
        mu_series.get(c, 0.0) for c in codes
    ], dtype="float64")

    # Step 5: Align previous weights
    prev_aligned = np.array([
        prev_weights.get(c, 0.0) if prev_weights is not None else 0.0
        for c in codes
    ], dtype="float64")

    # Step 6: Solve — optionally with tiered relaxation
    # Batch 1 fix: cost_aware_lambda and estimated_cost_bps MUST reach the solver.
    if constraint_relaxation == "tiered":
        optimal, solve_diag = relax_constraints_tiered(
            mu_aligned, Sigma, codes, prev_aligned,
            weight_max, _to_max, _to_penalty,
            risk_aversion=1.0,
            original_Sigma=Sigma,
            cost_aware_lambda=cost_aware_lambda,
            estimated_cost_bps=estimated_cost_bps,
        )
    else:
        # "none" or unknown: single solve_with_retries, no relaxation
        optimal, solve_diag = solve_with_retries(
            mu_aligned, Sigma, codes, prev_aligned,
            weight_max, _to_max, _to_penalty,
            risk_aversion=1.0,
            cost_aware_lambda=cost_aware_lambda,
            estimated_cost_bps=estimated_cost_bps,
        )
    solve_diag["constraint_relaxation_mode"] = constraint_relaxation
    # Batch 1: Record cost-aware params in diagnostics
    solve_diag["cost_aware_lambda"] = cost_aware_lambda
    solve_diag["estimated_cost_bps"] = estimated_cost_bps

    if optimal is None:
        # Level 4 fallback
        fb_weights, fb_diag = build_fallback_weights(
            top_n, codes, prev_weights, method="equal"
        )
        # Merge diagnostics
        fb_diag["fallback_reason"] = (
            solve_diag.get("fallback_reason", "unknown") +
            f" → {fb_diag['fallback_reason']}"
        )
        fb_diag["relaxation_level"] = solve_diag.get("relaxation_level", 4)
        fb_diag["relaxation_applied"] = solve_diag.get("relaxation_applied", [])
        return fb_weights, fb_diag

    # Step 7: Post-processing — no-trade band
    result = pd.Series(optimal, index=codes, dtype="float64")

    if no_trade_band > 0 and prev_weights is not None:
        result = _apply_no_trade_band(result, prev_weights, no_trade_band)

    # Step 8: Max weight change cap
    if max_weight_change is not None and prev_weights is not None:
        result = _apply_max_weight_change(result, prev_weights, max_weight_change)

    # Merge diagnostics
    solve_diag["used_mu"] = mu_diag.get("used_mu", False)
    solve_diag["low_optimizer_space"] = low_space
    if not solve_diag.get("n_optimized"):
        solve_diag["n_optimized"] = int((optimal > 1e-6).sum())

    return result, solve_diag


# ---------------------------------------------------------------------------
# Post-processing: turnover controls
# ---------------------------------------------------------------------------

def _apply_no_trade_band(
    target_weights: pd.Series,
    prev_weights: pd.Series,
    band: float,
) -> pd.Series:
    """
    If target weight change is below `band`, keep the previous weight.

    This reduces micro-rebalancing turnover.
    """
    result = target_weights.copy()
    all_codes = list(set(target_weights.index) | set(prev_weights.index))
    for code in all_codes:
        target_w = target_weights.get(code, 0.0)
        prev_w = prev_weights.get(code, 0.0)
        if abs(target_w - prev_w) < band:
            result[code] = prev_w

    # Renormalize
    if result.sum() > 0:
        result = result / result.sum()
    return result


def _apply_max_weight_change(
    target_weights: pd.Series,
    prev_weights: pd.Series,
    max_change: float,
) -> pd.Series:
    """
    Cap individual stock weight changes to max_change.

    Maintains sum-to-1 constraint by proportional redistribution.
    """
    result = target_weights.copy()
    all_codes = set(target_weights.index) | set(prev_weights.index)
    excess = 0.0

    for code in all_codes:
        target_w = target_weights.get(code, 0.0)
        prev_w = prev_weights.get(code, 0.0)
        delta = target_w - prev_w

        if abs(delta) > max_change:
            clipped = prev_w + np.sign(delta) * max_change
            excess += target_w - clipped
            result[code] = max(0.0, clipped)  # floor at 0 (long-only)

    # Redistribute excess proportionally among un-capped stocks
    if abs(excess) > 1e-10:
        uncapped = [
            c for c in all_codes
            if abs(result.get(c, 0.0) - prev_weights.get(c, 0.0)) < max_change
        ]
        if uncapped:
            redist_per_stock = excess / len(uncapped)
            for c in uncapped:
                result[c] = max(0.0, result.get(c, 0.0) + redist_per_stock)

    # Renormalize
    if result.sum() > 0:
        result = result / result.sum()
    return result

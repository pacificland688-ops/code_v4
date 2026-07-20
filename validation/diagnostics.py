"""
Phase 5 Failure Diagnostics Module.

Performs attribution analysis on backtest failures:
1. Turnover attribution — new entries, exits, within-portfolio rebalancing
2. Cost attribution — gross/net return decomposition, cost drag
3. Fallback attribution — optimizer fallback reason classification
4. Factor stability — annual IC, coverage, decay markers

All outputs distinguish IS (in-sample) from OOS (out-of-sample).
DATA_MISSING is used when no data is available, never 0.
"""

import json
import logging
from collections import defaultdict
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DATA_MISSING_SENTINEL = "DATA_MISSING"
OOS_START_DATE = "20250101"


def _safe_float(val, default=float("nan")):
    """Convert to float, returning default for non-numeric."""
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _is_oos(date_val, oos_start=OOS_START_DATE):
    """Check if a date is in the OOS period."""
    if date_val is None:
        return False
    try:
        return str(int(date_val)) >= oos_start
    except (TypeError, ValueError):
        return False


# ===================================================================
# Turnover Attribution
# ===================================================================


def decompose_turnover(
    trades_log: List[Dict],
    holdings_log: List[Dict],
    portfolio_values: List[Dict],
) -> Dict[str, Any]:
    """
    Decompose average turnover into constituent components.

    Parameters
    ----------
    trades_log : list of dict
        Per-rebalance trade records with signal_date, turnover.
    holdings_log : list of dict
        Per-rebalance holdings with signal_date, weights dict.
    portfolio_values : list of dict
        Portfolio value records with signal_date.

    Returns
    -------
    dict with turnover breakdown statistics, separated IS/OOS.
    """
    if not trades_log or not holdings_log:
        return {
            "avg_turnover": DATA_MISSING_SENTINEL,
            "n_observations": 0,
            "error": "No trade/holdings data available",
        }

    # Align by date
    trade_df = _build_trade_df(trades_log)
    holdings_by_date = {h["signal_date"]: h.get("weights", {}) for h in holdings_log}

    if trade_df.empty:
        return {
            "avg_turnover": DATA_MISSING_SENTINEL,
            "n_observations": 0,
            "error": "No trade data after alignment",
        }

    # Overall stats
    turnover_series = trade_df["turnover"]
    avg_to = float(turnover_series.mean()) if len(turnover_series) > 0 else float("nan")
    p50_to = float(turnover_series.quantile(0.50)) if len(turnover_series) > 0 else float("nan")
    p75_to = float(turnover_series.quantile(0.75)) if len(turnover_series) > 0 else float("nan")
    p95_to = float(turnover_series.quantile(0.95)) if len(turnover_series) > 0 else float("nan")
    max_to = float(turnover_series.max()) if len(turnover_series) > 0 else float("nan")
    max_to_date = (
        str(int(trade_df.loc[turnover_series.idxmax(), "signal_date"]))
        if len(turnover_series) > 0 and not turnover_series.isna().all()
        else DATA_MISSING_SENTINEL
    )

    # IS / OOS split
    is_mask = ~trade_df["signal_date"].apply(_is_oos)
    oos_mask = trade_df["signal_date"].apply(_is_oos)

    is_turnover = turnover_series[is_mask] if is_mask.any() else pd.Series(dtype=float)
    oos_turnover = turnover_series[oos_mask] if oos_mask.any() else pd.Series(dtype=float)

    # Entry/exit/within decomposition (heuristic: compare consecutive holdings)
    entry_contrib, exit_contrib, within_contrib = _estimate_turnover_components(
        holdings_log, trades_log
    )

    # Weekly vs monthly comparison (if available)
    weekly_vs_monthly = _weekly_monthly_comparison(trade_df)

    # Top turnover dates
    top_n_dates = 10
    top_dates = (
        trade_df.nlargest(top_n_dates, "turnover")[["signal_date", "turnover"]]
        .assign(signal_date=lambda x: x["signal_date"].astype(str))
        .to_dict("records")
    )

    result = {
        "avg_turnover": avg_to,
        "turnover_p50": p50_to,
        "turnover_p75": p75_to,
        "turnover_p95": p95_to,
        "max_turnover": max_to,
        "max_turnover_date": max_to_date,
        "n_observations": len(trade_df),
        # IS
        "is_avg_turnover": float(is_turnover.mean()) if len(is_turnover) > 0 else float("nan"),
        "is_n_observations": int(is_turnover.count()),
        # OOS
        "oos_avg_turnover": float(oos_turnover.mean()) if len(oos_turnover) > 0 else float("nan"),
        "oos_n_observations": int(oos_turnover.count()),
        # Decomposition
        "entry_contribution_pct": entry_contrib,
        "exit_contribution_pct": exit_contrib,
        "within_portfolio_contribution_pct": within_contrib,
        # Comparison
        "weekly_vs_monthly": weekly_vs_monthly,
        # High turnover dates
        "top_turnover_dates": top_dates,
    }
    return result


def _build_trade_df(trades_log: List[Dict]) -> pd.DataFrame:
    """Build a DataFrame from trades_log, with signal_date as int."""
    if not trades_log:
        return pd.DataFrame()
    df = pd.DataFrame(trades_log)
    if "signal_date" not in df.columns:
        return pd.DataFrame()
    df["signal_date"] = df["signal_date"].apply(lambda d: int(d) if d is not None else 0)
    return df


def _estimate_turnover_components(
    holdings_log: List[Dict], trades_log: List[Dict]
) -> Tuple[float, float, float]:
    """
    Estimate turnover split into entry (new stocks), exit (dropped stocks),
    and within-portfolio rebalancing.

    Returns (entry_pct, exit_pct, within_pct) as fractions of total turnover.
    """
    if len(holdings_log) < 2:
        return (float("nan"), float("nan"), float("nan"))

    total_entry_to = 0.0
    total_exit_to = 0.0
    total_within_to = 0.0
    total_to = 0.0

    for i in range(1, len(holdings_log)):
        prev_weights = holdings_log[i - 1].get("weights", {})
        curr_weights = holdings_log[i].get("weights", {})
        trade = trades_log[i] if i < len(trades_log) else {}
        period_to = trade.get("turnover", 0.0)

        if period_to <= 0:
            continue

        prev_codes = set(prev_weights.keys())
        curr_codes = set(curr_weights.keys())

        entered = curr_codes - prev_codes
        exited = prev_codes - curr_codes
        held = prev_codes & curr_codes

        entry_to = sum(curr_weights.get(c, 0) for c in entered)
        exit_to = sum(prev_weights.get(c, 0) for c in exited)
        within_to = sum(
            abs(curr_weights.get(c, 0) - prev_weights.get(c, 0))
            for c in held
        )

        total_entry_to += entry_to
        total_exit_to += exit_to
        total_within_to += within_to
        total_to += entry_to + exit_to + within_to

    if total_to <= 0:
        return (float("nan"), float("nan"), float("nan"))

    return (
        total_entry_to / total_to,
        total_exit_to / total_to,
        total_within_to / total_to,
    )


def _weekly_monthly_comparison(trade_df: pd.DataFrame) -> Dict[str, Any]:
    """Compare weekly vs monthly turnover patterns if detectable."""
    if trade_df.empty or "signal_date" not in trade_df.columns:
        return {"available": False, "reason": "No data"}

    # Heuristic: monthly dates end in patterns like 01/28-01/31 or
    # happen ~20 trading days apart. We'll approximate by checking
    # if the signal_date is near month-end.
    try:
        dates = pd.to_datetime(trade_df["signal_date"].astype(str), format="%Y%m%d")
        is_month_end = dates.dt.is_month_end | (dates.dt.day >= 25)
    except Exception:
        return {"available": False, "reason": "Date parsing failed"}

    if is_month_end.sum() < 2:
        return {"available": False, "reason": "Insufficient monthly-like dates"}

    weekly = trade_df.loc[~is_month_end, "turnover"]
    monthly = trade_df.loc[is_month_end, "turnover"]

    return {
        "available": True,
        "weekly_avg_turnover": float(weekly.mean()) if len(weekly) > 0 else float("nan"),
        "monthly_avg_turnover": float(monthly.mean()) if len(monthly) > 0 else float("nan"),
        "weekly_n": int(len(weekly)),
        "monthly_n": int(len(monthly)),
    }


# ===================================================================
# Cost Attribution
# ===================================================================


def decompose_costs(
    portfolio_values: List[Dict],
    cost_multipliers: Optional[List[float]] = None,
) -> Dict[str, Any]:
    """
    Decompose trading costs and their impact on returns.

    Parameters
    ----------
    portfolio_values : list of dict
        Per-period records with gross_period_return, period_return, cost_bps.
    cost_multipliers : list of float, optional
        Cost multipliers to simulate (default: [1.0, 2.0]).

    Returns
    -------
    dict with gross/net return decomposition and cost sensitivity.
    """
    if not portfolio_values:
        return {
            "gross_return": DATA_MISSING_SENTINEL,
            "net_return": DATA_MISSING_SENTINEL,
            "error": "No portfolio value data",
        }

    pv = pd.DataFrame(portfolio_values)

    required_cols = ["period_return", "cost_bps"]
    missing = [c for c in required_cols if c not in pv.columns]
    if missing:
        return {
            "gross_return": DATA_MISSING_SENTINEL,
            "net_return": DATA_MISSING_SENTINEL,
            "error": f"Missing columns: {missing}",
        }

    # Check for gross_period_return
    has_gross = "gross_period_return" in pv.columns and not pv["gross_period_return"].isna().all()

    periods_per_year = 52  # weekly

    # Net return
    net_returns = pv["period_return"].dropna()
    if len(net_returns) < 5:
        return {
            "gross_return": DATA_MISSING_SENTINEL,
            "net_return": DATA_MISSING_SENTINEL,
            "error": f"Insufficient periods: {len(net_returns)}",
        }

    net_total = float((1 + net_returns).prod() - 1)
    net_ann = float((1 + net_returns).prod() ** (periods_per_year / len(net_returns)) - 1)

    # Gross return (net + cost impact, approximated)
    if has_gross:
        gross_returns = pv["gross_period_return"].dropna()
        gross_total = float((1 + gross_returns).prod() - 1)
        gross_ann = float(
            (1 + gross_returns).prod() ** (periods_per_year / len(gross_returns)) - 1
        )
    else:
        # Approximate gross by adding costs back
        cost_bps_series = pv["cost_bps"].fillna(0) / 10000  # bps → decimal
        gross_approx = net_returns + cost_bps_series.loc[net_returns.index]
        gross_total = float((1 + gross_approx).prod() - 1)
        gross_ann = float(
            (1 + gross_approx).prod() ** (periods_per_year / len(gross_approx)) - 1
        )

    # Cost drag (1x)
    cost_drag_1x = gross_ann - net_ann if gross_ann is not None else float("nan")

    # 2x cost drag (simulated)
    if has_gross and "cost_bps" in pv.columns:
        cost_bps_series = pv["cost_bps"].fillna(0) / 10000
        gross_returns_aligned = pv["gross_period_return"].dropna()
        aligned_idx = gross_returns_aligned.index.intersection(cost_bps_series.index)
        net_2x_approx = gross_returns_aligned.loc[aligned_idx] - 2 * cost_bps_series.loc[aligned_idx]
        net_2x_total = float((1 + net_2x_approx).prod() - 1)
        net_2x_ann = float(
            (1 + net_2x_approx).prod() ** (periods_per_year / len(net_2x_approx)) - 1
        )
        cost_drag_2x = gross_ann - net_2x_ann
    else:
        net_2x_ann = net_ann - cost_drag_1x  # rough: double the 1x drag
        cost_drag_2x = 2 * cost_drag_1x if cost_drag_1x is not None else float("nan")

    # Turnover-cost beta: how much does a 1% turnover increase affect cost?
    if "turnover" in pv.columns:
        valid = pv[["turnover", "cost_bps"]].dropna()
        if len(valid) >= 10:
            to_cost_beta = float(
                np.cov(valid["turnover"], valid["cost_bps"])[0, 1] / valid["turnover"].var()
                if valid["turnover"].var() > 0
                else 0
            )
        else:
            to_cost_beta = float("nan")
    else:
        to_cost_beta = float("nan")

    # High-cost dates (top 10)
    if "cost_bps" in pv.columns:
        high_cost = (
            pv.nlargest(10, "cost_bps")[["signal_date", "cost_bps"]]
            .assign(signal_date=lambda x: x["signal_date"].astype(str))
            .to_dict("records")
        )
    else:
        high_cost = []

    # IS/OOS split
    if "signal_date" in pv.columns:
        is_mask = ~pv["signal_date"].apply(
            lambda d: _is_oos(d) if d is not None else False
        )
        oos_mask = pv["signal_date"].apply(
            lambda d: _is_oos(d) if d is not None else False
        )

        is_costs = pv.loc[is_mask, "cost_bps"].dropna() if is_mask.any() else pd.Series(dtype=float)
        oos_costs = (
            pv.loc[oos_mask, "cost_bps"].dropna() if oos_mask.any() else pd.Series(dtype=float)
        )
    else:
        is_costs = pd.Series(dtype=float)
        oos_costs = pd.Series(dtype=float)

    multipliers = cost_multipliers or [1.0, 2.0]
    cost_sensitivity = {}
    for mult in multipliers:
        if has_gross and "cost_bps" in pv.columns:
            mult_returns = gross_returns_aligned - mult * cost_bps_series.loc[aligned_idx]
            mult_total = float((1 + mult_returns).prod() - 1)
            mult_ann = float(
                (1 + mult_returns).prod() ** (periods_per_year / len(mult_returns)) - 1
            )
            cost_sensitivity[f"{mult}x_cost_annualized_return"] = mult_ann
            cost_sensitivity[f"{mult}x_cost_excess_vs_net"] = mult_ann - net_ann
        else:
            cost_sensitivity[f"{mult}x_cost_annualized_return"] = float("nan")
            cost_sensitivity[f"{mult}x_cost_excess_vs_net"] = float("nan")

    return {
        "gross_annualized_return": gross_ann,
        "net_annualized_return": net_ann,
        "cost_drag_1x_annualized": cost_drag_1x,
        "cost_drag_2x_annualized": cost_drag_2x,
        "net_2x_annualized_return": net_2x_ann,
        "turnover_cost_beta": to_cost_beta,
        "total_cost_bps": float(pv["cost_bps"].sum()) if "cost_bps" in pv.columns else float("nan"),
        "avg_cost_bps_per_period": float(pv["cost_bps"].mean()) if "cost_bps" in pv.columns else float("nan"),
        "n_periods": len(net_returns),
        "high_cost_dates": high_cost,
        "cost_sensitivity": cost_sensitivity,
        "is_avg_cost_bps": float(is_costs.mean()) if len(is_costs) > 0 else float("nan"),
        "oos_avg_cost_bps": float(oos_costs.mean()) if len(oos_costs) > 0 else float("nan"),
    }


# ===================================================================
# Fallback Attribution
# ===================================================================


def analyze_fallback(
    opt_diagnostics: Dict[str, Any],
    trades_log: Optional[List[Dict]] = None,
) -> Dict[str, Any]:
    """
    Analyze optimizer fallback events.

    Parameters
    ----------
    opt_diagnostics : dict
        Output from PortfolioBacktester._simulate, containing:
        - opt_n_total, opt_n_fallback, opt_fallback_reasons
        - opt_fallback_rate
    trades_log : list of dict, optional
        Per-rebalance trade records for IS/OOS classification.

    Returns
    -------
    dict with fallback analysis.
    """
    if not opt_diagnostics:
        return {
            "fallback_rate": DATA_MISSING_SENTINEL,
            "error": "No optimizer diagnostics available",
        }

    n_total = opt_diagnostics.get("opt_n_total", 0)
    n_fallback = opt_diagnostics.get("opt_n_fallback", 0)
    fallback_reasons = opt_diagnostics.get("opt_fallback_reasons", {})

    if n_total == 0:
        return {
            "fallback_rate": DATA_MISSING_SENTINEL,
            "n_total": 0,
            "error": "No optimizer runs recorded",
        }

    fallback_rate = n_fallback / n_total if n_total > 0 else 0.0

    # Classify reasons
    classified = _classify_fallback_reasons(fallback_reasons)

    # Unknown fallback rate
    unknown_count = sum(
        v for k, v in fallback_reasons.items()
        if k not in _KNOWN_REASON_PATTERNS
    )
    unknown_rate = unknown_count / n_total if n_total > 0 else 0.0

    # Solver-level detail (if available)
    solver_counts = defaultdict(int)
    solver_statuses = defaultdict(list)

    result = {
        "fallback_rate": fallback_rate,
        "n_total": n_total,
        "n_fallback": n_fallback,
        "n_success": n_total - n_fallback,
        "unknown_fallback_rate": unknown_rate,
        "unknown_count": unknown_count,
        "fallback_reasons": classified,
        "raw_fallback_reasons": fallback_reasons,
    }

    return result


_KNOWN_REASON_PATTERNS = {
    "infeasible_config": ["infeasible"],
    "missing_mu": ["missing_mu"],
    "insufficient_price_history": ["insufficient price history", "price history"],
    "insufficient_return_obs": ["return observations"],
    "insufficient_stocks_after_cov": ["valid stocks after cov"],
    "no_convergence": ["did not converge", "all_relaxation", "no_convergence"],
    "cvxpy_not_installed": ["cvxpy not installed"],
    "solver_crash": ["solver failed"],
    "non_finite_weights": ["non-finite"],
    "zero_weights": ["zero weights"],
}


def _classify_fallback_reasons(raw_reasons: Dict[str, int]) -> Dict[str, Any]:
    """Classify raw fallback reason strings into standard categories."""
    classified = {}
    unknown = {}
    for reason, count in raw_reasons.items():
        reason_lower = str(reason).lower()
        matched = False
        for category, patterns in _KNOWN_REASON_PATTERNS.items():
            for pattern in patterns:
                if pattern.lower() in reason_lower:
                    classified[category] = classified.get(category, 0) + count
                    matched = True
                    break
            if matched:
                break
        if not matched:
            unknown[reason] = count

    result = deepcopy(classified)
    if unknown:
        result["unknown"] = sum(unknown.values())
        result["unknown_details"] = unknown
    return result


def build_fallback_events_csv(
    opt_diagnostics: Dict[str, Any],
    trades_log: Optional[List[Dict]] = None,
    holdings_log: Optional[List[Dict]] = None,
) -> pd.DataFrame:
    """
    Build a per-event fallback CSV from available diagnostics.

    Priority: event-level opt_events (Batch 7) > aggregate reasons.
    """
    rows = []
    if not opt_diagnostics:
        return pd.DataFrame()

    # Batch 7: Use event-level logs when available
    opt_events = opt_diagnostics.get("opt_events", [])
    if opt_events:
        for event in opt_events:
            sd = event.get("signal_date", "")
            is_oos = _is_oos(sd) if sd else False
            rows.append({
                "signal_date": str(sd),
                "exec_date": str(event.get("exec_date", "")),
                "is_oos": is_oos,
                "fallback": event.get("fallback", False),
                "fallback_reason": event.get("fallback_reason", ""),
                "relaxation_level": event.get("relaxation_level", 0),
                "relaxation_applied": ", ".join(event.get("relaxation_applied", [])),
                "constraint_relaxation_mode": event.get("constraint_relaxation_mode", ""),
                "solver": event.get("solver", ""),
                "n_optimized": event.get("n_optimized", 0),
                "used_mu": event.get("used_mu", False),
                "low_optimizer_space": event.get("low_optimizer_space", False),
            })
        return pd.DataFrame(rows)

    # Fallback: aggregate reasons
    raw_reasons = opt_diagnostics.get("opt_fallback_reasons", {})
    for reason, count in raw_reasons.items():
        rows.append({
            "fallback_reason": reason,
            "count": count,
            "is_classified": any(
                any(p.lower() in str(reason).lower() for p in patterns)
                for patterns in _KNOWN_REASON_PATTERNS.values()
            ),
        })

    return pd.DataFrame(rows)


# ===================================================================
# Factor Stability
# ===================================================================


def analyze_factor_stability(
    factor_dfs: Dict[str, pd.DataFrame],
    fwd_rets: pd.DataFrame,
    signal_dates: List[int],
    ic_weighting=None,
) -> Dict[str, Any]:
    """
    Analyze factor stability over time.

    Parameters
    ----------
    factor_dfs : dict of factor_name → DataFrame
        Factor values with ts_code, trade_date, value columns.
    fwd_rets : DataFrame
        Forward returns with ts_code, trade_date, fwd_ret_* columns.
    signal_dates : list of int
        Rebalance signal dates.
    ic_weighting : ICWeighting, optional
        Pre-configured IC weighting instance for composite analysis.

    Returns
    -------
    dict with annual IC, coverage stats, and 2025+ decay markers.
    """
    if not factor_dfs or not signal_dates:
        return {
            "n_factors": len(factor_dfs) if factor_dfs else 0,
            "error": "No factor data or signal dates",
        }

    horizon_col = "fwd_ret_5d"
    if fwd_rets is not None and not fwd_rets.empty:
        available = [c for c in fwd_rets.columns if c.startswith("fwd_ret_")]
        if available:
            horizon_col = available[0]

    annual_ic = {}
    annual_coverage = {}
    factor_decay_2025 = {}
    factor_turnover_beta = {}

    for factor_name, factor_df in factor_dfs.items():
        if factor_df.empty:
            continue

        # Annual IC
        try:
            ic_by_year = _compute_annual_ic(factor_df, fwd_rets, signal_dates, horizon_col)
            annual_ic[factor_name] = ic_by_year
        except Exception as e:
            logger.warning(f"Annual IC computation failed for {factor_name}: {e}")
            annual_ic[factor_name] = {"error": str(e)}

        # Coverage
        try:
            coverage = _compute_coverage_stats(factor_df, signal_dates)
            annual_coverage[factor_name] = coverage
        except Exception as e:
            logger.warning(f"Coverage computation failed for {factor_name}: {e}")
            annual_coverage[factor_name] = {"error": str(e)}

        # 2025+ decay marker
        try:
            decay = _check_2025_decay(factor_df, fwd_rets, signal_dates, horizon_col)
            factor_decay_2025[factor_name] = decay
        except Exception as e:
            logger.warning(f"Decay check failed for {factor_name}: {e}")
            factor_decay_2025[factor_name] = {"error": str(e)}

        # Turnover contribution (approximated by IC × signal volatility)
        try:
            to_beta = _estimate_factor_turnover_contribution(factor_df, signal_dates)
            factor_turnover_beta[factor_name] = to_beta
        except Exception as e:
            logger.warning(f"Turnover beta failed for {factor_name}: {e}")
            factor_turnover_beta[factor_name] = {"error": str(e)}

    # Cost-sensitive factor markers
    cost_sensitive_factors = _identify_cost_sensitive_factors(factor_turnover_beta, annual_ic)

    return {
        "n_factors": len(factor_dfs),
        "annual_ic": annual_ic,
        "annual_coverage": annual_coverage,
        "factor_decay_2025": factor_decay_2025,
        "factor_turnover_beta": factor_turnover_beta,
        "cost_sensitive_factors": cost_sensitive_factors,
    }


def _compute_annual_ic(
    factor_df: pd.DataFrame,
    fwd_rets: pd.DataFrame,
    signal_dates: List[int],
    horizon_col: str,
) -> Dict[str, Any]:
    """Compute annual rank IC for a factor."""
    if factor_df.empty or fwd_rets is None or fwd_rets.empty:
        return {"error": "No data"}

    # Merge factor with forward returns
    if "value" not in factor_df.columns or horizon_col not in fwd_rets.columns:
        return {"error": "Missing required columns"}

    factor_df = factor_df.copy()
    factor_df["year"] = pd.to_datetime(
        factor_df["trade_date"].astype(str), format="%Y%m%d"
    ).dt.year

    annual_results = {}
    for year, year_data in factor_df.groupby("year"):
        year_dates = year_data["trade_date"].unique()
        # Only use dates that are in signal_dates
        valid_dates = [d for d in year_dates if d in signal_dates]
        if len(valid_dates) < 5:
            annual_results[str(year)] = {
                "mean_ic": float("nan"),
                "ic_positive_rate": float("nan"),
                "n_dates": len(valid_dates),
                "note": "Insufficient dates",
            }
            continue

        ics = []
        for dt in valid_dates:
            f_day = factor_df[factor_df["trade_date"] == dt]
            r_day = fwd_rets[fwd_rets["trade_date"] == dt]
            if f_day.empty or r_day.empty:
                continue

            merged = f_day.merge(r_day, on=["ts_code", "trade_date"], how="inner")
            if len(merged) < 10:
                continue

            ic = merged["value"].rank().corr(merged[horizon_col].rank())
            if np.isfinite(ic):
                ics.append(ic)

        if ics:
            annual_results[str(year)] = {
                "mean_ic": float(np.mean(ics)),
                "ic_positive_rate": float(np.mean([ic > 0 for ic in ics])),
                "ic_std": float(np.std(ics)),
                "n_dates": len(ics),
            }
        else:
            annual_results[str(year)] = {
                "mean_ic": float("nan"),
                "ic_positive_rate": float("nan"),
                "n_dates": 0,
                "note": "No valid IC observations",
            }

    return annual_results


def _compute_coverage_stats(
    factor_df: pd.DataFrame,
    signal_dates: List[int],
) -> Dict[str, Any]:
    """Compute coverage statistics for a factor."""
    if factor_df.empty:
        return {"error": "No factor data"}

    factor_dates = set(factor_df["trade_date"].unique())
    expected_dates = set(signal_dates)
    covered = factor_dates & expected_dates

    coverage_ratio = len(covered) / len(expected_dates) if expected_dates else 0.0

    # Per-date stock count
    date_coverage = {}
    for dt in sorted(covered)[:5]:  # sample first 5
        n_stocks = len(factor_df[factor_df["trade_date"] == dt])
        date_coverage[str(dt)] = n_stocks

    return {
        "coverage_ratio": coverage_ratio,
        "n_covered_dates": len(covered),
        "n_expected_dates": len(expected_dates),
        "n_missing_dates": len(expected_dates - covered),
        "sample_date_stock_counts": date_coverage,
    }


def _check_2025_decay(
    factor_df: pd.DataFrame,
    fwd_rets: pd.DataFrame,
    signal_dates: List[int],
    horizon_col: str,
) -> Dict[str, Any]:
    """Check for factor decay in 2025+ OOS period."""
    if factor_df.empty or fwd_rets is None or fwd_rets.empty:
        return {"decay_detected": False, "note": "No data"}

    # Pre-2025 IC
    pre_dates = [d for d in signal_dates if str(d) < "20250101"]
    post_dates = [d for d in signal_dates if str(d) >= "20250101"]

    pre_ic = _compute_period_ic(factor_df, fwd_rets, pre_dates, horizon_col)
    post_ic = _compute_period_ic(factor_df, fwd_rets, post_dates, horizon_col)

    decay = False
    if pre_ic is not None and post_ic is not None and pre_ic > 0:
        decay = post_ic < pre_ic * 0.5  # 50%+ decline

    return {
        "decay_detected": decay,
        "pre_2025_mean_ic": pre_ic if pre_ic is not None else float("nan"),
        "post_2025_mean_ic": post_ic if post_ic is not None else float("nan"),
        "pre_2025_n": len(pre_dates),
        "post_2025_n": len(post_dates),
    }


def _compute_period_ic(
    factor_df, fwd_rets, dates, horizon_col
) -> Optional[float]:
    """Compute mean IC for a period."""
    if not dates:
        return None
    ics = []
    for dt in dates:
        f_day = factor_df[factor_df["trade_date"] == dt]
        r_day = fwd_rets[fwd_rets["trade_date"] == dt]
        if f_day.empty or r_day.empty:
            continue
        merged = f_day.merge(r_day, on=["ts_code", "trade_date"], how="inner")
        if len(merged) < 10:
            continue
        ic = merged["value"].rank().corr(merged[horizon_col].rank())
        if np.isfinite(ic):
            ics.append(ic)
    return float(np.mean(ics)) if ics else None


def _estimate_factor_turnover_contribution(
    factor_df: pd.DataFrame,
    signal_dates: List[int],
) -> Dict[str, Any]:
    """
    Estimate how much a factor contributes to portfolio turnover.
    Uses signal autocorrelation as a proxy for stability.
    """
    if factor_df.empty or len(signal_dates) < 10:
        return {"error": "Insufficient data"}

    # Compute cross-sectional rank autocorrelation of the factor
    # Low autocorrelation → high turnover contribution
    factor_df = factor_df.copy()
    factor_df["trade_date"] = factor_df["trade_date"].astype(int)

    autocorrs = []
    for i, dt in enumerate(signal_dates[1:], 1):
        prev_dt = signal_dates[i - 1]
        prev_day = factor_df[factor_df["trade_date"] == prev_dt]
        curr_day = factor_df[factor_df["trade_date"] == dt]
        if prev_day.empty or curr_day.empty:
            continue

        common = set(prev_day["ts_code"]) & set(curr_day["ts_code"])
        if len(common) < 20:
            continue

        prev_rank = (
            prev_day[prev_day["ts_code"].isin(common)]
            .set_index("ts_code")["value"]
            .rank()
        )
        curr_rank = (
            curr_day[curr_day["ts_code"].isin(common)]
            .set_index("ts_code")["value"]
            .rank()
        )

        aligned = pd.concat([prev_rank, curr_rank], axis=1, join="inner").dropna()
        if len(aligned) < 20:
            continue

        autocorr = aligned.iloc[:, 0].corr(aligned.iloc[:, 1])
        if np.isfinite(autocorr):
            autocorrs.append(autocorr)

    avg_autocorr = float(np.mean(autocorrs)) if autocorrs else float("nan")

    return {
        "avg_rank_autocorrelation": avg_autocorr,
        "n_comparisons": len(autocorrs),
        "interpretation": (
            "Low autocorr → high turnover contribution"
            if not np.isnan(avg_autocorr) and avg_autocorr < 0.3
            else "Stable"
        ),
    }


def _identify_cost_sensitive_factors(
    factor_turnover_beta: Dict[str, Any],
    annual_ic: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Identify factors that are cost-sensitive: high turnover contribution + low IC."""
    sensitive = []
    for fname, to_data in factor_turnover_beta.items():
        if isinstance(to_data, dict) and "error" in to_data:
            continue
        autocorr = to_data.get("avg_rank_autocorrelation", float("nan"))
        if np.isnan(autocorr):
            continue

        ic_data = annual_ic.get(fname, {})
        # Get latest year IC
        ic_years = sorted(
            [k for k in ic_data.keys() if k.isdigit()],
            reverse=True,
        )
        latest_ic = float("nan")
        if ic_years and isinstance(ic_data.get(ic_years[0]), dict):
            latest_ic = ic_data[ic_years[0]].get("mean_ic", float("nan"))

        if autocorr < 0.3 and (np.isnan(latest_ic) or latest_ic < 0.02):
            sensitive.append({
                "factor": fname,
                "autocorrelation": autocorr,
                "latest_annual_ic": latest_ic,
                "recommendation": "Consider down-weighting or pruning",
            })

    return sensitive


# ===================================================================
# Combined Diagnostics Runner
# ===================================================================


class Phase5Diagnostics:
    """
    Run comprehensive Phase 5 failure diagnostics.

    Parameters
    ----------
    backtest_result : dict
        Full backtest result from run_backtest().
    opt_diagnostics : dict
        Optimizer diagnostics from _simulate().
    trades_log : list of dict
        Per-rebalance trade records.
    holdings_log : list of dict
        Per-rebalance holdings records.
    portfolio_values : list of dict
        Per-period portfolio value records.
    factor_dfs : dict, optional
        Factor DataFrames for stability analysis.
    fwd_rets : DataFrame, optional
        Forward returns for IC computation.
    signal_dates : list of int, optional
        Rebalance signal dates.
    """

    def __init__(
        self,
        backtest_result: Dict[str, Any],
        opt_diagnostics: Optional[Dict[str, Any]] = None,
        trades_log: Optional[List[Dict]] = None,
        holdings_log: Optional[List[Dict]] = None,
        portfolio_values: Optional[List[Dict]] = None,
        factor_dfs: Optional[Dict[str, pd.DataFrame]] = None,
        fwd_rets: Optional[pd.DataFrame] = None,
        signal_dates: Optional[List[int]] = None,
    ):
        self.backtest_result = backtest_result
        self.opt_diagnostics = opt_diagnostics or backtest_result.get("opt_diagnostics", {})
        self.trades_log = trades_log or []
        self.holdings_log = holdings_log or []
        self.portfolio_values = portfolio_values or []
        self.factor_dfs = factor_dfs or {}
        self.fwd_rets = fwd_rets
        self.signal_dates = signal_dates or []

        self._turnover_diag = None
        self._cost_diag = None
        self._fallback_diag = None
        self._factor_diag = None

    # ------------------------------------------------------------------
    # Run all diagnostics
    # ------------------------------------------------------------------
    def run_all(self) -> Dict[str, Any]:
        """Run all diagnostic analyses."""
        self._turnover_diag = decompose_turnover(
            self.trades_log, self.holdings_log, self.portfolio_values
        )
        self._cost_diag = decompose_costs(self.portfolio_values)
        self._fallback_diag = analyze_fallback(self.opt_diagnostics, self.trades_log)
        self._factor_diag = analyze_factor_stability(
            self.factor_dfs, self.fwd_rets, self.signal_dates
        )

        return {
            "turnover": self._turnover_diag,
            "cost": self._cost_diag,
            "fallback": self._fallback_diag,
            "factor_stability": self._factor_diag,
        }

    # ------------------------------------------------------------------
    # Generate Markdown report
    # ------------------------------------------------------------------
    def generate_report(self) -> str:
        """Generate comprehensive diagnostics report in Markdown."""
        if self._turnover_diag is None:
            self.run_all()

        lines = []
        lines.append("# Phase 5 Failure Diagnostics Report")
        lines.append(f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")

        # Executive summary
        lines.append("## Executive Summary")
        lines.append("")

        # Turnover
        to = self._turnover_diag or {}
        avg_to = to.get("avg_turnover", DATA_MISSING_SENTINEL)
        lines.append(f"- **Average Turnover**: {_fmt_val(avg_to, '.4f')}")
        lines.append(f"- **Turnover P95**: {_fmt_val(to.get('turnover_p95'), '.4f')}")
        lines.append(f"- **Max Turnover Date**: {to.get('max_turnover_date', DATA_MISSING_SENTINEL)}")
        lines.append("")

        # Cost
        cost = self._cost_diag or {}
        lines.append(f"- **Net Annualized Return**: {_fmt_val(cost.get('net_annualized_return'), '.4%')}")
        lines.append(f"- **1x Cost Drag**: {_fmt_val(cost.get('cost_drag_1x_annualized'), '.4%')}")
        lines.append(f"- **2x Cost Drag**: {_fmt_val(cost.get('cost_drag_2x_annualized'), '.4%')}")
        lines.append(f"- **Turnover-Cost Beta**: {_fmt_val(cost.get('turnover_cost_beta'), '.2f')}")
        lines.append("")

        # Fallback
        fb = self._fallback_diag or {}
        lines.append(f"- **Optimizer Fallback Rate**: {_fmt_val(fb.get('fallback_rate'), '.4f')}")
        lines.append(f"- **Unknown Fallback Rate**: {_fmt_val(fb.get('unknown_fallback_rate'), '.4f')}")
        lines.append("")

        # Turnover section
        lines.append("---")
        lines.append("## 1. Turnover Attribution")
        lines.append("")
        self._append_turnover_section(lines, to)

        # Cost section
        lines.append("---")
        lines.append("## 2. Cost Attribution")
        lines.append("")
        self._append_cost_section(lines, cost)

        # Fallback section
        lines.append("---")
        lines.append("## 3. Fallback Attribution")
        lines.append("")
        self._append_fallback_section(lines, fb)

        # Factor stability section
        lines.append("---")
        lines.append("## 4. Factor Stability")
        lines.append("")
        self._append_factor_section(lines, self._factor_diag or {})

        # OOS summary
        lines.append("---")
        lines.append("## 5. OOS (2025+) Summary")
        lines.append("")
        lines.append(f"- IS Avg Turnover: {_fmt_val(to.get('is_avg_turnover'), '.4f')}")
        lines.append(f"- OOS Avg Turnover: {_fmt_val(to.get('oos_avg_turnover'), '.4f')}")
        lines.append(f"- IS Avg Cost (bps): {_fmt_val(cost.get('is_avg_cost_bps'), '.2f')}")
        lines.append(f"- OOS Avg Cost (bps): {_fmt_val(cost.get('oos_avg_cost_bps'), '.2f')}")

        return "\n".join(lines)

    def _append_turnover_section(self, lines, to):
        lines.append(f"| Metric | Value |")
        lines.append(f"|--------|-------|")
        for key in ["avg_turnover", "turnover_p50", "turnover_p75", "turnover_p95",
                     "max_turnover", "max_turnover_date"]:
            val = to.get(key, DATA_MISSING_SENTINEL)
            lines.append(f"| {key} | {_fmt_val(val, '.4f')} |")
        lines.append("")

        # Entry/exit/within
        entry = to.get("entry_contribution_pct", float("nan"))
        exit_c = to.get("exit_contribution_pct", float("nan"))
        within = to.get("within_portfolio_contribution_pct", float("nan"))
        lines.append("### Turnover Decomposition")
        lines.append("")
        lines.append(f"- Entry (new stocks): {_fmt_pct(entry)}")
        lines.append(f"- Exit (dropped stocks): {_fmt_pct(exit_c)}")
        lines.append(f"- Within-portfolio rebalancing: {_fmt_pct(within)}")
        lines.append("")

        # Top dates
        top_dates = to.get("top_turnover_dates", [])
        if top_dates:
            lines.append("### Highest Turnover Dates")
            lines.append("")
            lines.append("| Date | Turnover |")
            lines.append("|------|----------|")
            for d in top_dates[:10]:
                lines.append(
                    f"| {d.get('signal_date', 'N/A')} | "
                    f"{_fmt_val(d.get('turnover'), '.4f')} |"
                )
            lines.append("")

    def _append_cost_section(self, lines, cost):
        lines.append(f"| Metric | Value |")
        lines.append(f"|--------|-------|")
        for key in ["gross_annualized_return", "net_annualized_return",
                     "cost_drag_1x_annualized", "cost_drag_2x_annualized",
                     "net_2x_annualized_return", "turnover_cost_beta",
                     "total_cost_bps", "avg_cost_bps_per_period"]:
            val = cost.get(key, DATA_MISSING_SENTINEL)
            lines.append(f"| {key} | {_fmt_val(val, '.4f')} |")
        lines.append("")

        high_cost = cost.get("high_cost_dates", [])
        if high_cost:
            lines.append("### Highest Cost Dates")
            lines.append("")
            lines.append("| Date | Cost (bps) |")
            lines.append("|------|------------|")
            for d in high_cost[:10]:
                lines.append(
                    f"| {d.get('signal_date', 'N/A')} | "
                    f"{_fmt_val(d.get('cost_bps'), '.2f')} |"
                )
            lines.append("")

        # Cost sensitivity
        sens = cost.get("cost_sensitivity", {})
        if sens:
            lines.append("### Cost Sensitivity (Multiplier Grid)")
            lines.append("")
            lines.append("| Multiplier | Annualized Return | Excess vs Net |")
            lines.append("|------------|-------------------|---------------|")
            for key, val in sens.items():
                lines.append(f"| {key} | {_fmt_val(val, '.4%')} | |")
            lines.append("")

    def _append_fallback_section(self, lines, fb):
        lines.append(f"| Metric | Value |")
        lines.append(f"|--------|-------|")
        for key in ["fallback_rate", "n_total", "n_fallback", "n_success",
                     "unknown_fallback_rate", "unknown_count"]:
            val = fb.get(key, DATA_MISSING_SENTINEL)
            lines.append(f"| {key} | {_fmt_val(val, '.4f')} |")
        lines.append("")

        reasons = fb.get("fallback_reasons", {})
        if reasons:
            lines.append("### Fallback Reason Breakdown")
            lines.append("")
            lines.append("| Reason | Count |")
            lines.append("|--------|-------|")
            for reason, count in reasons.items():
                lines.append(f"| {reason} | {count} |")
            lines.append("")

        raw = fb.get("raw_fallback_reasons", {})
        if raw:
            lines.append("### Raw Fallback Reasons")
            lines.append("")
            for reason, count in raw.items():
                lines.append(f"- {reason}: {count}")
            lines.append("")

    def _append_factor_section(self, lines, fs):
        lines.append(f"- **Number of Factors Analyzed**: {fs.get('n_factors', 0)}")
        lines.append("")

        # Annual IC table
        annual_ic = fs.get("annual_ic", {})
        if annual_ic:
            lines.append("### Annual IC by Factor")
            lines.append("")
            # Collect all years
            all_years = set()
            for fname, year_data in annual_ic.items():
                if isinstance(year_data, dict):
                    all_years.update(k for k in year_data.keys() if k.isdigit())
            years_sorted = sorted(all_years)

            if years_sorted:
                header = "| Factor | " + " | ".join(years_sorted) + " |"
                lines.append(header)
                sep = "|--------|" + "|".join(["--------"] * len(years_sorted)) + "|"
                lines.append(sep)
                for fname, year_data in sorted(annual_ic.items()):
                    if not isinstance(year_data, dict) or "error" in year_data:
                        continue
                    vals = []
                    for yr in years_sorted:
                        yd = year_data.get(str(yr), {})
                        if isinstance(yd, dict):
                            ic = yd.get("mean_ic", float("nan"))
                            vals.append(_fmt_val(ic, ".4f"))
                        else:
                            vals.append("N/A")
                    lines.append(f"| {fname} | " + " | ".join(vals) + " |")
                lines.append("")

        # 2025+ decay
        decay_data = fs.get("factor_decay_2025", {})
        if decay_data:
            lines.append("### 2025+ Decay Markers")
            lines.append("")
            lines.append("| Factor | Pre-2025 IC | Post-2025 IC | Decay Detected |")
            lines.append("|--------|-------------|--------------|----------------|")
            for fname, dd in sorted(decay_data.items()):
                if isinstance(dd, dict) and "error" not in dd:
                    lines.append(
                        f"| {fname} | {_fmt_val(dd.get('pre_2025_mean_ic'), '.4f')} | "
                        f"{_fmt_val(dd.get('post_2025_mean_ic'), '.4f')} | "
                        f"{dd.get('decay_detected', False)} |"
                    )
            lines.append("")

        # Cost-sensitive factors
        cost_sens = fs.get("cost_sensitive_factors", [])
        if cost_sens:
            lines.append("### Cost-Sensitive Factor Markers")
            lines.append("")
            for item in cost_sens:
                lines.append(
                    f"- **{item.get('factor')}**: autocorr={_fmt_val(item.get('autocorrelation'), '.3f')}, "
                    f"latest_IC={_fmt_val(item.get('latest_annual_ic'), '.4f')} "
                    f"→ {item.get('recommendation', '')}"
                )
            lines.append("")

    # ------------------------------------------------------------------
    # Export to JSON
    # ------------------------------------------------------------------
    def to_json(self, path: Optional[Path] = None) -> Dict[str, Any]:
        """Export all diagnostics as a JSON-serializable dict."""
        if self._turnover_diag is None:
            self.run_all()

        result = {
            "generated_at": datetime.now().isoformat(),
            "turnover": _make_json_safe(self._turnover_diag),
            "cost": _make_json_safe(self._cost_diag),
            "fallback": _make_json_safe(self._fallback_diag),
            "factor_stability": _make_json_safe(self._factor_diag),
        }

        if path:
            path = Path(path)
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, ensure_ascii=False, default=str)
            logger.info(f"Diagnostics JSON saved to {path}")

        return result

    # ------------------------------------------------------------------
    # Export fallback events CSV
    # ------------------------------------------------------------------
    def export_fallback_csv(self, path: Optional[Path] = None) -> pd.DataFrame:
        """Export fallback events as CSV."""
        df = build_fallback_events_csv(self.opt_diagnostics)
        if path:
            path = Path(path)
            path.parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(path, index=False, encoding="utf-8")
            logger.info(f"Fallback events CSV saved to {path}")
        return df

    # ------------------------------------------------------------------
    # Export turnover breakdown CSV
    # ------------------------------------------------------------------
    def export_turnover_csv(self, path: Optional[Path] = None) -> pd.DataFrame:
        """Export turnover breakdown as CSV."""
        if self._turnover_diag is None:
            self.run_all()

        rows = []
        to = self._turnover_diag or {}
        for key, val in to.items():
            if key in ("top_turnover_dates", "weekly_vs_monthly", "error"):
                continue
            rows.append({"metric": key, "value": val})

        # Append top dates
        for item in to.get("top_turnover_dates", []):
            rows.append({
                "metric": "top_turnover_date",
                "date": item.get("signal_date", ""),
                "value": item.get("turnover", ""),
            })

        df = pd.DataFrame(rows)
        if path:
            path = Path(path)
            path.parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(path, index=False, encoding="utf-8")
            logger.info(f"Turnover breakdown CSV saved to {path}")
        return df


# ===================================================================
# Helpers
# ===================================================================


def _fmt_val(val, fmt: str) -> str:
    """Format a value for display, handling DATA_MISSING and NaN."""
    if val is None or val == DATA_MISSING_SENTINEL:
        return DATA_MISSING_SENTINEL
    if isinstance(val, float) and np.isnan(val):
        return DATA_MISSING_SENTINEL
    if isinstance(val, float):
        try:
            return format(val, fmt)
        except (ValueError, TypeError):
            return str(val)
    return str(val)


def _fmt_pct(val) -> str:
    """Format as percentage."""
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return DATA_MISSING_SENTINEL
    try:
        return f"{float(val):.2%}"
    except (TypeError, ValueError):
        return str(val)


def _make_json_safe(obj: Any) -> Any:
    """Recursively convert to JSON-safe types."""
    if isinstance(obj, dict):
        return {str(k): _make_json_safe(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [_make_json_safe(v) for v in obj]
    elif isinstance(obj, (np.integer,)):
        return int(obj)
    elif isinstance(obj, (np.floating,)):
        return float(obj) if np.isfinite(obj) else None
    elif isinstance(obj, (np.bool_,)):
        return bool(obj)
    elif isinstance(obj, (np.ndarray,)):
        return obj.tolist()
    elif isinstance(obj, float) and np.isnan(obj):
        return None
    return obj

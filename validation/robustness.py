"""
Robustness testing framework.

Tests strategy robustness across:
- Cost sensitivity (1x, 2x, 3x costs)
- Slippage sensitivity (1x, 2x)
- Rebalance frequency (weekly, bi-weekly, monthly)
- Portfolio size (top 30, 50, 100)
- Single stock cap (1%, 2%, 3%)
- Industry deviation (tight, loose)
- Market regime segments (2016-2018, 2019-2021, 2022-2024, 2025+)
- Parameter sensitivity

Final Go/No-Go checklist:
- Cost-adjusted excess return > 0
- IR above threshold
- Max relative drawdown acceptable
- Cost 2x still doesn't break
- Turnover explainable
- Recent 2-year OOS not decayed
"""

import json
import logging
from typing import Optional, List, Dict, Any, Callable, Tuple
from copy import deepcopy

import numpy as np
import pandas as pd


def _safe_fmt(val, fmt: str) -> str:
    """Format a value safely for report output."""
    if val is None:
        return "N/A"
    if isinstance(val, float) and np.isnan(val):
        return "DATA_MISSING"
    try:
        return format(float(val), fmt)
    except (TypeError, ValueError):
        return str(val)

logger = logging.getLogger(__name__)


class RobustnessTester:
    """
    Multi-dimensional robustness testing for portfolio strategies.
    """

    def __init__(self, backtest_fn: Callable[..., Dict[str, Any]]):
        """
        Parameters
        ----------
        backtest_fn : callable
            Function that takes config parameters and returns backtest results.
            Signature: backtest_fn(**kwargs) -> dict of metrics.
        """
        self.backtest_fn = backtest_fn
        self._results: Dict[str, Dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # Test suites
    # ------------------------------------------------------------------
    def test_cost_sensitivity(self, base_config: dict) -> pd.DataFrame:
        """Test sensitivity to transaction costs at 1x, 2x, 3x."""
        results = []
        for multiplier, label in [(1.0, "1x"), (2.0, "2x"), (3.0, "3x")]:
            config = deepcopy(base_config)
            config["cost_multiplier"] = multiplier
            result = self.backtest_fn(**config)
            result["cost_scenario"] = label
            results.append(result)
            self._results[f"cost_{label}"] = result

        return pd.DataFrame(results)

    def test_slippage_sensitivity(self, base_config: dict) -> pd.DataFrame:
        """Test sensitivity to slippage assumptions."""
        results = []
        for slippage_bps, label in [(5.0, "5bp"), (10.0, "10bp"), (20.0, "20bp")]:
            config = deepcopy(base_config)
            config["slippage_bps"] = slippage_bps
            result = self.backtest_fn(**config)
            result["slippage_scenario"] = label
            results.append(result)
            self._results[f"slippage_{label}"] = result

        return pd.DataFrame(results)

    def test_rebalance_frequency(self, base_config: dict,
                                 frequencies: Optional[List[tuple]] = None
                                 ) -> pd.DataFrame:
        """
        Test different rebalance frequencies.

        Parameters
        ----------
        frequencies : list of (freq_str, label) tuples, optional
            Default: weekly and monthly only.
            Biweekly is NOT included by default because PortfolioBacktester
            does not support it.
        """
        if frequencies is None:
            frequencies = [("weekly", "Weekly"), ("monthly", "Monthly")]
        results = []
        for freq, label in frequencies:
            config = deepcopy(base_config)
            config["rebalance_freq"] = freq
            result = self.backtest_fn(**config)
            result["rebalance_freq"] = label
            results.append(result)
            self._results[f"freq_{label}"] = result

        return pd.DataFrame(results)

    def test_portfolio_size(self, base_config: dict) -> pd.DataFrame:
        """Test different portfolio sizes."""
        results = []
        for top_n, label in [(30, "Top30"), (50, "Top50"), (100, "Top100")]:
            config = deepcopy(base_config)
            config["top_n"] = top_n
            result = self.backtest_fn(**config)
            result["portfolio_size"] = label
            results.append(result)
            self._results[f"size_{label}"] = result

        return pd.DataFrame(results)

    def test_stock_caps(self, base_config: dict) -> pd.DataFrame:
        """Test single-stock weight caps."""
        results = []
        for cap, label in [(0.01, "1%"), (0.02, "2%"), (0.03, "3%)")]:
            config = deepcopy(base_config)
            config["weight_max"] = cap
            result = self.backtest_fn(**config)
            result["stock_cap"] = label
            results.append(result)
            self._results[f"cap_{label}"] = result

        return pd.DataFrame(results)

    def test_industry_deviation(self, base_config: dict) -> pd.DataFrame:
        """Test industry deviation constraints."""
        results = []
        for dev, label in [(0.03, "Tight(3%)"), (0.05, "Medium(5%)"),
                           (0.10, "Loose(10%)")]:
            config = deepcopy(base_config)
            config["industry_deviation_max"] = dev
            result = self.backtest_fn(**config)
            result["industry_deviation"] = label
            results.append(result)
            self._results[f"ind_{label}"] = result

        return pd.DataFrame(results)

    def test_market_regimes(self, base_config: dict,
                            regimes: Optional[List[Tuple[str, str, str]]] = None
                            ) -> pd.DataFrame:
        """
        Test performance across market regimes.

        Parameters
        ----------
        regimes : list of (start_date, end_date, label) tuples.
        """
        if regimes is None:
            regimes = [
                ("20160101", "20181231", "2016-2018 Recovery/Bear"),
                ("20190101", "20211231", "2019-2021 Bull/Rotation"),
                ("20220101", "20241231", "2022-2024 Bear/Redividend"),
                ("20250101", "20260601", "2025+ OOS"),
            ]

        results = []
        for start, end, label in regimes:
            config = deepcopy(base_config)
            config["start_date"] = start
            config["end_date"] = end
            result = self.backtest_fn(**config)
            result["regime"] = label
            result["start_date"] = start
            result["end_date"] = end

            # Phase 1: DATA_MISSING detection — if backtest returned
            # error or < 5 periods, mark as DATA_MISSING (NOT zero-filled)
            is_missing = (
                result.get("error") is not None
                or result.get("n_periods", 0) < 5
            )
            result["data_missing"] = is_missing
            if is_missing:
                logger.warning(
                    f"Regime {label} ({start}→{end}): DATA_MISSING — "
                    f"n_periods={result.get('n_periods', 0)}, "
                    f"error={result.get('error', 'N/A')}"
                )
                # Zero out metrics to prevent accidental PASS with 0s
                for key in ("annualized_return", "annualized_excess_return",
                           "sharpe_ratio", "information_ratio", "max_drawdown",
                           "avg_turnover"):
                    if key in result and result.get("data_missing"):
                        result[key] = float("nan")

            results.append(result)
            self._results[f"regime_{label}"] = result

        return pd.DataFrame(results)

    # ------------------------------------------------------------------
    # Parameter sensitivity (grid search)
    # ------------------------------------------------------------------
    def test_turnover_scenarios(self, base_config: dict) -> pd.DataFrame:
        """
        Test different turnover reduction scenarios (Phase 3).

        Scenarios:
        - weekly (baseline)
        - monthly
        - buffer_top50_80 (entry=50, exit=80)
        - buffer_top100_150 (entry=100, exit=150)
        """
        results = []

        # Baseline: weekly
        config = deepcopy(base_config)
        config["rebalance_freq"] = "weekly"
        result = self.backtest_fn(**config)
        result["turnover_scenario"] = "weekly_baseline"
        results.append(result)
        self._results["to_weekly_baseline"] = result

        # Monthly
        config = deepcopy(base_config)
        config["rebalance_freq"] = "monthly"
        result = self.backtest_fn(**config)
        result["turnover_scenario"] = "monthly"
        results.append(result)
        self._results["to_monthly"] = result

        # Buffer Top50/80
        config = deepcopy(base_config)
        config["entry_rank"] = 50
        config["exit_rank"] = 80
        config["top_n"] = 50
        result = self.backtest_fn(**config)
        result["turnover_scenario"] = "buffer_top50_80"
        results.append(result)
        self._results["to_buffer_top50_80"] = result

        # Buffer Top100/150
        config = deepcopy(base_config)
        config["entry_rank"] = 100
        config["exit_rank"] = 150
        config["top_n"] = 100
        result = self.backtest_fn(**config)
        result["turnover_scenario"] = "buffer_top100_150"
        results.append(result)
        self._results["to_buffer_top100_150"] = result

        return pd.DataFrame(results)

    def test_parameter_sensitivity(self, base_config: dict,
                                   param_name: str,
                                   param_values: List[Any]) -> pd.DataFrame:
        """
        Test sensitivity to a single parameter.

        Parameters
        ----------
        param_name : str
            Parameter name to vary.
        param_values : list
            Values to test.
        """
        results = []
        for val in param_values:
            config = deepcopy(base_config)
            config[param_name] = val
            result = self.backtest_fn(**config)
            result[param_name] = val
            results.append(result)

        return pd.DataFrame(results)

    # ------------------------------------------------------------------
    # Go/No-Go assessment
    # ------------------------------------------------------------------
    def go_nogo_check(self,
                      base_result: Dict[str, Any],
                      cost_2x_result: Optional[Dict[str, Any]] = None,
                      recent_oos_result: Optional[Dict[str, Any]] = None,
                      ir_threshold: float = 0.3,
                      max_dd_threshold: float = 0.25,
                      min_excess_return: float = 0.03,
                      min_oos_excess: float = 0.02,
                      max_turnover: float = 0.30) -> Dict[str, Any]:
        """
        Final Go/No-Go decision checklist.

        New (data quality preconditions):
        Before evaluating performance checks, verify that the underlying
        data is valid. If ANY data quality precondition fails, the verdict
        is immediately NO_GO_DATA_INVALID — regardless of IR or excess return.

        Parameters
        ----------
        base_result : dict
            Base case backtest result.
        cost_2x_result : dict, optional
            Result with 2x costs.
        recent_oos_result : dict, optional
            Most recent 2-year OOS result.
        ir_threshold : float
            Minimum acceptable IR (target > 0.5).
        max_dd_threshold : float
            Maximum acceptable drawdown (< 25%).
        min_excess_return : float
            Minimum full-sample annualized excess return (> 3%).
        min_oos_excess : float
            Minimum recent 2-year OOS excess return (> 2%).
        max_turnover : float
            Maximum acceptable average turnover (< 30%).

        Returns
        -------
        dict with each check, overall verdict, and `overall` field
        (GO, NO-GO, or NO_GO_DATA_INVALID).
        """
        checks = {}

        # ================================================================
        # DATA QUALITY PRECONDITIONS (must ALL pass for any GO verdict)
        #
        # When a field is ABSENT from base_result (not just UNKNOWN),
        # the precondition is logged as a WARNING but does NOT fail.
        # This provides backward compatibility with test code that does
        # not yet populate these fields.
        #
        # When a field is PRESENT with a non-OK value, the precondition
        # is a HARD FAIL and the verdict is NO_GO_DATA_INVALID.
        # ================================================================
        preconditions_failed = []

        # PC1: data_quality_status must be OK
        if "data_quality_status" in base_result:
            dq_status = base_result.get("data_quality_status", "UNKNOWN")
            if dq_status != "OK":
                preconditions_failed.append(f"data_quality_status={dq_status}")
        else:
            logger.debug("go_nogo: data_quality_status not set in base_result — skipping precondition")

        # PC2: benchmark_status must be OK
        if "benchmark_status" in base_result:
            bm_status = base_result.get("benchmark_status", "UNKNOWN")
            if bm_status != "OK":
                preconditions_failed.append(
                    f"benchmark_status={bm_status}; "
                    f"reason={base_result.get('benchmark_failure_reason', 'N/A')}"
                )
        else:
            logger.debug("go_nogo: benchmark_status not set in base_result — skipping precondition")

        # PC3: price_quality_status must be OK
        if "price_quality_status" in base_result:
            pq_status = base_result.get("price_quality_status", "UNKNOWN")
            if pq_status != "OK":
                preconditions_failed.append(f"price_quality_status={pq_status}")
        else:
            logger.debug("go_nogo: price_quality_status not set in base_result — skipping precondition")

        # PC4: max_single_period_return must not exceed extreme threshold
        if "max_single_period_return" in base_result:
            max_single = base_result.get("max_single_period_return")
            if max_single is not None and isinstance(max_single, (int, float)):
                if abs(max_single) > 5.0:  # 500% single-period return
                    preconditions_failed.append(
                        f"max_single_period_return={max_single:.2%} exceeds 500%; "
                        f"date={base_result.get('max_single_period_return_date', 'N/A')}"
                    )

        # PC5: minimum sample periods for stable estimates
        if "n_periods" in base_result:
            n_periods = base_result.get("n_periods", 0)
            if n_periods < 5:
                preconditions_failed.append(
                    f"n_periods={n_periods} < 5 (INSUFFICIENT for any estimate)"
                )
            elif n_periods < 26:
                # < 26 weekly periods = UNSTABLE but not fatal — STRONG WARNING
                logger.warning(
                    f"go_nogo_check: n_periods={n_periods} < 26 — "
                    f"annualized metrics are UNSTABLE"
                )
        else:
            logger.debug("go_nogo: n_periods not set in base_result — skipping precondition")

        if preconditions_failed:
            logger.error(
                f"go_nogo_check: DATA INVALID — "
                f"preconditions failed: {'; '.join(preconditions_failed)}"
            )
            checks["data_preconditions"] = {
                "pass": False,
                "value": "; ".join(preconditions_failed),
                "threshold": "ALL OK",
                "description": (
                    "Data quality preconditions: data_quality, benchmark, "
                    "price_quality, max_single_period_return, n_periods"
                ),
                "severity": "hard",
            }
            return {
                "checks": checks,
                "hard_checks": {"data_preconditions": checks["data_preconditions"]},
                "warning_checks": {},
                "verdict": "NO-GO (DATA_INVALID)",
                "overall": "NO_GO_DATA_INVALID",
                "n_pass": 0,
                "n_total": 1,
                "n_hard_pass": 0,
                "n_hard_total": 1,
                "n_warning_total": 0,
                "n_warning_fail": 0,
                "pass_rate": 0.0,
            }

        # Is data actually available?
        is_missing = base_result.get("data_missing", False) or base_result.get("error") is not None

        # 1. Full sample annualized excess > 3% (HARD)
        ann_excess = base_result.get("annualized_excess_return", 0)
        checks["full_sample_excess"] = {
            "pass": (not is_missing) and ann_excess > min_excess_return,
            "value": ann_excess if not is_missing else float("nan"),
            "threshold": min_excess_return,
            "description": "Full sample ann. excess > 3%",
            "severity": "hard",
        }

        # 2. IR above threshold (> 0.3, target > 0.5) (HARD)
        ir = base_result.get("information_ratio", 0)
        checks["information_ratio"] = {
            "pass": (not is_missing) and ir > ir_threshold,
            "value": ir if not is_missing else float("nan"),
            "threshold": ir_threshold,
            "description": "IR > 0.3 (target > 0.5)",
            "severity": "hard",
        }

        # 3. Max drawdown acceptable (< 25%) (HARD)
        max_dd = base_result.get("max_drawdown", -1)
        checks["max_drawdown"] = {
            "pass": abs(max_dd) < max_dd_threshold,
            "value": max_dd,
            "threshold": max_dd_threshold,
            "description": "Max DD < 25%",
            "severity": "hard",
        }

        # 4. Cost 2x survivable (excess > -1%, prefer positive) (HARD)
        if cost_2x_result and not cost_2x_result.get("error"):
            cost_2x_excess = cost_2x_result.get("annualized_excess_return", 0)
            checks["cost_2x_survivable"] = {
                "pass": cost_2x_excess > -0.01,
                "value": cost_2x_excess,
                "threshold": -0.01,
                "description": "2x cost excess > -1% (prefer > 0)",
                "severity": "hard",
            }

        # 5. Recent OOS (2025+) — must have positive excess (HARD)
        if recent_oos_result is not None:
            oos_is_missing = (
                recent_oos_result.get("error") is not None
                or recent_oos_result.get("n_periods", 0) < 5
                or recent_oos_result.get("data_missing", False)
            )
            oos_excess = recent_oos_result.get("annualized_excess_return", 0)
            checks["recent_oos"] = {
                "pass": (not oos_is_missing) and oos_excess > min_oos_excess,
                "value": oos_excess if not oos_is_missing else float("nan"),
                "threshold": min_oos_excess,
                "description": "Recent 2yr OOS ann. excess > 2%",
                "severity": "hard",
            }
            if oos_is_missing:
                checks["recent_oos_data"] = {
                    "pass": False,
                    "value": "DATA_MISSING",
                    "threshold": "AVAILABLE",
                    "description": "Recent OOS data must be available",
                    "severity": "hard",
                }
            else:
                oos_fallback_rate = recent_oos_result.get(
                    "optimizer_fallback_rate", None
                )
                if oos_fallback_rate is not None:
                    checks["recent_oos_optimizer_fallback"] = {
                        "pass": oos_fallback_rate < 0.20,
                        "value": oos_fallback_rate,
                        "threshold": 0.20,
                        "description": "Recent OOS optimizer fallback < 20%",
                        "severity": "hard",
                    }

        # 6. Turnover reasonable (< 30%) (HARD)
        turnover = base_result.get("avg_turnover", 0)
        checks["avg_turnover"] = {
            "pass": turnover < max_turnover,
            "value": turnover,
            "threshold": max_turnover,
            "description": "Avg turnover < 30%",
            "severity": "hard",
        }

        # 7. Positive Sharpe (HARD)
        sharpe = base_result.get("sharpe_ratio", 0)
        checks["positive_sharpe"] = {
            "pass": (not is_missing) and sharpe > 0,
            "value": sharpe if not is_missing else float("nan"),
            "threshold": 0,
            "description": "Positive Sharpe ratio",
            "severity": "hard",
        }

        # 8. Optimizer fallback rate (HARD)
        fallback_rate = base_result.get("optimizer_fallback_rate", None)
        if fallback_rate is not None:
            checks["optimizer_fallback"] = {
                "pass": fallback_rate < 0.20,
                "value": fallback_rate,
                "threshold": 0.20,
                "description": "Optimizer fallback < 20%",
                "severity": "hard",
            }

        # 9. Optimizer relaxation rate (WARNING — does not force NO-GO)
        relaxation_rate = base_result.get("optimizer_relaxation_rate", None)
        if relaxation_rate is not None:
            checks["optimizer_relaxation"] = {
                "pass": relaxation_rate < 0.20,
                "value": relaxation_rate,
                "threshold": 0.20,
                "description": "Optimizer relaxation < 20% (WARNING)",
                "severity": "warning",
            }

        # 10. Fallback unknown rate (HARD NO-GO)
        fallback_reasons = base_result.get("opt_fallback_reasons", {})
        if fallback_reasons:
            unknown_count = sum(
                v for k, v in fallback_reasons.items()
                if not any(p in str(k).lower().replace(" ", "_")
                          for p in ("infeasible", "missing_mu", "insufficient",
                                    "convergence", "solver", "non_finite",
                                    "zero_weights"))
            )
            total_opt = base_result.get("opt_n_total", 1)
            unknown_rate = unknown_count / total_opt if total_opt > 0 else 0.0
            checks["fallback_unknown_rate"] = {
                "pass": unknown_rate < 0.05,
                "value": unknown_rate,
                "threshold": 0.05,
                "description": "Unknown fallback rate < 5% (HARD NO-GO)",
                "severity": "hard",
            }

        # 11. Cost drag 2x check (HARD)
        if cost_2x_result and not cost_2x_result.get("error"):
            cost_2x_drag = cost_2x_result.get("cost_drag_2x_annualized",
                cost_2x_result.get("annualized_excess_return", 0))
            checks["cost_drag_2x"] = {
                "pass": isinstance(cost_2x_drag, (int, float))
                    and cost_2x_drag > -0.02,
                "value": cost_2x_drag if isinstance(cost_2x_drag, (int, float))
                    else float("nan"),
                "threshold": -0.02,
                "description": "2x cost drag > -2%",
                "severity": "hard",
            }

        # 12. Turnover P95 (WARNING)
        turnover_p95 = base_result.get("turnover_p95", None)
        if turnover_p95 is not None:
            checks["turnover_p95"] = {
                "pass": turnover_p95 < 0.60,
                "value": turnover_p95,
                "threshold": 0.60,
                "description": "Turnover P95 < 60% (WARNING)",
                "severity": "warning",
            }

        # 13. DATA_MISSING hard check (HARD)
        if is_missing:
            checks["data_available"] = {
                "pass": False,
                "value": "DATA_MISSING",
                "threshold": "AVAILABLE",
                "description": "Base result data must be available",
                "severity": "hard",
            }

        # NaN/zero guard (HARD)
        for key in ["information_ratio", "annualized_excess_return",
                     "sharpe_ratio"]:
            val = base_result.get(key, float("nan"))
            if isinstance(val, float) and np.isnan(val):
                checks[f"nan_guard_{key}"] = {
                    "pass": False,
                    "value": "NaN",
                    "threshold": "finite",
                    "description": f"{key} must not be NaN",
                    "severity": "hard",
                }

        # Overall verdict (Batch 6 fix): only hard checks determine GO/NO-GO
        hard_checks = {k: c for k, c in checks.items()
                       if c.get("severity", "hard") == "hard"}
        warning_checks = {k: c for k, c in checks.items()
                         if c.get("severity", "hard") == "warning"}

        hard_all_pass = all(c["pass"] for c in hard_checks.values())
        n_hard_pass = sum(1 for c in hard_checks.values() if c["pass"])
        n_hard_total = len(hard_checks)
        n_warning_total = len(warning_checks)
        n_warning_fail = sum(1 for c in warning_checks.values() if not c["pass"])

        verdict = "GO" if hard_all_pass else "NO-GO"
        overall = "GO" if hard_all_pass else "NO-GO"

        return {
            "checks": checks,
            "hard_checks": hard_checks,
            "warning_checks": warning_checks,
            "verdict": verdict,
            "overall": overall,
            "n_pass": n_hard_pass + sum(1 for c in warning_checks.values() if c["pass"]),
            "n_total": len(checks),
            "n_hard_pass": n_hard_pass,
            "n_hard_total": n_hard_total,
            "n_warning_total": n_warning_total,
            "n_warning_fail": n_warning_fail,
            "pass_rate": (n_hard_pass + sum(1 for c in warning_checks.values() if c["pass"])) / len(checks) if checks else 0,
        }

    # ------------------------------------------------------------------
    # Report generation
    # ------------------------------------------------------------------
    def generate_report(self) -> str:
        """Generate comprehensive robustness report."""
        if not self._results:
            return "No robustness test results."

        lines = []
        lines.append("# Robustness Test Report")
        lines.append("")

        for scenario_name, result in self._results.items():
            lines.append(f"## {scenario_name}")
            lines.append("")

            # DATA_MISSING handling
            if result.get("data_missing"):
                lines.append(f"**STATUS: DATA_MISSING** — "
                           f"n_periods={result.get('n_periods', 0)}, "
                           f"error={result.get('error', 'N/A')}")
                lines.append("")
                continue

            if result.get("error"):
                lines.append(f"**STATUS: ERROR** — {result.get('error')}")
                lines.append("")
                continue

            # Key metrics
            for key in ["annualized_return", "annualized_excess_return",
                        "sharpe_ratio", "information_ratio",
                        "max_drawdown", "avg_turnover"]:
                if key in result:
                    val = result[key]
                    if isinstance(val, float):
                        if np.isnan(val):
                            lines.append(f"- {key}: DATA_MISSING")
                        else:
                            lines.append(f"- {key}: {val:.4f}")
                    else:
                        lines.append(f"- {key}: {val}")

            # Optimizer diagnostics (if available)
            opt_keys = [
                "optimizer_fallback_rate", "optimizer_relaxation_rate",
                "opt_n_total", "opt_n_fallback", "opt_n_relaxation",
                "opt_fallback_reasons",
            ]
            for key in opt_keys:
                if key in result and result[key] is not None:
                    val = result[key]
                    if isinstance(val, float):
                        lines.append(f"- {key}: {val:.4f}")
                    elif isinstance(val, dict):
                        lines.append(f"- {key}: {json.dumps(val)}")
                    else:
                        lines.append(f"- {key}: {val}")

            lines.append("")

        # Additional report sections
        lines.append("---")
        lines.append("## Current Configuration")
        lines.append("")
        if self._results:
            first_result = list(self._results.values())[0]
            config = first_result.get("config", {})
            if config:
                for k, v in config.items():
                    lines.append(f"- **{k}**: {v}")
                lines.append("")
            else:
                lines.append("No config metadata available.")
                lines.append("")

        # Cost sensitivity section
        cost_scenarios = [k for k in self._results.keys() if "cost" in k.lower()]
        if cost_scenarios:
            lines.append("---")
            lines.append("## Cost Sensitivity")
            lines.append("")
            lines.append("| Scenario | Excess Return | IR | Turnover |")
            lines.append("|----------|--------------|-----|----------|")
            for scenario in cost_scenarios:
                r = self._results[scenario]
                if r.get("error") or r.get("data_missing"):
                    continue
                lines.append(
                    f"| {scenario} | "
                    f"{_safe_fmt(r.get('annualized_excess_return'), '.4%')} | "
                    f"{_safe_fmt(r.get('information_ratio'), '.3f')} | "
                    f"{_safe_fmt(r.get('avg_turnover'), '.4f')} |"
                )
            lines.append("")

        # Optimizer diagnostics section
        opt_results = [k for k in self._results.keys()
                       if self._results[k].get("optimizer_fallback_rate") is not None]
        if opt_results:
            lines.append("---")
            lines.append("## Optimizer Fallback Details")
            lines.append("")
            lines.append("| Scenario | Fallback Rate | N Total | N Fallback | Reasons |")
            lines.append("|----------|--------------|---------|------------|---------|")
            for scenario in opt_results:
                r = self._results[scenario]
                reasons = r.get("opt_fallback_reasons", {})
                reasons_str = ", ".join(f"{k}={v}" for k, v in reasons.items())[:80]
                lines.append(
                    f"| {scenario} | "
                    f"{_safe_fmt(r.get('optimizer_fallback_rate'), '.3f')} | "
                    f"{r.get('opt_n_total', 'N/A')} | "
                    f"{r.get('opt_n_fallback', 'N/A')} | "
                    f"{reasons_str} |"
                )
            lines.append("")

        # OOS separate report
        oos_results = [k for k in self._results.keys()
                       if "oos" in k.lower() or "2025" in k]
        if oos_results:
            lines.append("---")
            lines.append("## OOS (2025+) Separate Report")
            lines.append("")
            lines.append("| Scenario | Excess Return | IR | Max DD | Turnover | Fallback% |")
            lines.append("|----------|--------------|-----|--------|----------|-----------|")
            for scenario in oos_results:
                r = self._results[scenario]
                if r.get("data_missing"):
                    lines.append(f"| {scenario} | DATA_MISSING | | | | |")
                    continue
                lines.append(
                    f"| {scenario} | "
                    f"{_safe_fmt(r.get('annualized_excess_return'), '.4%')} | "
                    f"{_safe_fmt(r.get('information_ratio'), '.3f')} | "
                    f"{_safe_fmt(r.get('max_drawdown'), '.2%')} | "
                    f"{_safe_fmt(r.get('avg_turnover'), '.4f')} | "
                    f"{_safe_fmt(r.get('optimizer_fallback_rate'), '.3f')} |"
                )
            lines.append("")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Standalone robustness test functions
    # ------------------------------------------------------------------
    @staticmethod
    def compute_rolling_window_metrics(returns: pd.Series,
                                       window: int = 52,
                                       metric_fn: Callable = np.mean
                                       ) -> pd.Series:
        """Compute rolling window metrics for stability analysis."""
        return returns.rolling(window=window, min_periods=max(10, window // 4)).apply(metric_fn)

    @staticmethod
    def compute_rolling_ir(strategy_returns: pd.Series,
                           benchmark_returns: pd.Series,
                           window: int = 52) -> pd.Series:
        """Compute rolling information ratio."""
        excess = strategy_returns - benchmark_returns.reindex(strategy_returns.index)
        roll_mean = excess.rolling(window).mean()
        roll_std = excess.rolling(window).std()
        return (roll_mean / roll_std) * np.sqrt(52)  # annualized

    @staticmethod
    def compute_rolling_sharpe(returns: pd.Series,
                               window: int = 52) -> pd.Series:
        """Compute rolling Sharpe ratio."""
        roll_mean = returns.rolling(window).mean()
        roll_std = returns.rolling(window).std()
        return (roll_mean / roll_std) * np.sqrt(52)

"""
Factor performance report generator.

Produces markdown-formatted evaluation reports for individual factors
and multi-factor composites. Includes:
- IC statistics (mean, std, ICIR, positive rate)
- Quantile returns and cumulative plots
- Turnover analysis
- Decay across horizons
- Year-by-year breakdown
"""

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class FactorReport:
    """Generate factor evaluation reports."""

    def __init__(self, evaluator=None):
        self._evaluator = evaluator

    @property
    def evaluator(self):
        if self._evaluator is None:
            from eval.cs_evaluator import CrossSectionEvaluator
            self._evaluator = CrossSectionEvaluator()
        return self._evaluator

    # ------------------------------------------------------------------
    # Single factor report
    # ------------------------------------------------------------------
    def report_single_factor(self, factor_name: str,
                             factor_df: pd.DataFrame,
                             forward_returns_df: pd.DataFrame,
                             factor_col: Optional[str] = None) -> str:
        """
        Generate markdown report for a single factor.

        Parameters
        ----------
        factor_name : str
            Display name for the factor.
        factor_df : pd.DataFrame
            Factor values.
        forward_returns_df : pd.DataFrame
            Forward returns.
        factor_col : str, optional
            Column name of the factor value. Auto-detected if None.

        Returns
        -------
        str: Markdown report.
        """
        if factor_col is None:
            cols = [c for c in factor_df.columns
                    if c not in ("ts_code", "trade_date")]
            if not cols:
                return f"# {factor_name}\n\nNo factor data available."
            factor_col = cols[0]

        eval_result = self.evaluator.evaluate_factor(
            factor_name, factor_col, factor_df, forward_returns_df
        )

        return self._format_factor_report(eval_result)

    def _format_factor_report(self, result: Dict[str, Any]) -> str:
        """Format factor evaluation result as markdown."""
        lines = []
        lines.append(f"# Factor: {result['factor_name']}")
        lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        lines.append("")

        # Overview
        lines.append("## Overview")
        lines.append(f"- Observations: {result['n_observations']:,}")
        lines.append(f"- Unique Stocks: {result['n_stocks']}")
        lines.append(f"- Dates: {result['n_dates']}")
        lines.append("")

        # IC Statistics
        ic = result.get("ic", {})
        lines.append("## IC Statistics (Rank IC, 5-day forward)")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| Mean IC | {ic.get('mean_ic', 0):.4f} |")
        lines.append(f"| Std IC | {ic.get('std_ic', 0):.4f} |")
        lines.append(f"| ICIR | {ic.get('icir', 0):.3f} |")
        lines.append(f"| IC Positive Rate | {ic.get('ic_positive_rate', 0):.2%} |")
        lines.append(f"| t-stat | {ic.get('t_stat', 0):.3f} |")
        lines.append(f"| N days | {ic.get('n_days', 0)} |")
        lines.append("")

        # IC by Period
        period_data = result.get("ic_by_period", [])
        if period_data:
            lines.append("## IC by Period")
            lines.append("| Period | Mean IC | Std IC | ICIR | Pos Rate | N |")
            lines.append("|--------|---------|--------|------|----------|---|")
            for p in period_data:
                lines.append(
                    f"| {p.get('period', '')} "
                    f"| {p.get('mean_ic', 0):.4f} "
                    f"| {p.get('std_ic', 0):.4f} "
                    f"| {p.get('icir', 0):.3f} "
                    f"| {p.get('ic_positive_rate', 0):.2%} "
                    f"| {p.get('n_days', 0)} |"
                )
            lines.append("")

        # Quantile Returns
        quantile = result.get("quantile", {})
        if quantile:
            lines.append("## Quantile Returns (5-day forward)")
            lines.append(f"- Top quantile return: {quantile.get('top_ret', 0):.4%}")
            lines.append(f"- Bottom quantile return: {quantile.get('bottom_ret', 0):.4%}")
            lines.append(f"- Long-Short spread: {quantile.get('spread', 0):.4%}")
            lines.append(f"- t-stat (top): {quantile.get('t_stat', 0):.3f}")
            lines.append("")

        # Decay
        decay = result.get("decay", pd.DataFrame())
        if not isinstance(decay, pd.DataFrame):
            decay = pd.DataFrame(decay)
        if not decay.empty:
            lines.append("## IC Decay Across Horizons")
            lines.append("| Horizon (days) | Mean IC | ICIR | Pos Rate |")
            lines.append("|----------------|---------|------|----------|")
            for _, row in decay.iterrows():
                lines.append(
                    f"| {row.get('horizon', '')} "
                    f"| {row.get('mean_ic', 0):.4f} "
                    f"| {row.get('icir', 0):.3f} "
                    f"| {row.get('ic_positive_rate', 0):.2%} |"
                )
            lines.append("")

        # Turnover
        turnover = result.get("turnover", pd.DataFrame())
        if not isinstance(turnover, pd.DataFrame):
            turnover = pd.DataFrame(turnover)
        if not turnover.empty:
            avg_to = turnover["turnover"].mean()
            lines.append("## Turnover")
            lines.append(f"- Average top-quantile turnover: {avg_to:.2%}")
            lines.append("")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Multi-factor comparison
    # ------------------------------------------------------------------
    def report_multi_factor(self,
                            factor_results: List[Dict[str, Any]]) -> str:
        """
        Generate comparison report for multiple factors.

        Parameters
        ----------
        factor_results : list of dict
            Results from CrossSectionEvaluator.evaluate_all_factors().
        """
        lines = []
        lines.append("# Multi-Factor Comparison")
        lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        lines.append("")

        # Summary table
        lines.append("## Ranked by ICIR")
        lines.append("| Rank | Factor | Mean IC | ICIR | IC Pos Rate | Spread | Turnover |")
        lines.append("|------|--------|---------|------|-------------|--------|----------|")

        for i, r in enumerate(factor_results, 1):
            ic = r.get("ic", {})
            quantile = r.get("quantile", {})
            turnover = r.get("turnover", pd.DataFrame())
            avg_to = turnover["turnover"].mean() if not isinstance(turnover, dict) and len(turnover) > 0 else 0.0

            lines.append(
                f"| {i} | {r.get('factor_name', '')} "
                f"| {ic.get('mean_ic', 0):.4f} "
                f"| {ic.get('icir', 0):.3f} "
                f"| {ic.get('ic_positive_rate', 0):.2%} "
                f"| {quantile.get('spread', 0):.4%} "
                f"| {avg_to:.2%} |"
            )

        lines.append("")

        # Go/No-Go assessment
        lines.append("## Go/No-Go Assessment")
        lines.append("| Factor | Mean IC >= 0.02 | ICIR >= 0.3 | IC Pos >= 52% | Verdict |")
        lines.append("|--------|-----------------|-------------|---------------|---------|")

        for r in factor_results:
            ic = r.get("ic", {})
            mean_ok = "Y" if ic.get("mean_ic", 0) >= 0.02 else "N"
            icir_ok = "Y" if ic.get("icir", 0) >= 0.3 else "N"
            pos_ok = "Y" if ic.get("ic_positive_rate", 0) >= 0.52 else "N"
            verdict = "PASS" if all(s == "Y" for s in [mean_ok, icir_ok, pos_ok]) else "FAIL"

            lines.append(
                f"| {r.get('factor_name', '')} "
                f"| {mean_ok} ({ic.get('mean_ic', 0):.4f}) "
                f"| {icir_ok} ({ic.get('icir', 0):.3f}) "
                f"| {pos_ok} ({ic.get('ic_positive_rate', 0):.2%}) "
                f"| **{verdict}** |"
            )

        lines.append("")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Per-year IC breakdown (Phase 4)
    # ------------------------------------------------------------------
    def report_ic_by_year(self, factor_results: List[Dict[str, Any]],
                          ic_df: pd.DataFrame = None) -> str:
        """
        Generate year-by-year IC/ICIR breakdown for each factor.

        Uses IC data if provided, otherwise extracts from factor_results.
        """
        lines = []
        lines.append("## IC by Year")
        lines.append("")

        for r in factor_results:
            factor_name = r.get("factor_name", "unknown")
            period_data = r.get("ic_by_period", [])

            if not period_data:
                continue

            lines.append(f"### {factor_name}")
            lines.append("| Period | Mean IC | ICIR | Pos Rate | N |")
            lines.append("|--------|---------|------|----------|---|")

            for p in period_data:
                period = p.get("period", "")
                mean_ic = p.get("mean_ic", 0)
                icir = p.get("icir", 0)
                pos_rate = p.get("ic_positive_rate", 0)
                n = p.get("n_days", 0)
                lines.append(
                    f"| {period} | {mean_ic:.4f} | {icir:.3f} "
                    f"| {pos_rate:.2%} | {n} |"
                )

            lines.append("")

        return "\n".join(lines)

    def report_ic_by_regime(self, factor_results: List[Dict[str, Any]],
                            regimes: list = None) -> str:
        """
        Generate IC/ICIR breakdown by market regime (Phase 4).

        Regimes should be list of (start_year, end_year, label) tuples.
        If not provided, uses default: 2016-2018, 2019-2021, 2022-2024, 2025+.
        """
        if regimes is None:
            regimes = [
                (2016, 2018, "2016-2018 Recovery/Bear"),
                (2019, 2021, "2019-2021 Bull/Rotation"),
                (2022, 2024, "2022-2024 Bear/Redividend"),
                (2025, 2026, "2025+ OOS"),
            ]

        lines = []
        lines.append("## IC by Market Regime")
        lines.append("")

        for r in factor_results:
            factor_name = r.get("factor_name", "unknown")
            period_data = r.get("ic_by_period", [])

            if not period_data:
                continue

            lines.append(f"### {factor_name}")
            lines.append("| Regime | Mean IC | ICIR | Pos Rate |")
            lines.append("|--------|---------|------|----------|")

            for start_yr, end_yr, label in regimes:
                regime_periods = [
                    p for p in period_data
                    if start_yr <= int(str(p.get("period", "0"))[:4]) <= end_yr
                ]
                if regime_periods:
                    mean_ics = [p.get("mean_ic", 0) for p in regime_periods]
                    icirs = [p.get("icir", 0) for p in regime_periods]
                    pos_rates = [p.get("ic_positive_rate", 0) for p in regime_periods]
                    avg_ic = sum(mean_ics) / len(mean_ics) if mean_ics else 0
                    avg_icir = sum(icirs) / len(icirs) if icirs else 0
                    avg_pos = sum(pos_rates) / len(pos_rates) if pos_rates else 0
                    lines.append(
                        f"| {label} | {avg_ic:.4f} | {avg_icir:.3f} "
                        f"| {avg_pos:.2%} |"
                    )
                else:
                    lines.append(f"| {label} | DATA_MISSING | — | — |")

            lines.append("")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Save report to file
    # ------------------------------------------------------------------
    def save_report(self, report: str, filepath: str):
        """Save markdown report to file."""
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(report)
        logger.info(f"Report saved to {filepath}")

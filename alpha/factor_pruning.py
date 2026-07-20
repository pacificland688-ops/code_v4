"""
Factor Pruning Module.

Prunes or down-weights factors based on diagnostic criteria:
1. Annual IC predominantly negative → down-weight or remove
2. High turnover contribution but low IC → down-weight
3. Unstable coverage → down-weight
4. 2025+ IC decay → flagged for monitoring (NOT used for parameter selection)

All removal decisions are documented with explicit reasons.
Output: configs/factors_pruned.yaml
"""

import logging
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class FactorPruner:
    """
    Analyze and prune factors based on stability and contribution criteria.

    Parameters
    ----------
    factor_dfs : dict of factor_name → DataFrame
    fwd_rets : DataFrame
    signal_dates : list of int
    enabled_factors : list of str, optional
        Currently enabled factor names.
    """

    def __init__(
        self,
        factor_dfs: Dict[str, pd.DataFrame],
        fwd_rets: pd.DataFrame,
        signal_dates: List[int],
        enabled_factors: Optional[List[str]] = None,
    ):
        self.factor_dfs = factor_dfs
        self.fwd_rets = fwd_rets
        self.signal_dates = signal_dates
        self.enabled_factors = (
            enabled_factors if enabled_factors is not None
            else list(factor_dfs.keys())
        )

        self._analysis: Dict[str, Any] = {}
        self._removals: List[Dict[str, Any]] = []
        self._downweights: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Run pruning analysis
    # ------------------------------------------------------------------
    def analyze(self) -> Dict[str, Any]:
        """Run pruning analysis on all enabled factors."""
        horizon_col = "fwd_ret_5d"
        if self.fwd_rets is not None and not self.fwd_rets.empty:
            available = [c for c in self.fwd_rets.columns if c.startswith("fwd_ret_")]
            if available:
                horizon_col = available[0]

        for fname in self.enabled_factors:
            if fname not in self.factor_dfs:
                logger.warning(f"Factor {fname} not in factor_dfs — skipping")
                continue

            factor_df = self.factor_dfs[fname]
            if factor_df.empty:
                self._removals.append({
                    "factor": fname,
                    "reason": "empty_data",
                    "action": "remove",
                    "details": "Factor DataFrame is empty",
                })
                continue

            analysis = self._analyze_single(fname, factor_df, horizon_col)
            self._analysis[fname] = analysis

            # Decision logic
            action, reason = self._decide_action(fname, analysis)
            if action == "remove":
                self._removals.append({
                    "factor": fname,
                    "reason": reason,
                    "action": "remove",
                    "details": analysis,
                })
            elif action == "downweight":
                self._downweights.append({
                    "factor": fname,
                    "reason": reason,
                    "action": "downweight",
                    "details": analysis,
                })

        return {
            "n_analyzed": len(self._analysis),
            "n_remove": len(self._removals),
            "n_downweight": len(self._downweights),
            "removals": self._removals,
            "downweights": self._downweights,
            "analysis": self._analysis,
        }

    # ------------------------------------------------------------------
    # Single factor analysis
    # ------------------------------------------------------------------
    def _analyze_single(self, fname: str, factor_df: pd.DataFrame,
                        horizon_col: str) -> Dict[str, Any]:
        """Analyze a single factor comprehensively."""
        result = {}

        # 1. Annual IC
        annual_ic = {}
        if self.fwd_rets is not None and not self.fwd_rets.empty:
            factor_df_copy = factor_df.copy()
            factor_df_copy["year"] = pd.to_datetime(
                factor_df_copy["trade_date"].astype(str), format="%Y%m%d"
            ).dt.year

            for year, year_data in factor_df_copy.groupby("year"):
                year_dates = set(year_data["trade_date"].unique())
                valid_dates = sorted(year_dates & set(self.signal_dates))
                if len(valid_dates) < 5:
                    continue

                ics = []
                for dt in valid_dates:
                    f_day = year_data[year_data["trade_date"] == dt]
                    r_day = self.fwd_rets[self.fwd_rets["trade_date"] == dt]
                    if f_day.empty or r_day.empty:
                        continue
                    merged = f_day.merge(r_day, on=["ts_code", "trade_date"], how="inner")
                    if len(merged) < 10:
                        continue
                    if "value" not in merged.columns or horizon_col not in merged.columns:
                        continue
                    ic = merged["value"].rank().corr(merged[horizon_col].rank())
                    if np.isfinite(ic):
                        ics.append(ic)

                if ics:
                    annual_ic[str(year)] = {
                        "mean_ic": float(np.mean(ics)),
                        "ic_positive_rate": float(np.mean([ic > 0 for ic in ics])),
                        "n_dates": len(ics),
                    }

        result["annual_ic"] = annual_ic

        # 2. IC sign stability — count years with negative mean IC
        negative_ic_years = [
            yr for yr, data in annual_ic.items()
            if data.get("mean_ic", 0) < 0
        ]
        result["negative_ic_years"] = negative_ic_years
        result["negative_ic_year_ratio"] = (
            len(negative_ic_years) / len(annual_ic) if annual_ic else 0.0
        )

        # 3. Coverage analysis
        factor_dates = set(factor_df["trade_date"].unique())
        expected_dates = set(self.signal_dates)
        covered = factor_dates & expected_dates
        result["coverage_ratio"] = (
            len(covered) / len(expected_dates) if expected_dates else 0.0
        )

        # Coverage instability: check per-year coverage
        factor_df_copy = factor_df.copy()
        factor_df_copy["year"] = pd.to_datetime(
            factor_df_copy["trade_date"].astype(str), format="%Y%m%d"
        ).dt.year
        year_coverage = {}
        for year, year_data in factor_df_copy.groupby("year"):
            year_dates = set(year_data["trade_date"].unique())
            year_signal_dates = {d for d in self.signal_dates if str(d)[:4] == str(year)}
            if year_signal_dates:
                year_coverage[str(year)] = (
                    len(year_dates & year_signal_dates) / len(year_signal_dates)
                )
        result["yearly_coverage"] = year_coverage

        # Coverage instability: std of yearly coverage
        cov_values = list(year_coverage.values())
        result["coverage_instability"] = float(np.std(cov_values)) if len(cov_values) >= 2 else 0.0

        # 4. Turnover contribution (rank autocorrelation)
        autocorr = self._compute_rank_autocorr(factor_df)
        result["rank_autocorrelation"] = autocorr

        # 5. 2025+ decay check
        pre_2025_ic = self._period_mean_ic(factor_df, horizon_col, lambda d: str(d) < "20250101")
        post_2025_ic = self._period_mean_ic(factor_df, horizon_col, lambda d: str(d) >= "20250101")
        result["pre_2025_mean_ic"] = pre_2025_ic
        result["post_2025_mean_ic"] = post_2025_ic
        result["decay_2025"] = (
            post_2025_ic is not None and pre_2025_ic is not None
            and pre_2025_ic > 0 and post_2025_ic < pre_2025_ic * 0.5
        )

        return result

    def _compute_rank_autocorr(self, factor_df: pd.DataFrame) -> float:
        """Compute average cross-sectional rank autocorrelation."""
        if factor_df.empty or len(self.signal_dates) < 2:
            return float("nan")

        factor_df = factor_df.copy()
        factor_df["trade_date"] = factor_df["trade_date"].astype(int)

        autocorrs = []
        for i, dt in enumerate(self.signal_dates[1:], 1):
            prev_dt = self.signal_dates[i - 1]
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

            ac = aligned.iloc[:, 0].corr(aligned.iloc[:, 1])
            if np.isfinite(ac):
                autocorrs.append(ac)

        return float(np.mean(autocorrs)) if autocorrs else float("nan")

    def _period_mean_ic(self, factor_df: pd.DataFrame, horizon_col: str,
                        date_filter) -> Optional[float]:
        """Compute mean IC for a date-filtered period."""
        filtered_dates = [d for d in self.signal_dates if date_filter(d)]
        if not filtered_dates or self.fwd_rets is None or self.fwd_rets.empty:
            return None

        factor_df = factor_df.copy()
        factor_df["trade_date"] = factor_df["trade_date"].astype(int)

        ics = []
        for dt in filtered_dates:
            f_day = factor_df[factor_df["trade_date"] == dt]
            r_day = self.fwd_rets[self.fwd_rets["trade_date"] == dt]
            if f_day.empty or r_day.empty:
                continue
            merged = f_day.merge(r_day, on=["ts_code", "trade_date"], how="inner")
            if len(merged) < 10:
                continue
            if "value" in merged.columns and horizon_col in merged.columns:
                ic = merged["value"].rank().corr(merged[horizon_col].rank())
                if np.isfinite(ic):
                    ics.append(ic)

        return float(np.mean(ics)) if ics else None

    # ------------------------------------------------------------------
    # Decision logic
    # ------------------------------------------------------------------
    def _decide_action(self, fname: str,
                       analysis: Dict[str, Any]) -> Tuple[str, str]:
        """
        Decide whether to keep, down-weight, or remove a factor.

        Returns (action, reason).
        """
        annual_ic = analysis.get("annual_ic", {})

        # Rule 1: Majority of years have negative IC
        neg_ratio = analysis.get("negative_ic_year_ratio", 0.0)
        if neg_ratio > 0.6 and len(annual_ic) >= 3:
            return ("remove",
                    f"negative_IC_in_{int(neg_ratio*100)}%_of_years")

        # Rule 2: High turnover contribution + low IC
        autocorr = analysis.get("rank_autocorrelation", float("nan"))
        if not np.isnan(autocorr) and autocorr < 0.2:
            # Check latest year IC
            ic_years = sorted(annual_ic.keys(), reverse=True)
            if ic_years:
                latest_ic = annual_ic[ic_years[0]].get("mean_ic", float("inf"))
                if latest_ic < 0.01:
                    return ("remove",
                            f"high_turnover_contribution_low_IC_({autocorr:.2f}_autocorr)")

        # Rule 3: Coverage instability
        cov_instability = analysis.get("coverage_instability", 0.0)
        if cov_instability > 0.3:
            return ("downweight",
                    f"unstable_coverage_(std={cov_instability:.2f})")

        # Rule 4: Coverage ratio too low
        cov_ratio = analysis.get("coverage_ratio", 0.0)
        if cov_ratio < 0.5:
            return ("remove",
                    f"low_coverage_({cov_ratio:.1%})")

        # Rule 5: Low rank autocorrelation (high turnover contributor)
        if not np.isnan(autocorr) and autocorr < 0.15:
            # Check if IC is also poor
            ic_years = sorted(annual_ic.keys(), reverse=True)
            if ic_years:
                latest_ic = annual_ic[ic_years[0]].get("mean_ic", 0)
                if latest_ic < 0.02:
                    return ("downweight",
                            f"high_turnover_low_IC_(autocorr={autocorr:.2f})")

        # 2025+ decay is flagged for monitoring but NOT used for removal
        # (OOS should not drive parameter selection)
        if analysis.get("decay_2025"):
            logger.info(
                f"Factor {fname}: 2025+ decay detected — flagged for monitoring, "
                f"NOT used for removal decision"
            )

        return ("keep", "passes_all_checks")

    # ------------------------------------------------------------------
    # Generate pruned config
    # ------------------------------------------------------------------
    def generate_pruned_config(self, output_path: Optional[Path] = None) -> Dict[str, Any]:
        """Generate a pruned factor config for configs/factors_pruned.yaml."""
        removed_names = {r["factor"] for r in self._removals}
        downweighted_names = {d["factor"] for d in self._downweights}

        # Build new enabled list
        kept = [f for f in self.enabled_factors
                if f not in removed_names and f in self.factor_dfs]

        config = {
            "generated_at": datetime.now().isoformat(),
            "n_original": len(self.enabled_factors),
            "n_kept": len(kept),
            "n_removed": len(removed_names),
            "n_downweighted": len(downweighted_names),
            "enabled_factors": kept,
            "removed_factors": [
                {"factor": f, "reason": next(
                    (r["reason"] for r in self._removals if r["factor"] == f), ""
                )}
                for f in sorted(removed_names)
            ],
            "downweighted_factors": [
                {"factor": f, "reason": next(
                    (d["reason"] for d in self._downweights if d["factor"] == f), ""
                )}
                for f in sorted(downweighted_names)
            ],
            "note": (
                "2025+ OOS data is used for DIAGNOSTICS ONLY, not for factor "
                "selection. Removal decisions are based on IS (pre-2025) data."
            ),
        }

        if output_path:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                import yaml
                with open(output_path, "w", encoding="utf-8") as f:
                    yaml.dump(config, f, default_flow_style=False, allow_unicode=True)
                logger.info(f"Pruned config saved to {output_path}")
            except ImportError:
                # Fallback to JSON
                json_path = output_path.with_suffix(".json")
                import json
                with open(json_path, "w", encoding="utf-8") as f:
                    json.dump(config, f, indent=2, ensure_ascii=False, default=str)
                logger.info(f"Pruned config saved to {json_path} (JSON fallback)")

        return config

    # ------------------------------------------------------------------
    # Generate report
    # ------------------------------------------------------------------
    def generate_report(self) -> str:
        """Generate markdown pruning report."""
        lines = []
        lines.append("# Factor Pruning Report")
        lines.append(f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")

        lines.append(f"- **Factors Analyzed**: {len(self._analysis)}")
        lines.append(f"- **Removed**: {len(self._removals)}")
        lines.append(f"- **Down-weighted**: {len(self._downweights)}")
        lines.append("")

        # Removals
        if self._removals:
            lines.append("## Removed Factors")
            lines.append("")
            lines.append("| Factor | Reason |")
            lines.append("|--------|--------|")
            for r in self._removals:
                lines.append(f"| {r['factor']} | {r['reason']} |")
            lines.append("")

        # Down-weights
        if self._downweights:
            lines.append("## Down-weighted Factors")
            lines.append("")
            lines.append("| Factor | Reason |")
            lines.append("|--------|--------|")
            for d in self._downweights:
                lines.append(f"| {d['factor']} | {d['reason']} |")
            lines.append("")

        # Annual IC summary
        lines.append("## Annual IC Summary")
        lines.append("")

        # Collect all years
        all_years = set()
        for fname, analysis in self._analysis.items():
            all_years.update(analysis.get("annual_ic", {}).keys())
        years_sorted = sorted(all_years)

        if years_sorted:
            header = "| Factor | " + " | ".join(years_sorted) + " | Action |"
            lines.append(header)
            sep = "|--------|" + "|".join(["--------"] * len(years_sorted)) + "|--------|"
            lines.append(sep)

            removed_names = {r["factor"] for r in self._removals}
            downweighted_names = {d["factor"] for d in self._downweights}

            for fname in sorted(self._analysis.keys()):
                analysis = self._analysis[fname]
                annual_ic = analysis.get("annual_ic", {})
                vals = []
                for yr in years_sorted:
                    yd = annual_ic.get(str(yr), {})
                    if isinstance(yd, dict):
                        ic = yd.get("mean_ic", float("nan"))
                        vals.append(f"{ic:.4f}" if np.isfinite(ic) else "N/A")
                    else:
                        vals.append("N/A")

                if fname in removed_names:
                    action = "REMOVED"
                elif fname in downweighted_names:
                    action = "DOWNWEIGHT"
                else:
                    action = "KEPT"

                lines.append(f"| {fname} | " + " | ".join(vals) + f" | {action} |")
            lines.append("")

        # 2025+ decay flags (diagnostic only)
        lines.append("## 2025+ Decay Flags (Diagnostic Only)")
        lines.append("")
        lines.append("| Factor | Pre-2025 IC | Post-2025 IC | Decay |")
        lines.append("|--------|-------------|--------------|-------|")
        for fname, analysis in sorted(self._analysis.items()):
            pre = analysis.get("pre_2025_mean_ic")
            post = analysis.get("post_2025_mean_ic")
            decay = analysis.get("decay_2025", False)
            lines.append(
                f"| {fname} | "
                f"{pre:.4f}" if pre is not None else "N/A" + " | "
                f"{post:.4f}" if post is not None else "N/A" + " | "
                f"{'YES' if decay else 'no'} |"
            )
        lines.append("")
        lines.append("**Note**: 2025+ decay flags are for monitoring only. "
                     "Removal decisions use IS (pre-2025) data exclusively.")
        lines.append("")

        return "\n".join(lines)

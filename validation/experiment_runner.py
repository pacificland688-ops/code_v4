"""
Phase 5 Experiment Runner.

Orchestrates grid-search experiments defined in a YAML configuration.
Evaluates parameter combinations against candidate criteria:
- avg_turnover <= 0.32
- optimizer_fallback_rate <= 0.15
- cost_2x_excess >= -0.015
- information_ratio >= 0.25

Batch 1+2 fixes:
- Unified BACKTEST_PARAM_KEYS ensures ALL params reach run_backtest().
- _build_bt_kwargs() avoids manual field omissions.
- Every config runs BOTH 1x and 2x cost backtests.
- _filter_candidates() checks cost_2x_excess from real 2x results.
- Filter thresholds read from YAML config.filters, not hard-coded.
- Summary CSV records all params, not just diff from base.

Outputs:
- outputs/phase5_experiment_summary.csv
- outputs/phase5_experiment_report.md
- outputs/phase5_experiment_candidates.json
"""

import itertools
import json
import logging
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Allowed backtest parameters — every key in a config dict that should be
# forwarded to PortfolioBacktester.run_backtest().  Adding a key here is the
# ONLY thing needed to wire a new experiment parameter end-to-end.
# ---------------------------------------------------------------------------
BACKTEST_PARAM_KEYS = {
    "top_n", "weighting", "weight_max",
    "rebalance_freq",
    "turnover_max", "turnover_penalty",
    "entry_rank", "exit_rank",
    "no_trade_band", "max_weight_change",
    "score_smoothing_halflife", "hold_buffer_mode",
    "cost_aware_lambda", "estimated_cost_bps",
    "cov_shrinkage", "constraint_relaxation",
}

# Default candidate filter thresholds — overridden by YAML config.filters.
DEFAULT_FILTERS = {
    "avg_turnover": {"max": 0.32, "description": "avg_turnover <= 0.32"},
    "optimizer_fallback_rate": {"max": 0.15, "description": "fallback_rate <= 0.15"},
    "cost_2x_excess": {"min": -0.015, "description": "2x cost excess >= -0.015"},
    "information_ratio": {"min": 0.25, "description": "IR >= 0.25"},
}


class ExperimentRunner:
    """
    Run parameter grid experiments from YAML configuration.

    Parameters
    ----------
    config_path : str or Path
        Path to YAML experiment configuration.
    args : argparse.Namespace
        CLI arguments for date ranges and base parameters.
    """

    def __init__(self, config_path: str = "configs/phase5_experiments.yaml",
                 args: Any = None):
        self.config_path = Path(config_path)
        if not self.config_path.exists():
            raise FileNotFoundError(f"Config file not found: {self.config_path}")

        self.args = args
        self.config = self._load_config()
        self.base = self.config.get("base", {})
        self.experiments = self.config.get("experiments", {})

        # Batch 5: Execution rules
        self.execution = self.config.get("execution", {})
        self.oos_for_selection = self.execution.get("oos_for_selection", True)
        self.max_candidates_per_line = self.execution.get("max_candidates_per_line", 0)
        self.phase3_interval_first = self.execution.get("phase3_interval_first", True)

        # Selection interval: prefer explicit config, else exclude OOS
        self.selection_start = self.base.get("selection_start_date", self.base.get("start_date", "20160101"))
        if not self.oos_for_selection and "selection_end_date" not in self.base:
            oos_start = self.base.get("oos_start_date", "20250101")
            self.selection_end = self._one_day_before(oos_start)
        else:
            self.selection_end = self.base.get("selection_end_date", self.base.get("end_date", "20260604"))

        # Filters: prefer YAML config.filters, fall back to DEFAULT_FILTERS
        self.filters = self.config.get("filters", None)
        if self.filters is None:
            self.filters = DEFAULT_FILTERS

        self.results: List[Dict[str, Any]] = []
        self.candidates: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Load and validate config
    # ------------------------------------------------------------------
    def _load_config(self) -> Dict[str, Any]:
        """Load YAML configuration."""
        try:
            import yaml
        except ImportError:
            raise ImportError("PyYAML required for experiment config. "
                            "Install with: pip install pyyaml")

        with open(self.config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)

        if not config:
            raise ValueError(f"Empty or invalid config: {self.config_path}")

        if "base" not in config:
            logger.warning("No 'base' section in config — using CLI defaults")
            config["base"] = {}

        if "experiments" not in config:
            raise ValueError("Config must contain 'experiments' section")

        return config

    # ------------------------------------------------------------------
    # Build experiment grid
    # ------------------------------------------------------------------
    def build_grid(self, experiment_name: str) -> List[Dict[str, Any]]:
        """
        Expand a parameter grid into a list of individual configs.
        """
        exp_def = self.experiments.get(experiment_name)
        if not exp_def:
            logger.warning(f"Experiment '{experiment_name}' not found in config")
            return []

        if not isinstance(exp_def, dict):
            logger.warning(f"Experiment '{experiment_name}' is not a dict: {type(exp_def)}")
            return []

        param_keys = [k for k in exp_def.keys() if isinstance(exp_def[k], list)]
        if not param_keys:
            logger.warning(f"Experiment '{experiment_name}' has no parameter lists")
            return []

        configs = []
        param_values = [exp_def[k] for k in param_keys]

        for combo in itertools.product(*param_values):
            config = deepcopy(self.base)
            config["experiment"] = experiment_name
            for key, val in zip(param_keys, combo):
                if key == "entry_exit":
                    if isinstance(val, (list, tuple)) and len(val) == 2:
                        config["entry_rank"] = int(val[0])
                        config["exit_rank"] = int(val[1])
                    else:
                        config["entry_exit"] = val
                elif key == "constraint_relaxation":
                    config["constraint_relaxation"] = val
                elif key == "cov_shrinkage":
                    config["cov_shrinkage"] = val
                else:
                    config[key] = val
            configs.append(config)

        logger.info(f"Experiment '{experiment_name}': {len(configs)} combinations "
                     f"across {len(param_keys)} parameter(s)")
        return configs

    # ------------------------------------------------------------------
    # Build backtest kwargs from config (Batch 1 fix)
    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # Selection interval — respects oos_for_selection (方案二)
    # ------------------------------------------------------------------
    def _selection_interval(self, config: Dict[str, Any]) -> Tuple[str, str]:
        """
        Return the (start_date, end_date) to use for data loading and
        backtest selection, respecting oos_for_selection.

        When oos_for_selection=False, the selection end_date is capped at
        the day before OOS start, preventing OOS data from leaking into
        candidate selection.
        """
        if getattr(self, "oos_for_selection", True):
            return (
                config.get("start_date", "20160101"),
                config.get("end_date", "20260604"),
            )
        # Strict IS-only: use explicit selection_end_date if set,
        # otherwise one day before oos_start_date.
        sel_start = config.get(
            "selection_start_date",
            getattr(self, "selection_start", "20160101"),
        )
        sel_end = config.get(
            "selection_end_date",
            getattr(self, "selection_end", "20241231"),
        )
        return (sel_start, sel_end)

    # ------------------------------------------------------------------
    # Build backtest kwargs
    # ------------------------------------------------------------------
    def _build_bt_kwargs(self, config: Dict[str, Any],
                         composite: pd.DataFrame,
                         mu_df: Optional[pd.DataFrame]) -> Dict[str, Any]:
        """
        Build kwargs dict for bt.run_backtest() using the whitelist.
        Every parameter in BACKTEST_PARAM_KEYS that exists in config is forwarded.
        This prevents the "parameter written but not passed" bug.
        """
        eval_start, eval_end = self._selection_interval(config)
        bt_kwargs = {
            "scores": composite,
            "score_col": "composite_score",
            "start_date": eval_start,
            "end_date": eval_end,
            "mu_df": mu_df,
        }

        for key in BACKTEST_PARAM_KEYS:
            if key in config:
                bt_kwargs[key] = config[key]

        return bt_kwargs

    # ------------------------------------------------------------------
    # Run all experiments
    # ------------------------------------------------------------------
    def run(self) -> Dict[str, Any]:
        """Run all experiments defined in the configuration."""
        logger.info(f"Running {len(self.experiments)} experiment(s)...")

        for exp_name in self.experiments:
            logger.info(f"--- Experiment: {exp_name} ---")
            configs = self.build_grid(exp_name)

            if not configs:
                logger.warning(f"Skipping {exp_name}: no valid configs")
                continue

            for i, config in enumerate(configs):
                label = self._make_label(exp_name, config, i)
                logger.info(f"  [{i+1}/{len(configs)}] {label}")

                try:
                    result = self._evaluate_config(config, label)
                    self.results.append(result)
                except Exception as e:
                    logger.error(f"  Failed: {e}")
                    self.results.append({
                        "experiment": exp_name,
                        "label": label,
                        "error": str(e),
                        "status": "FAILED",
                    })

        self.candidates = self._filter_candidates(self.results)
        self._write_outputs()

        return {
            "n_experiments": len(self.experiments),
            "n_configs": len(self.results),
            "n_candidates": len(self.candidates),
            "candidates": self.candidates,
        }

    # ------------------------------------------------------------------
    # Evaluate a single config (runs BOTH 1x and 2x cost — Batch 2)
    # ------------------------------------------------------------------
    def _evaluate_config(self, config: Dict[str, Any],
                         label: str) -> Dict[str, Any]:
        """Run 1x and 2x cost backtests for a single configuration.

        方案二: All data loading uses _selection_interval() to ensure
        OOS data does not leak into candidate selection when
        oos_for_selection=False.
        """
        from backtest.portfolio_backtester import PortfolioBacktester
        from data.panel_loader import get_loader
        from data.calendar import get_calendar
        from data.universe import get_universe_builder
        from data.tradable import get_tradable
        from alpha.ic_weighting import ICWeighting
        from run_research import (
            _select_valid_cs_factors,
            _filter_enabled_factors,
        )
        from configs.factor_config import load_factor_config

        # 方案二: Use selection interval for data loading
        eval_start, eval_end = self._selection_interval(config)

        loader = get_loader()
        calendar = get_calendar()
        calendar.load(start_date=eval_start, end_date=eval_end)

        factor_names = _select_valid_cs_factors(loader, calendar, eval_start, eval_end)
        factor_config = load_factor_config()
        enabled_factors = factor_config["enabled_factors"]
        composite_params = factor_config["composite_params"]
        factor_names = _filter_enabled_factors(factor_names, enabled_factors)

        if not factor_names:
            return {"experiment": config.get("experiment"), "label": label,
                    "error": "No valid factors", "status": "FAILED"}

        factor_dfs = {}
        for name in factor_names:
            df = loader.read_factor(name, eval_start, eval_end)
            if not df.empty:
                factor_dfs[name] = df

        fwd_rets = loader.read_factor("fwd_returns", eval_start, eval_end)

        weekly_dates = set(calendar.weekly_rebalance_dates(eval_start, eval_end))
        signal_dates_int = [int(d) for d in sorted(weekly_dates)]

        icw = ICWeighting(**composite_params, factor_whitelist=enabled_factors)
        composite = icw.compute_composite_series(factor_dfs, fwd_rets, signal_dates_int)

        mu_df = None
        try:
            from alpha.score_to_mu import ScoreToMu
            stm = ScoreToMu(method="rolling_ic")
            mu_df = stm.calibrate(composite, "composite_score", fwd_rets,
                                  horizon=composite_params.get("horizon", 5))
        except Exception:
            pass

        universe = get_universe_builder()
        universe.load(start_date=eval_start, end_date=eval_end)
        tradable = get_tradable()
        tradable.load(start_date=eval_start, end_date=eval_end)

        bt = PortfolioBacktester(
            universe_builder=universe,
            tradable_mask=tradable,
            panel_loader=loader,
        )

        # --- 1x cost backtest ---
        bt_kwargs = self._build_bt_kwargs(config, composite, mu_df)
        bt_kwargs["cost_multiplier"] = 1.0
        base_result = bt.run_backtest(**bt_kwargs)

        # --- 2x cost backtest ---
        bt_kwargs_2x = deepcopy(bt_kwargs)
        bt_kwargs_2x["cost_multiplier"] = 2.0
        cost_2x_result = bt.run_backtest(**bt_kwargs_2x)

        # --- Build summary with ALL params (not just diff) ---
        summary = {
            "experiment": config.get("experiment", ""),
            "label": label,
            "status": "OK" if not base_result.get("error") else "FAILED",
            # 方案二: Record actual selection interval used
            "selection_start_date": eval_start,
            "selection_end_date": eval_end,
            "oos_for_selection": self.oos_for_selection,
            "eval_start_date": eval_start,
            "eval_end_date": eval_end,
            "annualized_excess_return": base_result.get("annualized_excess_return", float("nan")),
            "information_ratio": base_result.get("information_ratio", float("nan")),
            "sharpe_ratio": base_result.get("sharpe_ratio", float("nan")),
            "max_drawdown": base_result.get("max_drawdown", float("nan")),
            "avg_turnover": base_result.get("avg_turnover", float("nan")),
            "optimizer_fallback_rate": base_result.get("optimizer_fallback_rate", float("nan")),
            "optimizer_relaxation_rate": base_result.get("optimizer_relaxation_rate", float("nan")),
            "total_cost_bps": base_result.get("total_cost_bps", float("nan")),
            "n_periods": base_result.get("n_periods", 0),
        }

        # --- 2x cost fields ---
        if cost_2x_result.get("error"):
            summary["cost_2x_excess"] = float("nan")
            summary["cost_2x_ir"] = float("nan")
            summary["cost_2x_avg_turnover"] = float("nan")
            summary["cost_2x_error"] = cost_2x_result.get("error", "")
            summary["cost_2x_n_periods"] = cost_2x_result.get("n_periods", 0)
        else:
            summary["cost_2x_excess"] = cost_2x_result.get("annualized_excess_return", float("nan"))
            summary["cost_2x_ir"] = cost_2x_result.get("information_ratio", float("nan"))
            summary["cost_2x_avg_turnover"] = cost_2x_result.get("avg_turnover", float("nan"))
            summary["cost_2x_error"] = ""
            summary["cost_2x_n_periods"] = cost_2x_result.get("n_periods", 0)

        # --- Record ALL experiment parameters (Batch 1 fix) ---
        for key in sorted(BACKTEST_PARAM_KEYS):
            if key in config:
                summary[f"param_{key}"] = config[key]

        if base_result.get("error"):
            summary["error"] = base_result["error"]

        if cost_2x_result.get("error"):
            summary["cost_2x_error"] = cost_2x_result["error"]

        return summary

    # ------------------------------------------------------------------
    # Candidate filtering (Batch 2: real 2x cost check)
    # ------------------------------------------------------------------
    def _filter_candidates(self, results: List[Dict]) -> List[Dict]:
        """Filter results using config.filters thresholds, including 2x cost."""
        candidates = []

        # Read thresholds from self.filters (YAML) or defaults
        def _threshold(filter_key: str, bound: str) -> float:
            f = self.filters.get(filter_key, {})
            return f.get(bound, DEFAULT_FILTERS.get(filter_key, {}).get(bound, 0))

        for r in results:
            if r.get("status") != "OK":
                continue
            if r.get("error"):
                continue
            # Batch 2: 2x cost must exist and not have error
            if r.get("cost_2x_error"):
                continue

            passes = True
            checks = {}

            # avg_turnover
            to = r.get("avg_turnover", float("inf"))
            to_max = _threshold("avg_turnover", "max")
            to_ok = isinstance(to, (int, float)) and not np.isnan(to) and to <= to_max
            checks["avg_turnover"] = {"value": to, "threshold": to_max, "pass": to_ok}
            if not to_ok:
                passes = False

            # fallback rate
            fb = r.get("optimizer_fallback_rate", float("inf"))
            fb_max = _threshold("optimizer_fallback_rate", "max")
            fb_ok = isinstance(fb, (int, float)) and not np.isnan(fb) and fb <= fb_max
            checks["optimizer_fallback_rate"] = {"value": fb, "threshold": fb_max, "pass": fb_ok}
            if not fb_ok:
                passes = False

            # information_ratio
            ir = r.get("information_ratio", float("-inf"))
            ir_min = _threshold("information_ratio", "min")
            ir_ok = isinstance(ir, (int, float)) and not np.isnan(ir) and ir >= ir_min
            checks["information_ratio"] = {"value": ir, "threshold": ir_min, "pass": ir_ok}
            if not ir_ok:
                passes = False

            # cost_2x_excess (Batch 2: real check from 2x backtest)
            c2x = r.get("cost_2x_excess", float("-inf"))
            c2x_min = _threshold("cost_2x_excess", "min")
            c2x_ok = isinstance(c2x, (int, float)) and not np.isnan(c2x) and c2x >= c2x_min
            checks["cost_2x_excess"] = {"value": c2x, "threshold": c2x_min, "pass": c2x_ok}
            if not c2x_ok:
                passes = False

            r["candidate_checks"] = checks
            r["is_candidate"] = passes

            if passes:
                candidates.append(r)

        logger.info(f"Candidates: {len(candidates)}/{len(results)} passed all filters "
                     f"(including 2x cost)")

        # Batch 5: Enforce max_candidates_per_line (safe against unset attr)
        if getattr(self, "max_candidates_per_line", 0) > 0:
            candidates = self._cap_per_line(candidates)

        return candidates

    def _cap_per_line(self, candidates: List[Dict]) -> List[Dict]:
        """Limit candidates per experiment line to max_candidates_per_line.

        Ranking priority: cost_2x_excess desc → IR desc → avg_turnover asc → fallback_rate asc.
        """
        capped = []
        by_exp = {}
        for c in candidates:
            exp = c.get("experiment", "unknown")
            by_exp.setdefault(exp, []).append(c)

        for exp, items in by_exp.items():
            if len(items) <= self.max_candidates_per_line:
                capped.extend(items)
                continue

            # Sort by ranking criteria
            sorted_items = sorted(items, key=lambda x: (
                -(_safe_num(x.get("cost_2x_excess"), -999)),
                -(_safe_num(x.get("information_ratio"), -999)),
                _safe_num(x.get("avg_turnover"), 999),
                _safe_num(x.get("optimizer_fallback_rate"), 999),
            ))
            capped.extend(sorted_items[:self.max_candidates_per_line])
            logger.info(f"Experiment '{exp}': capped from {len(items)} to "
                        f"{self.max_candidates_per_line} candidates")

        return capped

    @staticmethod
    def _one_day_before(date_str: str) -> str:
        """Return the day before a YYYYMMDD date string."""
        from datetime import datetime, timedelta
        try:
            dt = datetime.strptime(date_str, "%Y%m%d")
            return (dt - timedelta(days=1)).strftime("%Y%m%d")
        except ValueError:
            return date_str

    # ------------------------------------------------------------------
    # Output generation
    # ------------------------------------------------------------------
    def _write_outputs(self):
        """Write summary CSV, report MD, and candidates JSON."""
        outputs_dir = Path("outputs")
        outputs_dir.mkdir(parents=True, exist_ok=True)

        if self.results:
            df = pd.DataFrame(self.results)
            csv_path = outputs_dir / "phase5_experiment_summary.csv"
            df.to_csv(csv_path, index=False, encoding="utf-8")
            logger.info(f"Experiment summary: {csv_path}")

        cand_path = outputs_dir / "phase5_experiment_candidates.json"
        with open(cand_path, "w", encoding="utf-8") as f:
            json.dump(self.candidates, f, indent=2, ensure_ascii=False, default=str)
        logger.info(f"Candidates: {cand_path}")

        report = self._generate_report()
        report_path = outputs_dir / "phase5_experiment_report.md"
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report)
        logger.info(f"Experiment report: {report_path}")

    # ------------------------------------------------------------------
    # Report generation
    # ------------------------------------------------------------------
    def _generate_report(self) -> str:
        """Generate markdown experiment report."""
        lines = []
        lines.append("# Phase 5 Experiment Report")
        lines.append(f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")

        lines.append("## Summary")
        lines.append("")
        lines.append(f"- **Total experiments**: {len(self.experiments)}")
        lines.append(f"- **Total configs evaluated**: {len(self.results)}")
        lines.append(f"- **Candidates passing all filters**: {len(self.candidates)}")
        lines.append("")

        # Batch 5: Execution rules in report
        lines.append("## Execution Rules")
        lines.append("")
        lines.append(f"- **Selection interval**: {self.selection_start} → {self.selection_end}")
        lines.append(f"- **OOS used for selection**: {self.oos_for_selection}")
        lines.append(f"- **Max candidates per experiment line**: "
                     f"{self.max_candidates_per_line if self.max_candidates_per_line > 0 else 'unlimited'}")
        lines.append("")

        lines.append("## Candidate Filter Criteria")
        lines.append("")
        lines.append("| Criterion | Threshold |")
        lines.append("|-----------|-----------|")
        for key, spec in self.filters.items():
            threshold = spec.get("max", spec.get("min", "N/A"))
            op = "<=" if "max" in spec else ">="
            lines.append(f"| {key} | {op} {threshold} |")
        lines.append("")

        lines.append("## Experiment Results")
        lines.append("")

        by_experiment = {}
        for r in self.results:
            exp = r.get("experiment", "unknown")
            by_experiment.setdefault(exp, []).append(r)

        for exp_name, exp_results in by_experiment.items():
            lines.append(f"### {exp_name}")
            lines.append("")

            ok_results = [r for r in exp_results if r.get("status") == "OK"]
            candidates = [r for r in ok_results if r.get("is_candidate")]

            lines.append(f"- Configs: {len(exp_results)}")
            lines.append(f"- OK: {len(ok_results)}")
            lines.append(f"- Candidates: {len(candidates)}")
            lines.append("")

            if ok_results:
                lines.append("| Label | IR | Turnover | Fallback% | 2x Excess | Candidate |")
                lines.append("|-------|----|----------|-----------|-----------|-----------|")
                for r in ok_results:
                    lines.append(
                        f"| {r.get('label', '')} | "
                        f"{_fmt(r.get('information_ratio'), '.3f')} | "
                        f"{_fmt(r.get('avg_turnover'), '.3f')} | "
                        f"{_fmt(r.get('optimizer_fallback_rate'), '.3f')} | "
                        f"{_fmt(r.get('cost_2x_excess'), '.4f')} | "
                        f"{'YES' if r.get('is_candidate') else 'no'} |"
                    )
                lines.append("")

        lines.append("## Top Candidates")
        lines.append("")

        if self.candidates:
            sorted_cands = sorted(
                self.candidates,
                key=lambda x: x.get("information_ratio", 0),
                reverse=True,
            )

            lines.append("| Rank | Label | IR | Turnover | Fallback% | 2x Excess |")
            lines.append("|------|-------|----|----------|-----------|-----------|")
            for i, c in enumerate(sorted_cands[:20], 1):
                lines.append(
                    f"| {i} | {c.get('label', '')} | "
                    f"{_fmt(c.get('information_ratio'), '.3f')} | "
                    f"{_fmt(c.get('avg_turnover'), '.3f')} | "
                    f"{_fmt(c.get('optimizer_fallback_rate'), '.3f')} | "
                    f"{_fmt(c.get('cost_2x_excess'), '.4f')} |"
                )
        else:
            lines.append("No configurations passed all candidate filters.")
            lines.append("")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _make_label(self, exp_name: str, config: Dict[str, Any],
                    index: int) -> str:
        """Generate a readable label for a config."""
        parts = [exp_name]
        for key in sorted(config.keys()):
            if key not in BACKTEST_PARAM_KEYS and key != "experiment":
                continue
            val = config[key]
            if isinstance(val, float):
                parts.append(f"{key}={val:.4f}")
            else:
                parts.append(f"{key}={val}")
        if len(parts) == 1:
            parts.append(f"#{index}")
        return "_".join(parts[:4])


def _fmt(val, fmt_str: str) -> str:
    """Format a float value for display."""
    if val is None:
        return "N/A"
    if isinstance(val, float) and np.isnan(val):
        return "N/A"
    try:
        return format(float(val), fmt_str)
    except (TypeError, ValueError):
        return str(val)


def _safe_num(val, default: float = 0.0) -> float:
    """Convert to float, returning default for non-numeric/NaN values."""
    if val is None:
        return default
    if isinstance(val, float) and np.isnan(val):
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default

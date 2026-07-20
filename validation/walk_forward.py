"""
Walk-forward validation framework.

Implements time-series cross-validation with:
- Expanding or rolling window
- Purge + embargo to prevent overlap leakage
- Train/test IC comparison
- OOS stability diagnostics
- Parameter sensitivity

Reuses code_v3 ML walk-forward concepts adapted for cross-sectional setting.
"""

import logging
from typing import Optional, List, Dict, Any, Tuple, Callable

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class WalkForwardValidator:
    """
    Walk-forward validation for cross-sectional alpha strategies.

    Given a function that takes (train_dates, test_dates) and returns
    performance metrics, performs sequential train/test splits and
    aggregates results.
    """

    def __init__(self,
                 n_initial_train: int = 252,
                 n_test: int = 21,
                 n_retrain: int = 63,
                 purge_days: int = 5,
                 embargo_days: int = 60,
                 expanding_window: bool = True,
                 rolling_window_size: Optional[int] = None):
        self.n_initial_train = n_initial_train
        self.n_test = n_test
        self.n_retrain = n_retrain
        self.purge_days = purge_days
        self.embargo_days = embargo_days
        self.expanding_window = expanding_window
        self.rolling_window_size = rolling_window_size

    # ------------------------------------------------------------------
    # Split generation
    # ------------------------------------------------------------------
    def generate_splits(self, dates: List[int]) -> List[Dict[str, Any]]:
        """
        Generate walk-forward train/test splits.

        Parameters
        ----------
        dates : list of int
            Sorted trade dates.

        Returns
        -------
        list of dicts with: train_start, train_end, test_start, test_end, fold_id.
        """
        dates = sorted(dates)
        if len(dates) < self.n_initial_train + self.n_test:
            return []

        splits = []
        fold_id = 0

        test_start_idx = self.n_initial_train
        while test_start_idx + self.n_test <= len(dates):
            test_dates = dates[test_start_idx:test_start_idx + self.n_test]
            test_start = test_dates[0]
            test_end = test_dates[-1]

            # Training dates end before test_start - embargo_days
            train_end_idx = test_start_idx - self.embargo_days
            if train_end_idx <= 0:
                test_start_idx += self.n_retrain
                continue

            if self.expanding_window:
                train_start = dates[0]
            elif self.rolling_window_size:
                train_start_idx = max(0, train_end_idx - self.rolling_window_size)
                train_start = dates[train_start_idx]
            else:
                train_start = dates[0]

            train_end = dates[min(train_end_idx - 1, len(dates) - 1)]

            # Purge: remove training samples that overlap with test
            train_dates = [d for d in dates
                           if train_start <= d <= train_end
                           and d < test_start - self.purge_days]

            if len(train_dates) < 20:
                test_start_idx += self.n_retrain
                continue

            splits.append({
                "fold_id": fold_id,
                "train_start": train_start,
                "train_end": train_end,
                "test_start": test_start,
                "test_end": test_end,
                "n_train_dates": len(train_dates),
                "n_test_dates": len(test_dates),
            })

            fold_id += 1
            test_start_idx += self.n_retrain

        return splits

    # ------------------------------------------------------------------
    # Run validation
    # ------------------------------------------------------------------
    def run(self, dates: List[int],
            train_fn: Callable[[List[int]], Any],
            test_fn: Callable[[Any, List[int]], Dict[str, float]]
            ) -> List[Dict[str, Any]]:
        """
        Run walk-forward validation.

        Parameters
        ----------
        dates : list of int
            Sorted trade dates.
        train_fn : callable
            Function(train_dates) -> model_state.
        test_fn : callable
            Function(model_state, test_dates) -> metrics_dict.

        Returns
        -------
        list of fold results.
        """
        splits = self.generate_splits(dates)

        if not splits:
            logger.error("No valid splits generated")
            return []

        results = []
        model_state = None

        for split in splits:
            train_dates = [d for d in dates
                           if split["train_start"] <= d <= split["train_end"]]
            test_dates = [d for d in dates
                          if split["test_start"] <= d <= split["test_end"]]

            logger.info(f"Fold {split['fold_id']}: "
                         f"train {split['train_start']}-{split['train_end']} "
                         f"({len(train_dates)}d) -> "
                         f"test {split['test_start']}-{split['test_end']} "
                         f"({len(test_dates)}d)")

            try:
                # Train
                if model_state is None or split["fold_id"] % max(1, self.n_retrain // self.n_test) == 0:
                    model_state = train_fn(train_dates)

                # Test
                metrics = test_fn(model_state, test_dates)

                fold_result = {**split, **metrics}
                results.append(fold_result)

            except Exception as e:
                logger.error(f"Fold {split['fold_id']} failed: {e}")
                continue

        return results

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    @staticmethod
    def summarize(results: List[Dict[str, Any]],
                  metric_keys: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Summarize walk-forward results across folds.

        Parameters
        ----------
        results : list of dict
            Fold results from run().
        metric_keys : list of str, optional
            Keys to summarize. If None, auto-detect numeric keys.

        Returns
        -------
        dict with mean, std, min, max, last per metric.
        """
        if not results:
            return {"n_folds": 0}

        if metric_keys is None:
            # Auto-detect numeric keys
            first = results[0]
            metric_keys = [k for k, v in first.items()
                           if isinstance(v, (int, float, np.floating))]
            # Exclude metadata keys
            exclude = {"fold_id", "train_start", "train_end", "test_start",
                       "test_end", "n_train_dates", "n_test_dates"}
            metric_keys = [k for k in metric_keys if k not in exclude]

        summary = {"n_folds": len(results)}

        for key in metric_keys:
            values = [r.get(key, np.nan) for r in results if key in r]
            values = [v for v in values if not np.isnan(v)]

            if not values:
                continue

            summary[f"{key}_mean"] = float(np.mean(values))
            summary[f"{key}_std"] = float(np.std(values))
            summary[f"{key}_min"] = float(np.min(values))
            summary[f"{key}_max"] = float(np.max(values))
            summary[f"{key}_last"] = float(values[-1])
            summary[f"{key}_trend"] = float(values[-1] - values[0]) if len(values) > 1 else 0.0

        return summary

    # ------------------------------------------------------------------
    # Stability diagnostics
    # ------------------------------------------------------------------
    @staticmethod
    def stability_report(results: List[Dict[str, Any]],
                         ic_key: str = "rank_ic") -> str:
        """
        Generate OOS stability report.

        Checks for:
        - IC collapse (declining OOS IC over folds)
        - IC variability
        - Regime-dependent performance
        """
        if not results:
            return "No results to report."

        ics = [r.get(ic_key, np.nan) for r in results]
        ics = [v for v in ics if not np.isnan(v)]

        if len(ics) < 2:
            return "Insufficient folds for stability analysis."

        lines = []
        lines.append("## Walk-Forward Stability Report")
        lines.append("")

        mean_ic = np.mean(ics)
        std_ic = np.std(ics)
        trend = ics[-1] - ics[0] if len(ics) > 1 else 0

        lines.append(f"- Mean OOS IC: {mean_ic:.4f}")
        lines.append(f"- Std OOS IC: {std_ic:.4f}")
        lines.append(f"- IC Trend: {trend:.4f}")
        lines.append(f"- N Folds: {len(ics)}")
        lines.append("")

        # Stability assessment
        if trend < -0.05:
            lines.append("⚠️ **WARNING**: Significant IC decline — possible alpha decay.")
        elif trend < -0.02:
            lines.append("⚡ **CAUTION**: Mild IC decline — monitor closely.")
        else:
            lines.append("✓ IC stable across folds.")

        if std_ic > abs(mean_ic) * 2:
            lines.append("⚠️ **WARNING**: High IC variability — OOS performance inconsistent.")

        positive_rate = (np.array(ics) > 0).mean()
        if positive_rate < 0.55:
            lines.append(f"⚠️ **CAUTION**: IC positive rate {positive_rate:.1%} below 55%.")

        lines.append("")
        lines.append(f"IC series: {', '.join(f'{v:.3f}' for v in ics[:10])}"
                     f"{'...' if len(ics) > 10 else ''}")

        return "\n".join(lines)

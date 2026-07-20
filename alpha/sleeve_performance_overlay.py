"""
Performance overlay for regime strategy sleeves.

The regime allocator maps observable market regimes to base sleeve weights.
This module adds a second, point-in-time layer: recent realised sleeve IC
controls a multiplier applied to each sleeve before allocator constraints.

The overlay never inverts a sleeve and never uses unmatured forward returns.
It only increases or decreases the non-negative sleeve allocation multiplier.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Sequence, Tuple

import numpy as np
import pandas as pd

from alpha.time_utils import calendar_month_lookback_start, matured_ic_cutoff

logger = logging.getLogger(__name__)

SLEEVE_NAMES = ["reversal", "momentum", "defensive", "value", "volume_price", "shock_reversal"]


class SleevePerformanceOverlay:
    """Compute PIT-safe sleeve allocation multipliers from recent sleeve IC.

    Parameters
    ----------
    config : dict
        ``sleeve_performance_overlay`` config from ``configs/regime.yaml``.
    """

    def __init__(self, config: dict):
        self.enabled = bool(config.get("enabled", False))
        self.lookback_months = int(config.get("lookback_months", 6))
        self.horizon = int(config.get("horizon", 5))
        self.min_obs = int(config.get("min_obs", 12))
        self.min_stocks = int(config.get("min_stocks", 30))

        self.icir_weight = float(config.get("icir_weight", 0.70))
        self.hit_rate_weight = float(config.get("hit_rate_weight", 0.30))
        self.icir_scale = float(config.get("icir_scale", 0.50))
        self.strength = float(config.get("strength", 0.50))
        self.multiplier_min = float(config.get("multiplier_min", 0.60))
        self.multiplier_max = float(config.get("multiplier_max", 1.60))
        self.neutral_multiplier = float(config.get("neutral_multiplier", 1.0))

    def compute_multipliers(
        self,
        sleeve_scores: Dict[str, pd.DataFrame],
        fwd_returns: pd.DataFrame,
        signal_dates: Sequence[int],
        trade_dates: Sequence[int] | None = None,
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """Return per-date sleeve multipliers and long-form diagnostics.

        Returns
        -------
        multipliers : pd.DataFrame
            Columns: ``trade_date`` and ``{sleeve}_multiplier``.
        metrics : pd.DataFrame
            Long-form diagnostics with one row per ``trade_date × sleeve``.
        """
        signal_dates = sorted(int(d) for d in signal_dates)
        if not self.enabled or not signal_dates:
            return pd.DataFrame(), pd.DataFrame()

        ret_col = f"fwd_ret_{self.horizon}d"
        if fwd_returns.empty or ret_col not in fwd_returns.columns:
            logger.warning(
                "Sleeve overlay disabled for this run: missing %s in fwd_returns",
                ret_col,
            )
            return self._neutral_multipliers(signal_dates), pd.DataFrame()

        if trade_dates is None:
            trade_dates = sorted(int(d) for d in fwd_returns["trade_date"].dropna().unique())
        else:
            trade_dates = sorted(int(d) for d in trade_dates)

        ic_history = self._compute_ic_history(sleeve_scores, fwd_returns, ret_col)

        rows: List[dict] = []
        metric_rows: List[dict] = []
        for signal_date in signal_dates:
            row = {"trade_date": signal_date}
            cutoff = matured_ic_cutoff(signal_date, self.horizon, trade_dates)
            lookback_start = calendar_month_lookback_start(
                signal_date, self.lookback_months
            )

            for sleeve in SLEEVE_NAMES:
                metric = self._score_sleeve_window(
                    ic_history, sleeve, signal_date, lookback_start, cutoff
                )
                row[f"{sleeve}_multiplier"] = metric["multiplier"]
                metric_rows.append(metric)

            rows.append(row)

        return pd.DataFrame(rows), pd.DataFrame(metric_rows)

    def _compute_ic_history(
        self,
        sleeve_scores: Dict[str, pd.DataFrame],
        fwd_returns: pd.DataFrame,
        ret_col: str,
    ) -> pd.DataFrame:
        """Compute realised cross-sectional sleeve IC by date."""
        fwd = fwd_returns[["ts_code", "trade_date", ret_col]].dropna().copy()
        records: List[dict] = []

        for sleeve, scores in sleeve_scores.items():
            if sleeve not in SLEEVE_NAMES or scores is None or scores.empty:
                continue
            needed = {"ts_code", "trade_date", "composite_score"}
            if not needed.issubset(scores.columns):
                continue

            merged = scores[["ts_code", "trade_date", "composite_score"]].merge(
                fwd, on=["ts_code", "trade_date"], how="inner"
            )
            merged = merged.dropna(subset=["composite_score", ret_col])
            if merged.empty:
                continue

            for trade_date, group in merged.groupby("trade_date"):
                if len(group) < self.min_stocks:
                    continue
                if group["composite_score"].nunique() < 2 or group[ret_col].nunique() < 2:
                    continue

                ic = group["composite_score"].corr(group[ret_col], method="spearman")
                if pd.isna(ic):
                    continue
                records.append({
                    "sleeve": sleeve,
                    "trade_date": int(trade_date),
                    "ic": float(ic),
                    "n_stocks": int(len(group)),
                })

        if not records:
            return pd.DataFrame(columns=["sleeve", "trade_date", "ic", "n_stocks"])
        return pd.DataFrame(records)

    def _score_sleeve_window(
        self,
        ic_history: pd.DataFrame,
        sleeve: str,
        signal_date: int,
        lookback_start: int,
        cutoff: int | None,
    ) -> dict:
        """Score one sleeve using only mature IC observations."""
        base = {
            "trade_date": signal_date,
            "sleeve": sleeve,
            "lookback_start": lookback_start,
            "ic_cutoff": cutoff,
            "n_obs": 0,
            "mean_ic": np.nan,
            "std_ic": np.nan,
            "icir": np.nan,
            "hit_rate": np.nan,
            "quality_score": 0.0,
            "multiplier": self.neutral_multiplier,
            "status": "insufficient_history",
        }
        if cutoff is None or ic_history.empty:
            return base

        window = ic_history[
            (ic_history["sleeve"] == sleeve) &
            (ic_history["trade_date"] >= lookback_start) &
            (ic_history["trade_date"] <= cutoff)
        ]["ic"].dropna()

        base["n_obs"] = int(len(window))
        if len(window) < self.min_obs:
            return base

        mean_ic = float(window.mean())
        std_ic = float(window.std(ddof=0))
        if not np.isfinite(std_ic) or std_ic <= 1e-12:
            icir = 0.0
        else:
            icir = mean_ic / std_ic
        hit_rate = float((window > 0).mean())

        quality_score = self._quality_score(icir, hit_rate)
        multiplier = float(
            np.clip(
                self.neutral_multiplier + self.strength * quality_score,
                self.multiplier_min,
                self.multiplier_max,
            )
        )

        base.update({
            "mean_ic": mean_ic,
            "std_ic": std_ic,
            "icir": float(icir),
            "hit_rate": hit_rate,
            "quality_score": quality_score,
            "multiplier": multiplier,
            "status": "ok",
        })
        return base

    def _quality_score(self, icir: float, hit_rate: float) -> float:
        """Map ICIR and positive-IC hit rate to [-1, 1]."""
        total_weight = self.icir_weight + self.hit_rate_weight
        if total_weight <= 1e-12:
            return 0.0

        scale = self.icir_scale if self.icir_scale > 1e-12 else 1.0
        icir_component = float(np.tanh(icir / scale))
        hit_component = float(2.0 * hit_rate - 1.0)
        score = (
            self.icir_weight * icir_component +
            self.hit_rate_weight * hit_component
        ) / total_weight
        return float(np.clip(score, -1.0, 1.0))

    def _neutral_multipliers(self, signal_dates: Sequence[int]) -> pd.DataFrame:
        rows = []
        for d in signal_dates:
            row = {"trade_date": int(d)}
            for sleeve in SLEEVE_NAMES:
                row[f"{sleeve}_multiplier"] = self.neutral_multiplier
            rows.append(row)
        return pd.DataFrame(rows)

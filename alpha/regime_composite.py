"""
Regime Composite Builder.

Combines multiple strategy sleeve scores with regime-driven weights
into a single final composite score.  The output has the same schema
as ICWeighting's output, so downstream consumers (ScoreToMu, backtester)
work unchanged.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Canonical sleeve names
SLEEVE_NAMES = ["reversal", "momentum", "defensive", "value", "volume_price", "shock_reversal"]


class RegimeCompositeBuilder:
    """Combine sleeve scores and weights into a final composite score.

    Parameters
    ----------
    min_sleeves : int
        Minimum number of sleeves with valid scores required to produce
        a composite.  Default 2.
    """

    def __init__(self, min_sleeves: int = 2):
        self.min_sleeves = min_sleeves

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build(
        self,
        sleeve_scores: Dict[str, pd.DataFrame],
        sleeve_weights: pd.DataFrame,
    ) -> pd.DataFrame:
        """Build final composite score from sleeve scores and weights.

        Parameters
        ----------
        sleeve_scores : dict
            ``{sleeve_name: composite_score_df}`` from ``StrategySleeveEngine``.
            Each DataFrame has columns ``[ts_code, trade_date, composite_score]``.
        sleeve_weights : pd.DataFrame
            From ``RegimeAllocator.compute_sleeve_weights()``.
            Columns: ``trade_date``, ``{sleeve_name}_weight``.

        Returns
        -------
        pd.DataFrame
            ``[ts_code, trade_date, composite_score]`` — same schema as
            ``ICWeighting.compute_composite_series()``.
        """
        if sleeve_weights.empty:
            logger.warning("Empty sleeve weights — returning empty composite")
            return pd.DataFrame()

        # Index sleeve weights by trade_date
        weight_cols = [f"{name}_weight" for name in SLEEVE_NAMES]
        available_weight_cols = [c for c in weight_cols if c in sleeve_weights.columns]

        if not available_weight_cols:
            logger.warning("No weight columns found in sleeve_weights")
            return pd.DataFrame()

        weights_indexed = sleeve_weights.set_index("trade_date")

        # Collect all trade_dates from all sleeve scores
        all_dates: set = set()
        for df in sleeve_scores.values():
            if df is not None and not df.empty:
                all_dates.update(int(d) for d in df["trade_date"].unique())

        if not all_dates:
            logger.warning("No sleeve scores available")
            return pd.DataFrame()

        # Also get dates from weights
        all_dates.update(int(d) for d in weights_indexed.index)

        all_rows: List[dict] = []

        for trade_date in sorted(all_dates):
            rows_for_date = self._build_date(
                trade_date, sleeve_scores, weights_indexed, available_weight_cols
            )
            all_rows.extend(rows_for_date)

        if not all_rows:
            logger.warning("No composite rows built")
            return pd.DataFrame()

        composite = pd.DataFrame(all_rows)

        # Cross-sectional z-score the final composite per date
        composite = self._cross_sectional_zscore(composite)

        logger.info(
            "Regime composite: %d rows, %d dates",
            len(composite), composite["trade_date"].nunique(),
        )

        return composite

    # ------------------------------------------------------------------
    # Per-date builder (private)
    # ------------------------------------------------------------------

    def _build_date(
        self,
        trade_date: int,
        sleeve_scores: Dict[str, pd.DataFrame],
        weights_indexed: pd.DataFrame,
        weight_cols: List[str],
    ) -> List[dict]:
        """Build composite rows for a single trade_date.

        final_score = Σ(w_sleeve × score_sleeve) across sleeves with data.
        """
        # Get weights for this date
        if trade_date in weights_indexed.index:
            weight_row = weights_indexed.loc[trade_date]
            if isinstance(weight_row, pd.DataFrame):
                weight_row = weight_row.iloc[0]
        else:
            return []  # no weights for this date

        # Collect sleeve scores for this date
        weighted_scores: Dict[str, pd.DataFrame] = {}
        active_sleeves: List[str] = []

        for name in SLEEVE_NAMES:
            weight_col = f"{name}_weight"
            if weight_col not in weight_cols:
                continue

            w = float(weight_row.get(weight_col, 0.0))
            if w < 1e-8:
                continue  # zero weight, skip

            df = sleeve_scores.get(name)
            if df is None or df.empty:
                continue

            date_df = df[df["trade_date"] == trade_date]
            if date_df.empty:
                continue

            # Store weighted scores
            date_df = date_df.copy()
            date_df["weighted_score"] = date_df["composite_score"] * w
            weighted_scores[name] = date_df
            active_sleeves.append(name)

        if len(active_sleeves) < self.min_sleeves:
            logger.debug(
                "trade_date=%d: only %d sleeves with scores (min=%d) — skipping",
                trade_date, len(active_sleeves), self.min_sleeves,
            )
            return []

        # Merge all sleeve scores by ts_code and sum weighted scores
        # Strategy: concatenate all weighted score DataFrames, then groupby ts_code
        parts = []
        for name, df in weighted_scores.items():
            parts.append(df[["ts_code", "trade_date", "weighted_score"]])

        if not parts:
            return []

        merged = pd.concat(parts, ignore_index=True)
        final = merged.groupby(["ts_code", "trade_date"], as_index=False)["weighted_score"].sum()
        final = final.rename(columns={"weighted_score": "composite_score"})

        return final.to_dict("records")

    # ------------------------------------------------------------------
    # Cross-sectional normalization (private)
    # ------------------------------------------------------------------

    @staticmethod
    def _cross_sectional_zscore(composite: pd.DataFrame) -> pd.DataFrame:
        """Z-score composite_score cross-sectionally per trade_date."""
        if composite.empty:
            return composite

        result_parts = []
        for trade_date, group in composite.groupby("trade_date"):
            scores = group["composite_score"].values.astype(float)
            mean = np.nanmean(scores)
            std = np.nanstd(scores)

            group = group.copy()
            if std is not None and std > 1e-8:
                group["composite_score"] = (scores - mean) / std
            else:
                group["composite_score"] = 0.0

            result_parts.append(group)

        return pd.concat(result_parts, ignore_index=True)

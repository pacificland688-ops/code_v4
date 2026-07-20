"""
Regime-to-sleeve weight allocator.

Converts regime probabilities into strategy sleeve weights using a
configurable mapping matrix, with constraints for:
  - Weight caps and floors per sleeve
  - Weight change smoothing (prevents abrupt rotations)
  - Missing sleeve renormalization
  - Minimum sleeve count safety valve

All computations are per-date; no forward-looking.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# The canonical sleeve order (matches regime.yaml mapping matrix columns)
SLEEVE_NAMES = ["reversal", "momentum", "defensive", "value", "volume_price", "shock_reversal"]
REGIME_NAMES = ["trend_up", "trend_down", "range_bound", "high_volatility", "value_rotation"]


class RegimeAllocator:
    """Convert regime probabilities to sleeve weights with risk constraints.

    Parameters
    ----------
    config : dict
        Allocator configuration (from regime.yaml ``allocator`` section).
    """

    def __init__(self, config: dict):
        # --- constraints ---
        self.min_sleeves = int(config.get("min_sleeves", 2))
        self.sleeve_weight_cap = float(config.get("sleeve_weight_cap", 0.50))
        self.sleeve_weight_floor = float(config.get("sleeve_weight_floor", 0.05))
        self.max_weekly_change = float(config.get("max_weekly_weight_change", 0.15))

        # --- mapping matrix ---
        self.mapping = self._build_mapping_matrix(
            config.get("regime_to_sleeve_weights", {})
        )

        # --- state for smoothing ---
        self._prev_weights: Optional[Dict[str, float]] = None
        self._prev_date: Optional[int] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def compute_sleeve_weights(
        self,
        regime_probs: pd.DataFrame,
        available_sleeves: Optional[Dict[int, List[str]]] = None,
        sleeve_multipliers: Optional[pd.DataFrame] = None,
    ) -> pd.DataFrame:
        """Compute sleeve weights from regime probabilities.

        Parameters
        ----------
        regime_probs : pd.DataFrame
            Output of ``RegimeDetector.predict_regime_probs()``.
            Must have columns: ``trade_date`` and ``*_prob`` columns
            matching REGIME_NAMES.
        available_sleeves : dict, optional
            Mapping ``{trade_date: [sleeve_name, ...]}`` of sleeves that
            have valid scores for that date.  If None, all sleeves are
            considered available.
        sleeve_multipliers : pd.DataFrame, optional
            Per-date performance overlay multipliers.  Expected columns are
            ``trade_date`` and ``{sleeve_name}_multiplier``.  Multipliers are
            applied before floor/cap/smoothing constraints.

        Returns
        -------
        pd.DataFrame
            Columns: ``trade_date``, ``reversal_weight``, ``momentum_weight``,
            ``defensive_weight``, ``value_weight``, ``volume_price_weight``.
            Weights sum to 1.0 per date (if enough sleeves available).
            Returns empty DataFrame if no valid dates.
        """
        if regime_probs.empty:
            return pd.DataFrame()

        # Reset smoothing state for fresh computation
        self._prev_weights = None
        self._prev_date = None

        # Sort by trade_date for smoothing
        regime_probs = regime_probs.sort_values("trade_date").reset_index(drop=True)

        # Build probability vectors
        prob_cols = _find_prob_columns(regime_probs, REGIME_NAMES)
        multiplier_indexed = self._prepare_multipliers(sleeve_multipliers)

        rows = []
        for _, row in regime_probs.iterrows():
            trade_date = int(row["trade_date"])

            # Get regime probability vector (in REGIME_NAMES order)
            probs = np.array([float(row.get(c, 0.0)) for c in prob_cols], dtype=float)

            # Matrix multiply: sleeve_weights = regime_probs @ mapping_matrix
            raw_weights = probs @ self.mapping  # shape: (n_sleeves,)
            raw_weights = self._apply_multipliers(
                raw_weights, trade_date, multiplier_indexed
            )

            # Convert to dict
            weights = dict(zip(SLEEVE_NAMES, raw_weights))

            # Get available sleeves for this date
            avail = None
            if available_sleeves is not None:
                avail = available_sleeves.get(trade_date, None)

            # Apply constraints
            weights = self._apply_constraints(weights, avail, trade_date)

            if weights is None:
                # Insufficient sleeves — skip this date
                continue

            row_data = {"trade_date": trade_date}
            for name in SLEEVE_NAMES:
                row_data[f"{name}_weight"] = weights.get(name, 0.0)
            rows.append(row_data)

            # Update smoothing state
            self._prev_weights = weights
            self._prev_date = trade_date

        if not rows:
            return pd.DataFrame()

        return pd.DataFrame(rows)

    def _prepare_multipliers(
        self,
        sleeve_multipliers: Optional[pd.DataFrame],
    ) -> Optional[pd.DataFrame]:
        """Validate and index optional sleeve multiplier data."""
        if sleeve_multipliers is None or sleeve_multipliers.empty:
            return None
        if "trade_date" not in sleeve_multipliers.columns:
            logger.warning("Ignoring sleeve_multipliers without trade_date column")
            return None
        return sleeve_multipliers.set_index("trade_date")

    def _apply_multipliers(
        self,
        raw_weights: np.ndarray,
        trade_date: int,
        multiplier_indexed: Optional[pd.DataFrame],
    ) -> np.ndarray:
        """Apply performance overlay multipliers for one date."""
        if multiplier_indexed is None or trade_date not in multiplier_indexed.index:
            return raw_weights

        row = multiplier_indexed.loc[trade_date]
        if isinstance(row, pd.DataFrame):
            row = row.iloc[0]

        multipliers = []
        for sleeve in SLEEVE_NAMES:
            m = row.get(f"{sleeve}_multiplier", 1.0)
            if pd.isna(m) or not np.isfinite(float(m)):
                m = 1.0
            multipliers.append(max(float(m), 0.0))
        return raw_weights * np.array(multipliers, dtype=float)

    # ------------------------------------------------------------------
    # Constraint application (private)
    # ------------------------------------------------------------------

    def _apply_constraints(
        self,
        weights: Dict[str, float],
        available: Optional[List[str]],
        trade_date: int,
    ) -> Optional[Dict[str, float]]:
        """Apply all constraints to raw weights for one date.

        Returns None if insufficient sleeves are available.
        """
        # 1. Zero out unavailable sleeves
        if available is not None:
            for name in SLEEVE_NAMES:
                if name not in available:
                    weights[name] = 0.0

        # 2. Check min_sleeves
        active = [name for name in SLEEVE_NAMES if weights.get(name, 0.0) > 1e-8]
        if len(active) < self.min_sleeves:
            logger.debug(
                "trade_date=%d: only %d sleeves available (min=%d) — no signal",
                trade_date, len(active), self.min_sleeves,
            )
            return None

        # 3. Renormalize active weights to sum to 1.0
        total = sum(weights.values())
        if total > 1e-8:
            weights = {k: v / total for k, v in weights.items()}
        else:
            return None

        # 4. Apply floor: any weight < floor gets set to 0 and redistributed
        weights = self._apply_floor(weights)

        # 5. Apply cap: any weight > cap gets clipped and excess redistributed
        weights = self._apply_cap(weights)

        # 6. Apply smoothing vs previous weights
        if self._prev_weights is not None:
            weights = self._apply_smoothing(weights)

        # 7. Re-apply unavailable hard mask after smoothing
        #    Availability priority > smoothing
        if available is not None:
            for name in SLEEVE_NAMES:
                if name not in available:
                    weights[name] = 0.0

        # Final check
        active = [name for name in SLEEVE_NAMES if weights.get(name, 0.0) > 1e-8]
        if len(active) < self.min_sleeves:
            return None

        # Ensure sum to 1.0
        total = sum(weights.values())
        if total > 1e-8:
            weights = {k: v / total for k, v in weights.items()}

        return weights

    def _apply_floor(self, weights: Dict[str, float]) -> Dict[str, float]:
        """Set weights below floor to 0, redistribute to others.

        Only applies if there are enough sleeves above floor.
        """
        floor = self.sleeve_weight_floor
        below = [k for k, v in weights.items() if 0 < v < floor]
        above = [k for k, v in weights.items() if v >= floor]

        if not below:
            return weights

        # If removing below-floor sleeves would leave too few, skip the floor
        if len(above) < self.min_sleeves:
            return weights

        # Redistribute: zero out below-floor, give excess to above
        excess = sum(weights[k] for k in below)
        above_total = sum(weights[k] for k in above)

        result = {k: 0.0 for k in below}
        for k in above:
            if above_total > 1e-8:
                result[k] = weights[k] + excess * (weights[k] / above_total)
            else:
                result[k] = 1.0 / len(above)
        return result

    def _apply_cap(self, weights: Dict[str, float]) -> Dict[str, float]:
        """Iteratively cap weights above ceiling, redistribute excess.

        Similar to ICWeighting._apply_hard_cap logic.
        """
        cap = self.sleeve_weight_cap
        active = {k: v for k, v in weights.items() if v > 1e-8}

        if not active:
            return weights

        for _ in range(20):  # safety iteration limit
            capped = {k: v for k, v in active.items() if v > cap}
            if not capped:
                break

            # Reduce capped weights to cap
            excess = sum(v - cap for v in capped.values())
            uncapped = {k: v for k, v in active.items() if v <= cap and v > 0}

            for k in capped:
                active[k] = cap

            if not uncapped:
                # All weights are capped — distribute equally
                n = len(active)
                for k in active:
                    active[k] = 1.0 / n
                break

            # Distribute excess to uncapped proportionally
            uncapped_total = sum(uncapped.values())
            for k in uncapped:
                if uncapped_total > 1e-8:
                    active[k] += excess * (uncapped[k] / uncapped_total)

        return active

    def _apply_smoothing(self, weights: Dict[str, float]) -> Dict[str, float]:
        """Smooth weights vs previous period using max_weekly_change clamp.

        |new_weight - prev_weight| <= max_weekly_change for each sleeve.

        Uses iterative clamp + renormalize to ensure the constraint holds
        after normalization (renormalization can push weights slightly
        beyond the delta bound).
        """
        prev = self._prev_weights
        max_delta = self.max_weekly_change

        # Start with target weights
        smoothed = dict(weights)

        for _ in range(5):  # iterate to convergence
            # Clamp each weight to [prev - max_delta, prev + max_delta]
            clamped = {}
            for name in SLEEVE_NAMES:
                pw = prev.get(name, 0.0)
                cw = smoothed.get(name, 0.0)
                lower = max(0.0, pw - max_delta)
                upper = min(1.0, pw + max_delta)
                clamped[name] = np.clip(cw, lower, upper)

            # Renormalize
            total = sum(clamped.values())
            if total > 1e-8:
                clamped = {k: v / total for k, v in clamped.items()}

            # Check if any weight still violates the constraint significantly
            max_violation = 0.0
            for name in SLEEVE_NAMES:
                pw = prev.get(name, 0.0)
                cw = clamped.get(name, 0.0)
                violation = abs(cw - pw) - max_delta
                if violation > 1e-8:
                    max_violation = max(max_violation, violation)

            smoothed = clamped

            if max_violation < 1e-6:
                break

        return smoothed

    # ------------------------------------------------------------------
    # Mapping matrix builder (private)
    # ------------------------------------------------------------------

    def _build_mapping_matrix(self, regime_weights: dict) -> np.ndarray:
        """Build (n_regimes × n_sleeves) mapping matrix from YAML config.

        Parameters
        ----------
        regime_weights : dict
            Nested dict: {regime_name: {sleeve_name: weight, ...}, ...}

        Returns
        -------
        np.ndarray
            Shape (5, 5) in (REGIME_NAMES, SLEEVE_NAMES) order.
        """
        matrix = np.zeros((len(REGIME_NAMES), len(SLEEVE_NAMES)), dtype=float)

        for i, regime in enumerate(REGIME_NAMES):
            sleeve_map = regime_weights.get(regime, {})
            for j, sleeve in enumerate(SLEEVE_NAMES):
                matrix[i, j] = float(sleeve_map.get(sleeve, 0.0))

            # Normalize row to sum to 1.0
            row_sum = matrix[i].sum()
            if row_sum > 1e-8:
                matrix[i] /= row_sum
            else:
                # Fallback: equal weight
                matrix[i] = 1.0 / len(SLEEVE_NAMES)

        return matrix


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_prob_columns(df: pd.DataFrame, regime_names: List[str]) -> List[str]:
    """Find probability columns matching regime names.

    Tries exact ``{name}_prob`` matches first, then falls back to
    any column ending in ``_prob``.
    """
    expected = [f"{r}_prob" for r in regime_names]
    available = []
    for col in expected:
        if col in df.columns:
            available.append(col)
    if len(available) == len(regime_names):
        return available

    # Fallback: any _prob columns
    prob_cols = sorted([c for c in df.columns if c.endswith("_prob")])
    if len(prob_cols) >= len(regime_names):
        return prob_cols[: len(regime_names)]

    return expected  # will produce NaN/0 weights

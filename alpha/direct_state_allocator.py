"""
Direct state-to-sleeve allocator (Plan B).

Maps continuous PIT market state features directly to sleeve multipliers
without the intermediate 5-class regime softmax classification.

B1 rules (volatility / breadth → momentum):
  - High vol  (volatility_state >= PIT expanding q75) → momentum × 0.50
  - High breadth (breadth_score >= q75 AND vol < q75) → momentum × 1.25
  - Default → momentum × 1.00

Base weights are equal across available sleeves; the rule multiplier only
adjusts the target sleeve (momentum by default).  Standard floor / cap /
smoothing constraints are applied afterwards, mirroring RegimeAllocator.

Output schema is compatible with RegimeCompositeBuilder:
  ``trade_date, reversal_weight, momentum_weight, ...``
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

SLEEVE_NAMES = [
    "reversal", "momentum", "defensive", "value", "volume_price", "shock_reversal",
]


class DirectStateAllocator:
    """Map PIT market state features directly to sleeve weights.

    Parameters
    ----------
    config : dict
        ``direct_state_allocator`` section from the config YAML.
    """

    def __init__(self, config: dict):
        # --- PIT threshold params ---
        self.min_warmup_trading_days = int(config.get("min_warmup_trading_days", 252))
        # Number of signal observations before rules activate (weekly: 252 td ≈ 52)
        self.min_warmup_obs = int(config.get(
            "min_warmup_signal_observations",
            max(int(self.min_warmup_trading_days / 5), 20),
        ))

        # --- Feature names ---
        self.state_features = list(config.get(
            "features",
            ["volatility_state", "breadth_score"],
        ))

        # --- Rules ---
        rules_cfg = config.get("rules", {})
        self.high_quantile = float(rules_cfg.get("high_quantile", 0.75))
        self.target_sleeve = str(rules_cfg.get("target_sleeve", "momentum"))

        self.mult_high_vol = float(
            rules_cfg.get("rule_high_vol", {}).get("multiplier", 0.50)
        )
        self.mult_high_breadth = float(
            rules_cfg.get("rule_high_breadth", {}).get("multiplier", 1.25)
        )
        self.mult_default = float(
            rules_cfg.get("rule_default", {}).get("multiplier", 1.00)
        )

        # --- Base policy ---
        self.base_policy = str(config.get("base_policy", "equal_weight"))

        # --- Constraints ---
        constraints_cfg = config.get("constraints", {})
        self.min_sleeves = int(constraints_cfg.get("min_sleeves", 2))
        self.sleeve_weight_cap = float(constraints_cfg.get("sleeve_weight_cap", 0.50))
        self.sleeve_weight_floor = float(
            constraints_cfg.get("sleeve_weight_floor", 0.05)
        )
        self.max_weekly_change = float(
            constraints_cfg.get("max_weekly_weight_change", 0.15)
        )

        # --- Smoothing state ---
        self._prev_weights: Optional[Dict[str, float]] = None
        self._prev_date: Optional[int] = None

        # --- Validation ---
        self._validate_and_warn()

    def _validate_and_warn(self):
        """Log warnings for suspicious config combinations."""
        if self.target_sleeve not in SLEEVE_NAMES:
            logger.warning(
                "target_sleeve='%s' not in recognised SLEEVE_NAMES=%s",
                self.target_sleeve, SLEEVE_NAMES,
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def compute_sleeve_weights(
        self,
        features: pd.DataFrame,
        available_sleeves: Optional[Dict[int, List[str]]] = None,
    ) -> pd.DataFrame:
        """Compute sleeve weights from continuous state features.

        Parameters
        ----------
        features : pd.DataFrame
            Output of ``RegimeDetector.compute_features()``.
            Must contain ``trade_date`` and columns for each feature in
            ``self.state_features``.
        available_sleeves : dict, optional
            ``{trade_date: [sleeve_name, ...]}`` of sleeves with valid
            scores on that date.

        Returns
        -------
        pd.DataFrame
            Columns: ``trade_date``, ``{sleeve_name}_weight``, plus
            diagnostic columns ``high_vol_flag`` and ``high_breadth_flag``.
            Weights sum to 1.0 per date (if enough sleeves are available).
            Returns empty DataFrame if no valid dates.
        """
        if features.empty:
            return pd.DataFrame()

        # Reset smoothing state
        self._prev_weights = None
        self._prev_date = None

        features = features.sort_values("trade_date").reset_index(drop=True)
        n_obs = len(features)

        # Compute PIT expanding thresholds
        thresholds = self._compute_pit_thresholds(features)

        rows = []
        for idx in range(n_obs):
            row = features.iloc[idx]
            trade_date = int(row["trade_date"])

            # Warmup: first min_warmup_obs observations are fully neutral
            warmup_ready = idx >= self.min_warmup_obs

            # Evaluate rule conditions (always returns False before warmup)
            flags = self._evaluate_rules(row, thresholds, trade_date, warmup_ready)

            # Build base weights
            weights = self._build_base_weights()

            # Apply rule multiplier to target sleeve (neutral when !warmup_ready)
            if flags.get("high_vol", False):
                weights[self.target_sleeve] *= self.mult_high_vol
            elif flags.get("high_breadth", False):
                weights[self.target_sleeve] *= self.mult_high_breadth

            # Get available sleeves for this date
            avail = None
            if available_sleeves is not None:
                avail = available_sleeves.get(trade_date, None)

            # Apply constraints
            weights = self._apply_constraints(weights, avail, trade_date)
            if weights is None:
                continue

            row_data = {"trade_date": trade_date}
            for s in SLEEVE_NAMES:
                row_data[f"{s}_weight"] = weights.get(s, 0.0)
            row_data["high_vol_flag"] = int(flags.get("high_vol", False))
            row_data["high_breadth_flag"] = int(flags.get("high_breadth", False))
            row_data["warmup_ready_flag"] = int(warmup_ready)
            rows.append(row_data)

            # Update smoothing state
            self._prev_weights = weights
            self._prev_date = trade_date

        if not rows:
            return pd.DataFrame()

        return pd.DataFrame(rows)

    # ------------------------------------------------------------------
    # Threshold computation
    # ------------------------------------------------------------------

    def _compute_pit_thresholds(
        self, features: pd.DataFrame,
    ) -> pd.DataFrame:
        """Compute expanding-window q75 for each state feature at each date.

        Strictly PIT-safe: q75 at date T uses only observations with
        trade_date <= T.
        """
        trade_dates = features["trade_date"].values
        result_cols: Dict[str, np.ndarray] = {
            "trade_date": trade_dates,
        }

        for feat_name in self.state_features:
            if feat_name not in features.columns:
                continue
            q75_vals = _compute_rolling_quantile(
                features[feat_name].values,
                min_warmup=self.min_warmup_obs,
                quantile=self.high_quantile,
            )
            result_cols[f"{feat_name}_q{int(self.high_quantile * 100)}"] = q75_vals

        return pd.DataFrame(result_cols)

    # ------------------------------------------------------------------
    # Rule evaluation
    # ------------------------------------------------------------------

    def _evaluate_rules(
        self,
        feature_row: pd.Series,
        thresholds: pd.DataFrame,
        trade_date: int,
        warmup_ready: bool = True,
    ) -> Dict[str, bool]:
        """Evaluate B1 rule conditions for a single date.

        Before warmup all flags are False — rules are fully neutral.
        """
        flags: Dict[str, bool] = {"high_vol": False, "high_breadth": False}

        if not warmup_ready:
            return flags

        thresh_rows = thresholds[thresholds["trade_date"] == trade_date]
        if thresh_rows.empty:
            return flags
        thresh_row = thresh_rows.iloc[0]

        vol_val = float(feature_row.get("volatility_state", 0.15))
        breadth_val = float(feature_row.get("breadth_score", 0.5))

        vol_q_col = f"volatility_state_q{int(self.high_quantile * 100)}"
        breadth_q_col = f"breadth_score_q{int(self.high_quantile * 100)}"

        vol_q75 = float(thresh_row.get(vol_q_col, np.nan))
        breadth_q75 = float(thresh_row.get(breadth_q_col, np.nan))

        # NaN quantile = insufficient data → stay neutral
        if not np.isnan(vol_q75):
            flags["high_vol"] = vol_val >= vol_q75

        if not np.isnan(breadth_q75) and not np.isnan(vol_q75):
            flags["high_breadth"] = (
                breadth_val >= breadth_q75 and vol_val < vol_q75
            )

        return flags

    # ------------------------------------------------------------------
    # Weight construction
    # ------------------------------------------------------------------

    def _build_base_weights(self) -> Dict[str, float]:
        """Build base sleeve weights before rule adjustment."""
        if self.base_policy == "equal_weight":
            n = max(len([s for s in SLEEVE_NAMES]), 1)
            return {s: 1.0 / n for s in SLEEVE_NAMES}
        # Fallback: equal weight
        n = max(len([s for s in SLEEVE_NAMES]), 1)
        return {s: 1.0 / n for s in SLEEVE_NAMES}

    # ------------------------------------------------------------------
    # Constraints (mirrors RegimeAllocator._apply_constraints)
    # ------------------------------------------------------------------

    def _apply_constraints(
        self,
        weights: Dict[str, float],
        available: Optional[List[str]],
        trade_date: int,
    ) -> Optional[Dict[str, float]]:
        """Apply all constraints to raw weights for one date.

        Returns None if insufficient sleeves are available.
        Availability is a hard constraint — unavailable sleeves are
        zeroed both before AND after smoothing.
        """
        # 1. Zero out unavailable sleeves (first pass)
        if available is not None:
            for s in SLEEVE_NAMES:
                if s not in available:
                    weights[s] = 0.0

        # 2. Check min_sleeves
        active = [s for s in SLEEVE_NAMES if weights.get(s, 0.0) > 1e-8]
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

        # 4. Floor: weights below floor → 0, redistributed
        weights = self._apply_floor(weights)

        # 5. Cap: weights above cap → clipped, excess redistributed
        weights = self._apply_cap(weights)

        # 6. Smoothing vs previous weights
        if self._prev_weights is not None:
            weights = self._apply_smoothing(weights)

        # 7. Re-apply unavailable hard mask after smoothing
        #    Availability priority > smoothing
        if available is not None:
            for s in SLEEVE_NAMES:
                if s not in available:
                    weights[s] = 0.0

        # 8. Re-check and renormalize
        active = [s for s in SLEEVE_NAMES if weights.get(s, 0.0) > 1e-8]
        if len(active) < self.min_sleeves:
            return None

        total = sum(weights.values())
        if total > 1e-8:
            weights = {k: v / total for k, v in weights.items()}

        return weights

    def _apply_floor(self, weights: Dict[str, float]) -> Dict[str, float]:
        """Set weights below floor to 0, redistribute to others."""
        floor = self.sleeve_weight_floor
        below = [k for k, v in weights.items() if 0 < v < floor]
        above = [k for k, v in weights.items() if v >= floor]

        if not below:
            return weights

        if len(above) < self.min_sleeves:
            return weights

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
        """Iteratively cap weights above ceiling, redistribute excess."""
        cap = self.sleeve_weight_cap
        active = {k: v for k, v in weights.items() if v > 1e-8}

        if not active:
            return weights

        for _i in range(20):
            capped = {k: v for k, v in active.items() if v > cap}
            if not capped:
                break

            excess = sum(v - cap for v in capped.values())
            uncapped = {k: v for k, v in active.items() if v <= cap and v > 0}

            for k in capped:
                active[k] = cap

            if not uncapped:
                n = len(active)
                for k in active:
                    active[k] = 1.0 / n
                break

            uncapped_total = sum(uncapped.values())
            for k in uncapped:
                if uncapped_total > 1e-8:
                    active[k] += excess * (uncapped[k] / uncapped_total)

        return active

    def _apply_smoothing(self, weights: Dict[str, float]) -> Dict[str, float]:
        """Smooth weights vs previous period using max_weekly_change."""
        prev = self._prev_weights
        if prev is None:
            return weights

        max_delta = self.max_weekly_change
        smoothed = dict(weights)

        for _i in range(5):
            clamped: Dict[str, float] = {}
            for s in SLEEVE_NAMES:
                pw = prev.get(s, 0.0)
                cw = smoothed.get(s, 0.0)
                lower = max(0.0, pw - max_delta)
                upper = min(1.0, pw + max_delta)
                clamped[s] = float(np.clip(cw, lower, upper))

            total = sum(clamped.values())
            if total > 1e-8:
                clamped = {k: v / total for k, v in clamped.items()}

            max_violation = 0.0
            for s in SLEEVE_NAMES:
                pw = prev.get(s, 0.0)
                cw = clamped.get(s, 0.0)
                violation = abs(cw - pw) - max_delta
                if violation > 1e-8:
                    max_violation = max(max_violation, violation)

            smoothed = clamped
            if max_violation < 1e-6:
                break

        return smoothed


# ---------------------------------------------------------------------------
# PIT-safe rolling quantile (reused from market state rule validation)
# ---------------------------------------------------------------------------

def _compute_rolling_quantile(
    values: np.ndarray,
    min_warmup: int = 52,
    quantile: float = 0.75,
) -> np.ndarray:
    """Compute expanding-window quantile for each position, strictly PIT-safe.

    At position i, the quantile is computed from all observations in
    ``values[0:i+1]``.  Positions with fewer than ``min_warmup``
    observations return NaN — the caller must treat these as insufficient
    data (no forward-fill).

    Parameters
    ----------
    values : np.ndarray
        1-D array of feature values in chronological order.
    min_warmup : int
        Minimum observations before quantile is computed.
    quantile : float
        Quantile to compute (0.0–1.0).

    Returns
    -------
    np.ndarray
        Same length as *values*.  NaN before warmup; quantile afterwards.
    """
    n = len(values)
    result = np.full(n, np.nan, dtype=float)
    if n == 0:
        return result

    for i in range(n):
        window = values[:i + 1]
        if len(window) >= max(min_warmup, 2):
            result[i] = float(np.percentile(window, quantile * 100))

    return result

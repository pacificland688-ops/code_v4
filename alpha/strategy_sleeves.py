"""
Multi-sleeve strategy engine.

Each "sleeve" is a named sub-strategy with its own factor list.
Internally, each sleeve uses ICWeighting to compute a composite score
from its factor pool.  The engine orchestrates all sleeves and returns
their scores as a dictionary.

This reuses ICWeighting **unchanged** — the only difference is that
``factor_whitelist`` restricts each sleeve to its own factor subset
and ``min_active_factors`` is lower (2 instead of 4) since each
sleeve has fewer factors.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from alpha.ic_weighting import ICWeighting

logger = logging.getLogger(__name__)

# Canonical sleeve names
SLEEVE_NAMES = ["reversal", "momentum", "defensive", "value", "volume_price", "shock_reversal", "growth"]


class StrategySleeveEngine:
    """Run ICWeighting inside each strategy sleeve.

    Parameters
    ----------
    sleeve_config : dict
        Mapping ``{sleeve_name: {factors: [...]}}`` from regime.yaml.
    composite_params : dict
        Parameters forwarded to ``ICWeighting.__init__`` for each sleeve.
    """

    def __init__(self, sleeve_config: dict, composite_params: dict):
        # Normalize sleeve_config to a standard format
        self.sleeves: Dict[str, List[str]] = {}
        for name, cfg in sleeve_config.items():
            if isinstance(cfg, dict):
                factors = cfg.get("factors", [])
            elif isinstance(cfg, list):
                factors = cfg
            else:
                logger.warning("Skipping sleeve '%s': invalid config type %s", name, type(cfg))
                continue
            if factors:
                self.sleeves[name] = list(factors)

        if not self.sleeves:
            logger.warning("No valid sleeves configured")

        # Build composite params
        self.composite_params = dict(composite_params)

        # --- Config validation ---
        self._validate_and_warn()

        logger.info(
            "StrategySleeveEngine initialized with %d sleeves: %s",
            len(self.sleeves), list(self.sleeves.keys()),
        )

    def _validate_and_warn(self):
        """Validate sleeve config against composite params for conflicts."""
        hard_cap = self.composite_params.get("hard_cap", False)
        weight_cap = self.composite_params.get("weight_cap", 0.50)
        min_active = self.composite_params.get("min_active_factors", 1)
        min_icir = self.composite_params.get("min_icir", 0.0)
        coverage_gate = self.composite_params.get("coverage_gate_enabled", False)

        # Check: hard_cap + weight_cap feasibility
        if hard_cap:
            min_required = int(np.ceil(1.0 / weight_cap)) if weight_cap > 0 else 999
            logger.info(
                "hard_cap=true, weight_cap=%.2f → requires at least %d active factors "
                "per sleeve for feasible weights", weight_cap, min_required,
            )

        for name, factors in self.sleeves.items():
            n_factors = len(factors)
            issues = []

            # Check: min_active_factors <= sleeve factor count
            if min_active > n_factors:
                issues.append(
                    f"min_active_factors={min_active} > factor_count={n_factors} "
                    f"— sleeve will NEVER produce scores"
                )

            # Check: hard_cap feasibility
            if hard_cap and weight_cap > 0:
                min_for_cap = int(np.ceil(1.0 / weight_cap))
                if min_for_cap > n_factors:
                    issues.append(
                        f"hard_cap=true + weight_cap={weight_cap} requires "
                        f">={min_for_cap} active factors, but sleeve has only {n_factors}"
                    )

            # Check: ICIR gate + few factors
            if min_icir > 0 and n_factors <= 2:
                issues.append(
                    f"min_icir={min_icir} + only {n_factors} factors — "
                    f"high risk of empty sleeve if any factor fails ICIR gate"
                )

            # Check: coverage gate + few factors
            if coverage_gate and n_factors <= 2:
                issues.append(
                    f"coverage_gate_enabled=true + only {n_factors} factors — "
                    f"high risk of empty sleeve if coverage gate rejects any factor"
                )

            if issues:
                logger.warning(
                    "Sleeve '%s' (%d factors) config issues: %s",
                    name, n_factors, "; ".join(issues),
                )
            else:
                logger.info(
                    "Sleeve '%s': %d factors, min_active=%d — OK",
                    name, n_factors, min_active,
                )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def compute_sleeve_scores(
        self,
        factor_dfs: Dict[str, pd.DataFrame],
        fwd_returns: pd.DataFrame,
        signal_dates: List[int],
    ) -> Dict[str, pd.DataFrame]:
        """Compute composite score for each sleeve.

        Parameters
        ----------
        factor_dfs : dict
            Mapping ``{factor_name: DataFrame}`` with all available factor panels.
            Each DataFrame must have columns ``[ts_code, trade_date, <value>]``.
        fwd_returns : pd.DataFrame
            Forward returns panel with columns ``[ts_code, trade_date, fwd_ret_*d]``.
        signal_dates : list of int
            Signal dates YYYYMMDD for which to compute scores.

        Returns
        -------
        dict[str, pd.DataFrame]
            Mapping ``{sleeve_name: composite_score_df}``.
            Each DataFrame has columns ``[ts_code, trade_date, composite_score]``.
            Empty DataFrames indicate the sleeve produced no valid scores.
        """
        results: Dict[str, pd.DataFrame] = {}

        for sleeve_name, factor_names in self.sleeves.items():
            logger.info("Computing sleeve '%s' with factors: %s", sleeve_name, factor_names)

            # Filter factor_dfs to this sleeve's factors
            sleeve_factor_dfs = {}
            for fname in factor_names:
                if fname in factor_dfs:
                    sleeve_factor_dfs[fname] = factor_dfs[fname]
                else:
                    logger.debug(
                        "Sleeve '%s': factor '%s' not in factor_dfs — skipping",
                        sleeve_name, fname,
                    )

            if not sleeve_factor_dfs:
                logger.warning(
                    "Sleeve '%s': no factors available — returning empty", sleeve_name
                )
                results[sleeve_name] = pd.DataFrame()
                continue

            # Create ICWeighting instance for this sleeve
            try:
                icw = ICWeighting(
                    **self.composite_params,
                    factor_whitelist=list(sleeve_factor_dfs.keys()),
                )
                composite = icw.compute_composite_series(
                    sleeve_factor_dfs, fwd_returns, signal_dates
                )
            except Exception as exc:
                logger.error(
                    "Sleeve '%s': ICWeighting failed: %s — returning empty",
                    sleeve_name, exc,
                )
                results[sleeve_name] = pd.DataFrame()
                continue

            if composite.empty:
                logger.info(
                    "Sleeve '%s': no valid composite scores (insufficient factors/data)",
                    sleeve_name,
                )
            else:
                logger.info(
                    "Sleeve '%s': %d composite score rows across %d dates",
                    sleeve_name, len(composite), composite["trade_date"].nunique(),
                )

            results[sleeve_name] = composite

        return results

    def get_available_sleeves_by_date(
        self, sleeve_scores: Dict[str, pd.DataFrame]
    ) -> Dict[int, List[str]]:
        """Build a per-date availability map from sleeve scores.

        Parameters
        ----------
        sleeve_scores : dict
            Output of ``compute_sleeve_scores()``.

        Returns
        -------
        dict
            ``{trade_date: [sleeve_name, ...]}`` for sleeves that have
            non-empty scores on that date.
        """
        date_to_sleeves: Dict[int, List[str]] = {}

        for sleeve_name, df in sleeve_scores.items():
            if df is None or df.empty:
                continue
            for d in df["trade_date"].unique():
                d_int = int(d)
                if d_int not in date_to_sleeves:
                    date_to_sleeves[d_int] = []
                date_to_sleeves[d_int].append(sleeve_name)

        return date_to_sleeves

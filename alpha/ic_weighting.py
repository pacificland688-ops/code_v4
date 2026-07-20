"""
IC-weighted multi-factor composite score.

Implements the rolling IC weighting scheme:
1. For each factor, compute rolling IC over lookback window
2. Shrink IC estimates toward zero (Bayesian shrinkage)
3. Weight = shrunk_IC / IC_volatility
4. Apply weight cap, sign stability check, minimum obs
5. Composite score = Σ(weight_i × zscore(factor_i))

This produces a composite_score, NOT expected return μ.
Score-to-μ calibration happens separately in score_to_mu.py.

v3 additions (2026-06-07):
- min_icir gate (default 0.0 = disabled)
- IC horizon lag (prevents forward-looking bias in weight computation)
- eligible_factor_names (normalize only for factors that pass coverage gate)
- hard_cap with iterative redistribution
- min_active_factors safety valve
- coverage_gate_enabled (integration with factor_gating.py)
- ic_method respect (Spearman / Pearson)

Memory: IC history is a small (factor × date) matrix. Weight computation
is vectorized. Composite score computed per date batch.
"""

import logging
from typing import Optional, List, Dict, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class ICWeighting:
    """IC-weighted multi-factor composite score.

    Uses rolling window of past IC to determine factor weights.
    All new capability gates default to ``off`` so that existing
    callers see zero behaviour change.
    """

    def __init__(self,
                 ic_window_months: int = 12,
                 shrinkage: float = 0.3,
                 weight_cap: float = 0.3,
                 min_ic_obs: int = 20,
                 min_icir: float = 0.0,
                 hard_cap: bool = False,
                 horizon: int = 5,
                 min_active_factors: int = 1,
                 coverage_gate_enabled: bool = False,
                 sign_stability_check: bool = True,
                 ic_method: str = "rank",
                 factor_whitelist: Optional[List[str]] = None,
                 factor_blacklist: Optional[List[str]] = None,
                 # Extra YAML keys forwarded by factor_config are accepted
                 # via **kwargs and silently ignored.
                 **kwargs):
        self.ic_window_months = ic_window_months
        self.shrinkage = shrinkage
        self.weight_cap = weight_cap
        self.min_ic_obs = min_ic_obs
        self.min_icir = min_icir
        self.hard_cap = hard_cap
        self.horizon = horizon
        self.min_active_factors = min_active_factors
        self.coverage_gate_enabled = coverage_gate_enabled
        self.sign_stability_check = sign_stability_check
        self.ic_method = ic_method
        self.factor_whitelist = factor_whitelist or []
        self.factor_blacklist = factor_blacklist or []

        # Extra YAML keys (min_date_coverage, min_stocks_per_date, etc.)
        # forwarded by factor_config for coverage gate use.
        self._extra = kwargs

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _min_factors_for_cap(self) -> int:
        """Minimum active factors required for the hard cap to be feasible.

        Constraint: n_active * weight_cap >= 1.0

        If hard_cap is enabled with weight_cap=0.25, at least 4 factors
        must be active, otherwise the cap cannot be satisfied.
        """
        import math
        if not self.hard_cap or self.weight_cap <= 0:
            return self.min_active_factors
        return max(self.min_active_factors, math.ceil(1.0 / self.weight_cap))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _filter_factors(self, factor_dfs: Dict[str, pd.DataFrame]
                        ) -> Dict[str, pd.DataFrame]:
        """Filter factors based on whitelist/blacklist."""
        filtered = {}
        for name, df in factor_dfs.items():
            if self.factor_blacklist and name in self.factor_blacklist:
                logger.debug("Factor %s excluded by blacklist", name)
                continue
            if self.factor_whitelist and name not in self.factor_whitelist:
                logger.debug("Factor %s excluded (not in whitelist)", name)
                continue
            filtered[name] = df
        return filtered

    # ------------------------------------------------------------------
    # Rolling IC estimation
    # ------------------------------------------------------------------
    def compute_rolling_ic(self, factor_dfs: Dict[str, pd.DataFrame],
                           forward_returns_df: pd.DataFrame,
                           horizon: int = 5,
                           min_stocks: int = 30) -> pd.DataFrame:
        """Compute rolling IC for multiple factors.

        For each date, computes cross-sectional IC of each factor
        against forward return at the given horizon.

        Returns
        -------
        pd.DataFrame with columns: trade_date, {factor_name}_ic
        """
        ret_col = f"fwd_ret_{horizon}d"
        dates = sorted(forward_returns_df["trade_date"].unique())

        # Determine IC function based on ic_method
        if self.ic_method == "pearson":
            logger.warning(
                "ic_method='pearson' not yet implemented; falling back to 'rank' (Spearman)"
            )
        # Always use Spearman rank IC for now (industry standard)
        from scipy.stats import spearmanr

        ic_records = []
        for date in dates:
            fwd = forward_returns_df[forward_returns_df["trade_date"] == date]
            if len(fwd) < min_stocks:
                continue

            fwd_lookup = fwd.set_index("ts_code")[ret_col]

            record = {"trade_date": date}
            for name, df in factor_dfs.items():
                if df.empty:
                    record[f"{name}_ic"] = np.nan
                    continue

                factor_cols = [c for c in df.columns
                               if c not in ("ts_code", "trade_date")]
                if not factor_cols:
                    record[f"{name}_ic"] = np.nan
                    continue

                factor_col = factor_cols[0]
                day_factor = df[df["trade_date"] == date]
                if len(day_factor) < min_stocks:
                    record[f"{name}_ic"] = np.nan
                    continue

                merged = day_factor.set_index("ts_code")[factor_col].to_frame()
                merged["fwd_ret"] = fwd_lookup
                merged = merged.dropna()

                if len(merged) < min_stocks:
                    record[f"{name}_ic"] = np.nan
                    continue

                ic, _ = spearmanr(merged[factor_col], merged["fwd_ret"])
                record[f"{name}_ic"] = np.float32(ic)

            ic_records.append(record)

        return pd.DataFrame(ic_records)

    # ------------------------------------------------------------------
    # Weight computation
    # ------------------------------------------------------------------
    def compute_weights(self,
                        ic_df: pd.DataFrame,
                        signal_date: int,
                        eligible_factor_names: Optional[List[str]] = None,
                        trade_dates: Optional[List[int]] = None,
                        ) -> Dict[str, float]:
        """Compute factor weights for a single signal date.

        Uses rolling IC data whose forward-return horizon has **fully
        elapsed** before the signal_date — no forward-looking bias.

        The cutoff is computed from the real trading calendar via
        ``matured_ic_cutoff()``, NOT from YYYYMMDD integer subtraction.

        Parameters
        ----------
        ic_df : pd.DataFrame
            IC time series from ``compute_rolling_ic()``.
        signal_date : int
            Signal date YYYYMMDD.
        eligible_factor_names : list[str], optional
            If provided, ONLY these factors participate in weight
            computation and normalisation.  Factors filtered out by
            the coverage gate are excluded from the denominator.
        trade_dates : list[int], optional
            Sorted trading dates for horizon cutoff computation.

        Returns
        -------
        dict[factor_name] -> weight
        """
        ic_cols = [c for c in ic_df.columns if c.endswith("_ic")]
        if not ic_cols:
            return {}

        # ---- horizon lag: use real trading calendar, NOT integer math ----
        if not trade_dates:
            logger.warning(
                "trade_dates required for horizon-safe IC weighting "
                "(signal=%d) — returning empty", signal_date,
            )
            return {}

        from alpha.time_utils import matured_ic_cutoff, calendar_month_lookback_start

        ic_cutoff = matured_ic_cutoff(signal_date, self.horizon, trade_dates)
        if ic_cutoff is None:
            logger.debug("No matured IC cutoff for %d (horizon=%d)",
                         signal_date, self.horizon)
            return {}

        lookback_start = calendar_month_lookback_start(
            signal_date, self.ic_window_months
        )
        ic_window = ic_df[
            (ic_df["trade_date"] <= ic_cutoff) &
            (ic_df["trade_date"] >= lookback_start)
        ]

        if len(ic_window) < self.min_ic_obs:
            logger.debug(
                "Insufficient IC data for %d: %d < %d",
                signal_date, len(ic_window), self.min_ic_obs,
            )
            return {}

        # ---- restrict to eligible factors (coverage gate survivors) ----
        factor_names = [c.replace("_ic", "") for c in ic_cols]
        if eligible_factor_names is not None:
            eligible_set = set(eligible_factor_names)
            factor_names = [n for n in factor_names if n in eligible_set]
            if not factor_names:
                return {}

        weights = {}
        for factor_name in factor_names:
            ic_col = f"{factor_name}_ic"
            if ic_col not in ic_window.columns:
                continue

            ic_series = ic_window[ic_col].dropna()
            if len(ic_series) < self.min_ic_obs:
                continue

            mean_ic = ic_series.mean()
            std_ic = ic_series.std(ddof=0)
            if std_ic == 0 or np.isnan(std_ic):
                continue

            # ---- ICIR gate (only when enabled) ----
            if self.min_icir > 0:
                icir = abs(mean_ic / std_ic)
                if icir < self.min_icir:
                    continue

            # Shrinkage toward zero
            shrunk_ic = mean_ic * (1.0 - self.shrinkage)

            # Sign stability check
            if self.sign_stability_check and len(ic_series) >= 10:
                n_recent = max(5, len(ic_series) // 4)
                recent_ic = ic_series.iloc[-n_recent:]
                if np.sign(mean_ic) != np.sign(recent_ic.mean()):
                    shrunk_ic *= 0.5

            raw_weight = shrunk_ic / std_ic
            weight = np.clip(raw_weight, -self.weight_cap, self.weight_cap)
            weights[factor_name] = float(weight)

        # Normalize to sum(|w|) = 1
        if weights:
            weight_sum = sum(abs(w) for w in weights.values())
            if weight_sum > 0:
                weights = {k: v / weight_sum for k, v in weights.items()}

            # Hard cap feasibility check: n_active * cap >= 1.0
            required = self._min_factors_for_cap()
            if len(weights) < required:
                logger.warning(
                    "signal=%d: %d factors with weight < required=%d "
                    "(cap=%.2f) — returning empty weights",
                    signal_date, len(weights), required, self.weight_cap,
                )
                return {}

            # Hard cap (only when explicitly enabled)
            if self.hard_cap and 0 < self.weight_cap < 1.0:
                weights = self._apply_hard_cap(weights)
                if not weights:
                    return {}

        return weights

    # ------------------------------------------------------------------
    # Hard cap (post-normalization iterative cap + redistribute)
    # ------------------------------------------------------------------
    def _apply_hard_cap(self, weights: Dict[str, float]) -> Dict[str, float]:
        """Apply hard weight cap AFTER normalization.

        Algorithm (stable, non-oscillating)
        ------------------------------------
        1. Start with normalized weights (sum |w| = 1).
        2. Identify capped group: |w| > cap → set to cap.
        3. Distribute excess ONLY to uncapped weights, proportionally.
        4. If any uncapped weight now exceeds cap, add it to the capped
           group and repeat from step 2.
        5. If ALL weights are capped (no uncapped remaining), distribute
           excess equally among all weights.

        Converges in at most ``len(weights)`` iterations.
        """
        if not weights or self.weight_cap <= 0:
            return weights

        cap = self.weight_cap
        working = {k: abs(v) for k, v in weights.items()}

        # Normalize to 1
        total = sum(working.values())
        if total == 0:
            return {k: 0.0 for k in weights}
        working = {k: v / total for k, v in working.items()}

        capped: set = set()

        for _ in range(len(working) + 2):  # safety bound
            # Identify newly-capped weights
            for k, w in working.items():
                if k not in capped and w > cap:
                    capped.add(k)

            # Separate into capped (fixed at cap) and uncapped
            excess = sum(working[k] - cap for k in capped)
            uncapped = {k: working[k] for k in working if k not in capped}

            if excess < 1e-8:
                break

            uncapped_total = sum(uncapped.values())
            if uncapped_total < 1e-8:
                # ALL weights are capped → distribute equally
                n = len(working)
                for k in working:
                    working[k] = 1.0 / n
                break

            # Fix capped weights at cap
            for k in capped:
                working[k] = cap

            # Redistribute excess to uncapped proportionally
            for k, w in uncapped.items():
                working[k] = w + excess * (w / uncapped_total)

        # Restore signs
        return {k: (working[k] if v >= 0 else -working[k])
                for (k, v) in weights.items()}

    # ------------------------------------------------------------------
    # Composite score (single date)
    # ------------------------------------------------------------------
    def compute_composite_score(self,
                                factor_dfs: Dict[str, pd.DataFrame],
                                ic_df: pd.DataFrame,
                                signal_date: int,
                                fwd_returns_df: "pd.DataFrame | None" = None,
                                trade_dates: "list[int] | None" = None,
                                expected_dates: "list[int] | None" = None,
                                ) -> pd.DataFrame:
        """Compute IC-weighted composite score for a single date.

        Parameters
        ----------
        factor_dfs : dict[factor_name] -> pd.DataFrame
            Processed factor values (cross-sectionally standardized).
        ic_df : pd.DataFrame
            IC time series.
        signal_date : int
            Date for which to compute composite score.
        fwd_returns_df : pd.DataFrame, optional
            Required when ``coverage_gate_enabled=True``.
        trade_dates : list[int], optional
            Sorted trading dates for horizon cutoff (no leakage).
        expected_dates : list[int], optional
            Expected signal dates for coverage gate denominator.
            Passed through to ``evaluate_factor_coverage_at_date``
            so that weekly-aligned factors aren't penalised by a
            daily-frequency denominator.

        Returns
        -------
        pd.DataFrame with ts_code, trade_date, composite_score.
        Empty DataFrame if ``min_active_factors`` is not met or
        hard cap is infeasible.
        """
        # ---- coverage gate (per-date, historical window only) ----
        eligible_names = None
        if self.coverage_gate_enabled:
            from alpha.factor_gating import evaluate_factor_coverage_at_date

            lookback_months = self._extra.get(
                "min_date_coverage_lookback", self.ic_window_months
            )
            eligible = {}
            for name, df in factor_dfs.items():
                if evaluate_factor_coverage_at_date(
                    factor_df=df,
                    fwd_returns_df=fwd_returns_df,
                    signal_date=signal_date,
                    lookback_months=lookback_months,
                    horizon=self.horizon,
                    trade_dates=trade_dates,
                    min_date_coverage=self._extra.get("min_date_coverage", 0.70),
                    min_stocks_per_date=self._extra.get("min_stocks_per_date", 30),
                    min_merge_rate=self._extra.get("min_merge_rate", 0.30),
                    expected_dates=expected_dates,
                ):
                    eligible[name] = df

            if len(eligible) < len(factor_dfs):
                dropped = set(factor_dfs) - set(eligible)
                logger.debug(
                    "Coverage gate signal=%d: dropped %s",
                    signal_date, sorted(dropped),
                )
            factor_dfs = eligible
            eligible_names = list(eligible.keys())

        # ---- min_active_factors + hard cap feasibility ----
        required = self._min_factors_for_cap()
        active_count = len(factor_dfs) if eligible_names is None else len(eligible_names)
        if active_count < required:
            logger.warning(
                "signal=%d: only %d factor(s) passed gates (required=%d, "
                "min_active=%d, cap=%.2f) — returning empty composite",
                signal_date, active_count, required,
                self.min_active_factors, self.weight_cap,
            )
            return pd.DataFrame()

        # ---- compute weights (only for eligible factors) ----
        weights = self.compute_weights(
            ic_df, signal_date,
            eligible_factor_names=eligible_names,
            trade_dates=trade_dates,
        )

        if not weights:
            return pd.DataFrame()

        # ---- build weighted composite ----
        weighted_series = []
        for factor_name, weight in weights.items():
            df = factor_dfs.get(factor_name)
            if df is None or df.empty:
                continue

            cols = [c for c in df.columns if c not in ("ts_code", "trade_date")]
            if not cols:
                continue
            factor_col = cols[0]

            day_vals = df[df["trade_date"] == signal_date][
                ["ts_code", factor_col]
            ].copy()
            if day_vals.empty:
                continue

            day_vals = day_vals.set_index("ts_code")
            s = day_vals[factor_col] * weight
            s.name = factor_name
            weighted_series.append(s)

        if not weighted_series:
            return pd.DataFrame()

        composite = pd.concat(weighted_series, axis=1)
        composite["composite_score"] = composite.sum(axis=1, skipna=True)

        result = composite[["composite_score"]].reset_index()
        result["trade_date"] = signal_date

        # Cross-sectional z-score the composite
        valid = result["composite_score"].dropna()
        if len(valid) > 10:
            mean = valid.mean()
            std = valid.std(ddof=0)
            if std > 0:
                result["composite_score"] = (
                    (result["composite_score"] - mean) / std
                ).astype("float32")

        # ---- per-date factor weight log (auditability) ----
        if weights:
            w_str = ", ".join(
                f"{k}={v:+.3f}" for k, v in
                sorted(weights.items(), key=lambda x: -abs(x[1]))
            )
            logger.info("signal=%d weights: %s", signal_date, w_str)

        return result[["ts_code", "trade_date", "composite_score"]]

    # ------------------------------------------------------------------
    # Batch composite score computation
    # ------------------------------------------------------------------
    def compute_composite_series(self,
                                 factor_dfs: Dict[str, pd.DataFrame],
                                 forward_returns_df: pd.DataFrame,
                                 signal_dates: List[int],
                                 horizon: "int | None" = None,
                                 ) -> pd.DataFrame:
        """Compute composite scores for a series of signal dates.

        Parameters
        ----------
        factor_dfs : dict
            Processed factor DataFrames.
        forward_returns_df : pd.DataFrame
            Forward returns for IC computation.
        signal_dates : list of int
            Signal dates.
        horizon : int, optional
            Forward horizon for IC computation.  Defaults to
            ``self.horizon`` (from YAML).

        Returns
        -------
        pd.DataFrame with composite_score for all dates.
        """
        if horizon is None:
            horizon = self.horizon

        # Step 0: Filter factors by whitelist/blacklist
        factor_dfs = self._filter_factors(factor_dfs)
        if not factor_dfs:
            logger.error("No factors remain after whitelist/blacklist filtering")
            return pd.DataFrame()
        logger.info("Using %d factors after filtering", len(factor_dfs))

        # Build the sorted trading-date list ONCE for horizon-lag
        # computation.  This is the real calendar — no integer math.
        trade_dates: List[int] = sorted(
            int(d) for d in forward_returns_df["trade_date"].dropna().unique()
        )

        # Step 1: Compute rolling IC
        logger.info("Computing rolling IC for composite weighting...")
        ic_df = self.compute_rolling_ic(
            factor_dfs, forward_returns_df, horizon=horizon
        )

        if ic_df.empty:
            logger.error("No IC data computed — cannot create composite")
            return pd.DataFrame()

        # Step 2: For each signal date, compute weights and composite score
        logger.info("Computing composite scores for %d dates...", len(signal_dates))
        all_scores = []
        skipped_dates = 0
        sorted_signal_dates = sorted(int(d) for d in signal_dates)

        for i, date in enumerate(sorted_signal_dates):
            score_df = self.compute_composite_score(
                factor_dfs, ic_df, date,
                fwd_returns_df=forward_returns_df,
                trade_dates=trade_dates,
                expected_dates=sorted_signal_dates,
            )
            if not score_df.empty:
                all_scores.append(score_df)
            else:
                skipped_dates += 1

            if (i + 1) % 200 == 0:
                logger.debug("Composite score: %d/%d", i + 1, len(signal_dates))

        if skipped_dates > 0:
            logger.info(
                "%d/%d signal dates skipped (min_active_factors or "
                "coverage gate)",
                skipped_dates, len(signal_dates),
            )

        if not all_scores:
            return pd.DataFrame()

        result = pd.concat(all_scores, ignore_index=True)
        logger.info(
            "Composite score: %d rows across %d dates",
            len(result), result["trade_date"].nunique(),
        )
        return result

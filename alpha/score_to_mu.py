"""
Score-to-expected-return calibration.

CRITICAL: composite_score is NOT expected return μ.
Must calibrate before feeding into mean-variance optimizer.

Three methods:
1. rolling_IC: μ_i = score_i × rolling_IC × cross_section_return_vol
2. historical_regression: forward_return ~ score, take predicted value
3. rank_only: skip calibration, use score only for sorting (not MV)

v5 (2026-06-07): All methods now use ``matured_ic_cutoff()`` so that
only forward returns whose horizon has fully elapsed before the signal
date contribute to IC/vol history.  Changing t-1's unmatured fwd_ret
no longer changes t's μ.

Memory: calibration is per-date with O(200) stocks — negligible.
"""

import logging
from typing import Optional, Dict, List

import numpy as np
import pandas as pd
from scipy import stats

logger = logging.getLogger(__name__)


class ScoreToMu:
    """Calibrate composite_score to expected return μ.

    The output μ vector is in the same units as forward returns
    (e.g., weekly returns for weekly rebalance).
    """

    def __init__(self,
                 method: str = "rolling_ic",
                 rolling_ic_window: int = 60,
                 vol_window: int = 60,
                 regression_window: int = 252,
                 regression_min_obs: int = 60):
        self.method = method
        self.rolling_ic_window = rolling_ic_window
        self.vol_window = vol_window
        self.regression_window = regression_window
        self.regression_min_obs = regression_min_obs

    # ------------------------------------------------------------------
    # Main calibration
    # ------------------------------------------------------------------
    def calibrate(self, scores: pd.DataFrame,
                  score_col: str = "composite_score",
                  forward_returns_df: Optional[pd.DataFrame] = None,
                  horizon: int = 5,
                  trade_dates: Optional[List[int]] = None,
                  ) -> pd.DataFrame:
        """Calibrate scores to expected returns.

        Parameters
        ----------
        scores : pd.DataFrame
            Scores with ts_code, trade_date, score_col.
        score_col : str
            Score column name.
        forward_returns_df : pd.DataFrame, optional
            Forward returns for IC estimation. Required for methods 1 and 2.
        horizon : int
            Forward return horizon for calibration.
        trade_dates : list[int], optional
            Sorted trading dates for horizon-safe cutoff.  If not
            provided, built from ``forward_returns_df["trade_date"]``.

        Returns
        -------
        pd.DataFrame with ts_code, trade_date, mu column.
        """
        # Build trade_dates if not provided
        if trade_dates is None and forward_returns_df is not None:
            trade_dates = sorted(
                int(d)
                for d in forward_returns_df["trade_date"].dropna().unique()
            )

        if self.method == "rank_only":
            return self._rank_only(scores, score_col)

        elif self.method == "rolling_ic":
            if forward_returns_df is None:
                raise ValueError(
                    "forward_returns_df required for rolling_ic method"
                )
            return self._calibrate_rolling_ic(
                scores, score_col, forward_returns_df, horizon, trade_dates,
            )

        elif self.method == "historical_regression":
            if forward_returns_df is None:
                raise ValueError(
                    "forward_returns_df required for regression method"
                )
            return self._calibrate_regression(
                scores, score_col, forward_returns_df, horizon, trade_dates,
            )

        else:
            raise ValueError(f"Unknown calibration method: {self.method}")

    # ------------------------------------------------------------------
    # Method 1: Rolling IC calibration (horizon-safe)
    # ------------------------------------------------------------------
    def _calibrate_rolling_ic(self, scores: pd.DataFrame,
                               score_col: str,
                               forward_returns_df: pd.DataFrame,
                               horizon: int,
                               trade_dates: Optional[List[int]] = None,
                               ) -> pd.DataFrame:
        """μ_i = score_i × rolling_IC × cross_section_return_vol

        IC and cs_vol history are filtered by ``matured_ic_cutoff()``
        so that ONLY forward returns whose horizon has fully elapsed
        contribute to the rolling estimates.
        """
        from alpha.time_utils import matured_ic_cutoff

        ret_col = f"fwd_ret_{horizon}d"
        dates = sorted(scores["trade_date"].unique())

        if trade_dates is None:
            trade_dates = sorted(
                int(d)
                for d in forward_returns_df["trade_date"].dropna().unique()
            )

        results: list = []
        # history: list of (trade_date_int, ic, cs_vol)
        history: list = []

        for date in dates:
            day_scores = scores[
                scores["trade_date"] == date
            ].dropna(subset=[score_col])
            if len(day_scores) < 30:
                continue

            # ---- matured cutoff: only use ICs whose fwd_ret has matured ----
            cutoff = matured_ic_cutoff(date, horizon, trade_dates)

            # ---- Step 1: compute rolling estimates from MATURE history only ----
            if cutoff is not None:
                mature_history = [
                    (d, ic, vol) for d, ic, vol in history
                    if d <= cutoff
                ]
            else:
                mature_history = []

            if len(mature_history) < 5:
                rolling_ic = 0.0
                rolling_cs_vol = 0.0
            else:
                recent_ic = [
                    ic for _, ic, _ in mature_history[-self.rolling_ic_window:]
                ]
                rolling_ic = float(np.mean(recent_ic))
                if not np.isfinite(rolling_ic):
                    rolling_ic = 0.0

                recent_vols = [
                    v for _, _, v in mature_history[-self.vol_window:]
                ]
                rolling_cs_vol = float(np.mean(recent_vols))
                if not np.isfinite(rolling_cs_vol):
                    rolling_cs_vol = 0.0

            # ---- Step 2: calibrate μ from PAST estimates ----
            mu = day_scores.copy()
            mu["mu"] = (
                mu[score_col].astype("float32")
                * np.float32(rolling_ic)
                * np.float32(rolling_cs_vol)
            )
            results.append(mu[["ts_code", "trade_date", "mu"]])

            # ---- Step 3: compute CURRENT IC & cs_vol → add to history ----
            # The current IC relies on fwd_ret at this date (T+horizon).
            # It is added to history for FUTURE dates only — today's μ
            # does NOT use today's IC.
            day_rets = forward_returns_df[
                forward_returns_df["trade_date"] == date
            ]
            merged = day_scores.merge(
                day_rets[["ts_code", ret_col]],
                on="ts_code", how="inner",
            )
            if len(merged) >= 30:
                current_ic, _ = stats.spearmanr(
                    merged[score_col], merged[ret_col],
                )
                current_cs_vol = merged[ret_col].std()
                if not np.isfinite(current_ic):
                    current_ic = 0.0
                if not np.isfinite(current_cs_vol):
                    current_cs_vol = 0.0
                history.append((date, current_ic, current_cs_vol))

            # Prune old history — keep up to 2× rolling window
            max_history = self.rolling_ic_window * 3
            if len(history) > max_history:
                history = history[-max_history:]

        if not results:
            return pd.DataFrame(columns=["ts_code", "trade_date", "mu"])

        return pd.concat(results, ignore_index=True)

    # ------------------------------------------------------------------
    # Method 2: Historical regression (horizon-safe)
    # ------------------------------------------------------------------
    def _calibrate_regression(self, scores: pd.DataFrame,
                               score_col: str,
                               forward_returns_df: pd.DataFrame,
                               horizon: int,
                               trade_dates: Optional[List[int]] = None,
                               ) -> pd.DataFrame:
        """For each date, run expanding-window regression:
        forward_return ~ score.  Training set uses ONLY mature dates.
        """
        from alpha.time_utils import matured_ic_cutoff

        ret_col = f"fwd_ret_{horizon}d"
        dates = sorted(scores["trade_date"].unique())

        if trade_dates is None:
            trade_dates = sorted(
                int(d)
                for d in forward_returns_df["trade_date"].dropna().unique()
            )

        # Merge all data
        merged = scores.merge(
            forward_returns_df[["ts_code", "trade_date", ret_col]],
            on=["ts_code", "trade_date"], how="inner",
        ).dropna(subset=[score_col, ret_col])

        results = []

        for date in dates:
            # ---- ONLY use mature dates for training ----
            cutoff = matured_ic_cutoff(date, horizon, trade_dates)
            if cutoff is None:
                continue

            train = merged[merged["trade_date"] <= cutoff]
            if len(train) < self.regression_min_obs:
                continue

            # Fit OLS
            from statsmodels.api import OLS, add_constant
            X = add_constant(train[score_col].astype("float64"))
            y = train[ret_col].astype("float64")

            try:
                model = OLS(y, X).fit()
            except Exception:
                continue

            # Predict for current date
            day_data = merged[merged["trade_date"] == date].copy()
            if len(day_data) < 30:
                continue

            X_pred = add_constant(day_data[score_col].astype("float64"))
            day_data["mu"] = model.predict(X_pred).astype("float32")

            results.append(day_data[["ts_code", "trade_date", "mu"]])

        if not results:
            return pd.DataFrame(columns=["ts_code", "trade_date", "mu"])

        return pd.concat(results, ignore_index=True)

    # ------------------------------------------------------------------
    # Method 3: Rank only (no calibration)
    # ------------------------------------------------------------------
    def _rank_only(self, scores: pd.DataFrame,
                   score_col: str) -> pd.DataFrame:
        """Return normalized scores without calibrating to returns."""
        result = scores[["ts_code", "trade_date"]].copy()
        result["mu"] = scores[score_col].astype("float32")
        return result

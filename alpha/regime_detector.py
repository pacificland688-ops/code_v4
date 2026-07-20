"""
Rule-based market regime detector.

Detects market regime using only point-in-time (PIT) observable features.
No ML training, no HMM — uses configurable thresholds on market data
that was knowable at each signal_date.

Regimes (v1):
  - trend_up: 趋势上涨
  - trend_down: 趋势下跌
  - range_bound: 震荡
  - high_volatility: 高波动
  - value_rotation: 价值轮动

Horizon safety
--------------
ALL feature computations use only data with ``trade_date <= signal_date``.
No forward-looking leakage.  Uses ``matured_ic_cutoff`` pattern from
``alpha.time_utils``.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
REGIME_NAMES = ["trend_up", "trend_down", "range_bound", "high_volatility", "value_rotation"]
SLEEVE_NAMES = ["reversal", "momentum", "defensive", "value", "volume_price", "shock_reversal"]


class RegimeDetector:
    """Rule-based market regime detection.

    Computes PIT-safe features from index and price data, then converts
    them to regime probabilities via softmax with temperature.

    Features are computed as raw values (not z-scored).  Regime scores
    are derived from raw features using directional rules, then passed
    through softmax to produce probabilities.

    Parameters
    ----------
    config : dict
        Regime detector configuration (from regime.yaml).
    """

    def __init__(self, config: dict):
        # --- version ---
        self.scoring_version = str(config.get("scoring_version", "v1"))

        # --- index ---
        self.index_code = config.get("index_code", "000300.SH")

        # --- trend ---
        trend_cfg = config.get("trend", {})
        self.ma_short = int(trend_cfg.get("ma_short", 60))
        self.ma_long = int(trend_cfg.get("ma_long", 120))
        self.return_windows = trend_cfg.get("return_windows", [20, 60, 120])

        # --- volatility ---
        vol_cfg = config.get("volatility", {})
        self.vol_windows = vol_cfg.get("vol_windows", [20, 60])
        self.drawdown_window = int(vol_cfg.get("drawdown_window", 60))

        # --- breadth ---
        breadth_cfg = config.get("breadth", {})
        self.ma_window = int(breadth_cfg.get("ma_window", 60))
        self.min_stocks = int(breadth_cfg.get("min_stocks", 100))

        # --- smoothing ---
        smooth_cfg = config.get("smoothing", {})
        self.halflife = int(smooth_cfg.get("halflife", 4))

        # --- softmax temperature ---
        # Priority: scoring.temperature > top-level temperature > 1.0
        _scoring_cfg_temp = config.get("scoring", {})
        self.temperature = float(
            _scoring_cfg_temp.get("temperature",
            config.get("temperature", 1.0))
        )

        # --- Feature scale reference (computed from first call) ---
        self._feature_scales: Dict[str, float] = {}

        # --- V2: PIT normalization ---
        norm_cfg = config.get("normalization", {})
        self.norm_mode = str(norm_cfg.get("mode", "expanding"))
        self.norm_rolling_window = int(norm_cfg.get("rolling_window_trading_days", 504))
        self.norm_min_warmup = int(norm_cfg.get("min_warmup_trading_days", 252))

        # --- V2: scoring tweaks ---
        scoring_cfg = config.get("scoring", {})
        self.v2_range_bound_bias = float(scoring_cfg.get("range_bound_baseline", 0.0))
        self.v2_value_rotation_enabled = bool(
            scoring_cfg.get("value_rotation_enabled", False)
        )

        # --- V2: auxiliary indices for value_rotation ---
        aux_idx = config.get("auxiliary_indices", {})
        self.aux_value_index = str(aux_idx.get("csi300_value", "930917.CSI"))
        self.aux_growth_index = str(aux_idx.get("csi300_growth", "930918.CSI"))
        self._aux_index_cache: Optional[pd.DataFrame] = None
        self._aux_index_diag: Dict[str, object] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def compute_features(
        self,
        index_df: pd.DataFrame,
        prices_df: Optional[pd.DataFrame],
        signal_dates: Sequence[int],
    ) -> pd.DataFrame:
        """Compute PIT-safe raw regime features for each signal date.

        Parameters
        ----------
        index_df : pd.DataFrame
            Index daily data with columns ``[ts_code, trade_date, close, vol, ...]``.
            Must be sorted by trade_date ascending.
        prices_df : pd.DataFrame or None
            Adjusted stock prices with columns ``[ts_code, trade_date, adj_close]``.
            Used for market breadth computation.  If None, breadth features
            are set to neutral (0.0).
        signal_dates : sequence of int
            Signal dates YYYYMMDD for which to compute features.

        Returns
        -------
        pd.DataFrame
            Columns:
            - trade_date (int)
            - trend_strength (raw, not z-scored)
            - volatility_state (raw, annualized vol scale)
            - breadth_score (0.0–1.0 scale)
            - turnover_state (z-score of recent volume)
        """
        if index_df is None or index_df.empty:
            logger.warning("index_df is empty — returning empty features")
            return pd.DataFrame()

        # Ensure sorted
        index_df = index_df.sort_values("trade_date").reset_index(drop=True)
        index_dates = index_df["trade_date"].values

        rows = []
        for sd in signal_dates:
            sd_int = int(sd)
            # PIT: only use index data up to and including signal_date
            idx_mask = index_dates <= sd_int
            idx_pit = index_df.iloc[: idx_mask.sum()]

            # Need enough history for MA_long and longest return window
            min_required = max(self.ma_long, max(self.return_windows))
            if idx_pit.empty or len(idx_pit) < min(min_required, 20):
                continue

            trend = self._compute_trend_features(idx_pit)
            vol_state = self._compute_volatility_features(idx_pit)
            breadth = self._compute_breadth_features(prices_df, sd_int)
            turnover = self._compute_turnover_features(idx_pit)

            rows.append({
                "trade_date": sd_int,
                "trend_strength": trend,
                "volatility_state": vol_state,
                "breadth_score": breadth,
                "turnover_state": turnover,
            })

        if not rows:
            logger.warning("No valid feature rows computed")
            return pd.DataFrame()

        features = pd.DataFrame(rows)
        return features

    def predict_regime_probs(self, features: pd.DataFrame) -> pd.DataFrame:
        """Convert features to regime probabilities via softmax.

        Uses raw feature values with directional regime scoring rules.
        Features with zero variance are handled gracefully.

        Parameters
        ----------
        features : pd.DataFrame
            Output of ``compute_features()``.

        Returns
        -------
        pd.DataFrame
            Columns: ``trade_date``, ``trend_up_prob``, ``trend_down_prob``,
            ``range_bound_prob``, ``high_volatility_prob``, ``value_rotation_prob``.
            Probabilities sum to 1.0 per date.
        """
        if features.empty:
            return pd.DataFrame()

        # Build regime scores — V1 or V2 path
        if self.scoring_version == "v2":
            features_norm = self._pit_normalize_features(features)
            scores = self._features_to_regime_scores_v2(features_norm)
        else:
            scores = self._features_to_regime_scores(features)

        # Softmax with temperature
        probs = self._softmax(scores, self.temperature)

        # Apply EWM smoothing on probabilities
        if self.halflife > 0 and len(probs) > 1:
            prob_cols = [c for c in probs.columns if c.endswith("_prob")]
            probs[prob_cols] = probs[prob_cols].ewm(
                halflife=self.halflife, min_periods=1
            ).mean()

        return probs

    # ------------------------------------------------------------------
    # Feature computation (private)
    # ------------------------------------------------------------------

    def _compute_trend_features(self, idx_pit: pd.DataFrame) -> float:
        """Compute trend strength from index PIT data.

        Returns raw trend score:
          Positive = uptrend (returns positive, price above MAs, MA sloping up)
          Negative = downtrend
          Near zero = sideways

        Scale: roughly in -1.0 to +1.0 range for typical markets.
        """
        closes = idx_pit["close"].values.astype(float)

        # Returns over multiple windows
        ret_20d = 0.0
        if len(closes) > 20:
            ret_20d = (closes[-1] / closes[-21]) - 1.0

        ret_60d = 0.0
        if len(closes) > 60:
            ret_60d = (closes[-1] / closes[-61]) - 1.0

        ret_120d = 0.0
        if len(closes) > 120:
            ret_120d = (closes[-1] / closes[-121]) - 1.0

        # Price vs MAs
        price_vs_ma60 = 0.0
        if len(closes) >= 60:
            ma60 = float(np.mean(closes[-60:]))
            if ma60 > 0:
                price_vs_ma60 = (closes[-1] / ma60) - 1.0

        price_vs_ma120 = 0.0
        if len(closes) >= 120:
            ma120 = float(np.mean(closes[-120:]))
            if ma120 > 0:
                price_vs_ma120 = (closes[-1] / ma120) - 1.0

        # MA slope (20-day change in MA60, normalized)
        ma_slope = 0.0
        if len(closes) >= 80:
            ma60_20d_ago = float(np.mean(closes[-80:-20]))
            ma60_now = float(np.mean(closes[-60:]))
            if ma60_20d_ago > 0:
                ma_slope = (ma60_now / ma60_20d_ago) - 1.0

        # Combine: weight toward intermediate-term (60d) signals
        trend = (
            0.20 * ret_20d
            + 0.35 * ret_60d
            + 0.15 * ret_120d
            + 0.15 * price_vs_ma60
            + 0.05 * price_vs_ma120
            + 0.10 * ma_slope
        )
        return float(trend)

    def _compute_volatility_features(self, idx_pit: pd.DataFrame) -> float:
        """Compute volatility state from index PIT data.

        Returns annualized volatility estimate.
        Scale: ~0.10 = 10% annual vol (low), ~0.40 = 40% annual vol (high).
        """
        closes = idx_pit["close"].values.astype(float)

        if len(closes) < 21:
            return 0.15  # default moderate vol

        rets = np.diff(np.log(closes))

        # Realized volatility (annualized), emphasis on recent
        vol_20d = float(np.std(rets[-20:]) * np.sqrt(252)) if len(rets) >= 20 else 0.15

        # Max drawdown contribution
        dd_window = min(self.drawdown_window, len(closes))
        max_dd = 0.0
        if dd_window > 1:
            window_closes = closes[-dd_window:]
            peak = np.maximum.accumulate(window_closes)
            drawdowns = np.abs((window_closes - peak) / peak)
            max_dd = float(np.max(drawdowns))

        # Blend: vol dominates, DD amplifies
        vol_state = vol_20d + 0.5 * max_dd
        return float(vol_state)

    def _compute_breadth_features(
        self, prices_df: Optional[pd.DataFrame], signal_date: int
    ) -> float:
        """Compute market breadth from stock price data.

        Returns a score in [0.0, 1.0] where:
          > 0.6 = broad participation (many stocks above MA)
          < 0.4 = narrow market (few stocks participating)
          0.5 = neutral (or no data)
        """
        if prices_df is None or prices_df.empty:
            return 0.5

        # PIT filter
        pit = prices_df[prices_df["trade_date"] <= signal_date]
        if pit.empty:
            return 0.5

        # Find the price column
        if "adj_close" in pit.columns:
            price_col = "adj_close"
        elif "close" in pit.columns:
            price_col = "close"
        else:
            numeric_cols = [
                c for c in pit.columns
                if c not in ("ts_code", "trade_date")
                and pit[c].dtype in ("float64", "float32", "int64", "int32")
            ]
            if not numeric_cols:
                return 0.5
            price_col = numeric_cols[0]

        # Use the most recent date available
        all_dates = sorted(pit["trade_date"].unique())
        if len(all_dates) < 5:
            return 0.5

        latest_date = all_dates[-1]

        # Get data in a window around the latest dates for MA computation
        # Use at most the last 120 distinct dates
        window_dates = all_dates[-min(self.ma_window + 20, len(all_dates)):]

        recent = pit[pit["trade_date"].isin(window_dates)]

        # Pivot to stocks x dates
        try:
            price_matrix = recent.pivot_table(
                index="ts_code", columns="trade_date", values=price_col,
                aggfunc="last", observed=False,
            )
        except Exception:
            return 0.5

        if price_matrix.empty or price_matrix.shape[1] < 5:
            return 0.5

        n_stocks = len(price_matrix)
        if n_stocks < self.min_stocks:
            return 0.5

        # Compute MA for each stock using available columns
        n_cols = price_matrix.shape[1]
        ma_lookback = min(self.ma_window, n_cols)
        ma_values = price_matrix.iloc[:, -ma_lookback:].mean(axis=1)
        latest_prices = price_matrix.iloc[:, -1]

        # Pct stocks above MA
        above_ma = (latest_prices > ma_values).sum()
        pct_above = above_ma / n_stocks if n_stocks > 0 else 0.5

        # Advance/decline: use ~20d returns
        ad_ratio = 1.0
        if n_cols >= 21:
            rets_20d = price_matrix.iloc[:, -1] / price_matrix.iloc[:, -21] - 1.0
            advancing = (rets_20d > 0).sum()
            declining = (rets_20d < 0).sum()
            if declining > 0:
                ad_ratio = advancing / declining
            elif advancing > 0:
                ad_ratio = 3.0
        # Normalize AD ratio to [0, 1] range
        ad_normalized = min(float(ad_ratio), 5.0) / 5.0

        # Combine: average of pct_above and AD ratio
        breadth = 0.6 * float(pct_above) + 0.4 * ad_normalized
        return float(np.clip(breadth, 0.0, 1.0))

    def _compute_turnover_features(self, idx_pit: pd.DataFrame) -> float:
        """Compute turnover/volume state from index data.

        Returns a z-score of recent volume vs historical.
        Positive = volume elevated, Negative = volume depressed.
        """
        if "vol" not in idx_pit.columns:
            return 0.0

        volumes = idx_pit["vol"].values.astype(float)

        if len(volumes) < 60:
            return 0.0

        vol_20d_avg = float(np.mean(volumes[-20:]))
        vol_60d_avg = float(np.mean(volumes[-60:]))
        vol_60d_std = float(np.std(volumes[-60:]))

        if vol_60d_std > 0:
            vol_zscore = (vol_20d_avg - vol_60d_avg) / vol_60d_std
        else:
            vol_zscore = 0.0

        return float(vol_zscore)

    # ------------------------------------------------------------------
    # Regime scoring & softmax (private)
    # ------------------------------------------------------------------

    def _features_to_regime_scores(self, features: pd.DataFrame) -> pd.DataFrame:
        """Convert raw feature columns to regime scores.

        Uses directional logic based on feature signs and magnitudes.
        All features are raw (not z-scored), so signs are meaningful.

        Regime score rules:
          trend_up:      trend > 0 and vol not extreme
          trend_down:    trend < 0
          range_bound:   |trend| small and vol low
          high_vol:      vol high
          value_rotation: neutral baseline (factor return proxy in v2)
        """
        t = features["trend_strength"].values.astype(float)
        v = features["volatility_state"].values.astype(float)
        b = features["breadth_score"].values.astype(float)
        to = features["turnover_state"].values.astype(float)

        # Normalize trend to [-1, 1] using tanh (squashes extreme values)
        t_norm = np.tanh(t * 10.0)  # *10 makes -0.1 → -0.76, +0.1 → +0.76

        # Normalize vol: typical annual vol is 0.15-0.40
        # Map to [0, 1] where 0.15→0, 0.40→1
        v_norm = np.clip((v - 0.10) / 0.40, 0.0, 1.0)

        # Breadth already in [0, 1]
        b_norm = np.clip(b, 0.0, 1.0)

        # Turnover: z-score, use tanh to bound
        to_norm = np.tanh(to * 0.5)

        # --- Regime scores ---
        # trend_up: positive trend, low/medium vol, good breadth
        trend_up = (
            3.0 * np.maximum(t_norm, 0.0)
            - 2.0 * v_norm
            + 1.5 * (b_norm - 0.5)
        )

        # trend_down: negative trend, elevated vol, poor breadth
        trend_down = (
            3.0 * np.maximum(-t_norm, 0.0)
            + 1.0 * v_norm
            - 1.5 * (b_norm - 0.5)
        )

        # range_bound: small |trend|, low vol
        range_bound = (
            -2.0 * np.abs(t_norm)
            - 3.0 * v_norm
            + 3.0  # baseline
        )

        # high_volatility: high vol dominates
        high_vol = (
            4.0 * v_norm
            - 1.0 * np.abs(t_norm)
            + 0.5 * np.abs(to_norm)
        )

        # value_rotation: neutral baseline (v1 — will use factor returns in v2)
        value_rotation = np.full_like(t_norm, 0.0)

        scores = pd.DataFrame(
            {
                "trade_date": features["trade_date"].values,
                "trend_up_score": trend_up,
                "trend_down_score": trend_down,
                "range_bound_score": range_bound,
                "high_volatility_score": high_vol,
                "value_rotation_score": value_rotation,
            }
        )
        return scores

    # ------------------------------------------------------------------
    # V2: PIT normalization + adjusted regime scoring
    # ------------------------------------------------------------------

    def _pit_normalize_features(self, features: pd.DataFrame) -> pd.DataFrame:
        """PIT-safe expanding/rolling z-score normalization of raw features.

        For each feature column, compute z-scores using only data available
        up to and including the current row.  Insufficient warmup rows are
        clipped to [-3, 3] to avoid extreme early-sample values.

        Returns a DataFrame with ``_norm``-suffixed columns.
        """
        feature_cols = [
            "trend_strength", "volatility_state",
            "breadth_score", "turnover_state",
        ]
        available = [c for c in feature_cols if c in features.columns]
        if not available:
            return features.copy()

        result = features[["trade_date"]].copy()
        n = len(features)

        for col in available:
            values = features[col].values.astype(float)
            normed = np.full(n, np.nan, dtype=float)

            for i in range(n):
                if self.norm_mode == "rolling":
                    start = max(0, i - self.norm_rolling_window + 1)
                else:
                    start = 0  # expanding

                window = values[start:i + 1]
                if len(window) >= max(self.norm_min_warmup, 5):
                    mu = float(np.mean(window))
                    sigma = float(np.std(window))
                    if sigma > 1e-10:
                        normed[i] = (values[i] - mu) / sigma
                    else:
                        normed[i] = 0.0
                elif len(window) >= 5:
                    # Partial warmup: compute but clip more aggressively
                    mu = float(np.mean(window))
                    sigma = float(np.std(window))
                    if sigma > 1e-10:
                        raw_z = (values[i] - mu) / sigma
                        normed[i] = float(np.clip(raw_z, -3.0, 3.0))
                    else:
                        normed[i] = 0.0

            # Clip remaining NaN (early rows)
            normed = np.where(np.isnan(normed), 0.0, normed)
            normed = np.clip(normed, -4.0, 4.0)
            result[f"{col}_norm"] = normed

        return result

    def _features_to_regime_scores_v2(
        self, features_norm: pd.DataFrame,
    ) -> pd.DataFrame:
        """Convert PIT-normalized features to regime scores (V2).

        Same directional logic as V1, but:
          - range_bound baseline replaced with ``v2_range_bound_bias``
          - value_rotation uses real style signal (or falls back to 0.0)
        """
        # Map normalized columns to original names for scoring
        col_map = {}
        for orig in ["trend_strength", "volatility_state", "breadth_score", "turnover_state"]:
            norm_col = f"{orig}_norm"
            if norm_col in features_norm.columns:
                col_map[orig] = norm_col
            elif orig in features_norm.columns:
                col_map[orig] = orig

        def _get(col_name: str) -> np.ndarray:
            key = col_map.get(col_name, col_name)
            if key in features_norm.columns:
                return features_norm[key].values.astype(float)
            return np.zeros(len(features_norm), dtype=float)

        t = _get("trend_strength")
        v = _get("volatility_state")
        b = _get("breadth_score")
        to = _get("turnover_state")

        # Normalized features are roughly unit-variance; use tanh for bounds
        t_norm = np.tanh(t * 0.5)
        v_norm = np.tanh(v * 0.5)
        # b_norm is z-scored → 0 is neutral center (not 0.5)
        b_norm = np.tanh(b * 0.5)
        to_norm = np.tanh(to * 0.5)

        # --- V2 Regime scores ---
        bias = self.v2_range_bound_bias

        # breadth uses 0-centered b_norm (neutral breadth → no tilt)
        trend_up = (
            3.0 * np.maximum(t_norm, 0.0)
            - 2.0 * v_norm
            + 1.5 * b_norm
        )

        trend_down = (
            3.0 * np.maximum(-t_norm, 0.0)
            + 1.0 * v_norm
            - 1.5 * b_norm
        )

        # V2: range_bound uses only bias (no hidden +1.5 baseline)
        range_bound = (
            -2.0 * np.abs(t_norm)
            - 3.0 * v_norm
            + bias
        )

        high_vol = (
            4.0 * v_norm
            - 1.0 * np.abs(t_norm)
            + 0.5 * np.abs(to_norm)
        )

        # V2: value_rotation from real style signal or fallback
        if self.v2_value_rotation_enabled:
            value_rotation = self._compute_value_rotation_scores(features_norm)
        else:
            value_rotation = np.zeros(len(features_norm), dtype=float)

        scores = pd.DataFrame(
            {
                "trade_date": features_norm["trade_date"].values,
                "trend_up_score": trend_up,
                "trend_down_score": trend_down,
                "range_bound_score": range_bound,
                "high_volatility_score": high_vol,
                "value_rotation_score": value_rotation,
            }
        )
        return scores

    def _compute_value_rotation_scores(
        self, features_norm: pd.DataFrame,
    ) -> np.ndarray:
        """Compute value_rotation scores from value/growth index relative returns.

        Loads auxiliary CSI 300 Value / Growth index data (cached).
        The end_date is driven by ``features_norm.trade_date.max()``, not
        hardcoded.  Returns a score array aligned to features_norm trade
        dates.  Falls back to all-zero (V1 behaviour) on any data failure.
        """
        n = len(features_norm)
        trade_dates = features_norm["trade_date"].values

        # Determine load end_date from features
        max_td = int(trade_dates.max()) if len(trade_dates) > 0 else 20251231

        # Load auxiliary index data once (or reload if cache is stale)
        if self._aux_index_cache is None:
            self._aux_index_cache = self._load_auxiliary_index_data(end_date=str(max_td))

        aux = self._aux_index_cache
        if aux is None or aux.empty:
            return np.zeros(n, dtype=float)

        scores = np.zeros(n, dtype=float)
        invalid_close_count = 0
        for i, td in enumerate(trade_dates):
            td_int = int(td)
            # PIT: only use data up to td
            pit = aux[aux["trade_date"] <= td_int]
            if len(pit) < 60:
                continue

            # Compute 20d relative return: value vs growth
            value_close = pit["value_close"].values.astype(float)
            growth_close = pit["growth_close"].values.astype(float)

            # --- Robustness guards ---
            # Filter to positive, finite close prices
            v_valid = (value_close > 0) & np.isfinite(value_close)
            g_valid = (growth_close > 0) & np.isfinite(growth_close)
            both_valid = v_valid & g_valid

            if not both_valid.any():
                invalid_close_count += 1
                logger.debug(
                    "trade_date=%d: no valid (positive, finite) close prices — "
                    "value_rotation_score=0", td_int,
                )
                continue

            value_close_clean = value_close[both_valid]
            growth_close_clean = growth_close[both_valid]

            if len(value_close_clean) < 21:
                invalid_close_count += 1
                continue

            # 20d returns (safe: denominators are positive by construction)
            v20 = value_close_clean[-1] / value_close_clean[-21] - 1.0
            g20 = growth_close_clean[-1] / growth_close_clean[-21] - 1.0

            if not (np.isfinite(v20) and np.isfinite(g20)):
                invalid_close_count += 1
                continue

            rel_ret = v20 - g20

            # 60d if available
            if len(value_close_clean) >= 61:
                v60 = value_close_clean[-1] / value_close_clean[-61] - 1.0
                g60 = growth_close_clean[-1] / growth_close_clean[-61] - 1.0
                if np.isfinite(v60) and np.isfinite(g60):
                    rel_ret_60 = v60 - g60
                else:
                    rel_ret_60 = rel_ret
            else:
                rel_ret_60 = rel_ret

            # Combine: more weight on recent 20d, some on 60d trend
            raw = 2.0 * rel_ret + 1.0 * rel_ret_60
            result = float(np.tanh(raw * 10.0)) * 2.0
            if np.isfinite(result):
                scores[i] = result
            else:
                invalid_close_count += 1

        # Update diagnostic counter (best-effort)
        try:
            if isinstance(self._aux_index_diag, dict):
                self._aux_index_diag["invalid_close_rows"] = invalid_close_count
        except Exception:
            pass

        return scores

    def _load_auxiliary_index_data(
        self, end_date: str = "20241231",
    ) -> Optional[pd.DataFrame]:
        """Load value and growth index data for value_rotation computation.

        Best-effort: returns None on any failure.  Stores diagnostic info
        in ``self._aux_index_diag`` for downstream inspection.

        Parameters
        ----------
        end_date : str
            End date for data loading (driven by features max trade_date).
        """
        diag: Dict[str, object] = {
            "value_index": self.aux_value_index,
            "growth_index": self.aux_growth_index,
            "end_date": end_date,
            "rows": 0,
            "min_date": None,
            "max_date": None,
            "fallback_reason": None,
            "invalid_close_rows": 0,
        }
        try:
            from data.tushare_client import get_client
            client = get_client()

            value_df = client.get_index_daily(
                index_code=self.aux_value_index,
                start_date="20150101",
                end_date=end_date,
                allow_partial=True,
            )
            growth_df = client.get_index_daily(
                index_code=self.aux_growth_index,
                start_date="20150101",
                end_date=end_date,
                allow_partial=True,
            )

            if value_df is None or value_df.empty:
                diag["fallback_reason"] = "value_index_empty"
                logger.debug("Value index data empty — value_rotation disabled")
                self._aux_index_diag = diag
                return None
            if growth_df is None or growth_df.empty:
                diag["fallback_reason"] = "growth_index_empty"
                logger.debug("Growth index data empty — value_rotation disabled")
                self._aux_index_diag = diag
                return None

            # Merge on trade_date
            value_df = value_df[["trade_date", "close"]].copy()
            value_df = value_df.rename(columns={"close": "value_close"})
            growth_df = growth_df[["trade_date", "close"]].copy()
            growth_df = growth_df.rename(columns={"close": "growth_close"})

            merged = value_df.merge(growth_df, on="trade_date", how="inner")
            merged = merged.sort_values("trade_date").reset_index(drop=True)

            if merged.empty:
                diag["fallback_reason"] = "merge_empty"
                self._aux_index_diag = diag
                return None

            diag["rows"] = len(merged)
            diag["min_date"] = int(merged["trade_date"].min())
            diag["max_date"] = int(merged["trade_date"].max())

            logger.info(
                "Loaded auxiliary index data: %d rows for value_rotation "
                "(end_date=%s, range=%s → %s)",
                len(merged), end_date, diag["min_date"], diag["max_date"],
            )
            self._aux_index_diag = diag
            return merged

        except Exception as exc:
            diag["fallback_reason"] = f"exception: {exc}"
            logger.debug("Failed to load auxiliary indices: %s — value_rotation disabled", exc)
            self._aux_index_diag = diag
            return None

    # ------------------------------------------------------------------
    # Softmax (shared by V1 and V2)
    # ------------------------------------------------------------------

    @staticmethod
    def _softmax(scores: pd.DataFrame, temperature: float = 1.0) -> pd.DataFrame:
        """Apply softmax to regime scores, returning probabilities.

        P(regime_i) = exp(score_i / T) / Σ exp(score_j / T)

        Uses numerically stable implementation (subtract max per row).
        """
        score_cols = [c for c in scores.columns if c.endswith("_score")]
        score_matrix = scores[score_cols].values.astype(float)

        # Apply temperature
        if temperature > 0:
            score_matrix = score_matrix / max(temperature, 0.1)

        # Numerical stability: subtract max per row
        row_max = score_matrix.max(axis=1, keepdims=True)
        exp_scores = np.exp(score_matrix - row_max)
        row_sum = exp_scores.sum(axis=1, keepdims=True)
        prob_matrix = exp_scores / row_sum

        # Build output
        regime_names = [c.replace("_score", "_prob") for c in score_cols]
        probs = pd.DataFrame(prob_matrix, columns=regime_names)
        probs.insert(0, "trade_date", scores["trade_date"].values)

        return probs


# ---------------------------------------------------------------------------
# Convenience loader
# ---------------------------------------------------------------------------

def load_regime_config(config_path: str = "configs/regime.yaml") -> dict:
    """Load regime YAML configuration.

    Parameters
    ----------
    config_path : str
        Path to regime YAML file.

    Returns
    -------
    dict
        Parsed configuration.
    """
    import yaml
    from pathlib import Path

    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Regime config not found: {config_path}")

    with open(path, "r", encoding="utf-8") as fh:
        config = yaml.safe_load(fh) or {}

    return config

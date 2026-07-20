"""
ML-based alpha generation for cross-sectional return prediction.

Reuses code_v3 ML strategy concepts (walk-forward, purge+embargo,
train-only preprocessing) but adapted for cross-sectional setting.

Model: sklearn GBDT/RandomForest predicting future cross-sectional return rank.
Features: PIT-processed factors (already cross-sectionally standardized).
Target: forward 5/10/20 day return, cross-sectionally rank-normalized or
industry+marketcap neutralized.

Walk-forward: expanding or rolling window, sequential training.

Memory: ML is trained per walk-forward fold. Features are loaded
for the training window, not the full history.
"""

import logging
from typing import Optional, List, Dict, Any, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class MLAlphaModel:
    """
    Machine learning alpha model for cross-sectional prediction.

    Uses walk-forward validation with purge + embargo to prevent
    data leakage across training/test splits.

    Parameters
    ----------
    model_type : str
        "random_forest", "gradient_boosting", or "lightgbm".
    model_params : dict
        Parameters passed to the sklearn model constructor.
    """

    SUPPORTED_MODELS = ["random_forest", "gradient_boosting"]

    def __init__(self,
                 model_type: str = "gradient_boosting",
                 model_params: Optional[dict] = None,
                 target_horizon: int = 5,
                 purge_days: int = 5,
                 embargo_days: int = 60):
        self.model_type = model_type
        self.model_params = model_params or {}
        self.target_horizon = target_horizon
        self.purge_days = purge_days
        self.embargo_days = embargo_days

        self._model = None
        self._feature_names: List[str] = []
        self._feature_importance: Optional[pd.DataFrame] = None

    # ------------------------------------------------------------------
    # Model factory
    # ------------------------------------------------------------------
    def _build_model(self):
        """Create a new model instance."""
        if self.model_type == "random_forest":
            from sklearn.ensemble import RandomForestRegressor
            params = {"n_estimators": 100, "max_depth": 8,
                      "min_samples_leaf": 50, "random_state": 42,
                      "n_jobs": -1}
            params.update(self.model_params)
            return RandomForestRegressor(**params)
        elif self.model_type == "gradient_boosting":
            from sklearn.ensemble import GradientBoostingRegressor
            params = {"n_estimators": 100, "max_depth": 5,
                      "learning_rate": 0.05, "min_samples_leaf": 50,
                      "subsample": 0.8, "random_state": 42}
            params.update(self.model_params)
            return GradientBoostingRegressor(**params)
        else:
            raise ValueError(f"Unsupported model: {self.model_type}")

    # ------------------------------------------------------------------
    # Data preparation
    # ------------------------------------------------------------------
    def prepare_data(self,
                     factor_dfs: Dict[str, pd.DataFrame],
                     forward_returns_df: pd.DataFrame,
                     start_date: Optional[int] = None,
                     end_date: Optional[int] = None) -> Tuple[np.ndarray, np.ndarray, pd.Index]:
        """
        Merge factor DataFrames into a single feature matrix.

        Builds sample-level (date, ts_code) records.

        Returns
        -------
        (X, y, index) where index is a MultiIndex (trade_date, ts_code).
        """
        ret_col = f"fwd_ret_{self.target_horizon}d"

        # Merge all factor DataFrames
        merged = None
        # Build fresh feature list each call (don't accumulate from previous calls)
        feature_names = []

        for factor_name, df in factor_dfs.items():
            if df.empty:
                continue

            cols = [c for c in df.columns if c not in ("ts_code", "trade_date")]
            if not cols:
                continue

            factor_col = cols[0]
            feature_names.append(factor_col)

            sub = df[["ts_code", "trade_date", factor_col]].copy()
            if merged is None:
                merged = sub
            else:
                merged = merged.merge(sub, on=["ts_code", "trade_date"], how="inner")

        if merged is None:
            return np.array([]), np.array([]), pd.MultiIndex.from_arrays([[], []])

        # Date filter (before merge to reduce rows)
        if start_date is not None:
            merged = merged[merged["trade_date"] >= start_date]
        if end_date is not None:
            merged = merged[merged["trade_date"] <= end_date]

        # Merge target only if available (not available during predict)
        has_target = (
            forward_returns_df is not None
            and not forward_returns_df.empty
            and ret_col in forward_returns_df.columns
        )
        if has_target:
            target_df = forward_returns_df[["ts_code", "trade_date", ret_col]].copy()
            merged = merged.merge(target_df, on=["ts_code", "trade_date"], how="inner")
            merged = merged.dropna()
            if len(merged) < 20:
                return np.array([]), np.array([]), pd.MultiIndex.from_arrays([[], []])

        if len(merged) < 10:
            return np.array([]), np.array([]), pd.MultiIndex.from_arrays([[], []])

        # Build arrays
        self._feature_names = feature_names
        X = merged[feature_names].values.astype("float64")
        y = merged[ret_col].values.astype("float64") if has_target else np.array([])
        index = pd.MultiIndex.from_arrays(
            [merged["trade_date"], merged["ts_code"]],
            names=["trade_date", "ts_code"]
        )

        return X, y, index

    # ------------------------------------------------------------------
    # Walk-forward training
    # ------------------------------------------------------------------
    def walk_forward_train(self,
                           factor_dfs: Dict[str, pd.DataFrame],
                           forward_returns_df: pd.DataFrame,
                           dates: List[int],
                           n_initial_train: int = 252,
                           n_retrain: int = 63) -> List[Dict[str, Any]]:
        """
        Walk-forward training with purge + embargo.

        Parameters
        ----------
        factor_dfs : dict
            Factor DataFrames.
        forward_returns_df : pd.DataFrame
            Forward returns.
        dates : list of int
            Sorted list of trade dates.
        n_initial_train : int
            Number of initial training dates.
        n_retrain : int
            Retrain every N dates.

        Returns
        -------
        list of dicts with fold results.
        """
        dates = sorted(dates)
        if len(dates) < n_initial_train + 20:
            logger.error("Insufficient dates for walk-forward")
            return []

        results = []

        for i in range(n_initial_train, len(dates), n_retrain):
            train_end_idx = i - self.embargo_days
            if train_end_idx <= 0:
                continue

            test_start = dates[i]
            train_start = dates[0]
            train_end = dates[min(train_end_idx, len(dates) - 1)]

            # Prepare training data
            X_train, y_train, idx_train = self.prepare_data(
                factor_dfs, forward_returns_df,
                start_date=train_start, end_date=train_end
            )

            # Prepare test data
            test_end = dates[min(i + n_retrain - 1, len(dates) - 1)]
            X_test, y_test, idx_test = self.prepare_data(
                factor_dfs, forward_returns_df,
                start_date=test_start, end_date=test_end
            )

            if len(X_train) < 100 or len(X_test) < 30:
                continue

            logger.info(f"Fold: train {train_start}-{train_end} "
                         f"({len(X_train)} samples), "
                         f"test {test_start}-{test_end} ({len(X_test)} samples)")

            # Train
            model = self._build_model()
            model.fit(X_train, y_train)

            # Predict
            y_pred_train = model.predict(X_train)
            y_pred_test = model.predict(X_test)

            # Evaluate
            from scipy.stats import spearmanr

            train_ic, _ = spearmanr(y_train, y_pred_train)
            test_ic, _ = spearmanr(y_test, y_pred_test)

            # Feature importance
            importance = None
            if hasattr(model, "feature_importances_"):
                importance = dict(zip(self._feature_names,
                                      model.feature_importances_))

            fold_result = {
                "train_start": train_start,
                "train_end": train_end,
                "test_start": test_start,
                "test_end": test_end,
                "n_train": len(X_train),
                "n_test": len(X_test),
                "train_ic": float(train_ic),
                "test_ic": float(test_ic),
                "feature_importance": importance,
            }

            results.append(fold_result)

            # Update model for prediction
            self._model = model
            if importance:
                self._feature_importance = pd.DataFrame({
                    "feature": list(importance.keys()),
                    "importance": list(importance.values()),
                }).sort_values("importance", ascending=False)

        return results

    # ------------------------------------------------------------------
    # Prediction
    # ------------------------------------------------------------------
    def predict(self, factor_dfs: Dict[str, pd.DataFrame],
                date: int) -> pd.DataFrame:
        """
        Generate ML alpha scores for a single date.

        Parameters
        ----------
        factor_dfs : dict
            Factor DataFrames.
        date : int
            Prediction date.

        Returns
        -------
        pd.DataFrame with ts_code, trade_date, ml_score.
        """
        if self._model is None:
            raise RuntimeError("Model not trained. Call walk_forward_train first.")

        X, _, idx = self.prepare_data(
            factor_dfs, pd.DataFrame(),  # no target needed for prediction
            start_date=date, end_date=date
        )

        if len(X) == 0:
            return pd.DataFrame()

        # Predict
        scores = self._model.predict(X).astype("float32")

        result = pd.DataFrame({
            "ts_code": idx.get_level_values("ts_code"),
            "trade_date": date,
            "ml_score": scores,
        })

        # Cross-sectional z-score
        valid = result["ml_score"].dropna()
        if len(valid) > 10:
            mean = valid.mean()
            std = valid.std(ddof=0)
            if std > 0:
                result["ml_score"] = (
                    (result["ml_score"] - mean) / std
                ).astype("float32")

        return result

    # ------------------------------------------------------------------
    # Evaluation
    # ------------------------------------------------------------------
    def evaluate_walk_forward(self,
                              results: List[Dict]) -> Dict[str, Any]:
        """
        Summarize walk-forward results.

        Returns aggregate metrics and stability checks.
        """
        if not results:
            return {}

        train_ics = [r["train_ic"] for r in results]
        test_ics = [r["test_ic"] for r in results]

        # Feature importance stability
        all_features = set()
        for r in results:
            if r["feature_importance"]:
                all_features.update(r["feature_importance"].keys())

        # Check for IC collapse
        ic_decay = test_ics[-1] - test_ics[0] if len(test_ics) > 1 else 0.0

        return {
            "n_folds": len(results),
            "train_ic_mean": float(np.mean(train_ics)),
            "train_ic_std": float(np.std(train_ics)),
            "test_ic_mean": float(np.mean(test_ics)),
            "test_ic_std": float(np.std(test_ics)),
            "test_ic_last": float(test_ics[-1]) if test_ics else 0.0,
            "ic_stability": ic_decay,
            "test_ic_positive_rate": float((np.array(test_ics) > 0).mean()),
            "ic_collapse": "WARN" if ic_decay < -0.1 else "OK",
            "n_features": len(all_features),
            "total_samples": sum(r["n_train"] + r["n_test"] for r in results),
        }

    @property
    def feature_importance(self) -> Optional[pd.DataFrame]:
        """Get latest feature importance."""
        return self._feature_importance

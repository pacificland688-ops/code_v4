"""
Covariance matrix estimation for portfolio optimization.

Methods:
1. Sample covariance (naive)
2. Ledoit-Wolf shrinkage (default)
3. Factor model covariance (Barra-style): Σ = XFX' + Δ

Memory: covariance matrix is (N × N) where N ≤ 300 for CSI 300.
This is trivially small (~1MB for float32).

The estimation uses daily log returns over a configurable window
(default 252 trading days).
"""

import logging
from typing import Optional, Tuple

import numpy as np
import pandas as pd
from scipy import linalg

logger = logging.getLogger(__name__)


class CovarianceEstimator:
    """
    Covariance matrix estimator for CSI 300 portfolios.

    All methods operate on a returns matrix: (T x N) where
    T = number of time periods, N = number of stocks.
    """

    def __init__(self,
                 method: str = "ledoit_wolf",
                 window: int = 252,
                 min_obs: int = 60,
                 shrinkage_target: str = "constant_correlation",
                 annualize: bool = True):
        self.method = method
        self.window = window
        self.min_obs = min_obs
        self.shrinkage_target = shrinkage_target
        self.annualize = annualize
        self._last_cov: Optional[np.ndarray] = None
        self._last_codes: Optional[list] = None

    # ------------------------------------------------------------------
    # Main estimation
    # ------------------------------------------------------------------
    def estimate(self, returns_df: pd.DataFrame,
                 ts_codes: Optional[list] = None) -> Tuple[np.ndarray, list]:
        """
        Estimate covariance matrix from returns data.

        Parameters
        ----------
        returns_df : pd.DataFrame
            Long-format returns with ts_code, trade_date, and return columns.
            Or wide-format (date x stock) if already pivoted.
        ts_codes : list, optional
            Stock codes to include (and order).

        Returns
        -------
        (cov_matrix, stock_codes) — cov_matrix is (N x N) numpy array.
        """
        # Convert to wide format if needed
        returns_wide = self._to_wide(returns_df, ts_codes)

        if returns_wide.empty:
            return np.array([]), []

        # Use recent window
        if len(returns_wide) > self.window:
            returns_wide = returns_wide.iloc[-self.window:]

        if len(returns_wide) < self.min_obs:
            logger.warning(f"Insufficient observations: {len(returns_wide)} < {self.min_obs}")
            return np.array([]), []

        codes = list(returns_wide.columns)
        ret_matrix = returns_wide.values.astype("float64")

        # Remove columns with too many NaN
        valid_mask = np.sum(~np.isnan(ret_matrix), axis=0) >= self.min_obs
        ret_matrix = ret_matrix[:, valid_mask]
        codes = [c for c, v in zip(codes, valid_mask) if v]

        if ret_matrix.shape[1] < 5:
            return np.array([]), []

        # Fill remaining NaN with 0
        ret_matrix = np.nan_to_num(ret_matrix, nan=0.0)

        if self.method == "sample":
            cov = self._sample_cov(ret_matrix)
        elif self.method == "ledoit_wolf":
            cov = self._ledoit_wolf(ret_matrix)
        elif self.method == "factor_model":
            cov = self._factor_model_cov(ret_matrix)
        elif self.method.startswith("diagonal_shrink_"):
            # Batch 4: diagonal_shrink_NN → ledoit_wolf base + diagonal shrinkage
            factor_str = self.method.replace("diagonal_shrink_", "")
            try:
                factor = float(factor_str) / 100.0  # "20" → 0.20, "40" → 0.40
            except ValueError:
                raise ValueError(
                    f"Invalid diagonal_shrink method: {self.method}. "
                    f"Expected diagonal_shrink_NN where NN is a number (e.g. 20)."
                )
            cov = self._diagonal_shrink(ret_matrix, factor)
        else:
            raise ValueError(f"Unknown method: {self.method}")

        # Annualize
        if self.annualize:
            cov = cov * 252

        self._last_cov = cov
        self._last_codes = codes

        return cov, codes

    # ------------------------------------------------------------------
    # Conversion helpers
    # ------------------------------------------------------------------
    def _to_wide(self, returns_df: pd.DataFrame,
                 ts_codes: Optional[list] = None) -> pd.DataFrame:
        """Convert long-format returns to wide (date x stock) matrix."""
        if returns_df.empty:
            return pd.DataFrame()

        # Check if already wide (trade_date as index, ts_codes as columns)
        if returns_df.index.name == "trade_date" or isinstance(returns_df.index, pd.DatetimeIndex):
            if ts_codes:
                returns_df = returns_df.reindex(columns=ts_codes)
            return returns_df

        # Try to find return column
        ret_cols = [c for c in returns_df.columns
                    if "ret" in c.lower() or "return" in c.lower()]
        if not ret_cols:
            # Use last non-id column
            ret_cols = [c for c in returns_df.columns
                        if c not in ("ts_code", "trade_date")]

        if not ret_cols:
            return pd.DataFrame()

        ret_col = ret_cols[0]

        wide = returns_df.pivot_table(
            index="trade_date",
            columns="ts_code",
            values=ret_col,
            aggfunc="first"
        )

        if ts_codes:
            wide = wide.reindex(columns=ts_codes)

        return wide

    # ------------------------------------------------------------------
    # Sample covariance
    # ------------------------------------------------------------------
    @staticmethod
    def _sample_cov(ret_matrix: np.ndarray) -> np.ndarray:
        """Sample covariance matrix."""
        return np.cov(ret_matrix, rowvar=False)

    # ------------------------------------------------------------------
    # Ledoit-Wolf shrinkage
    # ------------------------------------------------------------------
    def _ledoit_wolf(self, ret_matrix: np.ndarray) -> np.ndarray:
        """
        Ledoit-Wolf shrinkage estimator.

        Shrinks sample covariance toward a structured target:
        - constant_correlation: all pairwise correlations equal
        - identity: diagonal matrix
        """
        n_samples, n_features = ret_matrix.shape

        # Sample covariance
        sample_cov = np.cov(ret_matrix, rowvar=False)

        if self.shrinkage_target == "constant_correlation":
            # Target: constant correlation matrix
            stds = np.sqrt(np.diag(sample_cov))
            # Correlation matrix
            D = np.diag(1.0 / (stds + 1e-12))
            corr = D @ sample_cov @ D
            # Average correlation (excluding diagonal)
            n = corr.shape[0]
            if n > 1:
                avg_corr = (corr.sum() - n) / (n * (n - 1))
            else:
                avg_corr = 0.0
            # Constant correlation target
            target_corr = np.ones((n, n)) * avg_corr
            np.fill_diagonal(target_corr, 1.0)
            # Convert back to covariance
            target = np.diag(stds) @ target_corr @ np.diag(stds)
        else:
            # Identity target (diagonal)
            avg_var = np.trace(sample_cov) / n_features
            target = np.eye(n_features) * avg_var

        # Compute shrinkage intensity (Ledoit-Wolf formula)
        # pi = sum of asymptotic variances
        delta = (sample_cov - target) ** 2
        pi = delta.sum().sum() / (n_features ** 2)

        # rho = sum of asymptotic covariances
        # Simplified: use sample variance of covariance elements
        cov_elements = sample_cov.flatten()
        rho = cov_elements.var()

        # Shrinkage intensity
        kappa = (pi - rho) / (pi + 1e-12)
        shrinkage = max(0.0, min(1.0, kappa / n_samples))

        # Shrink
        cov = (1 - shrinkage) * sample_cov + shrinkage * target

        return cov

    # ------------------------------------------------------------------
    # Diagonal shrinkage (Batch 4)
    # ------------------------------------------------------------------
    def _diagonal_shrink(self, ret_matrix: np.ndarray,
                         factor: float) -> np.ndarray:
        """
        Shrink sample covariance toward its diagonal.

        cov = (1 - factor) * sample_cov + factor * diag(diag(sample_cov))

        Parameters
        ----------
        ret_matrix : np.ndarray (T x N)
            Return matrix.
        factor : float
            Shrinkage factor toward diagonal (0 = no shrinkage, 1 = diagonal).

        Returns
        -------
        np.ndarray — shrunk covariance matrix (N x N), guaranteed finite and PSD.
        """
        # Start from sample covariance
        sample_cov = np.cov(ret_matrix, rowvar=False)

        # Construct diagonal target
        diag_vals = np.diag(sample_cov).copy()
        # Protect against zero or negative variances
        diag_vals = np.maximum(diag_vals, 1e-12)
        target = np.diag(diag_vals)

        # Shrink
        cov = (1.0 - factor) * sample_cov + factor * target

        # Guarantee PSD
        cov = (cov + cov.T) / 2.0
        eigenvalues = np.linalg.eigvalsh(cov)
        min_eig = float(eigenvalues.min()) if len(eigenvalues) else 0.0
        if min_eig < 1e-6:
            cov = cov + np.eye(cov.shape[0]) * (1e-6 - min_eig)

        return cov

    # ------------------------------------------------------------------
    # Factor model covariance
    # ------------------------------------------------------------------
    def _factor_model_cov(self, ret_matrix: np.ndarray) -> np.ndarray:
        """
        Barra-style factor model covariance.

        Σ = X * F * X' + Δ

        where X = factor exposures, F = factor covariance, Δ = specific risk.

        Simplified version: uses PCA to extract top K factors.
        """
        n_samples, n_features = ret_matrix.shape

        # Use top K principal components as factors
        n_factors = min(5, n_features // 5, n_samples // 2)
        if n_factors < 1:
            return np.cov(ret_matrix, rowvar=False)

        # PCA
        try:
            from sklearn.decomposition import PCA
            pca = PCA(n_components=n_factors)
            factors = pca.fit_transform(ret_matrix)
            factor_cov = np.cov(factors, rowvar=False)  # F: (K x K)
            loadings = pca.components_.T  # X: (N x K)
        except Exception:
            return np.cov(ret_matrix, rowvar=False)

        # Specific risk (diagonal)
        common_ret = factors @ loadings.T
        specific_ret = ret_matrix - common_ret
        specific_var = np.var(specific_ret, axis=0)
        specific_risk = np.diag(specific_var)

        # Full covariance
        cov = loadings @ factor_cov @ loadings.T + specific_risk

        return cov

    # ------------------------------------------------------------------
    # Correlation to covariance conversion
    # ------------------------------------------------------------------
    @staticmethod
    def corr_to_cov(corr: np.ndarray, vols: np.ndarray) -> np.ndarray:
        """Convert correlation matrix + volatilities to covariance."""
        D = np.diag(vols)
        return D @ corr @ D

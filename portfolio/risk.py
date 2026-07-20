"""
Portfolio risk analytics.

Computes:
- Volatility (annualized)
- Value at Risk (VaR) — historical and parametric
- Expected Shortfall (ES/CVaR)
- Maximum drawdown and drawdown profile
- Risk decomposition (factor and specific risk)
- Exposure analysis (industry, size, style)

Memory: risk computations are on portfolio-level time series
and weight vectors — negligible.
"""

import logging
from typing import Optional, List, Dict, Tuple

import numpy as np
import pandas as pd
from scipy import stats

logger = logging.getLogger(__name__)


class RiskAnalytics:
    """Portfolio risk analytics."""

    def __init__(self, confidence: float = 0.95,
                 var_window: int = 252,
                 target_volatility: float = 0.15,
                 max_drawdown_hard_stop: float = 0.25):
        self.confidence = confidence
        self.var_window = var_window
        self.target_volatility = target_volatility
        self.max_drawdown_hard_stop = max_drawdown_hard_stop

    # ------------------------------------------------------------------
    # Return-based risk metrics
    # ------------------------------------------------------------------
    def compute_metrics(self, returns: pd.Series,
                        weights_history: Optional[pd.DataFrame] = None,
                        annual_factor: float = 52.0) -> Dict[str, float]:
        """
        Compute comprehensive risk metrics from return series.

        Parameters
        ----------
        returns : pd.Series
            Portfolio period returns.
        weights_history : pd.DataFrame, optional
            (date x stock) weight matrix for risk decomposition.
        annual_factor : float
            Periods per year (52 for weekly, 252 for daily).

        Returns
        -------
        Dict of risk metrics.
        """
        if len(returns) < 5:
            return {}

        rets = returns.dropna()

        # Basic stats
        total_return = float((1 + rets).prod() - 1)
        ann_return = float((1 + rets).prod() ** (annual_factor / len(rets)) - 1)
        ann_vol = float(rets.std() * np.sqrt(annual_factor))
        sharpe = ann_return / ann_vol if ann_vol > 0 else 0.0

        # Skewness and kurtosis
        skew = float(rets.skew())
        kurt = float(rets.kurtosis())

        # Drawdown
        cumulative = (1 + rets).cumprod()
        running_max = cumulative.cummax()
        drawdown = cumulative / running_max - 1
        max_dd = float(drawdown.min())
        dd_start = drawdown.idxmin() if len(drawdown) > 0 else None
        avg_dd = float(drawdown[drawdown < 0].mean()) if (drawdown < 0).any() else 0.0

        # VaR (historical)
        var_hist = float(rets.quantile(1 - self.confidence))

        # VaR (parametric, assuming normality)
        z_score = stats.norm.ppf(1 - self.confidence)
        var_param = float(-(ann_return / annual_factor) + z_score * ann_vol / np.sqrt(annual_factor))

        # Expected Shortfall (CVaR)
        tail = rets[rets <= var_hist]
        cvar = float(tail.mean()) if len(tail) > 0 else var_hist

        # Calmar ratio
        calmar = ann_return / abs(max_dd) if max_dd != 0 else 0.0

        # Sortino ratio (downside deviation)
        downside = rets[rets < 0]
        downside_vol = downside.std() * np.sqrt(annual_factor) if len(downside) > 0 else ann_vol
        sortino = ann_return / downside_vol if downside_vol > 0 else 0.0

        # Win rate
        win_rate = float((rets > 0).mean())

        # Average win / average loss
        avg_win = float(rets[rets > 0].mean()) if (rets > 0).any() else 0.0
        avg_loss = float(rets[rets < 0].mean()) if (rets < 0).any() else 0.0
        profit_factor = abs(avg_win / avg_loss) if avg_loss != 0 else float("inf")

        # Ulcer index
        ulcer = float(np.sqrt((drawdown ** 2).mean()))

        metrics = {
            "total_return": total_return,
            "annualized_return": ann_return,
            "annualized_volatility": ann_vol,
            "sharpe_ratio": sharpe,
            "sortino_ratio": sortino,
            "calmar_ratio": calmar,
            "max_drawdown": max_dd,
            "avg_drawdown": avg_dd,
            "var_historical": var_hist,
            "var_parametric": var_param,
            "expected_shortfall": cvar,
            "skewness": skew,
            "kurtosis": kurt,
            "win_rate": win_rate,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "profit_factor": profit_factor,
            "ulcer_index": ulcer,
            "n_periods": len(rets),
        }

        # Drawdown duration
        if max_dd < 0 and dd_start is not None:
            # Find recovery
            dd_series = drawdown[dd_start:]
            recovery = dd_series[dd_series == 0]
            if len(recovery) > 0:
                metrics["max_dd_duration"] = (recovery.index[0] - dd_start) if hasattr(dd_start, '__sub__') else 0
            else:
                metrics["max_dd_duration"] = len(dd_series)

        # Hard stop check
        metrics["hard_stop_triggered"] = max_dd <= -self.max_drawdown_hard_stop

        return metrics

    # ------------------------------------------------------------------
    # Risk decomposition
    # ------------------------------------------------------------------
    def risk_decomposition(self, weights: np.ndarray,
                           Sigma: np.ndarray,
                           factor_exposures: Optional[np.ndarray] = None,
                           specific_risk: Optional[np.ndarray] = None
                           ) -> Dict[str, float]:
        """
        Decompose portfolio risk into factor and specific components.

        Parameters
        ----------
        weights : np.ndarray
            Portfolio weights.
        Sigma : np.ndarray
            Covariance matrix.
        factor_exposures : np.ndarray, optional
            Factor loading matrix (n_stocks × n_factors).
        specific_risk : np.ndarray, optional
            Specific variance per stock.

        Returns
        -------
        dict with portfolio_vol, factor_risk, specific_risk, diversification_ratio.
        """
        portfolio_var = weights @ Sigma @ weights
        portfolio_vol = np.sqrt(portfolio_var) if portfolio_var > 0 else 0.0

        result = {"portfolio_vol": float(portfolio_vol)}

        if factor_exposures is not None and specific_risk is not None:
            factor_cov = factor_exposures.T @ np.diag(
                specific_risk
            ) @ factor_exposures
            factor_var = weights @ factor_exposures @ factor_cov @ factor_exposures.T @ weights
            specific_var = portfolio_var - factor_var

            result["factor_risk"] = float(np.sqrt(max(0, factor_var)))
            result["specific_risk"] = float(np.sqrt(max(0, specific_var)))
            result["factor_risk_pct"] = float(factor_var / portfolio_var if portfolio_var > 0 else 0)

        # Diversification ratio
        vol_weighted = np.sum(np.sqrt(np.diag(Sigma)) * weights)
        result["diversification_ratio"] = float(vol_weighted / portfolio_vol if portfolio_vol > 0 else 0)

        return result

    # ------------------------------------------------------------------
    # Exposure analysis
    # ------------------------------------------------------------------
    def exposure_analysis(self, weights: np.ndarray,
                          factor_exposures: pd.DataFrame,
                          benchmark_exposures: Optional[np.ndarray] = None
                          ) -> pd.DataFrame:
        """
        Analyze portfolio factor exposures vs benchmark.

        Parameters
        ----------
        weights : np.ndarray
            Portfolio weights.
        factor_exposures : pd.DataFrame
            (stock x factor) exposure matrix.
        benchmark_exposures : np.ndarray, optional
            Benchmark factor exposures.

        Returns
        -------
        pd.DataFrame with exposure analysis.
        """
        portfolio_exp = weights @ factor_exposures.values

        result = pd.DataFrame({
            "factor": factor_exposures.columns,
            "portfolio_exposure": portfolio_exp,
        })

        if benchmark_exposures is not None:
            result["benchmark_exposure"] = benchmark_exposures
            result["active_exposure"] = portfolio_exp - benchmark_exposures

        return result

    # ------------------------------------------------------------------
    # Volatility scaling
    # ------------------------------------------------------------------
    def vol_scale_weights(self, weights: np.ndarray,
                          Sigma: np.ndarray) -> np.ndarray:
        """
        Scale portfolio weights to target volatility.

        Returns scaled weights such that portfolio vol = target_volatility.
        """
        portfolio_var = weights @ Sigma @ weights
        portfolio_vol = np.sqrt(portfolio_var) if portfolio_var > 0 else 0.0

        if portfolio_vol == 0:
            return weights

        scale = self.target_volatility / portfolio_vol
        scaled = weights * scale

        # Re-normalize to sum to 1
        if scaled.sum() > 0:
            scaled = scaled / scaled.sum()

        return scaled

    # ------------------------------------------------------------------
    # Drawdown analysis
    # ------------------------------------------------------------------
    def drawdown_analysis(self, returns: pd.Series) -> pd.DataFrame:
        """
        Detailed drawdown analysis.

        Returns DataFrame with each drawdown episode:
        start, trough, recovery, depth, duration.
        """
        if len(returns) < 2:
            return pd.DataFrame()

        cumulative = (1 + returns).cumprod()
        running_max = cumulative.cummax()
        drawdown = cumulative / running_max - 1

        # Identify drawdown episodes
        episodes = []
        in_dd = False
        dd_start = None
        dd_trough = None
        dd_max_depth = 0.0

        for date, dd in drawdown.items():
            if dd < 0 and not in_dd:
                in_dd = True
                dd_start = date
                dd_trough = date
                dd_max_depth = dd
            elif dd < 0 and in_dd:
                if dd < dd_max_depth:
                    dd_max_depth = dd
                    dd_trough = date
            elif dd == 0 and in_dd:
                episodes.append({
                    "start": dd_start,
                    "trough": dd_trough,
                    "recovery": date,
                    "depth": dd_max_depth,
                    "duration": (date - dd_start).days if hasattr(date, 'days') else 0,
                })
                in_dd = False

        if in_dd:
            episodes.append({
                "start": dd_start,
                "trough": dd_trough,
                "recovery": None,
                "depth": dd_max_depth,
                "duration": None,
            })

        return pd.DataFrame(episodes)

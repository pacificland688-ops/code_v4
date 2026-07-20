"""
Cross-sectional factor evaluation.

Computes per-factor:
- Daily Rank IC: corr(rank(factor_t), rank(forward_return_{t+1 to t+h}))
- ICIR: mean(IC) / std(IC)
- IC positive rate
- Quantile returns (top/bottom/quantile spreads)
- Factor turnover (top decile weight change between adjacent rebalance dates)
- Decay across horizons [1, 5, 10, 20]

Memory: processes one factor at a time, one date at a time.
"""

import logging
from typing import Optional, List, Dict, Tuple, Any

import numpy as np
import pandas as pd
from scipy import stats

logger = logging.getLogger(__name__)


class CrossSectionEvaluator:
    """
    Evaluate cross-sectional factor performance.

    Computes IC statistics, quantile returns, turnover, and decay.
    """

    def __init__(self, panel_loader=None, min_stocks: int = 30):
        self._loader = panel_loader
        self.min_stocks = min_stocks

    @property
    def loader(self):
        if self._loader is None:
            from data.panel_loader import get_loader
            self._loader = get_loader()
        return self._loader

    # ------------------------------------------------------------------
    # IC computation
    # ------------------------------------------------------------------
    def compute_daily_ic(self, factor_df: pd.DataFrame,
                         factor_col: str,
                         forward_returns_df: pd.DataFrame,
                         horizon: int = 5) -> pd.DataFrame:
        """
        Compute daily Rank IC for a factor.

        Parameters
        ----------
        factor_df : pd.DataFrame
            Factor values with ts_code, trade_date, and factor column.
        factor_col : str
            Name of the factor value column.
        forward_returns_df : pd.DataFrame
            Forward returns with ts_code, trade_date, fwd_ret_{h}d columns.
        horizon : int
            Forward return horizon in trading days.

        Returns
        -------
        pd.DataFrame with trade_date, ic, rank_ic columns.
        """
        ret_col = f"fwd_ret_{horizon}d"

        if factor_df.empty or forward_returns_df.empty:
            return pd.DataFrame()

        # Merge factor with forward returns
        merged = factor_df.merge(
            forward_returns_df[["ts_code", "trade_date", ret_col]],
            on=["ts_code", "trade_date"],
            how="inner"
        )

        if merged.empty:
            return pd.DataFrame()

        # Compute daily IC
        dates = sorted(merged["trade_date"].unique())
        records = []

        for date in dates:
            day_data = merged[merged["trade_date"] == date].dropna(
                subset=[factor_col, ret_col]
            )
            if len(day_data) < self.min_stocks:
                continue

            # Pearson IC
            pearson_ic, pearson_pval = stats.pearsonr(
                day_data[factor_col], day_data[ret_col]
            )

            # Rank (Spearman) IC
            rank_ic, rank_pval = stats.spearmanr(
                day_data[factor_col], day_data[ret_col]
            )

            records.append({
                "trade_date": date,
                "ic": np.float32(pearson_ic),
                "ic_pval": np.float32(pearson_pval),
                "rank_ic": np.float32(rank_ic),
                "rank_ic_pval": np.float32(rank_pval),
                "n_stocks": len(day_data),
            })

        return pd.DataFrame(records)

    # ------------------------------------------------------------------
    # IC Summary statistics
    # ------------------------------------------------------------------
    def ic_summary(self, ic_df: pd.DataFrame,
                   ic_col: str = "rank_ic") -> Dict[str, float]:
        """
        Compute IC summary statistics.

        Returns dict with:
        - mean_ic, std_ic, icir, ic_positive_rate, t_stat
        """
        if ic_df.empty:
            return {
                "mean_ic": 0.0, "std_ic": 0.0, "icir": 0.0,
                "ic_positive_rate": 0.0, "t_stat": 0.0,
                "n_days": 0,
            }

        ic = ic_df[ic_col].dropna()
        if len(ic) < 5:
            return {
                "mean_ic": 0.0, "std_ic": 0.0, "icir": 0.0,
                "ic_positive_rate": 0.0, "t_stat": 0.0,
                "n_days": len(ic),
            }

        mean_ic = float(ic.mean())
        std_ic = float(ic.std(ddof=0))
        icir = mean_ic / std_ic if std_ic > 0 else 0.0
        positive_rate = float((ic > 0).mean())
        t_stat = mean_ic / (std_ic / np.sqrt(len(ic))) if std_ic > 0 else 0.0

        return {
            "mean_ic": mean_ic,
            "std_ic": std_ic,
            "icir": icir,
            "ic_positive_rate": positive_rate,
            "t_stat": t_stat,
            "n_days": len(ic),
        }

    # ------------------------------------------------------------------
    # IC by year
    # ------------------------------------------------------------------
    def ic_by_period(self, ic_df: pd.DataFrame,
                     periods: List[Tuple[int, int]],
                     ic_col: str = "rank_ic") -> pd.DataFrame:
        """
        Compute IC statistics for specified year ranges.

        Parameters
        ----------
        ic_df : pd.DataFrame
            Daily IC data with trade_date column.
        periods : list of (start_year, end_year) tuples
        ic_col : str
            IC column name.

        Returns
        -------
        pd.DataFrame with period label and summary stats.
        """
        if ic_df.empty:
            return pd.DataFrame()

        ic_df = ic_df.copy()
        ic_df["year"] = ic_df["trade_date"] // 10000

        results = []
        for start_year, end_year in periods:
            period_data = ic_df[
                (ic_df["year"] >= start_year) & (ic_df["year"] <= end_year)
                ]
            summary = self.ic_summary(period_data, ic_col)
            summary["period"] = f"{start_year}-{end_year}"
            results.append(summary)

        return pd.DataFrame(results)

    # ------------------------------------------------------------------
    # Quantile (bucket) returns
    # ------------------------------------------------------------------
    def quantile_returns(self, factor_df: pd.DataFrame,
                         factor_col: str,
                         forward_returns_df: pd.DataFrame,
                         horizon: int = 5,
                         n_quantiles: int = 5) -> pd.DataFrame:
        """
        Compute returns by factor quantile.

        For each date, sort stocks by factor, split into n_quantiles,
        compute equal-weight forward return for each quantile.

        Returns DataFrame with columns: trade_date, quantile, ret, n_stocks
        """
        ret_col = f"fwd_ret_{horizon}d"

        merged = factor_df.merge(
            forward_returns_df[["ts_code", "trade_date", ret_col]],
            on=["ts_code", "trade_date"], how="inner"
        )

        if merged.empty:
            return pd.DataFrame()

        dates = sorted(merged["trade_date"].unique())
        records = []

        for date in dates:
            day_data = merged[merged["trade_date"] == date].dropna(
                subset=[factor_col, ret_col]
            )
            if len(day_data) < self.min_stocks:
                continue

            # Check for constant factor — skip quantile assignment
            if day_data[factor_col].nunique() <= 1:
                logger.debug(
                    f"Constant factor {factor_col} on {date} — "
                    f"skipping quantile returns"
                )
                continue

            # Assign quantiles (1 = lowest factor, n = highest)
            try:
                day_data["quantile"] = pd.qcut(
                    day_data[factor_col], n_quantiles,
                    labels=False, duplicates="drop"
                ) + 1
            except ValueError:
                # Too many duplicates — skip this date
                continue

            # Drop any NaN quantiles before iterating
            day_data = day_data.dropna(subset=["quantile"])
            valid_qs = day_data["quantile"].unique()
            if len(valid_qs) < 2:
                continue

            for q in valid_qs:
                if pd.isna(q):
                    continue
                q_data = day_data[day_data["quantile"] == q]
                records.append({
                    "trade_date": date,
                    "quantile": int(q),
                    "ret": float(q_data[ret_col].mean()),
                    "n_stocks": len(q_data),
                })

        return pd.DataFrame(records)

    def quantile_summary(self, factor_df: pd.DataFrame,
                         factor_col: str,
                         forward_returns_df: pd.DataFrame,
                         horizon: int = 5,
                         n_quantiles: int = 5) -> Dict[str, Any]:
        """
        Quantile analysis summary.

        Returns top, bottom, top-bottom spread, and all quantile mean returns.
        """
        qr = self.quantile_returns(
            factor_df, factor_col, forward_returns_df, horizon, n_quantiles
        )

        if qr.empty:
            return {}

        # Average return by quantile
        q_means = qr.groupby("quantile")["ret"].mean()

        top = q_means.get(n_quantiles, np.nan)
        bottom = q_means.get(1, np.nan)
        spread = top - bottom

        # Cumulative returns
        qr["cum_ret"] = qr.groupby("quantile")["ret"].transform(
            lambda x: (1 + x).cumprod()
        )

        return {
            "horizon": horizon,
            "n_quantiles": n_quantiles,
            "top_ret": float(top) if not pd.isna(top) else 0.0,
            "bottom_ret": float(bottom) if not pd.isna(bottom) else 0.0,
            "spread": float(spread) if not pd.isna(spread) else 0.0,
            "quantile_returns": q_means.to_dict(),
            "t_stat": float(
                qr.groupby("quantile")["ret"].apply(
                    lambda x: x.mean() / (x.std() / np.sqrt(len(x))) if x.std() > 0 else 0
                ).get(n_quantiles, 0)
            ),
        }

    # ------------------------------------------------------------------
    # Factor turnover
    # ------------------------------------------------------------------
    def compute_turnover(self, factor_df: pd.DataFrame,
                         factor_col: str,
                         top_fraction: float = 0.2) -> pd.DataFrame:
        """
        Compute top-portfolio turnover between adjacent rebalance dates.

        Turnover = fraction of stocks leaving the top N% between t and t+1.

        Parameters
        ----------
        factor_df : pd.DataFrame
            Factor values.
        factor_col : str
            Factor column.
        top_fraction : float
            Fraction of stocks considered "top" (e.g., 0.2 = top quintile).

        Returns
        -------
        pd.DataFrame with trade_date and turnover columns.
        """
        if factor_df.empty:
            return pd.DataFrame()

        dates = sorted(factor_df["trade_date"].unique())
        records = []

        prev_top_stocks = None
        for date in dates:
            day_data = factor_df[factor_df["trade_date"] == date].dropna(
                subset=[factor_col]
            )
            if len(day_data) < self.min_stocks:
                continue

            n_top = max(1, int(len(day_data) * top_fraction))
            top_stocks = set(
                day_data.nlargest(n_top, factor_col)["ts_code"]
            )

            if prev_top_stocks is not None:
                # Fraction of previous top stocks NOT in current top
                left = prev_top_stocks - top_stocks
                # Fraction of current top stocks that are NEW
                new_stocks = top_stocks - prev_top_stocks
                turnover = len(new_stocks) / len(top_stocks) if top_stocks else 0.0

                records.append({
                    "trade_date": date,
                    "turnover": float(turnover),
                    "n_top": n_top,
                    "stocks_entered": len(new_stocks),
                    "stocks_left": len(left),
                })

            prev_top_stocks = top_stocks

        return pd.DataFrame(records)

    # ------------------------------------------------------------------
    # Factor decay (across horizons)
    # ------------------------------------------------------------------
    def compute_decay(self, factor_df: pd.DataFrame,
                      factor_col: str,
                      forward_returns_df: pd.DataFrame,
                      horizons: List[int] = [1, 5, 10, 20]) -> pd.DataFrame:
        """
        Compute IC across multiple horizons to assess factor decay.

        Returns DataFrame with horizon and IC statistics.
        """
        records = []
        for h in horizons:
            ic_df = self.compute_daily_ic(
                factor_df, factor_col, forward_returns_df, horizon=h
            )
            summary = self.ic_summary(ic_df)
            summary["horizon"] = h
            records.append(summary)

        return pd.DataFrame(records)

    # ------------------------------------------------------------------
    # Full factor evaluation
    # ------------------------------------------------------------------
    def evaluate_factor(self, factor_name: str,
                        factor_col: str,
                        factor_df: pd.DataFrame,
                        forward_returns_df: pd.DataFrame,
                        horizons: List[int] = [1, 5, 10, 20],
                        n_quantiles: int = 5,
                        periods: Optional[List[Tuple[int, int]]] = None
                        ) -> Dict[str, Any]:
        """
        Complete factor evaluation.

        Returns dict with all evaluation metrics.
        """
        if periods is None:
            periods = [(2016, 2018), (2019, 2021), (2022, 2024), (2025, 2026)]

        results = {
            "factor_name": factor_name,
            "factor_col": factor_col,
            "n_observations": len(factor_df),
            "n_stocks": factor_df["ts_code"].nunique(),
            "n_dates": factor_df["trade_date"].nunique(),
        }

        # IC at primary horizon (5-day)
        ic_df = self.compute_daily_ic(factor_df, factor_col,
                                      forward_returns_df, horizon=5)
        results["ic"] = self.ic_summary(ic_df)

        # IC by period
        results["ic_by_period"] = self.ic_by_period(ic_df, periods).to_dict("records")

        # Quantile returns
        quantile = self.quantile_summary(factor_df, factor_col,
                                         forward_returns_df, horizon=5,
                                         n_quantiles=n_quantiles)
        results["quantile"] = quantile

        # Turnover
        results["turnover"] = self.compute_turnover(factor_df, factor_col)

        # Decay
        results["decay"] = self.compute_decay(factor_df, factor_col,
                                              forward_returns_df, horizons)

        return results

    # ------------------------------------------------------------------
    # Batch evaluation
    # ------------------------------------------------------------------
    def evaluate_all_factors(self,
                             factor_dfs: Dict[str, pd.DataFrame],
                             forward_returns_df: pd.DataFrame,
                             **kwargs) -> List[Dict[str, Any]]:
        """
        Evaluate multiple factors and return ranked list.
        """
        all_results = []
        for name, df in factor_dfs.items():
            if df.empty:
                continue
            # Determine factor column
            factor_cols = [c for c in df.columns
                           if c not in ("ts_code", "trade_date")]
            if not factor_cols:
                continue
            factor_col = factor_cols[0]

            result = self.evaluate_factor(
                name, factor_col, df, forward_returns_df, **kwargs
            )
            all_results.append(result)

        # Sort by ICIR
        all_results.sort(
            key=lambda x: x.get("ic", {}).get("icir", 0),
            reverse=True
        )

        return all_results

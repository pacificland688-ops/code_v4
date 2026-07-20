"""
Cross-sectional factor processing pipeline.

For each date, processes raw factor values through:
1. MAD or quantile winsorization (per cross-section)
2. Industry + market-cap neutralization (OLS residual)
3. Cross-sectional z-score standardization
4. Missing value handling (industry median or drop)

Memory strategy:
- Processes one date at a time (or a small batch of dates)
- Returns long-format DataFrame, never wide matrix
- Each step is vectorized per cross-section

This is brand new code, not copied from code_v3 — the code_v3 utils
provide only the per-stock formula patterns, not the cross-sectional logic.
"""

import logging
from typing import Optional, List, Dict, Tuple

import numpy as np
import pandas as pd
from statsmodels.api import OLS, add_constant

logger = logging.getLogger(__name__)


class CrossSectionProcessor:
    """
    Cross-sectional factor processing.

    For each date in the factor panel:
    1. Winsorize: clip extreme values within each cross-section
    2. Fill missing: industry median or cross-sectional median
    3. Neutralize: regress on industry dummies + log(market_cap), take residual
    4. Standardize: cross-sectional z-score
    """

    def __init__(self,
                 winsor_method: str = "mad",
                 mad_multiplier: float = 5.0,
                 quantile_lower: float = 0.01,
                 quantile_upper: float = 0.99,
                 missing_method: str = "industry_median",
                 neutralize: bool = True,
                 neutralizers: Optional[List[str]] = None,
                 standardize_method: str = "zscore",
                 min_stocks: int = 30):
        self.winsor_method = winsor_method
        self.mad_multiplier = mad_multiplier
        self.quantile_lower = quantile_lower
        self.quantile_upper = quantile_upper
        self.missing_method = missing_method
        self.neutralize = neutralize
        self.neutralizers = neutralizers or ["industry", "log_market_cap"]
        self.standardize_method = standardize_method
        self.min_stocks = min_stocks

        # Component references (set via setters or constructor injection)
        self._industry_classifier = None
        self._loader = None

        # Flag: set to False if industry data is not PIT (default safety)
        self._industry_neutralization_warned = False

    @property
    def industry(self):
        if self._industry_classifier is None:
            from data.industry import get_industry_classifier
            self._industry_classifier = get_industry_classifier()
        return self._industry_classifier

    @property
    def loader(self):
        if self._loader is None:
            from data.panel_loader import get_loader
            self._loader = get_loader()
        return self._loader

    def _check_industry_pit(self):
        """Check if industry data is PIT-quality. If not, disable industry neutralization."""
        if not self.neutralize:
            return
        if "industry" not in self.neutralizers:
            return
        if self._industry_neutralization_warned:
            return

        if not self.industry.has_pit_data:
            logger.warning(
                "Industry classification is STATIC (not PIT). "
                "Industry neutralization DISABLED to avoid forward-looking bias. "
                "Only market-cap neutralization will be applied. "
                "Set industry.has_pit_data=True if you have true PIT industry data."
            )
            self.neutralizers = [
                n for n in self.neutralizers if n != "industry"
            ]
            self._industry_neutralization_warned = True

    # ------------------------------------------------------------------
    # Main processing pipeline
    # ------------------------------------------------------------------
    def process_factor(self, factor_df: pd.DataFrame,
                       factor_name: str,
                       ts_codes: Optional[List[str]] = None,
                       save: bool = True) -> pd.DataFrame:
        """
        Process a single factor through the cross-sectional pipeline.

        Parameters
        ----------
        factor_df : pd.DataFrame
            Long-format with columns: ts_code, trade_date, {factor_name}.
        factor_name : str
            Name of the factor column.
        ts_codes : list of str, optional
            Universe to include. If None, uses all codes in factor_df.
        save : bool
            If True, write processed factor to parquet.

        Returns
        -------
        pd.DataFrame with processed factor values (same long format).
        """
        if factor_df.empty:
            return factor_df

        df = factor_df.copy()
        processed_name = f"{factor_name}_cs"

        # Get unique dates
        dates = sorted(df["trade_date"].unique())
        logger.info(f"Processing {factor_name}: {len(dates)} dates, "
                     f"{df['ts_code'].nunique()} stocks")

        all_processed = []
        skipped = 0

        for i, date in enumerate(dates):
            try:
                date_df = self._process_single_date(
                    df, date, factor_name, ts_codes
                )
                if date_df is not None and not date_df.empty:
                    all_processed.append(date_df)
                else:
                    skipped += 1
            except Exception as e:
                logger.debug(f"Error processing {factor_name} on {date}: {e}")
                skipped += 1

            if (i + 1) % 500 == 0:
                logger.debug(f"Processed {i+1}/{len(dates)} dates for {factor_name}")

        if not all_processed:
            logger.warning(f"No valid cross-sections for {factor_name}")
            return pd.DataFrame()

        result = pd.concat(all_processed, ignore_index=True)
        logger.info(f"Processed {factor_name}: {len(result)} rows, "
                     f"{len(dates) - skipped}/{len(dates)} dates valid")

        if save and not result.empty:
            self.loader.write_factor(result, processed_name)

        return result

    def _process_single_date(self, df: pd.DataFrame, date: int,
                             factor_name: str,
                             ts_codes: Optional[List[str]] = None
                             ) -> Optional[pd.DataFrame]:
        """Process a single cross-section."""
        # Extract data for this date
        date_df = df[df["trade_date"] == date].copy()

        if ts_codes:
            date_df = date_df[date_df["ts_code"].isin(ts_codes)]

        if len(date_df) < self.min_stocks:
            return None

        # Get factor values
        values = date_df.set_index("ts_code")[factor_name].astype("float32")

        # Step 1: Winsorize
        values = self._winsorize(values)

        # Step 2: Handle missing values
        values = self._fill_missing(values, date)

        # Step 3: Neutralize
        if self.neutralize:
            values = self._neutralize(values, date)

        # Step 4: Standardize
        values = self._standardize(values)

        # Build result
        result = pd.DataFrame({
            "ts_code": values.index,
            "trade_date": date,
            f"{factor_name}_cs": values.values.astype("float32"),
        })

        return result

    # ------------------------------------------------------------------
    # Step 1: Winsorization
    # ------------------------------------------------------------------
    def _winsorize(self, series: pd.Series) -> pd.Series:
        """Winsorize extreme values in a cross-section."""
        valid = series.dropna()
        if len(valid) < 5:
            return series

        if self.winsor_method == "mad":
            median = valid.median()
            mad = (valid - median).abs().median()
            if mad == 0:
                return series
            upper = median + self.mad_multiplier * mad
            lower = median - self.mad_multiplier * mad
            return series.clip(lower=lower, upper=upper)
        elif self.winsor_method == "quantile":
            lower = valid.quantile(self.quantile_lower)
            upper = valid.quantile(self.quantile_upper)
            return series.clip(lower=lower, upper=upper)
        else:
            return series

    # ------------------------------------------------------------------
    # Step 2: Missing value handling
    # ------------------------------------------------------------------
    def _fill_missing(self, series: pd.Series, date: int) -> pd.Series:
        """Fill missing factor values."""
        if self.missing_method == "drop":
            return series.dropna()
        elif self.missing_method == "cross_sectional_median":
            median = series.median()
            return series.fillna(median)
        elif self.missing_method == "industry_median":
            return self._fill_with_industry_median(series, date)
        else:
            return series

    def _fill_with_industry_median(self, series: pd.Series, date: int) -> pd.Series:
        """
        Fill missing values with industry-specific median.

        If industry data is not PIT, falls back to cross-sectional median
        (static industry applied historically would be forward-looking bias).
        """
        result = series.copy()
        missing_mask = result.isna()
        if not missing_mask.any():
            return result

        # Only use industry median if we have PIT industry data
        if not self.industry.has_pit_data:
            cs_median = series.median()
            result[missing_mask] = cs_median
            return result

        # Get industry for each stock
        ts_codes = series.index.tolist()
        industries = self.industry.get_industries(ts_codes, date)

        # Compute industry medians
        industry_series = pd.Series(industries, name="industry")
        combined = pd.DataFrame({"value": series, "industry": industry_series})
        industry_medians = combined.groupby("industry")["value"].median()

        # Fill missing with industry median, fallback to cross-sectional median
        cs_median = series.median()
        for code in series[missing_mask].index:
            ind = industries.get(code)
            if ind and ind in industry_medians.index and pd.notna(industry_medians[ind]):
                result[code] = industry_medians[ind]
            else:
                result[code] = cs_median

        return result

    # ------------------------------------------------------------------
    # Step 3: Neutralization
    # ------------------------------------------------------------------
    def _neutralize(self, series: pd.Series, date: int) -> pd.Series:
        """
        Neutralize factor against industry dummies and log market cap.

        Runs OLS: factor ~ industry_dummies + log_market_cap
        Returns the residual (orthogonalized factor).

        Industry neutralization is gated on IndustryClassifier.has_pit_data.
        """
        # Gate: check industry data quality before using it
        self._check_industry_pit()

        # Build design matrix
        ts_codes = series.dropna().index.tolist()
        if len(ts_codes) < self.min_stocks:
            return series

        # Build X matrix. Start empty; add columns only if neutralizer is enabled
        # AND the data source is PIT-quality.
        X_parts = []

        # Industry dummies — ONLY if industry data is PIT
        if "industry" in self.neutralizers and self.industry.has_pit_data:
            industry_dummies = self.industry.get_industry_dummies(ts_codes, date)
            if not industry_dummies.empty:
                X_parts.append(industry_dummies.reindex(ts_codes))
        elif "industry" in self.neutralizers and not self.industry.has_pit_data:
            # Already warned by _check_industry_pit; skip silently here
            pass

        # Market cap — from daily_basic (PIT via asof_date)
        if "log_market_cap" in self.neutralizers:
            try:
                size_df = self.loader.read_factor("log_market_cap",
                                                  start_date=str(date),
                                                  end_date=str(date),
                                                  ts_codes=ts_codes)
                if not size_df.empty:
                    size = size_df.set_index("ts_code")["log_market_cap"]
                    X_parts.append(size.reindex(ts_codes).to_frame("log_market_cap"))
            except Exception:
                pass

        # Combine X parts
        if not X_parts:
            # No neutralizers available — return original series unchanged
            return series
        X = pd.concat(X_parts, axis=1)

        # Ensure all columns have variance
        X = X.loc[:, X.std() > 1e-10]
        if X.shape[1] == 0:
            return series

        # Align y with X
        y = series.reindex(ts_codes)
        common_idx = y.dropna().index.intersection(X.dropna().index)
        if len(common_idx) < self.min_stocks:
            return series

        y_aligned = y.loc[common_idx].astype("float64")
        X_aligned = X.loc[common_idx].astype("float64")

        try:
            X_const = add_constant(X_aligned)
            model = OLS(y_aligned, X_const).fit()
            residuals = pd.Series(model.resid, index=common_idx, dtype="float32")
            # Return residual (preserving NaN for stocks not in regression)
            result = pd.Series(np.nan, index=series.index, dtype="float32")
            result.loc[common_idx] = residuals
            return result
        except Exception as e:
            logger.debug(f"Neutralization failed for {date}: {e}")
            return series

    # ------------------------------------------------------------------
    # Step 4: Cross-sectional standardization
    # ------------------------------------------------------------------
    def _standardize(self, series: pd.Series) -> pd.Series:
        """Cross-sectional z-score or rank standardization."""
        valid = series.dropna()
        if len(valid) < 5:
            return series

        if self.standardize_method == "zscore":
            mean = valid.mean()
            std = valid.std(ddof=0)
            if std == 0 or pd.isna(std):
                return series
            return (series - mean) / std
        elif self.standardize_method == "rank":
            ranks = valid.rank(pct=True)
            result = pd.Series(np.nan, index=series.index, dtype="float32")
            result.loc[ranks.index] = ranks.astype("float32")
            return result
        else:
            return series

    # ------------------------------------------------------------------
    # Batch processing
    # ------------------------------------------------------------------
    def process_all_factors(self, factor_dfs: Dict[str, pd.DataFrame],
                            save: bool = True) -> Dict[str, pd.DataFrame]:
        """
        Process multiple factors through the cross-sectional pipeline.

        Parameters
        ----------
        factor_dfs : dict[factor_name] -> pd.DataFrame
            Raw factor DataFrames in long format.

        Returns
        -------
        dict[factor_name] -> pd.DataFrame of processed factors.
        """
        results = {}
        for name, df in factor_dfs.items():
            if df.empty:
                results[name] = df
                continue
            processed = self.process_factor(df, name, save=save)
            results[name] = processed
        return results

    # ------------------------------------------------------------------
    # Forward return computation for evaluation
    # ------------------------------------------------------------------
    @staticmethod
    def compute_forward_returns(prices_df: pd.DataFrame,
                                horizons: List[int] = [1, 5, 10, 20]) -> pd.DataFrame:
        """
        Compute forward returns for factor evaluation.

        Uses adj_close to compute forward returns.
        horizon = trading days from signal date.

        Parameters
        ----------
        prices_df : pd.DataFrame
            Must have ts_code, trade_date, adj_close columns.
        horizons : list of int
            Forward horizons in trading days.

        Returns
        -------
        pd.DataFrame with cols: ts_code, trade_date, fwd_ret_{h}d
        """
        if prices_df.empty:
            return prices_df

        df = prices_df[["ts_code", "trade_date", "adj_close"]].copy()
        df = df.sort_values(["ts_code", "trade_date"])

        for h in horizons:
            df[f"fwd_ret_{h}d"] = (
                df.groupby("ts_code")["adj_close"]
                .shift(-h) / df["adj_close"] - 1.0
            ).astype("float32")

        return df


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------
def create_default_processor() -> CrossSectionProcessor:
    """Create a CrossSectionProcessor with default settings."""
    return CrossSectionProcessor(
        winsor_method="mad",
        mad_multiplier=5.0,
        missing_method="industry_median",
        neutralize=True,
        neutralizers=["industry", "log_market_cap"],
        standardize_method="zscore",
        min_stocks=30,
    )


def create_processor_from_config(
    config_path: str = "configs/factors.yaml",
    section: str = None,
) -> CrossSectionProcessor:
    """Create a CrossSectionProcessor from a YAML config file.

    Reads the ``cross_section`` section of the YAML.
    Falls back to ``create_default_processor()`` defaults for any
    missing key.

    Parameters
    ----------
    config_path : str
        Path to a factors YAML file.
    section : str, optional
        If provided, read ``config[section]["cross_section"]`` instead
        of the top-level ``cross_section``.  Used for factor-specific
        CS configs (e.g. ``section="shock_reversal"`` reads from
        ``configs/factors_shock_reversal.yaml`` under the
        ``shock_reversal`` key).

    Returns
    -------
    CrossSectionProcessor

    Raises
    ------
    RuntimeError
        If ``section`` is provided but the config does not contain
        a ``cross_section`` block under that section.  This prevents
        silent fallback to default imputation when a factor requires
        ``missing_method="drop"`` for structural NaN filtering.
    """
    import yaml
    try:
        with open(config_path, "r", encoding="utf-8") as fh:
            config = yaml.safe_load(fh) or {}
    except Exception:
        logger.warning(
            "Cannot read %s — falling back to default processor", config_path
        )
        return create_default_processor()

    if section:
        section_cfg = config.get(section, {})
        cs = section_cfg.get("cross_section", {})
        if not cs:
            raise RuntimeError(
                f"Section '{section}' not found or missing 'cross_section' "
                f"block in {config_path}.  Shock-reversal factors require a "
                f"dedicated CS config with missing_method='drop' to prevent "
                f"structural NaN backfill.  Check that "
                f"{config_path} has [{section}].cross_section defined."
            )
    else:
        cs = config.get("cross_section", {})

    if not cs:
        return create_default_processor()

    return CrossSectionProcessor(
        winsor_method=cs.get("winsor_method", "mad"),
        mad_multiplier=cs.get("mad_multiplier", 5.0),
        quantile_lower=cs.get("quantile_lower", 0.01),
        quantile_upper=cs.get("quantile_upper", 0.99),
        missing_method=cs.get("missing_method", "industry_median"),
        neutralize=cs.get("neutralize", True),
        neutralizers=cs.get(
            "neutralizers", ["industry", "log_market_cap"]
        ),
        standardize_method=cs.get("standardize", "zscore"),
        min_stocks=cs.get("min_stocks_for_cs", 30),
    )

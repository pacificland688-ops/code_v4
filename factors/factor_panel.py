"""
Factor panel builder — orchestrates factor computation and cross-sectional
processing for a CSI 300 universe over a date range.

This is the main entry point for factor generation. It:
1. Loads PIT universe for each signal date
2. Computes technical and fundamental factors per-stock
3. Runs cross-sectional processing (winsorize, neutralize, standardize)
4. Computes forward returns for evaluation
5. Outputs processed factor parquet files

Memory: factors are computed and processed one at a time. Each factor's
raw and processed data is written to disk before the next factor starts.
"""

import logging
from typing import Optional, List, Dict, Tuple
from datetime import datetime

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class FactorPanelBuilder:
    """
    Build factor panels for CSI 300 cross-sectional strategy.

    Orchestrates universe loading, factor computation, cross-sectional
    processing, and forward return calculation.
    """

    def __init__(self,
                 universe_builder=None,
                 technical_computer=None,
                 fundamental_computer=None,
                 cs_processor=None,
                 panel_loader=None,
                 config: Optional[dict] = None):
        self._universe = universe_builder
        self._technical = technical_computer
        self._fundamental = fundamental_computer
        self._shock_reversal = None
        self._cs = cs_processor
        self._shock_cs = None
        self._loader = panel_loader
        self.config = config or {}

    @property
    def universe(self):
        if self._universe is None:
            from data.universe import get_universe_builder
            self._universe = get_universe_builder()
        return self._universe

    @property
    def technical(self):
        if self._technical is None:
            from factors.technical import TechnicalFactorComputer
            self._technical = TechnicalFactorComputer()
        return self._technical

    @property
    def fundamental(self):
        if self._fundamental is None:
            from factors.fundamental import FundamentalFactorComputer
            self._fundamental = FundamentalFactorComputer()
        return self._fundamental

    @property
    def shock_reversal(self):
        if self._shock_reversal is None:
            from factors.shock_reversal import ShockReversalComputer
            self._shock_reversal = ShockReversalComputer()
        return self._shock_reversal

    @property
    def cs(self):
        if self._cs is None:
            from factors.cross_section import (
                create_default_processor,
                create_processor_from_config,
            )
            try:
                self._cs = create_processor_from_config()
                logger.info("CrossSectionProcessor initialized from YAML config")
            except Exception:
                self._cs = create_default_processor()
                logger.warning(
                    "Falling back to default CrossSectionProcessor"
                )
        return self._cs

    @property
    def shock_cs(self):
        """CrossSectionProcessor for shock_reversal factors.

        P0-1 fix: Uses section="shock_reversal" to read the nested
        ``shock_reversal.cross_section`` block from
        configs/factors_shock_reversal.yaml.  This ensures
        missing_method='drop' and neutralizers=['log_market_cap']
        are in effect.  Structural NaN from ST/suspend/IPO/low-liquidity
        filters are NOT backfilled.

        If the config is missing or unreadable, raises RuntimeError
        rather than silently falling back to default imputation.
        """
        if self._shock_cs is None:
            from factors.cross_section import create_processor_from_config

            self._shock_cs = create_processor_from_config(
                "configs/factors_shock_reversal.yaml",
                section="shock_reversal",
            )

            # Safety assertion: must not silently backfill structural NaN
            if self._shock_cs.missing_method != "drop":
                raise RuntimeError(
                    "shock_reversal CS processor must use missing_method='drop'. "
                    "Got missing_method=%r. Check "
                    "configs/factors_shock_reversal.yaml -> "
                    "shock_reversal.cross_section.missing_method"
                    % self._shock_cs.missing_method
                )

            logger.info(
                "Shock CS processor: missing_method=%s, neutralizers=%s",
                self._shock_cs.missing_method,
                self._shock_cs.neutralizers,
            )
        return self._shock_cs

    @property
    def loader(self):
        if self._loader is None:
            from data.panel_loader import get_loader
            self._loader = get_loader()
        return self._loader

    # ------------------------------------------------------------------
    # Main pipeline
    # ------------------------------------------------------------------
    def build_panel(self,
                    start_date: str = "20160101",
                    end_date: Optional[str] = None,
                    technical_factors: Optional[List[str]] = None,
                    fundamental_factors: Optional[List[str]] = None,
                    signal_frequency: str = "weekly",
                    recompute_all: bool = False) -> Dict[str, pd.DataFrame]:
        """
        Build the complete factor panel.

        Steps:
        1. Load universe for signal dates
        2. Compute technical factors (per-stock batches)
        3. Compute fundamental factors (PIT aligned)
        4. Cross-sectional processing for each factor
        5. Compute forward returns

        Parameters
        ----------
        start_date, end_date : str
            Date range YYYYMMDD.
        technical_factors : list of str, optional
            Technical factor names to compute. None = all.
        fundamental_factors : list of str, optional
            Fundamental factor names to compute. None = all.
        signal_frequency : str
            "weekly" or "monthly".
        recompute_all : bool
            If True, recompute all factors even if cached.

        Returns
        -------
        dict[factor_name_cs] -> pd.DataFrame of processed factors.
        """
        if end_date is None:
            end_date = datetime.now().strftime("%Y%m%d")

        logger.info(f"Building factor panel: {start_date} -> {end_date}")

        # 1. Get signal dates
        signal_dates = self._get_signal_dates(start_date, end_date, signal_frequency)
        logger.info(f"Signal dates: {len(signal_dates)} ({signal_frequency})")

        # 2. Get universe for each signal date
        universe_map = self._build_universe_map(signal_dates)
        all_stocks = sorted(set().union(*universe_map.values()))
        logger.info(f"Universe: {len(all_stocks)} unique stocks across "
                     f"{len(signal_dates)} dates")

        # Guard: empty universe → no factors to compute
        if not all_stocks:
            logger.warning(
                f"No stocks in universe for {start_date}→{end_date}. "
                f"Check that index_weight data has available snapshots "
                f"within this range (PIT lag={self.universe.availability_lag_days}d). "
                f"No factors will be computed."
            )
            return {}

        # 3. Compute technical factors
        tech_results = self._compute_technical_factors(
            all_stocks, start_date, end_date,
            technical_factors, recompute_all
        )

        # 4. Compute fundamental factors
        fund_results = self._compute_fundamental_factors(
            all_stocks, start_date, end_date,
            fundamental_factors, recompute_all
        )

        # 5. Compute shock_reversal factors
        shock_results = self._compute_shock_reversal_factors(
            all_stocks, start_date, end_date, recompute_all
        )

        # 6. Cross-sectional processing
        # P1-2 fix: shock_reversal factors use their own CS processor
        # with missing_method='drop' (from configs/factors_shock_reversal.yaml).
        # Other factors continue using the generic processor from factors.yaml.
        all_raw = {**tech_results, **fund_results, **shock_results}
        processed = {}
        for name, df in all_raw.items():
            if df.empty:
                continue
            logger.info(f"Cross-section processing: {name}")
            # Route shock_reversal factors to dedicated processor
            if name in shock_results:
                cs_df = self.shock_cs.process_factor(df, name)
            else:
                cs_df = self.cs.process_factor(df, name)
            if not cs_df.empty:
                processed[f"{name}_cs"] = cs_df

        # 7. Compute forward returns for evaluation
        self._compute_and_save_returns(
            all_stocks, start_date, end_date,
            recompute=recompute_all
        )

        logger.info(f"Panel build complete: {len(processed)} processed factors")
        return processed

    # ------------------------------------------------------------------
    # Signal dates
    # ------------------------------------------------------------------
    def _get_signal_dates(self, start_date: str, end_date: str,
                          frequency: str) -> List[int]:
        """Get list of signal (rebalance) dates."""
        from data.calendar import get_calendar
        cal = get_calendar()

        if frequency == "weekly":
            date_strs = cal.weekly_rebalance_dates(start_date, end_date)
        elif frequency == "monthly":
            date_strs = cal.monthly_rebalance_dates(start_date, end_date)
        else:
            raise ValueError(f"Unknown frequency: {frequency}")

        return [int(d) for d in date_strs]

    # ------------------------------------------------------------------
    # Universe
    # ------------------------------------------------------------------
    def _build_universe_map(self, signal_dates: List[int]) -> Dict[int, List[str]]:
        """Build PIT universe for each signal date."""
        # Ensure universe data is loaded
        if self.universe._monthly_constituents is None:
            self.universe.load()

        return self.universe.get_universe_batch(signal_dates)

    # ------------------------------------------------------------------
    # Factor computation
    # ------------------------------------------------------------------
    def _compute_technical_factors(self, all_stocks: List[str],
                                   start_date: str, end_date: str,
                                   factor_names: Optional[List[str]],
                                   recompute: bool) -> Dict[str, pd.DataFrame]:
        """Compute or load technical factors."""
        if factor_names is None:
            from factors.technical import FACTOR_REGISTRY
            factor_names = list(FACTOR_REGISTRY.keys())

        results = {}
        for name in factor_names:
            if not recompute:
                # Try loading from cache
                try:
                    cached = self.loader.read_factor(name, start_date, end_date)
                    if not cached.empty and len(cached) > 1000:
                        logger.info(f"Loaded cached {name}: {len(cached)} rows")
                        results[name] = cached
                        continue
                except Exception:
                    pass

            # Compute
            df = self.technical.compute_factor(
                name, all_stocks, start_date, end_date, save=True
            )
            if not df.empty:
                results[name] = df

        return results

    def _compute_fundamental_factors(self, all_stocks: List[str],
                                     start_date: str, end_date: str,
                                     factor_names: Optional[List[str]],
                                     recompute: bool) -> Dict[str, pd.DataFrame]:
        """Compute or load fundamental factors."""
        if factor_names is None:
            factor_names = ["ep", "bp", "sp", "log_market_cap"]

        results = {}
        for name in factor_names:
            if not recompute:
                try:
                    cached = self.loader.read_factor(name, start_date, end_date)
                    if not cached.empty and len(cached) > 1000:
                        logger.info(f"Loaded cached {name}: {len(cached)} rows")
                        results[name] = cached
                        continue
                except Exception:
                    pass

        # Compute remaining
        fund_results = self.fundamental.compute_daily_basic_factors(
            all_stocks, start_date, end_date, factor_names, save=True
        )
        results.update(fund_results)

        # Financial statement factors
        if any(f in factor_names for f in ["roe", "gross_margin",
                                            "profit_growth", "leverage"]):
            fin_results = self.fundamental.compute_financial_factors(
                all_stocks, start_date, end_date, save=True
            )
            results.update(fin_results)

        return results

    def _compute_shock_reversal_factors(
        self, all_stocks: List[str],
        start_date: str, end_date: str,
        recompute: bool,
    ) -> Dict[str, pd.DataFrame]:
        """Compute or load shock_reversal factors."""
        from factors.shock_reversal import FACTOR_SPEC
        factor_names = list(FACTOR_SPEC.keys())

        results = {}
        for name in factor_names:
            if not recompute:
                try:
                    cached = self.loader.read_factor(name, start_date, end_date)
                    if not cached.empty and len(cached) > 1000:
                        logger.info(f"Loaded cached {name}: {len(cached)} rows")
                        results[name] = cached
                        continue
                except Exception:
                    pass

            # Compute
            df = self.shock_reversal.compute_factor(
                ts_codes=all_stocks,
                start_date=start_date,
                end_date=end_date,
                factor_name=name,
                save=True,
            )
            if not df.empty:
                results[name] = df

        return results

    # ------------------------------------------------------------------
    # Forward returns
    # ------------------------------------------------------------------
    def _compute_and_save_returns(self, all_stocks: List[str],
                                  start_date: str, end_date: str,
                                  recompute: bool = False):
        """Compute and cache forward returns for factor evaluation.

        When recompute=True, deletes existing cache and rebuilds.
        When recompute=False, uses factor_coverage to decide.
        Extends end_date by 20 trading days to ensure terminal labels exist.
        """
        horizons = [1, 5, 10, 20]

        # Extend end_date for look-ahead labels
        try:
            from data.calendar import get_calendar
            cal = get_calendar()
            cal.load(start_date=start_date, end_date=end_date)
            extended_end = str(
                cal.next_trade_day(int(end_date), 25)
            )
        except Exception:
            extended_end = end_date

        if not recompute:
            # Check coverage intelligently
            cov = self.loader.factor_coverage("fwd_returns", start_date, end_date)
            if cov["n_dates"] >= 12 and cov["duplicates"] == 0:
                logger.info("Forward returns already cached with sufficient coverage")
                return
            logger.info(
                f"fwd_returns coverage insufficient "
                f"(dates={cov['n_dates']}, dup={cov['duplicates']}) — rebuilding"
            )

        # Clean old cache for the affected years
        if recompute:
            import shutil
            base = self.loader.data_path / "factors/factor_name=fwd_returns"
            if base.exists():
                # Clean only year partitions within requested range
                for y in range(int(start_date[:4]), int(end_date[:4]) + 1):
                    ydir = base / f"year={y}"
                    if ydir.exists():
                        shutil.rmtree(str(ydir))
                        logger.debug(f"Cleaned fwd_returns year={y}")

        # Load adj_close — use extended range for look-ahead
        prices = self.loader.query_prices(
            start_date=start_date, end_date=extended_end,
            ts_codes=all_stocks,
            fields=["ts_code", "trade_date", "adj_close"],
            price_type="adj"
        )

        if prices.empty:
            logger.warning("No price data for forward returns")
            return

        from factors.cross_section import CrossSectionProcessor
        rets = CrossSectionProcessor.compute_forward_returns(prices, horizons)

        if not rets.empty:
            self.loader.write_factor(rets, "fwd_returns")
            logger.info(
                f"Computed forward returns: {len(rets)} rows "
                f"(range={start_date}→{extended_end})"
            )

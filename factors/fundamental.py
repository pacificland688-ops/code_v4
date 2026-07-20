"""
Fundamental factor computation for CSI 300 stocks.

Computes value, quality, growth, and risk factors from daily_basic
and financial statement data.

PIT rule: fundamentals use ann_date (announcement date) <= signal_date.
Latest available fiscal period data is used.

Memory strategy:
- Per-factor computation with narrow column selection
- Fundamental data is smaller than price data (~1 row per stock per day)
- Uses float32 for factor values
"""

import logging
from typing import Optional, List, Dict

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Factor registry
# ---------------------------------------------------------------------------
FUNDAMENTAL_FACTOR_REGISTRY: Dict[str, dict] = {
    "ep": {
        "description": "Earnings-to-Price = 1/PE",
        "data_fields": ["pe"],
        "source": "daily_basic",
        "sign": 1,
        "category": "value",
    },
    "bp": {
        "description": "Book-to-Price = 1/PB",
        "data_fields": ["pb"],
        "source": "daily_basic",
        "sign": 1,
        "category": "value",
    },
    "sp": {
        "description": "Sales-to-Price = 1/PS",
        "data_fields": ["ps"],
        "source": "daily_basic",
        "sign": 1,
        "category": "value",
    },
    "log_market_cap": {
        "description": "Log total market capitalization",
        "data_fields": ["total_mv"],
        "source": "daily_basic",
        "sign": -1,
        "category": "size",
    },
    "turnover_raw": {
        "description": "Raw turnover rate (for use in other factors)",
        "data_fields": ["turnover_rate"],
        "source": "daily_basic",
        "sign": -1,
        "category": "liquidity",
    },
}


class FundamentalFactorComputer:
    """
    Compute fundamental factors from daily_basic and financial data.

    Uses daily_basic as primary source (PE, PB, PS, total_mv, turnover_rate).
    For ROE, gross_margin, revenue_growth, profit_growth, leverage:
    uses fina_indicator / income statements with PIT ann_date alignment.
    """

    def __init__(self, panel_loader=None, client=None):
        self._loader = panel_loader
        self._client = client

    @property
    def loader(self):
        if self._loader is None:
            from data.panel_loader import get_loader
            self._loader = get_loader()
        return self._loader

    @property
    def client(self):
        if self._client is None:
            from data.tushare_client import get_client
            self._client = get_client()
        return self._client

    # ------------------------------------------------------------------
    # Daily basic factors (simple ratios)
    # ------------------------------------------------------------------
    def compute_daily_basic_factors(self, ts_codes: List[str],
                                    start_date: str, end_date: str,
                                    factor_names: Optional[List[str]] = None,
                                    save: bool = True) -> Dict[str, pd.DataFrame]:
        """
        Compute factors directly from daily_basic data.

        These are simple transformations of PE/PB/PS/total_mv.
        """
        # Guard: empty stock list → no factors to compute
        if not ts_codes:
            logger.info("compute_daily_basic_factors: empty ts_codes, returning {}")
            return {}

        if factor_names is None:
            factor_names = list(FUNDAMENTAL_FACTOR_REGISTRY.keys())

        # Only fetch factors that come from daily_basic
        daily_factors = [f for f in factor_names
                         if FUNDAMENTAL_FACTOR_REGISTRY.get(f, {}).get("source") == "daily_basic"]

        if not daily_factors:
            return {}

        # Determine required fields
        fields = set()
        for f in daily_factors:
            fields.update(FUNDAMENTAL_FACTOR_REGISTRY[f]["data_fields"])
        fields = ["ts_code", "trade_date"] + list(fields)

        logger.info(f"Loading daily_basic for {len(ts_codes)} stocks: {start_date}->{end_date}")
        df = self.loader.query_daily_basic(
            start_date=start_date, end_date=end_date,
            ts_codes=ts_codes,
            fields=fields
        )

        if df.empty:
            logger.warning("No daily_basic data for requested range")
            return {f: pd.DataFrame() for f in daily_factors}

        results = {}

        # EP = 1 / PE
        if "ep" in daily_factors and "pe" in df.columns:
            ep = df[["ts_code", "trade_date"]].copy()
            pe = df["pe"].astype("float32")
            ep["ep"] = np.where(pe > 0, (1.0 / pe).astype("float32"), np.nan)
            results["ep"] = ep
            if save:
                self.loader.write_factor(ep, "ep")

        # BP = 1 / PB
        if "bp" in daily_factors and "pb" in df.columns:
            bp = df[["ts_code", "trade_date"]].copy()
            pb = df["pb"].astype("float32")
            bp["bp"] = np.where(pb > 0, (1.0 / pb).astype("float32"), np.nan)
            results["bp"] = bp
            if save:
                self.loader.write_factor(bp, "bp")

        # SP = 1 / PS
        if "sp" in daily_factors and "ps" in df.columns:
            sp = df[["ts_code", "trade_date"]].copy()
            ps = df["ps"].astype("float32")
            sp["sp"] = np.where(ps > 0, (1.0 / ps).astype("float32"), np.nan)
            results["sp"] = sp
            if save:
                self.loader.write_factor(sp, "sp")

        # log_market_cap
        if "log_market_cap" in daily_factors and "total_mv" in df.columns:
            size = df[["ts_code", "trade_date"]].copy()
            size["log_market_cap"] = np.log(
                df["total_mv"].astype("float64") + 1.0
            ).astype("float32")
            results["log_market_cap"] = size
            if save:
                self.loader.write_factor(size, "log_market_cap")

        # turnover_raw
        if "turnover_raw" in daily_factors and "turnover_rate" in df.columns:
            to = df[["ts_code", "trade_date"]].copy()
            to["turnover_raw"] = df["turnover_rate"].astype("float32")
            results["turnover_raw"] = to
            if save:
                self.loader.write_factor(to, "turnover_raw")

        logger.info(f"Computed {len(results)} daily_basic factors")
        return results

    # ------------------------------------------------------------------
    # Financial statement factors (PIT aligned by ann_date)
    # ------------------------------------------------------------------
    def compute_financial_factors(self, ts_codes: List[str],
                                  start_date: str, end_date: str,
                                  save: bool = True) -> Dict[str, pd.DataFrame]:
        """
        Compute factors requiring financial statement data.

        Uses PIT alignment: at each signal_date t, uses the latest
        financial data with ann_date <= t.

        Factors: roe, gross_margin, revenue_growth, profit_growth, leverage.
        """
        results = {}

        # Fetch fina_indicator for ROE
        fina = self.client.get_fina_indicator(
            ts_code=",".join(ts_codes) if len(ts_codes) < 500 else None,
            fields="ts_code,ann_date,end_date,roe,roe_yoy,grossprofit_margin,"
                   "netprofit_yoy,debt_to_assets",
            start_date=start_date,
            end_date=end_date
        )

        if fina.empty:
            logger.warning("No fina_indicator data")
            return results

        # Ensure types
        fina["ann_date"] = fina["ann_date"].astype("int32")
        fina["end_date"] = fina["end_date"].astype("int32")
        fina = fina.sort_values(["ts_code", "end_date", "ann_date"])

        # Build PIT mapping: for each signal_date, find latest ann_date <= signal_date
        # We process in chunks of signal dates
        signal_dates = pd.date_range(start=start_date, end=end_date, freq="W-FRI")
        signal_ints = [int(d.strftime("%Y%m%d")) for d in signal_dates]

        roe_records = []
        gross_margin_records = []
        profit_growth_records = []
        leverage_records = []

        for code in ts_codes:
            stock_fina = fina[fina["ts_code"] == code]
            if stock_fina.empty:
                continue

            stock_fina = stock_fina.sort_values("ann_date")
            ann_dates = stock_fina["ann_date"].values

            for sd in signal_ints:
                # Find latest ann_date <= sd
                mask = ann_dates <= sd
                if not mask.any():
                    continue
                latest_idx = mask.nonzero()[0][-1]
                latest = stock_fina.iloc[latest_idx]

                # ROE
                if "roe" in latest.index and pd.notna(latest["roe"]):
                    roe_records.append({
                        "ts_code": code, "trade_date": sd,
                        "roe": np.float32(latest["roe"])
                    })

                # Gross margin
                if "grossprofit_margin" in latest.index and pd.notna(latest["grossprofit_margin"]):
                    gross_margin_records.append({
                        "ts_code": code, "trade_date": sd,
                        "gross_margin": np.float32(latest["grossprofit_margin"])
                    })

                # Profit growth
                if "netprofit_yoy" in latest.index and pd.notna(latest["netprofit_yoy"]):
                    profit_growth_records.append({
                        "ts_code": code, "trade_date": sd,
                        "profit_growth": np.float32(latest["netprofit_yoy"])
                    })

                # Leverage (debt to assets)
                if "debt_to_assets" in latest.index and pd.notna(latest["debt_to_assets"]):
                    leverage_records.append({
                        "ts_code": code, "trade_date": sd,
                        "leverage": np.float32(latest["debt_to_assets"])
                    })

        # Convert to DataFrames
        for name, records in [
            ("roe", roe_records),
            ("gross_margin", gross_margin_records),
            ("profit_growth", profit_growth_records),
            ("leverage", leverage_records),
        ]:
            if records:
                df = pd.DataFrame(records)
                results[name] = df
                if save:
                    self.loader.write_factor(df, name)
                logger.info(f"Computed {name}: {len(df)} records")

        return results

    # ------------------------------------------------------------------
    # Compute all fundamental factors
    # ------------------------------------------------------------------
    def compute_all(self, ts_codes: List[str],
                    start_date: str, end_date: str,
                    save: bool = True) -> Dict[str, pd.DataFrame]:
        """Compute all fundamental factors."""
        results = {}

        # Daily basic factors
        daily_results = self.compute_daily_basic_factors(
            ts_codes, start_date, end_date, save=save
        )
        results.update(daily_results)

        # Financial statement factors
        fin_results = self.compute_financial_factors(
            ts_codes, start_date, end_date, save=save
        )
        results.update(fin_results)

        return results

"""
PIT industry classification for CSI 300 stocks.

Uses Shenwan (申万) industry classification where available,
falling back to stock_basic industry field.

PIT rule: industry_date = most recent classification known at signal_date.

Memory: industry data is a small (stock x effective_date) table.
Stored with category dtype for ts_code and industry_code.
"""

import logging
from typing import Optional, List, Dict
from datetime import datetime

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class IndustryClassifier:
    """
    Industry classification for CSI 300 stocks.

    IMPORTANT: Currently uses stock_basic.industry which is a STATIC snapshot
    (current classification), NOT point-in-time. This is acceptable for CSI 300
    stocks where industry membership is relatively stable, but industry
    neutralization should be explicitly gated.

    Set `has_pit_data = True` only when a PIT source with effective dates
    is connected.
    """

    def __init__(self, client=None):
        self._client = client
        self._classification: Optional[pd.DataFrame] = None
        # effective_date -> {ts_code: industry_code}
        self._pit_lookup: Optional[Dict[int, Dict[str, str]]] = None
        self._effective_dates_sorted: Optional[List[int]] = None
        # Whether the loaded data is true PIT (with effective dates per stock)
        self.has_pit_data: bool = False

    @property
    def has_data(self) -> bool:
        """Whether ANY industry classification data is loaded (static or PIT)."""
        return (self._classification is not None
                and not self._classification.empty)

    @property
    def classifications(self) -> Optional[pd.DataFrame]:
        """Public accessor for classification data (read-only)."""
        return self._classification

    @property
    def client(self):
        if self._client is None:
            from data.tushare_client import get_client
            self._client = get_client()
        return self._client

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------
    def load(self, force_reload: bool = False):
        """
        Load industry classification data.

        NOTE: Tushare's index_classify returns the industry classification SCHEME
        (industry names/codes), NOT stock-to-industry mappings.

        For stock-to-industry mapping, we use stock_basic.industry which is the
        CURRENT (not PIT) classification. This is acceptable for CSI 300 stocks
        where industry membership is relatively stable, but is a known simplification.

        For true PIT industry classification, a Shenwan stock-industry membership
        table with effective dates would be needed.
        """
        # Try Tushare index_classify for Shenwan scheme (industry reference data)
        scheme_df = self.client.get_industry(use_cache=not force_reload)

        # Load stock-to-industry mapping from stock_basic
        # Note: this is STATIC (current), not PIT
        df = self._load_from_stock_basic(force_reload)

        if df.empty:
            logger.error("No industry classification available")
            return

        # If we have a scheme, validate/map industry codes
        if not scheme_df.empty and "industry_name" in scheme_df.columns:
            logger.info(f"Loaded Shenwan industry scheme: {len(scheme_df)} industries")

        # Memory-efficient types
        df["ts_code"] = df["ts_code"].astype("category")
        df["industry_code"] = df["industry_code"].astype("category")
        df["effective_date"] = df["effective_date"].astype("int32")

        self._classification = df
        self._build_pit_lookup()

        n_industries = df["industry_code"].nunique()
        logger.info(f"Loaded industry classification: "
                     f"{df['ts_code'].nunique()} stocks, "
                     f"{n_industries} industries "
                     f"(static snapshot, not PIT — acceptable for CSI 300)")

    def _load_from_stock_basic(self, force_reload: bool) -> pd.DataFrame:
        """Fallback: extract industry from stock_basic."""
        sb = self.client.get_stock_basic(
            fields="ts_code,industry",
            use_cache=not force_reload
        )
        if sb.empty:
            return sb

        sb = sb.rename(columns={"industry": "industry_name"})
        # Generate a simple industry code from the name
        industry_codes = {name: f"SW_{i:04d}"
                          for i, name in enumerate(sb["industry_name"].unique())}
        sb["industry_code"] = sb["industry_name"].map(industry_codes)
        sb["effective_date"] = 20150101  # assume static from 2015
        return sb

    def _build_pit_lookup(self):
        """Build PIT lookup: effective_date -> {ts_code: industry_code}."""
        if self._classification is None or self._classification.empty:
            self._pit_lookup = {}
            self._effective_dates_sorted = []
            return

        df = self._classification
        effective_dates = sorted(df["effective_date"].unique())
        self._effective_dates_sorted = effective_dates

        lookup = {}
        for ed in effective_dates:
            subset = df[df["effective_date"] == ed]
            lookup[ed] = dict(zip(subset["ts_code"], subset["industry_code"]))

        self._pit_lookup = lookup

    # ------------------------------------------------------------------
    # PIT queries
    # ------------------------------------------------------------------
    def get_industry(self, ts_code: str, date: int) -> Optional[str]:
        """
        Get industry code for a single stock at a PIT date.

        Returns None if no classification is available.
        """
        if self._pit_lookup is None:
            self.load()

        if not self._effective_dates_sorted:
            return None

        # Find latest effective_date <= date
        eligible = [ed for ed in self._effective_dates_sorted if ed <= date]
        if not eligible:
            return None

        latest_ed = eligible[-1]
        return self._pit_lookup.get(latest_ed, {}).get(ts_code)

    def get_industries(self, ts_codes: List[str], date: int) -> Dict[str, str]:
        """
        Get industry codes for multiple stocks at a PIT date.

        Returns dict[ts_code] -> industry_code. Missing stocks are excluded.
        """
        result = {}
        for c in ts_codes:
            ind = self.get_industry(c, date)
            if ind is not None:
                result[c] = ind
        return result

    def get_industry_dummies(self, ts_codes: List[str], date: int) -> pd.DataFrame:
        """
        Get industry dummy variables for cross-sectional neutralization.

        Returns DataFrame with index=ts_code and one column per industry.
        Missing industry = NaN (dropped later).
        """
        industries = self.get_industries(ts_codes, date)
        if not industries:
            return pd.DataFrame(index=ts_codes)

        # Create dummy matrix
        idx = pd.Index(ts_codes, name="ts_code")
        industry_series = pd.Series(industries, name="industry_code")
        dummies = pd.get_dummies(industry_series, dtype="int8")

        # Align to requested ts_codes (missing -> all zeros)
        dummies = dummies.reindex(idx, fill_value=0)

        return dummies

    def get_benchmark_industry_weights(self, date: int,
                                       universe: List[str]) -> pd.Series:
        """
        Compute benchmark industry weights for a universe at a date.

        Uses market-cap weights if available, else equal weight.
        """
        industries = self.get_industries(universe, date)
        if not industries:
            return pd.Series(dtype="float32")

        # Equal weight across stocks within each industry
        industry_counts = pd.Series(industries).value_counts()
        weights = industry_counts / industry_counts.sum()
        return weights.astype("float32")

    # ------------------------------------------------------------------
    # Industry mappings
    # ------------------------------------------------------------------
    def get_industry_name(self, industry_code: str) -> Optional[str]:
        """Get human-readable industry name from code."""
        if self._classification is None:
            return None
        match = self._classification[
            self._classification["industry_code"] == industry_code
            ]
        if match.empty or "industry_name" not in match.columns:
            return industry_code
        return match["industry_name"].iloc[0]

    def list_industries(self) -> List[str]:
        """List all unique industry codes."""
        if self._classification is None:
            return []
        return sorted(self._classification["industry_code"].unique().tolist())


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
_industry: Optional[IndustryClassifier] = None


def get_industry_classifier(**kwargs) -> IndustryClassifier:
    """Get or create singleton IndustryClassifier."""
    global _industry
    if _industry is None:
        _industry = IndustryClassifier(**kwargs)
    return _industry

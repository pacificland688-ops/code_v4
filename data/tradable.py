"""
Tradable mask generator for A-share trading constraints.

Generates per-date, per-stock tradable_mask with:
- can_buy: stock is buyable (not suspended, not limit-up at open)
- can_sell: stock is sellable (not suspended, not limit-down at open)
- can_hold: stock can be held (not delisted, etc.)
- is_suspended: stock is suspended on this date
- is_limit_up_open: opens at limit-up (cannot buy)
- is_limit_down_open: opens at limit-down (cannot sell)
- is_st: stock is ST/*ST
- is_new_stock: stock is within IPO window
- reason: human-readable explanation

Sources: suspend_d, stk_limit, stock_basic, namechange.

Memory: computed per-date, per-universe batch. Never stored as
full (date x stock x flag) wide tensor.
"""

import logging
from typing import Optional, List, Dict, Set, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class TradableMask:
    """
    Per-date tradable mask for A-share stocks.

    Evaluates all trading constraints for a given date and stock list.
    """

    # Column definitions for tradable mask DataFrame
    MASK_COLUMNS = [
        "ts_code", "trade_date",
        "can_buy", "can_sell", "can_hold",
        "is_suspended", "is_limit_up_open", "is_limit_down_open",
        "is_st", "is_new_stock",
        "limit_check_available",  # True if we had raw prices to check limits
        "reason"
    ]

    def __init__(self, client=None):
        self._client = client

        # Cached data
        self._suspend_records: Optional[pd.DataFrame] = None
        self._stock_basic: Optional[pd.DataFrame] = None
        # ST periods: {ts_code: [(entry_date, exit_date), ...]} — handles 摘帽
        self._st_periods: Dict[str, List[Tuple[int, int]]] = {}
        self._list_dates: Optional[Dict[str, int]] = None
        self._delist_dates: Optional[Dict[str, int]] = None

        # Cache: (date, limit_check_mode) -> mask DataFrame
        # Key includes limit_check_mode to prevent polluting "with limits"
        # results with "no limits" cached data.
        self._mask_cache: Dict[tuple, pd.DataFrame] = {}

        # Config
        self.ipo_min_days: int = 60
        self.cache_size_limit: int = 500  # max cached dates

    @property
    def client(self):
        if self._client is None:
            from data.tushare_client import get_client
            self._client = get_client()
        return self._client

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------
    def load(self, start_date: str = "20150101",
             end_date: Optional[str] = None,
             force_reload: bool = False):
        """
        Load all data needed for tradable mask computation.

        Data volumes are moderate (suspend records ~100K, stk_limit per date).
        """
        if end_date is None:
            from datetime import datetime
            end_date = datetime.now().strftime("%Y%m%d")

        logger.info(f"Loading tradable mask data: {start_date} -> {end_date}")

        # 1. Suspend records
        self._suspend_records = self.client.get_suspend(
            start_date=start_date,
            end_date=end_date,
            use_cache=not force_reload
        )
        if not self._suspend_records.empty:
            self._suspend_records["suspend_date"] = (
                self._suspend_records["suspend_date"].astype("int32")
            )
            self._suspend_records["resume_date"] = (
                self._suspend_records["resume_date"].astype("int32")
            )
            logger.info(f"Loaded {len(self._suspend_records)} suspend records")

        # 2. Stock basic (for listing/delisting dates)
        self._stock_basic = self.client.get_stock_basic(use_cache=not force_reload)
        if not self._stock_basic.empty:
            self._list_dates = {}
            self._delist_dates = {}
            for _, row in self._stock_basic.iterrows():
                code = row["ts_code"]
                self._list_dates[code] = int(row["list_date"])
                self._delist_dates[code] = int(row["delist_date"])
            logger.info(f"Loaded {len(self._stock_basic)} stock basic records")

        # 3. ST flags
        self._load_st_flags(start_date, force_reload)

        logger.info("Tradable mask data loaded")

    def _load_st_flags(self, start_date: str, force_reload: bool):
        """
        Build ST period lookup: {ts_code: [(entry_date, exit_date), ...]}.

        Tracks both ST entry (name change to ST*) and ST exit/摘帽
        (name change back to non-ST).
        """
        nc = self.client.get_namechange(
            start_date=start_date,
            use_cache=not force_reload
        )
        if nc.empty:
            self._st_periods = {}
            return

        nc = nc.sort_values(["ts_code", "start_date"])
        is_st = nc["name"].str.match(r"^\*?ST[^\x00-\x7F]", case=False, na=False)

        self._st_periods = {}
        for code, group in nc.groupby("ts_code"):
            periods = []
            st_entry = None
            for idx, row in group.iterrows():
                if is_st.loc[idx] and st_entry is None:
                    st_entry = int(row["start_date"])
                elif not is_st.loc[idx] and st_entry is not None:
                    periods.append((st_entry, int(row["start_date"])))
                    st_entry = None
            if st_entry is not None:
                periods.append((st_entry, 20991231))
            if periods:
                self._st_periods[code] = periods

        logger.info(f"Extracted ST periods for {len(self._st_periods)} stocks")

    # ------------------------------------------------------------------
    # Main mask computation
    # ------------------------------------------------------------------
    def get_mask(self, ts_codes: List[str], date: int,
                 raw_prices: Optional[pd.DataFrame] = None,
                 limit_data: Optional[pd.DataFrame] = None) -> pd.DataFrame:
        """
        Compute tradable mask for a list of stocks on a single date.

        Parameters
        ----------
        ts_codes : list of str
            Stock codes to evaluate.
        date : int
            Trade date YYYYMMDD.
        raw_prices : pd.DataFrame, optional
            Pre-fetched raw price data for this date (for limit checks).
            If not provided, will fetch from client.
        limit_data : pd.DataFrame, optional
            Pre-fetched stk_limit data for this date.

        Returns
        -------
        pd.DataFrame with MASK_COLUMNS.
        """
        # Determine if we have enough data to perform limit checks
        has_raw_prices = raw_prices is not None and not raw_prices.empty
        has_limit_data = limit_data is not None and not limit_data.empty
        will_check_limits = has_raw_prices and has_limit_data

        # If raw_prices provided but no limit_data, auto-fetch limit_data
        if has_raw_prices and not has_limit_data:
            limit_data = self._fetch_limit_data(ts_codes, date)
            has_limit_data = limit_data is not None and not limit_data.empty
            will_check_limits = has_raw_prices and has_limit_data

        # If raw_prices is None but we want limit checks, fetch raw open too
        if not has_raw_prices and has_limit_data:
            raw_prices = self._fetch_raw_open(ts_codes, date)
            has_raw_prices = raw_prices is not None and not raw_prices.empty
            will_check_limits = has_raw_prices and has_limit_data

        # Cache key includes whether limit checks were performed
        cache_key = (date, will_check_limits)

        # Check cache — must match both date AND limit_check_available status
        if cache_key in self._mask_cache:
            cached = self._mask_cache[cache_key]
            cached_codes = set(cached["ts_code"])
            if set(ts_codes).issubset(cached_codes):
                return cached[cached["ts_code"].isin(ts_codes)]
        # Also check opposite cache key: if we have a "with limits" cached
        # and caller only wants "no limits", the "with limits" result is
        # strictly more accurate — but we must NOT return "no limits" cached
        # when caller wants "with limits" (that's the cache pollution bug).
        # So we only reuse cached when it has >= the requested limit checks.
        if not will_check_limits:
            cache_key_with = (date, True)
            if cache_key_with in self._mask_cache:
                cached = self._mask_cache[cache_key_with]
                cached_codes = set(cached["ts_code"])
                if set(ts_codes).issubset(cached_codes):
                    return cached[cached["ts_code"].isin(ts_codes)]

        # Initialize mask
        n = len(ts_codes)
        mask = pd.DataFrame({
            "ts_code": ts_codes,
            "trade_date": date,
            "can_buy": True,
            "can_sell": True,
            "can_hold": True,
            "is_suspended": False,
            "is_limit_up_open": False,
            "is_limit_down_open": False,
            "is_st": False,
            "is_new_stock": False,
            "limit_check_available": False,
            "reason": "",
        })

        # Apply filters in order
        self._check_listing_status(mask, date)
        self._check_new_stock(mask, date)
        self._check_st(mask, date)
        self._check_suspend(mask, date)

        # Price-dependent checks (fetch if needed)
        if limit_data is None and raw_prices is None:
            self._check_limits_with_fetch(mask, date)
        else:
            self._check_limits(mask, date, raw_prices, limit_data)

        # Consolidate can_buy / can_sell / can_hold
        self._consolidate(mask)

        # Cache
        self._cache_mask(cache_key, mask)

        return mask

    def get_mask_str(self, ts_codes: List[str], date_str: str,
                     **kwargs) -> pd.DataFrame:
        """Get mask for date string YYYYMMDD."""
        return self.get_mask(ts_codes, int(date_str), **kwargs)

    def get_mask_batch(self, ts_codes: List[str],
                       dates: List[int],
                       raw_prices_by_date: Optional[Dict[int, pd.DataFrame]] = None
                       ) -> Dict[int, pd.DataFrame]:
        """
        Get masks for multiple dates efficiently.

        Does NOT construct a single huge DataFrame — returns dict keyed by date.
        """
        result = {}
        for d in dates:
            prices = raw_prices_by_date.get(d) if raw_prices_by_date else None
            result[d] = self.get_mask(ts_codes, d, raw_prices=prices)
        return result

    # ------------------------------------------------------------------
    # Individual checks
    # ------------------------------------------------------------------
    def _check_listing_status(self, mask: pd.DataFrame, date: int):
        """Check if stocks are listed and not delisted."""
        if self._list_dates is None:
            return

        for idx, row in mask.iterrows():
            code = row["ts_code"]
            list_date = self._list_dates.get(code)
            delist_date = self._delist_dates.get(code)

            if list_date is not None and date < list_date:
                mask.at[idx, "can_buy"] = False
                mask.at[idx, "can_sell"] = False
                mask.at[idx, "can_hold"] = False
                mask.at[idx, "reason"] += "not_listed; "

            if delist_date is not None and date >= delist_date:
                mask.at[idx, "can_buy"] = False
                mask.at[idx, "can_sell"] = False
                mask.at[idx, "can_hold"] = False
                mask.at[idx, "reason"] += "delisted; "

    def _check_new_stock(self, mask: pd.DataFrame, date: int):
        """Check IPO window: stocks listed < ipo_min_days ago."""
        if self.ipo_min_days <= 0 or self._list_dates is None:
            return

        from datetime import datetime, timedelta
        dt = datetime.strptime(str(date), "%Y%m%d")
        min_list_dt = dt - timedelta(days=self.ipo_min_days)
        min_list_date = int(min_list_dt.strftime("%Y%m%d"))

        for idx, row in mask.iterrows():
            code = row["ts_code"]
            list_date = self._list_dates.get(code)
            if list_date is not None and list_date > min_list_date:
                mask.at[idx, "is_new_stock"] = True
                mask.at[idx, "can_buy"] = False
                mask.at[idx, "reason"] += f"new_stock(<{self.ipo_min_days}d); "

    def _check_st(self, mask: pd.DataFrame, date: int):
        """Check ST/*ST status using period-based tracking (handles 摘帽)."""
        if not self._st_periods:
            return

        for idx, row in mask.iterrows():
            code = row["ts_code"]
            periods = self._st_periods.get(code, [])
            for entry, exit_ in periods:
                if entry <= date < exit_:
                    mask.at[idx, "is_st"] = True
                    mask.at[idx, "can_buy"] = False
                    mask.at[idx, "reason"] += "ST; "
                    break

    def _check_suspend(self, mask: pd.DataFrame, date: int):
        """Check suspension status."""
        if self._suspend_records is None or self._suspend_records.empty:
            return

        susp = self._suspend_records
        suspended = susp[
            (susp["suspend_date"] <= date) &
            (susp["resume_date"] > date)
            ]["ts_code"].unique()

        suspended_set = set(suspended)
        for idx, row in mask.iterrows():
            if row["ts_code"] in suspended_set:
                mask.at[idx, "is_suspended"] = True
                mask.at[idx, "can_buy"] = False
                mask.at[idx, "can_sell"] = False
                mask.at[idx, "reason"] += "suspended; "

    def _check_limits_with_fetch(self, mask: pd.DataFrame, date: int):
        """Fetch stk_limit and check limit up/down."""
        try:
            date_str = str(date)
            limits = self.client.get_stk_limit(
                ts_code=",".join(mask["ts_code"].tolist()),
                trade_date=date_str
            )
            if limits is not None and not limits.empty:
                self._check_limits(mask, date, None, limits)
            else:
                logger.warning(
                    f"stk_limit data unavailable for {date}. "
                    f"Limit up/down checks NOT performed — can_buy/can_sell "
                    f"may be incorrect for stocks at price limits."
                )
        except Exception as e:
            logger.warning(
                f"Could not fetch stk_limit for {date}: {e}. "
                f"Limit up/down checks NOT performed."
            )

    def _check_limits(self, mask: pd.DataFrame, date: int,
                      raw_prices: Optional[pd.DataFrame],
                      limit_data: Optional[pd.DataFrame]):
        """
        Check limit up/down at open.

        A stock opens at limit-up if raw open == up_limit.
        A stock opens at limit-down if raw open == down_limit.

        Uses raw prices (not adjusted!) for limit checks.
        Sets limit_check_available=True only when both limits and raw open are present.
        """
        if limit_data is None or limit_data.empty:
            return
        if raw_prices is None or raw_prices.empty:
            logger.warning(
                f"No raw open prices provided for limit check on {date}. "
                f"Limit checks skipped — provide raw_prices to TradableMask.get_mask()."
            )
            return

        mask["limit_check_available"] = True

        # Deduplicate to avoid ambiguous Series from duplicate index
        limit_data = limit_data.drop_duplicates(["ts_code", "trade_date"], keep="last")
        if raw_prices is not None and not raw_prices.empty:
            raw_prices = raw_prices.drop_duplicates(["ts_code"], keep="last")

        # Build lookup
        limits = limit_data.set_index("ts_code")

        for idx, row in mask.iterrows():
            code = row["ts_code"]
            if code not in limits.index:
                continue

            lr = limits.loc[code]
            up_limit = lr["up_limit"] if "up_limit" in limits.columns else None
            down_limit = lr["down_limit"] if "down_limit" in limits.columns else None

            if up_limit is None or down_limit is None:
                continue

            # Get raw open from price data if available
            open_price = None
            if raw_prices is not None and not raw_prices.empty:
                price_row = raw_prices[raw_prices["ts_code"] == code]
                if not price_row.empty and "open" in price_row.columns:
                    open_price = price_row["open"].iloc[0]

            if open_price is not None:
                if open_price >= up_limit:
                    mask.at[idx, "is_limit_up_open"] = True
                    mask.at[idx, "can_buy"] = False
                    mask.at[idx, "reason"] += "limit_up_open; "

                if open_price <= down_limit:
                    mask.at[idx, "is_limit_down_open"] = True
                    mask.at[idx, "can_sell"] = False
                    mask.at[idx, "reason"] += "limit_down_open; "

    def _consolidate(self, mask: pd.DataFrame):
        """Consolidate can_hold: can hold if can_sell (can't do anything with suspended)."""
        mask["can_hold"] = mask["can_sell"].copy()
        # Clean up reason strings
        mask["reason"] = mask["reason"].str.rstrip("; ")

    # ------------------------------------------------------------------
    # Cache management
    # ------------------------------------------------------------------
    def _cache_mask(self, cache_key: tuple, mask: pd.DataFrame):
        """Cache mask for a (date, limit_check_mode) key (LRU-style eviction)."""
        if len(self._mask_cache) >= self.cache_size_limit:
            # Remove oldest entry (by insertion order in Python 3.7+)
            oldest = next(iter(self._mask_cache))
            del self._mask_cache[oldest]
        self._mask_cache[cache_key] = mask.copy()

    def _fetch_limit_data(self, ts_codes: List[str], date: int) -> Optional[pd.DataFrame]:
        """Auto-fetch stk_limit data for the given date and stocks."""
        try:
            from data.panel_loader import get_loader
            loader = get_loader()
            limit_data = loader.query_limit_data(str(date), ts_codes=ts_codes)
            if limit_data is not None and not limit_data.empty:
                return limit_data
        except Exception as e:
            logger.debug(f"Could not auto-fetch limit_data for {date}: {e}")

        # Fallback: try client directly
        try:
            date_str = str(date)
            limits = self.client.get_stk_limit(
                ts_code=",".join(ts_codes[:500]),
                trade_date=date_str
            )
            if limits is not None and not limits.empty:
                return limits
        except Exception as e:
            logger.debug(f"Client fallback for limit_data {date} failed: {e}")

        return None

    def _fetch_raw_open(self, ts_codes: List[str], date: int) -> Optional[pd.DataFrame]:
        """Auto-fetch raw open prices for the given date and stocks."""
        try:
            from data.panel_loader import get_loader
            loader = get_loader()
            prices = loader.query_prices(
                start_date=str(date), end_date=str(date),
                ts_codes=ts_codes,
                fields=["ts_code", "trade_date", "open"],
                price_type="raw"
            )
            if prices is not None and not prices.empty:
                return prices
        except Exception as e:
            logger.debug(f"Could not auto-fetch raw_prices for {date}: {e}")
        return None

    def clear_cache(self):
        """Clear the mask cache."""
        self._mask_cache.clear()

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    def mask_summary(self, mask: pd.DataFrame) -> Dict[str, int]:
        """Get summary counts from a mask DataFrame."""
        return {
            "total": len(mask),
            "can_buy": mask["can_buy"].sum(),
            "can_sell": mask["can_sell"].sum(),
            "can_hold": mask["can_hold"].sum(),
            "suspended": mask["is_suspended"].sum(),
            "limit_up": mask["is_limit_up_open"].sum(),
            "limit_down": mask["is_limit_down_open"].sum(),
            "st": mask["is_st"].sum(),
            "new_stock": mask["is_new_stock"].sum(),
        }


# ---------------------------------------------------------------------------
# Standalone helper: create tradable mask from data sources
# ---------------------------------------------------------------------------
def build_tradable_mask_for_date(date: int,
                                 ts_codes: List[str],
                                 suspend_records: pd.DataFrame,
                                 limit_data: pd.DataFrame,
                                 stock_basic: pd.DataFrame,
                                 st_set: Set[str],
                                 ipo_min_days: int = 60) -> pd.DataFrame:
    """
    Standalone function to build tradable mask without TradableMask class.

    Useful when all data is pre-loaded and you want a pure function.
    """
    tm = TradableMask()
    tm._suspend_records = suspend_records
    tm._stock_basic = stock_basic
    tm._st_flags = {date: st_set} if st_set else {}
    tm._list_dates = dict(zip(stock_basic["ts_code"], stock_basic["list_date"].astype(int)))
    tm._delist_dates = dict(zip(stock_basic["ts_code"], stock_basic["delist_date"].astype(int)))
    tm.ipo_min_days = ipo_min_days
    return tm.get_mask(ts_codes, date, limit_data=limit_data)


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
_tradable: Optional[TradableMask] = None


def get_tradable(**kwargs) -> TradableMask:
    """Get or create singleton TradableMask."""
    global _tradable
    if _tradable is None:
        _tradable = TradableMask(**kwargs)
    return _tradable

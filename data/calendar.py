"""
A-share trading calendar with date utilities.

Provides:
- Trading day sequences (from Tushare trade_cal)
- Weekly rebalance date generation
- Trade date offset functions (next_trade_day, prev_trade_day)
- Date range generation with business-day aware semantics

Memory: calendar is a small lookup table, cached as single parquet file.
All lookups are O(1) dict access after initial load.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, List, Set, Tuple
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class TradingCalendar:
    """
    A-share trading calendar.

    Caches trade dates from Tushare trade_cal API.
    Provides efficient date lookup and rebalance schedule generation.
    """

    def __init__(self, client=None):
        """
        Parameters
        ----------
        client : TushareClient, optional
            If None, will use singleton get_client().
        """
        self._client = client
        self._trade_dates: Optional[Set[int]] = None
        self._trade_dates_sorted: Optional[np.ndarray] = None
        self._date_to_idx: Optional[dict] = None
        self._cache_path = Path("data/parquet/trade_cal")

    @property
    def client(self):
        if self._client is None:
            from data.tushare_client import get_client
            self._client = get_client()
        return self._client

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------
    def load(self, start_date: str = "20150101", end_date: str = "20991231",
             force_reload: bool = False):
        """
        Load trading calendar into memory (small, ~5K dates for 20 years).

        IMPORTANT: This method uses UNION semantics — if the in-memory cache
        already covers a wider range than requested, it keeps the wider range.
        Calling load() with a narrow window will NEVER shrink the calendar.

        Parameters
        ----------
        start_date : str
            Start date YYYYMMDD.
        end_date : str
            End date YYYYMMDD.
        force_reload : bool
            If True, re-fetch from API even if cached.
        """
        req_min = int(start_date)
        req_max = int(end_date) if end_date else 20991231

        # 1. Check if in-memory cache already covers the range
        if self._trade_dates is not None and not force_reload:
            cached_min = int(self._trade_dates_sorted[0])
            cached_max = int(self._trade_dates_sorted[-1])
            if cached_min <= req_min and cached_max >= req_max:
                return  # already covered
            # In-memory cache is insufficient — expand to UNION rather than
            # shrinking. This prevents singleton pollution where a narrow
            # load() destroys a wide calendar.
            req_min = min(req_min, cached_min)
            req_max = max(req_max, cached_max)
            logger.debug(
                f"Calendar: expanding request to union [{req_min}, {req_max}] "
                f"(cache was [{cached_min}, {cached_max}])"
            )

        # 2. Try parquet cache (also with union semantics)
        cache_file = self._cache_path / "calendar.parquet"
        need_api_fetch = True
        df = pd.DataFrame()

        if cache_file.exists() and not force_reload:
            df = pd.read_parquet(cache_file)
            if not df.empty:
                cached_min = df["cal_date"].min()
                cached_max = df["cal_date"].max()
                if cached_min <= req_min and cached_max >= req_max:
                    need_api_fetch = False
                    logger.debug(f"Calendar cache hit: [{cached_min},{cached_max}]")
                else:
                    # Expand request to union with parquet cache
                    req_min = min(req_min, cached_min)
                    req_max = max(req_max, cached_max)
                    logger.info(f"Calendar cache [{cached_min},{cached_max}] "
                                f"insufficient, expanded request to "
                                f"[{req_min},{req_max}]")

        # 3. Fetch from API if needed (use expanded union range)
        if need_api_fetch:
            fetch_start = str(req_min)
            fetch_end = str(req_max)
            df = self.client.get_trade_cal(
                exchange="SSE",
                start_date=fetch_start,
                end_date=fetch_end,
                use_cache=not force_reload
            )
            if not df.empty:
                self._cache_path.mkdir(parents=True, exist_ok=True)
                df.to_parquet(cache_file, index=False)

        if df.empty:
            # If we have in-memory data already (partial coverage), keep it
            # rather than destroying what we have.  This prevents API
            # failures from shrinking the calendar to nothing.
            if self._trade_dates is not None:
                logger.warning(
                    "Failed to load expanded trading calendar — "
                    "keeping existing in-memory data"
                )
                return
            logger.error("Failed to load trading calendar")
            return

        # 4. Post-load validation: ensure loaded dates are within the requested range.
        #    If the cache or API returned wildly wrong dates, reject them.
        loaded_min = df["cal_date"].min()
        loaded_max = df["cal_date"].max()
        if loaded_min > req_max or loaded_max < req_min:
            logger.error(
                f"Trading calendar data mismatch: "
                f"loaded [{loaded_min}, {loaded_max}] but "
                f"requested [{req_min}, {req_max}]. "
                f"Clearing cache and retry with force_reload=True."
            )
            # Delete the bad cache and signal caller
            if cache_file.exists():
                cache_file.unlink()
            self._trade_dates = None
            self._trade_dates_sorted = None
            self._date_to_idx = None
            return

        if loaded_min > req_min + 700 or loaded_max < req_max - 700:
            logger.warning(
                f"Trading calendar: loaded [{loaded_min}, {loaded_max}] "
                f"partially covers [{req_min}, {req_max}] — "
                f"some dates at edges may be missing."
            )

        dates = set(df["cal_date"].astype(int).values)
        self._trade_dates = dates
        self._trade_dates_sorted = np.array(sorted(dates), dtype=np.int32)
        self._date_to_idx = {d: i for i, d in enumerate(self._trade_dates_sorted)}

        logger.info(f"Loaded {len(self._trade_dates)} trading days "
                     f"({self._trade_dates_sorted[0]} to {self._trade_dates_sorted[-1]})")

    @property
    def trade_dates(self) -> np.ndarray:
        """Return sorted array of all trading dates."""
        if self._trade_dates_sorted is None:
            self.load()
        return self._trade_dates_sorted

    def is_trade_day(self, date: int) -> bool:
        """Check if date is a trading day."""
        if self._trade_dates is None:
            self.load()
        return date in self._trade_dates

    def is_trade_day_str(self, date_str: str) -> bool:
        """Check if date string (YYYYMMDD) is a trading day."""
        return self.is_trade_day(int(date_str))

    # ------------------------------------------------------------------
    # Date navigation
    # ------------------------------------------------------------------
    def next_trade_day(self, date: int, n: int = 1) -> int:
        """Return the nth next trading day (n >= 1)."""
        if self._date_to_idx is None:
            self.load()
        idx = self._date_to_idx.get(date)
        if idx is None:
            # Find the first trade date >= this date
            pos = np.searchsorted(self._trade_dates_sorted, date)
            if pos >= len(self._trade_dates_sorted):
                return date
            idx = pos - 1  # searchsorted finds insertion point; back one
        new_idx = idx + n
        if new_idx < 0 or new_idx >= len(self._trade_dates_sorted):
            return date
        return int(self._trade_dates_sorted[new_idx])

    def prev_trade_day(self, date: int, n: int = 1) -> int:
        """Return the nth previous trading day (n >= 1)."""
        return self.next_trade_day(date, -n)

    def first_trade_day_on_or_after(self, date: int) -> int:
        """Return the first trading day >= date.

        If date itself is a trading day, returns date.
        If date is a non-trading day, returns the first trading day
        strictly greater than date.
        If no such trading day exists (date beyond the calendar), returns date
        unchanged — callers should treat this as NOT_AVAILABLE.

        This is the correct primitive for "signal date = first day you can
        legally trade after data becomes available".  Do NOT use
        next_trade_day(n=0) for this purpose — that method rounds *down*
        (to the previous trading day) for non-trading inputs.
        """
        if self._trade_dates_sorted is None:
            self.load()
        pos = np.searchsorted(self._trade_dates_sorted, date)
        if pos < len(self._trade_dates_sorted):
            return int(self._trade_dates_sorted[pos])
        return date

    def next_trade_day_str(self, date_str: str, n: int = 1) -> str:
        """Return the nth next trading day as YYYYMMDD string."""
        return str(self.next_trade_day(int(date_str), n))

    def prev_trade_day_str(self, date_str: str, n: int = 1) -> str:
        """Return the nth previous trading day as YYYYMMDD string."""
        return str(self.prev_trade_day(int(date_str), n))

    def trade_days_between(self, start: int, end: int) -> np.ndarray:
        """Return all trading days in [start, end]."""
        if self._trade_dates_sorted is None:
            self.load()
        mask = (self._trade_dates_sorted >= start) & (self._trade_dates_sorted <= end)
        return self._trade_dates_sorted[mask]

    def trade_days_in_range(self, start: str, end: str) -> np.ndarray:
        """Return all trading days in [start, end] as strings."""
        return self.trade_days_between(int(start), int(end))

    def count_trade_days(self, start: int, end: int) -> int:
        """Count trading days between two dates (inclusive)."""
        return len(self.trade_days_between(start, end))

    # ------------------------------------------------------------------
    # Rebalance schedule
    # ------------------------------------------------------------------
    def weekly_rebalance_dates(self, start_date: str, end_date: str,
                               weekday: int = 4) -> List[str]:
        """
        Generate weekly rebalance dates.

        Takes the last trading day of each week (default Friday).
        If Friday is a holiday, uses the previous trading day.

        Parameters
        ----------
        start_date : str
            Start date YYYYMMDD.
        end_date : str
            End date YYYYMMDD.
        weekday : int
            Target weekday (0=Mon, 4=Fri).

        Returns
        -------
        List of trade date strings.
        """
        if self._trade_dates_sorted is None:
            self.load()

        start = int(start_date)
        end = int(end_date)

        # Get all trading days in range
        mask = (self._trade_dates_sorted >= start) & (self._trade_dates_sorted <= end)
        all_dates = self._trade_dates_sorted[mask]

        if len(all_dates) == 0:
            return []

        # Group by ISO week and take the last trading day of each week
        result = []
        seen_weeks = set()

        for d in all_dates:
            d_str = str(d)
            dt = datetime.strptime(d_str, "%Y%m%d")
            iso_year, iso_week, iso_day = dt.isocalendar()

            week_key = (iso_year, iso_week)
            if week_key in seen_weeks:
                # Replace with later date in same week
                result[-1] = d_str
            else:
                seen_weeks.add(week_key)
                result.append(d_str)

        return result

    def monthly_rebalance_dates(self, start_date: str, end_date: str) -> List[str]:
        """
        Generate monthly rebalance dates.

        Returns the last trading day of each month.
        """
        if self._trade_dates_sorted is None:
            self.load()

        start = int(start_date)
        end = int(end_date)
        mask = (self._trade_dates_sorted >= start) & (self._trade_dates_sorted <= end)
        all_dates = self._trade_dates_sorted[mask]

        if len(all_dates) == 0:
            return []

        result = []
        seen_months = set()

        for d in all_dates:
            month_key = d // 100  # YYYYMM
            if month_key in seen_months:
                result[-1] = str(d)
            else:
                seen_months.add(month_key)
                result.append(str(d))

        return result


# ---------------------------------------------------------------------------
# Standalone date utilities (no API needed)
# ---------------------------------------------------------------------------
def int_to_datetime(date_int: int) -> datetime:
    """Convert YYYYMMDD int to datetime."""
    s = str(date_int)
    return datetime(int(s[:4]), int(s[4:6]), int(s[6:8]))


def datetime_to_int(dt: datetime) -> int:
    """Convert datetime to YYYYMMDD int."""
    return dt.year * 10000 + dt.month * 100 + dt.day


def date_range(start: str, end: str, freq: str = "W-FRI") -> List[str]:
    """Generate date range as YYYYMMDD strings."""
    dr = pd.date_range(start=start, end=end, freq=freq)
    return [d.strftime("%Y%m%d") for d in dr]


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
_calendar: Optional[TradingCalendar] = None


def get_calendar(**kwargs) -> TradingCalendar:
    """Get or create singleton TradingCalendar."""
    global _calendar
    if _calendar is None:
        _calendar = TradingCalendar(**kwargs)
    return _calendar

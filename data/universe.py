"""
Point-in-time (PIT) stock universe builder.

Builds the CSI 300 constituent universe for each signal date using:
- index_weight monthly snapshots (forward-filled to daily)
- stock_basic for list_date / delist_date
- namechange for ST/*ST history
- IPO window filter (default 60 days)

Key PIT rule: at signal_date t, the universe consists of stocks that:
1. Were in the latest index_weight snapshot on or before t
2. Are listed and not yet delisted at t
3. Have been listed for >= ipo_min_days calendar days
4. Are not ST/*ST (unless config allows)

Memory: universe is computed per date batch, never stored as full
(date x stock) wide matrix.
"""

import logging
from typing import Optional, List, Set, Dict, Tuple
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class UniverseBuilder:
    """
    PIT universe builder for CSI 300 constituents.

    Provides per-date universe with all filters applied.
    All lookups respect point-in-time availability.

    PIT rules for index_weight constituent snapshots:
    - snapshot_date: when the index_weight snapshot was taken (month-end)
    - effective_date: when the new weights take effect
    - available_date: when the data is actually knowable (snapshot_date + lag)
    - Universe uses available_date <= signal_date (NOT snapshot_date <= signal_date)
    """

    INDEX_CODE = "000300.SH"

    def __init__(self, client=None,
                 ipo_min_days: int = 60,
                 exclude_st: bool = True,
                 availability_lag_days: int = 1):
        self._client = client
        self.ipo_min_days = ipo_min_days
        self.exclude_st = exclude_st
        self.availability_lag_days = availability_lag_days

        # Cached data
        self._index_weight: Optional[pd.DataFrame] = None
        self._stock_basic: Optional[pd.DataFrame] = None
        self._st_history: Optional[pd.DataFrame] = None
        # ST periods: {ts_code: [(entry_date, exit_date), ...]}
        self._st_periods: Dict[str, List[Tuple[int, int]]] = {}

        # Derived
        # {snapshot_date: constituents_list} — raw snapshots without lag
        self._monthly_constituents: Optional[Dict[int, List[str]]] = None
        # {available_date: constituents_list} — lag-adjusted, PIT-safe
        self._available_constituents: Optional[Dict[int, List[str]]] = None
        # {snapshot_date: available_date} — mapping for diagnostics
        self._snapshot_to_available: Dict[int, int] = {}

    @property
    def client(self):
        if self._client is None:
            from data.tushare_client import get_client
            self._client = get_client()
        return self._client

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------
    def load(self, start_date: str = "20160101",
             end_date: Optional[str] = None,
             force_reload: bool = False):
        """
        Load all universe-relevant data.

        Parameters
        ----------
        start_date : str
            Earliest date for index_weight. 20160101 is the hard minimum
            for CSI 300 PIT constituents.
        end_date : str, optional
            Latest date. Defaults to today.
        force_reload : bool
            If True, skip cache.
        """
        if end_date is None:
            end_date = datetime.now().strftime("%Y%m%d")

        logger.info(f"Loading universe data: {start_date} -> {end_date}")

        # 1. Index weight (monthly snapshots) — with LOOKBACK
        # The user's start_date may be in the middle of a month. Per PIT rules,
        # the prior month-end snapshot becomes available on the first trade day
        # of the next month. So we must load at least one snapshot BEFORE the
        # user's start_date to ensure the available_date falls within range.
        # Lookback: 2 calendar months before start_date to be safe.
        data_start = (
            datetime.strptime(start_date, "%Y%m%d") - timedelta(days=62)
        ).strftime("%Y%m01")  # go back ~2 months, round to 1st
        # Clamp: minimum CSI 300 index_weight data starts 2016-01
        data_start = max(data_start, "20160101")

        self._index_weight = self.client.get_index_weight(
            index_code=self.INDEX_CODE,
            start_date=data_start,
            end_date=end_date,
            use_cache=not force_reload
        )
        if self._index_weight.empty:
            raise RuntimeError(
                f"No index_weight data for {self.INDEX_CODE}. "
                f"CSI 300 PIT data starts from 2016-01."
            )
        self._index_weight["trade_date"] = self._index_weight["trade_date"].astype("int32")
        self._index_weight["ts_code"] = self._index_weight["ts_code"].astype("category")
        logger.info(f"Loaded {len(self._index_weight)} index_weight records, "
                     f"{self._index_weight['trade_date'].nunique()} snapshots")

        # 2. Stock basic
        self._stock_basic = self.client.get_stock_basic(use_cache=not force_reload)
        if not self._stock_basic.empty:
            self._stock_basic["list_date"] = self._stock_basic["list_date"].astype("int32")
            self._stock_basic["delist_date"] = self._stock_basic["delist_date"].astype("int32")
            logger.info(f"Loaded {len(self._stock_basic)} stock basic records")

        # 3. ST history from namechange
        self._load_st_history(start_date, force_reload)

        # 4. Build monthly constituent lookup
        self._build_monthly_lookup()

        logger.info("Universe data loaded")

    def _load_st_history(self, start_date: str, force_reload: bool):
        """
        Extract ST flag history from namechange records.

        Builds ST periods per stock: [(entry_date, exit_date), ...].
        ST entry = namechange to "ST*" or "*ST*" name.
        ST exit = next namechange for same stock to non-ST name.
        If no exit record exists, ST extends to 20991231 (still ST).
        """
        nc = self.client.get_namechange(
            start_date=start_date,
            use_cache=not force_reload
        )
        if nc.empty:
            logger.warning("No namechange data; ST filter will be unavailable")
            self._st_history = pd.DataFrame()
            self._st_periods = {}  # ts_code -> [(entry_date, exit_date), ...]
            return

        nc = nc.sort_values(["ts_code", "start_date"])

        # Detect ST vs non-ST name patterns
        is_st = nc["name"].str.match(r"^\*?ST[^\x00-\x7F]", case=False, na=False)

        # Build ST periods per stock
        self._st_periods = {}
        for code, group in nc.groupby("ts_code"):
            periods = []
            st_entry = None
            for _, row in group.iterrows():
                if is_st.loc[row.name] and st_entry is None:
                    # Enter ST
                    st_entry = row["start_date"]
                elif not is_st.loc[row.name] and st_entry is not None:
                    # Exit ST (name changed back to normal)
                    periods.append((int(st_entry), int(row["start_date"])))
                    st_entry = None
            # Still in ST at end of records
            if st_entry is not None:
                periods.append((int(st_entry), 20991231))
            if periods:
                self._st_periods[code] = periods

        logger.info(f"Extracted ST periods for {len(self._st_periods)} stocks "
                     f"({sum(len(p) for p in self._st_periods.values())} episodes)")

    def _build_monthly_lookup(self):
        """
        Build monthly constituent lookup with PIT availability dates.

        Each snapshot_date gets an available_date = snapshot + lag days,
        adjusted to the next TRADING day. Uses the trading calendar to
        ensure available_date is always a valid trade date.
        """
        if self._index_weight is None or self._index_weight.empty:
            self._monthly_constituents = {}
            self._available_constituents = {}
            return

        iw = self._index_weight.copy()
        monthly = iw.groupby("trade_date")["ts_code"].apply(list).to_dict()
        self._monthly_constituents = monthly

        # Build available_date mapping
        self._snapshot_to_available = {}
        self._available_constituents = {}

        # Determine date range for calendar load
        snap_dates = sorted(monthly.keys())
        min_snap = min(snap_dates)
        max_snap = max(snap_dates)

        # Try loading trading calendar
        cal_ok = False
        cal = None
        try:
            from data.calendar import get_calendar
            cal = get_calendar()
            # Explicitly load calendar for the needed range
            cal.load(start_date=str(min_snap), end_date=str(max_snap + 10))
            cal_ok = cal._trade_dates_sorted is not None and len(cal.trade_dates) > 0
        except Exception as e:
            logger.warning(
                f"Trading calendar unavailable for PIT universe: {e}. "
                f"available_date will use pd.Timestamp arithmetic "
                f"(safe but may not align to A-share holidays)."
            )

        for snapshot_date in snap_dates:
            if cal_ok and cal is not None:
                # Use trading calendar: next trade day >= snapshot + lag
                try:
                    avail = cal.next_trade_day(
                        snapshot_date, self.availability_lag_days
                    )
                except Exception:
                    # Fallback: use pd.Timestamp arithmetic (safe, no simple int addition)
                    avail = int(
                        (pd.Timestamp(str(snapshot_date))
                         + pd.Timedelta(days=self.availability_lag_days))
                        .strftime("%Y%m%d")
                    )
            else:
                # Calendar unavailable — use pd.Timestamp (safe)
                avail = int(
                    (pd.Timestamp(str(snapshot_date))
                     + pd.Timedelta(days=self.availability_lag_days))
                    .strftime("%Y%m%d")
                )

            # Validate: available_date must be a real calendar date
            try:
                datetime.strptime(str(avail), "%Y%m%d")
            except ValueError:
                logger.error(
                    f"Invalid available_date {avail} for snapshot {snapshot_date} "
                    f"— falling back to simple next-day. "
                    f"This should NOT happen with pd.Timestamp arithmetic."
                )
                avail = snapshot_date + self.availability_lag_days

            self._snapshot_to_available[snapshot_date] = avail
            self._available_constituents[avail] = monthly[snapshot_date]

        logger.info(
            f"Built PIT universe lookup: {len(monthly)} snapshots, "
            f"{len(self._available_constituents)} available-date entries "
            f"(lag={self.availability_lag_days}d, calendar={'ok' if cal_ok else 'fallback'})"
        )

    # ------------------------------------------------------------------
    # Per-date universe query
    # ------------------------------------------------------------------
    def get_universe(self, date: int) -> List[str]:
        """
        Get PIT universe for a single date.

        Parameters
        ----------
        date : int
            Trade date as YYYYMMDD int.

        Returns
        -------
        List of ts_code strings that are valid constituents on this date.
        """
        if self._monthly_constituents is None:
            raise RuntimeError("Universe not loaded. Call load() first.")

        # 1. Get latest index_weight snapshot <= date
        constituents = self._get_constituents_at_date(date)

        if not constituents:
            return []

        # 2. Filter by listing status
        if self._stock_basic is not None and not self._stock_basic.empty:
            constituents = self._filter_listing_status(constituents, date)

        # 3. Filter IPO window
        constituents = self._filter_ipo_window(constituents, date)

        # 4. Filter ST
        if self.exclude_st:
            constituents = self._filter_st(constituents, date)

        return constituents

    def get_universe_str(self, date_str: str) -> List[str]:
        """Get PIT universe for a date string YYYYMMDD."""
        return self.get_universe(int(date_str))

    def get_universe_batch(self, dates: List[int]) -> Dict[int, List[str]]:
        """
        Get universe for multiple dates efficiently.

        Returns dict[date_int] -> list of ts_code.
        Does NOT construct a full date x stock matrix.
        """
        result = {}
        for d in dates:
            result[d] = self.get_universe(d)
        return result

    # ------------------------------------------------------------------
    # Internal filters
    # ------------------------------------------------------------------
    def _get_constituents_at_date(self, date: int) -> List[str]:
        """
        Get index_weight constituents available at the query date.

        Uses available_date (snapshot_date + lag) <= query_date,
        NOT snapshot_date <= query_date. This enforces the PIT rule
        that a month-end snapshot is NOT usable on its own date.
        """
        if not self._monthly_constituents:
            return []

        if self._available_constituents and self._snapshot_to_available:
            # Use PIT-aware available_date lookup
            available_dates = sorted(self._available_constituents.keys())
            eligible = [d for d in available_dates if d <= date]
            if not eligible:
                return []
            latest_available = eligible[-1]
            return list(self._available_constituents[latest_available])

        # Fallback: use raw snapshot dates (backward compat)
        snapshot_dates = sorted(self._monthly_constituents.keys())
        eligible = [d for d in snapshot_dates if d <= date]
        if not eligible:
            return []

        latest_snapshot = eligible[-1]
        return list(self._monthly_constituents[latest_snapshot])

    def _filter_listing_status(self, codes: List[str], date: int) -> List[str]:
        """Remove stocks not yet listed or already delisted at date."""
        sb = self._stock_basic
        # Ensure ts_code is a column, not the index
        if "ts_code" not in sb.columns:
            sb = sb.reset_index()
        sb_lookup = sb.set_index("ts_code")

        result = []
        for c in codes:
            if c not in sb_lookup.index:
                continue
            info = sb_lookup.loc[c]

            # Handle potential DataFrame (duplicate index) or Series
            if isinstance(info, pd.DataFrame):
                info = info.iloc[0]

            try:
                list_date = info["list_date"]
                delist_date = info["delist_date"]
            except (KeyError, TypeError):
                continue

            # Handle Series (in case of duplicate entries)
            if isinstance(list_date, pd.Series):
                list_date = list_date.iloc[0]
            if isinstance(delist_date, pd.Series):
                delist_date = delist_date.iloc[0]

            # Convert to Python int for safe comparison
            try:
                list_date = int(list_date)
                delist_date = int(delist_date)
            except (ValueError, TypeError):
                continue

            if list_date <= date < delist_date:
                result.append(c)

        return result

    def _filter_ipo_window(self, codes: List[str], date: int) -> List[str]:
        """Remove stocks listed fewer than ipo_min_days calendar days ago."""
        if self.ipo_min_days <= 0:
            return codes

        sb = self._stock_basic
        sb_lookup = sb.set_index("ts_code")

        # Calculate minimum list date
        dt = datetime.strptime(str(date), "%Y%m%d")
        min_list_dt = dt - timedelta(days=self.ipo_min_days)
        min_list_date = int(min_list_dt.strftime("%Y%m%d"))

        result = []
        for c in codes:
            if c not in sb_lookup.index:
                continue
            info = sb_lookup.loc[c]
            list_date = info["list_date"]
            if isinstance(list_date, pd.Series):
                list_date = list_date.iloc[0]
            if list_date <= min_list_date:
                result.append(c)

        return result

    def _filter_st(self, codes: List[str], date: int) -> List[str]:
        """
        Remove ST/*ST stocks based on ST periods.

        A stock is ST at `date` if any ST period covers this date.
        ST exit (摘帽) is properly handled.
        """
        if not self._st_periods:
            # Without ST data, fall back to name-based check
            return self._filter_st_by_name(codes)

        result = []
        for c in codes:
            is_st_now = False
            periods = self._st_periods.get(c, [])
            for entry, exit_ in periods:
                if entry <= date < exit_:
                    is_st_now = True
                    break
            if not is_st_now:
                result.append(c)

        return result

    def _filter_st_by_name(self, codes: List[str]) -> List[str]:
        """
        Fallback ST filter using stock_basic name field.

        A-share ST stocks have names like 'ST凯乐' or '*ST华泽' where
        'ST'/'*ST' is followed by Chinese characters, not Latin letters.
        """
        import re
        sb = self._stock_basic
        if sb is None or sb.empty:
            return codes
        sb_lookup = sb.set_index("ts_code")
        # ST prefix followed by non-ASCII (Chinese) character
        st_pattern = re.compile(r'^\*?ST[^\x00-\x7F]')
        result = []
        for c in codes:
            if c not in sb_lookup.index:
                result.append(c)
                continue
            name = sb_lookup.loc[c, "name"]
            if isinstance(name, pd.Series):
                name = name.iloc[0]
            name_str = str(name).strip()
            if not st_pattern.match(name_str):
                result.append(c)
        return result

    # ------------------------------------------------------------------
    # Universe diagnostics
    # ------------------------------------------------------------------
    def constituent_count_history(self, start_date: str, end_date: str) -> pd.DataFrame:
        """Get time series of constituent counts for diagnostics."""
        from data.calendar import get_calendar
        cal = get_calendar()

        dates = cal.trade_days_between(int(start_date), int(end_date))
        records = []
        for d in dates[::5]:  # Sample every 5 trading days for speed
            univ = self.get_universe(int(d))
            records.append({"trade_date": d, "n_stocks": len(univ)})

        return pd.DataFrame(records)

    def sample_universe_check(self, n_samples: int = 20) -> pd.DataFrame:
        """
        Randomly sample N rebalance dates and verify:
        - No future constituents (constituents from later index_weight snapshots
          not appearing in the current snapshot)
        - Reasonable stock count (~280-310 for CSI 300)

        Returns DataFrame with diagnostic info.
        """
        if not self._monthly_constituents:
            return pd.DataFrame()

        from data.calendar import get_calendar
        cal = get_calendar()

        snapshot_dates = sorted(self._monthly_constituents.keys())
        if len(snapshot_dates) < n_samples:
            n_samples = len(snapshot_dates)

        # Pick random snapshot dates
        rng = np.random.default_rng(42)
        sampled = list(rng.choice(snapshot_dates, size=n_samples, replace=False))
        sampled.sort()

        results = []
        for d in sampled:
            univ = self.get_universe(d)
            # Check forward: are there constituents from future snapshots in this universe?
            future_dates = [fd for fd in snapshot_dates if fd > d]
            future_stocks = set()
            for fd in future_dates[:3]:  # Check next 3 snapshots
                future_stocks.update(self._monthly_constituents.get(fd, []))

            univ_set = set(univ)
            future_intrusion = univ_set - future_stocks

            results.append({
                "trade_date": d,
                "n_stocks": len(univ),
                "future_intrusion_count": len(future_intrusion),
                "status": "OK" if 250 <= len(univ) <= 320 else "WARN",
            })

        return pd.DataFrame(results)


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
_universe: Optional[UniverseBuilder] = None


def get_universe_builder(**kwargs) -> UniverseBuilder:
    """Get or create singleton UniverseBuilder."""
    global _universe
    if _universe is None:
        _universe = UniverseBuilder(**kwargs)
    return _universe

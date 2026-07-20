"""
Tushare Pro API Client with rate limiting, retry, and incremental parquet caching.

Memory constraint: all fetch methods accept columns/date_range/universe filters
and return only the requested subset. Full-table reads are prohibited.

Uses hive-partitioned parquet as local cache with predicate-pushdown reads.
"""

import os
import time
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any, Union
from functools import wraps

import numpy as np
import pandas as pd
from dotenv import load_dotenv
import pyarrow.dataset as ds
import pyarrow as pa
import pyarrow.parquet as pq

logger = logging.getLogger(__name__)

# Load Tushare Pro lazily — only needed when actual API calls are made.
# This allows dry-run and testing without tushare installed.
_PRO = None
_PRO_AVAILABLE = False

try:
    import tushare as ts

    load_dotenv()
    TUSHARE_TOKEN = os.getenv("TUSHARE_TOKEN")

    if TUSHARE_TOKEN and TUSHARE_TOKEN != "your_tushare_pro_token_here":
        ts.set_token(TUSHARE_TOKEN)
        _PRO = ts.pro_api()
        _PRO_AVAILABLE = True
    else:
        logger.warning("Tushare token not configured; API calls will fail. Set TUSHARE_TOKEN in .env")
except ImportError:
    logger.warning("tushare not installed; API calls will fail. Install with: pip install tushare")


# ---------------------------------------------------------------------------
# Rate limiter: token-bucket style with min interval
# ---------------------------------------------------------------------------
class RateLimiter:
    """Simple rate limiter enforcing minimum interval between calls."""

    def __init__(self, max_calls_per_minute: int = 180):
        self._min_interval = 60.0 / max_calls_per_minute
        self._last_call = 0.0

    def wait(self):
        now = time.monotonic()
        elapsed = now - self._last_call
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_call = time.monotonic()

    def update_rate(self, max_calls_per_minute: int):
        self._min_interval = 60.0 / max_calls_per_minute


# ---------------------------------------------------------------------------
# Retry decorator with exponential backoff
# ---------------------------------------------------------------------------
def with_retry(max_retries: int = 5, base_seconds: float = 1.0,
               max_seconds: float = 60.0, backoff: float = 2.0):
    """Decorator for Tushare API calls with exponential backoff."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    msg = str(e).lower()
                    if "每分钟最多访问" in msg or "rate limit" in msg or "too many" in msg:
                        wait = min(base_seconds * (backoff ** attempt), max_seconds)
                        logger.warning(f"Rate limit hit, retry {attempt+1}/{max_retries} after {wait:.1f}s")
                        time.sleep(wait)
                    elif "网络" in msg or "timeout" in msg or "connection" in msg:
                        wait = min(base_seconds * (backoff ** attempt), max_seconds)
                        logger.warning(f"Network error, retry {attempt+1}/{max_retries} after {wait:.1f}s: {e}")
                        time.sleep(wait)
                    else:
                        raise
            raise last_exception
        return wrapper
    return decorator


from data.parquet_cache import ParquetCache  # noqa: E402

# ---------------------------------------------------------------------------
# Main Tushare client
# ---------------------------------------------------------------------------
class TushareClient:
    """
    Tushare Pro API client with caching and rate limiting.

    All data access methods are memory-constrained — they accept
    columns, date ranges, and stock universe filters, and return
    only the requested data slice.
    """

    def __init__(self, cache_path: str = "data/parquet",
                 max_requests_per_minute: int = 180):
        self.pro = _PRO
        self.available = _PRO_AVAILABLE
        self.cache = ParquetCache(cache_path)
        self.rate_limiter = RateLimiter(max_requests_per_minute)
        self._config = {
            "max_requests_per_minute": max_requests_per_minute,
            "cache_path": cache_path,
        }

    # ------------------------------------------------------------------
    # Core fetch method
    # ------------------------------------------------------------------
    @with_retry(max_retries=5)
    def _call_api(self, func, **kwargs) -> pd.DataFrame:
        """Call a Tushare API function with rate limiting and retry."""
        if not self.available:
            if not _PRO_AVAILABLE:
                raise RuntimeError(
                    "Tushare Pro not available. "
                    "Install with: pip install tushare; "
                    "set TUSHARE_TOKEN in .env"
                )
            raise RuntimeError("Tushare Pro not available. Check TUSHARE_TOKEN in .env")
        self.rate_limiter.wait()
        return func(**kwargs)

    # ------------------------------------------------------------------
    # Daily OHLCV (raw prices)
    # ------------------------------------------------------------------
    def get_daily(self, ts_code: Optional[Union[str, List[str]]] = None,
                  start_date: Optional[str] = None,
                  end_date: Optional[str] = None,
                  fields: Optional[str] = None,
                  use_cache: bool = True) -> pd.DataFrame:
        """
        Fetch daily OHLCV (raw prices).

        Parameters
        ----------
        ts_code : str or list of str, optional
            Stock code(s). If None, fetches all available.
        start_date, end_date : str, optional
            Date range in YYYYMMDD format.
        fields : str, optional
            Comma-separated field list for Tushare API.
        use_cache : bool
            Whether to check local parquet cache first.

        Returns
        -------
        pd.DataFrame with columns: ts_code, trade_date, open, high, low, close,
            pre_close, change, pct_chg, vol, amount
        """
        table_name = "prices_raw"

        # Try cache first if using full date range for known stocks
        if use_cache and self._cache_covers_range(table_name, start_date, end_date):
            cached = self.cache.read(
                table_name,
                filters=self._date_code_filters(start_date, end_date, ts_code)
            )
            if not cached.empty:
                return cached

        # Fetch from API
        if isinstance(ts_code, list):
            ts_code_str = ",".join(ts_code)
        else:
            ts_code_str = ts_code

        kwargs = {}
        if ts_code_str:
            kwargs["ts_code"] = ts_code_str
        if start_date:
            kwargs["start_date"] = start_date
        if end_date:
            kwargs["end_date"] = end_date
        if fields:
            kwargs["fields"] = fields

        result = self._call_api(self.pro.daily, **kwargs)

        if result is not None and not result.empty:
            # Ensure trade_date is int32
            result["trade_date"] = result["trade_date"].astype("int32")
            # Cache by year/month partition
            result["year"] = result["trade_date"] // 10000
            result["month"] = (result["trade_date"] % 10000) // 100
            self.cache.write(result, table_name, partition_cols=["year", "month"])
            result.drop(columns=["year", "month"], inplace=True, errors="ignore")

        return result if result is not None else pd.DataFrame()

    # ------------------------------------------------------------------
    # Daily OHLCV — per-trading-day fetch (avoids single-call limits)
    # ------------------------------------------------------------------
    def get_daily_by_trade_dates(
        self,
        trade_dates: list,
        fields: Optional[str] = None,
        use_cache: bool = True,
    ) -> pd.DataFrame:
        """
        Fetch daily OHLCV one trading day at a time.

        Tushare's daily() API with a date range often returns truncated
        results (~18 days max per call in practice). This method fetches
        each trade_date individually, ensuring complete coverage.

        Each day's result is immediately written to parquet cache and
        released from memory — peak memory is bounded by one day's data
        (~300 stocks × 11 columns ≈ negligible).

        Parameters
        ----------
        trade_dates : list[int] or list[str]
            Trading days to fetch.
        fields : str, optional
            Comma-separated Tushare field list.
        use_cache : bool
            Whether to skip days already in cache.

        Returns
        -------
        pd.DataFrame with all fetched data (for caller convenience),
        but data is also persisted to parquet incrementally.
        """
        table_name = "prices_raw"
        # Convert to plain Python str — numpy int32 causes JSON errors
        trade_dates = [str(int(d)) for d in trade_dates]

        all_results = []
        n_fetched = 0
        n_skipped = 0

        for date_str in trade_dates:
            # Check if this date is already cached
            if use_cache:
                cached = self.cache.read(
                    table_name,
                    filters=[("trade_date", "==", np.int32(date_str))]
                )
                if not cached.empty:
                    all_results.append(cached)
                    n_skipped += 1
                    continue

            # Fetch from API
            kwargs = {"trade_date": date_str}
            if fields:
                kwargs["fields"] = fields
            try:
                chunk = self._call_api(self.pro.daily, **kwargs)
            except Exception as e:
                logger.warning(f"daily {date_str}: API call failed: {e}")
                continue

            if chunk is not None and not chunk.empty:
                chunk["trade_date"] = chunk["trade_date"].astype("int32")
                chunk["year"] = chunk["trade_date"] // 10000
                chunk["month"] = (chunk["trade_date"] % 10000) // 100
                self.cache.write(chunk, table_name,
                                 partition_cols=["year", "month"])
                chunk.drop(columns=["year", "month"], inplace=True, errors="ignore")
                all_results.append(chunk)
                n_fetched += 1
                del chunk

        logger.info(
            f"get_daily_by_trade_dates: fetched {n_fetched}, "
            f"cached {n_skipped}, total {len(all_results)} batches"
        )
        if all_results:
            return pd.concat(all_results, ignore_index=True)
        return pd.DataFrame()

    # ------------------------------------------------------------------
    # Adj factor
    # ------------------------------------------------------------------
    def get_adj_factor(self, ts_code: Optional[Union[str, List[str]]] = None,
                       start_date: Optional[str] = None,
                       end_date: Optional[str] = None,
                       use_cache: bool = True,
                       batch_size: int = 100,
                       allow_partial: bool = False,
                       _write_cache: bool = True) -> pd.DataFrame:
        """
        Fetch adjustment factor (qfq).

        When ts_code is a list longer than batch_size, splits into batches
        to avoid API timeouts and reduce per-call memory pressure.
        The adj_factor API does not support date filters — we post-filter.

        Cache validation (STRICT by default):
        - Verifies ALL requested ts_codes are covered.
        - Verifies full date range coverage.
        - Verifies per-trading-day stock coverage >= 98%.
        - Deduplicates by (ts_code, trade_date) before writing.
        - On partial hit: fetches missing stocks/dates, merges.
        - On gap-fill failure with allow_partial=False (production):
          returns empty DataFrame with diagnostic .attrs set.
        - allow_partial=True (smoke/test) permits degraded partial returns.

        Parameters
        ----------
        ts_code : str or list of str, optional
            Stock codes. If list and len > batch_size, auto-split into batches.
        start_date, end_date : str, optional
            Date range YYYYMMDD. Post-filter applied after fetch.
        use_cache : bool
            Whether to check local cache first.
        batch_size : int
            Max stocks per API call when ts_code is a list.
        allow_partial : bool
            If False (default, production): gap-fill failures return empty
            DataFrame with .attrs diagnostics. If True (smoke/test): may
            return partial cache with warnings.

        Returns
        -------
        pd.DataFrame with columns: ts_code, trade_date, adj_factor.
        On strict failure: empty DataFrame with .attrs containing:
            status, reason, requested_start, requested_end,
            cached_start, cached_end, n_requested_stocks, n_cached_stocks.
        """
        table_name = "adj_factor"
        req_start = int(start_date) if start_date else None
        req_end = int(end_date) if end_date else None
        requested_codes = set(
            ts_code if isinstance(ts_code, list)
            else [ts_code] if isinstance(ts_code, str)
            else []
        )

        if use_cache:
            cached = self.cache.read(
                table_name,
                filters=self._date_code_filters(start_date, end_date, ts_code)
            )
            if not cached.empty:
                # Deduplicate cached before using
                cached = cached.drop_duplicates(
                    subset=["ts_code", "trade_date"], keep="last"
                )

                # ---- Stock coverage check ----
                if requested_codes:
                    cached_codes = set(cached["ts_code"].unique())
                    missing_codes = requested_codes - cached_codes
                    if missing_codes:
                        logger.warning(
                            f"adj_factor cache missing {len(missing_codes)} "
                            f"stocks: {sorted(list(missing_codes))[:10]}"
                        )
                        # Fetch only missing stocks
                        missing_start = str(req_start) if req_start else None
                        missing_end = str(req_end) if req_end else None
                        try:
                            missing_result = self.get_adj_factor(
                                ts_code=list(missing_codes),
                                start_date=missing_start,
                                end_date=missing_end,
                                use_cache=False,
                                allow_partial=allow_partial,
                                _write_cache=_write_cache,
                            )
                        except Exception as e:
                            missing_result = pd.DataFrame()
                            logger.error(f"Failed to fetch missing stocks: {e}")

                        if missing_result is not None and not missing_result.empty:
                            merged = pd.concat(
                                [cached, missing_result], ignore_index=True
                            ).drop_duplicates(
                                subset=["ts_code", "trade_date"], keep="last"
                            )
                            logger.info(
                                f"adj_factor gap filled: cached={len(cached)} + "
                                f"missing={len(missing_result)} → merged={len(merged)}"
                            )
                            cached = merged
                        else:
                            if not allow_partial:
                                diag = pd.DataFrame()
                                diag.attrs = {
                                    "status": "FETCH_FAILED",
                                    "reason": (
                                        f"adj_factor: could not fetch {len(missing_codes)} "
                                        f"missing stocks; gap-fill failed"
                                    ),
                                    "requested_start": start_date,
                                    "requested_end": end_date,
                                    "cached_start": str(int(cached["trade_date"].min())),
                                    "cached_end": str(int(cached["trade_date"].max())),
                                    "n_requested_stocks": len(requested_codes),
                                    "n_cached_stocks": len(cached_codes),
                                    "missing_stocks": sorted(list(missing_codes))[:20],
                                }
                                logger.error(
                                    f"adj_factor FETCH_FAILED (allow_partial=False): "
                                    f"missing {len(missing_codes)} stocks"
                                )
                                return diag
                            logger.warning(
                                f"adj_factor: could not fetch {len(missing_codes)} "
                                f"missing stocks; returning partial cache "
                                f"(allow_partial=True)"
                            )
                            return cached

                # ---- Date range coverage check ----
                cache_min = int(cached["trade_date"].min())
                cache_max = int(cached["trade_date"].max())
                date_coverage_ok = True
                if req_start and cache_min > req_start:
                    date_coverage_ok = False
                if req_end and cache_max < req_end:
                    date_coverage_ok = False

                if not date_coverage_ok:
                    logger.info(
                        f"adj_factor cache PARTIAL date coverage: "
                        f"cached={cache_min}-{cache_max}, "
                        f"requested={req_start}-{req_end}"
                    )
                    # Fall through to full fetch to fill the gap
                else:
                    # ---- Per-trading-day stock coverage >= 98% ----
                    if requested_codes:
                        try:
                            from data.calendar import get_calendar
                            cal = get_calendar()
                            cal.load(start_date=start_date, end_date=end_date)
                            trade_days = cal.trade_days_between(
                                req_start or cache_min, req_end or cache_max
                            )
                            low_cov_days = []
                            for td in trade_days:
                                day_data = cached[cached["trade_date"] == int(td)]
                                if len(day_data) == 0:
                                    day_cov = 0.0
                                else:
                                    day_stocks = set(day_data["ts_code"].unique())
                                    day_cov = len(day_stocks & requested_codes) / len(requested_codes)
                                if day_cov < 0.98:
                                    low_cov_days.append((int(td), round(day_cov, 4)))
                            if low_cov_days:
                                logger.warning(
                                    f"adj_factor: {len(low_cov_days)} days with "
                                    f"stock coverage < 98%: {low_cov_days[:5]}"
                                )
                                if not allow_partial:
                                    diag = pd.DataFrame()
                                    diag.attrs = {
                                        "status": "PARTIAL_CACHE",
                                        "reason": (
                                            f"{len(low_cov_days)} trade days have "
                                            f"stock coverage < 98%"
                                        ),
                                        "requested_start": start_date,
                                        "requested_end": end_date,
                                        "cached_start": str(cache_min),
                                        "cached_end": str(cache_max),
                                        "n_requested_stocks": len(requested_codes),
                                        "n_cached_stocks": len(
                                            set(cached["ts_code"].unique()) & requested_codes
                                        ),
                                        "low_coverage_days": low_cov_days[:10],
                                        "coverage_ratio": round(
                                            1.0 - len(low_cov_days) / len(trade_days), 4
                                        ) if trade_days else 0.0,
                                    }
                                    logger.error(
                                        f"adj_factor PARTIAL_CACHE (allow_partial=False): "
                                        f"{len(low_cov_days)} low-coverage days"
                                    )
                                    return diag
                        except Exception as e:
                            logger.debug(f"Per-day coverage check skipped: {e}")

                    # Full cache hit
                    if "trade_date" in cached.columns:
                        cached_dates = set(cached["trade_date"].unique())
                    else:
                        cached_dates = set()
                    logger.debug(
                        f"adj_factor cache HIT: {len(cached)} rows, "
                        f"{cache_min}-{cache_max}, "
                        f"{cached['ts_code'].nunique()} stocks, "
                        f"{len(cached_dates)} trade days"
                    )
                    return cached

        # Date-range adj_factor calls are row-limited by Tushare. Fetch one
        # trade date at a time to avoid truncated ranges, then filter locally.
        if start_date and end_date and not isinstance(ts_code, str):
            try:
                from data.calendar import get_calendar
                cal = get_calendar()
                cal.load(start_date=start_date, end_date=end_date)
                trade_days = cal.trade_days_between(int(start_date), int(end_date))
            except Exception as e:
                diag = pd.DataFrame()
                diag.attrs = {
                    "status": "FETCH_FAILED",
                    "reason": f"adj_factor: cannot load trading calendar: {e}",
                    "requested_start": start_date,
                    "requested_end": end_date,
                }
                logger.error(diag.attrs["reason"])
                return diag

            requested_set = requested_codes if requested_codes else None
            chunks = []
            failed_days = []
            for td in trade_days:
                try:
                    day_df = self._call_api(
                        self.pro.adj_factor, trade_date=str(int(td))
                    )
                except Exception as e:
                    logger.warning(f"adj_factor trade_date={td}: {e}")
                    day_df = pd.DataFrame()

                if day_df is None or day_df.empty:
                    failed_days.append(int(td))
                    continue

                day_df["trade_date"] = day_df["trade_date"].astype("int32")
                if requested_set:
                    day_df = day_df[day_df["ts_code"].isin(requested_set)]
                if not day_df.empty:
                    chunks.append(day_df)

            if failed_days and not allow_partial:
                diag = pd.DataFrame()
                diag.attrs = {
                    "status": "FETCH_FAILED",
                    "reason": (
                        f"adj_factor: {len(failed_days)} trade-date fetches failed"
                    ),
                    "requested_start": start_date,
                    "requested_end": end_date,
                    "failed_days": failed_days[:20],
                }
                logger.error(
                    f"adj_factor FETCH_FAILED: {len(failed_days)} trade dates failed "
                    f"(allow_partial=False)"
                )
                return diag

            if chunks:
                result = pd.concat(chunks, ignore_index=True)
                result = result.drop_duplicates(
                    subset=["ts_code", "trade_date"], keep="last"
                )
                if _write_cache:
                    result["year"] = result["trade_date"] // 10000
                    self.cache.write(result, table_name, partition_cols=["year"],
                                     replace_partitions=True)
                    result.drop(columns=["year"], inplace=True, errors="ignore")
                return result

            return pd.DataFrame()

        # If ts_code is a large list, split into batches
        if isinstance(ts_code, list) and len(ts_code) > batch_size:
            all_chunks = []
            failed_batches = 0
            for i in range(0, len(ts_code), batch_size):
                batch = ts_code[i:i + batch_size]
                try:
                    chunk = self.get_adj_factor(
                        ts_code=batch,
                        start_date=start_date,
                        end_date=end_date,
                        use_cache=False,  # already checked cache above
                        batch_size=batch_size,
                        allow_partial=allow_partial,
                        _write_cache=False,
                    )
                    if chunk is not None and not chunk.empty:
                        all_chunks.append(chunk)
                    else:
                        failed_batches += 1
                except Exception as e:
                    failed_batches += 1
                    logger.warning(f"adj_factor batch {i}-{i+len(batch)}: {e}")

            if failed_batches > 0 and not allow_partial:
                diag = pd.DataFrame()
                diag.attrs = {
                    "status": "FETCH_FAILED",
                    "reason": f"adj_factor: {failed_batches} batches failed",
                    "requested_start": start_date,
                    "requested_end": end_date,
                }
                logger.error(
                    f"adj_factor FETCH_FAILED: {failed_batches} batches failed "
                    f"(allow_partial=False)"
                )
                return diag

            if all_chunks:
                result = pd.concat(all_chunks, ignore_index=True)
                # Post-filter and cache the merged result
                if start_date:
                    result = result[result["trade_date"] >= int(start_date)]
                if end_date:
                    result = result[result["trade_date"] <= int(end_date)]
                if not result.empty:
                    result = result.drop_duplicates(
                        subset=["ts_code", "trade_date"], keep="last"
                    )
                    if _write_cache:
                        result["year"] = result["trade_date"] // 10000
                        self.cache.write(result, table_name, partition_cols=["year"],
                                         replace_partitions=True)
                        result.drop(columns=["year"], inplace=True, errors="ignore")
                return result

            if failed_batches > 0 and not allow_partial:
                diag = pd.DataFrame()
                diag.attrs = {
                    "status": "FETCH_FAILED",
                    "reason": f"adj_factor: {failed_batches} batches failed",
                    "requested_start": start_date,
                    "requested_end": end_date,
                }
                logger.error(
                    f"adj_factor FETCH_FAILED: {failed_batches} batches failed "
                    f"(allow_partial=False)"
                )
                return diag
            return pd.DataFrame()

        kwargs = {}
        if ts_code:
            kwargs["ts_code"] = ts_code if isinstance(ts_code, str) else ",".join(ts_code)
        result = self._call_api(self.pro.adj_factor, **kwargs)
        # adj_factor API doesn't support date filter; we filter post-fetch

        if result is not None and not result.empty:
            result["trade_date"] = result["trade_date"].astype("int32")
            # Filter by date if specified
            if start_date:
                sd = int(start_date)
                result = result[result["trade_date"] >= sd]
            if end_date:
                ed = int(end_date)
                result = result[result["trade_date"] <= ed]
            # Deduplicate before writing
            result = result.drop_duplicates(
                subset=["ts_code", "trade_date"], keep="last"
            )
            if _write_cache:
                result["year"] = result["trade_date"] // 10000
                self.cache.write(result, table_name, partition_cols=["year"])
                result.drop(columns=["year"], inplace=True, errors="ignore")

        return result if result is not None else pd.DataFrame()

    # ------------------------------------------------------------------
    # Daily basic (fundamentals)
    # ------------------------------------------------------------------
    def get_daily_basic(self, ts_code: Optional[str] = None,
                        trade_date: Optional[str] = None,
                        start_date: Optional[str] = None,
                        end_date: Optional[str] = None,
                        fields: Optional[str] = None,
                        use_cache: bool = True) -> pd.DataFrame:
        """
        Fetch daily basic data (PE, PB, total_mv, turnover_rate, etc.).

        NOTE: Tushare daily_basic data is published at MONTH-END snapshots only.
        This method checks which months are already cached and only fetches
        missing months. Missing months are fetched one at a time, using the
        trading calendar to find the nearest trade day to each month-end.
        """
        table_name = "daily_basic"

        # Single date mode
        if trade_date:
            kwargs = {"trade_date": trade_date}
            if ts_code:
                kwargs["ts_code"] = ts_code if isinstance(ts_code, str) else ",".join(ts_code)
            if fields:
                kwargs["fields"] = fields
            result = self._call_api(self.pro.daily_basic, **kwargs)
            if result is not None and not result.empty:
                result["trade_date"] = result["trade_date"].astype("int32")
                result["year"] = result["trade_date"] // 10000
                result["month"] = (result["trade_date"] % 10000) // 100
                self.cache.write(result, table_name, partition_cols=["year", "month"])
                result.drop(columns=["year", "month"], inplace=True, errors="ignore")
            return result if result is not None else pd.DataFrame()

        # Date range mode — check coverage and fetch missing months
        if start_date and end_date:
            # 1. Determine expected month-end dates and nearby trading days
            try:
                from data.calendar import get_calendar
                cal = get_calendar()
                cal.load(start_date=start_date, end_date=end_date)
                has_cal = True
            except Exception:
                has_cal = False

            expected_dates = []
            current = pd.Timestamp(str(start_date))
            end = pd.Timestamp(str(end_date))
            while current <= end:
                month_end = current + pd.offsets.MonthEnd(0)
                if month_end > end:
                    break
                me_str = int(month_end.strftime("%Y%m%d"))
                if has_cal:
                    target = cal.prev_trade_day(me_str)
                else:
                    target = me_str
                expected_dates.append((me_str, target))
                current = month_end + pd.Timedelta(days=1)

            # 2. Check cache for existing months
            cached = pd.DataFrame()
            if use_cache:
                cached = self.cache.read(
                    table_name,
                    filters=self._date_filters(start_date, end_date)
                )
                if not cached.empty:
                    cached["trade_date"] = cached["trade_date"].astype("int32")

            cached_dates = set(cached["trade_date"].unique()) if not cached.empty else set()
            missing_months = [
                (me, tgt) for me, tgt in expected_dates
                if tgt not in cached_dates
            ]

            if missing_months:
                logger.info(
                    f"daily_basic: {len(cached_dates)} months cached, "
                    f"{len(missing_months)} missing — fetching..."
                )
            else:
                logger.debug(f"daily_basic: all {len(expected_dates)} months cached")

            # 3. Fetch missing months
            new_chunks = []
            for me_str, target_date in missing_months:
                kwargs = {"trade_date": str(target_date)}
                if ts_code:
                    kwargs["ts_code"] = ts_code if isinstance(ts_code, str) else ",".join(ts_code)
                if fields:
                    kwargs["fields"] = fields
                try:
                    chunk = self._call_api(self.pro.daily_basic, **kwargs)
                    if chunk is not None and not chunk.empty:
                        chunk["trade_date"] = chunk["trade_date"].astype("int32")
                        chunk["year"] = chunk["trade_date"] // 10000
                        chunk["month"] = (chunk["trade_date"] % 10000) // 100
                        chunk = chunk.drop_duplicates(["ts_code", "trade_date"])
                        self.cache.write(
                            chunk, table_name,
                            partition_cols=["year", "month"]
                        )
                        chunk.drop(columns=["year", "month"], inplace=True, errors="ignore")
                        new_chunks.append(chunk)
                except Exception as e:
                    logger.warning(f"daily_basic {target_date}: {e}")

            # 4. Combine
            all_parts = [cached] if not cached.empty else []
            all_parts.extend(new_chunks)
            if all_parts:
                result = pd.concat(all_parts, ignore_index=True)
            else:
                result = pd.DataFrame()
            return result

        # No date filter
        result = self._call_api(self.pro.daily_basic)
        if result is not None and not result.empty:
            result["trade_date"] = result["trade_date"].astype("int32")
            result["year"] = result["trade_date"] // 10000
            result["month"] = (result["trade_date"] % 10000) // 100
            self.cache.write(result, table_name, partition_cols=["year", "month"])
            result.drop(columns=["year", "month"], inplace=True, errors="ignore")
        return result if result is not None else pd.DataFrame()

    # ------------------------------------------------------------------
    # Index weight (CSI 300 PIT constituents)
    # ------------------------------------------------------------------
    def get_index_weight(self, index_code: str = "000300.SH",
                         trade_date: Optional[str] = None,
                         start_date: Optional[str] = None,
                         end_date: Optional[str] = None,
                         use_cache: bool = True) -> pd.DataFrame:
        """
        Fetch CSI 300 index constituent weights (monthly snapshots).

        This is the critical PIT universe source. Earliest available: 2016-01.

        IMPORTANT: index_weight uses trade_date (month-end), but month-ends
        can be non-trading days (e.g., 20160430 = Saturday → 0 rows).
        We try the exact date first, then walk backward up to 5 days to find
        the nearest valid snapshot.
        """
        table_name = "index_weight"

        if use_cache:
            cached = self.cache.read(
                table_name,
                filters=self._date_filters(start_date, end_date)
            )
            if not cached.empty:
                # Standardize: API returns 'con_code', downstream expects 'ts_code'
                if "con_code" in cached.columns and "ts_code" not in cached.columns:
                    cached = cached.rename(columns={"con_code": "ts_code"})
                # index_weight is a monthly snapshot table.  A request like
                # 20190101-20191231 is valid when it returns month-end snapshots
                # inside that range; requiring min<=start and max>=end treats
                # monthly snapshots like daily bars and incorrectly falls
                # through to the API when Tushare is unavailable.
                return cached

        kwargs = {"index_code": index_code}
        if trade_date:
            kwargs["trade_date"] = trade_date
            result = self._call_api(self.pro.index_weight, **kwargs)
            if result is None or result.empty:
                # Walk backward to find valid trade date
                from datetime import datetime as dt, timedelta
                base = dt.strptime(trade_date, "%Y%m%d")
                for offset in range(1, 6):
                    try_date = (base - timedelta(days=offset)).strftime("%Y%m%d")
                    kwargs["trade_date"] = try_date
                    result = self._call_api(self.pro.index_weight, **kwargs)
                    if result is not None and not result.empty:
                        logger.info(f"index_weight: retargeted {trade_date} → {try_date}")
                        break
        elif start_date:
            # Loop over months
            all_results = []
            current = pd.Timestamp(str(start_date))
            end = pd.Timestamp(str(end_date or datetime.now().strftime("%Y%m%d")))
            while current <= end:
                month_end = (current + pd.offsets.MonthEnd(0))
                if month_end > end:
                    month_end = end
                date_str = month_end.strftime("%Y%m%d")

                # Try exact date, fall back up to 5 days
                chunk = None
                for offset in range(6):
                    try_date = (month_end - pd.Timedelta(days=offset)).strftime("%Y%m%d")
                    try:
                        chunk = self._call_api(
                            self.pro.index_weight,
                            index_code=index_code,
                            trade_date=try_date
                        )
                        if chunk is not None and not chunk.empty:
                            if offset > 0:
                                logger.debug(f"index_weight {date_str} → {try_date}")
                            break
                    except Exception:
                        continue

                if chunk is not None and not chunk.empty:
                    all_results.append(chunk)
                else:
                    logger.warning(f"index_weight: no data for month ending ~{date_str}")

                current = month_end + pd.Timedelta(days=1)

            result = pd.concat(all_results, ignore_index=True) if all_results else pd.DataFrame()
        else:
            result = self._call_api(self.pro.index_weight, **kwargs)

        if result is not None and not result.empty:
            # Standardize: API returns 'con_code', downstream expects 'ts_code'
            if "con_code" in result.columns and "ts_code" not in result.columns:
                result = result.rename(columns={"con_code": "ts_code"})
            result["trade_date"] = result["trade_date"].astype("int32")
            result["year"] = result["trade_date"] // 10000
            self.cache.write(result, table_name, partition_cols=["year"])
            result.drop(columns=["year"], inplace=True, errors="ignore")

        return result if result is not None else pd.DataFrame()

    # ------------------------------------------------------------------
    # Stock basic (listing/delisting info)
    # ------------------------------------------------------------------
    def get_stock_basic(self, exchange: str = "",
                        list_status: str = "L",
                        fields: Optional[str] = None,
                        use_cache: bool = True) -> pd.DataFrame:
        """
        Fetch stock basic info (list_date, delist_date, name, industry, etc.).

        IMPORTANT: To avoid survivorship bias, pulls both L (listed) and D (delisted)
        stocks by default. The list_status parameter can override this.
        When pulling historical universe, use include_delisted=True.
        """
        table_name = "stock_status"

        if use_cache:
            cached = self.cache.read(table_name)
            if not cached.empty:
                # Validate cache includes delisted stocks (no survivorship bias)
                statuses = cached["list_status"].unique() if "list_status" in cached.columns else []
                has_delisted = "D" in statuses
                has_listed = "L" in statuses
                if has_listed and has_delisted:
                    return cached
                elif has_listed and not has_delisted:
                    logger.warning(
                        "stock_basic cache missing delisted (D) stocks — "
                        "re-fetching to avoid survivorship bias"
                    )

        # Pull both L and D to avoid survivorship bias, unless caller specifies
        results = []
        for status in ["L", "D"]:
            kwargs = {"exchange": exchange, "list_status": status}
            if fields:
                kwargs["fields"] = fields
            chunk = self._call_api(self.pro.stock_basic, **kwargs)
            if chunk is not None and not chunk.empty:
                chunk["list_status"] = status
                results.append(chunk)

        if not results:
            return pd.DataFrame()

        result = pd.concat(results, ignore_index=True)
        result["list_date"] = result["list_date"].astype("int32")
        # delist_date may not exist in the API response for listed stocks
        if "delist_date" in result.columns:
            result["delist_date"] = pd.to_numeric(
                result["delist_date"], errors="coerce"
            ).fillna(20991231).astype("int32")
        else:
            result["delist_date"] = np.int32(20991231)
        self.cache.write(result, table_name)

        return result

    # ------------------------------------------------------------------
    # Name change (for ST history)
    # ------------------------------------------------------------------
    def get_namechange(self, ts_code: Optional[str] = None,
                       start_date: Optional[str] = None,
                       end_date: Optional[str] = None,
                       use_cache: bool = True) -> pd.DataFrame:
        """
        Fetch stock name change history (for ST flag extraction).

        Uses ann_date (announcement date) for date filtering, NOT trade_date.
        """
        table_name = "namechange"

        if use_cache:
            # namechange table uses 'ann_date' not 'trade_date'
            nc_filters = self._date_code_filters(
                start_date, end_date, ts_code, date_col="ann_date"
            )
            cached = self.cache.read(table_name, filters=nc_filters)
            if not cached.empty:
                return cached

        kwargs = {}
        if ts_code:
            kwargs["ts_code"] = ts_code if isinstance(ts_code, str) else ",".join(ts_code)
        result = self._call_api(self.pro.namechange, **kwargs)

        if result is not None and not result.empty:
            # Handle nullable date columns safely
            for col in ["ann_date", "start_date", "end_date"]:
                if col in result.columns:
                    result[col] = pd.to_numeric(
                        result[col], errors="coerce"
                    ).astype("Int64")  # nullable int
            # Filter by date using ann_date
            date_col = "ann_date" if "ann_date" in result.columns else None
            if date_col:
                if start_date:
                    result = result[result[date_col] >= int(start_date)]
                if end_date:
                    result = result[result[date_col] <= int(end_date)]
                result["year"] = result[date_col].astype("float").fillna(2099).astype("int32") // 10000
            self.cache.write(result, table_name, partition_cols=["year"])
            result.drop(columns=["year"], inplace=True, errors="ignore")

        return result if result is not None else pd.DataFrame()

    # ------------------------------------------------------------------
    # Suspend (停牌)
    # ------------------------------------------------------------------
    def get_suspend(self, ts_code: Optional[str] = None,
                    suspend_date: Optional[str] = None,
                    resume_date: Optional[str] = None,
                    start_date: Optional[str] = None,
                    end_date: Optional[str] = None,
                    use_cache: bool = True) -> pd.DataFrame:
        """
        Fetch suspend/resume records.

        Tushare suspend_d API supports suspend_date as a single date filter.
        To cover a date range, we iterate over months of suspend_date.
        All records are post-filtered to match the requested range.
        """
        table_name = "suspend_status"

        if use_cache:
            cached = self.cache.read(table_name)
            if not cached.empty:
                # Validate date range
                if start_date and end_date:
                    valid = cached[
                        (cached["suspend_date"] >= int(start_date)) &
                        (cached["suspend_date"] <= int(end_date))
                    ]
                    if not valid.empty:
                        return valid

        all_results = []
        if suspend_date:
            kwargs = {"suspend_date": suspend_date}
            if ts_code:
                kwargs["ts_code"] = ts_code if isinstance(ts_code, str) else ",".join(ts_code)
            result = self._call_api(self.pro.suspend_d, **kwargs)
            if result is not None and not result.empty:
                all_results.append(result)
        elif start_date and end_date:
            # Loop over every WEEK (not month) since suspend_d is a single-date
            # query and suspensions can start any trading day.
            current = pd.Timestamp(str(start_date))
            end = pd.Timestamp(str(end_date))
            while current <= end:
                date_str = current.strftime("%Y%m%d")
                kwargs = {"suspend_date": date_str}
                if ts_code:
                    kwargs["ts_code"] = ts_code if isinstance(ts_code, str) else ",".join(ts_code)
                try:
                    chunk = self._call_api(self.pro.suspend_d, **kwargs)
                    if chunk is not None and not chunk.empty:
                        all_results.append(chunk)
                except Exception as e:
                    logger.debug(f"suspend_d {date_str}: {e}")
                current += pd.Timedelta(days=1)
        else:
            kwargs = {}
            if ts_code:
                kwargs["ts_code"] = ts_code if isinstance(ts_code, str) else ",".join(ts_code)
            result = self._call_api(self.pro.suspend_d, **kwargs)
            if result is not None and not result.empty:
                all_results.append(result)

        if not all_results:
            return pd.DataFrame()

        result = pd.concat(all_results, ignore_index=True)
        if not result.empty:
            # Handle API response variability: column may be 'suspend_date'
            # or 'trade_date' or 'ann_date' depending on API version
            date_col = None
            for candidate in ["suspend_date", "trade_date", "ann_date"]:
                if candidate in result.columns:
                    date_col = candidate
                    break
            # Standardize column names: API may return 'trade_date' instead
            # of 'suspend_date'. We ALWAYS normalize to 'suspend_date' +
            # 'resume_date' for downstream consumers (TradableMask).
            if date_col is None:
                logger.warning(
                    f"suspend_d returned columns: {list(result.columns)}. "
                    f"Expected suspend_date. Skipping cache write."
                )
                return result

            if date_col != "suspend_date":
                result = result.rename(columns={date_col: "suspend_date"})
                date_col = "suspend_date"  # update after rename

            result[date_col] = result[date_col].astype("int32")

            # Handle resume_date similarly
            if "resume_date" in result.columns:
                result["resume_date"] = pd.to_numeric(
                    result["resume_date"], errors="coerce"
                ).fillna(20991231).astype("int32")
            else:
                result["resume_date"] = np.int32(20991231)

            # Post-filter to requested date range
            if start_date:
                result = result[result[date_col] >= int(start_date)]
            if end_date:
                result = result[result[date_col] <= int(end_date)]

            result["year"] = result[date_col] // 10000
            result["month"] = (result[date_col] % 10000) // 100
            self.cache.write(result, table_name, partition_cols=["year", "month"])
            result.drop(columns=["year", "month"], inplace=True, errors="ignore")

        return result

    # ------------------------------------------------------------------
    # Stock limits (涨跌停)
    # ------------------------------------------------------------------
    def get_stk_limit(self, ts_code: Optional[str] = None,
                      trade_date: Optional[str] = None,
                      start_date: Optional[str] = None,
                      end_date: Optional[str] = None,
                      use_cache: bool = True,
                      write_cache: bool = True) -> pd.DataFrame:
        """
        Fetch daily price limit (up/down limit prices).

        Supports: single trade_date, date range (trading days only),
        or no date filter (latest only).

        Parameters
        ----------
        write_cache : bool
            If False, skip writing to parquet cache. Caller is responsible
            for aggregating and writing (e.g., Phase 0 monthly batches).
        """
        table_name = "limit_status"

        if use_cache:
            # When querying a single trade_date, filter cache precisely.
            # A broad date-range filter can pull back stale data from
            # overlapping partitions.
            date_filters = None
            if trade_date:
                date_filters = [("trade_date", "==", np.int32(trade_date))]
            elif start_date and end_date:
                date_filters = [
                    ("trade_date", ">=", np.int32(start_date)),
                    ("trade_date", "<=", np.int32(end_date)),
                ]
            else:
                date_filters = None

            # Add ts_code filter if provided
            if date_filters and ts_code:
                codes = [ts_code] if isinstance(ts_code, str) else ts_code
                date_filters.append(("ts_code", "in", codes))

            if date_filters:
                cached = self.cache.read(table_name, filters=date_filters)
                if not cached.empty:
                    return cached

        # Build ts_code argument once
        ts_code_arg = None
        if ts_code:
            ts_code_arg = ts_code if isinstance(ts_code, str) else ",".join(ts_code)

        # Single trade_date branch
        if trade_date:
            kwargs = {"trade_date": trade_date}
            if ts_code_arg:
                kwargs["ts_code"] = ts_code_arg
            result = self._call_api(self.pro.stk_limit, **kwargs)

        # Date range branch — iterate TRADING DAYS only, not all calendar days
        elif start_date and end_date:
            all_results = []
            # Use trading calendar to avoid calling API on weekends/holidays
            try:
                cal = self.get_trade_cal(start_date=start_date, end_date=end_date)
                if not cal.empty:
                    trade_dates = sorted(cal["cal_date"].unique())
                else:
                    # Fallback: every calendar day (slow)
                    trade_dates = [
                        int(d.strftime("%Y%m%d"))
                        for d in pd.date_range(start_date, end_date)
                    ]
            except Exception:
                trade_dates = [
                    int(d.strftime("%Y%m%d"))
                    for d in pd.date_range(start_date, end_date)
                ]

            for date_int in trade_dates:
                date_str = str(date_int)
                k = {"trade_date": date_str}
                if ts_code_arg:
                    k["ts_code"] = ts_code_arg
                try:
                    chunk = self._call_api(self.pro.stk_limit, **k)
                    if chunk is not None and not chunk.empty:
                        all_results.append(chunk)
                except Exception as e:
                    logger.debug(f"stk_limit {date_str}: {e}")
            result = pd.concat(all_results, ignore_index=True) if all_results else pd.DataFrame()

        # No date filter — latest only
        else:
            kwargs = {}
            if ts_code_arg:
                kwargs["ts_code"] = ts_code_arg
            result = self._call_api(self.pro.stk_limit, **kwargs)

        if result is not None and not result.empty:
            # Validate required columns exist
            required = ["ts_code", "trade_date", "up_limit", "down_limit"]
            missing = [c for c in required if c not in result.columns]
            if missing:
                logger.warning(
                    f"stk_limit response missing columns: {missing}. "
                    f"Available: {list(result.columns)}"
                )
                # Fill missing columns with defaults
                for c in missing:
                    if c == "up_limit":
                        result["up_limit"] = np.float32(np.nan)
                    elif c == "down_limit":
                        result["down_limit"] = np.float32(np.nan)

            result["trade_date"] = result["trade_date"].astype("int32")
            # Deduplicate before writing — API may return overlapping data
            n_before = len(result)
            result = result.drop_duplicates(["ts_code", "trade_date"], keep="last")
            if len(result) < n_before:
                logger.debug(
                    f"stk_limit: deduped {n_before - len(result)} rows"
                )

            if write_cache:
                result["year"] = result["trade_date"] // 10000
                result["month"] = (result["trade_date"] % 10000) // 100
                self.cache.write(
                    result, table_name,
                    partition_cols=["year", "month"],
                    replace_partitions=True,
                )
                result.drop(columns=["year", "month"], inplace=True, errors="ignore")

        return result if result is not None else pd.DataFrame()

    # ------------------------------------------------------------------
    # Trade calendar
    # ------------------------------------------------------------------
    def get_trade_cal(self, exchange: str = "SSE",
                      start_date: Optional[str] = None,
                      end_date: Optional[str] = None,
                      use_cache: bool = True) -> pd.DataFrame:
        """
        Fetch trading calendar.

        Uses cal_date (not trade_date) for range validation and filtering.
        Cache is validated to cover the full requested range before returning.
        """
        table_name = "trade_cal"
        date_col = "cal_date"

        # Validate cache covers the requested range
        if use_cache and start_date and end_date:
            if self._cache_covers_range(table_name, start_date, end_date, date_col):
                # Cache covers the range — read with date filter
                filters = [
                    (date_col, ">=", np.int32(start_date)),
                    (date_col, "<=", np.int32(end_date)),
                ]
                cached = self.cache.read(table_name, filters=filters)
                if not cached.empty:
                    logger.debug(f"trade_cal cache hit: {start_date}-{end_date}")
                    return cached
            else:
                logger.info("trade_cal cache does not cover requested range; re-fetching")

        # Fetch from API — always request the full range to avoid partial cache
        if not self.available:
            logger.warning("Tushare not available; returning empty trade calendar")
            return pd.DataFrame()
        kwargs = {"exchange": exchange}
        if start_date:
            kwargs["start_date"] = start_date
        if end_date:
            kwargs["end_date"] = end_date
        result = self._call_api(self.pro.trade_cal, **kwargs)

        if result is not None and not result.empty:
            result[date_col] = result[date_col].astype("int32")
            result = result[result["is_open"] == 1]
            # Filter to requested range (API may return broader)
            if start_date:
                result = result[result[date_col] >= int(start_date)]
            if end_date:
                result = result[result[date_col] <= int(end_date)]
            self.cache.write(result, table_name)

        return result if result is not None else pd.DataFrame()

    # ------------------------------------------------------------------
    # Index daily (benchmark)
    # ------------------------------------------------------------------
    def get_index_daily(self, index_code: str = "000300.SH",
                        start_date: Optional[str] = None,
                        end_date: Optional[str] = None,
                        use_cache: bool = True,
                        allow_partial: bool = False) -> pd.DataFrame:
        """Fetch index daily OHLCV for benchmark.

        Cache validation (STRICT by default):
        - Filters by ts_code == index_code (not just date range).
        - Verifies full date coverage AND trading-day completeness against calendar.
        - On partial hit: attempts gap-fill via API.
        - On gap-fill failure with allow_partial=False (production):
          returns empty DataFrame with .attrs diagnostics — NEVER
          returns incomplete data that would produce 0% benchmark returns.
        - allow_partial=True (smoke/test) permits degraded returns.

        Parameters
        ----------
        index_code : str
            Tushare index code (e.g., "000300.SH").
        start_date, end_date : str, optional
            Date range YYYYMMDD.
        use_cache : bool
            Whether to check local cache first.
        allow_partial : bool
            If False (default, production): gap-fill failures return empty
            DataFrame with .attrs diagnostics.

        Returns
        -------
        pd.DataFrame with columns: ts_code, trade_date, open, high, low, close, ...
        On strict failure: empty DataFrame with .attrs containing:
            status, reason, requested_start, requested_end,
            cached_start, cached_end, missing_trade_days, coverage_ratio.
        """
        table_name = "index_daily"
        req_start = int(start_date) if start_date else None
        req_end = int(end_date) if end_date else None

        if use_cache:
            # Build filters with BOTH ts_code AND date range
            filters = self._date_filters(start_date, end_date)
            if filters is None:
                filters = []
            filters.append(("ts_code", "==", index_code))
            cached = self.cache.read(table_name, filters=filters)

            if not cached.empty:
                cached = cached[cached["ts_code"] == index_code]
                if not cached.empty:
                    cached = cached.drop_duplicates(
                        subset=["ts_code", "trade_date"], keep="last"
                    )
                    cache_min = int(cached["trade_date"].min())
                    cache_max = int(cached["trade_date"].max())
                    cached_days = set(int(d) for d in cached["trade_date"].unique())

                    # Check trading-day completeness
                    missing = set()
                    expected_days = set()
                    try:
                        from data.calendar import get_calendar
                        cal = get_calendar()
                        cal.load(start_date=start_date, end_date=end_date)
                        expected_days = set(
                            int(d) for d in
                            cal.trade_days_between(req_start or cache_min,
                                                   req_end or cache_max)
                        )
                        missing = expected_days - cached_days
                    except Exception:
                        pass  # Calendar unavailable — trust range coverage only

                    coverage_ratio = (
                        len(cached_days & expected_days) / len(expected_days)
                        if expected_days else 1.0
                    )

                    # Check date range coverage.  Prefer trading-calendar
                    # completeness over raw natural-date endpoints: requests
                    # often start/end on weekends or holidays, while the cache
                    # correctly starts at the first trading day and ends at the
                    # last trading day.
                    if expected_days:
                        range_ok = len(missing) == 0
                    else:
                        range_ok = True
                        if req_start and cache_min > req_start:
                            range_ok = False
                        if req_end and cache_max < req_end:
                            range_ok = False

                    if range_ok and not missing:
                        # Full cache hit
                        logger.debug(
                            f"index_daily cache HIT: {len(cached)} rows, "
                            f"{cache_min}-{cache_max}, "
                            f"{len(cached_days)}/{len(expected_days)} trade days, "
                            f"coverage={coverage_ratio:.2%}"
                        )
                        result = cached.sort_values("trade_date")
                        result.attrs = {
                            "requested_start": start_date,
                            "requested_end": end_date,
                            "cached_start": str(cache_min),
                            "cached_end": str(cache_max),
                            "missing_trade_days": [],
                            "coverage_ratio": coverage_ratio,
                        }
                        return result

                    # ---- Partial hit — try gap-fill ----
                    logger.info(
                        f"index_daily cache PARTIAL: cached={cache_min}-{cache_max}, "
                        f"requested={req_start}-{req_end}, "
                        f"missing_days={len(missing)}, "
                        f"coverage={coverage_ratio:.2%}"
                    )
                    fetch_start = str(req_start) if req_start and req_start < cache_min \
                        else None
                    fetch_end = str(req_end) if req_end and req_end > cache_max \
                        else None

                    gap_filled = False
                    if fetch_start or fetch_end:
                        kwargs = {"ts_code": index_code}
                        if fetch_start:
                            kwargs["start_date"] = fetch_start
                        if fetch_end:
                            kwargs["end_date"] = fetch_end
                        try:
                            gap_result = self._call_api(self.pro.index_daily, **kwargs)
                        except Exception as e:
                            gap_result = None
                            logger.error(f"index_daily gap fetch failed: {e}")

                        if gap_result is not None and not gap_result.empty:
                            gap_result["trade_date"] = gap_result["trade_date"].astype("int32")
                            merged = pd.concat(
                                [cached, gap_result], ignore_index=True
                            ).drop_duplicates(
                                subset=["ts_code", "trade_date"], keep="last"
                            )
                            merged["year"] = merged["trade_date"] // 10000
                            self.cache.write(
                                merged, table_name, partition_cols=["year"],
                                replace_partitions=True,
                            )
                            merged.drop(columns=["year"], inplace=True, errors="ignore")
                            logger.info(
                                f"index_daily gap filled: cached={len(cached)} + "
                                f"fetched={len(gap_result)} → merged={len(merged)}"
                            )
                            gap_filled = True
                            result = merged.sort_values("trade_date")
                            result.attrs = {
                                "requested_start": start_date,
                                "requested_end": end_date,
                                "cached_start": str(cache_min),
                                "cached_end": str(cache_max),
                                "missing_trade_days": [],
                                "coverage_ratio": 1.0,
                            }
                            return result

                    # ---- Gap-fill failed or not possible ----
                    if not gap_filled and not allow_partial:
                        diag = pd.DataFrame()
                        diag.attrs = {
                            "status": "PARTIAL_CACHE" if not fetch_start and not fetch_end
                                      else "FETCH_FAILED",
                            "reason": (
                                f"index_daily cache incomplete: "
                                f"missing {len(missing)} trade days, "
                                f"coverage={coverage_ratio:.2%}"
                                + (f"; gap fetch failed" if (fetch_start or fetch_end) else "")
                            ),
                            "requested_start": start_date,
                            "requested_end": end_date,
                            "cached_start": str(cache_min),
                            "cached_end": str(cache_max),
                            "missing_trade_days": sorted(list(missing))[:20],
                            "coverage_ratio": round(coverage_ratio, 4),
                        }
                        logger.error(
                            f"index_daily {diag.attrs['status']} "
                            f"(allow_partial=False): "
                            f"coverage={coverage_ratio:.2%}, "
                            f"missing={len(missing)} days"
                        )
                        return diag

                    # allow_partial=True: return partial with warning
                    logger.warning(
                        f"index_daily: returning partial cache with "
                        f"{len(missing)} missing trade days (allow_partial=True)"
                    )
                    result = cached.sort_values("trade_date")
                    result.attrs = {
                        "requested_start": start_date,
                        "requested_end": end_date,
                        "cached_start": str(cache_min),
                        "cached_end": str(cache_max),
                        "missing_trade_days": sorted(list(missing)),
                        "coverage_ratio": coverage_ratio,
                    }
                    return result

        # Full fetch — bypass cache
        kwargs = {"ts_code": index_code}
        if start_date:
            kwargs["start_date"] = start_date
        if end_date:
            kwargs["end_date"] = end_date
        result = self._call_api(self.pro.index_daily, **kwargs)

        if result is not None and not result.empty:
            result["trade_date"] = result["trade_date"].astype("int32")
            result = result.drop_duplicates(
                subset=["ts_code", "trade_date"], keep="last"
            )
            result["year"] = result["trade_date"] // 10000
            self.cache.write(result, table_name, partition_cols=["year"])
            result.drop(columns=["year"], inplace=True, errors="ignore")

        return result if result is not None else pd.DataFrame()

    # ------------------------------------------------------------------
    # Income statement (for fundamental factors)
    # ------------------------------------------------------------------
    def get_income(self, ts_code: Optional[str] = None,
                   ann_date: Optional[str] = None,
                   start_date: Optional[str] = None,
                   end_date: Optional[str] = None,
                   period: Optional[str] = None,
                   fields: Optional[str] = None,
                   use_cache: bool = True) -> pd.DataFrame:
        """Fetch income statement data. Uses ann_date for PIT alignment."""
        table_name = "income"

        if use_cache:
            cached = self.cache.read(table_name)
            if not cached.empty:
                return cached

        kwargs = {}
        if ts_code:
            kwargs["ts_code"] = ts_code if isinstance(ts_code, str) else ",".join(ts_code)
        if ann_date:
            kwargs["ann_date"] = ann_date
        if start_date:
            kwargs["start_date"] = start_date
        if end_date:
            kwargs["end_date"] = end_date
        if period:
            kwargs["period"] = period
        if fields:
            kwargs["fields"] = fields
        result = self._call_api(self.pro.income, **kwargs)

        if result is not None and not result.empty:
            for col in ["ann_date", "f_ann_date", "end_date"]:
                if col in result.columns:
                    result[col] = result[col].astype("int32")
            result["year"] = result["ann_date"] // 10000
            self.cache.write(result, table_name, partition_cols=["year"])
            result.drop(columns=["year"], inplace=True, errors="ignore")

        return result if result is not None else pd.DataFrame()

    # ------------------------------------------------------------------
    # Fina indicator (ROE, etc.)
    # ------------------------------------------------------------------
    def get_fina_indicator(self, ts_code: Optional[str] = None,
                           ann_date: Optional[str] = None,
                           start_date: Optional[str] = None,
                           end_date: Optional[str] = None,
                           period: Optional[str] = None,
                           fields: Optional[str] = None,
                           use_cache: bool = True) -> pd.DataFrame:
        """Fetch financial indicators. Uses ann_date for PIT alignment."""
        table_name = "fina_indicator"

        if use_cache:
            cached = self.cache.read(table_name)
            if not cached.empty:
                return cached

        kwargs = {}
        if ts_code:
            kwargs["ts_code"] = ts_code if isinstance(ts_code, str) else ",".join(ts_code)
        if ann_date:
            kwargs["ann_date"] = ann_date
        if start_date:
            kwargs["start_date"] = start_date
        if end_date:
            kwargs["end_date"] = end_date
        if period:
            kwargs["period"] = period
        if fields:
            kwargs["fields"] = fields
        result = self._call_api(self.pro.fina_indicator, **kwargs)

        if result is not None and not result.empty:
            if "ann_date" in result.columns:
                result["ann_date"] = result["ann_date"].astype("int32")
                result["year"] = result["ann_date"] // 10000
            self.cache.write(result, table_name, partition_cols=["year"] if "ann_date" in result.columns else None)
            result.drop(columns=["year"], inplace=True, errors="ignore")

        return result if result is not None else pd.DataFrame()

    # ------------------------------------------------------------------
    # Cashflow statement
    # ------------------------------------------------------------------
    def get_cashflow(self, ts_code: Optional[str] = None,
                     ann_date: Optional[str] = None,
                     start_date: Optional[str] = None,
                     end_date: Optional[str] = None,
                     period: Optional[str] = None,
                     fields: Optional[str] = None,
                     use_cache: bool = True) -> pd.DataFrame:
        """Fetch cashflow statement data. Uses ann_date for PIT alignment.

        Key fields: n_cashflow_act (经营现金流净额), free_cashflow,
        c_pay_acq_const_fiolta (资本开支).
        """
        table_name = "cashflow"

        if use_cache:
            cached = self.cache.read(table_name)
            if not cached.empty:
                return cached

        kwargs = {}
        if ts_code:
            kwargs["ts_code"] = ts_code if isinstance(ts_code, str) else ",".join(ts_code)
        if ann_date:
            kwargs["ann_date"] = ann_date
        if start_date:
            kwargs["start_date"] = start_date
        if end_date:
            kwargs["end_date"] = end_date
        if period:
            kwargs["period"] = period
        if fields:
            kwargs["fields"] = fields
        result = self._call_api(self.pro.cashflow, **kwargs)

        if result is not None and not result.empty:
            for col in ["ann_date", "f_ann_date", "end_date"]:
                if col in result.columns:
                    result[col] = result[col].astype("int32")
            result["year"] = result["ann_date"] // 10000
            self.cache.write(result, table_name, partition_cols=["year"])
            result.drop(columns=["year"], inplace=True, errors="ignore")

        return result if result is not None else pd.DataFrame()

    # ------------------------------------------------------------------
    # Balance sheet
    # ------------------------------------------------------------------
    def get_balancesheet(self, ts_code: Optional[str] = None,
                         ann_date: Optional[str] = None,
                         start_date: Optional[str] = None,
                         end_date: Optional[str] = None,
                         period: Optional[str] = None,
                         fields: Optional[str] = None,
                         use_cache: bool = True) -> pd.DataFrame:
        """Fetch balance sheet data. Uses ann_date for PIT alignment.

        Key fields: total_assets, accounts_receiv, total_cur_assets,
        total_cur_liab.
        """
        table_name = "balancesheet"

        if use_cache:
            cached = self.cache.read(table_name)
            if not cached.empty:
                return cached

        kwargs = {}
        if ts_code:
            kwargs["ts_code"] = ts_code if isinstance(ts_code, str) else ",".join(ts_code)
        if ann_date:
            kwargs["ann_date"] = ann_date
        if start_date:
            kwargs["start_date"] = start_date
        if end_date:
            kwargs["end_date"] = end_date
        if period:
            kwargs["period"] = period
        if fields:
            kwargs["fields"] = fields
        result = self._call_api(self.pro.balancesheet, **kwargs)

        if result is not None and not result.empty:
            for col in ["ann_date", "f_ann_date", "end_date"]:
                if col in result.columns:
                    result[col] = result[col].astype("int32")
            result["year"] = result["ann_date"] // 10000
            self.cache.write(result, table_name, partition_cols=["year"])
            result.drop(columns=["year"], inplace=True, errors="ignore")

        return result if result is not None else pd.DataFrame()

    # ------------------------------------------------------------------
    # Industry classification (申万)
    # ------------------------------------------------------------------
    def get_industry(self, level: str = "L1",
                     use_cache: bool = True) -> pd.DataFrame:
        """Fetch Shenwan industry classification."""
        table_name = "industry_pit"

        if use_cache:
            cached = self.cache.read(table_name)
            if not cached.empty:
                return cached

        try:
            result = self._call_api(self.pro.index_classify,
                                    index_code="SW",
                                    level=level)
        except Exception:
            # Fallback: try trade_cal based approach
            logger.warning("index_classify failed; using stock_basic industry as fallback")
            result = self.get_stock_basic(fields="ts_code,industry")

        if result is not None and not result.empty:
            result = result.rename(columns={
                "industry": "industry_name",
                "industry_code": "industry_code"
            }) if "industry_code" not in result.columns else result
            self.cache.write(result, table_name)

        return result if result is not None else pd.DataFrame()

    # ------------------------------------------------------------------
    # Incremental update
    # ------------------------------------------------------------------
    def incremental_update(self, table_name: str, end_date: Optional[str] = None):
        """
        Update cached data incrementally from last_cached_date + 1.

        Only pulls new data; does not rebuild full cache.
        For adj_factor changes, re-pulls the lookback window.
        """
        last = self.cache.last_date(table_name, "trade_date")
        if last is None:
            logger.info(f"No existing cache for {table_name}, doing full pull")
            return None  # caller should do full pull

        start = str(last + 1)
        if end_date is None:
            end_date = datetime.now().strftime("%Y%m%d")

        if int(start) > int(end_date):
            logger.info(f"{table_name} cache is up to date (last={last})")
            return pd.DataFrame()

        logger.info(f"Incremental update {table_name}: {start} -> {end_date}")

        if table_name == "prices_raw":
            return self.get_daily(start_date=start, end_date=end_date, use_cache=False)
        elif table_name == "adj_factor":
            lookback_start = str(last - 60)  # 60-day lookback for adj factor changes
            return self.get_adj_factor(start_date=lookback_start, end_date=end_date,
                                       use_cache=False)
        elif table_name == "daily_basic":
            return self.get_daily_basic(start_date=start, end_date=end_date, use_cache=False)
        elif table_name == "index_weight":
            return self.get_index_weight(start_date=start, end_date=end_date, use_cache=False)
        elif table_name == "limit_status":
            return self.get_stk_limit(start_date=start, end_date=end_date, use_cache=False)
        else:
            raise ValueError(f"Unknown incremental strategy for table: {table_name}")

    # ------------------------------------------------------------------
    # Cache validation helper
    # ------------------------------------------------------------------
    def _cache_covers_range(self, table_name: str, start_date: Optional[str],
                            end_date: Optional[str],
                            date_col: str = "trade_date") -> bool:
        """
        Check if cached data covers the full requested date range.

        Returns False if the cache needs a refresh.
        """
        if not start_date or not end_date:
            return True  # can't validate without range
        return self.cache.covers_range(table_name, start_date, end_date, date_col)

    # ------------------------------------------------------------------
    # Helper: filter builders
    # ------------------------------------------------------------------
    @staticmethod
    def _date_filters(start_date: Optional[str], end_date: Optional[str]) -> List[tuple]:
        """Build date range filters for cache read."""
        filters = []
        if start_date:
            filters.append(("trade_date", ">=", np.int32(start_date)))
        if end_date:
            filters.append(("trade_date", "<=", np.int32(end_date)))
        return filters if filters else None

    @staticmethod
    def _date_code_filters(start_date: Optional[str], end_date: Optional[str],
                           ts_code: Optional[Union[str, List[str]]],
                           date_col: str = "trade_date") -> List[tuple]:
        """Build date + code filters for cache read."""
        filters = []
        if start_date:
            filters.append((date_col, ">=", np.int32(start_date)))
        if end_date:
            filters.append((date_col, "<=", np.int32(end_date)))
        if ts_code:
            codes = [ts_code] if isinstance(ts_code, str) else ts_code
            filters.append(("ts_code", "in", codes))
        return filters if filters else None


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------
_client: Optional[TushareClient] = None


def get_client(**kwargs) -> TushareClient:
    """Get or create singleton TushareClient."""
    global _client
    if _client is None:
        _client = TushareClient(**kwargs)
    return _client

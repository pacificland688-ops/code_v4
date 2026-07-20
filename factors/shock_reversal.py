"""
Shock Reversal factor computation.

Captures tradable reversal opportunities after abnormal residual drops
that cannot be explained by market, industry, fundamentals, limit-downs,
suspensions, or low liquidity noise.

Factor: abnormal_drop_reversal_5_cs

Pipeline (per stock, per date t):
  1. Adj close from daily + adj_factor
  2. Market return from CSI 300 index_daily
  3. Rolling 60-day beta vs CSI 300
  4. 5-day residual return = ret_5 - beta * mkt_ret_5
  5. Residual vol (60-day std of daily residuals)
  6. Drop z-score = -resid_ret_5 / (resid_vol * sqrt(5))
  7. Severity = max(0, drop_z - 1.5)
  8. Apply filters: liquidity, limit-down, suspend, ST, IPO, earnings, trend
  9. Cross-sectional: winsorize -> neutralize (log_mcap) -> zscore
     (with missing_method='drop' — filtered stocks are NOT backfilled)

All computations use only data available at t (PIT-safe).

Key remediation fixes (2026-06-11):
  - P0-1: limit-down uses raw close <= down_limit * 1.001 (not down_limit.notna())
  - P0-2: NaN for ST/suspend/IPO/low-liquidity — CS processor must use drop
  - P1-1: amount_20d from prices_raw.amount (daily), not daily_basic (month-end)
  - Step 4: namechange lookback from 19900101; suspend covers cross-window cases
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Factor registry entry
# ---------------------------------------------------------------------------
FACTOR_SPEC: dict = {
    "abnormal_drop_reversal_5": {
        "func": "shock_reversal",
        "params": {
            "residual_window": 5,
            "beta_window": 60,
            "vol_window": 60,
            "drop_z_threshold": 1.5,
            "min_liquidity_rank": 0.3,
            "limit_down_lookback": 3,
            "trend_window": 20,
            "trend_z_threshold": -2.0,
            "trend_penalty": 0.5,
            "earnings_blackout_days_after": 3,
            "ipo_min_trading_days": 60,
            "ipo_min_calendar_days": 120,
        },
        "data_fields": ["adj_close"],
        "sign": 1,
        "category": "shock_reversal",
        "sleeve": "shock_reversal",
    },
}

# Sentinel for dates where all filter data is unavailable
_FILTER_UNAVAILABLE_SENTINEL = -999


# ---------------------------------------------------------------------------
# Shock Reversal Factor Computer
# ---------------------------------------------------------------------------
class ShockReversalComputer:
    """Compute abnormal_drop_reversal_5 factor for CSI 300 stocks.

    Parameters
    ----------
    panel_loader : PanelLoader, optional
    stock_batch_size : int
        Number of stocks to process per batch.
    index_code : str
        Benchmark index code.
    """

    INDEX_CODE = "000300.SH"

    def __init__(self, panel_loader=None, stock_batch_size: int = 80,
                 index_code: str = "000300.SH"):
        self._loader = panel_loader
        self.stock_batch_size = stock_batch_size
        self.index_code = index_code

        # Cached market data
        self._market_returns: Optional[pd.Series] = None
        self._market_prices: Optional[pd.DataFrame] = None

        # Cached filter data
        self._suspend_cache: Optional[pd.DataFrame] = None
        self._stock_basic_cache: Optional[pd.DataFrame] = None
        self._st_periods: Dict[str, List[Tuple[int, int]]] = {}
        self._list_dates: Dict[str, int] = {}
        self._delist_dates: Dict[str, int] = {}

        # Filter diagnostics
        self._filter_stats: Dict[str, int] = defaultdict(int)

    @property
    def loader(self):
        if self._loader is None:
            from data.panel_loader import get_loader
            self._loader = get_loader()
        return self._loader

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def compute_factor(
        self,
        ts_codes: List[str],
        start_date: str,
        end_date: str,
        factor_name: str = "abnormal_drop_reversal_5",
        save: bool = True,
    ) -> pd.DataFrame:
        """Compute the shock reversal factor for a universe of stocks."""
        spec = FACTOR_SPEC[factor_name]
        params = spec["params"]

        logger.info(
            "Computing %s: %d stocks, %s -> %s",
            factor_name, len(ts_codes), start_date, end_date,
        )

        # Reset diagnostics
        self._filter_stats = defaultdict(int)

        # Load market data (CSI 300)
        self._load_market_data(start_date, end_date, params["beta_window"])

        # Load filter data (ST, suspend, IPO)
        self._load_filter_data(start_date, end_date)

        # Compute lookback start
        max_window = max(
            params["beta_window"],
            params["vol_window"],
            params["trend_window"],
            params["residual_window"],
        )
        lookback_days = max(180, max_window + 60)
        try:
            lookback_start = (
                pd.Timestamp(start_date) - pd.Timedelta(days=lookback_days)
            ).strftime("%Y%m%d")
        except Exception:
            lookback_start = start_date

        all_results = []

        for i in range(0, len(ts_codes), self.stock_batch_size):
            batch_codes = ts_codes[i:i + self.stock_batch_size]
            batch_result = self._compute_batch(
                batch_codes, lookback_start, end_date, factor_name, params
            )
            if not batch_result.empty:
                all_results.append(batch_result)

            if (i // self.stock_batch_size + 1) % 10 == 0:
                logger.debug(
                    "Batch %d/%d done for %s",
                    i // self.stock_batch_size + 1,
                    (len(ts_codes) + self.stock_batch_size - 1) // self.stock_batch_size,
                    factor_name,
                )

        if not all_results:
            logger.warning("No results for %s", factor_name)
            return pd.DataFrame()

        result = pd.concat(all_results, ignore_index=True)

        # --- Apply cross-sectional liquidity filter ---
        # This must run AFTER all per-stock computation (needs cross-section)
        result = self._apply_cross_sectional_amount_filter(
            result, factor_name, lookback_start, end_date,
            ts_codes, params,
        )

        if save and not result.empty:
            self.loader.write_factor(result, factor_name)

        # Log filter diagnostics
        logger.info(
            "Computed %s: %d rows, %d stocks, %d dates",
            factor_name, len(result),
            result["ts_code"].nunique() if not result.empty else 0,
            result["trade_date"].nunique() if not result.empty else 0,
        )
        if self._filter_stats:
            logger.info("Filter stats: %s",
                        dict(sorted(self._filter_stats.items())))

        return result

    def get_filter_stats(self) -> Dict[str, int]:
        """Return accumulated filter diagnostics."""
        return dict(self._filter_stats)

    # ------------------------------------------------------------------
    # Market data loading
    # ------------------------------------------------------------------
    def _load_market_data(self, start_date: str, end_date: str, beta_window: int):
        """Load CSI 300 index daily data and compute market returns."""
        lookback_days = max(180, beta_window + 60)
        try:
            lookback_start = (
                pd.Timestamp(start_date) - pd.Timedelta(days=lookback_days)
            ).strftime("%Y%m%d")
        except Exception:
            lookback_start = start_date

        mkt = self.loader.query(
            "index_daily",
            columns=["ts_code", "trade_date", "close"],
            start_date=lookback_start,
            end_date=end_date,
        )

        if mkt.empty:
            logger.warning("No index_daily data for %s.", self.index_code)
            self._market_returns = pd.Series(dtype="float32")
            self._market_prices = pd.DataFrame()
            return

        mkt = mkt[mkt["ts_code"] == self.index_code].copy()
        if mkt.empty:
            logger.warning("No data for %s in index_daily.", self.index_code)
            self._market_returns = pd.Series(dtype="float32")
            self._market_prices = pd.DataFrame()
            return

        mkt = mkt.sort_values("trade_date")
        mkt["ret_mkt"] = mkt["close"].pct_change().astype("float32")
        self._market_returns = mkt.set_index("trade_date")["ret_mkt"]
        self._market_prices = mkt.set_index("trade_date")[["close"]]

        logger.info(
            "Loaded market data: %d dates, %s -> %s",
            len(self._market_returns),
            self._market_returns.index.min() if len(self._market_returns) > 0 else "N/A",
            self._market_returns.index.max() if len(self._market_returns) > 0 else "N/A",
        )

    # ------------------------------------------------------------------
    # Filter data loading
    # ------------------------------------------------------------------
    def _load_filter_data(self, start_date: str, end_date: str):
        """Load ST, IPO, and suspension filter data.

        IMPORTANT (Step 4 fix):
          - namechange: load from 19900101 so we capture ST entries that
            started long before the query window
          - suspend: load from well before start_date to capture
            cross-window suspensions (suspend_date < start_date AND
            resume_date > start_date)
        """
        try:
            from data.tushare_client import get_client
            client = get_client()

            # Stock basic (always full history)
            self._stock_basic_cache = client.get_stock_basic(use_cache=True)
            if not self._stock_basic_cache.empty:
                for _, row in self._stock_basic_cache.iterrows():
                    code = row["ts_code"]
                    try:
                        self._list_dates[code] = int(row["list_date"])
                        self._delist_dates[code] = int(row["delist_date"])
                    except (ValueError, TypeError):
                        pass

            # ST periods from namechange — wide lookback (Step 4 fix)
            self._load_st_periods(client, end_date)

            # Suspend records — wide lookback to cover cross-window cases (Step 4 fix)
            # Load from well before start_date
            suspend_lookback_start = _compute_suspend_lookback(start_date)
            self._suspend_cache = client.get_suspend(
                start_date=suspend_lookback_start,
                end_date=end_date,
                use_cache=True,
            )
            if not self._suspend_cache.empty:
                self._suspend_cache["suspend_date"] = (
                    self._suspend_cache["suspend_date"].astype("int32")
                )
                self._suspend_cache["resume_date"] = (
                    self._suspend_cache["resume_date"].astype("int32")
                )

            logger.info(
                "Filter data loaded: %d ST stocks, %d list dates, %d suspend records",
                len(self._st_periods), len(self._list_dates),
                len(self._suspend_cache) if self._suspend_cache is not None else 0,
            )

        except Exception as e:
            logger.warning("Could not load filter data: %s. Some filters disabled.", e)

    def _load_st_periods(self, client, end_date: str):
        """Build ST period lookup from namechange records.

        Step 4 fix: load namechange from 19900101 (not start_date) so we
        capture stocks that entered ST well before the query window and
        are still in ST during our window.
        """
        nc = client.get_namechange(
            start_date="19900101", end_date=end_date, use_cache=True
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

    # ------------------------------------------------------------------
    # Batch computation
    # ------------------------------------------------------------------
    def _compute_batch(
        self,
        ts_codes: List[str],
        start_date: str,
        end_date: str,
        factor_name: str,
        params: dict,
    ) -> pd.DataFrame:
        """Compute factor for a batch of stocks.

        Loads price data (adj + raw) with lookback, then computes
        per-stock time series.
        """
        # Load adjusted prices (for factor computation)
        price_df = self.loader.query_prices(
            start_date=start_date,
            end_date=end_date,
            ts_codes=ts_codes,
            fields=["ts_code", "trade_date", "adj_close"],
            price_type="adj",
        )
        if price_df.empty:
            return pd.DataFrame()

        # --- P1-1 fix: Load raw prices for amount and limit-down checks ---
        raw_price_df = self.loader.query_prices(
            start_date=start_date,
            end_date=end_date,
            ts_codes=ts_codes,
            fields=["ts_code", "trade_date", "open", "close", "amount"],
            price_type="raw",
        )

        # Load limit data
        limit_df = self._load_limit_data_batch(start_date, end_date, ts_codes)

        results = []
        for code in ts_codes:
            stock_price = (
                price_df[price_df["ts_code"] == code]
                .sort_values("trade_date")
                .set_index("trade_date")
            )
            if len(stock_price) < params["beta_window"] + 10:
                continue

            # Per-stock raw price slice
            stock_raw = pd.DataFrame()
            if not raw_price_df.empty:
                stock_raw = (
                    raw_price_df[raw_price_df["ts_code"] == code]
                    .sort_values("trade_date")
                    .set_index("trade_date")
                )

            try:
                factor_series = self._compute_stock_factor(
                    code, stock_price, stock_raw, limit_df, params
                )
            except Exception as e:
                logger.debug("Error computing shock_reversal for %s: %s", code, e)
                continue

            valid = factor_series.dropna()
            if len(valid) > 0:
                stock_result = pd.DataFrame({
                    "ts_code": code,
                    "trade_date": valid.index.astype("int32"),
                    factor_name: valid.values.astype("float32"),
                })
                results.append(stock_result)

        if not results:
            return pd.DataFrame()
        return pd.concat(results, ignore_index=True)

    def _load_limit_data_batch(
        self, start_date: str, end_date: str, ts_codes: List[str]
    ) -> pd.DataFrame:
        """Load stk_limit data for the date range."""
        try:
            limit_df = self.loader.query(
                "limit_status",
                columns=["ts_code", "trade_date", "up_limit", "down_limit"],
                start_date=start_date,
                end_date=end_date,
                ts_codes=ts_codes,
            )
            return limit_df
        except Exception:
            return pd.DataFrame()

    # ------------------------------------------------------------------
    # Cross-sectional amount filter (P1-1 fix)
    # ------------------------------------------------------------------
    def _apply_cross_sectional_amount_filter(
        self,
        factor_df: pd.DataFrame,
        factor_col: str,
        lookback_start: str,
        end_date: str,
        ts_codes: List[str],
        params: dict,
    ) -> pd.DataFrame:
        """Apply cross-sectional amount_20d rank filter.

        P1-1 fix: Uses prices_raw.amount (daily) for amount_20d,
        NOT daily_basic.amount (month-end snapshot).

        For each date: compute amount_20d rank, set factor to NaN
        for stocks below min_liquidity_rank. These NaN values MUST
        be preserved (not backfilled) by the CS processor using
        missing_method='drop'.
        """
        min_rank = params.get("min_liquidity_rank", 0.3)

        if factor_df.empty:
            return factor_df

        # Load raw prices with amount for the full window
        raw_price_df = self.loader.query_prices(
            start_date=lookback_start,
            end_date=end_date,
            ts_codes=ts_codes,
            fields=["ts_code", "trade_date", "amount"],
            price_type="raw",
        )

        if raw_price_df.empty:
            logger.warning("No raw price data for amount filter — skipping liquidity filter")
            return factor_df

        # Compute amount_20d per stock
        raw = raw_price_df.sort_values(["ts_code", "trade_date"])
        raw["amount_20d"] = (
            raw.groupby("ts_code")["amount"]
            .transform(lambda x: x.rolling(20, min_periods=5).mean())
        )

        # Merge with factor
        merged = factor_df.merge(
            raw[["ts_code", "trade_date", "amount_20d"]],
            on=["ts_code", "trade_date"],
            how="left",
        )

        n_filtered = 0
        dates = sorted(merged["trade_date"].unique())
        for date in dates:
            date_mask = merged["trade_date"] == date
            amount = merged.loc[date_mask, "amount_20d"]
            n_valid = amount.notna().sum()
            if n_valid < 10:
                continue

            amount_rank = amount.rank(pct=True)
            low_amount = amount_rank < min_rank
            n_before = low_amount.sum()
            if n_before > 0:
                merged.loc[date_mask & low_amount, factor_col] = np.nan
                n_filtered += n_before

        self._filter_stats["liquidity_amount_filtered"] += n_filtered
        if n_filtered > 0:
            logger.info(
                "Cross-sectional amount filter: %d observations set to NaN "
                "(amount_20d rank < %.0f%%)",
                n_filtered, min_rank * 100,
            )

        return merged[["ts_code", "trade_date", factor_col]]

    # ------------------------------------------------------------------
    # Per-stock factor computation
    # ------------------------------------------------------------------
    def _compute_stock_factor(
        self,
        code: str,
        price_df: pd.DataFrame,
        raw_price_df: pd.DataFrame,
        limit_df: pd.DataFrame,
        params: dict,
    ) -> pd.Series:
        """Compute the shock reversal factor for a single stock.

        Parameters
        ----------
        code : str
            Stock ts_code.
        price_df : pd.DataFrame
            Indexed by trade_date, must have adj_close column.
        raw_price_df : pd.DataFrame
            Indexed by trade_date, must have close column (for limit-down check).
        limit_df : pd.DataFrame
            Limit data with ts_code, trade_date, down_limit.
        params : dict
            Factor parameters.

        Returns
        -------
        pd.Series indexed by trade_date with raw factor values.
        """
        adj_close = price_df["adj_close"].astype("float64")

        # 1. Daily returns
        daily_ret = adj_close.pct_change()

        # 2. Rolling beta vs market (60-day)
        beta_window = params["beta_window"]
        beta = self._compute_rolling_beta(daily_ret, beta_window)

        # 3. 5-day cumulative return
        residual_window = params["residual_window"]
        ret_5 = adj_close / adj_close.shift(residual_window) - 1.0

        # 4. 5-day market return
        mkt_ret_5 = self._compute_market_n_day_return(residual_window)

        # 5. 5-day residual return
        resid_ret_5 = ret_5 - beta * mkt_ret_5.reindex(ret_5.index)

        # 6. Daily residuals
        daily_resid = daily_ret - beta * self._market_returns.reindex(daily_ret.index)

        # 7. Residual volatility (60-day rolling std)
        vol_window = params["vol_window"]
        resid_vol = daily_resid.rolling(
            window=vol_window, min_periods=max(20, vol_window // 3)
        ).std()

        # 8. Drop z-score
        drop_z = -resid_ret_5 / (resid_vol * np.sqrt(float(residual_window)) + 1e-12)

        # 9. Severity (raw signal)
        threshold = params["drop_z_threshold"]
        severity = (drop_z - threshold).clip(lower=0.0)

        # 10. Apply filters (order matters — structural filters first)
        signal = severity.copy()

        # 10a. Suspension filter (→ NaN, structural)
        signal = self._apply_suspend_filter(signal, code)

        # 10b. ST filter (→ NaN, structural)
        signal = self._apply_st_filter(signal, code)

        # 10c. IPO / new stock filter (→ NaN, structural)
        signal = self._apply_new_stock_filter(signal, code, params)

        # 10d. Limit down filter (→ 0.0, tradability) — P0-1 fix
        signal = self._apply_limit_down_filter(
            signal, code, limit_df, raw_price_df, params
        )

        # 10e. Medium-term trend penalty (→ ×0.5, signal attenuation)
        signal = self._apply_trend_penalty(signal, adj_close, beta, params)

        # 10f. Earnings window filter (reserved — not yet active)
        # signal = self._apply_earnings_filter(signal, code, params)

        return signal.astype("float32")

    # ------------------------------------------------------------------
    # Rolling beta computation
    # ------------------------------------------------------------------
    def _compute_rolling_beta(self, daily_ret: pd.Series, window: int) -> pd.Series:
        """Compute rolling market beta using covariance/variance."""
        if self._market_returns is None or len(self._market_returns) == 0:
            return pd.Series(1.0, index=daily_ret.index)

        common_idx = daily_ret.index.intersection(self._market_returns.index)
        if len(common_idx) < window // 2:
            return pd.Series(1.0, index=daily_ret.index)

        ret_aligned = daily_ret.reindex(common_idx)
        mkt_aligned = self._market_returns.reindex(common_idx)

        rolling_cov = ret_aligned.rolling(
            window=window, min_periods=max(20, window // 3)
        ).cov(mkt_aligned)

        rolling_var_mkt = mkt_aligned.rolling(
            window=window, min_periods=max(20, window // 3)
        ).var()

        beta = rolling_cov / (rolling_var_mkt + 1e-12)
        beta = beta.clip(lower=-2.0, upper=4.0)

        return beta.reindex(daily_ret.index).ffill().fillna(1.0)

    # ------------------------------------------------------------------
    # Market N-day return
    # ------------------------------------------------------------------
    def _compute_market_n_day_return(self, n: int) -> pd.Series:
        """Compute n-day cumulative market return."""
        if self._market_prices is None or self._market_prices.empty:
            return pd.Series(dtype="float64")
        close = self._market_prices["close"]
        return close / close.shift(n) - 1.0

    # ------------------------------------------------------------------
    # Filter: Limit Down (P0-1 fix)
    # ------------------------------------------------------------------
    def _apply_limit_down_filter(
        self,
        signal: pd.Series,
        code: str,
        limit_df: pd.DataFrame,
        raw_price_df: pd.DataFrame,
        params: dict,
    ) -> pd.Series:
        """Filter stocks with recent limit-down events.

        P0-1 FIX: Uses raw close <= down_limit * 1.001 to detect actual
        limit-down events. The OLD code incorrectly used
        ``down_limit.notna()`` which flags EVERY date with limit data
        as a limit-down, systematically killing the factor.

        Recent lookback uses a rolling window over the TRADING DAY index
        (not integer date arithmetic), so "last 3 trading days" means
        exactly the 3 most recent observations in the time series.
        """
        lookback = params.get("limit_down_lookback", 3)

        if limit_df.empty or raw_price_df.empty:
            return signal

        # Build per-code limit-down flag series
        code_limits = limit_df[limit_df["ts_code"] == code].copy()
        if code_limits.empty:
            return signal

        code_limits = code_limits.sort_values("trade_date")

        # P0-1 fix: use raw close vs down_limit comparison
        # Merge raw close with limit data on trade_date
        if "close" not in raw_price_df.columns:
            # Fallback: can't check limits without raw prices
            return signal

        raw_close = raw_price_df[["close"]].copy()

        merged = code_limits.merge(
            raw_close, left_on="trade_date", right_index=True, how="left"
        )

        # Actual limit-down: close at or below down_limit (with 0.1% tolerance)
        merged["is_limit_down_close"] = (
            merged["close"].notna()
            & merged["down_limit"].notna()
            & (merged["close"] <= merged["down_limit"] * 1.001)
        )

        # Build a boolean Series indexed by trade_date
        limit_flags = merged.set_index("trade_date")["is_limit_down_close"]
        # Ensure we have entries for all dates in the merged data
        limit_flags = limit_flags.reindex(
            merged["trade_date"].unique()
        ).fillna(False)

        # Align to signal index
        flag_aligned = limit_flags.reindex(signal.index).fillna(False)

        # Rolling window: any limit-down in the last `lookback` trading days
        # This uses trading-day index (not calendar date arithmetic)
        recent = flag_aligned.rolling(
            window=lookback, min_periods=1
        ).max().fillna(False).astype(bool)

        signal = signal.copy()
        n_zeroed = recent.sum()
        signal[recent] = 0.0
        self._filter_stats["limit_down_zeroed"] += n_zeroed

        return signal

    # ------------------------------------------------------------------
    # Filter: Suspension
    # ------------------------------------------------------------------
    def _apply_suspend_filter(
        self, signal: pd.Series, code: str
    ) -> pd.Series:
        """Mark suspended stocks as NaN.

        Step 4 fix: suspend_cache now includes records with
        suspend_date well before start_date, so cross-window
        suspensions are properly detected.
        """
        if self._suspend_cache is None or self._suspend_cache.empty:
            return signal

        susp = self._suspend_cache[self._suspend_cache["ts_code"] == code]
        if susp.empty:
            return signal

        signal = signal.copy()
        n_suspended = 0
        for _, row in susp.iterrows():
            susp_start = int(row["suspend_date"])
            susp_end = int(row["resume_date"])
            for date in signal.index:
                date_int = int(date)
                if susp_start <= date_int < susp_end:
                    if not pd.isna(signal.loc[date]):
                        signal.loc[date] = np.nan
                        n_suspended += 1

        self._filter_stats["suspend_nan"] += n_suspended
        return signal

    # ------------------------------------------------------------------
    # Filter: ST
    # ------------------------------------------------------------------
    def _apply_st_filter(
        self, signal: pd.Series, code: str
    ) -> pd.Series:
        """Set signal to NaN for ST periods.

        Step 4 fix: _st_periods now covers stocks that entered ST
        well before the query window (namechange loaded from 19900101).
        """
        if not self._st_periods:
            return signal

        periods = self._st_periods.get(code, [])
        if not periods:
            return signal

        signal = signal.copy()
        n_st = 0
        for date in signal.index:
            date_int = int(date)
            for entry, exit_ in periods:
                if entry <= date_int < exit_:
                    if not pd.isna(signal.loc[date]):
                        signal.loc[date] = np.nan
                        n_st += 1
                    break

        self._filter_stats["st_nan"] += n_st
        return signal

    # ------------------------------------------------------------------
    # Filter: New Stock (IPO)
    # ------------------------------------------------------------------
    def _apply_new_stock_filter(
        self, signal: pd.Series, code: str, params: dict
    ) -> pd.Series:
        """Set signal to NaN for stocks within IPO window."""
        list_date = self._list_dates.get(code)
        if list_date is None:
            return signal

        min_calendar_days = params.get("ipo_min_calendar_days", 120)
        min_trading_days = params.get("ipo_min_trading_days", 60)

        signal = signal.copy()
        n_ipo = 0
        for date in signal.index:
            date_int = int(date)

            try:
                dt = datetime.strptime(str(date_int), "%Y%m%d")
                list_dt = datetime.strptime(str(list_date), "%Y%m%d")
                calendar_days = (dt - list_dt).days
            except (ValueError, TypeError):
                calendar_days = 0

            if calendar_days < min_calendar_days:
                signal.loc[date] = np.nan
                n_ipo += 1
                continue

            # Approximate trading days from calendar days
            trading_days_est = int(calendar_days * 5.0 / 7.0)
            if trading_days_est < min_trading_days:
                signal.loc[date] = np.nan
                n_ipo += 1

        self._filter_stats["new_stock_nan"] += n_ipo
        return signal

    # ------------------------------------------------------------------
    # Filter: Medium-term Trend Penalty
    # ------------------------------------------------------------------
    def _apply_trend_penalty(
        self,
        signal: pd.Series,
        adj_close: pd.Series,
        beta: pd.Series,
        params: dict,
    ) -> pd.Series:
        """Penalize stocks in medium-term downtrend.

        If 20-day residual return z-score < trend_z_threshold,
        multiply signal by trend_penalty (default 0.5).
        """
        trend_window = params.get("trend_window", 20)
        trend_z_threshold = params.get("trend_z_threshold", -2.0)
        trend_penalty = params.get("trend_penalty", 0.5)

        ret_20 = adj_close / adj_close.shift(trend_window) - 1.0

        if self._market_prices is not None and not self._market_prices.empty:
            mkt_close = self._market_prices["close"]
            mkt_ret_20 = mkt_close / mkt_close.shift(trend_window) - 1.0
            mkt_ret_20_aligned = mkt_ret_20.reindex(ret_20.index)
        else:
            mkt_ret_20_aligned = pd.Series(0.0, index=ret_20.index)

        resid_ret_20 = ret_20 - beta * mkt_ret_20_aligned

        vol_window = params.get("vol_window", 60)
        daily_ret = adj_close.pct_change()
        daily_resid = daily_ret - beta * self._market_returns.reindex(daily_ret.index)
        resid_vol = daily_resid.rolling(
            window=vol_window, min_periods=max(20, vol_window // 3)
        ).std()
        resid_vol_aligned = resid_vol.reindex(resid_ret_20.index)

        resid_ret_20_z = resid_ret_20 / (
            resid_vol_aligned * np.sqrt(float(trend_window)) + 1e-12
        )

        signal = signal.copy()
        penalty_mask = resid_ret_20_z < trend_z_threshold
        n_penalized = penalty_mask.sum()
        signal[penalty_mask] = signal[penalty_mask] * trend_penalty
        self._filter_stats["trend_penalized"] += n_penalized

        return signal


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _compute_suspend_lookback(start_date: str) -> str:
    """Compute a safe lookback start for suspend data.

    The longest A-share suspension can be months. We go back at least
    2 years before start_date to ensure cross-window suspensions are
    captured. (Step 4 fix)
    """
    try:
        dt = datetime.strptime(start_date, "%Y%m%d")
        lookback_dt = dt - timedelta(days=730)  # ~2 years
        return lookback_dt.strftime("%Y%m%d")
    except Exception:
        return "20150101"


# ---------------------------------------------------------------------------
# Convenience functions
# ---------------------------------------------------------------------------
def compute_shock_reversal_factor(
    ts_codes: List[str],
    start_date: str,
    end_date: str,
    save: bool = True,
) -> pd.DataFrame:
    """Convenience function to compute shock reversal factor."""
    computer = ShockReversalComputer()
    return computer.compute_factor(
        ts_codes=ts_codes,
        start_date=start_date,
        end_date=end_date,
        factor_name="abnormal_drop_reversal_5",
        save=save,
    )

"""
Price adjustment handling: raw/adj price separation.

Core principle:
- Factor computation: adj_close / adj_open / adj_high / adj_low
- Return calculation: adj_close forward return, strictly t signal -> t+1 or later
- Trade simulation: raw open / VWAP / close (real executable prices)
- Limit up/down check: raw open vs up_limit / down_limit
- Cost calculation: raw price, raw amount, share count, 100-share lots

Never use adjusted prices for execution or limit checks.
"""

import logging
from typing import Optional, List, Dict, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class PriceAdjuster:
    """
    Manages the raw/adj price separation for CSI 300 stocks.

    Caches adj_factors and computes adjusted prices on demand.
    All output uses float32 for memory efficiency.
    """

    REQUIRED_RAW_FIELDS = ["open", "high", "low", "close", "pre_close", "vol", "amount"]
    ADJ_FIELDS = ["adj_open", "adj_high", "adj_low", "adj_close"]

    def __init__(self, client=None):
        self._client = client
        self._adj_factor_cache: Optional[pd.DataFrame] = None

    @property
    def client(self):
        if self._client is None:
            from data.tushare_client import get_client
            self._client = get_client()
        return self._client

    # ------------------------------------------------------------------
    # Adj factor loading
    # ------------------------------------------------------------------
    def load_adj_factors(self, ts_codes: Optional[List[str]] = None,
                         start_date: Optional[str] = None,
                         end_date: Optional[str] = None,
                         force_reload: bool = False):
        """
        Load adjustment factors for specified stocks and date range.

        Adj factors are relatively small (~1 float per stock per day).
        Uses float32 for memory efficiency.
        """
        if self._adj_factor_cache is not None and not force_reload:
            return

        df = self.client.get_adj_factor(
            ts_code=",".join(ts_codes) if ts_codes and len(ts_codes) < 500 else None,
            start_date=start_date,
            end_date=end_date,
            use_cache=not force_reload
        )

        if df.empty:
            logger.warning("No adj_factor data loaded")
            self._adj_factor_cache = pd.DataFrame(
                columns=["ts_code", "trade_date", "adj_factor"]
            )
            return

        # Ensure types
        df["trade_date"] = df["trade_date"].astype("int32")
        df["adj_factor"] = df["adj_factor"].astype("float32")
        df["ts_code"] = df["ts_code"].astype("category")

        self._adj_factor_cache = df
        logger.info(f"Loaded {len(df)} adj_factor records "
                     f"for {df['ts_code'].nunique()} stocks")

    # ------------------------------------------------------------------
    # Compute adjusted prices from raw + adj_factor
    # ------------------------------------------------------------------
    def compute_adj_prices(self, raw_prices: pd.DataFrame,
                           adj_factor_df: Optional[pd.DataFrame] = None,
                           missing_threshold: float = 0.02,
                           strict: bool = True) -> pd.DataFrame:
        """
        Compute adjusted OHLC from raw prices and adj_factor.

        Adjusted price = raw price × adj_factor.
        Uses float32 for all price fields.

        Production behavior (strict=True, the default):
            If the adj_factor missing ratio exceeds `missing_threshold`,
            raises ValueError with detailed diagnostics — NO silent fill.
            This prevents data gaps from propagating into strategy metrics.

        Parameters
        ----------
        raw_prices : pd.DataFrame
            Must contain: ts_code, trade_date, open, high, low, close, pre_close.
            May also contain vol, amount which are passed through.
        adj_factor_df : pd.DataFrame, optional
            Explicit adj_factor data for this chunk. Must contain
            ts_code, trade_date, adj_factor. If None, falls back to
            self._adj_factor_cache (legacy path).
        missing_threshold : float
            Maximum acceptable adj_factor missing ratio (default 2%).
            Above this: ValueError if strict=True, ERROR log if strict=False.
        strict : bool
            If True (production), raise ValueError on excess missing.
            If False (testing/smoke), log error but continue with fill.

        Returns
        -------
        pd.DataFrame with added adj_open, adj_high, adj_low, adj_close columns.
        """
        if raw_prices.empty:
            return raw_prices

        df = raw_prices.copy()

        # Determine adj_factor source: explicit > cache > load
        adj = None
        if adj_factor_df is not None:
            if adj_factor_df.empty:
                msg = "Explicit adj_factor_df is empty; cannot compute adjusted prices"
                if strict:
                    raise ValueError(msg)
                logger.error(msg)
                return df
            adj = adj_factor_df[["ts_code", "trade_date", "adj_factor"]].copy()
        elif self._adj_factor_cache is not None and not self._adj_factor_cache.empty:
            adj = self._adj_factor_cache[["ts_code", "trade_date", "adj_factor"]].copy()
        else:
            self.load_adj_factors()
            if self._adj_factor_cache is not None and not self._adj_factor_cache.empty:
                adj = self._adj_factor_cache[["ts_code", "trade_date", "adj_factor"]].copy()

        if adj is None or adj.empty:
            msg = "No adj_factors available; cannot compute adjusted prices"
            if strict:
                raise ValueError(msg)
            logger.error(msg)
            return df

        # Merge adj_factor
        df = df.merge(adj, on=["ts_code", "trade_date"], how="left")

        # ---- Threshold-gated fill (replace silent fillna(1.0)) ----
        n_missing = int(df["adj_factor"].isna().sum())
        n_total = len(df)
        missing_ratio = n_missing / n_total if n_total > 0 else 0.0

        if n_missing > 0:
            missing_dates = sorted(
                int(d) for d in df.loc[df["adj_factor"].isna(), "trade_date"].unique()
            )
            missing_stocks = sorted(
                df.loc[df["adj_factor"].isna(), "ts_code"].unique()
            )
            msg = (
                f"adj_factor missing {n_missing}/{n_total} rows "
                f"({missing_ratio:.2%}), "
                f"n_dates={len(missing_dates)}, "
                f"n_stocks={len(missing_stocks)}"
            )
            if missing_ratio > missing_threshold:
                detail = (
                    f"{msg}. "
                    f"Exceeds threshold {missing_threshold:.2%}. "
                    f"missing_dates={missing_dates[:20]}, "
                    f"sample_stocks={missing_stocks[:10]}"
                )
                if strict:
                    raise ValueError(detail)
                else:
                    logger.error(detail)
                    df["adj_factor"] = df["adj_factor"].fillna(1.0)
            else:
                logger.warning(
                    f"{msg} (below threshold {missing_threshold:.2%}). "
                    f"Filling with 1.0. "
                    f"Affected stocks: {missing_stocks[:10]}"
                )
                df["adj_factor"] = df["adj_factor"].fillna(1.0)

        # Compute adjusted OHLC (float32)
        for col in ["open", "high", "low", "close"]:
            if col in df.columns:
                adj_col = f"adj_{col}"
                df[adj_col] = (df[col].astype("float32") *
                               df["adj_factor"].astype("float32")).astype("float32")
            else:
                logger.warning(f"Column {col} not in raw_prices; skipping adj_{col}")

        # Pre-close is raw, but adj_pre_close is needed for returns
        if "pre_close" in df.columns:
            # adj_pre_close for previous day needs shifted adj_factor
            # Simplified: use same-day adj_factor as approximation for pre_close
            df["adj_pre_close"] = (df["pre_close"].astype("float32") *
                                   df["adj_factor"].astype("float32")).astype("float32")

        return df

    # ------------------------------------------------------------------
    # Forward return calculation (using adjusted prices)
    # ------------------------------------------------------------------
    @staticmethod
    def compute_forward_returns(prices: pd.DataFrame,
                                horizons: List[int] = [1, 5, 10, 20]) -> pd.DataFrame:
        """
        Compute forward returns using adjusted close.

        Strictly: return at t for horizon h uses adj_close[t+h] / adj_close[t] - 1.
        This is look-ahead-free because the label at t uses data from t+h.

        Parameters
        ----------
        prices : pd.DataFrame
            Must contain ts_code, trade_date, adj_close.
        horizons : list of int
            Forward horizons in trading days.

        Returns
        -------
        pd.DataFrame with cols: ts_code, trade_date, fwd_ret_{h}d for each horizon.
        """
        if prices.empty:
            return prices

        df = prices[["ts_code", "trade_date", "adj_close"]].copy()
        df = df.sort_values(["ts_code", "trade_date"])

        for h in horizons:
            df[f"fwd_ret_{h}d"] = (
                df.groupby("ts_code")["adj_close"]
                .shift(-h) / df["adj_close"] - 1.0
            ).astype("float32")

        return df

    # ------------------------------------------------------------------
    # Price accessors: raw vs adj
    # ------------------------------------------------------------------
    def get_prices_for_factors(self, ts_codes: List[str],
                               start_date: str, end_date: str,
                               fields: Optional[List[str]] = None) -> pd.DataFrame:
        """
        Get adjusted price data for factor computation.

        Returns only the fields needed for factor calculation.
        Uses float32 for price fields.

        Parameters
        ----------
        ts_codes : list of str
            Stock codes to include.
        start_date, end_date : str
            Date range YYYYMMDD.
        fields : list of str, optional
            Specific adj fields to return. Default: all adj OHLC.

        Returns
        -------
        pd.DataFrame with ts_code, trade_date, and adj price columns.
        """
        # Pull raw prices
        raw = self.client.get_daily(
            ts_code=ts_codes if len(ts_codes) < 500 else None,
            start_date=start_date,
            end_date=end_date
        )

        if raw.empty:
            return raw

        # Compute adjusted
        adj = self.compute_adj_prices(raw)

        # Select columns
        if fields is None:
            fields = self.ADJ_FIELDS
        cols = ["ts_code", "trade_date"] + [f for f in fields if f in adj.columns]

        result = adj[cols].copy()
        # Ensure float32
        for c in result.columns:
            if c not in ["ts_code", "trade_date"]:
                result[c] = result[c].astype("float32")

        return result

    def get_prices_for_trading(self, ts_codes: List[str],
                               date: str) -> pd.DataFrame:
        """
        Get raw (executable) prices for a specific trade date.

        Returns raw open/high/low/close/VWAP for trade execution simulation.
        Never uses adjusted prices here.
        """
        raw = self.client.get_daily(
            ts_code=ts_codes if len(ts_codes) < 500 else None,
            start_date=date,
            end_date=date
        )

        if raw.empty:
            return raw

        cols = ["ts_code", "trade_date", "open", "high", "low", "close", "vol", "amount"]
        result = raw[[c for c in cols if c in raw.columns]].copy()

        # Compute approximate VWAP = amount / vol
        if "amount" in result.columns and "vol" in result.columns:
            result["vwap"] = np.where(
                result["vol"] > 0,
                (result["amount"] / result["vol"]).astype("float32"),
                result["open"].astype("float32")
            )

        return result

    # ------------------------------------------------------------------
    # Returns: signal-date aligned forward returns
    # ------------------------------------------------------------------
    def get_signal_returns(self, ts_codes: List[str],
                           signal_dates: List[str],
                           forward_horizon: int = 5) -> pd.DataFrame:
        """
        Get forward returns for signal evaluation.

        For each signal_date, computes:
        forward_return = adj_close[signal_date + forward_horizon] / adj_close[signal_date] - 1

        Uses adj_close only.
        """
        if not signal_dates:
            return pd.DataFrame()

        from data.calendar import get_calendar
        cal = get_calendar()

        # Determine the max date we need
        max_signal = max(int(d) for d in signal_dates)
        max_needed = cal.next_trade_day(max_signal, forward_horizon)
        min_signal = min(int(d) for d in signal_dates)

        # Pull adj close for the full window
        prices = self.get_prices_for_factors(
            ts_codes=ts_codes,
            start_date=str(min_signal),
            end_date=str(max_needed),
            fields=["adj_close"]
        )

        if prices.empty:
            return prices

        # Compute forward returns at all horizons
        rets = self.compute_forward_returns(
            prices,
            horizons=[forward_horizon]
        )

        # Filter to signal dates
        signal_ints = [int(d) for d in signal_dates]
        rets = rets[rets["trade_date"].isin(signal_ints)]

        return rets[["ts_code", "trade_date", f"fwd_ret_{forward_horizon}d"]]


# ---------------------------------------------------------------------------
# Price quality validation
# ---------------------------------------------------------------------------
def validate_adj_prices(adj_prices: pd.DataFrame,
                        raw_prices: Optional[pd.DataFrame] = None,
                        daily_return_threshold: float = 5.0,
                        weekly_return_threshold: float = 10.0) -> dict:
    """
    Hard validation of adjusted prices after Phase 0 write.

    Checks:
    1. adj_factor coverage ratio (must be >= 98%)
    2. Duplicate (ts_code, trade_date) rows
    3. adj_close / raw_close ratio jump detection — daily and weekly
    4. Single-stock daily and weekly return extremes

    Parameters
    ----------
    adj_prices : pd.DataFrame
        Adjusted prices with adj_factor, adj_close columns.
    raw_prices : pd.DataFrame, optional
        Raw prices for ratio comparison. If None, skips ratio check.
    daily_return_threshold : float
        Max absolute daily return before flagging (default 5.0 = 500%).
    weekly_return_threshold : float
        Max absolute weekly return before flagging (default 10.0 = 1000%).

    Returns
    -------
    dict with:
        status: "OK" | "FAIL"
        price_quality_status: "OK" | "FAIL"
        checks: {check_name: {pass: bool, value: ..., detail: str}}
        failures: list of failure descriptions
        n_missing_adj_factor: int
        missing_ratio: float
        n_duplicates: int
    """
    checks = {}
    failures = []
    n_total = len(adj_prices)

    # Check 1: adj_factor coverage
    if "adj_factor" in adj_prices.columns:
        n_missing = int(adj_prices["adj_factor"].isna().sum())
        missing_ratio = n_missing / n_total if n_total > 0 else 0.0
        checks["adj_factor_coverage"] = {
            "pass": missing_ratio <= 0.02,
            "value": 1.0 - missing_ratio,
            "threshold": 0.98,
            "detail": f"{n_missing}/{n_total} rows missing adj_factor ({missing_ratio:.2%})",
        }
        if missing_ratio > 0.02:
            failures.append(
                f"adj_factor missing ratio {missing_ratio:.2%} exceeds 2%: "
                f"{n_missing}/{n_total} rows"
            )
    else:
        failures.append("adj_factor column missing from adj_prices")
        checks["adj_factor_coverage"] = {
            "pass": False, "value": "MISSING", "threshold": "present",
            "detail": "adj_factor column not in DataFrame",
        }

    # Check 2: Duplicate rows
    dup_mask = adj_prices.duplicated(subset=["ts_code", "trade_date"], keep=False)
    n_dupes = int(dup_mask.sum())
    checks["duplicate_rows"] = {
        "pass": n_dupes == 0,
        "value": n_dupes,
        "threshold": 0,
        "detail": f"{n_dupes} duplicate (ts_code, trade_date) rows",
    }
    if n_dupes > 0:
        dup_sample = adj_prices[dup_mask].head(10)[["ts_code", "trade_date"]].to_dict("records")
        failures.append(
            f"{n_dupes} duplicate (ts_code, trade_date) rows. "
            f"Sample: {dup_sample}"
        )

    # Check 3: adj_close daily jump detection
    if "adj_close" in adj_prices.columns and "ts_code" in adj_prices.columns:
        df_sorted = adj_prices.sort_values(["ts_code", "trade_date"]).copy()
        df_sorted["daily_ret"] = (
            df_sorted.groupby("ts_code", observed=False)["adj_close"]
            .transform(lambda x: x.pct_change())
        )
        # Also compute weekly (5-day) return
        df_sorted["weekly_ret"] = (
            df_sorted.groupby("ts_code", observed=False)["adj_close"]
            .transform(lambda x: x.pct_change(5))
        )

        daily_jumps = df_sorted[
            df_sorted["daily_ret"].abs() > daily_return_threshold
        ]
        weekly_jumps = df_sorted[
            df_sorted["weekly_ret"].abs() > weekly_return_threshold
        ]

        n_daily_jumps = len(daily_jumps)
        n_weekly_jumps = len(weekly_jumps)

        checks["daily_return_jumps"] = {
            "pass": n_daily_jumps == 0,
            "value": n_daily_jumps,
            "threshold": 0,
            "detail": f"{n_daily_jumps} daily returns exceed {daily_return_threshold:.0f}x",
        }
        checks["weekly_return_jumps"] = {
            "pass": n_weekly_jumps == 0,
            "value": n_weekly_jumps,
            "threshold": 0,
            "detail": f"{n_weekly_jumps} weekly returns exceed {weekly_return_threshold:.0f}x",
        }

        if n_daily_jumps > 0:
            sample = daily_jumps.head(5)[
                ["ts_code", "trade_date", "adj_close", "daily_ret"]
            ].to_dict("records")
            failures.append(
                f"{n_daily_jumps} extreme daily adj_close returns "
                f"(> {daily_return_threshold:.0f}x). Sample: {sample}"
            )

        if n_weekly_jumps > 0:
            sample = weekly_jumps.head(5)[
                ["ts_code", "trade_date", "adj_close", "weekly_ret"]
            ].to_dict("records")
            failures.append(
                f"{n_weekly_jumps} extreme weekly adj_close returns "
                f"(> {weekly_return_threshold:.0f}x). Sample: {sample}"
            )
    else:
        checks["daily_return_jumps"] = {
            "pass": True, "value": "SKIPPED", "threshold": 0,
            "detail": "adj_close column not available",
        }
        checks["weekly_return_jumps"] = {
            "pass": True, "value": "SKIPPED", "threshold": 0,
            "detail": "adj_close column not available",
        }

    # Check 4: adj_close / raw_close ratio jump sanity (if raw provided)
    if raw_prices is not None and not raw_prices.empty:
        if "adj_close" in adj_prices.columns and "close" in raw_prices.columns:
            merged = adj_prices[["ts_code", "trade_date", "adj_close"]].merge(
                raw_prices[["ts_code", "trade_date", "close"]],
                on=["ts_code", "trade_date"], how="inner"
            )
            if not merged.empty and (merged["close"] != 0).any():
                merged["ratio"] = merged["adj_close"] / merged["close"].replace(0, np.nan)
                merged = merged.sort_values(["ts_code", "trade_date"])
                merged["ratio_ret"] = merged.groupby(
                    "ts_code", observed=False
                )["ratio"].transform(lambda x: x.pct_change())
                ratio_jumps = merged[
                    merged["ratio_ret"].abs() > daily_return_threshold
                ]
                n_jumps = len(ratio_jumps)
                checks["adj_close_raw_close_ratio"] = {
                    "pass": n_jumps == 0,
                    "value": n_jumps,
                    "threshold": 0,
                    "detail": (
                        f"{n_jumps} adj_close/raw_close ratio jumps exceed "
                        f"{daily_return_threshold:.0f}x"
                    ),
                }
                if n_jumps > 0:
                    sample = ratio_jumps.head(5)[
                        [
                            "ts_code", "trade_date", "adj_close", "close",
                            "ratio", "ratio_ret",
                        ]
                    ].to_dict("records")
                    failures.append(
                        f"{n_jumps} extreme adj_close/raw_close ratio jumps. "
                        f"Sample: {sample}"
                    )
            else:
                checks["adj_close_raw_close_ratio"] = {
                    "pass": True, "value": "SKIPPED", "threshold": 0,
                    "detail": "raw close not available or all zero",
                }

    # Compute daily/weekly jump counts before they go out of scope
    _n_daily_jumps = n_daily_jumps if "n_daily_jumps" in dir() else 0
    _n_weekly_jumps = n_weekly_jumps if "n_weekly_jumps" in dir() else 0

    # ---- Monthly summary ----
    monthly_summary = {}
    if "trade_date" in adj_prices.columns:
        try:
            adj_prices_copy = adj_prices.copy()
            # Month column: first 6 digits of trade_date
            adj_prices_copy["month"] = adj_prices_copy["trade_date"].astype(int) // 100
            # Also compute daily/weekly jumps per month if we have adj_close
            if "adj_close" in adj_prices_copy.columns:
                df_s = adj_prices_copy.sort_values(["ts_code", "trade_date"])
                df_s["daily_ret"] = df_s.groupby(
                    "ts_code", observed=False
                )["adj_close"].transform(lambda x: x.pct_change())
                df_s["weekly_ret"] = df_s.groupby(
                    "ts_code", observed=False
                )["adj_close"].transform(lambda x: x.pct_change(5))
                monthly = df_s.groupby("month").agg(
                    n_rows=("trade_date", "count"),
                    n_daily_jumps=("daily_ret", lambda x: int((x.abs() > daily_return_threshold).sum())),
                    n_weekly_jumps=("weekly_ret", lambda x: int((x.abs() > weekly_return_threshold).sum())),
                )
            else:
                monthly = adj_prices_copy.groupby("month").agg(
                    n_rows=("trade_date", "count"),
                )
            # Add adj_factor missing ratio per month
            if "adj_factor" in adj_prices_copy.columns:
                missing_by_month = (
                    adj_prices_copy.groupby("month")["adj_factor"]
                    .apply(lambda x: x.isna().mean())
                )
                monthly["missing_ratio"] = missing_by_month
            monthly["status"] = monthly.apply(
                lambda row: "FAIL" if (
                    row.get("n_daily_jumps", 0) > 0
                    or row.get("n_weekly_jumps", 0) > 0
                    or row.get("missing_ratio", 0) > 0.02
                ) else "OK",
                axis=1,
            )
            monthly_summary = {
                str(k): v.to_dict() for k, v in monthly.iterrows()
            }
        except Exception as e:
            logger.warning(f"validate_adj_prices: monthly summary failed: {e}")

    # Overall status
    all_pass = all(c["pass"] for c in checks.values())
    status = "OK" if all_pass else "FAIL"

    return {
        "status": status,
        "price_quality_status": status,  # for go_nogo precondition
        "checks": checks,
        "failures": failures,
        "n_missing_adj_factor": int(adj_prices["adj_factor"].isna().sum())
            if "adj_factor" in adj_prices.columns else n_total,
        "missing_ratio": float(adj_prices["adj_factor"].isna().mean())
            if "adj_factor" in adj_prices.columns and len(adj_prices) > 0
            else 1.0,
        "n_duplicates": n_dupes if "n_dupes" in dir() else 0,
        "n_daily_jumps": _n_daily_jumps,
        "n_weekly_jumps": _n_weekly_jumps,
        "monthly_summary": monthly_summary,
    }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
_adjuster: Optional[PriceAdjuster] = None


def get_adjuster(**kwargs) -> PriceAdjuster:
    """Get or create singleton PriceAdjuster."""
    global _adjuster
    if _adjuster is None:
        _adjuster = PriceAdjuster(**kwargs)
    return _adjuster

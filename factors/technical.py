"""
Technical (price-based) factor computation.

Reuses code_v3 technical indicator formulas (ema, rsi, macd, etc.)
adapted for per-stock batch processing on A-share data.

Memory strategy:
- Compute per-stock in batches (default 80 stocks per batch)
- Only load required price fields via panel_loader
- Output one factor at a time to partitioned parquet
- Never construct full (date x stock x factor) wide tensor in memory

All factors use adjusted prices (adj_close, adj_open, etc.).
"""

import logging
from typing import Optional, List, Dict, Tuple, Callable

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Technical indicator formulas (from code_v3 utils)
# ---------------------------------------------------------------------------
def _ema(series: pd.Series, span: int) -> pd.Series:
    """Exponential moving average."""
    return series.ewm(span=span, adjust=False).mean()


def _rsi(series: pd.Series, window: int = 14) -> pd.Series:
    """Relative Strength Index."""
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.rolling(window=window, min_periods=window).mean()
    avg_loss = loss.rolling(window=window, min_periods=window).mean()
    rs = avg_gain / (avg_loss + 1e-12)
    return 100.0 - 100.0 / (1.0 + rs)


def _macd_hist(series: pd.Series, fast: int = 12, slow: int = 26,
               signal: int = 9) -> pd.Series:
    """MACD histogram."""
    ema_fast = _ema(series, fast)
    ema_slow = _ema(series, slow)
    macd_line = ema_fast - ema_slow
    macd_signal = _ema(macd_line, signal)
    return macd_line - macd_signal


def _rolling_std(series: pd.Series, window: int) -> pd.Series:
    """Rolling standard deviation."""
    return series.rolling(window=window, min_periods=max(10, window // 4)).std()


def _rolling_mean(series: pd.Series, window: int) -> pd.Series:
    """Rolling mean."""
    return series.rolling(window=window, min_periods=max(10, window // 4)).mean()


def _rolling_corr(a: pd.Series, b: pd.Series, window: int) -> pd.Series:
    """Rolling correlation."""
    return a.rolling(window=window, min_periods=max(10, window // 4)).corr(b)


# ---------------------------------------------------------------------------
# Per-stock factor functions (each processes a single stock's time series)
# ---------------------------------------------------------------------------
def _compute_reversal(adj_close: pd.Series, window: int,
                      skip_recent: int = 0) -> pd.Series:
    """Short-term reversal: -(return over window), skip most recent days."""
    if skip_recent > 0:
        ret = adj_close.shift(skip_recent) / adj_close.shift(window + skip_recent) - 1.0
    else:
        ret = adj_close / adj_close.shift(window) - 1.0
    return -ret


def _compute_momentum(adj_close: pd.Series, window: int,
                      skip_recent: int = 20) -> pd.Series:
    """Momentum: return over window, skip recent to avoid short-term reversal."""
    if skip_recent > 0:
        ret = adj_close.shift(skip_recent) / adj_close.shift(window + skip_recent) - 1.0
    else:
        ret = adj_close / adj_close.shift(window) - 1.0
    return ret


def _compute_volatility(adj_close: pd.Series, window: int) -> pd.Series:
    """Daily return volatility (annualized not applied)."""
    log_ret = np.log(adj_close / adj_close.shift(1))
    return _rolling_std(log_ret, window)


def _compute_ivol(adj_close: pd.Series, market_return: pd.Series,
                  window: int) -> pd.Series:
    """
    Idiosyncratic volatility: residual std after regressing on market return.
    Computed per-stock using rolling OLS residuals.
    """
    log_ret = np.log(adj_close / adj_close.shift(1))
    # Rolling beta
    cov = _rolling_corr(log_ret, market_return, window)
    var_mkt = _rolling_std(market_return, window) ** 2
    beta = cov
    # Residual
    residual = log_ret - beta * market_return
    return _rolling_std(residual, window)


def _compute_turnover_ma(turnover_rate: pd.Series, window: int) -> pd.Series:
    """Average turnover rate."""
    return _rolling_mean(turnover_rate, window)


def _compute_abnormal_turnover(turnover_rate: pd.Series, window: int) -> pd.Series:
    """Abnormal turnover: current / average - 1."""
    avg = _rolling_mean(turnover_rate, window)
    return turnover_rate / (avg + 1e-12) - 1.0


def _compute_pv_divergence(adj_close: pd.Series, vol: pd.Series,
                           window: int) -> pd.Series:
    """Price-volume divergence: -corr(price_change, volume_change)."""
    price_ret = adj_close.pct_change()
    vol_change = vol.pct_change()
    corr = _rolling_corr(price_ret, vol_change, window)
    return -corr


def _compute_rsi_factor(adj_close: pd.Series, window: int) -> pd.Series:
    """RSI factor: RSI(adj_close, window)."""
    return _rsi(adj_close, window)


def _compute_macd_factor(adj_close: pd.Series, fast: int = 12,
                         slow: int = 26, signal: int = 9) -> pd.Series:
    """MACD histogram."""
    return _macd_hist(adj_close, fast, slow, signal)


# ---------------------------------------------------------------------------
# Factor registry
# ---------------------------------------------------------------------------
FACTOR_REGISTRY: Dict[str, dict] = {
    "reversal_5": {
        "func": "reversal",
        "params": {"window": 5, "skip_recent": 0},
        "data_fields": ["adj_close"],
        "sign": 1,
        "category": "reversal",
    },
    "reversal_20": {
        "func": "reversal",
        "params": {"window": 20, "skip_recent": 0},
        "data_fields": ["adj_close"],
        "sign": 1,
        "category": "reversal",
    },
    "momentum_60": {
        "func": "momentum",
        "params": {"window": 60, "skip_recent": 20},
        "data_fields": ["adj_close"],
        "sign": 1,
        "category": "momentum",
    },
    "momentum_120": {
        "func": "momentum",
        "params": {"window": 120, "skip_recent": 20},
        "data_fields": ["adj_close"],
        "sign": 1,
        "category": "momentum",
    },
    "volatility_20": {
        "func": "volatility",
        "params": {"window": 20},
        "data_fields": ["adj_close"],
        "sign": -1,
        "category": "volatility",
    },
    "volatility_60": {
        "func": "volatility",
        "params": {"window": 60},
        "data_fields": ["adj_close"],
        "sign": -1,
        "category": "volatility",
    },
    "turnover_5": {
        "func": "turnover_ma",
        "params": {"window": 5},
        "data_fields": ["turnover_rate"],
        "sign": -1,
        "category": "liquidity",
    },
    "abnormal_turnover_20": {
        "func": "abnormal_turnover",
        "params": {"window": 20},
        "data_fields": ["turnover_rate"],
        "sign": -1,
        "category": "liquidity",
    },
    "pv_divergence_20": {
        "func": "pv_divergence",
        "params": {"window": 20},
        "data_fields": ["adj_close", "vol"],
        "sign": 1,
        "category": "price_volume",
    },
    "rsi_14": {
        "func": "rsi",
        "params": {"window": 14},
        "data_fields": ["adj_close"],
        "sign": -1,
        "category": "oscillator",
    },
    "macd_12_26_9": {
        "func": "macd",
        "params": {"fast": 12, "slow": 26, "signal": 9},
        "data_fields": ["adj_close"],
        "sign": 1,
        "category": "oscillator",
    },
}


# ---------------------------------------------------------------------------
# Technical factor computer
# ---------------------------------------------------------------------------
class TechnicalFactorComputer:
    """
    Compute technical factors for CSI 300 stocks.

    Processes stocks in batches to keep memory usage low.
    Each factor is computed per-stock as a time series, then
    collected into a long-format DataFrame.
    """

    FUNC_MAP: Dict[str, Callable] = {
        "reversal": _compute_reversal,
        "momentum": _compute_momentum,
        "volatility": _compute_volatility,
        "turnover_ma": _compute_turnover_ma,
        "abnormal_turnover": _compute_abnormal_turnover,
        "pv_divergence": _compute_pv_divergence,
        "rsi": _compute_rsi_factor,
        "macd": _compute_macd_factor,
    }

    def __init__(self, panel_loader=None, stock_batch_size: int = 80):
        self._loader = panel_loader
        self.stock_batch_size = stock_batch_size

    @property
    def loader(self):
        if self._loader is None:
            from data.panel_loader import get_loader
            self._loader = get_loader()
        return self._loader

    # ------------------------------------------------------------------
    # Main factor computation
    # ------------------------------------------------------------------
    def compute_factor(self, factor_name: str,
                       ts_codes: List[str],
                       start_date: str, end_date: str,
                       save: bool = True) -> pd.DataFrame:
        """
        Compute a single technical factor for a universe of stocks.

        Parameters
        ----------
        factor_name : str
            Factor key from FACTOR_REGISTRY.
        ts_codes : list of str
            Stock codes to compute for.
        start_date, end_date : str
            Date range YYYYMMDD.
        save : bool
            If True, write to parquet cache.

        Returns
        -------
        pd.DataFrame with columns: ts_code, trade_date, {factor_name}
        """
        if factor_name not in FACTOR_REGISTRY:
            raise ValueError(f"Unknown factor: {factor_name}. "
                             f"Available: {list(FACTOR_REGISTRY.keys())}")

        spec = FACTOR_REGISTRY[factor_name]
        func_key = spec["func"]
        params = spec["params"]
        data_fields = spec["data_fields"]

        if func_key not in self.FUNC_MAP:
            raise ValueError(f"Unknown function: {func_key}")

        compute_func = self.FUNC_MAP[func_key]

        logger.info(f"Computing {factor_name}: {spec['category']}, "
                     f"{len(ts_codes)} stocks, {start_date}->{end_date}")

        all_results = []

        # Process stocks in batches
        for i in range(0, len(ts_codes), self.stock_batch_size):
            batch_codes = ts_codes[i:i + self.stock_batch_size]
            batch_result = self._compute_factor_batch(
                factor_name, batch_codes, start_date, end_date,
                compute_func, params, data_fields, func_key
            )
            if not batch_result.empty:
                all_results.append(batch_result)

            logger.debug(f"Batch {i // self.stock_batch_size + 1}: "
                         f"{len(batch_codes)} stocks done")

        if not all_results:
            logger.warning(f"No results for {factor_name}")
            return pd.DataFrame()

        result = pd.concat(all_results, ignore_index=True)

        # Apply sign
        sign = spec.get("sign", 1)
        if sign != 1:
            result[factor_name] = result[factor_name] * sign

        # Save
        if save and not result.empty:
            self.loader.write_factor(result, factor_name)

        logger.info(f"Computed {factor_name}: {len(result)} rows, "
                     f"{result['ts_code'].nunique()} stocks, "
                     f"{result['trade_date'].nunique()} dates")

        return result

    def _compute_factor_batch(self, factor_name: str,
                              ts_codes: List[str],
                              start_date: str, end_date: str,
                              compute_func: Callable,
                              params: dict,
                              data_fields: List[str],
                              func_key: str) -> pd.DataFrame:
        """Compute factor for a batch of stocks.

        Loads price data with a lookback window before start_date to ensure
        indicators have enough history for proper computation.
        """
        # Compute lookback: max window parameter + extra buffer
        max_window = max(params.values()) if params else 0
        lookback_days = max(160, max_window + 40)  # at least ~8 months
        try:
            lookback_start = (
                pd.Timestamp(start_date) - pd.Timedelta(days=lookback_days)
            ).strftime("%Y%m%d")
        except Exception:
            lookback_start = start_date

        # Determine which data source to use
        if "turnover_rate" in data_fields:
            df = self.loader.query_daily_basic(
                start_date=lookback_start, end_date=end_date,
                ts_codes=ts_codes,
                fields=["ts_code", "trade_date"] + data_fields
            )
        else:
            df = self.loader.query_prices(
                start_date=lookback_start, end_date=end_date,
                ts_codes=ts_codes,
                fields=list(set(data_fields + ["ts_code", "trade_date"])),
                price_type="adj"
            )

        if df.empty:
            return df

        results = []
        for code in ts_codes:
            stock_df = df[df["ts_code"] == code].sort_values("trade_date")
            if len(stock_df) < max(params.values()) + 10:
                continue

            stock_df = stock_df.set_index("trade_date")

            # Prepare arguments based on function
            try:
                if func_key == "reversal":
                    factor_vals = compute_func(stock_df["adj_close"], **params)
                elif func_key == "momentum":
                    factor_vals = compute_func(stock_df["adj_close"], **params)
                elif func_key == "volatility":
                    factor_vals = compute_func(stock_df["adj_close"], **params)
                elif func_key in ("turnover_ma", "abnormal_turnover"):
                    factor_vals = compute_func(stock_df["turnover_rate"], **params)
                elif func_key == "pv_divergence":
                    factor_vals = compute_func(
                        stock_df["adj_close"], stock_df["vol"], **params
                    )
                elif func_key == "rsi":
                    factor_vals = compute_func(stock_df["adj_close"], **params)
                elif func_key == "macd":
                    factor_vals = compute_func(stock_df["adj_close"], **params)
                else:
                    continue
            except Exception as e:
                logger.debug(f"Error computing {factor_name} for {code}: {e}")
                continue

            # Build result
            valid = factor_vals.dropna()
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

    # ------------------------------------------------------------------
    # Batch compute all technical factors
    # ------------------------------------------------------------------
    def compute_all_factors(self, ts_codes: List[str],
                            start_date: str, end_date: str,
                            factor_names: Optional[List[str]] = None,
                            save: bool = True) -> Dict[str, pd.DataFrame]:
        """
        Compute multiple technical factors.

        Returns dict[factor_name] -> DataFrame.
        Each factor is computed and saved independently.
        """
        if factor_names is None:
            factor_names = list(FACTOR_REGISTRY.keys())

        results = {}
        for name in factor_names:
            try:
                df = self.compute_factor(
                    name, ts_codes, start_date, end_date, save=save
                )
                results[name] = df
            except Exception as e:
                logger.error(f"Failed to compute {name}: {e}")
                results[name] = pd.DataFrame()

        return results


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------
def list_technical_factors() -> List[str]:
    """List all available technical factor names."""
    return list(FACTOR_REGISTRY.keys())


def get_factor_spec(factor_name: str) -> dict:
    """Get specification for a factor."""
    return FACTOR_REGISTRY.get(factor_name, {})

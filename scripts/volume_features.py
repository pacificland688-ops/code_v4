"""
Volume / Turnover Diagnostic Features (Phase A — diagnostic only)
==================================================================
Computes per-event volume, turnover, and liquidity features for
distinguishing panic liquidation from sustained distribution.

DESIGN CONSTRAINT: This module is DIAGNOSTIC ONLY.  It does NOT
modify R0–R3 trading results.  Features are computed from PIT data
available at event-date close and attached to the event ledger.

Stock-level features use equal-weight median across frozen basket
components.  Basket-level features aggregate across components.

Historical normalization baselines end before the event day (shift(1)).
Event-window state measures such as 5-day down-amount share and smoothed
Amihud include the event close by definition.

Reference: Cox & Peterson (1994), Amihud (2002)
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")


# ═══════════════════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════════════════
ROLLING_WINDOW = 20          # trading days for baseline computation
MIN_PERIODS = 10             # minimum observations for rolling stats
DOWN_DAYS_WINDOW = 5         # window for down-amount share
AMIHUD_SMOOTH_WINDOW = 20    # smoothing window for Amihud illiquidity
MAD_SCALE = 1.4826           # scale factor for MAD → robust stddev


# ═══════════════════════════════════════════════════════════════════════════
# Dataclass
# ═══════════════════════════════════════════════════════════════════════════
@dataclass
class VolumeFeatures:
    """Per-event volume/turnover diagnostics.  All fields may be NaN if
    data is unavailable for any component (FEATURE_UNAVAILABLE policy).

    All features use data ≤ signal_date (event day close).  Phase A is
    pre-trade diagnostics — entry_date (T+1) data must NOT be used.
    """

    signal_id: str = ""
    signal_date: int = 0  # event trigger date (NOT entry_date = T+1)

    # ── Stock-level (equal-weight median across frozen components) ──────
    amount_ratio_20d_median: float = np.nan
    turnover_ratio_20d_median: float = np.nan
    turnover_robust_z20_median: float = np.nan
    amihud_illiquidity_median: float = np.nan
    down_amount_share_5d_median: float = np.nan

    # ── Basket-level aggregations ───────────────────────────────────────
    abnormal_volume_fraction: float = np.nan       # frac of stocks with amount_ratio > 2.0 AND pct_chg < 0
    high_turnover_limit_down_count: int = 0         # stocks with turnover z > 2 AND at limit-down
    amihud_shock_median: float = np.nan             # median Amihud across components
    turnover_cross_sectional_dispersion: float = np.nan  # IQR / median of turnover_rate_f

    # ── Coverage ────────────────────────────────────────────────────────
    turnover_coverage: float = np.nan               # fraction of components with non-NaN turnover_rate_f
    amount_coverage: float = np.nan                 # fraction of components with non-NaN amount

    # ── Metadata ────────────────────────────────────────────────────────
    n_components: int = 0
    features_unavailable: list[str] = field(default_factory=list)

    @staticmethod
    def columns() -> list[str]:
        return [f.name for f in VolumeFeatures.__dataclass_fields__.values()]


# ═══════════════════════════════════════════════════════════════════════════
# Stock-level feature computation
# ═══════════════════════════════════════════════════════════════════════════

def _rolling_median_ratio(series: pd.Series, window: int = ROLLING_WINDOW,
                          min_periods: int = MIN_PERIODS) -> pd.Series:
    """Ratio of current value to rolling median of past *window* values.

    Uses shift(1) to exclude the current observation from the baseline.
    """
    min_p = min(min_periods, window)
    rolling_med = series.shift(1).rolling(window, min_periods=min_p).median()
    ratio = series / rolling_med.replace(0, np.nan)
    return ratio


def _robust_zscore(series: pd.Series, window: int = ROLLING_WINDOW,
                   min_periods: int = MIN_PERIODS) -> pd.Series:
    """Robust z-score using rolling median and MAD.

    z = (x - median) / (MAD * 1.4826), where MAD = median(|x - median|).
    Uses shift(1) for the baseline window.
    """
    min_p = min(min_periods, window)
    history = series.shift(1)
    rolling_med = history.rolling(window, min_periods=min_p).median()
    rolling_mad = history.rolling(window, min_periods=min_p).apply(
        lambda values: float(
            np.median(np.abs(values - np.median(values)))
        ),
        raw=True,
    )
    denom = rolling_mad * MAD_SCALE
    denom = denom.replace(0, np.nan)
    return (series - rolling_med) / denom


def _amihud_illiquidity(pct_chg: pd.Series, amount: pd.Series,
                        window: int = AMIHUD_SMOOTH_WINDOW) -> pd.Series:
    """Amihud (2002) illiquidity: |return| / dollar volume, smoothed.

    Units: percentage points per 10,000 CNY of volume (scaled for readability).
    Higher values → more price impact per unit of volume → less liquid.
    """
    pct = pct_chg.abs() / 100.0  # convert pct_chg (e.g. -5.0) to decimal return (0.05)
    amount_safe = amount.replace(0, np.nan)
    # Tushare amount is 千元 (thousand CNY).  Divide by 10 for 万元.
    daily_illiq = pct / (amount_safe / 10.0)  # per 万元
    min_p = min(MIN_PERIODS, window)
    return daily_illiq.rolling(window, min_periods=min_p).mean()


def _down_amount_share(pct_chg: pd.Series, amount: pd.Series,
                       window: int = DOWN_DAYS_WINDOW) -> pd.Series:
    """Fraction of total amount on down days over the past *window* days."""
    min_p = min(MIN_PERIODS, window)  # min_periods must be ≤ window
    is_down = (pct_chg < 0).astype(float)
    down_amount = (is_down * amount).rolling(window, min_periods=min_p).sum()
    total_amount = amount.rolling(window, min_periods=min_p).sum()
    return down_amount / total_amount.replace(0, np.nan)


# ═══════════════════════════════════════════════════════════════════════════
# Basket-level aggregation
# ═══════════════════════════════════════════════════════════════════════════

def _basket_median(values: list[float], n_components: int | None = None) -> float:
    """Median of component values.

    If n_components is provided, ALL components must be present (no NaN).
    Returns NaN if any component is missing or all are NaN.
    """
    n_total = len(values)
    arr = np.array([v for v in values if np.isfinite(v)], dtype=float)
    if n_components is not None and len(arr) < n_components:
        return np.nan
    if n_components is None and len(arr) < n_total:
        return np.nan
    return float(np.median(arr)) if len(arr) > 0 else np.nan


def _basket_fraction(values: list[bool]) -> float:
    """Fraction of True values."""
    clean = [v for v in values if isinstance(v, (bool, np.bool_))]
    return float(np.mean(clean)) if clean else np.nan


def _cross_sectional_dispersion(values: list[float]) -> float:
    """IQR / median for cross-sectional dispersion of turnover."""
    arr = np.array([v for v in values if np.isfinite(v)], dtype=float)
    if len(arr) < 3:
        return np.nan
    q75, q25 = np.percentile(arr, [75, 25])
    med = np.median(arr)
    if med == 0 or np.isnan(med):
        return np.nan
    return float((q75 - q25) / med)


# ═══════════════════════════════════════════════════════════════════════════
# Main computation entry point
# ═══════════════════════════════════════════════════════════════════════════

def compute_volume_features(
    signal_id: str,
    signal_date: int,
    component_codes: list[str],
    prices: pd.DataFrame,
    daily_basic: pd.DataFrame | None = None,
    limit_status: pd.DataFrame | None = None,
) -> VolumeFeatures:
    """Compute all volume/turnover diagnostic features for one event.

    All data is filtered to ≤ signal_date (event day close, PIT).
    Phase A features must use signal_date, NOT entry_date (T+1).
    Features are computed per-component, then aggregated to basket-level
    via median or fraction.

    Parameters
    ----------
    signal_id : str
        Event identifier (e.g. "PANIC_20230421").
    signal_date : int
        Event trigger date in YYYYMMDD format (NOT entry_date).
    component_codes : list[str]
        Frozen basket component ts_codes.
    prices : pd.DataFrame
        Daily prices with columns: ts_code, trade_date, amount, pct_chg, vol.
    daily_basic : pd.DataFrame | None
        Daily basic with columns: ts_code, trade_date, turnover_rate_f.
        If None, turnover features will be NaN.
    limit_status : pd.DataFrame | None
        Limit status for detecting limit-down in basket aggregations.

    Returns
    -------
    VolumeFeatures dataclass.
    """
    features = VolumeFeatures(
        signal_id=signal_id,
        signal_date=signal_date,
        n_components=len(component_codes),
    )

    if not component_codes or prices is None or prices.empty:
        features.features_unavailable.append("no_component_data")
        return features

    code_set = set(str(c) for c in component_codes)

    # ── Per-component accumulators ──────────────────────────────────────
    amt_ratios: list[float] = []
    to_ratios: list[float] = []
    to_z_scores: list[float] = []
    amihud_vals: list[float] = []
    amihud_shock_vals: list[float] = []  # event-day raw |return|/amount (unsmoothed)
    down_shares: list[float] = []
    turnover_vals_event: list[float] = []  # for cross-sectional dispersion
    abnormal_volume_flags: list[bool] = []
    n_turnover_available = 0
    n_amount_available = 0
    high_to_limit_down_count = 0

    for code in sorted(code_set):
        # Filter to PIT: data ≤ signal_date (event day close)
        stock_prices = prices[
            (prices["ts_code"].astype(str) == code)
            & (prices["trade_date"].astype(int) <= signal_date)
        ].sort_values("trade_date")

        if stock_prices.empty or len(stock_prices) < MIN_PERIODS:
            continue

        # ── PIT freshness check: last trade_date must match signal_date exactly ──
        # YYYYMMDD integer subtraction doesn't handle calendar gaps;
        # require exact match so stale data is NEVER included in basket stats.
        last_price_date = int(stock_prices["trade_date"].max())
        price_fresh = (last_price_date == signal_date)

        # ── Amount ratio ────────────────────────────────────────────────
        amt_ratio_val = np.nan
        if "amount" in stock_prices.columns:
            amt_series = pd.to_numeric(stock_prices["amount"], errors="coerce")
            amt_ratio = _rolling_median_ratio(amt_series)
            if amt_ratio.notna().iloc[-1] if len(amt_ratio) > 0 else False:
                amt_ratio_val = float(amt_ratio.iloc[-1])
                if price_fresh:
                    amt_ratios.append(amt_ratio_val)
                    n_amount_available += 1

        # ── Turnover rate features (from daily_basic) ───────────────────
        turnover_val = np.nan
        current_turnover_z = np.nan
        basic_fresh = False
        if daily_basic is not None and not daily_basic.empty:
            stock_basic = daily_basic[
                (daily_basic["ts_code"].astype(str) == code)
                & (daily_basic["trade_date"].astype(int) <= signal_date)
            ].sort_values("trade_date")

            if not stock_basic.empty and "turnover_rate_f" in stock_basic.columns:
                last_basic_date = int(stock_basic["trade_date"].max())
                basic_fresh = (last_basic_date == signal_date)
                to_series = pd.to_numeric(stock_basic["turnover_rate_f"], errors="coerce")
                to_series = to_series.dropna()
                if len(to_series) >= MIN_PERIODS:
                    to_ratio = _rolling_median_ratio(to_series)
                    to_z = _robust_zscore(to_series)
                    has_to_ratio = not to_ratio.empty and to_ratio.notna().iloc[-1]
                    has_to_z = not to_z.empty and to_z.notna().iloc[-1]
                    if has_to_ratio and basic_fresh:
                        to_ratios.append(float(to_ratio.iloc[-1]))
                    if has_to_z and basic_fresh:
                        z_val = float(to_z.iloc[-1])
                        to_z_scores.append(z_val)
                        current_turnover_z = z_val
                    turnover_val = float(to_series.iloc[-1]) if not to_series.empty else np.nan
                    if basic_fresh and (has_to_ratio or has_to_z):
                        n_turnover_available += 1

        if np.isfinite(turnover_val) and price_fresh and basic_fresh:
            turnover_vals_event.append(turnover_val)

        # ── Amihud illiquidity ──────────────────────────────────────────
        if "pct_chg" in stock_prices.columns and "amount" in stock_prices.columns and price_fresh:
            pct = pd.to_numeric(stock_prices["pct_chg"], errors="coerce")
            amt = pd.to_numeric(stock_prices["amount"], errors="coerce")
            amihud = _amihud_illiquidity(pct, amt)
            if not amihud.empty and amihud.notna().iloc[-1]:
                amihud_vals.append(float(amihud.iloc[-1]))
            # Raw event-day shock (unsmoothed, for amihud_shock_median)
            event_row_shock = stock_prices[stock_prices["trade_date"].astype(int) == signal_date]
            if not event_row_shock.empty:
                raw_pct = float(event_row_shock["pct_chg"].iloc[0]) if "pct_chg" in event_row_shock.columns else np.nan
                raw_amt = float(event_row_shock["amount"].iloc[0]) if "amount" in event_row_shock.columns else np.nan
                if np.isfinite(raw_pct) and np.isfinite(raw_amt) and raw_amt > 0:
                    shock = abs(raw_pct) / 100.0 / (raw_amt / 10000.0)  # per 万元
                    amihud_shock_vals.append(float(shock))

        # ── Down amount share ───────────────────────────────────────────
        if "pct_chg" in stock_prices.columns and "amount" in stock_prices.columns and price_fresh:
            pct2 = pd.to_numeric(stock_prices["pct_chg"], errors="coerce")
            amt2 = pd.to_numeric(stock_prices["amount"], errors="coerce")
            das = _down_amount_share(pct2, amt2)
            if not das.empty and das.notna().iloc[-1]:
                down_shares.append(float(das.iloc[-1]))

        # ── Abnormal volume flags ───────────────────────────────────────
        if price_fresh and "pct_chg" in stock_prices.columns and "amount" in stock_prices.columns:
            event_row = stock_prices[stock_prices["trade_date"].astype(int) == signal_date]
            if not event_row.empty:
                pct_val = float(event_row["pct_chg"].iloc[0]) if "pct_chg" in event_row.columns else np.nan
                amt_val = float(event_row["amount"].iloc[0]) if "amount" in event_row.columns else np.nan
                if np.isfinite(amt_val) and len(amt_series) >= MIN_PERIODS + 1:
                    baseline = amt_series.shift(1).rolling(ROLLING_WINDOW, min_periods=MIN_PERIODS).median().iloc[-1]
                    if np.isfinite(baseline) and baseline > 0:
                        ratio = amt_val / baseline
                        abnormal_volume_flags.append(ratio > 2.0 and np.isfinite(pct_val) and pct_val < 0)

        # ── High-turnover + limit-down count ────────────────────────────
        if price_fresh and limit_status is not None and not limit_status.empty:
            lim_row = limit_status[
                (limit_status["ts_code"].astype(str) == code)
                & (limit_status["trade_date"].astype(int) == signal_date)
            ]
            at_limit_down = False
            if not lim_row.empty:
                limit_col = "down_limit" if "down_limit" in lim_row.columns else None
                if limit_col:
                    down_lim = float(lim_row[limit_col].iloc[0])
                    event_row2 = stock_prices[stock_prices["trade_date"].astype(int) == signal_date]
                    event_close = (
                        float(event_row2["close"].iloc[0])
                        if not event_row2.empty and "close" in event_row2.columns
                        else np.nan
                    )
                    if np.isfinite(down_lim) and np.isfinite(event_close):
                        at_limit_down = abs(event_close - down_lim) < 0.005
            if at_limit_down and np.isfinite(current_turnover_z) and current_turnover_z > 2.0:
                high_to_limit_down_count += 1

    # ── Basket-level aggregation ─────────────────────────────────────────
    n_total = len(code_set)
    features.amount_ratio_20d_median = _basket_median(amt_ratios)
    features.turnover_ratio_20d_median = _basket_median(to_ratios)
    features.turnover_robust_z20_median = _basket_median(to_z_scores)
    features.amihud_illiquidity_median = _basket_median(amihud_vals)   # smoothed (20d avg)
    features.down_amount_share_5d_median = _basket_median(down_shares)
    features.abnormal_volume_fraction = _basket_fraction(abnormal_volume_flags)
    features.high_turnover_limit_down_count = high_to_limit_down_count
    features.amihud_shock_median = _basket_median(amihud_shock_vals)    # event-day raw shock (distinct from smoothed)
    features.turnover_cross_sectional_dispersion = _cross_sectional_dispersion(turnover_vals_event)
    features.turnover_coverage = n_turnover_available / max(n_total, 1)
    features.amount_coverage = n_amount_available / max(n_total, 1)

    # Record unavailable features
    if n_turnover_available == 0:
        features.features_unavailable.append("turnover_rate_f")
    if n_amount_available == 0:
        features.features_unavailable.append("amount")

    return features

#!/usr/bin/env python
"""
Factor Style Signal Validation — evaluate whether momentum / value-repair /
growth-quality factors can predict 20-day-forward style regime WITHOUT
look-ahead bias.

Output: style signal labels (momentum_on, value_repair_on, mixed_style,
growth_quality_watch, no_clear_style) with forward-validation metrics.

Key anti-leakage rule:
  IC[d] = corr(factor[d], fwd_ret_H[d]) is only *knowable* after horizon
  trading days have passed.  The script maps every daily IC to an
  ic_available_date = trading_calendar.shift(factor_date, +horizon) and
  computes trailing ICs on that axis.  Labels at signal_date T only use ICs
  whose ic_available_date < T.

Research candidates only — does NOT modify production eligible_factors.

Usage:
  python -X utf8 scripts/evaluate_factor_style_signals.py
  python -X utf8 scripts/evaluate_factor_style_signals.py --start 20170101 --end 20241231
  python -X utf8 scripts/evaluate_factor_style_signals.py --lookback 60 --horizon 20
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import yaml
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ===========================================================================
# Configuration
# ===========================================================================

# Factor groups for style signals
MOMENTUM_FACTORS = [
    "risk_adjusted_momentum_60_cs",
    "momentum_60_skip5_cs",
    "trend_quality_cs",
]

VALUE_REPAIR_FACTORS = [
    "valuation_reversion_3y_cs",
]

GROWTH_QUALITY_FACTORS = [
    "earnings_acceleration_cs",
]

CONFIRM_FACTORS = [
    "volume_confirmed_momentum_cs",
]

ALL_FACTORS = MOMENTUM_FACTORS + VALUE_REPAIR_FACTORS + GROWTH_QUALITY_FACTORS + CONFIRM_FACTORS

# Default thresholds
TRAILING_IC_THRESHOLD = 0.01       # Min trailing IC to declare a style "active"
MOMENTUM_LOOKBACK = 60              # Trading days for trailing IC computation
FORWARD_HORIZON = 20                # Forward trading days for validation
MIN_DAYS_FOR_LABEL = 20            # Min samples to trust a style label
MIN_OBS_FOR_IC = 30                # Min stocks per date for rank IC
CORRELATION_DEDUP_THRESHOLD = 0.70  # Max correlation to treat as independent
MIXED_MARGIN = 0.005               # Margin for mixed_style vs single-style

# Coverage thresholds
MIN_MEDIAN_COVERAGE_PCT = 0.80     # Min median daily coverage to be "active"
MIN_YEARLY_COVERAGE_PCT = 0.60     # Min coverage in any single year

# Style label ordering (priority descending)
STYLE_LABELS = [
    "mixed_style",
    "momentum_on",
    "value_repair_on",
    "growth_quality_watch",
    "no_clear_style",
]

# ===========================================================================
# Trading calendar helper
# ===========================================================================

def _get_calendar():
    """Lazy-load the trading calendar singleton."""
    try:
        from data.calendar import get_calendar
        cal = get_calendar()
        cal.load("20100101", "20991231")
        return cal
    except Exception:
        return None


# ===========================================================================
# Data loading
# ===========================================================================

def _load_factor_cache(factor_name: str) -> pd.DataFrame:
    """Load factor values from parquet cache (handles v3 month= and v4 formats)."""
    root = ROOT / "data" / "parquet" / "factors" / f"factor_name={factor_name}"
    if not root.exists():
        return pd.DataFrame(columns=["ts_code", "trade_date", "value"])

    chunks = []
    for year_dir in sorted(root.iterdir()):
        if not year_dir.is_dir() or not year_dir.name.startswith("year="):
            continue
        for sub in sorted(year_dir.iterdir()):
            if sub.is_dir() and sub.name.startswith("month="):
                # v3 format: year=YYYY/month=MM/*.parquet
                for pq_file in sub.glob("*.parquet"):
                    try:
                        part = pd.read_parquet(pq_file)
                        part.columns = [str(c).strip().lower() for c in part.columns]
                        if "ts_code" not in part.columns or "trade_date" not in part.columns:
                            continue
                        val_col = next((c for c in part.columns
                                       if c not in ("ts_code", "trade_date", "year", "month")), None)
                        if val_col is None:
                            continue
                        part = part.rename(columns={val_col: "value"})
                        part = part[["ts_code", "trade_date", "value"]].copy()
                        part["ts_code"] = part["ts_code"].astype(str)
                        part["trade_date"] = pd.to_numeric(part["trade_date"], errors="coerce")
                        part = part.dropna(subset=["trade_date"])
                        if not part.empty:
                            chunks.append(part)
                    except Exception:
                        continue
            elif sub.suffix == ".parquet":
                # v4 format: year=YYYY/part_YYYY.parquet
                try:
                    part = pd.read_parquet(sub)
                    part.columns = [str(c).strip().lower() for c in part.columns]
                    if "ts_code" not in part.columns or "trade_date" not in part.columns:
                        continue
                    if "value" not in part.columns:
                        continue
                    part = part[["ts_code", "trade_date", "value"]].copy()
                    part["ts_code"] = part["ts_code"].astype(str)
                    part["trade_date"] = pd.to_numeric(part["trade_date"], errors="coerce")
                    part = part.dropna(subset=["trade_date"])
                    if not part.empty:
                        chunks.append(part)
                except Exception:
                    continue

    if not chunks:
        return pd.DataFrame(columns=["ts_code", "trade_date", "value"])
    result = pd.concat(chunks, ignore_index=True)
    result = result.drop_duplicates(["ts_code", "trade_date"])
    return result.sort_values(["ts_code", "trade_date"])


def _load_fwd_returns() -> pd.DataFrame:
    """Load forward returns (same format as factor_quality_rebuild uses)."""
    root = ROOT / "data" / "parquet" / "factors" / "factor_name=fwd_returns"
    if not root.exists():
        return pd.DataFrame()

    chunks = []
    for year_dir in sorted(root.iterdir()):
        if not year_dir.is_dir() or not year_dir.name.startswith("year="):
            continue
        for month_dir in sorted(year_dir.iterdir()):
            if not month_dir.is_dir():
                continue
            for pq_file in month_dir.glob("*.parquet"):
                try:
                    part = pd.read_parquet(pq_file)
                    part.columns = [str(c).strip().lower() for c in part.columns]
                    keep = [c for c in part.columns if c not in ("year", "month")]
                    part = part[keep].copy()
                    part["ts_code"] = part["ts_code"].astype(str)
                    part["trade_date"] = pd.to_numeric(part["trade_date"], errors="coerce")
                    part = part.dropna(subset=["trade_date"])
                    if not part.empty:
                        chunks.append(part)
                except Exception:
                    continue

    if not chunks:
        return pd.DataFrame()
    result = pd.concat(chunks, ignore_index=True)
    return result.drop_duplicates(["ts_code", "trade_date"]).sort_values(["ts_code", "trade_date"])


# ===========================================================================
# Date filtering
# ===========================================================================

def _filter_by_date_range(df: pd.DataFrame, start: int, end: int,
                          date_col: str = "trade_date") -> pd.DataFrame:
    """Filter DataFrame to keep only rows with start <= date_col <= end."""
    if df.empty:
        return df
    mask = (df[date_col] >= start) & (df[date_col] <= end)
    return df[mask].copy()


# ===========================================================================
# IC computation (WITH look-ahead fix)
# ===========================================================================

def _rank_ic(factor_vals: pd.Series, fwd_rets: pd.Series) -> float:
    """Spearman rank correlation, NaN if < MIN_OBS_FOR_IC observations."""
    mask = factor_vals.notna() & fwd_rets.notna()
    if mask.sum() < MIN_OBS_FOR_IC:
        return float("nan")
    try:
        return float(spearmanr(factor_vals[mask], fwd_rets[mask])[0])
    except Exception:
        return float("nan")


def _compute_daily_ic(factor_df: pd.DataFrame, fwd_df: pd.DataFrame,
                      horizon: str = "fwd_ret_20d") -> pd.DataFrame:
    """Compute cross-sectional rank IC per trade_date (factor_date).

    IC[d] = corr(factor[d], fwd_ret_H[d])

    Returns DataFrame with columns [trade_date, ic].
    trade_date here is the factor observation date.
    """
    if factor_df.empty or fwd_df.empty or horizon not in fwd_df.columns:
        return pd.DataFrame(columns=["trade_date", "ic"])

    merged = factor_df.merge(
        fwd_df[["ts_code", "trade_date", horizon]],
        on=["ts_code", "trade_date"], how="inner"
    )
    if merged.empty:
        return pd.DataFrame(columns=["trade_date", "ic"])

    daily_ic = merged.groupby("trade_date").apply(
        lambda g: _rank_ic(g["value"], g[horizon]), include_groups=False
    ).dropna()

    return daily_ic.reset_index(name="ic")


def _map_ic_to_available_date(daily_ic: pd.DataFrame, cal,
                              horizon_days: int) -> pd.DataFrame:
    """Map each daily IC from factor_date to ic_available_date.

    ic_available_date = cal.next_trade_day(factor_date, horizon_days)

    This is the ANTI-LEAKAGE step: an IC computed from factor[d] and
    fwd_ret_H[d] is only *knowable* after horizon_days trading days.
    """
    if daily_ic.empty:
        return pd.DataFrame(columns=["factor_date", "ic", "ic_available_date"])

    df = daily_ic.rename(columns={"trade_date": "factor_date"}).copy()
    df["factor_date"] = df["factor_date"].astype(int)

    if cal is not None:
        df["ic_available_date"] = df["factor_date"].apply(
            lambda d: cal.next_trade_day(d, horizon_days)
        )
    else:
        # Fallback: add horizon_days * 1.4 calendar days (weekend/holiday approx)
        df["ic_available_date"] = df["factor_date"].apply(
            lambda d: _add_calendar_days_fallback(d, int(horizon_days * 1.4))
        )

    return df[["factor_date", "ic", "ic_available_date"]]


def _add_calendar_days_fallback(date_int: int, days: int) -> int:
    """Fallback: add calendar days to YYYYMMDD int."""
    from datetime import timedelta
    s = str(date_int)
    dt = datetime(int(s[:4]), int(s[4:6]), int(s[6:8]))
    dt = dt + timedelta(days=days)
    return int(dt.strftime("%Y%m%d"))


def _compute_trailing_ic_on_available_axis(
    daily_ic_mapped: pd.DataFrame,
    lookback: int,
) -> pd.DataFrame:
    """Compute trailing mean IC on the ic_available_date axis.

    For each ic_available_date A, trailing_ic[A] = mean of ICs whose
    ic_available_date falls in [A - lookback + 1, A].

    This is the correct no-leakage computation: the trailing IC at A only
    uses ICs that were *knowable* by date A.
    """
    if daily_ic_mapped.empty:
        return pd.DataFrame(columns=["ic_available_date", "trailing_ic", "n_ic_obs"])

    # Sort by ic_available_date
    df = daily_ic_mapped.sort_values("ic_available_date").copy()

    # Compute rolling mean on ic_available_date axis
    df["trailing_ic"] = (
        df["ic"]
        .rolling(lookback, min_periods=max(10, lookback // 3))
        .mean()
    )
    df["n_ic_obs"] = (
        df["ic"]
        .rolling(lookback, min_periods=max(10, lookback // 3))
        .count()
    )

    # Aggregate: one row per ic_available_date (take last if multiple ICs same date)
    result = (
        df.groupby("ic_available_date")
        .agg(trailing_ic=("trailing_ic", "last"),
             n_ic_obs=("n_ic_obs", "last"),
             latest_factor_date=("factor_date", "max"))
        .reset_index()
    )

    return result.dropna(subset=["trailing_ic"])


def _align_trailing_to_signal_dates(
    trailing_df: pd.DataFrame,
    signal_dates: np.ndarray,
) -> pd.DataFrame:
    """Align trailing ICs to signal dates using merge_asof.

    For each signal_date T, use the most recent trailing_ic from
    ic_available_date < T (strictly before).  The IC at ic_available_date
    is only knowable at the END of that trading day, so it can first be
    used for signals on the NEXT trading day.

    Uses pd.merge_asof with direction='backward' and allow_exact_matches=False
    to guarantee strict look-back.

    Returns DataFrame with columns [signal_date, trailing_ic, n_ic_obs,
    latest_factor_date, latest_ic_available_date].
    """
    if trailing_df.empty:
        return pd.DataFrame(columns=[
            "signal_date", "trailing_ic", "n_ic_obs",
            "latest_factor_date", "latest_ic_available_date"
        ])

    # Prepare left frame: signal dates
    left = pd.DataFrame({"signal_date": sorted(signal_dates)})
    left["signal_date"] = left["signal_date"].astype("int64")

    # Prepare right frame: trailing IC keyed by ic_available_date
    right = trailing_df.rename(columns={"ic_available_date": "signal_date"}).copy()
    right = right.sort_values("signal_date")
    right["signal_date"] = right["signal_date"].astype("int64")

    # merge_asof with allow_exact_matches=False: for signal_date T,
    # match the latest ic_available_date strictly < T
    result = pd.merge_asof(
        left,
        right,
        on="signal_date",
        direction="backward",
        allow_exact_matches=False,
    )

    # Rename the matched ic_available_date back for clarity
    # (merge_asof fills NaN for no match — these are dates before the first
    #  ic_available_date became available)
    return result[["signal_date", "trailing_ic", "n_ic_obs",
                    "latest_factor_date"]]


# ===========================================================================
# Coverage computation
# ===========================================================================

def _compute_coverage(factor_df: pd.DataFrame, fwd_df: pd.DataFrame) -> pd.DataFrame:
    """Compute daily coverage of factor stocks vs forward return universe.

    coverage_pct = |factor ∩ fwd_universe| / |fwd_universe|

    Returns DataFrame with columns:
      trade_date, fwd_universe_n, factor_coverage_n, coverage_pct
    """
    if factor_df.empty or fwd_df.empty:
        return pd.DataFrame(columns=["trade_date", "fwd_universe_n",
                                     "factor_coverage_n", "coverage_pct"])

    # Universe per date from forward returns
    fwd_universe = fwd_df.groupby("trade_date")["ts_code"].apply(set)

    # Factor stocks per date
    factor_stocks = factor_df.groupby("trade_date")["ts_code"].apply(set)

    # Align dates
    common_dates = sorted(set(fwd_universe.index) & set(factor_stocks.index))

    rows = []
    for d in common_dates:
        fwd_set = fwd_universe.get(d, set())
        fac_set = factor_stocks.get(d, set())
        intersection = fac_set & fwd_set
        fwd_n = len(fwd_set)
        if fwd_n == 0:
            continue
        rows.append({
            "trade_date": d,
            "fwd_universe_n": fwd_n,
            "factor_coverage_n": len(intersection),
            "coverage_pct": len(intersection) / fwd_n,
        })

    return pd.DataFrame(rows)


def _evaluate_coverage(coverage_df: pd.DataFrame) -> Dict[str, Any]:
    """Evaluate whether a factor meets coverage thresholds.

    Returns dict with:
      - median_coverage_pct
      - min_yearly_coverage_pct
      - coverage_blocked: bool
      - coverage_status: str
    """
    if coverage_df.empty:
        return {
            "median_coverage_pct": 0.0,
            "min_yearly_coverage_pct": 0.0,
            "coverage_blocked": True,
            "coverage_status": "NO_DATA",
        }

    median_cov = coverage_df["coverage_pct"].median()

    # Yearly coverage
    coverage_df_copy = coverage_df.copy()
    coverage_df_copy["year"] = coverage_df_copy["trade_date"] // 10000
    yearly_median = coverage_df_copy.groupby("year")["coverage_pct"].median()
    min_yearly = yearly_median.min() if len(yearly_median) > 0 else 0.0

    blocked = (
        median_cov < MIN_MEDIAN_COVERAGE_PCT
        or min_yearly < MIN_YEARLY_COVERAGE_PCT
    )

    status = "DATA_COVERAGE_BLOCKED" if blocked else "OK"

    return {
        "median_coverage_pct": float(median_cov),
        "min_yearly_coverage_pct": float(min_yearly),
        "coverage_blocked": blocked,
        "coverage_status": status,
        "yearly_median_coverage": {int(k): float(v) for k, v in yearly_median.items()},
    }


# ===========================================================================
# Correlation dedup
# ===========================================================================

def _dedup_momentum_factors(
    factor_daily_ics: Dict[str, pd.DataFrame],
    coverage_info: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Tuple[Optional[str], List[str], pd.DataFrame, Dict[str, Any]]:
    """Deduplicate momentum factors: pick representative, report correlated.

    Returns (representative_name, [dropped_names], corr_matrix, selection_reasons).
    """
    selection_reasons: Dict[str, Any] = {
        "representative": None,
        "dropped": [],
        "selection_metric": "mean_ic",
    }

    if len(factor_daily_ics) == 0:
        return None, [], pd.DataFrame(), selection_reasons

    if len(factor_daily_ics) == 1:
        key = list(factor_daily_ics.keys())[0]
        selection_reasons["representative"] = {
            "name": key,
            "reason": "only one momentum factor available",
            "mean_ic": float(factor_daily_ics[key]["ic"].mean()) if not factor_daily_ics[key].empty else float("nan"),
        }
        return key, [], pd.DataFrame(), selection_reasons

    # Merge all ICs on factor_date
    merged = None
    for name, ic_df in factor_daily_ics.items():
        ic_df_sub = ic_df[["trade_date", "ic"]].rename(columns={"ic": name})
        if merged is None:
            merged = ic_df_sub
        else:
            merged = merged.merge(ic_df_sub, on="trade_date", how="inner")

    if merged is None or len(merged) < 20:
        key = list(factor_daily_ics.keys())[0]
        selection_reasons["representative"] = {
            "name": key,
            "reason": "insufficient overlapping data, picking first",
        }
        return key, [], pd.DataFrame(), selection_reasons

    factor_names = list(factor_daily_ics.keys())
    corr_matrix = merged[factor_names].corr()

    # Compute selection metrics for each factor
    metrics = {}
    for n in factor_names:
        m = {}
        m["mean_ic"] = float(merged[n].mean())
        m["icir"] = float(merged[n].mean() / merged[n].std()) if merged[n].std() > 0 else 0.0
        m["coverage_n_dates"] = int(merged[n].notna().sum())
        m["ic_std"] = float(merged[n].std())
        if coverage_info and n in coverage_info:
            m["median_coverage_pct"] = coverage_info[n].get("median_coverage_pct", None)
        metrics[n] = m

    # Pick representative: highest mean IC
    mean_ics = {n: merged[n].mean() for n in factor_names}
    representative = max(mean_ics, key=mean_ics.get)

    # Find redundant factors (correlation > threshold with representative)
    dropped = []
    for n in factor_names:
        if n != representative and abs(corr_matrix.loc[representative, n]) > CORRELATION_DEDUP_THRESHOLD:
            dropped.append(n)
            selection_reasons["dropped"].append({
                "name": n,
                "correlation_with_representative": float(corr_matrix.loc[representative, n]),
                "own_mean_ic": float(mean_ics[n]),
            })

    selection_reasons["representative"] = {
        "name": representative,
        "mean_ic": float(mean_ics[representative]),
        "icir": metrics[representative]["icir"],
        "reason": "highest mean IC among momentum factors",
    }

    return representative, dropped, corr_matrix, selection_reasons


# ===========================================================================
# Style signal classification
# ===========================================================================

def _classify_style_signals(
    momentum_aligned: pd.DataFrame,
    value_aligned: pd.DataFrame,
    growth_aligned: pd.DataFrame,
    threshold: float = TRAILING_IC_THRESHOLD,
    mixed_margin: float = MIXED_MARGIN,
    growth_coverage_blocked: bool = False,
) -> pd.DataFrame:
    """Classify each signal_date into a style signal label.

    Labels (priority order, first matching wins):
      1. mixed_style: both momentum and value trailing IC > threshold
                      AND |mom_ic - val_ic| < mixed_margin
      2. momentum_on: momentum trailing IC > threshold
                      AND momentum IC > value IC + mixed_margin
      3. value_repair_on: value trailing IC > threshold
                          AND value IC > momentum IC + mixed_margin
      4. growth_quality_watch: growth trailing IC > threshold
                               (observation only if coverage blocked)
      5. no_clear_style: none of the above

    If growth_coverage_blocked is True, growth_quality_watch is NOT used
    to drive formal style decisions — it is recorded as an observation label.
    """
    # Merge all aligned trailing ICs on signal_date
    result = momentum_aligned[["signal_date", "trailing_ic"]].rename(
        columns={"trailing_ic": "mom_ic"}
    ).copy()
    result["mom_n_obs"] = momentum_aligned.get("n_ic_obs", np.nan)

    if not value_aligned.empty:
        result = result.merge(
            value_aligned[["signal_date", "trailing_ic"]].rename(
                columns={"trailing_ic": "val_ic"}
            ),
            on="signal_date", how="left"
        )
        result["val_n_obs"] = value_aligned.get("n_ic_obs", np.nan)
    else:
        result["val_ic"] = np.nan

    if not growth_aligned.empty:
        result = result.merge(
            growth_aligned[["signal_date", "trailing_ic"]].rename(
                columns={"trailing_ic": "grw_ic"}
            ),
            on="signal_date", how="left"
        )
    else:
        result["grw_ic"] = np.nan

    # Also merge latest factor dates for reporting
    for prefix, src in [("mom", momentum_aligned), ("val", value_aligned), ("grw", growth_aligned)]:
        if src.empty:
            continue
        if "latest_factor_date" in src.columns:
            result[f"{prefix}_latest_factor_date"] = result["signal_date"].map(
                dict(zip(src["signal_date"], src["latest_factor_date"]))
            )

    # Classify
    labels = []
    for _, row in result.iterrows():
        mom = row["mom_ic"] if not (isinstance(row.get("mom_ic"), float) and np.isnan(row.get("mom_ic", np.nan))) else -999.0
        val = row.get("val_ic", np.nan)
        val = val if not (isinstance(val, float) and np.isnan(val)) else -999.0
        grw = row.get("grw_ic", np.nan)
        grw = grw if not (isinstance(grw, float) and np.isnan(grw)) else -999.0

        mom_on = mom > threshold
        val_on = val > threshold
        grw_on = grw > threshold

        if mom_on and val_on and abs(mom - val) < mixed_margin:
            labels.append("mixed_style")
        elif mom_on and (not val_on or mom > val + mixed_margin):
            labels.append("momentum_on")
        elif val_on and (not mom_on or val > mom + mixed_margin):
            labels.append("value_repair_on")
        elif grw_on and not growth_coverage_blocked:
            # growth can only be a formal style if not coverage blocked
            labels.append("growth_quality_watch")
        elif grw_on and growth_coverage_blocked:
            # coverage blocked: record as observation
            labels.append("growth_quality_watch")
        else:
            labels.append("no_clear_style")

    result["style_label"] = labels
    return result


# ===========================================================================
# Forward validation with comprehensive metrics
# ===========================================================================

def _validate_style_signals(
    style_df: pd.DataFrame,
    factor_daily_ics: Dict[str, pd.DataFrame],
    factor_data: Dict[str, pd.DataFrame],
    fwd_df: pd.DataFrame,
    horizon_col: str,
    momentum_rep: Optional[str],
    value_rep: Optional[str],
    growth_rep: Optional[str],
    growth_coverage_blocked: bool = False,
) -> Dict[str, Any]:
    """For each style label, compute comprehensive forward performance metrics.

    For a date with label L, we evaluate the RELEVANT factor's forward IC:
      - momentum_on: check momentum representative factor IC
      - value_repair_on: check value repair factor IC
      - mixed_style: check both
      - growth_quality_watch: check growth factor IC (observation)
      - no_clear_style: check momentum factor IC (as baseline)

    Metrics computed per label:
      - n_days, mean_ic, icir, hit_rate
      - top_bottom_spread, top_quintile_excess
      - estimated_cost, net_spread
      - positive_years, max_year_contribution
      - status, failure_reasons
    """
    results: Dict[str, Any] = {}

    # Map label to its representative factor IC
    label_factor_ic: Dict[str, Optional[pd.DataFrame]] = {}
    if momentum_rep and momentum_rep in factor_daily_ics:
        label_factor_ic["momentum_on"] = factor_daily_ics[momentum_rep]
        label_factor_ic["mixed_style"] = factor_daily_ics[momentum_rep]
        label_factor_ic["no_clear_style"] = factor_daily_ics[momentum_rep]
    if value_rep and value_rep in factor_daily_ics:
        label_factor_ic["value_repair_on"] = factor_daily_ics[value_rep]
    if growth_rep and growth_rep in factor_daily_ics:
        label_factor_ic["growth_quality_watch"] = factor_daily_ics[growth_rep]

    for label in STYLE_LABELS:
        label_dates = style_df[style_df["style_label"] == label]
        n_days = len(label_dates)

        if n_days < MIN_DAYS_FOR_LABEL:
            results[label] = {
                "n_days": n_days,
                "mean_ic": float("nan"),
                "icir": float("nan"),
                "hit_rate": float("nan"),
                "top_bottom_spread": float("nan"),
                "top_quintile_excess": float("nan"),
                "estimated_cost": float("nan"),
                "net_spread": float("nan"),
                "positive_years": 0,
                "max_year_contribution": float("nan"),
                "status": "INSUFFICIENT_DATA",
                "failure_reasons": [f"only {n_days} labeled days (< {MIN_DAYS_FOR_LABEL})"],
            }
            continue

        daily_ic_df = label_factor_ic.get(label)
        if daily_ic_df is None or daily_ic_df.empty:
            results[label] = {
                "n_days": n_days,
                "mean_ic": float("nan"),
                "icir": float("nan"),
                "hit_rate": float("nan"),
                "top_bottom_spread": float("nan"),
                "top_quintile_excess": float("nan"),
                "estimated_cost": float("nan"),
                "net_spread": float("nan"),
                "positive_years": 0,
                "max_year_contribution": float("nan"),
                "status": "NO_FACTOR_DATA",
                "failure_reasons": ["no daily IC data for representative factor"],
            }
            continue

        # IC values on labeled dates
        daily_ic_df_indexed = daily_ic_df.set_index("trade_date")["ic"]
        label_ics = []
        for dt in label_dates["signal_date"].values:
            if dt in daily_ic_df_indexed.index:
                v = daily_ic_df_indexed[dt]
                if not (isinstance(v, float) and np.isnan(v)):
                    label_ics.append(v)

        if len(label_ics) < MIN_DAYS_FOR_LABEL:
            results[label] = {
                "n_days": n_days,
                "mean_ic": float("nan"),
                "icir": float("nan"),
                "hit_rate": float("nan"),
                "top_bottom_spread": float("nan"),
                "top_quintile_excess": float("nan"),
                "estimated_cost": float("nan"),
                "net_spread": float("nan"),
                "positive_years": 0,
                "max_year_contribution": float("nan"),
                "status": "INSUFFICIENT_DATA",
                "failure_reasons": [f"only {len(label_ics)} valid IC observations on labeled dates"],
            }
            continue

        ics = np.array(label_ics)
        mean_ic = float(np.mean(ics))
        ic_std = float(np.std(ics))
        icir = float(mean_ic / ic_std) if ic_std > 0 else 0.0
        hit_rate = float(np.mean(ics > 0))

        # Top/bottom spread: mean IC vs zero (approximation when no quantile data)
        top_bottom_spread = float(mean_ic * 2.0)  # rough: IC * 2 ≈ top vs bottom spread

        # Top quintile excess (approximation: half the top-bottom spread)
        top_quintile_excess = float(mean_ic * 0.5)

        # Estimated cost (basis points, rough estimate for A-shares)
        # Double-sided turnover cost ~ 30 bps for top/bottom quintile rebalance
        estimated_cost = 0.0030

        # Net spread
        net_spread = float(mean_ic - estimated_cost) if not np.isnan(mean_ic) else float("nan")

        # Yearly breakdown
        label_dates_copy = label_dates.copy()
        label_dates_copy["year"] = label_dates_copy["signal_date"] // 10000
        label_dates_copy["ic"] = label_dates_copy["signal_date"].map(
            lambda d: daily_ic_df_indexed.get(d, np.nan)
        )
        label_dates_copy = label_dates_copy.dropna(subset=["ic"])

        yearly = label_dates_copy.groupby("year")["ic"].agg(["mean", "count"])
        positive_years = int((yearly["mean"] > 0).sum())
        max_year_contribution = float(yearly["mean"].max()) if len(yearly) > 0 else float("nan")

        # Status and failure reasons
        failure_reasons = []
        status = "OK"

        if np.isnan(mean_ic):
            status = "NO_DATA"
            failure_reasons.append("mean_ic is NaN")
        elif icir < 0.1:
            failure_reasons.append(f"low ICIR ({icir:.4f})")
            if status == "OK":
                status = "LOW_ICIR"

        if hit_rate < 0.50:
            failure_reasons.append(f"hit_rate below 50% ({hit_rate:.1%})")

        if positive_years < 1:
            failure_reasons.append("no positive years")

        # Specific checks
        if label == "growth_quality_watch" and growth_coverage_blocked:
            status = "DATA_COVERAGE_BLOCKED"
            failure_reasons.append("insufficient stock coverage for formal style signal")

        results[label] = {
            "n_days": n_days,
            "mean_ic": mean_ic,
            "icir": icir,
            "hit_rate": hit_rate,
            "top_bottom_spread": top_bottom_spread,
            "top_quintile_excess": top_quintile_excess,
            "estimated_cost": estimated_cost,
            "net_spread": net_spread,
            "positive_years": positive_years,
            "max_year_contribution": max_year_contribution,
            "status": status,
            "failure_reasons": failure_reasons,
            "_yearly_ic": {int(k): float(v) for k, v in yearly["mean"].items()},
            "_yearly_count": {int(k): int(v) for k, v in yearly["count"].items()},
        }

    # ---- Predictive power assessment ----
    # Compare momentum_on vs no_clear_style (baseline).
    # Runs whenever both have enough data, regardless of initial status.
    no_style_result = results.get("no_clear_style", {})
    base_valid = (
        no_style_result.get("status") not in ("INSUFFICIENT_DATA", "NO_FACTOR_DATA")
        and not np.isnan(no_style_result.get("mean_ic", float("nan")))
    )

    if base_valid:
        base_mean = no_style_result["mean_ic"]

        for label, result_key in [("momentum_on", "momentum_on"),
                                   ("value_repair_on", "value_repair_on")]:
            label_result = results.get(result_key, {})
            label_mean = label_result.get("mean_ic", float("nan"))
            if (label_result.get("status") not in ("INSUFFICIENT_DATA", "NO_FACTOR_DATA")
                    and not np.isnan(label_mean)):
                if label_mean <= base_mean:
                    old_status = label_result.get("status", "?")
                    results[result_key]["status"] = "NO_PREDICTIVE_POWER"
                    results[result_key]["failure_reasons"].append(
                        f"mean_ic ({label_mean:.4f}) <= no_clear_style baseline "
                        f"({base_mean:.4f}) — was {old_status}"
                    )

    return results


# ===========================================================================
# IC autocorrelation diagnostic
# ===========================================================================

def _compute_ic_autocorrelation(
    daily_ic: pd.DataFrame,
    max_lag: int = 60,
) -> pd.DataFrame:
    """Compute autocorrelation of daily IC series for lags 1..max_lag.

    Tests whether high-IC days tend to be followed by high-IC days
    (positive autocorrelation → IC momentum) or low-IC days
    (negative autocorrelation → IC reversal).

    Returns DataFrame with columns:
      factor, lag, n_obs, autocorr, p_value, significance
    """
    if daily_ic.empty or len(daily_ic) < max_lag + 10:
        return pd.DataFrame(columns=["factor", "lag", "n_obs", "autocorr",
                                     "p_value", "significance"])

    ic_series = daily_ic.sort_values("trade_date")["ic"].dropna().values

    rows = []
    for lag in range(1, max_lag + 1):
        if len(ic_series) <= lag + 10:
            continue
        # Shift: compare IC[t] with IC[t-lag]
        x = ic_series[lag:]
        y = ic_series[:-lag]
        mask = ~np.isnan(x) & ~np.isnan(y)
        n = mask.sum()
        if n < 20:
            rows.append({
                "factor": "", "lag": lag, "n_obs": n,
                "autocorr": float("nan"), "p_value": float("nan"),
                "significance": "INSUFFICIENT_DATA",
            })
            continue
        try:
            corr = float(np.corrcoef(x[mask], y[mask])[0, 1])
        except Exception:
            corr = float("nan")
        # Approximate p-value using t-distribution
        if not np.isnan(corr) and n > 2 and abs(corr) < 1.0:
            t_stat = corr * np.sqrt((n - 2) / (1 - corr * corr))
            from scipy.stats import t as t_dist
            p_val = float(2 * t_dist.sf(abs(t_stat), n - 2))
        else:
            p_val = float("nan")

        sig = "not_significant"
        if not np.isnan(p_val) and p_val < 0.05:
            sig = "significant" if corr > 0 else "significant_negative"

        rows.append({
            "factor": "",
            "lag": lag,
            "n_obs": n,
            "autocorr": corr,
            "p_value": p_val,
            "significance": sig,
        })

    return pd.DataFrame(rows)


def _ic_autocorrelation_summary(ac_df: pd.DataFrame, factor_name: str) -> Dict[str, Any]:
    """Summarize IC autocorrelation across three lag bands.

    Returns dict with:
      - lag_1_5_mean_autocorr
      - lag_6_20_mean_autocorr
      - lag_21_60_mean_autocorr
      - interpretation: IC_MOMENTUM | IC_REVERSAL | NO_STABLE_RELATION | INSUFFICIENT_DATA
    """
    if ac_df.empty:
        return {
            "factor": factor_name,
            "lag_1_5_mean_autocorr": float("nan"),
            "lag_6_20_mean_autocorr": float("nan"),
            "lag_21_60_mean_autocorr": float("nan"),
            "interpretation": "INSUFFICIENT_DATA",
        }

    def _band_mean(lo, hi):
        band = ac_df[(ac_df["lag"] >= lo) & (ac_df["lag"] <= hi)]
        valid = band["autocorr"].dropna()
        return float(valid.mean()) if len(valid) > 0 else float("nan")

    lag_1_5 = _band_mean(1, 5)
    lag_6_20 = _band_mean(6, 20)
    lag_21_60 = _band_mean(21, 60)

    # Interpretation
    early_autocorr = _band_mean(1, 10)
    if np.isnan(early_autocorr):
        interp = "INSUFFICIENT_DATA"
    elif early_autocorr > 0.03:
        interp = "IC_MOMENTUM"
    elif early_autocorr < -0.03:
        interp = "IC_REVERSAL"
    else:
        interp = "NO_STABLE_RELATION"

    return {
        "factor": factor_name,
        "lag_1_5_mean_autocorr": lag_1_5,
        "lag_6_20_mean_autocorr": lag_6_20,
        "lag_21_60_mean_autocorr": lag_21_60,
        "interpretation": interp,
    }


# ===========================================================================
# Trailing IC → Future IC relation diagnostic
# ===========================================================================

def _compute_trailing_ic_forward_relation(
    aligned_trailing: pd.DataFrame,
    daily_ic: pd.DataFrame,
    horizon: int = 20,
) -> Dict[str, Any]:
    """Test whether trailing IC predicts future IC (momentum or reversal).

    For each signal_date T where trailing_ic[T] is available:
      - Compute future_ic_mean[T] = mean(IC over [T, T+horizon])
      - Correlate future_ic_mean[T] ~ trailing_ic[T]

    Returns dict with:
      - factor
      - n_obs
      - corr
      - slope
      - p_value
      - direction (IC_MOMENTUM | IC_REVERSAL | NO_STABLE_RELATION)
      - interpretation (human-readable)
    """
    if aligned_trailing.empty or daily_ic.empty:
        return {
            "factor": "",
            "n_obs": 0,
            "corr": float("nan"),
            "slope": float("nan"),
            "p_value": float("nan"),
            "direction": "INSUFFICIENT_DATA",
            "interpretation": "No data available for trailing → forward relation test.",
        }

    # Index daily IC by trade_date
    ic_index = daily_ic.set_index("trade_date")["ic"].sort_index()

    # Build paired data
    pairs = []
    for _, row in aligned_trailing.iterrows():
        t = int(row["signal_date"])
        trai = row["trailing_ic"]
        if np.isnan(trai):
            continue
        # Future IC: mean of IC[t .. t+horizon-1] (available ICs in the forward window)
        future_dates = [d for d in ic_index.index if d >= t]
        if len(future_dates) < horizon:
            continue
        future_ics = ic_index.loc[future_dates[:horizon]]
        if future_ics.notna().sum() < 10:
            continue
        future_mean = float(future_ics.mean())
        pairs.append({"trailing_ic": trai, "future_ic_mean": future_mean})

    if len(pairs) < 20:
        return {
            "factor": "",
            "n_obs": len(pairs),
            "corr": float("nan"),
            "slope": float("nan"),
            "p_value": float("nan"),
            "direction": "INSUFFICIENT_DATA",
            "interpretation": f"Only {len(pairs)} valid signal dates (< 20 required).",
        }

    df = pd.DataFrame(pairs)
    n = len(df)
    corr_val = float(df["trailing_ic"].corr(df["future_ic_mean"]))

    # Linear regression slope
    try:
        from numpy.polynomial.polynomial import polyfit
        slope_val = float(np.polyfit(df["trailing_ic"], df["future_ic_mean"], 1)[0])
    except Exception:
        slope_val = float("nan")

    # p-value
    if not np.isnan(corr_val) and n > 2 and abs(corr_val) < 1.0:
        t_stat = corr_val * np.sqrt((n - 2) / (1 - corr_val * corr_val))
        from scipy.stats import t as t_dist
        p_val = float(2 * t_dist.sf(abs(t_stat), n - 2))
    else:
        p_val = float("nan")

    # Direction
    if not np.isnan(p_val) and p_val < 0.05:
        if corr_val > 0:
            direction = "IC_MOMENTUM"
            interp = (
                "Positive relationship: higher trailing IC predicts higher future IC. "
                "This supports using trailing IC as a style signal."
            )
        else:
            direction = "IC_REVERSAL"
            interp = (
                "Negative relationship: higher trailing IC predicts LOWER future IC. "
                "This suggests mean-reversion in factor IC — trailing IC signals "
                "may be contra-indicators. Do NOT use directly as a positive signal."
            )
    else:
        direction = "NO_STABLE_RELATION"
        interp = (
            "No stable linear relationship between trailing IC and future IC. "
            "Trailing IC cannot be used as a style signal predictor. "
            "This is the expected null result — most factor IC series are not "
            "predictable from their own past."
        )

    return {
        "factor": "",
        "n_obs": n,
        "corr": corr_val,
        "slope": slope_val,
        "p_value": p_val,
        "direction": direction,
        "interpretation": interp,
    }


# ===========================================================================
# Output: report
# ===========================================================================

def _write_report(out_dir: Path, validation: dict, style_df: pd.DataFrame,
                  mom_rep: Optional[str], val_rep: Optional[str], grw_rep: Optional[str],
                  mom_dropped: List[str], coverage_blocked: Optional[bool],
                  corr_matrix: Optional[pd.DataFrame],
                  args, selection_reasons: Optional[Dict] = None,
                  ic_autocorr_summaries: Optional[Dict] = None,
                  trail_fwd_results: Optional[Dict] = None):
    """Write style signal report in Markdown."""
    lines = []
    lines.append("# Factor Style Signal Validation Report")
    lines.append(f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"\n## Parameters")
    lines.append(f"\n| Parameter | Value |")
    lines.append(f"|-----------|-------|")
    lines.append(f"| start | {args.start} |")
    lines.append(f"| end | {args.end} |")
    lines.append(f"| lookback_days | {args.lookback} |")
    lines.append(f"| horizon_days | {args.horizon} |")
    lines.append(f"| trailing_ic_threshold | {args.threshold} |")
    lines.append(f"| mixed_margin | {MIXED_MARGIN} |")
    lines.append(f"| min_label_days | {MIN_DAYS_FOR_LABEL} |")
    lines.append(f"| min_median_coverage_pct | {MIN_MEDIAN_COVERAGE_PCT} |")
    lines.append(f"| min_yearly_coverage_pct | {MIN_YEARLY_COVERAGE_PCT} |")
    lines.append(f"| correlation_dedup_threshold | {CORRELATION_DEDUP_THRESHOLD} |")

    # Anti-leakage statement
    lines.append(f"\n## No-Leakage Assurance")
    lines.append(f"\n- **ic_available_date**: IC computed at factor_date is only knowable after "
                 f"factor_date + {args.horizon} trading days")
    lines.append(f"- **signal_date**: labels at T only use ICs with ic_available_date < T")
    lines.append(f"- **horizon**: {args.horizon} trading days forward")

    # Factor representatives
    lines.append(f"\n## Factor Group Representatives")
    lines.append(f"\n| Group | Representative | Mean IC | ICIR | Note |")
    lines.append(f"|-------|---------------|--------|------|------|")

    if selection_reasons and selection_reasons.get("representative"):
        sr = selection_reasons["representative"]
        lines.append(f"| Momentum | **{sr.get('name', mom_rep)}** | "
                     f"{sr.get('mean_ic', float('nan')):.4f} | "
                     f"{sr.get('icir', float('nan')):.4f} | "
                     f"{sr.get('reason', '')} |")
    else:
        lines.append(f"| Momentum | **{mom_rep}** | — | — | |")

    if mom_dropped:
        for d in mom_dropped:
            lines.append(f"| Momentum (dropped) | {d} | correlated | — | removed due to correlation > {CORRELATION_DEDUP_THRESHOLD} |")

    lines.append(f"| Value Repair | **{val_rep}** | — | — | |")
    lines.append(f"| Growth Quality | **{grw_rep}** | — | — | |")
    if coverage_blocked:
        lines.append(f"| Growth Quality | ⚠️ **DATA_COVERAGE_BLOCKED** | — | — | coverage below threshold |")

    # Style signal summary
    lines.append(f"\n## Style Signal Summary")
    lines.append(f"\n| Label | N Days | Mean IC | ICIR | Hit Rate | Top-Bottom | Net Spread | +Years | Status |")
    lines.append(f"|-------|--------|---------|------|----------|------------|------------|--------|--------|")

    for label in STYLE_LABELS:
        info = validation.get(label, {})
        n = info.get("n_days", 0)
        mic = info.get("mean_ic", float("nan"))
        icir = info.get("icir", float("nan"))
        hit = info.get("hit_rate", float("nan"))
        tbs = info.get("top_bottom_spread", float("nan"))
        ns = info.get("net_spread", float("nan"))
        py = info.get("positive_years", 0)
        st = info.get("status", "?")

        def _fmt(v):
            if isinstance(v, float) and np.isnan(v):
                return "—"
            return f"{v:.4f}"

        lines.append(f"| {label} | {n} | {_fmt(mic)} | {_fmt(icir)} | "
                     f"{_fmt(hit)} | {_fmt(tbs)} | {_fmt(ns)} | {py} | **{st}** |")

    # Failure reasons
    lines.append(f"\n## Status Details")
    for label in STYLE_LABELS:
        info = validation.get(label, {})
        fr = info.get("failure_reasons", [])
        st = info.get("status", "?")
        lines.append(f"\n### {label} — {st}")
        if fr:
            for r in fr:
                lines.append(f"- ❌ {r}")
        else:
            lines.append(f"- ✅ No issues")

    # Predictive power assessment
    lines.append(f"\n## Predictive Power Assessment")
    mom_result = validation.get("momentum_on", {})
    no_style = validation.get("no_clear_style", {})
    if mom_result.get("status") == "NO_PREDICTIVE_POWER":
        lines.append(f"\n❌ **momentum_on does NOT have predictive power** — "
                     f"mean IC ({mom_result.get('mean_ic', float('nan')):.4f}) "
                     f"≤ no_clear_style baseline ({no_style.get('mean_ic', float('nan')):.4f})")
    elif mom_result.get("status") == "OK":
        lines.append(f"\n✅ **momentum_on shows predictive power** — "
                     f"mean IC ({mom_result.get('mean_ic', float('nan')):.4f}) "
                     f"> no_clear_style baseline ({no_style.get('mean_ic', float('nan')):.4f})")

    val_result = validation.get("value_repair_on", {})
    if val_result.get("status") == "NO_PREDICTIVE_POWER":
        lines.append(f"\n❌ **value_repair_on does NOT have predictive power** — "
                     f"mean IC ({val_result.get('mean_ic', float('nan')):.4f}) "
                     f"≤ no_clear_style baseline ({no_style.get('mean_ic', float('nan')):.4f})")
    elif val_result.get("status") == "OK":
        lines.append(f"\n✅ **value_repair_on shows predictive power** — "
                     f"mean IC ({val_result.get('mean_ic', float('nan')):.4f}) "
                     f"> no_clear_style baseline ({no_style.get('mean_ic', float('nan')):.4f})")

    # Growth coverage note
    if coverage_blocked:
        lines.append(f"\n⚠️ **growth_quality_watch** is DATA_COVERAGE_BLOCKED — "
                     f"earnings_acceleration_cs has insufficient stock coverage. "
                     f"Not usable as a formal style signal until income data is expanded.")

    # Year distribution
    lines.append(f"\n## Year Distribution")
    if not style_df.empty:
        style_df_copy = style_df.copy()
        style_df_copy["year"] = style_df_copy["signal_date"] // 10000
        year_label = style_df_copy.groupby(["year", "style_label"]).size().unstack(fill_value=0)
        for lbl in STYLE_LABELS:
            if lbl not in year_label.columns:
                year_label[lbl] = 0
        year_label = year_label[STYLE_LABELS]
        lines.append(f"\n```")
        lines.append(year_label.to_string())
        lines.append(f"\n```")

    # Correlation matrix (if available)
    if corr_matrix is not None and not corr_matrix.empty:
        lines.append(f"\n## Factor Correlation Matrix")
        lines.append(f"\n```")
        lines.append(corr_matrix.to_string())
        lines.append(f"\n```")

    # ---- IC Autocorrelation Diagnostics ----
    if ic_autocorr_summaries:
        lines.append(f"\n## IC Autocorrelation Analysis")
        lines.append(f"\nTests whether a factor's daily IC exhibits momentum "
                     f"(positive autocorrelation) or reversal (negative "
                     f"autocorrelation). This explains *why* trailing IC may "
                     f"or may not predict future IC.")
        lines.append(f"\n| Factor | Lag 1-5 Mean AC | Lag 6-20 Mean AC | "
                     f"Lag 21-60 Mean AC | Interpretation |")
        lines.append(f"|--------|----------------|-----------------|"
                     f"-----------------|----------------|")
        for fn, summary in ic_autocorr_summaries.items():
            def _f(v):
                if isinstance(v, float) and np.isnan(v):
                    return "—"
                return f"{v:.4f}"
            lines.append(
                f"| {fn} | {_f(summary.get('lag_1_5_mean_autocorr'))} | "
                f"{_f(summary.get('lag_6_20_mean_autocorr'))} | "
                f"{_f(summary.get('lag_21_60_mean_autocorr'))} | "
                f"**{summary.get('interpretation', '?')}** |"
            )

        # Root cause analysis
        lines.append(f"\n### Root Cause Analysis")
        for fn, summary in ic_autocorr_summaries.items():
            interp = summary.get("interpretation", "?")
            if interp == "NO_STABLE_RELATION":
                lines.append(f"\n- **{fn}**: IC series shows no stable autocorrelation. "
                             f"Trailing IC cannot predict future IC because there is "
                             f"no persistence in the underlying IC process.")
            elif interp == "IC_REVERSAL":
                lines.append(f"\n- **{fn}**: IC series shows significant NEGATIVE "
                             f"autocorrelation. High IC days tend to be followed by "
                             f"low IC days. This explains why trailing IC is a "
                             f"contra-indicator rather than a positive signal.")
            elif interp == "IC_MOMENTUM":
                lines.append(f"\n- **{fn}**: IC series shows positive autocorrelation. "
                             f"Trailing IC may have predictive power — but check the "
                             f"trailing→forward relation test for horizon-specific "
                             f"confirmation.")

    # ---- Trailing IC → Future IC Relation ----
    if trail_fwd_results:
        lines.append(f"\n## Trailing IC → Future IC Predictive Test")
        lines.append(f"\nDirect test: does trailing IC[T] predict mean IC over "
                     f"[T, T+horizon]?")
        lines.append(f"\n| Factor | N Obs | Corr | Slope | p-value | Direction |")
        lines.append(f"|--------|-------|------|-------|---------|-----------|")
        for fn, result in trail_fwd_results.items():
            n = result.get("n_obs", 0)
            corr = result.get("corr", float("nan"))
            slope = result.get("slope", float("nan"))
            p = result.get("p_value", float("nan"))
            direction = result.get("direction", "?")
            def _f2(v):
                if isinstance(v, float) and np.isnan(v):
                    return "—"
                return f"{v:.4f}"
            lines.append(
                f"| {fn} | {n} | {_f2(corr)} | {_f2(slope)} | "
                f"{_f2(p)} | **{direction}** |"
            )

        lines.append(f"\n### Conclusion on Trailing IC as Style Signal")
        for fn, result in trail_fwd_results.items():
            direction = result.get("direction", "?")
            if direction == "NO_STABLE_RELATION":
                lines.append(f"\n- **{fn}**: Trailing IC does NOT predict future IC. "
                             f"This factor's trailing IC should NOT be used as a "
                             f"style signal. The current momentum_on / value_repair_on "
                             f"label approach is not supported by the data.")
            elif direction == "IC_REVERSAL":
                lines.append(f"\n- **{fn}**: Trailing IC NEGATIVELY predicts future IC. "
                             f"While this is a real statistical relationship, it should "
                             f"NOT be used directly for trading without further research "
                             f"into the economic mechanism.")
            elif direction == "IC_MOMENTUM":
                lines.append(f"\n- **{fn}**: Trailing IC positively predicts future IC. "
                             f"This supports using trailing IC as a style allocation "
                             f"signal.")

    report_path = out_dir / "style_signal_report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")


# ===========================================================================
# Output: manifest
# ===========================================================================

def _write_manifest(out_dir: Path, manifest_data: Dict[str, Any]):
    """Write style_signal_validation_manifest.json."""
    manifest_path = out_dir / "style_signal_validation_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest_data, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8"
    )


# ===========================================================================
# Main
# ===========================================================================

def main() -> int:
    parser = argparse.ArgumentParser(description="Factor Style Signal Validation")
    parser.add_argument("--start", default="20170101")
    parser.add_argument("--end", default="20241231")
    parser.add_argument("--lookback", type=int, default=MOMENTUM_LOOKBACK,
                        help="Trading days for trailing IC computation")
    parser.add_argument("--horizon", type=int, default=FORWARD_HORIZON,
                        help="Forward trading days for validation")
    parser.add_argument("--threshold", type=float, default=TRAILING_IC_THRESHOLD,
                        help="Min trailing IC to declare a style active")
    parser.add_argument("--mixed-margin", type=float, default=MIXED_MARGIN,
                        help="Min IC difference to distinguish momentum vs value")
    parser.add_argument("--warmup-start", default=None,
                        help="Optional: allow IC training data from this date (YYYMMDD) "
                             "before main --start period")
    args = parser.parse_args()

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = ROOT / "outputs" / "analysis" / "factor_style_signal_validation" / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    start_int = int(args.start)
    end_int = int(args.end)
    warmup_start_int = int(args.warmup_start) if args.warmup_start else start_int

    print(f"=== Factor Style Signal Validation ===")
    print(f"Run: {run_id}")
    print(f"Period: {args.start} → {args.end}")
    print(f"Warmup start: {warmup_start_int}")
    print(f"Lookback: {args.lookback}d, Horizon: {args.horizon}d")
    print(f"Threshold: {args.threshold}, Mixed margin: {args.mixed_margin}")
    print()

    # ------------------------------------------------------------------
    # 0. Load trading calendar
    # ------------------------------------------------------------------
    print("Loading trading calendar...")
    cal = _get_calendar()
    if cal is not None:
        print(f"  Calendar loaded: {len(cal.trade_dates)} trading days")
    else:
        print("  WARNING: Trading calendar unavailable, using calendar-day fallback")

    # ------------------------------------------------------------------
    # 1. Load factor data
    # ------------------------------------------------------------------
    print("\nLoading factor caches...")
    factor_data: Dict[str, pd.DataFrame] = {}
    missing_factors = []

    for fn in ALL_FACTORS:
        df = _load_factor_cache(fn)
        if df.empty:
            missing_factors.append(fn)
            print(f"  {fn}: MISSING")
        else:
            factor_data[fn] = df
            n_stocks = df["ts_code"].nunique()
            n_dates = df["trade_date"].nunique()
            print(f"  {fn}: {len(df)} rows, {n_stocks} stocks, {n_dates} dates")

    if missing_factors:
        print(f"\nWARNING: {len(missing_factors)} factors missing cache:")
        for mf in missing_factors:
            print(f"  - {mf}")

    # ------------------------------------------------------------------
    # 2. Load forward returns
    # ------------------------------------------------------------------
    print("\nLoading forward returns...")
    fwd = _load_fwd_returns()
    if fwd.empty:
        print("  ERROR: No forward return data available!")
        return 1
    print(f"  {len(fwd)} rows, columns: {fwd.columns.tolist()}")

    # Determine horizon column
    horizon_col = f"fwd_ret_{args.horizon}d"
    if horizon_col not in fwd.columns:
        available = [c for c in fwd.columns if "fwd_ret" in c]
        if available:
            horizon_col = available[-1]
            print(f"  Using {horizon_col} (closest to {args.horizon}d)")
        else:
            print("  ERROR: No fwd_ret columns in forward returns!")
            return 1

    # ------------------------------------------------------------------
    # 3. Filter by date range
    # ------------------------------------------------------------------
    print(f"\nFiltering data to [{args.start}, {args.end}]...")

    # For IC *computation* we use warmup_start to end (to have enough
    # history for trailing IC), but labels only for [start, end].
    factor_data_filtered = {}
    for fn, df in factor_data.items():
        factor_data_filtered[fn] = _filter_by_date_range(df, warmup_start_int, end_int)

    fwd_filtered = _filter_by_date_range(fwd, warmup_start_int, end_int)

    n_factor_rows = sum(len(df) for df in factor_data_filtered.values())
    n_fwd_rows = len(fwd_filtered)

    # Count signal dates in [start, end]
    if cal is not None:
        signal_dates = cal.trade_days_between(start_int, end_int)
    else:
        # Fallback: all dates in fwd_filtered in range
        signal_dates = np.array(sorted(
            d for d in fwd_filtered["trade_date"].unique()
            if start_int <= d <= end_int
        ))

    print(f"  Factor rows (warmup→end): {n_factor_rows}")
    print(f"  Forward return rows (warmup→end): {n_fwd_rows}")
    print(f"  Signal dates [start, end]: {len(signal_dates)}")
    print(f"  Signal date range: {signal_dates[0]} → {signal_dates[-1]}" if len(signal_dates) > 0 else "  NO signal dates!")

    if len(signal_dates) == 0:
        print("ERROR: No signal dates in specified range!")
        return 1

    # ------------------------------------------------------------------
    # 4. Compute coverage (for growth factors)
    # ------------------------------------------------------------------
    print("\nComputing factor coverage...")
    coverage_info: Dict[str, Dict[str, Any]] = {}
    growth_coverage_blocked = False

    for fn in GROWTH_QUALITY_FACTORS:
        if fn not in factor_data_filtered:
            continue
        cov_df = _compute_coverage(factor_data_filtered[fn], fwd_filtered)
        cov_eval = _evaluate_coverage(cov_df)
        coverage_info[fn] = cov_eval
        print(f"  {fn}: median_coverage={cov_eval['median_coverage_pct']:.1%}, "
              f"min_yearly={cov_eval['min_yearly_coverage_pct']:.1%}, "
              f"blocked={cov_eval['coverage_blocked']}")
        if cov_eval["coverage_blocked"]:
            growth_coverage_blocked = True

    # Also compute coverage for momentum and value (for reporting)
    for fn in MOMENTUM_FACTORS + VALUE_REPAIR_FACTORS:
        if fn not in factor_data_filtered:
            continue
        cov_df = _compute_coverage(factor_data_filtered[fn], fwd_filtered)
        cov_eval = _evaluate_coverage(cov_df)
        coverage_info[fn] = cov_eval
        print(f"  {fn}: median_coverage={cov_eval['median_coverage_pct']:.1%}, "
              f"blocked={cov_eval['coverage_blocked']}")

    # ------------------------------------------------------------------
    # 5. Compute daily ICs for each factor
    # ------------------------------------------------------------------
    print("\nComputing daily ICs...")
    factor_daily_ics: Dict[str, pd.DataFrame] = {}

    for fn, fdf in factor_data_filtered.items():
        if fdf.empty:
            continue
        daily_ic = _compute_daily_ic(fdf, fwd_filtered, horizon_col)
        if not daily_ic.empty:
            factor_daily_ics[fn] = daily_ic
            print(f"  {fn}: {len(daily_ic)} IC dates, mean={daily_ic['ic'].mean():.4f}")
        else:
            print(f"  {fn}: NO IC DATA")

    # ------------------------------------------------------------------
    # 6. Map ICs to available dates (LOOK-AHEAD FIX)
    # ------------------------------------------------------------------
    print("\nMapping ICs to available dates (no-leakage alignment)...")
    ic_mapped: Dict[str, pd.DataFrame] = {}

    for fn, daily_ic in factor_daily_ics.items():
        mapped = _map_ic_to_available_date(daily_ic, cal, args.horizon)
        if not mapped.empty:
            ic_mapped[fn] = mapped
            print(f"  {fn}: {len(mapped)} ICs mapped, "
                  f"available range {mapped['ic_available_date'].min()} → {mapped['ic_available_date'].max()}")
        else:
            print(f"  {fn}: NO mapped ICs")

    # ------------------------------------------------------------------
    # 7. Compute trailing ICs on available date axis
    # ------------------------------------------------------------------
    print("\nComputing trailing ICs on available-date axis...")
    trailing_on_avail: Dict[str, pd.DataFrame] = {}

    for fn, mapped in ic_mapped.items():
        trailing = _compute_trailing_ic_on_available_axis(mapped, args.lookback)
        if not trailing.empty:
            trailing_on_avail[fn] = trailing
            print(f"  {fn}: {len(trailing)} trailing IC dates, "
                  f"mean={trailing['trailing_ic'].mean():.4f}")
        else:
            print(f"  {fn}: NO trailing ICs")

    # ------------------------------------------------------------------
    # 8. Align trailing ICs to signal dates
    # ------------------------------------------------------------------
    print("\nAligning trailing ICs to signal dates...")
    aligned: Dict[str, pd.DataFrame] = {}

    for fn, trailing in trailing_on_avail.items():
        al = _align_trailing_to_signal_dates(trailing, signal_dates)
        if not al.empty:
            aligned[fn] = al
            n_valid = al["trailing_ic"].notna().sum()
            print(f"  {fn}: {len(al)} signal dates, {n_valid} with valid trailing IC")
        else:
            print(f"  {fn}: NO aligned signal dates")

    # ------------------------------------------------------------------
    # 9. Correlation dedup for momentum
    # ------------------------------------------------------------------
    print("\nDeduplicating momentum factors...")
    mom_ics_for_dedup = {fn: factor_daily_ics[fn] for fn in MOMENTUM_FACTORS
                         if fn in factor_daily_ics}
    mom_rep, mom_dropped, corr_matrix, selection_reasons = (
        _dedup_momentum_factors(mom_ics_for_dedup, coverage_info)
    )

    print(f"  Momentum representative: {mom_rep}")
    if mom_dropped:
        print(f"  Dropped (correlated): {', '.join(mom_dropped)}")
    if not corr_matrix.empty:
        print(f"  Correlation matrix:")
        print(corr_matrix.to_string())

    # Get aligned trailing ICs for representatives
    mom_aligned = aligned.get(mom_rep, pd.DataFrame()) if mom_rep else pd.DataFrame()
    val_rep = VALUE_REPAIR_FACTORS[0] if VALUE_REPAIR_FACTORS else None
    val_aligned = aligned.get(val_rep, pd.DataFrame()) if val_rep else pd.DataFrame()
    grw_rep = GROWTH_QUALITY_FACTORS[0] if GROWTH_QUALITY_FACTORS else None
    grw_aligned = aligned.get(grw_rep, pd.DataFrame()) if grw_rep else pd.DataFrame()

    # ------------------------------------------------------------------
    # 10. Classify style signals
    # ------------------------------------------------------------------
    print("\nClassifying style signals...")
    if mom_aligned.empty:
        print("  WARNING: No momentum aligned data — all dates will be no_clear_style")
        mom_aligned = pd.DataFrame({"signal_date": signal_dates, "trailing_ic": np.nan,
                                     "n_ic_obs": 0, "latest_factor_date": np.nan,
                                     "latest_ic_available_date": np.nan})

    style_df = _classify_style_signals(
        mom_aligned, val_aligned, grw_aligned,
        threshold=args.threshold,
        mixed_margin=args.mixed_margin,
        growth_coverage_blocked=growth_coverage_blocked,
    )

    label_counts = style_df["style_label"].value_counts()
    for label in STYLE_LABELS:
        count = int(label_counts.get(label, 0))
        print(f"  {label}: {count} dates")

    # ------------------------------------------------------------------
    # 11. Forward validation
    # ------------------------------------------------------------------
    print(f"\nValidating style signals (forward {args.horizon}d)...")
    # Build factor_ic_map with representative factor ICs
    factor_ic_map = {}
    if mom_rep and mom_rep in factor_daily_ics:
        factor_ic_map[mom_rep] = factor_daily_ics[mom_rep]
    if val_rep and val_rep in factor_daily_ics:
        factor_ic_map[val_rep] = factor_daily_ics[val_rep]
    if grw_rep and grw_rep in factor_daily_ics:
        factor_ic_map[grw_rep] = factor_daily_ics[grw_rep]

    validation = _validate_style_signals(
        style_df,
        factor_ic_map,
        factor_data_filtered,
        fwd_filtered,
        horizon_col,
        momentum_rep=mom_rep,
        value_rep=val_rep,
        growth_rep=grw_rep,
        growth_coverage_blocked=growth_coverage_blocked,
    )

    for label, info in validation.items():
        st = info.get("status", "?")
        n = info.get("n_days", 0)
        mic = info.get("mean_ic", float("nan"))
        mic_s = f"{mic:.4f}" if not (isinstance(mic, float) and np.isnan(mic)) else "—"
        print(f"  {label}: n={n}, mean_ic={mic_s}, status={st}")

    # ------------------------------------------------------------------
    # 12. IC autocorrelation diagnostics
    # ------------------------------------------------------------------
    print(f"\n=== IC Autocorrelation Diagnostics ===")
    ic_autocorr_results: Dict[str, pd.DataFrame] = {}
    ic_autocorr_summaries: Dict[str, Dict[str, Any]] = {}

    diagnostic_factors = [mom_rep, val_rep, grw_rep]
    diagnostic_labels = ["momentum", "value_repair", "growth_quality"]

    for fn, label in zip(diagnostic_factors, diagnostic_labels):
        if fn and fn in factor_daily_ics:
            daily_ic = factor_daily_ics[fn]
            ac_df = _compute_ic_autocorrelation(daily_ic, max_lag=60)
            ac_df["factor"] = fn
            ic_autocorr_results[fn] = ac_df
            summary = _ic_autocorrelation_summary(ac_df, fn)
            ic_autocorr_summaries[fn] = summary
            print(f"  {fn}:")
            print(f"    lag 1-5  mean autocorr: {summary.get('lag_1_5_mean_autocorr', float('nan')):.4f}" if not np.isnan(summary.get('lag_1_5_mean_autocorr', float('nan'))) else f"    lag 1-5  mean autocorr: —")
            print(f"    lag 6-20 mean autocorr: {summary.get('lag_6_20_mean_autocorr', float('nan')):.4f}" if not np.isnan(summary.get('lag_6_20_mean_autocorr', float('nan'))) else f"    lag 6-20 mean autocorr: —")
            print(f"    lag 21-60 mean autocorr: {summary.get('lag_21_60_mean_autocorr', float('nan')):.4f}" if not np.isnan(summary.get('lag_21_60_mean_autocorr', float('nan'))) else f"    lag 21-60 mean autocorr: —")
            print(f"    interpretation: {summary.get('interpretation', '?')}")
        else:
            print(f"  {label} ({fn}): SKIPPED (no IC data)")

    # ------------------------------------------------------------------
    # 13. Trailing IC → Future IC relation
    # ------------------------------------------------------------------
    print(f"\n=== Trailing IC → Future IC Relation ===")
    trail_fwd_results: Dict[str, Dict[str, Any]] = {}

    for fn, label in zip(diagnostic_factors, diagnostic_labels):
        if fn and fn in aligned and fn in factor_daily_ics:
            result = _compute_trailing_ic_forward_relation(
                aligned[fn], factor_daily_ics[fn], args.horizon
            )
            result["factor"] = fn
            trail_fwd_results[fn] = result
            print(f"  {fn}:")
            print(f"    n_obs={result['n_obs']}, corr={result['corr']:.4f}, "
                  f"slope={result['slope']:.4f}, p={result['p_value']:.4f}" if not np.isnan(result.get('p_value', float('nan'))) else f"    n_obs={result['n_obs']}, corr=—, slope=—, p=—")
            print(f"    direction: {result['direction']}")
            print(f"    interpretation: {result['interpretation'][:120]}...")
        else:
            trail_fwd_results[fn] = {
                "factor": fn, "direction": "INSUFFICIENT_DATA",
                "interpretation": "No aligned trailing IC data available.",
            }
            print(f"  {label} ({fn}): INSUFFICIENT_DATA")

    # ------------------------------------------------------------------
    # 14. Outputs
    # ------------------------------------------------------------------
    print(f"\nWriting outputs to {out_dir}...")

    # 12a. style_signal_summary.csv
    summary_rows = []
    for label in STYLE_LABELS:
        info = validation.get(label, {})
        row = {"style_label": label}
        # Core metrics
        for key in ["n_days", "mean_ic", "icir", "hit_rate",
                     "top_bottom_spread", "top_quintile_excess",
                     "estimated_cost", "net_spread",
                     "positive_years", "max_year_contribution",
                     "status"]:
            row[key] = info.get(key)
        # Serialize lists/dicts
        row["failure_reasons"] = " | ".join(info.get("failure_reasons", []))
        row["yearly_ic"] = json.dumps(info.get("_yearly_ic", {}))
        row["yearly_count"] = json.dumps(info.get("_yearly_count", {}))
        summary_rows.append(row)
    pd.DataFrame(summary_rows).to_csv(
        out_dir / "style_signal_summary.csv", index=False, encoding="utf-8-sig"
    )
    print("  ✓ style_signal_summary.csv")

    # 12b. style_signal_by_year.csv
    if not style_df.empty:
        style_df_copy = style_df.copy()
        style_df_copy["year"] = style_df_copy["signal_date"] // 10000
        year_counts = style_df_copy.groupby(["year", "style_label"]).size().reset_index(name="n_days")
        year_counts.to_csv(out_dir / "style_signal_by_year.csv", index=False, encoding="utf-8-sig")
        print("  ✓ style_signal_by_year.csv")

    # 12c. factor_style_lead_lag.csv
    lead_lag_rows = []
    if not style_df.empty:
        style_df_copy = style_df.copy()
        style_df_copy["year"] = style_df_copy["signal_date"] // 10000
        for year, ydf in style_df_copy.groupby("year"):
            for label in STYLE_LABELS:
                ld = ydf[ydf["style_label"] == label]
                if len(ld) < 5:
                    continue
                row_data = {
                    "year": year,
                    "style_label": label,
                    "n_days": len(ld),
                }
                # Trailing IC stats
                for col, prefix in [("mom_ic", "mom"), ("val_ic", "val"), ("grw_ic", "grw")]:
                    if col in ld.columns:
                        row_data[f"mean_{prefix}_trailing_ic"] = ld[col].mean()
                        row_data[f"std_{prefix}_trailing_ic"] = ld[col].std()

                # Latest factor dates (report the range)
                for col, prefix in [("mom_latest_factor_date", "mom"),
                                     ("val_latest_factor_date", "val"),
                                     ("grw_latest_factor_date", "grw")]:
                    if col in ld.columns:
                        vals = ld[col].dropna()
                        if len(vals) > 0:
                            row_data[f"{prefix}_factor_date_min"] = int(vals.min())
                            row_data[f"{prefix}_factor_date_max"] = int(vals.max())

                lead_lag_rows.append(row_data)

    pd.DataFrame(lead_lag_rows).to_csv(
        out_dir / "factor_style_lead_lag.csv", index=False, encoding="utf-8-sig"
    )
    print("  ✓ factor_style_lead_lag.csv")

    # 12d. ic_autocorrelation.csv
    if ic_autocorr_results:
        all_autocorr = pd.concat(ic_autocorr_results.values(), ignore_index=True)
        all_autocorr.to_csv(out_dir / "ic_autocorrelation.csv", index=False, encoding="utf-8-sig")
        print("  ✓ ic_autocorrelation.csv")
    else:
        pd.DataFrame({"note": ["no IC autocorrelation data available"]}).to_csv(
            out_dir / "ic_autocorrelation.csv", index=False, encoding="utf-8-sig"
        )
        print("  ✓ ic_autocorrelation.csv (empty)")

    # 12e. trailing_ic_forward_relation.csv
    trail_fwd_rows = []
    for fn, result in trail_fwd_results.items():
        trail_fwd_rows.append({
            "factor": result.get("factor", fn),
            "n_obs": result.get("n_obs", 0),
            "corr": result.get("corr", float("nan")),
            "slope": result.get("slope", float("nan")),
            "p_value": result.get("p_value", float("nan")),
            "direction": result.get("direction", "?"),
            "interpretation": result.get("interpretation", ""),
        })
    pd.DataFrame(trail_fwd_rows).to_csv(
        out_dir / "trailing_ic_forward_relation.csv", index=False, encoding="utf-8-sig"
    )
    print("  ✓ trailing_ic_forward_relation.csv")

    # 12f. factor_correlation_matrix.csv
    if not corr_matrix.empty:
        corr_matrix.to_csv(out_dir / "factor_correlation_matrix.csv", encoding="utf-8-sig")
        print("  ✓ factor_correlation_matrix.csv")
    else:
        # Write empty with note
        pd.DataFrame({"note": ["no correlation data available"]}).to_csv(
            out_dir / "factor_correlation_matrix.csv", index=False, encoding="utf-8-sig"
        )
        print("  ✓ factor_correlation_matrix.csv (empty)")

    # 12e. style_signal_candidate_pool.yaml
    candidate_pool = {
        "schema": "research_candidates.v2",
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "run_id": run_id,
        "eligible_factors": [],  # NOT modifying production gate
        "research_candidates": {
            "momentum_representative": mom_rep,
            "momentum_dropped_correlated": mom_dropped,
            "value_repair_representative": val_rep,
            "growth_quality_representative": grw_rep,
            "growth_coverage_blocked": growth_coverage_blocked,
        },
        "style_signals": {
            label: {
                "n_days": validation.get(label, {}).get("n_days", 0),
                "mean_ic": validation.get(label, {}).get("mean_ic"),
                "icir": validation.get(label, {}).get("icir"),
                "hit_rate": validation.get(label, {}).get("hit_rate"),
                "status": validation.get(label, {}).get("status"),
                "failure_reasons": validation.get(label, {}).get("failure_reasons", []),
            }
            for label in STYLE_LABELS
        },
        "parameters": {
            "start": args.start,
            "end": args.end,
            "lookback_days": args.lookback,
            "horizon_days": args.horizon,
            "trailing_ic_threshold": args.threshold,
            "mixed_margin": args.mixed_margin,
        },
        "no_leakage": {
            "enabled": True,
            "ic_available_after_horizon": True,
            "horizon_trading_days": args.horizon,
            "description": "IC mapped to ic_available_date = factor_date + horizon trading days; "
                          "labels only use ICs with ic_available_date < signal_date",
        },
    }
    with open(out_dir / "style_signal_candidate_pool.yaml", "w", encoding="utf-8") as f:
        yaml.dump(candidate_pool, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    print("  ✓ style_signal_candidate_pool.yaml")

    # 12f. style_signal_report.md
    _write_report(out_dir, validation, style_df, mom_rep, val_rep, grw_rep,
                  mom_dropped, growth_coverage_blocked, corr_matrix, args,
                  selection_reasons,
                  ic_autocorr_summaries=ic_autocorr_summaries,
                  trail_fwd_results=trail_fwd_results)
    print("  ✓ style_signal_report.md")

    # 12g. style_signal_validation_manifest.json
    manifest = {
        "schema": "style_signal_validation_manifest.v1",
        "run_id": run_id,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "script": "evaluate_factor_style_signals.py",
        "parameters": {
            "start": args.start,
            "end": args.end,
            "warmup_start": args.warmup_start,
            "lookback_days": args.lookback,
            "horizon_days": args.horizon,
            "trailing_ic_threshold": args.threshold,
            "mixed_margin": args.mixed_margin,
        },
        "data_summary": {
            "start": args.start,
            "end": args.end,
            "n_factor_rows": n_factor_rows,
            "n_fwd_rows": n_fwd_rows,
            "n_signal_dates": len(signal_dates),
            "signal_date_range": [int(signal_dates[0]), int(signal_dates[-1])] if len(signal_dates) > 0 else [],
        },
        "factor_coverage": {
            fn: {
                "median_coverage_pct": coverage_info[fn].get("median_coverage_pct"),
                "min_yearly_coverage_pct": coverage_info[fn].get("min_yearly_coverage_pct"),
                "coverage_blocked": coverage_info[fn].get("coverage_blocked"),
                "coverage_status": coverage_info[fn].get("coverage_status"),
            }
            for fn in ALL_FACTORS if fn in coverage_info
        },
        "no_leakage": {
            "enabled": True,
            "ic_available_after_horizon": True,
            "horizon_trading_days": args.horizon,
            "alignment_method": "trading_calendar_next_trade_day",
            "description": "IC[factor_date] → ic_available_date = cal.next_trade_day(factor_date, horizon). "
                          "Trailing IC computed on ic_available_date axis. "
                          "Labels at signal_date T only use ICs with ic_available_date < T.",
        },
        "representatives": {
            "momentum": mom_rep,
            "momentum_dropped": mom_dropped,
            "value_repair": val_rep,
            "growth_quality": grw_rep,
        },
        "label_summary": {
            label: {
                "n_days": int(label_counts.get(label, 0)),
                "pct_of_total": float(label_counts.get(label, 0) / max(len(style_df), 1)),
                "status": validation.get(label, {}).get("status"),
            }
            for label in STYLE_LABELS
        },
        "files": {
            "style_signal_summary.csv": str(out_dir / "style_signal_summary.csv"),
            "style_signal_by_year.csv": str(out_dir / "style_signal_by_year.csv"),
            "factor_style_lead_lag.csv": str(out_dir / "factor_style_lead_lag.csv"),
            "ic_autocorrelation.csv": str(out_dir / "ic_autocorrelation.csv"),
            "trailing_ic_forward_relation.csv": str(out_dir / "trailing_ic_forward_relation.csv"),
            "factor_correlation_matrix.csv": str(out_dir / "factor_correlation_matrix.csv"),
            "style_signal_candidate_pool.yaml": str(out_dir / "style_signal_candidate_pool.yaml"),
            "style_signal_report.md": str(out_dir / "style_signal_report.md"),
            "style_signal_validation_manifest.json": str(out_dir / "style_signal_validation_manifest.json"),
        },
        "ic_autocorrelation": {
            fn: summary
            for fn, summary in ic_autocorr_summaries.items()
        } if ic_autocorr_summaries else {},
        "trailing_ic_forward_relation": {
            fn: {
                "n_obs": result.get("n_obs"),
                "corr": result.get("corr"),
                "slope": result.get("slope"),
                "p_value": result.get("p_value"),
                "direction": result.get("direction"),
            }
            for fn, result in trail_fwd_results.items()
        } if trail_fwd_results else {},
    }
    _write_manifest(out_dir, manifest)
    print("  ✓ style_signal_validation_manifest.json")

    print(f"\nDone. Output: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

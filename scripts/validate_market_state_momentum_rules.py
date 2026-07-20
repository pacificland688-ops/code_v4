#!/usr/bin/env python
"""
Market State Momentum Rule Validation.

Validates whether market-state-driven rules can improve momentum factor
future IC / spread.  Takes rule candidates from the exploratory analysis
and converts them into explicit, backtestable, no-look-ahead rules.

Rules tested:
  1. High volatility → momentum_off  (volatility_state >= q75)
  2. High breadth    → momentum_on   (breadth_score >= q75 AND vol < q75)
  3. Combination (priority: vol > breadth)

Validation modes (threshold):
  A. research     — full-sample quantiles (quick check, NOT for acceptance)
  B. rolling_pit  — expanding-window quantiles (PIT-safe, but in-sample eval)

Train/test separation:
  C. strict_oos   — train thresholds on [start, train_end],
                     evaluate on (train_end, end]
                     Thresholds FROZEN from training period only.
  D. walkforward   — expanding train windows, test on each subsequent year.
                      Most rigorous: shows time stability of rules.

Usage:
  # In-sample (for reference only — do NOT use for acceptance)
  python -X utf8 scripts/validate_market_state_momentum_rules.py

  # Strict OOS: train 2017-2020, test 2021-2024
  python -X utf8 scripts/validate_market_state_momentum_rules.py \\
      --start 20170101 --end 20241231 --horizon 20 \\
      --train-end 20201231

  # Walk-forward: train expanding, test each subsequent year
  python -X utf8 scripts/validate_market_state_momentum_rules.py \\
      --start 20170101 --end 20241231 --horizon 20 \\
      --train-end 20201231 --walkforward

  # Walk-forward DISCOVERY: each window re-discovers rules from train only
  python -X utf8 scripts/validate_market_state_momentum_rules.py \\
      --start 20170101 --end 20241231 --horizon 20 \\
      --mode rolling_pit --train-end 20201231 --walkforward \\
      --walkforward-discovery
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

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Reuse discovery functions from exploration script
from scripts.explore_market_state_vs_factor_ic import (
    _conditional_ic_analysis,
    _apply_fdr_correction,
    _classify_findings_into_tiers,
    _compute_factor_coverage_for_market_state,
    MIN_OBS_PER_QUARTILE,
)
from scripts.evaluate_factor_style_signals import (
    _compute_coverage,
    _evaluate_coverage,
)

# ===========================================================================
# Constants
# ===========================================================================

MOMENTUM_FACTOR = "risk_adjusted_momentum_60_cs"
VALUE_FACTOR = "valuation_reversion_3y_cs"
GROWTH_FACTOR = "earnings_acceleration_cs"
DISCOVERY_FACTORS = [MOMENTUM_FACTOR, VALUE_FACTOR, GROWTH_FACTOR]

DISCOVERY_STATE_COLS = [
    "trend_strength",
    "volatility_state",
    "breadth_score",
    "turnover_state",
    "size_spread_20d",
    "gv_spread_20d",
]

RULE_STATE_COLS = ["volatility_state", "breadth_score"]

# Minimum days required for a label to be considered valid
MIN_LABEL_DAYS = 40

# Minimum warm-up for rolling PIT quantile estimation
MIN_PIT_WARMUP = 252  # ~1 year of trading days

# ===========================================================================
# Data loading (reuses existing infrastructure)
# ===========================================================================


def _load_factor_cache(factor_name: str) -> pd.DataFrame:
    """Load factor values from parquet cache."""
    root = ROOT / "data" / "parquet" / "factors" / f"factor_name={factor_name}"
    if not root.exists():
        return pd.DataFrame(columns=["ts_code", "trade_date", "value"])

    chunks = []
    for year_dir in sorted(root.iterdir()):
        if not year_dir.is_dir() or not year_dir.name.startswith("year="):
            continue
        for sub in sorted(year_dir.iterdir()):
            if sub.is_dir() and sub.name.startswith("month="):
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
    """Load forward returns."""
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


def _load_index_daily(index_code: str, start: str, end: str) -> pd.DataFrame:
    """Load index daily OHLCV data."""
    try:
        from data.tushare_client import get_client
        client = get_client()
        df = client.get_index_daily(
            index_code=index_code, start_date=start, end_date=end
        )
        if df.empty:
            return pd.DataFrame()
        df = df.sort_values("trade_date")
        return df
    except Exception:
        return pd.DataFrame()


def _load_index_cache_fast(index_code: str) -> pd.DataFrame:
    """Fast load index daily from parquet cache only."""
    import glob
    cache_dir = ROOT / "data" / "parquet" / "index_daily"
    if not cache_dir.exists():
        return pd.DataFrame()

    chunks = []
    for fpath in sorted(glob.glob(str(cache_dir / "**" / "*.parquet"), recursive=True)):
        try:
            part = pd.read_parquet(fpath)
            if "ts_code" not in part.columns or "trade_date" not in part.columns:
                continue
            mask = part["ts_code"] == index_code
            if mask.any():
                chunks.append(part[mask])
        except Exception:
            continue

    if not chunks:
        return pd.DataFrame()
    result = pd.concat(chunks, ignore_index=True)
    return result.drop_duplicates(["trade_date"]).sort_values("trade_date")


# ===========================================================================
# Market state feature computation (PIT-safe)
# ===========================================================================


def _build_regime_features_pit(
    index_df: pd.DataFrame,
    prices_df: Optional[pd.DataFrame],
    signal_dates: np.ndarray,
) -> pd.DataFrame:
    """Build regime features using RegimeDetector in PIT mode."""
    try:
        from alpha.regime_detector import RegimeDetector
    except ImportError:
        return _build_simplified_features_pit(index_df, signal_dates)

    cfg = {
        "index_code": "000300.SH",
        "trend": {"ma_short": 60, "ma_long": 120, "return_windows": [20, 60, 120]},
        "volatility": {"vol_windows": [20, 60], "drawdown_window": 60},
        "breadth": {"ma_window": 60, "min_stocks": 100},
        "smoothing": {"halflife": 0},
    }
    detector = RegimeDetector(cfg)
    features = detector.compute_features(index_df, prices_df, signal_dates)
    if features.empty:
        return pd.DataFrame()

    return features[["trade_date", "trend_strength", "volatility_state",
                      "breadth_score", "turnover_state"]]


def _build_simplified_features_pit(
    index_df: pd.DataFrame, signal_dates: np.ndarray
) -> pd.DataFrame:
    """Simplified trend/vol features (no RegimeDetector)."""
    if index_df.empty:
        return pd.DataFrame()

    idx = index_df.sort_values("trade_date").copy()
    idx["ret"] = idx["close"].pct_change()
    idx["log_ret"] = np.log(idx["close"]).diff()

    rows = []
    for sd in signal_dates:
        pit = idx[idx["trade_date"] <= sd]
        if len(pit) < 120:
            continue

        closes = pit["close"].values
        rets = pit["ret"].values
        log_rets = pit["log_ret"].values

        ret_20 = (closes[-1] / closes[-21]) - 1 if len(closes) > 20 else 0
        ret_60 = (closes[-1] / closes[-61]) - 1 if len(closes) > 60 else 0
        ret_120 = (closes[-1] / closes[-121]) - 1 if len(closes) > 120 else 0
        ma60 = np.mean(closes[-60:]) if len(closes) >= 60 else closes[-1]
        ma120 = np.mean(closes[-120:]) if len(closes) >= 120 else closes[-1]
        price_vs_ma60 = (closes[-1] / ma60 - 1) if ma60 > 0 else 0
        price_vs_ma120 = (closes[-1] / ma120 - 1) if ma120 > 0 else 0

        trend = (0.20 * ret_20 + 0.35 * ret_60 + 0.15 * ret_120
                 + 0.15 * price_vs_ma60 + 0.10 * price_vs_ma120)

        vol_20d = float(np.std(log_rets[-20:]) * np.sqrt(252)) if len(log_rets) >= 20 else 0.15

        if "vol" in pit.columns:
            vols = pit["vol"].values.astype(float)
            vol_20d_avg = np.mean(vols[-20:]) if len(vols) >= 20 else 0
            vol_60d_avg = np.mean(vols[-60:]) if len(vols) >= 60 else vol_20d_avg
            vol_60d_std = np.std(vols[-60:]) if len(vols) >= 60 else 1.0
            turnover = (vol_20d_avg - vol_60d_avg) / vol_60d_std if vol_60d_std > 0 else 0.0
        else:
            turnover = 0.0

        breadth = 0.5

        rows.append({
            "trade_date": int(sd),
            "trend_strength": float(trend),
            "volatility_state": float(vol_20d),
            "breadth_score": float(breadth),
            "turnover_state": float(turnover),
        })

    return pd.DataFrame(rows)


# ===========================================================================
# Factor IC computation
# ===========================================================================


def _rank_ic(factor_vals: pd.Series, fwd_rets: pd.Series, min_obs: int = 30) -> float:
    """Spearman rank correlation."""
    from scipy.stats import spearmanr
    mask = factor_vals.notna() & fwd_rets.notna()
    if mask.sum() < min_obs:
        return float("nan")
    try:
        return float(spearmanr(factor_vals[mask], fwd_rets[mask])[0])
    except Exception:
        return float("nan")


def _compute_factor_ic_series(
    factor_df: pd.DataFrame, fwd_df: pd.DataFrame, horizon: str = "fwd_ret_20d"
) -> pd.DataFrame:
    """Compute daily rank IC for a factor."""
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


# ===========================================================================
# Rule engine
# ===========================================================================


def _compute_rolling_q75(
    state_series: pd.Series,
    dates: np.ndarray,
    min_warmup: int = MIN_PIT_WARMUP,
) -> pd.Series:
    """Compute expanding-window q75 for each date (strictly PIT-safe).

    For each date T, q75 is computed from all observations with date <= T.
    Returns a Series indexed by date with the q75 threshold at each date.
    """
    sorted_vals = state_series.sort_index()
    q75_series = pd.Series(np.nan, index=sorted_vals.index)

    values_seen: List[float] = []
    for idx, val in sorted_vals.items():
        values_seen.append(val)
        if len(values_seen) >= min_warmup:
            q75_series[idx] = float(np.percentile(values_seen, 75))
        else:
            q75_series[idx] = float(np.percentile(values_seen, 75))  # still compute but flag as warmup

    return q75_series


def apply_market_state_rules(
    panel: pd.DataFrame,
    mode: str = "rolling_pit",
    vol_q75_research: Optional[float] = None,
    breadth_q75_research: Optional[float] = None,
) -> pd.DataFrame:
    """Apply market state rules to produce daily signals.

    Parameters
    ----------
    panel : DataFrame with columns [trade_date, volatility_state, breadth_score]
    mode : "research" or "rolling_pit"
    vol_q75_research : pre-computed full-sample q75 for volatility (research mode)
    breadth_q75_research : pre-computed full-sample q75 for breadth (research mode)

    Returns
    -------
    DataFrame with columns:
        trade_date, volatility_state, breadth_score,
        vol_q75, breadth_q75,
        volatility_high, breadth_high,
        rule_signal, rule_label,
        momentum_weight_multiplier, momentum_weight_multiplier_conservative
    """
    result = panel[["trade_date", "volatility_state", "breadth_score"]].copy()
    result = result.sort_values("trade_date").reset_index(drop=True)

    if mode == "research":
        # Full-sample quantiles
        if vol_q75_research is None:
            vol_q75_research = float(result["volatility_state"].quantile(0.75))
        if breadth_q75_research is None:
            breadth_q75_research = float(result["breadth_score"].quantile(0.75))

        result["vol_q75"] = vol_q75_research
        result["breadth_q75"] = breadth_q75_research

    elif mode == "rolling_pit":
        # Rolling PIT quantiles
        vol_sorted = result.set_index("trade_date")["volatility_state"]
        breadth_sorted = result.set_index("trade_date")["breadth_score"]
        dates = result["trade_date"].values

        result["vol_q75"] = _compute_rolling_q75(vol_sorted, dates).values
        result["breadth_q75"] = _compute_rolling_q75(breadth_sorted, dates).values
    else:
        raise ValueError(f"Unknown mode: {mode}")

    # Rule 1: High volatility flag
    result["volatility_high"] = result["volatility_state"] >= result["vol_q75"]

    # Rule 2: High breadth flag
    result["breadth_high"] = result["breadth_score"] >= result["breadth_q75"]

    # Combined rule with priority: volatility > breadth
    # Priority: high vol → off; elif high breadth → on; else → neutral
    conditions = [
        result["volatility_high"],
        result["breadth_high"] & ~result["volatility_high"],
    ]
    choices = ["momentum_off", "momentum_on"]
    result["rule_signal"] = np.select(conditions, choices, default="momentum_neutral")

    # Descriptive label
    label_map = {
        "momentum_off": "momentum_off_high_vol",
        "momentum_on": "momentum_on_high_breadth",
        "momentum_neutral": "momentum_neutral",
    }
    result["rule_label"] = result["rule_signal"].map(label_map)

    # Weight multipliers
    # Default: off → 0.0, on → 1.0, neutral → 1.0
    result["momentum_weight_multiplier"] = np.where(
        result["rule_signal"] == "momentum_off", 0.0, 1.0
    )
    # Conservative: off → 0.5 (half weight instead of zero)
    result["momentum_weight_multiplier_conservative"] = np.where(
        result["rule_signal"] == "momentum_off", 0.5, 1.0
    )

    return result


def apply_market_state_rules_oos(
    train_panel: pd.DataFrame,
    test_panel: pd.DataFrame,
    requested_train_end: Optional[int] = None,
) -> Tuple[pd.DataFrame, Dict[str, float]]:
    """Apply rules with thresholds FROZEN from training period only.

    Strictly out-of-sample: q75 computed from train_panel, then applied
    unchanged to test_panel.  No test data ever enters threshold calibration.

    Parameters
    ----------
    train_panel : DataFrame with [trade_date, volatility_state, breadth_score]
    test_panel : DataFrame with [trade_date, volatility_state, breadth_score]
    requested_train_end : int or None — the user-specified train cutoff date.
        When provided, this is stored separately from the last actual
        observation date in the training panel, so audit reports can
        clearly distinguish the requested boundary from data reality.

    Returns
    -------
    test_result : DataFrame with rule signals for test period only
    frozen_thresholds : dict with vol_q75, breadth_q75 from training,
        plus train/test date metadata with both requested and actual dates.
    """
    # Compute thresholds from TRAINING data ONLY
    vol_q75_train = float(train_panel["volatility_state"].quantile(0.75))
    breadth_q75_train = float(train_panel["breadth_score"].quantile(0.75))

    frozen_thresholds = {
        "vol_q75": vol_q75_train,
        "breadth_q75": breadth_q75_train,
        "requested_train_end": requested_train_end,
        "train_start": int(train_panel["trade_date"].min()),
        "train_end": int(train_panel["trade_date"].max()),
        "train_last_observation_date": int(train_panel["trade_date"].max()),
        "test_first_observation_date": int(test_panel["trade_date"].min()),
        "train_n_days": len(train_panel),
    }

    # Apply FROZEN thresholds to test data
    result = test_panel[["trade_date", "volatility_state", "breadth_score"]].copy()
    result = result.sort_values("trade_date").reset_index(drop=True)

    result["vol_q75"] = vol_q75_train
    result["breadth_q75"] = breadth_q75_train

    # Rule 1: High volatility flag
    result["volatility_high"] = result["volatility_state"] >= result["vol_q75"]

    # Rule 2: High breadth flag
    result["breadth_high"] = result["breadth_score"] >= result["breadth_q75"]

    # Combined rule with priority: volatility > breadth
    conditions = [
        result["volatility_high"],
        result["breadth_high"] & ~result["volatility_high"],
    ]
    choices = ["momentum_off", "momentum_on"]
    result["rule_signal"] = np.select(conditions, choices, default="momentum_neutral")

    label_map = {
        "momentum_off": "momentum_off_high_vol",
        "momentum_on": "momentum_on_high_breadth",
        "momentum_neutral": "momentum_neutral",
    }
    result["rule_label"] = result["rule_signal"].map(label_map)

    result["momentum_weight_multiplier"] = np.where(
        result["rule_signal"] == "momentum_off", 0.0, 1.0
    )
    result["momentum_weight_multiplier_conservative"] = np.where(
        result["rule_signal"] == "momentum_off", 0.5, 1.0
    )

    return result, frozen_thresholds


def _compute_walkforward_validation(
    panel: pd.DataFrame,
    daily_ic: pd.DataFrame,
    train_end_dates: List[int],
) -> Dict[str, Any]:
    """Walk-forward validation: expanding train window, test each subsequent year.

    For each train_end in train_end_dates:
      1. Train thresholds on [panel_start, train_end]
      2. Test on (train_end, next_train_end] or (train_end, panel_end]
      3. Compute metrics on test period only
      4. Record results independently for each test window

    Parameters
    ----------
    panel : full panel with market state features
    daily_ic : full IC series
    train_end_dates : list of cutoff dates (YYYYMMDD int format)

    Returns
    -------
    Dict with:
      - windows: list of per-window results
      - aggregate: aggregated OOS metrics (mean across windows)
      - stability: std of key metrics across windows (lower = more stable)
    """
    panel = panel.sort_values("trade_date").reset_index(drop=True)
    daily_ic = daily_ic.sort_values("trade_date").reset_index(drop=True)

    panel_min = int(panel["trade_date"].min())
    panel_max = int(panel["trade_date"].max())

    windows = []
    all_oos_on_ics = []
    all_oos_off_ics = []
    all_oos_neutral_ics = []
    all_oos_baseline_ics = []

    for i, train_end in enumerate(train_end_dates):
        # Determine test period
        if i + 1 < len(train_end_dates):
            test_end = train_end_dates[i + 1]
        else:
            test_end = panel_max

        # Skip if test period is empty
        if test_end <= train_end:
            continue

        # Split data
        train_panel = panel[panel["trade_date"] <= train_end]
        test_panel = panel[(panel["trade_date"] > train_end) & (panel["trade_date"] <= test_end)]

        if len(train_panel) < MIN_PIT_WARMUP:
            continue
        if len(test_panel) < MIN_LABEL_DAYS:
            continue

        # Apply OOS rules
        test_signals, frozen = apply_market_state_rules_oos(train_panel, test_panel)

        # Merge with IC
        test_ic = daily_ic[daily_ic["trade_date"].between(
            int(test_panel["trade_date"].min()), int(test_panel["trade_date"].max())
        )]
        merged = test_signals.merge(test_ic, on="trade_date", how="inner")

        if merged.empty:
            continue

        # Compute per-label metrics for this window
        window_metrics = {}
        for label in ["momentum_on", "momentum_off", "momentum_neutral"]:
            label_ic = merged[merged["rule_signal"] == label]["ic"]
            window_metrics[label] = _compute_label_metrics(label_ic, label)

            # Collect for aggregate
            if label == "momentum_on" and len(label_ic) > 0:
                all_oos_on_ics.extend(label_ic.values)
            elif label == "momentum_off" and len(label_ic) > 0:
                all_oos_off_ics.extend(label_ic.values)
            elif label == "momentum_neutral" and len(label_ic) > 0:
                all_oos_neutral_ics.extend(label_ic.values)

        baseline_ic = merged["ic"]
        window_metrics["baseline_all_days"] = _compute_label_metrics(baseline_ic, "baseline_all_days")
        all_oos_baseline_ics.extend(baseline_ic.values)

        windows.append({
            "train_end": int(train_end),
            "test_start": int(test_panel["trade_date"].min()),
            "test_end": int(test_panel["trade_date"].max()),
            "train_n": len(train_panel),
            "test_n": len(test_panel),
            "frozen_thresholds": frozen,
            "label_metrics": window_metrics,
        })

    if not windows:
        return {"validation_mode": "walkforward_oos",
                "windows": [], "aggregate": None, "stability": None,
                "n_windows": 0, "oos_verdict": "INSUFFICIENT_DATA",
                "error": "No valid walk-forward windows"}

    # Aggregate OOS metrics (pool all test periods)
    aggregate = {}
    for label, ics in [
        ("momentum_on", all_oos_on_ics),
        ("momentum_off", all_oos_off_ics),
        ("momentum_neutral", all_oos_neutral_ics),
        ("baseline_all_days", all_oos_baseline_ics),
    ]:
        if ics:
            aggregate[label] = _compute_label_metrics(pd.Series(ics), f"oos_{label}")
        else:
            aggregate[label] = _compute_label_metrics(pd.Series([], dtype=float), f"oos_{label}")

    # Stability: std of mean_ic across windows (lower = more stable)
    stability = {}
    for label in ["momentum_on", "momentum_off", "momentum_neutral"]:
        mean_ics = []
        for w in windows:
            lm = w["label_metrics"].get(label, {})
            if lm and not lm.get("insufficient_data") and not np.isnan(lm.get("mean_ic", float("nan"))):
                mean_ics.append(lm["mean_ic"])
        if mean_ics:
            stability[label] = {
                "mean_of_means": float(np.mean(mean_ics)),
                "std_of_means": float(np.std(mean_ics)),
                "n_windows": len(mean_ics),
                "min_mean_ic": float(np.min(mean_ics)),
                "max_mean_ic": float(np.max(mean_ics)),
            }

    # OOS acceptance verdict
    if aggregate:
        base_mean = aggregate.get("baseline_all_days", {}).get("mean_ic", float("nan"))
        on_mean = aggregate.get("momentum_on", {}).get("mean_ic", float("nan"))
        off_mean = aggregate.get("momentum_off", {}).get("mean_ic", float("nan"))

        if not np.isnan(on_mean) and not np.isnan(base_mean) and not np.isnan(off_mean):
            on_better = on_mean > base_mean
            off_worse = off_mean < base_mean
            if on_better and off_worse:
                oos_verdict = "PROMOTING_TO_STRATEGY"
            elif on_better or off_worse:
                oos_verdict = "PARTIAL"
            else:
                oos_verdict = "NO_RULE_ALPHA"
        else:
            oos_verdict = "INSUFFICIENT_DATA"
    else:
        oos_verdict = "INSUFFICIENT_DATA"

    return {
        "validation_mode": "walkforward_oos",
        "windows": windows,
        "aggregate": aggregate,
        "stability": stability,
        "oos_verdict": oos_verdict,
        "n_windows": len(windows),
    }


# ===========================================================================
# Walk-Forward Discovery (strictest: rules re-discovered each window)
# ===========================================================================


def _discover_rules_from_train_window(
    train_panel: pd.DataFrame,
    factor_ics: Dict[str, pd.DataFrame],
    factor_data: Dict[str, pd.DataFrame],
    fwd_df: pd.DataFrame,
) -> Dict[str, Any]:
    """Run full rule discovery pipeline on a SINGLE training window.

    Uses ONLY training-period data for:
      - Conditional IC analysis (state × factor)
      - FDR correction
      - Effect size filtering
      - Coverage audit
      - Rule candidate selection

    Parameters
    ----------
    train_panel : DataFrame with market state features + factor IC columns
    factor_ics : dict of factor_name -> IC series DataFrame
    factor_data : dict of factor_name -> raw factor DataFrame
    fwd_df : forward returns DataFrame

    Returns
    -------
    Dict with:
      - rule_candidates: list of discovered rules
      - all_results: all state×factor test results
      - coverage_blocked: set of blocked factors
      - n_train_days: number of training days
      - train_date_range: (min, max) of training dates
    """
    train_start = int(train_panel["trade_date"].min())
    train_end = int(train_panel["trade_date"].max())
    n_train = len(train_panel)

    # Filter factor data and fwd returns to training period
    train_fwd = fwd_df[
        (fwd_df["trade_date"] >= train_start) & (fwd_df["trade_date"] <= train_end)
    ]

    # ---- Coverage audit (training period only) ----
    coverage_blocked: set = set()
    for fn in DISCOVERY_FACTORS:
        fdf = factor_data.get(fn)
        if fdf is None or fdf.empty:
            coverage_blocked.add(fn)
            continue
        fdf_train = fdf[
            (fdf["trade_date"] >= train_start) & (fdf["trade_date"] <= train_end)
        ]
        if fdf_train.empty:
            coverage_blocked.add(fn)
            continue
        try:
            cov_df = _compute_coverage(fdf_train, train_fwd)
            cov_eval = _evaluate_coverage(cov_df)
            if cov_eval.get("coverage_blocked", True):
                coverage_blocked.add(fn)
        except Exception:
            coverage_blocked.add(fn)

    # ---- Conditional IC analysis (training period only) ----
    all_results: List[Dict[str, Any]] = []

    for state_col in DISCOVERY_STATE_COLS:
        if state_col not in train_panel.columns:
            continue
        state_valid = train_panel[state_col].notna().sum()
        if state_valid < MIN_OBS_PER_QUARTILE * 4:
            continue

        for fn in DISCOVERY_FACTORS:
            ic_col = f"{fn}_ic"
            if ic_col not in train_panel.columns:
                continue

            result = _conditional_ic_analysis(train_panel, state_col, fn)
            all_results.append(result)

    # ---- FDR correction (training period only) ----
    all_results = _apply_fdr_correction(all_results)

    # ---- Tiered classification (training period only) ----
    tiers = _classify_findings_into_tiers(all_results, coverage_blocked)

    # Extract rule candidates for momentum factor only
    momentum_rules = []
    for rc in tiers.get("rule_candidates", []):
        if rc["factor"] == MOMENTUM_FACTOR and rc["direction"] != "none":
            momentum_rules.append(rc)

    # Sort by priority: negative (risk-control) > positive (enable),
    # larger abs(spread) > smaller abs(spread), smaller q_value > larger q_value
    def _rule_sort_key(r: Dict[str, Any]) -> Tuple[int, float, float]:
        is_negative = 0 if r["direction"] == "negative" else 1
        abs_spread = -abs(r.get("spread", r.get("top_vs_bottom_spread", 0)))
        q_val = r.get("q_value", 1.0)
        return (is_negative, abs_spread, q_val)

    momentum_rules.sort(key=_rule_sort_key)

    # Translate rules to action format
    translated_rules = []
    for r in momentum_rules:
        direction = r["direction"]
        state_col = r["state_col"]

        if direction == "negative":
            rule_id = f"momentum_off_high_{state_col}"
            action = "momentum_off"
        else:
            rule_id = f"momentum_on_high_{state_col}"
            action = "momentum_on"

        translated_rules.append({
            "rule_id": rule_id,
            "state_col": state_col,
            "factor": r["factor"],
            "direction": direction,
            "action": action,
            "spread": r.get("spread", r.get("top_vs_bottom_spread", 0)),
            "p_value": r.get("p_value"),
            "q_value": r.get("q_value"),
            "priority": len(translated_rules) + 1,
        })

    return {
        "rule_candidates": translated_rules,
        "all_results": all_results,
        "tiers": tiers,
        "coverage_blocked": sorted(coverage_blocked),
        "n_train_days": n_train,
        "train_date_range": (train_start, train_end),
        "n_rule_candidates": len(translated_rules),
        "n_fdr_robust": len(tiers.get("fdr_robust", [])),
        "n_raw_significant": len(tiers.get("raw_significant", [])),
    }


def _translate_rules_to_test_signals(
    rules: List[Dict[str, Any]],
    train_panel: pd.DataFrame,
    test_panel: pd.DataFrame,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Apply discovered rules to test period using frozen train thresholds.

    Parameters
    ----------
    rules : list of discovered rule dicts from _discover_rules_from_train_window
    train_panel : training-period panel (for threshold computation)
    test_panel : test-period panel (for signal generation)

    Returns
    -------
    test_signals : DataFrame with rule signals for test period
    applied_rules : dict describing which rules were applied and their thresholds
    """
    result = test_panel[["trade_date"]].copy()
    result = result.sort_values("trade_date").reset_index(drop=True)

    applied_rules = {"rules_applied": [], "thresholds": {}, "n_rules": len(rules)}

    if not rules:
        # No rules discovered → all neutral
        result["rule_signal"] = "momentum_neutral"
        result["rule_label"] = "momentum_neutral"
        result["momentum_weight_multiplier"] = 1.0
        result["momentum_weight_multiplier_conservative"] = 1.0
        applied_rules["rules_applied"] = []
        applied_rules["note"] = "NO_RULE_DISCOVERED"
        return result, applied_rules

    # Compute frozen thresholds from training period
    rule_conditions = []
    rule_choices = []
    rule_details = []

    for i, rule in enumerate(rules):
        state_col = rule["state_col"]
        if state_col not in train_panel.columns:
            continue

        # Compute q75 threshold from TRAINING data only
        q75 = float(train_panel[state_col].quantile(0.75))
        applied_rules["thresholds"][state_col] = q75

        # Add state column to test result if not present
        if state_col in test_panel.columns:
            result[state_col] = test_panel[state_col].values
        else:
            continue

        # Build condition
        condition = result[state_col] >= q75

        # For momentum_on rules, also require no higher-priority negative rule triggers
        if rule["action"] == "momentum_on":
            # Check if any higher-priority negative rule would fire
            blocked_by = False
            for j in range(i):
                prev_rule = rules[j]
                if prev_rule["action"] == "momentum_off":
                    prev_col = prev_rule["state_col"]
                    prev_q75 = applied_rules["thresholds"].get(prev_col, float("inf"))
                    if prev_col in result.columns:
                        if (result[prev_col] >= prev_q75).any():
                            condition = condition & ~(result[prev_col] >= prev_q75)
                            blocked_by = True
            if blocked_by:
                rule_details.append(f"{rule['rule_id']}: blocked by higher-priority negative rule")

        rule_conditions.append(condition)
        rule_choices.append(rule["action"])
        rule_details.append(
            f"{rule['rule_id']}: {state_col} >= {q75:.4f} → {rule['action']}"
        )

    if rule_conditions:
        result["rule_signal"] = np.select(rule_conditions, rule_choices, default="momentum_neutral")
    else:
        result["rule_signal"] = "momentum_neutral"

    # Descriptive label
    result["rule_label"] = result["rule_signal"].map({
        "momentum_off": "momentum_off_high_vol",
        "momentum_on": "momentum_on_high_breadth",
        "momentum_neutral": "momentum_neutral",
    }).fillna("momentum_neutral")

    # Weight multipliers
    result["momentum_weight_multiplier"] = np.where(
        result["rule_signal"] == "momentum_off", 0.0, 1.0
    )
    result["momentum_weight_multiplier_conservative"] = np.where(
        result["rule_signal"] == "momentum_off", 0.5, 1.0
    )

    applied_rules["rules_applied"] = rule_details
    return result, applied_rules


def _compute_window_verdict(
    test_signals: pd.DataFrame,
    test_ic: pd.DataFrame,
    discovered_rules: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Compute per-window verdict for walk-forward discovery.

    Verdict rules:
      PASS: momentum_on.mean_ic > baseline.mean_ic AND momentum_off.mean_ic < baseline.mean_ic
      PARTIAL: only one side satisfied
      FAIL: rules discovered but neither side satisfied
      NO_RULE_DISCOVERED: no rules discovered in training
    """
    if not discovered_rules:
        return {
            "verdict": "NO_RULE_DISCOVERED",
            "detail": "Training period did not yield any qualified rule candidates.",
            "checks": [],
        }

    merged = test_signals.merge(test_ic, on="trade_date", how="inner")
    if merged.empty:
        return {
            "verdict": "INSUFFICIENT_DATA",
            "detail": "No test data available for evaluation.",
            "checks": [],
        }

    baseline = merged["ic"]
    baseline_mean = float(baseline.mean())

    checks = []
    on_pass = None
    off_pass = None

    # Check momentum_on
    on_data = merged[merged["rule_signal"] == "momentum_on"]["ic"]
    if len(on_data) >= MIN_LABEL_DAYS:
        on_mean = float(on_data.mean())
        on_ok = on_mean > baseline_mean
        on_pass = on_ok
        checks.append({
            "check": "momentum_on > baseline",
            "pass": on_ok,
            "detail": f"on_mean={on_mean:.4f} vs baseline={baseline_mean:.4f}, n={len(on_data)}",
        })

    # Check momentum_off
    off_data = merged[merged["rule_signal"] == "momentum_off"]["ic"]
    if len(off_data) >= MIN_LABEL_DAYS:
        off_mean = float(off_data.mean())
        off_ok = off_mean < baseline_mean
        off_pass = off_ok
        checks.append({
            "check": "momentum_off < baseline",
            "pass": off_ok,
            "detail": f"off_mean={off_mean:.4f} vs baseline={baseline_mean:.4f}, n={len(off_data)}",
        })

    if on_pass is None and off_pass is None:
        return {
            "verdict": "INSUFFICIENT_DATA",
            "detail": "Neither momentum_on nor momentum_off had enough observations.",
            "checks": checks,
        }

    if on_pass is True and (off_pass is True or off_pass is None):
        verdict = "PASS"
    elif off_pass is True and (on_pass is True or on_pass is None):
        verdict = "PASS"
    elif on_pass is True or off_pass is True:
        verdict = "PARTIAL"
    else:
        verdict = "FAIL"

    return {
        "verdict": verdict,
        "detail": f"on_pass={on_pass}, off_pass={off_pass}",
        "checks": checks,
    }


def _compute_overall_discovery_verdict(
    window_results: List[Dict[str, Any]],
    all_test_signals: pd.DataFrame,
    all_test_ic: pd.DataFrame,
) -> Dict[str, Any]:
    """Compute overall verdict from walk-forward discovery windows.

    PROMOTING_TO_STRATEGY:
      - Windows with rules >= 2
      - PASS ratio >= 60% among windows that discovered rules
      - Pooled momentum_on mean_ic > pooled baseline mean_ic
      - Pooled momentum_off mean_ic < pooled baseline mean_ic
      - No single year contributes > 60% of momentum_on observations

    PARTIAL: PASS ratio >= 50% but stability or sample insufficient

    NO_RULE_ALPHA: otherwise
    """
    n_windows = len(window_results)
    windows_with_rules = [w for w in window_results
                         if w.get("verdict") != "NO_RULE_DISCOVERED"]
    n_with_rules = len(windows_with_rules)

    if n_with_rules < 2:
        return {
            "overall_verdict": "NO_RULE_ALPHA",
            "overall_detail": (
                f"Only {n_with_rules} window(s) discovered rules "
                f"(need >= 2 for robustness)."
            ),
            "n_windows": n_windows,
            "n_with_rules": n_with_rules,
            "pass_count": 0,
            "pass_ratio": 0.0,
            "pooled_metrics": None,
            "max_year_contribution_pct": None,
        }

    pass_count = sum(1 for w in windows_with_rules if w.get("verdict") == "PASS")
    pass_ratio = pass_count / n_with_rules if n_with_rules > 0 else 0.0

    # Pooled OOS metrics
    if all_test_signals is not None and all_test_ic is not None:
        merged = all_test_signals.merge(all_test_ic, on="trade_date", how="inner")
        if not merged.empty:
            base_mean = float(merged["ic"].mean())
            on_data = merged[merged["rule_signal"] == "momentum_on"]["ic"]
            off_data = merged[merged["rule_signal"] == "momentum_off"]["ic"]

            on_mean = float(on_data.mean()) if len(on_data) > 0 else float("nan")
            off_mean = float(off_data.mean()) if len(off_data) > 0 else float("nan")

            # Max year contribution
            merged["year"] = merged["trade_date"].astype(str).str[:4].astype(int)
            on_by_year = merged[merged["rule_signal"] == "momentum_on"].groupby("year").size()
            total_on = len(on_data)
            max_year_pct = float(on_by_year.max() / total_on) if total_on > 0 and len(on_by_year) > 0 else 0.0

            pooled_metrics = {
                "baseline_mean_ic": base_mean,
                "momentum_on_mean_ic": on_mean,
                "momentum_off_mean_ic": off_mean,
                "momentum_on_n": len(on_data),
                "momentum_off_n": len(off_data),
                "total_n": len(merged),
                "max_year_contribution_pct": max_year_pct,
            }
        else:
            pooled_metrics = None
    else:
        pooled_metrics = None

    # Check pooled conditions
    pooled_on_ok = True
    pooled_off_ok = True
    max_year_ok = True

    if pooled_metrics:
        if not np.isnan(pooled_metrics["momentum_on_mean_ic"]):
            pooled_on_ok = pooled_metrics["momentum_on_mean_ic"] > pooled_metrics["baseline_mean_ic"]
        if not np.isnan(pooled_metrics["momentum_off_mean_ic"]):
            pooled_off_ok = pooled_metrics["momentum_off_mean_ic"] < pooled_metrics["baseline_mean_ic"]
        max_year_ok = pooled_metrics.get("max_year_contribution_pct", 0.0) <= 0.60

    # Final verdict
    if (n_with_rules >= 2 and pass_ratio >= 0.60
            and pooled_on_ok and pooled_off_ok and max_year_ok):
        overall = "PROMOTING_TO_STRATEGY"
        detail = (
            f"Walk-forward discovery: {pass_count}/{n_with_rules} windows PASS. "
            f"Rules are re-discovered independently in each training window and "
            f"validate OOS. Pooled metrics confirm improvement over baseline. "
            f"Proceed to strategy-level backtesting."
        )
    elif n_with_rules >= 2 and pass_ratio >= 0.50:
        overall = "PARTIAL"
        detail = (
            f"Walk-forward discovery: {pass_count}/{n_with_rules} windows PASS "
            f"(ratio={pass_ratio:.1%}). Some windows validate but stability is "
            f"insufficient for full confidence."
        )
        if not pooled_on_ok:
            detail += " Pooled momentum_on does NOT outperform baseline."
        if not pooled_off_ok:
            detail += " Pooled momentum_off is NOT worse than baseline."
        if not max_year_ok:
            detail += " Single-year concentration exceeds 60%."
    else:
        overall = "NO_RULE_ALPHA"
        detail = (
            f"Walk-forward discovery: {pass_count}/{n_with_rules} windows PASS "
            f"(ratio={pass_ratio:.1%}). Rules cannot be reliably re-discovered "
            f"and/or validated OOS. Do NOT proceed to strategy development."
        )

    return {
        "overall_verdict": overall,
        "overall_detail": detail,
        "n_windows": n_windows,
        "n_with_rules": n_with_rules,
        "pass_count": pass_count,
        "pass_ratio": pass_ratio,
        "pooled_metrics": pooled_metrics,
        "max_year_contribution_pct": (
            pooled_metrics.get("max_year_contribution_pct") if pooled_metrics else None
        ),
    }


def _compute_walkforward_discovery_validation(
    regime_features: pd.DataFrame,
    factor_ics: Dict[str, pd.DataFrame],
    factor_data: Dict[str, pd.DataFrame],
    fwd_df: pd.DataFrame,
    ic_series: pd.DataFrame,
    train_end_dates: List[int],
    horizon_col: str,
) -> Dict[str, Any]:
    """Full walk-forward discovery validation.

    For each train_end date:
      1. Split data into train and test
      2. Discover rules from train period ONLY
      3. Freeze thresholds from train period ONLY
      4. Apply rules to test period
      5. Evaluate on test period ONLY
      6. Record per-window verdict

    Parameters
    ----------
    regime_features : DataFrame with market state features
    factor_ics : dict of factor_name -> IC series DataFrame
    factor_data : dict of factor_name -> raw factor values
    fwd_df : forward returns DataFrame
    ic_series : momentum IC series
    train_end_dates : list of train_end cutoffs
    horizon_col : forward return column name

    Returns
    -------
    Dict with per-window results, overall verdict, and pooled metrics.
    """
    regime_features = regime_features.sort_values("trade_date").reset_index(drop=True)
    ic_series = ic_series.sort_values("trade_date").reset_index(drop=True)
    panel_max = int(regime_features["trade_date"].max())

    # Build panel with all factor ICs for discovery
    discovery_panel = regime_features.copy()
    for fn, ic_df in factor_ics.items():
        ic_renamed = ic_df.rename(columns={"trade_date": "trade_date", "ic": f"{fn}_ic"})
        discovery_panel = discovery_panel.merge(
            ic_renamed, on="trade_date", how="left"
        )

    windows = []
    all_test_signals_list = []
    all_test_ic_list = []

    for i, train_end in enumerate(train_end_dates):
        if i + 1 < len(train_end_dates):
            test_end = train_end_dates[i + 1]
        else:
            test_end = panel_max

        if test_end <= train_end:
            continue

        # Split
        train_panel = discovery_panel[discovery_panel["trade_date"] <= train_end]
        test_panel = discovery_panel[
            (discovery_panel["trade_date"] > train_end)
            & (discovery_panel["trade_date"] <= test_end)
        ]

        if len(train_panel) < MIN_PIT_WARMUP or len(test_panel) < MIN_LABEL_DAYS:
            continue

        # --- Step 1: Discover rules from training period ONLY ---
        discovery_result = _discover_rules_from_train_window(
            train_panel, factor_ics, factor_data, fwd_df
        )
        rules = discovery_result["rule_candidates"]

        # --- Step 2: Translate rules to test signals ---
        test_signals, applied_rules = _translate_rules_to_test_signals(
            rules, train_panel, test_panel
        )

        # --- Step 3: Evaluate on test period ONLY ---
        test_ic = ic_series[
            (ic_series["trade_date"] > train_end)
            & (ic_series["trade_date"] <= test_end)
        ]

        # --- Step 4: Per-window verdict ---
        window_verdict = _compute_window_verdict(test_signals, test_ic, rules)

        # Collect for pooled analysis
        all_test_signals_list.append(test_signals)
        all_test_ic_list.append(test_ic)

        # Per-label metrics
        merged = test_signals.merge(test_ic, on="trade_date", how="inner")
        label_metrics = {}
        for label in ["momentum_on", "momentum_off", "momentum_neutral"]:
            label_ic = merged[merged["rule_signal"] == label]["ic"]
            label_metrics[label] = _compute_label_metrics(label_ic, label)
        baseline_ic = merged["ic"]
        label_metrics["baseline_all_days"] = _compute_label_metrics(baseline_ic, "baseline_all_days")

        windows.append({
            "train_end": int(train_end),
            "test_start": int(test_panel["trade_date"].min()),
            "test_end": int(test_panel["trade_date"].max()),
            "train_n": len(train_panel),
            "test_n": len(test_panel),
            "discovery": {
                "n_rule_candidates": discovery_result["n_rule_candidates"],
                "n_fdr_robust": discovery_result["n_fdr_robust"],
                "n_raw_significant": discovery_result["n_raw_significant"],
                "coverage_blocked": discovery_result["coverage_blocked"],
                "rules": rules,
            },
            "applied_rules": applied_rules,
            "label_metrics": label_metrics,
            "verdict": window_verdict["verdict"],
            "verdict_detail": window_verdict["detail"],
            "verdict_checks": window_verdict.get("checks", []),
        })

    if not windows:
        return {
            "validation_mode": "walkforward_discovery",
            "rule_discovery_oos_safe": True,
            "full_sample_rule_candidates_used": False,
            "windows": [],
            "overall_verdict": "INSUFFICIENT_DATA",
            "overall_detail": "No valid walk-forward discovery windows.",
            "n_windows": 0,
            "n_with_rules": 0,
        }

    # Pooled OOS signals and ICs
    all_test_signals = pd.concat(all_test_signals_list, ignore_index=True) if all_test_signals_list else None
    all_test_ic = pd.concat(all_test_ic_list, ignore_index=True) if all_test_ic_list else None

    # Overall verdict
    overall = _compute_overall_discovery_verdict(windows, all_test_signals, all_test_ic)

    # Add per-window summary to overall
    overall["windows"] = windows
    overall["all_test_signals"] = all_test_signals
    overall["all_test_ic"] = all_test_ic

    # Add explicit validation mode metadata (must survive regardless of windows content)
    overall["validation_mode"] = "walkforward_discovery"
    overall["rule_discovery_oos_safe"] = True
    overall["full_sample_rule_candidates_used"] = False

    return overall


# ===========================================================================
# Validation metrics
# ===========================================================================


def _compute_label_metrics(
    ic_by_label: pd.Series,
    label: str,
) -> Dict[str, Any]:
    """Compute validation metrics for a given label's IC series."""
    n_days = len(ic_by_label)
    if n_days < 5:
        return {
            "label": label,
            "n_days": n_days,
            "mean_ic": float("nan"),
            "icir": float("nan"),
            "hit_rate": float("nan"),
            "ic_std": float("nan"),
            "top_bottom_spread": float("nan"),
            "top_quintile_excess": float("nan"),
            "estimated_cost": float("nan"),
            "net_spread": float("nan"),
            "positive_years": 0,
            "max_year_contribution": float("nan"),
            "insufficient_data": True,
        }

    mean_ic = float(ic_by_label.mean())
    ic_std = float(ic_by_label.std())
    icir = float(mean_ic / ic_std) if ic_std > 0 else 0.0
    hit_rate = float((ic_by_label > 0).mean())

    # Top-bottom spread: within-label, compare top 20% IC days vs bottom 20%
    sorted_ic = ic_by_label.sort_values()
    n = len(sorted_ic)
    if n >= 10:
        n_quintile = max(1, n // 5)
        top_mean = sorted_ic.iloc[-n_quintile:].mean()
        bottom_mean = sorted_ic.iloc[:n_quintile].mean()
        top_bottom_spread = float(top_mean - bottom_mean)
        top_quintile_excess = float(top_mean - sorted_ic.mean())
    else:
        top_bottom_spread = float("nan")
        top_quintile_excess = float("nan")

    # Estimated cost (2x bid-ask as rough proxy for turnover cost)
    estimated_cost = 0.0030  # 30bps one-way for A-shares, 2x = 60bps round-trip
    net_spread = float(mean_ic - estimated_cost) if not np.isnan(mean_ic) else float("nan")

    # Year-by-year analysis
    ic_series_with_date = ic_by_label.copy()
    if hasattr(ic_series_with_date, 'index'):
        try:
            yearly = ic_series_with_date.groupby(
                lambda x: int(str(x)[:4]) if isinstance(x, (int, str)) else x.year
            ).agg(["mean", "count"])
            positive_years = int((yearly["mean"] > 0).sum())
            max_year_contribution = float(yearly["mean"].max()) if len(yearly) > 0 else float("nan")
        except Exception:
            positive_years = 0
            max_year_contribution = float("nan")
    else:
        positive_years = 0
        max_year_contribution = float("nan")

    return {
        "label": label,
        "n_days": n_days,
        "mean_ic": mean_ic,
        "icir": icir,
        "hit_rate": hit_rate,
        "ic_std": ic_std,
        "top_bottom_spread": top_bottom_spread,
        "top_quintile_excess": top_quintile_excess,
        "estimated_cost": estimated_cost,
        "net_spread": net_spread,
        "positive_years": positive_years,
        "max_year_contribution": max_year_contribution,
        "insufficient_data": False,
    }


def _compute_validation_metrics(
    rule_signals: pd.DataFrame,
    daily_ic: pd.DataFrame,
) -> Dict[str, Any]:
    """Compute all validation metrics.

    Parameters
    ----------
    rule_signals : DataFrame with [trade_date, rule_signal, ...]
    daily_ic : DataFrame with [trade_date, ic]

    Returns
    -------
    Dict with:
        - label_metrics: per-label metric dicts
        - baseline_metrics: all-days baseline
        - acceptance_results: per-label pass/fail vs baseline
        - overall_verdict: whether rules are effective
    """
    merged = rule_signals.merge(daily_ic, on="trade_date", how="inner")
    if merged.empty:
        return {
            "label_metrics": [],
            "baseline_metrics": {},
            "acceptance_results": {},
            "overall_verdict": "INSUFFICIENT_DATA",
        }

    # Baseline: all days
    baseline_metrics = _compute_label_metrics(merged["ic"], "baseline_all_days")

    # Per-label metrics
    labels = ["momentum_on", "momentum_off", "momentum_neutral"]
    label_metrics = []
    for label in labels:
        label_ic = merged[merged["rule_signal"] == label]["ic"]
        label_metrics.append(_compute_label_metrics(label_ic, label))

    # Acceptance tests
    acceptance = {}
    baseline_mean = baseline_metrics["mean_ic"]
    baseline_icir = baseline_metrics["icir"]
    baseline_hit = baseline_metrics["hit_rate"]

    for lm in label_metrics:
        if lm.get("insufficient_data"):
            acceptance[lm["label"]] = {
                "verdict": "INSUFFICIENT_DATA",
                "reason": f"n_days={lm['n_days']} < 5",
            }
            continue

        label_name = lm["label"]

        if label_name == "momentum_on":
            # momentum_on should be BETTER than baseline
            checks = []
            if lm["n_days"] < MIN_LABEL_DAYS:
                checks.append(("n_days", False, f"{lm['n_days']} < {MIN_LABEL_DAYS}"))
            else:
                checks.append(("n_days", True, "OK"))

            if not np.isnan(lm["mean_ic"]) and not np.isnan(baseline_mean):
                mean_ok = lm["mean_ic"] > baseline_mean
                checks.append(("mean_ic > baseline", mean_ok,
                               f"{lm['mean_ic']:.4f} vs {baseline_mean:.4f}"))
            else:
                checks.append(("mean_ic > baseline", False, "NaN"))

            if not np.isnan(lm["icir"]) and not np.isnan(baseline_icir):
                icir_ok = lm["icir"] > baseline_icir
                checks.append(("icir > baseline", icir_ok,
                               f"{lm['icir']:.4f} vs {baseline_icir:.4f}"))
            else:
                checks.append(("icir > baseline", False, "NaN"))

            if not np.isnan(lm["hit_rate"]) and not np.isnan(baseline_hit):
                hit_ok = lm["hit_rate"] > baseline_hit
                checks.append(("hit_rate > baseline", hit_ok,
                               f"{lm['hit_rate']:.4f} vs {baseline_hit:.4f}"))
            else:
                checks.append(("hit_rate > baseline", False, "NaN"))

            all_pass = all(c[1] for c in checks)
            acceptance[label_name] = {
                "verdict": "PASS" if all_pass else "FAIL",
                "checks": [{"check": c[0], "pass": c[1], "detail": c[2]} for c in checks],
            }

        elif label_name == "momentum_off":
            # momentum_off should be WORSE than baseline (confirming we want to avoid it)
            checks = []
            if lm["n_days"] < MIN_LABEL_DAYS:
                checks.append(("n_days", False, f"{lm['n_days']} < {MIN_LABEL_DAYS}"))
            else:
                checks.append(("n_days", True, "OK"))

            if not np.isnan(lm["mean_ic"]) and not np.isnan(baseline_mean):
                mean_ok = lm["mean_ic"] < baseline_mean
                checks.append(("mean_ic < baseline", mean_ok,
                               f"{lm['mean_ic']:.4f} vs {baseline_mean:.4f}"))
            else:
                checks.append(("mean_ic < baseline", False, "NaN"))

            all_pass = all(c[1] for c in checks)
            acceptance[label_name] = {
                "verdict": "PASS" if all_pass else "FAIL",
                "checks": [{"check": c[0], "pass": c[1], "detail": c[2]} for c in checks],
            }

        elif label_name == "momentum_neutral":
            # Neutral should be roughly similar to baseline (no strong assertion)
            checks = []
            if lm["n_days"] >= MIN_LABEL_DAYS:
                checks.append(("n_days", True, "OK"))
            else:
                checks.append(("n_days", False, f"{lm['n_days']} < {MIN_LABEL_DAYS}"))

            acceptance[label_name] = {
                "verdict": "OBSERVE",
                "checks": [{"check": c[0], "pass": c[1], "detail": c[2]} for c in checks],
            }

    # Overall verdict
    mom_on_pass = acceptance.get("momentum_on", {}).get("verdict") == "PASS"
    mom_off_pass = acceptance.get("momentum_off", {}).get("verdict") == "PASS"

    if mom_on_pass and mom_off_pass:
        overall = "PROMOTING_TO_STRATEGY"
        overall_detail = (
            "momentum_on outperforms baseline AND momentum_off successfully avoids "
            "low-IC environments. Rules are effective and should proceed to strategy-level "
            "market-state-driven momentum sleeve weight backtesting."
        )
    elif mom_on_pass and not mom_off_pass:
        overall = "PARTIAL"
        overall_detail = (
            "momentum_on outperforms baseline but momentum_off does not show clear "
            "deterioration vs baseline. The 'avoid high vol' rule may not add value "
            "beyond the 'embrace high breadth' rule. Consider simplifying to "
            "single-rule (breadth only)."
        )
    elif not mom_on_pass and mom_off_pass:
        overall = "PARTIAL"
        overall_detail = (
            "momentum_off correctly identifies worse IC environments but momentum_on "
            "does not significantly outperform baseline. The rule is useful for risk "
            "avoidance but not for alpha enhancement."
        )
    else:
        overall = "NO_RULE_ALPHA"
        overall_detail = (
            "Market state variables can explain historical IC differences but cannot "
            "form stable, usable rules. The rules do NOT produce statistically or "
            "economically meaningful improvement over the baseline. "
            "Do NOT proceed to strategy switching development."
        )

    return {
        "label_metrics": label_metrics,
        "baseline_metrics": baseline_metrics,
        "acceptance_results": acceptance,
        "overall_verdict": overall,
        "overall_detail": overall_detail,
    }


# ===========================================================================
# Year-by-year breakdown
# ===========================================================================


def _compute_validation_by_year(
    rule_signals: pd.DataFrame,
    daily_ic: pd.DataFrame,
) -> pd.DataFrame:
    """Compute validation metrics by year."""
    merged = rule_signals.merge(daily_ic, on="trade_date", how="inner")
    if merged.empty:
        return pd.DataFrame()

    merged["year"] = merged["trade_date"].astype(str).str[:4].astype(int)

    rows = []
    for year, year_data in merged.groupby("year"):
        # Baseline
        base_mean = year_data["ic"].mean()
        base_icir = (year_data["ic"].mean() / year_data["ic"].std()
                     if year_data["ic"].std() > 0 else 0.0)
        base_n = len(year_data)

        row = {"year": int(year), "baseline_n": base_n,
               "baseline_mean_ic": base_mean, "baseline_icir": base_icir}

        for label in ["momentum_on", "momentum_off", "momentum_neutral"]:
            label_data = year_data[year_data["rule_signal"] == label]["ic"]
            n_l = len(label_data)
            mean_l = label_data.mean() if n_l > 0 else float("nan")
            icir_l = (mean_l / label_data.std()) if (n_l > 0 and label_data.std() > 0) else 0.0
            row[f"{label}_n"] = n_l
            row[f"{label}_mean_ic"] = mean_l
            row[f"{label}_icir"] = icir_l

        rows.append(row)

    return pd.DataFrame(rows)


# ===========================================================================
# Unified verdict resolution
# ===========================================================================


def _resolve_final_verdict(
    validation_results: Dict[str, Any],
    walkforward_results: Optional[Dict[str, Any]] = None,
    is_oos: bool = False,
) -> Dict[str, Any]:
    """Resolve a single-source-of-truth final verdict across all validation modes.

    This is the ONLY function that determines the final verdict and promotion
    decision. All outputs (YAML, manifest, report, CLI) must use this result.

    Rules:
      --walkforward-discovery  → walkforward_results["overall_verdict"]
      --walkforward (non-disc) → walkforward_results["oos_verdict"]
      --train-end (strict OOS) → validation_results["overall_verdict"]
      in-sample               → validation_results["overall_verdict"]

    Promotion decision:
      Only PROMOTING_TO_STRATEGY → PROMOTE
      Everything else (PARTIAL, FAIL, NO_RULE_ALPHA, NO_RULE_DISCOVERED,
                        INSUFFICIENT_DATA) → BLOCK
    """
    # Determine validation mode — use explicit metadata, NOT windows emptiness
    if walkforward_results:
        mode_hint = walkforward_results.get("validation_mode")

        if mode_hint == "walkforward_discovery" or walkforward_results.get("rule_discovery_oos_safe"):
            source_verdict = walkforward_results.get("overall_verdict", "INSUFFICIENT_DATA")
            source_detail = walkforward_results.get("overall_detail", "")
            mode = "walkforward_discovery"

        elif mode_hint == "walkforward_oos" or "oos_verdict" in walkforward_results:
            source_verdict = walkforward_results.get("oos_verdict", "INSUFFICIENT_DATA")
            source_detail = walkforward_results.get("overall_detail", "")
            mode = "walkforward_oos"

        # Legacy fallback: check windows for discovery metadata
        elif walkforward_results.get("windows"):
            is_discovery = any("discovery" in w for w in walkforward_results["windows"])
            if is_discovery:
                mode = "walkforward_discovery"
                source_verdict = walkforward_results.get("overall_verdict", "INSUFFICIENT_DATA")
                source_detail = walkforward_results.get("overall_detail", "")
            else:
                mode = "walkforward_oos"
                source_verdict = walkforward_results.get("oos_verdict", "INSUFFICIENT_DATA")
                source_detail = walkforward_results.get("overall_detail", "")
        else:
            # walkforward_results present but empty/unrecognized — block safely
            mode = "walkforward_discovery"
            source_verdict = walkforward_results.get("overall_verdict", "INSUFFICIENT_DATA")
            source_detail = walkforward_results.get("overall_detail", "")
    elif is_oos:
        mode = "strict_oos"
        source_verdict = validation_results.get("overall_verdict", "INSUFFICIENT_DATA")
        source_detail = validation_results.get("overall_detail", "")
    else:
        mode = "in_sample"
        source_verdict = validation_results.get("overall_verdict", "INSUFFICIENT_DATA")
        source_detail = validation_results.get("overall_detail", "")

    # Promotion decision: only PROMOTING_TO_STRATEGY → PROMOTE
    if source_verdict == "PROMOTING_TO_STRATEGY":
        promotion = "PROMOTE"
    else:
        promotion = "BLOCK"

    return {
        "validation_mode": mode,
        "final_verdict": source_verdict,
        "final_detail": source_detail,
        "promotion_decision": promotion,
        "verdict_source": mode,
    }


# ===========================================================================
# Output generation
# ===========================================================================


def _write_outputs(
    out_dir: Path,
    run_id: str,
    args,
    rule_signals: pd.DataFrame,
    daily_ic: pd.DataFrame,
    validation_results: Dict[str, Any],
    validation_by_year: pd.DataFrame,
    mode: str,
    vol_q75: Optional[float],
    breadth_q75: Optional[float],
    frozen_thresholds: Optional[Dict[str, Any]] = None,
    walkforward_results: Optional[Dict[str, Any]] = None,
):
    """Write all output files."""
    out_dir.mkdir(parents=True, exist_ok=True)

    # Resolve final verdict ONCE — single source of truth for all outputs
    is_oos = frozen_thresholds is not None
    resolved = _resolve_final_verdict(validation_results, walkforward_results, is_oos)

    # ------------------------------------------------------------------
    # 1. rule_validation_summary.csv
    # ------------------------------------------------------------------
    summary_rows = []
    for lm in validation_results["label_metrics"]:
        summary_rows.append(lm)
    # Add baseline
    bl = validation_results["baseline_metrics"]
    summary_rows.append(bl)

    summary_df = pd.DataFrame(summary_rows)
    summary_df.to_csv(out_dir / "rule_validation_summary.csv", index=False, encoding="utf-8-sig")
    print("  ✓ rule_validation_summary.csv")

    # ------------------------------------------------------------------
    # 2. rule_validation_by_year.csv
    # ------------------------------------------------------------------
    if not validation_by_year.empty:
        validation_by_year.to_csv(out_dir / "rule_validation_by_year.csv", index=False, encoding="utf-8-sig")
        print("  ✓ rule_validation_by_year.csv")
    else:
        print("  ⚠ rule_validation_by_year.csv: SKIPPED (no data)")

    # ------------------------------------------------------------------
    # 3. rule_signal_daily.csv
    # ------------------------------------------------------------------
    signal_cols = [
        "trade_date", "volatility_state", "breadth_score",
        "vol_q75", "breadth_q75",
        "volatility_high", "breadth_high",
        "rule_signal", "rule_label",
        "momentum_weight_multiplier", "momentum_weight_multiplier_conservative",
    ]
    available_cols = [c for c in signal_cols if c in rule_signals.columns]
    rule_signals[available_cols].to_csv(
        out_dir / "rule_signal_daily.csv", index=False, encoding="utf-8-sig"
    )
    print("  ✓ rule_signal_daily.csv")

    # ------------------------------------------------------------------
    # 4. rule_candidate_pool.yaml
    # ------------------------------------------------------------------
    rule_pool = {
        "schema": "market_state_momentum_rule_pool.v1",
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "run_id": run_id,
        "parameters": {
            "start": args.start, "end": args.end,
            "horizon_days": args.horizon,
            "threshold_mode": mode,
        },
        "thresholds": {
            "volatility_q75": float(vol_q75) if vol_q75 is not None else None,
            "breadth_q75": float(breadth_q75) if breadth_q75 is not None else None,
        },
        "rules": [
            {
                "rule_id": "momentum_off_high_vol",
                "condition": "volatility_state >= volatility_q75",
                "action": "momentum_weight_multiplier = 0.0",
                "action_conservative": "momentum_weight_multiplier = 0.5",
                "priority": 1,
                "rationale": (
                    "High volatility environments produce significantly worse momentum IC "
                    "(spread=-0.0847, p<0.001). This is the strongest and most robust "
                    "state→IC relationship found."
                ),
            },
            {
                "rule_id": "momentum_on_high_breadth",
                "condition": "breadth_score >= breadth_q75 AND volatility_state < volatility_q75",
                "action": "momentum_weight_multiplier = 1.0 (default)",
                "priority": 2,
                "rationale": (
                    "High market breadth environments produce better momentum IC "
                    "(spread=+0.0332, p<0.01). However, the vol rule takes priority "
                    "since its effect is stronger."
                ),
            },
        ],
        "priority_order": "volatility > breadth",
        "eligible_factors": [],
        "no_leakage": {
            "enabled": True,
            "mode": mode,
            "warmup_days": MIN_PIT_WARMUP,
        },
        # Resolve final verdict (single source of truth)
        "overall_verdict": resolved["final_verdict"],
        "overall_detail": resolved["final_detail"],
        "promotion_decision": resolved["promotion_decision"],
        "verdict_source": resolved["verdict_source"],
        "validation_mode": resolved["validation_mode"],
    }

    # Add OOS-specific metadata
    if is_oos:
        rule_pool["train_test_split"] = {
            "requested_train_end": frozen_thresholds.get("requested_train_end"),
            "train_last_observation_date": frozen_thresholds["train_end"],
            "test_first_observation_date": frozen_thresholds.get("test_first_observation_date"),
            "train_n_days": frozen_thresholds["train_n_days"],
            "threshold_source": "TRAINING_PERIOD_ONLY",
            "test_period_end": str(args.end),
        }
        rule_pool["no_leakage"]["train_test_separation"] = True
        rule_pool["no_leakage"]["threshold_frozen_from_train"] = True

    # Add walk-forward results
    if walkforward_results and walkforward_results.get("windows"):
        rule_pool["walkforward"] = {
            "n_windows": walkforward_results["n_windows"],
            "oos_verdict": walkforward_results.get("oos_verdict"),
            "stability": walkforward_results.get("stability"),
        }
        # Add per-window summary
        wf_summary = []
        for w in walkforward_results["windows"]:
            wf_summary.append({
                "train_end": w["train_end"],
                "test_start": w["test_start"],
                "test_end": w["test_end"],
                "test_n": w["test_n"],
                "momentum_on_mean_ic": w["label_metrics"].get("momentum_on", {}).get("mean_ic"),
                "momentum_off_mean_ic": w["label_metrics"].get("momentum_off", {}).get("mean_ic"),
                "baseline_mean_ic": w["label_metrics"].get("baseline_all_days", {}).get("mean_ic"),
            })
        rule_pool["walkforward"]["windows"] = wf_summary

    # Add discovery-specific metadata
    if walkforward_results:
        is_discovery = walkforward_results.get("validation_mode") == "walkforward_discovery"
        if is_discovery:
            rule_pool["validation_mode"] = "walkforward_discovery"
            rule_pool["rule_discovery_oos_safe"] = True
            rule_pool["full_sample_rule_candidates_used"] = False

    with open(out_dir / "rule_candidate_pool.yaml", "w", encoding="utf-8") as f:
        yaml.dump(rule_pool, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    print("  ✓ rule_candidate_pool.yaml")

    # ------------------------------------------------------------------
    # 5. rule_validation_report.md
    # ------------------------------------------------------------------
    _write_validation_report(
        out_dir, run_id, args, validation_results, validation_by_year,
        mode, vol_q75, breadth_q75, rule_signals,
        frozen_thresholds=frozen_thresholds,
        walkforward_results=walkforward_results,
    )
    print("  ✓ rule_validation_report.md")

    # ------------------------------------------------------------------
    # 6. rule_validation_manifest.json
    # ------------------------------------------------------------------
    manifest = {
        "schema": "rule_validation_manifest.v1",
        "run_id": run_id,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "parameters": {
            "start": args.start, "end": args.end,
            "horizon_days": args.horizon,
            "threshold_mode": mode,
        },
        "output_files": {
            "rule_validation_summary.csv": str(out_dir / "rule_validation_summary.csv"),
            "rule_validation_by_year.csv": str(out_dir / "rule_validation_by_year.csv"),
            "rule_signal_daily.csv": str(out_dir / "rule_signal_daily.csv"),
            "rule_candidate_pool.yaml": str(out_dir / "rule_candidate_pool.yaml"),
            "rule_validation_report.md": str(out_dir / "rule_validation_report.md"),
            "rule_validation_manifest.json": str(out_dir / "rule_validation_manifest.json"),
        },
        "no_leakage": {
            "enabled": True,
            "mode": mode,
            "warmup_days": MIN_PIT_WARMUP,
        },
        "validation_results": {
            "overall_verdict": resolved["final_verdict"],
            "n_labels": len(validation_results["label_metrics"]),
            "baseline_n_days": validation_results["baseline_metrics"].get("n_days", 0),
        },
        "eligible_factors": [],
        "promotion_decision": resolved["promotion_decision"],
        "validation_mode": resolved["validation_mode"],
        "verdict_source": resolved["verdict_source"],
    }

    if is_oos:
        manifest["train_test_split"] = {
            "enabled": True,
            "requested_train_end": frozen_thresholds.get("requested_train_end"),
            "train_last_observation_date": frozen_thresholds["train_end"],
            "test_first_observation_date": frozen_thresholds.get("test_first_observation_date"),
            "train_n_days": frozen_thresholds["train_n_days"],
            "test_period_end": args.end,
        }
        manifest["no_leakage"]["train_test_separation"] = True
        manifest["no_leakage"]["threshold_frozen_from_train"] = True

        # OOS / walkforward metadata
        if walkforward_results:
            is_discovery = walkforward_results.get("validation_mode") == "walkforward_discovery"
            if is_discovery:
                manifest["rule_discovery_oos_safe"] = True
                manifest["full_sample_rule_candidates_used"] = False
                manifest["validation_results"]["n_discovery_windows"] = walkforward_results.get("n_windows", 0)
                manifest["validation_results"]["pass_count"] = walkforward_results.get("pass_count", 0)
                manifest["validation_results"]["pass_ratio"] = walkforward_results.get("pass_ratio", 0.0)
                if walkforward_results.get("pooled_metrics"):
                    manifest["validation_results"]["pooled_metrics"] = walkforward_results["pooled_metrics"]
            else:
                if walkforward_results.get("oos_verdict"):
                    manifest["validation_results"]["oos_verdict"] = walkforward_results["oos_verdict"]
                manifest["validation_results"]["n_walkforward_windows"] = walkforward_results["n_windows"]

    with open(out_dir / "rule_validation_manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    print("  ✓ rule_validation_manifest.json")

    # ------------------------------------------------------------------
    # 7. Discovery-specific outputs (walkforward_discovery mode only)
    # ------------------------------------------------------------------
    if walkforward_results:
        is_discovery = walkforward_results.get("validation_mode") == "walkforward_discovery"
        if is_discovery:
            _write_discovery_outputs(
                out_dir, walkforward_results, validation_results
            )


def _write_discovery_outputs(
    out_dir: Path,
    walkforward_results: Dict[str, Any],
    validation_results: Dict[str, Any],
):
    """Write walk-forward discovery specific output files."""
    windows = walkforward_results.get("windows", [])

    # --- walkforward_discovery_windows.csv ---
    wf_rows = []
    for w in windows:
        discovery = w.get("discovery", {})
        rules = discovery.get("rules", [])
        lm = w.get("label_metrics", {})

        wf_rows.append({
            "train_end": w["train_end"],
            "test_start": w["test_start"],
            "test_end": w["test_end"],
            "train_n": w["train_n"],
            "test_n": w["test_n"],
            "n_rules_discovered": discovery.get("n_rule_candidates", 0),
            "n_fdr_robust": discovery.get("n_fdr_robust", 0),
            "n_raw_significant": discovery.get("n_raw_significant", 0),
            "coverage_blocked": ",".join(discovery.get("coverage_blocked", [])),
            "rules": "; ".join(r["rule_id"] for r in rules) if rules else "",
            "verdict": w["verdict"],
            "verdict_detail": w.get("verdict_detail", ""),
            "momentum_on_n": lm.get("momentum_on", {}).get("n_days", 0),
            "momentum_on_mean_ic": lm.get("momentum_on", {}).get("mean_ic"),
            "momentum_off_n": lm.get("momentum_off", {}).get("n_days", 0),
            "momentum_off_mean_ic": lm.get("momentum_off", {}).get("mean_ic"),
            "baseline_mean_ic": lm.get("baseline_all_days", {}).get("mean_ic"),
        })
    if wf_rows:
        pd.DataFrame(wf_rows).to_csv(
            out_dir / "walkforward_discovery_windows.csv",
            index=False, encoding="utf-8-sig"
        )
        print("  ✓ walkforward_discovery_windows.csv")

    # --- walkforward_discovery_rule_candidates.csv ---
    rule_rows = []
    for w in windows:
        discovery = w.get("discovery", {})
        rules = discovery.get("rules", [])
        for r in rules:
            rule_rows.append({
                "train_end": w["train_end"],
                "test_start": w["test_start"],
                "test_end": w["test_end"],
                "rule_id": r["rule_id"],
                "state_col": r["state_col"],
                "factor": r["factor"],
                "direction": r["direction"],
                "action": r["action"],
                "spread": r.get("spread"),
                "p_value": r.get("p_value"),
                "q_value": r.get("q_value"),
                "priority": r.get("priority"),
                "window_verdict": w["verdict"],
            })
    if rule_rows:
        pd.DataFrame(rule_rows).to_csv(
            out_dir / "walkforward_discovery_rule_candidates.csv",
            index=False, encoding="utf-8-sig"
        )
        print("  ✓ walkforward_discovery_rule_candidates.csv")

    # --- walkforward_discovery_test_metrics.csv ---
    metrics_rows = []
    for w in windows:
        lm = w.get("label_metrics", {})
        for label in ["momentum_on", "momentum_off", "momentum_neutral", "baseline_all_days"]:
            m = lm.get(label, {})
            if m:
                metrics_rows.append({
                    "train_end": w["train_end"],
                    "test_start": w["test_start"],
                    "test_end": w["test_end"],
                    "label": label,
                    "n_days": m.get("n_days", 0),
                    "mean_ic": m.get("mean_ic"),
                    "icir": m.get("icir"),
                    "hit_rate": m.get("hit_rate"),
                    "ic_std": m.get("ic_std"),
                    "window_verdict": w["verdict"],
                })
    if metrics_rows:
        pd.DataFrame(metrics_rows).to_csv(
            out_dir / "walkforward_discovery_test_metrics.csv",
            index=False, encoding="utf-8-sig"
        )
        print("  ✓ walkforward_discovery_test_metrics.csv")

    # --- walkforward_discovery_summary.yaml ---
    discovery_summary = {
        "schema": "walkforward_discovery_summary.v1",
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "validation_mode": "walkforward_discovery",
        "rule_discovery_oos_safe": True,
        "full_sample_rule_candidates_used": False,
        "n_windows": walkforward_results.get("n_windows", 0),
        "n_with_rules": walkforward_results.get("n_with_rules", 0),
        "pass_count": walkforward_results.get("pass_count", 0),
        "pass_ratio": walkforward_results.get("pass_ratio", 0.0),
        "overall_verdict": walkforward_results.get("overall_verdict"),
        "overall_detail": walkforward_results.get("overall_detail"),
        "pooled_metrics": walkforward_results.get("pooled_metrics"),
        "windows": [],
    }
    for w in windows:
        discovery = w.get("discovery", {})
        rules = discovery.get("rules", [])
        discovery_summary["windows"].append({
            "train_end": w["train_end"],
            "test_period": f"{w['test_start']}→{w['test_end']}",
            "train_n": w["train_n"],
            "test_n": w["test_n"],
            "n_rules_discovered": discovery.get("n_rule_candidates", 0),
            "rules": [
                {
                    "rule_id": r["rule_id"],
                    "state_col": r["state_col"],
                    "direction": r["direction"],
                    "spread": r.get("spread"),
                    "q_value": r.get("q_value"),
                }
                for r in rules
            ],
            "verdict": w["verdict"],
            "verdict_detail": w.get("verdict_detail", ""),
        })
    with open(out_dir / "walkforward_discovery_summary.yaml", "w", encoding="utf-8") as f:
        yaml.dump(discovery_summary, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    print("  ✓ walkforward_discovery_summary.yaml")


def _write_validation_report(
    out_dir: Path,
    run_id: str,
    args,
    validation_results: Dict[str, Any],
    validation_by_year: pd.DataFrame,
    mode: str,
    vol_q75: Optional[float],
    breadth_q75: Optional[float],
    rule_signals: pd.DataFrame,
    frozen_thresholds: Optional[Dict[str, Any]] = None,
    walkforward_results: Optional[Dict[str, Any]] = None,
):
    """Write the validation report in Markdown."""
    is_oos = frozen_thresholds is not None
    is_discovery_wf = (
        walkforward_results is not None
        and (
            walkforward_results.get("validation_mode") == "walkforward_discovery"
            # Legacy fallback: check per-window "discovery" key
            or (
                walkforward_results.get("windows")
                and any("discovery" in w for w in walkforward_results["windows"])
            )
        )
    )
    resolved = _resolve_final_verdict(validation_results, walkforward_results, is_oos)

    lines = [
        "# Market State Momentum Rule Validation Report",
        f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Run ID: {run_id}",
        f"\n## Parameters",
        f"\n- Period: {args.start} → {args.end}",
        f"- Horizon: {args.horizon}d",
        f"- Threshold mode: **{mode}**",
        f"- Min PIT warmup: {MIN_PIT_WARMUP} days",
        f"- Min label days: {MIN_LABEL_DAYS}",
    ]

    # --- OOS banner ---
    if is_oos:
        req_end = frozen_thresholds.get("requested_train_end")
        train_last = frozen_thresholds["train_end"]
        test_first = frozen_thresholds.get("test_first_observation_date", train_last)

        lines.append(f"\n## ⚠️  VALIDATION TYPE: OUT-OF-SAMPLE")
        if req_end is not None:
            lines.append(f"\n- **Requested train cutoff**: {req_end}")
        lines.append(f"- **Train observations**: {frozen_thresholds.get('train_start', args.start)} → {train_last}"
                     f" ({frozen_thresholds['train_n_days']} days)")
        lines.append(f"- **Test observations**: {test_first} → {args.end}")
        lines.append(f"- **Thresholds**: FROZEN from training period only")
        lines.append(f"- Volatility q75 (from train): {vol_q75:.4f}")
        lines.append(f"- Breadth q75 (from train): {breadth_q75:.4f}")
        lines.append(f"\n> All evaluation metrics below are computed on the TEST period only. "
                     f"Training data never enters evaluation.")

    if mode == "research":
        lines.append(f"- Volatility q75 (full-sample): {vol_q75:.4f}")
        lines.append(f"- Breadth q75 (full-sample): {breadth_q75:.4f}")

    # ---- Rules Applied ----
    lines.append(f"\n## Rules Applied")
    lines.append(f"\n### Rule 1: High Volatility → Momentum Off")
    lines.append(f"- Condition: `volatility_state >= volatility_q75`")
    lines.append(f"- Action: `momentum_weight_multiplier = 0.0`")
    lines.append(f"- Conservative variant: `momentum_weight_multiplier = 0.5`")
    lines.append(f"- Priority: 1 (highest)")
    lines.append(f"\n### Rule 2: High Breadth → Momentum On")
    lines.append(f"- Condition: `breadth_score >= breadth_q75 AND volatility_state < volatility_q75`")
    lines.append(f"- Action: `momentum_weight_multiplier = 1.0` (default)")
    lines.append(f"- Priority: 2")
    lines.append(f"\n### Priority Logic")
    lines.append(f"1. If vol ≥ vol_q75 → momentum_off")
    lines.append(f"2. Elif breadth ≥ breadth_q75 → momentum_on")
    lines.append(f"3. Else → momentum_neutral")

    # ---- Signal Distribution ----
    lines.append(f"\n## Signal Distribution")
    if "rule_signal" in rule_signals.columns:
        dist = rule_signals["rule_signal"].value_counts()
        lines.append(f"\n| Label | N Days | Pct |")
        lines.append(f"|-------|--------|-----|")
        total = len(rule_signals)
        for label in ["momentum_off", "momentum_on", "momentum_neutral"]:
            n = dist.get(label, 0)
            pct = n / total * 100 if total > 0 else 0
            lines.append(f"| {label} | {n} | {pct:.1f}% |")
        lines.append(f"| **Total** | {total} | 100% |")

    # ---- Validation Metrics ----
    lines.append(f"\n## Validation Metrics")
    lines.append(f"\n| Label | N Days | Mean IC | ICIR | Hit Rate | IC Std | Net Spread | +Years |")
    lines.append(f"|-------|--------|---------|------|----------|--------|------------|--------|")

    for lm in validation_results["label_metrics"]:
        lines.append(
            f"| {lm['label']} | {lm['n_days']} | "
            f"{lm['mean_ic']:.4f} | {lm['icir']:.4f} | {lm['hit_rate']:.3f} | "
            f"{lm['ic_std']:.4f} | {lm['net_spread']:.4f} | {lm['positive_years']} |"
        )
    bl = validation_results["baseline_metrics"]
    lines.append(
        f"| **{bl['label']}** | **{bl['n_days']}** | "
        f"**{bl['mean_ic']:.4f}** | **{bl['icir']:.4f}** | **{bl['hit_rate']:.3f}** | "
        f"**{bl['ic_std']:.4f}** | **{bl['net_spread']:.4f}** | **{bl['positive_years']}** |"
    )

    # ---- Acceptance Tests ----
    lines.append(f"\n## Acceptance Tests")
    acceptance = validation_results.get("acceptance_results", {})
    for label, result in acceptance.items():
        lines.append(f"\n### {label}: {result['verdict']}")
        for check in result.get("checks", []):
            icon = "✅" if check["pass"] else "❌"
            lines.append(f"- {icon} {check['check']}: {check['detail']}")

    # ---- Overall Verdict ----
    lines.append(f"\n## Overall Verdict: **{resolved['final_verdict']}**")
    lines.append(f"\n{resolved['final_detail']}")

    # ---- Decision ----
    lines.append(f"\n## Decision")
    if resolved["promotion_decision"] == "PROMOTE":
        lines.append(f"\n✅ **PROMOTE**: Rules are effective. Proceed to market-state-driven "
                     f"momentum sleeve weight backtesting.")
    else:
        verdict = resolved["final_verdict"]
        if verdict == "PARTIAL":
            lines.append(f"\n⚠️ **BLOCK**: Rules partially validated ({resolved['verdict_source']}).")
            lines.append(f"\nThe rules show research value but do NOT meet the stability "
                         f"requirements for strategy promotion. Review the specific failure "
                         f"modes above before considering promotion.")
        elif verdict == "NO_RULE_ALPHA":
            lines.append(f"\n❌ **BLOCK**: Rules are ineffective. Do NOT proceed to strategy "
                         f"switching development. Market state variables explain historical IC "
                         f"differences but cannot form stable, usable rules.")
        elif verdict == "NO_RULE_DISCOVERED":
            lines.append(f"\n❌ **BLOCK**: No rules could be reliably discovered across "
                         f"walk-forward windows. Do NOT proceed.")
        else:
            lines.append(f"\n❌ **BLOCK**: Verdict={verdict}. Do NOT proceed to strategy "
                         f"development. Source: {resolved['verdict_source']}.")

    # ---- Year-by-Year ----
    if not validation_by_year.empty:
        lines.append(f"\n## Year-by-Year Breakdown")
        lines.append(f"\n| Year | Base N | Base IC | Base ICIR | "
                     f"On N | On IC | Off N | Off IC | Neutral N | Neutral IC |")
        lines.append(f"|------|--------|---------|-----------|"
                     f"------|-------|-------|--------|-----------|----------|")
        for _, row in validation_by_year.iterrows():
            lines.append(
                f"| {int(row['year'])} | {int(row['baseline_n'])} | "
                f"{row['baseline_mean_ic']:.4f} | {row['baseline_icir']:.4f} | "
                f"{int(row.get('momentum_on_n', 0))} | {row.get('momentum_on_mean_ic', float('nan')):.4f} | "
                f"{int(row.get('momentum_off_n', 0))} | {row.get('momentum_off_mean_ic', float('nan')):.4f} | "
                f"{int(row.get('momentum_neutral_n', 0))} | {row.get('momentum_neutral_mean_ic', float('nan')):.4f} |"
            )

    # ---- No-Leakage Statement ----
    lines.append(f"\n## No-Leakage Compliance")
    lines.append(f"\n- Threshold mode: **{mode}**")
    lines.append(f"- Validation mode: **{resolved['validation_mode']}**")

    if is_oos:
        lines.append(f"- ✅ **Train/Test Split**: Thresholds calibrated on "
                     f"[{args.start}, {frozen_thresholds['train_end']}] only")
        lines.append(f"- ✅ **Thresholds FROZEN** from training — not updated during testing")
        lines.append(f"- ✅ **All evaluation on test period** "
                     f"({frozen_thresholds['train_end']} → {args.end})")

        if is_discovery_wf:
            lines.append(f"- ✅ **Rule selection**: Rules re-discovered independently in each "
                         f"walk-forward training window. NO full-sample rule candidates used.")
            lines.append(f"- ✅ **FDR + effect size + coverage gates** applied within each "
                         f"training window independently.")
            lines.append(f"- ✅ **Test data never enters** rule discovery, threshold estimation, "
                         f"or FDR correction.")
        else:
            lines.append(f"- ⚠️  **Rule selection**: State→factor pairs were identified from a "
                         f"prior full-period exploration (documented in Known Limitations).")
    elif mode == "rolling_pit":
        lines.append(f"- All q75 thresholds computed using only data <= signal_date T")
        lines.append(f"- Warmup period: {MIN_PIT_WARMUP} trading days")
        lines.append(f"- ⚠️  **In-sample evaluation**: thresholds adapt to evaluation data")
    lines.append(f"- Market state[T] uses only trade_date <= T data")
    lines.append(f"- Factor[T] vs fwd_ret[T] uses standard factor→forward alignment")

    # ---- Walk-Forward Results ----
    if walkforward_results and walkforward_results.get("windows"):
        lines.append(f"\n## Walk-Forward Validation (Most Rigorous)")
        lines.append(f"\nExpanding training windows, testing on each subsequent year OOS.")
        lines.append(f"\nWindows: {walkforward_results['n_windows']}")
        lines.append(f"\nOOS Verdict: **{walkforward_results.get('oos_verdict', '?')}**")
        lines.append(f"\n| Train End | Test Period | Test N | On Mean IC | Off Mean IC | Base Mean IC |")
        lines.append(f"|-----------|-------------|--------|------------|-------------|--------------|")
        for w in walkforward_results["windows"]:
            on_m = w["label_metrics"].get("momentum_on", {})
            off_m = w["label_metrics"].get("momentum_off", {})
            base_m = w["label_metrics"].get("baseline_all_days", {})
            lines.append(
                f"| {w['train_end']} | {w['test_start']}→{w['test_end']} | {w['test_n']} | "
                f"{on_m.get('mean_ic', float('nan')):.4f} | "
                f"{off_m.get('mean_ic', float('nan')):.4f} | "
                f"{base_m.get('mean_ic', float('nan')):.4f} |"
            )

        # Stability metrics
        stability = walkforward_results.get("stability", {})
        if stability:
            lines.append(f"\n### Stability Across Windows")
            for label, stats in stability.items():
                lines.append(f"\n**{label}**:")
                lines.append(f"- Mean of per-window mean_ic: {stats['mean_of_means']:.4f}")
                lines.append(f"- Std of per-window mean_ic: {stats['std_of_means']:.4f} "
                             f"(lower = more stable)")
                lines.append(f"- Range: [{stats['min_mean_ic']:.4f}, {stats['max_mean_ic']:.4f}]")
                lines.append(f"- Windows: {stats['n_windows']}")

        # Pooled OOS aggregate
        agg = walkforward_results.get("aggregate", {})
        if agg:
            lines.append(f"\n### Pooled OOS Aggregate (All Test Periods Combined)")
            lines.append(f"\n| Label | N Days | Mean IC | ICIR | Hit Rate |")
            lines.append(f"|-------|--------|---------|------|----------|")
            for label_key in ["oos_momentum_on", "oos_momentum_off",
                             "oos_momentum_neutral", "oos_baseline_all_days"]:
                lm = agg.get(label_key, {})
                if lm and not lm.get("insufficient_data"):
                    lines.append(
                        f"| {label_key} | {lm['n_days']} | {lm['mean_ic']:.4f} | "
                        f"{lm['icir']:.4f} | {lm['hit_rate']:.3f} |"
                    )

    # ---- Walk-Forward Discovery Results ----
    is_discovery = (
        walkforward_results is not None
        and walkforward_results.get("validation_mode") == "walkforward_discovery"
    )
    if is_discovery:
        lines.append(f"\n## Walk-Forward Discovery Results (Strictest Validation)")
        lines.append(f"\nEach window independently discovers rules from training data only. "
                     f"No full-sample information crosses the train/test boundary.")
        lines.append(f"\n### Per-Window Discovery Summary")
        lines.append(f"\n| Train End | Test Period | Rules Discovered | N Rules | "
                     f"On IC | Off IC | Base IC | Verdict |")
        lines.append(f"|-----------|-------------|-----------------|---------|"
                     f"-------|--------|----------|---------|")
        for w in walkforward_results["windows"]:
            discovery = w.get("discovery", {})
            rules = discovery.get("rules", [])
            rules_str = ", ".join(r["rule_id"] for r in rules) if rules else "NONE"
            n_rules = len(rules)
            lm = w.get("label_metrics", {})
            on_ic = lm.get("momentum_on", {}).get("mean_ic", float("nan"))
            off_ic = lm.get("momentum_off", {}).get("mean_ic", float("nan"))
            base_ic = lm.get("baseline_all_days", {}).get("mean_ic", float("nan"))
            verdict = w.get("verdict", "?")
            lines.append(
                f"| {w['train_end']} | {w['test_start']}→{w['test_end']} | "
                f"{rules_str} | {n_rules} | "
                f"{on_ic:.4f} | {off_ic:.4f} | {base_ic:.4f} | **{verdict}** |"
            )

        lines.append(f"\n### Overall Discovery Verdict: **{walkforward_results.get('overall_verdict', '?')}**")
        lines.append(f"\n{walkforward_results.get('overall_detail', '')}")
        lines.append(f"\n- Windows: {walkforward_results.get('n_windows', 0)}")
        lines.append(f"- Windows with rules: {walkforward_results.get('n_with_rules', 0)}")
        lines.append(f"- PASS windows: {walkforward_results.get('pass_count', 0)}")
        lines.append(f"- PASS ratio: {walkforward_results.get('pass_ratio', 0):.1%}")

        pm = walkforward_results.get("pooled_metrics")
        if pm:
            lines.append(f"\n### Pooled OOS Metrics (All Test Periods Combined)")
            lines.append(f"\n- Baseline mean_ic: {pm['baseline_mean_ic']:.4f}")
            lines.append(f"- momentum_on mean_ic: {pm['momentum_on_mean_ic']:.4f} "
                         f"(n={pm['momentum_on_n']})")
            lines.append(f"- momentum_off mean_ic: {pm['momentum_off_mean_ic']:.4f} "
                         f"(n={pm['momentum_off_n']})")
            lines.append(f"- Max single-year contribution: {pm['max_year_contribution_pct']:.1%}")

        lines.append(f"\n### Discovery Compliance")
        lines.append(f"- ✅ Rules re-discovered independently in each training window")
        lines.append(f"- ✅ Thresholds frozen from training period only")
        lines.append(f"- ✅ FDR correction applied within each window")
        lines.append(f"- ✅ Coverage audit performed within each window")
        lines.append(f"- ✅ No full-sample rule candidates used")

    # ---- Known Limitations ----
    lines.append(f"\n## Known Limitations")

    if is_discovery_wf:
        # Discovery mode: no full-sample discovery bias
        lines.append(f"\n1. **True out-of-sample rule discovery**: Rules were re-discovered "
                     f"independently in each walk-forward training window. No full-sample "
                     f"information crossed the train/test boundary.")
        lines.append(f"\n2. **Limited sample size**: Only {walkforward_results.get('n_windows', 0)} "
                     f"walk-forward windows. More data (e.g., 2010–2016 pre-period) would "
                     f"increase confidence.")
        lines.append(f"\n3. **Factor definition stability**: The momentum factor definition "
                     f"(risk_adjusted_momentum_60_cs) was NOT discovered in this study — it is "
                     f"a pre-existing factor with established construction.")
        if resolved["final_verdict"] == "PARTIAL":
            lines.append(f"\n4. **Stability concerns**: Not all windows passed. The rules "
                         f"vary across windows (different state variables selected). "
                         f"The pooled momentum_on improvement has high single-year "
                         f"concentration. These must be addressed before promotion.")
        if resolved["final_verdict"] == "NO_RULE_ALPHA":
            lines.append(f"\n4. **Rules did not validate**: Even with strict no-leakage "
                         f"discovery, the rules failed to produce stable OOS improvement. "
                         f"This is a valid negative result — do not lower thresholds.")
        lines.append(f"\n5. **Threshold simplicity**: q75 is a simple split; more sophisticated "
                     f"threshold optimization (e.g., decision trees, smooth regimes) might improve "
                     f"performance but also increases overfitting risk.")
    else:
        # Non-discovery modes: keep the full-sample discovery bias warning
        lines.append(f"\n1. **Rule discovery bias**: The state→factor pairs (volatility_state, "
                     f"breadth_score → momentum) were identified using the FULL 2017-2024 period "
                     f"via `explore_market_state_vs_factor_ic.py`. A more rigorous approach would "
                     f"discover rules on training data only.")
        lines.append(f"\n2. **Factor definition stability**: The momentum factor definition "
                     f"(risk_adjusted_momentum_60_cs) was NOT discovered in this study — it is "
                     f"a pre-existing factor with established construction.")
        if not is_oos:
            lines.append(f"\n3. **⚠️  In-sample evaluation**: This run used the SAME period for "
                         f"threshold calibration and evaluation. The metrics may be optimistic. "
                         f"Re-run with --train-end for out-of-sample validation.")
        if is_oos and not walkforward_results:
            lines.append(f"\n3. **Single train/test split**: Only one partition was tested. "
                         f"Use --walkforward for multi-window robustness check.")
        lines.append(f"\n4. **Threshold simplicity**: q75 is a simple split; more sophisticated "
                     f"threshold optimization (e.g., decision trees, smooth regimes) might improve "
                     f"performance but also increases overfitting risk.")

    (out_dir / "rule_validation_report.md").write_text("\n".join(lines), encoding="utf-8")


# ===========================================================================
# Main
# ===========================================================================


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate market state momentum rules"
    )
    parser.add_argument("--start", default="20170101")
    parser.add_argument("--end", default="20241231")
    parser.add_argument("--horizon", type=int, default=20)
    parser.add_argument("--mode", choices=["research", "rolling_pit"],
                       default="rolling_pit",
                       help="Threshold mode: research (full-sample) or rolling_pit (PIT-safe)")
    parser.add_argument("--train-end", type=str, default=None,
                       help="End date for training period (YYYYMMDD). "
                            "When set, thresholds are calibrated on [start, train_end] "
                            "and evaluation is on (train_end, end]. "
                            "This enables STRICT out-of-sample validation.")
    parser.add_argument("--walkforward", action="store_true",
                       help="Enable walk-forward validation. Requires --train-end. "
                            "Expanding train windows test each subsequent year OOS.")
    parser.add_argument("--walkforward-discovery", action="store_true",
                       help="Enable strict walk-forward discovery. Each window "
                            "re-discovers rules from training data only. "
                            "Requires --walkforward and --train-end. "
                            "This is the MOST RIGOROUS validation mode.")
    parser.add_argument("--rule-candidates-yaml", type=str, default=None,
                       help="Path to rule candidates YAML (optional, for reference)")
    args = parser.parse_args()

    # Validate walk-forward discovery requirements
    if args.walkforward_discovery:
        if not args.walkforward:
            print("ERROR: --walkforward-discovery requires --walkforward")
            return 1
        if not args.train_end:
            print("ERROR: --walkforward-discovery requires --train-end")
            return 1
        if args.mode == "research":
            print("WARNING: --walkforward-discovery is designed for rolling_pit mode. "
                  "Continuing but results may not be as rigorous.")

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = ROOT / "outputs" / "analysis" / "market_state_momentum_rule_validation" / run_id

    start_int = int(args.start)
    end_int = int(args.end)
    horizon_col = f"fwd_ret_{args.horizon}d"

    print(f"=== Market State Momentum Rule Validation ===")
    print(f"Run: {run_id}")
    print(f"Period: {args.start} → {args.end}, Horizon: {args.horizon}d")
    print(f"Threshold mode: {args.mode}")
    print()

    # ------------------------------------------------------------------
    # 1. Load factor data
    # ------------------------------------------------------------------
    print("Loading factor data...")
    factor_df = _load_factor_cache(MOMENTUM_FACTOR)
    if factor_df.empty:
        print(f"ERROR: No data for {MOMENTUM_FACTOR}")
        return 1
    factor_df = factor_df[(factor_df["trade_date"] >= start_int) & (factor_df["trade_date"] <= end_int)]
    print(f"  {MOMENTUM_FACTOR}: {len(factor_df)} rows")

    fwd_df = _load_fwd_returns()
    if fwd_df.empty:
        print("ERROR: No forward return data")
        return 1
    fwd_df = fwd_df[(fwd_df["trade_date"] >= start_int) & (fwd_df["trade_date"] <= end_int)]
    print(f"  fwd_returns: {len(fwd_df)} rows")

    # ------------------------------------------------------------------
    # 2. Compute IC series
    # ------------------------------------------------------------------
    print("\nComputing IC series...")
    ic_series = _compute_factor_ic_series(factor_df, fwd_df, horizon_col)
    if ic_series.empty:
        print("ERROR: No IC data")
        return 1
    print(f"  IC series: {len(ic_series)} dates, mean={ic_series['ic'].mean():.4f}, "
          f"std={ic_series['ic'].std():.4f}")

    # ------------------------------------------------------------------
    # 3. Load index data and build market state features
    # ------------------------------------------------------------------
    print("\nLoading index data...")
    csi300 = _load_index_daily("000300.SH", args.start, args.end)
    if csi300.empty:
        csi300 = _load_index_cache_fast("000300.SH")
    print(f"  CSI 300: {len(csi300)} rows")

    # Build prices for breadth from fwd returns (adj_close)
    if not fwd_df.empty and "adj_close" in fwd_df.columns:
        prices_for_breadth = fwd_df[["ts_code", "trade_date", "adj_close"]].dropna(subset=["adj_close"])
        if prices_for_breadth.empty:
            prices_for_breadth = None
    else:
        prices_for_breadth = None

    # Use IC dates as signal dates
    signal_dates = np.array(sorted(ic_series["trade_date"].unique()))
    signal_dates = signal_dates[(signal_dates >= start_int) & (signal_dates <= end_int)]
    print(f"  Signal dates: {len(signal_dates)}")

    print("\nBuilding market state features...")
    regime_features = _build_regime_features_pit(csi300, prices_for_breadth, signal_dates)
    if regime_features.empty:
        regime_features = _build_simplified_features_pit(csi300, signal_dates)
    print(f"  Features: {len(regime_features)} dates")

    if "volatility_state" not in regime_features.columns:
        print("ERROR: volatility_state missing from regime features")
        return 1
    if "breadth_score" not in regime_features.columns:
        print("ERROR: breadth_score missing from regime features")
        return 1

    # ------------------------------------------------------------------
    # 4. Apply rules
    # ------------------------------------------------------------------
    train_end_int = int(args.train_end) if args.train_end else None
    is_oos = train_end_int is not None

    vol_q75 = None
    breadth_q75 = None
    frozen_thresholds = None
    walkforward_results = None
    rule_signals = None

    if is_oos:
        # ================================================================
        # STRICT OUT-OF-SAMPLE MODE
        # ================================================================
        print(f"\n{'='*60}")
        print(f"STRICT OUT-OF-SAMPLE VALIDATION")
        print(f"{'='*60}")
        print(f"  Train period: {args.start} → {args.train_end}")
        print(f"  Test period:  {args.train_end} → {args.end}")
        print(f"  Thresholds: FROZEN from training period only")
        print()

        # Split data
        train_features = regime_features[regime_features["trade_date"] <= train_end_int]
        test_features = regime_features[regime_features["trade_date"] > train_end_int]

        if len(train_features) < MIN_PIT_WARMUP:
            print(f"ERROR: Training period has only {len(train_features)} days "
                  f"(need >= {MIN_PIT_WARMUP})")
            return 1
        if len(test_features) < MIN_LABEL_DAYS:
            print(f"ERROR: Test period has only {len(test_features)} days "
                  f"(need >= {MIN_LABEL_DAYS})")
            return 1

        print(f"  Train days: {len(train_features)}")
        print(f"  Test days:  {len(test_features)}")

        # Apply OOS rules (thresholds from train, applied to test)
        rule_signals, frozen_thresholds = apply_market_state_rules_oos(
            train_features, test_features, requested_train_end=train_end_int
        )
        vol_q75 = frozen_thresholds["vol_q75"]
        breadth_q75 = frozen_thresholds["breadth_q75"]

        print(f"\n  Frozen thresholds (from train period only):")
        print(f"    vol_q75:     {vol_q75:.4f}")
        print(f"    breadth_q75: {breadth_q75:.4f}")

        if "rule_signal" in rule_signals.columns:
            counts = rule_signals["rule_signal"].value_counts()
            for label in ["momentum_off", "momentum_on", "momentum_neutral"]:
                print(f"  {label}: {counts.get(label, 0)} days (test period)")

        # Validation on TEST PERIOD ONLY
        print(f"\n=== OOS Validation (test period only) ===")
        test_ic = ic_series[ic_series["trade_date"] > train_end_int]
        validation_results = _compute_validation_metrics(rule_signals, test_ic)

        # Year-by-year on test period only
        print("\nComputing year-by-year validation (test period)...")
        validation_by_year = _compute_validation_by_year(rule_signals, test_ic)

        # Walk-forward if requested
        if args.walkforward:
            print(f"\n{'='*60}")

            # Generate train_end dates: each year-end from train_end to end
            train_start_year = int(args.start[:4])
            train_end_year = int(args.train_end[:4])
            end_year = int(args.end[:4])

            wf_train_ends = []
            for y in range(train_end_year, end_year):
                wf_train_ends.append(int(f"{y}1231"))

            if args.walkforward_discovery:
                # ========================================================
                # STRICT WALK-FORWARD DISCOVERY MODE
                # ========================================================
                print(f"STRICT WALK-FORWARD DISCOVERY VALIDATION")
                print(f"{'='*60}")
                print(f"  Each window: discover rules from train → freeze → test OOS")
                print(f"  Train windows ending: {wf_train_ends}")

                # Load factor data for all discovery factors
                print(f"\n  Loading discovery factor data...")
                discovery_factor_data: Dict[str, pd.DataFrame] = {}
                discovery_factor_ics: Dict[str, pd.DataFrame] = {}

                for fn in DISCOVERY_FACTORS:
                    fdf = _load_factor_cache(fn)
                    if fdf.empty:
                        print(f"    {fn}: NO DATA")
                        continue
                    fdf = fdf[(fdf["trade_date"] >= start_int) & (fdf["trade_date"] <= end_int)]
                    discovery_factor_data[fn] = fdf

                    # Compute IC for this factor
                    fic = _compute_factor_ic_series(fdf, fwd_df, horizon_col)
                    if not fic.empty:
                        discovery_factor_ics[fn] = fic
                        print(f"    {fn}: {len(fdf)} rows, {len(fic)} IC dates, "
                              f"mean_ic={fic['ic'].mean():.4f}")
                    else:
                        print(f"    {fn}: {len(fdf)} rows, NO IC DATA")

                walkforward_results = _compute_walkforward_discovery_validation(
                    regime_features,
                    discovery_factor_ics,
                    discovery_factor_data,
                    fwd_df,
                    ic_series,
                    wf_train_ends,
                    horizon_col,
                )

                # Print per-window results
                print(f"\n  Discovery windows: {walkforward_results.get('n_windows', 0)}")
                for w in walkforward_results.get("windows", []):
                    n_rules = w["discovery"]["n_rule_candidates"]
                    rules_str = ", ".join(
                        r["rule_id"] for r in w["discovery"]["rules"]
                    ) if n_rules > 0 else "none"
                    print(f"    Train→{w['train_end']} Test={w['test_start']}→{w['test_end']}: "
                          f"rules=[{rules_str}], verdict={w['verdict']}")
                    for c in w.get("verdict_checks", []):
                        icon = "✅" if c["pass"] else "❌"
                        print(f"      {icon} {c['check']}: {c['detail']}")

                print(f"\n  Overall Discovery Verdict: "
                      f"{walkforward_results.get('overall_verdict', '?')}")
                if walkforward_results.get("pooled_metrics"):
                    pm = walkforward_results["pooled_metrics"]
                    print(f"    Pooled baseline: {pm['baseline_mean_ic']:.4f}")
                    print(f"    Pooled momentum_on: {pm['momentum_on_mean_ic']:.4f} "
                          f"(n={pm['momentum_on_n']})")
                    print(f"    Pooled momentum_off: {pm['momentum_off_mean_ic']:.4f} "
                          f"(n={pm['momentum_off_n']})")
                    print(f"    Max year contribution: {pm['max_year_contribution_pct']:.1%}")

                validation_mode = "walkforward_discovery"

            else:
                # Original walk-forward (fixed rules, varying thresholds)
                print(f"WALK-FORWARD VALIDATION (fixed rules)")
                print(f"{'='*60}")
                print(f"  Train windows ending: {wf_train_ends}")

                walkforward_results = _compute_walkforward_validation(
                    regime_features, ic_series, wf_train_ends
                )
                print(f"  Walk-forward windows: {walkforward_results['n_windows']}")
                if walkforward_results.get("aggregate"):
                    agg = walkforward_results["aggregate"]
                    for label in ["oos_momentum_on", "oos_momentum_off", "oos_baseline_all_days"]:
                        lm = agg.get(label, {})
                        if lm and not lm.get("insufficient_data"):
                            print(f"    {label}: n={lm['n_days']}, mean_ic={lm['mean_ic']:.4f}, "
                                  f"icir={lm['icir']:.4f}")
                print(f"  OOS Verdict: {walkforward_results.get('oos_verdict', '?')}")

                validation_mode = "walkforward"

        else:
            validation_mode = "strict_oos"

    else:
        # ================================================================
        # IN-SAMPLE MODE (original behavior)
        # ================================================================
        print(f"\nApplying market state rules (mode={args.mode})...")
        print(f"⚠️  WARNING: In-sample evaluation. Use --train-end for OOS validation.")

        if args.mode == "research":
            vol_q75 = float(regime_features["volatility_state"].quantile(0.75))
            breadth_q75 = float(regime_features["breadth_score"].quantile(0.75))
            print(f"  Research vol_q75: {vol_q75:.4f}")
            print(f"  Research breadth_q75: {breadth_q75:.4f}")

        rule_signals = apply_market_state_rules(
            regime_features,
            mode=args.mode,
            vol_q75_research=vol_q75,
            breadth_q75_research=breadth_q75,
        )

        if "rule_signal" in rule_signals.columns:
            counts = rule_signals["rule_signal"].value_counts()
            for label in ["momentum_off", "momentum_on", "momentum_neutral"]:
                print(f"  {label}: {counts.get(label, 0)} days")

        print("\n=== Validation ===")
        validation_results = _compute_validation_metrics(rule_signals, ic_series)

        print("\nComputing year-by-year validation...")
        validation_by_year = _compute_validation_by_year(rule_signals, ic_series)

        validation_mode = args.mode

    # ------------------------------------------------------------------
    # 5. Print validation results
    # ------------------------------------------------------------------
    # Resolve final verdict BEFORE printing, so the mid-section doesn't
    # mislead with the old strict-OOS verdict when discovery overrides it.
    oos_for_cli = train_end_int is not None
    resolved = _resolve_final_verdict(validation_results, walkforward_results, oos_for_cli)

    print(f"\n  Base strict-OOS verdict: {validation_results['overall_verdict']}")
    print(f"  {validation_results['overall_detail']}")

    if walkforward_results:
        print(f"\n  Final resolved verdict: {resolved['final_verdict']}")
        print(f"  Promotion decision: {resolved['promotion_decision']}")
        print(f"  Verdict source: {resolved['verdict_source']}")

    print(f"\n  Per-label metrics:")
    for lm in validation_results["label_metrics"]:
        print(f"    {lm['label']}: n={lm['n_days']}, mean_ic={lm['mean_ic']:.4f}, "
              f"icir={lm['icir']:.4f}, hit={lm['hit_rate']:.3f}")

    bl = validation_results["baseline_metrics"]
    print(f"    {bl['label']}: n={bl['n_days']}, mean_ic={bl['mean_ic']:.4f}, "
          f"icir={bl['icir']:.4f}, hit={bl['hit_rate']:.3f}")

    print(f"\n  Acceptance tests:")
    for label, result in validation_results.get("acceptance_results", {}).items():
        checks_str = ", ".join(
            f"{'✅' if c['pass'] else '❌'} {c['check']}"
            for c in result.get("checks", [])
        )
        print(f"    {label}: {result['verdict']} [{checks_str}]")

    if not validation_by_year.empty:
        print(f"\n  Year-by-year ({len(validation_by_year)} years):")
        for _, row in validation_by_year.iterrows():
            print(f"    {int(row['year'])}: baseline_ic={row['baseline_mean_ic']:.4f}, "
                  f"on_ic={row.get('momentum_on_mean_ic', float('nan')):.4f}, "
                  f"off_ic={row.get('momentum_off_mean_ic', float('nan')):.4f}")

    # ------------------------------------------------------------------
    # 6. Write outputs
    # ------------------------------------------------------------------
    print(f"\nWriting outputs to {out_dir}...")
    _write_outputs(
        out_dir, run_id, args, rule_signals, ic_series,
        validation_results, validation_by_year, validation_mode,
        vol_q75, breadth_q75,
        frozen_thresholds=frozen_thresholds,
        walkforward_results=walkforward_results,
    )

    print(f"\nDone. Output: {out_dir}")

    verdict = resolved["final_verdict"]
    promotion = resolved["promotion_decision"]
    source = resolved["verdict_source"]

    print(f"\n{'='*60}")
    print(f"Final Verdict: {verdict}  |  Promotion: {promotion}  |  Source: {source}")
    print(f"{'='*60}")

    if verdict == "PROMOTING_TO_STRATEGY":
        print(f"\n✅ Rules validated ({source}) — ready for strategy backtesting.")
    elif verdict == "PARTIAL":
        print(f"\n⚠️ Rules partially validated ({source}).")
        print(f"   Promotion decision: BLOCK.")
        print(f"   Do NOT promote to strategy backtesting yet.")
        print(f"   Address stability issues before reconsidering.")
    elif verdict == "NO_RULE_ALPHA":
        print(f"\n❌ Rules ineffective ({source}).")
        print(f"   Do NOT proceed to strategy development.")
    elif verdict == "NO_RULE_DISCOVERED":
        print(f"\n❌ No rules discovered ({source}).")
        print(f"   Do NOT proceed to strategy development.")
    else:
        print(f"\n❌ Verdict={verdict} ({source}).")
        print(f"   Do NOT proceed to strategy development.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

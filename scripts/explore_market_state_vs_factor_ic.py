#!/usr/bin/env python
"""
Market State vs Factor IC — exploratory conditional analysis.

Tests whether market state variables (all PIT-observable) predict
differences in factor forward IC.  If any state dimension reliably
separates high-IC from low-IC periods for a given factor, that
dimension is a candidate for building a true market-state-driven
style allocator.

Market state variables (all from existing PIT-verified data):
  1. trend_strength      — index trend (RegimeDetector)
  2. volatility_state    — index realized vol (RegimeDetector)
  3. breadth_score       — market participation (RegimeDetector)
  4. turnover_state      — volume z-score (RegimeDetector)
  5. size_spread_20d     — CSI 500 / CSI 300 20d relative return
  6. growth_value_spread_20d — CSI 300 Growth / CSI 300 Value 20d rel return

Factors tested:
  - risk_adjusted_momentum_60_cs (momentum representative)
  - valuation_reversion_3y_cs   (value repair)
  - earnings_acceleration_cs     (growth quality)

For each (state_dimension, factor) pair, the script groups dates into
quartiles by state value and reports:
  - mean IC per quartile
  - top vs bottom quartile spread (Q4 - Q1)
  - t-statistic of the spread
  - ICIR per quartile
  - hit rate per quartile

Usage:
  python -X utf8 scripts/explore_market_state_vs_factor_ic.py
  python -X utf8 scripts/explore_market_state_vs_factor_ic.py --start 20170101 --end 20241231
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
from scipy.stats import ttest_ind

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ===========================================================================
# Config
# ===========================================================================

MOMENTUM_REPRESENTATIVE = "risk_adjusted_momentum_60_cs"
VALUE_REPRESENTATIVE = "valuation_reversion_3y_cs"
GROWTH_REPRESENTATIVE = "earnings_acceleration_cs"

TEST_FACTORS = [MOMENTUM_REPRESENTATIVE, VALUE_REPRESENTATIVE, GROWTH_REPRESENTATIVE]

INDEX_CODES = {
    "csi300": "000300.SH",
    "csi500": "000905.SH",
    "csi300_growth": "000918.SH",
    "csi300_value": "000919.SH",
}

# Minimum observations per quartile for a valid comparison
MIN_OBS_PER_QUARTILE = 20

# ===========================================================================
# Data loading helpers
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
    """Load index daily OHLCV data from cache or API."""
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
    """Fast load index daily from parquet cache only (no API fallback)."""
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
    """Compute daily rank IC for a factor. Returns [trade_date, ic]."""
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
# Market state features
# ===========================================================================

def _compute_index_spread(
    idx1: pd.DataFrame, idx2: pd.DataFrame, window: int = 20, label: str = "spread"
) -> pd.DataFrame:
    """Compute rolling relative return spread between two indexes.

    spread[t] = (idx1_return[t-window:t] - idx2_return[t-window:t])

    Returns DataFrame with [trade_date, {label}_20d].
    """
    if idx1.empty or idx2.empty:
        return pd.DataFrame()

    # Align on dates
    merged = idx1[["trade_date", "close"]].merge(
        idx2[["trade_date", "close"]],
        on="trade_date", how="inner",
        suffixes=("_1", "_2")
    )
    if merged.empty:
        return pd.DataFrame()

    merged = merged.sort_values("trade_date")
    merged["ret_1"] = merged["close_1"].pct_change()
    merged["ret_2"] = merged["close_2"].pct_change()

    cum_1 = (1 + merged["ret_1"]).rolling(window).apply(np.prod, raw=True) - 1
    cum_2 = (1 + merged["ret_2"]).rolling(window).apply(np.prod, raw=True) - 1
    merged[f"{label}_20d"] = cum_1 - cum_2

    return merged[["trade_date", f"{label}_20d"]].dropna()


def _build_regime_features(
    index_df: pd.DataFrame,
    prices_df: Optional[pd.DataFrame],
    signal_dates: np.ndarray,
) -> pd.DataFrame:
    """Build regime features (trend, vol, breadth, turnover) for each signal_date.

    Uses RegimeDetector in PIT mode (only data <= signal_date).
    """
    try:
        from alpha.regime_detector import RegimeDetector
    except ImportError:
        print("  WARNING: RegimeDetector not available, using simplified features")
        return _build_simplified_features(index_df, signal_dates)

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


def _build_simplified_features(
    index_df: pd.DataFrame, signal_dates: np.ndarray
) -> pd.DataFrame:
    """Simplified trend/vol features from index data alone (no RegimeDetector)."""
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

        # Trend: price vs MA60, MA120, multi-window returns
        ret_20 = (closes[-1] / closes[-21]) - 1 if len(closes) > 20 else 0
        ret_60 = (closes[-1] / closes[-61]) - 1 if len(closes) > 60 else 0
        ret_120 = (closes[-1] / closes[-121]) - 1 if len(closes) > 120 else 0
        ma60 = np.mean(closes[-60:]) if len(closes) >= 60 else closes[-1]
        ma120 = np.mean(closes[-120:]) if len(closes) >= 120 else closes[-1]
        price_vs_ma60 = (closes[-1] / ma60 - 1) if ma60 > 0 else 0
        price_vs_ma120 = (closes[-1] / ma120 - 1) if ma120 > 0 else 0

        trend = 0.20 * ret_20 + 0.35 * ret_60 + 0.15 * ret_120 + 0.15 * price_vs_ma60 + 0.10 * price_vs_ma120

        # Vol: 20d realized vol annualized
        vol_20d = float(np.std(log_rets[-20:]) * np.sqrt(252)) if len(log_rets) >= 20 else 0.15

        # Turnover: volume z-score
        if "vol" in pit.columns:
            vols = pit["vol"].values.astype(float)
            vol_20d_avg = np.mean(vols[-20:]) if len(vols) >= 20 else 0
            vol_60d_avg = np.mean(vols[-60:]) if len(vols) >= 60 else vol_20d_avg
            vol_60d_std = np.std(vols[-60:]) if len(vols) >= 60 else 1.0
            turnover = (vol_20d_avg - vol_60d_avg) / vol_60d_std if vol_60d_std > 0 else 0.0
        else:
            turnover = 0.0

        # Breadth: not available without prices_df → neutral
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
# Conditional analysis
# ===========================================================================

def _conditional_ic_analysis(
    panel: pd.DataFrame,
    state_col: str,
    factor_name: str,
    n_quantiles: int = 4,
) -> Dict[str, Any]:
    """For a given state dimension and factor, analyze IC across state quantiles.

    Returns dict with:
      - state_col, factor
      - n_total, n_valid
      - per_quantile: [{q, n, mean_ic, icir, hit_rate, ic_std}, ...]
      - top_vs_bottom_spread, t_stat, p_value
      - direction: "positive" (high state → high IC) or "negative" or "none"
      - is_significant (p < 0.05)
    """
    sub = panel[[state_col, f"{factor_name}_ic"]].dropna().copy()
    n_total = len(sub)

    if n_total < MIN_OBS_PER_QUARTILE * n_quantiles:
        return {
            "state_col": state_col, "factor": factor_name,
            "n_total": n_total, "n_valid": 0,
            "error": f"insufficient data ({n_total} < {MIN_OBS_PER_QUARTILE * n_quantiles})",
        }

    # Assign quantile labels
    sub["q"] = pd.qcut(sub[state_col], q=n_quantiles, labels=False, duplicates="drop")
    n_actual = sub["q"].nunique()
    if n_actual < 2:
        return {
            "state_col": state_col, "factor": factor_name,
            "n_total": n_total, "n_valid": n_total,
            "error": f"only {n_actual} distinct quantiles (low variance in {state_col})",
        }

    ic_col = f"{factor_name}_ic"
    per_q = []
    for q in range(n_actual):
        q_data = sub[sub["q"] == q][ic_col]
        if len(q_data) < MIN_OBS_PER_QUARTILE:
            continue
        mean_ic = float(q_data.mean())
        ic_std = float(q_data.std())
        icir = float(mean_ic / ic_std) if ic_std > 0 else 0.0
        hit = float((q_data > 0).mean())
        per_q.append({
            "quantile": q,
            "n": len(q_data),
            "mean_ic": mean_ic,
            "icir": icir,
            "hit_rate": hit,
            "ic_std": ic_std,
            "state_min": float(sub[sub["q"] == q][state_col].min()),
            "state_max": float(sub[sub["q"] == q][state_col].max()),
        })

    if len(per_q) < 2:
        return {
            "state_col": state_col, "factor": factor_name,
            "n_total": n_total, "n_valid": n_total,
            "error": "not enough valid quantiles after filtering",
        }

    # Top vs bottom spread
    top = per_q[-1]
    bottom = per_q[0]
    spread = top["mean_ic"] - bottom["mean_ic"]

    # t-test between top and bottom quantile
    q_max = per_q[-1]["quantile"]
    q_min = per_q[0]["quantile"]
    top_data = sub[sub["q"] == q_max][ic_col]
    bottom_data = sub[sub["q"] == q_min][ic_col]

    try:
        t_stat, p_value = ttest_ind(top_data, bottom_data, equal_var=False)
        t_stat = float(t_stat)
        p_value = float(p_value)
    except Exception:
        t_stat, p_value = float("nan"), float("nan")

    # Direction
    if spread > 0 and p_value < 0.05:
        direction = "positive"  # higher state → higher IC
    elif spread < 0 and p_value < 0.05:
        direction = "negative"  # higher state → lower IC
    else:
        direction = "none"

    return {
        "state_col": state_col,
        "factor": factor_name,
        "n_total": n_total,
        "n_valid": n_total,
        "n_quantiles": n_actual,
        "per_quantile": per_q,
        "top_vs_bottom_spread": spread,
        "t_statistic": t_stat,
        "p_value": p_value,
        "direction": direction,
        "is_significant": p_value < 0.05,
    }


# ===========================================================================
# FDR correction (Benjamini-Hochberg)
# ===========================================================================

def _apply_fdr_correction(
    all_results: List[Dict[str, Any]],
    raw_p_threshold: float = 0.05,
    fdr_q_threshold: float = 0.10,
    min_abs_ic_spread: float = 0.02,
) -> List[Dict[str, Any]]:
    """Apply Benjamini-Hochberg FDR correction to all state×factor tests.

    For each result, adds:
      - q_value: FDR-adjusted p-value
      - significant_raw: p < raw_p_threshold
      - significant_fdr: q < fdr_q_threshold
      - passes_effect_size: abs(spread) >= min_abs_ic_spread

    Returns the enriched list.
    """
    # Collect valid p-values
    valid_indices = []
    p_values = []
    for i, r in enumerate(all_results):
        pv = r.get("p_value", float("nan"))
        if not np.isnan(pv) and r.get("n_valid", 0) > 0:
            valid_indices.append(i)
            p_values.append(pv)

    if len(p_values) < 2:
        # Can't do FDR with < 2 tests; with 1 test, q = p
        for r in all_results:
            pv = r.get("p_value", float("nan"))
            r["q_value"] = pv if not np.isnan(pv) else float("nan")
            r["significant_raw"] = not np.isnan(pv) and pv < raw_p_threshold
            r["significant_fdr"] = r["significant_raw"]  # same when n=1
            r["passes_effect_size"] = (
                not np.isnan(r.get("top_vs_bottom_spread", float("nan")))
                and abs(r["top_vs_bottom_spread"]) >= min_abs_ic_spread
            )
        return all_results

    # Benjamini-Hochberg procedure
    p_array = np.array(p_values)
    n = len(p_array)
    # Sort p-values ascending
    sorted_idx = np.argsort(p_array)
    sorted_p = p_array[sorted_idx]
    ranks = np.arange(1, n + 1)

    # BH adjusted p-values (q-values)
    q_raw = sorted_p * n / ranks

    # Ensure monotonicity: going from largest p to smallest,
    # q-value = min(current q_raw, next q-value)
    q_values = np.empty(n)
    q_values[-1] = q_raw[-1]
    for i in range(n - 2, -1, -1):
        q_values[i] = min(q_raw[i], q_values[i + 1])

    # Map back to original ordering
    inverse_idx = np.argsort(sorted_idx)
    q_original = q_values[inverse_idx]

    # Build lookup
    p_to_q = {}
    for vi, qv in zip(valid_indices, q_original):
        p_to_q[vi] = float(qv)

    for i, r in enumerate(all_results):
        pv = r.get("p_value", float("nan"))
        if i in p_to_q:
            r["q_value"] = p_to_q[i]
        else:
            r["q_value"] = float("nan")

        r["significant_raw"] = (
            not np.isnan(pv) and pv < raw_p_threshold
        )
        r["significant_fdr"] = (
            not np.isnan(r["q_value"]) and r["q_value"] < fdr_q_threshold
        )
        r["passes_effect_size"] = (
            not np.isnan(r.get("top_vs_bottom_spread", float("nan")))
            and abs(r["top_vs_bottom_spread"]) >= min_abs_ic_spread
        )

    return all_results


def _classify_findings_into_tiers(
    all_results: List[Dict[str, Any]],
    coverage_blocked_factors: set,
) -> Dict[str, List[Dict[str, Any]]]:
    """Classify findings into three tiers.

    Tier 1 — raw_significant: p < 0.05 (for reference only)
    Tier 2 — fdr_robust: significant_fdr AND passes_effect_size
    Tier 3 — rule_candidates: fdr_robust AND factor NOT coverage_blocked
                              AND n_per_quantile >= MIN_OBS_PER_QUARTILE
                              AND direction != "none"

    Returns dict with keys: raw_significant, fdr_robust, rule_candidates
    """
    tiers: Dict[str, List[Dict[str, Any]]] = {
        "raw_significant": [],
        "fdr_robust": [],
        "rule_candidates": [],
    }

    for r in all_results:
        if r.get("error"):
            continue

        factor = r.get("factor", "?")
        is_blocked = factor in coverage_blocked_factors

        # Tier 1: raw significant
        if r.get("significant_raw"):
            tiers["raw_significant"].append({
                "state_col": r["state_col"],
                "factor": factor,
                "spread": r.get("top_vs_bottom_spread"),
                "p_value": r.get("p_value"),
                "q_value": r.get("q_value"),
                "direction": r.get("direction"),
                "coverage_blocked": is_blocked,
            })

        # Tier 2: FDR robust
        if r.get("significant_fdr") and r.get("passes_effect_size"):
            tiers["fdr_robust"].append({
                "state_col": r["state_col"],
                "factor": factor,
                "spread": r.get("top_vs_bottom_spread"),
                "p_value": r.get("p_value"),
                "q_value": r.get("q_value"),
                "direction": r.get("direction"),
                "coverage_blocked": is_blocked,
                "per_quantile": r.get("per_quantile", []),
            })

        # Tier 3: rule candidates
        if (r.get("significant_fdr")
                and r.get("passes_effect_size")
                and not is_blocked
                and r.get("direction") != "none"
                and r.get("n_valid", 0) >= MIN_OBS_PER_QUARTILE * 2):
            tiers["rule_candidates"].append({
                "state_col": r["state_col"],
                "factor": factor,
                "spread": r.get("top_vs_bottom_spread"),
                "p_value": r.get("p_value"),
                "q_value": r.get("q_value"),
                "direction": r.get("direction"),
                "t_statistic": r.get("t_statistic"),
                "per_quantile": r.get("per_quantile", []),
                "interpretation": _build_rule_interpretation(r),
            })

    return tiers


def _build_rule_interpretation(result: Dict[str, Any]) -> str:
    """Build human-readable interpretation of a rule candidate."""
    state = result.get("state_col", "?")
    factor = result.get("factor", "?")
    direction = result.get("direction", "?")
    spread = result.get("spread",
                         result.get("top_vs_bottom_spread", 0.0))

    state_labels = {
        "trend_strength": "index trend strength",
        "volatility_state": "index realized volatility",
        "breadth_score": "market breadth (pct stocks above MA)",
        "turnover_state": "volume/turnover z-score",
        "size_spread_20d": "CSI 500 vs CSI 300 20d relative return",
        "gv_spread_20d": "CSI 300 Growth vs Value 20d relative return",
    }
    state_label = state_labels.get(state, state)

    factor_labels = {
        "risk_adjusted_momentum_60_cs": "momentum factor",
        "valuation_reversion_3y_cs": "value repair factor",
        "earnings_acceleration_cs": "growth quality factor",
    }
    factor_label = factor_labels.get(factor, factor)

    if direction == "negative":
        return (
            f"When {state_label} is HIGH, {factor_label} IC is LOWER "
            f"(spread={spread:.4f}). Consider reducing {factor_label} "
            f"weight in high-{state_label} environments."
        )
    elif direction == "positive":
        return (
            f"When {state_label} is HIGH, {factor_label} IC is HIGHER "
            f"(spread={spread:.4f}). Consider increasing {factor_label} "
            f"weight in high-{state_label} environments."
        )
    return f"No clear directional interpretation for {state_label} → {factor_label}."


# ===========================================================================
# Coverage audit (reuses logic from evaluate_factor_style_signals)
# ===========================================================================

def _compute_factor_coverage_for_market_state(
    factor_df: pd.DataFrame,
    fwd_df: pd.DataFrame,
) -> Dict[str, Any]:
    """Compute factor coverage vs forward return universe.

    Reuses the same thresholds as evaluate_factor_style_signals.py:
      - MIN_MEDIAN_COVERAGE_PCT = 0.80
      - MIN_YEARLY_COVERAGE_PCT = 0.60

    Returns dict with coverage metrics and blocking status.
    """
    from scripts.evaluate_factor_style_signals import (
        _compute_coverage, _evaluate_coverage,
    )
    cov_df = _compute_coverage(factor_df, fwd_df)
    return _evaluate_coverage(cov_df)


# ===========================================================================
# Main
# ===========================================================================

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Explore whether market state predicts factor IC differences"
    )
    parser.add_argument("--start", default="20170101")
    parser.add_argument("--end", default="20241231")
    parser.add_argument("--horizon", type=int, default=20)
    args = parser.parse_args()

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = ROOT / "outputs" / "analysis" / "market_state_vs_factor_ic" / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    start_int = int(args.start)
    end_int = int(args.end)
    horizon_col = f"fwd_ret_{args.horizon}d"

    print(f"=== Market State vs Factor IC Analysis ===")
    print(f"Run: {run_id}")
    print(f"Period: {args.start} → {args.end}, Horizon: {args.horizon}d")
    print()

    # ------------------------------------------------------------------
    # 1. Load index data
    # ------------------------------------------------------------------
    print("Loading index daily data...")
    index_data: Dict[str, pd.DataFrame] = {}
    for label, code in INDEX_CODES.items():
        df = _load_index_daily(code, args.start, args.end)
        if df.empty:
            # Try fast cache load
            df = _load_index_cache_fast(code)
        status = f"{len(df)} rows" if not df.empty else "MISSING"
        index_data[label] = df
        print(f"  {label} ({code}): {status}")
        if df.empty:
            print(f"    WARNING: {label} not available, dependent metrics will be NaN")

    csi300 = index_data.get("csi300", pd.DataFrame())

    # ------------------------------------------------------------------
    # 2. Compute index-derived spreads
    # ------------------------------------------------------------------
    print("\nComputing index spreads...")

    size_spread = pd.DataFrame()
    if not csi300.empty and not index_data.get("csi500", pd.DataFrame()).empty:
        size_spread = _compute_index_spread(
            index_data["csi500"], csi300, window=20, label="size_spread"
        )
        print(f"  size_spread_20d: {len(size_spread)} dates")
    else:
        print("  size_spread_20d: SKIPPED (missing CSI 300 or CSI 500)")

    gv_spread = pd.DataFrame()
    if (not index_data.get("csi300_growth", pd.DataFrame()).empty
            and not index_data.get("csi300_value", pd.DataFrame()).empty):
        gv_spread = _compute_index_spread(
            index_data["csi300_growth"], index_data["csi300_value"],
            window=20, label="gv_spread"
        )
        print(f"  gv_spread_20d: {len(gv_spread)} dates")
    else:
        print("  gv_spread_20d: SKIPPED (missing Growth or Value index data)")

    # ------------------------------------------------------------------
    # 3. Build regime features
    # ------------------------------------------------------------------
    print("\nBuilding market regime features...")

    # Load stock prices for breadth (reuse fwd returns for prices)
    fwd_raw = _load_fwd_returns()
    if not fwd_raw.empty:
        fwd_raw["adj_close"] = fwd_raw.get("adj_close", np.nan)
        prices_for_breadth = fwd_raw[["ts_code", "trade_date", "adj_close"]].dropna(subset=["adj_close"])
        if prices_for_breadth.empty:
            prices_for_breadth = None
    else:
        prices_for_breadth = None

    # Use all index dates as signal dates
    if not csi300.empty:
        all_signal_dates = np.array(sorted(csi300["trade_date"].unique()))
        all_signal_dates = all_signal_dates[
            (all_signal_dates >= start_int) & (all_signal_dates <= end_int)
        ]
    else:
        # Fallback: generate all dates from factor data
        all_signal_dates = np.array(sorted(
            fwd_raw[fwd_raw["trade_date"].between(start_int, end_int)]["trade_date"].unique()
        )) if not fwd_raw.empty else np.array([])

    print(f"  Signal dates: {len(all_signal_dates)}")

    regime_features = _build_regime_features(csi300, prices_for_breadth, all_signal_dates)
    if regime_features.empty:
        print("  WARNING: regime features empty, using simplified fallback")
        regime_features = _build_simplified_features(csi300, all_signal_dates)

    print(f"  Regime features: {len(regime_features)} dates")
    if not regime_features.empty:
        print(f"  Columns: {regime_features.columns.tolist()}")
        for col in ["trend_strength", "volatility_state", "breadth_score", "turnover_state"]:
            if col in regime_features.columns:
                vals = regime_features[col].dropna()
                print(f"    {col}: mean={vals.mean():.4f}, std={vals.std():.4f}, "
                      f"range=[{vals.min():.4f}, {vals.max():.4f}]")

    # ------------------------------------------------------------------
    # 4. Load factors and compute ICs
    # ------------------------------------------------------------------
    print("\nLoading factors and computing ICs...")
    factor_ics: Dict[str, pd.DataFrame] = {}

    for fn in TEST_FACTORS:
        fdf = _load_factor_cache(fn)
        if fdf.empty:
            print(f"  {fn}: NO DATA")
            continue
        fdf = fdf[(fdf["trade_date"] >= start_int) & (fdf["trade_date"] <= end_int)]
        if fdf.empty:
            print(f"  {fn}: EMPTY after date filter")
            continue

        fwd_f = fwd_raw[(fwd_raw["trade_date"] >= start_int) & (fwd_raw["trade_date"] <= end_int)]

        ic_series = _compute_factor_ic_series(fdf, fwd_f, horizon_col)
        if ic_series.empty:
            print(f"  {fn}: NO IC DATA")
            continue

        factor_ics[fn] = ic_series
        print(f"  {fn}: {len(ic_series)} IC dates, mean={ic_series['ic'].mean():.4f}, "
              f"std={ic_series['ic'].std():.4f}")

    if not factor_ics:
        print("ERROR: No factor IC data available!")
        return 1

    # ------------------------------------------------------------------
    # 5. Factor coverage audit
    # ------------------------------------------------------------------
    print("\nComputing factor coverage audit...")
    factor_coverage: Dict[str, Dict[str, Any]] = {}
    coverage_blocked_factors: set = set()

    from scripts.evaluate_factor_style_signals import (
        _compute_coverage, _evaluate_coverage,
    )

    for fn in TEST_FACTORS:
        fdf = _load_factor_cache(fn)
        if fdf.empty:
            factor_coverage[fn] = {"coverage_status": "NO_DATA", "coverage_blocked": True}
            coverage_blocked_factors.add(fn)
            print(f"  {fn}: NO DATA")
            continue
        fdf = fdf[(fdf["trade_date"] >= start_int) & (fdf["trade_date"] <= end_int)]
        if fdf.empty:
            factor_coverage[fn] = {"coverage_status": "NO_DATA", "coverage_blocked": True}
            coverage_blocked_factors.add(fn)
            print(f"  {fn}: EMPTY after date filter")
            continue

        fwd_f = fwd_raw[(fwd_raw["trade_date"] >= start_int) & (fwd_raw["trade_date"] <= end_int)]
        cov_df = _compute_coverage(fdf, fwd_f)
        cov_eval = _evaluate_coverage(cov_df)
        factor_coverage[fn] = cov_eval
        if cov_eval["coverage_blocked"]:
            coverage_blocked_factors.add(fn)
        print(f"  {fn}: median_coverage={cov_eval['median_coverage_pct']:.1%}, "
              f"min_yearly={cov_eval['min_yearly_coverage_pct']:.1%}, "
              f"blocked={cov_eval['coverage_blocked']}")

    print(f"\n  Coverage blocked factors: {coverage_blocked_factors if coverage_blocked_factors else 'none'}")

    # ------------------------------------------------------------------
    # 6. Build aligned panel
    # ------------------------------------------------------------------
    print("\nBuilding aligned panel...")

    # Start with regime features
    panel = regime_features.rename(columns={"trade_date": "date"}).copy()

    # Merge size spread
    if not size_spread.empty:
        panel = panel.merge(
            size_spread.rename(columns={"trade_date": "date"}),
            on="date", how="left"
        )
    else:
        panel["size_spread_20d"] = np.nan

    # Merge gv spread
    if not gv_spread.empty:
        panel = panel.merge(
            gv_spread.rename(columns={"trade_date": "date"}),
            on="date", how="left"
        )
    else:
        panel["gv_spread_20d"] = np.nan

    # Merge factor ICs
    for fn, ic_df in factor_ics.items():
        ic_renamed = ic_df.rename(columns={"trade_date": "date", "ic": f"{fn}_ic"})
        panel = panel.merge(ic_renamed, on="date", how="left")

    # Rename date back
    panel = panel.rename(columns={"date": "trade_date"})

    n_with_all = panel.dropna().shape[0]
    print(f"  Panel: {len(panel)} rows, {n_with_all} complete across all columns")
    print(f"  Date range: {int(panel['trade_date'].min())} → {int(panel['trade_date'].max())}")

    # ------------------------------------------------------------------
    # 6. Conditional analysis
    # ------------------------------------------------------------------
    print("\n=== Conditional IC Analysis ===")

    state_columns = [
        "trend_strength",
        "volatility_state",
        "breadth_score",
        "turnover_state",
        "size_spread_20d",
        "gv_spread_20d",
    ]

    all_results: List[Dict[str, Any]] = []
    significant_findings: List[Dict[str, Any]] = []

    for state_col in state_columns:
        if state_col not in panel.columns:
            continue

        state_valid = panel[state_col].notna().sum()
        if state_valid < MIN_OBS_PER_QUARTILE * 4:
            print(f"\n  {state_col}: insufficient data ({state_valid} obs)")
            continue

        for fn in TEST_FACTORS:
            ic_col = f"{fn}_ic"
            if ic_col not in panel.columns:
                continue

            result = _conditional_ic_analysis(panel, state_col, fn)
            all_results.append(result)

            if result.get("error"):
                continue

            spread = result["top_vs_bottom_spread"]
            p = result["p_value"]
            sig_marker = " **" if result.get("is_significant") else ""
            direction = result["direction"]

            if result.get("is_significant"):
                significant_findings.append(result)

            print(f"\n  {state_col} × {fn}:")
            print(f"    spread(Q4-Q1)={spread:.4f}, t={result['t_statistic']:.2f}, "
                  f"p={p:.4f}, dir={direction}{sig_marker}")
            for qr in result.get("per_quantile", []):
                print(f"    Q{qr['quantile']}: n={qr['n']}, mean_ic={qr['mean_ic']:.4f}, "
                      f"icir={qr['icir']:.2f}, hit={qr['hit_rate']:.1%}, "
                      f"state=[{qr['state_min']:.3f}, {qr['state_max']:.3f}]")

    # ------------------------------------------------------------------
    # 8. FDR correction and tiered classification
    # ------------------------------------------------------------------
    print(f"\nApplying FDR correction (Benjamini-Hochberg, q<0.10)...")
    all_results = _apply_fdr_correction(all_results)

    # Count FDR-significant
    n_fdr = sum(1 for r in all_results if r.get("significant_fdr"))
    n_effect = sum(1 for r in all_results if r.get("passes_effect_size"))
    print(f"  FDR-significant: {n_fdr}, passes effect size: {n_effect}")

    tiers = _classify_findings_into_tiers(all_results, coverage_blocked_factors)

    print(f"\n{'='*60}")
    print(f"Tiered Summary")
    print(f"{'='*60}")
    print(f"  Tier 1 — Raw significant (p<0.05):        {len(tiers['raw_significant'])}")
    print(f"  Tier 2 — FDR robust (q<0.10, effect>0.02): {len(tiers['fdr_robust'])}")
    print(f"  Tier 3 — Rule candidates:                  {len(tiers['rule_candidates'])}")

    if tiers["rule_candidates"]:
        print(f"\n  ✅ Rule candidates (ready for allocator development):")
        for rc in tiers["rule_candidates"]:
            print(f"    {rc['state_col']} → {rc['factor']}: "
                  f"spread={rc['spread']:.4f}, dir={rc['direction']}, "
                  f"q={rc['q_value']:.4f}")
    else:
        print(f"\n  No rule candidates found after FDR, effect size, and coverage filters.")
        print(f"  This is an acceptable outcome — do not lower statistical standards.")

    if tiers["fdr_robust"]:
        fdr_blocked = [f for f in tiers["fdr_robust"] if f["coverage_blocked"]]
        if fdr_blocked:
            print(f"\n  ⚠️ FDR-robust findings blocked by coverage:")
            for fb in fdr_blocked:
                print(f"    {fb['state_col']} → {fb['factor']}: "
                      f"DATA_COVERAGE_BLOCKED (observation only)")

    # ------------------------------------------------------------------
    # 9. Outputs
    # ------------------------------------------------------------------
    print(f"\nWriting outputs to {out_dir}...")

    # 9a. Full results JSON (with FDR fields)
    results_json = {
        "run_id": run_id,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "parameters": {
            "start": args.start, "end": args.end, "horizon_days": args.horizon,
        },
        "n_signal_dates": len(all_signal_dates),
        "n_panel_rows": len(panel),
        "n_complete_rows": n_with_all,
        "state_columns_tested": state_columns,
        "factors_tested": TEST_FACTORS,
        "factor_coverage": {fn: {
            "median_coverage_pct": factor_coverage[fn].get("median_coverage_pct"),
            "coverage_blocked": factor_coverage[fn].get("coverage_blocked"),
            "coverage_status": factor_coverage[fn].get("coverage_status"),
        } for fn in TEST_FACTORS},
        "coverage_blocked_factors": sorted(coverage_blocked_factors),
        "fdr_parameters": {
            "method": "Benjamini-Hochberg",
            "raw_p_threshold": 0.05,
            "fdr_q_threshold": 0.10,
            "min_abs_ic_spread": 0.02,
        },
        "tier_summary": {
            "raw_significant": len(tiers["raw_significant"]),
            "fdr_robust": len(tiers["fdr_robust"]),
            "rule_candidates": len(tiers["rule_candidates"]),
        },
        "tiers": tiers,
        "all_results": [
            {k: v for k, v in r.items() if k != "per_quantile"}
            for r in all_results
        ],
    }
    with open(out_dir / "market_state_vs_factor_ic_results.json", "w", encoding="utf-8") as f:
        json.dump(results_json, f, indent=2, ensure_ascii=False, default=str)
    print("  ✓ market_state_vs_factor_ic_results.json")

    # 9b. Significance-adjusted CSV
    sig_rows = []
    for r in all_results:
        if r.get("error"):
            continue
        factor = r.get("factor", "?")
        sig_rows.append({
            "state_col": r["state_col"],
            "factor": factor,
            "n_total": r.get("n_total", 0),
            "top_vs_bottom_spread": r.get("top_vs_bottom_spread"),
            "p_value": r.get("p_value"),
            "q_value": r.get("q_value"),
            "significant_raw": r.get("significant_raw", False),
            "significant_fdr": r.get("significant_fdr", False),
            "passes_effect_size": r.get("passes_effect_size", False),
            "direction": r.get("direction"),
            "coverage_blocked": factor in coverage_blocked_factors,
            "tier": (
                "rule_candidate" if any(
                    rc["state_col"] == r["state_col"] and rc["factor"] == factor
                    for rc in tiers["rule_candidates"]
                ) else "fdr_robust" if r.get("significant_fdr") and r.get("passes_effect_size")
                else "raw_significant" if r.get("significant_raw")
                else "not_significant"
            ),
        })
    pd.DataFrame(sig_rows).to_csv(
        out_dir / "market_state_significance_adjusted.csv", index=False, encoding="utf-8-sig"
    )
    print("  ✓ market_state_significance_adjusted.csv")

    # 9c. Detailed conditional IC table (CSV)
    detail_rows = []
    for result in all_results:
        for qr in result.get("per_quantile", []):
            detail_rows.append({
                "state_col": result["state_col"],
                "factor": result["factor"],
                "quantile": qr["quantile"],
                "n": qr["n"],
                "mean_ic": qr["mean_ic"],
                "icir": qr["icir"],
                "hit_rate": qr["hit_rate"],
                "state_min": qr["state_min"],
                "state_max": qr["state_max"],
                "top_vs_bottom_spread": result.get("top_vs_bottom_spread"),
                "p_value": result.get("p_value"),
                "q_value": result.get("q_value"),
                "significant_fdr": result.get("significant_fdr"),
                "direction": result.get("direction"),
            })
    pd.DataFrame(detail_rows).to_csv(
        out_dir / "market_state_conditional_ic.csv", index=False, encoding="utf-8-sig"
    )
    print("  ✓ market_state_conditional_ic.csv")

    # 9d. Rule candidates YAML
    rule_candidates_yaml = {
        "schema": "market_state_rule_candidates.v1",
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "parameters": {
            "start": args.start, "end": args.end, "horizon_days": args.horizon,
        },
        "fdr": {
            "method": "Benjamini-Hochberg",
            "q_threshold": 0.10,
        },
        "effect_size_threshold": 0.02,
        "coverage_required": True,
        "n_rule_candidates": len(tiers["rule_candidates"]),
        "rule_candidates": tiers["rule_candidates"],
        "fdr_robust_but_blocked": [
            f for f in tiers["fdr_robust"] if f["coverage_blocked"]
        ],
        "note": (
            "Only rule_candidates pass all gates: FDR q<0.10, "
            "|spread|>=0.02, coverage OK, n>=40. "
            "These are suitable for building market-state-driven allocation rules. "
            "fdr_robust_but_blocked items passed statistical gates but are blocked "
            "by DATA_COVERAGE_BLOCKED — they need expanded data before use."
        ),
    }
    with open(out_dir / "market_state_rule_candidates.yaml", "w", encoding="utf-8") as f:
        yaml.dump(rule_candidates_yaml, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    print("  ✓ market_state_rule_candidates.yaml")

    # 9e. Correlation matrix
    corr_cols = [c for c in state_columns if c in panel.columns]
    ic_cols = [f"{fn}_ic" for fn in TEST_FACTORS if f"{fn}_ic" in panel.columns]
    if corr_cols and ic_cols:
        corr_panel = panel[corr_cols + ic_cols].dropna()
        if len(corr_panel) > 30:
            corr_matrix = corr_panel.corr()
            corr_matrix.to_csv(
                out_dir / "state_vs_ic_correlation_matrix.csv", encoding="utf-8-sig"
            )
            print("  ✓ state_vs_ic_correlation_matrix.csv")

    # 9f. Three-tier summary report (Markdown)
    _write_tiered_report(
        out_dir, tiers, all_results, factor_coverage,
        coverage_blocked_factors, args, len(all_signal_dates), n_with_all,
    )
    print("  ✓ market_state_analysis_summary.md")

    print(f"\nDone. Output: {out_dir}")
    return 0


def _write_tiered_report(
    out_dir: Path,
    tiers: Dict[str, List[Dict[str, Any]]],
    all_results: List[Dict[str, Any]],
    factor_coverage: Dict[str, Dict[str, Any]],
    coverage_blocked_factors: set,
    args,
    n_signal_dates: int,
    n_with_all: int,
):
    """Write the three-tier analysis summary report."""
    lines = [
        "# Market State vs Factor IC — Three-Tier Analysis",
        f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"\nParameters: {args.start} → {args.end}, horizon={args.horizon}d",
        f"\n## Data Summary",
        f"\n- Signal dates: {n_signal_dates}",
        f"- Complete panel rows: {n_with_all}",
        f"- Factors tested: {len(TEST_FACTORS)}",
        f"- State dimensions: 6",
        f"\n## Factor Coverage Status",
        f"\n| Factor | Median Coverage | Status |",
        f"\n|--------|----------------|--------|",
    ]
    for fn in TEST_FACTORS:
        cov = factor_coverage.get(fn, {})
        med = cov.get("median_coverage_pct", 0)
        status = cov.get("coverage_status", "?")
        lines.append(f"| {fn} | {med:.1%} | **{status}** |")
    if coverage_blocked_factors:
        lines.append(f"\n⚠️ **Coverage-blocked factors**: {', '.join(sorted(coverage_blocked_factors))}")
        lines.append(f"\nThese factors are included in exploratory analysis but excluded from rule_candidates.")

    # ---- Tier 1: Raw Significant ----
    lines.append(f"\n## Tier 1 — Raw Significant (p < 0.05, uncorrected)")
    lines.append(f"\n{len(tiers['raw_significant'])} findings. For reference only — ")
    lines.append(f"NOT corrected for multiple testing.")
    if tiers["raw_significant"]:
        lines.append(f"\n| State | Factor | Spread | p-value | Coverage |")
        lines.append(f"|-------|--------|--------|---------|----------|")
        for f in tiers["raw_significant"]:
            blk = "BLOCKED" if f["coverage_blocked"] else "OK"
            lines.append(
                f"| {f['state_col']} | {f['factor']} | "
                f"{f['spread']:.4f} | {f['p_value']:.4f} | {blk} |"
            )
    else:
        lines.append(f"\nNo findings at this tier.")

    # ---- Tier 2: FDR Robust ----
    lines.append(f"\n## Tier 2 — FDR-Adjusted Robust (q < 0.10, |spread| ≥ 0.02)")
    lines.append(f"\n{len(tiers['fdr_robust'])} findings. Passed Benjamini-Hochberg FDR ")
    lines.append(f"correction and minimum effect size filter.")
    if tiers["fdr_robust"]:
        lines.append(f"\n| State | Factor | Spread | q-value | Direction | Coverage |")
        lines.append(f"|-------|--------|--------|---------|-----------|----------|")
        for f in tiers["fdr_robust"]:
            blk = "⚠️ BLOCKED" if f["coverage_blocked"] else "OK"
            lines.append(
                f"| {f['state_col']} | {f['factor']} | "
                f"{f['spread']:.4f} | {f['q_value']:.4f} | "
                f"{f['direction']} | {blk} |"
            )
    else:
        lines.append(f"\nNo findings at this tier.")
        lines.append(f"\nThis means either: (a) the raw findings were false positives ")
        lines.append(f"eliminated by FDR correction, or (b) the effect sizes were too ")
        lines.append(f"small to be economically meaningful.")
        lines.append(f"\n**Do not lower the statistical thresholds to produce findings.**")

    # ---- Tier 3: Rule Candidates ----
    lines.append(f"\n## Tier 3 — Rule Candidates (Production-Ready)")
    lines.append(f"\n{len(tiers['rule_candidates'])} candidates. Passed ALL gates:")
    lines.append(f"- FDR q < 0.10")
    lines.append(f"- |IC spread| ≥ 0.02")
    lines.append(f"- Factor coverage OK (not DATA_COVERAGE_BLOCKED)")
    lines.append(f"- Sufficient sample size")
    lines.append(f"- Interpretable direction")

    if tiers["rule_candidates"]:
        lines.append(f"\nThese state→factor relationships are validated for building ")
        lines.append(f"market-state-driven allocation rules.")
        lines.append(f"\n| State | Factor | Spread | q-value | Direction |")
        lines.append(f"|-------|--------|--------|---------|-----------|")
        for rc in tiers["rule_candidates"]:
            lines.append(
                f"| {rc['state_col']} | {rc['factor']} | "
                f"{rc['spread']:.4f} | {rc['q_value']:.4f} | "
                f"**{rc['direction']}** |"
            )
        lines.append(f"\n### Rule Interpretations")
        for rc in tiers["rule_candidates"]:
            lines.append(f"\n**{rc['state_col']} → {rc['factor']}**:")
            lines.append(f"  {rc.get('interpretation', 'No interpretation available.')}")
    else:
        lines.append(f"\n**No rule candidates found.**")
        lines.append(f"\nThis means none of the market state dimensions tested can ")
        lines.append(f"reliably predict factor IC differences after accounting for ")
        lines.append(f"multiple testing, effect size, and data coverage constraints.")
        lines.append(f"\n### Recommended Next Steps")
        lines.append(f"\n1. Accept this negative result — do not force rules from noise")
        lines.append(f"\n2. Try alternative approaches:")
        lines.append(f"   - Non-linear state splits (e.g., decision trees)")
        lines.append(f"   - State variable interactions (e.g., low vol + mild trend)")
        lines.append(f"   - Different IC horizons (5d, 10d, 60d)")
        lines.append(f"   - Regime probability thresholds instead of raw state values")
        lines.append(f"\n3. Consider that A-share factor IC may be inherently difficult ")
        lines.append(f"   to predict from simple market states at the 20-day horizon.")
        lines.append(f"\n4. If no approach yields robust rule candidates after reasonable ")
        lines.append(f"   exploration, the correct conclusion is that market-state-driven ")
        lines.append(f"   style rotation is not supported by the current data.")

    (out_dir / "market_state_analysis_summary.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )


if __name__ == "__main__":
    raise SystemExit(main())

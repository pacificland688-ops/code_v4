"""
Phase 4: Panic Basket Gate — Sleeve Integration Validation (v2 — audited)
==========================================================================
Two-layer validation:
  A. Event-Day Forward Return Validation (labels, no daily PnL)
  B. Real Path Sleeve Simulation (overlapping 20d tranche holdings)

Gate signals are walk-forward frozen from Phase 2 (rule) and Phase 3 (ML).
Thresholds come from TRAINING period, not test set.

Primary strategy (frozen): gate_ml_logreg

Outputs (-> outputs/analysis/panic_reversal_gate/daily_basket_v1/):
  - panic_sleeve_gate_event_forward_compare.csv
  - panic_sleeve_gate_path_daily_returns.csv
  - panic_sleeve_gate_path_compare.csv
  - panic_sleeve_gate_path_yearly_attribution.csv
  - panic_sleeve_gate_threshold_audit.csv
  - panic_sleeve_gate_drawdown_report.md
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from panic_gate_shared import (  # noqa: E402
    COST_BPS, DEFAULT_WINDOWS, PRIMARY_GATE_STRATEGY, GATE_STRATEGY_WHITELIST,
    PRIMARY_ML_THRESHOLD, HOLDING_DAYS, MAX_TRANCHES,
    build_trading_calendar, load_market_calendar,
    get_windows, split_train_test, validate_leakage_audit,
    trading_day_offset, first_trading_day_of_year, build_exec_date_map,
)

DEFAULT_INPUT_DIR = ROOT / "outputs" / "analysis" / "panic_reversal_gate" / "daily_basket_v1"
DEFAULT_OUT_DIR = DEFAULT_INPUT_DIR

# Feature columns for ML gate
FEATURE_COLS = [
    "event_count", "event_count_hist_pct_60d",
    "up_pct", "up_5d_pct", "down_pct", "big_down_pct",
    "cs_ret_std", "cs_ret_spread",
    "med_turnover", "turnover_chg_5d", "amount_chg_5d",
]
INDEX_FEATURES = [
    "idx_csi300_sh_ret_5d", "idx_csi300_sh_ret_20d",
    "idx_csi300_sh_drawdown_20d", "idx_csi300_sh_dist_to_20d_low",
    "idx_csi300_sh_vol_5d_over_20d_x",
    "idx_930917_csi_ret_5d", "idx_930917_csi_drawdown_20d",
    "idx_930918_csi_ret_20d", "idx_930918_csi_drawdown_20d",
]
ALL_FEATURES = FEATURE_COLS + INDEX_FEATURES

HOLDING_DAYS = 20
MAX_TRANCHES = 20


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Phase 4: Sleeve validation (v2 audited)")
    p.add_argument("--input-dir", default=str(DEFAULT_INPUT_DIR))
    p.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    return p.parse_args()


# ═══════════════════════════════════════════════════════════════════════
# Scoring functions (replicating Phase 2 for walk-forward)
# ═══════════════════════════════════════════════════════════════════════
def _rolling_percentile(series: pd.Series, window: int = 60) -> pd.Series:
    result = pd.Series(np.nan, index=series.index)
    arr = series.values
    for i in range(len(arr)):
        start = max(0, i - window)
        if i - start < 20:
            continue
        past = arr[start:i]
        result.iloc[i] = (past < arr[i]).mean()
    return result


def score_panic_intensity(df: pd.DataFrame) -> pd.Series:
    if "event_count" in df.columns:
        return _rolling_percentile(df["event_count"], 60).fillna(0.5).clip(0, 1)
    return pd.Series(0.5, index=df.index)


def score_market_stress_inverted(df: pd.DataFrame) -> pd.Series:
    components = []
    for c in df.columns:
        if c.startswith("idx_") and "drawdown_20d" in c:
            components.append((df[c] + 0.30).clip(0, 0.30) / 0.30)
            break
    for c in df.columns:
        if "vol_5d_over_20d" in c and c.startswith("idx_"):
            components.append((1.5 - df[c]).clip(0, 1.5) / 1.5)
            break
    if "big_down_pct" in df.columns:
        components.append((0.20 - df["big_down_pct"]).clip(0, 0.20) / 0.20)
    if components:
        return pd.concat(components, axis=1).mean(axis=1)
    return pd.Series(0.5, index=df.index)


def score_breadth_repair(df: pd.DataFrame) -> pd.Series:
    components = []
    if "up_5d_pct" in df.columns:
        components.append((df["up_5d_pct"] - 0.40).clip(0, 0.15) / 0.15)
    if "up_pct" in df.columns:
        components.append((df["up_pct"] - 0.40).clip(0, 0.20) / 0.20)
    if components:
        return pd.concat(components, axis=1).mean(axis=1)
    return pd.Series(0.5, index=df.index)


def score_liquidity_support(df: pd.DataFrame) -> pd.Series:
    components = []
    if "turnover_chg_5d" in df.columns:
        components.append((df["turnover_chg_5d"] + 0.05).clip(0, 0.10) / 0.10)
    if "amount_chg_5d" in df.columns:
        components.append((df["amount_chg_5d"] + 0.05).clip(0, 0.10) / 0.10)
    if components:
        return pd.concat(components, axis=1).mean(axis=1)
    return pd.Series(0.5, index=df.index)


SCORE_FUNCS = {
    "panic_intensity": score_panic_intensity,
    "market_stress": score_market_stress_inverted,
    "breadth": score_breadth_repair,
    "liquidity": score_liquidity_support,
}


def build_logreg_model() -> Pipeline:
    return Pipeline(steps=[
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler", StandardScaler()),
        ("model", LogisticRegression(
            class_weight="balanced", max_iter=2000, random_state=42)),
    ])


# ═══════════════════════════════════════════════════════════════════════
# Walk-forward gate generation with train-frozen thresholds
# ═══════════════════════════════════════════════════════════════════════
def generate_walkforward_gates(daily_basket: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    """Generate walk-forward gate signals. All thresholds frozen from training."""
    df = daily_basket.copy()
    df["year"] = df["trade_date"] // 10000

    market_cal = load_market_calendar(ROOT, int(df["trade_date"].min()), int(df["trade_date"].max()))
    if market_cal is None:
        market_cal = build_trading_calendar(
            pd.DataFrame({"trade_date": sorted(df["trade_date"].unique())}))
    calendar_source = "prices_adj_full_market" if market_cal is not None else "basket_dates"
    calendar_is_full = market_cal is not None and len(market_cal) > len(df) * 2

    windows = get_windows()
    ret_col = "basket_mean_fwd_ret_20d"
    net_ret_col = "basket_net_fwd_ret_20d"

    if net_ret_col in df.columns:
        df["gate_label"] = (df[net_ret_col] > 0).astype(int)
    else:
        df["gate_label"] = ((df[ret_col] - COST_BPS) > 0).astype(int)

    all_gates = []
    all_thresholds = []
    all_audits = []

    for window in windows:
        train, test, audit = split_train_test(
            df, window, market_cal,
            calendar_source=calendar_source,
            calendar_is_full_market=calendar_is_full,
        )
        all_audits.append(audit.to_dict())

        if len(train) < 30 or len(test) < 10:
            continue

        window_name = window.name

        # Compute rule scores on train and test
        for name, fn in SCORE_FUNCS.items():
            test[f"score_{name}"] = fn(test).values
            train[f"score_{name}"] = fn(train).values

        # Composite score (equal weight)
        score_cols = [f"score_{n}" for n in SCORE_FUNCS]
        test["score_composite"] = test[score_cols].mean(axis=1)
        train["score_composite"] = train[score_cols].mean(axis=1)

        # ── Rule gates: threshold from TRAIN, apply to test ──────────
        for dim in list(SCORE_FUNCS.keys()) + ["composite"]:
            sc = f"score_{dim}"
            if sc not in train.columns:
                continue
            train_scores = train[sc].dropna()
            if len(train_scores) < 20:
                continue

            threshold = float(train_scores.quantile(0.80))  # top 20% from TRAIN
            gate_col = f"gate_rule_{dim}"
            test[gate_col] = np.where(test[sc] >= threshold, "ALLOW", "REDUCE")

            all_thresholds.append({
                "window": window_name,
                "strategy": f"gate_rule_{dim}",
                "score_column": sc,
                "top_pct": 0.20,
                "threshold_source": "train_quantile",
                "threshold_value": round(threshold, 6),
                "n_train_scores": len(train_scores),
                "n_test_scores": len(test[sc].dropna()),
            })

        # ── ML gate: train on train, predict on test ──────────────────
        available_features = [c for c in ALL_FEATURES if c in train.columns]
        X_train = train[available_features].copy()
        y_train = train["gate_label"].values
        X_test = test[available_features].copy()

        if y_train.sum() >= 5 and (len(y_train) - y_train.sum()) >= 5:
            try:
                model = build_logreg_model()
                model.fit(X_train, y_train)
                test["gate_ml_logreg_score"] = model.predict_proba(X_test)[:, 1]
                test["gate_ml_logreg"] = np.where(
                    test["gate_ml_logreg_score"] >= PRIMARY_ML_THRESHOLD,
                    "ALLOW", "REDUCE")
                all_thresholds.append({
                    "window": window_name,
                    "strategy": "gate_ml_logreg",
                    "score_column": "pred_score",
                    "top_pct": float("nan"),
                    "threshold_source": "frozen_probability",
                    "threshold_value": PRIMARY_ML_THRESHOLD,
                    "n_train_scores": len(y_train),
                    "n_test_scores": len(X_test),
                })
            except Exception:
                test["gate_ml_logreg"] = "REDUCE"
        else:
            test["gate_ml_logreg"] = "REDUCE"

        # Keep relevant columns
        out_cols = ["trade_date", "year", ret_col, "basket_a_rate_20d",
                     "basket_net_fwd_ret_20d", "gate_label", "event_count"]
        out_cols += [f"score_{n}" for n in SCORE_FUNCS] + ["score_composite"]
        out_cols += [c for c in test.columns if c in GATE_STRATEGY_WHITELIST]
        if "gate_ml_logreg_score" in test.columns:
            out_cols.append("gate_ml_logreg_score")
        out_cols.append("window")
        all_gates.append(test[[c for c in out_cols if c in test.columns]])

    return (pd.concat(all_gates, ignore_index=True) if all_gates else pd.DataFrame(),
            all_thresholds,
            all_audits)


# ═══════════════════════════════════════════════════════════════════════
# Layer A: Event-Day Forward Return Validation
# ═══════════════════════════════════════════════════════════════════════
def event_forward_validation(gates: pd.DataFrame) -> pd.DataFrame:
    """Validate gate using event-day forward returns (NOT daily PnL).

    Metrics: net_spread_lift, A-rate lift, win-rate lift.
    These are LABEL-LEVEL comparisons, not portfolio returns.
    """
    ret_col = "basket_mean_fwd_ret_20d"
    results = []

    # Raw baseline
    raw_ret = float(gates[ret_col].mean())
    raw_a = float(gates["basket_a_rate_20d"].mean())
    raw_wr = float((gates[ret_col] > 0).mean())

    results.append({
        "strategy": "raw_events",
        "validation_type": "event_forward",
        "n_days": len(gates),
        "n_participate": len(gates),
        "coverage_pct": 100.0,
        "mean_fwd_ret": round(raw_ret, 6),
        "mean_net_fwd_ret": round(raw_ret - COST_BPS, 6),
        "a_rate": round(raw_a, 6),
        "win_rate": round(raw_wr, 6),
        "net_spread_lift": 0.0,
        "a_rate_lift": 0.0,
    })

    for gcol in GATE_STRATEGY_WHITELIST:
        if gcol not in gates.columns:
            continue
        mask = gates[gcol] == "ALLOW"
        n_part = int(mask.sum())
        if n_part == 0:
            continue

        mr = float(gates.loc[mask, ret_col].mean())
        ar = float(gates.loc[mask, "basket_a_rate_20d"].mean())
        wr = float((gates.loc[mask, ret_col] > 0).mean())

        results.append({
            "strategy": gcol,
            "validation_type": "event_forward",
            "n_days": len(gates),
            "n_participate": n_part,
            "coverage_pct": round(n_part / len(gates) * 100, 1),
            "mean_fwd_ret": round(mr, 6),
            "mean_net_fwd_ret": round(mr - COST_BPS, 6),
            "a_rate": round(ar, 6),
            "win_rate": round(wr, 6),
            "net_spread_lift": round(mr - raw_ret, 6),
            "a_rate_lift": round(ar - raw_a, 6),
        })

    return pd.DataFrame(results)


# ═══════════════════════════════════════════════════════════════════════
# Layer B: Real Path Sleeve Simulation
# ═══════════════════════════════════════════════════════════════════════
def _legacy_simulate_real_path_sleeve_unused(
    prices: pd.DataFrame,
    gates: pd.DataFrame,
    market_calendar: np.ndarray,
    event_stock_samples: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Real path sleeve simulation using actual constituent stock returns.

    Each ALLOW basket day creates a tranche of the panic event stocks on that day.
    Tranche daily return = mean(stock daily returns of constituents).
    Portfolio daily return = weighted average of active tranches.
    Costs deducted at entry and exit only (not daily).

    Returns (daily_returns_df, tranche_audit_df).
    """
    if gates.empty or prices.empty or event_stock_samples.empty:
        return pd.DataFrame(), pd.DataFrame()

    # Build daily stock return lookup
    prices_sorted = prices.sort_values(["ts_code", "trade_date"])
    prices_sorted["daily_ret"] = prices_sorted.groupby("ts_code")["adj_close"].pct_change()
    prices_sorted = prices_sorted.dropna(subset=["daily_ret"])

    # Build fast lookup: dict[(ts_code, trade_date)] -> daily_ret
    ret_lookup = {}
    for _, row in prices_sorted.iterrows():
        ret_lookup[(str(row["ts_code"]), int(row["trade_date"]))] = float(row["daily_ret"])

    exec_map = build_exec_date_map(market_calendar)
    all_dates = sorted(market_calendar)

    daily_pnl_records = []
    all_tranche_audit = []

    for gcol in GATE_STRATEGY_WHITELIST:
        if gcol not in gates.columns:
            continue

        allow_days = gates[gates[gcol] == "ALLOW"].copy()
        if allow_days.empty:
            continue

        # Active tranches: list of {exit_date, stock_weights: {ts_code: weight}}
        tranches: list[dict] = []

        for td in all_dates:
            # ── Open new tranche ───────────────────────────────────────
            if td in allow_days["trade_date"].values:
                exec_date = exec_map.get(int(td))
                if exec_date is not None:
                    exit_date = trading_day_offset(market_calendar, exec_date, HOLDING_DAYS)
                    if exit_date is not None:
                        # Get constituent stocks for this signal date
                        constituents = event_stock_samples[
                            (event_stock_samples["trade_date"] == td)
                            & (event_stock_samples["value"] > 0)
                        ]
                        if len(constituents) > 0:
                            stocks = constituents["ts_code"].tolist()
                            n_stocks = len(stocks)
                            stock_wt = 1.0 / n_stocks if n_stocks > 0 else 0.0
                            # Determine tranche weight: fixed capital allocation
                            tranche_wt = 1.0 / MAX_TRANCHES
                            # Entry cost
                            entry_cost = COST_BPS * tranche_wt
                            # Store tranche
                            tranche_info = {
                                "signal_date": int(td),
                                "exec_date": int(exec_date),
                                "exit_date": int(exit_date),
                                "stocks": stocks,
                                "n_stocks": n_stocks,
                                "stock_weight": stock_wt,
                                "tranche_weight": tranche_wt,
                                "entry_cost": entry_cost,
                                "exit_cost": COST_BPS * tranche_wt,
                                "label_fwd_ret": float(
                                    allow_days[allow_days["trade_date"] == td][
                                        "basket_mean_fwd_ret_20d"].values[0])
                                    if "basket_mean_fwd_ret_20d" in allow_days.columns
                                    else 0.0,
                            }
                            tranches.append(tranche_info)

                            all_tranche_audit.append({
                                "strategy": gcol,
                                "signal_date": int(td),
                                "exec_date": int(exec_date),
                                "exit_date": int(exit_date),
                                "n_stocks": n_stocks,
                                "entry_cost": round(entry_cost, 8),
                                "exit_cost": round(COST_BPS * tranche_wt, 8),
                                "tranche_fwd_ret_20d": tranche_info["label_fwd_ret"],
                                "realized_path_ret": 0.0,  # filled at exit
                                "path_vs_label_diff": 0.0,
                            })

            # ── Close expired tranches ──────────────────────────────────
            for t in tranches:
                if t["exit_date"] == td:
                    # Compute realized path return for this tranche
                    # Sum of daily returns over the holding period
                    path_ret = 0.0
                    holding_dates = [
                        d for d in all_dates
                        if t["exec_date"] <= d <= t["exit_date"]
                    ]
                    # We'll use the stored daily returns — handled below
                    # Mark for cleanup
                    t["_closing"] = True

            # ── Compute daily portfolio return ──────────────────────────
            active = [t for t in tranches
                      if t["exec_date"] <= td <= t["exit_date"]]
            n_active = len(active)

            daily_gross = 0.0
            daily_cost = 0.0
            active_stocks = 0

            if n_active > 0:
                for t in active:
                    tw = t["tranche_weight"]
                    # Mean stock return for this tranche on this day
                    stock_rets = []
                    for s in t["stocks"]:
                        r = ret_lookup.get((s, td), 0.0)
                        stock_rets.append(r)
                        active_stocks += 1
                    tranche_ret = np.mean(stock_rets) if stock_rets else 0.0
                    daily_gross += tw * tranche_ret

                    # Entry cost on exec_date
                    if td == t["exec_date"]:
                        daily_cost += t["entry_cost"]
                    # Exit cost on exit_date
                    if td == t["exit_date"]:
                        daily_cost += t["exit_cost"]

                # Legacy implementation is no longer used by Phase 4.
                daily_gross = np.nan
                daily_gross = np.clip(daily_gross, -0.15, 0.15)
            else:
                daily_gross = 0.0
                daily_cost = 0.0

            daily_net = daily_gross - daily_cost
            gross_exposure = n_active / MAX_TRANCHES

            daily_pnl_records.append({
                "trade_date": int(td),
                "strategy": gcol,
                "daily_gross_return": round(daily_gross, 8),
                "daily_cost": round(daily_cost, 8),
                "daily_net_return": round(daily_net, 8),
                "active_tranches": n_active,
                "active_stocks": active_stocks,
                "gross_exposure": round(gross_exposure, 4),
                "turnover": round(daily_cost / COST_BPS, 6) if daily_cost > 0 else 0.0,
            })

            # Remove closed tranches
            tranches = [t for t in tranches if not t.get("_closing", False)]

    daily_returns = pd.DataFrame(daily_pnl_records)
    tranche_audit = pd.DataFrame(all_tranche_audit)

    return daily_returns, tranche_audit


def simulate_real_path_sleeve(
    prices: pd.DataFrame,
    gates: pd.DataFrame,
    market_calendar: np.ndarray,
    event_stock_samples: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Final-acceptance real path sleeve simulation.

    The portfolio uses fixed capital allocation: each active tranche owns
    1 / MAX_TRANCHES of capital. Daily returns are therefore not rescaled by
    the number of active tranches.
    """
    if gates.empty or prices.empty or event_stock_samples.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    prices_sorted = prices.sort_values(["ts_code", "trade_date"]).copy()
    prices_sorted["ts_code"] = prices_sorted["ts_code"].astype(str)
    prices_sorted["trade_date"] = pd.to_numeric(
        prices_sorted["trade_date"], errors="coerce").astype("int64")
    prices_sorted["adj_close"] = pd.to_numeric(
        prices_sorted["adj_close"], errors="coerce")
    prices_sorted["daily_ret"] = prices_sorted.groupby("ts_code")["adj_close"].pct_change()

    ret_rows = prices_sorted.dropna(subset=["daily_ret"])
    ret_lookup = dict(zip(
        zip(ret_rows["ts_code"], ret_rows["trade_date"]),
        ret_rows["daily_ret"].astype(float),
    ))
    close_rows = prices_sorted.dropna(subset=["adj_close"])
    close_lookup = dict(zip(
        zip(close_rows["ts_code"], close_rows["trade_date"]),
        close_rows["adj_close"].astype(float),
    ))

    events = event_stock_samples.copy()
    events["trade_date"] = pd.to_numeric(events["trade_date"], errors="coerce")
    events = events.dropna(subset=["trade_date"])
    events["trade_date"] = events["trade_date"].astype("int64")
    events["ts_code"] = events["ts_code"].astype(str)

    exec_map = build_exec_date_map(market_calendar)
    all_dates = sorted(int(d) for d in market_calendar)

    daily_pnl_records = []
    all_tranche_audit = []
    all_constituents = []

    for gcol in GATE_STRATEGY_WHITELIST:
        if gcol not in gates.columns:
            continue

        allow_days = gates[gates[gcol] == "ALLOW"].copy()
        if allow_days.empty:
            continue
        allow_days["trade_date"] = pd.to_numeric(
            allow_days["trade_date"], errors="coerce").astype("int64")
        allow_by_date = allow_days.set_index("trade_date", drop=False)
        tranches: list[dict] = []

        for td in all_dates:
            if td in allow_by_date.index:
                gate_row = allow_by_date.loc[td]
                if isinstance(gate_row, pd.DataFrame):
                    gate_row = gate_row.iloc[0]
                exec_date = exec_map.get(int(td))
                exit_date = (
                    trading_day_offset(market_calendar, exec_date, HOLDING_DAYS)
                    if exec_date is not None else None
                )

                if exec_date is not None and exit_date is not None:
                    constituents = events[
                        (events["trade_date"] == td) & (events["value"] > 0)
                    ].copy()
                    if not constituents.empty:
                        stocks = constituents["ts_code"].tolist()
                        n_stocks = len(stocks)
                        stock_wt = 1.0 / n_stocks
                        tranche_wt = 1.0 / MAX_TRANCHES
                        entry_cost = COST_BPS * tranche_wt
                        exit_cost = COST_BPS * tranche_wt
                        label_fwd_ret = (
                            float(gate_row["basket_mean_fwd_ret_20d"])
                            if "basket_mean_fwd_ret_20d" in gate_row.index
                            and pd.notna(gate_row["basket_mean_fwd_ret_20d"])
                            else 0.0
                        )

                        audit_idx = len(all_tranche_audit)
                        tranche_info = {
                            "signal_date": int(td),
                            "exec_date": int(exec_date),
                            "exit_date": int(exit_date),
                            "stocks": stocks,
                            "n_stocks": n_stocks,
                            "stock_weight": stock_wt,
                            "tranche_weight": tranche_wt,
                            "entry_cost": entry_cost,
                            "exit_cost": exit_cost,
                            "label_fwd_ret": label_fwd_ret,
                            "tranche_daily_returns": [],
                            "audit_idx": audit_idx,
                        }
                        tranches.append(tranche_info)

                        all_tranche_audit.append({
                            "strategy": gcol,
                            "signal_date": int(td),
                            "exec_date": int(exec_date),
                            "exit_date": int(exit_date),
                            "n_stocks": n_stocks,
                            "entry_cost": round(entry_cost, 8),
                            "exit_cost": round(exit_cost, 8),
                            "tranche_weight": round(tranche_wt, 8),
                            "tranche_fwd_ret_20d": label_fwd_ret,
                            "realized_path_ret": np.nan,
                            "path_vs_label_diff": np.nan,
                            "realized_path_available": False,
                            "holding_days_observed": 0,
                        })

                        for _, c_row in constituents.iterrows():
                            ts_code = str(c_row["ts_code"])
                            entry_price = close_lookup.get((ts_code, int(exec_date)), np.nan)
                            exit_price = close_lookup.get((ts_code, int(exit_date)), np.nan)
                            stock_path_ret = (
                                float(exit_price / entry_price - 1.0)
                                if pd.notna(entry_price)
                                and pd.notna(exit_price)
                                and entry_price > 0
                                else np.nan
                            )
                            all_constituents.append({
                                "strategy": gcol,
                                "signal_date": int(td),
                                "exec_date": int(exec_date),
                                "exit_date": int(exit_date),
                                "ts_code": ts_code,
                                "n_stocks": n_stocks,
                                "stock_weight_in_tranche": round(stock_wt, 12),
                                "tranche_weight": round(tranche_wt, 8),
                                "portfolio_weight": round(stock_wt * tranche_wt, 12),
                                "entry_price": entry_price,
                                "exit_price": exit_price,
                                "stock_path_ret": stock_path_ret,
                                "stock_path_ret_available": bool(pd.notna(stock_path_ret)),
                                "event_value": c_row.get("value", np.nan),
                                "label_fwd_ret_20d": c_row.get("fwd_ret_20d", np.nan),
                                "ab_label": c_row.get("ab_label", ""),
                                "quality_pass_20d": c_row.get("quality_pass_20d", np.nan),
                            })

            active = [t for t in tranches if t["exec_date"] <= td <= t["exit_date"]]
            n_active = len(active)
            daily_gross = 0.0
            daily_cost = 0.0
            active_stocks = 0

            for t in active:
                stock_rets = []
                for s in t["stocks"]:
                    stock_rets.append(ret_lookup.get((s, td), 0.0))
                    active_stocks += 1

                if td > t["exec_date"]:
                    tranche_ret = float(np.mean(stock_rets)) if stock_rets else 0.0
                    t["tranche_daily_returns"].append(tranche_ret)
                    daily_gross += t["tranche_weight"] * tranche_ret

                if td == t["exec_date"]:
                    daily_cost += t["entry_cost"]
                if td == t["exit_date"]:
                    daily_cost += t["exit_cost"]

            daily_gross = float(np.clip(daily_gross, -0.15, 0.15))
            daily_net = daily_gross - daily_cost
            gross_exposure = n_active / MAX_TRANCHES

            daily_pnl_records.append({
                "trade_date": int(td),
                "strategy": gcol,
                "daily_gross_return": round(daily_gross, 8),
                "daily_cost": round(daily_cost, 8),
                "daily_net_return": round(daily_net, 8),
                "active_tranches": n_active,
                "active_stocks": active_stocks,
                "gross_exposure": round(gross_exposure, 4),
                "turnover": round(daily_cost / COST_BPS, 6) if daily_cost > 0 else 0.0,
            })

            for t in tranches:
                if t["exit_date"] == td:
                    gross_path_ret = float(np.prod(
                        1.0 + np.asarray(t["tranche_daily_returns"], dtype=float)
                    ) - 1.0)
                    realized_path_ret = gross_path_ret - t["entry_cost"] - t["exit_cost"]
                    audit_idx = t["audit_idx"]
                    all_tranche_audit[audit_idx]["realized_path_ret"] = round(
                        realized_path_ret, 8)
                    all_tranche_audit[audit_idx]["path_vs_label_diff"] = round(
                        realized_path_ret - t["label_fwd_ret"], 8)
                    all_tranche_audit[audit_idx]["realized_path_available"] = True
                    all_tranche_audit[audit_idx]["holding_days_observed"] = len(
                        t["tranche_daily_returns"])
                    t["_closing"] = True

            tranches = [t for t in tranches if not t.get("_closing", False)]

    daily_returns = pd.DataFrame(daily_pnl_records)
    if not daily_returns.empty:
        frames = []
        for _, grp in daily_returns.groupby("strategy", sort=False):
            grp = grp.copy()
            grp["cum_net_return"] = (1.0 + grp["daily_net_return"]).cumprod() - 1.0
            equity = 1.0 + grp["cum_net_return"]
            grp["drawdown"] = equity / equity.cummax() - 1.0
            frames.append(grp)
        daily_returns = pd.concat(frames, ignore_index=True)

    return (
        daily_returns,
        pd.DataFrame(all_tranche_audit),
        pd.DataFrame(all_constituents),
    )


def compute_real_path_metrics(
    daily_returns: pd.DataFrame,
) -> pd.DataFrame:
    """Compute real path sleeve performance metrics from daily net returns."""
    if daily_returns.empty:
        return pd.DataFrame()

    results = []
    for gcol in sorted(daily_returns["strategy"].unique()):
        dr = daily_returns[daily_returns["strategy"] == gcol]
        if dr.empty:
            continue

        ret_series = dr["daily_net_return"].values
        cum_ret = float(np.prod(1 + ret_series) - 1)
        avg_daily = float(np.mean(ret_series))
        daily_std = float(np.std(ret_series)) if len(ret_series) > 1 else 1.0
        ann_ret = float(avg_daily * 252)
        ann_vol = float(daily_std * np.sqrt(252))
        sharpe = float(ann_ret / ann_vol) if ann_vol > 0 else 0.0

        cum_series = np.cumprod(1 + ret_series)
        running_max = np.maximum.accumulate(cum_series)
        drawdown_series = cum_series / running_max - 1
        max_dd = float(np.min(drawdown_series))

        win_rate = float(np.mean(ret_series > 0))
        avg_tranches = float(dr["active_tranches"].mean())
        avg_exposure = float(dr["gross_exposure"].mean())
        total_cost = float(dr["daily_cost"].sum())

        results.append({
            "strategy": gcol,
            "validation_type": "real_path_simulation",
            "n_days": len(dr),
            "cumulative_return": round(cum_ret, 6),
            "annualized_return": round(ann_ret, 6),
            "annualized_vol": round(ann_vol, 6),
            "sharpe_ratio": round(sharpe, 4),
            "max_drawdown": round(max_dd, 6),
            "win_rate": round(win_rate, 4),
            "avg_active_tranches": round(avg_tranches, 2),
            "max_active_tranches": int(dr["active_tranches"].max()) if len(dr) > 0 else 0,
            "avg_gross_exposure": round(avg_exposure, 4),
            "total_cost": round(total_cost, 6),
        })

    return pd.DataFrame(results)


# ═══════════════════════════════════════════════════════════════════════
# Report
# ═══════════════════════════════════════════════════════════════════════
def generate_phase4_report(
    event_forward: pd.DataFrame,
    path_metrics: pd.DataFrame,
    threshold_audit: list[dict],
    audits: list[dict],
    daily_returns: pd.DataFrame,
) -> str:
    primary = PRIMARY_GATE_STRATEGY
    lines = [
        "# Panic Sleeve Gate — Phase 4 Report (v2 audited)",
        "",
        "**RESEARCH ONLY — does not approve production use.**",
        "",
        "## Primary Strategy (frozen)",
        "",
        f"- `{primary}`",
        "- ML model: logreg, threshold=0.60",
        "- Rule gates: top 20% threshold, frozen from training period",
        "",
        "## Leakage Control",
        "",
        "- mode: label_available_plus_embargo",
        "- embargo_days: 20",
        "- All thresholds from training period only",
        "",
    ]

    # Leakage audit
    if audits:
        df_audit = pd.DataFrame(audits)
        lines.extend([
            "## Leakage Audit",
            "",
            df_audit.to_markdown(index=False, floatfmt=".4f"),
            "",
        ])
        ok, violations = validate_leakage_audit(audits)
        lines.append(f"**Leakage audit: {'PASS' if ok else 'FAIL'}**")
        for v in violations:
            lines.append(f"- FAIL: {v}")
        lines.append("")

    # Threshold audit
    if threshold_audit:
        lines.extend([
            "## Threshold Audit",
            "",
            pd.DataFrame(threshold_audit).to_markdown(index=False, floatfmt=".4f"),
            "",
        ])

    # ── Layer A: Event forward validation ────────────────────────────
    if not event_forward.empty:
        lines.extend([
            "## Layer A: Event-Day Forward Return Validation",
            "",
            "**NOTE: These are label-level metrics. They are NOT portfolio returns.**",
            "No annualization, no Sharpe, no cumulative PnL.",
            "",
            event_forward.to_markdown(index=False, floatfmt=".4f"),
            "",
        ])

        # Primary strategy event-forward result
        pm = event_forward[event_forward["strategy"] == primary]
        if not pm.empty:
            p = pm.iloc[0]
            lines.extend([
                "### Primary Strategy Event-Forward Result",
                "",
                f"- net_spread_lift: `{p['net_spread_lift']:.4f}`",
                f"- a_rate_lift: `{p['a_rate_lift']:.4f}`",
                f"- coverage: `{p['coverage_pct']:.1f}%`",
                "",
            ])

    # ── Layer B: Path simulation ─────────────────────────────────────
    if not path_metrics.empty:
        lines.extend([
            "## Layer B: Real Path Sleeve Simulation",
            "",
            "Tranche-based simulation with overlapping 20-day holdings.",
            "Daily returns account for concurrently active tranches.",
            "",
            path_metrics.to_markdown(index=False, floatfmt=".4f"),
            "",
        ])

        pm_path = path_metrics[path_metrics["strategy"] == primary]
        if not pm_path.empty:
            p = pm_path.iloc[0]
            go_ret = p["cumulative_return"] > 0
            go_dd = p["max_drawdown"] > -0.30
            lines.extend([
                "### Primary Strategy Path Result",
                "",
                f"- cumulative_return: `{p['cumulative_return']:.4f}` {'PASS' if go_ret else 'FAIL'}",
                f"- sharpe_ratio: `{p['sharpe_ratio']:.4f}`",
                f"- max_drawdown: `{p['max_drawdown']:.4f}` {'PASS' if go_dd else 'FAIL'}",
                f"- avg_active_tranches: `{p['avg_active_tranches']:.1f}`",
                "",
            ])

    # ── Go/No-Go ─────────────────────────────────────────────────────
    lines.extend([
        "## Go / No-Go",
        "",
        "Go/No-Go based ONLY on primary strategy `gate_ml_logreg`.",
        "",
    ])

    pm_ef = event_forward[event_forward["strategy"] == primary] if not event_forward.empty else pd.DataFrame()
    pm_path = path_metrics[path_metrics["strategy"] == primary] if not path_metrics.empty else pd.DataFrame()

    if not pm_ef.empty:
        ef_lift = pm_ef.iloc[0]["net_spread_lift"]
        ef_pos = ef_lift > 0

        path_ok = True
        if not pm_path.empty:
            path_ok = pm_path.iloc[0]["cumulative_return"] > 0

        go = ef_pos and path_ok
        lines.append(f"- net_spread_lift > 0: `{ef_lift:.4f}` {'PASS' if ef_pos else 'FAIL'}")
        lines.append(f"- path cumulative_return > 0: {'PASS' if path_ok else 'FAIL'}")
        lines.append(f"- **Overall: {'GO' if go else 'NO-GO'}**")
        lines.append("")
        lines.append("(Candidate strategies below are diagnostics only; Go/No-Go based on primary.)")
        lines.append("")

    lines.extend([
        "## Final Status",
        "",
        "```",
        "research_only = true",
        "production_eligible = false",
        "use_case = panic event diagnostic / panic basket gate research",
        "not_use_case = stock selector / portfolio alpha / live filter",
        "```",
        "",
    ])

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════
def main() -> int:
    args = parse_args()
    input_dir = Path(args.input_dir)
    out_dir = Path(args.out_dir)

    print("=" * 70)
    print("Phase 4: Panic Sleeve Gate Validation (v3 real path)")
    print("=" * 70)

    # ── Clean up deprecated old outputs ───────────────────────────────
    deprecated_dir = out_dir / "deprecated"
    deprecated_dir.mkdir(parents=True, exist_ok=True)
    deprecated_files = [
        "panic_sleeve_gate_backtest_compare.csv",
        "panic_sleeve_gate_daily_signals.csv",
        "panic_sleeve_gate_yearly_attribution.csv",
        "panic_sleeve_gate_path_daily_returns.csv",
        "panic_sleeve_gate_path_compare.csv",
        "panic_sleeve_gate_path_yearly_attribution.csv",
    ]
    deprecated_manifest = []
    for fname in deprecated_files:
        fpath = out_dir / fname
        if fpath.exists():
            target = deprecated_dir / fname
            import shutil
            shutil.move(str(fpath), str(target))
            deprecated_manifest.append({
                "file": fname,
                "deprecated_reason": "replaced_by_real_path_v3",
                "deprecated_at": pd.Timestamp.now().isoformat(),
                "replacement_file": (
                    fname.replace("path_", "real_path_")
                    if "path_" in fname else
                    fname.replace("backtest_compare", "real_path_compare")
                    .replace("daily_signals", "real_path_daily_returns")
                    .replace("yearly_attribution", "real_path_yearly_attribution")
                ),
            })
            print(f"  [cleanup] Moved {fname} -> deprecated/")

    if deprecated_manifest:
        (deprecated_dir / "deprecated_manifest.json").write_text(
            json.dumps(deprecated_manifest, indent=2, ensure_ascii=False),
            encoding="utf-8")

    # ── Load data ─────────────────────────────────────────────────────
    samples_path = input_dir / "panic_basket_daily_samples.csv"
    daily = pd.read_csv(samples_path)
    daily["trade_date"] = pd.to_numeric(daily["trade_date"], errors="coerce")
    daily = daily.dropna(subset=["trade_date"])
    daily = daily.sort_values("trade_date").reset_index(drop=True)
    daily = daily.replace([np.inf, -np.inf], np.nan)
    print(f"Loaded {len(daily):,} daily basket samples")

    # Load stock-level event samples (Phase 1 output)
    event_stock_path = input_dir / "panic_basket_event_stock_samples.parquet"
    event_stock_samples = pd.DataFrame()
    if event_stock_path.exists():
        event_stock_samples = pd.read_parquet(event_stock_path)
        event_stock_samples["trade_date"] = pd.to_numeric(
            event_stock_samples["trade_date"], errors="coerce")
        event_stock_samples = event_stock_samples.dropna(subset=["trade_date"])
        print(f"Loaded {len(event_stock_samples):,} stock-level event samples")
    else:
        print("WARNING: event_stock_samples.parquet not found (run Phase 1 first)")

    # Load prices for real path simulation
    prices_path = ROOT / "data" / "parquet" / "prices_adj"
    prices = pd.DataFrame()
    if prices_path.exists():
        print("Loading prices for real path simulation...")
        from build_panic_basket_daily_gate import load_prices
        prices = load_prices(ROOT, 20170101, 20251231)
        print(f"  prices: {len(prices):,} rows")
    else:
        print("WARNING: prices not found, real path simulation will be skipped")

    # Load full market calendar
    market_cal = load_market_calendar(ROOT, 20170101, 20251231)
    if market_cal is None and not prices.empty:
        market_cal = build_trading_calendar(prices)
    if market_cal is not None:
        print(f"  market calendar: {len(market_cal):,} trading days")

    # ── Generate walk-forward gates ────────────────────────────────────
    print("\n[1] Generating walk-forward gate signals (train-frozen thresholds)...")
    gates, threshold_audit, audits = generate_walkforward_gates(daily)
    print(f"  {len(gates):,} daily gate signals")
    gate_cols_found = [c for c in gates.columns if c.startswith("gate_")]
    print(f"  Gate columns: {gate_cols_found}")

    # Layer A: Event forward validation (label-level, NOT portfolio returns)
    print("\n[2] Layer A: Event-Day Forward Return Validation...")
    event_forward = event_forward_validation(gates)

    # Layer B: Real path simulation
    print("\n[3] Layer B: Real Path Sleeve Simulation (constituent stock returns)...")
    if not prices.empty and not event_stock_samples.empty and market_cal is not None:
        daily_returns, tranche_audit, tranche_constituents = simulate_real_path_sleeve(
            prices, gates, market_cal, event_stock_samples)
        path_metrics = compute_real_path_metrics(daily_returns)
    else:
        daily_returns = pd.DataFrame()
        tranche_audit = pd.DataFrame()
        tranche_constituents = pd.DataFrame()
        path_metrics = pd.DataFrame()
        print("  SKIPPED: missing prices, event_stock_samples, or market calendar")

    # ── Save outputs ───────────────────────────────────────────────────
    event_forward.to_csv(out_dir / "panic_sleeve_gate_event_forward_compare.csv", index=False)
    pd.DataFrame(threshold_audit).to_csv(out_dir / "panic_sleeve_gate_threshold_audit.csv", index=False)
    pd.DataFrame(audits).to_csv(out_dir / "panic_sleeve_gate_leakage_audit.csv", index=False)

    if not daily_returns.empty:
        daily_returns.to_csv(out_dir / "panic_sleeve_gate_real_path_daily_returns.csv", index=False)
    if not path_metrics.empty:
        path_metrics.to_csv(out_dir / "panic_sleeve_gate_real_path_compare.csv", index=False)
    if not tranche_constituents.empty:
        tranche_constituents.to_parquet(
            out_dir / "panic_sleeve_gate_tranche_constituents.parquet", index=False)
    if not tranche_audit.empty:
        tranche_audit.to_csv(out_dir / "panic_sleeve_gate_tranche_audit.csv", index=False)

    # Yearly attribution for real path
    if not daily_returns.empty:
        daily_returns["year"] = daily_returns["trade_date"] // 10000
        yearly_path = []
        for (gcol, yr), grp in daily_returns.groupby(["strategy", "year"]):
            if len(grp) < 10:
                continue
            rets = grp["daily_net_return"].values
            cum = float(np.prod(1 + rets) - 1)
            avg_d = float(np.mean(rets))
            yearly_path.append({
                "year": int(yr),
                "strategy": gcol,
                "n_days": len(grp),
                "cumulative_return": round(cum, 6),
                "annualized_return": round(avg_d * 252, 6),
                "avg_active_tranches": round(float(grp["active_tranches"].mean()), 2),
                "avg_gross_exposure": round(float(grp["gross_exposure"].mean()), 4),
                "total_cost": round(float(grp["daily_cost"].sum()), 6),
            })
        if yearly_path:
            pd.DataFrame(yearly_path).to_csv(
                out_dir / "panic_sleeve_gate_real_path_yearly_attribution.csv", index=False)

    # ── Final manifest ─────────────────────────────────────────────────
    ok, violations = validate_leakage_audit(audits)
    leakage_ok = ok
    threshold_ok = all(
        t.get("threshold_source") in ("train_quantile", "frozen_probability")
        for t in threshold_audit
    ) if threshold_audit else False

    # Determine event-forward status
    ef_ok = False
    ef_net_lift = float("nan")
    if not event_forward.empty:
        pm_ef = event_forward[event_forward["strategy"] == PRIMARY_GATE_STRATEGY]
        if not pm_ef.empty:
            ef_net_lift = pm_ef.iloc[0]["net_spread_lift"]
            ef_ok = ef_net_lift > 0

    # Determine real path status
    rp_ok = False
    rp_cum_ret = float("nan")
    if not path_metrics.empty:
        pm_rp = path_metrics[path_metrics["strategy"] == PRIMARY_GATE_STRATEGY]
        if not pm_rp.empty:
            rp_cum_ret = pm_rp.iloc[0]["cumulative_return"]
            rp_ok = rp_cum_ret > 0

    output_contract_ok = (
        not daily_returns.empty
        and {"cum_net_return", "drawdown"}.issubset(daily_returns.columns)
        and not tranche_audit.empty
        and {"realized_path_ret", "path_vs_label_diff", "realized_path_available"}.issubset(
            tranche_audit.columns)
        and bool(tranche_audit["realized_path_available"].all())
        and not tranche_constituents.empty
        and {"ts_code", "stock_weight_in_tranche", "tranche_weight",
             "entry_price", "exit_price", "stock_path_ret"}.issubset(
                 tranche_constituents.columns)
    )

    # Final GO must satisfy ALL conditions
    final_go = (leakage_ok and threshold_ok and ef_ok and rp_ok and output_contract_ok)
    block_reasons = []
    if not leakage_ok:
        block_reasons.append("leakage_audit_FAIL")
        for v in violations:
            block_reasons.append(f"  {v}")
    if not threshold_ok:
        block_reasons.append("threshold_not_train_frozen")
    if not ef_ok:
        block_reasons.append(
            f"event_forward_net_spread_lift={ef_net_lift:.4f} (required: > 0)")
    if not rp_ok:
        block_reasons.append(
            f"real_path_cumulative_return={rp_cum_ret:.4f} (required: > 0)")
    if not output_contract_ok:
        block_reasons.append("real_path_output_contract_FAIL")

    # List valid output files
    valid_files = sorted([
        f.name for f in out_dir.glob("*")
        if f.is_file() and "deprecated" not in str(f)
    ])
    deprecated_output_files = sorted([
        f.name for f in deprecated_dir.iterdir()
        if f.is_file() and f.name != "deprecated_manifest.json"
    ]) if deprecated_dir.exists() else []

    final_manifest = {
        "schema": "panic_basket_gate.final_acceptance.v1",
        "research_only": True,
        "production_eligible": False,
        "final_status": "GO" if final_go else "NO_GO",
        "primary_strategy": PRIMARY_GATE_STRATEGY,
        "leakage_audit": "PASS" if leakage_ok else "FAIL",
        "threshold_audit": "PASS" if threshold_ok else "FAIL",
        "event_forward_status": "PASS" if ef_ok else "FAIL",
        "event_forward_net_spread_lift": round(ef_net_lift, 6) if not math.isnan(ef_net_lift) else None,
        "real_path_status": "PASS" if rp_ok else "FAIL",
        "real_path_cumulative_return": round(rp_cum_ret, 6) if not math.isnan(rp_cum_ret) else None,
        "real_path_output_contract": "PASS" if output_contract_ok else "FAIL",
        "block_reasons": block_reasons,
        "valid_output_files": valid_files,
        "deprecated_output_files": deprecated_output_files,
    }
    (out_dir / "panic_basket_gate_final_manifest.json").write_text(
        json.dumps(final_manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    # ── Report ─────────────────────────────────────────────────────────
    report = generate_phase4_report(
        event_forward, path_metrics, threshold_audit, audits, daily_returns)
    (out_dir / "panic_sleeve_gate_drawdown_report.md").write_text(report, encoding="utf-8")

    print(f"\nPhase 4 complete. Leakage audit: {'PASS' if leakage_ok else 'FAIL'}")
    if violations:
        for v in violations:
            print(f"  {v}")

    if not event_forward.empty:
        pm = event_forward[event_forward["strategy"] == PRIMARY_GATE_STRATEGY]
        if not pm.empty:
            p = pm.iloc[0]
            print(f"  Event-forward ({PRIMARY_GATE_STRATEGY}): "
                  f"net_lift={p['net_spread_lift']:.4f} "
                  f"a_rate_lift={p['a_rate_lift']:.4f} "
                  f"cov={p['coverage_pct']:.1f}%")

    if not path_metrics.empty:
        pm = path_metrics[path_metrics["strategy"] == PRIMARY_GATE_STRATEGY]
        if not pm.empty:
            p = pm.iloc[0]
            print(f"  Real-path ({PRIMARY_GATE_STRATEGY}): "
                  f"cum_ret={p['cumulative_return']:.4f} "
                  f"sharpe={p['sharpe_ratio']:.4f} "
                  f"max_dd={p['max_drawdown']:.4f}")

    print(f"  Final status: {final_manifest['final_status']}")
    if block_reasons:
        for r in block_reasons:
            print(f"    Block: {r}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

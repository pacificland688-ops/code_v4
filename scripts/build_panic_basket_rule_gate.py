"""
Phase 2: Rule-Based Panic Basket Daily Gate Prototype (v2 — audited)
=====================================================================
Scoring-based rule gate for daily panic basket. Thresholds are estimated
from training period and frozen in test. Walk-forward split uses unified
label_availability + embargo controls.

Primary strategy (frozen): composite_top_50pct
Gate scoring dimensions: panic_intensity, market_stress_inverted,
  breadth_repair, liquidity_support

Outputs (-> outputs/analysis/panic_reversal_gate/daily_basket_v1/):
  - panic_basket_gate_rule_compare.csv
  - panic_basket_gate_rule_walkforward.csv
  - panic_basket_gate_leakage_audit.csv
  - panic_basket_gate_rule_report.md
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from panic_gate_shared import (  # noqa: E402
    COST_BPS, DEFAULT_WINDOWS, PRIMARY_RULE_STRATEGY,
    WindowSpec, LeakageAudit,
    build_trading_calendar, load_market_calendar,
    get_windows, split_train_test, validate_leakage_audit,
)

DEFAULT_INPUT_DIR = ROOT / "outputs" / "analysis" / "panic_reversal_gate" / "daily_basket_v1"
DEFAULT_OUT_DIR = DEFAULT_INPUT_DIR
TOP_THRESHOLDS = (0.20, 0.30, 0.50)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Phase 2: Rule-based panic basket gate (v2)")
    p.add_argument("--input-dir", default=str(DEFAULT_INPUT_DIR))
    p.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    return p.parse_args()


# ═══════════════════════════════════════════════════════════════════════
# Scoring functions
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
            dd = df[c].copy()
            components.append((dd + 0.30).clip(0, 0.30) / 0.30)
            break
    for c in df.columns:
        if "vol_5d_over_20d" in c and c.startswith("idx_"):
            vr = df[c].copy()
            components.append((1.5 - vr).clip(0, 1.5) / 1.5)
            break
    if "big_down_pct" in df.columns:
        bd = df["big_down_pct"].copy()
        components.append((0.20 - bd).clip(0, 0.20) / 0.20)
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
    "market_stress_inverted": score_market_stress_inverted,
    "breadth_repair": score_breadth_repair,
    "liquidity_support": score_liquidity_support,
}


def compute_all_scores(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    for name, fn in SCORE_FUNCS.items():
        result[f"score_{name}"] = fn(df).values
    score_cols = [f"score_{n}" for n in SCORE_FUNCS]
    result["score_composite"] = result[score_cols].mean(axis=1)
    return result


# ═══════════════════════════════════════════════════════════════════════
# Gate evaluation
# ═══════════════════════════════════════════════════════════════════════
def evaluate_gate(
    df: pd.DataFrame,
    gate_mask: pd.Series,
    strategy_name: str,
    window_name: str,
    raw_ret: float,
    raw_a_rate: float,
    threshold_info: str = "",
) -> dict:
    ret_col = "basket_mean_fwd_ret_20d"
    n_days = len(df)
    n_allow = int(gate_mask.sum())
    cov = n_allow / n_days * 100 if n_days else 0

    result = {
        "strategy": strategy_name,
        "window": window_name,
        "n_days": n_days,
        "n_allow": n_allow,
        "coverage_pct": round(cov, 1),
        "raw_mean_ret": round(raw_ret, 6),
        "raw_a_rate": round(raw_a_rate, 6),
        "threshold_info": threshold_info,
    }

    if n_allow > 0 and ret_col in df.columns:
        amr = float(df.loc[gate_mask, ret_col].mean())
        result["allow_mean_ret"] = round(amr, 6)
        result["allow_net_ret"] = round(amr - COST_BPS, 6)
        result["net_spread_lift"] = round(amr - raw_ret, 6)
    else:
        result["allow_mean_ret"] = float("nan")
        result["allow_net_ret"] = float("nan")
        result["net_spread_lift"] = float("nan")

    if "basket_a_rate_20d" in df.columns and n_allow > 0:
        ara = float(df.loc[gate_mask, "basket_a_rate_20d"].mean())
        result["allow_a_rate"] = round(ara, 6)
        result["a_rate_lift"] = round(ara - raw_a_rate, 6) if not math.isnan(raw_a_rate) else float("nan")
    else:
        result["allow_a_rate"] = float("nan")
        result["a_rate_lift"] = float("nan")

    return result


# ═══════════════════════════════════════════════════════════════════════
# Walk-forward
# ═══════════════════════════════════════════════════════════════════════
def run_walkforward(daily_basket: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, list[dict]]:
    df = daily_basket.copy()
    df["year"] = df["trade_date"] // 10000

    # Full market calendar (NOT basket dates)
    market_cal = load_market_calendar(ROOT, int(df["trade_date"].min()), int(df["trade_date"].max()))
    if market_cal is None:
        market_cal = build_trading_calendar(
            pd.DataFrame({"trade_date": sorted(df["trade_date"].unique())}))
    calendar_source = "prices_adj_full_market" if market_cal is not None else "basket_dates"
    calendar_is_full = market_cal is not None and len(market_cal) > len(df) * 2

    windows = get_windows()
    ret_col = "basket_mean_fwd_ret_20d"

    all_metrics = []
    all_predictions = []
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

        # Compute scores on train AND test independently
        train = compute_all_scores(train)
        test = compute_all_scores(test)

        raw_ret = float(test[ret_col].mean())
        raw_a_rate = (float(test["basket_a_rate_20d"].mean())
                      if "basket_a_rate_20d" in test.columns else float("nan"))

        window_name = window.name

        # Raw events baseline
        all_metrics.append(evaluate_gate(
            test, pd.Series(True, index=test.index),
            "raw_events", window_name, raw_ret, raw_a_rate, "none"))

        # Test each dimension + composite at each threshold
        dim_names = list(SCORE_FUNCS.keys()) + ["composite"]

        for dim in dim_names:
            score_col = f"score_{dim}"
            if score_col not in test.columns:
                continue

            train_scores = train[score_col].dropna()
            if len(train_scores) < 20:
                continue

            for top_pct in TOP_THRESHOLDS:
                # Threshold FROZEN from training period
                threshold = float(train_scores.quantile(1.0 - top_pct))
                strategy_name = f"{dim}_top_{int(top_pct * 100)}pct"
                mask = test[score_col] >= threshold

                all_metrics.append(evaluate_gate(
                    test, mask, strategy_name, window_name,
                    raw_ret, raw_a_rate,
                    f"train_quantile({1.0 - top_pct:.2f})={threshold:.4f}"))

        # Save test predictions
        pred = test[["trade_date", "year", ret_col, "basket_a_rate_20d",
                      "basket_win_rate_20d", "event_count"]].copy()
        pred["window"] = window_name
        for dim in dim_names:
            sc = f"score_{dim}"
            if sc in test.columns:
                pred[sc] = test[sc].values
        all_predictions.append(pred)

    return (pd.DataFrame(all_metrics),
            pd.concat(all_predictions, ignore_index=True) if all_predictions else pd.DataFrame(),
            all_audits)


# ═══════════════════════════════════════════════════════════════════════
# Report
# ═══════════════════════════════════════════════════════════════════════
def generate_rule_report(metrics: pd.DataFrame, audits: list[dict]) -> str:
    primary = PRIMARY_RULE_STRATEGY

    lines = [
        "# Panic Basket Rule-Based Gate — Phase 2 Report (v2 audited)",
        "",
        "**RESEARCH ONLY — does not approve production use.**",
        "",
        "## Leakage Control",
        "",
        "- `mode = label_available_plus_embargo`",
        "- `embargo_days = 20`",
        "- Training excludes samples where basket_label_available_date >= test_start",
        "- Training ends 20 trading days before test start",
        "",
        f"## Primary Strategy (frozen): `{primary}`",
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
        if violations:
            for v in violations:
                lines.append(f"- FAIL: {v}")
        lines.append("")

    if metrics.empty:
        lines.append("**No valid metrics.**")
        return "\n".join(lines)

    # Primary strategy result
    primary_metrics = metrics[metrics["strategy"] == primary]
    lines.extend([
        "## Primary Strategy Result (for Go/No-Go)",
        "",
    ])
    if not primary_metrics.empty:
        avg_net = primary_metrics["net_spread_lift"].mean()
        pos = int((primary_metrics["net_spread_lift"] > 0).sum())
        tot = len(primary_metrics)
        avg_cov = primary_metrics["coverage_pct"].mean()
        lines.append(f"- avg_net_spread_lift: `{avg_net:.4f}`")
        lines.append(f"- positive_windows: `{pos}/{tot}`")
        lines.append(f"- avg_coverage: `{avg_cov:.1f}%`")
        lines.append(f"- primary Go/No-Go: **{'GO' if avg_net > 0 and pos >= 2 else 'NO-GO'}**")
        lines.append("")
        lines.append(primary_metrics.to_markdown(index=False, floatfmt=".4f"))
        lines.append("")

    # Candidate comparison
    lines.extend([
        "## Candidate Strategy Comparison (diagnostics only)",
        "",
    ])
    agg = metrics.groupby("strategy").agg(
        avg_net_spread_lift=("net_spread_lift", "mean"),
        avg_a_rate_lift=("a_rate_lift", "mean"),
        avg_coverage_pct=("coverage_pct", "mean"),
        positive_windows=("net_spread_lift", lambda x: int((x > 0).sum())),
        total_windows=("net_spread_lift", "count"),
    ).reset_index()
    agg = agg.sort_values("avg_net_spread_lift", ascending=False)
    lines.append(agg.to_markdown(index=False, floatfmt=".4f"))
    lines.append("")

    # Full detail
    lines.extend([
        "## Full Walk-Forward Detail",
        "",
        metrics.to_markdown(index=False, floatfmt=".4f"),
        "",
    ])

    lines.extend([
        "## Go / No-Go",
        "",
        "Go/No-Go based ONLY on primary strategy `composite_top_50pct`.",
        "All candidate strategies above are diagnostics only.",
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
    print("Phase 2: Rule-Based Panic Basket Daily Gate (v2 audited)")
    print("=" * 70)

    samples_path = input_dir / "panic_basket_daily_samples.csv"
    if not samples_path.exists():
        print(f"ERROR: {samples_path} not found. Run Phase 1 first.")
        return 1

    daily = pd.read_csv(samples_path)
    daily["trade_date"] = pd.to_numeric(daily["trade_date"], errors="coerce")
    daily = daily.dropna(subset=["trade_date"])
    daily = daily.sort_values("trade_date").reset_index(drop=True)
    print(f"Loaded {len(daily):,} daily basket samples")
    if "basket_label_available_date" in daily.columns:
        print(f"  basket_label_available_date present: OK")
    else:
        print(f"  WARNING: basket_label_available_date missing — leakage control degraded")

    print("\nRunning walk-forward rule evaluation...")
    metrics, preds, audits = run_walkforward(daily)

    metrics.to_csv(out_dir / "panic_basket_gate_rule_compare.csv", index=False)
    preds.to_csv(out_dir / "panic_basket_gate_rule_walkforward.csv", index=False)
    pd.DataFrame(audits).to_csv(out_dir / "panic_basket_gate_leakage_audit.csv", index=False)

    report = generate_rule_report(metrics, audits)
    (out_dir / "panic_basket_gate_rule_report.md").write_text(report, encoding="utf-8")

    ok, violations = validate_leakage_audit(audits)
    print(f"\nPhase 2 complete. Outputs saved to {out_dir}")
    print(f"  Leakage audit: {'PASS' if ok else 'FAIL'}")
    if violations:
        for v in violations:
            print(f"    {v}")

    # Primary strategy
    primary = PRIMARY_RULE_STRATEGY
    pm = metrics[metrics["strategy"] == primary]
    if not pm.empty:
        avg_l = pm["net_spread_lift"].mean()
        pos = int((pm["net_spread_lift"] > 0).sum())
        print(f"  Primary ({primary}): net_lift={avg_l:.4f}  pos_wins={pos}/{len(pm)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

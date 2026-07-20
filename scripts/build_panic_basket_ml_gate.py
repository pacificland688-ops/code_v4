"""
Phase 3: ML Model for Panic Basket Daily Gate (v2 — audited)
=============================================================
Walk-forward ML gate using Logistic Regression (frozen primary model)
with training-period frozen parameters and embargo controls.

All feature selection, imputation, scaling, and model fitting are done
within each walk-forward window using ONLY training data.

Primary strategy (frozen): logreg, gate_threshold=0.60

Outputs (-> outputs/analysis/panic_reversal_gate/daily_basket_v1/):
  - panic_basket_gate_model_walkforward.csv
  - panic_basket_gate_model_feature_importance.csv
  - panic_basket_gate_model_feature_audit.csv
  - panic_basket_gate_model_calibration.csv
  - panic_basket_gate_model_report.md
"""
from __future__ import annotations

import argparse
import math
import sys
import warnings
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, average_precision_score, brier_score_loss
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from panic_gate_shared import (  # noqa: E402
    COST_BPS, DEFAULT_WINDOWS, PRIMARY_ML_MODEL, PRIMARY_ML_THRESHOLD,
    build_trading_calendar, load_market_calendar,
    get_windows, split_train_test, validate_leakage_audit,
)

DEFAULT_INPUT_DIR = ROOT / "outputs" / "analysis" / "panic_reversal_gate" / "daily_basket_v1"
DEFAULT_OUT_DIR = DEFAULT_INPUT_DIR
MAX_FEATURES = 30

EXCLUDE_COLS = {
    "trade_date", "year", "window",
    "basket_mean_fwd_ret_20d", "basket_net_fwd_ret_20d",
    "basket_a_rate_20d", "basket_b_rate_20d",
    "basket_win_rate_20d", "basket_top_half_ret_20d",
    "basket_ret_std_20d",
    "basket_mean_fwd_ret_20d_hist_pct_60d",
    "event_ratio_hist_pct_60d",
    "gate_label",
    "basket_label_available_date",
    "min_event_label_available_date",
    "n_events_label_available", "n_events_label_unavailable",
}

FORBIDDEN_SUBSTRINGS = (
    "fwd_", "future_", "_label", "target_",
    "basket_mean_fwd", "basket_net_fwd", "basket_a_rate",
    "basket_b_rate", "basket_win_rate", "basket_top_half",
    "basket_ret_std",
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Phase 3: ML model gate (v2 audited)")
    p.add_argument("--input-dir", default=str(DEFAULT_INPUT_DIR))
    p.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    return p.parse_args()


# ═══════════════════════════════════════════════════════════════════════
# Per-window feature selection
# ═══════════════════════════════════════════════════════════════════════
def select_features(train_df: pd.DataFrame) -> tuple[list[str], dict]:
    """Select features using ONLY training data. Returns (feature_list, audit_info)."""
    features = []
    missing_info = {}

    for c in train_df.columns:
        if c in EXCLUDE_COLS:
            continue
        cl = c.lower()
        if any(p in cl for p in FORBIDDEN_SUBSTRINGS):
            continue
        if train_df[c].dtype not in ("float64", "float32", "int64", "int32"):
            continue
        missing_rate = train_df[c].isna().mean()
        if missing_rate > 0.5:
            continue
        features.append(c)
        missing_info[c] = round(missing_rate, 4)

    # Variance-based truncation to max_features
    if len(features) > MAX_FEATURES:
        variances = {}
        for c in features:
            var = train_df[c].var()
            variances[c] = var if not pd.isna(var) else 0.0
        features = sorted(variances, key=variances.get, reverse=True)[:MAX_FEATURES]

    audit = {
        "n_features": len(features),
        "feature_columns": ",".join(features),
        "feature_selection_source": "train_only",
        "max_missing_rate_train": max(missing_info.values()) if missing_info else 0.0,
    }
    return features, audit


def build_logreg() -> Pipeline:
    return Pipeline(steps=[
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler", StandardScaler()),
        ("model", LogisticRegression(
            class_weight="balanced", max_iter=2000, random_state=42)),
    ])


# ═══════════════════════════════════════════════════════════════════════
# Walk-forward
# ═══════════════════════════════════════════════════════════════════════
def run_ml_walkforward(daily_basket: pd.DataFrame):
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

    all_metrics = []
    all_importance = []
    all_feature_audit = []
    all_calibration = []
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

        # Per-window feature selection (train only)
        features, feat_audit = select_features(train)
        feat_audit["window"] = window_name
        feat_audit["model"] = PRIMARY_ML_MODEL
        all_feature_audit.append(feat_audit)

        # Missing rate on test (for diagnostics)
        test_missing = {c: round(test[c].isna().mean(), 4) for c in features if c in test.columns}
        feat_audit["max_missing_rate_test"] = max(test_missing.values()) if test_missing else 0.0

        # Skip if not enough features
        if len(features) < 3:
            continue

        X_train = train[features].copy()
        y_train = train["gate_label"].values
        X_test = test[features].copy()
        y_test = test["gate_label"].values

        if y_train.sum() < 5 or (len(y_train) - y_train.sum()) < 5:
            continue

        try:
            model = build_logreg()
            model.fit(X_train, y_train)
            test_scores = model.predict_proba(X_test)[:, 1]

            # AUC
            if len(np.unique(y_test)) >= 2:
                auc = float(roc_auc_score(y_test, test_scores))
                pr_auc = float(average_precision_score(y_test, test_scores))
                brier = float(brier_score_loss(y_test, test_scores))
            else:
                auc = float("nan")
                pr_auc = float("nan")
                brier = float("nan")

            raw_ret = float(test[ret_col].mean())
            raw_a_rate = (float(test["basket_a_rate_20d"].mean())
                          if "basket_a_rate_20d" in test.columns else float("nan"))

            # Evaluate at primary threshold
            mask = test_scores >= PRIMARY_ML_THRESHOLD
            n_allow = int(mask.sum())

            result = {
                "model": PRIMARY_ML_MODEL,
                "window": window_name,
                "gate_threshold": PRIMARY_ML_THRESHOLD,
                "n_train": len(X_train),
                "n_test": len(X_test),
                "n_features": len(features),
                "auc": round(auc, 4),
                "pr_auc": round(pr_auc, 4),
                "brier": round(brier, 4),
                "n_allow": n_allow,
                "coverage_pct": round(n_allow / len(test) * 100, 1) if len(test) > 0 else 0.0,
                "raw_mean_ret": round(raw_ret, 6),
                "raw_a_rate": round(raw_a_rate, 6) if not (isinstance(raw_a_rate, float) and math.isnan(raw_a_rate)) else float("nan"),
            }

            if n_allow > 0:
                result["allow_mean_ret"] = round(float(test.loc[mask, ret_col].mean()), 6)
                result["allow_net_ret"] = round(result["allow_mean_ret"] - COST_BPS, 6)
                result["net_spread_lift"] = round(result["allow_mean_ret"] - raw_ret, 6)
                if "basket_a_rate_20d" in test.columns:
                    ara = float(test.loc[mask, "basket_a_rate_20d"].mean())
                    result["allow_a_rate"] = round(ara, 6)
                    result["a_rate_lift"] = round(ara - raw_a_rate, 6) if not math.isnan(raw_a_rate) else float("nan")
            else:
                result["allow_mean_ret"] = float("nan")
                result["allow_net_ret"] = float("nan")
                result["net_spread_lift"] = float("nan")
                result["allow_a_rate"] = float("nan")
                result["a_rate_lift"] = float("nan")

            all_metrics.append(result)

            # Feature importance (coefficients from logreg)
            lr = model.named_steps["model"]
            for feat, coef in zip(features, lr.coef_[0]):
                all_importance.append({
                    "window": window_name,
                    "model": PRIMARY_ML_MODEL,
                    "feature": feat,
                    "coefficient": float(coef),
                    "abs_coefficient": float(abs(coef)),
                })

            # Calibration (score bins)
            test_cal = test.copy()
            test_cal["pred_score"] = test_scores
            test_cal["gate_label"] = y_test
            try:
                test_cal["score_bin"] = pd.qcut(test_cal["pred_score"], 5,
                                                 labels=False, duplicates="drop")
                for b in sorted(test_cal["score_bin"].dropna().unique()):
                    subset = test_cal[test_cal["score_bin"] == b]
                    all_calibration.append({
                        "window": window_name,
                        "model": PRIMARY_ML_MODEL,
                        "score_bin": int(b),
                        "n": len(subset),
                        "mean_score": float(subset["pred_score"].mean()),
                        "actual_pos_rate": float(subset["gate_label"].mean()),
                        "mean_ret": float(subset[ret_col].mean()),
                    })
            except Exception:
                pass

        except Exception as e:
            print(f"  ERROR {window_name}: {e}")

    return (pd.DataFrame(all_metrics),
            pd.DataFrame(all_importance),
            pd.DataFrame(all_feature_audit),
            pd.DataFrame(all_calibration),
            all_audits)


# ═══════════════════════════════════════════════════════════════════════
# Report
# ═══════════════════════════════════════════════════════════════════════
def generate_ml_report(
    metrics: pd.DataFrame,
    importance: pd.DataFrame,
    feature_audit: pd.DataFrame,
    calibration: pd.DataFrame,
    audits: list[dict],
) -> str:
    primary_model = PRIMARY_ML_MODEL
    primary_thr = PRIMARY_ML_THRESHOLD
    primary_strat = f"gate_{primary_model}"

    lines = [
        "# Panic Basket ML Gate — Phase 3 Report (v2 audited)",
        "",
        "**RESEARCH ONLY — does not approve production use.**",
        "",
        "## Configuration",
        "",
        f"- primary_model (frozen): `{primary_model}`",
        f"- primary_gate_threshold (frozen): `{primary_thr}`",
        f"- primary_strategy: `{primary_strat}`",
        "- feature_selection: per-window, train-only",
        "- leakage_control: label_available_plus_embargo",
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

    # Feature audit
    if not feature_audit.empty:
        lines.extend([
            "## Feature Audit (per-window)",
            "",
            feature_audit.to_markdown(index=False, floatfmt=".4f"),
            "",
        ])

    if metrics.empty:
        lines.append("**No valid model results.**")
        return "\n".join(lines)

    # Primary result
    lines.extend([
        "## Primary Strategy Result (for Go/No-Go)",
        "",
        metrics.to_markdown(index=False, floatfmt=".4f"),
        "",
    ])

    avg_lift = metrics["net_spread_lift"].mean()
    pos = int((metrics["net_spread_lift"] > 0).sum())
    tot = len(metrics)
    avg_auc = metrics["auc"].mean()
    avg_cov = metrics["coverage_pct"].mean()

    go_lift = avg_lift > 0
    go_pos = pos >= 2
    go = go_lift and go_pos

    lines.extend([
        f"- avg_net_spread_lift: `{avg_lift:.4f}` {'PASS' if go_lift else 'FAIL'}",
        f"- positive_windows: `{pos}/{tot}` {'PASS' if go_pos else 'FAIL'}",
        f"- avg_auc: `{avg_auc:.4f}`",
        f"- avg_coverage: `{avg_cov:.1f}%`",
        f"- **Go/No-Go: {'GO' if go else 'NO-GO'}**",
        "",
    ])

    # Feature importance
    if not importance.empty:
        imp_agg = importance.groupby("feature").agg(
            mean_coef=("coefficient", "mean"),
            mean_abs=("abs_coefficient", "mean"),
            stability=("coefficient", lambda x: abs(x.mean() / x.std()) if x.std() > 0 else 0),
        ).reset_index()
        imp_agg = imp_agg.sort_values("mean_abs", ascending=False)
        lines.extend([
            "## Feature Importance (top 15)",
            "",
            imp_agg.head(15).to_markdown(index=False, floatfmt=".4f"),
            "",
        ])

    # Calibration
    if not calibration.empty:
        lines.extend([
            "## Calibration Check",
            "",
            calibration.to_markdown(index=False, floatfmt=".4f"),
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
    print("Phase 3: ML Model for Panic Basket Daily Gate (v2 audited)")
    print("=" * 70)

    samples_path = input_dir / "panic_basket_daily_samples.csv"
    if not samples_path.exists():
        print(f"ERROR: {samples_path} not found. Run Phase 1 first.")
        return 1

    daily = pd.read_csv(samples_path)
    daily["trade_date"] = pd.to_numeric(daily["trade_date"], errors="coerce")
    daily = daily.dropna(subset=["trade_date"])
    daily = daily.sort_values("trade_date").reset_index(drop=True)
    daily = daily.replace([np.inf, -np.inf], np.nan)
    daily = daily.dropna(axis=1, how="all")

    net_ret_col = "basket_net_fwd_ret_20d"
    if net_ret_col in daily.columns:
        pos_rate = (daily[net_ret_col] > 0).mean()
        print(f"Label (net_ret > 0) positive rate: {pos_rate:.2%}")

    print("\nRunning walk-forward ML evaluation...")
    metrics, importance, feat_audit, calibration, audits = run_ml_walkforward(daily)

    metrics.to_csv(out_dir / "panic_basket_gate_model_walkforward.csv", index=False)
    importance.to_csv(out_dir / "panic_basket_gate_model_feature_importance.csv", index=False)
    feat_audit.to_csv(out_dir / "panic_basket_gate_model_feature_audit.csv", index=False)
    calibration.to_csv(out_dir / "panic_basket_gate_model_calibration.csv", index=False)
    pd.DataFrame(audits).to_csv(out_dir / "panic_basket_gate_leakage_audit.csv", index=False)

    report = generate_ml_report(metrics, importance, feat_audit, calibration, audits)
    (out_dir / "panic_basket_gate_model_report.md").write_text(report, encoding="utf-8")

    ok, violations = validate_leakage_audit(audits)
    print(f"\nPhase 3 complete. Leakage audit: {'PASS' if ok else 'FAIL'}")
    if not metrics.empty:
        avg_l = metrics["net_spread_lift"].mean()
        pos = int((metrics["net_spread_lift"] > 0).sum())
        print(f"  Primary ({PRIMARY_ML_MODEL}/thr={PRIMARY_ML_THRESHOLD}): "
              f"net_lift={avg_l:.4f} pos_wins={pos}/{len(metrics)} "
              f"auc={metrics['auc'].mean():.4f}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

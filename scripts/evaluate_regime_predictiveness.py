#!/usr/bin/env python
"""Evaluate predictive usefulness of regime probability diagnostics.

This script reads existing Phase 2 diagnostic artifacts only.  It does not
rerun backtests and does not rebuild factors.

The goal is to separate two questions:

1. Does the RegimeDetector output differentiated market-state probabilities?
2. Do those probabilities predict forward benchmark return / risk states?

The ex-post labels used here are diagnostic labels, not training labels:

* high_volatility: abs(forward benchmark period return) >= q75
* trend_up:        forward benchmark period return >= q67
* trend_down:      forward benchmark period return <= q33
* range_bound:     everything else

They are deliberately simple so that detector changes can be compared with a
stable, reproducible yardstick.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


PROB_SUFFIX = "_prob"
COMPARABLE_REGIMES = {"trend_up", "trend_down", "range_bound", "high_volatility"}


@dataclass(frozen=True)
class RunArtifact:
    year: int
    run_dir: Path
    regime_probs_path: Path
    benchmark_returns_path: Path


def _pct(x: Any, digits: int = 1) -> str:
    if x is None or pd.isna(x):
        return "NA"
    return f"{float(x) * 100:.{digits}f}%"


def _num(x: Any, digits: int = 4) -> str:
    if x is None or pd.isna(x):
        return "NA"
    return f"{float(x):.{digits}f}"


def _parse_annual_year(run_name: str) -> int | None:
    """Return the year for annual run names like 20240101_20241231_top50_..."""
    m = re.match(r"^(20\d{2})0101_(20\d{2})1231_top50_", run_name)
    if not m:
        return None
    start_year = int(m.group(1))
    end_year = int(m.group(2))
    if start_year != end_year:
        return None
    return start_year


def discover_run_artifacts(
    runs_root: Path,
    start_year: int,
    end_year: int,
    run_id_contains: str | None = None,
) -> list[RunArtifact]:
    """Find one latest diagnostic run per annual year."""
    candidates: dict[int, list[RunArtifact]] = {}

    for probs_path in runs_root.glob("*/diagnostics/phase2_regime_probs.parquet"):
        run_dir = probs_path.parents[1]
        run_name = run_dir.name
        if run_id_contains and run_id_contains not in run_name:
            continue
        year = _parse_annual_year(run_name)
        if year is None or year < start_year or year > end_year:
            continue

        bench_path = run_dir / "diagnostics" / "phase2_benchmark_period_returns.csv"
        if not bench_path.exists():
            continue

        candidates.setdefault(year, []).append(
            RunArtifact(
                year=year,
                run_dir=run_dir,
                regime_probs_path=probs_path,
                benchmark_returns_path=bench_path,
            )
        )

    selected: list[RunArtifact] = []
    for year in sorted(candidates):
        year_candidates = candidates[year]
        year_candidates.sort(
            key=lambda a: (a.regime_probs_path.stat().st_mtime, a.run_dir.name)
        )
        selected.append(year_candidates[-1])

    return selected


def load_prediction_panel(artifacts: list[RunArtifact]) -> pd.DataFrame:
    """Load and align regime probabilities with forward benchmark returns."""
    rows: list[pd.DataFrame] = []
    for artifact in artifacts:
        probs = pd.read_parquet(artifact.regime_probs_path)
        bench = pd.read_csv(artifact.benchmark_returns_path)

        prob_cols = [c for c in probs.columns if str(c).endswith(PROB_SUFFIX)]
        if "trade_date" not in probs.columns or not prob_cols:
            continue
        required_bench = {"trade_date", "benchmark_return"}
        if not required_bench.issubset(bench.columns):
            continue

        probs = probs[["trade_date", *prob_cols]].copy()
        probs["trade_date"] = probs["trade_date"].astype(str)
        probs["dominant_regime"] = (
            probs[prob_cols].idxmax(axis=1).str.replace(PROB_SUFFIX, "", regex=False)
        )
        probs["dominant_prob"] = probs[prob_cols].max(axis=1)
        prob_values = probs[prob_cols].clip(lower=1e-12)
        probs["prob_entropy"] = (
            -(prob_values * np.log(prob_values)).sum(axis=1) / np.log(len(prob_cols))
        )

        bench = bench.copy()
        bench["trade_date"] = bench["trade_date"].astype(str)
        keep_cols = [
            c
            for c in ["trade_date", "exec_date", "period_end", "benchmark_return"]
            if c in bench.columns
        ]
        merged = bench[keep_cols].merge(probs, on="trade_date", how="inner")
        merged["year"] = artifact.year
        merged["run_dir"] = str(artifact.run_dir)
        rows.append(merged)

    if not rows:
        return pd.DataFrame()

    panel = pd.concat(rows, ignore_index=True)
    panel["benchmark_return"] = pd.to_numeric(panel["benchmark_return"], errors="coerce")
    panel = panel.dropna(subset=["benchmark_return"])
    return panel.sort_values(["year", "trade_date"]).reset_index(drop=True)


def add_expost_labels(panel: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, float]]:
    """Attach simple ex-post labels based on forward benchmark returns."""
    result = panel.copy()
    ret_hi = float(result["benchmark_return"].quantile(0.67))
    ret_lo = float(result["benchmark_return"].quantile(0.33))
    abs_ret_hi = float(result["benchmark_return"].abs().quantile(0.75))

    def label(row: pd.Series) -> str:
        ret = float(row["benchmark_return"])
        if abs(ret) >= abs_ret_hi:
            return "high_volatility"
        if ret >= ret_hi:
            return "trend_up"
        if ret <= ret_lo:
            return "trend_down"
        return "range_bound"

    result["expost_label"] = result.apply(label, axis=1)
    thresholds = {
        "return_q67": ret_hi,
        "return_q33": ret_lo,
        "abs_return_q75": abs_ret_hi,
    }
    return result, thresholds


def compute_outputs(panel: pd.DataFrame) -> dict[str, Any]:
    """Compute summary tables and scalar diagnostics."""
    prob_cols = [c for c in panel.columns if c.endswith(PROB_SUFFIX)]

    comparable_mask = panel["dominant_regime"].isin(COMPARABLE_REGIMES)
    comparable = panel[comparable_mask].copy()
    accuracy_comparable = float(
        comparable["dominant_regime"].eq(comparable["expost_label"]).mean()
    ) if not comparable.empty else float("nan")
    accuracy_all = float(panel["dominant_regime"].eq(panel["expost_label"]).mean())

    dominant_counts = panel["dominant_regime"].value_counts()
    range_bound_share = float(
        dominant_counts.get("range_bound", 0) / len(panel)
    ) if len(panel) else float("nan")

    by_dom = (
        panel.groupby("dominant_regime")
        .agg(
            n=("benchmark_return", "size"),
            mean_forward_return=("benchmark_return", "mean"),
            median_forward_return=("benchmark_return", "median"),
            forward_return_std=("benchmark_return", "std"),
            mean_abs_forward_return=("benchmark_return", lambda s: s.abs().mean()),
            positive_forward_return_rate=("benchmark_return", lambda s: (s > 0).mean()),
            avg_dominant_prob=("dominant_prob", "mean"),
            avg_prob_entropy=("prob_entropy", "mean"),
        )
        .reset_index()
        .sort_values("n", ascending=False)
    )

    year_probs = panel.groupby("year")[prob_cols + ["dominant_prob", "prob_entropy"]].mean()
    year_probs = year_probs.reset_index()
    year_share = pd.crosstab(panel["year"], panel["dominant_regime"], normalize="index")
    year_share = year_share.reset_index()

    confusion_counts = pd.crosstab(panel["dominant_regime"], panel["expost_label"])
    confusion_row_pct = pd.crosstab(
        panel["dominant_regime"], panel["expost_label"], normalize="index"
    )

    ordered = panel.sort_values(["year", "trade_date"]).copy()
    ordered["prev_dominant_regime"] = ordered.groupby("year")["dominant_regime"].shift(1)
    transitions = ordered.dropna(subset=["prev_dominant_regime"])
    transition_row_pct = pd.crosstab(
        transitions["prev_dominant_regime"],
        transitions["dominant_regime"],
        normalize="index",
    )

    corr_rows = []
    for col in prob_cols:
        corr_rows.append(
            {
                "prob_col": col,
                "corr_forward_return": panel[col].corr(panel["benchmark_return"]),
                "corr_abs_forward_return": panel[col].corr(panel["benchmark_return"].abs()),
            }
        )
    corr = pd.DataFrame(corr_rows)

    if by_dom.empty:
        return_spread = float("nan")
    else:
        return_spread = float(
            by_dom["mean_forward_return"].max() - by_dom["mean_forward_return"].min()
        )

    all_abs_mean = float(panel["benchmark_return"].abs().mean())
    high_vol_abs = by_dom.loc[
        by_dom["dominant_regime"] == "high_volatility", "mean_abs_forward_return"
    ]
    high_vol_abs_lift = (
        float(high_vol_abs.iloc[0] / all_abs_mean - 1.0)
        if not high_vol_abs.empty and all_abs_mean > 0
        else float("nan")
    )

    summary = {
        "n_periods": int(len(panel)),
        "years": [int(x) for x in sorted(panel["year"].unique())],
        "n_dominant_regimes": int(panel["dominant_regime"].nunique()),
        "dominant_regime_counts": {
            str(k): int(v) for k, v in dominant_counts.to_dict().items()
        },
        "range_bound_dominant_share": range_bound_share,
        "avg_dominant_prob": float(panel["dominant_prob"].mean()),
        "avg_prob_entropy_0_to_1": float(panel["prob_entropy"].mean()),
        "simple_expost_accuracy_all": accuracy_all,
        "simple_expost_accuracy_comparable": accuracy_comparable,
        "mean_forward_return_spread_by_dominant": return_spread,
        "high_vol_abs_return_lift_vs_all": high_vol_abs_lift,
        "status": classify_status(
            accuracy_comparable=accuracy_comparable,
            return_spread=return_spread,
            range_bound_share=range_bound_share,
            high_vol_abs_lift=high_vol_abs_lift,
        ),
    }

    return {
        "summary": summary,
        "dominant_forward_returns": by_dom,
        "year_regime_probs": year_probs,
        "year_dominant_share": year_share,
        "confusion_counts": confusion_counts,
        "confusion_row_pct": confusion_row_pct,
        "transition_row_pct": transition_row_pct,
        "probability_correlations": corr,
    }


def classify_status(
    accuracy_comparable: float,
    return_spread: float,
    range_bound_share: float,
    high_vol_abs_lift: float,
) -> str:
    """Coarse diagnostic status, not an investment decision."""
    weak_flags = 0
    if pd.isna(accuracy_comparable) or accuracy_comparable < 0.40:
        weak_flags += 1
    if pd.isna(return_spread) or return_spread < 0.01:
        weak_flags += 1
    if pd.isna(range_bound_share) or range_bound_share > 0.50:
        weak_flags += 1
    if pd.isna(high_vol_abs_lift) or high_vol_abs_lift < 0.10:
        weak_flags += 1

    if weak_flags >= 3:
        return "WEAK"
    if weak_flags >= 1:
        return "PARTIAL"
    return "PASS"


def write_report(
    out_dir: Path,
    panel: pd.DataFrame,
    thresholds: dict[str, float],
    outputs: dict[str, Any],
    artifacts: list[RunArtifact],
    run_id_contains: str | None,
) -> None:
    """Persist CSV/JSON/Markdown outputs."""
    out_dir.mkdir(parents=True, exist_ok=True)

    summary = outputs["summary"]
    panel.to_csv(out_dir / "regime_prediction_panel.csv", index=False)
    outputs["dominant_forward_returns"].to_csv(
        out_dir / "dominant_regime_forward_returns.csv", index=False
    )
    outputs["year_regime_probs"].to_csv(out_dir / "year_regime_probs.csv", index=False)
    outputs["year_dominant_share"].to_csv(out_dir / "year_dominant_share.csv", index=False)
    outputs["confusion_counts"].to_csv(out_dir / "confusion_matrix_counts.csv")
    outputs["confusion_row_pct"].to_csv(out_dir / "confusion_matrix_row_pct.csv")
    outputs["transition_row_pct"].to_csv(out_dir / "transition_matrix_row_pct.csv")
    outputs["probability_correlations"].to_csv(
        out_dir / "probability_correlations.csv", index=False
    )

    with open(out_dir / "summary_metrics.json", "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, ensure_ascii=False)

    manifest = {
        "schema": "regime_predictiveness_manifest.v1",
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "run_id_contains": run_id_contains,
        "thresholds": thresholds,
        "artifacts": [
            {
                "year": a.year,
                "run_dir": str(a.run_dir),
                "regime_probs_path": str(a.regime_probs_path),
                "benchmark_returns_path": str(a.benchmark_returns_path),
            }
            for a in artifacts
        ],
        "output_files": {
            p.name: str(p)
            for p in sorted(out_dir.iterdir())
            if p.is_file() and p.name != "manifest.json"
        },
    }
    with open(out_dir / "manifest.json", "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, ensure_ascii=False)

    report = build_markdown_report(summary, thresholds, outputs, artifacts)
    (out_dir / "regime_predictiveness_report.md").write_text(report, encoding="utf-8")


def build_markdown_report(
    summary: dict[str, Any],
    thresholds: dict[str, float],
    outputs: dict[str, Any],
    artifacts: list[RunArtifact],
) -> str:
    by_dom = outputs["dominant_forward_returns"].copy()
    corr = outputs["probability_correlations"].copy()
    year_share = outputs["year_dominant_share"].copy()
    confusion = outputs["confusion_row_pct"].copy()

    lines = [
        "# Regime Predictiveness Evaluation",
        "",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## Inputs",
        "",
        f"- Years: {summary['years']}",
        f"- Periods: {summary['n_periods']}",
        f"- Runs: {len(artifacts)}",
        "",
        "## Ex-Post Label Thresholds",
        "",
        f"- trend_up: forward benchmark return >= {_pct(thresholds['return_q67'], 2)}",
        f"- trend_down: forward benchmark return <= {_pct(thresholds['return_q33'], 2)}",
        f"- high_volatility: abs(forward benchmark return) >= {_pct(thresholds['abs_return_q75'], 2)}",
        "",
        "## Summary",
        "",
        f"- Diagnostic status: **{summary['status']}**",
        f"- Simple ex-post accuracy: {_pct(summary['simple_expost_accuracy_comparable'], 1)}",
        f"- Range-bound dominant share: {_pct(summary['range_bound_dominant_share'], 1)}",
        f"- Mean dominant probability: {_pct(summary['avg_dominant_prob'], 1)}",
        f"- Mean normalized entropy: {_pct(summary['avg_prob_entropy_0_to_1'], 1)}",
        f"- Mean forward return spread by dominant regime: {_pct(summary['mean_forward_return_spread_by_dominant'], 2)}",
        f"- High-vol abs-return lift vs all: {_pct(summary['high_vol_abs_return_lift_vs_all'], 1)}",
        "",
        "## Forward Benchmark Return By Dominant Regime",
        "",
        by_dom.to_markdown(index=False, floatfmt=".4f"),
        "",
        "## Yearly Dominant Regime Share",
        "",
        year_share.to_markdown(index=False, floatfmt=".3f"),
        "",
        "## Confusion Matrix Row Percent",
        "",
        confusion.reset_index().to_markdown(index=False, floatfmt=".3f"),
        "",
        "## Probability Correlations",
        "",
        corr.to_markdown(index=False, floatfmt=".4f"),
        "",
        "## Interpretation",
        "",
        "- This is a detector diagnostic, not an investment gate.",
        "- A stronger detector should lower range-bound dominance, improve simple ex-post accuracy,",
        "  and make high_volatility probability more aligned with forward absolute returns.",
        "- Use this report as a before/after baseline for RegimeDetector changes.",
        "",
    ]
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-root", default=str(ROOT / "outputs" / "runs"))
    parser.add_argument("--start-year", type=int, default=2017)
    parser.add_argument("--end-year", type=int, default=2024)
    parser.add_argument(
        "--run-id-contains",
        default="20260615",
        help=(
            "Only use run directories containing this string. Use an empty string "
            "to select the latest available annual run for each year."
        ),
    )
    parser.add_argument(
        "--output-root",
        default=str(ROOT / "outputs" / "analysis" / "regime_predictiveness"),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run_filter = args.run_id_contains or None
    artifacts = discover_run_artifacts(
        runs_root=Path(args.runs_root),
        start_year=args.start_year,
        end_year=args.end_year,
        run_id_contains=run_filter,
    )
    if not artifacts:
        print("No matching regime diagnostic artifacts found.", file=sys.stderr)
        return 2

    panel = load_prediction_panel(artifacts)
    if panel.empty:
        print("No aligned regime/benchmark rows found.", file=sys.stderr)
        return 2

    panel, thresholds = add_expost_labels(panel)
    outputs = compute_outputs(panel)

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.output_root) / run_id
    write_report(
        out_dir=out_dir,
        panel=panel,
        thresholds=thresholds,
        outputs=outputs,
        artifacts=artifacts,
        run_id_contains=run_filter,
    )

    summary = outputs["summary"]
    print(f"Output: {out_dir}")
    print(f"Status: {summary['status']}")
    print(f"Periods: {summary['n_periods']}")
    print(f"Simple ex-post accuracy: {_pct(summary['simple_expost_accuracy_comparable'], 1)}")
    print(f"Range-bound dominant share: {_pct(summary['range_bound_dominant_share'], 1)}")
    print(f"High-vol abs-return lift: {_pct(summary['high_vol_abs_return_lift_vs_all'], 1)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

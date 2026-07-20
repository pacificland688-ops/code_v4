#!/usr/bin/env python
"""
Generate go_nogo_decision.md from frozen backtest run CSVs.

Reads:
  - outputs/validation/frozen_backtest/runs.csv
  - outputs/validation/candidate_v2/runs.csv (if available)

Writes:
  - docs/go_nogo_decision.md (auto-generated, no hand-edited numbers)

Principle: All tables are generated from metrics — no manual number maintenance.
"""

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

# Hard GO/NO-GO thresholds (from strategy_next_development_plan.md §6)
THRESHOLDS = {
    "avg_annualized_excess_return": 0.02,
    "median_annualized_excess_return": 0.0,
    "min_positive_excess_years": 5,
    "avg_ir": 0.30,
    "max_single_year_excess_loss": -0.10,
}

# Required year coverage for formal GO/NO-GO decision
REQUIRED_VALIDATION_YEARS = list(range(2017, 2025))  # 2017-2024
REQUIRED_YTD_YEARS = [2026]
REQUIRED_CANDIDATE_STRATEGIES = ["E_candidate_v2", "F_candidate_v3", "G_candidate_v4_r1", "G_candidate_v4_r2"]

METRIC_COLS = [
    "strategy",
    "year",
    "annualized_return",
    "annualized_excess_return",
    "information_ratio",
    "max_drawdown",
    "avg_turnover",
    "sharpe_ratio",
    "total_cost_bps",
    "n_periods",
]


def _fmt_pct(value, digits=1):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return f"{float(value) * 100:.{digits}f}%"


def _fmt_num(value, digits=2):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return f"{float(value):.{digits}f}"


def load_runs(csv_paths: List[Path]) -> pd.DataFrame:
    """Load and merge run CSVs."""
    dfs = []
    for p in csv_paths:
        if p.exists():
            df = pd.read_csv(p)
            dfs.append(df)
    if not dfs:
        raise FileNotFoundError("No runs.csv files found")
    return pd.concat(dfs, ignore_index=True)


def check_completeness(
    df: pd.DataFrame,
    candidate_strategies: List[str],
    required_validation_years: Optional[List[int]] = None,
    required_ytd_years: Optional[List[int]] = None,
) -> Dict[str, Any]:
    """Check if the loaded runs cover all required years for each candidate.

    Returns dict with:
      - is_complete: bool
      - issues: list of issue description strings
      - missing_validation: dict mapping strategy -> list of missing years
      - missing_ytd: dict mapping strategy -> list of missing ytd years
    """
    if required_validation_years is None:
        required_validation_years = REQUIRED_VALIDATION_YEARS
    if required_ytd_years is None:
        required_ytd_years = REQUIRED_YTD_YEARS

    issues = []
    missing_validation: Dict[str, List[int]] = {}
    missing_ytd: Dict[str, List[int]] = {}

    for strategy in candidate_strategies:
        strat_data = df[df["strategy"] == strategy]
        if strat_data.empty:
            issues.append(f"{strategy}: no runs found")
            missing_validation[strategy] = list(required_validation_years)
            missing_ytd[strategy] = list(required_ytd_years)
            continue

        # Check validation years
        present_validation = set(
            strat_data[strat_data["sample"] == "validation"]["year"].unique()
        )
        missing_val = sorted(set(required_validation_years) - present_validation)
        if missing_val:
            missing_validation[strategy] = missing_val
            issues.append(
                f"{strategy}: missing validation years: {missing_val}"
            )

        # Check YTD years
        present_ytd = set(
            strat_data[strat_data["sample"] == "ytd"]["year"].unique()
        )
        missing_yt = sorted(set(required_ytd_years) - present_ytd)
        if missing_yt:
            missing_ytd[strategy] = missing_yt
            issues.append(
                f"{strategy}: missing ytd years: {missing_yt}"
            )

    is_complete = len(issues) == 0
    return {
        "is_complete": is_complete,
        "issues": issues,
        "missing_validation": missing_validation,
        "missing_ytd": missing_ytd,
    }


def compute_summary(df: pd.DataFrame, strategy: str, sample: str = "validation") -> Dict:
    """Compute summary metrics for a strategy across validation years."""
    subset = df[(df["strategy"] == strategy) & (df["sample"] == sample)]
    if subset.empty:
        return {}

    excess = subset["annualized_excess_return"].dropna()
    if excess.empty:
        return {}

    ir = subset["information_ratio"].dropna()
    turnover = subset["avg_turnover"].dropna()
    max_dd = subset["max_drawdown"].dropna()

    return {
        "n_years": len(excess),
        "avg_ann_return": float(subset["annualized_return"].mean()),
        "avg_excess": float(excess.mean()),
        "median_excess": float(excess.median()),
        "pos_excess_years": int((excess > 0).sum()),
        "pos_return_years": int((subset["annualized_return"] > 0).sum()),
        "avg_ir": float(ir.mean()) if not ir.empty else None,
        "avg_turnover": float(turnover.mean()) if not turnover.empty else None,
        "avg_max_drawdown": float(max_dd.mean()) if not max_dd.empty else None,
        "worst_max_drawdown": float(max_dd.min()) if not max_dd.empty else None,
        "min_excess": float(excess.min()),
        "max_excess": float(excess.max()),
        "worst_year": int(subset.loc[excess.idxmin(), "year"]) if len(excess) > 0 else None,
        "best_year": int(subset.loc[excess.idxmax(), "year"]) if len(excess) > 0 else None,
    }


def evaluate_thresholds(summary: Dict) -> Dict[str, bool]:
    """Check a strategy summary against GO/NO-GO thresholds."""
    checks = {}
    checks["avg_excess > 2%"] = summary.get("avg_excess", -99) > THRESHOLDS["avg_annualized_excess_return"]
    checks["median_excess > 0%"] = summary.get("median_excess", -99) > THRESHOLDS["median_annualized_excess_return"]
    checks["pos_excess_years >= 5"] = summary.get("pos_excess_years", 0) >= THRESHOLDS["min_positive_excess_years"]
    checks["avg_ir > 0.30"] = (summary.get("avg_ir") or -99) > THRESHOLDS["avg_ir"]
    checks["max_excess_loss > -10%"] = summary.get("min_excess", -99) > THRESHOLDS["max_single_year_excess_loss"]
    return checks


def write_report(
    df: pd.DataFrame,
    out_path: Path,
    base_strategies: List[str],
    candidate_strategies: List[str],
    allow_incomplete: bool = False,
    required_validation_years: Optional[List[int]] = None,
    required_ytd_years: Optional[List[int]] = None,
) -> None:
    """Write the GO/NO-GO decision document."""
    if required_validation_years is None:
        required_validation_years = REQUIRED_VALIDATION_YEARS
    if required_ytd_years is None:
        required_ytd_years = REQUIRED_YTD_YEARS

    lines = []

    # Check completeness before generating
    completeness = check_completeness(
        df, candidate_strategies,
        required_validation_years=required_validation_years,
        required_ytd_years=required_ytd_years,
    )
    is_incomplete = not completeness["is_complete"]

    if is_incomplete and not allow_incomplete:
        # Refuse to generate — print errors and exit
        print("ERROR: Cannot generate GO/NO-GO decision — data incomplete:")
        for issue in completeness["issues"]:
            print(f"  - {issue}")
        print()
        print("Required coverage:")
        print(f"  validation years: {required_validation_years}")
        print(f"  ytd years: {required_ytd_years}")
        print(f"  candidate strategies: {candidate_strategies}")
        print()
        print("To bypass this check for diagnostic purposes, use --allow-incomplete")
        raise SystemExit(1)

    if is_incomplete and allow_incomplete:
        title = "# GO / NO-GO Decision — Auto-Generated ⚠️ INCOMPLETE"
        lines.append(title)
    else:
        title = "# GO / NO-GO Decision — Auto-Generated"
        lines.append(title)

    lines.append("")
    lines.append(f"生成日期：{pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}  ")
    lines.append(f"生成脚本：`scripts/generate_go_nogo_decision.py`  ")
    lines.append("原则：所有指标从 runs.csv 生成，不手工维护。")
    if is_incomplete:
        lines.append("")
        lines.append("> ⚠️ **警告：此文档基于不完整数据生成，不可作为正式验收依据。**")
        lines.append("> 以下问题导致数据不完整：")
        for issue in completeness["issues"]:
            lines.append(f"> - {issue}")
    lines.append("")

    # ---- Section 1: Year-by-year comparison ----
    lines.append("## 1. 年度超额对比")
    lines.append("")

    all_strategies = base_strategies + candidate_strategies
    subset = df[df["strategy"].isin(all_strategies)]

    piv = subset.pivot_table(
        index="year",
        columns="strategy",
        values="annualized_excess_return",
        aggfunc="first",
    ).reset_index()

    # Format all excess columns as percentages
    for col in piv.columns:
        if col != "year":
            piv[col] = piv[col].apply(_fmt_pct)

    lines.append(piv.to_markdown(index=False))
    lines.append("")

    # ---- Section 2: Strategy summaries ----
    lines.append("## 2. 策略汇总")
    lines.append("")

    summary_rows = []
    for strategy in all_strategies:
        summary = compute_summary(subset, strategy)
        if not summary:
            continue
        checks = evaluate_thresholds(summary)
        all_pass = all(checks.values())

        summary_rows.append({
            "Strategy": strategy,
            "Avg Excess": _fmt_pct(summary.get("avg_excess")),
            "Median Excess": _fmt_pct(summary.get("median_excess")),
            "Pos Years": f"{summary.get('pos_excess_years', 0)}/{summary.get('n_years', 0)}",
            "Avg IR": _fmt_num(summary.get("avg_ir")),
            "Avg Turnover": _fmt_pct(summary.get("avg_turnover")),
            "Avg Max DD": _fmt_pct(summary.get("avg_max_drawdown")),
            "Worst Max DD": _fmt_pct(summary.get("worst_max_drawdown")),
            "GO?": "✅ GO" if all_pass else "❌ NO-GO",
        })

    summary_df = pd.DataFrame(summary_rows)
    lines.append(summary_df.to_markdown(index=False))
    lines.append("")

    # ---- Section 3: Threshold checks for candidates ----
    lines.append("## 3. GO/NO-GO 门槛检查")
    lines.append("")

    for strategy in candidate_strategies:
        summary = compute_summary(subset, strategy)
        if not summary:
            lines.append(f"### {strategy}: 无数据")
            lines.append("")
            continue

        checks = evaluate_thresholds(summary)
        lines.append(f"### {strategy}")
        lines.append("")
        lines.append("| 指标 | 门槛 | 实际值 | 通过？ |")
        lines.append("|------|------|--------|-------|")

        def _check_row(label, threshold, actual, passed):
            t_str = _fmt_pct(threshold) if "excess" in label.lower() or "loss" in label.lower() else _fmt_num(threshold)
            a_str = _fmt_pct(actual) if "excess" in label.lower() or "loss" in label.lower() else _fmt_num(actual)
            return f"| {label} | {t_str} | {a_str} | {'✅' if passed else '❌'} |"

        lines.append(_check_row("平均年化超额", THRESHOLDS["avg_annualized_excess_return"],
                                summary.get("avg_excess"), checks["avg_excess > 2%"]))
        lines.append(_check_row("中位数年化超额", THRESHOLDS["median_annualized_excess_return"],
                                summary.get("median_excess"), checks["median_excess > 0%"]))
        lines.append(_check_row("正超额年份", THRESHOLDS["min_positive_excess_years"],
                                summary.get("pos_excess_years"), checks["pos_excess_years >= 5"]))
        lines.append(_check_row("平均 IR", THRESHOLDS["avg_ir"],
                                summary.get("avg_ir"), checks["avg_ir > 0.30"]))
        lines.append(_check_row("最大单年超额亏损", THRESHOLDS["max_single_year_excess_loss"],
                                summary.get("min_excess"), checks["max_excess_loss > -10%"]))
        lines.append("")

        all_pass = all(checks.values())
        worst = summary.get("worst_year")
        best = summary.get("best_year")
        lines.append(f"**判决：{'GO' if all_pass else 'NO-GO'}**  ")
        lines.append(f"最差年份：{worst}，最佳年份：{best}  ")
        lines.append("")

    # ---- Section 4: YTD observation ----
    lines.append("## 4. 2026 YTD 前瞻观察")
    lines.append("")
    ytd = df[df["sample"] == "ytd"]
    if not ytd.empty:
        for strategy in candidate_strategies:
            s_ytd = ytd[ytd["strategy"] == strategy]
            if s_ytd.empty:
                continue
            row = s_ytd.iloc[0]
            lines.append(f"### {strategy}")
            lines.append("")
            lines.append("| 指标 | 值 |")
            lines.append("|------|----|")
            lines.append(f"| 年化收益 | {_fmt_pct(row.get('annualized_return'))} |")
            lines.append(f"| 年化超额 | {_fmt_pct(row.get('annualized_excess_return'))} |")
            lines.append(f"| IR | {_fmt_num(row.get('information_ratio'))} |")
            lines.append(f"| 最大回撤 | {_fmt_pct(row.get('max_drawdown'))} |")
            lines.append(f"| 平均换手 | {_fmt_pct(row.get('avg_turnover'))} |")
            lines.append(f"| 样本数 | {int(row.get('n_periods', 0))} |")
            lines.append(f"| 状态 | NO-GO / UNSTABLE |")
            lines.append("")
            lines.append("> ⚠️ 2026 YTD 样本不足，不纳入验证均值，不能用于调参，仅作前瞻观察。")
            lines.append("")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {out_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate GO/NO-GO decision document")
    parser.add_argument(
        "--runs", nargs="+",
        default=[
            "outputs/validation/frozen_backtest/runs.csv",
            "outputs/validation/candidate_v2/runs.csv",
        ],
        help="Path(s) to runs.csv"
    )
    parser.add_argument("--out", default="docs/go_nogo_decision.md")
    parser.add_argument(
        "--allow-incomplete", action="store_true", default=False,
        help="Allow generation with incomplete data (for diagnostic use only). "
             "Output will be clearly marked INCOMPLETE."
    )
    parser.add_argument(
        "--base-strategies", nargs="+",
        default=["A_5reversal", "B_dynamic", "C_regime_baseline", "D_regime_overlay"],
        help="Base/benchmark strategies for comparison."
    )
    parser.add_argument(
        "--candidate-strategies", nargs="+",
        default=["E_candidate_v2", "F_candidate_v3", "G_candidate_v4_r1", "G_candidate_v4_r2"],
        help="Candidate strategies to evaluate for GO/NO-GO."
    )
    parser.add_argument(
        "--required-validation-years", type=int, nargs="+",
        default=REQUIRED_VALIDATION_YEARS,
        help="Validation years required for formal decision."
    )
    parser.add_argument(
        "--required-ytd-years", type=int, nargs="+",
        default=REQUIRED_YTD_YEARS,
        help="YTD years for forward observation."
    )
    args = parser.parse_args()

    run_paths = [ROOT / p for p in args.runs]
    df = load_runs(run_paths)

    base_strategies = args.base_strategies
    candidate_strategies = args.candidate_strategies

    write_report(
        df, ROOT / args.out, base_strategies, candidate_strategies,
        allow_incomplete=args.allow_incomplete,
        required_validation_years=args.required_validation_years,
        required_ytd_years=args.required_ytd_years,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

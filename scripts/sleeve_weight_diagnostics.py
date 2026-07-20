"""Diagnose factor weights inside each strategy sleeve.

This is a diagnostic-only script. It does not search parameters and does not
change strategy configuration. The goal is to explain why a sleeve may fail
even when one raw factor looks useful.

Outputs:
* per-date ICWeighting factor weights inside each sleeve
* summary of average factor weights and signs
* Top-N selection exposure to each raw factor
* Phase1-vs-aligned IC reconciliation for value-factor mismatches
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from alpha.factor_gating import evaluate_factor_coverage_at_date
from alpha.ic_weighting import ICWeighting
from alpha.time_utils import calendar_month_lookback_start, matured_ic_cutoff
from sleeve_factor_attribution import (  # noqa: E402
    _build_sleeve_scores,
    _factor_score_panel,
    _fast_backtest_scores,
    _find_value_col,
    _load_phase2_row,
    _num,
    _pct,
    _realised_factor_ic,
    _summarise_periods,
)


def _load_config(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _signal_dates_from_aligned(aligned: dict[str, pd.DataFrame]) -> list[int]:
    dates: set[int] = set()
    for df in aligned.values():
        if df is not None and not df.empty and "trade_date" in df:
            dates.update(int(d) for d in df["trade_date"].dropna().unique())
    return sorted(dates)


def _sleeve_factors(config: dict[str, Any]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for sleeve, scfg in config.get("strategy_sleeves", {}).items():
        if isinstance(scfg, dict):
            factors = scfg.get("factors", [])
        else:
            factors = scfg
        if factors:
            result[sleeve] = list(factors)
    return result


def _eligible_names_for_date(
    factor_dfs: dict[str, pd.DataFrame],
    fwd_rets: pd.DataFrame,
    signal_date: int,
    composite_cfg: dict[str, Any],
    trade_dates: list[int],
    expected_dates: list[int],
) -> list[str]:
    if not composite_cfg.get("coverage_gate_enabled", False):
        return list(factor_dfs)

    lookback_months = composite_cfg.get(
        "min_date_coverage_lookback",
        composite_cfg.get("ic_window_months", 6),
    )
    passed: list[str] = []
    for name, df in factor_dfs.items():
        ok = evaluate_factor_coverage_at_date(
            factor_df=df,
            fwd_returns_df=fwd_rets,
            signal_date=signal_date,
            lookback_months=lookback_months,
            horizon=int(composite_cfg.get("horizon", 5)),
            trade_dates=trade_dates,
            min_date_coverage=composite_cfg.get("min_date_coverage", 0.70),
            min_stocks_per_date=composite_cfg.get("min_stocks_per_date", 30),
            min_merge_rate=composite_cfg.get("min_merge_rate", 0.30),
            expected_dates=expected_dates,
        )
        if ok:
            passed.append(name)
    return passed


def _ic_stats_for_factor(
    icw: ICWeighting,
    ic_df: pd.DataFrame,
    signal_date: int,
    factor_name: str,
    trade_dates: list[int],
) -> dict[str, Any]:
    cutoff = matured_ic_cutoff(signal_date, icw.horizon, trade_dates)
    lookback_start = calendar_month_lookback_start(
        signal_date, icw.ic_window_months
    )
    base = {
        "lookback_start": lookback_start,
        "ic_cutoff": cutoff,
        "n_obs": 0,
        "mean_ic": np.nan,
        "std_ic": np.nan,
        "icir": np.nan,
        "hit_rate": np.nan,
        "recent_mean_ic": np.nan,
        "sign_unstable": False,
        "below_min_icir": False,
        "skip_reason": "",
    }
    if cutoff is None or ic_df.empty:
        base["skip_reason"] = "no_matured_cutoff"
        return base

    ic_col = f"{factor_name}_ic"
    if ic_col not in ic_df.columns:
        base["skip_reason"] = "missing_ic_column"
        return base

    window = ic_df[
        (ic_df["trade_date"] <= cutoff)
        & (ic_df["trade_date"] >= lookback_start)
    ]
    series = window[ic_col].dropna()
    base["n_obs"] = int(len(series))
    if len(series) < icw.min_ic_obs:
        base["skip_reason"] = "insufficient_ic_obs"
        return base

    mean_ic = float(series.mean())
    std_ic = float(series.std(ddof=0))
    base["mean_ic"] = mean_ic
    base["std_ic"] = std_ic
    base["hit_rate"] = float((series > 0).mean())
    if std_ic == 0 or np.isnan(std_ic):
        base["skip_reason"] = "zero_or_nan_ic_std"
        return base

    icir = mean_ic / std_ic
    base["icir"] = float(icir)
    if icw.min_icir > 0 and abs(icir) < icw.min_icir:
        base["below_min_icir"] = True
        base["skip_reason"] = "below_min_icir"

    if icw.sign_stability_check and len(series) >= 10:
        n_recent = max(5, len(series) // 4)
        recent_mean = float(series.iloc[-n_recent:].mean())
        base["recent_mean_ic"] = recent_mean
        base["sign_unstable"] = bool(np.sign(mean_ic) != np.sign(recent_mean))

    return base


def _compute_weight_rows(
    config: dict[str, Any],
    aligned: dict[str, pd.DataFrame],
    fwd_rets: pd.DataFrame,
    signal_dates: list[int],
    analysis_start: int,
    analysis_end: int,
) -> pd.DataFrame:
    composite_cfg = dict(config.get("sleeve_composite", {}))
    horizon = int(composite_cfg.get("horizon", 5))
    trade_dates = sorted(
        int(d) for d in fwd_rets["trade_date"].dropna().unique()
    )
    rows: list[dict[str, Any]] = []

    for sleeve, factor_names in _sleeve_factors(config).items():
        sleeve_factor_dfs = {
            name: aligned[name]
            for name in factor_names
            if name in aligned and aligned[name] is not None and not aligned[name].empty
        }
        if not sleeve_factor_dfs:
            continue

        icw = ICWeighting(
            **composite_cfg,
            factor_whitelist=list(sleeve_factor_dfs),
        )
        ic_df = icw.compute_rolling_ic(
            sleeve_factor_dfs,
            fwd_rets,
            horizon=horizon,
        )

        for signal_date in signal_dates:
            eligible = _eligible_names_for_date(
                sleeve_factor_dfs,
                fwd_rets,
                signal_date,
                composite_cfg,
                trade_dates,
                signal_dates,
            )
            weights = icw.compute_weights(
                ic_df,
                signal_date,
                eligible_factor_names=eligible,
                trade_dates=trade_dates,
            )
            in_analysis_window = analysis_start <= signal_date <= analysis_end
            for factor_name in factor_names:
                stats = _ic_stats_for_factor(
                    icw, ic_df, signal_date, factor_name, trade_dates
                )
                if factor_name not in eligible:
                    stats["skip_reason"] = "failed_coverage_gate"
                elif factor_name not in weights and not stats["skip_reason"]:
                    stats["skip_reason"] = "not_in_final_weights"

                weight = float(weights.get(factor_name, 0.0))
                rows.append({
                    "sleeve": sleeve,
                    "signal_date": signal_date,
                    "month": signal_date // 100,
                    "factor": factor_name,
                    "in_analysis_window": in_analysis_window,
                    "eligible": factor_name in eligible,
                    "has_weight": factor_name in weights,
                    "weight": weight,
                    "abs_weight": abs(weight),
                    **stats,
                })

    return pd.DataFrame(rows)


def _summarise_weights(weight_rows: pd.DataFrame) -> pd.DataFrame:
    if weight_rows.empty:
        return pd.DataFrame()
    df = weight_rows[weight_rows["in_analysis_window"]].copy()
    if df.empty:
        return pd.DataFrame()

    def _rate(mask: pd.Series) -> float:
        return float(mask.mean()) if len(mask) else np.nan

    summary = (
        df.groupby(["sleeve", "factor"], dropna=False)
        .agg(
            n_dates=("signal_date", "nunique"),
            eligible_rate=("eligible", "mean"),
            active_rate=("has_weight", "mean"),
            avg_weight=("weight", "mean"),
            avg_abs_weight=("abs_weight", "mean"),
            positive_weight_rate=("weight", lambda s: _rate(s > 0)),
            negative_weight_rate=("weight", lambda s: _rate(s < 0)),
            avg_mean_ic=("mean_ic", "mean"),
            avg_icir=("icir", "mean"),
            avg_hit_rate=("hit_rate", "mean"),
            sign_unstable_rate=("sign_unstable", "mean"),
            below_min_icir_rate=("below_min_icir", "mean"),
        )
        .reset_index()
        .sort_values(["sleeve", "avg_abs_weight"], ascending=[True, False])
    )
    return summary


def _monthly_weight_summary(weight_rows: pd.DataFrame) -> pd.DataFrame:
    if weight_rows.empty:
        return pd.DataFrame()
    df = weight_rows[weight_rows["in_analysis_window"]].copy()
    if df.empty:
        return pd.DataFrame()
    return (
        df.groupby(["month", "sleeve", "factor"], dropna=False)
        .agg(
            avg_weight=("weight", "mean"),
            avg_abs_weight=("abs_weight", "mean"),
            active_rate=("has_weight", "mean"),
            avg_icir=("icir", "mean"),
        )
        .reset_index()
        .sort_values(["month", "sleeve", "factor"])
    )


def _selection_exposure_rows(
    config: dict[str, Any],
    sleeve_scores: dict[str, pd.DataFrame],
    aligned: dict[str, pd.DataFrame],
    analysis_start: int,
    analysis_end: int,
    top_n: int,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for sleeve, factor_names in _sleeve_factors(config).items():
        scores = sleeve_scores.get(sleeve)
        if scores is None or scores.empty:
            continue
        dates = sorted(
            int(d)
            for d in scores.loc[
                (scores["trade_date"] >= analysis_start)
                & (scores["trade_date"] <= analysis_end),
                "trade_date",
            ].unique()
        )
        for signal_date in dates:
            day_scores = scores[scores["trade_date"] == signal_date]
            selected = set(
                day_scores.sort_values("composite_score", ascending=False)
                .drop_duplicates("ts_code")
                .head(top_n)["ts_code"]
                .tolist()
            )
            if not selected:
                continue
            for factor_name in factor_names:
                fdf = aligned.get(factor_name)
                if fdf is None or fdf.empty:
                    continue
                value_col = _find_value_col(fdf, factor_name)
                if value_col is None:
                    continue
                day = fdf[fdf["trade_date"] == signal_date][
                    ["ts_code", value_col]
                ].dropna()
                if day.empty:
                    continue
                selected_day = day[day["ts_code"].isin(selected)]
                if selected_day.empty:
                    continue
                universe_mean = float(day[value_col].mean())
                selected_mean = float(selected_day[value_col].mean())
                rows.append({
                    "sleeve": sleeve,
                    "signal_date": signal_date,
                    "month": signal_date // 100,
                    "factor": factor_name,
                    "selected_n": int(len(selected_day)),
                    "universe_n": int(len(day)),
                    "selected_mean": selected_mean,
                    "universe_mean": universe_mean,
                    "selected_minus_universe": selected_mean - universe_mean,
                })
    return pd.DataFrame(rows)


def _summarise_exposure(exposures: pd.DataFrame) -> pd.DataFrame:
    if exposures.empty:
        return pd.DataFrame()
    return (
        exposures.groupby(["sleeve", "factor"], dropna=False)
        .agg(
            n_dates=("signal_date", "nunique"),
            avg_selected_mean=("selected_mean", "mean"),
            avg_selected_minus_universe=("selected_minus_universe", "mean"),
            positive_exposure_rate=(
                "selected_minus_universe",
                lambda s: float((s > 0).mean()),
            ),
            avg_selected_n=("selected_n", "mean"),
        )
        .reset_index()
        .sort_values(
            ["sleeve", "avg_selected_minus_universe"],
            ascending=[True, False],
        )
    )


def _find_phase1_log(start: str) -> Path | None:
    """Find the closest segmented Phase1 log for a window's start year."""
    year = str(start)[:4]
    base = Path("outputs/segmented_validate")
    if not base.exists():
        return None
    candidates = sorted(base.glob(f"phase1_{year}*.out.log"))
    if not candidates:
        return None
    return candidates[-1]


def _parse_phase1_log(path: Path | None) -> pd.DataFrame:
    if path is None or not path.exists():
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    pattern = re.compile(
        r"^\|\s*\d+\s*\|\s*([^|]+?)\s*\|\s*([-0-9.]+)\s*\|\s*([-0-9.]+)"
        r"\s*\|\s*([-0-9.]+)%"
    )
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        match = pattern.match(line.strip())
        if not match:
            continue
        factor, mean_ic, icir, pos_rate = match.groups()
        rows.append({
            "factor": factor.strip(),
            "phase1_mean_ic": float(mean_ic),
            "phase1_icir": float(icir),
            "phase1_hit_rate": float(pos_rate) / 100.0,
        })
    return pd.DataFrame(rows).drop_duplicates("factor")


def _reconcile_ic(
    phase1_log: Path | None,
    factor_ic_path: Path,
    factor_top_bottom_path: Path,
) -> pd.DataFrame:
    phase1 = _parse_phase1_log(phase1_log)
    aligned_ic = pd.read_csv(factor_ic_path) if factor_ic_path.exists() else pd.DataFrame()
    top_bottom = (
        pd.read_csv(factor_top_bottom_path)
        if factor_top_bottom_path.exists()
        else pd.DataFrame()
    )

    if phase1.empty:
        phase1 = pd.DataFrame(columns=[
            "factor",
            "phase1_mean_ic",
            "phase1_icir",
            "phase1_hit_rate",
        ])

    if aligned_ic.empty:
        aligned_ic = pd.DataFrame(columns=[
            "factor",
            "aligned_ic_dates",
            "aligned_mean_ic",
            "aligned_icir",
            "aligned_hit_rate",
        ])

    if top_bottom.empty:
        top_bottom = pd.DataFrame(columns=[
            "factor",
            "top_excess",
            "bottom_excess",
            "top_minus_bottom_excess",
        ])

    if phase1.empty and aligned_ic.empty and top_bottom.empty:
        return pd.DataFrame()

    if not aligned_ic.empty:
        aligned_ic = aligned_ic.rename(columns={
            "mean_ic": "aligned_mean_ic",
            "icir": "aligned_icir",
            "hit_rate": "aligned_hit_rate",
            "ic_dates": "aligned_ic_dates",
        })
    if not top_bottom.empty:
        top_bottom = top_bottom[[
            "factor",
            "top_excess",
            "bottom_excess",
            "top_minus_bottom_excess",
        ]]

    out = phase1.merge(aligned_ic, on="factor", how="outer")
    if not top_bottom.empty:
        out = out.merge(top_bottom, on="factor", how="left")
    return out.sort_values("factor")


def _factor_to_sleeves(config: dict[str, Any]) -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = {}
    for sleeve, factors in _sleeve_factors(config).items():
        for factor in factors:
            mapping.setdefault(factor, []).append(sleeve)
    return mapping


def _compute_factor_diagnostics(
    aligned: dict[str, pd.DataFrame],
    fwd_rets: pd.DataFrame,
    config: dict[str, Any],
    start: str,
    end: str,
    horizon: int,
    top_n: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Compute raw-factor Top/Bottom and aligned realised IC diagnostics."""
    factor_to_sleeves = _factor_to_sleeves(config)
    factor_rows: list[dict[str, Any]] = []
    ic_rows: list[dict[str, Any]] = []

    for factor in sorted(aligned):
        fdf = aligned[factor]
        if fdf is None or fdf.empty:
            continue
        top_scores = _factor_score_panel(factor, fdf, sign=1.0)
        bottom_scores = _factor_score_panel(factor, fdf, sign=-1.0)
        top_periods = _fast_backtest_scores(top_scores, start, end, top_n)
        bottom_periods = _fast_backtest_scores(bottom_scores, start, end, top_n)
        top_summary = _summarise_periods(factor, top_periods, "factor_top")
        bottom_summary = _summarise_periods(factor, bottom_periods, "factor_bottom")
        factor_rows.append({
            "factor": factor,
            "sleeves": ",".join(factor_to_sleeves.get(factor, [])),
            "top_return": top_summary["annualized_return"],
            "top_excess": top_summary["annualized_excess_return"],
            "top_ir": top_summary["information_ratio"],
            "bottom_return": bottom_summary["annualized_return"],
            "bottom_excess": bottom_summary["annualized_excess_return"],
            "bottom_ir": bottom_summary["information_ratio"],
            "top_minus_bottom_excess": (
                top_summary["annualized_excess_return"]
                - bottom_summary["annualized_excess_return"]
            ),
            "top_n_periods": top_summary["n_periods"],
            "bottom_n_periods": bottom_summary["n_periods"],
        })
        ic_rows.append(_realised_factor_ic(
            factor, fdf, fwd_rets, start, end, horizon=horizon,
        ))

    return pd.DataFrame(factor_rows), pd.DataFrame(ic_rows)


def _fmt_float(value: Any, digits: int = 3) -> str:
    if value is None or pd.isna(value):
        return ""
    return f"{float(value):.{digits}f}"


def _write_report(
    out_doc: Path,
    meta: dict[str, Any],
    weight_summary: pd.DataFrame,
    exposure_summary: pd.DataFrame,
    ic_reconcile: pd.DataFrame,
    factor_top_bottom: pd.DataFrame,
) -> None:
    start = str(meta.get("start", ""))
    end = str(meta.get("end", ""))
    window = f"{start}-{end}" if start and end else "unknown window"
    lines: list[str] = []
    lines.append(f"# Sleeve 内部权重诊断：{window}")
    lines.append("")
    lines.append("## 边界")
    lines.append("")
    lines.append(f"- 固定使用配置 `{meta.get('config_path', '')}`。")
    lines.append("- 只重算 sleeve 内部 IC 权重和选股暴露，不搜索参数、不改配置。")
    lines.append("- 权重使用 `matured_ic_cutoff()`，只看 forward return 已成熟的历史 IC。")
    lines.append("- 当前窗口结果只用于诊断，不作为直接调参或反向因子的依据。")
    lines.append("")
    lines.append("## 样本")
    lines.append("")
    lines.append(f"- Window: `{meta.get('start')}-{meta.get('end')}`")
    lines.append(f"- Data window: `{meta.get('data_start')}-{meta.get('data_end')}`")
    lines.append(f"- Target signal dates: {meta.get('target_signal_dates')}")
    lines.append(f"- Scoring signal dates: {meta.get('scoring_signal_dates')}")
    lines.append("")

    lines.append("## Sleeve 内部因子权重")
    lines.append("")
    if weight_summary.empty:
        lines.append("无可用权重诊断。")
    else:
        lines.append(
            "| Sleeve | Factor | 活跃率 | 平均权重 | 平均绝对权重 | 正权重率 | "
            "负权重率 | 平均ICIR | ICIR低于门槛率 | 方向不稳率 |"
        )
        lines.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|")
        for _, r in weight_summary.iterrows():
            lines.append(
                f"| {r['sleeve']} | {r['factor']} | {_pct(r['active_rate'])} | "
                f"{_fmt_float(r['avg_weight'])} | {_fmt_float(r['avg_abs_weight'])} | "
                f"{_pct(r['positive_weight_rate'])} | {_pct(r['negative_weight_rate'])} | "
                f"{_fmt_float(r['avg_icir'])} | {_pct(r['below_min_icir_rate'])} | "
                f"{_pct(r['sign_unstable_rate'])} |"
            )
    lines.append("")

    lines.append("## Top50 选股暴露")
    lines.append("")
    if exposure_summary.empty:
        lines.append("无可用选股暴露诊断。")
    else:
        lines.append(
            "| Sleeve | Factor | 平均选中暴露 | 相对全域暴露 | 正暴露率 | 平均有效持仓数 |"
        )
        lines.append("|---|---|---:|---:|---:|---:|")
        for _, r in exposure_summary.iterrows():
            lines.append(
                f"| {r['sleeve']} | {r['factor']} | "
                f"{_fmt_float(r['avg_selected_mean'])} | "
                f"{_fmt_float(r['avg_selected_minus_universe'])} | "
                f"{_pct(r['positive_exposure_rate'])} | "
                f"{_fmt_float(r['avg_selected_n'], 1)} |"
            )
    lines.append("")

    lines.append("## Phase1 与 Aligned IC 口径对照")
    lines.append("")
    lines.append(
        "这里专门核对 value 因子的矛盾：旧 Phase1 日志是直接用当期因子面板"
        "与 `fwd_ret_5d` 做全样本日频/原始面板评估；regime 诊断使用 weekly "
        "as-of aligned 因子、coverage gate、warmup 后的目标信号日。"
    )
    lines.append("")
    if ic_reconcile.empty:
        lines.append("未找到可对照的 Phase1 日志或 aligned IC 结果。")
    else:
        focus = ic_reconcile[
            ic_reconcile["factor"].isin(
                ["ep_cs", "bp_cs", "sp_cs", "momentum_60_cs", "momentum_120_cs"]
            )
        ]
        lines.append(
            "| Factor | Phase1 Mean IC | Phase1 ICIR | Phase1正IC率 | "
            "Aligned Mean IC | Aligned ICIR | Aligned正IC率 | Top-Bottom超额 |"
        )
        lines.append("|---|---:|---:|---:|---:|---:|---:|---:|")
        for _, r in focus.iterrows():
            lines.append(
                f"| {r['factor']} | {_fmt_float(r.get('phase1_mean_ic'))} | "
                f"{_fmt_float(r.get('phase1_icir'))} | {_pct(r.get('phase1_hit_rate'))} | "
                f"{_fmt_float(r.get('aligned_mean_ic'))} | "
                f"{_fmt_float(r.get('aligned_icir'))} | "
                f"{_pct(r.get('aligned_hit_rate'))} | "
                f"{_pct(r.get('top_minus_bottom_excess'))} |"
            )
    lines.append("")

    lines.append("## 诊断判断")
    lines.append("")
    if not factor_top_bottom.empty:
        mtm = factor_top_bottom[
            factor_top_bottom["factor"].isin(["momentum_60_cs", "momentum_120_cs"])
        ]
        if not mtm.empty:
            best = mtm.sort_values("top_minus_bottom_excess", ascending=False).iloc[0]
            lines.append(
                f"- 单因子层面最值得关注的是 `{best['factor']}`，"
                f"Top-Bottom 年化超额 {_pct(best['top_minus_bottom_excess'])}。"
            )
    if not weight_summary.empty:
        m60 = weight_summary[
            (weight_summary["sleeve"] == "momentum")
            & (weight_summary["factor"] == "momentum_60_cs")
        ]
        if not m60.empty:
            r = m60.iloc[0]
            lines.append(
                f"- 在 momentum sleeve 内，`momentum_60_cs` 平均权重 "
                f"{_fmt_float(r['avg_weight'])}，活跃率 {_pct(r['active_rate'])}，"
                f"平均 ICIR {_fmt_float(r['avg_icir'])}。"
            )
        value = weight_summary[weight_summary["sleeve"] == "value"]
        if not value.empty:
            top_value = value.sort_values("avg_abs_weight", ascending=False).iloc[0]
            lines.append(
                f"- value sleeve 中绝对权重最高的是 `{top_value['factor']}`，"
                f"平均权重 {_fmt_float(top_value['avg_weight'])}，"
                f"但这只说明历史滚动 IC 权重如何下注，不等于当前窗口 Top50 经济收益有效。"
            )
    lines.append("- 结论仍保持保守：先解释权重和口径差异，再决定是否做跨年份 OOS 假设检验。")
    lines.append("")

    lines.append("## 下一步验证方案")
    lines.append("")
    lines.append("先把单窗口诊断转成冻结假设，再跨年份验证，避免用失败年份直接调参：")
    lines.append("")
    lines.append(
        "1. **H1：momentum sleeve 失败来自内部权重方向错配。** "
        "`momentum_60_cs` raw Top50 有效，但当前滚动 IC 权重多数时间给负权重；"
        "下一步只验证这个现象是否跨年份反复出现。"
    )
    lines.append(
        "2. **H2：value 因子的 Phase1 强 IC 不等于 weekly aligned Top50 alpha。** "
        "先复现 Phase1 与 aligned 两套口径的差异来源，再决定 value sleeve 是否需要改造。"
    )
    lines.append(
        "3. **H3：不要基于 2025 单年反向因子。** "
        "任何方向约束、窗口调整、因子剔除都必须先写成固定候选配置，再用未参与设计的年份验证。"
    )
    lines.append("")
    lines.append("建议的下一批只读验证：")
    lines.append("")
    lines.append("- 将本脚本扩展到 `2017-2024` 和 `2026 YTD`，输出同样的 weight/exposure/reconciliation 表。")
    lines.append("- 对每一年检查 `momentum_60_cs` 的 raw Top-Bottom 与 sleeve 内平均权重方向是否一致。")
    lines.append("- 对 value 因子检查 Phase1 原始面板 IC、weekly aligned IC、Top50 经济收益三者是否稳定同向。")
    lines.append("- 只有当错配跨多年成立，才进入候选策略开发；否则继续停留在诊断层。")

    out_doc.parent.mkdir(parents=True, exist_ok=True)
    out_doc.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--runs-csv",
        default="outputs/analysis/regime_grid_overlay_phase2_2025/runs.csv",
        help="Legacy mode: load config/start/end from a successful grid row.",
    )
    parser.add_argument("--case", default="less_reversal_faster_overlay")
    parser.add_argument(
        "--config-path",
        default=None,
        help="Regime config path. If provided, --start and --end are required.",
    )
    parser.add_argument("--start", default=None, help="Analysis start date YYYYMMDD.")
    parser.add_argument("--end", default=None, help="Analysis end date YYYYMMDD.")
    parser.add_argument(
        "--cache-dir",
        default=None,
        help="Build cache dir for sleeve scores/aligned factors. Defaults to --out-dir.",
    )
    parser.add_argument(
        "--out-dir",
        default="outputs/analysis/sleeve_weight_diagnostics_2025",
    )
    parser.add_argument(
        "--out-doc",
        default="docs/sleeve_weight_diagnostics_2025.md",
    )
    parser.add_argument(
        "--phase1-log",
        default=None,
        help="Optional Phase1 report log. If omitted, the script auto-finds one by year.",
    )
    parser.add_argument("--top-n", type=int, default=50)
    parser.add_argument("--force-rebuild", action="store_true")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.config_path:
        if not args.start or not args.end:
            raise ValueError("--config-path requires --start and --end")
        cfg_path = Path(args.config_path)
        start = str(args.start)
        end = str(args.end)
    else:
        row = _load_phase2_row(Path(args.runs_csv), args.case)
        cfg_path = Path(str(row["config_path"]))
        start = str(row["start"])
        end = str(row["end"])

    cache_dir = Path(args.cache_dir) if args.cache_dir else out_dir
    config = _load_config(cfg_path)

    sleeve_scores, aligned, fwd_rets, meta = _build_sleeve_scores(
        cfg_path,
        start,
        end,
        cache_dir,
        args.force_rebuild,
    )
    meta["config_path"] = str(cfg_path)
    signal_dates = _signal_dates_from_aligned(aligned)
    analysis_start = int(start)
    analysis_end = int(end)

    weight_rows = _compute_weight_rows(
        config,
        aligned,
        fwd_rets,
        signal_dates,
        analysis_start,
        analysis_end,
    )
    weight_summary = _summarise_weights(weight_rows)
    monthly_weights = _monthly_weight_summary(weight_rows)
    exposures = _selection_exposure_rows(
        config,
        sleeve_scores,
        aligned,
        analysis_start,
        analysis_end,
        args.top_n,
    )
    exposure_summary = _summarise_exposure(exposures)

    horizon = int(meta.get("horizon", config.get("sleeve_composite", {}).get("horizon", 5)))
    factor_top_bottom, factor_ic = _compute_factor_diagnostics(
        aligned,
        fwd_rets,
        config,
        start,
        end,
        horizon=horizon,
        top_n=args.top_n,
    )
    factor_top_bottom_path = out_dir / "factor_top_bottom_summary.csv"
    factor_ic_path = out_dir / "factor_realised_ic.csv"
    factor_top_bottom.to_csv(factor_top_bottom_path, index=False)
    factor_ic.to_csv(factor_ic_path, index=False)

    phase1_log = Path(args.phase1_log) if args.phase1_log else _find_phase1_log(start)
    ic_reconcile = _reconcile_ic(
        phase1_log,
        factor_ic_path,
        factor_top_bottom_path,
    )

    weight_rows.to_csv(out_dir / "sleeve_factor_weight_rows.csv", index=False)
    weight_summary.to_csv(out_dir / "sleeve_factor_weight_summary.csv", index=False)
    monthly_weights.to_csv(out_dir / "sleeve_factor_weight_monthly.csv", index=False)
    exposures.to_csv(out_dir / "selection_factor_exposure_rows.csv", index=False)
    exposure_summary.to_csv(out_dir / "selection_factor_exposure_summary.csv", index=False)
    ic_reconcile.to_csv(out_dir / "phase1_aligned_ic_reconciliation.csv", index=False)
    (out_dir / "meta.json").write_text(
        json.dumps({
            "config_path": str(cfg_path),
            "start": start,
            "end": end,
            "cache_dir": str(cache_dir),
            "phase1_log": str(phase1_log) if phase1_log else "",
            "signal_dates": len(signal_dates),
            "top_n": args.top_n,
        }, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    _write_report(
        Path(args.out_doc),
        meta,
        weight_summary,
        exposure_summary,
        ic_reconcile,
        factor_top_bottom,
    )

    print(f"Wrote {args.out_doc}")
    print(f"Wrote artifacts under {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Attribution for the frozen out-of-sample backtest.

This script reads existing Phase 2 diagnostics only. It does not rerun a
strategy, change a config, or search parameters.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SLEEVES = ["reversal", "momentum", "defensive", "value", "volume_price", "shock_reversal"]
REGIME_PROB_COLS = [
    "trend_up_prob",
    "trend_down_prob",
    "range_bound_prob",
    "high_volatility_prob",
    "value_rotation_prob",
]
STYLE_FACTORS = {
    "reversal_5_cs": "technical",
    "reversal_20_cs": "technical",
    "rsi_14_cs": "technical",
    "pv_divergence_20_cs": "technical",
    "momentum_120_cs": "technical",
    "volatility_20_cs": "technical",
    "volatility_60_cs": "technical",
    "abnormal_drop_reversal_5_cs": "technical",
    "ep_cs": "fundamental",
    "bp_cs": "fundamental",
    "sp_cs": "fundamental",
    "log_market_cap_cs": "fundamental",
}
MAX_LAG_DAYS = {
    "technical": 14,
    "fundamental": 120,
}
VALIDATION_YEARS = list(range(2017, 2025))


def _pct(value: Any, digits: int = 1) -> str:
    if value is None or pd.isna(value):
        return ""
    return f"{float(value) * 100:.{digits}f}%"


def _num(value: Any, digits: int = 2) -> str:
    if value is None or pd.isna(value):
        return ""
    return f"{float(value):.{digits}f}"


def _compound(series: pd.Series) -> float:
    values = series.dropna()
    if values.empty:
        return float("nan")
    return float((1.0 + values).prod() - 1.0)


def _idxmax_label(values: pd.Series) -> str:
    valid = values.dropna()
    if valid.empty:
        return ""
    return str(valid.idxmax())


def _resolve_path(path: str | Path) -> Path:
    p = Path(path)
    if p.is_absolute():
        return p
    return ROOT / p


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _parse_weights(value: Any) -> dict[str, float]:
    if isinstance(value, dict):
        return {
            str(k): float(v)
            for k, v in value.items()
            if v is not None and not pd.isna(v)
        }
    if value is None or pd.isna(value):
        return {}
    if isinstance(value, str):
        for parser in (ast.literal_eval, json.loads):
            try:
                parsed = parser(value)
            except Exception:
                continue
            if isinstance(parsed, dict):
                return _parse_weights(parsed)
    return {}


def _load_runs(path: Path) -> pd.DataFrame:
    runs = pd.read_csv(path)
    required = {
        "year",
        "sample",
        "start",
        "end",
        "strategy",
        "run_dir",
        "annualized_return",
        "annualized_excess_return",
        "information_ratio",
        "max_drawdown",
        "avg_turnover",
        "total_cost_bps",
        "go_nogo_overall",
        "metric_stability_status",
        "max_period_end",
    }
    missing = required - set(runs.columns)
    if missing:
        raise ValueError(f"{path} missing required columns: {sorted(missing)}")
    if (runs["year"].astype(int) == 2025).any():
        raise ValueError("Frozen attribution must not include 2025 rows.")
    return runs.copy()


def _load_period_returns(row: pd.Series) -> pd.DataFrame:
    diag = _resolve_path(row["run_dir"]) / "diagnostics"
    pv = pd.read_parquet(diag / "phase2_portfolio_values.parquet")
    bm_path = diag / "phase2_benchmark_period_returns.csv"
    if bm_path.exists():
        bm = pd.read_csv(bm_path)
        bm = bm[["exec_date", "period_end", "benchmark_return"]].drop_duplicates()
        pv = pv.merge(bm, on=["exec_date", "period_end"], how="left")
    else:
        pv["benchmark_return"] = float("nan")
    pv["year"] = int(row["year"])
    pv["sample"] = str(row["sample"])
    pv["strategy"] = str(row["strategy"])
    pv["excess_return"] = pv["period_return"] - pv["benchmark_return"]
    pv["month"] = (pv["period_end"].astype(int) // 100).astype(int)
    return pv


def _filter_run_dates(df: pd.DataFrame, row: pd.Series, date_col: str = "trade_date") -> pd.DataFrame:
    if df.empty or date_col not in df.columns:
        return df
    dates = df[date_col].astype("int64")
    return df[(dates >= int(row["start"])) & (dates <= int(row["end"]))].copy()


def _summarise_regime_run(row: pd.Series) -> dict[str, Any]:
    diag = _resolve_path(row["run_dir"]) / "diagnostics"
    result: dict[str, Any] = {
        "year": int(row["year"]),
        "sample": str(row["sample"]),
        "strategy": str(row["strategy"]),
        "ann_return": float(row["annualized_return"]),
        "ann_excess": float(row["annualized_excess_return"]),
        "ir": float(row["information_ratio"]),
    }

    probs_path = diag / "phase2_regime_probs.parquet"
    if probs_path.exists():
        probs = _filter_run_dates(pd.read_parquet(probs_path), row)
        for col in REGIME_PROB_COLS:
            result[col] = float(probs[col].mean()) if col in probs.columns and not probs.empty else np.nan
        result["dominant_regime"] = _idxmax_label(pd.Series({c: result.get(c) for c in REGIME_PROB_COLS}))

    weights_path = diag / "phase2_sleeve_weights.parquet"
    base_path = diag / "phase2_sleeve_base_weights.parquet"
    weights = _filter_run_dates(pd.read_parquet(weights_path), row) if weights_path.exists() else pd.DataFrame()
    base = _filter_run_dates(pd.read_parquet(base_path), row) if base_path.exists() else pd.DataFrame()

    for sleeve in SLEEVES:
        w_col = f"{sleeve}_weight"
        result[w_col] = float(weights[w_col].mean()) if w_col in weights.columns and not weights.empty else np.nan
        result[f"{sleeve}_base_weight"] = (
            float(base[w_col].mean()) if w_col in base.columns and not base.empty else np.nan
        )
        result[f"{sleeve}_overlay_weight_delta"] = (
            result[w_col] - result[f"{sleeve}_base_weight"]
            if not pd.isna(result.get(w_col)) and not pd.isna(result.get(f"{sleeve}_base_weight"))
            else np.nan
        )
    result["dominant_sleeve"] = _idxmax_label(
        pd.Series({f"{s}_weight": result.get(f"{s}_weight") for s in SLEEVES})
    )

    mult_path = diag / "phase2_sleeve_overlay_multipliers.parquet"
    if mult_path.exists():
        mult = _filter_run_dates(pd.read_parquet(mult_path), row)
        for sleeve in SLEEVES:
            col = f"{sleeve}_multiplier"
            result[col] = float(mult[col].mean()) if col in mult.columns and not mult.empty else np.nan
    return result


def _overlay_quality(row: pd.Series) -> pd.DataFrame:
    diag = _resolve_path(row["run_dir"]) / "diagnostics"
    path = diag / "phase2_sleeve_overlay_metrics.parquet"
    if not path.exists():
        return pd.DataFrame()
    metrics = _filter_run_dates(pd.read_parquet(path), row)
    if metrics.empty:
        return pd.DataFrame()
    rows = []
    for sleeve, g in metrics.groupby("sleeve"):
        ok = g[g["status"].astype(str) == "ok"]
        rows.append({
            "year": int(row["year"]),
            "sample": str(row["sample"]),
            "sleeve": str(sleeve),
            "ok_obs": int(len(ok)),
            "all_obs": int(len(g)),
            "ok_ratio": float(len(ok) / len(g)) if len(g) else np.nan,
            "avg_icir_ok": float(ok["icir"].mean()) if not ok.empty else np.nan,
            "avg_hit_rate_ok": float(ok["hit_rate"].mean()) if not ok.empty else np.nan,
            "avg_quality_ok": float(ok["quality_score"].mean()) if not ok.empty else np.nan,
            "avg_multiplier_all": float(g["multiplier"].mean()),
        })
    return pd.DataFrame(rows)


def _strategy_summary(validation: pd.DataFrame) -> pd.DataFrame:
    return (
        validation.groupby("strategy", as_index=False)
        .agg(
            avg_ann_return=("annualized_return", "mean"),
            avg_excess=("annualized_excess_return", "mean"),
            median_excess=("annualized_excess_return", "median"),
            pos_excess_years=("annualized_excess_return", lambda s: int((s > 0).sum())),
            pos_return_years=("annualized_return", lambda s: int((s > 0).sum())),
            avg_ir=("information_ratio", "mean"),
            avg_turnover=("avg_turnover", "mean"),
            avg_max_drawdown=("max_drawdown", "mean"),
        )
        .sort_values("strategy")
    )


def _relative_excess(validation: pd.DataFrame) -> pd.DataFrame:
    wide = validation.pivot(index="year", columns="strategy", values="annualized_excess_return")
    wide = wide.sort_index()
    return pd.DataFrame({
        "year": wide.index.astype(int).to_numpy(),
        "D_minus_C_excess": (wide["D_regime_overlay"] - wide["C_regime_baseline"]).to_numpy(),
        "D_minus_A_excess": (wide["D_regime_overlay"] - wide["A_5reversal"]).to_numpy(),
        "B_minus_A_excess": (wide["B_dynamic"] - wide["A_5reversal"]).to_numpy(),
        "C_minus_A_excess": (wide["C_regime_baseline"] - wide["A_5reversal"]).to_numpy(),
    })


def _period_diff_tables(runs: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    frames = []
    for _, row in runs[runs["strategy"].isin(["C_regime_baseline", "D_regime_overlay"])].iterrows():
        frames.append(_load_period_returns(row))
    periods = pd.concat(frames, ignore_index=True)
    c = periods[periods["strategy"] == "C_regime_baseline"].copy()
    d = periods[periods["strategy"] == "D_regime_overlay"].copy()
    keys = ["year", "sample", "signal_date", "exec_date", "period_end"]
    merged = d.merge(
        c,
        on=keys,
        suffixes=("_D", "_C"),
        how="inner",
    )
    merged["D_minus_C_period_return"] = merged["period_return_D"] - merged["period_return_C"]
    merged["D_minus_C_turnover"] = merged["turnover_D"] - merged["turnover_C"]
    merged["D_minus_C_cost_bps"] = merged["cost_bps_D"] - merged["cost_bps_C"]
    keep = keys + [
        "period_return_D",
        "turnover_D",
        "cost_bps_D",
        "period_return_C",
        "turnover_C",
        "cost_bps_C",
        "D_minus_C_period_return",
        "D_minus_C_turnover",
        "D_minus_C_cost_bps",
    ]
    detail = merged[keep].sort_values(["year", "period_end"])
    summary = (
        detail.groupby(["year", "sample"], as_index=False)
        .agg(
            periods=("D_minus_C_period_return", "count"),
            win_periods=("D_minus_C_period_return", lambda s: int((s > 0).sum())),
            avg_period_diff=("D_minus_C_period_return", "mean"),
            median_period_diff=("D_minus_C_period_return", "median"),
            worst_period_diff=("D_minus_C_period_return", "min"),
            best_period_diff=("D_minus_C_period_return", "max"),
            avg_turnover_delta=("D_minus_C_turnover", "mean"),
            avg_cost_bps_delta=("D_minus_C_cost_bps", "mean"),
        )
        .sort_values("year")
    )
    return detail, summary


def _flatten_dict(value: Any, prefix: str = "") -> dict[str, Any]:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, child in value.items():
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            result.update(_flatten_dict(child, child_prefix))
        return result
    return {prefix: value}


def _config_diff_table(c_path: Path, d_path: Path) -> pd.DataFrame:
    c_cfg = yaml.safe_load(c_path.read_text(encoding="utf-8")) or {}
    d_cfg = yaml.safe_load(d_path.read_text(encoding="utf-8")) or {}
    c_flat = _flatten_dict(c_cfg)
    d_flat = _flatten_dict(d_cfg)
    rows = []
    for key in sorted(set(c_flat) | set(d_flat)):
        c_val = c_flat.get(key)
        d_val = d_flat.get(key)
        if c_val != d_val:
            rows.append({
                "path": key,
                "C_regime_baseline": json.dumps(c_val, ensure_ascii=False),
                "D_regime_overlay": json.dumps(d_val, ensure_ascii=False),
            })
    return pd.DataFrame(rows)


def _expand_holdings(row: pd.Series) -> pd.DataFrame:
    diag = _resolve_path(row["run_dir"]) / "diagnostics"
    holdings = pd.read_parquet(diag / "phase2_holdings.parquet")
    pv = pd.read_parquet(
        diag / "phase2_portfolio_values.parquet",
        columns=["signal_date", "exec_date", "period_end"],
    )
    holdings = holdings.merge(pv, on=["signal_date", "exec_date"], how="left")
    rows = []
    for _, h in holdings.iterrows():
        weights = _parse_weights(h["weights"])
        for ts_code, weight in weights.items():
            if weight is None or pd.isna(weight) or weight <= 0:
                continue
            rows.append({
                "year": int(row["year"]),
                "sample": str(row["sample"]),
                "strategy": str(row["strategy"]),
                "signal_date": int(h["signal_date"]),
                "exec_date": int(h["exec_date"]),
                "period_end": int(h["period_end"]) if not pd.isna(h["period_end"]) else np.nan,
                "ts_code": str(ts_code),
                "weight": float(weight),
            })
    return pd.DataFrame(rows)


def _factor_value_column(df: pd.DataFrame, factor: str) -> str:
    if factor in df.columns:
        return factor
    candidates = [c for c in df.columns if c not in {"ts_code", "trade_date"}]
    if not candidates:
        raise ValueError(f"No value column for {factor}")
    return candidates[0]


def _load_factor_cache(factor: str, years: set[int], ts_codes: set[str]) -> pd.DataFrame:
    root = ROOT / "data" / "parquet" / "factors" / f"factor_name={factor}"
    chunks = []
    for year in sorted(years):
        year_dir = root / f"year={year}"
        if not year_dir.exists():
            continue
        for file in year_dir.rglob("*.parquet"):
            try:
                part = pd.read_parquet(file, columns=["ts_code", "trade_date", factor])
            except Exception:
                part = pd.read_parquet(file)
            value_col = _factor_value_column(part, factor)
            part = part[["ts_code", "trade_date", value_col]].rename(columns={value_col: factor})
            part["ts_code"] = part["ts_code"].astype(str)
            part = part[part["ts_code"].isin(ts_codes)]
            if not part.empty:
                chunks.append(part)
    if not chunks:
        return pd.DataFrame(columns=["ts_code", "trade_date", factor])
    result = pd.concat(chunks, ignore_index=True)
    result["trade_date"] = result["trade_date"].astype("int64")
    result[factor] = pd.to_numeric(result[factor], errors="coerce")
    result = result.dropna(subset=["trade_date", factor])
    return result.drop_duplicates(["ts_code", "trade_date"]).sort_values(["ts_code", "trade_date"])


def _add_factor_asof(base: pd.DataFrame, factor: str, factor_df: pd.DataFrame, max_lag_days: int) -> pd.DataFrame:
    left = base[["year", "sample", "strategy", "signal_date", "ts_code", "weight"]].copy()
    left["row_id"] = np.arange(len(left), dtype=np.int64)
    left["signal_date"] = left["signal_date"].astype("int64")
    left["ts_code"] = left["ts_code"].astype(str)

    right = factor_df[["ts_code", "trade_date", factor]].copy()
    right["trade_date"] = right["trade_date"].astype("int64")
    right["ts_code"] = right["ts_code"].astype(str)

    result = left.copy()
    result["factor_trade_date"] = np.nan
    result[factor] = np.nan
    right_groups = {
        code: g.sort_values("trade_date")
        for code, g in right.groupby("ts_code", sort=False)
    }
    parts = []
    for code, lgrp in left.groupby("ts_code", sort=False):
        rgrp = right_groups.get(code)
        if rgrp is None or rgrp.empty:
            continue
        merged = pd.merge_asof(
            lgrp.sort_values("signal_date"),
            rgrp[["trade_date", factor]].sort_values("trade_date"),
            left_on="signal_date",
            right_on="trade_date",
            direction="backward",
        )
        parts.append(merged[["row_id", "trade_date", factor]])

    if parts:
        matched = pd.concat(parts, ignore_index=True).rename(columns={"trade_date": "factor_trade_date"})
        result = result.drop(columns=["factor_trade_date", factor]).merge(matched, on="row_id", how="left")

    result["factor_lag_days"] = np.nan
    has_date = result["factor_trade_date"].notna()
    if has_date.any():
        signal_dt = pd.to_datetime(result.loc[has_date, "signal_date"].astype("int64").astype(str), format="%Y%m%d")
        factor_dt = pd.to_datetime(result.loc[has_date, "factor_trade_date"].astype("int64").astype(str), format="%Y%m%d")
        result.loc[has_date, "factor_lag_days"] = (signal_dt - factor_dt).dt.days.astype(float)

    valid = (
        result[factor].notna()
        & result["factor_lag_days"].notna()
        & (result["factor_lag_days"] >= 0)
        & (result["factor_lag_days"] <= max_lag_days)
    )
    result.loc[~valid, factor] = np.nan
    result["factor"] = factor
    result["factor_type"] = STYLE_FACTORS[factor]
    result["max_allowed_lag_days"] = int(max_lag_days)
    result["valid_factor_obs"] = valid.astype(int)
    return result


def _weighted_mean(group: pd.DataFrame, value_col: str) -> float:
    valid = group.dropna(subset=[value_col, "weight"])
    if valid.empty:
        return float("nan")
    denom = valid["weight"].sum()
    if denom == 0 or pd.isna(denom):
        return float("nan")
    return float((valid[value_col] * valid["weight"]).sum() / denom)


def _holdings_style_exposure(validation_runs: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    holdings = pd.concat([_expand_holdings(row) for _, row in validation_runs.iterrows()], ignore_index=True)
    if holdings.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    min_year = int(holdings["signal_date"].min()) // 10000
    max_year = int(holdings["signal_date"].max()) // 10000
    years = set(range(min_year - 1, max_year + 1))
    ts_codes = set(holdings["ts_code"].astype(str).unique())
    total_obs = (
        holdings.groupby(["year", "sample", "strategy"], as_index=False)
        .agg(total_holding_obs=("ts_code", "count"))
    )

    exposure_rows = []
    lag_rows = []
    detail_frames = []
    for factor, factor_type in STYLE_FACTORS.items():
        max_lag = MAX_LAG_DAYS[factor_type]
        factor_df = _load_factor_cache(factor, years, ts_codes)
        merged = _add_factor_asof(holdings, factor, factor_df, max_lag)
        detail_frames.append(merged)

        date_exposure = (
            merged.groupby(["year", "sample", "strategy", "signal_date"])
            .apply(lambda g: _weighted_mean(g, factor))
            .rename("date_exposure")
            .reset_index()
        )
        annual = (
            date_exposure.groupby(["year", "sample", "strategy"], as_index=False)
            .agg(avg_exposure=("date_exposure", "mean"), signal_count=("date_exposure", "count"))
        )
        valid_obs = (
            merged[merged[factor].notna()]
            .groupby(["year", "sample", "strategy"], as_index=False)
            .agg(
                valid_holding_obs=("ts_code", "count"),
                avg_lag_days=("factor_lag_days", "mean"),
                max_observed_lag_days=("factor_lag_days", "max"),
            )
        )
        annual = annual.merge(valid_obs, on=["year", "sample", "strategy"], how="left")
        annual = annual.merge(total_obs, on=["year", "sample", "strategy"], how="left")
        annual["coverage"] = annual["valid_holding_obs"] / annual["total_holding_obs"]
        annual["factor"] = factor
        annual["factor_type"] = factor_type
        annual["max_allowed_lag_days"] = max_lag
        exposure_rows.append(annual)

        lag_rows.append({
            "factor": factor,
            "factor_type": factor_type,
            "max_allowed_lag_days": max_lag,
            "valid_holding_obs": int(merged[factor].notna().sum()),
            "total_holding_obs": int(len(merged)),
            "coverage": float(merged[factor].notna().mean()) if len(merged) else np.nan,
            "avg_lag_days": float(merged.loc[merged[factor].notna(), "factor_lag_days"].mean()),
            "max_observed_lag_days": float(merged.loc[merged[factor].notna(), "factor_lag_days"].max()),
            "future_obs": int((merged["factor_lag_days"] < 0).sum()),
        })

    exposure = pd.concat(exposure_rows, ignore_index=True) if exposure_rows else pd.DataFrame()
    detail = pd.concat(detail_frames, ignore_index=True) if detail_frames else pd.DataFrame()
    lag_summary = pd.DataFrame(lag_rows)

    pivot = exposure.pivot_table(
        index=["year", "sample", "factor", "factor_type"],
        columns="strategy",
        values="avg_exposure",
        aggfunc="first",
    ).reset_index()
    if {"D_regime_overlay", "C_regime_baseline"}.issubset(pivot.columns):
        pivot["D_minus_C_exposure"] = pivot["D_regime_overlay"] - pivot["C_regime_baseline"]
    if {"D_regime_overlay", "A_5reversal"}.issubset(pivot.columns):
        pivot["D_minus_A_exposure"] = pivot["D_regime_overlay"] - pivot["A_5reversal"]
    return exposure.sort_values(["year", "strategy", "factor"]), pivot.sort_values(["year", "factor"]), lag_summary


def _write_report(
    out_doc: Path,
    runs: pd.DataFrame,
    strategy_summary: pd.DataFrame,
    relative: pd.DataFrame,
    regime_summary: pd.DataFrame,
    sleeve_deltas: pd.DataFrame,
    period_summary: pd.DataFrame,
    overlay_quality: pd.DataFrame,
    exposure_delta: pd.DataFrame,
    lag_summary: pd.DataFrame,
    config_diff: pd.DataFrame,
) -> None:
    lines: list[str] = []
    lines.append("# 冻结回测归因分析")
    lines.append("")
    lines.append("## 边界")
    lines.append("")
    lines.append("- 本报告只读取已完成的 Phase 2 diagnostics，不重跑策略、不改参数、不搜索配置。")
    lines.append("- 正式验证集只使用 2017-2024；2025 不进入本报告；2026 只作为 YTD 观察。")
    lines.append("- 持仓风格暴露使用信号日前最近一次因子值；技术因子最大滞后 14 天，基本面因子最大滞后 120 天。")
    lines.append("")

    lines.append("## 核心结论")
    lines.append("")
    d_c = relative["D_minus_C_excess"]
    d_a = relative["D_minus_A_excess"]
    b_a = relative["B_minus_A_excess"]
    d_row = strategy_summary[strategy_summary["strategy"] == "D_regime_overlay"].iloc[0]
    b_row = strategy_summary[strategy_summary["strategy"] == "B_dynamic"].iloc[0]
    lines.append(
        f"- D 相对 C 在验证集 {int((d_c > 0).sum())}/8 年改善，平均年化超额差 {_pct(d_c.mean(), 2)}。"
    )
    lines.append(
        f"- D 相对 A 在验证集 {int((d_a > 0).sum())}/8 年改善，平均年化超额差 {_pct(d_a.mean(), 2)}。"
    )
    lines.append(
        f"- D 自身平均年化超额为 {_pct(d_row['avg_excess'], 2)}，正超额年份 {int(d_row['pos_excess_years'])}/8；仍不是生产候选。"
    )
    lines.append(
        f"- B dynamic 相对 A 只有 {int((b_a > 0).sum())}/8 年改善，平均年化超额差 {_pct(b_a.mean(), 2)}，全候选动态 IC 路线未通过冻结验证。"
    )
    lines.append(
        f"- B 自身平均年化超额为 {_pct(b_row['avg_excess'], 2)}，说明单纯打开全因子候选池没有解决问题。"
    )
    lines.append("")

    lines.append("## 年度相对表现")
    lines.append("")
    lines.append("| 年份 | D-C 超额差 | D-A 超额差 | B-A 超额差 | C-A 超额差 |")
    lines.append("|---:|---:|---:|---:|---:|")
    for _, r in relative.iterrows():
        lines.append(
            f"| {int(r['year'])} | {_pct(r['D_minus_C_excess'])} | {_pct(r['D_minus_A_excess'])} | "
            f"{_pct(r['B_minus_A_excess'])} | {_pct(r['C_minus_A_excess'])} |"
        )
    lines.append("")

    lines.append("## C/D 不是纯 Overlay 对照")
    lines.append("")
    lines.append("D 相对 C 同时改变了基础 regime 参数和 overlay 开关，所以 D-C 差异不能全部归因于 overlay。关键差异如下：")
    lines.append("")
    wanted = [
        "regime_detector.smoothing.halflife",
        "sleeve_performance_overlay.enabled",
        "allocator.max_weekly_weight_change",
        "allocator.regime_to_sleeve_weights.range_bound.reversal",
        "allocator.regime_to_sleeve_weights.range_bound.volume_price",
        "allocator.regime_to_sleeve_weights.range_bound.value",
        "allocator.regime_to_sleeve_weights.range_bound.momentum",
    ]
    lines.append("| 配置路径 | C | D |")
    lines.append("|---|---:|---:|")
    for key in wanted:
        row = config_diff[config_diff["path"] == key]
        if row.empty:
            continue
        rr = row.iloc[0]
        lines.append(f"| `{key}` | `{rr['C_regime_baseline']}` | `{rr['D_regime_overlay']}` |")
    lines.append("")

    lines.append("## Sleeve 权重归因")
    lines.append("")
    lines.append("| 年份 | D-C reversal | D-C momentum | D-C defensive | D-C value | D-C volume_price | D-C 期均收益差 | D-C 成本差bps |")
    lines.append("|---:|---:|---:|---:|---:|---:|---:|---:|")
    ps = period_summary.set_index("year")
    for _, r in sleeve_deltas.iterrows():
        year = int(r["year"])
        if year not in ps.index or str(r["sample"]) != "validation":
            continue
        p = ps.loc[year]
        lines.append(
            f"| {year} | {_pct(r['D_minus_C_reversal_weight'])} | {_pct(r['D_minus_C_momentum_weight'])} | "
            f"{_pct(r['D_minus_C_defensive_weight'])} | {_pct(r['D_minus_C_value_weight'])} | "
            f"{_pct(r['D_minus_C_volume_price_weight'])} | {_pct(p['avg_period_diff'], 3)} | {_num(p['avg_cost_bps_delta'], 2)} |"
        )
    lines.append("")
    lines.append("读法：D 的主要结构变化是降低 range-bound 下的 reversal，并抬高 volume_price/value/momentum；overlay 再按近期 sleeve IC 做二次乘数。")
    lines.append("")

    lines.append("## Overlay 质量")
    lines.append("")
    if not overlay_quality.empty:
        validation_overlay = overlay_quality[overlay_quality["sample"] == "validation"]
        oq = (
            validation_overlay.groupby("sleeve", as_index=False)
            .agg(avg_multiplier=("avg_multiplier_all", "mean"), avg_ok_ratio=("ok_ratio", "mean"), avg_icir=("avg_icir_ok", "mean"))
            .sort_values("avg_multiplier", ascending=False)
        )
        lines.append("| Sleeve | 平均乘数 | OK 比例 | OK 样本平均 ICIR |")
        lines.append("|---|---:|---:|---:|")
        for _, r in oq.iterrows():
            lines.append(
                f"| {r['sleeve']} | {_num(r['avg_multiplier'], 3)} | {_pct(r['avg_ok_ratio'])} | {_num(r['avg_icir'], 3)} |"
            )
    else:
        lines.append("无 overlay 质量数据。")
    lines.append("")

    lines.append("## 持仓风格暴露")
    lines.append("")
    lines.append("下表是验证集 D-C 的平均持仓暴露差，因子均为截面标准化值；正数代表 D 更偏向该风格。")
    lines.append("")
    focus = ["reversal_5_cs", "momentum_120_cs", "volatility_20_cs", "ep_cs", "bp_cs", "sp_cs", "log_market_cap_cs"]
    lines.append("| 因子 | D-C 平均暴露差 | D-C 最小年份 | D-C 最大年份 |")
    lines.append("|---|---:|---:|---:|")
    val_delta = exposure_delta[exposure_delta["sample"] == "validation"]
    for factor in focus:
        g = val_delta[val_delta["factor"] == factor]
        if g.empty or "D_minus_C_exposure" not in g.columns:
            continue
        lines.append(
            f"| `{factor}` | {_num(g['D_minus_C_exposure'].mean(), 3)} | "
            f"{_num(g['D_minus_C_exposure'].min(), 3)} | {_num(g['D_minus_C_exposure'].max(), 3)} |"
        )
    lines.append("")

    if not lag_summary.empty:
        future_obs = int(lag_summary["future_obs"].sum())
        max_ratio = (lag_summary["max_observed_lag_days"] <= lag_summary["max_allowed_lag_days"]).all()
        lines.append("## PIT 暴露核验")
        lines.append("")
        lines.append(f"- as-of 合并未来观测数：{future_obs}。")
        lines.append(f"- 所有有效暴露滞后均未超过设定上限：{'是' if max_ratio else '否'}。")
        lines.append("- 持仓风格暴露仅用于解释组合暴露，不参与任何参数选择。")
        lines.append("")

    lines.append("## 2026 YTD")
    lines.append("")
    ytd = runs[runs["sample"] == "ytd"].copy()
    if not ytd.empty:
        lines.append("| 策略 | 年化收益 | 年化超额 | 状态 | 稳定性 |")
        lines.append("|---|---:|---:|---|---|")
        for _, r in ytd.sort_values("strategy").iterrows():
            lines.append(
                f"| {r['strategy']} | {_pct(r['annualized_return'])} | {_pct(r['annualized_excess_return'])} | "
                f"{r['go_nogo_overall']} | {r['metric_stability_status']} |"
            )
        lines.append("")
        lines.append("2026 全部为 NO-GO/UNSTABLE，只能作为前瞻观察，不纳入验证结论。")
        lines.append("")

    lines.append("## 判断")
    lines.append("")
    lines.append("1. D 的方向比 C 更接近“不同市场用不同 sleeve”，但这次改善来自基础权重、平滑速度、换手约束和 overlay 的组合效应。")
    lines.append("2. D 在多数年份改善 C，却仍然平均负超额，说明 regime 映射还没有把有效因子暴露稳定转成收益。")
    lines.append("3. 当前结论应维持为研究候选，不应上线；下一步应做固定参数下的交易成本、持仓重合、行业/市值暴露和失败月份拆解，而不是继续调参。")

    out_doc.parent.mkdir(parents=True, exist_ok=True)
    out_doc.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs-csv", default="outputs/validation/frozen_backtest/runs.csv")
    parser.add_argument("--out-dir", default="outputs/analysis/frozen_backtest_attribution")
    parser.add_argument("--out-doc", default="docs/frozen_backtest_attribution.md")
    args = parser.parse_args()

    runs_csv = _resolve_path(args.runs_csv)
    out_dir = _resolve_path(args.out_dir)
    out_doc = _resolve_path(args.out_doc)
    out_dir.mkdir(parents=True, exist_ok=True)

    runs = _load_runs(runs_csv)
    validation = runs[(runs["sample"] == "validation") & (runs["year"].isin(VALIDATION_YEARS))].copy()
    if len(validation) != 32:
        raise ValueError(f"Expected 32 validation rows, got {len(validation)}")

    strategy_summary = _strategy_summary(validation)
    relative = _relative_excess(validation)

    regime_rows = [
        _summarise_regime_run(row)
        for _, row in runs[runs["strategy"].isin(["C_regime_baseline", "D_regime_overlay"])].iterrows()
    ]
    regime_summary = pd.DataFrame(regime_rows).sort_values(["year", "strategy"])

    d = regime_summary[regime_summary["strategy"] == "D_regime_overlay"].copy()
    c = regime_summary[regime_summary["strategy"] == "C_regime_baseline"].copy()
    sleeve_deltas = d[["year", "sample"]].copy()
    c_by_year = c.set_index("year")
    d_by_year = d.set_index("year")
    for sleeve in SLEEVES:
        sleeve_deltas[f"D_minus_C_{sleeve}_weight"] = (
            d_by_year[f"{sleeve}_weight"].reindex(sleeve_deltas["year"]).to_numpy()
            - c_by_year[f"{sleeve}_weight"].reindex(sleeve_deltas["year"]).to_numpy()
        )
        sleeve_deltas[f"D_overlay_{sleeve}_weight_delta"] = (
            d_by_year[f"{sleeve}_overlay_weight_delta"].reindex(sleeve_deltas["year"]).to_numpy()
        )
        sleeve_deltas[f"D_{sleeve}_multiplier"] = (
            d_by_year.get(f"{sleeve}_multiplier", pd.Series(dtype=float)).reindex(sleeve_deltas["year"]).to_numpy()
        )

    period_detail, period_summary = _period_diff_tables(runs)

    overlay_frames = [
        _overlay_quality(row)
        for _, row in runs[runs["strategy"] == "D_regime_overlay"].iterrows()
    ]
    overlay_quality = (
        pd.concat([df for df in overlay_frames if not df.empty], ignore_index=True)
        if overlay_frames
        else pd.DataFrame()
    )

    exposure, exposure_delta, lag_summary = _holdings_style_exposure(validation)

    config_diff = _config_diff_table(
        ROOT / "configs" / "regime.yaml",
        ROOT / "outputs" / "analysis" / "regime_grid_overlay_phase2_2025" / "configs" / "less_reversal_faster_overlay.yaml",
    )

    runs.to_csv(out_dir / "run_index.csv", index=False, encoding="utf-8")
    strategy_summary.to_csv(out_dir / "strategy_summary.csv", index=False, encoding="utf-8")
    relative.to_csv(out_dir / "relative_excess.csv", index=False, encoding="utf-8")
    regime_summary.to_csv(out_dir / "regime_sleeve_summary.csv", index=False, encoding="utf-8")
    sleeve_deltas.to_csv(out_dir / "sleeve_weight_deltas.csv", index=False, encoding="utf-8")
    period_detail.to_csv(out_dir / "period_return_diff_D_vs_C.csv", index=False, encoding="utf-8")
    period_summary.to_csv(out_dir / "period_return_diff_summary.csv", index=False, encoding="utf-8")
    overlay_quality.to_csv(out_dir / "overlay_quality_by_sleeve.csv", index=False, encoding="utf-8")
    exposure.to_csv(out_dir / "holdings_style_exposure.csv", index=False, encoding="utf-8")
    exposure_delta.to_csv(out_dir / "holdings_style_exposure_delta.csv", index=False, encoding="utf-8")
    lag_summary.to_csv(out_dir / "factor_asof_lag_summary.csv", index=False, encoding="utf-8")
    config_diff.to_csv(out_dir / "config_diff_C_vs_D.csv", index=False, encoding="utf-8")

    _write_report(
        out_doc,
        runs,
        strategy_summary,
        relative,
        regime_summary,
        sleeve_deltas,
        period_summary,
        overlay_quality,
        exposure_delta,
        lag_summary,
        config_diff,
    )

    print(f"Wrote {out_doc}")
    print(f"Wrote artifacts under {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Fast Top-N vs production Phase 2 attribution.

This is a diagnostic script, not a parameter search.  It rebuilds the
composite for one fixed regime config, then compares:

* simplified fast Top-N holdings
* actual Phase 2 holdings from an existing run directory

All future returns are used only for post-run attribution.  Signal generation
continues to use the same PIT-safe regime pipeline as ``run_research.py``.
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


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _pct(value: Any, digits: int = 1) -> str:
    if value is None or pd.isna(value):
        return ""
    return f"{float(value) * 100:.{digits}f}%"


def _num(value: Any, digits: int = 2) -> str:
    if value is None or pd.isna(value):
        return ""
    return f"{float(value):.{digits}f}"


def _compound(series: pd.Series) -> float:
    s = series.dropna()
    if s.empty:
        return float("nan")
    return float((1.0 + s).prod() - 1.0)


def _annualized_return(period_returns: pd.Series) -> float:
    r = period_returns.dropna()
    if r.empty:
        return float("nan")
    return float((1.0 + r).prod() ** (52.0 / len(r)) - 1.0)


def _information_ratio(returns: pd.Series) -> float:
    r = returns.dropna()
    if len(r) < 2:
        return float("nan")
    std = float(r.std(ddof=1))
    if std == 0 or np.isnan(std):
        return float("nan")
    return float(r.mean() / std * np.sqrt(52.0))


def _max_drawdown(period_returns: pd.Series) -> float:
    r = period_returns.dropna()
    if r.empty:
        return float("nan")
    equity = (1.0 + r).cumprod()
    dd = equity / equity.cummax() - 1.0
    return float(dd.min())


def _parse_weights(value: Any) -> dict[str, float]:
    if isinstance(value, dict):
        raw = value
    elif isinstance(value, str):
        try:
            raw = ast.literal_eval(value)
        except Exception:
            try:
                raw = json.loads(value)
            except Exception:
                return {}
    else:
        return {}
    result: dict[str, float] = {}
    for code, weight in raw.items():
        if weight is None or pd.isna(weight):
            continue
        weight_f = float(weight)
        if weight_f > 0:
            result[str(code)] = weight_f
    return result


def _read_year_partitions(dataset: str, years: set[int], columns: list[str]) -> pd.DataFrame:
    chunks = []
    for year in sorted(years):
        path = Path("data/parquet") / dataset / f"year={year}"
        if path.exists():
            chunks.append(pd.read_parquet(path, columns=columns))
    if not chunks:
        return pd.DataFrame(columns=columns)
    return pd.concat(chunks, ignore_index=True)


def _next_trade_date(trade_dates: list[int], date: int) -> int | None:
    for d in trade_dates:
        if d > date:
            return int(d)
    return None


def _load_phase2_run(runs_csv: Path, case: str | None) -> pd.Series:
    runs = pd.read_csv(runs_csv)
    runs = runs[runs["return_code"].astype(str) == "0"].copy()
    if case:
        runs = runs[runs["case"].astype(str) == case].copy()
    if runs.empty:
        raise ValueError(f"No successful run found in {runs_csv} for case={case}")
    return runs.iloc[0]


def _build_or_load_composite(
    cfg_path: Path,
    start: str,
    end: str,
    out_dir: Path,
    force_rebuild: bool,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    composite_path = out_dir / "regime_composite.parquet"
    diag_path = out_dir / "regime_composite_diag.json"
    if composite_path.exists() and not force_rebuild:
        composite = pd.read_parquet(composite_path)
        diag = json.loads(diag_path.read_text(encoding="utf-8")) if diag_path.exists() else {}
        return composite, diag

    from data.calendar import get_calendar
    from data.panel_loader import get_loader
    from run_research import (
        _compute_regime_load_window,
        _load_regime_config_safe,
        _select_regime_candidate_factors,
        build_regime_composite,
    )

    loader = get_loader()
    calendar = get_calendar()
    regime_config = _load_regime_config_safe(str(cfg_path))
    factor_names = _select_regime_candidate_factors(loader, regime_config, start, end)
    data_start, data_end = _compute_regime_load_window(
        start, end, regime_config, calendar=calendar,
    )
    calendar.load(start_date=data_start, end_date=data_end)
    factor_dfs = {
        name: loader.read_factor(name, data_start, data_end)
        for name in factor_names
    }
    factor_dfs = {name: df for name, df in factor_dfs.items() if not df.empty}
    fwd_rets = loader.read_factor("fwd_returns", data_start, data_end)
    signal_dates = [int(d) for d in calendar.weekly_rebalance_dates(start, end)]

    composite, raw_diag = build_regime_composite(
        factor_dfs,
        fwd_rets,
        signal_dates,
        str(cfg_path),
        start,
        end,
        loader=loader,
        data_start_date=data_start,
        data_end_date=data_end,
    )
    composite.to_parquet(composite_path, index=False)

    diag = {
        "config_path": str(cfg_path),
        "start": start,
        "end": end,
        "data_start": data_start,
        "data_end": data_end,
        "n_rows": int(len(composite)),
        "n_dates": int(composite["trade_date"].nunique()) if not composite.empty else 0,
        "target_signal_dates_count": raw_diag.get("target_signal_dates_count"),
        "scoring_signal_dates_count": raw_diag.get("scoring_signal_dates_count"),
        "warmup_signal_dates_count": raw_diag.get("warmup_signal_dates_count"),
    }
    diag_path.write_text(json.dumps(diag, indent=2, ensure_ascii=False), encoding="utf-8")
    return composite, diag


def _load_price_matrix(dates: set[int]) -> pd.DataFrame:
    years = {int(d) // 10000 for d in dates}
    prices = _read_year_partitions(
        "prices_adj", years, ["ts_code", "trade_date", "adj_close"]
    )
    prices = prices[prices["trade_date"].isin(dates)].drop_duplicates(
        ["ts_code", "trade_date"]
    )
    return prices.pivot(index="ts_code", columns="trade_date", values="adj_close")


def _load_index_returns(periods: pd.DataFrame) -> pd.DataFrame:
    dates = set(periods["exec_date"].astype(int)) | set(periods["period_end"].astype(int))
    years = {int(d) // 10000 for d in dates}
    index_df = _read_year_partitions(
        "index_daily", years, ["ts_code", "trade_date", "close"]
    )
    if index_df.empty:
        periods["benchmark_return"] = np.nan
        return periods
    idx = (
        index_df[index_df["ts_code"] == "000300.SH"]
        .drop_duplicates("trade_date")
        .set_index("trade_date")["close"]
    )
    bms = []
    for _, r in periods.iterrows():
        e = int(r["exec_date"])
        p = int(r["period_end"])
        if e in idx.index and p in idx.index and idx.loc[e] != 0:
            bms.append(float(idx.loc[p] / idx.loc[e] - 1.0))
        else:
            bms.append(float("nan"))
    periods["benchmark_return"] = bms
    return periods


def _build_fast_holdings(
    composite: pd.DataFrame,
    start: str,
    end: str,
    top_n: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    start_i = int(start)
    end_i = int(end)
    years = {int(start[:4]), int(end[:4])}
    prices = _read_year_partitions(
        "prices_adj", years, ["ts_code", "trade_date", "adj_close"]
    )
    prices = prices[(prices["trade_date"] >= start_i) & (prices["trade_date"] <= end_i)]
    trade_dates = sorted(int(d) for d in prices["trade_date"].unique())
    px = prices.pivot(index="ts_code", columns="trade_date", values="adj_close")

    signal_dates = sorted(
        int(d) for d in composite.loc[
            (composite["trade_date"] >= start_i) &
            (composite["trade_date"] <= end_i),
            "trade_date",
        ].unique()
    )

    period_rows = []
    holding_rows = []
    prev_names: set[str] = set()
    target_year = int(start[:4])

    for i, signal_date in enumerate(signal_dates[:-1]):
        next_signal = signal_dates[i + 1]
        exec_date = _next_trade_date(trade_dates, signal_date)
        period_end = _next_trade_date(trade_dates, next_signal)
        if exec_date is None or period_end is None:
            continue
        if exec_date // 10000 != target_year or period_end // 10000 != target_year:
            continue
        if exec_date not in px.columns or period_end not in px.columns:
            continue

        day_scores = composite[composite["trade_date"] == signal_date]
        selected = (
            day_scores.sort_values("composite_score", ascending=False)
            .drop_duplicates("ts_code")
            .head(top_n)["ts_code"]
            .tolist()
        )
        p0 = px[exec_date].reindex(selected)
        p1 = px[period_end].reindex(selected)
        valid = p0.notna() & p1.notna() & (p0 != 0)
        selected_valid = [code for code, ok in zip(selected, valid) if ok]
        if len(selected_valid) < max(10, top_n // 2):
            continue

        returns = p1[valid] / p0[valid] - 1.0
        weights = {code: 1.0 / len(selected_valid) for code in selected_valid}
        names = set(selected_valid)
        turnover = 1.0 if not prev_names else 1.0 - len(names & prev_names) / max(len(names), 1)
        prev_names = names

        period_rows.append({
            "signal_date": signal_date,
            "exec_date": exec_date,
            "period_end": period_end,
            "fast_return": float(returns.mean()),
            "fast_turnover": turnover,
            "fast_n_holdings": len(selected_valid),
        })
        for code in selected_valid:
            holding_rows.append({
                "signal_date": signal_date,
                "exec_date": exec_date,
                "period_end": period_end,
                "ts_code": code,
                "fast_weight": weights[code],
            })

    periods = pd.DataFrame(period_rows)
    if not periods.empty:
        periods = _load_index_returns(periods)
        periods["fast_excess_return"] = periods["fast_return"] - periods["benchmark_return"]
    return periods, pd.DataFrame(holding_rows)


def _load_phase2_periods(run_dir: Path) -> pd.DataFrame:
    diag = run_dir / "diagnostics"
    pv = pd.read_parquet(diag / "phase2_portfolio_values.parquet")
    bm_path = diag / "phase2_benchmark_period_returns.csv"
    if bm_path.exists():
        bm = pd.read_csv(bm_path)[["exec_date", "period_end", "benchmark_return"]]
        pv = pv.merge(bm.drop_duplicates(["exec_date", "period_end"]), on=["exec_date", "period_end"], how="left")
    else:
        pv["benchmark_return"] = np.nan
    pv["phase2_excess_return"] = pv["period_return"] - pv["benchmark_return"]
    return pv.rename(columns={
        "period_return": "phase2_net_return",
        "gross_period_return": "phase2_gross_return",
        "turnover": "phase2_turnover",
        "cost_bps": "phase2_cost_bps",
        "n_holdings": "phase2_n_holdings",
    })


def _load_phase2_holdings(run_dir: Path, periods: pd.DataFrame) -> pd.DataFrame:
    h = pd.read_parquet(run_dir / "diagnostics" / "phase2_holdings.parquet")
    h = h.merge(
        periods[["signal_date", "exec_date", "period_end"]],
        on=["signal_date", "exec_date"],
        how="left",
    )
    rows = []
    for _, r in h.iterrows():
        weights = _parse_weights(r["weights"])
        for code, weight in weights.items():
            rows.append({
                "signal_date": int(r["signal_date"]),
                "exec_date": int(r["exec_date"]),
                "period_end": int(r["period_end"]),
                "ts_code": code,
                "phase2_weight": float(weight),
            })
    return pd.DataFrame(rows)


def _build_rank_panel(composite: pd.DataFrame) -> pd.DataFrame:
    parts = []
    for d, g in composite.groupby("trade_date"):
        day = g[["ts_code", "trade_date", "composite_score"]].drop_duplicates("ts_code").copy()
        day = day.sort_values("composite_score", ascending=False)
        day["score_rank"] = np.arange(1, len(day) + 1)
        parts.append(day)
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def _stock_return_lookup(periods: pd.DataFrame) -> pd.DataFrame:
    dates = set(periods["exec_date"].astype(int)) | set(periods["period_end"].astype(int))
    px = _load_price_matrix(dates)
    rows = []
    for _, r in periods.iterrows():
        exec_date = int(r["exec_date"])
        period_end = int(r["period_end"])
        if exec_date not in px.columns or period_end not in px.columns:
            continue
        p0 = px[exec_date]
        p1 = px[period_end]
        ret = p1 / p0 - 1.0
        valid = ret.dropna()
        valid = valid[np.isfinite(valid)]
        rows.append(pd.DataFrame({
            "signal_date": int(r["signal_date"]),
            "exec_date": exec_date,
            "period_end": period_end,
            "ts_code": valid.index.astype(str),
            "stock_return": valid.values.astype(float),
        }))
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def _compare_holdings(
    fast_periods: pd.DataFrame,
    fast_holdings: pd.DataFrame,
    phase2_periods: pd.DataFrame,
    phase2_holdings: pd.DataFrame,
    rank_panel: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    common_keys = ["signal_date", "exec_date", "period_end"]
    periods = fast_periods.merge(
        phase2_periods,
        on=common_keys,
        how="inner",
        suffixes=("", "_phase2"),
    )
    if "benchmark_return_phase2" in periods.columns:
        periods["benchmark_return"] = periods["benchmark_return"].combine_first(
            periods["benchmark_return_phase2"]
        )
        periods = periods.drop(columns=["benchmark_return_phase2"])

    returns = _stock_return_lookup(periods)
    fast_h = fast_holdings.merge(returns, on=common_keys + ["ts_code"], how="left")
    phase_h = phase2_holdings.merge(returns, on=common_keys + ["ts_code"], how="left")
    fast_h = fast_h.merge(
        rank_panel.rename(columns={"trade_date": "signal_date"}),
        on=["signal_date", "ts_code"],
        how="left",
    )
    phase_h = phase_h.merge(
        rank_panel.rename(columns={"trade_date": "signal_date"}),
        on=["signal_date", "ts_code"],
        how="left",
    )

    fast_sets = fast_h.groupby(common_keys)["ts_code"].apply(set).rename("fast_names")
    phase_sets = phase_h.groupby(common_keys)["ts_code"].apply(set).rename("phase2_names")
    sets = pd.concat([fast_sets, phase_sets], axis=1).dropna().reset_index()

    period_rows = []
    diff_rows = []
    prev_phase2_names: set[str] = set()
    for _, r in sets.iterrows():
        key = {k: int(r[k]) for k in common_keys}
        f_names = set(r["fast_names"])
        p_names = set(r["phase2_names"])
        common = f_names & p_names
        fast_only = f_names - p_names
        phase2_only = p_names - f_names
        union = f_names | p_names

        ph_day = phase_h[
            (phase_h["signal_date"] == key["signal_date"]) &
            (phase_h["exec_date"] == key["exec_date"]) &
            (phase_h["period_end"] == key["period_end"])
        ].copy()
        fa_day = fast_h[
            (fast_h["signal_date"] == key["signal_date"]) &
            (fast_h["exec_date"] == key["exec_date"]) &
            (fast_h["period_end"] == key["period_end"])
        ].copy()

        phase2_only_prev = len(phase2_only & prev_phase2_names)

        row = dict(key)
        row.update({
            "intersection": len(common),
            "fast_n": len(f_names),
            "phase2_n": len(p_names),
            "fast_overlap": len(common) / len(f_names) if f_names else np.nan,
            "phase2_overlap": len(common) / len(p_names) if p_names else np.nan,
            "jaccard": len(common) / len(union) if union else np.nan,
            "phase2_only_prev_held_pct": phase2_only_prev / len(phase2_only) if phase2_only else np.nan,
            "phase2_mean_rank": float(ph_day["score_rank"].mean()) if not ph_day.empty else np.nan,
            "phase2_median_rank": float(ph_day["score_rank"].median()) if not ph_day.empty else np.nan,
            "phase2_top50_pct": float((ph_day["score_rank"] <= 50).mean()) if not ph_day.empty else np.nan,
            "phase2_top100_pct": float((ph_day["score_rank"] <= 100).mean()) if not ph_day.empty else np.nan,
            "phase2_wavg_rank": _weighted_average(ph_day, "score_rank", "phase2_weight"),
            "fast_only_avg_return": _subset_mean_return(fa_day, fast_only),
            "phase2_only_avg_return": _subset_mean_return(ph_day, phase2_only),
            "common_avg_return": _subset_mean_return(fa_day, common),
            "fast_only_contribution": _subset_contribution(fa_day, fast_only, "fast_weight"),
            "phase2_only_contribution": _subset_contribution(ph_day, phase2_only, "phase2_weight"),
            "phase2_common_contribution": _subset_contribution(ph_day, common, "phase2_weight"),
            "fast_common_contribution": _subset_contribution(fa_day, common, "fast_weight"),
        })
        period_rows.append(row)

        for label, names, frame, weight_col in [
            ("fast_only", fast_only, fa_day, "fast_weight"),
            ("phase2_only", phase2_only, ph_day, "phase2_weight"),
            ("common_fast", common, fa_day, "fast_weight"),
            ("common_phase2", common, ph_day, "phase2_weight"),
        ]:
            sub = frame[frame["ts_code"].isin(names)].copy()
            if sub.empty:
                continue
            sub["bucket"] = label
            sub["weight"] = sub[weight_col]
            sub["contribution"] = sub["weight"] * sub["stock_return"]
            diff_rows.append(sub[common_keys + [
                "ts_code", "bucket", "weight", "stock_return",
                "contribution", "composite_score", "score_rank",
            ]])

        prev_phase2_names = p_names

    period_compare = periods.merge(pd.DataFrame(period_rows), on=common_keys, how="left")
    period_compare["fast_minus_phase2_net"] = (
        period_compare["fast_return"] - period_compare["phase2_net_return"]
    )
    period_compare["fast_minus_phase2_gross"] = (
        period_compare["fast_return"] - period_compare["phase2_gross_return"]
    )
    period_compare["month"] = (period_compare["period_end"].astype(int) // 100).astype(int)

    diff = pd.concat(diff_rows, ignore_index=True) if diff_rows else pd.DataFrame()
    return period_compare, diff, pd.concat([fast_h.assign(source="fast"), phase_h.assign(source="phase2")], ignore_index=True)


def _weighted_average(df: pd.DataFrame, value_col: str, weight_col: str) -> float:
    if df.empty or value_col not in df or weight_col not in df:
        return float("nan")
    sub = df[[value_col, weight_col]].dropna()
    if sub.empty or sub[weight_col].sum() == 0:
        return float("nan")
    return float((sub[value_col] * sub[weight_col]).sum() / sub[weight_col].sum())


def _subset_mean_return(df: pd.DataFrame, names: set[str]) -> float:
    if df.empty or not names:
        return float("nan")
    sub = df[df["ts_code"].isin(names)]["stock_return"].dropna()
    return float(sub.mean()) if not sub.empty else float("nan")


def _subset_contribution(df: pd.DataFrame, names: set[str], weight_col: str) -> float:
    if df.empty or not names:
        return 0.0
    sub = df[df["ts_code"].isin(names)].dropna(subset=["stock_return", weight_col])
    if sub.empty:
        return 0.0
    return float((sub[weight_col] * sub["stock_return"]).sum())


def _monthly_summary(period_compare: pd.DataFrame) -> pd.DataFrame:
    return (
        period_compare
        .groupby("month")
        .agg(
            fast_return=("fast_return", _compound),
            phase2_net_return=("phase2_net_return", _compound),
            phase2_gross_return=("phase2_gross_return", _compound),
            benchmark_return=("benchmark_return", _compound),
            fast_minus_phase2_net=("fast_minus_phase2_net", "sum"),
            avg_overlap=("jaccard", "mean"),
            phase2_top50_pct=("phase2_top50_pct", "mean"),
            phase2_top100_pct=("phase2_top100_pct", "mean"),
            phase2_wavg_rank=("phase2_wavg_rank", "mean"),
            avg_cost_bps=("phase2_cost_bps", "mean"),
            fast_only_contribution=("fast_only_contribution", "sum"),
            phase2_only_contribution=("phase2_only_contribution", "sum"),
            phase2_common_contribution=("phase2_common_contribution", "sum"),
            n_periods=("signal_date", "count"),
        )
        .reset_index()
    )


def _metrics_from_periods(period_compare: pd.DataFrame) -> dict[str, float]:
    return {
        "n_common_periods": int(len(period_compare)),
        "fast_annualized_return": _annualized_return(period_compare["fast_return"]),
        "fast_annualized_excess_return": _annualized_return(
            period_compare["fast_return"] - period_compare["benchmark_return"]
        ),
        "fast_ir": _information_ratio(
            period_compare["fast_return"] - period_compare["benchmark_return"]
        ),
        "fast_max_drawdown": _max_drawdown(period_compare["fast_return"]),
        "phase2_annualized_return": _annualized_return(period_compare["phase2_net_return"]),
        "phase2_annualized_excess_return": _annualized_return(
            period_compare["phase2_net_return"] - period_compare["benchmark_return"]
        ),
        "phase2_ir": _information_ratio(
            period_compare["phase2_net_return"] - period_compare["benchmark_return"]
        ),
        "phase2_max_drawdown": _max_drawdown(period_compare["phase2_net_return"]),
        "avg_jaccard": float(period_compare["jaccard"].mean()),
        "avg_phase2_top50_pct": float(period_compare["phase2_top50_pct"].mean()),
        "avg_phase2_top100_pct": float(period_compare["phase2_top100_pct"].mean()),
        "avg_phase2_wavg_rank": float(period_compare["phase2_wavg_rank"].mean()),
        "avg_phase2_cost_bps": float(period_compare["phase2_cost_bps"].mean()),
        "total_cost_drag": float(
            (period_compare["phase2_gross_return"] - period_compare["phase2_net_return"]).sum()
        ),
    }


def _write_report(
    out_doc: Path,
    row: pd.Series,
    composite_diag: dict[str, Any],
    metrics: dict[str, float],
    period_compare: pd.DataFrame,
    monthly: pd.DataFrame,
    diff: pd.DataFrame,
) -> None:
    lines: list[str] = []
    lines.append("# Fast Top50 vs Phase2 归因：2025 Overlay")
    lines.append("")
    lines.append("## 边界")
    lines.append("")
    lines.append("- 固定使用已经选定的 `less_reversal_faster_overlay` 配置，不做参数搜索。")
    lines.append("- composite 由现有 PIT-safe regime pipeline 生成；收益只用于事后归因。")
    lines.append("- 不使用静态行业分类做判断，避免引入非 PIT 行业信息。")
    lines.append("")
    lines.append("## 样本")
    lines.append("")
    lines.append(f"- Phase2 run: `{row.get('run_dir')}`")
    lines.append(f"- Config: `{row.get('config_path')}`")
    lines.append(f"- Window: `{row.get('start')}-{row.get('end')}`")
    lines.append(f"- Common closed periods: {metrics.get('n_common_periods')}")
    lines.append(
        f"- Composite rows/dates: {composite_diag.get('n_rows')} / "
        f"{composite_diag.get('n_dates')}"
    )
    lines.append("")

    lines.append("## 年度对比")
    lines.append("")
    lines.append("| 口径 | 年化收益 | 年化超额 | IR | 最大回撤 |")
    lines.append("|---|---:|---:|---:|---:|")
    lines.append(
        f"| Fast Top50 | {_pct(metrics['fast_annualized_return'])} | "
        f"{_pct(metrics['fast_annualized_excess_return'])} | "
        f"{_num(metrics['fast_ir'])} | {_pct(metrics['fast_max_drawdown'])} |"
    )
    lines.append(
        f"| Phase2 实际 | {_pct(metrics['phase2_annualized_return'])} | "
        f"{_pct(metrics['phase2_annualized_excess_return'])} | "
        f"{_num(metrics['phase2_ir'])} | {_pct(metrics['phase2_max_drawdown'])} |"
    )
    lines.append("")

    lines.append("## 持仓穿透")
    lines.append("")
    lines.append("| 指标 | 数值 |")
    lines.append("|---|---:|")
    lines.append(f"| 平均 Jaccard 重合度 | {_pct(metrics['avg_jaccard'])} |")
    lines.append(f"| Phase2 持仓落在 composite Top50 的比例 | {_pct(metrics['avg_phase2_top50_pct'])} |")
    lines.append(f"| Phase2 持仓落在 composite Top100 的比例 | {_pct(metrics['avg_phase2_top100_pct'])} |")
    lines.append(f"| Phase2 持仓加权平均 rank | {_num(metrics['avg_phase2_wavg_rank'], 1)} |")
    lines.append(f"| Phase2 平均成本 bps/期 | {_num(metrics['avg_phase2_cost_bps'], 2)} |")
    lines.append(f"| Phase2 全年成本拖累近似 | {_pct(metrics['total_cost_drag'])} |")
    lines.append("")

    lines.append("## 诊断结论")
    lines.append("")
    if metrics["avg_phase2_top50_pct"] >= 0.95 and metrics["avg_jaccard"] >= 0.90:
        lines.append(
            "- Phase2 对 fast 信号的穿透率很高：实际持仓大多已经在 composite Top50，"
            "所以 2025 失败不主要是“组合构建没有买到信号”。"
        )
    else:
        lines.append(
            "- Phase2 对 fast 信号的穿透率偏低，组合构建、持仓延续或交易过滤需要优先排查。"
        )
    if metrics["fast_annualized_excess_return"] < 0:
        lines.append(
            "- Fast Top50 本身仍是负超额，说明 overlay 后的 alpha 信号没有跑赢 2025 基准；"
            "Phase2 只是进一步放大了这个问题。"
        )
    if metrics["total_cost_drag"] > 0.02:
        lines.append(
            f"- 成本拖累不可忽略，全年近似 {_pct(metrics['total_cost_drag'])}；"
            "这能解释 Fast 与 Phase2 的相当一部分差距。"
        )
    lines.append("")

    lines.append("## 月度差异")
    lines.append("")
    lines.append("| 月份 | Fast | Phase2净值 | 基准 | Fast-Phase2 | Jaccard | Phase2 Top50 | Phase2 WAvgRank |")
    lines.append("|---:|---:|---:|---:|---:|---:|---:|---:|")
    for _, r in monthly.iterrows():
        lines.append(
            f"| {int(r['month'])} | {_pct(r['fast_return'])} | "
            f"{_pct(r['phase2_net_return'])} | {_pct(r['benchmark_return'])} | "
            f"{_pct(r['fast_minus_phase2_net'])} | {_pct(r['avg_overlap'])} | "
            f"{_pct(r['phase2_top50_pct'])} | {_num(r['phase2_wavg_rank'], 1)} |"
        )
    lines.append("")

    lines.append("## 差异贡献")
    lines.append("")
    lines.append("说明：贡献为 `持仓权重 × 持有期收益` 的近似和，只用于定位差异。")
    lines.append("")
    bucket = (
        diff.groupby("bucket")
        .agg(
            contribution=("contribution", "sum"),
            avg_return=("stock_return", "mean"),
            avg_rank=("score_rank", "mean"),
            rows=("ts_code", "count"),
        )
        .reset_index()
        if not diff.empty else pd.DataFrame()
    )
    if not bucket.empty:
        lines.append("| Bucket | 贡献 | 平均个股收益 | 平均rank | 样本数 |")
        lines.append("|---|---:|---:|---:|---:|")
        for _, r in bucket.iterrows():
            lines.append(
                f"| {r['bucket']} | {_pct(r['contribution'])} | "
                f"{_pct(r['avg_return'])} | {_num(r['avg_rank'], 1)} | {int(r['rows'])} |"
            )
    lines.append("")

    if not diff.empty:
        fast_only = diff[diff["bucket"] == "fast_only"]
        phase2_only = diff[diff["bucket"] == "phase2_only"]
        lines.append("### Fast only 正贡献 Top10")
        lines.append("")
        lines.append("| 股票 | 贡献 | 平均rank | 出现次数 |")
        lines.append("|---|---:|---:|---:|")
        for _, r in _stock_summary(fast_only).head(10).iterrows():
            lines.append(
                f"| {r['ts_code']} | {_pct(r['contribution'])} | "
                f"{_num(r['avg_rank'], 1)} | {int(r['n'])} |"
            )
        lines.append("")
        lines.append("### Phase2 only 负贡献 Top10")
        lines.append("")
        lines.append("| 股票 | 贡献 | 平均rank | 出现次数 |")
        lines.append("|---|---:|---:|---:|")
        for _, r in _stock_summary(phase2_only, ascending=True).head(10).iterrows():
            lines.append(
                f"| {r['ts_code']} | {_pct(r['contribution'])} | "
                f"{_num(r['avg_rank'], 1)} | {int(r['n'])} |"
            )
        lines.append("")

    lines.append("## 初步判断")
    lines.append("")
    lines.append("1. 若 Fast 明显好于 Phase2，而 Phase2 Top50/Top100 穿透率低，问题优先看组合构建和持仓延续。")
    lines.append("2. 若 Phase2 Top50 穿透率高但仍跑输，问题优先看成本、执行日、交易过滤和权重约束。")
    lines.append("3. 本报告只定位差异来源，不作为调参依据；下一步应先修穿透/组合构建问题，再做新的 OOS 验证。")

    out_doc.parent.mkdir(parents=True, exist_ok=True)
    out_doc.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _stock_summary(df: pd.DataFrame, ascending: bool = False) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["ts_code", "contribution", "avg_rank", "n"])
    return (
        df.groupby("ts_code")
        .agg(
            contribution=("contribution", "sum"),
            avg_rank=("score_rank", "mean"),
            n=("contribution", "count"),
        )
        .reset_index()
        .sort_values("contribution", ascending=ascending)
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs-csv", default="outputs/analysis/regime_grid_overlay_phase2_2025/runs.csv")
    parser.add_argument("--case", default="less_reversal_faster_overlay")
    parser.add_argument("--top-n", type=int, default=50)
    parser.add_argument("--out-dir", default="outputs/analysis/fast_vs_phase2_overlay_2025")
    parser.add_argument("--out-doc", default="docs/fast_vs_phase2_overlay_2025.md")
    parser.add_argument("--force-rebuild-composite", action="store_true")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    row = _load_phase2_run(Path(args.runs_csv), args.case)
    cfg_path = Path(str(row["config_path"]))
    run_dir = Path(str(row["run_dir"]))
    start = str(row["start"])
    end = str(row["end"])

    composite, composite_diag = _build_or_load_composite(
        cfg_path, start, end, out_dir, args.force_rebuild_composite
    )
    if composite.empty:
        raise RuntimeError("Composite is empty; cannot compare fast vs Phase2")

    fast_periods, fast_holdings = _build_fast_holdings(
        composite, start, end, args.top_n
    )
    phase2_periods = _load_phase2_periods(run_dir)
    phase2_holdings = _load_phase2_holdings(run_dir, phase2_periods)
    rank_panel = _build_rank_panel(composite)

    period_compare, diff, expanded_holdings = _compare_holdings(
        fast_periods, fast_holdings, phase2_periods, phase2_holdings, rank_panel
    )
    monthly = _monthly_summary(period_compare)
    metrics = _metrics_from_periods(period_compare)

    period_compare.to_csv(out_dir / "period_compare.csv", index=False, encoding="utf-8")
    monthly.to_csv(out_dir / "monthly_compare.csv", index=False, encoding="utf-8")
    diff.to_csv(out_dir / "holding_diff_contributions.csv", index=False, encoding="utf-8")
    expanded_holdings.to_csv(out_dir / "expanded_holdings_with_ranks.csv", index=False, encoding="utf-8")
    (out_dir / "metrics.json").write_text(
        json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    _write_report(
        Path(args.out_doc),
        row,
        composite_diag,
        metrics,
        period_compare,
        monthly,
        diff,
    )
    print(f"Wrote {args.out_doc}")
    print(f"Wrote artifacts under {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Small regime-router parameter grid for 2023/2025 failure years.

The script generates candidate regime configs from ``configs/regime.yaml``,
runs Phase 2 for same-year windows, and writes a compact comparison report.
It intentionally keeps the grid small: the goal is diagnosis, not large-scale
hyper-parameter search.
"""

from __future__ import annotations

import argparse
import copy
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


DEFAULT_WINDOWS = {
    # End before the final rebalance that would hold into the next calendar
    # year. Legacy prices_adj partitions can have different adjustment bases
    # across years, so these windows isolate regime-config effects.
    2023: ("20230101", "20231222"),
    2025: ("20250101", "20251224"),
}


CASES: dict[str, dict[str, Any]] = {
    "baseline": {
        "description": "原始 regime.yaml，同窗口重跑",
        "overrides": {},
    },
    "less_reversal": {
        "description": "降低 range_bound 对 reversal 的依赖，增加量价/动量/价值分散",
        "overrides": {
            "allocator.regime_to_sleeve_weights.range_bound.reversal": 0.30,
            "allocator.regime_to_sleeve_weights.range_bound.volume_price": 0.30,
            "allocator.regime_to_sleeve_weights.range_bound.defensive": 0.15,
            "allocator.regime_to_sleeve_weights.range_bound.value": 0.15,
            "allocator.regime_to_sleeve_weights.range_bound.momentum": 0.10,
        },
    },
    "faster_switch": {
        "description": "缩短 regime 平滑半衰期并放宽每周 sleeve 权重变化",
        "overrides": {
            "regime_detector.smoothing.halflife": 2,
            "allocator.max_weekly_weight_change": 0.30,
        },
    },
    "trend_value_push": {
        "description": "提高趋势/价值 regime 的主 sleeve 穿透，并放宽单 sleeve 上限",
        "overrides": {
            "allocator.sleeve_weight_cap": 0.60,
            "allocator.regime_to_sleeve_weights.trend_up.momentum": 0.55,
            "allocator.regime_to_sleeve_weights.trend_up.volume_price": 0.20,
            "allocator.regime_to_sleeve_weights.trend_up.reversal": 0.05,
            "allocator.regime_to_sleeve_weights.trend_up.defensive": 0.10,
            "allocator.regime_to_sleeve_weights.trend_up.value": 0.10,
            "allocator.regime_to_sleeve_weights.value_rotation.value": 0.55,
            "allocator.regime_to_sleeve_weights.value_rotation.defensive": 0.15,
            "allocator.regime_to_sleeve_weights.value_rotation.reversal": 0.10,
            "allocator.regime_to_sleeve_weights.value_rotation.momentum": 0.10,
            "allocator.regime_to_sleeve_weights.value_rotation.volume_price": 0.10,
        },
    },
    "less_reversal_faster_switch": {
        "description": "组合候选：降低 range_bound 反转依赖，同时加快 regime/sleeve 切换",
        "overrides": {
            "regime_detector.smoothing.halflife": 2,
            "allocator.max_weekly_weight_change": 0.30,
            "allocator.regime_to_sleeve_weights.range_bound.reversal": 0.30,
            "allocator.regime_to_sleeve_weights.range_bound.volume_price": 0.30,
            "allocator.regime_to_sleeve_weights.range_bound.defensive": 0.15,
            "allocator.regime_to_sleeve_weights.range_bound.value": 0.15,
            "allocator.regime_to_sleeve_weights.range_bound.momentum": 0.10,
        },
    },
    "performance_overlay": {
        "description": "在基础 regime 权重上叠加 sleeve 近期 IC 表现乘数",
        "overrides": {
            "sleeve_performance_overlay.enabled": True,
        },
    },
    "less_reversal_faster_overlay": {
        "description": "降低 range_bound 反转依赖、加快切换，并叠加 sleeve 近期 IC 表现乘数",
        "overrides": {
            "regime_detector.smoothing.halflife": 2,
            "allocator.max_weekly_weight_change": 0.30,
            "allocator.regime_to_sleeve_weights.range_bound.reversal": 0.30,
            "allocator.regime_to_sleeve_weights.range_bound.volume_price": 0.30,
            "allocator.regime_to_sleeve_weights.range_bound.defensive": 0.15,
            "allocator.regime_to_sleeve_weights.range_bound.value": 0.15,
            "allocator.regime_to_sleeve_weights.range_bound.momentum": 0.10,
            "sleeve_performance_overlay.enabled": True,
        },
    },
}


def _set_nested(config: dict[str, Any], dotted_path: str, value: Any) -> None:
    node = config
    keys = dotted_path.split(".")
    for key in keys[:-1]:
        node = node.setdefault(key, {})
    node[keys[-1]] = value


def _pct(value: Any, digits: int = 1) -> str:
    if value is None or pd.isna(value):
        return ""
    return f"{float(value) * 100:.{digits}f}%"


def _num(value: Any, digits: int = 2) -> str:
    if value is None or pd.isna(value):
        return ""
    return f"{float(value):.{digits}f}"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _new_run_dir(before: set[Path]) -> Path | None:
    runs_dir = Path("outputs/runs")
    after = {p for p in runs_dir.iterdir() if p.is_dir()}
    created = sorted(after - before, key=lambda p: p.stat().st_mtime, reverse=True)
    return created[0] if created else None


def _collect_sleeve_means(run_dir: Path) -> dict[str, float]:
    path = run_dir / "diagnostics" / "phase2_sleeve_weights.parquet"
    if not path.exists():
        return {}
    df = pd.read_parquet(path)
    cols = [c for c in df.columns if c.endswith("_weight")]
    return {c: float(df[c].mean()) for c in cols if c in df}


def _collect_regime_means(run_dir: Path) -> dict[str, float]:
    path = run_dir / "diagnostics" / "phase2_regime_probs.parquet"
    if not path.exists():
        return {}
    df = pd.read_parquet(path)
    cols = [c for c in df.columns if c.endswith("_prob")]
    return {c: float(df[c].mean()) for c in cols if c in df}


def _collect_overlay_multiplier_means(run_dir: Path) -> dict[str, float]:
    path = run_dir / "diagnostics" / "phase2_sleeve_overlay_multipliers.parquet"
    if not path.exists():
        return {}
    df = pd.read_parquet(path)
    cols = [c for c in df.columns if c.endswith("_multiplier")]
    return {c: float(df[c].mean()) for c in cols if c in df}


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


def _fast_backtest(composite: pd.DataFrame, start: str, end: str, top_n: int) -> dict[str, Any]:
    """Local simplified Top-N backtest for parameter diagnostics.

    This skips production universe/tradable/cost modeling. Use it to screen
    regime-router directions, then rerun finalists through full Phase 2.
    """
    if composite.empty:
        return {"error": "empty_composite"}

    start_i = int(start)
    end_i = int(end)
    years = {int(start[:4]), int(end[:4])}
    prices = _read_year_partitions(
        "prices_adj",
        years,
        ["ts_code", "trade_date", "adj_close"],
    )
    if prices.empty:
        return {"error": "missing_prices"}
    prices = prices[(prices["trade_date"] >= start_i) & (prices["trade_date"] <= end_i)]
    trade_dates = sorted(int(d) for d in prices["trade_date"].unique())
    px = prices.pivot(index="ts_code", columns="trade_date", values="adj_close")

    index_df = _read_year_partitions(
        "index_daily",
        years,
        ["ts_code", "trade_date", "close"],
    )
    index_df = index_df[index_df["ts_code"] == "000300.SH"].copy() if not index_df.empty else index_df
    index_close = (
        index_df.drop_duplicates(["trade_date"]).set_index("trade_date")["close"]
        if not index_df.empty else pd.Series(dtype=float)
    )

    signal_dates = sorted(
        int(d) for d in composite.loc[
            (composite["trade_date"] >= start_i) & (composite["trade_date"] <= end_i),
            "trade_date",
        ].unique()
    )
    rows = []
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
        if not selected:
            continue
        p0 = px[exec_date].reindex(selected)
        p1 = px[period_end].reindex(selected)
        valid = p0.notna() & p1.notna() & (p0 != 0)
        if valid.sum() < max(10, top_n // 2):
            continue
        selected_valid = [code for code, ok in zip(selected, valid) if ok]
        period_ret = float((p1[valid] / p0[valid] - 1.0).mean())

        if exec_date in index_close.index and period_end in index_close.index:
            benchmark_ret = float(index_close.loc[period_end] / index_close.loc[exec_date] - 1.0)
        else:
            benchmark_ret = float("nan")

        names = set(selected_valid)
        turnover = 1.0 if not prev_names else 1.0 - len(names & prev_names) / max(len(names), 1)
        prev_names = names
        rows.append({
            "signal_date": signal_date,
            "exec_date": exec_date,
            "period_end": period_end,
            "period_return": period_ret,
            "benchmark_return": benchmark_ret,
            "excess_return": period_ret - benchmark_ret if not pd.isna(benchmark_ret) else float("nan"),
            "turnover": turnover,
            "n_holdings": len(selected_valid),
        })

    periods = pd.DataFrame(rows)
    if periods.empty:
        return {"error": "no_periods"}

    return {
        "periods": periods,
        "annualized_return": _annualized_return(periods["period_return"]),
        "annualized_excess_return": _annualized_return(periods["excess_return"]),
        "benchmark_annualized_return": _annualized_return(periods["benchmark_return"]),
        "information_ratio": _information_ratio(periods["excess_return"]),
        "sharpe_ratio": _information_ratio(periods["period_return"]),
        "max_drawdown": _max_drawdown(periods["period_return"]),
        "avg_turnover": float(periods["turnover"].mean()),
        "n_periods": int(len(periods)),
    }


def _run_fast_case(cfg_path: Path, start: str, end: str, top_n: int) -> dict[str, Any]:
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
    factor_dfs = {
        name: loader.read_factor(name, data_start, data_end)
        for name in factor_names
    }
    factor_dfs = {name: df for name, df in factor_dfs.items() if not df.empty}
    fwd_rets = loader.read_factor("fwd_returns", data_start, data_end)
    signal_dates = [int(d) for d in calendar.weekly_rebalance_dates(start, end)]

    composite, diag = build_regime_composite(
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
    result = _fast_backtest(composite, start, end, top_n)
    result["_regime_diag"] = diag
    return result


def _write_summary(out_doc: Path, rows: list[dict[str, Any]]) -> None:
    df = pd.DataFrame(rows)
    lines: list[str] = []
    lines.append("# Regime 参数小网格：2023 / 2025")
    lines.append("")
    lines.append(
        "验证窗口使用同年闭合口径：2023 为 `20230101-20231222`，"
        "2025 为 `20250101-20251224`，避免最后一周持仓跨年受到旧复权缓存口径影响。"
    )
    lines.append("")
    lines.append(
        "默认结果来自 fast 诊断引擎：复用现有 regime composite 生成信号，"
        "再用本地 parquet 做简化等权 Top-N 回测；它用于筛方向，不能替代完整 Phase 2。"
    )
    lines.append("")

    if df.empty:
        lines.append("没有生成有效结果。")
        out_doc.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return

    lines.append("## 结果总表")
    lines.append("")
    lines.append("| 年份 | 配置 | 年化收益 | 年化超额 | IR | 最大回撤 | reversal | momentum | defensive | value | volume_price | reversal_x | value_x |")
    lines.append("|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for _, r in df.sort_values(["year", "case"]).iterrows():
        lines.append(
            f"| {int(r['year'])} | {r['case']} | {_pct(r.get('annualized_return'))} | "
            f"{_pct(r.get('annualized_excess_return'))} | {_num(r.get('information_ratio'))} | "
            f"{_pct(r.get('max_drawdown'))} | {_pct(r.get('reversal_weight'))} | "
            f"{_pct(r.get('momentum_weight'))} | {_pct(r.get('defensive_weight'))} | "
            f"{_pct(r.get('value_weight'))} | {_pct(r.get('volume_price_weight'))} | "
            f"{_num(r.get('reversal_multiplier'))} | {_num(r.get('value_multiplier'))} |"
        )

    lines.append("")
    lines.append("## 相对 baseline")
    lines.append("")
    lines.append("| 年份 | 配置 | 超额变化 | IR变化 | 回撤变化 | 判断 |")
    lines.append("|---:|---|---:|---:|---:|---|")
    for year, g in df.groupby("year"):
        base = g[g["case"] == "baseline"]
        if base.empty:
            continue
        b = base.iloc[0]
        for _, r in g[g["case"] != "baseline"].sort_values("case").iterrows():
            if pd.isna(r.get("annualized_excess_return")) or pd.isna(b.get("annualized_excess_return")):
                excess_delta = float("nan")
                ir_delta = float("nan")
                dd_delta = float("nan")
                verdict = "无结果"
            else:
                excess_delta = r.get("annualized_excess_return") - b.get("annualized_excess_return")
                ir_delta = r.get("information_ratio") - b.get("information_ratio")
                dd_delta = r.get("max_drawdown") - b.get("max_drawdown")
                verdict = "改善" if excess_delta > 0 and ir_delta > 0 else "未改善"
            lines.append(
                f"| {int(year)} | {r['case']} | {_pct(excess_delta)} | "
                f"{_num(ir_delta)} | {_pct(dd_delta)} | {verdict} |"
            )

    lines.append("")
    lines.append("## 初步结论")
    lines.append("")
    for year, g in df.groupby("year"):
        g_valid = g.dropna(subset=["annualized_excess_return"]) if "annualized_excess_return" in g else pd.DataFrame()
        if g_valid.empty or g_valid[g_valid["case"] == "baseline"].empty:
            lines.append(f"- {int(year)}：没有可用的 baseline 和候选指标。")
            continue
        best = g_valid.sort_values("annualized_excess_return", ascending=False).iloc[0]
        base = g_valid[g_valid["case"] == "baseline"].iloc[0]
        delta = best["annualized_excess_return"] - base["annualized_excess_return"]
        lines.append(
            f"- {int(year)}：最佳配置是 `{best['case']}`，"
            f"相对 baseline 年化超额变化 {_pct(delta)}。"
        )
    lines.append(
        "- 这只是失败年份的小网格诊断；若某个配置在 2023/2025 有改善，"
        "还需要回到 2017-2025 全样本和 2026 YTD 做稳定性复验。"
    )

    out_doc.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-config", default="configs/regime.yaml")
    parser.add_argument("--out-dir", default="outputs/analysis/regime_grid_2023_2025")
    parser.add_argument("--cases", nargs="+", default=list(CASES.keys()))
    parser.add_argument("--years", nargs="+", type=int, default=sorted(DEFAULT_WINDOWS))
    parser.add_argument("--engine", choices=["fast", "phase2"], default="fast")
    parser.add_argument("--top-n", type=int, default=50)
    parser.add_argument("--skip-existing", action="store_true")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    cfg_dir = out_dir / "configs"
    log_dir = out_dir / "logs"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    base = yaml.safe_load(Path(args.base_config).read_text(encoding="utf-8"))
    selected_cases = [case for case in args.cases if case in CASES]
    if not selected_cases:
        raise ValueError(f"No valid cases selected: {args.cases}")

    rows: list[dict[str, Any]] = []
    runs_csv = out_dir / "runs.csv"
    if args.skip_existing and runs_csv.exists():
        rows = pd.read_csv(runs_csv).to_dict("records")
        done = {(int(r["year"]), str(r["case"])) for r in rows}
    else:
        done = set()

    for case in selected_cases:
        cfg = copy.deepcopy(base)
        for path, value in CASES[case]["overrides"].items():
            _set_nested(cfg, path, value)
        cfg_path = cfg_dir / f"{case}.yaml"
        cfg_path.write_text(
            yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )

        for year in args.years:
            start, end = DEFAULT_WINDOWS[year]
            if (year, case) in done:
                continue

            log_path = log_dir / f"{year}_{case}.log"
            row: dict[str, Any] = {
                "year": year,
                "case": case,
                "description": CASES[case]["description"],
                "start": start,
                "end": end,
                "engine": args.engine,
                "config_path": str(cfg_path),
                "log_path": str(log_path),
            }

            if args.engine == "phase2":
                before = {p for p in Path("outputs/runs").iterdir() if p.is_dir()}
                cmd = [
                    sys.executable,
                    "-X",
                    "utf8",
                    "run_research.py",
                    "phase2",
                    "--start",
                    start,
                    "--end",
                    end,
                    "--top-n",
                    str(args.top_n),
                    "--no-recompute",
                    "--factors-config",
                    "configs/factors.yaml",
                    "--strategy-mode",
                    "regime",
                    "--regime-config",
                    str(cfg_path),
                ]
                print(f"Running {year} {case}: {' '.join(cmd)}")
                with log_path.open("w", encoding="utf-8") as fh:
                    proc = subprocess.run(
                        cmd,
                        stdout=fh,
                        stderr=subprocess.STDOUT,
                        text=True,
                        encoding="utf-8",
                    )

                run_dir = _new_run_dir(before)
                row["return_code"] = proc.returncode
                row["run_dir"] = str(run_dir) if run_dir else ""
                if proc.returncode == 0 and run_dir is not None:
                    metrics = _load_json(run_dir / "metrics_summary.json").get("phase2", {})
                    row.update({
                        "annualized_return": metrics.get("annualized_return"),
                        "annualized_excess_return": metrics.get("annualized_excess_return"),
                        "information_ratio": metrics.get("information_ratio"),
                        "sharpe_ratio": metrics.get("sharpe_ratio"),
                        "max_drawdown": metrics.get("max_drawdown"),
                        "avg_turnover": metrics.get("avg_turnover"),
                        "n_periods": metrics.get("n_periods"),
                        "benchmark_annualized_return": metrics.get("benchmark_annualized_return"),
                    })
                    row.update(_collect_sleeve_means(run_dir))
                    row.update(_collect_regime_means(run_dir))
                    row.update(_collect_overlay_multiplier_means(run_dir))
                else:
                    print(f"FAILED {year} {case}, see {log_path}")
            else:
                print(f"Running fast {year} {case}")
                try:
                    with log_path.open("w", encoding="utf-8") as fh:
                        old_stdout, old_stderr = sys.stdout, sys.stderr
                        sys.stdout = fh
                        sys.stderr = fh
                        try:
                            result = _run_fast_case(cfg_path, start, end, args.top_n)
                        finally:
                            sys.stdout = old_stdout
                            sys.stderr = old_stderr
                    row["return_code"] = 0 if "error" not in result else 1
                    row["error"] = result.get("error", "")
                    for key in [
                        "annualized_return",
                        "annualized_excess_return",
                        "benchmark_annualized_return",
                        "information_ratio",
                        "sharpe_ratio",
                        "max_drawdown",
                        "avg_turnover",
                        "n_periods",
                    ]:
                        row[key] = result.get(key)
                    diag = result.get("_regime_diag", {})
                    sleeve_weights = diag.get("sleeve_weights")
                    if isinstance(sleeve_weights, pd.DataFrame) and not sleeve_weights.empty:
                        for col in [c for c in sleeve_weights.columns if c.endswith("_weight")]:
                            row[col] = float(sleeve_weights[col].mean())
                    sleeve_multipliers = diag.get("sleeve_overlay_multipliers")
                    if isinstance(sleeve_multipliers, pd.DataFrame) and not sleeve_multipliers.empty:
                        for col in [c for c in sleeve_multipliers.columns if c.endswith("_multiplier")]:
                            row[col] = float(sleeve_multipliers[col].mean())
                    regime_probs = diag.get("regime_probs")
                    if isinstance(regime_probs, pd.DataFrame) and not regime_probs.empty:
                        for col in [c for c in regime_probs.columns if c.endswith("_prob")]:
                            row[col] = float(regime_probs[col].mean())
                except Exception as exc:
                    row["return_code"] = 1
                    row["error"] = str(exc)
                    print(f"FAILED fast {year} {case}: {exc}")
            rows.append(row)
            pd.DataFrame(rows).to_csv(runs_csv, index=False, encoding="utf-8")

    pd.DataFrame(rows).to_csv(runs_csv, index=False, encoding="utf-8")
    _write_summary(out_dir / "summary.md", rows)
    print(f"Wrote {runs_csv}")
    print(f"Wrote {out_dir / 'summary.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

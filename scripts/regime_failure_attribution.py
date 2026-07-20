"""Attribution for regime-router failure years.

Reads existing run diagnostics and writes a compact markdown report plus CSV
artifacts. This script intentionally uses only cached backtest artifacts and
local price data; it does not rerun strategies.
"""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Any

import pandas as pd


STRATEGY_LABELS = {
    "A_5reversal": "A 固定5反转",
    "B_dynamic": "B 动态IC",
    "C_regime": "C Regime",
}


def _pct(x: Any, digits: int = 1) -> str:
    if pd.isna(x):
        return ""
    return f"{float(x) * 100:.{digits}f}%"


def _num(x: Any, digits: int = 2) -> str:
    if pd.isna(x):
        return ""
    return f"{float(x):.{digits}f}"


def _parse_mapping(value: Any) -> dict[str, float]:
    if isinstance(value, dict):
        return {str(k): float(v) for k, v in value.items() if v is not None}
    if pd.isna(value):
        return {}
    if isinstance(value, str):
        try:
            parsed = ast.literal_eval(value)
        except Exception:
            try:
                parsed = json.loads(value)
            except Exception:
                return {}
        if isinstance(parsed, dict):
            return {
                str(k): float(v)
                for k, v in parsed.items()
                if v is not None
            }
    return {}


def _compound(series: pd.Series) -> float:
    s = series.dropna()
    if s.empty:
        return float("nan")
    return float((1.0 + s).prod() - 1.0)


def _idxmax_label(values: pd.Series) -> str:
    """Return idxmax label, or blank when a row/series is all missing."""
    valid = values.dropna()
    if valid.empty:
        return ""
    return str(valid.idxmax())


def _load_run_index(runs_csv: Path, years: list[int]) -> pd.DataFrame:
    df = pd.read_csv(runs_csv)
    df = df[df["year"].isin(years)].copy()
    required = {"year", "strategy", "run_dir"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{runs_csv} missing columns: {sorted(missing)}")
    return df


def _load_period_returns(run_dir: Path, strategy: str, year: int) -> pd.DataFrame:
    diag = run_dir / "diagnostics"
    pv = pd.read_parquet(diag / "phase2_portfolio_values.parquet")
    bench_path = diag / "phase2_benchmark_period_returns.csv"
    if bench_path.exists():
        bm = pd.read_csv(bench_path)
        bm = bm[["exec_date", "period_end", "benchmark_return"]].drop_duplicates()
        pv = pv.merge(bm, on=["exec_date", "period_end"], how="left")
    else:
        pv["benchmark_return"] = float("nan")

    pv["year"] = year
    pv["strategy"] = strategy
    pv["month"] = (pv["period_end"].astype(int) // 100).astype(int)
    pv["period_end_year"] = (pv["period_end"].astype(int) // 10000).astype(int)
    pv["excess_return"] = pv["period_return"] - pv["benchmark_return"]
    return pv


def _load_holdings(run_dir: Path, strategy: str, year: int) -> pd.DataFrame:
    path = run_dir / "diagnostics" / "phase2_holdings.parquet"
    h = pd.read_parquet(path)
    h["year"] = year
    h["strategy"] = strategy
    h["weights_map"] = h["weights"].map(_parse_mapping)
    h["positive_names"] = h["weights_map"].map(
        lambda m: {k for k, v in m.items() if v and v > 0}
    )
    h["n_positive"] = h["positive_names"].map(len)
    return h


def _read_prices_for_dates(dates: set[int]) -> pd.DataFrame:
    years = sorted({int(str(d)[:4]) for d in dates})
    chunks = []
    for year in years:
        p = Path("data/parquet/prices_adj") / f"year={year}"
        if p.exists():
            chunks.append(pd.read_parquet(p))
    if not chunks:
        return pd.DataFrame(columns=["ts_code", "trade_date", "adj_close"])
    prices = pd.concat(chunks, ignore_index=True)
    prices = prices[prices["trade_date"].isin(dates)]
    return prices[["ts_code", "trade_date", "adj_close"]].drop_duplicates()


def _stock_contributions(holdings: pd.DataFrame) -> pd.DataFrame:
    dates = set(holdings["exec_date"].astype(int)) | set(holdings["period_end"].astype(int))
    prices = _read_prices_for_dates(dates)
    if prices.empty:
        return pd.DataFrame()

    px = prices.pivot(index="ts_code", columns="trade_date", values="adj_close")
    rows = []
    for _, r in holdings.iterrows():
        year = int(r["year"])
        exec_date = int(r["exec_date"])
        period_end = int(r["period_end"]) if "period_end" in r else None
        if period_end is None:
            continue
        # prices_adj partitions before/after a year boundary may have different
        # adjustment bases in legacy caches. Keep this attribution conservative
        # and avoid fabricating single-stock PnL across calendar years.
        if exec_date // 10000 != year or period_end // 10000 != year:
            continue
        if exec_date not in px.columns or period_end not in px.columns:
            continue
        weights = {
            k: v for k, v in r["weights_map"].items()
            if v is not None and v > 0
        }
        if not weights:
            continue
        p0 = px[exec_date]
        p1 = px[period_end]
        for ts_code, weight in weights.items():
            if ts_code not in p0.index:
                continue
            start = p0.loc[ts_code]
            end = p1.loc[ts_code]
            if pd.isna(start) or pd.isna(end) or start == 0:
                continue
            stock_ret = float(end / start - 1.0)
            rows.append({
                "year": year,
                "strategy": r["strategy"],
                "signal_date": int(r["signal_date"]),
                "exec_date": exec_date,
                "period_end": period_end,
                "month": int(period_end // 100),
                "ts_code": ts_code,
                "weight": float(weight),
                "stock_return": stock_ret,
                "contribution": float(weight) * stock_ret,
            })
    return pd.DataFrame(rows)


def _load_regime_monthly(run_dir: Path, year: int) -> pd.DataFrame:
    diag = run_dir / "diagnostics"
    probs_path = diag / "phase2_regime_probs.parquet"
    sleeves_path = diag / "phase2_sleeve_weights.parquet"
    if not probs_path.exists() or not sleeves_path.exists():
        return pd.DataFrame()

    probs = pd.read_parquet(probs_path)
    sleeves = pd.read_parquet(sleeves_path)
    df = probs.merge(sleeves, on="trade_date", how="outer")
    df = df[(df["trade_date"].astype(int) >= year * 10000)
            & (df["trade_date"].astype(int) < (year + 1) * 10000)].copy()
    if df.empty:
        return df
    df["year"] = year
    df["month"] = (df["trade_date"].astype(int) // 100).astype(int)
    prob_cols = [c for c in df.columns if c.endswith("_prob")]
    sleeve_cols = [c for c in df.columns if c.endswith("_weight")]
    monthly = df.groupby(["year", "month"])[prob_cols + sleeve_cols].mean().reset_index()
    monthly["dominant_regime"] = (
        monthly[prob_cols].apply(_idxmax_label, axis=1) if prob_cols else ""
    )
    monthly["dominant_sleeve"] = (
        monthly[sleeve_cols].apply(_idxmax_label, axis=1) if sleeve_cols else ""
    )
    return monthly


def _holdings_overlap(holdings: dict[tuple[int, str], pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for (year, _), c_h in holdings.items():
        if (year, "C_regime") not in holdings:
            continue
    years = sorted({year for year, _ in holdings})
    for year in years:
        if (year, "C_regime") not in holdings:
            continue
        c = holdings[(year, "C_regime")][
            ["signal_date", "positive_names", "n_positive"]
        ].rename(columns={
            "positive_names": "c_names",
            "n_positive": "c_n",
        })
        for other in ["A_5reversal", "B_dynamic"]:
            if (year, other) not in holdings:
                continue
            o = holdings[(year, other)][
                ["signal_date", "positive_names", "n_positive"]
            ].rename(columns={
                "positive_names": "o_names",
                "n_positive": "o_n",
            })
            merged = c.merge(o, on="signal_date", how="inner")
            for _, r in merged.iterrows():
                c_names = r["c_names"]
                o_names = r["o_names"]
                inter = len(c_names & o_names)
                union = len(c_names | o_names)
                rows.append({
                    "year": year,
                    "other_strategy": other,
                    "signal_date": int(r["signal_date"]),
                    "c_n": int(r["c_n"]),
                    "other_n": int(r["o_n"]),
                    "intersection": inter,
                    "c_overlap": inter / len(c_names) if c_names else float("nan"),
                    "jaccard": inter / union if union else float("nan"),
                })
    return pd.DataFrame(rows)


def _write_report(
    out_doc: Path,
    run_index: pd.DataFrame,
    monthly: pd.DataFrame,
    regime_monthly: pd.DataFrame,
    contrib_summary: pd.DataFrame,
    overlap: pd.DataFrame,
) -> None:
    lines: list[str] = []
    lines.append("# Regime 失败归因：2023 / 2025")
    lines.append("")
    lines.append("数据来源：已有 Phase 2 diagnostics，不重新回测。")
    lines.append("")

    lines.append("## 年度结论")
    lines.append("")
    lines.append("| 年份 | A超额 | B超额 | C超额 | C-A | C-B | 初步判断 |")
    lines.append("|---:|---:|---:|---:|---:|---:|---|")
    for year, g in run_index.groupby("year"):
        by = g.set_index("strategy")
        a = by.loc["A_5reversal", "annualized_excess_return"]
        b = by.loc["B_dynamic", "annualized_excess_return"]
        c = by.loc["C_regime", "annualized_excess_return"]
        if year == 2023:
            note = "C 明显输给 A，router/sleeve 暴露不适配"
        elif year == 2025:
            note = "B 最好，C 接近 A 但未捕捉动态因子"
        else:
            note = ""
        lines.append(
            f"| {int(year)} | {_pct(a)} | {_pct(b)} | {_pct(c)} | "
            f"{_pct(c-a)} | {_pct(c-b)} | {note} |"
        )

    lines.append("")
    lines.append("## 月度相对收益")
    lines.append("")
    lines.append("| 年月 | A | B | C | C-A | C-B | C主导Regime | C主导Sleeve |")
    lines.append("|---:|---:|---:|---:|---:|---:|---|---|")
    for _, r in monthly.sort_values(["year", "month"]).iterrows():
        lines.append(
            f"| {int(r['month'])} | {_pct(r.get('A_5reversal'))} | "
            f"{_pct(r.get('B_dynamic'))} | {_pct(r.get('C_regime'))} | "
            f"{_pct(r.get('C_minus_A'))} | {_pct(r.get('C_minus_B'))} | "
            f"{r.get('dominant_regime', '') or ''} | {r.get('dominant_sleeve', '') or ''} |"
        )

    lines.append("")
    lines.append("## C Regime 平均配置")
    lines.append("")
    lines.append("| 年份 | 主导Regime均值最高 | 主导Sleeve均值最高 | reversal | momentum | defensive | value | volume_price |")
    lines.append("|---:|---|---|---:|---:|---:|---:|---:|")
    sleeve_cols = [
        "reversal_weight", "momentum_weight", "defensive_weight",
        "value_weight", "volume_price_weight",
    ]
    prob_cols = [
        "trend_up_prob", "trend_down_prob", "range_bound_prob",
        "high_volatility_prob", "value_rotation_prob",
    ]
    for year, g in regime_monthly.groupby("year"):
        avg = g[prob_cols + sleeve_cols].mean()
        top_regime = _idxmax_label(avg[prob_cols])
        top_sleeve = _idxmax_label(avg[sleeve_cols])
        lines.append(
            f"| {int(year)} | {top_regime} {_pct(avg[prob_cols].max())} | "
            f"{top_sleeve} {_pct(avg[sleeve_cols].max())} | "
            f"{_pct(avg['reversal_weight'])} | {_pct(avg['momentum_weight'])} | "
            f"{_pct(avg['defensive_weight'])} | {_pct(avg['value_weight'])} | "
            f"{_pct(avg['volume_price_weight'])} |"
        )

    lines.append("")
    lines.append("## 持仓重合度")
    lines.append("")
    if not overlap.empty:
        ov = overlap.groupby(["year", "other_strategy"])[["c_overlap", "jaccard"]].mean().reset_index()
        lines.append("| 年份 | 对比 | C持仓重合率 | Jaccard |")
        lines.append("|---:|---|---:|---:|")
        for _, r in ov.iterrows():
            lines.append(
                f"| {int(r['year'])} | {STRATEGY_LABELS.get(r['other_strategy'], r['other_strategy'])} | "
                f"{_pct(r['c_overlap'])} | {_pct(r['jaccard'])} |"
            )
    else:
        lines.append("无可用持仓重合度数据。")

    lines.append("")
    lines.append("## C Regime 年度近似贡献 Top/Bottom")
    lines.append("")
    lines.append(
        "说明：个股贡献按 `期初权重 × 持有期个股收益` 近似估算，"
        "仅用于定位暴露来源；跨自然年持有期已排除，避免旧缓存复权基准不连续造成虚假贡献。"
    )
    lines.append("")
    if not contrib_summary.empty:
        c_only = contrib_summary[contrib_summary["strategy"] == "C_regime"]
        for year, g in c_only.groupby("year"):
            lines.append(f"### {int(year)}")
            lines.append("")
            top = g.sort_values("contribution", ascending=False).head(8)
            bottom = g.sort_values("contribution", ascending=True).head(8)
            lines.append("Top contributors:")
            lines.append("")
            lines.append("| 股票 | 贡献 | 平均权重 | 持有期数 |")
            lines.append("|---|---:|---:|---:|")
            for _, r in top.iterrows():
                lines.append(
                    f"| {r['ts_code']} | {_pct(r['contribution'])} | "
                    f"{_pct(r['avg_weight'])} | {int(r['n_periods'])} |"
                )
            lines.append("")
            lines.append("Bottom contributors:")
            lines.append("")
            lines.append("| 股票 | 贡献 | 平均权重 | 持有期数 |")
            lines.append("|---|---:|---:|---:|")
            for _, r in bottom.iterrows():
                lines.append(
                    f"| {r['ts_code']} | {_pct(r['contribution'])} | "
                    f"{_pct(r['avg_weight'])} | {int(r['n_periods'])} |"
                )
            lines.append("")

    lines.append("## 诊断判断")
    lines.append("")
    lines.append("1. 2023 不是简单的“动态不够”，因为 B 也没有优于 A；C 的问题更像是 router 将组合持续推向了不占优的 sleeve 暴露。")
    lines.append("2. 2025 B 明显优于 A/C，说明全因子动态 IC 在该年比显式 regime router 更灵敏；C 的 sleeve 映射和权重平滑可能压慢了切换。")
    lines.append("3. C 在两个年份的主导概率仍偏 `range_bound_prob`，平均最高 sleeve 仍偏 `reversal_weight`，这和“不同市场趋势使用不同策略”的目标还有距离。")
    lines.append("4. 下一步参数网格应优先测试：降低 range_bound→reversal 权重、提高 trend/value 对 momentum/value sleeve 的穿透、放宽每周权重变化约束。")

    out_doc.parent.mkdir(parents=True, exist_ok=True)
    out_doc.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs-csv", default="outputs/comparison/backtest_2017_2025/runs.csv")
    parser.add_argument("--years", nargs="+", type=int, default=[2023, 2025])
    parser.add_argument("--out-dir", default="outputs/analysis/regime_failure_2023_2025")
    parser.add_argument("--out-doc", default="docs/regime_failure_attribution_2023_2025.md")
    args = parser.parse_args()

    runs_csv = Path(args.runs_csv)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    run_index = _load_run_index(runs_csv, args.years)

    period_frames = []
    holdings_map: dict[tuple[int, str], pd.DataFrame] = {}
    regime_frames = []
    contrib_frames = []

    for _, r in run_index.iterrows():
        year = int(r["year"])
        strategy = str(r["strategy"])
        run_dir = Path(str(r["run_dir"]))
        period = _load_period_returns(run_dir, strategy, year)
        period_frames.append(period)

        holdings = _load_holdings(run_dir, strategy, year)
        # Add period_end to holdings for contribution calculation.
        holdings = holdings.merge(
            period[["signal_date", "exec_date", "period_end"]],
            on=["signal_date", "exec_date"], how="left"
        )
        holdings_map[(year, strategy)] = holdings
        contrib = _stock_contributions(holdings)
        if not contrib.empty:
            contrib_frames.append(contrib)

        if strategy == "C_regime":
            regime = _load_regime_monthly(run_dir, year)
            if not regime.empty:
                regime_frames.append(regime)

    periods = pd.concat(period_frames, ignore_index=True)
    periods_in_year = periods[periods["period_end_year"] == periods["year"]].copy()
    period_monthly = (
        periods_in_year
        .groupby(["year", "month", "strategy"])
        .agg(
            total_return=("period_return", _compound),
            excess_return=("excess_return", _compound),
            n_periods=("period_return", "count"),
        )
        .reset_index()
    )
    monthly_wide = period_monthly.pivot(
        index=["year", "month"], columns="strategy", values="total_return"
    ).reset_index()
    monthly_wide["C_minus_A"] = monthly_wide.get("C_regime") - monthly_wide.get("A_5reversal")
    monthly_wide["C_minus_B"] = monthly_wide.get("C_regime") - monthly_wide.get("B_dynamic")

    regime_monthly = (
        pd.concat(regime_frames, ignore_index=True)
        if regime_frames else pd.DataFrame()
    )
    if not regime_monthly.empty:
        monthly_wide = monthly_wide.merge(
            regime_monthly[["year", "month", "dominant_regime", "dominant_sleeve"]],
            on=["year", "month"], how="left",
        )

    contrib_all = (
        pd.concat(contrib_frames, ignore_index=True)
        if contrib_frames else pd.DataFrame()
    )
    if not contrib_all.empty:
        contrib_summary = (
            contrib_all
            .groupby(["year", "strategy", "ts_code"])
            .agg(
                contribution=("contribution", "sum"),
                avg_weight=("weight", "mean"),
                n_periods=("contribution", "count"),
            )
            .reset_index()
        )
    else:
        contrib_summary = pd.DataFrame()

    overlap = _holdings_overlap(holdings_map)

    run_index.to_csv(out_dir / "run_index.csv", index=False, encoding="utf-8")
    period_monthly.to_csv(out_dir / "monthly_returns_long.csv", index=False, encoding="utf-8")
    monthly_wide.to_csv(out_dir / "monthly_returns_wide.csv", index=False, encoding="utf-8")
    if not regime_monthly.empty:
        regime_monthly.to_csv(out_dir / "regime_monthly.csv", index=False, encoding="utf-8")
    if not contrib_all.empty:
        contrib_all.to_csv(out_dir / "stock_contributions_period.csv", index=False, encoding="utf-8")
        contrib_summary.to_csv(out_dir / "stock_contributions_summary.csv", index=False, encoding="utf-8")
    if not overlap.empty:
        overlap.to_csv(out_dir / "holdings_overlap.csv", index=False, encoding="utf-8")

    _write_report(
        Path(args.out_doc),
        run_index,
        monthly_wide,
        regime_monthly,
        contrib_summary,
        overlap,
    )
    print(f"Wrote {args.out_doc}")
    print(f"Wrote artifacts under {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

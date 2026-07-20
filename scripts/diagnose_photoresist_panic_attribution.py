"""Diagnose overlap, semiconductor beta, and placebo structure for panic events."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_photoresist_panic_events import (  # noqa: E402
    build_trading_calendar, load_index_prices, load_prices, trading_day_offset,
)
from validate_photoresist_panic_thresholds import (  # noqa: E402
    _event_exclusion_dates, build_candidate_forward_returns,
    compute_market_regime, load_validation_inputs, load_yaml,
)

DEFAULT_CONFIG = ROOT / "configs" / "photoresist_panic_research.yaml"
DEFAULT_INPUT = ROOT / "outputs" / "analysis" / "photoresist_panic_threshold_validation"
DEFAULT_FROZEN = ROOT / "outputs" / "analysis" / "photoresist_panic_bbb_full"
DEFAULT_OUTPUT = ROOT / "outputs" / "analysis" / "photoresist_panic_attribution_diagnostics"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Diagnose photoresist panic attribution")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--input-dir", default=str(DEFAULT_INPUT))
    parser.add_argument("--frozen-dir", default=str(DEFAULT_FROZEN))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--gate-id", default="primary_5d")
    parser.add_argument("--runs", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=20260712)
    parser.add_argument("--cost-bps", type=int, default=20)
    return parser.parse_args()


def select_non_overlapping(events: pd.DataFrame, horizon: int) -> pd.DataFrame:
    if events.empty:
        return events.copy()
    selected = []
    last_exit = -1
    exit_col = f"exit_date_{horizon}d"
    for _, row in events.sort_values(["entry_date", "event_date"]).iterrows():
        entry = int(row["entry_date"])
        exit_date = row.get(exit_col, row.get("exit_date_20d"))
        if pd.isna(exit_date):
            continue
        if entry > last_exit:
            selected.append(row)
            last_exit = int(exit_date)
    return pd.DataFrame(selected).reset_index(drop=True) if selected else events.iloc[0:0].copy()


def add_backward_features(frame: pd.DataFrame, core_basket: pd.DataFrame,
                          index_prices: pd.DataFrame,
                          semi_code: str = "931865.CSI") -> pd.DataFrame:
    result = frame.copy()
    basket = core_basket.sort_values("trade_date").copy()
    basket["basket_pre_20d"] = (
        (1.0 + basket["basket_ret_1d"].fillna(0.0)).rolling(20).apply(np.prod, raw=True) - 1.0
    ).shift(1)
    semi = index_prices[index_prices["ts_code"] == semi_code].sort_values("trade_date").copy()
    semi["semi_ret_1d"] = semi["close"].pct_change()
    semi["semi_pre_20d"] = semi["close"].pct_change(20).shift(1)
    semi["semi_vol_20d"] = semi["semi_ret_1d"].rolling(20).std().shift(1)
    features = basket[["trade_date", "basket_pre_20d"]].merge(
        semi[["trade_date", "semi_pre_20d", "semi_vol_20d"]], on="trade_date", how="left"
    )
    return result.merge(features.rename(columns={"trade_date": "event_date"}),
                        on="event_date", how="left")


def summarize_event_returns(events: pd.DataFrame, gate_id: str, cost_bps: int) -> pd.DataFrame:
    rows = []
    cost = 2.0 * cost_bps / 10000.0
    samples = (("all_events", events), ("non_overlapping", select_non_overlapping(events, 20)))
    for sample_name, sample in samples:
        for horizon in (5, 10, 20):
            basket_col = f"basket_fwd_ret_{horizon}d"
            semi_col = f"semi_fwd_ret_{horizon}d"
            valid = sample.dropna(subset=[basket_col]).copy()
            comparable = valid.dropna(subset=[semi_col]).copy()
            basket_net = valid[basket_col] - cost
            excess = comparable[basket_col] - comparable[semi_col]
            rows.append({
                "gate_id": gate_id, "sample": sample_name, "horizon_days": horizon,
                "n_events_total": int(len(sample)), "n_basket_valid": int(len(valid)),
                "n_excess_valid": int(len(comparable)),
                "basket_mean_net": float(basket_net.mean()) if len(valid) else np.nan,
                "basket_win_rate": float((basket_net > 0).mean()) if len(valid) else np.nan,
                "semi_mean_return": float(comparable[semi_col].mean()) if len(comparable) else np.nan,
                "excess_mean": float(excess.mean()) if len(comparable) else np.nan,
                "excess_win_rate": float((excess > 0).mean()) if len(comparable) else np.nan,
            })
    return pd.DataFrame(rows)


def summarize_by_regime(events: pd.DataFrame, gate_id: str, cost_bps: int) -> pd.DataFrame:
    rows = []
    cost = 2.0 * cost_bps / 10000.0
    samples = (("all_events", events), ("non_overlapping", select_non_overlapping(events, 20)))
    for sample_name, sample in samples:
        for regime, group in sample.groupby("market_regime", dropna=False):
            for horizon in (5, 10, 20):
                basket_col, semi_col = f"basket_fwd_ret_{horizon}d", f"semi_fwd_ret_{horizon}d"
                comparable = group.dropna(subset=[basket_col, semi_col])
                excess = comparable[basket_col] - comparable[semi_col]
                rows.append({
                    "gate_id": gate_id, "sample": sample_name, "market_regime": regime,
                    "horizon_days": horizon, "n_events": int(len(comparable)),
                    "basket_mean_net": float((comparable[basket_col] - cost).mean()) if len(comparable) else np.nan,
                    "semi_mean_return": float(comparable[semi_col].mean()) if len(comparable) else np.nan,
                    "excess_mean": float(excess.mean()) if len(comparable) else np.nan,
                    "excess_win_rate": float((excess > 0).mean()) if len(comparable) else np.nan,
                })
    return pd.DataFrame(rows)


def build_coverage_diagnostics(events: pd.DataFrame, gate_id: str) -> pd.DataFrame:
    rows = []
    for horizon in (5, 10, 20):
        basket_col, semi_col = f"basket_fwd_ret_{horizon}d", f"semi_fwd_ret_{horizon}d"
        for _, row in events.iterrows():
            basket_ok, semi_ok = pd.notna(row.get(basket_col)), pd.notna(row.get(semi_col))
            rows.append({"gate_id": gate_id, "event_date": int(row["event_date"]),
                         "horizon_days": horizon, "basket_available": bool(basket_ok),
                         "semi_available": bool(semi_ok), "comparable": bool(basket_ok and semi_ok)})
    return pd.DataFrame(rows)


def _distance(pool: pd.DataFrame, event: pd.Series) -> pd.Series:
    scales = {"basket_pre_20d": 0.05, "semi_pre_20d": 0.05, "semi_vol_20d": 0.02}
    distance = pd.Series(0.0, index=pool.index)
    for column, scale in scales.items():
        if column in pool and pd.notna(event.get(column)):
            valid = pool[column].notna()
            distance.loc[valid] += ((pool.loc[valid, column] - float(event[column])) / scale) ** 2
            distance.loc[~valid] += 100.0
    return np.sqrt(distance)


def run_strict_placebo(real: pd.DataFrame, candidates: pd.DataFrame,
                       calendar: np.ndarray, gate_id: str,
                       runs: int, seed: int) -> pd.DataFrame:
    excluded = _event_exclusion_dates(real, calendar, 5)
    candidates = candidates[~candidates["event_date"].isin(excluded)].copy()
    candidates["event_year"] = candidates["event_date"] // 10000
    real = real.copy()
    real["event_year"] = real["event_date"] // 10000
    rng = np.random.default_rng(seed)
    rows = []
    calendar_index = {int(date): position for position, date in enumerate(calendar)}
    samples = (("all_events", real), ("non_overlapping", select_non_overlapping(real, 20)))
    for sample_name, sample in samples:
      for horizon in (5, 10, 20):
        column = f"basket_fwd_ret_{horizon}d"
        usable = sample.dropna(subset=[column]).sort_values("event_date")
        pools, matched = [], []
        for _, event in usable.iterrows():
            pool = candidates[(candidates["event_year"] == event["event_year"])
                              & (candidates["market_regime"] == event["market_regime"])]
            pool = pool.dropna(subset=[column]).copy()
            if pool.empty:
                continue
            pool["match_distance"] = _distance(pool, event)
            nearest = pool.nsmallest(min(30, len(pool)), "match_distance")
            pools.append({
                "dates": nearest["event_date"].to_numpy(dtype=int),
                "positions": nearest["event_date"].map(calendar_index).to_numpy(dtype=int),
                "returns": nearest[column].to_numpy(dtype=float),
                "weights": np.exp(-nearest["match_distance"].to_numpy(dtype=float)),
            })
            matched.append(event)
        if not pools:
            continue
        sampled_means, sample_sizes = [], []
        for _ in range(runs):
            used_positions, draws = [], []
            for pool in pools:
                mask = np.ones(len(pool["positions"]), dtype=bool)
                if used_positions:
                    existing = np.asarray(used_positions, dtype=int)
                    mask = (np.abs(pool["positions"][:, None] - existing[None, :]) > horizon).all(axis=1)
                available = np.flatnonzero(mask)
                if len(available) == 0:
                    continue
                weights = pool["weights"][available]
                weights = weights / weights.sum() if weights.sum() > 0 else None
                selected = int(rng.choice(available, p=weights))
                used_positions.append(int(pool["positions"][selected]))
                draws.append(float(pool["returns"][selected]))
            if draws:
                sampled_means.append(float(np.mean(draws)))
                sample_sizes.append(len(draws))
        distribution = np.asarray(sampled_means)
        real_mean = float(pd.DataFrame(matched)[column].mean())
        rows.append({
            "gate_id": gate_id, "sample": sample_name, "horizon_days": horizon,
            "n_real_events": int(len(usable)), "n_matched_events": int(len(pools)),
            "match_coverage": float(len(pools) / len(usable)),
            "mean_unique_draws_per_run": float(np.mean(sample_sizes)),
            "effective_draw_coverage": float(np.mean(sample_sizes) / len(pools)),
            "real_mean_return": real_mean, "placebo_mean_return": float(distribution.mean()),
            "mean_diff": real_mean - float(distribution.mean()),
            "permutation_p_value": float((1 + np.sum(distribution >= real_mean)) / (len(distribution) + 1)),
            "matching": "year+regime+nearest_backward_features+nonoverlap_controls",
        })
    return pd.DataFrame(rows)


def generate_report(summary: pd.DataFrame, regime_summary: pd.DataFrame, placebo: pd.DataFrame,
                    coverage: pd.DataFrame) -> str:
    def table(frame: pd.DataFrame) -> str:
        return frame.to_markdown(index=False, floatfmt=".4f") if not frame.empty else "_无数据_"
    missing = coverage.groupby("horizon_days").agg(
        n_rows=("event_date", "size"), basket_coverage=("basket_available", "mean"),
        semi_coverage=("semi_available", "mean"), comparable_coverage=("comparable", "mean"),
    ).reset_index()
    lines = [
        "# 光刻胶恐慌修复归因诊断", "", f"生成时间：{datetime.now():%Y-%m-%d %H:%M:%S}", "",
        "状态：RESEARCH ONLY。该诊断不修改冻结阈值和 Go/No-Go。", "",
        "## 原始与非重叠事件", "", table(summary), "",
        "## 按市场状态的半导体超额", "", table(regime_summary), "",
        "## 严格 Placebo", "", table(placebo), "",
        "## 收益覆盖率", "", table(missing), "", "## 解释边界", "",
        "- non_overlapping 按时间贪心保留，避免同一段行情被多个事件重复计权。",
        "- excess_mean 为 basket 收益减 931865.CSI 同期收益，不代表完整多因子 alpha。",
        "- 严格 placebo 匹配年份、市场状态、事前20日趋势及半导体波动率，且单轮日期不重复。",
        "- 该匹配仍是研究性诊断，不构成因果识别。",
    ]
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    input_dir, frozen_dir, out_dir = Path(args.input_dir), Path(args.frozen_dir), Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    config = load_yaml(Path(args.config))
    validation = config["threshold_validation"]
    forward = pd.read_csv(input_dir / "photoresist_threshold_forward_returns.csv")
    events = forward[forward["gate_id"] == args.gate_id].copy()
    if events.empty:
        raise RuntimeError(f"No events for gate {args.gate_id}")
    core, universe = load_validation_inputs(frozen_dir)
    codes = universe["ts_code"].astype(str).unique().tolist()
    start, end = int(core.trade_date.min()), int(core.trade_date.max())
    prices = load_prices(start, end, codes)
    calendar = build_trading_calendar(prices)
    regime_cfg = validation["market_regime"]
    index_prices = load_index_prices(start, end, [regime_cfg["primary_index"], "931865.CSI"])
    regime = compute_market_regime(index_prices, regime_cfg)
    candidates = build_candidate_forward_returns(core, index_prices, calendar, regime)
    candidates = add_backward_features(candidates, core, index_prices)
    events = add_backward_features(events, core, index_prices)
    summary = summarize_event_returns(events, args.gate_id, args.cost_bps)
    regime_summary = summarize_by_regime(events, args.gate_id, args.cost_bps)
    coverage = build_coverage_diagnostics(events, args.gate_id)
    strict_placebo = run_strict_placebo(events, candidates, calendar, args.gate_id, args.runs, args.seed)
    outputs = {
        "photoresist_attribution_return_summary.csv": summary,
        "photoresist_attribution_by_market_regime.csv": regime_summary,
        "photoresist_attribution_strict_placebo.csv": strict_placebo,
        "photoresist_attribution_coverage.csv": coverage,
    }
    for name, frame in outputs.items():
        frame.to_csv(out_dir / name, index=False)
    (out_dir / "photoresist_attribution_report.md").write_text(
        generate_report(summary, regime_summary, strict_placebo, coverage), encoding="utf-8")
    manifest = {
        "schema": "photoresist_panic_attribution.v1", "status": "RESEARCH_ONLY",
        "gate_id": args.gate_id, "random_seed": args.seed, "placebo_runs": args.runs,
        "semiconductor_benchmark": "931865.CSI", "frozen_thresholds_unchanged": True,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "outputs": list(outputs) + ["photoresist_attribution_report.md", "photoresist_attribution_manifest.json"],
    }
    (out_dir / "photoresist_attribution_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(summary.to_string(index=False))
    print(strict_placebo.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

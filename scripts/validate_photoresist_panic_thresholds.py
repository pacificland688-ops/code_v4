"""Validate photoresist panic thresholds without changing the frozen pipeline."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from build_photoresist_panic_events import (  # noqa: E402
    build_calendar_index,
    build_trading_calendar,
    load_index_prices,
    load_limit_status,
    load_prices,
    load_stock_status,
    load_suspend_status,
    trading_day_offset,
)
from evaluate_photoresist_panic_reversal import (  # noqa: E402
    compute_basket_leave_one_out,
    compute_concentration_diagnostics,
    compute_forward_returns,
    compute_leave_one_out,
    compute_robustness,
    evaluate_go_nogo,
    evaluate_top1_rules,
)

DEFAULT_RESEARCH_CONFIG = ROOT / "configs" / "photoresist_panic_research.yaml"
DEFAULT_UNIVERSE_CONFIG = ROOT / "configs" / "photoresist_universe.yaml"
DEFAULT_INPUT_DIR = ROOT / "outputs" / "analysis" / "photoresist_panic"
DEFAULT_OUT_DIR = ROOT / "outputs" / "analysis" / "photoresist_panic_threshold_validation"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate photoresist panic thresholds")
    parser.add_argument("--research-config", default=str(DEFAULT_RESEARCH_CONFIG))
    parser.add_argument("--universe-config", default=str(DEFAULT_UNIVERSE_CONFIG))
    parser.add_argument("--input-dir", default=str(DEFAULT_INPUT_DIR))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--start", type=int, default=None)
    parser.add_argument("--end", type=int, default=None)
    parser.add_argument("--cost-bps", type=int, default=20)
    return parser.parse_args()


def load_yaml(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def load_validation_inputs(input_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    core_path = input_dir / "photoresist_core_basket_with_gate.csv"
    universe_path = input_dir / "photoresist_universe_snapshot.csv"
    missing = [str(path) for path in (core_path, universe_path) if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing frozen pipeline outputs: " + ", ".join(missing))
    core_basket = pd.read_csv(core_path)
    universe_df = pd.read_csv(universe_path)
    core_basket["trade_date"] = pd.to_numeric(core_basket["trade_date"], errors="coerce")
    core_basket = core_basket.dropna(subset=["trade_date"]).copy()
    core_basket["trade_date"] = core_basket["trade_date"].astype(int)
    universe_df["ts_code"] = universe_df["ts_code"].astype(str)
    for column in ("effective_start", "effective_end"):
        universe_df[column] = pd.to_numeric(universe_df[column], errors="coerce")
    return core_basket.sort_values("trade_date").reset_index(drop=True), universe_df


def _ensure_return_column(frame: pd.DataFrame, window: int) -> pd.DataFrame:
    result = frame.copy()
    column = f"basket_ret_{window}d"
    if column not in result.columns:
        result[column] = result["basket_ret_1d"].rolling(
            window, min_periods=window
        ).apply(lambda values: np.prod(1.0 + values) - 1.0, raw=True)
    return result


def build_threshold_gate(
    core_basket: pd.DataFrame,
    gate_id: str,
    gate_config: dict,
) -> pd.DataFrame:
    return_window = int(gate_config["return_window_days"])
    breadth_window = int(gate_config.get("breadth_window_days", 5))
    result = _ensure_return_column(core_basket, return_window)
    return_column = f"basket_ret_{return_window}d"
    quantile_window = int(gate_config["quantile_window_days"])
    quantile_level = float(gate_config["quantile_threshold_pct"]) / 100.0
    absolute_threshold = float(gate_config["absolute_threshold_pct"]) / 100.0
    breadth_threshold = float(gate_config["breadth_threshold_pct"]) / 100.0
    historical_returns = result[return_column].shift(1)
    result["validation_quantile"] = historical_returns.rolling(
        quantile_window, min_periods=min(60, quantile_window)
    ).quantile(quantile_level)
    result["validation_breadth"] = result["down_stock_ratio"].rolling(
        breadth_window, min_periods=min(3, breadth_window)
    ).mean()
    result["validation_return"] = result[return_column]
    result["validation_gate_triggered"] = (
        (result["validation_return"] < 0)
        & (
            (result["validation_return"] <= absolute_threshold)
            | (result["validation_return"] <= result["validation_quantile"])
        )
        & (result["validation_breadth"] >= breadth_threshold)
    )
    result["gate_id"] = gate_id
    return result


def cluster_threshold_events(
    gated: pd.DataFrame,
    calendar: np.ndarray,
    max_gap: int,
) -> pd.DataFrame:
    triggered = gated[gated["validation_gate_triggered"]].copy()
    if triggered.empty:
        return pd.DataFrame()
    calendar_index = build_calendar_index(calendar)
    triggered["calendar_index"] = triggered["trade_date"].map(calendar_index)
    triggered = triggered.dropna(subset=["calendar_index"]).sort_values("trade_date")
    gaps = triggered["calendar_index"].diff().fillna(max_gap + 1)
    triggered["event_cluster_id"] = (gaps > max_gap).cumsum().astype(int) - 1
    rows = []
    for cluster_id, cluster in triggered.groupby("event_cluster_id"):
        cluster = cluster.sort_values("trade_date")
        event_date = int(cluster["trade_date"].iloc[-1])
        rows.append({
            "gate_id": str(cluster["gate_id"].iloc[0]),
            "event_cluster_id": int(cluster_id),
            "event_start_date": int(cluster["trade_date"].iloc[0]),
            "event_date": event_date,
            "exec_date": trading_day_offset(calendar, event_date, 1),
            "n_triggered_days": int(len(cluster)),
            "validation_return_at_event": float(cluster["validation_return"].iloc[-1]),
            "validation_quantile_at_event": float(cluster["validation_quantile"].iloc[-1])
                if pd.notna(cluster["validation_quantile"].iloc[-1]) else np.nan,
            "validation_breadth_at_event": float(cluster["validation_breadth"].iloc[-1]),
            "panic_amount_ratio_20d": float(cluster["median_amount_ratio_20d"].iloc[-1])
                if pd.notna(cluster["median_amount_ratio_20d"].iloc[-1]) else np.nan,
            "intensity_label": "threshold_validation",
            "environment_label": "threshold_validation",
        })
    return pd.DataFrame(rows)


def compute_market_regime(index_prices: pd.DataFrame, config: dict) -> pd.DataFrame:
    primary_code = str(config.get("primary_index", "000300.SH"))
    ma_window = int(config.get("ma_window_days", 120))
    return_window = int(config.get("return_window_days", 60))
    primary = index_prices[index_prices["ts_code"] == primary_code].copy()
    if primary.empty:
        return pd.DataFrame(columns=["trade_date", "market_regime"])
    primary = primary.sort_values("trade_date").drop_duplicates("trade_date")
    primary["market_ma"] = primary["close"].rolling(
        ma_window, min_periods=min(60, ma_window)
    ).mean()
    primary["market_return"] = primary["close"].pct_change(return_window)
    primary["market_regime"] = "neutral"
    primary.loc[
        (primary["close"] > primary["market_ma"]) & (primary["market_return"] > 0),
        "market_regime",
    ] = "bull"
    primary.loc[
        (primary["close"] < primary["market_ma"]) & (primary["market_return"] < 0),
        "market_regime",
    ] = "bear"
    return primary[["trade_date", "market_regime", "market_return", "market_ma"]]


def summarize_index_coverage(
    index_prices: pd.DataFrame,
    index_codes: list[str],
    target_dates: pd.Series,
) -> dict[str, dict[str, Any]]:
    requested_dates = set(int(value) for value in target_dates.dropna())
    coverage: dict[str, dict[str, Any]] = {}
    for code in index_codes:
        subset = index_prices[index_prices["ts_code"] == code]
        available_dates = set(int(value) for value in subset["trade_date"].dropna())
        requested_available = requested_dates & available_dates
        coverage[code] = {
            "available": not subset.empty,
            "min_date": int(subset["trade_date"].min()) if not subset.empty else None,
            "max_date": int(subset["trade_date"].max()) if not subset.empty else None,
            "requested_date_coverage": float(len(requested_available) / len(requested_dates))
                if requested_dates else 0.0,
            "missing_requested_years": sorted({
                date // 10000 for date in requested_dates - available_dates
            }),
        }
    return coverage


def attach_event_diagnostics(
    events: pd.DataFrame,
    core_basket: pd.DataFrame,
    market_regime: pd.DataFrame,
    calendar: np.ndarray,
    volume_config: dict,
) -> pd.DataFrame:
    if events.empty:
        return events.copy()
    result = events.merge(
        market_regime.rename(columns={"trade_date": "event_date"}),
        on="event_date",
        how="left",
    )
    result["market_regime"] = result["market_regime"].fillna("unknown")
    panic_high = float(volume_config.get("panic_high_ratio", 1.2))
    repair_high = float(volume_config.get("repair_high_ratio", 1.0))
    search_days = int(volume_config.get("repair_search_days", 5))
    result["panic_volume_group"] = np.where(
        result["panic_amount_ratio_20d"] >= panic_high,
        "high_panic_volume",
        "normal_panic_volume",
    )
    basket_by_date = core_basket.set_index("trade_date")
    repair_dates = []
    repair_ratios = []
    for event_date in result["event_date"].astype(int):
        repair_date = None
        repair_ratio = np.nan
        for offset in range(1, search_days + 1):
            candidate_date = trading_day_offset(calendar, event_date, offset)
            if candidate_date is None or candidate_date not in basket_by_date.index:
                continue
            candidate = basket_by_date.loc[candidate_date]
            if isinstance(candidate, pd.DataFrame):
                candidate = candidate.iloc[-1]
            if float(candidate.get("basket_ret_1d", 0.0)) > 0:
                repair_date = int(candidate_date)
                repair_ratio = float(candidate.get("median_amount_ratio_20d", np.nan))
                break
        repair_dates.append(repair_date)
        repair_ratios.append(repair_ratio)
    result["repair_date"] = repair_dates
    result["repair_amount_ratio_20d"] = repair_ratios
    result["repair_confirmed"] = result["repair_date"].notna()
    result["repair_volume_group"] = np.where(
        result["repair_amount_ratio_20d"] >= repair_high,
        "high_repair_volume",
        "low_or_missing_repair_volume",
    )
    return result


def assign_sample_split(event_date: int, split_config: dict) -> str:
    for split_name, bounds in split_config.items():
        if len(bounds) == 2 and int(bounds[0]) <= event_date <= int(bounds[1]):
            return split_name
    return "outside_configured_split"


def summarize_gate(
    gate_id: str,
    gate_config: dict,
    forward_returns: pd.DataFrame,
    cost_bps: int,
    events: pd.DataFrame | None = None,
) -> dict:
    row: dict[str, Any] = {
        "gate_id": gate_id,
        "return_window_days": int(gate_config["return_window_days"]),
        "absolute_threshold_pct": float(gate_config["absolute_threshold_pct"]),
        "quantile_window_days": int(gate_config["quantile_window_days"]),
        "quantile_threshold_pct": float(gate_config["quantile_threshold_pct"]),
        "n_event_clusters": int(len(forward_returns)),
        "n_event_days": int(events["n_triggered_days"].sum())
            if events is not None and not events.empty else 0,
    }
    round_trip_cost = 2.0 * cost_bps / 10000.0
    for horizon in (5, 10, 20):
        column = f"basket_fwd_ret_{horizon}d"
        values = forward_returns[column].dropna() if column in forward_returns else pd.Series(dtype=float)
        net_values = values - round_trip_cost
        row[f"mean_fwd_ret_{horizon}d"] = float(values.mean()) if len(values) else np.nan
        row[f"mean_net_ret_{horizon}d"] = float(net_values.mean()) if len(values) else np.nan
        row[f"win_rate_{horizon}d"] = float((net_values > 0).mean()) if len(values) else np.nan
        row[f"n_fwd_{horizon}d"] = int(len(values))
    return row


def summarize_groups(
    forward_returns: pd.DataFrame,
    group_columns: list[str],
    cost_bps: int,
) -> pd.DataFrame:
    rows = []
    round_trip_cost = 2.0 * cost_bps / 10000.0
    if forward_returns.empty:
        return pd.DataFrame()
    for keys, group in forward_returns.groupby(group_columns, dropna=False):
        if not isinstance(keys, tuple):
            keys = (keys,)
        row = dict(zip(group_columns, keys))
        row["n_event_clusters"] = int(len(group))
        for horizon in (5, 10, 20):
            column = f"basket_fwd_ret_{horizon}d"
            values = group[column].dropna() if column in group else pd.Series(dtype=float)
            net_values = values - round_trip_cost
            row[f"mean_net_ret_{horizon}d"] = float(net_values.mean()) if len(values) else np.nan
            row[f"win_rate_{horizon}d"] = float((net_values > 0).mean()) if len(values) else np.nan
        rows.append(row)
    return pd.DataFrame(rows)


def build_candidate_forward_returns(
    core_basket: pd.DataFrame,
    index_prices: pd.DataFrame,
    calendar: np.ndarray,
    market_regime: pd.DataFrame,
) -> pd.DataFrame:
    rows = []
    for row_id, event_date in enumerate(core_basket["trade_date"].astype(int)):
        exec_date = trading_day_offset(calendar, event_date, 1)
        if exec_date is None or trading_day_offset(calendar, exec_date, 20) is None:
            continue
        rows.append({
            "event_cluster_id": row_id,
            "event_date": event_date,
            "exec_date": exec_date,
        })
    candidate_events = pd.DataFrame(rows)
    candidates = compute_forward_returns(
        candidate_events, pd.DataFrame(), core_basket, index_prices, calendar
    )
    return candidates.merge(
        market_regime.rename(columns={"trade_date": "event_date"}),
        on="event_date",
        how="left",
    )


def _event_exclusion_dates(
    events: pd.DataFrame,
    calendar: np.ndarray,
    buffer_days: int,
) -> set[int]:
    excluded: set[int] = set()
    for event_date in events["event_date"].astype(int):
        for offset in range(-buffer_days, buffer_days + 1):
            candidate = trading_day_offset(calendar, event_date, offset)
            if candidate is not None:
                excluded.add(int(candidate))
    return excluded


def run_placebo_tests(
    gate_id: str,
    real_returns: pd.DataFrame,
    candidate_returns: pd.DataFrame,
    calendar: np.ndarray,
    config: dict,
    random_seed: int,
) -> pd.DataFrame:
    if real_returns.empty:
        return pd.DataFrame()
    n_runs = int(config.get("n_runs", 1000))
    match_year = bool(config.get("match_by_year", True))
    match_regime = bool(config.get("match_by_market_regime", True))
    excluded = _event_exclusion_dates(real_returns, calendar, 5)
    candidates = candidate_returns[~candidate_returns["event_date"].isin(excluded)].copy()
    candidates["year"] = candidates["event_date"] // 10000
    real = real_returns.copy()
    real["year"] = real["event_date"] // 10000
    rng = np.random.default_rng(random_seed + sum(gate_id.encode("utf-8")))
    rows = []
    for horizon in (5, 10, 20):
        column = f"basket_fwd_ret_{horizon}d"
        usable_real = real.dropna(subset=[column]).copy()
        if usable_real.empty:
            continue
        pools = []
        for _, event in usable_real.iterrows():
            pool = candidates.dropna(subset=[column])
            if match_year:
                pool = pool[pool["year"] == event["year"]]
            if match_regime:
                pool = pool[pool["market_regime"] == event.get("market_regime", "unknown")]
            if not pool.empty:
                pools.append(pool[column].to_numpy(dtype=float))
        if not pools:
            continue
        sampled_means = []
        for _ in range(n_runs):
            draws = [pool[rng.integers(0, len(pool))] for pool in pools]
            sampled_means.append(float(np.mean(draws)))
        real_mean = float(usable_real[column].mean())
        distribution = np.asarray(sampled_means, dtype=float)
        p_value = float((1 + np.sum(distribution >= real_mean)) / (len(distribution) + 1))
        rows.append({
            "gate_id": gate_id,
            "horizon_days": horizon,
            "n_real_events": int(len(usable_real)),
            "n_matched_events": int(len(pools)),
            "match_coverage": float(len(pools) / len(usable_real)),
            "n_placebo_runs": n_runs,
            "real_mean_return": real_mean,
            "placebo_mean_return": float(distribution.mean()),
            "placebo_std_return": float(distribution.std(ddof=1)),
            "mean_diff": real_mean - float(distribution.mean()),
            "percentile_rank": float(np.mean(distribution <= real_mean)),
            "permutation_p_value": p_value,
            "significance_label": "significant" if p_value <= 0.05 else (
                "weak_significance" if p_value <= 0.10 else "not_significant"
            ),
        })
    return pd.DataFrame(rows)


def run_bootstrap_tests(
    gate_id: str,
    forward_returns: pd.DataFrame,
    config: dict,
    random_seed: int,
    cost_bps: int,
) -> pd.DataFrame:
    if forward_returns.empty:
        return pd.DataFrame()
    n_runs = int(config.get("n_runs", 1000))
    confidence = float(config.get("confidence_level", 0.90))
    alpha = (1.0 - confidence) / 2.0
    round_trip_cost = 2.0 * cost_bps / 10000.0
    rng = np.random.default_rng(random_seed + 10000 + sum(gate_id.encode("utf-8")))
    rows = []
    for horizon in (5, 10, 20):
        column = f"basket_fwd_ret_{horizon}d"
        values = forward_returns[column].dropna().to_numpy(dtype=float) - round_trip_cost
        if len(values) == 0:
            continue
        samples = rng.choice(values, size=(n_runs, len(values)), replace=True).mean(axis=1)
        low, high = np.quantile(samples, [alpha, 1.0 - alpha])
        rows.append({
            "gate_id": gate_id,
            "horizon_days": horizon,
            "n_events": int(len(values)),
            "n_bootstrap_runs": n_runs,
            "confidence_level": confidence,
            "bootstrap_mean_net": float(samples.mean()),
            "ci_low": float(low),
            "ci_high": float(high),
            "ci_contains_zero": bool(low <= 0 <= high),
        })
    return pd.DataFrame(rows)


def evaluate_threshold_acceptance(
    gate_summary: pd.DataFrame,
    market_summary: pd.DataFrame,
    placebo: pd.DataFrame,
    bootstrap: pd.DataFrame,
    basket_loo: pd.DataFrame,
    base_go_nogo: dict,
    validation_config: dict,
) -> dict:
    primary_gate = str(validation_config["primary_gate_id"])
    acceptance = validation_config.get("acceptance", {})
    primary = gate_summary[gate_summary["gate_id"] == primary_gate]
    reasons = []
    event_go = True
    if primary.empty:
        return {
            "primary_gate_id": primary_gate,
            "event_GO": False,
            "top1_GO": False,
            "trade_GO": False,
            "classification": "missing_primary_gate",
            "reasons": ["primary_gate_missing"],
        }
    primary_row = primary.iloc[0]
    if int(primary_row["n_event_clusters"]) < int(acceptance.get("min_event_clusters", 5)):
        event_go = False
        reasons.append("insufficient_event_clusters")
    if float(primary_row.get("mean_net_ret_20d", np.nan)) <= 0:
        event_go = False
        reasons.append("non_positive_mean_net_20d")
    if float(primary_row.get("win_rate_20d", np.nan)) <= float(acceptance.get("min_win_rate_20d", 0.5)):
        event_go = False
        reasons.append("insufficient_win_rate_20d")

    primary_placebo = placebo[
        (placebo["gate_id"] == primary_gate) & (placebo["horizon_days"] == 20)
    ] if not placebo.empty else pd.DataFrame()
    if primary_placebo.empty or float(primary_placebo.iloc[0]["permutation_p_value"]) > float(
        acceptance.get("max_placebo_p_value", 0.10)
    ):
        event_go = False
        reasons.append("placebo_significance_failure")
    elif float(primary_placebo.iloc[0].get("match_coverage", 0.0)) < float(
        acceptance.get("min_placebo_match_coverage", 0.80)
    ):
        event_go = False
        reasons.append("placebo_match_coverage_failure")

    primary_bootstrap = bootstrap[
        (bootstrap["gate_id"] == primary_gate) & (bootstrap["horizon_days"] == 20)
    ] if not bootstrap.empty else pd.DataFrame()
    if bool(acceptance.get("require_bootstrap_ci_low_positive", True)):
        if primary_bootstrap.empty or float(primary_bootstrap.iloc[0]["ci_low"]) <= 0:
            event_go = False
            reasons.append("bootstrap_ci_failure")

    regimes = market_summary[
        (market_summary["gate_id"] == primary_gate)
        & (market_summary["market_regime"] != "unknown")
    ] if not market_summary.empty else pd.DataFrame()
    non_negative_regimes = int((regimes["mean_net_ret_20d"] >= 0).sum()) if not regimes.empty else 0
    if non_negative_regimes < int(acceptance.get("min_non_negative_regimes", 2)):
        event_go = False
        reasons.append("market_regime_concentration")

    if not basket_loo.empty:
        primary_loo = basket_loo[basket_loo["gate_id"] == primary_gate]
        if not primary_loo.empty:
            loo_means = primary_loo.groupby("removed_stock")["loo_basket_ret_20d"].mean()
            if (loo_means <= 0).any():
                event_go = False
                reasons.append("basket_loo_failure")

    top1_go = bool(base_go_nogo.get("top1_GO", False))
    trade_go = event_go and top1_go
    classification = (
        "both_valid" if event_go and top1_go else
        "basket_valid_top1_invalid" if event_go else
        "basket_invalid_top1_valid" if top1_go else
        "both_invalid"
    )
    return {
        "primary_gate_id": primary_gate,
        "event_GO": event_go,
        "top1_GO": top1_go,
        "trade_GO": trade_go,
        "classification": classification,
        "non_negative_regimes": non_negative_regimes,
        "reasons": reasons,
    }


def _markdown_table(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "_无可用数据_"
    try:
        return frame.to_markdown(index=False, floatfmt=".4f")
    except ImportError:
        return "```text\n" + frame.to_string(index=False) + "\n```"


def generate_report(
    gate_summary: pd.DataFrame,
    market_summary: pd.DataFrame,
    volume_summary: pd.DataFrame,
    sample_summary: pd.DataFrame,
    placebo: pd.DataFrame,
    bootstrap: pd.DataFrame,
    top1_summary: pd.DataFrame,
    top1_market_summary: pd.DataFrame,
    top1_concentration: pd.DataFrame,
    top1_loo: pd.DataFrame,
    acceptance: dict,
) -> str:
    lines = [
        "# 光刻胶恐慌修复阈值验证报告",
        "",
        f"生成时间：{datetime.now():%Y-%m-%d %H:%M:%S}",
        "",
        "状态：RESEARCH ONLY，不构成投资建议。",
        "",
        "## 最终结论",
        "",
        f"- event_GO: **{acceptance['event_GO']}**",
        f"- top1_GO: **{acceptance['top1_GO']}**",
        f"- trade_GO: **{acceptance['trade_GO']}**",
        f"- classification: `{acceptance['classification']}`",
        f"- reasons: `{acceptance['reasons']}`",
        "",
        "## Gate 对比", "", _markdown_table(gate_summary), "",
        "## 市场状态分层", "", _markdown_table(market_summary), "",
        "## 成交量分组", "", _markdown_table(volume_summary), "",
        "## 样本外与逐年结果", "", _markdown_table(sample_summary), "",
        "## Placebo 检验", "", _markdown_table(placebo), "",
        "## Bootstrap 置信区间", "", _markdown_table(bootstrap), "",
        "## Top1 同步诊断", "", _markdown_table(top1_summary), "",
        "## Top1 市场状态分层", "", _markdown_table(top1_market_summary), "",
        "## Top1 贡献集中度", "", _markdown_table(top1_concentration), "",
        "## Top1 Leave-One-Out", "", _markdown_table(top1_loo), "",
        "## 解释边界", "",
        "- 主 gate 独立冻结，辅助 gate 不用于反向挑参。",
        "- Placebo 按年份和市场状态匹配，并排除真实事件附近日期。",
        "- 资金流向仍为未实现的辅助诊断，不进入主 gate。",
    ]
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    research_config = load_yaml(Path(args.research_config))
    universe_config = load_yaml(Path(args.universe_config))
    validation_config = research_config.get("threshold_validation", {})
    if not validation_config.get("enabled", False):
        raise RuntimeError("threshold_validation is not enabled in research config")

    input_dir = Path(args.input_dir)
    output_dir = Path(args.out_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    core_basket_all, universe_df = load_validation_inputs(input_dir)
    configured_range = research_config.get("research", {}).get("date_range", {})
    start = int(args.start or configured_range.get("start", core_basket_all["trade_date"].min()))
    end = int(args.end or configured_range.get("end", core_basket_all["trade_date"].max()))
    target_basket = core_basket_all[
        (core_basket_all["trade_date"] >= start) & (core_basket_all["trade_date"] <= end)
    ].copy()
    if target_basket.empty:
        raise RuntimeError("No core basket rows in requested date range")
    # Keep the complete frozen series for historical warmup and forward exits.
    # Event creation is restricted to the requested interval below.
    core_basket = core_basket_all.copy()
    history_start = int(core_basket["trade_date"].min())
    data_end = int(core_basket["trade_date"].max())

    all_codes = universe_df["ts_code"].unique().tolist()
    prices = load_prices(history_start, data_end, all_codes)
    calendar = build_trading_calendar(prices)
    regime_config = validation_config.get("market_regime", {})
    index_codes = [regime_config.get("primary_index", "000300.SH"), *regime_config.get("comparison_indices", [])]
    index_codes = list(dict.fromkeys(str(code) for code in index_codes))
    index_prices = load_index_prices(history_start, data_end, index_codes)
    index_coverage = summarize_index_coverage(
        index_prices, index_codes, target_basket["trade_date"]
    )
    market_regime = compute_market_regime(index_prices, regime_config)
    candidate_returns = build_candidate_forward_returns(
        target_basket, index_prices, calendar, market_regime
    )

    limit_status = load_limit_status(history_start, data_end, all_codes)
    suspend_status = load_suspend_status(history_start, data_end, all_codes)
    stock_status = load_stock_status()
    eligibility = universe_config.get("eligibility", {})
    top1_config = research_config.get("top1_rules", {})
    split_config = validation_config.get("sample_split", {})
    random_seed = int(validation_config.get("random_seed", 20260710))
    max_gap = int(validation_config.get("event_clustering", {}).get("max_gap_trading_days", 5))

    all_events = []
    all_forward = []
    all_trades = []
    all_basket_loo = []
    all_top1_concentration = []
    all_top1_loo = []
    gate_rows = []
    placebo_frames = []
    bootstrap_frames = []
    base_go_by_gate: dict[str, dict] = {}

    for gate_id, gate_config in validation_config.get("gates", {}).items():
        gated = build_threshold_gate(core_basket, gate_id, gate_config)
        gated_in_range = gated[
            (gated["trade_date"] >= start) & (gated["trade_date"] <= end)
        ].copy()
        events = cluster_threshold_events(gated_in_range, calendar, max_gap)
        events = attach_event_diagnostics(
            events, core_basket, market_regime, calendar,
            validation_config.get("volume_groups", {}),
        )
        if events.empty:
            gate_rows.append(summarize_gate(
                gate_id, gate_config, pd.DataFrame(), args.cost_bps, events
            ))
            continue
        events["sample_split"] = events["event_date"].apply(
            lambda date: assign_sample_split(int(date), split_config)
        )
        events["event_year"] = events["event_date"] // 10000
        forward = compute_forward_returns(events, prices, core_basket, index_prices, calendar)
        forward["gate_id"] = gate_id
        diagnostics = events[[
            "event_cluster_id", "event_date", "gate_id", "market_regime",
            "panic_volume_group", "repair_volume_group", "repair_confirmed",
            "sample_split", "event_year",
        ]]
        forward = forward.merge(
            diagnostics, on=["event_cluster_id", "event_date", "gate_id"], how="left"
        )
        trades = evaluate_top1_rules(
            events, prices, core_basket, universe_df, calendar, top1_config,
            args.cost_bps, limit_status=limit_status, suspend_status=suspend_status,
            stock_status=stock_status, eligibility=eligibility,
        )
        if not trades.empty:
            trades["gate_id"] = gate_id
            trades = trades.merge(
                events[["event_date", "market_regime", "sample_split", "event_year"]],
                on="event_date", how="left",
            )
        basket_loo = compute_basket_leave_one_out(
            forward, events, prices, core_basket, universe_df, calendar
        )
        if not basket_loo.empty:
            basket_loo["gate_id"] = gate_id
        concentration = compute_concentration_diagnostics(trades)
        top1_loo = compute_leave_one_out(trades)
        if not concentration.empty:
            concentration["gate_id"] = gate_id
            all_top1_concentration.append(concentration)
        if not top1_loo.empty:
            top1_loo["gate_id"] = gate_id
            all_top1_loo.append(top1_loo)
        robustness = compute_robustness(forward, trades, research_config)
        base_go_by_gate[gate_id] = evaluate_go_nogo(
            forward, trades, concentration, top1_loo, basket_loo, robustness,
            research_config.get("go_nogo", {}),
            ["confirmation_entry", "top1_residual_bucket", "robustness_aux_gates"],
        )

        gate_rows.append(summarize_gate(
            gate_id, gate_config, forward, args.cost_bps, events
        ))
        placebo_frames.append(run_placebo_tests(
            gate_id, forward, candidate_returns, calendar,
            validation_config.get("significance_tests", {}).get("placebo", {}),
            random_seed,
        ))
        bootstrap_frames.append(run_bootstrap_tests(
            gate_id, forward,
            validation_config.get("significance_tests", {}).get("bootstrap", {}),
            random_seed, args.cost_bps,
        ))
        all_events.append(events)
        all_forward.append(forward)
        if not trades.empty:
            all_trades.append(trades)
        if not basket_loo.empty:
            all_basket_loo.append(basket_loo)

    events_df = pd.concat(all_events, ignore_index=True) if all_events else pd.DataFrame()
    forward_df = pd.concat(all_forward, ignore_index=True) if all_forward else pd.DataFrame()
    trades_df = pd.concat(all_trades, ignore_index=True) if all_trades else pd.DataFrame()
    basket_loo_df = pd.concat(all_basket_loo, ignore_index=True) if all_basket_loo else pd.DataFrame()
    top1_concentration_df = pd.concat(
        all_top1_concentration, ignore_index=True
    ) if all_top1_concentration else pd.DataFrame()
    top1_loo_df = pd.concat(all_top1_loo, ignore_index=True) if all_top1_loo else pd.DataFrame()
    gate_summary = pd.DataFrame(gate_rows)
    placebo_df = pd.concat(placebo_frames, ignore_index=True) if placebo_frames else pd.DataFrame()
    bootstrap_df = pd.concat(bootstrap_frames, ignore_index=True) if bootstrap_frames else pd.DataFrame()
    market_summary = summarize_groups(forward_df, ["gate_id", "market_regime"], args.cost_bps)
    volume_summary = summarize_groups(
        forward_df, ["gate_id", "panic_volume_group", "repair_volume_group"], args.cost_bps
    )
    sample_summary = summarize_groups(
        forward_df, ["gate_id", "sample_split", "event_year"], args.cost_bps
    )
    top1_summary = pd.DataFrame()
    top1_market_summary = pd.DataFrame()
    if not trades_df.empty:
        top1_summary = trades_df.groupby(
            ["gate_id", "top1_rule", "exit_rule"], dropna=False
        ).agg(
            n_trades=("return_net", "size"),
            mean_net_return=("return_net", "mean"),
            win_rate=("return_net", lambda values: float((values > 0).mean())),
            n_stocks=("ts_code", "nunique"),
        ).reset_index()
        top1_market_summary = trades_df.groupby(
            ["gate_id", "top1_rule", "exit_rule", "market_regime"], dropna=False
        ).agg(
            n_trades=("return_net", "size"),
            mean_net_return=("return_net", "mean"),
            win_rate=("return_net", lambda values: float((values > 0).mean())),
        ).reset_index()

    primary_gate = str(validation_config["primary_gate_id"])
    acceptance = evaluate_threshold_acceptance(
        gate_summary, market_summary, placebo_df, bootstrap_df, basket_loo_df,
        base_go_by_gate.get(primary_gate, {}), validation_config,
    )
    gate_summary["event_go_raw"] = gate_summary["gate_id"].map(
        lambda gate_id: bool(base_go_by_gate.get(str(gate_id), {}).get("event_GO", False))
    )
    gate_summary["event_go_after_significance"] = pd.NA
    gate_summary.loc[
        gate_summary["gate_id"] == primary_gate, "event_go_after_significance"
    ] = bool(acceptance["event_GO"])
    outputs = {
        "photoresist_threshold_events.csv": events_df,
        "photoresist_threshold_gate_compare.csv": gate_summary,
        "photoresist_threshold_forward_returns.csv": forward_df,
        "photoresist_threshold_by_market_regime.csv": market_summary,
        "photoresist_threshold_volume_groups.csv": volume_summary,
        "photoresist_threshold_walkforward.csv": sample_summary,
        "photoresist_threshold_placebo_test.csv": placebo_df,
        "photoresist_threshold_bootstrap_ci.csv": bootstrap_df,
        "photoresist_threshold_top1_compare.csv": top1_summary,
        "photoresist_threshold_top1_by_market_regime.csv": top1_market_summary,
        "photoresist_threshold_top1_concentration.csv": top1_concentration_df,
        "photoresist_threshold_top1_leave_one_out.csv": top1_loo_df,
        "photoresist_threshold_basket_loo.csv": basket_loo_df,
    }
    for filename, frame in outputs.items():
        frame.to_csv(output_dir / filename, index=False)

    report = generate_report(
        gate_summary, market_summary, volume_summary, sample_summary,
        placebo_df, bootstrap_df, top1_summary, top1_market_summary,
        top1_concentration_df, top1_loo_df, acceptance,
    )
    (output_dir / "photoresist_threshold_validation_report.md").write_text(
        report, encoding="utf-8"
    )
    config_hash = hashlib.sha256(
        json.dumps(validation_config, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    manifest = {
        "schema": "photoresist_panic_threshold_validation.v1",
        "status": "RESEARCH_ONLY",
        "date_range": {
            "requested_start": start,
            "requested_end": end,
            "actual_start": int(target_basket["trade_date"].min()),
            "actual_end": int(target_basket["trade_date"].max()),
            "history_warmup_start": int(core_basket["trade_date"].min()),
        },
        "primary_gate_id": primary_gate,
        "auxiliary_gate_ids": [
            gate_id for gate_id in validation_config.get("gates", {})
            if gate_id != primary_gate
        ],
        "gate_ids": list(validation_config.get("gates", {}).keys()),
        "sample_split": split_config,
        "walkforward_config": {
            "mode": "fixed_gate_yearly_diagnostics",
            "thresholds_reestimated_in_test": False,
        },
        "market_regime_definition": regime_config,
        "index_data_coverage": index_coverage,
        "placebo_config": validation_config.get("significance_tests", {}).get("placebo", {}),
        "bootstrap_config": validation_config.get("significance_tests", {}).get("bootstrap", {}),
        "random_seed": random_seed,
        "config_sha256": config_hash,
        "data_sources_used_in_computation": {
            "frozen_core_basket": str(input_dir / "photoresist_core_basket_with_gate.csv"),
            "frozen_universe": str(input_dir / "photoresist_universe_snapshot.csv"),
            "prices_adj": True,
            "index_daily": index_codes,
            "limit_status": limit_status is not None,
            "suspend_status": suspend_status is not None,
            "stock_status": stock_status is not None,
        },
        "not_implemented_features": ["fund_flow_diagnostics"],
        "acceptance": acceptance,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "outputs": list(outputs.keys()) + [
            "photoresist_threshold_validation_report.md",
            "photoresist_threshold_manifest.json",
        ],
    }
    (output_dir / "photoresist_threshold_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    print(json.dumps(acceptance, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

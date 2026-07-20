"""Analyze 5% take-profit hit rates for frozen primary_5d signals."""
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
    PRICES_DIR, build_trading_calendar, compute_amount_20d_avg,
    compute_listing_age, load_index_prices, load_limit_status, load_stock_status,
    load_suspend_status, trading_day_offset,
)
from evaluate_photoresist_panic_reversal import (  # noqa: E402
    _get_available_stocks_v2, _select_top1_stock,
)
from validate_photoresist_panic_thresholds import (  # noqa: E402
    build_threshold_gate, compute_market_regime, load_validation_inputs, load_yaml,
)

DEFAULT_CONFIG = ROOT / "configs" / "photoresist_panic_research.yaml"
DEFAULT_INPUT = ROOT / "outputs" / "analysis" / "photoresist_panic_threshold_validation"
DEFAULT_FROZEN = ROOT / "outputs" / "analysis" / "photoresist_panic_bbb_full"
DEFAULT_OUTPUT = ROOT / "outputs" / "analysis" / "photoresist_panic_take_profit"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze primary_5d 5% take-profit hit rates")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--input-dir", default=str(DEFAULT_INPUT))
    parser.add_argument("--frozen-dir", default=str(DEFAULT_FROZEN))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--gate-id", default="primary_5d")
    parser.add_argument("--max-hold-days", type=int, default=20)
    parser.add_argument("--cooldown-days", type=int, default=5)
    return parser.parse_args()


def load_adjusted_ohlc(start: int, end: int, codes: list[str]) -> pd.DataFrame:
    wanted = ["ts_code", "trade_date", "adj_open", "adj_high", "adj_low",
              "adj_close", "pct_chg", "amount"]
    chunks = []
    years = set(range(start // 10000, end // 10000 + 1))
    for path in PRICES_DIR.rglob("*.parquet"):
        year_parts = [part for part in path.parts if part.startswith("year=")]
        if year_parts and int(year_parts[-1].split("=", 1)[1]) not in years:
            continue
        frame = pd.read_parquet(path)
        if not {"ts_code", "trade_date", "adj_close"}.issubset(frame.columns):
            continue
        frame = frame[frame["ts_code"].astype(str).isin(codes)].copy()
        if frame.empty:
            continue
        for adjusted, raw in (("adj_open", "open"), ("adj_high", "high"), ("adj_low", "low")):
            if adjusted not in frame and raw in frame and "close" in frame:
                frame[adjusted] = frame[raw] * frame["adj_close"] / frame["close"]
        chunks.append(frame[[column for column in wanted if column in frame]])
    if not chunks:
        raise RuntimeError("No adjusted OHLC data found")
    result = pd.concat(chunks, ignore_index=True)
    result["trade_date"] = pd.to_numeric(result["trade_date"], errors="coerce")
    result = result.dropna(subset=["trade_date", "adj_close"])
    result["trade_date"] = result["trade_date"].astype(int)
    result = result[(result["trade_date"] >= start) & (result["trade_date"] <= end)]
    return result.drop_duplicates(["ts_code", "trade_date"]).sort_values(["ts_code", "trade_date"])


def build_online_first_trigger_signals(gated: pd.DataFrame, calendar: np.ndarray,
                                       max_hold_days: int, cooldown_days: int) -> pd.DataFrame:
    trigger_map = gated.set_index("trade_date")["validation_gate_triggered"].to_dict()
    rows, state, active_until, false_streak = [], "IDLE", -1, 0
    for position, trade_date in enumerate(calendar):
        triggered = bool(trigger_map.get(int(trade_date), False))
        if state == "IDLE" and triggered:
            exec_date = trading_day_offset(calendar, int(trade_date), 1)
            if exec_date is None:
                continue
            rows.append({"signal_type": "online_first_trigger", "event_date": int(trade_date),
                         "exec_date": int(exec_date), "event_cluster_id": len(rows)})
            active_until = int(np.searchsorted(calendar, exec_date)) + max_hold_days
            state, false_streak = "ACTIVE", 0
        elif state == "ACTIVE" and position >= active_until:
            state, false_streak = "COOLDOWN", 0 if triggered else 1
        elif state == "COOLDOWN":
            false_streak = 0 if triggered else false_streak + 1
            if false_streak >= cooldown_days:
                state = "IDLE"
    return pd.DataFrame(rows)


def build_last_trigger_signals(path: Path, gate_id: str) -> pd.DataFrame:
    events = pd.read_csv(path)
    result = events[events["gate_id"] == gate_id][
        ["event_cluster_id", "event_date", "exec_date"]].copy()
    result["signal_type"] = "retrospective_last_trigger"
    return result


def simulate_take_profit(ts_code: str, event: pd.Series, prices: pd.DataFrame,
                         calendar: np.ndarray, horizon: int, target_net: float,
                         round_trip_cost: float, touch_mode: str) -> dict | None:
    exec_date = int(event["exec_date"])
    entry = prices[(prices["ts_code"] == ts_code) & (prices["trade_date"] == exec_date)]
    if entry.empty:
        return None
    entry_price = float(entry.iloc[-1]["adj_close"])
    target_price = entry_price * (1.0 + target_net + round_trip_cost)
    exit_limit = trading_day_offset(calendar, exec_date, horizon)
    if exit_limit is None:
        return None
    path = prices[(prices["ts_code"] == ts_code) & (prices["trade_date"] > exec_date)
                  & (prices["trade_date"] <= exit_limit)].sort_values("trade_date")
    if path.empty:
        return None
    trigger_column = "adj_close" if touch_mode == "close" else "adj_high"
    touched = path[path[trigger_column] >= target_price]
    hit = not touched.empty
    if hit:
        exit_date, exit_price, reason = int(touched.iloc[0]["trade_date"]), target_price, "take_profit"
    else:
        exit_date, exit_price, reason = int(path.iloc[-1]["trade_date"]), float(path.iloc[-1]["adj_close"]), "timeout"
    gross_return = exit_price / entry_price - 1.0
    return {
        "ts_code": ts_code, "entry_date": exec_date, "entry_price": entry_price,
        "exit_date": exit_date, "exit_price": exit_price, "exit_reason": reason,
        "target_hit": hit, "hit_date": exit_date if hit else np.nan,
        "days_to_hit": int(np.searchsorted(calendar, exit_date) - np.searchsorted(calendar, exec_date)) if hit else np.nan,
        "gross_return": gross_return, "net_return": gross_return - round_trip_cost,
        "horizon_days": horizon, "touch_mode": touch_mode,
        "round_trip_cost_bps": int(round_trip_cost * 10000), "target_net": target_net,
    }


def evaluate_signals(signals: pd.DataFrame, prices: pd.DataFrame, core_basket: pd.DataFrame,
                     universe: pd.DataFrame, calendar: np.ndarray, config: dict,
                     limit_status: pd.DataFrame | None, suspend_status: pd.DataFrame | None,
                     stock_status: pd.DataFrame | None) -> pd.DataFrame:
    listing_age_map = compute_listing_age(prices, calendar)
    amount_map = compute_amount_20d_avg(prices)
    eligibility = config.get("eligibility", {})
    top1_config = config.get("top1_rules", {})
    rules = [name for name in ("top1_strength", "top1_mid_drop", "top1_liquidity_core")
             if top1_config.get(name, {}).get("enabled", True)]
    rows = []
    for _, event in signals.iterrows():
        available = _get_available_stocks_v2(
            int(event["event_date"]), int(event["exec_date"]), universe, prices,
            calendar, listing_age_map, amount_map, limit_status, suspend_status,
            stock_status, eligibility,
        )
        if available.empty:
            continue
        for rule in rules:
            selected = _select_top1_stock(
                available, rule, top1_config.get(rule, {}), int(event["event_date"]),
                core_basket, prices, int(event["exec_date"]), amount_map,
            )
            if selected is None or selected.empty:
                continue
            code = str(selected.iloc[0]["ts_code"])
            for horizon in (5, 10, 20):
                for touch_mode in ("close", "intraday_high"):
                    for cost_bps in (40, 100):
                        result = simulate_take_profit(
                            code, event, prices, calendar, horizon, 0.05,
                            cost_bps / 10000.0, touch_mode,
                        )
                        if result is None:
                            continue
                        result.update({
                            "signal_type": event["signal_type"],
                            "event_date": int(event["event_date"]),
                            "event_cluster_id": int(event["event_cluster_id"]),
                            "market_regime": event.get("market_regime", "unknown"),
                            "top1_rule": rule,
                        })
                        rows.append(result)
    return pd.DataFrame(rows)


def summarize(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame()
    group_cols = ["signal_type", "market_regime", "top1_rule", "horizon_days",
                  "touch_mode", "round_trip_cost_bps"]
    return trades.groupby(group_cols, dropna=False).agg(
        n_trades=("target_hit", "size"),
        target_hits=("target_hit", "sum"),
        hit_rate=("target_hit", "mean"),
        median_days_to_hit=("days_to_hit", "median"),
        mean_net_return=("net_return", "mean"),
        median_net_return=("net_return", "median"),
        positive_return_rate=("net_return", lambda values: float((values > 0).mean())),
    ).reset_index()


def _wilson_interval(hits: int, total: int, z: float = 1.96) -> tuple[float, float]:
    if total == 0:
        return np.nan, np.nan
    rate = hits / total
    denominator = 1.0 + z * z / total
    center = (rate + z * z / (2.0 * total)) / denominator
    half_width = z * np.sqrt(
        rate * (1.0 - rate) / total + z * z / (4.0 * total * total)
    ) / denominator
    return float(center - half_width), float(center + half_width)


def summarize_primary_conditions(trades: pd.DataFrame) -> pd.DataFrame:
    primary = trades[
        (trades["signal_type"] == "online_first_trigger")
        & (trades["market_regime"].isin(["bull", "neutral"]))
    ]
    rows = []
    for keys, group in primary.groupby(
        ["top1_rule", "horizon_days", "touch_mode", "round_trip_cost_bps"]
    ):
        hits, total = int(group["target_hit"].sum()), int(len(group))
        low, high = _wilson_interval(hits, total)
        rows.append({
            "top1_rule": keys[0], "horizon_days": keys[1],
            "touch_mode": keys[2], "round_trip_cost_bps": keys[3],
            "n_trades": total, "target_hits": hits, "hit_rate": hits / total,
            "hit_rate_ci95_low": low, "hit_rate_ci95_high": high,
            "median_days_to_hit": float(group["days_to_hit"].median()),
            "mean_net_return": float(group["net_return"].mean()),
            "positive_return_rate": float((group["net_return"] > 0).mean()),
        })
    return pd.DataFrame(rows)


def generate_report(summary: pd.DataFrame, primary_summary: pd.DataFrame) -> str:
    table = summary.to_markdown(index=False, floatfmt=".4f") if not summary.empty else "_无数据_"
    primary_table = primary_summary.to_markdown(index=False, floatfmt=".4f") if not primary_summary.empty else "_无数据_"
    return "\n".join([
        "# 光刻胶 primary_5d 恐慌反转 5% 止盈研究", "",
        f"生成时间：{datetime.now():%Y-%m-%d %H:%M:%S}", "",
        "状态：RESEARCH ONLY，不构成投资建议。", "",
        "## 口径", "",
        "- 入场：事件识别后下一交易日收盘。",
        "- 主信号：在线 first-trigger；历史 last-trigger 仅作对照。",
        "- 目标：扣除往返成本后净收益达到5%。",
        "- close：收盘价触及目标，保守口径。",
        "- intraday_high：复权日内最高价触及目标，代表可成交上限，未建模盘口排队。",
        "- 入场日不计算止盈，最早从下一交易日开始触发。", "",
        "## 主结果：在线首次触发 + bull/neutral", "", primary_table, "",
        "## 汇总", "", table, "",
        "## 边界", "",
        "- 当前Top1规则尚未通过正式GO，本报告只回答历史命中率。",
        "- 日内最高价触及不等于限价单必然成交。",
        "- 未触及5%时按固定持有期最后一个收盘价退出。",
    ])


def main() -> int:
    args = parse_args()
    config = load_yaml(Path(args.config))
    universe_config = load_yaml(ROOT / "configs" / "photoresist_universe.yaml")
    validation = config["threshold_validation"]
    frozen_dir, input_dir, out_dir = Path(args.frozen_dir), Path(args.input_dir), Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    core, universe = load_validation_inputs(frozen_dir)
    codes = universe["ts_code"].astype(str).unique().tolist()
    start, end = int(core.trade_date.min()), int(core.trade_date.max())
    prices = load_adjusted_ohlc(start, end, codes)
    calendar = build_trading_calendar(prices)
    gated = build_threshold_gate(core, args.gate_id, validation["gates"][args.gate_id])
    online = build_online_first_trigger_signals(
        gated, calendar, args.max_hold_days, args.cooldown_days)
    last = build_last_trigger_signals(input_dir / "photoresist_threshold_events.csv", args.gate_id)
    regime_cfg = validation["market_regime"]
    index_prices = load_index_prices(start, end, [regime_cfg["primary_index"]])
    regime = compute_market_regime(index_prices, regime_cfg)
    regime_map = regime.set_index("trade_date")["market_regime"]
    signals = pd.concat([online, last], ignore_index=True)
    signals["market_regime"] = signals["event_date"].map(regime_map).fillna("unknown")
    limit_status = load_limit_status(start, end, codes)
    suspend_status = load_suspend_status(start, end, codes)
    stock_status = load_stock_status()
    merged_config = {"eligibility": universe_config.get("eligibility", {}),
                     "top1_rules": config.get("top1_rules", {})}
    trades = evaluate_signals(signals, prices, core, universe, calendar, merged_config,
                              limit_status, suspend_status, stock_status)
    summary = summarize(trades)
    primary_summary = summarize_primary_conditions(trades)
    trades.to_csv(out_dir / "photoresist_take_profit_trades.csv", index=False)
    summary.to_csv(out_dir / "photoresist_take_profit_summary.csv", index=False)
    primary_summary.to_csv(out_dir / "photoresist_take_profit_primary_summary.csv", index=False)
    (out_dir / "photoresist_take_profit_report.md").write_text(
        generate_report(summary, primary_summary), encoding="utf-8")
    manifest = {
        "schema": "photoresist_take_profit.v1", "status": "RESEARCH_ONLY",
        "gate_id": args.gate_id, "target_net": 0.05,
        "entry": "t+1 close", "touch_starts": "trading day after entry",
        "horizons": [5, 10, 20], "touch_modes": ["close", "intraday_high_adjusted"],
        "round_trip_cost_bps": [40, 100], "online_max_hold_days": args.max_hold_days,
        "cooldown_days": args.cooldown_days, "frozen_gate_unchanged": True,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }
    (out_dir / "photoresist_take_profit_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(summary.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

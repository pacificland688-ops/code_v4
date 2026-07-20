"""Generate a research-only live alert for the frozen primary_5d signal."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from build_photoresist_panic_events import (  # noqa: E402
    build_basket_daily, build_trading_calendar, load_index_prices, load_limit_status,
    load_prices, load_stock_status, load_suspend_status,
)
from validate_photoresist_panic_thresholds import (  # noqa: E402
    build_threshold_gate, compute_market_regime, load_validation_inputs, load_yaml,
)

DEFAULT_RESEARCH = ROOT / "configs" / "photoresist_panic_research.yaml"
DEFAULT_UNIVERSE = ROOT / "configs" / "photoresist_universe.yaml"
DEFAULT_MONITOR = ROOT / "configs" / "photoresist_panic_monitor.yaml"
DEFAULT_FROZEN = ROOT / "outputs" / "analysis" / "photoresist_panic_bbb_full"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Monitor photoresist primary_5d panic")
    parser.add_argument("--as-of", default=date.today().strftime("%Y%m%d"))
    parser.add_argument("--research-config", default=str(DEFAULT_RESEARCH))
    parser.add_argument("--universe-config", default=str(DEFAULT_UNIVERSE))
    parser.add_argument("--monitor-config", default=str(DEFAULT_MONITOR))
    parser.add_argument("--frozen-dir", default=str(DEFAULT_FROZEN))
    parser.add_argument("--out-dir", default=None)
    parser.add_argument("--refresh-tushare", action="store_true")
    parser.add_argument("--allow-universe-carry-forward", action="store_true")
    return parser.parse_args()


def _load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def classify_severity(triggered: bool, basket_return: float, percentile: float,
                      breadth: float, config: dict) -> str:
    if triggered:
        if basket_return <= float(config["l4_absolute_return"]) or (
            percentile <= float(config["l4_percentile"])
            and breadth >= float(config["l4_breadth"])
        ):
            return "PANIC_L4"
        if basket_return <= float(config["l3_absolute_return"]) or percentile <= float(config["l3_percentile"]):
            return "PANIC_L3"
        if basket_return <= float(config["l2_absolute_return"]):
            return "PANIC_L2"
        return "PANIC_L1"
    if basket_return < 0 and percentile <= float(config["watch_percentile"]):
        return "WATCH"
    return "NORMAL"


def data_is_stale(latest_date: int, requested_date: int, max_days: int) -> bool:
    latest = datetime.strptime(str(latest_date), "%Y%m%d").date()
    requested = datetime.strptime(str(requested_date), "%Y%m%d").date()
    return (requested - latest).days > max_days


def _refresh_prices(prices: pd.DataFrame, codes: list[str], start: int, end: int) -> tuple[pd.DataFrame, dict]:
    if start > end:
        return prices, {"requested": False, "rows": 0}
    from data.adjust import PriceAdjuster
    from data.tushare_client import get_client

    client = get_client()
    raw = client._call_api(
        client.pro.daily, ts_code=",".join(codes),
        start_date=str(start), end_date=str(end),
    )
    factors = client.get_adj_factor(
        codes, str(start), str(end), use_cache=False, allow_partial=False, _write_cache=False
    )
    if raw.empty or factors.empty:
        return prices, {"requested": True, "rows": 0, "error": "tushare_price_refresh_failed"}
    raw["trade_date"] = pd.to_numeric(raw["trade_date"], errors="coerce").astype("int32")
    factors["trade_date"] = pd.to_numeric(
        factors["trade_date"], errors="coerce"
    ).astype("int32")
    adjusted = PriceAdjuster(client=client).compute_adj_prices(raw, factors)
    keep = [column for column in prices.columns if column in adjusted.columns]
    combined = pd.concat([prices, adjusted[keep]], ignore_index=True)
    combined = combined.drop_duplicates(["ts_code", "trade_date"], keep="last")
    return combined.sort_values(["ts_code", "trade_date"]), {
        "requested": True, "rows": int(len(adjusted)),
        "min_date": int(adjusted["trade_date"].min()), "max_date": int(adjusted["trade_date"].max()),
    }


def _refresh_indices(index_prices: pd.DataFrame, codes: list[str], start: int, end: int) -> tuple[pd.DataFrame, dict]:
    if start > end:
        return index_prices, {"requested": False, "rows": 0}
    from data.tushare_client import get_client

    frames = []
    client = get_client()
    for code in codes:
        frame = client._call_api(
            client.pro.index_daily, ts_code=code,
            start_date=str(start), end_date=str(end),
        )
        if not frame.empty:
            frame["trade_date"] = pd.to_numeric(
                frame["trade_date"], errors="coerce"
            ).astype("int32")
            frames.append(frame)
    if not frames:
        return index_prices, {"requested": True, "rows": 0, "error": "tushare_index_refresh_failed"}
    fetched = pd.concat(frames, ignore_index=True)
    keep = [column for column in index_prices.columns if column in fetched.columns]
    combined = pd.concat([index_prices, fetched[keep]], ignore_index=True)
    combined = combined.drop_duplicates(["ts_code", "trade_date"], keep="last")
    return combined.sort_values(["ts_code", "trade_date"]), {
        "requested": True, "rows": int(len(fetched)), "max_date": int(fetched["trade_date"].max())
    }


def _candidate_snapshot(prices: pd.DataFrame, universe: pd.DataFrame, event_date: int) -> list[dict]:
    active = universe[(universe["pool_type"] == "core")
                      & (universe["effective_start"] <= event_date)
                      & (universe["effective_end"] >= event_date)]
    rows = []
    for _, member in active.iterrows():
        history = prices[(prices["ts_code"] == member["ts_code"])
                         & (prices["trade_date"] <= event_date)].sort_values("trade_date")
        if history.empty:
            continue
        latest = history.iloc[-1]
        ret5 = float(history["adj_close"].iloc[-1] / history["adj_close"].iloc[-6] - 1.0) if len(history) >= 6 else np.nan
        amount20 = float(history["amount"].tail(20).mean()) if "amount" in history else np.nan
        rows.append({
            "ts_code": str(member["ts_code"]), "name": str(member.get("name", "")),
            "ret_5d": ret5, "pct_chg_1d": float(latest.get("pct_chg", np.nan)) / 100.0,
            "amount_20d": amount20,
        })
    return sorted(rows, key=lambda row: row["ret_5d"] if np.isfinite(row["ret_5d"]) else 999)


def _render_report(alert: dict) -> str:
    lines = [
        "# 光刻胶恐慌监控提示", "",
        f"生成时间：{alert['generated_at']}",
        f"数据日期：{alert.get('data_date')}",
        f"状态：**{alert['alert_status']}**", "",
    ]
    for warning in alert.get("warnings", []):
        lines.append(f"- 警告：{warning}")
    lines.extend(["", "## 恐慌状态", ""])
    metrics = alert.get("metrics", {})
    for key in ("severity", "primary_5d_triggered", "basket_ret_5d", "historical_percentile",
                "down_breadth_5d", "amount_ratio_20d", "market_regime", "relative_vs_semiconductor_5d"):
        lines.append(f"- {key}: `{metrics.get(key)}`")
    lines.extend(["", "## 候选观察", ""])
    candidates = pd.DataFrame(alert.get("candidates", []))
    lines.append(candidates.to_markdown(index=False, floatfmt=".4f") if not candidates.empty else "_无候选数据_")
    lines.extend(["", "## 历史参考", "", alert.get("historical_reference", ""), "",
                  "本工具只输出恐慌识别与反转观察，不生成自动买入指令。"])
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    requested = int(args.as_of)
    research = load_yaml(Path(args.research_config))
    universe_cfg = _load_yaml(Path(args.universe_config))
    monitor = _load_yaml(Path(args.monitor_config))
    out_dir = Path(args.out_dir or monitor["outputs"]["directory"])
    out_dir.mkdir(parents=True, exist_ok=True)
    _, universe = load_validation_inputs(Path(args.frozen_dir))
    core_codes = universe[universe["pool_type"] == "core"]["ts_code"].astype(str).tolist()
    history_start = int(research["research"]["date_range"]["start"])
    prices = load_prices(history_start, requested, core_codes)
    local_price_max = int(prices["trade_date"].max())
    regime_cfg = research["threshold_validation"]["market_regime"]
    index_codes = [regime_cfg["primary_index"], "931865.CSI"]
    index_prices = load_index_prices(history_start, requested, index_codes)
    refresh = {"prices": {"requested": False}, "indices": {"requested": False}}
    if args.refresh_tushare:
        prices, refresh["prices"] = _refresh_prices(prices, core_codes, local_price_max + 1, requested)
        index_start = int(index_prices["trade_date"].max()) + 1 if not index_prices.empty else local_price_max + 1
        index_prices, refresh["indices"] = _refresh_indices(index_prices, index_codes, index_start, requested)
    data_date = int(prices["trade_date"].max())
    max_effective_end = int(universe[universe["pool_type"] == "core"]["effective_end"].max())
    warnings = []
    blocked = []
    if data_is_stale(data_date, requested, int(monitor["max_data_staleness_calendar_days"])):
        blocked.append("DATA_STALE")
        warnings.append(f"核心行情最新日期为{data_date}，请求日期为{requested}")
    universe_carried = requested > max_effective_end
    if universe_carried and not args.allow_universe_carry_forward:
        blocked.append("UNIVERSE_REVIEW_REQUIRED")
        warnings.append(f"核心股票池有效期截止{max_effective_end}，未获准向后沿用")
    elif universe_carried:
        warnings.append(f"临时沿用截止{max_effective_end}的核心池，成员资格待人工复核")
        universe.loc[universe["pool_type"] == "core", "effective_end"] = requested
    alert: dict[str, Any] = {
        "schema": monitor["schema"], "generated_at": datetime.now().isoformat(timespec="seconds"),
        "requested_date": requested, "data_date": data_date, "refresh": refresh,
        "warnings": warnings, "blocked_reasons": blocked, "alert_status": "BLOCKED" if blocked else "PENDING",
        "metrics": {}, "candidates": [],
        "historical_reference": monitor["historical_reference"]["warning"],
    }
    if not blocked:
        calendar = build_trading_calendar(prices)
        basket_rules = universe_cfg["basket_rules"]
        limit_status = load_limit_status(history_start, data_date, core_codes)
        suspend_status = load_suspend_status(history_start, data_date, core_codes)
        baskets = build_basket_daily(
            prices, universe, basket_rules, calendar, history_start, data_date,
            limit_status=limit_status, suspend_status=suspend_status,
            stock_status=load_stock_status(), eligibility=universe_cfg.get("eligibility", {}),
        )
        core = baskets.get("core_basket", pd.DataFrame())
        gate_cfg = research["threshold_validation"]["gates"][monitor["gate_id"]]
        gated = build_threshold_gate(core, monitor["gate_id"], gate_cfg)
        row = gated[gated["trade_date"] == data_date].iloc[-1]
        historical = gated.loc[gated["trade_date"] < data_date, "validation_return"].dropna().tail(250)
        percentile = float((historical <= float(row["validation_return"])).mean()) if len(historical) else np.nan
        regime = compute_market_regime(index_prices, regime_cfg)
        regime_row = regime[regime["trade_date"] == data_date]
        market_regime = str(regime_row.iloc[-1]["market_regime"]) if not regime_row.empty else "unknown"
        semi = index_prices[index_prices["ts_code"] == "931865.CSI"].sort_values("trade_date")
        semi5 = float(semi["close"].iloc[-1] / semi["close"].iloc[-6] - 1.0) if len(semi) >= 6 else np.nan
        basket5 = float(row["validation_return"])
        triggered = bool(row["validation_gate_triggered"])
        severity = classify_severity(triggered, basket5, percentile,
                                     float(row["validation_breadth"]), monitor["severity"])
        if triggered and market_regime in monitor["reversal_eligible_regimes"]:
            status = "REVERSAL_WATCH"
        elif triggered:
            status = "PANIC_RISK_ONLY"
        elif severity == "WATCH":
            status = "WEAKNESS_WATCH"
        else:
            status = "NORMAL"
        alert["alert_status"] = status
        alert["metrics"] = {
            "severity": severity, "primary_5d_triggered": triggered,
            "basket_ret_5d": basket5, "historical_percentile": percentile,
            "down_breadth_5d": float(row["validation_breadth"]),
            "amount_ratio_20d": float(row.get("median_amount_ratio_20d", np.nan)),
            "market_regime": market_regime,
            "relative_vs_semiconductor_5d": basket5 - semi5 if np.isfinite(semi5) else None,
        }
        alert["candidates"] = _candidate_snapshot(prices, universe, data_date)
        reference = monitor["historical_reference"]
        alert["historical_reference"] = (
            f"{reference['label']}：历史命中率约{reference['hit_rate_range'][0]:.1%}-"
            f"{reference['hit_rate_range'][1]:.1%}，每条规则样本{reference['sample_per_rule']}笔。"
            f"{reference['warning']}"
        )
    suffix = str(data_date)
    json_path = out_dir / f"photoresist_panic_alert_{suffix}.json"
    md_path = out_dir / f"photoresist_panic_alert_{suffix}.md"
    latest_json = out_dir / "photoresist_panic_alert_latest.json"
    latest_md = out_dir / "photoresist_panic_alert_latest.md"
    payload = json.dumps(alert, ensure_ascii=False, indent=2, default=str)
    json_path.write_text(payload, encoding="utf-8")
    latest_json.write_text(payload, encoding="utf-8")
    report = _render_report(alert)
    md_path.write_text(report, encoding="utf-8")
    latest_md.write_text(report, encoding="utf-8")
    print(payload)
    return 2 if blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())

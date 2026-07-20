"""Historical day-by-day replay of the online first-trigger pipeline.

Replays 2019-2025 (configurable) through the SAME per-day core as live runs
(runner.evaluate_day: frozen gate + member scopes + active-member stress +
severity) and the SAME state machine, under strict PIT discipline:
  - each replay day only reads rows <= that day (shift(1) quantile, trailing
    severity percentile);
  - online first-trigger days come from the state machine, never from
    post-hoc cluster end dates;
  - re-running must produce identical outputs (determinism hash).

Outputs -> outputs/live/photoresist_panic_alert/replay/
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Replay photoresist panic state machine")
    parser.add_argument("--start", type=int, default=20190101)
    parser.add_argument("--end", type=int, default=20251231)
    parser.add_argument("--live-config",
                        default=str(ROOT / "configs" / "photoresist_panic_live.yaml"))
    parser.add_argument("--out-dir",
                        default=str(ROOT / "outputs" / "live" /
                                    "photoresist_panic_alert" / "replay"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    from live.photoresist_panic import signal_engine
    from live.photoresist_panic.runner import (
        LiveRunContext, _regime_by_date, evaluate_day,
    )
    from live.photoresist_panic.state_machine import PanicState, step

    context = LiveRunContext(args.live_config, out_dir=out_dir)
    live = context.live_config
    core_codes = sorted(
        context.universe.loc[
            context.universe["pool_type"] == "core", "ts_code"
        ].unique().tolist()
    )
    history_start = int(live["data"]["history_start"])
    index_codes = list(live["data"]["benchmark_indices"])

    data = signal_engine.load_market_data(
        history_start, args.end, core_codes, index_codes
    )
    basket = signal_engine.build_core_basket(
        data, context.universe, context.universe_config, history_start, args.end
    )
    gated = signal_engine.apply_frozen_gate(basket, live["frozen_gate"]["gate_id"])
    from build_photoresist_panic_events import build_trading_calendar
    calendar = build_trading_calendar(data["prices"])
    regime_by_date = _regime_by_date(
        data["index_prices"], live["reversal"]["market_regime"]
    )

    machine = live["state_machine"]
    state = PanicState()
    rows = []
    replay_days = [
        int(d) for d in gated["trade_date"] if args.start <= int(d) <= args.end
    ]
    for day in replay_days:
        evaluation = evaluate_day(context, data, gated, calendar, day,
                                  regime_by_date)
        state, transition = step(
            state, day,
            triggered=evaluation["snapshot"]["primary_5d_triggered"],
            severity=evaluation["severity"]["level"],
            active_max_trading_days=int(machine["active_max_trading_days"]),
            cooldown_clear_days=int(machine["cooldown_clear_days"]),
        )
        rows.append({
            "trade_date": day,
            "primary_5d_triggered": evaluation["snapshot"]["primary_5d_triggered"],
            "basket_ret_5d": evaluation["snapshot"]["basket_ret_5d"],
            "severity": evaluation["severity"]["level"],
            "market_regime": evaluation["market_regime"],
            "active_components": evaluation["eligibility"]["active_components"],
            "signal_components": evaluation["eligibility"]["signal_components"],
            "state_before": transition["state_before"],
            "state_after": transition["state_after"],
            "transition": transition["kind"],
            "emit_alert": transition["emit_alert"],
            "is_new_event": transition["is_new_event"],
            "signal_id": transition["signal_id"],
            "live_signal_date": transition["live_signal_date"],
        })

    frame = pd.DataFrame(rows)
    frame.to_csv(out_dir / "replay_daily_states.csv", index=False,
                 encoding="utf-8-sig")
    events = frame[frame["is_new_event"]]
    events.to_csv(out_dir / "replay_first_triggers.csv", index=False,
                  encoding="utf-8-sig")

    content_hash = hashlib.sha256(
        frame.to_csv(index=False).encode("utf-8")
    ).hexdigest()[:16]
    summary = {
        "start": args.start, "end": args.end,
        "n_days": int(len(frame)),
        "n_triggered_days": int(frame["primary_5d_triggered"].sum()),
        "n_online_first_triggers": int(len(events)),
        "first_trigger_dates": events["trade_date"].tolist(),
        "severity_distribution": frame.loc[
            frame["primary_5d_triggered"], "severity"
        ].value_counts().to_dict(),
        "determinism_hash": content_hash,
        "core": "runner.evaluate_day (same as live)",
        "note": "online first-trigger only; no post-hoc cluster-end dates",
    }
    (out_dir / "replay_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

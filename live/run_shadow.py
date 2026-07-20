#!/usr/bin/env python
"""
Shadow Trading Runner — end-to-end shadow trading loop.

Runs the full live pipeline without real orders:
1. Signal generation
2. Order building
3. Risk gate checks
4. Paper execution

Usage:
    python -m live.run_shadow --start 20260105 --end 20260331
"""

import argparse
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("live.run_shadow")


def run_single_date(date_str: str, top_n: int = 50,
                    capital: float = 100_000_000.0) -> Dict[str, Any]:
    """
    Run the full shadow trading pipeline for one date.

    Returns audit record dict.
    """
    result = {
        "date": date_str,
        "timestamp": datetime.now().isoformat(),
        "stages": {},
    }

    # 1. Signal generation
    logger.info(f"[{date_str}] Stage 1/4: Generating signals...")
    try:
        from live.signal_service import SignalService
        svc = SignalService(date_str=date_str, top_n=top_n)
        signals = svc.generate_signals()
        if signals.empty:
            result["stages"]["signals"] = {"status": "FAIL", "error": "No signals generated"}
            return result
        svc.save_signals(signals)
        result["stages"]["signals"] = {"status": "OK", "n_stocks": len(signals)}
    except Exception as e:
        result["stages"]["signals"] = {"status": "FAIL", "error": str(e)}
        return result

    # 2. Order building
    logger.info(f"[{date_str}] Stage 2/4: Building orders...")
    try:
        from live.order_builder import OrderBuilder
        builder = OrderBuilder(date_str=date_str, capital=capital)
        orders = builder.build_orders()
        builder.save_orders(orders)
        n_ready = len(orders[orders["status"] == "READY"]) if not orders.empty else 0
        result["stages"]["orders"] = {
            "status": "OK",
            "n_total": len(orders),
            "n_ready": n_ready,
        }
    except Exception as e:
        result["stages"]["orders"] = {"status": "FAIL", "error": str(e)}
        return result

    # 3. Risk gate
    logger.info(f"[{date_str}] Stage 3/4: Risk checks...")
    try:
        from live.risk_gate import RiskGate
        gate = RiskGate(date_str=date_str)
        risk_result = gate.check()
        gate.save_result(risk_result)
        result["stages"]["risk"] = {
            "status": "OK",
            "verdict": risk_result["verdict"],
            "n_pass": risk_result["n_pass"],
            "n_warn": risk_result["n_warn"],
            "n_block": risk_result["n_block"],
        }

        if risk_result["verdict"] == "BLOCK":
            logger.warning(f"[{date_str}] Risk gate BLOCKED — skipping execution")
            result["stages"]["execution"] = {
                "status": "SKIPPED",
                "reason": f"Risk gate: {risk_result['verdict']}",
            }
            return result
    except Exception as e:
        result["stages"]["risk"] = {"status": "FAIL", "error": str(e)}
        return result

    # 4. Paper execution — with upfront price precheck
    logger.info(f"[{date_str}] Stage 4/4: Paper execution...")
    n_ready = result["stages"]["orders"].get("n_ready", 0)
    try:
        from live.paper_broker import PaperBroker
        from data.calendar import get_calendar as _get_shadow_cal
        from data.panel_loader import get_loader as _get_shadow_loader

        # ── Execution price precheck ──
        # Before running paper fills, verify that raw execution prices
        # exist for the execution date.  This catches DATA_INSUFFICIENT
        # early (before reaching empty-fills detection) and provides a
        # clearer failure reason.
        _shadow_cal = _get_shadow_cal()
        _shadow_cal.load(start_date=date_str, end_date=date_str)
        _shadow_date_int = int(date_str)
        _shadow_exec_date = _shadow_cal.next_trade_day(_shadow_date_int, 1)
        _shadow_exec_date_str = str(_shadow_exec_date)

        _shadow_precheck_fail = False
        _shadow_precheck_skip = False
        _shadow_precheck_reason = ""

        if _shadow_exec_date == _shadow_date_int:
            # next_trade_day returned the same date → no next trade day
            _shadow_precheck_skip = True
            _shadow_precheck_reason = (
                f"DATA_INSUFFICIENT: no next trade day after {date_str}"
            )
        elif n_ready > 0:
            # Check if execution prices exist for the execution date
            _shadow_loader = _get_shadow_loader()
            _shadow_px = _shadow_loader.query_prices(
                start_date=_shadow_exec_date_str,
                end_date=_shadow_exec_date_str,
                fields=["ts_code", "trade_date", "open"],
                price_type="raw",
            )
            if _shadow_px.empty:
                _shadow_precheck_fail = True
                _shadow_precheck_reason = (
                    f"DATA_INSUFFICIENT: missing execution prices "
                    f"for {_shadow_exec_date_str} "
                    f"(exec date for signal {date_str}) — "
                    f"{n_ready} READY orders cannot be filled"
                )

        if _shadow_precheck_skip:
            logger.warning(
                f"[{date_str}] Execution SKIPPED: {_shadow_precheck_reason}"
            )
            result["stages"]["execution"] = {
                "status": "SKIPPED",
                "reason": _shadow_precheck_reason,
            }
            result["overall"] = "SKIPPED"
            return result

        if _shadow_precheck_fail:
            logger.error(
                f"[{date_str}] Execution FAIL: {_shadow_precheck_reason}"
            )
            result["stages"]["execution"] = {
                "status": "FAIL",
                "reason": _shadow_precheck_reason,
                "n_fills": 0,
                "n_clean": 0,
                "n_high_slippage": 0,
                "n_executed": 0,
                "n_failed": n_ready,
            }
            result["overall"] = "FAIL"
            return result
        # ── End price precheck ──

        broker = PaperBroker(date_str=date_str)
        fills = broker.execute()
        broker.save_fills(fills)

        if not fills.empty:
            n_clean = int((fills["status"] == "FILLED").sum())
            n_high_slippage = int((fills["status"] == "HIGH_SLIPPAGE").sum())
            n_executed = n_clean + n_high_slippage
            n_failed_fills = int((fills["status"] == "NO_PRICE").sum())
        else:
            n_clean = 0
            n_high_slippage = 0
            n_executed = 0
            n_failed_fills = 0

        # Execution failure detection: if there were READY orders but
        # nothing actually executed, that's a FAIL (not OK).
        if n_ready > 0 and fills.empty:
            exec_status = "FAIL"
            exec_reason = (
                f"{n_ready} READY orders but fills empty — "
                f"execution prices missing for {date_str}"
            )
        elif n_ready > 0 and n_executed == 0:
            exec_status = "FAIL"
            exec_reason = (
                f"{n_ready} READY orders but 0 executed "
                f"(all NO_PRICE or missing prices)"
            )
        else:
            exec_status = "OK"
            exec_reason = ""

        result["stages"]["execution"] = {
            "status": exec_status,
            "n_fills": len(fills),
            "n_clean": n_clean,
            "n_high_slippage": n_high_slippage,
            "n_executed": n_executed,
            "n_failed": n_failed_fills,
        }
        if exec_reason:
            result["stages"]["execution"]["reason"] = exec_reason
    except Exception as e:
        result["stages"]["execution"] = {"status": "FAIL", "error": str(e)}
        return result

    # ---- Overall verdict: aggregate stage statuses ----
    stage_statuses = [s.get("status") for s in result["stages"].values()]
    if "FAIL" in stage_statuses:
        result["overall"] = "FAIL"
    elif "SKIPPED" in stage_statuses:
        result["overall"] = "SKIPPED"
    else:
        result["overall"] = "OK"

    # If risk gate was BLOCKED, execution is SKIPPED (not FAIL)
    if result["stages"].get("risk", {}).get("verdict") == "BLOCK":
        if result["stages"]["execution"].get("status") == "SKIPPED":
            pass  # already correct

    logger.info(
        f"[{date_str}] Verdict: {result['overall']} — "
        f"exec: {result['stages'].get('execution', {}).get('n_executed', 0)} executed "
        f"({result['stages'].get('execution', {}).get('n_clean', 0)} clean, "
        f"{result['stages'].get('execution', {}).get('n_high_slippage', 0)} high_slip), "
        f"{result['stages'].get('execution', {}).get('n_failed', 0)} failed"
    )
    return result


def run_shadow_loop(start_date: str, end_date: str,
                    top_n: int = 50,
                    capital: float = 100_000_000.0) -> List[Dict[str, Any]]:
    """
    Run shadow trading loop across a date range.

    Generates weekly signals and processes each date through the pipeline.
    """
    from data.calendar import get_calendar

    cal = get_calendar()
    cal.load(start_date=start_date, end_date=end_date)
    all_signal_dates = cal.weekly_rebalance_dates(start_date, end_date)

    # Filter: remove dates that don't have a next trade day for execution
    signal_dates = []
    skipped_dates = []
    for d in all_signal_dates:
        d_int = int(d)
        next_td = cal.next_trade_day(d_int, 1)
        if next_td == d_int:
            # next_trade_day returns the same date when out of range
            skipped_dates.append(d)
        else:
            signal_dates.append(d)

    if skipped_dates:
        logger.warning(
            f"Skipping {len(skipped_dates)} dates without next trade day: "
            f"{skipped_dates}"
        )

    logger.info(
        f"Shadow trading: {start_date} → {end_date}, "
        f"{len(signal_dates)} weekly dates "
        f"({len(skipped_dates)} skipped — no next trade day)"
    )

    audit_log = []

    # Add skipped dates to audit log (not failures, just unavailable)
    for d in skipped_dates:
        audit_log.append({
            "date": d,
            "timestamp": datetime.now().isoformat(),
            "overall": "SKIPPED",
            "reason": "DATA_INSUFFICIENT: no next trade day available for execution",
            "stages": {"execution": {"status": "SKIPPED",
                                     "reason": "no next trade day"}},
        })

    n_ok = 0
    n_skipped = 0
    n_fail = 0

    for i, date_str in enumerate(signal_dates):
        logger.info(f"=" * 50)
        logger.info(f"Date {i+1}/{len(signal_dates)}: {date_str}")
        logger.info(f"=" * 50)

        result = run_single_date(date_str, top_n=top_n, capital=capital)
        audit_log.append(result)

        if result.get("overall") == "OK":
            n_ok += 1
        elif result.get("overall") == "SKIPPED":
            n_skipped += 1
        else:
            n_fail += 1

        # Log progress
        stages_ok = sum(
            1 for s in result.get("stages", {}).values()
            if s.get("status") in ("OK", "SKIPPED")
        )
        logger.info(
            f"[{date_str}] Pipeline: {stages_ok}/4 stages OK. "
            f"Cumulative: {n_ok} OK, {n_skipped} SKIPPED, {n_fail} FAIL"
        )

    logger.info(
        f"\nShadow Trading Complete: {n_ok} OK, {n_skipped} SKIPPED, {n_fail} FAIL"
    )

    return audit_log


def main():
    parser = argparse.ArgumentParser(
        description="Shadow trading loop (paper only, no real orders)"
    )
    parser.add_argument("--start", type=str, required=True,
                       help="Start date YYYYMMDD")
    parser.add_argument("--end", type=str, required=True,
                       help="End date YYYYMMDD")
    parser.add_argument("--top-n", type=int, default=50,
                       help="Number of stocks in portfolio")
    parser.add_argument("--capital", type=float, default=100_000_000.0,
                       help="Portfolio capital in CNY")

    args = parser.parse_args()

    start_ts = time.monotonic()
    audit_log = run_shadow_loop(
        start_date=args.start,
        end_date=args.end,
        top_n=args.top_n,
        capital=args.capital,
    )
    elapsed = time.monotonic() - start_ts

    # Save audit log
    out_dir = Path("outputs/live")
    out_dir.mkdir(parents=True, exist_ok=True)
    audit_path = out_dir / f"audit_{args.start}_{args.end}.json"
    with open(audit_path, "w", encoding="utf-8") as f:
        json.dump(audit_log, f, indent=2, ensure_ascii=False, default=str)

    n_ok = sum(1 for r in audit_log if r.get("overall") == "OK")
    n_skipped = sum(1 for r in audit_log if r.get("overall") == "SKIPPED")
    n_fail = sum(1 for r in audit_log
                 if r.get("overall") not in ("OK", "SKIPPED"))

    print(f"\n{'='*60}")
    print(f"Shadow Trading Report: {args.start} → {args.end}")
    print(f"{'='*60}")
    print(f"  Dates processed: {len(audit_log)}")
    print(f"  OK: {n_ok}, SKIPPED: {n_skipped}, FAIL: {n_fail}")
    if n_skipped > 0:
        skipped_dates_list = [r["date"] for r in audit_log
                             if r.get("overall") == "SKIPPED"]
        print(f"  Skipped dates: {', '.join(skipped_dates_list)}")
    print(f"  Elapsed: {elapsed:.1f}s")
    print(f"  Audit log: {audit_path}")

    return 1 if n_fail > 0 else 0


if __name__ == "__main__":
    sys.exit(main())

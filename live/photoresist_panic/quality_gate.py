"""Data quality gate v2 — hard blocking rules before any signal interpretation.

Status rules (frozen, plan §5.3 + gap-fix plan §3.3/§3.5/§7.1):
  NORMAL   : all active core components have market data at the evaluation day
  DEGRADED : one active component missing/suspended (>= min_components_degraded)
  BLOCKED  : <3 components, stock data behind the latest closed trading day,
             per-security trading-day continuity violated (unexplained gap),
             any required index missing an open date in the check window,
             adjusted OHLC columns missing/bad, duplicate keys, or
             insufficient warmup

Expected membership comes from active_members(universe, evaluation_day) —
never from the union of all historical core codes.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

NORMAL = "NORMAL"
DEGRADED = "DEGRADED"
BLOCKED = "BLOCKED"

ADJ_OHLC_COLUMNS = ("adj_open", "adj_high", "adj_low", "adj_close")


def _duplicate_key_audit(frame: pd.DataFrame) -> list[dict]:
    if frame.empty or not {"ts_code", "trade_date"}.issubset(frame.columns):
        return []
    duplicate_rows = frame[frame.duplicated(["ts_code", "trade_date"], keep=False)]
    if duplicate_rows.empty:
        return []
    counts = duplicate_rows.groupby(["ts_code", "trade_date"]).size()
    return [
        {"ts_code": str(code), "trade_date": int(day), "row_count": int(count)}
        for (code, day), count in counts.items()
    ]


def _suspended_keys(suspend_records: pd.DataFrame | None) -> set[tuple[str, int]]:
    if suspend_records is None or getattr(suspend_records, "empty", True):
        return set()
    return set(zip(suspend_records["ts_code"].astype(str),
                   suspend_records["trade_date"].astype(int)))


def run_quality_gate(
    prices: pd.DataFrame,
    index_prices: pd.DataFrame,
    active_codes: list[str],
    as_of: int,
    config: dict,
    open_dates: list[int] | None = None,
    suspend_records: pd.DataFrame | None = None,
    limit_status: pd.DataFrame | None = None,
    calendar_latest_trading_day: int | None = None,
) -> dict:
    """Evaluate all quality checks; returns the data_quality_report payload.

    open_dates: expected exchange open dates for the continuity check window
    (last 250 trading days through the current day). Without it, continuity
    checks fail closed (BLOCKED) rather than silently passing.
    """
    checks: list[dict] = []
    warnings: list[str] = []
    blockers: list[str] = []

    def check(name: str, passed: bool, detail: str, blocking: bool = True) -> None:
        checks.append({"check": name, "passed": bool(passed), "detail": detail})
        if not passed:
            (blockers if blocking else warnings).append(f"{name}: {detail}")

    active_codes = sorted(str(c) for c in active_codes)
    stock_max = int(prices["trade_date"].max()) if not prices.empty else None
    index_max = (
        int(index_prices["trade_date"].max()) if not index_prices.empty else None
    )
    suspended = _suspended_keys(suspend_records)
    duplicate_stock_keys = _duplicate_key_audit(prices)
    duplicate_index_keys = _duplicate_key_audit(index_prices)

    # ── 1. Stock data must reach the latest closed trading day ────────
    reference_day = calendar_latest_trading_day or (
        open_dates[-1] if open_dates else index_max
    )
    if reference_day is not None and stock_max is not None:
        check("stock_data_current", stock_max >= reference_day,
              f"prices_adj max={stock_max}, latest trading day={reference_day}")
    else:
        check("stock_data_current", False,
              f"prices_adj max={stock_max}, reference day={reference_day}")

    eval_day = min(stock_max or 0, as_of)

    # ── 2. Continuity window ──────────────────────────────────────────
    window = [d for d in (open_dates or []) if d <= eval_day]
    check("continuity_window_available", bool(window),
          f"{len(window)} expected open dates in check window"
          if window else "no expected open dates supplied — failing closed")

    # ── 3. Per-index trading-day continuity (not just max_date) ───────
    required_indices = list(config.get("required_indices", []))
    index_continuity: dict[str, dict] = {}
    if window and required_indices:
        for code in required_indices:
            have = set(
                int(d) for d in index_prices.loc[
                    index_prices["ts_code"] == code, "trade_date"
                ]
            ) if not index_prices.empty else set()
            missing = [d for d in window if d not in have]
            index_continuity[code] = {
                "n_expected": len(window), "n_missing": len(missing),
                "missing_dates": missing[:20],
            }
            check(f"index_continuity[{code}]", not missing,
                  f"{len(missing)} open dates missing "
                  f"(e.g. {missing[:5]})" if missing
                  else f"all {len(window)} open dates present")

    # ── 4. Per-stock continuity: legal suspension vs unexplained gap ──
    stock_continuity: dict[str, dict] = {}
    if window:
        for code in active_codes:
            have = set(
                int(d) for d in prices.loc[
                    prices["ts_code"] == code, "trade_date"
                ]
            ) if not prices.empty else set()
            missing = [d for d in window if d not in have]
            legal = [d for d in missing if (code, d) in suspended]
            unexplained = [d for d in missing if (code, d) not in suspended]
            stock_continuity[code] = {
                "n_missing": len(missing),
                "legal_suspension_dates": legal[:20],
                "unexplained_dates": unexplained[:20],
            }
            if legal:
                warnings.append(
                    f"stock_continuity[{code}]: {len(legal)} days missing under "
                    f"suspension records (legal)"
                )
            check(f"stock_continuity[{code}]", not unexplained,
                  f"{len(unexplained)} unexplained missing open dates "
                  f"(e.g. {unexplained[:5]})" if unexplained
                  else f"no unexplained gaps ({len(legal)} legal suspensions)")

    # ── 5. Active component presence at the evaluation day ────────────
    day_rows = prices[prices["trade_date"] == eval_day] if stock_max else pd.DataFrame()
    present = sorted(set(day_rows["ts_code"].astype(str)) & set(active_codes))
    missing_today = sorted(set(active_codes) - set(present))
    missing_detail = [
        {"ts_code": code,
         "reason": "suspended" if (code, eval_day) in suspended else "no_market_data"}
        for code in missing_today
    ]
    n_present = len(present)
    check("core_components_present",
          n_present >= int(config.get("min_components_degraded", 3)),
          f"{n_present}/{len(active_codes)} present at {eval_day}, "
          f"missing={missing_detail}")
    if missing_today and n_present >= int(config.get("min_components_degraded", 3)):
        warnings.append(
            f"core_components_degraded: {n_present}/{len(active_codes)} at "
            f"{eval_day}, missing={missing_detail}"
        )

    # ── 6. Duplicate keys (stocks and indices) ────────────────────────
    if not prices.empty:
        dup = int(prices.duplicated(["ts_code", "trade_date"]).sum())
        check("no_duplicate_stock_keys", dup == 0,
              f"{dup} duplicate (ts_code, trade_date) rows in prices; "
              f"keys={duplicate_stock_keys[:20]}")
    if not index_prices.empty:
        dup_idx = int(index_prices.duplicated(["ts_code", "trade_date"]).sum())
        check("no_duplicate_index_keys", dup_idx == 0,
              f"{dup_idx} duplicate (ts_code, trade_date) rows in index_daily; "
              f"keys={duplicate_index_keys[:20]}")

    # ── 7. Adjusted OHLC: ALL FOUR columns must exist and be sane ─────
    if config.get("require_adj_prices_positive", True) and not prices.empty:
        window_lo = window[0] if window else eval_day
        recent = prices[prices["trade_date"] >= window_lo]
        missing_cols = [c for c in ADJ_OHLC_COLUMNS if c not in recent.columns]
        if missing_cols:
            check("adj_ohlc_columns_complete", False,
                  f"missing adjusted OHLC columns: {missing_cols} — "
                  "adj_close alone is NOT a pass")
        else:
            check("adj_ohlc_columns_complete", True,
                  "all four adjusted OHLC columns present")
            bad = int(((recent[list(ADJ_OHLC_COLUMNS)] <= 0)
                       | recent[list(ADJ_OHLC_COLUMNS)].isna()).any(axis=1).sum())
            check("adj_prices_positive", bad == 0,
                  f"{bad} rows with null/non-positive adjusted OHLC in window")

    # ── 8. Amount: config semantics are authoritative ─────────────────
    amount_required = bool(config.get("require_amount_present", True))
    if not prices.empty:
        window_lo = window[0] if window else eval_day
        recent = prices[prices["trade_date"] >= window_lo]
        n_missing_amount = (
            int(recent["amount"].isna().sum()) if "amount" in recent.columns
            else len(recent)
        )
        check("amount_present", n_missing_amount == 0,
              f"{n_missing_amount} rows missing amount in window"
              + ("" if amount_required
                 else " (require_amount_present=false: warning only)"),
              blocking=amount_required)

    # ── 9. Limit / suspend availability (warning only) ────────────────
    limit_available = limit_status is not None and not getattr(
        limit_status, "empty", True
    )
    check("limit_status_available", limit_available,
          "limit_status parquet rows found" if limit_available
          else "limit_status unavailable — pct_chg proxy will be used",
          blocking=False)

    # ── 10. 250-trading-day warmup ─────────────────────────────────────
    warmup_days = int(config.get("warmup_trading_days", 250))
    n_days = int(prices["trade_date"].nunique()) if not prices.empty else 0
    check("history_warmup", n_days >= warmup_days,
          f"{n_days} trading days loaded, need >= {warmup_days}")

    # ── Final status ──────────────────────────────────────────────────
    if blockers:
        status = BLOCKED
    elif n_present >= int(config.get("min_components_normal", 4)) or (
        n_present == len(active_codes)
    ):
        status = NORMAL
    else:
        status = DEGRADED

    return {
        "gate_version": str(config.get("gate_version", "dq_gate_v2")),
        "status": status,
        "as_of": int(as_of),
        "evaluation_day": int(eval_day) if stock_max else None,
        "stock_max_date": stock_max,
        "index_max_date": index_max,
        "calendar_latest_trading_day": calendar_latest_trading_day,
        "active_expected": active_codes,
        "market_data_present": present,
        "missing_components": missing_detail,
        "components_present": n_present,
        "components_expected": len(active_codes),
        "index_continuity": index_continuity,
        "stock_continuity": stock_continuity,
        "duplicate_key_audit": {
            "stock": duplicate_stock_keys,
            "index": duplicate_index_keys,
        },
        "checks": checks,
        "warnings": warnings,
        "blockers": blockers,
    }

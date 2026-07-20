"""Incremental Tushare data updater for the photoresist panic live pipeline.

v2 (gap-fix round):
  - Real calendar arithmetic only — never ``yyyymmdd + 1``.
  - Per-security incremental update: each stock/index computes its own
    cached dates, expected open dates, missing dates, and fetch ranges.
    A single lagging security can no longer hide behind the group max.
  - Continuity scan + data_gap_report: a missing stock row is only legal
    when a suspension record explains it; unexplained gaps are surfaced
    for the quality gate to BLOCK on.
  - Merge-write per partition (read-modify-write) so a 4-stock refresh can
    never clobber full-market history; touched partitions are deduped.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

import numpy as np
import pandas as pd

from .common import ROOT

logger = logging.getLogger("photoresist_panic_live")

PARQUET_ROOT = ROOT / "data" / "parquet"


# ═══════════════════════════════════════════════════════════════════════
# Real date arithmetic (plan §3.1) — the ONLY sanctioned date math
# ═══════════════════════════════════════════════════════════════════════
def yyyymmdd_to_date(day: int) -> date:
    day = int(day)
    return date(day // 10000, (day % 10000) // 100, day % 100)


def date_to_yyyymmdd(value: date) -> int:
    return value.year * 10000 + value.month * 100 + value.day


def yyyymmdd_add_days(day: int, n: int) -> int:
    """Calendar-correct day shift: month/year ends, leap Februaries, weekends
    and holiday spans (which plain integer +1 silently corrupts)."""
    return date_to_yyyymmdd(yyyymmdd_to_date(day) + timedelta(days=n))


def contiguous_ranges(days: list[int], max_gap_calendar_days: int = 7) -> list[tuple[int, int]]:
    """Group sorted YYYYMMDD days into fetch ranges.

    Days whose calendar distance is <= max_gap_calendar_days merge into one
    range (holiday spans inside a missing stretch do not split the fetch)."""
    if not days:
        return []
    days = sorted(int(d) for d in days)
    ranges = [[days[0], days[0]]]
    for day in days[1:]:
        previous_end = yyyymmdd_to_date(ranges[-1][1])
        if (yyyymmdd_to_date(day) - previous_end).days <= max_gap_calendar_days:
            ranges[-1][1] = day
        else:
            ranges.append([day, day])
    return [(lo, hi) for lo, hi in ranges]


# ═══════════════════════════════════════════════════════════════════════
# Trading calendar
# ═══════════════════════════════════════════════════════════════════════
def expected_open_dates(client, start: int, end: int) -> list[int]:
    """Exchange open dates in [start, end], from the cached trade calendar.

    The trade_cal parquet cache accumulates duplicated rows across fetches —
    dedup here or windows like [-250:] silently collapse to repeated days."""
    cal = client.get_trade_cal(start_date=str(start), end_date=str(end))
    if cal is None or cal.empty:
        return []
    open_days = cal[cal["is_open"] == 1]["cal_date"].astype(int)
    return sorted({int(d) for d in open_days if start <= d <= end})


def latest_closed_trading_day(client, as_of: int) -> int | None:
    """Most recent trading day <= as_of according to the exchange calendar."""
    start = date_to_yyyymmdd(yyyymmdd_to_date(as_of) - timedelta(days=45))
    days = expected_open_dates(client, start, as_of)
    return days[-1] if days else None


# ═══════════════════════════════════════════════════════════════════════
# Partition merge-write (read-modify-write; never shrinks history)
# ═══════════════════════════════════════════════════════════════════════
def _month_partition_bounds(year: int, month: int) -> tuple[int, int]:
    first = date(year, month, 1)
    last = (date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)) - timedelta(days=1)
    return date_to_yyyymmdd(first), date_to_yyyymmdd(last)


def _merge_write_partitions(
    cache,
    table_name: str,
    new_rows: pd.DataFrame,
    partition_cols: list[str],
    key_cols: list[str] = ["ts_code", "trade_date"],
) -> int:
    """Read-modify-write month/year partitions; existing rows are preserved.

    Also drops duplicate keys already present in the touched partitions, so a
    merge pass doubles as partition-level repair."""
    if new_rows.empty:
        return 0
    df = new_rows.copy()
    df["trade_date"] = pd.to_numeric(df["trade_date"], errors="coerce").astype("int32")
    df["year"] = df["trade_date"] // 10000
    if "month" in partition_cols:
        df["month"] = (df["trade_date"] % 10000) // 100
    total = 0
    for keys, chunk in df.groupby(partition_cols):
        if not isinstance(keys, tuple):
            keys = (keys,)
        partition = dict(zip(partition_cols, (int(k) for k in keys)))
        year = partition["year"]
        month = partition.get("month")
        if month is not None:
            lo, hi = _month_partition_bounds(year, month)
        else:
            lo, hi = year * 10000 + 101, year * 10000 + 1231
        existing = cache.read(
            table_name,
            filters=[("trade_date", ">=", np.int32(lo)),
                     ("trade_date", "<=", np.int32(hi))],
        )
        if not existing.empty:
            existing = existing.copy()
            existing["trade_date"] = pd.to_numeric(
                existing["trade_date"], errors="coerce"
            ).astype("int32")
            existing["year"] = existing["trade_date"] // 10000
            if month is not None:
                existing["month"] = (existing["trade_date"] % 10000) // 100
            shared = [c for c in existing.columns if c in chunk.columns]
            combined = pd.concat(
                [existing[shared], chunk[shared]], ignore_index=True
            )
        else:
            combined = chunk
        combined = combined.drop_duplicates(key_cols, keep="last")
        cache.write(
            combined, table_name,
            partition_cols=partition_cols, replace_partitions=True,
        )
        total += len(combined)
        logger.info(
            "data_updater: %s partition %s merged -> %d rows",
            table_name, partition, len(combined),
        )
    return total


# ═══════════════════════════════════════════════════════════════════════
# Per-security continuity planning (plan §3.2)
# ═══════════════════════════════════════════════════════════════════════
def _cached_dates(cache, table_name: str, code: str, start: int, end: int) -> set[int]:
    frame = cache.read(
        table_name, columns=["ts_code", "trade_date"],
        filters=[("ts_code", "==", code),
                 ("trade_date", ">=", np.int32(start)),
                 ("trade_date", "<=", np.int32(end))],
    )
    if frame is None or frame.empty:
        return set()
    return set(int(d) for d in frame["trade_date"])


def security_update_plan(cache, table_name: str, code: str,
                         open_dates: list[int]) -> dict:
    """Per-security incremental plan: cached max, missing dates, fetch ranges."""
    if not open_dates:
        return {"ts_code": code, "cached_max_date": None, "missing_dates": [],
                "fetch_ranges": [], "n_expected": 0}
    start, end = open_dates[0], open_dates[-1]
    cached = _cached_dates(cache, table_name, code, start, end)
    missing = [d for d in open_dates if d not in cached]
    return {
        "ts_code": code,
        "cached_max_date": max(cached) if cached else None,
        "n_expected": len(open_dates),
        "n_cached": len(cached),
        "missing_dates": missing,
        "fetch_ranges": contiguous_ranges(missing),
    }


# ═══════════════════════════════════════════════════════════════════════
# Fetch + write, per security
# ═══════════════════════════════════════════════════════════════════════
def update_stock_prices(client, codes: list[str], open_dates: list[int]) -> dict:
    """Per-stock gap-filling fetch of raw daily + adj_factor -> prices_adj.

    prices_adj stores 后复权 prices (raw * adj_factor); historical rows are
    invariant under new dividends, so gap-filling appends stay consistent."""
    from data.adjust import PriceAdjuster

    report: dict = {"per_security": {}, "rows": 0}
    raw_frames, plans = [], {}
    for code in codes:
        plan = security_update_plan(client.cache, "prices_adj", code, open_dates)
        plans[code] = plan
        report["per_security"][code] = {
            "cached_max_date": plan["cached_max_date"],
            "n_missing_before": len(plan["missing_dates"]),
            "fetch_ranges": plan["fetch_ranges"],
        }
        for lo, hi in plan["fetch_ranges"]:
            frame = client._call_api(
                client.pro.daily, ts_code=code,
                start_date=str(lo), end_date=str(hi),
            )
            if frame is not None and not frame.empty:
                raw_frames.append(frame)
    if not raw_frames:
        report["note"] = "no new rows fetched"
        return report
    raw = pd.concat(raw_frames, ignore_index=True)
    raw["trade_date"] = pd.to_numeric(raw["trade_date"], errors="coerce").astype("int32")
    raw = raw.drop_duplicates(["ts_code", "trade_date"])
    lo, hi = int(raw["trade_date"].min()), int(raw["trade_date"].max())
    factors = client.get_adj_factor(
        sorted(raw["ts_code"].unique()), str(lo), str(hi),
        use_cache=False, allow_partial=False, _write_cache=False,
    )
    if factors is None or factors.empty:
        raise RuntimeError(
            f"adj_factor fetch failed for {codes} {lo}-{hi}: "
            f"{getattr(factors, 'attrs', {})}"
        )
    factors["trade_date"] = pd.to_numeric(
        factors["trade_date"], errors="coerce"
    ).astype("int32")
    adjusted = PriceAdjuster(client=client).compute_adj_prices(
        raw, adj_factor_df=factors, strict=True,
    )
    written = _merge_write_partitions(
        client.cache, "prices_adj", adjusted, ["year", "month"]
    )
    _merge_write_partitions(client.cache, "prices_raw", raw, ["year", "month"])
    _merge_write_partitions(client.cache, "adj_factor", factors, ["year"])
    report.update({
        "rows": int(len(adjusted)),
        "min_date": int(adjusted["trade_date"].min()),
        "max_date": int(adjusted["trade_date"].max()),
        "partition_rows_written": int(written),
    })
    return report


def update_indices(client, index_codes: list[str], open_dates: list[int]) -> dict:
    """Per-index gap-filling fetch — every missing open date is requested,
    not just dates past max_date (this is what backfills 931865.CSI)."""
    report: dict = {"per_security": {}, "rows": 0}
    frames = []
    for code in index_codes:
        plan = security_update_plan(client.cache, "index_daily", code, open_dates)
        report["per_security"][code] = {
            "cached_max_date": plan["cached_max_date"],
            "n_missing_before": len(plan["missing_dates"]),
            "fetch_ranges": plan["fetch_ranges"],
        }
        for lo, hi in plan["fetch_ranges"]:
            frame = client._call_api(
                client.pro.index_daily, ts_code=code,
                start_date=str(lo), end_date=str(hi),
            )
            if frame is not None and not frame.empty:
                frame["trade_date"] = pd.to_numeric(
                    frame["trade_date"], errors="coerce"
                ).astype("int32")
                frames.append(frame)
    if not frames:
        report["note"] = "no new rows fetched"
        return report
    fetched = pd.concat(frames, ignore_index=True)
    written = _merge_write_partitions(
        client.cache, "index_daily", fetched, ["year"]
    )
    report.update({
        "rows": int(len(fetched)),
        "max_date": int(fetched["trade_date"].max()),
        "partition_rows_written": int(written),
    })
    return report


def update_limit_status(client, codes: list[str], open_dates: list[int]) -> dict:
    report: dict = {"per_security": {}, "rows": 0}
    frames = []
    for code in codes:
        plan = security_update_plan(client.cache, "limit_status", code, open_dates)
        report["per_security"][code] = {
            "n_missing_before": len(plan["missing_dates"]),
            "fetch_ranges": plan["fetch_ranges"],
        }
        for lo, hi in plan["fetch_ranges"]:
            fetched = client.get_stk_limit(
                ts_code=code, start_date=str(lo), end_date=str(hi),
                use_cache=False, write_cache=False,
            )
            if fetched is not None and not fetched.empty:
                fetched["trade_date"] = pd.to_numeric(
                    fetched["trade_date"], errors="coerce"
                ).astype("int32")
                frames.append(fetched)
    if not frames:
        return report
    merged = pd.concat(frames, ignore_index=True)
    written = _merge_write_partitions(
        client.cache, "limit_status", merged, ["year", "month"]
    )
    report.update({"rows": int(len(merged)),
                   "partition_rows_written": int(written)})
    return report


def fetch_suspend_records(client, codes: list[str], days: list[int]) -> pd.DataFrame:
    """Fetch suspend_d for specific days (bounded: only price-gap days).

    Fetched records are persisted to the suspend_status table so offline
    (--no-refresh) runs can still classify gaps as legal suspensions."""
    frames = []
    for day in days:
        try:
            frame = client._call_api(client.pro.suspend_d, suspend_date=str(day),
                                     ts_code=",".join(codes))
        except Exception as exc:
            logger.warning("data_updater: suspend fetch failed for %s: %s", day, exc)
            continue
        if frame is not None and not frame.empty:
            frames.append(frame)
    if not frames:
        return pd.DataFrame(columns=["ts_code", "trade_date", "suspend_type"])
    merged = pd.concat(frames, ignore_index=True)
    merged = merged.rename(columns={"suspend_date": "trade_date"})
    merged["trade_date"] = pd.to_numeric(merged["trade_date"], errors="coerce")
    merged = merged.dropna(subset=["trade_date"])
    keep = [c for c in ("ts_code", "trade_date", "suspend_type") if c in merged.columns]
    merged = merged[keep]
    try:
        _merge_write_partitions(client.cache, "suspend_status", merged, ["year"])
    except Exception as exc:
        logger.warning("data_updater: suspend cache write failed: %s", exc)
    return merged


def load_local_suspend_records(cache, codes: list[str],
                               start: int, end: int) -> pd.DataFrame:
    """Local suspend records for gap classification when Tushare is offline."""
    try:
        frame = cache.read(
            "suspend_status",
            filters=[("ts_code", "in", codes),
                     ("trade_date", ">=", np.int32(start)),
                     ("trade_date", "<=", np.int32(end))],
        )
    except Exception:
        return pd.DataFrame(columns=["ts_code", "trade_date"])
    if frame is None or frame.empty:
        return pd.DataFrame(columns=["ts_code", "trade_date"])
    frame = frame.copy()
    frame["trade_date"] = pd.to_numeric(frame["trade_date"], errors="coerce")
    return frame.dropna(subset=["trade_date"])


# ═══════════════════════════════════════════════════════════════════════
# Gap classification (plan §3.3 input for the quality gate)
# ═══════════════════════════════════════════════════════════════════════
def build_data_gap_report(client, core_codes: list[str], index_codes: list[str],
                          open_dates: list[int],
                          fetch_missing_suspends: bool = True) -> dict:
    """Post-update continuity scan over the check window.

    Stock gaps with a suspension record => legal_suspension; without =>
    unexplained_gap (quality gate blocks). Index gaps are always gaps."""
    report: dict = {
        "window_start": open_dates[0] if open_dates else None,
        "window_end": open_dates[-1] if open_dates else None,
        "n_open_dates": len(open_dates),
        "indices": {},
        "stocks": {},
        "unexplained_gaps": [],
    }
    for code in index_codes:
        plan = security_update_plan(client.cache, "index_daily", code, open_dates)
        report["indices"][code] = {
            "n_missing": len(plan["missing_dates"]),
            "missing_dates": plan["missing_dates"],
        }
        for day in plan["missing_dates"]:
            report["unexplained_gaps"].append(
                {"ts_code": code, "trade_date": day, "kind": "index_gap"}
            )

    stock_missing: dict[str, list[int]] = {}
    all_missing_days: set[int] = set()
    for code in core_codes:
        plan = security_update_plan(client.cache, "prices_adj", code, open_dates)
        stock_missing[code] = plan["missing_dates"]
        all_missing_days.update(plan["missing_dates"])

    suspends = pd.DataFrame(columns=["ts_code", "trade_date"])
    if all_missing_days and fetch_missing_suspends and client.available:
        suspends = fetch_suspend_records(
            client, core_codes, sorted(all_missing_days)
        )
    suspended_keys = (
        set(zip(suspends["ts_code"].astype(str),
                suspends["trade_date"].astype(int)))
        if not suspends.empty else set()
    )
    for code, missing in stock_missing.items():
        legal = [d for d in missing if (code, d) in suspended_keys]
        unexplained = [d for d in missing if (code, d) not in suspended_keys]
        report["stocks"][code] = {
            "n_missing": len(missing),
            "legal_suspension_dates": legal,
            "unexplained_dates": unexplained,
        }
        for day in unexplained:
            report["unexplained_gaps"].append(
                {"ts_code": code, "trade_date": day, "kind": "stock_gap"}
            )
    return report


def repair_duplicate_keys(cache, table_name: str, codes: list[str],
                          start: int, end: int,
                          partition_cols: list[str]) -> dict:
    """Detect duplicate (ts_code, trade_date) rows in a window and rewrite the
    affected partitions deduplicated (merge-write dedupes the whole partition)."""
    frame = cache.read(
        table_name,
        filters=[("ts_code", "in", codes),
                 ("trade_date", ">=", np.int32(start)),
                 ("trade_date", "<=", np.int32(end))],
    )
    if frame is None or frame.empty:
        return {"duplicates_found": 0}
    frame = frame.copy()
    frame["trade_date"] = pd.to_numeric(frame["trade_date"], errors="coerce").astype("int32")
    dup_mask = frame.duplicated(["ts_code", "trade_date"], keep=False)
    n_dups = int(dup_mask.sum())
    if n_dups == 0:
        return {"duplicates_found": 0}
    affected = frame[dup_mask].drop_duplicates(["ts_code", "trade_date"], keep="last")
    logger.warning("data_updater: %s has %d duplicated rows in window — repairing",
                   table_name, n_dups)
    _merge_write_partitions(cache, table_name, affected, partition_cols)
    return {"duplicates_found": n_dups,
            "keys_repaired": int(len(affected))}


# ═══════════════════════════════════════════════════════════════════════
# Orchestration
# ═══════════════════════════════════════════════════════════════════════
def run_incremental_update(core_codes: list[str], index_codes: list[str],
                           as_of: int, enabled: bool = True,
                           continuity_lookback_trading_days: int = 250) -> dict:
    """Bring every core stock and index up to the latest closed trading day,
    filling interior gaps per security, then produce the data gap report.

    Fetch failures are recorded (quality gate decides on blocking); integrity
    failures such as missing adj_factor coverage raise."""
    report: dict = {"enabled": enabled, "as_of": int(as_of), "errors": []}
    if not enabled:
        return report
    from data.tushare_client import get_client

    client = get_client()
    if not client.available:
        report["errors"].append("tushare_unavailable")
        return report

    target = latest_closed_trading_day(client, as_of)
    report["target_trading_day"] = target
    if target is None:
        report["errors"].append("trade_calendar_unavailable")
        return report

    # Check window: last N trading days up to target (covers the 250d warmup
    # window, the 5/10/20d computation windows, and the current day).
    window_start_hint = date_to_yyyymmdd(
        yyyymmdd_to_date(target)
        - timedelta(days=int(continuity_lookback_trading_days * 1.7) + 30)
    )
    open_dates = expected_open_dates(client, window_start_hint, target)
    open_dates = open_dates[-continuity_lookback_trading_days:]
    report["check_window"] = {
        "start": open_dates[0] if open_dates else None,
        "end": target, "n_trading_days": len(open_dates),
    }

    try:
        report["prices"] = update_stock_prices(client, core_codes, open_dates)
    except Exception as exc:
        logger.error("data_updater: stock price update failed: %s", exc)
        report["prices"] = {"rows": 0}
        report["errors"].append(f"stock_update_failed: {exc}")
    try:
        report["indices"] = update_indices(client, index_codes, open_dates)
        if open_dates:
            report["index_dedupe"] = repair_duplicate_keys(
                client.cache, "index_daily", index_codes,
                open_dates[0], open_dates[-1], ["year"],
            )
    except Exception as exc:
        logger.error("data_updater: index update failed: %s", exc)
        report["indices"] = {"rows": 0}
        report["errors"].append(f"index_update_failed: {exc}")
    try:
        report["limit_status"] = update_limit_status(client, core_codes, open_dates)
    except Exception as exc:
        logger.error("data_updater: limit status update failed: %s", exc)
        report["limit_status"] = {"rows": 0}
        report["errors"].append(f"limit_update_failed: {exc}")

    try:
        report["gap_report"] = build_data_gap_report(
            client, core_codes, index_codes, open_dates
        )
    except Exception as exc:
        logger.error("data_updater: gap report failed: %s", exc)
        report["errors"].append(f"gap_report_failed: {exc}")
        report["gap_report"] = None
    return report

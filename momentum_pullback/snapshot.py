"""Normalize a declared source package into one immutable snapshot.

The manifest is the commit marker. A directory without it is not a snapshot.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from momentum_pullback.contracts import ROOT, Contract, GateError, file_hash, fingerprint, write_json
from momentum_pullback.data_adapter import (
    KEYS, PRICE_COLUMNS, frame_hash, unique_keys, validate_calendar_binding, validate_join, validate_normalized_panel,
)
from momentum_pullback.runtime import create_run, implementation_hash, verify_run_inputs
from momentum_pullback.source_bindings import (
    INDEX_RELATIVE, SnapshotPolicy, SourcePackage, convert_to_cny, load_source_package, require_real_bools,
    require_supported_lifecycle, required_dates, select_asof,
)

SNAPSHOT_SCHEMA = "momentum_pullback.snapshot.v1"
COVERAGE_SCHEMA = "momentum_pullback.coverage_report.v1"
GATE_SCHEMA = "momentum_pullback.data_gate_report.v1"
REQUIRED_TABLES = (
    "calendar", "roster", "lifecycle", "prices_raw", "prices_adj", "amount", "circ_mv",
    "membership", "st_status", "industry", "halts",
)
PANEL_COLUMNS = [
    "ts_code", "trade_date", "signal_cutoff",
    "adj_open", "adj_high", "adj_low", "adj_close", "raw_open", "raw_high", "raw_low", "raw_close", "adj_factor",
    "price_status", "price_available_at", "price_revision_id",
    "membership_known", "is_member", "membership_available_at", "membership_effective_from", "membership_effective_to",
    "st_known", "is_st", "st_available_at", "st_effective_from", "st_effective_to",
    "amount_cny", "amount_available_at", "amount_unit", "amount_derivation",
    "circ_mv_cny", "basic_available_at", "circ_mv_unit",
    "industry_code", "industry_available_at", "industry_effective_from", "industry_effective_to",
]
ROSTER_COLUMNS = ["trade_date", "ts_code", "required_for_rank", "track_identity", "source_file_sha256"]
CALENDAR_COLUMNS = ["market_index", "trade_date", "declaration_ref", "signal_cutoff"]
LINEAGE_COLUMNS = [
    "ts_code", "trade_date", "field_group", "source_table", "source_file_sha256", "source_primary_key",
    "revision_id", "available_at", "selection_reason", "unit", "scale_to_canonical", "derivation",
]
CONSUMABLE_NAMES = (
    "normalized_panel.parquet", "universe_daily.parquet", "calendar.parquet", "lineage.parquet",
    "coverage_report.json", "data_gate_report.json", "snapshot_manifest.json",
)
FLOAT_COLUMNS = {
    "adj_open", "adj_high", "adj_low", "adj_close", "raw_open", "raw_high", "raw_low", "raw_close",
    "adj_factor", "amount_cny", "circ_mv_cny",
}
BOOL_COLUMNS = ("membership_known", "is_member", "st_known", "is_st")
INT_COLUMNS = ("membership_effective_from", "membership_effective_to", "st_effective_from", "st_effective_to", "industry_effective_from", "industry_effective_to")
TEXT_COLUMNS = (
    "signal_cutoff", "price_status", "price_available_at", "price_revision_id",
    "membership_available_at", "st_available_at", "amount_available_at", "amount_unit", "amount_derivation",
    "basic_available_at", "circ_mv_unit", "industry_code", "industry_available_at",
)


@dataclass(frozen=True)
class BuiltSnapshot:
    folder: Path
    manifest: dict[str, Any]
    panel: pd.DataFrame
    roster: pd.DataFrame
    calendar: pd.DataFrame
    lineage: pd.DataFrame
    coverage: dict[str, Any]
    gate: dict[str, Any]


def _blank(value: Any) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _stamp(value: Any) -> str:
    parsed = pd.Timestamp(value)
    if parsed.tzinfo is None or pd.isna(parsed):
        raise GateError("TIMEZONE_OR_TIMESTAMP_INVALID", value)
    local = parsed.tz_convert("Asia/Shanghai")
    suffix = local.strftime("%z")
    return local.strftime("%Y-%m-%dT%H:%M:%S") + suffix[:3] + ":" + suffix[3:]


def _clock(value: Any, trade_date: int, policy: SnapshotPolicy) -> str:
    text = _stamp(value)
    parsed = pd.Timestamp(text)
    zone = policy.payload["signal_clock"]["timezone"]
    local = parsed.tz_convert(zone)
    suffix = local.strftime("%z")
    clock = local.strftime("%H:%M:%S") + suffix[:3] + ":" + suffix[3:]
    if clock != policy.payload["signal_clock"]["synthetic_hand_case"] or int(local.strftime("%Y%m%d")) != int(trade_date):
        raise GateError("SOURCE_MANIFEST_INVALID", {"reason": "SIGNAL_CLOCK", "trade_date": int(trade_date)})
    return text


def _optional_int(value: Any) -> int | None:
    if _blank(value):
        return None
    number = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if not math.isfinite(float(number)) or float(number) % 1 != 0:
        raise GateError("EFFECTIVE_DATE_INVALID", value)
    return int(number)


def _frame(package: SourcePackage, table: str, columns: list[str]) -> pd.DataFrame:
    if table not in package.tables:
        raise GateError("SOURCE_MANIFEST_INVALID", {"reason": "TABLE_MISSING", "table": table})
    frame = package.tables[table]
    if frame.empty and len(frame.columns) == 0:
        return pd.DataFrame(columns=columns)
    missing = [column for column in columns if column not in frame]
    if missing:
        raise GateError("SOURCE_MANIFEST_INVALID", {"reason": "COLUMNS", "table": table, "missing": missing})
    return frame.copy()


def _with_status(frame: pd.DataFrame) -> pd.DataFrame:
    if "fact_status" not in frame:
        frame = frame.copy()
        frame["fact_status"] = "KNOWN"
    status = frame["fact_status"].where(~frame["fact_status"].map(_blank), "KNOWN")
    if not status.isin(["KNOWN", "UNKNOWN"]).all():
        raise GateError("SOURCE_MANIFEST_INVALID", "FACT_STATUS")
    frame = frame.copy()
    frame["fact_status"] = status
    return frame


def _file_hash(package: SourcePackage, table: str) -> str:
    for spec in package.manifest["tables"]:
        if spec["table_id"] == table:
            return spec["sha256"]
    raise GateError("SOURCE_MANIFEST_INVALID", table)


def _declared_unit(package: SourcePackage, table: str, canonical: str) -> str:
    for spec in package.manifest["tables"]:
        if spec["table_id"] != table:
            continue
        for field in spec.get("fields", {}).values():
            if field.get("canonical") == canonical:
                unit = field.get("unit")
                if not isinstance(unit, str):
                    raise GateError("SOURCE_UNIT_UNVERIFIED", {"field": canonical, "unit": unit})
                return unit
    raise GateError("SOURCE_UNIT_UNVERIFIED", {"field": canonical, "table": table})


def _select_daily(frame: pd.DataFrame, cutoffs: dict[int, str]) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    parts = []
    for date, cutoff in cutoffs.items():
        day = frame.loc[frame["trade_date"].eq(date)]
        if day.empty:
            continue
        parts.append(select_asof(day, business_keys=["ts_code", "trade_date"], revision_column="revision_id", order_columns=["available_at", "revision_id"], cutoff=cutoff, available_column="available_at"))
    if not parts:
        return frame.iloc[0:0].copy()
    return pd.concat(parts, ignore_index=True)


def _keyset(frame: pd.DataFrame) -> set[tuple[str, int]]:
    if frame.empty or "ts_code" not in frame or "trade_date" not in frame:
        return set()
    return set(zip(frame["ts_code"].astype(str), frame["trade_date"].astype(int)))


def _records(frame: pd.DataFrame) -> dict[tuple[str, int], Any]:
    if frame.empty:
        return {}
    return {(str(row.ts_code), int(row.trade_date)): row for row in frame.itertuples(index=False)}


def _line(code: str, date: int, group: str, table: str, digest: str, revision: Any, available: Any, reason: str, unit: str | None, scale: int | None, derivation: str) -> dict[str, Any]:
    key = "" if not code else f"ts_code={code}|trade_date={date}|revision_id={'' if _blank(revision) else revision}"
    return {
        "ts_code": code, "trade_date": int(date), "field_group": group, "source_table": table,
        "source_file_sha256": digest, "source_primary_key": key, "revision_id": "" if _blank(revision) else str(revision),
        "available_at": "" if _blank(available) else _stamp(available), "selection_reason": reason,
        "unit": unit or "", "scale_to_canonical": "" if scale is None else str(int(scale)), "derivation": derivation,
    }


def _prepare_calendar(package: SourcePackage, policy: SnapshotPolicy, contract: Contract) -> tuple[pd.DataFrame, dict[int, str], list[int]]:
    frame = _frame(package, "calendar", ["trade_date", "market_index", "declaration_ref", "signal_cutoff"])
    if frame.empty:
        raise GateError("CALENDAR_OR_INPUT_EMPTY")
    frame["trade_date"] = frame["trade_date"].map(_optional_int)
    unique_keys(frame, ["trade_date"], "calendar")
    if not frame["market_index"].eq("DECLARED_SYNTHETIC").all() or not frame["declaration_ref"].eq(package.manifest["case_id"]).all():
        raise GateError("SOURCE_MANIFEST_INVALID", "SYNTHETIC_CALENDAR_DECLARATION")
    dates = [int(value) for value in frame.sort_values("trade_date", kind="stable")["trade_date"].tolist()]
    certified = [int(value) for value in package.manifest["calendar_dates"]]
    validate_calendar_binding(dates, certified)
    scope = contract.section("scope")
    if dates[0] != scope["feature_origin"] or dates[-1] != scope["output_end"]:
        raise GateError("SOURCE_MANIFEST_INVALID", "SCOPE_CALENDAR")
    cutoffs = {}
    rows = []
    for record in frame.sort_values("trade_date", kind="stable").itertuples(index=False):
        cutoff = _clock(record.signal_cutoff, int(record.trade_date), policy)
        cutoffs[int(record.trade_date)] = cutoff
        rows.append({"market_index": "DECLARED_SYNTHETIC", "trade_date": int(record.trade_date), "declaration_ref": str(record.declaration_ref), "signal_cutoff": cutoff})
    calendar = pd.DataFrame(rows, columns=CALENDAR_COLUMNS)
    return calendar, cutoffs, dates


def _prepare_roster(package: SourcePackage, dates: list[int]) -> tuple[pd.DataFrame, list[str]]:
    frame = _frame(package, "roster", ["trade_date", "ts_code", "required_for_rank", "track_identity"])
    frame["trade_date"] = frame["trade_date"].map(_optional_int)
    frame["ts_code"] = frame["ts_code"].astype(str)
    require_real_bools(frame, ["required_for_rank", "track_identity"])
    frame["required_for_rank"] = frame["required_for_rank"].astype(bool)
    frame["track_identity"] = frame["track_identity"].astype(bool)
    unique_keys(frame, ["trade_date", "ts_code"], "roster")
    if (frame["required_for_rank"] & ~frame["track_identity"]).any() or not frame["track_identity"].all():
        raise GateError("ROSTER_ROLE_INVALID")
    codes = [str(code) for code in package.manifest["roster_codes"]]
    if codes != sorted(set(codes)):
        raise GateError("SOURCE_MANIFEST_INVALID", "ROSTER_ORDER")
    expected = {(date, code) for date in dates for code in codes}
    actual = {(int(row.trade_date), str(row.ts_code)) for row in frame.itertuples(index=False)}
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing or extra or set(frame["ts_code"]) != set(codes):
        raise GateError("SNAPSHOT_COVERAGE_INCOMPLETE", {"reason": "ROSTER_GRID", "missing_count": len(missing), "missing": [{"trade_date": date, "ts_code": code} for date, code in missing[:10]], "extra_count": len(extra), "missing_codes": sorted({code for _, code in missing})})
    digest = _file_hash(package, "roster")
    rows = frame.sort_values(["trade_date", "ts_code"], kind="stable")
    roster = pd.DataFrame({
        "trade_date": rows["trade_date"].astype(int),
        "ts_code": rows["ts_code"].astype(str),
        "required_for_rank": rows["required_for_rank"].astype(bool),
        "track_identity": rows["track_identity"].astype(bool),
        "source_file_sha256": digest,
    }, columns=ROSTER_COLUMNS)
    return roster.reset_index(drop=True), codes


def _prepare_lifecycle(package: SourcePackage, codes: list[str], dates: list[int]) -> None:
    frame = _frame(package, "lifecycle", ["ts_code", "listed_on", "delisted_on"])
    if "ts_code" not in frame:
        raise GateError("SOURCE_MANIFEST_INVALID", "LIFECYCLE")
    present = set() if frame.empty else set(frame["ts_code"].astype(str))
    missing = sorted(set(codes) - present)
    extra = sorted(present - set(codes))
    if missing or extra or frame["ts_code"].astype(str).duplicated().any():
        raise GateError("SNAPSHOT_COVERAGE_INCOMPLETE", {"reason": "LIFECYCLE_GRID", "missing_codes": missing, "extra_codes": extra})
    records = []
    for record in frame.itertuples(index=False):
        records.append({"ts_code": str(record.ts_code), "listed_on": _optional_int(record.listed_on), "delisted_on": _optional_int(record.delisted_on)})
    require_supported_lifecycle(records, feature_origin=dates[0], output_end=dates[-1])


def _interval_table(package: SourcePackage, table: str, value_column: str) -> pd.DataFrame:
    frame = _with_status(_frame(package, table, ["ts_code", "revision_id", value_column, "effective_from", "effective_to", "available_at"]))
    if frame.empty:
        return frame
    frame["ts_code"] = frame["ts_code"].astype(str)
    frame["effective_from"] = frame["effective_from"].map(_optional_int)
    if frame["effective_from"].map(_blank).any():
        raise GateError("EFFECTIVE_DATE_INVALID", table)
    return frame


def _choose_interval(records: list[Any], trade_date: int) -> Any | None:
    covering = []
    for record in records:
        end = _optional_int(record.effective_to)
        if int(record.effective_from) <= trade_date and (end is None or trade_date <= end):
            covering.append(record)
    if len(covering) > 1:
        raise GateError("SOURCE_MANIFEST_INVALID", "INTERVAL_OVERLAP")
    if covering:
        return covering[0]
    started = [record for record in records if int(record.effective_from) <= trade_date]
    if started:
        return max(started, key=lambda record: int(record.effective_from))
    if records:
        return min(records, key=lambda record: int(record.effective_from))
    return None


def _intervals_at(frame: pd.DataFrame, cutoff: str) -> dict[str, list[Any]]:
    if frame.empty:
        return {}
    chosen = select_asof(frame, business_keys=["ts_code", "effective_from"], revision_column="revision_id", order_columns=["available_at", "revision_id"], cutoff=cutoff, available_column="available_at")
    grouped: dict[str, list[Any]] = {}
    for record in chosen.itertuples(index=False):
        grouped.setdefault(str(record.ts_code), []).append(record)
    return grouped


def _window_dates(policy: SnapshotPolicy, name: str, dates: list[int], scope: dict[str, Any]) -> list[int]:
    return required_dates(policy.payload["consumer_windows"][name], calendar=dates, feature_origin=scope["feature_origin"], output_start=scope["output_start"], output_end=scope["output_end"])


def _consumer_count(required: int, unknown: int, outside: int) -> dict[str, int]:
    return {"required": required, "missing": 0, "unknown": unknown, "not_required": outside}


def normalize_package(package: SourcePackage, contract: Contract, policy: SnapshotPolicy) -> dict[str, Any]:
    """Build frames in memory. Callers write them only after every check succeeds."""
    for table in REQUIRED_TABLES:
        if table not in package.tables:
            raise GateError("SOURCE_MANIFEST_INVALID", {"reason": "TABLE_MISSING", "table": table})
    calendar, cutoffs, dates = _prepare_calendar(package, policy, contract)
    roster, codes = _prepare_roster(package, dates)
    _prepare_lifecycle(package, codes, dates)
    scope = contract.section("scope")
    price_dates = set(_window_dates(policy, "calendar_prices_lifecycle", dates, scope))
    amount_dates = set(_window_dates(policy, "amount_adv20", dates, scope))
    industry_dates = set(_window_dates(policy, "industry_circ_mv", dates, scope))
    membership_dates = set(_window_dates(policy, "membership_st", dates, scope))
    expected = {(code, date) for code in codes for date in dates}

    raw = _with_status(_frame(package, "prices_raw", ["ts_code", "trade_date", "revision_id", *PRICE_COLUMNS, "available_at"]))
    adjusted = _with_status(_frame(package, "prices_adj", ["ts_code", "trade_date", "revision_id", *[f"adj_{column}" for column in PRICE_COLUMNS], "available_at"]))
    if "adj_factor" not in adjusted:
        raise GateError("ADJUSTMENT_FACTOR_MISSING")
    if "price_status" not in raw:
        raw["price_status"] = "TRADED"
    if not raw["price_status"].isin(["TRADED", "UNKNOWN"]).all():
        raise GateError("PRICE_STATUS_INVALID")
    raw["trade_date"] = raw["trade_date"].map(_optional_int)
    adjusted["trade_date"] = adjusted["trade_date"].map(_optional_int)
    raw["ts_code"] = raw["ts_code"].astype(str)
    adjusted["ts_code"] = adjusted["ts_code"].astype(str)
    raw_source, adj_source = _keyset(raw), _keyset(adjusted)
    extra = sorted((raw_source | adj_source) - expected)
    if extra:
        raise GateError("SNAPSHOT_COVERAGE_INCOMPLETE", {"reason": "EXTRA_PRICE_KEYS", "extra_count": len(extra), "extra": [{"ts_code": code, "trade_date": date} for code, date in extra[:10]]})
    usable_raw = _select_daily(raw, cutoffs)
    usable_adj = _select_daily(adjusted, cutoffs)
    raw_map, adj_map = _records(usable_raw), _records(usable_adj)
    halts = _with_status(_frame(package, "halts", ["ts_code", "trade_date", "revision_id", "halt_scope", "available_at"]))
    if not halts.empty:
        halts["trade_date"] = halts["trade_date"].map(_optional_int)
        halts["ts_code"] = halts["ts_code"].astype(str)
        if not halts["halt_scope"].isin(["FULL_DAY", "PARTIAL_DAY"]).all():
            raise GateError("SOURCE_MANIFEST_INVALID", "HALT_SCOPE")
    full_halts = halts.loc[halts["halt_scope"].eq("FULL_DAY")] if not halts.empty else halts
    halt_source = _keyset(full_halts)
    halt_map = _records(_select_daily(full_halts, cutoffs) if not full_halts.empty else full_halts)
    missing = sorted(key for key in expected if key not in raw_source and key not in halt_source and key not in raw_map)
    if missing:
        missing_codes = sorted({code for code, _ in missing})
        raise GateError("SNAPSHOT_COVERAGE_INCOMPLETE", {"reason": "PRICE_GRID", "missing_count": len(missing), "missing_codes": missing_codes, "missing": [{"ts_code": code, "trade_date": date} for code, date in missing[:10]]})

    traded_keys = []
    roles: dict[tuple[str, int], str] = {}
    for key in sorted(expected):
        code, date = key
        if key in halt_map and key in raw_map:
            raise GateError("SOURCE_MANIFEST_INVALID", {"reason": "HALT_TRADE_CONFLICT", "ts_code": code, "trade_date": date})
        if key in halt_map:
            roles[key] = "HALT"
        elif key in raw_map and raw_map[key].fact_status == "KNOWN" and getattr(raw_map[key], "price_status", "TRADED") == "TRADED":
            if key in adj_map and adj_map[key].fact_status == "KNOWN":
                roles[key] = "TRADED"
                traded_keys.append(key)
            elif key not in adj_source:
                roles[key] = "UNPAIRED"
                traded_keys.append(key)
            else:
                roles[key] = "UNKNOWN"
        else:
            roles[key] = "UNKNOWN"
    joined = {}
    if traded_keys:
        raw_rows = pd.DataFrame([raw_map[key]._asdict() for key in traded_keys])
        paired = [key for key in traded_keys if roles[key] == "TRADED"]
        adj_rows = pd.DataFrame([adj_map[key]._asdict() for key in paired]) if paired else pd.DataFrame(columns=["ts_code", "trade_date"])
        if _keyset(raw_rows) != _keyset(adj_rows):
            raise GateError("RAW_ADJUSTED_KEY_SET_MISMATCH", {"raw_only": len(_keyset(raw_rows) - _keyset(adj_rows)), "adj_only": len(_keyset(adj_rows) - _keyset(raw_rows))})
        checked = validate_join(raw_rows, adj_rows)
        for record in checked.itertuples(index=False):
            joined[(str(record.ts_code), int(record.trade_date))] = record

    amount = _with_status(_frame(package, "amount", ["ts_code", "trade_date", "revision_id", "amount", "unit", "available_at"]))
    circ = _with_status(_frame(package, "circ_mv", ["ts_code", "trade_date", "revision_id", "circ_mv", "unit", "available_at"]))
    for frame, label in ((amount, "amount"), (circ, "circ_mv")):
        if not frame.empty:
            frame["trade_date"] = frame["trade_date"].map(_optional_int)
            frame["ts_code"] = frame["ts_code"].astype(str)
    amount_unit = _declared_unit(package, "amount", "amount_cny")
    circ_unit = _declared_unit(package, "circ_mv", "circ_mv_cny")
    amount_map = _records(_select_daily(amount, cutoffs))
    circ_map = _records(_select_daily(circ, cutoffs))
    amount_source, circ_source = _keyset(amount), _keyset(circ)
    membership = _interval_table(package, "membership", "is_member")
    st_table = _interval_table(package, "st_status", "is_st")
    industry = _interval_table(package, "industry", "industry_code")
    for table, frame in (("membership", membership), ("st_status", st_table), ("industry", industry)):
        present = set() if frame.empty else set(frame["ts_code"])
        required_window = membership_dates if table != "industry" else industry_dates
        if required_window and present != set(codes):
            raise GateError("SNAPSHOT_COVERAGE_INCOMPLETE", {"reason": table.upper(), "missing_codes": sorted(set(codes) - present)})
    membership_at = {date: _intervals_at(membership, cutoffs[date]) for date in dates}
    st_at = {date: _intervals_at(st_table, cutoffs[date]) for date in dates}
    industry_at = {date: _intervals_at(industry, cutoffs[date]) for date in dates}

    unknown_keys: set[tuple[str, int]] = set()
    unknown_fields: set[str] = set()
    field_unknown = {"prices": 0, "amount_adv20": 0, "industry_circ_mv": 0, "membership_st": 0}
    panel_rows = []
    lineage = []
    raw_digest, adj_digest = _file_hash(package, "prices_raw"), _file_hash(package, "prices_adj")
    amount_digest, circ_digest = _file_hash(package, "amount"), _file_hash(package, "circ_mv")
    membership_digest, st_digest, industry_digest = _file_hash(package, "membership"), _file_hash(package, "st_status"), _file_hash(package, "industry")
    halt_digest = _file_hash(package, "halts")

    def _note(kind: str, field: str, key: tuple[str, int]) -> None:
        unknown_keys.add(key)
        unknown_fields.add(field)
        field_unknown[kind] += 1

    def _daily_value(key: tuple[str, int], mapping: dict, source: set, required: bool, column: str, canonical: str, declared: str, policy_field: str) -> tuple[float | None, str | None, str | None, str, int | None, Any]:
        code, date = key
        if key in mapping:
            record = mapping[key]
            if record.fact_status == "UNKNOWN" or record.unit != declared:
                if record.unit != declared and record.fact_status != "UNKNOWN":
                    raise GateError("SOURCE_UNIT_UNVERIFIED", {"field": canonical, "unit": record.unit})
                if required:
                    _note("amount_adv20" if canonical == "amount_cny" else "industry_circ_mv", canonical, key)
                return None, None, None, "EXPLICIT_UNKNOWN", None, record
            value = convert_to_cny(getattr(record, column), declared, policy_field, policy)
            scale = int(policy.payload["units"][policy_field]["factors"][declared])
            return value, _stamp(record.available_at), declared, "POLICY_UNIT_FACTOR", scale, record
        if not required:
            return None, None, None, "NOT_REQUIRED", None, None
        if key in source:
            _note("amount_adv20" if canonical == "amount_cny" else "industry_circ_mv", canonical, key)
            return None, None, None, "LATE_EXCLUDED", None, None
        raise GateError("SNAPSHOT_COVERAGE_INCOMPLETE", {"reason": canonical.upper(), "ts_code": code, "trade_date": date, "missing_codes": [code]})

    for key in sorted(expected):
        code, date = key
        role = roles[key]
        row = {column: pd.NA for column in PANEL_COLUMNS}
        row.update(ts_code=code, trade_date=date, signal_cutoff=cutoffs[date], membership_known=False, is_member=False, st_known=False, is_st=False)
        if role == "HALT":
            record = halt_map[key]
            row.update(price_status="VERIFIED_FULL_DAY_HALT", price_available_at=_stamp(record.available_at), price_revision_id=str(record.revision_id), amount_cny=0.0, amount_available_at=_stamp(record.available_at), amount_unit="", amount_derivation="VERIFIED_HALT_ZERO")
            lineage.append(_line(code, date, "halt", "halts", halt_digest, record.revision_id, record.available_at, "ASOF_MAXIMUM_DECLARED_ORDER", None, None, "VERIFIED_HALT_ZERO"))
        elif role == "TRADED":
            record = joined[key]
            raw_record, adj_record = raw_map[key], adj_map[key]
            available = _stamp(max(pd.Timestamp(raw_record.available_at), pd.Timestamp(adj_record.available_at)))
            row.update(price_status="TRADED", price_available_at=available, price_revision_id=f"{raw_record.revision_id}/{adj_record.revision_id}", adj_factor=float(record.adj_factor))
            for column in PRICE_COLUMNS:
                row[f"raw_{column}"] = float(getattr(record, column))
                row[f"adj_{column}"] = float(getattr(record, f"adj_{column}"))
            lineage.append(_line(code, date, "price_raw", "prices_raw", raw_digest, raw_record.revision_id, raw_record.available_at, "ASOF_MAXIMUM_DECLARED_ORDER", "DECLARED_PRICE", None, "ADJUSTED_EQUALS_RAW_TIMES_STORED_FACTOR"))
            lineage.append(_line(code, date, "price_adj", "prices_adj", adj_digest, adj_record.revision_id, adj_record.available_at, "ASOF_MAXIMUM_DECLARED_ORDER", "DECLARED_PRICE", None, "ADJUSTED_EQUALS_RAW_TIMES_STORED_FACTOR"))
        else:
            if date in price_dates:
                _note("prices", "price", key)
            row.update(price_status="UNKNOWN", price_available_at=pd.NA, price_revision_id="", amount_derivation="LATE_OR_UNKNOWN_PRICE")
            lineage.append(_line(code, date, "price_raw", "prices_raw", raw_digest, None, None, "EXCLUDED_NOT_USABLE_AT_CUTOFF", "DECLARED_PRICE", None, "LATE_OR_UNKNOWN_PRICE"))
        if role != "HALT":
            value, available, unit, derivation, scale, source = _daily_value(key, amount_map, amount_source, date in amount_dates, "amount", "amount_cny", amount_unit, "amount_cny")
            row.update(amount_cny=value if value is not None else pd.NA, amount_available_at=available if available else pd.NA, amount_unit=unit or "", amount_derivation=derivation)
            if source is not None and derivation == "POLICY_UNIT_FACTOR":
                lineage.append(_line(code, date, "amount", "amount", amount_digest, source.revision_id, source.available_at, "ASOF_MAXIMUM_DECLARED_ORDER", unit, scale, derivation))
            elif derivation != "NOT_REQUIRED":
                lineage.append(_line(code, date, "amount", "amount", amount_digest, None, None, derivation, unit, scale, derivation))
        value, available, unit, derivation, scale, source = _daily_value(key, circ_map, circ_source, date in industry_dates, "circ_mv", "circ_mv_cny", circ_unit, "circ_mv_cny")
        row.update(circ_mv_cny=value if value is not None else pd.NA, basic_available_at=available if available else pd.NA, circ_mv_unit=unit or "")
        if source is not None and derivation == "POLICY_UNIT_FACTOR":
            lineage.append(_line(code, date, "circ_mv", "circ_mv", circ_digest, source.revision_id, source.available_at, "ASOF_MAXIMUM_DECLARED_ORDER", unit, scale, derivation))
        elif derivation != "NOT_REQUIRED":
            lineage.append(_line(code, date, "circ_mv", "circ_mv", circ_digest, None, None, derivation, unit, scale, derivation))
        for label, grouped, value_name, known_name, flag_name, digest, required in (
            ("membership", membership_at, "is_member", "membership_known", "is_member", membership_digest, date in membership_dates),
            ("st", st_at, "is_st", "st_known", "is_st", st_digest, date in membership_dates),
            ("industry", industry_at, "industry_code", None, None, industry_digest, date in industry_dates),
        ):
            chosen = _choose_interval(grouped[date].get(code, []), date) if required or code in grouped[date] else None
            if not required and chosen is None:
                lineage.append(_line(code, date, label, label if label != "st" else "st_status", digest, None, None, "NOT_REQUIRED", None, None, "NOT_REQUIRED"))
                continue
            if chosen is None or chosen.fact_status == "UNKNOWN":
                if required:
                    _note("membership_st" if label != "industry" else "industry_circ_mv", label, key)
                lineage.append(_line(code, date, label, label if label != "st" else "st_status", digest, None, None, "EXPLICIT_UNKNOWN" if chosen is not None else "LATE_EXCLUDED", None, None, "FIELD_UNKNOWN"))
                continue
            end = _optional_int(chosen.effective_to)
            inside = int(chosen.effective_from) <= date and (end is None or date <= end)
            available = _stamp(chosen.available_at)
            if label == "industry":
                row.update(industry_code=chosen.industry_code if inside and not _blank(chosen.industry_code) else pd.NA, industry_available_at=available, industry_effective_from=int(chosen.effective_from), industry_effective_to=end if end is not None else pd.NA)
            else:
                flag = bool(getattr(chosen, value_name)) if inside else False
                if not _is_bool(getattr(chosen, value_name)):
                    require_real_bools(pd.DataFrame({value_name: [getattr(chosen, value_name)]}), [value_name])
                row.update({known_name: True, flag_name: flag, f"{label}_available_at": available, f"{label}_effective_from": int(chosen.effective_from), f"{label}_effective_to": end if end is not None else pd.NA})
            lineage.append(_line(code, date, label, label if label != "st" else "st_status", digest, chosen.revision_id, chosen.available_at, "ASOF_MAXIMUM_DECLARED_ORDER", None, None, "CLOSED_CLOSED_INTERVAL"))
        panel_rows.append(row)

    panel = _canonicalize_panel(pd.DataFrame(panel_rows))
    validate_normalized_panel(panel, dates)
    lineage_frame = pd.DataFrame(lineage, columns=LINEAGE_COLUMNS).sort_values(["trade_date", "ts_code", "field_group", "source_table"], kind="stable").reset_index(drop=True)
    outside_industry = len(expected) - len({(code, date) for code, date in expected if date in industry_dates})
    outside_amount = len(expected) - len({(code, date) for code, date in expected if date in amount_dates})
    coverage = {
        "schema": COVERAGE_SCHEMA,
        "expected_keys": len(expected),
        "actual_keys": len(panel),
        "duplicate_keys": 0,
        "missing_keys": [],
        "extra_keys": [],
        "unknown_state_count": len(unknown_keys),
        "consumers": {
            "prices": _consumer_count(len(expected), field_unknown["prices"], 0),
            "amount_adv20": _consumer_count(len(codes) * len(amount_dates), field_unknown["amount_adv20"], outside_amount),
            "industry_circ_mv": _consumer_count(len(codes) * len(industry_dates), field_unknown["industry_circ_mv"], outside_industry),
            "membership_st": _consumer_count(len(codes) * len(membership_dates), field_unknown["membership_st"], 0),
        },
    }
    quality = "SYNTHETIC_SNAPSHOT_PARTIAL" if unknown_keys else "SYNTHETIC_SNAPSHOT_READY"
    gate = {
        "schema": GATE_SCHEMA,
        "status": quality,
        "mode": "SYNTHETIC",
        "integrity_status": "PRE_COMMIT_CHECK",
        "source_authority": package.authority,
        "coverage_status": "PARTIAL" if unknown_keys else "COMPLETE",
        "reasons": [] if not unknown_keys else [{"code": "FIELD_UNKNOWN", "fields": sorted(unknown_fields)}],
        "affected_fields": sorted(unknown_fields),
        "affected_dates": sorted({date for _, date in unknown_keys}),
        "affected_codes": sorted({code for code, _ in unknown_keys}),
        "permitted_consumers": ["SYNTHETIC_DIAGNOSTIC"] if unknown_keys else ["SYNTHETIC_ENGINEERING"],
        "outcomes_enabled": False,
        "network_requests": 0,
        "parameter_status": "PROPOSED",
    }
    if gate["status"] == "DATA_READY_FOR_ENGINEERING":
        raise GateError("REVIEW_RECEIPT_UNTRUSTED", "DATA_READY_FOR_ENGINEERING")
    logical = {
        "normalized_panel": frame_hash(panel),
        "universe_daily": frame_hash(roster),
        "calendar": _content_hash(calendar, ["trade_date"]),
        "lineage": frame_hash(lineage_frame),
        "coverage": fingerprint(coverage),
        "data_gate_report": fingerprint(gate),
    }
    return {"panel": panel, "roster": roster, "calendar": calendar, "lineage": lineage_frame, "coverage": coverage, "gate": gate, "logical_hashes": logical, "quality_status": quality}


def _content_hash(frame: pd.DataFrame, keys: list[str]) -> str:
    selected = frame.sort_values(keys, kind="stable")[list(frame.columns)]
    return fingerprint({"columns": list(selected.columns), "data": selected.to_json(orient="split", date_format="iso", index=False, double_precision=15)})


def _canonicalize_panel(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out["ts_code"] = out["ts_code"].astype(str)
    out["trade_date"] = out["trade_date"].astype(int)
    for column in FLOAT_COLUMNS:
        out[column] = pd.to_numeric(out[column], errors="coerce")
    for column in BOOL_COLUMNS:
        out[column] = pd.Series([_boolean(value) for value in out[column]], index=out.index, dtype="bool")
    for column in INT_COLUMNS:
        out[column] = pd.to_numeric(out[column], errors="coerce").astype("Int64")
    for column in TEXT_COLUMNS:
        out[column] = out[column].map(lambda value: pd.NA if _blank(value) else str(value)).astype("string")
    return out[PANEL_COLUMNS].sort_values(KEYS, kind="stable").reset_index(drop=True)


def _is_bool(value: Any) -> bool:
    return isinstance(value, (bool, np.bool_))


def _boolean(value: Any) -> bool:
    if not _is_bool(value):
        raise GateError("BOOLEAN_STATE_INVALID", value)
    return bool(value)


def _identity(package: SourcePackage, contract: Contract, policy: SnapshotPolicy, source_hash: str, receipt_hash: str, normalized: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": SNAPSHOT_SCHEMA,
        "mode": "SYNTHETIC",
        "contract_hash": contract.hash,
        "parent_contract_hash": package.manifest["parent_contract_hash"],
        "snapshot_policy_hash": policy.file_hash,
        "source_definition_sha256": policy.document_hash,
        "implementation_hash": implementation_hash(),
        "source_manifest_sha256": source_hash,
        "review_receipt_sha256": receipt_hash,
        "logical_hashes": normalized["logical_hashes"],
        "quality_status": normalized["quality_status"],
        "diagnostic_only": normalized["quality_status"] != "SYNTHETIC_SNAPSHOT_READY",
        "scope": contract.section("scope"),
        "tracking_policy": policy.payload["lifecycle"]["supported"],
        "outcomes_enabled": False,
        "network_requests": 0,
        "parameter_status": "PROPOSED",
    }


def snapshot_identity(package: SourcePackage, contract: Contract, policy: SnapshotPolicy, source_hash: str, receipt_hash: str, normalized: dict[str, Any]) -> str:
    """Identity excludes the run id, creation time, and output path."""
    return fingerprint(_identity(package, contract, policy, source_hash, receipt_hash, normalized))


def _arrow_schema(frame: pd.DataFrame) -> pa.Schema:
    fields = []
    for name in frame.columns:
        dtype = frame[name].dtype
        if name == "trade_date" or str(dtype) == "Int64" or str(dtype).startswith("int"):
            nullable = name != "trade_date"
            fields.append(pa.field(name, pa.int64(), nullable=nullable))
        elif str(dtype) == "bool":
            fields.append(pa.field(name, pa.bool_(), nullable=False))
        elif "float" in str(dtype):
            fields.append(pa.field(name, pa.float64(), nullable=True))
        else:
            fields.append(pa.field(name, pa.string(), nullable=True))
    return pa.schema(fields)


def _write_frame(path: Path, frame: pd.DataFrame) -> None:
    table = pa.Table.from_pandas(frame, schema=_arrow_schema(frame), preserve_index=False)
    table = table.replace_schema_metadata(None)
    pq.write_table(table, path, compression="snappy")


def _read_frame(path: Path) -> pd.DataFrame:
    return pq.read_table(path).to_pandas()


def _artifact(path: Path, rows: int | None, schema: list[str] | str) -> dict[str, Any]:
    return {"relative_path": path.name, "sha256": file_hash(path), "rows": rows, "schema": schema}


def _remove_consumables(folder: Path) -> None:
    for name in CONSUMABLE_NAMES:
        path = folder / name
        if path.is_file():
            path.unlink()


def _refuse_output(root: Path, input_root: Path) -> None:
    resolved = root.resolve()
    source = input_root.resolve()
    public = (ROOT / "data/parquet").resolve()
    evidence = (ROOT / "momentum_pullback/evidence").resolve()
    if resolved == public or resolved.is_relative_to(public) or resolved == evidence or resolved.is_relative_to(evidence):
        raise GateError("PUBLIC_CACHE_WRITE_FORBIDDEN")
    if resolved == source or resolved.is_relative_to(source):
        raise GateError("SOURCE_MANIFEST_INVALID", "OUTPUT_INSIDE_INPUT")


def _input_files(manifest_path: Path, package: SourcePackage, policy: SnapshotPolicy, oracle_files: list[Path]) -> list[Path]:
    files = [manifest_path, package.input_root / package.manifest["review_receipt_ref"], Path(policy.source_path), ROOT / policy.payload["documents"][0]["path"], ROOT / INDEX_RELATIVE]
    files.extend(package.input_root / spec["relative_path"] for spec in package.manifest["tables"])
    files.extend(oracle_files)
    return files


def _blocked(folder: Path, error: GateError) -> None:
    _remove_consumables(folder)
    details = error.details if isinstance(error.details, dict) else {"details": error.details}
    write_json(folder / "blocked.json", {"status": "DATA_BLOCKED", "reason": error.code, "details": _jsonable(details), "outcomes_enabled": False, "network_requests": 0, "consumable_panel": False, "quality_status": "DATA_BLOCKED"})


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (bool, int, str)) or value is None:
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        return value
    return str(value)


def build_snapshot(manifest_path: Path, *, contract: Contract, policy: SnapshotPolicy, mode: str, root: Path = ROOT, oracle_files: list[Path] | None = None, before_commit: Callable[[Path], None] | None = None) -> BuiltSnapshot:
    """Write tables first and the manifest last. Failure leaves no committed snapshot."""
    if mode not in {"SYNTHETIC", "REAL"}:
        raise GateError("SNAPSHOT_MODE_MISMATCH", mode)
    allowed = [manifest_path.parent.resolve()]
    package = load_source_package(manifest_path, policy=policy, contract=contract, allowed_roots=allowed)
    if package.manifest["mode"] != mode:
        raise GateError("SNAPSHOT_MODE_MISMATCH", {"manifest": package.manifest["mode"], "command": mode})
    if mode != "SYNTHETIC" or package.authority != "SYNTHETIC_DECLARATION":
        raise GateError("REVIEW_RECEIPT_UNTRUSTED", "NO_REAL_GRANT")
    _refuse_output(root, package.input_root)
    source_hash = file_hash(manifest_path)
    receipt_path = package.input_root / package.manifest["review_receipt_ref"]
    receipt_hash = file_hash(receipt_path)
    folder = None
    try:
        normalized = normalize_package(package, contract, policy)
        identity = _identity(package, contract, policy, source_hash, receipt_hash, normalized)
        snapshot_id = fingerprint(identity)
        consumed = [int(value) for value in normalized["calendar"]["trade_date"].tolist()]
        folder, run_manifest = create_run(contract, "build_snapshot", _input_files(manifest_path, package, policy, oracle_files or []), root=root, logical_inputs={"mode": mode, "schema": SNAPSHOT_SCHEMA, "snapshot_id": snapshot_id, "consumed_calendar": consumed, "source_manifest_sha256": source_hash, "review_receipt_sha256": receipt_hash})
        if folder.resolve().is_relative_to(package.input_root.resolve()):
            raise GateError("SOURCE_MANIFEST_INVALID", "OUTPUT_INSIDE_INPUT")
        _write_frame(folder / "normalized_panel.parquet", normalized["panel"])
        _write_frame(folder / "universe_daily.parquet", normalized["roster"])
        _write_frame(folder / "calendar.parquet", normalized["calendar"])
        _write_frame(folder / "lineage.parquet", normalized["lineage"])
        write_json(folder / "coverage_report.json", normalized["coverage"])
        write_json(folder / "data_gate_report.json", normalized["gate"])
        write_json(folder / "snapshot_policy_snapshot.json", {"snapshot_policy_hash": policy.file_hash, "source_definition_sha256": policy.document_hash, "parameter_status": "PROPOSED", "outcomes_enabled": False})
        if before_commit is not None:
            before_commit(folder)
        verify_run_inputs(run_manifest)
        artifacts = {
            "normalized_panel": _artifact(folder / "normalized_panel.parquet", len(normalized["panel"]), PANEL_COLUMNS),
            "universe_daily": _artifact(folder / "universe_daily.parquet", len(normalized["roster"]), ROSTER_COLUMNS),
            "calendar": _artifact(folder / "calendar.parquet", len(normalized["calendar"]), CALENDAR_COLUMNS),
            "lineage": _artifact(folder / "lineage.parquet", len(normalized["lineage"]), LINEAGE_COLUMNS),
            "coverage_report": _artifact(folder / "coverage_report.json", None, COVERAGE_SCHEMA),
            "data_gate_report": _artifact(folder / "data_gate_report.json", None, GATE_SCHEMA),
        }
        manifest = {**identity, "snapshot_id": snapshot_id, "run_id": run_manifest["run_id"], "source_manifest_path": str(manifest_path.resolve()), "artifacts": artifacts}
        write_json(folder / "snapshot_manifest.json", manifest)
        verify_run_inputs(run_manifest)
        if file_hash(manifest_path) != source_hash or file_hash(receipt_path) != receipt_hash:
            raise GateError("SNAPSHOT_CONTENT_CHANGED", "SOURCE_AFTER_COMMIT")
        return BuiltSnapshot(folder, manifest, normalized["panel"], normalized["roster"], normalized["calendar"], normalized["lineage"], normalized["coverage"], normalized["gate"])
    except GateError as error:
        if folder is None:
            folder, _ = create_run(contract, "build_snapshot", _input_files(manifest_path, package, policy, oracle_files or []), root=root, logical_inputs={"mode": mode, "schema": SNAPSHOT_SCHEMA, "source_manifest_sha256": source_hash, "blocked": error.code})
        _blocked(folder, error)
        details = error.details if isinstance(error.details, dict) else {"details": error.details}
        raise GateError(error.code, {**_jsonable(details), "artifact_dir": str(folder)}) from error


def _panel_from_file(path: Path) -> pd.DataFrame:
    frame = _read_frame(path)
    restored = frame.copy()
    for column in BOOL_COLUMNS:
        restored[column] = [_boolean(value) for value in restored[column]]
    return _canonicalize_panel(restored)


def read_snapshot(manifest_path: Path, *, contract: Contract, policy: SnapshotPolicy, mode: str) -> BuiltSnapshot:
    """Recompute source bindings and artifact hashes. A READY flag is not evidence."""
    if manifest_path.name != "snapshot_manifest.json" or not manifest_path.is_file():
        raise GateError("SOURCE_MANIFEST_INVALID", "SNAPSHOT_NOT_COMMITTED")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise GateError("SOURCE_MANIFEST_INVALID", "SNAPSHOT_JSON") from error
    if manifest.get("schema") != SNAPSHOT_SCHEMA or manifest.get("outcomes_enabled") is not False or manifest.get("network_requests") != 0:
        raise GateError("SOURCE_MANIFEST_INVALID", "SNAPSHOT_HEADER")
    if manifest.get("quality_status") == "DATA_READY_FOR_ENGINEERING" or manifest.get("parameter_status") != "PROPOSED":
        raise GateError("REVIEW_RECEIPT_UNTRUSTED", "SNAPSHOT_CANNOT_GRANT_REAL_OR_OUTCOMES")
    if manifest.get("mode") != mode:
        raise GateError("SNAPSHOT_MODE_MISMATCH", {"manifest": manifest.get("mode"), "command": mode})
    if mode != "SYNTHETIC":
        raise GateError("REVIEW_RECEIPT_UNTRUSTED", "NO_REAL_GRANT")
    ready = manifest.get("quality_status") == "SYNTHETIC_SNAPSHOT_READY"
    partial = manifest.get("quality_status") == "SYNTHETIC_SNAPSHOT_PARTIAL"
    if ready == manifest.get("diagnostic_only") or not (ready or partial):
        raise GateError("SOURCE_MANIFEST_INVALID", "QUALITY_FLAG")
    if manifest.get("contract_hash") != contract.hash or manifest.get("snapshot_policy_hash") != policy.file_hash or manifest.get("implementation_hash") != implementation_hash():
        raise GateError("SNAPSHOT_CONTENT_CHANGED", "IDENTITY")
    folder = manifest_path.parent
    for name, spec in manifest.get("artifacts", {}).items():
        path = folder / spec["relative_path"]
        if path.name != spec["relative_path"] or not path.is_file() or file_hash(path) != spec["sha256"]:
            raise GateError("SNAPSHOT_CONTENT_CHANGED", name)
    source_path = Path(manifest["source_manifest_path"])
    if not source_path.is_file() or file_hash(source_path) != manifest["source_manifest_sha256"]:
        raise GateError("SNAPSHOT_CONTENT_CHANGED", "SOURCE_MANIFEST")
    package = load_source_package(source_path, policy=policy, contract=contract, allowed_roots=[source_path.parent.resolve()])
    if package.manifest["calendar_dates"] != [int(value) for value in _read_frame(folder / "calendar.parquet")["trade_date"].tolist()]:
        raise GateError("CERTIFIED_CALENDAR_MISMATCH", "SNAPSHOT_CALENDAR_EDIT")
    normalized = normalize_package(package, contract, policy)
    identity = snapshot_identity(package, contract, policy, manifest["source_manifest_sha256"], manifest["review_receipt_sha256"], normalized)
    panel = _panel_from_file(folder / "normalized_panel.parquet")
    if identity != manifest["snapshot_id"] or normalized["logical_hashes"] != manifest["logical_hashes"] or frame_hash(panel) != normalized["logical_hashes"]["normalized_panel"]:
        raise GateError("SNAPSHOT_CONTENT_CHANGED", "LOGICAL_CONTENT")
    if file_hash(source_path.parent / package.manifest["review_receipt_ref"]) != manifest["review_receipt_sha256"]:
        raise GateError("SNAPSHOT_CONTENT_CHANGED", "REVIEW_RECEIPT")
    validate_normalized_panel(panel, [int(value) for value in normalized["calendar"]["trade_date"].tolist()])
    return BuiltSnapshot(folder, manifest, panel, normalized["roster"], normalized["calendar"], normalized["lineage"], normalized["coverage"], normalized["gate"])

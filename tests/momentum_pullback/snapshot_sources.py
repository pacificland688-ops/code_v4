"""Build declared synthetic source packages for snapshot tests."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

from momentum_pullback.casebook import hand_panel
from momentum_pullback.contracts import Contract, validate_contract


def narrow_contract(parent: Contract, origin: int, output_start: int, output_end: int) -> Contract:
    payload = parent.payload
    payload["scope"] = {"purpose": "ENGINEERING_ONLY", "feature_origin": origin, "output_start": output_start, "output_end": output_end}
    return validate_contract(payload)


def _day(date: int) -> str:
    return pd.Timestamp(str(int(date))).strftime("%Y-%m-%d")


def _available(date: int, clock: str = "17:00:00") -> str:
    return f"{_day(date)}T{clock}+08:00"


def _cutoff(date: int) -> str:
    return f"{_day(date)}T18:00:00+08:00"


def flat_package(dates: list[int], codes: list[str], *, close: float, factor: float, amount: float, amount_unit: str, circ: float, circ_unit: str, industry: str = "SYNTHETIC_INDUSTRY", industry_from: int | None = None, industry_available: int | None = None, circ_dates: list[int] | None = None, amount_dates: list[int] | None = None, price_dates: list[int] | None = None, industry_status: str = "KNOWN") -> dict[str, list[dict]]:
    """One flat traded grid. Dates are an explicit declaration, not a generated exchange calendar."""
    industry_from = dates[0] if industry_from is None else industry_from
    industry_available = industry_from if industry_available is None else industry_available
    price_dates = dates if price_dates is None else price_dates
    amount_dates = dates if amount_dates is None else amount_dates
    circ_dates = dates if circ_dates is None else circ_dates
    raw_rows, adj_rows, amount_rows, circ_rows, roster = [], [], [], [], []
    for code in codes:
        for date in dates:
            roster.append({"trade_date": date, "ts_code": code, "required_for_rank": True, "track_identity": True})
            if date in price_dates:
                raw_price = close / factor
                raw_rows.append({"ts_code": code, "trade_date": date, "revision_id": "1", "open": raw_price, "high": raw_price, "low": raw_price, "close": raw_price, "available_at": _available(date)})
                adj_rows.append({"ts_code": code, "trade_date": date, "revision_id": "1", "adj_open": close, "adj_high": close, "adj_low": close, "adj_close": close, "adj_factor": factor, "available_at": _available(date)})
            if date in amount_dates:
                amount_rows.append({"ts_code": code, "trade_date": date, "revision_id": "1", "amount": amount, "unit": amount_unit, "available_at": _available(date)})
            if date in circ_dates:
                circ_rows.append({"ts_code": code, "trade_date": date, "revision_id": "1", "circ_mv": circ, "unit": circ_unit, "available_at": _available(date)})
    membership, st_rows, industry_rows, lifecycle = [], [], [], []
    for code in codes:
        membership.append({"ts_code": code, "revision_id": "1", "is_member": True, "effective_from": dates[0], "effective_to": None, "available_at": _available(dates[0])})
        st_rows.append({"ts_code": code, "revision_id": "1", "is_st": False, "effective_from": dates[0], "effective_to": None, "available_at": _available(dates[0])})
        industry_rows.append({"ts_code": code, "revision_id": "1", "industry_code": industry, "fact_status": industry_status, "effective_from": industry_from, "effective_to": None, "available_at": _available(industry_available)})
        lifecycle.append({"ts_code": code, "listed_on": dates[0], "delisted_on": None})
    return _bundle(dates, raw_rows, adj_rows, amount_rows, circ_rows, membership, st_rows, industry_rows, [], lifecycle, roster)


def hand_tables(factor: float) -> tuple[dict[str, list[dict]], list[int]]:
    panel, dates = hand_panel()
    raw_rows, adj_rows, amount_rows, circ_rows, roster = [], [], [], [], []
    for record in panel.itertuples(index=False):
        date = int(record.trade_date)
        raw_rows.append({"ts_code": record.ts_code, "trade_date": date, "revision_id": "1", "open": record.adj_open / factor, "high": record.adj_high / factor, "low": record.adj_low / factor, "close": record.adj_close / factor, "available_at": record.price_available_at})
        adj_rows.append({"ts_code": record.ts_code, "trade_date": date, "revision_id": "1", "adj_open": record.adj_open, "adj_high": record.adj_high, "adj_low": record.adj_low, "adj_close": record.adj_close, "adj_factor": factor, "available_at": record.price_available_at})
        amount_rows.append({"ts_code": record.ts_code, "trade_date": date, "revision_id": "1", "amount": record.amount_cny, "unit": "CNY", "available_at": record.amount_available_at})
        circ_rows.append({"ts_code": record.ts_code, "trade_date": date, "revision_id": "1", "circ_mv": record.circ_mv_cny, "unit": "CNY", "available_at": record.basic_available_at})
        roster.append({"trade_date": date, "ts_code": record.ts_code, "required_for_rank": True, "track_identity": True})
    codes = sorted(set(panel.ts_code))
    membership, st_rows, industry_rows, lifecycle = [], [], [], []
    for code in codes:
        membership.append({"ts_code": code, "revision_id": "1", "is_member": True, "effective_from": dates[0], "effective_to": None, "available_at": _available(dates[0])})
        st_rows.append({"ts_code": code, "revision_id": "1", "is_st": False, "effective_from": dates[0], "effective_to": None, "available_at": _available(dates[0])})
        industry_rows.append({"ts_code": code, "revision_id": "1", "industry_code": "SYNTHETIC_INDUSTRY", "effective_from": dates[0], "effective_to": None, "available_at": _available(dates[0])})
        lifecycle.append({"ts_code": code, "listed_on": dates[0], "delisted_on": None})
    return _bundle(dates, raw_rows, adj_rows, amount_rows, circ_rows, membership, st_rows, industry_rows, [], lifecycle, roster), dates


def _bundle(dates, raw_rows, adj_rows, amount_rows, circ_rows, membership, st_rows, industry_rows, halts, lifecycle, roster) -> dict[str, list[dict]]:
    return {
        "calendar": [{"trade_date": date, "market_index": "DECLARED_SYNTHETIC", "declaration_ref": "CASE", "signal_cutoff": _cutoff(date)} for date in dates],
        "prices_raw": raw_rows,
        "prices_adj": adj_rows,
        "amount": amount_rows,
        "circ_mv": circ_rows,
        "membership": membership,
        "st_status": st_rows,
        "industry": industry_rows,
        "halts": halts,
        "lifecycle": lifecycle,
        "roster": roster,
    }


def commit_tables(directory: Path, tables: dict[str, list[dict]], *, policy, contract: Contract, parent_hash: str, case_id: str, amount_unit: str = "CNY", circ_unit: str = "CNY", calendar_dates: list[int] | None = None, roster_codes: list[str] | None = None, mode: str = "SYNTHETIC", review_kind: str = "SYNTHETIC_DECLARATION", real_flag: bool = False) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    for row in tables["calendar"]:
        row["declaration_ref"] = case_id
    factors = policy.payload["units"]["amount_cny"]["factors"]
    hashes = {}
    for table_id, rows in tables.items():
        payload = json.dumps(rows, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        (directory / f"{table_id}.json").write_bytes(payload)
        hashes[table_id] = hashlib.sha256(payload).hexdigest()
    calendar_dates = list(calendar_dates) if calendar_dates is not None else [row["trade_date"] for row in tables["calendar"]]
    roster_codes = list(roster_codes) if roster_codes is not None else sorted({row["ts_code"] for row in tables["roster"]})

    def timed(canonical: str, unit: str | None = None) -> dict:
        field = {"canonical": canonical, "available_at_column": "available_at", "available_at_semantics": "EXPLICIT_TIMEZONE_TIMESTAMP"}
        if unit is not None:
            field["unit"] = unit
            field["scale_to_canonical"] = factors[unit]
        return field

    fields = {
        "calendar": {},
        "roster": {},
        "lifecycle": {},
        "prices_raw": {name: timed(name) for name in ["open", "high", "low", "close"]},
        "prices_adj": {name: timed(name) for name in ["adj_open", "adj_high", "adj_low", "adj_close", "adj_factor"]},
        "amount": {"amount": timed("amount_cny", amount_unit)},
        "circ_mv": {"circ_mv": timed("circ_mv_cny", circ_unit)},
        "membership": {"is_member": timed("is_member")},
        "st_status": {"is_st": timed("is_st")},
        "industry": {"industry_code": timed("industry_code")},
        "halts": {"halt_scope": timed("halt_scope")},
    }
    manifest = {
        "schema": "momentum_pullback.source_manifest.v1",
        "mode": mode,
        "case_id": case_id,
        "parent_contract_hash": parent_hash,
        "engineering_contract_hash": contract.hash,
        "snapshot_policy_hash": policy.file_hash,
        "source_definition_sha256": policy.document_hash,
        "parameter_status": "PROPOSED",
        "outcomes_enabled": False,
        "date_only_announcement_policy": policy.payload["date_only_announcement_policy"],
        "input_root": ".",
        "calendar_dates": calendar_dates,
        "roster_codes": roster_codes,
        "review_receipt_ref": "receipt.json",
        "tables": [{"table_id": table_id, "relative_path": f"{table_id}.json", "sha256": hashes[table_id], "primary_key": ["ts_code", "trade_date", "revision_id"], "fields": fields[table_id]} for table_id in tables],
    }
    manifest_path = directory / "source_manifest.json"
    manifest_bytes = json.dumps(manifest, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    manifest_path.write_bytes(manifest_bytes)
    receipt = {
        "schema": "momentum_pullback.source_review_receipt.v1",
        "mode": mode,
        "review_kind": review_kind,
        "source_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "snapshot_policy_hash": policy.file_hash,
        "case_id": case_id,
        "calendar_dates": calendar_dates,
        "roster_codes": roster_codes,
        "reviewed_at": "2026-10-16T12:00:00+08:00",
        "real_events_permitted": real_flag,
        "open_items": ["REAL_CERTIFICATION_NOT_CLAIMED"],
    }
    (directory / "receipt.json").write_bytes(json.dumps(receipt, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    return manifest_path

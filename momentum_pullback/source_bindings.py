"""Resolve a declared source package. A self-reported flag is not a REAL grant."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from momentum_pullback.contracts import ROOT, Contract, GateError, UniqueKeyLoader, file_hash, fingerprint
from momentum_pullback.data_adapter import roster_history_hash, unique_keys

POLICY_SCHEMA = "momentum_pullback.snapshot_policy.v1"
MANIFEST_SCHEMA = "momentum_pullback.source_manifest.v1"
RECEIPT_SCHEMA = "momentum_pullback.source_review_receipt.v1"
INDEX_SCHEMA = "momentum_pullback.approved_source_reviews.v1"
INDEX_RELATIVE = Path("momentum_pullback/evidence/approved_source_reviews.json")
REJECTED_TIME_COLUMNS = {"trade_date", "mtime", "file_mtime", "downloaded_at", "download_time", "retrieved_at", "reviewed_at", "ann_date"}
REJECTED_TIME_SEMANTICS = {"FILE_MTIME", "TRADE_DATE", "DOWNLOAD_TIME", "REVIEWED_AT", "DATE_ONLY"}
PRICE_TOLERANCE = 2e-5


@dataclass(frozen=True)
class SnapshotPolicy:
    payload: dict[str, Any]
    source_path: str
    file_hash: str

    @property
    def document_hash(self) -> str:
        return self.payload["documents"][0]["sha256"]


@dataclass(frozen=True)
class SourcePackage:
    manifest: dict[str, Any]
    receipt: dict[str, Any]
    policy_hash: str
    authority: str
    tables: dict[str, pd.DataFrame]
    input_root: Path


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _require_timestamp(value: Any) -> pd.Timestamp:
    try:
        parsed = pd.Timestamp(value)
        valid = parsed.tzinfo is not None and not pd.isna(parsed)
    except (TypeError, ValueError):
        valid = False
    if not valid:
        raise GateError("TIMEZONE_OR_TIMESTAMP_INVALID", value)
    return parsed.tz_convert("UTC")


def load_snapshot_policy(path: Path, *, root: Path = ROOT) -> SnapshotPolicy:
    """Bind the policy bytes and the definition document. Defaults cannot replace either."""
    raw = path.read_bytes()
    try:
        payload = yaml.load(raw.decode("utf-8"), Loader=UniqueKeyLoader)
    except (UnicodeDecodeError, yaml.YAMLError) as error:
        raise GateError("SNAPSHOT_POLICY_INVALID", str(path)) from error
    if not isinstance(payload, dict) or payload.get("schema") != POLICY_SCHEMA:
        raise GateError("SNAPSHOT_POLICY_INVALID", "schema")
    if payload.get("status") != "PROPOSED_ENGINEERING_SPEC" or payload.get("parameter_status") != "PROPOSED" or payload.get("outcomes_enabled") is not False or payload.get("freeze_timestamp") is not None:
        raise GateError("SNAPSHOT_POLICY_INVALID", "parameter_status")
    if payload.get("modes") != ["SYNTHETIC", "REAL"] or payload.get("real_review_index") != INDEX_RELATIVE.as_posix():
        raise GateError("SNAPSHOT_POLICY_INVALID", "authority")
    date_policy = payload.get("date_only_announcement_policy")
    if date_policy != {"id": "DATE_ONLY_ANNOUNCEMENT_ASIA_SHANGHAI_END_OF_DAY", "status": "PROPOSED_NOT_APPLIED"}:
        raise GateError("SNAPSHOT_POLICY_INVALID", "date_only_announcement_policy")
    scale = payload.get("price_scale")
    if not isinstance(scale, dict) or scale.get("formula") != "ADJUSTED_EQUALS_RAW_TIMES_STORED_FACTOR" or float(scale.get("rtol")) != PRICE_TOLERANCE or float(scale.get("atol")) != PRICE_TOLERANCE:
        raise GateError("SNAPSHOT_POLICY_INVALID", "price_scale")
    factors = {"CNY": 1, "THOUSAND_CNY": 1000, "TEN_THOUSAND_CNY": 10000}
    units = payload.get("units")
    if set(units or {}) != {"amount_cny", "circ_mv_cny"} or any(item.get("factors") != factors for item in units.values()):
        raise GateError("SNAPSHOT_POLICY_INVALID", "units")
    windows = payload.get("consumer_windows")
    expected_windows = {
        "calendar_prices_lifecycle": "FEATURE_ORIGIN_THROUGH_OUTPUT_END",
        "membership_st": "FEATURE_ORIGIN_THROUGH_OUTPUT_END",
        "industry_circ_mv": "OUTPUT_WINDOW_AND_REQUIRED_CROSS_SECTIONS",
        "amount_adv20": "NINETEEN_CERTIFIED_SESSIONS_BEFORE_OUTPUT_THROUGH_OUTPUT_END",
    }
    if windows != expected_windows or payload.get("revision", {}).get("selection") != "MAXIMUM_DECLARED_ORDER":
        raise GateError("SNAPSHOT_POLICY_INVALID", "windows_or_revision")
    if payload.get("lifecycle", {}).get("unsupported_code") != "UNSUPPORTED_SECURITY_LIFECYCLE":
        raise GateError("SNAPSHOT_POLICY_INVALID", "lifecycle")
    documents = payload.get("documents")
    if not isinstance(documents, list) or len(documents) != 1:
        raise GateError("SNAPSHOT_POLICY_INVALID", "documents")
    document = root / documents[0]["path"]
    if not document.is_file() or file_hash(document) != documents[0].get("sha256"):
        raise GateError("SNAPSHOT_POLICY_INVALID", documents[0].get("path"))
    return SnapshotPolicy(payload, str(path.resolve()), _sha256(raw))


def load_real_review_index(root: Path = ROOT) -> dict[str, Any]:
    """The trust index is the fixed project file. A package cannot supply a substitute."""
    path = root / INDEX_RELATIVE
    if path.resolve() != (root / INDEX_RELATIVE).resolve() or not path.is_file():
        raise GateError("REVIEW_RECEIPT_UNTRUSTED", "INDEX_MISSING")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise GateError("REVIEW_RECEIPT_UNTRUSTED", "INDEX_INVALID") from error
    if payload.get("schema") != INDEX_SCHEMA or not isinstance(payload.get("entries"), list):
        raise GateError("REVIEW_RECEIPT_UNTRUSTED", "INDEX_SCHEMA")
    return payload


def resolve_declared_path(input_root: Path, relative: str, allowed_roots: list[Path]) -> Path:
    """Reject absolute paths, parent segments, and links that resolve outside the allowed root."""
    raw = Path(relative)
    if raw.is_absolute() or ".." in raw.parts or raw.parts[:1] == ("/",):
        raise GateError("SOURCE_MANIFEST_INVALID", "PATH_ESCAPE")
    root = input_root.resolve()
    if not any(root.is_relative_to(allowed.resolve()) for allowed in allowed_roots):
        raise GateError("SOURCE_MANIFEST_INVALID", "INPUT_ROOT_UNTRUSTED")
    candidate = (root / raw).resolve()
    if not candidate.is_relative_to(root) or not candidate.is_file():
        raise GateError("SOURCE_MANIFEST_INVALID", "PATH_ESCAPE")
    return candidate


def convert_to_cny(value: Any, unit: Any, field: str, policy: SnapshotPolicy) -> float:
    """Scale only by the policy table. An unknown unit is not guessed."""
    factors = policy.payload["units"].get(field, {}).get("factors", {})
    if not isinstance(unit, str) or unit not in factors:
        raise GateError("SOURCE_UNIT_UNVERIFIED", {"field": field, "unit": unit})
    number = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if not np.isfinite(number):
        raise GateError("SOURCE_UNIT_UNVERIFIED", {"field": field, "unit": unit})
    return float(number) * int(factors[unit])


def require_real_bools(frame: pd.DataFrame, columns: list[str]) -> None:
    """Reject textual booleans. A string false is not a known negative fact."""
    for column in columns:
        if column not in frame or not frame[column].map(lambda value: isinstance(value, (bool, np.bool_))).all():
            raise GateError("BOOLEAN_STATE_INVALID", column)


def validate_time_mapping(column: str, semantics: str) -> None:
    """A date, file time, or review time cannot be used before a certified publication rule exists."""
    if column in REJECTED_TIME_COLUMNS or semantics in REJECTED_TIME_SEMANTICS or semantics != "EXPLICIT_TIMEZONE_TIMESTAMP":
        raise GateError("AVAILABLE_AT_SOURCE_REJECTED", {"column": column, "semantics": semantics})


def _order_token(value: Any, column: str, revision_column: str) -> Any:
    if column == revision_column:
        if isinstance(value, (bool, np.bool_)):
            raise GateError("SOURCE_MANIFEST_INVALID", "REVISION_TYPE")
        text = str(value)
        if text.isdigit():
            return int(text)
        return text
    return value


def select_asof(frame: pd.DataFrame, *, business_keys: list[str], revision_column: str, order_columns: list[str], cutoff: str, available_column: str) -> pd.DataFrame:
    """Choose the maximum declared order among revisions available at cutoff. Ties stay unresolved."""
    if revision_column not in frame or any(column not in frame for column in business_keys + order_columns + [available_column]):
        raise GateError("SOURCE_MANIFEST_INVALID", "ASOF_COLUMNS")
    unique_keys(frame, business_keys + [revision_column], "asof_source")
    cutoff_ts = _require_timestamp(cutoff)
    working = frame.copy()
    working["_available_ts"] = working[available_column].map(_require_timestamp)
    usable = working.loc[working["_available_ts"].le(cutoff_ts)].copy()
    if usable.empty:
        return usable.drop(columns=["_available_ts"]).reset_index(drop=True)
    revision_flags = [str(value).isdigit() for value in usable[revision_column].tolist()]
    if any(revision_flags) and not all(revision_flags):
        raise GateError("SOURCE_MANIFEST_INVALID", "REVISION_TYPE")
    chosen = []
    for _, group in usable.groupby(business_keys, sort=False, dropna=False):
        records = group.to_dict("records")
        tokens = []
        for record in records:
            values = []
            for column in order_columns:
                value = record[column]
                if column == available_column:
                    value = _require_timestamp(value)
                elif column == revision_column:
                    value = _order_token(value, column, revision_column)
                values.append(value)
            tokens.append(tuple(values))
        if len(set(tokens)) != len(tokens):
            sample = {key: records[0][key] for key in business_keys}
            raise GateError("AMBIGUOUS_ASOF_REVISION", sample)
        best = max(range(len(tokens)), key=lambda index: tokens[index])
        chosen.append(group.iloc[best].drop(labels=["_available_ts"]))
    return pd.DataFrame(chosen).reset_index(drop=True)


def require_supported_lifecycle(records: list[dict[str, Any]], *, feature_origin: int, output_end: int) -> None:
    """A fixed set listed at the feature origin is supported. Later listings and inside-window delistings are not."""
    for record in records:
        listed = record.get("listed_on")
        delisted = record.get("delisted_on")
        if not isinstance(listed, int) or listed > feature_origin or (delisted is not None and delisted <= output_end):
            raise GateError("UNSUPPORTED_SECURITY_LIFECYCLE", record.get("ts_code"))


def required_dates(rule: str, *, calendar: list[int], feature_origin: int, output_start: int, output_end: int) -> list[int]:
    """Return the dates a consumer must observe. Dates outside this list are not required."""
    ordered = [date for date in calendar if feature_origin <= date <= output_end]
    if rule == "FEATURE_ORIGIN_THROUGH_OUTPUT_END":
        return ordered
    if rule == "OUTPUT_WINDOW_AND_REQUIRED_CROSS_SECTIONS":
        return [date for date in ordered if date >= output_start]
    if rule == "NINETEEN_CERTIFIED_SESSIONS_BEFORE_OUTPUT_THROUGH_OUTPUT_END":
        output = [date for date in ordered if date >= output_start]
        prior = [date for date in ordered if date < output_start]
        return prior[-19:] + output
    if rule == "NOT_REQUIRED":
        return []
    raise GateError("SNAPSHOT_POLICY_INVALID", rule)


def source_history_prefix(prices: pd.DataFrame, events: pd.DataFrame, calendar: list[int], roster: pd.DataFrame, cutoff: int) -> str:
    """Hash consumed source rows. A future-only append keeps the prefix; a late past revision does not."""
    past_prices = prices.loc[prices["trade_date"].le(cutoff)].copy()
    unique_keys(past_prices, ["ts_code", "trade_date", "revision_id"], "prefix_prices")
    price_payload = json.loads(past_prices.sort_values(["trade_date", "ts_code", "revision_id"], kind="stable").to_json(orient="records", double_precision=15))
    if events.empty:
        event_payload = []
    else:
        available = events["available_at"].map(_require_timestamp)
        cutoff_ts = _require_timestamp(f"{cutoff // 10000:04d}-{(cutoff // 100) % 100:02d}-{cutoff % 100:02d}T23:59:59.999999+08:00")
        effective = pd.to_numeric(events["effective_from"], errors="coerce")
        keep = available.le(cutoff_ts) | effective.le(cutoff)
        kept = events.loc[keep].copy()
        event_payload = json.loads(kept.sort_values(["effective_from", "ts_code"], kind="stable").to_json(orient="records", double_precision=15))
    return fingerprint({
        "prices": price_payload,
        "events": event_payload,
        "calendar": [date for date in calendar if date <= cutoff],
        "roster": roster_history_hash(roster, cutoff),
    })


def _read_table(path: Path, declared_hash: str) -> pd.DataFrame:
    before = path.read_bytes()
    if _sha256(before) != declared_hash:
        raise GateError("SOURCE_MANIFEST_INVALID", path.name)
    if path.suffix == ".json":
        frame = pd.DataFrame(json.loads(before.decode("utf-8")))
    elif path.suffix == ".parquet":
        frame = pd.read_parquet(path)
    else:
        raise GateError("SOURCE_MANIFEST_INVALID", path.suffix)
    if path.read_bytes() != before:
        raise GateError("SNAPSHOT_CONTENT_CHANGED", path.name)
    return frame


def _check_receipt(receipt: dict[str, Any], manifest: dict[str, Any], manifest_hash: str, policy: SnapshotPolicy) -> str:
    if receipt.get("schema") != RECEIPT_SCHEMA or receipt.get("source_manifest_sha256") != manifest_hash:
        raise GateError("SOURCE_MANIFEST_INVALID", "RECEIPT_BINDING")
    if receipt.get("snapshot_policy_hash") != policy.file_hash:
        raise GateError("SOURCE_MANIFEST_INVALID", "POLICY_HASH")
    if receipt.get("mode") != manifest.get("mode"):
        raise GateError("SNAPSHOT_MODE_MISMATCH", {"manifest": manifest.get("mode"), "receipt": receipt.get("mode")})
    if receipt.get("real_events_permitted") is True:
        raise GateError("REVIEW_RECEIPT_UNTRUSTED", "REAL_EVENTS_FLAG_DOES_NOT_GRANT_AUTHORITY")
    _require_timestamp(receipt.get("reviewed_at"))
    if receipt.get("case_id") != manifest.get("case_id") or receipt.get("calendar_dates") != manifest.get("calendar_dates") or receipt.get("roster_codes") != manifest.get("roster_codes"):
        raise GateError("REVIEW_SCOPE_MISMATCH")
    mode = manifest.get("mode")
    kind = receipt.get("review_kind")
    if mode == "SYNTHETIC" and kind == "SYNTHETIC_DECLARATION":
        return "SYNTHETIC_DECLARATION"
    if mode == "REAL" and kind == "REAL_CERTIFIED":
        index = load_real_review_index()
        approved = [item for item in index["entries"] if item.get("receipt_sha256") == receipt.get("self_described_sha256")]
        if not approved:
            raise GateError("REVIEW_RECEIPT_UNTRUSTED", "NO_MATCHING_INDEX_ENTRY")
        raise GateError("REVIEW_RECEIPT_UNTRUSTED", "INDEX_ENTRY_NOT_RECHECKED")
    raise GateError("SNAPSHOT_MODE_MISMATCH", {"mode": mode, "review_kind": kind})


def load_source_package(manifest_path: Path, *, policy: SnapshotPolicy, contract: Contract, allowed_roots: list[Path]) -> SourcePackage:
    """Read only the declared files under a caller-limited root, then bind the declaration."""
    manifest_bytes = manifest_path.read_bytes()
    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise GateError("SOURCE_MANIFEST_INVALID", "JSON") from error
    if manifest.get("schema") != MANIFEST_SCHEMA or manifest.get("mode") not in {"SYNTHETIC", "REAL"}:
        raise GateError("SOURCE_MANIFEST_INVALID", "schema")
    if manifest.get("engineering_contract_hash") != contract.hash or manifest.get("snapshot_policy_hash") != policy.file_hash or manifest.get("source_definition_sha256") != policy.document_hash:
        raise GateError("SOURCE_MANIFEST_INVALID", "IDENTITY")
    if manifest.get("parameter_status") != "PROPOSED" or manifest.get("outcomes_enabled") is not False:
        raise GateError("SOURCE_MANIFEST_INVALID", "PARAMETER_STATUS")
    date_policy = manifest.get("date_only_announcement_policy")
    if date_policy != policy.payload["date_only_announcement_policy"]:
        raise GateError("SOURCE_MANIFEST_INVALID", "DATE_ONLY_POLICY")
    if not isinstance(manifest.get("parent_contract_hash"), str) or len(manifest["parent_contract_hash"]) != 64:
        raise GateError("SOURCE_MANIFEST_INVALID", "PARENT_CONTRACT")
    input_root = resolve_input_root(manifest_path, manifest.get("input_root"), allowed_roots)
    tables = {}
    for spec in manifest.get("tables", []):
        for field in spec.get("fields", {}).values():
            validate_time_mapping(field.get("available_at_column", ""), field.get("available_at_semantics", ""))
            canonical = field.get("canonical")
            if canonical in policy.payload["units"]:
                factors = policy.payload["units"][canonical]["factors"]
                if field.get("unit") not in factors:
                    raise GateError("SOURCE_UNIT_UNVERIFIED", {"field": canonical, "unit": field.get("unit")})
                if field.get("scale_to_canonical", factors[field["unit"]]) != factors[field["unit"]]:
                    raise GateError("SOURCE_MANIFEST_INVALID", "SCALE_MISMATCH")
        path = resolve_declared_path(input_root, spec["relative_path"], allowed_roots)
        tables[spec["table_id"]] = _read_table(path, spec["sha256"])
    receipt_path = resolve_declared_path(input_root, manifest["review_receipt_ref"], allowed_roots)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    authority = _check_receipt(receipt, manifest, _sha256(manifest_bytes), policy)
    if manifest_path.read_bytes() != manifest_bytes:
        raise GateError("SNAPSHOT_CONTENT_CHANGED", manifest_path.name)
    return SourcePackage(manifest, receipt, policy.file_hash, authority, tables, input_root)


def resolve_input_root(manifest_path: Path, declared: Any, allowed_roots: list[Path]) -> Path:
    if not isinstance(declared, str) or declared == "" or Path(declared).is_absolute() or ".." in Path(declared).parts:
        raise GateError("SOURCE_MANIFEST_INVALID", "INPUT_ROOT")
    candidate = (manifest_path.parent / declared).resolve()
    if not candidate.is_dir() or not any(candidate.is_relative_to(allowed.resolve()) for allowed in allowed_roots):
        raise GateError("SOURCE_MANIFEST_INVALID", "INPUT_ROOT_UNTRUSTED")
    return candidate

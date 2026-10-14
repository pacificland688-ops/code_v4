"""Strict local-only data validation. No de-duplication or market API fallback."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from momentum_pullback.contracts import GateError, fingerprint

KEYS = ["ts_code", "trade_date"]
PRICE_COLUMNS = ["open", "high", "low", "close"]


def unique_keys(frame: pd.DataFrame, keys: list[str], label: str) -> None:
    if any(key not in frame for key in keys) or frame[keys].isna().any().any():
        raise GateError("KEY_MISSING", label)
    duplicated = frame.duplicated(keys, keep=False)
    if duplicated.any():
        raise GateError("DUPLICATE_OR_CONFLICTING_KEYS", {"table": label, "rows": int(duplicated.sum()), "sample": frame.loc[duplicated, keys].head(5).to_dict("records")})


def validate_prices(frame: pd.DataFrame, columns: list[str], label: str) -> None:
    if frame.empty:
        raise GateError("EMPTY_PRICE_SCOPE", label)
    if any(column not in frame for column in columns):
        raise GateError("PRICE_COLUMNS_MISSING", label)
    prices = frame[columns].apply(pd.to_numeric, errors="coerce")
    invalid = (~np.isfinite(prices)).any(axis=1) | (prices <= 0).any(axis=1)
    if invalid.any():
        raise GateError("NONFINITE_OR_NONPOSITIVE_PRICE", {"table": label, "rows": int(invalid.sum())})
    op, high, low, close = (prices[column] for column in columns)
    tol = 1e-6 * prices.max(axis=1)
    invalid = (low > high + tol) | (op > high + tol) | (op < low - tol) | (close > high + tol) | (close < low - tol)
    if invalid.any():
        raise GateError("OHLC_RELATION_INVALID", {"table": label, "rows": int(invalid.sum())})


def validate_join(raw: pd.DataFrame, adjusted: pd.DataFrame) -> pd.DataFrame:
    """Do not merge until each side is unique; require exact business-key sets."""
    unique_keys(raw, KEYS, "prices_raw")
    unique_keys(adjusted, KEYS, "prices_adj")
    validate_prices(raw, PRICE_COLUMNS, "prices_raw")
    validate_prices(adjusted, [f"adj_{column}" for column in PRICE_COLUMNS], "prices_adj")
    if "adj_factor" not in adjusted:
        raise GateError("ADJUSTMENT_FACTOR_MISSING")
    factors = pd.to_numeric(adjusted["adj_factor"], errors="coerce")
    if (~np.isfinite(factors) | (factors <= 0)).any():
        raise GateError("ADJUSTMENT_FACTOR_INVALID", int((~np.isfinite(factors) | (factors <= 0)).sum()))
    left = set(map(tuple, raw[KEYS].to_numpy()))
    right = set(map(tuple, adjusted[KEYS].to_numpy()))
    if left != right:
        raise GateError("RAW_ADJUSTED_KEY_SET_MISMATCH", {"raw_only": len(left - right), "adj_only": len(right - left)})
    adj_columns = KEYS + [f"adj_{column}" for column in PRICE_COLUMNS] + ["adj_factor"]
    joined = raw.merge(adjusted[adj_columns], on=KEYS, how="inner", validate="one_to_one")
    for column in PRICE_COLUMNS:
        expected = joined[column].to_numpy(dtype=float) * joined["adj_factor"].to_numpy(dtype=float)
        if not np.allclose(expected, joined[f"adj_{column}"].to_numpy(dtype=float), rtol=2e-5, atol=2e-5):
            raise GateError("ADJUSTED_PRICE_SCALE_MISMATCH", column)
    return joined.sort_values(KEYS, kind="stable").reset_index(drop=True)


def checked_available(frame: pd.DataFrame, cutoff_column: str, available_column: str) -> pd.Series:
    cutoff = pd.to_datetime(frame[cutoff_column], utc=True, errors="coerce")
    available = pd.to_datetime(frame[available_column], utc=True, errors="coerce")
    return cutoff.notna() & available.notna() & available.le(cutoff)


def validate_normalized_panel(panel: pd.DataFrame, calendar: list[int]) -> None:
    """Validate the complete declared grid; missing facts remain explicit unknowns."""
    unique_keys(panel, KEYS, "normalized_observations")
    if panel.empty or not calendar or calendar != sorted(set(calendar)):
        raise GateError("CALENDAR_OR_INPUT_EMPTY")
    if any(type(date) is not int or len(str(date)) != 8 for date in calendar):
        raise GateError("CALENDAR_DATE_INVALID")
    if any(not isinstance(code, str) or not code for code in panel.ts_code):
        raise GateError("SECURITY_IDENTIFIER_INVALID")
    for column in ["membership_known", "is_member", "st_known", "is_st"]:
        if not panel[column].map(lambda value: isinstance(value, (bool, np.bool_))).all():
            raise GateError("BOOLEAN_STATE_INVALID", column)
    if not panel.price_status.isin(["TRADED", "VERIFIED_FULL_DAY_HALT", "UNKNOWN"]).all():
        raise GateError("PRICE_STATUS_INVALID")
    for code, stock in panel.groupby("ts_code", sort=True):
        if sorted(stock.trade_date.tolist()) != calendar:
            raise GateError("MARKET_GRID_INCOMPLETE", code)
    for column in [name for name in panel if name.endswith("_available_at")] + ["signal_cutoff"]:
        for value in panel[column].dropna():
            try:
                parsed = pd.Timestamp(value)
                valid = parsed.tzinfo is not None and not pd.isna(parsed)
            except (TypeError, ValueError):
                valid = False
            if not valid:
                raise GateError("TIMEZONE_OR_TIMESTAMP_INVALID", column)
    if panel.signal_cutoff.isna().any():
        raise GateError("SIGNAL_CUTOFF_MISSING")
    for prefix in ["membership", "st", "industry"]:
        starts = pd.to_numeric(panel[prefix + "_effective_from"], errors="coerce")
        ends = pd.to_numeric(panel[prefix + "_effective_to"], errors="coerce")
        for edge, parsed in [("from", starts), ("to", ends)]:
            populated = panel[prefix + "_effective_" + edge].notna()
            finite = parsed.loc[populated]
            if (~np.isfinite(finite) | finite.mod(1).ne(0)).any():
                raise GateError("EFFECTIVE_DATE_INVALID", prefix + "_" + edge)
            if pd.to_datetime(finite.astype("int64").astype(str), format="%Y%m%d", errors="coerce").isna().any():
                raise GateError("EFFECTIVE_DATE_INVALID", prefix + "_" + edge)
        if (starts.notna() & ends.notna() & starts.gt(ends)).any():
            raise GateError("EFFECTIVE_INTERVAL_INVALID", prefix)
    signal_dates = pd.to_datetime(panel.signal_cutoff, utc=True).dt.tz_convert("Asia/Shanghai").dt.strftime("%Y%m%d").astype(int)
    if not signal_dates.eq(panel.trade_date).all():
        raise GateError("SIGNAL_CUTOFF_DATE_MISMATCH")
    cutoffs = pd.to_datetime(panel.signal_cutoff, utc=True)
    if pd.DataFrame({"trade_date": panel.trade_date, "cutoff": cutoffs}).groupby("trade_date").cutoff.nunique().gt(1).any():
        raise GateError("CROSS_SECTION_CUTOFF_MISMATCH")
    traded = panel[panel.price_status.eq("TRADED")]
    if not traded.empty:
        validate_prices(traded, [f"adj_{name}" for name in PRICE_COLUMNS], "normalized_traded_prices")
    for column in ["amount_cny", "circ_mv_cny"]:
        populated = panel[column].notna()
        numeric = pd.to_numeric(panel.loc[populated, column], errors="coerce")
        invalid = ~np.isfinite(numeric) | (numeric < 0 if column == "amount_cny" else numeric <= 0)
        if invalid.any():
            raise GateError("NONFINITE_OR_INVALID_COVARIATE", column)


def frame_hash(frame: pd.DataFrame, *, cutoff: int | None = None) -> str:
    selected = frame if cutoff is None else frame.loc[frame["trade_date"].le(cutoff)]
    selected = selected.sort_values(KEYS, kind="stable")[sorted(selected.columns)]
    return fingerprint({"columns": list(selected.columns), "data": selected.to_json(orient="split", date_format="iso", index=False, double_precision=15)})


def input_history_hash(panel: pd.DataFrame, calendar: list[int], cutoff: int) -> str:
    return fingerprint({"observations": frame_hash(panel, cutoff=cutoff), "consumed_calendar": [date for date in calendar if date <= cutoff]})


def read_partition(path: Path, columns: list[str], start: int, end: int) -> pd.DataFrame:
    """Filter each explicitly selected file without directory glob fallbacks."""
    try:
        # Read the selected file itself: Hive directory inference can inject a
        # conflicting year/month type and must not change the source schema.
        frame = pq.ParquetFile(path).read(columns=columns).to_pandas()
        frame = frame[frame.trade_date.between(start, end)].copy()
    except Exception as error:
        raise GateError("PARQUET_READ_FAILED", {"path": str(path), "type": type(error).__name__}) from error
    return frame


def period_files(base: Path, start: int, end: int) -> list[Path]:
    """Only enumerate year/month partitions inside a declared audit period."""
    files = []
    for month in pd.period_range(str(start), str(end), freq="M"):
        directory = base / f"year={month.year}" / f"month={month.month}"
        files.extend(sorted(directory.glob("*.parquet")))
    return files


def local_audit_files(root: Path, start: int, end: int) -> list[Path]:
    base = root / "data/parquet"
    paths = period_files(base / "prices_raw", start, end) + period_files(base / "prices_adj", start, end)
    for label in ["index_weight", "industry_member", "daily_basic"]:
        paths.extend(sorted((base / label).glob(f"year={start // 10000}/*.parquet")))
    paths.extend(sorted((base / "trade_cal").glob("*.parquet")))
    return sorted(set(paths))


def audit_local_prices(root: Path, start: int, end: int) -> tuple[dict[str, Any], list[Path]]:
    base = root / "data/parquet"
    raw_files = period_files(base / "prices_raw", start, end)
    adjusted_files = period_files(base / "prices_adj", start, end)
    gates = []
    loaded = {}
    file_rows = []
    for label, paths, columns in [("prices_raw", raw_files, KEYS + PRICE_COLUMNS + ["vol", "amount"]), ("prices_adj", adjusted_files, KEYS + [f"adj_{column}" for column in PRICE_COLUMNS] + ["adj_factor"])]:
        try:
            if not paths:
                raise GateError("PRICE_PARTITIONS_MISSING", label)
            frames = []
            for path in paths:
                frame = read_partition(path, columns, start, end)
                frames.append(frame)
                file_rows.append({"table": label, "path": str(path.relative_to(root)), "selected_rows": len(frame)})
            loaded[label] = pd.concat(frames, ignore_index=True)
            unique_keys(loaded[label], KEYS, label)
            validate_prices(loaded[label], PRICE_COLUMNS if label == "prices_raw" else [f"adj_{column}" for column in PRICE_COLUMNS], label)
            gates.append({"gate": label + "_keys_ohlc", "status": "PASS", "rows": len(loaded[label])})
        except GateError as error:
            gates.append({"gate": label + "_keys_ohlc", "status": "FAIL", "reason": error.code, "details": error.details})
    if len(loaded) == 2:
        try:
            combined = validate_join(loaded["prices_raw"], loaded["prices_adj"])
            gates.append({"gate": "raw_adjusted_factor_join", "status": "PASS", "rows": len(combined)})
        except GateError as error:
            gates.append({"gate": "raw_adjusted_factor_join", "status": "FAIL", "reason": error.code, "details": error.details})
    factor_sample = []
    if "prices_adj" in loaded and "adj_factor" in loaded["prices_adj"]:
        values = pd.to_numeric(loaded["prices_adj"].adj_factor, errors="coerce")
        factor_sample = loaded["prices_adj"].loc[~np.isfinite(values) | values.le(0), KEYS].head(10).to_dict("records")
    required_bindings = {"index_weight": ["announced_at", "effective_from", "effective_to"], "industry_member": ["available_at", "effective_date"], "daily_basic": ["available_at"]}
    for label, fields in required_bindings.items():
        files = sorted((base / label).glob(f"year={start // 10000}/*.parquet"))
        schemas = [set(pq.ParquetFile(path).schema_arrow.names) for path in files]
        missing = [field for field in fields if not schemas or any(field not in schema for schema in schemas)]
        gates.append({"gate": label + "_publication_binding", "status": "FAIL" if missing else "UNVERIFIED", "reason": "PIT_SOURCE_BINDING_MISSING" if missing else "SOURCE_EVIDENCE_REVIEW_REQUIRED", "missing_fields": missing})
    evidence_files = []
    for label in required_bindings:
        evidence_files.extend(sorted((base / label).glob(f"year={start // 10000}/*.parquet")))
    calendar_paths = sorted((base / "trade_cal").glob("*.parquet"))
    gates.append({"gate": "calendar_and_historical_warmup_binding", "status": "UNVERIFIED", "reason": "COMPLETE_MARKET_CALENDAR_AND_PIT_HISTORY_NOT_CERTIFIED", "calendar_files": [str(path.relative_to(root)) for path in calendar_paths]})
    return {"status": "DATA_BLOCKED", "audit_scope": "OUTPUT_PRICE_CACHE_AUDIT_WARMUP_AND_PIT_NOT_CERTIFIED", "output_start": start, "output_end": end, "gates": gates, "file_rows": file_rows, "invalid_factor_sample": factor_sample, "real_event_generation": "NOT_PERMITTED", "network_requests": 0}, raw_files + adjusted_files + evidence_files + calendar_paths

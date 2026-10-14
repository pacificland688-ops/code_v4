"""Inspect local Parquet metadata and one bounded sample without network access."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pyarrow.parquet as pq


ROOT = Path(__file__).resolve().parents[1]
TABLES = (
    "prices_raw", "prices_adj", "daily_basic", "adj_factor", "index_weight",
    "index_daily", "limit_status", "suspend_status", "stock_status",
    "namechange", "industry_member", "trade_cal",
)


def inspect_table(name: str) -> dict:
    """Read file footers only; date extrema are not a coverage certificate."""
    directory = ROOT / "data" / "parquet" / name
    files = sorted(directory.rglob("*.parquet"))
    years: Counter[str] = Counter()
    partitions: Counter[str] = Counter()
    schemas: set[tuple[str, ...]] = set()
    dates: list[int] = []
    total_rows = 0
    missing_statistics = 0
    for path in files:
        parquet = pq.ParquetFile(path)
        total_rows += parquet.metadata.num_rows
        schemas.add(tuple(parquet.schema_arrow.names))
        relative = path.relative_to(directory)
        partitions[str(relative.parent)] += 1
        for part in relative.parts:
            if part.startswith("year="):
                years[part] += 1
        if "trade_date" not in parquet.schema.names:
            continue
        column = parquet.schema.names.index("trade_date")
        for group in range(parquet.metadata.num_row_groups):
            stats = parquet.metadata.row_group(group).column(column).statistics
            if stats is None or not stats.has_min_max:
                missing_statistics += 1
                continue
            dates.extend((int(stats.min), int(stats.max)))
    return {
        "table": name,
        "parquet_files": len(files),
        "physical_rows_from_footers": total_rows,
        "files_by_year": dict(sorted(years.items())),
        "schemas": [list(schema) for schema in sorted(schemas)],
        "footer_trade_date_min": min(dates) if dates else None,
        "footer_trade_date_max": max(dates) if dates else None,
        "row_groups_without_date_statistics": missing_statistics,
        "partitions_with_multiple_files": {
            partition: count for partition, count in sorted(partitions.items())
            if count > 1
        },
        "coverage_verified": False,
        "note": "Physical file counts and extrema do not establish PIT coverage or unique rows.",
    }


def bounded_sample() -> dict:
    """Check business keys in the January 2026 raw-price partition only."""
    path = ROOT / "data/parquet/prices_raw/year=2026/month=1/cache.parquet"
    if not path.exists():
        return {"status": "SAMPLE_FILE_MISSING", "relative_path": str(path.relative_to(ROOT))}
    table = pq.read_table(
        path,
        columns=["ts_code", "trade_date"],
        filters=[("trade_date", ">=", 20260101), ("trade_date", "<=", 20260131)],
    )
    keys = list(zip(table["ts_code"].to_pylist(), table["trade_date"].to_pylist()))
    return {
        "status": "OBSERVED",
        "relative_path": str(path.relative_to(ROOT)),
        "start_date": 20260101,
        "end_date": 20260131,
        "rows": len(keys),
        "stocks": len({code for code, _ in keys}),
        "trade_dates": len({date for _, date in keys}),
        "duplicate_business_keys": len(keys) - len(set(keys)),
        "does_not_verify": ["daily_universe_completeness", "suspension_semantics", "PIT_membership"],
    }


def main() -> None:
    tables = [inspect_table(name) for name in TABLES]
    report = {
        "schema": "martin_luk_pullback.local_inventory.v1",
        "observed_at": datetime.now(timezone(timedelta(hours=8))).isoformat(),
        "workspace": str(ROOT),
        "method": "Parquet footers plus one date-filtered two-column monthly sample",
        "network_requests": 0,
        "is_data_snapshot": False,
        "data_readiness": "NOT_CERTIFIED",
        "tables": tables,
        "bounded_sample": bounded_sample(),
        "top_level_parquet_directories": sorted(
            path.name for path in (ROOT / "data/parquet").iterdir() if path.is_dir()
        ),
    }
    output = ROOT / "momentum_pullback/evidence/local_data_inventory.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(output),
        "tables_checked": len(tables),
        "price_data_latest": next(row["footer_trade_date_max"] for row in tables if row["table"] == "prices_raw"),
        "bounded_sample": report["bounded_sample"],
        "data_readiness": report["data_readiness"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()

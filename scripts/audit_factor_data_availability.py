#!/usr/bin/env python
"""
Factor Data Availability Audit — cross-reference factor universe requirements
against actual parquet data on disk.

Produces per-factor diagnosis with explicit status:
  OK, SOURCE_MISSING, FIELD_MISSING, INSUFFICIENT_DATE_COVERAGE,
  INSUFFICIENT_STOCK_COVERAGE, FORMULA_NOT_IMPLEMENTED

Output: CSV in outputs/audits/<timestamp>/factor_data_availability_audit.csv

Usage:
  python -X utf8 scripts/audit_factor_data_availability.py
  python -X utf8 scripts/audit_factor_data_availability.py --universe configs/factors_alpha_v4_universe.yaml
  python -X utf8 scripts/audit_factor_data_availability.py --factors ocf_to_profit_cs ocf_to_mktcap_cs
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------------------
# Source name → parquet path mapping
# ---------------------------------------------------------------------------
SOURCE_PATH_MAP = {
    "fina_indicator": "data/parquet/fina_indicator",
    "income": "data/parquet/income",
    "daily_basic": "data/parquet/daily_basic",
    "prices_adj": "data/parquet/prices_adj",
    "prices_raw": "data/parquet/prices_raw",
    "cashflow": "data/parquet/cashflow",
    "balancesheet": "data/parquet/balancesheet",
    "industry_pit": "data/parquet/industry_pit",
    "stock_status": "data/parquet/stock_status",
}

# Alternative: names used in build script but not separate parquet dirs
SOURCE_ALIASES = {
    "prices": "prices_adj",
}


def _resolve_source(source_name: str) -> str:
    """Resolve aliases to canonical source names."""
    return SOURCE_ALIASES.get(source_name, source_name)


# ---------------------------------------------------------------------------
# Source & field checks
# ---------------------------------------------------------------------------

def _check_source_exists(source_name: str) -> dict:
    """Check if a data source parquet directory exists with files."""
    canonical = _resolve_source(source_name)
    rel_path = SOURCE_PATH_MAP.get(canonical)
    if rel_path is None:
        return {"source": source_name, "canonical": canonical,
                "exists": False, "path": None, "file_count": 0,
                "reason": f"unknown source: {canonical}"}

    abs_path = ROOT / rel_path
    if not abs_path.exists() or not abs_path.is_dir():
        return {"source": source_name, "canonical": canonical,
                "exists": False, "path": str(abs_path), "file_count": 0,
                "reason": "directory does not exist"}

    files = list(abs_path.rglob("*.parquet"))
    return {"source": source_name, "canonical": canonical,
            "exists": True, "path": str(abs_path),
            "file_count": len(files),
            "reason": ""}


def _check_available_fields(source_name: str) -> Set[str]:
    """Read schema from first parquet file in source directory."""
    canonical = _resolve_source(source_name)
    rel_path = SOURCE_PATH_MAP.get(canonical)
    if rel_path is None:
        return set()

    abs_path = ROOT / rel_path
    if not abs_path.exists():
        return set()

    files = list(abs_path.rglob("*.parquet"))
    if not files:
        return set()

    # Try first few files in case first is empty/corrupt
    for f in files[:5]:
        try:
            df = pd.read_parquet(f)
            return {str(c).strip().lower() for c in df.columns}
        except Exception:
            continue
    return set()


def _check_date_coverage(source_name: str) -> dict:
    """Get approximate date range and row count from source."""
    canonical = _resolve_source(source_name)
    rel_path = SOURCE_PATH_MAP.get(canonical)
    if rel_path is None:
        return {"date_start": None, "date_end": None,
                "row_count": 0, "stock_count": 0}

    abs_path = ROOT / rel_path
    if not abs_path.exists():
        return {"date_start": None, "date_end": None,
                "row_count": 0, "stock_count": 0}

    files = list(abs_path.rglob("*.parquet"))
    if not files:
        return {"date_start": None, "date_end": None,
                "row_count": 0, "stock_count": 0}

    # Scan metadata only (fast) for approximate coverage
    date_col = _guess_date_column(canonical)
    min_date = None
    max_date = None
    total_rows = 0
    stocks: Set[str] = set()

    for f in files:  # Full scan all parquet files for accurate stats
        try:
            df = pd.read_parquet(f, columns=_columns_to_read(canonical, date_col))
            total_rows += len(df)
            if "ts_code" in df.columns:
                stocks.update(df["ts_code"].astype(str).dropna().unique())
            if date_col and date_col in df.columns:
                col_vals = pd.to_numeric(df[date_col], errors="coerce").dropna()
                if len(col_vals) > 0:
                    fmin = int(col_vals.min())
                    fmax = int(col_vals.max())
                    min_date = fmin if min_date is None else min(min_date, fmin)
                    max_date = fmax if max_date is None else max(max_date, fmax)
        except Exception:
            continue

    return {
        "date_start": min_date,
        "date_end": max_date,
        "row_count": total_rows,
        "stock_count": len(stocks),
    }


def _guess_date_column(source_name: str) -> Optional[str]:
    """Guess the date column for a source."""
    if source_name in ("daily_basic", "prices_adj", "prices_raw"):
        return "trade_date"
    return "end_date"  # financial statements


def _columns_to_read(source_name: str, date_col: Optional[str]) -> List[str]:
    """Minimal columns to read for date/stock coverage check."""
    cols = []
    if date_col:
        cols.append(date_col)
    cols.append("ts_code")
    return cols


# ---------------------------------------------------------------------------
# Formula implementation check
# ---------------------------------------------------------------------------

def _check_formula_implemented(factor_name: str) -> dict:
    """Check if the build script has real computation or just 'pass'."""
    build_path = ROOT / "scripts" / "build_alpha_factors_v4.py"
    if not build_path.exists():
        return {"implemented": False, "reason": "build script not found"}

    source = build_path.read_text(encoding="utf-8")

    # Find the factor's elif block
    fname_escaped = factor_name.replace("(", r"\(").replace(")", r"\)")
    import re

    # Pattern: elif fname == "xxx": or elif fname in (...):
    pattern = rf'elif\s+fname\s*(?:==|in)\s*.*?{fname_escaped}.*?:'
    match = re.search(pattern, source)
    if not match:
        # Also try multi-factor pattern: elif fname in ("a", "b", "xxx"):
        multi_pattern = rf'elif\s+fname\s+in\s+\([^)]*{fname_escaped}[^)]*\)'
        match = re.search(multi_pattern, source)
    if not match:
        return {"implemented": False, "reason": "no elif branch found"}

    # Get the block content (up to next elif or else or except)
    start = match.end()
    # Find next elif/else at same indent level
    rest = source[start:]
    # Simple heuristic: look for `pass\n` as the first substantive line
    block_end = len(rest)
    for m2 in re.finditer(r'\n\s{8,12}elif\s+fname\s', rest):
        block_end = m2.start()
        break

    block = rest[:block_end]
    # Strip comments and whitespace
    lines = [l.strip() for l in block.split("\n")
             if l.strip() and not l.strip().startswith("#")]
    non_empty = [l for l in lines if l]

    if not non_empty:
        return {"implemented": False, "reason": "empty block"}
    if any(l == "pass" for l in non_empty):
        return {"implemented": False, "reason": "pass stub"}
    if any(l.startswith("pass  #") for l in non_empty):
        return {"implemented": False, "reason": "pass stub (commented)"}

    return {"implemented": True, "reason": f"has real code ({len(non_empty)} lines)"}


# ---------------------------------------------------------------------------
# Main audit
# ---------------------------------------------------------------------------

def _load_universe_factors(universe_path: Path) -> List[dict]:
    """Load factor specs from universe YAML."""
    if not universe_path.exists():
        print(f"ERROR: Universe config not found: {universe_path}")
        return []
    cfg = yaml.safe_load(universe_path.read_text(encoding="utf-8"))
    return cfg.get("factors", [])


def audit_factor(factor_spec: dict) -> dict:
    """Audit a single factor's data availability.

    Now includes per-source detail columns with full-scan statistics.
    """
    fname = factor_spec["name"]
    required_sources = factor_spec.get("data_sources", [])
    required_fields_map = factor_spec.get("required_fields", {})

    result = {
        "factor_name": fname,
        "category": factor_spec.get("category", ""),
        "priority": factor_spec.get("priority", ""),
        "type": factor_spec.get("type", ""),
        "required_sources": "|".join(required_sources),
        "required_fields": str(required_fields_map),
        "source_exists": "",
        "available_fields": "",
        "missing_fields": "",
        "date_start": None,
        "date_end": None,
        "row_count": 0,
        "stock_count": 0,
        "diagnosis_status": "OK",
        "diagnosis_reason": "",
        # Per-source details (new)
        "source_details": "",
    }

    # Check formula implementation
    formula_check = _check_formula_implemented(fname)
    if not formula_check["implemented"]:
        result["diagnosis_status"] = "FORMULA_NOT_IMPLEMENTED"
        result["diagnosis_reason"] = formula_check["reason"]

    # Check data sources
    source_statuses = []
    source_details_list = []
    available_fields_all: Set[str] = set()
    missing_fields_all: List[str] = []
    date_starts = []
    date_ends = []
    total_rows = 0
    total_stocks = 0

    for src in required_sources:
        check = _check_source_exists(src)
        source_statuses.append(f"{src}:{'OK' if check['exists'] else 'MISSING'}")

        src_detail = {
            "source_name": src,
            "source_exists": check["exists"],
            "source_row_count": 0,
            "source_stock_count": 0,
            "source_date_start": None,
            "source_date_end": None,
        }

        if check["exists"]:
            fields = _check_available_fields(src)
            available_fields_all.update(fields)

            req_fields = required_fields_map.get(src, [])
            for rf in req_fields:
                field_exists = rf in fields
                src_detail[f"field_{rf}_exists"] = field_exists
                if not field_exists:
                    missing_fields_all.append(f"{src}.{rf}")

            coverage = _check_date_coverage(src)
            src_detail["source_row_count"] = coverage["row_count"]
            src_detail["source_stock_count"] = coverage["stock_count"]
            src_detail["source_date_start"] = coverage["date_start"]
            src_detail["source_date_end"] = coverage["date_end"]

            if coverage["date_start"]:
                date_starts.append(coverage["date_start"])
            if coverage["date_end"]:
                date_ends.append(coverage["date_end"])
            total_rows += coverage["row_count"]
            total_stocks = max(total_stocks, coverage["stock_count"])
        else:
            # Source missing — all its required fields are missing
            req_fields = required_fields_map.get(src, [])
            for rf in req_fields:
                src_detail[f"field_{rf}_exists"] = False
                missing_fields_all.append(f"{src}.{rf}")

        source_details_list.append(src_detail)

    result["source_exists"] = "|".join(source_statuses)
    result["available_fields"] = "|".join(sorted(available_fields_all)) if available_fields_all else ""
    result["missing_fields"] = "|".join(missing_fields_all) if missing_fields_all else ""
    result["date_start"] = min(date_starts) if date_starts else None
    result["date_end"] = max(date_ends) if date_ends else None
    result["row_count"] = total_rows
    result["stock_count"] = total_stocks
    result["source_details"] = json.dumps(source_details_list) if source_details_list else ""

    # Determine diagnosis if not already FORMULA_NOT_IMPLEMENTED
    if result["diagnosis_status"] != "FORMULA_NOT_IMPLEMENTED":
        source_missing = [s.split(":")[0] for s in source_statuses if ":MISSING" in s]
        if source_missing:
            result["diagnosis_status"] = "SOURCE_MISSING"
            result["diagnosis_reason"] = f"missing sources: {', '.join(source_missing)}"
        elif missing_fields_all:
            result["diagnosis_status"] = "FIELD_MISSING"
            result["diagnosis_reason"] = f"missing fields: {', '.join(missing_fields_all[:5])}"
        elif not source_statuses:
            result["diagnosis_status"] = "SOURCE_MISSING"
            result["diagnosis_reason"] = "no data sources specified"
        elif result["row_count"] == 0:
            result["diagnosis_status"] = "INSUFFICIENT_DATE_COVERAGE"
            result["diagnosis_reason"] = "no data rows found in any source"

    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit factor data availability against parquet data on disk"
    )
    parser.add_argument(
        "--universe", default="configs/factors_alpha_v4_universe.yaml",
        help="Path to factor universe YAML"
    )
    parser.add_argument(
        "--factors", nargs="+",
        help="Only audit specific factors (by name)"
    )
    parser.add_argument(
        "--output-dir",
        help="Override output directory (default: outputs/audits/<timestamp>)"
    )
    parser.add_argument(
        "--csv-only", action="store_true",
        help="Output CSV only, no console report"
    )
    args = parser.parse_args()

    universe_path = ROOT / args.universe
    factors = _load_universe_factors(universe_path)
    if not factors:
        print("ERROR: No factors found in universe config")
        return 1

    if args.factors:
        factors = [f for f in factors if f["name"] in args.factors]
        if not factors:
            print(f"ERROR: No matching factors found for: {args.factors}")
            return 1

    print(f"Auditing {len(factors)} factors from {args.universe}...")
    print()

    # Audit all factors
    results = []
    for i, spec in enumerate(factors):
        fname = spec["name"]
        print(f"[{i+1}/{len(factors)}] {fname}...", end=" ", flush=True)
        result = audit_factor(spec)
        results.append(result)
        status = result["diagnosis_status"]
        reason = result["diagnosis_reason"] or "-"
        print(f"{status} ({reason})")

    # Build DataFrame
    columns = [
        "factor_name", "category", "priority", "type",
        "required_sources", "required_fields",
        "source_exists", "available_fields", "missing_fields",
        "date_start", "date_end", "row_count", "stock_count",
        "source_details",
        "diagnosis_status", "diagnosis_reason",
    ]
    df = pd.DataFrame(results)
    for col in columns:
        if col not in df.columns:
            df[col] = ""
    df = df[columns]

    # Output directory
    if args.output_dir:
        out_dir = Path(args.output_dir)
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir = ROOT / "outputs" / "audits" / ts
    out_dir.mkdir(parents=True, exist_ok=True)

    csv_path = out_dir / "factor_data_availability_audit.csv"
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"\nAudit saved: {csv_path}")

    if not args.csv_only:
        # Summary
        status_counts = df["diagnosis_status"].value_counts()
        print(f"\n=== Audit Summary ===")
        print(f"Total factors: {len(df)}")
        for status in ["OK", "SOURCE_MISSING", "FIELD_MISSING",
                        "INSUFFICIENT_DATE_COVERAGE",
                        "INSUFFICIENT_STOCK_COVERAGE",
                        "FORMULA_NOT_IMPLEMENTED"]:
            count = int(status_counts.get(status, 0))
            if count > 0:
                names = df[df["diagnosis_status"] == status]["factor_name"].tolist()
                print(f"  {status}: {count} — {', '.join(names)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

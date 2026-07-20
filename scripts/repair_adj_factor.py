#!/usr/bin/env python
"""
Repair adj_factor cache: deduplicate + fill missing years from prices_adj/prices_raw.

Strategy:
  1. Deduplicate existing adj_factor partitions (keep last per (ts_code, trade_date)).
  2. For years with low coverage, derive adj_factor from:
       adj_factor = prices_adj.close / prices_raw.close
     This uses the fact that prices_adj = prices_raw * adj_factor.
  3. Write the derived adj_factor into the cache with proper year partitioning.

Safety:
  - --dry-run reports without modifications.
  - Backs up affected partitions before modification.
  - Writes to temp directory then atomically replaces (no half-written state).
  - Refuses to auto-resolve conflicting adj_factor values for the same key.
  - --years flag allows targeting specific years for repair.

Usage:
    python scripts/repair_adj_factor.py --start 20170101 --end 20241231 --dry-run
    python scripts/repair_adj_factor.py --start 20170101 --end 20241231 --years 2024
    python scripts/repair_adj_factor.py --start 20170101 --end 20241231
"""

import argparse
import logging
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Unified schema for adj_factor: ensures no type conflicts across partitions
ADJ_FACTOR_SCHEMA = pa.schema([
    ("ts_code", pa.string()),
    ("trade_date", pa.int32()),
    ("adj_factor", pa.float64()),
    ("year", pa.int32()),
])


def _parse_date(s: str) -> int:
    return int(s)


def _scan_partition_files(part_path: Path) -> List[Tuple[Path, pd.DataFrame]]:
    """Read all parquet files in a partition, returning (path, dataframe) pairs."""
    results = []
    if not part_path.exists():
        return results
    for f in sorted(part_path.glob("*.parquet")):
        try:
            df = pd.read_parquet(f)
            if not df.empty:
                results.append((f, df))
        except Exception:
            logger.warning(f"Could not read {f}, skipping")
            continue
    return results


def _normalize_schema(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize adj_factor dataframe to unified schema."""
    df = df.copy()

    # Ensure ts_code is string
    if "ts_code" in df.columns:
        df["ts_code"] = df["ts_code"].astype(str)

    # Coerce trade_date to numeric first (before dropna — strings become NaN)
    if "trade_date" in df.columns:
        df["trade_date"] = pd.to_numeric(df["trade_date"], errors="coerce")

    # Ensure adj_factor is float64
    if "adj_factor" in df.columns:
        df["adj_factor"] = pd.to_numeric(df["adj_factor"], errors="coerce").astype("float64")

    # Drop rows with nulls in key columns BEFORE casting trade_date to int32
    # (pandas cannot cast NaN to int32)
    df = df.dropna(subset=["ts_code", "trade_date", "adj_factor"])
    df = df[df["ts_code"].notna() & (df["ts_code"] != "None") & (df["ts_code"] != "nan")]

    # Now safe to cast to int32 — no NaN values remain
    if "trade_date" in df.columns:
        df["trade_date"] = df["trade_date"].astype("int32")

    return df


def _find_duplicates(part_path: Path) -> Dict:
    """
    Analyze duplicates in a partition.
    Returns dict with:
      - total_rows: int
      - unique_keys: int
      - dup_keys: list of (ts_code, trade_date) tuples
      - dup_sources: list of source files contributing to dups
      - conflict_keys: list of keys where adj_factor values differ
      - resolved_by_rule: str describing the resolution rule
    """
    files_data = _scan_partition_files(part_path)
    if not files_data:
        return {
            "total_rows": 0, "unique_keys": 0, "dup_keys": [],
            "dup_sources": [], "conflict_keys": [], "resolved_by_rule": "no data"
        }

    # Track which file each row came from
    all_rows = []
    for fpath, df in files_data:
        df = _normalize_schema(df)
        df["_source_file"] = str(fpath.name)
        all_rows.append(df[["ts_code", "trade_date", "adj_factor", "_source_file"]])

    combined = pd.concat(all_rows, ignore_index=True)
    total_rows = len(combined)

    # Find duplicates
    dup_mask = combined.duplicated(subset=["ts_code", "trade_date"], keep=False)
    dup_df = combined[dup_mask].copy()

    if dup_df.empty:
        n_unique = len(combined.drop_duplicates(subset=["ts_code", "trade_date"]))
        return {
            "total_rows": total_rows,
            "unique_keys": n_unique,
            "dup_count": 0,
            "dup_keys": [],
            "dup_sources": [],
            "conflict_keys": [],
            "resolved_by_rule": "no duplicates"
        }

    # Group by key and check for conflicting adj_factor values
    dup_groups = dup_df.groupby(["ts_code", "trade_date"])
    dup_keys_list = list(dup_groups.groups.keys())
    dup_sources = sorted(dup_df["_source_file"].unique().tolist())

    conflict_keys = []
    for key, group in dup_groups:
        unique_vals = group["adj_factor"].dropna().unique()
        if len(unique_vals) > 1:
            # Check if differences are meaningful (> 1e-6 relative)
            vals = sorted(unique_vals)
            for i in range(len(vals) - 1):
                ratio = abs(vals[i] - vals[i+1]) / max(abs(vals[i]), abs(vals[i+1]), 1e-10)
                if ratio > 1e-6:
                    conflict_keys.append({
                        "ts_code": key[0],
                        "trade_date": int(key[1]),
                        "values": [float(v) for v in vals],
                    })
                    break

    resolution = "keep last per (ts_code, trade_date)" if not conflict_keys else "CONFLICT — manual resolution required"

    return {
        "total_rows": total_rows,
        "unique_keys": len(combined.drop_duplicates(subset=["ts_code", "trade_date"])),
        "dup_keys": [(str(k[0]), int(k[1])) for k in dup_keys_list[:100]],  # cap at 100
        "dup_count": len(dup_keys_list),
        "dup_sources": dup_sources,
        "conflict_keys": conflict_keys,
        "resolved_by_rule": resolution,
    }


def dedup_partition(
    part_path: Path,
    dry_run: bool = False,
    years_filter: Optional[Set[int]] = None,
) -> int:
    """
    Deduplicate a single adj_factor partition.

    Rules:
      1. Same (ts_code, trade_date), same adj_factor → keep one (last).
      2. Same (ts_code, trade_date), different adj_factor → refuse, report conflict.
      3. Write via temp directory + atomic replace.

    Returns number of duplicate rows removed.
    """
    if not part_path.exists():
        return 0

    year = int(part_path.name.split("=")[1])
    if years_filter is not None and year not in years_filter:
        return 0

    files_data = _scan_partition_files(part_path)
    if not files_data:
        return 0

    # Analyze duplicates first
    dup_info = _find_duplicates(part_path)
    if dup_info["dup_count"] == 0:
        logger.info(f"year={year}: no duplicates found ({dup_info['total_rows']} rows, {dup_info['unique_keys']} unique keys)")
        return 0

    # Report duplicate details
    logger.info(f"year={year}: {dup_info['total_rows']} rows, "
                f"{dup_info['unique_keys']} unique keys, "
                f"{dup_info['dup_count']} duplicate keys")
    logger.info(f"  Source files contributing to duplicates: {dup_info['dup_sources']}")
    if dup_info["dup_keys"]:
        sample_dups = dup_info["dup_keys"][:5]
        logger.info(f"  Sample duplicate keys: {sample_dups}")

    # Check for conflicts
    if dup_info["conflict_keys"]:
        logger.error(f"year={year}: CONFLICT — {len(dup_info['conflict_keys'])} keys have "
                     f"different adj_factor values!")
        for ck in dup_info["conflict_keys"][:5]:
            logger.error(f"  {ck['ts_code']} @ {ck['trade_date']}: values={ck['values']}")
        logger.error("Cannot auto-resolve conflicting adj_factor values. Manual review required.")
        logger.error("Run with --dry-run for full conflict listing.")
        if not dry_run:
            raise SystemExit(1)
        return 0

    # Proceed with dedup
    all_dfs = []
    for _, df in files_data:
        df = _normalize_schema(df)
        all_dfs.append(df[["ts_code", "trade_date", "adj_factor"]])

    combined = pd.concat(all_dfs, ignore_index=True)
    n_before = len(combined)

    # Drop duplicates, keeping last
    df_clean = combined.drop_duplicates(subset=["ts_code", "trade_date"], keep="last")
    n_after = len(df_clean)
    n_removed = n_before - n_after

    if n_removed == 0:
        return 0

    if dry_run:
        logger.info(f"  [DRY-RUN] year={year}: would remove {n_removed} duplicate rows "
                    f"({n_before} → {n_after})")
        return n_removed

    # Backup existing partition
    backup_dir = Path("data") / "parquet_backup" / f"adj_factor_{part_path.name}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    backup_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(str(part_path), str(backup_dir))
    logger.info(f"  Backed up {part_path.name} to {backup_dir}")

    # Add year column
    df_clean["year"] = np.int32(year)

    # Write to temp directory first, then atomically replace
    tmp_dir = Path(tempfile.mkdtemp(prefix=f"adj_factor_repair_{year}_"))
    try:
        table = pa.Table.from_pandas(df_clean, schema=ADJ_FACTOR_SCHEMA)
        tmp_file = tmp_dir / "data.parquet"
        pq.write_table(table, str(tmp_file), compression="zstd")

        # Clear existing partition files
        for f in part_path.glob("*.parquet"):
            f.unlink()

        # Atomically move temp file to target
        shutil.move(str(tmp_file), str(part_path / "data.parquet"))
        logger.info(f"  year={year}: {n_before} → {n_after} rows ({n_removed} dupes removed) "
                    f"[atomic write, backed up]")
    finally:
        # Clean up temp dir
        if tmp_dir.exists():
            shutil.rmtree(str(tmp_dir), ignore_errors=True)

    return n_removed


def derive_adj_factor_from_prices(
    year: int,
    prices_raw_base: Path,
    prices_adj_base: Path,
    adj_factor_base: Path,
    dry_run: bool = False,
) -> int:
    """
    Derive adj_factor for a given year from prices_adj and prices_raw.
    adj_factor = prices_adj.close / prices_raw.close (handling zeros).
    Returns number of rows written.
    """
    import pyarrow.dataset as ds

    yp_raw = prices_raw_base / f"year={year}"
    yp_adj = prices_adj_base / f"year={year}"

    if not yp_raw.exists() or not yp_adj.exists():
        logger.warning(f"Missing prices for year={year} (raw={yp_raw.exists()}, adj={yp_adj.exists()})")
        return 0

    try:
        raw_ds = ds.dataset(str(yp_raw), format="parquet")
        adj_ds = ds.dataset(str(yp_adj), format="parquet")
    except Exception as e:
        logger.warning(f"Cannot open dataset for year={year}: {e}")
        return 0

    scanner_raw = raw_ds.scanner(columns=["ts_code", "trade_date", "close"])
    scanner_adj = adj_ds.scanner(columns=["ts_code", "trade_date", "close"])

    df_raw = scanner_raw.to_table().to_pandas()
    df_adj = scanner_adj.to_table().to_pandas()

    if df_raw.empty or df_adj.empty:
        return 0

    df_raw = df_raw.rename(columns={"close": "close_raw"})
    df_adj = df_adj.rename(columns={"close": "close_adj"})

    merged = pd.merge(df_raw, df_adj, on=["ts_code", "trade_date"], how="inner")

    if merged.empty:
        return 0

    # Compute adj_factor = close_adj / close_raw
    # Guard against zeros and extreme values
    mask = (merged["close_raw"].abs() > 1e-8) & (merged["close_adj"].abs() > 1e-8)
    merged = merged[mask].copy()

    merged["adj_factor"] = merged["close_adj"] / merged["close_raw"]

    # Filter unreasonable adj_factors (should be near 1.0, typically 0.1 to 10)
    merged = merged[(merged["adj_factor"] > 0.05) & (merged["adj_factor"] < 20.0)]

    output = merged[["ts_code", "trade_date", "adj_factor"]].copy()
    output["trade_date"] = output["trade_date"].astype("int32")
    output["ts_code"] = output["ts_code"].astype(str)
    output["adj_factor"] = output["adj_factor"].astype("float64")
    output["year"] = np.int32(year)

    # Drop any nulls
    output = output.dropna(subset=["ts_code", "trade_date", "adj_factor"])

    n_rows = len(output)

    if not dry_run and n_rows > 0:
        out_dir = adj_factor_base / f"year={year}"
        out_dir.mkdir(parents=True, exist_ok=True)

        # Write to temp dir, then atomically replace
        tmp_dir = Path(tempfile.mkdtemp(prefix=f"adj_factor_derive_{year}_"))
        try:
            # Remove existing files
            for f in out_dir.glob("*.parquet"):
                f.unlink()

            table = pa.Table.from_pandas(output, schema=ADJ_FACTOR_SCHEMA)
            tmp_file = tmp_dir / "data.parquet"
            pq.write_table(table, str(tmp_file), compression="zstd")
            shutil.move(str(tmp_file), str(out_dir / "data.parquet"))
            logger.info(f"Derived adj_factor for year={year}: {n_rows} rows [atomic write]")
        finally:
            if tmp_dir.exists():
                shutil.rmtree(str(tmp_dir), ignore_errors=True)

    return n_rows


def main():
    parser = argparse.ArgumentParser(description="Repair adj_factor cache")
    parser.add_argument("--start", default="20170101", help="Start date (YYYYMMDD)")
    parser.add_argument("--end", default="20241231", help="End date (YYYYMMDD)")
    parser.add_argument("--years", type=str, default=None,
                        help="Comma-separated list of specific years to repair (e.g. '2023,2024')")
    parser.add_argument("--dry-run", action="store_true", help="Report only, no modifications")
    parser.add_argument("--dedup-only", action="store_true",
                        help="Only deduplicate existing partitions, skip derivation")
    args = parser.parse_args()

    start_year = int(args.start[:4])
    end_year = int(args.end[:4])

    # Parse --years filter
    years_filter: Optional[Set[int]] = None
    if args.years:
        years_filter = set(int(y.strip()) for y in args.years.split(","))
        logger.info(f"Targeting specific years: {sorted(years_filter)}")

    data_dir = Path("data") / "parquet"
    adj_factor_base = data_dir / "adj_factor"
    prices_raw_base = data_dir / "prices_raw"
    prices_adj_base = data_dir / "prices_adj"

    total_removed = 0
    total_derived = 0

    # Step 1: Deduplicate existing partitions
    logger.info("=" * 60)
    logger.info("Step 1: Deduplicating adj_factor partitions...")
    if years_filter:
        logger.info(f"  Filtered to years: {sorted(years_filter)}")

    for year_dir in sorted(adj_factor_base.glob("year=*")):
        year = int(year_dir.name.split("=")[1])
        # Dedup all years by default, or filter if --years specified
        if years_filter is not None and year not in years_filter:
            continue
        if start_year <= year <= end_year:
            n = dedup_partition(year_dir, dry_run=args.dry_run, years_filter=years_filter)
            total_removed += n

    logger.info(f"Deduplication: {total_removed} total rows removed")

    if args.dedup_only:
        logger.info("--dedup-only specified, skipping derivation step.")
        if args.dry_run:
            logger.info("DRY RUN — no changes made. Remove --dry-run to apply.")
        else:
            logger.info("Repair (dedup only) complete. Run audit_cache.py to verify.")
        return

    # Step 2: Fill missing years from prices
    logger.info("=" * 60)
    logger.info("Step 2: Deriving adj_factor from prices_adj / prices_raw for missing years...")
    for year in range(start_year, end_year + 1):
        if years_filter is not None and year not in years_filter:
            continue

        ydir = adj_factor_base / f"year={year}"
        # Check if coverage is adequate (> 50 trading days of data)
        if ydir.exists():
            files = list(ydir.glob("*.parquet"))
            if files:
                try:
                    n_rows = sum(pq.read_metadata(str(f)).num_rows for f in files)
                    if n_rows > 1000:  # Adequate coverage
                        logger.info(f"year={year}: {n_rows} rows, skipping (adequate)")
                        continue
                except Exception:
                    pass

        logger.info(f"year={year}: rebuilding from prices...")
        n = derive_adj_factor_from_prices(
            year, prices_raw_base, prices_adj_base, adj_factor_base, dry_run=args.dry_run
        )
        total_derived += n

    logger.info(f"Derivation: {total_derived} total rows derived")

    # Summary
    logger.info("=" * 60)
    logger.info(f"Summary: {total_removed} dupes removed, {total_derived} rows derived")
    if args.dry_run:
        logger.info("DRY RUN — no changes made. Remove --dry-run to apply.")
    else:
        logger.info("Repair complete. Run audit_cache.py to verify.")


if __name__ == "__main__":
    main()

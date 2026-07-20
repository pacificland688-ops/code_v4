#!/usr/bin/env python
"""
Cache repair script — fix corrupted parquet partitions.

Currently supports:
- limit_status: deduplicate (ts_code, trade_date) and rewrite partitions

Safety: backs up affected partitions to data/parquet_backup/ before repair.

Usage:
    python scripts/repair_cache.py --dataset limit_status --start 20160101 --end 20161231
    python scripts/repair_cache.py --dataset limit_status --start 20160101 --end 20161231 --dry-run
"""

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def repair_limit_status(start: str, end: str, dry_run: bool = False):
    """Deduplicate limit_status cache and rewrite clean partitions."""
    from data.panel_loader import get_loader

    loader = get_loader()
    base = loader.data_path / "limit_status"

    if not base.exists():
        print(f"No limit_status cache at {base}")
        return 0, 0

    # 1. Read all data in the requested date range
    print(f"Reading limit_status {start}-{end} ...")
    df = loader.query(
        "limit_status",
        start_date=start, end_date=end,
    )

    if df.empty:
        print("No data found in range.")
        return 0, 0

    n_before = len(df)
    n_dupes = int(df.duplicated(["ts_code", "trade_date"]).sum())
    print(f"  {n_before} rows, {n_dupes} duplicates")

    if n_dupes == 0:
        print("No duplicates to repair.")
        return 0, n_before

    # 2. Backup
    backup_base = Path("data/parquet_backup")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = backup_base / f"limit_status_{ts}"
    if not dry_run:
        backup_dir.parent.mkdir(parents=True, exist_ok=True)
        if base.exists():
            shutil.copytree(str(base), str(backup_dir))
            print(f"Backed up to {backup_dir}")

    # 3. Deduplicate
    df_clean = df.drop_duplicates(["ts_code", "trade_date"], keep="last")
    n_after = len(df_clean)
    n_removed = n_before - n_after
    print(f"After dedup: {n_after} rows ({n_removed} removed)")

    # 4. Rewrite partitions
    if not dry_run:
        # Ensure year and month columns exist for partitioning
        if "year" not in df_clean.columns:
            df_clean["year"] = df_clean["trade_date"].astype(int) // 10000
        if "month" not in df_clean.columns:
            df_clean["month"] = (df_clean["trade_date"].astype(int) % 10000) // 100

        # Remove old partitions for affected months
        affected_partitions = set()
        for _, row in df_clean.iterrows():
            affected_partitions.add((int(row["year"]), int(row["month"])))

        for y, m in sorted(affected_partitions):
            part_dir = base / f"year={y}" / f"month={m}"
            if part_dir.exists():
                shutil.rmtree(str(part_dir))
                print(f"  Cleaned {part_dir}")

        # Write clean data
        loader.write_data(
            df_clean,
            "limit_status",
            partition_cols=["year", "month"],
            dedupe_keys=["ts_code", "trade_date"],
            replace_partitions=True,
        )
        print(f"Wrote {n_after} clean rows to limit_status")

        # Verify
        df_verify = loader.query(
            "limit_status",
            columns=["ts_code", "trade_date"],
            start_date=start, end_date=end,
        )
        dupes_after = int(df_verify.duplicated(["ts_code", "trade_date"]).sum())
        if dupes_after > 0:
            print(f"WARNING: {dupes_after} duplicates remain after repair!")
            return dupes_after, n_after
        else:
            print("Verified: 0 duplicates after repair.")
    else:
        print(f"[DRY-RUN] Would remove {n_removed} duplicate rows "
              f"and rewrite {n_after} clean rows.")

    return 0 if not dry_run else n_dupes, n_after


def main():
    parser = argparse.ArgumentParser(
        description="Repair corrupted parquet cache partitions"
    )
    parser.add_argument(
        "--dataset", required=True,
        choices=["limit_status"],
        help="Dataset to repair"
    )
    parser.add_argument("--start", default="20160101")
    parser.add_argument("--end", default="20161231")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be done without doing it")
    args = parser.parse_args()

    if args.dataset == "limit_status":
        remaining_dupes, clean_rows = repair_limit_status(
            args.start, args.end, args.dry_run
        )
        if remaining_dupes > 0:
            sys.exit(1)
    else:
        print(f"Unknown dataset: {args.dataset}")
        sys.exit(1)


if __name__ == "__main__":
    main()

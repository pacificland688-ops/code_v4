#!/usr/bin/env python
"""
Migrate factor cache from legacy year-level layout to year+month layout.

Problem:
    Old layout:  factors/factor_name=xxx/year=2016/*.parquet
    New layout:  factors/factor_name=xxx/year=2016/month=1/*.parquet

    When both coexist, DuckDB / PyArrow reads both, causing duplicate
    (ts_code, trade_date) rows that break factor_coverage and cause
    Phase 2 to skip factors.

Solution:
    This script scans all factor directories and removes bare .parquet
    files at the year=YYYY level when month=M subdirectories already
    exist in the same year directory.

Usage:
    python scripts/migrate_factor_cache.py
    python scripts/migrate_factor_cache.py --dry-run
    python scripts/migrate_factor_cache.py --factor reversal_5_cs
"""

import argparse
import sys
from pathlib import Path

# Add code_v4 to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def migrate(dry_run: bool = False, factor_name: str = None):
    """Scan and clean legacy factor cache layout."""
    from data.panel_loader import get_loader

    loader = get_loader()
    factors_base = loader.data_path / "factors"

    if not factors_base.exists():
        print("No factor cache found at", factors_base)
        return 0

    total_removed = 0
    total_factors_checked = 0

    pattern = f"factor_name={factor_name}" if factor_name else "factor_name=*"
    for factor_dir in sorted(factors_base.glob(pattern)):
        total_factors_checked += 1
        fname = factor_dir.name.replace("factor_name=", "")

        for year_dir in sorted(factor_dir.glob("year=*")):
            bare_files = sorted(year_dir.glob("*.parquet"))
            month_dirs = sorted(year_dir.glob("month=*"))

            if not bare_files:
                continue

            if month_dirs:
                # Legacy files coexist with new month partitions → remove legacy
                for p in bare_files:
                    size_kb = p.stat().st_size / 1024
                    if dry_run:
                        print(f"  [DRY-RUN] would remove: {p} ({size_kb:.1f} KB)")
                    else:
                        p.unlink()
                        print(f"  Removed: {p} ({size_kb:.1f} KB)")
                    total_removed += 1
            else:
                # Only bare files, no month dirs → whole year is legacy.
                # Don't touch these — they'll be migrated naturally when
                # Phase 1 --recompute writes the new layout.
                print(f"  [INFO] {fname}/{year_dir.name}: legacy-only "
                      f"({len(bare_files)} files, no month dirs) — "
                      f"will be migrated on next --recompute")

    if dry_run:
        print(f"\nDRY-RUN: {total_removed} files would be removed "
              f"across {total_factors_checked} factors")
    else:
        print(f"\nRemoved {total_removed} legacy files "
              f"across {total_factors_checked} factors")
        if total_removed > 0:
            print("Done. Re-run factor_coverage checks to verify duplicates=0.")

    return total_removed


def main():
    parser = argparse.ArgumentParser(
        description="Migrate factor cache from legacy year-level to year+month layout"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be removed without actually removing"
    )
    parser.add_argument(
        "--factor", type=str, default=None,
        help="Migrate only a specific factor (e.g., reversal_5_cs)"
    )
    args = parser.parse_args()

    migrate(dry_run=args.dry_run, factor_name=args.factor)


if __name__ == "__main__":
    main()

"""
Tests for factor cache migration from legacy year-level to year+month layout.

Verifies:
- Legacy year=YYYY/*.parquet files are removed when month=M/ subdirs exist
- factor_coverage returns duplicates=0 after migration
- write_factor automatically cleans up legacy files
"""

import os
import shutil
import tempfile
from pathlib import Path

import pandas as pd
import pytest


class TestLegacyFactorCleanup:
    """Verify legacy factor layout cleanup."""

    def test_cleanup_legacy_factor_layout_removes_bare_files(self):
        """When year=2016 has both *.parquet AND month=1/, bare files removed."""
        from data.panel_loader import PanelLoader

        tmp = tempfile.mkdtemp()
        try:
            loader = PanelLoader(data_path=tmp)

            # Create a legacy file
            base = Path(tmp) / "factors/factor_name=test_cs/year=2016"
            base.mkdir(parents=True)
            legacy_file = base / "part-0.parquet"
            # Create a minimal parquet file
            df_legacy = pd.DataFrame({
                "ts_code": ["000001.SZ"],
                "trade_date": [20160104],
                "test_cs": [0.5],
            })
            df_legacy.to_parquet(legacy_file)

            # Create a month subdirectory (new layout)
            month_dir = base / "month=1"
            month_dir.mkdir(parents=True)
            df_new = pd.DataFrame({
                "ts_code": ["000001.SZ"],
                "trade_date": [20160104],
                "test_cs": [0.5],
            })
            df_new.to_parquet(month_dir / "part-0.parquet")

            # Verify both exist
            assert legacy_file.exists()
            assert month_dir.exists()

            # Run cleanup
            loader.cleanup_legacy_factor_layout("test_cs", [2016])

            # Legacy file should be gone, month dir should remain
            assert not legacy_file.exists(), "Legacy file was not removed"
            assert month_dir.exists(), "Month directory was incorrectly removed"

        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_write_factor_auto_cleans_legacy(self):
        """write_factor should auto-clean legacy files before writing."""
        from data.panel_loader import PanelLoader

        tmp = tempfile.mkdtemp()
        try:
            loader = PanelLoader(data_path=tmp)

            # Create legacy layout first
            base = Path(tmp) / "factors/factor_name=test_cs/year=2016"
            base.mkdir(parents=True)
            legacy_file = base / "legacy.parquet"
            pd.DataFrame({
                "ts_code": ["000001.SZ"],
                "trade_date": [20160104],
                "test_cs": [0.5],
            }).to_parquet(legacy_file)

            # Also create a month subdir (simulating mixed state)
            (base / "month=1").mkdir(parents=True, exist_ok=True)

            # Now write new data via write_factor
            df = pd.DataFrame({
                "ts_code": ["000001.SZ", "000002.SZ"],
                "trade_date": [20160104, 20160104],
                "test_cs": [0.1, -0.2],
            })
            loader.write_factor(df, "test_cs", partition_by_year=True)

            # Legacy file should be gone
            assert not legacy_file.exists(), (
                f"Legacy file still exists at {legacy_file}"
            )

            # New month partition should exist
            new_part = base / "month=1"
            assert new_part.exists(), f"New partition {new_part} missing"

            # Coverage should show 0 duplicates
            cov = loader.factor_coverage("test_cs", "20160101", "20160131")
            assert cov["duplicates"] == 0, f"Got {cov['duplicates']} duplicates"
            assert cov["rows"] == 2, f"Got {cov['rows']} rows"

        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_cleanup_all_legacy_scans_everything(self):
        """cleanup_all_legacy_factor_layouts scans all factors."""
        from data.panel_loader import PanelLoader

        tmp = tempfile.mkdtemp()
        try:
            loader = PanelLoader(data_path=tmp)

            # Create 3 factors with mixed layouts
            for fname in ["a_cs", "b_cs", "c_cs"]:
                base = Path(tmp) / f"factors/factor_name={fname}/year=2016"
                base.mkdir(parents=True)
                # Legacy file
                pd.DataFrame({
                    "ts_code": ["000001.SZ"],
                    "trade_date": [20160104],
                    fname: [0.1],
                }).to_parquet(base / "old.parquet")
                # Month subdir
                (base / "month=1").mkdir(parents=True, exist_ok=True)

            # Also create a factor with ONLY legacy layout (no month dirs)
            base_legacy = Path(tmp) / "factors/factor_name=legacy_cs/year=2016"
            base_legacy.mkdir(parents=True)
            pd.DataFrame({
                "ts_code": ["000001.SZ"],
                "trade_date": [20160104],
                "legacy_cs": [0.1],
            }).to_parquet(base_legacy / "old.parquet")

            removed = loader.cleanup_all_legacy_factor_layouts()

            # Should remove 3 files (a, b, c) but leave legacy-only alone
            assert removed == 3, f"Expected 3 removed, got {removed}"
            assert base_legacy.glob("*.parquet"), "Legacy-only should be untouched"

        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_factor_coverage_no_duplicates_after_cleanup(self):
        """After cleanup, factor_coverage should report duplicates=0."""
        from data.panel_loader import PanelLoader

        tmp = tempfile.mkdtemp()
        try:
            loader = PanelLoader(data_path=tmp)

            # Write via write_factor (which auto-cleans)
            df = pd.DataFrame({
                "ts_code": ["000001.SZ", "000002.SZ"] * 3,
                "trade_date": [20160104, 20160104, 20160201, 20160201,
                              20160301, 20160301],
                "test_cs": [0.1, -0.2, 0.3, -0.4, 0.5, -0.6],
            })
            loader.write_factor(df, "test_cs", partition_by_year=True)

            cov = loader.factor_coverage("test_cs", "20160101", "20160331")
            assert cov["duplicates"] == 0, f"Got {cov['duplicates']} duplicates"
            assert cov["rows"] == 6
            assert cov["n_dates"] == 3

        finally:
            shutil.rmtree(tmp, ignore_errors=True)

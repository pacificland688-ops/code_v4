"""
Tests for limit_status merge-write helper.

Verifies:
- Short-window write doesn't reduce cached date count
- Merged write deduplicates correctly
- New data overwrites old data for same (ts_code, trade_date)
- Cross-month writes don't affect other months
"""

import os
import shutil
import tempfile
from pathlib import Path

import pandas as pd
import pytest

from data.limit_status_cache import (
    write_limit_status_merged,
    _normalize_limit_status_df,
    _month_bounds,
)


class TestLimitStatusMergeWrite:
    """Verify merge write preserves existing dates."""

    def test_short_window_does_not_reduce_dates(self):
        """Writing 5 dates when 20 exist should keep all 20 dates."""
        from data.panel_loader import PanelLoader

        tmp = tempfile.mkdtemp()
        try:
            loader = PanelLoader(data_path=tmp)

            # Create full-month data: 20 trading days
            full_dates = [20160104, 20160105, 20160106, 20160107, 20160108,
                         20160111, 20160112, 20160113, 20160114, 20160115,
                         20160118, 20160119, 20160120, 20160121, 20160122,
                         20160125, 20160126, 20160127, 20160128, 20160129]

            full_rows = []
            for d in full_dates:
                for s in ["000001.SZ", "000002.SZ", "000003.SZ"]:
                    full_rows.append({
                        "ts_code": s,
                        "trade_date": d,
                        "up_limit": 11.0,
                        "down_limit": 9.0,
                    })
            df_full = pd.DataFrame(full_rows)
            df_full["year"] = 2016
            df_full["month"] = 1
            loader.write_data(
                df_full, "limit_status",
                partition_cols=["year", "month"],
                dedupe_keys=["ts_code", "trade_date"],
                replace_partitions=True,
            )

            # Verify full data exists
            before = loader.query(
                "limit_status",
                columns=["ts_code", "trade_date"],
                start_date="20160101", end_date="20160131",
            )
            assert before["trade_date"].nunique() == 20, (
                f"Expected 20 dates, got {before['trade_date'].nunique()}"
            )

            # Now simulate short-window Phase 0: only 5 dates, overlapping
            short_dates = [20160104, 20160105, 20160111, 20160118, 20160125]
            short_rows = []
            for d in short_dates:
                for s in ["000001.SZ", "000002.SZ"]:
                    short_rows.append({
                        "ts_code": s,
                        "trade_date": d,
                        "up_limit": 99.0,  # updated value
                        "down_limit": 81.0,
                    })
            df_short = pd.DataFrame(short_rows)

            # Use merged write
            n_written = write_limit_status_merged(loader, df_short)
            assert n_written > 0

            # After merge: should still have 20 dates
            after = loader.query(
                "limit_status",
                columns=["ts_code", "trade_date", "up_limit"],
                start_date="20160101", end_date="20160131",
            )
            assert after["trade_date"].nunique() == 20, (
                f"Dates reduced from 20 to {after['trade_date'].nunique()} "
                f"after short-window write!"
            )
            assert after.duplicated(["ts_code", "trade_date"]).sum() == 0

            # Updated values should be from short write (99.0 not 11.0)
            updated = after[
                (after["ts_code"] == "000001.SZ") &
                (after["trade_date"] == 20160104)
            ]
            assert len(updated) == 1
            assert updated["up_limit"].iloc[0] == 99.0, (
                f"Expected updated value 99.0, got {updated['up_limit'].iloc[0]}"
            )

            # Unchanged date should keep original values
            unchanged = after[
                (after["ts_code"] == "000003.SZ") &
                (after["trade_date"] == 20160106)
            ]
            assert len(unchanged) == 1

        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_merge_write_cross_month_isolation(self):
        """Writing to Jan+Feb should not affect March."""
        from data.panel_loader import PanelLoader

        tmp = tempfile.mkdtemp()
        try:
            loader = PanelLoader(data_path=tmp)

            # Write March data first
            mar_rows = []
            for d in [20160301, 20160302]:
                for s in ["000001.SZ"]:
                    mar_rows.append({
                        "ts_code": s, "trade_date": d,
                        "up_limit": 11.0, "down_limit": 9.0,
                    })
            df_mar = pd.DataFrame(mar_rows)
            df_mar["year"] = 2016
            df_mar["month"] = 3
            loader.write_data(
                df_mar, "limit_status",
                partition_cols=["year", "month"],
                dedupe_keys=["ts_code", "trade_date"],
                replace_partitions=True,
            )

            # Now write Jan+Feb via merged write
            jan_feb_rows = []
            for d in [20160104, 20160201]:
                for s in ["000001.SZ"]:
                    jan_feb_rows.append({
                        "ts_code": s, "trade_date": d,
                        "up_limit": 99.0, "down_limit": 81.0,
                    })
            df_jan_feb = pd.DataFrame(jan_feb_rows)
            write_limit_status_merged(loader, df_jan_feb)

            # March should still exist
            mar_after = loader.query(
                "limit_status",
                columns=["ts_code", "trade_date"],
                start_date="20160301", end_date="20160302",
            )
            assert not mar_after.empty, "March data was incorrectly deleted!"
            assert mar_after["trade_date"].nunique() == 2

        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_normalize_adds_year_month(self):
        """_normalize_limit_status_df should add year/month columns."""
        df = pd.DataFrame({
            "ts_code": ["000001.SZ"],
            "trade_date": [20160104],
            "up_limit": [11.0],
            "down_limit": [9.0],
        })
        result = _normalize_limit_status_df(df)
        assert "year" in result.columns
        assert "month" in result.columns
        assert result["year"].iloc[0] == 2016
        assert result["month"].iloc[0] == 1

    def test_month_bounds_correct(self):
        """_month_bounds should return correct start/end."""
        # January
        start, end = _month_bounds(2016, 1)
        assert start == "20160101"
        assert end == "20160131"

        # December
        start, end = _month_bounds(2016, 12)
        assert start == "20161201"
        assert end == "20161231"

        # February (leap year 2016)
        start, end = _month_bounds(2016, 2)
        assert start == "20160201"
        assert end == "20160229"

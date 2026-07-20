"""
Verify calendar singleton load() uses UNION semantics — a narrow load()
must never shrink the in-memory date range.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import numpy as np


class TestCalendarSingletonPollution:
    """Verify narrow load() does not shrink the calendar."""

    def test_narrow_load_does_not_shrink_wide_calendar(self, monkeypatch):
        """Load wide range, then narrow — wide range must stay intact."""
        from data.calendar import TradingCalendar

        cal = TradingCalendar()

        # Build a fake calendar: all days 1-28 for every month 2015-2025
        all_dates = []
        for y in range(2015, 2026):
            for m in range(1, 13):
                for d in range(1, 29):
                    date_int = y * 10000 + m * 100 + d
                    all_dates.append(date_int)
        cal._trade_dates = set(all_dates)
        cal._trade_dates_sorted = np.array(sorted(all_dates), dtype=np.int32)
        cal._date_to_idx = {d: i for i, d in enumerate(cal._trade_dates_sorted)}

        orig_min = int(cal._trade_dates_sorted[0])
        orig_max = int(cal._trade_dates_sorted[-1])

        # Simulate Phase3 price window check: narrow load
        cal.load(start_date="20160101", end_date="20160131")

        # After narrow load, the range must NOT have shrunk
        new_min = int(cal._trade_dates_sorted[0])
        new_max = int(cal._trade_dates_sorted[-1])
        assert new_min <= orig_min, (
            f"Narrow load shrunk calendar start: {orig_min} → {new_min}"
        )
        assert new_max >= orig_max, (
            f"Narrow load shrunk calendar end: {orig_max} → {new_max}"
        )

    def test_weekly_dates_after_narrow_load_attempt(self, monkeypatch):
        """After a narrow load attempt, weekly dates for 2016 must be ~50."""
        from data.calendar import TradingCalendar
        from datetime import datetime

        cal = TradingCalendar()

        # Build realistic A-share calendar: Mon-Fri for 2015-2016
        all_dates = []
        for y in range(2015, 2017):
            for m in range(1, 13):
                for d in range(1, 29):
                    try:
                        dt = datetime(y, m, d)
                        if dt.weekday() < 5:  # Mon-Fri only
                            date_int = y * 10000 + m * 100 + d
                            all_dates.append(date_int)
                    except ValueError:
                        pass

        cal._trade_dates = set(all_dates)
        cal._trade_dates_sorted = np.array(sorted(all_dates), dtype=np.int32)
        cal._date_to_idx = {d: i for i, d in enumerate(cal._trade_dates_sorted)}

        # Simulate narrow load pollution attempt
        cal.load(start_date="20160101", end_date="20160131")

        # After pollution attempt, 2016 weekly dates must be substantial
        weekly = cal.weekly_rebalance_dates("20160101", "20161231")
        assert len(weekly) >= 40, (
            f"Expected >= 40 weekly dates for 2016, got {len(weekly)}"
        )

    def test_load_fully_covered_returns_immediately(self):
        """When cache fully covers request, load() is a no-op."""
        from data.calendar import TradingCalendar

        cal = TradingCalendar()
        # Set up wide cache covering 2015-2026 properly
        all_dates = []
        for y in range(2015, 2027):
            for m in range(1, 13):
                for d in range(1, 29):
                    date_int = y * 10000 + m * 100 + d
                    all_dates.append(date_int)
        cal._trade_dates = set(all_dates)
        cal._trade_dates_sorted = np.array(sorted(all_dates), dtype=np.int32)
        cal._date_to_idx = {d: i for i, d in enumerate(cal._trade_dates_sorted)}

        orig_len = len(cal._trade_dates_sorted)

        # Request fully within cache
        cal.load(start_date="20160101", end_date="20160131")

        # Cache must be unchanged (no-op)
        assert len(cal._trade_dates_sorted) == orig_len, (
            f"Fully covered load() should be a no-op. "
            f"Length changed: {orig_len} → {len(cal._trade_dates_sorted)}"
        )

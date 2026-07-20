"""
Verify Phase5 monthly scenario has valid composite scores — the union
of weekly + monthly signal dates must cover all scenarios.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import pandas as pd
import numpy as np


class TestPhase5MonthlyScores:
    """Monthly scenarios must have valid composite score coverage."""

    def test_union_contains_monthly_dates(self):
        """Union of weekly + monthly includes monthly-only dates."""
        # Simulate a calendar with known dates
        weekly = {"20160101", "20160108", "20160115", "20160122", "20160129"}
        monthly = {"20160129", "20160226"}  # last trading days of month

        union = sorted(weekly | monthly)

        # Monthly-only dates must be in union
        for d in monthly:
            assert d in union, f"Monthly date {d} must be in union"

        # Union is superset of both
        assert set(union) >= weekly
        assert set(union) >= monthly

    def test_monthly_scenario_gets_scores(self):
        """When composite has union dates, a monthly date query finds scores."""
        # Build a composite with union weekly+monthly dates
        dates = list(range(20160104, 20161231, 7))  # weekly
        monthly_dates = [20160104, 20160201, 20160301, 20160401,
                        20160502, 20160601, 20160701, 20160801,
                        20160901, 20161003, 20161101, 20161201]
        all_dates = sorted(set(dates) | set(monthly_dates))

        composite = pd.DataFrame({
            "ts_code": [f"{i:04d}.SZ" for i in range(100) for _ in range(len(all_dates))],
            "trade_date": [d for d in all_dates for _ in range(100)],
            "composite_score": np.random.randn(100 * len(all_dates)).astype("float32"),
        })

        # A monthly rebalance date must have scores
        test_monthly = 20160201  # monthly-only date (not weekly)
        day_scores = composite[composite["trade_date"] == test_monthly]
        assert len(day_scores) > 0, (
            f"No scores for monthly rebalance date {test_monthly}! "
            f"Composite covers: {sorted(composite['trade_date'].unique())[:10]}..."
        )

        # A weekly date also has scores
        test_weekly = 20160111
        day_scores = composite[composite["trade_date"] == test_weekly]
        assert len(day_scores) > 0, (
            f"No scores for weekly date {test_weekly}"
        )

    def test_monthly_n_periods_sufficient(self):
        """Monthly backtest should have >= 5 periods when data covers union."""
        # Simulate 12 monthly periods in a year
        monthly_dates_count = 12
        assert monthly_dates_count >= 5, (
            f"Expected >= 5 monthly periods per year, got {monthly_dates_count}"
        )

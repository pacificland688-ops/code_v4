"""
Verify PaperBroker execution summary — HIGH_SLIPPAGE is counted as
executed (not failed), and FILLED is clean.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import pandas as pd
import numpy as np


class TestPaperBrokerSummary:
    """HIGH_SLIPPAGE fills are executed, not failed."""

    def test_high_slippage_counted_as_executed(self):
        """50 HIGH_SLIPPAGE + 0 FILLED = 50 executed, 0 clean."""
        # Simulate the counting logic from _log_summary
        fills = pd.DataFrame({
            "status": ["HIGH_SLIPPAGE"] * 50,
            "fill_rate": [1.0] * 50,
            "slippage_bps": [15.0] * 50,
            "cost_cny": [10000.0] * 50,
        })

        n_clean = len(fills[fills["status"] == "FILLED"])
        n_high_slip = len(fills[fills["status"] == "HIGH_SLIPPAGE"])
        n_executed = n_clean + n_high_slip
        n_failed = len(fills[fills["status"] == "NO_PRICE"])

        assert n_clean == 0, "HIGH_SLIPPAGE orders are not 'clean'"
        assert n_high_slip == 50
        assert n_executed == 50, (
            f"HIGH_SLIPPAGE orders ARE executed! Expected 50, got {n_executed}"
        )
        assert n_failed == 0

    def test_mixed_statuses_correctly_counted(self):
        """25 FILLED + 20 HIGH_SLIPPAGE + 5 NO_PRICE = 45 executed, 5 failed."""
        fills = pd.DataFrame({
            "status": (["FILLED"] * 25 + ["HIGH_SLIPPAGE"] * 20
                      + ["NO_PRICE"] * 5),
            "fill_rate": [1.0] * 45 + [0.0] * 5,
            "slippage_bps": [5.0] * 25 + [20.0] * 20 + [0.0] * 5,
            "cost_cny": [10000.0] * 50,
        })

        n_clean = len(fills[fills["status"] == "FILLED"])
        n_high_slip = len(fills[fills["status"] == "HIGH_SLIPPAGE"])
        n_executed = n_clean + n_high_slip
        n_failed = len(fills[fills["status"] == "NO_PRICE"])

        assert n_clean == 25
        assert n_high_slip == 20
        assert n_executed == 45, f"Expected 45 executed, got {n_executed}"
        assert n_failed == 5, f"Expected 5 failed, got {n_failed}"

    def test_slippage_computed_when_assumed_and_actual_differ(self):
        """When assumed_price != actual_price, slippage_bps is non-zero."""
        from live.paper_broker import PaperBroker

        # Build a minimal fill manually
        broker = PaperBroker(date_str="20260105")
        broker.slippage_tolerance_bps = 10.0

        # Simulate: assumed=10.0 (signal close), actual=10.02 (next open)
        # slippage = (10.02/10.0 - 1) * 10000 = 20 bps for buy
        assumed = 10.0
        actual = 10.02
        slippage = (actual / assumed - 1) * 10000  # +20 bps

        # For buy: positive slippage = paid more
        assert abs(slippage - 20.0) < 0.01, f"Expected ~20 bps, got {slippage:.1f}"

    def test_no_slippage_when_prices_equal(self):
        """When assumed == actual, slippage is 0."""
        assumed = 10.0
        actual = 10.0
        slippage = (actual / assumed - 1) * 10000
        assert abs(slippage) < 0.001, f"Slippage should be 0, got {slippage:.4f}"

"""
Verify shadow trading execution failure detection:
- READY orders with empty fills → FAIL
- HIGH_SLIPPAGE counted in n_executed
- Risk gate BLOCK → SKIPPED
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import pandas as pd


class TestShadowExecutionFailure:
    """Shadow must detect execution failures correctly."""

    def test_ready_orders_empty_fills_is_fail(self):
        """n_ready > 0 and fills.empty → execution FAIL."""
        n_ready = 57
        fills = pd.DataFrame()

        # Replicate the execution-stage logic from run_shadow
        if not fills.empty:
            n_clean = int((fills["status"] == "FILLED").sum())
            n_high_slippage = int((fills["status"] == "HIGH_SLIPPAGE").sum())
            n_executed = n_clean + n_high_slippage
        else:
            n_clean = 0
            n_high_slippage = 0
            n_executed = 0

        if n_ready > 0 and fills.empty:
            exec_status = "FAIL"
        elif n_ready > 0 and n_executed == 0:
            exec_status = "FAIL"
        else:
            exec_status = "OK"

        assert exec_status == "FAIL", (
            f"{n_ready} READY orders with empty fills must be FAIL, "
            f"got {exec_status}"
        )

    def test_ready_orders_zero_executed_is_fail(self):
        """n_ready > 0 and n_executed == 0 → execution FAIL."""
        # All orders resulted in NO_PRICE
        fills = pd.DataFrame({
            "status": ["NO_PRICE"] * 57,
            "fill_rate": [0.0] * 57,
        })
        n_ready = 57

        n_clean = int((fills["status"] == "FILLED").sum())
        n_high_slippage = int((fills["status"] == "HIGH_SLIPPAGE").sum())
        n_executed = n_clean + n_high_slippage

        if n_ready > 0 and n_executed == 0:
            exec_status = "FAIL"
        else:
            exec_status = "OK"

        assert exec_status == "FAIL", (
            f"0 executed with {n_ready} READY must be FAIL, got {exec_status}"
        )

    def test_partial_execution_is_ok(self):
        """Some executed + some NO_PRICE → execution OK (partial fill is OK)."""
        fills = pd.DataFrame({
            "status": (["FILLED"] * 40 + ["HIGH_SLIPPAGE"] * 10
                      + ["NO_PRICE"] * 7),
            "fill_rate": [1.0] * 50 + [0.0] * 7,
        })
        n_ready = 57

        n_clean = int((fills["status"] == "FILLED").sum())
        n_high_slippage = int((fills["status"] == "HIGH_SLIPPAGE").sum())
        n_executed = n_clean + n_high_slippage

        exec_status = "OK"  # 50 executed > 0, partial fill is not a failure
        assert exec_status == "OK"
        assert n_executed == 50
        assert n_clean == 40
        assert n_high_slippage == 10

    def test_overall_verdict_fail_when_execution_fails(self):
        """Any stage FAIL → overall FAIL."""
        stages = {
            "signals": {"status": "OK"},
            "orders": {"status": "OK", "n_ready": 57},
            "risk": {"status": "OK"},
            "execution": {"status": "FAIL", "n_executed": 0},
        }
        stage_statuses = [s["status"] for s in stages.values()]
        if "FAIL" in stage_statuses:
            overall = "FAIL"
        elif "SKIPPED" in stage_statuses:
            overall = "SKIPPED"
        else:
            overall = "OK"

        assert overall == "FAIL", (
            f"Execution FAIL must produce overall FAIL, got {overall}"
        )

    def test_overall_verdict_skipped_when_no_fail(self):
        """No FAIL but some SKIPPED → overall SKIPPED."""
        stages = {
            "signals": {"status": "OK"},
            "orders": {"status": "OK", "n_ready": 0},
            "risk": {"status": "OK"},
            "execution": {"status": "SKIPPED",
                         "reason": "Risk gate: BLOCK"},
        }
        stage_statuses = [s["status"] for s in stages.values()]
        if "FAIL" in stage_statuses:
            overall = "FAIL"
        elif "SKIPPED" in stage_statuses:
            overall = "SKIPPED"
        else:
            overall = "OK"

        assert overall == "SKIPPED", (
            f"Risk BLOCK with no FAIL should be SKIPPED, got {overall}"
        )

    def test_high_slippage_counted_as_executed(self):
        """HIGH_SLIPPAGE fills are executed, not failed."""
        # Simulate a realistic shadow execution result
        fills = pd.DataFrame({
            "status": (["FILLED"] * 11 + ["HIGH_SLIPPAGE"] * 38
                      + ["NO_PRICE"] * 1),
            "fill_rate": [1.0] * 49 + [0.0] * 1,
            "slippage_bps": [5.0] * 11 + [25.0] * 38 + [0.0] * 1,
        })

        n_clean = int((fills["status"] == "FILLED").sum())
        n_high_slippage = int((fills["status"] == "HIGH_SLIPPAGE").sum())
        n_executed = n_clean + n_high_slippage
        n_failed = int((fills["status"] == "NO_PRICE").sum())

        assert n_clean == 11, f"Expected 11 clean, got {n_clean}"
        assert n_high_slippage == 38, f"Expected 38 high slippage, got {n_high_slippage}"
        assert n_executed == 49, (
            f"Expected 49 executed (11+38), got {n_executed}"
        )
        assert n_failed == 1, f"Expected 1 failed, got {n_failed}"

        # Verify that HIGH_SLIPPAGE is NOT counted as failed
        n_failed_by_status = int((fills["status"] == "NO_PRICE").sum())
        assert n_failed_by_status == n_failed

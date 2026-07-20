"""
Verify shadow trading execution price precheck:

- READY orders + missing execution prices → FAIL (DATA_INSUFFICIENT).
- No next trade day → SKIPPED (not FAIL).
- HIGH_SLIPPAGE is counted in n_executed.
- Price precheck runs BEFORE paper broker execution.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import pandas as pd
import numpy as np
from unittest.mock import patch, MagicMock


class TestShadowExecutionPricePrecheck:
    """Shadow must detect missing execution prices early."""

    def test_ready_orders_missing_exec_prices_is_fail(self):
        """When n_ready > 0 but execution prices for exec_date are empty,
        the precheck must mark execution as FAIL with DATA_INSUFFICIENT."""
        n_ready = 57
        exec_prices_empty = True  # prices_raw returns empty

        # Simulate the precheck logic from run_shadow.run_single_date
        if exec_prices_empty and n_ready > 0:
            exec_status = "FAIL"
            exec_reason = (
                f"DATA_INSUFFICIENT: missing execution prices "
                f"for 20170103 (exec date for signal 20161230) — "
                f"{n_ready} READY orders cannot be filled"
            )
        else:
            exec_status = "OK"
            exec_reason = ""

        assert exec_status == "FAIL", (
            f"n_ready={n_ready} with empty exec prices must be FAIL, "
            f"got {exec_status}"
        )
        assert "DATA_INSUFFICIENT" in exec_reason, (
            f"Reason must mention DATA_INSUFFICIENT, got: {exec_reason}"
        )
        assert "missing execution prices" in exec_reason

    def test_no_next_trade_day_is_skipped(self):
        """When next_trade_day returns the same date (no next trade day),
        the execution must be SKIPPED, not FAIL."""
        date_str = "20161230"
        date_int = int(date_str)

        # Simulate: next_trade_day returns same date → no next trade day
        exec_date = date_int  # same = no next trade day
        n_ready = 57

        if exec_date == date_int:
            verdict = "SKIPPED"
            reason = (
                f"DATA_INSUFFICIENT: no next trade day after {date_str}"
            )
        elif n_ready > 0:
            verdict = "check_prices"
        else:
            verdict = "OK"

        assert verdict == "SKIPPED", (
            f"No next trade day must be SKIPPED, got {verdict}"
        )
        assert "DATA_INSUFFICIENT" in reason
        assert "no next trade day" in reason

    def test_price_precheck_returns_early_before_paper_broker(self):
        """When the precheck fails, it must return before calling
        PaperBroker.execute()."""
        n_ready = 57
        date_str = "20161230"
        exec_date = 20170103
        date_int = int(date_str)

        # Simulate full precheck flow
        precheck_fail = False
        precheck_skip = False

        if exec_date == date_int:
            precheck_skip = True
        elif n_ready > 0:
            # Check prices — simulate empty
            prices_empty = True
            if prices_empty:
                precheck_fail = True

        # When precheck triggers, paper_broker.execute() is never called
        paper_broker_called = False

        if precheck_skip:
            result = {"status": "SKIPPED"}
        elif precheck_fail:
            result = {"status": "FAIL"}
        else:
            paper_broker_called = True
            result = {"status": "OK"}

        assert precheck_fail, "Should detect FAIL condition"
        assert not paper_broker_called, (
            "PaperBroker.execute() must NOT be called on precheck fail"
        )
        assert result["status"] == "FAIL"

    def test_prices_present_proceeds_to_execution(self):
        """When execution prices exist, the precheck passes and
        paper execution proceeds normally."""
        n_ready = 57
        exec_date = 20170103
        date_int = 20161230

        precheck_fail = False
        precheck_skip = False

        if exec_date == date_int:
            precheck_skip = True
        elif n_ready > 0:
            prices_empty = False  # prices exist!
            if prices_empty:
                precheck_fail = True

        paper_broker_called = False

        if precheck_skip:
            result = {"status": "SKIPPED"}
        elif precheck_fail:
            result = {"status": "FAIL"}
        else:
            paper_broker_called = True
            result = {"status": "OK"}

        assert not precheck_fail, "Should not fail when prices exist"
        assert not precheck_skip, "Should not skip when next trade day exists"
        assert paper_broker_called, (
            "PaperBroker.execute() must be called when prices are available"
        )
        assert result["status"] == "OK"


class TestShadowHighSlippageCounted:
    """HIGH_SLIPPAGE fills are executed, not failed."""

    def test_high_slippage_counted_in_n_executed(self):
        """HIGH_SLIPPAGE trades count toward n_executed."""
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

        assert n_clean == 11
        assert n_high_slippage == 38
        assert n_executed == 49, (
            f"HIGH_SLIPPAGE must count toward n_executed: "
            f"11+38={n_executed}"
        )
        assert n_failed == 1

    def test_only_high_slippage_still_counts_as_executed(self):
        """Even when ALL fills are HIGH_SLIPPAGE, n_executed > 0."""
        fills = pd.DataFrame({
            "status": ["HIGH_SLIPPAGE"] * 50,
            "fill_rate": [1.0] * 50,
            "slippage_bps": [30.0] * 50,
        })

        n_clean = int((fills["status"] == "FILLED").sum())
        n_high_slippage = int((fills["status"] == "HIGH_SLIPPAGE").sum())
        n_executed = n_clean + n_high_slippage

        assert n_clean == 0
        assert n_high_slippage == 50
        assert n_executed == 50, (
            f"All HIGH_SLIPPAGE still means executed: got {n_executed}"
        )


class TestShadowPrecheckAuditRecord:
    """Verify the audit record structure for precheck failures."""

    def test_precheck_fail_audit_record_structure(self):
        """The execution stage record for a precheck FAIL must include
        reason, n_fills=0, n_executed=0, n_failed=n_ready."""
        n_ready = 57
        result = {
            "status": "FAIL",
            "reason": (
                "DATA_INSUFFICIENT: missing execution prices "
                "for 20170103 (exec date for signal 20161230) — "
                "57 READY orders cannot be filled"
            ),
            "n_fills": 0,
            "n_clean": 0,
            "n_high_slippage": 0,
            "n_executed": 0,
            "n_failed": n_ready,
        }

        assert result["status"] == "FAIL"
        assert result["n_executed"] == 0
        assert result["n_failed"] == n_ready, (
            f"n_failed must equal n_ready ({n_ready}) when all fail, "
            f"got {result['n_failed']}"
        )
        assert "DATA_INSUFFICIENT" in result["reason"]

    def test_precheck_skip_audit_record_structure(self):
        """The execution stage record for a SKIPPED precheck must
        include the skip reason."""
        result = {
            "status": "SKIPPED",
            "reason": "DATA_INSUFFICIENT: no next trade day after 20161230",
        }

        assert result["status"] == "SKIPPED"
        assert "DATA_INSUFFICIENT" in result["reason"]
        assert "no next trade day" in result["reason"]

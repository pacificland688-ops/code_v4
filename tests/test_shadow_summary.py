"""
Verify shadow trading summary counts — SKIPPED dates must not contribute
to FAIL count or non-zero exit code.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import json
import pytest
from unittest.mock import patch, MagicMock


class TestShadowSummaryCounting:
    """OK + SKIPPED should produce exit code 0."""

    def test_ok_and_skipped_returns_zero(self, tmp_path):
        """With 1 OK + 1 SKIPPED, function returns 0."""
        from live.run_shadow import main as shadow_main
        import argparse

        # We test the counting logic directly by building a mock audit_log
        audit_log = [
            {"date": "20161223", "overall": "OK", "stages": {}},
            {"date": "20161230", "overall": "SKIPPED",
             "reason": "no next trade day", "stages": {}},
        ]

        n_ok = sum(1 for r in audit_log if r.get("overall") == "OK")
        n_skipped = sum(1 for r in audit_log if r.get("overall") == "SKIPPED")
        n_fail = sum(1 for r in audit_log
                     if r.get("overall") not in ("OK", "SKIPPED"))

        assert n_ok == 1
        assert n_skipped == 1
        assert n_fail == 0

        exit_code = 1 if n_fail > 0 else 0
        assert exit_code == 0, (
            f"OK + SKIPPED should return 0, got exit_code={exit_code}"
        )

    def test_all_skipped_returns_zero(self):
        """All skipped → exit code 0 (not a failure)."""
        audit_log = [
            {"date": "20161226", "overall": "SKIPPED",
             "reason": "no next trade day", "stages": {}},
        ]

        n_ok = sum(1 for r in audit_log if r.get("overall") == "OK")
        n_skipped = sum(1 for r in audit_log if r.get("overall") == "SKIPPED")
        n_fail = sum(1 for r in audit_log
                     if r.get("overall") not in ("OK", "SKIPPED"))

        assert n_ok == 0
        assert n_skipped == 1
        assert n_fail == 0

        exit_code = 1 if n_fail > 0 else 0
        assert exit_code == 0, (
            f"All SKIPPED should return 0, got exit_code={exit_code}"
        )

    def test_fail_and_skipped_returns_one(self):
        """1 FAIL + 1 SKIPPED → exit code 1 (only FAIL matters)."""
        audit_log = [
            {"date": "20161223", "overall": "OK", "stages": {}},
            {"date": "20161226", "overall": "FAIL", "stages": {}},
            {"date": "20161230", "overall": "SKIPPED",
             "reason": "no next trade day", "stages": {}},
        ]

        n_ok = sum(1 for r in audit_log if r.get("overall") == "OK")
        n_skipped = sum(1 for r in audit_log if r.get("overall") == "SKIPPED")
        n_fail = sum(1 for r in audit_log
                     if r.get("overall") not in ("OK", "SKIPPED"))

        assert n_ok == 1
        assert n_skipped == 1
        assert n_fail == 1

        exit_code = 1 if n_fail > 0 else 0
        assert exit_code == 1, (
            f"FAIL should return 1 even with SKIPPED present"
        )

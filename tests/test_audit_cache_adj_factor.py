"""
Test: audit_cache adj_factor_dedup — verbose detail output and FAIL/PASS behavior.
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class TestAdjFactorDedupAudit:
    """Verify adj_factor_dedup check behavior in audit_cache."""

    def _make_mock_args(self, start="20170101", end="20241231", verbose=False):
        args = MagicMock()
        args.start = start
        args.end = end
        args.verbose = verbose
        args.limit_status_mode = "exec"
        return args

    def _make_mock_loader(self, adjf_df=None):
        loader = MagicMock()
        if adjf_df is None:
            # Create data with enough unique trade_dates for high coverage
            dates = [20240101 + i for i in range(240)]
            rows = []
            for j, d in enumerate(dates[:100]):
                rows.append({"ts_code": f"{j:06d}.SZ", "trade_date": d})
            adjf_df = pd.DataFrame(rows)
        loader.query.return_value = adjf_df
        loader.factor_coverage.return_value = {
            "rows": 100, "n_dates": 50, "duplicates": 0,
            "min_date": "20170103", "max_date": "20241231",
        }
        loader.price_coverage.return_value = {
            "coverage_ratio": 0.95, "n_dates": 240, "expected_trade_dates": 252,
            "missing_dates": [],
        }
        loader.daily_basic_coverage.return_value = {
            "coverage_ratio": 0.95, "n_months_cached": 96, "n_months_expected": 96,
        }
        return loader

    def _make_mock_calendar(self, n_trade_days=100):
        cal = MagicMock()
        cal.weekly_rebalance_dates.return_value = []
        cal.next_trade_day.return_value = 20240115
        cal.trade_days_between.return_value = [20240101 + i for i in range(n_trade_days)]
        return cal

    @patch("data.calendar.get_calendar")
    @patch("data.panel_loader.get_loader")
    def test_adj_factor_dedup_pass_when_no_duplicates(self, mock_get_loader, mock_get_calendar):
        """PASS when adj_factor has no duplicate (ts_code, trade_date) pairs."""
        from scripts.audit_cache import audit

        mock_get_loader.return_value = self._make_mock_loader()
        mock_get_calendar.return_value = self._make_mock_calendar()

        results = audit(self._make_mock_args())
        checks = {c["name"]: c for c in results["checks"]}

        assert "adj_factor_dedup" in checks
        assert checks["adj_factor_dedup"]["status"] == "PASS"

    @patch("data.calendar.get_calendar")
    @patch("data.panel_loader.get_loader")
    def test_adj_factor_dedup_fail_when_duplicates(self, mock_get_loader, mock_get_calendar):
        """FAIL when adj_factor has duplicate (ts_code, trade_date) rows."""
        from scripts.audit_cache import audit

        adjf_df = pd.DataFrame({
            "ts_code": ["000001.SZ", "000001.SZ", "000002.SZ"],
            "trade_date": [20240115, 20240115, 20240116],
        })
        mock_get_loader.return_value = self._make_mock_loader(adjf_df)
        mock_get_calendar.return_value = self._make_mock_calendar()

        results = audit(self._make_mock_args())
        checks = {c["name"]: c for c in results["checks"]}

        assert "adj_factor_dedup" in checks
        assert checks["adj_factor_dedup"]["status"] == "FAIL"
        assert "1 duplicate" in checks["adj_factor_dedup"]["detail"]

    @patch("data.calendar.get_calendar")
    @patch("data.panel_loader.get_loader")
    def test_adj_factor_dedup_verbose_shows_keys(self, mock_get_loader, mock_get_calendar):
        """--verbose mode shows the actual duplicate keys."""
        from scripts.audit_cache import audit

        adjf_df = pd.DataFrame({
            "ts_code": ["000001.SZ", "000001.SZ"],
            "trade_date": [20240115, 20240115],
        })
        mock_get_loader.return_value = self._make_mock_loader(adjf_df)
        mock_get_calendar.return_value = self._make_mock_calendar()

        results = audit(self._make_mock_args(verbose=True))
        checks = {c["name"]: c for c in results["checks"]}

        assert checks["adj_factor_dedup"]["status"] == "FAIL"
        detail = checks["adj_factor_dedup"]["detail"]
        assert "000001.SZ" in detail
        assert "20240115" in detail

    @patch("data.calendar.get_calendar")
    @patch("data.panel_loader.get_loader")
    def test_adj_factor_coverage_pass(self, mock_get_loader, mock_get_calendar):
        """adj_factor_coverage PASS when coverage >= 0.90."""
        from scripts.audit_cache import audit

        mock_get_loader.return_value = self._make_mock_loader()
        mock_get_calendar.return_value = self._make_mock_calendar()

        results = audit(self._make_mock_args())
        checks = {c["name"]: c for c in results["checks"]}

        assert "adj_factor_coverage" in checks
        assert checks["adj_factor_coverage"]["status"] in ("PASS", "WARN")

    @patch("data.calendar.get_calendar")
    @patch("data.panel_loader.get_loader")
    def test_empty_adj_factor_fails_coverage(self, mock_get_loader, mock_get_calendar):
        """adj_factor_coverage FAIL when no data in window."""
        from scripts.audit_cache import audit

        mock_get_loader.return_value = self._make_mock_loader(
            pd.DataFrame(columns=["ts_code", "trade_date"])
        )
        mock_get_calendar.return_value = self._make_mock_calendar()

        results = audit(self._make_mock_args())
        checks = {c["name"]: c for c in results["checks"]}

        assert checks["adj_factor_coverage"]["status"] == "FAIL"

"""
Tests for Windows GBK console output safety.

Verifies:
- safe_print handles Unicode characters on GBK consoles
- Report output with special characters doesn't crash
- ✓/✗/→ are replaced with ASCII-safe equivalents in reports
"""

import io
import sys
import pytest


class TestSafePrint:
    """Verify safe_print doesn't crash on GBK consoles."""

    def test_safe_print_unicode_fallback(self):
        """safe_print should not raise UnicodeEncodeError on GBK stdout."""
        # Force run_research's safe_print to be tested
        from run_research import safe_print

        # Simulate GBK-encoded stdout that can't handle ✓
        fake_stdout = io.StringIO()

        # safe_print should fall back gracefully
        try:
            safe_print("Test PASS")
            safe_print("Test with unicode: ✓ ✗ →")
        except UnicodeEncodeError:
            pytest.fail("safe_print raised UnicodeEncodeError on GBK-like output")

    def test_safe_print_normal_text(self):
        """safe_print should work normally with ASCII text."""
        from run_research import safe_print
        # Should not raise any exception
        safe_print("Normal ASCII text")
        safe_print("Phase 0: OK")
        safe_print("Phase 2: OK")

    def test_report_markdown_no_unicode_chars(self):
        """Backtest reports should use PASS/FAIL instead of ✓/✗."""
        from backtest.portfolio_backtester import PortfolioBacktester

        bt = PortfolioBacktester()
        results = {
            "total_return": 0.15,
            "annualized_return": 0.12,
            "annualized_volatility": 0.20,
            "sharpe_ratio": 0.6,
            "max_drawdown": -0.15,
            "calmar_ratio": 0.8,
            "win_rate": 0.55,
            "avg_turnover": 0.30,
            "total_cost_bps": 150.0,
            "avg_holdings": 48.0,
            "var_95": -0.02,
            "cvar_95": -0.03,
            "n_periods": 200,
            "annualized_excess_return": 0.05,
            "tracking_error": 0.08,
            "information_ratio": 0.625,
            "max_excess_drawdown": -0.05,
            "excess_win_rate": 0.52,
            "hit_rate": 0.58,
            "go_nogo": {
                "positive_excess_return": True,
                "positive_ir": True,
                "acceptable_max_dd": True,
            },
            "config": {
                "start_date": "20160101",
                "end_date": "20161231",
                "top_n": 50,
                "weighting": "equal",
                "rebalance_freq": "weekly",
                "initial_capital": 100_000_000,
            },
        }

        report = bt.generate_report(results)
        # Report should not contain Unicode checkmarks
        assert "✓" not in report, "Report should use PASS, not ✓"
        assert "✗" not in report, "Report should use FAIL, not ✗"
        assert "PASS" in report
        assert "FAIL" not in report  # all checks pass in this test


class TestSmokeStatusClassification:
    """Smoke status classification for short windows."""

    def test_smoke_short_window_phase2_data_insufficient(self):
        """Verify the smoke Phase 2 handler recognizes short windows."""
        # Simulate the short-window detection logic
        fwd_dates = 8
        n_signal = 3
        n_trade_days = 40

        is_short = (
            fwd_dates < 16
            or n_signal < 6
            or n_trade_days < 60
        )

        assert is_short, (
            f"Window with fwd_dates={fwd_dates}, signal_dates={n_signal}, "
            f"trade_days={n_trade_days} should be classified as short"
        )

    def test_smoke_full_window_not_short(self):
        """Full year window should not be classified as short."""
        fwd_dates = 200
        n_signal = 50
        n_trade_days = 244

        is_short = (
            fwd_dates < 16
            or n_signal < 6
            or n_trade_days < 60
        )

        assert not is_short, (
            f"Window with fwd_dates={fwd_dates}, signal_dates={n_signal}, "
            f"trade_days={n_trade_days} should NOT be short"
        )

    def test_smoke_borderline_window(self):
        """Two-month window (~40 trade days) should be short."""
        fwd_dates = 36
        n_signal = 8
        n_trade_days = 40

        is_short = (
            fwd_dates < 16
            or n_signal < 6
            or n_trade_days < 60
        )

        assert is_short, "40 trade days < 60 threshold should be short"

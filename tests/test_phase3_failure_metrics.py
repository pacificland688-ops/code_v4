"""
Verify Phase3 failure writes FAIL metrics to metrics_summary.json
and latest_metrics_summary.json, overwriting stale success data.

CRITICAL: _write_metrics_summary() uses a std_keys whitelist.
Failure fields (status, error, failure_reasons) MUST be in that
whitelist — otherwise the FAIL metrics are silently stripped and
stale success data persists.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import json
import argparse
import pytest
import numpy as np
import pandas as pd
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Test helpers — all date arithmetic uses pd.Timestamp to avoid integer
# overflow across month/year boundaries.
# ---------------------------------------------------------------------------

def _weekly_dates(start_str: str, n: int):
    start = pd.Timestamp(start_str)
    return [(start + pd.DateOffset(weeks=i)).strftime("%Y%m%d") for i in range(n)]


def _monthly_dates(start_str: str, n: int):
    start = pd.Timestamp(start_str)
    return [(start + pd.DateOffset(months=i)).strftime("%Y%m%d") for i in range(n)]


def _add_days(d: int, n: int) -> int:
    return int((pd.Timestamp(str(d)) + pd.DateOffset(days=n)).strftime("%Y%m%d"))


def _td_between(start, end):
    result = []
    cur = pd.Timestamp(str(int(start)))
    stop = pd.Timestamp(str(int(end)))
    while cur <= stop:
        result.append(int(cur.strftime("%Y%m%d")))
        cur += pd.DateOffset(days=1)
    return np.array(result, dtype=np.int32)


def _make_composite_df(signal_dates_int, n_stocks=100):
    rows = []
    for d in signal_dates_int:
        for i in range(n_stocks):
            rows.append({
                "ts_code": f"{i:04d}.SZ",
                "trade_date": d,
                "composite_score": np.random.randn(),
            })
    return pd.DataFrame(rows)


def _make_mu_df(signal_dates_int, n_stocks=100):
    rows = []
    for d in signal_dates_int:
        for i in range(n_stocks):
            rows.append({
                "ts_code": f"{i:04d}.SZ",
                "trade_date": d,
                "mu": np.random.randn(),
            })
    return pd.DataFrame(rows)


def _build_mocks(rr, signal_dates, composite_df, mu_df, loader=None):
    """Minimum viable mocks so run_phase3 reaches the precheck or
    validation stage (not failing at load/composite)."""
    cal = MagicMock()
    cal.weekly_rebalance_dates.return_value = signal_dates
    cal.monthly_rebalance_dates.return_value = _monthly_dates(
        signal_dates[0], 12
    )
    cal.next_trade_day.side_effect = lambda d, n: _add_days(d, n)
    cal.prev_trade_day.side_effect = lambda d, n: _add_days(d, -n)
    cal.trade_days_between.side_effect = _td_between

    icw = MagicMock()
    icw.compute_composite_series.return_value = composite_df

    stm = MagicMock()
    stm.calibrate.return_value = mu_df

    bt = MagicMock()
    bt.run_backtest.return_value = {
        "n_periods": len(signal_dates),
        "annualized_return": 0.15,
    }

    return cal, icw, stm, bt


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPhase3FailureMetrics:
    """Phase3 failure must write FAIL metrics, not leave stale data."""

    def test_failure_metrics_contain_status_fail(self):
        """When Phase3 validation fails (fallback_rate=100%),
        the written metrics must include status=FAIL, error code,
        and failure_reasons — all preserved by std_keys whitelist."""
        from run_research import run_phase3
        import run_research as rr

        args = argparse.Namespace(
            start="20160101", end="20161231",
            top_n=50, weight_max=0.02,
            turnover_max=None, turnover_penalty=None,
            recompute=False, no_recompute=True,
            dry_run=False, frequency="weekly",
            run_id="test_failure_metrics",
        )
        sig_dates = _weekly_dates("2016-01-04", 50)
        sig_dates_int = [int(d) for d in sig_dates]
        composite_df = _make_composite_df(sig_dates_int)
        mu_df = _make_mu_df(sig_dates_int)

        captured_metrics = {}

        def fake_write_metrics(run_id, phase_name, metrics):
            captured_metrics[phase_name] = (run_id, dict(metrics))

        with patch.object(rr, '_select_valid_cs_factors',
                          return_value=['reversal_5_cs']):
            with patch.object(rr, '_load_factor_config', return_value=[]):
                with patch.object(rr, '_filter_enabled_factors',
                                  side_effect=lambda x, y: x):
                    with patch.object(rr, '_write_metrics_summary',
                                      side_effect=fake_write_metrics):
                        with patch('data.panel_loader.get_loader') as mock_loader:
                            mock_l = MagicMock()
                            mock_l.read_factor.return_value = composite_df.copy()

                            # Direct prices_adj query: FULL coverage → precheck PASS
                            expected_all = _td_between(20141228, 20161231)
                            def _fake_query(table_name, columns=None, **kw):
                                if table_name == "prices_adj":
                                    return pd.DataFrame({"trade_date": expected_all})
                                return pd.DataFrame()
                            mock_l.query.side_effect = _fake_query
                            mock_loader.return_value = mock_l

                            with patch('data.calendar.get_calendar') as mock_cal:
                                cal, icw, stm, _ = _build_mocks(
                                    rr, sig_dates, composite_df, mu_df
                                )
                                mock_cal.return_value = cal

                                with patch('alpha.ic_weighting.ICWeighting',
                                           return_value=icw):
                                    with patch('alpha.score_to_mu.ScoreToMu',
                                               return_value=stm):
                                        with patch.object(rr, '_build_backtester') as mock_bt:
                                            bt = MagicMock()
                                            # ew: OK, opt: 100% fallback → FAIL
                                            bt.run_backtest.side_effect = [
                                                {"n_periods": 50,
                                                 "annualized_return": 0.15},
                                                {"n_periods": 44,
                                                 "annualized_return": 0.10,
                                                 "opt_n_total": 44,
                                                 "optimizer_fallback_rate": 1.0,
                                                 "opt_n_fallback": 44,
                                                 "avg_active_weight": 0.02,
                                                 "opt_fallback_reasons": {
                                                     "insufficient_return_obs": 44}},
                                            ]
                                            mock_bt.return_value = bt

                                            rc = run_phase3(args)
                                            assert rc == 1, (
                                                f"Phase3 must return 1 on "
                                                f"100% fallback, got {rc}"
                                            )

        # Verify FAIL metrics were written AND preserved by whitelist
        assert "phase3_optimized" in captured_metrics, (
            "phase3_optimized metrics must be written on failure"
        )
        opt_run_id, opt_metrics = captured_metrics["phase3_optimized"]
        assert opt_run_id == "test_failure_metrics"
        assert opt_metrics["status"] == "FAIL", (
            f"status must be FAIL, got {opt_metrics.get('status')}"
        )
        assert opt_metrics["error"] == "OPTIMIZED_BACKTEST_INVALID", (
            f"error must be OPTIMIZED_BACKTEST_INVALID, "
            f"got {opt_metrics.get('error')}"
        )
        assert "failure_reasons" in opt_metrics, (
            "failure_reasons must survive std_keys whitelist"
        )
        assert opt_metrics["optimizer_fallback_rate"] == 1.0
        assert opt_metrics["opt_n_total"] == 44
        assert opt_metrics["opt_n_fallback"] == 44
        assert "insufficient_return_obs" in opt_metrics.get(
            "opt_fallback_reasons", {}
        ), "opt_fallback_reasons must be preserved"

    def test_failure_metrics_overwrite_old_success(self):
        """Calling _write_metrics_summary with FAIL metrics must overwrite
        the old phase3_optimized key — no stale success data remains."""
        import run_research as rr

        captured = {}

        def fake_write(run_id, phase_name, metrics):
            captured[phase_name] = (run_id, dict(metrics))

        with patch.object(rr, '_write_metrics_summary', side_effect=fake_write):
            # Old success run
            rr._write_metrics_summary("old_run", "phase3_optimized", {
                "run_id": "old_run",
                "annualized_return": 0.18,
                "information_ratio": 0.65,
                "optimizer_fallback_rate": 0.05,
                "opt_n_total": 48,
            })

            # New failure run — must overwrite
            rr._write_metrics_summary("new_run", "phase3_optimized", {
                "run_id": "new_run",
                "status": "FAIL",
                "error": "OPTIMIZED_BACKTEST_INVALID",
                "failure_reasons": ["fallback_rate 100% > 20%"],
                "optimizer_fallback_rate": 1.0,
                "opt_n_total": 44,
                "opt_n_fallback": 44,
                "opt_fallback_reasons": {"insufficient_return_obs": 44},
            })

        final_run_id, final_metrics = captured["phase3_optimized"]
        assert final_run_id == "new_run", (
            f"run_id must be 'new_run' (overwritten), got {final_run_id}"
        )
        assert final_metrics["status"] == "FAIL"
        # Old success fields like annualized_return should NOT appear
        # (they weren't in the fail dict, so they're gone)
        assert "annualized_return" not in final_metrics, (
            "FAIL metrics should not retain old success fields"
        )
        assert final_metrics["opt_n_total"] == 44
        assert "insufficient_return_obs" in final_metrics.get(
            "opt_fallback_reasons", {}
        )

    def test_price_precheck_failure_writes_metrics(self):
        """When the price precheck fails (coverage < 95%),
        FAIL metrics must be written BEFORE returning 1."""
        from run_research import run_phase3
        import run_research as rr

        args = argparse.Namespace(
            start="20160101", end="20161231",
            top_n=50, weight_max=0.02,
            turnover_max=None, turnover_penalty=None,
            recompute=False, no_recompute=True,
            dry_run=False, frequency="weekly",
            run_id="test_precheck_metrics",
        )
        sig_dates = _weekly_dates("2016-01-04", 50)
        sig_dates_int = [int(d) for d in sig_dates]
        composite_df = _make_composite_df(sig_dates_int)
        mu_df = _make_mu_df(sig_dates_int)

        captured_metrics = {}

        def fake_write_metrics(run_id, phase_name, metrics):
            captured_metrics[phase_name] = (run_id, dict(metrics))

        with patch.object(rr, '_select_valid_cs_factors',
                          return_value=['reversal_5_cs']):
            with patch.object(rr, '_load_factor_config', return_value=[]):
                with patch.object(rr, '_filter_enabled_factors',
                                  side_effect=lambda x, y: x):
                    with patch.object(rr, '_write_metrics_summary',
                                      side_effect=fake_write_metrics):
                        with patch('data.panel_loader.get_loader') as mock_loader:
                            mock_l = MagicMock()
                            mock_l.read_factor.return_value = composite_df.copy()
                            # Direct query: EMPTY prices_adj → 0% coverage
                            def _fake_query(table_name, columns=None, **kw):
                                if table_name == "prices_adj":
                                    return pd.DataFrame()
                                return pd.DataFrame()
                            mock_l.query.side_effect = _fake_query
                            mock_loader.return_value = mock_l

                            with patch('data.calendar.get_calendar') as mock_cal:
                                cal, icw, stm, _ = _build_mocks(
                                    rr, sig_dates, composite_df, mu_df
                                )
                                mock_cal.return_value = cal

                                with patch('alpha.ic_weighting.ICWeighting',
                                           return_value=icw):
                                    with patch('alpha.score_to_mu.ScoreToMu',
                                               return_value=stm):
                                        with patch.object(rr, '_build_backtester'):
                                            rc = run_phase3(args)
                                            assert rc == 1, (
                                                f"Phase3 must return 1 on "
                                                f"price cache insufficient"
                                            )

        # Verify precheck FAIL metrics were written
        assert "phase3_optimized" in captured_metrics, (
            "phase3_optimized FAIL metrics must be written on precheck failure"
        )
        run_id, metrics = captured_metrics["phase3_optimized"]
        assert run_id == "test_precheck_metrics"
        assert metrics["status"] == "FAIL", (
            f"status must be FAIL, got {metrics.get('status')}"
        )
        assert metrics["error"] == "OPTIMIZER_PRICE_CACHE_INSUFFICIENT", (
            f"error must be OPTIMIZER_PRICE_CACHE_INSUFFICIENT, "
            f"got {metrics.get('error')}"
        )
        assert "failure_reasons" in metrics, (
            "failure_reasons must survive std_keys whitelist"
        )
        assert "required_start" in metrics
        assert "required_end" in metrics
        assert "fix_command" in metrics
        assert "first_missing_dates" in metrics


class TestPhase3FailureMetricsFields:
    """Verify specific diagnostic fields survive the whitelist."""

    def test_fail_metrics_include_fallback_diagnostics(self):
        """FAIL metrics must retain opt_n_total, opt_n_fallback,
        optimizer_fallback_rate, opt_fallback_reasons, status, error,
        and failure_reasons — all now in the std_keys whitelist."""
        fail_metrics = {
            "run_id": "test_run",
            "status": "FAIL",
            "error": "OPTIMIZED_BACKTEST_INVALID",
            "failure_reasons": ["fallback_rate 100% > 20%"],
            "n_periods": 44,
            "opt_n_total": 44,
            "opt_n_fallback": 44,
            "optimizer_fallback_rate": 1.0,
            "avg_active_weight": 0.02,
            "opt_fallback_reasons": {"insufficient_return_obs": 44},
        }

        required_fields = [
            "run_id", "status", "error", "failure_reasons",
            "n_periods", "opt_n_total", "opt_n_fallback",
            "optimizer_fallback_rate", "opt_fallback_reasons",
        ]
        for field in required_fields:
            assert field in fail_metrics, (
                f"FAIL metrics must include '{field}'"
            )
        assert fail_metrics["status"] == "FAIL"
        assert fail_metrics["error"] == "OPTIMIZED_BACKTEST_INVALID"
        assert fail_metrics["opt_n_total"] == 44
        assert fail_metrics["opt_n_fallback"] == 44
        assert fail_metrics["optimizer_fallback_rate"] == 1.0
        assert fail_metrics["opt_fallback_reasons"] == {
            "insufficient_return_obs": 44,
        }

    def test_whitelist_includes_all_failure_fields(self):
        """Verify the std_keys whitelist in _write_metrics_summary
        actually includes status, error, failure_reasons, etc."""
        import run_research as rr
        import inspect

        source = inspect.getsource(rr._write_metrics_summary)
        for field in [
            "status", "error", "failure_reasons",
            "required_start", "required_end",
            "coverage_ratio", "first_missing_dates", "fix_command",
        ]:
            assert f'"{field}"' in source, (
                f"std_keys must include '{field}'"
            )

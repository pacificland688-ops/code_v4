"""
Verify Phase3 price precheck correctly rejects insufficient data.

Key invariant: candidate dates MUST come from composite.trade_date,
NOT from the first weekly signal date.  The precheck computes
required_start = min(lookback_starts) across ALL real candidates.

- Only 2016 prices (no 2015 lookback) → precheck must FAIL.
- Coverage ratio < 95% → precheck must FAIL.
- Missing dates > 5 → precheck must FAIL.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import argparse
import pytest
import numpy as np
import pandas as pd
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Test helpers — all date arithmetic uses pd.Timestamp to avoid integer
# overflow across month/year boundaries (e.g. 20160104 + 28 = 20160132).
# ---------------------------------------------------------------------------

def _weekly_dates(start_str: str, n: int):
    """Generate n weekly YYYYMMDD strings from start_str."""
    start = pd.Timestamp(start_str)
    return [(start + pd.DateOffset(weeks=i)).strftime("%Y%m%d") for i in range(n)]


def _monthly_dates(start_str: str, n: int):
    """Generate n monthly YYYYMMDD strings from start_str."""
    start = pd.Timestamp(start_str)
    return [(start + pd.DateOffset(months=i)).strftime("%Y%m%d") for i in range(n)]


def _add_days(d: int, n: int) -> int:
    """Add n calendar days to YYYYMMDD int, returning YYYYMMDD int."""
    return int((pd.Timestamp(str(d)) + pd.DateOffset(days=n)).strftime("%Y%m%d"))


def _td_between(start, end):
    """Generate every calendar day in [start, end] as int32 array."""
    result = []
    cur = pd.Timestamp(str(int(start)))
    stop = pd.Timestamp(str(int(end)))
    while cur <= stop:
        result.append(int(cur.strftime("%Y%m%d")))
        cur += pd.DateOffset(days=1)
    return np.array(result, dtype=np.int32)


def _make_composite_df(signal_dates_int, n_stocks=100):
    """Build a realistic composite DataFrame whose trade_date values
    overlap candidate_dates with the weekly rebalance schedule."""
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
    """Build a realistic mu_df for ScoreToMu.calibrate()."""
    rows = []
    for d in signal_dates_int:
        for i in range(n_stocks):
            rows.append({
                "ts_code": f"{i:04d}.SZ",
                "trade_date": d,
                "mu": np.random.randn(),
            })
    return pd.DataFrame(rows)


def _build_base_mocks(rr, signal_dates, composite_df, mu_df, loader=None):
    """Set up the minimum viable mock stack so run_phase3 reaches
    the price precheck against real composite dates."""
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
        "information_ratio": 0.5,
    }

    return cal, icw, stm, bt


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPhase3PricePrecheck:
    """Phase3 must fail when prices_adj lookup is insufficient for the
    REAL candidate optimization dates (from composite, not first signal)."""

    def _make_fake_args(self):
        return argparse.Namespace(
            start="20160101", end="20161231",
            top_n=100, weight_max=0.02,
            turnover_max=0.30, turnover_penalty=0.005,
            recompute=False, no_recompute=True,
            dry_run=False, frequency="weekly",
            run_id="test_price_precheck",
        )

    def test_only_2016_prices_precheck_fails(self):
        """When prices_adj only has 2016 data (min_date=20160104),
        required_start falls in 2015, coverage << 95% → FAIL."""
        from run_research import run_phase3
        import run_research as rr

        args = self._make_fake_args()
        sig_dates = _weekly_dates("2016-01-04", 50)
        sig_dates_int = [int(d) for d in sig_dates]
        composite_df = _make_composite_df(sig_dates_int)
        mu_df = _make_mu_df(sig_dates_int)

        with patch.object(rr, '_select_valid_cs_factors',
                          return_value=['reversal_5_cs']):
            with patch.object(rr, '_load_factor_config', return_value=[]):
                with patch.object(rr, '_filter_enabled_factors',
                                  side_effect=lambda x, y: x):
                    with patch('data.panel_loader.get_loader') as mock_loader:
                        mock_l = MagicMock()
                        mock_l.read_factor.return_value = composite_df.copy()

                        # prices_adj: min_date=20160104 (only 2016 data)
                        mock_l.price_coverage.return_value = {
                            "n_dates": 244,
                            "coverage_ratio": 0.96,
                            "min_date": 20160104,
                            "max_date": 20161230,
                            "expected_trade_dates": 255,
                            "missing_dates": [],
                        }
                        # KEY: the DIRECT query must also reflect 2016-only data.
                        # The precheck now queries prices_adj directly, so we
                        # must mock query() (not just price_coverage()).
                        def _fake_query(table_name, columns=None,
                                        start_date=None, end_date=None,
                                        ts_codes=None, extra_where=None,
                                        order_by=None, limit=None):
                            if table_name == "prices_adj":
                                # Only return 2016 dates
                                dates = list(range(20160104, 20161231))
                                # Filter to requested range
                                if start_date:
                                    dates = [d for d in dates if d >= int(start_date)]
                                if end_date:
                                    dates = [d for d in dates if d <= int(end_date)]
                                return pd.DataFrame({"trade_date": dates})
                            return pd.DataFrame()
                        mock_l.query.side_effect = _fake_query
                        mock_loader.return_value = mock_l

                        with patch('data.calendar.get_calendar') as mock_cal:
                            cal, icw, stm, bt = _build_base_mocks(
                                rr, sig_dates, composite_df, mu_df
                            )
                            mock_cal.return_value = cal

                            with patch('alpha.ic_weighting.ICWeighting',
                                       return_value=icw):
                                with patch('alpha.score_to_mu.ScoreToMu',
                                           return_value=stm):
                                    with patch.object(rr, '_build_backtester',
                                                      return_value=bt):
                                        rc = run_phase3(args)
                                        assert rc == 1, (
                                            f"Phase3 must return 1 when only "
                                            f"2016 prices present, got {rc}"
                                        )

    def test_coverage_below_95pct_fails(self):
        """Coverage ratio 93% < 95% threshold → FAIL, even with
        n_dates=230 > 200 (the old threshold that was too lax)."""
        from run_research import run_phase3
        import run_research as rr

        args = self._make_fake_args()
        sig_dates = _weekly_dates("2016-01-04", 50)
        sig_dates_int = [int(d) for d in sig_dates]
        composite_df = _make_composite_df(sig_dates_int)
        mu_df = _make_mu_df(sig_dates_int)

        with patch.object(rr, '_select_valid_cs_factors',
                          return_value=['reversal_5_cs']):
            with patch.object(rr, '_load_factor_config', return_value=[]):
                with patch.object(rr, '_filter_enabled_factors',
                                  side_effect=lambda x, y: x):
                    with patch('data.panel_loader.get_loader') as mock_loader:
                        mock_l = MagicMock()
                        mock_l.read_factor.return_value = composite_df.copy()
                        mock_l.price_coverage.return_value = {
                            "n_dates": 230,
                            "coverage_ratio": 0.93,
                            "min_date": 20150301,
                            "max_date": 20161230,
                            "expected_trade_dates": 247,
                            "missing_dates": [],
                        }
                        # Direct query: only ~93% of expected
                        expected_all = _td_between(20141228, 20161230)
                        keep_count = int(len(expected_all) * 0.93)
                        actual = expected_all[:keep_count]
                        def _fake_query(table_name, columns=None, **kw):
                            if table_name == "prices_adj":
                                return pd.DataFrame({"trade_date": actual})
                            return pd.DataFrame()
                        mock_l.query.side_effect = _fake_query
                        mock_loader.return_value = mock_l

                        with patch('data.calendar.get_calendar') as mock_cal:
                            cal, icw, stm, bt = _build_base_mocks(
                                rr, sig_dates, composite_df, mu_df
                            )
                            mock_cal.return_value = cal

                            with patch('alpha.ic_weighting.ICWeighting',
                                       return_value=icw):
                                with patch('alpha.score_to_mu.ScoreToMu',
                                           return_value=stm):
                                    with patch.object(rr, '_build_backtester',
                                                      return_value=bt):
                                        rc = run_phase3(args)
                                        assert rc == 1, (
                                            f"Phase3 must return 1 when "
                                            f"coverage 93% < 95%, got {rc}"
                                        )


class TestPhase3PricePrecheckMissingDates:
    """Missing dates threshold enforcement."""

    def test_more_than_5_missing_dates_fails(self):
        """When missing_dates=6 > threshold 5, the precheck must FAIL."""
        from run_research import run_phase3
        import run_research as rr

        args = argparse.Namespace(
            start="20160101", end="20161231",
            top_n=50, weight_max=0.02,
            turnover_max=None, turnover_penalty=None,
            recompute=False, no_recompute=True,
            dry_run=False, frequency="weekly",
            run_id="test_missing_dates",
        )
        sig_dates = _weekly_dates("2016-01-04", 50)
        sig_dates_int = [int(d) for d in sig_dates]
        composite_df = _make_composite_df(sig_dates_int)
        mu_df = _make_mu_df(sig_dates_int)

        with patch.object(rr, '_select_valid_cs_factors',
                          return_value=['reversal_5_cs']):
            with patch.object(rr, '_load_factor_config', return_value=[]):
                with patch.object(rr, '_filter_enabled_factors',
                                  side_effect=lambda x, y: x):
                    with patch('data.panel_loader.get_loader') as mock_loader:
                        mock_l = MagicMock()
                        mock_l.read_factor.return_value = composite_df.copy()
                        mock_l.price_coverage.return_value = {
                            "n_dates": 239,
                            "coverage_ratio": 0.976,
                            "min_date": 20150105,
                            "max_date": 20161230,
                            "expected_trade_dates": 245,
                            "missing_dates": [],
                        }
                        # Direct query: missing exactly 6 dates
                        expected_all = _td_between(20141228, 20161230)
                        missing_6 = set(expected_all[:6].tolist())
                        actual = [d for d in expected_all if d not in missing_6]
                        def _fake_query(table_name, columns=None, **kw):
                            if table_name == "prices_adj":
                                return pd.DataFrame({"trade_date": actual})
                            return pd.DataFrame()
                        mock_l.query.side_effect = _fake_query
                        mock_loader.return_value = mock_l

                        with patch('data.calendar.get_calendar') as mock_cal:
                            cal, icw, stm, bt = _build_base_mocks(
                                rr, sig_dates, composite_df, mu_df
                            )
                            mock_cal.return_value = cal

                            with patch('alpha.ic_weighting.ICWeighting',
                                       return_value=icw):
                                with patch('alpha.score_to_mu.ScoreToMu',
                                           return_value=stm):
                                    with patch.object(rr, '_build_backtester',
                                                      return_value=bt):
                                        rc = run_phase3(args)
                                        assert rc == 1, (
                                            f"Phase3 must return 1 when "
                                            f"missing_dates=6 > threshold 5, "
                                            f"got {rc}"
                                        )

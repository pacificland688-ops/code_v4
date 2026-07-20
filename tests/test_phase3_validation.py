"""
Verify Phase3 hard validation — optimized backtest must fail non-zero
when results are invalid (error, insufficient periods, or opt_n_total=0).
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import argparse
import pytest
from unittest.mock import patch, MagicMock
import numpy as np
import pandas as pd


class TestPhase3HardValidation:
    """Phase3 must return non-zero when optimized backtest is invalid."""

    def _make_fake_args(self):
        """Build minimal args for Phase3."""
        return argparse.Namespace(
            start="20160101", end="20161231",
            top_n=50, weight_max=0.02,
            turnover_max=None, turnover_penalty=None,
            recompute=False, no_recompute=True,
            dry_run=False, frequency="weekly",
            run_id="test_phase3_validation",
        )

    def test_phase3_fails_on_error_in_opt_results(self):
        """When opt_results contains 'error', Phase3 must return 1."""
        from run_research import run_phase3
        import run_research as rr

        args = self._make_fake_args()

        # Mock dependencies so we reach the validation point
        with patch.object(rr, '_select_valid_cs_factors', return_value=['reversal_5_cs']):
            with patch.object(rr, '_load_factor_config', return_value=[]):
                with patch.object(rr, '_filter_enabled_factors', side_effect=lambda x, y: x):
                    with patch('data.panel_loader.get_loader') as mock_loader:
                        mock_l = MagicMock()
                        mock_l.read_factor.return_value = pd.DataFrame({
                            "ts_code": [f"{i:04d}.SZ" for i in range(100)],
                            "trade_date": [20160104] * 100,
                            "value": np.random.randn(100).astype("float32"),
                        })
                        # Provide sufficient price_coverage to pass pre-check
                        mock_l.price_coverage.return_value = {
                            "n_dates": 250, "coverage_ratio": 0.95,
                            "missing_dates": [],
                        }
                        mock_loader.return_value = mock_l
                        with patch('data.calendar.get_calendar') as mock_cal:
                            mock_c = MagicMock()
                            mock_c.weekly_rebalance_dates.return_value = [
                                str(20160104 + i * 7) for i in range(50)
                            ]
                            mock_c.monthly_rebalance_dates.return_value = [
                                str(20160104 + i * 28) for i in range(12)
                            ]
                            mock_c.next_trade_day.side_effect = lambda d, n: d + n
                            mock_c.prev_trade_day.side_effect = lambda d, n: d - n
                            mock_c.trade_days_between.return_value = np.array(
                                [20150104 + i for i in range(300)]
                            )
                            mock_cal.return_value = mock_c
                            with patch('alpha.ic_weighting.ICWeighting') as mock_icw:
                                mock_icw_instance = MagicMock()
                                n_stocks = 100
                                n_dates = 50
                                mock_codes = [f"{i:04d}.SZ" for i in range(n_stocks)]
                                mock_dates = [20160104 + i * 7 for i in range(n_dates)]
                                n_rows = n_stocks * n_dates
                                mock_icw_instance.compute_composite_series.return_value = pd.DataFrame({
                                    "ts_code": mock_codes * n_dates,
                                    "trade_date": [d for d in mock_dates
                                                   for _ in range(n_stocks)],
                                    "composite_score": np.random.randn(n_rows).astype("float32"),
                                })
                                mock_icw.return_value = mock_icw_instance
                                with patch('alpha.score_to_mu.ScoreToMu') as mock_stm:
                                    mock_stm_instance = MagicMock()
                                    mock_stm_instance.calibrate.return_value = pd.DataFrame({
                                        "ts_code": [f"{i:04d}.SZ" for i in range(100)],
                                        "trade_date": [20160105] * 100,
                                        "mu": np.random.randn(100).astype("float32"),
                                    })
                                    mock_stm.return_value = mock_stm_instance
                                    with patch.object(rr, '_build_backtester') as mock_bt:
                                        mock_bt_instance = MagicMock()
                                        # equal-weight: returns valid results
                                        # optimized: returns ERROR
                                        mock_bt_instance.run_backtest.side_effect = [
                                            {  # ew_results
                                                "n_periods": 50,
                                                "annualized_return": 0.15,
                                                "information_ratio": 0.5,
                                            },
                                            {  # opt_results — INVALID
                                                "error": "Optimized backtest failed",
                                                "n_periods": 0,
                                                "opt_n_total": 0,
                                            },
                                        ]
                                        mock_bt.return_value = mock_bt_instance

                                        rc = run_phase3(args)
                                        assert rc == 1, (
                                            f"Phase3 must return 1 on error in "
                                            f"opt_results, got {rc}"
                                        )

    def test_phase3_fails_on_opt_n_total_zero(self):
        """When opt_n_total==0, Phase3 must return 1 (optimizer never ran)."""
        from run_research import run_phase3
        import run_research as rr

        args = self._make_fake_args()

        with patch.object(rr, '_select_valid_cs_factors', return_value=['reversal_5_cs']):
            with patch.object(rr, '_load_factor_config', return_value=[]):
                with patch.object(rr, '_filter_enabled_factors', side_effect=lambda x, y: x):
                    with patch('data.panel_loader.get_loader') as mock_loader:
                        mock_l = MagicMock()
                        mock_l.read_factor.return_value = pd.DataFrame({
                            "ts_code": [f"{i:04d}.SZ" for i in range(100)],
                            "trade_date": [20160104] * 100,
                            "value": np.random.randn(100).astype("float32"),
                        })
                        # Provide sufficient price_coverage to pass pre-check
                        mock_l.price_coverage.return_value = {
                            "n_dates": 250, "coverage_ratio": 0.95,
                            "missing_dates": [],
                        }
                        mock_loader.return_value = mock_l
                        with patch('data.calendar.get_calendar') as mock_cal:
                            mock_c = MagicMock()
                            mock_c.weekly_rebalance_dates.return_value = [
                                str(20160104 + i * 7) for i in range(50)
                            ]
                            mock_c.monthly_rebalance_dates.return_value = [
                                str(20160104 + i * 28) for i in range(12)
                            ]
                            mock_c.next_trade_day.side_effect = lambda d, n: d + n
                            mock_c.prev_trade_day.side_effect = lambda d, n: d - n
                            mock_c.trade_days_between.return_value = np.array(
                                [20150104 + i for i in range(300)]
                            )
                            mock_cal.return_value = mock_c
                            with patch('alpha.ic_weighting.ICWeighting') as mock_icw:
                                mock_icw_instance = MagicMock()
                                n_stocks = 100
                                n_dates = 50
                                mock_codes = [f"{i:04d}.SZ" for i in range(n_stocks)]
                                mock_dates = [20160104 + i * 7 for i in range(n_dates)]
                                n_rows = n_stocks * n_dates
                                mock_icw_instance.compute_composite_series.return_value = pd.DataFrame({
                                    "ts_code": mock_codes * n_dates,
                                    "trade_date": [d for d in mock_dates
                                                   for _ in range(n_stocks)],
                                    "composite_score": np.random.randn(n_rows).astype("float32"),
                                })
                                mock_icw.return_value = mock_icw_instance
                                with patch('alpha.score_to_mu.ScoreToMu') as mock_stm:
                                    mock_stm_instance = MagicMock()
                                    mock_stm_instance.calibrate.return_value = pd.DataFrame({
                                        "ts_code": [f"{i:04d}.SZ" for i in range(100)],
                                        "trade_date": [20160105] * 100,
                                        "mu": np.random.randn(100).astype("float32"),
                                    })
                                    mock_stm.return_value = mock_stm_instance
                                    with patch.object(rr, '_build_backtester') as mock_bt:
                                        mock_bt_instance = MagicMock()
                                        mock_bt_instance.run_backtest.side_effect = [
                                            {  # ew_results
                                                "n_periods": 50,
                                                "annualized_return": 0.15,
                                            },
                                            {  # opt_results — opt_n_total=0
                                                "n_periods": 50,
                                                "annualized_return": 0.15,
                                                "opt_n_total": 0,
                                                "optimizer_fallback_rate": 0.0,
                                                "avg_active_weight": 0.02,
                                            },
                                        ]
                                        mock_bt.return_value = mock_bt_instance

                                        rc = run_phase3(args)
                                        assert rc == 1, (
                                            f"Phase3 must return 1 when opt_n_total=0, "
                                            f"got {rc}"
                                        )


class TestPhase3FallbackThreshold:
    """Phase3 must fail when fallback_rate exceeds 20%."""

    def test_phase3_fails_on_fallback_rate_above_20pct(self):
        """fallback_rate=100% → Phase3 must return 1."""
        from run_research import run_phase3
        import run_research as rr
        import argparse

        args = argparse.Namespace(
            start="20160101", end="20161231",
            top_n=50, weight_max=0.02,
            turnover_max=None, turnover_penalty=None,
            recompute=False, no_recompute=True,
            dry_run=False, frequency="weekly",
            run_id="test_fallback_threshold",
        )

        with patch.object(rr, '_select_valid_cs_factors', return_value=['reversal_5_cs']):
            with patch.object(rr, '_load_factor_config', return_value=[]):
                with patch.object(rr, '_filter_enabled_factors', side_effect=lambda x, y: x):
                    with patch('data.panel_loader.get_loader') as mock_loader:
                        mock_l = MagicMock()
                        mock_l.read_factor.return_value = pd.DataFrame({
                            "ts_code": [f"{i:04d}.SZ" for i in range(100)],
                            "trade_date": [20160104] * 100,
                            "value": np.random.randn(100).astype("float32"),
                        })
                        # Mock price_coverage to return sufficient data
                        mock_l.price_coverage.return_value = {
                            "n_dates": 250, "coverage_ratio": 0.95,
                            "missing_dates": [],
                        }
                        mock_loader.return_value = mock_l
                        with patch('data.calendar.get_calendar') as mock_cal:
                            mock_c = MagicMock()
                            mock_c.weekly_rebalance_dates.return_value = [
                                str(20160104 + i * 7) for i in range(50)
                            ]
                            mock_c.monthly_rebalance_dates.return_value = [
                                str(20160104 + i * 28) for i in range(12)
                            ]
                            mock_c.next_trade_day.side_effect = lambda d, n: d + n
                            mock_c.prev_trade_day.side_effect = lambda d, n: d - n
                            mock_c.trade_days_between.return_value = np.array(
                                [20150104 + i for i in range(300)]
                            )
                            mock_cal.return_value = mock_c
                            with patch('alpha.ic_weighting.ICWeighting') as mock_icw:
                                mock_icw_instance = MagicMock()
                                n_stocks = 100
                                n_dates = 50
                                mock_codes = [f"{i:04d}.SZ" for i in range(n_stocks)]
                                mock_dates = [20160104 + i * 7 for i in range(n_dates)]
                                n_rows = n_stocks * n_dates
                                mock_icw_instance.compute_composite_series.return_value = pd.DataFrame({
                                    "ts_code": mock_codes * n_dates,
                                    "trade_date": [d for d in mock_dates
                                                   for _ in range(n_stocks)],
                                    "composite_score": np.random.randn(n_rows).astype("float32"),
                                })
                                mock_icw.return_value = mock_icw_instance
                                with patch('alpha.score_to_mu.ScoreToMu') as mock_stm:
                                    mock_stm_instance = MagicMock()
                                    mock_stm_instance.calibrate.return_value = pd.DataFrame({
                                        "ts_code": [f"{i:04d}.SZ" for i in range(100)],
                                        "trade_date": [20160105] * 100,
                                        "mu": np.random.randn(100).astype("float32"),
                                    })
                                    mock_stm.return_value = mock_stm_instance
                                    with patch.object(rr, '_build_backtester') as mock_bt:
                                        mock_bt_instance = MagicMock()
                                        mock_bt_instance.run_backtest.side_effect = [
                                            {  # ew_results
                                                "n_periods": 50,
                                                "annualized_return": 0.15,
                                            },
                                            {  # opt_results — 100% fallback
                                                "n_periods": 50,
                                                "annualized_return": 0.15,
                                                "opt_n_total": 44,
                                                "optimizer_fallback_rate": 1.0,
                                                "opt_n_fallback": 44,
                                                "avg_active_weight": 0.02,  # = 1/50
                                                "opt_fallback_reasons": {
                                                    "insufficient_return_obs": 44,
                                                },
                                            },
                                        ]
                                        mock_bt.return_value = mock_bt_instance

                                        rc = run_phase3(args)
                                        assert rc == 1, (
                                            f"Phase3 must return 1 when "
                                            f"fallback_rate=100%, got {rc}"
                                        )


class TestPhase3PriceCacheCheck:
    """Phase3 must fail when prices_adj cache is insufficient."""

    def test_phase3_fails_on_price_cache_insufficient(self):
        """prices_adj has < 200 dates → Phase3 must return 1."""
        from run_research import run_phase3
        import run_research as rr
        import argparse

        args = argparse.Namespace(
            start="20160101", end="20161231",
            top_n=50, weight_max=0.02,
            turnover_max=None, turnover_penalty=None,
            recompute=False, no_recompute=True,
            dry_run=False, frequency="weekly",
            run_id="test_price_cache",
        )

        with patch.object(rr, '_select_valid_cs_factors', return_value=['reversal_5_cs']):
            with patch.object(rr, '_load_factor_config', return_value=[]):
                with patch.object(rr, '_filter_enabled_factors', side_effect=lambda x, y: x):
                    with patch('data.panel_loader.get_loader') as mock_loader:
                        mock_l = MagicMock()
                        mock_l.read_factor.return_value = pd.DataFrame({
                            "ts_code": [f"{i:04d}.SZ" for i in range(100)],
                            "trade_date": [20160104] * 100,
                            "value": np.random.randn(100).astype("float32"),
                        })
                        # CRITICAL: prices_adj has only 10 dates (far below 200)
                        mock_l.price_coverage.return_value = {
                            "n_dates": 10,
                            "coverage_ratio": 0.02,
                            "missing_dates": [str(20150104 + i * 7) for i in range(240)],
                        }
                        mock_loader.return_value = mock_l
                        with patch('data.calendar.get_calendar') as mock_cal:
                            mock_c = MagicMock()
                            mock_c.weekly_rebalance_dates.return_value = [
                                str(20160104 + i * 7) for i in range(50)
                            ]
                            mock_c.monthly_rebalance_dates.return_value = []
                            mock_c.next_trade_day.return_value = 20160105
                            mock_c.prev_trade_day.return_value = 20150104
                            mock_c.trade_days_between.return_value = np.array(
                                [20150104 + i for i in range(5)]  # only 5 days
                            )
                            mock_cal.return_value = mock_c
                            with patch('alpha.ic_weighting.ICWeighting') as mock_icw:
                                mock_icw_instance = MagicMock()
                                n_stocks = 100
                                n_dates = 50
                                mock_codes = [f"{i:04d}.SZ" for i in range(n_stocks)]
                                mock_dates = [20160104 + i * 7 for i in range(n_dates)]
                                n_rows = n_stocks * n_dates
                                mock_icw_instance.compute_composite_series.return_value = pd.DataFrame({
                                    "ts_code": mock_codes * n_dates,
                                    "trade_date": [d for d in mock_dates
                                                   for _ in range(n_stocks)],
                                    "composite_score": np.random.randn(n_rows).astype("float32"),
                                })
                                mock_icw.return_value = mock_icw_instance
                                with patch('alpha.score_to_mu.ScoreToMu') as mock_stm:
                                    mock_stm_instance = MagicMock()
                                    mock_stm_instance.calibrate.return_value = pd.DataFrame({
                                        "ts_code": [f"{i:04d}.SZ" for i in range(100)],
                                        "trade_date": [20160105] * 100,
                                        "mu": np.random.randn(100).astype("float32"),
                                    })
                                    mock_stm.return_value = mock_stm_instance
                                    with patch.object(rr, '_build_backtester') as mock_bt:
                                        mock_bt_instance = MagicMock()
                                        # equal-weight runs fine
                                        mock_bt_instance.run_backtest.return_value = {
                                            "n_periods": 50,
                                            "annualized_return": 0.15,
                                        }
                                        mock_bt.return_value = mock_bt_instance

                                        rc = run_phase3(args)
                                        assert rc == 1, (
                                            f"Phase3 must return 1 when prices_adj "
                                            f"has < 200 dates, got {rc}"
                                        )


class TestOptimizerReturnMatrix:
    """Optimizer covariance input should tolerate sparse per-stock gaps."""

    def test_log_return_matrix_keeps_partially_observed_dates(self):
        from backtest.portfolio_backtester import PortfolioBacktester

        dates = list(range(20200101, 20200182))
        codes = [f"{i:04d}.SZ" for i in range(100)]
        prices = pd.DataFrame(
            np.tile(np.linspace(10.0, 18.0, len(dates)), (len(codes), 1)).T,
            index=dates,
            columns=codes,
        )

        # Simulate realistic sparse gaps: each date has a different missing
        # name, but most names still have enough history for covariance.
        for row_idx in range(1, len(prices)):
            prices.iloc[row_idx, row_idx % len(codes)] = np.nan

        old_strict_rows = np.log(prices / prices.shift(1)).dropna().shape[0]
        ret_matrix = PortfolioBacktester._compute_log_return_matrix(prices)

        assert old_strict_rows == 0
        assert ret_matrix.shape[0] >= 60
        assert ret_matrix.notna().sum().min() >= 60

    def test_ensure_psd_cleans_non_finite_covariance(self):
        from backtest.portfolio_backtester import PortfolioBacktester

        sigma = np.array([
            [1.0, np.nan, 2.0],
            [np.nan, -1.0, np.inf],
            [2.0, np.inf, 1.0],
        ])

        cleaned = PortfolioBacktester._ensure_psd(sigma)

        assert np.isfinite(cleaned).all()
        assert np.allclose(cleaned, cleaned.T)
        assert np.linalg.eigvalsh(cleaned).min() >= -1e-8

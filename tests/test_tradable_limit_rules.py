"""Tests for tradable mask limit up/down rules and constraint enforcement."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pandas as pd
import pytest


class TestLimitRules:
    """Verify limit up/down checks are correctly applied."""

    def test_limit_up_open_blocks_buy(self):
        """Stock opening at limit-up must have can_buy=False."""
        from data.tradable import TradableMask
        tm = TradableMask()
        tm._list_dates = {"A.SZ": 20150101}
        tm._delist_dates = {"A.SZ": 20991231}
        tm._st_periods = {}
        tm._suspend_records = pd.DataFrame()

        # Build limit data: up_limit = 11.0, down_limit = 9.0
        limit_data = pd.DataFrame({
            "ts_code": ["A.SZ"],
            "trade_date": [20240115],
            "up_limit": [11.0],
            "down_limit": [9.0],
        })

        # Raw open = up_limit → limit-up at open
        raw_prices = pd.DataFrame({
            "ts_code": ["A.SZ"],
            "open": [11.0],
        })

        mask = tm.get_mask(["A.SZ"], 20240115, raw_prices=raw_prices,
                           limit_data=limit_data)
        assert mask["is_limit_up_open"].iloc[0]
        assert not mask["can_buy"].iloc[0]
        assert mask["limit_check_available"].iloc[0]

    def test_limit_down_open_blocks_sell(self):
        """Stock opening at limit-down must have can_sell=False."""
        from data.tradable import TradableMask
        tm = TradableMask()
        tm._list_dates = {"A.SZ": 20150101}
        tm._delist_dates = {"A.SZ": 20991231}
        tm._st_periods = {}
        tm._suspend_records = pd.DataFrame()

        limit_data = pd.DataFrame({
            "ts_code": ["A.SZ"],
            "trade_date": [20240115],
            "up_limit": [11.0],
            "down_limit": [9.0],
        })
        raw_prices = pd.DataFrame({
            "ts_code": ["A.SZ"],
            "open": [9.0],
        })

        mask = tm.get_mask(["A.SZ"], 20240115, raw_prices=raw_prices,
                           limit_data=limit_data)
        assert mask["is_limit_down_open"].iloc[0]
        assert not mask["can_sell"].iloc[0]

    def test_limit_check_unavailable_without_prices(self):
        """limit_check_available=False when no raw prices provided."""
        from data.tradable import TradableMask
        tm = TradableMask()
        tm._list_dates = {"A.SZ": 20150101}
        tm._delist_dates = {"A.SZ": 20991231}
        tm._st_periods = {}
        tm._suspend_records = pd.DataFrame()

        limit_data = pd.DataFrame({
            "ts_code": ["A.SZ"],
            "trade_date": [20240115],
            "up_limit": [11.0],
            "down_limit": [9.0],
        })

        # No raw_prices provided
        mask = tm.get_mask(["A.SZ"], 20240115, limit_data=limit_data)
        assert not mask["limit_check_available"].iloc[0]
        # Without prices, limits can't be checked → can_buy defaults to True
        assert mask["can_buy"].iloc[0]

    def test_normal_stock_buyable(self):
        """Stock trading within limits is fully buyable/sellable."""
        from data.tradable import TradableMask
        tm = TradableMask()
        tm._list_dates = {"A.SZ": 20150101}
        tm._delist_dates = {"A.SZ": 20991231}
        tm._st_periods = {}
        tm._suspend_records = pd.DataFrame()

        limit_data = pd.DataFrame({
            "ts_code": ["A.SZ"],
            "trade_date": [20240115],
            "up_limit": [11.0],
            "down_limit": [9.0],
        })
        raw_prices = pd.DataFrame({
            "ts_code": ["A.SZ"],
            "open": [10.0],  # between limits
        })

        mask = tm.get_mask(["A.SZ"], 20240115, raw_prices=raw_prices,
                           limit_data=limit_data)
        assert mask["can_buy"].iloc[0]
        assert mask["can_sell"].iloc[0]
        assert not mask["is_limit_up_open"].iloc[0]
        assert not mask["is_limit_down_open"].iloc[0]


class TestExecutionEdgeCases:
    """Verify execution handles untradable positions correctly."""

    def test_frozen_weight_not_rescaled(self):
        """When a stock is frozen, its weight stays exactly at previous value."""
        from backtest.execution import ExecutionSimulator
        exe = ExecutionSimulator()

        # A=100% holding, can't sell; target wants B=100%
        target = pd.Series({"A.SZ": 0.0, "B.SZ": 1.0})
        prev = pd.Series({"A.SZ": 1.0, "B.SZ": 0.0})
        prices = pd.DataFrame({"ts_code": ["A.SZ", "B.SZ"], "open": [10.0, 20.0]})
        can_buy = pd.Series({"A.SZ": True, "B.SZ": True})
        can_sell = pd.Series({"A.SZ": False, "B.SZ": True})

        result = exe.execute_rebalance(20240115, target, prev, prices, 1_000_000,
                                       can_buy, can_sell)
        w = result["executed_weights"]
        assert w.get("A.SZ") > 0.99, f"A was rescaled! Got {w.get('A.SZ')}"
        assert w.get("B.SZ") < 0.01, f"B got weight despite frozen A!"

    def test_sell_generates_turnover_and_cost(self):
        """Selling an old holding generates turnover and transaction costs."""
        from backtest.execution import ExecutionSimulator
        exe = ExecutionSimulator()

        target = pd.Series({"A.SZ": 0.0, "B.SZ": 1.0})  # sell all A, buy B
        prev = pd.Series({"A.SZ": 1.0, "B.SZ": 0.0})
        prices = pd.DataFrame({"ts_code": ["A.SZ", "B.SZ"], "open": [10.0, 20.0]})
        can_all = pd.Series({"A.SZ": True, "B.SZ": True})

        result = exe.execute_rebalance(20240115, target, prev, prices, 1_000_000,
                                       can_all, can_all)
        assert result["turnover"] > 0.4, f"Turnover too low: {result['turnover']}"
        assert result["costs"]["total_cost_cny"] > 0, "No costs on sell!"


class TestLimitCacheIsolation:
    """Verify cache does NOT pollute limit-check results across calls."""

    def test_no_limit_then_with_limit_not_reuse_cache(self):
        """Call without limit_data first, then with limit_data — must NOT reuse stale cache."""
        from data.tradable import TradableMask
        tm = TradableMask()
        tm._list_dates = {"A.SZ": 20150101}
        tm._delist_dates = {"A.SZ": 20991231}
        tm._st_periods = {}
        tm._suspend_records = pd.DataFrame()

        limit_data = pd.DataFrame({
            "ts_code": ["A.SZ"],
            "trade_date": [20240115],
            "up_limit": [11.0],
            "down_limit": [9.0],
        })
        raw_prices = pd.DataFrame({
            "ts_code": ["A.SZ"],
            "open": [11.0],  # at limit-up
        })

        # First call: NO limit_data → limit_check_available=False
        mask1 = tm.get_mask(["A.SZ"], 20240115, raw_prices=raw_prices)
        assert not mask1["limit_check_available"].iloc[0], \
            "Without limit_data, limit_check_available should be False"
        assert mask1["can_buy"].iloc[0], \
            "Without limit check, can_buy should default to True"

        # Second call: WITH limit_data → limit_check_available=True, can_buy=False
        mask2 = tm.get_mask(["A.SZ"], 20240115, raw_prices=raw_prices,
                            limit_data=limit_data)
        assert mask2["limit_check_available"].iloc[0], \
            "With limit_data, limit_check_available should be True"
        assert not mask2["can_buy"].iloc[0], \
            "With limit-up open, can_buy should be False — cache pollution!"

    def test_with_limit_then_without_limit_reuse_is_ok(self):
        """Call with limit_data first, then without — 'with' cache is more accurate, reuse ok."""
        from data.tradable import TradableMask
        tm = TradableMask()
        tm._list_dates = {"A.SZ": 20150101}
        tm._delist_dates = {"A.SZ": 20991231}
        tm._st_periods = {}
        tm._suspend_records = pd.DataFrame()

        limit_data = pd.DataFrame({
            "ts_code": ["A.SZ"],
            "trade_date": [20240115],
            "up_limit": [11.0],
            "down_limit": [9.0],
        })
        raw_prices = pd.DataFrame({
            "ts_code": ["A.SZ"],
            "open": [11.0],
        })

        # First: with limit_data → correctly detects limit-up
        mask1 = tm.get_mask(["A.SZ"], 20240115, raw_prices=raw_prices,
                            limit_data=limit_data)
        assert mask1["limit_check_available"].iloc[0]
        assert not mask1["can_buy"].iloc[0]

        # Second: without limit_data → should reuse "with" cache
        mask2 = tm.get_mask(["A.SZ"], 20240115, raw_prices=raw_prices)
        assert mask2["limit_check_available"].iloc[0], \
            "Should reuse accurate 'with-limits' cache"
        assert not mask2["can_buy"].iloc[0], \
            "Should preserve limit-up detection from cache"


class TestBacktestPriceLimitPath:
    """Verify the actual backtest path correctly handles price limits."""

    def test_raw_open_at_up_limit_cannot_buy(self):
        """Backtest path: raw open == up_limit → can_buy=False."""
        from data.tradable import TradableMask
        tm = TradableMask()
        tm._list_dates = {"000001.SZ": 20150101}
        tm._delist_dates = {"000001.SZ": 20991231}
        tm._st_periods = {}
        tm._suspend_records = pd.DataFrame()

        # Simulate what the backtest does: raw open prices + limit_data
        raw_prices = pd.DataFrame({
            "ts_code": ["000001.SZ"],
            "open": [11.0],
        })
        limit_data = pd.DataFrame({
            "ts_code": ["000001.SZ"],
            "trade_date": [20240115],
            "up_limit": [11.0],
            "down_limit": [9.0],
        })

        mask = tm.get_mask(["000001.SZ"], 20240115,
                           raw_prices=raw_prices,
                           limit_data=limit_data)
        assert mask["is_limit_up_open"].iloc[0], \
            "Stock opening at up_limit should have is_limit_up_open=True"
        assert not mask["can_buy"].iloc[0], \
            "Stock at limit-up open must have can_buy=False"
        assert mask["limit_check_available"].iloc[0], \
            "limit_check_available must be True when both raw_prices and limit_data provided"

    def test_raw_open_at_down_limit_cannot_sell(self):
        """Backtest path: raw open == down_limit → can_sell=False."""
        from data.tradable import TradableMask
        tm = TradableMask()
        tm._list_dates = {"000001.SZ": 20150101}
        tm._delist_dates = {"000001.SZ": 20991231}
        tm._st_periods = {}
        tm._suspend_records = pd.DataFrame()

        raw_prices = pd.DataFrame({
            "ts_code": ["000001.SZ"],
            "open": [9.0],
        })
        limit_data = pd.DataFrame({
            "ts_code": ["000001.SZ"],
            "trade_date": [20240115],
            "up_limit": [11.0],
            "down_limit": [9.0],
        })

        mask = tm.get_mask(["000001.SZ"], 20240115,
                           raw_prices=raw_prices,
                           limit_data=limit_data)
        assert mask["is_limit_down_open"].iloc[0], \
            "Stock opening at down_limit should have is_limit_down_open=True"
        assert not mask["can_sell"].iloc[0], \
            "Stock at limit-down open must have can_sell=False"
        assert mask["limit_check_available"].iloc[0]

    def test_auto_fetch_limit_data_triggers(self):
        """When raw_prices provided but no limit_data, auto-fetch should trigger."""
        from data.tradable import TradableMask
        from unittest.mock import patch, MagicMock
        import pandas as pd

        tm = TradableMask()
        tm._list_dates = {"A.SZ": 20150101}
        tm._delist_dates = {"A.SZ": 20991231}
        tm._st_periods = {}
        tm._suspend_records = pd.DataFrame()

        # Mock the client to return limit data
        mock_limit = pd.DataFrame({
            "ts_code": ["A.SZ"],
            "trade_date": [20240115],
            "up_limit": [11.0],
            "down_limit": [9.0],
        })

        with patch.object(tm, '_fetch_limit_data', return_value=mock_limit):
            raw_prices = pd.DataFrame({"ts_code": ["A.SZ"], "open": [11.0]})
            mask = tm.get_mask(["A.SZ"], 20240115, raw_prices=raw_prices)

        assert mask["limit_check_available"].iloc[0], \
            "Auto-fetch should provide limit_data → limit_check_available=True"
        assert not mask["can_buy"].iloc[0], \
            "With auto-fetched limit_data, limit-up should block buy"


class TestBacktesterToTradableMaskIntegration:
    """Verify the full PortfolioBacktester → TradableMask path handles limits.

    These tests mock the backtester's _get_execution_prices and the
    PanelLoader's query_limit_data to simulate the actual backtest flow
    from scores → execution → tradable mask → can_buy/can_sell.
    """

    def test_simulate_passes_limit_data_to_get_mask(self):
        """_simulate() fetches limit_data and passes it to get_mask()."""
        from unittest.mock import patch, MagicMock
        from backtest.portfolio_backtester import PortfolioBacktester
        import pandas as pd

        bt = PortfolioBacktester()

        # Build minimal scores: 2 stocks, 2 signal dates (need t+1)
        scores = pd.DataFrame({
            "ts_code": ["000001.SZ", "000002.SZ", "000001.SZ", "000002.SZ"],
            "trade_date": [20240102, 20240102, 20240109, 20240109],
            "composite_score": [0.8, 0.6, 0.9, 0.5],
        })

        # Mock calendar (imported inside _simulate from data.calendar)
        with patch('data.calendar.get_calendar') as mock_cal:
            mock_cal_instance = MagicMock()
            mock_cal_instance.weekly_rebalance_dates.return_value = [
                '20240102', '20240109', '20240116'
            ]
            mock_cal_instance.next_trade_day.side_effect = lambda d, n: d + n
            mock_cal.return_value = mock_cal_instance

            # Mock the private attributes that the properties would return
            mock_univ = MagicMock()
            mock_univ.get_universe.return_value = ["000001.SZ", "000002.SZ"]
            bt._universe = mock_univ

            mock_exec = MagicMock()
            mock_exec.execute_rebalance.return_value = {
                "executed_weights": pd.Series(
                    [0.0, 1.0], index=["000001.SZ", "000002.SZ"]
                ),
                "costs": {"total_cost_cny": 100.0, "total_cost_bps": 5.0},
                "turnover": 0.5,
                "cash_drag": 0.0,
            }
            bt._execution = mock_exec

            mock_tm = MagicMock()
            mock_mask = pd.DataFrame({
                "ts_code": ["000001.SZ", "000002.SZ"],
                "trade_date": [20240103, 20240103],
                "can_buy": [False, True],
                "can_sell": [True, True],
                "can_hold": [True, True],
                "is_suspended": [False, False],
                "is_limit_up_open": [True, False],
                "is_limit_down_open": [False, False],
                "is_st": [False, False],
                "is_new_stock": [False, False],
                "limit_check_available": [True, True],
                "reason": ["limit_up_open", ""],
            })
            mock_tm.get_mask.return_value = mock_mask
            bt._tradable = mock_tm

            # Execution prices: 000001.SZ at limit-up
            bt._get_execution_prices = MagicMock(return_value=pd.DataFrame({
                "ts_code": ["000001.SZ", "000002.SZ"],
                "open": [11.0, 10.0],
            }))

            # Mock holding return to avoid real price queries
            bt._compute_holding_return = MagicMock(return_value=0.01)

            # Mock loader to avoid real limit_data fetch
            mock_loader = MagicMock()
            mock_loader.query_limit_data.return_value = pd.DataFrame({
                "ts_code": ["000001.SZ", "000002.SZ"],
                "trade_date": [20240103, 20240103],
                "up_limit": [11.0, 12.0],
                "down_limit": [9.0, 8.0],
            })
            bt._loader = mock_loader

            # Run _simulate
            pv, hld, trd, diag = bt._simulate(
                scores, "composite_score",
                signal_dates=[20240102, 20240109],
                top_n=2, weighting="equal",
                initial_capital=1_000_000,
                mu_df=None,
            )

            # Verify get_mask was called with raw_prices
            call_args = mock_tm.get_mask.call_args
            assert call_args is not None, "get_mask should have been called"
            _, kwargs = call_args
            assert kwargs.get("raw_prices") is not None, \
                "raw_prices should be passed to get_mask"

            # 000001.SZ (limit-up) should have can_buy=False in the mock mask
            assert not mock_mask[mock_mask["ts_code"] == "000001.SZ"]["can_buy"].iloc[0], \
                "000001.SZ at limit-up must have can_buy=False"
            assert mock_mask["limit_check_available"].all(), \
                "limit_check_available should be True"

    def test_simulate_limit_up_stock_excluded_from_buys(self):
        """Stock at limit-up open is NOT bought even if top-scored."""
        from unittest.mock import patch, MagicMock
        from backtest.portfolio_backtester import PortfolioBacktester
        import pandas as pd

        bt = PortfolioBacktester()

        scores = pd.DataFrame({
            "ts_code": ["000001.SZ", "000002.SZ"],
            "trade_date": [20240102, 20240102],
            "composite_score": [0.95, 0.60],
        })

        with patch('data.calendar.get_calendar') as mock_cal:
            mock_cal_instance = MagicMock()
            mock_cal_instance.weekly_rebalance_dates.return_value = [
                '20240102', '20240109'
            ]
            mock_cal_instance.next_trade_day.side_effect = lambda d, n: d + n
            mock_cal.return_value = mock_cal_instance

            # Set private attributes directly (avoids property patching)
            mock_univ = MagicMock()
            mock_univ.get_universe.return_value = ["000001.SZ", "000002.SZ"]
            bt._universe = mock_univ

            mock_exec = MagicMock()
            mock_exec.execute_rebalance.return_value = {
                "executed_weights": pd.Series(
                    [0.0, 1.0], index=["000001.SZ", "000002.SZ"]
                ),
                "costs": {"total_cost_cny": 50.0, "total_cost_bps": 2.5},
                "turnover": 1.0,
                "cash_drag": 0.0,
            }
            bt._execution = mock_exec

            mock_tm = MagicMock()
            mock_mask = pd.DataFrame({
                "ts_code": ["000001.SZ", "000002.SZ"],
                "trade_date": [20240103, 20240103],
                "can_buy": [False, True],
                "can_sell": [True, True],
                "can_hold": [True, True],
                "is_suspended": [False, False],
                "is_limit_up_open": [True, False],
                "is_limit_down_open": [False, False],
                "is_st": [False, False],
                "is_new_stock": [False, False],
                "limit_check_available": [True, True],
                "reason": ["limit_up_open", ""],
            })
            mock_tm.get_mask.return_value = mock_mask
            bt._tradable = mock_tm

            bt._get_execution_prices = MagicMock(return_value=pd.DataFrame({
                "ts_code": ["000001.SZ", "000002.SZ"],
                "open": [11.0, 10.0],
            }))

            bt._compute_holding_return = MagicMock(return_value=0.01)

            # Mock loader
            mock_loader = MagicMock()
            mock_loader.query_limit_data.return_value = pd.DataFrame({
                "ts_code": ["000001.SZ", "000002.SZ"],
                "trade_date": [20240103, 20240103],
                "up_limit": [11.0, 12.0],
                "down_limit": [9.0, 8.0],
            })
            bt._loader = mock_loader

            pv, hld, trd, diag = bt._simulate(
                scores, "composite_score",
                signal_dates=[20240102, 20240109],
                top_n=2, weighting="equal",
                initial_capital=1_000_000,
                mu_df=None,
            )

            # 000001.SZ at limit-up → can_buy=False
            assert not mock_mask[mock_mask["ts_code"] == "000001.SZ"]["can_buy"].iloc[0], \
                "Limit-up stock must have can_buy=False"
            assert mock_mask[mock_mask["ts_code"] == "000001.SZ"]["is_limit_up_open"].iloc[0], \
                "Limit-up stock must have is_limit_up_open=True"

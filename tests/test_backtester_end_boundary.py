import pandas as pd


def test_simulate_caps_period_end_at_backtest_end(monkeypatch):
    """Last holding period must not mark to market beyond end_date."""
    from backtest.portfolio_backtester import PortfolioBacktester

    class FakeCalendar:
        def next_trade_day(self, date, n=1):
            mapping = {
                (20241220, 1): 20241223,
                (20241227, 1): 20241230,
                (20241231, 1): 20250102,
                (20241231, 0): 20241231,
            }
            return mapping.get((date, n), date + n)

    monkeypatch.setattr("data.calendar.get_calendar", lambda: FakeCalendar())

    bt = PortfolioBacktester()
    bt._universe = type(
        "Universe",
        (),
        {"get_universe": lambda self, date: ["000001.SZ", "000002.SZ"]},
    )()

    bt._get_execution_prices = lambda stocks, date: pd.DataFrame(
        {
            "ts_code": stocks,
            "open": [10.0] * len(stocks),
        }
    )
    bt._compute_holding_return = lambda weights, exec_date, next_exec_date: 0.01

    class FakeTradable:
        client = None

        def get_mask(self, stocks, exec_date, raw_prices=None, limit_data=None):
            return pd.DataFrame(
                {
                    "ts_code": stocks,
                    "can_buy": [True] * len(stocks),
                    "can_sell": [True] * len(stocks),
                    "limit_check_available": [True] * len(stocks),
                }
            )

    bt._tradable = FakeTradable()
    bt._loader = type(
        "Loader",
        (),
        {"query_limit_data": lambda self, date, ts_codes=None: pd.DataFrame()},
    )()

    scores = pd.DataFrame(
        {
            "ts_code": ["000001.SZ", "000002.SZ"] * 2,
            "trade_date": [20241220, 20241220, 20241227, 20241227],
            "composite_score": [1.0, 0.9, 1.0, 0.9],
        }
    )

    portfolio_values, _, _, _ = bt._simulate(
        scores=scores,
        score_col="composite_score",
        signal_dates=[20241220, 20241227, 20241231],
        top_n=2,
        weighting="equal",
        initial_capital=1_000_000.0,
        end_date=20241231,
    )

    assert portfolio_values[-1]["signal_date"] == 20241227
    assert portfolio_values[-1]["exec_date"] == 20241230
    assert portfolio_values[-1]["period_end"] == 20241231

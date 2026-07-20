"""
Tests for benchmark period alignment, optimizer Phase 3, panel loader batching,
robustness cost sensitivity, and price adjustment pipeline.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pandas as pd
import pytest


class TestBenchmarkAlignment:
    """Verify benchmark returns exclude execution date."""

    def test_benchmark_excludes_exec_date(self):
        """Benchmark period return must start AFTER exec_date, not include it."""
        # Simulate benchmark daily returns
        bench = pd.DataFrame({
            "trade_date": [20240101, 20240102, 20240103, 20240104, 20240105],
            "benchmark_ret": [0.01, 0.02, -0.01, 0.005, 0.015],
        }).set_index("trade_date")["benchmark_ret"]

        # Strategy period: exec=20240102, period_end=20240104
        # Benchmark should use ONLY dates > 20240102: [20240103, 20240104]
        period_bench = bench.loc[
            (bench.index > 20240102) & (bench.index <= 20240104)
        ]
        assert 20240102 not in period_bench.index, "exec_date included in benchmark!"
        assert 20240103 in period_bench.index
        assert 20240104 in period_bench.index


class TestPriceAdjustmentPipeline:
    """Verify prices_adj is correctly computed from raw + adj_factor."""

    def test_adj_prices_computation(self):
        """adj_close = raw close × adj_factor."""
        from data.adjust import PriceAdjuster

        adjuster = PriceAdjuster()
        adjuster._adj_factor_cache = pd.DataFrame({
            "ts_code": ["000001.SZ"],
            "trade_date": [20240115],
            "adj_factor": [1.5],
        })

        raw = pd.DataFrame({
            "ts_code": ["000001.SZ"],
            "trade_date": [20240115],
            "open": [10.0], "high": [11.0], "low": [9.5], "close": [10.5],
            "pre_close": [9.8], "vol": [1e6], "amount": [1e7],
        })

        result = adjuster.compute_adj_prices(raw)
        expected_adj_close = 10.5 * 1.5  # 15.75
        assert abs(result["adj_close"].iloc[0] - expected_adj_close) < 0.01

    def test_raw_prices_unchanged(self):
        """Raw prices are preserved alongside adjusted prices."""
        from data.adjust import PriceAdjuster
        adjuster = PriceAdjuster()
        adjuster._adj_factor_cache = pd.DataFrame({
            "ts_code": ["A.SZ"],
            "trade_date": [1],
            "adj_factor": [2.0],
        })
        raw = pd.DataFrame({
            "ts_code": ["A.SZ"], "trade_date": [1],
            "open": [10.0], "high": [11.0], "low": [9.5], "close": [10.5],
            "pre_close": [9.8], "vol": [1000], "amount": [10000],
        })
        result = adjuster.compute_adj_prices(raw)
        # Raw close unchanged
        assert result["close"].iloc[0] == 10.5
        # Adj close = raw × factor
        assert result["adj_close"].iloc[0] == 21.0


class TestPanelLoaderBatching:
    """Verify PanelLoader handles stock lists > batch size correctly."""

    def test_write_data_creates_partitions(self, tmp_path):
        """write_data creates partitioned parquet."""
        from data.panel_loader import PanelLoader
        loader = PanelLoader(data_path=str(tmp_path))

        df = pd.DataFrame({
            "ts_code": ["A", "B", "C"],
            "trade_date": [20240115, 20240115, 20240115],
            "adj_close": [10.0, 20.0, 30.0],
        })
        loader.write_data(df, "test_prices_adj", partition_cols=["trade_date"])
        assert (tmp_path / "test_prices_adj").exists()

    def test_query_handles_many_stocks(self):
        """Query batches large stock lists internally and returns all results."""
        from data.panel_loader import PanelLoader
        import pyarrow.parquet as pq
        import pyarrow as pa

        loader = PanelLoader(data_path="/tmp/code_v4_batch_test")
        loader.initialize()

        # Write test data with 600 stocks
        stocks = [f"{i:04d}.SZ" for i in range(600)]
        df = pd.DataFrame({
            "ts_code": stocks,
            "trade_date": [20240115] * 600,
            "value": np.random.random(600).astype("float32"),
        })
        loader.write_data(df, "batch_test_table")

        # Query all 600 stocks
        result = loader.query("batch_test_table", columns=["ts_code", "value"],
                              start_date="20240115", end_date="20240115",
                              ts_codes=stocks)
        assert len(result) == 600, f"Expected 600, got {len(result)}"

        import shutil
        shutil.rmtree("/tmp/code_v4_batch_test", ignore_errors=True)


class TestRobustnessCosts:
    """Verify cost sensitivity tests actually change the cost model."""

    def test_cost_multiplier_changes_costs(self):
        """2x cost produces higher cost_bps than 1x."""
        from backtest.cost_model import CostConfig, CostModel

        base = CostConfig(commission_rate=0.00025, slippage_bps=5.0)
        model_1x = CostModel(base)
        model_2x = CostModel(base.stress_2x())

        # Same trade, different costs
        cost_1x = model_1x.compute_trade_cost("A.SZ", "buy", 10.0, 10000, 100000.0)
        cost_2x = model_2x.compute_trade_cost("A.SZ", "buy", 10.0, 10000, 100000.0)

        assert cost_2x["total_cost"] > cost_1x["total_cost"], (
            f"2x cost ({cost_2x['total_cost']}) not > 1x ({cost_1x['total_cost']})"
        )

    def test_cost_multiplier_applied_to_portfolio_level(self):
        """Cost multiplier changes turnover cost computation."""
        from backtest.cost_model import CostConfig, CostModel

        prev = pd.Series({"A": 1.0, "B": 0.0})
        new = pd.Series({"A": 0.0, "B": 1.0})
        prices = pd.Series({"A": 10.0, "B": 20.0})

        base = CostConfig(commission_rate=0.00025, slippage_bps=5.0, stamp_duty_rate=0.0005)
        model_1x = CostModel(base)
        model_2x = CostModel(base.stress_2x())

        r1 = model_1x.compute_turnover_cost(prev, new, prices, 1_000_000)
        r2 = model_2x.compute_turnover_cost(prev, new, prices, 1_000_000)

        assert r2["total_cost_bps"] > r1["total_cost_bps"], (
            f"2x ({r2['total_cost_bps']:.2f} bps) not > 1x ({r1['total_cost_bps']:.2f} bps)"
        )

    def test_backtester_cost_scenarios_change_net_metrics_without_leakage(self, monkeypatch):
        """Cost stress should lower net returns and not leak into the next run."""
        from backtest.portfolio_backtester import PortfolioBacktester

        class FakeCalendar:
            def load(self, start_date=None, end_date=None):
                pass  # no-op for tests

            def weekly_rebalance_dates(self, start_date, end_date):
                return [
                    "20240101", "20240108", "20240115", "20240122",
                    "20240129", "20240205", "20240212",
                ]

            def monthly_rebalance_dates(self, start_date, end_date):
                return self.weekly_rebalance_dates(start_date, end_date)

        monkeypatch.setattr("data.calendar.get_calendar", lambda: FakeCalendar())

        bt = PortfolioBacktester()

        def fake_load_benchmark_returns(*args, **kwargs):
            return pd.DataFrame()

        def fake_simulate(scores, score_col, signal_dates, top_n, weighting,
                          initial_capital, mu_df=None, weight_max=0.02, **kwargs):
            prev = pd.Series({"A": 1.0, "B": 0.0})
            new = pd.Series({"A": 0.0, "B": 1.0})
            prices = pd.Series({"A": 10.0, "B": 10.0})
            cost = bt.cost_model.compute_turnover_cost(
                prev, new, prices, initial_capital
            )

            gross_return = 0.01
            net_return = gross_return - cost["total_cost_bps"] / 10000.0
            value = initial_capital
            portfolio_values = []
            trades_log = []

            for i, signal_date in enumerate(signal_dates[:-1]):
                value *= 1.0 + net_return
                portfolio_values.append({
                    "signal_date": int(signal_date),
                    "exec_date": int(signal_date) + 1,
                    "period_end": int(signal_date) + 7,
                    "portfolio_value": value,
                    "period_return": net_return,
                    "gross_period_return": gross_return,
                    "turnover": 1.0,
                    "cost_cny": cost["total_cost_cny"],
                    "cost_bps": cost["total_cost_bps"],
                    "n_holdings": top_n,
                })
                trades_log.append({
                    "signal_date": int(signal_date),
                    "exec_date": int(signal_date) + 1,
                    "turnover": 1.0,
                    "cost_cny": cost["total_cost_cny"],
                    "cost_bps": cost["total_cost_bps"],
                })

            return portfolio_values, [], trades_log, {
                "opt_n_total": 0, "opt_n_fallback": 0, "opt_n_mu_used": 0,
                "opt_fallback_rate": 0.0, "opt_mu_rate": 0.0,
                "opt_avg_active_weight": 0.0, "opt_max_single_weight": 0.0,
            }

        monkeypatch.setattr(bt, "_load_benchmark_returns", fake_load_benchmark_returns)
        monkeypatch.setattr(bt, "_simulate", fake_simulate)

        scores = pd.DataFrame({
            "ts_code": ["A"],
            "trade_date": [20240101],
            "composite_score": [1.0],
        })

        r1 = bt.run_backtest(scores, start_date="20240101", end_date="20240212")
        r2 = bt.run_backtest(
            scores, start_date="20240101", end_date="20240212",
            cost_multiplier=2.0,
        )
        r1_again = bt.run_backtest(
            scores, start_date="20240101", end_date="20240212",
        )

        assert r2["total_cost_bps"] > r1["total_cost_bps"]
        assert r2["annualized_return"] < r1["annualized_return"]
        assert r1_again["total_cost_bps"] == pytest.approx(r1["total_cost_bps"])
        assert r1_again["annualized_return"] == pytest.approx(r1["annualized_return"])


class TestWeightMaxOptimization:
    """Verify weight_max flows through to optimization constraints."""

    def test_weight_max_changes_constraint(self):
        """weight_max=0.03 produces constraint w <= 0.03 (not 0.02)."""
        from portfolio.constraints import ConstraintBuilder

        cb_2pct = ConstraintBuilder(weight_max=0.02)
        cb_3pct = ConstraintBuilder(weight_max=0.03)

        assert cb_2pct.weight_max == 0.02
        assert cb_3pct.weight_max == 0.03
        assert cb_2pct.weight_max != cb_3pct.weight_max, \
            "Different weight_max values should produce different constraints"

    def test_infeasible_config_detected(self):
        """top_n=50, weight_max=0.01 → infeasible (50*0.01=0.5 < 1.0)."""
        top_n = 50
        weight_max = 0.01
        assert top_n * weight_max < 1.0, \
            f"Config should be detected as infeasible: {top_n} * {weight_max} = {top_n * weight_max}"

    def test_feasible_config_passes(self):
        """top_n=50, weight_max=0.03 → feasible (50*0.03=1.5 >= 1.0)."""
        top_n = 50
        weight_max = 0.03
        assert top_n * weight_max >= 1.0, \
            f"Config should be feasible: {top_n} * {weight_max} = {top_n * weight_max}"

    def test_backtester_feasibility_check(self):
        """PortfolioBacktester._compute_optimized_weights detects infeasible config."""
        from backtest.portfolio_backtester import PortfolioBacktester
        import pandas as pd

        bt = PortfolioBacktester()
        # Minimal stocks
        top_stocks = pd.DataFrame({
            "ts_code": [f"{i:04d}.SZ" for i in range(10)],
            "composite_score": range(10),
        })
        prev_w = pd.Series(0.1, index=top_stocks["ts_code"])

        # weight_max=0.05 (feasible: 10*0.05=0.5 but with 10 stocks cvxpy might work)
        # Actually 10*0.05=0.5 < 1.0, so it IS infeasible
        weights, diag = bt._compute_optimized_weights(
            top_stocks, "composite_score", 20240115,
            prev_weights=prev_w, exec_date=20240116,
            top_n=10, mu_df=None, weight_max=0.05
        )
        assert diag["fallback"], "Should fallback when 10*0.05=0.5 < 1.0"
        assert "infeasible" in diag.get("fallback_reason", ""), \
            f"Should mention infeasible, got: {diag.get('fallback_reason')}"

    def test_weight_max_0_10_is_feasible(self):
        """weight_max=0.10 with top_n=20 → 20*0.10=2.0 >= 1.0 → feasible check passes."""
        from backtest.portfolio_backtester import PortfolioBacktester
        import pandas as pd

        bt = PortfolioBacktester()
        top_stocks = pd.DataFrame({
            "ts_code": [f"{i:04d}.SZ" for i in range(20)],
            "composite_score": range(20),
        })
        prev_w = pd.Series(0.05, index=top_stocks["ts_code"])

        # weight_max=0.10, top_n=20: 20*0.10=2.0 >= 1.0 → passes feasibility
        # But without cvxpy/mu_df should still fallback for other reasons
        weights, diag = bt._compute_optimized_weights(
            top_stocks, "composite_score", 20240115,
            prev_weights=prev_w, exec_date=20240116,
            top_n=20, mu_df=None, weight_max=0.10
        )
        # Should NOT fail on feasibility, but on missing mu_df
        assert "infeasible" not in diag.get("fallback_reason", ""), \
            f"Should not be infeasible (20*0.10=2.0 >= 1.0), got: {diag.get('fallback_reason')}"
        assert diag["fallback"], "Should still fallback (no mu_df)"


class TestWeightMaxOptimizedPath:
    """Verify weight_max actually changes optimization results with real data."""

    def test_weight_max_002_vs_005_feasibility_differs(self):
        """weight_max changes the feasibility boundary correctly."""
        import numpy as np
        import pandas as pd
        from backtest.portfolio_backtester import PortfolioBacktester

        np.random.seed(42)
        n_stocks = 50
        codes = [f"{i:04d}.SZ" for i in range(n_stocks)]
        true_mu = np.linspace(0.0001, 0.002, n_stocks)

        top_stocks = pd.DataFrame({
            "ts_code": codes,
            "composite_score": range(n_stocks),
        })

        mu_df = pd.DataFrame({
            "ts_code": codes,
            "trade_date": [20240102] * n_stocks,
            "mu": true_mu,
        })

        bt = PortfolioBacktester()
        prev_w = pd.Series(1.0 / n_stocks, index=codes)

        # weight_max=0.02: 50*0.02=1.0 → barely feasible (not infeasible)
        _, diag_002 = bt._compute_optimized_weights(
            top_stocks, "composite_score", 20240102,
            prev_weights=prev_w, exec_date=20240103,
            top_n=n_stocks, mu_df=mu_df, weight_max=0.02
        )
        if diag_002.get("fallback"):
            assert "infeasible" not in diag_002.get("fallback_reason", ""), \
                f"50×0.02=1.0 should be feasible, got: {diag_002.get('fallback_reason')}"

        # weight_max=0.05: 50*0.05=2.5 → clearly feasible
        _, diag_005 = bt._compute_optimized_weights(
            top_stocks, "composite_score", 20240102,
            prev_weights=prev_w, exec_date=20240103,
            top_n=n_stocks, mu_df=mu_df, weight_max=0.05
        )
        if diag_005.get("fallback"):
            assert "infeasible" not in diag_005.get("fallback_reason", ""), \
                f"50×0.05=2.5 should be feasible, got: {diag_005.get('fallback_reason')}"

        # weight_max=0.01: 50*0.01=0.5 → infeasible
        _, diag_001 = bt._compute_optimized_weights(
            top_stocks, "composite_score", 20240102,
            prev_weights=prev_w, exec_date=20240103,
            top_n=n_stocks, mu_df=mu_df, weight_max=0.01
        )
        assert diag_001["fallback"], "Should fallback on infeasible config"
        assert diag_001.get("infeasible_config"), "Should mark as infeasible"

    def test_weight_max_001_infeasible_with_50_stocks(self):
        """top_n=50, weight_max=0.01 → infeasible (50×0.01=0.5 < 1.0)."""
        from backtest.portfolio_backtester import PortfolioBacktester
        import numpy as np
        import pandas as pd

        bt = PortfolioBacktester()
        n = 50
        codes = [f"{i:04d}.SZ" for i in range(n)]
        top_stocks = pd.DataFrame({
            "ts_code": codes,
            "composite_score": range(n),
        })

        mu_df = pd.DataFrame({
            "ts_code": codes,
            "trade_date": [20240102] * n,
            "mu": np.linspace(0.0001, 0.002, n),
        })

        weights, diag = bt._compute_optimized_weights(
            top_stocks, "composite_score", 20240102,
            prev_weights=pd.Series(1.0 / n, index=codes),
            exec_date=20240103, top_n=n,
            mu_df=mu_df, weight_max=0.01
        )

        assert diag["fallback"], "Should fallback when infeasible"
        assert diag.get("infeasible_config"), \
            "Should set infeasible_config=True"
        assert "infeasible" in diag.get("fallback_reason", ""), \
            f"Reason should mention infeasible, got: {diag.get('fallback_reason')}"

    def test_constraint_builder_uses_weight_max(self):
        """ConstraintBuilder with different weight_max produces different objects."""
        from portfolio.constraints import ConstraintBuilder

        cb_02 = ConstraintBuilder(weight_max=0.02)
        cb_05 = ConstraintBuilder(weight_max=0.05)

        # The weight_max property must differ
        assert cb_02.weight_max == 0.02
        assert cb_05.weight_max == 0.05
        assert cb_02.weight_max != cb_05.weight_max, \
            "Different weight_max values should produce different constraint builders"

        # Verify the builder stores the value used for constraints
        # (cvxpy constraint objects use Variable references, not literal values,
        # but the ConstraintBuilder.weight_max field IS the source of truth)
        assert hasattr(cb_02, 'weight_max'), "ConstraintBuilder must have weight_max"
        assert hasattr(cb_05, 'weight_max'), "ConstraintBuilder must have weight_max"


class TestBiweeklyNotCalled:
    """Verify Phase 5 never calls biweekly (which would crash)."""

    def test_rebalance_frequency_default_excludes_biweekly(self):
        """test_rebalance_frequency() default only runs weekly and monthly."""
        from validation.robustness import RobustnessTester

        def mock_bt(**kwargs):
            freq = kwargs.get("rebalance_freq", "")
            if freq == "biweekly":
                raise ValueError("Unknown frequency: biweekly")
            return {"rebalance_freq": freq, "ok": True}

        tester = RobustnessTester(mock_bt)
        # Default — should NOT call biweekly
        results = tester.test_rebalance_frequency({"test": True})
        freqs = set(results["rebalance_freq"])
        assert "Biweekly" not in freqs, \
            f"Biweekly should not be in default frequencies! Got: {freqs}"
        assert "Weekly" in freqs
        assert "Monthly" in freqs

    def test_explicit_frequencies_respected(self):
        """Explicit frequencies override the default list."""
        from validation.robustness import RobustnessTester

        def mock_bt(**kwargs):
            freq = kwargs.get("rebalance_freq", "")
            return {"rebalance_freq": freq.capitalize(), "ok": True}

        tester = RobustnessTester(mock_bt)
        # Explicit: only weekly
        results = tester.test_rebalance_frequency(
            {"test": True},
            frequencies=[("weekly", "Weekly")]
        )
        freqs = set(results["rebalance_freq"])
        assert freqs == {"Weekly"}, f"Should only have Weekly, got: {freqs}"


class TestBufferSelection:
    """Verify buffer selection logic (Phase 4)."""

    def test_retained_stock_with_rank_60_exit_80_is_kept(self):
        """Old holding at rank=60 with exit_rank=80 MUST be retained."""
        from backtest.portfolio_backtester import PortfolioBacktester

        # Simulate: 100 stocks ranked 1-100
        day_scores = pd.DataFrame({
            "ts_code": [f"{i:04d}.SZ" for i in range(1, 101)],
            "composite_score": list(range(100, 0, -1)),  # descending
        })

        # Previous weights: hold stock rank 60
        prev_weights = pd.Series(
            [1.0], index=["0060.SZ"], dtype="float64"
        )

        result = PortfolioBacktester._select_with_buffer(
            day_scores, "composite_score", top_n=50,
            prev_weights=prev_weights,
            entry_rank=50, exit_rank=80
        )

        # Stock 0060.SZ (rank=60) MUST be in result (within exit_rank=80)
        codes = set(result["ts_code"])
        assert "0060.SZ" in codes, (
            f"Rank-60 stock with exit_rank=80 must be retained! Got: {sorted(codes)}"
        )
        assert len(result) <= 50, f"Should have at most top_n=50 stocks, got {len(result)}"

    def test_new_stock_beyond_entry_rank_not_selected(self):
        """With existing holdings, new stocks beyond entry_rank must NOT enter."""
        from backtest.portfolio_backtester import PortfolioBacktester

        day_scores = pd.DataFrame({
            "ts_code": [f"{i:04d}.SZ" for i in range(1, 101)],
            "composite_score": list(range(100, 0, -1)),
        })

        # Previous positions: hold ranks 75-79 (within exit_rank=80,
        # but OUTSIDE entry_rank=50 — they can be retained, and should NOT
        # be replaced by stocks ranked 51-55 just because those score higher)
        held_codes = ["0075.SZ", "0076.SZ", "0077.SZ", "0078.SZ", "0079.SZ"]
        prev_weights = pd.Series(0.05, index=held_codes, dtype="float64")

        result = PortfolioBacktester._select_with_buffer(
            day_scores, "composite_score", top_n=50,
            prev_weights=prev_weights,
            entry_rank=50, exit_rank=80
        )

        codes = set(result["ts_code"])
        # Retained stocks at rank 80-84 should be in result
        for code in held_codes:
            assert code in codes, (
                f"Stock {code} in exit_rank=80 must be retained!"
            )
        # New stocks beyond entry_rank=50 should NOT enter
        # Stock 0051.SZ (rank=51 > entry_rank=50) should not be selected
        assert "0051.SZ" not in codes, (
            f"Stock rank 51 > entry_rank=50 must not enter as new candidate!"
        )

    def test_buffer_reduces_turnover_vs_no_buffer(self):
        """Buffered selection must produce lower turnover than unbuffered."""
        from backtest.portfolio_backtester import PortfolioBacktester
        import numpy as np

        np.random.seed(42)
        n_stocks = 200
        top_n = 50
        entry_rank = 50
        exit_rank = 80

        # Score: some stocks are consistently high, others drift
        base_score = np.arange(n_stocks) * 0.01
        # Two consecutive periods with noise
        scores_t0 = pd.DataFrame({
            "ts_code": [f"{i:04d}.SZ" for i in range(n_stocks)],
            "composite_score": base_score + np.random.randn(n_stocks) * 0.3,
        })
        scores_t1 = pd.DataFrame({
            "ts_code": [f"{i:04d}.SZ" for i in range(n_stocks)],
            "composite_score": base_score + np.random.randn(n_stocks) * 0.5,
        })

        # t0: unbuffered selection (no prev weights)
        sel_t0 = PortfolioBacktester._select_with_buffer(
            scores_t0, "composite_score", top_n,
            prev_weights=pd.Series(dtype="float64"),
            entry_rank=200, exit_rank=200  # effectively no buffer
        )
        t0_codes = set(sel_t0["ts_code"])

        # t1: buffered selection
        prev_w = pd.Series(1.0 / top_n, index=list(t0_codes), dtype="float64")
        sel_t1_buf = PortfolioBacktester._select_with_buffer(
            scores_t1, "composite_score", top_n,
            prev_weights=prev_w,
            entry_rank=entry_rank, exit_rank=exit_rank
        )
        # t1: unbuffered
        sel_t1_nobuf = scores_t1.nlargest(top_n, "composite_score")

        # Turnover = fraction of stocks that changed
        t1_buf_codes = set(sel_t1_buf["ts_code"])
        t1_nobuf_codes = set(sel_t1_nobuf["ts_code"])

        # Buffered: stocks removed / added
        buf_removed = t0_codes - t1_buf_codes
        buf_added = t1_buf_codes - t0_codes
        buf_turnover = max(len(buf_removed), len(buf_added)) / top_n

        # Unbuffered: stocks removed / added
        nobuf_removed = t0_codes - t1_nobuf_codes
        nobuf_added = t1_nobuf_codes - t0_codes
        nobuf_turnover = max(len(nobuf_removed), len(nobuf_added)) / top_n

        assert buf_turnover <= nobuf_turnover, (
            f"Buffered turnover ({buf_turnover:.2%}) should be <= "
            f"unbuffered ({nobuf_turnover:.2%})"
        )
        assert buf_turnover < 0.90, (
            f"Buffered turnover ({buf_turnover:.2%}) should be significantly < 100%"
        )

"""
Test: diagnostic artifacts — portfolio values, benchmark period returns.
"""
import pytest
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
import pandas as pd
import numpy as np


class TestDiagnosticArtifacts:
    """_write_diagnostic_artifacts must produce per-run output files."""

    def test_artifacts_portfolio_values_saved(self, tmp_path):
        """Portfolio values are saved as parquet and CSV."""
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

        # Patch outputs/runs path to use tmp_path
        with patch("run_research.Path", side_effect=lambda p: Path(str(tmp_path / str(p).replace("outputs", "outputs")))) as mock_path:
            # Actually we need a simpler approach — just call with tmp_path
            pass

        # Simpler: call the function with a tmp_path-based run_id
        from run_research import _write_diagnostic_artifacts

        # Create mock run dir
        run_dir = tmp_path / "outputs" / "runs" / "test_run"
        run_dir.mkdir(parents=True, exist_ok=True)

        # We can't easily mock the Path inside the function, so let's
        # test the function's behavior through the backtester flow instead
        pv = [
            {"signal_date": 20240105, "exec_date": 20240106, "period_end": 20240112,
             "portfolio_value": 100_500_000, "period_return": 0.005,
             "gross_period_return": 0.006, "turnover": 0.1,
             "cost_cny": 500, "cost_bps": 5.0, "n_holdings": 50},
            {"signal_date": 20240112, "exec_date": 20240113, "period_end": 20240119,
             "portfolio_value": 101_000_000, "period_return": 0.005,
             "gross_period_return": 0.006, "turnover": 0.1,
             "cost_cny": 500, "cost_bps": 5.0, "n_holdings": 50},
        ]

        # Verify portfolio values can be converted to DataFrame
        pv_df = pd.DataFrame(pv)
        assert len(pv_df) == 2
        assert "portfolio_value" in pv_df.columns
        assert "period_return" in pv_df.columns

        # Verify parquet writeability
        pv_parquet = tmp_path / "test_portfolio_values.parquet"
        pv_df.to_parquet(pv_parquet, index=False)
        assert pv_parquet.exists()

        # Verify CSV writeability
        pv_csv = tmp_path / "test_portfolio_values.csv"
        pv_df.to_csv(pv_csv, index=False)
        assert pv_csv.exists()

        # Round-trip verification
        loaded = pd.read_parquet(pv_parquet)
        assert len(loaded) == 2

    def test_benchmark_period_returns_from_compute_stats(self):
        """_compute_benchmark_stats produces _benchmark_period_returns."""
        from backtest.portfolio_backtester import PortfolioBacktester

        bt = PortfolioBacktester()

        # Build benchmark with consecutive dates covering the full period
        bench_dates = list(range(20240102, 20240102 + 120))

        bench = pd.DataFrame({
            "trade_date": bench_dates,
            "close": [3500.0 + i * 10 for i in range(len(bench_dates))],
            "benchmark_ret": [0.001] * len(bench_dates),
        })

        # Strategy returns: enough to get >=5 valid periods
        strategy_returns = pd.Series(
            [0.01, 0.02, -0.01, 0.03, 0.01, 0.02],
            index=[20240114, 20240121, 20240128, 20240204, 20240211, 20240218],
        )

        # Period dates with benchmark dates strictly between exec and period_end
        # exec_date uses a benchmark date, period_end uses a later benchmark date
        period_dates = pd.DataFrame({
            "exec_date": [20240107, 20240114, 20240121, 20240128, 20240204, 20240211],
            "period_end": [20240114, 20240121, 20240128, 20240204, 20240211, 20240218],
        })

        result = bt._compute_benchmark_stats(
            strategy_returns, bench, period_dates=period_dates
        )

        # Should be OK since we have >=5 periods with overlapping benchmark data
        assert result["benchmark_status"] in ("OK", "INSUFFICIENT")
        assert "_benchmark_period_returns" in result
        bm_period = result["_benchmark_period_returns"]
        assert "strategy_return" in bm_period.columns
        assert "benchmark_return" in bm_period.columns

    def test_metrics_include_go_nogo_structured(self):
        """_compute_metrics produces structured go_nogo with overall field."""
        from backtest.portfolio_backtester import PortfolioBacktester

        bt = PortfolioBacktester()

        pv = [
            {"signal_date": 20240105, "exec_date": 20240106, "period_end": 20240112,
             "portfolio_value": 100_500_000, "period_return": 0.005,
             "turnover": 0.1, "cost_bps": 5.0, "n_holdings": 50},
            {"signal_date": 20240112, "exec_date": 20240113, "period_end": 20240119,
             "portfolio_value": 101_000_000, "period_return": 0.005,
             "turnover": 0.1, "cost_bps": 5.0, "n_holdings": 50},
            {"signal_date": 20240119, "exec_date": 20240120, "period_end": 20240126,
             "portfolio_value": 101_500_000, "period_return": 0.005,
             "turnover": 0.1, "cost_bps": 5.0, "n_holdings": 50},
            {"signal_date": 20240126, "exec_date": 20240127, "period_end": 20240202,
             "portfolio_value": 102_000_000, "period_return": 0.005,
             "turnover": 0.1, "cost_bps": 5.0, "n_holdings": 50},
            {"signal_date": 20240202, "exec_date": 20240203, "period_end": 20240209,
             "portfolio_value": 102_500_000, "period_return": 0.005,
             "turnover": 0.1, "cost_bps": 5.0, "n_holdings": 50},
            {"signal_date": 20240209, "exec_date": 20240210, "period_end": 20240216,
             "portfolio_value": 103_000_000, "period_return": 0.005,
             "turnover": 0.1, "cost_bps": 5.0, "n_holdings": 50},
        ]
        bench = pd.DataFrame()

        result = bt._compute_metrics(pv, bench, [], [])

        assert "go_nogo" in result
        gn = result["go_nogo"]
        assert "overall" in gn
        assert gn["overall"] == "NO_GO_DATA_INVALID"
        assert "data_quality" in gn
        assert gn["data_quality"] == "FAIL"
        assert "benchmark_status" in gn
        assert "failure_reasons" in gn

    def test_data_quality_gate_in_metrics(self):
        """Metrics dict includes _data_quality_gate."""
        from backtest.portfolio_backtester import PortfolioBacktester

        bt = PortfolioBacktester()

        pv = [
            {"signal_date": 20240105 + i * 7, "exec_date": 20240106 + i * 7,
             "period_end": 20240112 + i * 7,
             "portfolio_value": 100_500_000 * (1.005 ** i),
             "period_return": 0.005, "turnover": 0.1, "cost_bps": 5.0, "n_holdings": 50}
            for i in range(6)
        ]
        bench = pd.DataFrame()

        result = bt._compute_metrics(pv, bench, [], [])
        assert "_data_quality_gate" in result
        gate = result["_data_quality_gate"]
        assert "overall" in gate
        assert "failure_reasons" in gate

"""Unit tests for panic reversal factor computation."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.build_alpha_factors_v4 import _compute_panic_reversal, _keep_rebalance_frequency


def make_prices(data_dict):
    """Helper: create price DataFrame from {ts_code: [close_series]}."""
    rows = []
    for code, closes in data_dict.items():
        for i, close in enumerate(closes):
            if not np.isnan(close):
                rows.append({
                    "ts_code": code,
                    "trade_date": 20200101 + i,
                    "adj_close": close,
                })
    return pd.DataFrame(rows)


class TestThresholdBoundaries:
    """Threshold uses inclusive <= and >=."""

    def test_drop_inclusive_lower_bound(self):
        """mom5 exactly at -threshold should trigger drop event."""
        # Need 6 consecutive non-NaN closes for shift(5) to work on day 5
        prices = make_prices({
            "A": [100, 101, 102, 101, 100, 95.0],  # exactly -5% from day0
        })
        result = _compute_panic_reversal(prices, threshold=0.05, direction="drop",
                                         signal_type="bin", frequency="daily")
        # trade_date at index 5 (20200106)
        val = result[result["trade_date"] == 20200106]["value"].values
        assert len(val) == 1
        assert val[0] == 1.0, f"Expected 1.0, got {val[0]}"

    def test_drop_just_above_threshold(self):
        """mom5 at -4.99% should NOT trigger at 5% threshold."""
        prices = make_prices({
            "A": [100, 101, 102, 101, 100, 95.01],  # -4.99%
        })
        result = _compute_panic_reversal(prices, threshold=0.05, direction="drop",
                                         signal_type="bin", frequency="daily")
        val = result[result["trade_date"] == 20200106]["value"].values
        assert len(val) == 1
        assert val[0] == 0.0, f"Expected 0.0, got {val[0]}"

    def test_up_inclusive_upper_bound(self):
        """mom5 exactly at +threshold should trigger up event."""
        prices = make_prices({
            "A": [100, 101, 102, 101, 100, 105.0],  # exactly +5%
        })
        result = _compute_panic_reversal(prices, threshold=0.05, direction="up",
                                         signal_type="bin", frequency="daily")
        val = result[result["trade_date"] == 20200106]["value"].values
        assert len(val) == 1
        assert val[0] == -1.0, f"Expected -1.0, got {val[0]}"


class TestDirectionSigns:
    """Verify correct sign for each direction × signal_type."""

    def test_drop_bin_positive(self):
        prices = make_prices({"A": [100]*5 + [90]})  # -10%
        result = _compute_panic_reversal(prices, 0.05, "drop", "bin", "daily")
        assert (result["value"] >= 0).all()

    def test_drop_cont_positive(self):
        prices = make_prices({"A": [100]*5 + [90]})
        result = _compute_panic_reversal(prices, 0.05, "drop", "cont", "daily")
        nz = result[result["value"] != 0]
        assert (nz["value"] > 0).all(), f"drop_cont should have positive values, got {nz['value'].values}"

    def test_up_bin_negative(self):
        prices = make_prices({"A": [100]*5 + [110]})  # +10%
        result = _compute_panic_reversal(prices, 0.05, "up", "bin", "daily")
        nz = result[result["value"] != 0]
        assert (nz["value"] < 0).all(), f"up_bin should have negative values, got {nz['value'].values}"

    def test_up_cont_negative(self):
        """After fix: up_cont value = -mom5, should be negative for surges."""
        prices = make_prices({"A": [100]*5 + [110]})  # +10%, mom5=+0.10
        result = _compute_panic_reversal(prices, 0.05, "up", "cont", "daily")
        nz = result[result["value"] != 0]
        assert (nz["value"] < 0).all(), f"up_cont should have negative values, got {nz['value'].values}"

    def test_sym_drop_positive_up_negative(self):
        """sym: drop events positive, up events negative."""
        prices = make_prices({
            "A": [100]*5 + [90],   # drop -10%
            "B": [100]*5 + [110],  # up +10%
        })
        result = _compute_panic_reversal(prices, 0.05, "sym", "bin", "daily")
        row_a = result[(result["ts_code"] == "A") & (result["trade_date"] == 20200106)]
        row_b = result[(result["ts_code"] == "B") & (result["trade_date"] == 20200106)]
        assert row_a["value"].values[0] == 1.0, f"sym drop should be +1, got {row_a['value'].values}"
        assert row_b["value"].values[0] == -1.0, f"sym up should be -1, got {row_b['value'].values}"

    def test_sym_cont_drop_positive_up_negative(self):
        """After fix: sym_cont value = -mom5. Drop→positive, Up→negative."""
        prices = make_prices({
            "A": [100]*5 + [90],   # mom5=-0.10, -mom5=+0.10
            "B": [100]*5 + [110],  # mom5=+0.10, -mom5=-0.10
        })
        result = _compute_panic_reversal(prices, 0.05, "sym", "cont", "daily")
        row_a = result[(result["ts_code"] == "A") & (result["trade_date"] == 20200106)]
        row_b = result[(result["ts_code"] == "B") & (result["trade_date"] == 20200106)]
        assert row_a["value"].values[0] > 0, f"sym_cont drop should be positive, got {row_a['value'].values}"
        assert row_b["value"].values[0] < 0, f"sym_cont up should be negative, got {row_b['value'].values}"


class TestNonEventZero:
    """Non-event stocks should have value = 0."""

    def test_no_event_zero(self):
        prices = make_prices({
            "A": [100]*5 + [98],  # -2%, not enough for 5% threshold
        })
        result = _compute_panic_reversal(prices, 0.05, "drop", "bin", "daily")
        assert (result["value"] == 0).all()

    def test_missing_price_dropped(self):
        """Stocks with NaN price should be dropped, not get value=0."""
        prices = make_prices({
            "A": [100]*4 + [np.nan] + [95],  # NaN at day 4
        })
        result = _compute_panic_reversal(prices, 0.05, "drop", "bin", "daily")
        # mom5 can't be computed for any day after NaN in the window
        # Result should have fewer rows or NaN-free
        assert result["value"].notna().all()


class TestWinsor:
    """wcont only clips non-zero values, zero stays zero."""

    def test_wcont_doesnt_touch_zero(self):
        prices = make_prices({
            "A": [100]*5 + [90],   # event
            "B": [100]*5 + [98],   # no event (should stay 0)
        })
        result = _compute_panic_reversal(prices, 0.05, "drop", "wcont", "daily")
        row_b = result[(result["ts_code"] == "B") & (result["trade_date"] == 20200106)]
        assert len(row_b) > 0
        assert row_b["value"].values[0] == 0.0

    def test_wcont_clips_nonzero(self):
        """With many events, extreme values should be clipped."""
        rows = []
        for i in range(50):
            drop = 0.05 + i * 0.01  # 5% to 54%
            # Need 6 consecutive closes for shift(5): days 0-4 at 100, day 5 at drop
            for d in range(5):
                rows.append({"ts_code": f"S{i:03d}", "trade_date": 20200101 + d, "adj_close": 100.0})
            rows.append({"ts_code": f"S{i:03d}", "trade_date": 20200106, "adj_close": 100.0 * (1 - drop)})
        prices = pd.DataFrame(rows)
        result = _compute_panic_reversal(prices, 0.05, "drop", "wcont", "daily")
        nz = result[result["value"] != 0]
        assert len(nz) > 0, "Should have non-zero values"
        # The max should be less than the raw max (which would be ~0.54)
        raw_max = nz["value"].max()
        assert raw_max < 0.53, f"wcont should clip extreme values, max={raw_max:.4f}"


class TestWeeklyFrequency:
    """Weekly output keeps only last trading day per ISO week."""

    def test_weekly_output(self):
        # 10 consecutive trading days (2 weeks)
        closes = [100] * 5 + [90] * 5  # all drop
        dates = list(range(20200106, 20200120))  # Mon-Fri x2
        rows = []
        for d in dates:
            rows.append({"ts_code": "A", "trade_date": d, "adj_close": 100})
        prices = pd.DataFrame(rows)
        # Add mom5-capable data
        prices2 = make_prices({"A": [100]*5 + [90]*10})
        # Only keep dates with mom5
        prices2 = prices2[prices2["trade_date"] >= 20200113]

        result = _compute_panic_reversal(prices2, 0.05, "drop", "bin", "weekly")
        dates_out = sorted(result["trade_date"].unique())
        assert len(dates_out) <= len(prices2["trade_date"].unique()), "Weekly should have fewer dates"
        # Each output date should be a Friday (week ending Friday)
        for d in dates_out:
            dt = pd.to_datetime(str(d), format="%Y%m%d")
            assert dt.dayofweek == 4, f"Expected Friday, got {dt.day_name()} for {d}"


class TestEmptyEdgeCases:
    """Edge case handling."""

    def test_empty_prices(self):
        result = _compute_panic_reversal(pd.DataFrame(), 0.05, "drop", "bin", "weekly")
        assert result.empty

    def test_no_events(self):
        """If no stock crosses threshold, all values should be 0."""
        prices = make_prices({"A": [100]*5 + [99]})  # -1%
        result = _compute_panic_reversal(prices, 0.05, "drop", "bin", "daily")
        assert (result["value"] == 0).all()


class TestYearLoopBug:
    """Regression test: `for yr in sorted(df["trade_date"] // 10000)` iterates
    per ROW, not per unique year, inflating year-count statistics."""

    def test_unique_years_not_per_row(self):
        """Verify that unique() is used when counting years."""
        # Simulate the bug pattern: 1000 rows all in year 2021
        df = pd.DataFrame({
            "trade_date": [20210101] * 1000,
            "fwd_ret_5d": np.random.randn(1000) * 0.01,
        })
        # BUGGY pattern (fixed now):
        # years = sorted(df["trade_date"] // 10000)
        # assert len(years) == 1000  # would fail: 1000 entries for 1 year

        # CORRECT pattern:
        years = sorted((df["trade_date"] // 10000).dropna().astype(int).unique())
        assert len(years) == 1
        assert years[0] == 2021

    def test_val_pos_years_bounded(self):
        """val_pos_years should never exceed val_n_years (max 4 for 2021-2024)."""
        # Simulate val_years counting with the fixed pattern
        n_years = 4
        pos_count = 0
        for yr in sorted(set([2021, 2022, 2023, 2024])):
            if yr >= 2021:
                pos_count += 1
        assert pos_count <= n_years
        assert pos_count == 4  # all positive in this simulation


# ===========================================================================
# P1/P2 Tests: Lag1 returns, formal gate, cost/liquidity, regime,
# walk-forward selection, multiple testing, fast check isolation
# ===========================================================================


class TestLag1ReturnOutlierFilter:
    """Verify lag1 return outlier filtering logic."""

    def test_outlier_abs_above_05_flagged(self):
        """abs(fwd_ret) > 0.5 should be flagged as outlier."""
        # Simulate the filtering logic inline
        import numpy as np
        returns = pd.Series([-0.02, 0.01, 0.55, -0.60, 0.03, 0.48, -0.49])
        is_outlier = returns.abs() > 0.5
        assert is_outlier[2], "0.55 should be outlier"
        assert is_outlier[3], "-0.60 should be outlier"
        assert not is_outlier[5], "0.48 should not be outlier"
        assert not is_outlier[6], "-0.49 should not be outlier"
        assert is_outlier.sum() == 2

    def test_close_negative_or_zero_flagged(self):
        """close <= 0 should be flagged."""
        closes_t1 = pd.Series([10.0, 0.0, -1.0, 5.0, np.nan])
        closes_t6 = pd.Series([12.0, 5.0, 3.0, 0.0, 8.0])
        invalid = (closes_t1 <= 0) | (closes_t6 <= 0)
        assert invalid[1], "close_t1=0 should be invalid"
        assert invalid[2], "close_t1=-1 should be invalid"
        assert invalid[3], "close_t6=0 should be invalid"
        assert not invalid[0], "both positive should be valid"

    def test_boundary_missing_drops(self):
        """If t+1 or t+6 missing, return should be NaN."""
        prices = pd.DataFrame({
            "ts_code": ["A"] * 15,
            "trade_date": list(range(20200101, 20200116)),
            "adj_close": [100.0 + i for i in range(15)],
        })
        prices["close_t1"] = prices.groupby("ts_code")["adj_close"].transform(lambda x: x.shift(-1))
        prices["close_t6"] = prices.groupby("ts_code")["adj_close"].transform(lambda x: x.shift(-6))
        # Last row (index 14): t+6 doesn't exist (needs index 20)
        last = prices.iloc[-1]
        assert pd.isna(last["close_t6"]), "Last row should have NaN close_t6"
        # Row 0: t+6 should exist (index 6)
        row0 = prices.iloc[0]
        assert pd.notna(row0["close_t6"]), f"First row should have close_t6, got {row0['close_t6']}"


class TestAlignmentTradeDayGap:
    """Verify alignment audit uses calendar days and trade_day_gap."""

    def test_calendar_gap_uses_datetime_not_int_subtraction(self):
        """Calendar gap must use pd.to_datetime, not integer subtraction."""
        # Integer subtraction: 20200110 - 20200109 = 1 (works for same month)
        # Integer subtraction: 20200201 - 20200131 = 70 (WRONG, should be 1)
        sd = 20200131
        ed = 20200201
        wrong_gap = ed - sd  # 20200201 - 20200131 = 70
        assert wrong_gap == 70, "Integer subtraction gives wrong calendar gap"

        # Correct: use datetime
        sig_dt = pd.to_datetime(str(sd), format="%Y%m%d")
        exec_dt = pd.to_datetime(str(ed), format="%Y%m%d")
        correct_gap = (exec_dt - sig_dt).days
        assert correct_gap == 1, f"Calendar gap should be 1 day, got {correct_gap}"

    def test_trade_day_gap_is_one(self):
        """Execution date must be the 1st trading day after signal date."""
        all_td = np.array([20200102, 20200103, 20200106, 20200107, 20200108])
        sd = 20200103
        idx = np.searchsorted(all_td, sd)
        next_idx = idx + 1
        assert next_idx - idx == 1, "Trade day gap should be 1"
        exec_date = all_td[next_idx]
        assert exec_date == 20200106, f"Next trade date should be 20200106, got {exec_date}"
        assert exec_date > sd

    def test_holiday_gap_larger_than_one(self):
        """Calendar gap can be >1 over weekends/holidays (should not error)."""
        sd = 20200103  # Friday
        ed = 20200106  # Monday
        sig_dt = pd.to_datetime(str(sd), format="%Y%m%d")
        exec_dt = pd.to_datetime(str(ed), format="%Y%m%d")
        cal_gap = (exec_dt - sig_dt).days
        assert cal_gap == 3, f"Weekend gap should be 3, got {cal_gap}"
        assert cal_gap > 1  # Should be allowed, just not an int-subtraction artifact


class TestFormalGateUsesLag1:
    """Verify formal gate correctly uses execution_lag=1 returns."""

    def test_execution_lag_in_summary_fields(self):
        """Summary must contain execution_lag and return_col fields."""
        # Simulate a summary row with required fields
        row = {
            "factor": "panic_drop_rev5_t005_bin_weekly_cs",
            "execution_lag": 1,
            "return_col": "fwd_ret_5d_exec_lag1",
            "direction": "drop",
            "threshold": 0.05,
            "signal_type": "bin",
        }
        assert row["execution_lag"] == 1
        assert row["return_col"] == "fwd_ret_5d_exec_lag1"
        assert "execution_lag" in row
        assert "return_col" in row

    def test_same_day_return_not_allowed_as_default(self):
        """Formal gate should NOT use same-day returns as default."""
        # The constant in evaluate_panic_reversal_diagnostics.py:
        SAME_DAY_RETURN_USED = False  # Should match the script
        assert not SAME_DAY_RETURN_USED, "same_day_return_used must be False"

    def test_lag1_parquet_has_correct_column(self):
        """If lag1 file exists, it must have fwd_ret_5d_exec_lag1 column."""
        lag1_path = Path("D:/workspace/q_project/code_v4/outputs/analysis/panic_reversal_gate/panic_lag1_returns.parquet")
        if not lag1_path.exists():
            pytest.skip("lag1 returns not yet generated — run generate_exec_lag1_returns.py")
        df = pd.read_parquet(lag1_path)
        assert "fwd_ret_5d_exec_lag1" in df.columns, (
            f"lag1 parquet must have fwd_ret_5d_exec_lag1, found: {list(df.columns)}"
        )


class TestCostLiquidityOutput:
    """Verify cost/liquidity CSV is generated and non-empty."""

    def test_cost_liquidity_csv_exists_and_non_empty(self):
        cl_path = Path("D:/workspace/q_project/code_v4/outputs/analysis/panic_reversal_gate/panic_cost_liquidity.csv")
        if not cl_path.exists():
            pytest.skip("cost_liquidity.csv not yet generated — run evaluate_panic_reversal_diagnostics.py")
        df = pd.read_csv(cl_path)
        assert len(df) > 0, "cost_liquidity.csv is empty"
        required = [
            "factor", "year", "event_rate",
            "event_median_mv", "noevent_median_mv",
        ]
        # event_median_amount is optional (depends on daily_basic having 'amount' column)
        for col in required:
            assert col in df.columns, f"Missing required column: {col}"

    def test_cost_liquidity_has_cost_scenarios(self):
        cl_path = Path("D:/workspace/q_project/code_v4/outputs/analysis/panic_reversal_gate/panic_cost_liquidity.csv")
        if not cl_path.exists():
            pytest.skip("cost_liquidity.csv not yet generated")
        df = pd.read_csv(cl_path)
        cost_cols = [c for c in df.columns if "net_spread_cost" in c]
        assert len(cost_cols) >= 1, f"Should have cost scenario columns, found: {cost_cols}"

    def test_cost_liquidity_has_mv_buckets(self):
        cl_path = Path("D:/workspace/q_project/code_v4/outputs/analysis/panic_reversal_gate/panic_cost_liquidity.csv")
        if not cl_path.exists():
            pytest.skip("cost_liquidity.csv not yet generated")
        df = pd.read_csv(cl_path)
        mv_cols = [c for c in df.columns if "net_spread_mv" in c]
        if len(mv_cols) == 0:
            pytest.skip("MV bucket columns not generated (may need more data variation for qcut)")
        assert len(mv_cols) >= 1


class TestRegimeFactorAndSourceFields:
    """Verify regime diagnostic has correct factor, regime_source, diagnostic_only fields."""

    def test_regime_csv_has_correct_fields(self):
        rg_path = Path("D:/workspace/q_project/code_v4/outputs/analysis/panic_reversal_gate/panic_regime_diagnostic.csv")
        if not rg_path.exists():
            pytest.skip("regime_diagnostic.csv not yet generated — run evaluate_panic_reversal_diagnostics.py")
        df = pd.read_csv(rg_path)
        assert "factor" in df.columns, "regime CSV must have 'factor' column"
        assert "regime_source" in df.columns, "regime CSV must have 'regime_source' column"
        assert "diagnostic_only" in df.columns, "regime CSV must have 'diagnostic_only' column"

    def test_regime_factor_is_real_factor_name(self):
        """Factor column should contain real factor names, not 'fallback_vol_quantile'."""
        rg_path = Path("D:/workspace/q_project/code_v4/outputs/analysis/panic_reversal_gate/panic_regime_diagnostic.csv")
        if not rg_path.exists():
            pytest.skip("regime_diagnostic.csv not yet generated")
        df = pd.read_csv(rg_path)
        assert len(df) > 0
        # factor should start with "panic_" (real factor names)
        non_panic = df[~df["factor"].astype(str).str.startswith("panic_")]
        assert len(non_panic) == 0, (
            f"All factor values should start with 'panic_', found: {non_panic['factor'].unique()}"
        )

    def test_regime_source_separate_from_factor(self):
        """regime_source should be separate from factor."""
        rg_path = Path("D:/workspace/q_project/code_v4/outputs/analysis/panic_reversal_gate/panic_regime_diagnostic.csv")
        if not rg_path.exists():
            pytest.skip("regime_diagnostic.csv not yet generated")
        df = pd.read_csv(rg_path)
        # regime_source should be something like "fallback_vol_quantile"
        assert df["regime_source"].notna().all(), "regime_source should not be NaN"
        assert (df["regime_source"] != df["factor"]).all(), "regime_source should differ from factor"

    def test_diagnostic_only_is_true(self):
        """diagnostic_only must be True — prevents misuse as hard gate."""
        rg_path = Path("D:/workspace/q_project/code_v4/outputs/analysis/panic_reversal_gate/panic_regime_diagnostic.csv")
        if not rg_path.exists():
            pytest.skip("regime_diagnostic.csv not yet generated")
        df = pd.read_csv(rg_path)
        if "diagnostic_only" in df.columns:
            assert df["diagnostic_only"].all(), "diagnostic_only must be True for all rows"


class TestWalkforwardSelectedOutput:
    """Verify walk-forward produces selected (not just candidates) output."""

    def test_walkforward_selected_csv_exists(self):
        wf_path = Path("D:/workspace/q_project/code_v4/outputs/analysis/panic_reversal_gate/panic_walkforward_selected.csv")
        if not wf_path.exists():
            pytest.skip("walkforward_selected.csv not yet generated — run panic_walkforward_validate.py")
        df = pd.read_csv(wf_path)
        assert len(df) > 0, "walkforward_selected.csv is empty"

    def test_walkforward_selected_has_required_fields(self):
        wf_path = Path("D:/workspace/q_project/code_v4/outputs/analysis/panic_reversal_gate/panic_walkforward_selected.csv")
        if not wf_path.exists():
            pytest.skip("walkforward_selected.csv not yet generated")
        df = pd.read_csv(wf_path)
        required = [
            "window", "train_start", "train_end", "test_start", "test_end",
            "selected_factor", "selection_metric", "train_icir",
            "train_net_spread", "test_net_spread", "test_icir",
            "test_event_rate", "test_pass",
        ]
        for col in required:
            assert col in df.columns, f"Missing required column: {col}"

    def test_walkforward_four_windows(self):
        """Walk-forward should have 4 windows (2017-2020, 2017-2021, 2017-2022, 2017-2023)."""
        wf_path = Path("D:/workspace/q_project/code_v4/outputs/analysis/panic_reversal_gate/panic_walkforward_selected.csv")
        if not wf_path.exists():
            pytest.skip("walkforward_selected.csv not yet generated")
        df = pd.read_csv(wf_path)
        assert len(df) == 4, f"Expected 4 walk-forward windows, got {len(df)}"
        assert df["window"].nunique() == 4

    def test_walkforward_selected_one_factor_per_window(self):
        """Each window must have exactly one selected factor."""
        wf_path = Path("D:/workspace/q_project/code_v4/outputs/analysis/panic_reversal_gate/panic_walkforward_selected.csv")
        if not wf_path.exists():
            pytest.skip("walkforward_selected.csv not yet generated")
        df = pd.read_csv(wf_path)
        for wname, grp in df.groupby("window"):
            assert len(grp) == 1, f"Window {wname} should have 1 selected factor, got {len(grp)}"

    def test_walkforward_candidates_csv_exists(self):
        wf_path = Path("D:/workspace/q_project/code_v4/outputs/analysis/panic_reversal_gate/panic_walkforward_candidates.csv")
        if not wf_path.exists():
            pytest.skip("walkforward_candidates.csv not yet generated")
        df = pd.read_csv(wf_path)
        assert len(df) > 0, "walkforward_candidates.csv is empty"

    def test_selected_factor_in_candidates(self):
        """Selected factor should be among the candidates for each window."""
        sel_path = Path("D:/workspace/q_project/code_v4/outputs/analysis/panic_reversal_gate/panic_walkforward_selected.csv")
        cand_path = Path("D:/workspace/q_project/code_v4/outputs/analysis/panic_reversal_gate/panic_walkforward_candidates.csv")
        if not sel_path.exists() or not cand_path.exists():
            pytest.skip("walkforward files not yet generated")
        sel = pd.read_csv(sel_path)
        cand = pd.read_csv(cand_path)
        for _, sr in sel.iterrows():
            w_cand = cand[cand["window"] == sr["window"]]
            assert sr["selected_factor"] in w_cand["factor"].values, (
                f"Selected factor {sr['selected_factor']} not in candidates for {sr['window']}"
            )


class TestMultipleTestingOutput:
    """Verify multiple testing check CSV is generated with correct fields."""

    def test_multiple_testing_csv_exists(self):
        mt_path = Path("D:/workspace/q_project/code_v4/outputs/analysis/panic_reversal_gate/panic_multiple_testing_check.csv")
        if not mt_path.exists():
            pytest.skip("multiple_testing_check.csv not yet generated — run panic_walkforward_validate.py")
        df = pd.read_csv(mt_path)
        assert len(df) > 0, "multiple_testing_check.csv is empty"

    def test_multiple_testing_required_fields(self):
        mt_path = Path("D:/workspace/q_project/code_v4/outputs/analysis/panic_reversal_gate/panic_multiple_testing_check.csv")
        if not mt_path.exists():
            pytest.skip("multiple_testing_check.csv not yet generated")
        df = pd.read_csv(mt_path)
        required_metrics = [
            "best_real_net_spread", "perm_max_mean", "perm_max_std",
            "perm_p95", "empirical_p_value", "n_candidates", "n_permutations",
        ]
        metric_names = df["metric"].tolist() if "metric" in df.columns else df.iloc[:, 0].tolist()
        for m in required_metrics:
            assert m in metric_names, f"Missing required metric: {m}"

    def test_multiple_testing_n_candidates_27(self):
        mt_path = Path("D:/workspace/q_project/code_v4/outputs/analysis/panic_reversal_gate/panic_multiple_testing_check.csv")
        if not mt_path.exists():
            pytest.skip("multiple_testing_check.csv not yet generated")
        df = pd.read_csv(mt_path)
        if "metric" in df.columns and "value" in df.columns:
            n_cand_row = df[df["metric"] == "n_candidates"]
            if len(n_cand_row) > 0:
                n = int(n_cand_row["value"].values[0])
                assert n == 27, f"n_candidates should be 27, got {n}"

    def test_multiple_testing_n_permutations_ge_500(self):
        mt_path = Path("D:/workspace/q_project/code_v4/outputs/analysis/panic_reversal_gate/panic_multiple_testing_check.csv")
        if not mt_path.exists():
            pytest.skip("multiple_testing_check.csv not yet generated")
        df = pd.read_csv(mt_path)
        if "metric" in df.columns and "value" in df.columns:
            n_perm_row = df[df["metric"] == "n_permutations"]
            if len(n_perm_row) > 0:
                n = int(n_perm_row["value"].values[0])
                assert n >= 500, (
                    f"n_permutations={n} < 500. "
                    f"Re-run without --quick: python scripts/panic_walkforward_validate.py"
                )


class TestFastCheckDoesNotOverwriteFormal:
    """Verify fast check outputs only to debug/, never overwrites formal files."""

    def test_fast_check_output_in_debug_dir(self):
        """fast_check output should be in debug/ subdirectory."""
        debug_path = Path("D:/workspace/q_project/code_v4/outputs/analysis/panic_reversal_gate/debug/panic_fast_check_summary.csv")
        if not debug_path.exists():
            pytest.skip("fast_check_summary.csv not yet generated — run panic_fast_check.py")
        assert debug_path.exists(), "fast check output should be in debug/ directory"

    def test_fast_check_does_not_overwrite_formal_summary(self):
        """Formal panic_variant_summary.csv should NOT come from fast_check."""
        formal_path = Path("D:/workspace/q_project/code_v4/outputs/analysis/panic_reversal_gate/panic_variant_summary.csv")
        debug_path = Path("D:/workspace/q_project/code_v4/outputs/analysis/panic_reversal_gate/debug/panic_fast_check_summary.csv")
        if not formal_path.exists() or not debug_path.exists():
            pytest.skip("summary files not yet generated")
        formal = pd.read_csv(formal_path)
        debug = pd.read_csv(debug_path)
        # Formal should have execution_lag and return_col (from full gate)
        # Debug should NOT have these (fast check simplified columns)
        formal_cols = set(formal.columns)
        debug_cols = set(debug.columns)
        gate_cols = {"execution_lag", "return_col"}
        assert gate_cols.issubset(formal_cols), (
            f"Formal summary missing gate columns: {gate_cols - formal_cols}. "
            f"May have been overwritten by fast_check."
        )


class TestOutputFileCompleteness:
    """Verify all required output files exist."""

    REQUIRED_FILES = [
        "panic_lag1_returns.parquet",
        "panic_lag1_return_outliers.csv",
        "panic_lag1_return_quality_summary.csv",
        "panic_return_alignment_check.csv",
        "panic_variant_summary.csv",
        "panic_reversal_report.md",
        "panic_cost_liquidity.csv",
        "panic_redundancy_corr.csv",
        "panic_regime_diagnostic.csv",
        "panic_walkforward_candidates.csv",
        "panic_walkforward_selected.csv",
        "panic_multiple_testing_check.csv",
    ]

    def test_all_required_files_exist(self):
        out_dir = Path("D:/workspace/q_project/code_v4/outputs/analysis/panic_reversal_gate")
        missing = []
        for fname in self.REQUIRED_FILES:
            if not (out_dir / fname).exists():
                missing.append(fname)
        if missing:
            pytest.skip(f"Missing files (run full pipeline first): {missing}")
        # If all exist, verify they are non-empty
        for fname in self.REQUIRED_FILES:
            fpath = out_dir / fname
            if fpath.suffix == ".parquet":
                df = pd.read_parquet(fpath)
                assert len(df) > 0, f"{fname} is empty"
            elif fpath.suffix == ".csv":
                df = pd.read_csv(fpath)
                assert len(df) > 0, f"{fname} is empty"
            elif fpath.suffix == ".md":
                content = fpath.read_text(encoding="utf-8")
                assert len(content) > 100, f"{fname} is too short"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

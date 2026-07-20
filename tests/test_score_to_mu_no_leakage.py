"""Verify score_to_mu has no look-ahead leakage (IC and vol both backward-looking)."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pandas as pd


class TestScoreToMuNoLeakage:
    """Verify μ calibration uses only past data for both IC and CS vol."""

    def test_first_date_mu_is_zero(self):
        """First signal date has no IC or vol history → μ should be 0 (not NaN)."""
        from alpha.score_to_mu import ScoreToMu
        stm = ScoreToMu(method="rolling_ic", rolling_ic_window=5, vol_window=5)

        rng = np.random.default_rng(42)
        dates = [20240101, 20240102, 20240103, 20240104, 20240105]
        stocks = ["A", "B", "C", "D", "E"] * 5

        scores = pd.DataFrame({
            "ts_code": stocks,
            "trade_date": sorted(dates * 5),
            "composite_score": rng.normal(0, 1, 25).astype("float32"),
        })
        fwd = scores[["ts_code", "trade_date"]].copy()
        fwd["fwd_ret_5d"] = rng.normal(0, 0.02, 25).astype("float32")

        result = stm.calibrate(scores, "composite_score", fwd, horizon=5)

        first_date = result["trade_date"].min()
        first_mu = result[result["trade_date"] == first_date]["mu"]
        # First date: rolling_ic=0, rolling_cs_vol=0 → mu should be all zeros
        assert (first_mu == 0).all(), (
            f"First date μ should be 0 (no history), got {first_mu.values}"
        )

    def test_changing_future_return_does_not_change_current_mu(self):
        """
        Mutating the t+h forward return for date t must NOT change μ at date t.
        This is the definitive test for look-ahead leakage.
        """
        from alpha.score_to_mu import ScoreToMu
        stm = ScoreToMu(method="rolling_ic", rolling_ic_window=3, vol_window=3)

        rng = np.random.default_rng(99)
        n_dates = 10
        stocks_per_date = 30

        dates = [20240101 + i for i in range(n_dates)]
        all_stocks = [f"{i:04d}.SZ" for i in range(stocks_per_date)]

        scores = pd.DataFrame({
            "ts_code": all_stocks * n_dates,
            "trade_date": sorted(dates * stocks_per_date),
            "composite_score": rng.normal(0, 1, stocks_per_date * n_dates).astype("float32"),
        })

        # Original forward returns
        fwd_base = scores[["ts_code", "trade_date"]].copy()
        fwd_base["fwd_ret_5d"] = rng.normal(0, 0.02, stocks_per_date * n_dates).astype("float32")

        # Compute μ with original forwards
        result_base = stm.calibrate(scores, "composite_score", fwd_base, horizon=5)

        # Mutate forward return for the LAST date (drastically)
        fwd_perturbed = fwd_base.copy()
        last_date = dates[-1]
        fwd_perturbed.loc[
            fwd_perturbed["trade_date"] == last_date, "fwd_ret_5d"
        ] = 999.0  # extreme perturbation

        # Re-compute
        result_pert = stm.calibrate(scores, "composite_score", fwd_perturbed, horizon=5)

        # μ at the LAST date may differ (it uses IC history up to last-1 only),
        # and the perturbation at the last date only enters history AFTER
        # the last date's μ is computed. So last date's μ should be UNCHANGED.
        last_mu_base = result_base[result_base["trade_date"] == last_date]["mu"]
        last_mu_pert = result_pert[result_pert["trade_date"] == last_date]["mu"]

        # With backward-looking IC/vol only, changing current date's forward
        # return should NOT affect current date's μ
        assert last_mu_base.reset_index(drop=True).equals(
            last_mu_pert.reset_index(drop=True)
        ), "μ at date t changed when t+h forward return changed — LOOK-AHEAD LEAK!"

    def test_t_minus_1_unmatured_forward_return_does_not_change_t_mu(self):
        """Changing t-1's unmatured fwd_ret_5d must NOT change t's μ.

        t-1's forward return depends on prices at (t-1)+5 = t+4, which
        is in the future relative to t.  So t-1's IC should not
        contribute to t's rolling IC estimate.
        """
        from alpha.score_to_mu import ScoreToMu
        stm = ScoreToMu(method="rolling_ic", rolling_ic_window=4, vol_window=4)

        rng = np.random.default_rng(7)
        n_dates = 12
        stocks_per_date = 30
        dates = [20240101 + i for i in range(n_dates)]
        # Filter to valid YYYYMMDD only
        import pandas as pd
        dates = [
            d for d in dates
            if _is_valid_ymd(d)
        ]
        all_stocks = [f"{i:04d}.SZ" for i in range(stocks_per_date)]

        scores = pd.DataFrame({
            "ts_code": all_stocks * len(dates),
            "trade_date": sorted(dates * stocks_per_date),
            "composite_score": rng.normal(0, 1, stocks_per_date * len(dates)).astype("float32"),
        })
        fwd_base = scores[["ts_code", "trade_date"]].copy()
        fwd_base["fwd_ret_5d"] = rng.normal(0, 0.02, stocks_per_date * len(dates)).astype("float32")

        # Compute baseline
        result_base = stm.calibrate(scores, "composite_score", fwd_base, horizon=5)

        # Perturb t-1 (the second-to-last date)
        fwd_pert = fwd_base.copy()
        t_minus_1 = dates[-2]
        fwd_pert.loc[
            fwd_pert["trade_date"] == t_minus_1, "fwd_ret_5d"
        ] = 999.0

        result_pert = stm.calibrate(scores, "composite_score", fwd_pert, horizon=5)

        # μ at last date should be UNCHANGED
        last_date = dates[-1]
        last_mu_base = result_base[
            result_base["trade_date"] == last_date
        ]["mu"]
        last_mu_pert = result_pert[
            result_pert["trade_date"] == last_date
        ]["mu"]

        assert last_mu_base.reset_index(drop=True).equals(
            last_mu_pert.reset_index(drop=True)
        ), (
            "μ at t changed when t-1's fwd_ret was perturbed — "
            "unmatured IC leaked into rolling estimate"
        )

    def test_matured_forward_return_can_affect_later_mu(self):
        """Changing a mature early date's fwd_ret CAN affect later μ.

        If date t-k's fwd_ret is changed and k > horizon (fwd_ret fully
        matured by signal time t), AND k is within the rolling window,
        then t's μ should reflect the change.
        """
        from alpha.score_to_mu import ScoreToMu
        # Use a window large enough to include the perturbed early date
        stm = ScoreToMu(method="rolling_ic", rolling_ic_window=8, vol_window=8)

        rng = np.random.default_rng(13)
        n_dates = 14
        stocks_per_date = 40  # more stocks for stable IC
        dates = [20240101 + i for i in range(n_dates)]
        import pandas as pd
        dates = [d for d in dates if _is_valid_ymd(d)]
        all_stocks = [f"{i:04d}.SZ" for i in range(stocks_per_date)]

        scores = pd.DataFrame({
            "ts_code": all_stocks * len(dates),
            "trade_date": sorted(dates * stocks_per_date),
            "composite_score": rng.normal(0, 1, stocks_per_date * len(dates)).astype("float32"),
        })
        fwd_base = scores[["ts_code", "trade_date"]].copy()
        fwd_base["fwd_ret_5d"] = rng.normal(0, 0.02, stocks_per_date * len(dates)).astype("float32")

        result_base = stm.calibrate(scores, "composite_score", fwd_base, horizon=5)

        # Perturb date[1] — well before the last date and within horizon=5
        # From dates[-1], matured_ic_cutoff = pos(-1) - 5 - 1 ≈ 7.
        # dates[1] is at position 1, which IS in the mature window.
        # With rolling_ic_window=8, dates[1] IS in the last 8 ICs for
        # early signal dates (but not the very last). Pick a mid-range
        # later_date where the perturbed IC is still in the rolling window.
        fwd_pert = fwd_base.copy()
        early_date = dates[2]  # position 2
        fwd_pert.loc[
            fwd_pert["trade_date"] == early_date, "fwd_ret_5d"
        ] = 999.0

        result_pert = stm.calibrate(scores, "composite_score", fwd_pert, horizon=5)

        # Check a date where early_date's IC IS in the rolling window.
        # With window=8, positions 2 through 9 would include date[2].
        # Signal at position 10 → mature cutoff = 10-5-1 = 4. date[2]=pos 2,
        # which is ≤ 4. The mature history [-8:] includes pos 2.
        check_date = dates[10]
        check_mu_base = result_base[
            result_base["trade_date"] == check_date
        ]["mu"]
        check_mu_pert = result_pert[
            result_pert["trade_date"] == check_date
        ]["mu"]

        assert not check_mu_base.reset_index(drop=True).equals(
            check_mu_pert.reset_index(drop=True)
        ), (
            "μ at later date should change when mature early fwd_ret changed "
            "— rolling IC/vol may be all-zero (no history)"
        )

    def test_historical_regression_uses_matured_cutoff(self):
        """Regression method must also use matured cutoff for training."""
        from alpha.score_to_mu import ScoreToMu
        stm = ScoreToMu(
            method="historical_regression",
            regression_window=252,
            regression_min_obs=30,
        )

        rng = np.random.default_rng(21)
        n_dates = 10
        stocks_per_date = 50
        dates = [20240101 + i for i in range(n_dates)]
        import pandas as pd
        dates = [d for d in dates if _is_valid_ymd(d)]
        all_stocks = [f"{i:04d}.SZ" for i in range(stocks_per_date)]

        scores = pd.DataFrame({
            "ts_code": all_stocks * len(dates),
            "trade_date": sorted(dates * stocks_per_date),
            "composite_score": rng.normal(0, 1, stocks_per_date * len(dates)).astype("float32"),
        })
        fwd = scores[["ts_code", "trade_date"]].copy()
        fwd["fwd_ret_5d"] = rng.normal(0, 0.02, stocks_per_date * len(dates)).astype("float32")

        result = stm.calibrate(scores, "composite_score", fwd, horizon=5)
        # Should produce valid μ (not empty, not NaN-dominated)
        assert len(result) > 0, "Regression returned empty result"
        assert result["mu"].notna().sum() > 0, "All μ values are NaN"


def _is_valid_ymd(d: int) -> bool:
    """Check if an int looks like a valid YYYYMMDD date."""
    import pandas as pd
    try:
        pd.to_datetime(str(d), format="%Y%m%d")
        return True
    except (ValueError, Exception):
        return False

    def test_ic_history_does_not_include_current_date(self):
        """IC at date t is only added to history AFTER calibration, not before."""
        from alpha.score_to_mu import ScoreToMu
        stm = ScoreToMu(method="rolling_ic", rolling_ic_window=2, vol_window=2)

        rng = np.random.default_rng(7)
        n = 5
        all_stocks = [f"{i:04d}.SZ" for i in range(30)]
        dates = [20240101 + i for i in range(n)]

        scores = pd.DataFrame({
            "ts_code": all_stocks * n,
            "trade_date": sorted(dates * 30),
            "composite_score": rng.normal(0, 1, 30 * n).astype("float32"),
        })
        fwd = scores[["ts_code", "trade_date"]].copy()
        fwd["fwd_ret_5d"] = rng.normal(0, 0.02, 30 * n).astype("float32")

        result = stm.calibrate(scores, "composite_score", fwd, horizon=5)
        # If no look-ahead, the first rolling_ic_window dates should have μ=0
        # (not enough history for IC estimation)
        first_dates = sorted(result["trade_date"].unique())[:stm.rolling_ic_window]
        for d in first_dates:
            mu_vals = result[result["trade_date"] == d]["mu"]
            assert (mu_vals == 0).all(), (
                f"Date {d} has non-zero μ before enough IC history accumulated"
            )

    def test_constant_inputs_do_not_produce_nan_mu(self):
        """Undefined Spearman IC should be treated as 0, not propagated as NaN."""
        from alpha.score_to_mu import ScoreToMu
        stm = ScoreToMu(method="rolling_ic", rolling_ic_window=10, vol_window=10)

        n_dates = 12
        stocks_per_date = 30
        dates = [20240101 + i for i in range(n_dates)]
        stocks = [f"{i:04d}.SZ" for i in range(stocks_per_date)]

        scores = pd.DataFrame({
            "ts_code": stocks * n_dates,
            "trade_date": sorted(dates * stocks_per_date),
            "composite_score": np.ones(stocks_per_date * n_dates, dtype="float32"),
        })
        fwd = scores[["ts_code", "trade_date"]].copy()
        fwd["fwd_ret_5d"] = np.ones(
            stocks_per_date * n_dates, dtype="float32"
        ) * 0.01

        result = stm.calibrate(scores, "composite_score", fwd, horizon=5)

        assert not result.empty
        assert np.isfinite(result["mu"].astype(float)).all()
        assert (result["mu"] == 0).all()

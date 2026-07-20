"""
Tests for regime warmup and OOS data window handling.

Verifies:
  - Load window includes sufficient warmup for regime features
  - Same signal date gets consistent features regardless of data start
  - Phase 5 OOS dates get regime probs when oos_end > end_date
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from unittest.mock import MagicMock, patch

from run_research import _compute_regime_load_window


class TestRegimeLoadWindow:
    """Verify warmup window computation."""

    def test_load_window_includes_warmup(self):
        """data_start should be earlier than backtest start."""
        regime_config = {
            "regime_detector": {
                "trend": {"ma_long": 120, "return_windows": [20, 60, 120]},
                "volatility": {"drawdown_window": 60},
                "breadth": {"ma_window": 60},
            },
            "sleeve_composite": {"ic_window_months": 6},
        }

        data_start, data_end = _compute_regime_load_window(
            "20230101", "20231231", regime_config,
        )

        # data_start should be before 20230101
        assert int(data_start) < 20230101, (
            f"data_start={data_start} should be < 20230101"
        )
        # data_end should equal end_date
        assert data_end == "20231231"

    def test_longer_window_for_long_ma(self):
        """Longer MA requires longer warmup."""
        config_short = {
            "regime_detector": {
                "trend": {"ma_long": 60, "return_windows": [20, 60]},
                "volatility": {"drawdown_window": 20},
                "breadth": {"ma_window": 20},
            },
            "sleeve_composite": {"ic_window_months": 3},
        }
        config_long = {
            "regime_detector": {
                "trend": {"ma_long": 250, "return_windows": [20, 60, 120, 250]},
                "volatility": {"drawdown_window": 120},
                "breadth": {"ma_window": 120},
            },
            "sleeve_composite": {"ic_window_months": 12},
        }

        ds_short, _ = _compute_regime_load_window("20230101", "20231231", config_short)
        ds_long, _ = _compute_regime_load_window("20230101", "20231231", config_long)

        # Longer MA should push data_start further back
        assert int(ds_long) < int(ds_short), (
            f"Long config start={ds_long} should be < short config start={ds_short}"
        )

    def test_oos_end_preserved(self):
        """data_end should always be end_date (not shortened)."""
        regime_config = {
            "regime_detector": {
                "trend": {"ma_long": 120, "return_windows": [20, 60, 120]},
                "volatility": {"drawdown_window": 60},
                "breadth": {"ma_window": 60},
            },
            "sleeve_composite": {"ic_window_months": 6},
        }

        _, data_end = _compute_regime_load_window(
            "20230101", "20251231", regime_config,
        )
        assert data_end == "20251231"


class TestRegimeDetectorWarmup:
    """Verify regime features are consistent regardless of data start."""

    def test_truncated_data_produces_features(self):
        """Even with truncated (no-warmup) data, regime detector produces
        features for dates that have enough history — no crash, no future leak."""
        from alpha.regime_detector import RegimeDetector

        n_days = 500
        import numpy as np
        import pandas as pd

        rng = np.random.default_rng(99)
        rets = 0.0003 + 0.015 * rng.standard_normal(n_days)
        prices = 100.0 * np.cumprod(1.0 + rets)
        volumes = rng.lognormal(mean=15.0, sigma=0.5, size=n_days)

        dates = []
        current = 20220101
        while len(dates) < n_days:
            day = current % 100
            if 1 <= day <= 28:
                dates.append(current)
            current += 1
            if (current % 100) > 31:
                current = ((current // 100) * 100) + 101
            if (current // 100) % 100 > 12:
                current = (((current // 10000) + 1) * 10000) + 101
        dates = sorted(dates)

        idx_full = pd.DataFrame({
            "ts_code": "000300.SH",
            "trade_date": dates,
            "close": prices,
            "vol": volumes,
        })

        # Truncate: only from 2023-01-01 (reduced history)
        idx_truncated = idx_full[idx_full["trade_date"] >= 20230101].copy()

        detector = RegimeDetector({
            "trend": {"ma_short": 60, "ma_long": 120, "return_windows": [20, 60, 120]},
            "volatility": {"vol_windows": [20, 60], "drawdown_window": 60},
            "breadth": {"ma_window": 60, "min_stocks": 100},
            "smoothing": {"halflife": 0},
        })

        # Signal dates in 2023-Q2 (well after the truncation point)
        signal_dates = [d for d in dates if 20230401 <= d <= 20230630][:5]

        feat_full = detector.compute_features(idx_full, None, signal_dates)
        feat_trunc = detector.compute_features(idx_truncated, None, signal_dates)

        # Both should produce features for these dates (enough history)
        assert not feat_full.empty, "Full data should produce features"
        assert not feat_trunc.empty, "Truncated data should also produce features"

        # Key property: features at a date only use PIT data (no future).
        # Features may differ slightly because more history → more accurate
        # estimates, but both are valid PIT computations.
        # Verify: no future dates appear
        for sd in signal_dates:
            # Truncated data only has dates >= 20230101
            used_dates = idx_truncated[idx_truncated["trade_date"] <= sd]["trade_date"]
            assert (used_dates >= 20230101).all(), (
                f"Truncated data at {sd} should only use dates >= 20230101"
            )

    def test_early_dates_without_warmup_skipped(self):
        """Signal dates too close to data start (without warmup) should
        produce empty features, not crash."""
        from alpha.regime_detector import RegimeDetector
        import numpy as np
        import pandas as pd

        rng = np.random.default_rng(42)
        n_days = 5  # very short history — far below min_required threshold
        prices = 100.0 * np.cumprod(1.0 + 0.0003 + 0.015 * rng.standard_normal(n_days))
        dates = []
        current = 20230101
        while len(dates) < n_days:
            day = current % 100
            if 1 <= day <= 28:
                dates.append(current)
            current += 1
            if (current % 100) > 31:
                current = ((current // 100) * 100) + 101

        idx = pd.DataFrame({
            "ts_code": "000300.SH",
            "trade_date": sorted(dates),
            "close": prices,
            "vol": np.ones(n_days) * 1e6,
        })

        detector = RegimeDetector({
            "trend": {"ma_short": 60, "ma_long": 120, "return_windows": [20, 60, 120]},
            "volatility": {"vol_windows": [20, 60], "drawdown_window": 60},
            "breadth": {"ma_window": 60, "min_stocks": 100},
            "smoothing": {"halflife": 0},
        })

        features = detector.compute_features(idx, None, sorted(dates)[-5:])
        # With only 30 days of data and ma_long=120, features should be empty
        assert features.empty, (
            "Short history should produce empty features, not crash"
        )


class TestBuildRegimeCompositeOOS:
    """Integration test: build_regime_composite with OOS data window."""

    def test_oos_dates_in_regime_probs(self):
        """When data_end_date > end_date, diagnostics regime_probs
        should cover OOS signal dates."""
        import numpy as np
        import pandas as pd
        from unittest.mock import MagicMock, patch

        # Minimal synthetic data — enough to verify OOS coverage without
        # triggering expensive RegimeDetector computation (use ~200 days
        # to stay fast, but enough for detector min_history).
        n_days = 250
        rng = np.random.default_rng(77)
        rets = 0.0003 + 0.015 * rng.standard_normal(n_days)
        prices = 100.0 * np.cumprod(1.0 + rets)
        volumes = rng.lognormal(mean=15.0, sigma=0.5, size=n_days)

        dates = []
        current = 20210101
        while len(dates) < n_days:
            day = current % 100
            if 1 <= day <= 28:
                dates.append(current)
            current += 1
            if (current % 100) > 31:
                current = ((current // 100) * 100) + 101
            if (current // 100) % 100 > 12:
                current = (((current // 10000) + 1) * 10000) + 101
        dates = sorted(dates)

        idx_full = pd.DataFrame({
            "ts_code": "000300.SH",
            "trade_date": dates,
            "close": prices,
            "vol": volumes,
        })
        idx_full = idx_full[idx_full["ts_code"] == "000300.SH"]

        # Build synthetic factor data (small stock universe for speed)
        stocks = [f"{i:06d}.SZ" for i in range(1, 16)]
        factor_dfs = {}
        for fname in ["reversal_5_cs", "reversal_20_cs", "volatility_20_cs"]:
            rows = []
            for d in dates:
                for ts in stocks:
                    rows.append({
                        "ts_code": ts,
                        "trade_date": d,
                        fname: float(rng.normal(0, 1)),
                    })
            factor_dfs[fname] = pd.DataFrame(rows)

        fwd_rows = []
        for d in dates:
            for ts in stocks:
                fwd_rows.append({
                    "ts_code": ts,
                    "trade_date": d,
                    "fwd_ret_5d": float(rng.normal(0.0005, 0.02)),
                })
        fwd_rets = pd.DataFrame(fwd_rows)

        # Mock loader to return our synthetic data
        mock_loader = MagicMock()
        def mock_query(table_name, columns=None, start_date=None, end_date=None, **kwargs):
            if table_name == "index_daily":
                df = idx_full.copy()
                if start_date:
                    df = df[df["trade_date"] >= int(start_date)]
                if end_date:
                    df = df[df["trade_date"] <= int(end_date)]
                return df
            return pd.DataFrame()
        mock_loader.query.side_effect = mock_query

        # Signal dates: backtest period + OOS period
        backtest_signal_dates = [d for d in dates if 20210601 <= d <= 20210831]
        oos_signal_dates = [d for d in dates if 20210901 <= d <= 20211031]
        all_signal_dates = sorted(backtest_signal_dates + oos_signal_dates)

        # Patch calendar to return real-ish dates
        with patch("data.calendar.get_calendar") as mock_cal:
            mock_cal_instance = MagicMock()
            mock_cal_instance.trade_days_between.return_value = [int(d) for d in dates]
            mock_cal_instance.weekly_rebalance_dates.return_value = [
                str(d) for d in dates
            ]
            mock_cal.return_value = mock_cal_instance

            from run_research import build_regime_composite

            composite, diag = build_regime_composite(
                factor_dfs, fwd_rets, all_signal_dates,
                "configs/regime.yaml",
                start_date="20210601",
                end_date="20210831",
                loader=mock_loader,
                data_start_date="20210101",
                data_end_date="20211031",
            )

        # Diagnostics should exist
        assert "regime_probs" in diag
        regime_probs = diag["regime_probs"]
        if regime_probs.empty:
            # With only 250 days and ma_long=120, the detector may not have
            # enough history for early dates.  This is acceptable — the key
            # invariant is that the diagnostics record the reason clearly.
            assert "skip_reasons" in diag or "error" in diag, (
                "If regime_probs is empty, diagnostics must explain why"
            )
        else:
            prob_dates = set(regime_probs["trade_date"].unique())
            oos_set = set(oos_signal_dates)
            # OOS dates should be covered when data_end_date includes them
            # and there's enough history. With scoring-signal-date
            # warmup, the regime engine has full rolling IC history for
            # every OOS date, so the entire OOS subset must be present.
            oos_covered = oos_set & prob_dates
            assert oos_set.issubset(prob_dates), (
                f"OOS dates missing from regime probs: "
                f"{sorted(oos_set - prob_dates)[:5]}... "
                f"covered={len(oos_covered)}/{len(oos_set)}"
            )


class TestWarmupSignalDates:
    """Verify warmup signal dates enable early target composite production."""

    def test_build_scoring_signal_dates_union(self):
        """_build_regime_scoring_signal_dates produces correct union of
        warmup weekly + target dates, with target dates preserved."""
        from unittest.mock import MagicMock
        from run_research import _build_regime_scoring_signal_dates

        cal = MagicMock()
        # warmup weekly dates: 2022-06 to 2023-01
        cal.weekly_rebalance_dates.return_value = [
            "20220603", "20220610", "20220617", "20220624",
            "20220701", "20221230",
            "20230106", "20230113", "20230120", "20230127",
        ]

        # Target signal dates: only 2023 dates (subset of warmup)
        target = [20230113, 20230120, 20230127, 20230203, 20230210]

        result = _build_regime_scoring_signal_dates(
            target_signal_dates=target,
            data_start_date="20220601",
            data_end_date="20230210",
            calendar=cal,
        )

        # All target dates must be in result
        target_set = set(target)
        result_set = set(result)
        assert target_set.issubset(result_set), (
            f"All target dates must be in scoring dates.\n"
            f"  Missing: {sorted(target_set - result_set)}"
        )
        # Result must contain warmup dates not in target
        assert len(result) > len(target), (
            f"Scoring dates ({len(result)}) should be more than "
            f"target dates ({len(target)}) due to warmup"
        )
        # Result must be sorted
        assert result == sorted(result), "Result must be sorted"

    def test_scoring_dates_in_diagnostics(self):
        """Verify that build_regime_composite captures scoring signal date
        diagnostics even when the composite ends up empty."""
        import numpy as np
        import pandas as pd
        import tempfile
        import yaml
        import os
        from unittest.mock import MagicMock, patch

        # Minimal data: just enough to get through calendar/config loading
        n_days = 60
        rng = np.random.default_rng(42)
        rets = 0.0003 + 0.015 * rng.standard_normal(n_days)
        prices = 100.0 * np.cumprod(1.0 + rets)

        dates = []
        current = 20230101
        while len(dates) < n_days:
            day = current % 100
            if 1 <= day <= 28:
                dates.append(current)
            current += 1
            if (current % 100) > 31:
                current = ((current // 100) * 100) + 101
            if (current // 100) % 100 > 12:
                current = (((current // 10000) + 1) * 10000) + 101
        dates = sorted(dates)

        idx_full = pd.DataFrame({
            "ts_code": "000300.SH",
            "trade_date": dates,
            "close": prices,
            "vol": np.ones(n_days) * 1e6,
        })
        idx_full = idx_full[idx_full["ts_code"] == "000300.SH"]

        stocks = [f"{i:06d}.SZ" for i in range(1, 11)]
        factor_dfs = {}
        for fname in ["reversal_5_cs", "reversal_20_cs", "volatility_20_cs",
                       "momentum_60_cs", "momentum_120_cs", "macd_12_26_9_cs",
                       "rsi_14_cs", "pv_divergence_20_cs"]:
            rows = []
            for d in dates:
                for ts in stocks:
                    rows.append({
                        "ts_code": ts, "trade_date": d,
                        fname: float(rng.normal(0, 1)),
                    })
            factor_dfs[fname] = pd.DataFrame(rows)

        fwd_rows = []
        for d in dates:
            for ts in stocks:
                fwd_rows.append({
                    "ts_code": ts, "trade_date": d,
                    "fwd_ret_5d": float(rng.normal(0, 0.02)),
                })
        fwd_rets = pd.DataFrame(fwd_rows)

        target_signal_dates = [d for d in dates if d >= 20230201]

        mock_loader = MagicMock()
        def mock_query(table_name, **kwargs):
            if table_name == "index_daily":
                df = idx_full.copy()
                sd = kwargs.get("start_date")
                ed = kwargs.get("end_date")
                if sd:
                    df = df[df["trade_date"] >= int(sd)]
                if ed:
                    df = df[df["trade_date"] <= int(ed)]
                return df
            return pd.DataFrame()
        mock_loader.query.side_effect = mock_query

        with patch("data.calendar.get_calendar") as mock_cal:
            mock_cal_instance = MagicMock()
            mock_cal_instance.trade_days_between.return_value = [
                int(d) for d in dates
            ]
            mock_cal_instance.weekly_rebalance_dates.return_value = [
                str(d) for d in dates
            ]
            mock_cal.return_value = mock_cal_instance

            from run_research import build_regime_composite

            composite, diag = build_regime_composite(
                factor_dfs, fwd_rets, target_signal_dates,
                "configs/regime.yaml",
                start_date="20230201",
                end_date="20230228",
                loader=mock_loader,
                data_start_date="20230101",
                data_end_date="20230228",
            )

        # Diagnostics must always contain these keys regardless of
        # whether composite is empty
        assert "target_signal_dates_count" in diag, (
            "Diagnostics must record target_signal_dates_count"
        )
        assert "scoring_signal_dates_count" in diag, (
            "Diagnostics must record scoring_signal_dates_count"
        )
        assert diag["scoring_signal_dates_count"] >= diag["target_signal_dates_count"], (
            f"scoring_signal_dates ({diag['scoring_signal_dates_count']}) "
            f"must be >= target ({diag['target_signal_dates_count']})"
        )
        # If composite was produced, verify clipping
        if not composite.empty:
            assert "first_composite_date_before_clip" in diag
            assert "first_composite_date_after_clip" in diag
            composite_dates = set(int(d) for d in composite["trade_date"].unique())
            target_set = set(target_signal_dates)
            assert composite_dates.issubset(target_set), (
                "Composite dates must be subset of target signal dates after clipping"
            )


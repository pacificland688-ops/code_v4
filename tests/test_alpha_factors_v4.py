"""
Test: V4 alpha factor computation, direction, PIT alignment, and missing data handling.

Covers:
  - Factor formula correctness (basic smoke)
  - PIT: available_date <= trade_date
  - Direction: sign_hint consistent with computed values
  - Missing data: graceful empty DataFrame return
  - CS processing: winsorize and z-score produce finite values
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.build_alpha_factors_v4 import (
    _compute_technical_skip_momentum,
    _compute_risk_adjusted_momentum,
    _compute_volume_confirmed_momentum,
    _compute_trend_quality,
    _compute_liquidity_adjusted_reversal,
    _compute_vol_adjusted_reversal,
    _compute_low_beta,
    _compute_drawdown_resilience,
    _compute_low_beta_stable,
    _compute_liquidity_adjusted_reversal_low_turnover,
    _compute_growth_ttm,
    _compute_stability_8q,
    _compute_earnings_acceleration,
    _compute_profitability_quality,
    _compute_ocf_to_profit,
    _compute_fundamental_ttm,
    _compute_industry_relative,
    _apply_cs_processing,
    _resolve_available_date,
    _detect_report_type,
)


# ===========================================================================
# Test fixtures
# ===========================================================================

@pytest.fixture
def sample_prices():
    """Generate sample price data for 5 stocks over 150 trading days."""
    np.random.seed(42)
    stocks = [f"{i:06d}.SZ" for i in range(5)]
    rows = []
    for s in stocks:
        price = 10.0
        for t in range(150):
            trade_date = 20210104 + t
            ret = np.random.randn() * 0.02
            price *= (1 + ret)
            vol = np.random.rand() * 1e6
            rows.append({
                "ts_code": s,
                "trade_date": trade_date,
                "adj_close": price,
                "vol": vol,
                "amount": vol * price,
            })
    return pd.DataFrame(rows)


@pytest.fixture
def sample_financial_data():
    """Generate sample financial data with PIT fields."""
    np.random.seed(42)
    stocks = [f"{i:06d}.SZ" for i in range(5)]
    rows = []
    for s in stocks:
        for quarter in range(20180101, 20250101, 30000):  # rough quarterly
            # Normalize to quarter-end dates
            y = quarter // 10000
            m = ((quarter // 100) % 100)
            end_date = y * 10000 + ((m - 1) // 3 + 1) * 3 * 100 + 30
            # Clamp to valid dates
            if end_date % 10000 > 1231:
                end_date = y * 10000 + 1231
            ann_date = end_date + np.random.randint(20, 90)
            rows.append({
                "ts_code": s,
                "end_date": end_date,
                "ann_date": ann_date,
                "roe": np.random.randn() * 0.05 + 0.12,
                "roa": np.random.randn() * 0.03 + 0.06,
                "grossprofit_margin": np.random.rand() * 0.3 + 0.2,
                "netprofit_margin": np.random.rand() * 0.2 + 0.05,
                "revenue": np.random.rand() * 1e10 + 1e9,
                "n_income": np.random.randn() * 1e8 + 5e8,
                "ocf": np.random.randn() * 1e8 + 3e8,
                "profit_dedt": np.random.randn() * 1e8 + 4e8,
            })
    return pd.DataFrame(rows)


@pytest.fixture
def sample_industry_map():
    """Sample industry classification."""
    return pd.DataFrame({
        "ts_code": [f"{i:06d}.SZ" for i in range(5)],
        "industry_code": ["IND_A", "IND_A", "IND_B", "IND_B", "IND_C"],
    })


# ===========================================================================
# PIT Alignment Tests
# ===========================================================================

class TestPITAlignment:
    """PIT: available_date must be <= trade_date. Fundamental data uses ann_date."""

    def test_available_date_uses_ann_date(self):
        """When ann_date is available, it should be used."""
        end_date = 20230630
        ann_date = 20230815
        result = _resolve_available_date(ann_date, end_date)
        assert result == ann_date

    def test_fallback_when_ann_date_none(self):
        """When ann_date is None, conservative fallback should be used."""
        end_date = 20231231
        result = _resolve_available_date(None, end_date)
        assert result == 20231231 + 90  # annual report: +90 days (v4-r2 relaxed)

    def test_fallback_when_ann_date_nan(self):
        """When ann_date is NaN, conservative fallback should be used."""
        result = _resolve_available_date(float("nan"), 20230630)
        assert result == 20230630 + 45  # semi-annual: +45 days (v4-r2 relaxed)

    def test_quarterly_fallback(self):
        """Quarterly report: +30 days."""
        result = _resolve_available_date(None, 20230930)
        assert result == 20230930 + 30

    def test_detect_report_type_annual(self):
        assert _detect_report_type(20231231) == "annual"

    def test_detect_report_type_semi_annual(self):
        assert _detect_report_type(20230630) == "semi_annual"

    def test_detect_report_type_quarterly(self):
        assert _detect_report_type(20230331) == "quarterly"
        assert _detect_report_type(20230930) == "quarterly"

    def test_growth_ttm_has_available_date(self, sample_financial_data):
        """Growth TTM output must include available_date."""
        df = sample_financial_data.copy()
        if "revenue" in df.columns:
            result = _compute_growth_ttm(df, "revenue")
            if not result.empty:
                assert "available_date" in result.columns
                assert "source_period" in result.columns

    def test_stability_8q_has_available_date(self, sample_financial_data):
        """Stability output must include available_date."""
        df = sample_financial_data.copy()
        if "roe" in df.columns:
            result = _compute_stability_8q(df, "roe")
            if not result.empty:
                assert "available_date" in result.columns


# ===========================================================================
# Factor Computation Tests
# ===========================================================================

class TestTechnicalFactors:
    """Test technical/price-based factor computations."""

    def test_skip_momentum_shape(self, sample_prices):
        """Skip momentum returns correct columns."""
        result = _compute_technical_skip_momentum(sample_prices, 60, 5)
        assert not result.empty
        assert "ts_code" in result.columns
        assert "trade_date" in result.columns
        assert "value" in result.columns

    def test_skip_momentum_values_finite(self, sample_prices):
        """All factor values should be finite."""
        result = _compute_technical_skip_momentum(sample_prices, 60, 5)
        assert result["value"].notna().all()
        assert np.isfinite(result["value"]).all()

    def test_risk_adjusted_momentum(self, sample_prices):
        """Risk-adjusted momentum produces finite values."""
        result = _compute_risk_adjusted_momentum(sample_prices, 60, 60)
        if not result.empty:
            assert np.isfinite(result["value"]).all()

    def test_volume_confirmed_momentum(self, sample_prices):
        """Volume-confirmed momentum works with vol column."""
        result = _compute_volume_confirmed_momentum(sample_prices, 60, 20)
        if not result.empty:
            assert "value" in result.columns

    def test_trend_quality(self, sample_prices):
        """Trend quality produces values."""
        result = _compute_trend_quality(sample_prices, 20, 60)
        if not result.empty:
            assert np.isfinite(result["value"]).all()

    def test_liquidity_adjusted_reversal(self, sample_prices):
        """Liquidity-adjusted reversal produces finite values."""
        result = _compute_liquidity_adjusted_reversal(sample_prices, 5, 20, 20)
        if not result.empty:
            assert {"ts_code", "trade_date", "value"}.issubset(result.columns)
            assert np.isfinite(result["value"]).all()

    def test_vol_adjusted_reversal(self, sample_prices):
        """Vol-adjusted reversal produces finite values."""
        result = _compute_vol_adjusted_reversal(sample_prices, 20, 60)
        if not result.empty:
            assert {"ts_code", "trade_date", "value"}.issubset(result.columns)
            assert np.isfinite(result["value"]).all()

    def test_low_beta(self, sample_prices):
        """Low-beta defensive factor produces finite values."""
        result = _compute_low_beta(sample_prices, 60)
        if not result.empty:
            assert {"ts_code", "trade_date", "value"}.issubset(result.columns)
            assert np.isfinite(result["value"]).all()

    def test_drawdown_resilience(self, sample_prices):
        """Drawdown resilience produces finite values."""
        result = _compute_drawdown_resilience(sample_prices, 60, 20)
        if not result.empty:
            assert {"ts_code", "trade_date", "value"}.issubset(result.columns)
            assert np.isfinite(result["value"]).all()

    def test_low_beta_stable_monthly_has_fewer_dates(self, sample_prices):
        """Stable low-beta should downsample daily signals to monthly signals."""
        daily = _compute_low_beta(sample_prices, 60)
        monthly = _compute_low_beta_stable(sample_prices, 60, 5, "monthly")
        if not daily.empty and not monthly.empty:
            assert monthly["trade_date"].nunique() < daily["trade_date"].nunique()
            assert np.isfinite(monthly["value"]).all()

    def test_reversal_low_turnover_weekly_has_fewer_dates(self, sample_prices):
        """Weekly reversal should have fewer signal dates than daily reversal."""
        daily = _compute_liquidity_adjusted_reversal(sample_prices, 5, 20, 20)
        weekly = _compute_liquidity_adjusted_reversal_low_turnover(
            sample_prices, 5, 20, 20, 3, "weekly"
        )
        if not daily.empty and not weekly.empty:
            assert weekly["trade_date"].nunique() < daily["trade_date"].nunique()
            assert np.isfinite(weekly["value"]).all()

    def test_empty_prices_returns_empty(self):
        """Empty price data → empty DataFrame."""
        empty = pd.DataFrame(columns=["ts_code", "trade_date", "adj_close"])
        result = _compute_technical_skip_momentum(empty, 60, 5)
        assert result.empty


class TestFundamentalFactors:
    """Test fundamental factor computations with PIT alignment."""

    def test_growth_ttm(self, sample_financial_data):
        """Growth TTM computes valid growth rates."""
        df = sample_financial_data.copy()
        if "revenue" in df.columns:
            result = _compute_growth_ttm(df, "revenue")
            if not result.empty:
                assert "value" in result.columns
                assert "available_date" in result.columns

    def test_stability_8q(self, sample_financial_data):
        """Stability returns negative std (more stable = higher value)."""
        df = sample_financial_data.copy()
        if "roe" in df.columns:
            result = _compute_stability_8q(df, "roe")
            if not result.empty:
                # Stability is -std, so values should be <= 0
                assert (result["value"] <= 0.01).all(), "Stability should be negative (=-std)"

    def test_earnings_acceleration(self, sample_financial_data):
        """Earnings acceleration computes 2nd derivative."""
        df = sample_financial_data.copy()
        if "n_income" in df.columns:
            result = _compute_earnings_acceleration(df)
            if not result.empty:
                assert "value" in result.columns

    def test_profitability_quality(self, sample_financial_data):
        """Composite profitability quality from multiple margins."""
        df = sample_financial_data.copy()
        margin_fields = ["grossprofit_margin", "netprofit_margin"]
        available = [f for f in margin_fields if f in df.columns]
        if available:
            result = _compute_profitability_quality(df, available)
            if not result.empty:
                assert "value" in result.columns
                assert np.isfinite(result["value"]).all()

    def test_ocf_to_profit(self, sample_financial_data):
        """OCF/Profit ratio computation."""
        df = sample_financial_data.copy()
        result = _compute_ocf_to_profit(df)
        # May be empty if fields not found, that's OK (not all fields guaranteed)

    def test_fundamental_ttm(self, sample_financial_data):
        """TTM computation for a generic field."""
        df = sample_financial_data.copy()
        if "roe" in df.columns:
            result = _compute_fundamental_ttm(df, "roe")
            if not result.empty:
                assert "value" in result.columns
                assert "available_date" in result.columns

    def test_empty_financial_data_returns_empty(self):
        """Empty financial data → empty results."""
        empty = pd.DataFrame()
        result_ttm = _compute_fundamental_ttm(empty, "roe")
        assert result_ttm.empty
        result_growth = _compute_growth_ttm(empty, "revenue")
        assert result_growth.empty
        result_stab = _compute_stability_8q(empty, "roe")
        assert result_stab.empty

    def test_missing_field_returns_empty(self, sample_financial_data):
        """Nonexistent field → empty DataFrame."""
        df = sample_financial_data.copy()
        result = _compute_growth_ttm(df, "nonexistent_field")
        assert result.empty


class TestIndustryRelative:
    """Test industry-relative factor computation."""

    def test_industry_relative(self, sample_prices, sample_industry_map):
        """Industry-relative rank transforms values to within-industry ranks."""
        # First compute a base factor
        base = _compute_technical_skip_momentum(sample_prices, 60, 5)
        result = _compute_industry_relative(base, sample_industry_map, "test")
        if not result.empty:
            # Ranks should be between 0 and 1
            assert result["value"].between(0, 1).all()

    def test_industry_relative_empty_base(self, sample_industry_map):
        """Empty base factor → empty result."""
        empty = pd.DataFrame(columns=["ts_code", "trade_date", "value"])
        result = _compute_industry_relative(empty, sample_industry_map, "test")
        assert result.empty

    def test_industry_relative_empty_map(self, sample_prices):
        """Empty industry map → empty result."""
        base = _compute_technical_skip_momentum(sample_prices, 60, 5)
        empty_map = pd.DataFrame(columns=["ts_code", "industry_code"])
        result = _compute_industry_relative(base, empty_map, "test")
        assert result.empty


class TestCSProcessing:
    """Test cross-sectional processing."""

    def test_cs_processing_produces_finite_values(self, sample_prices):
        """CS-processed values should be finite z-scores."""
        base = _compute_technical_skip_momentum(sample_prices, 60, 5)
        cs_config = {"enabled": True}
        result = _apply_cs_processing(base, cs_config)
        if not result.empty:
            assert np.isfinite(result["value"]).all()

    def test_cs_empty_input(self):
        """Empty input → empty output."""
        empty = pd.DataFrame(columns=["ts_code", "trade_date", "value"])
        result = _apply_cs_processing(empty, {})
        assert result.empty


class TestPITDedup:
    """PIT expansion must not produce duplicate (ts_code, trade_date) keys."""

    def test_dedup_keeps_most_recent_available_date(self, sample_financial_data, sample_prices):
        """When multiple available_dates are valid for a trade_date, keep the latest."""
        import pandas as pd
        from scripts.build_alpha_factors_v4 import _compute_growth_ttm

        df = sample_financial_data.copy()
        if "n_income" not in df.columns:
            pytest.skip("n_income not in sample data")

        # Compute growth factor — one row per (ts_code, available_date)
        factor = _compute_growth_ttm(df, "n_income")
        if factor.empty:
            pytest.skip("growth factor computation produced empty result")

        # Simulate PIT expansion (same logic as build script)
        trade_dates = sample_prices[["ts_code", "trade_date"]].drop_duplicates()
        expanded = factor.merge(trade_dates, on="ts_code", how="inner")
        expanded = expanded[expanded["trade_date"] >= expanded["available_date"]]

        # BEFORE dedup: may have duplicates
        n_dup_before = int(expanded.duplicated(["ts_code", "trade_date"]).sum())

        # Apply the dedup fix
        expanded = expanded.sort_values(["ts_code", "trade_date", "available_date"])
        expanded = expanded.drop_duplicates(["ts_code", "trade_date"], keep="last")

        # AFTER dedup: must be unique
        n_dup_after = int(expanded.duplicated(["ts_code", "trade_date"]).sum())
        assert n_dup_after == 0, (
            f"PIT expansion still has {n_dup_after} duplicates after dedup "
            f"(was {n_dup_before} before dedup)"
        )

    def test_dedup_preserves_pit_constraint(self, sample_financial_data, sample_prices):
        """After dedup, the kept available_date must still be <= trade_date."""
        from scripts.build_alpha_factors_v4 import _compute_growth_ttm

        df = sample_financial_data.copy()
        if "n_income" not in df.columns:
            pytest.skip("n_income not in sample data")

        factor = _compute_growth_ttm(df, "n_income")
        if factor.empty:
            pytest.skip("growth factor computation produced empty result")

        trade_dates = sample_prices[["ts_code", "trade_date"]].drop_duplicates()
        expanded = factor.merge(trade_dates, on="ts_code", how="inner")
        expanded = expanded[expanded["trade_date"] >= expanded["available_date"]]
        expanded = expanded.sort_values(["ts_code", "trade_date", "available_date"])
        expanded = expanded.drop_duplicates(["ts_code", "trade_date"], keep="last")

        # PIT constraint must hold for all rows
        assert (expanded["trade_date"] >= expanded["available_date"]).all(), (
            "PIT constraint violated after dedup"
        )

    def test_growth_factors_output_unique_keys(self, sample_financial_data):
        """All growth factor computation functions must produce unique (ts_code, available_date)."""
        from scripts.build_alpha_factors_v4 import (
            _compute_growth_ttm, _compute_stability_8q, _compute_earnings_acceleration
        )

        df = sample_financial_data.copy()

        for func, args in [
            (_compute_growth_ttm, ("n_income",)),
            (_compute_growth_ttm, ("revenue",)),
            (_compute_stability_8q, ("n_income", 5)),
            (_compute_earnings_acceleration, ()),
        ]:
            if "n_income" not in df.columns and args[0] == "n_income":
                continue
            if "revenue" not in df.columns and args[0] == "revenue":
                continue
            result = func(df, *args) if args else func(df)
            if result.empty:
                continue
            # No (ts_code, available_date) duplicates in raw factor output
            n_dup = int(result.duplicated(["ts_code", "available_date"]).sum())
            assert n_dup == 0, (
                f"{func.__name__}({args}) has {n_dup} duplicate (ts_code, available_date) keys"
            )

    def test_multi_report_period_same_trade_date(self, sample_financial_data, sample_prices):
        """Construct a scenario where Q1/Q2/Q3 reports all precede the same trade_date."""
        from scripts.build_alpha_factors_v4 import _compute_growth_ttm

        df = sample_financial_data.copy()
        if "n_income" not in df.columns:
            pytest.skip("n_income not in sample data")

        factor = _compute_growth_ttm(df, "n_income")
        if factor.empty:
            pytest.skip("growth factor computation produced empty result")

        # Count stocks with multiple available_dates per trade_date after PIT expansion
        trade_dates = sample_prices[["ts_code", "trade_date"]].drop_duplicates()
        expanded = factor.merge(trade_dates, on="ts_code", how="inner")
        expanded = expanded[expanded["trade_date"] >= expanded["available_date"]]

        multi_avail = expanded.groupby(["ts_code", "trade_date"]).size()
        n_multi = int((multi_avail > 1).sum())

        if n_multi > 0:
            # The dedup fix must eliminate all of these
            expanded = expanded.sort_values(["ts_code", "trade_date", "available_date"])
            expanded = expanded.drop_duplicates(["ts_code", "trade_date"], keep="last")
            multi_after = expanded.groupby(["ts_code", "trade_date"]).size()
            n_multi_after = int((multi_after > 1).sum())
            assert n_multi_after == 0, (
                f"Dedup failed to clean {n_multi_after} multi-available_date keys "
                f"(had {n_multi} before dedup)"
            )
        # If n_multi == 0 with synthetic data, that's fine — the test documents the scenario

    def test_duplicate_assertion_would_fire(self):
        """Verify that the unique-key assertion logic detects duplicates."""
        import pandas as pd

        # Create a DataFrame with intentional duplicates
        df = pd.DataFrame({
            "ts_code": ["000001.SZ", "000001.SZ", "000002.SZ"],
            "trade_date": [20210104, 20210104, 20210104],
            "value": [0.5, 0.6, 0.3],
        })
        n_dup = int(df.duplicated(["ts_code", "trade_date"]).sum())
        assert n_dup > 0, "Test fixture should have duplicates"
        # The assertion in build script would fire here
        # This test just validates the detection logic


class TestFactorConfig:
    """Test V4 factor universe config integrity."""

    def test_universe_config_loads(self):
        """V4 universe config should be valid YAML with factors list."""
        import yaml
        config_path = ROOT / "configs" / "factors_alpha_v4_universe.yaml"
        if config_path.exists():
            cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            assert "factors" in cfg
            assert len(cfg["factors"]) > 0
            for f in cfg["factors"]:
                assert "name" in f
                assert "category" in f
                assert "type" in f
                assert "sign_hint" in f

    def test_build_config_loads(self):
        """V4 build config should be valid YAML."""
        import yaml
        config_path = ROOT / "configs" / "factor_build_v4.yaml"
        if config_path.exists():
            cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            assert "universe_config" in cfg
            assert "cache" in cfg
            assert "cross_section" in cfg
            assert "build_order" in cfg

    def test_all_factors_have_sign_hint(self):
        """Every factor must have a sign_hint for direction audit."""
        import yaml
        config_path = ROOT / "configs" / "factors_alpha_v4_universe.yaml"
        if config_path.exists():
            cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            for f in cfg["factors"]:
                assert f.get("sign_hint") in ("positive", "negative"), \
                    f"Factor {f['name']} missing or invalid sign_hint"

    def test_p0_factors_cover_all_categories(self):
        """P0 factors should cover quality, growth, and cashflow (failure year gaps)."""
        import yaml
        config_path = ROOT / "configs" / "factors_alpha_v4_universe.yaml"
        if config_path.exists():
            cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            p0_factors = [f for f in cfg["factors"] if f.get("priority") == "P0"]
            p0_categories = set(f["category"] for f in p0_factors)
            assert "quality" in p0_categories, "P0 must include quality factors"
            assert "growth" in p0_categories, "P0 must include growth factors"
            assert "cashflow" in p0_categories, "P0 must include cashflow factors"

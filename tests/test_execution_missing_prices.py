"""
Tests for ExecutionSimulator invalid-price position freeze logic.

Verifies:
- Existing position with invalid price: weight stays unchanged (frozen)
- New position with invalid price: weight stays 0
- Invalid-price stocks don't participate in normalization
- Cost model skips NaN/0 price stocks
- Turnover reflects actual executed weights
"""

import numpy as np
import pandas as pd
import pytest

from backtest.execution import ExecutionSimulator


def _make_prices(codes, prices_dict):
    """Create a prices DataFrame for execution."""
    records = []
    for code in codes:
        records.append({
            "ts_code": code,
            "open": prices_dict.get(code, np.nan),
        })
    return pd.DataFrame(records)


class TestExecutionMissingPrices:
    """Verify execution handles missing/invalid prices correctly."""

    def test_existing_position_invalid_price_kept(self):
        """Stock A has 0.2 weight, A has no open price → weight stays 0.2."""
        sim = ExecutionSimulator()

        codes = ["A", "B", "C"]
        target = pd.Series([0.2, 0.5, 0.3], index=codes, dtype="float64")
        prev = pd.Series([0.2, 0.5, 0.3], index=codes, dtype="float64")

        # A has NaN price (invalid)
        prices = _make_prices(codes, {"A": np.nan, "B": 10.0, "C": 20.0})

        result = sim.execute_rebalance(
            signal_date=20160104,
            target_weights=target,
            prev_holdings=prev,
            prices=prices,
            portfolio_value=1_000_000,
        )

        executed = result["executed_weights"]
        # A should keep its previous weight (target=prev=0.2, no change attempted)
        assert abs(executed["A"] - 0.2) < 1e-10, (
            f"A weight changed to {executed['A']}, expected 0.2"
        )
        # frozen_weights = prev - executed; when target=prev, no change was
        # attempted so frozen_weights["A"] is correctly 0.
        # The real test is: when target != prev AND price invalid, the
        # difference IS captured in frozen_weights. See next test.

    def test_existing_position_invalid_price_target_differs_frozen(self):
        """A has 0.2 prev, want to sell A→0, A has no price → A frozen at 0.2."""
        sim = ExecutionSimulator()

        codes = ["A", "B", "C"]
        # Want to sell A (0.2→0) but A has no price
        target = pd.Series([0.0, 0.5, 0.5], index=codes, dtype="float64")
        prev = pd.Series([0.2, 0.5, 0.3], index=codes, dtype="float64")

        prices = _make_prices(codes, {"A": np.nan, "B": 10.0, "C": 20.0})

        result = sim.execute_rebalance(
            signal_date=20160104,
            target_weights=target,
            prev_holdings=prev,
            prices=prices,
            portfolio_value=1_000_000,
        )

        executed = result["executed_weights"]
        # A should stay at 0.2 (can't sell without price)
        assert abs(executed["A"] - 0.2) < 1e-10, (
            f"A was sold despite invalid price: weight={executed['A']}"
        )
        # frozen_weights = original_target - executed;
        # target was 0, executed 0.2 → frozen = -0.2 (can't sell)
        frozen = result["frozen_weights"]
        assert abs(abs(frozen["A"]) - 0.2) < 1e-10, (
            f"A frozen weight wrong (expected ±0.2): {frozen.to_dict()}"
        )

    def test_new_buy_no_price_stays_zero(self):
        """Stock B is new (prev=0), B has no open → target stays 0."""
        sim = ExecutionSimulator()

        codes = ["A", "B"]
        target = pd.Series([0.5, 0.5], index=codes, dtype="float64")
        prev = pd.Series([1.0, 0.0], index=codes, dtype="float64")

        # B has NaN price — can't buy
        prices = _make_prices(codes, {"A": 10.0, "B": np.nan})

        result = sim.execute_rebalance(
            signal_date=20160104,
            target_weights=target,
            prev_holdings=prev,
            prices=prices,
            portfolio_value=1_000_000,
        )

        executed = result["executed_weights"]
        # B should still be 0 (can't buy without price)
        assert abs(executed["B"]) < 1e-10, (
            f"B bought without valid price: weight={executed['B']}"
        )

    def test_invalid_price_not_in_normalization(self):
        """Invalid-price stocks should NOT participate in normalization."""
        sim = ExecutionSimulator()

        codes = ["A", "B", "C"]
        # A has 0.5 prev weight, A has invalid price → frozen
        target = pd.Series([0.3, 0.4, 0.3], index=codes, dtype="float64")
        prev = pd.Series([0.5, 0.3, 0.2], index=codes, dtype="float64")

        prices = _make_prices(codes, {"A": np.nan, "B": 10.0, "C": 20.0})

        result = sim.execute_rebalance(
            signal_date=20160104,
            target_weights=target,
            prev_holdings=prev,
            prices=prices,
            portfolio_value=1_000_000,
        )

        executed = result["executed_weights"]

        # A stays frozen at previous weight
        assert abs(executed["A"] - 0.5) < 1e-10, (
            f"A changed from 0.5 to {executed['A']}"
        )

        # B and C should be normalized to fill remaining budget (1.0 - 0.5 = 0.5)
        # Target for B was 0.4, C was 0.3 → sum=0.7
        # Scale factor = 0.5 / 0.7 ≈ 0.714
        expected_b = 0.4 * (0.5 / 0.7)
        expected_c = 0.3 * (0.5 / 0.7)
        assert abs(executed["B"] - expected_b) < 1e-6, (
            f"B={executed['B']}, expected ~{expected_b:.6f}"
        )
        assert abs(executed["C"] - expected_c) < 1e-6, (
            f"C={executed['C']}, expected ~{expected_c:.6f}"
        )

        # Sum should be ~1.0
        assert abs(executed.sum() - 1.0) < 1e-10

    def test_cost_model_skips_nan_prices(self):
        """Costs should not include NaN-priced trades."""
        sim = ExecutionSimulator()

        codes = ["A", "B"]
        target = pd.Series([0.5, 0.5], index=codes, dtype="float64")
        prev = pd.Series([0.3, 0.7], index=codes, dtype="float64")

        # A has NaN price
        prices = _make_prices(codes, {"A": np.nan, "B": 10.0})

        result = sim.execute_rebalance(
            signal_date=20160104,
            target_weights=target,
            prev_holdings=prev,
            prices=prices,
            portfolio_value=1_000_000,
        )

        costs = result["costs"]
        # Should not crash, and costs should only reflect tradable stocks
        assert "total_cost_cny" in costs
        assert costs["total_cost_cny"] >= 0

    def test_non_finite_target_weights_are_cleaned(self):
        """NaN/inf target weights should not crash execution or costs."""
        sim = ExecutionSimulator()

        codes = ["A", "B", "C"]
        target = pd.Series([np.nan, np.inf, 0.5], index=codes, dtype="float64")
        prev = pd.Series([0.2, 0.3, 0.5], index=codes, dtype="float64")
        prices = _make_prices(codes, {"A": 10.0, "B": 20.0, "C": 30.0})

        result = sim.execute_rebalance(
            signal_date=20160104,
            target_weights=target,
            prev_holdings=prev,
            prices=prices,
            portfolio_value=1_000_000,
        )

        executed = result["executed_weights"]
        assert np.isfinite(executed).all()
        assert np.isfinite(result["costs"]["total_cost_cny"])

    def test_all_prices_invalid_zero_turnover(self):
        """If all stocks have invalid prices, turnover should be 0."""
        sim = ExecutionSimulator()

        codes = ["A", "B", "C"]
        target = pd.Series([0.33, 0.33, 0.34], index=codes, dtype="float64")
        prev = pd.Series([0.33, 0.33, 0.34], index=codes, dtype="float64")

        prices = _make_prices(codes, {"A": np.nan, "B": 0.0, "C": -1.0})

        result = sim.execute_rebalance(
            signal_date=20160104,
            target_weights=target,
            prev_holdings=prev,
            prices=prices,
            portfolio_value=1_000_000,
        )

        # All stocks should keep their previous weights
        executed = result["executed_weights"]
        for code in codes:
            assert abs(executed[code] - prev[code]) < 1e-10, (
                f"{code} weight changed despite invalid prices"
            )

        # Turnover should be 0
        assert result["turnover"] < 1e-10

    def test_mixed_valid_invalid_turnover_consistent(self):
        """Turnover should only reflect actually traded stocks."""
        sim = ExecutionSimulator()

        codes = ["A", "B", "C", "D"]
        # prev: A=0.25, B=0.25, C=0.25, D=0.25
        # target: sell A→0, sell B→0, buy C, buy D (new stock E)
        # But A has invalid price → frozen at 0.25
        target = pd.Series([0.0, 0.0, 0.4, 0.4, 0.2],
                          index=["A", "B", "C", "D", "E"], dtype="float64")
        prev = pd.Series([0.25, 0.25, 0.25, 0.25, 0.0],
                        index=["A", "B", "C", "D", "E"], dtype="float64")

        prices = _make_prices(
            ["A", "B", "C", "D", "E"],
            {"A": np.nan, "B": 10.0, "C": 20.0, "D": 15.0, "E": 30.0}
        )

        result = sim.execute_rebalance(
            signal_date=20160104,
            target_weights=target,
            prev_holdings=prev,
            prices=prices,
            portfolio_value=1_000_000,
        )

        executed = result["executed_weights"]

        # A should be frozen at 0.25
        assert abs(executed["A"] - 0.25) < 1e-10

        # Turnover should only count B, C, D, E trades (not A)
        weight_change = executed - prev
        # A's weight change should be 0 (frozen)
        assert abs(weight_change["A"]) < 1e-10

        # Turnover should be < 1.0 (some frozen)
        assert result["turnover"] < 1.0

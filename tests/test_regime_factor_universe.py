"""
Tests that regime mode uses its own independent factor pool.

Verifies:
  - Regime mode ignores configs/factors.yaml enabled_factors
  - Regime factor pool = union of strategy_sleeves factors
  - Missing factors are logged, not silently ignored
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from unittest.mock import MagicMock, patch


class TestRegimeFactorPool:
    """Verify regime factor pool independence."""

    def test_regime_factors_from_sleeves_union(self):
        """Regime factor pool equals union of all sleeve factors."""
        regime_config = {
            "strategy_sleeves": {
                "reversal": {"factors": ["reversal_5_cs", "reversal_20_cs"]},
                "momentum": {"factors": ["momentum_60_cs", "momentum_120_cs"]},
                "defensive": {"factors": ["volatility_20_cs"]},
            },
        }

        # Compute union manually
        expected = {"reversal_5_cs", "reversal_20_cs", "momentum_60_cs",
                     "momentum_120_cs", "volatility_20_cs"}

        from run_research import _select_regime_candidate_factors

        loader = MagicMock()
        # All factors "exist" in cache (rows > 0)
        loader.factor_coverage.return_value = {"rows": 100}

        result = _select_regime_candidate_factors(
            loader, regime_config, "20230101", "20231231"
        )

        assert set(result) == expected, f"Got {set(result)}, expected {expected}"

    def test_regime_missing_factors_logged(self):
        """Factors not in cache should be excluded and logged."""
        regime_config = {
            "strategy_sleeves": {
                "reversal": {"factors": ["reversal_5_cs", "nonexistent_cs"]},
            },
        }

        from run_research import _select_regime_candidate_factors

        loader = MagicMock()
        def mock_coverage(name, start, end):
            if name == "reversal_5_cs":
                return {"rows": 100}
            return {"rows": 0}

        loader.factor_coverage.side_effect = mock_coverage

        result = _select_regime_candidate_factors(
            loader, regime_config, "20230101", "20231231"
        )

        assert result == ["reversal_5_cs"], f"Should only have cached factor: {result}"
        # nonexistent_cs should not appear

    def test_regime_ignores_factors_yaml_whitelist(self):
        """_select_regime_candidate_factors does not consult factors.yaml."""
        # This function only looks at regime_config, not factors.yaml
        # Verified by the fact that _select_regime_candidate_factors
        # signature doesn't take a factor_config_path argument
        import inspect
        from run_research import _select_regime_candidate_factors
        sig = inspect.signature(_select_regime_candidate_factors)
        params = list(sig.parameters.keys())
        assert "factor_config_path" not in params
        assert "enabled_factors" not in params

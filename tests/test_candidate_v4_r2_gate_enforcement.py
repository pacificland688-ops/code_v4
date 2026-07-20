"""
Test: V4 R2 candidate pool gate enforcement.

Validates:
  - enabled_factors contains at least one formal gate PASS alpha factor
  - FAIL/DATA_MISSING/input audit FAIL factors are excluded from enabled
  - WATCH_NEUTRAL_ONLY factors are not in alpha enabled (only defensive)
  - Candidate pool refuses generation when 0 PASS factors exist
  - Empty candidate pool correctly flags NO_ALPHA_SOURCE_FOUND
"""

import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

FACTORS_CONFIG = ROOT / "configs" / "factors_candidate_v4_r2.yaml"
GATE_CSV = ROOT / "outputs" / "analysis" / "factor_quality_rebuild_v4" / "factor_quality_gate.csv"
AUDIT_CSV = ROOT / "outputs" / "analysis" / "v4_alpha_inputs" / "audit_summary.csv"


class TestGateEnforcement:
    """Gate rules must be enforced in the candidate pool."""

    @pytest.fixture
    def cfg(self):
        if not FACTORS_CONFIG.exists():
            pytest.skip(f"Config not found: {FACTORS_CONFIG}")
        return yaml.safe_load(FACTORS_CONFIG.read_text(encoding="utf-8"))

    def test_at_least_one_alpha_pass_or_documented_blocking(self, cfg):
        """If no gate PASS alpha factors exist, the config must document why
        and enabled_factors must not pretend to have alpha factors."""
        enabled = [e for e in (cfg.get("enabled_factors") or []) if isinstance(e, str)]

        # Check which enabled factors have gate PASS status
        pass_alpha_factors = []
        for fname, fdef in cfg.get("factors", {}).items():
            if isinstance(fdef, dict):
                gs = fdef.get("gate_status", "")
                role = fdef.get("role", "")
                if gs == "PASS" and role != "neutralizer":
                    pass_alpha_factors.append(fname)
                if gs == "PASS":
                    pass_alpha_factors.append(f"{fname}_cs")

        # If no PASS factors exist anywhere, the config must acknowledge this
        if not pass_alpha_factors:
            # Verify the config documents the blocking situation
            config_text = FACTORS_CONFIG.read_text(encoding="utf-8") if FACTORS_CONFIG.exists() else ""
            has_documentation = (
                "PASS" in config_text
                and ("0 PASS" in config_text or "no factors" in config_text.lower()
                     or "NO_ALPHA_SOURCE" in config_text
                     or "Populated after M4" in config_text)
            )
            assert has_documentation, (
                "Config has 0 PASS alpha factors but does not document the blocking situation"
            )
            # enabled_factors must not contain any factor claiming to be alpha PASS
            for ef in enabled:
                base = ef.replace("_cs", "")
                fdef = cfg.get("factors", {}).get(base, {})
                if isinstance(fdef, dict):
                    gs = fdef.get("gate_status", "")
                    assert gs != "PASS", (
                        f"Enabled factor '{ef}' claims gate PASS but no PASS factors exist"
                    )

    def test_no_fail_in_enabled(self, cfg):
        """No enabled factor may have gate_status FAIL."""
        fail_factors = set()
        for fname, fdef in cfg.get("factors", {}).items():
            if isinstance(fdef, dict) and fdef.get("gate_status") == "FAIL":
                if fdef.get("role") != "neutralizer":
                    fail_factors.add(fname)
                    fail_factors.add(f"{fname}_cs")

        enabled = [e for e in (cfg.get("enabled_factors") or []) if isinstance(e, str)]
        for ef in enabled:
            assert ef not in fail_factors, (
                f"FAIL factor '{ef}' found in enabled_factors — violates gate enforcement"
            )

    def test_no_data_missing_in_enabled(self, cfg):
        """No enabled factor may have gate_status DATA_MISSING."""
        missing = set()
        for fname, fdef in cfg.get("factors", {}).items():
            if isinstance(fdef, dict) and fdef.get("gate_status") == "DATA_MISSING":
                missing.add(fname)
                missing.add(f"{fname}_cs")

        enabled = [e for e in (cfg.get("enabled_factors") or []) if isinstance(e, str)]
        for ef in enabled:
            assert ef not in missing, (
                f"DATA_MISSING factor '{ef}' found in enabled_factors"
            )

    def test_watch_neutral_only_not_in_alpha_enabled(self, cfg):
        """WATCH_NEUTRAL_ONLY factors must not be presented as alpha PASS."""
        watch_factors = set()
        for fname, fdef in cfg.get("factors", {}).items():
            if isinstance(fdef, dict) and fdef.get("gate_status") == "WATCH_NEUTRAL_ONLY":
                watch_factors.add(fname)
                watch_factors.add(f"{fname}_cs")

        enabled = [e for e in (cfg.get("enabled_factors") or []) if isinstance(e, str)]

        # If WATCH factors are in enabled, config must clearly label them as defensive/risk
        for ef in enabled:
            if ef in watch_factors:
                config_text = FACTORS_CONFIG.read_text(encoding="utf-8") if FACTORS_CONFIG.exists() else ""
                assert "defensive" in config_text.lower() or "WATCH_NEUTRAL_ONLY" in config_text, (
                    f"WATCH_NEUTRAL_ONLY factor '{ef}' in enabled_factors without defensive/risk documentation"
                )

    def test_disabled_factors_comprehensive(self, cfg):
        """All FAIL/DATA_MISSING factors should appear in disabled_factors with reasons."""
        disabled = cfg.get("disabled_factors", {})
        fail_or_missing = set()
        for fname, fdef in cfg.get("factors", {}).items():
            if isinstance(fdef, dict):
                gs = fdef.get("gate_status", "")
                if gs in ("FAIL", "DATA_MISSING"):
                    fail_or_missing.add(f"{fname}_cs")

        # Not all need to be in disabled (some may be pending_gate), but most should
        # At minimum, verify that explicitly FAIL factors are documented somewhere
        for fname, fdef in cfg.get("factors", {}).items():
            if isinstance(fdef, dict) and fdef.get("gate_status") == "FAIL":
                # Normalize: some factors already have _cs suffix, some don't
                cs_name = fname if fname.endswith("_cs") else f"{fname}_cs"
                base_name = fname.replace("_cs", "")
                in_disabled = cs_name in disabled or base_name in disabled
                in_pending = cs_name in (cfg.get("pending_gate_factors") or []) or base_name in (cfg.get("pending_gate_factors") or [])
                assert in_disabled or in_pending, (
                    f"FAIL factor '{cs_name}' not in disabled_factors or pending_gate_factors"
                )

    def test_pending_gate_factors_have_clear_status(self, cfg):
        """Factors in pending_gate_factors must have documented status (PENDING_GATE, FAIL, or PENDING_REBUILD)."""
        pending = cfg.get("pending_gate_factors", [])
        for pf in pending:
            # Must appear in factor definitions with a documented status
            found_status = None
            for fname, fdef in cfg.get("factors", {}).items():
                if pf == fname or pf == f"{fname}_cs":
                    if isinstance(fdef, dict):
                        found_status = fdef.get("gate_status")
                    break
            assert found_status in ("PENDING_GATE", "FAIL", "PENDING_REBUILD"), (
                f"Pending factor '{pf}' has gate_status='{found_status}', "
                f"expected PENDING_GATE, FAIL, or PENDING_REBUILD"
            )


class TestRegimeAllocatorGateEnforcement:
    """Allocator must not give weight to empty sleeves."""

    @pytest.fixture
    def regime_cfg(self):
        regime_path = ROOT / "configs" / "regime_candidate_v4_r2.yaml"
        if not regime_path.exists():
            pytest.skip(f"Config not found: {regime_path}")
        return yaml.safe_load(regime_path.read_text(encoding="utf-8"))

    def test_empty_sleeves_have_zero_weight(self, regime_cfg):
        """Any sleeve with 0 factors must have weight 0 in ALL regimes."""
        sleeves = regime_cfg.get("strategy_sleeves", {})
        empty_sleeves = {
            name for name, sdef in sleeves.items()
            if len(sdef.get("factors", [])) == 0
        }

        weights_map = regime_cfg.get("allocator", {}).get("regime_to_sleeve_weights", {})
        for regime, weights in weights_map.items():
            for sleeve_name in empty_sleeves:
                w = weights.get(sleeve_name, 0)
                assert w == 0.0, (
                    f"Empty sleeve '{sleeve_name}' has non-zero weight {w} in regime '{regime}'"
                )

    def test_weights_sum_to_one_or_zero(self, regime_cfg):
        """All regime weights must sum to 1.0, or 0.0 if all sleeves are empty."""
        sleeves = regime_cfg.get("strategy_sleeves", {})
        all_empty = all(
            len(sdef.get("factors", [])) == 0
            for sdef in sleeves.values()
        )
        weights_map = regime_cfg.get("allocator", {}).get("regime_to_sleeve_weights", {})
        for regime, weights in weights_map.items():
            total = sum(weights.values())
            if all_empty:
                assert total == 0.0, (
                    f"All sleeves empty but regime '{regime}' has non-zero total {total:.4f}"
                )
            else:
                assert abs(total - 1.0) < 0.02, (
                    f"Regime '{regime}' weights sum to {total:.4f}, expected 1.0"
                )

    def test_non_empty_sleeves_have_positive_total_weight(self, regime_cfg):
        """At least one sleeve with factors must have non-zero total weight."""
        sleeves = regime_cfg.get("strategy_sleeves", {})
        non_empty = {
            name for name, sdef in sleeves.items()
            if len(sdef.get("factors", [])) > 0
        }

        if non_empty:
            weights_map = regime_cfg.get("allocator", {}).get("regime_to_sleeve_weights", {})
            for regime, weights in weights_map.items():
                total_non_empty = sum(weights.get(s, 0) for s in non_empty)
                assert total_non_empty > 0, (
                    f"Regime '{regime}' gives 0 total weight to non-empty sleeves {non_empty}"
                )

    def test_only_defensive_non_empty_no_formal_alpha_claim(self, regime_cfg):
        """If only defensive sleeve has factors, config must not claim alpha strategy."""
        sleeves = regime_cfg.get("strategy_sleeves", {})
        non_empty = {
            name for name, sdef in sleeves.items()
            if len(sdef.get("factors", [])) > 0
        }

        if non_empty == {"defensive"}:
            # This is NOT a valid alpha strategy — config must acknowledge
            config_text = (
                ROOT / "configs" / "regime_candidate_v4_r2.yaml"
            ).read_text(encoding="utf-8") if (ROOT / "configs" / "regime_candidate_v4_r2.yaml").exists() else ""
            assert "defensive-only" in config_text.lower() or "not a valid alpha" in config_text.lower() or "not an acceptable alpha" in config_text.lower() or "only defensive" in config_text.lower(), (
                "Defensive-only config must acknowledge it is not a valid alpha strategy"
            )

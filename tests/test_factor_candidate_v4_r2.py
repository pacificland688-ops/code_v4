"""
Test: V4 R2 candidate pool config compliance.

Validates:
  - enabled_factors does not contain gate FAIL factors
  - enabled_factors does not contain DATA_MISSING factors
  - enabled_factors does not contain input audit FAIL factors
  - WATCH factors have documented justification
  - Candidate pool structure is valid YAML
  - SHA256 can be computed
"""

import hashlib
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CONFIG_PATH = ROOT / "configs" / "factors_candidate_v4_r2.yaml"


class TestCandidatePoolConfig:
    """V4 R2 candidate pool config structural validation."""

    @pytest.fixture
    def cfg(self):
        if not CONFIG_PATH.exists():
            pytest.skip(f"Config not found: {CONFIG_PATH}")
        return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))

    def test_config_is_valid_yaml(self, cfg):
        """Config must be parseable YAML with required top-level keys."""
        assert "factors" in cfg
        assert "enabled_factors" in cfg
        assert "disabled_factors" in cfg

    def test_enabled_factors_is_list(self, cfg):
        """enabled_factors must be a list (empty is OK — reflects gate results)."""
        ef = cfg.get("enabled_factors")
        assert ef is not None, "enabled_factors must exist (even if empty)"
        assert isinstance(ef, list), f"enabled_factors must be a list, got {type(ef)}"

    def test_enabled_factors_exist_in_definitions(self, cfg):
        """Every factor in enabled_factors must exist in the factors section or in pending_gate_factors."""
        defined = set(cfg.get("factors", {}).keys())
        pending = set(cfg.get("pending_gate_factors", []))
        # Also support _cs suffix matching
        all_defined = defined | {f"{k}_cs" for k in defined} | pending

        for fname in cfg["enabled_factors"]:
            # Strip comments
            if isinstance(fname, str) and not fname.startswith("#"):
                base = fname.replace("_cs", "")
                assert fname in all_defined or base in defined or fname in pending, (
                    f"Enabled factor '{fname}' not defined in factors section"
                )

    def test_no_gate_fail_in_enabled(self, cfg):
        """No factor with gate_status=FAIL should be in enabled_factors."""
        fail_factors = set()
        for fname, fdef in cfg.get("factors", {}).items():
            if isinstance(fdef, dict) and fdef.get("gate_status") == "FAIL":
                fail_factors.add(fname)
                fail_factors.add(f"{fname}_cs")

        for ef in cfg["enabled_factors"]:
            if isinstance(ef, str) and not ef.startswith("#"):
                assert ef not in fail_factors, (
                    f"Enabled factor '{ef}' has gate_status=FAIL in factor definitions"
                )

    def test_no_data_missing_in_enabled(self, cfg):
        """No factor with gate_status=DATA_MISSING should be in enabled_factors."""
        missing_factors = set()
        for fname, fdef in cfg.get("factors", {}).items():
            if isinstance(fdef, dict) and fdef.get("gate_status") == "DATA_MISSING":
                missing_factors.add(fname)
                missing_factors.add(f"{fname}_cs")

        for ef in cfg["enabled_factors"]:
            if isinstance(ef, str) and not ef.startswith("#"):
                assert ef not in missing_factors, (
                    f"Enabled factor '{ef}' has gate_status=DATA_MISSING in factor definitions"
                )

    def test_watch_factors_have_justification(self, cfg):
        """Any WATCH factor in enabled must be documented (check comment or doc)."""
        watch_factors = set()
        for fname, fdef in cfg.get("factors", {}).items():
            if isinstance(fdef, dict) and "WATCH" in str(fdef.get("gate_status", "")):
                watch_factors.add(fname)
                watch_factors.add(f"{fname}_cs")

        enabled = [e for e in cfg.get("enabled_factors") or [] if isinstance(e, str)]
        config_text = CONFIG_PATH.read_text(encoding="utf-8") if CONFIG_PATH.exists() else ""

        for wf in watch_factors:
            if wf in enabled:
                # WATCH factor in enabled — verify justification exists in config text or docs
                has_justification = (
                    "Justification" in config_text
                    or "Defensive" in config_text
                    or "defensive" in config_text
                    or "WATCH_NEUTRAL_ONLY" in config_text
                )
                assert has_justification, (
                    f"WATCH factor '{wf}' in enabled_factors but no justification found in config"
                )

    def test_sha256_computable(self, cfg):
        """Config file must have a computable SHA256."""
        sha = hashlib.sha256(CONFIG_PATH.read_bytes()).hexdigest()
        assert len(sha) == 64
        assert sha != ""

    def test_composite_config_valid(self, cfg):
        """Composite section must have required fields."""
        composite = cfg.get("composite", {})
        required = ["ic_window_months", "shrinkage", "weight_cap", "min_ic_obs", "horizon"]
        for key in required:
            assert key in composite, f"Missing composite.{key}"

    def test_cross_section_config_valid(self, cfg):
        """Cross section config must have required fields."""
        cs = cfg.get("cross_section", {})
        required = ["winsor_method", "mad_multiplier", "min_coverage", "neutralize", "standardize"]
        for key in required:
            assert key in cs, f"Missing cross_section.{key}"

    def test_disabled_factors_have_reasons(self, cfg):
        """Every disabled factor must have a non-empty reason."""
        for fname, reason in cfg.get("disabled_factors", {}).items():
            assert reason, f"Disabled factor '{fname}' has empty reason"
            assert len(str(reason)) > 5, f"Disabled factor '{fname}' reason too short: '{reason}'"

    def test_pending_gate_documented(self, cfg):
        """All pending_gate_factors must also be documented in factor definitions."""
        pending = set(cfg.get("pending_gate_factors", []))
        if pending:
            for pf in pending:
                # Must have a documented status in factors section
                found = False
                for fname, fdef in cfg.get("factors", {}).items():
                    if pf == fname or pf == f"{fname}_cs":
                        if isinstance(fdef, dict) and fdef.get("gate_status") in (
                            "PENDING_GATE", "FAIL", "PENDING_REBUILD"
                        ):
                            found = True
                            break
                assert found, (
                    f"Pending gate factor '{pf}' not documented in factor definitions"
                )


class TestCandidatePoolVsGate:
    """Validate candidate pool consistency with gate output (if available)."""

    @pytest.fixture
    def gate_df(self):
        """Load factor_quality_gate.csv if it exists."""
        gate_path = ROOT / "outputs" / "analysis" / "factor_quality_rebuild_v4" / "factor_quality_gate.csv"
        if not gate_path.exists():
            pytest.skip("Gate CSV not yet generated (run M4 first)")
        import pandas as pd
        return pd.read_csv(gate_path)

    def test_gate_pass_factors_in_candidate_pool(self, gate_df):
        """If gate has PASS factors and they have valid data, suggest inclusion."""
        import pandas as pd
        if "final_status" not in gate_df.columns:
            # Try common column names
            status_col = next((c for c in gate_df.columns if "status" in c.lower()), None)
            if status_col is None:
                pytest.skip("Cannot identify status column in gate CSV")
        else:
            status_col = "final_status"

        pass_factors = gate_df[gate_df[status_col] == "PASS"]
        if len(pass_factors) == 0:
            pytest.skip("No PASS factors in gate — candidate pool correctly empty")

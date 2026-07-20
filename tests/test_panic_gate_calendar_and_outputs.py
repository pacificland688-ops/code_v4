"""
Unit tests for calendar and output governance — final acceptance v1.

Covers:
  9. embargo uses full market calendar, not basket dates
 10. Old outputs not in main output directory
 11. Final manifest exists and matches report status
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from panic_gate_shared import (  # noqa: E402
    build_trading_calendar, load_market_calendar,
    EMBARGO_DAYS, PRIMARY_GATE_STRATEGY,
)

OUT_DIR = ROOT / "outputs" / "analysis" / "panic_reversal_gate" / "daily_basket_v1"


# ═══════════════════════════════════════════════════════════════════════
# Test 9: Embargo uses full market calendar
# ═══════════════════════════════════════════════════════════════════════

class TestMarketCalendar:
    def test_load_market_calendar_returns_data(self):
        """load_market_calendar must return full market dates."""
        cal = load_market_calendar(ROOT, 20170101, 20251231)
        assert cal is not None, "Market calendar is None"
        assert len(cal) > 400, f"Calendar too small: {len(cal)} days (expected >400)"
        # Full market should have ~2500 days for 2017-2025
        assert len(cal) > 2000, \
            f"Calendar seems sparse: {len(cal)} days (expected ~2500 for 2017-2025)"

    def test_market_calendar_larger_than_basket(self):
        """Full market calendar must be larger than basket date count."""
        cal = load_market_calendar(ROOT, 20170101, 20251231)
        assert cal is not None
        n_market = len(cal)

        # Basket dates from daily_samples
        samples_path = OUT_DIR / "panic_basket_daily_samples.csv"
        if samples_path.exists():
            df = pd.read_csv(samples_path)
            n_basket = df["trade_date"].nunique()
            assert n_market > n_basket * 2, \
                f"Market calendar ({n_market}) not >> basket dates ({n_basket})"

    def test_leakage_audit_has_calendar_source(self):
        """Leakage audit must specify calendar_source."""
        audit_path = OUT_DIR / "panic_sleeve_gate_leakage_audit.csv"
        if not audit_path.exists():
            pytest.skip("leakage audit not found")

        df = pd.read_csv(audit_path)
        assert "calendar_source" in df.columns, \
            "Leakage audit missing calendar_source column"
        assert (df["calendar_source"] == "prices_adj_full_market").all(), \
            f"calendar_source not prices_adj_full_market: {df['calendar_source'].unique()}"

    def test_leakage_audit_has_calendar_is_full_market(self):
        """Leakage audit must confirm full market calendar."""
        audit_path = OUT_DIR / "panic_sleeve_gate_leakage_audit.csv"
        if not audit_path.exists():
            pytest.skip("leakage audit not found")

        df = pd.read_csv(audit_path)
        assert "calendar_is_full_market" in df.columns, \
            "Leakage audit missing calendar_is_full_market column"

    def test_leakage_audit_has_embargo_cutoff_date(self):
        """Leakage audit must record embargo_cutoff_date."""
        audit_path = OUT_DIR / "panic_sleeve_gate_leakage_audit.csv"
        if not audit_path.exists():
            pytest.skip("leakage audit not found")

        df = pd.read_csv(audit_path)
        assert "embargo_cutoff_date" in df.columns, \
            "Leakage audit missing embargo_cutoff_date column"

    def test_embargo_uses_real_trading_days(self):
        """Embargo gap must be real trading days, not basket dates."""
        # Synthetic test: sparse basket calendar vs full market calendar
        market_cal = np.array([20200102 + i for i in range(100)])  # 100 consecutive days
        basket_dates = market_cal[::5]  # every 5th day = 20 sparse dates

        from panic_gate_shared import trading_day_offset
        # Embargo of 20 market days from day 50
        embargo = trading_day_offset(market_cal, int(market_cal[50]), -20)
        assert embargo == int(market_cal[30]), \
            "Embargo must use market calendar, not basket dates"
        # This is 20 real trading days, not 20 basket events

    def test_calendar_n_days_recorded(self):
        """calendar_n_days must be recorded in audit."""
        audit_path = OUT_DIR / "panic_sleeve_gate_leakage_audit.csv"
        if not audit_path.exists():
            pytest.skip("leakage audit not found")

        df = pd.read_csv(audit_path)
        assert "calendar_n_days" in df.columns, \
            "Leakage audit missing calendar_n_days"
        if len(df) > 0:
            cd = df["calendar_n_days"].iloc[0]
            assert cd > 400, f"calendar_n_days too small: {cd}"


# ═══════════════════════════════════════════════════════════════════════
# Test 10: Old outputs not in main directory
# ═══════════════════════════════════════════════════════════════════════

class TestDeprecatedOutputs:
    def test_old_backtest_compare_not_in_main_dir(self):
        """Old backtest_compare.csv must not be in main output dir."""
        path = OUT_DIR / "panic_sleeve_gate_backtest_compare.csv"
        assert not path.exists(), \
            f"Old file still in main dir: {path.name}"

    def test_old_daily_signals_not_in_main_dir(self):
        """Old daily_signals.csv must not be in main output dir."""
        path = OUT_DIR / "panic_sleeve_gate_daily_signals.csv"
        assert not path.exists(), \
            f"Old file still in main dir: {path.name}"

    def test_old_yearly_attribution_not_in_main_dir(self):
        """Old yearly_attribution.csv must not be in main output dir."""
        path = OUT_DIR / "panic_sleeve_gate_yearly_attribution.csv"
        assert not path.exists(), \
            f"Old file still in main dir: {path.name}"

    def test_deprecated_dir_exists(self):
        """deprecated/ directory must exist."""
        dep_dir = OUT_DIR / "deprecated"
        assert dep_dir.exists(), "deprecated/ directory not found"

    def test_deprecated_manifest_exists(self):
        """deprecated_manifest.json must exist."""
        path = OUT_DIR / "deprecated" / "deprecated_manifest.json"
        assert path.exists(), "deprecated_manifest.json not found"

    def test_deprecated_manifest_valid(self):
        """deprecated_manifest.json must list deprecated files."""
        path = OUT_DIR / "deprecated" / "deprecated_manifest.json"
        if not path.exists():
            pytest.skip("deprecated_manifest.json not found")

        manifest = json.loads(path.read_text(encoding="utf-8"))
        assert len(manifest) > 0, "deprecated_manifest is empty"
        for entry in manifest:
            assert "file" in entry, f"Missing 'file' in: {entry}"
            assert "deprecated_reason" in entry
            assert "deprecated_at" in entry


# ═══════════════════════════════════════════════════════════════════════
# Test 11: Final manifest
# ═══════════════════════════════════════════════════════════════════════

class TestFinalManifest:
    def test_final_manifest_exists(self):
        """panic_basket_gate_final_manifest.json must exist."""
        path = OUT_DIR / "panic_basket_gate_final_manifest.json"
        assert path.exists(), "final_manifest.json not found"

    def test_final_manifest_has_required_fields(self):
        """Final manifest must contain all required fields."""
        path = OUT_DIR / "panic_basket_gate_final_manifest.json"
        if not path.exists():
            pytest.skip("final_manifest.json not found")

        m = json.loads(path.read_text(encoding="utf-8"))
        required = [
            "schema", "research_only", "production_eligible",
            "final_status", "primary_strategy",
            "leakage_audit", "threshold_audit",
            "event_forward_status", "real_path_status",
            "real_path_output_contract",
            "block_reasons", "valid_output_files", "deprecated_output_files",
        ]
        for field in required:
            assert field in m, f"Missing field in final manifest: {field}"

    def test_final_manifest_research_only(self):
        """research_only must be true, production_eligible must be false."""
        path = OUT_DIR / "panic_basket_gate_final_manifest.json"
        if not path.exists():
            pytest.skip("final_manifest.json not found")

        m = json.loads(path.read_text(encoding="utf-8"))
        assert m["research_only"] is True, "research_only must be True"
        assert m["production_eligible"] is False, "production_eligible must be False"

    def test_final_manifest_primary_strategy(self):
        """Primary strategy must be gate_ml_logreg."""
        path = OUT_DIR / "panic_basket_gate_final_manifest.json"
        if not path.exists():
            pytest.skip("final_manifest.json not found")

        m = json.loads(path.read_text(encoding="utf-8"))
        assert m["primary_strategy"] == PRIMARY_GATE_STRATEGY, \
            f"Wrong primary: {m['primary_strategy']}"

    def test_final_manifest_status_consistent_with_audit(self):
        """If leakage_audit is PASS, final_status reflects event_forward + real_path."""
        path = OUT_DIR / "panic_basket_gate_final_manifest.json"
        if not path.exists():
            pytest.skip("final_manifest.json not found")

        m = json.loads(path.read_text(encoding="utf-8"))
        if m["leakage_audit"] == "FAIL":
            assert m["final_status"] == "NO_GO", \
                "leakage FAIL must result in NO_GO"
        if m["threshold_audit"] == "FAIL":
            assert m["final_status"] == "NO_GO", \
                "threshold FAIL must result in NO_GO"
        if m["real_path_output_contract"] == "FAIL":
            assert m["final_status"] == "NO_GO", \
                "real_path output contract FAIL must result in NO_GO"

    def test_final_manifest_lists_valid_files(self):
        """valid_output_files must list files that actually exist."""
        path = OUT_DIR / "panic_basket_gate_final_manifest.json"
        if not path.exists():
            pytest.skip("final_manifest.json not found")

        m = json.loads(path.read_text(encoding="utf-8"))
        valid_files = m.get("valid_output_files", [])
        assert len(valid_files) > 5, f"Too few valid files: {len(valid_files)}"
        for fname in valid_files:
            fpath = OUT_DIR / fname
            assert fpath.exists(), \
                f"Valid file listed in manifest but missing: {fname}"

    def test_final_manifest_deprecated_files_match_actual(self):
        """deprecated_output_files must match files actually in deprecated/."""
        path = OUT_DIR / "panic_basket_gate_final_manifest.json"
        dep_dir = OUT_DIR / "deprecated"
        if not path.exists() or not dep_dir.exists():
            pytest.skip("manifest or deprecated/ not found")

        m = json.loads(path.read_text(encoding="utf-8"))
        deprecated_listed = set(m.get("deprecated_output_files", []))
        deprecated_actual = set(
            f.name for f in dep_dir.iterdir()
            if f.is_file() and f.name != "deprecated_manifest.json"
        )
        # All deprecated files should be listed
        for f in deprecated_actual:
            assert f in deprecated_listed, \
                f"File in deprecated/ but not in manifest: {f}"

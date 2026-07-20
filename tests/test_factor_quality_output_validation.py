"""Tests for validate_factor_quality_outputs.py check functions."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pandas as pd
import pytest
import yaml

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.validate_factor_quality_outputs import (
    check_neutralization_validity,
    check_gate_neutralization_consistency,
    check_capacity_cny_scale,
    check_capacity_participation,
    check_candidate_pool_contract,
    check_run_manifest,
    check_diagnostic_csvs_in_run_dir,
    check_no_diagnostic_csvs_in_root,
)


def _write_csv(tmp_path: Path, name: str, data: list[dict]) -> Path:
    df = pd.DataFrame(data)
    p = tmp_path / name
    df.to_csv(p, index=False, encoding="utf-8-sig")
    return tmp_path


def _write_yaml(tmp_path: Path, name: str, data: dict) -> Path:
    p = tmp_path / name
    p.write_text(yaml.dump(data, allow_unicode=True), encoding="utf-8")
    return tmp_path


class TestNeutralizationValidity:
    def test_low_coverage_ok_fails(self, tmp_path):
        _write_csv(tmp_path, "factor_neutralization_diagnostic.csv", [
            {"factor": "foo_cs", "neutralizer_coverage_pct": 5.0,
             "neutralization_status": "OK", "neutralization_valid": False}
        ])
        config = {"neutralization": {"min_neutralizer_coverage_pct": 70}}
        issues = check_neutralization_validity(tmp_path, config)
        assert len(issues) > 0, "Low coverage + OK must fail"

    def test_low_coverage_size_dependent_fails(self, tmp_path):
        _write_csv(tmp_path, "factor_neutralization_diagnostic.csv", [
            {"factor": "bar_cs", "neutralizer_coverage_pct": 5.0,
             "neutralization_status": "SIZE_DEPENDENT", "neutralization_valid": False}
        ])
        config = {"neutralization": {"min_neutralizer_coverage_pct": 70}}
        issues = check_neutralization_validity(tmp_path, config)
        assert len(issues) > 0, "Low coverage + SIZE_DEPENDENT must fail"

    def test_normal_coverage_passes(self, tmp_path):
        _write_csv(tmp_path, "factor_neutralization_diagnostic.csv", [
            {"factor": "good_cs", "neutralizer_coverage_pct": 100.0,
             "neutralization_status": "OK", "neutralization_valid": True}
        ])
        config = {"neutralization": {"min_neutralizer_coverage_pct": 70}}
        issues = check_neutralization_validity(tmp_path, config)
        assert len(issues) == 0, f"Normal coverage should pass, got {issues}"


class TestGateNeutralizationConsistency:
    def test_watch_neutral_only_invalid_fails(self, tmp_path):
        _write_csv(tmp_path, "factor_quality_gate.csv", [
            {"factor": "foo_cs", "quality_gate_status": "WATCH_NEUTRAL_ONLY"}
        ])
        _write_csv(tmp_path, "factor_neutralization_diagnostic.csv", [
            {"factor": "foo_cs", "neutralizer_coverage_pct": 5.0,
             "neutralization_status": "LOW_COVERAGE", "neutralization_valid": False}
        ])
        config = {"neutralization": {"min_neutralizer_coverage_pct": 70,
                                     "require_valid_neutralization_for_neutral_gate": True}}
        issues = check_gate_neutralization_consistency(tmp_path, config)
        assert len(issues) > 0, "WATCH_NEUTRAL_ONLY with invalid neutralization must fail"

    def test_pass_invalid_neutralization_fails(self, tmp_path):
        _write_csv(tmp_path, "factor_quality_gate.csv", [
            {"factor": "foo_cs", "quality_gate_status": "PASS"}
        ])
        _write_csv(tmp_path, "factor_neutralization_diagnostic.csv", [
            {"factor": "foo_cs", "neutralizer_coverage_pct": 5.0,
             "neutralization_status": "LOW_COVERAGE", "neutralization_valid": False}
        ])
        config = {"neutralization": {"min_neutralizer_coverage_pct": 70,
                                     "require_valid_neutralization_for_neutral_gate": True}}
        issues = check_gate_neutralization_consistency(tmp_path, config)
        assert len(issues) > 0, "PASS with invalid neutralization must fail"


class TestCapacityCNYScale:
    def test_market_cap_wan_scale_fails(self, tmp_path):
        _write_csv(tmp_path, "factor_capacity_audit.csv", [
            {"factor": "foo_cs", "year": 2024,
             "median_market_cap_cny": 8758455,  # still万元
             "median_top_amount_cny": 500000000}
        ])
        issues = check_capacity_cny_scale(tmp_path, {})
        assert len(issues) > 0, "Market cap in 万元 must fail"

    def test_normal_cny_scale_passes(self, tmp_path):
        _write_csv(tmp_path, "factor_capacity_audit.csv", [
            {"factor": "good_cs", "year": 2024,
             "median_market_cap_cny": 80_000_000_000,
             "median_top_amount_cny": 500_000_000}
        ])
        issues = check_capacity_cny_scale(tmp_path, {})
        assert len(issues) == 0, f"Normal CNY scale should pass, got {issues}"


class TestCapacityParticipation:
    def test_participation_formula_mismatch_fails(self, tmp_path):
        _write_csv(tmp_path, "factor_capacity_audit.csv", [
            {"factor": "foo_cs", "year": 2024,
             "estimated_trade_cny_at_target_aum": 50_000_000,
             "median_leg_amount_sum_cny": 1_000_000_000,
             "participation_rate_at_target_aum": 0.20}  # should be 0.05
        ])
        issues = check_capacity_participation(tmp_path)
        assert len(issues) > 0, "Wrong participation formula must fail"

    def test_correct_participation_passes(self, tmp_path):
        _write_csv(tmp_path, "factor_capacity_audit.csv", [
            {"factor": "good_cs", "year": 2024,
             "estimated_trade_cny_at_target_aum": 50_000_000,
             "median_leg_amount_sum_cny": 50_000_000_000,
             "participation_rate_at_target_aum": 0.001}
        ])
        issues = check_capacity_participation(tmp_path)
        assert len(issues) == 0, f"Correct participation should pass, got {issues}"


class TestCandidatePoolContract:
    def test_log_market_cap_in_eligible_fails(self, tmp_path):
        _write_yaml(tmp_path, "factor_candidate_pool.yaml", {
            "eligible_factors": ["log_market_cap_cs", "foo_cs"],
            "watch_factors_for_review": [],
            "support_factors": {"neutralizers": [], "redundant": []},
            "missing_data_factors": [],
            "fail_factors": [],
            "recommendation": "2 eligible factor(s)"
        })
        issues = check_candidate_pool_contract(tmp_path)
        assert len(issues) > 0, "log_market_cap_cs in eligible must fail"

    def test_empty_eligible_no_alpha_source(self, tmp_path):
        _write_yaml(tmp_path, "factor_candidate_pool.yaml", {
            "eligible_factors": [],
            "watch_factors_for_review": [],
            "support_factors": {"neutralizers": ["log_market_cap_cs"], "redundant": []},
            "missing_data_factors": ["roe_cs"],
            "fail_factors": ["reversal_5_cs"],
            "recommendation": "NO_ALPHA_SOURCE_FOUND"
        })
        issues = check_candidate_pool_contract(tmp_path)
        assert len(issues) == 0, f"Correct NO_ALPHA contract should pass, got {issues}"


# ---------------------------------------------------------------------------
# Manifest and diagnostic CSV validator tests
# ---------------------------------------------------------------------------

class TestManifestValidator:
    """Verify check_run_manifest catches missing/empty fields."""

    def test_fails_empty_manifest_start_time(self, tmp_path):
        run_dir = tmp_path / "_run_testval001"
        run_dir.mkdir()
        manifest = {
            "run_id": "testval001",
            "config_path": "configs/test.yaml",
            "config_sha256": "abc123def456",
            "seed": 42,
            "factor_count": 3,
            "out_dir": "outputs/test",
            "out_doc": "docs/report.md",
            "start_time": "",
            "end_time": "2026-06-18T16:56:46",
            "status": "SUCCESS",
        }
        (run_dir / "run_manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

        issues = check_run_manifest(tmp_path, config_path=None)
        assert len(issues) > 0, "Empty start_time on SUCCESS must produce issues"
        assert any("start_time" in i for i in issues), \
            f"Issues should mention start_time, got: {issues}"

    def test_fails_missing_required_field(self, tmp_path):
        run_dir = tmp_path / "_run_testval002"
        run_dir.mkdir()
        manifest = {
            "run_id": "testval002",
            "config_path": "configs/test.yaml",
            # config_sha256 missing
            "seed": 42,
            "factor_count": 3,
            "out_dir": "outputs/test",
            "out_doc": "docs/report.md",
            "start_time": "2026-06-18T16:28:43",
            "end_time": "2026-06-18T16:56:46",
            "status": "SUCCESS",
        }
        (run_dir / "run_manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

        issues = check_run_manifest(tmp_path, config_path=None)
        assert len(issues) > 0, "Missing required field must produce issues"
        assert any("config_sha256" in i for i in issues), \
            f"Issues should mention config_sha256, got: {issues}"

    def test_fails_end_time_before_start_time(self, tmp_path):
        run_dir = tmp_path / "_run_testval003"
        run_dir.mkdir()
        manifest = {
            "run_id": "testval003",
            "config_path": "configs/test.yaml",
            "config_sha256": "abc123def456",
            "seed": 42,
            "factor_count": 3,
            "out_dir": "outputs/test",
            "out_doc": "docs/report.md",
            "start_time": "2026-06-18T16:56:46",
            "end_time": "2026-06-18T16:28:43",  # before start_time
            "status": "SUCCESS",
        }
        (run_dir / "run_manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

        issues = check_run_manifest(tmp_path, config_path=None)
        assert len(issues) > 0, "end_time < start_time must produce issues"
        assert any("end_time" in i and "start_time" in i for i in issues), \
            f"Issues should mention ordering, got: {issues}"

    def test_valid_manifest_passes(self, tmp_path):
        run_dir = tmp_path / "_run_testval004"
        run_dir.mkdir()
        manifest = {
            "run_id": "testval004",
            "config_path": "configs/test.yaml",
            "config_sha256": "abc123def456",
            "seed": 42,
            "factor_count": 3,
            "out_dir": "outputs/test",
            "out_doc": "docs/report.md",
            "start_time": "2026-06-18T16:28:43",
            "end_time": "2026-06-18T16:56:46",
            "status": "SUCCESS",
        }
        (run_dir / "run_manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

        issues = check_run_manifest(tmp_path, config_path=None)
        assert len(issues) == 0, f"Valid manifest should pass, got: {issues}"


class TestDiagnosticCsvValidator:
    """Verify diagnostic CSV existence and root pollution checks."""

    def test_fails_diagnostic_csv_leaked_to_root(self, tmp_path):
        # Place a leaked diagnostic CSV in out_dir root
        (tmp_path / "run_progress.csv").write_text("col1\nval1", encoding="utf-8-sig")
        # Also create a valid _run_* dir with manifest so the check has context
        run_dir = tmp_path / "_run_testval010"
        run_dir.mkdir()

        issues = check_no_diagnostic_csvs_in_root(tmp_path)
        assert len(issues) > 0, "Leaked diagnostic CSV in root must fail"
        assert any("run_progress.csv" in i for i in issues), \
            f"Issues should name the leaked file, got: {issues}"

    def test_clean_root_passes(self, tmp_path):
        run_dir = tmp_path / "_run_testval011"
        run_dir.mkdir()
        # No diagnostic CSVs in root

        issues = check_no_diagnostic_csvs_in_root(tmp_path)
        assert len(issues) == 0, f"Clean root should pass, got: {issues}"

    def test_fails_missing_diagnostic_csv_in_run_dir(self, tmp_path):
        run_dir = tmp_path / "_run_testval012"
        run_dir.mkdir()
        # Don't create any diagnostic CSVs — check should fail

        issues = check_diagnostic_csvs_in_run_dir(tmp_path)
        assert len(issues) > 0, "Missing diagnostic CSVs must produce issues"
        # All 3 should be missing
        assert len(issues) == 3, f"Expected 3 missing, got {len(issues)}: {issues}"

    def test_passes_when_all_diagnostic_csvs_present(self, tmp_path):
        run_dir = tmp_path / "_run_testval013"
        run_dir.mkdir()
        for name in ["run_progress.csv", "run_stage_timings.csv", "run_errors.csv"]:
            (run_dir / name).write_text("col1,col2\nval1,val2", encoding="utf-8-sig")

        issues = check_diagnostic_csvs_in_run_dir(tmp_path)
        assert len(issues) == 0, f"All diagnostic CSVs present should pass, got: {issues}"

    def test_fails_unreadable_diagnostic_csv(self, tmp_path):
        run_dir = tmp_path / "_run_testval014"
        run_dir.mkdir()
        # Write binary garbage that pandas can't read as CSV
        (run_dir / "run_progress.csv").write_bytes(b"\x00\x01\x02\x03\xff\xfe")
        # But the other two are fine
        for name in ["run_stage_timings.csv", "run_errors.csv"]:
            (run_dir / name).write_text("col1\nval1", encoding="utf-8-sig")

        issues = check_diagnostic_csvs_in_run_dir(tmp_path)
        assert len(issues) > 0, "Unreadable diagnostic CSV must produce issues"
        assert any("run_progress.csv" in i for i in issues), \
            f"Issues should name the unreadable file, got: {issues}"

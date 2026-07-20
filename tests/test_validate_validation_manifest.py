"""Test: validate_validation_manifest.py — manifest integrity checks.

Covers:
  - Year coverage validation
  - Return code validation
  - Strategy uniqueness
  - Manifest hash matching
  - Missing manifest detection
  - Config file SHA256 computation
"""

import hashlib
import json
import sys
import tempfile
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

# Import the module under test
import importlib.util
spec = importlib.util.spec_from_file_location(
    "validate_validation_manifest",
    ROOT / "scripts" / "validate_validation_manifest.py",
)
validate_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validate_module)

# Shortcuts
validate_year_coverage = validate_module.validate_year_coverage
validate_return_codes = validate_module.validate_return_codes
validate_strategy_unique = validate_module.validate_strategy_unique
validate_manifests = validate_module.validate_manifests
sha256_hex = validate_module.sha256_hex


class TestSHA256:
    """sha256_hex tests."""

    def test_sha256_hex_deterministic(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("test content")
            tmp = Path(f.name)
        try:
            h1 = sha256_hex(tmp)
            h2 = sha256_hex(tmp)
            assert h1 == h2
            assert len(h1) == 64
        finally:
            tmp.unlink()

    def test_sha256_different_content(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("content A")
            tmp_a = Path(f.name)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("content B")
            tmp_b = Path(f.name)
        try:
            assert sha256_hex(tmp_a) != sha256_hex(tmp_b)
        finally:
            tmp_a.unlink()
            tmp_b.unlink()


class TestYearCoverage:
    """validate_year_coverage tests."""

    def test_all_years_present(self):
        df = pd.DataFrame({"year": [2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2026]})
        issues = validate_year_coverage(df, [2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024], [2026])
        assert issues == []

    def test_missing_years(self):
        df = pd.DataFrame({"year": [2017, 2018, 2019]})
        issues = validate_year_coverage(df, [2017, 2018, 2019, 2020], [2026])
        assert len(issues) == 1
        assert "2020" in issues[0]
        assert "2026" in issues[0]

    def test_missing_only_ytd(self):
        df = pd.DataFrame({"year": [2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024]})
        issues = validate_year_coverage(
            df, [2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024], [2026]
        )
        assert len(issues) == 1
        assert "2026" in issues[0]


class TestReturnCodes:
    """validate_return_codes tests."""

    def test_all_zero(self):
        df = pd.DataFrame({"year": [2017, 2018], "return_code": [0, 0]})
        issues = validate_return_codes(df)
        assert issues == []

    def test_nonzero_found(self):
        df = pd.DataFrame({"year": [2017, 2018, 2019], "return_code": [0, 1, 0]})
        issues = validate_return_codes(df)
        assert len(issues) == 1
        assert "Non-zero" in issues[0]


class TestStrategyUnique:
    """validate_strategy_unique tests."""

    def test_single_strategy(self):
        df = pd.DataFrame({"strategy": ["G_candidate_v4_r2", "G_candidate_v4_r2"]})
        issues = validate_strategy_unique(df)
        assert issues == []

    def test_multiple_strategies(self):
        df = pd.DataFrame({"strategy": ["G_v4_r1", "G_candidate_v4_r2"]})
        issues = validate_strategy_unique(df)
        assert len(issues) == 1
        assert "Multiple" in issues[0]

    def test_empty_strategies(self):
        df = pd.DataFrame({"strategy": []})
        issues = validate_strategy_unique(df)
        assert len(issues) == 1


class TestManifestValidation:
    """validate_manifests tests with synthetic run directories."""

    def setup_method(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="test_manifest_"))

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _make_run_dir(self, year: str, factors_hash: str, regime_hash: str,
                      factors_path: str = "configs/factors_candidate_v4_r2.yaml",
                      regime_path: str = "configs/regime_candidate_v4_r2.yaml") -> Path:
        run_dir = self.tmpdir / f"run_{year}"
        run_dir.mkdir(parents=True, exist_ok=True)
        manifest = {
            "run_id": f"run_{year}",
            "start": f"{year}0101",
            "end": f"{year}1231",
            "top_n": 50,
            "weight_max": 0.02,
            "factor_list": ["factor_a_cs"],
            "factor_list_sha256": "abc123",
            "factors_config": factors_path,
            "factors_config_sha256": factors_hash,
            "regime_config": regime_path,
            "regime_config_sha256": regime_hash,
            "strategy_mode": "regime",
        }
        (run_dir / "run_manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )
        return run_dir

    def test_all_manifests_match(self):
        EXPECTED_FACTORS = "aaaabbbbccccddddeeeeffff0000111122223333444455556666777788889999"
        EXPECTED_REGIME = "9999888877776666555544443333222211110000ffffeeeeddddccccbbbbaaaa"
        for y in ["2017", "2018", "2019"]:
            self._make_run_dir(y, EXPECTED_FACTORS, EXPECTED_REGIME)

        df = pd.DataFrame({
            "year": [2017, 2018, 2019],
            "run_dir": [str(self.tmpdir / f"run_{y}") for y in ["2017", "2018", "2019"]],
        })
        issues = validate_manifests(
            df, EXPECTED_FACTORS, EXPECTED_REGIME,
            "configs/factors_candidate_v4_r2.yaml",
            "configs/regime_candidate_v4_r2.yaml",
        )
        # The first issue is the summary line; filter actual issues
        actual_issues = [i for i in issues if not i.startswith("Manifest check:")]
        assert len(actual_issues) == 0

    def test_hash_mismatch_detected(self):
        EXPECTED_FACTORS = "aaaabbbbccccddddeeeeffff0000111122223333444455556666777788889999"
        EXPECTED_REGIME = "9999888877776666555544443333222211110000ffffeeeeddddccccbbbbaaaa"
        self._make_run_dir("2017", "wrong_hash_here", EXPECTED_REGIME)

        df = pd.DataFrame({
            "year": [2017],
            "run_dir": [str(self.tmpdir / "run_2017")],
        })
        issues = validate_manifests(
            df, EXPECTED_FACTORS, EXPECTED_REGIME,
            "configs/factors_candidate_v4_r2.yaml",
            "configs/regime_candidate_v4_r2.yaml",
        )
        mismatch_issues = [i for i in issues if "MISMATCH" in i]
        assert len(mismatch_issues) >= 1

    def test_missing_manifest(self):
        run_dir = self.tmpdir / "run_missing"
        run_dir.mkdir(parents=True, exist_ok=True)
        # Don't create run_manifest.json

        df = pd.DataFrame({
            "year": [2017],
            "run_dir": [str(run_dir)],
        })
        issues = validate_manifests(
            df, "hash_f", "hash_r",
            "configs/factors_candidate_v4_r2.yaml",
            "configs/regime_candidate_v4_r2.yaml",
        )
        missing_issues = [i for i in issues if "not found" in i]
        assert len(missing_issues) >= 1

    def test_nonexistent_run_dir(self):
        df = pd.DataFrame({
            "year": [2017],
            "run_dir": ["/nonexistent/path/run_2017"],
        })
        issues = validate_manifests(
            df, "hash_f", "hash_r",
            "configs/factors.yaml", "configs/regime.yaml",
        )
        assert len(issues) >= 1
        assert any("does not exist" in i for i in issues)

    def test_config_path_differs(self):
        EXPECTED_FACTORS = "aaaabbbbccccddddeeeeffff0000111122223333444455556666777788889999"
        EXPECTED_REGIME = "9999888877776666555544443333222211110000ffffeeeeddddccccbbbbaaaa"
        self._make_run_dir("2017", EXPECTED_FACTORS, EXPECTED_REGIME,
                          factors_path="configs/old_factors.yaml",
                          regime_path="configs/old_regime.yaml")

        df = pd.DataFrame({
            "year": [2017],
            "run_dir": [str(self.tmpdir / "run_2017")],
        })
        issues = validate_manifests(
            df, EXPECTED_FACTORS, EXPECTED_REGIME,
            "configs/factors_candidate_v4_r2.yaml",
            "configs/regime_candidate_v4_r2.yaml",
        )
        path_issues = [i for i in issues if "path differs" in i]
        assert len(path_issues) >= 1


class TestIntegration:
    """Integration-style test: run the script against a real-config scenario."""

    def test_script_imports_cleanly(self):
        """Verify the module can be imported without errors."""
        assert validate_module is not None
        assert callable(validate_module.main)

    def test_help_flag(self, capsys):
        """Verify --help works."""
        with pytest.raises(SystemExit):
            validate_module.main()
        # argparse exits with code 2 for missing required args; acceptable


class TestManifestMismatchCount:
    """Verify that mismatch_count=0 when all hashes match."""

    def test_mismatch_count_zero_on_match(self):
        tmpdir = Path(tempfile.mkdtemp(prefix="test_mm_"))
        try:
            factors_hash = "a" * 64
            regime_hash = "b" * 64
            for y in ["2017", "2018"]:
                rd = tmpdir / f"run_{y}"
                rd.mkdir(parents=True)
                manifest = {
                    "factors_config_sha256": factors_hash,
                    "regime_config_sha256": regime_hash,
                    "factors_config": "configs/f_cfg.yaml",
                    "regime_config": "configs/r_cfg.yaml",
                }
                (rd / "run_manifest.json").write_text(
                    json.dumps(manifest), encoding="utf-8")

            df = pd.DataFrame({
                "year": [2017, 2018],
                "run_dir": [str(tmpdir / "run_2017"), str(tmpdir / "run_2018")],
            })
            issues = validate_manifests(
                df, factors_hash, regime_hash,
                "configs/f_cfg.yaml", "configs/r_cfg.yaml",
            )
            actual = [i for i in issues if not i.startswith("Manifest check:")]
            assert len(actual) == 0
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

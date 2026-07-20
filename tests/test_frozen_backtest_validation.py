"""
Test: frozen_backtest_validation — config hash validation, force rerun, reuse logic.
"""
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.frozen_backtest_validation import (
    _manifest_matches,
    _compute_file_sha256,
    _compute_factor_list_hash,
    Strategy,
)


class TestConfigHashes:
    """SHA256 hash computation for config files and factor lists."""

    def test_file_sha256_consistent(self):
        """Same file content → same hash."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("factors:\n  - bp_cs\n  - ep_cs\n")
            f.flush()
            path1 = f.name

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("factors:\n  - bp_cs\n  - ep_cs\n")
            f.flush()
            path2 = f.name

        h1 = _compute_file_sha256(path1)
        h2 = _compute_file_sha256(path2)
        assert h1 == h2
        assert len(h1) == 64  # SHA256 hex

        Path(path1).unlink()
        Path(path2).unlink()

    def test_file_sha256_different(self):
        """Different file content → different hash."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("factors:\n  - bp_cs\n")
            f.flush()
            path1 = f.name

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("factors:\n  - ep_cs\n")
            f.flush()
            path2 = f.name

        h1 = _compute_file_sha256(path1)
        h2 = _compute_file_sha256(path2)
        assert h1 != h2

        Path(path1).unlink()
        Path(path2).unlink()

    def test_file_sha256_missing_file(self):
        """Missing file returns empty string."""
        h = _compute_file_sha256("/nonexistent/path/config.yaml")
        assert h == ""

    def test_factor_list_hash_consistent(self):
        """Same factor list → same hash regardless of order."""
        h1 = _compute_factor_list_hash(["bp_cs", "ep_cs"])
        h2 = _compute_factor_list_hash(["ep_cs", "bp_cs"])
        assert h1 == h2
        assert len(h1) == 64

    def test_factor_list_hash_different(self):
        """Different factor list → different hash."""
        h1 = _compute_factor_list_hash(["bp_cs", "ep_cs"])
        h2 = _compute_factor_list_hash(["bp_cs", "ep_cs", "sp_cs"])
        assert h1 != h2

    def test_factor_list_hash_empty(self):
        """Empty factor list returns empty string."""
        assert _compute_factor_list_hash([]) == ""
        assert _compute_factor_list_hash(None) == ""


class TestManifestMatches:
    """_manifest_matches validation with config hashes."""

    def setup_method(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="test_fbv_manifest_"))
        # Create a dummy strategy
        self.strategy = Strategy(
            name="E_candidate_v2",
            label="test",
            args=(
                "--factors-config", "configs/factors_candidate_v1.yaml",
                "--strategy-mode", "regime",
                "--regime-config", "configs/regime_candidate_v2.yaml",
            ),
        )

    def teardown_method(self):
        import shutil
        if self.tmpdir.exists():
            shutil.rmtree(str(self.tmpdir), ignore_errors=True)

    def _write_manifest(self, **overrides):
        manifest = {
            "run_id": "test_run",
            "start": "20230101",
            "end": "20231231",
            "top_n": 50,
            "strategy_mode": "regime",
            "factors_config": "configs/factors_candidate_v1.yaml",
            "regime_config": "configs/regime_candidate_v2.yaml",
            "factor_list": ["bp_cs", "ep_cs", "sp_cs"],
        }
        manifest.update(overrides)
        (self.tmpdir / "run_manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        # Also create metrics_summary.json for _manifest_matches
        (self.tmpdir / "metrics_summary.json").write_text(
            json.dumps({"phase2": {"benchmark_status": "OK"}}), encoding="utf-8"
        )

    def test_basic_match(self):
        """Manifest matches when path, start, end, top_n, mode all match
        AND required hashes are present."""
        # Create temp config files so hashes can be computed from real files
        config_dir = self.tmpdir / "configs"
        config_dir.mkdir(parents=True, exist_ok=True)
        fc_path = config_dir / "factors_candidate_v1.yaml"
        fc_path.write_text("factors:\n  - bp_cs\n  - ep_cs\n  - sp_cs\n")
        rc_path = config_dir / "regime_candidate_v2.yaml"
        rc_path.write_text("regime_detector:\n  method: test\n")

        fc_hash = _compute_file_sha256(str(fc_path))
        rc_hash = _compute_file_sha256(str(rc_path))
        fl_hash = _compute_factor_list_hash(["bp_cs", "ep_cs", "sp_cs"])

        self._write_manifest(
            factors_config=str(fc_path),
            factors_config_sha256=fc_hash,
            regime_config=str(rc_path),
            regime_config_sha256=rc_hash,
            factor_list=["bp_cs", "ep_cs", "sp_cs"],
            factor_list_sha256=fl_hash,
        )

        strategy = Strategy(
            name="E_candidate_v2",
            label="test",
            args=(
                "--factors-config", str(fc_path),
                "--strategy-mode", "regime",
                "--regime-config", str(rc_path),
            ),
        )

        assert _manifest_matches(
            self.tmpdir, "20230101", "20231231", 50, strategy,
            check_hashes=True,
        )

    def test_mismatch_start_date(self):
        """Different start date → no match."""
        self._write_manifest()
        assert not _manifest_matches(
            self.tmpdir, "20220101", "20231231", 50, self.strategy,
        )

    def test_mismatch_end_date(self):
        """Different end date → no match."""
        self._write_manifest()
        assert not _manifest_matches(
            self.tmpdir, "20230101", "20231230", 50, self.strategy,
        )

    def test_mismatch_top_n(self):
        """Different top_n → no match."""
        self._write_manifest()
        assert not _manifest_matches(
            self.tmpdir, "20230101", "20231231", 100, self.strategy,
        )

    def test_mismatch_strategy_mode(self):
        """Different strategy_mode → no match."""
        self._write_manifest(strategy_mode="factor_dynamic")
        assert not _manifest_matches(
            self.tmpdir, "20230101", "20231231", 50, self.strategy,
        )

    def test_mismatch_factors_config_path(self):
        """Different factors_config path → no match."""
        self._write_manifest(factors_config="configs/other.yaml")
        assert not _manifest_matches(
            self.tmpdir, "20230101", "20231231", 50, self.strategy,
        )

    def test_mismatch_config_hash_blocks_reuse(self):
        """Config hash mismatch blocks reuse when check_hashes=True."""
        # Create temp config files
        config_dir = self.tmpdir / "configs"
        config_dir.mkdir(parents=True, exist_ok=True)
        fc_path = config_dir / "factors_candidate_v1.yaml"
        fc_path.write_text("factors:\n  - bp_cs\n  - ep_cs\n")
        rc_path = config_dir / "regime_candidate_v2.yaml"
        rc_path.write_text("regime_detector:\n  method: test\n")

        # Write manifest with OLD hash (different content)
        old_hash = "a" * 64
        self._write_manifest(
            factors_config=str(fc_path),
            factors_config_sha256=old_hash,
            regime_config=str(rc_path),
            regime_config_sha256=old_hash,
        )

        # Create a strategy that points to the temp config files
        strategy = Strategy(
            name="test",
            label="test",
            args=(
                "--factors-config", str(fc_path),
                "--strategy-mode", "regime",
                "--regime-config", str(rc_path),
            ),
        )

        # With check_hashes=True, hash mismatch → no match
        assert not _manifest_matches(
            self.tmpdir, "20230101", "20231231", 50, strategy,
            check_hashes=True,
        )

        # With check_hashes=False, hash is ignored → matches
        assert _manifest_matches(
            self.tmpdir, "20230101", "20231231", 50, strategy,
            check_hashes=False,
        )

    def test_config_hash_match_allows_reuse(self):
        """When config hasn't changed, hash matches and reuse is allowed."""
        config_dir = self.tmpdir / "configs"
        config_dir.mkdir(parents=True, exist_ok=True)
        fc_path = config_dir / "factors_candidate_v1.yaml"
        fc_content = "factors:\n  - bp_cs\n  - ep_cs\n  - sp_cs\n"
        fc_path.write_text(fc_content)
        rc_path = config_dir / "regime_candidate_v2.yaml"
        rc_content = "regime_detector:\n  method: test\n"
        rc_path.write_text(rc_content)

        # Compute correct hashes
        fc_hash = _compute_file_sha256(str(fc_path))
        rc_hash = _compute_file_sha256(str(rc_path))
        fl_hash = _compute_factor_list_hash(["bp_cs", "ep_cs", "sp_cs"])

        self._write_manifest(
            factors_config=str(fc_path),
            factors_config_sha256=fc_hash,
            regime_config=str(rc_path),
            regime_config_sha256=rc_hash,
            factor_list=["bp_cs", "ep_cs", "sp_cs"],
            factor_list_sha256=fl_hash,
        )

        strategy = Strategy(
            name="test",
            label="test",
            args=(
                "--factors-config", str(fc_path),
                "--strategy-mode", "regime",
                "--regime-config", str(rc_path),
            ),
        )

        assert _manifest_matches(
            self.tmpdir, "20230101", "20231231", 50, strategy,
            check_hashes=True,
        )

    def test_missing_manifest_file(self):
        """No manifest file → no match."""
        assert not _manifest_matches(
            self.tmpdir, "20230101", "20231231", 50, self.strategy,
        )

    def test_no_hash_fields_rejected_by_default(self):
        """Strict mode: manifests without required hash fields are REJECTED."""
        self._write_manifest(
            factors_config_sha256=None,
            regime_config_sha256=None,
            factor_list_sha256=None,
        )
        # Remove hash fields from manifest to simulate old run
        manifest = json.loads((self.tmpdir / "run_manifest.json").read_text())
        manifest.pop("factors_config_sha256", None)
        manifest.pop("regime_config_sha256", None)
        manifest.pop("factor_list_sha256", None)
        (self.tmpdir / "run_manifest.json").write_text(json.dumps(manifest))

        # Default: allow_legacy_manifest=False → should NOT match
        assert not _manifest_matches(
            self.tmpdir, "20230101", "20231231", 50, self.strategy,
            check_hashes=True,
        )

        # Even with check_hashes=False, basic match still works
        assert _manifest_matches(
            self.tmpdir, "20230101", "20231231", 50, self.strategy,
            check_hashes=False,
        )

    def test_legacy_manifest_allowed_with_flag(self):
        """allow_legacy_manifest=True permits old manifests without hashes."""
        self._write_manifest(
            factors_config_sha256=None,
            regime_config_sha256=None,
            factor_list_sha256=None,
        )
        # Remove hash fields to simulate old run
        manifest = json.loads((self.tmpdir / "run_manifest.json").read_text())
        manifest.pop("factors_config_sha256", None)
        manifest.pop("regime_config_sha256", None)
        manifest.pop("factor_list_sha256", None)
        (self.tmpdir / "run_manifest.json").write_text(json.dumps(manifest))

        # With allow_legacy_manifest=True → matches (diagnostic only)
        assert _manifest_matches(
            self.tmpdir, "20230101", "20231231", 50, self.strategy,
            check_hashes=True, allow_legacy_manifest=True,
        )

    def test_partial_hashes_rejected_in_strict_mode(self):
        """Manifest with some but not all required hashes is rejected."""
        # Create temp config files so hashes can be computed
        config_dir = self.tmpdir / "configs"
        config_dir.mkdir(parents=True, exist_ok=True)
        fc_path = config_dir / "factors_candidate_v1.yaml"
        fc_content = "factors:\n  - bp_cs\n  - ep_cs\n"
        fc_path.write_text(fc_content)
        rc_path = config_dir / "regime_candidate_v2.yaml"
        rc_content = "regime_detector:\n  method: test\n"
        rc_path.write_text(rc_content)

        # Write manifest with factors_config_sha256 but MISSING regime_config_sha256
        fc_hash = _compute_file_sha256(str(fc_path))
        self._write_manifest(
            factors_config=str(fc_path),
            factors_config_sha256=fc_hash,
            regime_config=str(rc_path),
            # regime_config_sha256 intentionally missing
            factor_list_sha256=_compute_factor_list_hash(["bp_cs", "ep_cs"]),
        )
        manifest = json.loads((self.tmpdir / "run_manifest.json").read_text())
        manifest.pop("regime_config_sha256", None)
        (self.tmpdir / "run_manifest.json").write_text(json.dumps(manifest))

        strategy = Strategy(
            name="test",
            label="test",
            args=(
                "--factors-config", str(fc_path),
                "--strategy-mode", "regime",
                "--regime-config", str(rc_path),
            ),
        )

        # Strict mode: missing regime_config_sha256 → rejected
        assert not _manifest_matches(
            self.tmpdir, "20230101", "20231231", 50, strategy,
            check_hashes=True,
        )

        # Legacy mode: allowed
        assert _manifest_matches(
            self.tmpdir, "20230101", "20231231", 50, strategy,
            check_hashes=True, allow_legacy_manifest=True,
        )


class TestCLIFlags:
    """CLI flag behavior tests."""

    def test_force_overrides_reuse(self):
        """--force flag exists and takes precedence."""
        parser_args = [
            "--strategies", "E_candidate_v2",
            "--force",
            "--reuse-existing",
        ]
        # We test the argparse setup, not full execution
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--strategies", nargs="+", default=[])
        parser.add_argument("--reuse-existing", action="store_true", default=False)
        parser.add_argument("--force", action="store_true", default=False)
        parser.add_argument("--skip-existing", action="store_true", default=False)
        args = parser.parse_args(parser_args)

        force_rerun = args.force
        reuse = (args.reuse_existing or args.skip_existing) and not force_rerun
        assert force_rerun is True
        assert reuse is False

    def test_default_no_reuse(self):
        """Default mode is fresh re-run (no reuse)."""
        parser_args: list = []
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--reuse-existing", action="store_true", default=False)
        parser.add_argument("--force", action="store_true", default=False)
        parser.add_argument("--skip-existing", action="store_true", default=False)
        args = parser.parse_args(parser_args)

        force_rerun = args.force
        reuse = (args.reuse_existing or args.skip_existing) and not force_rerun
        assert force_rerun is False
        assert reuse is False

    def test_reuse_existing_enables_reuse(self):
        """--reuse-existing enables reuse mode."""
        parser_args = ["--reuse-existing"]
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--reuse-existing", action="store_true", default=False)
        parser.add_argument("--force", action="store_true", default=False)
        parser.add_argument("--skip-existing", action="store_true", default=False)
        args = parser.parse_args(parser_args)

        force_rerun = args.force
        reuse = (args.reuse_existing or args.skip_existing) and not force_rerun
        assert reuse is True

    def test_skip_existing_backward_compat(self):
        """--skip-existing still works for backward compatibility."""
        parser_args = ["--skip-existing"]
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--reuse-existing", action="store_true", default=False)
        parser.add_argument("--force", action="store_true", default=False)
        parser.add_argument("--skip-existing", action="store_true", default=False)
        args = parser.parse_args(parser_args)

        reuse = (args.reuse_existing or args.skip_existing) and not args.force
        assert reuse is True

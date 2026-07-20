"""
Test: repair_adj_factor — dedup, conflict detection, schema unification, atomic write.
"""
import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

# Import the module under test
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.repair_adj_factor import (
    _normalize_schema,
    _find_duplicates,
    _scan_partition_files,
    ADJ_FACTOR_SCHEMA,
)


class TestNormalizeSchema:
    """Schema normalization tests."""

    def test_normalize_basic_types(self):
        """ts_code → string, trade_date → int32, adj_factor → float64."""
        df = pd.DataFrame({
            "ts_code": [1, 2, 3],  # int codes
            "trade_date": ["20240115", "20240116", "20240117"],
            "adj_factor": ["1.0", "0.95", "1.05"],
        })
        result = _normalize_schema(df)
        assert result["ts_code"].dtype == object  # string in pandas
        assert result["trade_date"].dtype == "int32"
        assert result["adj_factor"].dtype == "float64"

    def test_drop_nulls_in_keys(self):
        """Rows with nulls in key columns are dropped."""
        df = pd.DataFrame({
            "ts_code": ["000001.SZ", None, "000002.SZ"],
            "trade_date": [20240115, 20240116, None],
            "adj_factor": [1.0, 0.95, np.nan],
        })
        result = _normalize_schema(df)
        assert len(result) == 1
        assert result.iloc[0]["ts_code"] == "000001.SZ"

    def test_numeric_trade_date_coerced(self):
        """Non-numeric trade_date values become NaN then dropped."""
        df = pd.DataFrame({
            "ts_code": ["000001.SZ", "000002.SZ"],
            "trade_date": ["abc", "20240116"],
            "adj_factor": [1.0, 0.95],
        })
        result = _normalize_schema(df)
        assert len(result) == 1
        assert result.iloc[0]["trade_date"] == 20240116


class TestFindDuplicates:
    """Duplicate detection tests."""

    def setup_method(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="test_repair_adj_"))

    def teardown_method(self):
        import shutil
        if self.tmpdir.exists():
            shutil.rmtree(str(self.tmpdir), ignore_errors=True)

    def _write_parquet(self, name, data):
        """Write a parquet file with the given data to tmpdir."""
        df = pd.DataFrame(data)
        # Normalize schema
        df["ts_code"] = df["ts_code"].astype(str)
        df["trade_date"] = df["trade_date"].astype("int32")
        df["adj_factor"] = df["adj_factor"].astype("float64")
        table = pa.Table.from_pandas(df)
        path = self.tmpdir / name
        pq.write_table(table, str(path))
        return path

    def test_no_duplicates(self):
        """Clean partition returns no duplicates."""
        self._write_parquet("data.parquet", {
            "ts_code": ["000001.SZ", "000002.SZ"],
            "trade_date": [20240115, 20240116],
            "adj_factor": [1.0, 0.95],
        })
        info = _find_duplicates(self.tmpdir)
        assert info["dup_count"] == 0
        assert info["total_rows"] == 2
        assert info["unique_keys"] == 2

    def test_duplicates_same_value(self):
        """Same key, same value → detected as duplicate, no conflict."""
        self._write_parquet("data.parquet", {
            "ts_code": ["000001.SZ", "000001.SZ", "000002.SZ"],
            "trade_date": [20240115, 20240115, 20240116],
            "adj_factor": [1.0, 1.0, 0.95],
        })
        info = _find_duplicates(self.tmpdir)
        assert info["dup_count"] == 1  # one key duplicated
        assert len(info["conflict_keys"]) == 0  # same value, no conflict
        assert info["total_rows"] == 3
        assert info["unique_keys"] == 2

    def test_duplicates_different_value_conflict(self):
        """Same key, different adj_factor → conflict detected."""
        self._write_parquet("data.parquet", {
            "ts_code": ["000001.SZ", "000001.SZ"],
            "trade_date": [20240115, 20240115],
            "adj_factor": [1.0, 1.5],  # 50% difference
        })
        info = _find_duplicates(self.tmpdir)
        assert info["dup_count"] == 1
        assert len(info["conflict_keys"]) == 1
        assert info["conflict_keys"][0]["ts_code"] == "000001.SZ"
        assert info["conflict_keys"][0]["trade_date"] == 20240115
        assert 1.0 in info["conflict_keys"][0]["values"]
        assert 1.5 in info["conflict_keys"][0]["values"]

    def test_duplicates_across_multiple_files(self):
        """Duplicates spread across multiple parquet files."""
        self._write_parquet("frag_1.parquet", {
            "ts_code": ["000001.SZ", "000002.SZ"],
            "trade_date": [20240115, 20240115],
            "adj_factor": [1.0, 0.95],
        })
        self._write_parquet("frag_2.parquet", {
            "ts_code": ["000001.SZ", "000003.SZ"],
            "trade_date": [20240115, 20240116],
            "adj_factor": [1.0, 1.05],
        })
        info = _find_duplicates(self.tmpdir)
        assert info["dup_count"] == 1  # 000001.SZ @ 20240115 appears twice
        assert len(info["dup_sources"]) >= 2  # from both files
        assert len(info["conflict_keys"]) == 0  # same value

    def test_small_numeric_difference_not_conflict(self):
        """Near-identical adj_factor values (floating point) not flagged as conflict."""
        self._write_parquet("data.parquet", {
            "ts_code": ["000001.SZ", "000001.SZ"],
            "trade_date": [20240115, 20240115],
            "adj_factor": [1.0, 1.000000001],  # extremely close
        })
        info = _find_duplicates(self.tmpdir)
        assert len(info["conflict_keys"]) == 0


class TestScanPartitionFiles:
    """Partition file scanning tests."""

    def setup_method(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="test_scan_adj_"))

    def teardown_method(self):
        import shutil
        if self.tmpdir.exists():
            shutil.rmtree(str(self.tmpdir), ignore_errors=True)

    def test_empty_partition(self):
        """Non-existent path returns empty list."""
        result = _scan_partition_files(self.tmpdir / "nonexistent")
        assert result == []

    def test_reads_all_parquet_files(self):
        """All .parquet files in a directory are read."""
        for i in range(3):
            df = pd.DataFrame({
                "ts_code": [f"{i:06d}.SZ"],
                "trade_date": [20240115],
                "adj_factor": [1.0],
            })
            table = pa.Table.from_pandas(df)
            pq.write_table(table, str(self.tmpdir / f"part_{i}.parquet"))
        result = _scan_partition_files(self.tmpdir)
        assert len(result) == 3

    def test_skips_bad_files(self):
        """Unreadable files are skipped gracefully."""
        (self.tmpdir / "bad.parquet").write_text("not a parquet file")
        df = pd.DataFrame({
            "ts_code": ["000001.SZ"],
            "trade_date": [20240115],
            "adj_factor": [1.0],
        })
        table = pa.Table.from_pandas(df)
        pq.write_table(table, str(self.tmpdir / "good.parquet"))
        result = _scan_partition_files(self.tmpdir)
        assert len(result) == 1


class TestADJFactorSchema:
    """Unified schema validation."""

    def test_schema_fields(self):
        """Schema has all required fields with correct types."""
        fields = {f.name: f.type for f in ADJ_FACTOR_SCHEMA}
        assert fields["ts_code"] == pa.string()
        assert fields["trade_date"] == pa.int32()
        assert fields["adj_factor"] == pa.float64()
        assert fields["year"] == pa.int32()


class TestDedupPartition:
    """Integration tests for dedup_partition."""

    def setup_method(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="test_repair_dedup_"))
        # Create a mock partition structure
        self.part_path = self.tmpdir / "year=2024"
        self.part_path.mkdir(parents=True, exist_ok=True)

    def teardown_method(self):
        import shutil
        if self.tmpdir.exists():
            shutil.rmtree(str(self.tmpdir), ignore_errors=True)

    def _write_test_data(self, data_dict):
        df = pd.DataFrame(data_dict)
        df["ts_code"] = df["ts_code"].astype(str)
        df["trade_date"] = df["trade_date"].astype("int32")
        df["adj_factor"] = df["adj_factor"].astype("float64")
        table = pa.Table.from_pandas(df)
        pq.write_table(table, str(self.part_path / "data.parquet"))

    def test_dry_run_no_modification(self):
        """--dry-run reports duplicates but doesn't modify files."""
        self._write_test_data({
            "ts_code": ["000001.SZ", "000001.SZ", "000002.SZ"],
            "trade_date": [20240115, 20240115, 20240116],
            "adj_factor": [1.0, 1.0, 0.95],
        })
        from scripts.repair_adj_factor import dedup_partition
        n = dedup_partition(self.part_path, dry_run=True)
        assert n == 1  # reported removal
        # File should still exist unchanged
        assert (self.part_path / "data.parquet").exists()

    def test_conflict_refuses_to_fix(self):
        """Conflicting adj_factor values cause SystemExit (in non-dry-run)."""
        self._write_test_data({
            "ts_code": ["000001.SZ", "000001.SZ"],
            "trade_date": [20240115, 20240115],
            "adj_factor": [1.0, 1.5],
        })
        from scripts.repair_adj_factor import dedup_partition
        with pytest.raises(SystemExit):
            dedup_partition(self.part_path, dry_run=False)

    def test_years_filter_respected(self):
        """--years filter skips non-targeted years."""
        self._write_test_data({
            "ts_code": ["000001.SZ", "000001.SZ"],
            "trade_date": [20240115, 20240115],
            "adj_factor": [1.0, 1.0],
        })
        from scripts.repair_adj_factor import dedup_partition
        n = dedup_partition(self.part_path, dry_run=True, years_filter={2023})
        assert n == 0  # 2024 not in filter, skipped

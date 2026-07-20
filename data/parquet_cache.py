"""Parquet cache manager for hive-partitioned storage."""
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
import pandas as pd
import pyarrow.dataset as ds
import pyarrow.parquet as pq
import pyarrow as pa

logger = logging.getLogger(__name__)

class ParquetCache:
    """Manages hive-partitioned parquet cache with incremental updates."""

    def __init__(self, base_path: str = "data/parquet"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _partition_path(self, table_name: str, partition: Dict[str, str] = None) -> Path:
        """Build path for a partitioned table."""
        p = self.base_path / table_name
        if partition:
            for k, v in partition.items():
                p = p / f"{k}={v}"
        return p

    def exists(self, table_name: str, partition: Dict[str, str] = None) -> bool:
        """Check if cached data exists for table/partition."""
        p = self._partition_path(table_name, partition)
        return p.exists() and any(p.glob("*.parquet"))

    def covers_range(self, table_name: str, start_date: str, end_date: str,
                     date_col: str = "trade_date") -> bool:
        """
        Check if cached data covers the full requested date range.

        Uses PyArrow compute functions for min/max — NEVER materializes
        the full date column into a Python list.
        """
        p = self._partition_path(table_name)
        if not p.exists():
            return False
        try:
            import pyarrow.compute as pc
            dataset_ = ds.dataset(str(p), format="parquet", partitioning="hive")

            # Use partition-level date filtering when possible
            # Hive partitioning by year/month lets us skip most files
            date_col_scalar = ds.field(date_col)

            # Batch-scan compute min/max without loading full column
            scanner = dataset_.scanner(columns=[date_col])
            # Use a small batch reader to compute min/max incrementally
            batches = scanner.to_batches()
            cached_min = None
            cached_max = None
            for batch in batches:
                arr = batch.column(date_col)
                if len(arr) == 0:
                    continue
                batch_min = pc.min(arr).as_py()
                batch_max = pc.max(arr).as_py()
                if cached_min is None or batch_min < cached_min:
                    cached_min = batch_min
                if cached_max is None or batch_max > cached_max:
                    cached_max = batch_max

            if cached_min is None or cached_max is None:
                return False
            return cached_min <= int(start_date) and cached_max >= int(end_date)
        except Exception:
            return False

    def read(self, table_name: str, columns: List[str] = None,
             filters: Any = None, partition: Dict[str, str] = None) -> pd.DataFrame:
        """
        Read from parquet cache with predicate pushdown.

        Uses PyArrow Dataset to push column selection and row filters
        to the parquet layer — never loads full table into memory.
        """
        p = self._partition_path(table_name, partition)
        if not p.exists():
            return pd.DataFrame()

        try:
            dataset = ds.dataset(str(p), format="parquet", partitioning="hive")
            # Build filter expression if provided as list of tuples
            filter_expr = None
            if filters:
                filter_expr = self._build_filter(filters)
            table = dataset.to_table(columns=columns, filter=filter_expr)
            return table.to_pandas()
        except Exception:
            # Fallback: read individual parquet files
            return self._read_fallback(p, columns, filters)

    def _read_fallback(self, path: Path, columns: List[str] = None,
                       filters: Any = None) -> pd.DataFrame:
        """Fallback read using individual parquet files."""
        files = list(path.rglob("*.parquet"))
        if not files:
            return pd.DataFrame()
        dfs = []
        for f in files:
            try:
                chunk = pq.read_table(f, columns=columns).to_pandas()
                dfs.append(chunk)
            except Exception:
                continue
        if not dfs:
            return pd.DataFrame()
        result = pd.concat(dfs, ignore_index=True)
        if filters:
            result = self._apply_filters_in_memory(result, filters)
        return result

    def write(self, df: pd.DataFrame, table_name: str,
              partition_cols: List[str] = None,
              row_group_size: int = 200000,
              compression: str = "zstd",
              compression_level: int = 3,
              replace_partitions: bool = False) -> None:
        """Write DataFrame to hive-partitioned parquet.

        Parameters
        ----------
        replace_partitions : bool
            If True, delete matching partition directories before writing.
            Prevents duplicate rows when re-writing the same logical partition
            (e.g., the same year+month) with different data.
        """
        if df.empty:
            return

        out_path = self.base_path / table_name

        if replace_partitions and partition_cols:
            import shutil
            for keys, _ in df.groupby(partition_cols):
                if not isinstance(keys, tuple):
                    keys = (keys,)
                part_dir = out_path
                for c, v in zip(partition_cols, keys):
                    part_dir = part_dir / f"{c}={v}"
                if part_dir.exists():
                    shutil.rmtree(str(part_dir))
                    logger.debug(f"ParquetCache: replaced partition {part_dir}")

        table = pa.Table.from_pandas(df, preserve_index=False)
        pq.write_to_dataset(
            table,
            root_path=str(out_path),
            partition_cols=partition_cols or [],
            row_group_size=row_group_size,
            compression=compression,
            compression_level=compression_level,
            existing_data_behavior='overwrite_or_ignore',
        )

    def last_date(self, table_name: str, date_col: str = "trade_date") -> Optional[int]:
        """Get the most recent date in cached data."""
        p = self.base_path / table_name
        if not p.exists():
            return None
        files = list(p.rglob("*.parquet"))
        if not files:
            return None
        max_date = None
        for f in files:
            try:
                tbl = pq.read_table(f, columns=[date_col])
                dates = tbl.column(date_col).to_pylist()
                file_max = max(d for d in dates if d is not None)
                if max_date is None or file_max > max_date:
                    max_date = file_max
            except Exception:
                continue
        return max_date

    @staticmethod
    def _build_filter(conditions: List[tuple]) -> ds.Expression:
        """Build PyArrow filter expression from list of (field, op, value) tuples."""
        expr = None
        for field, op, value in conditions:
            if op == ">=":
                e = ds.field(field) >= value
            elif op == ">":
                e = ds.field(field) > value
            elif op == "<=":
                e = ds.field(field) <= value
            elif op == "<":
                e = ds.field(field) < value
            elif op == "==":
                e = ds.field(field) == value
            elif op == "in":
                e = ds.field(field).isin(value)
            else:
                raise ValueError(f"Unsupported filter operator: {op}")
            expr = e if expr is None else expr & e
        return expr

    @staticmethod
    def _apply_filters_in_memory(df: pd.DataFrame, conditions: List[tuple]) -> pd.DataFrame:
        """Apply simple filters in pandas (fallback when pyarrow dataset fails)."""
        for field, op, value in conditions:
            if op == ">=":
                df = df[df[field] >= value]
            elif op == ">":
                df = df[df[field] > value]
            elif op == "<=":
                df = df[df[field] <= value]
            elif op == "<":
                df = df[df[field] < value]
            elif op == "==":
                df = df[df[field] == value]
            elif op == "in":
                df = df[df[field].isin(value)]
        return df


# ---------------------------------------------------------------------------
# Main Tushare client

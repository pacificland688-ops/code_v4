"""
Memory-constrained panel data access layer.

CORE RULE: panel_loader NEVER returns a full (date x stock x field) wide
DataFrame. Instead, it provides:

1. Query-based access with predicate pushdown (DuckDB / PyArrow)
2. Chunked iteration by date batches
3. Per-stock time-series slices
4. On-demand pivot for single computation windows

Architecture:
- DuckDB for cross-parquet SQL with WHERE pushdown
- PyArrow Dataset for partitioned parquet scans
- Polars optional for lazy groupby operations
- psutil for memory monitoring

All data remains in long format (date, ts_code, field_value) physically.
"""

import logging
import gc
from pathlib import Path
from typing import Optional, List, Dict, Any, Iterator, Tuple, Callable
from contextlib import contextmanager

import numpy as np
import pandas as pd
import pyarrow.dataset as ds
import pyarrow.parquet as pq
import pyarrow as pa

logger = logging.getLogger(__name__)

# Optional imports
try:
    import duckdb
    _HAS_DUCKDB = True
except ImportError:
    _HAS_DUCKDB = False
    logger.warning("duckdb not installed; falling back to PyArrow scans")

try:
    import psutil
    _HAS_PSUTIL = True
except ImportError:
    _HAS_PSUTIL = False

try:
    import polars as pl
    _HAS_POLARS = True
except ImportError:
    _HAS_POLARS = False


# ---------------------------------------------------------------------------
# Memory monitor
# ---------------------------------------------------------------------------
class MemoryMonitor:
    """Track memory usage and enforce budget."""

    def __init__(self, max_memory_gb: float = 8.0, warning_threshold_gb: float = 6.0):
        self.max_memory_gb = max_memory_gb
        self.warning_threshold_gb = warning_threshold_gb
        self._peak_gb = 0.0
        self._check_count = 0

    @property
    def current_gb(self) -> float:
        """Current RSS in GB."""
        if _HAS_PSUTIL:
            proc = psutil.Process()
            return proc.memory_info().rss / (1024 ** 3)
        return 0.0

    @property
    def peak_gb(self) -> float:
        return self._peak_gb

    def check(self, label: str = "") -> float:
        """Check current memory, update peak, warn if over threshold."""
        current = self.current_gb
        self._peak_gb = max(self._peak_gb, current)
        self._check_count += 1

        if current > self.warning_threshold_gb:
            logger.warning(
                f"[MEM:{label}] {current:.2f}GB > {self.warning_threshold_gb}GB "
                f"threshold (peak={self._peak_gb:.2f}GB)"
            )

        if current > self.max_memory_gb:
            raise MemoryError(
                f"[MEM:{label}] {current:.2f}GB exceeds budget "
                f"{self.max_memory_gb}GB — aborting"
            )

        return current

    def report(self) -> Dict[str, Any]:
        """Return memory report."""
        return {
            "current_gb": self.current_gb,
            "peak_gb": self.peak_gb,
            "budget_gb": self.max_memory_gb,
            "warning_threshold_gb": self.warning_threshold_gb,
            "checks": self._check_count,
        }


# ---------------------------------------------------------------------------
# Panel Loader
# ---------------------------------------------------------------------------
class PanelLoader:
    """
    Memory-constrained panel data access layer.

    Usage:
        loader = PanelLoader(max_memory_gb=8.0)
        loader.initialize()

        # Query-based: returns only what you ask for
        df = loader.query_prices(
            start_date="20240101", end_date="20240131",
            ts_codes=["000001.SZ", "000002.SZ"],
            fields=["adj_close", "vol"]
        )

        # Chunked iteration over dates
        for chunk in loader.iter_date_chunks(months=3):
            process_cross_section(chunk)

        # Single date pivot (small, for optimizer)
        matrix = loader.pivot_for_date("20240115", fields=["adj_close"])
    """

    def __init__(self,
                 data_path: str = "data/parquet",
                 max_memory_gb: float = 8.0,
                 stock_batch_size: int = 80,
                 date_chunk_months: int = 3,
                 use_float32: bool = True):
        self.data_path = Path(data_path)
        self.max_memory_gb = max_memory_gb
        self.stock_batch_size = stock_batch_size
        self.date_chunk_months = date_chunk_months
        self.use_float32 = use_float32

        self.monitor = MemoryMonitor(max_memory_gb=max_memory_gb)
        self._duckdb_conn = None
        self._initialized = False

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------
    def initialize(self):
        """Set up DuckDB connection and verify data paths."""
        if self._initialized:
            return

        self.data_path.mkdir(parents=True, exist_ok=True)

        if _HAS_DUCKDB:
            self._duckdb_conn = duckdb.connect(":memory:")
            # Register parquet paths for SQL access
            self._register_tables()

        self._initialized = True
        self.monitor.check("initialize")
        logger.info(f"PanelLoader initialized: data_path={self.data_path}, "
                     f"budget={self.max_memory_gb}GB")

    def _register_tables(self):
        """Register parquet directories as DuckDB views."""
        if not self._duckdb_conn:
            return

        table_map = {
            "prices_raw": "prices_raw",
            "daily_basic": "daily_basic",
            "adj_factor": "adj_factor",
            "index_weight": "index_weight",
            "limit_status": "limit_status",
            "suspend_status": "suspend_status",
            "trade_cal": "trade_cal",
        }

        for name, table_name in table_map.items():
            p = self.data_path / table_name
            if p.exists() and any(p.rglob("*.parquet")):
                try:
                    self._duckdb_conn.execute(
                        f"CREATE OR REPLACE VIEW {name} AS "
                        f"SELECT * FROM read_parquet('{p}/**/*.parquet', union_by_name=true)"
                    )
                    logger.debug(f"Registered DuckDB view: {name}")
                except Exception as e:
                    logger.debug(f"Could not register {name}: {e}")

    # ------------------------------------------------------------------
    # Query interface (DuckDB preferred, PyArrow fallback)
    # ------------------------------------------------------------------
    def query(self, table_name: str,
              columns: Optional[List[str]] = None,
              start_date: Optional[str] = None,
              end_date: Optional[str] = None,
              ts_codes: Optional[List[str]] = None,
              extra_where: Optional[str] = None,
              order_by: Optional[str] = None,
              limit: Optional[int] = None) -> pd.DataFrame:
        """
        Execute a filtered query against cached parquet data.

        All filters are pushed down to the parquet layer — only matching
        rows and columns are loaded into memory.

        Parameters
        ----------
        table_name : str
            Registered table name or path to parquet directory.
        columns : list of str, optional
            Columns to select. If None, select all.
        start_date, end_date : str, optional
            Date range filter on trade_date (YYYYMMDD).
        ts_codes : list of str, optional
            Stock codes to include.
        extra_where : str, optional
            Additional WHERE clause.
        order_by : str, optional
            ORDER BY clause.
        limit : int, optional
            LIMIT clause.

        Returns
        -------
        pd.DataFrame with only the requested data.
        """
        if not self._initialized:
            self.initialize()

        # Guard: empty ts_codes list means NO stocks requested → return empty
        # (NOT the same as ts_codes=None which means "no filter")
        if ts_codes is not None and len(ts_codes) == 0:
            logger.debug(f"query:{table_name}: ts_codes=[] → returning empty DataFrame")
            return pd.DataFrame()

        self.monitor.check(f"query:{table_name}")

        # Build SQL
        cols = ", ".join(f'"{c}"' for c in columns) if columns else "*"

        if _HAS_DUCKDB and self._duckdb_conn:
            return self._query_duckdb(table_name, cols, start_date, end_date,
                                      ts_codes, extra_where, order_by, limit)
        else:
            return self._query_pyarrow(table_name, columns, start_date, end_date,
                                       ts_codes, extra_where)

    def _query_duckdb(self, table_name: str, cols: str,
                      start_date: Optional[str], end_date: Optional[str],
                      ts_codes: Optional[List[str]],
                      extra_where: Optional[str],
                      order_by: Optional[str],
                      limit: Optional[int]) -> pd.DataFrame:
        """Execute query via DuckDB."""
        try:
            # Check if table is registered; if not, try direct path
            path = self.data_path / table_name
            if path.exists():
                # Normalize to forward slashes for DuckDB SQL compatibility
                path_str = str(path).replace("\\", "/")
                from_clause = (
                    f"read_parquet('{path_str}/**/*.parquet', "
                    f"union_by_name=true, hive_partitioning=true)"
                )
            else:
                from_clause = table_name  # assume registered view

            where_parts = []
            if start_date:
                where_parts.append(f"trade_date >= {int(start_date)}")
            if end_date:
                where_parts.append(f"trade_date <= {int(end_date)}")
            if ts_codes:
                # Batch large stock lists — never silently truncate.
                # Each batch queries one chunk, results are concatenated.
                if extra_where:
                    where_parts.append(extra_where)
                all_batches = []
                for batch_start in range(0, len(ts_codes), self.stock_batch_size):
                    batch_codes = ts_codes[batch_start:batch_start + self.stock_batch_size]
                    codes_str = ", ".join(f"'{c}'" for c in batch_codes)
                    batch_where = where_parts + [f"ts_code IN ({codes_str})"]
                    batch_sql = f"SELECT {cols} FROM {from_clause}"
                    batch_sql += " WHERE " + " AND ".join(batch_where)
                    if order_by:
                        batch_sql += f" ORDER BY {order_by}"
                    if limit:
                        batch_sql += f" LIMIT {limit}"
                    try:
                        batch_df = self._duckdb_conn.execute(batch_sql).df()
                        if not batch_df.empty:
                            all_batches.append(batch_df)
                    except Exception as e:
                        logger.debug(f"DuckDB batch {batch_start}: {e}")
                        continue

                if all_batches:
                    result = pd.concat(all_batches, ignore_index=True)
                else:
                    return pd.DataFrame()
                self.monitor.check(f"query_done:{table_name}({len(result)} rows)")
                return self._enforce_dtypes(result, table_name)
                # NOTE: we handle the full result above and return early;
                # the code below continues for the non-ts_codes case.
            if extra_where:
                where_parts.append(extra_where)

            sql = f"SELECT {cols} FROM {from_clause}"
            if where_parts:
                sql += " WHERE " + " AND ".join(where_parts)
            if order_by:
                sql += f" ORDER BY {order_by}"
            if limit:
                sql += f" LIMIT {limit}"

            logger.debug(f"DuckDB query: {sql[:200]}...")
            result = self._duckdb_conn.execute(sql).df()

            # Enforce dtypes
            result = self._enforce_dtypes(result, table_name)

            self.monitor.check(f"query_done:{table_name}({len(result)} rows)")
            return result

        except Exception as e:
            logger.debug(f"DuckDB query failed ({e}), falling back to PyArrow")
            return self._query_pyarrow(table_name, None, start_date, end_date, ts_codes)

    def _query_pyarrow(self, table_name: str,
                       columns: Optional[List[str]],
                       start_date: Optional[str], end_date: Optional[str],
                       ts_codes: Optional[List[str]],
                       extra_where: Optional[str] = None) -> pd.DataFrame:
        """Execute query via PyArrow Dataset (fallback)."""
        path = self.data_path / table_name
        if not path.exists():
            logger.warning(f"No data at {path}")
            return pd.DataFrame()

        # Build PyArrow filter
        filter_expr = None
        filters = []
        if start_date:
            filters.append(("trade_date", ">=", int(start_date)))
        if end_date:
            filters.append(("trade_date", "<=", int(end_date)))
        if ts_codes:
            filters.append(("ts_code", "in", ts_codes))

        if filters:
            filter_expr = self._build_pa_filter(filters)

        try:
            dataset = ds.dataset(str(path), format="parquet", partitioning="hive")
            table = dataset.to_table(columns=columns, filter=filter_expr)
            result = table.to_pandas()
            result = self._enforce_dtypes(result, table_name)
            self.monitor.check(f"pyarrow_query:{table_name}({len(result)} rows)")
            return result
        except Exception as e:
            logger.error(f"PyArrow query failed: {e}")
            # Last resort: scan individual files
            return self._scan_fallback(path, columns, filters)

    def _scan_fallback(self, path: Path, columns: Optional[List[str]],
                       filters: List[tuple]) -> pd.DataFrame:
        """Last-resort scan of individual parquet files."""
        files = list(path.rglob("*.parquet"))
        if not files:
            return pd.DataFrame()

        chunks = []
        for f in files:
            try:
                chunk = pq.read_table(f, columns=columns).to_pandas()
                # Apply filters manually
                for field, op, value in filters:
                    if op == ">=" and field in chunk.columns:
                        chunk = chunk[chunk[field] >= value]
                    elif op == "<=" and field in chunk.columns:
                        chunk = chunk[chunk[field] <= value]
                    elif op == "in" and field in chunk.columns:
                        chunk = chunk[chunk[field].isin(value)]
                if not chunk.empty:
                    chunks.append(chunk)
            except Exception:
                continue

        if chunks:
            return pd.concat(chunks, ignore_index=True)
        return pd.DataFrame()

    # ------------------------------------------------------------------
    # Convenience query methods
    # ------------------------------------------------------------------
    def query_prices(self, start_date: str, end_date: str,
                     ts_codes: Optional[List[str]] = None,
                     fields: Optional[List[str]] = None,
                     price_type: str = "adj") -> pd.DataFrame:
        """
        Query price data.

        Parameters
        ----------
        price_type : str
            "raw" for raw prices, "adj" for adjusted prices.
        """
        if price_type == "adj":
            table = "prices_adj"
            default_fields = ["ts_code", "trade_date",
                              "adj_open", "adj_high", "adj_low", "adj_close"]
        else:
            table = "prices_raw"
            default_fields = ["ts_code", "trade_date",
                              "open", "high", "low", "close", "vol", "amount"]

        cols = fields if fields else default_fields
        return self.query(table, columns=cols,
                          start_date=start_date, end_date=end_date,
                          ts_codes=ts_codes,
                          order_by="ts_code, trade_date")

    def query_daily_basic(self, start_date: str, end_date: str,
                          ts_codes: Optional[List[str]] = None,
                          fields: Optional[List[str]] = None) -> pd.DataFrame:
        """Query daily basic (fundamental) data."""
        default_fields = ["ts_code", "trade_date",
                          "total_mv", "circ_mv", "pe", "pb", "ps",
                          "turnover_rate"]
        return self.query("daily_basic",
                          columns=fields or default_fields,
                          start_date=start_date, end_date=end_date,
                          ts_codes=ts_codes,
                          order_by="ts_code, trade_date")

    def query_limit_data(self, date: str,
                         ts_codes: Optional[List[str]] = None) -> pd.DataFrame:
        """Query price limit data for a single date."""
        return self.query("limit_status",
                          columns=["ts_code", "trade_date", "up_limit", "down_limit"],
                          start_date=date, end_date=date,
                          ts_codes=ts_codes)

    # ------------------------------------------------------------------
    # Chunked iteration
    # ------------------------------------------------------------------
    def iter_date_chunks(self, start_date: str, end_date: str,
                         months: int = 3,
                         fields: Optional[List[str]] = None,
                         ts_codes: Optional[List[str]] = None) -> Iterator[pd.DataFrame]:
        """
        Iterate over date chunks for batch processing.

        Yields DataFrames covering 'months' of data at a time.
        Caller processes each chunk and releases it before the next.
        """
        start_dt = pd.Timestamp(start_date)
        end_dt = pd.Timestamp(end_date)

        current = start_dt
        while current <= end_dt:
            chunk_end = min(current + pd.DateOffset(months=months) - pd.Timedelta(days=1),
                            end_dt)
            chunk_start_str = current.strftime("%Y%m%d")
            chunk_end_str = chunk_end.strftime("%Y%m%d")

            logger.debug(f"Loading chunk: {chunk_start_str} -> {chunk_end_str}")
            chunk = self.query_prices(
                start_date=chunk_start_str,
                end_date=chunk_end_str,
                ts_codes=ts_codes,
                fields=fields,
                price_type="adj"
            )

            if not chunk.empty:
                yield chunk

            # Force garbage collection between chunks
            del chunk
            gc.collect()
            self.monitor.check(f"chunk_{chunk_start_str}")

            current = chunk_end + pd.Timedelta(days=1)

    def iter_stock_batches(self, ts_codes: List[str],
                           batch_size: int = None) -> Iterator[List[str]]:
        """Iterate over stock batches for per-stock factor computation."""
        if batch_size is None:
            batch_size = self.stock_batch_size
        for i in range(0, len(ts_codes), batch_size):
            yield ts_codes[i:i + batch_size]

    # ------------------------------------------------------------------
    # Single-date pivot (for small windows only)
    # ------------------------------------------------------------------
    def pivot_for_date(self, date: str,
                       ts_codes: Optional[List[str]] = None,
                       fields: Optional[List[str]] = None,
                       price_type: str = "adj") -> pd.DataFrame:
        """
        Pivot data for a SINGLE date into (stock x field) matrix.

        This is safe because a single date's cross-section is bounded
        (~300 stocks for CSI 300). Never use for date ranges.

        Returns DataFrame with index=ts_code, columns=fields.
        """
        df = self.query_prices(
            start_date=date, end_date=date,
            ts_codes=ts_codes,
            fields=fields,
            price_type=price_type
        )

        if df.empty:
            return df

        # Pivot to (stock x field)
        value_cols = [c for c in df.columns
                      if c not in ("ts_code", "trade_date")]
        pivoted = df.pivot_table(
            index="ts_code",
            values=value_cols,
            aggfunc="first"
        )
        pivoted.columns = value_cols

        # Ensure all requested stocks present
        if ts_codes:
            pivoted = pivoted.reindex(ts_codes)

        self.monitor.check(f"pivot_{date}")
        return pivoted

    def pivot_for_window(self, start_date: str, end_date: str,
                         ts_codes: Optional[List[str]] = None,
                         field: str = "adj_close") -> pd.DataFrame:
        """
        Pivot a single field over a date window into (date x stock) matrix.

        Only safe for small windows (e.g., 60 trading days × 300 stocks).
        For larger windows, use iter_date_chunks.

        Returns DataFrame with index=trade_date, columns=ts_code.
        """
        df = self.query_prices(
            start_date=start_date, end_date=end_date,
            ts_codes=ts_codes,
            fields=["ts_code", "trade_date", field],
            price_type="adj"
        )

        if df.empty:
            return df

        pivoted = df.pivot_table(
            index="trade_date",
            columns="ts_code",
            values=field,
            aggfunc="first"
        )

        self.monitor.check(f"pivot_window_{start_date}_{end_date}")
        return pivoted

    # ------------------------------------------------------------------
    # Generic data write (for prices, daily_basic, etc. — not factors)
    # ------------------------------------------------------------------
    def write_data(self, df: pd.DataFrame, table_name: str,
                   partition_cols: Optional[List[str]] = None,
                   row_group_size: int = 200000,
                   compression: str = "zstd",
                   compression_level: int = 3,
                   dedupe_keys: Optional[List[str]] = None,
                   replace_partitions: bool = False,
                   partition_values: Optional[dict] = None):
        """
        Write a DataFrame to hive-partitioned parquet under the data path.

        Parameters
        ----------
        dedupe_keys : list of str, optional
            Columns to deduplicate before writing (keep last).
        replace_partitions : bool
            If True, delete matched partitions before writing.
        partition_values : dict, optional
            {col: value} to identify partitions to replace.
        """
        if df.empty:
            return

        # Deduplicate
        if dedupe_keys:
            n_before = len(df)
            df = df.copy()
            df = df.drop_duplicates(dedupe_keys, keep="last")
            n_dropped = n_before - len(df)
            if n_dropped > 0:
                logger.info(f"write_data({table_name}): deduped {n_dropped} rows, "
                            f"{len(df)} remaining")
        if df.empty:
            return

        # Replace partitions — only delete combined paths (e.g. year=2016/month=1)
        out_path = self.data_path / table_name
        if replace_partitions and partition_cols and partition_cols:
            import shutil
            # Group by all partition columns to get unique combined paths
            if all(c in df.columns for c in partition_cols):
                for keys, _ in df.groupby(partition_cols):
                    if not isinstance(keys, tuple):
                        keys = (keys,)
                    part_dir = out_path
                    for c, v in zip(partition_cols, keys):
                        part_dir = part_dir / f"{c}={v}"
                    if part_dir.exists():
                        shutil.rmtree(str(part_dir))
                        logger.debug(f"Replaced partition: {part_dir}")

        out_path.mkdir(parents=True, exist_ok=True)
        table = pa.Table.from_pandas(df, preserve_index=False)
        pq.write_to_dataset(
            table,
            root_path=str(out_path),
            partition_cols=partition_cols or [],
            row_group_size=row_group_size,
            compression=compression,
            compression_level=compression_level,
            existing_data_behavior="overwrite_or_ignore",
        )
        logger.info(f"Wrote {len(df)} rows to {table_name} "
                     f"(partitions: {partition_cols})")

    # ------------------------------------------------------------------
    # Legacy factor layout cleanup
    # ------------------------------------------------------------------
    def cleanup_legacy_factor_layout(self, factor_name: str,
                                     years: list):
        """
        Remove legacy year-level parquet files that coexist with new
        year/month partitions.

        Old layout:  factors/factor_name=xxx/year=2016/*.parquet
        New layout:  factors/factor_name=xxx/year=2016/month=1/*.parquet

        When both exist, DuckDB / PyArrow reads both, causing duplicate
        (ts_code, trade_date) rows in factor_coverage and read_factor.
        """
        import shutil
        base = self.data_path / f"factors/factor_name={factor_name}"
        cleaned = 0
        for y in years:
            year_dir = base / f"year={y}"
            if not year_dir.exists():
                continue
            # Remove any bare .parquet files at the year level
            for p in year_dir.glob("*.parquet"):
                p.unlink()
                cleaned += 1
                logger.debug(f"Removed legacy file: {p}")
        if cleaned:
            logger.info(
                f"cleanup_legacy({factor_name}): removed {cleaned} "
                f"legacy parquet files in years {years}"
            )

    def cleanup_all_legacy_factor_layouts(self):
        """
        Scan all factor directories and remove legacy year-level
        parquet files when month subdirectories exist.
        """
        import shutil
        factors_base = self.data_path / "factors"
        if not factors_base.exists():
            return 0

        total_cleaned = 0
        for factor_dir in sorted(factors_base.glob("factor_name=*")):
            factor_name = factor_dir.name.replace("factor_name=", "")
            for year_dir in sorted(factor_dir.glob("year=*")):
                # Check if month subdirectories exist alongside bare files
                bare_files = list(year_dir.glob("*.parquet"))
                month_dirs = list(year_dir.glob("month=*"))
                if bare_files and month_dirs:
                    for p in bare_files:
                        p.unlink()
                        total_cleaned += 1
                        logger.debug(f"Removed legacy file: {p}")

        if total_cleaned:
            logger.info(
                f"cleanup_all_legacy: removed {total_cleaned} legacy "
                f"parquet files across all factors"
            )
        return total_cleaned

    # ------------------------------------------------------------------
    # Factor data I/O
    # ------------------------------------------------------------------
    def write_factor(self, df: pd.DataFrame, factor_name: str,
                     partition_by_year: bool = True):
        """
        Write computed factor values to partitioned parquet.

        Uses year+month partitions so that a short-window recompute
        (e.g., smoke test with --recompute) never deletes an entire
        year of production data.

        Automatically cleans up legacy year-level parquet files that
        would cause duplicate reads when coexisting with month partitions.

        Parameters
        ----------
        df : pd.DataFrame
            Must contain ts_code, trade_date, and factor value columns.
        factor_name : str
            Factor name for partitioning path.
        partition_by_year : bool
            If True, partition by year AND month.
        """
        if df.empty:
            return

        # Deduplicate: ensure no duplicate (ts_code, trade_date) keys
        df = df.copy()  # avoid SettingWithCopyWarning from upstream slice
        n_before = len(df)
        df = df.drop_duplicates(["ts_code", "trade_date"], keep="last")
        n_dropped = n_before - len(df)
        if n_dropped > 0:
            logger.warning(
                f"write_factor({factor_name}): dropped {n_dropped} duplicate "
                f"(ts_code, trade_date) rows — {len(df)} unique rows remaining"
            )

        if df.empty:
            return

        table_name = f"factors/factor_name={factor_name}"

        if partition_by_year:
            if "year" not in df.columns:
                df["year"] = df["trade_date"].astype(int) // 10000
            if "month" not in df.columns:
                df["month"] = (df["trade_date"].astype(int) % 10000) // 100
            partition_cols = ["year", "month"]

            # Clean up legacy year-level files BEFORE writing new data.
            # Old layout has year=YYYY/*.parquet; new layout has
            # year=YYYY/month=M/*.parquet.  Coexistence → duplicates.
            years = sorted(df["year"].unique())
            self.cleanup_legacy_factor_layout(factor_name, years)
        else:
            partition_cols = []

        # Clean partition directories before writing to avoid stale files
        # from previous runs with different data ranges.
        # With year+month partitions, only the affected months are cleaned.
        if partition_cols:
            import shutil
            for keys, _ in df.groupby(partition_cols):
                if not isinstance(keys, tuple):
                    keys = (keys,)
                part_dir = self.data_path / table_name
                for c, v in zip(partition_cols, keys):
                    part_dir = part_dir / f"{c}={v}"
                if part_dir.exists():
                    shutil.rmtree(str(part_dir))
                    logger.debug(f"Cleaned partition: {part_dir}")
        else:
            # Clean entire factor directory
            factor_dir = self.data_path / table_name
            if factor_dir.exists():
                import shutil
                shutil.rmtree(str(factor_dir))
                logger.debug(f"Cleaned factor dir: {factor_dir}")

        table = pa.Table.from_pandas(df, preserve_index=False)
        out_path = self.data_path / table_name
        out_path.mkdir(parents=True, exist_ok=True)

        pq.write_to_dataset(
            table,
            root_path=str(out_path),
            partition_cols=partition_cols,
            compression="zstd",
            compression_level=3,
            existing_data_behavior="overwrite_or_ignore",
        )

        df.drop(columns=["year", "month"], inplace=True, errors="ignore")

    def read_factor(self, factor_name: str,
                    start_date: Optional[str] = None,
                    end_date: Optional[str] = None,
                    ts_codes: Optional[List[str]] = None) -> pd.DataFrame:
        """Read pre-computed factor values (defensive dedup on read)."""
        table_name = f"factors/factor_name={factor_name}"
        df = self.query(table_name,
                        start_date=start_date, end_date=end_date,
                        ts_codes=ts_codes,
                        order_by="ts_code, trade_date")
        # Defensive: remove any duplicate (ts_code, trade_date) from stale cache
        if not df.empty:
            n_before = len(df)
            df = df.drop_duplicates(["ts_code", "trade_date"], keep="last")
            n_dropped = n_before - len(df)
            if n_dropped > 0:
                logger.warning(
                    f"read_factor({factor_name}): dropped {n_dropped} stale "
                    f"duplicate rows (cached data may need rebuild)"
                )
        return df

    # ------------------------------------------------------------------
    # Factor coverage check
    # ------------------------------------------------------------------
    def factor_coverage(self, factor_name: str,
                        start_date: str, end_date: str) -> dict:
        """Check if a cached factor covers the requested date range.

        Returns dict with: rows, n_dates, min_date, max_date, duplicates
        """
        table_name = f"factors/factor_name={factor_name}"
        path = self.data_path / table_name
        if not path.exists():
            return {"rows": 0, "n_dates": 0, "min_date": None,
                    "max_date": None, "duplicates": 0}

        df = self.query(table_name,
                        start_date=start_date, end_date=end_date,
                        columns=["ts_code", "trade_date"])
        if df.empty:
            return {"rows": 0, "n_dates": 0, "min_date": None,
                    "max_date": None, "duplicates": 0}

        n_before = len(df)
        df = df.drop_duplicates(["ts_code", "trade_date"])
        n_dup = n_before - len(df)

        return {
            "rows": len(df),
            "n_dates": int(df["trade_date"].nunique()),
            "min_date": int(df["trade_date"].min()),
            "max_date": int(df["trade_date"].max()),
            "duplicates": n_dup,
        }

    def has_factor_coverage(self, factor_name: str,
                            start_date: str, end_date: str,
                            min_dates: int = 12) -> bool:
        """Check if cached factor has enough dates to be useful.

        Returns True only if the factor covers the requested range with
        at least min_dates unique dates and has no duplicates.
        """
        cov = self.factor_coverage(factor_name, start_date, end_date)
        if cov["rows"] == 0:
            return False
        if cov["duplicates"] > 0:
            return False
        if cov["n_dates"] < min_dates:
            return False
        return True

    # ------------------------------------------------------------------
    # Coverage checks
    # ------------------------------------------------------------------
    def price_coverage(self, table_name: str,
                       start_date: str, end_date: str) -> dict:
        """
        Check if cached price data covers the requested date range.

        Returns dict with: rows, n_dates, expected_trade_dates,
        coverage_ratio, missing_dates, min_date, max_date.

        Uses trading calendar for expected_trade_dates comparison.
        """
        path = self.data_path / table_name
        if not path.exists():
            return {"rows": 0, "n_dates": 0, "expected_trade_dates": 0,
                    "coverage_ratio": 0.0, "missing_dates": [],
                    "min_date": None, "max_date": None}

        df = self.query(table_name,
                        columns=["trade_date"],
                        start_date=start_date, end_date=end_date)
        if df.empty:
            return {"rows": 0, "n_dates": 0, "expected_trade_dates": 0,
                    "coverage_ratio": 0.0, "missing_dates": [],
                    "min_date": None, "max_date": None}

        cached_dates = set(df["trade_date"].unique().tolist())

        # Get expected trade dates from calendar
        try:
            from data.calendar import get_calendar
            cal = get_calendar()
            cal.load(start_date=start_date, end_date=end_date)
            expected = set(
                int(d) for d in
                cal.trade_days_between(int(start_date), int(end_date))
            )
        except Exception:
            expected = cached_dates  # can't compare

        missing = sorted(expected - cached_dates)
        coverage = len(cached_dates) / len(expected) if expected else 0.0

        return {
            "rows": len(df),
            "n_dates": len(cached_dates),
            "expected_trade_dates": len(expected),
            "coverage_ratio": round(coverage, 4),
            "missing_dates": missing[:20],  # first 20 for readability
            "min_date": int(df["trade_date"].min()),
            "max_date": int(df["trade_date"].max()),
        }

    def daily_basic_coverage(self, start_date: str, end_date: str) -> dict:
        """
        Check monthly snapshot coverage for daily_basic.

        Uses the SAME expected-date logic as get_daily_basic():
        for each month-end, the expected trade_date is the nearest
        previous trading day (not the calendar month-end itself).

        Returns dict with: n_months_expected, n_months_cached,
        coverage_ratio, expected_dates, cached_dates, missing_dates.
        """
        df = self.query("daily_basic",
                        columns=["trade_date"],
                        start_date=start_date, end_date=end_date)
        if df.empty:
            return {"n_months_expected": 0, "n_months_cached": 0,
                    "coverage_ratio": 0.0, "expected_dates": [],
                    "cached_dates": [], "missing_dates": []}

        cached_dates = set(df["trade_date"].unique().tolist())

        # Generate expected month-end dates using the SAME logic as
        # TushareClient.get_daily_basic(): prev_trade_day of month-end
        from data.calendar import get_calendar
        cal = get_calendar()
        cal.load(start_date=start_date, end_date=end_date)

        start_dt = pd.Timestamp(start_date)
        end_dt = pd.Timestamp(end_date)
        expected_dates = []
        current = pd.Timestamp(year=start_dt.year, month=start_dt.month, day=1)
        while current <= end_dt:
            month_end = current + pd.offsets.MonthEnd(0)
            if month_end > end_dt:
                break
            me_int = int(month_end.strftime("%Y%m%d"))
            try:
                target = cal.prev_trade_day(me_int)
            except Exception:
                target = me_int
            expected_dates.append(target)
            current = month_end + pd.Timedelta(days=1)

        expected_set = set(expected_dates)
        cached_in_expected = cached_dates & expected_set
        missing = sorted(expected_set - cached_dates)
        coverage = len(cached_in_expected) / len(expected_set) if expected_set else 0.0

        return {
            "n_months_expected": len(expected_set),
            "n_months_cached": len(cached_in_expected),
            "coverage_ratio": round(coverage, 4),
            "expected_dates": sorted(expected_set),
            "cached_dates": sorted(cached_dates),
            "missing_dates": missing,
        }

    # ------------------------------------------------------------------
    # Dtype enforcement
    # ------------------------------------------------------------------
    def _enforce_dtypes(self, df: pd.DataFrame, table_name: str) -> pd.DataFrame:
        """Enforce memory-efficient dtypes on query results."""
        if df.empty:
            return df

        DTYPE_MAP = {
            "ts_code": "category",
            "industry_code": "category",
            "trade_date": "int32",
            "open": "float32", "high": "float32", "low": "float32", "close": "float32",
            "adj_open": "float32", "adj_high": "float32", "adj_low": "float32",
            "adj_close": "float32",
            "pre_close": "float32", "adj_factor": "float32",
            "vol": "float64", "amount": "float64",
            "total_mv": "float64", "circ_mv": "float64",
            "pe": "float32", "pb": "float32", "ps": "float32",
            "turnover_rate": "float32",
            "up_limit": "float32", "down_limit": "float32",
        }

        for col, dtype in DTYPE_MAP.items():
            if col in df.columns:
                try:
                    df[col] = df[col].astype(dtype)
                except (ValueError, TypeError):
                    pass

        # Cast category columns from object
        for col in df.columns:
            if df[col].dtype == "object":
                try:
                    df[col] = df[col].astype("category")
                except (ValueError, TypeError):
                    pass

        return df

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _build_pa_filter(conditions: List[tuple]) -> ds.Expression:
        """Build PyArrow filter expression."""
        expr = None
        for field, op, value in conditions:
            if op == ">=":
                e = ds.field(field) >= value
            elif op == "<=":
                e = ds.field(field) <= value
            elif op == "==":
                e = ds.field(field) == value
            elif op == "in":
                e = ds.field(field).isin(value)
            else:
                raise ValueError(f"Unsupported filter: {op}")
            expr = e if expr is None else expr & e
        return expr

    def close(self):
        """Clean up connections."""
        if self._duckdb_conn:
            self._duckdb_conn.close()
            self._duckdb_conn = None
        self._initialized = False

    def __del__(self):
        self.close()

    def __enter__(self):
        self.initialize()
        return self

    def __exit__(self, *args):
        self.close()


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
_loader: Optional[PanelLoader] = None


def get_loader(**kwargs) -> PanelLoader:
    """Get or create singleton PanelLoader."""
    global _loader
    if _loader is None:
        _loader = PanelLoader(**kwargs)
    return _loader

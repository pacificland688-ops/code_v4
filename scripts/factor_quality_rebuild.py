"""Factor Quality Rebuild — systematic factor audit, direction validation,
IC/quantile-return evaluation, turnover-cost analysis, neutralization diagnostic,
no-leakage alignment, regime breakdown, capacity screening, correlation clustering,
and multi-gate quality gate.

Reads existing factor cache and forward returns. Does not recompute factors.

v2 — 2026-06-14
- Factor-level data_lag_days with trading-calendar alignment (no-leakage hard gate).
- Raw + mcap-neutral dual reporting with four-state quality gate.
- Real turnover cost (drifted-weight or overlap-proxy).
- IC trend, rolling-window robustness, capacity/liquidity screening.
- Correlation-cluster deduplication with gate_score ranking.
- Candidate-pool contract: eligible / watch / support / missing_data / fail.
- No STUB outputs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from time import perf_counter
from typing import Any, Optional

import numpy as np
import pandas as pd
import yaml
from scipy.stats import spearmanr, pearsonr, linregress

# Version strings for reproducibility metadata
_PYTHON_VERSION: str = platform.python_version()
_NUMPY_VERSION: str = np.__version__
_PANDAS_VERSION: str = pd.__version__
try:
    import scipy
    _SCIPY_VERSION: str = scipy.__version__
except Exception:
    _SCIPY_VERSION: str = "unknown"

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ---------------------------------------------------------------------------
# Stage timing
# ---------------------------------------------------------------------------

_profile: dict[str, float] = {}

@contextmanager
def timed_stage(name: str):
    t0 = perf_counter()
    print(f"[stage:start] {name}", flush=True)
    try:
        yield
    finally:
        elapsed = perf_counter() - t0
        _profile[name] = elapsed
        print(f"[stage:end]   {name}  elapsed={elapsed:.1f}s", flush=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pct(value: Any, digits: int = 1) -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return ""
    return f"{float(value) * 100:.{digits}f}%"


def _num(value: Any, digits: int = 3) -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return ""
    return f"{float(value):.{digits}f}"


def _rank_ic(factor_vals: pd.Series, fwd_rets: pd.Series) -> float:
    """Spearman rank correlation, returns NaN if < 30 observations."""
    mask = factor_vals.notna() & fwd_rets.notna()
    if mask.sum() < 30:
        return float("nan")
    try:
        return float(spearmanr(factor_vals[mask], fwd_rets[mask])[0])
    except Exception:
        return float("nan")


def _pearson_ic(factor_vals: pd.Series, fwd_rets: pd.Series) -> float:
    mask = factor_vals.notna() & fwd_rets.notna()
    if mask.sum() < 30:
        return float("nan")
    try:
        return float(pearsonr(factor_vals[mask], fwd_rets[mask])[0])
    except Exception:
        return float("nan")


def _add_calendar_days(date_int: int, days: int) -> int:
    """Add calendar days to a YYYYMMDD int, return YYYYMMDD int."""
    dt = datetime.strptime(str(date_int), "%Y%m%d")
    dt = dt + timedelta(days=days)
    return int(dt.strftime("%Y%m%d"))


def _get_trading_calendar():
    """Lazy-load the trading calendar singleton."""
    try:
        from data.calendar import get_calendar
        cal = get_calendar()
        cal.load("20150101", "20991231")
        return cal
    except Exception:
        return None


def _config_checksum(config_path: Path) -> str:
    """Return SHA256 hex digest (first 16 chars) of config file for traceability."""
    try:
        return hashlib.sha256(config_path.read_bytes()).hexdigest()[:16]
    except Exception:
        return "unavailable"


def _validate_factor_config(factor_cfg: dict) -> list[str]:
    """Return list of config warnings/suggestions for a single factor.

    Checks:
      - pit_aligned + data_lag_days > 0  →  contradictory (lag ignored for pit_aligned)
      - fundamental + observation_date + data_lag_days == 0  →  potential look-ahead
    """
    warnings: list[str] = []
    fname = factor_cfg.get("name", "?")
    date_semantics = factor_cfg.get("date_semantics", "observation_date")
    data_lag_days = int(factor_cfg.get("data_lag_days", 0))
    ftype = factor_cfg.get("type", "")

    if date_semantics == "pit_aligned" and data_lag_days > 0:
        warnings.append(
            f"[{fname}] pit_aligned with data_lag_days={data_lag_days}>0 — "
            f"lag offset will NOT be applied for pit_aligned factors "
            f"(available_date = trade_date)"
        )
    if (ftype == "fundamental" and date_semantics == "observation_date"
            and data_lag_days == 0 and fname != "log_market_cap_cs"):
        warnings.append(
            f"[{fname}] fundamental factor with observation_date + "
            f"data_lag_days=0 — potential look-ahead bias"
        )
    return warnings


# ---------------------------------------------------------------------------
# Run diagnostics — manifest, progress, timing, error files
# ---------------------------------------------------------------------------

RUN_MANIFEST_COLUMNS = [
    "run_id", "config_path", "config_sha256", "seed",
    "factor_count", "out_dir", "out_doc",
    "start_time", "end_time", "status",
]

RUN_PROGRESS_COLUMNS = [
    "run_id", "factor", "factor_index",
    "stage", "status", "elapsed_sec",
    "raw_rows", "aligned_rows", "message",
]

RUN_STAGE_TIMINGS_COLUMNS = [
    "run_id", "stage", "elapsed_sec", "status", "rows_out", "warning",
]

RUN_ERRORS_COLUMNS = [
    "run_id", "stage", "factor", "error_type", "error_message", "traceback",
]


class RunDiagnostics:
    """Manages run-level diagnostic files: manifest, progress, timings, errors.

    All files are flushed to disk immediately for crash-safe diagnostics.
    """

    def __init__(self, diag_dir: Path, run_id: str, config_path: str,
                 config_sha256: str, seed: int, factor_count: int,
                 out_dir: str, out_doc: str):
        self.diag_dir = diag_dir
        self.run_id = run_id
        self.config_path = config_path
        self.config_sha256 = config_sha256
        self.seed = seed
        self.factor_count = factor_count
        self.out_dir = out_dir
        self.out_doc = out_doc
        self._manifest_path = diag_dir / "run_manifest.json"
        self._progress_path = diag_dir / "run_progress.csv"
        self._timings_path = diag_dir / "run_stage_timings.csv"
        self._errors_path = diag_dir / "run_errors.csv"

        # Capture start_time once and preserve it across all manifest writes
        self.start_time = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

        diag_dir.mkdir(parents=True, exist_ok=True)

        # Create header-only diagnostic CSVs on start (crash-safe contract)
        _write_csv_safe(self._progress_path, [], RUN_PROGRESS_COLUMNS)
        _write_csv_safe(self._timings_path, [], RUN_STAGE_TIMINGS_COLUMNS)
        _write_csv_safe(self._errors_path, [], RUN_ERRORS_COLUMNS)

        self._write_manifest("RUNNING")

    def _write_manifest(self, status: str, end_time: str = ""):
        manifest = {
            "run_id": self.run_id,
            "config_path": self.config_path,
            "config_sha256": self.config_sha256,
            "seed": self.seed,
            "factor_count": self.factor_count,
            "out_dir": self.out_dir,
            "out_doc": self.out_doc,
            "start_time": self.start_time,
            "end_time": end_time,
            "status": status,
        }
        self._manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def mark_success(self):
        self._write_manifest("SUCCESS", datetime.now().strftime("%Y-%m-%dT%H:%M:%S"))

    def mark_failed(self):
        self._write_manifest("FAILED", datetime.now().strftime("%Y-%m-%dT%H:%M:%S"))

    def log_progress(self, factor: str, factor_index: int, stage: str,
                     status: str, elapsed_sec: float,
                     raw_rows: int = 0, aligned_rows: int = 0,
                     message: str = ""):
        row = {
            "run_id": self.run_id,
            "factor": factor,
            "factor_index": factor_index,
            "stage": stage,
            "status": status,
            "elapsed_sec": round(elapsed_sec, 2),
            "raw_rows": raw_rows,
            "aligned_rows": aligned_rows,
            "message": message,
        }
        _write_csv_safe_append(self._progress_path, [row], RUN_PROGRESS_COLUMNS)

    def log_stage_timing(self, stage: str, elapsed_sec: float,
                         status: str = "OK", rows_out: int = 0,
                         warning: str = ""):
        row = {
            "run_id": self.run_id,
            "stage": stage,
            "elapsed_sec": round(elapsed_sec, 1),
            "status": status,
            "rows_out": rows_out,
            "warning": warning,
        }
        _write_csv_safe_append(self._timings_path, [row], RUN_STAGE_TIMINGS_COLUMNS)

    def log_error(self, stage: str, factor: str, error_type: str,
                  error_message: str, traceback_str: str = ""):
        row = {
            "run_id": self.run_id,
            "stage": stage,
            "factor": factor,
            "error_type": error_type,
            "error_message": error_message[:500],
            "traceback": traceback_str[:2000],
        }
        _write_csv_safe_append(self._errors_path, [row], RUN_ERRORS_COLUMNS)


def _write_csv_safe_append(path: Path, rows: list[dict], columns: list[str]) -> None:
    """Append rows to a CSV file, creating header if file doesn't exist."""
    import pandas as pd
    exists = path.exists()
    df = pd.DataFrame(rows)
    for col in columns:
        if col not in df.columns:
            df[col] = ""
    df = df[columns]
    df.to_csv(path, mode="a", index=False, header=not exists, encoding="utf-8-sig")

# Fixed columns for each output CSV (ensures header-only when no data)
ROLLING_WINDOW_GATE_COLUMNS = [
    "factor", "window_name", "calibration_years", "validation_years",
    "n_dates", "mean_rank_ic", "icir", "net_spread_5d",
    "positive_ic_years", "positive_spread_years", "window_pass",
    "failure_reasons",
]

REGIME_BREAKDOWN_COLUMNS = [
    "factor", "basis", "regime", "n_dates", "mean_ic",
    "mean_net_spread", "regime_status",
]

CAPACITY_AUDIT_COLUMNS = [
    "factor", "year", "basis", "n_stocks", "n_dates",
    "median_market_cap_cny", "median_top_amount_cny",
    "median_leg_amount_sum_cny", "estimated_trade_cny_at_target_aum",
    "participation_rate_at_target_aum", "capacity_status",
]

CORRELATION_CLUSTER_COLUMNS = [
    "cluster_id", "factor", "representative", "redundant_to",
    "max_abs_corr_to_rep", "gate_score",
]


def _validate_robustness_config(robustness_cfg: dict) -> None:
    """Validate robustness.rolling_windows schema before any heavy computation.

    Each rolling window MUST have name, start, end (YYYYMMDD strings).
    Raises ValueError with a clear message if the schema is wrong.
    """
    rolling_windows = robustness_cfg.get("rolling_windows", [])
    if not rolling_windows:
        return  # no windows configured, acceptable

    for i, rw in enumerate(rolling_windows):
        prefix = f"robustness.rolling_windows[{i}]"
        for key in ("name", "start", "end"):
            if key not in rw:
                raise ValueError(
                    f"Invalid {prefix}: missing required key '{key}'. "
                    f"Each rolling window requires {{name, start, end}} with YYYYMMDD strings. "
                    f"Got keys: {list(rw.keys())}"
                )
        # Validate date format
        for key in ("start", "end"):
            val = str(rw[key])
            if len(val) != 8 or not val.isdigit():
                raise ValueError(
                    f"Invalid {prefix}.{key}='{val}': must be YYYYMMDD string (8 digits)"
                )


def _write_csv_safe(out_path: Path, rows: list[dict], columns: list[str]) -> None:
    """Write a CSV file with guaranteed header row.

    - rows non-empty: write rows in column order
    - rows empty: write header-only CSV
    """
    import pandas as pd
    if rows:
        df = pd.DataFrame(rows)
        # Ensure all columns exist in order
        for col in columns:
            if col not in df.columns:
                df[col] = ""
        df = df[columns]
    else:
        df = pd.DataFrame(columns=columns)
    df.to_csv(out_path, index=False, encoding="utf-8-sig")


def _write_partial_csvs(
    partial_dir: Path,
    input_audits: list[dict],
    direction_audits: list[dict],
    alignment_audits: list[dict],
    ic_rows_all: list[dict],
    quantile_rows_all: list[dict],
    turnover_cost_all: list[dict],
    neutralization_diags: list[dict],
    ic_trends: list[dict],
) -> None:
    """Write incremental partial CSVs after each factor completes.

    These are crash-safe checkpoints — even if the run fails later,
    the partial data for completed factors is preserved.
    """
    try:
        pd.DataFrame(input_audits).to_csv(
            partial_dir / "factor_input_audit.partial.csv", index=False, encoding="utf-8-sig")
        pd.DataFrame(direction_audits).to_csv(
            partial_dir / "factor_direction_audit.partial.csv", index=False, encoding="utf-8-sig")
        pd.DataFrame(alignment_audits).to_csv(
            partial_dir / "factor_alignment_audit.partial.csv", index=False, encoding="utf-8-sig")
        if ic_rows_all:
            pd.DataFrame(ic_rows_all).to_csv(
                partial_dir / "factor_ic_by_year.partial.csv", index=False, encoding="utf-8-sig")
        if quantile_rows_all:
            pd.DataFrame(quantile_rows_all).to_csv(
                partial_dir / "factor_quantile_returns.partial.csv", index=False, encoding="utf-8-sig")
        if turnover_cost_all:
            pd.DataFrame(turnover_cost_all).to_csv(
                partial_dir / "factor_turnover_cost.partial.csv", index=False, encoding="utf-8-sig")
        if neutralization_diags:
            pd.DataFrame(neutralization_diags).to_csv(
                partial_dir / "factor_neutralization_diagnostic.partial.csv", index=False, encoding="utf-8-sig")
        if ic_trends:
            pd.DataFrame(ic_trends).to_csv(
                partial_dir / "factor_ic_trend.partial.csv", index=False, encoding="utf-8-sig")
    except Exception:
        pass  # Partial writes are best-effort; don't crash the main pipeline


PUBLISH_CSVS = [
    "factor_input_audit.csv",
    "factor_direction_audit.csv",
    "factor_alignment_audit.csv",
    "factor_ic_by_year.csv",
    "factor_quantile_returns.csv",
    "factor_turnover_cost.csv",
    "factor_neutralization_diagnostic.csv",
    "factor_ic_trend.csv",
    "factor_rolling_window_gate.csv",
    "factor_correlation_cluster.csv",
    "factor_capacity_audit.csv",
    "factor_regime_breakdown.csv",
    "factor_quality_gate.csv",
]

DIAGNOSTIC_CSV_NAMES = ["run_progress.csv", "run_stage_timings.csv", "run_errors.csv"]


def _publish_outputs(out_dir: Path, run_dir: Path, out_doc: Path) -> int:
    """Publish only official output CSVs from run_dir to out-dir root.

    - Copies each whitelisted CSV from run_dir to out_dir.
    - Copies factor_candidate_pool.yaml.
    - Copies the report to out_doc.
    - Cleans up stale diagnostic CSVs that may have leaked in previous runs.
    - Does NOT publish diagnostic CSVs (run_progress, run_stage_timings, run_errors).

    Returns the count of published files.
    """
    import shutil

    # Clean up stale diagnostic CSVs that may have leaked in previous runs
    for name in DIAGNOSTIC_CSV_NAMES:
        stale = out_dir / name
        if stale.exists():
            stale.unlink()

    published = 0
    for name in PUBLISH_CSVS:
        src = run_dir / name
        if src.exists():
            shutil.copy2(src, out_dir / name)
            published += 1

    pool_src = run_dir / "factor_candidate_pool.yaml"
    if pool_src.exists():
        shutil.copy2(pool_src, out_dir / "factor_candidate_pool.yaml")
        published += 1

    # Copy report to out_doc location
    report_src = run_dir / "factor_quality_rebuild_report.md"
    if report_src.exists():
        out_doc.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(report_src, out_doc)

    return published


# ---------------------------------------------------------------------------
# Factor data loading — two-phase (raw → audit → clean)
# ---------------------------------------------------------------------------

def _load_factor_cache_raw(factor_name: str, start: str, end: str) -> pd.DataFrame:
    """Load CS-processed factor from parquet cache WITHOUT deduplication.

    Returns DataFrame with columns [ts_code, trade_date, value].
    Preserves duplicates, missing values, and outliers for audit.
    """
    root = ROOT / "data" / "parquet" / "factors" / f"factor_name={factor_name}"
    if not root.exists():
        return pd.DataFrame(columns=["ts_code", "trade_date", "value"])

    chunks = []
    start_int = int(start)
    end_int = int(end)
    for year_dir in sorted(root.iterdir()):
        if not year_dir.is_dir() or not year_dir.name.startswith("year="):
            continue
        year = int(year_dir.name.split("=")[1])
        if year < (start_int // 10000) - 1 or year > (end_int // 10000) + 1:
            continue

        for sub_dir in sorted(year_dir.iterdir()):
            if sub_dir.is_dir() and sub_dir.name.startswith("month="):
                # Old V3 format: year={Y}/month={M}/*.parquet
                for pq_file in sub_dir.glob("*.parquet"):
                    try:
                        part = pd.read_parquet(pq_file)
                    except Exception:
                        continue

                    part.columns = [str(c).strip().lower() for c in part.columns]
                    value_cols = [c for c in part.columns if c not in ("ts_code", "trade_date", "year", "month")]
                    if not value_cols:
                        continue
                    value_col = value_cols[0]
                    part = part.rename(columns={value_col: "value"})

                    if "ts_code" not in part.columns or "trade_date" not in part.columns:
                        continue
                    part = part[["ts_code", "trade_date", "value"]].copy()
                    part["ts_code"] = part["ts_code"].astype(str)
                    part["trade_date"] = pd.to_numeric(part["trade_date"], errors="coerce")
                    part["value"] = pd.to_numeric(part["value"], errors="coerce")
                    part = part.dropna(subset=["trade_date"])
                    part = part[(part["trade_date"] >= start_int) & (part["trade_date"] <= end_int)]
                    if not part.empty:
                        chunks.append(part)
            elif sub_dir.suffix == ".parquet":
                # V4 format: year={Y}/part_{Y}.parquet (already has 'value' column)
                try:
                    part = pd.read_parquet(sub_dir)
                except Exception:
                    continue

                part.columns = [str(c).strip().lower() for c in part.columns]
                if "ts_code" not in part.columns or "trade_date" not in part.columns:
                    continue
                if "value" not in part.columns:
                    continue

                part = part[["ts_code", "trade_date", "value"]].copy()
                part["ts_code"] = part["ts_code"].astype(str)
                part["trade_date"] = pd.to_numeric(part["trade_date"], errors="coerce")
                part["value"] = pd.to_numeric(part["value"], errors="coerce")
                part = part.dropna(subset=["trade_date"])
                part = part[(part["trade_date"] >= start_int) & (part["trade_date"] <= end_int)]
                if not part.empty:
                    chunks.append(part)

    if not chunks:
        return pd.DataFrame(columns=["ts_code", "trade_date", "value"])
    result = pd.concat(chunks, ignore_index=True)
    return result.sort_values(["ts_code", "trade_date"])


def _clean_factor_panel(raw_df: pd.DataFrame) -> pd.DataFrame:
    """Remove duplicates and extreme outliers from raw factor panel.

    Only drops (ts_code, trade_date) duplicates keeping the first value.
    Does NOT remove NaN values — those are tracked in audit.
    """
    if raw_df.empty:
        return raw_df.copy()
    clean = raw_df.drop_duplicates(["ts_code", "trade_date"], keep="first")
    # Remove extreme outliers (> 10 std from median) — data errors
    val = clean["value"].dropna()
    if len(val) > 0:
        median = val.median()
        mad = (val - median).abs().median()
        if mad > 0:
            clean = clean[
                (clean["value"].isna()) |
                ((clean["value"] - median).abs() <= 10 * mad * 1.4826)
            ]
    return clean.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)


def _load_fwd_returns(start: str, end: str) -> pd.DataFrame:
    """Load forward returns from factor cache (multi-column, preserve all)."""
    root = ROOT / "data" / "parquet" / "factors" / "factor_name=fwd_returns"
    if not root.exists():
        return pd.DataFrame()

    chunks = []
    start_int, end_int = int(start), int(end)
    for year_dir in sorted(root.iterdir()):
        if not year_dir.is_dir() or not year_dir.name.startswith("year="):
            continue
        year = int(year_dir.name.split("=")[1])
        if year < (start_int // 10000) - 1 or year > (end_int // 10000) + 1:
            continue
        for month_dir in sorted(year_dir.iterdir()):
            if not month_dir.is_dir():
                continue
            for pq_file in month_dir.glob("*.parquet"):
                try:
                    part = pd.read_parquet(pq_file)
                except Exception:
                    continue
                part.columns = [str(c).strip().lower() for c in part.columns]
                keep_cols = [c for c in part.columns if c not in ("year", "month")]
                part = part[keep_cols].copy()
                part["ts_code"] = part["ts_code"].astype(str)
                part["trade_date"] = pd.to_numeric(part["trade_date"], errors="coerce")
                part = part.dropna(subset=["trade_date"])
                part = part[(part["trade_date"] >= start_int) & (part["trade_date"] <= end_int)]
                if not part.empty:
                    chunks.append(part)

    if not chunks:
        return pd.DataFrame()
    result = pd.concat(chunks, ignore_index=True)
    result = result.drop_duplicates(["ts_code", "trade_date"])
    return result.sort_values(["ts_code", "trade_date"])


def _load_daily_basic(start: str, end: str) -> pd.DataFrame:
    """Load daily_basic data for capacity screening.

    Returns DataFrame with [ts_code, trade_date, total_mv, circ_mv, turnover_rate].
    """
    root = ROOT / "data" / "parquet" / "daily_basic"
    if not root.exists():
        return pd.DataFrame()

    chunks = []
    start_int, end_int = int(start), int(end)
    for year_dir in sorted(root.iterdir()):
        if not year_dir.is_dir() or not year_dir.name.startswith("year="):
            continue
        year = int(year_dir.name.split("=")[1])
        if year < (start_int // 10000) - 1 or year > (end_int // 10000) + 1:
            continue
        for month_dir in sorted(year_dir.iterdir()):
            if not month_dir.is_dir():
                continue
            for pq_file in month_dir.glob("*.parquet"):
                try:
                    part = pd.read_parquet(pq_file)
                except Exception:
                    continue
                part.columns = [str(c).strip().lower() for c in part.columns]
                needed = ["ts_code", "trade_date"]
                available = [c for c in needed if c in part.columns]
                extra = [c for c in ["total_mv", "circ_mv", "turnover_rate"] if c in part.columns]
                if "ts_code" not in part.columns or "trade_date" not in part.columns:
                    continue
                part = part[available + extra].copy()
                part["ts_code"] = part["ts_code"].astype(str)
                part["trade_date"] = pd.to_numeric(part["trade_date"], errors="coerce")
                part = part.dropna(subset=["trade_date"])
                part = part[(part["trade_date"] >= start_int) & (part["trade_date"] <= end_int)]
                if not part.empty:
                    chunks.append(part)

    if not chunks:
        return pd.DataFrame()
    result = pd.concat(chunks, ignore_index=True)
    result = result.drop_duplicates(["ts_code", "trade_date"])
    return result.sort_values(["ts_code", "trade_date"])


# ---------------------------------------------------------------------------
# Data quality audit
# ---------------------------------------------------------------------------

def _audit_factor_input(
    factor_cfg: dict, raw_df: pd.DataFrame, fwd: pd.DataFrame,
    window_start: str, window_end: str,
) -> dict[str, Any]:
    """Audit a single factor's data quality from raw (pre-dedup) data."""
    fname = factor_cfg["name"]

    if raw_df.empty:
        return {
            "factor": fname,
            "raw_rows": 0, "clean_rows": 0,
            "n_rows": 0, "n_unique_stocks": 0, "n_unique_dates": 0,
            "duplicate_keys": 0, "duplicate_key_rate": 0.0,
            "missing_rate": 1.0,
            "constant_dates": 0, "extreme_outlier_rate": 0.0,
            "median_daily_coverage": 0, "min_daily_coverage": 0,
            "median_coverage_pct": 0.0, "min_yearly_coverage_pct": 0.0,
            "median_fwd_universe_size": 0, "median_overlap_count": 0,
            "missing_fwd_universe_dates": 0, "coverage_status": "NO_OVERLAP_WITH_FORWARD_RETURNS",
            "input_audit_status": "FAIL",
            "input_audit_reason": "empty factor cache",
            "data_status": "DATA_MISSING",
        }

    raw_rows = len(raw_df)
    n_stocks = raw_df["ts_code"].nunique()
    n_dates = raw_df["trade_date"].nunique()
    dupes = int(raw_df.duplicated(["ts_code", "trade_date"]).sum())
    dupe_rate = dupes / max(raw_rows, 1)

    # Clean for coverage computation
    clean = _clean_factor_panel(raw_df)
    clean_rows = len(clean)

    # Coverage: |factor ∩ fwd| / |fwd| per factor date
    # Only compute on dates where the factor HAS data (not all fwd dates).
    # Computing on all fwd dates drags median to 0 for sparse (e.g. monthly) factors.
    median_coverage_pct = 0.0
    min_yearly_coverage_pct = 0.0
    median_cov = 0
    min_cov = 0
    median_fwd_universe_size = 0
    median_overlap_count = 0
    missing_fwd_universe_dates = 0
    coverage_status = "OK"

    if not fwd.empty and not clean.empty:
        fwd_counts = fwd[["ts_code", "trade_date"]].drop_duplicates().groupby("trade_date").size()
        factor_counts = clean.groupby("trade_date")["ts_code"].nunique()
        daily_cov_pcts = []
        daily_overlaps = []
        daily_fwd_sizes = []
        yearly_cov: dict[int, list] = {}

        # Iterate over FACTOR dates (not fwd dates) to avoid zero-inflation
        for dt, factor_n in factor_counts.items():
            if factor_n <= 0:
                continue
            fwd_n = int(fwd_counts.get(dt, 0))
            if fwd_n == 0:
                missing_fwd_universe_dates += 1
                continue  # don't count dates with no fwd universe
            # Intersection: count stocks present in BOTH factor and fwd on this date
            factor_stocks = set(clean[clean["trade_date"] == dt]["ts_code"].unique())
            fwd_stocks = set(fwd[fwd["trade_date"] == dt]["ts_code"].unique())
            overlap_n = len(factor_stocks & fwd_stocks)
            pct = min(overlap_n / fwd_n, 1.0)

            daily_cov_pcts.append(pct)
            daily_overlaps.append(overlap_n)
            daily_fwd_sizes.append(fwd_n)
            yr = dt // 10000
            yearly_cov.setdefault(yr, []).append(pct)

        if daily_cov_pcts:
            median_coverage_pct = float(np.median(daily_cov_pcts))
            median_fwd_universe_size = float(np.median(daily_fwd_sizes))
            median_overlap_count = float(np.median(daily_overlaps))
        if yearly_cov:
            yearly_medians = [float(np.median(v)) for v in yearly_cov.values()]
            min_yearly_coverage_pct = float(min(yearly_medians)) if yearly_medians else 0.0

        # Coverage status
        if missing_fwd_universe_dates > 0 and len(daily_cov_pcts) == 0:
            coverage_status = "FORWARD_UNIVERSE_MISSING"
        elif len(daily_cov_pcts) == 0:
            coverage_status = "NO_OVERLAP_WITH_FORWARD_RETURNS"

    # Absolute coverage
    if not clean.empty:
        daily_coverage = clean.groupby("trade_date").size()
        median_cov = int(daily_coverage.median()) if len(daily_coverage) > 0 else 0
        min_cov = int(daily_coverage.min()) if len(daily_coverage) > 0 else 0

    # Missing rate
    val = clean["value"].dropna()
    missing_rate = 1.0 - (len(val) / max(clean_rows, 1))

    # Constant / extreme values
    constant_dates = 0
    if len(val) > 0:
        nun = clean.groupby("trade_date")["value"].nunique()
        constant_dates = int((nun <= 1).sum())
    extreme = (np.abs(val) > 5.0).mean() if len(val) > 0 else 0.0

    # Status determination
    max_missing_rate = 0.20  # from gate config, hard threshold
    if clean_rows == 0 or n_stocks < 10 or n_dates < 10:
        status, reason = "FAIL", "insufficient data"
    elif dupe_rate > 0.05:
        status, reason = "FAIL", f"duplicate keys rate {dupe_rate:.2%}"
    elif constant_dates > n_dates * 0.1:
        status, reason = "FAIL", f"constant on {constant_dates}/{n_dates} dates"
    elif missing_rate > max_missing_rate:
        status, reason = "FAIL", f"missing rate {missing_rate:.1%} > {max_missing_rate:.0%}"
    else:
        status, reason = "PASS", ""

    return {
        "factor": fname, "raw_rows": raw_rows, "clean_rows": clean_rows,
        "n_rows": clean_rows, "n_unique_stocks": n_stocks, "n_unique_dates": n_dates,
        "duplicate_keys": dupes, "duplicate_key_rate": round(dupe_rate, 4),
        "missing_rate": round(missing_rate, 4),
        "constant_dates": constant_dates,
        "extreme_outlier_rate": round(extreme, 4),
        "median_daily_coverage": median_cov,
        "min_daily_coverage": min_cov,
        "median_coverage_pct": round(median_coverage_pct, 4),
        "min_yearly_coverage_pct": round(min_yearly_coverage_pct, 4),
        "median_fwd_universe_size": int(median_fwd_universe_size),
        "median_overlap_count": int(median_overlap_count),
        "missing_fwd_universe_dates": missing_fwd_universe_dates,
        "coverage_status": coverage_status,
        "input_audit_status": status,
        "input_audit_reason": reason,
        "data_status": "OK" if status == "PASS" else "INPUT_FAIL",
    }


# ---------------------------------------------------------------------------
# Factor alignment — factor-level data_lag with trading calendar
# ---------------------------------------------------------------------------

def _build_aligned_panel(
    factor_cfg: dict,
    clean_df: pd.DataFrame,
    fwd: pd.DataFrame,
    horizon: str,
    cal_start: str, cal_end: str,
    val_start: str, val_end: str,
    watch_start: str, watch_end: str,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Build a leakage-free aligned panel using factor-level data_lag_days.

    Alignment rule:
        observation_date = factor.trade_date
        available_date  = observation_date + data_lag_days (calendar days)
        signal_date     = first_trading_day_on_or_after(available_date)
        forward_return  = fwd_ret(signal_date, signal_date + horizon)

    Returns:
        aligned DataFrame with [ts_code, signal_date, value, fwd_return]
        alignment audit dict
    """
    fname = factor_cfg["name"]
    data_lag_days = int(factor_cfg.get("data_lag_days", 0))
    date_semantics = factor_cfg.get("date_semantics", "observation_date")

    audit = {
        "factor": fname,
        "horizon": horizon,
        "data_lag_days": data_lag_days,
        "date_semantics": date_semantics,
        "n_observations": len(clean_df),
        "n_aligned_rows": 0,
        "n_unmatured_rows_excluded": 0,
        "n_signal_dates": 0,
        "calibration_rows": 0,
        "validation_rows": 0,
        "watch_rows": 0,
        "no_leakage_status": "NOT_AVAILABLE",
        "alignment_reason": "",
        "alignment_warning": "",
    }

    if clean_df.empty:
        audit["no_leakage_status"] = "NOT_AVAILABLE"
        audit["alignment_reason"] = "empty factor data"
        return pd.DataFrame(), audit

    if fwd.empty or horizon not in fwd.columns:
        audit["no_leakage_status"] = "NOT_AVAILABLE"
        audit["alignment_reason"] = f"forward return column {horizon} not available"
        return pd.DataFrame(), audit

    # Fundamental factors: check for potential look-ahead risk but don't auto-block.
    # date_semantics governs how available_date is computed (see below).
    if (factor_cfg.get("type") == "fundamental"
            and date_semantics == "observation_date"
            and data_lag_days == 0
            and fname != "log_market_cap_cs"):
        audit["alignment_warning"] = (
            "fundamental factor with observation_date semantics and "
            "data_lag_days=0 — potential look-ahead bias; "
            "consider setting data_lag_days>=63"
        )
        # Continue processing — don't auto-fail, but record the warning

    # Get trading calendar
    cal = _get_trading_calendar()

    # ---- Compute available_date respecting date_semantics ----
    df_copy = clean_df[["ts_code", "trade_date", "value"]].copy()

    if date_semantics == "pit_aligned":
        # PIT-aligned: trade_date IS the available_date (no additional lag)
        df_copy["available_date"] = df_copy["trade_date"]
        if data_lag_days > 0:
            audit["alignment_warning"] = (
                f"pit_aligned with data_lag_days={data_lag_days}>0 — "
                f"lag offset NOT applied; available_date = trade_date"
            )
    else:
        # observation_date (default): apply data_lag_days calendar offset
        unique_obs = df_copy["trade_date"].dropna().unique()
        avail_map = {int(d): _add_calendar_days(int(d), data_lag_days) for d in unique_obs}
        df_copy["available_date"] = df_copy["trade_date"].map(avail_map)

    if cal is None:
        # Fallback: use calendar days directly (signal_date = available_date)
        audit["alignment_reason"] = "trading calendar unavailable, using calendar-day alignment"
        df_copy["signal_date"] = df_copy["available_date"]
    else:
        unique_avail = df_copy["available_date"].dropna().unique()
        unique_avail_int = [int(a) for a in unique_avail]
        signal_map = {a: cal.first_trade_day_on_or_after(a) for a in unique_avail_int}
        df_copy["signal_date"] = df_copy["available_date"].map(signal_map)

    fwd_renamed = fwd[["ts_code", "trade_date", horizon]].rename(
        columns={"trade_date": "signal_date", horizon: "fwd_return"}
    ).copy()
    aligned = df_copy.merge(fwd_renamed, on=["ts_code", "signal_date"], how="inner")

    if aligned.empty:
        audit["no_leakage_status"] = "FAIL"
        audit["alignment_reason"] = f"no rows survive alignment (data_lag={data_lag_days}d)"
        return pd.DataFrame(), audit

    # Categorize rows by window
    cal_start_int = int(cal_start)
    cal_end_int = int(cal_end)
    val_start_int = int(val_start)
    val_end_int = int(val_end)
    watch_start_int = int(watch_start)
    watch_end_int = int(watch_end)

    aligned["_window"] = "unknown"
    aligned.loc[
        (aligned["signal_date"] >= cal_start_int) & (aligned["signal_date"] <= cal_end_int),
        "_window"
    ] = "calibration"
    aligned.loc[
        (aligned["signal_date"] >= val_start_int) & (aligned["signal_date"] <= val_end_int),
        "_window"
    ] = "validation"
    aligned.loc[
        (aligned["signal_date"] >= watch_start_int) & (aligned["signal_date"] <= watch_end_int),
        "_window"
    ] = "watch_only"

    # Leakage check: for each row, observation_date + data_lag_days must be <= signal_date
    aligned["_lag_ok"] = aligned["signal_date"] >= aligned["available_date"]
    n_unmatured = int((~aligned["_lag_ok"]).sum())
    n_aligned = int(aligned["_lag_ok"].sum())

    # Build result
    result = aligned[aligned["_lag_ok"]][["ts_code", "signal_date", "value", "fwd_return", "_window"]].copy()
    result = result.rename(columns={"signal_date": "trade_date"})

    audit["n_aligned_rows"] = n_aligned
    audit["n_unmatured_rows_excluded"] = n_unmatured
    audit["n_signal_dates"] = result["trade_date"].nunique()
    audit["calibration_rows"] = int((result["_window"] == "calibration").sum())
    audit["validation_rows"] = int((result["_window"] == "validation").sum())
    audit["watch_rows"] = int((result["_window"] == "watch_only").sum())

    # Date-range audit fields (for downstream verification of lag correctness)
    audit["min_observation_date"] = int(clean_df["trade_date"].min())
    audit["max_observation_date"] = int(clean_df["trade_date"].max())
    audit["min_available_date"] = int(df_copy["available_date"].min())
    audit["max_available_date"] = int(df_copy["available_date"].max())
    audit["min_signal_date"] = int(aligned["signal_date"].min())
    audit["max_signal_date"] = int(aligned["signal_date"].max())

    # Coverage on signal_date (aligned) — iterate over ALIGNED dates, not fwd dates
    if not fwd.empty:
        fwd_counts = (
            fwd[["ts_code", "trade_date"]]
            .drop_duplicates()
            .groupby("trade_date")
            .size()
        )
        aligned_counts = aligned.groupby("signal_date")["ts_code"].nunique()
        aligned_sizes = aligned.groupby("signal_date").size()
        signal_cov_pcts = []
        signal_yearly: dict[int, list] = {}
        # Iterate over ALIGNED dates (not fwd dates) to avoid zero-inflation
        for sd, factor_n in aligned_counts.items():
            if factor_n <= 0:
                continue
            fwd_n = int(fwd_counts.get(sd, 0))
            if fwd_n == 0:
                continue
            pct = min(factor_n / fwd_n, 1.0)
            signal_cov_pcts.append(pct)
            yr = sd // 10000
            signal_yearly.setdefault(yr, []).append(pct)
        if signal_cov_pcts:
            audit["median_coverage_pct"] = round(float(np.median(signal_cov_pcts)), 4)
        else:
            audit["median_coverage_pct"] = 0.0
        if signal_yearly:
            yearly_meds = [float(np.median(v)) for v in signal_yearly.values()]
            audit["min_yearly_coverage_pct"] = round(float(min(yearly_meds)), 4) if yearly_meds else 0.0
        else:
            audit["min_yearly_coverage_pct"] = 0.0
        audit["median_daily_coverage"] = int(aligned_sizes.median()) if len(aligned_sizes) > 0 else 0
        audit["min_daily_coverage"] = int(aligned_sizes.min()) if len(aligned_sizes) > 0 else 0
        audit["coverage_date_basis"] = "signal_date"
    else:
        audit["median_coverage_pct"] = 0.0
        audit["min_yearly_coverage_pct"] = 0.0
        audit["median_daily_coverage"] = 0
        audit["min_daily_coverage"] = 0
        audit["coverage_date_basis"] = "signal_date"
    audit["watch_rows"] = int((result["_window"] == "watch_only").sum())

    # Determine no_leakage status
    if n_aligned == 0:
        audit["no_leakage_status"] = "FAIL"
        audit["alignment_reason"] = "zero aligned rows after lag enforcement"
    elif n_unmatured > n_aligned * 0.10:
        audit["no_leakage_status"] = "FAIL"
        audit["alignment_reason"] = f"{n_unmatured}/{n_aligned + n_unmatured} rows have unmatured forward returns"
    elif audit["validation_rows"] < 50:
        audit["no_leakage_status"] = "FAIL"
        audit["alignment_reason"] = f"only {audit['validation_rows']} validation rows"
    else:
        audit["no_leakage_status"] = "PASS"
        audit["alignment_reason"] = f"lag={data_lag_days}d, {n_aligned} aligned rows"

    return result, audit


# ---------------------------------------------------------------------------
# Mcap neutralization
# ---------------------------------------------------------------------------

def _neutralize_by_mcap(
    factor_name: str,
    aligned_panel: pd.DataFrame,
    log_market_cap_panel: pd.DataFrame,
    min_coverage_pct: float = 70.0,
) -> tuple[pd.DataFrame, dict]:
    """Neutralize factor against log_market_cap_cs via OLS residual.

    For each trade_date, regress factor_value ~ const + log_market_cap_cs,
    return the residual as factor_value_mcap_neutral.

    If neutralizer coverage < min_coverage_pct on a date, that date is
    excluded from neutralization (value_mcap_neutral = NaN for that date).

    Returns:
        DataFrame with [ts_code, trade_date, value_raw, value_mcap_neutral, ...]
        meta dict with neutralization statistics
    """
    # Determine columns to preserve beyond factor values
    extra_cols = [c for c in aligned_panel.columns if c not in ("ts_code", "trade_date", "value")]

    if aligned_panel.empty or log_market_cap_panel.empty:
        keep = ["ts_code", "trade_date", "value"] + extra_cols
        result = aligned_panel[keep].copy()
        result = result.rename(columns={"value": "value_raw"})
        result["value_mcap_neutral"] = np.nan
        meta = {"neutralizer_coverage_pct": float("nan"), "size_beta_mean": float("nan"),
                "size_beta_std": float("nan"), "n_neutralized_dates": 0,
                "n_skipped_dates": 0, "skip_reason_top": "empty input"}
        return result, meta

    # Align factor with log_market_cap on (ts_code, trade_date)
    merged = aligned_panel.merge(
        log_market_cap_panel[["ts_code", "trade_date", "value"]].rename(
            columns={"value": "log_mcap"}
        ),
        on=["ts_code", "trade_date"], how="left"
    )

    # Extra columns to preserve in output (e.g. fwd_return, _window)
    extra_cols = [c for c in aligned_panel.columns if c not in ("ts_code", "trade_date", "value")]

    results = []
    daily_coverages = []
    daily_betas = []
    n_neut_dates = 0
    n_skip_dates = 0
    skip_reasons: dict[str, int] = {}

    for dt, g in merged.groupby("trade_date"):
        g = g.copy()
        n_factor = g["value"].notna().sum()
        n_mcap = g["log_mcap"].notna().sum()
        coverage = (min(n_factor, n_mcap) / max(n_factor, 1)) * 100 if n_factor > 0 else 0
        daily_coverages.append(coverage)

        g["value_raw"] = g["value"]
        g["value_mcap_neutral"] = np.nan

        if coverage >= min_coverage_pct and n_factor >= 30:
            valid = g.dropna(subset=["value", "log_mcap"])
            if len(valid) >= 30:
                try:
                    from statsmodels.api import OLS, add_constant
                    y = valid["value"].astype("float64")
                    X = add_constant(valid[["log_mcap"]].astype("float64"))
                    model = OLS(y, X).fit()
                    g.loc[valid.index, "value_mcap_neutral"] = model.resid.astype("float32")
                    # Extract size_beta (coefficient on log_mcap)
                    beta = float(model.params.get("log_mcap", 0))
                    daily_betas.append(beta)
                    n_neut_dates += 1
                except Exception:
                    n_skip_dates += 1
                    skip_reasons["regression_failed"] = skip_reasons.get("regression_failed", 0) + 1
            else:
                n_skip_dates += 1
                skip_reasons["insufficient_valid_rows"] = skip_reasons.get("insufficient_valid_rows", 0) + 1
        else:
            n_skip_dates += 1
            if coverage < min_coverage_pct:
                skip_reasons["low_coverage"] = skip_reasons.get("low_coverage", 0) + 1
            else:
                skip_reasons["insufficient_factor_rows"] = skip_reasons.get("insufficient_factor_rows", 0) + 1

        keep_cols = ["ts_code", "trade_date", "value_raw", "value_mcap_neutral"] + extra_cols
        results.append(g[keep_cols])

    # Build meta
    avg_coverage = float(np.mean(daily_coverages)) if daily_coverages else float("nan")
    median_coverage = float(np.median(daily_coverages)) if daily_coverages else float("nan")
    min_coverage = float(np.min(daily_coverages)) if daily_coverages else float("nan")
    mean_beta = float(np.mean(daily_betas)) if daily_betas else float("nan")
    std_beta = float(np.std(daily_betas, ddof=0)) if daily_betas else float("nan")
    total_dates = n_neut_dates + n_skip_dates
    skipped_pct = (n_skip_dates / total_dates * 100) if total_dates > 0 else 100.0
    top_skip = max(skip_reasons, key=skip_reasons.get) if skip_reasons else "none"
    # Real row counts (accumulated during loop above)
    raw_row_count = 0
    neut_row_count = 0
    if results:
        try:
            combined = pd.concat([r for r in results], ignore_index=True)
            raw_row_count = int(combined["value_raw"].notna().sum())
            neut_row_count = int(combined["value_mcap_neutral"].notna().sum())
        except Exception:
            raw_row_count = total_dates
            neut_row_count = n_neut_dates

    meta = {
        "neutralizer_coverage_pct": round(avg_coverage, 2),
        "neutralizer_coverage_median_pct": round(median_coverage, 2),
        "neutralizer_coverage_min_pct": round(min_coverage, 2),
        "size_beta_mean": round(mean_beta, 4),
        "size_beta_std": round(std_beta, 4),
        "n_neutralized_dates": n_neut_dates,
        "n_skipped_dates": n_skip_dates,
        "skipped_date_pct": round(skipped_pct, 2),
        "skip_reason_top": top_skip,
        "neutralized_row_count": neut_row_count,
        "raw_row_count": raw_row_count,
        "neutralized_row_coverage_pct": round(neut_row_count / max(raw_row_count, 1) * 100, 2),
    }

    if not results:
        keep = ["ts_code", "trade_date", "value"] + extra_cols
        result = aligned_panel[keep].copy()
        result = result.rename(columns={"value": "value_raw"})
        result["value_mcap_neutral"] = np.nan
        return result, meta

    return pd.concat(results, ignore_index=True), meta


# ---------------------------------------------------------------------------
# Direction audit
# ---------------------------------------------------------------------------

def _audit_factor_direction(
    factor_cfg: dict, aligned_panel: pd.DataFrame,
    cal_start: str, cal_end: str,
    value_col: str = "value_raw",
) -> dict[str, Any]:
    """Determine the correct sign for a factor using calibration window."""
    sign_hint = factor_cfg.get("sign_hint", "positive")
    original_sign = 1 if sign_hint == "positive" else -1

    if aligned_panel.empty or value_col not in aligned_panel.columns:
        return {
            "factor": factor_cfg["name"],
            "calibration_mean_ic_original": float("nan"),
            "calibration_mean_ic_reversed": float("nan"),
            "selected_direction": "original",
            "direction_flipped": False,
            "direction_audit_status": "FAIL",
            "direction_audit_reason": f"no usable aligned data for {value_col}",
        }

    cal_start_int, cal_end_int = int(cal_start), int(cal_end)
    cal_data = aligned_panel[
        (aligned_panel["trade_date"] >= cal_start_int) &
        (aligned_panel["trade_date"] <= cal_end_int)
    ].dropna(subset=[value_col, "fwd_return"])

    if cal_data.empty or len(cal_data) < 100:
        return {
            "factor": factor_cfg["name"],
            "calibration_mean_ic_original": float("nan"),
            "calibration_mean_ic_reversed": float("nan"),
            "selected_direction": "original",
            "direction_flipped": False,
            "direction_audit_status": "FAIL",
            "direction_audit_reason": "insufficient calibration data",
        }

    daily_ic_orig = cal_data.groupby("trade_date").apply(
        lambda g: _rank_ic(g[value_col] * original_sign, g["fwd_return"])
    ).dropna()
    mean_ic_orig = float(daily_ic_orig.mean()) if len(daily_ic_orig) > 0 else float("nan")

    daily_ic_rev = cal_data.groupby("trade_date").apply(
        lambda g: _rank_ic(g[value_col] * (-original_sign), g["fwd_return"])
    ).dropna()
    mean_ic_rev = float(daily_ic_rev.mean()) if len(daily_ic_rev) > 0 else float("nan")

    if np.isnan(mean_ic_orig) and np.isnan(mean_ic_rev):
        selected, flipped, status, reason = "original", False, "FAIL", "both directions NaN"
    elif np.isnan(mean_ic_rev) or mean_ic_orig >= mean_ic_rev:
        selected, flipped = "original", False
    else:
        selected, flipped = "reversed", True

    status = "PASS" if not np.isnan(mean_ic_orig) else "FAIL"
    reason = "" if status == "PASS" else "no valid IC in calibration"

    return {
        "factor": factor_cfg["name"],
        "calibration_mean_ic_original": mean_ic_orig,
        "calibration_mean_ic_reversed": mean_ic_rev,
        "selected_direction": selected,
        "direction_flipped": flipped,
        "direction_audit_status": status,
        "direction_audit_reason": reason,
    }


# ---------------------------------------------------------------------------
# IC by year (with basis)
# ---------------------------------------------------------------------------

def _compute_ic_by_year(
    factor_cfg: dict, aligned_panel: pd.DataFrame,
    direction_info: dict, years: list[int],
    value_col: str, basis: str,
) -> list[dict[str, Any]]:
    """Compute IC statistics per year for a given value column."""
    sign = -1 if direction_info.get("direction_flipped", False) else 1
    sign_hint = factor_cfg.get("sign_hint", "positive")
    original_sign = 1 if sign_hint == "positive" else -1
    mult = original_sign * sign

    if aligned_panel.empty or value_col not in aligned_panel.columns:
        rows = []
        for year in years:
            rows.append({
                "factor": factor_cfg["name"], "year": year, "basis": basis,
                "n_dates": 0, "mean_rank_ic": float("nan"), "mean_pearson_ic": float("nan"),
                "icir": float("nan"), "hit_rate": float("nan"), "ic_std": float("nan"),
            })
        return rows

    merged = aligned_panel.dropna(subset=[value_col, "fwd_return"]).copy()

    rows = []
    for year in years:
        ydf = merged[(merged["trade_date"] >= year * 10000) & (merged["trade_date"] < (year + 1) * 10000)]
        daily_ic = ydf.groupby("trade_date").apply(
            lambda g: _rank_ic(g[value_col] * mult, g["fwd_return"])
        ).dropna()

        if len(daily_ic) == 0:
            rows.append({
                "factor": factor_cfg["name"], "year": year, "basis": basis,
                "n_dates": 0, "mean_rank_ic": float("nan"), "mean_pearson_ic": float("nan"),
                "icir": float("nan"), "hit_rate": float("nan"), "ic_std": float("nan"),
            })
            continue

        daily_pearson = ydf.groupby("trade_date").apply(
            lambda g: _pearson_ic(g[value_col] * mult, g["fwd_return"])
        ).dropna()

        mean_ric = float(daily_ic.mean())
        ic_std = float(daily_ic.std(ddof=0))
        icir = mean_ric / ic_std if ic_std and ic_std > 0 else float("nan")
        hit_rate = float((daily_ic > 0).mean())

        rows.append({
            "factor": factor_cfg["name"], "year": year, "basis": basis,
            "n_dates": len(daily_ic),
            "mean_rank_ic": mean_ric,
            "mean_pearson_ic": float(daily_pearson.mean()) if len(daily_pearson) > 0 else float("nan"),
            "icir": icir, "hit_rate": hit_rate, "ic_std": ic_std,
        })

    return rows


# ---------------------------------------------------------------------------
# Quantile portfolios and real turnover cost
# ---------------------------------------------------------------------------

def _compute_quantile_portfolios(
    factor_cfg: dict, aligned_panel: pd.DataFrame,
    direction_info: dict, value_col: str,
    weighting: str = "equal_weight",
    daily_basic: Optional[pd.DataFrame] = None,
) -> list[dict[str, Any]]:
    """Compute top/bottom quintile portfolio weights per signal_date.

    Returns list of per-date dicts with:
        signal_date, top_names, bottom_names, top_weights, bottom_weights
    """
    sign = -1 if direction_info.get("direction_flipped", False) else 1
    sign_hint = factor_cfg.get("sign_hint", "positive")
    original_sign = 1 if sign_hint == "positive" else -1
    mult = original_sign * sign

    if aligned_panel.empty or value_col not in aligned_panel.columns:
        return []

    merged = aligned_panel.dropna(subset=[value_col, "fwd_return"]).copy()
    if merged.empty:
        return []

    n_q = 5
    portfolios = []

    for dt, g in merged.groupby("trade_date"):
        g = g.copy()
        g["score"] = g[value_col] * mult
        try:
            g["quantile"] = pd.qcut(g["score"], n_q, labels=False, duplicates="drop")
        except Exception:
            continue

        top_idx = g["quantile"] == (n_q - 1)
        bot_idx = g["quantile"] == 0
        if not top_idx.any() or not bot_idx.any():
            continue

        top_names = set(g.loc[top_idx, "ts_code"].tolist())
        bot_names = set(g.loc[bot_idx, "ts_code"].tolist())

        # Build weights
        if weighting == "mcap_weight" and daily_basic is not None and not daily_basic.empty:
            db_date = daily_basic[daily_basic["trade_date"] == dt]
            if not db_date.empty:
                top_mcap = db_date[db_date["ts_code"].isin(top_names)]
                bot_mcap = db_date[db_date["ts_code"].isin(bot_names)]
                if "total_mv" in top_mcap.columns and not top_mcap.empty:
                    top_w = top_mcap.set_index("ts_code")["total_mv"]
                    top_w = top_w / top_w.sum()
                else:
                    top_w = pd.Series(1.0 / len(top_names), index=list(top_names))
                if "total_mv" in bot_mcap.columns and not bot_mcap.empty:
                    bot_w = bot_mcap.set_index("ts_code")["total_mv"]
                    bot_w = bot_w / bot_w.sum()
                else:
                    bot_w = pd.Series(1.0 / len(bot_names), index=list(bot_names))
            else:
                top_w = pd.Series(1.0 / len(top_names), index=list(top_names))
                bot_w = pd.Series(1.0 / len(bot_names), index=list(bot_names))
        else:
            top_w = pd.Series(1.0 / len(top_names), index=list(top_names))
            bot_w = pd.Series(1.0 / len(bot_names), index=list(bot_names))

        portfolios.append({
            "signal_date": dt,
            "top_names": top_names,
            "bottom_names": bot_names,
            "top_weights": top_w,
            "bottom_weights": bot_w,
        })

    return portfolios


def _compute_real_turnover_cost(
    factor_cfg: dict,
    portfolios: list[dict],
    fwd: pd.DataFrame,
    aligned_panel: pd.DataFrame,
    direction_info: dict,
    years: list[int],
    value_col: str,
    basis: str,
    weighting: str,
    cost_bps: float,
) -> list[dict[str, Any]]:
    """Compute real turnover and cost from portfolio weight changes.

    If fwd_ret_1d is available:
        drifted_w = normalize(w_t * (1 + ret_1d))
        turnover = sum(|drifted_w - w_next|) / 2
    Else:
        overlap_ratio = |names_t ∩ names_{t+1}| / |names_t ∪ names_{t+1}|
        turnover_proxy = 1 - overlap_ratio
    """
    sign = -1 if direction_info.get("direction_flipped", False) else 1
    sign_hint = factor_cfg.get("sign_hint", "positive")
    original_sign = 1 if sign_hint == "positive" else -1
    mult = original_sign * sign

    n_q = 5
    has_fwd_1d = "fwd_ret_1d" in fwd.columns

    if not portfolios:
        return []

    # Pre-compute gross quantile returns per date
    merged = aligned_panel.dropna(subset=[value_col, "fwd_return"]).copy()
    if merged.empty:
        return []

    # Build date → gross_spread mapping
    date_spreads = {}
    for dt, g in merged.groupby("trade_date"):
        g = g.copy()
        g["score"] = g[value_col] * mult
        try:
            g["quantile"] = pd.qcut(g["score"], n_q, labels=False, duplicates="drop")
        except Exception:
            continue
        q_mean = g.groupby("quantile")["fwd_return"].mean()
        if len(q_mean) >= n_q:
            top_q = q_mean.get(n_q - 1, float("nan"))
            bot_q = q_mean.get(0, float("nan"))
            date_spreads[dt] = top_q - bot_q

    # Compute turnover per consecutive pair
    turnover_rows: dict[int, list] = {}  # year → list of per-period turnover

    for i in range(len(portfolios) - 1):
        p_curr = portfolios[i]
        p_next = portfolios[i + 1]
        dt_curr = p_curr["signal_date"]
        dt_next = p_next["signal_date"]
        year = dt_curr // 10000

        if has_fwd_1d:
            # Real weight drift turnover
            fwd_date = fwd[fwd["trade_date"] == dt_curr]
            top_to_long = 0.0
            top_to_short = 0.0

            if not fwd_date.empty:
                fwd_map = fwd_date.set_index("ts_code")["fwd_ret_1d"].to_dict()

                # Long leg (top quintile)
                top_w_curr = p_curr["top_weights"].copy()
                drifted = {}
                for name, w in top_w_curr.items():
                    ret = fwd_map.get(name, 0.0)
                    drifted[name] = w * (1.0 + ret)
                total = sum(drifted.values())
                if total > 0:
                    drifted = {k: v / total for k, v in drifted.items()}

                top_w_next = p_next["top_weights"]
                all_names = set(list(drifted.keys()) + list(top_w_next.index))
                for name in all_names:
                    w_d = drifted.get(name, 0.0)
                    w_n = top_w_next.get(name, 0.0)
                    top_to_long += abs(w_d - w_n)

                # Short leg (bottom quintile)
                bot_w_curr = p_curr["bottom_weights"].copy()
                drifted_bot = {}
                for name, w in bot_w_curr.items():
                    ret = fwd_map.get(name, 0.0)
                    drifted_bot[name] = w * (1.0 + ret)
                total_bot = sum(drifted_bot.values())
                if total_bot > 0:
                    drifted_bot = {k: v / total_bot for k, v in drifted_bot.items()}

                bot_w_next = p_next["bottom_weights"]
                all_names_bot = set(list(drifted_bot.keys()) + list(bot_w_next.index))
                for name in all_names_bot:
                    w_d = drifted_bot.get(name, 0.0)
                    w_n = bot_w_next.get(name, 0.0)
                    top_to_short += abs(w_d - w_n)

            turnover_long = top_to_long / 2
            turnover_short = top_to_short / 2
            total_turnover = turnover_long + turnover_short
            method = "REAL_WEIGHT_DRIFT"
        else:
            # Overlap proxy
            top_overlap = len(p_curr["top_names"] & p_next["top_names"])
            top_union = len(p_curr["top_names"] | p_next["top_names"])
            bot_overlap = len(p_curr["bottom_names"] & p_next["bottom_names"])
            bot_union = len(p_curr["bottom_names"] | p_next["bottom_names"])

            top_turnover = 1.0 - (top_overlap / max(top_union, 1))
            bot_turnover = 1.0 - (bot_overlap / max(bot_union, 1))
            turnover_long = top_turnover
            turnover_short = bot_turnover
            total_turnover = (top_turnover + bot_turnover)
            method = "OVERLAP_PROXY"

        gross_spread = date_spreads.get(dt_curr, float("nan"))
        est_cost = total_turnover * cost_bps / 10000
        net_spread = gross_spread - est_cost if not np.isnan(gross_spread) else float("nan")

        turnover_rows.setdefault(year, []).append({
            "turnover_long": turnover_long,
            "turnover_short": turnover_short,
            "total_turnover": total_turnover,
            "gross_spread": gross_spread,
            "estimated_cost": est_cost,
            "net_spread": net_spread,
            "method": method,
        })

    # Aggregate by year
    rows = []
    for year in years:
        if year not in turnover_rows or not turnover_rows[year]:
            rows.append({
                "factor": factor_cfg["name"], "year": year, "basis": basis,
                "weighting": weighting,
                "avg_turnover_long": float("nan"),
                "avg_turnover_short": float("nan"),
                "avg_total_turnover": float("nan"),
                "gross_spread": float("nan"),
                "estimated_cost": float("nan"),
                "net_spread": float("nan"),
                "net_gross_ratio": float("nan"),
                "turnover_method": "NOT_AVAILABLE",
            })
            continue

        tr = turnover_rows[year]
        avg_tl = float(np.mean([r["turnover_long"] for r in tr]))
        avg_ts = float(np.mean([r["turnover_short"] for r in tr]))
        avg_tt = float(np.mean([r["total_turnover"] for r in tr]))
        avg_gs = float(np.nanmean([r["gross_spread"] for r in tr]))
        avg_cost = float(np.mean([r["estimated_cost"] for r in tr]))
        avg_ns = float(np.nanmean([r["net_spread"] for r in tr]))
        ratio = avg_ns / avg_gs if avg_gs and avg_gs != 0 else float("nan")
        method = tr[0]["method"]

        rows.append({
            "factor": factor_cfg["name"], "year": year, "basis": basis,
            "weighting": weighting,
            "avg_turnover_long": round(avg_tl, 4),
            "avg_turnover_short": round(avg_ts, 4),
            "avg_total_turnover": round(avg_tt, 4),
            "gross_spread": round(avg_gs, 6),
            "estimated_cost": round(avg_cost, 6),
            "net_spread": round(avg_ns, 6),
            "net_gross_ratio": round(ratio, 4) if not np.isnan(ratio) else float("nan"),
            "turnover_method": method,
        })

    return rows


# ---------------------------------------------------------------------------
# Quantile returns (for IC + simple quantile metrics, used in gate)
# ---------------------------------------------------------------------------

def _compute_quantile_returns(
    factor_cfg: dict, aligned_panel: pd.DataFrame,
    direction_info: dict, years: list[int],
    value_col: str, basis: str,
    cost_bps: float, turnover_rows: Optional[list[dict]] = None,
) -> list[dict[str, Any]]:
    """Compute quantile returns (5 groups) per year with real turnover cost."""
    sign = -1 if direction_info.get("direction_flipped", False) else 1
    sign_hint = factor_cfg.get("sign_hint", "positive")
    original_sign = 1 if sign_hint == "positive" else -1
    mult = original_sign * sign

    if aligned_panel.empty or value_col not in aligned_panel.columns:
        return []

    merged = aligned_panel.dropna(subset=[value_col, "fwd_return"]).copy()
    if merged.empty:
        return []

    n_q = 5

    # Build turnover lookup: year → avg_total_turnover
    year_turnover: dict[int, float] = {}
    if turnover_rows:
        for tr in turnover_rows:
            if tr["factor"] == factor_cfg["name"] and tr["basis"] == basis:
                yr = tr["year"]
                t = tr["avg_total_turnover"]
                if not np.isnan(t):
                    year_turnover[yr] = t

    rows = []
    for year in years:
        ydf = merged[(merged["trade_date"] >= year * 10000) & (merged["trade_date"] < (year + 1) * 10000)]
        if ydf.empty:
            continue

        q_returns = []
        dates_processed = 0
        for dt, g in ydf.groupby("trade_date"):
            g = g.copy()
            g["score"] = g[value_col] * mult
            try:
                g["quantile"] = pd.qcut(g["score"], n_q, labels=False, duplicates="drop")
            except Exception:
                continue
            q_mean = g.groupby("quantile")["fwd_return"].mean()
            if len(q_mean) < n_q:
                continue
            q_returns.append(q_mean.to_dict())
            dates_processed += 1

        if not q_returns:
            continue

        q_df = pd.DataFrame(q_returns)
        q_avg = q_df.mean()
        top_q = q_avg.get(n_q - 1, float("nan"))
        bottom_q = q_avg.get(0, float("nan"))
        gross_spread = top_q - bottom_q

        # Use real turnover if available, otherwise fall back
        est_turnover = year_turnover.get(year, 0.20)
        net_spread = gross_spread - (est_turnover * 2 * cost_bps / 10000)

        mono_ok = True
        for i in range(n_q - 1):
            if q_avg.get(i, float("-inf")) > q_avg.get(i + 1, float("inf")):
                mono_ok = False
                break

        rows.append({
            "factor": factor_cfg["name"], "year": year, "basis": basis,
            "n_dates": dates_processed,
            "top_quintile_return": top_q,
            "bottom_quintile_return": bottom_q,
            "gross_spread": gross_spread,
            "net_spread": net_spread,
            "top_quintile_net_excess": top_q - (est_turnover * cost_bps / 10000),
            "monotonic": mono_ok,
            "turnover_estimate": est_turnover,
            "cost_bps_assumption": cost_bps,
        })

    return rows


# ---------------------------------------------------------------------------
# IC Trend
# ---------------------------------------------------------------------------

def _compute_ic_trend(
    factor_name: str,
    aligned_panel: pd.DataFrame,
    direction_info: dict,
    value_col: str,
    basis: str,
    val_start: str, val_end: str,
    p_value_threshold: float = 0.10,
) -> dict[str, Any]:
    """Compute IC trend over validation window via linear regression on monthly IC."""
    sign = -1 if direction_info.get("direction_flipped", False) else 1
    sign_hint = "positive"
    original_sign = 1
    mult = original_sign * sign

    result = {
        "factor": factor_name, "basis": basis,
        "monthly_ic_count": 0, "ic_trend_slope": float("nan"),
        "ic_trend_p_value": float("nan"), "ic_declining": False,
    }

    if aligned_panel.empty or value_col not in aligned_panel.columns:
        return result

    val_start_int, val_end_int = int(val_start), int(val_end)
    merged = aligned_panel[
        (aligned_panel["trade_date"] >= val_start_int) &
        (aligned_panel["trade_date"] <= val_end_int)
    ].dropna(subset=[value_col, "fwd_return"]).copy()

    if merged.empty or len(merged) < 100:
        return result

    merged["month"] = merged["trade_date"] // 100
    monthly_ic = merged.groupby("month").apply(
        lambda g: _rank_ic(g[value_col] * mult, g["fwd_return"])
    ).dropna()

    if len(monthly_ic) < 12:
        return {**result, "monthly_ic_count": len(monthly_ic)}

    try:
        slope, intercept, r_value, p_value, _ = linregress(
            range(len(monthly_ic)), monthly_ic.values
        )
        declining = bool(slope < 0 and p_value < p_value_threshold)
        return {
            "factor": factor_name, "basis": basis,
            "monthly_ic_count": len(monthly_ic),
            "ic_trend_slope": round(slope, 6),
            "ic_trend_p_value": round(p_value, 4),
            "ic_declining": declining,
        }
    except Exception:
        return {**result, "monthly_ic_count": len(monthly_ic)}


# ---------------------------------------------------------------------------
# Rolling window robustness
# ---------------------------------------------------------------------------

def _compute_rolling_window_gate(
    factor_cfg: dict,
    ic_rows_all: list[dict],
    quantile_rows_all: list[dict],
    direction_info: dict,
    rolling_windows: list[dict],
    gate_cfg: dict,
) -> list[dict[str, Any]]:
    """Compute gate results across multiple rolling validation windows."""
    fname = factor_cfg["name"]
    results = []

    for rw in rolling_windows:
        w_name = rw["name"]
        w_start = int(rw["start"])
        w_end = int(rw["end"])
        w_years = list(range(w_start // 10000, w_end // 10000 + 1))

        # Compute gate for this window
        w_ic = [r for r in ic_rows_all
                if r["factor"] == fname and r["year"] in w_years]
        w_q = [r for r in quantile_rows_all
               if r["factor"] == fname and r["year"] in w_years]

        # Simplified gate for window: check IC + quantile criteria
        failures = []
        val_ic = [r for r in w_ic if r["basis"] == "raw"]
        val_q = [r for r in w_q if r["basis"] == "raw"]

        if val_ic:
            mean_ic = float(np.nanmean([r["mean_rank_ic"] for r in val_ic]))
            mean_icir = float(np.nanmean([r["icir"] for r in val_ic]))
            pos_years = sum(1 for r in val_ic if not np.isnan(r["mean_rank_ic"]) and r["mean_rank_ic"] > 0)

            if np.isnan(mean_ic) or mean_ic < gate_cfg.get("min_mean_rank_ic", 0.01):
                failures.append(f"mean_rank_ic={_num(mean_ic)}")
            if np.isnan(mean_icir) or mean_icir < gate_cfg.get("min_icir", 0.20):
                failures.append(f"icir={_num(mean_icir)}")
            if pos_years < gate_cfg.get("min_positive_ic_years", max(1, len(w_years) - 1)):
                failures.append(f"pos_ic_years={pos_years}/{len(w_years)}")
        else:
            failures.append("no IC data")

        if val_q:
            net_spreads = [r["net_spread"] for r in val_q if not np.isnan(r["net_spread"])]
            pos_spread_yrs = sum(1 for s in net_spreads if s > 0)
            mean_ns = float(np.nanmean(net_spreads)) if net_spreads else float("nan")

            if np.isnan(mean_ns) or mean_ns <= 0:
                failures.append(f"net_spread={_num(mean_ns)}")
            if pos_spread_yrs < gate_cfg.get("min_positive_spread_years", max(1, len(w_years) - 1)):
                failures.append(f"pos_spread_years={pos_spread_yrs}/{len(w_years)}")

        status = "PASS" if not failures else "FAIL"

        results.append({
            "factor": fname, "window": w_name, "basis": "raw",
            "window_start": rw["start"], "window_end": rw["end"],
            "primary": rw.get("primary", False),
            "window_years": len(w_years),
            "window_gate_status": status,
            "mean_ic": float(np.nanmean([r["mean_rank_ic"] for r in val_ic])) if val_ic else float("nan"),
            "icir": float(np.nanmean([r["icir"] for r in val_ic])) if val_ic else float("nan"),
            "net_spread": float(np.nanmean([r["net_spread"] for r in val_q])) if val_q else float("nan"),
            "positive_ic_years": sum(1 for r in val_ic if not np.isnan(r["mean_rank_ic"]) and r["mean_rank_ic"] > 0) if val_ic else 0,
            "positive_spread_years": sum(1 for r in val_q if not np.isnan(r["net_spread"]) and r["net_spread"] > 0) if val_q else 0,
            "failure_reasons": "; ".join(failures),
        })

    return results


# ---------------------------------------------------------------------------
# Capacity / liquidity audit
# ---------------------------------------------------------------------------

def _market_cap_cny(series: pd.Series, capacity_cfg: dict) -> pd.Series:
    """Convert market cap to CNY based on config unit."""
    unit = capacity_cfg.get("daily_basic_mv_unit", "wan_cny")
    if unit == "wan_cny":
        return series * 10000.0
    elif unit in ("cny", "yuan"):
        return series
    return series * 10000.0  # default Tushare万元


def _daily_basic_amount_cny(db_date: pd.DataFrame, capacity_cfg: dict) -> pd.Series:
    """Estimate daily trading amount in CNY, respecting config unit settings."""
    amount_unit = capacity_cfg.get("amount_unit", "derived_from_circ_mv")

    if amount_unit == "derived_from_circ_mv":
        if "circ_mv" in db_date.columns and "turnover_rate" in db_date.columns:
            circ_cny = _market_cap_cny(db_date["circ_mv"], capacity_cfg)
            return circ_cny * db_date["turnover_rate"] / 100.0
        return pd.Series(np.nan, index=db_date.index)

    # Direct amount column mode
    amount_col = capacity_cfg.get("amount_column")
    if amount_col and amount_col in db_date.columns:
        return _convert_amount_to_cny(db_date[amount_col], amount_unit)
    for col in ["amount", "total_amount"]:
        if col in db_date.columns:
            return _convert_amount_to_cny(db_date[col], amount_unit)
    # Fallback to derived
    if "circ_mv" in db_date.columns and "turnover_rate" in db_date.columns:
        circ_cny = _market_cap_cny(db_date["circ_mv"], capacity_cfg)
        return circ_cny * db_date["turnover_rate"] / 100.0
    return pd.Series(np.nan, index=db_date.index)


def _convert_amount_to_cny(series: pd.Series, amount_unit: str) -> pd.Series:
    """Convert a direct amount column to CNY."""
    if amount_unit in ("cny", "yuan"):
        return series
    if amount_unit == "thousand_cny":
        return series * 1000.0
    if amount_unit == "wan_cny":
        return series * 10000.0
    raise ValueError(f"Unsupported amount_unit: {amount_unit}")


def _compute_capacity_audit(
    factor_cfg: dict,
    aligned_panel: pd.DataFrame,
    direction_info: dict,
    value_col: str,
    basis: str,
    daily_basic: pd.DataFrame,
    years: list[int],
    capacity_cfg: dict,
    weighting: str = "equal_weight",
    daily_basic_by_date: Optional[dict] = None,
) -> list[dict[str, Any]]:
    """Screen top/bottom quantile stocks for liquidity and capacity."""
    if aligned_panel.empty or daily_basic.empty:
        return []

    target_aum = float(capacity_cfg.get("target_aum_cny", 1_000_000_000))
    max_participation = float(capacity_cfg.get("max_participation_rate", 0.05))
    min_median_amount = float(capacity_cfg.get("min_median_amount_cny", 20_000_000))

    sign = -1 if direction_info.get("direction_flipped", False) else 1
    sign_hint = factor_cfg.get("sign_hint", "positive")
    original_sign = 1 if sign_hint == "positive" else -1
    mult = original_sign * sign

    merged = aligned_panel.dropna(subset=[value_col, "fwd_return"]).copy()
    if merged.empty:
        return []

    n_q = 5
    rows = []

    for year in years:
        ydf = merged[(merged["trade_date"] >= year * 10000) & (merged["trade_date"] < (year + 1) * 10000)]
        if ydf.empty:
            continue

        top_amounts: list[float] = []
        bot_amounts: list[float] = []
        top_mcaps: list[float] = []
        bot_mcaps: list[float] = []
        top_amount_sums: list[float] = []  # daily total amount for top leg
        bot_amount_sums: list[float] = []
        top_counts: list[int] = []
        bot_counts: list[int] = []

        for dt, g in ydf.groupby("trade_date"):
            g = g.copy()
            g["score"] = g[value_col] * mult
            try:
                g["quantile"] = pd.qcut(g["score"], n_q, labels=False, duplicates="drop")
            except Exception:
                continue

            top_codes = g.loc[g["quantile"] == n_q - 1, "ts_code"].tolist()
            bot_codes = g.loc[g["quantile"] == 0, "ts_code"].tolist()

            db_date = daily_basic_by_date.get(int(dt)) if daily_basic_by_date else None
            if db_date is None:
                db_date = daily_basic[daily_basic["trade_date"] == dt]
            if db_date is None or (hasattr(db_date, 'empty') and db_date.empty):
                continue

            # Estimate daily amount per stock using unified CNY conversion
            db_date = db_date.copy()
            db_date["_amount_cny"] = _daily_basic_amount_cny(db_date, capacity_cfg)
            top_amt_series = db_date[db_date["ts_code"].isin(top_codes)]["_amount_cny"].dropna()
            bot_amt_series = db_date[db_date["ts_code"].isin(bot_codes)]["_amount_cny"].dropna()
            if not top_amt_series.empty:
                top_amounts.extend(top_amt_series.tolist())
                top_amount_sums.append(float(top_amt_series.sum()))
            if not bot_amt_series.empty:
                bot_amounts.extend(bot_amt_series.tolist())
                bot_amount_sums.append(float(bot_amt_series.sum()))

            if "total_mv" in db_date.columns:
                # Tushare total_mv is in 万元 — convert to CNY
                mv_unit = capacity_cfg.get("daily_basic_mv_unit", "wan_cny")
                mv_mult = 10000 if mv_unit == "wan_cny" else 1
                top_mv = db_date[db_date["ts_code"].isin(top_codes)]["total_mv"].dropna() * mv_mult
                bot_mv = db_date[db_date["ts_code"].isin(bot_codes)]["total_mv"].dropna() * mv_mult
                if not top_mv.empty:
                    top_mcaps.extend(top_mv.tolist())
                if not bot_mv.empty:
                    bot_mcaps.extend(bot_mv.tolist())

            top_counts.append(len(top_codes))
            bot_counts.append(len(bot_codes))

        if not top_amount_sums and not top_amounts:
            status = "NOT_AVAILABLE"
            reason = "no daily_basic data for this year"
            med_top_amt = float("nan")
            med_bot_amt = float("nan")
            med_top_mcap = float("nan")
            med_bot_mcap = float("nan")
            med_mcap = float("nan")
            med_leg_sum = float("nan")
            med_top_count = float("nan")
            participation = float("nan")
            est_capacity = float("nan")
            assumed_turnover = float(capacity_cfg.get("assumed_daily_turnover", 0.05))
            required_trade = target_aum * assumed_turnover
        else:
            med_top_amt = float(np.median(top_amounts)) if top_amounts else float("nan")
            med_bot_amt = float(np.median(bot_amounts)) if bot_amounts else float("nan")
            med_top_mcap = float(np.median(top_mcaps)) if top_mcaps else float("nan")
            med_bot_mcap = float(np.median(bot_mcaps)) if bot_mcaps else float("nan")
            med_mcap = float(np.median(top_mcaps + bot_mcaps)) if (top_mcaps or bot_mcaps) else float("nan")

            # Capacity estimation using daily leg amount sum
            med_top_sum = float(np.median(top_amount_sums)) if top_amount_sums else float("nan")
            med_bot_sum = float(np.median(bot_amount_sums)) if bot_amount_sums else float("nan")
            med_leg_sum = float(np.nanmin([med_top_sum, med_bot_sum])) if not np.isnan(med_top_sum) and not np.isnan(med_bot_sum) else med_top_sum
            med_top_count = float(np.median(top_counts)) if top_counts else float("nan")

            # Participation: required trade / available liquidity
            assumed_turnover = float(capacity_cfg.get("assumed_daily_turnover", 0.05))
            required_trade = target_aum * assumed_turnover
            participation = required_trade / max(med_leg_sum, 1) if not np.isnan(med_leg_sum) else float("nan")

            # Estimated capacity: max AUM given constraints
            est_capacity = med_leg_sum * max_participation / max(assumed_turnover, 0.001) if not np.isnan(med_leg_sum) else float("nan")

            # Status: single-stock liquidity check + portfolio capacity check
            if np.isnan(med_top_amt) or med_top_amt < min_median_amount:
                status = "FAIL"
                reason = f"single_stock_liquidity: median_top_amount={med_top_amt:.0f} < {min_median_amount:.0f}"
            elif not np.isnan(participation) and participation > max_participation:
                status = "WATCH"
                reason = f"portfolio_participation: {participation:.2%} > {max_participation:.0%} at {target_aum:.0e} AUM"
            else:
                status = "PASS"
                reason = f"capacity ok, participation={participation:.2%}, est_capacity={est_capacity:.0f} CNY"

        rows.append({
            "factor": factor_cfg["name"], "year": year, "basis": basis,
            "median_top_amount_cny": round(med_top_amt, 0) if not np.isnan(med_top_amt) else float("nan"),
            "median_bottom_amount_cny": round(med_bot_amt, 0) if not np.isnan(med_bot_amt) else float("nan"),
            "median_top_market_cap_cny": round(med_top_mcap, 0) if not np.isnan(med_top_mcap) else float("nan"),
            "median_bottom_market_cap_cny": round(med_bot_mcap, 0) if not np.isnan(med_bot_mcap) else float("nan"),
            "median_market_cap_cny": round(med_mcap, 0) if not np.isnan(med_mcap) else float("nan"),
            "median_top_count": round(med_top_count, 1) if not np.isnan(med_top_count) else float("nan"),
            "median_leg_amount_sum_cny": round(med_leg_sum, 0) if not np.isnan(med_leg_sum) else float("nan"),
            "assumed_daily_turnover": assumed_turnover,
            "estimated_trade_cny_at_target_aum": round(required_trade, 0),
            "participation_rate_at_target_aum": round(participation, 4) if not np.isnan(participation) else float("nan"),
            "estimated_capacity_cny": round(est_capacity, 0) if not np.isnan(est_capacity) else float("nan"),
            "capacity_status": status,
            "capacity_reason": reason,
        })

    return rows


# ---------------------------------------------------------------------------
# Regime breakdown
# ---------------------------------------------------------------------------

def _compute_regime_breakdown(
    factor_cfg: dict,
    aligned_panel: pd.DataFrame,
    direction_info: dict,
    value_col: str,
    basis: str,
    years: list[int],
) -> list[dict[str, Any]]:
    """Map factor performance to market regimes from phase2_regime_probs.parquet."""
    fname = factor_cfg["name"]

    if aligned_panel.empty:
        return [{"factor": fname, "basis": basis, "regime": "ALL",
                 "n_dates": 0, "mean_ic": float("nan"),
                 "mean_net_spread": float("nan"),
                 "regime_status": "NOT_AVAILABLE"}]

    # Scan for regime files
    regime_root = ROOT / "outputs" / "runs"
    regime_files = list(regime_root.glob("*/diagnostics/phase2_regime_probs.parquet"))
    if not regime_files:
        return [{"factor": fname, "basis": basis, "regime": "ALL",
                 "n_dates": 0, "mean_ic": float("nan"),
                 "mean_net_spread": float("nan"),
                 "regime_status": "NOT_AVAILABLE"}]

    # Load and aggregate regime data across all runs
    regime_chunks = []
    for rf in regime_files:
        try:
            rp = pd.read_parquet(rf)
            rp.columns = [str(c).strip().lower() for c in rp.columns]
            regime_chunks.append(rp)
        except Exception:
            continue

    if not regime_chunks:
        return [{"factor": fname, "basis": basis, "regime": "ALL",
                 "n_dates": 0, "mean_ic": float("nan"),
                 "mean_net_spread": float("nan"),
                 "regime_status": "NOT_AVAILABLE"}]

    regime_df = pd.concat(regime_chunks, ignore_index=True)
    regime_df = regime_df.drop_duplicates(subset=["trade_date"])

    if "trade_date" not in regime_df.columns:
        return [{"factor": fname, "basis": basis, "regime": "ALL",
                 "n_dates": 0, "mean_ic": float("nan"),
                 "mean_net_spread": float("nan"),
                 "regime_status": "NOT_AVAILABLE"}]

    # Find dominant regime per date
    prob_cols = [c for c in regime_df.columns
                 if c.endswith("_prob") and c != "trade_date"]
    if not prob_cols:
        return [{"factor": fname, "basis": basis, "regime": "ALL",
                 "n_dates": 0, "mean_ic": float("nan"),
                 "mean_net_spread": float("nan"),
                 "regime_status": "NOT_AVAILABLE"}]

    regime_df["dominant_regime"] = regime_df[prob_cols].idxmax(axis=1)
    regime_df["dominant_regime"] = regime_df["dominant_regime"].str.replace("_prob", "")

    # Merge with factor data
    sign = -1 if direction_info.get("direction_flipped", False) else 1
    sign_hint = factor_cfg.get("sign_hint", "positive")
    original_sign = 1 if sign_hint == "positive" else -1
    mult = original_sign * sign

    merged = aligned_panel.dropna(subset=[value_col, "fwd_return"]).copy()
    merged = merged[
        (merged["trade_date"] >= years[0] * 10000) &
        (merged["trade_date"] < (years[-1] + 1) * 10000)
    ]

    if merged.empty:
        return [{"factor": fname, "basis": basis, "regime": "ALL",
                 "n_dates": 0, "mean_ic": float("nan"),
                 "mean_net_spread": float("nan"),
                 "regime_status": "NOT_AVAILABLE"}]

    merged = merged.merge(
        regime_df[["trade_date", "dominant_regime"]],
        on="trade_date", how="left"
    )
    merged["dominant_regime"] = merged["dominant_regime"].fillna("unclassified")

    rows = []
    for regime, g in merged.groupby("dominant_regime"):
        daily_ic = g.groupby("trade_date").apply(
            lambda grp: _rank_ic(grp[value_col] * mult, grp["fwd_return"])
        ).dropna()

        mean_ic = float(daily_ic.mean()) if len(daily_ic) > 0 else float("nan")
        n_dates = len(daily_ic)

        rows.append({
            "factor": fname, "basis": basis, "regime": regime,
            "n_dates": n_dates,
            "mean_ic": round(mean_ic, 6) if not np.isnan(mean_ic) else float("nan"),
            "mean_net_spread": float("nan"),  # filled later if needed
            "regime_status": "OK" if n_dates > 0 else "NOT_AVAILABLE",
        })

    return rows


# ---------------------------------------------------------------------------
# Neutralization diagnostic
# ---------------------------------------------------------------------------

def _compute_neutralization_diagnostic(
    factor_cfg: dict,
    ic_raw: list[dict],
    ic_neutral: list[dict],
    quant_raw: list[dict],
    quant_neutral: list[dict],
    val_years: list[int],
    neut_meta: Optional[dict] = None,
    neutralization_cfg: Optional[dict] = None,
) -> dict[str, Any]:
    """Compare raw vs mcap-neutral IC and quantile metrics.

    Uses neut_meta from _neutralize_by_mcap to fill coverage and size_beta.
    Determines neutralization_valid based on config thresholds.
    """
    fname = factor_cfg["name"]
    if neut_meta is None:
        neut_meta = {}
    if neutralization_cfg is None:
        neutralization_cfg = {}

    min_cov = float(neutralization_cfg.get("min_neutralizer_coverage_pct", 70))
    min_dates = int(neutralization_cfg.get("min_valid_neutralized_dates", 60))
    max_skip_pct = float(neutralization_cfg.get("max_skipped_date_pct", 50))

    def _val_mean(rows, key):
        vals = [r[key] for r in rows
                if r["factor"] == fname and r["year"] in val_years
                and not np.isnan(r.get(key, float("nan")))]
        return float(np.mean(vals)) if vals else float("nan")

    raw_mean_ic = _val_mean(ic_raw, "mean_rank_ic")
    neutral_mean_ic = _val_mean(ic_neutral, "mean_rank_ic")
    raw_net_spread = _val_mean(quant_raw, "net_spread")
    neutral_net_spread = _val_mean(quant_neutral, "net_spread")

    # Size dependency: if raw IC drops significantly after neutralization
    size_dependency = False
    if not np.isnan(raw_mean_ic) and not np.isnan(neutral_mean_ic):
        if raw_mean_ic > 0.01 and neutral_mean_ic < raw_mean_ic * 0.5:
            size_dependency = True

    # Determine neutralization validity from meta
    cov_pct = neut_meta.get("neutralizer_coverage_pct", float("nan"))
    n_neut_dates = neut_meta.get("n_neutralized_dates", 0)
    skip_pct = neut_meta.get("skipped_date_pct", 100.0)
    neut_row_count = neut_meta.get("neutralized_row_count", 0)

    neutral_status: str
    neutral_valid: bool
    invalid_reason: str

    if not neut_meta or neut_row_count == 0:
        neutral_status = "NOT_AVAILABLE"
        neutral_valid = False
        invalid_reason = "no neutralized data"
    elif np.isnan(cov_pct) or cov_pct < min_cov:
        neutral_status = "LOW_COVERAGE"
        neutral_valid = False
        invalid_reason = f"coverage={cov_pct:.1f}% < {min_cov:.0f}%"
    elif n_neut_dates < min_dates:
        neutral_status = "INSUFFICIENT_DATES"
        neutral_valid = False
        invalid_reason = f"neutralized_dates={n_neut_dates} < {min_dates}"
    elif skip_pct > max_skip_pct:
        neutral_status = "LOW_COVERAGE"
        neutral_valid = False
        invalid_reason = f"skipped_date_pct={skip_pct:.1f}% > {max_skip_pct:.0f}%"
    elif size_dependency:
        neutral_status = "SIZE_DEPENDENT"
        neutral_valid = True
        invalid_reason = ""
    else:
        neutral_status = "OK"
        neutral_valid = True
        invalid_reason = ""

    # Use real coverage and beta from neutralization meta
    return {
        "factor": fname,
        "neutralizer_coverage_pct": cov_pct,
        "neutralizer_coverage_median_pct": neut_meta.get("neutralizer_coverage_median_pct", float("nan")),
        "neutralized_row_coverage_pct": neut_meta.get("neutralized_row_coverage_pct", float("nan")),
        "raw_mean_ic": round(raw_mean_ic, 6) if not np.isnan(raw_mean_ic) else float("nan"),
        "neutral_mean_ic": round(neutral_mean_ic, 6) if not np.isnan(neutral_mean_ic) else float("nan"),
        "raw_net_spread": round(raw_net_spread, 6) if not np.isnan(raw_net_spread) else float("nan"),
        "neutral_net_spread": round(neutral_net_spread, 6) if not np.isnan(neutral_net_spread) else float("nan"),
        "size_beta_mean": neut_meta.get("size_beta_mean", float("nan")),
        "size_dependency_flag": size_dependency,
        "neutralization_status": neutral_status,
        "neutralization_valid": neutral_valid,
        "neutralization_invalid_reason": invalid_reason,
        "n_neutralized_dates": n_neut_dates,
        "n_skipped_dates": neut_meta.get("n_skipped_dates", 0),
        "skipped_date_pct": skip_pct,
    }


# ---------------------------------------------------------------------------
# Correlation clustering (with gate_score dedup)
# ---------------------------------------------------------------------------

def _compute_correlation_clusters(
    factor_dfs: dict[str, pd.DataFrame],
    fwd: pd.DataFrame,
    direction_infos: dict[str, dict],
    factor_cfgs: list[dict],
    gate_results: list[dict],
    threshold: float = 0.85,
) -> pd.DataFrame:
    """Compute pairwise factor correlations and cluster redundant factors.

    Only clusters alpha_candidate non-hard-fail factors.
    Computes gate_score to select cluster representative.
    """
    cfg_map = {c["name"]: c for c in factor_cfgs}
    gate_map = {g["factor"]: g for g in gate_results}

    # Restrict to alpha_candidate factors that are not hard-fail
    eligible_names = set()
    for name, df in factor_dfs.items():
        if df.empty:
            continue
        cfg = cfg_map.get(name, {})
        if cfg.get("role", "alpha_candidate") != "alpha_candidate":
            continue
        g = gate_map.get(name, {})
        final_status = g.get("quality_gate_status", "FAIL")
        if final_status in ("FAIL", "DATA_MISSING"):
            continue
        eligible_names.add(name)

    CORRELATION_CLUSTER_COLUMNS = [
        "cluster_id", "factor", "representative", "redundant_to",
        "max_abs_corr_to_rep", "gate_score",
    ]

    if len(eligible_names) < 2:
        return pd.DataFrame(columns=CORRELATION_CLUSTER_COLUMNS)

    # Build monthly average factor values
    monthly_data: dict[str, pd.Series] = {}
    for name in eligible_names:
        df = factor_dfs[name]
        di = direction_infos.get(name, {})
        sign = -1 if di.get("direction_flipped", False) else 1
        hint = cfg_map.get(name, {}).get("sign_hint", "positive")
        original_sign = 1 if hint == "positive" else -1
        mult = original_sign * sign
        df_copy = df.copy()
        df_copy["value"] = df_copy["value"] * mult
        df_copy["month"] = df_copy["trade_date"] // 100
        monthly_avg = df_copy.groupby(["ts_code", "month"])["value"].mean()
        monthly_data[name] = monthly_avg

    if len(monthly_data) < 2:
        return pd.DataFrame()

    combined = pd.DataFrame(monthly_data).dropna()
    if combined.empty or len(combined.columns) < 2:
        return pd.DataFrame(columns=CORRELATION_CLUSTER_COLUMNS)

    corr = combined.corr()

    # Compute gate_score per factor
    def _compute_gate_score(name: str) -> float:
        g = gate_map.get(name, {})
        final_status = g.get("quality_gate_status", "FAIL")
        status_map = {"PASS": 100, "WATCH_SIZE_DEPENDENT": 50,
                      "WATCH_NEUTRAL_ONLY": 30, "WATCH_IC_DECAY": 40,
                      "WATCH_WINDOW_FRAGILE": 40, "WATCH_CAPACITY_CONSTRAINED": 40}
        status_score = status_map.get(final_status, 10)

        # Get mean IC from gate results
        mean_ic = 0.0
        icir = 0.0
        net_spread = 0.0
        avg_turnover = 0.0
        coverage = 0.0

        failure_reasons = g.get("failure_reasons", "")
        # Extract from gate metadata if available
        gate_meta = g.get("_gate_meta", {})
        mean_ic = float(gate_meta.get("raw_mean_ic", 0))
        icir = float(gate_meta.get("raw_icir", 0))
        net_spread = float(gate_meta.get("raw_net_spread", 0))
        avg_turnover = float(gate_meta.get("avg_total_turnover", 0))
        coverage = float(gate_meta.get("coverage_pct", 0))

        return status_score + 10 * mean_ic + 5 * icir + 100 * net_spread - 2 * avg_turnover + coverage

    # Cluster
    rows = []
    assigned = set()
    cluster_id = 0

    for f1 in corr.columns:
        if f1 in assigned:
            continue
        cluster_id += 1
        cluster = [f1]
        for f2 in corr.columns:
            if f2 != f1 and f2 not in assigned and abs(corr.loc[f1, f2]) > threshold:
                cluster.append(f2)
                assigned.add(f2)
        assigned.add(f1)

        # Find representative
        scores = {f: _compute_gate_score(f) for f in cluster}
        rep = max(scores, key=scores.get)

        for f in cluster:
            rows.append({
                "cluster_id": cluster_id,
                "factor": f,
                "representative": "yes" if f == rep else "no",
                "redundant_to": "" if f == rep else rep,
                "max_abs_corr_to_rep": round(abs(corr.loc[f, rep]), 4) if f != rep else 1.0,
                "gate_score": round(scores[f], 2),
            })

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Quality gate (unified, four-state)
# ---------------------------------------------------------------------------

def _apply_quality_gate(
    factor_cfg: dict,
    input_audit: dict,
    alignment_audit: dict,
    direction_info: dict,
    ic_raw: list[dict],
    ic_neutral: list[dict],
    quant_raw: list[dict],
    quant_neutral: list[dict],
    turnover_cost_rows: list[dict],
    ic_trend: dict,
    rolling_results: list[dict],
    capacity_rows: list[dict],
    gate_cfg: dict,
    gate_basis_cfg: dict,
    robustness_cfg: dict,
    capacity_cfg: dict,
    neutralization_diag: Optional[dict] = None,
    neutralization_cfg: Optional[dict] = None,
) -> dict[str, Any]:
    """Apply unified quality gate with raw/neutral four-state logic."""
    if neutralization_diag is None:
        neutralization_diag = {}
    if neutralization_cfg is None:
        neutralization_cfg = {}
    fname = factor_cfg["name"]
    hard_failures: list[str] = []
    soft_failures: list[str] = []
    warnings: list[str] = []
    gate_meta: dict[str, Any] = {}

    # ---- 0. DATA_MISSING (must early-exit — no data to compute anything) ----
    if input_audit.get("data_status") == "DATA_MISSING":
        return {"factor": fname, "quality_gate_status": "DATA_MISSING",
                "n_failures": 0, "n_hard_failures": 0, "n_soft_failures": 0,
                "hard_failure_reasons": "", "soft_failure_reasons": "",
                "warning_reasons": "",
                "failure_reasons": "factor cache empty",
                "_gate_meta": gate_meta}

    # ---- 1. Collect all diagnostics (do NOT exit early) ----
    require_no_leakage = gate_cfg.get("require_no_leakage", True)
    no_leakage_status = alignment_audit.get("no_leakage_status", "NOT_AVAILABLE")
    if require_no_leakage and no_leakage_status not in ("PASS",):
        hard_failures.append(f"no_leakage: {no_leakage_status} — {alignment_audit.get('alignment_reason', '')}")

    if capacity_cfg.get("enabled", False) and capacity_rows:
        cap_statuses = [r["capacity_status"] for r in capacity_rows]
        if "FAIL" in cap_statuses:
            hard_failures.append("capacity: FAIL — liquidity/capacity insufficient")
        elif "WATCH" in cap_statuses:
            warnings.append("capacity: WATCH — liquidity constraints")

    # ---- 2. Input audit ----
    if input_audit.get("input_audit_status") != "PASS":
        soft_failures.append(f"input_audit: {input_audit.get('input_audit_reason', 'FAIL')}")

    # ---- 3. Direction audit ----
    if direction_info.get("direction_audit_status") != "PASS":
        soft_failures.append(f"direction_audit: {direction_info.get('direction_audit_reason', 'FAIL')}")

    # ---- 5. Compute raw gate ----
    val_years = [2021, 2022, 2023, 2024]

    def _compute_single_gate(ic_rows, q_rows, basis_label):
        fails = []
        meta = {}
        val_ic = [r for r in ic_rows if r["year"] in val_years]
        meta["ic_rows_count"] = len(val_ic)
        if val_ic:
            mean_ic = float(np.nanmean([r["mean_rank_ic"] for r in val_ic]))
            mean_icir = float(np.nanmean([r["icir"] for r in val_ic]))
            pos_years = sum(1 for r in val_ic if not np.isnan(r["mean_rank_ic"]) and r["mean_rank_ic"] > 0)
            meta["mean_ic"] = mean_ic
            meta["icir"] = mean_icir
            meta["pos_ic_years"] = pos_years

            if np.isnan(mean_ic) or mean_ic < gate_cfg.get("min_mean_rank_ic", 0.01):
                fails.append(f"[{basis_label}] mean_rank_ic={_num(mean_ic)} < {_num(gate_cfg['min_mean_rank_ic'])}")
            if np.isnan(mean_icir) or mean_icir < gate_cfg.get("min_icir", 0.20):
                fails.append(f"[{basis_label}] icir={_num(mean_icir)} < {_num(gate_cfg['min_icir'])}")
            if pos_years < gate_cfg.get("min_positive_ic_years", 3):
                fails.append(f"[{basis_label}] pos_ic_years={pos_years}/4 < {gate_cfg['min_positive_ic_years']}")
        else:
            fails.append(f"[{basis_label}] no validation IC data")
            meta["mean_ic"] = float("nan")
            meta["icir"] = float("nan")

        val_q = [r for r in q_rows if r["year"] in val_years]
        if val_q:
            net_spreads = [r["net_spread"] for r in val_q if not np.isnan(r["net_spread"])]
            top_excess = [r["top_quintile_net_excess"] for r in val_q if not np.isnan(r["top_quintile_net_excess"])]
            pos_spread_yrs = sum(1 for s in net_spreads if s > 0)
            pos_excess_yrs = sum(1 for e in top_excess if e > 0)
            mean_net_spread = float(np.nanmean(net_spreads)) if net_spreads else float("nan")
            mean_top_excess = float(np.nanmean(top_excess)) if top_excess else float("nan")
            meta["net_spread"] = mean_net_spread
            meta["pos_spread_years"] = pos_spread_yrs

            if np.isnan(mean_net_spread) or mean_net_spread <= gate_cfg.get("min_top_bottom_net_spread_5d", 0):
                fails.append(f"[{basis_label}] net_spread={_num(mean_net_spread, 4)} <= 0")
            if pos_spread_yrs < gate_cfg.get("min_positive_spread_years", 3):
                fails.append(f"[{basis_label}] pos_spread_years={pos_spread_yrs}/4 < {gate_cfg['min_positive_spread_years']}")
            if np.isnan(mean_top_excess) or mean_top_excess <= gate_cfg.get("min_top_quintile_net_excess_5d", 0):
                fails.append(f"[{basis_label}] top_quintile_net_excess={_num(mean_top_excess, 4)} <= 0")
            if pos_excess_yrs < gate_cfg.get("min_positive_excess_years", 3):
                fails.append(f"[{basis_label}] pos_excess_years={pos_excess_yrs}/4 < {gate_cfg['min_positive_excess_years']}")

            if net_spreads and sum(net_spreads) > 0:
                max_contrib = max(net_spreads) / sum(net_spreads)
                if max_contrib > gate_cfg.get("max_single_year_contribution_pct", 60) / 100:
                    fails.append(f"[{basis_label}] max_year_contrib={_pct(max_contrib, 0)} > {gate_cfg['max_single_year_contribution_pct']}%")

            gross_spreads = [r["gross_spread"] for r in val_q if not np.isnan(r["gross_spread"])]
            if gross_spreads and sum(gross_spreads) > 0:
                ratio = sum(net_spreads) / sum(gross_spreads) if sum(gross_spreads) > 0 else 0
                meta["net_gross_ratio"] = ratio
                if ratio < gate_cfg.get("min_net_gross_spread_ratio", 0.50):
                    fails.append(f"[{basis_label}] net/gross_ratio={_pct(ratio, 0)} < {_pct(gate_cfg['min_net_gross_spread_ratio'], 0)}")
        else:
            fails.append(f"[{basis_label}] no validation quantile data")
            meta["net_spread"] = float("nan")

        meta["failures"] = fails
        return fails, meta

    raw_fails, raw_meta = _compute_single_gate(ic_raw, quant_raw, "raw")
    neutral_fails, neutral_meta = _compute_single_gate(ic_neutral, quant_neutral, "neutral")

    gate_meta["raw_mean_ic"] = raw_meta.get("mean_ic", float("nan"))
    gate_meta["raw_icir"] = raw_meta.get("icir", float("nan"))
    gate_meta["raw_net_spread"] = raw_meta.get("net_spread", float("nan"))
    gate_meta["raw_net_gross_ratio"] = raw_meta.get("net_gross_ratio", float("nan"))
    gate_meta["neutral_mean_ic"] = neutral_meta.get("mean_ic", float("nan"))
    gate_meta["neutral_icir"] = neutral_meta.get("icir", float("nan"))
    gate_meta["neutral_net_spread"] = neutral_meta.get("net_spread", float("nan"))

    # Coverage gate (from alignment audit, signal_date based)
    cov_pct = alignment_audit.get("median_coverage_pct", input_audit.get("median_coverage_pct", 0))
    min_cov_pct = gate_cfg.get("min_coverage_pct", 80)
    min_yr_cov = alignment_audit.get("min_yearly_coverage_pct", input_audit.get("min_yearly_coverage_pct", 0))
    min_single_yr = gate_cfg.get("min_single_year_coverage_pct", 60)
    if cov_pct < min_cov_pct / 100.0:
        soft_failures.append(f"coverage: {_pct(cov_pct)} < {min_cov_pct}%")
    if min_yr_cov < min_single_yr / 100.0:
        soft_failures.append(f"min_yearly_coverage: {_pct(min_yr_cov)} < {min_single_yr}%")
    gate_meta["coverage_pct"] = cov_pct

    # ---- 6. Four-state machine (with neutralization validity) ----
    raw_pass = not raw_fails
    neutral_pass = not neutral_fails

    # Check neutralization validity
    neutral_valid = neutralization_diag.get("neutralization_valid", False) if neutralization_diag else False
    require_valid_neut = gate_basis_cfg.get("require_valid_neutralization_for_neutral_gate",
                                            neutralization_cfg.get("require_valid_neutralization_for_neutral_gate", True))

    if raw_pass and neutral_pass and (not require_valid_neut or neutral_valid):
        base_status = "PASS"
    elif raw_pass and neutral_pass and require_valid_neut and not neutral_valid:
        # Neutral appears to pass but is based on invalid neutralization
        base_status = "WATCH_NEUTRAL_UNAVAILABLE"
        soft_failures.append(f"neutralization: invalid ({neutralization_diag.get('neutralization_status', '?')}), "
                            f"{neutralization_diag.get('neutralization_invalid_reason', '')}")
    elif raw_pass and not neutral_pass:
        if not require_valid_neut or neutral_valid:
            base_status = gate_basis_cfg.get("raw_pass_neutral_fail_status", "WATCH_SIZE_DEPENDENT")
        else:
            base_status = "WATCH_NEUTRAL_UNAVAILABLE"
            soft_failures.append(f"neutralization: invalid ({neutralization_diag.get('neutralization_status', '?')}), "
                                f"{neutralization_diag.get('neutralization_invalid_reason', '')}")
    elif not raw_pass and neutral_pass:
        if neutral_valid:
            base_status = gate_basis_cfg.get("raw_fail_neutral_pass_status", "WATCH_NEUTRAL_ONLY")
        else:
            # Neutral gate passes but neutralization is invalid — cannot be WATCH_NEUTRAL_ONLY
            base_status = "FAIL"
            soft_failures.append(f"neutralization: invalid ({neutralization_diag.get('neutralization_status', '?')}), "
                                f"cannot be WATCH_NEUTRAL_ONLY with {neutralization_diag.get('neutralization_invalid_reason', '')}")
    else:
        base_status = "FAIL"

    # Collect raw/neutral failures into soft
    soft_failures.extend(raw_fails)
    soft_failures.extend(neutral_fails)

    # If neutralization invalid, add warning
    if not neutral_valid and base_status not in ("FAIL",):
        warnings.append(f"neutralization_invalid: {neutralization_diag.get('neutralization_status', '?')}")

    # ---- 7. Downgrade checks ----
    final_status = base_status

    # IC decay downgrade
    if base_status == "PASS" and ic_trend.get("ic_declining", False):
        final_status = "WATCH_IC_DECAY"
        soft_failures.append("IC_DECLINING: significant negative trend in monthly IC")

    # Rolling window downgrade
    if rolling_results:
        pass_count = sum(1 for r in rolling_results if r["window_gate_status"] == "PASS")
        min_pass = robustness_cfg.get("min_pass_windows_for_strong_pass", 3)
        if base_status == "PASS" and pass_count < min_pass:
            final_status = "WATCH_WINDOW_FRAGILE"
            soft_failures.append(f"rolling_window: only {pass_count}/{len(rolling_results)} windows PASS")

    # Capacity downgrade
    if capacity_cfg.get("enabled", False) and capacity_rows:
        cap_watch = any(r["capacity_status"] == "WATCH" for r in capacity_rows)
        if base_status == "PASS" and cap_watch:
            final_status = "WATCH_CAPACITY_CONSTRAINED"
            soft_failures.append("capacity: WATCH — liquidity constraints")

    # ---- 8. Role override ----
    role = factor_cfg.get("role", "alpha_candidate")
    if role != "alpha_candidate":
        final_status = "SUPPORT"

    # ---- 9. Final status resolution ----
    # Hard failures override to FAIL (unless SUPPORT or DATA_MISSING)
    if hard_failures and final_status not in ("SUPPORT", "DATA_MISSING"):
        final_status = "FAIL"

    # Build combined failure strings
    hard_str = "; ".join(hard_failures[:10])
    soft_str = "; ".join(soft_failures[:15])
    warn_str = "; ".join(warnings[:10])
    all_parts = [s for s in [hard_str, soft_str, warn_str] if s]
    failure_str = " | ".join(all_parts)

    # Also include turnover cost info if available
    if turnover_cost_rows:
        val_tc = [r for r in turnover_cost_rows if r["year"] in val_years]
        if val_tc:
            avg_to = float(np.nanmean([r["avg_total_turnover"] for r in val_tc]))
            gate_meta["avg_total_turnover"] = avg_to

    return {
        "factor": fname,
        "quality_gate_status": final_status,
        "n_failures": len(hard_failures) + len(soft_failures),
        "n_hard_failures": len(hard_failures),
        "n_soft_failures": len(soft_failures),
        "hard_failure_reasons": hard_str,
        "soft_failure_reasons": soft_str,
        "warning_reasons": warn_str,
        "failure_reasons": failure_str,
        "_gate_meta": gate_meta,
    }


# ---------------------------------------------------------------------------
# Candidate pool generation
# ---------------------------------------------------------------------------

def _generate_candidate_pool(
    gate_results: list[dict],
    factor_cfgs: list[dict],
    correlation_clusters: pd.DataFrame,
    out_path: Path,
) -> dict:
    """Generate candidate pool with new contract."""
    cfg_map = {c["name"]: c for c in factor_cfgs}

    eligible = []
    watch_for_review = []
    support_neutralizers = []
    support_redundant = []
    missing_data = []
    fail_factors = []

    for g in gate_results:
        fname = g["factor"]
        status = g["quality_gate_status"]
        role = cfg_map.get(fname, {}).get("role", "alpha_candidate")

        if status == "DATA_MISSING":
            missing_data.append(fname)
        elif status == "SUPPORT" or role == "neutralizer":
            if role == "neutralizer":
                support_neutralizers.append(fname)
            else:
                support_redundant.append({"factor": fname, "redundant_to": "cluster"})
        elif status == "PASS":
            # Check if cluster representative
            if not correlation_clusters.empty:
                cc = correlation_clusters[correlation_clusters["factor"] == fname]
                if not cc.empty and cc.iloc[0]["representative"] == "yes":
                    eligible.append(fname)
                elif not cc.empty:
                    rep = cc.iloc[0]["redundant_to"]
                    support_redundant.append({"factor": fname, "redundant_to": rep})
                else:
                    eligible.append(fname)
            else:
                eligible.append(fname)
        elif status.startswith("WATCH"):
            watch_for_review.append(fname)
        elif status == "FAIL":
            fail_factors.append(fname)

    # Recommendation
    if not eligible:
        recommendation = "NO_ALPHA_SOURCE_FOUND"
    else:
        recommendation = f"{len(eligible)} eligible factor(s) available for sleeve rebuild"

    pool = {
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "description": "Factor quality rebuild — candidate pool (v2)",
        "recommendation": recommendation,
        "eligible_factors": eligible,
        "watch_factors_for_review": watch_for_review,
        "support_factors": {
            "neutralizers": support_neutralizers,
            "redundant": support_redundant,
        },
        "missing_data_factors": missing_data,
        "fail_factors": fail_factors,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(yaml.dump(pool, allow_unicode=True, default_flow_style=False), encoding="utf-8")
    return pool


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def _write_report(
    out_doc: Path,
    input_audits: list[dict],
    direction_audits: list[dict],
    alignment_audits: list[dict],
    ic_rows_all: list[dict],
    quantile_rows_all: list[dict],
    turnover_cost_all: list[dict],
    neutralization_diags: list[dict],
    ic_trends: list[dict],
    rolling_gates: list[dict],
    correlation_clusters: pd.DataFrame,
    capacity_audits: list[dict],
    regime_breakdowns: list[dict],
    gate_results: list[dict],
    pool: dict,
    config_path: str = "",
    config_sha256: str = "",
    seed: int = 42,
) -> None:
    lines: list[str] = []
    lines.append("# Factor Quality Rebuild Report (v2)")
    lines.append("")
    lines.append(f"生成日期：{datetime.now().strftime('%Y-%m-%d %H:%M')}")
    if config_path:
        lines.append(f"配置：`{config_path}` (sha256={config_sha256})")
    lines.append(f"随机种子：{seed}")
    lines.append("")

    # Summary
    status_count = {}
    for g in gate_results:
        s = g["quality_gate_status"]
        status_count[s] = status_count.get(s, 0) + 1
    lines.append("## Summary")
    lines.append("")
    for s in ["PASS", "WATCH_SIZE_DEPENDENT", "WATCH_NEUTRAL_ONLY", "WATCH_IC_DECAY",
              "WATCH_WINDOW_FRAGILE", "WATCH_CAPACITY_CONSTRAINED", "DATA_MISSING",
              "SUPPORT", "FAIL"]:
        if s in status_count:
            lines.append(f"- {s}: {status_count[s]}")
    lines.append(f"- **Recommendation**: **{pool.get('recommendation', 'N/A')}**")
    lines.append("")

    # No-leakage audit
    lines.append("## No-Leakage Alignment Audit")
    lines.append("")
    lines.append("| Factor | Horizon | Lag (days) | Aligned Rows | Signal Dates | Cal/Val/Watch | Status |")
    lines.append("|---|---:|---:|---:|---:|---|")
    for a in alignment_audits:
        lines.append(
            f"| `{a['factor']}` | {a.get('horizon','')} | {a.get('data_lag_days','')} | "
            f"{a.get('n_aligned_rows','')} | {a.get('n_signal_dates','')} | "
            f"{a.get('calibration_rows','')}/{a.get('validation_rows','')}/{a.get('watch_rows','')} | "
            f"{a.get('no_leakage_status','')} |"
        )
    lines.append("")

    # Raw vs mcap-neutral comparison
    lines.append("## Raw vs Mcap-Neutral Comparison (Validation 2021-2024)")
    lines.append("")
    lines.append("| Factor | Raw IC | Neutral IC | Raw ICIR | Neutral ICIR | Raw Net Spread | Neutral Net Spread | Size Dependent |")
    lines.append("|---|---:|---:|---:|---:|---:|---|")
    for nd in neutralization_diags:
        lines.append(
            f"| `{nd['factor']}` | {_num(nd.get('raw_mean_ic'), 4)} | {_num(nd.get('neutral_mean_ic'), 4)} | "
            f"{_num(nd.get('raw_icir', float('nan')), 3)} | {_num(nd.get('neutral_icir', float('nan')), 3)} | "
            f"{_pct(nd.get('raw_net_spread'), 2)} | {_pct(nd.get('neutral_net_spread'), 2)} | "
            f"{nd.get('size_dependency_flag', False)} |"
        )
    lines.append("")

    # Turnover/cost
    lines.append("## Turnover Cost Analysis (Validation 2021-2024)")
    lines.append("")
    lines.append("| Factor | Basis | Method | Avg Turnover | Gross Spread | Net Spread | Net/Gross |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    val_tc = [r for r in turnover_cost_all if r["year"] in [2021, 2022, 2023, 2024]]
    tc_by_factor: dict[str, list] = {}
    for r in val_tc:
        tc_by_factor.setdefault(r["factor"], []).append(r)
    for fname, rows in sorted(tc_by_factor.items()):
        avg_to = float(np.nanmean([r["avg_total_turnover"] for r in rows]))
        avg_gs = float(np.nanmean([r["gross_spread"] for r in rows]))
        avg_ns = float(np.nanmean([r["net_spread"] for r in rows]))
        ratio = float(np.nanmean([r["net_gross_ratio"] for r in rows]))
        method = rows[0].get("turnover_method", "N/A")
        lines.append(
            f"| `{fname}` | {rows[0].get('basis','')} | {method} | "
            f"{_pct(avg_to, 1)} | {_pct(avg_gs, 2)} | {_pct(avg_ns, 2)} | {_pct(ratio, 1)} |"
        )
    lines.append("")

    # IC trend
    lines.append("## IC Trend (Validation Window)")
    lines.append("")
    lines.append("| Factor | Basis | Monthly ICs | Slope | p-value | Declining |")
    lines.append("|---|---:|---:|---:|---|")
    for t in ic_trends:
        lines.append(
            f"| `{t['factor']}` | {t.get('basis','')} | {t.get('monthly_ic_count','')} | "
            f"{_num(t.get('ic_trend_slope'), 6)} | {_num(t.get('ic_trend_p_value'), 4)} | "
            f"{t.get('ic_declining', False)} |"
        )
    lines.append("")

    # Rolling window robustness
    lines.append("## Rolling Window Robustness")
    lines.append("")
    if rolling_gates:
        lines.append("| Factor | Window | Basis | Status | Mean IC | ICIR | Net Spread | Pos IC Yrs | Pos Spread Yrs |")
        lines.append("|---|---:|---:|---:|---:|---:|---:|---:|")
        for r in rolling_gates:
            lines.append(
                f"| `{r['factor']}` | {r['window']} | {r.get('basis','')} | {r['window_gate_status']} | "
                f"{_num(r.get('mean_ic'), 4)} | {_num(r.get('icir'), 3)} | "
                f"{_pct(r.get('net_spread'), 2)} | {r.get('positive_ic_years','')}/{r.get('window_years','')} | "
                f"{r.get('positive_spread_years','')}/{r.get('window_years','')} |"
            )
    else:
        lines.append("No rolling window data available.")
    lines.append("")

    # Correlation clusters
    lines.append("## Correlation Clusters")
    lines.append("")
    if not correlation_clusters.empty:
        lines.append("| Cluster | Factor | Representative | Redundant To | Max Corr to Rep | Gate Score |")
        lines.append("|---|---:|---:|---:|---:|")
        for _, row in correlation_clusters.iterrows():
            lines.append(
                f"| {row['cluster_id']} | `{row['factor']}` | {row['representative']} | "
                f"{row['redundant_to'] or '-'} | {row['max_abs_corr_to_rep']} | {row['gate_score']} |"
            )
    else:
        lines.append("No correlation data available (fewer than 2 eligible factors).")
    lines.append("")

    # Capacity audit
    lines.append("## Capacity / Liquidity Audit")
    lines.append("")
    if capacity_audits:
        lines.append("| Factor | Year | Median Top Amt (CNY) | Median Mkt Cap (CNY) | Participation Rate | Status |")
        lines.append("|---|---:|---:|---:|---:|---|")
        for c in capacity_audits:
            lines.append(
                f"| `{c['factor']}` | {c.get('year','')} | "
                f"{c.get('median_top_amount_cny', float('nan')):.0f} | "
                f"{c.get('median_market_cap_cny', float('nan')):.0f} | "
                f"{_pct(c.get('participation_rate_at_target_aum', float('nan')), 2)} | "
                f"{c.get('capacity_status','')} |"
            )
    else:
        lines.append("Capacity data not available.")
    lines.append("")

    # Regime breakdown
    lines.append("## Regime Breakdown")
    lines.append("")
    if regime_breakdowns:
        regimes_seen = set()
        lines.append("| Factor | Regime | N Dates | Mean IC |")
        lines.append("|---|---:|---:|")
        for r in regime_breakdowns:
            lines.append(
                f"| `{r['factor']}` | {r.get('regime','')} | {r.get('n_dates','')} | "
                f"{_num(r.get('mean_ic'), 4)} |"
            )
            regimes_seen.add(r.get("regime_status", ""))
        if "NOT_AVAILABLE" in regimes_seen:
            lines.append("")
            lines.append("*Note: Some regime data is NOT_AVAILABLE. Regime breakdown is diagnostic only and does not affect gate.*")
    else:
        lines.append("Regime data not available (diagnostic only, does not affect gate).")
    lines.append("")

    # Quality gate
    lines.append("## Quality Gate Results")
    lines.append("")
    lines.append("| Factor | Status | Failures | Reasons |")
    lines.append("|---|---:|---|")
    for g in sorted(gate_results, key=lambda x: {
        "PASS": 0, "WATCH_SIZE_DEPENDENT": 1, "WATCH_NEUTRAL_ONLY": 1,
        "WATCH_IC_DECAY": 1, "WATCH_WINDOW_FRAGILE": 1, "WATCH_CAPACITY_CONSTRAINED": 1,
        "DATA_MISSING": 2, "SUPPORT": 3, "FAIL": 4,
    }.get(x["quality_gate_status"], 99)):
        icon = f"[{g['quality_gate_status']}]"
        lines.append(f"| `{g['factor']}` | {icon} | {g['n_failures']} | {g['failure_reasons'][:200]} |")
    lines.append("")

    # Candidate pool
    lines.append("## Candidate Pool")
    lines.append("")
    lines.append(f"- **Eligible**: {pool['eligible_factors']}")
    lines.append(f"- **Watch for Review**: {pool['watch_factors_for_review']}")
    lines.append(f"- **Support — Neutralizers**: {pool['support_factors'].get('neutralizers', [])}")
    lines.append(f"- **Support — Redundant**: {pool['support_factors'].get('redundant', [])}")
    lines.append(f"- **Missing Data**: {pool.get('missing_data_factors', [])}")
    lines.append(f"- **FAIL**: {pool.get('fail_factors', [])}")
    lines.append(f"- **Recommendation**: **{pool['recommendation']}**")
    lines.append("")

    # Conclusions
    lines.append("## Conclusions")
    lines.append("")
    eligible = pool.get("eligible_factors", [])
    watch = pool.get("watch_factors_for_review", [])
    missing = pool.get("missing_data_factors", [])
    fail = pool.get("fail_factors", [])

    if eligible:
        lines.append(f"1. **哪些因子真的有净 alpha**: {', '.join(eligible)}")
    else:
        lines.append("1. **哪些因子真的有净 alpha**: None — no factors pass the full quality gate with net positive post-cost alpha.")

    # Classify WATCH factors
    size_dep = [g["factor"] for g in gate_results if g["quality_gate_status"] == "WATCH_SIZE_DEPENDENT"]
    neutral_only = [g["factor"] for g in gate_results if g["quality_gate_status"] == "WATCH_NEUTRAL_ONLY"]
    ic_decay = [g["factor"] for g in gate_results if g["quality_gate_status"] == "WATCH_IC_DECAY"]
    window_fragile = [g["factor"] for g in gate_results if g["quality_gate_status"] == "WATCH_WINDOW_FRAGILE"]
    cap_constrained = [g["factor"] for g in gate_results if g["quality_gate_status"] == "WATCH_CAPACITY_CONSTRAINED"]

    lines.append(f"2. **哪些因子只是方向/实现问题**: {', '.join(watch) if watch else 'None identified'}")
    if size_dep:
        lines.append(f"   - SIZE_DEPENDENT (raw alpha exists but comes from size exposure): {', '.join(size_dep)}")
    if neutral_only:
        lines.append(f"   - NEUTRAL_ONLY (only shows alpha after mcap neutralization): {', '.join(neutral_only)}")
    if ic_decay:
        lines.append(f"   - IC_DECAY (passing gate but IC declining significantly): {', '.join(ic_decay)}")
    if window_fragile:
        lines.append(f"   - WINDOW_FRAGILE (fails in ≥2 rolling windows): {', '.join(window_fragile)}")
    if cap_constrained:
        lines.append(f"   - CAPACITY_CONSTRAINED (liquidity concerns): {', '.join(cap_constrained)}")

    if missing:
        lines.append(f"3. **哪些因子数据缺失，不应永久淘汰**: {', '.join(missing)}")
    else:
        lines.append("3. **哪些因子数据缺失**: None")
    if fail:
        lines.append(f"4. **哪些因子应永久淘汰**: {', '.join(fail)}")
    else:
        lines.append("4. **哪些因子应永久淘汰**: None")

    lines.append("")
    lines.append("## Sleeve Rebuild Authorization")
    lines.append("")
    if eligible:
        lines.append(f"✅ **AUTHORIZED**: {len(eligible)} eligible factor(s) available. Proceed to sleeve rebuild.")
    else:
        lines.append("❌ **NOT AUTHORIZED**: No eligible factors. Sleeve/strategy rebuild is blocked.")
        if missing:
            lines.append(f"   → Action: Restore data for {', '.join(missing)} before re-running factor quality rebuild.")
        if watch:
            lines.append(f"   → Action: Manually review {len(watch)} WATCH factor(s) for potential alpha.")

    out_doc.parent.mkdir(parents=True, exist_ok=True)
    out_doc.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Factor Quality Rebuild v2")
    parser.add_argument("--config", default="configs/factor_quality_rebuild.yaml")
    parser.add_argument("--start", default="20170101")
    parser.add_argument("--end", default="20241231")
    parser.add_argument("--out-dir", default="outputs/analysis/factor_quality_rebuild")
    parser.add_argument("--out-doc", default="docs/factor_quality_rebuild_report.md")
    parser.add_argument("--profile-out", default="")
    parser.add_argument("--seed", type=int, default=42,
                       help="Random seed for reproducibility (default: 42)")
    # Smoke / quick-validation mode
    parser.add_argument("--factor-limit", type=int, default=0,
                       help="Process at most N factors (0 = no limit)")
    parser.add_argument("--factor-include", default="",
                       help="Comma-separated factor names to include (empty = all)")
    parser.add_argument("--skip-capacity", action="store_true",
                       help="Skip capacity audit stage")
    parser.add_argument("--skip-regime", action="store_true",
                       help="Skip regime breakdown stage")
    parser.add_argument("--skip-correlation", action="store_true",
                       help="Skip correlation clustering stage")
    # Runtime warnings
    parser.add_argument("--warn-stage-seconds", type=int, default=300,
                       help="Warn if a stage exceeds this duration in seconds")
    parser.add_argument("--warn-factor-seconds", type=int, default=600,
                       help="Warn if a single factor exceeds this duration in seconds")
    args = parser.parse_args()

    # ---- Reproducibility: set numpy random seed ----
    np.random.seed(args.seed)

    config_path = ROOT / args.config
    out_dir = ROOT / args.out_dir
    out_doc = ROOT / args.out_doc

    # ---- Compute config checksum for traceability ----
    config_sha256 = _config_checksum(config_path)
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    config_warnings: list[str] = []

    # ---- Atomic output: write to _run_<run_id>/ first, publish on success ----
    run_dir = out_dir / f"_run_{run_id}"
    partial_dir = run_dir / "partial"
    partial_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[run] run_id={run_id} config={args.config} sha256={config_sha256} seed={args.seed}", flush=True)

    # ---- Run diagnostics ----
    diag = RunDiagnostics(
        diag_dir=run_dir, run_id=run_id, config_path=args.config,
        config_sha256=config_sha256, seed=args.seed,
        factor_count=0,  # updated after filtering
        out_dir=str(out_dir), out_doc=str(out_doc),
    )

    # Load config
    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    factors_cfg_original = cfg["factors"]
    gate_cfg = cfg["gate"]
    gate_basis_cfg = cfg.get("gate_basis", {})
    robustness_cfg = cfg.get("robustness", {})
    capacity_cfg = cfg.get("capacity", {})
    neutralization_cfg = cfg.get("neutralization", {})

    # ---- Config schema validation (fail-fast) ----
    _validate_robustness_config(robustness_cfg)

    windows = cfg["windows"]
    cal_start = windows["calibration"]["start"]
    cal_end = windows["calibration"]["end"]
    val_start = windows["validation"]["start"]
    val_end = windows["validation"]["end"]
    watch_start = windows["watch_only"]["start"]
    watch_end = windows["watch_only"]["end"]

    # ---- Factor filtering (smoke mode) ----
    factors_cfg = factors_cfg_original
    if args.factor_include:
        include_set = {n.strip() for n in args.factor_include.split(",") if n.strip()}
        factors_cfg = [f for f in factors_cfg if f["name"] in include_set]
        print(f"[smoke] factor-include: limiting to {len(factors_cfg)} factor(s): "
              f"{[f['name'] for f in factors_cfg]}", flush=True)
    if args.factor_limit > 0 and len(factors_cfg) > args.factor_limit:
        factors_cfg = factors_cfg[:args.factor_limit]
        print(f"[smoke] factor-limit: truncating to first {args.factor_limit} factor(s)", flush=True)
    if args.skip_capacity:
        capacity_cfg = {**capacity_cfg, "enabled": False}
        print("[smoke] skip-capacity: capacity audit disabled", flush=True)
    if args.skip_regime:
        print("[smoke] skip-regime: regime breakdown disabled", flush=True)
    if args.skip_correlation:
        print("[smoke] skip-correlation: correlation clustering disabled", flush=True)

    # Update diagnostics with actual factor count
    diag.factor_count = len(factors_cfg)
    diag._write_manifest("RUNNING")

    # ---- Data range vs config window validation ----
    if int(watch_end) > int(args.end):
        w = (f"[config] watch_only.end={watch_end} > CLI --end={args.end} — "
             f"watch window data will be incomplete; "
             f"consider --end {watch_end}")
        config_warnings.append(w)
        print(f"[WARNING] {w}", flush=True)

    # ---- Per-factor config validation ----
    for factor_cfg in factors_cfg:
        fw = _validate_factor_config(factor_cfg)
        for w in fw:
            config_warnings.append(w)
            print(f"[WARNING] {w}", flush=True)
    cost_bps = cfg["cost"]["single_side_bps"]
    corr_threshold = cfg["correlation"]["max_intra_cluster_corr"]
    primary_horizon = cfg["horizons"]["primary"]
    aux_horizons = cfg["horizons"].get("auxiliary", [])
    min_neutralizer_cov = float(cfg.get("neutralization", {}).get("min_neutralizer_coverage_pct", 70))

    val_years = list(range(2021, 2025))
    years_all = list(range(2017, 2025))
    rolling_windows = robustness_cfg.get("rolling_windows", [])

    with timed_stage("load_fwd_returns"):
        print(f"Loading forward returns ({args.start} to {args.end})...")
        fwd = _load_fwd_returns(args.start, args.end)
    fwd.columns = [str(c).strip().lower() for c in fwd.columns]
    fwd_ret_cols = [c for c in fwd.columns if c.startswith("fwd_ret")]
    print(f"  {len(fwd)} rows, columns: {fwd_ret_cols}")
    # Normalize fwd column names
    for c in list(fwd.columns):
        if c in ("fwd_ret_5d", "fwd_ret_10d", "fwd_ret_20d", "fwd_ret_1d"):
            continue
        if c == "fwd_ret_5" or "fwd_ret_5d" in c:
            fwd = fwd.rename(columns={c: "fwd_ret_5d"})
        elif c == "fwd_ret_10" or "fwd_ret_10d" in c:
            fwd = fwd.rename(columns={c: "fwd_ret_10d"})
        elif c == "fwd_ret_20" or "fwd_ret_20d" in c:
            fwd = fwd.rename(columns={c: "fwd_ret_20d"})
        elif c == "fwd_ret_1" or "fwd_ret_1d" in c:
            fwd = fwd.rename(columns={c: "fwd_ret_1d"})
    print(f"  Normalized columns: {[c for c in fwd.columns if c.startswith('fwd_ret')]}", flush=True)

    # Pre-index forward universe by signal_date for fast coverage lookup
    fwd_dates = fwd[["ts_code", "trade_date"]].rename(columns={"trade_date": "signal_date"})
    fwd_universe_by_date: dict[int, set] = {
        int(sd): set(g["ts_code"].tolist())
        for sd, g in fwd_dates.groupby("signal_date", sort=False)
    }
    # Pre-index daily_basic by date for fast capacity lookup
    daily_basic_by_date: dict[int, pd.DataFrame] = {}

    # Load daily basic for capacity
    with timed_stage("load_daily_basic"):
        daily_basic = pd.DataFrame()
        if capacity_cfg.get("enabled", False):
            print("Loading daily_basic for capacity screening...", flush=True)
            daily_basic = _load_daily_basic(args.start, args.end)
            print(f"  {len(daily_basic)} rows, columns: {list(daily_basic.columns)}", flush=True)
            # Pre-index
            daily_basic_by_date = {
                int(dt): g for dt, g in daily_basic.groupby("trade_date", sort=False)
            }

    # Load log_market_cap_cs for neutralization
    with timed_stage("load_neutralizer"):
        print("Loading log_market_cap_cs for neutralization...", flush=True)
        log_mcap_raw = _load_factor_cache_raw("log_market_cap_cs", args.start, args.end)
        log_mcap_clean = _clean_factor_panel(log_mcap_raw)
        print(f"  {len(log_mcap_clean)} rows after cleaning", flush=True)

    # Process each factor
    input_audits = []
    direction_audits = []
    alignment_audits = []
    ic_rows_all = []
    quantile_rows_all = []
    turnover_cost_all = []
    neutralization_diags = []
    neut_metas: dict[str, dict] = {}
    ic_trends = []
    factor_dfs: dict[str, pd.DataFrame] = {}
    direction_infos: dict[str, dict] = {}
    aligned_panels: dict[str, pd.DataFrame] = {}

    _t0_factor = perf_counter()
    for fi, factor_cfg in enumerate(factors_cfg):
        fname = factor_cfg["name"]
        t0_f = perf_counter()
        role = factor_cfg.get("role", "alpha_candidate")
        print(f"[{fi+1}/{len(factors_cfg)}] Processing {fname} (role={role})...", flush=True)

        # ---- 1. Load raw & audit ----
        raw_df = _load_factor_cache_raw(fname, args.start, args.end)
        audit = _audit_factor_input(factor_cfg, raw_df, fwd, args.start, args.end)
        input_audits.append(audit)

        if raw_df.empty:
            elapsed_f = perf_counter() - t0_f
            print(f"  data: DATA_MISSING (empty cache)")
            direction_audits.append({
                "factor": fname, "direction_audit_status": "FAIL",
                "direction_audit_reason": "empty cache",
                "direction_flipped": False, "selected_direction": "original",
            })
            alignment_audits.append({
                "factor": fname, "horizon": primary_horizon,
                "data_lag_days": factor_cfg.get("data_lag_days", 0),
                "n_observations": 0, "n_aligned_rows": 0,
                "n_unmatured_rows_excluded": 0, "n_signal_dates": 0,
                "calibration_rows": 0, "validation_rows": 0, "watch_rows": 0,
                "no_leakage_status": "NOT_AVAILABLE",
                "alignment_reason": "empty cache",
            })
            diag.log_progress(fname, fi + 1, "input_audit", "DATA_MISSING",
                             elapsed_f, 0, 0, "empty cache")
            _write_partial_csvs(partial_dir, input_audits, direction_audits, alignment_audits,
                               ic_rows_all, quantile_rows_all, turnover_cost_all,
                               neutralization_diags, ic_trends)
            continue

        print(f"  input: {audit['input_audit_status']} ({audit['raw_rows']} raw → {audit['clean_rows']} clean, "
              f"dup_rate={audit['duplicate_key_rate']:.3%}, cov={_pct(audit['median_coverage_pct'])})")

        # ---- 2. Clean panel ----
        clean_df = _clean_factor_panel(raw_df)
        factor_dfs[fname] = clean_df

        # ---- 3. Alignment ----
        aligned_panel, alignment_audit = _build_aligned_panel(
            factor_cfg, clean_df, fwd, primary_horizon,
            cal_start, cal_end, val_start, val_end, watch_start, watch_end,
        )
        alignment_audits.append(alignment_audit)
        print(f"  alignment: {alignment_audit['no_leakage_status']} ({alignment_audit['n_aligned_rows']} rows)")
        aligned_panels[fname] = aligned_panel

        if aligned_panel.empty:
            elapsed_f = perf_counter() - t0_f
            direction_audits.append({
                "factor": fname, "direction_audit_status": "FAIL",
                "direction_audit_reason": "no aligned data",
                "direction_flipped": False, "selected_direction": "original",
            })
            diag.log_progress(fname, fi + 1, "alignment", "NO_ALIGNED_DATA",
                             elapsed_f, len(clean_df), 0, "no aligned data")
            _write_partial_csvs(partial_dir, input_audits, direction_audits, alignment_audits,
                               ic_rows_all, quantile_rows_all, turnover_cost_all,
                               neutralization_diags, ic_trends)
            continue

        # ---- 4. Mcap neutralization ----
        neutralized_panel, neut_meta = _neutralize_by_mcap(fname, aligned_panel, log_mcap_clean, min_neutralizer_cov)
        n_neutral_dates = neut_meta.get("n_neutralized_dates", 0)
        print(f"  neutralization: {n_neutral_dates} dates, coverage={neut_meta.get('neutralizer_coverage_pct', 'NaN')}%, "
              f"size_beta={_num(neut_meta.get('size_beta_mean'), 4)}")

        # ---- 5. Direction audit (on raw aligned data) ----
        direction_info = _audit_factor_direction(
            factor_cfg, aligned_panel, cal_start, cal_end, value_col="value"
        )
        direction_audits.append(direction_info)
        direction_infos[fname] = direction_info
        if direction_info.get("direction_flipped"):
            print(f"  direction: FLIPPED (orig IC={_num(direction_info['calibration_mean_ic_original'], 4)}, "
                  f"rev IC={_num(direction_info['calibration_mean_ic_reversed'], 4)})")
        else:
            print(f"  direction: {direction_info['selected_direction']} "
                  f"(IC={_num(direction_info['calibration_mean_ic_original'], 4)})")

        # Store neutralization meta for later diagnostic
        neut_metas.setdefault(fname, {})
        neut_metas[fname] = neut_meta

        # ---- Computation skip: neutralizer factors skip alpha candidate stages ----
        is_neutralizer = role == "neutralizer"

        # ---- 6. IC by year (raw + neutral) ----
        ic_raw = _compute_ic_by_year(factor_cfg, aligned_panel, direction_info, years_all, "value", "raw")
        ic_neutral = _compute_ic_by_year(factor_cfg, neutralized_panel, direction_info, years_all, "value_mcap_neutral", "mcap_neutral")
        ic_rows_all.extend(ic_raw)
        ic_rows_all.extend(ic_neutral)

        # ---- 7-8. Quantile, turnover, quantile returns (skip for neutralizers) ----
        if not is_neutralizer:
            weighting = factor_cfg.get("tradable_weighting", "equal_weight")
            portfolios_raw = _compute_quantile_portfolios(factor_cfg, aligned_panel, direction_info, "value", weighting, daily_basic)
            portfolios_neutral = _compute_quantile_portfolios(factor_cfg, neutralized_panel, direction_info, "value_mcap_neutral", weighting, daily_basic)

            tc_raw = _compute_real_turnover_cost(factor_cfg, portfolios_raw, fwd, aligned_panel, direction_info, years_all, "value", "raw", weighting, cost_bps)
            tc_neutral = _compute_real_turnover_cost(factor_cfg, portfolios_neutral, fwd, neutralized_panel, direction_info, years_all, "value_mcap_neutral", "mcap_neutral", weighting, cost_bps)
            turnover_cost_all.extend(tc_raw)
            turnover_cost_all.extend(tc_neutral)

            q_raw = _compute_quantile_returns(factor_cfg, aligned_panel, direction_info, years_all, "value", "raw", cost_bps, tc_raw)
            q_neutral = _compute_quantile_returns(factor_cfg, neutralized_panel, direction_info, years_all, "value_mcap_neutral", "mcap_neutral", cost_bps, tc_neutral)
            quantile_rows_all.extend(q_raw)
            quantile_rows_all.extend(q_neutral)
        else:
            # Neutralizer: skip quantile/turnover computation
            print(f"  quantile/turnover: SKIPPED (role=neutralizer)")

        # ---- 9. IC trend ----
        trend_raw = _compute_ic_trend(fname, aligned_panel, direction_info, "value", "raw", val_start, val_end, robustness_cfg.get("ic_decay_p_value", 0.10))
        trend_neutral = _compute_ic_trend(fname, neutralized_panel, direction_info, "value_mcap_neutral", "mcap_neutral", val_start, val_end, robustness_cfg.get("ic_decay_p_value", 0.10))
        ic_trends.append(trend_raw)
        ic_trends.append(trend_neutral)

        # ---- 10. Neutralization diagnostic ----
        nd = _compute_neutralization_diagnostic(factor_cfg, ic_raw, ic_neutral, q_raw if not is_neutralizer else [], q_neutral if not is_neutralizer else [], val_years, neut_metas.get(fname, {}), cfg.get("neutralization", {}))
        neutralization_diags.append(nd)

        # ---- Per-factor progress logging ----
        elapsed_f = perf_counter() - t0_f
        aligned_rows = alignment_audit.get("n_aligned_rows", 0)
        warning_msg = ""
        if elapsed_f > args.warn_factor_seconds:
            warning_msg = f"factor exceeded {args.warn_factor_seconds}s warning threshold"
            print(f"  [WARNING] {warning_msg}", flush=True)
        diag.log_progress(fname, fi + 1, "completed", "OK", elapsed_f,
                         len(clean_df), aligned_rows, warning_msg)
        _write_partial_csvs(partial_dir, input_audits, direction_audits, alignment_audits,
                           ic_rows_all, quantile_rows_all, turnover_cost_all,
                           neutralization_diags, ic_trends)

    _profile["factor_processing"] = perf_counter() - _t0_factor
    print(f"[stage:end]   factor_processing  elapsed={_profile['factor_processing']:.1f}s", flush=True)
    diag.log_stage_timing("factor_processing", _profile["factor_processing"], "OK", len(factors_cfg))

    # ---- 11. Rolling window gate (batch) ----
    rolling_gates_all = []
    if rolling_windows:
        with timed_stage("rolling_window_gate"):
            print("Computing rolling window robustness...", flush=True)
        rolling_windows = robustness_cfg.get("rolling_windows", [])
        for factor_cfg in factors_cfg:
            fname = factor_cfg["name"]
            role = factor_cfg.get("role", "alpha_candidate")
            # Skip DATA_MISSING and neutralizer factors
            if fname not in direction_infos:
                rg = [{"factor": fname, "window": rw["name"], "basis": "raw",
                       "window_gate_status": "NOT_AVAILABLE",
                       "window_start": rw["start"], "window_end": rw["end"],
                       "primary": rw.get("primary", False),
                       "window_years": 4, "mean_ic": float("nan"), "icir": float("nan"),
                       "net_spread": float("nan"), "positive_ic_years": 0,
                       "positive_spread_years": 0, "failure_reasons": "no data"}
                      for rw in rolling_windows]
                rolling_gates_all.extend(rg)
                continue
            f_ic = [r for r in ic_rows_all if r["factor"] == fname]
            f_q = [r for r in quantile_rows_all if r["factor"] == fname]
            f_di = direction_infos.get(fname, {})
            if f_ic and f_q:
                rg = _compute_rolling_window_gate(factor_cfg, f_ic, f_q, f_di, rolling_windows, gate_cfg)
            else:
                rg = [{"factor": fname, "window": rw["name"], "basis": "raw",
                       "window_gate_status": "NOT_AVAILABLE",
                       "window_start": rw["start"], "window_end": rw["end"],
                       "primary": rw.get("primary", False),
                       "window_years": 4, "mean_ic": float("nan"), "icir": float("nan"),
                       "net_spread": float("nan"), "positive_ic_years": 0,
                       "positive_spread_years": 0, "failure_reasons": "no data"}
                      for rw in rolling_windows]
            rolling_gates_all.extend(rg)
        diag.log_stage_timing("rolling_window_gate",
                             _profile.get("rolling_window_gate", 0), "OK", len(rolling_gates_all))
    else:
        print("Rolling windows: none configured, skipping", flush=True)

    # ---- 12. Capacity audit (skip for neutralizer + DATA_MISSING factors) ----
    capacity_audits_all = []
    if capacity_cfg.get("enabled", False) and not daily_basic.empty:
        with timed_stage("capacity_audit"):
            print("Computing capacity audit...", flush=True)
        for factor_cfg in factors_cfg:
            fname = factor_cfg["name"]
            role = factor_cfg.get("role", "alpha_candidate")
            # Skip neutralizers and DATA_MISSING
            if role != "alpha_candidate":
                continue
            if fname not in aligned_panels or aligned_panels[fname].empty:
                continue
            ap = aligned_panels[fname]
            di = direction_infos.get(fname, {})
            w = factor_cfg.get("tradable_weighting", "equal_weight")
            ca = _compute_capacity_audit(factor_cfg, ap, di, "value", "raw", daily_basic, val_years, capacity_cfg, w, daily_basic_by_date)
            capacity_audits_all.extend(ca)
        diag.log_stage_timing("capacity_audit",
                             _profile.get("capacity_audit", 0), "OK", len(capacity_audits_all))
    else:
        print("Capacity audit: disabled or no daily_basic data, writing header-only", flush=True)

    # ---- 13. Regime breakdown (skip if --skip-regime) ----
    regime_breakdowns_all = []
    if not args.skip_regime:
        with timed_stage("regime_breakdown"):
            print("Computing regime breakdown...", flush=True)
        for factor_cfg in factors_cfg:
            fname = factor_cfg["name"]
            if fname not in aligned_panels:
                continue
            ap = aligned_panels[fname]
            di = direction_infos.get(fname, {})
            rb = _compute_regime_breakdown(factor_cfg, ap, di, "value", "raw", years_all)
            regime_breakdowns_all.extend(rb)
        diag.log_stage_timing("regime_breakdown",
                             _profile.get("regime_breakdown", 0), "OK", len(regime_breakdowns_all))
    else:
        print("Regime breakdown: skipped (--skip-regime)", flush=True)

    # ---- 14. Initial quality gate (needed for correlation clusters) ----
    with timed_stage("quality_gate"):
        print("Applying initial quality gate...", flush=True)
    gate_results = []
    for factor_cfg in factors_cfg:
        fname = factor_cfg["name"]
        audit = next((a for a in input_audits if a["factor"] == fname), {})
        al_audit = next((a for a in alignment_audits if a["factor"] == fname), {})
        di = direction_infos.get(fname, {})
        ic_r = [r for r in ic_rows_all if r["factor"] == fname and r["basis"] == "raw"]
        ic_n = [r for r in ic_rows_all if r["factor"] == fname and r["basis"] == "mcap_neutral"]
        q_r = [r for r in quantile_rows_all if r["factor"] == fname and r["basis"] == "raw"]
        q_n = [r for r in quantile_rows_all if r["factor"] == fname and r["basis"] == "mcap_neutral"]
        tc_r = [r for r in turnover_cost_all if r["factor"] == fname]
        trend = next((t for t in ic_trends if t["factor"] == fname and t["basis"] == "raw"), {})
        rg = [r for r in rolling_gates_all if r["factor"] == fname]
        ca = [r for r in capacity_audits_all if r["factor"] == fname]

        nd = next((d for d in neutralization_diags if d["factor"] == fname), None)
        result = _apply_quality_gate(
            factor_cfg, audit, al_audit, di,
            ic_r, ic_n, q_r, q_n, tc_r,
            trend, rg, ca,
            gate_cfg, gate_basis_cfg, robustness_cfg, capacity_cfg,
            neutralization_diag=nd,
            neutralization_cfg=cfg.get("neutralization", {}),
        )
        gate_results.append(result)
        print(f"  {fname}: {result['quality_gate_status']} ({result['n_failures']} failures)")

    # ---- 15. Correlation clusters (with gate_score) ----
    correlation_clusters = pd.DataFrame()
    if not args.skip_correlation:
        with timed_stage("correlation_clusters"):
            print("Computing correlation clusters...", flush=True)
        correlation_clusters = _compute_correlation_clusters(
            factor_dfs, fwd, direction_infos, factors_cfg, gate_results, corr_threshold
        )
        if not correlation_clusters.empty:
            print(f"  {correlation_clusters['cluster_id'].nunique()} clusters found "
                  f"({len(correlation_clusters)} factors)")
        diag.log_stage_timing("correlation_clusters",
                             _profile.get("correlation_clusters", 0), "OK",
                             len(correlation_clusters))
    else:
        print("Correlation clusters: skipped (--skip-correlation)", flush=True)

    # ---- 16. Candidate pool ----
    print("Generating candidate pool...", flush=True)
    pool_path = run_dir / "factor_candidate_pool.yaml"
    pool = _generate_candidate_pool(gate_results, factors_cfg, correlation_clusters, pool_path)
    print(f"  {pool['recommendation']}")

    # ---- 17. Write outputs (to atomic run_dir first) ----
    pd.DataFrame(input_audits).to_csv(run_dir / "factor_input_audit.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(direction_audits).to_csv(run_dir / "factor_direction_audit.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(alignment_audits).to_csv(run_dir / "factor_alignment_audit.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(ic_rows_all).to_csv(run_dir / "factor_ic_by_year.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(quantile_rows_all).to_csv(run_dir / "factor_quantile_returns.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(turnover_cost_all).to_csv(run_dir / "factor_turnover_cost.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(neutralization_diags).to_csv(run_dir / "factor_neutralization_diagnostic.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(ic_trends).to_csv(run_dir / "factor_ic_trend.csv", index=False, encoding="utf-8-sig")
    _write_csv_safe(run_dir / "factor_rolling_window_gate.csv", rolling_gates_all, ROLLING_WINDOW_GATE_COLUMNS)
    _write_csv_safe(run_dir / "factor_correlation_cluster.csv",
                    correlation_clusters.to_dict("records") if not correlation_clusters.empty else [],
                    CORRELATION_CLUSTER_COLUMNS)
    _write_csv_safe(run_dir / "factor_capacity_audit.csv", capacity_audits_all, CAPACITY_AUDIT_COLUMNS)
    _write_csv_safe(run_dir / "factor_regime_breakdown.csv", regime_breakdowns_all, REGIME_BREAKDOWN_COLUMNS)

    # Remove _gate_meta column from gate CSV
    gate_df = pd.DataFrame(gate_results)
    if "_gate_meta" in gate_df.columns:
        gate_df = gate_df.drop(columns=["_gate_meta"])
    gate_df.to_csv(run_dir / "factor_quality_gate.csv", index=False, encoding="utf-8-sig")

    print(f"Wrote atomic outputs to {run_dir}")

    # ---- 18. Report (write to atomic dir first) ----
    _write_report(
        run_dir / "factor_quality_rebuild_report.md", input_audits, direction_audits, alignment_audits,
        ic_rows_all, quantile_rows_all, turnover_cost_all,
        neutralization_diags, ic_trends, rolling_gates_all,
        correlation_clusters, capacity_audits_all, regime_breakdowns_all,
        gate_results, pool,
        config_path=args.config,
        config_sha256=config_sha256,
        seed=args.seed,
    )

    # ---- 19. Publish: copy only official outputs to out-dir root ----
    published = _publish_outputs(out_dir, run_dir, out_doc)
    print(f"Published {published} files to {out_dir}", flush=True)
    print(f"Wrote report to {out_doc}", flush=True)

    # ---- 20. Profile output (always write to run_dir) ----
    total_elapsed = sum(_profile.values())
    status_counts: dict[str, int] = {}
    for g in gate_results:
        s = g["quality_gate_status"]
        status_counts[s] = status_counts.get(s, 0) + 1
    profile_data = {
        "run_id": run_id,
        "config_path": args.config,
        "config_sha256": config_sha256,
        "seed": args.seed,
        "cli_args": {
            "start": args.start,
            "end": args.end,
            "out_dir": args.out_dir,
            "out_doc": args.out_doc,
        },
        "environment": {
            "python_version": _PYTHON_VERSION,
            "numpy_version": _NUMPY_VERSION,
            "pandas_version": _PANDAS_VERSION,
            "scipy_version": _SCIPY_VERSION,
        },
        "run_summary": {
            "total_factors": len(factors_cfg),
            **{s.lower(): status_counts.get(s, 0)
               for s in ["PASS", "WATCH_SIZE_DEPENDENT", "WATCH_NEUTRAL_ONLY",
                         "WATCH_IC_DECAY", "WATCH_WINDOW_FRAGILE",
                         "WATCH_CAPACITY_CONSTRAINED", "WATCH_NEUTRAL_UNAVAILABLE",
                         "DATA_MISSING", "SUPPORT", "FAIL"]},
            "recommendation": pool.get("recommendation", "N/A"),
        },
        "config_warnings": config_warnings,
        "started_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "total_elapsed_sec": round(total_elapsed, 1),
        "stages": [{"name": k, "elapsed_sec": round(v, 1)} for k, v in _profile.items()],
    }
    # Always write profile to run_dir
    (run_dir / "profile.json").write_text(
        json.dumps(profile_data, indent=2, ensure_ascii=False), encoding="utf-8")
    # Optionally write to --profile-out
    if args.profile_out:
        profile_path = Path(args.profile_out)
        profile_path.parent.mkdir(parents=True, exist_ok=True)
        profile_path.write_text(json.dumps(profile_data, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Wrote profile to {profile_path}", flush=True)

    slowest = sorted(_profile.items(), key=lambda x: x[1], reverse=True)[:5]
    print("Slowest 5 stages:", flush=True)
    for name, elapsed in slowest:
        print(f"  {name}: {elapsed:.1f}s", flush=True)
    if config_warnings:
        print(f"Config warnings ({len(config_warnings)}):", flush=True)
        for w in config_warnings:
            print(f"  {w}", flush=True)

    # ---- Mark run as successful ----
    diag.mark_success()

    print("\nDone.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

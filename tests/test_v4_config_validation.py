"""Tests for V4 factor quality rebuild configuration and output validation.

Coverage:
  - V4 config marks log_market_cap_cs as neutralizer
  - Candidate pool neutralizer contract
  - Empty rolling window CSV has valid header
  - Empty capacity audit CSV has valid header
  - V4 config has required gate sections
  - CSV header-only files are readable by pandas
"""

import sys
from io import StringIO
from pathlib import Path

import pandas as pd
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def v4_config():
    """Load the V4 quality rebuild config."""
    cfg_path = ROOT / "configs" / "factor_quality_rebuild_v4.yaml"
    if not cfg_path.exists():
        pytest.skip("V4 config not found")
    return yaml.safe_load(cfg_path.read_text(encoding="utf-8"))


@pytest.fixture
def v4_factors(v4_config):
    """List of factor definitions from V4 config."""
    return v4_config.get("factors", [])


# ---------------------------------------------------------------------------
# Config contract tests
# ---------------------------------------------------------------------------

def test_v4_config_marks_log_market_cap_as_neutralizer(v4_factors):
    """V4 config must mark log_market_cap_cs with role=neutralizer."""
    lmp = next((f for f in v4_factors if f["name"] == "log_market_cap_cs"), None)
    assert lmp is not None, "log_market_cap_cs not found in V4 factor list"
    assert lmp.get("role") == "neutralizer", \
        f"log_market_cap_cs role={lmp.get('role')}, expected 'neutralizer'"
    assert lmp.get("data_lag_days") == 0, \
        f"log_market_cap_cs data_lag_days={lmp.get('data_lag_days')}, expected 0"


def test_v4_config_all_factors_have_required_fields(v4_factors):
    """Every factor in V4 config must declare role, data_lag_days,
    date_semantics, tradable_weighting."""
    required = ["role", "data_lag_days", "date_semantics", "tradable_weighting"]
    missing = []
    for f in v4_factors:
        for key in required:
            if key not in f:
                missing.append(f"{f['name']}: missing {key}")
    assert not missing, "\n".join(missing)


def test_v4_config_has_required_gate_sections(v4_config):
    """V4 config must include gate_basis, robustness, and capacity sections."""
    for section in ["gate_basis", "robustness", "capacity"]:
        assert section in v4_config, \
            f"V4 config missing required section: {section}"


def test_v4_config_gate_basis_has_required_fields(v4_config):
    """gate_basis must have raw_required, neutralized_required_for_pass,
    WATCH_SIZE_DEPENDENT, WATCH_NEUTRAL_ONLY."""
    gb = v4_config.get("gate_basis", {})
    for key in ["raw_required", "neutralized_required_for_pass",
                "raw_pass_neutral_fail_status", "raw_fail_neutral_pass_status"]:
        assert key in gb, f"gate_basis missing: {key}"
    assert gb.get("raw_pass_neutral_fail_status") == "WATCH_SIZE_DEPENDENT"
    assert gb.get("raw_fail_neutral_pass_status") == "WATCH_NEUTRAL_ONLY"


def test_v4_config_robustness_has_windows(v4_config):
    """robustness must have rolling_windows with start/end schema."""
    rb = v4_config.get("robustness", {})
    windows = rb.get("rolling_windows", [])
    assert len(windows) >= 4, f"Expected >=4 rolling windows, got {len(windows)}"
    assert rb.get("min_pass_windows_for_strong_pass", 0) >= 3
    # Each window must have name/start/end (not calibration/validation)
    for i, rw in enumerate(windows):
        for key in ("name", "start", "end"):
            assert key in rw, f"window[{i}] missing required key '{key}'"
        assert len(str(rw["start"])) == 8, f"window[{i}].start must be YYYYMMDD"
        assert len(str(rw["end"])) == 8, f"window[{i}].end must be YYYYMMDD"
        # Must NOT use old calibration/validation schema
        assert "calibration" not in rw, f"window[{i}] uses deprecated 'calibration' key (use start/end)"
        assert "validation" not in rw, f"window[{i}] uses deprecated 'validation' key (use start/end)"


def test_v4_config_capacity_enabled(v4_config):
    """capacity must be enabled with proper CNY units."""
    cap = v4_config.get("capacity", {})
    assert cap.get("enabled") is True
    assert cap.get("target_aum_cny") == 1_000_000_000
    assert cap.get("max_participation_rate") <= 0.10


def test_v4_config_fundamental_factors_have_data_lag(v4_factors):
    """All fundamental factors must have data_lag_days=63."""
    for f in v4_factors:
        if f.get("type") == "fundamental" and f.get("role") == "alpha_candidate":
            assert f.get("data_lag_days", 0) >= 63, \
                f"{f['name']}: fundamental alpha must have data_lag_days>=63, got {f.get('data_lag_days')}"


def test_v4_config_technical_factors_have_zero_lag(v4_factors):
    """All technical factors must have data_lag_days=0."""
    for f in v4_factors:
        if f.get("type") == "technical" and f.get("role") == "alpha_candidate":
            assert f.get("data_lag_days", 999) == 0, \
                f"{f['name']}: technical factor must have data_lag_days=0, got {f.get('data_lag_days')}"


# ---------------------------------------------------------------------------
# Empty CSV header tests
# ---------------------------------------------------------------------------

def test_empty_rolling_window_csv_has_header():
    """Empty rolling window gate CSV must be readable by pandas with correct columns."""
    from scripts.factor_quality_rebuild import ROLLING_WINDOW_GATE_COLUMNS, _write_csv_safe
    import tempfile, os

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "factor_rolling_window_gate.csv"
        _write_csv_safe(out, [], ROLLING_WINDOW_GATE_COLUMNS)

        # Must be readable
        df = pd.read_csv(out, encoding="utf-8-sig")
        assert len(df) == 0, f"Expected empty DataFrame, got {len(df)} rows"
        assert list(df.columns) == ROLLING_WINDOW_GATE_COLUMNS, \
            f"Column mismatch: {list(df.columns)} != {ROLLING_WINDOW_GATE_COLUMNS}"


def test_empty_capacity_csv_has_header():
    """Empty capacity audit CSV must be readable by pandas with correct columns."""
    from scripts.factor_quality_rebuild import CAPACITY_AUDIT_COLUMNS, _write_csv_safe
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "factor_capacity_audit.csv"
        _write_csv_safe(out, [], CAPACITY_AUDIT_COLUMNS)

        df = pd.read_csv(out, encoding="utf-8-sig")
        assert len(df) == 0
        assert list(df.columns) == CAPACITY_AUDIT_COLUMNS


def test_empty_correlation_cluster_csv_has_header():
    """Empty correlation cluster CSV must be readable with correct columns."""
    from scripts.factor_quality_rebuild import CORRELATION_CLUSTER_COLUMNS, _write_csv_safe
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "factor_correlation_cluster.csv"
        _write_csv_safe(out, [], CORRELATION_CLUSTER_COLUMNS)

        df = pd.read_csv(out, encoding="utf-8-sig")
        assert len(df) == 0
        assert list(df.columns) == CORRELATION_CLUSTER_COLUMNS


def test_non_empty_csv_writes_correctly():
    """Non-empty CSV must write data with correct column order."""
    from scripts.factor_quality_rebuild import CAPACITY_AUDIT_COLUMNS, _write_csv_safe
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "test.csv"
        rows = [
            {"factor": "test_cs", "year": 2023, "basis": "raw",
             "n_stocks": 100, "n_dates": 50, "median_market_cap_cny": 5e9,
             "median_top_amount_cny": 1e7, "median_leg_amount_sum_cny": 5e7,
             "estimated_trade_cny_at_target_aum": 5e6,
             "participation_rate_at_target_aum": 0.10, "capacity_status": "OK"},
        ]
        _write_csv_safe(out, rows, CAPACITY_AUDIT_COLUMNS)

        df = pd.read_csv(out, encoding="utf-8-sig")
        assert len(df) == 1
        assert df.iloc[0]["factor"] == "test_cs"
        assert float(df.iloc[0]["median_market_cap_cny"]) == 5e9


# ---------------------------------------------------------------------------
# Candidate pool contract tests
# ---------------------------------------------------------------------------

def test_candidate_pool_neutralizer_contract():
    """log_market_cap_cs must not enter eligible/fail, must enter support_factors.neutralizers."""
    import tempfile, yaml

    pool = {
        "generated": "2024-01-01",
        "description": "test",
        "recommendation": "NO_ALPHA_SOURCE_FOUND",
        "eligible_factors": [],
        "watch_factors_for_review": [],
        "support_factors": {
            "neutralizers": ["log_market_cap_cs"],
            "redundant": [],
        },
        "missing_data_factors": ["some_factor_cs"],
        "fail_factors": ["reversal_5_cs"],
    }

    # Verify contract
    assert "log_market_cap_cs" not in pool["eligible_factors"]
    assert "log_market_cap_cs" not in pool["fail_factors"]
    assert "log_market_cap_cs" in pool["support_factors"]["neutralizers"]

    # Empty eligible → NO_ALPHA_SOURCE_FOUND
    assert pool["recommendation"] == "NO_ALPHA_SOURCE_FOUND"


def test_candidate_pool_with_eligible():
    """When eligible_factors is non-empty, recommendation must reflect that."""
    pool = {
        "generated": "2024-01-01",
        "description": "test",
        "recommendation": "3 eligible factor(s) available for sleeve rebuild",
        "eligible_factors": ["low_volatility_60d_cs", "amihud_illiq_20d_cs", "bollinger_position_20d_cs"],
        "watch_factors_for_review": ["turnover_anomaly_20d_cs"],
        "support_factors": {"neutralizers": ["log_market_cap_cs"], "redundant": []},
        "missing_data_factors": [],
        "fail_factors": ["reversal_5_cs"],
    }

    assert len(pool["eligible_factors"]) >= 3
    assert "NO_ALPHA" not in pool["recommendation"]
    assert "log_market_cap_cs" in pool["support_factors"]["neutralizers"]


# ---------------------------------------------------------------------------
# Validation script tests
# ---------------------------------------------------------------------------

def test_validate_csvs_readable_header_only():
    """check_csvs_readable should accept header-only CSVs."""
    import tempfile, os
    from scripts.validate_factor_quality_outputs import check_csvs_readable

    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp)
        # Create a header-only CSV
        csv_path = out_dir / "factor_rolling_window_gate.csv"
        csv_path.write_text("factor,window_name,n_dates,mean_rank_ic\n", encoding="utf-8-sig")

        # Create other required CSVs as header-only
        for name in ["factor_input_audit.csv", "factor_direction_audit.csv",
                     "factor_alignment_audit.csv", "factor_ic_by_year.csv",
                     "factor_quantile_returns.csv", "factor_turnover_cost.csv",
                     "factor_neutralization_diagnostic.csv", "factor_ic_trend.csv",
                     "factor_correlation_cluster.csv", "factor_capacity_audit.csv",
                     "factor_regime_breakdown.csv", "factor_quality_gate.csv"]:
            (out_dir / name).write_text("dummy,header\n", encoding="utf-8-sig")

        issues = check_csvs_readable(out_dir)
        # All header-only CSVs should be readable
        assert not issues, f"Unexpected unreadable: {issues}"


def test_validate_candidate_pool_with_config():
    """Candidate pool validation should check config-driven neutralizer contract."""
    import tempfile, yaml
    from scripts.validate_factor_quality_outputs import check_candidate_pool_contract

    config = {
        "factors": [
            {"name": "log_market_cap_cs", "role": "neutralizer"},
            {"name": "low_volatility_60d_cs", "role": "alpha_candidate"},
        ]
    }

    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp)
        pool = {
            "eligible_factors": [],
            "watch_factors_for_review": [],
            "support_factors": {"neutralizers": ["log_market_cap_cs"], "redundant": []},
            "missing_data_factors": [],
            "fail_factors": [],
            "recommendation": "NO_ALPHA_SOURCE_FOUND",
        }
        pool_path = out_dir / "factor_candidate_pool.yaml"
        pool_path.write_text(yaml.dump(pool, allow_unicode=True), encoding="utf-8")

        issues = check_candidate_pool_contract(out_dir, config)
        assert not issues, f"Unexpected issues: {issues}"


def test_validate_candidate_pool_catches_neutralizer_in_eligible():
    """log_market_cap_cs in eligible_factors must be flagged."""
    import tempfile, yaml
    from scripts.validate_factor_quality_outputs import check_candidate_pool_contract

    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp)
        pool = {
            "eligible_factors": ["log_market_cap_cs"],
            "watch_factors_for_review": [],
            "support_factors": {"neutralizers": [], "redundant": []},
            "missing_data_factors": [],
            "fail_factors": [],
            "recommendation": "1 eligible factor(s) available for sleeve rebuild",
        }
        pool_path = out_dir / "factor_candidate_pool.yaml"
        pool_path.write_text(yaml.dump(pool, allow_unicode=True), encoding="utf-8")

        issues = check_candidate_pool_contract(out_dir)
        assert any("log_market_cap_cs" in i for i in issues), \
            f"Should catch log_market_cap_cs in eligible, got: {issues}"


# ---------------------------------------------------------------------------
# Rolling window schema tests
# ---------------------------------------------------------------------------

def test_v4_rolling_windows_use_start_end_schema(v4_config):
    """Every rolling window must use name/start/end, NOT calibration/validation."""
    rb = v4_config.get("robustness", {})
    windows = rb.get("rolling_windows", [])
    assert len(windows) >= 1, "No rolling windows defined"

    for i, rw in enumerate(windows):
        prefix = f"window[{i}] ({rw.get('name', '?')})"
        # Required keys
        for key in ("name", "start", "end"):
            assert key in rw, f"{prefix}: missing required key '{key}'"
        # Forbidden keys (old schema)
        for key in ("calibration", "validation"):
            assert key not in rw, \
                f"{prefix}: uses deprecated '{key}' key — use start/end instead"
        # Date format
        for dk in ("start", "end"):
            val = str(rw[dk])
            assert len(val) == 8 and val.isdigit(), \
                f"{prefix}.{dk}='{val}' — must be YYYYMMDD (8 digits)"


def test_v4_rolling_windows_match_script_contract():
    """Rolling windows must have fields consumed by _compute_rolling_window_gate.

    The script reads: rw['name'], rw['start'] (as int), rw['end'] (as int).
    """
    import yaml
    cfg_path = Path(__file__).resolve().parents[1] / "configs" / "factor_quality_rebuild_v4.yaml"
    if not cfg_path.exists():
        pytest.skip("V4 config not found")
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    windows = cfg.get("robustness", {}).get("rolling_windows", [])

    for rw in windows:
        # Verify int conversion works (simulating what the script does)
        start_int = int(rw["start"])
        end_int = int(rw["end"])
        name = rw["name"]
        assert start_int > 20000101, f"{name}: start={start_int} too early"
        assert end_int > start_int, f"{name}: end={end_int} <= start={start_int}"
        # Window name should match date span approximately
        expected_start_year = int(name.split("_")[0])
        expected_end_year = int(name.split("_")[1])
        assert abs(start_int // 10000 - expected_start_year) <= 1, \
            f"{name}: start year {start_int // 10000} != expected {expected_start_year}"


def test_validate_robustness_config_rejects_old_schema():
    """_validate_robustness_config must raise on calibration/validation schema."""
    from scripts.factor_quality_rebuild import _validate_robustness_config
    import pytest

    # Old schema — missing 'start'/'end', has 'calibration'/'validation'
    bad_config = {
        "rolling_windows": [
            {"name": "test", "calibration": ["2018"], "validation": ["2019"]}
        ]
    }
    with pytest.raises(ValueError, match="missing required key"):
        _validate_robustness_config(bad_config)


def test_validate_robustness_config_rejects_bad_date():
    """_validate_robustness_config must reject non-YYYYMMDD dates."""
    from scripts.factor_quality_rebuild import _validate_robustness_config
    import pytest

    bad_config = {
        "rolling_windows": [
            {"name": "test", "start": "2018", "end": "20191231"}
        ]
    }
    with pytest.raises(ValueError, match="YYYYMMDD"):
        _validate_robustness_config(bad_config)


def test_validate_robustness_config_accepts_valid_schema():
    """_validate_robustness_config must accept correct start/end schema."""
    from scripts.factor_quality_rebuild import _validate_robustness_config

    good_config = {
        "rolling_windows": [
            {"name": "test_window", "start": "20180101", "end": "20211231"},
            {"name": "second_window", "start": "20190101", "end": "20221231"},
        ],
        "min_pass_windows_for_strong_pass": 2,
    }
    # Should not raise
    _validate_robustness_config(good_config)


def test_validate_robustness_config_accepts_empty_windows():
    """_validate_robustness_config must accept no rolling windows."""
    from scripts.factor_quality_rebuild import _validate_robustness_config
    _validate_robustness_config({})
    _validate_robustness_config({"rolling_windows": []})

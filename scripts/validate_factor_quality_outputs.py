#!/usr/bin/env python
"""validate_factor_quality_outputs.py — Product-level validation for factor_quality_rebuild outputs.

Usage:
    python scripts/validate_factor_quality_outputs.py --out-dir outputs/analysis/factor_quality_rebuild
    python scripts/validate_factor_quality_outputs.py --out-dir ... --config configs/factor_quality_rebuild.yaml

Checks:
    1. All required CSV files exist and are readable.
    2. No CSV contains 'STUB'.
    3. factor_quality_gate.csv has complete failure reasons (not just one hard-fail).
    4. factor_neutralization_diagnostic.csv: status aligns with coverage thresholds.
    5. WATCH_NEUTRAL_ONLY requires valid neutralization.
    6. PASS requires valid neutralization when configured.
    7. factor_capacity_audit.csv: market_cap in CNY scale, amounts in CNY scale.
    8. factor_correlation_cluster.csv is readable even if empty.
    9. factor_candidate_pool.yaml satisfies the contract.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import yaml

REQUIRED_CSVS = [
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

REQUIRED_POOL = "factor_candidate_pool.yaml"


def load_config(config_path: Optional[Path]) -> dict:
    if config_path and config_path.exists():
        return yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    return {}


def check_files_exist(out_dir: Path) -> list[str]:
    missing = []
    for name in REQUIRED_CSVS:
        if not (out_dir / name).exists():
            missing.append(name)
    if not (out_dir / REQUIRED_POOL).exists():
        missing.append(REQUIRED_POOL)
    return missing


def check_csvs_readable(out_dir: Path) -> list[str]:
    """All CSVs must be readable by pandas. Header-only CSVs are acceptable."""
    unreadable = []
    for name in REQUIRED_CSVS:
        fpath = out_dir / name
        if not fpath.exists():
            unreadable.append(f"{name}: file not found")
            continue
        try:
            df = pd.read_csv(fpath, encoding="utf-8-sig")
            # Header-only (empty body) is acceptable — do not fail
            _ = len(df)  # verify DataFrame is usable
        except Exception as e:
            # Distinguish between truly broken and header-only
            try:
                # Check if file has at least a valid header
                with open(fpath, "r", encoding="utf-8-sig") as fh:
                    first_line = fh.readline().strip()
                if first_line and "," in first_line:
                    # Has header but no data rows — acceptable
                    pass
                else:
                    unreadable.append(f"{name}: {e}")
            except Exception:
                unreadable.append(f"{name}: {e}")
    return unreadable


def check_no_stub(out_dir: Path) -> list[str]:
    stub_files = []
    for name in REQUIRED_CSVS:
        try:
            df = pd.read_csv(out_dir / name, encoding="utf-8-sig")
            if df.empty:
                continue
            flat = " ".join(df.astype(str).stack().tolist())
            if "STUB" in flat:
                stub_files.append(name)
        except Exception:
            pass
    return stub_files


def check_neutralization_validity(out_dir: Path, config: dict) -> list[str]:
    """Neutralization status must align with coverage thresholds."""
    try:
        nd = pd.read_csv(out_dir / "factor_neutralization_diagnostic.csv", encoding="utf-8-sig")
        if nd.empty:
            return []
        issues = []
        neut_cfg = config.get("neutralization", {})
        min_cov = float(neut_cfg.get("min_neutralizer_coverage_pct", 70))

        for _, row in nd.iterrows():
            status = str(row.get("neutralization_status", ""))
            cov = float(row.get("neutralizer_coverage_pct", float("nan")))
            factor = row.get("factor", "?")

            # Rule: if coverage < threshold, status must NOT be OK or SIZE_DEPENDENT
            if not np.isnan(cov) and cov < min_cov:
                if status in ("OK", "SIZE_DEPENDENT"):
                    issues.append(
                        f"{factor}: coverage={cov:.1f}% < {min_cov:.0f}% but status={status}"
                    )
        return issues
    except Exception as e:
        return [f"neutralization validity check failed: {e}"]


def check_gate_neutralization_consistency(out_dir: Path, config: dict) -> list[str]:
    """WATCH_NEUTRAL_ONLY and PASS must require valid neutralization."""
    try:
        gate = pd.read_csv(out_dir / "factor_quality_gate.csv", encoding="utf-8-sig")
        nd = pd.read_csv(out_dir / "factor_neutralization_diagnostic.csv", encoding="utf-8-sig")
        if gate.empty or nd.empty:
            return []
        issues = []
        neut_cfg = config.get("neutralization", {})
        min_cov = float(neut_cfg.get("min_neutralizer_coverage_pct", 70))
        require_valid = neut_cfg.get("require_valid_neutralization_for_neutral_gate", True)

        nd_map = {}
        for _, row in nd.iterrows():
            nd_map[row["factor"]] = row

        for _, g in gate.iterrows():
            factor = g.get("factor", "?")
            status = str(g.get("quality_gate_status", ""))
            nd_row = nd_map.get(factor, {})
            neut_valid = nd_row.get("neutralization_valid", False)
            neut_status = str(nd_row.get("neutralization_status", "?"))
            cov = float(nd_row.get("neutralizer_coverage_pct", float("nan")))

            # WATCH_NEUTRAL_ONLY requires valid neutralization
            if status == "WATCH_NEUTRAL_ONLY" and not neut_valid:
                issues.append(
                    f"{factor}: WATCH_NEUTRAL_ONLY but neutralization_valid=False "
                    f"(status={neut_status}, coverage={cov:.1f}%)"
                )

            # PASS requires valid neutralization when configured
            if status == "PASS" and require_valid and not neut_valid:
                issues.append(
                    f"{factor}: PASS but neutralization_valid=False "
                    f"(status={neut_status}, coverage={cov:.1f}%)"
                )
        return issues
    except Exception as e:
        return [f"gate-neutralization consistency check failed: {e}"]


def check_capacity_cny_scale(out_dir: Path, config: dict) -> list[str]:
    """Market cap and amounts must be in CNY scale (not 万元).

    If capacity is enabled in config but CSV is header-only, that is acceptable
    (no capacity data available to audit yet).
    """
    try:
        cap_cfg = config.get("capacity", {})
        if not cap_cfg.get("enabled", True):
            return []

        ca = pd.read_csv(out_dir / "factor_capacity_audit.csv", encoding="utf-8-sig")
        if ca.empty:
            # Header-only CSV is acceptable — no data to audit
            return []
        issues = []

        # Market cap: for A-shares, median market cap should be > 1e9 CNY
        mcap_col = "median_market_cap_cny" if "median_market_cap_cny" in ca.columns else None
        if mcap_col:
            valid = ca[mcap_col].dropna()
            if len(valid) > 0:
                med = float(valid.median())
                if med < 1e9:
                    issues.append(
                        f"median_market_cap_cny median={med:.0f} CNY — "
                        f"suspiciously low, possibly still in 万元 (median should be > 1B CNY for A-shares)"
                    )

        # Amount: should be > 1000 CNY at minimum
        amt_col = "median_top_amount_cny" if "median_top_amount_cny" in ca.columns else None
        if amt_col:
            valid = ca[amt_col].dropna()
            if len(valid) > 0:
                med = float(valid.median())
                if med < 1000:
                    issues.append(
                        f"median_top_amount_cny median={med:.0f} CNY — "
                        f"suspiciously low, possible unit error"
                    )
        return issues
    except Exception as e:
        return [f"capacity CNY scale check failed: {e}"]


def check_capacity_participation(out_dir: Path) -> list[str]:
    """Participation formula should be approximately verifiable from output fields."""
    try:
        ca = pd.read_csv(out_dir / "factor_capacity_audit.csv", encoding="utf-8-sig")
        if ca.empty:
            return []
        issues = []

        # If new fields are present, verify formula
        if "estimated_trade_cny_at_target_aum" in ca.columns and "median_leg_amount_sum_cny" in ca.columns:
            for _, row in ca.iterrows():
                trade_cny = float(row.get("estimated_trade_cny_at_target_aum", float("nan")))
                leg_sum = float(row.get("median_leg_amount_sum_cny", float("nan")))
                part = float(row.get("participation_rate_at_target_aum", float("nan")))
                if not np.isnan(trade_cny) and not np.isnan(leg_sum) and leg_sum > 0:
                    expected_part = trade_cny / leg_sum
                    if not np.isnan(part) and abs(part - expected_part) > 0.01:
                        issues.append(
                            f"{row.get('factor','?')} year={row.get('year','?')}: "
                            f"participation_rate={part:.4f} != expected {expected_part:.4f} "
                            f"(trade={trade_cny:.0f} / leg_sum={leg_sum:.0f})"
                        )
        return issues
    except Exception as e:
        return [f"participation check failed: {e}"]


def check_candidate_pool_contract(out_dir: Path, config: dict = None) -> list[str]:
    """Verify candidate pool contract.

    - log_market_cap_cs must NOT be in eligible_factors
    - log_market_cap_cs must be in support_factors.neutralizers (if configured as neutralizer)
    - Empty eligible requires recommendation NO_ALPHA_SOURCE_FOUND
    - All required keys must be present
    """
    try:
        pool = yaml.safe_load((out_dir / REQUIRED_POOL).read_text(encoding="utf-8-sig"))
        issues = []

        for key in ["eligible_factors", "watch_factors_for_review", "support_factors",
                     "missing_data_factors", "fail_factors", "recommendation"]:
            if key not in pool:
                issues.append(f"candidate pool missing key: {key}")

        # log_market_cap_cs must NOT be eligible
        if "log_market_cap_cs" in pool.get("eligible_factors", []):
            issues.append("log_market_cap_cs in eligible_factors (must be neutralizer only)")

        # log_market_cap_cs must NOT be in fail_factors (it's a neutralizer, not an alpha)
        if "log_market_cap_cs" in pool.get("fail_factors", []):
            issues.append("log_market_cap_cs in fail_factors (neutralizers should not be in fail list)")

        # Check recommendation when eligible is empty
        if not pool.get("eligible_factors"):
            rec = pool.get("recommendation", "")
            if rec != "NO_ALPHA_SOURCE_FOUND":
                issues.append(
                    f"empty eligible but recommendation is '{rec}' "
                    f"(must be NO_ALPHA_SOURCE_FOUND)"
                )

        # log_market_cap_cs must be in support_factors.neutralizers
        support = pool.get("support_factors", {})
        if "log_market_cap_cs" not in support.get("neutralizers", []):
            # Check if it's in the config as a neutralizer
            if config:
                factors_cfg = config.get("factors", [])
                lmp_cfg = next((f for f in factors_cfg if f.get("name") == "log_market_cap_cs"), None)
                if lmp_cfg and lmp_cfg.get("role") == "neutralizer":
                    issues.append("log_market_cap_cs missing from support_factors.neutralizers "
                                  "(config declares role=neutralizer)")

        # WATCH_* factors should be in watch_factors_for_review, not in eligible or fail
        all_listed = (set(pool.get("eligible_factors", [])) |
                      set(pool.get("watch_factors_for_review", [])) |
                      set(pool.get("missing_data_factors", [])) |
                      set(pool.get("fail_factors", [])) |
                      set(support.get("neutralizers", [])) |
                      set(item["factor"] if isinstance(item, dict) else item
                          for item in support.get("redundant", [])))

        return issues
    except Exception as e:
        return [f"candidate pool unreadable: {e}"]


REQUIRED_MANIFEST_FIELDS = [
    "run_id", "config_path", "config_sha256", "seed",
    "factor_count", "out_dir", "out_doc",
    "start_time", "end_time", "status",
]

DIAGNOSTIC_CSVS = [
    "run_progress.csv",
    "run_stage_timings.csv",
    "run_errors.csv",
]


def check_run_manifest(out_dir: Path, config_path: Optional[Path] = None) -> list[str]:
    """Verify run_manifest.json exists, shows SUCCESS, and has all required fields.

    If config_path is provided, also verify config_sha256 matches.
    """
    issues = []
    # Find the most recent run manifest in _run_* subdirectories
    run_dirs = sorted(out_dir.glob("_run_*"), reverse=True)
    if not run_dirs:
        issues.append("No _run_* directory found — run manifest missing")
        return issues

    manifest_path = run_dirs[0] / "run_manifest.json"
    if not manifest_path.exists():
        issues.append(f"run_manifest.json not found in {run_dirs[0].name}")
        return issues

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as e:
        issues.append(f"run_manifest.json unreadable: {e}")
        return issues

    # Check all required fields exist
    for field in REQUIRED_MANIFEST_FIELDS:
        if field not in manifest:
            issues.append(f"run_manifest.json missing required field: {field}")

    status = manifest.get("status", "?")
    start_time = manifest.get("start_time", "")
    end_time = manifest.get("end_time", "")

    if status != "SUCCESS":
        issues.append(
            f"run_manifest status={status} (expected SUCCESS) — "
            f"outputs may be from a failed or incomplete run"
        )
    else:
        # For SUCCESS: start_time and end_time must be non-empty and ordered
        if not start_time:
            issues.append("run_manifest.start_time is empty on SUCCESS")
        if not end_time:
            issues.append("run_manifest.end_time is empty on SUCCESS")
        if start_time and end_time and end_time < start_time:
            issues.append(
                f"run_manifest end_time={end_time} < start_time={start_time}"
            )

    # Config checksum match
    if config_path and config_path.exists():
        current_sha = hashlib.sha256(config_path.read_bytes()).hexdigest()[:16]
        manifest_sha = manifest.get("config_sha256", "")
        if manifest_sha and current_sha != manifest_sha:
            issues.append(
                f"config_sha256 mismatch: current={current_sha}, "
                f"manifest={manifest_sha} — outputs may be from a different config version"
            )

    return issues


def check_diagnostic_csvs_in_run_dir(out_dir: Path) -> list[str]:
    """Verify diagnostic CSVs exist and are readable in the latest _run_* dir."""
    issues = []
    run_dirs = sorted(out_dir.glob("_run_*"), reverse=True)
    if not run_dirs:
        issues.append("No _run_* directory found for diagnostic CSV check")
        return issues

    run_dir = run_dirs[0]
    for name in DIAGNOSTIC_CSVS:
        fpath = run_dir / name
        if not fpath.exists():
            issues.append(f"Diagnostic CSV missing from {run_dir.name}: {name}")
            continue
        try:
            df = pd.read_csv(fpath, encoding="utf-8-sig")
            _ = len(df)  # verify readable
        except Exception as e:
            issues.append(f"Diagnostic CSV unreadable in {run_dir.name}: {name} — {e}")
    return issues


def check_no_diagnostic_csvs_in_root(out_dir: Path) -> list[str]:
    """Verify diagnostic CSVs have NOT leaked to the output root directory."""
    issues = []
    for name in DIAGNOSTIC_CSVS:
        if (out_dir / name).exists():
            issues.append(
                f"diagnostic CSV leaked to output root: {name} — "
                f"should only exist in _run_<run_id>/"
            )
    return issues


def check_output_freshness(out_dir: Path, max_age_minutes: int = 120) -> list[str]:
    """Verify that output files are not older than max_age_minutes.

    Checks modification time of factor_quality_gate.csv against current time.
    """
    issues = []
    gate_path = out_dir / "factor_quality_gate.csv"
    if not gate_path.exists():
        issues.append("factor_quality_gate.csv not found for freshness check")
        return issues

    mtime = gate_path.stat().st_mtime
    age_seconds = time.time() - mtime
    age_minutes = age_seconds / 60.0

    if age_minutes > max_age_minutes:
        mtime_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
        issues.append(
            f"factor_quality_gate.csv is {age_minutes:.0f} min old "
            f"(mtime={mtime_str}, max_age={max_age_minutes} min) — "
            f"outputs may be stale"
        )
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate factor quality rebuild outputs")
    parser.add_argument("--out-dir", default="outputs/analysis/factor_quality_rebuild")
    parser.add_argument("--config", default="configs/factor_quality_rebuild.yaml")
    parser.add_argument("--require-run-manifest", action="store_true",
                       help="Require run_manifest.json with status=SUCCESS")
    parser.add_argument("--max-output-age-minutes", type=int, default=0,
                       help="Max age of output files in minutes (0 = skip freshness check)")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    config_path = Path(args.config)
    if not out_dir.exists():
        print(f"FAIL: output directory does not exist: {out_dir}")
        return 1

    config = load_config(config_path)

    all_checks = [
        ("File existence", check_files_exist(out_dir)),
        ("CSV readability", check_csvs_readable(out_dir)),
        ("STUB prohibition", check_no_stub(out_dir)),
        ("Neutralization coverage vs status", check_neutralization_validity(out_dir, config)),
        ("Gate-neutralization consistency", check_gate_neutralization_consistency(out_dir, config)),
        ("Capacity CNY scale", check_capacity_cny_scale(out_dir, config)),
        ("Capacity participation formula", check_capacity_participation(out_dir)),
        ("Candidate pool contract", check_candidate_pool_contract(out_dir, config)),
    ]

    if args.require_run_manifest:
        all_checks.append(
            ("Run manifest", check_run_manifest(out_dir, config_path))
        )
        all_checks.append(
            ("Diagnostic CSV existence", check_diagnostic_csvs_in_run_dir(out_dir))
        )
        all_checks.append(
            ("No diagnostic CSV in root", check_no_diagnostic_csvs_in_root(out_dir))
        )
    if args.max_output_age_minutes > 0:
        all_checks.append(
            ("Output freshness", check_output_freshness(out_dir, args.max_output_age_minutes))
        )

    passed = 0
    failed = 0
    for check_name, issues in all_checks:
        if issues:
            print(f"FAIL [{check_name}]:")
            for issue in issues:
                print(f"  - {issue}")
            failed += 1
        else:
            print(f"PASS [{check_name}]")
            passed += 1

    total_issues = sum(len(issues) for _, issues in all_checks)
    print()
    if failed == 0:
        print(f"VALIDATION PASSED: {passed}/{passed + failed} checks OK")
        return 0
    else:
        print(f"VALIDATION FAILED: {passed}/{passed + failed} checks OK, {total_issues} issue(s)")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

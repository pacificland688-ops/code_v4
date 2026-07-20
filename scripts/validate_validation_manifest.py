#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Validate that validation runs match the current configuration.

This tool supports two modes:

**Single-strategy mode** (legacy — ``--factors-config`` + ``--regime-config``):
  1. ``runs.csv`` exists and is readable.
  2. Year coverage is complete (required validation + ytd years).
  3. Every run has ``return_code == 0``.
  4. Every ``run_dir`` contains a ``run_manifest.json``.
  5. ``factors_config_sha256`` matches the hash of the *current* factors config.
  6. ``regime_config_sha256`` matches the hash of the *current* regime config.
  7. ``strategy`` column contains a single unique value.

**Multi-strategy mode** (``--strategy-config`` repeatable):
  1-4. Same as single-strategy above.
  5. Each strategy's runs are validated against its own config hashes.
  6. Each strategy must independently cover all required validation + ytd years.
  7. No strategy uniqueness check — multiple strategies are expected.

Usage (single strategy)::

    python scripts/validate_validation_manifest.py \\
        --runs outputs/validation/candidate_v4_r2/runs.csv \\
        --factors-config configs/factors_candidate_v4_r2.yaml \\
        --regime-config configs/regime_candidate_v4_r2.yaml \\
        --required-validation-years 2017 2018 2019 2020 2021 2022 2023 2024 \\
        --required-ytd-years 2026

Usage (multi-strategy)::

    python scripts/validate_validation_manifest.py \\
        --runs outputs/validation/regime_ab_final/runs.csv \\
        --strategy-config A_regime_v2:configs/factors.yaml:configs/regime_v2.yaml \\
        --strategy-config B_direct_state_v1:configs/factors.yaml:configs/direct_state_v1.yaml \\
        --required-validation-years 2017 2018 2019 2020 2021 2022 2023 2024 \\
        --required-ytd-years 2026

Exit codes:
    0 — all checks passed
    1 — validation failed (manifest mismatch, missing years, etc.)
    2 — runtime error (file not found, unreadable config, etc.)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

# Project root — all manifest-relative paths are resolved against this,
# NOT the caller's current working directory.
ROOT = Path(__file__).resolve().parents[1]


def sha256_hex(path: Path) -> str:
    """Return the SHA-256 hex digest of a file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_runs(
    runs_path: Path,
    require_sample: bool = False,
) -> "pd.DataFrame":
    """Load ``runs.csv`` as a DataFrame, failing with exit code 2 on error.

    Parameters
    ----------
    require_sample : bool
        If True, the ``sample`` column is required (multi-strategy mode).
    """
    import pandas as pd

    if not runs_path.exists():
        print(f"FATAL: runs.csv not found: {runs_path}")
        sys.exit(2)

    try:
        df = pd.read_csv(runs_path)
    except Exception as exc:
        print(f"FATAL: cannot read runs.csv: {exc}")
        sys.exit(2)

    required_cols = {"year", "strategy", "return_code", "run_dir"}
    if require_sample:
        required_cols.add("sample")
    missing = required_cols - set(df.columns)
    if missing:
        print(f"FATAL: runs.csv missing columns: {missing}")
        sys.exit(2)

    return df


def validate_year_coverage(
    df: "pd.DataFrame",
    required_validation_years: List[int],
    required_ytd_years: List[int],
) -> List[str]:
    """Check that all required years are present (single-strategy mode).

    Returns a list of issues.
    """
    issues = []
    years_present = set(int(y) for y in df["year"].unique())

    all_required = required_validation_years + required_ytd_years
    missing = sorted(set(all_required) - years_present)
    if missing:
        issues.append(
            f"Missing years in runs.csv: {missing}. "
            f"Expected validation: {required_validation_years}, "
            f"expected YTD: {required_ytd_years}"
        )

    return issues


def validate_year_coverage_multi(
    df: "pd.DataFrame",
    strategy_configs: dict,
    required_validation_years: List[int],
    required_ytd_years: List[int],
) -> List[str]:
    """Check per-strategy year coverage (multi-strategy mode).

    Each strategy named in *strategy_configs* must independently cover
    all required validation years and all required ytd years.

    Returns a list of issues.
    """
    issues = []

    for strategy_name in sorted(strategy_configs):
        strat_data = df[df["strategy"] == strategy_name]
        if strat_data.empty:
            issues.append(
                f"{strategy_name}: no runs found in runs.csv"
            )
            continue

        present_validation = set(
            int(y) for y in
            strat_data[strat_data["sample"] == "validation"]["year"].unique()
        )
        missing_val = sorted(set(required_validation_years) - present_validation)
        if missing_val:
            issues.append(
                f"{strategy_name}: missing validation years: {missing_val}"
            )

        present_ytd = set(
            int(y) for y in
            strat_data[strat_data["sample"] == "ytd"]["year"].unique()
        )
        missing_yt = sorted(set(required_ytd_years) - present_ytd)
        if missing_yt:
            issues.append(
                f"{strategy_name}: missing ytd years: {missing_yt}"
            )

    return issues


def validate_return_codes(df: "pd.DataFrame") -> List[str]:
    """Check that all return codes are zero. Returns a list of issues."""
    issues = []
    nonzero = df[df["return_code"] != 0]
    if len(nonzero) > 0:
        issues.append(
            f"Non-zero return codes found ({len(nonzero)} rows): "
            f"{nonzero[['year', 'return_code']].to_dict('records')}"
        )
    return issues


def validate_strategy_unique(df: "pd.DataFrame") -> List[str]:
    """Check that the strategy column has a single unique value."""
    issues = []
    unique_strategies = df["strategy"].dropna().unique()
    if len(unique_strategies) == 0:
        issues.append("No strategy values found in runs.csv")
    elif len(unique_strategies) > 1:
        issues.append(
            f"Multiple strategy values found: {list(unique_strategies)}"
        )
    return issues


def validate_manifests(
    df: "pd.DataFrame",
    factors_config_sha256_expected: str,
    regime_config_sha256_expected: str,
    factors_config_relpath: str,
    regime_config_relpath: str,
) -> List[str]:
    """Check every run_dir for a matching run_manifest.json. Returns issues."""
    issues = []
    manifest_mismatches = 0
    missing_manifests = 0

    for _, row in df.iterrows():
        run_dir = Path(str(row["run_dir"]))
        year = row["year"]

        if not run_dir.exists():
            issues.append(
                f"Year {year}: run_dir does not exist: {run_dir}"
            )
            continue

        manifest_path = run_dir / "run_manifest.json"
        if not manifest_path.exists():
            missing_manifests += 1
            issues.append(
                f"Year {year}: run_manifest.json not found in {run_dir}"
            )
            continue

        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            issues.append(
                f"Year {year}: run_manifest.json invalid JSON: {exc}"
            )
            continue

        # Check factors config hash
        actual_factors_hash = manifest.get("factors_config_sha256", "")
        if actual_factors_hash != factors_config_sha256_expected:
            manifest_mismatches += 1
            issues.append(
                f"Year {year}: factors_config_sha256 MISMATCH — "
                f"manifest: {actual_factors_hash[:16]}..., "
                f"current: {factors_config_sha256_expected[:16]}..."
            )

        # Check regime config hash
        actual_regime_hash = manifest.get("regime_config_sha256", "")
        if actual_regime_hash != regime_config_sha256_expected:
            manifest_mismatches += 1
            issues.append(
                f"Year {year}: regime_config_sha256 MISMATCH — "
                f"manifest: {actual_regime_hash[:16]}..., "
                f"current: {regime_config_sha256_expected[:16]}..."
            )

        # Check config paths (informational)
        actual_factors_path = manifest.get("factors_config", "")
        if actual_factors_path != factors_config_relpath:
            issues.append(
                f"Year {year}: factors_config path differs — "
                f"manifest: {actual_factors_path}, expected: {factors_config_relpath}"
            )

        actual_regime_path = manifest.get("regime_config", "")
        if actual_regime_path != regime_config_relpath:
            issues.append(
                f"Year {year}: regime_config path differs — "
                f"manifest: {actual_regime_path}, expected: {regime_config_relpath}"
            )

    summary = (
        f"Manifest check: {len(df)} runs, {missing_manifests} missing, "
        f"{manifest_mismatches} hash mismatches"
    )
    if manifest_mismatches == 0 and missing_manifests == 0:
        print(f"  OK: {summary}")
    else:
        print(f"  FAIL: {summary}")
        issues.insert(0, summary)

    return issues


def _parse_strategy_configs(
    legacy: Optional[List[str]],
    entries: Optional[List[List[str]]],
) -> dict[str, tuple[Path, Path]]:
    """Parse legacy and entry strategy-config specifications into a lookup dict.

    Parameters
    ----------
    legacy : list of str or None
        Legacy ``STRATEGY:FACTORS:REGIME`` strings.
    entries : list of [str, str, str] or None
        Entry triples from ``--strategy-config-entry``.

    Returns
    -------
    dict
        ``{strategy_name: (factors_path, regime_path)}``.
    """
    result: dict[str, tuple[Path, Path]] = {}

    def _add(name: str, factors_raw: str, regime_raw: str, source: str):
        if name in result:
            print(
                f"FATAL: strategy '{name}' specified more than once "
                f"(source: {source})."
            )
            sys.exit(2)
        factors_path = Path(factors_raw)
        regime_path = Path(regime_raw)
        # Resolve relative paths against ROOT for existence checks
        factors_check = factors_path if factors_path.is_absolute() else ROOT / factors_path
        regime_check = regime_path if regime_path.is_absolute() else ROOT / regime_path
        if not factors_check.exists():
            print(
                f"FATAL: factors config not found for {name}: {factors_path}"
            )
            sys.exit(2)
        if not regime_check.exists():
            print(
                f"FATAL: regime config not found for {name}: {regime_path}"
            )
            sys.exit(2)
        result[name] = (factors_path, regime_path)

    # --- Legacy strings: STRATEGY:FACTORS:REGIME ---
    if legacy:
        for entry in legacy:
            # Detect Windows absolute paths BEFORE splitting on colon.
            # Windows drive letters (e.g. D:\ or D:/) will be broken by
            # the colon split; reject early with a clear message.
            if _looks_like_windows_absolute_in_legacy(entry):
                print(
                    f"FATAL: --strategy-config entry contains a Windows "
                    f"absolute path (e.g. D:\\... or D:/...):\n"
                    f"  {entry}\n"
                    f"  Use --strategy-config-entry with paths as separate "
                    f"arguments:\n"
                    f"  --strategy-config-entry STRATEGY FACTORS_CONFIG REGIME_CONFIG"
                )
                sys.exit(2)

            parts = entry.split(":", 2)
            if len(parts) != 3:
                print(
                    f"FATAL: --strategy-config must be STRATEGY:FACTORS:REGIME, "
                    f"got: {entry}"
                )
                sys.exit(2)
            strategy, factors_raw, regime_raw = parts

            _add(strategy, factors_raw, regime_raw, f"--strategy-config {entry}")

    # --- Entry triples: STRATEGY FACTORS REGIME ---
    if entries:
        for triple in entries:
            if len(triple) != 3:
                print(
                    f"FATAL: --strategy-config-entry expects exactly 3 values, "
                    f"got {len(triple)}: {triple}"
                )
                sys.exit(2)
            strategy, factors_raw, regime_raw = triple
            _add(strategy, factors_raw, regime_raw,
                  f"--strategy-config-entry {strategy}")

    if not result:
        print("FATAL: no strategy configs provided (use --strategy-config "
              "and/or --strategy-config-entry).")
        sys.exit(2)

    return result


def _looks_like_windows_absolute_in_legacy(entry: str) -> bool:
    """Return True if *entry* contains a Windows absolute path pattern.

    Patterns detected: ``X:\\`` or ``X:/`` (drive letter + colon + slash).
    These break the colon-based ``STRATEGY:FACTORS:REGIME`` split.
    """
    import re
    # Match a Windows drive letter followed by :\ or :/ anywhere in the string
    return bool(re.search(r"[a-zA-Z]:[\\/]", entry))


def _paths_equivalent(a: str, b: str) -> bool:
    """Return True if *a* and *b* resolve to the same file on disk.

    Manifest paths are relative to the project root (ROOT), not the
    caller's current working directory.  This prevents false path-mismatch
    errors when the caller is not inside the project directory.
    """
    # Fast path: exact string match
    a_norm = a.replace("\\", "/")
    b_norm = b.replace("\\", "/")
    if a_norm == b_norm:
        return True

    try:
        def _resolve(raw: str) -> Path:
            p = Path(raw)
            if not p.is_absolute():
                p = ROOT / p
            return p.resolve()

        return _resolve(a) == _resolve(b)
    except Exception:
        return False


def validate_manifests_multi(
    df: "pd.DataFrame",
    strategy_configs: dict[str, tuple[Path, Path]],
) -> List[str]:
    """Per-strategy manifest validation. Returns issues."""
    issues = []
    manifest_mismatches = 0
    missing_manifests = 0
    unknown_strategies = 0

    for _, row in df.iterrows():
        run_dir = Path(str(row["run_dir"]))
        year = row["year"]
        strategy = str(row.get("strategy", ""))

        if strategy not in strategy_configs:
            unknown_strategies += 1
            issues.append(
                f"Year {year}: strategy '{strategy}' not in --strategy-config list. "
                f"Known: {list(strategy_configs)}"
            )
            continue

        factors_path, regime_path = strategy_configs[strategy]
        expected_factors_hash = sha256_hex(factors_path)
        expected_regime_hash = sha256_hex(regime_path)
        expected_factors_rel = str(factors_path).replace("\\", "/")
        expected_regime_rel = str(regime_path).replace("\\", "/")

        if not run_dir.exists():
            issues.append(f"Year {year}: run_dir does not exist: {run_dir}")
            continue

        manifest_path = run_dir / "run_manifest.json"
        if not manifest_path.exists():
            missing_manifests += 1
            issues.append(f"Year {year}: run_manifest.json not found in {run_dir}")
            continue

        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            issues.append(f"Year {year}: run_manifest.json invalid JSON: {exc}")
            continue

        actual_factors_hash = manifest.get("factors_config_sha256", "")
        if actual_factors_hash != expected_factors_hash:
            manifest_mismatches += 1
            issues.append(
                f"Year {year} ({strategy}): factors_config_sha256 MISMATCH — "
                f"manifest: {actual_factors_hash[:16]}..., "
                f"current: {expected_factors_hash[:16]}..."
            )

        actual_regime_hash = manifest.get("regime_config_sha256", "")
        if actual_regime_hash != expected_regime_hash:
            manifest_mismatches += 1
            issues.append(
                f"Year {year} ({strategy}): regime_config_sha256 MISMATCH — "
                f"manifest: {actual_regime_hash[:16]}..., "
                f"current: {expected_regime_hash[:16]}..."
            )

        actual_factors_path = manifest.get("factors_config", "")
        if actual_factors_path != expected_factors_rel:
            if not _paths_equivalent(actual_factors_path, expected_factors_rel):
                issues.append(
                    f"Year {year} ({strategy}): factors_config path differs — "
                    f"manifest: {actual_factors_path}, expected: {expected_factors_rel}"
                )

        actual_regime_path = manifest.get("regime_config", "")
        if actual_regime_path != expected_regime_rel:
            if not _paths_equivalent(actual_regime_path, expected_regime_rel):
                issues.append(
                    f"Year {year} ({strategy}): regime_config path differs — "
                    f"manifest: {actual_regime_path}, expected: {expected_regime_rel}"
                )

    summary = (
        f"Manifest check: {len(df)} runs, {missing_manifests} missing, "
        f"{manifest_mismatches} hash mismatches, {unknown_strategies} unknown strategies"
    )
    if manifest_mismatches == 0 and missing_manifests == 0 and unknown_strategies == 0:
        print(f"  OK: {summary}")
    else:
        print(f"  FAIL: {summary}")
        issues.insert(0, summary)

    return issues


def main():
    parser = argparse.ArgumentParser(
        description="Validate that frozen backtest runs match current config."
    )
    parser.add_argument(
        "--runs",
        required=True,
        help="Path to runs.csv from frozen_backtest_validation.py output.",
    )
    parser.add_argument(
        "--factors-config",
        default=None,
        help="Path to factors YAML config (single-strategy mode).",
    )
    parser.add_argument(
        "--regime-config",
        default=None,
        help="Path to regime YAML config (single-strategy mode).",
    )
    parser.add_argument(
        "--strategy-config",
        action="append",
        default=None,
        dest="strategy_configs",
        metavar="STRATEGY:FACTORS_CONFIG:REGIME_CONFIG",
        help="[Legacy] Repeatable: per-strategy config mapping (colon-separated). "
             "Does NOT support Windows absolute paths. "
             "Use --strategy-config-entry for paths with drive letters.",
    )
    parser.add_argument(
        "--strategy-config-entry",
        action="append",
        default=None,
        nargs=3,
        metavar=("STRATEGY", "FACTORS_CONFIG", "REGIME_CONFIG"),
        dest="strategy_config_entries",
        help="[Recommended] Repeatable: STRATEGY FACTORS_CONFIG REGIME_CONFIG "
             "as separate arguments. Supports Windows absolute paths and "
             "relative paths.",
    )
    parser.add_argument(
        "--required-validation-years",
        type=int,
        nargs="+",
        default=[2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024],
        help="Validation years required (default: 2017-2024).",
    )
    parser.add_argument(
        "--required-ytd-years",
        type=int,
        nargs="+",
        default=[2026],
        help="YTD years required (default: 2026).",
    )

    args = parser.parse_args()

    runs_path = Path(args.runs)

    # Determine mode: multi-strategy or single-strategy
    has_legacy = args.strategy_configs is not None and len(args.strategy_configs) > 0
    has_entries = args.strategy_config_entries is not None and len(args.strategy_config_entries) > 0
    multi_strategy = has_legacy or has_entries

    if multi_strategy:
        strategy_configs = _parse_strategy_configs(
            legacy=args.strategy_configs,
            entries=args.strategy_config_entries,
        )
        print("Multi-strategy mode:")
        for s, (fp, rp) in strategy_configs.items():
            print(f"  {s}: factors={fp}  regime={rp}")
    else:
        if not args.factors_config or not args.regime_config:
            print("FATAL: either --strategy-config/--strategy-config-entry "
                  "or both --factors-config and --regime-config are required.")
            sys.exit(2)

        factors_config_path = Path(args.factors_config)
        regime_config_path = Path(args.regime_config)

        for label, path in [
            ("factors-config", factors_config_path),
            ("regime-config", regime_config_path),
        ]:
            if not path.exists():
                print(f"FATAL: {label} not found: {path}")
                sys.exit(2)

        factors_config_sha256_expected = sha256_hex(factors_config_path)
        regime_config_sha256_expected = sha256_hex(regime_config_path)

        factors_config_relpath = str(factors_config_path).replace("\\", "/")
        regime_config_relpath = str(regime_config_path).replace("\\", "/")

        print(
            f"Expected factors config:  {factors_config_relpath}\n"
            f"  SHA256: {factors_config_sha256_expected}"
        )
        print(
            f"Expected regime config:   {regime_config_relpath}\n"
            f"  SHA256: {regime_config_sha256_expected}"
        )

    # ------------------------------------------------------------------
    # Load runs
    # ------------------------------------------------------------------
    print(f"\nLoading runs from: {runs_path}")
    df = load_runs(runs_path, require_sample=multi_strategy)
    print(f"  {len(df)} runs loaded")

    all_issues: List[str] = []

    # ------------------------------------------------------------------
    # Check 1: Year coverage
    # ------------------------------------------------------------------
    print("\n[1/5] Year coverage check...")
    if multi_strategy:
        issues = validate_year_coverage_multi(
            df, strategy_configs,
            args.required_validation_years, args.required_ytd_years,
        )
        # Also check global coverage (all strategies combined)
        global_issues = validate_year_coverage(
            df, args.required_validation_years, args.required_ytd_years,
        )
    else:
        issues = validate_year_coverage(
            df, args.required_validation_years, args.required_ytd_years,
        )
        global_issues = []
    if issues:
        for i in issues:
            print(f"  FAIL: {i}")
        all_issues.extend(issues)
    if global_issues:
        for i in global_issues:
            print(f"  FAIL (global): {i}")
        all_issues.extend(global_issues)
    if not issues and not global_issues:
        years_str = ", ".join(str(y) for y in sorted(df["year"].unique()))
        print(f"  OK: all required years covered. Present: {years_str}")

    # ------------------------------------------------------------------
    # Check 2: Return codes
    # ------------------------------------------------------------------
    print("\n[2/5] Return code check...")
    issues = validate_return_codes(df)
    if issues:
        for i in issues:
            print(f"  FAIL: {i}")
        all_issues.extend(issues)
    else:
        print(f"  OK: all {len(df)} runs have return_code=0")

    # ------------------------------------------------------------------
    # Check 3: Strategy uniqueness (single-strategy) or coverage (multi)
    # ------------------------------------------------------------------
    if multi_strategy:
        print("\n[3/5] Strategy coverage check...")
        strategies_present = set(df["strategy"].dropna().unique())
        strategies_expected = set(strategy_configs.keys())
        missing_strategies = strategies_expected - strategies_present
        extra_strategies = strategies_present - strategies_expected
        if missing_strategies:
            issue = f"Strategies in config but not in runs.csv: {missing_strategies}"
            print(f"  FAIL: {issue}")
            all_issues.append(issue)
        if extra_strategies:
            print(f"  WARN: strategies in runs.csv not in config: {extra_strategies}")
        if not missing_strategies and not extra_strategies:
            print(f"  OK: {len(strategies_present)} strategies match config")
        elif not missing_strategies:
            print(f"  OK: all expected strategies present ({len(extra_strategies)} extra)")
    else:
        print("\n[3/5] Strategy uniqueness check...")
        issues = validate_strategy_unique(df)
        if issues:
            for i in issues:
                print(f"  FAIL: {i}")
            all_issues.extend(issues)
        else:
            print(f"  OK: strategy='{df['strategy'].iloc[0]}'")

    # ------------------------------------------------------------------
    # Check 4: Manifest existence and hash match
    # ------------------------------------------------------------------
    print("\n[4/5] Manifest hash check...")
    if multi_strategy:
        issues = validate_manifests_multi(df, strategy_configs)
    else:
        issues = validate_manifests(
            df,
            factors_config_sha256_expected,
            regime_config_sha256_expected,
            factors_config_relpath,
            regime_config_relpath,
        )
    if issues:
        all_issues.extend(issues)

    # ------------------------------------------------------------------
    # Check 5: Required columns / data quality
    # ------------------------------------------------------------------
    print("\n[5/5] Data quality check...")
    if "go_nogo_overall" in df.columns:
        incomplete = df[df["go_nogo_overall"].str.contains("INCOMPLETE", na=False)]
        if len(incomplete) > 0:
            issue = (
                f"INCOMPLETE flags found in {len(incomplete)} rows: "
                f"{list(incomplete['year'])}"
            )
            print(f"  FAIL: {issue}")
            all_issues.append(issue)
        else:
            print("  OK: no INCOMPLETE flags")
    else:
        print("  SKIP: no go_nogo_overall column")

    # ------------------------------------------------------------------
    # Final verdict
    # ------------------------------------------------------------------
    print("\n" + "=" * 60)
    if all_issues:
        print(f"VALIDATION FAILED — {len(all_issues)} issue(s):")
        for issue in all_issues:
            print(f"  • {issue}")
        print("\nRemediation: Re-run frozen_backtest_validation.py with current configs.")
        sys.exit(1)
    else:
        print("VALIDATION PASSED:")
        print(f"  manifest_mismatch_count = 0")
        print(f"  missing_years = []")
        print(f"  return_code failures = 0")
        print(f"  All {len(df)} runs match current configuration.")
        sys.exit(0)


if __name__ == "__main__":
    main()

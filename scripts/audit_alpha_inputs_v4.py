#!/usr/bin/env python
"""
Audit V4 alpha factor input data for PIT safety, coverage, and quality.

Checks:
  - future_leakage: available_date > trade_date
  - missing_available_date: null available_date
  - stale: pit_lag_days > max_tolerance
  - duplicate: (ts_code, trade_date) not unique
  - constant: factor value unchanged across dates
  - coverage: per-date stock count below threshold

Outputs:
  - outputs/analysis/v4_alpha_inputs/audit_summary.csv
  - outputs/analysis/v4_alpha_inputs/audit_detail.csv
  - outputs/analysis/v4_alpha_inputs/blocked_factors.yaml
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]

# Maximum tolerable lag days by data type
MAX_LAG_DAYS = {
    "technical": 7,
    "fundamental": 63,
    "financial_statement": 120,
}

# Minimum daily coverage (stocks per date)
MIN_COVERAGE = 30


def _load_factor_cache(factor_name: str, start: str, end: str) -> pd.DataFrame:
    """Load factor parquet cache, similar to factor_quality_rebuild.py."""
    root = ROOT / "data" / "parquet" / "factors" / f"factor_name={factor_name}"
    if not root.exists():
        return pd.DataFrame()

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
                    if "ts_code" not in part.columns or "trade_date" not in part.columns:
                        continue

                    part["ts_code"] = part["ts_code"].astype(str)
                    part["trade_date"] = pd.to_numeric(part["trade_date"], errors="coerce")
                    part = part.dropna(subset=["trade_date"])
                    part = part[(part["trade_date"] >= start_int) & (part["trade_date"] <= end_int)]

                    if not part.empty:
                        chunks.append(part)
            elif sub_dir.suffix == ".parquet":
                # V4 format: year={Y}/part_{Y}.parquet
                try:
                    part = pd.read_parquet(sub_dir)
                except Exception:
                    continue

                part.columns = [str(c).strip().lower() for c in part.columns]
                if "ts_code" not in part.columns or "trade_date" not in part.columns:
                    continue

                part["ts_code"] = part["ts_code"].astype(str)
                part["trade_date"] = pd.to_numeric(part["trade_date"], errors="coerce")
                part = part.dropna(subset=["trade_date"])
                part = part[(part["trade_date"] >= start_int) & (part["trade_date"] <= end_int)]

                if not part.empty:
                    chunks.append(part)

    if not chunks:
        return pd.DataFrame()

    result = pd.concat(chunks, ignore_index=True)
    return result.sort_values(["ts_code", "trade_date"])


def _audit_factor(
    factor_name: str,
    df: pd.DataFrame,
    factor_type: str,
    start: str,
    end: str,
) -> dict:
    """Run full PIT + data quality audit on a single factor."""
    max_lag = MAX_LAG_DAYS.get(factor_type, 63)
    total_rows = len(df)

    result = {
        "factor": factor_name,
        "factor_type": factor_type,
        "total_rows": total_rows,
        "time_range": f"{start}-{end}",
        "audit_timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }

    if df.empty:
        result["status"] = "FAIL"
        result["failure_reason"] = "empty_cache"
        result["future_leakage_count"] = 0
        result["missing_available_date_count"] = 0
        result["stale_count"] = 0
        result["duplicate_count"] = 0
        result["constant_date_count"] = 0
        result["low_coverage_date_count"] = 0
        result["n_unique_stocks"] = 0
        result["n_unique_dates"] = 0
        result["median_coverage"] = 0
        result["min_coverage"] = 0
        return result

    n_stocks = df["ts_code"].nunique()
    n_dates = df["trade_date"].nunique()

    # 1. Duplicate check
    dupes = int(df.duplicated(["ts_code", "trade_date"]).sum())

    # 2. Future leakage check
    future_leakage = 0
    if "available_date" in df.columns:
        future_leakage = int((df["available_date"] > df["trade_date"]).sum())

    # 3. Missing available_date
    missing_avail = 0
    if "available_date" in df.columns:
        missing_avail = int(df["available_date"].isna().sum())

    # 4. Stale check
    stale_count = 0
    if "pit_lag_days" in df.columns:
        stale_count = int((df["pit_lag_days"] > max_lag).sum())
    elif "available_date" in df.columns and "trade_date" in df.columns:
        lag = df["trade_date"] - df["available_date"]
        stale_count = int((lag > max_lag).sum())

    # 5. Constant values per date
    constant_dates = 0
    value_cols = [c for c in df.columns if c not in ("ts_code", "trade_date", "available_date",
                                                      "source_period", "source_date",
                                                      "pit_lag_days", "is_stale", "year", "month")]
    if value_cols:
        val_col = value_cols[0]
        for _, g in df.groupby("trade_date"):
            if g[val_col].nunique() <= 1:
                constant_dates += 1

    # 6. Coverage check
    daily_cov = df.groupby("trade_date").size()
    median_cov = int(daily_cov.median()) if len(daily_cov) > 0 else 0
    min_cov = int(daily_cov.min()) if len(daily_cov) > 0 else 0
    low_cov_dates = int((daily_cov < MIN_COVERAGE).sum())

    # 7. Missing / stale rate
    missing_rate = 0.0
    if "is_stale" in df.columns:
        n_stale_marked = int(df["is_stale"].sum())
    else:
        n_stale_marked = stale_count

    # Determine status
    failures = []
    if df.empty:
        failures.append("EMPTY_CACHE")
    if future_leakage > 0:
        failures.append(f"FUTURE_LEAKAGE:{future_leakage}")
    if dupes > total_rows * 0.05:
        failures.append(f"HIGH_DUPLICATE_RATE:{dupes}/{total_rows}")
    if n_stocks < 10:
        failures.append(f"LOW_STOCKS:{n_stocks}")
    if n_dates < 10:
        failures.append(f"LOW_DATES:{n_dates}")

    if failures:
        status = "FAIL"
        failure_reason = "; ".join(failures)
    elif stale_count > total_rows * 0.3:
        status = "WARN"
        failure_reason = f"high_stale_rate:{stale_count}/{total_rows}"
    elif low_cov_dates > n_dates * 0.3:
        status = "WARN"
        failure_reason = f"low_coverage_on_{low_cov_dates}/{n_dates}_dates"
    elif missing_avail > total_rows * 0.3:
        status = "WARN"
        failure_reason = f"missing_available_date:{missing_avail}/{total_rows}"
    else:
        status = "PASS"
        failure_reason = ""

    result.update({
        "status": status,
        "failure_reason": failure_reason,
        "future_leakage_count": future_leakage,
        "missing_available_date_count": missing_avail,
        "stale_count": stale_count,
        "stale_rate": round(stale_count / max(total_rows, 1), 4),
        "duplicate_count": dupes,
        "constant_date_count": constant_dates,
        "low_coverage_date_count": low_cov_dates,
        "n_unique_stocks": n_stocks,
        "n_unique_dates": n_dates,
        "median_coverage": median_cov,
        "min_coverage": min_cov,
        "max_lag_tolerance": max_lag,
    })

    return result


def _check_data_source_availability(client) -> dict:
    """Check which Tushare data tables/fields are available for V4 factors."""
    availability = {
        "fina_indicator": {"available": False, "fields_found": []},
        "income": {"available": False, "fields_found": []},
        "cashflow": {"available": False, "fields_found": []},
        "balancesheet": {"available": False, "fields_found": []},
        "daily_basic": {"available": False, "fields_found": []},
    }

    # Check fina_indicator
    try:
        df = client.get_fina_indicator(ts_code="000001.SZ", use_cache=True)
        if not df.empty:
            availability["fina_indicator"]["available"] = True
            availability["fina_indicator"]["fields_found"] = list(df.columns)
    except Exception:
        pass

    # Check income
    try:
        df = client.get_income(ts_code="000001.SZ", use_cache=True)
        if not df.empty:
            availability["income"]["available"] = True
            availability["income"]["fields_found"] = list(df.columns)
    except Exception:
        pass

    # Check daily_basic
    try:
        root = ROOT / "data" / "parquet" / "daily_basic"
        if root.exists():
            for year_dir in sorted(root.iterdir()):
                for month_dir in sorted(year_dir.iterdir()):
                    for pq_file in month_dir.glob("*.parquet"):
                        try:
                            part = pd.read_parquet(pq_file)
                            availability["daily_basic"]["available"] = True
                            availability["daily_basic"]["fields_found"] = list(part.columns)
                            break
                        except Exception:
                            continue
                    if availability["daily_basic"]["available"]:
                        break
                if availability["daily_basic"]["available"]:
                    break
    except Exception:
        pass

    return availability


def _generate_blocked_factors(
    factor_specs: list[dict],
    data_availability: dict,
    audit_results: list[dict],
    out_path: Path,
) -> list[str]:
    """Identify factors that cannot be built due to data unavailability."""
    blocked = []

    for spec in factor_specs:
        name = spec["name"]
        required_sources = spec.get("data_sources", [])
        reasons = []

        for src in required_sources:
            if src in data_availability:
                if not data_availability[src]["available"]:
                    reasons.append(f"data_source_unavailable:{src}")
                else:
                    # Check specific fields
                    required_fields = spec.get("required_fields", {}).get(src, [])
                    available_fields = data_availability[src]["fields_found"]
                    missing_fields = [f for f in required_fields if f not in available_fields]
                    if missing_fields:
                        reasons.append(f"missing_fields_in_{src}:{','.join(missing_fields)}")

        # Check audit results
        audit = next((a for a in audit_results if a.get("factor") == name), {})
        if audit.get("status") == "FAIL":
            reasons.append(f"audit_failed:{audit.get('failure_reason', 'unknown')}")

        if reasons:
            blocked.append({
                "factor": name,
                "reasons": reasons,
                "recommendation": "Resolve data availability or re-classify as P2.",
            })

    blocked_yaml = {
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "description": "V4 alpha factors blocked by data availability or audit failures",
        "blocked_factors": blocked,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(yaml.dump(blocked_yaml, allow_unicode=True, default_flow_style=False), encoding="utf-8")

    return [b["factor"] for b in blocked]


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit V4 alpha factor input data")
    parser.add_argument("--start", default="20170101")
    parser.add_argument("--end", default="20241231")
    parser.add_argument("--out", default="outputs/analysis/v4_alpha_inputs")
    parser.add_argument("--factor-config", default="configs/factors_alpha_v4_universe.yaml")
    args = parser.parse_args()

    out_dir = ROOT / args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    # Load V4 factor universe config
    config_path = ROOT / args.factor_config
    if not config_path.exists():
        print(f"ERROR: Factor config not found: {config_path}")
        print("Please create configs/factors_alpha_v4_universe.yaml first (M3 task).")
        print("Running with stub config for structure validation.")
        # Create a minimal stub config
        factor_specs = [
            {"name": "ep_cs", "type": "fundamental", "category": "value",
             "data_sources": ["daily_basic"], "required_fields": {"daily_basic": ["pe"]}},
            {"name": "bp_cs", "type": "fundamental", "category": "value",
             "data_sources": ["daily_basic"], "required_fields": {"daily_basic": ["pb"]}},
        ]
    else:
        cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        factor_specs = cfg.get("factors", [])

    # Load Tushare client for data availability check
    try:
        from data.tushare_client import get_client
        client = get_client()
    except Exception:
        client = None
        print("WARN: Could not initialize Tushare client. Data source availability check skipped.")

    # Check data source availability
    data_availability = {}
    if client is not None:
        data_availability = _check_data_source_availability(client)

    # Audit existing factor caches
    audit_results = []
    for spec in factor_specs:
        fname = spec["name"]
        ftype = spec.get("type", "fundamental")
        print(f"Auditing {fname} ({ftype})...")

        df = _load_factor_cache(fname, args.start, args.end)
        result = _audit_factor(fname, df, ftype, args.start, args.end)
        audit_results.append(result)

        icon = {"PASS": "[PASS]", "WARN": "[WARN]", "FAIL": "[FAIL]"}.get(result["status"], "[?]")
        print(f"  {icon} {result['status']}: {result['total_rows']} rows, "
              f"{result['n_unique_stocks']} stocks, "
              f"future_leakage={result['future_leakage_count']}, "
              f"stale={result['stale_count']}")

    # Generate blocked factors list
    blocked_path = out_dir / "blocked_factors.yaml"
    blocked = _generate_blocked_factors(factor_specs, data_availability, audit_results, blocked_path)
    if blocked:
        print(f"\nBlocked factors ({len(blocked)}):")
        for b in blocked:
            print(f"  - {b}")

    # Write outputs
    summary_df = pd.DataFrame(audit_results)
    summary_df.to_csv(out_dir / "audit_summary.csv", index=False, encoding="utf-8-sig")

    # Write data availability
    avail_df = pd.DataFrame([
        {"source": k, "available": v["available"],
         "n_fields": len(v["fields_found"]),
         "fields": ", ".join(v["fields_found"][:20])}
        for k, v in data_availability.items()
    ])
    avail_df.to_csv(out_dir / "data_availability.csv", index=False, encoding="utf-8-sig")

    print(f"\nWrote audit outputs to {out_dir}")
    print(f"  audit_summary.csv: {len(audit_results)} factors audited")
    print(f"  data_availability.csv: {len(data_availability)} data sources checked")
    print(f"  blocked_factors.yaml: {len(blocked)} factors blocked")

    # Final status summary
    fails = [r for r in audit_results if r["status"] == "FAIL"]
    warns = [r for r in audit_results if r["status"] == "WARN"]
    passes = [r for r in audit_results if r["status"] == "PASS"]

    print(f"\n=== Audit Summary ===")
    print(f"  PASS: {len(passes)}")
    print(f"  WARN: {len(warns)}")
    print(f"  FAIL: {len(fails)}")
    print(f"  BLOCKED: {len(blocked)}")

    if any(r["future_leakage_count"] > 0 for r in audit_results):
        print("\n  [CRITICAL] Future leakage detected! Affected factors must NOT enter candidate pool.")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python
"""
Cache audit script — read-only health check for all cached datasets.

Checks:
- Factor cache: duplicates, legacy files, date coverage
- fwd_returns: duplicates, date coverage
- limit_status: duplicates, exec-date coverage
- prices_adj: coverage ratio
- index_weight: coverage for PIT universe
- daily_basic: monthly coverage

Output: human-readable table and optional JSON.

Usage:
    python scripts/audit_cache.py --start 20160101 --end 20161231
    python scripts/audit_cache.py --start 20160101 --end 20161231 --json
    python scripts/audit_cache.py --start 20160101 --end 20160229 --verbose
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

# Add code_v4 to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def audit(args):
    """Run all cache audits and return structured results."""
    from data.panel_loader import get_loader
    from data.calendar import get_calendar

    loader = get_loader()
    cal = get_calendar()
    cal.load(start_date=args.start, end_date=args.end)

    results = {
        "window": {"start": args.start, "end": args.end},
        "passed": 0,
        "warned": 0,
        "failed": 0,
        "checks": [],
    }

    def add_check(name, status, detail=""):
        entry = {"name": name, "status": status, "detail": detail}
        results["checks"].append(entry)
        if status == "PASS":
            results["passed"] += 1
        elif status == "WARN":
            results["warned"] += 1
        else:
            results["failed"] += 1
        return entry

    # ------------------------------------------------------------------
    # 1. Factor cache legacy files
    # ------------------------------------------------------------------
    factors_base = Path("data/parquet/factors")
    legacy_count = 0
    legacy_details = []
    if factors_base.exists():
        for factor_dir in sorted(factors_base.glob("factor_name=*")):
            fname = factor_dir.name.replace("factor_name=", "")
            for year_dir in sorted(factor_dir.glob("year=*")):
                bare_files = list(year_dir.glob("*.parquet"))
                month_dirs = list(year_dir.glob("month=*"))
                if bare_files and month_dirs:
                    legacy_count += len(bare_files)
                    legacy_details.append(
                        f"{fname}/{year_dir.name}: {len(bare_files)} legacy files"
                    )

    if legacy_count > 0:
        add_check(
            "factor_legacy_files",
            "FAIL",
            f"{legacy_count} legacy year-level parquet files coexist with "
            f"month partitions. Run: python scripts/migrate_factor_cache.py\n"
            + "\n".join(f"  - {d}" for d in legacy_details[:10]),
        )
    else:
        add_check("factor_legacy_files", "PASS", "No legacy coexistence detected")

    # ------------------------------------------------------------------
    # 2. Factor _cs duplicates and coverage
    # ------------------------------------------------------------------
    import glob
    cs_factors = sorted([
        Path(d).name.replace("factor_name=", "")
        for d in glob.glob("data/parquet/factors/factor_name=*_cs")
    ])

    if not cs_factors:
        add_check("factor_cs_count", "FAIL", "No _cs factors found in cache")
    else:
        dup_factors = []
        short_factors = []
        for name in cs_factors:
            cov = loader.factor_coverage(name, args.start, args.end)
            if cov["duplicates"] > 0:
                dup_factors.append(f"{name}: {cov['duplicates']} dup")
            if cov["n_dates"] < 12:
                short_factors.append(
                    f"{name}: {cov['n_dates']} dates (max={cov.get('max_date')})"
                )

        status = "PASS"
        detail_parts = [f"{len(cs_factors)} factors checked"]
        if dup_factors:
            status = "FAIL"
            detail_parts.append(f"{len(dup_factors)} with duplicates")
        if short_factors:
            if status == "PASS":
                status = "WARN"
            detail_parts.append(f"{len(short_factors)} with <12 dates")

        add_check("factor_cs_quality", status, "; ".join(detail_parts))

        if args.verbose:
            for name in cs_factors:
                cov = loader.factor_coverage(name, args.start, args.end)
                add_check(
                    f"factor:{name}",
                    "FAIL" if cov["duplicates"] > 0 else "PASS",
                    f"rows={cov['rows']}, dates={cov['n_dates']}, "
                    f"dup={cov['duplicates']}, "
                    f"range={cov.get('min_date')}-{cov.get('max_date')}",
                )

    # ------------------------------------------------------------------
    # 3. fwd_returns
    # ------------------------------------------------------------------
    fwd_cov = loader.factor_coverage("fwd_returns", args.start, args.end)
    if fwd_cov["rows"] == 0:
        add_check("fwd_returns", "FAIL", "No fwd_returns data in window")
    elif fwd_cov["duplicates"] > 0:
        add_check(
            "fwd_returns", "FAIL",
            f"{fwd_cov['duplicates']} duplicates, "
            f"{fwd_cov['n_dates']} dates"
        )
    elif fwd_cov["n_dates"] < 12:
        add_check(
            "fwd_returns", "WARN",
            f"Only {fwd_cov['n_dates']} dates (need >=12 for reliable IC)"
        )
    else:
        add_check(
            "fwd_returns", "PASS",
            f"{fwd_cov['rows']} rows, {fwd_cov['n_dates']} dates, 0 dup, "
            f"range={fwd_cov['min_date']}-{fwd_cov['max_date']}"
        )

    # ------------------------------------------------------------------
    # 4. limit_status
    # ------------------------------------------------------------------
    lim_df = loader.query(
        "limit_status",
        columns=["ts_code", "trade_date"],
        start_date=args.start, end_date=args.end,
    )
    if lim_df.empty:
        add_check("limit_status", "WARN", "No limit_status data in window")
    else:
        lim_dupes = int(lim_df.duplicated(["ts_code", "trade_date"]).sum())
        lim_dates = set(lim_df["trade_date"].unique())

        # Exec-date coverage
        sig_dates = cal.weekly_rebalance_dates(args.start, args.end)
        exec_dates = {cal.next_trade_day(int(d), 1) for d in sig_dates[:-1]}
        covered = lim_dates & exec_dates
        lim_cov = len(covered) / len(exec_dates) if exec_dates else 0.0

        # Full trade-day coverage (all trading days in the window)
        trade_days = set(
            int(d) for d in cal.trade_days_between(
                int(args.start), int(args.end)
            )
        )
        td_covered = lim_dates & trade_days
        td_cov = len(td_covered) / len(trade_days) if trade_days else 0.0

        detail = (
            f"0 dup, cached_dates={len(lim_dates)}/{len(trade_days)}, "
            f"exec coverage={lim_cov:.1%}"
        )

        # Trade-day coverage is informational for exec-scoped caches.
        # Always show in detail, but only FAIL in full-calendar mode.
        if args.limit_status_mode == "full-calendar":
            detail += f", trade-day coverage={td_cov:.1%}"
            td_threshold = 0.90
        else:
            detail += f", trade-day coverage={td_cov:.1%} (exec-scoped cache)"

        if lim_dupes > 0:
            add_check(
                "limit_status", "FAIL",
                f"{lim_dupes} duplicate (ts_code, trade_date) rows. "
                f"Run: python scripts/repair_cache.py --dataset limit_status "
                f"--start {args.start} --end {args.end}"
            )
        elif lim_cov < 0.8:
            add_check(
                "limit_status", "WARN",
                f"0 dup, exec_date coverage={lim_cov:.1%} "
                f"({len(covered)}/{len(exec_dates)}). {detail}"
            )
        elif args.limit_status_mode == "full-calendar" and td_cov < td_threshold:
            add_check(
                "limit_status", "FAIL",
                f"{detail} — trade-day coverage below {td_threshold:.0%} "
                f"in full-calendar mode"
            )
        else:
            add_check(
                "limit_status", "PASS",
                detail
            )

    # ------------------------------------------------------------------
    # 5. prices_adj coverage
    # ------------------------------------------------------------------
    adj_cov = loader.price_coverage("prices_adj", args.start, args.end)
    if adj_cov["coverage_ratio"] < 0.75:
        add_check(
            "prices_adj", "FAIL",
            f"Coverage={adj_cov['coverage_ratio']:.1%} "
            f"({adj_cov['n_dates']}/{adj_cov['expected_trade_dates']} dates). "
            f"First missing: {adj_cov['missing_dates'][:5]}"
        )
    elif adj_cov["coverage_ratio"] < 0.90:
        add_check(
            "prices_adj", "WARN",
            f"Coverage={adj_cov['coverage_ratio']:.1%} "
            f"({adj_cov['n_dates']}/{adj_cov['expected_trade_dates']} dates)"
        )
    else:
        add_check(
            "prices_adj", "PASS",
            f"Coverage={adj_cov['coverage_ratio']:.1%} "
            f"({adj_cov['n_dates']}/{adj_cov['expected_trade_dates']} dates)"
        )

    # ------------------------------------------------------------------
    # 6. daily_basic coverage
    # ------------------------------------------------------------------
    db_cov = loader.daily_basic_coverage(args.start, args.end)
    if db_cov["coverage_ratio"] < 0.8:
        add_check(
            "daily_basic", "FAIL",
            f"Coverage={db_cov['coverage_ratio']:.1%} "
            f"({db_cov['n_months_cached']}/{db_cov['n_months_expected']} months). "
            f"Missing: {db_cov.get('missing_dates', [])[:5]}"
        )
    else:
        add_check(
            "daily_basic", "PASS",
            f"Coverage={db_cov['coverage_ratio']:.1%} "
            f"({db_cov['n_months_cached']}/{db_cov['n_months_expected']} months)"
        )

    # ------------------------------------------------------------------
    # 7. index_weight coverage
    # ------------------------------------------------------------------
    iw_df = loader.query(
        "index_weight",
        columns=["trade_date"],
        start_date=args.start, end_date=args.end,
    )
    if iw_df.empty:
        add_check("index_weight", "FAIL", "No index_weight data in window")
    else:
        iw_dates = iw_df["trade_date"].nunique()
        add_check(
            "index_weight", "PASS" if iw_dates >= 6 else "WARN",
            f"{iw_dates} monthly snapshots"
        )

    # ------------------------------------------------------------------
    # 8. prices_raw coverage
    # ------------------------------------------------------------------
    raw_cov = loader.price_coverage("prices_raw", args.start, args.end)
    if raw_cov["coverage_ratio"] < 0.75:
        add_check(
            "prices_raw", "FAIL",
            f"Coverage={raw_cov['coverage_ratio']:.1%} "
            f"({raw_cov['n_dates']}/{raw_cov['expected_trade_dates']} dates)"
        )
    else:
        add_check(
            "prices_raw", "PASS",
            f"Coverage={raw_cov['coverage_ratio']:.1%} "
            f"({raw_cov['n_dates']}/{raw_cov['expected_trade_dates']} dates)"
        )

    # ------------------------------------------------------------------
    # 9. adj_factor coverage & duplicates
    # ------------------------------------------------------------------
    adjf_df = loader.query(
        "adj_factor",
        columns=["ts_code", "trade_date"],
        start_date=args.start, end_date=args.end,
    )
    if adjf_df.empty:
        add_check("adj_factor_coverage", "FAIL", "No adj_factor data in window")
    else:
        adjf_dupes = int(adjf_df.duplicated(["ts_code", "trade_date"]).sum())
        adjf_dates = adjf_df["trade_date"].nunique()
        trade_days = set(
            int(d) for d in cal.trade_days_between(
                int(args.start), int(args.end)
            )
        )
        adjf_cov = adjf_dates / len(trade_days) if trade_days else 0.0

        if adjf_dupes > 0:
            detail = (f"{adjf_dupes} duplicate (ts_code, trade_date) rows. "
                      f"Run: python scripts/repair_adj_factor.py "
                      f"--start {args.start} --end {args.end}")
            if args.verbose:
                # Show which keys are duplicated
                dup_mask = adjf_df.duplicated(["ts_code", "trade_date"], keep=False)
                dup_rows = adjf_df[dup_mask]
                dup_groups = dup_rows.groupby(["ts_code", "trade_date"]).size().reset_index(name="count")
                dup_sample = dup_groups.head(20).to_dict("records")
                detail += ("\nDuplicate keys (up to 20):\n" +
                          "\n".join(f"  - {r['ts_code']} @ {r['trade_date']} ({r['count']} rows)"
                                    for r in dup_sample))
                # Also show year partition sources if dedup data loaded with _source info
                dup_dates = sorted(dup_rows["trade_date"].unique())
                detail += f"\nAffected trade_dates range: {dup_dates[0] if dup_dates else 'N/A'} — {dup_dates[-1] if dup_dates else 'N/A'}"
            add_check("adj_factor_dedup", "FAIL", detail)
        else:
            add_check(
                "adj_factor_dedup", "PASS",
                f"0 duplicates, {adjf_dates}/{len(trade_days)} trade days "
                f"(coverage={adjf_cov:.1%})"
            )

        if adjf_cov < 0.90:
            add_check(
                "adj_factor_coverage", "WARN" if adjf_cov >= 0.75 else "FAIL",
                f"adj_factor trade-day coverage={adjf_cov:.1%} "
                f"({adjf_dates}/{len(trade_days)} days) — may cause "
                f"prices_adj gaps"
            )
        else:
            add_check(
                "adj_factor_coverage", "PASS",
                f"adj_factor trade-day coverage={adjf_cov:.1%} "
                f"({adjf_dates}/{len(trade_days)} days)"
            )

    # ------------------------------------------------------------------
    # 10. prices_adj extreme return check
    # ------------------------------------------------------------------
    # Get CSI300 universe stocks for relevant filtering
    iw_df = loader.query(
        "index_weight",
        columns=["ts_code"],
        start_date=args.start, end_date=args.end,
    )
    universe_stocks = set(iw_df["ts_code"].unique()) if not iw_df.empty else set()

    adj_prices_df = loader.query(
        "prices_adj",
        columns=["ts_code", "trade_date", "adj_close"],
        start_date=args.start, end_date=args.end,
    )
    if not adj_prices_df.empty:
        from data.adjust import validate_adj_prices
        try:
            # Filter to universe stocks only (CSI300 constituents)
            if universe_stocks:
                adj_prices_universe = adj_prices_df[
                    adj_prices_df["ts_code"].isin(universe_stocks)
                ]
                if adj_prices_universe.empty:
                    adj_prices_universe = adj_prices_df  # fallback
            else:
                adj_prices_universe = adj_prices_df

            val = validate_adj_prices(adj_prices_universe)
            n_daily = val.get("n_daily_jumps", 0)
            n_weekly = val.get("n_weekly_jumps", 0)

            # Also check full universe for reporting
            if len(adj_prices_universe) < len(adj_prices_df):
                val_full = validate_adj_prices(adj_prices_df)
                n_daily_full = val_full.get("n_daily_jumps", 0)
                n_weekly_full = val_full.get("n_weekly_jumps", 0)
                full_detail = (
                    f" (full market: {n_daily_full} daily, "
                    f"{n_weekly_full} weekly — non-CSI300, non-blocking)"
                )
            else:
                full_detail = ""

            if n_daily > 0 or n_weekly > 0:
                add_check(
                    "prices_adj_jumps", "FAIL",
                    f"{n_daily} extreme daily returns (>5x), "
                    f"{n_weekly} extreme weekly returns (>10x) "
                    f"in CSI300 universe.{full_detail} "
                    f"Check {val.get('failures', [])[:3]}"
                )
            else:
                add_check(
                    "prices_adj_jumps", "PASS",
                    f"0 extreme daily/weekly adj_close returns "
                    f"in CSI300 universe{full_detail}"
                )
        except Exception as e:
            add_check("prices_adj_jumps", "WARN", f"Could not validate: {e}")
    else:
        add_check("prices_adj_jumps", "WARN", "No prices_adj data for jump check")

    # ------------------------------------------------------------------
    # 11. index_daily trade-day coverage
    # ------------------------------------------------------------------
    idx_df = loader.query(
        "index_daily",
        columns=["ts_code", "trade_date"],
        start_date=args.start, end_date=args.end,
    )
    if idx_df.empty:
        add_check("index_daily_coverage", "FAIL",
                  "No index_daily data in window — benchmark will be 0")
    else:
        idx_dates = set(idx_df["trade_date"].unique())
        idx_cov = len(idx_dates & trade_days) / len(trade_days) if trade_days else 0.0
        idx_codes = set(idx_df["ts_code"].unique())
        if idx_cov < 0.90:
            missing = sorted(trade_days - idx_dates)[:10]
            add_check(
                "index_daily_coverage", "FAIL",
                f"Trade-day coverage={idx_cov:.1%} "
                f"({len(idx_dates & trade_days)}/{len(trade_days)}). "
                f"Codes: {idx_codes}. Missing: {missing}"
            )
        else:
            add_check(
                "index_daily_coverage", "PASS",
                f"Trade-day coverage={idx_cov:.1%} "
                f"({len(idx_dates & trade_days)}/{len(trade_days)}). "
                f"Codes: {idx_codes}"
            )

    return results


def print_human(results):
    """Print human-readable audit report."""
    print()
    print("=" * 64)
    print(f"Cache Audit: {results['window']['start']} -> {results['window']['end']}")
    print("=" * 64)
    print(f"{'Check':<30} {'Status':<8} Detail")
    print("-" * 64)
    for c in results["checks"]:
        print(f"{c['name']:<30} {c['status']:<8} {c['detail'][:80]}")
    print("-" * 64)
    total = results["passed"] + results["warned"] + results["failed"]
    print(f"Total: {total} checks | "
          f"PASS={results['passed']} | "
          f"WARN={results['warned']} | "
          f"FAIL={results['failed']}")
    print()

    if results["failed"] > 0:
        print("FAILED checks need attention before running Phase 1/2.")
        print("See messages above for repair instructions.")
    elif results["warned"] > 0:
        print("All critical checks PASS. Warnings may affect backtest quality.")


def main():
    parser = argparse.ArgumentParser(
        description="Audit cached data for research pipeline readiness"
    )
    parser.add_argument("--start", default="20160101", help="Start date YYYYMMDD")
    parser.add_argument("--end", default="20161231", help="End date YYYYMMDD")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Show per-factor details")
    parser.add_argument("--limit-status-mode", default="exec",
                        choices=["exec", "full-calendar"],
                        help="exec: require >=80%% execution-date coverage (default). "
                             "full-calendar: require >=90%% trade-day coverage")
    args = parser.parse_args()

    results = audit(args)

    if args.json:
        print(json.dumps(results, indent=2, default=str))
    else:
        print_human(results)

    # Exit code: 0=PASS, 1=FAIL, 2=WARN
    if results["failed"] > 0:
        sys.exit(1)
    elif results["warned"] > 0:
        sys.exit(2)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()

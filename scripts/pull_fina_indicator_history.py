#!/usr/bin/env python
"""
Pull historical fina_indicator data from Tushare for 2017-2022.

Strategy:
- Pull by period (end_date) with 80 stock batches → each call ≤100 rows
- 24 periods × ~50 batches = ~1200 API calls
- Rate limit: 0.2s between calls (~240s total)
- Data auto-cached to data/parquet/fina_indicator/ via tushare_client

Usage:
  python -u scripts/pull_fina_indicator_history.py
  python -u scripts/pull_fina_indicator_history.py --resume-from 2019
"""

import argparse
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def get_universe_stocks() -> list:
    """Get all unique stocks from price data."""
    prices_dir = ROOT / "data" / "parquet" / "prices_adj"
    if not prices_dir.exists():
        return []
    stocks = set()
    for year_dir in sorted(prices_dir.iterdir()):
        if not year_dir.is_dir() or not year_dir.name.startswith("year="):
            continue
        year = int(year_dir.name.split("=")[1])
        if year < 2017 or year > 2024:
            continue
        for month_dir in sorted(year_dir.iterdir()):
            for pq_file in month_dir.glob("*.parquet"):
                try:
                    part = pd.read_parquet(pq_file, columns=["ts_code"])
                    part.columns = [c.strip().lower() for c in part.columns]
                    stocks.update(part["ts_code"].astype(str).unique())
                except Exception:
                    continue
    return sorted(stocks)


def main():
    parser = argparse.ArgumentParser(description="Pull historical fina_indicator")
    parser.add_argument("--batch-size", type=int, default=80)
    parser.add_argument("--sleep", type=float, default=0.2)
    parser.add_argument("--resume-from", type=int, help="Resume from year")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    # Generate periods: all quarterly end dates 2017-2022
    all_periods = []
    for y in range(2017, 2023):
        for m in ["0331", "0630", "0930", "1231"]:
            all_periods.append(f"{y}{m}")

    if args.resume_from:
        all_periods = [p for p in all_periods if int(p[:4]) >= args.resume_from]

    print(f"=== Pull Historical fina_indicator ===\n")
    print(f"Periods: {len(all_periods)} ({all_periods[0]} → {all_periods[-1]})")
    print(f"Batch size: {args.batch_size}")
    print(f"Sleep: {args.sleep}s")
    if args.dry_run:
        print("MODE: DRY RUN")
    print()

    from data.tushare_client import get_client
    client = get_client()
    if not client.available:
        print("ERROR: Tushare client not available. Check TUSHARE_TOKEN in .env")
        return 1

    stocks = get_universe_stocks()
    batches = [stocks[i:i + args.batch_size] for i in range(0, len(stocks), args.batch_size)]

    print(f"Universe stocks: {len(stocks)}")
    print(f"Batches per period: {len(batches)}")
    print(f"Total API calls: {len(batches) * len(all_periods)}")
    print(f"Estimated time: {len(batches) * len(all_periods) * args.sleep:.0f}s")
    print()

    if args.dry_run:
        print("[DRY RUN] Done.")
        return 0

    fields = ("ts_code,ann_date,end_date,roe,roa,"
              "grossprofit_margin,netprofit_margin,"
              "profit_dedt,debt_to_assets")

    total_rows = 0
    t_start = time.time()

    for pi, period in enumerate(all_periods):
        period_rows = 0
        batch_errors = 0
        print(f"\n[{pi+1}/{len(all_periods)}] Period {period} ", end="", flush=True)

        for bi, batch in enumerate(batches):
            try:
                df = client.get_fina_indicator(
                    ts_code=",".join(batch),
                    period=period,
                    fields=fields,
                    use_cache=False,
                )
                n = len(df) if df is not None and not df.empty else 0
                period_rows += n
                total_rows += n
                time.sleep(args.sleep)

            except KeyboardInterrupt:
                print(f"\n\nInterrupted at period={period}, batch={bi+1}")
                print(f"Total rows: {total_rows}")
                print(f"Resume: --resume-from {period[:4]}")
                return 0

            except Exception:
                batch_errors += 1
                time.sleep(1.0)
                if batch_errors > 10:
                    print(f"\n  Too many errors, skipping period")
                    break

        elapsed = time.time() - t_start
        eta = (elapsed / (pi + 1)) * (len(all_periods) - pi - 1) if pi > 0 else 0
        print(f"→ {period_rows} rows (total: {total_rows}, errors: {batch_errors}) "
              f"[{elapsed:.0f}s elapsed, ETA {eta:.0f}s]", flush=True)

    elapsed = time.time() - t_start
    print(f"\n{'='*60}")
    print(f"COMPLETE: {total_rows} rows in {elapsed:.0f}s ({elapsed/60:.1f}m)")
    print(f"Data cached: data/parquet/fina_indicator/")
    print(f"\nNext: python -u scripts/repair_fundamental_factors.py --force")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

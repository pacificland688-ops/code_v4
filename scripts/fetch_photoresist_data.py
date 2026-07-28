"""
Photoresist Panic Research — Data Fetcher
==========================================
Fetches all required data from Tushare Pro for the photoresist panic
evaluation pipeline (Phase 0 + path rules R0-R3).

Required data:
  - prices_adj (daily OHLCV, adjusted) for 15 stocks + indices
  - index_daily for 000300.SH, 931865.CSI, 399006.SZ
  - adj_factor for all stocks
  - limit_status (涨跌停价格)
  - suspend_status (停牌记录)
  - stock_status (上市/退市/ST)

Date range: 2015-01-01 to 2025-12-31
  (2015-2016 for rolling quantile warmup; 2017-2025 is the research window)

Usage:
  python scripts/fetch_photoresist_data.py           # full fetch
  python scripts/fetch_photoresist_data.py --check   # check existing cache only
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv()

TUSHARE_TOKEN = os.getenv("TUSHARE_TOKEN", "")

from data.tushare_client import TushareClient

# ── Universe codes (from configs/photoresist_universe.yaml) ──────────────
CORE_CODES = ["300655.SZ", "300346.SZ", "603650.SH", "300236.SZ"]
ADJACENT_CODES = ["300576.SZ", "300398.SZ", "300537.SZ", "300429.SZ", "002584.SZ"]
MAPPING_CODES = ["002409.SZ", "688019.SH", "688126.SH", "688233.SH", "300054.SZ", "688012.SH"]
ALL_STOCK_CODES = CORE_CODES + ADJACENT_CODES + MAPPING_CODES

INDEX_CODES = ["000300.SH", "931865.CSI", "399006.SZ"]

DATE_START_STR = "20150101"
DATE_END_STR = "20251231"


def parse_args():
    p = argparse.ArgumentParser(description="Fetch photoresist research data from Tushare")
    p.add_argument("--check", action="store_true", help="Only check existing cache")
    p.add_argument("--start", default=DATE_START_STR)
    p.add_argument("--end", default=DATE_END_STR)
    p.add_argument("--skip-prices", action="store_true")
    p.add_argument("--skip-index", action="store_true")
    p.add_argument("--skip-adj-factor", action="store_true")
    p.add_argument("--skip-limits", action="store_true")
    p.add_argument("--skip-suspend", action="store_true")
    p.add_argument("--skip-stock-status", action="store_true")
    return p.parse_args()


def fetch_trade_calendar(client: TushareClient, start: str, end: str):
    """Fetch trading calendar — needed for all other fetches. Returns None on failure."""
    print("\n[0] Trading calendar ...")
    try:
        cal = client.get_trade_cal(exchange="SSE", start_date=start, end_date=end)
        if cal is None or cal.empty:
            print("    ERROR: empty response")
            return None
        print(f"    {len(cal)} trading days ({start} – {end})")
        return cal
    except Exception as e:
        print(f"    ERROR: {e}")
        return None


def fetch_prices(client: TushareClient, codes: list[str], start: str, end: str):
    """Fetch daily OHLCV (raw prices) for all stocks."""
    print(f"\n[1] Daily prices for {len(codes)} stocks ...")
    print(f"    Codes: {codes}")

    # Fetch year by year to avoid timeouts
    start_year = int(start[:4])
    end_year = int(end[:4])

    all_data = []
    failed_years = []
    for yr in range(start_year, end_year + 1):
        yr_start = f"{yr}0101"
        yr_end = f"{yr}1231"
        print(f"    Year {yr} ...", end=" ", flush=True)
        try:
            chunk = client.get_daily(
                ts_code=codes,
                start_date=yr_start,
                end_date=yr_end,
                use_cache=True,
            )
            n = len(chunk) if chunk is not None else 0
            print(f"{n} rows")
            if chunk is not None and not chunk.empty:
                all_data.append(chunk)
            elif n == 0:
                failed_years.append(yr)
        except Exception as e:
            print(f"ERROR: {e}")
            failed_years.append(yr)

    if failed_years:
        print(f"    WARNING: {len(failed_years)} years had no data: {failed_years}")
    if not all_data:
        print(f"    ERROR: all {end_year - start_year + 1} years returned no data")
        return None

    import pandas as pd
    result = pd.concat(all_data, ignore_index=True)
    n_unique = result['ts_code'].nunique()
    n_requested = len(codes)
    print(f"    Total: {len(result)} rows, {n_unique}/{n_requested} stocks")
    if n_unique < n_requested:
        missing = n_requested - n_unique
        print(f"    WARNING: {missing} requested stock(s) have no price data")
    return result


def fetch_adj_factor(client: TushareClient, codes: list[str], start: str, end: str):
    """Fetch adjustment factors for all stocks."""
    print(f"\n[2] Adj factors for {len(codes)} stocks ...")
    try:
        result = client.get_adj_factor(
            ts_code=codes,
            start_date=start,
            end_date=end,
            batch_size=100,
        )
        n = len(result) if result is not None and not result.empty else 0
        print(f"    {n} rows")
        return result
    except Exception as e:
        print(f"    ERROR: {e}")
        return None


def fetch_index_daily(client: TushareClient, codes: list[str], start: str, end: str):
    """Fetch index daily data. Returns False if any code fetch failed."""
    print(f"\n[3] Index daily for {codes} ...")
    any_failure = False
    for code in codes:
        print(f"    {code} ...", end=" ", flush=True)
        try:
            result = client.get_index_daily(
                index_code=code,
                start_date=start,
                end_date=end,
            )
            n = len(result) if result is not None and not result.empty else 0
            print(f"{n} rows")
            if n == 0:
                any_failure = True
        except Exception as e:
            print(f"ERROR: {e}")
            any_failure = True
    return None if any_failure else True


def fetch_limit_status(client: TushareClient, codes: list[str], start: str, end: str):
    """Fetch daily price limits. Returns False if any year fetch failed."""
    print(f"\n[4] Limit status for {len(codes)} stocks ...")

    # Fetch month by month to manage volume
    import pandas as pd
    start_year = int(start[:4])
    end_year = int(end[:4])
    any_failure = False

    for yr in range(start_year, end_year + 1):
        yr_start = f"{yr}0101"
        yr_end = f"{yr}1231"
        print(f"    Year {yr} ...", end=" ", flush=True)
        try:
            chunk = client.get_stk_limit(
                ts_code=codes,
                start_date=yr_start,
                end_date=yr_end,
                write_cache=True,
            )
            n = len(chunk) if chunk is not None else 0
            print(f"{n} rows")
            if n == 0:
                any_failure = True
        except Exception as e:
            print(f"ERROR: {e}")
            any_failure = True
    return None if any_failure else True


def fetch_suspend_status(client: TushareClient, codes: list[str], start: str, end: str):
    """Fetch suspension records."""
    print(f"\n[5] Suspend status for {len(codes)} stocks ...")
    try:
        result = client.get_suspend(
            ts_code=codes,
            start_date=start,
            end_date=end,
        )
        n = len(result) if result is not None and not result.empty else 0
        print(f"    {n} rows")
        return result
    except Exception as e:
        print(f"    ERROR: {e}")
        return None


def fetch_stock_status(client: TushareClient):
    """Fetch stock basic info (listing, ST status)."""
    print("\n[6] Stock basic info ...")
    try:
        result = client.get_stock_basic()
        n = len(result) if result is not None and not result.empty else 0
        print(f"    {n} rows")
        return result if n > 0 else None
    except Exception as e:
        print(f"    ERROR: {e}")
        return None


def fetch_namechange(client: TushareClient, codes: list[str]):
    """Fetch historical name changes (股票曾用名) for PIT ST detection."""
    print(f"\n[7] Name change history for {len(codes)} stocks ...")
    try:
        result = client.get_namechange(
            ts_code=codes,
        )
        n = len(result) if result is not None and not result.empty else 0
        print(f"    {n} rows")
        return result
    except Exception as e:
        print(f"    ERROR: {e}")
        return None


def fetch_daily_basic(client: TushareClient, codes: list[str], start: str, end: str):
    """Fetch daily basic data (turnover_rate_f, circ_mv, etc.) for all trading days."""
    print(f"\n[8] Daily basic for {len(codes)} stocks ...")
    try:
        result = client.get_daily_basic(
            ts_code=codes,
            start_date=start,
            end_date=end,
            fields="ts_code,trade_date,turnover_rate,turnover_rate_f,volume_ratio,circ_mv,total_mv",
        )
        n = len(result) if result is not None and not result.empty else 0
        print(f"    {n} rows")
        return result if n > 0 else None
    except Exception as e:
        print(f"    ERROR: {e}")
        return None


def check_cache():
    """Report existing cache state."""
    cache_path = ROOT / "data" / "parquet"
    if not cache_path.exists():
        print("Cache directory does not exist: data/parquet/")
        return

    tables = {
        "prices_raw": "日线行情",
        "prices_adj": "复权行情",
        "adj_factor": "复权因子",
        "index_daily": "指数日线",
        "limit_status": "涨跌停状态",
        "suspend_status": "停牌记录",
        "stock_status": "股票基本信息",
        "namechange": "股票曾用名",
        "daily_basic": "每日换手率/市值",
        "trade_cal": "交易日历",
    }

    print("=" * 60)
    print("Parquet Cache Status")
    print("=" * 60)

    import pandas as pd
    import pyarrow.dataset as ds

    for table_name, desc in tables.items():
        table_path = cache_path / table_name
        if not table_path.exists():
            print(f"\n  [{desc}] {table_name}: EMPTY (directory missing)")
            continue

        parquet_files = list(table_path.rglob("*.parquet"))
        if not parquet_files:
            print(f"\n  [{desc}] {table_name}: EMPTY (no parquet files)")
            continue

        total_rows = 0
        min_date = None
        max_date = None
        codes = set()
        import pyarrow.parquet as parquet
        for pq_file in parquet_files:
            try:
                schema_names = set(parquet.read_schema(pq_file).names)
                read_cols = [
                    col for col in ("trade_date", "ann_date", "start_date", "ts_code")
                    if col in schema_names
                ]
                df = pd.read_parquet(pq_file, columns=read_cols)
                total_rows += len(df)
                date_col = next(
                    (col for col in ("trade_date", "ann_date", "start_date") if col in df.columns),
                    None,
                )
                if date_col is not None and df[date_col].notna().any():
                    dates = pd.to_numeric(df[date_col], errors="coerce").dropna()
                    dmin = int(dates.min())
                    dmax = int(dates.max())
                    if min_date is None or dmin < min_date:
                        min_date = dmin
                    if max_date is None or dmax > max_date:
                        max_date = dmax
                if "ts_code" in df.columns:
                    codes.update(df["ts_code"].astype(str).unique())
            except Exception as exc:
                print(f"\n    WARNING: corrupted file {pq_file.name}: {exc}")

        size_mb = sum(f.stat().st_size for f in parquet_files) / (1024 * 1024)
        print(f"\n  [{desc}] {table_name}:")
        print(f"    Files: {len(parquet_files)}, Rows: {total_rows:,}, Size: {size_mb:.1f} MB")
        print(f"    Date range: {min_date} – {max_date}")
        print(f"    Stocks: {len(codes)}")
        if len(codes) <= 20:
            print(f"    Codes: {sorted(codes)}")


def main():
    args = parse_args()

    if args.check:
        check_cache()
        return 0

    if not TUSHARE_TOKEN or TUSHARE_TOKEN == "your_tushare_pro_token_here":
        print("=" * 60)
        print("ERROR: Tushare token not configured.")
        print("  1. Copy .env.example to .env")
        print("  2. Replace 'your_tushare_pro_token_here' with your actual token")
        print("  3. Token available at: https://tushare.pro/user/token")
        print("=" * 60)
        return 1

    print("=" * 60)
    print("Photoresist Panic — Data Fetcher")
    print(f"  Range: {args.start} – {args.end}")
    print(f"  Stocks: {len(ALL_STOCK_CODES)}")
    print(f"  Indices: {INDEX_CODES}")
    print("=" * 60)

    client = TushareClient(cache_path=str(ROOT / "data" / "parquet"))

    if not client.available:
        print("\nERROR: Tushare Pro API not available.")
        print("  Check: 1) TUSHARE_TOKEN is correct in .env")
        print("        2) Network connectivity")
        print("        3) Tushare Pro subscription is active")
        return 1

    failures = []  # track which steps failed

    # 0. Calendar (needed for other fetches)
    if fetch_trade_calendar(client, args.start, args.end) is None:
        failures.append("trade_calendar")

    # 1. Daily prices
    if not args.skip_prices:
        if fetch_prices(client, ALL_STOCK_CODES, args.start, args.end) is None:
            failures.append("prices")

    # 2. Adj factors
    if not args.skip_adj_factor:
        if fetch_adj_factor(client, ALL_STOCK_CODES, args.start, args.end) is None:
            failures.append("adj_factor")

    # 3. Index daily
    if not args.skip_index:
        if fetch_index_daily(client, INDEX_CODES, args.start, args.end) is None:
            failures.append("index_daily")

    # 4. Limit status
    if not args.skip_limits:
        if fetch_limit_status(client, ALL_STOCK_CODES, args.start, args.end) is None:
            failures.append("limit_status")

    # 5. Suspend status
    if not args.skip_suspend:
        if fetch_suspend_status(client, ALL_STOCK_CODES, args.start, args.end) is None:
            failures.append("suspend_status")

    # 6. Stock status
    if not args.skip_stock_status:
        if fetch_stock_status(client) is None:
            failures.append("stock_status")

    # 7. Name change history (PIT ST detection)
    if not args.skip_stock_status:
        if fetch_namechange(client, ALL_STOCK_CODES) is None:
            failures.append("namechange")

    # 8. Daily basic (turnover_rate_f, circ_mv — DAILY, not month-end)
    if not args.skip_prices:
        if fetch_daily_basic(client, ALL_STOCK_CODES, args.start, args.end) is None:
            failures.append("daily_basic")

    # ── Final cache report ──────────────────────────────────────────────
    print("\n" + "=" * 60)
    if failures:
        print(f"ERROR: {len(failures)} fetch step(s) FAILED: {', '.join(failures)}")
        print("  Re-run to retry. Missing data will cause downstream issues.")
        print("  The evaluation pipeline will use PROXY judgments for missing data.")
        print("=" * 60)
        return 1
    print("Data fetch complete. Running cache check...")
    print("=" * 60)
    check_cache()

    print("\nNext step:")
    print("  python scripts/build_photoresist_panic_events.py --start 20170101 --end 20251231")
    print("  python scripts/evaluate_photoresist_panic_path_rules.py --start 20170101 --end 20251231")

    return 0


if __name__ == "__main__":
    sys.exit(main())

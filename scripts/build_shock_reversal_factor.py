#!/usr/bin/env python
"""Build shock_reversal factor cache for frozen validation.

Explicit, auditable factor generation pipeline for
``abnormal_drop_reversal_5`` → ``abnormal_drop_reversal_5_cs``.

Usage:
  python scripts/build_shock_reversal_factor.py --start 20170101 --end 20241231 --recompute
  python scripts/build_shock_reversal_factor.py --start 20250101 --end 20251231 --recompute
  python scripts/build_shock_reversal_factor.py --start 20260101 --end 20260605 --recompute

Outputs:
  - data/parquet/factors/factor_name=abnormal_drop_reversal_5/
  - data/parquet/factors/factor_name=abnormal_drop_reversal_5_cs/
  - Coverage report by year
  - Filter diagnostics (limit-down, liquidity, ST, suspend, IPO counts)
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Optional

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("build_shock_reversal")


def _load_universe(start_date: str, end_date: str) -> list:
    """Load CSI 300 PIT universe stocks for the date range."""
    from data.universe import get_universe_builder
    ub = get_universe_builder()
    ub.load(start_date=start_date, end_date=end_date)

    from data.calendar import get_calendar
    cal = get_calendar()
    cal.load(start_date=start_date, end_date=end_date)
    signal_dates = cal.weekly_rebalance_dates(start_date, end_date)

    all_stocks: set = set()
    for d_str in signal_dates:
        d_int = int(d_str)
        stocks = ub.get_universe(d_int)
        all_stocks.update(stocks)

    logger.info(
        "Universe: %d unique stocks across %d signal dates",
        len(all_stocks), len(signal_dates),
    )
    return sorted(all_stocks)


def _compute_raw_factor(
    ts_codes: list, start_date: str, end_date: str, recompute: bool
) -> pd.DataFrame:
    """Compute or load raw abnormal_drop_reversal_5 factor."""
    from factors.shock_reversal import ShockReversalComputer
    from data.panel_loader import get_loader

    loader = get_loader()

    if not recompute:
        cov = loader.factor_coverage(
            "abnormal_drop_reversal_5", start_date, end_date
        )
        if cov["n_dates"] >= 12 and cov["duplicates"] == 0:
            logger.info(
                "Raw factor already cached: %d rows, %d dates",
                cov["rows"], cov["n_dates"],
            )
            return loader.read_factor(
                "abnormal_drop_reversal_5", start_date, end_date, ts_codes=ts_codes
            )

    # Clean stale cache
    if recompute:
        _clean_factor_cache("abnormal_drop_reversal_5", start_date, end_date)

    computer = ShockReversalComputer()
    raw = computer.compute_factor(
        ts_codes=ts_codes,
        start_date=start_date,
        end_date=end_date,
        factor_name="abnormal_drop_reversal_5",
        save=True,
    )

    # Print filter diagnostics
    stats = computer.get_filter_stats()
    if stats:
        logger.info("Filter diagnostics:")
        for key, count in sorted(stats.items()):
            logger.info("  %s: %d", key, count)

    return raw


def _cs_process(raw_df: pd.DataFrame) -> pd.DataFrame:
    """Cross-sectionally process the raw factor.

    P0-1 fix: Uses section="shock_reversal" to read the nested
    ``shock_reversal.cross_section`` block.  No silent fallback —
    if the config is missing or misconfigured, raises RuntimeError.
    """
    if raw_df.empty:
        return raw_df

    from factors.cross_section import create_processor_from_config

    cs = create_processor_from_config(
        "configs/factors_shock_reversal.yaml",
        section="shock_reversal",
    )

    # Safety assertion: must use drop, not median imputation
    if cs.missing_method != "drop":
        raise RuntimeError(
            "build_shock_reversal_factor: CS processor must use "
            "missing_method='drop', got %r. Check "
            "configs/factors_shock_reversal.yaml"
            % cs.missing_method
        )

    logger.info(
        "Shock CS processor: missing_method=%s, neutralizers=%s",
        cs.missing_method, cs.neutralizers,
    )

    processed = cs.process_factor(raw_df, "abnormal_drop_reversal_5", save=True)
    return processed


def _clean_factor_cache(factor_name: str, start_date: str, end_date: str) -> None:
    """Remove existing cache partitions for the given date range."""
    import shutil
    from data.panel_loader import get_loader

    loader = get_loader()
    base = loader.data_path / f"factors/factor_name={factor_name}"
    if not base.exists():
        return

    for y in range(int(start_date[:4]), int(end_date[:4]) + 1):
        ydir = base / f"year={y}"
        if ydir.exists():
            shutil.rmtree(str(ydir))
            logger.info("Cleaned %s year=%d", factor_name, y)


def _coverage_report(factor_name: str, start_date: str, end_date: str) -> dict:
    """Generate coverage report for a factor."""
    from data.panel_loader import get_loader

    loader = get_loader()
    cov = loader.factor_coverage(factor_name, start_date, end_date)

    # Per-year breakdown
    yearly = {}
    for y in range(int(start_date[:4]), int(end_date[:4]) + 1):
        ys = f"{y}0101"
        ye = f"{y}1231"
        ycov = loader.factor_coverage(factor_name, ys, ye)
        yearly[y] = {
            "rows": ycov["rows"],
            "n_dates": ycov["n_dates"],
            "duplicates": ycov["duplicates"],
        }

    return {
        "factor": factor_name,
        "overall": cov,
        "yearly": yearly,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build shock_reversal factor cache"
    )
    parser.add_argument("--start", required=True, help="Start date YYYYMMDD")
    parser.add_argument("--end", required=True, help="End date YYYYMMDD")
    parser.add_argument(
        "--recompute", action="store_true",
        help="Recompute even if cache exists",
    )
    parser.add_argument(
        "--skip-cs", action="store_true",
        help="Skip cross-sectional processing (raw only)",
    )
    args = parser.parse_args()

    start = args.start
    end = args.end

    # 1. Load universe
    ts_codes = _load_universe(start, end)
    if not ts_codes:
        logger.error("Empty universe — check index_weight cache for %s→%s", start, end)
        return 1

    # 2. Compute raw factor
    raw = _compute_raw_factor(ts_codes, start, end, args.recompute)
    if raw.empty:
        logger.error("Raw factor computation produced no results")
        return 1

    logger.info(
        "Raw factor: %d rows, %d stocks, %d dates",
        len(raw), raw["ts_code"].nunique(), raw["trade_date"].nunique(),
    )

    # 3. Coverage report (raw)
    raw_cov = _coverage_report("abnormal_drop_reversal_5", start, end)
    logger.info("Raw factor coverage: %s", raw_cov["overall"])
    for y, yc in sorted(raw_cov["yearly"].items()):
        status = "OK" if yc["n_dates"] >= 40 else "LOW"
        logger.info("  %d: %d rows, %d dates [%s]", y, yc["rows"], yc["n_dates"], status)

    # 4. Cross-sectional processing
    if not args.skip_cs:
        processed = _cs_process(raw)
        if processed.empty:
            logger.error("CS processing produced no results")
            return 1

        logger.info(
            "Processed factor: %d rows, %d stocks, %d dates",
            len(processed),
            processed["ts_code"].nunique(),
            processed["trade_date"].nunique(),
        )

        # Coverage report (processed)
        cs_cov = _coverage_report("abnormal_drop_reversal_5_cs", start, end)
        logger.info("CS factor coverage: %s", cs_cov["overall"])
        for y, yc in sorted(cs_cov["yearly"].items()):
            status = "OK" if yc["n_dates"] >= 40 else "LOW"
            logger.info("  %d: %d rows, %d dates [%s]", y, yc["rows"], yc["n_dates"], status)

    logger.info("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

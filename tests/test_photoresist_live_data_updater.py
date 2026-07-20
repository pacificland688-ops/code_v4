"""Data updater tests — real date arithmetic + per-security planning (plan §10)."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from live.photoresist_panic.data_updater import (  # noqa: E402
    contiguous_ranges, date_to_yyyymmdd, security_update_plan,
    yyyymmdd_add_days, yyyymmdd_to_date,
)


# ── Date arithmetic (plan §3.1) ─────────────────────────────────────────
def test_month_end_rollover():
    assert yyyymmdd_add_days(20260131, 1) == 20260201


def test_year_end_rollover():
    assert yyyymmdd_add_days(20261231, 1) == 20270101


def test_leap_february():
    assert yyyymmdd_add_days(20240228, 1) == 20240229  # 2024 is a leap year
    assert yyyymmdd_add_days(20240229, 1) == 20240301
    assert yyyymmdd_add_days(20250228, 1) == 20250301  # 2025 is not


def test_weekend_and_holiday_spans_are_plain_calendar_math():
    # Friday +1 = Saturday (calendar); trading-day logic lives in the
    # exchange calendar, never in integer arithmetic
    assert yyyymmdd_add_days(20260213, 1) == 20260214
    assert yyyymmdd_add_days(20260101, -1) == 20251231


def test_integer_plus_one_is_wrong_and_we_do_not_do_it():
    # regression guard: the buggy pattern produces invalid dates
    assert 20260131 + 1 == 20260132  # invalid date int
    with pytest.raises(ValueError):
        yyyymmdd_to_date(20260132)
    assert date_to_yyyymmdd(yyyymmdd_to_date(yyyymmdd_add_days(20260131, 1))) == 20260201


# ── Fetch range planning ────────────────────────────────────────────────
def test_contiguous_ranges_merges_across_weekends_splits_on_long_gaps():
    days = [20260105, 20260106, 20260109,        # weekend inside -> one range
            20260224, 20260225]                  # spring-festival distance -> split
    assert contiguous_ranges(days) == [(20260105, 20260109),
                                       (20260224, 20260225)]


def test_contiguous_ranges_empty():
    assert contiguous_ranges([]) == []


# ── Per-security planning (plan §3.2) ───────────────────────────────────
class FakeCache:
    """ParquetCache stub: returns pre-seeded (ts_code -> dates)."""

    def __init__(self, dates_by_code):
        self.dates_by_code = dates_by_code

    def read(self, table_name, columns=None, filters=None, partition=None):
        code = None
        lo, hi = None, None
        for field, op, value in filters or []:
            if field == "ts_code" and op == "==":
                code = value
            elif field == "trade_date" and op == ">=":
                lo = int(value)
            elif field == "trade_date" and op == "<=":
                hi = int(value)
        dates = [d for d in self.dates_by_code.get(code, [])
                 if (lo is None or d >= lo) and (hi is None or d <= hi)]
        return pd.DataFrame({"ts_code": code, "trade_date": dates})


def test_security_update_plan_is_per_code_not_group_max():
    open_dates = [20260105, 20260106, 20260107, 20260108, 20260109]
    cache = FakeCache({
        "AAA.SZ": open_dates,                       # complete
        "BBB.SZ": [20260105, 20260109],             # interior gap, fresh max
    })
    complete = security_update_plan(cache, "prices_adj", "AAA.SZ", open_dates)
    lagging = security_update_plan(cache, "prices_adj", "BBB.SZ", open_dates)
    assert complete["missing_dates"] == []
    assert complete["fetch_ranges"] == []
    # BBB's gap is found even though its max date equals the group max
    assert lagging["cached_max_date"] == 20260109
    assert lagging["missing_dates"] == [20260106, 20260107, 20260108]
    assert lagging["fetch_ranges"] == [(20260106, 20260108)]


def test_security_update_plan_empty_cache_fetches_everything():
    open_dates = [20260105, 20260106]
    plan = security_update_plan(FakeCache({}), "index_daily", "931865.CSI",
                                open_dates)
    assert plan["missing_dates"] == open_dates
    assert plan["fetch_ranges"] == [(20260105, 20260106)]
    assert plan["cached_max_date"] is None

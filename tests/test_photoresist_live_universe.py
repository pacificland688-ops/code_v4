"""PIT boundary tests for photoresist_universe_v2."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from live.photoresist_panic.universe import (  # noqa: E402
    UNIVERSE_COLUMNS, _validate_universe, active_members, load_universe_v2,
    universe_status,
)

CONFIG_PATH = ROOT / "configs" / "photoresist_universe_v2.yaml"
CORE = {"300655.SZ", "300346.SZ", "603650.SH", "300236.SZ"}


@pytest.fixture(scope="module")
def universe():
    frame, meta = load_universe_v2(CONFIG_PATH)
    return frame


def test_historical_v1_periods_untouched(universe):
    v1_core = universe[
        (universe["pool_type"] == "core")
        & (universe["universe_version"] == "photoresist_universe_v1")
    ]
    assert set(v1_core["ts_code"]) == CORE
    assert (v1_core["effective_end"] == 20251231).all()


def test_2026_periods_are_new_entries_not_overwrites(universe):
    v2_core = universe[
        (universe["pool_type"] == "core")
        & (universe["universe_version"] == "photoresist_universe_v2")
    ]
    assert set(v2_core["ts_code"]) == CORE
    assert (v2_core["effective_start"] == 20260101).all()
    assert (v2_core["announcement_date"].astype(int) <= 20260101).all()


def test_core_pool_continuous_across_year_boundary(universe):
    for day in (20251231, 20260102, 20260315, 20260715):
        members = active_members(universe, day, ("core",), "medium")
        assert set(members["ts_code"]) == CORE, f"gap at {day}"


def test_confirmed_desk_research_is_reported_pending_review(universe):
    status = universe_status(universe, 20260715)
    assert set(status["pending_review"]) == CORE


def test_membership_expires_after_effective_end(universe):
    status = universe_status(universe, 20270105)
    assert status["expired"] is True
    assert status["core_active_count"] == 0


def test_no_overlapping_periods_validated():
    rows = [
        {"ts_code": "X.SZ", "name": "x", "pool_type": "core",
         "effective_start": 20170101, "effective_end": 20251231,
         "source_type": "annual_report", "source_ref": "r",
         "announcement_date": None, "pit_confidence": "high",
         "business_tier": "", "universe_version": "v1", "review_status": ""},
        {"ts_code": "X.SZ", "name": "x", "pool_type": "core",
         "effective_start": 20251201, "effective_end": 20261231,  # overlaps
         "source_type": "annual_report", "source_ref": "r",
         "announcement_date": 20251031, "pit_confidence": "high",
         "business_tier": "", "universe_version": "v2", "review_status": ""},
    ]
    frame = pd.DataFrame(rows, columns=UNIVERSE_COLUMNS)
    with pytest.raises(ValueError, match="overlapping"):
        _validate_universe(frame, {"universe_version": "photoresist_universe_v2"})


def test_announcement_date_gates_membership():
    rows = [{
        "ts_code": "Y.SZ", "name": "y", "pool_type": "core",
        "effective_start": 20260101, "effective_end": 20261231,
        "source_type": "annual_report", "source_ref": "r",
        "announcement_date": 20260430, "pit_confidence": "high",
        "business_tier": "", "universe_version": "v2", "review_status": "",
    }]
    frame = pd.DataFrame(rows, columns=UNIVERSE_COLUMNS)
    # before the disclosure is public the stock must NOT be usable
    assert active_members(frame, 20260315, ("core",), "medium").empty
    assert len(active_members(frame, 20260430, ("core",), "medium")) == 1

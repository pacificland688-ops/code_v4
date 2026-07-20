"""
Shared walk-forward utilities for panic basket gate research.

Provides:
  - Unified train/test split with label_availability + embargo controls
  - Trading calendar helpers
  - Leakage audit output
  - Primary strategy definitions (frozen before any test evaluation)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np
import pandas as pd

# ── Primary strategies (FROZEN — do not change based on test results) ──
PRIMARY_RULE_STRATEGY = "composite_top_50pct"
PRIMARY_ML_MODEL = "logreg"
PRIMARY_ML_THRESHOLD = 0.60
PRIMARY_GATE_STRATEGY = "gate_ml_logreg"

# ── Walk-forward windows ──────────────────────────────────────────────
DEFAULT_WINDOWS = (
    (2017, 2021, 2022, 2022),
    (2017, 2022, 2023, 2023),
    (2017, 2023, 2024, 2024),
    (2017, 2024, 2025, 2025),
)

# ── Gate strategy whitelist (Phase 4 must use this) ───────────────────
GATE_STRATEGY_WHITELIST = [
    "gate_rule_panic_intensity",
    "gate_rule_market_stress",
    "gate_rule_breadth",
    "gate_rule_liquidity",
    "gate_rule_composite",
    "gate_ml_logreg",
]

COST_BPS = 20 / 10000
EMBARGO_DAYS = 20
HOLDING_DAYS = 20
MAX_TRANCHES = 20


# ═══════════════════════════════════════════════════════════════════════
# Calendar helpers
# ═══════════════════════════════════════════════════════════════════════
def build_trading_calendar(prices: pd.DataFrame) -> np.ndarray:
    return np.array(sorted(int(d) for d in prices["trade_date"].dropna().unique()))


def load_market_calendar(root: str | Path, start: int, end: int) -> np.ndarray | None:
    """Load the full-market trading calendar from prices_adj parquet files.

    Returns sorted array of all unique trade_date values across all stocks.
    This is the authoritative calendar for embargo computation.
    """
    from pathlib import Path as _Path
    root = _Path(root)
    base = root / "data" / "parquet" / "prices_adj"
    if not base.exists():
        return None

    dates = set()
    sy, ey = start // 10000, end // 10000
    for yr_dir in sorted(base.glob("year=*")):
        try:
            yr = int(yr_dir.name.split("=", 1)[1])
        except ValueError:
            continue
        if sy - 1 <= yr <= ey + 1:
            for pq in sorted(yr_dir.rglob("*.parquet")):
                try:
                    df = pd.read_parquet(pq, columns=["trade_date"])
                    dates.update(int(d) for d in df["trade_date"].dropna().unique())
                except Exception:
                    pass

    if not dates:
        return None
    return np.array(sorted(dates))


def trading_day_offset(calendar: np.ndarray, date: int, offset: int) -> int | None:
    idx = np.searchsorted(calendar, date)
    if idx >= len(calendar) or calendar[idx] != date:
        return None
    target = idx + offset
    if 0 <= target < len(calendar):
        return int(calendar[target])
    return None


def first_trading_day_of_year(calendar: np.ndarray, year: int) -> int | None:
    for d in calendar:
        if d // 10000 == year:
            return int(d)
    return None


def build_exec_date_map(calendar: np.ndarray, lag: int = 1) -> dict:
    return {int(calendar[i]): int(calendar[i + lag])
            for i in range(len(calendar) - lag)}


# ═══════════════════════════════════════════════════════════════════════
# Unified walk-forward split
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class WindowSpec:
    train_start_year: int
    train_end_year: int
    test_start_year: int
    test_end_year: int

    @property
    def name(self) -> str:
        return (f"train_{self.train_start_year}_{self.train_end_year}_"
                f"test_{self.test_start_year}_{self.test_end_year}")


@dataclass
class LeakageAudit:
    window: str = ""
    test_start_trade_date: int = 0
    train_rows_raw: int = 0
    train_rows_after_label_availability: int = 0
    label_unavailable_dropped_rows: int = 0
    label_unavailable_dropped_pct: float = 0.0
    train_rows_after_embargo: int = 0
    embargo_dropped_rows: int = 0
    embargo_dropped_pct: float = 0.0
    max_train_trade_date_after_filter: int | None = None
    max_train_label_available_date_after_filter: int | None = None
    min_test_trade_date: int = 0
    leakage_control_mode: str = "label_available_plus_embargo"
    embargo_days: int = EMBARGO_DAYS
    embargo_cutoff_date: int | None = None
    calendar_source: str = ""
    calendar_n_days: int = 0
    calendar_is_full_market: bool = False

    def to_dict(self) -> dict:
        return self.__dict__


def split_train_test(
    daily_basket: pd.DataFrame,
    window: WindowSpec,
    calendar: np.ndarray,
    leakage_control: str = "label_available_plus_embargo",
    embargo_days: int = EMBARGO_DAYS,
    calendar_source: str = "",
    calendar_is_full_market: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame, LeakageAudit]:
    """Split daily basket into train/test with leakage controls.

    Args:
        daily_basket: daily-level panic basket samples
        window: train/test year specification
        calendar: FULL-MARKET trading calendar for embargo computation.
                  Must be from prices_adj, NOT from daily_basket dates.
        leakage_control: leakage filter mode
        embargo_days: number of MARKET trading days for embargo gap
        calendar_source: label for audit (e.g. "prices_adj_full_market")
        calendar_is_full_market: whether calendar covers all market trading days

    Training set is filtered by:
      1. Year range: [train_start_year, train_end_year]
      2. Label availability: basket_label_available_date < test_start_trade_date
      3. Embargo: trade_date <= test_start_td - embargo_days (market trading days)

    Returns (train_df, test_df, leakage_audit).
    """
    df = daily_basket.copy()
    audit = LeakageAudit(
        window=window.name,
        calendar_source=calendar_source,
        calendar_n_days=len(calendar),
        calendar_is_full_market=calendar_is_full_market,
    )

    test_start_td = first_trading_day_of_year(calendar, window.test_start_year)
    if test_start_td is None:
        return pd.DataFrame(), pd.DataFrame(), audit

    audit.test_start_trade_date = int(test_start_td)

    # Step 0: test set by year
    test = df[
        (df["year"] >= window.test_start_year) &
        (df["year"] <= window.test_end_year)
    ].copy()
    if "trade_date" in test.columns:
        audit.min_test_trade_date = int(test["trade_date"].min()) if len(test) > 0 else 0

    # Step 1: raw train by year
    train_raw = df[
        (df["year"] >= window.train_start_year) &
        (df["year"] <= window.train_end_year)
    ].copy()
    audit.train_rows_raw = len(train_raw)

    # Step 2: label availability filter
    train_after_label = train_raw.copy()
    if leakage_control in ("label_available", "label_available_plus_embargo"):
        label_col = "basket_label_available_date"
        if label_col in train_after_label.columns:
            train_after_label = train_after_label[
                train_after_label[label_col] < test_start_td
            ].copy()
            audit.train_rows_after_label_availability = len(train_after_label)
            audit.label_unavailable_dropped_rows = (
                audit.train_rows_raw - audit.train_rows_after_label_availability)
            audit.label_unavailable_dropped_pct = (
                round(audit.label_unavailable_dropped_rows / audit.train_rows_raw * 100, 3)
                if audit.train_rows_raw else 0.0)
        else:
            audit.train_rows_after_label_availability = len(train_after_label)

    # Step 3: embargo filter (uses FULL MARKET calendar)
    train_after_embargo = train_after_label.copy()
    if leakage_control == "label_available_plus_embargo" and embargo_days > 0:
        embargo_cutoff = trading_day_offset(calendar, test_start_td, -embargo_days)
        audit.embargo_cutoff_date = embargo_cutoff
        if embargo_cutoff is not None:
            train_after_embargo = train_after_label[
                train_after_label["trade_date"] <= embargo_cutoff
            ].copy()
            audit.train_rows_after_embargo = len(train_after_embargo)
            audit.embargo_dropped_rows = (
                audit.train_rows_after_label_availability - audit.train_rows_after_embargo)
            audit.embargo_dropped_pct = (
                round(audit.embargo_dropped_rows / audit.train_rows_raw * 100, 3)
                if audit.train_rows_raw else 0.0)

    train_final = train_after_embargo
    audit.train_rows_after_embargo = len(train_final)
    if len(train_final) > 0 and "trade_date" in train_final.columns:
        audit.max_train_trade_date_after_filter = int(train_final["trade_date"].max())
    if (len(train_final) > 0 and
            "basket_label_available_date" in train_final.columns):
        audit.max_train_label_available_date_after_filter = (
            int(train_final["basket_label_available_date"].max()))

    return train_final, test, audit


def get_windows() -> list[WindowSpec]:
    return [WindowSpec(*w) for w in DEFAULT_WINDOWS]


def validate_leakage_audit(audits: list[dict]) -> tuple[bool, list[str]]:
    """Check all leakage audits pass. Returns (passed, violations)."""
    violations = []
    for a in audits:
        w = a.get("window", "?")
        max_label = a.get("max_train_label_available_date_after_filter")
        min_test = a.get("min_test_trade_date", 0)
        max_train = a.get("max_train_trade_date_after_filter")
        embargo_cutoff = a.get("embargo_cutoff_date")
        cal_source = a.get("calendar_source", "")
        cal_full = a.get("calendar_is_full_market", False)

        if not cal_full:
            violations.append(f"{w}: calendar_is_full_market=False (must use prices_adj)")
        if max_label is not None and min_test and max_label >= min_test:
            violations.append(
                f"{w}: max_train_label_available_date ({max_label}) >= "
                f"min_test_trade_date ({min_test})")
        if max_train is not None and embargo_cutoff is not None and max_train > embargo_cutoff:
            violations.append(
                f"{w}: max_train_trade_date ({max_train}) > "
                f"embargo_cutoff_date ({embargo_cutoff})")

    return len(violations) == 0, violations

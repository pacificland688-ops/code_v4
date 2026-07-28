"""Photoresist Panic Path Rule Evaluator
=========================================
Three-layer analysis for post-panic price path classification and
pre-registered trading rule evaluation.

Layer 1 — Path Parser:      deterministic, day-by-day PIT path decomposition
Layer 2 — Rule Simulator:   PIT-consistent trading rule simulation
Layer 3 — Statistical Reporter: paired-difference statistics

Design principles:
  - Input: online FIRST-trigger events, bull/neutral only, ENTRY_RESOLVED
    frozen basket (Phase 0 formal specification)
  - Path states use basket CLOSE prices only
  - Confirmation at day k close → execution at day k+1 close (never same day)
  - round_trip_cost_bps = total cost for one complete entry+exit (e.g. 100bp = 1%)
  - All four pre-registered rules reported regardless of results
  - Primary cost: 100bp round-trip (Phase 0); 20/50bp as sensitivity
  - Three path classes: SUSTAINED_REPAIR | RETEST_SECONDARY_REPAIR | NO_OR_FAILED_REPAIR
  - Does NOT modify frozen primary_5d gate or live state machine

Trade status taxonomy:
  - COMPLETED:      trade executed and exited normally (20d hold)
  - TRUNCATED_EXIT: trade exited early because next panic event fired
  - PARTIAL:        some legs completed, some open (R3 re-entry censored)
  - NO_TRADE:       valid strategy decision not to trade → return=0
  - STOPPED_OUT:    trade entered but stopped out (all legs closed)
  - RIGHT_CENSORED: insufficient data (NaN gaps only, NOT next-event truncation)
  - UNTRADABLE:     confirmation received but entry not executable
  - REJECTED:       invalid input (missing entry NAV, etc.)

Inputs (from outputs/analysis/photoresist_panic/):
  - photoresist_core_basket_with_gate.csv  (for first-trigger detection)
  - photoresist_universe_snapshot.csv       (for PIT core codes)
  - data/parquet/prices_adj/                (for frozen basket + tradability)
  - data/parquet/index_daily/               (for semiconductor benchmark)

Outputs (to outputs/analysis/photoresist_panic/):
  - photoresist_event_path_ledger.csv
  - photoresist_rule_trade_ledger.csv
  - photoresist_path_rules_report.md
  - photoresist_path_rules_manifest.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import warnings
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from build_photoresist_panic_events import (  # noqa: E402
    build_trading_calendar,
    load_index_prices,
    load_prices,
    load_daily_basic,
    load_limit_status,
    load_suspend_status,
    load_stock_status,
    load_namechange,
    is_suspended,
    trading_day_offset,
)
from live.photoresist_panic.outcome_tracker import resolve_entry as resolve_live_entry  # noqa: E402
from volume_features import compute_volume_features, VolumeFeatures  # noqa: E402
from validation_firewall import (  # noqa: E402
    CandidateRegistry, ValidationFirewall,
    _candidate_identity_hash,
    expanding_window_split, leave_one_year_out_split,
)
from hard_gate_checker import HardGateChecker, HardGateResult  # noqa: E402
from data.tushare_client import FetchManifest  # noqa: E402


def _json_default(obj):
    """JSON default encoder that handles numpy scalars correctly."""
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, (np.ndarray,)):
        return obj.tolist()
    return str(obj)


# ═══════════════════════════════════════════════════════════════════════════
# Constants (PRE-REGISTERED — not optimized on sample)
# ═══════════════════════════════════════════════════════════════════════════
DEFAULT_INPUT_DIR = ROOT / "outputs" / "analysis" / "photoresist_panic"
DEFAULT_OUT_DIR = ROOT / "outputs" / "analysis" / "photoresist_panic"

BOUNCE_START_THRESHOLD = 0.02
BOUNCE_END_DRAWDOWN = 0.03
RETEST_DRAWDOWN_THRESHOLD = -0.03
TARGET_NET_GAIN = 0.05
HOLD_DAYS = 20
OBSERVATION_HORIZON = 60
STOP_LEVELS = [-0.05]  # primary stop: -5% from entry (position-relative)
# Sensitivity: -8% requires a separate run with STOP_LEVELS = [-0.08]
COST_SCENARIOS_BPS = [20, 50, 100]
PRIMARY_COST_BPS = 100
BOOTSTRAP_RUNS = 2000
BOOTSTRAP_CI_LEVEL = 0.95
RANDOM_SEED = 20260710

SCRIPT_VERSION = "2.6.0"  # bugfix batch: NaN-gap, truncation consistency, R3 boundary/reentry/PARTIAL, stop-scan trunc_date, deferral boundary, tradability audit, proxy limit ST, manifest-data mismatch

# Market regime (frozen, matching photoresist_panic_research.yaml §market_regime)
REGIME_MA_WINDOW = 120
REGIME_RETURN_WINDOW = 60
REGIME_PRIMARY_INDEX = "000300.SH"
ELIGIBLE_REGIMES = {"bull", "neutral"}

# Entry resolution (frozen, matching photoresist_panic_live.yaml §outcomes)
MIN_ENTRY_COMPONENTS = 3
MIN_LIST_DAYS = 120
MIN_AMOUNT_20D = 1.0e8  # CNY
MIN_AMOUNT_UNIT = "thousand_cny"

# Event clustering (frozen, matching photoresist_panic_research.yaml)
MAX_CLUSTER_GAP_TRADING_DAYS = 5

# ═══════════════════════════════════════════════════════════════════════════
# Dataclasses
# ═══════════════════════════════════════════════════════════════════════════
@dataclass
class EventRecord:
    """A single first-trigger event with resolved entry basket."""
    signal_id: str
    signal_date: int           # first trigger date (online)
    entry_date: int            # signal_date + 1 trading day
    entry_component_codes: list[str]  # FROZEN ENTRY_RESOLVED components
    n_entry_components: int
    market_regime: str
    entry_status: str          # ENTRY_RESOLVED | NO_TRADABLE_BASKET
    exclusions: list[dict]     # per-stock exclusion reasons
    entry_input_digest: str = ""
    entry_data_version: str = ""


@dataclass
class ExecutionContext:
    """Stock-level inputs needed to validate each simulated basket fill."""
    prices: pd.DataFrame
    component_codes: list[str]
    limit_status: pd.DataFrame | None = None
    suspend_status: pd.DataFrame | None = None
    strict_tradability: bool = False


@dataclass
class PathResult:
    """Deterministic day-by-day path decomposition for one event.

    All path detection uses the FROZEN basket close path.
    Anchors are dimensionless returns relative to entry basket close.
    """
    signal_id: str = ""
    signal_date: int = 0
    entry_date: int = 0
    entry_component_codes: list[str] = None
    n_entry_components: int = 0
    market_regime: str = ""

    # Anchors (dimensionless returns relative to entry basket close)
    signal_basket_return: float = np.nan
    signal_basket_low_return: float = np.nan

    # Path sequence
    first_bounce_date: int | None = None
    first_bounce_high: float | None = None
    first_bounce_high_date: int | None = None
    mae_before_bounce: float | None = None

    post_bounce_drawdown: float | None = None
    retest_low: float | None = None
    retest_low_date: int | None = None
    broke_signal_close: bool = False
    broke_signal_low: bool = False

    reclaim_date: int | None = None
    second_breakout_date: int | None = None

    # Classification
    path_type: str = "NO_OR_FAILED_REPAIR"

    # Diagnostics
    undercut_seen: bool = False
    undercut_reclaimed: bool = False

    # Endpoint outcomes (cost-adjusted at PRIMARY_COST_BPS — one round trip)
    net_return_20d: float | None = None
    net_return_40d: float | None = None
    net_return_60d: float | None = None
    excess_vs_semi_20d: float | None = None
    excess_vs_semi_40d: float | None = None
    excess_vs_semi_60d: float | None = None

    # Timing
    days_to_first_bounce: int | None = None
    days_to_retest: int | None = None
    days_to_second_breakout: int | None = None
    target_5pct_hit_date: int | None = None
    target_5pct_hit: bool = False

    # Volume/turnover diagnostics (Phase A — None when --volume-diagnostics not set)
    volume_features: VolumeFeatures | None = None

    # Data quality
    right_censored: bool = False
    censored_at_day: int | None = None
    insufficient_data: bool = False  # < 20d of data → excluded from classification
    insufficient_reason: str = ""
    truncated_by_next_event: bool = False  # exit at next panic, not RIGHT_CENSORED
    truncated_holding_days: int | None = None
    next_event_signal_date: int | None = None  # for computing correct k+1 exit
    has_post_20d_gap: bool = False  # NaN gaps after day 20 — late-entry rules at risk

    def __post_init__(self):
        if self.entry_component_codes is None:
            self.entry_component_codes = []

    @staticmethod
    def columns() -> list[str]:
        # Exclude volume_features (nested object) from flat CSV output
        return [f.name for f in PathResult.__dataclass_fields__.values()
                if f.name != "volume_features"]


@dataclass
class RuleTrade:
    """Complete trade simulation for one event under one rule."""
    signal_id: str = ""
    rule_id: str = ""
    event_date: int = 0
    entry_date: int = 0
    cost_bps: int = 100
    legs: list[dict] = None
    net_return: float | None = None
    gross_return: float | None = None
    total_cost_ratio: float = 0.0
    n_legs: int = 0
    status: str = "COMPLETED"
    status_reason: str | None = None
    path_type: str = ""
    market_regime: str = ""

    def __post_init__(self):
        if self.legs is None:
            self.legs = []

    @staticmethod
    def columns() -> list[str]:
        return [
            "signal_id", "rule_id", "event_date", "entry_date", "cost_bps",
            "n_legs", "net_return", "gross_return", "total_cost_ratio",
            "status", "status_reason", "path_type", "market_regime",
            "leg_1_type", "leg_1_date", "leg_1_weight", "leg_1_price_ratio", "leg_1_reason",
            "leg_2_type", "leg_2_date", "leg_2_weight", "leg_2_price_ratio", "leg_2_reason",
            "leg_3_type", "leg_3_date", "leg_3_weight", "leg_3_price_ratio", "leg_3_reason",
            "leg_4_type", "leg_4_date", "leg_4_weight", "leg_4_price_ratio", "leg_4_reason",
        ]


# ═══════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Evaluate photoresist panic path rules (v2, first-trigger + frozen basket)"
    )
    p.add_argument("--input-dir", type=str, default=str(DEFAULT_INPUT_DIR))
    p.add_argument("--out-dir", type=str, default=str(DEFAULT_OUT_DIR))
    p.add_argument("--start", type=int, default=20170101)
    p.add_argument("--end", type=int, default=20251231)
    p.add_argument("--cost-scenarios", type=int, nargs="+", default=COST_SCENARIOS_BPS)
    p.add_argument("--primary-cost-bps", type=int, default=PRIMARY_COST_BPS)
    p.add_argument("--observation-horizon", type=int, default=OBSERVATION_HORIZON)
    p.add_argument("--hold-days", type=int, default=HOLD_DAYS)
    p.add_argument("--bootstrap-runs", type=int, default=BOOTSTRAP_RUNS)
    p.add_argument("--bootstrap-ci", type=float, default=BOOTSTRAP_CI_LEVEL)
    p.add_argument("--seed", type=int, default=RANDOM_SEED)
    p.add_argument("--strict-tradability", action="store_true",
                   help="Fail if real limit/suspend/ST data is missing for any event (no proxy judgments)")
    p.add_argument("--upstream-manifest", type=str, default=None,
                   help="Path to upstream photoresist_panic_manifest.json for provenance validation")
    p.add_argument("--volume-diagnostics", action="store_true",
                   help="Compute volume/turnover diagnostic features (Phase A — does not modify R0-R3)")
    return p.parse_args()


def _validate_upstream_manifest(
    manifest_path: Path, strict: bool,
) -> dict:
    """Read and validate the upstream event-builder manifest.

    Returns the parsed manifest dict.  Exits with code 2 if validation fails.
    """
    if not manifest_path.exists():
        print(f"ERROR: upstream manifest not found: {manifest_path}")
        if strict:
            raise SystemExit(2)
        return {}

    upstream = json.loads(manifest_path.read_text(encoding="utf-8"))
    schema = upstream.get("schema", "")
    if "photoresist_panic_events" not in schema:
        print(f"ERROR: upstream manifest has unexpected schema: {schema}")
        if strict:
            raise SystemExit(2)

    # Check for proxy data sources
    sources = upstream.get("data_sources_available", {})
    proxies = []
    for key in ("limit_status", "suspend_status"):
        val = sources.get(key, "")
        if "proxy" in str(val).lower():
            proxies.append(f"{key}={val}")
    if sources.get("stock_status", "") == "unavailable":
        proxies.append("stock_status=unavailable")

    if proxies:
        print(f"WARNING: upstream manifest reports proxy data sources: {proxies}")
        if strict:
            print("ERROR: --strict-tradability refuses proxy data. Re-run event builder with real data.")
            raise SystemExit(2)

    print(f"  Upstream manifest OK (schema={schema}, run_id={upstream.get('run_id', 'N/A')})")
    return upstream


# ═══════════════════════════════════════════════════════════════════════════
# Data Loading
# ═══════════════════════════════════════════════════════════════════════════
def load_inputs(input_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    basket_path = input_dir / "photoresist_core_basket_with_gate.csv"
    universe_path = input_dir / "photoresist_universe_snapshot.csv"
    for p in (basket_path, universe_path):
        if not p.exists():
            raise FileNotFoundError(f"Missing input: {p}")

    basket = pd.read_csv(basket_path)
    basket["trade_date"] = pd.to_numeric(basket["trade_date"], errors="coerce")
    basket = basket.dropna(subset=["trade_date"]).sort_values("trade_date")

    universe = pd.read_csv(universe_path)
    universe["ts_code"] = universe["ts_code"].astype(str)
    return basket, universe


def _count_feature_unavailable(volume_features_list: list) -> dict:
    """Count FEATURE_UNAVAILABLE reasons across events."""
    counts: dict[str, int] = {}
    for vf in volume_features_list:
        for reason in vf.features_unavailable:
            counts[reason] = counts.get(reason, 0) + 1
    return counts


def _dataframe_sha256(frame: pd.DataFrame | None) -> str:
    """Return an order-independent digest of a loaded input frame."""
    digest = hashlib.sha256()
    if frame is None:
        digest.update(b"NONE")
        return digest.hexdigest()
    ordered = frame.reindex(sorted(frame.columns), axis=1).copy()
    schema = [(str(c), str(ordered[c].dtype)) for c in ordered.columns]
    digest.update(json.dumps(schema, ensure_ascii=False).encode("utf-8"))
    digest.update(str(ordered.shape).encode("ascii"))
    if not ordered.empty:
        row_hashes = pd.util.hash_pandas_object(ordered, index=False).to_numpy(
            dtype=np.uint64, copy=True
        )
        row_hashes.sort()
        digest.update(row_hashes.tobytes())
    return digest.hexdigest()


def _entry_resolution_digest(
    prices: pd.DataFrame,
    codes: list[str],
    signal_date: int,
    entry_date: int,
    limit_status: pd.DataFrame | None,
    suspend_status: pd.DataFrame | None,
    stock_status: pd.DataFrame | None,
    namechange: pd.DataFrame | None = None,
) -> str:
    code_set = set(str(c) for c in codes)
    price_slice = prices[
        (prices["ts_code"].astype(str).isin(code_set))
        & (prices["trade_date"].astype(int) <= int(entry_date))
    ]

    def _event_slice(frame: pd.DataFrame | None, date_only: bool) -> pd.DataFrame | None:
        if frame is None or frame.empty:
            return frame
        selected = frame[frame["ts_code"].astype(str).isin(code_set)]
        if date_only and "trade_date" in selected.columns:
            selected = selected[selected["trade_date"].astype(int) == int(entry_date)]
        return selected

    payload = {
        "signal_date": int(signal_date),
        "entry_date": int(entry_date),
        "codes": sorted(code_set),
        "policy": {
            "min_components": MIN_ENTRY_COMPONENTS,
            "min_list_days": MIN_LIST_DAYS,
            "min_daily_amount_20d": MIN_AMOUNT_20D,
            "amount_unit": MIN_AMOUNT_UNIT,
        },
        "prices": _dataframe_sha256(price_slice),
        "limit_status": _dataframe_sha256(_event_slice(limit_status, True)),
        "suspend_status": _dataframe_sha256(_event_slice(suspend_status, True)),
        "stock_status": _dataframe_sha256(_event_slice(stock_status, False)),
        "namechange": _dataframe_sha256(_event_slice(namechange, False)),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


# ═══════════════════════════════════════════════════════════════════════════
# Phase 0 Event Construction: first-trigger + bull/neutral + ENTRY_RESOLVED
# ═══════════════════════════════════════════════════════════════════════════

def detect_first_triggers(
    core_basket: pd.DataFrame,
    calendar: np.ndarray,
    max_gap: int = MAX_CLUSTER_GAP_TRADING_DAYS,
) -> pd.DataFrame:
    """Find ONLINE first-trigger dates from gate triggers.

    Clusters consecutive or nearby trigger days (gap ≤ max_gap trading days).
    For each cluster, the FIRST trigger date is the online first-trigger
    (NOT the last — that requires hindsight).

    Returns DataFrame with columns: first_trigger_date, cluster_id.
    """
    if "panic_gate_triggered" not in core_basket.columns:
        return pd.DataFrame(columns=["first_trigger_date", "cluster_id"])
    raw_trigger = core_basket["panic_gate_triggered"]
    if pd.api.types.is_bool_dtype(raw_trigger):
        trigger_mask = raw_trigger.fillna(False)
    else:
        trigger_mask = raw_trigger.astype(str).str.strip().str.lower().isin(
            {"1", "true", "yes"}
        )
    triggered = core_basket[trigger_mask].copy()
    if triggered.empty:
        return pd.DataFrame(columns=["first_trigger_date", "cluster_id"])

    # Map dates to calendar indices for trading-day gap computation
    cal_idx = {int(d): i for i, d in enumerate(calendar)}
    triggered["cal_idx"] = triggered["trade_date"].map(cal_idx)
    triggered = triggered.dropna(subset=["cal_idx"]).sort_values("trade_date")
    triggered["cal_idx"] = triggered["cal_idx"].astype(int)

    # Cluster: split when gap > max_gap trading days
    gaps = triggered["cal_idx"].diff().fillna(max_gap + 1)
    triggered["cluster_id"] = (gaps > max_gap).cumsum()

    # First trigger per cluster
    first_triggers = triggered.groupby("cluster_id")["trade_date"].first().reset_index()
    first_triggers.columns = ["cluster_id", "first_trigger_date"]
    first_triggers["first_trigger_date"] = first_triggers["first_trigger_date"].astype(int)
    return first_triggers


def compute_market_regime(
    index_prices: pd.DataFrame,
    calendar: np.ndarray,
    ma_window: int = REGIME_MA_WINDOW,
    ret_window: int = REGIME_RETURN_WINDOW,
    primary_code: str = REGIME_PRIMARY_INDEX,
) -> dict[int, str]:
    """Compute bull/neutral/bear regime for each calendar date.

    PIT: uses data only up to (and including) the target date.

    Returns dict: trade_date → regime string.
    """
    primary = index_prices[index_prices["ts_code"] == primary_code].copy()
    if primary.empty:
        return {}

    primary = primary.sort_values("trade_date").drop_duplicates("trade_date")
    primary["ma"] = primary["close"].rolling(ma_window, min_periods=min(60, ma_window)).mean()
    primary["ret"] = primary["close"].pct_change(ret_window)

    regime = {}
    for _, row in primary.iterrows():
        d = int(row["trade_date"])
        if pd.isna(row["ma"]) or pd.isna(row["ret"]):
            regime[d] = "unknown"
        elif row["close"] > row["ma"] and row["ret"] > 0:
            regime[d] = "bull"
        elif row["close"] < row["ma"] and row["ret"] < 0:
            regime[d] = "bear"
        else:
            regime[d] = "neutral"
    return regime


def get_core_codes(universe_df: pd.DataFrame, trade_date: int) -> list[str]:
    """Get PIT core universe codes active on a date."""
    active = universe_df[
        (universe_df["pool_type"] == "core")
        & (universe_df["pit_confidence"] != "low")
        & (universe_df["effective_start"] <= trade_date)
        & (universe_df["effective_end"] >= trade_date)
    ]
    return sorted(active["ts_code"].astype(str).unique().tolist())


def resolve_entry_basket(
    prices: pd.DataFrame,
    core_codes: list[str],
    signal_date: int,
    entry_date: int,
    calendar: np.ndarray,
    limit_status: pd.DataFrame | None = None,
    suspend_status: pd.DataFrame | None = None,
    namechange: pd.DataFrame | None = None,
    stock_status: pd.DataFrame | None = None,
    min_components: int = MIN_ENTRY_COMPONENTS,
) -> tuple[list[str], list[dict], str]:
    """Resolve the tradable entry basket at entry_date.

    The live resolver is the single source of truth for entry-day ST, limit-up,
    price completeness and frozen 20-day liquidity checks.  This wrapper adds
    the research universe's listing-age rule and the audited suspension table.

    Returns (included_codes, exclusions, status).
    status: ENTRY_RESOLVED | NO_TRADABLE_BASKET
    """
    # Normalize suspend date column: tushare_client stores "suspend_date";
    # is_suspended() in build_photoresist_panic_events already handles this,
    # but resolve_entry_basket must also use the correct column.
    _sus_date_col = (
        "trade_date" if suspend_status is not None and "trade_date" in suspend_status.columns
        else "suspend_date"
    )
    audited_suspend_exclusions: list[dict] = []
    resolver_codes: list[str] = []
    for code in sorted(set(str(c) for c in core_codes)):
        has_suspend_record = (
            suspend_status is not None
            and not suspend_status.empty
            and bool(((suspend_status["ts_code"].astype(str) == code)
                      & (suspend_status[_sus_date_col].astype(int) == int(entry_date))).any())
        )
        if has_suspend_record and is_suspended(code, entry_date, suspend_status, prices):
            audited_suspend_exclusions.append(
                {"ts_code": code, "reason": "suspended_entry_day"}
            )
            continue
        resolver_codes.append(code)

    resolution = resolve_live_entry(
        prices=prices,
        calendar=calendar,
        signal={
            "signal_id": f"PANIC_{signal_date}",
            "live_signal_date": int(signal_date),
            "active_member_codes": resolver_codes,
        },
        limit_status=limit_status,
        stock_status=stock_status,
        namechange=namechange,
        min_components=min_components,
        entry_liquidity={
            "enabled": True,
            "source": "frozen_universe_eligibility",
            "window": 20,
            "min_periods": 10,
            "min_daily_amount_20d": MIN_AMOUNT_20D,
            "amount_unit": MIN_AMOUNT_UNIT,
        },
    )

    exclusions = audited_suspend_exclusions + list(resolution.get("exclusions", []))
    resolved_entry_date = resolution.get("entry_date")
    if resolved_entry_date is None or int(resolved_entry_date) != int(entry_date):
        exclusions.append({
            "ts_code": "__BASKET__",
            "reason": "entry_date_resolution_mismatch",
            "expected_entry_date": int(entry_date),
            "resolved_entry_date": resolved_entry_date,
        })
        return [], exclusions, "NO_TRADABLE_BASKET"

    included: list[str] = []
    for code in resolution.get("entry_component_codes", []):
        stock_history = prices[
            (prices["ts_code"].astype(str) == str(code))
            & (prices["trade_date"] <= entry_date)
        ]
        listing_days = int(stock_history["trade_date"].nunique())
        if listing_days < MIN_LIST_DAYS:
            exclusions.append({
                "ts_code": str(code),
                "reason": "min_list_days",
                "listing_days": listing_days,
            })
            continue
        included.append(str(code))

    status = "ENTRY_RESOLVED" if len(included) >= min_components else "NO_TRADABLE_BASKET"
    return sorted(included), exclusions, status


def construct_events(
    core_basket: pd.DataFrame,
    universe_df: pd.DataFrame,
    prices: pd.DataFrame,
    index_prices: pd.DataFrame,
    calendar: np.ndarray,
    start: int,
    end: int,
    limit_status: pd.DataFrame | None = None,
    suspend_status: pd.DataFrame | None = None,
    stock_status: pd.DataFrame | None = None,
    namechange: pd.DataFrame | None = None,
) -> list[EventRecord]:
    """Construct Phase 0 events: first-trigger, bull/neutral, ENTRY_RESOLVED.

    Pipeline:
    1. Detect first-trigger dates from gate triggers
    2. Compute market regime PIT at each trigger date
    3. Filter to bull/neutral
    4. For each surviving trigger: resolve entry basket at T+1
    5. Return list of EventRecord with frozen entry baskets
    """
    # Step 1: First triggers
    first_triggers = detect_first_triggers(core_basket, calendar)
    if first_triggers.empty:
        return []
    first_triggers = first_triggers[
        (first_triggers["first_trigger_date"] >= start)
        & (first_triggers["first_trigger_date"] <= end)
    ]

    # Step 2: Market regime
    regime_map = compute_market_regime(index_prices, calendar)

    # Step 3: Filter bull/neutral + resolve entry
    events = []
    for _, ft in first_triggers.iterrows():
        signal_date = int(ft["first_trigger_date"])
        regime = regime_map.get(signal_date, "unknown")
        if regime not in ELIGIBLE_REGIMES:
            continue

        # Entry date = next trading day
        entry_date = trading_day_offset(calendar, signal_date, 1)
        if entry_date is None:
            continue

        # Get core codes and resolve entry basket
        core_codes = get_core_codes(universe_df, signal_date)
        if len(core_codes) < MIN_ENTRY_COMPONENTS:
            continue

        included, exclusions, entry_status = resolve_entry_basket(
            prices, core_codes, signal_date, entry_date, calendar,
            limit_status=limit_status, suspend_status=suspend_status,
            stock_status=stock_status, namechange=namechange,
        )

        if entry_status != "ENTRY_RESOLVED":
            continue

        signal_id = f"PANIC_{signal_date}"
        # Disambiguate duplicate dates
        dup_count = sum(1 for e in events if e.signal_date == signal_date)
        if dup_count > 0:
            signal_id = f"PANIC_{signal_date}_{dup_count + 1}"

        events.append(EventRecord(
            signal_id=signal_id,
            signal_date=signal_date,
            entry_date=entry_date,
            entry_component_codes=included,
            n_entry_components=len(included),
            market_regime=regime,
            entry_status=entry_status,
            exclusions=exclusions,
            entry_input_digest=_entry_resolution_digest(
                prices, core_codes, signal_date, entry_date,
                limit_status, suspend_status, stock_status, namechange,
            ),
            entry_data_version=(
                f"prices_max_trade_date={int(prices['trade_date'].max())}"
                if not prices.empty else "prices_empty"
            ),
        ))

    return events


# ═══════════════════════════════════════════════════════════════════════════
# Frozen Basket NAV
# ═══════════════════════════════════════════════════════════════════════════

def build_frozen_basket_path(
    prices: pd.DataFrame,
    entry_component_codes: list[str],
    signal_date: int,
    entry_date: int,
    calendar: np.ndarray,
    horizon: int,
    suspend_status: pd.DataFrame | None = None,
) -> tuple[np.ndarray, np.ndarray] | None:
    """Build FROZEN equal-weight basket return path.

    Basket composition is FROZEN at entry_date. Missing data is handled:
    - Suspended stocks: carry last valid close forward (audited suspension)
    - Unexplained missing: that day's basket return is NaN (data gap)

    Returns (rets, dates) where rets[i] = basket_close[i] / basket_close[0] - 1,
    and dates[i] is the calendar date. rets[0] = 0 at entry_date.
    Returns None if entry_date not in calendar or fewer than 3 stocks have data.
    """
    idx = np.searchsorted(calendar, entry_date)
    if idx >= len(calendar) or calendar[idx] != entry_date:
        return None
    end_idx = min(idx + horizon + 1, len(calendar))
    grid_dates = calendar[idx:end_idx]

    if len(entry_component_codes) < 3:
        return None

    # Build suspended-keys set for audited suspension carry
    suspended_keys: set[tuple[str, int]] = set()
    if suspend_status is not None and not suspend_status.empty:
        # Normalize column name: cache may store "suspend_date", loader renames
        # to "trade_date"; handle both for robustness.
        date_col = (
            "trade_date" if "trade_date" in suspend_status.columns
            else "suspend_date" if "suspend_date" in suspend_status.columns
            else None
        )
        if date_col is not None:
            suspended_keys = set(zip(
                suspend_status["ts_code"].astype(str),
                suspend_status[date_col].astype(int),
            ))

    stock_paths = []
    for code in entry_component_codes:
        stock = prices[
            (prices["ts_code"] == code) & (prices["trade_date"].isin(grid_dates))
        ].set_index("trade_date").sort_index()

        if entry_date not in stock.index:
            return None  # ENTRY_RESOLVED invariant: denominator must never shrink

        entry_close = float(stock.at[entry_date, "adj_close"])
        if np.isnan(entry_close) or entry_close <= 0:
            return None

        closes = np.full(len(grid_dates), np.nan)
        has_data = np.zeros(len(grid_dates), dtype=bool)
        for j, d in enumerate(grid_dates):
            if d in stock.index:
                c = float(stock.at[d, "adj_close"])
                if not np.isnan(c) and c > 0:
                    closes[j] = c
                    has_data[j] = True

        # Carry suspended stocks forward (audited suspension only)
        for j in range(1, len(grid_dates)):
            if not has_data[j]:
                is_suspended = (str(code), int(grid_dates[j])) in suspended_keys
                if is_suspended and j > 0 and not np.isnan(closes[j - 1]):
                    closes[j] = closes[j - 1]  # carry last valid close

        stock_paths.append(closes / entry_close - 1.0)

    if len(stock_paths) != len(entry_component_codes):
        return None

    stacked = np.array(stock_paths)
    # Ordinary mean deliberately propagates any unexplained component gap.
    # np.nanmean would silently change the frozen denominator and weights.
    basket_rets = np.mean(stacked, axis=0)
    return basket_rets, grid_dates


def compute_signal_anchors(
    prices: pd.DataFrame,
    entry_component_codes: list[str],
    signal_date: int,
    entry_date: int,
) -> tuple[float, float]:
    """Compute dimensionless signal-day anchors for frozen basket components.

    Returns (signal_basket_return, signal_basket_low_return).
    Both are equal-weight averages across ENTRY_RESOLVED components.
    """
    close_rets = []
    low_rets = []
    for code in entry_component_codes:
        stock = prices[prices["ts_code"] == code]

        # Entry close
        entry_rows = stock[stock["trade_date"] == entry_date]
        if entry_rows.empty:
            continue
        entry_close = float(entry_rows.iloc[0]["adj_close"])
        if np.isnan(entry_close) or entry_close <= 0:
            continue

        # Signal close
        sig_rows = stock[stock["trade_date"] == signal_date]
        if not sig_rows.empty:
            sig_close = float(sig_rows.iloc[0].get("adj_close", np.nan))
            if not np.isnan(sig_close) and sig_close > 0:
                close_rets.append(sig_close / entry_close - 1.0)

        # Signal low.  Never mix raw low with an adjusted entry close and never
        # substitute the close: an unavailable low remains an unavailable
        # diagnostic anchor.
        sig_low = float(sig_rows.iloc[0].get("adj_low", np.nan)) if not sig_rows.empty else np.nan
        if not np.isnan(sig_low) and sig_low > 0:
            low_rets.append(sig_low / entry_close - 1.0)

    expected = len(entry_component_codes)
    signal_close_ret = float(np.mean(close_rets)) if len(close_rets) == expected else np.nan
    signal_low_ret = float(np.mean(low_rets)) if len(low_rets) == expected else np.nan
    return signal_close_ret, signal_low_ret


def build_semi_nav_map(
    path_dates: np.ndarray,
    index_prices: pd.DataFrame,
) -> dict[int, float]:
    """Build semiconductor NAV lookup.

    NAV[t] = cumulative product of daily returns up to day t.
    The NAV at day t reflects the close of day t.
    """
    semi = index_prices[index_prices["ts_code"] == "931865.CSI"].copy()
    if semi.empty or "close" not in semi.columns:
        return {}

    # Get full history to compute cumulative NAV correctly
    semi = semi.sort_values("trade_date")
    semi["ret_1d"] = semi["close"].pct_change()
    semi["nav"] = (1.0 + semi["ret_1d"].fillna(0.0)).cumprod()

    result = {}
    for _, row in semi.iterrows():
        d = int(row["trade_date"])
        if d in path_dates:
            result[d] = float(row["nav"])
    return result


# ═══════════════════════════════════════════════════════════════════════════
# Layer 1: Path Parser (day-by-day, PIT-consistent)
# ═══════════════════════════════════════════════════════════════════════════

PHASE_PRE_BOUNCE = 0
PHASE_BOUNCING = 1
PHASE_RETESTING = 2


def parse_event_path(
    basket_rets: np.ndarray,
    path_dates: np.ndarray,
    semi_nav_map: dict[int, float],
    signal_date: int,
    entry_date: int,
    signal_basket_return: float,
    signal_basket_low_return: float,
    next_event_date: int | None = None,
    observation_horizon: int = 60,
    target_gain: float = 0.05,
    cost_bps: int = 100,
) -> PathResult:
    """Parse post-panic price path with day-by-day PIT-consistent scanning.

    State machine: PRE_BOUNCE → BOUNCING → RETESTING
    - PRE_BOUNCE: bounce starts when ret rises ≥ BOUNCE_START_THRESHOLD above running min
    - BOUNCING: FREEZE first_bounce_high when ret drops ≥ BOUNCE_END_DRAWDOWN from running max
    - RETESTING: track retest low, signal breaks, reclaim, second breakout

    Right-censored events: data gaps (NaN) → insufficient_data=True, excluded.
    Next-event truncation → truncated_by_next_event=True, still classified and
    tradable (simulated early exit at the next panic signal date).
    """
    result = PathResult(
        signal_id="",
        signal_date=signal_date,
        entry_date=entry_date,
        signal_basket_return=signal_basket_return,
        signal_basket_low_return=signal_basket_low_return,
    )

    if basket_rets is None or len(basket_rets) <= 1:
        result.insufficient_data = True
        result.right_censored = True
        result.insufficient_reason = "right_censored_before_20d_endpoint"
        result.path_type = "RIGHT_CENSORED"
        return result

    # Truncate at next event date
    trunc_idx = len(basket_rets)
    if next_event_date is not None:
        nxt = np.searchsorted(path_dates, next_event_date)
        if nxt < trunc_idx:
            trunc_idx = nxt
            result.censored_at_day = trunc_idx

    rets = basket_rets[:trunc_idx].copy()
    dates = path_dates[:trunc_idx]
    n_days = len(rets)

    # ── Check data sufficiency BEFORE classification ────────────────────
    # Unexplained gaps (NaN) within the minimum required horizon (20 days)
    # → truly censored, cannot evaluate even the shortest-hold rules.
    # NaN gaps AFTER day 20 do NOT censor 20-day trades — those settle normally.
    # Next-event truncation → tradable early exit at the next panic signal.
    min_required = min(20, len(rets))
    has_gap_in_min_horizon = bool(np.isnan(rets[:min_required]).any())
    has_unexplained_gap = bool(np.isnan(rets).any())
    result.has_post_20d_gap = has_unexplained_gap and not has_gap_in_min_horizon
    is_next_event_truncation = (
        result.censored_at_day is not None and not has_gap_in_min_horizon
    )
    has_20d_endpoint = len(rets) > 20

    if has_gap_in_min_horizon:
        result.insufficient_data = True
        result.right_censored = True
        result.insufficient_reason = "unexplained_gap_in_first_20d"
        result.path_type = "RIGHT_CENSORED"
        _fill_endpoint_metrics_available(
            result, rets, dates, semi_nav_map, cost_bps, target_gain
        )
        return result

    if not has_20d_endpoint and not is_next_event_truncation:
        # True end-of-data — no next event to blame, just ran out of history
        result.insufficient_data = True
        result.right_censored = True
        result.insufficient_reason = "right_censored_before_20d_endpoint"
        result.path_type = "RIGHT_CENSORED"
        _fill_endpoint_metrics_available(
            result, rets, dates, semi_nav_map, cost_bps, target_gain
        )
        return result

    # ── Next-event truncated paths: mark for early exit, continue analysis ──
    if is_next_event_truncation:
        result.truncated_by_next_event = True
        # rets[:trunc_idx] excludes next_event_date itself.  The actual exit
        # is at trunc_date = k+1 of next_event_date, which is one trading day
        # beyond the slice boundary.
        result.truncated_holding_days = len(rets) + 1
        result.next_event_signal_date = next_event_date

    # ── Day-by-day state scanning ───────────────────────────────────────
    # Only scan the first `observation_horizon` trading days for path signals.
    # Second breakout / reclaim MUST occur within this window to qualify.
    scan_days = min(n_days, observation_horizon)
    phase = PHASE_PRE_BOUNCE
    post_entry_min = 0.0
    running_max_since_bounce = -999.0
    running_max_idx = -1
    first_bounce_high_frozen = None
    first_bounce_high_date_frozen = None
    retest_low_val = 999.0
    retest_low_idx = -1
    broke_signal_close_seen = False
    broke_signal_low_seen = False
    reclaim_date_val = None
    second_breakout_date_val = None

    for i in range(1, scan_days):
        r = rets[i]
        if np.isnan(r):
            continue

        if r < post_entry_min:
            post_entry_min = r

        if phase == PHASE_PRE_BOUNCE:
            if r - post_entry_min >= BOUNCE_START_THRESHOLD:
                phase = PHASE_BOUNCING
                running_max_since_bounce = r
                running_max_idx = i
                result.days_to_first_bounce = i
                result.first_bounce_date = int(dates[i])
                result.mae_before_bounce = float(post_entry_min)

        elif phase == PHASE_BOUNCING:
            if r > running_max_since_bounce:
                running_max_since_bounce = r
                running_max_idx = i

            drawdown_from_max = (1.0 + r) / (1.0 + running_max_since_bounce) - 1.0
            if drawdown_from_max <= -BOUNCE_END_DRAWDOWN:
                first_bounce_high_frozen = float(running_max_since_bounce)
                first_bounce_high_date_frozen = int(dates[running_max_idx])
                result.first_bounce_high = first_bounce_high_frozen
                result.first_bounce_high_date = first_bounce_high_date_frozen
                phase = PHASE_RETESTING
                retest_low_val = r
                retest_low_idx = i

                if not np.isnan(signal_basket_return) and r < signal_basket_return:
                    broke_signal_close_seen = True
                if not np.isnan(signal_basket_low_return) and r < signal_basket_low_return:
                    broke_signal_low_seen = True

        elif phase == PHASE_RETESTING:
            if r < retest_low_val:
                retest_low_val = r
                retest_low_idx = i

            if not broke_signal_close_seen and not np.isnan(signal_basket_return) and r < signal_basket_return:
                broke_signal_close_seen = True
            if not broke_signal_low_seen and not np.isnan(signal_basket_low_return) and r < signal_basket_low_return:
                broke_signal_low_seen = True

            if broke_signal_low_seen and reclaim_date_val is None:
                if not np.isnan(signal_basket_low_return) and r > signal_basket_low_return:
                    reclaim_date_val = int(dates[i])

            if first_bounce_high_frozen is not None and second_breakout_date_val is None:
                if r > first_bounce_high_frozen:
                    second_breakout_date_val = int(dates[i])

    # ── Post-scan: freeze if still bouncing ─────────────────────────────
    if phase == PHASE_BOUNCING and running_max_idx >= 0:
        first_bounce_high_frozen = float(running_max_since_bounce)
        first_bounce_high_date_frozen = int(dates[running_max_idx])
        result.first_bounce_high = first_bounce_high_frozen
        result.first_bounce_high_date = first_bounce_high_date_frozen
        phase = PHASE_RETESTING
        if n_days > 1:
            retest_low_val = rets[-1]
            retest_low_idx = n_days - 1

    # ── Fill path fields ─────────────────────────────────────────────────
    result.broke_signal_close = broke_signal_close_seen
    result.broke_signal_low = broke_signal_low_seen
    result.undercut_seen = broke_signal_low_seen

    if phase == PHASE_RETESTING and retest_low_idx >= 0 and retest_low_val < 999.0:
        result.retest_low = float(retest_low_val)
        result.retest_low_date = int(dates[retest_low_idx])
        result.days_to_retest = retest_low_idx
        if first_bounce_high_frozen is not None:
            fb_price = 1.0 + first_bounce_high_frozen
            rl_price = 1.0 + retest_low_val
            if fb_price > 0:
                result.post_bounce_drawdown = float(rl_price / fb_price - 1.0)

    if reclaim_date_val is not None:
        result.reclaim_date = reclaim_date_val
        result.undercut_reclaimed = True

    if second_breakout_date_val is not None:
        result.second_breakout_date = second_breakout_date_val
        result.days_to_second_breakout = int(np.searchsorted(dates, second_breakout_date_val))

    # ── Fill endpoint metrics FIRST, then classify ──────────────────────
    _fill_endpoint_metrics(result, rets, dates, semi_nav_map, cost_bps, target_gain)
    result.path_type = _classify_path_type(result, target_gain)
    result.right_censored = False

    return result


def _classify_path_type(path: PathResult, target_gain: float = 0.05) -> str:
    """Classify path by observable price-pattern shape (PRE-TRADE).

    These labels describe what the price path DID before any exit decision.
    They are diagnostic descriptors, NOT trading signals.
    The economic outcome is stored separately as net_return_20d.
    """
    if path.insufficient_data:
        return "RIGHT_CENSORED"

    if path.first_bounce_date is None:
        return "NO_BOUNCE"

    had_significant_retest = (
        path.post_bounce_drawdown is not None
        and path.post_bounce_drawdown <= RETEST_DRAWDOWN_THRESHOLD
    )
    recovered = path.second_breakout_date is not None

    if had_significant_retest and recovered:
        return "W_RECOVERY"
    elif had_significant_retest and not recovered:
        return "BOUNCE_THEN_FAIL"
    else:
        return "BOUNCE_NO_RETEST"


def _fill_endpoint_metrics_available(
    result: PathResult,
    rets: np.ndarray,
    dates: np.ndarray,
    semi_nav_map: dict[int, float],
    cost_bps: int,
    target_gain: float = TARGET_NET_GAIN,
) -> None:
    """Fill whatever endpoint metrics are available (for insufficient-data events)."""
    _fill_endpoint_metrics(result, rets, dates, semi_nav_map, cost_bps, target_gain)


def _fill_endpoint_metrics(
    result: PathResult,
    rets: np.ndarray,
    dates: np.ndarray,
    semi_nav_map: dict[int, float],
    cost_bps: int,
    target_gain: float = TARGET_NET_GAIN,
) -> None:
    """Fill net_return_*d and excess_vs_semi_*d fields.

    round_trip_cost_bps = total cost for one complete entry+exit.
    Net return = gross_return - cost_bps/10000.
    """
    cost = cost_bps / 10000.0  # one round trip
    entry_date = result.entry_date
    semi_entry_nav = semi_nav_map.get(entry_date)

    # Window-hit and endpoint-success are distinct.  Record the first known
    # close-basis hit even if the basket subsequently fades before day 20.
    for i in range(1, min(20, len(rets) - 1) + 1):
        if not np.isnan(rets[i]) and rets[i] - cost >= target_gain:
            result.target_5pct_hit = True
            result.target_5pct_hit_date = int(dates[i])
            break

    for horizon, req_days in [("20d", 20), ("40d", 40), ("60d", 60)]:
        if req_days < len(rets) and not np.isnan(rets[req_days]):
            gross = float(rets[req_days])
            net = gross - cost
            setattr(result, f"net_return_{horizon}", net)

            # Excess vs semiconductor
            exit_date = int(dates[req_days])
            semi_exit_nav = semi_nav_map.get(exit_date)
            if semi_entry_nav is not None and semi_exit_nav is not None and semi_entry_nav > 0:
                semi_ret = semi_exit_nav / semi_entry_nav - 1.0
                # net excess = (gross - cost) - semi_ret
                setattr(result, f"excess_vs_semi_{horizon}", net - semi_ret)


def _is_right_censored(all_dates: np.ndarray, entry_date: int, min_days: int) -> bool:
    idx = np.searchsorted(all_dates, entry_date)
    return idx + min_days >= len(all_dates)


# ═══════════════════════════════════════════════════════════════════════════
# Layer 2: Rule Simulator
# ═══════════════════════════════════════════════════════════════════════════

def _nav_at_path(rets: np.ndarray, dates: np.ndarray, target_date: int) -> tuple[float | None, int]:
    """Get basket return at a date within the path slice."""
    idx = np.searchsorted(dates, target_date)
    if idx < len(dates) and dates[idx] == target_date and not np.isnan(rets[idx]):
        return float(rets[idx]), idx
    return None, -1


def _check_basket_execution(
    context: ExecutionContext | None,
    trade_date: int,
    side: str,
) -> tuple[bool, str]:
    """Validate a whole-basket close fill at stock level.

    ``side`` is ``buy`` or ``sell``.  A synthetic context of ``None`` is used
    by pure rule-unit tests; production always passes the frozen stock basket.
    """
    if context is None:
        return True, ""
    if side not in {"buy", "sell"}:
        raise ValueError(f"Unsupported execution side: {side}")

    prices = context.prices
    for code in context.component_codes:
        rows = prices[
            (prices["ts_code"].astype(str) == str(code))
            & (prices["trade_date"].astype(int) == int(trade_date))
        ]
        if rows.empty:
            return False, f"{code}:no_fill_data"
        stock = rows.iloc[-1]
        adj_close = float(stock.get("adj_close", np.nan))
        if not np.isfinite(adj_close) or adj_close <= 0:
            return False, f"{code}:bad_fill_price"
        if is_suspended(
            str(code), int(trade_date), context.suspend_status, prices
        ):
            return False, f"{code}:suspended"

        limit_side = "up" if side == "buy" else "down"
        exact_limit_available = False
        if context.limit_status is not None and not context.limit_status.empty:
            lim = context.limit_status[
                (context.limit_status["ts_code"].astype(str) == str(code))
                & (context.limit_status["trade_date"].astype(int) == int(trade_date))
            ]
            limit_col = f"{limit_side}_limit"
            if not lim.empty and limit_col in lim.columns:
                limit_price = float(lim[limit_col].iloc[-1])
                close = float(stock.get("close", np.nan))
                if np.isfinite(limit_price) and limit_price > 0 and np.isfinite(close):
                    exact_limit_available = True
                    if abs(close - limit_price) < 0.005:
                        return False, f"{code}:limit_{limit_side}"

        if not exact_limit_available:
            if context.strict_tradability:
                raise RuntimeError(
                    "Strict tradability coverage invariant failed: missing exact "
                    f"limit_status for {code} on {trade_date}."
                )
            pct = float(stock.get("pct_chg", np.nan))
            stock_name = str(stock.get("name", "")) if "name" in stock.index else None
            limit_pct = _proxy_limit_pct(str(code), int(trade_date), stock_name=stock_name)
            if side == "buy" and np.isfinite(pct) and pct >= limit_pct * 0.975:
                return False, f"{code}:limit_up_proxy"
            if side == "sell" and np.isfinite(pct) and pct <= -limit_pct * 0.975:
                return False, f"{code}:limit_down_proxy"

    return True, ""


def _proxy_limit_pct(code: str, trade_date: int,
                     stock_name: str | None = None) -> float:
    """Best-effort daily limit percentage when real stk_limit data is unavailable.

    Known regimes (IPO first-day no-limit & suspension-based rules not covered):
      - 北交所 (8xxxxx):          30% since 2023-02-20 (was 30% at launch 2021-11-15)
      - 科创板 (688xxx):          20% since inception (2019-07-22)
      - 创业板 (300xxx):          20% since 2020-08-24, 10% before
      - ST/*ST (any board):       5%
      - Main board (other):       10%

    This is a FALLBACK proxy only used when real limit_status data is missing.
    In strict mode (--strict-tradability), proxy is never invoked because
    evaluation aborts when real data is unavailable.
    """
    # ST/*ST check FIRST — overrides board-specific limits for all boards
    if stock_name and ("ST" in stock_name.upper()):
        return 5.0
    # BSE / 北交所: 30% limit
    if code.startswith("8"):
        return 30.0
    # STAR / 科创板: 20% since inception
    if code.startswith("688"):
        return 20.0
    # ChiNext / 创业板: 20% since 2020-08-24, 10% before
    if code.startswith("300"):
        return 20.0 if trade_date >= 20200824 else 10.0
    # Default: main board 10%
    return 10.0


def _try_exit_or_defer(
    exit_date: int,
    context: ExecutionContext | None,
    calendar: np.ndarray,
    trunc_date: int | None = None,
    max_defer_days: int = 3,
) -> tuple[int | None, str | None]:
    """Check exit executability, deferring if blocked by limit/suspension.

    Returns (exit_date | None, failure_reason | None).
    If exit_date is not None, the caller should proceed with that date.
    If exit_date is None, failure_reason explains why — the caller should
    mark the trade UNTRADABLE / RIGHT_CENSORED as appropriate.
    """
    # Never attempt to exit past the next-event boundary
    if trunc_date is not None and exit_date > trunc_date:
        return None, f"exit_untradable:exit_past_trunc_date"

    executable, reason = _check_basket_execution(context, exit_date, "sell")
    if executable:
        return exit_date, None  # exit works at original date

    # Exit blocked — try deferring
    if context is None:
        return None, f"exit_untradable:{reason}"
    idx = np.searchsorted(calendar, exit_date)
    if idx >= len(calendar):
        return None, f"exit_untradable:{reason}_beyond_calendar"

    for offset in range(1, max_defer_days + 1):
        defer_idx = idx + offset
        if defer_idx >= len(calendar):
            break
        candidate = int(calendar[defer_idx])
        # Never defer past the next-event boundary
        if trunc_date is not None and candidate > trunc_date:
            break
        ok, r = _check_basket_execution(context, candidate, "sell")
        if ok:
            return candidate, f"deferred_{offset}d_from_{reason}"

    # Deferral exhausted: mark-to-market at last available price instead of
    # excluding from statistics (avoids systematically dropping worst trades).
    last_idx = min(idx + max_defer_days, len(calendar) - 1)
    if trunc_date is not None:
        trunc_idx = np.searchsorted(calendar, trunc_date)
        last_idx = min(last_idx, trunc_idx)
    if last_idx >= idx:
        fallback_date = int(calendar[last_idx])
        return fallback_date, f"mtm_at_{reason}_deferred_max_d"
    return None, f"exit_untradable:{reason}_deferred_exhausted"


def _round_trip_cost(weight: float, cost_bps: int) -> float:
    """Total round-trip cost for a position leg.

    round_trip_cost_bps = cost of one complete entry+exit.
    Scaled by position weight.
    """
    return weight * cost_bps / 10000.0


def _holding_has_gap(
    rets: np.ndarray, dates: np.ndarray,
    entry_date: int, exit_date: int,
) -> bool:
    """Check if the holding period [entry_date, exit_date] contains any NaN gap."""
    entry_idx = np.searchsorted(dates, entry_date)
    exit_idx = np.searchsorted(dates, exit_date)
    if entry_idx >= len(dates) or exit_idx >= len(dates):
        return True
    if entry_idx > exit_idx:
        return True
    return bool(np.isnan(rets[entry_idx:exit_idx + 1]).any())


def _position_return(event_ret: float, entry_event_ret: float) -> float:
    """Convert event-level return to position-level return.

    event_ret: basket return relative to original event entry
    entry_event_ret: basket return at the rule's actual entry point
    """
    return (1.0 + event_ret) / (1.0 + entry_event_ret) - 1.0


def _stop_scan_position(
    rets: np.ndarray,
    dates: np.ndarray,
    calendar: np.ndarray,
    entry_date: int,
    entry_event_ret: float,
    hold_days: int,
    stop_levels: list[float],
    trunc_date: int | None = None,
) -> tuple[bool, int | None, float | None]:
    """Scan for stop using POSITION returns, execute at day k+1.

    Stop is confirmed when position_return at day k close <= stop_level.
    Exit price = day k+1 close (never same day).

    Returns (stopped, exit_date, stop_level_hit).
    exit_date = day k+1 (the actual exit execution date).
    """
    for offset in range(1, hold_days):  # exclude hold_days: day-20 stop → day-21 exit is past horizon
        check_date_k = trading_day_offset(calendar, entry_date, offset)
        if check_date_k is None:
            break
        if trunc_date is not None and check_date_k >= trunc_date:
            # Stop confirmed at trunc_date itself would need k+1 execution
            # past the boundary → never executable.  Fall through to normal
            # boundary exit instead of same-day confirm+execute.
            break

        check_ret, _ = _nav_at_path(rets, dates, check_date_k)
        if check_ret is None:
            continue
        pos_ret = _position_return(check_ret, entry_event_ret)

        for level in stop_levels:
            if pos_ret <= level:
                # Execute at day k+1
                exit_date_k1 = trading_day_offset(calendar, entry_date, offset + 1)
                if exit_date_k1 is None:
                    return True, None, level
                if trunc_date is not None and exit_date_k1 > trunc_date:
                    # k+1 beyond boundary → cannot execute (violates k-confirm, k+1-execute)
                    return True, None, level
                return True, exit_date_k1, level

    return False, None, None


def simulate_rule_r0(
    signal_id: str, event_date: int, entry_date: int,
    rets: np.ndarray, dates: np.ndarray, calendar: np.ndarray,
    cost_bps: int = 100, hold_days: int = 20,
    stop_levels: list[float] | None = None,
    trunc_date: int | None = None,
    execution_context: ExecutionContext | None = None,
    path_result: PathResult | None = None,
) -> RuleTrade:
    """R0: Immediate entry at T+1 close. One round-trip cost = cost_bps."""
    if stop_levels is None:
        stop_levels = STOP_LEVELS

    trade = RuleTrade(
        signal_id=signal_id, rule_id="R0", event_date=event_date,
        entry_date=entry_date, cost_bps=cost_bps,
    )

    if path_result is not None and path_result.insufficient_data:
        # Only genuine data gaps (NaN) are RIGHT_CENSORED.
        # Next-event truncation is handled as TRUNCATED_EXIT below.
        trade.status = "RIGHT_CENSORED"
        trade.status_reason = (
            path_result.insufficient_reason or "path_insufficient_data"
        )
        return trade

    # Detect truncated-by-next-event mode
    is_truncated = (
        path_result is not None and path_result.truncated_by_next_event
    )

    entry_ret, _ = _nav_at_path(rets, dates, entry_date)
    if entry_ret is None:
        trade.status = "REJECTED"; trade.status_reason = "no_entry_data"; return trade
    executable, reason = _check_basket_execution(execution_context, entry_date, "buy")
    if not executable:
        # No position established → strategy P&L = 0
        trade.status = "NO_TRADE"; trade.status_reason = f"entry_untradable:{reason}"
        trade.net_return = 0.0; trade.gross_return = 0.0; return trade

    # Entry leg (no cost on entry leg alone — cost is per round trip)
    entry_leg = {
        "leg_type": "entry", "date": entry_date,
        "fill_price_ratio": 1.0 + entry_ret, "weight": 1.0,
        "reason": "initial_entry",
    }

    # Stop scan (position-relative, k→k+1 execution)
    stopped, stop_exit_date, stop_level = _stop_scan_position(
        rets, dates, calendar, entry_date, entry_ret,
        hold_days, stop_levels, trunc_date,
    )

    # Stop confirmed at k but k+1 > trunc_date → cannot execute the stop.
    # Fall through to boundary exit instead of right-censoring.
    stop_blocked_by_boundary = stopped and stop_exit_date is None

    if stopped and not stop_blocked_by_boundary:
        stop_exit_date, defer_reason = _try_exit_or_defer(
            stop_exit_date, execution_context, calendar, trunc_date,
        )
        if stop_exit_date is None:
            trade.status = "UNTRADABLE"
            trade.status_reason = f"stop_exit_deferred_failed:{defer_reason}"
            trade.legs = [entry_leg]; trade.n_legs = 1
            return trade
        stop_ret, _ = _nav_at_path(rets, dates, stop_exit_date)
        if stop_ret is None:
            trade.status = "RIGHT_CENSORED"
            trade.status_reason = "no_stop_exit_data"
            trade.legs = [entry_leg]; trade.n_legs = 1
            return trade
        pos_ret = _position_return(stop_ret, entry_ret)
        exit_leg = {
            "leg_type": "exit", "date": stop_exit_date,
            "fill_price_ratio": 1.0 + stop_ret, "weight": 1.0,
            "reason": f"stop_loss_{stop_level}",
        }
        trade.status = "STOPPED_OUT"
        trade.status_reason = f"stop_at_{stop_level}"
        gross = float(pos_ret)
    else:
        # Either (a) no stop, or (b) stop confirmed but k+1 past boundary.
        # Case (b): exit at the boundary (consistent with 20d capping).
        if stop_blocked_by_boundary:
            exit_date = trunc_date
            exit_reason = "next_event_exit"
        else:
            exit_date = trading_day_offset(calendar, entry_date, hold_days)
            exit_reason = "hold_20d"
            if trunc_date is not None and exit_date is not None and exit_date > trunc_date:
                exit_date = trunc_date
                exit_reason = "next_event_exit"
        if exit_date is None:
            trade.status = "RIGHT_CENSORED"; trade.status_reason = "exit_beyond_data"
            trade.legs = [entry_leg]; trade.n_legs = 1; return trade
        exit_date, defer_reason = _try_exit_or_defer(
            exit_date, execution_context, calendar, trunc_date,
        )
        if exit_date is None:
            trade.status = "UNTRADABLE"; trade.status_reason = f"exit_deferred_failed:{defer_reason}"
            trade.legs = [entry_leg]; trade.n_legs = 1; return trade
        exit_ret, _ = _nav_at_path(rets, dates, exit_date)
        if exit_ret is None:
            trade.status = "RIGHT_CENSORED"; trade.status_reason = "no_exit_data"
            trade.legs = [entry_leg]; trade.n_legs = 1; return trade
        exit_leg = {
            "leg_type": "exit", "date": exit_date,
            "fill_price_ratio": 1.0 + exit_ret, "weight": 1.0,
            "reason": exit_reason,
        }
        gross = _position_return(exit_ret, entry_ret)

    cost_ratio = _round_trip_cost(1.0, cost_bps)
    trade.legs = [entry_leg, exit_leg]
    trade.n_legs = 2
    trade.total_cost_ratio = cost_ratio  # one round trip
    trade.gross_return = float(gross) if not np.isnan(gross) else None
    trade.net_return = float(gross - cost_ratio) if trade.gross_return is not None else None
    if (is_truncated or stop_blocked_by_boundary) and trade.status == "COMPLETED" and exit_leg.get("reason", "") == "next_event_exit":
        trade.status = "TRUNCATED_EXIT"
        trade.status_reason = (
            f"truncated_at_day_{path_result.truncated_holding_days}"
            if path_result and path_result.truncated_holding_days
            else "truncated_by_next_event"
        )
    # Else: 20d exit was before next_event → normal COMPLETED
    return trade


def simulate_rule_r1(
    signal_id: str, event_date: int, entry_date_original: int,
    path: PathResult,
    rets: np.ndarray, dates: np.ndarray, calendar: np.ndarray,
    cost_bps: int = 100, hold_days: int = 20,
    stop_levels: list[float] | None = None,
    trunc_date: int | None = None,
    execution_context: ExecutionContext | None = None,
) -> RuleTrade:
    """R1: Wait for second breakout, enter at confirmation+1.

    NO_TRADE (return=0) if no second breakout.
    Stop uses position return relative to actual R1 entry price.
    """
    if stop_levels is None:
        stop_levels = STOP_LEVELS

    trade = RuleTrade(
        signal_id=signal_id, rule_id="R1", event_date=event_date,
        entry_date=entry_date_original, cost_bps=cost_bps,
    )

    if path.insufficient_data:
        trade.status = "RIGHT_CENSORED"
        trade.status_reason = path.insufficient_reason or "path_insufficient_data"
        return trade

    if path.second_breakout_date is None:
        trade.status = "NO_TRADE"; trade.status_reason = "no_second_breakout"
        trade.net_return = 0.0; trade.gross_return = 0.0; return trade

    conf_idx = np.searchsorted(calendar, path.second_breakout_date)
    if conf_idx >= len(calendar) or calendar[conf_idx] != path.second_breakout_date:
        trade.status = "NO_TRADE"; trade.status_reason = "second_breakout_not_in_calendar"
        trade.net_return = 0.0; trade.gross_return = 0.0; return trade
    if conf_idx + 1 >= len(calendar):
        trade.status = "RIGHT_CENSORED"; trade.status_reason = "entry_beyond_calendar"; return trade

    r1_entry_date = int(calendar[conf_idx + 1])
    if trunc_date is not None and r1_entry_date >= trunc_date:
        trade.status = "NO_TRADE"; trade.status_reason = "confirmation_beyond_boundary"
        trade.net_return = 0.0; trade.gross_return = 0.0; return trade

    # Late-entry rules (R1/R3) enter after day 20.  If the path has unexplained
    # NaN gaps beyond day 20, the holding period may contain unknown prices.
    if path.has_post_20d_gap:
        # Check if the entry falls after the 20-day verified window
        entry_idx = np.searchsorted(dates, r1_entry_date)
        if entry_idx >= 20:
            trade.status = "RIGHT_CENSORED"
            trade.status_reason = "late_entry_overlaps_post_20d_gap"
            return trade

    trade.entry_date = r1_entry_date
    executable, reason = _check_basket_execution(
        execution_context, r1_entry_date, "buy"
    )
    if not executable:
        # No position established → strategy P&L = 0
        trade.status = "NO_TRADE"
        trade.status_reason = f"entry_untradable:{reason}"
        trade.net_return = 0.0; trade.gross_return = 0.0
        return trade
    entry_ret, _ = _nav_at_path(rets, dates, r1_entry_date)
    if entry_ret is None:
        trade.status = "UNTRADABLE"; trade.status_reason = "no_entry_data_after_confirmation"
        return trade

    entry_leg = {
        "leg_type": "entry", "date": r1_entry_date,
        "fill_price_ratio": 1.0 + entry_ret, "weight": 1.0,
        "reason": "second_breakout_confirmed",
    }

    # Stop scan with POSITION returns relative to R1 entry
    stopped, stop_exit_date, stop_level = _stop_scan_position(
        rets, dates, calendar, r1_entry_date, entry_ret,
        hold_days, stop_levels, trunc_date,
    )

    # Stop confirmed at k but k+1 > trunc_date → cannot execute the stop.
    # Fall through to boundary exit instead of right-censoring.
    stop_blocked_by_boundary = stopped and stop_exit_date is None

    if stopped and not stop_blocked_by_boundary:
        stop_exit_date, defer_reason = _try_exit_or_defer(
            stop_exit_date, execution_context, calendar, trunc_date,
        )
        if stop_exit_date is None:
            trade.status = "UNTRADABLE"
            trade.status_reason = f"stop_exit_deferred_failed:{defer_reason}"
            trade.legs = [entry_leg]; trade.n_legs = 1
            return trade
        stop_ret, _ = _nav_at_path(rets, dates, stop_exit_date)
        if stop_ret is None:
            trade.status = "RIGHT_CENSORED"
            trade.status_reason = "no_stop_exit_data"
            trade.legs = [entry_leg]; trade.n_legs = 1
            return trade
        pos_ret = _position_return(stop_ret, entry_ret)
        exit_leg = {
            "leg_type": "exit", "date": stop_exit_date,
            "fill_price_ratio": 1.0 + stop_ret, "weight": 1.0,
            "reason": f"stop_loss_{stop_level}",
        }
        trade.status = "STOPPED_OUT"; trade.status_reason = f"stop_at_{stop_level}"
        gross = float(pos_ret)
    else:
        # Either (a) no stop, or (b) stop confirmed but k+1 past boundary.
        # Case (b): exit at the boundary (consistent with 20d capping).
        if stop_blocked_by_boundary:
            exit_date = trunc_date
            exit_reason = "next_event_exit"
        else:
            exit_date = trading_day_offset(calendar, r1_entry_date, hold_days)
            exit_reason = "hold_20d"
            if trunc_date is not None and exit_date is not None and exit_date > trunc_date:
                exit_date = trunc_date
                exit_reason = "next_event_exit"
        if exit_date is None:
            trade.status = "RIGHT_CENSORED"; trade.status_reason = "exit_beyond_data"
            trade.legs = [entry_leg]; trade.n_legs = 1; return trade
        exit_date, defer_reason = _try_exit_or_defer(
            exit_date, execution_context, calendar, trunc_date,
        )
        if exit_date is None:
            trade.status = "UNTRADABLE"; trade.status_reason = f"exit_deferred_failed:{defer_reason}"
            trade.legs = [entry_leg]; trade.n_legs = 1; return trade
        exit_ret, _ = _nav_at_path(rets, dates, exit_date)
        if exit_ret is None:
            trade.status = "RIGHT_CENSORED"; trade.status_reason = "no_exit_data"
            trade.legs = [entry_leg]; trade.n_legs = 1; return trade
        exit_leg = {
            "leg_type": "exit", "date": exit_date,
            "fill_price_ratio": 1.0 + exit_ret, "weight": 1.0,
            "reason": exit_reason,
        }
        gross = _position_return(exit_ret, entry_ret)

    cost_ratio = _round_trip_cost(1.0, cost_bps)
    trade.legs = [entry_leg, exit_leg]
    trade.n_legs = 2
    trade.total_cost_ratio = cost_ratio
    trade.gross_return = float(gross) if not np.isnan(gross) else None
    trade.net_return = float(gross - cost_ratio) if trade.gross_return is not None else None
    if trade.status == "COMPLETED" and exit_leg.get("reason", "") == "next_event_exit":
        trade.status = "TRUNCATED_EXIT"
        trade.status_reason = "next_event_exit"
    return trade


def simulate_rule_r2(
    signal_id: str, event_date: int, entry_date: int,
    path: PathResult,
    rets: np.ndarray, dates: np.ndarray, calendar: np.ndarray,
    cost_bps: int = 100, hold_days: int = 20,
    stop_levels: list[float] | None = None,
    trunc_date: int | None = None,
    execution_context: ExecutionContext | None = None,
) -> RuleTrade:
    """R2: Half at T+1, half on second breakout. Each half pays scaled cost."""
    if stop_levels is None:
        stop_levels = STOP_LEVELS

    trade = RuleTrade(
        signal_id=signal_id, rule_id="R2", event_date=event_date,
        entry_date=entry_date, cost_bps=cost_bps,
    )

    if path.insufficient_data:
        trade.status = "RIGHT_CENSORED"
        trade.status_reason = path.insufficient_reason or "path_insufficient_data"
        return trade

    entry_ret, _ = _nav_at_path(rets, dates, entry_date)
    if entry_ret is None:
        trade.status = "REJECTED"; trade.status_reason = "no_entry_data_leg1"; return trade
    executable, reason = _check_basket_execution(execution_context, entry_date, "buy")
    if not executable:
        # No position established → strategy P&L = 0
        trade.status = "NO_TRADE"; trade.status_reason = f"entry_untradable:{reason}"
        trade.net_return = 0.0; trade.gross_return = 0.0; return trade

    leg1_entry = {
        "leg_type": "entry", "date": entry_date,
        "fill_price_ratio": 1.0 + entry_ret, "weight": 0.5,
        "reason": "initial_half",
    }

    exit_date_20 = trading_day_offset(calendar, entry_date, hold_days)
    r2_truncated = False
    if trunc_date is not None and exit_date_20 is not None and exit_date_20 > trunc_date:
        exit_date_20 = trunc_date  # exit at next panic signal
        r2_truncated = True

    # Leg 2: confirmation date must be before Leg 1 exit
    leg2_entry = None
    leg2_failure_reason = ""
    if path.second_breakout_date is not None:
        conf_idx = np.searchsorted(calendar, path.second_breakout_date)
        if conf_idx + 1 < len(calendar) and calendar[conf_idx] == path.second_breakout_date:
            leg2_date = int(calendar[conf_idx + 1])
            if exit_date_20 is None or leg2_date < exit_date_20:
                if trunc_date is None or leg2_date < trunc_date:
                    executable, reason = _check_basket_execution(
                        execution_context, leg2_date, "buy"
                    )
                    if not executable:
                        leg2_failure_reason = f"leg2_untradable:{reason}"
                    else:
                        leg2_ret, _ = _nav_at_path(rets, dates, leg2_date)
                        if leg2_ret is not None:
                            leg2_entry = {
                                "leg_type": "add", "date": leg2_date,
                                "fill_price_ratio": 1.0 + leg2_ret, "weight": 0.5,
                                "reason": "second_breakout_add",
                            }
                        else:
                            leg2_failure_reason = "leg2_untradable:no_entry_nav"

    if exit_date_20 is None:
        trade.status = "RIGHT_CENSORED"; trade.status_reason = "exit_beyond_data"
        trade.legs = [leg1_entry] + ([leg2_entry] if leg2_entry else [])
        trade.n_legs = len(trade.legs); return trade

    # Stop scan from Leg 1 entry, using position returns relative to Leg 1 entry
    stopped, stop_exit_date, stop_level = _stop_scan_position(
        rets, dates, calendar, entry_date, entry_ret,
        hold_days, stop_levels, trunc_date,
    )

    # Stop confirmed at k but k+1 > trunc_date → fall through to boundary exit
    stop_blocked_by_boundary = stopped and stop_exit_date is None

    if stopped and not stop_blocked_by_boundary:
        stop_exit_date, defer_reason = _try_exit_or_defer(
            stop_exit_date, execution_context, calendar, trunc_date,
        )
        if stop_exit_date is None:
            trade.status = "UNTRADABLE"
            trade.status_reason = f"stop_exit_deferred_failed:{defer_reason}"
            trade.legs = [leg1_entry] + ([leg2_entry] if leg2_entry else [])
            trade.n_legs = len(trade.legs)
            return trade
        stop_ret, _ = _nav_at_path(rets, dates, stop_exit_date)
        if stop_ret is None:
            trade.status = "RIGHT_CENSORED"
            trade.status_reason = "no_stop_exit_data"
            trade.legs = [leg1_entry] + ([leg2_entry] if leg2_entry else [])
            trade.n_legs = len(trade.legs)
            return trade
        stop_pos_ret = _position_return(stop_ret, entry_ret)
        exit_ratio = 1.0 + stop_ret
        leg1_exit = {
            "leg_type": "exit", "date": stop_exit_date,
            "fill_price_ratio": exit_ratio, "weight": 0.5,
            "reason": f"stop_loss_{stop_level}",
        }
        trade.status = "STOPPED_OUT"; trade.status_reason = f"stop_at_{stop_level}"
        leg1_gross = 0.5 * float(stop_pos_ret)
        leg2_gross = 0.0
        if leg2_entry is not None and leg2_entry["date"] < stop_exit_date:
            leg2_pos_ret = _position_return(stop_ret,
                                            leg2_entry["fill_price_ratio"] - 1.0)
            leg2_gross = 0.5 * float(leg2_pos_ret)
            leg2_exit = {
                "leg_type": "exit", "date": stop_exit_date,
                "fill_price_ratio": exit_ratio, "weight": 0.5,
                "reason": f"stop_loss_{stop_level}",
            }
            trade.legs = [leg1_entry, leg2_entry, leg1_exit, leg2_exit]
            trade.n_legs = 4
            trade.total_cost_ratio = _round_trip_cost(0.5, cost_bps) + _round_trip_cost(0.5, cost_bps)
        else:
            trade.legs = [leg1_entry, leg1_exit]
            trade.n_legs = 2
            trade.total_cost_ratio = _round_trip_cost(0.5, cost_bps)
        gross = leg1_gross + leg2_gross
    else:
        # Either (a) no stop, or (b) stop confirmed but k+1 past boundary.
        # Case (b): exit at the boundary (consistent with R0/R1/R3).
        if stop_blocked_by_boundary:
            exit_date_20 = trunc_date
            exit_reason_r2 = "next_event_exit"
            # Boundary exit: leg2 would have entered past boundary → no leg2
            if leg2_entry is not None:
                leg2_entry = None
                leg2_failure_reason = "leg2_blocked_by_boundary"
        else:
            exit_reason_r2 = "hold_20d"
        exit_date_20, defer_reason = _try_exit_or_defer(
            exit_date_20, execution_context, calendar, trunc_date,
        )
        if exit_date_20 is None:
            trade.status = "UNTRADABLE"; trade.status_reason = f"exit_deferred_failed:{defer_reason}"
            trade.legs = [leg1_entry] + ([leg2_entry] if leg2_entry else [])
            trade.n_legs = len(trade.legs); return trade

        # Read NAV at the FINAL exit date (after any deferral)
        exit_ret, _ = _nav_at_path(rets, dates, exit_date_20)
        if exit_ret is None:
            trade.status = "RIGHT_CENSORED"; trade.status_reason = "no_exit_data"
            trade.legs = [leg1_entry] + ([leg2_entry] if leg2_entry else [])
            trade.n_legs = len(trade.legs); return trade

        exit_ratio = 1.0 + exit_ret
        leg1_exit = {
            "leg_type": "exit", "date": exit_date_20,
            "fill_price_ratio": exit_ratio, "weight": 0.5,
            "reason": exit_reason_r2,
        }
        leg1_pos_ret = _position_return(exit_ret, entry_ret)
        leg1_gross = 0.5 * float(leg1_pos_ret)

        if leg2_entry is not None:
            leg2_entry_ret = leg2_entry["fill_price_ratio"] - 1.0
            leg2_pos_ret = _position_return(exit_ret, leg2_entry_ret)
            leg2_gross = 0.5 * float(leg2_pos_ret)
            leg2_exit = {
                "leg_type": "exit", "date": exit_date_20,
                "fill_price_ratio": exit_ratio, "weight": 0.5,
                "reason": exit_reason_r2,
            }
            trade.legs = [leg1_entry, leg2_entry, leg1_exit, leg2_exit]
            trade.n_legs = 4
            trade.total_cost_ratio = _round_trip_cost(0.5, cost_bps) + _round_trip_cost(0.5, cost_bps)
        else:
            leg2_gross = 0.0
            trade.legs = [leg1_entry, leg1_exit]
            trade.n_legs = 2
            trade.total_cost_ratio = _round_trip_cost(0.5, cost_bps)

        gross = leg1_gross + leg2_gross

    trade.gross_return = float(gross) if not np.isnan(gross) else None
    trade.net_return = float(gross - trade.total_cost_ratio) if trade.gross_return is not None else None
    if (r2_truncated or stop_blocked_by_boundary) and trade.status == "COMPLETED":
        trade.status = "TRUNCATED_EXIT"
        trade.status_reason = "next_event_exit"
    if leg2_failure_reason and trade.status == "COMPLETED":
        trade.status_reason = leg2_failure_reason
    return trade


def simulate_rule_r3(
    signal_id: str, event_date: int, entry_date: int,
    path: PathResult,
    rets: np.ndarray, dates: np.ndarray, calendar: np.ndarray,
    cost_bps: int = 100, hold_days: int = 20,
    stop_levels: list[float] | None = None,
    trunc_date: int | None = None,
    execution_context: ExecutionContext | None = None,
) -> RuleTrade:
    """R3: Full position at T+1, stop-loss with ONE optional W-pattern re-entry.

    Stop executes at day k+1. Each completed round trip pays its own cost.
    """
    if stop_levels is None:
        stop_levels = STOP_LEVELS

    trade = RuleTrade(
        signal_id=signal_id, rule_id="R3", event_date=event_date,
        entry_date=entry_date, cost_bps=cost_bps,
    )

    if path.insufficient_data:
        trade.status = "RIGHT_CENSORED"
        trade.status_reason = path.insufficient_reason or "path_insufficient_data"
        return trade

    entry_ret, _ = _nav_at_path(rets, dates, entry_date)
    if entry_ret is None:
        trade.status = "REJECTED"; trade.status_reason = "no_entry_data_leg1"; return trade
    executable, reason = _check_basket_execution(execution_context, entry_date, "buy")
    if not executable:
        # No position established → strategy P&L = 0
        trade.status = "NO_TRADE"; trade.status_reason = f"entry_untradable:{reason}"
        trade.net_return = 0.0; trade.gross_return = 0.0; return trade

    leg1_entry = {
        "leg_type": "entry", "date": entry_date,
        "fill_price_ratio": 1.0 + entry_ret, "weight": 1.0,
        "reason": "initial_entry",
    }

    stopped, stop_exit_date, stop_level = _stop_scan_position(
        rets, dates, calendar, entry_date, entry_ret,
        hold_days, stop_levels, trunc_date,
    )

    # Stop confirmed at k but k+1 > trunc_date → cannot execute the stop.
    # Fall through to boundary exit instead of right-censoring.
    stop_blocked_by_boundary = stopped and stop_exit_date is None

    if not stopped or stop_blocked_by_boundary:
        # Either (a) no stop, or (b) stop confirmed but k+1 past boundary.
        # Case (b): exit at the boundary — no re-entry possible.
        if stop_blocked_by_boundary:
            exit_date = trunc_date
            exit_reason_r3 = "next_event_exit"
        else:
            exit_date = trading_day_offset(calendar, entry_date, hold_days)
            exit_reason_r3 = "hold_20d"
            if trunc_date is not None and exit_date is not None and exit_date > trunc_date:
                exit_date = trunc_date
                exit_reason_r3 = "next_event_exit"
        if exit_date is None:
            trade.status = "RIGHT_CENSORED"; trade.status_reason = "exit_beyond_data"
            trade.legs = [leg1_entry]; trade.n_legs = 1; return trade
        exit_date, defer_reason = _try_exit_or_defer(
            exit_date, execution_context, calendar, trunc_date,
        )
        if exit_date is None:
            trade.status = "UNTRADABLE"; trade.status_reason = f"exit_deferred_failed:{defer_reason}"
            trade.legs = [leg1_entry]; trade.n_legs = 1; return trade
        exit_ret, _ = _nav_at_path(rets, dates, exit_date)
        if exit_ret is None:
            trade.status = "RIGHT_CENSORED"; trade.status_reason = "no_exit_data"
            trade.legs = [leg1_entry]; trade.n_legs = 1; return trade
        leg1_exit = {
            "leg_type": "exit", "date": exit_date,
            "fill_price_ratio": 1.0 + exit_ret, "weight": 1.0,
            "reason": exit_reason_r3,
        }
        gross = _position_return(exit_ret, entry_ret)
        cost_ratio = _round_trip_cost(1.0, cost_bps)
        trade.legs = [leg1_entry, leg1_exit]; trade.n_legs = 2
        trade.total_cost_ratio = cost_ratio
        trade.gross_return = float(gross)
        trade.net_return = float(gross - cost_ratio)
        if exit_reason_r3 == "next_event_exit":
            trade.status = "TRUNCATED_EXIT"
            trade.status_reason = "next_event_exit"
        return trade

    # Stop executed normally (k+1 ≤ trunc_date).
    # Proceed with stop exit + potential re-entry.
    stop_exit_date, defer_reason = _try_exit_or_defer(
        stop_exit_date, execution_context, calendar, trunc_date,
    )
    if stop_exit_date is None:
        trade.status = "UNTRADABLE"
        trade.status_reason = f"stop_exit_deferred_failed:{defer_reason}"
        trade.legs = [leg1_entry]; trade.n_legs = 1
        return trade
    stop_ret, _ = _nav_at_path(rets, dates, stop_exit_date)
    if stop_ret is None:
        trade.status = "RIGHT_CENSORED"
        trade.status_reason = "no_stop_exit_data"
        trade.legs = [leg1_entry]; trade.n_legs = 1
        return trade
    stop_pos_ret = _position_return(stop_ret, entry_ret)
    leg1_exit = {
        "leg_type": "exit", "date": stop_exit_date,
        "fill_price_ratio": 1.0 + stop_ret, "weight": 1.0,
        "reason": f"stop_loss_{stop_level}",
    }
    trade.status = "STOPPED_OUT"; trade.status_reason = f"stop_at_{stop_level}"
    leg1_gross = float(stop_pos_ret)
    cost_full = _round_trip_cost(1.0, cost_bps)
    leg1_net = leg1_gross - cost_full

    # Re-entry check
    if (path.second_breakout_date is not None and stop_exit_date is not None
            and path.second_breakout_date >= stop_exit_date):
        conf_idx = np.searchsorted(calendar, path.second_breakout_date)
        if conf_idx + 1 < len(calendar) and calendar[conf_idx] == path.second_breakout_date:
            re_entry_date = int(calendar[conf_idx + 1])
            # If the path has post-20d gaps and re-entry happens after day 20,
            # the re-entry holding period may be unreliable.
            if path.has_post_20d_gap:
                entry_idx = np.searchsorted(dates, re_entry_date)
                if entry_idx >= 20:
                    trade.status = "PARTIAL"
                    trade.status_reason = "leg1_stopped__leg2_reentry_blocked_by_post_20d_gap"
                    # PARTIAL: leg2 open, P&L is incomplete.  Set to None so
                    # aggregates never include half-realized returns.
                    trade.gross_return = None
                    trade.net_return = None
                    trade.legs = [leg1_entry, leg1_exit]
                    trade.n_legs = 2
                    trade.total_cost_ratio = cost_full
                    return trade
            if trunc_date is None or re_entry_date < trunc_date:
                executable, reason = _check_basket_execution(
                    execution_context, re_entry_date, "buy"
                )
                if executable:
                    re_entry_ret, _ = _nav_at_path(rets, dates, re_entry_date)
                else:
                    re_entry_ret = None
                    trade.status_reason = f"reentry_untradable:{reason}"
                if re_entry_ret is not None:
                    leg2_entry = {
                        "leg_type": "entry", "date": re_entry_date,
                        "fill_price_ratio": 1.0 + re_entry_ret, "weight": 1.0,
                        "reason": "re_entry_second_breakout",
                    }
                    # ── Re-entry stop scan (same parameters as initial entry) ──
                    re_stopped, re_stop_exit_date, re_stop_level = _stop_scan_position(
                        rets, dates, calendar, re_entry_date, re_entry_ret,
                        hold_days, stop_levels, trunc_date,
                    )

                    # Stop confirmed at k but k+1 > trunc_date → cannot
                    # execute the stop.  Fall through to boundary exit.
                    re_stop_blocked = re_stopped and re_stop_exit_date is None

                    if re_stopped and not re_stop_blocked:
                        re_stop_exit_date, defer_reason = _try_exit_or_defer(
                            re_stop_exit_date, execution_context, calendar,
                            trunc_date,
                        )
                        if re_stop_exit_date is None:
                            trade.legs = [leg1_entry, leg1_exit, leg2_entry]
                            trade.n_legs = 3
                            trade.total_cost_ratio = cost_full
                            trade.status = "UNTRADABLE"
                            trade.status_reason = (
                                f"leg1_stopped__leg2_stop_deferred_failed"
                                f":{defer_reason}"
                            )
                            trade.gross_return = leg1_gross
                            trade.net_return = leg1_net
                            return trade
                        re_exit_ret, _ = _nav_at_path(rets, dates, re_stop_exit_date)
                        if re_exit_ret is None:
                            trade.legs = [leg1_entry, leg1_exit, leg2_entry]
                            trade.n_legs = 3
                            trade.total_cost_ratio = cost_full
                            trade.status = "RIGHT_CENSORED"
                            trade.status_reason = "no_reentry_stop_exit_data"
                            trade.gross_return = None; trade.net_return = None
                            return trade
                        leg2_exit = {
                            "leg_type": "exit", "date": re_stop_exit_date,
                            "fill_price_ratio": 1.0 + re_exit_ret, "weight": 1.0,
                            "reason": f"re_entry_stop_loss_{re_stop_level}",
                        }
                        leg2_pos_ret = _position_return(re_exit_ret, re_entry_ret)
                        leg2_gross = float(leg2_pos_ret)
                        leg2_net = leg2_gross - cost_full
                        trade.legs = [leg1_entry, leg1_exit, leg2_entry, leg2_exit]
                        trade.n_legs = 4
                        compound_gross = (1.0 + leg1_gross) * (1.0 + leg2_gross) - 1.0
                        trade.gross_return = float(compound_gross)
                        trade.net_return = float((1.0 + leg1_net) * (1.0 + leg2_net) - 1.0)
                        trade.total_cost_ratio = float(compound_gross - trade.net_return)
                        trade.status = "STOPPED_OUT"
                        trade.status_reason = (
                            f"stop_at_{stop_level}_"
                            f"re_entry_stop_at_{re_stop_level}"
                        )
                        return trade

                    # ── No re-entry stop (or stop blocked by boundary): ──
                    # hold 20d / boundary exit
                    if re_stop_blocked:
                        re_exit_date = trunc_date
                        re_exit_reason = "next_event_exit"
                    else:
                        re_exit_date = trading_day_offset(
                            calendar, re_entry_date, hold_days,
                        )
                        re_exit_reason = "hold_20d_re_entry"
                        if (trunc_date is not None and re_exit_date is not None
                                and re_exit_date > trunc_date):
                            re_exit_date = trunc_date
                            re_exit_reason = "next_event_exit"
                    if re_exit_date is None:
                        # Planned 20d exit is beyond calendar.  If a next-event
                        # boundary exists, exit there; otherwise truly censored.
                        if trunc_date is not None:
                            re_exit_date = trunc_date
                            re_exit_reason = "next_event_exit"
                        else:
                            # Re-entry exit beyond data — leg1 stop IS realized,
                            # leg2 is open.  Mark partial, report leg1 P&L only.
                            trade.legs = [leg1_entry, leg1_exit, leg2_entry]
                            trade.n_legs = 3
                            trade.total_cost_ratio = cost_full  # one round trip for leg1
                            trade.status = "PARTIAL"
                            trade.status_reason = "leg1_stopped__leg2_open_censored_exit"
                            # PARTIAL: leg2 open, P&L is incomplete.
                            trade.gross_return = None
                            trade.net_return = None
                            return trade
                    re_exit_date, defer_reason = _try_exit_or_defer(
                        re_exit_date, execution_context, calendar, trunc_date,
                    )
                    if re_exit_date is None:
                        trade.legs = [leg1_entry, leg1_exit, leg2_entry]
                        trade.n_legs = 3
                        trade.total_cost_ratio = cost_full
                        trade.status = "UNTRADABLE"
                        trade.status_reason = (
                            f"leg1_stopped__leg2_deferred_failed"
                            f":{defer_reason}"
                        )
                        trade.gross_return = leg1_gross
                        trade.net_return = leg1_net
                        return trade
                    re_exit_ret, _ = _nav_at_path(rets, dates, re_exit_date)
                    if re_exit_ret is None:
                        trade.legs = [leg1_entry, leg1_exit, leg2_entry]
                        trade.n_legs = 3
                        trade.total_cost_ratio = cost_full
                        trade.status = "RIGHT_CENSORED"
                        trade.status_reason = "no_reentry_exit_data"
                        trade.gross_return = None; trade.net_return = None
                        return trade
                    leg2_exit = {
                        "leg_type": "exit", "date": re_exit_date,
                        "fill_price_ratio": 1.0 + re_exit_ret, "weight": 1.0,
                        "reason": re_exit_reason,
                    }
                    leg2_pos_ret = _position_return(re_exit_ret, re_entry_ret)
                    leg2_gross = float(leg2_pos_ret)
                    leg2_net = leg2_gross - cost_full
                    trade.legs = [leg1_entry, leg1_exit, leg2_entry, leg2_exit]
                    trade.n_legs = 4
                    # Compound returns: capital is reinvested across legs
                    compound_gross = (1.0 + leg1_gross) * (1.0 + leg2_gross) - 1.0
                    trade.gross_return = float(compound_gross)
                    trade.net_return = float((1.0 + leg1_net) * (1.0 + leg2_net) - 1.0)
                    trade.total_cost_ratio = float(compound_gross - trade.net_return)
                    if re_exit_reason == "next_event_exit":
                        trade.status = "TRUNCATED_EXIT"
                        trade.status_reason = "stop_then_re_entry_next_event_exit"
                    else:
                        trade.status = "COMPLETED"
                        trade.status_reason = "stop_then_re_entry"
                    return trade

    # No re-entry
    trade.legs = [leg1_entry, leg1_exit]; trade.n_legs = 2
    trade.total_cost_ratio = cost_full
    trade.gross_return = leg1_gross
    trade.net_return = leg1_net
    return trade


def _flatten_trade(trade: RuleTrade) -> dict:
    row = {
        "signal_id": trade.signal_id, "rule_id": trade.rule_id,
        "event_date": trade.event_date, "entry_date": trade.entry_date,
        "cost_bps": trade.cost_bps, "n_legs": trade.n_legs,
        "net_return": trade.net_return, "gross_return": trade.gross_return,
        "total_cost_ratio": trade.total_cost_ratio,
        "status": trade.status, "status_reason": trade.status_reason,
        "path_type": trade.path_type, "market_regime": trade.market_regime,
    }
    for i in range(4):
        idx = str(i + 1)
        if i < len(trade.legs):
            leg = trade.legs[i]
            row[f"leg_{idx}_type"] = leg.get("leg_type", "")
            row[f"leg_{idx}_date"] = leg.get("date", 0)
            row[f"leg_{idx}_weight"] = leg.get("weight", 0.0)
            row[f"leg_{idx}_price_ratio"] = leg.get("fill_price_ratio", np.nan)
            row[f"leg_{idx}_reason"] = leg.get("reason", "")
        else:
            for s, d in [("type", ""), ("date", 0), ("weight", 0.0), ("price_ratio", np.nan), ("reason", "")]:
                row[f"leg_{idx}_{s}"] = d
    return row


# ═══════════════════════════════════════════════════════════════════════════
# Layer 3: Statistical Reporter
# ═══════════════════════════════════════════════════════════════════════════

def compute_paired_differences(
    trade_ledger: pd.DataFrame, primary_cost: int = 100,
) -> pd.DataFrame:
    """Paired differences. Only a deliberate NO_TRADE maps to zero."""
    required = {"cost_bps", "signal_id", "rule_id", "status", "net_return"}
    if trade_ledger.empty or not required.issubset(trade_ledger.columns):
        return pd.DataFrame()
    ledger = trade_ledger[trade_ledger["cost_bps"] == primary_cost].copy()
    if ledger.empty:
        return pd.DataFrame()

    pairs = []
    for signal_id in ledger["signal_id"].unique():
        et = ledger[ledger["signal_id"] == signal_id]
        r0 = et[et["rule_id"] == "R0"]
        if r0.empty or r0.iloc[0]["status"] in (
            "REJECTED", "RIGHT_CENSORED", "UNTRADABLE", "PARTIAL"
        ):
            continue
        r0_net = r0.iloc[0]["net_return"]
        if pd.isna(r0_net):
            continue

        row = {"signal_id": signal_id, "R0_net": r0_net}
        for rule in ["R1", "R2", "R3"]:
            rt = et[et["rule_id"] == rule]
            if rt.empty:
                row[f"{rule}_net"] = np.nan; row[f"delta_{rule}_R0"] = np.nan; continue
            s = rt.iloc[0]
            if s["status"] in ("REJECTED", "RIGHT_CENSORED", "UNTRADABLE", "PARTIAL"):
                row[f"{rule}_net"] = np.nan; row[f"delta_{rule}_R0"] = np.nan; continue
            rn = s["net_return"]
            if pd.isna(rn) and s["status"] == "NO_TRADE":
                rn = 0.0
            elif pd.isna(rn):
                row[f"{rule}_net"] = np.nan; row[f"delta_{rule}_R0"] = np.nan; continue
            row[f"{rule}_net"] = rn
            row[f"delta_{rule}_R0"] = rn - r0_net

        pairs.append(row)
    return pd.DataFrame(pairs)


def bootstrap_ci(values: np.ndarray, n_bootstrap: int = 2000,
                 ci_level: float = 0.95, seed: int = 20260710) -> tuple[float, float, float]:
    """IID bootstrap (naive).  Use cluster_bootstrap_ci for temporal data."""
    values = values[~np.isnan(values)]
    if len(values) == 0:
        return np.nan, np.nan, np.nan
    rng = np.random.RandomState(seed)
    boot_means = np.array([np.mean(rng.choice(values, size=len(values), replace=True))
                           for _ in range(n_bootstrap)])
    alpha = (1.0 - ci_level) / 2.0
    return (float(np.mean(boot_means)),
            float(np.percentile(boot_means, 100 * alpha)),
            float(np.percentile(boot_means, 100 * (1 - alpha))))


def cluster_bootstrap_ci(
    values: np.ndarray,
    cluster_ids: np.ndarray,
    n_bootstrap: int = 2000,
    ci_level: float = 0.95,
    seed: int = 20260710,
) -> tuple[float, float, float]:
    """Block/cluster bootstrap: resample clusters, not individual events.

    Each *cluster_id* (e.g. year) is a block.  Within-cluster correlation
    is preserved.  Appropriate for panel/time-series data where events
    within the same year are not independent.
    """
    mask = ~np.isnan(values)
    values = values[mask]
    cluster_ids = cluster_ids[mask]
    if len(values) == 0:
        return np.nan, np.nan, np.nan

    unique_clusters = np.unique(cluster_ids)
    n_clusters = len(unique_clusters)
    if n_clusters < 3:
        # Too few clusters for meaningful bootstrap — return iid as fallback
        # with a note that CIs are descriptive only
        return bootstrap_ci(values, n_bootstrap, ci_level, seed)

    rng = np.random.RandomState(seed)
    boot_means = np.empty(n_bootstrap)
    for b in range(n_bootstrap):
        # Resample clusters with replacement
        sampled_clusters = rng.choice(unique_clusters, size=n_clusters, replace=True)
        boot_sample = []
        for c in sampled_clusters:
            boot_sample.extend(values[cluster_ids == c])
        boot_means[b] = np.mean(boot_sample) if boot_sample else 0.0

    alpha = (1.0 - ci_level) / 2.0
    return (float(np.mean(boot_means)),
            float(np.percentile(boot_means, 100 * alpha)),
            float(np.percentile(boot_means, 100 * (1 - alpha))))


def generate_report(
    path_ledger: pd.DataFrame, trade_ledger: pd.DataFrame, paired: pd.DataFrame,
    events: list, start: int, end: int,
    primary_cost: int = 100, cost_scenarios: list[int] | None = None,
    bootstrap_runs: int = 2000, bootstrap_ci_level: float = 0.95,
    seed: int = 20260710, config_hash: str = "",
    **kwargs,
) -> str:
    if cost_scenarios is None:
        cost_scenarios = COST_SCENARIOS_BPS

    n_events = len(path_ledger)
    n_insufficient = int((path_ledger["insufficient_data"] == True).sum()) if not path_ledger.empty else 0  # noqa: E712
    n_censored_paths = int((path_ledger["path_type"] == "RIGHT_CENSORED").sum()) if not path_ledger.empty else 0
    n_truncated = int((path_ledger["truncated_by_next_event"] == True).sum()) if not path_ledger.empty and "truncated_by_next_event" in path_ledger.columns else 0  # noqa: E712
    n_valid = n_events - n_insufficient

    lines = [
        "# 光刻胶恐慌路径规则评估报告",
        "",
        f"生成时间：{datetime.now():%Y-%m-%d %H:%M:%S}",
        f"数据区间：{start} – {end}",
        f"配置哈希：{config_hash}",
        f"脚本版本：{SCRIPT_VERSION}",
        "",
        "状态：RESEARCH ONLY — 不构成投资建议。",
        "",
        "## 1. 事件总览",
        "",
        f"- 在线 first-trigger 事件（bull/neutral + ENTRY_RESOLVED）：{n_events}",
        f"- 数据缺口（NaN，不可交易）：{n_censored_paths}",
        f"- 下一事件截断（提前退出）：{n_truncated}",
        f"- 有效分类样本：{n_valid}",
    ]

    # Path type distribution (valid events only)
    valid = path_ledger[path_ledger["insufficient_data"] == False] if not path_ledger.empty else path_ledger  # noqa: E712
    if not valid.empty and "path_type" in valid.columns:
        dist = valid["path_type"].value_counts()
        lines.append("")
        lines.append("## 2. 路径类型分布（有效样本，排除 RIGHT_CENSORED）")
        lines.append("")
        lines.append("| 路径类型 | 数量 | 占比 |")
        lines.append("|----------|------|------|")
        for pt in ["NO_BOUNCE", "BOUNCE_NO_RETEST", "BOUNCE_THEN_FAIL", "W_RECOVERY"]:
            count = dist.get(pt, 0)
            pct = count / len(valid) * 100 if len(valid) > 0 else 0.0
            lines.append(f"| {pt} | {count} | {pct:.1f}% |")
        # Also report censored separately
        censored_count = int((path_ledger["path_type"] == "RIGHT_CENSORED").sum()) if not path_ledger.empty else 0
        if censored_count > 0:
            lines.append(f"| RIGHT_CENSORED (excluded) | {censored_count} | — |")

        lines.append("")
        lines.append(f"### 按路径类型的净收益（{primary_cost}bp 往返成本后，R0 规则）")
        lines.append("")
        lines.append("| 路径类型 | 均值 | 中位数 | 标准差 | 正收益率(全部信号) | 事件数 |")
        lines.append("|----------|------|--------|--------|-------------------|--------|")
        # Use R0 trade results (which handle truncation / NO_TRADE / censor)
        # rather than net_return_20d (which requires a full 20-day window).
        valid_with_r0 = valid.copy()
        valid_with_r0["r0_net_return"] = np.nan
        if not trade_ledger.empty:
            r0_sub = trade_ledger[
                (trade_ledger["rule_id"] == "R0")
                & (trade_ledger["cost_bps"] == primary_cost)
            ].copy()
            # Only deliberate NO_TRADE maps to zero; censored / partial /
            # untradable are excluded so they don't bias the per-path-type
            # distribution.
            r0_sub = r0_sub[r0_sub["status"].isin(
                ["COMPLETED", "STOPPED_OUT", "NO_TRADE", "TRUNCATED_EXIT"]
            )]
            no_trade = r0_sub["status"] == "NO_TRADE"
            r0_sub.loc[no_trade, "net_return"] = (
                r0_sub.loc[no_trade, "net_return"].fillna(0.0)
            )
            r0_sub = r0_sub.dropna(subset=["net_return"])
            if not r0_sub.empty:
                valid_with_r0 = valid.merge(
                    r0_sub[["signal_id", "net_return"]].rename(
                        columns={"net_return": "r0_net_return"}
                    ),
                    on="signal_id", how="left",
                )
        for pt in ["NO_BOUNCE", "BOUNCE_NO_RETEST", "BOUNCE_THEN_FAIL", "W_RECOVERY"]:
            subset = valid_with_r0[valid_with_r0["path_type"] == pt]["r0_net_return"].dropna()
            if len(subset) > 0:
                lines.append(
                    f"| {pt} | {subset.mean():.4f} | {subset.median():.4f} | "
                    f"{subset.std():.4f} | {(subset > 0).mean():.1%} | {len(subset)} |"
                )
            else:
                lines.append(f"| {pt} | — | — | — | — | 0 |")

    # Rule comparison
    if not paired.empty:
        lines.append("")
        lines.append("## 3. 规则配对比较")
        lines.append("")
        lines.append(f"口径：{primary_cost}bp 往返成本（= 完整开平仓合计）。NO_TRADE → 0。")
        lines.append(f"Bootstrap：{bootstrap_runs} 次，{bootstrap_ci_level:.0%} CI。")
        lines.append("")

        for rule in ["R1", "R2", "R3"]:
            dc = f"delta_{rule}_R0"
            if dc not in paired.columns:
                continue
            deltas = paired[dc].dropna()
            if len(deltas) == 0:
                continue
            # Extract cluster IDs from signal_id (e.g. PANIC_20210125 → year 2021)
            cluster_years = None
            if "signal_id" in paired.columns:
                idx = deltas.index
                years = paired.loc[idx, "signal_id"].astype(str).str.extract(
                    r"(\d{4})"
                )[0].astype(int).values
                if len(np.unique(years)) >= 3:
                    cluster_years = years
            if cluster_years is not None:
                bm, cl, ch = cluster_bootstrap_ci(
                    deltas.values, cluster_years,
                    n_bootstrap=bootstrap_runs, ci_level=bootstrap_ci_level, seed=seed,
                )
                ci_method = "cluster (by year)"
            else:
                bm, cl, ch = bootstrap_ci(
                    deltas.values,
                    n_bootstrap=bootstrap_runs, ci_level=bootstrap_ci_level, seed=seed,
                )
                ci_method = "iid (descriptive only)"
            lines.append(f"### {rule} − R0")
            lines.append(f"- 配对事件数：{len(deltas)}")
            lines.append(f"- 均值差异：{np.mean(deltas.values):.4f}")
            lines.append(f"- 中位数差异：{np.median(deltas.values):.4f}")
            lines.append(f"- Bootstrap {bootstrap_ci_level:.0%} CI [{ci_method}]：[{cl:.4f}, {ch:.4f}]")
            lines.append(f"- {rule} > R0 占比：{(deltas.values > 0).mean():.1%}")
            lines.append("")

    # Cost sensitivity
    lines.append("## 4. 成本敏感性")
    lines.append("")
    header = "| 规则 |" + "|".join(f" {c}bp 均值 | {c}bp 正收益率(全部信号) " for c in cost_scenarios) + "|"
    lines.append(header)
    lines.append("|------|" + "|".join("------|------" for _ in cost_scenarios) + "|")
    for rule_id in ["R0", "R1", "R2", "R3"]:
        vals = []
        for c in cost_scenarios:
            if trade_ledger.empty or not {
                "rule_id", "cost_bps", "status", "net_return"
            }.issubset(trade_ledger.columns):
                sub = pd.DataFrame(columns=["status", "net_return"])
            else:
                sub = trade_ledger[
                    (trade_ledger["rule_id"] == rule_id)
                    & (trade_ledger["cost_bps"] == c)
                ]
            # Execution/data failures are unknown outcomes, not zero-return
            # strategy decisions.  Only an explicit NO_TRADE maps to zero.
            mask_valid = sub["status"].isin(
                ["COMPLETED", "STOPPED_OUT", "NO_TRADE", "TRUNCATED_EXIT"]
            )
            returns = sub.loc[mask_valid, "net_return"].copy()
            no_trade = sub.loc[mask_valid, "status"] == "NO_TRADE"
            returns.loc[no_trade & returns.isna()] = 0.0
            returns = returns.dropna()
            if len(returns) > 0:
                vals.append(f" {returns.mean():.4f} | {(returns > 0).mean():.1%} ")
            else:
                vals.append(" — | — ")
        lines.append(f"| {rule_id} |" + "|".join(vals) + "|")

    # Coverage note
    statuses = trade_ledger["status"] if "status" in trade_ledger.columns else pd.Series(dtype=str)
    n_censored = int((statuses == "RIGHT_CENSORED").sum())
    n_rejected = int((statuses == "REJECTED").sum())
    n_untradable = int((statuses == "UNTRADABLE").sum())
    n_partial = int((statuses == "PARTIAL").sum())
    lines.append("")
    lines.append(
        f"排除：RIGHT_CENSORED {n_censored} 行，REJECTED {n_rejected} 行，"
        f"UNTRADABLE {n_untradable} 行，PARTIAL {n_partial} 行。仅 NO_TRADE 填 0。"
    )

    # Caveats — Pre-registered evaluation contract (§5)
    lines.append("")
    lines.append("## 5. 预登记评价合同与解释边界")
    lines.append("")
    lines.append("### 5.1 指标定义")
    lines.append("- **\"正收益率(全部信号)\"**：分母包含 NO_TRADE（P&L=0）、COMPLETED、STOPPED_OUT、TRUNCATED_EXIT；")
    lines.append("  排除 RIGHT_CENSORED、REJECTED、PARTIAL、UNTRADABLE。")
    lines.append("  这是全部信号正收益率，**不是**成交交易胜率。成交交易胜率排除 NO_TRADE 后会更低/更高。")
    lines.append("- **\"平均净收益\"**：事件等权平均净收益（非组合 P&L）。不包含资金时间线、")
    lines.append("  空仓再投资、净值曲线、最大回撤或年化收益率。**不能直接解读为组合绩效**。")
    lines.append("")
    lines.append("### 5.2 事件退出边界")
    lines.append("- \"下一事件\" = 下一条 bull/neutral + ENTRY_RESOLVED 的 panic first-trigger 信号日，")
    lines.append("  **不是**下一次原始 panic gate 触发。退出边界为下一事件日的 k+1（trunc_date），即信号确认日的下一个可交易日。")
    lines.append("- 退出不可交易时（跌停/停牌），尝试顺延至多 3 个交易日；全部失败则标记 UNTRADABLE。")
    lines.append("")
    lines.append("### 5.3 止损规则（预登记，不可事后优化）")
    lines.append("- R0/R1/R3 止损：基于仓位收益率（position return），k 日收盘确认 → k+1 日收盘执行。")
    lines.append("- R2 止损：基于**第一段仓位（leg1）的 entry 价格**计算仓位收益，不是组合加权成本。")
    lines.append("- R3 再入场后：**继续执行**相同止损参数（预登记决策）。再入场后的止损同样基于再入场价格。")
    lines.append("")
    lines.append("### 5.4 其他约束")
    lines.append("- 事件：在线 **first-trigger**，bull/neutral 状态，ENTRY_RESOLVED 冻结篮子。")
    lines.append("- 路径状态使用**冻结篮子收盘价**判定。")
    lines.append(f"- 往返成本 = {primary_cost}bp = 完整一次开平仓合计。")
    lines.append("- 四套规则预登记，**全部报告**。")
    lines.append(f"- 样本量有限（{n_valid} 有效事件），统计效力受样本量约束。")
    lines.append("- 未修改冻结的 primary_5d 主 gate。")
    lines.append("- 不足 20 日数据的删失事件不进入路径分类。")

    # ── Volume diagnostics (§6) ─────────────────────────────────────────
    volume_features_list = kwargs.get("volume_features_list", [])
    if volume_features_list:
        lines.append("")
        lines.append("## 6. 成交量/换手率诊断（Phase A — 不改变交易结果）")
        lines.append("")
        lines.append("### 6.1 特征覆盖率")
        n_vf = len(volume_features_list)
        n_to = sum(1 for vf in volume_features_list
                   if "turnover_rate_f" not in vf.features_unavailable)
        n_amt = sum(1 for vf in volume_features_list
                    if "amount" not in vf.features_unavailable)
        lines.append(f"- 事件数：{n_vf}")
        lines.append(f"- 换手率覆盖率：{n_to}/{n_vf} ({n_to/max(n_vf,1):.0%})")
        lines.append(f"- 成交额覆盖率：{n_amt}/{n_vf} ({n_amt/max(n_vf,1):.0%})")
        unavailable_reasons: dict[str, int] = {}
        for vf in volume_features_list:
            for reason in vf.features_unavailable:
                unavailable_reasons[reason] = unavailable_reasons.get(reason, 0) + 1
        if unavailable_reasons:
            lines.append("- 不可用原因：" + ", ".join(
                f"{k}: {v} 事件" for k, v in unavailable_reasons.items()
            ))
        lines.append("")
        lines.append("### 6.2 个股级特征（仅描述分布，不查看全样本收益关系）")
        lines.append("")
        lines.append("只允许预登记的成交额比率进入 §7 OOS 检验；其余特征不计算收益相关性或 p-value。")
        lines.append("")
        lines.append("| 特征 | 均值 | 中位数 | 标准差 | 状态 |")
        lines.append("|------|------|--------|--------|------|")
        feature_cols = [
            ("amount_ratio_20d_median", "成交额比率(20d中位数)", "唯一预登记候选"),
            ("turnover_ratio_20d_median", "换手率比率(20d中位数)", "描述性，不检验"),
            ("turnover_robust_z20_median", "换手率Robust z20", "描述性，不检验"),
            ("amihud_illiquidity_median", "Amihud非流动性", "描述性，不检验"),
            ("down_amount_share_5d_median", "下跌日成交占比(5d)", "描述性，不检验"),
        ]
        for attr, label, status in feature_cols:
            vals = [
                getattr(vf, attr, np.nan) for vf in volume_features_list
                if np.isfinite(getattr(vf, attr, np.nan))
            ]
            if len(vals) < 3:
                lines.append(f"| {label} | — | — | — | {status} (n<3) |")
                continue
            arr = np.array(vals, dtype=float)
            lines.append(
                f"| {label} | {np.mean(arr):.4f} | {np.median(arr):.4f} | "
                f"{np.std(arr):.4f} | {status} |"
            )

        lines.append("")
        lines.append("### 6.3 篮子级特征")
        lines.append("")
        lines.append("| 特征 | 均值 | 中位数 | 标准差 |")
        lines.append("|------|------|--------|--------|")
        basket_cols = [
            ("abnormal_volume_fraction", "异常放量且下跌比例"),
            ("high_turnover_limit_down_count", "高换手跌停家数"),
            ("amihud_shock_median", "Amihud冲击中位数"),
            ("turnover_cross_sectional_dispersion", "换手率横截面离散度"),
        ]
        for attr, label in basket_cols:
            vals = [getattr(vf, attr, np.nan) for vf in volume_features_list
                    if np.isfinite(getattr(vf, attr, np.nan))]
            if len(vals) < 3:
                lines.append(f"| {label} | — | — | — |")
                continue
            arr = np.array(vals, dtype=float)
            lines.append(f"| {label} | {np.mean(arr):.4f} | {np.median(arr):.4f} | {np.std(arr):.4f} |")

        lines.append("")
        lines.append("⚠️ 以上所有特征仅用于诊断，不参与 R0–R3 交易决策。")

        # ── Firewall and hard-gate results (§7) ──────────────────────────
        firewall_report = kwargs.get("firewall_report", {})
        hard_gate_verdict = kwargs.get("hard_gate_verdict")
        if firewall_report or hard_gate_verdict:
            lines.append("")
            lines.append("## 7. 防过拟合验证（Validation Firewall + Hard Gate Checker）")
            lines.append("")
            if firewall_report:
                lines.append(f"- 训练/验证分割数：{firewall_report.get('n_splits', 0)}")
                lines.append(f"- 候选总数：{firewall_report.get('n_total_candidates_tested', 0)}")
                lines.append(f"- 失败门槛触发数：{firewall_report.get('n_rejections', 0)}（1 个候选触发 {firewall_report.get('n_rejections', 0)} 道门槛）")
                rejection_breakdown = firewall_report.get("rejection_breakdown", {})
                if rejection_breakdown:
                    lines.append("- 拒绝原因分布：" + ", ".join(
                        f"{k}: {v}" for k, v in rejection_breakdown.items()
                    ))
                lines.append(f"- 封存分片：{firewall_report.get('sealed_splits', [])}")
            if hard_gate_verdict:
                verdict_status = "✅ PASS" if hard_gate_verdict.passed else "❌ FAIL"
                lines.append(f"- Hard Gate 裁决：**{verdict_status}**")
                if not hard_gate_verdict.passed:
                    lines.append(f"- 失败门槛：{hard_gate_verdict.failure_gates}")
                lines.append(f"- 通过：{hard_gate_verdict.n_passed}/{hard_gate_verdict.n_passed + hard_gate_verdict.n_failed}")
            lines.append("")
            lines.append(f"⚠️ {n_valid} 个历史事件最多只能产生候选证据。策略确认需前瞻 shadow 观察。")

    return "\n".join(lines)


def _frozen_run_config(args) -> dict:
    """Complete set of arguments/constants that can change a result."""
    return {
        "date_range": {"start": args.start, "end": args.end},
        "primary_cost_bps": args.primary_cost_bps,
        "cost_scenarios_bps": list(args.cost_scenarios),
        "observation_horizon": args.observation_horizon,
        "hold_days": args.hold_days,
        "bounce_start_threshold": BOUNCE_START_THRESHOLD,
        "bounce_end_drawdown": BOUNCE_END_DRAWDOWN,
        "retest_drawdown_threshold": RETEST_DRAWDOWN_THRESHOLD,
        "target_net_gain": TARGET_NET_GAIN,
        "stop_levels": list(STOP_LEVELS),
        "stop_rules_pre_registered": {
            "R0": "position-return stop from entry close, k-confirm → k+1-execute",
            "R1": "position-return stop from R1 entry price, k-confirm → k+1-execute",
            "R2": "position-return stop from leg1 (50%) entry price only — NOT portfolio cost-weighted",
            "R3": "position-return stop from initial entry; re-entry continues same stop params from re-entry price",
            "exit_deferral": "up to 3 trading days when exit blocked by limit-down/suspension",
        },
        "market_regime": {
            "primary_index": REGIME_PRIMARY_INDEX,
            "ma_window": REGIME_MA_WINDOW,
            "return_window": REGIME_RETURN_WINDOW,
            "eligible": sorted(ELIGIBLE_REGIMES),
        },
        "volume_diagnostics_enabled": getattr(args, "volume_diagnostics", False),
        "volume_candidate_pre_registration": {
            "name": "amount_ratio_20d_median_high_filter",
            "feature": "amount_ratio_20d_median",
            "split": "expanding_window_min_3_train_years",
            "threshold": "training_window_median",
            "action_above": "keep_R0",
            "action_at_or_below": "cash_return_0",
            "missing_feature": "keep_R0",
            "validation_cost_bps": 100,
            "candidate_count": 1,
        },
        "entry_resolution": {
            "min_components": MIN_ENTRY_COMPONENTS,
            "min_list_days": MIN_LIST_DAYS,
            "min_daily_amount_20d": MIN_AMOUNT_20D,
            "amount_unit": MIN_AMOUNT_UNIT,
        },
        "max_cluster_gap_trading_days": MAX_CLUSTER_GAP_TRADING_DAYS,
        "bootstrap_runs": args.bootstrap_runs,
        "bootstrap_ci_level": args.bootstrap_ci,
        "random_seed": args.seed,
    }


def _build_manifest(
    args,
    path_ledger,
    events,
    config_hash: str,
    input_digests: dict[str, str] | None = None,
    path_failures: list[dict] | None = None,
    tradability_audit: dict | None = None,
    upstream_manifest: dict | None = None,
) -> dict:
    input_digests = input_digests or {}
    path_failures = path_failures or []
    tradability_audit = tradability_audit or {}
    upstream_manifest = upstream_manifest or {}

    upstream_provenance = None
    if upstream_manifest:
        upstream_provenance = {
            "run_id": upstream_manifest.get("run_id", "unknown"),
            "schema": upstream_manifest.get("schema", "unknown"),
            "script_version": upstream_manifest.get("script_version", "unknown"),
            "manifest_sha256": hashlib.sha256(
                json.dumps(upstream_manifest, sort_keys=True, default=str).encode()
            ).hexdigest(),
        }

    return {
        "schema": "photoresist_panic_path_rules.v3",
        "script_version": SCRIPT_VERSION,
        "status": "RESEARCH_ONLY",
        "upstream_provenance": upstream_provenance,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "config": _frozen_run_config(args),
        "date_range": {"start": args.start, "end": args.end},
        "event_filter": "first_trigger + bull_neutral + ENTRY_RESOLVED",
        "event_boundary_note": (
            "next_event = next bull/neutral + ENTRY_RESOLVED first-trigger signal_date "
            "(NOT next raw panic gate trigger). Exit boundary is k+1 of next_event_date "
            "(trunc_date = next trading day after the signal date)."
        ),
        "n_events": len(path_ledger),
        "n_eligible_events": len(events),
        "n_path_failures": len(path_failures),
        "n_entry_resolved": sum(1 for e in events if e.entry_status == "ENTRY_RESOLVED"),
        "frozen_component_codes": {e.signal_id: e.entry_component_codes for e in events},
        "entry_resolution_digests": {
            e.signal_id: e.entry_input_digest for e in events
        },
        "entry_exclusions": {e.signal_id: e.exclusions for e in events},
        "path_failures": path_failures,
        "tradability_audit": tradability_audit,
        "inputs": {
            "core_basket": {
                "source": "photoresist_core_basket_with_gate.csv",
                "sha256": input_digests.get("core_basket", ""),
            },
            "universe": {
                "source": "photoresist_universe_snapshot.csv",
                "sha256": input_digests.get("universe", ""),
            },
            "prices": {
                "source": "data/parquet/prices_adj/",
                "loaded_frame_sha256": input_digests.get("prices", ""),
            },
            "index": {
                "source": "data/parquet/index_daily/",
                "loaded_frame_sha256": input_digests.get("index_prices", ""),
            },
            "limit_status": {
                "loaded_frame_sha256": input_digests.get("limit_status", ""),
            },
            "suspend_status": {
                "loaded_frame_sha256": input_digests.get("suspend_status", ""),
            },
            "stock_status": {
                "loaded_frame_sha256": input_digests.get("stock_status", ""),
            },
            "namechange": {
                "source": "data/parquet/namechange/",
                "loaded_frame_sha256": input_digests.get("namechange", ""),
            },
            "daily_basic": {
                "source": "data/parquet/daily_basic/",
                "loaded_frame_sha256": input_digests.get("daily_basic", ""),
            },
            "fetch_manifest": {
                "source": "data/parquet/_fetch_manifest.json",
                "sha256": input_digests.get("fetch_manifest", ""),
            },
        },
        "config_sha256": config_hash,
        "script_sha256": hashlib.sha256(
            Path(__file__).read_text(encoding="utf-8").encode()
        ).hexdigest(),
        # Audit trail: hash all source files the result depends on
        "dependency_sha256": {
            "evaluate_photoresist_panic_path_rules.py": hashlib.sha256(
                Path(__file__).read_text(encoding="utf-8").encode()
            ).hexdigest(),
            "build_photoresist_panic_events.py": hashlib.sha256(
                (ROOT / "scripts" / "build_photoresist_panic_events.py")
                .read_text(encoding="utf-8").encode()
            ).hexdigest() if (ROOT / "scripts" / "build_photoresist_panic_events.py").exists() else "MISSING",
            "outcome_tracker.py": hashlib.sha256(
                (ROOT / "live" / "photoresist_panic" / "outcome_tracker.py")
                .read_text(encoding="utf-8").encode()
            ).hexdigest() if (ROOT / "live" / "photoresist_panic" / "outcome_tracker.py").exists() else "MISSING",
            "market_utils.py": hashlib.sha256(
                (ROOT / "live" / "photoresist_panic" / "market_utils.py")
                .read_text(encoding="utf-8").encode()
            ).hexdigest() if (ROOT / "live" / "photoresist_panic" / "market_utils.py").exists() else "MISSING",
            "fetch_photoresist_data.py": hashlib.sha256(
                (ROOT / "scripts" / "fetch_photoresist_data.py")
                .read_text(encoding="utf-8").encode()
            ).hexdigest() if (ROOT / "scripts" / "fetch_photoresist_data.py").exists() else "MISSING",
            "tushare_client.py": hashlib.sha256(
                (ROOT / "data" / "tushare_client.py")
                .read_text(encoding="utf-8").encode()
            ).hexdigest() if (ROOT / "data" / "tushare_client.py").exists() else "MISSING",
            "volume_features.py": hashlib.sha256(
                (ROOT / "scripts" / "volume_features.py")
                .read_text(encoding="utf-8").encode()
            ).hexdigest() if (ROOT / "scripts" / "volume_features.py").exists() else "MISSING",
            "validation_firewall.py": hashlib.sha256(
                (ROOT / "scripts" / "validation_firewall.py")
                .read_text(encoding="utf-8").encode()
            ).hexdigest() if (ROOT / "scripts" / "validation_firewall.py").exists() else "MISSING",
            "hard_gate_checker.py": hashlib.sha256(
                (ROOT / "scripts" / "hard_gate_checker.py")
                .read_text(encoding="utf-8").encode()
            ).hexdigest() if (ROOT / "scripts" / "hard_gate_checker.py").exists() else "MISSING",
            "signal_engine.py": hashlib.sha256(
                (ROOT / "live" / "photoresist_panic" / "signal_engine.py")
                .read_text(encoding="utf-8").encode()
            ).hexdigest() if (ROOT / "live" / "photoresist_panic" / "signal_engine.py").exists() else "MISSING",
        },
        "pre_registered": True,
    }


def _validate_tradability_coverage(
    events: list,
    limit_status: pd.DataFrame | None,
    suspend_status: pd.DataFrame | None,
    stock_status: pd.DataFrame | None,
    suspend_coverage_proven: bool = False,
) -> dict:
    """Validate per-event date×stock coverage of tradability data.

    A non-empty table does NOT guarantee that every event's specific
    (entry_date, component_code) combination has a record.  This function
    computes the actual coverage matrix and returns gaps.
    """
    total_checks = 0
    limit_missing = 0
    suspend_missing = 0
    stock_missing = 0
    gap_events: list[dict] = []

    for e in events:
        if e.entry_status != "ENTRY_RESOLVED":
            continue
        entry_date = e.entry_date
        event_gaps = {"signal_id": e.signal_id, "entry_date": entry_date,
                      "missing_limit": [], "missing_suspend": [], "missing_stock": []}
        for code in e.entry_component_codes:
            code_str = str(code)
            total_checks += 1
            # Check limit_status
            if limit_status is not None and not limit_status.empty:
                lim_rows = limit_status[
                    (limit_status["ts_code"].astype(str) == code_str)
                    & (limit_status["trade_date"].astype(int) == int(entry_date))
                ]
                if lim_rows.empty:
                    limit_missing += 1
                    event_gaps["missing_limit"].append(code_str)
            else:
                limit_missing += 1
                event_gaps["missing_limit"].append(code_str)
            # Suspend is sparse. Absence of a row is valid negative evidence
            # only when the fetch manifest proves the full query completed.
            if not suspend_coverage_proven:
                suspend_missing += 1
                event_gaps["missing_suspend"].append(code_str)
            # Check stock_status
            if stock_status is not None and not stock_status.empty:
                stk_rows = stock_status[stock_status["ts_code"].astype(str) == code_str]
                if stk_rows.empty:
                    stock_missing += 1
                    event_gaps["missing_stock"].append(code_str)
            else:
                stock_missing += 1
                event_gaps["missing_stock"].append(code_str)
        if any([event_gaps["missing_limit"], event_gaps["missing_suspend"],
                event_gaps["missing_stock"]]):
            gap_events.append(event_gaps)

    return {
        "total_checks": total_checks,
        "limit_missing": limit_missing,
        "suspend_missing": suspend_missing,
        "stock_missing": stock_missing,
        "limit_coverage_pct": round((1 - limit_missing / max(total_checks, 1)) * 100, 1),
        "suspend_coverage_pct": round((1 - suspend_missing / max(total_checks, 1)) * 100, 1),
        "stock_coverage_pct": round((1 - stock_missing / max(total_checks, 1)) * 100, 1),
        "events_with_gaps": len(gap_events),
        "gap_details": gap_events[:20],  # cap for manifest size
    }


# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════
def main() -> int:
    args = parse_args()
    input_dir = Path(args.input_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Atomic output: write to staging dir, promote on success
    eval_run_id = f"eval_{datetime.now().strftime('%Y%m%dT%H%M%S')}"
    staging_dir = out_dir / f".staging_{eval_run_id}"
    staging_dir.mkdir(parents=True, exist_ok=True)
    _final_out_dir = out_dir  # preserve for promotion
    out_dir = staging_dir     # redirect all writes to staging

    config_payload = json.dumps(
        _frozen_run_config(args), sort_keys=True, ensure_ascii=False
    )
    config_hash = hashlib.sha256(config_payload.encode()).hexdigest()

    # ── Load inputs ───────────────────────────────────────────────────────
    print("=" * 60)
    print(f"Photoresist Panic Path Rules v{SCRIPT_VERSION} (PRE-REGISTERED)")
    print(f"  Range: {args.start} – {args.end}")
    print(f"  Config hash: {config_hash}")
    print("=" * 60)

    # ── Validate upstream provenance ────────────────────────────────────
    upstream_manifest = {}
    if args.upstream_manifest:
        upstream_manifest = _validate_upstream_manifest(
            Path(args.upstream_manifest), args.strict_tradability,
        )

    core_basket, universe_df = load_inputs(input_dir)
    all_codes = sorted(core_basket["ts_code"].dropna().unique().tolist()) if "ts_code" in core_basket.columns else sorted(
        set(c for c_list in core_basket.get("component_codes", []) for c in c_list)
    ) if "component_codes" in core_basket.columns else []
    if not all_codes:
        all_codes = sorted(universe_df["ts_code"].unique().tolist())
    print(f"  Codes: {all_codes}")

    h_start = int(core_basket["trade_date"].min())
    h_end = int(core_basket["trade_date"].max())
    cache_root = ROOT / "data" / "parquet"
    fetch_manifest_path = cache_root / "_fetch_manifest.json"
    fetch_manifest = FetchManifest(str(cache_root))
    limit_coverage_proven = fetch_manifest.has_coverage(
        "limit_status", h_start, h_end, all_codes
    )
    suspend_coverage_proven = fetch_manifest.has_coverage(
        "suspend_status", h_start, h_end, all_codes
    )
    namechange_coverage_proven = fetch_manifest.has_coverage(
        "namechange", 0, 99991231, all_codes
    )
    daily_basic_coverage_proven = fetch_manifest.has_coverage(
        "daily_basic", h_start, h_end, all_codes
    )

    prices = load_prices(h_start, h_end, all_codes)
    calendar = build_trading_calendar(prices)
    index_prices = load_index_prices(h_start, h_end, ["000300.SH", "931865.CSI"])
    print(f"  Prices: {len(prices)} rows, Calendar: {len(calendar)} dates")

    # Load auxiliary data for entry resolution
    limit_status = load_limit_status(h_start, h_end, all_codes)
    suspend_status = load_suspend_status(h_start, h_end, all_codes)
    stock_status = load_stock_status()
    namechange = load_namechange(all_codes)  # 股票曾用名 for PIT ST detection

    # Load daily_basic BEFORE input_digests so the manifest has correct SHA
    daily_basic = None
    if args.volume_diagnostics:
        daily_basic = load_daily_basic(h_start, h_end, all_codes)
        if daily_basic is not None and not daily_basic.empty:
            print(f"  daily_basic: {len(daily_basic)} rows, "
                  f"{daily_basic['ts_code'].nunique()} stocks")
        else:
            print("  WARNING: daily_basic unavailable — turnover features will be NaN")
        if daily_basic is None or daily_basic.empty or not daily_basic_coverage_proven:
            print(
                "FATAL: --volume-diagnostics requires complete manifest-proven "
                "daily_basic coverage.",
                file=sys.stderr,
            )
            return 1

    # ── Tradability data audit ────────────────────────────────────────────
    # Missing real tradability data forces proxy judgments (pct_chg heuristics).
    # This is NOT equivalent to real limit/suspend/ST data and WILL bias results.
    missing_tradability = []
    if limit_status is None or limit_status.empty or not limit_coverage_proven:
        missing_tradability.append("limit_status (涨跌停)")
    if suspend_status is None or suspend_status.empty or not suspend_coverage_proven:
        missing_tradability.append("suspend_status (停牌)")
    if stock_status is None or stock_status.empty:
        missing_tradability.append("stock_status (ST/上市)")
    if namechange is None or namechange.empty or not namechange_coverage_proven:
        missing_tradability.append("namechange (股票曾用名/PIT ST)")
    # Detect manifest-data mismatch: manifest claims coverage but loaded data
    # is empty.  This indicates a corrupt or incomplete cache.
    manifest_data_mismatches = []
    if limit_coverage_proven and (limit_status is None or limit_status.empty):
        manifest_data_mismatches.append("limit_status (manifest claims coverage, data is empty)")
    if suspend_coverage_proven and (suspend_status is None or suspend_status.empty):
        manifest_data_mismatches.append("suspend_status (manifest claims coverage, data is empty)")
    if namechange_coverage_proven and (namechange is None or namechange.empty):
        manifest_data_mismatches.append("namechange (manifest claims coverage, data is empty)")
    if manifest_data_mismatches:
        print("\n" + "=" * 72, file=sys.stderr)
        print("FATAL: Fetch manifest claims coverage but loaded data is empty:", file=sys.stderr)
        for m in manifest_data_mismatches:
            print(f"  - {m}", file=sys.stderr)
        print("  Re-run: python scripts/fetch_photoresist_data.py", file=sys.stderr)
        print("  Then re-run this evaluation.", file=sys.stderr)
        print("=" * 72 + "\n", file=sys.stderr)
        return 1

    if missing_tradability:
        banner = "=" * 72
        msg = (
            f"\n{banner}\n"
            f"!! WARNING: Real tradability data MISSING — using proxy judgments !!\n"
            f"   Missing: {', '.join(missing_tradability)}\n"
            f"   Proxy heuristics (pct_chg >= 9.5, etc.) are NOT equivalent to\n"
            f"   real 涨跌停 limit prices, 停牌 records, or PIT ST status.\n"
            f"   Results MAY be biased. Fetch real data with:\n"
            f"     python scripts/fetch_photoresist_data.py\n"
            f"{banner}\n"
        )
        print(msg, file=sys.stderr)
        print(msg)
        if args.strict_tradability:
            print("FATAL: --strict-tradability is set. Cannot proceed with proxy judgments.", file=sys.stderr)
            return 1

    input_digests = {
        "core_basket": _dataframe_sha256(core_basket),
        "universe": _dataframe_sha256(universe_df),
        "prices": _dataframe_sha256(prices),
        "index_prices": _dataframe_sha256(index_prices),
        "limit_status": _dataframe_sha256(limit_status),
        "suspend_status": _dataframe_sha256(suspend_status),
        "stock_status": _dataframe_sha256(stock_status),
        "namechange": _dataframe_sha256(namechange),
        "daily_basic": _dataframe_sha256(daily_basic) if daily_basic is not None else hashlib.sha256(b"NONE").hexdigest(),
        "fetch_manifest": hashlib.sha256(
            fetch_manifest_path.read_bytes() if fetch_manifest_path.exists() else b"NONE"
        ).hexdigest(),
    }
    # Record tradability completeness in manifest
    tradability_audit = {
        "limit_status_available": not (limit_status is None or limit_status.empty) and limit_coverage_proven,
        "suspend_status_available": not (suspend_status is None or suspend_status.empty) and suspend_coverage_proven,
        "stock_status_available": not (stock_status is None or stock_status.empty),
        "namechange_available": not (namechange is None or namechange.empty) and namechange_coverage_proven,
        "daily_basic_available": not (daily_basic is None or daily_basic.empty) and daily_basic_coverage_proven,
        "fetch_manifest_coverage": {
            "limit_status": limit_coverage_proven,
            "suspend_status": suspend_coverage_proven,
            "namechange": namechange_coverage_proven,
            "daily_basic": daily_basic_coverage_proven,
        },
        "using_proxy_judgments": bool(missing_tradability),
        "missing_datasets": missing_tradability,
    }

    # ── Construct Phase 0 events ─────────────────────────────────────────
    print("\n[2/6] Constructing first-trigger events (bull/neutral + ENTRY_RESOLVED)...")
    events = construct_events(
        core_basket, universe_df, prices, index_prices, calendar,
        args.start, args.end,
        limit_status=limit_status, suspend_status=suspend_status,
        stock_status=stock_status, namechange=namechange,
    )
    print(f"  Events: {len(events)}")
    if not events:
        print("  No qualifying events — writing auditable empty outputs.")
    regimes = {}
    for e in events:
        regimes[e.market_regime] = regimes.get(e.market_regime, 0) + 1
    print(f"  Regimes: {regimes}")

    # ── Validate per-event tradability coverage ──────────────────────────
    tradability_coverage = _validate_tradability_coverage(
        events, limit_status, suspend_status, stock_status,
        suspend_coverage_proven=suspend_coverage_proven,
    )
    if tradability_coverage["events_with_gaps"] > 0:
        banner = "=" * 72
        msg = (
            f"\n{banner}\n"
            f"!! Tradability coverage gaps detected !!\n"
            f"   Limit:  {tradability_coverage['limit_coverage_pct']}% coverage "
            f"({tradability_coverage['limit_missing']}/{tradability_coverage['total_checks']} missing)\n"
            f"   Suspend: {tradability_coverage['suspend_coverage_pct']}% coverage "
            f"({tradability_coverage['suspend_missing']}/{tradability_coverage['total_checks']} stocks have no records)\n"
            f"   Stock:   {tradability_coverage['stock_coverage_pct']}% coverage "
            f"({tradability_coverage['stock_missing']}/{tradability_coverage['total_checks']} missing)\n"
            f"   Events with gaps: {tradability_coverage['events_with_gaps']}\n"
        )
        if args.strict_tradability:
            # Strict mode: any gap is fatal. Print detailed gap report.
            detail_lines = ["\nMissing per event:"]
            for gap in tradability_coverage.get("gap_details", [])[:10]:
                parts = [f"  {gap['signal_id']} ({gap['entry_date']})"]
                if gap["missing_limit"]:
                    parts.append(f"limit: {gap['missing_limit']}")
                if gap["missing_suspend"]:
                    parts.append(f"suspend: {gap['missing_suspend']}")
                if gap["missing_stock"]:
                    parts.append(f"stock: {gap['missing_stock']}")
                detail_lines.append(" | ".join(parts))
            print(msg + f"   --strict-tradability is set. EVALUATION ABORTED.\n{banner}\n")
            print("\n".join(detail_lines))
            return 1
        else:
            print(msg + f"   Proxy judgments WILL be used for missing entries.\n{banner}\n")
    # Merge coverage into tradability_audit
    tradability_audit["coverage"] = {
        k: v for k, v in tradability_coverage.items() if k != "gap_details"
    }

    # ── Layer 1: Path parsing ────────────────────────────────────────────
    print("\n[3/6] Parsing event paths with frozen baskets...")
    path_results = []
    path_contexts: list[tuple[EventRecord, PathResult, np.ndarray, np.ndarray]] = []
    path_failures: list[dict] = []

    for i, event in enumerate(events):
        # Extend horizon to cover delayed entries + deferral: R1/R3 may enter up
        # to day ~observation_horizon, hold for hold_days, and defer exit up to 3
        # days.  Max path length: 60 (obs) + 1 (confirm+1) + 20 (hold) + 3 (defer)
        # = 84 trading days.  Pad to 90 for safety.
        max_defer = 3
        basket_result = build_frozen_basket_path(
            prices, event.entry_component_codes,
            event.signal_date, event.entry_date, calendar,
            args.observation_horizon + args.hold_days + max_defer + 7,  # 60+20+3+7=90
            suspend_status=suspend_status,
        )
        if basket_result is None:
            path_failures.append({
                "signal_id": event.signal_id,
                "reason": "entry_resolved_frozen_basket_invariant_failed",
            })
            continue
        basket_rets, path_dates = basket_result

        semi_map = build_semi_nav_map(path_dates, index_prices)
        sig_close, sig_low = compute_signal_anchors(
            prices, event.entry_component_codes,
            event.signal_date, event.entry_date,
        )

        next_evt = None
        for j in range(i + 1, len(events)):
            if events[j].signal_date > event.signal_date:
                next_evt = events[j].signal_date
                break

        path = parse_event_path(
            basket_rets, path_dates, semi_map,
            event.signal_date, event.entry_date,
            sig_close, sig_low,
            next_event_date=next_evt,
            observation_horizon=args.observation_horizon,
            target_gain=TARGET_NET_GAIN,
            cost_bps=args.primary_cost_bps,
        )
        path.signal_id = event.signal_id
        path.entry_component_codes = event.entry_component_codes
        path.n_entry_components = event.n_entry_components
        path.market_regime = event.market_regime
        path.next_event_signal_date = next_evt  # store for k+1 exit in trading loop
        path_results.append(path)
        path_contexts.append((event, path, basket_rets, path_dates))

    print(f"  Parsed {len(path_results)} paths")

    # Volume diagnostics run only after the R0-R3 ledger has been finalized.
    # This ordering is the structural diagnostic-only invariant.
    volume_features_list: list[VolumeFeatures] = []
    trade_ledger_without_diagnostics: pd.DataFrame | None = None
    trade_ledger_with_diagnostics: pd.DataFrame | None = None

    # ── Layer 2: Rule simulation ─────────────────────────────────────────
    print("\n[4/6] Simulating trading rules...")
    trade_rows = []
    for event, path, rets, dates in path_contexts:
        execution_context = ExecutionContext(
            prices=prices,
            component_codes=event.entry_component_codes,
            limit_status=limit_status,
            suspend_status=suspend_status,
            strict_tradability=args.strict_tradability,
        )

        # Truncation exit date: next panic fires at next_evt close →
        # earliest executable exit is next_evt + 1 (k+1, not k−1)
        next_evt_signal = path.next_event_signal_date
        trunc_date = None
        if next_evt_signal is not None:
            trunc_date = trading_day_offset(calendar, next_evt_signal, 1)

        for cost_bps in args.cost_scenarios:
            t0 = simulate_rule_r0(
                path.signal_id, event.signal_date, event.entry_date,
                rets, dates, calendar, cost_bps=cost_bps,
                hold_days=args.hold_days, trunc_date=trunc_date,
                execution_context=execution_context,
                path_result=path,
            )
            t0.path_type = path.path_type; t0.market_regime = event.market_regime
            trade_rows.append(_flatten_trade(t0))

            for rule_fn, rid in [(simulate_rule_r1, "R1"), (simulate_rule_r2, "R2"), (simulate_rule_r3, "R3")]:
                t = rule_fn(
                    path.signal_id, event.signal_date, event.entry_date,
                    path, rets, dates, calendar, cost_bps=cost_bps,
                    hold_days=args.hold_days, trunc_date=trunc_date,
                    execution_context=execution_context,
                )
                t.path_type = path.path_type; t.market_regime = event.market_regime
                trade_rows.append(_flatten_trade(t))

    trade_ledger = pd.DataFrame(trade_rows, columns=RuleTrade.columns())
    print(f"  Trade rows: {len(trade_ledger)}")

    if args.volume_diagnostics:
        trade_ledger_without_diagnostics = trade_ledger.copy(deep=True)
        print("\n[4.5/6] Computing volume/turnover diagnostic features...")
        sig_date_map = {e.signal_id: e.signal_date for e in events}
        for path in path_results:
            if path.insufficient_data:
                continue
            signal_date = sig_date_map.get(path.signal_id, path.entry_date)
            vf = compute_volume_features(
                signal_id=path.signal_id,
                signal_date=signal_date,
                component_codes=path.entry_component_codes,
                prices=prices,
                daily_basic=daily_basic,
                limit_status=limit_status,
            )
            path.volume_features = vf
            volume_features_list.append(vf)
        n_turnover_available = sum(
            1 for vf in volume_features_list
            if "turnover_rate_f" not in vf.features_unavailable
        )
        print(
            f"  Volume features computed: {len(volume_features_list)} events, "
            f"{n_turnover_available} with turnover data"
        )
        # Independent deep snapshot captured after diagnostics.  The trade
        # ledger itself is never passed into feature computation.
        trade_ledger_with_diagnostics = trade_ledger.copy(deep=True)

    # ── Statistics ───────────────────────────────────────────────────────
    print("\n[5/6] Computing statistics...")
    paired = compute_paired_differences(trade_ledger, primary_cost=args.primary_cost_bps)
    print(f"  Paired events: {len(paired)}")

    # ── Volume diagnostics: firewall + hard-gate validation ───────────────
    firewall_report: dict = {}
    hard_gate_verdict: HardGateResult | None = None
    if args.volume_diagnostics and volume_features_list:
        print("\n[5.5/6] Running validation firewall with train/validation splits...")
        # Frozen Phase-A candidate (the only candidate tested): keep the R0
        # trade when event-day amount ratio is above the training-only median;
        # otherwise remain in cash with return 0. Missing features conservatively
        # leave R0 unchanged and are never excluded from the return denominator.
        candidate_name = "amount_ratio_20d_median_high_filter"
        validation_cost_bps = 100
        r0_returns = trade_ledger[
            (trade_ledger["rule_id"] == "R0")
            & (trade_ledger["cost_bps"] == validation_cost_bps)
        ]
        net_return_map: dict[str, float] = {}
        feature_map: dict[str, float] = {}
        for __, row in r0_returns.iterrows():
            sid = str(row["signal_id"])
            if row["status"] in ("COMPLETED", "STOPPED_OUT", "NO_TRADE", "TRUNCATED_EXIT"):
                r = row["net_return"]
                if pd.notna(r):
                    net_return_map[sid] = float(r)
        for vf in volume_features_list:
            v = vf.amount_ratio_20d_median
            if np.isfinite(v) and vf.signal_id in net_return_map:
                feature_map[vf.signal_id] = v

        # Group events by year. Each event appears in exactly one OOS year.
        events_by_year: dict[int, list[str]] = {}
        for e in events:
            yr = e.signal_date // 10000
            events_by_year.setdefault(yr, []).append(e.signal_id)

        # ── Persistent candidate registry (cross-run) ───────────────────
        registry_path = str(out_dir / "_candidate_registry.json")
        registry = CandidateRegistry(registry_path)

        candidate_hash = _candidate_identity_hash(
            feature_name="amount_ratio_20d_median_high_filter",
            direction="retain_if_high",
            threshold_method="median_split",
            missing_strategy="keep_R0",
            code_sha256=config_hash,
            config_sha256=config_hash,
        )
        valid_years = sorted(events_by_year.keys())
        sealed, reason = registry.is_sealed(candidate_hash, valid_years)
        if sealed:
            print(f"  ERROR: candidate registry sealed: {reason}")
            print("  Cannot re-test on already-validated years. "
                  "Add new (untested) data years to proceed.")
            firewall_report = {"sealed": True, "reason": reason}
            hard_gate_verdict = None
            candidate_status_sealed = "SEALED_PREVIOUSLY_VALIDATED"
            # fall through to skip OOS but still produce R0-R3 reports
            splits = []
        else:
            firewall = ValidationFirewall()
        splits = expanding_window_split(events_by_year, min_train_years=3)
        if not splits:
            print("  WARNING: insufficient years for expanding-window splits "
                  "(need ≥4 years).  OOS validation skipped — "
                  "LOYO is NOT a valid temporal holdout.")
            firewall_report = firewall.summary()
            firewall_report["insufficient_sample_for_temporal_oos"] = True
            splits = []  # explicitly empty

        oos_rows: list[dict] = []
        usable_splits = 0

        for split in splits:
            # Pair feature and return by signal_id; independent list filters
            # can silently misalign the arrays when a feature is missing.
            train_ids = [
                sid for sid in split.train_events
                if sid in feature_map and sid in net_return_map
            ]
            train_features = np.array(
                [feature_map[sid] for sid in train_ids], dtype=float
            )
            if len(train_ids) < 5:
                split.set_threshold("status", "insufficient_training_data")
                split.validate({
                    "status": "INSUFFICIENT_TRAINING_DATA",
                    "n_train_paired": len(train_ids),
                    "oos_rows": [],
                })
                firewall.add_split(split)
                continue

            threshold = float(np.median(train_features))
            split.set_threshold("feature_median", threshold)
            split.set_threshold("source", "training_only")
            split.set_threshold("direction", "keep_if_feature_above_median")
            split.set_threshold("missing_feature_policy", "keep_baseline_trade")

            split_rows: list[dict] = []
            for sid in split.valid_events:
                if sid not in net_return_map:
                    continue
                baseline_return = float(net_return_map[sid])
                feature_value = feature_map.get(sid)
                if feature_value is None:
                    selected = None
                    candidate_return = baseline_return
                else:
                    selected = bool(feature_value > threshold)
                    candidate_return = baseline_return if selected else 0.0
                split_rows.append({
                    "signal_id": sid,
                    "valid_year": split.valid_year,
                    "feature_value": float(feature_value) if feature_value is not None else None,
                    "threshold": threshold,
                    "selected": selected,
                    "baseline_return": baseline_return,
                    "candidate_return": float(candidate_return),
                })

            if len(split_rows) < 2:
                split.set_threshold("status", "insufficient_validation_data")
                split.validate({
                    "status": "INSUFFICIENT_VALIDATION_DATA",
                    "n_train_paired": len(train_ids),
                    "n_valid_returns": len(split_rows),
                    "oos_rows": split_rows,
                })
                firewall.add_split(split)
                continue

            split.validate({
                "status": "SEALED_OOS_RESULTS",
                "n_train_paired": len(train_ids),
                "n_valid_returns": len(split_rows),
                "n_valid_with_feature": sum(
                    row["feature_value"] is not None for row in split_rows
                ),
                "oos_rows": split_rows,
            })
            firewall.add_split(split)
            oos_rows.extend(split_rows)
            usable_splits += 1

        baseline_oos = np.array(
            [row["baseline_return"] for row in oos_rows], dtype=float
        )
        candidate_oos = np.array(
            [row["candidate_return"] for row in oos_rows], dtype=float
        )
        feature_oos = np.array(
            [
                row["feature_value"]
                if row["feature_value"] is not None else np.nan
                for row in oos_rows
            ],
            dtype=float,
        )

        returns_by_year: dict[int, tuple[np.ndarray, np.ndarray]] = {}
        for year in sorted({row["valid_year"] for row in oos_rows}):
            year_rows = [row for row in oos_rows if row["valid_year"] == year]
            returns_by_year[year] = (
                np.array([row["baseline_return"] for row in year_rows], dtype=float),
                np.array([row["candidate_return"] for row in year_rows], dtype=float),
            )

        checker = HardGateChecker(
            candidate_name,
            firewall_sealed=(
                bool(splits)
                and usable_splits > 0
                and all(split.is_sealed() for split in splits)
            ),
        )
        checker.check_diagnostic_only(
            trade_ledger_with=trade_ledger_with_diagnostics,
            trade_ledger_without=trade_ledger_without_diagnostics,
        )
        checker.check_single_candidate([candidate_name])
        checker.check_monotonic_relationship(feature_oos, baseline_oos)
        checker.check_multiple_testing_tally(1)
        checker.check_threshold_from_training("training")
        checker.check_viewed_once()
        checker.check_year_consistency(returns_by_year)
        checker.check_median_not_worse(
            float(np.median(baseline_oos)) if len(baseline_oos) else np.nan,
            float(np.median(candidate_oos)) if len(candidate_oos) else np.nan,
        )
        checker.check_left_tail_not_wider(baseline_oos, candidate_oos)
        checker.check_top3_not_dominant(baseline_oos, candidate_oos)
        checker.check_jackknife_stable(baseline_oos, candidate_oos)
        checker.check_cost_100bp_improves(baseline_oos, candidate_oos)
        hard_gate_verdict = checker.verdict()

        if hard_gate_verdict.passed:
            firewall.record_pass(candidate_name)
            status = "PASSED"
        else:
            for gate_name in hard_gate_verdict.failure_gates:
                firewall.record_rejection(
                    candidate_name,
                    gate_name,
                    f"pooled_oos_n={len(oos_rows)}",
                    "pooled_oos",
                )
            status = "REJECTED"

        # Persist to cross-run registry
        validated_split_records = []
        for s in firewall.splits:
            if s.is_sealed():
                validated_split_records.append({
                    "name": s.name,
                    "valid_year": s.valid_year,
                    "results_sha256": s._results_hash,
                    "sealed_at": s._sealed_at,
                })
        registry.register(candidate_hash, candidate_name, status,
                          validated_split_records)

        firewall_report = firewall.summary()
        firewall_report["oos_summary"] = {
            "candidate": candidate_name,
            "n_usable_splits": usable_splits,
            "n_oos_events": len(oos_rows),
            "n_oos_with_feature": int(np.isfinite(feature_oos).sum()),
            "validation_cost_bps": validation_cost_bps,
            "baseline_mean": float(np.mean(baseline_oos)) if len(baseline_oos) else None,
            "candidate_mean": float(np.mean(candidate_oos)) if len(candidate_oos) else None,
            "baseline_returns_sha256": hashlib.sha256(baseline_oos.tobytes()).hexdigest(),
            "candidate_returns_sha256": hashlib.sha256(candidate_oos.tobytes()).hexdigest(),
        }
        print(
            f"  Firewall: {len(splits)} sealed splits, 1 candidate, "
            f"{len(oos_rows)} pooled OOS events"
        )
        if hard_gate_verdict.passed:
            print("  Hard-gate: ALL gates PASSED")
        else:
            print(
                f"  Hard-gate: FAIL ({hard_gate_verdict.n_failed} gates failed: "
                f"{hard_gate_verdict.failure_gates})"
            )

    # ── Outputs ──────────────────────────────────────────────────────────
    print("\n[6/6] Writing outputs...")
    path_frame = pd.DataFrame(
        [asdict(p) for p in path_results], columns=PathResult.columns()
    )
    path_frame.to_csv(out_dir / "photoresist_event_path_ledger.csv", index=False, encoding="utf-8-sig")
    trade_ledger.to_csv(out_dir / "photoresist_rule_trade_ledger.csv", index=False, encoding="utf-8-sig")

    # Write volume feature ledger if diagnostics enabled
    if args.volume_diagnostics and volume_features_list:
        vf_frame = pd.DataFrame([asdict(vf) for vf in volume_features_list],
                                columns=VolumeFeatures.columns())
        vf_frame.to_csv(out_dir / "photoresist_volume_feature_ledger.csv",
                        index=False, encoding="utf-8-sig")
        print(f"  Volume feature ledger: {len(vf_frame)} rows")

        firewall_artifact = {
            "generated_at": datetime.now().isoformat(),
            "candidate_definition": {
                "name": "amount_ratio_20d_median_high_filter",
                "feature": "amount_ratio_20d_median",
                "threshold": "median of each training window only",
                "action_above_threshold": "keep R0 trade",
                "action_at_or_below_threshold": "cash return 0",
                "missing_feature_policy": "keep R0 trade",
                "number_of_candidates": 1,
            },
            "diagnostic_only_ledger_sha256": {
                "before_features": _dataframe_sha256(
                    trade_ledger_without_diagnostics
                ),
                "after_features": _dataframe_sha256(
                    trade_ledger_with_diagnostics
                ),
            },
            "firewall": firewall_report,
            "hard_gate": asdict(hard_gate_verdict) if hard_gate_verdict else None,
        }
        firewall_path = out_dir / "photoresist_volume_validation_firewall.json"
        firewall_path.write_text(
            json.dumps(firewall_artifact, indent=2, ensure_ascii=False, default=_json_default),
            encoding="utf-8",
        )

    report = generate_report(
        path_frame, trade_ledger, paired, events,
        start=args.start, end=args.end,
        primary_cost=args.primary_cost_bps,
        cost_scenarios=args.cost_scenarios,
        bootstrap_runs=args.bootstrap_runs,
        bootstrap_ci_level=args.bootstrap_ci,
        seed=args.seed,
        config_hash=config_hash,
        volume_features_list=volume_features_list if args.volume_diagnostics else [],
        firewall_report=firewall_report,
        hard_gate_verdict=hard_gate_verdict,
    )
    (out_dir / "photoresist_path_rules_report.md").write_text(report, encoding="utf-8")

    manifest = _build_manifest(
        args, path_frame, events, config_hash,
        input_digests=input_digests,
        path_failures=path_failures,
        tradability_audit=tradability_audit,
        upstream_manifest=upstream_manifest,
    )
    # Attach volume diagnostics metadata
    if args.volume_diagnostics and volume_features_list:
        candidate_status = candidate_status_sealed if 'candidate_status_sealed' in dir() else (
            "PASSED_OOS_HARD_GATES"
            if hard_gate_verdict and hard_gate_verdict.passed
            else "REJECTED_OOS_HARD_GATES"
        )
        manifest["volume_diagnostics"] = {
            "phase": "A — diagnostic only",
            "n_events_with_features": len(volume_features_list),
            "turnover_coverage_mean": float(np.mean([
                vf.turnover_coverage for vf in volume_features_list
            ])) if volume_features_list else None,
            "amount_coverage_mean": float(np.mean([
                vf.amount_coverage for vf in volume_features_list
            ])) if volume_features_list else None,
            "features_unavailable_summary": _count_feature_unavailable(volume_features_list),
            "candidate_status": candidate_status,
            "candidate_name": "amount_ratio_20d_median_high_filter",
            "n_candidates_tested": registry.n_unique_candidates(),
            "trade_ledger_before_sha256": _dataframe_sha256(
                trade_ledger_without_diagnostics
            ),
            "trade_ledger_after_sha256": _dataframe_sha256(
                trade_ledger_with_diagnostics
            ),
            "firewall_artifact": "photoresist_volume_validation_firewall.json",
            "firewall_artifact_sha256": hashlib.sha256(
                (out_dir / "photoresist_volume_validation_firewall.json").read_bytes()
            ).hexdigest(),
            "hard_gate_passed": bool(
                hard_gate_verdict and hard_gate_verdict.passed
            ),
            "note": "Candidate is evaluated OOS only; R0-R3 ledgers remain unchanged.",
        }
    (out_dir / "photoresist_path_rules_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, default=_json_default), encoding="utf-8",
    )

    # ── Summary ──────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    if not path_frame.empty:
        dist = path_frame["path_type"].value_counts()
        for pt in ["NO_BOUNCE", "BOUNCE_NO_RETEST", "BOUNCE_THEN_FAIL", "W_RECOVERY", "RIGHT_CENSORED"]:
            count = dist.get(pt, 0)
            if count > 0:
                print(f"  {pt}: {count}")
    if not paired.empty:
        for rule in ["R1", "R2", "R3"]:
            dc = f"delta_{rule}_R0"
            if dc in paired.columns:
                d = paired[dc].dropna()
                if len(d) > 0:
                    print(f"  {rule}-R0 ({args.primary_cost_bps}bp): mean={d.mean():.4f} n={len(d)}")

    # ── Atomic promotion: staging → final ───────────────────────────────
    import shutil
    import stat as _stat

    (_final_out_dir / "_SUCCESS").write_text(
        json.dumps({
            "run_id": eval_run_id,
            "completed_at": datetime.now().isoformat(),
            "script_version": SCRIPT_VERSION,
            "n_outputs": len(list(staging_dir.iterdir())),
        }, indent=2),
        encoding="utf-8",
    )

    # Move files from staging to final, overwriting previous run
    for src_path in staging_dir.iterdir():
        if src_path.is_file():
            dst_path = _final_out_dir / src_path.name
            # On Windows, ensure destination is writable
            if dst_path.exists():
                dst_path.chmod(_stat.S_IWRITE)
            shutil.move(str(src_path), str(dst_path))
    staging_dir.rmdir()
    print(f"\n  Outputs promoted: {staging_dir.name} → {_final_out_dir}")

    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

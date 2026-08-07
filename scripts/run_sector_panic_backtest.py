"""Run the frozen panic-repair strategy across the three sector contracts.

This is the sector-specific Phase 4/5 entry point.  It deliberately keeps the
index universe and signal benchmark dynamic; the photoresist evaluator is not
used because its semiconductor-only assumptions would contaminate these
results.

Examples
--------
python scripts/run_sector_panic_backtest.py --config configs/sector_panic/nonferrous.yaml
python scripts/run_sector_panic_backtest.py --config configs/sector_panic/new_energy.yaml --config configs/sector_panic/lithium_battery.yaml
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sector_panic.backtest import (  # noqa: E402
    active_codes,
    annual_trade_returns,
    assign_sample_split,
    build_frozen_path,
    build_pit_universe_from_weights,
    build_signal_frame,
    cluster_first_triggers,
    simulate_rule,
    summarize_trade_ledger,
)
from sector_panic.config import load_config  # noqa: E402
_BUILDER_IMPORT_ERROR = None
try:  # Keep --help and pure unit imports usable without a parquet runtime.
    from scripts.build_photoresist_panic_events import (  # noqa: E402
        _is_at_limit,
        build_basket_daily,
        filter_eligible_stocks,
        is_suspended,
        load_daily_basic,
        load_index_prices,
        load_limit_status,
        load_namechange,
        load_prices,
        load_stock_status,
        load_suspend_status,
    )
except ImportError as exc:  # pragma: no cover - depends on host DLL policy
    _BUILDER_IMPORT_ERROR = exc


def _ensure_builder_imports() -> None:
    if _BUILDER_IMPORT_ERROR is not None:
        raise RuntimeError(
            "sector backtest requires a working pandas parquet engine; "
            "the host rejected the pyarrow extension DLL"
        ) from _BUILDER_IMPORT_ERROR


SECTOR_CONFIGS = [
    ROOT / "configs" / "sector_panic" / "nonferrous.yaml",
    ROOT / "configs" / "sector_panic" / "new_energy.yaml",
    ROOT / "configs" / "sector_panic" / "lithium_battery.yaml",
]
DEFAULT_OUT_DIR = ROOT / "outputs" / "analysis" / "sector_panic"
DATA_PREPARATION_MANIFEST = DEFAULT_OUT_DIR / "data_preparation_manifest.json"
INDEX_WEIGHT_DIR = ROOT / "data" / "parquet" / "index_weight"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", action="append", dest="configs", default=None,
        help="Sector YAML. Repeat for multiple sectors; default is all three formal pools.",
    )
    parser.add_argument("--start", type=int, default=20170101)
    parser.add_argument("--end", type=int, default=20260804)
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument(
        "--runtime-data-dir", default=None,
        help="Optional CSV runtime dataset produced by fetch_sector_panic_runtime_data.py.",
    )
    parser.add_argument(
        "--strict-tradability", action="store_true",
        help="Fail rather than use a proxy when a tradability source is incomplete.",
    )
    parser.add_argument(
        "--path-horizon", type=int, default=0,
        help="Override the frozen-path horizon for every trade. 0 keeps the "
             "default max(hold_days + 8, 28). Used by the hold-period "
             "sensitivity study to simulate all arms on a common horizon.",
    )
    return parser.parse_args()


def _read_partitioned(path: Path, start: int | None = None, end: int | None = None) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    chunks = []
    for parquet_path in sorted(path.rglob("*.parquet")):
        try:
            frame = pd.read_parquet(parquet_path)
        except ImportError as exc:
            raise RuntimeError(
                "cannot read prepared parquet data: the installed pyarrow "
                "extension was blocked by the host application-control policy"
            ) from exc
        if "trade_date" in frame.columns:
            dates = pd.to_numeric(frame["trade_date"], errors="coerce")
            if start is not None:
                frame = frame.loc[dates >= int(start)]
            if end is not None:
                frame = frame.loc[dates <= int(end)]
        if not frame.empty:
            chunks.append(frame)
    if not chunks:
        return pd.DataFrame()
    frame = pd.concat(chunks, ignore_index=True)
    keys = [key for key in ("index_code", "ts_code", "con_code", "trade_date") if key in frame.columns]
    if keys:
        frame = frame.drop_duplicates(keys, keep="last")
    return frame.reset_index(drop=True)


def _load_weights(index_codes: list[str], start: int, end: int) -> pd.DataFrame:
    # Month-end snapshots are the only index membership evidence accepted by
    # the Phase 0 contract.  Reading the cache once also prevents code-level
    # request loops from changing the PIT pool between sectors.
    weights = _read_partitioned(INDEX_WEIGHT_DIR, start=start, end=end)
    if weights.empty:
        raise RuntimeError(f"no index_weight parquet under {INDEX_WEIGHT_DIR}")
    if "con_code" in weights.columns and "ts_code" not in weights.columns:
        weights = weights.rename(columns={"con_code": "ts_code"})
    if "ts_code" not in weights.columns:
        raise RuntimeError("index_weight cache has neither ts_code nor con_code")
    weights["index_code"] = weights["index_code"].astype(str)
    return weights[weights["index_code"].isin(set(index_codes))].copy()


def _read_runtime_table(runtime_dir: Path, name: str) -> pd.DataFrame:
    for suffix in (".csv.gz", ".csv"):
        path = runtime_dir / f"{name}{suffix}"
        if path.exists():
            return pd.read_csv(path, low_memory=False)
    return pd.DataFrame()


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _status_sources(
    limit_status: pd.DataFrame | None,
    suspend_status: pd.DataFrame | None,
    stock_status: pd.DataFrame | None,
    namechange: pd.DataFrame | None,
    limit_status_missing_rows: int = 0,
) -> tuple[list[str], dict]:
    missing = []
    if limit_status is None or limit_status.empty:
        missing.append("limit_status")
    if suspend_status is None or suspend_status.empty:
        missing.append("suspend_status")
    if stock_status is None or stock_status.empty:
        missing.append("stock_status")
    if namechange is None or namechange.empty:
        missing.append("namechange")
    audit = {
        "limit_status": "exact" if limit_status is not None and not limit_status.empty else "proxy",
        "suspend_status": "exact" if suspend_status is not None and not suspend_status.empty else "proxy",
        "stock_status": "exact" if stock_status is not None and not stock_status.empty else "unavailable",
        "namechange": "exact" if namechange is not None and not namechange.empty else "unavailable",
        "using_proxy_judgments": bool(missing),
        "missing": missing,
        "limit_status_missing_rows": int(limit_status_missing_rows),
    }
    if int(limit_status_missing_rows) > 0:
        # A non-empty table is not sufficient evidence of full coverage:
        # the runtime builder records historical BSE rows that are absent
        # from Tushare's limit-list endpoint.  Those rows fall back to the
        # documented pct_chg proxy and must be visible in the audit.
        audit["limit_status"] = "partial_proxy"
        audit["using_proxy_judgments"] = True
        audit["limit_status_missing_rows"] = int(limit_status_missing_rows)
        missing.append(f"limit_status_rows:{int(limit_status_missing_rows)}")
    return missing, audit


def _count_runtime_limit_gaps(
    prices: pd.DataFrame,
    limit_status: pd.DataFrame | None,
    weight_codes: list[str],
    runtime_manifest: dict,
) -> int:
    """Count limit-list gaps affecting this sector's PIT price panel."""
    global_missing = int(runtime_manifest.get("limit_status_missing_rows", 0))
    if global_missing <= 0:
        return 0
    by_board = runtime_manifest.get("limit_status_missing_by_board")
    if not isinstance(by_board, dict):
        return global_missing
    boards = {
        str(board).upper()
        for board, count in by_board.items()
        if int(count or 0) > 0
    }
    affected_codes = [
        str(code) for code in weight_codes
        if any(str(code).upper().endswith(board) for board in boards)
    ]
    if not affected_codes or prices.empty or limit_status is None or limit_status.empty:
        return 0
    required = {"ts_code", "trade_date"}
    if not required.issubset(prices.columns) or not required.issubset(limit_status.columns):
        return global_missing
    expected = prices.loc[
        prices["ts_code"].astype(str).isin(affected_codes),
        ["ts_code", "trade_date"],
    ].copy()
    observed = limit_status.loc[
        limit_status["ts_code"].astype(str).isin(affected_codes),
        ["ts_code", "trade_date"],
    ].copy()
    expected["trade_date"] = pd.to_numeric(expected["trade_date"], errors="coerce")
    observed["trade_date"] = pd.to_numeric(observed["trade_date"], errors="coerce")
    expected = expected.dropna().drop_duplicates()
    observed = observed.dropna().drop_duplicates()
    if expected.empty:
        return 0
    merged = expected.merge(observed, on=["ts_code", "trade_date"], how="left", indicator=True)
    return int((merged["_merge"] == "left_only").sum())


def _suspended_keys(suspend_status: pd.DataFrame | None) -> set[tuple[str, int]]:
    if suspend_status is None or suspend_status.empty or "ts_code" not in suspend_status.columns:
        return set()
    date_column = "trade_date" if "trade_date" in suspend_status.columns else "suspend_date"
    if date_column not in suspend_status.columns:
        return set()
    frame = suspend_status[["ts_code", date_column]].copy()
    frame[date_column] = pd.to_numeric(frame[date_column], errors="coerce")
    return {
        (str(code), int(date))
        for code, date in zip(frame["ts_code"], frame[date_column])
        if pd.notna(date)
    }


def _entry_codes(
    universe: pd.DataFrame,
    signal_date: int,
    entry_date: int,
    prices: pd.DataFrame,
    calendar: np.ndarray,
    eligibility: dict,
    limit_status: pd.DataFrame | None,
    suspend_status: pd.DataFrame | None,
    stock_status: pd.DataFrame | None,
    namechange: pd.DataFrame | None,
    min_components: int,
    eligible_by_date: dict[int, list[str]] | None = None,
    suspended_by_date: dict[int, set[str]] | None = None,
) -> tuple[list[str], dict[str, str]]:
    codes = active_codes(universe, signal_date)
    if not codes:
        return [], {"__BASKET__": "no_pit_membership"}
    if eligible_by_date is not None:
        included = sorted(set(codes) & set(eligible_by_date.get(int(signal_date), [])))
        if suspended_by_date is not None:
            included = [
                code for code in included
                if code not in suspended_by_date.get(int(entry_date), set())
            ]
    else:
        event_prices = prices[
            (prices["trade_date"] == int(signal_date))
            & prices["ts_code"].astype(str).isin(codes)
        ].copy()
        if event_prices.empty:
            return [], {"__BASKET__": "no_event_prices"}
        eligible = filter_eligible_stocks(
            day_prices=event_prices,
            prices=prices,
            trade_date=int(signal_date),
            calendar=calendar,
            eligibility=eligibility,
            limit_status=limit_status,
            suspend_status=suspend_status,
            stock_status=stock_status,
            namechange=namechange,
            exec_date=int(entry_date),
        )
        included = sorted(eligible["ts_code"].astype(str).unique().tolist())
    # The frozen path requires an entry close for every included component.
    entry_prices = prices[
        (prices["trade_date"] == int(entry_date))
        & prices["ts_code"].astype(str).isin(included)
    ]
    included = sorted(
        code for code in included
        if code in set(entry_prices["ts_code"].astype(str))
    )
    exclusions = {
        code: "entry_price_missing"
        for code in sorted(set(codes) - set(included))
    }
    if len(included) < int(min_components):
        exclusions["__BASKET__"] = f"only_{len(included)}_components"
        return [], exclusions
    return included, exclusions


def _exit_checker(
    codes: list[str],
    prices: pd.DataFrame,
    limit_status: pd.DataFrame | None,
    suspend_status: pd.DataFrame | None,
):
    def executable(trade_date: int) -> bool:
        for code in codes:
            if is_suspended(code, int(trade_date), suspend_status, prices):
                return False
            is_limit_down, _ = _is_at_limit(
                code, int(trade_date), "down", limit_status, prices
            )
            if is_limit_down:
                return False
        return True
    return executable


def _regime_map(parent_index: pd.DataFrame) -> dict[int, str]:
    frame = parent_index[["trade_date", "close"]].copy().sort_values("trade_date")
    frame["ma120"] = frame["close"].rolling(120, min_periods=60).mean()
    frame["ret60"] = frame["close"].pct_change(60)
    result = {}
    for row in frame.itertuples(index=False):
        if pd.isna(row.ma120) or pd.isna(row.ret60):
            result[int(row.trade_date)] = "unknown"
        elif row.close > row.ma120 and row.ret60 > 0:
            result[int(row.trade_date)] = "bull"
        elif row.close < row.ma120 and row.ret60 < 0:
            result[int(row.trade_date)] = "bear"
        else:
            result[int(row.trade_date)] = "neutral"
    return result


def _build_efficient_basket(
    prices: pd.DataFrame,
    universe: pd.DataFrame,
    calendar: np.ndarray,
    eligibility: dict,
    max_single_weight: float,
    min_components: int,
    limit_status: pd.DataFrame | None,
    suspend_status: pd.DataFrame | None,
    stock_status: pd.DataFrame | None,
    namechange: pd.DataFrame | None,
) -> tuple[pd.DataFrame, dict[int, list[str]], dict[int, set[str]]]:
    """Vectorized equivalent of the shared basket eligibility calculation."""
    panel = prices.copy()
    panel["ts_code"] = panel["ts_code"].astype(str)
    panel["trade_date"] = pd.to_numeric(panel["trade_date"], errors="raise").astype(int)
    panel = panel.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)
    calendar = np.asarray(sorted(set(int(value) for value in calendar)), dtype=int)
    calendar_position = {int(date): position for position, date in enumerate(calendar)}

    # Resolve the PIT membership interval with a backward as-of join.  A
    # month-end row cannot become active until its effective_start.
    membership = universe[["ts_code", "effective_start", "effective_end"]].copy()
    membership["ts_code"] = membership["ts_code"].astype(str)
    membership["effective_start"] = pd.to_numeric(membership["effective_start"], errors="raise").astype(int)
    membership = membership.sort_values(["effective_start", "ts_code"])
    panel = pd.merge_asof(
        panel.sort_values(["trade_date", "ts_code"]),
        membership,
        by="ts_code", left_on="trade_date", right_on="effective_start",
        direction="backward",
    )
    panel["pit_member"] = (
        panel["effective_start"].notna()
        & (panel["trade_date"] <= panel["effective_end"])
    )
    panel = panel.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)

    # Listing age from stock_basic.list_date, with first observed price as a
    # conservative fallback for metadata gaps.
    first_price = panel.groupby("ts_code")["trade_date"].transform("min")
    list_date_map = {}
    if stock_status is not None and not stock_status.empty:
        for row in stock_status[["ts_code", "list_date"]].dropna().itertuples(index=False):
            try:
                list_date_map[str(row.ts_code)] = int(row.list_date)
            except (TypeError, ValueError):
                continue
    list_positions = {
        code: int(np.searchsorted(calendar, date, side="right") - 1)
        for code, date in list_date_map.items()
    }
    panel_position = panel["trade_date"].map(calendar_position).fillna(-1).astype(int)
    fallback_position = first_price.map(calendar_position).fillna(-1).astype(int)
    list_position = panel["ts_code"].map(list_positions)
    list_position = list_position.fillna(fallback_position)
    panel["listing_age"] = panel_position - list_position + 1

    panel["amount"] = pd.to_numeric(panel.get("amount"), errors="coerce")
    panel["amount_avg_20d"] = panel.groupby("ts_code")["amount"].transform(
        lambda values: values.rolling(20, min_periods=10).mean()
    )
    panel["amount_ratio_20d"] = panel["amount"] / panel["amount_avg_20d"]

    suspended = _suspended_keys(suspend_status)
    panel_keys = list(zip(panel["ts_code"], panel["trade_date"]))
    panel["suspended"] = [key in suspended for key in panel_keys]

    # Resolve exact limit prices where present; missing historical board rows
    # use the same documented pct_chg proxy as the shared helper.
    panel["limit_down"] = False
    if limit_status is not None and not limit_status.empty:
        limit_frame = limit_status.copy()
        limit_frame["ts_code"] = limit_frame["ts_code"].astype(str)
        limit_frame["trade_date"] = pd.to_numeric(limit_frame["trade_date"], errors="coerce").astype(int)
        keep = [column for column in ["ts_code", "trade_date", "down_limit"] if column in limit_frame.columns]
        panel = panel.merge(limit_frame[keep], on=["ts_code", "trade_date"], how="left")
    else:
        panel["down_limit"] = np.nan
    code_text = panel["ts_code"].astype(str)
    tick = np.where(code_text.str.startswith(("300", "688")), 0.001, 0.01)
    close = pd.to_numeric(panel["close"], errors="coerce").to_numpy(dtype=float)
    down_limit = pd.to_numeric(panel["down_limit"], errors="coerce").to_numpy(dtype=float)
    exact = np.isfinite(down_limit) & np.isfinite(close) & (down_limit > 0)
    exact &= np.abs(close - down_limit) <= tick + 0.005
    pct = pd.to_numeric(panel.get("pct_chg"), errors="coerce").to_numpy(dtype=float)
    proxy_threshold = np.where(
        code_text.str.startswith("300") & (panel["trade_date"].to_numpy() >= 20200824)
        | code_text.str.startswith("688"), -19.5, -9.5
    )
    panel["limit_down"] = exact | (~np.isfinite(down_limit) & (pct <= proxy_threshold))

    # PIT ST intervals from namechange.  This loop is over the small metadata
    # table, not over every price row, and produces an O(1) key lookup below.
    st_keys: set[tuple[str, int]] = set()
    if namechange is not None and not namechange.empty:
        nc = namechange.copy()
        nc["ts_code"] = nc["ts_code"].astype(str)
        for code, rows in nc.groupby("ts_code"):
            for row in rows.itertuples(index=False):
                name = str(getattr(row, "name", "")).upper()
                if "ST" not in name:
                    continue
                try:
                    start_date = int(getattr(row, "start_date"))
                except (TypeError, ValueError):
                    continue
                try:
                    end_date = int(getattr(row, "end_date"))
                except (TypeError, ValueError):
                    end_date = 20991231
                positions = np.searchsorted(calendar, [start_date, end_date], side="left")
                for date in calendar[int(positions[0]) : int(positions[1]) + 1]:
                    st_keys.add((str(code), int(date)))
    panel["st"] = [(code, date) in st_keys for code, date in zip(panel["ts_code"], panel["trade_date"])]

    min_list_days = float(eligibility.get("min_list_days", 120))
    min_amount = float(eligibility.get("min_daily_amount_20d", 1.0e8))
    amount_unit = str(eligibility.get("amount_unit", "cny")).lower()
    if amount_unit in {"thousand_cny", "thousand_yuan", "k_cny"}:
        min_amount /= 1000.0
    elif amount_unit in {"wan_cny", "wan_yuan"}:
        min_amount /= 10000.0
    panel["eligible"] = (
        panel["pit_member"]
        & (panel["listing_age"].isna() | (panel["listing_age"] >= min_list_days))
        & (panel["amount_avg_20d"].isna() | (panel["amount_avg_20d"] >= min_amount))
        & (~panel["st"] if eligibility.get("exclude_st", True) else True)
        & (~panel["suspended"] if eligibility.get("exclude_suspend", True) else True)
        & (~panel["limit_down"] if eligibility.get("exclude_limit_down_event", True) else True)
    )

    eligible_by_date = {
        int(date): sorted(group["ts_code"].astype(str).tolist())
        for date, group in panel[panel["eligible"]].groupby("trade_date")
    }
    suspended_by_date: dict[int, set[str]] = {}
    for date, group in panel[panel["suspended"]].groupby("trade_date"):
        suspended_by_date[int(date)] = set(group["ts_code"].astype(str))

    rows = []
    eligible_panel = panel[panel["eligible"]].copy()
    for date, group in eligible_panel.groupby("trade_date", sort=True):
        if len(group) < int(min_components):
            continue
        n_stocks = len(group)
        weight = min(1.0 / n_stocks, float(max_single_weight))
        returns = pd.to_numeric(group["pct_chg"], errors="coerce").fillna(0.0).to_numpy(dtype=float) / 100.0
        rows.append({
            "trade_date": int(date),
            "basket_name": "core_basket",
            "basket_ret_1d": float(np.sum(weight * returns)),
            "down_stock_ratio": float(np.mean(returns < 0)),
            "large_drop_ratio": float(np.mean(returns < -0.07)),
            "limit_up_ratio": 0.0,
            "limit_down_ratio": float(np.mean(group["limit_down"])),
            "tradable_count": int(n_stocks),
            "component_count": int(n_stocks),
            "configured_max_single_weight": float(max_single_weight),
            "realized_max_single_weight": float(weight),
            "cash_weight": float(1.0 - n_stocks * weight),
            "weight_cap_satisfied": bool(weight <= float(max_single_weight) + 1e-12),
            "median_amount_ratio_20d": float(group["amount_ratio_20d"].median()),
            "research_only": False,
        })
    basket = pd.DataFrame(rows)
    if not basket.empty:
        basket = basket.sort_values("trade_date").reset_index(drop=True)
        for window in (3, 5, 10):
            basket[f"basket_ret_{window}d"] = basket["basket_ret_1d"].rolling(window, min_periods=1).apply(
                lambda values: np.prod(1.0 + values) - 1.0, raw=True
            )
    return basket, eligible_by_date, suspended_by_date


def _write_sector_outputs(
    sector_dir: Path,
    config,
    universe: pd.DataFrame,
    signal: pd.DataFrame,
    events: pd.DataFrame,
    ledger: pd.DataFrame,
    summary: pd.DataFrame,
    annual: pd.DataFrame,
    manifest: dict,
) -> None:
    sector_dir.mkdir(parents=True, exist_ok=True)
    universe.to_csv(sector_dir / "universe_snapshot.csv", index=False, encoding="utf-8-sig")
    signal.to_csv(sector_dir / "signal_daily.csv", index=False, encoding="utf-8-sig")
    events.to_csv(sector_dir / "panic_events.csv", index=False, encoding="utf-8-sig")
    ledger.to_csv(sector_dir / "rule_trade_ledger.csv", index=False, encoding="utf-8-sig")
    summary.to_csv(sector_dir / "performance_summary.csv", index=False, encoding="utf-8-sig")
    annual.to_csv(sector_dir / "annual_returns.csv", index=False, encoding="utf-8-sig")
    output_files = {}
    for path in sorted(sector_dir.glob("*.csv")):
        output_files[path.name] = {
            "sha256": _hash_file(path),
            "size_bytes": path.stat().st_size,
            "row_count": int(len(pd.read_csv(path))),
        }
    manifest["output_files"] = output_files
    (sector_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def run_sector(
    config_path: Path,
    start: int,
    end: int,
    out_dir: Path,
    strict_tradability: bool,
    runtime_data_dir: Path | None = None,
    path_horizon: int = 0,
) -> dict:
    _ensure_builder_imports()
    config = load_config(config_path)
    raw = config.raw
    sector_name = str(config.sector["name"])
    signal_code = str(config.signal_benchmark["index_code"])
    parent_code = str(config.parent_benchmark["index_code"])
    print(f"\n[{sector_name}] loading PIT weights and prices", flush=True)

    if runtime_data_dir is None:
        weights = _load_weights([str(config.universe["index_code"])], start, end)
    else:
        weights = _read_runtime_table(runtime_data_dir, "index_weight")
        weights = weights[
            weights["index_code"].astype(str) == str(config.universe["index_code"])
        ].copy()
        if weights.empty:
            raise RuntimeError(f"{sector_name}: runtime index_weight is empty")
    # Prices are loaded for the union of all formal index members.  No manual
    # lithium-mining candidate enters this set.
    weight_codes = sorted(weights["ts_code"].astype(str).unique())
    if runtime_data_dir is None:
        prices = load_prices(start, end, weight_codes)
        index_prices = load_index_prices(start, end, [signal_code, parent_code])
    else:
        prices = _read_runtime_table(runtime_data_dir, "prices_adj")
        prices = prices[
            prices["ts_code"].astype(str).isin(weight_codes)
            & pd.to_numeric(prices["trade_date"], errors="coerce").between(start, end)
        ].copy()
        index_prices = _read_runtime_table(runtime_data_dir, "index_daily")
        index_prices = index_prices[
            index_prices["ts_code"].astype(str).isin([signal_code, parent_code])
            & pd.to_numeric(index_prices["trade_date"], errors="coerce").between(start, end)
        ].copy()
    # Tushare ``daily.amount`` is in thousand CNY.  The sector contracts
    # declare their thresholds in CNY, so normalize the loaded transport
    # frame before the shared eligibility helper compares amounts.
    if str(config.universe.get("eligibility", {}).get("amount_unit", "cny")).lower() in {
        "cny", "yuan"
    } and "amount" in prices.columns:
        prices["amount"] = pd.to_numeric(prices["amount"], errors="coerce") * 1000.0
    if index_prices.empty:
        raise RuntimeError(f"{sector_name}: no index_daily data for {signal_code}/{parent_code}")
    parent_index = index_prices[index_prices["ts_code"] == parent_code][["trade_date", "close"]].copy()
    sector_index = index_prices[index_prices["ts_code"] == signal_code][["trade_date", "close"]].copy()
    if parent_index.empty or sector_index.empty:
        raise RuntimeError(f"{sector_name}: required benchmark is empty")
    calendar = np.array(sorted(parent_index["trade_date"].astype(int).unique()), dtype=int)
    universe = build_pit_universe_from_weights(
        weights, str(config.universe["index_code"]), calendar
    )

    if runtime_data_dir is None:
        daily_basic = load_daily_basic(start, end, weight_codes)
        limit_status = load_limit_status(start, end, weight_codes)
        suspend_status = load_suspend_status(start, end, weight_codes)
        stock_status = load_stock_status()
        namechange = load_namechange(weight_codes)
    else:
        daily_basic = pd.DataFrame()
        limit_status = _read_runtime_table(runtime_data_dir, "limit_status")
        suspend_status = _read_runtime_table(runtime_data_dir, "suspend_status")
        stock_status = _read_runtime_table(runtime_data_dir, "stock_status")
        namechange = _read_runtime_table(runtime_data_dir, "namechange")
        for frame in (limit_status, suspend_status, namechange):
            if not frame.empty and "ts_code" in frame.columns:
                frame.drop(
                    frame.index[~frame["ts_code"].astype(str).isin(weight_codes)],
                    inplace=True,
                )
    missing_limit_rows = 0
    runtime_global_limit_gaps = 0
    if runtime_data_dir is not None:
        runtime_manifest = json.loads(
            (runtime_data_dir / "manifest.json").read_text(encoding="utf-8")
        )
        runtime_global_limit_gaps = int(
            runtime_manifest.get("limit_status_missing_rows", 0)
        )
        missing_limit_rows = _count_runtime_limit_gaps(
            prices, limit_status, weight_codes, runtime_manifest
        )
    missing_sources, tradability_audit = _status_sources(
        limit_status, suspend_status, stock_status, namechange,
        limit_status_missing_rows=missing_limit_rows,
    )
    if runtime_data_dir is not None:
        tradability_audit["runtime_global_limit_status_missing_rows"] = runtime_global_limit_gaps
        if runtime_global_limit_gaps and not missing_limit_rows:
            tradability_audit["runtime_dataset_has_unrelated_limit_gaps"] = True
            if strict_tradability:
                raise RuntimeError(
                    f"{sector_name}: runtime data has "
                    f"{runtime_global_limit_gaps} limit_status gaps outside this "
                    "sector (--strict-tradability)"
                )
    if missing_sources:
        message = f"{sector_name}: missing tradability sources: {', '.join(missing_sources)}"
        if strict_tradability:
            raise RuntimeError(message + " (--strict-tradability)")
        print("  WARNING: " + message + "; proxy judgments may be used", flush=True)

    basket, eligible_by_date, suspended_by_date = _build_efficient_basket(
        prices, universe, calendar, config.universe.get("eligibility", {}),
        float(config.universe["max_single_weight"]),
        int(config.universe["min_components"]), limit_status,
        suspend_status, stock_status, namechange,
    )
    if basket.empty:
        raise RuntimeError(f"{sector_name}: eligible basket is empty")
    signal = build_signal_frame(
        basket, sector_index, parent_index, config.panic_gate
    )
    events = cluster_first_triggers(
        signal, calendar,
        max_gap_trading_days=int(raw.get("event_clustering", {}).get("max_gap_trading_days", 5)),
    )
    regime = _regime_map(parent_index)
    suspended = _suspended_keys(suspend_status)
    hold_days = int(config.execution["hold_days"])
    stops = [float(value) for value in config.execution["stop_levels"]]
    primary_cost = int(config.cost.round_trip_bps)
    scenarios = sorted(set([primary_cost] + [
        int(value) for value in raw.get("cost", {}).get("stress_scenarios", [])
    ]))

    ledger_rows = []
    event_rows = []
    event_records = events.to_dict("records")
    for position, event in enumerate(event_records):
        signal_date = int(event["event_date"])
        next_signal = (
            int(event_records[position + 1]["event_date"])
            if position + 1 < len(event_records) else None
        )
        signal_position = int(np.searchsorted(calendar, signal_date))
        if signal_position + 1 >= len(calendar):
            continue
        entry_date = int(calendar[signal_position + 1])
        codes, exclusions = _entry_codes(
            universe, signal_date, entry_date, prices, calendar,
            config.universe.get("eligibility", {}), limit_status,
            suspend_status, stock_status, namechange,
            int(config.execution.get("min_entry_components", config.universe["min_components"])),
            eligible_by_date=eligible_by_date,
            suspended_by_date=suspended_by_date,
        )
        event_row = dict(event)
        event_row.update({
            "sector": sector_name,
            "signal_index": signal_code,
            "signal_date": signal_date,
            "entry_date": entry_date,
            "entry_component_count": len(codes),
            "entry_component_codes": ",".join(codes),
            "entry_status": "ENTRY_RESOLVED" if codes else "NO_TRADABLE_BASKET",
            "market_regime": regime.get(signal_date, "unknown"),
            "excluded_count": len(exclusions),
        })
        event_rows.append(event_row)
        if not codes:
            continue
        path_horizon_days = (
            int(path_horizon) if int(path_horizon) > 0
            else max(hold_days + 8, 28)
        )
        path_result = build_frozen_path(
            prices, codes, entry_date, calendar,
            horizon=path_horizon_days, suspended_keys=suspended,
        )
        if path_result is None:
            continue
        returns, dates = path_result
        boundary_exit = None
        if next_signal is not None:
            boundary_position = int(np.searchsorted(calendar, next_signal)) + 1
            if boundary_position < len(calendar):
                boundary_exit = int(calendar[boundary_position])
        checker = _exit_checker(codes, prices, limit_status, suspend_status)
        path_type = ""
        for cost_bps in scenarios:
            for rule_id in config.execution["rules"]:
                result = simulate_rule(
                    str(rule_id), returns, dates, hold_days, stops, cost_bps,
                    boundary_exit_date=boundary_exit,
                    executable_exit=checker,
                )
                path_type = result.path_type or path_type
                ledger_rows.append({
                    "sector": sector_name,
                    "signal_id": str(event["event_id"]),
                    "rule_id": str(rule_id),
                    "event_date": signal_date,
                    "entry_date": entry_date,
                    "cost_bps": int(cost_bps),
                    "market_regime": regime.get(signal_date, "unknown"),
                    "sample_split": assign_sample_split(signal_date, config.sample_split),
                    "n_entry_components": len(codes),
                    "path_type": result.path_type,
                    "status": result.status,
                    "status_reason": result.status_reason,
                    "exit_date": result.exit_date,
                    "second_entry_date": result.second_entry_date,
                    "invested_weight": result.invested_weight,
                    "gross_return": result.gross_return,
                    "net_return": result.net_return,
                })
        event_row["path_type"] = path_type

    events_output = pd.DataFrame(event_rows)
    ledger = pd.DataFrame(ledger_rows)
    if ledger.empty:
        ledger = pd.DataFrame(columns=[
            "sector", "signal_id", "rule_id", "event_date", "entry_date", "cost_bps",
            "market_regime", "sample_split", "n_entry_components", "path_type",
            "status", "status_reason", "exit_date", "second_entry_date",
            "invested_weight", "gross_return", "net_return",
        ])
    summary = summarize_trade_ledger(ledger, primary_cost)
    annual = annual_trade_returns(ledger, primary_cost)
    summary.insert(0, "sector", sector_name)
    annual.insert(0, "sector", sector_name)
    manifest = {
        "schema": "sector_panic_backtest.v1",
        "status": "RESEARCH_ONLY",
        "sector": sector_name,
        "signal_index": signal_code,
        "parent_index": parent_code,
        "date_range": {"start": int(start), "end": int(end)},
        "config_path": str(config_path.relative_to(ROOT)),
        "config_sha256": config.config_hash,
        "primary_cost_bps": primary_cost,
        "cost_scenarios_bps": scenarios,
        "execution_rules": list(config.execution["rules"]),
        "hold_days": hold_days,
        "path_horizon": path_horizon_days,
        "stop_levels": stops,
        "n_universe_intervals": int(len(universe)),
        "n_universe_codes": int(universe["ts_code"].nunique()),
        "n_signal_days": int(len(signal)),
        "n_panic_clusters": int(len(events_output)),
        "n_trade_rows": int(len(ledger)),
        "tradability_audit": tradability_audit,
        "pit_membership_rule": "monthly index_weight snapshot effective next exchange trading day",
        "metric_basis": "realized event-trade sequence; max drawdown is over sorted realized trades",
        "amount_normalization": {
            "source_unit": "thousand_cny",
            "contract_threshold_unit": str(config.universe.get("eligibility", {}).get("amount_unit", "cny")),
            "multiplier_applied": 1000.0,
        },
    }
    sector_dir = out_dir / sector_name
    _write_sector_outputs(
        sector_dir, config, universe, signal, events_output, ledger,
        summary, annual, manifest,
    )
    print(
        f"[{sector_name}] universe={universe['ts_code'].nunique()} codes, "
        f"signals={len(signal)}, clusters={len(events_output)}, trades={len(ledger)}",
        flush=True,
    )
    return {"sector": sector_name, "summary": summary, "annual": annual, "manifest": manifest}


def _write_comparison(results: list[dict], out_dir: Path) -> None:
    frames = []
    for result in results:
        summary = result["summary"].copy()
        if not summary.empty:
            frames.append(summary)
    comparison = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    comparison.to_csv(out_dir / "sector_performance_comparison.csv", index=False, encoding="utf-8-sig")
    lines = [
        "# Sector Panic Repair Comparison",
        "",
        "The formal comparison covers nonferrous, new_energy, and lithium_battery. "
        "The quarantined lithium-mining candidate pool is excluded.",
        "",
        "Primary cost is the round-trip cost declared by each YAML (100bp for all three). "
        "Returns are realized event-trade sequence returns; right-censored and "
        "untradable trades are excluded from return statistics and reported separately.",
        "",
    ]
    if not comparison.empty:
        primary = comparison[comparison["sample_split"].isin(["all_period", "locked_oos", "pre_registration_holdout"])]
        columns = [
            "sector", "rule_id", "sample_split", "n_signals", "n_realized",
            "n_censored", "n_untradable", "mean_return", "median_return",
            "win_rate", "cumulative_return", "max_drawdown",
        ]
        # pandas.DataFrame.to_markdown requires the optional ``tabulate``
        # package.  This report is part of the runnable research artifact, so
        # keep it independent of that optional presentation dependency.
        display = primary[columns].copy()
        lines.append("| " + " | ".join(columns) + " |")
        lines.append("| " + " | ".join(["---"] * len(columns)) + " |")
        for row in display.itertuples(index=False, name=None):
            values = []
            for value in row:
                if isinstance(value, (float, np.floating)):
                    values.append("" if not np.isfinite(value) else f"{value:.4f}")
                elif pd.isna(value):
                    values.append("")
                else:
                    values.append(str(value).replace("|", "\\|"))
            lines.append("| " + " | ".join(values) + " |")
    lines.extend([
        "",
        "## Interpretation",
        "",
        "- `R0` enters the full frozen basket on T+1 and holds for the configured 20 trading days unless the stop or next panic boundary fires.",
        "- `R2` enters 50% on T+1 and adds 50% on the first post-retest second breakout observed within the path window.",
        "- A comparison is descriptive evidence, not a promotion decision; use the locked OOS row before considering the 2026 holdout.",
    ])
    (out_dir / "sector_performance_comparison.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    config_paths = [Path(value) for value in args.configs] if args.configs else SECTOR_CONFIGS
    config_paths = [path if path.is_absolute() else ROOT / path for path in config_paths]
    out_dir = Path(args.out_dir)
    out_dir = out_dir if out_dir.is_absolute() else ROOT / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    runtime_data_dir = None
    if args.runtime_data_dir:
        runtime_data_dir = Path(args.runtime_data_dir)
        runtime_data_dir = (
            runtime_data_dir if runtime_data_dir.is_absolute()
            else ROOT / runtime_data_dir
        )
        runtime_manifest_path = runtime_data_dir / "manifest.json"
        if not runtime_manifest_path.exists():
            raise SystemExit(f"runtime data manifest missing: {runtime_manifest_path}")
        runtime_manifest = json.loads(runtime_manifest_path.read_text(encoding="utf-8"))
        if runtime_manifest.get("status") != "COMPLETE":
            raise SystemExit("runtime data is not COMPLETE")
    if not DATA_PREPARATION_MANIFEST.exists():
        raise SystemExit(f"missing data preparation manifest: {DATA_PREPARATION_MANIFEST}")
    prep_manifest = json.loads(DATA_PREPARATION_MANIFEST.read_text(encoding="utf-8"))
    if prep_manifest.get("status") != "COMPLETE":
        raise SystemExit("data preparation manifest is not COMPLETE; run preparation first")
    prep_end = int(prep_manifest.get("request", {}).get("end", 0))
    if int(args.end) > prep_end:
        raise SystemExit(
            f"requested end {args.end} exceeds prepared data end {prep_end}; "
            "prepare an audited increment before extending the run"
        )

    results = []
    for config_path in config_paths:
        results.append(run_sector(
            config_path, int(args.start), int(args.end), out_dir,
            bool(args.strict_tradability), runtime_data_dir,
            path_horizon=int(args.path_horizon),
        ))
    _write_comparison(results, out_dir)
    comparison_manifest = {
        "schema": "sector_panic_comparison.v1",
        "status": "RESEARCH_ONLY",
        "sectors": [result["sector"] for result in results],
        "excluded_pools": ["lithium_mining_quarantined_pending_pit_evidence"],
        "date_range": {"start": int(args.start), "end": int(args.end)},
        "data_preparation_manifest_sha256": _hash_file(DATA_PREPARATION_MANIFEST),
        "comparison_csv_sha256": _hash_file(out_dir / "sector_performance_comparison.csv"),
    }
    (out_dir / "sector_performance_comparison_manifest.json").write_text(
        json.dumps(comparison_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"\nComparison written to {out_dir / 'sector_performance_comparison.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

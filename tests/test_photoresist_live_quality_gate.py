"""Data quality gate v2 tests — per-security continuity matrix (plan §10)."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from live.photoresist_panic.quality_gate import (  # noqa: E402
    BLOCKED, DEGRADED, NORMAL, run_quality_gate,
)

CORE = ["300655.SZ", "300346.SZ", "603650.SH", "300236.SZ"]
INDICES = ["000300.SH", "931865.CSI", "399006.SZ"]


def _config(**overrides):
    config = {
        "gate_version": "dq_gate_v2",
        "min_components_normal": 4,
        "min_components_degraded": 3,
        "require_index_alignment": True,
        "require_adj_prices_positive": True,
        "require_amount_present": True,
        "warmup_trading_days": 250,
        "required_indices": INDICES,
    }
    config.update(overrides)
    return config


def _days(n=300, end="2025-12-31"):
    dates = pd.bdate_range(end=end, periods=n)
    return [int(d.strftime("%Y%m%d")) for d in dates]


def _make_prices(days, codes=CORE, drop=None):
    """drop: {(code, day), ...} rows to omit."""
    drop = drop or set()
    rows = []
    for code in codes:
        for day in days:
            if (code, day) in drop:
                continue
            rows.append({
                "ts_code": code, "trade_date": day,
                "adj_open": 10.0, "adj_high": 10.5, "adj_low": 9.5,
                "adj_close": 10.0, "pct_chg": 0.0, "vol": 1000.0,
                "amount": 5000.0,
            })
    return pd.DataFrame(rows)


def _make_indices(days, codes=INDICES, drop=None):
    drop = drop or set()
    return pd.DataFrame([
        {"ts_code": code, "trade_date": day, "close": 4000.0, "pct_chg": 0.0}
        for code in codes for day in days if (code, day) not in drop
    ])


def _gate(prices, indices, days, config=None, suspend=None):
    return run_quality_gate(
        prices, indices, CORE, days[-1], config or _config(),
        open_dates=days, suspend_records=suspend,
        calendar_latest_trading_day=days[-1],
    )


def test_normal_when_all_components_current():
    days = _days()
    report = _gate(_make_prices(days), _make_indices(days), days)
    assert report["status"] == NORMAL
    assert report["components_present"] == 4
    assert report["active_expected"] == sorted(CORE)
    assert report["market_data_present"] == sorted(CORE)


def test_stale_stock_data_blocks():
    days = _days()
    report = run_quality_gate(
        _make_prices(days), _make_indices(days), CORE, 20260110, _config(),
        open_dates=days, calendar_latest_trading_day=20260110,
    )
    assert report["status"] == BLOCKED
    assert any("stock_data_current" in b for b in report["blockers"])


def test_stock_missing_20_middle_days_blocks_even_with_fresh_max_date():
    """Plan §10: 单只股票中间缺20日但最新日期正常 -> BLOCKED."""
    days = _days()
    hole = {( "300236.SZ", d) for d in days[100:120]}
    report = _gate(_make_prices(days, drop=hole), _make_indices(days), days)
    assert report["status"] == BLOCKED
    assert any("stock_continuity[300236.SZ]" in b for b in report["blockers"])
    assert report["stock_continuity"]["300236.SZ"]["n_missing"] == 20


def test_index_missing_100_middle_days_blocks_even_with_fresh_max_date():
    """Plan §10: 指数中间缺100日但max_date正常 -> BLOCKED (931865.CSI case)."""
    days = _days()
    hole = {("931865.CSI", d) for d in days[50:150]}
    report = _gate(_make_prices(days), _make_indices(days, drop=hole), days)
    assert report["status"] == BLOCKED
    assert any("index_continuity[931865.CSI]" in b for b in report["blockers"])
    assert report["index_continuity"]["931865.CSI"]["n_missing"] == 100


def test_legal_suspension_gap_does_not_block():
    """Missing rows covered by suspension records are legal (warning only)."""
    days = _days()
    hole_days = days[200:203]
    hole = {("300236.SZ", d) for d in hole_days}
    suspend = pd.DataFrame({
        "ts_code": ["300236.SZ"] * 3, "trade_date": hole_days,
    })
    report = _gate(_make_prices(days, drop=hole), _make_indices(days), days,
                   suspend=suspend)
    assert report["status"] == NORMAL
    assert any("legal" in w for w in report["warnings"])
    assert report["stock_continuity"]["300236.SZ"]["unexplained_dates"] == []


def test_unexplained_gap_blocks():
    """Same missing rows WITHOUT suspension records -> data gap, BLOCKED."""
    days = _days()
    hole = {("300236.SZ", d) for d in days[200:203]}
    report = _gate(_make_prices(days, drop=hole), _make_indices(days), days)
    assert report["status"] == BLOCKED
    assert any("stock_continuity[300236.SZ]" in b for b in report["blockers"])


def test_missing_open_dates_fails_closed():
    days = _days()
    report = run_quality_gate(
        _make_prices(days), _make_indices(days), CORE, days[-1], _config(),
        open_dates=None, calendar_latest_trading_day=days[-1],
    )
    assert report["status"] == BLOCKED
    assert any("continuity_window_available" in b for b in report["blockers"])


def test_component_missing_on_eval_day_with_suspension_degrades():
    days = _days()
    hole = {("300236.SZ", days[-1])}
    suspend = pd.DataFrame({"ts_code": ["300236.SZ"],
                            "trade_date": [days[-1]]})
    report = _gate(_make_prices(days, drop=hole), _make_indices(days), days,
                   suspend=suspend)
    assert report["status"] == DEGRADED
    assert report["components_present"] == 3
    assert report["missing_components"] == [
        {"ts_code": "300236.SZ", "reason": "suspended"}
    ]


def test_fewer_than_three_components_blocks():
    days = _days()
    hole = {(c, days[-1]) for c in ("300236.SZ", "603650.SH")}
    suspend = pd.DataFrame({
        "ts_code": ["300236.SZ", "603650.SH"],
        "trade_date": [days[-1], days[-1]],
    })
    report = _gate(_make_prices(days, drop=hole), _make_indices(days), days,
                   suspend=suspend)
    assert report["status"] == BLOCKED


def test_duplicate_stock_and_index_keys_block():
    days = _days()
    prices = _make_prices(days)
    prices = pd.concat([prices, prices.tail(1)], ignore_index=True)
    report = _gate(prices, _make_indices(days), days)
    assert any("no_duplicate_stock_keys" in b for b in report["blockers"])
    assert report["duplicate_key_audit"]["stock"] == [{
        "ts_code": CORE[-1], "trade_date": days[-1], "row_count": 2,
    }]
    indices = _make_indices(days)
    indices = pd.concat([indices, indices.tail(1)], ignore_index=True)
    report = _gate(_make_prices(days), indices, days)
    assert any("no_duplicate_index_keys" in b for b in report["blockers"])
    assert report["duplicate_key_audit"]["index"] == [{
        "ts_code": INDICES[-1], "trade_date": days[-1], "row_count": 2,
    }]


def test_live_raw_loaders_preserve_source_duplicates(tmp_path, monkeypatch):
    from scripts import build_photoresist_panic_events as builder
    from live.photoresist_panic import signal_engine

    prices_dir = tmp_path / "prices"
    index_dir = tmp_path / "indices"
    (prices_dir / "year=2026").mkdir(parents=True)
    (index_dir / "year=2026").mkdir(parents=True)
    stock_row = pd.DataFrame([{
        "ts_code": CORE[0], "trade_date": 20260715,
        "adj_open": 10.0, "adj_high": 10.1, "adj_low": 9.9,
        "adj_close": 10.0, "close": 10.0, "pct_chg": 0.0,
        "vol": 100.0, "amount": 1000.0,
    }])
    index_row = pd.DataFrame([{
        "ts_code": INDICES[0], "trade_date": 20260715,
        "close": 4000.0, "pct_chg": 0.0,
    }])
    for name in ("a.parquet", "b.parquet"):
        stock_row.to_parquet(prices_dir / "year=2026" / name, index=False)
        index_row.to_parquet(index_dir / "year=2026" / name, index=False)
    monkeypatch.setattr(builder, "PRICES_DIR", prices_dir)
    monkeypatch.setattr(builder, "INDEX_DIR", index_dir)

    prices = signal_engine.load_full_prices(20260101, 20261231, [CORE[0]])
    indices = signal_engine.load_full_index_prices(
        20260101, 20261231, [INDICES[0]]
    )
    assert len(prices) == 2
    assert prices.duplicated(["ts_code", "trade_date"]).sum() == 1
    assert len(indices) == 2
    assert indices.duplicated(["ts_code", "trade_date"]).sum() == 1


def test_adj_ohlc_missing_any_column_blocks():
    """Plan §3.5: adj_close alone must NOT pass the OHLC check."""
    days = _days()
    for missing_col in ("adj_open", "adj_high", "adj_low"):
        prices = _make_prices(days).drop(columns=[missing_col])
        report = _gate(prices, _make_indices(days), days)
        assert report["status"] == BLOCKED, missing_col
        assert any("adj_ohlc_columns_complete" in b for b in report["blockers"])


def test_nonpositive_adj_price_blocks():
    days = _days()
    prices = _make_prices(days)
    prices.loc[prices.index[-1], "adj_low"] = -1.0
    report = _gate(prices, _make_indices(days), days)
    assert report["status"] == BLOCKED
    assert any("adj_prices_positive" in b for b in report["blockers"])


def test_amount_missing_blocks_when_required():
    """Plan §3.5: require_amount_present=true means BLOCK, not warn."""
    days = _days()
    prices = _make_prices(days)
    prices.loc[prices.index[-1], "amount"] = np.nan
    report = _gate(prices, _make_indices(days), days)
    assert report["status"] == BLOCKED
    assert any("amount_present" in b for b in report["blockers"])


def test_amount_missing_warns_when_config_false():
    days = _days()
    prices = _make_prices(days)
    prices.loc[prices.index[-1], "amount"] = np.nan
    report = _gate(prices, _make_indices(days), days,
                   config=_config(require_amount_present=False))
    assert report["status"] == NORMAL
    assert any("amount_present" in w for w in report["warnings"])


def test_insufficient_warmup_blocks():
    days = _days(n=100)
    report = _gate(_make_prices(days), _make_indices(days), days)
    assert report["status"] == BLOCKED
    assert any("history_warmup" in b for b in report["blockers"])

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class DummyLoader:
    def __init__(self, prices_adj, index_weight=None):
        self.prices_adj = prices_adj
        self.index_weight = index_weight

    def query(self, table_name, columns=None, start_date=None, end_date=None, ts_codes=None):
        assert table_name in {"prices_adj", "index_weight"}
        if table_name == "prices_adj":
            df = self.prices_adj.copy()
        else:
            if self.index_weight is None:
                raise KeyError("index_weight not available")
            df = self.index_weight.copy()
        if start_date is not None:
            df = df[df["trade_date"] >= int(start_date)]
        if end_date is not None:
            df = df[df["trade_date"] <= int(end_date)]
        if ts_codes is not None:
            df = df[df["ts_code"].isin(ts_codes)]
        if columns is not None:
            df = df[columns]
        return df


def test_phase2_price_quality_precheck_passes_clean_prices(tmp_path, monkeypatch):
    import run_research

    monkeypatch.chdir(tmp_path)
    prices = pd.DataFrame({
        "ts_code": ["A.SZ", "A.SZ", "B.SZ", "B.SZ"],
        "trade_date": [20260102, 20260105, 20260102, 20260105],
        "adj_close": [10.0, 10.1, 20.0, 19.8],
        "adj_factor": [1.0, 1.0, 1.0, 1.0],
    })

    ok = run_research._check_phase2_price_quality(
        DummyLoader(prices), "20260101", "20260131"
    )

    assert ok is True


def test_phase2_price_quality_precheck_blocks_adj_factor_regime_break(
    tmp_path, monkeypatch
):
    import run_research

    monkeypatch.chdir(tmp_path)
    prices = pd.DataFrame({
        "ts_code": ["A.SZ", "A.SZ", "B.SZ", "B.SZ"],
        "trade_date": [20260306, 20260309, 20260306, 20260309],
        "adj_close": [10.0, 1500.0, 20.0, 19.8],
        "adj_factor": [1.0, 150.0, 1.0, 1.0],
    })

    ok = run_research._check_phase2_price_quality(
        DummyLoader(prices), "20260301", "20260331"
    )

    assert ok is False
    failure_path = (
        tmp_path / "outputs" / "price_quality_failures"
        / "phase2_20260301_20260331.json"
    )
    assert failure_path.exists()


def test_phase2_price_quality_precheck_ignores_non_universe_extreme_rows(
    tmp_path, monkeypatch
):
    import run_research

    monkeypatch.chdir(tmp_path)
    prices = pd.DataFrame({
        "ts_code": ["A.SZ", "A.SZ", "Z.BJ", "Z.BJ"],
        "trade_date": [20260306, 20260309, 20260306, 20260309],
        "adj_close": [10.0, 10.1, 1.0, 100.0],
        "adj_factor": [1.0, 1.0, 1.0, 100.0],
    })
    index_weight = pd.DataFrame({
        "ts_code": ["A.SZ"],
        "trade_date": [20260301],
    })

    ok = run_research._check_phase2_price_quality(
        DummyLoader(prices, index_weight=index_weight), "20260301", "20260331"
    )

    assert ok is True


def test_phase2_price_quality_precheck_still_blocks_universe_extreme_rows(
    tmp_path, monkeypatch
):
    import run_research

    monkeypatch.chdir(tmp_path)
    prices = pd.DataFrame({
        "ts_code": ["A.SZ", "A.SZ", "Z.BJ", "Z.BJ"],
        "trade_date": [20260306, 20260309, 20260306, 20260309],
        "adj_close": [10.0, 1000.0, 1.0, 1.1],
        "adj_factor": [1.0, 100.0, 1.0, 1.0],
    })
    index_weight = pd.DataFrame({
        "ts_code": ["A.SZ"],
        "trade_date": [20260301],
    })

    ok = run_research._check_phase2_price_quality(
        DummyLoader(prices, index_weight=index_weight), "20260301", "20260331"
    )

    assert ok is False

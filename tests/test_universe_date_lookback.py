"""UniverseBuilder date lookback formatting."""

from unittest.mock import MagicMock

import pandas as pd


def test_universe_load_uses_yyyymmdd_lookback_start():
    from data.universe import UniverseBuilder

    client = MagicMock()
    client.get_index_weight.return_value = pd.DataFrame({
        "trade_date": [20241231],
        "ts_code": ["000001.SZ"],
        "weight": [1.0],
    })
    client.get_stock_basic.return_value = pd.DataFrame({
        "ts_code": ["000001.SZ"],
        "list_date": [20200101],
        "delist_date": [20991231],
    })
    client.get_namechange.return_value = pd.DataFrame()

    ub = UniverseBuilder(client=client)
    ub.load(start_date="20250101", end_date="20260604")

    kwargs = client.get_index_weight.call_args.kwargs
    assert kwargs["start_date"] == "20241001"
    assert kwargs["end_date"] == "20260604"

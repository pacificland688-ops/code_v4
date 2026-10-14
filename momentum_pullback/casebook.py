"""Hand-designed inputs, not market observations or profitability evidence."""
from __future__ import annotations

import pandas as pd

from momentum_pullback.contracts import Contract, validate_contract


def hand_panel() -> tuple[pd.DataFrame, list[int]]:
    """150 flat observations, Dec-29 breakout, Jan-02/05 separate touches."""
    # Weekdays here are a declared synthetic clock, never a market-calendar fallback.
    dates = [int(date.strftime("%Y%m%d")) for date in pd.bdate_range(end="2017-12-29", periods=151)]
    dates += [20180102, 20180103, 20180104, 20180105]
    rows = []
    for code in list("ABCDEFGHIJKLMNOPQRST"):
        for index, date in enumerate(dates):
            leader = code in "ABCD" and index >= 150
            close = 12.0 if leader else 10.0
            low = 11.8 if leader else 10.0
            high = 12.1 if leader else 10.0
            if code == "A" and date in [20180102, 20180103, 20180105]:
                low = 10.1
            day = pd.to_datetime(str(date), format="%Y%m%d").strftime("%Y-%m-%d")
            available = f"{day}T17:00:00+08:00"
            row = {"ts_code": code, "trade_date": date, "adj_open": close, "adj_high": high, "adj_low": low, "adj_close": close, "amount_cny": 100_000_000.0, "circ_mv_cny": 1_000_000_000.0, "price_status": "TRADED", "membership_known": True, "is_member": True, "st_known": True, "is_st": False, "industry_code": "SYNTHETIC_INDUSTRY", "signal_cutoff": f"{day}T18:00:00+08:00"}
            for field in ["price", "membership", "st", "amount", "basic", "industry"]:
                row[field + "_available_at"] = available
            for field in ["membership", "st", "industry"]:
                row[field + "_effective_from"] = dates[0]
                row[field + "_effective_to"] = None
            rows.append(row)
    return pd.DataFrame(rows), dates


def declare_synthetic_roster(panel: pd.DataFrame) -> pd.DataFrame:
    """Explicit test declaration. The feature engine must not invent this from rows."""
    roster = panel[["trade_date", "ts_code"]].drop_duplicates().copy()
    roster["ts_code"] = roster["ts_code"].astype(str)
    roster["required_for_rank"] = True
    roster["track_identity"] = True
    return roster.reset_index(drop=True)


def hand_contract(contract: Contract) -> Contract:
    payload = contract.payload
    _, dates = hand_panel()
    payload["scope"] = {"purpose": "ENGINEERING_ONLY", "feature_origin": dates[0], "output_start": 20180101, "output_end": 20180105}
    return validate_contract(payload)

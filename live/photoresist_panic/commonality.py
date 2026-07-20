"""Component commonality diagnostics for the 4-stock core basket.

Classification (frozen thresholds in configs/photoresist_panic_live.yaml):
  SECTOR_WIDE       : >= 3/4 components move the same direction and the drop
                      is not dominated by a single stock
  MIXED             : only 2/4 down or clearly divergent components
  STOCK_DRIVEN      : one stock contributes more than the frozen cap of the
                      basket drop — PANIC_ALERT still fires, but reversal
                      credibility is downgraded
  INSUFFICIENT_DATA : fewer than 3 valid components
"""
from __future__ import annotations

import numpy as np
import pandas as pd

SECTOR_WIDE = "SECTOR_WIDE"
MIXED = "MIXED"
STOCK_DRIVEN = "STOCK_DRIVEN"
INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


def component_snapshot(
    prices: pd.DataFrame,
    members: pd.DataFrame,
    trade_date: int,
    semi_ret_5d: float | None,
    limit_status: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Per-component 5d metrics at trade_date using adjusted closes only."""
    rows = []
    for _, member in members.iterrows():
        code = str(member["ts_code"])
        history = prices[
            (prices["ts_code"] == code) & (prices["trade_date"] <= trade_date)
        ].sort_values("trade_date")
        if history.empty or int(history["trade_date"].iloc[-1]) != int(trade_date):
            rows.append({
                "ts_code": code, "name": str(member.get("name", "")),
                "ret_5d": np.nan, "pct_chg_1d": np.nan,
                "rel_vs_semi_5d": np.nan, "amount_ratio_20d": np.nan,
                "limit_down_today": False, "valid": False,
            })
            continue
        closes = history["adj_close"]
        ret_5d = float(closes.iloc[-1] / closes.iloc[-6] - 1.0) if len(history) >= 6 else np.nan
        latest = history.iloc[-1]
        amount = history["amount"] if "amount" in history.columns else None
        amount_ratio = (
            float(amount.iloc[-1] / amount.tail(21).iloc[:-1].mean())
            if amount is not None and len(amount) >= 21
            and amount.tail(21).iloc[:-1].mean() > 0 else np.nan
        )
        limit_down_today = _hit_limit_down(latest, code, trade_date, limit_status)
        rows.append({
            "ts_code": code, "name": str(member.get("name", "")),
            "ret_5d": ret_5d,
            "pct_chg_1d": float(latest.get("pct_chg", np.nan)) / 100.0,
            "rel_vs_semi_5d": ret_5d - semi_ret_5d
                if semi_ret_5d is not None and np.isfinite(ret_5d) else np.nan,
            "amount_ratio_20d": amount_ratio,
            "limit_down_today": bool(limit_down_today),
            "valid": bool(np.isfinite(ret_5d)),
        })
    return pd.DataFrame(rows)


def _hit_limit_down(latest_row, code: str, trade_date: int,
                    limit_status: pd.DataFrame | None) -> bool:
    """Frozen limit-down-event semantics: exact limit-price hit OR the frozen
    pct_chg <= -9.5 proxy (the eligibility filter's definition). The stress
    count must never be narrower than the exclusion reason, or a member
    excluded "for limit-down" would vanish from P4 pressure."""
    if limit_status is not None and not limit_status.empty:
        row = limit_status[
            (limit_status["ts_code"] == code)
            & (limit_status["trade_date"] == trade_date)
        ]
        if not row.empty and "down_limit" in row.columns:
            down_limit = float(row["down_limit"].iloc[-1])
            close = float(latest_row.get("close", np.nan))
            if np.isfinite(close) and down_limit > 0 and (
                abs(close - down_limit) < 0.005
            ):
                return True
    pct = float(latest_row.get("pct_chg", np.nan))
    return bool(np.isfinite(pct) and pct <= -9.5)


def classify_commonality(snapshot: pd.DataFrame, basket_ret_5d: float,
                         config: dict) -> dict:
    """Classify the drop structure and produce contribution diagnostics."""
    cap = float(config.get("stock_driven_contribution_cap", 0.50))
    min_valid = int(config.get("min_valid_components", 3))
    sector_min_down = int(config.get("sector_wide_min_down", 3))

    valid = snapshot[snapshot["valid"]]
    n_valid = len(valid)
    result = {
        "n_valid_components": int(n_valid),
        "n_total_components": int(len(snapshot)),
        "down_count": None, "median_ret_5d": None,
        "max_contribution_share": None, "max_contributor": None,
        "classification": INSUFFICIENT_DATA,
        "reversal_credibility_downgraded": False,
        "notes": [],
    }
    if n_valid < min_valid:
        result["notes"].append(f"有效成分{n_valid}只 < {min_valid}，无法诊断共同性")
        return result

    returns = valid["ret_5d"].to_numpy()
    down_mask = returns < 0
    down_count = int(down_mask.sum())
    result["down_count"] = down_count
    result["median_ret_5d"] = float(np.median(returns))

    # Equal-weight contribution of each stock to the basket 5d move
    contributions = returns / n_valid
    if basket_ret_5d is not None and basket_ret_5d < 0 and down_count > 0:
        negative_sum = contributions[down_mask].sum()
        if negative_sum < 0:
            shares = np.zeros_like(contributions)
            shares[down_mask] = contributions[down_mask] / negative_sum
            max_idx = int(np.argmax(shares))
            result["max_contribution_share"] = float(shares[max_idx])
            result["max_contributor"] = str(valid.iloc[max_idx]["ts_code"])

    max_share = result["max_contribution_share"]
    # Single-stock domination: share above the frozen cap AND clearly larger
    # than the next contributor (with <=2 downs the top share is trivially
    # >=50%, so the cap alone cannot distinguish MIXED from STOCK_DRIVEN).
    dominance_ratio = float(config.get("stock_driven_dominance_ratio", 2.0))
    dominant = False
    if max_share is not None and max_share > cap:
        down_mags = np.sort(-returns[down_mask])[::-1]
        dominant = len(down_mags) == 1 or (
            down_mags[1] <= 0 or down_mags[0] >= dominance_ratio * down_mags[1]
        )
    if dominant:
        result["classification"] = STOCK_DRIVEN
        result["reversal_credibility_downgraded"] = True
        result["notes"].append(
            f"{result['max_contributor']}贡献篮子跌幅的{max_share:.0%} > 冻结上限{cap:.0%}，"
            "恐慌预警仍有效，但反转可信度下调"
        )
    elif down_count >= sector_min_down:
        result["classification"] = SECTOR_WIDE
        result["notes"].append(f"{down_count}/{n_valid}成分同向下跌，非单一股票主导")
    else:
        result["classification"] = MIXED
        result["notes"].append(f"仅{down_count}/{n_valid}成分下跌或成分明显分化")
    return result


def dual_commonality(snapshot: pd.DataFrame, eligible_codes: list[str],
                     gate_basket_ret_5d: float, config: dict) -> dict:
    """Two frozen member scopes (gap-fix plan §5):

    theme_commonality  — ALL active core members: did the sector fall together?
    signal_commonality — only gate-eligible members: who computed the signal?
    """
    valid = snapshot[snapshot["valid"]]
    theme_ret = float(np.mean(valid["ret_5d"])) if not valid.empty else None
    theme = classify_commonality(snapshot, theme_ret, config)
    theme["scope"] = "all_active_members"
    theme["basket_ret_5d"] = theme_ret

    eligible_set = {str(c) for c in eligible_codes}
    signal_snapshot = snapshot[
        snapshot["ts_code"].astype(str).isin(eligible_set)
    ].reset_index(drop=True)
    signal = classify_commonality(signal_snapshot, gate_basket_ret_5d, config)
    signal["scope"] = "signal_eligible_members"
    signal["basket_ret_5d"] = gate_basket_ret_5d
    return {"theme_commonality": theme, "signal_commonality": signal}

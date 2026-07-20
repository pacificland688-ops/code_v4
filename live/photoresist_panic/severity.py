"""Panic severity ladder P0-P4 — explanation only, never modifies the P2 gate.

  P0: normal
  P1: weak-panic watch — worst 20% of trailing 250d, but primary_5d NOT triggered
  P2: primary_5d triggered (the frozen signal, eligible basket)
  P3: P2 plus 5d return <= -8% OR historical percentile <= 5%
  P4: P3 plus liquidity stress

Frozen scope split (gap-fix plan §5):
  - P2/P3 magnitude legs read the FROZEN eligible-basket gate metrics.
  - P4 stress legs (breadth / volume / limit-down) read ALL active core
    members — a limit-down member filtered out of the gate basket must still
    count toward P4 stress.
"""
from __future__ import annotations

import math


def _finite(value) -> bool:
    return value is not None and math.isfinite(value)


def classify_severity(
    triggered: bool,
    basket_ret_5d: float,
    historical_percentile: float,
    active_down_breadth_5d: float | None,
    active_amount_ratio_20d: float | None,
    active_limit_down_count: int,
    config: dict,
) -> dict:
    """Return {'level': 'P0'..'P4', 'reasons': [...]} for the current day."""
    p1_pct = float(config.get("p1_watch_percentile", 0.20))
    p3_ret = float(config.get("p3_absolute_return", -0.08))
    p3_pct = float(config.get("p3_percentile", 0.05))
    p4_breadth = float(config.get("p4_breadth", 0.75))
    p4_amount = float(config.get("p4_amount_ratio", 1.5))
    p4_requires_liquidity = bool(
        config.get("p4_requires_limit_down_or_volume", False)
    )

    reasons: list[str] = []
    pct_known = _finite(historical_percentile)

    if not triggered:
        if basket_ret_5d < 0 and pct_known and historical_percentile <= p1_pct:
            reasons.append(
                f"5日收益进入历史最差{p1_pct:.0%}(百分位{historical_percentile:.1%})，"
                "但未触发primary_5d"
            )
            return {"level": "P1", "reasons": reasons}
        return {"level": "P0", "reasons": ["未见异常下跌"]}

    level = "P2"
    reasons.append("primary_5d正式触发")

    p3_hit = basket_ret_5d <= p3_ret or (pct_known and historical_percentile <= p3_pct)
    if p3_hit:
        level = "P3"
        if basket_ret_5d <= p3_ret:
            reasons.append(f"5日跌幅{basket_ret_5d:.1%} <= {p3_ret:.0%}")
        if pct_known and historical_percentile <= p3_pct:
            reasons.append(f"历史百分位{historical_percentile:.1%} <= {p3_pct:.0%}")

        breadth_hit = (
            _finite(active_down_breadth_5d)
            and active_down_breadth_5d >= p4_breadth
        )
        amount_hit = (
            _finite(active_amount_ratio_20d)
            and active_amount_ratio_20d >= p4_amount
        )
        limit_hit = bool(active_limit_down_count and active_limit_down_count > 0)
        p4_hit = (
            amount_hit or limit_hit
            if p4_requires_liquidity else breadth_hit or amount_hit or limit_hit
        )
        stress = []
        if p4_hit and breadth_hit:
            stress.append(
                f"全部核心成员下跌广度{active_down_breadth_5d:.0%} >= {p4_breadth:.0%}"
            )
        if p4_hit and amount_hit:
            stress.append(
                f"全部核心成员成交额放大{active_amount_ratio_20d:.2f}倍 >= {p4_amount:.1f}"
            )
        if p4_hit and limit_hit:
            stress.append(f"{active_limit_down_count}只核心成员跌停(含被gate资格过滤者)")
        if p4_hit:
            level = "P4"
            reasons.extend(stress)

    return {"level": level, "reasons": reasons}

"""Reversal-context assessment: market regime + historical evidence framing.

The regime formula is frozen (identical to the research config):
  bull    : 000300.SH close > MA120 AND 60d return > 0
  bear    : 000300.SH close < MA120 AND 60d return < 0
  neutral : otherwise

Displays sample counts and a Wilson 95% interval — never a point probability.
"""
from __future__ import annotations

import pandas as pd

from .common import wilson_interval

REVERSAL_CANDIDATE = "REVERSAL_CANDIDATE"
REVERSAL_CANDIDATE_LOW_SAMPLE = "REVERSAL_CANDIDATE_LOW_SAMPLE"
REVERSAL_DISABLED = "REVERSAL_DISABLED"


def market_regime_on(index_prices: pd.DataFrame, trade_date: int,
                     config: dict) -> dict:
    """Frozen bull/neutral/bear classification at trade_date (PIT: uses <= date)."""
    from validate_photoresist_panic_thresholds import compute_market_regime

    history = index_prices[index_prices["trade_date"] <= trade_date]
    regime = compute_market_regime(history, config)
    row = regime[regime["trade_date"] == trade_date]
    if row.empty:
        return {"market_regime": "unknown", "market_return_60d": None,
                "market_ma120": None}
    last = row.iloc[-1]
    return {
        "market_regime": str(last["market_regime"]),
        "market_return_60d": float(last["market_return"])
            if pd.notna(last["market_return"]) else None,
        "market_ma120": float(last["market_ma"]) if pd.notna(last["market_ma"]) else None,
    }


def semiconductor_state(index_prices: pd.DataFrame, trade_date: int,
                        semi_code: str = "931865.CSI") -> dict:
    """Companion display of the semiconductor index — never used for selection."""
    semi = index_prices[
        (index_prices["ts_code"] == semi_code)
        & (index_prices["trade_date"] <= trade_date)
    ].sort_values("trade_date")
    if len(semi) < 6:
        return {"semi_ret_5d": None, "semi_ret_60d": None}
    close = semi["close"]
    return {
        "semi_ret_5d": float(close.iloc[-1] / close.iloc[-6] - 1.0),
        "semi_ret_60d": float(close.iloc[-1] / close.iloc[-61] - 1.0)
            if len(semi) >= 61 else None,
    }


def assess_reversal_context(regime: str, triggered: bool, config: dict) -> dict:
    """Map regime -> reversal status with Wilson-CI historical framing."""
    reference = config.get("historical_reference", {})
    n = int(reference.get("sample_size", 0))
    hits_low = int(reference.get("hits_low", 0))
    hits_high = int(reference.get("hits_high", hits_low))
    confidence = float(reference.get("wilson_confidence", 0.95))
    ci_low, _ = wilson_interval(hits_low, n, confidence) if n else (None, None)
    _, ci_high = wilson_interval(hits_high, n, confidence) if n else (None, None)

    eligible = set(config.get("eligible_regimes", ["bull", "neutral"]))
    if not triggered:
        status = "NOT_APPLICABLE"
        explanation = "未触发primary_5d，无反转观察对象。"
    elif regime == "bull":
        status = REVERSAL_CANDIDATE
        explanation = "Bull状态：历史上恐慌后修复概率更有利，进入反转观察。"
    elif regime == "neutral" and "neutral" in eligible:
        status = REVERSAL_CANDIDATE_LOW_SAMPLE
        explanation = "Neutral状态：历史样本较少，反转观察可信度降低。"
    else:
        status = REVERSAL_DISABLED
        explanation = (
            "Bear/unknown状态：历史熊市修复优势未成立，禁止仅依据恐慌信号抄底。"
        )

    return {
        "reversal_status": status,
        "explanation": explanation,
        "market_regime": regime,
        "historical_evidence": {
            "label": reference.get("label", ""),
            "sample_size": n,
            "hits_range": [hits_low, hits_high],
            "hit_rate_range": [round(hits_low / n, 4), round(hits_high / n, 4)]
                if n else None,
            "wilson_ci_95": [round(ci_low, 4), round(ci_high, 4)]
                if ci_low is not None else None,
            "evidence_grade": reference.get("evidence_grade", "初步"),
            "note": reference.get("note", ""),
        },
    }

#!/usr/bin/env python
"""
Risk Gate — pre-trade risk checks.

Enforces:
- Single stock weight caps
- Industry exposure limits
- Single-day turnover caps
- Max order amount
- Data freshness / missing data circuit breaker

Usage:
    python -m live.risk_gate --date 20260105
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

import numpy as np
import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("live.risk_gate")


class RiskGate:
    """Pre-trade risk gate for portfolio rebalancing."""

    def __init__(self, date_str: str,
                 max_single_weight: float = 0.05,
                 max_industry_deviation: float = 0.10,
                 max_turnover: float = 0.30,
                 max_order_amount: float = 10_000_000.0,
                 max_data_missing_ratio: float = 0.20):
        self.date_str = date_str
        self.date_int = int(date_str)
        self.max_single_weight = max_single_weight
        self.max_industry_deviation = max_industry_deviation
        self.max_turnover = max_turnover
        self.max_order_amount = max_order_amount
        self.max_data_missing_ratio = max_data_missing_ratio

    def check(self) -> Dict[str, Any]:
        """
        Run all risk checks.

        Returns dict with:
            verdict: "PASS" | "WARN" | "BLOCK"
            checks: list of individual check results
        """
        checks = []
        signals = self._load_signals()
        orders = self._load_orders()

        # 1. Single stock weight check
        checks.append(self._check_single_weight(signals))

        # 2. Industry exposure check
        checks.append(self._check_industry_exposure(signals))

        # 3. Turnover check
        checks.append(self._check_turnover(orders))

        # 4. Max order amount check
        checks.append(self._check_order_amounts(orders))

        # 5. Data freshness check
        checks.append(self._check_data_freshness())

        # 6. Missing data circuit breaker
        checks.append(self._check_missing_data(signals, orders))

        # Determine verdict
        block_count = sum(1 for c in checks if c["result"] == "BLOCK")
        warn_count = sum(1 for c in checks if c["result"] == "WARN")

        if block_count > 0:
            verdict = "BLOCK"
        elif warn_count > 0:
            verdict = "WARN"
        else:
            verdict = "PASS"

        result = {
            "date": self.date_str,
            "timestamp": datetime.now().isoformat(),
            "verdict": verdict,
            "n_checks": len(checks),
            "n_pass": sum(1 for c in checks if c["result"] == "PASS"),
            "n_warn": warn_count,
            "n_block": block_count,
            "checks": checks,
        }

        return result

    def _load_signals(self) -> pd.DataFrame:
        """Load signals file."""
        path = Path(f"outputs/live/signals_{self.date_str}.csv")
        if not path.exists():
            logger.warning(f"Signals file not found: {path}")
            return pd.DataFrame()
        return pd.read_csv(path)

    def _load_orders(self) -> pd.DataFrame:
        """Load orders file."""
        path = Path(f"outputs/live/orders_{self.date_str}.csv")
        if not path.exists():
            logger.warning(f"Orders file not found: {path}")
            return pd.DataFrame()
        return pd.read_csv(path)

    def _check_single_weight(self, signals: pd.DataFrame) -> dict:
        """Check no single stock exceeds max weight."""
        if signals.empty:
            return {
                "check": "single_weight",
                "result": "WARN",
                "detail": "No signals data",
                "threshold": self.max_single_weight,
            }

        max_w = signals["target_weight"].max()
        violation = max_w > self.max_single_weight

        return {
            "check": "single_weight",
            "result": "BLOCK" if violation else "PASS",
            "detail": f"Max weight={max_w:.4f}",
            "threshold": self.max_single_weight,
            "value": float(max_w),
        }

    def _check_industry_exposure(self, signals: pd.DataFrame) -> dict:
        """Check industry concentration."""
        if signals.empty:
            return {
                "check": "industry_exposure",
                "result": "WARN",
                "detail": "No signals data — cannot check industry exposure",
            }

        try:
            from data.industry import get_industry_classifier
            ic = get_industry_classifier()
            if not ic.has_data:
                return {
                    "check": "industry_exposure",
                    "result": "WARN",
                    "detail": "Industry data not available",
                }

            codes = list(signals["ts_code"])
            industries = ic.get_industries(codes, self.date_int)

            if not industries:
                return {
                    "check": "industry_exposure",
                    "result": "WARN",
                    "detail": "No industry assignments for signal stocks",
                }

            # Count weight per industry
            ind_series = pd.Series(industries)
            ind_weights = signals.set_index("ts_code")["target_weight"].groupby(
                ind_series
            ).sum()

            max_ind = ind_weights.max()
            # Equal-weight benchmark: 1 / n_industries
            n_industries = len(ind_weights)
            benchmark = 1.0 / n_industries if n_industries > 0 else 0
            deviation = max_ind - benchmark

            violation = deviation > self.max_industry_deviation

            return {
                "check": "industry_exposure",
                "result": "WARN" if violation else "PASS",
                "detail": f"Max industry={max_ind:.2%}, deviation={deviation:.2%}",
                "threshold": self.max_industry_deviation,
                "value": float(deviation),
            }
        except Exception as e:
            return {
                "check": "industry_exposure",
                "result": "WARN",
                "detail": f"Industry check error: {e}",
            }

    def _check_turnover(self, orders: pd.DataFrame) -> dict:
        """Check single-day turnover."""
        if orders.empty:
            return {
                "check": "turnover",
                "result": "PASS",
                "detail": "No orders — zero turnover",
                "value": 0.0,
            }

        ready_orders = orders[orders["status"] == "READY"]
        if ready_orders.empty:
            return {
                "check": "turnover",
                "result": "PASS",
                "detail": "No ready orders",
                "value": 0.0,
            }

        # One-way turnover = sum(abs(weight_change)) / 2
        turnover = ready_orders["weight_change"].abs().sum() / 2.0
        violation = turnover > self.max_turnover

        return {
            "check": "turnover",
            "result": "WARN" if violation else "PASS",
            "detail": f"One-way turnover={turnover:.2%}",
            "threshold": self.max_turnover,
            "value": float(turnover),
        }

    def _check_order_amounts(self, orders: pd.DataFrame) -> dict:
        """Check no single order exceeds max amount."""
        if orders.empty:
            return {
                "check": "order_amount",
                "result": "PASS",
                "detail": "No orders",
            }

        ready = orders[orders["status"] == "READY"]
        if ready.empty:
            return {
                "check": "order_amount",
                "result": "PASS",
                "detail": "No ready orders",
            }

        max_amt = ready["amount"].max()
        violation = max_amt > self.max_order_amount
        n_violations = len(ready[ready["amount"] > self.max_order_amount])

        return {
            "check": "order_amount",
            "result": "BLOCK" if violation else "PASS",
            "detail": f"Max order={max_amt:,.0f} CNY ({n_violations} violations)",
            "threshold": self.max_order_amount,
            "value": float(max_amt),
        }

    def _check_data_freshness(self) -> dict:
        """Check that input data is from the expected date."""
        signals_path = Path(f"outputs/live/signals_{self.date_str}.csv")
        orders_path = Path(f"outputs/live/orders_{self.date_str}.csv")

        issues = []
        if not signals_path.exists():
            issues.append("signals file missing")
        if not orders_path.exists():
            issues.append("orders file missing")

        if issues:
            return {
                "check": "data_freshness",
                "result": "BLOCK",
                "detail": "; ".join(issues),
            }

        return {
            "check": "data_freshness",
            "result": "PASS",
            "detail": "All data files present",
        }

    def _check_missing_data(self, signals: pd.DataFrame,
                            orders: pd.DataFrame) -> dict:
        """Circuit breaker: too many missing prices/statuses."""
        if orders.empty and signals.empty:
            return {
                "check": "missing_data_cb",
                "result": "BLOCK",
                "detail": "No signals and no orders — data pipeline likely broken",
            }

        if orders.empty:
            return {
                "check": "missing_data_cb",
                "result": "WARN",
                "detail": "No orders to check",
            }

        total = len(orders)
        blocked = len(orders[orders["status"] != "READY"])
        ratio = blocked / total if total > 0 else 0

        violation = ratio > self.max_data_missing_ratio

        return {
            "check": "missing_data_cb",
            "result": "BLOCK" if violation else "PASS",
            "detail": f"{blocked}/{total} orders blocked ({ratio:.1%})",
            "threshold": self.max_data_missing_ratio,
            "value": float(ratio),
        }

    def save_result(self, result: dict, output_dir: str = None):
        """Save risk check result to JSON."""
        out_dir = Path(output_dir or "outputs/live")
        out_dir.mkdir(parents=True, exist_ok=True)

        filepath = out_dir / f"risk_checks_{self.date_str}.json"
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False, default=str)
        logger.info(f"Risk checks saved to {filepath}")
        return str(filepath)


def main():
    parser = argparse.ArgumentParser(
        description="Pre-trade risk checks"
    )
    parser.add_argument("--date", type=str, required=True,
                       help="Signal date YYYYMMDD")
    parser.add_argument("--max-weight", type=float, default=0.05,
                       help="Max single stock weight")
    parser.add_argument("--max-turnover", type=float, default=0.30,
                       help="Max one-way turnover")
    parser.add_argument("--max-order", type=float, default=10_000_000.0,
                       help="Max single order amount in CNY")

    args = parser.parse_args()
    gate = RiskGate(
        date_str=args.date,
        max_single_weight=args.max_weight,
        max_turnover=args.max_turnover,
        max_order_amount=args.max_order,
    )

    result = gate.check()
    gate.save_result(result)

    print(f"\nRisk Gate Result: {result['verdict']}")
    print(f"  Pass: {result['n_pass']}, Warn: {result['n_warn']}, "
          f"Block: {result['n_block']}")
    print()
    for check in result["checks"]:
        icon = {"PASS": "+", "WARN": "~", "BLOCK": "X"}.get(
            check["result"], "?"
        )
        print(f"  [{icon}] {check['check']}: {check['detail']}")

    return 1 if result["verdict"] == "BLOCK" else 0


if __name__ == "__main__":
    sys.exit(main())

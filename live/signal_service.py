#!/usr/bin/env python
"""
Signal Service — generate target portfolio signals.

Reads the latest processed data, computes the composite score from
enabled factors, and selects the top N stocks for the portfolio.

Usage:
    python -m live.signal_service --date 20260105
    python -m live.signal_service --date 20260105 --top-n 50
"""

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("live.signal_service")


class SignalService:
    """Generate target portfolio signals from latest data."""

    def __init__(self, date_str: str, top_n: int = 50,
                 weight_max: float = 0.02):
        self.date_str = date_str
        self.top_n = top_n
        self.weight_max = weight_max
        self.date_int = int(date_str)

    def generate_signals(self) -> pd.DataFrame:
        """
        Generate target portfolio signals for the given date.

        Returns DataFrame with columns:
            ts_code, composite_score, rank, target_weight
        """
        from data.panel_loader import get_loader
        from data.calendar import get_calendar
        from alpha.ic_weighting import ICWeighting

        loader = get_loader()
        calendar = get_calendar()
        calendar.load(start_date="20160101", end_date=self.date_str)

        # Load factor config from shared module (not run_research.py)
        from configs.factor_config import load_factor_config
        factor_config = load_factor_config()
        enabled = factor_config["enabled_factors"]
        composite_params = factor_config["composite_params"]

        # Load factor data
        factor_names = self._get_available_factors()
        if enabled:
            factor_names = [f for f in factor_names if f in enabled]
            logger.info(f"Using {len(factor_names)} enabled factors: {factor_names}")

        if not factor_names:
            logger.error("No factors available for signal generation")
            return pd.DataFrame()

        # Determine a lookback window for IC computation
        lookback_start = str(max(20160101, self.date_int - 20000))

        factor_dfs = {}
        for name in factor_names:
            df = loader.read_factor(name, lookback_start, self.date_str)
            if not df.empty:
                factor_dfs[name] = df

        fwd_rets = loader.read_factor("fwd_returns", lookback_start, self.date_str)

        if not factor_dfs or fwd_rets.empty:
            logger.error("Insufficient data for signal generation")
            return pd.DataFrame()

        # Compute composite score
        signal_dates = calendar.weekly_rebalance_dates(
            lookback_start, self.date_str
        )
        signal_dates_int = [int(d) for d in signal_dates]

        icw = ICWeighting(**composite_params)
        composite = icw.compute_composite_series(
            factor_dfs, fwd_rets, signal_dates_int
        )

        if composite.empty:
            logger.error(f"No composite scores generated for {self.date_str}")
            return pd.DataFrame()

        # Get signal for target date
        day_scores = composite[composite["trade_date"] == self.date_int]
        if day_scores.empty:
            logger.warning(
                f"No scores for {self.date_str} — "
                f"using most recent date available"
            )
            latest_date = composite["trade_date"].max()
            day_scores = composite[composite["trade_date"] == latest_date]

        if day_scores.empty:
            return pd.DataFrame()

        # Select top N and assign equal weights
        top = day_scores.nlargest(self.top_n, "composite_score")
        top = top.copy()
        top["rank"] = range(1, len(top) + 1)
        top["target_weight"] = 1.0 / self.top_n

        logger.info(
            f"Generated {len(top)} signals for {self.date_str}"
        )
        return top[["ts_code", "composite_score", "rank", "target_weight"]]

    def _get_available_factors(self):
        """Get list of available _cs factor names from cache."""
        import glob
        dirs = glob.glob("data/parquet/factors/factor_name=*")
        return sorted([
            Path(d).name.replace("factor_name=", "")
            for d in dirs if "_cs" in Path(d).name
        ])

    def save_signals(self, signals: pd.DataFrame, output_dir: str = None):
        """Save signals to CSV."""
        if signals.empty:
            logger.warning("No signals to save")
            return

        out_dir = Path(output_dir or "outputs/live")
        out_dir.mkdir(parents=True, exist_ok=True)

        filename = f"signals_{self.date_str}.csv"
        filepath = out_dir / filename
        signals.to_csv(filepath, index=False)
        logger.info(f"Signals saved to {filepath}")
        return str(filepath)


def main():
    parser = argparse.ArgumentParser(
        description="Generate target portfolio signals"
    )
    parser.add_argument("--date", type=str, required=True,
                       help="Signal date YYYYMMDD")
    parser.add_argument("--top-n", type=int, default=50,
                       help="Number of stocks in portfolio")
    parser.add_argument("--output-dir", type=str, default="outputs/live",
                       help="Output directory")

    args = parser.parse_args()
    service = SignalService(date_str=args.date, top_n=args.top_n)
    signals = service.generate_signals()

    if signals.empty:
        logger.error("Failed to generate signals")
        return 1

    service.save_signals(signals, output_dir=args.output_dir)
    print(f"\nSignals ({len(signals)} stocks):")
    print(signals.to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

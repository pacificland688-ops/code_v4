#!/usr/bin/env python
"""
code_v4 Main Research Entry Point

CSI 300 Cross-Sectional Multi-Factor Strategy

Usage:
    # Phase 0: data pipeline
    python run_research.py phase0 --start 20160101 --end 20251231

    # Phase 1: factor computation + evaluation
    python run_research.py phase1 --start 20160101 --end 20251231

    # Phase 2: MVP backtest (IC-weighted top N)
    python run_research.py phase2 --top-n 50 --start 20160101

    # Phase 3: portfolio optimization
    python run_research.py phase3 --start 20160101

    # Phase 4: ML alpha
    python run_research.py phase4 --start 20160101

    # Phase 5: robustness tests
    python run_research.py phase5 --start 20160101

    # Full pipeline
    python run_research.py all --start 20160101

Environment:
    TUSHARE_TOKEN must be set in .env file.
"""

import argparse
import hashlib
import json
import logging
import sys
import uuid
from copy import deepcopy
from datetime import datetime
from pathlib import Path

import pandas as pd

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("code_v4")


# ===================================================================
# Safe console output (handles Windows GBK code pages)
# ===================================================================
def safe_print(text: str) -> None:
    """Print text safely on Windows consoles with non-UTF-8 code pages.

    On Windows with GBK (cp936), Unicode characters like ✓ ✗ →
    cause UnicodeEncodeError.  This fallback replaces unencodable
    characters instead of crashing.
    """
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode(encoding, errors="replace").decode(encoding, errors="replace"))


# ===================================================================
# Strategy parameter keys — all params that affect backtest results.
# Batch 3: single source of truth for parameter forwarding.
# ===================================================================
STRATEGY_PARAM_KEYS = [
    "entry_rank", "exit_rank",
    "turnover_max", "turnover_penalty",
    "no_trade_band", "max_weight_change",
    "score_smoothing_halflife", "hold_buffer_mode",
    "cost_aware_lambda", "estimated_cost_bps",
    "cov_shrinkage", "constraint_relaxation",
]


def _strategy_kwargs_from_args(args) -> dict:
    """Extract strategy parameters from CLI args into a kwargs dict."""
    return {
        "entry_rank": getattr(args, "entry_rank", None),
        "exit_rank": getattr(args, "exit_rank", None),
        "turnover_max": getattr(args, "turnover_max", None),
        "turnover_penalty": getattr(args, "turnover_penalty", None),
        "no_trade_band": getattr(args, "no_trade_band", 0.0),
        "max_weight_change": getattr(args, "max_weight_change", None),
        "score_smoothing_halflife": getattr(args, "score_smoothing_halflife", None),
        "hold_buffer_mode": getattr(args, "hold_buffer_mode", "standard"),
        "cost_aware_lambda": getattr(args, "cost_aware_lambda", 0.0),
        "estimated_cost_bps": getattr(args, "estimated_cost_bps", 10.0),
        "cov_shrinkage": getattr(args, "cov_shrinkage", "ledoit_wolf"),
        "constraint_relaxation": getattr(args, "constraint_relaxation", "none"),
    }


def _merge_strategy_kwargs(args, kwargs: dict) -> dict:
    """Merge CLI defaults with override kwargs, prioritizing kwargs."""
    merged = _strategy_kwargs_from_args(args)
    for key in STRATEGY_PARAM_KEYS:
        if key in kwargs and kwargs[key] is not None:
            merged[key] = kwargs[key]
    return merged


def _build_backtester(start_date: str, end_date: str, loader=None):
    """Create a backtester with explicitly loaded runtime dependencies."""
    from backtest.portfolio_backtester import PortfolioBacktester
    from data.universe import get_universe_builder
    from data.tradable import get_tradable

    universe = get_universe_builder()
    universe.load(start_date=start_date, end_date=end_date)

    tradable = get_tradable()
    tradable.load(start_date=start_date, end_date=end_date)

    return PortfolioBacktester(
        universe_builder=universe,
        tradable_mask=tradable,
        panel_loader=loader,
    )


def _check_phase2_price_quality(loader, start_date: str, end_date: str) -> bool:
    """Validate cached adjusted prices before Phase 2 backtests.

    Phase 2 can run from existing caches, so Phase 0 validation is not enough:
    stale or partially rebuilt ``prices_adj`` partitions can still be present.
    This catches extreme adjusted-price jumps before they inflate returns.

    The validation is scoped to stocks that have appeared in the CSI 300
    point-in-time index_weight cache by ``end_date``.  The adjusted-price cache
    can contain broader-market symbols that are irrelevant to this strategy;
    blocking Phase 2 on those non-universe rows would make historical backtests
    fail for data the backtester can never trade.
    """
    try:
        from data.adjust import validate_adj_prices
    except Exception as e:
        logger.error(f"Cannot import price validator: {e}")
        return False

    universe_codes = None
    try:
        index_weight = loader.query(
            "index_weight",
            columns=["ts_code", "trade_date"],
            start_date="20150101",
            end_date=end_date,
        )
        if not index_weight.empty and "ts_code" in index_weight:
            universe_codes = sorted(index_weight["ts_code"].astype(str).unique().tolist())
    except Exception as e:
        logger.warning(
            "Failed to load index_weight for Phase 2 price-quality scoping; "
            f"falling back to all cached prices. Error: {e}"
        )

    try:
        adj_prices = loader.query(
            "prices_adj",
            columns=["ts_code", "trade_date", "adj_close", "adj_factor"],
            start_date=start_date,
            end_date=end_date,
            ts_codes=universe_codes,
        )
    except Exception as e:
        logger.error(f"Failed to load prices_adj for Phase 2 quality check: {e}")
        return False

    if adj_prices.empty:
        logger.error(
            f"prices_adj quality check failed: no rows for {start_date}->{end_date}. "
            f"RUN Phase 0 FIRST: python run_research.py phase0 "
            f"--start {start_date} --end {end_date}"
        )
        return False

    validation = validate_adj_prices(adj_prices, raw_prices=None)
    if validation.get("status") != "OK":
        failures = validation.get("failures", [])
        logger.error(
            "prices_adj quality check failed before Phase 2. "
            f"n_rows={len(adj_prices)}, "
            f"n_daily_jumps={validation.get('n_daily_jumps')}, "
            f"n_weekly_jumps={validation.get('n_weekly_jumps')}, "
            f"n_duplicates={validation.get('n_duplicates')}, "
            f"missing_ratio={validation.get('missing_ratio', 0):.2%}. "
            f"First failures: {failures[:3]}"
        )
        fail_dir = Path("outputs/price_quality_failures")
        fail_dir.mkdir(parents=True, exist_ok=True)
        fail_path = fail_dir / f"phase2_{start_date}_{end_date}.json"
        with open(fail_path, "w", encoding="utf-8") as f:
            json.dump(validation, f, indent=2, default=str)
        logger.error(
            f"Detailed price-quality failure written to {fail_path}. "
            "Fix prices_adj/adj_factor cache and re-run Phase 0 before Phase 2."
        )
        return False

    logger.info(
        "prices_adj quality check OK before Phase 2: "
        f"n_rows={len(adj_prices)}, "
        f"n_universe_codes={len(universe_codes) if universe_codes is not None else 'ALL'}, "
        f"n_daily_jumps={validation.get('n_daily_jumps')}, "
        f"n_weekly_jumps={validation.get('n_weekly_jumps')}"
    )
    return True


def _get_cached_cs_factors():
    """Return cached cross-sectional factor names."""
    import glob

    dirs = glob.glob("data/parquet/factors/factor_name=*")
    return sorted([
        Path(d).name.replace("factor_name=", "")
        for d in dirs if "_cs" in Path(d).name
    ])


def _select_valid_cs_factors(loader, calendar, start_date: str, end_date: str):
    """Select _cs factors using the same coverage rules as Phase 2."""
    factor_names = _get_cached_cs_factors()
    if not factor_names:
        return []

    expected_signal_dates = set(
        int(d) for d in calendar.weekly_rebalance_dates(start_date, end_date)
    )
    min_dates = max(16, int(len(expected_signal_dates) * 0.5))

    valid_factors = []
    for name in factor_names:
        cov = loader.factor_coverage(name, start_date, end_date)
        if cov["rows"] == 0 or cov["n_dates"] < min_dates:
            continue

        df_temp = loader.query(
            f"factors/factor_name={name}",
            columns=["trade_date"],
            start_date=start_date,
            end_date=end_date,
        )
        if df_temp.empty or not expected_signal_dates:
            continue

        actual_dates = set(df_temp["trade_date"].unique())
        coverage_ratio = len(actual_dates & expected_signal_dates) / len(expected_signal_dates)
        if coverage_ratio < 0.6:
            continue

        valid_factors.append(name)

    return valid_factors


def _load_factor_config(config_path=None):
    """Load factor + composite config from a YAML file.

    Delegates to ``configs.factor_config.load_factor_config()`` so that
    all modules share one configuration source of truth.

    Parameters
    ----------
    config_path : str, optional
        Path to a factors YAML.  Defaults to ``configs/factors.yaml``.

    Returns
    -------
    dict
        Keys: ``enabled_factors``, ``composite_params``, ``cross_section_params``.
    """
    from configs.factor_config import load_factor_config
    return load_factor_config(config_path)


def _factors_config_path(args) -> str:
    """Return the factors-config path from parsed CLI args.

    Handles the case where ``args`` is a plain namespace without the
    ``factors_config`` attribute (programmatic / test calls).
    """
    return getattr(args, "factors_config", "configs/factors.yaml")


def _normalize_factor_config(config):
    """Normalize a factor config to the dict shape expected by callers.

    Backward-compat: if ``_load_factor_config`` was mocked in tests to
    return a plain list (the old API), wrap it.
    """
    if isinstance(config, list):
        return {
            "enabled_factors": config,
            "composite_params": {},
            "cross_section_params": {},
        }
    return config


def _filter_enabled_factors(factor_names: list, enabled_factors: list | None = None):
    """Filter factor_names to only include enabled factors.

    Semantic contract:
        - ``enabled_factors is None``   → no filter specified → return all (compat)
        - ``enabled_factors == []``     → explicitly empty pool → return []
        - ``enabled_factors`` non-empty → return intersection

    .. warning::
        An explicitly empty list means NO factors are enabled.  Do NOT
        fall back to all factors — that would silently run on the full
        universe when the config intends an empty candidate pool.
    """
    if enabled_factors is None:
        return factor_names
    filtered = [f for f in factor_names if f in enabled_factors]
    if len(filtered) < len(factor_names):
        logger.info(
            f"Factor filter: {len(factor_names)} available → "
            f"{len(filtered)} enabled (whitelist: {len(enabled_factors)} entries)"
        )
    return filtered


def _check_formal_candidate_policy(factor_config: dict, config_path: str = "configs/factors.yaml") -> int | None:
    """Enforce formal candidate policy.  Returns exit code or None.

    When the config declares ``candidate_policy.formal_candidate=true``
    and ``require_non_empty_enabled_factors=true``, an empty
    ``enabled_factors`` list is a hard error — the run MUST abort.

    Returns
    -------
    int or None
        Non-zero exit code if policy is violated, ``None`` if OK.
    """
    from configs.factor_config import validate_candidate_policy

    result = validate_candidate_policy(factor_config)
    if result["valid"]:
        return None

    logger.error(
        "Formal candidate policy violated for %s: %s",
        config_path,
        result["blocked_reason"],
    )
    return 1


def _load_regime_config_safe(config_path: str = "configs/regime.yaml") -> dict:
    """Load regime YAML config, returning empty dict on failure."""
    try:
        import yaml
        path = Path(config_path)
        if not path.exists():
            return {}
        with open(path, "r", encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except Exception:
        return {}


def _select_regime_candidate_factors(loader, regime_config: dict,
                                      start_date: str, end_date: str,
                                      factor_config: dict = None) -> list:
    """Return union of all factors declared in regime strategy_sleeves.

    Only keeps factors that exist in the parquet cache (via loader).
    When ``factor_config`` is provided, also validates against
    ``enabled_factors``: disabled factors in sleeves trigger a warning.
    """
    sleeves = regime_config.get("strategy_sleeves", {})
    all_factors: set = set()
    for sleeve_name, cfg in sleeves.items():
        if isinstance(cfg, dict):
            factors = cfg.get("factors", [])
        elif isinstance(cfg, list):
            factors = cfg
        else:
            continue
        for f in factors:
            all_factors.add(f)

    if not all_factors:
        logger.warning("No factors found in regime strategy_sleeves")
        return []

    # --- Validate against enabled_factors if factor_config is provided ---
    if factor_config:
        enabled_factors = factor_config.get("enabled_factors", [])
        if enabled_factors:
            disabled_in_sleeves = []
            for fname in sorted(all_factors):
                if fname not in enabled_factors:
                    disabled_in_sleeves.append(fname)
            if disabled_in_sleeves:
                logger.warning(
                    "Regime sleeves reference %d factor(s) NOT in enabled_factors: %s. "
                    "These factors will be SKIPPED. "
                    "Update regime config or add them to enabled_factors.",
                    len(disabled_in_sleeves), disabled_in_sleeves,
                )
                # Remove disabled factors from the pool
                for fname in disabled_in_sleeves:
                    all_factors.discard(fname)

    # Keep only factors that exist in cache
    valid = []
    missing = []
    for fname in sorted(all_factors):
        cov = loader.factor_coverage(fname, start_date, end_date)
        if cov.get("rows", 0) > 0:
            valid.append(fname)
        else:
            missing.append(fname)

    if missing:
        logger.warning(
            "Regime factors not in cache (will be skipped): %s", missing
        )

    # --- P1-3: hard-fail for shock_reversal factors declared but missing ---
    _validate_shock_factor_requirements(
        loader, regime_config, all_factors, valid, start_date, end_date
    )

    logger.info(
        "Regime factor pool: %d total cached, %d missing",
        len(valid), len(missing),
    )
    return valid


def _validate_shock_factor_requirements(
    loader, regime_config: dict, all_factors: set, valid: list,
    start_date: str, end_date: str,
) -> None:
    """P1-3 fix: hard-fail when shock_reversal is declared but not cached.

    If the regime config declares ``abnormal_drop_reversal_5_cs`` in any
    sleeve and the factor is NOT in the parquet cache (or coverage is
    severely insufficient), this function raises a RuntimeError rather
    than silently skipping the sleeve.

    Thresholds:
      - n_dates >= 70% of approximate signal dates in range
      - min 30 stocks per valid date on average
    """
    # Check if any sleeve references shock_reversal factors
    shock_factors_declared = {
        f for f in all_factors if f.startswith("abnormal_drop_reversal")
    }
    if not shock_factors_declared:
        return  # No shock factors declared — nothing to validate

    sleeves = regime_config.get("strategy_sleeves", {})
    shock_sleeve_configured = "shock_reversal" in sleeves

    if not shock_sleeve_configured:
        # Shock factors listed in other sleeves — unusual but not an error
        logger.info(
            "Shock factors %s declared outside shock_reversal sleeve",
            shock_factors_declared,
        )
        return

    for fname in sorted(shock_factors_declared):
        if fname in valid:
            # Factor is cached — verify coverage
            cov = loader.factor_coverage(fname, start_date, end_date)
            n_dates = cov.get("n_dates", 0)
            n_stocks_avg = cov.get("rows", 0) / max(n_dates, 1)

            # Approximate expected signal dates (weekly, ~52 per year)
            years = int(end_date[:4]) - int(start_date[:4]) + 1
            expected_dates = years * 52
            min_dates = int(expected_dates * 0.70)

            if n_dates < min_dates:
                raise RuntimeError(
                    f"shock_reversal declared but {fname} has insufficient "
                    f"coverage: {n_dates} dates (need >= {min_dates}, "
                    f"70% of ~{expected_dates} signal dates). "
                    f"Run: python scripts/build_shock_reversal_factor.py "
                    f"--start {start_date} --end {end_date} --recompute"
                )

            if n_stocks_avg < 30:
                raise RuntimeError(
                    f"shock_reversal declared but {fname} has too few stocks "
                    f"per date: avg {n_stocks_avg:.0f} (need >= 30). "
                    f"Factor may be corrupted — rebuild with --recompute."
                )

            logger.info(
                "Shock factor %s coverage OK: %d dates, avg %.0f stocks/date",
                fname, n_dates, n_stocks_avg,
            )
        else:
            # Factor NOT in cache at all
            raise RuntimeError(
                f"shock_reversal sleeve is declared in regime config but "
                f"'{fname}' is MISSING from parquet cache. "
                f"Cannot silently skip — this sleeve must be validated. "
                f"Run: python scripts/build_shock_reversal_factor.py "
                f"--start {start_date} --end {end_date} --recompute"
            )


def _compute_regime_load_window(start_date: str, end_date: str,
                                 regime_config: dict,
                                 factor_config: dict = None,
                                 calendar=None) -> tuple:
    """Return (data_start_date, data_end_date) with enough warmup for regime.

    Warmup covers:
      - max(ma_long, return_windows, drawdown_window + bread_window) trading days
      - ic_window_months + 1 calendar months for rolling IC
    """
    detector_cfg = regime_config.get("regime_detector", {})
    trend_cfg = detector_cfg.get("trend", {})
    vol_cfg = detector_cfg.get("volatility", {})
    breadth_cfg = detector_cfg.get("breadth", {})

    # Max lookback from regime features
    ma_long = trend_cfg.get("ma_long", 120)
    return_windows = trend_cfg.get("return_windows", [20, 60, 120])
    dd_window = vol_cfg.get("drawdown_window", 60)
    breadth_ma = breadth_cfg.get("ma_window", 60)

    regime_td_needed = max(ma_long, max(return_windows), dd_window, breadth_ma + 20)

    # Approximate calendar days for that many trading days
    regime_cal_days = int(regime_td_needed * 1.45)

    # IC window warmup
    composite_cfg = regime_config.get("sleeve_composite", {})
    ic_months = composite_cfg.get("ic_window_months", 6)

    from datetime import datetime
    from dateutil.relativedelta import relativedelta

    end_dt = datetime.strptime(end_date, "%Y%m%d")
    start_dt = datetime.strptime(start_date, "%Y%m%d")

    # IC warmup: go back ic_months + 1
    ic_warmup_dt = start_dt - relativedelta(months=ic_months + 1)
    ic_warmup_str = ic_warmup_dt.strftime("%Y%m%d")

    # Regime feature warmup: go back ~regime_cal_days
    from datetime import timedelta
    regime_warmup_dt = start_dt - timedelta(days=regime_cal_days)
    regime_warmup_str = regime_warmup_dt.strftime("%Y%m%d")

    # Take the earlier of the two
    data_start = min(ic_warmup_str, regime_warmup_str)

    logger.info(
        "Regime load window: backtest=%s→%s, data=%s→%s "
        "(warmup: %d td regime + %d mo IC)",
        start_date, end_date, data_start, end_date,
        regime_td_needed, ic_months,
    )

    return data_start, end_date


# ===================================================================
# Regime composite builder (Phase 2 / Phase 3 integration)
# ===================================================================
def _build_regime_scoring_signal_dates(
    target_signal_dates: list,
    data_start_date: str,
    data_end_date: str,
    calendar,
) -> list:
    """Return warmup + target signal dates for regime IC/coverage computation.

    Generates weekly rebalance dates across the full data window (including
    warmup), unions them with the target signal dates, and returns a sorted,
    deduplicated list.  This ensures that the warmup period's data contributes
    to factor alignment, regime detection, sleeve IC, and allocator weights.

    Parameters
    ----------
    target_signal_dates : list of int
        Real backtest / OOS target rebalance dates (YYYYMMDD).
    data_start_date : str
        Extended data loading start (includes warmup), e.g. "20220601".
    data_end_date : str
        Extended data loading end (includes OOS), e.g. "20231231".
    calendar : TradingCalendar
        Calendar instance with ``weekly_rebalance_dates()``.

    Returns
    -------
    list of int
        Sorted, deduplicated union of warmup weekly dates and target dates.
    """
    target_set = set(int(d) for d in target_signal_dates)

    # Generate warmup weekly rebalance dates across the full data window
    try:
        warmup_weekly_strs = calendar.weekly_rebalance_dates(
            data_start_date, data_end_date
        )
        warmup_weekly = [int(d) for d in warmup_weekly_strs]
    except Exception:
        warmup_weekly = []

    # Union: target + warmup weekly, sorted and deduplicated
    scoring = sorted(set(warmup_weekly) | target_set)

    logger.info(
        "Regime scoring signal dates: target=%d, warmup_weekly=%d, union=%d "
        "(data_window=%s→%s)",
        len(target_set), len(warmup_weekly), len(scoring),
        data_start_date, data_end_date,
    )

    return scoring


def build_regime_composite(
    factor_dfs: dict,
    fwd_rets,
    signal_dates_int: list,
    regime_config_path: str,
    start_date: str,
    end_date: str,
    loader=None,
    data_start_date: str = None,
    data_end_date: str = None,
):
    """Build regime-routed composite score.

    Orchestrates the full regime pipeline:
      Factor alignment → RegimeDetector → RegimeAllocator
      → StrategySleeveEngine → RegimeCompositeBuilder → final composite_score

    Parameters
    ----------
    factor_dfs : dict
        ``{factor_name: DataFrame}`` with all available factor panels.
    fwd_rets : pd.DataFrame
        Forward returns panel.
    signal_dates_int : list of int
        Signal dates YYYYMMDD.
    regime_config_path : str
        Path to regime YAML config.
    start_date : str
        Backtest start date YYYYMMDD.
    end_date : str
        Backtest end date YYYYMMDD.
    loader : PanelLoader, optional
        Data loader for index and prices data.
    data_start_date : str, optional
        Extended data loading start (includes warmup). Falls back to start_date.
    data_end_date : str, optional
        Extended data loading end (includes OOS). Falls back to end_date.

    Returns
    -------
    composite : pd.DataFrame
        ``[ts_code, trade_date, composite_score]``.
    diagnostics : dict
        Debug info with skip reasons, sleeve coverage, etc.
    """
    import yaml
    import numpy as np
    import pandas as pd
    from alpha.regime_detector import RegimeDetector
    from alpha.regime_allocator import RegimeAllocator
    from alpha.strategy_sleeves import StrategySleeveEngine
    from alpha.regime_composite import RegimeCompositeBuilder
    from alpha.sleeve_performance_overlay import SleevePerformanceOverlay
    from alpha.factor_alignment import align_factors_to_signal_dates

    # Data loading windows
    load_start = data_start_date or start_date
    load_end = data_end_date or end_date

    diagnostics: dict = {
        "loaded_factors": list(factor_dfs.keys()),
        "missing_factors": [],
        "skip_reasons": {},
    }

    # 1. Load regime config
    regime_path = Path(regime_config_path)
    if not regime_path.exists():
        logger.error("Regime config not found: %s", regime_config_path)
        diagnostics["error"] = "regime_config_not_found"
        return pd.DataFrame(), diagnostics

    with open(regime_path, "r", encoding="utf-8") as fh:
        regime_config = yaml.safe_load(fh) or {}

    detector_cfg = regime_config.get("regime_detector", {})
    sleeve_cfg = regime_config.get("strategy_sleeves", {})
    composite_cfg = regime_config.get("sleeve_composite", {})
    allocator_cfg = regime_config.get("allocator", {})
    overlay_cfg = regime_config.get("sleeve_performance_overlay", {})
    alignment_cfg = regime_config.get("factor_alignment", {})

    # --- Log regime factor pool ---
    all_sleeve_factors: set = set()
    for sname, scfg in sleeve_cfg.items():
        factors = scfg.get("factors", []) if isinstance(scfg, dict) else (scfg if isinstance(scfg, list) else [])
        all_sleeve_factors.update(factors)
        logger.info("Sleeve '%s': factors=%s", sname, factors)

    missing_from_cache = [f for f in all_sleeve_factors if f not in factor_dfs]
    diagnostics["missing_factors"] = missing_from_cache
    if missing_from_cache:
        logger.warning("Regime factors missing from cache: %s", missing_from_cache)

    # 2. Set up calendar and compute scoring signal dates (warmup + target union)
    from data.calendar import get_calendar as _get_cal_aligned
    cal = _get_cal_aligned()
    cal.load(start_date="20150101", end_date=load_end)

    target_signal_dates = sorted(set(int(d) for d in signal_dates_int))
    scoring_signal_dates = _build_regime_scoring_signal_dates(
        target_signal_dates=target_signal_dates,
        data_start_date=load_start,
        data_end_date=load_end,
        calendar=cal,
    )
    diagnostics["target_signal_dates_count"] = len(target_signal_dates)
    diagnostics["scoring_signal_dates_count"] = len(scoring_signal_dates)
    diagnostics["warmup_signal_dates_count"] = len(scoring_signal_dates) - len(
        set(target_signal_dates) & set(scoring_signal_dates)
    )

    # 3. Factor alignment (PIT as-of for monthly fundamental factors)
    if alignment_cfg:
        logger.info("Applying PIT as-of factor alignment...")
        _all_td = sorted(int(d) for d in cal.trade_days_between(
            int(load_start), int(load_end)
        ))
        factor_dfs_aligned = align_factors_to_signal_dates(
            factor_dfs, scoring_signal_dates, alignment_cfg,
            trade_dates=_all_td,
        )
        # Count aligned coverage — structured for debugging
        aligned_cov = {}
        for name, adf in factor_dfs_aligned.items():
            if adf.empty:
                aligned_cov[name] = {"rows": 0, "n_dates": 0, "min_date": None, "max_date": None}
                # Mark alignment failure in skip reasons
                if name in all_sleeve_factors:
                    diagnostics["skip_reasons"][name] = "alignment_empty_or_failed"
            else:
                aligned_cov[name] = {
                    "rows": len(adf),
                    "n_dates": adf["trade_date"].nunique(),
                    "min_date": int(adf["trade_date"].min()),
                    "max_date": int(adf["trade_date"].max()),
                }
        diagnostics["aligned_factor_coverage"] = aligned_cov
    else:
        factor_dfs_aligned = factor_dfs

    # 3. Load index data (use extended load window for warmup)
    index_code = detector_cfg.get("index_code", "000300.SH")
    index_df = pd.DataFrame()
    if loader is not None:
        try:
            index_df = loader.query(
                "index_daily",
                columns=["ts_code", "trade_date", "close", "vol"],
                start_date=load_start,
                end_date=load_end,
            )
            if not index_df.empty:
                index_df = index_df[index_df["ts_code"] == index_code]
        except Exception as exc:
            logger.warning("Failed to load index_daily via loader: %s — trying TushareClient", exc)

    if index_df.empty:
        try:
            from data.tushare_client import get_client
            client = get_client()
            index_df = client.get_index_daily(
                index_code=index_code,
                start_date=load_start,
                end_date=load_end,
                allow_partial=True,
            )
        except Exception as exc:
            logger.error("Failed to load index data: %s", exc)
            diagnostics["error"] = f"index_data_load_failed: {exc}"
            return pd.DataFrame(), diagnostics

    if index_df.empty:
        logger.error("Index data is empty — cannot compute regime features")
        diagnostics["error"] = "index_data_empty"
        return pd.DataFrame(), diagnostics

    # 4. Load prices for breadth (best-effort, extended window)
    prices_df = None
    if loader is not None:
        try:
            prices_df = loader.query(
                "prices_adj",
                columns=["ts_code", "trade_date", "adj_close"],
                start_date=load_start,
                end_date=load_end,
            )
        except Exception:
            logger.debug("Could not load prices_adj for breadth — continuing without")

    # 5. Calendar already initialized in step 2 — compute trade_dates
    trade_dates = sorted(int(d) for d in cal.trade_days_between(
        int(load_start), int(load_end)
    ))

    # 6. Regime detection
    detector = RegimeDetector(detector_cfg)
    features = detector.compute_features(index_df, prices_df, scoring_signal_dates)

    if features.empty:
        logger.error("No regime features computed — check index data coverage "
                      "(load_start=%s, load_end=%s)", load_start, load_end)
        diagnostics["error"] = "regime_features_empty"
        diagnostics["skip_reasons"]["features"] = (
            f"No features for {len(scoring_signal_dates)} signal dates "
            f"with index data from {load_start} to {load_end}"
        )
        return pd.DataFrame(), diagnostics

    # --- Check allocation_mode to decide regime vs direct_state path ---
    allocation_mode = regime_config.get("allocation_mode", "regime")

    if allocation_mode == "direct_state":
        # ================================================================
        # Plan B: Direct State Allocator
        # (skip regime_probs + RegimeAllocator, go direct from features)
        # ================================================================
        from alpha.direct_state_allocator import DirectStateAllocator

        diagnostics["market_state_features"] = features

        # 7b. Strategy sleeves (shared with regime path)
        sleeve_engine = StrategySleeveEngine(sleeve_cfg, composite_cfg)
        sleeve_scores = sleeve_engine.compute_sleeve_scores(
            factor_dfs_aligned, fwd_rets, scoring_signal_dates
        )
        diagnostics["sleeve_scores"] = {
            name: f"{len(df)} rows, {df['trade_date'].nunique()} dates" if not df.empty else "EMPTY"
            for name, df in sleeve_scores.items()
        }

        available_sleeves = sleeve_engine.get_available_sleeves_by_date(sleeve_scores)
        diagnostics["sleeve_active_dates"] = {
            name: len(dates) for name, dates in _invert_available_sleeves(available_sleeves).items()
        }

        date_sleeve_counts = {d: len(s) for d, s in available_sleeves.items()}
        if date_sleeve_counts:
            logger.info(
                "Per-date sleeves: min=%d, max=%d, median=%.1f, dates with <2=%d",
                min(date_sleeve_counts.values()),
                max(date_sleeve_counts.values()),
                np.median(list(date_sleeve_counts.values())),
                sum(1 for v in date_sleeve_counts.values() if v < 2),
            )

        # Check for empty sleeves
        skip_reasons = {}
        for name, df in sleeve_scores.items():
            if df.empty:
                factors = sleeve_cfg.get(name, {}).get("factors", []) if isinstance(sleeve_cfg.get(name, {}), dict) else []
                available = [f for f in factors if f in factor_dfs_aligned]
                skip_reasons[name] = {
                    "declared_factors": factors,
                    "available_in_cache": available,
                    "reason": "no_composite_produced",
                }
        diagnostics["skip_reasons"].update(skip_reasons)

        # 9b. Direct state allocator
        dsa_cfg = regime_config.get("direct_state_allocator", {})
        dsa = DirectStateAllocator(dsa_cfg)
        sleeve_weights = dsa.compute_sleeve_weights(features, available_sleeves)

        if sleeve_weights.empty:
            diagnostics["error"] = "direct_allocator_no_weights"
            return pd.DataFrame(), diagnostics

        # Strip diagnostic flag columns before composite builder
        diag_cols = [c for c in sleeve_weights.columns
                     if c.endswith("_flag")]
        diagnostics["direct_state_flags"] = (
            sleeve_weights[["trade_date"] + diag_cols].copy()
            if diag_cols else pd.DataFrame()
        )
        sleeve_weights = sleeve_weights.drop(columns=diag_cols, errors="ignore")
        diagnostics["sleeve_weights"] = sleeve_weights

        # Log average sleeve weights
        if not sleeve_weights.empty:
            wt_cols = [c for c in sleeve_weights.columns if c.endswith("_weight")]
            avg_wts = {c: f"{sleeve_weights[c].mean():.3f}" for c in wt_cols}
            logger.info("Average sleeve weights (direct_state): %s", avg_wts)

    else:
        # ================================================================
        # Plan A / default: Regime-based path (existing logic, unchanged)
        # ================================================================
        regime_probs = detector.predict_regime_probs(features)
        diagnostics["regime_probs"] = regime_probs

        avg_probs = {c: f"{regime_probs[c].mean():.3f}" for c in regime_probs.columns if c.endswith("_prob")}
        logger.info("Regime detection: %d dates, avg probs=%s", len(regime_probs), avg_probs)

        # 7. Strategy sleeves (with aligned factor_dfs)
        sleeve_engine = StrategySleeveEngine(sleeve_cfg, composite_cfg)
        sleeve_scores = sleeve_engine.compute_sleeve_scores(
            factor_dfs_aligned, fwd_rets, scoring_signal_dates
        )
        diagnostics["sleeve_scores"] = {
            name: f"{len(df)} rows, {df['trade_date'].nunique()} dates" if not df.empty else "EMPTY"
            for name, df in sleeve_scores.items()
        }

        available_sleeves = sleeve_engine.get_available_sleeves_by_date(sleeve_scores)
        diagnostics["sleeve_active_dates"] = {
            name: len(dates) for name, dates in _invert_available_sleeves(available_sleeves).items()
        }

        # Per-date sleeve count summary
        date_sleeve_counts = {d: len(s) for d, s in available_sleeves.items()}
        if date_sleeve_counts:
            logger.info(
                "Per-date sleeves: min=%d, max=%d, median=%.1f, dates with <2=%d",
                min(date_sleeve_counts.values()),
                max(date_sleeve_counts.values()),
                np.median(list(date_sleeve_counts.values())),
                sum(1 for v in date_sleeve_counts.values() if v < 2),
            )

        # Check for empty sleeves and record reasons
        skip_reasons = {}
        for name, df in sleeve_scores.items():
            if df.empty:
                factors = sleeve_cfg.get(name, {}).get("factors", []) if isinstance(sleeve_cfg.get(name, {}), dict) else []
                available = [f for f in factors if f in factor_dfs_aligned]
                skip_reasons[name] = {
                    "declared_factors": factors,
                    "available_in_cache": available,
                    "reason": "no_composite_produced",
                }
        diagnostics["skip_reasons"].update(skip_reasons)

        # 8. Optional sleeve performance overlay
        sleeve_multipliers = pd.DataFrame()
        sleeve_overlay_metrics = pd.DataFrame()
        if overlay_cfg.get("enabled", False):
            overlay_params = dict(overlay_cfg)
            overlay_params.setdefault("horizon", composite_cfg.get("horizon", 5))
            overlay = SleevePerformanceOverlay(overlay_params)
            sleeve_multipliers, sleeve_overlay_metrics = overlay.compute_multipliers(
                sleeve_scores,
                fwd_rets,
                scoring_signal_dates,
                trade_dates=trade_dates,
            )
            diagnostics["sleeve_overlay_multipliers"] = sleeve_multipliers
            diagnostics["sleeve_overlay_metrics"] = sleeve_overlay_metrics
            if not sleeve_multipliers.empty:
                mult_cols = [c for c in sleeve_multipliers.columns if c.endswith("_multiplier")]
                avg_mults = {c: f"{sleeve_multipliers[c].mean():.3f}" for c in mult_cols}
                logger.info("Average sleeve overlay multipliers: %s", avg_mults)

        # 9. Allocator
        allocator = RegimeAllocator(allocator_cfg)
        base_sleeve_weights = allocator.compute_sleeve_weights(regime_probs, available_sleeves)
        diagnostics["sleeve_base_weights"] = base_sleeve_weights

        # --- P1-3: shock_reversal specific diagnostics ---
        _add_shock_diagnostics(diagnostics, sleeve_scores, base_sleeve_weights)

        if overlay_cfg.get("enabled", False) and not sleeve_multipliers.empty:
            allocator = RegimeAllocator(allocator_cfg)
            sleeve_weights = allocator.compute_sleeve_weights(
                regime_probs, available_sleeves, sleeve_multipliers=sleeve_multipliers
            )
        else:
            sleeve_weights = base_sleeve_weights
        diagnostics["sleeve_weights"] = sleeve_weights

        if sleeve_weights.empty:
            # Build detailed error context for debugging
            sleeve_detail = {}
            for sname, sdf in sleeve_scores.items():
                factors = sleeve_cfg.get(sname, {}).get("factors", []) if isinstance(sleeve_cfg.get(sname, {}), dict) else []
                aligned_info = diagnostics.get("aligned_factor_coverage", {})
                factor_cov = {f: aligned_info.get(f, "N/A") for f in factors}
                sleeve_detail[sname] = {
                    "declared_factors": factors,
                    "score_rows": len(sdf) if not sdf.empty else 0,
                    "score_dates": sdf["trade_date"].nunique() if not sdf.empty else 0,
                    "aligned_factor_coverage": factor_cov,
                }
            date_sleeve_counts = {d: len(s) for d, s in available_sleeves.items()}
            logger.error(
                "No sleeve weights produced — insufficient sleeves available. "
                "Sleeve detail: %s. Per-date sleeve counts: min=%d, max=%d",
                sleeve_detail,
                min(date_sleeve_counts.values()) if date_sleeve_counts else 0,
                max(date_sleeve_counts.values()) if date_sleeve_counts else 0,
            )
            diagnostics["error"] = "allocator_no_weights"
            diagnostics["sleeve_detail"] = sleeve_detail
            return pd.DataFrame(), diagnostics

        # Log average sleeve weights
        if not sleeve_weights.empty:
            wt_cols = [c for c in sleeve_weights.columns if c.endswith("_weight")]
            avg_wts = {c: f"{sleeve_weights[c].mean():.3f}" for c in wt_cols}
            logger.info("Average sleeve weights: %s", avg_wts)

    # 10. Composite builder
    builder = RegimeCompositeBuilder(
        min_sleeves=allocator_cfg.get("min_sleeves", 2)
    )
    composite_full = builder.build(sleeve_scores, sleeve_weights)

    if not composite_full.empty:
        diagnostics["first_composite_date_before_clip"] = int(composite_full["trade_date"].min())
        diagnostics["last_composite_date_before_clip"] = int(composite_full["trade_date"].max())

    # Clip composite to target signal dates only (warmup dates were for IC/coverage)
    target_set = set(target_signal_dates)
    if not composite_full.empty:
        composite = composite_full[composite_full["trade_date"].isin(target_set)].copy()
    else:
        composite = composite_full

    if not composite.empty:
        diagnostics["first_composite_date_after_clip"] = int(composite["trade_date"].min())
        diagnostics["last_composite_date_after_clip"] = int(composite["trade_date"].max())

    logger.info(
        "Regime composite: %d rows, %d dates (after clipping to %d target dates, "
        "full had %d dates)",
        len(composite),
        composite["trade_date"].nunique() if not composite.empty else 0,
        len(target_set),
        composite_full["trade_date"].nunique() if not composite_full.empty else 0,
    )

    diagnostics["features"] = features

    return composite, diagnostics


def _add_shock_diagnostics(
    diagnostics: dict,
    sleeve_scores: dict,
    sleeve_weights: pd.DataFrame,
) -> None:
    """P1-3: Add shock_reversal-specific diagnostic entries.

    Outputs:
      - shock_active_dates: number of dates with valid shock scores
      - shock_avg_weight: mean allocator weight when active
      - shock_status: "ACTIVE" | "EMPTY" | "NOT_CONFIGURED"
    """
    shock_diag = {"status": "NOT_CONFIGURED"}

    if "shock_reversal" in sleeve_scores:
        shock_df = sleeve_scores.get("shock_reversal")
        if shock_df is not None and not shock_df.empty:
            shock_diag["status"] = "ACTIVE"
            shock_diag["n_rows"] = len(shock_df)
            n_dates = shock_df["trade_date"].nunique()
            shock_diag["active_dates"] = n_dates
            shock_diag["avg_stocks_per_date"] = (
                len(shock_df) / max(n_dates, 1)
            )
        else:
            shock_diag["status"] = "EMPTY"
            shock_diag["active_dates"] = 0

        # Average weight from allocator
        if not sleeve_weights.empty and "shock_reversal_weight" in sleeve_weights.columns:
            shock_diag["avg_weight"] = float(
                sleeve_weights["shock_reversal_weight"].mean()
            )
            shock_diag["max_weight"] = float(
                sleeve_weights["shock_reversal_weight"].max()
            )
            shock_diag["weight_positive_dates"] = int(
                (sleeve_weights["shock_reversal_weight"] > 1e-6).sum()
            )

    diagnostics["shock_reversal"] = shock_diag


def _invert_available_sleeves(available_sleeves: dict) -> dict:
    """Invert {date: [sleeves]} → {sleeve: [dates]}."""
    result: dict = {}
    for d, sleeves in available_sleeves.items():
        for s in sleeves:
            if s not in result:
                result[s] = []
            result[s].append(d)
    return result


# ===================================================================
# Unified reporting helpers (Phase 0)
# ===================================================================
def _generate_run_id(args) -> str:
    """Generate a unique run_id for this execution.

    Format:
      {start}_{end}_top{top_n}_{strategy_mode}_{config_stem}_{hash8}_{ts_micros}_{uuid12}

    The config stem and hash first 8 chars ensure A/B concurrent runs
    are human-distinguishable.  The uuid.uuid4().hex[:12] suffix
    guarantees uniqueness even under concurrent invocation with the
    same timestamp.  Microsecond timestamp is retained for human
    sortability, not as the sole uniqueness mechanism.
    """
    start = args.start or "20160101"
    end = args.end or datetime.now().strftime("%Y%m%d")
    top_n = getattr(args, "top_n", 50) or 50
    strategy_mode = getattr(args, "strategy_mode", "factor_dynamic") or "factor_dynamic"

    # Regime config stem + hash for isolation
    regime_config_path = getattr(args, "regime_config", None)
    config_stem = "default"
    config_hash8 = "00000000"
    if regime_config_path:
        try:
            config_stem = Path(regime_config_path).stem  # e.g. "direct_state_v1"
        except Exception:
            config_stem = "unknown"
        config_hash = _compute_sha256(regime_config_path)
        config_hash8 = config_hash[:8] if config_hash else "00000000"

    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    uid = uuid.uuid4().hex[:12]
    return f"{start}_{end}_top{top_n}_{strategy_mode}_{config_stem}_{config_hash8}_{ts}_{uid}"


def _compute_sha256(file_path: str) -> str:
    """Compute SHA256 hex digest of a file's contents."""
    try:
        p = Path(file_path)
        if not p.exists():
            return ""
        return hashlib.sha256(p.read_bytes()).hexdigest()
    except Exception:
        return ""


def _compute_factor_list_hash(factor_list: list) -> str:
    """Compute SHA256 of the sorted, joined factor_list string."""
    if not factor_list:
        return ""
    normalized = ",".join(sorted(str(f) for f in factor_list))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _write_run_manifest(run_id: str, args, factor_list: list = None,
                        phases_run: list = None, extra: dict = None):
    """Write or update outputs/run_manifest.json and per-run files.

    Key invariant: if the manifest's run_id differs from the current run_id,
    rebuild the manifest from scratch.  The old setdefault() behavior caused
    cross-run pollution (old run_id/start/end never overwritten).

    Now also writes SHA256 hashes of config files and factor_list for frozen
    validation reuse detection.
    """
    manifest_dir = Path("outputs/runs") / run_id
    manifest_dir.mkdir(parents=True, exist_ok=True)

    # Build fresh manifest for THIS run
    manifest = {
        "run_id": run_id,
        "start": args.start or "20160101",
        "end": args.end or datetime.now().strftime("%Y%m%d"),
        "top_n": getattr(args, "top_n", 50) or 50,
        "weight_max": getattr(args, "weight_max", 0.02) or 0.02,
        "cost_multiplier": getattr(args, "cost_multiplier", 1.0) or 1.0,
        "slippage_bps": getattr(args, "slippage_bps", None),
        "rebalance_freq": getattr(args, "frequency", "weekly") or "weekly",
        "phases_run": sorted(phases_run) if phases_run else [],
    }

    if factor_list:
        manifest["factor_list"] = factor_list
        manifest["factor_list_sha256"] = _compute_factor_list_hash(factor_list)

    # Add config paths and their SHA256 hashes
    factors_config_path = getattr(args, "factors_config", None)
    if factors_config_path:
        manifest["factors_config"] = factors_config_path
        manifest["factors_config_sha256"] = _compute_sha256(factors_config_path)

    regime_config_path = getattr(args, "regime_config", None)
    if regime_config_path:
        manifest["regime_config"] = regime_config_path
        manifest["regime_config_sha256"] = _compute_sha256(regime_config_path)

    if extra:
        for k, v in extra.items():
            if k not in manifest:
                manifest[k] = v

    # Merge with existing global manifest (for phase aggregation)
    global_manifest_path = Path("outputs/run_manifest.json")
    global_manifest_path.parent.mkdir(parents=True, exist_ok=True)

    if global_manifest_path.exists():
        with open(global_manifest_path, "r", encoding="utf-8") as f:
            global_manifest = json.load(f)
        # If global manifest is from a different run, rebuild it
        if global_manifest.get("run_id") != run_id:
            global_manifest = manifest.copy()
        else:
            # Merge new phases into existing
            prev_phases = set(global_manifest.get("phases_run", []))
            if phases_run:
                prev_phases.update(phases_run)
            global_manifest["phases_run"] = sorted(prev_phases)
            # Update mutable fields
            for key in manifest:
                if key not in ("phases_run",):
                    global_manifest[key] = manifest[key]
    else:
        global_manifest = manifest.copy()

    # Write per-run manifest
    per_run_path = manifest_dir / "run_manifest.json"
    with open(per_run_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False, default=str)
    logger.info(f"Per-run manifest: {per_run_path}")

    # Write global manifest
    with open(global_manifest_path, "w", encoding="utf-8") as f:
        json.dump(global_manifest, f, indent=2, ensure_ascii=False, default=str)
    logger.info(f"Global manifest updated: {global_manifest_path}")

    # Write latest symlinks/manifests
    latest_manifest_path = Path("outputs/latest_run_manifest.json")
    with open(latest_manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False, default=str)
    logger.debug(f"Latest manifest: {latest_manifest_path}")


def _write_metrics_summary(run_id: str, phase_name: str,
                           metrics: dict):
    """Write outputs/metrics_summary.json and per-run metrics."""
    manifest_dir = Path("outputs/runs") / run_id
    manifest_dir.mkdir(parents=True, exist_ok=True)

    # Standardized metric keys to extract.
    # MUST include failure-diagnostic fields so that FAIL metrics are
    # written in full — otherwise the whitelist silently drops status,
    # error, and failure_reasons, leaving stale success data in place.
    std_keys = [
        "annualized_return", "annualized_excess_return", "benchmark_annualized_return",
        "information_ratio", "sharpe_ratio", "max_drawdown", "avg_turnover",
        "total_cost_bps", "n_periods", "period_start", "period_end",
        "optimizer_fallback_rate", "avg_active_weight", "max_single_weight",
        "used_mu_rate", "opt_n_total", "opt_n_fallback", "opt_n_low_space",
        "opt_n_relaxation", "opt_n_relaxation_success",
        "optimizer_relaxation_rate",
        "opt_fallback_reasons",
        # Benchmark diagnostics
        "benchmark_status", "benchmark_daily_rows", "benchmark_valid_periods",
        "benchmark_start", "benchmark_end", "benchmark_failure_reason",
        # Stability diagnostics
        "max_single_period_return", "max_single_period_return_date",
        "min_single_period_return", "min_single_period_return_date",
        "period_return_std", "metric_stability_status", "n_weekly_samples",
        # Data quality status
        "data_quality_status", "price_quality_status",
        # Go/No-Go gate
        "go_nogo",
        # Failure diagnostics — must survive the whitelist
        "status", "error", "failure_reasons",
        "required_start", "required_end",
        "n_candidates", "first_candidate", "last_candidate",
        "coverage_ratio", "expected_dates", "actual_dates",
        "n_missing", "first_missing_dates", "fix_command",
    ]

    phase_metrics = {"run_id": run_id}
    for key in std_keys:
        if key in metrics and not key.startswith("_"):
            phase_metrics[key] = metrics[key]

    # Per-run metrics
    per_run_path = manifest_dir / "metrics_summary.json"
    if per_run_path.exists():
        with open(per_run_path, "r", encoding="utf-8") as f:
            per_run_summary = json.load(f)
    else:
        per_run_summary = {}
    per_run_summary[phase_name] = phase_metrics
    with open(per_run_path, "w", encoding="utf-8") as f:
        json.dump(per_run_summary, f, indent=2, ensure_ascii=False, default=str)
    logger.info(f"Per-run metrics: {per_run_path}")

    # Global summary
    summary_path = Path("outputs/metrics_summary.json")
    summary_path.parent.mkdir(parents=True, exist_ok=True)

    if summary_path.exists():
        with open(summary_path, "r", encoding="utf-8") as f:
            summary = json.load(f)
    else:
        summary = {}

    summary[phase_name] = phase_metrics

    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False, default=str)

    logger.info(f"Metrics summary updated for {phase_name}: {summary_path}")

    # Latest symlink
    latest_metrics_path = Path("outputs/latest_metrics_summary.json")
    with open(latest_metrics_path, "w", encoding="utf-8") as f:
        json.dump(per_run_summary, f, indent=2, ensure_ascii=False, default=str)
    logger.debug(f"Latest metrics: {latest_metrics_path}")


def _same_float(a, b, tol: float = 1e-12) -> bool:
    if a is None or b is None:
        return a is None and b is None
    try:
        return abs(float(a) - float(b)) <= tol
    except (TypeError, ValueError):
        return False


def _same_config_value(manifest: dict, key: str, expected_value, default=None):
    """Compare a manifest value with expected, treating None as 'not set'."""
    actual = manifest.get(key, default)
    if actual is None and expected_value is None:
        return True
    if actual is None or expected_value is None:
        return actual == expected_value
    if isinstance(expected_value, float) and isinstance(actual, (int, float)):
        return _same_float(actual, expected_value)
    return actual == expected_value


def _load_matching_phase3_optimized(base_config: dict) -> dict | None:
    """Return Phase 3 optimized metrics when they exactly match config.

    Batch 4 fix: all STRATEGY_PARAM_KEYS must match, including new params
    like cost_aware_lambda, cov_shrinkage, constraint_relaxation, etc.
    Missing manifest keys are compared against defaults — a manifest
    without a field is treated as having the default value for that field.
    """

    def _read_json(path: Path) -> dict | None:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.debug(f"Phase 3 reuse skipped: failed to read {path}: {e}")
            return None

    metrics_summary = _read_json(Path("outputs/metrics_summary.json"))
    if not metrics_summary:
        metrics_summary = _read_json(Path("outputs/latest_metrics_summary.json"))
    if not metrics_summary:
        return None

    phase3_metrics = metrics_summary.get("phase3_optimized")
    if not isinstance(phase3_metrics, dict):
        return None
    if phase3_metrics.get("error") or phase3_metrics.get("status") == "FAIL":
        return None

    phase3_run_id = phase3_metrics.get("run_id")
    if not phase3_run_id:
        return None
    manifest = _read_json(Path("outputs/runs") / phase3_run_id / "run_manifest.json")
    if not manifest:
        manifest = _read_json(Path("outputs/latest_run_manifest.json"))
    if not manifest or phase3_run_id != manifest.get("run_id"):
        return None

    # Required identity fields — must match exactly
    required_fields = {
        "start": base_config.get("start_date"),
        "end": base_config.get("end_date"),
        "top_n": base_config.get("top_n"),
        "weighting": "optimized",
        "rebalance_freq": base_config.get("rebalance_freq", "weekly"),
    }
    for key, value in required_fields.items():
        if manifest.get(key) != value:
            logger.debug(f"Phase3 reuse: {key} mismatch ({manifest.get(key)} != {value})")
            return None

    # Strategy parameters — must all match (Batch 4 fix)
    # Use STRATEGY_PARAM_KEYS plus legacy weight_max
    all_param_keys = ["weight_max"] + STRATEGY_PARAM_KEYS
    defaults = {
        "entry_rank": None, "exit_rank": None,
        "turnover_max": None, "turnover_penalty": None,
        "no_trade_band": 0.0, "max_weight_change": None,
        "score_smoothing_halflife": None, "hold_buffer_mode": "standard",
        "cost_aware_lambda": 0.0, "estimated_cost_bps": 10.0,
        "cov_shrinkage": "ledoit_wolf", "constraint_relaxation": "none",
    }

    for key in all_param_keys:
        expected_val = base_config.get(key, defaults.get(key))
        if not _same_config_value(manifest, key, expected_val, defaults.get(key)):
            logger.debug(
                f"Phase3 reuse: strategy param '{key}' mismatch "
                f"(manifest={manifest.get(key)}, expected={expected_val})"
            )
            return None

    logger.info(
        "Reusing matching Phase 3 optimized metrics as Phase 5 core base: "
        f"run_id={phase3_metrics.get('run_id')}"
    )
    reused = deepcopy(phase3_metrics)
    reused["source"] = "phase3_optimized_reused"
    return reused


# ===================================================================
# Diagnostic artifact writer
# ===================================================================
def _dump_regime_diagnostics(results, artifacts_dir, period_diag, phase_name):
    """Persist regime probs and sleeve weights to parquet if the run
    was produced via the regime router. Also attaches period-average
    regime probabilities and sleeve weights to period_diag for the JSON
    sidecar. Best-effort: a failure here must not abort the run.
    """
    regime_diag = results.get("_regime_diag")
    if not regime_diag:
        return
    import pandas as pd
    # regime probs: per-date DataFrame with trade_date + prob columns
    rp = regime_diag.get("regime_probs")
    if rp is not None and isinstance(rp, pd.DataFrame) and not rp.empty:
        try:
            rp_path = artifacts_dir / f"{phase_name}_regime_probs.parquet"
            rp.to_parquet(rp_path, index=False)
            prob_cols = [c for c in rp.columns if c.endswith("_prob")]
            if prob_cols:
                avg = {c: float(rp[c].mean()) for c in prob_cols}
                period_diag["avg_regime_probs"] = avg
        except Exception as e:
            logger.warning(f"Failed to write regime_probs: {e}")
    # sleeve weights: per-date DataFrame with trade_date + weight columns
    sw = regime_diag.get("sleeve_weights")
    if sw is not None and isinstance(sw, pd.DataFrame) and not sw.empty:
        try:
            sw_path = artifacts_dir / f"{phase_name}_sleeve_weights.parquet"
            sw.to_parquet(sw_path, index=False)
            wt_cols = [c for c in sw.columns if c.endswith("_weight")]
            if wt_cols:
                avg = {c: float(sw[c].mean()) for c in wt_cols}
                period_diag["avg_sleeve_weights"] = avg
        except Exception as e:
            logger.warning(f"Failed to write sleeve_weights: {e}")
    # Optional regime overlay diagnostics
    diagnostic_frames = [
        ("sleeve_base_weights", "_weight", "_sleeve_base_weights.parquet"),
        ("sleeve_overlay_multipliers", "_multiplier", "_sleeve_overlay_multipliers.parquet"),
        ("sleeve_overlay_metrics", None, "_sleeve_overlay_metrics.parquet"),
    ]
    for diag_key, avg_suffix, file_suffix in diagnostic_frames:
        df = regime_diag.get(diag_key)
        if df is None or not isinstance(df, pd.DataFrame) or df.empty:
            continue
        try:
            path = artifacts_dir / f"{phase_name}{file_suffix}"
            df.to_parquet(path, index=False)
            if avg_suffix is not None:
                cols = [c for c in df.columns if c.endswith(avg_suffix)]
                if cols:
                    period_diag[f"avg_{diag_key}"] = {
                        c: float(df[c].mean()) for c in cols
                    }
        except Exception as e:
            logger.warning(f"Failed to write {diag_key}: {e}")
    # --- direct_state diagnostics (Plan B) ---
    dsf = regime_diag.get("direct_state_flags")
    if dsf is not None and isinstance(dsf, pd.DataFrame) and not dsf.empty:
        try:
            dsf_path = artifacts_dir / f"{phase_name}_direct_state_flags.parquet"
            dsf.to_parquet(dsf_path, index=False)
            if "high_vol_flag" in dsf.columns:
                period_diag["high_vol_flag_share"] = float(dsf["high_vol_flag"].mean())
            if "high_breadth_flag" in dsf.columns:
                period_diag["high_breadth_flag_share"] = float(dsf["high_breadth_flag"].mean())
        except Exception as e:
            logger.warning(f"Failed to write direct_state_flags: {e}")

    # --- market state features (Plan B) ---
    msf = regime_diag.get("market_state_features")
    if msf is not None and isinstance(msf, pd.DataFrame) and not msf.empty:
        try:
            msf_path = artifacts_dir / f"{phase_name}_market_state_features.parquet"
            msf.to_parquet(msf_path, index=False)
            feat_cols = ["volatility_state", "breadth_score", "trend_strength", "turnover_state"]
            for col in feat_cols:
                if col in msf.columns:
                    period_diag[f"avg_{col}"] = float(msf[col].mean())
        except Exception as e:
            logger.warning(f"Failed to write market_state_features: {e}")

    # Coverage: how many of period target dates had any regime prob
    try:
        if rp is not None and isinstance(rp, pd.DataFrame) and not rp.empty:
            period_diag["regime_probs_dates"] = int(rp["trade_date"].nunique())
        if sw is not None and isinstance(sw, pd.DataFrame) and not sw.empty:
            period_diag["sleeve_weights_dates"] = int(sw["trade_date"].nunique())
    except Exception:
        pass
def _write_diagnostic_artifacts(run_id: str, phase_name: str, results: dict,
                                portfolio_values: list = None,
                                benchmark_period_returns: dict = None,
                                run_id_override: str = None):
    """
    Save minimum diagnostic artifacts per run.

    Saves portfolio values, benchmark returns, period return diagnostics,
    and optionally holdings/trades. Always saved — even for FAILED runs —
    so post-mortem diagnosis is always possible.

    Parameters
    ----------
    run_id : str
        Run identifier.
    phase_name : str
        Phase name for file naming (e.g., "phase2", "phase3_optimized").
    results : dict
        The backtest results dict (contains metrics and _diagnostics_payload).
    portfolio_values : list of dict, optional
        Portfolio value series from _simulate().
    benchmark_period_returns : dict, optional
        Benchmark period return diagnostics.
    run_id_override : str, optional
        Override run_id for cross-phase artifact linking.
    """
    import pandas as pd
    rid = run_id_override or run_id
    artifacts_dir = Path("outputs/runs") / rid / "diagnostics"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    # 1. Portfolio values
    if portfolio_values:
        pv_df = pd.DataFrame(portfolio_values)
        try:
            pv_df.to_parquet(
                artifacts_dir / f"{phase_name}_portfolio_values.parquet",
                index=False,
            )
            pv_df.to_csv(
                artifacts_dir / f"{phase_name}_portfolio_values.csv",
                index=False,
            )
            logger.info(
                f"Diagnostic artifacts: saved portfolio_values "
                f"({len(pv_df)} periods) → {artifacts_dir}"
            )
        except Exception as e:
            logger.warning(f"Failed to write portfolio_values artifacts: {e}")

    # 2. Benchmark period returns (from _compute_benchmark_stats)
    bm_period_returns = results.get("_benchmark_period_returns")
    if bm_period_returns is not None:
        import pandas as pd
        try:
            if isinstance(bm_period_returns, pd.DataFrame):
                bm_period_returns.to_csv(
                    artifacts_dir / f"{phase_name}_benchmark_period_returns.csv",
                    index=True,
                )
            else:
                with open(
                    artifacts_dir / f"{phase_name}_benchmark_period_returns.json", "w",
                    encoding="utf-8",
                ) as f:
                    json.dump(bm_period_returns, f, indent=2, default=str)
            logger.info(f"Diagnostic artifacts: saved benchmark_period_returns")
        except Exception as e:
            logger.warning(f"Failed to write benchmark_period_returns: {e}")
    elif benchmark_period_returns:
        try:
            with open(
                artifacts_dir / f"{phase_name}_benchmark_period_returns.json", "w",
                encoding="utf-8",
            ) as f:
                json.dump(benchmark_period_returns, f, indent=2, default=str)
        except Exception as e:
            logger.warning(f"Failed to write benchmark_period_returns: {e}")

    # 3. Period return diagnostics
    period_diag = {}
    for key in [
        "n_periods", "n_weekly_samples",
        "max_single_period_return", "max_single_period_return_date",
        "min_single_period_return", "min_single_period_return_date",
        "period_return_std", "metric_stability_status",
        "benchmark_status", "benchmark_daily_rows", "benchmark_valid_periods",
        "benchmark_start", "benchmark_end", "benchmark_failure_reason",
        "data_quality_status", "price_quality_status",
        "annualized_return", "annualized_excess_return",
        "sharpe_ratio", "information_ratio", "max_drawdown",
    ]:
        if key in results:
            period_diag[key] = results[key]
    # Include data quality gate summary
    dq_gate = results.get("_data_quality_gate", {})
    if dq_gate:
        period_diag["go_nogo_overall"] = dq_gate.get("overall")
        period_diag["go_nogo_failure_reasons"] = dq_gate.get("failure_reasons", [])
    # Regime-mode diagnostics: persist per-date regime probs and sleeve weights,
    # plus period averages. Best-effort: failures here must not break the run.
    _dump_regime_diagnostics(results, artifacts_dir, period_diag, phase_name)
    try:
        with open(
            artifacts_dir / f"{phase_name}_period_return_diagnostics.json", "w",
            encoding="utf-8",
        ) as f:
            json.dump(period_diag, f, indent=2, default=str)
    except Exception as e:
        logger.warning(f"Failed to write period_return_diagnostics: {e}")

    # 4. Holdings / Trades (from diagnostics payload)
    diag_payload = results.get("_diagnostics_payload", {})
    if diag_payload.get("holdings_log"):
        try:
            h_df = pd.DataFrame(diag_payload["holdings_log"])
            h_df.to_parquet(
                artifacts_dir / f"{phase_name}_holdings.parquet",
                index=False,
            )
        except Exception as e:
            logger.warning(f"Failed to write holdings artifact: {e}")
    if diag_payload.get("trades_log"):
        try:
            t_df = pd.DataFrame(diag_payload["trades_log"])
            t_df.to_parquet(
                artifacts_dir / f"{phase_name}_trades.parquet",
                index=False,
            )
        except Exception as e:
            logger.warning(f"Failed to write trades artifact: {e}")


# ===================================================================
# Phase 0: Data Pipeline
# ===================================================================
def run_phase0(args):
    """
    Phase 0: Build data pipeline.

    1. Load Tushare client
    2. Fetch and cache: prices_raw, adj_factor, daily_basic, index_weight,
       stock_basic, namechange, suspend, stk_limit, trade_cal, index_daily, industry
    3. Build PIT universe
    4. Verify tradable mask
    """
    logger.info("=" * 60)
    logger.info("Phase 0: Data Pipeline")
    logger.info("=" * 60)

    start_date = args.start or "20160101"
    end_date = args.end or datetime.now().strftime("%Y%m%d")
    phase5_suite = getattr(args, "phase5_suite", "full")

    # 1. Tushare client
    from data.tushare_client import get_client
    client = get_client()
    logger.info(f"Tushare client initialized (available={client.available})")

    if not client.available and not args.dry_run:
        logger.error("Tushare not available. Set TUSHARE_TOKEN in .env")
        return 1

    # 2. Trading calendar
    from data.calendar import get_calendar
    calendar = get_calendar()
    calendar_loaded = False
    try:
        calendar.load(start_date=start_date, end_date=end_date)
        if calendar._trade_dates_sorted is not None:
            logger.info(f"Trading calendar: {len(calendar.trade_dates)} days "
                         f"({calendar._trade_dates_sorted[0]} to "
                         f"{calendar._trade_dates_sorted[-1]})")
            calendar_loaded = True
    except (RuntimeError, AttributeError) as e:
        logger.warning(f"Trading calendar load failed: {e}")

    if args.dry_run:
        if not client.available:
            logger.warning("Tushare not available — dry-run limited to import checks")
        elif not calendar_loaded:
            logger.warning("Calendar not loaded — dry-run limited to import checks")
        else:
            logger.info("Dry run complete — skipping data fetch")
        return 0

    # 3. Fetch core data — PER TRADING DAY for prices, MONTHLY for adj.
    #    Tushare daily() with range returns truncated results. We fetch
    #    one trading day at a time to guarantee full coverage.
    import gc as _gc
    import pandas as pd
    from data.panel_loader import MemoryMonitor, get_loader
    from data.adjust import PriceAdjuster
    monitor = MemoryMonitor(max_memory_gb=8.0, warning_threshold_gb=6.0)
    loader = get_loader()
    adjuster = PriceAdjuster()
    monitor.check("phase0_start")

    # Get trading days within the requested range
    from data.calendar import get_calendar
    cal = get_calendar()
    cal.load(start_date=start_date, end_date=end_date)
    all_trade_days = cal.trade_days_between(int(start_date), int(end_date))
    logger.info(
        f"Trading days in range: {len(all_trade_days)} "
        f"({all_trade_days[0]} → {all_trade_days[-1]})"
    )

    # Step A: Fetch raw prices — one day at a time, by MONTH
    logger.info("Fetching prices_raw (per trading day, monthly batches)...")
    # Group trade days by month
    from itertools import groupby
    trade_days_by_month = {}
    for d in all_trade_days:
        ym = str(d)[:6]  # YYYYMM
        trade_days_by_month.setdefault(ym, []).append(d)

    for ym, month_days in sorted(trade_days_by_month.items()):
        logger.info(f"  Month {ym}: {len(month_days)} trade days")
        raw_month = client.get_daily_by_trade_dates(
            trade_dates=month_days, use_cache=True
        )
        if not raw_month.empty:
            logger.debug(f"    → {len(raw_month)} raw rows")
        monitor.check(f"phase0_raw_{ym}")

        # For this month's stocks, fetch adj_factor and compute adj prices
        month_stocks = list(raw_month["ts_code"].unique()) if not raw_month.empty else []
        if month_stocks:
            m_start = str(int(min(month_days)))
            m_end = str(int(max(month_days)))
            adj_f = client.get_adj_factor(
                ts_code=month_stocks, start_date=m_start, end_date=m_end,
                batch_size=100, use_cache=False,
            )
            if adj_f.empty:
                logger.error(
                    f"adj_factor fetch failed for {ym}: "
                    f"{adj_f.attrs if hasattr(adj_f, 'attrs') else {}}. "
                    "Cannot build prices_adj from incomplete adjustment factors."
                )
                return 1
            expected_adj_keys = raw_month[["ts_code", "trade_date"]].drop_duplicates()
            actual_adj_keys = adj_f[["ts_code", "trade_date"]].drop_duplicates()
            missing_adj = expected_adj_keys.merge(
                actual_adj_keys,
                on=["ts_code", "trade_date"],
                how="left",
                indicator=True,
            )
            missing_adj = missing_adj[missing_adj["_merge"] == "left_only"]
            if not missing_adj.empty:
                missing_ratio = len(missing_adj) / len(expected_adj_keys)
                logger.error(
                    f"adj_factor coverage failed for {ym}: "
                    f"missing {len(missing_adj)}/{len(expected_adj_keys)} "
                    f"raw price keys ({missing_ratio:.2%}). "
                    f"Sample: {missing_adj[['ts_code', 'trade_date']].head(10).to_dict('records')}"
                )
                return 1
            adj_month = adjuster.compute_adj_prices(raw_month, adj_factor_df=adj_f)
            if not adj_month.empty:
                adj_month["year"] = adj_month["trade_date"].astype(int) // 10000
                adj_month["month"] = (adj_month["trade_date"].astype(int) % 10000) // 100
                loader.write_data(
                    adj_month, "prices_adj",
                    partition_cols=["year", "month"],
                    dedupe_keys=["ts_code", "trade_date"],
                    replace_partitions=True,
                )
                logger.info(f"    → {len(adj_month)} adj rows written")
            del adj_month, adj_f
        del raw_month
        _gc.collect()
        monitor.check(f"phase0_adj_{ym}")

    # Print coverage summary
    raw_cov = loader.price_coverage("prices_raw", start_date, end_date)
    adj_cov = loader.price_coverage("prices_adj", start_date, end_date)
    logger.info(
        f"prices_raw coverage: {raw_cov['n_dates']}/{raw_cov['expected_trade_dates']} "
        f"dates ({raw_cov['coverage_ratio']:.1%})"
    )
    logger.info(
        f"prices_adj coverage: {adj_cov['n_dates']}/{adj_cov['expected_trade_dates']} "
        f"dates ({adj_cov['coverage_ratio']:.1%})"
    )
    # ---- Phase 0 hard price quality validation (ALL months) ----
    # Runs validate_adj_prices on EVERY month of written data to catch
    # extreme adj_close jumps, duplicate rows, and adj_factor gaps.
    # Now validates ALL months, not just first/last — this catches
    # mid-range anomalies like the 2026‑03 price jumps.
    # A FAIL on ANY month blocks Phase 0 from completing.
    price_quality_ok = True
    try:
        from data.adjust import validate_adj_prices
        all_months = sorted(trade_days_by_month.keys())
        validation_results = {}
        for ym in all_months:
            sample_adj = loader.query(
                "prices_adj",
                columns=["ts_code", "trade_date", "adj_close", "adj_factor"],
                start_date=f"{ym}01",
                end_date=f"{ym}31",
            )
            if not sample_adj.empty:
                sample_raw = loader.query(
                    "prices_raw",
                    columns=["ts_code", "trade_date", "close"],
                    start_date=f"{ym}01",
                    end_date=f"{ym}31",
                )
                val = validate_adj_prices(
                    sample_adj,
                    raw_prices=sample_raw if not sample_raw.empty else None,
                )
                validation_results[ym] = val
                if val["status"] != "OK":
                    price_quality_ok = False
                    logger.error(
                        f"prices_adj quality FAIL for {ym}: "
                        f"{json.dumps(val['failures'], default=str)[:500]}"
                    )
                    # Write detailed failure report
                    fail_dir = Path("outputs/price_quality_failures")
                    fail_dir.mkdir(parents=True, exist_ok=True)
                    with open(fail_dir / f"phase0_{ym}.json", "w", encoding="utf-8") as f:
                        json.dump(val, f, indent=2, default=str)
            else:
                validation_results[ym] = {"status": "EMPTY", "failures": [f"No adj data for {ym}"]}

        # Write aggregate validation report
        if validation_results:
            agg_status = "OK" if price_quality_ok else "FAIL"
            with open(Path("outputs/price_quality_validation.json"), "w", encoding="utf-8") as f:
                json.dump({
                    "status": agg_status,
                    "validated_months": list(validation_results.keys()),
                    "n_validated": len(validation_results),
                    "n_failed": sum(
                        1 for v in validation_results.values()
                        if v.get("status") not in ("OK", "EMPTY")
                    ),
                    "results": {
                        k: {
                            "status": v.get("status", "UNKNOWN"),
                            "failures": v.get("failures", [])[:3],
                            "n_daily_jumps": v.get("n_daily_jumps", 0),
                            "n_weekly_jumps": v.get("n_weekly_jumps", 0),
                            "missing_ratio": v.get("missing_ratio", 0),
                        }
                        for k, v in validation_results.items()
                    },
                }, f, indent=2, default=str)
        if not price_quality_ok:
            logger.error(
                "Phase 0 HARD FAIL: price quality validation failed for "
                f"{sum(1 for v in validation_results.values() if v.get('status') == 'FAIL')} "
                f"of {len(validation_results)} months. "
                "See outputs/price_quality_failures/ for details. "
                "Fix the adj_factor cache and re-run Phase 0 before proceeding."
            )
            return 1
    except Exception as e:
        logger.error(f"Price quality validation error: {e} — continuing with warning")
        # Don't block if validation itself fails (e.g., missing dependency)

    if adj_cov["coverage_ratio"] < 0.75:
        logger.warning(
            f"prices_adj coverage is low ({adj_cov['coverage_ratio']:.1%}). "
            f"Missing {len(adj_cov['missing_dates'])} dates. "
            f"Backtests may have gaps."
        )

    monitor.check("phase0_after_prices_adj")

    logger.info("Fetching daily_basic (monthly snapshots)...")
    db = client.get_daily_basic(start_date=start_date, end_date=end_date)
    logger.info(f"daily_basic: {len(db)} rows")
    monitor.check("phase0_after_daily_basic")

    # Verify daily_basic monthly coverage is sufficient
    db_cov = loader.daily_basic_coverage(start_date, end_date)
    logger.info(
        f"daily_basic coverage: {db_cov['n_months_cached']}/"
        f"{db_cov['n_months_expected']} months "
        f"({db_cov['coverage_ratio']:.1%})"
    )
    if db_cov["coverage_ratio"] < 0.8:
        logger.error(
            f"daily_basic coverage too low: "
            f"{db_cov['n_months_cached']}/{db_cov['n_months_expected']} months "
            f"({db_cov['coverage_ratio']:.1%}). "
            f"Missing: {db_cov['missing_dates'][:10]}"
        )
        return 1

    logger.info("Fetching index_weight (CSI 300)...")
    iw = client.get_index_weight(index_code="000300.SH",
                                 start_date=start_date, end_date=end_date)
    logger.info(f"index_weight: {len(iw)} rows, "
                f"{iw['trade_date'].nunique()} snapshots")
    monitor.check("phase0_after_index_weight")

    logger.info("Fetching stock_basic...")
    sb = client.get_stock_basic()
    logger.info(f"stock_basic: {len(sb)} stocks")

    logger.info("Fetching suspend records...")
    susp = client.get_suspend(start_date=start_date, end_date=end_date)
    logger.info(f"suspend: {len(susp)} records")
    monitor.check("phase0_after_suspend")

    logger.info("Fetching namechange (ST history)...")
    try:
        nc = client.get_namechange(start_date=start_date, end_date=end_date)
        logger.info(f"namechange: {len(nc)} records")
    except Exception as e:
        logger.warning(f"namechange fetch failed: {e} — continuing without ST data")
        nc = pd.DataFrame()
    monitor.check("phase0_after_namechange")

    # Prefetch stk_limit data for execution dates that will actually be
    # used by Phase 2 / smoke backtests.  Aggregate by month, write ONCE
    # per month via loader to avoid dual-write conflicts with
    # get_stk_limit()'s internal caching.
    try:
        from data.calendar import get_calendar
        cal2 = get_calendar()
        cal2.load(start_date=start_date, end_date=end_date)
        all_days = list(cal2.trade_days_between(int(start_date), int(end_date)))

        # Build the exact execution-date set that Phase 2 will query:
        # every weekly signal date's T+1, plus a few tradable-mask
        # sample dates spread across the range.
        signal_dates = cal2.weekly_rebalance_dates(start_date, end_date)
        exec_dates = sorted({
            cal2.next_trade_day(int(d), 1) for d in signal_dates
        })

        # Also include a few sample dates for tradable mask checks
        step = max(1, len(all_days) // 20)
        sample_days = sorted(set(
            list(exec_dates) + [int(all_days[i]) for i in range(0, len(all_days), step)]
        ))
        logger.info(
            f"Prefetching stk_limit for {len(sample_days)} days "
            f"({len(exec_dates)} exec dates + samples)..."
        )

        # Group by month; fetch each day with write_cache=False, then
        # write the whole month at once with deduplication.
        from collections import defaultdict
        from data.panel_loader import get_loader as _gl
        _ldr = _gl()
        days_by_month = defaultdict(list)
        for d in sample_days:
            ym = d // 100  # YYYYMM -> YYYYMM
            days_by_month[ym].append(d)

        n_lim_rows = 0
        n_months = len(days_by_month)

        for ym, month_days in sorted(days_by_month.items()):
            month_chunks = []
            for day in month_days:
                try:
                    _lim = client.get_stk_limit(
                        trade_date=str(day), use_cache=False,
                        write_cache=False,  # Phase 0 manages the write
                    )
                    if not _lim.empty:
                        month_chunks.append(_lim)
                except Exception:
                    pass

            if month_chunks:
                lim_month = pd.concat(month_chunks, ignore_index=True)
                lim_month = lim_month.drop_duplicates(
                    ["ts_code", "trade_date"], keep="last"
                )
                if not lim_month.empty:
                    # Use merged write to preserve existing dates in this
                    # month that are not present in the current fetch.
                    # Short-window Phase 0 will no longer shrink the
                    # limit_status cache.
                    from data.limit_status_cache import write_limit_status_merged
                    month_new_rows = len(lim_month)
                    month_written = write_limit_status_merged(_ldr, lim_month)
                    n_lim_rows += month_new_rows
                    logger.debug(
                        f"  stk_limit {ym}: {month_new_rows} new rows → "
                        f"{month_written} partition rows"
                    )
                del lim_month
            del month_chunks

            if (ym - min(days_by_month.keys()) + 1) % 3 == 0:
                logger.debug(
                    f"  stk_limit: {ym - min(days_by_month.keys()) + 1}/{n_months} months"
                )

        logger.info(
            f"stk_limit prefetch complete: {n_lim_rows} rows "
            f"across {len(sample_days)} days in {n_months} months"
        )
    except Exception as e:
        logger.warning(f"stk_limit bulk prefetch failed: {e}")

    # 4. Build PIT universe
    from data.universe import get_universe_builder
    universe = get_universe_builder()
    universe.load(start_date=start_date, end_date=end_date)

    # 5. Verify tradable mask with a REAL non-empty universe date.
    #    Don't just pick day 6 blindly — find a date where universe >= 50
    #    stocks so the validation is meaningful.
    from data.tradable import get_tradable
    tradable = get_tradable()
    tradable.load(start_date=start_date, end_date=end_date)

    sample_date = None
    sample_univ = None
    for d in all_trade_days:
        univ = universe.get_universe(int(d))
        if len(univ) >= 50:
            sample_date = d
            sample_univ = univ[:50]
            break

    if sample_date is None:
        logger.error(
            f"No non-empty universe (>=50 stocks) found in {start_date}→{end_date}. "
            f"Check that index_weight data covers this range. "
            f"Run Phase 0 with a wider date range to prefetch more index_weight snapshots."
        )
        return 1

    from data.panel_loader import get_loader as _gl2
    _ldr2 = _gl2()
    raw_sample = _ldr2.query_prices(
        start_date=str(sample_date), end_date=str(sample_date),
        ts_codes=list(sample_univ),
        fields=["ts_code", "trade_date", "open"],
        price_type="raw"
    )
    limit_sample = _ldr2.query_limit_data(str(sample_date), ts_codes=list(sample_univ))
    mask = tradable.get_mask(
        list(sample_univ), int(sample_date),
        raw_prices=raw_sample,
        limit_data=limit_sample,
    )
    summary = tradable.mask_summary(mask)
    limit_avail = mask["limit_check_available"].all() if not mask.empty else False
    logger.info(
        f"Tradable mask check ({sample_date}, {len(sample_univ)} stocks): "
        f"total={summary['total']}, can_buy={summary['can_buy']}, "
        f"can_sell={summary['can_sell']}, "
        f"raw_prices={len(raw_sample)} rows, "
        f"limit_data={len(limit_sample) if limit_sample is not None else 0} rows, "
        f"limit_check_available={limit_avail}"
    )
    if summary["total"] == 0:
        logger.error(
            f"Tradable mask returned 0 stocks for sample date {sample_date}. "
            f"Tradable data may be missing."
        )
        return 1
    if not limit_avail:
        logger.warning(
            f"limit_check_available=False for sample date {sample_date}. "
            f"stk_limit data may not be cached yet. "
            f"Backtests will skip limit-up/down checks for this date."
        )
    if raw_sample.empty:
        logger.warning(
            f"No raw prices for sample date {sample_date}. "
            f"Tradable mask limit checks will be incomplete."
        )
    if limit_sample is None or limit_sample.empty:
        logger.warning(
            f"No limit data for sample date {sample_date} — DATA_INSUFFICIENT. "
            f"Run Phase 0 with a wider range to prefetch stk_limit data."
        )

    # 6. Universe diagnostics
    diag = universe.sample_universe_check(n_samples=20)
    if not diag.empty:
        logger.info(f"Universe check: {len(diag)} samples, "
                     f"mean stocks={diag['n_stocks'].mean():.0f}")

    # 7. limit_status coverage verification
    logger.info("Verifying limit_status coverage...")
    _lim_check = loader.query(
        "limit_status",
        columns=["ts_code", "trade_date"],
        start_date=start_date, end_date=end_date,
    )
    if _lim_check.empty:
        logger.error(
            "limit_status is EMPTY after Phase 0 fetch. "
            "stk_limit API may have returned no data. "
            "Backtest limit-up/down checks will be disabled."
        )
        return 1

    _lim_dupes = int(_lim_check.duplicated(["ts_code", "trade_date"]).sum())
    _lim_dates = set(_lim_check["trade_date"].unique())

    # Compute exec-date coverage
    _sig_dates = calendar.weekly_rebalance_dates(start_date, end_date)
    _exec_dates = {
        calendar.next_trade_day(int(d), 1) for d in _sig_dates[:-1]
    }
    _covered = _lim_dates & _exec_dates
    _lim_exec_coverage = len(_covered) / len(_exec_dates) if _exec_dates else 0.0

    logger.info(
        f"limit_status: {len(_lim_check)} rows, "
        f"{len(_lim_dates)} unique dates, "
        f"{_lim_dupes} duplicates, "
        f"exec_date coverage={_lim_exec_coverage:.1%} "
        f"({len(_covered)}/{len(_exec_dates)})"
    )

    if _lim_dupes > 0:
        logger.error(
            f"limit_status has {_lim_dupes} duplicate (ts_code, trade_date) rows. "
            f"Cache is corrupted — re-run Phase 0 to rebuild."
        )
        return 1

    if _lim_exec_coverage < 0.8:
        logger.error(
            f"limit_status exec_date coverage too low: "
            f"{_lim_exec_coverage:.1%} ({len(_covered)}/{len(_exec_dates)}). "
            f"Missing: {sorted(set(_exec_dates) - _lim_dates)[:10]}...\n"
            f"Backtests will miss limit-up/down checks for uncovered dates."
        )
        return 1

    # Memory report
    mem_report = monitor.report()
    logger.info(
        f"Phase 0 memory: peak={mem_report['peak_gb']:.2f}GB / "
        f"budget={mem_report['budget_gb']:.1f}GB, "
        f"checks={mem_report['checks']}"
    )
    logger.info("Phase 0 complete.")
    return 0


# ===================================================================
# Phase 1: Factor Computation + Evaluation
# ===================================================================
def run_phase1(args):
    """
    Phase 1: Compute factors and evaluate.

    1. Build factor panel (technical + fundamental)
    2. Cross-sectional processing
    3. Forward returns
    4. Per-factor evaluation (IC, ICIR, quantile returns, decay)
    5. Factor report
    """
    logger.info("=" * 60)
    logger.info("Phase 1: Factor Computation & Evaluation")
    logger.info("=" * 60)

    start_date = args.start or "20160101"
    end_date = args.end or datetime.now().strftime("%Y%m%d")

    if args.dry_run:
        logger.info("Dry run — listing factors only")
        from factors.technical import list_technical_factors
        logger.info(f"Technical factors: {list_technical_factors()}")
        return 0

    # 1. Build factor panel
    from factors.factor_panel import FactorPanelBuilder
    builder = FactorPanelBuilder()
    panel = builder.build_panel(
        start_date=start_date,
        end_date=end_date,
        signal_frequency=args.frequency or "weekly",
        recompute_all=args.recompute,
    )
    logger.info(f"Panel built: {len(panel)} processed factors")

    # 2. Evaluate factors
    from data.panel_loader import get_loader
    loader = get_loader()
    fwd_rets = loader.read_factor("fwd_returns", start_date, end_date)

    if fwd_rets.empty:
        logger.error("No forward returns — cannot evaluate factors")
        return 1

    from eval.cs_evaluator import CrossSectionEvaluator
    evaluator = CrossSectionEvaluator()

    # Evaluate all processed factors
    processed_factors = {k: v for k, v in panel.items() if not v.empty}
    all_results = evaluator.evaluate_all_factors(processed_factors, fwd_rets)

    # 3. Generate report
    from eval.factor_report import FactorReport
    reporter = FactorReport()
    report = reporter.report_multi_factor(all_results)

    report_path = Path("outputs/factor_report.md")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    reporter.save_report(report, str(report_path))

    logger.info(f"Factor report saved to {report_path}")
    safe_print(report)

    return 0


# ===================================================================
# Phase 2: MVP Backtest
# ===================================================================
def run_phase2(args):
    """
    Phase 2: MVP portfolio backtest.

    1. Compute IC-weighted composite score
    2. Run T+1 weekly rebalance backtest (top N equal weight)
    3. Benchmark vs CSI 300
    4. Report performance
    """
    logger.info("=" * 60)
    logger.info("Phase 2: MVP Portfolio Backtest")
    logger.info("=" * 60)

    start_date = args.start or "20160101"
    end_date = args.end or datetime.now().strftime("%Y%m%d")
    top_n = args.top_n or 50

    if args.dry_run:
        logger.info(f"Dry run: top_{top_n} equal-weight, {start_date}-{end_date}")
        return 0

    # 1. Load processed factors — with coverage validation
    from data.panel_loader import get_loader
    from alpha.ic_weighting import ICWeighting
    from data.calendar import get_calendar

    loader = get_loader()
    calendar = get_calendar()

    import glob

    def _get_cached_cs_factors():
        """Return list of _cs factor names from cache."""
        dirs = glob.glob("data/parquet/factors/factor_name=*")
        return sorted([
            Path(d).name.replace("factor_name=", "")
            for d in dirs if "_cs" in Path(d).name
        ])

    def _check_coverage():
        """Check if cached factors cover the requested date range."""
        factor_names = _get_cached_cs_factors()
        if not factor_names:
            return False, None

        # Check fwd_returns
        fwd_cov = loader.factor_coverage("fwd_returns", start_date, end_date)
        cs_covs = {}
        for name in factor_names:
            cov = loader.factor_coverage(name, start_date, end_date)
            cs_covs[name] = cov

        # Expected signal dates for this range
        expected_signal_dates = set(
            int(d) for d in calendar.weekly_rebalance_dates(start_date, end_date)
        )
        min_dates = max(16, int(len(expected_signal_dates) * 0.5))

        valid_factors = []
        for name, cov in cs_covs.items():
            if cov["rows"] == 0:
                continue
            if cov["n_dates"] < min_dates:
                continue
            # Factor must cover at least 60% of expected signal dates.
            # NOTE: duplicates in cache are a warning, not a hard block —
            # read_factor() deduplicates on read.
            df_temp = loader.query(
                f"factors/factor_name={name}",
                columns=["trade_date"],
                start_date=start_date, end_date=end_date
            )
            if df_temp.empty:
                continue
            actual_dates = set(df_temp["trade_date"].unique())
            overlap = len(actual_dates & expected_signal_dates)
            coverage_ratio = overlap / len(expected_signal_dates) if expected_signal_dates else 0
            if coverage_ratio < 0.6:
                continue
            if cov["duplicates"] > 0:
                logger.warning(
                    f"  {name}: {cov['duplicates']} duplicate rows in cache. "
                    f"read_factor will deduplicate on load. "
                    f"Run migrate_factor_cache.py to clean up."
                )
            valid_factors.append(name)

        coverage_ok = (
            fwd_cov["rows"] > 0
            and fwd_cov["duplicates"] == 0
            and fwd_cov["n_dates"] >= min_dates
            and len(valid_factors) >= 3
        )
        return coverage_ok, valid_factors

    # --- Phase 2 diagnostic chain ---
    # 1. Check prices_adj coverage first (root cause of most failures)
    adj_cov = loader.price_coverage("prices_adj", start_date, end_date)
    if adj_cov["coverage_ratio"] < 0.75:
        logger.error(
            f"prices_adj coverage too low: "
            f"{adj_cov['n_dates']}/{adj_cov['expected_trade_dates']} dates "
            f"({adj_cov['coverage_ratio']:.1%}). "
            f"Missing {len(adj_cov['missing_dates'])} dates. "
            f"First missing: {adj_cov['missing_dates'][:5]}\n"
            f"RUN Phase 0 FIRST: python run_research.py phase0 "
            f"--start {start_date} --end {end_date}"
        )
        return 1

    if not _check_phase2_price_quality(loader, start_date, end_date):
        return 1

    coverage_ok, valid_factors = _check_coverage()

    if not coverage_ok:
        fwd_cov = loader.factor_coverage("fwd_returns", start_date, end_date)

        # If --no-recompute is set, never auto-trigger Phase 1 rebuild.
        # This protects production cache from being overwritten by short
        # windows (e.g., smoke tests).
        if getattr(args, "no_recompute", False):
            logger.error(
                f"Factor coverage insufficient and --no-recompute is set. "
                f"Cannot proceed with Phase 2.\n"
                f"  fwd_returns: dates={fwd_cov.get('n_dates',0)}, "
                f"dupes={fwd_cov.get('duplicates',0)}\n"
                f"  valid _cs factors: {len(valid_factors)} (need >=3)\n"
                f"  prices_adj: {adj_cov['n_dates']}/{adj_cov['expected_trade_dates']} dates\n"
                f"Run Phase 1 manually first: "
                f"python run_research.py phase1 --start {start_date} "
                f"--end {end_date} --recompute"
            )
            return 1

        if fwd_cov["n_dates"] < 12:
            logger.warning(
                f"fwd_returns coverage insufficient: "
                f"{fwd_cov['n_dates']} dates (need >=12). "
                f"Running Phase 1 with --recompute to rebuild..."
            )
        else:
            logger.warning(
                f"Factor coverage insufficient: "
                f"valid _cs factors={len(valid_factors)} (need >=3). "
                f"Running Phase 1 to rebuild..."
            )
        # Run Phase 1 with recompute
        saved_recompute = args.recompute
        args.recompute = True
        rc1 = run_phase1(args)
        args.recompute = saved_recompute
        if rc1 != 0:
            logger.error("Phase 1 failed — cannot proceed with Phase 2")
            return 1

        # Re-check after rebuild
        coverage_ok, valid_factors = _check_coverage()
        if not coverage_ok:
            logger.error(
                "Still insufficient factor coverage after Phase 1 rebuild.\n"
                f"  prices_adj: {adj_cov['n_dates']}/{adj_cov['expected_trade_dates']} dates\n"
                f"  fwd_returns: dates={fwd_cov.get('n_dates',0)}, "
                f"dupes={fwd_cov.get('duplicates',0)}\n"
                f"  _cs factors found: {len(_get_cached_cs_factors())}\n"
                f"  Valid (>=16 dates, no dupes): {len(valid_factors)}\n"
                f"  Each factor coverage:\n" +
                "\n".join(
                    f"    {name}: {loader.factor_coverage(name, start_date, end_date)}"
                    for name in _get_cached_cs_factors()
                )
            )
            return 1
        logger.info(f"Rebuilt: {len(valid_factors)} valid _cs factors")

    factor_names = valid_factors if valid_factors else _get_cached_cs_factors()

    # Determine strategy mode
    strategy_mode = getattr(args, "strategy_mode", "factor_dynamic")

    if strategy_mode == "regime":
        # ── Regime mode: use independent factor pool from regime.yaml ──
        regime_config = _load_regime_config_safe(
            getattr(args, "regime_config", "configs/regime.yaml")
        )
        regime_factor_names = _select_regime_candidate_factors(
            loader, regime_config, start_date, end_date
        )
        if not regime_factor_names:
            logger.error("No regime factors available in cache — cannot proceed")
            return 1
        factor_names = regime_factor_names

        # Regime data window with warmup
        data_start, data_end = _compute_regime_load_window(
            start_date, end_date, regime_config, calendar=calendar,
        )
    else:
        # ── Factor dynamic mode: use enabled_factors from factors.yaml ──
        factor_config = _normalize_factor_config(
            _load_factor_config(_factors_config_path(args))
        )
        enabled_factors = factor_config["enabled_factors"]
        composite_params = factor_config["composite_params"]
        factor_names = _filter_enabled_factors(factor_names, enabled_factors)
        data_start, data_end = start_date, end_date
        if (code := _check_formal_candidate_policy(
            factor_config, _factors_config_path(args)
        )):
            return code

    logger.info(f"Loading {len(factor_names)} processed factors...")

    factor_dfs = {}
    for name in factor_names:
        df = loader.read_factor(name, data_start, data_end)
        if not df.empty:
            factor_dfs[name] = df

    fwd_rets = loader.read_factor("fwd_returns", data_start, data_end)

    # 2. Compute composite score
    signal_dates = calendar.weekly_rebalance_dates(start_date, end_date)
    signal_dates_int = [int(d) for d in signal_dates]

    if strategy_mode == "regime":
        logger.info("Using regime router strategy mode")
        composite, regime_diag = build_regime_composite(
            factor_dfs, fwd_rets, signal_dates_int,
            getattr(args, "regime_config", "configs/regime.yaml"),
            start_date, end_date, loader=loader,
            data_start_date=data_start, data_end_date=data_end,
        )
        if composite.empty:
            logger.error(
                "Regime composite failed to produce scores. "
                "Check regime config and index data coverage. "
                "Error: %s", regime_diag.get("error", "unknown"),
            )
            return 1
    else:
        icw = ICWeighting(**composite_params, factor_whitelist=enabled_factors)
        composite = icw.compute_composite_series(
            factor_dfs, fwd_rets, signal_dates_int
        )

    if composite.empty:
        logger.error(
            "Failed to compute composite scores. "
            "This is expected for very short date ranges (< 3 months) "
            "where rolling IC has insufficient history. "
            "Try a longer range: --start 20160101 --end 20161231"
        )
        return 1

    logger.info(f"Composite score: {len(composite)} rows")

    # 3. Run backtest — inject loaded dependencies for independence
    bt = _build_backtester(start_date, end_date, loader=loader)
    results = bt.run_backtest(
        scores=composite,
        score_col="composite_score",
        start_date=start_date,
        end_date=end_date,
        top_n=top_n,
        weighting="equal",
        rebalance_freq="weekly",
        entry_rank=getattr(args, "entry_rank", None),
        exit_rank=getattr(args, "exit_rank", None),
        return_diagnostics=True,
    )

    # Stash regime diag (if any) for the diagnostic-artifact writer. The
    # _dump_regime_diagnostics helper is a no-op for non-regime runs.
    if "_regime_diag" not in results:
        try:
            results["_regime_diag"] = regime_diag  # noqa: F821
        except NameError:
            pass  # non-regime mode; nothing to stash

    # 4. Check for backtest errors BEFORE generating report
    if isinstance(results, dict) and results.get("error"):
        logger.error(
            f"Backtest failed: {results['error']}. "
            f"n_periods={results.get('n_periods', 'N/A')}"
        )
        return 1

    # 5. Write run manifest and metrics summary (Phase 0)
    # factor_names is already filtered to enabled factors only
    used_factors = [f for f in factor_names if f in factor_dfs]
    _write_run_manifest(
        args.run_id, args,
        factor_list=used_factors,
        phases_run=["phase2"],
        extra={
            "weighting": "equal",
            "entry_rank": getattr(args, "entry_rank", None),
            "exit_rank": getattr(args, "exit_rank", None),
            "factors_config": getattr(args, "factors_config", None),
            "strategy_mode": strategy_mode,
            "regime_config": getattr(args, "regime_config", None),
        }
    )
    _write_metrics_summary(args.run_id, "phase2", results)

    # Save diagnostic artifacts for post-mortem analysis
    diag_payload = results.get("_diagnostics_payload", {})
    _write_diagnostic_artifacts(
        args.run_id, "phase2", results,
        portfolio_values=diag_payload.get("portfolio_values"),
        benchmark_period_returns={
            "benchmark_status": results.get("benchmark_status"),
            "benchmark_daily_rows": results.get("benchmark_daily_rows"),
            "benchmark_valid_periods": results.get("benchmark_valid_periods"),
            "benchmark_start": results.get("benchmark_start"),
            "benchmark_end": results.get("benchmark_end"),
        },
    )

    # 6. Generate report
    report = bt.generate_report(results, run_id=getattr(args, "run_id", None))
    report_path = Path("outputs/backtest_report.md")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)

    logger.info(f"Backtest report saved to {report_path}")
    safe_print(report)

    return 0


# ===================================================================
# Phase 3: Portfolio Optimization
# ===================================================================
def run_phase3(args):
    """
    Phase 3: Mean-variance portfolio optimization.

    Runs optimizations and compares to equal-weight baseline.
    Requires processed factors + composite scores from Phase 1-2.
    """
    logger.info("=" * 60)
    logger.info("Phase 3: Portfolio Optimization")
    logger.info("=" * 60)

    if args.dry_run:
        logger.info("Dry run: optimizer configuration check")
        try:
            import cvxpy
            logger.info(f"cvxpy {cvxpy.__version__} available — Phase 3 OK")
        except ImportError:
            logger.error(
                "cvxpy not installed! Phase 3 cannot run without cvxpy. "
                "Install with: pip install cvxpy"
            )
            return 1
        from portfolio.cov_estimator import CovarianceEstimator
        from portfolio.optimizer import PortfolioOptimizer
        from portfolio.constraints import ConstraintBuilder
        from portfolio.risk import RiskAnalytics
        logger.info("All optimizer modules importable")
        return 0

    start_date = args.start or "20160101"
    end_date = args.end or datetime.now().strftime("%Y%m%d")

    # Check for cvxpy
    try:
        import cvxpy
    except ImportError:
        logger.error("cvxpy not installed. Install with: pip install cvxpy")
        return 1

    # Load processed factors and scores
    from data.panel_loader import get_loader
    from data.calendar import get_calendar
    from alpha.ic_weighting import ICWeighting
    from alpha.score_to_mu import ScoreToMu
    from portfolio.cov_estimator import CovarianceEstimator
    from portfolio.optimizer import PortfolioOptimizer
    from portfolio.constraints import ConstraintBuilder

    loader = get_loader()
    calendar = get_calendar()
    calendar.load(start_date=start_date, end_date=end_date)

    # Load factor DFs using the same coverage rules as Phase 2.
    factor_names = _select_valid_cs_factors(loader, calendar, start_date, end_date)

    if not factor_names:
        logger.error("No valid processed (*_cs) factors found. Run phase1 first.")
        return 1

    # Determine strategy mode
    strategy_mode = getattr(args, "strategy_mode", "factor_dynamic")

    if strategy_mode == "regime":
        # ── Regime mode: use independent factor pool from regime.yaml ──
        regime_config = _load_regime_config_safe(
            getattr(args, "regime_config", "configs/regime.yaml")
        )
        regime_factor_names = _select_regime_candidate_factors(
            loader, regime_config, start_date, end_date
        )
        if not regime_factor_names:
            logger.error("No regime factors available in cache — cannot proceed")
            return 1
        factor_names = regime_factor_names

        # Regime data window with warmup
        data_start, data_end = _compute_regime_load_window(
            start_date, end_date, regime_config, calendar=calendar,
        )
        composite_horizon = regime_config.get("sleeve_composite", {}).get("horizon", 5)
    else:
        # ── Factor dynamic mode ──
        factor_config = _normalize_factor_config(
            _load_factor_config(_factors_config_path(args))
        )
        enabled_factors = factor_config["enabled_factors"]
        composite_params = factor_config["composite_params"]
        factor_names = _filter_enabled_factors(factor_names, enabled_factors)
        data_start, data_end = start_date, end_date
        composite_horizon = composite_params.get("horizon", 5)
        if (code := _check_formal_candidate_policy(
            factor_config, _factors_config_path(args)
        )):
            return code

    logger.info(f"Loading {len(factor_names)} valid processed factors...")
    factor_dfs = {}
    for name in factor_names:
        df = loader.read_factor(name, data_start, data_end)
        if not df.empty:
            factor_dfs[name] = df

    fwd_rets = loader.read_factor("fwd_returns", data_start, data_end)
    if fwd_rets.empty:
        logger.error("No forward returns. Run phase1 first.")
        return 1

    # Compute composite score
    signal_dates = calendar.weekly_rebalance_dates(start_date, end_date)
    signal_dates_int = [int(d) for d in signal_dates]

    if strategy_mode == "regime":
        logger.info("Phase 3: Using regime router strategy mode")
        composite, regime_diag = build_regime_composite(
            factor_dfs, fwd_rets, signal_dates_int,
            getattr(args, "regime_config", "configs/regime.yaml"),
            start_date, end_date, loader=loader,
            data_start_date=data_start, data_end_date=data_end,
        )
        if composite.empty:
            logger.error(
                "Phase 3: Regime composite failed. Error: %s",
                regime_diag.get("error", "unknown"),
            )
            return 1
    else:
        icw = ICWeighting(**composite_params, factor_whitelist=enabled_factors)
        composite = icw.compute_composite_series(factor_dfs, fwd_rets, signal_dates_int)

    # Calibrate scores to expected returns
    stm = ScoreToMu(method="rolling_ic")
    mu_df = stm.calibrate(composite, "composite_score", fwd_rets,
                          horizon=composite_horizon)

    # Run equal-weight baseline
    logger.info("Phase 3: Running equal-weight baseline...")
    bt = _build_backtester(start_date, end_date, loader=loader)
    ew_results = bt.run_backtest(
        scores=composite,
        start_date=start_date,
        end_date=end_date,
        top_n=args.top_n or 50,
        weighting="equal",
        return_diagnostics=True,
    )

    # ══════════════════════════════════════════════════════════════════
    # Price window coverage check before optimization
    # ══════════════════════════════════════════════════════════════════
    # The optimizer needs ~252 trading days of price history BEFORE each
    # execution date for covariance estimation.  A naive n_dates >= 200
    # check misclassifies 2016-only data as sufficient when the 2015
    # lookback is actually missing.
    #
    # CORRECT approach: find the REAL candidate signal dates (those where
    # composite has scores), compute each one's exec_date + lookback_start,
    # then take the UNION [min(lookback_starts), max(exec_dates)] and
    # check prices_adj coverage across that range.
    # ══════════════════════════════════════════════════════════════════
    from data.calendar import get_calendar as _get_calendar
    from data.panel_loader import get_loader as _get_loader_p3
    _cal = _get_calendar()
    _cal.load(start_date="20150101", end_date=end_date)
    _loader_p3 = _get_loader_p3()

    # 1. Find candidate dates — signal dates that actually have composite
    #    scores.  The first weekly signal (e.g. 20160104) often has no
    #    composite data yet; the optimizer won't run until composite is
    #    populated.
    _composite_dates = set(composite["trade_date"].astype(int).unique())
    _candidate_dates = sorted(
        d for d in signal_dates_int if d in _composite_dates
    )
    if not _candidate_dates:
        logger.error(
            "OPTIMIZER_PRICE_CACHE_INSUFFICIENT: "
            "No candidate signal dates — composite has no overlap with "
            "weekly rebalance schedule"
        )
        return 1

    # 2. Compute execution dates and lookback starts for EVERY candidate
    _exec_dates = [_cal.next_trade_day(d, 1) for d in _candidate_dates]
    _lookback_starts = [_cal.prev_trade_day(ed, 252) for ed in _exec_dates]
    required_start = int(min(_lookback_starts))
    required_end = int(max(_exec_dates))

    logger.info(
        f"Price precheck: {len(_candidate_dates)} candidate dates, "
        f"required_start={required_start}, required_end={required_end}"
    )

    # 3. Expected trade dates from calendar (the full required window)
    _expected_arr = _cal.trade_days_between(required_start, required_end)
    _expected_dates = set(int(d) for d in _expected_arr)
    _n_expected = len(_expected_dates)

    # 4. Query actual trade dates DIRECTLY from prices_adj.
    #    Do NOT rely on price_coverage().missing_dates — that list is
    #    truncated to 20 entries and will produce an inflated coverage
    #    ratio when the real gap is larger.
    _prices_df = _loader_p3.query(
        "prices_adj",
        columns=["trade_date"],
        start_date=str(required_start),
        end_date=str(required_end),
    )
    if _prices_df.empty:
        _actual_dates = set()
        price_dates_available = 0
        _min_actual_date = 0
    else:
        _actual_dates = set(int(d) for d in _prices_df["trade_date"].unique())
        price_dates_available = len(_actual_dates)
        _min_actual_date = int(_prices_df["trade_date"].min())

    # 5. Compute coverage from the real actual vs expected sets
    _missing_dates = _expected_dates - _actual_dates
    if _n_expected > 0:
        _coverage_ratio = len(_actual_dates) / _n_expected
        _n_missing = len(_missing_dates)
        _first_missing = sorted(_missing_dates)[:10] if _missing_dates else []
    else:
        _coverage_ratio = 0.0
        _n_missing = 0
        _first_missing = []

    # 6. Hard thresholds
    _MISSING_THRESHOLD = 5
    _COVERAGE_THRESHOLD = 0.95

    _precheck_failures = []
    if _coverage_ratio < _COVERAGE_THRESHOLD:
        _precheck_failures.append(
            f"Coverage ratio {_coverage_ratio:.1%} < {_COVERAGE_THRESHOLD:.0%}"
        )
    if _min_actual_date > 0 and int(_min_actual_date) > required_start:
        _precheck_failures.append(
            f"Earliest actual date {_min_actual_date} > "
            f"required_start {required_start}"
        )
    if _n_missing > _MISSING_THRESHOLD:
        _precheck_failures.append(
            f"Missing dates {_n_missing} > threshold {_MISSING_THRESHOLD}"
        )

    if _precheck_failures:
        logger.error(
            f"OPTIMIZER_PRICE_CACHE_INSUFFICIENT\n"
            f"  required_start: {required_start}\n"
            f"  required_end: {required_end}\n"
            f"  n_candidates: {len(_candidate_dates)}\n"
            f"  first_candidate: {_candidate_dates[0]}\n"
            f"  last_candidate: {_candidate_dates[-1]}\n"
            f"  expected_dates: {_n_expected}\n"
            f"  actual_dates: {price_dates_available}\n"
            f"  coverage_ratio: {_coverage_ratio:.1%} "
            f"(threshold: {_COVERAGE_THRESHOLD:.0%})\n"
            f"  missing_dates: {_n_missing} "
            f"(threshold: {_MISSING_THRESHOLD})\n"
            f"  first_missing_dates: {_first_missing}\n"
            f"  Failures: {'; '.join(_precheck_failures)}\n"
            f"\n"
            f"  The optimizer needs ~1 year of historical prices before each\n"
            f"  execution date for covariance estimation.  Run:\n"
            f"\n"
            f"    python run_research.py phase0 --start 20150101 --end {end_date}\n"
            f"\n"
            f"  to populate prices_adj cache, then retry Phase 3."
        )
        # Write FAIL metrics before returning (don't leave stale success data)
        _fail_run_id = getattr(args, "run_id", "unknown")
        _fail_metrics = {
            "run_id": _fail_run_id,
            "status": "FAIL",
            "error": "OPTIMIZER_PRICE_CACHE_INSUFFICIENT",
            "failure_reasons": _precheck_failures,
            "required_start": str(required_start),
            "required_end": str(required_end),
            "n_candidates": len(_candidate_dates),
            "first_candidate": str(_candidate_dates[0]),
            "last_candidate": str(_candidate_dates[-1]),
            "coverage_ratio": _coverage_ratio,
            "expected_dates": _n_expected,
            "actual_dates": price_dates_available,
            "n_missing": _n_missing,
            "first_missing_dates": [str(d) for d in _first_missing],
            "fix_command": (
                f"python run_research.py phase0 --start 20150101 --end {end_date}"
            ),
        }
        _write_metrics_summary(_fail_run_id, "phase3_optimized", _fail_metrics)
        return 1

    logger.info(
        f"Price window coverage: {len(_candidate_dates)} candidates, "
        f"required_start={required_start}, required_end={required_end}, "
        f"expected={_n_expected}, actual={price_dates_available}, "
        f"coverage_ratio={_coverage_ratio:.1%} — sufficient"
    )

    # Run optimized backtest
    logger.info("Phase 3: Running optimized portfolio...")
    try:
        import cvxpy  # noqa: F401
    except ImportError:
        logger.error(
            "cvxpy not installed. Phase 3 requires cvxpy for optimization. "
            "Install with: pip install cvxpy"
        )
        return 1

    opt_top_n = args.top_n or 50
    opt_weight_max = args.weight_max or 0.02
    opt_turnover_max = args.turnover_max
    opt_turnover_penalty = args.turnover_penalty

    # Batch 3: Forward ALL strategy params to Phase 3 optimized backtest
    strat = _strategy_kwargs_from_args(args)
    opt_results = bt.run_backtest(
        scores=composite,
        score_col="composite_score",
        start_date=start_date,
        end_date=end_date,
        top_n=opt_top_n,
        weighting="optimized",
        mu_df=mu_df,
        weight_max=opt_weight_max,
        return_diagnostics=True,
        **strat,
    )

    # ---- Hard validation: prevent Phase3 false success ----
    opt_validation_errors = []
    if opt_results.get("error"):
        opt_validation_errors.append(
            f"Optimized backtest returned error: {opt_results['error']}"
        )
    if opt_results.get("n_periods", 0) < 5:
        opt_validation_errors.append(
            f"Optimized backtest has insufficient periods: "
            f"n_periods={opt_results.get('n_periods', 0)} (need >= 5)"
        )
    opt_n_total = opt_results.get("opt_n_total", 0)
    if opt_n_total == 0:
        opt_validation_errors.append(
            "Optimizer never ran: opt_n_total=0. "
            "Check that weighting='optimized' was used, mu_df was provided, "
            "and rebalance dates were generated."
        )

    # Hard threshold: fallback rate must be <= 20%
    fallback_rate = opt_results.get("optimizer_fallback_rate", 0.0)
    if opt_n_total > 0 and fallback_rate > 0.20:
        opt_validation_errors.append(
            f"Optimizer fallback rate {fallback_rate:.1%} > 20% threshold. "
            f"{opt_results.get('opt_n_fallback', 0)} of {opt_n_total} "
            f"optimizations fell back to equal-weight. "
            f"Top reasons: {opt_results.get('opt_fallback_reasons', {})}"
        )

    # Hard threshold: optimized weights must differ from equal-weight
    # (avg_active_weight should be meaningfully different from 1/top_n)
    avg_active = opt_results.get("avg_active_weight", 0.0)
    eq_weight = 1.0 / max(opt_n_total, opt_results.get("n_periods", 1), 1)
    top_n_val = args.top_n or 50
    eq_w = 1.0 / top_n_val
    if opt_n_total > 0 and avg_active > 0 and abs(avg_active - eq_w) < 0.0001:
        opt_validation_errors.append(
            f"Optimized weights are identical to equal-weight: "
            f"avg_active_weight={avg_active:.6f} ≈ 1/top_n={eq_w:.6f}. "
            f"Optimizer produced no meaningful differentiation."
        )

    if opt_validation_errors:
        logger.error("PHASE3 OPTIMIZED BACKTEST INVALID:")
        for err in opt_validation_errors:
            logger.error(f"  - {err}")

        # Write FAIL metrics BEFORE returning — overwrites any stale
        # success data from a previous run, preventing auto-validation
        # from misreading old results.
        _fail_opt_metrics = {
            "run_id": args.run_id,
            "status": "FAIL",
            "error": "OPTIMIZED_BACKTEST_INVALID",
            "failure_reasons": opt_validation_errors,
            "n_periods": opt_results.get("n_periods", 0),
            "opt_n_total": opt_n_total,
            "opt_n_fallback": opt_results.get("opt_n_fallback", 0),
            "optimizer_fallback_rate": fallback_rate,
            "avg_active_weight": avg_active,
            "opt_fallback_reasons": opt_results.get("opt_fallback_reasons", {}),
        }
        _write_metrics_summary(args.run_id, "phase3_equal_weight", ew_results)
        _write_metrics_summary(args.run_id, "phase3_optimized", _fail_opt_metrics)
        # Save diagnostics even for FAILED runs
        _write_diagnostic_artifacts(
            args.run_id, "phase3_equal_weight", ew_results,
            portfolio_values=(ew_results.get("_diagnostics_payload", {}).get("portfolio_values")),
        )
        _write_diagnostic_artifacts(
            args.run_id, "phase3_optimized", opt_results,
            portfolio_values=(opt_results.get("_diagnostics_payload", {}).get("portfolio_values")),
        )
        logger.info(
            f"Phase 3 FAIL metrics written to outputs/metrics_summary.json "
            f"and outputs/latest_metrics_summary.json"
        )

        # Still generate a minimal report explaining the failure
        fail_report_lines = [
            "# Phase 3: OPTIMIZED BACKTEST INVALID",
            f"Period: {start_date} → {end_date}",
            f"Top N: {args.top_n or 50}",
            "",
            "## FAILURE REASONS",
        ]
        for err in opt_validation_errors:
            fail_report_lines.append(f"- {err}")
        fail_report_lines.append("")
        fail_report_lines.append(
            "The optimized backtest did not produce valid results. "
            "No comparison table can be generated."
        )
        fail_report_lines.append("")
        fail_report_lines.append("### Available Diagnostics")
        fail_report_lines.append(f"- n_periods: {opt_results.get('n_periods', 0)}")
        fail_report_lines.append(f"- opt_n_total: {opt_n_total}")
        fail_report_lines.append(f"- fallback_rate: {fallback_rate:.1%}")
        fail_report_lines.append(f"- avg_active_weight: {avg_active:.6f}")
        fail_report_lines.append(f"- error: {opt_results.get('error', 'N/A')}")

        fail_report = "\n".join(fail_report_lines)
        fail_report_path = Path("outputs/optimization_report.md")
        fail_report_path.parent.mkdir(parents=True, exist_ok=True)
        with open(fail_report_path, "w", encoding="utf-8") as f:
            f.write(fail_report)
        logger.info(f"Phase 3 failure report saved to {fail_report_path}")
        return 1

    logger.info(
        f"Phase 3 optimized validation passed: "
        f"n_periods={opt_results.get('n_periods')}, "
        f"opt_n_total={opt_n_total}, "
        f"fallback_rate={fallback_rate:.1%}, "
        f"avg_active_weight={avg_active:.6f} (vs equal-weight {eq_w:.6f})"
    )

    # Write run manifest and metrics summary (Phase 0)
    # factor_names is already filtered to enabled factors only
    used_factors = [f for f in factor_names if f in factor_dfs]
    _write_run_manifest(
        args.run_id, args,
        factor_list=used_factors,
        phases_run=["phase3"],
        extra={
            "weighting": "optimized",
            "weight_max": opt_weight_max,
            **{k: v for k, v in strat.items() if v is not None},
        }
    )
    _write_metrics_summary(args.run_id, "phase3_equal_weight", ew_results)
    _write_metrics_summary(args.run_id, "phase3_optimized", opt_results)
    # Save diagnostic artifacts for post-mortem analysis
    _write_diagnostic_artifacts(
        args.run_id, "phase3_equal_weight", ew_results,
        portfolio_values=(ew_results.get("_diagnostics_payload", {}).get("portfolio_values")),
    )
    _write_diagnostic_artifacts(
        args.run_id, "phase3_optimized", opt_results,
        portfolio_values=(opt_results.get("_diagnostics_payload", {}).get("portfolio_values")),
    )

    # Compare
    report_lines = [
        "# Phase 3: Optimized vs Equal-Weight Comparison",
        f"Period: {start_date} → {end_date}",
        f"Top N: {args.top_n or 50}",
        "",
        "## Performance Comparison",
        "| Metric | Equal-Weight | Optimized | Delta |",
        "|--------|-------------|-----------|-------|",
    ]

    metrics_to_compare = [
        ("annualized_return", "Ann. Return"),
        ("annualized_excess_return", "Ann. Excess Return"),
        ("information_ratio", "Information Ratio"),
        ("annualized_volatility", "Ann. Volatility"),
        ("max_drawdown", "Max Drawdown"),
        ("sharpe_ratio", "Sharpe Ratio"),
        ("avg_turnover", "Avg Turnover"),
        ("total_cost_bps", "Total Cost (bps)"),
    ]

    for key, label in metrics_to_compare:
        ew_val = ew_results.get(key, 0)
        opt_val = opt_results.get(key, 0)
        if isinstance(ew_val, (int, float)) and isinstance(opt_val, (int, float)):
            delta = opt_val - ew_val
            report_lines.append(
                f"| {label} | {ew_val:.4f} | {opt_val:.4f} | {delta:+.4f} |"
            )

    report_lines.append("")
    report_lines.append(
        f"**IR Improvement**: {opt_results.get('information_ratio', 0) - ew_results.get('information_ratio', 0):+.3f}"
    )
    report_lines.append(
        f"**Excess Return Improvement**: "
        f"{opt_results.get('annualized_excess_return', 0) - ew_results.get('annualized_excess_return', 0):+.4%}"
    )

    # Optimizer diagnostics
    report_lines.append("")
    report_lines.append("## Optimizer Diagnostics")
    report_lines.append(f"- Fallback Rate: {opt_results.get('optimizer_fallback_rate', 0):.2%}")
    report_lines.append(f"- Mu Usage Rate: {opt_results.get('used_mu_rate', 0):.2%}")
    report_lines.append(f"- Total Optimizations: {opt_results.get('opt_n_total', 0)}")
    report_lines.append(f"- Fallbacks: {opt_results.get('opt_n_fallback', 0)}")
    report_lines.append(f"- Low Optimizer Space: {opt_results.get('opt_n_low_space', 0)}")
    report_lines.append(f"- Avg Active Weight: {opt_results.get('avg_active_weight', 0):.4f}")
    report_lines.append(f"- Max Single Weight: {opt_results.get('max_single_weight', 0):.4f}")
    # Fallback reason breakdown
    reasons = opt_results.get("opt_fallback_reasons", {})
    if reasons:
        report_lines.append("")
        report_lines.append("### Fallback Reason Top 5")
        top5 = sorted(reasons.items(), key=lambda x: -x[1])[:5]
        for reason, count in top5:
            report_lines.append(f"- {reason}: {count}")
    # Low optimizer space flag
    low_space = opt_results.get("opt_n_low_space", 0)
    if low_space > 0:
        report_lines.append("")
        report_lines.append(
            f"⚠️ **Low Optimizer Space**: {low_space} rebalances had "
            f"top_n × weight_max ≤ 1.05 — very little room to deviate "
            f"from equal-weight. Consider increasing weight_max or "
            f"reducing top_n."
        )
    # Optimization space summary
    opt_used = (opt_results.get("avg_active_weight", 0)
                if opt_results.get("avg_active_weight", 0) > 0
                else opt_results.get("max_single_weight", 0))
    if opt_used > 0 and opt_used < 0.021:
        report_lines.append("")
        report_lines.append(
            f"⚠️ **Weights near equal-weight**: avg_active={opt_results.get('avg_active_weight', 0):.4f}, "
            f"max={opt_results.get('max_single_weight', 0):.4f}. "
            f"Optimizer is not meaningfully differentiating from equal-weight. "
            f"Possible causes: weak mu signal, binding weight_max constraint, "
            f"or covariance issues."
        )

    report = "\n".join(report_lines)
    report_path = Path("outputs/optimization_report.md")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)

    logger.info(f"Phase 3 report saved to {report_path}")
    safe_print(report)
    return 0


# ===================================================================
# Phase 4: ML Alpha
# ===================================================================
def run_phase4(args):
    """
    Phase 4: Machine learning alpha.

    Walk-forward GBDT/RF for cross-sectional return prediction.
    Requires factor panel from Phase 1.
    """
    logger.info("=" * 60)
    logger.info("Phase 4: ML Alpha")
    logger.info("=" * 60)

    if args.dry_run:
        from alpha.ml_alpha import MLAlphaModel
        model = MLAlphaModel(model_type="gradient_boosting")
        logger.info(f"MLAlphaModel initialized: {model.model_type}")
        return 0

    start_date = args.start or "20160101"
    end_date = args.end or datetime.now().strftime("%Y%m%d")

    from data.panel_loader import get_loader
    from alpha.ml_alpha import MLAlphaModel
    from data.calendar import get_calendar
    import glob

    loader = get_loader()
    calendar = get_calendar()
    calendar.load(start_date=start_date, end_date=end_date)

    # Load processed factors
    factor_dirs = glob.glob("data/parquet/factors/factor_name=*_cs")
    factor_names = [Path(d).name.replace("factor_name=", "") for d in factor_dirs]

    if not factor_names:
        logger.error("No processed (*_cs) factors found. Run phase1 first.")
        return 1

    logger.info(f"Loading {len(factor_names)} processed factors...")
    factor_dfs = {}
    for name in factor_names[:15]:
        df = loader.read_factor(name, start_date, end_date)
        if not df.empty:
            factor_dfs[name] = df

    fwd_rets = loader.read_factor("fwd_returns", start_date, end_date)
    if fwd_rets.empty:
        logger.error("No forward returns. Run phase1 first.")
        return 1

    # Run ML walk-forward
    dates = sorted(fwd_rets["trade_date"].unique().tolist())
    logger.info(f"ML walk-forward: {len(dates)} total dates")

    model = MLAlphaModel(model_type="gradient_boosting", target_horizon=5)
    wf_results = model.walk_forward_train(factor_dfs, fwd_rets, dates)

    if not wf_results:
        logger.error("Walk-forward training produced no folds")
        return 1

    # Evaluate
    eval_result = model.evaluate_walk_forward(wf_results)

    # Report
    report_lines = [
        "# ML Alpha Walk-Forward Report",
        f"Model: {model.model_type}",
        f"Target horizon: {model.target_horizon}d",
        f"Folds: {eval_result['n_folds']}",
        f"Train IC mean: {eval_result['train_ic_mean']:.4f}",
        f"Test IC mean: {eval_result['test_ic_mean']:.4f}",
        f"Test IC std: {eval_result['test_ic_std']:.4f}",
        f"Test IC positive rate: {eval_result['test_ic_positive_rate']:.2%}",
        f"IC stability: {eval_result['ic_collapse']}",
    ]

    if model.feature_importance is not None:
        report_lines.append("\n## Feature Importance")
        for _, row in model.feature_importance.head(10).iterrows():
            report_lines.append(f"- {row['feature']}: {row['importance']:.4f}")

    report = "\n".join(report_lines)
    report_path = Path("outputs/ml_alpha_report.md")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)

    logger.info(f"Phase 4 report saved to {report_path}")
    safe_print(report)
    return 0


# ===================================================================
# Phase 5: Robustness
# ===================================================================
def run_phase5(args):
    """
    Phase 5: Robustness tests and Go/No-Go assessment.

    Runs comprehensive robustness suite:
    - Cost sensitivity (1x/2x/3x)
    - Slippage sensitivity (5/10/20bp)
    - Rebalance frequency (weekly/monthly)
    - Portfolio size (Top30/50/100)
    - Single stock caps (feasible combos only)
    - Market regime segments
    - Industry deviation (when industry data available)
    """
    logger.info("=" * 60)
    logger.info("Phase 5: Robustness & Go/No-Go")
    logger.info("=" * 60)

    phase5_suite = getattr(args, "phase5_suite", "full")

    if args.dry_run:
        from validation.robustness import RobustnessTester
        from validation.walk_forward import WalkForwardValidator
        logger.info("All validation modules importable")
        # Print expected test matrix
        logger.info("Robustness suite (dry-run):")
        logger.info("  - cost_sensitivity: 1x, 2x, 3x")
        logger.info("  - slippage_sensitivity: 5bp, 10bp, 20bp")
        logger.info("  - rebalance_frequency: weekly, monthly")
        logger.info("  - portfolio_size: Top30, Top50, Top100")
        logger.info("  - stock_caps: feasible combinations only")
        logger.info("  - market_regimes: 4 periods")
        logger.info("  - industry_deviation: SKIPPED (requires PIT industry data)")
        return 0

    start_date = args.start or "20160101"
    end_date = args.end or datetime.now().strftime("%Y%m%d")
    oos_start_date = getattr(args, "phase5_oos_start", None) or "20250101"
    oos_end_date = getattr(args, "phase5_oos_end", None) or end_date
    load_start_date = min(start_date, oos_start_date)
    load_end_date = max(end_date, oos_end_date)

    from data.panel_loader import get_loader
    from data.calendar import get_calendar
    from alpha.ic_weighting import ICWeighting
    from alpha.score_to_mu import ScoreToMu
    from validation.robustness import RobustnessTester

    loader = get_loader()
    calendar = get_calendar()
    calendar.load(start_date=load_start_date, end_date=load_end_date)

    # Load factors and compute scores (same as Phase 2)
    factor_names = _select_valid_cs_factors(loader, calendar, start_date, end_date)

    if not factor_names:
        logger.error("No valid processed factors. Run phase1 first.")
        return 1

    # Determine strategy mode
    strategy_mode = getattr(args, "strategy_mode", "factor_dynamic")

    if strategy_mode == "regime":
        # ── Regime mode: use independent factor pool from regime.yaml ──
        regime_config = _load_regime_config_safe(
            getattr(args, "regime_config", "configs/regime.yaml")
        )
        regime_factor_names = _select_regime_candidate_factors(
            loader, regime_config, load_start_date, load_end_date,
        )
        if not regime_factor_names:
            logger.error("No regime factors available in cache — cannot proceed")
            return 1
        factor_names = regime_factor_names

        # Regime data window with warmup, extended to OOS range
        data_start, _ = _compute_regime_load_window(
            start_date, load_end_date, regime_config, calendar=calendar,
        )
        data_end = load_end_date
        p5_horizon = regime_config.get("sleeve_composite", {}).get("horizon", 5)
    else:
        # ── Factor dynamic mode ──
        factor_config = _normalize_factor_config(
            _load_factor_config(_factors_config_path(args))
        )
        enabled_factors = factor_config["enabled_factors"]
        composite_params = factor_config["composite_params"]
        factor_names = _filter_enabled_factors(factor_names, enabled_factors)
        data_start, data_end = load_start_date, load_end_date
        p5_horizon = composite_params.get("horizon", 5)
        if (code := _check_formal_candidate_policy(
            factor_config, _factors_config_path(args)
        )):
            return code

    logger.info(f"Loading {len(factor_names)} valid processed factors...")
    factor_dfs = {}
    for name in factor_names:
        df = loader.read_factor(name, data_start, data_end)
        if not df.empty:
            factor_dfs[name] = df

    fwd_rets = loader.read_factor("fwd_returns", data_start, data_end)

    # Generate composite scores for the UNION of all signal dates that
    # robustness scenarios will use.
    weekly_dates = set(calendar.weekly_rebalance_dates(start_date, end_date))
    monthly_dates = set(calendar.monthly_rebalance_dates(start_date, end_date))
    if phase5_suite == "core" and oos_start_date <= oos_end_date:
        weekly_dates.update(calendar.weekly_rebalance_dates(oos_start_date, oos_end_date))
        monthly_dates.update(calendar.monthly_rebalance_dates(oos_start_date, oos_end_date))
    all_signal_dates = sorted(weekly_dates | monthly_dates)
    signal_dates_int = [int(d) for d in all_signal_dates]
    logger.info(
        f"Phase 5 signal dates: {len(weekly_dates)} weekly + "
        f"{len(monthly_dates)} monthly = {len(all_signal_dates)} union"
    )

    if strategy_mode == "regime":
        logger.info("Phase 5: Using regime router strategy mode")
        composite, regime_diag = build_regime_composite(
            factor_dfs, fwd_rets, signal_dates_int,
            getattr(args, "regime_config", "configs/regime.yaml"),
            start_date, load_end_date, loader=loader,
            data_start_date=data_start, data_end_date=data_end,
        )
    else:
        icw = ICWeighting(**composite_params, factor_whitelist=enabled_factors)
        composite = icw.compute_composite_series(factor_dfs, fwd_rets, signal_dates_int)

    if composite.empty:
        logger.error("Phase 5: Composite is empty — cannot proceed")
        return 1

    # Calibrate scores to mu for optimized weighting tests
    mu_df = None
    try:
        from alpha.score_to_mu import ScoreToMu
        stm = ScoreToMu(method="rolling_ic")
        mu_df = stm.calibrate(composite, "composite_score", fwd_rets,
                              horizon=p5_horizon)
        logger.info(f"mu_df calibrated: {len(mu_df)} rows")
    except Exception as e:
        logger.warning(f"mu calibration skipped: {e}")

    # Determine industry data availability
    # Static industry data (from stock_basic) exists but is NOT PIT.
    # Industry deviation constraint requires PIT data with effective dates.
    industry_available = False
    try:
        from data.industry import get_industry_classifier
        ic = get_industry_classifier()
        # Only enable industry deviation tests when PIT data is available
        industry_available = ic.has_data and ic.has_pit_data
        if ic.has_data and not ic.has_pit_data:
            logger.info("Industry data is static (not PIT) — industry deviation tests skipped")
    except Exception as e:
        logger.debug(f"Industry classifier check failed: {e}")

    # Define backtest function for robustness tester
    bt_cache = {}

    def _get_bt(bt_start: str, bt_end: str):
        key = (bt_start, bt_end)
        if key not in bt_cache:
            bt_cache[key] = _build_backtester(bt_start, bt_end, loader=loader)
        return bt_cache[key]

    def run_bt(**kwargs):
        bt_start = kwargs.get("start_date", start_date)
        bt_end = kwargs.get("end_date", end_date)
        bt = _get_bt(bt_start, bt_end)
        # Merge CLI defaults with call-site overrides (Batch 3)
        strat = _merge_strategy_kwargs(args, kwargs)
        return bt.run_backtest(
            scores=composite,
            score_col="composite_score",
            start_date=bt_start,
            end_date=bt_end,
            top_n=kwargs.get("top_n", 50),
            weighting=kwargs.get("weighting", "equal"),
            rebalance_freq=kwargs.get("rebalance_freq", "weekly"),
            cost_multiplier=kwargs.get("cost_multiplier", 1.0),
            slippage_bps=kwargs.get("slippage_bps"),
            weight_max=kwargs.get("weight_max", 0.02),
            mu_df=kwargs.get("mu_df", mu_df),
            **strat,
        )

    # Run robustness tests
    tester = RobustnessTester(run_bt)
    base_config = {
        "start_date": start_date,
        "end_date": end_date,
        "top_n": args.top_n or 50,
        "weighting": "optimized",
        "weight_max": args.weight_max or 0.02,
        "turnover_max": args.turnover_max,
        "turnover_penalty": args.turnover_penalty,
        "mu_df": mu_df,
    }
    skipped = []  # track skipped tests with reasons

    if phase5_suite == "core":
        logger.info("Running Phase 5 core suite: base, 2x cost, recent OOS")

        base_result = _load_matching_phase3_optimized(base_config)
        if base_result is None:
            base_result = run_bt(**base_config)
        base_result["cost_scenario"] = "1x"
        tester._results["cost_1x"] = base_result

        cost_2x_config = deepcopy(base_config)
        cost_2x_config["cost_multiplier"] = 2.0
        cost_2x_result = run_bt(**cost_2x_config)
        cost_2x_result["cost_scenario"] = "2x"
        tester._results["cost_2x"] = cost_2x_result

        if oos_end_date < oos_start_date:
            recent_oos = {
                "regime": f"{oos_start_date}+ OOS",
                "start_date": oos_start_date,
                "end_date": oos_end_date,
                "data_missing": True,
                "error": (
                    f"Recent OOS start_date {oos_start_date} is after "
                    f"Phase 5 OOS end_date {oos_end_date}"
                ),
                "n_periods": 0,
            }
        else:
            recent_config = deepcopy(base_config)
            recent_config["start_date"] = oos_start_date
            recent_config["end_date"] = oos_end_date
            recent_oos = run_bt(**recent_config)
            recent_oos["regime"] = f"{oos_start_date}+ OOS"
            recent_oos["start_date"] = oos_start_date
            recent_oos["end_date"] = oos_end_date
        recent_oos["data_missing"] = (
            recent_oos.get("error") is not None
            or recent_oos.get("n_periods", 0) < 5
        )
        if recent_oos["data_missing"]:
            for key in ("annualized_return", "annualized_excess_return",
                        "sharpe_ratio", "information_ratio",
                        "max_drawdown", "avg_turnover"):
                if key in recent_oos:
                    recent_oos[key] = float("nan")
        tester._results["regime_2025+ OOS"] = recent_oos

        go_nogo = tester.go_nogo_check(
            base_result,
            cost_2x_result=cost_2x_result,
            recent_oos_result=recent_oos,
        )

        if recent_oos.get("data_missing"):
            go_nogo["verdict"] = "NO-GO (OOS missing or insufficient data)"
            go_nogo["oos_available"] = False
            logger.warning(
                "Go/No-Go: Recent OOS (2025+) is missing or has insufficient data. "
                "Verdict forced to NO-GO. Run Phase 0/1 with full date range "
                "to populate OOS data and factors."
            )
        else:
            go_nogo["oos_available"] = True

        used_factors = [f for f in factor_names if f in factor_dfs]
        _write_run_manifest(
            args.run_id, args,
            factor_list=used_factors,
            phases_run=["phase5"],
            extra={
                "go_nogo_verdict": go_nogo.get("verdict", "UNKNOWN"),
                "phase5_suite": "core",
                "phase5_oos_start": oos_start_date,
                "phase5_oos_end": oos_end_date,
            },
        )
        _write_metrics_summary(args.run_id, "phase5_base", base_result)
        if not cost_2x_result.get("error"):
            _write_metrics_summary(args.run_id, "phase5_cost_2x", cost_2x_result)
        if not recent_oos.get("error") and recent_oos.get("n_periods", 0) >= 5:
            _write_metrics_summary(args.run_id, "phase5_recent_oos", recent_oos)
        # Save diagnostic artifacts
        _write_diagnostic_artifacts(
            args.run_id, "phase5_base", base_result,
            portfolio_values=(base_result.get("_diagnostics_payload", {}).get("portfolio_values")),
        )

        report = tester.generate_report()
        report += "\n\n# Go/No-Go Assessment\n\n"
        report += f"**Verdict: {go_nogo['verdict']}** "
        report += f"(Hard: {go_nogo.get('n_hard_pass', 0)}/{go_nogo.get('n_hard_total', 0)} passed"
        if go_nogo.get("n_warning_fail", 0) > 0:
            report += f", Warning fails: {go_nogo['n_warning_fail']}"
        report += ")\n\n"

        # Hard checks table
        hard_checks = go_nogo.get("hard_checks", {})
        if hard_checks:
            report += "### Hard Checks (determine GO/NO-GO)\n\n"
            report += "| Check | Value | Threshold | Pass |\n"
            report += "|-------|-------|-----------|------|\n"
            for check_name, check_data in hard_checks.items():
                val = check_data.get("value", "N/A")
                threshold = check_data.get("threshold", "N/A")
                passed = "PASS" if check_data.get("pass") else "FAIL"
                val_str = f"{val:.4f}" if isinstance(val, float) else str(val)
                thr_str = (
                    f"{threshold:.4f}" if isinstance(threshold, float)
                    else str(threshold)
                )
                report += f"| {check_name} | {val_str} | {thr_str} | {passed} |\n"
            report += "\n"

        # Warning checks table
        warning_checks = go_nogo.get("warning_checks", {})
        if warning_checks:
            report += "### Warning Checks (informational, do NOT force NO-GO)\n\n"
            report += "| Check | Value | Threshold | Pass |\n"
            report += "|-------|-------|-----------|------|\n"
            for check_name, check_data in warning_checks.items():
                val = check_data.get("value", "N/A")
                threshold = check_data.get("threshold", "N/A")
                passed = "PASS" if check_data.get("pass") else "WARN"
                val_str = f"{val:.4f}" if isinstance(val, float) else str(val)
                thr_str = (
                    f"{threshold:.4f}" if isinstance(threshold, float)
                    else str(threshold)
                )
                report += f"| {check_name} | {val_str} | {thr_str} | {passed} |\n"
            report += "\n"

        report += "## Robustness Suite Summary\n\n"
        report += f"- Suite: core\n"
        report += f"- Total scenarios run: {len(tester._results)}\n"
        report += f"- Scenario keys: {', '.join(sorted(tester._results.keys()))}\n"
        report += "\n## SKIPPED Tests\n\n"
        report += "- full robustness matrix: skipped by --phase5-suite core\n"

        report_path = Path("outputs/robustness_report.md")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report)

        logger.info(f"Phase 5 core report saved to {report_path}")
        safe_print(report)
        return 0

    # 1. Cost sensitivity
    logger.info("1/7 Running cost sensitivity (1x/2x/3x)...")
    cost_results = tester.test_cost_sensitivity(base_config)

    # 2. Slippage sensitivity
    logger.info("2/7 Running slippage sensitivity (5/10/20bp)...")
    slippage_results = tester.test_slippage_sensitivity(base_config)

    # 3. Rebalance frequency (weekly/monthly only — biweekly not supported)
    logger.info("3/7 Running rebalance frequency (weekly/monthly)...")
    freq_results = tester.test_rebalance_frequency(
        base_config,
        frequencies=[("weekly", "Weekly"), ("monthly", "Monthly")]
    )
    skipped.append("rebalance_freq=biweekly: skipped, not supported by PortfolioBacktester")

    # 4. Portfolio size
    logger.info("4/7 Running portfolio size (Top30/50/100)...")
    size_results = tester.test_portfolio_size(base_config)

    # 5. Stock caps — only feasible combinations
    logger.info("5/7 Running stock cap sensitivity (feasible combos)...")
    cap_configs = [
        (100, 0.01, "Top100_cap1%"),   # 100*0.01 = 1.0 → feasible
        (50, 0.02, "Top50_cap2%"),     # 50*0.02 = 1.0 → feasible
        (50, 0.03, "Top50_cap3%"),     # 50*0.03 = 1.5 → feasible
    ]
    for top_n, cap, label in cap_configs:
        config = deepcopy(base_config)
        config["top_n"] = top_n
        config["weight_max"] = cap
        try:
            result = run_bt(**config)
            result["stock_cap"] = label
            tester._results[f"cap_{label}"] = result
            logger.info(f"  cap_{label}: IR={result.get('information_ratio', 'N/A')}")
        except Exception as e:
            skipped.append(f"cap_{label}: {e}")

    # Skip infeasible: Top50_cap1% (50*0.01=0.5 < 1.0)
    skipped.append("cap_Top50_cap1%: infeasible (50*0.01=0.5 < 1.0, cannot fully invest)")
    # Skip infeasible: Top30_cap1% (30*0.01=0.3 < 1.0)
    skipped.append("cap_Top30_cap1%: infeasible (30*0.01=0.3 < 1.0, cannot fully invest)")

    # 6. Turnover scenarios (buffer, monthly, etc.)
    logger.info("6/8 Running turnover scenarios...")
    try:
        to_results = tester.test_turnover_scenarios(base_config)
        n_to = len(to_results) if hasattr(to_results, '__len__') else 0
        logger.info(f"  Turnover scenarios: {n_to} results")
        for scenario_key in ["to_weekly_baseline", "to_monthly",
                             "to_buffer_top50_80", "to_buffer_top100_150"]:
            if scenario_key in tester._results:
                r = tester._results[scenario_key]
                logger.info(
                    f"  {scenario_key}: IR={r.get('information_ratio', 'N/A')}, "
                    f"turnover={r.get('avg_turnover', 'N/A'):.2%}"
                    if isinstance(r.get('avg_turnover'), (int, float))
                    else f"  {scenario_key}: IR={r.get('information_ratio', 'N/A')}"
                )
    except Exception as e:
        skipped.append(f"turnover_scenarios: {e}")
        logger.warning(f"Turnover scenarios failed: {e}")

    # 7. Market regime segments
    logger.info("7/8 Running market regime segments...")
    regime_results = tester.test_market_regimes(base_config)

    # 8. Industry deviation (only if industry data available)
    if industry_available:
        logger.info("8/8 Running industry deviation tests...")
        try:
            ind_results = tester.test_industry_deviation(base_config)
        except Exception as e:
            skipped.append(f"industry_deviation: {e}")
    else:
        skipped.append("industry_deviation: SKIPPED — industry PIT data not available")
        logger.info("8/8 Industry deviation: SKIPPED (industry PIT data not available)")

    # Go/No-Go assessment
    base_result = tester._results.get(
        "cost_1x", run_bt(**base_config)
    )
    cost_2x_result = tester._results.get("cost_2x")

    # Find recent OOS result (2025+ regime) — Phase 1: OOS enforcement
    recent_oos = None
    for key, result in tester._results.items():
        if "2025" in str(key) or "OOS" in str(key):
            recent_oos = result
            break

    go_nogo = tester.go_nogo_check(base_result, cost_2x_result=cost_2x_result,
                                   recent_oos_result=recent_oos)

    # Phase 1: OOS enforcement — if recent OOS is missing/empty, verdict must
    # be FAIL or WARN (never PASS with 0s)
    if recent_oos is None or recent_oos.get("error") or recent_oos.get("n_periods", 0) < 5:
        go_nogo["verdict"] = "NO-GO (OOS missing or insufficient data)"
        go_nogo["oos_available"] = False
        logger.warning(
            "Go/No-Go: Recent OOS (2025+) is missing or has insufficient data. "
            "Verdict forced to NO-GO. Run Phase 0 with full date range to populate OOS data."
        )
    else:
        go_nogo["oos_available"] = True

    # Phase 0: Write run manifest and metrics summary
    # factor_names is already filtered to enabled factors only
    used_factors = [f for f in factor_names if f in factor_dfs]
    _write_run_manifest(
        args.run_id, args,
        factor_list=used_factors,
        phases_run=["phase5"],
        extra={"go_nogo_verdict": go_nogo.get("verdict", "UNKNOWN")}
    )
    _write_metrics_summary(args.run_id, "phase5_base", base_result)
    if cost_2x_result and not cost_2x_result.get("error"):
        _write_metrics_summary(args.run_id, "phase5_cost_2x", cost_2x_result)
    if recent_oos and not recent_oos.get("error") and recent_oos.get("n_periods", 0) >= 5:
        _write_metrics_summary(args.run_id, "phase5_recent_oos", recent_oos)
    # Save diagnostic artifacts for the full suite
    _write_diagnostic_artifacts(
        args.run_id, "phase5_base", base_result,
        portfolio_values=(base_result.get("_diagnostics_payload", {}).get("portfolio_values")),
    )

    # Generate comprehensive report
    report = tester.generate_report()

    # Append Go/No-Go section
    report += f"\n\n# Go/No-Go Assessment\n\n"
    report += f"**Verdict: {go_nogo['verdict']}** "
    report += f"(Hard: {go_nogo.get('n_hard_pass', 0)}/{go_nogo.get('n_hard_total', 0)} passed"
    if go_nogo.get("n_warning_fail", 0) > 0:
        report += f", Warning fails: {go_nogo['n_warning_fail']}"
    report += ")\n\n"

    # Hard checks
    hard_checks = go_nogo.get("hard_checks", go_nogo.get("checks", {}))
    if hard_checks:
        report += "### Hard Checks (determine GO/NO-GO)\n\n"
        report += "| Check | Value | Threshold | Pass |\n"
        report += "|-------|-------|-----------|------|\n"
        for check_name, check_data in hard_checks.items():
            val = check_data.get("value", "N/A")
            threshold = check_data.get("threshold", "N/A")
            passed = "PASS" if check_data.get("pass") else "FAIL"
            if isinstance(val, float):
                val_str = f"{val:.4f}"
            else:
                val_str = str(val)
            if isinstance(threshold, float):
                thr_str = f"{threshold:.4f}"
            else:
                thr_str = str(threshold)
            report += f"| {check_name} | {val_str} | {thr_str} | {passed} |\n"
        report += "\n"

    # Warning checks
    warning_checks = go_nogo.get("warning_checks", {})
    if warning_checks:
        report += "### Warning Checks (informational, do NOT force NO-GO)\n\n"
        report += "| Check | Value | Threshold | Pass |\n"
        report += "|-------|-------|-----------|------|\n"
        for check_name, check_data in warning_checks.items():
            val = check_data.get("value", "N/A")
            threshold = check_data.get("threshold", "N/A")
            passed = "PASS" if check_data.get("pass") else "WARN"
            if isinstance(val, float):
                val_str = f"{val:.4f}"
            else:
                val_str = str(val)
            if isinstance(threshold, float):
                thr_str = f"{threshold:.4f}"
            else:
                thr_str = str(threshold)
            report += f"| {check_name} | {val_str} | {thr_str} | {passed} |\n"
        report += "\n"

    report += "## Robustness Suite Summary\n\n"
    report += f"- Total scenarios run: {len(tester._results)}\n"
    report += f"- Scenario keys: {', '.join(sorted(tester._results.keys()))}\n"

    # Append SKIPPED items
    if skipped:
        report += "\n## SKIPPED Tests\n\n"
        for item in skipped:
            report += f"- {item}\n"
    else:
        report += "\n## SKIPPED Tests\n\n"
        report += "- None — all test suites ran\n"

    # Key metrics from 2x cost scenario
    if cost_2x_result:
        report += "\n## 2x Cost Survival Check\n\n"
        report += f"- 2x Cost Excess Return: {cost_2x_result.get('annualized_excess_return', 0):.4%}\n"
        report += f"- 2x Cost IR: {cost_2x_result.get('information_ratio', 0):.3f}\n"
        report += f"- 2x Cost Max DD: {cost_2x_result.get('max_drawdown', 0):.2%}\n"

    # Recent OOS decay check
    if recent_oos:
        report += "\n## Recent OOS (2025+) Decay Check\n\n"
        report += f"- OOS Excess Return: {recent_oos.get('annualized_excess_return', 0):.4%}\n"
        report += f"- OOS IR: {recent_oos.get('information_ratio', 0):.3f}\n"
        report += f"- OOS Max DD: {recent_oos.get('max_drawdown', 0):.2%}\n"

    report_path = Path("outputs/robustness_report.md")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)

    logger.info(f"Phase 5 report saved to {report_path}")
    safe_print(report)
    return 0


# ===================================================================
# Phase 5 Diagnostics: Failure Attribution
# ===================================================================
def run_phase5_diagnostics(args):
    """
    Run failure diagnostics on Phase 5 backtest results.

    Performs:
    1. Turnover attribution — entry/exit/within decomposition
    2. Cost attribution — gross/net drag, 2x cost simulation
    3. Fallback attribution — reason classification, unknown rate
    4. Factor stability — annual IC, coverage, 2025+ decay
    """
    logger.info("=" * 60)
    logger.info("Phase 5 Diagnostics: Failure Attribution")
    logger.info("=" * 60)

    # Batch 6: dry-run — verify imports and expected outputs, no real data
    if args.dry_run:
        from validation.diagnostics import Phase5Diagnostics
        logger.info("Phase 5 diagnostics dry-run:")
        logger.info("  - diagnostics module importable: OK")
        logger.info("  - expected outputs:")
        logger.info("    outputs/phase5_failure_diagnostics.md")
        logger.info("    outputs/phase5_failure_diagnostics.json")
        logger.info("    outputs/phase5_fallback_events.csv")
        logger.info("    outputs/phase5_turnover_breakdown.csv")
        return 0

    start_date = args.start or "20160101"
    end_date = args.end or datetime.now().strftime("%Y%m%d")
    oos_start_date = getattr(args, "phase5_oos_start", None) or "20250101"
    oos_end_date = getattr(args, "phase5_oos_end", None) or end_date
    load_start_date = min(start_date, oos_start_date)
    load_end_date = max(end_date, oos_end_date)

    from data.panel_loader import get_loader
    from data.calendar import get_calendar
    from alpha.ic_weighting import ICWeighting
    from validation.diagnostics import Phase5Diagnostics

    loader = get_loader()
    calendar = get_calendar()
    calendar.load(start_date=load_start_date, end_date=load_end_date)

    # Load factors
    factor_names = _select_valid_cs_factors(loader, calendar, start_date, end_date)
    if not factor_names:
        logger.error("No valid processed factors. Run phase1 first.")
        return 1

    strategy_mode = getattr(args, "strategy_mode", "factor_dynamic")

    if strategy_mode == "regime":
        regime_config = _load_regime_config_safe(
            getattr(args, "regime_config", "configs/regime.yaml")
        )
        regime_factor_names = _select_regime_candidate_factors(
            loader, regime_config, load_start_date, load_end_date,
        )
        if not regime_factor_names:
            logger.error("No regime factors in cache — cannot proceed")
            return 1
        factor_names = regime_factor_names
        data_start, _ = _compute_regime_load_window(
            start_date, load_end_date, regime_config, calendar=calendar,
        )
        data_end = load_end_date
        diag_horizon = regime_config.get("sleeve_composite", {}).get("horizon", 5)
    else:
        factor_config = _normalize_factor_config(
            _load_factor_config(_factors_config_path(args))
        )
        enabled_factors = factor_config["enabled_factors"]
        composite_params = factor_config["composite_params"]
        factor_names = _filter_enabled_factors(factor_names, enabled_factors)
        data_start, data_end = load_start_date, load_end_date
        diag_horizon = composite_params.get("horizon", 5)
        if (code := _check_formal_candidate_policy(
            factor_config, _factors_config_path(args)
        )):
            return code

    logger.info(f"Loading {len(factor_names)} factors for diagnostics...")

    factor_dfs = {}
    for name in factor_names:
        df = loader.read_factor(name, data_start, data_end)
        if not df.empty:
            factor_dfs[name] = df

    fwd_rets = loader.read_factor("fwd_returns", data_start, data_end)

    # Generate composite scores for signal dates
    weekly_dates = set(calendar.weekly_rebalance_dates(start_date, end_date))
    all_signal_dates = sorted(weekly_dates)
    signal_dates_int = [int(d) for d in all_signal_dates]

    if strategy_mode == "regime":
        logger.info("Phase 5 diagnostics: Using regime router strategy mode")
        composite, _ = build_regime_composite(
            factor_dfs, fwd_rets, signal_dates_int,
            getattr(args, "regime_config", "configs/regime.yaml"),
            start_date, load_end_date, loader=loader,
            data_start_date=data_start, data_end_date=data_end,
        )
    else:
        icw = ICWeighting(**composite_params, factor_whitelist=enabled_factors)
        composite = icw.compute_composite_series(factor_dfs, fwd_rets, signal_dates_int)

    # Build backtester and run with the base config
    bt = _build_backtester(start_date, end_date, loader=loader)

    # Build mu_df for optimized weighting
    mu_df = None
    try:
        from alpha.score_to_mu import ScoreToMu
        stm = ScoreToMu(method="rolling_ic")
        mu_df = stm.calibrate(composite, "composite_score", fwd_rets,
                              horizon=diag_horizon)
    except Exception as e:
        logger.warning(f"mu calibration skipped: {e}")

    strat_kwargs = _strategy_kwargs_from_args(args)
    base_config = {
        "start_date": start_date,
        "end_date": end_date,
        "top_n": args.top_n or 50,
        "weighting": "optimized",
        "weight_max": args.weight_max or 0.02,
        **strat_kwargs,
    }

    backtest_result = bt.run_backtest(
        scores=composite,
        score_col="composite_score",
        **base_config,
        mu_df=mu_df,
        return_diagnostics=True,
    )

    # Extract raw diagnostics payload from backtest result (Batch 3 fix)
    payload = backtest_result.get("_diagnostics_payload", {})
    opt_diag = payload.get("opt_diagnostics", {})
    if not opt_diag:
        # Fallback: extract from top-level result keys
        opt_diag = {
            "opt_n_total": backtest_result.get("opt_n_total", 0),
            "opt_n_fallback": backtest_result.get("opt_n_fallback", 0),
            "opt_fallback_reasons": backtest_result.get("opt_fallback_reasons", {}),
            "opt_fallback_rate": backtest_result.get("optimizer_fallback_rate", 0.0),
        }

    # Run diagnostics with real per-period data
    diag = Phase5Diagnostics(
        backtest_result=backtest_result,
        opt_diagnostics=opt_diag,
        trades_log=payload.get("trades_log", []),
        holdings_log=payload.get("holdings_log", []),
        portfolio_values=payload.get("portfolio_values", []),
        factor_dfs=factor_dfs,
        fwd_rets=fwd_rets,
        signal_dates=signal_dates_int,
    )
    diag.run_all()

    # Generate outputs
    outputs_dir = Path("outputs")

    # Markdown report
    report = diag.generate_report()
    report_path = outputs_dir / "phase5_failure_diagnostics.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    logger.info(f"Diagnostics report saved to {report_path}")

    # JSON
    diag.to_json(outputs_dir / "phase5_failure_diagnostics.json")

    # Fallback events CSV
    diag.export_fallback_csv(outputs_dir / "phase5_fallback_events.csv")

    # Turnover breakdown CSV
    diag.export_turnover_csv(outputs_dir / "phase5_turnover_breakdown.csv")

    safe_print(report)
    logger.info("Phase 5 diagnostics complete.")

    # Write manifest
    used_factors = [f for f in factor_names if f in factor_dfs]
    _write_run_manifest(
        args.run_id, args,
        factor_list=used_factors,
        phases_run=["phase5-diagnostics"],
    )

    return 0


# ===================================================================
# Phase 5 Experiments: Parameter Grid Search
# ===================================================================
def run_phase5_experiments(args):
    """
    Run Phase 5 experiment grid using YAML configuration.

    Supports parallel evaluation of parameter variations with
    candidate filtering based on turnover, fallback, cost, and IR thresholds.
    """
    logger.info("=" * 60)
    logger.info("Phase 5 Experiments: Grid Search")
    logger.info("=" * 60)

    config_path = args.config or "configs/phase5_experiments.yaml"

    try:
        from validation.experiment_runner import ExperimentRunner
        runner = ExperimentRunner(config_path=config_path, args=args)
        runner.run()
    except ImportError as e:
        logger.error(f"Experiment runner not available: {e}")
        return 1
    except FileNotFoundError as e:
        logger.error(f"Config file not found: {e}")
        return 1
    except Exception as e:
        logger.error(f"Experiment runner failed: {e}", exc_info=True)
        return 1

    return 0



# ===================================================================
# Smoke test: short-interval real-data validation
# ===================================================================
def run_smoke(args):
    """
    Short-interval end-to-end smoke test using REAL data.

    Result states: OK | WARN | DATA_INSUFFICIENT | FAIL
    - OK: all checks pass
    - WARN: minor issues (e.g. no limit data cached yet)
    - DATA_INSUFFICIENT: short window can't support Phase 2 (exit 0)
    - FAIL: real error (exit 1)

    Minimum verified items:
    - Phase 0 writes prices_raw/prices_adj/index_weight/daily_basic
    - Phase 1 generates at least one processed factor
    - fwd_returns has no duplicate ts_code/trade_date
    - Empty universe does not leak full market
    - Tradable mask can check limit data
    """
    import gc as _gc
    import time
    smoke_start = time.monotonic()

    start_date = args.start or "20160101"
    end_date = args.end or "20160131"

    logger.info("=" * 60)
    logger.info(f"SMOKE TEST: {start_date} -> {end_date}")
    logger.info("=" * 60)

    from data.panel_loader import MemoryMonitor, get_loader
    from data.calendar import get_calendar
    monitor = MemoryMonitor(max_memory_gb=8.0, warning_threshold_gb=6.0)
    loader = get_loader()
    calendar = get_calendar()
    calendar.load(start_date=start_date, end_date=end_date)

    checks = {
        "phase0": "PENDING",
        "prices_adj": "PENDING",
        "tradable_limit": "PENDING",
        "phase1": "PENDING",
        "factors": "PENDING",
        "fwd_duplicates": "PENDING",
        "phase2": "PENDING",
    }
    warnings = []
    has_failure = False

    # --- Phase 0 ---
    logger.info("--- Smoke Phase 0: Data Pipeline ---")
    rc0 = run_phase0(args)
    checks["phase0"] = "OK" if rc0 == 0 else "FAIL"
    if rc0 != 0:
        has_failure = True

    # Verify prices_adj
    prices_adj_path = Path("data/parquet/prices_adj")
    n_adj_files = len(list(prices_adj_path.rglob("*.parquet"))) if prices_adj_path.exists() else 0
    checks["prices_adj"] = "OK" if n_adj_files > 0 else "FAIL"
    if n_adj_files == 0:
        has_failure = True
        warnings.append("prices_adj: no files written")

    # Verify tradable mask — check if limit data exists for ANY date
    try:
        from data.tradable import get_tradable
        trade_days = calendar.trade_days_between(int(start_date), int(end_date))
        if len(trade_days) > 0:
            # Simple check: does limit_status cache have ANY data?
            limit_df = loader.query(
                "limit_status",
                columns=["trade_date"],
                start_date=str(trade_days[0]),
                end_date=str(trade_days[-1]),
            )
            if not limit_df.empty:
                checks["tradable_limit"] = "OK"
                logger.info(
                    f"  limit_status: {len(limit_df)} rows, "
                    f"{limit_df['trade_date'].nunique()} dates covered"
                )
            else:
                checks["tradable_limit"] = "DATA_INSUFFICIENT"
                warnings.append(
                    "limit_status: no data in cache for requested range. "
                    "Run Phase 0 to prefetch limit data. "
                    "Without cached stk_limit data, limit_up/down checks "
                    "will be skipped in backtests."
                )
        else:
            checks["tradable_limit"] = "DATA_INSUFFICIENT"
            warnings.append("tradable_mask: no trade days in range")
    except Exception as e:
        checks["tradable_limit"] = "FAIL"
        has_failure = True
        warnings.append(f"tradable check exception: {e}")

    monitor.check("smoke_after_phase0")
    _gc.collect()

    # --- Phase 1 (READ-ONLY: never call run_phase1 in smoke) ---
    # Smoke NEVER computes or recomputes factors.  It only checks whether
    # production cache (built by: python run_research.py phase1 --recompute)
    # already covers the smoke window.
    logger.info("--- Smoke Phase 1: Factor Coverage Check (read-only) ---")
    import glob as _glob2

    def _get_cached_cs_factors_smoke():
        dirs = _glob2.glob("data/parquet/factors/factor_name=*")
        return sorted([
            Path(d).name.replace("factor_name=", "")
            for d in dirs if "_cs" in Path(d).name
        ])

    cs_names = _get_cached_cs_factors_smoke()
    fwd_cov = loader.factor_coverage("fwd_returns", start_date, end_date)

    if not cs_names:
        logger.warning(
            "No _cs factors in cache — smoke cannot verify factor coverage. "
            "Run 'python run_research.py phase1 --start 20160101 "
            "--end 20161231 --recompute' first to build production cache."
        )
        checks["phase1"] = "DATA_INSUFFICIENT"
        checks["factors"] = "DATA_INSUFFICIENT"
        checks["fwd_duplicates"] = "DATA_INSUFFICIENT"
        rc1 = 1  # signal "no factors" for Phase 2 skip
    else:
        # Check each _cs factor coverage within the smoke window.
        # A factor is "usable" if it has any data in the window.
        # read_factor() deduplicates on read, so duplicates in cache
        # are a warning, not a hard block.
        n_ok = 0
        n_dup_warn = 0
        for name in cs_names:
            cov = loader.factor_coverage(name, start_date, end_date)
            if cov["n_dates"] > 0:
                n_ok += 1
                if cov["duplicates"] > 0:
                    n_dup_warn += 1
                    logger.warning(
                        f"  {name}: {cov['duplicates']} duplicate rows detected. "
                        f"This is typically caused by legacy year-level parquet "
                        f"files coexisting with year/month partitions. "
                        f"Run: python scripts/migrate_factor_cache.py"
                    )
            else:
                logger.debug(
                    f"  {name}: no data in smoke window "
                    f"(range={cov.get('min_date')}→{cov.get('max_date')})"
                )

        checks["phase1"] = "OK" if n_ok >= 1 else "DATA_INSUFFICIENT"
        checks["factors"] = "OK" if n_ok >= 1 else "DATA_INSUFFICIENT"
        rc1 = 0 if n_ok >= 1 else 1

        if n_dup_warn > 0:
            warnings.append(
                f"{n_dup_warn}/{len(cs_names)} factors have duplicate rows in cache. "
                f"Run migration script to clean up."
            )

        logger.info(
            f"Factor coverage: {n_ok}/{len(cs_names)} _cs factors have data "
            f"in smoke window {start_date}→{end_date}"
            f"{f' ({n_dup_warn} with duplicates)' if n_dup_warn else ''}"
        )

    # Check fwd_returns
    checks["fwd_duplicates"] = "OK" if fwd_cov["duplicates"] == 0 else "FAIL"
    if fwd_cov["duplicates"] > 0:
        has_failure = True
        warnings.append(f"fwd_returns: {fwd_cov['duplicates']} duplicate rows")
    elif fwd_cov["n_dates"] == 0:
        checks["fwd_duplicates"] = "DATA_INSUFFICIENT"
        warnings.append("fwd_returns: no data in smoke window")

    monitor.check("smoke_after_phase1")
    _gc.collect()

    # --- Phase 2 (read-only — may be DATA_INSUFFICIENT for short windows) ---
    # Smoke MUST pass --no-recompute to prevent auto-rebuild of production cache.
    if rc1 == 0 and len(cs_names) >= 1:
        logger.info("--- Smoke Phase 2: Backtest (read-only) ---")
        saved_no_recompute = args.no_recompute
        args.no_recompute = True
        rc2 = run_phase2(args)
        args.no_recompute = saved_no_recompute
        if rc2 == 0:
            checks["phase2"] = "OK"
        elif rc2 == 1:
            # Determine if this is a real failure or a short-window issue
            fwd_cov2 = loader.factor_coverage("fwd_returns", start_date, end_date)
            n_signal = len(calendar.weekly_rebalance_dates(start_date, end_date))
            # Count trading days in window
            n_trade_days = len(calendar.trade_days_between(
                int(start_date), int(end_date)
            ))

            is_short_window = (
                fwd_cov2["n_dates"] < 16
                or n_signal < 6
                or n_trade_days < 60
            )

            if is_short_window:
                checks["phase2"] = "DATA_INSUFFICIENT"
                warnings.append(
                    f"Phase 2: insufficient data for backtest "
                    f"(fwd_dates={fwd_cov2['n_dates']}, "
                    f"signal_dates={n_signal}, "
                    f"trade_days={n_trade_days}). "
                    f"Windows < 3 months cannot produce valid backtest results. "
                    f"This is expected for smoke — not a code error."
                )
            else:
                checks["phase2"] = "FAIL"
                has_failure = True
                warnings.append(
                    f"Phase 2 failed with sufficient data available "
                    f"(fwd_dates={fwd_cov2['n_dates']}, "
                    f"signal_dates={n_signal}). "
                    f"Check logs for details."
                )
    else:
        checks["phase2"] = "SKIPPED"
        warnings.append("Phase 2 skipped: no factors or fwd_returns in smoke window")

    monitor.check("smoke_after_phase2")

    # --- Summary ---
    elapsed = time.monotonic() - smoke_start
    mem_report = monitor.report()

    logger.info("=" * 60)
    logger.info("SMOKE TEST RESULTS")
    logger.info("=" * 60)
    for key, val in sorted(checks.items()):
        logger.info(f"  {key}: {val}")

    logger.info(f"  elapsed: {elapsed:.1f}s")
    logger.info(f"  peak_memory: {mem_report['peak_gb']:.2f}GB")

    # Determine overall verdict
    has_data_insufficient = any(v == "DATA_INSUFFICIENT" for v in checks.values())
    verdict = "FAIL" if has_failure else ("WARN" if has_data_insufficient else "OK")
    exit_code = 1 if has_failure else 0

    # Print summary to stdout
    factors_path = Path("data/parquet/factors")
    n_cs_val = len(cs_names)  # from the read-only coverage check
    n_factor_files_val = len(list(factors_path.rglob("*.parquet"))) if factors_path.exists() else 0
    print(f"\nSmoke Test: {start_date} -> {end_date}")
    print(f"  Phase 0:            {checks['phase0']}")
    safe_print(f"  Prices adj:         {checks['prices_adj']} ({n_adj_files} files)")
    safe_print(f"  Tradable limit:     {checks['tradable_limit']}")
    print(f"  Phase 1:            {checks['phase1']}")
    safe_print(f"  Factors:            {checks['factors']} ({n_cs_val} cs, {n_factor_files_val} total)")
    safe_print(f"  Fwd dups:           {checks['fwd_duplicates']} ({fwd_cov['duplicates']} dup, {fwd_cov['n_dates']} dates)")
    print(f"  Phase 2:            {checks['phase2']}")
    safe_print(f"  Peak memory:        {mem_report['peak_gb']:.2f}GB")
    safe_print(f"  Elapsed:            {elapsed:.1f}s")
    safe_print(f"  Verdict:            {verdict}")
    if warnings:
        safe_print(f"  Notes ({len(warnings)}):")
        for w in warnings:
            safe_print(f"    - {w}")

    return exit_code


# ===================================================================
# Validate: full end-to-end pipeline verification
# ===================================================================
def run_validate(args):
    """
    Full pipeline validation.

    Runs: check_env, cache audit, Phase 0-2 full, smoke, Phase 3-5 dry-run.
    Generates outputs/validation_report.md.
    """
    import time
    import subprocess
    validate_start = time.monotonic()

    start_date = args.start or "20160101"
    end_date = args.end or "20161231"

    logger.info("=" * 60)
    logger.info(f"VALIDATE: {start_date} -> {end_date}")
    logger.info("=" * 60)

    results = {}
    all_passed = True

    # 1. check_env
    logger.info("--- 1/7: Environment check ---")
    try:
        rc = subprocess.run(
            [sys.executable, "scripts/check_env.py"],
            capture_output=True, text=True, timeout=60,
        )
        results["check_env"] = "OK" if rc.returncode == 0 else "FAIL"
        if rc.returncode != 0:
            logger.warning(f"check_env stderr: {rc.stderr[:500]}")
            all_passed = False
    except Exception as e:
        results["check_env"] = f"FAIL: {e}"
        all_passed = False
    logger.info(f"  check_env: {results['check_env']}")

    # 2. Cache audit
    logger.info("--- 2/7: Cache audit ---")
    try:
        rc = subprocess.run(
            [sys.executable, "scripts/audit_cache.py",
             "--start", start_date, "--end", end_date],
            capture_output=True, text=True, timeout=120,
        )
        results["audit_cache"] = "OK" if rc.returncode == 0 else (
            "WARN" if rc.returncode == 2 else "FAIL"
        )
        if rc.returncode == 1:
            logger.error(f"Cache audit FAILED:\n{rc.stdout[-1000:]}")
            all_passed = False
    except Exception as e:
        results["audit_cache"] = f"FAIL: {e}"
        all_passed = False
    logger.info(f"  audit_cache: {results['audit_cache']}")

    # 3. Phase 0
    logger.info("--- 3/7: Phase 0 ---")
    rc0 = run_phase0(args)
    results["phase0"] = "OK" if rc0 == 0 else "FAIL"
    if rc0 != 0:
        all_passed = False
    logger.info(f"  phase0: {results['phase0']}")

    # 4. Phase 1
    logger.info("--- 4/7: Phase 1 ---")
    rc1 = run_phase1(args)
    results["phase1"] = "OK" if rc1 == 0 else "FAIL"
    if rc1 != 0:
        all_passed = False
    logger.info(f"  phase1: {results['phase1']}")

    # 5. Phase 2
    logger.info("--- 5/7: Phase 2 ---")
    saved_no_recompute = args.no_recompute
    args.no_recompute = True
    rc2 = run_phase2(args)
    args.no_recompute = saved_no_recompute
    results["phase2"] = "OK" if rc2 == 0 else "FAIL"
    if rc2 != 0:
        all_passed = False
    logger.info(f"  phase2: {results['phase2']}")

    # 6. Smoke
    logger.info("--- 6/7: Smoke ---")
    smoke_args = deepcopy(args)
    smoke_args.start = start_date
    smoke_args.end = end_date
    smoke_args.recompute = False
    smoke_args.no_recompute = True
    smoke_args.dry_run = False
    smoke_args.top_n = args.top_n or 50
    smoke_args.frequency = args.frequency or "weekly"
    smoke_args.end_date = end_date
    rc_smoke = run_smoke(smoke_args)
    results["smoke"] = "OK" if rc_smoke == 0 else (
        "WARN" if rc_smoke == 2 else "FAIL"
    )
    if rc_smoke == 1:
        all_passed = False
    logger.info(f"  smoke: {results['smoke']}")

    # 7. Phase 3-5 dry-run
    logger.info("--- 7/7: Phase 3-5 dry-run ---")
    for phase_name, phase_fn in [("phase3", run_phase3), ("phase4", run_phase4),
                                  ("phase5", run_phase5)]:
        dry_args = deepcopy(args)
        dry_args.start = start_date
        dry_args.end = end_date
        dry_args.recompute = False
        dry_args.no_recompute = True
        dry_args.dry_run = True
        dry_args.top_n = args.top_n or 50
        dry_args.frequency = args.frequency or "weekly"
        dry_args.end_date = end_date
        rc = phase_fn(dry_args)
        results[phase_name] = "OK" if rc == 0 else "FAIL"
        if rc != 0:
            all_passed = False
        logger.info(f"  {phase_name}: {results[phase_name]}")

    # Summary
    elapsed = time.monotonic() - validate_start
    logger.info("=" * 60)
    logger.info("VALIDATION RESULTS")
    logger.info("=" * 60)
    for key, val in results.items():
        logger.info(f"  {key}: {val}")
    logger.info(f"  elapsed: {elapsed:.1f}s")

    # Write report
    report_lines = [
        "# Validation Report",
        f"Period: {start_date} -> {end_date}",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"Elapsed: {elapsed:.1f}s",
        "",
        "## Results",
        "| Step | Status |",
        "|------|--------|",
    ]
    for key, val in results.items():
        report_lines.append(f"| {key} | {val} |")
    report_lines.append("")
    report_lines.append(f"**Overall**: {'PASS' if all_passed else 'FAIL'}")

    report = "\n".join(report_lines)
    report_path = Path("outputs/validation_report.md")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)

    safe_print(report)
    logger.info(f"Validation report saved to {report_path}")

    return 0 if all_passed else 1


# ===================================================================
# Main
# ===================================================================
def main():
    parser = argparse.ArgumentParser(
        description="code_v4: CSI 300 Cross-Sectional Multi-Factor Strategy",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument("phase", nargs="?",
                        choices=["phase0", "phase1", "phase2", "phase3",
                                 "phase4", "phase5", "phase5-diagnostics",
                                 "phase5-experiments",
                                 "all", "smoke", "validate"],
                        default="phase0",
                        help="Which phase to run (or 'smoke'/'validate' for E2E)")

    parser.add_argument("--start", type=str, default=None,
                        help="Start date YYYYMMDD (default: 20160101)")
    parser.add_argument("--end", type=str, default=None,
                        help="End date YYYYMMDD (default: today)")
    parser.add_argument("--top-n", type=int, default=50,
                        help="Number of stocks in portfolio (default: 50)")
    parser.add_argument("--frequency", type=str, default="weekly",
                        choices=["weekly", "monthly"],
                        help="Rebalance frequency")
    parser.add_argument("--recompute", action="store_true",
                        help="Recompute all factors (skip cache)")
    parser.add_argument("--no-recompute", action="store_true",
                        help="Never auto-trigger Phase 1 rebuild; "
                             "return error if coverage insufficient")
    parser.add_argument("--dry-run", action="store_true",
                        help="Dry run without data fetch")
    parser.add_argument("--weight-max", type=float, default=None,
                        help="Max single stock weight (e.g. 0.02 for 2%%)")
    parser.add_argument("--turnover-max", type=float, default=None,
                        help="Max one-way turnover per rebalance (e.g. 0.30)")
    parser.add_argument("--turnover-penalty", type=float, default=None,
                        help="Turnover penalty gamma in optimizer objective")
    parser.add_argument("--phase5-suite", type=str, default="full",
                        choices=["core", "full"],
                        help="Phase 5 suite to run: core Go/No-Go or full matrix")
    parser.add_argument("--phase5-oos-start", type=str, default=None,
                        help="Phase 5 core recent OOS start date YYYYMMDD")
    parser.add_argument("--phase5-oos-end", type=str, default=None,
                        help="Phase 5 core recent OOS end date YYYYMMDD")
    parser.add_argument("--entry-rank", type=int, default=None,
                        help="Buffer: stocks must be in top N to enter")
    parser.add_argument("--exit-rank", type=int, default=None,
                        help="Buffer: stocks below rank N are forced to exit")
    parser.add_argument("--diagnostics", action="store_true",
                        help="Run failure diagnostics alongside Phase 5")
    parser.add_argument("--config", type=str, default=None,
                        help="Path to YAML config file for experiments")
    parser.add_argument("--factors-config", type=str, default="configs/factors.yaml",
                        help="Path to factor YAML config (for A/B testing different "
                             "factor sets without overwriting the default config)")
    # Batch 2: New strategy parameters for CLI
    parser.add_argument("--no-trade-band", type=float, default=0.0,
                        help="Minimum weight change to trigger trade")
    parser.add_argument("--max-weight-change", type=float, default=None,
                        help="Maximum individual stock weight change per rebalance")
    parser.add_argument("--score-smoothing-halflife", type=int, default=None,
                        help="Halflife for score smoothing (periods)")
    parser.add_argument("--hold-buffer-mode", type=str, default="standard",
                        help="Buffer mode: standard or aggressive")
    parser.add_argument("--cost-aware-lambda", type=float, default=0.0,
                        help="Explicit cost penalty weight in objective")
    parser.add_argument("--estimated-cost-bps", type=float, default=10.0,
                        help="Estimated trading cost in bps for cost-aware term")
    parser.add_argument("--cov-shrinkage", type=str, default="ledoit_wolf",
                        choices=["sample", "ledoit_wolf", "factor_model",
                                 "diagonal_shrink_20", "diagonal_shrink_40"],
                        help="Covariance estimation method")
    parser.add_argument("--constraint-relaxation", type=str,
                        default="none", choices=["none", "tiered"],
                        help="Constraint relaxation strategy")
    parser.add_argument("--strategy-mode", type=str,
                        default="factor_dynamic",
                        choices=["factor_dynamic", "regime"],
                        help="Strategy mode: factor_dynamic (default) or regime")
    parser.add_argument("--regime-config", type=str,
                        default="configs/regime.yaml",
                        help="Path to regime YAML config")

    args = parser.parse_args()

    # Generate run_id and attach to args for unified reporting
    args.run_id = _generate_run_id(args)

    if args.phase == "smoke":
        logger.info("code_v4 starting: phase=smoke")
        return run_smoke(args)

    if args.phase == "validate":
        logger.info("code_v4 starting: phase=validate")
        return run_validate(args)

    logger.info(f"code_v4 starting: phase={args.phase} run_id={args.run_id}")

    phases = {
        "phase0": run_phase0,
        "phase1": run_phase1,
        "phase2": run_phase2,
        "phase3": run_phase3,
        "phase4": run_phase4,
        "phase5": run_phase5,
        "phase5-diagnostics": run_phase5_diagnostics,
        "phase5-experiments": run_phase5_experiments,
    }

    if args.phase == "all":
        for phase_name, phase_fn in phases.items():
            rc = phase_fn(args)
            if rc != 0:
                logger.error(f"{phase_name} failed with code {rc}")
                return rc
        return 0
    else:
        return phases[args.phase](args)


if __name__ == "__main__":
    sys.exit(main())

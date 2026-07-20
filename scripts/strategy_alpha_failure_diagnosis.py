"""Strategy-family alpha failure diagnosis — v2 with strict retention gate, real
sleeve oracle / opportunity cost, construction diagnostic matrix, benchmark
conflict detection, and artifact consistency checks.

Reads existing Phase 2 diagnostics only. Does not rerun strategies.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
VALIDATION_YEARS = list(range(2017, 2025))
YTD_YEAR = 2026
SLEEVES = ["reversal", "momentum", "defensive", "value", "volume_price"]
REGIME_PROB_COLS = [
    "trend_up_prob", "trend_down_prob", "range_bound_prob",
    "high_volatility_prob", "value_rotation_prob",
]
FACTOR_TYPE: dict[str, str] = {
    "reversal_5_cs": "technical", "reversal_20_cs": "technical",
    "rsi_14_cs": "technical", "pv_divergence_20_cs": "technical",
    "momentum_60_cs": "technical", "momentum_120_cs": "technical",
    "macd_12_26_9_cs": "technical", "volatility_20_cs": "technical",
    "volatility_60_cs": "technical", "abnormal_drop_reversal_5_cs": "technical",
    "ep_cs": "fundamental", "bp_cs": "fundamental", "sp_cs": "fundamental",
    "roe_cs": "fundamental", "gross_margin_cs": "fundamental",
    "revenue_growth_cs": "fundamental", "profit_growth_cs": "fundamental",
    "leverage_cs": "fundamental", "log_market_cap_cs": "fundamental",
}
INVESTMENT_GATE: dict[str, float] = {
    "avg_annualized_return": 0.0,
    "avg_annualized_excess_return": 0.02,
    "median_annualized_excess_return": 0.0,
    "positive_excess_years": 5,
    "avg_information_ratio": 0.30,
    "max_single_year_excess_loss": -0.10,
}

# Expected output files for artifact consistency check
EXPECTED_OUTPUTS = [
    "normalized_strategy_metrics.csv",
    "benchmark_calendar_audit.csv",
    "strategy_yearly_returns_common_calendar.csv",
    "strategy_investment_gate.csv",
    "factor_alpha_scorecard_2017_2024.csv",
    "sleeve_alpha_scorecard_2017_2024.csv",
    "construction_loss_bridge.csv",
    "pre_cost_vs_post_cost.csv",
    "rebalance_frequency_diagnostic.csv",
    "topn_capacity_diagnostic.csv",
    "regime_router_scorecard.csv",
    "router_opportunity_cost.csv",
    "sleeve_hindsight_oracle.csv",
    "overlay_predictiveness.csv",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _resolve_path(path: str | Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


def _pct(value: Any, digits: int = 1) -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return ""
    return f"{float(value) * 100:.{digits}f}%"


def _num(value: Any, digits: int = 3) -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return ""
    return f"{float(value):.{digits}f}"


def _compound(series: pd.Series) -> float:
    values = series.dropna()
    if values.empty:
        return float("nan")
    return float((1.0 + values).prod() - 1.0)


def _annualize_from_period_returns(period_returns: pd.Series, periods_per_year: int = 52) -> float:
    values = period_returns.dropna()
    if values.empty:
        return float("nan")
    total = _compound(values)
    if total <= -1.0:
        return float("nan")
    return float((1.0 + total) ** (periods_per_year / len(values)) - 1.0)


def _sharpe_from_period_returns(period_returns: pd.Series, periods_per_year: int = 52) -> float:
    values = period_returns.dropna()
    if values.empty or values.std() == 0:
        return float("nan")
    return float(values.mean() / values.std() * np.sqrt(periods_per_year))


def _max_drawdown(period_returns: pd.Series) -> float:
    values = period_returns.dropna()
    if values.empty:
        return float("nan")
    cum = (1.0 + values).cumprod()
    running_max = cum.cummax()
    drawdown = (cum - running_max) / running_max
    return float(drawdown.min())


def _ir_from_excess(period_returns: pd.Series, benchmark_returns: pd.Series) -> float:
    valid = pd.DataFrame({"strat": period_returns, "bm": benchmark_returns}).dropna()
    if valid.empty or len(valid) < 5:
        return float("nan")
    excess = valid["strat"] - valid["bm"]
    if excess.std() == 0:
        return float("nan")
    return float(excess.mean() / excess.std() * np.sqrt(52))


def _idxmax_label(series: pd.Series) -> str:
    valid = series.dropna()
    return str(valid.idxmax()) if not valid.empty else ""


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _read_parquet_safe(path: Path) -> pd.DataFrame:
    return pd.read_parquet(path) if path.exists() else pd.DataFrame()


def _read_csv_safe(path: Path) -> pd.DataFrame:
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
def _load_runs(path: Path) -> pd.DataFrame:
    runs = pd.read_csv(path)
    required = {
        "year", "sample", "start", "end", "strategy", "run_dir",
        "annualized_return", "annualized_excess_return",
        "benchmark_annualized_return", "information_ratio",
        "max_drawdown", "avg_turnover", "total_cost_bps",
        "n_periods", "go_nogo_overall",
    }
    missing = required - set(runs.columns)
    if missing:
        raise ValueError(f"{path} missing required columns: {sorted(missing)}")
    return runs.copy()


def _load_period_data(row: pd.Series) -> dict[str, Any]:
    diag = _resolve_path(row["run_dir"]) / "diagnostics"
    result: dict[str, Any] = {
        "year": int(row["year"]), "sample": str(row["sample"]),
        "strategy": str(row["strategy"]),
        "start": str(row["start"]), "end": str(row["end"]),
    }
    result["period_returns"] = _read_parquet_safe(diag / "phase2_portfolio_values.parquet")
    result["benchmark_returns"] = _read_csv_safe(diag / "phase2_benchmark_period_returns.csv")
    result["manifest"] = _read_json(_resolve_path(row["run_dir"]) / "run_manifest.json")
    metrics_raw = _read_json(_resolve_path(row["run_dir"]) / "metrics_summary.json")
    result["metrics"] = metrics_raw.get("phase2", {})
    result["regime_probs"] = _read_parquet_safe(diag / "phase2_regime_probs.parquet")
    result["sleeve_weights"] = _read_parquet_safe(diag / "phase2_sleeve_weights.parquet")
    result["sleeve_base_weights"] = _read_parquet_safe(diag / "phase2_sleeve_base_weights.parquet")
    result["sleeve_overlay_multipliers"] = _read_parquet_safe(diag / "phase2_sleeve_overlay_multipliers.parquet")
    result["sleeve_overlay_metrics"] = _read_parquet_safe(diag / "phase2_sleeve_overlay_metrics.parquet")
    return result


def _load_all_periods(runs: pd.DataFrame) -> dict[tuple, dict[str, Any]]:
    data: dict[tuple, dict[str, Any]] = {}
    for _, row in runs.iterrows():
        key = (int(row["year"]), str(row["strategy"]))
        data[key] = _load_period_data(row)
    return data


# ---------------------------------------------------------------------------
# 1. Common-calendar evaluation (with benchmark conflict detection)
# ---------------------------------------------------------------------------
def _common_calendar_evaluation(
    runs: pd.DataFrame,
    period_data: dict[tuple, dict[str, Any]],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    norm_rows: list[dict[str, Any]] = []
    audit_rows: list[dict[str, Any]] = []

    for year in sorted(runs["year"].unique()):
        year_runs = runs[runs["year"] == year]
        strategies_in_year = list(year_runs["strategy"].unique())

        # Collect period_ends and benchmark returns per strategy
        period_ends_by_strat: dict[str, set] = {}
        bm_by_period_by_strat: dict[str, dict[int, float]] = {}
        for _, row in year_runs.iterrows():
            strat = str(row["strategy"])
            key = (int(year), strat)
            pd_data = period_data.get(key, {})
            pv = pd_data.get("period_returns", pd.DataFrame())
            if not pv.empty and "period_end" in pv.columns:
                period_ends_by_strat[strat] = set(int(pe) for pe in pv["period_end"].dropna())
            else:
                period_ends_by_strat[strat] = set()

            bm = pd_data.get("benchmark_returns", pd.DataFrame())
            bm_map: dict[int, float] = {}
            if not bm.empty and "period_end" in bm.columns and "benchmark_return" in bm.columns:
                for _, br in bm.iterrows():
                    pe = int(br["period_end"])
                    bm_map[pe] = float(br["benchmark_return"])
            bm_by_period_by_strat[strat] = bm_map

        common_ends = sorted(set.intersection(*period_ends_by_strat.values())) if period_ends_by_strat else []

        # Benchmark annualized comparison
        benchmarks = {}
        for _, row in year_runs.iterrows():
            strat = str(row["strategy"])
            bm_ann = row.get("benchmark_annualized_return", float("nan"))
            benchmarks[strat] = float(bm_ann) if not pd.isna(bm_ann) else float("nan")
        bm_values = [v for v in benchmarks.values() if not np.isnan(v)]
        bm_spread = (max(bm_values) - min(bm_values)) if len(bm_values) >= 2 else float("nan")
        benchmark_mismatch = (bm_spread > 0.005) if not np.isnan(bm_spread) else False

        # NEW: Detect BENCHMARK_RETURN_CONFLICT (same period_end, different benchmark return)
        benchmark_conflict = False
        max_bm_conflict_bps = 0.0
        if len(strategies_in_year) >= 2 and common_ends:
            for pe in common_ends:
                pe_returns = {}
                for strat in strategies_in_year:
                    bm_map = bm_by_period_by_strat.get(strat, {})
                    if pe in bm_map:
                        pe_returns[strat] = bm_map[pe]
                if len(pe_returns) >= 2:
                    pe_spread = max(pe_returns.values()) - min(pe_returns.values())
                    if pe_spread > 0.0001:  # > 1bp difference
                        benchmark_conflict = True
                        max_bm_conflict_bps = max(max_bm_conflict_bps, pe_spread * 10000)

        # Determine calendar status
        if benchmark_conflict:
            calendar_status = "BENCHMARK_RETURN_CONFLICT"
        elif benchmark_mismatch:
            calendar_status = "BENCHMARK_CALENDAR_MISMATCH"
        else:
            calendar_status = "OK"

        audit_rows.append({
            "year": int(year),
            "sample": str(year_runs.iloc[0]["sample"]),
            "n_strategies": len(strategies_in_year),
            "benchmark_spread_bps": round(bm_spread * 10000, 1) if not np.isnan(bm_spread) else np.nan,
            "benchmark_calendar_mismatch": benchmark_mismatch,
            "benchmark_return_conflict": benchmark_conflict,
            "max_benchmark_return_conflict_bps": round(max_bm_conflict_bps, 1),
            "calendar_status": calendar_status,
            "n_common_periods": len(common_ends),
            "strategies": ", ".join(sorted(strategies_in_year)),
            "benchmark_values": json.dumps({k: round(v, 6) for k, v in benchmarks.items()}),
        })

        # Determine a single benchmark series for common calendar
        # Use the first strategy's benchmark as the reference
        canonical_bm_series: dict[int, float] = {}
        if common_ends:
            ref_strat = strategies_in_year[0]
            canonical_bm_series = {
                pe: bm_by_period_by_strat.get(ref_strat, {}).get(pe, float("nan"))
                for pe in common_ends
            }

        # Recompute on common calendar
        for _, row in year_runs.iterrows():
            strat = str(row["strategy"])
            key = (int(year), strat)
            pd_data = period_data.get(key, {})
            pv = pd_data.get("period_returns", pd.DataFrame())

            if pv.empty or not common_ends:
                norm_rows.append({
                    "year": int(year), "sample": str(row["sample"]), "strategy": strat,
                    "n_common_periods": len(common_ends),
                    "annualized_return_common": float("nan"),
                    "annualized_excess_common": float("nan"),
                    "information_ratio_common": float("nan"),
                    "sharpe_ratio_common": float("nan"),
                    "max_drawdown_common": float("nan"),
                    "benchmark_return_common": float("nan"),
                    "benchmark_conflict_detected": benchmark_conflict,
                    "excess_metric_reliable": not benchmark_conflict,
                    "original_annualized_return": row.get("annualized_return", float("nan")),
                    "original_annualized_excess": row.get("annualized_excess_return", float("nan")),
                })
                continue

            pv_common = pv[pv["period_end"].astype(int).isin(common_ends)].sort_values("period_end")
            if pv_common.empty:
                norm_rows.append({
                    "year": int(year), "sample": str(row["sample"]), "strategy": strat,
                    "n_common_periods": len(common_ends),
                    "annualized_return_common": float("nan"),
                    "annualized_excess_common": float("nan"),
                    "information_ratio_common": float("nan"),
                    "sharpe_ratio_common": float("nan"),
                    "max_drawdown_common": float("nan"),
                    "benchmark_return_common": float("nan"),
                    "benchmark_conflict_detected": benchmark_conflict,
                    "excess_metric_reliable": not benchmark_conflict,
                    "original_annualized_return": row.get("annualized_return", float("nan")),
                    "original_annualized_excess": row.get("annualized_excess_return", float("nan")),
                })
                continue

            strat_period_returns = pv_common["period_return"]
            strat_return_ann = _annualize_from_period_returns(strat_period_returns)
            sharpe = _sharpe_from_period_returns(strat_period_returns)
            max_dd = _max_drawdown(strat_period_returns)

            # Use canonical benchmark
            bm_period_list = [canonical_bm_series.get(pe, float("nan")) for pe in common_ends]
            bm_series = pd.Series(bm_period_list).dropna()
            if len(bm_series) == len(strat_period_returns.dropna()) and len(bm_series) > 0:
                bm_return_ann = _annualize_from_period_returns(bm_series)
                ir_val = _ir_from_excess(strat_period_returns, bm_series)
                excess_ann = strat_return_ann - bm_return_ann
            else:
                bm_return_ann = float("nan")
                ir_val = float("nan")
                excess_ann = float("nan")

            norm_rows.append({
                "year": int(year), "sample": str(row["sample"]), "strategy": strat,
                "n_common_periods": len(common_ends),
                "annualized_return_common": strat_return_ann,
                "annualized_excess_common": excess_ann,
                "information_ratio_common": ir_val,
                "sharpe_ratio_common": sharpe,
                "max_drawdown_common": max_dd,
                "benchmark_return_common": bm_return_ann,
                "benchmark_conflict_detected": benchmark_conflict,
                "excess_metric_reliable": not benchmark_conflict,
                "original_annualized_return": row.get("annualized_return", float("nan")),
                "original_annualized_excess": row.get("annualized_excess_return", float("nan")),
            })

    return pd.DataFrame(norm_rows), pd.DataFrame(audit_rows)


# ---------------------------------------------------------------------------
# 2. Investment gate (with benchmark reliability flag)
# ---------------------------------------------------------------------------
def _compute_investment_gate(
    normalized: pd.DataFrame,
    runs: pd.DataFrame,
    calendar_audit: pd.DataFrame,
) -> pd.DataFrame:
    validation = normalized[
        (normalized["sample"] == "validation")
        & (normalized["year"].isin(VALIDATION_YEARS))
    ].copy()

    # Determine if any validation year has benchmark conflict
    val_audit = calendar_audit[
        (calendar_audit["year"].isin(VALIDATION_YEARS))
    ]
    has_benchmark_conflict = (val_audit["benchmark_return_conflict"] == True).any() if not val_audit.empty else False  # noqa: E712

    rows = []
    for strategy in sorted(validation["strategy"].unique()):
        sv = validation[validation["strategy"] == strategy].copy()
        excess = sv["annualized_excess_common"].dropna()
        returns = sv["annualized_return_common"].dropna()
        irs = sv["information_ratio_common"].dropna()
        dds = sv["max_drawdown_common"].dropna()
        excess_reliable = not (sv["benchmark_conflict_detected"] == True).any()  # noqa: E712

        # Fall back to original if common-calendar unavailable
        if len(excess) < len(sv):
            excess_orig = sv["original_annualized_excess"].dropna()
            if len(excess_orig) > len(excess):
                excess = excess_orig
                orig_run = runs[
                    (runs["strategy"] == strategy)
                    & (runs["year"].isin(VALIDATION_YEARS))
                    & (runs["sample"] == "validation")
                ]
                returns = orig_run["annualized_return"].dropna()
                irs = orig_run["information_ratio"].dropna()
                dds = orig_run["max_drawdown"].dropna()

        if excess.empty:
            rows.append({
                "strategy": strategy,
                "avg_annualized_return": float("nan"),
                "avg_annualized_excess_return": float("nan"),
                "median_annualized_excess_return": float("nan"),
                "positive_excess_years": 0,
                "total_validation_years": len(sv),
                "avg_information_ratio": float("nan"),
                "max_single_year_excess_loss": float("nan"),
                "avg_max_drawdown": float("nan"),
                "benchmark_calendar_status": "BENCHMARK_RETURN_CONFLICT" if has_benchmark_conflict else "OK",
                "excess_metric_reliable": not has_benchmark_conflict,
                "calendar_failure_reasons": "Benchmark return conflict detected" if has_benchmark_conflict else "",
                "investment_status": "NO_GO",
                "failure_reasons": "insufficient data for gate evaluation",
            })
            continue

        avg_ret = float(returns.mean()) if not returns.empty else float("nan")
        avg_excess = float(excess.mean())
        median_excess = float(excess.median())
        pos_years = int((excess > 0).sum())
        avg_ir = float(irs.mean()) if not irs.empty else float("nan")
        max_loss = float(excess.min())
        avg_dd = float(dds.mean()) if not dds.empty else float("nan")
        total_years = len(sv)

        failures = []
        if avg_ret <= INVESTMENT_GATE["avg_annualized_return"] or np.isnan(avg_ret):
            failures.append(f"avg_return={_pct(avg_ret)} <= {_pct(INVESTMENT_GATE['avg_annualized_return'])}")
        if avg_excess < INVESTMENT_GATE["avg_annualized_excess_return"] or np.isnan(avg_excess):
            if excess_reliable:
                failures.append(f"avg_excess={_pct(avg_excess)} < {_pct(INVESTMENT_GATE['avg_annualized_excess_return'])}")
            else:
                failures.append(f"avg_excess={_pct(avg_excess)} < {_pct(INVESTMENT_GATE['avg_annualized_excess_return'])} (UNRELIABLE: benchmark conflict)")
        if median_excess <= INVESTMENT_GATE["median_annualized_excess_return"] or np.isnan(median_excess):
            failures.append(f"median_excess={_pct(median_excess)} <= {_pct(INVESTMENT_GATE['median_annualized_excess_return'])}")
        if pos_years < INVESTMENT_GATE["positive_excess_years"]:
            failures.append(f"pos_years={pos_years}/{total_years} < {INVESTMENT_GATE['positive_excess_years']}/8")
        if avg_ir < INVESTMENT_GATE["avg_information_ratio"] or np.isnan(avg_ir):
            failures.append(f"avg_ir={_num(avg_ir, 2)} < {_num(INVESTMENT_GATE['avg_information_ratio'], 2)}")
        if max_loss < INVESTMENT_GATE["max_single_year_excess_loss"] or np.isnan(max_loss):
            failures.append(f"max_loss={_pct(max_loss)} < {_pct(INVESTMENT_GATE['max_single_year_excess_loss'])}")

        if not failures:
            status = "PRODUCTION_GO"
        elif avg_excess > -0.02 and not np.isnan(avg_excess):
            status = "RESEARCH_ONLY"
        else:
            status = "NO_GO"

        calendar_failures = []
        if has_benchmark_conflict:
            calendar_failures.append("BENCHMARK_RETURN_CONFLICT: cross-strategy excess ranking may be unreliable")

        rows.append({
            "strategy": strategy,
            "avg_annualized_return": avg_ret,
            "avg_annualized_excess_return": avg_excess,
            "median_annualized_excess_return": median_excess,
            "positive_excess_years": pos_years,
            "total_validation_years": total_years,
            "avg_information_ratio": avg_ir,
            "max_single_year_excess_loss": max_loss,
            "avg_max_drawdown": avg_dd,
            "benchmark_calendar_status": "BENCHMARK_RETURN_CONFLICT" if has_benchmark_conflict else "OK",
            "excess_metric_reliable": not has_benchmark_conflict,
            "calendar_failure_reasons": "; ".join(calendar_failures) if calendar_failures else "",
            "investment_status": status,
            "failure_reasons": "; ".join(failures) if failures else "",
        })

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 3. Factor alpha scorecard (STRICT retention gate)
# ---------------------------------------------------------------------------
def _build_factor_scorecard(
    period_data: dict[tuple, dict[str, Any]],
    runs: pd.DataFrame,
) -> pd.DataFrame:
    cross_year_dir = ROOT / "outputs" / "analysis" / "sleeve_weight_cross_year"
    rows = []

    for year in VALIDATION_YEARS:
        year_dir = cross_year_dir / f"year={year}"
        ic_path = year_dir / "factor_realised_ic.csv"
        tb_path = year_dir / "factor_top_bottom_summary.csv"

        ic_df = _read_csv_safe(ic_path)
        tb_df = _read_csv_safe(tb_path)

        if ic_df.empty:
            continue

        for _, ic_row in ic_df.iterrows():
            factor = str(ic_row.get("factor", ""))
            if not factor:
                continue

            row_data: dict[str, Any] = {
                "year": year, "factor": factor,
                "factor_type": FACTOR_TYPE.get(factor, "unknown"),
                "mean_ic": ic_row.get("mean_ic", float("nan")),
                "icir": ic_row.get("icir", float("nan")),
                "hit_rate": ic_row.get("hit_rate", float("nan")),
                "ic_dates": ic_row.get("ic_dates", np.nan),
            }

            # Top-bottom data from factor_top_bottom_summary.csv
            if not tb_df.empty:
                tb_factor = tb_df[tb_df["factor"] == factor]
                if not tb_factor.empty:
                    row = tb_factor.iloc[0]
                    row_data["top_bottom_excess"] = row.get("top_minus_bottom_excess", float("nan"))
                    # long_only_top_excess: top excess (top vs benchmark or top return)
                    row_data["long_only_top_excess"] = row.get("top_excess", float("nan"))
                    row_data["decile_monotonicity"] = row.get("decile_monotonicity", float("nan"))

            rows.append(row_data)

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)

    # Aggregate across years with strict retention gate
    agg_rows = []
    for factor in sorted(df["factor"].unique()):
        fdf = df[df["factor"] == factor].sort_values("year")
        n_years = len(fdf)

        # IC stats
        mean_ic = float(fdf["mean_ic"].mean()) if "mean_ic" in fdf else float("nan")
        ic_std = float(fdf["mean_ic"].std()) if "mean_ic" in fdf else float("nan")
        icir_agg = mean_ic / ic_std if ic_std and ic_std > 0 else float("nan")
        hit_rate_agg = float(fdf["hit_rate"].mean()) if "hit_rate" in fdf else float("nan")
        positive_ic_years = int((fdf["mean_ic"] > 0).sum()) if "mean_ic" in fdf else 0

        # Consecutive negative years
        signs = (fdf["mean_ic"] > 0).astype(int) if "mean_ic" in fdf else pd.Series()
        max_consecutive_neg = 0
        if len(signs) > 0:
            c = 0
            for s in signs:
                if s == 0:
                    c += 1
                    max_consecutive_neg = max(max_consecutive_neg, c)
                else:
                    c = 0

        # Long-only top excess
        avg_long_only_top = float(fdf["long_only_top_excess"].mean()) if "long_only_top_excess" in fdf.columns else float("nan")
        positive_long_only_years = int((fdf["long_only_top_excess"] > 0).sum()) if "long_only_top_excess" in fdf.columns else 0

        # Top-bottom excess
        avg_top_bottom = float(fdf["top_bottom_excess"].mean()) if "top_bottom_excess" in fdf.columns else float("nan")
        positive_top_bottom_years = int((fdf["top_bottom_excess"] > 0).sum()) if "top_bottom_excess" in fdf.columns else 0

        # Decile monotonicity
        avg_monotonicity = float(fdf["decile_monotonicity"].mean()) if "decile_monotonicity" in fdf.columns else float("nan")
        positive_monotonicity_years = int((fdf["decile_monotonicity"] > 0).sum()) if "decile_monotonicity" in fdf.columns else 0

        # Coverage
        avg_coverage = float(fdf["coverage"].mean()) if "coverage" in fdf.columns else float("nan")
        coverage_ok_years = int((fdf["coverage"] > 0.3).sum()) if "coverage" in fdf.columns else 0

        # STRICT retention gate
        failure_reasons = []
        has_long_only = "long_only_top_excess" in fdf.columns and fdf["long_only_top_excess"].notna().any()
        has_top_bottom = "top_bottom_excess" in fdf.columns and fdf["top_bottom_excess"].notna().any()
        has_monotonicity = "decile_monotonicity" in fdf.columns and fdf["decile_monotonicity"].notna().any()
        has_coverage = "coverage" in fdf.columns and fdf["coverage"].notna().any()

        # Gate 1: long_only_top must be positive and passable
        if not has_long_only:
            failure_reasons.append("missing long_only_top_excess data")
        elif avg_long_only_top <= 0:
            failure_reasons.append(f"avg_long_only_top={_pct(avg_long_only_top)} <= 0")
        elif positive_long_only_years < 5:
            failure_reasons.append(f"positive_long_only_years={positive_long_only_years}/{n_years} < 5")

        # Gate 2: top_bottom must be positive
        if not has_top_bottom:
            failure_reasons.append("missing top_bottom_excess data")
        elif avg_top_bottom <= 0:
            failure_reasons.append(f"avg_top_bottom={_pct(avg_top_bottom)} <= 0")
        elif positive_top_bottom_years < 5:
            failure_reasons.append(f"positive_top_bottom_years={positive_top_bottom_years}/{n_years} < 5")

        # Gate 3: decile monotonicity
        if not has_monotonicity:
            failure_reasons.append("missing decile_monotonicity data")
        elif positive_monotonicity_years < 5:
            failure_reasons.append(f"positive_monotonicity_years={positive_monotonicity_years}/{n_years} < 5")

        # Gate 4: IC
        if np.isnan(mean_ic):
            failure_reasons.append("missing mean_ic")
        elif mean_ic <= 0:
            failure_reasons.append(f"mean_ic={_num(mean_ic, 3)} <= 0")
        elif positive_ic_years < 5:
            failure_reasons.append(f"positive_ic_years={positive_ic_years}/{n_years} < 5")

        # Gate 5: consecutive negative
        if max_consecutive_neg >= 3:
            failure_reasons.append(f"max_consecutive_negative={max_consecutive_neg} >= 3")

        # Gate 6: coverage
        if not has_coverage:
            failure_reasons.append("missing coverage data")
        elif np.isnan(avg_coverage):
            failure_reasons.append("avg_coverage is NaN")

        passes_gate = len(failure_reasons) == 0

        agg_rows.append({
            "factor": factor,
            "factor_type": FACTOR_TYPE.get(factor, "unknown"),
            "n_years": n_years,
            "mean_ic": mean_ic,
            "icir_aggregate": icir_agg,
            "hit_rate_avg": hit_rate_agg,
            "positive_ic_years": positive_ic_years,
            "max_consecutive_negative_years": max_consecutive_neg,
            "avg_long_only_top_excess": avg_long_only_top,
            "positive_long_only_top_years": positive_long_only_years,
            "avg_top_bottom_excess": avg_top_bottom,
            "positive_top_bottom_years": positive_top_bottom_years,
            "avg_decile_monotonicity": avg_monotonicity,
            "positive_monotonicity_years": positive_monotonicity_years,
            "avg_coverage": avg_coverage,
            "coverage_ok_years": coverage_ok_years,
            "passes_retention_gate": passes_gate,
            "retention_failure_reasons": "; ".join(failure_reasons) if failure_reasons else "",
        })

    return pd.DataFrame(agg_rows).sort_values("mean_ic", ascending=False)


# ---------------------------------------------------------------------------
# 4. Sleeve alpha scorecard
# ---------------------------------------------------------------------------
def _build_sleeve_scorecard(
    period_data: dict[tuple, dict[str, Any]],
    runs: pd.DataFrame,
) -> pd.DataFrame:
    rows = []
    cross_year_dir = ROOT / "outputs" / "analysis" / "sleeve_weight_cross_year"
    for year in VALIDATION_YEARS:
        year_dir = cross_year_dir / f"year={year}"
        weight_summary = _read_csv_safe(year_dir / "sleeve_factor_weight_summary.csv")
        if weight_summary.empty:
            continue
        for sleeve in SLEEVES:
            sleeve_data = weight_summary[weight_summary["sleeve"] == sleeve]
            if sleeve_data.empty:
                continue
            row_data: dict[str, Any] = {
                "year": year, "sleeve": sleeve,
                "n_dates": int(sleeve_data["n_dates"].iloc[0]) if "n_dates" in sleeve_data.columns else 0,
                "avg_icir": float(sleeve_data["avg_icir"].mean()) if "avg_icir" in sleeve_data.columns else float("nan"),
                "avg_hit_rate": float(sleeve_data["avg_hit_rate"].mean()) if "avg_hit_rate" in sleeve_data.columns else float("nan"),
                "eligible_rate": float(sleeve_data["eligible_rate"].mean()) if "eligible_rate" in sleeve_data.columns else float("nan"),
                "active_rate": float(sleeve_data["active_rate"].mean()) if "active_rate" in sleeve_data.columns else float("nan"),
                "avg_weight": float(sleeve_data["avg_weight"].mean()) if "avg_weight" in sleeve_data.columns else float("nan"),
            }
            rows.append(row_data)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    agg_rows = []
    for sleeve in sorted(df["sleeve"].unique()):
        sdf = df[df["sleeve"] == sleeve]
        agg_rows.append({
            "sleeve": sleeve, "n_years": len(sdf),
            "avg_icir": float(sdf["avg_icir"].mean()) if "avg_icir" in sdf else float("nan"),
            "avg_hit_rate": float(sdf["avg_hit_rate"].mean()) if "avg_hit_rate" in sdf else float("nan"),
            "avg_weight": float(sdf["avg_weight"].mean()) if "avg_weight" in sdf else float("nan"),
            "positive_icir_years": int((sdf["avg_icir"] > 0).sum()) if "avg_icir" in sdf else 0,
        })
    return pd.DataFrame(agg_rows).sort_values("avg_icir", ascending=False)


# ---------------------------------------------------------------------------
# 5. Construction loss bridge (expanded)
# ---------------------------------------------------------------------------
def _build_construction_diagnostics(
    period_data: dict[tuple, dict[str, Any]],
    runs: pd.DataFrame,
    out_dir: Path,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Build construction loss bridge and related diagnostics."""
    bridge_rows = []
    pre_post_rows = []

    for (year, strat), data in period_data.items():
        if year not in VALIDATION_YEARS:
            continue
        pv = data.get("period_returns", pd.DataFrame())
        if pv.empty:
            continue

        run_row = runs[(runs["year"] == year) & (runs["strategy"] == strat)]
        sample = str(run_row.iloc[0]["sample"]) if not run_row.empty else "unknown"

        has_gross = "gross_period_return" in pv.columns
        gross_col = "gross_period_return" if has_gross else "period_return"
        net_col = "period_return"

        gross_returns = pv[gross_col].dropna()
        net_returns = pv[net_col].dropna()
        turnover = pv["turnover"].dropna() if "turnover" in pv.columns else pd.Series(dtype=float)
        cost_bps = pv["cost_bps"].dropna() if "cost_bps" in pv.columns else pd.Series(dtype=float)

        gross_ann = _annualize_from_period_returns(gross_returns) if len(gross_returns) > 0 else float("nan")
        net_ann = _annualize_from_period_returns(net_returns) if len(net_returns) > 0 else float("nan")
        cost_drag = gross_ann - net_ann if not np.isnan(gross_ann) and not np.isnan(net_ann) else float("nan")
        avg_turnover = float(turnover.mean()) if len(turnover) > 0 else float("nan")
        avg_cost_bps = float(cost_bps.mean()) if len(cost_bps) > 0 else float("nan")

        bm = data.get("benchmark_returns", pd.DataFrame())
        if not bm.empty and "benchmark_return" in bm.columns:
            bm_ret = _annualize_from_period_returns(bm["benchmark_return"].dropna())
        else:
            bm_ret = float("nan")

        gross_excess = gross_ann - bm_ret if not np.isnan(gross_ann) and not np.isnan(bm_ret) else float("nan")
        net_excess = net_ann - bm_ret if not np.isnan(net_ann) and not np.isnan(bm_ret) else float("nan")

        bridge_rows.append({
            "year": int(year), "sample": sample, "strategy": str(strat),
            "gross_annualized_return": gross_ann, "net_annualized_return": net_ann,
            "benchmark_annualized": bm_ret, "gross_excess_return": gross_excess,
            "net_excess_return": net_excess, "cost_drag": cost_drag,
            "avg_turnover": avg_turnover, "avg_cost_bps": avg_cost_bps,
            "n_periods": len(net_returns),
        })

        # Pre/post cost detail
        pre_post_rows.append({
            "year": int(year), "sample": sample, "strategy": str(strat),
            "pre_cost_annualized": gross_ann, "post_cost_annualized": net_ann,
            "cost_drag_annualized": cost_drag, "avg_turnover": avg_turnover,
            "avg_cost_bps": avg_cost_bps, "benchmark_annualized": bm_ret,
            "pre_cost_excess": gross_excess, "post_cost_excess": net_excess,
            "data_source": "phase2_portfolio_values.parquet (gross_period_return)" if has_gross else "phase2_portfolio_values.parquet (net only, gross=net)",
        })

    bridge = pd.DataFrame(bridge_rows).sort_values(["year", "strategy"])
    pre_post = pd.DataFrame(pre_post_rows).sort_values(["year", "strategy"])

    # Stub: rebalance frequency diagnostic (NOT_AVAILABLE — no multi-frequency runs exist)
    rebalance_freq = pd.DataFrame([{
        "diagnostic": "rebalance_frequency",
        "status": "NOT_AVAILABLE",
        "reason": "No multi-frequency (weekly/biweekly/monthly) parallel runs exist. Requires dedicated parameter sweep.",
    }])

    # Stub: topn capacity diagnostic
    topn_cap = pd.DataFrame([{
        "diagnostic": "topn_capacity",
        "status": "NOT_AVAILABLE",
        "reason": "No multi-topN (top50/top100) parallel runs exist. Requires dedicated parameter sweep.",
    }])

    return bridge, pre_post, rebalance_freq, topn_cap


# ---------------------------------------------------------------------------
# 6. Regime router scorecard
# ---------------------------------------------------------------------------
def _build_regime_router_scorecard(
    period_data: dict[tuple, dict[str, Any]],
    runs: pd.DataFrame,
) -> pd.DataFrame:
    router_rows = []
    for (year, strat), data in period_data.items():
        if year not in VALIDATION_YEARS and year != YTD_YEAR:
            continue
        regime_probs = data.get("regime_probs", pd.DataFrame())
        sleeve_weights = data.get("sleeve_weights", pd.DataFrame())
        base_weights = data.get("sleeve_base_weights", pd.DataFrame())
        overlay_mult = data.get("sleeve_overlay_multipliers", pd.DataFrame())
        if regime_probs.empty and sleeve_weights.empty:
            continue

        run_row = runs[(runs["year"] == year) & (runs["strategy"] == strat)]
        sample = str(run_row.iloc[0]["sample"]) if not run_row.empty else "unknown"
        row_data: dict[str, Any] = {"year": int(year), "sample": sample, "strategy": str(strat)}

        for col in REGIME_PROB_COLS:
            row_data[col] = float(regime_probs[col].mean()) if col in regime_probs.columns and not regime_probs.empty else float("nan")
        if regime_probs is not None and not regime_probs.empty:
            prob_means = {c: row_data.get(c, np.nan) for c in REGIME_PROB_COLS if c in regime_probs.columns}
            row_data["dominant_regime"] = _idxmax_label(pd.Series(prob_means))
        else:
            row_data["dominant_regime"] = ""

        for sleeve in SLEEVES:
            w_col = f"{sleeve}_weight"
            if w_col in sleeve_weights.columns and not sleeve_weights.empty:
                row_data[f"{sleeve}_actual_weight"] = float(sleeve_weights[w_col].mean())
            else:
                row_data[f"{sleeve}_actual_weight"] = float("nan")
            if w_col in base_weights.columns and not base_weights.empty:
                row_data[f"{sleeve}_base_weight"] = float(base_weights[w_col].mean())
            else:
                row_data[f"{sleeve}_base_weight"] = float("nan")
            actual = row_data.get(f"{sleeve}_actual_weight", np.nan)
            base_w = row_data.get(f"{sleeve}_base_weight", np.nan)
            row_data[f"{sleeve}_overlay_delta"] = actual - base_w if not np.isnan(actual) and not np.isnan(base_w) else float("nan")

        for sleeve in SLEEVES:
            m_col = f"{sleeve}_multiplier"
            row_data[f"{sleeve}_avg_multiplier"] = float(overlay_mult[m_col].mean()) if m_col in overlay_mult.columns and not overlay_mult.empty else float("nan")

        wt_cols = {f"{s}_actual_weight": row_data.get(f"{s}_actual_weight", np.nan) for s in SLEEVES}
        row_data["dominant_sleeve"] = _idxmax_label(pd.Series(wt_cols))
        row_data["router_active"] = not overlay_mult.empty
        router_rows.append(row_data)

    return pd.DataFrame(router_rows).sort_values(["year", "strategy"])


# ---------------------------------------------------------------------------
# 7. Real sleeve oracle & opportunity cost
# ---------------------------------------------------------------------------
def _build_router_opportunity_cost(
    period_data: dict[tuple, dict[str, Any]],
    runs: pd.DataFrame,
    out_dir: Path,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Compute real sleeve oracle using sleeve scores + fwd_ret_5d.

    Returns:
        opportunity_cost, hindsight_oracle, overlay_predictiveness
    """
    cross_year_dir = ROOT / "outputs" / "analysis" / "sleeve_weight_cross_year"
    opp_rows = []
    oracle_rows = []
    predictiveness_rows = []

    for (year, strat), data in period_data.items():
        if year not in VALIDATION_YEARS:
            continue

        sw = data.get("sleeve_weights", pd.DataFrame())
        if sw.empty:
            continue

        # Check if sleeve score data and fwd_returns are available
        year_dir = cross_year_dir / f"year={year}"
        fwd_path = year_dir / "fwd_returns.parquet"
        if not fwd_path.exists():
            # Mark as insufficient
            opp_rows.append({
                "year": int(year), "strategy": str(strat),
                "signal_date": 0, "period_end": 0,
                "status": "INSUFFICIENT_SLEEVE_RETURN_DATA",
                "dominant_sleeve": "", "dominant_sleeve_return": float("nan"),
                "oracle_best_sleeve": "", "oracle_best_sleeve_return": float("nan"),
                "opportunity_cost_vs_oracle": float("nan"),
                "opportunity_cost_vs_equal": float("nan"),
                "actual_weighted_return": float("nan"),
                "equal_weighted_return": float("nan"),
                "dominant_is_oracle": False,
                "regime_label": "",
            })
            continue

        # Load fwd_returns
        try:
            fwd = pd.read_parquet(fwd_path)
            fwd_needed = fwd[["ts_code", "trade_date", "fwd_ret_5d"]].dropna()
            fwd_needed["trade_date"] = fwd_needed["trade_date"].astype(int)
            fwd_needed["ts_code"] = fwd_needed["ts_code"].astype(str)
        except Exception:
            opp_rows.append({
                "year": int(year), "strategy": str(strat),
                "signal_date": 0, "period_end": 0,
                "status": "INSUFFICIENT_SLEEVE_RETURN_DATA",
            })
            continue

        # Load sleeve scores for each sleeve
        sleeve_scores: dict[str, pd.DataFrame] = {}
        all_available = True
        for sleeve in SLEEVES:
            score_path = year_dir / "sleeve_scores" / f"{sleeve}.parquet"
            if score_path.exists():
                try:
                    ss = pd.read_parquet(score_path)
                    ss["trade_date"] = ss["trade_date"].astype(int)
                    ss["ts_code"] = ss["ts_code"].astype(str)
                    sleeve_scores[sleeve] = ss
                except Exception:
                    all_available = False
                    break
            else:
                all_available = False
                break

        if not all_available or not sleeve_scores:
            opp_rows.append({
                "year": int(year), "strategy": str(strat),
                "signal_date": 0, "period_end": 0,
                "status": "INSUFFICIENT_SLEEVE_RETURN_DATA",
            })
            continue

        # Determine date column (real data uses 'trade_date', may also be 'signal_date')
        sw_date_col = "trade_date" if "trade_date" in sw.columns else "signal_date"

        # Build signal_date -> period_end map from portfolio values
        pe_map: dict[int, int] = {}
        pv = data.get("period_returns", pd.DataFrame())
        if not pv.empty and "signal_date" in pv.columns and "period_end" in pv.columns:
            for _, pv_row in pv.iterrows():
                sd = int(pv_row["signal_date"])
                pe = int(pv_row["period_end"])
                pe_map[sd] = pe

        # Build set of valid phase2 period_ends for the backtest window
        valid_period_ends: set[int] = set(pe_map.values())

        # For each signal_date (period) in sleeve_weights, compute sleeve returns
        for _, srow in sw.iterrows():
            signal_date = int(srow[sw_date_col]) if sw_date_col in sw.columns and not pd.isna(srow[sw_date_col]) else 0

            # --- Status classification ---------------------------------------
            if signal_date == 0:
                opp_rows.append({
                    "year": int(year), "strategy": str(strat),
                    "signal_date": 0, "period_end": 0,
                    "status": "INVALID_SIGNAL_DATE",
                    "status_reason": "signal_date is 0 or missing in sleeve_weights",
                })
                continue

            period_end_raw = pe_map.get(signal_date)
            if period_end_raw is None or int(period_end_raw) == 0:
                opp_rows.append({
                    "year": int(year), "strategy": str(strat),
                    "signal_date": signal_date,
                    "period_end": int(period_end_raw) if period_end_raw is not None else 0,
                    "status": "OUT_OF_BACKTEST_WINDOW",
                    "status_reason": f"signal_date {signal_date} not in phase2 portfolio period_end map (warmup or out-of-window)",
                })
                continue

            period_end = int(period_end_raw)
            # -----------------------------------------------------------------

            # Get regime label if available
            regime_label = ""
            rp = data.get("regime_probs", pd.DataFrame())
            rp_date_col = "trade_date" if "trade_date" in rp.columns else "signal_date"
            if not rp.empty and rp_date_col in rp.columns:
                rp_row = rp[rp[rp_date_col] == signal_date]
                if not rp_row.empty:
                    regime_probs_row = {c: rp_row.iloc[0][c] for c in REGIME_PROB_COLS if c in rp_row.columns}
                    regime_label = _idxmax_label(pd.Series(regime_probs_row))

            # Actual sleeve weights
            actual_weights = {}
            for sleeve in SLEEVES:
                w_col = f"{sleeve}_weight"
                if w_col in sw.columns:
                    actual_weights[sleeve] = float(srow[w_col]) if not pd.isna(srow[w_col]) else 0.0
            dominant = max(actual_weights, key=actual_weights.get) if actual_weights else ""

            # Compute per-sleeve Top-50 return using fwd_ret_5d
            sleeve_returns: dict[str, float] = {}
            for sleeve in SLEEVES:
                ss = sleeve_scores.get(sleeve)
                if ss is None or ss.empty:
                    continue
                ss_date = ss[ss["trade_date"] == signal_date]
                if ss_date.empty:
                    continue
                # Top-50 by composite_score
                top50 = ss_date.nlargest(50, "composite_score")
                top50_codes = top50["ts_code"].tolist()
                # Get fwd_ret_5d for these stocks at this date
                fwd_date = fwd_needed[fwd_needed["trade_date"] == signal_date]
                fwd_top = fwd_date[fwd_date["ts_code"].isin(top50_codes)]
                if not fwd_top.empty and len(fwd_top) >= 10:
                    sleeve_returns[sleeve] = float(fwd_top["fwd_ret_5d"].mean())

            if not sleeve_returns:
                continue

            # Actual weighted return
            actual_wtd_return = sum(
                actual_weights.get(s, 0) * sleeve_returns.get(s, 0)
                for s in SLEEVES
            )

            # Oracle: best sleeve
            oracle_sleeve = max(sleeve_returns, key=sleeve_returns.get)
            oracle_return = sleeve_returns[oracle_sleeve]

            # Equal weight return
            equal_return = float(np.mean(list(sleeve_returns.values())))

            # Dominant sleeve return
            dominant_return = sleeve_returns.get(dominant, float("nan"))

            # Opportunity costs
            opp_vs_oracle = oracle_return - actual_wtd_return
            opp_vs_equal = equal_return - actual_wtd_return

            opp_rows.append({
                "year": int(year), "strategy": str(strat),
                "signal_date": signal_date, "period_end": period_end,
                "dominant_sleeve": dominant, "dominant_sleeve_return": dominant_return,
                "oracle_best_sleeve": oracle_sleeve, "oracle_best_sleeve_return": oracle_return,
                "actual_weighted_sleeve_return": actual_wtd_return,
                "equal_sleeve_return": equal_return,
                "opportunity_cost_vs_oracle": opp_vs_oracle,
                "opportunity_cost_vs_equal": opp_vs_equal,
                "dominant_is_oracle": dominant == oracle_sleeve,
                "regime_label": regime_label,
                "status": "OK",
                "status_reason": "",
            })

            # Hindsight oracle row (OK only — no warmup pollution)
            oracle_rows.append({
                "year": int(year), "strategy": str(strat),
                "signal_date": signal_date, "period_end": period_end,
                "oracle_best_sleeve": oracle_sleeve,
                "oracle_best_sleeve_return": oracle_return,
                "equal_sleeve_return": equal_return,
                "regime_label": regime_label,
                "sleeve_returns": json.dumps({s: round(v, 6) for s, v in sleeve_returns.items()}),
            })

        # Overlay predictiveness
        overlay_mult = data.get("sleeve_overlay_multipliers", pd.DataFrame())
        if not overlay_mult.empty:
            # Use trade_date (the column name in real overlay_multipliers parquet)
            date_col = "trade_date" if "trade_date" in overlay_mult.columns else "signal_date"
            for sleeve in SLEEVES:
                m_col = f"{sleeve}_multiplier"
                if m_col in overlay_mult.columns:
                    mults = overlay_mult[[date_col, m_col]].dropna().copy()
                    mults[date_col] = mults[date_col].astype(int)
                    sleeve_ret_list = []
                    for _, mr in mults.iterrows():
                        sd = int(mr[date_col])
                        matching = [r for r in oracle_rows if r["year"] == int(year) and r["signal_date"] == sd]
                        if matching and matching[0]["oracle_best_sleeve"] == sleeve:
                            sleeve_ret_list.append(matching[0]["oracle_best_sleeve_return"])
                    if len(sleeve_ret_list) >= 5:
                        mult_vals = mults[m_col].iloc[:len(sleeve_ret_list)]
                        corr = float(np.corrcoef(mult_vals, sleeve_ret_list)[0, 1]) if len(mult_vals) == len(sleeve_ret_list) else float("nan")
                        predictiveness_rows.append({
                            "year": int(year), "strategy": str(strat),
                            "sleeve": sleeve,
                            "n_periods": len(sleeve_ret_list),
                            "multiplier_return_correlation": corr,
                            "predictive": corr > 0 if not np.isnan(corr) else False,
                        })

    opp_df = pd.DataFrame(opp_rows) if opp_rows else pd.DataFrame()
    if not opp_df.empty and "year" in opp_df.columns:
        opp_df = opp_df.sort_values(["year", "strategy", "period_end"])
    oracle_df = pd.DataFrame(oracle_rows) if oracle_rows else pd.DataFrame()
    if not oracle_df.empty and "year" in oracle_df.columns:
        oracle_df = oracle_df.sort_values(["year", "strategy", "period_end"])
    pred_df = pd.DataFrame(predictiveness_rows) if predictiveness_rows else pd.DataFrame()
    if not pred_df.empty and "year" in pred_df.columns:
        pred_df = pred_df.sort_values(["year", "strategy", "sleeve"])

    return opp_df, oracle_df, pred_df


# ---------------------------------------------------------------------------
# 8. Artifact consistency check
# ---------------------------------------------------------------------------
def _check_artifact_consistency(out_dir: Path, out_doc: Path, out_go_nogo: Path) -> dict[str, Any]:
    """Check that all expected outputs exist and are valid."""
    results: dict[str, Any] = {
        "all_csv_exist": True,
        "reports_exist": True,
        "reports_no_template_artifacts": True,
        "missing_files": [],
        "report_issues": [],
    }

    for fname in EXPECTED_OUTPUTS:
        fpath = out_dir / fname
        if not fpath.exists():
            results["missing_files"].append(fname)
            results["all_csv_exist"] = False

    for report_path in [out_doc, out_go_nogo]:
        if not report_path.exists():
            results["reports_exist"] = False
            results["report_issues"].append(f"Missing report: {report_path}")
            continue
        content = report_path.read_text(encoding="utf-8")
        # Check for template artifacts
        for artifact in ["pd.Timestamp", "strftime", "← auto"]:
            if artifact in content:
                results["reports_no_template_artifacts"] = False
                results["report_issues"].append(f"{report_path.name}: contains '{artifact}'")
                break

    return results


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------
def _write_alpha_failure_report(
    out_doc: Path,
    normalized: pd.DataFrame,
    calendar_audit: pd.DataFrame,
    investment_gate: pd.DataFrame,
    factor_scorecard: pd.DataFrame,
    sleeve_scorecard: pd.DataFrame,
    construction_bridge: pd.DataFrame,
    pre_post_cost: pd.DataFrame,
    regime_router: pd.DataFrame,
    opportunity_cost: pd.DataFrame,
    oracle_df: pd.DataFrame,
    pred_df: pd.DataFrame,
) -> None:
    lines: list[str] = []
    lines.append("# Strategy Alpha Failure Diagnosis Report")
    lines.append("")
    lines.append(f"生成日期：{datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("")

    # 1. Benchmark Calendar Audit
    lines.append("## 1. Benchmark Calendar Audit")
    lines.append("")
    if not calendar_audit.empty:
        mismatches = calendar_audit[calendar_audit["benchmark_calendar_mismatch"] == True]  # noqa: E712
        conflicts = calendar_audit[calendar_audit["benchmark_return_conflict"] == True]  # noqa: E712
        lines.append(f"- Years with benchmark calendar mismatch (>50bps spread): {len(mismatches)}/{len(calendar_audit)}")
        lines.append(f"- Years with BENCHMARK_RETURN_CONFLICT (same period, different bm return): {len(conflicts)}/{len(calendar_audit)}")
        if not conflicts.empty:
            lines.append("")
            lines.append("### ⚠️ Benchmark Return Conflicts Detected")
            for _, row in conflicts.iterrows():
                lines.append(f"  - {int(row['year'])}: max conflict={row['max_benchmark_return_conflict_bps']}bps, status={row['calendar_status']}")
            lines.append("")
            lines.append("> Cross-strategy excess return ranking is UNRELIABLE when benchmark conflicts exist.")
            lines.append("> NO-GO determination is primarily supported by negative absolute returns.")
        lines.append("")
        lines.append("| year | n_strategies | bm_spread_bps | calendar_mismatch | return_conflict | max_conflict_bps | calendar_status | n_common |")
        lines.append("|---:|---:|---:|---:|---:|---:|---:|---:|")
        for _, row in calendar_audit.iterrows():
            lines.append(
                f"| {int(row['year'])} | {int(row['n_strategies'])} | "
                f"{row['benchmark_spread_bps']} | {row['benchmark_calendar_mismatch']} | "
                f"{row['benchmark_return_conflict']} | {row.get('max_benchmark_return_conflict_bps', '')} | "
                f"{row['calendar_status']} | {int(row['n_common_periods'])} |"
            )
    else:
        lines.append("No calendar audit data available.")
    lines.append("")

    # 2. Normalized Returns
    lines.append("## 2. Normalized Strategy Returns (Common Calendar)")
    lines.append("")
    if not normalized.empty:
        val_norm = normalized[normalized["sample"] == "validation"].copy()
        lines.append("| year | strategy | common_return | common_excess | common_IR | excess_reliable | original_excess |")
        lines.append("|---:|---|---:|---:|---:|---:|---:|")
        for _, row in val_norm.iterrows():
            reliable = "✅" if row.get("excess_metric_reliable", True) else "⚠️"
            lines.append(
                f"| {int(row['year'])} | {row['strategy']} | "
                f"{_pct(row['annualized_return_common'])} | {_pct(row['annualized_excess_common'])} | "
                f"{_num(row['information_ratio_common'], 2)} | {reliable} | {_pct(row['original_annualized_excess'])} |"
            )
    lines.append("")

    # 3. Investment Gate
    lines.append("## 3. Investment Gate Decision")
    lines.append("")
    if not investment_gate.empty:
        lines.append("| Strategy | Avg Return | Avg Excess | Median Excess | Pos Years | Avg IR | Max Loss | Excess Reliable | Status |")
        lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
        for _, row in investment_gate.iterrows():
            reliable = "✅" if row.get("excess_metric_reliable", True) else "⚠️ UNRELIABLE"
            lines.append(
                f"| {row['strategy']} | {_pct(row['avg_annualized_return'])} | "
                f"{_pct(row['avg_annualized_excess_return'])} | {_pct(row['median_annualized_excess_return'])} | "
                f"{int(row['positive_excess_years'])}/{int(row['total_validation_years'])} | "
                f"{_num(row['avg_information_ratio'], 2)} | {_pct(row['max_single_year_excess_loss'])} | "
                f"{reliable} | **{row['investment_status']}** |"
            )
        lines.append("")
        for _, row in investment_gate.iterrows():
            if row["failure_reasons"]:
                lines.append(f"- **{row['strategy']}**: {row['failure_reasons']}")
            if row.get("calendar_failure_reasons"):
                lines.append(f"  - Calendar: {row['calendar_failure_reasons']}")
    lines.append("")

    # 4. Factor Scorecard
    lines.append("## 4. Factor Alpha Scorecard (2017-2024) — Strict Retention Gate")
    lines.append("")
    if not factor_scorecard.empty:
        lines.append("| Factor | Type | Mean IC | ICIR | Pos IC Yrs | LongOnly Top | Pos LO Yrs | TB Excess | Pos TB Yrs | Monotonicity | Pos Mono Yrs | Coverage | Retain? |")
        lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
        for _, row in factor_scorecard.iterrows():
            passes = "✅" if row.get("passes_retention_gate", False) else "❌"
            lines.append(
                f"| `{row['factor']}` | {row['factor_type']} | {_num(row['mean_ic'], 3)} | {_num(row['icir_aggregate'], 3)} | "
                f"{int(row['positive_ic_years'])}/{int(row['n_years'])} | "
                f"{_pct(row.get('avg_long_only_top_excess', float('nan')))} | "
                f"{int(row.get('positive_long_only_top_years', 0))}/{int(row['n_years'])} | "
                f"{_pct(row.get('avg_top_bottom_excess', float('nan')))} | "
                f"{int(row.get('positive_top_bottom_years', 0))}/{int(row['n_years'])} | "
                f"{_num(row.get('avg_decile_monotonicity', float('nan')))} | "
                f"{int(row.get('positive_monotonicity_years', 0))}/{int(row['n_years'])} | "
                f"{_pct(row.get('avg_coverage', float('nan')))} | "
                f"{passes} |"
            )
        failing = factor_scorecard[~factor_scorecard["passes_retention_gate"]]
        if not failing.empty:
            lines.append("")
            lines.append("### Factors Failing Retention Gate")
            for _, row in failing.iterrows():
                lines.append(f"- `{row['factor']}`: {row.get('retention_failure_reasons', 'no reason recorded')}")
    lines.append("")

    # 5. Sleeve Scorecard
    lines.append("## 5. Sleeve Alpha Scorecard")
    lines.append("")
    if not sleeve_scorecard.empty:
        lines.append("| Sleeve | N Years | Avg ICIR | Avg Hit Rate | Avg Weight | Pos ICIR Years |")
        lines.append("|---|---:|---:|---:|---:|---:|")
        for _, row in sleeve_scorecard.iterrows():
            lines.append(
                f"| {row['sleeve']} | {int(row['n_years'])} | {_num(row['avg_icir'], 3)} | "
                f"{_pct(row['avg_hit_rate'])} | {_pct(row['avg_weight'])} | "
                f"{int(row['positive_icir_years'])}/{int(row['n_years'])} |"
            )
    lines.append("")

    # 6. Construction Loss Bridge
    lines.append("## 6. Construction Loss Bridge")
    lines.append("")
    if not construction_bridge.empty:
        lines.append("| Year | Strategy | Gross Excess | Net Excess | Cost Drag | Avg Turnover | Avg Cost bps |")
        lines.append("|---:|---|---:|---:|---:|---:|---:|")
        for _, row in construction_bridge.iterrows():
            lines.append(
                f"| {int(row['year'])} | {row['strategy']} | "
                f"{_pct(row['gross_excess_return'])} | {_pct(row['net_excess_return'])} | "
                f"{_pct(row['cost_drag'])} | {_pct(row['avg_turnover'])} | {_num(row['avg_cost_bps'], 1)} |"
            )
        lines.append("")
        val_bridge = construction_bridge[construction_bridge["sample"] == "validation"]
        if not val_bridge.empty:
            gross_pos = (val_bridge["gross_excess_return"] > 0).mean()
            net_pos = (val_bridge["net_excess_return"] > 0).mean()
            lines.append(f"- Gross excess positive rate: {_pct(gross_pos)}")
            lines.append(f"- Net excess positive rate: {_pct(net_pos)}")
            if gross_pos > 0.5 and net_pos < 0.3:
                lines.append("- ⚠️ Costs are destroying alpha that exists pre-cost.")
            elif gross_pos < 0.3:
                lines.append("- ⚠️ Alpha does not exist even pre-cost. Factor pool is the root problem.")
    lines.append("")

    if not pre_post_cost.empty:
        lines.append("### Pre-Cost vs Post-Cost Detail")
        lines.append("")
        lines.append("| Year | Strategy | Pre-Cost Excess | Post-Cost Excess | Cost Drag | Data Source |")
        lines.append("|---:|---|---:|---:|---:|")
        for _, row in pre_post_cost.iterrows():
            lines.append(
                f"| {int(row['year'])} | {row['strategy']} | "
                f"{_pct(row['pre_cost_excess'])} | {_pct(row['post_cost_excess'])} | "
                f"{_pct(row['cost_drag_annualized'])} | {row.get('data_source', '')} |"
            )
    lines.append("")

    # 7. Regime Router
    lines.append("## 7. Regime Router Scorecard")
    lines.append("")
    if not regime_router.empty:
        lines.append("| Year | Strategy | Dominant Regime | Dominant Sleeve | Router Active |")
        lines.append("|---:|---|---|---:|")
        for _, row in regime_router.iterrows():
            lines.append(
                f"| {int(row['year'])} | {row['strategy']} | "
                f"{row.get('dominant_regime', '')} | {row.get('dominant_sleeve', '')} | "
                f"{row.get('router_active', False)} |"
            )
        lines.append("")

        overlay_strats = regime_router[regime_router["router_active"] == True]  # noqa: E712
        if not overlay_strats.empty:
            lines.append("### Overlay Multiplier Summary")
            for sleeve in SLEEVES:
                m_col = f"{sleeve}_avg_multiplier"
                if m_col in overlay_strats.columns:
                    vals = overlay_strats[m_col].dropna()
                    if not vals.empty:
                        lines.append(f"- **{sleeve}**: mean={_num(vals.mean(), 3)}, range=[{_num(vals.min(), 3)}, {_num(vals.max(), 3)}]")
    lines.append("")

    # 8. Oracle & Opportunity Cost
    lines.append("## 8. Sleeve Oracle & Opportunity Cost")
    lines.append("")
    if not opportunity_cost.empty:
        has_data = (opportunity_cost["status"] != "INSUFFICIENT_SLEEVE_RETURN_DATA").any()
        if has_data:
            valid_opp = opportunity_cost[opportunity_cost["status"] == "OK"]
            n_periods = len(valid_opp)
            lines.append(f"- Periods with oracle data (status=OK): {n_periods}")

            # Excluded row counts
            if "status" in opportunity_cost.columns:
                excluded = opportunity_cost[opportunity_cost["status"] != "OK"]
                if not excluded.empty:
                    status_counts = excluded["status"].value_counts()
                    lines.append("")
                    lines.append("### Router Oracle Excluded Rows")
                    for st, count in status_counts.items():
                        lines.append(f"- {st}: {count}")

            if not oracle_df.empty:
                # Oracle sleeve frequency
                oracle_freq = oracle_df["oracle_best_sleeve"].value_counts()
                lines.append("")
                lines.append("### Oracle Sleeve Distribution")
                lines.append("| Sleeve | N Periods as Oracle | Pct |")
                lines.append("|---|---:|")
                for sleeve in SLEEVES:
                    count = int(oracle_freq.get(sleeve, 0))
                    pct = count / len(oracle_df) * 100 if len(oracle_df) > 0 else 0
                    lines.append(f"| {sleeve} | {count} | {pct:.1f}% |")

            if not valid_opp.empty:
                avg_opp = valid_opp["opportunity_cost_vs_oracle"].mean()
                avg_opp_eq = valid_opp["opportunity_cost_vs_equal"].mean()
                dominant_is_oracle_rate = valid_opp["dominant_is_oracle"].mean()
                lines.append("")
                lines.append(f"- Mean opportunity cost vs oracle: {_pct(avg_opp, 2)}")
                lines.append(f"- Mean opportunity cost vs equal-weight: {_pct(avg_opp_eq, 2)}")
                lines.append(f"- Dominant sleeve equals oracle: {_pct(dominant_is_oracle_rate)}")

            if not pred_df.empty:
                pred_pos = (pred_df["predictive"] == True).mean()  # noqa: E712
                lines.append("")
                lines.append("### Overlay Predictiveness")
                lines.append(f"- Sleeves with positive multiplier→return correlation: {_pct(pred_pos)}")
        else:
            lines.append("⚠️ INSUFFICIENT_SLEEVE_RETURN_DATA: sleeve return data not available for oracle computation.")
            lines.append("Run sleeve_weight_cross_year.py with full year coverage first.")
    lines.append("")

    # 9. Diagnosis Summary
    lines.append("## 9. Diagnosis Summary")
    lines.append("")
    lines.append("### Root Cause Classification")
    lines.append("")
    lines.append("1. **原始因子无 alpha** — pre-cost gross excess is negative for most years.")
    lines.append("2. **Top-bottom 有 alpha 但 long-only 无 alpha** — short side drives returns.")
    lines.append("3. **Long-only 有 alpha 但成本吃掉** — gross excess positive, net excess negative.")
    lines.append("4. **成本后仍有 alpha 但 regime/router 降低暴露** — net excess positive but regime misallocates.")
    lines.append("5. **组合约束导致持仓偏离有效暴露** — constraints prevent alpha from reaching portfolio.")
    lines.append("")

    if not construction_bridge.empty:
        val_bridge = construction_bridge[construction_bridge["sample"] == "validation"]
        if not val_bridge.empty:
            mean_gross = val_bridge["gross_excess_return"].mean()
            mean_net = val_bridge["net_excess_return"].mean()
            if mean_gross < 0:
                lines.append(f"**Diagnosis: 原始因子无 alpha** (mean gross excess={_pct(mean_gross)})")
            elif mean_gross > 0 and mean_net < 0:
                lines.append(f"**Diagnosis: 成本吃掉 alpha** (gross={_pct(mean_gross)}, net={_pct(mean_net)})")
            elif mean_net > 0:
                lines.append(f"**Diagnosis: Alpha exists post-cost (net={_pct(mean_net)}) — check router/constraints**")
    lines.append("")

    # Missing diagnostics
    lines.append("### Missing or Unavailable Diagnostics")
    lines.append("")
    lines.append("- `rebalance_frequency_diagnostic.csv`: NOT_AVAILABLE (no multi-frequency runs exist)")
    lines.append("- `topn_capacity_diagnostic.csv`: NOT_AVAILABLE (no multi-topN runs exist)")
    lines.append("")

    out_doc.parent.mkdir(parents=True, exist_ok=True)
    out_doc.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_go_nogo_report(
    out_doc: Path,
    investment_gate: pd.DataFrame,
    normalized: pd.DataFrame,
    calendar_audit: pd.DataFrame,
) -> None:
    lines: list[str] = []
    lines.append("# Strategy Family GO / NO-GO Decision")
    lines.append("")
    lines.append(f"生成日期：{datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("")

    # Benchmark reliability warning
    if not calendar_audit.empty:
        conflicts = calendar_audit[calendar_audit["benchmark_return_conflict"] == True]  # noqa: E712
        if not conflicts.empty:
            lines.append("## ⚠️ Benchmark Reliability Warning")
            lines.append("")
            lines.append("Benchmark return conflicts detected in the following years:")
            for _, row in conflicts.iterrows():
                lines.append(f"- {int(row['year'])}: max same-period benchmark return conflict = {row['max_benchmark_return_conflict_bps']}bps")
            lines.append("")
            lines.append("Cross-strategy excess return comparisons are UNRELIABLE.")
            lines.append("NO-GO determination relies primarily on negative absolute returns.")
            lines.append("")

    lines.append("## Investment Status")
    lines.append("")
    if investment_gate.empty:
        lines.append("No investment gate data available.")
        out_doc.parent.mkdir(parents=True, exist_ok=True)
        out_doc.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return

    lines.append("| Strategy | Investment Status | Avg Excess | Excess Reliable | Pos Years | Avg IR | Max Loss |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for _, row in investment_gate.iterrows():
        icon = {"PRODUCTION_GO": "🟢", "RESEARCH_ONLY": "🟡", "NO_GO": "🔴"}.get(row["investment_status"], "⚪")
        reliable = "✅" if row.get("excess_metric_reliable", True) else "⚠️"
        lines.append(
            f"| {row['strategy']} | {icon} **{row['investment_status']}** | "
            f"{_pct(row['avg_annualized_excess_return'])} | {reliable} | "
            f"{int(row['positive_excess_years'])}/{int(row['total_validation_years'])} | "
            f"{_num(row['avg_information_ratio'], 2)} | {_pct(row['max_single_year_excess_loss'])} |"
        )
    lines.append("")

    lines.append("## Recommendations")
    lines.append("")
    go_s = investment_gate[investment_gate["investment_status"] == "PRODUCTION_GO"]
    research_s = investment_gate[investment_gate["investment_status"] == "RESEARCH_ONLY"]
    nogo_s = investment_gate[investment_gate["investment_status"] == "NO_GO"]

    if not go_s.empty:
        lines.append("### 🟢 Production GO")
        for _, row in go_s.iterrows():
            lines.append(f"- **{row['strategy']}**: meets all investment gate thresholds.")
        lines.append("")

    if not research_s.empty:
        lines.append("### 🟡 Research Only")
        for _, row in research_s.iterrows():
            lines.append(f"- **{row['strategy']}**: close but not passing. {row['failure_reasons']}")
        lines.append("")

    if not nogo_s.empty:
        lines.append("### 🔴 NO-GO")
        for _, row in nogo_s.iterrows():
            lines.append(f"- **{row['strategy']}**: {row['failure_reasons']}")
            if row.get("calendar_failure_reasons"):
                lines.append(f"  - Calendar: {row['calendar_failure_reasons']}")
        lines.append("")

    all_nogo = len(go_s) == 0
    lines.append("## Path Forward")
    lines.append("")
    if all_nogo:
        lines.append("**All strategies are NO-GO for production.**")
        lines.append("")
        lines.append("Recommended actions:")
        lines.append("1. Review factor scorecard — which factors survive the strict retention gate?")
        lines.append("2. If 0 factors survive → **Kill / Restart**: current factor pool cannot support positive alpha.")
        lines.append("3. If 1-3 factors survive → **Alpha salvage**: build minimal candidate pool from surviving factors.")
        lines.append("4. If gross excess positive but net negative → **Construction repair**: fix costs and constraints.")
        lines.append("5. Do NOT continue tuning regime weights — the alpha layer must be fixed first.")
    else:
        lines.append("Some strategies pass investment gate. Proceed to production validation.")
    lines.append("")

    out_doc.parent.mkdir(parents=True, exist_ok=True)
    out_doc.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(description="Strategy-family alpha failure diagnosis v2")
    parser.add_argument("--runs-csv", default="outputs/validation/frozen_backtest/runs.csv")
    parser.add_argument("--out-dir", default="outputs/analysis/strategy_alpha_failure")
    parser.add_argument("--out-doc", default="docs/strategy_alpha_failure_report.md")
    parser.add_argument("--out-go-nogo", default="docs/strategy_family_go_nogo.md")
    args = parser.parse_args()

    runs_csv = _resolve_path(args.runs_csv)
    out_dir = _resolve_path(args.out_dir)
    out_doc = _resolve_path(args.out_doc)
    out_go_nogo = _resolve_path(args.out_go_nogo)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading runs from {runs_csv}")
    runs = _load_runs(runs_csv)
    print(f"  {len(runs)} rows, {runs['strategy'].nunique()} strategies")

    print("Loading period-level diagnostics...")
    period_data = _load_all_periods(runs)
    print(f"  {len(period_data)} run diagnostics loaded")

    # 1. Common-calendar evaluation
    print("Computing common-calendar evaluation (with benchmark conflict detection)...")
    normalized, calendar_audit = _common_calendar_evaluation(runs, period_data)
    normalized.to_csv(out_dir / "normalized_strategy_metrics.csv", index=False, encoding="utf-8-sig")
    calendar_audit.to_csv(out_dir / "benchmark_calendar_audit.csv", index=False, encoding="utf-8-sig")
    print(f"  Wrote normalized_strategy_metrics.csv ({len(normalized)} rows)")
    print(f"  Wrote benchmark_calendar_audit.csv ({len(calendar_audit)} rows)")

    val_norm = normalized[normalized["sample"] == "validation"].copy()
    if not val_norm.empty:
        piv = val_norm.pivot_table(index="year", columns="strategy", values="annualized_excess_common", aggfunc="first").reset_index()
        piv.to_csv(out_dir / "strategy_yearly_returns_common_calendar.csv", index=False, encoding="utf-8-sig")

    # 2. Investment gate
    print("Computing investment gate...")
    investment_gate = _compute_investment_gate(normalized, runs, calendar_audit)
    investment_gate.to_csv(out_dir / "strategy_investment_gate.csv", index=False, encoding="utf-8-sig")
    print(f"  Wrote strategy_investment_gate.csv ({len(investment_gate)} rows)")

    # 3. Factor scorecard (strict)
    print("Building factor alpha scorecard (strict retention gate)...")
    factor_scorecard = _build_factor_scorecard(period_data, runs)
    if not factor_scorecard.empty:
        factor_scorecard.to_csv(out_dir / "factor_alpha_scorecard_2017_2024.csv", index=False, encoding="utf-8-sig")
        n_pass = int(factor_scorecard["passes_retention_gate"].sum())
        print(f"  Wrote factor_alpha_scorecard_2017_2024.csv ({len(factor_scorecard)} factors, {n_pass} pass strict gate)")
    else:
        print("  [WARN] No factor scorecard data — run sleeve_weight_cross_year.py first")

    # 4. Sleeve scorecard
    print("Building sleeve alpha scorecard...")
    sleeve_scorecard = _build_sleeve_scorecard(period_data, runs)
    if not sleeve_scorecard.empty:
        sleeve_scorecard.to_csv(out_dir / "sleeve_alpha_scorecard_2017_2024.csv", index=False, encoding="utf-8-sig")
        print(f"  Wrote sleeve_alpha_scorecard_2017_2024.csv ({len(sleeve_scorecard)} sleeves)")

    # 5. Construction diagnostics
    print("Building construction diagnostics...")
    construction_bridge, pre_post_cost, rebalance_freq, topn_cap = _build_construction_diagnostics(period_data, runs, out_dir)
    if not construction_bridge.empty:
        construction_bridge.to_csv(out_dir / "construction_loss_bridge.csv", index=False, encoding="utf-8-sig")
        print(f"  Wrote construction_loss_bridge.csv ({len(construction_bridge)} rows)")
    if not pre_post_cost.empty:
        pre_post_cost.to_csv(out_dir / "pre_cost_vs_post_cost.csv", index=False, encoding="utf-8-sig")
        print(f"  Wrote pre_cost_vs_post_cost.csv ({len(pre_post_cost)} rows)")
    rebalance_freq.to_csv(out_dir / "rebalance_frequency_diagnostic.csv", index=False, encoding="utf-8-sig")
    topn_cap.to_csv(out_dir / "topn_capacity_diagnostic.csv", index=False, encoding="utf-8-sig")
    print("  Wrote rebalance_frequency_diagnostic.csv (NOT_AVAILABLE)")
    print("  Wrote topn_capacity_diagnostic.csv (NOT_AVAILABLE)")

    # 6. Regime router scorecard
    print("Building regime router scorecard...")
    regime_router = _build_regime_router_scorecard(period_data, runs)
    if not regime_router.empty:
        regime_router.to_csv(out_dir / "regime_router_scorecard.csv", index=False, encoding="utf-8-sig")
        print(f"  Wrote regime_router_scorecard.csv ({len(regime_router)} rows)")

    # 7. Oracle & opportunity cost (REAL)
    print("Building real sleeve oracle & opportunity cost...")
    opportunity_cost, oracle_df, pred_df = _build_router_opportunity_cost(period_data, runs, out_dir)
    if not opportunity_cost.empty:
        opportunity_cost.to_csv(out_dir / "router_opportunity_cost.csv", index=False, encoding="utf-8-sig")
        n_ok = int((opportunity_cost["status"] == "OK").sum())
        n_insufficient = int((opportunity_cost["status"] == "INSUFFICIENT_SLEEVE_RETURN_DATA").sum())
        print(f"  Wrote router_opportunity_cost.csv ({len(opportunity_cost)} rows, {n_ok} OK, {n_insufficient} INSUFFICIENT)")
    if not oracle_df.empty:
        oracle_df.to_csv(out_dir / "sleeve_hindsight_oracle.csv", index=False, encoding="utf-8-sig")
        print(f"  Wrote sleeve_hindsight_oracle.csv ({len(oracle_df)} rows)")
    if not pred_df.empty:
        pred_df.to_csv(out_dir / "overlay_predictiveness.csv", index=False, encoding="utf-8-sig")
        print(f"  Wrote overlay_predictiveness.csv ({len(pred_df)} rows)")

    # 8. Reports
    print("Generating reports...")
    _write_alpha_failure_report(
        out_doc, normalized, calendar_audit, investment_gate,
        factor_scorecard, sleeve_scorecard, construction_bridge, pre_post_cost,
        regime_router, opportunity_cost, oracle_df, pred_df,
    )
    print(f"  Wrote {out_doc}")
    _write_go_nogo_report(out_go_nogo, investment_gate, normalized, calendar_audit)
    print(f"  Wrote {out_go_nogo}")

    # 9. Artifact consistency check
    print("Running artifact consistency check...")
    check_result = _check_artifact_consistency(out_dir, out_doc, out_go_nogo)
    if check_result["all_csv_exist"]:
        print("  [OK] All expected CSV outputs exist")
    else:
        print(f"  [FAIL] Missing CSVs: {check_result['missing_files']}")
    if check_result["reports_exist"]:
        print("  [OK] Reports exist")
    else:
        print(f"  [FAIL] Report issues: {check_result['report_issues']}")
    if check_result["reports_no_template_artifacts"]:
        print("  [OK] Reports have no template artifacts")
    else:
        print(f"  [WARN] Report template artifacts found: {check_result['report_issues']}")

    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

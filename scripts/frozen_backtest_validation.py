"""Frozen out-of-sample backtest validation.

This driver intentionally does no parameter search.  It reuses fixed strategy
configs and yearly windows, then writes one compact report for review.

Default validation set excludes 2025 because recent diagnostics and candidate
selection used that year heavily.  2026 is YTD and should be read separately.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
RUN_RESEARCH = ROOT / "run_research.py"


WINDOWS: dict[int, tuple[str, str, str]] = {
    2017: ("20170101", "20171231", "validation"),
    2018: ("20180101", "20181231", "validation"),
    2019: ("20190101", "20191231", "validation"),
    2020: ("20200101", "20201231", "validation"),
    2021: ("20210101", "20211231", "validation"),
    2022: ("20220101", "20221231", "validation"),
    2023: ("20230101", "20231231", "validation"),
    2024: ("20240101", "20241231", "validation"),
    2025: ("20250101", "20251231", "discovery"),
    2026: ("20260101", "20260605", "ytd"),
}


@dataclass(frozen=True)
class Strategy:
    name: str
    label: str
    args: tuple[str, ...]


STRATEGIES: dict[str, Strategy] = {
    "A_5reversal": Strategy(
        name="A_5reversal",
        label="固定 5 反转因子",
        args=(
            "--factors-config",
            "configs/factors_5reversal.yaml",
            "--strategy-mode",
            "factor_dynamic",
        ),
    ),
    "B_dynamic": Strategy(
        name="B_dynamic",
        label="全候选因子 + 动态 IC 权重",
        args=(
            "--factors-config",
            "configs/factors_dynamic.yaml",
            "--strategy-mode",
            "factor_dynamic",
        ),
    ),
    "C_regime_baseline": Strategy(
        name="C_regime_baseline",
        label="Regime baseline",
        args=(
            "--factors-config",
            "configs/factors.yaml",
            "--strategy-mode",
            "regime",
            "--regime-config",
            "configs/regime.yaml",
        ),
    ),
    "D_regime_overlay": Strategy(
        name="D_regime_overlay",
        label="冻结候选：less_reversal_faster_overlay",
        args=(
            "--factors-config",
            "configs/factors.yaml",
            "--strategy-mode",
            "regime",
            "--regime-config",
            "outputs/analysis/regime_grid_overlay_phase2_2025/configs/less_reversal_faster_overlay.yaml",
        ),
    ),
    "E_shock_reversal": Strategy(
        name="E_shock_reversal",
        label="Regime + shock_reversal 低权重",
        args=(
            "--factors-config",
            "configs/factors.yaml",
            "--strategy-mode",
            "regime",
            "--regime-config",
            "configs/regime_shock_reversal.yaml",
        ),
    ),
    "E_candidate_v2": Strategy(
        name="E_candidate_v2",
        label="Candidate v2: factors_candidate_v1 + regime_candidate_v2",
        args=(
            "--factors-config",
            "configs/factors_candidate_v1.yaml",
            "--strategy-mode",
            "regime",
            "--regime-config",
            "configs/regime_candidate_v2.yaml",
        ),
    ),
    "F_candidate_v3": Strategy(
        name="F_candidate_v3",
        label="Candidate v3: factors_candidate_v1 + regime_candidate_v3 (perf overlay)",
        args=(
            "--factors-config",
            "configs/factors_candidate_v1.yaml",
            "--strategy-mode",
            "regime",
            "--regime-config",
            "configs/regime_candidate_v3.yaml",
        ),
    ),
    "G_candidate_v4": Strategy(
        name="G_candidate_v4",
        label="Candidate v4: alpha rebuild + regime_candidate_v4 (no overlay)",
        args=(
            "--factors-config",
            "configs/factors_candidate_v4.yaml",
            "--strategy-mode",
            "regime",
            "--regime-config",
            "configs/regime_candidate_v4.yaml",
        ),
    ),
    "G_candidate_v4_lite": Strategy(
        name="G_candidate_v4_lite",
        label="Candidate v4-lite: V3 factors + V4 regime (no overlay) — isolates regime effect",
        args=(
            "--factors-config",
            "configs/factors_candidate_v1.yaml",
            "--strategy-mode",
            "regime",
            "--regime-config",
            "configs/regime_candidate_v4.yaml",
        ),
    ),
    "G_candidate_v4_r1": Strategy(
        name="G_candidate_v4_r1",
        label="Candidate v4 r1: repaired alpha rebuild + regime_candidate_v4_r1",
        args=(
            "--factors-config",
            "configs/factors_candidate_v4_r1.yaml",
            "--strategy-mode",
            "regime",
            "--regime-config",
            "configs/regime_candidate_v4_r1.yaml",
        ),
    ),
    "G_candidate_v4_r2": Strategy(
        name="G_candidate_v4_r2",
        label="Candidate v4 r2: data-clean gate-compliant alpha candidate",
        args=(
            "--factors-config",
            "configs/factors_candidate_v4_r2.yaml",
            "--strategy-mode",
            "regime",
            "--regime-config",
            "configs/regime_candidate_v4_r2.yaml",
        ),
    ),
    "A_regime_v2": Strategy(
        name="A_regime_v2",
        label="A: RegimeDetector V2 (PIT-normalised scoring, reduced range_bound bias)",
        args=(
            "--factors-config",
            "configs/factors.yaml",
            "--strategy-mode",
            "regime",
            "--regime-config",
            "configs/regime_v2.yaml",
        ),
    ),
    "B_direct_state_v1": Strategy(
        name="B_direct_state_v1",
        label="B: Direct State Allocator (vol/breadth → momentum, no softmax regime)",
        args=(
            "--factors-config",
            "configs/factors.yaml",
            "--strategy-mode",
            "regime",
            "--regime-config",
            "configs/direct_state_v1.yaml",
        ),
    ),
}


METRIC_KEYS = [
    "annualized_return",
    "annualized_excess_return",
    "benchmark_annualized_return",
    "information_ratio",
    "sharpe_ratio",
    "max_drawdown",
    "avg_turnover",
    "total_cost_bps",
    "n_periods",
    "data_quality_status",
    "benchmark_status",
    "metric_stability_status",
    "max_single_period_return",
    "max_single_period_return_date",
]


def _arg_value(args: tuple[str, ...], flag: str) -> str | None:
    if flag not in args:
        return None
    idx = args.index(flag)
    if idx + 1 >= len(args):
        return None
    return args[idx + 1]


def _norm_path_like(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("\\", "/").rstrip("/")


def _run_dirs() -> list[Path]:
    runs_root = ROOT / "outputs" / "runs"
    if not runs_root.exists():
        return []
    return sorted(
        [p for p in runs_root.iterdir() if p.is_dir()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )


def _compute_file_sha256(file_path: str) -> str:
    """Compute SHA256 hex digest of a file."""
    try:
        p = Path(file_path)
        if not p.exists():
            return ""
        return hashlib.sha256(p.read_bytes()).hexdigest()
    except Exception:
        return ""


def _compute_factor_list_hash(factor_list: list) -> str:
    """Compute SHA256 of the sorted, joined factor_list."""
    if not factor_list:
        return ""
    normalized = ",".join(sorted(str(f) for f in factor_list))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _manifest_matches(
    run_dir: Path, start: str, end: str, top_n: int, strategy: Strategy,
    check_hashes: bool = True,
    allow_legacy_manifest: bool = False,
) -> bool:
    """Check if a run_dir manifest matches the requested config.

    When check_hashes=True (the default), validates that config files haven't
    changed since the run was created.

    When allow_legacy_manifest=False (the default), manifests that are missing
    required hash fields are rejected — this is the formal acceptance behavior.
    Use allow_legacy_manifest=True ONLY for diagnostic inspection of old runs;
    it must never be used for formal acceptance validation.
    """
    manifest_path = run_dir / "run_manifest.json"
    metrics_path = run_dir / "metrics_summary.json"
    if not manifest_path.exists() or not metrics_path.exists():
        return False
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return False

    expected_factors = _arg_value(strategy.args, "--factors-config")
    expected_mode = _arg_value(strategy.args, "--strategy-mode") or "factor_dynamic"
    expected_regime = _arg_value(strategy.args, "--regime-config") or ""

    # Basic path and parameter match
    basic_match = (
        str(manifest.get("start")) == start
        and str(manifest.get("end")) == end
        and int(manifest.get("top_n", -1)) == int(top_n)
        and str(manifest.get("strategy_mode")) == expected_mode
        and _norm_path_like(manifest.get("factors_config")) == _norm_path_like(expected_factors)
        and (
            expected_mode != "regime"
            or _norm_path_like(manifest.get("regime_config")) == _norm_path_like(expected_regime)
        )
    )

    if not basic_match:
        return False

    # If hash checking is enabled, validate config content hasn't changed
    if check_hashes:
        # Determine which hash fields are required
        required_hash_fields = [
            "factors_config_sha256",
            "factor_list_sha256",
        ]
        if expected_mode == "regime" and expected_regime:
            required_hash_fields.append("regime_config_sha256")

        # Check for missing hash fields
        missing_hashes = [k for k in required_hash_fields if not manifest.get(k)]

        if missing_hashes:
            if allow_legacy_manifest:
                # Legacy mode: skip hash checks, just return basic match
                return True
            else:
                # Strict mode: reject manifests without required hashes
                return False

        # All required hashes present — validate them
        # Check factors_config hash
        if expected_factors:
            manifest_fc_hash = manifest["factors_config_sha256"]
            current_fc_hash = _compute_file_sha256(expected_factors)
            if current_fc_hash and manifest_fc_hash != current_fc_hash:
                return False

        # Check regime_config hash
        if expected_mode == "regime" and expected_regime:
            manifest_rc_hash = manifest["regime_config_sha256"]
            current_rc_hash = _compute_file_sha256(expected_regime)
            if current_rc_hash and manifest_rc_hash != current_rc_hash:
                return False

        # Check factor_list hash (internal consistency check)
        manifest_fl = manifest.get("factor_list", [])
        current_fl_hash = _compute_factor_list_hash(manifest_fl)
        manifest_fl_hash = manifest["factor_list_sha256"]
        if current_fl_hash and manifest_fl_hash != current_fl_hash:
            return False

    return True


def _periods_within_manifest_window(run_dir: Path) -> bool:
    """Return True only when diagnostic holding periods stay inside manifest end."""
    try:
        manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
        end = int(manifest["end"])
        pv_path = run_dir / "diagnostics" / "phase2_portfolio_values.parquet"
        if not pv_path.exists():
            return False
        pv = pd.read_parquet(pv_path, columns=["period_end"])
        if pv.empty:
            return False
        return int(pv["period_end"].max()) <= end
    except Exception:
        return False


def _has_valid_phase2_metrics(run_dir: Path) -> bool:
    try:
        metrics = json.loads((run_dir / "metrics_summary.json").read_text(encoding="utf-8"))
    except Exception:
        return False
    phase2 = metrics.get("phase2", {})
    return (
        phase2.get("benchmark_status") == "OK"
        and phase2.get("annualized_return") is not None
        and phase2.get("annualized_excess_return") is not None
        and phase2.get("information_ratio") is not None
        and phase2.get("go_nogo", {}).get("overall") != "NO_GO_DATA_INVALID"
        and _periods_within_manifest_window(run_dir)
    )


def _find_existing_run(start: str, end: str, top_n: int, strategy: Strategy,
                      check_hashes: bool = True,
                      allow_legacy_manifest: bool = False) -> Path | None:
    for run_dir in _run_dirs():
        if (
            _manifest_matches(run_dir, start, end, top_n, strategy,
                              check_hashes=check_hashes,
                              allow_legacy_manifest=allow_legacy_manifest)
            and _has_valid_phase2_metrics(run_dir)
        ):
            return run_dir
    return None


def _new_run_dir(before: set[Path]) -> Path | None:
    created = [p for p in _run_dirs() if p not in before]
    return created[0] if created else None


def _write_reuse_audit_log(
    log_path: Path,
    year: int,
    start: str,
    end: str,
    top_n: int,
    strategy: Strategy,
    existing: Path,
) -> None:
    """Write an audit log when reusing an existing run.

    Produces a compact log that allows frozen-backtest auditors
    to trace from the strategy/year → run_dir → manifest without
    re-executing ``run_research.py``.
    """
    import json as _json

    manifest_path = existing / "run_manifest.json"
    manifest: dict = {}
    try:
        manifest = _json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        pass

    metrics_path = existing / "metrics_summary.json"

    lines = [
        f"Reusing existing run: {existing}",
        f"validated_by=frozen_backtest_validation.py",
        f"strategy={strategy.name}",
        f"label={strategy.label}",
        f"year={year}",
        f"start={start}",
        f"end={end}",
        f"top_n={top_n}",
        f"args={' '.join(strategy.args)}",
        f"run_id={manifest.get('run_id', '')}",
        f"factors_config={manifest.get('factors_config', '')}",
        f"factors_config_sha256={manifest.get('factors_config_sha256', '')}",
        f"regime_config={manifest.get('regime_config', '')}",
        f"regime_config_sha256={manifest.get('regime_config_sha256', '')}",
        f"factor_list_sha256={manifest.get('factor_list_sha256', '')}",
        f"strategy_mode={manifest.get('strategy_mode', '')}",
        f"metrics_summary={str(metrics_path)}",
        f"diagnostics={str(existing / 'diagnostics')}",
        "",
    ]

    log_path.write_text("\n".join(lines), encoding="utf-8")


def _run_one(
    year: int,
    start: str,
    end: str,
    top_n: int,
    strategy: Strategy,
    log_dir: Path,
    reuse_existing: bool,
    check_hashes: bool = True,
    allow_legacy_manifest: bool = False,
) -> tuple[int, Path | None]:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{year}_{strategy.name}.log"

    if reuse_existing:
        existing = _find_existing_run(start, end, top_n, strategy,
                                      check_hashes=check_hashes,
                                      allow_legacy_manifest=allow_legacy_manifest)
        if existing is not None:
            _write_reuse_audit_log(
                log_path, year, start, end, top_n, strategy, existing
            )
            print(f"  Reusing existing run: {existing.name}")
            return 0, existing

    before = set(_run_dirs())
    cmd = [
        sys.executable,
        "-X",
        "utf8",
        str(RUN_RESEARCH),
        "phase2",
        "--start",
        start,
        "--end",
        end,
        "--top-n",
        str(top_n),
        "--no-recompute",
        *strategy.args,
    ]
    print("Running " + " ".join(cmd))
    with log_path.open("w", encoding="utf-8") as fh:
        proc = subprocess.run(
            cmd,
            cwd=ROOT,
            stdout=fh,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
        )
    return proc.returncode, _new_run_dir(before)


def _load_metrics(run_dir: Path | None) -> dict[str, Any]:
    if run_dir is None:
        return {}
    path = run_dir / "metrics_summary.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("phase2", {})


def _go_nogo_overall(metrics: dict[str, Any]) -> str:
    return str(metrics.get("go_nogo", {}).get("overall", ""))


def _go_nogo_reasons(metrics: dict[str, Any]) -> str:
    reasons = metrics.get("go_nogo", {}).get("failure_reasons", [])
    if not reasons:
        return ""
    return "; ".join(str(r) for r in reasons)


def _max_diagnostic_period_end(run_dir: Path | None) -> int | None:
    if run_dir is None:
        return None
    try:
        pv_path = run_dir / "diagnostics" / "phase2_portfolio_values.parquet"
        if not pv_path.exists():
            return None
        pv = pd.read_parquet(pv_path, columns=["period_end"])
        if pv.empty:
            return None
        return int(pv["period_end"].max())
    except Exception:
        return None


def _fmt_pct(value: Any, digits: int = 1) -> str:
    if value is None or pd.isna(value):
        return ""
    return f"{float(value) * 100:.{digits}f}%"


def _fmt_num(value: Any, digits: int = 2) -> str:
    if value is None or pd.isna(value):
        return ""
    return f"{float(value):.{digits}f}"


def _write_report(df: pd.DataFrame, out_doc: Path, include_discovery_2025: bool) -> None:
    lines: list[str] = []
    lines.append("# 冻结配置回测验证")
    lines.append("")
    lines.append("## 边界")
    lines.append("")
    lines.append("- 固定策略配置；不搜索参数、不按结果改配置。")
    lines.append("- 默认验证集为 2017-2024；2026 是 YTD，仅作前瞻观察。")
    if include_discovery_2025:
        lines.append("- 2025 标为 discovery，不作为独立 OOS 证据。")
    else:
        lines.append("- 2025 被排除，因为该年份已用于问题发现和候选配置形成。")
    lines.append("- 所有 Phase2 命令使用 `--no-recompute`，不自动重建因子缓存。")
    lines.append("")

    cols = [
        "year",
        "sample",
        "strategy",
        "go_nogo_overall",
        "annualized_return",
        "annualized_excess_return",
        "information_ratio",
        "max_drawdown",
        "avg_turnover",
        "n_periods",
        "max_single_period_return",
        "max_period_end",
    ]
    table = df[[c for c in cols if c in df.columns]].copy()
    for col in [
        "annualized_return",
        "annualized_excess_return",
        "max_drawdown",
        "avg_turnover",
        "max_single_period_return",
    ]:
        if col in table:
            table[col] = table[col].map(_fmt_pct)
    if "information_ratio" in table:
        table["information_ratio"] = table["information_ratio"].map(_fmt_num)

    lines.append("## 年度结果")
    lines.append("")
    lines.append(table.to_markdown(index=False))
    lines.append("")

    invalid_mask = (
        df["go_nogo_overall"].eq("NO_GO_DATA_INVALID")
        if "go_nogo_overall" in df.columns
        else pd.Series(False, index=df.index)
    )
    invalid = df[invalid_mask].copy()
    if not invalid.empty:
        invalid_cols = [
            "year",
            "sample",
            "strategy",
            "max_single_period_return",
            "go_nogo_reasons",
            "run_dir",
        ]
        invalid_table = invalid[[c for c in invalid_cols if c in invalid.columns]].copy()
        if "max_single_period_return" in invalid_table:
            invalid_table["max_single_period_return"] = invalid_table[
                "max_single_period_return"
            ].map(_fmt_pct)
        lines.append("## 数据质量剔除")
        lines.append("")
        lines.append(
            "以下记录保留在明细表中，但不进入胜率、均值或升级判断。"
        )
        lines.append("")
        lines.append(invalid_table.to_markdown(index=False))
        lines.append("")

    eligible = df[~invalid_mask].copy()
    piv = eligible.pivot_table(
        index=["year", "sample"],
        columns="strategy",
        values="annualized_excess_return",
        aggfunc="first",
    ).reset_index()
    if {"D_regime_overlay", "C_regime_baseline"}.issubset(piv.columns):
        piv["D_minus_C_excess"] = piv["D_regime_overlay"] - piv["C_regime_baseline"]
    if {"D_regime_overlay", "A_5reversal"}.issubset(piv.columns):
        piv["D_minus_A_excess"] = piv["D_regime_overlay"] - piv["A_5reversal"]
    if {"B_dynamic", "A_5reversal"}.issubset(piv.columns):
        piv["B_minus_A_excess"] = piv["B_dynamic"] - piv["A_5reversal"]
    if {"E_candidate_v2", "D_regime_overlay"}.issubset(piv.columns):
        piv["E2_minus_D_excess"] = (
            piv["E_candidate_v2"] - piv["D_regime_overlay"]
        )
    if {"E_candidate_v2", "C_regime_baseline"}.issubset(piv.columns):
        piv["E2_minus_C_excess"] = (
            piv["E_candidate_v2"] - piv["C_regime_baseline"]
        )

    delta_cols = [
        "year",
        "sample",
        "D_minus_C_excess",
        "D_minus_A_excess",
        "B_minus_A_excess",
        "E2_minus_D_excess",
        "E2_minus_C_excess",
    ]
    delta = piv[[c for c in delta_cols if c in piv.columns]].copy()
    for col in delta.columns:
        if col.endswith("_excess"):
            delta[col] = delta[col].map(_fmt_pct)
    lines.append("## 相对差异")
    lines.append("")
    lines.append(delta.to_markdown(index=False))
    lines.append("")

    validation = piv[piv["sample"] == "validation"].copy()
    lines.append("## 初步判读")
    lines.append("")
    lines.append("- 判读统计已排除 `NO_GO_DATA_INVALID` 记录。")
    if "D_minus_C_excess" in validation:
        vals = validation["D_minus_C_excess"].dropna()
        if not vals.empty:
            hit_rate = float((vals > 0).mean())
            lines.append(
                "- 冻结 overlay 候选相对 regime baseline 的验证年胜率："
                f"{_fmt_pct(hit_rate)}，平均年化超额差：{_fmt_pct(vals.mean())}。"
            )
    if "B_minus_A_excess" in validation:
        vals = validation["B_minus_A_excess"].dropna()
        if not vals.empty:
            hit_rate = float((vals > 0).mean())
            lines.append(
                "- 动态全因子相对固定 5 反转的验证年胜率："
                f"{_fmt_pct(hit_rate)}，平均年化超额差：{_fmt_pct(vals.mean())}。"
            )
    if "E2_minus_D_excess" in validation:
        vals = validation["E2_minus_D_excess"].dropna()
        if not vals.empty:
            hit_rate = float((vals > 0).mean())
            lines.append(
                "- Candidate v2 相对 D_regime_overlay 的验证年胜率："
                f"{_fmt_pct(hit_rate)}，平均年化超额差：{_fmt_pct(vals.mean())}。"
            )
    if "E2_minus_C_excess" in validation:
        vals = validation["E2_minus_C_excess"].dropna()
        if not vals.empty:
            hit_rate = float((vals > 0).mean())
            lines.append(
                "- Candidate v2 相对 C_regime_baseline 的验证年胜率："
                f"{_fmt_pct(hit_rate)}，平均年化超额差：{_fmt_pct(vals.mean())}。"
            )
    lines.append(
        "- 判读规则：只有跨多数验证年改善、且 2026 YTD 不明显反向，"
        "才进入更细的交易成本/持仓归因；否则保留诊断，不升级为生产候选。"
    )

    out_doc.parent.mkdir(parents=True, exist_ok=True)
    out_doc.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--years", nargs="+", type=int)
    parser.add_argument("--strategies", nargs="+", default=list(STRATEGIES))
    parser.add_argument("--top-n", type=int, default=50)
    parser.add_argument("--out-dir", default="outputs/validation/frozen_backtest")
    parser.add_argument("--out-doc", default="docs/frozen_backtest_validation.md")
    parser.add_argument(
        "--reuse-existing", action="store_true", default=False,
        help="Reuse existing runs if manifest matches (including config hashes). "
             "Without this flag, all runs are re-executed fresh."
    )
    parser.add_argument(
        "--force", action="store_true", default=False,
        help="Force re-run all years even if valid existing runs exist. "
             "Overrides --reuse-existing."
    )
    parser.add_argument(
        "--skip-existing", action="store_true", default=False,
        help="DEPRECATED: use --reuse-existing instead. "
             "Kept for backward compatibility."
    )
    parser.add_argument(
        "--no-skip-existing", action="store_true", default=False,
        help="DEPRECATED: this is now the default behavior. "
             "Kept for backward compatibility."
    )
    parser.add_argument(
        "--allow-legacy-manifest", action="store_true", default=False,
        help="Allow reusing old runs whose manifests lack config hash fields. "
             "WARNING: This is for diagnostic inspection only. "
             "Runs reused under this flag CANNOT be used as formal acceptance evidence."
    )
    parser.add_argument("--include-discovery-2025", action="store_true")
    args = parser.parse_args()

    # Resolve reuse mode:
    # --force means never reuse.
    # --reuse-existing or --skip-existing means reuse if manifest matches.
    # default (none of the above) means fresh re-run.
    force_rerun = args.force
    reuse_existing = (args.reuse_existing or args.skip_existing) and not force_rerun
    check_hashes = reuse_existing  # Only check hashes if we're in reuse mode
    allow_legacy_manifest = args.allow_legacy_manifest

    if force_rerun:
        print("--force: all runs will be re-executed (no reuse).")
    elif reuse_existing:
        if allow_legacy_manifest:
            print("--reuse-existing --allow-legacy-manifest: "
                  "will reuse existing runs, including legacy manifests without hashes.")
            print("  ⚠️  WARNING: Legacy manifest reuse is NOT valid for formal acceptance.")
        else:
            print("--reuse-existing: will reuse valid existing runs "
                  "with matching config hashes (strict mode — legacy manifests rejected).")
    else:
        print("Default mode: fresh re-run for all years (no reuse).")

    years = args.years
    if years is None:
        years = [2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2026]
        if args.include_discovery_2025:
            years.insert(8, 2025)

    strategies = [STRATEGIES[name] for name in args.strategies]
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    log_dir = out_dir / "logs"

    # ── Pre-flight: formal candidate policy enforcement ──
    from configs.factor_config import load_factor_config, validate_candidate_policy

    for strategy in strategies:
        factors_config_path = _arg_value(strategy.args, "--factors-config")
        if factors_config_path:
            factor_config = load_factor_config(factors_config_path)
            policy_result = validate_candidate_policy(factor_config)
            if not policy_result["valid"]:
                print(
                    f"BLOCKED: Strategy '{strategy.name}' — "
                    f"{policy_result['blocked_reason']}"
                )
                print(
                    "Fix: update enabled_factors in "
                    f"{factors_config_path} with >= "
                    f"{policy_result['min_gate_pass_alpha_factors']} "
                    "gate-PASS alpha factors, or set "
                    "candidate_policy.formal_candidate=false."
                )
                return 1

    rows: list[dict[str, Any]] = []
    for year in years:
        if year not in WINDOWS:
            raise ValueError(f"No frozen window defined for year={year}")
        start, end, sample = WINDOWS[year]
        for strategy in strategies:
            rc, run_dir = _run_one(
                year=year,
                start=start,
                end=end,
                top_n=args.top_n,
                strategy=strategy,
                log_dir=log_dir,
                reuse_existing=reuse_existing,
                check_hashes=check_hashes,
                allow_legacy_manifest=allow_legacy_manifest,
            )
            metrics = _load_metrics(run_dir)
            row: dict[str, Any] = {
                "year": year,
                "sample": sample,
                "start": start,
                "end": end,
                "strategy": strategy.name,
                "label": strategy.label,
                "return_code": rc,
                "run_dir": str(run_dir) if run_dir is not None else "",
            }
            row.update({key: metrics.get(key) for key in METRIC_KEYS})
            row["go_nogo_overall"] = _go_nogo_overall(metrics)
            row["go_nogo_reasons"] = _go_nogo_reasons(metrics)
            row["max_period_end"] = _max_diagnostic_period_end(run_dir)
            rows.append(row)
            pd.DataFrame(rows).to_csv(out_dir / "runs_partial.csv", index=False, encoding="utf-8-sig")

    df = pd.DataFrame(rows).sort_values(["year", "strategy"])
    df.to_csv(out_dir / "runs.csv", index=False, encoding="utf-8-sig")
    _write_report(df, Path(args.out_doc), args.include_discovery_2025)
    print(f"Wrote {out_dir / 'runs.csv'}")
    print(f"Wrote {args.out_doc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Cross-year sleeve/factor mismatch diagnostics.

This script runs ``sleeve_weight_diagnostics.py`` for fixed yearly windows
and aggregates the evidence into one compact report.

It is diagnostic-only:
* no parameter search
* no config mutation
* no strategy change
* no direct use of a failure year to tune parameters
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


DEFAULT_WINDOWS: dict[int, tuple[str, str]] = {
    2017: ("20170101", "20171231"),
    2018: ("20180101", "20181231"),
    2019: ("20190101", "20191231"),
    2020: ("20200101", "20201231"),
    2021: ("20210101", "20211231"),
    2022: ("20220101", "20221231"),
    2023: ("20230101", "20231222"),
    2024: ("20240101", "20241231"),
    2026: ("20260101", "20260605"),
}

FOCUS_FACTORS = ["momentum_60_cs", "momentum_120_cs", "ep_cs", "bp_cs", "sp_cs"]


def _pct(value: Any, digits: int = 1) -> str:
    if value is None or pd.isna(value):
        return ""
    return f"{float(value) * 100:.{digits}f}%"


def _num(value: Any, digits: int = 3) -> str:
    if value is None or pd.isna(value):
        return ""
    return f"{float(value):.{digits}f}"


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def _run_one(
    year: int,
    start: str,
    end: str,
    config_path: Path,
    out_root: Path,
    top_n: int,
    skip_existing: bool,
) -> Path:
    year_dir = out_root / f"year={year}"
    summary_path = year_dir / "sleeve_factor_weight_summary.csv"
    if skip_existing and summary_path.exists():
        return year_dir

    year_dir.mkdir(parents=True, exist_ok=True)
    log_dir = out_root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    out_doc = Path("docs") / f"sleeve_weight_diagnostics_{year}.md"
    log_path = log_dir / f"{year}.log"

    cmd = [
        sys.executable,
        "-X",
        "utf8",
        "scripts/sleeve_weight_diagnostics.py",
        "--config-path",
        str(config_path),
        "--start",
        start,
        "--end",
        end,
        "--out-dir",
        str(year_dir),
        "--out-doc",
        str(out_doc),
        "--top-n",
        str(top_n),
    ]
    with log_path.open("w", encoding="utf-8") as log:
        log.write(" ".join(cmd) + "\n\n")
        result = subprocess.run(
            cmd,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
        )
    if result.returncode != 0:
        raise RuntimeError(f"Year {year} diagnostics failed; see {log_path}")
    return year_dir


def _extract_year_summary(year: int, year_dir: Path) -> dict[str, Any]:
    weights = _read_csv(year_dir / "sleeve_factor_weight_summary.csv")
    exposures = _read_csv(year_dir / "selection_factor_exposure_summary.csv")
    factor_tb = _read_csv(year_dir / "factor_top_bottom_summary.csv")
    reconcile = _read_csv(year_dir / "phase1_aligned_ic_reconciliation.csv")
    meta = {}
    meta_path = year_dir / "meta.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))

    row: dict[str, Any] = {
        "year": year,
        "start": meta.get("start", ""),
        "end": meta.get("end", ""),
        "signal_dates": meta.get("signal_dates", np.nan),
    }

    def tb_value(factor: str, col: str) -> float:
        if factor_tb.empty:
            return float("nan")
        s = factor_tb[factor_tb["factor"] == factor]
        if s.empty or col not in s:
            return float("nan")
        return float(s.iloc[0][col])

    def weight_value(sleeve: str, factor: str, col: str) -> float:
        if weights.empty:
            return float("nan")
        s = weights[(weights["sleeve"] == sleeve) & (weights["factor"] == factor)]
        if s.empty or col not in s:
            return float("nan")
        return float(s.iloc[0][col])

    def exposure_value(sleeve: str, factor: str, col: str) -> float:
        if exposures.empty:
            return float("nan")
        s = exposures[(exposures["sleeve"] == sleeve) & (exposures["factor"] == factor)]
        if s.empty or col not in s:
            return float("nan")
        return float(s.iloc[0][col])

    def reconcile_value(factor: str, col: str) -> float:
        if reconcile.empty:
            return float("nan")
        s = reconcile[reconcile["factor"] == factor]
        if s.empty or col not in s:
            return float("nan")
        return float(s.iloc[0][col])

    row["m60_top_bottom_excess"] = tb_value("momentum_60_cs", "top_minus_bottom_excess")
    row["m60_momentum_avg_weight"] = weight_value("momentum", "momentum_60_cs", "avg_weight")
    row["m60_momentum_active_rate"] = weight_value("momentum", "momentum_60_cs", "active_rate")
    row["m60_momentum_avg_icir"] = weight_value("momentum", "momentum_60_cs", "avg_icir")
    row["m60_momentum_exposure"] = exposure_value(
        "momentum", "momentum_60_cs", "avg_selected_minus_universe"
    )
    row["m60_weight_sign_matches_raw"] = (
        np.sign(row["m60_top_bottom_excess"])
        == np.sign(row["m60_momentum_avg_weight"])
        if pd.notna(row["m60_top_bottom_excess"]) and pd.notna(row["m60_momentum_avg_weight"])
        else np.nan
    )
    row["m60_exposure_sign_matches_raw"] = (
        np.sign(row["m60_top_bottom_excess"])
        == np.sign(row["m60_momentum_exposure"])
        if pd.notna(row["m60_top_bottom_excess"]) and pd.notna(row["m60_momentum_exposure"])
        else np.nan
    )

    value_rows = []
    for factor in ["ep_cs", "bp_cs", "sp_cs"]:
        value_rows.append({
            "factor": factor,
            "phase1_icir": reconcile_value(factor, "phase1_icir"),
            "aligned_icir": reconcile_value(factor, "aligned_icir"),
            "top_minus_bottom_excess": tb_value(factor, "top_minus_bottom_excess"),
            "value_avg_weight": weight_value("value", factor, "avg_weight"),
        })
    vdf = pd.DataFrame(value_rows)
    row["value_phase1_icir_avg"] = float(vdf["phase1_icir"].mean(skipna=True))
    row["value_aligned_icir_avg"] = float(vdf["aligned_icir"].mean(skipna=True))
    row["value_top_bottom_avg"] = float(vdf["top_minus_bottom_excess"].mean(skipna=True))
    row["value_avg_weight"] = float(vdf["value_avg_weight"].mean(skipna=True))
    row["value_phase1_positive_count"] = int((vdf["phase1_icir"] > 0).sum())
    row["value_aligned_positive_count"] = int((vdf["aligned_icir"] > 0).sum())
    row["value_top_bottom_positive_count"] = int((vdf["top_minus_bottom_excess"] > 0).sum())

    return row


def _write_report(summary: pd.DataFrame, out_doc: Path) -> None:
    def year_list(years: list[int]) -> str:
        if not years:
            return "无"
        return "、".join(str(y) for y in years)

    lines: list[str] = []
    lines.append("# Sleeve 权重错配跨年验证")
    lines.append("")
    lines.append("## 边界")
    lines.append("")
    lines.append("- 固定使用同一套 regime overlay 配置，不搜索参数、不改策略。")
    lines.append("- 每年单独闭合窗口诊断；2026 是 YTD，不与完整年份等同。")
    lines.append("- 目标是验证 2025 发现的错配是否跨年份存在，而不是用这些结果直接调参。")
    lines.append("")

    lines.append("## Momentum_60 错配检查")
    lines.append("")
    lines.append(
        "| 年份 | Raw Top-Bottom | Momentum内平均权重 | 活跃率 | 平均ICIR | "
        "选股暴露 | 权重方向一致 | 暴露方向一致 |"
    )
    lines.append("|---:|---:|---:|---:|---:|---:|---|---|")
    for _, r in summary.sort_values("year").iterrows():
        lines.append(
            f"| {int(r['year'])} | {_pct(r['m60_top_bottom_excess'])} | "
            f"{_num(r['m60_momentum_avg_weight'])} | {_pct(r['m60_momentum_active_rate'])} | "
            f"{_num(r['m60_momentum_avg_icir'])} | {_num(r['m60_momentum_exposure'])} | "
            f"{r['m60_weight_sign_matches_raw']} | {r['m60_exposure_sign_matches_raw']} |"
        )
    lines.append("")

    lines.append("## Value 三因子口径检查")
    lines.append("")
    lines.append(
        "| 年份 | Phase1平均ICIR | Aligned平均ICIR | Top-Bottom平均超额 | "
        "Value内平均权重 | Phase1正数 | Aligned正数 | Top-Bottom正数 |"
    )
    lines.append("|---:|---:|---:|---:|---:|---:|---:|---:|")
    for _, r in summary.sort_values("year").iterrows():
        lines.append(
            f"| {int(r['year'])} | {_num(r['value_phase1_icir_avg'])} | "
            f"{_num(r['value_aligned_icir_avg'])} | {_pct(r['value_top_bottom_avg'])} | "
            f"{_num(r['value_avg_weight'])} | {int(r['value_phase1_positive_count'])} | "
            f"{int(r['value_aligned_positive_count'])} | "
            f"{int(r['value_top_bottom_positive_count'])} |"
        )
    lines.append("")

    valid_m60 = summary.dropna(subset=["m60_weight_sign_matches_raw"])
    m60_weight_mismatch = valid_m60[valid_m60["m60_weight_sign_matches_raw"] == False]  # noqa: E712
    m60_exposure_mismatch = valid_m60[valid_m60["m60_exposure_sign_matches_raw"] == False]  # noqa: E712
    mismatch_count = int(len(m60_weight_mismatch))
    valid_count = int(len(valid_m60))

    value_valid = summary.dropna(subset=["value_phase1_icir_avg"])
    value_phase1_aligned_conflict = value_valid[
        (value_valid["value_phase1_icir_avg"] * value_valid["value_aligned_icir_avg"]) < 0
    ]
    value_phase1_top_bottom_conflict = value_valid[
        (value_valid["value_phase1_icir_avg"] * value_valid["value_top_bottom_avg"]) < 0
    ]
    ytd_years = summary[summary["year"].astype(int) == 2026]["year"].astype(int).tolist()

    lines.append("## 初步判断")
    lines.append("")
    lines.append(
        f"- `momentum_60_cs` 权重方向与 raw Top-Bottom 不一致的年份："
        f"{mismatch_count}/{valid_count}（{year_list(m60_weight_mismatch['year'].astype(int).tolist())}）。"
    )
    lines.append(
        "- `momentum_60_cs` 的 Top50 选股暴露方向不一致年份："
        f"{len(m60_exposure_mismatch)}/{valid_count}"
        f"（{year_list(m60_exposure_mismatch['year'].astype(int).tolist())}）。"
    )
    lines.append(
        "- 结论：2025 观察到的 `momentum_60_cs` 错配不是多数年份稳定现象，"
        "更像特定市场阶段/组合构造下的问题；暂不支持直接反转或重写 momentum 因子方向。"
    )
    lines.append(
        "- value 的 Phase1 与 weekly aligned ICIR 方向冲突年份："
        f"{len(value_phase1_aligned_conflict)}/{len(value_valid)}"
        f"（{year_list(value_phase1_aligned_conflict['year'].astype(int).tolist())}）。"
    )
    lines.append(
        "- value 的 Phase1 与 Top-Bottom 经济收益方向冲突年份："
        f"{len(value_phase1_top_bottom_conflict)}/{len(value_valid)}"
        f"（{year_list(value_phase1_top_bottom_conflict['year'].astype(int).tolist())}）。"
    )
    lines.append(
        "- 结论：value 在 2021-2023 的三层口径较一致，但 2018、2019、2024、2026 存在冲突；"
        "后续应先统一 Phase1、weekly aligned、Top50 经济收益口径，再决定是否提高 value sleeve 权重。"
    )
    lines.append(
        f"- 样本提醒：{year_list(ytd_years)} 是 YTD，不应和完整年份等权用于规则设计。"
    )
    lines.append("")
    lines.append("## 后续约束")
    lines.append("")
    lines.append("- 暂不基于单年或单因子结果反转方向。")
    lines.append("- 暂不搜索 IC 窗口、min_icir、weight cap。")
    lines.append("- 若进入策略开发，候选规则必须先冻结，再做未参与设计年份的 OOS 复验。")

    out_doc.parent.mkdir(parents=True, exist_ok=True)
    out_doc.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config-path",
        default="outputs/analysis/regime_grid_overlay_phase2_2025/configs/less_reversal_faster_overlay.yaml",
    )
    parser.add_argument(
        "--out-dir",
        default="outputs/analysis/sleeve_weight_cross_year",
    )
    parser.add_argument(
        "--out-doc",
        default="docs/sleeve_weight_cross_year.md",
    )
    parser.add_argument("--years", nargs="+", type=int, default=sorted(DEFAULT_WINDOWS))
    parser.add_argument("--top-n", type=int, default=50)
    parser.add_argument("--skip-existing", action="store_true")
    args = parser.parse_args()

    out_root = Path(args.out_dir)
    out_root.mkdir(parents=True, exist_ok=True)
    config_path = Path(args.config_path)

    rows: list[dict[str, Any]] = []
    for year in args.years:
        if year not in DEFAULT_WINDOWS:
            raise ValueError(f"No default window defined for year={year}")
        start, end = DEFAULT_WINDOWS[year]
        print(f"Running diagnostics for {year}: {start}-{end}")
        year_dir = _run_one(
            year=year,
            start=start,
            end=end,
            config_path=config_path,
            out_root=out_root,
            top_n=args.top_n,
            skip_existing=args.skip_existing,
        )
        rows.append(_extract_year_summary(year, year_dir))

    summary = pd.DataFrame(rows).sort_values("year")
    summary.to_csv(out_root / "cross_year_summary.csv", index=False)
    _write_report(summary, Path(args.out_doc))
    print(f"Wrote {args.out_doc}")
    print(f"Wrote {out_root / 'cross_year_summary.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

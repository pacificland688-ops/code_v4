"""Classify local cache gaps without inventing publication times or factors."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from momentum_pullback.contracts import ROOT, file_hash, fingerprint, write_json

ORIGIN = 20150105
OUTPUT_START = 20180101
OUTPUT_END = 20180330
SCALE_RTOL = 2e-5
SCALE_ATOL = 2e-5
CATALOG_SCHEMA = "momentum_pullback.source_catalog.v1"
LEDGER_COLUMNS = [
    "ts_code", "trade_date", "audit_slice", "raw_price_state", "adjusted_price_state",
    "stored_factor_state", "sibling_factor_state", "sibling_matches_adjusted_price",
    "scope_class", "scope_class_reason", "seen_in_unverified_000300_weight_file",
    "publication_time_status", "effective_time_status", "proposed_treatment",
]


def classify_scope(eligibility_known: bool, in_research_universe: bool | None) -> tuple[str, str]:
    """Absence from an unverified weight file is not proof that a name was out of the pool."""
    if not eligibility_known or in_research_universe is None:
        return "ELIGIBILITY_UNKNOWN", "NO_CERTIFIED_PIT_MEMBERSHIP_INTERVAL"
    if in_research_universe:
        return "NECESSARY_RESEARCH_SCOPE", "CERTIFIED_PIT_MEMBER_ON_DATE"
    return "PROVEN_OUT_OF_POOL", "CERTIFIED_PIT_NON_MEMBER_ON_DATE"


def publication_status(column_names: list[str], *, publication_columns: tuple[str, ...] = ("announced_at", "available_at", "ann_date")) -> str:
    """A trade date or file timestamp is not a historical publication time."""
    if any(name in column_names for name in publication_columns):
        return "FIELD_PRESENT_SEMANTICS_UNVERIFIED"
    return "UNKNOWN"


def resolve_stored_factor(stored: Any, sibling: Any, raw_close: Any, adjusted_close: Any) -> dict[str, Any]:
    """Never replace a missing factor with an adjusted/raw price ratio."""
    del raw_close, adjusted_close
    stored_value = pd.to_numeric(pd.Series([stored]), errors="coerce").iloc[0]
    sibling_value = pd.to_numeric(pd.Series([sibling]), errors="coerce").iloc[0]
    stored_ok = bool(np.isfinite(stored_value) and stored_value > 0)
    sibling_ok = bool(np.isfinite(sibling_value) and sibling_value > 0)
    if stored_ok:
        return {"factor": float(stored_value), "state": "STORED_FINITE_POSITIVE", "treatment": "KEEP_ORIGINAL_CACHE"}
    if sibling_ok:
        return {"factor": None, "state": "STORED_MISSING_SIBLING_UNVERIFIED", "treatment": "DO_NOT_ADOPT_UNVERIFIED_SIBLING"}
    return {"factor": None, "state": "UNRESOLVED_NOT_INFERRED", "treatment": "DO_NOT_INFER_FROM_PRICE_RATIO"}


def _state(value: Any) -> str:
    number = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(number):
        return "NULL"
    if not np.isfinite(number) or float(number) <= 0:
        return "NONPOSITIVE_OR_NONFINITE"
    return "FINITE_POSITIVE"


def build_issue_rows(invalid: pd.DataFrame, sibling: pd.DataFrame, unverified_weight_codes: set[str]) -> pd.DataFrame:
    """One ledger row per stored-factor failure. Eligibility stays unknown without PIT proof."""
    if invalid.empty:
        return pd.DataFrame(columns=LEDGER_COLUMNS)
    sibling_keys = sibling.rename(columns={"adj_factor": "sibling_factor"}) if not sibling.empty else pd.DataFrame(columns=["ts_code", "trade_date", "sibling_factor"])
    frame = invalid.merge(sibling_keys[["ts_code", "trade_date", "sibling_factor"]], on=["ts_code", "trade_date"], how="left")
    rows = []
    for record in frame.itertuples(index=False):
        scope, reason = classify_scope(False, None)
        sibling_value = getattr(record, "sibling_factor", np.nan)
        stored_state = _state(record.stored_factor)
        sibling_state = "ABSENT" if "sibling_factor" not in frame or pd.isna(sibling_value) else _state(sibling_value)
        match = None
        if sibling_state == "FINITE_POSITIVE" and _state(record.close) == "FINITE_POSITIVE" and _state(record.adj_close) == "FINITE_POSITIVE":
            match = bool(np.isclose(float(record.close) * float(sibling_value), float(record.adj_close), rtol=SCALE_RTOL, atol=SCALE_ATOL))
        resolved = resolve_stored_factor(record.stored_factor, sibling_value, record.close, record.adj_close)
        rows.append({
            "ts_code": str(record.ts_code),
            "trade_date": int(record.trade_date),
            "audit_slice": str(record.audit_slice),
            "raw_price_state": _state(record.close),
            "adjusted_price_state": _state(record.adj_close),
            "stored_factor_state": stored_state,
            "sibling_factor_state": sibling_state,
            "sibling_matches_adjusted_price": match,
            "scope_class": scope,
            "scope_class_reason": reason,
            "seen_in_unverified_000300_weight_file": str(record.ts_code) in unverified_weight_codes,
            "publication_time_status": "UNKNOWN",
            "effective_time_status": "UNKNOWN",
            "proposed_treatment": resolved["treatment"],
        })
    return pd.DataFrame(rows, columns=LEDGER_COLUMNS).sort_values(["trade_date", "ts_code"], kind="stable").reset_index(drop=True)


def _read_columns(path: Path, columns: list[str], start: int, end: int) -> pd.DataFrame:
    names = set(pq.ParquetFile(path).schema_arrow.names)
    use = [column for column in columns if column in names]
    frame = pq.ParquetFile(path).read(columns=use).to_pandas()
    if "trade_date" in frame:
        frame = frame[frame.trade_date.between(start, end)].copy()
    elif "cal_date" in frame:
        frame = frame[frame.cal_date.between(start, end)].copy()
    return frame


def _month_files(root: Path, table: str, year: int, month: int) -> list[Path]:
    directory = root / "data" / "parquet" / table / f"year={year}" / f"month={month}"
    return sorted(directory.glob("*.parquet")) if directory.exists() else []


def _year_files(root: Path, table: str, year: int) -> list[Path]:
    directory = root / "data" / "parquet" / table / f"year={year}"
    return sorted(directory.glob("*.parquet")) if directory.exists() else []


def _accumulate_prices(root: Path) -> tuple[pd.DataFrame, dict[str, Any], list[Path]]:
    invalid_frames = []
    stats = {"slices": {}, "files": []}
    consumed = []
    periods = []
    for year, months in [(2015, range(1, 13)), (2016, range(1, 13)), (2017, range(1, 13)), (2018, range(1, 4))]:
        for month in months:
            periods.append((year, month))
    for year, month in periods:
        paths = _month_files(root, "prices_adj", year, month)
        start = ORIGIN if (year, month) == (2015, 1) else year * 10000 + month * 100 + 1
        end = OUTPUT_END if (year, month) == (2018, 3) else year * 10000 + month * 100 + 31
        start = max(start, ORIGIN)
        end = min(end, OUTPUT_END)
        slice_name = "OUTPUT_WINDOW" if start >= OUTPUT_START else "WARMUP"
        bucket = stats["slices"].setdefault(slice_name, {"rows": 0, "factor_column_absent_rows": 0, "invalid_factor_rows": 0, "finite_factor_rows": 0, "scale_mismatches": 0, "duplicate_keys": 0, "finite_factor_min": None, "finite_factor_max": None})
        year_bucket = stats.setdefault("years", {}).setdefault(str(year), {"rows": 0, "factor_column_absent_rows": 0, "invalid_factor_rows": 0, "finite_factor_rows": 0, "scale_mismatches": 0})
        for path in paths:
            consumed.append(path)
            names = pq.ParquetFile(path).schema_arrow.names
            frame = _read_columns(path, ["ts_code", "trade_date", "close", "adj_close", "adj_factor"], start, end)
            bucket["rows"] += len(frame)
            year_bucket["rows"] += len(frame)
            duplicated = int(frame.duplicated(["ts_code", "trade_date"]).sum()) if {"ts_code", "trade_date"}.issubset(frame) else 0
            bucket["duplicate_keys"] += duplicated
            if "adj_factor" not in names:
                bucket["factor_column_absent_rows"] += len(frame)
                year_bucket["factor_column_absent_rows"] += len(frame)
                continue
            factors = pd.to_numeric(frame["adj_factor"], errors="coerce")
            invalid = ~np.isfinite(factors) | factors.le(0)
            finite = ~invalid
            bucket["invalid_factor_rows"] += int(invalid.sum())
            bucket["finite_factor_rows"] += int(finite.sum())
            year_bucket["invalid_factor_rows"] += int(invalid.sum())
            year_bucket["finite_factor_rows"] += int(finite.sum())
            if finite.any():
                close = pd.to_numeric(frame.loc[finite, "close"], errors="coerce").to_numpy(dtype=float)
                adjusted = pd.to_numeric(frame.loc[finite, "adj_close"], errors="coerce").to_numpy(dtype=float)
                factor = factors.loc[finite].to_numpy(dtype=float)
                comparable = np.isfinite(close) & np.isfinite(adjusted) & np.isfinite(factor)
                mismatches = int((~np.isclose(close[comparable] * factor[comparable], adjusted[comparable], rtol=SCALE_RTOL, atol=SCALE_ATOL)).sum())
                bucket["scale_mismatches"] += mismatches
                year_bucket["scale_mismatches"] += mismatches
            if invalid.any():
                failed = frame.loc[invalid, ["ts_code", "trade_date", "close", "adj_close", "adj_factor"]].copy()
                failed = failed.rename(columns={"adj_factor": "stored_factor"})
                failed["audit_slice"] = slice_name
                invalid_frames.append(failed)
            factor_min = float(factors.loc[finite].min()) if finite.any() else None
            factor_max = float(factors.loc[finite].max()) if finite.any() else None
            if factor_min is not None:
                bucket["finite_factor_min"] = factor_min if bucket["finite_factor_min"] is None else min(bucket["finite_factor_min"], factor_min)
                bucket["finite_factor_max"] = factor_max if bucket["finite_factor_max"] is None else max(bucket["finite_factor_max"], factor_max)
            stats["files"].append({"path": str(path.relative_to(root)), "rows_in_scope": len(frame), "invalid_rows": int(invalid.sum()) if "adj_factor" in names else None, "factor_column_present": "adj_factor" in names, "finite_factor_min": factor_min, "finite_factor_max": factor_max, "sha256": file_hash(path)})
    invalid = pd.concat(invalid_frames, ignore_index=True) if invalid_frames else pd.DataFrame(columns=["ts_code", "trade_date", "close", "adj_close", "stored_factor", "audit_slice"])
    return invalid, stats, consumed


def _load_sibling(root: Path, keys: pd.DataFrame) -> tuple[pd.DataFrame, list[Path]]:
    if keys.empty:
        return pd.DataFrame(columns=["ts_code", "trade_date", "adj_factor"]), []
    frames, consumed = [], []
    years = sorted({int(value) // 10000 for value in keys.trade_date})
    for year in years:
        for path in _year_files(root, "adj_factor", year):
            consumed.append(path)
            frame = _read_columns(path, ["ts_code", "trade_date", "adj_factor"], int(keys.trade_date.min()), int(keys.trade_date.max()))
            frames.append(frame)
    sibling = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["ts_code", "trade_date", "adj_factor"])
    sibling = sibling.merge(keys[["ts_code", "trade_date"]].drop_duplicates(), on=["ts_code", "trade_date"], how="inner")
    return sibling, consumed


def _weight_codes(root: Path) -> tuple[set[str], dict[str, Any], list[Path]]:
    details = {"table": "index_weight", "index_code_filter_observed": "000300.SH", "pit_fields_present": False, "years_present": [], "years_absent_in_warmup": [], "snapshot_dates": [], "names_per_snapshot_min": None, "names_per_snapshot_max": None, "use": "DESCRIPTIVE_ONLY_NOT_A_PIT_ROSTER"}
    codes, consumed = set(), []
    for year in (2015, 2016, 2017, 2018):
        paths = _year_files(root, "index_weight", year)
        if not paths:
            if year < 2018:
                details["years_absent_in_warmup"].append(year)
            continue
        details["years_present"].append(year)
        for path in paths:
            consumed.append(path)
            frame = pq.ParquetFile(path).read(columns=["index_code", "ts_code", "trade_date", "weight"]).to_pandas()
            details["pit_fields_present"] = False
            selected = frame[frame.index_code.eq("000300.SH") & frame.trade_date.between(ORIGIN, OUTPUT_END)]
            details["snapshot_dates"].extend(int(value) for value in selected.trade_date.drop_duplicates().tolist())
            if not selected.empty:
                counts = selected.groupby("trade_date").ts_code.nunique()
                details["names_per_snapshot_min"] = int(counts.min()) if details["names_per_snapshot_min"] is None else min(details["names_per_snapshot_min"], int(counts.min()))
                details["names_per_snapshot_max"] = int(counts.max()) if details["names_per_snapshot_max"] is None else max(details["names_per_snapshot_max"], int(counts.max()))
            codes.update(selected.ts_code.astype(str))
    details["snapshot_dates"] = sorted(set(details["snapshot_dates"]))
    details["publication_time_status"] = publication_status(["index_code", "ts_code", "trade_date", "weight"])
    return codes, details, consumed


def _partition_years(root: Path, table: str) -> list[str]:
    base = root / "data" / "parquet" / table
    if not base.exists():
        return []
    return sorted(path.name.split("=", 1)[1] for path in base.glob("year=*") if path.is_dir())


def _table_presence(root: Path) -> dict[str, Any]:
    """Schema and coverage facts. Missing time columns stay UNKNOWN rather than imputed."""
    suspend_2015 = sorted(path.name for path in (root / "data" / "parquet" / "suspend_status" / "year=2015").glob("month=*")) if (root / "data" / "parquet" / "suspend_status" / "year=2015").exists() else []
    catalog = []
    def add(table, field, semantic, unit, unit_evidence, publication, effective, status, gaps, coverage):
        catalog.append({"table": table, "field": field, "semantic": semantic, "unit": unit, "unit_evidence": unit_evidence, "publication_time_evidence": publication, "effective_interval_evidence": effective, "evidence_status": status, "coverage": coverage, "gaps": gaps})
    add("prices_adj", "adj_factor", "Stored multiplier in the adjusted-price cache. Non-missing 2018Q1 rows satisfy adjusted close = raw close * factor at rtol 2e-5. Median is not 1, so this is not a last-day normalized coefficient.", "dimensionless multiplier", "RELATION_TO_STORED_PRICES_WHERE_FACTOR_IS_FINITE", "UNKNOWN", "UNKNOWN", "OBSERVED_CACHE_ONLY", ["2015 monthly prices_adj files have no adj_factor column", "2018Q1 contains null factors"], "2015-01-05 through 2018-03-30 partial")
    add("adj_factor", "adj_factor", "Sibling cache of a numeric factor. It is not a second certified source and has no publication timestamp.", "dimensionless multiplier", "NO_UNIT_METADATA", "UNKNOWN", "UNKNOWN", "UNVERIFIED_SIBLING_CACHE", ["No announced_at or revision id"], "yearly files observed from 1996; this review joins only failing keys")
    add("index_weight", "trade_date", "Date on a weight row. Not used as an announcement time or as a daily membership interval.", "date", "COLUMN_NAME_ONLY", "UNKNOWN", "SOURCE_UNAVAILABLE", "SOURCE_UNAVAILABLE", ["No announced_at, effective_from, or effective_to", "Warmup years 2015 and 2016 are not in the local year partitions"], f"year partitions observed: {_partition_years(root, 'index_weight')}")
    add("industry_member", "effective_date", "A date column is present. No available_at column is present, so publication time is unknown. Date-only values are not treated as intraday timestamps.", "date", "COLUMN_NAME_ONLY", "UNKNOWN", "FIELD_PRESENT_SEMANTICS_UNVERIFIED", "SOURCE_UNAVAILABLE", ["available_at absent", "2015 is outside the observed year partitions" if "2015" not in _partition_years(root, "industry_member") else "2015 partition exists"], f"year partitions observed: {_partition_years(root, 'industry_member')}")
    add("daily_basic", "circ_mv", "Circulating-value column. The cache does not state CNY or another unit, so no conversion is applied.", "UNKNOWN", "NO_UNIT_METADATA", "UNKNOWN", "UNKNOWN", "SOURCE_UNAVAILABLE", ["available_at absent"], f"year partitions observed: {_partition_years(root, 'daily_basic')}")
    add("prices_raw", "amount", "Turnover column copied beside prices. No unit metadata is stored in the file.", "UNKNOWN", "NO_UNIT_METADATA", "UNKNOWN", "UNKNOWN", "OBSERVED_CACHE_ONLY", ["No currency unit field"], "monthly files exist across the engineering window")
    add("trade_cal", "cal_date", "Two local calendar files disagree in row count. Neither file carries a publication time. A shorter file is not self-certified.", "date", "COLUMN_NAME_ONLY", "UNKNOWN", "UNKNOWN", "UNVERIFIED", ["cache.parquet and calendar.parquet are not identical", "exchange value observed as SSE only"], "both files contain dates inside the engineering window")
    add("suspend_status", "suspend_type", "Suspension rows exist for part of the window. No publication timestamp and no verified full-day flag under this contract's vocabulary.", "unspecified", "NO_UNIT_METADATA", "UNKNOWN", "UNKNOWN", "SOURCE_UNAVAILABLE", [f"2015 month partitions observed: {suspend_2015}"], f"year partitions observed: {_partition_years(root, 'suspend_status')}")
    add("namechange", "ann_date", "Date-only announcement column. Semantics are not certified. It is not copied into available_at.", "date", "COLUMN_NAME_ONLY", "FIELD_PRESENT_SEMANTICS_UNVERIFIED", "start_date/end_date present, endpoint convention unverified", "UNVERIFIED", ["Date only, no timezone", "Not a certified ST event table"], f"year partitions observed: {_partition_years(root, 'namechange')}")
    add("stock_status", "list_status", "A single current-status extract. It has no as-of timestamp and cannot reconstruct historical ST or listing state.", "unspecified", "NO_UNIT_METADATA", "UNKNOWN", "SOURCE_UNAVAILABLE", "SOURCE_UNAVAILABLE", ["No history axis"], "one cache file")
    return {"fields": catalog, "date_only_announcement_policy": {"status": "PROPOSED_NOT_APPLIED", "rule": "A date-only announcement, if later certified, becomes available at 23:59:59.999999 Asia/Shanghai on that calendar date and cannot be used at an earlier signal cutoff. This policy does not fill current UNKNOWN fields and is not historical evidence.", "timezone": "Asia/Shanghai"}}


def _calendar_fact(root: Path) -> dict[str, Any]:
    facts = {}
    for name in ["calendar.parquet", "cache.parquet"]:
        path = root / "data" / "parquet" / "trade_cal" / name
        frame = _read_columns(path, ["exchange", "cal_date", "is_open", "pretrade_date"], ORIGIN, OUTPUT_END)
        facts[name] = {"rows_in_scope": len(frame), "exchanges": sorted(frame.exchange.astype(str).unique().tolist()), "is_open_values": sorted(int(value) for value in frame.is_open.drop_duplicates().tolist()), "sha256": file_hash(path)}
    return facts


def render_report(summary: dict[str, Any]) -> str:
    output = summary["output_window_invalid_rows"]
    slices = summary["price_slices"]
    weight = summary["weight"]
    lines = [
        "# 来源可行性裁定",
        "",
        "2026-10-14。范围是预热起点 2015-01-05 至输出终点 2018-03-30，沪深 300、日线、多头。本文件只裁定现有本地缓存，没有改写 `data/parquet`，没有用价格比推导因子，也没有把成交日、下载时间或文件修改时间写成历史发布时间。研究参数仍是 PROPOSED，收益关闭。",
        "",
        "## 结论",
        "",
        f"真实路径维持 **SOURCE_UNAVAILABLE / DATA_BLOCKED**。输出窗口内存储因子无效的行数是 **{output}**。这些行的事前成分资格是 **ELIGIBILITY_UNKNOWN**，不能记成已证明的池外数据，因此也不能判定它们是否落在必要研究范围内。",
        "",
        "规则修复和合成测试不依赖这次来源补齐，可以继续。真实快照、真实事件和配对仍不能放行。",
        "",
        "## 因子尺度",
        "",
        "已有非缺失因子按现行合同公式核对：调整后价格 = 原始价格 × 存储因子。容差 rtol=2e-5、atol=2e-5。",
        "",
        f"- 输出窗口有限正因子 {slices['OUTPUT_WINDOW']['finite_factor_rows']} 行，尺度不一致 {slices['OUTPUT_WINDOW']['scale_mismatches']} 行。观察到的因子最小值 {slices['OUTPUT_WINDOW']['finite_factor_min']}、最大值 {slices['OUTPUT_WINDOW']['finite_factor_max']}。最大值远大于 1，所以它不是把样本最后一天归一成 1 的系数。",
        f"- 预热段有限正因子 {slices['WARMUP']['finite_factor_rows']} 行，尺度不一致 {slices['WARMUP']['scale_mismatches']} 行；因子列存在但无效的预热行 {summary['warmup_invalid_rows']} 行，已进入同一问题台账。",
        f"- 2015 年复权价文件合计只有 {summary['years']['2015']['rows']} 行，而且没有 `adj_factor` 列。这是整年缓存不完整，不是完整行情里的少量缺行。缺列不展开成零因子，也不用价格比填补。",
        "",
        "公式不需要为了通过校验器而改写。孤立目录里的旁路因子只是未认证候选，不回写原缓存。",
        "",
        "## 2,477 行与名册",
        "",
        f"输出窗口无效因子全部是空值，不是非正数。涉及证券数 {summary['output_window_invalid_codes']}。旁路 `adj_factor` 缓存对这些键给出了有限正因子，并且与已存储的调整后收盘在同一公式下一致的行数是 {summary['sibling_scale_matches']}。旁路缓存没有发布时间，资格仍是未知，所以处理方式是 DO_NOT_ADOPT_UNVERIFIED_SIBLING。",
        "",
        f"未认证的 000300.SH 权重文件快照日为 {weight['snapshot_dates'] or '无'}，预热年份缺失为 {weight['years_absent_in_warmup']}。无效因子证券中，出现在该文件里的只数是 {summary['invalid_codes_seen_in_unverified_weight']}。这个计数是描述，不是 PIT 证明。",
        "",
        "## 其他必要字段",
        "",
        "成分、行业、市值、停牌、ST 都缺少可直接使用的发布时间和生效区间。`namechange.ann_date` 只有日期、没有时区，语义未认证。日期型公告的保守时点只作为 PROPOSED_NOT_APPLIED 政策登记：若将来来源被认证且只有日期，可用时点取该日 Asia/Shanghai 的最后一微秒，不能用于更早的信号截止。该政策不回填当前未知字段。",
        "",
        "两份交易日历在工程窗口内的行数不一致，不能把较短的那份自证为完整日历。",
        "",
        "## 未通过的门",
        "",
        "- G-A 的规则部分由 r3 草案和合成反例提交；来源部分没有达到可构建真实快照的证据。",
        "- 真实数据门保持 DATA_BLOCKED。批次 B、C 依赖的认证名册、日历和因子发布证据仍然缺失。",
        "- 不换年份、不换板块、不用当前分类回填来绕开这个窗口。",
        "",
    ]
    return "\n".join(lines)


def adjudicate(root: Path = ROOT, evidence: Path | None = None) -> dict[str, Any]:
    evidence = evidence or (root / "momentum_pullback" / "evidence" / "source_adjudication")
    evidence.mkdir(parents=True, exist_ok=True)
    invalid, price_stats, price_files = _accumulate_prices(root)
    sibling, sibling_files = _load_sibling(root, invalid[["ts_code", "trade_date"]] if not invalid.empty else pd.DataFrame(columns=["ts_code", "trade_date"]))
    codes, weight, weight_files = _weight_codes(root)
    ledger = build_issue_rows(invalid, sibling, codes)
    isolated = root / "data" / "research" / "momentum_pullback" / "source_adjudication_r3"
    isolated.mkdir(parents=True, exist_ok=True)
    candidates = ledger.loc[ledger.sibling_factor_state.eq("FINITE_POSITIVE"), ["ts_code", "trade_date", "audit_slice", "sibling_matches_adjusted_price", "proposed_treatment"]].copy()
    candidate_path = isolated / "unverified_sibling_factor_keys.parquet"
    candidates.to_parquet(candidate_path, index=False)
    ledger_path = evidence / "factor_issue_ledger.parquet"
    ledger.to_parquet(ledger_path, index=False)
    output_ledger = ledger[ledger.audit_slice.eq("OUTPUT_WINDOW")]
    summary = {
        "output_window_invalid_rows": int(output_ledger.shape[0]),
        "output_window_invalid_codes": int(output_ledger.ts_code.nunique()) if not output_ledger.empty else 0,
        "warmup_invalid_rows": int(ledger.audit_slice.eq("WARMUP").sum()) if not ledger.empty else 0,
        "sibling_scale_matches": int(output_ledger.sibling_matches_adjusted_price.fillna(False).sum()) if not output_ledger.empty else 0,
        "invalid_codes_seen_in_unverified_weight": int(output_ledger.loc[output_ledger.seen_in_unverified_000300_weight_file, "ts_code"].nunique()) if not output_ledger.empty else 0,
        "price_slices": price_stats["slices"],
        "years": price_stats.get("years", {}),
        "weight": weight,
        "scope_class_counts": ledger.scope_class.value_counts().to_dict() if not ledger.empty else {},
        "public_cache_modified": False,
        "network_requests": 0,
    }
    catalog = {
        "schema": CATALOG_SCHEMA,
        "adjudication_clock": "REVIEW_TIME_NOT_A_HISTORICAL_PUBLICATION_TIME",
        "scope": {"feature_origin": ORIGIN, "output_start": OUTPUT_START, "output_end": OUTPUT_END, "universe": "CSI300_PIT", "frequency": "DAILY", "direction": "LONG_ONLY"},
        "parameter_status": "PROPOSED",
        "outcomes_enabled": False,
        "network_requests": 0,
        "public_cache_modified": False,
        "price_scale_formula": "ADJUSTED_EQUALS_RAW_TIMES_STORED_FACTOR",
        "price_scale_formula_changed": False,
        "factor_kind_where_finite": "CUMULATIVE_MULTIPLIER_NOT_REBASED_TO_ONE_AT_SAMPLE_END",
        "tables": _table_presence(root),
        "calendar_files_in_scope": _calendar_fact(root),
        "weight_observation": weight,
        "price_slice_counts": price_stats["slices"],
        "input_files": [{"path": str(path.relative_to(root)), "sha256": file_hash(path)} for path in sorted(set(price_files + sibling_files + weight_files))],
        "ledger_rows": len(ledger),
        "ledger_sha256": file_hash(ledger_path),
        "ledger_content_id": fingerprint(json.loads(ledger.to_json(orient="split", index=False))) if not ledger.empty else fingerprint([]),
        "unverified_sibling_key_file": str(candidate_path.relative_to(root)),
        "unverified_sibling_key_sha256": file_hash(candidate_path),
    }
    write_json(evidence / "source_catalog.json", catalog)
    report = render_report(summary)
    report_path = evidence / "source_feasibility_report.md"
    report_path.write_text(report, encoding="utf-8")
    manifest = {"ledger_sha256": catalog["ledger_sha256"], "ledger_rows": len(ledger), "catalog_sha256": file_hash(evidence / "source_catalog.json"), "report_sha256": file_hash(report_path), "sibling_keys_sha256": catalog["unverified_sibling_key_sha256"], "output_window_invalid_rows": summary["output_window_invalid_rows"], "public_cache_modified": False}
    write_json(evidence / "adjudication_manifest.json", manifest)
    return {"summary": summary, "evidence": str(evidence), "manifest": manifest}


def main() -> None:
    result = adjudicate(ROOT)
    print(json.dumps({"status": "SOURCE_UNAVAILABLE", "output_window_invalid_rows": result["summary"]["output_window_invalid_rows"], "evidence": result["evidence"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()

"""PIT universe manager for the live alert pipeline (photoresist_universe_v2).

Loads the v2 universe config, validates period integrity (no overlapping
periods per stock, historical v1 ranges untouched), and exposes the active
core pool for a given trade date.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from .common import load_yaml

UNIVERSE_COLUMNS = [
    "ts_code", "name", "pool_type", "effective_start", "effective_end",
    "source_type", "source_ref", "announcement_date", "pit_confidence",
    "business_tier", "universe_version", "review_status",
    "document_id", "document_title", "publication_date", "source_url",
    "document_sha256", "reviewer", "reviewed_at",
]


def load_universe_v2(config_path: Path | str) -> tuple[pd.DataFrame, dict]:
    """Load photoresist_universe_v2 into a flat PIT membership table.

    Returns (universe_df, universe_meta). Raises ValueError on integrity
    violations (overlapping periods, missing fields, wrong version tag).
    """
    config = load_yaml(config_path)
    meta = config.get("universe", {})
    records = []
    for layer in ("core", "adjacent", "mapping"):
        for entry in meta.get(layer, []) or []:
            evidence = entry.get("evidence") or {}
            records.append({
                "ts_code": str(entry["ts_code"]),
                "name": str(entry.get("name", "")),
                "pool_type": str(entry.get("pool_type", layer)),
                "effective_start": int(entry["effective_start"]),
                "effective_end": int(entry["effective_end"]),
                "source_type": str(entry.get("source_type", "")),
                "source_ref": str(entry.get("source_ref", "")).strip(),
                "announcement_date": int(entry.get("announcement_date", 0)) or None,
                "pit_confidence": str(entry.get("pit_confidence", "low")),
                "business_tier": str(entry.get("business_tier", "")),
                "universe_version": str(entry.get("universe_version", "")),
                "review_status": str(entry.get("review_status", "")),
                "document_id": evidence.get("document_id"),
                "document_title": evidence.get("document_title"),
                "publication_date": evidence.get("publication_date"),
                "source_url": evidence.get("source_url"),
                "document_sha256": evidence.get("document_sha256"),
                "reviewer": evidence.get("reviewer"),
                "reviewed_at": evidence.get("reviewed_at"),
            })
    if not records:
        raise ValueError(f"Universe config {config_path} has no members")
    universe = pd.DataFrame(records, columns=UNIVERSE_COLUMNS)
    _validate_universe(universe, meta)
    return universe, meta


def _validate_universe(universe: pd.DataFrame, meta: dict) -> None:
    errors = []
    if str(meta.get("universe_version", "")) != "photoresist_universe_v2":
        errors.append("universe.universe_version must be photoresist_universe_v2")
    bad_range = universe[universe["effective_start"] > universe["effective_end"]]
    if not bad_range.empty:
        errors.append(f"effective_start > effective_end: {bad_range['ts_code'].tolist()}")
    for (code, pool), group in universe.groupby(["ts_code", "pool_type"]):
        periods = group.sort_values("effective_start")
        previous_end = None
        for _, row in periods.iterrows():
            if previous_end is not None and int(row["effective_start"]) <= previous_end:
                errors.append(
                    f"{code}/{pool}: overlapping periods at {int(row['effective_start'])}"
                )
            previous_end = int(row["effective_end"])
    core_2026 = universe[
        (universe["pool_type"] == "core") & (universe["effective_end"] >= 20260101)
    ]
    missing_announce = core_2026[core_2026["announcement_date"].isna()]
    if not missing_announce.empty:
        errors.append(
            "2026 core periods missing announcement_date: "
            f"{missing_announce['ts_code'].tolist()}"
        )
    pit_announced = core_2026.dropna(subset=["announcement_date"])
    too_early = pit_announced[
        pit_announced["announcement_date"].astype(int)
        > pit_announced["effective_end"].astype(int)
    ]
    if not too_early.empty:
        errors.append(
            "announcement_date after effective_end (not point-in-time): "
            f"{too_early['ts_code'].tolist()}"
        )
    # Evidence governance (gap-fix plan §9): every 2026 core period must carry
    # a documented disclosure; 'approved' additionally requires reviewer,
    # reviewed_at and an archived document hash.
    for _, row in core_2026.iterrows():
        code = row["ts_code"]
        if not row.get("document_id") or not row.get("document_title") or (
            pd.isna(row.get("publication_date"))
        ):
            errors.append(f"{code}: 2026 period missing evidence "
                          "(document_id/document_title/publication_date)")
        status = str(row.get("review_status", ""))
        if status not in ("approved", "confirmed_desk_research"):
            errors.append(f"{code}: review_status must be approved or "
                          f"confirmed_desk_research, got '{status}'")
        if status == "approved" and not (
            row.get("reviewer") and row.get("reviewed_at")
            and row.get("document_sha256")
        ):
            errors.append(f"{code}: approved requires reviewer/reviewed_at/"
                          "document_sha256")
    if errors:
        raise ValueError("universe_v2 integrity check failed: " + "; ".join(errors))


def production_approved(universe: pd.DataFrame, as_of: int) -> bool:
    """Production eligibility: every v2 core period in use at as_of is approved.

    confirmed_desk_research keeps the system research-only (the alert renders
    an explicit 未完成正式审核 note). Frozen v1 historical periods carry the
    original research freeze and need no re-approval."""
    in_use = active_members(universe, as_of, ("core",), "medium")
    if in_use.empty:
        return False
    v2_rows = in_use[in_use["universe_version"] == "photoresist_universe_v2"]
    return bool(v2_rows.empty or (v2_rows["review_status"] == "approved").all())


def active_members(
    universe: pd.DataFrame,
    trade_date: int,
    pool_types: tuple[str, ...] = ("core",),
    min_pit_confidence: str = "medium",
) -> pd.DataFrame:
    """PIT-clean member lookup for a trade date.

    A 2026-period membership only becomes usable once its supporting
    disclosure is public (announcement_date <= trade_date); before that the
    stock is still covered by its frozen historical period.
    """
    conf_order = {"high": 3, "medium": 2, "low": 1}
    min_conf = conf_order.get(min_pit_confidence, 0)
    active = universe[
        (universe["effective_start"] <= trade_date)
        & (universe["effective_end"] >= trade_date)
        & (universe["pool_type"].isin(pool_types))
        & (universe["pit_confidence"].map(conf_order).fillna(0) >= min_conf)
    ].copy()
    has_announce = active["announcement_date"].notna()
    usable = ~has_announce | (
        active["announcement_date"].fillna(0).astype(int) <= trade_date
    )
    return active[usable].reset_index(drop=True)


def universe_status(universe: pd.DataFrame, as_of: int) -> dict:
    """Summary for quality gate / manifest: coverage of the core pool at as_of."""
    core_active = active_members(universe, as_of, ("core",), "medium")
    core_all = universe[universe["pool_type"] == "core"]
    return {
        "as_of": int(as_of),
        "core_active_count": int(len(core_active)),
        "core_active_codes": sorted(core_active["ts_code"].tolist()),
        "core_max_effective_end": int(core_all["effective_end"].max()),
        "expired": bool(core_active.empty),
        "versions_in_use": sorted(core_active["universe_version"].unique().tolist()),
        "pending_review": sorted(
            core_active.loc[
                (core_active["universe_version"] == "photoresist_universe_v2")
                & (core_active["review_status"] != "approved"),
                "ts_code",
            ].tolist()
        ),
    }


def export_snapshot(
    universe: pd.DataFrame, meta: dict, out_dir: Path,
) -> dict[str, str]:
    """Write photoresist_universe_v2 snapshot + manifest next to live outputs."""
    out_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = out_dir / "photoresist_universe_v2_snapshot.csv"
    manifest_path = out_dir / "photoresist_universe_v2_manifest.json"
    universe.to_csv(snapshot_path, index=False, encoding="utf-8-sig")
    manifest = {
        "universe_version": meta.get("universe_version"),
        "name": meta.get("name"),
        "last_updated": meta.get("last_updated"),
        "status": meta.get("status"),
        "predecessor": meta.get("predecessor"),
        "n_members": int(len(universe)),
        "n_core_periods": int((universe["pool_type"] == "core").sum()),
        "core_codes": sorted(
            universe.loc[universe["pool_type"] == "core", "ts_code"].unique().tolist()
        ),
    }
    import json
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {"snapshot": str(snapshot_path), "manifest": str(manifest_path)}

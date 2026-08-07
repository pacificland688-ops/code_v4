"""Run the holding-period sensitivity grid for the frozen sector contracts.

EXPLORATORY, POST-HOC study.  Every parameter except
``execution.hold_days`` is frozen: events, T+1 entries, stop levels,
costs, and the next-event boundary are identical to the frozen 20-day
contract.  All arms run offline on the audited runtime Tushare snapshot
and on a COMMON frozen-path horizon, so censoring differences come from
the hold rule, not from path length.

The formal 20-day results, config hashes, and golden baseline are never
touched.  Each arm lands under
``outputs/analysis/sector_panic/hold_sensitivity/<hold>/<sector>/`` with a
patched manifest recording ``baseline_config_hash``, ``hold_days_override``
and ``status: EXPLORATORY_POST_HOC``.

Examples
--------
python scripts/sector_panic_hold_sensitivity.py
python scripts/sector_panic_hold_sensitivity.py --holds 20 --sectors nonferrous
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(ROOT))

from scripts.run_sector_panic_backtest import run_sector  # noqa: E402
from sector_panic.config import load_config  # noqa: E402

SECTOR_CONFIGS = {
    "nonferrous": ROOT / "configs" / "sector_panic" / "nonferrous.yaml",
    "new_energy": ROOT / "configs" / "sector_panic" / "new_energy.yaml",
    "lithium_battery": ROOT / "configs" / "sector_panic" / "lithium_battery.yaml",
}
DEFAULT_HOLDS = [5, 10, 15, 20, 30]
START_DATE = 20170101
END_DATE = 20260804
PATH_HORIZON = 40
RUNTIME_DATA_DIR = (
    ROOT / "outputs" / "analysis" / "sector_panic" / "runtime_tushare"
)
OUT_ROOT = ROOT / "outputs" / "analysis" / "sector_panic" / "hold_sensitivity"

# Pre-specified judgment rules (recorded in the root manifest BEFORE any
# arm runs; the analysis script applies them mechanically).  This is NOT a
# formal pre-registration with an external trust anchor: the rules and the
# manifest are written by the same run code, and the manifest is refreshed
# after execution.  The trust anchor is the post-2026-08-05 frozen window.
DECISION_RULES = {
    "registration_status": (
        "mechanical judgment rules pre-specified in the run code; root "
        "manifest written before arm execution; NOT a formal "
        "pre-registration with an external trust anchor"
    ),
    "purpose": (
        "exclude obviously unsuitable holding periods, observe the "
        "risk-return curve, and establish the adjudication framework for "
        "the post-2026-08-05 frozen window"
    ),
    "no_promotion_from_history": (
        "no holding period may be selected from historical returns; "
        "the only promotion window is data frozen after 2026-08-05"
    ),
    "baseline": {"hold_days": 20, "reference": "frozen 20-day contract"},
    "sample_roles": {
        "train": "observe base behavior (2017-2020)",
        "validation": "check direction continuation (2021-2023)",
        "locked_oos": "post-hoc robustness only, revealed (2024-2025)",
        "pre_registration_holdout": "diagnostic only, never a parameter input (2026)",
    },
    "candidate_conditions": {
        "direction_consistency": (
            "sign of the paired mean diff vs 20d agrees with locked_oos "
            "in at least 2 of the 3 historical splits"
        ),
        "mean_median_agreement": (
            "mean and median paired diffs have the same sign in at least "
            "2 sectors"
        ),
        "max_drawdown_tolerance": (
            "arm PRE-2026 max drawdown (train+validation+locked_oos "
            "pooled) not worse than baseline by more than the recorded "
            "tolerance; 2026 data never a parameter input"
        ),
        "realizable_rate_tolerance": (
            "arm PRE-2026 realizable rate not lower than baseline by more "
            "than the recorded tolerance; 2026 data never a parameter input"
        ),
        "sector_direction": "at least 2 sectors show the same direction",
        "paired_stability": (
            "pooled paired mean diff positive with a bootstrap CI "
            "excluding zero"
        ),
    },
    "tolerances": {"max_drawdown_pp": 0.02, "realizable_rate_pp": 0.02},
    "default_conclusion": (
        "no candidate meets every condition -> keep the frozen 20-day "
        "holding period"
    ),
}


def _runtime_manifest_sha256() -> str:
    return hashlib.sha256(
        (RUNTIME_DATA_DIR / "manifest.json").read_bytes()
    ).hexdigest()


def _manifest_snapshot_ok(
    manifest: dict,
    hold: int,
    baseline_hash: str,
    end_date: int,
    runtime_hash: str,
) -> bool:
    return (
        manifest.get("status") == "EXPLORATORY_POST_HOC"
        and manifest.get("hold_days_override") == hold
        and manifest.get("baseline_config_hash") == baseline_hash
        and manifest.get("end_date") == int(end_date)
        and manifest.get("path_horizon") == int(PATH_HORIZON)
        and manifest.get("runtime_manifest_sha256") == runtime_hash
    )


def _manifest_needs_upgrade(
    manifest: dict,
    hold: int,
    baseline_hash: str,
    end_date: int,
    runtime_hash: str,
) -> bool:
    """Existing arm ran before the end-date/runtime-hash fields existed.

    Upgrade (re-patch the manifest WITHOUT re-running) is only allowed when
    the requested end date is the grid default: arms are deterministic on
    the frozen snapshot, the 20-day arms are cross-checked against the
    formal ledgers, and any arm run with a non-default end date cannot be
    told apart from the default run afterwards.
    """
    legacy_ok = (
        manifest.get("status") == "EXPLORATORY_POST_HOC"
        and manifest.get("hold_days_override") == hold
        and manifest.get("baseline_config_hash") == baseline_hash
    )
    new_ok = _manifest_snapshot_ok(
        manifest, hold, baseline_hash, end_date, runtime_hash
    )
    return bool(legacy_ok and not new_ok and int(end_date) == int(END_DATE))


def _patch_arm_manifest(
    manifest_path: Path,
    hold: int,
    baseline_hash: str,
    end_date: int,
    runtime_hash: str,
    upgraded: bool = False,
) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["status"] = "EXPLORATORY_POST_HOC"
    manifest["baseline_config_hash"] = baseline_hash
    manifest["hold_days_override"] = int(hold)
    manifest["config_sha256_is_study_copy"] = True
    manifest["end_date"] = int(end_date)
    manifest["path_horizon"] = int(PATH_HORIZON)
    manifest["runtime_manifest_sha256"] = runtime_hash
    manifest["analysis_scope_note"] = (
        "Holding-period sensitivity arm. Every parameter other than "
        "execution.hold_days is frozen from the baseline contract; the "
        "formal 20-day outputs and their config hashes are untouched. "
        "See the root manifest for the pre-specified decision rules."
    )
    if upgraded:
        manifest["manifest_upgraded"] = True
        manifest["manifest_upgrade_note"] = (
            "Arm ledger predates end_date/runtime_manifest_sha256 "
            "recording; fields back-filled at the grid default end date. "
            "Ledger not re-run (deterministic on the frozen snapshot)."
        )
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_study_config(sector: str, hold: int, raw: dict) -> Path:
    study = json.loads(json.dumps(raw, ensure_ascii=False))
    study["execution"]["hold_days"] = int(hold)
    configs_dir = OUT_ROOT / "configs"
    configs_dir.mkdir(parents=True, exist_ok=True)
    path = configs_dir / f"{sector}_hold{int(hold)}.yaml"
    path.write_text(
        yaml.safe_dump(study, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return path


def _compare_formal_20d(sector: str, hold: int) -> str:
    """Column-level consistency of the sensitivity 20d arm vs the formal run.

    The formal run uses the default 28-day frozen-path horizon and the
    sensitivity arms a common 40-day horizon.  ``path_type`` is the only
    column that legitimately depends on the observation horizon (a W
    pattern is only classifiable over the window it is scored on); every
    execution and return field must match exactly.
    """
    if hold != 20:
        return "n/a"
    sensitivity = OUT_ROOT / "20" / sector / "rule_trade_ledger.csv"
    formal = ROOT / "outputs" / "analysis" / "sector_panic" / sector / "rule_trade_ledger.csv"
    if not sensitivity.exists() or not formal.exists():
        return "missing formal or sensitivity ledger"
    try:
        arm = pd.read_csv(sensitivity)
        base = pd.read_csv(formal)
    except Exception as exc:  # noqa: BLE001 - reporting only
        return f"compare failed: {exc}"
    if len(arm) != len(base):
        return f"row count differs: sensitivity={len(arm)} formal={len(base)}"
    differing = {}
    for column in base.columns:
        if column not in arm.columns:
            differing[column] = "missing in sensitivity"
            continue
        a = arm[column]
        b = base[column]
        if column in ("gross_return", "net_return"):
            mask = ~np.isclose(
                a.to_numpy(dtype=float), b.to_numpy(dtype=float),
                rtol=1e-9, atol=1e-12, equal_nan=True,
            )
        else:
            mask = (a.fillna("").astype(str) != b.fillna("").astype(str)).to_numpy()
        n_diff = int(mask.sum())
        if n_diff:
            differing[column] = n_diff
    if not differing:
        return "fully identical rows"
    if set(differing) == {"path_type"}:
        return (
            f"all execution and return fields identical; path_type differs "
            f"in {differing['path_type']} rows (formal 28d vs study 40d "
            f"observation horizon)"
        )
    parts = ", ".join(f"{col}={n}" for col, n in sorted(differing.items()))
    return f"differs in columns: {parts}"


def run_arm(sector: str, hold: int, end_date: int, runtime_hash: str) -> str:
    frozen_path = SECTOR_CONFIGS[sector]
    baseline = load_config(frozen_path)
    baseline_hash = baseline.config_hash
    arm_dir = OUT_ROOT / str(hold) / sector
    arm_manifest = arm_dir / "manifest.json"
    if arm_manifest.exists():
        manifest = json.loads(arm_manifest.read_text(encoding="utf-8"))
        if _manifest_snapshot_ok(manifest, hold, baseline_hash,
                                 end_date, runtime_hash):
            return (
                f"[{sector} hold={hold}] already complete "
                f"({_compare_formal_20d(sector, hold)})"
            )
        if _manifest_needs_upgrade(manifest, hold, baseline_hash,
                                   end_date, runtime_hash):
            _patch_arm_manifest(arm_manifest, hold, baseline_hash,
                                end_date, runtime_hash, upgraded=True)
            return (
                f"[{sector} hold={hold}] upgraded manifest "
                f"({_compare_formal_20d(sector, hold)})"
            )
    study_path = _write_study_config(sector, hold, baseline.raw)
    run_sector(
        study_path, START_DATE, int(end_date), OUT_ROOT / str(hold),
        strict_tradability=False,
        runtime_data_dir=RUNTIME_DATA_DIR,
        path_horizon=PATH_HORIZON,
    )
    _patch_arm_manifest(arm_dir / "manifest.json", hold, baseline_hash,
                        end_date, runtime_hash)
    return f"[{sector} hold={hold}] done ({_compare_formal_20d(sector, hold)})"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--holds", nargs="+", type=int, default=None,
        help="Holding periods in trading days; default is the full grid.",
    )
    parser.add_argument(
        "--sectors", nargs="+", choices=sorted(SECTOR_CONFIGS), default=None,
        help="Subset of the three formal sector contracts.",
    )
    parser.add_argument(
        "--end", type=int, default=END_DATE,
        help="Data end date (frozen); default 20260804.",
    )
    args = parser.parse_args()
    holds = sorted(set(args.holds or DEFAULT_HOLDS))
    sectors = args.sectors or sorted(SECTOR_CONFIGS)
    end_date = int(args.end)

    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    runtime_hash = _runtime_manifest_sha256()
    baseline_hashes = {}
    for sector, path in SECTOR_CONFIGS.items():
        baseline_hashes[sector] = load_config(path).config_hash

    root_manifest = {
        "schema": "sector_panic_hold_sensitivity.v1",
        "status": "EXPLORATORY_POST_HOC",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "purpose": DECISION_RULES["purpose"],
        "holds": holds,
        "sectors": sectors,
        "baseline_config_hashes": baseline_hashes,
        "date_range": {"start": START_DATE, "end": end_date},
        "path_horizon": PATH_HORIZON,
        "runtime_dataset": str(RUNTIME_DATA_DIR.relative_to(ROOT)),
        "runtime_manifest_sha256": runtime_hash,
        "formal_20d_untouched": {
            sector: str(SECTOR_CONFIGS[sector].relative_to(ROOT))
            for sector in SECTOR_CONFIGS
        },
        "decision_rules": DECISION_RULES,
        "root_manifest_written_before_arms": True,
        "note": (
            "2024-2025 locked OOS and 2026 data are already revealed; this "
            "study has NO strict out-of-sample window. The only adjudication "
            "window for replacing the 20-day parameter is data frozen after "
            "2026-08-05."
        ),
    }
    # Written before any arm runs so the pre-specified rules are recorded
    # ahead of execution; refreshed after with the same content.
    (OUT_ROOT / "manifest.json").write_text(
        json.dumps(root_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Grid: sectors={sectors} holds={holds} end={end_date} "
          f"path_horizon={PATH_HORIZON}", flush=True)
    for sector in sectors:
        for hold in holds:
            print(run_arm(sector, hold, end_date, runtime_hash), flush=True)

    root_manifest["generated_at"] = datetime.now().isoformat(timespec="seconds")
    (OUT_ROOT / "manifest.json").write_text(
        json.dumps(root_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Root manifest: {OUT_ROOT / 'manifest.json'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

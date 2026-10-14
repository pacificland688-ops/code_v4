"""Local P0-P2 entry point. Research outcomes and order replay are closed."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from momentum_pullback.acceptance import run_hand_acceptance
from momentum_pullback.contracts import GateError, load_contract, require_outcome_permission, write_json
from momentum_pullback.data_adapter import audit_local_prices, local_audit_files
from momentum_pullback.runtime import create_run, environment_probe, verify_run_inputs


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["contract-check", "env-probe", "audit-data", "build-events", "engineering-smoke", "conditional-study", "compare-policies", "portfolio-replay"])
    parser.add_argument("--config", type=Path, default=ROOT / "configs/momentum_pullback/research_contract_v0_2.yaml")
    parser.add_argument("--start", type=int)
    parser.add_argument("--end", type=int)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--outcomes-disabled", action="store_true")
    args = parser.parse_args(argv)
    folder = None
    try:
        contract = load_contract(args.config)
        if args.command in ["conditional-study", "compare-policies", "portfolio-replay"]:
            require_outcome_permission(contract)
        if args.command == "contract-check":
            result = {"status": "DRAFT_CONTRACT_VALID", "contract_hash": contract.hash, "parameter_status": "PROPOSED", "outcomes_enabled": False, "sources_status": contract.section("sources")["status"]}
        elif args.command == "env-probe":
            result = environment_probe(ROOT / "data/research/momentum_pullback/p0_env", install_report=ROOT / "data/research/momentum_pullback/p0_env/install_report.json")
            # Installation metadata remains in the receipt; console output stays small.
            result = {key: result[key] for key in ["status", "executable", "python", "parquet_roundtrip", "probe_file"]}
        elif args.command == "engineering-smoke":
            folder, result = run_hand_acceptance(contract)
            result["artifact_dir"] = str(folder)
        else:
            scope = contract.section("scope")
            start, end = args.start or scope["output_start"], args.end or scope["output_end"]
            if (start, end) != (scope["output_start"], scope["output_end"]):
                raise GateError("ENGINEERING_OUTPUT_WINDOW_CHANGED")
            paths = local_audit_files(ROOT, start, end)
            folder, manifest = create_run(contract, args.command.replace("-", "_"), paths)
            result, consumed = audit_local_prices(ROOT, start, end)
            if set(consumed) != set(paths):
                raise GateError("AUDIT_INPUT_INVENTORY_CHANGED")
            verify_run_inputs(manifest)
            result.update(run_id=manifest["run_id"], source_contract_status=contract.section("sources")["status"], artifact_dir=str(folder))
            write_json(folder / "data_gate_report.json", result)
            # Schema presence alone never attests source accuracy or PIT completeness.
            if result["status"] == "DATA_BLOCKED" or not contract.section("sources")["real_events_permitted"]:
                raise GateError("REAL_EVENT_DATA_GATE_BLOCKED", {"artifact_dir": str(folder), "gates": result["gates"]})
            raise GateError("REVIEWED_NORMALIZED_SNAPSHOT_REQUIRED")
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
        return 0
    except GateError as error:
        result = {"status": "BLOCKED", "reason": error.code, "details": error.details, "outcomes_generated": False}
        if folder is not None:
            write_json(folder / "blocked.json", result)
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

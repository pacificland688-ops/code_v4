"""Interpreter evidence, immutable run manifests and content identities."""
from __future__ import annotations

import importlib
import importlib.metadata as metadata
import json
import platform
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from momentum_pullback.contracts import ROOT, Contract, GateError, file_hash, fingerprint, write_json


def implementation_hash() -> str:
    files = {str(path.relative_to(ROOT)): file_hash(path) for path in sorted((ROOT / "momentum_pullback").glob("*.py"))}
    entry = ROOT / "scripts/run_momentum_pullback.py"
    if entry.exists():
        files[str(entry.relative_to(ROOT))] = file_hash(entry)
    requirements = ROOT / "momentum_pullback/requirements-p0.txt"
    files[str(requirements.relative_to(ROOT))] = file_hash(requirements)
    return fingerprint(files)


def dependency_identity() -> dict:
    pins = {}
    for line in (ROOT / "momentum_pullback/requirements-p0.txt").read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            package, expected = line.split("==")
            try:
                actual = metadata.version(package)
            except metadata.PackageNotFoundError as error:
                raise GateError("DEPENDENCY_NOT_INSTALLED", package) from error
            if actual != expected:
                raise GateError("DEPENDENCY_PIN_MISMATCH", {"package": package, "expected": expected, "actual": actual})
            pins[package] = actual
    if sys.version_info[:2] != (3, 11):
        raise GateError("RESEARCH_INTERPRETER_INCOMPATIBLE", sys.version)
    return {"executable": str(Path(sys.executable).resolve()), "python": platform.python_version(), "pins": pins}


def environment_probe(output: Path, *, install_report: Path | None = None) -> dict:
    """Import binary extensions and verify a small typed Parquet round trip."""
    output = output.resolve()
    if output.is_relative_to((ROOT / "data/parquet").resolve()):
        raise GateError("PUBLIC_CACHE_WRITE_FORBIDDEN")
    output.mkdir(parents=True, exist_ok=True)
    identity = dependency_identity()
    if not install_report or not install_report.is_file():
        raise GateError("INSTALL_SOURCE_EVIDENCE_MISSING")
    install_evidence = json.loads(install_report.read_text(encoding="utf-8"))
    installed_sources = {item["metadata"]["name"].lower().replace("_", "-") for item in install_evidence["install"]}
    if any(package.lower().replace("_", "-") not in installed_sources for package in identity["pins"]):
        raise GateError("INSTALL_SOURCE_EVIDENCE_INCOMPLETE")
    modules = {}
    imports = {}
    for package, module in [("numpy", "numpy"), ("pandas", "pandas"), ("pyarrow", "pyarrow"), ("PyYAML", "yaml"), ("pytest", "pytest")]:
        loaded = importlib.import_module(module)
        imports[module] = loaded
        distribution = metadata.distribution(package)
        modules[package] = {"version": distribution.version, "module_path": str(Path(loaded.__file__).resolve()), "installer": distribution.read_text("INSTALLER"), "direct_url": distribution.read_text("direct_url.json")}
    if sys.version_info[:2] != (3, 11) or int(modules["numpy"]["version"].split(".")[0]) >= 2:
        raise GateError("RESEARCH_ENVIRONMENT_INCOMPATIBLE", {"python": sys.version, "numpy": modules["numpy"]})
    pa = imports["pyarrow"]
    pq = importlib.import_module("pyarrow.parquet")
    path = output / f"probe-{uuid.uuid4().hex}.parquet"
    table = pa.table({"code": ["X", "Y"], "date": pa.array([20171229, 20180102], type=pa.int32()), "price": [10.0, 10.25], "available_at": pa.array([datetime(2017, 12, 29, 9, tzinfo=timezone.utc), datetime(2018, 1, 2, 9, tzinfo=timezone.utc)], type=pa.timestamp("us", tz="UTC"))})
    pq.write_table(table, path)
    restored = pq.ParquetFile(path).read()
    if not table.equals(restored) or table.schema != restored.schema:
        raise GateError("PARQUET_ROUNDTRIP_FAILED")
    receipt = {**identity, "status": "ENVIRONMENT_ACCEPTED", "modules": modules, "parquet_roundtrip": "PASS", "probe_file": str(path), "probe_sha256": file_hash(path), "install_report_sha256": file_hash(install_report), "install_sources": install_evidence["install"], "scope": "NEW_ENGINEERING_MODULES_ONLY"}
    write_json(output / f"environment-{uuid.uuid4().hex}.json", receipt)
    return receipt


def create_run(contract: Contract, phase: str, input_files: list[Path], *, root: Path = ROOT, logical_inputs: dict | None = None) -> tuple[Path, dict]:
    # `root` controls artifact placement; document bindings stay in the workspace.
    bound = [ROOT / item["path"] for item in contract.payload["documents"]]
    if contract.source_path:
        bound.append(Path(contract.source_path))
    content_inputs = [{"path": str(path.resolve()), "sha256": file_hash(path)} for path in sorted(set(input_files + bound))]
    identity = {"contract_hash": contract.hash, "code_hash": implementation_hash(), "phase": phase, "inputs": content_inputs, "logical_inputs": logical_inputs or {}, "scope": contract.section("scope"), "environment": dependency_identity()}
    content_id = fingerprint(identity)
    run_id = f"{phase}-{content_id[:12]}-{uuid.uuid4().hex[:10]}"
    folder = root / "data/research/momentum_pullback" / run_id
    manifest = {**identity, "content_id": content_id, "run_id": run_id, "contract_status": "DRAFT", "parameter_status": "PROPOSED", "outcomes_enabled": False, "created_at_utc": datetime.now(timezone.utc).isoformat(), "executable": str(Path(sys.executable).resolve()), "sample_authority": "ENGINEERING_ONLY_NOT_OOS"}
    write_json(folder / "run_manifest.json", manifest)
    write_json(folder / "contract_snapshot.json", contract.payload)
    return folder, manifest


def verify_run_inputs(manifest: dict) -> None:
    """Catch concurrent file changes rather than blessing an unrecorded input."""
    for item in manifest["inputs"]:
        path = Path(item["path"])
        if not path.is_file() or file_hash(path) != item["sha256"]:
            raise GateError("INPUT_CONTENT_CHANGED_DURING_RUN", item["path"])
    if implementation_hash() != manifest["code_hash"] or dependency_identity() != manifest["environment"]:
        raise GateError("IMPLEMENTATION_CHANGED_DURING_RUN")

"""One interpretation per draft run; study freezing is a separate operation."""
from __future__ import annotations

import copy
import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "momentum_pullback.engineering.v0_2.r3"
CHECKPOINT_SCHEMA = "momentum_pullback.checkpoint.v4"
LEGACY_CONTRACT_SCHEMAS = {"momentum_pullback.engineering.v0_2.r2"}
LEGACY_CHECKPOINT_SCHEMAS = {"momentum_pullback.checkpoint.v2", "momentum_pullback.checkpoint.v3"}


class GateError(ValueError):
    """An invalid or unverified input must not become an empty success."""

    def __init__(self, code: str, details: Any = None):
        super().__init__(code)
        self.code = code
        self.details = details


class UniqueKeyLoader(yaml.SafeLoader):
    """A repeated configuration key cannot silently overwrite its predecessor."""


def _unique_mapping(loader, node, deep=False):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise GateError("DUPLICATE_CONTRACT_KEY", str(key))
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _unique_mapping)


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")


def fingerprint(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    """Write a new artifact, accepting only byte-identical repeat writes."""
    contents = canonical_bytes(value) + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != contents:
            raise GateError("ARTIFACT_ALREADY_EXISTS", str(path))
        return
    with path.open("xb") as target:
        target.write(contents)


@dataclass(frozen=True)
class Contract:
    _payload: dict[str, Any]
    source_path: str = ""

    @property
    def payload(self) -> dict[str, Any]:
        return copy.deepcopy(self._payload)

    @property
    def hash(self) -> str:
        return fingerprint(self._payload)

    def section(self, name: str) -> dict[str, Any]:
        return copy.deepcopy(self._payload[name])


def validate_contract(payload: dict[str, Any], *, root: Path = ROOT, verify_documents: bool = True) -> Contract:
    required = {"schema", "strategy_id", "status", "parameter_status", "freeze_timestamp", "outcomes_enabled", "market", "features", "events", "matching", "orders", "study", "scope", "sources", "documents"}
    if payload.get("schema") in LEGACY_CONTRACT_SCHEMAS:
        raise GateError("CONTRACT_NOT_UPGRADABLE", payload.get("schema"))
    if set(payload) != required or payload.get("schema") != SCHEMA:
        raise GateError("CONTRACT_SCHEMA_INVALID")
    if any(not isinstance(payload[key], dict) for key in ["market", "features", "events", "matching", "orders", "study", "scope", "sources"]) or not isinstance(payload["documents"], list):
        raise GateError("CONTRACT_SECTION_TYPE_INVALID")
    if payload["status"] != "DRAFT" or payload["parameter_status"] != "PROPOSED" or payload["freeze_timestamp"] is not None or payload["outcomes_enabled"] is not False:
        raise GateError("ENGINEERING_ONLY_CONTRACT_REQUIRED")
    if payload["market"] != {"universe": "CSI300_PIT", "asset": "A_SHARE_COMMON_STOCK", "direction": "LONG_ONLY"}:
        raise GateError("MARKET_SCOPE_CHANGED")
    features = payload["features"]
    for key in ("ema_support", "ema_trend", "slope_lag", "momentum_intervals", "prior_high_observations", "volatility_intervals", "min_price_observations", "adv_market_sessions"):
        if type(features.get(key)) is not int or features[key] <= 0:
            raise GateError("FEATURE_WINDOW_INVALID", key)
    if features.get("ema_adjust") is not False or features.get("adv_window") != "MARKET_SESSIONS_INCLUDING_SIGNAL_DAY" or features.get("halt_amount") != "VERIFIED_FULL_DAY_ZERO_ONLY":
        raise GateError("FEATURE_CLOCK_AMBIGUOUS")
    if features.get("feature_ready") != "MIN_VALID_OBSERVATIONS_KNOWN_HISTORY_EVALUABLE_EMA" or features.get("reset_ready") != "FEATURE_READY_PRICE_KNOWN_EMA_SEEDED_BEFORE_BAR":
        raise GateError("FEATURE_READY_RULE_AMBIGUOUS")
    if features.get("rank_roster") != "CERTIFIED_PIT_DAILY_ROSTER" or features.get("rank_execution") != "ONE_CROSS_SECTION_AFTER_REQUIRED_NAMES":
        raise GateError("RANK_ROSTER_RULE_AMBIGUOUS")
    if features.get("rank_denominator") != "ALL_PIT_ELIGIBLE_WITH_KNOWN_WARMUP" or features.get("rank_ties") != "MOMENTUM_DESC_CODE_ASC" or features.get("covariate_percentile") != "AVERAGE_RANK_OVER_SAME_DENOMINATOR":
        raise GateError("RANK_DENOMINATOR_AMBIGUOUS")
    fraction = features.get("top_fraction")
    if type(fraction) not in (int, float) or not math.isfinite(fraction) or not 0 < fraction <= 1:
        raise GateError("TOP_FRACTION_INVALID")
    events = payload["events"]
    if events.get("reset") != "OBSERVED_CLOSE_LE_EMA50_WHEN_RESET_READY" or events.get("pre_ready_reset") != "NOT_A_SEED" or events.get("identity_seed") != "VERIFIED_CHECKPOINT_OR_POST_READY_RESET":
        raise GateError("EVENT_IDENTITY_AMBIGUOUS")
    if events.get("same_day_reclaim") is not True or events.get("primary_first_window") != "ROOT_PLUS_1_THROUGH_WAIT_LIMIT" or events.get("unknown_root") != "PERSIST_UNTIL_VALID_RESET_OR_HISTORY_REPLAY":
        raise GateError("EVENT_IDENTITY_AMBIGUOUS")
    if type(events.get("wait_sessions")) is not int or events["wait_sessions"] < 1:
        raise GateError("WAIT_WINDOW_INVALID")
    matching = payload["matching"]
    caliper = matching.get("caliper")
    if matching.get("controls") != 3 or matching.get("covariates") != ["momentum63", "volatility20", "circ_mv_cny", "adv20_cny"] or type(caliper) not in (int, float) or not math.isfinite(caliper) or not 0 <= caliper <= 1:
        raise GateError("MATCHING_SPEC_INVALID")
    for key, expected in {"distance": "MEAN_SQUARED_PERCENTILE_DIFFERENCE", "industry": "SIGNAL_TIME_PIT_SAME_INDUSTRY", "ties": "DISTANCE_ASC_CODE_ASC", "replacement_within_event": False, "reuse_across_events": True, "outcome_replacement": False}.items():
        if matching.get(key) != expected:
            raise GateError("MATCHING_SPEC_NOT_IMPLEMENTED", key)
    if payload["orders"].get("signal_clock") != "SIGNAL_CUTOFF" or payload["orders"].get("order_clock") != "ORDER_DECISION_CUTOFF" or payload["orders"].get("open_used_in_decision") is not False:
        raise GateError("ORDER_CLOCK_AMBIGUOUS")
    scope = payload["scope"]
    if any(type(scope.get(key)) is not int for key in ["feature_origin", "output_start", "output_end"]):
        raise GateError("OUTPUT_SCOPE_INVALID")
    if scope.get("purpose") != "ENGINEERING_ONLY" or not scope["feature_origin"] <= scope["output_start"] <= scope["output_end"]:
        raise GateError("OUTPUT_SCOPE_INVALID")
    if verify_documents:
        if not payload["documents"]:
            raise GateError("DOCUMENT_BINDING_MISSING")
        for binding in payload["documents"]:
            path = (root / binding["path"]).resolve()
            if not path.is_relative_to(root.resolve()) or not path.is_file() or file_hash(path) != binding["sha256"]:
                raise GateError("DOCUMENT_BINDING_CHANGED", binding["path"])
    return Contract(copy.deepcopy(payload))


def load_contract(path: Path, *, root: Path = ROOT) -> Contract:
    try:
        payload = yaml.load(path.read_text(encoding="utf-8"), Loader=UniqueKeyLoader)
    except yaml.YAMLError as error:
        raise GateError("CONTRACT_YAML_INVALID") from error
    if not isinstance(payload, dict):
        raise GateError("CONTRACT_SCHEMA_INVALID")
    result = validate_contract(payload, root=root)
    return Contract(result.payload, str(path.resolve()))


def require_outcome_permission(contract: Contract) -> None:
    del contract
    raise GateError("OUTCOMES_NOT_IMPLEMENTED_OR_AUTHORIZED")


def checkpoint(state: Any, *, contract: Contract, code_hash: str, feature_origin: int, processed_cutoff: int, history_hash: str, roster_hash: str) -> dict[str, Any]:
    """Bind the consumed roster. A boolean inside the state is not this identity."""
    if not isinstance(roster_hash, str) or not roster_hash:
        raise GateError("ROSTER_HASH_MISSING")
    return {"schema": CHECKPOINT_SCHEMA, "contract_hash": contract.hash, "code_hash": code_hash, "feature_origin": feature_origin, "processed_cutoff": processed_cutoff, "consumed_history_hash": history_hash, "consumed_roster_hash": roster_hash, "state_hash": fingerprint(state), "state": copy.deepcopy(state)}


def restore_checkpoint(saved: dict[str, Any], *, contract: Contract, code_hash: str, feature_origin: int, processed_cutoff: int, history_hash: str, roster_hash: str) -> Any:
    if saved.get("schema") in LEGACY_CHECKPOINT_SCHEMAS:
        raise GateError("CHECKPOINT_NOT_UPGRADABLE", saved.get("schema"))
    expected = checkpoint(None, contract=contract, code_hash=code_hash, feature_origin=feature_origin, processed_cutoff=processed_cutoff, history_hash=history_hash, roster_hash=roster_hash)
    for key in expected:
        if key not in {"state", "state_hash"} and saved.get(key) != expected[key]:
            raise GateError("CHECKPOINT_IDENTITY_MISMATCH", key)
    if saved.get("state_hash") != fingerprint(saved.get("state")):
        raise GateError("CHECKPOINT_STATE_CONTENT_CHANGED")
    return copy.deepcopy(saved["state"])

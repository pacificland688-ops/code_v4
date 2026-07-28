"""
Validation Firewall — Training/Validation Split with Anti-Leakage Enforcement
==============================================================================
Provides expanding-window and leave-one-year-out train/validation splits
with a sealing mechanism that prevents result-dependent redefinition.

Key invariants:
  - Thresholds are determined ONLY from training windows.
  - Once validation results are computed, the split is FROZEN.
  - Any attempt to re-validate after viewing results raises FirewallSealedError.
  - All candidates, thresholds, and failed attempts are recorded.

This enforces hard constraints #5 and #6: "阈值只能由训练窗口确定" and
"验证期一旦查看，就不能因结果不好重新定义规则".
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


class FirewallSealedError(Exception):
    """Raised when attempting to re-validate a sealed split."""
    pass


@dataclass
class TrainValidationSplit:
    """A single train/validation split with anti-leakage sealing.

    Once `validate()` is called, the object is sealed — any subsequent
    call to `validate()` or `set_threshold()` raises FirewallSealedError.
    """

    name: str
    split_type: str  # "expanding_window" | "leave_one_year_out"
    train_events: list[str]   # signal_ids in training set
    valid_events: list[str]   # signal_ids in validation set
    train_years: list[int]
    valid_year: int

    # Thresholds determined from training data only
    thresholds: dict[str, Any] = field(default_factory=dict)

    # Results computed on validation set
    validation_results: dict[str, Any] | None = None

    # Seal state
    _sealed: bool = False
    _sealed_at: str | None = None
    _results_hash: str = ""

    def set_threshold(self, name: str, value: Any) -> None:
        """Set a threshold derived from training data ONLY."""
        if self._sealed:
            raise FirewallSealedError(
                f"Split '{self.name}' is sealed. Cannot modify threshold '{name}'."
            )
        self.thresholds[name] = value

    def validate(self, results: dict[str, Any]) -> None:
        """Record validation results.  This SEALS the split permanently."""
        if self._sealed:
            raise FirewallSealedError(
                f"Split '{self.name}' is already sealed. "
                f"Validation results were recorded at {self._sealed_at}. "
                f"Results hash: {self._results_hash[:16]}..."
            )
        self.validation_results = results
        self._sealed = True
        self._sealed_at = datetime.now().isoformat()
        self._results_hash = _hash_dict(results)

    def is_sealed(self) -> bool:
        return self._sealed


@dataclass
class ValidationFirewall:
    """Manages train/validation splits across multiple windows.

    Records ALL attempts (including rejected candidates) in the ledger.
    """

    splits: list[TrainValidationSplit] = field(default_factory=list)
    rejection_ledger: list[dict] = field(default_factory=list)
    total_candidates_tested: int = 0  # unique candidate definitions, not failed gates/folds
    candidate_ledger: dict[str, dict] = field(default_factory=dict)

    def add_split(self, split: TrainValidationSplit) -> None:
        self.splits.append(split)

    def record_rejection(self, candidate_name: str, gate_name: str,
                         detail: str, split_name: str = "") -> None:
        """Record a hard-gate rejection for audit trail."""
        attempt = self.candidate_ledger.get(candidate_name)
        if attempt is None:
            attempt = {
                "candidate": candidate_name,
                "status": "REJECTED",
                "failed_gates": [],
                "splits": [],
                "first_recorded_at": datetime.now().isoformat(),
            }
            self.candidate_ledger[candidate_name] = attempt
            self.total_candidates_tested += 1
        attempt["status"] = "REJECTED"
        if gate_name not in attempt["failed_gates"]:
            attempt["failed_gates"].append(gate_name)
        if split_name and split_name not in attempt["splits"]:
            attempt["splits"].append(split_name)
        self.rejection_ledger.append({
            "candidate": candidate_name,
            "failed_gate": gate_name,
            "detail": detail,
            "split": split_name,
            "timestamp": datetime.now().isoformat(),
        })

    def record_pass(self, candidate_name: str) -> None:
        """Record a candidate that passed all gates."""
        if candidate_name not in self.candidate_ledger:
            self.candidate_ledger[candidate_name] = {
                "candidate": candidate_name,
                "status": "PASSED",
                "failed_gates": [],
                "splits": [],
                "first_recorded_at": datetime.now().isoformat(),
            }
            self.total_candidates_tested += 1

    def summary(self) -> dict:
        return {
            "n_splits": len(self.splits),
            "n_total_candidates_tested": self.total_candidates_tested,
            "n_rejections": len(self.rejection_ledger),
            "rejection_breakdown": _count_by_gate(self.rejection_ledger),
            "sealed_splits": [s.name for s in self.splits if s.is_sealed()],
            "unsealed_splits": [s.name for s in self.splits if not s.is_sealed()],
            "candidate_ledger": list(self.candidate_ledger.values()),
            "split_audit": [
                {
                    "name": s.name,
                    "split_type": s.split_type,
                    "train_years": s.train_years,
                    "valid_year": s.valid_year,
                    "n_train_events": len(s.train_events),
                    "n_valid_events": len(s.valid_events),
                    "train_events_sha256": _hash_dict({"events": s.train_events}),
                    "valid_events_sha256": _hash_dict({"events": s.valid_events}),
                    "thresholds": s.thresholds,
                    "sealed": s.is_sealed(),
                    "sealed_at": s._sealed_at,
                    "results_sha256": s._results_hash,
                    "validation_results": s.validation_results,
                }
                for s in self.splits
            ],
        }


# ═══════════════════════════════════════════════════════════════════════════
# Persistent Candidate Registry (cross-run, append-only)
# ═══════════════════════════════════════════════════════════════════════════

def _candidate_identity_hash(
    feature_name: str,
    direction: str,
    threshold_method: str,
    missing_strategy: str,
    code_sha256: str,
    config_sha256: str,
) -> str:
    """Deterministic SHA256 of the full candidate definition."""
    payload = json.dumps({
        "feature": feature_name,
        "direction": direction,
        "threshold_method": threshold_method,
        "missing_strategy": missing_strategy,
        "code_sha256": code_sha256,
        "config_sha256": config_sha256,
    }, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


class CandidateRegistry:
    """Append-only, cross-run registry of tested candidates.

    Lives at ``registry_path``.  Prevents re-validating on already-seen
    validation years and tracks total unique candidates for multiple-testing
    correction.
    """

    def __init__(self, registry_path: str):
        self.path = registry_path
        self._entries: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        import os
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for entry in data.get("entries", []):
                    ch = entry.get("candidate_hash", "")
                    if ch:
                        self._entries[ch] = entry
            except (json.JSONDecodeError, KeyError):
                pass

    def _save(self) -> None:
        import os
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        payload = {
            "schema": "candidate_registry.v1",
            "updated_at": datetime.now().isoformat(),
            "n_entries": len(self._entries),
            "entries": list(self._entries.values()),
        }
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False, default=str)

    def is_sealed(self, candidate_hash: str,
                  valid_years: list[int]) -> tuple[bool, str]:
        """Check whether any of *valid_years* have already been tested.

        Returns (sealed: bool, reason: str).
        """
        if candidate_hash in self._entries:
            existing = self._entries[candidate_hash]
            seen_years = set()
            for s in existing.get("validated_splits", []):
                seen_years.add(s.get("valid_year"))
            overlap = set(valid_years) & seen_years
            if overlap:
                return True, (
                    f"Candidate {candidate_hash[:16]} already validated on "
                    f"years {sorted(overlap)} (first tested "
                    f"{existing.get('first_tested_at', 'unknown')})"
                )
        return False, ""

    def n_unique_candidates(self) -> int:
        return len(self._entries)

    def register(self, candidate_hash: str, candidate_name: str,
                 status: str, validated_splits: list[dict]) -> None:
        """Append or update a candidate entry."""
        if candidate_hash in self._entries:
            entry = self._entries[candidate_hash]
            existing_splits = {
                s.get("name"): s for s in entry.get("validated_splits", [])
            }
            for s in validated_splits:
                existing_splits[s.get("name", "")] = s
            entry["validated_splits"] = list(existing_splits.values())
            if status == "PASSED":
                entry["status"] = "PASSED"
        else:
            self._entries[candidate_hash] = {
                "candidate_hash": candidate_hash,
                "candidate_name": candidate_name,
                "status": status,
                "first_tested_at": datetime.now().isoformat(),
                "validated_splits": validated_splits,
            }
        self._save()


# ═══════════════════════════════════════════════════════════════════════════
# Split constructors
# ═══════════════════════════════════════════════════════════════════════════

def expanding_window_split(
    events_by_year: dict[int, list[str]],
    min_train_years: int = 3,
) -> list[TrainValidationSplit]:
    """Expanding window: train on years [Y0 .. Y-1], validate on year Y.

    Produces one split per validation year starting from year
    (min_earliest + min_train_years).
    """
    years = sorted(events_by_year.keys())
    if len(years) < min_train_years + 1:
        return []

    splits = []
    for i in range(min_train_years, len(years)):
        train_years = years[:i]
        valid_year = years[i]
        train_events = []
        for y in train_years:
            train_events.extend(events_by_year.get(y, []))
        valid_events = events_by_year.get(valid_year, [])

        if not train_events or not valid_events:
            continue

        name = f"expanding_{years[0]}-{train_years[-1]}_valid_{valid_year}"
        splits.append(TrainValidationSplit(
            name=name,
            split_type="expanding_window",
            train_events=train_events,
            valid_events=valid_events,
            train_years=list(train_years),
            valid_year=valid_year,
        ))

    return splits


def leave_one_year_out_split(
    events_by_year: dict[int, list[str]],
    min_events_per_fold: int = 5,
) -> list[TrainValidationSplit]:
    """Leave-one-year-out: each year is validation once, rest are training.

    Skips years with fewer than min_events_per_fold events.
    """
    years = sorted(events_by_year.keys())
    splits = []

    for valid_year in years:
        valid_events = events_by_year.get(valid_year, [])
        if len(valid_events) < min_events_per_fold:
            continue

        train_events = []
        train_years = []
        for y in years:
            if y != valid_year:
                train_events.extend(events_by_year.get(y, []))
                train_years.append(y)

        if not train_events:
            continue

        name = f"loyo_valid_{valid_year}"
        splits.append(TrainValidationSplit(
            name=name,
            split_type="leave_one_year_out",
            train_events=train_events,
            valid_events=valid_events,
            train_years=train_years,
            valid_year=valid_year,
        ))

    return splits


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

def _hash_dict(d: dict) -> str:
    return hashlib.sha256(
        json.dumps(d, sort_keys=True, ensure_ascii=False, default=str).encode()
    ).hexdigest()


def _count_by_gate(ledger: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entry in ledger:
        gate = entry.get("failed_gate", "unknown")
        counts[gate] = counts.get(gate, 0) + 1
    return counts

"""Shared helpers for the photoresist panic live alert system."""
from __future__ import annotations

import hashlib
import json
import logging
import math
import sys
from datetime import datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]

_SCRIPTS = ROOT / "scripts"
for _p in (str(ROOT), str(_SCRIPTS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

DEFAULT_LIVE_CONFIG = ROOT / "configs" / "photoresist_panic_live.yaml"
DEFAULT_RESEARCH_CONFIG = ROOT / "configs" / "photoresist_panic_research.yaml"


def load_yaml(path: Path | str) -> dict:
    with open(path, "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def config_hash(config: dict) -> str:
    """Stable short hash of a config dict for audit trails."""
    payload = json.dumps(config, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def wilson_interval(hits: int, n: int, confidence: float = 0.95) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion (no scipy dependency)."""
    if n <= 0:
        return (0.0, 1.0)
    z = {0.90: 1.6449, 0.95: 1.9600, 0.99: 2.5758}.get(round(confidence, 2), 1.9600)
    phat = hits / n
    denom = 1.0 + z * z / n
    center = (phat + z * z / (2 * n)) / denom
    margin = (z / denom) * math.sqrt(phat * (1 - phat) / n + z * z / (4 * n * n))
    return (max(0.0, center - margin), min(1.0, center + margin))


def validate_frozen_gate(live_config: dict, research_config: dict) -> None:
    """Hard startup check: live copy of primary_5d must match the frozen research gate.

    Raises ValueError on any drift — the live system must never redefine the gate.
    """
    frozen = live_config["frozen_gate"]
    research = research_config["threshold_validation"]["gates"][frozen["gate_id"]]
    fields = (
        "return_window_days", "absolute_threshold_pct", "quantile_window_days",
        "quantile_threshold_pct", "breadth_window_days", "breadth_threshold_pct",
    )
    drift = {
        field: (frozen.get(field), research.get(field))
        for field in fields
        if float(frozen.get(field)) != float(research.get(field))
    }
    if drift:
        raise ValueError(
            "frozen_gate drift vs configs/photoresist_panic_research.yaml "
            f"threshold_validation.gates.{frozen['gate_id']}: {drift}"
        )


def setup_runtime_logger(log_path: Path) -> logging.Logger:
    """File + console logger writing to the live output runtime.log."""
    logger = logging.getLogger("photoresist_panic_live")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    )
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    logger.propagate = False
    return logger


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def make_run_id(as_of: int) -> str:
    return f"run_{as_of}_{datetime.now().strftime('%H%M%S')}"


class RunLock:
    """Single-instance lock per output directory (panic_runner.lock).

    The lock file records owner pid/host/run_id/started_at. A lock older than
    stale_after_seconds is treated as abandoned: it is journal-logged and
    taken over (the transaction order guarantees a killed run left a
    consistent journal to recover from).
    """

    def __init__(self, out_dir: Path, run_id: str,
                 stale_after_seconds: int = 7200):
        self.path = Path(out_dir) / "panic_runner.lock"
        self.run_id = run_id
        self.stale_after_seconds = stale_after_seconds
        self.acquired = False
        self.takeover_of: dict | None = None

    def acquire(self) -> None:
        import os
        import socket

        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({
            "pid": os.getpid(),
            "host": socket.gethostname(),
            "run_id": self.run_id,
            "started_at": now_iso(),
            "recovery": "if this lock is stale (>2h), the holder crashed; "
                        "state is rebuildable from panic_transition_journal.jsonl",
        }, ensure_ascii=False, indent=2)
        try:
            fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
            self.acquired = True
            return
        except FileExistsError:
            pass
        holder = self._read_holder()
        age = self._age_seconds(holder)
        if age is not None and age < self.stale_after_seconds:
            raise RuntimeError(
                f"another runner holds {self.path.name}: {holder} "
                f"(age {age:.0f}s) — concurrent runs on one output directory "
                "are forbidden"
            )
        # Stale lock: record the takeover and replace it.
        self.takeover_of = holder
        self.path.unlink(missing_ok=True)
        fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
        self.acquired = True

    def _read_holder(self) -> dict:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {"raw": "unreadable lock file"}

    def _age_seconds(self, holder: dict) -> float | None:
        try:
            started = datetime.fromisoformat(holder["started_at"])
            return (datetime.now() - started).total_seconds()
        except Exception:
            return None

    def release(self) -> None:
        if self.acquired:
            self.path.unlink(missing_ok=True)
            self.acquired = False

    def __enter__(self) -> "RunLock":
        self.acquire()
        return self

    def __exit__(self, *exc) -> None:
        self.release()

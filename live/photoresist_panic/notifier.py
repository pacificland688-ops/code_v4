"""Notification dispatch with transition-driven push policy and idempotency.

Daily refresh (always, not a "push"): latest_alert.json / latest_alert.md /
runtime.log.

Webhook pushes ONLY for these transitions (plan §8):
  first_trigger, severity_upgrade, quality_blocked, pipeline_failure,
  rearmed (config-gated).
Never pushed: still_active at unchanged severity, plain NORMAL dailies,
duplicate same-day runs, ordinary catch-up states.

Every push attempt is recorded in notification_delivery_log.jsonl with its
idempotency key (same key as the journal record), channel, response, attempt
count and final status. A delivered key is never pushed again; a failed key
stays retryable on subsequent runs — webhook failures never roll back signal
facts.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger("photoresist_panic_live")

DELIVERY_LOG_FILENAME = "notification_delivery_log.jsonl"

PUSH_TRANSITIONS = {
    "first_trigger", "severity_upgrade", "quality_blocked", "pipeline_failure",
}


def should_push(transition_kind: str, config: dict) -> bool:
    if transition_kind in PUSH_TRANSITIONS:
        return True
    if transition_kind == "rearmed":
        return bool(config.get("push_on_rearmed", False))
    return False


class DeliveryLog:
    """Append-only JSONL delivery ledger keyed by idempotency key."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._final_ok: set[str] = set()
        self._terminal: dict[str, str] = {}
        self._attempts: dict[str, int] = {}
        self._pending: dict[str, dict] = {}
        if self.path.exists():
            self._load()

    def _load(self) -> None:
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue  # a torn tail line must not kill the pipeline
            key = record.get("idempotency_key")
            if not key:
                continue
            self._attempts[key] = max(
                self._attempts.get(key, 0), int(record.get("attempt", 1))
            )
            if record.get("final_status") == "delivered":
                self._final_ok.add(key)
                self._terminal[key] = "delivered"
                self._pending.pop(key, None)
            elif record.get("final_status") == "pending_retry":
                self._terminal.pop(key, None)
                self._pending[key] = record
            else:  # gave_up or other terminal states clear the retry queue
                self._terminal[key] = str(record.get("final_status") or "unknown")
                self._pending.pop(key, None)

    def delivered(self, key: str) -> bool:
        return key in self._final_ok

    def terminal_status(self, key: str) -> str | None:
        return self._terminal.get(key)

    def attempt_count(self, key: str) -> int:
        return self._attempts.get(key, 0)

    def pending_retries(self) -> list[dict]:
        return [dict(r) for r in self._pending.values()]

    def record(self, key: str, channel: str, status: str, response: str,
               payload_summary: str = "", final_status: str | None = None,
               payload_title: str | None = None,
               payload_markdown: str | None = None) -> None:
        attempt = self._attempts.get(key, 0) + 1
        self._attempts[key] = attempt
        entry = {
            "idempotency_key": key,
            "channel": channel,
            "attempt": attempt,
            "status": status,
            "response": response[:500],
            "payload_summary": payload_summary[:200],
            "payload_title": payload_title if payload_title is not None else payload_summary,
            "payload_markdown": (
                payload_markdown if payload_markdown is not None else payload_summary
            ),
            "final_status": final_status or status,
        }
        from .common import now_iso
        entry["logged_at"] = now_iso()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        if entry["final_status"] == "delivered":
            self._final_ok.add(key)
            self._terminal[key] = "delivered"
            self._pending.pop(key, None)
        elif entry["final_status"] == "pending_retry":
            self._terminal.pop(key, None)
            self._pending[key] = entry
        else:
            self._terminal[key] = str(entry["final_status"])
            self._pending.pop(key, None)


def refresh_daily_files(alert: dict, markdown: str, out_dir: Path,
                        files: dict) -> None:
    """latest_alert.* refresh — happens every run, never counts as a push."""
    (out_dir / files.get("latest_alert_json", "latest_alert.json")).write_text(
        json.dumps(alert, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    (out_dir / files.get("latest_alert_md", "latest_alert.md")).write_text(
        markdown, encoding="utf-8",
    )


def push_webhook(
    delivery_log: DeliveryLog,
    idempotency_key: str,
    title: str,
    markdown: str,
    config: dict,
) -> str:
    """Idempotent webhook push. Returns delivered|skipped_duplicate|
    pending_retry|no_webhook."""
    if delivery_log.delivered(idempotency_key):
        return "skipped_duplicate"
    if delivery_log.terminal_status(idempotency_key) is not None:
        return "skipped_terminal"
    url = config.get("webhook_url")
    if not url:
        delivery_log.record(idempotency_key, "webhook", "skipped",
                            "no webhook_url configured", title,
                            final_status="delivered", payload_title=title,
                            payload_markdown=markdown)
        return "no_webhook"
    status, response = _post_webhook(url, markdown)
    final = "delivered" if status == "ok" else "pending_retry"
    delivery_log.record(idempotency_key, "webhook", status, response, title,
                        final_status=final, payload_title=title,
                        payload_markdown=markdown)
    return final


def retry_pending(delivery_log: DeliveryLog, config: dict,
                  max_retries: int = 5) -> list[dict]:
    """Retry previously failed pushes (independent of signal facts)."""
    results = []
    for entry in delivery_log.pending_retries():
        key = entry["idempotency_key"]
        if entry.get("attempt", 1) >= max_retries:
            delivery_log.record(key, "webhook", "gave_up",
                                f"max_retries={max_retries} reached",
                                entry.get("payload_summary", ""),
                                final_status="gave_up",
                                payload_title=entry.get("payload_title", ""),
                                payload_markdown=entry.get("payload_markdown", ""))
            results.append({"key": key, "result": "gave_up"})
            continue
        outcome = push_webhook(delivery_log, key,
                               entry.get("payload_title")
                               or entry.get("payload_summary", ""),
                               entry.get("payload_markdown")
                               or entry.get("payload_summary", ""), config)
        results.append({"key": key, "result": outcome})
    return results


def journal_notification_outbox(records: list[dict], config: dict) -> list[dict]:
    """Project every push-worthy journal fact into a durable outbox view.

    New records carry the exact payload rendered before the state commit.  The
    deterministic JSON fallback keeps older journal facts recoverable instead
    of silently dropping notifications that predate payload persistence.
    """
    outbox = []
    for record in records:
        kind = str(record.get("kind") or "")
        if not should_push(kind, config):
            continue
        payload = record.get("notification_payload") or {}
        title = str(payload.get("title") or kind)
        markdown = payload.get("markdown")
        if markdown is None:
            markdown = json.dumps(record, ensure_ascii=False, indent=2, default=str)
        outbox.append({
            "idempotency_key": record["idempotency_key"],
            "title": title,
            "markdown": str(markdown),
            "suppressed": bool(record.get("notifications_suppressed", False)),
        })
    return outbox


def dispatch_journal_outbox(
    delivery_log: DeliveryLog,
    records: list[dict],
    config: dict,
    max_retries: int = 5,
) -> list[dict]:
    """Deliver all journal facts missing a terminal delivery-ledger status."""
    results = []
    for item in journal_notification_outbox(records, config):
        if item["suppressed"]:
            continue
        key = item["idempotency_key"]
        if delivery_log.terminal_status(key) is not None:
            continue
        if delivery_log.attempt_count(key) >= max_retries:
            delivery_log.record(
                key, "webhook", "gave_up",
                f"max_retries={max_retries} reached", item["title"],
                final_status="gave_up", payload_title=item["title"],
                payload_markdown=item["markdown"],
            )
            results.append({"key": key, "result": "gave_up"})
            continue
        outcome = push_webhook(
            delivery_log, key, item["title"], item["markdown"], config
        )
        results.append({"key": key, "result": outcome})
    return results


def suppress_journal_outbox(
    delivery_log: DeliveryLog, records: list[dict], config: dict
) -> list[str]:
    """Give initialization-only historical notifications a terminal status."""
    suppressed = []
    for item in journal_notification_outbox(records, config):
        if not item["suppressed"]:
            continue
        key = item["idempotency_key"]
        if delivery_log.terminal_status(key) is not None:
            continue
        delivery_log.record(
            key, "webhook", "suppressed_initialization",
            "initialize-state replay: no historical re-send", item["title"],
            final_status="delivered", payload_title=item["title"],
            payload_markdown=item["markdown"],
        )
        suppressed.append(key)
    return suppressed


def _post_webhook(url: str, markdown: str) -> tuple[str, str]:
    """Minimal webhook POST (企业微信/generic)."""
    try:
        import urllib.request

        payload = json.dumps(
            {"msgtype": "markdown", "markdown": {"content": markdown[:4000]}},
            ensure_ascii=False,
        ).encode("utf-8")
        request = urllib.request.Request(
            url, data=payload, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            return "ok", f"http {response.status}"
    except Exception as exc:
        logger.error("notifier: webhook delivery failed: %s", exc)
        return "failed", str(exc)


def write_failure_file(reason: str, detail: dict, out_dir: Path) -> None:
    message = {"alert_status": "RUN_FAILED", "reason": reason, "detail": detail}
    logger.error("RUN_FAILED %s: %s", reason, detail)
    print(f"[RUN_FAILED] {reason}")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "latest_failure.json").write_text(
        json.dumps(message, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )

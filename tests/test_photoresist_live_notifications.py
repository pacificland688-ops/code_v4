"""Notification policy + idempotency tests (plan §8 / §10)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from live.photoresist_panic import notifier  # noqa: E402
from live.photoresist_panic import journal as journal_mod  # noqa: E402
from live.photoresist_panic.journal import TransitionJournal  # noqa: E402
from live.photoresist_panic.notifier import DeliveryLog  # noqa: E402
from live.photoresist_panic.state_machine import PanicState, step  # noqa: E402


# ── Push policy ─────────────────────────────────────────────────────────
def test_push_policy_transitions():
    config = {}
    assert notifier.should_push("first_trigger", config)
    assert notifier.should_push("severity_upgrade", config)
    assert notifier.should_push("quality_blocked", config)
    assert notifier.should_push("pipeline_failure", config)
    # never pushed
    assert not notifier.should_push("still_active", config)
    assert not notifier.should_push("none", config)          # NORMAL daily
    assert not notifier.should_push("duplicate_run", config)
    assert not notifier.should_push("enter_cooldown", config)
    assert not notifier.should_push("cooldown_reset", config)
    # rearmed is config-gated
    assert not notifier.should_push("rearmed", config)
    assert notifier.should_push("rearmed", {"push_on_rearmed": True})


# ── Idempotent delivery ─────────────────────────────────────────────────
def _failing_webhook(monkeypatch, results):
    calls = []

    def fake_post(url, markdown):
        calls.append(markdown)
        return results.pop(0)

    monkeypatch.setattr(notifier, "_post_webhook", fake_post)
    return calls


def test_first_trigger_pushes_exactly_once(tmp_path, monkeypatch):
    calls = _failing_webhook(monkeypatch, [("ok", "http 200"), ("ok", "http 200")])
    log = DeliveryLog(tmp_path / "d.jsonl")
    config = {"webhook_url": "http://example/hook"}
    key = "g|20260715|SIG1|first_trigger"
    assert notifier.push_webhook(log, key, "first_trigger", "md", config) == "delivered"
    # same key again (duplicate same-day rerun) -> skipped, no second call
    assert notifier.push_webhook(log, key, "first_trigger", "md", config) == "skipped_duplicate"
    assert len(calls) == 1
    # persists across process restarts
    log2 = DeliveryLog(tmp_path / "d.jsonl")
    assert notifier.push_webhook(log2, key, "first_trigger", "md", config) == "skipped_duplicate"
    assert len(calls) == 1


def test_upgrade_key_differs_from_first_trigger_and_pushes_once(tmp_path, monkeypatch):
    calls = _failing_webhook(monkeypatch, [("ok", "200"), ("ok", "200"), ("ok", "200")])
    log = DeliveryLog(tmp_path / "d.jsonl")
    config = {"webhook_url": "http://example/hook"}
    first = "g|20260715|SIG1|first_trigger"
    upgrade = "g|20260716|SIG1|severity_upgrade"
    assert notifier.push_webhook(log, first, "t", "md", config) == "delivered"
    assert notifier.push_webhook(log, upgrade, "t", "md", config) == "delivered"
    assert notifier.push_webhook(log, upgrade, "t", "md", config) == "skipped_duplicate"
    assert len(calls) == 2


def test_webhook_failure_is_retryable_without_touching_facts(tmp_path, monkeypatch):
    calls = _failing_webhook(monkeypatch, [("failed", "timeout"), ("ok", "200")])
    log = DeliveryLog(tmp_path / "d.jsonl")
    config = {"webhook_url": "http://example/hook"}
    key = "g|20260715|SIG1|first_trigger"
    assert notifier.push_webhook(log, key, "first_trigger", "md", config) == "pending_retry"
    assert not log.delivered(key)
    # independent retry pass (e.g. next run) succeeds
    results = notifier.retry_pending(log, config)
    assert results[0]["result"] == "delivered"
    assert log.delivered(key)
    assert len(calls) == 2
    assert calls == ["md", "md"]


def test_retry_preserves_full_original_markdown(tmp_path, monkeypatch):
    body = "# FULL ALERT\n\ncritical details\n\n- P4 liquidity shock"
    calls = _failing_webhook(monkeypatch, [("failed", "timeout"), ("ok", "200")])
    log = DeliveryLog(tmp_path / "d.jsonl")
    config = {"webhook_url": "http://example/hook"}
    key = "g|20260715|SIG1|first_trigger"
    assert notifier.push_webhook(
        log, key, "first_trigger", body, config
    ) == "pending_retry"

    reloaded = DeliveryLog(tmp_path / "d.jsonl")
    assert notifier.retry_pending(reloaded, config)[0]["result"] == "delivered"
    assert calls == [body, body]


def test_state_commit_crash_before_first_attempt_recovers_from_journal(
    tmp_path, monkeypatch
):
    """The next process must discover a never-attempted durable alert fact."""
    body = "# FULL ALERT\n\ncritical details"
    calls = _failing_webhook(monkeypatch, [("ok", "200")])
    journal_path = tmp_path / "journal.jsonl"
    state_path = tmp_path / "panic_state.json"

    journal = TransitionJournal(journal_path)
    state, transition = step(PanicState(), 20260715, True, "P4", 20, 5)
    record = journal_mod.transition_record(
        "primary_5d_frozen_v1", "run1", transition,
        extra={
            "notifications_suppressed": False,
            "notification_payload": {
                "title": "first_trigger", "markdown": body,
            },
        },
    )
    journal.append(record)
    state.save(state_path)
    # Simulated crash: no DeliveryLog exists and no webhook was attempted.
    assert not (tmp_path / "delivery.jsonl").exists()

    reloaded_journal = TransitionJournal(journal_path)
    delivery = DeliveryLog(tmp_path / "delivery.jsonl")
    results = notifier.dispatch_journal_outbox(
        delivery, reloaded_journal.records,
        {"webhook_url": "http://example/hook"},
    )
    assert results == [{"key": record["idempotency_key"], "result": "delivered"}]
    assert calls == [body]
    assert delivery.delivered(record["idempotency_key"])


def test_retry_gives_up_after_max_attempts(tmp_path, monkeypatch):
    _failing_webhook(monkeypatch, [("failed", "boom")] * 10)
    log = DeliveryLog(tmp_path / "d.jsonl")
    config = {"webhook_url": "http://example/hook"}
    key = "g|20260715|SIG1|first_trigger"
    notifier.push_webhook(log, key, "t", "md", config)
    for _ in range(6):
        notifier.retry_pending(log, config, max_retries=3)
    log2 = DeliveryLog(tmp_path / "d.jsonl")
    assert not log2.pending_retries()  # gave up, no infinite retry


def test_daily_refresh_is_not_a_push(tmp_path, monkeypatch):
    calls = _failing_webhook(monkeypatch, [])
    alert = {"alert_status": "NORMAL"}
    notifier.refresh_daily_files(alert, "# daily", tmp_path, {
        "latest_alert_json": "latest_alert.json",
        "latest_alert_md": "latest_alert.md",
    })
    assert (tmp_path / "latest_alert.json").exists()
    assert (tmp_path / "latest_alert.md").exists()
    assert calls == []  # no webhook traffic


def test_no_webhook_configured_marks_delivered(tmp_path):
    log = DeliveryLog(tmp_path / "d.jsonl")
    key = "g|20260715|SIG1|first_trigger"
    assert notifier.push_webhook(log, key, "t", "md", {}) == "no_webhook"
    assert log.delivered(key)  # never retried later

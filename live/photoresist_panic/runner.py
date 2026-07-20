"""Daily close-of-day pipeline orchestration (v2 — transactional).

Commit order per run (gap-fix plan §4.3):
  compute transitions -> append journal (atomic, idempotent)
  -> rebuild + write signal registry (entry resolution)
  -> rebuild + write history (deterministic projection of the journal)
  -> refresh latest alert files
  -> update forward outcomes
  -> COMMIT state last (atomic)
  -> webhook pushes (idempotent, retryable; never roll back facts)

Any failure before the state commit leaves last_processed_date unchanged: the
next run recomputes the same days, journal appends dedupe on the idempotency
key, and every projection is rebuilt from the journal — no signal can be lost.

Exit codes: 0 = status produced, 2 = BLOCKED by the quality gate,
3 = runtime failure (also notified), 4 = first-deploy initialization required.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from .common import (
    DEFAULT_LIVE_CONFIG, DEFAULT_RESEARCH_CONFIG, ROOT, RunLock, config_hash,
    load_yaml, make_run_id, now_iso, setup_runtime_logger, validate_frozen_gate,
)
from . import commonality as commonality_mod
from . import journal as journal_mod
from . import notifier as notifier_mod
from . import quality_gate as quality_mod
from . import reversal as reversal_mod
from . import severity as severity_mod
from . import signal_engine
from .data_updater import (
    expected_open_dates, load_local_suspend_records, run_incremental_update,
)
from .journal import TransitionJournal
from .market_utils import build_trading_calendar
from .renderer import build_conclusion, render_markdown
from .state_machine import PanicState, step
from .universe import (
    active_members, export_snapshot, load_universe_v2, universe_status,
)


class LiveRunContext:
    """Loaded configs + output paths shared across one run."""

    def __init__(self, live_config_path: Path | str = DEFAULT_LIVE_CONFIG,
                 out_dir: Path | str | None = None):
        self.live_config = load_yaml(live_config_path)
        self.research_config = load_yaml(DEFAULT_RESEARCH_CONFIG)
        validate_frozen_gate(self.live_config, self.research_config)
        outputs = self.live_config["outputs"]
        self.out_dir = Path(out_dir) if out_dir else ROOT / outputs["directory"]
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.files = outputs["files"]
        self.logger = setup_runtime_logger(self.out_dir / self.files["runtime_log"])
        self.config_hash = config_hash(self.live_config)
        universe_path = ROOT / self.live_config["universe"]["config_path"]
        self.universe, self.universe_meta = load_universe_v2(universe_path)
        self.universe_config = load_yaml(universe_path)
        self.universe_version = str(self.universe_meta.get("universe_version"))
        self.gate_version = str(self.live_config["gate_version"])

    def path(self, key: str) -> Path:
        return self.out_dir / self.files[key]

    @property
    def journal_path(self) -> Path:
        return self.out_dir / journal_mod.JOURNAL_FILENAME

    @property
    def delivery_log_path(self) -> Path:
        return self.out_dir / notifier_mod.DELIVERY_LOG_FILENAME


# ═══════════════════════════════════════════════════════════════════════
# Per-day evaluation core — SHARED by live runs, catch-up, initialization
# and historical replay (plan §2.8)
# ═══════════════════════════════════════════════════════════════════════
def evaluate_day(context: LiveRunContext, data: dict, gated: pd.DataFrame,
                 calendar: np.ndarray, trade_date: int,
                 regime_by_date: dict | None = None) -> dict:
    """Gate snapshot + member scopes + active-member stress + severity."""
    live = context.live_config
    snap = signal_engine.gate_snapshot(gated, trade_date)
    members = active_members(context.universe, trade_date, ("core",), "medium")
    eligibility = signal_engine.eligibility_snapshot(
        data["prices"], members, trade_date,
        context.universe_config.get("eligibility", {}), calendar,
        limit_status=data.get("limit_status"),
        suspend_status=data.get("suspend_status"),
        stock_status=data.get("stock_status"),
    )
    stress = signal_engine.active_stress_metrics(
        data["prices"], eligibility["active_member_codes"], trade_date,
        limit_status=data.get("limit_status"),
    )
    severity = severity_mod.classify_severity(
        triggered=snap["primary_5d_triggered"],
        basket_ret_5d=snap["basket_ret_5d"],
        historical_percentile=snap["historical_percentile"],
        active_down_breadth_5d=stress["active_down_breadth_5d"],
        active_amount_ratio_20d=stress["active_amount_ratio_20d"],
        active_limit_down_count=stress["active_limit_down_count"],
        config=live["severity"],
    )
    return {
        "trade_date": int(trade_date),
        "snapshot": snap,
        "members": members,
        "eligibility": eligibility,
        "stress": stress,
        "severity": severity,
        "market_regime": (regime_by_date or {}).get(int(trade_date), "unknown"),
    }


def _regime_by_date(index_prices: pd.DataFrame, config: dict) -> dict:
    from validate_photoresist_panic_thresholds import compute_market_regime

    regime = compute_market_regime(index_prices, config)
    if regime.empty:
        return {}
    return {int(r["trade_date"]): str(r["market_regime"])
            for _, r in regime.iterrows()}


def _alert_status(triggered: bool, severity_level: str, reversal_status: str) -> str:
    if triggered:
        return ("PANIC_ALERT_REVERSAL_WATCH"
                if reversal_status.startswith("REVERSAL_CANDIDATE")
                else "PANIC_ALERT_RISK_ONLY")
    if severity_level == "P1":
        return "WEAKNESS_WATCH"
    return "NORMAL"


# ═══════════════════════════════════════════════════════════════════════
# State loading with journal verification (plan §2.4)
# ═══════════════════════════════════════════════════════════════════════
def load_verified_state(context: LiveRunContext, journal: TransitionJournal,
                        state_path: Path) -> PanicState:
    """Journal is the fact source; the state file is only a snapshot cache."""
    recovery: dict = {"checked_at": now_iso(), "state_path": str(state_path)}
    try:
        state = PanicState.load(state_path)
        file_ok = True
    except RuntimeError as exc:
        recovery["state_file_error"] = str(exc)
        state = PanicState()
        file_ok = False

    if journal.records:
        verdict = journal_mod.verify_state_against_journal(state, journal.records)
        if not file_ok or not verdict["matches"]:
            recovery.update({
                "action": "rebuilt_from_journal",
                "differences": {
                    k: v for k, v in verdict["differences"].items()
                } if file_ok else "state file unreadable",
            })
            (context.out_dir / "state_recovery_report.json").write_text(
                json.dumps(recovery, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
            context.logger.warning("state rebuilt from journal: %s",
                                   recovery.get("differences"))
            return verdict["rebuilt"]
    elif not file_ok:
        raise RuntimeError(
            "panic_state.json unreadable and journal is empty — cannot recover"
        )
    return state


def _proven_idle_initialization_checkpoint(
    gated: pd.DataFrame,
    eval_day: int,
    machine_config: dict,
) -> tuple[PanicState | None, dict | None]:
    """Find a quiet window that proves the state is IDLE at its endpoint.

    Starting from any legal IDLE/ACTIVE/COOLDOWN state, at most
    active_max-1 quiet days finish ACTIVE and cooldown_clear further quiet
    days re-arm it.  Event numbering is reconstructed cheaply from the full
    trigger series; severity evaluation is only needed after the checkpoint.
    """
    rows = gated[gated["trade_date"] <= eval_day].sort_values("trade_date")
    if rows.empty:
        return None, None
    active_max = int(machine_config["active_max_trading_days"])
    cooldown = int(machine_config["cooldown_clear_days"])
    required_quiet = active_max + cooldown - 1
    triggers = rows["validation_gate_triggered"].fillna(False).astype(bool).tolist()
    dates = rows["trade_date"].astype(int).tolist()

    streak = 0
    proof_end_index = None
    for index, triggered in enumerate(triggers):
        streak = 0 if triggered else streak + 1
        if streak >= required_quiet:
            proof_end_index = index
    if proof_end_index is None:
        return None, None

    checkpoint_state = PanicState()
    for day, triggered in zip(
        dates[:proof_end_index + 1], triggers[:proof_end_index + 1]
    ):
        checkpoint_state, _ = step(
            checkpoint_state, day, triggered,
            "P2" if triggered else "P0",
            active_max_trading_days=active_max,
            cooldown_clear_days=cooldown,
        )
    if checkpoint_state.state != "IDLE":
        raise RuntimeError("initialization quiet-window proof did not reach IDLE")
    proof_start_index = proof_end_index - required_quiet + 1
    proof = {
        "method": "proven_idle_quiet_window",
        "required_quiet_trading_days": required_quiet,
        "quiet_window_start": dates[proof_start_index],
        "quiet_window_end": dates[proof_end_index],
        "available_history_start": dates[0],
        "events_counted_before_checkpoint": checkpoint_state.event_counter,
    }
    return checkpoint_state, proof


# ═══════════════════════════════════════════════════════════════════════
# Main entry
# ═══════════════════════════════════════════════════════════════════════
def run_daily(
    as_of: int,
    live_config_path: Path | str = DEFAULT_LIVE_CONFIG,
    out_dir: Path | str | None = None,
    refresh_data: bool = True,
    init_mode: str | None = None,          # None | initialize_state | fresh_start
    state_override_path: Path | str | None = None,
) -> int:
    try:
        context = LiveRunContext(live_config_path, out_dir)
    except Exception as exc:
        print(f"[RUN_FAILED] CONTEXT_INIT_FAILED: {exc}")
        return 3
    logger = context.logger
    run_id = make_run_id(as_of)
    notify_config = context.live_config.get("notify", {})
    lock = RunLock(context.out_dir, run_id)
    try:
        lock.acquire()
    except RuntimeError as exc:
        logger.error("run lock refused: %s", exc)
        print(f"[RUN_FAILED] CONCURRENT_RUN: {exc}")
        return 3
    if lock.takeover_of:
        logger.warning("stale run lock taken over: %s", lock.takeover_of)
    try:
        return _run_daily_inner(context, as_of, run_id, refresh_data,
                                init_mode, state_override_path)
    except Exception as exc:  # any uncaught failure must still notify
        logger.exception("run_daily failed")
        _record_pipeline_failure(context, run_id, as_of, str(exc), notify_config)
        return 3
    finally:
        lock.release()


def _record_pipeline_failure(context: LiveRunContext, run_id: str, as_of: int,
                             error: str, notify_config: dict) -> None:
    detail = {"as_of": as_of, "run_id": run_id, "error": error}
    notifier_mod.write_failure_file("PIPELINE_EXCEPTION", detail, context.out_dir)
    try:
        journal = TransitionJournal(context.journal_path)
        record = journal_mod.event_record(
            context.gate_version, run_id, as_of, "pipeline_failure", detail
        )
        record["notification_payload"] = {
            "title": "pipeline_failure",
            "markdown": f"【运行失败】{error}",
        }
        journal.append(record)
        delivery = notifier_mod.DeliveryLog(context.delivery_log_path)
        notifier_mod.suppress_journal_outbox(
            delivery, journal.records, notify_config
        )
        notifier_mod.dispatch_journal_outbox(
            delivery, journal.records, notify_config
        )
    except Exception:
        context.logger.exception("failure notification itself failed")


def _run_daily_inner(
    context: LiveRunContext,
    as_of: int,
    run_id: str,
    refresh_data: bool,
    init_mode: str | None,
    state_override_path: Path | str | None,
) -> int:
    logger = context.logger
    live = context.live_config
    data_config = live["data"]
    notify_config = live.get("notify", {})
    machine_config = live["state_machine"]
    history_start = int(data_config["history_start"])
    index_codes = list(data_config["benchmark_indices"])
    semi_code = str(data_config["semiconductor_index"])

    core_codes = sorted(
        context.universe.loc[
            context.universe["pool_type"] == "core", "ts_code"
        ].unique().tolist()
    )
    logger.info("run %s as_of=%s init_mode=%s", run_id, as_of, init_mode)
    export_snapshot(context.universe, context.universe_meta, context.out_dir)

    journal = TransitionJournal(context.journal_path)
    delivery = notifier_mod.DeliveryLog(context.delivery_log_path)

    # ── 1. Incremental data update (per security, real date math) ─────
    update_report = run_incremental_update(
        core_codes, index_codes, as_of,
        enabled=refresh_data and bool(data_config.get("update", {}).get("enabled", True)),
    )
    if update_report.get("errors"):
        logger.warning("data update errors: %s", update_report["errors"])
    gap_report = update_report.get("gap_report")

    # ── 2. Load market data ───────────────────────────────────────────
    data = signal_engine.load_market_data(history_start, as_of, core_codes, index_codes)
    prices, index_prices = data["prices"], data["index_prices"]

    # Expected open dates for continuity (works offline via cached calendar)
    open_dates = _continuity_window(update_report, as_of, live)
    suspend_records = load_local_suspend_records(
        _cache(), core_codes,
        open_dates[0] if open_dates else history_start, as_of,
    )

    # ── 3. Universe validity + active membership at evaluation day ────
    stock_max = int(prices["trade_date"].max()) if not prices.empty else None
    eval_day = min(stock_max or 0, as_of)
    members_today = active_members(context.universe, eval_day, ("core",), "medium")
    active_codes_today = sorted(members_today["ts_code"].astype(str).tolist())
    uni_status = universe_status(context.universe, eval_day)

    # ── 4. Quality gate (active-member basis) ─────────────────────────
    gate_config = dict(live["quality_gate"])
    gate_config["required_indices"] = index_codes
    quality = quality_mod.run_quality_gate(
        prices, index_prices, active_codes_today, as_of, gate_config,
        open_dates=open_dates,
        suspend_records=suspend_records,
        limit_status=data.get("limit_status"),
        calendar_latest_trading_day=update_report.get("target_trading_day"),
    )
    quality["data_update"] = update_report
    context.path("quality_json").write_text(
        json.dumps(quality, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    if gap_report is not None:
        (context.out_dir / "data_gap_report.json").write_text(
            json.dumps(gap_report, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

    if uni_status["expired"] and live["universe"].get("strict_effective_end", True):
        quality["status"] = quality_mod.BLOCKED
        quality["blockers"].append(
            f"universe_expired: 核心池有效期截止{uni_status['core_max_effective_end']}，"
            "需要先复核新一期成员资格"
        )

    if quality["status"] == quality_mod.BLOCKED:
        return _handle_blocked(context, journal, delivery, run_id, as_of,
                               eval_day, quality, uni_status, notify_config)

    # ── 5. Basket + frozen gate ───────────────────────────────────────
    basket = signal_engine.build_core_basket(
        data, context.universe, context.universe_config, history_start, eval_day
    )
    gated = signal_engine.apply_frozen_gate(basket, live["frozen_gate"]["gate_id"])
    calendar = build_trading_calendar(prices)
    regime_by_date = _regime_by_date(index_prices, live["reversal"]["market_regime"])

    # ── 6. State load (journal-verified) + pending-day resolution ─────
    state_path = (Path(state_override_path) if state_override_path
                  else context.path("state_json"))
    state = load_verified_state(context, journal, state_path)

    gated_days = [int(d) for d in gated["trade_date"]]
    if state.last_processed_date is None:
        if init_mode == "initialize_state":
            checkpoint_state, proof = _proven_idle_initialization_checkpoint(
                gated, eval_day, machine_config
            )
            if checkpoint_state is not None:
                state = checkpoint_state
                journal.append(journal_mod.initialization_checkpoint_record(
                    context.gate_version, run_id, state, proof
                ))
                (context.out_dir / "initialization_checkpoint_report.json").write_text(
                    json.dumps(proof, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                pending_days = [
                    d for d in gated_days
                    if state.last_processed_date < d <= eval_day
                ]
                logger.info(
                    "initialize-state: proven IDLE at %s; replaying %d later days",
                    state.last_processed_date, len(pending_days),
                )
            else:
                pending_days = [d for d in gated_days if d <= eval_day]
                logger.warning(
                    "initialize-state: no proven IDLE window; replaying all %d "
                    "available trading days", len(pending_days),
                )
        elif init_mode == "fresh_start":
            pending_days = [d for d in gated_days if d == eval_day]
            logger.warning("fresh-start: only %s processed — an in-flight "
                           "event before today may be missed", eval_day)
        else:
            print("[RUN_FAILED] FIRST_DEPLOY_REQUIRES_INIT_MODE: no state "
                  "exists; run with --initialize-state (production) or "
                  "--fresh-start (explicitly start from today)")
            return 4
    else:
        pending_days = [d for d in gated_days
                        if state.last_processed_date < d <= eval_day]
    duplicate_run = not pending_days
    suppress_notifications = init_mode == "initialize_state"

    # ── 7. Compute transitions + append journal (fact source first) ───
    transitions: list[dict] = []
    day_evals: dict[int, dict] = {}
    for day in pending_days:
        evaluation = evaluate_day(context, data, gated, calendar, day,
                                  regime_by_date)
        day_evals[day] = evaluation
        state, transition = step(
            state, day,
            triggered=evaluation["snapshot"]["primary_5d_triggered"],
            severity=evaluation["severity"]["level"],
            active_max_trading_days=int(machine_config["active_max_trading_days"]),
            cooldown_clear_days=int(machine_config["cooldown_clear_days"]),
        )
        transitions.append(transition)
        reversal_status = reversal_mod.assess_reversal_context(
            evaluation["market_regime"],
            evaluation["snapshot"]["primary_5d_triggered"], live["reversal"],
        )["reversal_status"]
        day_snapshot = commonality_mod.component_snapshot(
            data["prices"], evaluation["members"], day, None,
            limit_status=data.get("limit_status"),
        )
        day_commonality = commonality_mod.dual_commonality(
            day_snapshot, evaluation["eligibility"]["eligible_member_codes"],
            evaluation["snapshot"]["basket_ret_5d"], live["commonality"],
        )
        record = journal_mod.transition_record(
            context.gate_version, run_id, transition,
            extra={
                "data_as_of": int(as_of),
                "universe_version": context.universe_version,
                "config_hash": context.config_hash,
                "market_regime": evaluation["market_regime"],
                "component_status": day_commonality["signal_commonality"][
                    "classification"],
                "theme_component_status": day_commonality["theme_commonality"][
                    "classification"],
                "alert_status": _alert_status(
                    evaluation["snapshot"]["primary_5d_triggered"],
                    evaluation["severity"]["level"], reversal_status,
                ),
                "active_member_codes": evaluation["eligibility"]["active_member_codes"],
                "eligible_member_codes": evaluation["eligibility"]["eligible_member_codes"],
                "excluded_components": evaluation["eligibility"]["excluded_components"],
                "notifications_suppressed": suppress_notifications,
            },
        )
        if notifier_mod.should_push(transition["kind"], notify_config):
            notification_alert = _assemble_alert(
                context, run_id, as_of, day, state, [transition], evaluation,
                data, semi_code, quality, uni_status, duplicate_run=False,
            )
            record["notification_payload"] = {
                "title": transition["kind"],
                "markdown": render_markdown(notification_alert),
            }
        journal.append(record)

    # ── 8. Full explanation for the evaluation day ─────────────────────
    final_eval = day_evals.get(eval_day) or evaluate_day(
        context, data, gated, calendar, eval_day, regime_by_date
    )
    alert = _assemble_alert(context, run_id, as_of, eval_day, state,
                            transitions, final_eval, data, semi_code,
                            quality, uni_status, duplicate_run)
    markdown = render_markdown(alert)

    # ── 9. Projections: registry -> history -> latest -> outcomes ─────
    registry = journal_mod.rebuild_registry(journal.records)
    calendar_full = calendar
    outcome_config = dict(live["outcomes"])
    if outcome_config.get("entry_liquidity_policy") == (
        "frozen_universe_eligibility_20d"
    ):
        frozen_eligibility = context.universe_config.get("eligibility", {})
        outcome_config["entry_liquidity"] = {
            "enabled": True,
            "source": "frozen_universe_eligibility",
            "window": 20,
            "min_periods": 10,
            "min_daily_amount_20d": frozen_eligibility["min_daily_amount_20d"],
            "amount_unit": frozen_eligibility.get("amount_unit", "cny"),
        }
    from .outcome_tracker import (
        ENTRY_RESOLVED, NO_TRADABLE_BASKET, resolve_entry, update_outcomes,
    )
    for entry in registry:
        if entry.get("entry_resolution_idempotency_key"):
            continue
        resolution = resolve_entry(
            prices, calendar_full, entry,
            limit_status=data.get("limit_status"),
            stock_status=data.get("stock_status"),
            min_components=int(outcome_config.get("min_entry_components", 3)),
            entry_liquidity=outcome_config.get("entry_liquidity"),
        )
        if resolution["entry_status"] in (ENTRY_RESOLVED, NO_TRADABLE_BASKET):
            journal.append(journal_mod.entry_resolution_record(
                context.gate_version, run_id, entry, resolution
            ))
    registry = journal_mod.rebuild_registry(journal.records)
    (context.out_dir / "signals_registry.json").write_text(
        json.dumps(registry, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )

    history = journal_mod.rebuild_history(journal.records, default_as_of=as_of)
    history.to_csv(context.path("history_csv"), index=False, encoding="utf-8-sig")

    notifier_mod.refresh_daily_files(alert, markdown, context.out_dir, context.files)
    pd.DataFrame(alert["components"]).to_csv(
        context.path("component_csv"), index=False, encoding="utf-8-sig"
    )

    if registry:
        update_outcomes(
            context.path("outcomes_csv"),
            context.out_dir / "entry_eligibility.csv",
            prices, calendar_full, registry, outcome_config,
            limit_status=data.get("limit_status"),
            stock_status=data.get("stock_status"),
            suspend_status=data.get("suspend_status"),
        )

    # ── 10. COMMIT state (last) ────────────────────────────────────────
    state.save(state_path)

    # ── 11. Manifest + notifications (post-commit; idempotent) ────────
    _write_manifest(context, run_id, as_of, eval_day, quality, alert, registry,
                    update_report, init_mode)
    _mark_suppressed(context, journal, delivery, notify_config)
    _dispatch_notifications(context, journal, delivery, notify_config)

    if not duplicate_run:
        print(markdown)
    stale_failure = context.out_dir / "latest_failure.json"
    if stale_failure.exists():
        stale_failure.unlink()
    logger.info("run %s complete: %s (severity=%s, state=%s, duplicate=%s)",
                run_id, alert["alert_status"],
                alert["severity"]["level"], state.state, duplicate_run)
    return 0


# ═══════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════
def _cache():
    from data.parquet_cache import ParquetCache
    return ParquetCache(str(ROOT / "data" / "parquet"))


def _continuity_window(update_report: dict, as_of: int, live: dict) -> list[int]:
    """Expected open dates for the check window; offline-capable via cache."""
    gap = update_report.get("gap_report") or {}
    if gap.get("window_start") and gap.get("window_end"):
        try:
            from data.tushare_client import get_client
            client = get_client()
            return expected_open_dates(
                client, int(gap["window_start"]), int(gap["window_end"])
            )
        except Exception:
            pass
    try:
        from data.tushare_client import get_client
        from .data_updater import yyyymmdd_add_days
        client = get_client()
        lookback = int(live["quality_gate"].get("warmup_trading_days", 250))
        start_hint = yyyymmdd_add_days(as_of, -int(lookback * 1.7) - 30)
        days = expected_open_dates(client, start_hint, as_of)
        return days[-lookback:]
    except Exception:
        return []


def _handle_blocked(context, journal, delivery, run_id, as_of, eval_day,
                    quality, uni_status, notify_config) -> int:
    alert = {
        "schema": context.live_config["schema"],
        "generated_at": now_iso(),
        "run_id": run_id,
        "signal_id": None,
        "event_date": quality.get("evaluation_day"),
        "data_as_of": int(as_of),
        "universe_version": context.universe_version,
        "gate_version": context.gate_version,
        "config_hash": context.config_hash,
        "alert_status": "BLOCKED",
        "panic_alert": False,
        "reversal_candidate": False,
        "trade_ready": False,
        "data_quality": quality,
        "universe_status": uni_status,
        "conclusion": "数据质量未通过，今日不生成正式信号。",
    }
    markdown = (
        f"# 光刻胶恐慌预警 — 数据阻断\n\n日期：{as_of}\n\n状态：**BLOCKED**\n\n"
        + "\n".join(f"- {b}" for b in quality["blockers"])
    )
    record = journal_mod.event_record(
        context.gate_version, run_id, eval_day, "quality_blocked",
        {"as_of": as_of, "blockers": quality["blockers"],
         "universe_version": context.universe_version,
         "config_hash": context.config_hash},
    )
    record["notification_payload"] = {
        "title": "quality_blocked", "markdown": markdown,
    }
    journal.append(record)
    history = journal_mod.rebuild_history(journal.records, default_as_of=as_of)
    history.to_csv(context.path("history_csv"), index=False, encoding="utf-8-sig")
    notifier_mod.refresh_daily_files(alert, markdown, context.out_dir, context.files)
    notifier_mod.write_failure_file(
        "QUALITY_GATE_BLOCKED",
        {"as_of": as_of, "blockers": quality["blockers"]}, context.out_dir,
    )
    _mark_suppressed(context, journal, delivery, notify_config)
    _dispatch_notifications(context, journal, delivery, notify_config)
    return 2


def _assemble_alert(context, run_id, as_of, eval_day, state, transitions,
                    final_eval, data, semi_code, quality, uni_status,
                    duplicate_run) -> dict:
    live = context.live_config
    snap = final_eval["snapshot"]
    severity = final_eval["severity"]
    eligibility = final_eval["eligibility"]
    stress = final_eval["stress"]
    prices, index_prices = data["prices"], data["index_prices"]

    final_transition = transitions[-1] if transitions else {
        "kind": "duplicate_run", "state_before": state.state,
        "state_after": state.state, "emit_alert": False, "is_new_event": False,
    }
    regime_info = reversal_mod.market_regime_on(
        index_prices, eval_day, live["reversal"]["market_regime"]
    )
    semi_info = reversal_mod.semiconductor_state(index_prices, eval_day, semi_code)
    reversal = reversal_mod.assess_reversal_context(
        regime_info["market_regime"], snap["primary_5d_triggered"], live["reversal"]
    )
    snapshot = commonality_mod.component_snapshot(
        prices, final_eval["members"], eval_day, semi_info.get("semi_ret_5d"),
        limit_status=data.get("limit_status"),
    )
    commonality = commonality_mod.dual_commonality(
        snapshot, eligibility["eligible_member_codes"],
        snap["basket_ret_5d"], live["commonality"],
    )
    if commonality["signal_commonality"]["reversal_credibility_downgraded"] and (
        reversal["reversal_status"].startswith("REVERSAL_CANDIDATE")
    ):
        reversal["reversal_status"] = "REVERSAL_CANDIDATE_DOWNGRADED"
        reversal["explanation"] += " 注意：单票主导下跌，反转可信度下调。"

    panic_alert = bool(snap["primary_5d_triggered"])
    reversal_candidate = panic_alert and reversal["reversal_status"].startswith(
        "REVERSAL_CANDIDATE"
    )
    alert_status = _alert_status(panic_alert, severity["level"],
                                 reversal["reversal_status"])
    semi_5d = semi_info.get("semi_ret_5d")
    pending_review = uni_status.get("pending_review", [])
    review_note = None
    review_statuses = set(
        context.universe.loc[
            (context.universe["pool_type"] == "core")
            & (context.universe["universe_version"] == context.universe_version),
            "review_status",
        ].tolist()
    )
    if review_statuses - {"approved"}:
        review_note = ("股票池2026证据为desk research级别，未完成正式审核"
                       "(review_status!=approved)：仅供研究预警使用")

    alert = {
        "schema": live["schema"],
        "system_mode": live.get("system_mode", {
            "research_only": True, "shadow_enabled": False,
        }),
        "generated_at": now_iso(),
        "run_id": run_id,
        "signal_id": state.signal_id,
        "event_date": int(eval_day),
        "data_as_of": int(as_of),
        "universe_version": context.universe_version,
        "gate_version": context.gate_version,
        "config_hash": context.config_hash,
        "signal_phase": final_transition["kind"],
        "panic_alert": panic_alert,
        "reversal_candidate": reversal_candidate,
        "trade_ready": False,
        "alert_status": alert_status,
        "state": {
            "state_before": final_transition["state_before"],
            "state_after": final_transition["state_after"],
            "live_signal_date": state.live_signal_date,
            "active_days_elapsed": state.active_days_elapsed,
            "cooldown_clear_count": state.cooldown_clear_count,
            "max_severity": state.max_severity,
        },
        "membership": {
            "active_components": eligibility["active_components"],
            "signal_components": eligibility["signal_components"],
            "active_member_codes": eligibility["active_member_codes"],
            "eligible_member_codes": eligibility["eligible_member_codes"],
            "excluded_components": eligibility["excluded_components"],
        },
        "metrics": {
            **snap,
            "relative_vs_semiconductor_5d": (
                snap["basket_ret_5d"] - semi_5d if semi_5d is not None else None
            ),
            "active_limit_down_count": stress["active_limit_down_count"],
            "active_limit_down_codes": stress["active_limit_down_codes"],
            "active_down_breadth_5d": stress["active_down_breadth_5d"],
            "active_amount_ratio_20d": stress["active_amount_ratio_20d"],
            "active_breadth_member_coverage": stress[
                "active_breadth_member_coverage"
            ],
            "active_amount_member_coverage": stress[
                "active_amount_member_coverage"
            ],
            "semi_ret_5d": semi_5d,
        },
        "severity": severity,
        "reversal": reversal,
        "market": {**regime_info, **semi_info},
        "commonality": commonality,
        "components": snapshot.to_dict("records"),
        "data_quality": {k: quality[k] for k in (
            "status", "components_present", "components_expected",
            "active_expected", "market_data_present", "missing_components",
            "warnings", "blockers", "stock_max_date", "index_max_date",
        )},
        "universe_status": uni_status,
        "universe_review_note": review_note,
        "pending_review": pending_review,
        "duplicate_run": duplicate_run,
    }
    alert["conclusion"] = build_conclusion(alert)
    return alert


def _write_manifest(context, run_id, as_of, eval_day, quality, alert, registry,
                    update_report, init_mode) -> None:
    manifest = {
        "schema": context.live_config["schema"],
        "system_mode": alert.get("system_mode"),
        "run_id": run_id,
        "generated_at": alert["generated_at"],
        "as_of": int(as_of),
        "evaluation_day": int(eval_day),
        "init_mode": init_mode,
        "possible_missed_active_event": init_mode == "fresh_start",
        "universe_version": context.universe_version,
        "gate_version": context.gate_version,
        "config_hash": context.config_hash,
        "quality_status": quality["status"],
        "alert_status": alert["alert_status"],
        "state": alert["state"],
        "membership": alert["membership"],
        "n_signals_tracked": len(registry),
        "data_update": {k: update_report.get(k) for k in
                        ("target_trading_day", "check_window", "errors")},
    }
    context.path("manifest_json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def _dispatch_notifications(context, journal, delivery, notify_config) -> None:
    for result in notifier_mod.dispatch_journal_outbox(
        delivery, journal.records, notify_config
    ):
        context.logger.info(
            "notification %s -> %s", result["key"], result["result"]
        )


def _mark_suppressed(context, journal, delivery, notify_config) -> None:
    """initialize-state mode: journal facts exist, but historical pushes are
    permanently marked delivered so they can never fire later."""
    for key in notifier_mod.suppress_journal_outbox(
        delivery, journal.records, notify_config
    ):
        context.logger.info("notification %s -> suppressed_initialization", key)

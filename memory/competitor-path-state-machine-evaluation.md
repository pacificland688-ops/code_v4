---
name: competitor-path-state-machine-evaluation
description: Detailed evaluation of competitor's price path state machine proposal + rebuttal analysis
metadata:
  type: reference
---

# Evaluation of Competitor's Price Path State Machine Proposal (with Rebuttal Analysis)

## Summary After Rebuttal

The competitor's rebuttal is **substantially correct on all factual claims** verified against the codebase. My original evaluation made four specific errors that need correction. The areas of genuine disagreement have narrowed to: (a) whether path logic should go into the existing AB script vs a dedicated photoresist evaluation script, and (b) the specific threshold values for path state detection. The core integration direction (PIT path anchoring + pre-registered trading rules + don't touch frozen primary_5d) is now **aligned** between both sides.

---

## Errors in My Original Evaluation (Verified & Corrected)

### Error 1: "Add fields to existing AB script" (REJECTED)

**My claim**: Add PIT path fields to `evaluate_panic_ab_classification.py`.

**Competitor's correction**: The AB script (`scripts/evaluate_panic_ab_classification.py`) operates on **individual stock-date pairs** with panic factor values — its unit of analysis is `(ts_code, trade_date)`. The photoresist research operates on **event-level basket analysis** — its unit is `(signal_id, live_signal_date, frozen basket)`. These are fundamentally different sample units, anchors, execution semantics, and cost structures.

**Verified**: Correct. The AB script loads individual stock factor parquet files, computes per-stock forward metrics, and evaluates cross-sectional IC. The photoresist system aggregates a frozen basket of core stocks, evaluates at the event level with a different entry mechanism. They cannot share a single evaluation script.

**Corrected position**: A **new dedicated script** (`scripts/evaluate_photoresist_panic_path_rules.py`) is the right approach. The path parsing logic can be a small, pure-function kernel that both scripts could eventually import, but the photoresist event evaluation must be its own module.

### Error 2: "COOLDOWN handles no-bounce time exit" (REJECTED)

**My claim**: The existing COOLDOWN state (5 consecutive clean days to re-arm) handles the "time exit" for events with no bounce.

**Competitor's correction**: The state machine (`live/photoresist_panic/state_machine.py`) manages **signal calendar state only** — IDLE→ACTIVE→COOLDOWN controls when new panic triggers can fire. It has no position, order, fill price, or exit logic. COOLDOWN prevents duplicate signal triggers; it does NOT equal a position TIME_EXIT.

**Verified**: Correct. The state machine's `PanicState` dataclass has fields: `state, live_signal_date, signal_id, active_days_elapsed, cooldown_clear_count, max_severity, last_processed_date, event_counter, history_dates`. None of these represent a position or an exit. The outcome tracker (`outcome_tracker.py`) handles position valuation, but on a fixed 20d window — there is no "exit at 20d if no target hit" logic distinct from "hold for 20d regardless."

**Corrected position**: A TIME_EXIT rule (close position at 20d close if no +5% net target was hit) is distinct from the COOLDOWN calendar reset. It must be explicitly modeled in the path rule evaluator.

### Error 3: "excess_vs_semiconductor is redundant" (REJECTED)

**My claim**: The existing `semiconductor_state()` in `reversal.py` already computes semiconductor-relative metrics, making the proposed `excess_vs_semiconductor` field redundant.

**Competitor's correction**: `semiconductor_state()` (line 41 of `reversal.py`) computes `semi_ret_5d` and `semi_ret_60d` at signal time — it's a **pre-signal market environment variable**, explicitly documented as "never used for selection" (display only). The proposed `basket_excess_vs_931865_20d/40d/60d` is a **post-signal outcome variable** — how much the basket outperformed the semiconductor index over the holding period. These serve completely different purposes.

**Verified**: Correct. Reading `reversal.py:41-55`: the function computes semiconductor returns at `trade_date` (signal date) as companion display context. The return dictionary even states the values are for display only. A post-event excess return field (basket return minus semiconductor index return over the 20d/40d/60d observation window) is genuinely new and useful for evaluating whether the panic reversal was photoresist-specific or just riding the semiconductor beta.

**Corrected position**: Add `basket_excess_vs_931865_20d`, `basket_excess_vs_931865_40d`, `basket_excess_vs_931865_60d` as outcome fields. Use clearer naming to distinguish from the pre-signal environment variable.

### Error 4: "100bp cost has no formal basis" (REJECTED)

**My claim**: The 100bp assumption needs explicit comparison against the existing 20/50/100bp grid.

**Competitor's correction**: 100bp IS the formal Phase 0 primary assumption. Evidence:
- `configs/photoresist_panic_live.yaml:109`: `round_trip_cost_bps: 100`
- `docs/photoresist_primary_5d_competitor_response_review.md:174-183`: Phase 0 uses 100bps as primary, with explicit listing of all assumptions including "100 bps 往返成本"

**Verified**: Correct. The live config at line 109 explicitly sets `round_trip_cost_bps: 100`. The research config (`photoresist_panic_research.yaml:244`) lists `primary_cost_bps: 20` with sensitivity scenarios `[20, 50, 100]` — so both exist in the repo. The competitor's point that the **photoresist Phase 0 primary口径 is 100bp** is factually correct.

**Corrected position**: 100bp is the correct primary assumption for photoresist-specific research. 20/50bp are sensitivity scenarios. Results must clearly label which cost assumption is in use when comparing across configurations.

---

## My Suggested Path Thresholds: Problems Acknowledged

I proposed specific thresholds (3% drawdown ends bounce, 2% buffer for retest, etc.). The competitor correctly identifies three issues:

1. **"3% from high ends bounce" doesn't define when a bounce BEGINS.** You need a "bounce started" condition first (e.g., close rises ≥2% above signal-day low).

2. **"Close < signal_low * 0.98" is a BREAKDOWN, not a retest.** This conflates a W-shaped support retest (holds above signal low) with a breakdown-and-reclaim pattern. These should stay separate.

3. **"Close > first_bounce_high AND close > signal_low * 1.02" — the second condition is usually redundant.** If close is above first_bounce_high, and first_bounce_high > signal_low by definition, the 1.02 multiplier is likely already satisfied.

**Corrected position**: Thresholds should be pre-registered candidates, not optimized on 21 samples. The competitor's approach of using these as research parameters with sensitivity analysis is correct. Do NOT claim any specific threshold set is "validated."

---

## Genuinely Missed Risks (Acknowledged)

The competitor identified five risks my evaluation missed entirely:

### 1. Confirmation-Execution Lag (CRITICAL)

If a path state (e.g., "second breakout confirmed") is determinable only at day k close, the earliest executable trade is day k+1 close. Using day k close creates look-ahead bias. This must be explicitly modeled in any path-dependent trading rule.

### 2. Multi-Leg Cost Accounting (CRITICAL)

The existing outcome tracker deducts one round-trip cost for a fixed 20d hold. Path-dependent rules involve:
- Initial trial entry → potential stop-loss exit → potential re-entry → potential add-on
- Each leg incurs its own cost and slippage
- The existing `evaluate_signal_outcome()` (line 361 of outcome_tracker.py) has no mechanism for multi-leg cost accounting

### 3. Basket High/Low Are Not Executable (IMPORTANT)

`outcome_tracker.py:247` already documents that component highs peak at different intraday times — the basket high is an upper bound, not an achievable fill price. Therefore:
- Path state determination must use **basket close prices** as primary
- Basket high/low should only be used for diagnostics and stress testing
- Cannot claim that intraday stop-loss or take-profit was "triggered" based on basket extremes

### 4. Event Overlap and Censoring (IMPORTANT)

If observation extends to 60d:
- A new panic event may occur before the previous 60d observation completes
- Need rules for: terminate old observation? run both in parallel? merge as same episode?
- Right-censoring at data end requires explicit handling
- Training/validation isolation periods must extend with the observation window

### 5. Existing A/B Script Has Implementation Issue (CONFIRMED)

`evaluate_panic_ab_classification.py:680-681`:
```python
"A_plus_half_M": lambda d: d[d["ab_label"].isin(["A", "M"])],
"exclude_B": lambda d: d[d["ab_label"].isin(["A", "M"])],
```
These two actions use **identical filter logic**. The "half_M" in the name is misleading — M-class stocks receive full weight, not 0.5 weight. This means the existing AB action evaluation cannot be treated as a complete, mature path-rule foundation.

---

## Where the Disagreement Now Stands

### Agreed (Both Sides)

| Point | Status |
|---|---|
| PIT path anchoring is necessary | ✅ Aligned |
| Pre-registered trading rule variants | ✅ Aligned |
| Don't modify frozen `primary_5d_frozen_v1` | ✅ Aligned |
| No ML at this stage | ✅ Aligned |
| Don't create `primary_5d_path_v2` prematurely | ✅ Aligned |
| 3 main path labels for current sample size | ✅ Aligned |
| Undercut as diagnostic boolean, not main class | ✅ Aligned |
| 100bp is Phase 0 primary cost assumption | ✅ Corrected |
| COOLDOWN ≠ position exit | ✅ Corrected |
| Pre-signal environment ≠ post-signal outcome | ✅ Corrected |
| New dedicated photoresist script needed | ✅ Corrected |

### Remaining Differences

| Topic | My Position | Competitor's Position | Assessment |
|---|---|---|---|
| "50 samples" threshold | A practical heuristic for when 5-class split becomes viable | Should use power analysis / minimum detectable effect instead | Competitor is more rigorous. Power analysis is better but requires specifying expected effect sizes — which we don't yet have. Accept their framing but note the bootstrapping challenge. |
| Path threshold values (3%, 2%) | I suggested concrete values as a starting point | Values are new research degrees of freedom; pre-register as candidates, don't optimize | Competitor is correct. My suggested values were premature. |
| Whether to keep path logic completely separate from AB script | Now agree: dedicated photoresist script | Dedicated photoresist script | Aligned after correction. |
| State machine vs pure function | I called the state machine "over-engineered" | They want a "small, pure-function, deterministic path parser" | These are essentially the same thing — a pure function that maps (price path, signal anchors) → path type. The disagreement was semantic. |

---

## Final Integrated Recommendation

### Architecture: Three Distinct Layers (Competitor's Framing — Adopt)

```
A/B/M labels         → answers "how well did it repair?" (endpoint)
Path states          → answers "what route did it take?" (process)
Trading rules        → answers "could we have traded it?" (executability)
```

These three should be computed and reported together but NOT merged into a single concept.

### What to Build

**New script**: `scripts/evaluate_photoresist_panic_path_rules.py`

Internal components:
1. **Path parser** (pure function): `parse_event_path(prices, calendar, signal) → PathResult`
   - Input: frozen basket close prices, trading calendar, signal anchors (signal_date, signal_low, entry_date, entry_close)
   - Output: `PathResult` with fields: `first_bounce_date`, `first_bounce_high`, `mae_before_bounce`, `post_bounce_drawdown`, `retest_low`, `broke_signal_low`, `reclaim_date`, `second_breakout_date`, `path_type_3class`, `undercut_seen`, `undercut_reclaimed`
   - Path type (3-class): `NO_OR_FAILED_REPAIR` | `SUSTAINED_REPAIR` | `RETEST_SECONDARY_REPAIR`

2. **Rule simulator**: simulates each pre-registered rule PIT
   - R0: T+1 immediate entry, 20d hold → exit
   - R1: Wait for second breakout confirmation, enter T+1 after confirmation
   - R2: Initial small position at T+1, add on second breakout (frozen ratio)
   - R3 (exploratory): After stop-out, allow ONE W-reentry only

3. **Output per event**:
   - `event_path_ledger.csv`: states, anchors, transition dates
   - `rule_trade_ledger.csv`: per-rule entries, fills, costs, rejections

4. **Statistical reporting**:
   - Primary: paired differences (R1/R2/R3 − R0) with confidence intervals
   - NOT: single-rule win rates or best-in-sample parameter selection
   - All four rules reported regardless of results

### Cost and Execution Rules (Hard Constraints)

- Confirmation at day k close → execution at day k+1 close (never same-day)
- Multi-leg rules: each leg pays its own round-trip cost
- Path state determination uses basket **close** prices only
- Basket high/low used only for diagnostic upper/lower bounds
- 100bp primary cost; 20/50bp as sensitivity columns

### What NOT to Do (Reaffirmed)

- Don't touch `primary_5d_frozen_v1`
- Don't modify `live/photoresist_panic/state_machine.py`
- Don't merge path logic into `evaluate_panic_ab_classification.py`
- Don't optimize path thresholds on 21 samples
- Don't create `primary_5d_path_v2` until out-of-sample confirmation
- Don't use basket intraday extremes for executable signal claims

---
name: style-signal-validation-lookahead-fix
description: Fixed look-ahead bias and completeness issues in evaluate_factor_style_signals.py
metadata:
  type: project
---

Refactored `scripts/evaluate_factor_style_signals.py` to eliminate look-ahead bias and meet the output contract spec.

**Why:** The original script computed IC[t] = corr(factor[t], fwd_ret_20d[t]) and used it directly at time t for style labeling. But IC[t] is only knowable after t+20 trading days — a clear look-ahead leakage.

**How to apply:** When working with forward returns and IC-based signals, always map ICs to their availability date via the trading calendar (`cal.next_trade_day(factor_date, horizon)`), compute rolling statistics on the availability axis, and use `pd.merge_asof(direction='backward', allow_exact_matches=False)` to align to signal dates with strict `<` constraint.

**Key changes made:**
1. **Look-ahead fix:** IC mapped to `ic_available_date = cal.next_trade_day(factor_date, horizon)`, trailing IC computed on that axis, aligned via `merge_asof` with `allow_exact_matches=False`
2. **Date filtering:** `_filter_by_date_range()` actually filters data to `[start, end]`
3. **Growth coverage:** Uses `coverage_pct = |factor ∩ fwd_universe| / |fwd_universe|` with thresholds (80% median, 60% yearly). `earnings_acceleration_cs` at 8% → `DATA_COVERAGE_BLOCKED`
4. **Label priority:** mixed_style > momentum_on > value_repair_on > growth_quality_watch > no_clear_style, with `mixed_margin=0.005`
5. **Metrics:** n_days, mean_ic, icir, hit_rate, top_bottom_spread, net_spread, positive_years, status, failure_reasons per label
6. **Predictive power:** If label mean_ic ≤ no_clear_style baseline → `NO_PREDICTIVE_POWER`

**Results after fix (2017-2024):**
- `momentum_on`: 729 days, mean_ic=-0.0435, status=NO_PREDICTIVE_POWER (≤ baseline -0.0158)
- `growth_quality_watch`: 25 days, status=DATA_COVERAGE_BLOCKED
- `eligible_factors`: [] (unchanged, research only)

**Test file:** `tests/test_factor_style_signal_validation.py` — 31 tests covering look-ahead bias, IC availability, date filtering, coverage blocking, correlation dedup, predictive power, output contract.

---
name: market-state-vs-factor-ic-findings
description: Conditional analysis of market state variables predicting factor IC differences
metadata:
  type: project
---

Ran `scripts/explore_market_state_vs_factor_ic.py` testing whether 6 PIT-observable market state dimensions predict differences in 3 factor forward ICs (2017-2024, horizon=20d).

**Key findings:**
1. **volatility_state** is the strongest and most robust predictor — monotonic negative relationship with momentum IC: low vol → IC=+0.016, high vol → IC=-0.068, spread=-0.085, p≈0.0000
2. **trend_strength** shows non-monotonic (inverted-U) relationship with momentum: best IC in neutral trend (Q2), worse in both extremes
3. **breadth_score** weakly predicts momentum: lowest breadth quartile has worst momentum IC
4. **Value repair** (valuation_reversion_3y_cs) shows NO significant state dependency — but only 89 obs, low power
5. **Growth factor** (earnings_acceleration_cs) results appear significant but are based on 146 obs with 8% coverage → flag as exploratory only
6. **size_spread_20d** and **gv_spread_20d** show limited predictive power for momentum/value

**How to apply:** volatility_state is the prime candidate for building a market-state-driven style allocator. Low vol → tilt toward momentum; high vol → tilt away from momentum. The other dimensions need non-linear modeling or interaction terms to be useful.

**Next:** build a simple rule-based allocator that uses volatility_state as the primary signal, then test if combining with trend_strength (non-linear) improves out-of-sample performance.

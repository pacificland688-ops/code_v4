---
name: market-state-tiered-analysis-results
description: Final three-tier analysis results: 2 rule candidates for market-state-driven style allocation
metadata:
  type: project
---

Ran the refined `explore_market_state_vs_factor_ic.py` with coverage audit, Benjamini-Hochberg FDR correction (q<0.10), effect size gate (|spread|>=0.02), and three-tier classification.

**Results (2017-2024, 20d horizon):**
- **7 raw significant** (p<0.05) — reference only
- **6 FDR-robust** (q<0.10 + effect>0.02) — 2 rule candidates + 4 blocked by coverage
- **2 rule candidates** — passed ALL gates (FDR + effect + coverage + sample size)

**Rule candidates (ready for allocator development):**
1. `volatility_state → risk_adjusted_momentum_60_cs`: spread=-0.085, q=0.0000 — high vol → reduce momentum
2. `breadth_score → risk_adjusted_momentum_60_cs`: spread=0.033, q=0.0182 — low breadth → reduce momentum

**FDR-robust but blocked by DATA_COVERAGE_BLOCKED (earnings_acceleration_cs, 8% coverage):**
- volatility_state, breadth_score, turnover_state, size_spread_20d

**IC autocorrelation and trailing→future diagnostics:**
- momentum: short-term positive AC (lag 1-5 = 0.78), but trailing IC → future IC is **IC_REVERSAL** (corr=-0.048, p=0.04)
- value_repair: NO_STABLE_RELATION in AC, strong IC_REVERSAL (corr=-0.63)
- growth: IC_MOMENTUM in both but only 87 obs, coverage 8% → observation only

**How to apply:** The two rule candidates provide a solid foundation for a simple volatility+breadth-driven momentum allocation rule. The IC autocorrelation findings explain WHY the trailing IC approach failed: factor IC mean-reverts at the aggregation level. The next step is building a rule-based allocator using these two state dimensions.

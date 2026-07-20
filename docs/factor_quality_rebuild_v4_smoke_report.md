# Factor Quality Rebuild Report (v2)

生成日期：2026-06-19 12:10
配置：`configs\factor_quality_rebuild_v4.yaml` (sha256=40f3d719a44337da)
随机种子：42

## Summary

- SUPPORT: 1
- FAIL: 2
- **Recommendation**: **NO_ALPHA_SOURCE_FOUND**

## No-Leakage Alignment Audit

| Factor | Horizon | Lag (days) | Aligned Rows | Signal Dates | Cal/Val/Watch | Status |
|---|---:|---:|---:|---:|---|
| `reversal_5_cs` | fwd_ret_5d | 0 | 583423 | 1943 | 289991/293432/0 | PASS |
| `volatility_60_cs` | fwd_ret_5d | 0 | 560851 | 1863 | 278729/282122/0 | PASS |
| `log_market_cap_cs` | fwd_ret_5d | 0 | 30104 | 96 | 14973/15131/0 | PASS |

## Raw vs Mcap-Neutral Comparison (Validation 2021-2024)

| Factor | Raw IC | Neutral IC | Raw ICIR | Neutral ICIR | Raw Net Spread | Neutral Net Spread | Size Dependent |
|---|---:|---:|---:|---:|---:|---|
| `reversal_5_cs` | 0.0045 | 0.0034 |  |  | -0.15% | -0.55% | False |
| `volatility_60_cs` | 0.0605 | 0.0685 |  |  | 0.29% | 0.52% | False |
| `log_market_cap_cs` | 0.0120 | 0.0084 |  |  |  |  | False |

## Turnover Cost Analysis (Validation 2021-2024)

| Factor | Basis | Method | Avg Turnover | Gross Spread | Net Spread | Net/Gross |
|---|---:|---:|---:|---:|---:|
| `reversal_5_cs` | raw | REAL_WEIGHT_DRIFT | 114.0% | 0.09% | -0.14% | 84.4% |
| `volatility_60_cs` | raw | REAL_WEIGHT_DRIFT | 31.2% | 0.48% | 0.42% | 101.2% |

## IC Trend (Validation Window)

| Factor | Basis | Monthly ICs | Slope | p-value | Declining |
|---|---:|---:|---:|---|
| `reversal_5_cs` | raw | 48 | -0.000506 | 0.4148 | False |
| `reversal_5_cs` | mcap_neutral | 45 | -0.000584 | 0.7666 | False |
| `volatility_60_cs` | raw | 48 | -0.001392 | 0.2881 | False |
| `volatility_60_cs` | mcap_neutral | 45 | 0.002170 | 0.3631 | False |
| `log_market_cap_cs` | raw | 45 | 0.000948 | 0.6382 | False |
| `log_market_cap_cs` | mcap_neutral | 45 | -0.000249 | 0.8991 | False |

## Rolling Window Robustness

| Factor | Window | Basis | Status | Mean IC | ICIR | Net Spread | Pos IC Yrs | Pos Spread Yrs |
|---|---:|---:|---:|---:|---:|---:|---:|
| `reversal_5_cs` | 2018_2021 | raw | FAIL | 0.0219 | 0.130 | -0.11% | 4/4 | 0/4 |
| `reversal_5_cs` | 2019_2022 | raw | FAIL | 0.0203 | 0.120 | -0.08% | 4/4 | 1/4 |
| `reversal_5_cs` | 2020_2023 | raw | FAIL | 0.0071 | 0.035 | -0.19% | 3/4 | 1/4 |
| `reversal_5_cs` | 2021_2024 | raw | FAIL | 0.0045 | 0.016 | -0.15% | 3/4 | 1/4 |
| `volatility_60_cs` | 2018_2021 | raw | FAIL | 0.0080 | 0.040 | -0.27% | 3/4 | 1/4 |
| `volatility_60_cs` | 2019_2022 | raw | FAIL | 0.0120 | 0.055 | -0.25% | 3/4 | 1/4 |
| `volatility_60_cs` | 2020_2023 | raw | FAIL | 0.0332 | 0.164 | -0.01% | 3/4 | 2/4 |
| `volatility_60_cs` | 2021_2024 | raw | PASS | 0.0605 | 0.256 | 0.29% | 4/4 | 3/4 |
| `log_market_cap_cs` | 2018_2021 | raw | NOT_AVAILABLE |  |  |  | 0/4 | 0/4 |
| `log_market_cap_cs` | 2019_2022 | raw | NOT_AVAILABLE |  |  |  | 0/4 | 0/4 |
| `log_market_cap_cs` | 2020_2023 | raw | NOT_AVAILABLE |  |  |  | 0/4 | 0/4 |
| `log_market_cap_cs` | 2021_2024 | raw | NOT_AVAILABLE |  |  |  | 0/4 | 0/4 |

## Correlation Clusters

No correlation data available (fewer than 2 eligible factors).

## Capacity / Liquidity Audit

Capacity data not available.

## Regime Breakdown

Regime data not available (diagnostic only, does not affect gate).

## Quality Gate Results

| Factor | Status | Failures | Reasons |
|---|---:|---|
| `log_market_cap_cs` | [SUPPORT] | 7 | coverage: 0.0% < 80%; min_yearly_coverage: 0.0% < 60%; [raw] icir=0.113 < 0.200; [raw] no validation quantile data; [neutral] mean_rank_ic=0.008 < 0.010; [neutral] icir=0.045 < 0.200; [neutral] no val |
| `reversal_5_cs` | [FAIL] | 14 | [raw] mean_rank_ic=0.004 < 0.010; [raw] icir=0.016 < 0.200; [raw] net_spread=-0.0015 <= 0; [raw] pos_spread_years=1/4 < 3; [raw] top_quintile_net_excess=-0.0031 <= 0; [raw] pos_excess_years=1/4 < 3; [ |
| `volatility_60_cs` | [FAIL] | 2 | neutralization: invalid (LOW_COVERAGE), cannot be WATCH_NEUTRAL_ONLY with coverage=5.1% < 70%; [raw] pos_excess_years=2/4 < 3 |

## Candidate Pool

- **Eligible**: []
- **Watch for Review**: []
- **Support — Neutralizers**: ['log_market_cap_cs']
- **Support — Redundant**: []
- **Missing Data**: []
- **FAIL**: ['reversal_5_cs', 'volatility_60_cs']
- **Recommendation**: **NO_ALPHA_SOURCE_FOUND**

## Conclusions

1. **哪些因子真的有净 alpha**: None — no factors pass the full quality gate with net positive post-cost alpha.
2. **哪些因子只是方向/实现问题**: None identified
3. **哪些因子数据缺失**: None
4. **哪些因子应永久淘汰**: reversal_5_cs, volatility_60_cs

## Sleeve Rebuild Authorization

❌ **NOT AUTHORIZED**: No eligible factors. Sleeve/strategy rebuild is blocked.

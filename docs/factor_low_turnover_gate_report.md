# Factor Quality Rebuild Report (v2)

生成日期：2026-06-27 17:28
配置：`outputs\analysis\factor_low_turnover_gate_config.yaml` (sha256=e58f6df72ffebc96)
随机种子：42

## Summary

- FAIL: 4
- **Recommendation**: **NO_ALPHA_SOURCE_FOUND**

## No-Leakage Alignment Audit

| Factor | Horizon | Lag (days) | Aligned Rows | Signal Dates | Cal/Val/Watch | Status |
|---|---:|---:|---:|---:|---|
| `reversal_5_liquidity_adj_weekly_cs` | fwd_ret_5d | 0 | 129034 | 407 | 64139/64895/0 | PASS |
| `reversal_20_vol_adj_weekly_cs` | fwd_ret_5d | 0 | 127359 | 402 | 62472/64887/0 | PASS |
| `low_beta_120_monthly_cs` | fwd_ret_5d | 0 | 29414 | 93 | 14152/15262/0 | PASS |
| `drawdown_resilience_monthly_cs` | fwd_ret_5d | 0 | 28401 | 90 | 13152/15249/0 | PASS |

## Raw vs Mcap-Neutral Comparison (Validation 2021-2024)

| Factor | Raw IC | Neutral IC | Raw ICIR | Neutral ICIR | Raw Net Spread | Neutral Net Spread | Size Dependent |
|---|---:|---:|---:|---:|---:|---|
| `reversal_5_liquidity_adj_weekly_cs` | 0.0097 | 0.1071 |  |  | -0.43% | 0.75% | False |
| `reversal_20_vol_adj_weekly_cs` | 0.0228 | -0.0038 |  |  | -0.05% | -0.75% | True |
| `low_beta_120_monthly_cs` | -0.0289 |  |  |  | -0.36% |  | False |
| `drawdown_resilience_monthly_cs` | -0.0101 |  |  |  | -0.71% |  | False |

## Turnover Cost Analysis (Validation 2021-2024)

| Factor | Basis | Method | Avg Turnover | Gross Spread | Net Spread | Net/Gross |
|---|---:|---:|---:|---:|---:|
| `drawdown_resilience_monthly_cs` | raw | REAL_WEIGHT_DRIFT | 141.2% | -0.13% | -0.41% | 93.7% |
| `low_beta_120_monthly_cs` | raw | REAL_WEIGHT_DRIFT | 31.3% | -0.19% | -0.25% | 91.8% |
| `reversal_20_vol_adj_weekly_cs` | raw | REAL_WEIGHT_DRIFT | 108.7% | 0.08% | -0.13% | 114.7% |
| `reversal_5_liquidity_adj_weekly_cs` | raw | REAL_WEIGHT_DRIFT | 151.8% | 0.63% | 0.33% | -190.6% |

## IC Trend (Validation Window)

| Factor | Basis | Monthly ICs | Slope | p-value | Declining |
|---|---:|---:|---:|---|
| `reversal_5_liquidity_adj_weekly_cs` | raw | 48 | 0.000323 | 0.7581 | False |
| `reversal_5_liquidity_adj_weekly_cs` | mcap_neutral | 5 |  |  | False |
| `reversal_20_vol_adj_weekly_cs` | raw | 48 | -0.000155 | 0.8927 | False |
| `reversal_20_vol_adj_weekly_cs` | mcap_neutral | 5 |  |  | False |
| `low_beta_120_monthly_cs` | raw | 45 | -0.003307 | 0.1757 | False |
| `low_beta_120_monthly_cs` | mcap_neutral | 0 |  |  | False |
| `drawdown_resilience_monthly_cs` | raw | 45 | -0.005091 | 0.0446 | True |
| `drawdown_resilience_monthly_cs` | mcap_neutral | 0 |  |  | False |

## Rolling Window Robustness

| Factor | Window | Basis | Status | Mean IC | ICIR | Net Spread | Pos IC Yrs | Pos Spread Yrs |
|---|---:|---:|---:|---:|---:|---:|---:|
| `reversal_5_liquidity_adj_weekly_cs` | 2018_2021 | raw | FAIL | 0.0173 | 0.104 | -0.54% | 4/4 | 0/4 |
| `reversal_5_liquidity_adj_weekly_cs` | 2019_2022 | raw | FAIL | 0.0153 | 0.093 | -0.49% | 4/4 | 0/4 |
| `reversal_5_liquidity_adj_weekly_cs` | 2020_2023 | raw | FAIL | 0.0076 | 0.046 | -0.53% | 3/4 | 0/4 |
| `reversal_5_liquidity_adj_weekly_cs` | 2021_2024 | raw | FAIL | 0.0097 | 0.051 | -0.43% | 3/4 | 0/4 |
| `reversal_20_vol_adj_weekly_cs` | 2018_2021 | raw | FAIL | 0.0211 | 0.130 | -0.20% | 3/4 | 2/4 |
| `reversal_20_vol_adj_weekly_cs` | 2019_2022 | raw | FAIL | 0.0294 | 0.175 | -0.08% | 3/4 | 3/4 |
| `reversal_20_vol_adj_weekly_cs` | 2020_2023 | raw | FAIL | 0.0211 | 0.109 | -0.17% | 3/4 | 2/4 |
| `reversal_20_vol_adj_weekly_cs` | 2021_2024 | raw | FAIL | 0.0228 | 0.117 | -0.05% | 4/4 | 2/4 |
| `low_beta_120_monthly_cs` | 2018_2021 | raw | FAIL | 0.0165 | 0.058 | 0.14% | 2/4 | 2/4 |
| `low_beta_120_monthly_cs` | 2019_2022 | raw | PASS | 0.0644 | 0.292 | 0.82% | 3/4 | 3/4 |
| `low_beta_120_monthly_cs` | 2020_2023 | raw | PASS | 0.0451 | 0.229 | 0.46% | 3/4 | 3/4 |
| `low_beta_120_monthly_cs` | 2021_2024 | raw | FAIL | -0.0289 | -0.168 | -0.36% | 2/4 | 2/4 |
| `drawdown_resilience_monthly_cs` | 2018_2021 | raw | FAIL | 0.0434 | 0.217 | -0.24% | 4/4 | 2/4 |
| `drawdown_resilience_monthly_cs` | 2019_2022 | raw | FAIL | 0.0543 | 0.251 | -0.03% | 4/4 | 2/4 |
| `drawdown_resilience_monthly_cs` | 2020_2023 | raw | FAIL | 0.0250 | 0.062 | -0.39% | 3/4 | 1/4 |
| `drawdown_resilience_monthly_cs` | 2021_2024 | raw | FAIL | -0.0101 | -0.162 | -0.71% | 2/4 | 1/4 |

## Correlation Clusters

No correlation data available (fewer than 2 eligible factors).

## Capacity / Liquidity Audit

| Factor | Year | Median Top Amt (CNY) | Median Mkt Cap (CNY) | Participation Rate | Status |
|---|---:|---:|---:|---:|---|
| `reversal_5_liquidity_adj_weekly_cs` | 2021 | 560666137 | 90438603254 | 0.05% | PASS |
| `reversal_5_liquidity_adj_weekly_cs` | 2022 | 665764355 | 97349737002 | 0.07% | PASS |
| `reversal_5_liquidity_adj_weekly_cs` | 2023 | 505015874 | 89216039084 | 0.11% | PASS |
| `reversal_5_liquidity_adj_weekly_cs` | 2024 | nan | nan |  | NOT_AVAILABLE |
| `reversal_20_vol_adj_weekly_cs` | 2021 | 568302667 | 89169669238 | 0.09% | PASS |
| `reversal_20_vol_adj_weekly_cs` | 2022 | 369796757 | 84603539901 | 0.09% | PASS |
| `reversal_20_vol_adj_weekly_cs` | 2023 | 598196755 | 79624032044 | 0.10% | PASS |
| `reversal_20_vol_adj_weekly_cs` | 2024 | 783847544 | 93474098683 | 0.08% | PASS |
| `low_beta_120_monthly_cs` | 2021 | nan | nan |  | NOT_AVAILABLE |
| `low_beta_120_monthly_cs` | 2022 | nan | nan |  | NOT_AVAILABLE |
| `low_beta_120_monthly_cs` | 2023 | nan | nan |  | NOT_AVAILABLE |
| `low_beta_120_monthly_cs` | 2024 | nan | nan |  | NOT_AVAILABLE |
| `drawdown_resilience_monthly_cs` | 2021 | nan | nan |  | NOT_AVAILABLE |
| `drawdown_resilience_monthly_cs` | 2022 | nan | nan |  | NOT_AVAILABLE |
| `drawdown_resilience_monthly_cs` | 2023 | nan | nan |  | NOT_AVAILABLE |
| `drawdown_resilience_monthly_cs` | 2024 | nan | nan |  | NOT_AVAILABLE |

## Regime Breakdown

| Factor | Regime | N Dates | Mean IC |
|---|---:|---:|
| `reversal_5_liquidity_adj_weekly_cs` | high_volatility | 49 | 0.0545 |
| `reversal_5_liquidity_adj_weekly_cs` | range_bound | 200 | 0.0240 |
| `reversal_5_liquidity_adj_weekly_cs` | trend_down | 100 | -0.0093 |
| `reversal_5_liquidity_adj_weekly_cs` | trend_up | 49 | -0.0068 |
| `reversal_5_liquidity_adj_weekly_cs` | value_rotation | 1 | 0.2090 |
| `reversal_20_vol_adj_weekly_cs` | high_volatility | 49 | 0.0095 |
| `reversal_20_vol_adj_weekly_cs` | range_bound | 195 | 0.0156 |
| `reversal_20_vol_adj_weekly_cs` | trend_down | 100 | 0.0203 |
| `reversal_20_vol_adj_weekly_cs` | trend_up | 49 | 0.0355 |
| `reversal_20_vol_adj_weekly_cs` | value_rotation | 1 | -0.4410 |
| `low_beta_120_monthly_cs` | high_volatility | 7 | -0.0117 |
| `low_beta_120_monthly_cs` | range_bound | 20 | 0.0507 |
| `low_beta_120_monthly_cs` | trend_down | 10 | -0.0878 |
| `low_beta_120_monthly_cs` | trend_up | 9 | -0.1512 |
| `low_beta_120_monthly_cs` | unclassified | 40 | 0.0330 |
| `drawdown_resilience_monthly_cs` | high_volatility | 7 | 0.0424 |
| `drawdown_resilience_monthly_cs` | range_bound | 18 | -0.0225 |
| `drawdown_resilience_monthly_cs` | trend_down | 10 | 0.0007 |
| `drawdown_resilience_monthly_cs` | trend_up | 9 | -0.0443 |
| `drawdown_resilience_monthly_cs` | unclassified | 39 | 0.0203 |

## Quality Gate Results

| Factor | Status | Failures | Reasons |
|---|---:|---|
| `reversal_5_liquidity_adj_weekly_cs` | [FAIL] | 8 | neutralization: invalid (LOW_COVERAGE), cannot be WATCH_NEUTRAL_ONLY with coverage=2.4% < 70%; [raw] mean_rank_ic=0.010 < 0.010; [raw] icir=0.051 < 0.200; [raw] net_spread=-0.0043 <= 0; [raw] pos_spre |
| `reversal_20_vol_adj_weekly_cs` | [FAIL] | 11 | [raw] icir=0.117 < 0.200; [raw] net_spread=-0.0005 <= 0; [raw] pos_spread_years=2/4 < 3; [raw] top_quintile_net_excess=-0.0014 <= 0; [raw] pos_excess_years=1/4 < 3; [raw] net/gross_ratio=-25% < 50%; [ |
| `low_beta_120_monthly_cs` | [FAIL] | 10 | [raw] mean_rank_ic=-0.029 < 0.010; [raw] icir=-0.168 < 0.200; [raw] pos_ic_years=2/4 < 3; [raw] net_spread=-0.0036 <= 0; [raw] pos_spread_years=2/4 < 3; [raw] pos_excess_years=1/4 < 3; [neutral] mean_ |
| `drawdown_resilience_monthly_cs` | [FAIL] | 11 | [raw] mean_rank_ic=-0.010 < 0.010; [raw] icir=-0.162 < 0.200; [raw] pos_ic_years=2/4 < 3; [raw] net_spread=-0.0071 <= 0; [raw] pos_spread_years=1/4 < 3; [raw] top_quintile_net_excess=-0.0012 <= 0; [ra |

## Candidate Pool

- **Eligible**: []
- **Watch for Review**: []
- **Support — Neutralizers**: []
- **Support — Redundant**: []
- **Missing Data**: []
- **FAIL**: ['reversal_5_liquidity_adj_weekly_cs', 'reversal_20_vol_adj_weekly_cs', 'low_beta_120_monthly_cs', 'drawdown_resilience_monthly_cs']
- **Recommendation**: **NO_ALPHA_SOURCE_FOUND**

## Conclusions

1. **哪些因子真的有净 alpha**: None — no factors pass the full quality gate with net positive post-cost alpha.
2. **哪些因子只是方向/实现问题**: None identified
3. **哪些因子数据缺失**: None
4. **哪些因子应永久淘汰**: reversal_5_liquidity_adj_weekly_cs, reversal_20_vol_adj_weekly_cs, low_beta_120_monthly_cs, drawdown_resilience_monthly_cs

## Sleeve Rebuild Authorization

❌ **NOT AUTHORIZED**: No eligible factors. Sleeve/strategy rebuild is blocked.

# Factor Quality Rebuild Report (v2)

生成日期：2026-06-20 22:57
配置：`configs/factor_quality_rebuild_v4.yaml` (sha256=40f3d719a44337da)
随机种子：42

## Summary

- FAIL: 6
- **Recommendation**: **NO_ALPHA_SOURCE_FOUND**

## No-Leakage Alignment Audit

| Factor | Horizon | Lag (days) | Aligned Rows | Signal Dates | Cal/Val/Watch | Status |
|---|---:|---:|---:|---:|---|
| `industry_relative_momentum_60_cs` | fwd_ret_5d | 0 | 595715 | 1883 | 287544/308171/0 | PASS |
| `momentum_60_skip5_cs` | fwd_ret_5d | 0 | 595715 | 1883 | 287544/308171/0 | PASS |
| `momentum_120_skip20_cs` | fwd_ret_5d | 0 | 574670 | 1823 | 266818/307852/0 | PASS |
| `risk_adjusted_momentum_60_cs` | fwd_ret_5d | 0 | 595715 | 1883 | 287544/308171/0 | PASS |
| `volume_confirmed_momentum_cs` | fwd_ret_5d | 0 | 595715 | 1883 | 287544/308171/0 | PASS |
| `trend_quality_cs` | fwd_ret_5d | 0 | 606360 | 1914 | 298111/308249/0 | PASS |

## Raw vs Mcap-Neutral Comparison (Validation 2021-2024)

| Factor | Raw IC | Neutral IC | Raw ICIR | Neutral ICIR | Raw Net Spread | Neutral Net Spread | Size Dependent |
|---|---:|---:|---:|---:|---:|---|
| `industry_relative_momentum_60_cs` | -0.0064 | -0.0120 |  |  | -0.23% | -0.45% | False |
| `momentum_60_skip5_cs` | 0.0235 | 0.0159 |  |  | 0.18% | -0.32% | False |
| `momentum_120_skip20_cs` | 0.0024 | -0.0182 |  |  | -0.24% | -0.57% | False |
| `risk_adjusted_momentum_60_cs` | 0.0255 | 0.0189 |  |  | 0.19% | -0.41% | False |
| `volume_confirmed_momentum_cs` | 0.0052 | -0.0294 |  |  | -0.26% | -1.04% | False |
| `trend_quality_cs` | 0.0229 | 0.0072 |  |  | 0.01% | -0.80% | True |

## Turnover Cost Analysis (Validation 2021-2024)

| Factor | Basis | Method | Avg Turnover | Gross Spread | Net Spread | Net/Gross |
|---|---:|---:|---:|---:|---:|
| `industry_relative_momentum_60_cs` | raw | REAL_WEIGHT_DRIFT | 65.6% | -0.04% | -0.17% | 141.3% |
| `momentum_120_skip20_cs` | raw | REAL_WEIGHT_DRIFT | 47.3% | -0.16% | -0.25% | 103.4% |
| `momentum_60_skip5_cs` | raw | REAL_WEIGHT_DRIFT | 61.0% | 0.12% | -0.00% | 123.3% |
| `risk_adjusted_momentum_60_cs` | raw | REAL_WEIGHT_DRIFT | 61.1% | 0.08% | -0.04% | 86.5% |
| `trend_quality_cs` | raw | REAL_WEIGHT_DRIFT | 82.8% | -0.08% | -0.25% | 57.9% |
| `volume_confirmed_momentum_cs` | raw | REAL_WEIGHT_DRIFT | 115.4% | -0.18% | -0.41% | 120.2% |

## IC Trend (Validation Window)

| Factor | Basis | Monthly ICs | Slope | p-value | Declining |
|---|---:|---:|---:|---|
| `industry_relative_momentum_60_cs` | raw | 48 | 0.000715 | 0.4038 | False |
| `industry_relative_momentum_60_cs` | mcap_neutral | 45 | 0.001514 | 0.4649 | False |
| `momentum_60_skip5_cs` | raw | 48 | -0.000780 | 0.4931 | False |
| `momentum_60_skip5_cs` | mcap_neutral | 45 | -0.001910 | 0.5085 | False |
| `momentum_120_skip20_cs` | raw | 48 | 0.000062 | 0.9511 | False |
| `momentum_120_skip20_cs` | mcap_neutral | 45 | -0.000058 | 0.9820 | False |
| `risk_adjusted_momentum_60_cs` | raw | 48 | -0.001279 | 0.2148 | False |
| `risk_adjusted_momentum_60_cs` | mcap_neutral | 45 | -0.001913 | 0.4673 | False |
| `volume_confirmed_momentum_cs` | raw | 48 | 0.000363 | 0.4664 | False |
| `volume_confirmed_momentum_cs` | mcap_neutral | 45 | 0.000472 | 0.7574 | False |
| `trend_quality_cs` | raw | 48 | -0.000816 | 0.4115 | False |
| `trend_quality_cs` | mcap_neutral | 45 | -0.001545 | 0.4130 | False |

## Rolling Window Robustness

| Factor | Window | Basis | Status | Mean IC | ICIR | Net Spread | Pos IC Yrs | Pos Spread Yrs |
|---|---:|---:|---:|---:|---:|---:|---:|
| `industry_relative_momentum_60_cs` | 2018_2021 | raw | FAIL | -0.0013 | 0.006 | -0.18% | 2/4 | 1/4 |
| `industry_relative_momentum_60_cs` | 2019_2022 | raw | FAIL | -0.0094 | -0.051 | -0.30% | 1/4 | 1/4 |
| `industry_relative_momentum_60_cs` | 2020_2023 | raw | FAIL | -0.0012 | 0.001 | -0.13% | 2/4 | 2/4 |
| `industry_relative_momentum_60_cs` | 2021_2024 | raw | FAIL | -0.0064 | -0.044 | -0.23% | 1/4 | 1/4 |
| `momentum_60_skip5_cs` | 2018_2021 | raw | FAIL | 0.0116 | 0.054 | 0.01% | 3/4 | 3/4 |
| `momentum_60_skip5_cs` | 2019_2022 | raw | FAIL | 0.0214 | 0.100 | 0.14% | 3/4 | 3/4 |
| `momentum_60_skip5_cs` | 2020_2023 | raw | FAIL | 0.0129 | 0.050 | 0.00% | 2/4 | 2/4 |
| `momentum_60_skip5_cs` | 2021_2024 | raw | FAIL | 0.0235 | 0.103 | 0.18% | 3/4 | 3/4 |
| `momentum_120_skip20_cs` | 2018_2021 | raw | FAIL | 0.0214 | 0.116 | 0.16% | 3/4 | 1/4 |
| `momentum_120_skip20_cs` | 2019_2022 | raw | FAIL | 0.0124 | 0.067 | 0.07% | 2/4 | 1/4 |
| `momentum_120_skip20_cs` | 2020_2023 | raw | FAIL | 0.0211 | 0.109 | 0.17% | 2/4 | 2/4 |
| `momentum_120_skip20_cs` | 2021_2024 | raw | FAIL | 0.0024 | 0.013 | -0.24% | 1/4 | 1/4 |
| `risk_adjusted_momentum_60_cs` | 2018_2021 | raw | FAIL | 0.0140 | 0.069 | -0.04% | 3/4 | 3/4 |
| `risk_adjusted_momentum_60_cs` | 2019_2022 | raw | FAIL | 0.0252 | 0.129 | 0.11% | 3/4 | 3/4 |
| `risk_adjusted_momentum_60_cs` | 2020_2023 | raw | FAIL | 0.0167 | 0.078 | -0.01% | 2/4 | 2/4 |
| `risk_adjusted_momentum_60_cs` | 2021_2024 | raw | FAIL | 0.0255 | 0.120 | 0.19% | 3/4 | 3/4 |
| `volume_confirmed_momentum_cs` | 2018_2021 | raw | FAIL | 0.0045 | 0.037 | -0.25% | 2/4 | 0/4 |
| `volume_confirmed_momentum_cs` | 2019_2022 | raw | FAIL | 0.0115 | 0.096 | -0.15% | 3/4 | 1/4 |
| `volume_confirmed_momentum_cs` | 2020_2023 | raw | FAIL | 0.0058 | 0.047 | -0.25% | 2/4 | 1/4 |
| `volume_confirmed_momentum_cs` | 2021_2024 | raw | FAIL | 0.0052 | 0.033 | -0.26% | 2/4 | 1/4 |
| `trend_quality_cs` | 2018_2021 | raw | FAIL | 0.0166 | 0.091 | -0.19% | 3/4 | 1/4 |
| `trend_quality_cs` | 2019_2022 | raw | FAIL | 0.0274 | 0.154 | -0.04% | 3/4 | 2/4 |
| `trend_quality_cs` | 2020_2023 | raw | FAIL | 0.0200 | 0.108 | -0.11% | 2/4 | 2/4 |
| `trend_quality_cs` | 2021_2024 | raw | FAIL | 0.0229 | 0.122 | 0.01% | 3/4 | 2/4 |

## Correlation Clusters

No correlation data available (fewer than 2 eligible factors).

## Capacity / Liquidity Audit

Capacity data not available.

## Regime Breakdown

Regime data not available (diagnostic only, does not affect gate).

## Quality Gate Results

| Factor | Status | Failures | Reasons |
|---|---:|---|
| `industry_relative_momentum_60_cs` | [FAIL] | 12 | [raw] mean_rank_ic=-0.006 < 0.010; [raw] icir=-0.044 < 0.200; [raw] pos_ic_years=1/4 < 3; [raw] net_spread=-0.0023 <= 0; [raw] pos_spread_years=1/4 < 3; [raw] top_quintile_net_excess=-0.0027 <= 0; [ra |
| `momentum_60_skip5_cs` | [FAIL] | 8 | [raw] icir=0.103 < 0.200; [raw] top_quintile_net_excess=-0.0008 <= 0; [raw] pos_excess_years=2/4 < 3; [raw] max_year_contrib=74% > 60%; [neutral] icir=0.084 < 0.200; [neutral] net_spread=-0.0032 <= 0; |
| `momentum_120_skip20_cs` | [FAIL] | 12 | [raw] mean_rank_ic=0.002 < 0.010; [raw] icir=0.013 < 0.200; [raw] pos_ic_years=1/4 < 3; [raw] net_spread=-0.0024 <= 0; [raw] pos_spread_years=1/4 < 3; [raw] top_quintile_net_excess=-0.0033 <= 0; [raw] |
| `risk_adjusted_momentum_60_cs` | [FAIL] | 7 | [raw] icir=0.120 < 0.200; [raw] top_quintile_net_excess=-0.0003 <= 0; [raw] pos_excess_years=2/4 < 3; [raw] max_year_contrib=84% > 60%; [neutral] icir=0.109 < 0.200; [neutral] net_spread=-0.0041 <= 0; |
| `volume_confirmed_momentum_cs` | [FAIL] | 14 | [raw] mean_rank_ic=0.005 < 0.010; [raw] icir=0.033 < 0.200; [raw] pos_ic_years=2/4 < 3; [raw] net_spread=-0.0026 <= 0; [raw] pos_spread_years=1/4 < 3; [raw] top_quintile_net_excess=-0.0027 <= 0; [raw] |
| `trend_quality_cs` | [FAIL] | 11 | [raw] icir=0.122 < 0.200; [raw] pos_spread_years=2/4 < 3; [raw] top_quintile_net_excess=-0.0015 <= 0; [raw] pos_excess_years=1/4 < 3; [raw] max_year_contrib=908% > 60%; [raw] net/gross_ratio=8% < 50%; |

## Candidate Pool

- **Eligible**: []
- **Watch for Review**: []
- **Support — Neutralizers**: []
- **Support — Redundant**: []
- **Missing Data**: []
- **FAIL**: ['industry_relative_momentum_60_cs', 'momentum_60_skip5_cs', 'momentum_120_skip20_cs', 'risk_adjusted_momentum_60_cs', 'volume_confirmed_momentum_cs', 'trend_quality_cs']
- **Recommendation**: **NO_ALPHA_SOURCE_FOUND**

## Conclusions

1. **哪些因子真的有净 alpha**: None — no factors pass the full quality gate with net positive post-cost alpha.
2. **哪些因子只是方向/实现问题**: None identified
3. **哪些因子数据缺失**: None
4. **哪些因子应永久淘汰**: industry_relative_momentum_60_cs, momentum_60_skip5_cs, momentum_120_skip20_cs, risk_adjusted_momentum_60_cs, volume_confirmed_momentum_cs, trend_quality_cs

## Sleeve Rebuild Authorization

❌ **NOT AUTHORIZED**: No eligible factors. Sleeve/strategy rebuild is blocked.

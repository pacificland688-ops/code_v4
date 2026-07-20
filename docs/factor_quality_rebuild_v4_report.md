# Factor Quality Rebuild Report (v2)

生成日期：2026-06-19 19:30
配置：`configs\factor_quality_rebuild_v4.yaml` (sha256=40f3d719a44337da)
随机种子：42

## Summary

- DATA_MISSING: 14
- SUPPORT: 1
- FAIL: 49
- **Recommendation**: **NO_ALPHA_SOURCE_FOUND**

## No-Leakage Alignment Audit

| Factor | Horizon | Lag (days) | Aligned Rows | Signal Dates | Cal/Val/Watch | Status |
|---|---:|---:|---:|---:|---|
| `reversal_5_cs` | fwd_ret_5d | 0 | 583423 | 1943 | 289991/293432/0 | PASS |
| `reversal_20_cs` | fwd_ret_5d | 0 | 549557 | 1823 | 273090/276467/0 | PASS |
| `momentum_60_cs` | fwd_ret_5d | 0 | 564114 | 1820 | 280209/283905/0 | PASS |
| `momentum_120_cs` | fwd_ret_5d | 0 | 527961 | 1688 | 260598/267363/0 | PASS |
| `volatility_20_cs` | fwd_ret_5d | 0 | 572134 | 1903 | 284357/287777/0 | PASS |
| `volatility_60_cs` | fwd_ret_5d | 0 | 560851 | 1863 | 278729/282122/0 | PASS |
| `rsi_14_cs` | fwd_ret_5d | 0 | 563108 | 1871 | 279855/283253/0 | PASS |
| `macd_12_26_9_cs` | fwd_ret_5d | 0 | 538990 | 1807 | 267590/271400/0 | PASS |
| `pv_divergence_20_cs` | fwd_ret_5d | 0 | 572134 | 1903 | 284357/287777/0 | PASS |
| `ep_cs` | fwd_ret_5d | 63 | 28627 | 93 | 14011/14616/0 | PASS |
| `bp_cs` | fwd_ret_5d | 63 | 28627 | 93 | 14011/14616/0 | PASS |
| `sp_cs` | fwd_ret_5d | 63 | 28627 | 93 | 14011/14616/0 | PASS |
| `roe_cs` | fwd_ret_5d | 63 | 414859 | 1703 | 188480/226379/0 | PASS |
| `gross_margin_cs` | fwd_ret_5d | 63 | 344059 | 1703 | 153642/190417/0 | PASS |
| `profit_growth_cs` | fwd_ret_5d | 63 | 39238 | 1387 | 15057/24181/0 | PASS |
| `revenue_growth_cs` | fwd_ret_5d | 63 | 39238 | 1387 | 15057/24181/0 | PASS |
| `leverage_cs` | fwd_ret_5d | 63 | 413286 | 1703 | 188360/224926/0 | PASS |
| `log_market_cap_cs` | fwd_ret_5d | 0 | 30104 | 96 | 14973/15131/0 | PASS |
| `roe_stability_8q_cs` | fwd_ret_5d | 63 | 389578 | 1634 | 168927/220651/0 | PASS |
| `roa_ttm_cs` | fwd_ret_5d | 63 | 340670 | 1703 | 152790/187880/0 | PASS |
| `gross_margin_ttm_cs` | fwd_ret_5d | 63 | 344059 | 1703 | 153642/190417/0 | PASS |
| `net_margin_ttm_cs` | fwd_ret_5d | 63 | 411228 | 1703 | 187628/223600/0 | PASS |
| `profitability_quality_cs` | fwd_ret_5d | 63 | 414859 | 1703 | 188480/226379/0 | PASS |
| `asset_turnover_ttm_cs` | fwd_ret_5d | 63 | 0 | 0 | 0/0/0 | NOT_AVAILABLE |
| `revenue_growth_ttm_cs` | fwd_ret_5d | 63 | 41708 | 1617 | 17527/24181/0 | PASS |
| `profit_growth_ttm_cs` | fwd_ret_5d | 63 | 41708 | 1617 | 17527/24181/0 | PASS |
| `growth_stability_8q_cs` | fwd_ret_5d | 63 | 42784 | 1587 | 18603/24181/0 | PASS |
| `growth_value_match_cs` | fwd_ret_5d | 63 | 0 | 0 | 0/0/0 | NOT_AVAILABLE |
| `earnings_acceleration_cs` | fwd_ret_5d | 63 | 36694 | 1440 | 12513/24181/0 | PASS |
| `ocf_to_mktcap_cs` | fwd_ret_5d | 63 | 0 | 0 | 0/0/0 | NOT_AVAILABLE |
| `ocf_to_profit_cs` | fwd_ret_5d | 63 | 0 | 0 | 0/0/0 | NOT_AVAILABLE |
| `fcf_yield_cs` | fwd_ret_5d | 63 | 0 | 0 | 0/0/0 | NOT_AVAILABLE |
| `cashflow_stability_8q_cs` | fwd_ret_5d | 63 | 0 | 0 | 0/0/0 | NOT_AVAILABLE |
| `accrual_quality_cs` | fwd_ret_5d | 63 | 0 | 0 | 0/0/0 | NOT_AVAILABLE |
| `receivable_pressure_cs` | fwd_ret_5d | 63 | 0 | 0 | 0/0/0 | NOT_AVAILABLE |
| `industry_relative_ep_cs` | fwd_ret_5d | 63 | 28482 | 93 | 14088/14394/0 | PASS |
| `industry_relative_bp_cs` | fwd_ret_5d | 63 | 29292 | 93 | 14346/14946/0 | PASS |
| `valuation_reversion_3y_cs` | fwd_ret_5d | 63 | 0 | 0 | 0/0/0 | NOT_AVAILABLE |
| `quality_value_composite_cs` | fwd_ret_5d | 63 | 0 | 0 | 0/0/0 | NOT_AVAILABLE |
| `dividend_quality_cs` | fwd_ret_5d | 63 | 0 | 0 | 0/0/0 | NOT_AVAILABLE |
| `industry_relative_momentum_60_cs` | fwd_ret_5d | 0 | 595715 | 1883 | 287544/308171/0 | PASS |
| `industry_relative_quality_cs` | fwd_ret_5d | 63 | 0 | 0 | 0/0/0 | NOT_AVAILABLE |
| `industry_relative_growth_cs` | fwd_ret_5d | 63 | 0 | 0 | 0/0/0 | NOT_AVAILABLE |
| `industry_relative_value_cs` | fwd_ret_5d | 63 | 0 | 0 | 0/0/0 | NOT_AVAILABLE |
| `momentum_60_skip5_cs` | fwd_ret_5d | 0 | 595715 | 1883 | 287544/308171/0 | PASS |
| `momentum_120_skip20_cs` | fwd_ret_5d | 0 | 574670 | 1823 | 266818/307852/0 | PASS |
| `risk_adjusted_momentum_60_cs` | fwd_ret_5d | 0 | 595715 | 1883 | 287544/308171/0 | PASS |
| `volume_confirmed_momentum_cs` | fwd_ret_5d | 0 | 595715 | 1883 | 287544/308171/0 | PASS |
| `trend_quality_cs` | fwd_ret_5d | 0 | 606360 | 1914 | 298111/308249/0 | PASS |
| `intraday_reversal_cs` | fwd_ret_5d | 0 | 616200 | 1943 | 307893/308307/0 | PASS |
| `overnight_reversal_cs` | fwd_ret_5d | 0 | 616200 | 1943 | 307893/308307/0 | PASS |
| `amihud_illiq_20d_cs` | fwd_ret_5d | 0 | 612815 | 1933 | 304528/308287/0 | PASS |
| `vol_price_divergence_20d_cs` | fwd_ret_5d | 0 | 613154 | 1934 | 304865/308289/0 | PASS |
| `volatility_squeeze_cs` | fwd_ret_5d | 0 | 606020 | 1913 | 297773/308247/0 | PASS |
| `tail_risk_60d_cs` | fwd_ret_5d | 0 | 606020 | 1913 | 297773/308247/0 | PASS |
| `turnover_anomaly_20d_cs` | fwd_ret_5d | 0 | 27309 | 87 | 12086/15223/0 | PASS |
| `turnover_volatility_60d_cs` | fwd_ret_5d | 0 | 19845 | 67 | 5395/14450/0 | PASS |
| `volume_shock_5d_cs` | fwd_ret_5d | 0 | 613154 | 1934 | 304865/308289/0 | PASS |
| `amount_concentration_20d_cs` | fwd_ret_5d | 0 | 613154 | 1934 | 304865/308289/0 | PASS |
| `low_volatility_60d_cs` | fwd_ret_5d | 0 | 606020 | 1913 | 297773/308247/0 | PASS |
| `residual_volatility_60d_cs` | fwd_ret_5d | 0 | 596061 | 1884 | 287887/308174/0 | PASS |
| `bollinger_position_20d_cs` | fwd_ret_5d | 0 | 613154 | 1934 | 304865/308289/0 | PASS |
| `price_channel_position_60d_cs` | fwd_ret_5d | 0 | 606360 | 1914 | 298111/308249/0 | PASS |
| `rsi_divergence_14d_cs` | fwd_ret_5d | 0 | 609757 | 1924 | 301488/308269/0 | PASS |
| `revenue_stability_8q_cs` | fwd_ret_5d | 63 | 45921 | 1581 | 21740/24181/0 | PASS |
| `margin_trend_8q_cs` | fwd_ret_5d | 63 | 39978 | 1404 | 15797/24181/0 | PASS |

## Raw vs Mcap-Neutral Comparison (Validation 2021-2024)

| Factor | Raw IC | Neutral IC | Raw ICIR | Neutral ICIR | Raw Net Spread | Neutral Net Spread | Size Dependent |
|---|---:|---:|---:|---:|---:|---|
| `reversal_5_cs` | 0.0045 | 0.0034 |  |  | -0.15% | -0.55% | False |
| `reversal_20_cs` | 0.0123 | -0.0390 |  |  | -0.03% | -1.28% | True |
| `momentum_60_cs` | -0.0133 | -0.0298 |  |  | -0.36% | -0.85% | False |
| `momentum_120_cs` | 0.0148 | -0.0183 |  |  | -0.16% | -0.57% | True |
| `volatility_20_cs` | 0.0577 | 0.0532 |  |  | 0.19% | 0.02% | False |
| `volatility_60_cs` | 0.0605 | 0.0685 |  |  | 0.29% | 0.52% | False |
| `rsi_14_cs` | 0.0038 | -0.0112 |  |  | -0.20% | -0.91% | False |
| `macd_12_26_9_cs` | 0.0046 | -0.0230 |  |  | -0.01% | -0.92% | False |
| `pv_divergence_20_cs` | 0.0256 | -0.0036 |  |  | 0.00% | -0.82% | True |
| `ep_cs` | -0.0831 | -0.1183 |  |  | -0.99% | -1.40% | False |
| `bp_cs` | -0.0927 | -0.1673 |  |  | -1.16% | -2.27% | False |
| `sp_cs` | -0.0672 | -0.1218 |  |  | -0.94% | -2.35% | False |
| `roe_cs` | -0.0226 | -0.0394 |  |  | -0.32% | -0.67% | False |
| `gross_margin_cs` | -0.0218 | -0.0406 |  |  | -0.39% | -0.93% | False |
| `profit_growth_cs` | -0.0196 | 0.0563 |  |  | -0.05% | -1.72% | False |
| `revenue_growth_cs` | -0.0208 | 0.1013 |  |  | -0.33% | 0.81% | False |
| `leverage_cs` | -0.0291 | -0.0159 |  |  | -0.29% | -0.24% | False |
| `log_market_cap_cs` | 0.0120 | 0.0084 |  |  |  |  | False |
| `roe_stability_8q_cs` | -0.0407 | -0.0505 |  |  | -0.44% | -0.75% | False |
| `roa_ttm_cs` | -0.0223 | -0.0328 |  |  | -0.39% | -0.59% | False |
| `gross_margin_ttm_cs` | -0.0222 | -0.0396 |  |  | -0.39% | -0.84% | False |
| `net_margin_ttm_cs` | 0.0091 | -0.0143 |  |  | -0.13% | -0.48% | False |
| `profitability_quality_cs` | -0.0147 | -0.0388 |  |  | -0.39% | -0.74% | False |
| `revenue_growth_ttm_cs` | -0.0208 | 0.1013 |  |  | -0.33% | 0.81% | False |
| `profit_growth_ttm_cs` | -0.0196 | 0.0563 |  |  | -0.05% | -1.72% | False |
| `growth_stability_8q_cs` | -0.0092 | 0.3906 |  |  |  | 2.67% | False |
| `earnings_acceleration_cs` | 0.0279 | 0.0836 |  |  | -0.03% | 1.10% | False |
| `industry_relative_ep_cs` | -0.0593 | -0.1119 |  |  | -0.76% | -1.59% | False |
| `industry_relative_bp_cs` | -0.0719 | -0.1325 |  |  | -1.04% | -2.13% | False |
| `industry_relative_momentum_60_cs` | -0.0064 | -0.0120 |  |  | -0.23% | -0.45% | False |
| `momentum_60_skip5_cs` | 0.0235 | 0.0159 |  |  | 0.18% | -0.32% | False |
| `momentum_120_skip20_cs` | 0.0024 | -0.0182 |  |  | -0.24% | -0.57% | False |
| `risk_adjusted_momentum_60_cs` | 0.0255 | 0.0189 |  |  | 0.19% | -0.41% | False |
| `volume_confirmed_momentum_cs` | 0.0052 | -0.0294 |  |  | -0.26% | -1.04% | False |
| `trend_quality_cs` | 0.0229 | 0.0072 |  |  | 0.01% | -0.80% | True |
| `intraday_reversal_cs` | 0.0006 | -0.0151 |  |  | -0.61% | -0.66% | False |
| `overnight_reversal_cs` | 0.0004 | -0.0199 |  |  | -0.74% | -0.96% | False |
| `amihud_illiq_20d_cs` | -0.0061 | -0.0140 |  |  | -0.17% | -0.26% | False |
| `vol_price_divergence_20d_cs` | 0.0302 | 0.0030 |  |  | -0.12% | -1.02% | True |
| `volatility_squeeze_cs` | 0.0054 | -0.0082 |  |  | -0.17% | -0.93% | False |
| `tail_risk_60d_cs` | 0.0319 | 0.0216 |  |  | 0.19% | -0.22% | False |
| `turnover_anomaly_20d_cs` | -0.0277 | -0.0344 |  |  | -0.14% | -0.31% | False |
| `turnover_volatility_60d_cs` | -0.0056 | -0.0184 |  |  | 0.00% | -0.14% | False |
| `volume_shock_5d_cs` | -0.0013 | -0.0057 |  |  | -0.29% | -0.94% | False |
| `amount_concentration_20d_cs` | 0.0173 | -0.0023 |  |  | -0.06% | -0.99% | True |
| `low_volatility_60d_cs` | 0.0650 | 0.0682 |  |  | 0.34% | 0.36% | False |
| `residual_volatility_60d_cs` | 0.0660 | 0.0786 |  |  | 0.43% | 0.59% | False |
| `bollinger_position_20d_cs` | 0.0088 | -0.0124 |  |  | -0.25% | -0.93% | False |
| `price_channel_position_60d_cs` | -0.0201 | -0.0073 |  |  | -0.25% | -0.26% | False |
| `rsi_divergence_14d_cs` | -0.0018 | 0.0238 |  |  | -0.24% | -0.32% | False |
| `revenue_stability_8q_cs` | -0.0398 | 0.1531 |  |  | -0.12% | -0.13% | False |
| `margin_trend_8q_cs` | -0.0057 | -0.0740 |  |  | 0.04% | -0.76% | False |

## Turnover Cost Analysis (Validation 2021-2024)

| Factor | Basis | Method | Avg Turnover | Gross Spread | Net Spread | Net/Gross |
|---|---:|---:|---:|---:|---:|
| `amihud_illiq_20d_cs` | raw | REAL_WEIGHT_DRIFT | 33.4% | -0.07% | -0.13% | 139.5% |
| `amount_concentration_20d_cs` | raw | REAL_WEIGHT_DRIFT | 89.6% | -0.19% | -0.37% | 106.1% |
| `bollinger_position_20d_cs` | raw | REAL_WEIGHT_DRIFT | 108.7% | -0.17% | -0.39% | 176.3% |
| `bp_cs` | raw | REAL_WEIGHT_DRIFT | 37.0% | -1.50% | -1.57% | 103.5% |
| `earnings_acceleration_cs` | raw | REAL_WEIGHT_DRIFT | 3.6% | -0.02% | -0.03% | 103.4% |
| `ep_cs` | raw | REAL_WEIGHT_DRIFT | 45.6% | -1.03% | -1.12% | 104.8% |
| `gross_margin_cs` | raw | REAL_WEIGHT_DRIFT | 6.5% | -0.63% | -0.64% | 104.2% |
| `gross_margin_ttm_cs` | raw | REAL_WEIGHT_DRIFT | 6.5% | -0.58% | -0.59% | 105.1% |
| `growth_stability_8q_cs` | raw | NOT_AVAILABLE |  |  |  |  |
| `industry_relative_bp_cs` | raw | REAL_WEIGHT_DRIFT | 39.7% | -1.44% | -1.52% | 103.0% |
| `industry_relative_ep_cs` | raw | REAL_WEIGHT_DRIFT | 58.8% | -0.93% | -1.05% | 116.4% |
| `industry_relative_momentum_60_cs` | raw | REAL_WEIGHT_DRIFT | 65.6% | -0.04% | -0.17% | 141.3% |
| `intraday_reversal_cs` | raw | REAL_WEIGHT_DRIFT | 153.8% | -0.01% | -0.32% | 597.6% |
| `leverage_cs` | raw | REAL_WEIGHT_DRIFT | 8.3% | -0.22% | -0.24% | 104.3% |
| `low_volatility_60d_cs` | raw | REAL_WEIGHT_DRIFT | 27.8% | 0.41% | 0.35% | 85.1% |
| `macd_12_26_9_cs` | raw | REAL_WEIGHT_DRIFT | 90.8% | -0.09% | -0.27% | 82.7% |
| `margin_trend_8q_cs` | raw | REAL_WEIGHT_DRIFT | 3.1% | 0.05% | 0.05% | 97.4% |
| `momentum_120_cs` | raw | REAL_WEIGHT_DRIFT | 46.6% | -0.13% | -0.22% | 95.7% |
| `momentum_120_skip20_cs` | raw | REAL_WEIGHT_DRIFT | 47.3% | -0.16% | -0.25% | 103.4% |
| `momentum_60_cs` | raw | REAL_WEIGHT_DRIFT | 60.2% | -0.30% | -0.42% | 132.3% |
| `momentum_60_skip5_cs` | raw | REAL_WEIGHT_DRIFT | 61.0% | 0.12% | -0.00% | 123.3% |
| `net_margin_ttm_cs` | raw | REAL_WEIGHT_DRIFT | 7.3% | -0.27% | -0.28% | 102.8% |
| `overnight_reversal_cs` | raw | REAL_WEIGHT_DRIFT | 153.0% | -0.25% | -0.56% | 115.7% |
| `price_channel_position_60d_cs` | raw | REAL_WEIGHT_DRIFT | 82.6% | 0.09% | -0.07% | 70.9% |
| `profit_growth_cs` | raw | REAL_WEIGHT_DRIFT | 3.5% | -0.03% | -0.04% | 98.9% |
| `profit_growth_ttm_cs` | raw | REAL_WEIGHT_DRIFT | 3.5% | -0.03% | -0.04% | 98.9% |
| `profitability_quality_cs` | raw | REAL_WEIGHT_DRIFT | 6.2% | -0.53% | -0.55% | 100.5% |
| `pv_divergence_20_cs` | raw | REAL_WEIGHT_DRIFT | 90.1% | -0.08% | -0.26% | 32.9% |
| `residual_volatility_60d_cs` | raw | REAL_WEIGHT_DRIFT | 29.1% | 0.59% | 0.53% | 99.9% |
| `revenue_growth_cs` | raw | REAL_WEIGHT_DRIFT | 5.0% | -0.32% | -0.33% | 98.8% |
| `revenue_growth_ttm_cs` | raw | REAL_WEIGHT_DRIFT | 5.0% | -0.32% | -0.33% | 98.8% |
| `revenue_stability_8q_cs` | raw | NOT_AVAILABLE |  |  |  |  |
| `reversal_20_cs` | raw | REAL_WEIGHT_DRIFT | 95.3% | -0.27% | -0.46% | 64.8% |
| `reversal_5_cs` | raw | REAL_WEIGHT_DRIFT | 114.0% | 0.09% | -0.14% | 84.4% |
| `risk_adjusted_momentum_60_cs` | raw | REAL_WEIGHT_DRIFT | 61.1% | 0.08% | -0.04% | 86.5% |
| `roa_ttm_cs` | raw | REAL_WEIGHT_DRIFT | 10.0% | -0.47% | -0.49% | 102.1% |
| `roe_cs` | raw | REAL_WEIGHT_DRIFT | 13.4% | -0.46% | -0.48% | 104.3% |
| `roe_stability_8q_cs` | raw | REAL_WEIGHT_DRIFT | 9.7% | -0.57% | -0.59% | 107.5% |
| `rsi_14_cs` | raw | REAL_WEIGHT_DRIFT | 104.4% | -0.15% | -0.35% | 148.8% |
| `rsi_divergence_14d_cs` | raw | REAL_WEIGHT_DRIFT | 118.7% | 0.19% | -0.05% | 81.6% |
| `sp_cs` | raw | REAL_WEIGHT_DRIFT | 35.2% | -1.54% | -1.61% | 102.8% |
| `tail_risk_60d_cs` | raw | REAL_WEIGHT_DRIFT | 51.6% | 0.14% | 0.04% | 86.3% |
| `trend_quality_cs` | raw | REAL_WEIGHT_DRIFT | 82.8% | -0.08% | -0.25% | 57.9% |
| `turnover_anomaly_20d_cs` | raw | REAL_WEIGHT_DRIFT | 14.9% | -0.08% | -0.11% | 106.6% |
| `turnover_volatility_60d_cs` | raw | REAL_WEIGHT_DRIFT | 13.8% | 0.05% | 0.03% | 96.6% |
| `vol_price_divergence_20d_cs` | raw | REAL_WEIGHT_DRIFT | 96.9% | -0.22% | -0.41% | -115.8% |
| `volatility_20_cs` | raw | REAL_WEIGHT_DRIFT | 58.7% | 0.31% | 0.19% | 74.0% |
| `volatility_60_cs` | raw | REAL_WEIGHT_DRIFT | 31.2% | 0.48% | 0.42% | 101.2% |
| `volatility_squeeze_cs` | raw | REAL_WEIGHT_DRIFT | 98.7% | -0.14% | -0.34% | 163.9% |
| `volume_confirmed_momentum_cs` | raw | REAL_WEIGHT_DRIFT | 115.4% | -0.18% | -0.41% | 120.2% |
| `volume_shock_5d_cs` | raw | REAL_WEIGHT_DRIFT | 105.2% | -0.19% | -0.40% | 211.5% |

## IC Trend (Validation Window)

| Factor | Basis | Monthly ICs | Slope | p-value | Declining |
|---|---:|---:|---:|---|
| `reversal_5_cs` | raw | 48 | -0.000506 | 0.4148 | False |
| `reversal_5_cs` | mcap_neutral | 45 | -0.000584 | 0.7666 | False |
| `reversal_20_cs` | raw | 48 | 0.000273 | 0.7859 | False |
| `reversal_20_cs` | mcap_neutral | 45 | -0.001034 | 0.5863 | False |
| `momentum_60_cs` | raw | 48 | 0.000775 | 0.4985 | False |
| `momentum_60_cs` | mcap_neutral | 45 | 0.000760 | 0.7595 | False |
| `momentum_120_cs` | raw | 44 | 0.000796 | 0.5452 | False |
| `momentum_120_cs` | mcap_neutral | 41 | 0.000704 | 0.7895 | False |
| `volatility_20_cs` | raw | 48 | -0.001140 | 0.3396 | False |
| `volatility_20_cs` | mcap_neutral | 45 | 0.003068 | 0.1663 | False |
| `volatility_60_cs` | raw | 48 | -0.001392 | 0.2881 | False |
| `volatility_60_cs` | mcap_neutral | 45 | 0.002170 | 0.3631 | False |
| `rsi_14_cs` | raw | 48 | 0.000150 | 0.8486 | False |
| `rsi_14_cs` | mcap_neutral | 45 | 0.001554 | 0.3182 | False |
| `macd_12_26_9_cs` | raw | 48 | -0.000039 | 0.9585 | False |
| `macd_12_26_9_cs` | mcap_neutral | 45 | -0.000482 | 0.7628 | False |
| `pv_divergence_20_cs` | raw | 48 | 0.000634 | 0.3207 | False |
| `pv_divergence_20_cs` | mcap_neutral | 45 | 0.000922 | 0.5363 | False |
| `ep_cs` | raw | 33 | 0.002892 | 0.3667 | False |
| `ep_cs` | mcap_neutral | 6 |  |  | False |
| `bp_cs` | raw | 33 | 0.003273 | 0.3599 | False |
| `bp_cs` | mcap_neutral | 6 |  |  | False |
| `sp_cs` | raw | 33 | 0.002083 | 0.3770 | False |
| `sp_cs` | mcap_neutral | 6 |  |  | False |
| `roe_cs` | raw | 48 | -0.000180 | 0.8185 | False |
| `roe_cs` | mcap_neutral | 44 | 0.002341 | 0.1738 | False |
| `gross_margin_cs` | raw | 48 | -0.000025 | 0.9765 | False |
| `gross_margin_cs` | mcap_neutral | 44 | 0.002289 | 0.1615 | False |
| `profit_growth_cs` | raw | 48 | 0.000214 | 0.8214 | False |
| `profit_growth_cs` | mcap_neutral | 1 |  |  | False |
| `revenue_growth_cs` | raw | 48 | -0.000503 | 0.5694 | False |
| `revenue_growth_cs` | mcap_neutral | 1 |  |  | False |
| `leverage_cs` | raw | 48 | 0.000530 | 0.6140 | False |
| `leverage_cs` | mcap_neutral | 44 | -0.001705 | 0.4464 | False |
| `log_market_cap_cs` | raw | 45 | 0.000948 | 0.6382 | False |
| `log_market_cap_cs` | mcap_neutral | 45 | -0.000249 | 0.8991 | False |
| `roe_stability_8q_cs` | raw | 48 | -0.000150 | 0.8581 | False |
| `roe_stability_8q_cs` | mcap_neutral | 44 | 0.000705 | 0.6971 | False |
| `roa_ttm_cs` | raw | 48 | 0.000297 | 0.7314 | False |
| `roa_ttm_cs` | mcap_neutral | 44 | 0.002744 | 0.1477 | False |
| `gross_margin_ttm_cs` | raw | 48 | -0.000010 | 0.9904 | False |
| `gross_margin_ttm_cs` | mcap_neutral | 44 | 0.002236 | 0.1687 | False |
| `net_margin_ttm_cs` | raw | 48 | 0.000753 | 0.1613 | False |
| `net_margin_ttm_cs` | mcap_neutral | 44 | 0.002505 | 0.0266 | False |
| `profitability_quality_cs` | raw | 48 | 0.000083 | 0.9021 | False |
| `profitability_quality_cs` | mcap_neutral | 44 | 0.002363 | 0.0876 | False |
| `revenue_growth_ttm_cs` | raw | 48 | -0.000503 | 0.5694 | False |
| `revenue_growth_ttm_cs` | mcap_neutral | 1 |  |  | False |
| `profit_growth_ttm_cs` | raw | 48 | 0.000214 | 0.8214 | False |
| `profit_growth_ttm_cs` | mcap_neutral | 1 |  |  | False |
| `growth_stability_8q_cs` | raw | 48 | 0.000204 | 0.8863 | False |
| `growth_stability_8q_cs` | mcap_neutral | 1 |  |  | False |
| `earnings_acceleration_cs` | raw | 48 | -0.000218 | 0.8049 | False |
| `earnings_acceleration_cs` | mcap_neutral | 1 |  |  | False |
| `industry_relative_ep_cs` | raw | 33 | 0.003446 | 0.1733 | False |
| `industry_relative_ep_cs` | mcap_neutral | 6 |  |  | False |
| `industry_relative_bp_cs` | raw | 33 | 0.003547 | 0.2188 | False |
| `industry_relative_bp_cs` | mcap_neutral | 6 |  |  | False |
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
| `intraday_reversal_cs` | raw | 48 | -0.001352 | 0.0935 | True |
| `intraday_reversal_cs` | mcap_neutral | 45 | -0.002369 | 0.1653 | False |
| `overnight_reversal_cs` | raw | 48 | 0.000953 | 0.0159 | False |
| `overnight_reversal_cs` | mcap_neutral | 45 | 0.001750 | 0.1852 | False |
| `amihud_illiq_20d_cs` | raw | 48 | -0.000786 | 0.2809 | False |
| `amihud_illiq_20d_cs` | mcap_neutral | 45 | -0.000502 | 0.6750 | False |
| `vol_price_divergence_20d_cs` | raw | 48 | 0.000990 | 0.1247 | False |
| `vol_price_divergence_20d_cs` | mcap_neutral | 45 | 0.000282 | 0.8162 | False |
| `volatility_squeeze_cs` | raw | 48 | -0.000018 | 0.9767 | False |
| `volatility_squeeze_cs` | mcap_neutral | 45 | -0.000047 | 0.9744 | False |
| `tail_risk_60d_cs` | raw | 48 | -0.000306 | 0.5840 | False |
| `tail_risk_60d_cs` | mcap_neutral | 45 | -0.000693 | 0.6515 | False |
| `turnover_anomaly_20d_cs` | raw | 45 | -0.001452 | 0.5558 | False |
| `turnover_anomaly_20d_cs` | mcap_neutral | 45 | -0.001988 | 0.3495 | False |
| `turnover_volatility_60d_cs` | raw | 45 | -0.001622 | 0.4373 | False |
| `turnover_volatility_60d_cs` | mcap_neutral | 45 | -0.002664 | 0.0972 | True |
| `volume_shock_5d_cs` | raw | 48 | -0.001359 | 0.0832 | True |
| `volume_shock_5d_cs` | mcap_neutral | 45 | -0.000033 | 0.9819 | False |
| `amount_concentration_20d_cs` | raw | 48 | -0.000380 | 0.4553 | False |
| `amount_concentration_20d_cs` | mcap_neutral | 45 | -0.000809 | 0.4948 | False |
| `low_volatility_60d_cs` | raw | 48 | 0.001514 | 0.2593 | False |
| `low_volatility_60d_cs` | mcap_neutral | 45 | -0.001804 | 0.4558 | False |
| `residual_volatility_60d_cs` | raw | 48 | -0.001464 | 0.2032 | False |
| `residual_volatility_60d_cs` | mcap_neutral | 45 | 0.001619 | 0.4503 | False |
| `bollinger_position_20d_cs` | raw | 48 | -0.000172 | 0.8556 | False |
| `bollinger_position_20d_cs` | mcap_neutral | 45 | 0.001305 | 0.4269 | False |
| `price_channel_position_60d_cs` | raw | 48 | 0.000932 | 0.3818 | False |
| `price_channel_position_60d_cs` | mcap_neutral | 45 | 0.000820 | 0.6767 | False |
| `rsi_divergence_14d_cs` | raw | 48 | 0.000006 | 0.9944 | False |
| `rsi_divergence_14d_cs` | mcap_neutral | 45 | 0.000505 | 0.7887 | False |
| `revenue_stability_8q_cs` | raw | 48 | 0.001379 | 0.2404 | False |
| `revenue_stability_8q_cs` | mcap_neutral | 1 |  |  | False |
| `margin_trend_8q_cs` | raw | 48 | 0.000811 | 0.3852 | False |
| `margin_trend_8q_cs` | mcap_neutral | 1 |  |  | False |

## Rolling Window Robustness

| Factor | Window | Basis | Status | Mean IC | ICIR | Net Spread | Pos IC Yrs | Pos Spread Yrs |
|---|---:|---:|---:|---:|---:|---:|---:|
| `reversal_5_cs` | 2018_2021 | raw | FAIL | 0.0219 | 0.130 | -0.11% | 4/4 | 0/4 |
| `reversal_5_cs` | 2019_2022 | raw | FAIL | 0.0203 | 0.120 | -0.08% | 4/4 | 1/4 |
| `reversal_5_cs` | 2020_2023 | raw | FAIL | 0.0071 | 0.035 | -0.19% | 3/4 | 1/4 |
| `reversal_5_cs` | 2021_2024 | raw | FAIL | 0.0045 | 0.016 | -0.15% | 3/4 | 1/4 |
| `reversal_20_cs` | 2018_2021 | raw | FAIL | 0.0191 | 0.108 | -0.09% | 4/4 | 2/4 |
| `reversal_20_cs` | 2019_2022 | raw | FAIL | 0.0205 | 0.114 | -0.04% | 4/4 | 2/4 |
| `reversal_20_cs` | 2020_2023 | raw | FAIL | 0.0131 | 0.066 | -0.07% | 4/4 | 1/4 |
| `reversal_20_cs` | 2021_2024 | raw | FAIL | 0.0123 | 0.062 | -0.03% | 3/4 | 1/4 |
| `momentum_60_cs` | 2018_2021 | raw | FAIL | 0.0140 | 0.092 | 0.08% | 3/4 | 3/4 |
| `momentum_60_cs` | 2019_2022 | raw | FAIL | -0.0018 | 0.004 | -0.13% | 2/4 | 2/4 |
| `momentum_60_cs` | 2020_2023 | raw | FAIL | -0.0015 | -0.004 | -0.11% | 2/4 | 2/4 |
| `momentum_60_cs` | 2021_2024 | raw | FAIL | -0.0133 | -0.062 | -0.36% | 1/4 | 1/4 |
| `momentum_120_cs` | 2018_2021 | raw | FAIL | 0.0243 | 0.142 | 0.21% | 4/4 | 3/4 |
| `momentum_120_cs` | 2019_2022 | raw | FAIL | 0.0137 | 0.087 | 0.08% | 3/4 | 3/4 |
| `momentum_120_cs` | 2020_2023 | raw | FAIL | 0.0217 | 0.105 | 0.15% | 3/4 | 3/4 |
| `momentum_120_cs` | 2021_2024 | raw | FAIL | 0.0148 | 0.066 | -0.16% | 3/4 | 2/4 |
| `volatility_20_cs` | 2018_2021 | raw | FAIL | 0.0100 | 0.050 | -0.25% | 3/4 | 2/4 |
| `volatility_20_cs` | 2019_2022 | raw | FAIL | 0.0139 | 0.067 | -0.27% | 3/4 | 2/4 |
| `volatility_20_cs` | 2020_2023 | raw | FAIL | 0.0352 | 0.192 | -0.06% | 3/4 | 3/4 |
| `volatility_20_cs` | 2021_2024 | raw | PASS | 0.0577 | 0.277 | 0.19% | 4/4 | 4/4 |
| `volatility_60_cs` | 2018_2021 | raw | FAIL | 0.0080 | 0.040 | -0.27% | 3/4 | 1/4 |
| `volatility_60_cs` | 2019_2022 | raw | FAIL | 0.0120 | 0.055 | -0.25% | 3/4 | 1/4 |
| `volatility_60_cs` | 2020_2023 | raw | FAIL | 0.0332 | 0.164 | -0.01% | 3/4 | 2/4 |
| `volatility_60_cs` | 2021_2024 | raw | PASS | 0.0605 | 0.256 | 0.29% | 4/4 | 3/4 |
| `rsi_14_cs` | 2018_2021 | raw | FAIL | 0.0046 | 0.032 | -0.28% | 2/4 | 0/4 |
| `rsi_14_cs` | 2019_2022 | raw | FAIL | 0.0120 | 0.072 | -0.19% | 3/4 | 1/4 |
| `rsi_14_cs` | 2020_2023 | raw | FAIL | 0.0040 | 0.022 | -0.25% | 3/4 | 1/4 |
| `rsi_14_cs` | 2021_2024 | raw | FAIL | 0.0038 | 0.023 | -0.20% | 3/4 | 1/4 |
| `macd_12_26_9_cs` | 2018_2021 | raw | FAIL | 0.0053 | 0.039 | -0.01% | 3/4 | 2/4 |
| `macd_12_26_9_cs` | 2019_2022 | raw | FAIL | 0.0053 | 0.038 | -0.00% | 3/4 | 2/4 |
| `macd_12_26_9_cs` | 2020_2023 | raw | FAIL | 0.0119 | 0.079 | 0.07% | 3/4 | 3/4 |
| `macd_12_26_9_cs` | 2021_2024 | raw | FAIL | 0.0046 | 0.035 | -0.01% | 2/4 | 2/4 |
| `pv_divergence_20_cs` | 2018_2021 | raw | FAIL | 0.0324 | 0.234 | 0.09% | 4/4 | 2/4 |
| `pv_divergence_20_cs` | 2019_2022 | raw | FAIL | 0.0282 | 0.214 | 0.07% | 4/4 | 2/4 |
| `pv_divergence_20_cs` | 2020_2023 | raw | FAIL | 0.0221 | 0.157 | -0.04% | 4/4 | 1/4 |
| `pv_divergence_20_cs` | 2021_2024 | raw | FAIL | 0.0256 | 0.176 | 0.00% | 4/4 | 2/4 |
| `ep_cs` | 2018_2021 | raw | FAIL | -0.0086 | -0.031 | -0.17% | 2/4 | 2/4 |
| `ep_cs` | 2019_2022 | raw | FAIL | -0.0177 | -0.063 | -0.20% | 2/4 | 2/4 |
| `ep_cs` | 2020_2023 | raw | FAIL | -0.0511 | -0.231 | -0.61% | 1/4 | 1/4 |
| `ep_cs` | 2021_2024 | raw | FAIL | -0.0831 | -0.390 | -0.99% | 0/4 | 0/4 |
| `bp_cs` | 2018_2021 | raw | FAIL | -0.0146 | -0.063 | -0.35% | 2/4 | 2/4 |
| `bp_cs` | 2019_2022 | raw | FAIL | -0.0233 | -0.099 | -0.35% | 2/4 | 2/4 |
| `bp_cs` | 2020_2023 | raw | FAIL | -0.0637 | -0.361 | -0.88% | 1/4 | 1/4 |
| `bp_cs` | 2021_2024 | raw | FAIL | -0.0927 | -0.479 | -1.16% | 0/4 | 0/4 |
| `sp_cs` | 2018_2021 | raw | FAIL | -0.0139 | -0.132 | -0.37% | 2/4 | 2/4 |
| `sp_cs` | 2019_2022 | raw | FAIL | -0.0120 | -0.089 | -0.36% | 2/4 | 2/4 |
| `sp_cs` | 2020_2023 | raw | FAIL | -0.0407 | -0.256 | -0.72% | 1/4 | 1/4 |
| `sp_cs` | 2021_2024 | raw | FAIL | -0.0672 | -0.402 | -0.94% | 0/4 | 0/4 |
| `roe_cs` | 2018_2021 | raw | FAIL | 0.0209 | 0.139 | 0.00% | 3/4 | 2/4 |
| `roe_cs` | 2019_2022 | raw | FAIL | 0.0144 | 0.097 | 0.01% | 2/4 | 2/4 |
| `roe_cs` | 2020_2023 | raw | FAIL | -0.0054 | -0.033 | -0.16% | 1/4 | 1/4 |
| `roe_cs` | 2021_2024 | raw | FAIL | -0.0226 | -0.157 | -0.32% | 0/4 | 0/4 |
| `gross_margin_cs` | 2018_2021 | raw | FAIL | 0.0230 | 0.163 | -0.02% | 3/4 | 3/4 |
| `gross_margin_cs` | 2019_2022 | raw | FAIL | 0.0151 | 0.112 | -0.11% | 2/4 | 2/4 |
| `gross_margin_cs` | 2020_2023 | raw | FAIL | -0.0014 | -0.008 | -0.27% | 1/4 | 1/4 |
| `gross_margin_cs` | 2021_2024 | raw | FAIL | -0.0218 | -0.131 | -0.39% | 0/4 | 0/4 |
| `profit_growth_cs` | 2018_2021 | raw | FAIL | 0.0441 | 0.214 | -0.26% | 3/4 | 1/4 |
| `profit_growth_cs` | 2019_2022 | raw | FAIL | 0.0230 | 0.109 | -0.07% | 3/4 | 2/4 |
| `profit_growth_cs` | 2020_2023 | raw | FAIL | -0.0010 | -0.128 | -0.08% | 2/4 | 2/4 |
| `profit_growth_cs` | 2021_2024 | raw | FAIL | -0.0196 | -0.209 | -0.05% | 2/4 | 2/4 |
| `revenue_growth_cs` | 2018_2021 | raw | PASS | 0.0664 | 0.265 | 0.30% | 3/4 | 3/4 |
| `revenue_growth_cs` | 2019_2022 | raw | FAIL | 0.0469 | 0.175 | 0.08% | 3/4 | 3/4 |
| `revenue_growth_cs` | 2020_2023 | raw | FAIL | 0.0212 | 0.005 | -0.06% | 2/4 | 2/4 |
| `revenue_growth_cs` | 2021_2024 | raw | FAIL | -0.0208 | -0.166 | -0.33% | 1/4 | 1/4 |
| `leverage_cs` | 2018_2021 | raw | FAIL | 0.0030 | 0.019 | -0.00% | 2/4 | 2/4 |
| `leverage_cs` | 2019_2022 | raw | FAIL | -0.0042 | -0.013 | -0.05% | 2/4 | 2/4 |
| `leverage_cs` | 2020_2023 | raw | FAIL | -0.0115 | -0.055 | -0.16% | 1/4 | 1/4 |
| `leverage_cs` | 2021_2024 | raw | FAIL | -0.0291 | -0.143 | -0.29% | 0/4 | 0/4 |
| `log_market_cap_cs` | 2018_2021 | raw | NOT_AVAILABLE |  |  |  | 0/4 | 0/4 |
| `log_market_cap_cs` | 2019_2022 | raw | NOT_AVAILABLE |  |  |  | 0/4 | 0/4 |
| `log_market_cap_cs` | 2020_2023 | raw | NOT_AVAILABLE |  |  |  | 0/4 | 0/4 |
| `log_market_cap_cs` | 2021_2024 | raw | NOT_AVAILABLE |  |  |  | 0/4 | 0/4 |
| `roe_stability_8q_cs` | 2018_2021 | raw | FAIL | 0.0162 | 0.119 | -0.01% | 3/4 | 2/4 |
| `roe_stability_8q_cs` | 2019_2022 | raw | FAIL | 0.0038 | 0.037 | -0.07% | 2/4 | 2/4 |
| `roe_stability_8q_cs` | 2020_2023 | raw | FAIL | -0.0206 | -0.125 | -0.33% | 1/4 | 1/4 |
| `roe_stability_8q_cs` | 2021_2024 | raw | FAIL | -0.0407 | -0.256 | -0.44% | 0/4 | 0/4 |
| `roa_ttm_cs` | 2018_2021 | raw | FAIL | 0.0200 | 0.133 | -0.05% | 3/4 | 2/4 |
| `roa_ttm_cs` | 2019_2022 | raw | FAIL | 0.0139 | 0.093 | -0.12% | 2/4 | 2/4 |
| `roa_ttm_cs` | 2020_2023 | raw | FAIL | -0.0012 | -0.006 | -0.25% | 1/4 | 1/4 |
| `roa_ttm_cs` | 2021_2024 | raw | FAIL | -0.0223 | -0.143 | -0.39% | 0/4 | 0/4 |
| `gross_margin_ttm_cs` | 2018_2021 | raw | FAIL | 0.0228 | 0.163 | -0.01% | 3/4 | 3/4 |
| `gross_margin_ttm_cs` | 2019_2022 | raw | FAIL | 0.0144 | 0.109 | -0.12% | 2/4 | 2/4 |
| `gross_margin_ttm_cs` | 2020_2023 | raw | FAIL | -0.0019 | -0.010 | -0.26% | 1/4 | 1/4 |
| `gross_margin_ttm_cs` | 2021_2024 | raw | FAIL | -0.0223 | -0.133 | -0.39% | 0/4 | 0/4 |
| `net_margin_ttm_cs` | 2018_2021 | raw | FAIL | 0.0183 | 0.172 | -0.09% | 3/4 | 2/4 |
| `net_margin_ttm_cs` | 2019_2022 | raw | FAIL | 0.0173 | 0.166 | -0.15% | 3/4 | 1/4 |
| `net_margin_ttm_cs` | 2020_2023 | raw | FAIL | 0.0147 | 0.127 | -0.17% | 3/4 | 1/4 |
| `net_margin_ttm_cs` | 2021_2024 | raw | FAIL | 0.0091 | 0.083 | -0.13% | 3/4 | 2/4 |
| `profitability_quality_cs` | 2018_2021 | raw | FAIL | 0.0225 | 0.188 | -0.02% | 3/4 | 2/4 |
| `profitability_quality_cs` | 2019_2022 | raw | FAIL | 0.0157 | 0.134 | -0.10% | 2/4 | 2/4 |
| `profitability_quality_cs` | 2020_2023 | raw | FAIL | 0.0031 | 0.026 | -0.23% | 2/4 | 1/4 |
| `profitability_quality_cs` | 2021_2024 | raw | FAIL | -0.0147 | -0.116 | -0.39% | 1/4 | 0/4 |
| `asset_turnover_ttm_cs` | 2018_2021 | raw | NOT_AVAILABLE |  |  |  | 0/4 | 0/4 |
| `asset_turnover_ttm_cs` | 2019_2022 | raw | NOT_AVAILABLE |  |  |  | 0/4 | 0/4 |
| `asset_turnover_ttm_cs` | 2020_2023 | raw | NOT_AVAILABLE |  |  |  | 0/4 | 0/4 |
| `asset_turnover_ttm_cs` | 2021_2024 | raw | NOT_AVAILABLE |  |  |  | 0/4 | 0/4 |
| `revenue_growth_ttm_cs` | 2018_2021 | raw | PASS | 0.0901 | 0.265 | 0.30% | 4/4 | 3/4 |
| `revenue_growth_ttm_cs` | 2019_2022 | raw | FAIL | 0.0469 | 0.175 | 0.08% | 3/4 | 3/4 |
| `revenue_growth_ttm_cs` | 2020_2023 | raw | FAIL | 0.0212 | 0.005 | -0.06% | 2/4 | 2/4 |
| `revenue_growth_ttm_cs` | 2021_2024 | raw | FAIL | -0.0208 | -0.166 | -0.33% | 1/4 | 1/4 |
| `profit_growth_ttm_cs` | 2018_2021 | raw | FAIL | 0.0151 | 0.214 | -0.26% | 3/4 | 1/4 |
| `profit_growth_ttm_cs` | 2019_2022 | raw | FAIL | 0.0230 | 0.109 | -0.07% | 3/4 | 2/4 |
| `profit_growth_ttm_cs` | 2020_2023 | raw | FAIL | -0.0010 | -0.128 | -0.08% | 2/4 | 2/4 |
| `profit_growth_ttm_cs` | 2021_2024 | raw | FAIL | -0.0196 | -0.209 | -0.05% | 2/4 | 2/4 |
| `growth_stability_8q_cs` | 2018_2021 | raw | FAIL | 0.0050 | 0.033 | 0.85% | 3/4 | 1/4 |
| `growth_stability_8q_cs` | 2019_2022 | raw | FAIL | -0.0329 | -0.120 | -0.78% | 2/4 | 0/4 |
| `growth_stability_8q_cs` | 2020_2023 | raw | FAIL | -0.0125 | 0.059 | -0.04% | 2/4 | 0/4 |
| `growth_stability_8q_cs` | 2021_2024 | raw | FAIL | -0.0091 | 0.074 |  | 2/4 | 0/4 |
| `growth_value_match_cs` | 2018_2021 | raw | NOT_AVAILABLE |  |  |  | 0/4 | 0/4 |
| `growth_value_match_cs` | 2019_2022 | raw | NOT_AVAILABLE |  |  |  | 0/4 | 0/4 |
| `growth_value_match_cs` | 2020_2023 | raw | NOT_AVAILABLE |  |  |  | 0/4 | 0/4 |
| `growth_value_match_cs` | 2021_2024 | raw | NOT_AVAILABLE |  |  |  | 0/4 | 0/4 |
| `earnings_acceleration_cs` | 2018_2021 | raw | FAIL | -0.0521 | -0.327 | -0.22% | 1/4 | 1/4 |
| `earnings_acceleration_cs` | 2019_2022 | raw | FAIL | -0.0305 | -0.202 | -0.22% | 2/4 | 1/4 |
| `earnings_acceleration_cs` | 2020_2023 | raw | FAIL | -0.0210 | -0.138 | -0.17% | 2/4 | 1/4 |
| `earnings_acceleration_cs` | 2021_2024 | raw | FAIL | 0.0279 | 0.162 | -0.03% | 3/4 | 1/4 |
| `ocf_to_mktcap_cs` | 2018_2021 | raw | NOT_AVAILABLE |  |  |  | 0/4 | 0/4 |
| `ocf_to_mktcap_cs` | 2019_2022 | raw | NOT_AVAILABLE |  |  |  | 0/4 | 0/4 |
| `ocf_to_mktcap_cs` | 2020_2023 | raw | NOT_AVAILABLE |  |  |  | 0/4 | 0/4 |
| `ocf_to_mktcap_cs` | 2021_2024 | raw | NOT_AVAILABLE |  |  |  | 0/4 | 0/4 |
| `ocf_to_profit_cs` | 2018_2021 | raw | NOT_AVAILABLE |  |  |  | 0/4 | 0/4 |
| `ocf_to_profit_cs` | 2019_2022 | raw | NOT_AVAILABLE |  |  |  | 0/4 | 0/4 |
| `ocf_to_profit_cs` | 2020_2023 | raw | NOT_AVAILABLE |  |  |  | 0/4 | 0/4 |
| `ocf_to_profit_cs` | 2021_2024 | raw | NOT_AVAILABLE |  |  |  | 0/4 | 0/4 |
| `fcf_yield_cs` | 2018_2021 | raw | NOT_AVAILABLE |  |  |  | 0/4 | 0/4 |
| `fcf_yield_cs` | 2019_2022 | raw | NOT_AVAILABLE |  |  |  | 0/4 | 0/4 |
| `fcf_yield_cs` | 2020_2023 | raw | NOT_AVAILABLE |  |  |  | 0/4 | 0/4 |
| `fcf_yield_cs` | 2021_2024 | raw | NOT_AVAILABLE |  |  |  | 0/4 | 0/4 |
| `cashflow_stability_8q_cs` | 2018_2021 | raw | NOT_AVAILABLE |  |  |  | 0/4 | 0/4 |
| `cashflow_stability_8q_cs` | 2019_2022 | raw | NOT_AVAILABLE |  |  |  | 0/4 | 0/4 |
| `cashflow_stability_8q_cs` | 2020_2023 | raw | NOT_AVAILABLE |  |  |  | 0/4 | 0/4 |
| `cashflow_stability_8q_cs` | 2021_2024 | raw | NOT_AVAILABLE |  |  |  | 0/4 | 0/4 |
| `accrual_quality_cs` | 2018_2021 | raw | NOT_AVAILABLE |  |  |  | 0/4 | 0/4 |
| `accrual_quality_cs` | 2019_2022 | raw | NOT_AVAILABLE |  |  |  | 0/4 | 0/4 |
| `accrual_quality_cs` | 2020_2023 | raw | NOT_AVAILABLE |  |  |  | 0/4 | 0/4 |
| `accrual_quality_cs` | 2021_2024 | raw | NOT_AVAILABLE |  |  |  | 0/4 | 0/4 |
| `receivable_pressure_cs` | 2018_2021 | raw | NOT_AVAILABLE |  |  |  | 0/4 | 0/4 |
| `receivable_pressure_cs` | 2019_2022 | raw | NOT_AVAILABLE |  |  |  | 0/4 | 0/4 |
| `receivable_pressure_cs` | 2020_2023 | raw | NOT_AVAILABLE |  |  |  | 0/4 | 0/4 |
| `receivable_pressure_cs` | 2021_2024 | raw | NOT_AVAILABLE |  |  |  | 0/4 | 0/4 |
| `industry_relative_ep_cs` | 2018_2021 | raw | FAIL | -0.0068 | 0.037 | -0.11% | 2/4 | 3/4 |
| `industry_relative_ep_cs` | 2019_2022 | raw | FAIL | -0.0159 | -0.009 | -0.20% | 2/4 | 2/4 |
| `industry_relative_ep_cs` | 2020_2023 | raw | FAIL | -0.0419 | -0.240 | -0.49% | 1/4 | 1/4 |
| `industry_relative_ep_cs` | 2021_2024 | raw | FAIL | -0.0593 | -0.462 | -0.76% | 0/4 | 0/4 |
| `industry_relative_bp_cs` | 2018_2021 | raw | FAIL | -0.0054 | -0.002 | -0.39% | 2/4 | 2/4 |
| `industry_relative_bp_cs` | 2019_2022 | raw | FAIL | -0.0195 | -0.076 | -0.52% | 2/4 | 2/4 |
| `industry_relative_bp_cs` | 2020_2023 | raw | FAIL | -0.0558 | -0.384 | -0.95% | 1/4 | 1/4 |
| `industry_relative_bp_cs` | 2021_2024 | raw | FAIL | -0.0719 | -0.489 | -1.04% | 0/4 | 0/4 |
| `valuation_reversion_3y_cs` | 2018_2021 | raw | NOT_AVAILABLE |  |  |  | 0/4 | 0/4 |
| `valuation_reversion_3y_cs` | 2019_2022 | raw | NOT_AVAILABLE |  |  |  | 0/4 | 0/4 |
| `valuation_reversion_3y_cs` | 2020_2023 | raw | NOT_AVAILABLE |  |  |  | 0/4 | 0/4 |
| `valuation_reversion_3y_cs` | 2021_2024 | raw | NOT_AVAILABLE |  |  |  | 0/4 | 0/4 |
| `quality_value_composite_cs` | 2018_2021 | raw | NOT_AVAILABLE |  |  |  | 0/4 | 0/4 |
| `quality_value_composite_cs` | 2019_2022 | raw | NOT_AVAILABLE |  |  |  | 0/4 | 0/4 |
| `quality_value_composite_cs` | 2020_2023 | raw | NOT_AVAILABLE |  |  |  | 0/4 | 0/4 |
| `quality_value_composite_cs` | 2021_2024 | raw | NOT_AVAILABLE |  |  |  | 0/4 | 0/4 |
| `dividend_quality_cs` | 2018_2021 | raw | NOT_AVAILABLE |  |  |  | 0/4 | 0/4 |
| `dividend_quality_cs` | 2019_2022 | raw | NOT_AVAILABLE |  |  |  | 0/4 | 0/4 |
| `dividend_quality_cs` | 2020_2023 | raw | NOT_AVAILABLE |  |  |  | 0/4 | 0/4 |
| `dividend_quality_cs` | 2021_2024 | raw | NOT_AVAILABLE |  |  |  | 0/4 | 0/4 |
| `industry_relative_momentum_60_cs` | 2018_2021 | raw | FAIL | -0.0013 | 0.006 | -0.18% | 2/4 | 1/4 |
| `industry_relative_momentum_60_cs` | 2019_2022 | raw | FAIL | -0.0094 | -0.051 | -0.30% | 1/4 | 1/4 |
| `industry_relative_momentum_60_cs` | 2020_2023 | raw | FAIL | -0.0012 | 0.001 | -0.13% | 2/4 | 2/4 |
| `industry_relative_momentum_60_cs` | 2021_2024 | raw | FAIL | -0.0064 | -0.044 | -0.23% | 1/4 | 1/4 |
| `industry_relative_quality_cs` | 2018_2021 | raw | NOT_AVAILABLE |  |  |  | 0/4 | 0/4 |
| `industry_relative_quality_cs` | 2019_2022 | raw | NOT_AVAILABLE |  |  |  | 0/4 | 0/4 |
| `industry_relative_quality_cs` | 2020_2023 | raw | NOT_AVAILABLE |  |  |  | 0/4 | 0/4 |
| `industry_relative_quality_cs` | 2021_2024 | raw | NOT_AVAILABLE |  |  |  | 0/4 | 0/4 |
| `industry_relative_growth_cs` | 2018_2021 | raw | NOT_AVAILABLE |  |  |  | 0/4 | 0/4 |
| `industry_relative_growth_cs` | 2019_2022 | raw | NOT_AVAILABLE |  |  |  | 0/4 | 0/4 |
| `industry_relative_growth_cs` | 2020_2023 | raw | NOT_AVAILABLE |  |  |  | 0/4 | 0/4 |
| `industry_relative_growth_cs` | 2021_2024 | raw | NOT_AVAILABLE |  |  |  | 0/4 | 0/4 |
| `industry_relative_value_cs` | 2018_2021 | raw | NOT_AVAILABLE |  |  |  | 0/4 | 0/4 |
| `industry_relative_value_cs` | 2019_2022 | raw | NOT_AVAILABLE |  |  |  | 0/4 | 0/4 |
| `industry_relative_value_cs` | 2020_2023 | raw | NOT_AVAILABLE |  |  |  | 0/4 | 0/4 |
| `industry_relative_value_cs` | 2021_2024 | raw | NOT_AVAILABLE |  |  |  | 0/4 | 0/4 |
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
| `intraday_reversal_cs` | 2018_2021 | raw | FAIL | 0.0151 | 0.096 | -0.48% | 4/4 | 0/4 |
| `intraday_reversal_cs` | 2019_2022 | raw | FAIL | 0.0146 | 0.089 | -0.47% | 4/4 | 0/4 |
| `intraday_reversal_cs` | 2020_2023 | raw | FAIL | 0.0062 | 0.033 | -0.54% | 3/4 | 0/4 |
| `intraday_reversal_cs` | 2021_2024 | raw | FAIL | 0.0006 | 0.005 | -0.61% | 2/4 | 0/4 |
| `overnight_reversal_cs` | 2018_2021 | raw | FAIL | 0.0056 | 0.047 | -0.54% | 3/4 | 0/4 |
| `overnight_reversal_cs` | 2019_2022 | raw | FAIL | -0.0001 | -0.002 | -0.68% | 2/4 | 0/4 |
| `overnight_reversal_cs` | 2020_2023 | raw | FAIL | 0.0010 | 0.008 | -0.71% | 2/4 | 0/4 |
| `overnight_reversal_cs` | 2021_2024 | raw | FAIL | 0.0004 | 0.004 | -0.74% | 1/4 | 0/4 |
| `amihud_illiq_20d_cs` | 2018_2021 | raw | FAIL | 0.0073 | 0.064 | 0.03% | 2/4 | 2/4 |
| `amihud_illiq_20d_cs` | 2019_2022 | raw | FAIL | 0.0023 | 0.013 | -0.02% | 2/4 | 2/4 |
| `amihud_illiq_20d_cs` | 2020_2023 | raw | FAIL | -0.0064 | -0.059 | -0.12% | 1/4 | 1/4 |
| `amihud_illiq_20d_cs` | 2021_2024 | raw | FAIL | -0.0061 | -0.067 | -0.17% | 1/4 | 1/4 |
| `vol_price_divergence_20d_cs` | 2018_2021 | raw | FAIL | 0.0252 | 0.220 | -0.11% | 4/4 | 1/4 |
| `vol_price_divergence_20d_cs` | 2019_2022 | raw | FAIL | 0.0208 | 0.182 | -0.18% | 4/4 | 0/4 |
| `vol_price_divergence_20d_cs` | 2020_2023 | raw | FAIL | 0.0205 | 0.181 | -0.21% | 4/4 | 0/4 |
| `vol_price_divergence_20d_cs` | 2021_2024 | raw | FAIL | 0.0302 | 0.224 | -0.12% | 4/4 | 1/4 |
| `volatility_squeeze_cs` | 2018_2021 | raw | FAIL | 0.0084 | 0.074 | -0.21% | 3/4 | 1/4 |
| `volatility_squeeze_cs` | 2019_2022 | raw | FAIL | 0.0075 | 0.064 | -0.16% | 3/4 | 1/4 |
| `volatility_squeeze_cs` | 2020_2023 | raw | FAIL | 0.0072 | 0.056 | -0.18% | 3/4 | 0/4 |
| `volatility_squeeze_cs` | 2021_2024 | raw | FAIL | 0.0054 | 0.044 | -0.17% | 3/4 | 0/4 |
| `tail_risk_60d_cs` | 2018_2021 | raw | FAIL | 0.0121 | 0.101 | 0.04% | 4/4 | 3/4 |
| `tail_risk_60d_cs` | 2019_2022 | raw | FAIL | 0.0177 | 0.166 | 0.07% | 4/4 | 3/4 |
| `tail_risk_60d_cs` | 2020_2023 | raw | PASS | 0.0256 | 0.262 | 0.15% | 4/4 | 4/4 |
| `tail_risk_60d_cs` | 2021_2024 | raw | PASS | 0.0319 | 0.290 | 0.19% | 4/4 | 4/4 |
| `turnover_anomaly_20d_cs` | 2018_2021 | raw | FAIL | 0.0128 | 0.036 | 0.18% | 2/4 | 2/4 |
| `turnover_anomaly_20d_cs` | 2019_2022 | raw | FAIL | 0.0255 | 0.114 | 0.53% | 2/4 | 3/4 |
| `turnover_anomaly_20d_cs` | 2020_2023 | raw | FAIL | 0.0099 | 0.033 | 0.24% | 1/4 | 2/4 |
| `turnover_anomaly_20d_cs` | 2021_2024 | raw | FAIL | -0.0277 | -0.156 | -0.14% | 0/4 | 1/4 |
| `turnover_volatility_60d_cs` | 2018_2021 | raw | FAIL | 0.0316 | 0.179 | 0.23% | 2/4 | 1/4 |
| `turnover_volatility_60d_cs` | 2019_2022 | raw | FAIL | 0.0224 | 0.128 | 0.18% | 2/4 | 2/4 |
| `turnover_volatility_60d_cs` | 2020_2023 | raw | FAIL | 0.0225 | 0.140 | 0.29% | 2/4 | 3/4 |
| `turnover_volatility_60d_cs` | 2021_2024 | raw | FAIL | -0.0056 | -0.059 | 0.00% | 1/4 | 3/4 |
| `volume_shock_5d_cs` | 2018_2021 | raw | FAIL | -0.0002 | -0.003 | -0.34% | 2/4 | 0/4 |
| `volume_shock_5d_cs` | 2019_2022 | raw | FAIL | 0.0065 | 0.049 | -0.25% | 2/4 | 0/4 |
| `volume_shock_5d_cs` | 2020_2023 | raw | FAIL | -0.0013 | -0.015 | -0.30% | 1/4 | 0/4 |
| `volume_shock_5d_cs` | 2021_2024 | raw | FAIL | -0.0013 | -0.012 | -0.29% | 1/4 | 0/4 |
| `amount_concentration_20d_cs` | 2018_2021 | raw | FAIL | 0.0315 | 0.242 | 0.13% | 4/4 | 2/4 |
| `amount_concentration_20d_cs` | 2019_2022 | raw | PASS | 0.0351 | 0.279 | 0.18% | 4/4 | 3/4 |
| `amount_concentration_20d_cs` | 2020_2023 | raw | FAIL | 0.0206 | 0.172 | -0.02% | 4/4 | 2/4 |
| `amount_concentration_20d_cs` | 2021_2024 | raw | FAIL | 0.0173 | 0.136 | -0.06% | 4/4 | 2/4 |
| `low_volatility_60d_cs` | 2018_2021 | raw | FAIL | 0.0120 | 0.057 | -0.22% | 2/4 | 1/4 |
| `low_volatility_60d_cs` | 2019_2022 | raw | FAIL | 0.0149 | 0.068 | -0.22% | 2/4 | 1/4 |
| `low_volatility_60d_cs` | 2020_2023 | raw | FAIL | 0.0393 | 0.191 | 0.05% | 3/4 | 2/4 |
| `low_volatility_60d_cs` | 2021_2024 | raw | PASS | 0.0650 | 0.275 | 0.34% | 4/4 | 3/4 |
| `residual_volatility_60d_cs` | 2018_2021 | raw | FAIL | 0.0099 | 0.049 | -0.14% | 2/4 | 1/4 |
| `residual_volatility_60d_cs` | 2019_2022 | raw | FAIL | 0.0142 | 0.069 | -0.14% | 2/4 | 1/4 |
| `residual_volatility_60d_cs` | 2020_2023 | raw | FAIL | 0.0388 | 0.211 | 0.11% | 3/4 | 2/4 |
| `residual_volatility_60d_cs` | 2021_2024 | raw | PASS | 0.0660 | 0.332 | 0.43% | 4/4 | 3/4 |
| `bollinger_position_20d_cs` | 2018_2021 | raw | FAIL | 0.0073 | 0.050 | -0.34% | 3/4 | 0/4 |
| `bollinger_position_20d_cs` | 2019_2022 | raw | FAIL | 0.0136 | 0.084 | -0.21% | 4/4 | 0/4 |
| `bollinger_position_20d_cs` | 2020_2023 | raw | FAIL | 0.0070 | 0.040 | -0.29% | 3/4 | 0/4 |
| `bollinger_position_20d_cs` | 2021_2024 | raw | FAIL | 0.0088 | 0.046 | -0.25% | 3/4 | 0/4 |
| `price_channel_position_60d_cs` | 2018_2021 | raw | FAIL | -0.0080 | -0.042 | 0.02% | 2/4 | 2/4 |
| `price_channel_position_60d_cs` | 2019_2022 | raw | FAIL | -0.0193 | -0.102 | -0.17% | 1/4 | 1/4 |
| `price_channel_position_60d_cs` | 2020_2023 | raw | FAIL | -0.0115 | -0.055 | -0.10% | 2/4 | 2/4 |
| `price_channel_position_60d_cs` | 2021_2024 | raw | FAIL | -0.0201 | -0.101 | -0.25% | 1/4 | 1/4 |
| `rsi_divergence_14d_cs` | 2018_2021 | raw | FAIL | -0.0013 | -0.008 | -0.33% | 3/4 | 0/4 |
| `rsi_divergence_14d_cs` | 2019_2022 | raw | FAIL | 0.0037 | 0.023 | -0.26% | 4/4 | 0/4 |
| `rsi_divergence_14d_cs` | 2020_2023 | raw | FAIL | 0.0016 | 0.009 | -0.27% | 3/4 | 0/4 |
| `rsi_divergence_14d_cs` | 2021_2024 | raw | FAIL | -0.0018 | -0.009 | -0.24% | 2/4 | 0/4 |
| `revenue_stability_8q_cs` | 2018_2021 | raw | FAIL | -0.0056 | -0.020 | 0.52% | 3/4 | 1/4 |
| `revenue_stability_8q_cs` | 2019_2022 | raw | FAIL | -0.0280 | -0.115 | -1.01% | 2/4 | 0/4 |
| `revenue_stability_8q_cs` | 2020_2023 | raw | FAIL | -0.0169 | 0.013 | -0.12% | 2/4 | 0/4 |
| `revenue_stability_8q_cs` | 2021_2024 | raw | FAIL | -0.0398 | -0.197 | -0.12% | 1/4 | 0/4 |
| `margin_trend_8q_cs` | 2018_2021 | raw | FAIL | 0.0142 | 0.107 | -0.28% | 4/4 | 2/4 |
| `margin_trend_8q_cs` | 2019_2022 | raw | FAIL | 0.0192 | 0.131 | 0.17% | 4/4 | 3/4 |
| `margin_trend_8q_cs` | 2020_2023 | raw | FAIL | -0.0241 | -0.198 | 0.12% | 3/4 | 3/4 |
| `margin_trend_8q_cs` | 2021_2024 | raw | FAIL | -0.0057 | -0.143 | 0.04% | 3/4 | 3/4 |

## Correlation Clusters

| Cluster | Factor | Representative | Redundant To | Max Corr to Rep | Gate Score |
|---|---:|---:|---:|---:|
| 1 | `residual_volatility_60d_cs` | yes | - | 1.0 | 13.17 |
| 1 | `low_volatility_60d_cs` | no | residual_volatility_60d_cs | 0.9493 | 12.81 |

## Capacity / Liquidity Audit

| Factor | Year | Median Top Amt (CNY) | Median Mkt Cap (CNY) | Participation Rate | Status |
|---|---:|---:|---:|---:|---|
| `reversal_5_cs` | 2021 | 719989531 | 92160287126 | 0.06% | PASS |
| `reversal_5_cs` | 2022 | 564590404 | 83393647911 | 0.09% | PASS |
| `reversal_5_cs` | 2023 | 514390043 | 82908576754 | 0.10% | PASS |
| `reversal_5_cs` | 2024 | 552689949 | 75493507182 | 0.09% | PASS |
| `reversal_20_cs` | 2021 | 721063286 | 94594390212 | 0.07% | PASS |
| `reversal_20_cs` | 2022 | 596315781 | 85930199019 | 0.09% | PASS |
| `reversal_20_cs` | 2023 | 523073597 | 83139669960 | 0.10% | PASS |
| `reversal_20_cs` | 2024 | 566128751 | 78126210925 | 0.11% | PASS |
| `momentum_60_cs` | 2021 | 887988899 | 100087366092 | 0.06% | PASS |
| `momentum_60_cs` | 2022 | 532932201 | 84915341290 | 0.10% | PASS |
| `momentum_60_cs` | 2023 | 514471754 | 81882190325 | 0.10% | PASS |
| `momentum_60_cs` | 2024 | 549242049 | 75983470220 | 0.09% | PASS |
| `momentum_120_cs` | 2021 | 1065131236 | 103390677252 | 0.07% | PASS |
| `momentum_120_cs` | 2022 | 531040411 | 82964759419 | 0.09% | PASS |
| `momentum_120_cs` | 2023 | 546944880 | 81113088000 | 0.08% | PASS |
| `momentum_120_cs` | 2024 | 556777689 | 79656506100 | 0.09% | PASS |
| `volatility_20_cs` | 2021 | 245013648 | 101901409817 | 0.18% | PASS |
| `volatility_20_cs` | 2022 | 233276353 | 91626126998 | 0.21% | PASS |
| `volatility_20_cs` | 2023 | 233613159 | 85297527747 | 0.25% | PASS |
| `volatility_20_cs` | 2024 | 318549999 | 80007183443 | 0.22% | PASS |
| `volatility_60_cs` | 2021 | 256921381 | 105118174103 | 0.16% | PASS |
| `volatility_60_cs` | 2022 | 231147389 | 95354859067 | 0.23% | PASS |
| `volatility_60_cs` | 2023 | 243575806 | 88989823256 | 0.25% | PASS |
| `volatility_60_cs` | 2024 | 313269824 | 76001608469 | 0.22% | PASS |
| `rsi_14_cs` | 2021 | 484455322 | 90251095709 | 0.09% | PASS |
| `rsi_14_cs` | 2022 | 457316506 | 89890767092 | 0.10% | PASS |
| `rsi_14_cs` | 2023 | 450398730 | 87878260553 | 0.12% | PASS |
| `rsi_14_cs` | 2024 | 520428792 | 87290850196 | 0.11% | PASS |
| `macd_12_26_9_cs` | 2021 | 852002375 | 110707489583 | 0.06% | PASS |
| `macd_12_26_9_cs` | 2022 | 602663945 | 84707800677 | 0.08% | PASS |
| `macd_12_26_9_cs` | 2023 | 592546986 | 81038025900 | 0.09% | PASS |
| `macd_12_26_9_cs` | 2024 | 577504519 | 78098702536 | 0.10% | PASS |
| `pv_divergence_20_cs` | 2021 | 621514076 | 87140795961 | 0.07% | PASS |
| `pv_divergence_20_cs` | 2022 | 493934430 | 86051077608 | 0.10% | PASS |
| `pv_divergence_20_cs` | 2023 | 398146520 | 86202566110 | 0.12% | PASS |
| `pv_divergence_20_cs` | 2024 | 446487433 | 83000055716 | 0.12% | PASS |
| `ep_cs` | 2021 | 1224225692 | 105598315722 | 0.15% | PASS |
| `ep_cs` | 2022 | 609808354 | 109696496216 | 0.20% | PASS |
| `ep_cs` | 2023 | 561660744 | 112444276316 | 0.20% | PASS |
| `ep_cs` | 2024 | 501714227 | 102066946897 | 0.12% | PASS |
| `bp_cs` | 2021 | 711241689 | 92155829310 | 0.16% | PASS |
| `bp_cs` | 2022 | 850387211 | 108428198620 | 0.27% | PASS |
| `bp_cs` | 2023 | 616615951 | 121189903700 | 0.23% | PASS |
| `bp_cs` | 2024 | 597722945 | 109739280000 | 0.13% | PASS |
| `sp_cs` | 2021 | 534653220 | 69699740276 | 0.13% | PASS |
| `sp_cs` | 2022 | 595933214 | 88552662090 | 0.23% | PASS |
| `sp_cs` | 2023 | 400191662 | 89131062886 | 0.15% | PASS |
| `sp_cs` | 2024 | 299895898 | 81125628913 | 0.13% | PASS |
| `roe_cs` | 2021 | 702381155 | 80935151590 | 0.14% | PASS |
| `roe_cs` | 2022 | 590616058 | 79268495510 | 0.17% | PASS |
| `roe_cs` | 2023 | 475141841 | 82376179649 | 0.18% | PASS |
| `roe_cs` | 2024 | 499717712 | 72273069517 | 0.17% | PASS |
| `gross_margin_cs` | 2021 | 546947679 | 68712668438 | 0.17% | PASS |
| `gross_margin_cs` | 2022 | 417451003 | 68251395269 | 0.17% | PASS |
| `gross_margin_cs` | 2023 | 427390477 | 75900234636 | 0.18% | PASS |
| `gross_margin_cs` | 2024 | 380174599 | 70457159759 | 0.16% | PASS |
| `profit_growth_cs` | 2021 | 1485012339 | 80289141515 | 0.93% | PASS |
| `profit_growth_cs` | 2022 | 751471536 | 83779199848 | 2.13% | PASS |
| `profit_growth_cs` | 2023 | 531825991 | 96042979758 | 2.13% | PASS |
| `profit_growth_cs` | 2024 | 594697257 | 79822428040 | 1.46% | PASS |
| `revenue_growth_cs` | 2021 | 584266404 | 67828835677 | 0.98% | PASS |
| `revenue_growth_cs` | 2022 | 619748089 | 61918066465 | 1.43% | PASS |
| `revenue_growth_cs` | 2023 | 417110407 | 80350349550 | 1.50% | PASS |
| `revenue_growth_cs` | 2024 | 579935251 | 75947865941 | 1.15% | PASS |
| `leverage_cs` | 2021 | 605646916 | 91898324825 | 0.12% | PASS |
| `leverage_cs` | 2022 | 403847070 | 83405450628 | 0.14% | PASS |
| `leverage_cs` | 2023 | 372677831 | 91368543693 | 0.16% | PASS |
| `leverage_cs` | 2024 | 391777564 | 92433646677 | 0.14% | PASS |
| `roe_stability_8q_cs` | 2021 | 620970137 | 75340372470 | 0.10% | PASS |
| `roe_stability_8q_cs` | 2022 | 505026585 | 79321280801 | 0.19% | PASS |
| `roe_stability_8q_cs` | 2023 | 419454190 | 87674662718 | 0.18% | PASS |
| `roe_stability_8q_cs` | 2024 | 474282704 | 81609525411 | 0.17% | PASS |
| `roa_ttm_cs` | 2021 | 700638042 | 75792055330 | 0.19% | PASS |
| `roa_ttm_cs` | 2022 | 570617031 | 74429061684 | 0.18% | PASS |
| `roa_ttm_cs` | 2023 | 431615350 | 75616118364 | 0.25% | PASS |
| `roa_ttm_cs` | 2024 | 414651715 | 69172729886 | 0.20% | PASS |
| `gross_margin_ttm_cs` | 2021 | 550041974 | 68352505056 | 0.16% | PASS |
| `gross_margin_ttm_cs` | 2022 | 409127848 | 67262403526 | 0.18% | PASS |
| `gross_margin_ttm_cs` | 2023 | 420300476 | 75425599750 | 0.18% | PASS |
| `gross_margin_ttm_cs` | 2024 | 396225725 | 70457159759 | 0.17% | PASS |
| `net_margin_ttm_cs` | 2021 | 426264261 | 72905443714 | 0.12% | PASS |
| `net_margin_ttm_cs` | 2022 | 423160742 | 89951190589 | 0.15% | PASS |
| `net_margin_ttm_cs` | 2023 | 444724999 | 92570551751 | 0.15% | PASS |
| `net_margin_ttm_cs` | 2024 | 576683133 | 89725927455 | 0.13% | PASS |
| `profitability_quality_cs` | 2021 | 529700989 | 70895136032 | 0.11% | PASS |
| `profitability_quality_cs` | 2022 | 441767882 | 68117666252 | 0.16% | PASS |
| `profitability_quality_cs` | 2023 | 435859031 | 86075385639 | 0.16% | PASS |
| `profitability_quality_cs` | 2024 | 417219066 | 81495515364 | 0.13% | PASS |
| `revenue_growth_ttm_cs` | 2021 | 584266404 | 67828835677 | 0.98% | PASS |
| `revenue_growth_ttm_cs` | 2022 | 619748089 | 61918066465 | 1.43% | PASS |
| `revenue_growth_ttm_cs` | 2023 | 417110407 | 80350349550 | 1.50% | PASS |
| `revenue_growth_ttm_cs` | 2024 | 579935251 | 75947865941 | 1.15% | PASS |
| `profit_growth_ttm_cs` | 2021 | 1485012339 | 80289141515 | 0.93% | PASS |
| `profit_growth_ttm_cs` | 2022 | 751471536 | 83779199848 | 2.13% | PASS |
| `profit_growth_ttm_cs` | 2023 | 531825991 | 96042979758 | 2.13% | PASS |
| `profit_growth_ttm_cs` | 2024 | 594697257 | 79822428040 | 1.46% | PASS |
| `growth_stability_8q_cs` | 2021 | nan | nan |  | NOT_AVAILABLE |
| `growth_stability_8q_cs` | 2022 | nan | nan |  | NOT_AVAILABLE |
| `growth_stability_8q_cs` | 2023 | nan | nan |  | NOT_AVAILABLE |
| `growth_stability_8q_cs` | 2024 | nan | nan |  | NOT_AVAILABLE |
| `earnings_acceleration_cs` | 2021 | 694554700 | 79480463352 | 0.94% | PASS |
| `earnings_acceleration_cs` | 2022 | 320550948 | 61820625785 | 1.84% | PASS |
| `earnings_acceleration_cs` | 2023 | 588125090 | 102029423900 | 1.59% | PASS |
| `earnings_acceleration_cs` | 2024 | 515434887 | 75377609226 | 1.36% | PASS |
| `industry_relative_ep_cs` | 2021 | 873569964 | 100312294882 | 0.12% | PASS |
| `industry_relative_ep_cs` | 2022 | 482893191 | 81021268576 | 0.22% | PASS |
| `industry_relative_ep_cs` | 2023 | 343527753 | 84572380209 | 0.14% | PASS |
| `industry_relative_ep_cs` | 2024 | 271090736 | 80291279776 | 0.14% | PASS |
| `industry_relative_bp_cs` | 2021 | 765317359 | 103611304006 | 0.16% | PASS |
| `industry_relative_bp_cs` | 2022 | 441314854 | 81231033460 | 0.29% | PASS |
| `industry_relative_bp_cs` | 2023 | 404833995 | 83817501560 | 0.20% | PASS |
| `industry_relative_bp_cs` | 2024 | 424856274 | 84042223634 | 0.16% | PASS |
| `industry_relative_momentum_60_cs` | 2021 | 833308710 | 86838738808 | 0.08% | PASS |
| `industry_relative_momentum_60_cs` | 2022 | 538770588 | 82844821872 | 0.09% | PASS |
| `industry_relative_momentum_60_cs` | 2023 | 530532921 | 85035312166 | 0.11% | PASS |
| `industry_relative_momentum_60_cs` | 2024 | 627766870 | 80571708906 | 0.12% | PASS |
| `momentum_60_skip5_cs` | 2021 | 504567840 | 85111914794 | 0.09% | PASS |
| `momentum_60_skip5_cs` | 2022 | 555216388 | 84051825380 | 0.08% | PASS |
| `momentum_60_skip5_cs` | 2023 | 486012708 | 78718242268 | 0.10% | PASS |
| `momentum_60_skip5_cs` | 2024 | 440371112 | 73637573672 | 0.13% | PASS |
| `momentum_120_skip20_cs` | 2021 | 1238021627 | 82851067300 | 0.09% | PASS |
| `momentum_120_skip20_cs` | 2022 | 628106653 | 80057891020 | 0.09% | PASS |
| `momentum_120_skip20_cs` | 2023 | 614593976 | 82276675262 | 0.10% | PASS |
| `momentum_120_skip20_cs` | 2024 | 631585920 | 72810588298 | 0.10% | PASS |
| `risk_adjusted_momentum_60_cs` | 2021 | 360863094 | 88450021463 | 0.11% | PASS |
| `risk_adjusted_momentum_60_cs` | 2022 | 403968242 | 84233531369 | 0.11% | PASS |
| `risk_adjusted_momentum_60_cs` | 2023 | 415432501 | 84899101875 | 0.14% | PASS |
| `risk_adjusted_momentum_60_cs` | 2024 | 406185319 | 85375665863 | 0.14% | PASS |
| `volume_confirmed_momentum_cs` | 2021 | 832046347 | 86846881154 | 0.06% | PASS |
| `volume_confirmed_momentum_cs` | 2022 | 591372763 | 72974226172 | 0.10% | PASS |
| `volume_confirmed_momentum_cs` | 2023 | 603786735 | 74938984500 | 0.09% | PASS |
| `volume_confirmed_momentum_cs` | 2024 | 572990191 | 67038441281 | 0.08% | PASS |
| `trend_quality_cs` | 2021 | 389181916 | 86170430760 | 0.11% | PASS |
| `trend_quality_cs` | 2022 | 361147567 | 88567860006 | 0.12% | PASS |
| `trend_quality_cs` | 2023 | 413052410 | 88045056800 | 0.12% | PASS |
| `trend_quality_cs` | 2024 | 441290068 | 82500825680 | 0.13% | PASS |
| `intraday_reversal_cs` | 2021 | 738704508 | 83451070066 | 0.06% | PASS |
| `intraday_reversal_cs` | 2022 | 571753897 | 81051206238 | 0.09% | PASS |
| `intraday_reversal_cs` | 2023 | 532560900 | 78688810752 | 0.10% | PASS |
| `intraday_reversal_cs` | 2024 | 581441775 | 74796331369 | 0.09% | PASS |
| `overnight_reversal_cs` | 2021 | 834485657 | 89442300531 | 0.07% | PASS |
| `overnight_reversal_cs` | 2022 | 654472784 | 87564523634 | 0.10% | PASS |
| `overnight_reversal_cs` | 2023 | 479570589 | 82065531913 | 0.10% | PASS |
| `overnight_reversal_cs` | 2024 | 590062795 | 75323727764 | 0.09% | PASS |
| `amihud_illiq_20d_cs` | 2021 | 2418010285 | 97512078616 | 0.32% | PASS |
| `amihud_illiq_20d_cs` | 2022 | 1540940694 | 99248237630 | 0.37% | PASS |
| `amihud_illiq_20d_cs` | 2023 | 1405143217 | 91615614394 | 0.34% | PASS |
| `amihud_illiq_20d_cs` | 2024 | 1545869459 | 87559067462 | 0.35% | PASS |
| `vol_price_divergence_20d_cs` | 2021 | 561001769 | 84256971678 | 0.09% | PASS |
| `vol_price_divergence_20d_cs` | 2022 | 387584627 | 85123724752 | 0.14% | PASS |
| `vol_price_divergence_20d_cs` | 2023 | 361757179 | 82542988765 | 0.22% | PASS |
| `vol_price_divergence_20d_cs` | 2024 | 464047068 | 74323684725 | 0.19% | PASS |
| `volatility_squeeze_cs` | 2021 | 358173945 | 74768132086 | 0.11% | PASS |
| `volatility_squeeze_cs` | 2022 | 403625407 | 80025869345 | 0.10% | PASS |
| `volatility_squeeze_cs` | 2023 | 374765907 | 82093943130 | 0.16% | PASS |
| `volatility_squeeze_cs` | 2024 | 466161749 | 86136270000 | 0.10% | PASS |
| `tail_risk_60d_cs` | 2021 | 545553376 | 78894933530 | 0.11% | PASS |
| `tail_risk_60d_cs` | 2022 | 350050628 | 76299874722 | 0.12% | PASS |
| `tail_risk_60d_cs` | 2023 | 387202470 | 85464019531 | 0.14% | PASS |
| `tail_risk_60d_cs` | 2024 | 474418014 | 88383507544 | 0.11% | PASS |
| `turnover_anomaly_20d_cs` | 2021 | 730662904 | 95540528008 | 0.12% | PASS |
| `turnover_anomaly_20d_cs` | 2022 | 650205061 | 95516761008 | 0.12% | PASS |
| `turnover_anomaly_20d_cs` | 2023 | 619112605 | 92630618232 | 0.12% | PASS |
| `turnover_anomaly_20d_cs` | 2024 | 800700858 | 87559067462 | 0.12% | PASS |
| `turnover_volatility_60d_cs` | 2021 | 625153167 | 102195905207 | 0.09% | PASS |
| `turnover_volatility_60d_cs` | 2022 | 429624727 | 101707897687 | 0.10% | PASS |
| `turnover_volatility_60d_cs` | 2023 | 452246058 | 102677370084 | 0.11% | PASS |
| `turnover_volatility_60d_cs` | 2024 | 452772074 | 101105651833 | 0.11% | PASS |
| `volume_shock_5d_cs` | 2021 | 372785419 | 73025070048 | 0.11% | PASS |
| `volume_shock_5d_cs` | 2022 | 344612571 | 79428537850 | 0.13% | PASS |
| `volume_shock_5d_cs` | 2023 | 365385797 | 81513880506 | 0.15% | PASS |
| `volume_shock_5d_cs` | 2024 | 373523207 | 77776639200 | 0.14% | PASS |
| `amount_concentration_20d_cs` | 2021 | 606752972 | 81955614038 | 0.08% | PASS |
| `amount_concentration_20d_cs` | 2022 | 486483824 | 82576748151 | 0.10% | PASS |
| `amount_concentration_20d_cs` | 2023 | 375134229 | 86982312802 | 0.12% | PASS |
| `amount_concentration_20d_cs` | 2024 | 487796240 | 80236028389 | 0.11% | PASS |
| `low_volatility_60d_cs` | 2021 | 231649267 | 101708249920 | 0.18% | PASS |
| `low_volatility_60d_cs` | 2022 | 252486339 | 91770297566 | 0.18% | PASS |
| `low_volatility_60d_cs` | 2023 | 271247018 | 87142793086 | 0.18% | PASS |
| `low_volatility_60d_cs` | 2024 | 498160433 | 84080539986 | 0.11% | PASS |
| `residual_volatility_60d_cs` | 2021 | 219966389 | 99729918790 | 0.22% | PASS |
| `residual_volatility_60d_cs` | 2022 | 238073900 | 85382002488 | 0.21% | PASS |
| `residual_volatility_60d_cs` | 2023 | 266715620 | 85377801715 | 0.19% | PASS |
| `residual_volatility_60d_cs` | 2024 | 425986836 | 81638133955 | 0.12% | PASS |
| `bollinger_position_20d_cs` | 2021 | 430506415 | 83730015818 | 0.10% | PASS |
| `bollinger_position_20d_cs` | 2022 | 416900411 | 89813810240 | 0.11% | PASS |
| `bollinger_position_20d_cs` | 2023 | 434463795 | 86207447779 | 0.11% | PASS |
| `bollinger_position_20d_cs` | 2024 | 463319206 | 86641316682 | 0.11% | PASS |
| `price_channel_position_60d_cs` | 2021 | 939376868 | 81931223646 | 0.11% | PASS |
| `price_channel_position_60d_cs` | 2022 | 655234937 | 78674634509 | 0.13% | PASS |
| `price_channel_position_60d_cs` | 2023 | 616264155 | 84792617846 | 0.12% | PASS |
| `price_channel_position_60d_cs` | 2024 | 694445912 | 76223159010 | 0.13% | PASS |
| `rsi_divergence_14d_cs` | 2021 | 481304130 | 81481713970 | 0.09% | PASS |
| `rsi_divergence_14d_cs` | 2022 | 424187062 | 85524106516 | 0.11% | PASS |
| `rsi_divergence_14d_cs` | 2023 | 470895496 | 86113137542 | 0.10% | PASS |
| `rsi_divergence_14d_cs` | 2024 | 510619195 | 80880881223 | 0.10% | PASS |
| `revenue_stability_8q_cs` | 2021 | nan | nan |  | NOT_AVAILABLE |
| `revenue_stability_8q_cs` | 2022 | nan | nan |  | NOT_AVAILABLE |
| `revenue_stability_8q_cs` | 2023 | nan | nan |  | NOT_AVAILABLE |
| `revenue_stability_8q_cs` | 2024 | nan | nan |  | NOT_AVAILABLE |
| `margin_trend_8q_cs` | 2021 | 1304872661 | 114583053028 | 0.61% | PASS |
| `margin_trend_8q_cs` | 2022 | 897866310 | 100992651314 | 1.04% | PASS |
| `margin_trend_8q_cs` | 2023 | 564067544 | 76367399004 | 1.43% | PASS |
| `margin_trend_8q_cs` | 2024 | 492616742 | 89759132627 | 1.35% | PASS |

## Regime Breakdown

| Factor | Regime | N Dates | Mean IC |
|---|---:|---:|
| `reversal_5_cs` | high_volatility | 49 | 0.0702 |
| `reversal_5_cs` | range_bound | 217 | 0.0122 |
| `reversal_5_cs` | trend_down | 101 | 0.0121 |
| `reversal_5_cs` | trend_up | 34 | 0.0003 |
| `reversal_5_cs` | unclassified | 1507 | 0.0134 |
| `reversal_20_cs` | high_volatility | 48 | 0.0106 |
| `reversal_20_cs` | range_bound | 200 | 0.0074 |
| `reversal_20_cs` | trend_down | 97 | 0.0194 |
| `reversal_20_cs` | trend_up | 32 | 0.0382 |
| `reversal_20_cs` | unclassified | 1411 | 0.0111 |
| `momentum_60_cs` | high_volatility | 45 | -0.0221 |
| `momentum_60_cs` | range_bound | 205 | 0.0182 |
| `momentum_60_cs` | trend_down | 92 | -0.0115 |
| `momentum_60_cs` | trend_up | 34 | -0.0462 |
| `momentum_60_cs` | unclassified | 1409 | 0.0078 |
| `momentum_120_cs` | high_volatility | 48 | -0.0137 |
| `momentum_120_cs` | range_bound | 182 | 0.0485 |
| `momentum_120_cs` | trend_down | 91 | -0.0142 |
| `momentum_120_cs` | trend_up | 28 | -0.0095 |
| `momentum_120_cs` | unclassified | 1304 | 0.0265 |
| `volatility_20_cs` | high_volatility | 48 | 0.0058 |
| `volatility_20_cs` | range_bound | 211 | 0.0266 |
| `volatility_20_cs` | trend_down | 100 | 0.0212 |
| `volatility_20_cs` | trend_up | 34 | 0.1584 |
| `volatility_20_cs` | unclassified | 1475 | 0.0328 |
| `volatility_60_cs` | high_volatility | 48 | 0.0196 |
| `volatility_60_cs` | range_bound | 205 | 0.0224 |
| `volatility_60_cs` | trend_down | 99 | 0.0337 |
| `volatility_60_cs` | trend_up | 33 | 0.1787 |
| `volatility_60_cs` | unclassified | 1443 | 0.0368 |
| `rsi_14_cs` | high_volatility | 48 | 0.0221 |
| `rsi_14_cs` | range_bound | 207 | 0.0050 |
| `rsi_14_cs` | trend_down | 99 | -0.0003 |
| `rsi_14_cs` | trend_up | 34 | 0.0149 |
| `rsi_14_cs` | unclassified | 1448 | 0.0018 |
| `macd_12_26_9_cs` | high_volatility | 46 | 0.0201 |
| `macd_12_26_9_cs` | range_bound | 202 | 0.0201 |
| `macd_12_26_9_cs` | trend_down | 95 | -0.0226 |
| `macd_12_26_9_cs` | trend_up | 31 | -0.0263 |
| `macd_12_26_9_cs` | unclassified | 1390 | 0.0076 |
| `pv_divergence_20_cs` | high_volatility | 48 | 0.0352 |
| `pv_divergence_20_cs` | range_bound | 211 | 0.0330 |
| `pv_divergence_20_cs` | trend_down | 100 | 0.0311 |
| `pv_divergence_20_cs` | trend_up | 34 | 0.0725 |
| `pv_divergence_20_cs` | unclassified | 1475 | 0.0336 |
| `ep_cs` | high_volatility | 2 | 0.0896 |
| `ep_cs` | range_bound | 6 | 0.1302 |
| `ep_cs` | trend_down | 1 | 0.3274 |
| `ep_cs` | trend_up | 2 | -0.1090 |
| `ep_cs` | unclassified | 79 | -0.0423 |
| `bp_cs` | high_volatility | 2 | 0.1408 |
| `bp_cs` | range_bound | 6 | 0.1131 |
| `bp_cs` | trend_down | 1 | 0.3132 |
| `bp_cs` | trend_up | 2 | 0.0162 |
| `bp_cs` | unclassified | 79 | -0.0540 |
| `sp_cs` | high_volatility | 2 | 0.1515 |
| `sp_cs` | range_bound | 6 | 0.0481 |
| `sp_cs` | trend_down | 1 | 0.2140 |
| `sp_cs` | trend_up | 2 | -0.0813 |
| `sp_cs` | unclassified | 79 | -0.0420 |
| `roe_cs` | high_volatility | 44 | 0.0183 |
| `roe_cs` | range_bound | 177 | -0.0033 |
| `roe_cs` | trend_down | 95 | 0.0155 |
| `roe_cs` | trend_up | 31 | 0.0076 |
| `roe_cs` | unclassified | 1315 | 0.0043 |
| `gross_margin_cs` | high_volatility | 44 | 0.0460 |
| `gross_margin_cs` | range_bound | 177 | -0.0015 |
| `gross_margin_cs` | trend_down | 95 | 0.0130 |
| `gross_margin_cs` | trend_up | 31 | -0.0229 |
| `gross_margin_cs` | unclassified | 1315 | 0.0049 |
| `profit_growth_cs` | high_volatility | 9 | -0.0382 |
| `profit_growth_cs` | range_bound | 23 | -0.0497 |
| `profit_growth_cs` | trend_down | 4 | 0.2274 |
| `profit_growth_cs` | trend_up | 8 | 0.0906 |
| `profit_growth_cs` | unclassified | 196 | 0.0099 |
| `revenue_growth_cs` | high_volatility | 9 | -0.0209 |
| `revenue_growth_cs` | range_bound | 23 | -0.0173 |
| `revenue_growth_cs` | trend_down | 4 | 0.1280 |
| `revenue_growth_cs` | trend_up | 8 | 0.2109 |
| `revenue_growth_cs` | unclassified | 196 | 0.0359 |
| `leverage_cs` | high_volatility | 44 | 0.0189 |
| `leverage_cs` | range_bound | 177 | -0.0197 |
| `leverage_cs` | trend_down | 95 | 0.0034 |
| `leverage_cs` | trend_up | 31 | -0.0484 |
| `leverage_cs` | unclassified | 1315 | -0.0108 |
| `log_market_cap_cs` | range_bound | 7 | -0.0005 |
| `log_market_cap_cs` | trend_down | 2 | 0.1098 |
| `log_market_cap_cs` | trend_up | 1 | 0.0968 |
| `log_market_cap_cs` | unclassified | 79 | 0.0130 |
| `roe_stability_8q_cs` | high_volatility | 44 | 0.0373 |
| `roe_stability_8q_cs` | range_bound | 162 | -0.0242 |
| `roe_stability_8q_cs` | trend_down | 95 | -0.0026 |
| `roe_stability_8q_cs` | trend_up | 31 | -0.0094 |
| `roe_stability_8q_cs` | unclassified | 1256 | -0.0067 |
| `roa_ttm_cs` | high_volatility | 44 | 0.0257 |
| `roa_ttm_cs` | range_bound | 177 | -0.0027 |
| `roa_ttm_cs` | trend_down | 95 | 0.0080 |
| `roa_ttm_cs` | trend_up | 31 | 0.0118 |
| `roa_ttm_cs` | unclassified | 1315 | 0.0049 |
| `gross_margin_ttm_cs` | high_volatility | 44 | 0.0472 |
| `gross_margin_ttm_cs` | range_bound | 177 | -0.0020 |
| `gross_margin_ttm_cs` | trend_down | 95 | 0.0127 |
| `gross_margin_ttm_cs` | trend_up | 31 | -0.0223 |
| `gross_margin_ttm_cs` | unclassified | 1315 | 0.0047 |
| `net_margin_ttm_cs` | high_volatility | 44 | 0.0209 |
| `net_margin_ttm_cs` | range_bound | 177 | 0.0235 |
| `net_margin_ttm_cs` | trend_down | 95 | 0.0047 |
| `net_margin_ttm_cs` | trend_up | 31 | 0.0142 |
| `net_margin_ttm_cs` | unclassified | 1315 | 0.0150 |
| `profitability_quality_cs` | high_volatility | 44 | 0.0389 |
| `profitability_quality_cs` | range_bound | 177 | 0.0052 |
| `profitability_quality_cs` | trend_down | 95 | 0.0056 |
| `profitability_quality_cs` | trend_up | 31 | -0.0018 |
| `profitability_quality_cs` | unclassified | 1315 | 0.0066 |
| `revenue_growth_ttm_cs` | high_volatility | 9 | -0.0209 |
| `revenue_growth_ttm_cs` | range_bound | 23 | -0.0173 |
| `revenue_growth_ttm_cs` | trend_down | 4 | 0.1280 |
| `revenue_growth_ttm_cs` | trend_up | 8 | 0.2109 |
| `revenue_growth_ttm_cs` | unclassified | 199 | 0.0386 |
| `profit_growth_ttm_cs` | high_volatility | 9 | -0.0382 |
| `profit_growth_ttm_cs` | range_bound | 23 | -0.0497 |
| `profit_growth_ttm_cs` | trend_down | 4 | 0.2274 |
| `profit_growth_ttm_cs` | trend_up | 8 | 0.0906 |
| `profit_growth_ttm_cs` | unclassified | 199 | 0.0093 |
| `growth_stability_8q_cs` | high_volatility | 9 | -0.0365 |
| `growth_stability_8q_cs` | range_bound | 23 | 0.0112 |
| `growth_stability_8q_cs` | trend_down | 14 | 0.0509 |
| `growth_stability_8q_cs` | trend_up | 8 | 0.0022 |
| `growth_stability_8q_cs` | unclassified | 238 | 0.0121 |
| `earnings_acceleration_cs` | high_volatility | 3 | 0.0414 |
| `earnings_acceleration_cs` | range_bound | 19 | 0.0231 |
| `earnings_acceleration_cs` | trend_down | 0 |  |
| `earnings_acceleration_cs` | trend_up | 1 | -0.2268 |
| `earnings_acceleration_cs` | unclassified | 120 | 0.0162 |
| `industry_relative_ep_cs` | high_volatility | 2 | 0.0342 |
| `industry_relative_ep_cs` | range_bound | 6 | 0.0840 |
| `industry_relative_ep_cs` | trend_down | 1 | 0.2170 |
| `industry_relative_ep_cs` | trend_up | 2 | 0.0604 |
| `industry_relative_ep_cs` | unclassified | 79 | -0.0370 |
| `industry_relative_bp_cs` | high_volatility | 2 | 0.0994 |
| `industry_relative_bp_cs` | range_bound | 6 | 0.0981 |
| `industry_relative_bp_cs` | trend_down | 1 | 0.1834 |
| `industry_relative_bp_cs` | trend_up | 2 | 0.1520 |
| `industry_relative_bp_cs` | unclassified | 79 | -0.0442 |
| `industry_relative_momentum_60_cs` | high_volatility | 49 | -0.0039 |
| `industry_relative_momentum_60_cs` | range_bound | 204 | 0.0151 |
| `industry_relative_momentum_60_cs` | trend_down | 101 | -0.0183 |
| `industry_relative_momentum_60_cs` | trend_up | 34 | -0.0644 |
| `industry_relative_momentum_60_cs` | unclassified | 1460 | 0.0028 |
| `momentum_60_skip5_cs` | high_volatility | 49 | 0.0260 |
| `momentum_60_skip5_cs` | range_bound | 204 | -0.0035 |
| `momentum_60_skip5_cs` | trend_down | 101 | 0.0379 |
| `momentum_60_skip5_cs` | trend_up | 34 | 0.1006 |
| `momentum_60_skip5_cs` | unclassified | 1460 | 0.0102 |
| `momentum_120_skip20_cs` | high_volatility | 49 | -0.0037 |
| `momentum_120_skip20_cs` | range_bound | 191 | 0.0353 |
| `momentum_120_skip20_cs` | trend_down | 101 | -0.0170 |
| `momentum_120_skip20_cs` | trend_up | 34 | -0.0405 |
| `momentum_120_skip20_cs` | unclassified | 1413 | 0.0172 |
| `risk_adjusted_momentum_60_cs` | high_volatility | 49 | 0.0399 |
| `risk_adjusted_momentum_60_cs` | range_bound | 204 | -0.0027 |
| `risk_adjusted_momentum_60_cs` | trend_down | 101 | 0.0410 |
| `risk_adjusted_momentum_60_cs` | trend_up | 34 | 0.0647 |
| `risk_adjusted_momentum_60_cs` | unclassified | 1460 | 0.0125 |
| `volume_confirmed_momentum_cs` | high_volatility | 49 | 0.0057 |
| `volume_confirmed_momentum_cs` | range_bound | 204 | -0.0096 |
| `volume_confirmed_momentum_cs` | trend_down | 101 | 0.0243 |
| `volume_confirmed_momentum_cs` | trend_up | 34 | -0.0086 |
| `volume_confirmed_momentum_cs` | unclassified | 1460 | 0.0088 |
| `trend_quality_cs` | high_volatility | 49 | 0.0452 |
| `trend_quality_cs` | range_bound | 210 | 0.0060 |
| `trend_quality_cs` | trend_down | 101 | 0.0269 |
| `trend_quality_cs` | trend_up | 34 | 0.0443 |
| `trend_quality_cs` | unclassified | 1485 | 0.0127 |
| `intraday_reversal_cs` | high_volatility | 49 | 0.0616 |
| `intraday_reversal_cs` | range_bound | 217 | 0.0037 |
| `intraday_reversal_cs` | trend_down | 101 | -0.0041 |
| `intraday_reversal_cs` | trend_up | 34 | 0.0317 |
| `intraday_reversal_cs` | unclassified | 1507 | 0.0090 |
| `overnight_reversal_cs` | high_volatility | 49 | -0.0123 |
| `overnight_reversal_cs` | range_bound | 217 | 0.0087 |
| `overnight_reversal_cs` | trend_down | 101 | 0.0043 |
| `overnight_reversal_cs` | trend_up | 34 | 0.0334 |
| `overnight_reversal_cs` | unclassified | 1507 | 0.0081 |
| `amihud_illiq_20d_cs` | high_volatility | 49 | -0.0103 |
| `amihud_illiq_20d_cs` | range_bound | 215 | 0.0076 |
| `amihud_illiq_20d_cs` | trend_down | 101 | -0.0042 |
| `amihud_illiq_20d_cs` | trend_up | 34 | 0.0057 |
| `amihud_illiq_20d_cs` | unclassified | 1499 | 0.0050 |
| `vol_price_divergence_20d_cs` | high_volatility | 49 | 0.0394 |
| `vol_price_divergence_20d_cs` | range_bound | 215 | 0.0302 |
| `vol_price_divergence_20d_cs` | trend_down | 101 | 0.0235 |
| `vol_price_divergence_20d_cs` | trend_up | 34 | 0.0641 |
| `vol_price_divergence_20d_cs` | unclassified | 1500 | 0.0324 |
| `volatility_squeeze_cs` | high_volatility | 49 | 0.0038 |
| `volatility_squeeze_cs` | range_bound | 210 | 0.0107 |
| `volatility_squeeze_cs` | trend_down | 101 | -0.0093 |
| `volatility_squeeze_cs` | trend_up | 34 | -0.0123 |
| `volatility_squeeze_cs` | unclassified | 1484 | 0.0053 |
| `tail_risk_60d_cs` | high_volatility | 49 | 0.0074 |
| `tail_risk_60d_cs` | range_bound | 210 | 0.0230 |
| `tail_risk_60d_cs` | trend_down | 101 | 0.0272 |
| `tail_risk_60d_cs` | trend_up | 34 | 0.0351 |
| `tail_risk_60d_cs` | unclassified | 1484 | 0.0224 |
| `turnover_anomaly_20d_cs` | range_bound | 5 | 0.0200 |
| `turnover_anomaly_20d_cs` | trend_down | 2 | 0.3287 |
| `turnover_anomaly_20d_cs` | trend_up | 1 | -0.0271 |
| `turnover_anomaly_20d_cs` | unclassified | 72 | -0.0141 |
| `turnover_volatility_60d_cs` | range_bound | 5 | 0.0358 |
| `turnover_volatility_60d_cs` | trend_down | 2 | 0.2759 |
| `turnover_volatility_60d_cs` | trend_up | 1 | 0.0513 |
| `turnover_volatility_60d_cs` | unclassified | 54 | 0.0056 |
| `volume_shock_5d_cs` | high_volatility | 49 | 0.0336 |
| `volume_shock_5d_cs` | range_bound | 215 | 0.0027 |
| `volume_shock_5d_cs` | trend_down | 101 | -0.0089 |
| `volume_shock_5d_cs` | trend_up | 34 | -0.0044 |
| `volume_shock_5d_cs` | unclassified | 1500 | 0.0009 |
| `amount_concentration_20d_cs` | high_volatility | 49 | 0.0230 |
| `amount_concentration_20d_cs` | range_bound | 215 | 0.0362 |
| `amount_concentration_20d_cs` | trend_down | 101 | 0.0125 |
| `amount_concentration_20d_cs` | trend_up | 34 | 0.0797 |
| `amount_concentration_20d_cs` | unclassified | 1500 | 0.0317 |
| `low_volatility_60d_cs` | high_volatility | 49 | 0.0264 |
| `low_volatility_60d_cs` | range_bound | 210 | 0.0274 |
| `low_volatility_60d_cs` | trend_down | 101 | 0.0349 |
| `low_volatility_60d_cs` | trend_up | 34 | 0.1831 |
| `low_volatility_60d_cs` | unclassified | 1484 | 0.0390 |
| `residual_volatility_60d_cs` | high_volatility | 49 | 0.0246 |
| `residual_volatility_60d_cs` | range_bound | 204 | 0.0300 |
| `residual_volatility_60d_cs` | trend_down | 101 | 0.0320 |
| `residual_volatility_60d_cs` | trend_up | 34 | 0.1518 |
| `residual_volatility_60d_cs` | unclassified | 1461 | 0.0380 |
| `bollinger_position_20d_cs` | high_volatility | 49 | 0.0523 |
| `bollinger_position_20d_cs` | range_bound | 215 | 0.0139 |
| `bollinger_position_20d_cs` | trend_down | 101 | 0.0067 |
| `bollinger_position_20d_cs` | trend_up | 34 | 0.0047 |
| `bollinger_position_20d_cs` | unclassified | 1500 | 0.0070 |
| `price_channel_position_60d_cs` | high_volatility | 49 | -0.0387 |
| `price_channel_position_60d_cs` | range_bound | 210 | -0.0032 |
| `price_channel_position_60d_cs` | trend_down | 101 | -0.0111 |
| `price_channel_position_60d_cs` | trend_up | 34 | -0.0342 |
| `price_channel_position_60d_cs` | unclassified | 1485 | -0.0064 |
| `rsi_divergence_14d_cs` | high_volatility | 49 | 0.0501 |
| `rsi_divergence_14d_cs` | range_bound | 212 | 0.0045 |
| `rsi_divergence_14d_cs` | trend_down | 101 | -0.0151 |
| `rsi_divergence_14d_cs` | trend_up | 34 | -0.0336 |
| `rsi_divergence_14d_cs` | unclassified | 1493 | -0.0007 |
| `revenue_stability_8q_cs` | high_volatility | 10 | 0.0070 |
| `revenue_stability_8q_cs` | range_bound | 36 | 0.0183 |
| `revenue_stability_8q_cs` | trend_down | 14 | -0.0178 |
| `revenue_stability_8q_cs` | trend_up | 8 | 0.0253 |
| `revenue_stability_8q_cs` | unclassified | 287 | -0.0005 |
| `margin_trend_8q_cs` | high_volatility | 9 | 0.0420 |
| `margin_trend_8q_cs` | range_bound | 23 | -0.0305 |
| `margin_trend_8q_cs` | trend_down | 11 | 0.0370 |
| `margin_trend_8q_cs` | trend_up | 8 | 0.0394 |
| `margin_trend_8q_cs` | unclassified | 219 | 0.0067 |

*Note: Some regime data is NOT_AVAILABLE. Regime breakdown is diagnostic only and does not affect gate.*

## Quality Gate Results

| Factor | Status | Failures | Reasons |
|---|---:|---|
| `asset_turnover_ttm_cs` | [DATA_MISSING] | 0 | factor cache empty |
| `growth_value_match_cs` | [DATA_MISSING] | 0 | factor cache empty |
| `ocf_to_mktcap_cs` | [DATA_MISSING] | 0 | factor cache empty |
| `ocf_to_profit_cs` | [DATA_MISSING] | 0 | factor cache empty |
| `fcf_yield_cs` | [DATA_MISSING] | 0 | factor cache empty |
| `cashflow_stability_8q_cs` | [DATA_MISSING] | 0 | factor cache empty |
| `accrual_quality_cs` | [DATA_MISSING] | 0 | factor cache empty |
| `receivable_pressure_cs` | [DATA_MISSING] | 0 | factor cache empty |
| `valuation_reversion_3y_cs` | [DATA_MISSING] | 0 | factor cache empty |
| `quality_value_composite_cs` | [DATA_MISSING] | 0 | factor cache empty |
| `dividend_quality_cs` | [DATA_MISSING] | 0 | factor cache empty |
| `industry_relative_quality_cs` | [DATA_MISSING] | 0 | factor cache empty |
| `industry_relative_growth_cs` | [DATA_MISSING] | 0 | factor cache empty |
| `industry_relative_value_cs` | [DATA_MISSING] | 0 | factor cache empty |
| `log_market_cap_cs` | [SUPPORT] | 7 | coverage: 0.0% < 80%; min_yearly_coverage: 0.0% < 60%; [raw] icir=0.113 < 0.200; [raw] no validation quantile data; [neutral] mean_rank_ic=0.008 < 0.010; [neutral] icir=0.045 < 0.200; [neutral] no val |
| `reversal_5_cs` | [FAIL] | 14 | [raw] mean_rank_ic=0.004 < 0.010; [raw] icir=0.016 < 0.200; [raw] net_spread=-0.0015 <= 0; [raw] pos_spread_years=1/4 < 3; [raw] top_quintile_net_excess=-0.0031 <= 0; [raw] pos_excess_years=1/4 < 3; [ |
| `reversal_20_cs` | [FAIL] | 13 | [raw] icir=0.062 < 0.200; [raw] net_spread=-0.0003 <= 0; [raw] pos_spread_years=1/4 < 3; [raw] top_quintile_net_excess=-0.0012 <= 0; [raw] pos_excess_years=1/4 < 3; [raw] net/gross_ratio=-21% < 50%; [ |
| `momentum_60_cs` | [FAIL] | 14 | [raw] mean_rank_ic=-0.013 < 0.010; [raw] icir=-0.062 < 0.200; [raw] pos_ic_years=1/4 < 3; [raw] net_spread=-0.0036 <= 0; [raw] pos_spread_years=1/4 < 3; [raw] top_quintile_net_excess=-0.0038 <= 0; [ra |
| `momentum_120_cs` | [FAIL] | 10 | [raw] icir=0.066 < 0.200; [raw] net_spread=-0.0016 <= 0; [raw] pos_spread_years=2/4 < 3; [raw] top_quintile_net_excess=-0.0032 <= 0; [raw] pos_excess_years=0/4 < 3; [neutral] mean_rank_ic=-0.018 < 0.0 |
| `volatility_20_cs` | [FAIL] | 5 | [raw] top_quintile_net_excess=-0.0001 <= 0; [raw] pos_excess_years=1/4 < 3; [neutral] pos_spread_years=1/4 < 3; [neutral] max_year_contrib=1437% > 60%; [neutral] net/gross_ratio=4% < 50% |
| `volatility_60_cs` | [FAIL] | 2 | neutralization: invalid (LOW_COVERAGE), cannot be WATCH_NEUTRAL_ONLY with coverage=5.1% < 70%; [raw] pos_excess_years=2/4 < 3 |
| `rsi_14_cs` | [FAIL] | 12 | [raw] mean_rank_ic=0.004 < 0.010; [raw] icir=0.023 < 0.200; [raw] net_spread=-0.0020 <= 0; [raw] pos_spread_years=1/4 < 3; [raw] top_quintile_net_excess=-0.0022 <= 0; [raw] pos_excess_years=1/4 < 3; [ |
| `macd_12_26_9_cs` | [FAIL] | 15 | [raw] mean_rank_ic=0.005 < 0.010; [raw] icir=0.035 < 0.200; [raw] pos_ic_years=2/4 < 3; [raw] net_spread=-0.0001 <= 0; [raw] pos_spread_years=2/4 < 3; [raw] top_quintile_net_excess=-0.0018 <= 0; [raw] |
| `pv_divergence_20_cs` | [FAIL] | 12 | [raw] icir=0.176 < 0.200; [raw] pos_spread_years=2/4 < 3; [raw] top_quintile_net_excess=-0.0014 <= 0; [raw] pos_excess_years=1/4 < 3; [raw] max_year_contrib=2271% > 60%; [raw] net/gross_ratio=3% < 50% |
| `ep_cs` | [FAIL] | 16 | coverage: 0.0% < 80%; min_yearly_coverage: 0.0% < 60%; [raw] mean_rank_ic=-0.083 < 0.010; [raw] icir=-0.390 < 0.200; [raw] pos_ic_years=0/4 < 3; [raw] net_spread=-0.0099 <= 0; [raw] pos_spread_years=0 |
| `bp_cs` | [FAIL] | 16 | coverage: 0.0% < 80%; min_yearly_coverage: 0.0% < 60%; [raw] mean_rank_ic=-0.093 < 0.010; [raw] icir=-0.479 < 0.200; [raw] pos_ic_years=0/4 < 3; [raw] net_spread=-0.0116 <= 0; [raw] pos_spread_years=0 |
| `sp_cs` | [FAIL] | 15 | coverage: 0.0% < 80%; min_yearly_coverage: 0.0% < 60%; [raw] mean_rank_ic=-0.067 < 0.010; [raw] icir=-0.402 < 0.200; [raw] pos_ic_years=0/4 < 3; [raw] net_spread=-0.0094 <= 0; [raw] pos_spread_years=0 |
| `roe_cs` | [FAIL] | 16 | coverage: 72.5% < 80%; min_yearly_coverage: 6.2% < 60%; [raw] mean_rank_ic=-0.023 < 0.010; [raw] icir=-0.157 < 0.200; [raw] pos_ic_years=0/4 < 3; [raw] net_spread=-0.0032 <= 0; [raw] pos_spread_years= |
| `gross_margin_cs` | [FAIL] | 16 | coverage: 59.2% < 80%; min_yearly_coverage: 5.5% < 60%; [raw] mean_rank_ic=-0.022 < 0.010; [raw] icir=-0.131 < 0.200; [raw] pos_ic_years=0/4 < 3; [raw] net_spread=-0.0039 <= 0; [raw] pos_spread_years= |
| `profit_growth_cs` | [FAIL] | 15 | coverage: 7.7% < 80%; min_yearly_coverage: 0.0% < 60%; [raw] mean_rank_ic=-0.020 < 0.010; [raw] icir=-0.209 < 0.200; [raw] pos_ic_years=2/4 < 3; [raw] net_spread=-0.0005 <= 0; [raw] pos_spread_years=2 |
| `revenue_growth_cs` | [FAIL] | 15 | coverage: 7.7% < 80%; min_yearly_coverage: 0.0% < 60%; [raw] mean_rank_ic=-0.021 < 0.010; [raw] icir=-0.166 < 0.200; [raw] pos_ic_years=1/4 < 3; [raw] net_spread=-0.0033 <= 0; [raw] pos_spread_years=1 |
| `leverage_cs` | [FAIL] | 15 | coverage: 72.2% < 80%; min_yearly_coverage: 6.2% < 60%; [raw] mean_rank_ic=-0.029 < 0.010; [raw] icir=-0.143 < 0.200; [raw] pos_ic_years=0/4 < 3; [raw] net_spread=-0.0029 <= 0; [raw] pos_spread_years= |
| `roe_stability_8q_cs` | [FAIL] | 15 | coverage: 70.2% < 80%; min_yearly_coverage: 0.0% < 60%; [raw] mean_rank_ic=-0.041 < 0.010; [raw] icir=-0.256 < 0.200; [raw] pos_ic_years=0/4 < 3; [raw] net_spread=-0.0044 <= 0; [raw] pos_spread_years= |
| `roa_ttm_cs` | [FAIL] | 16 | coverage: 58.6% < 80%; min_yearly_coverage: 5.5% < 60%; [raw] mean_rank_ic=-0.022 < 0.010; [raw] icir=-0.143 < 0.200; [raw] pos_ic_years=0/4 < 3; [raw] net_spread=-0.0039 <= 0; [raw] pos_spread_years= |
| `gross_margin_ttm_cs` | [FAIL] | 16 | coverage: 59.2% < 80%; min_yearly_coverage: 5.5% < 60%; [raw] mean_rank_ic=-0.022 < 0.010; [raw] icir=-0.133 < 0.200; [raw] pos_ic_years=0/4 < 3; [raw] net_spread=-0.0039 <= 0; [raw] pos_spread_years= |
| `net_margin_ttm_cs` | [FAIL] | 13 | coverage: 71.5% < 80%; min_yearly_coverage: 6.2% < 60%; [raw] mean_rank_ic=0.009 < 0.010; [raw] icir=0.083 < 0.200; [raw] net_spread=-0.0013 <= 0; [raw] pos_spread_years=2/4 < 3; [raw] top_quintile_ne |
| `profitability_quality_cs` | [FAIL] | 15 | coverage: 72.5% < 80%; min_yearly_coverage: 6.2% < 60%; [raw] mean_rank_ic=-0.015 < 0.010; [raw] icir=-0.116 < 0.200; [raw] pos_ic_years=1/4 < 3; [raw] net_spread=-0.0039 <= 0; [raw] pos_spread_years= |
| `revenue_growth_ttm_cs` | [FAIL] | 15 | coverage: 7.7% < 80%; min_yearly_coverage: 0.0% < 60%; [raw] mean_rank_ic=-0.021 < 0.010; [raw] icir=-0.166 < 0.200; [raw] pos_ic_years=1/4 < 3; [raw] net_spread=-0.0033 <= 0; [raw] pos_spread_years=1 |
| `profit_growth_ttm_cs` | [FAIL] | 15 | coverage: 7.7% < 80%; min_yearly_coverage: 0.0% < 60%; [raw] mean_rank_ic=-0.020 < 0.010; [raw] icir=-0.209 < 0.200; [raw] pos_ic_years=2/4 < 3; [raw] net_spread=-0.0005 <= 0; [raw] pos_spread_years=2 |
| `growth_stability_8q_cs` | [FAIL] | 12 | coverage: 8.0% < 80%; min_yearly_coverage: 0.0% < 60%; [raw] mean_rank_ic=-0.009 < 0.010; [raw] icir=0.074 < 0.200; [raw] pos_ic_years=2/4 < 3; [raw] no validation quantile data; [neutral] icir= < 0.2 |
| `earnings_acceleration_cs` | [FAIL] | 13 | coverage: 7.7% < 80%; min_yearly_coverage: 0.0% < 60%; [raw] icir=0.162 < 0.200; [raw] net_spread=-0.0003 <= 0; [raw] pos_spread_years=1/4 < 3; [raw] top_quintile_net_excess=-0.0014 <= 0; [raw] pos_ex |
| `industry_relative_ep_cs` | [FAIL] | 16 | coverage: 0.0% < 80%; min_yearly_coverage: 0.0% < 60%; [raw] mean_rank_ic=-0.059 < 0.010; [raw] icir=-0.462 < 0.200; [raw] pos_ic_years=0/4 < 3; [raw] net_spread=-0.0076 <= 0; [raw] pos_spread_years=0 |
| `industry_relative_bp_cs` | [FAIL] | 16 | coverage: 0.0% < 80%; min_yearly_coverage: 0.0% < 60%; [raw] mean_rank_ic=-0.072 < 0.010; [raw] icir=-0.489 < 0.200; [raw] pos_ic_years=0/4 < 3; [raw] net_spread=-0.0104 <= 0; [raw] pos_spread_years=0 |
| `industry_relative_momentum_60_cs` | [FAIL] | 12 | [raw] mean_rank_ic=-0.006 < 0.010; [raw] icir=-0.044 < 0.200; [raw] pos_ic_years=1/4 < 3; [raw] net_spread=-0.0023 <= 0; [raw] pos_spread_years=1/4 < 3; [raw] top_quintile_net_excess=-0.0027 <= 0; [ra |
| `momentum_60_skip5_cs` | [FAIL] | 8 | [raw] icir=0.103 < 0.200; [raw] top_quintile_net_excess=-0.0008 <= 0; [raw] pos_excess_years=2/4 < 3; [raw] max_year_contrib=74% > 60%; [neutral] icir=0.084 < 0.200; [neutral] net_spread=-0.0032 <= 0; |
| `momentum_120_skip20_cs` | [FAIL] | 12 | [raw] mean_rank_ic=0.002 < 0.010; [raw] icir=0.013 < 0.200; [raw] pos_ic_years=1/4 < 3; [raw] net_spread=-0.0024 <= 0; [raw] pos_spread_years=1/4 < 3; [raw] top_quintile_net_excess=-0.0033 <= 0; [raw] |
| `risk_adjusted_momentum_60_cs` | [FAIL] | 7 | [raw] icir=0.120 < 0.200; [raw] top_quintile_net_excess=-0.0003 <= 0; [raw] pos_excess_years=2/4 < 3; [raw] max_year_contrib=84% > 60%; [neutral] icir=0.109 < 0.200; [neutral] net_spread=-0.0041 <= 0; |
| `volume_confirmed_momentum_cs` | [FAIL] | 14 | [raw] mean_rank_ic=0.005 < 0.010; [raw] icir=0.033 < 0.200; [raw] pos_ic_years=2/4 < 3; [raw] net_spread=-0.0026 <= 0; [raw] pos_spread_years=1/4 < 3; [raw] top_quintile_net_excess=-0.0027 <= 0; [raw] |
| `trend_quality_cs` | [FAIL] | 11 | [raw] icir=0.122 < 0.200; [raw] pos_spread_years=2/4 < 3; [raw] top_quintile_net_excess=-0.0015 <= 0; [raw] pos_excess_years=1/4 < 3; [raw] max_year_contrib=908% > 60%; [raw] net/gross_ratio=8% < 50%; |
| `intraday_reversal_cs` | [FAIL] | 13 | [raw] mean_rank_ic=0.001 < 0.010; [raw] icir=0.005 < 0.200; [raw] pos_ic_years=2/4 < 3; [raw] net_spread=-0.0061 <= 0; [raw] pos_spread_years=0/4 < 3; [raw] top_quintile_net_excess=-0.0051 <= 0; [raw] |
| `overnight_reversal_cs` | [FAIL] | 14 | [raw] mean_rank_ic=0.000 < 0.010; [raw] icir=0.004 < 0.200; [raw] pos_ic_years=1/4 < 3; [raw] net_spread=-0.0074 <= 0; [raw] pos_spread_years=0/4 < 3; [raw] top_quintile_net_excess=-0.0056 <= 0; [raw] |
| `amihud_illiq_20d_cs` | [FAIL] | 12 | [raw] mean_rank_ic=-0.006 < 0.010; [raw] icir=-0.067 < 0.200; [raw] pos_ic_years=1/4 < 3; [raw] net_spread=-0.0017 <= 0; [raw] pos_spread_years=1/4 < 3; [raw] top_quintile_net_excess=-0.0019 <= 0; [ra |
| `vol_price_divergence_20d_cs` | [FAIL] | 11 | [raw] net_spread=-0.0012 <= 0; [raw] pos_spread_years=1/4 < 3; [raw] top_quintile_net_excess=-0.0018 <= 0; [raw] pos_excess_years=1/4 < 3; [raw] net/gross_ratio=-250% < 50%; [neutral] mean_rank_ic=0.0 |
| `volatility_squeeze_cs` | [FAIL] | 12 | [raw] mean_rank_ic=0.005 < 0.010; [raw] icir=0.044 < 0.200; [raw] net_spread=-0.0017 <= 0; [raw] pos_spread_years=0/4 < 3; [raw] top_quintile_net_excess=-0.0021 <= 0; [raw] pos_excess_years=1/4 < 3; [ |
| `tail_risk_60d_cs` | [FAIL] | 5 | [raw] top_quintile_net_excess=-0.0005 <= 0; [raw] pos_excess_years=2/4 < 3; [neutral] net_spread=-0.0022 <= 0; [neutral] pos_spread_years=1/4 < 3; [neutral] net/gross_ratio=-168% < 50% |
| `turnover_anomaly_20d_cs` | [FAIL] | 12 | coverage: 0.0% < 80%; min_yearly_coverage: 0.0% < 60%; [raw] mean_rank_ic=-0.028 < 0.010; [raw] icir=-0.156 < 0.200; [raw] pos_ic_years=0/4 < 3; [raw] net_spread=-0.0014 <= 0; [raw] pos_spread_years=1 |
| `turnover_volatility_60d_cs` | [FAIL] | 12 | coverage: 0.0% < 80%; min_yearly_coverage: 0.0% < 60%; [raw] mean_rank_ic=-0.006 < 0.010; [raw] icir=-0.059 < 0.200; [raw] pos_ic_years=1/4 < 3; [raw] max_year_contrib=2134% > 60%; [raw] net/gross_rat |
| `volume_shock_5d_cs` | [FAIL] | 13 | [raw] mean_rank_ic=-0.001 < 0.010; [raw] icir=-0.012 < 0.200; [raw] pos_ic_years=1/4 < 3; [raw] net_spread=-0.0029 <= 0; [raw] pos_spread_years=0/4 < 3; [raw] top_quintile_net_excess=-0.0029 <= 0; [ra |
| `amount_concentration_20d_cs` | [FAIL] | 12 | [raw] icir=0.136 < 0.200; [raw] net_spread=-0.0006 <= 0; [raw] pos_spread_years=2/4 < 3; [raw] top_quintile_net_excess=-0.0017 <= 0; [raw] pos_excess_years=1/4 < 3; [raw] net/gross_ratio=-131% < 50%;  |
| `bollinger_position_20d_cs` | [FAIL] | 12 | [raw] mean_rank_ic=0.009 < 0.010; [raw] icir=0.046 < 0.200; [raw] net_spread=-0.0025 <= 0; [raw] pos_spread_years=0/4 < 3; [raw] top_quintile_net_excess=-0.0027 <= 0; [raw] pos_excess_years=1/4 < 3; [ |
| `price_channel_position_60d_cs` | [FAIL] | 13 | [raw] mean_rank_ic=-0.020 < 0.010; [raw] icir=-0.101 < 0.200; [raw] pos_ic_years=1/4 < 3; [raw] net_spread=-0.0025 <= 0; [raw] pos_spread_years=1/4 < 3; [raw] top_quintile_net_excess=-0.0034 <= 0; [ra |
| `rsi_divergence_14d_cs` | [FAIL] | 13 | [raw] mean_rank_ic=-0.002 < 0.010; [raw] icir=-0.009 < 0.200; [raw] pos_ic_years=2/4 < 3; [raw] net_spread=-0.0024 <= 0; [raw] pos_spread_years=0/4 < 3; [raw] top_quintile_net_excess=-0.0030 <= 0; [ra |
| `revenue_stability_8q_cs` | [FAIL] | 15 | coverage: 8.0% < 80%; min_yearly_coverage: 0.0% < 60%; [raw] mean_rank_ic=-0.040 < 0.010; [raw] icir=-0.197 < 0.200; [raw] pos_ic_years=1/4 < 3; [raw] net_spread=-0.0012 <= 0; [raw] pos_spread_years=0 |
| `margin_trend_8q_cs` | [FAIL] | 14 | coverage: 7.7% < 80%; min_yearly_coverage: 0.0% < 60%; [raw] mean_rank_ic=-0.006 < 0.010; [raw] icir=-0.143 < 0.200; [raw] top_quintile_net_excess=-0.0019 <= 0; [raw] pos_excess_years=2/4 < 3; [raw] m |
| `low_volatility_60d_cs` | [WATCH_NEUTRAL_UNAVAILABLE] | 1 | neutralization: invalid (LOW_COVERAGE), coverage=4.9% < 70% | neutralization_invalid: LOW_COVERAGE |
| `residual_volatility_60d_cs` | [WATCH_NEUTRAL_UNAVAILABLE] | 1 | neutralization: invalid (LOW_COVERAGE), coverage=4.9% < 70% | neutralization_invalid: LOW_COVERAGE |

## Candidate Pool

- **Eligible**: []
- **Watch for Review**: ['low_volatility_60d_cs', 'residual_volatility_60d_cs']
- **Support — Neutralizers**: ['log_market_cap_cs']
- **Support — Redundant**: []
- **Missing Data**: ['asset_turnover_ttm_cs', 'growth_value_match_cs', 'ocf_to_mktcap_cs', 'ocf_to_profit_cs', 'fcf_yield_cs', 'cashflow_stability_8q_cs', 'accrual_quality_cs', 'receivable_pressure_cs', 'valuation_reversion_3y_cs', 'quality_value_composite_cs', 'dividend_quality_cs', 'industry_relative_quality_cs', 'industry_relative_growth_cs', 'industry_relative_value_cs']
- **FAIL**: ['reversal_5_cs', 'reversal_20_cs', 'momentum_60_cs', 'momentum_120_cs', 'volatility_20_cs', 'volatility_60_cs', 'rsi_14_cs', 'macd_12_26_9_cs', 'pv_divergence_20_cs', 'ep_cs', 'bp_cs', 'sp_cs', 'roe_cs', 'gross_margin_cs', 'profit_growth_cs', 'revenue_growth_cs', 'leverage_cs', 'roe_stability_8q_cs', 'roa_ttm_cs', 'gross_margin_ttm_cs', 'net_margin_ttm_cs', 'profitability_quality_cs', 'revenue_growth_ttm_cs', 'profit_growth_ttm_cs', 'growth_stability_8q_cs', 'earnings_acceleration_cs', 'industry_relative_ep_cs', 'industry_relative_bp_cs', 'industry_relative_momentum_60_cs', 'momentum_60_skip5_cs', 'momentum_120_skip20_cs', 'risk_adjusted_momentum_60_cs', 'volume_confirmed_momentum_cs', 'trend_quality_cs', 'intraday_reversal_cs', 'overnight_reversal_cs', 'amihud_illiq_20d_cs', 'vol_price_divergence_20d_cs', 'volatility_squeeze_cs', 'tail_risk_60d_cs', 'turnover_anomaly_20d_cs', 'turnover_volatility_60d_cs', 'volume_shock_5d_cs', 'amount_concentration_20d_cs', 'bollinger_position_20d_cs', 'price_channel_position_60d_cs', 'rsi_divergence_14d_cs', 'revenue_stability_8q_cs', 'margin_trend_8q_cs']
- **Recommendation**: **NO_ALPHA_SOURCE_FOUND**

## Conclusions

1. **哪些因子真的有净 alpha**: None — no factors pass the full quality gate with net positive post-cost alpha.
2. **哪些因子只是方向/实现问题**: low_volatility_60d_cs, residual_volatility_60d_cs
3. **哪些因子数据缺失，不应永久淘汰**: asset_turnover_ttm_cs, growth_value_match_cs, ocf_to_mktcap_cs, ocf_to_profit_cs, fcf_yield_cs, cashflow_stability_8q_cs, accrual_quality_cs, receivable_pressure_cs, valuation_reversion_3y_cs, quality_value_composite_cs, dividend_quality_cs, industry_relative_quality_cs, industry_relative_growth_cs, industry_relative_value_cs
4. **哪些因子应永久淘汰**: reversal_5_cs, reversal_20_cs, momentum_60_cs, momentum_120_cs, volatility_20_cs, volatility_60_cs, rsi_14_cs, macd_12_26_9_cs, pv_divergence_20_cs, ep_cs, bp_cs, sp_cs, roe_cs, gross_margin_cs, profit_growth_cs, revenue_growth_cs, leverage_cs, roe_stability_8q_cs, roa_ttm_cs, gross_margin_ttm_cs, net_margin_ttm_cs, profitability_quality_cs, revenue_growth_ttm_cs, profit_growth_ttm_cs, growth_stability_8q_cs, earnings_acceleration_cs, industry_relative_ep_cs, industry_relative_bp_cs, industry_relative_momentum_60_cs, momentum_60_skip5_cs, momentum_120_skip20_cs, risk_adjusted_momentum_60_cs, volume_confirmed_momentum_cs, trend_quality_cs, intraday_reversal_cs, overnight_reversal_cs, amihud_illiq_20d_cs, vol_price_divergence_20d_cs, volatility_squeeze_cs, tail_risk_60d_cs, turnover_anomaly_20d_cs, turnover_volatility_60d_cs, volume_shock_5d_cs, amount_concentration_20d_cs, bollinger_position_20d_cs, price_channel_position_60d_cs, rsi_divergence_14d_cs, revenue_stability_8q_cs, margin_trend_8q_cs

## Sleeve Rebuild Authorization

❌ **NOT AUTHORIZED**: No eligible factors. Sleeve/strategy rebuild is blocked.
   → Action: Restore data for asset_turnover_ttm_cs, growth_value_match_cs, ocf_to_mktcap_cs, ocf_to_profit_cs, fcf_yield_cs, cashflow_stability_8q_cs, accrual_quality_cs, receivable_pressure_cs, valuation_reversion_3y_cs, quality_value_composite_cs, dividend_quality_cs, industry_relative_quality_cs, industry_relative_growth_cs, industry_relative_value_cs before re-running factor quality rebuild.
   → Action: Manually review 2 WATCH factor(s) for potential alpha.

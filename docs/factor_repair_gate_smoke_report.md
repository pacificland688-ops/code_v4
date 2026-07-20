# Factor Quality Rebuild Report (v2)

生成日期：2026-06-27 16:41
配置：`outputs\analysis\factor_repair_gate_smoke_config.yaml` (sha256=9a8761d642b9852e)
随机种子：42

## Summary

- FAIL: 4
- **Recommendation**: **NO_ALPHA_SOURCE_FOUND**

## No-Leakage Alignment Audit

| Factor | Horizon | Lag (days) | Aligned Rows | Signal Dates | Cal/Val/Watch | Status |
|---|---:|---:|---:|---:|---|
| `reversal_5_liquidity_adj_cs` | fwd_ret_5d | 0 | 612812 | 1933 | 304528/308284/0 | PASS |
| `reversal_20_vol_adj_cs` | fwd_ret_5d | 0 | 606020 | 1913 | 297773/308247/0 | PASS |
| `low_beta_60_cs` | fwd_ret_5d | 0 | 606020 | 1913 | 297773/308247/0 | PASS |
| `drawdown_resilience_cs` | fwd_ret_5d | 0 | 596407 | 1885 | 288230/308177/0 | PASS |

## Raw vs Mcap-Neutral Comparison (Validation 2021-2024)

| Factor | Raw IC | Neutral IC | Raw ICIR | Neutral ICIR | Raw Net Spread | Neutral Net Spread | Size Dependent |
|---|---:|---:|---:|---:|---:|---|
| `reversal_5_liquidity_adj_cs` | 0.0038 | -0.0015 |  |  | -0.22% | -0.66% | False |
| `reversal_20_vol_adj_cs` | 0.0144 | -0.0270 |  |  | -0.10% | -1.22% | True |
| `low_beta_60_cs` | 0.0395 | -0.0033 |  |  | -0.04% | -0.46% | True |
| `drawdown_resilience_cs` | 0.0048 | -0.0350 |  |  | -0.10% | -1.23% | False |

## Turnover Cost Analysis (Validation 2021-2024)

| Factor | Basis | Method | Avg Turnover | Gross Spread | Net Spread | Net/Gross |
|---|---:|---:|---:|---:|---:|
| `drawdown_resilience_cs` | raw | REAL_WEIGHT_DRIFT | 93.5% | -0.29% | -0.48% | 88.8% |
| `low_beta_60_cs` | raw | REAL_WEIGHT_DRIFT | 38.2% | -0.15% | -0.23% | -238.5% |
| `reversal_20_vol_adj_cs` | raw | REAL_WEIGHT_DRIFT | 97.9% | -0.26% | -0.46% | 594.1% |
| `reversal_5_liquidity_adj_cs` | raw | REAL_WEIGHT_DRIFT | 115.9% | 0.01% | -0.22% | 62.7% |

## IC Trend (Validation Window)

| Factor | Basis | Monthly ICs | Slope | p-value | Declining |
|---|---:|---:|---:|---|
| `reversal_5_liquidity_adj_cs` | raw | 48 | -0.000731 | 0.4622 | False |
| `reversal_5_liquidity_adj_cs` | mcap_neutral | 45 | -0.000705 | 0.7258 | False |
| `reversal_20_vol_adj_cs` | raw | 48 | -0.000097 | 0.9159 | False |
| `reversal_20_vol_adj_cs` | mcap_neutral | 45 | -0.000956 | 0.6021 | False |
| `low_beta_60_cs` | raw | 48 | 0.001807 | 0.2029 | False |
| `low_beta_60_cs` | mcap_neutral | 45 | -0.000328 | 0.9035 | False |
| `drawdown_resilience_cs` | raw | 48 | -0.000532 | 0.6051 | False |
| `drawdown_resilience_cs` | mcap_neutral | 45 | -0.000419 | 0.8383 | False |

## Rolling Window Robustness

| Factor | Window | Basis | Status | Mean IC | ICIR | Net Spread | Pos IC Yrs | Pos Spread Yrs |
|---|---:|---:|---:|---:|---:|---:|---:|
| `reversal_5_liquidity_adj_cs` | 2018_2021 | raw | FAIL | 0.0189 | 0.115 | -0.23% | 4/4 | 0/4 |
| `reversal_5_liquidity_adj_cs` | 2019_2022 | raw | FAIL | 0.0191 | 0.116 | -0.16% | 4/4 | 1/4 |
| `reversal_5_liquidity_adj_cs` | 2020_2023 | raw | FAIL | 0.0061 | 0.031 | -0.27% | 3/4 | 1/4 |
| `reversal_5_liquidity_adj_cs` | 2021_2024 | raw | FAIL | 0.0038 | 0.014 | -0.22% | 3/4 | 1/4 |
| `reversal_20_vol_adj_cs` | 2018_2021 | raw | FAIL | 0.0176 | 0.105 | -0.12% | 4/4 | 1/4 |
| `reversal_20_vol_adj_cs` | 2019_2022 | raw | FAIL | 0.0237 | 0.138 | -0.03% | 4/4 | 2/4 |
| `reversal_20_vol_adj_cs` | 2020_2023 | raw | FAIL | 0.0128 | 0.069 | -0.15% | 3/4 | 1/4 |
| `reversal_20_vol_adj_cs` | 2021_2024 | raw | FAIL | 0.0144 | 0.071 | -0.10% | 3/4 | 1/4 |
| `low_beta_60_cs` | 2018_2021 | raw | FAIL | 0.0071 | 0.031 | -0.22% | 2/4 | 1/4 |
| `low_beta_60_cs` | 2019_2022 | raw | FAIL | 0.0069 | 0.031 | -0.29% | 2/4 | 0/4 |
| `low_beta_60_cs` | 2020_2023 | raw | FAIL | 0.0207 | 0.090 | -0.16% | 3/4 | 1/4 |
| `low_beta_60_cs` | 2021_2024 | raw | FAIL | 0.0395 | 0.141 | -0.04% | 4/4 | 2/4 |
| `drawdown_resilience_cs` | 2018_2021 | raw | FAIL | 0.0131 | 0.075 | -0.11% | 2/4 | 1/4 |
| `drawdown_resilience_cs` | 2019_2022 | raw | FAIL | 0.0188 | 0.103 | 0.01% | 3/4 | 2/4 |
| `drawdown_resilience_cs` | 2020_2023 | raw | FAIL | 0.0041 | 0.019 | -0.16% | 2/4 | 1/4 |
| `drawdown_resilience_cs` | 2021_2024 | raw | FAIL | 0.0048 | 0.022 | -0.10% | 3/4 | 1/4 |

## Correlation Clusters

No correlation data available (fewer than 2 eligible factors).

## Capacity / Liquidity Audit

| Factor | Year | Median Top Amt (CNY) | Median Mkt Cap (CNY) | Participation Rate | Status |
|---|---:|---:|---:|---:|---|
| `reversal_5_liquidity_adj_cs` | 2021 | 583473832 | 85518239718 | 0.07% | PASS |
| `reversal_5_liquidity_adj_cs` | 2022 | 491909945 | 82904790646 | 0.10% | PASS |
| `reversal_5_liquidity_adj_cs` | 2023 | 501651947 | 85763795654 | 0.09% | PASS |
| `reversal_5_liquidity_adj_cs` | 2024 | 502718975 | 75590605631 | 0.10% | PASS |
| `reversal_20_vol_adj_cs` | 2021 | 462766825 | 86634560752 | 0.09% | PASS |
| `reversal_20_vol_adj_cs` | 2022 | 409830938 | 86954829140 | 0.11% | PASS |
| `reversal_20_vol_adj_cs` | 2023 | 430036436 | 85808373515 | 0.13% | PASS |
| `reversal_20_vol_adj_cs` | 2024 | 453445096 | 86136270000 | 0.13% | PASS |
| `low_beta_60_cs` | 2021 | 490926649 | 99560661489 | 0.08% | PASS |
| `low_beta_60_cs` | 2022 | 503038458 | 94815489670 | 0.10% | PASS |
| `low_beta_60_cs` | 2023 | 410058571 | 87184771494 | 0.13% | PASS |
| `low_beta_60_cs` | 2024 | 606852646 | 79762356182 | 0.09% | PASS |
| `drawdown_resilience_cs` | 2021 | 461958537 | 87055873062 | 0.09% | PASS |
| `drawdown_resilience_cs` | 2022 | 436901068 | 84051825380 | 0.12% | PASS |
| `drawdown_resilience_cs` | 2023 | 430733061 | 84559196434 | 0.13% | PASS |
| `drawdown_resilience_cs` | 2024 | 458508087 | 85056722950 | 0.13% | PASS |

## Regime Breakdown

| Factor | Regime | N Dates | Mean IC |
|---|---:|---:|
| `reversal_5_liquidity_adj_cs` | high_volatility | 49 | 0.0700 |
| `reversal_5_liquidity_adj_cs` | range_bound | 200 | 0.0208 |
| `reversal_5_liquidity_adj_cs` | trend_down | 101 | 0.0018 |
| `reversal_5_liquidity_adj_cs` | trend_up | 49 | 0.0088 |
| `reversal_5_liquidity_adj_cs` | unclassified | 1498 | 0.0116 |
| `reversal_5_liquidity_adj_cs` | value_rotation | 1 | 0.1976 |
| `reversal_20_vol_adj_cs` | high_volatility | 49 | 0.0251 |
| `reversal_20_vol_adj_cs` | range_bound | 195 | 0.0160 |
| `reversal_20_vol_adj_cs` | trend_down | 101 | 0.0076 |
| `reversal_20_vol_adj_cs` | trend_up | 49 | 0.0316 |
| `reversal_20_vol_adj_cs` | unclassified | 1483 | 0.0135 |
| `reversal_20_vol_adj_cs` | value_rotation | 1 | -0.3796 |
| `low_beta_60_cs` | high_volatility | 49 | 0.0393 |
| `low_beta_60_cs` | range_bound | 195 | 0.0002 |
| `low_beta_60_cs` | trend_down | 101 | 0.0346 |
| `low_beta_60_cs` | trend_up | 49 | 0.1360 |
| `low_beta_60_cs` | unclassified | 1483 | 0.0281 |
| `low_beta_60_cs` | value_rotation | 1 | 0.4625 |
| `drawdown_resilience_cs` | high_volatility | 49 | 0.0218 |
| `drawdown_resilience_cs` | range_bound | 190 | 0.0117 |
| `drawdown_resilience_cs` | trend_down | 101 | 0.0025 |
| `drawdown_resilience_cs` | trend_up | 49 | 0.0035 |
| `drawdown_resilience_cs` | unclassified | 1460 | 0.0063 |
| `drawdown_resilience_cs` | value_rotation | 1 | -0.5006 |

## Quality Gate Results

| Factor | Status | Failures | Reasons |
|---|---:|---|
| `reversal_5_liquidity_adj_cs` | [FAIL] | 13 | [raw] mean_rank_ic=0.004 < 0.010; [raw] icir=0.014 < 0.200; [raw] net_spread=-0.0022 <= 0; [raw] pos_spread_years=1/4 < 3; [raw] top_quintile_net_excess=-0.0035 <= 0; [raw] pos_excess_years=1/4 < 3; [ |
| `reversal_20_vol_adj_cs` | [FAIL] | 13 | [raw] icir=0.071 < 0.200; [raw] net_spread=-0.0010 <= 0; [raw] pos_spread_years=1/4 < 3; [raw] top_quintile_net_excess=-0.0016 <= 0; [raw] pos_excess_years=1/4 < 3; [raw] net/gross_ratio=-196% < 50%;  |
| `low_beta_60_cs` | [FAIL] | 11 | [raw] icir=0.141 < 0.200; [raw] net_spread=-0.0004 <= 0; [raw] pos_spread_years=2/4 < 3; [raw] top_quintile_net_excess=-0.0013 <= 0; [raw] pos_excess_years=1/4 < 3; [raw] net/gross_ratio=-1414% < 50%; |
| `drawdown_resilience_cs` | [FAIL] | 13 | [raw] mean_rank_ic=0.005 < 0.010; [raw] icir=0.022 < 0.200; [raw] net_spread=-0.0010 <= 0; [raw] pos_spread_years=1/4 < 3; [raw] top_quintile_net_excess=-0.0015 <= 0; [raw] pos_excess_years=1/4 < 3; [ |

## Candidate Pool

- **Eligible**: []
- **Watch for Review**: []
- **Support — Neutralizers**: []
- **Support — Redundant**: []
- **Missing Data**: []
- **FAIL**: ['reversal_5_liquidity_adj_cs', 'reversal_20_vol_adj_cs', 'low_beta_60_cs', 'drawdown_resilience_cs']
- **Recommendation**: **NO_ALPHA_SOURCE_FOUND**

## Conclusions

1. **哪些因子真的有净 alpha**: None — no factors pass the full quality gate with net positive post-cost alpha.
2. **哪些因子只是方向/实现问题**: None identified
3. **哪些因子数据缺失**: None
4. **哪些因子应永久淘汰**: reversal_5_liquidity_adj_cs, reversal_20_vol_adj_cs, low_beta_60_cs, drawdown_resilience_cs

## Sleeve Rebuild Authorization

❌ **NOT AUTHORIZED**: No eligible factors. Sleeve/strategy rebuild is blocked.

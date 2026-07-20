# Strategy Alpha Failure Diagnosis Report

生成日期：2026-06-14 08:54

## 1. Benchmark Calendar Audit

- Years with benchmark calendar mismatch (>50bps spread): 9/9
- Years with BENCHMARK_RETURN_CONFLICT (same period, different bm return): 0/9

| year | n_strategies | bm_spread_bps | calendar_mismatch | return_conflict | max_conflict_bps | calendar_status | n_common |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 2017 | 5 | 138.3 | True | False | 0.0 | BENCHMARK_CALENDAR_MISMATCH | 44 |
| 2018 | 5 | 292.9 | True | False | 0.0 | BENCHMARK_CALENDAR_MISMATCH | 44 |
| 2019 | 5 | 1329.8 | True | False | 0.0 | BENCHMARK_CALENDAR_MISMATCH | 46 |
| 2020 | 5 | 518.5 | True | False | 0.0 | BENCHMARK_CALENDAR_MISMATCH | 46 |
| 2021 | 5 | 718.4 | True | False | 0.0 | BENCHMARK_CALENDAR_MISMATCH | 45 |
| 2022 | 5 | 222.4 | True | False | 0.0 | BENCHMARK_CALENDAR_MISMATCH | 43 |
| 2023 | 5 | 443.7 | True | False | 0.0 | BENCHMARK_CALENDAR_MISMATCH | 44 |
| 2024 | 5 | 406.9 | True | False | 0.0 | BENCHMARK_CALENDAR_MISMATCH | 45 |
| 2026 | 5 | 681.6 | True | False | 0.0 | BENCHMARK_CALENDAR_MISMATCH | 15 |

## 2. Normalized Strategy Returns (Common Calendar)

| year | strategy | common_return | common_excess | common_IR | excess_reliable | original_excess |
|---:|---|---:|---:|---:|---:|---:|
| 2017 | A_5reversal | -4.0% | -23.3% | -2.43 | ✅ | -21.7% |
| 2017 | B_dynamic | -6.1% | -25.4% | -3.21 | ✅ | -23.9% |
| 2017 | C_regime_baseline | -5.7% | -25.0% | -1.50 | ✅ | -19.9% |
| 2017 | D_regime_overlay | -5.4% | -24.7% | -1.48 | ✅ | -19.5% |
| 2017 | E_shock_reversal | -9.5% | -28.9% | -1.82 | ✅ | -24.0% |
| 2018 | A_5reversal | -37.1% | -14.9% | -0.48 | ✅ | -15.3% |
| 2018 | B_dynamic | -33.5% | -11.3% | -0.37 | ✅ | -14.4% |
| 2018 | C_regime_baseline | -32.9% | -10.7% | -0.16 | ✅ | -18.3% |
| 2018 | D_regime_overlay | -31.8% | -9.6% | -0.12 | ✅ | -17.5% |
| 2018 | E_shock_reversal | -32.5% | -10.3% | 0.15 | ✅ | -11.0% |
| 2019 | A_5reversal | 11.6% | -10.0% | -0.83 | ✅ | -8.3% |
| 2019 | B_dynamic | 15.8% | -5.8% | -0.44 | ✅ | -4.6% |
| 2019 | C_regime_baseline | 8.3% | -13.3% | -0.30 | ✅ | -13.7% |
| 2019 | D_regime_overlay | 9.1% | -12.5% | -0.27 | ✅ | -13.4% |
| 2019 | E_shock_reversal | 11.4% | -10.2% | -0.16 | ✅ | -11.4% |
| 2020 | A_5reversal | 5.1% | -26.9% | -1.69 | ✅ | -21.8% |
| 2020 | B_dynamic | 12.0% | -20.0% | -0.94 | ✅ | -14.6% |
| 2020 | C_regime_baseline | 13.6% | -18.4% | -1.17 | ✅ | -8.6% |
| 2020 | D_regime_overlay | 17.3% | -14.7% | -1.07 | ✅ | -4.2% |
| 2020 | E_shock_reversal | 7.3% | -24.7% | -1.36 | ✅ | -14.3% |
| 2021 | A_5reversal | -25.4% | -8.9% | -0.62 | ✅ | -11.1% |
| 2021 | B_dynamic | -42.0% | -25.5% | -3.18 | ✅ | -35.7% |
| 2021 | C_regime_baseline | -25.9% | -9.4% | -1.69 | ✅ | -6.5% |
| 2021 | D_regime_overlay | -27.4% | -10.8% | -1.78 | ✅ | -7.0% |
| 2021 | E_shock_reversal | -26.3% | -9.8% | -1.74 | ✅ | -9.6% |
| 2022 | A_5reversal | -15.1% | 3.8% | 0.24 | ✅ | 3.9% |
| 2022 | B_dynamic | -18.5% | 0.4% | 0.02 | ✅ | 0.2% |
| 2022 | C_regime_baseline | -9.7% | 9.2% | -0.30 | ✅ | 8.7% |
| 2022 | D_regime_overlay | -8.5% | 10.5% | -0.26 | ✅ | 10.0% |
| 2022 | E_shock_reversal | -10.1% | 8.8% | -0.33 | ✅ | 8.8% |
| 2023 | A_5reversal | -19.0% | 0.7% | 0.09 | ✅ | 0.8% |
| 2023 | B_dynamic | -20.1% | -0.3% | -0.05 | ✅ | -0.5% |
| 2023 | C_regime_baseline | -25.6% | -5.9% | -0.32 | ✅ | -6.6% |
| 2023 | D_regime_overlay | -21.4% | -1.6% | -0.05 | ✅ | -1.9% |
| 2023 | E_shock_reversal | -27.4% | -7.6% | -0.43 | ✅ | -8.9% |
| 2024 | A_5reversal | 7.6% | -14.3% | -0.76 | ✅ | -13.9% |
| 2024 | B_dynamic | 13.2% | -8.7% | -0.64 | ✅ | -9.2% |
| 2024 | C_regime_baseline | 19.7% | -2.2% | -0.17 | ✅ | 0.4% |
| 2024 | D_regime_overlay | 22.5% | 0.6% | -0.08 | ✅ | 2.5% |
| 2024 | E_shock_reversal | 22.4% | 0.5% | -0.09 | ✅ | 2.4% |

## 3. Investment Gate Decision

| Strategy | Avg Return | Avg Excess | Median Excess | Pos Years | Avg IR | Max Loss | Excess Reliable | Status |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| A_5reversal | -9.6% | -11.7% | -12.1% | 2/8 | -0.81 | -26.9% | ✅ | **NO_GO** |
| B_dynamic | -9.9% | -12.1% | -10.0% | 1/8 | -1.10 | -25.5% | ✅ | **NO_GO** |
| C_regime_baseline | -7.3% | -9.5% | -10.0% | 1/8 | -0.70 | -25.0% | ✅ | **NO_GO** |
| D_regime_overlay | -5.7% | -7.9% | -10.2% | 2/8 | -0.64 | -24.7% | ✅ | **NO_GO** |
| E_shock_reversal | -8.1% | -10.2% | -10.0% | 2/8 | -0.72 | -28.9% | ✅ | **NO_GO** |

- **A_5reversal**: avg_return=-9.6% <= 0.0%; avg_excess=-11.7% < 2.0%; median_excess=-12.1% <= 0.0%; pos_years=2/8 < 5/8; avg_ir=-0.81 < 0.30; max_loss=-26.9% < -10.0%
- **B_dynamic**: avg_return=-9.9% <= 0.0%; avg_excess=-12.1% < 2.0%; median_excess=-10.0% <= 0.0%; pos_years=1/8 < 5/8; avg_ir=-1.10 < 0.30; max_loss=-25.5% < -10.0%
- **C_regime_baseline**: avg_return=-7.3% <= 0.0%; avg_excess=-9.5% < 2.0%; median_excess=-10.0% <= 0.0%; pos_years=1/8 < 5/8; avg_ir=-0.70 < 0.30; max_loss=-25.0% < -10.0%
- **D_regime_overlay**: avg_return=-5.7% <= 0.0%; avg_excess=-7.9% < 2.0%; median_excess=-10.2% <= 0.0%; pos_years=2/8 < 5/8; avg_ir=-0.64 < 0.30; max_loss=-24.7% < -10.0%
- **E_shock_reversal**: avg_return=-8.1% <= 0.0%; avg_excess=-10.2% < 2.0%; median_excess=-10.0% <= 0.0%; pos_years=2/8 < 5/8; avg_ir=-0.72 < 0.30; max_loss=-28.9% < -10.0%

## 4. Factor Alpha Scorecard (2017-2024) — Strict Retention Gate

| Factor | Type | Mean IC | ICIR | Pos IC Yrs | LongOnly Top | Pos LO Yrs | TB Excess | Pos TB Yrs | Monotonicity | Pos Mono Yrs | Coverage | Retain? |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `volatility_60_cs` | technical | 0.040 | 1.114 | 7/8 | -0.7% | 4/8 | 3.5% | 5/8 |  | 0/8 |  | ❌ |
| `pv_divergence_20_cs` | technical | 0.037 | 2.187 | 8/8 | 3.9% | 7/8 | 15.2% | 7/8 |  | 0/8 |  | ❌ |
| `volatility_20_cs` | technical | 0.036 | 1.095 | 7/8 | -2.3% | 4/8 | 2.7% | 6/8 |  | 0/8 |  | ❌ |
| `momentum_120_cs` | technical | 0.019 | 0.670 | 5/8 | -2.1% | 4/8 | 11.9% | 5/8 |  | 0/8 |  | ❌ |
| `reversal_5_cs` | technical | 0.018 | 1.087 | 7/8 | 8.3% | 6/8 | 24.7% | 7/8 |  | 0/8 |  | ❌ |
| `reversal_20_cs` | technical | 0.016 | 0.767 | 6/8 | -0.1% | 5/8 | 8.6% | 5/8 |  | 0/8 |  | ❌ |
| `ep_cs` | fundamental | 0.013 | 0.389 | 7/8 | -4.9% | 5/8 | -3.7% | 4/8 |  | 0/8 |  | ❌ |
| `bp_cs` | fundamental | 0.012 | 0.235 | 5/8 | 0.0% | 5/8 | 2.8% | 5/8 |  | 0/8 |  | ❌ |
| `sp_cs` | fundamental | 0.010 | 0.322 | 6/8 | -2.1% | 4/8 | 0.7% | 5/8 |  | 0/8 |  | ❌ |
| `rsi_14_cs` | technical | 0.008 | 0.404 | 3/8 | -4.0% | 3/8 | 1.7% | 5/8 |  | 0/8 |  | ❌ |
| `momentum_60_cs` | technical | 0.000 | 0.014 | 5/8 | -3.6% | 3/8 | 1.8% | 5/8 |  | 0/8 |  | ❌ |
| `macd_12_26_9_cs` | technical | -0.006 | -0.397 | 3/8 | -9.3% | 1/8 | -9.3% | 3/8 |  | 0/8 |  | ❌ |

### Factors Failing Retention Gate
- `volatility_60_cs`: avg_long_only_top=-0.7% <= 0; missing decile_monotonicity data; missing coverage data
- `pv_divergence_20_cs`: missing decile_monotonicity data; missing coverage data
- `volatility_20_cs`: avg_long_only_top=-2.3% <= 0; missing decile_monotonicity data; missing coverage data
- `momentum_120_cs`: avg_long_only_top=-2.1% <= 0; missing decile_monotonicity data; missing coverage data
- `reversal_5_cs`: missing decile_monotonicity data; missing coverage data
- `reversal_20_cs`: avg_long_only_top=-0.1% <= 0; missing decile_monotonicity data; missing coverage data
- `ep_cs`: avg_long_only_top=-4.9% <= 0; avg_top_bottom=-3.7% <= 0; missing decile_monotonicity data; missing coverage data
- `bp_cs`: missing decile_monotonicity data; missing coverage data
- `sp_cs`: avg_long_only_top=-2.1% <= 0; missing decile_monotonicity data; missing coverage data
- `rsi_14_cs`: avg_long_only_top=-4.0% <= 0; missing decile_monotonicity data; positive_ic_years=3/8 < 5; missing coverage data
- `momentum_60_cs`: avg_long_only_top=-3.6% <= 0; missing decile_monotonicity data; missing coverage data
- `macd_12_26_9_cs`: avg_long_only_top=-9.3% <= 0; avg_top_bottom=-9.3% <= 0; missing decile_monotonicity data; mean_ic=-0.006 <= 0; max_consecutive_negative=3 >= 3; missing coverage data

## 5. Sleeve Alpha Scorecard

| Sleeve | N Years | Avg ICIR | Avg Hit Rate | Avg Weight | Pos ICIR Years |
|---|---:|---:|---:|---:|---:|
| defensive | 8 | 0.174 | 56.3% | 19.5% | 7/8 |
| reversal | 8 | 0.150 | 55.5% | 16.9% | 8/8 |
| volume_price | 8 | 0.125 | 55.4% | 13.7% | 8/8 |
| momentum | 8 | 0.102 | 54.8% | 11.2% | 8/8 |
| value | 8 | 0.074 | 52.2% | 6.8% | 6/8 |

## 6. Construction Loss Bridge

| Year | Strategy | Gross Excess | Net Excess | Cost Drag | Avg Turnover | Avg Cost bps |
|---:|---|---:|---:|---:|---:|---:|
| 2017 | A_5reversal | -18.7% | -23.3% | 4.6% | 44.1% | 8.9 |
| 2017 | B_dynamic | -21.2% | -25.4% | 4.3% | 42.1% | 8.5 |
| 2017 | C_regime_baseline | -17.6% | -21.8% | 4.2% | 39.6% | 8.0 |
| 2017 | D_regime_overlay | -17.3% | -21.4% | 4.1% | 38.5% | 7.8 |
| 2017 | E_shock_reversal | -21.7% | -25.8% | 4.1% | 39.8% | 8.1 |
| 2018 | A_5reversal | -7.4% | -11.1% | 3.6% | 52.7% | 10.7 |
| 2018 | B_dynamic | -6.8% | -10.1% | 3.3% | 47.1% | 9.6 |
| 2018 | C_regime_baseline | -10.2% | -12.8% | 2.7% | 40.1% | 8.1 |
| 2018 | D_regime_overlay | -9.5% | -12.2% | 2.7% | 40.8% | 8.3 |
| 2018 | E_shock_reversal | -5.0% | -7.8% | 2.8% | 40.9% | 8.3 |
| 2019 | A_5reversal | -4.4% | -10.0% | 5.6% | 46.1% | 9.4 |
| 2019 | B_dynamic | -0.5% | -5.8% | 5.4% | 43.1% | 8.7 |
| 2019 | C_regime_baseline | -11.8% | -17.1% | 5.3% | 42.0% | 8.5 |
| 2019 | D_regime_overlay | -11.3% | -16.6% | 5.3% | 41.7% | 8.5 |
| 2019 | E_shock_reversal | -9.0% | -14.4% | 5.4% | 41.4% | 8.4 |
| 2020 | A_5reversal | -20.4% | -26.9% | 6.5% | 56.8% | 11.5 |
| 2020 | B_dynamic | -14.2% | -20.0% | 5.8% | 47.9% | 9.7 |
| 2020 | C_regime_baseline | -6.8% | -12.1% | 5.4% | 43.4% | 8.8 |
| 2020 | D_regime_overlay | -2.0% | -7.3% | 5.2% | 40.7% | 8.2 |
| 2020 | E_shock_reversal | -13.5% | -18.6% | 5.1% | 43.6% | 8.8 |
| 2021 | A_5reversal | -5.5% | -9.3% | 3.7% | 46.5% | 9.4 |
| 2021 | B_dynamic | -22.6% | -25.5% | 2.9% | 45.7% | 9.2 |
| 2021 | C_regime_baseline | -1.9% | -6.0% | 4.1% | 45.3% | 9.2 |
| 2021 | D_regime_overlay | -2.5% | -6.6% | 4.1% | 45.0% | 9.1 |
| 2021 | E_shock_reversal | -4.6% | -8.5% | 3.9% | 44.4% | 9.0 |
| 2022 | A_5reversal | 7.8% | 3.3% | 4.5% | 49.4% | 10.0 |
| 2022 | B_dynamic | 4.6% | 0.4% | 4.1% | 47.0% | 9.5 |
| 2022 | C_regime_baseline | 10.8% | 7.0% | 3.7% | 40.2% | 8.1 |
| 2022 | D_regime_overlay | 12.0% | 8.3% | 3.6% | 38.6% | 7.8 |
| 2022 | E_shock_reversal | 10.9% | 7.2% | 3.7% | 39.8% | 8.1 |
| 2023 | A_5reversal | 4.7% | 0.7% | 4.0% | 46.0% | 9.3 |
| 2023 | B_dynamic | 3.1% | -0.3% | 3.4% | 39.8% | 8.1 |
| 2023 | C_regime_baseline | -1.9% | -5.3% | 3.4% | 39.7% | 8.0 |
| 2023 | D_regime_overlay | 1.4% | -1.5% | 2.8% | 31.8% | 6.4 |
| 2023 | E_shock_reversal | -3.8% | -7.2% | 3.3% | 39.8% | 8.1 |
| 2024 | A_5reversal | -8.9% | -13.4% | 4.6% | 40.5% | 8.2 |
| 2024 | B_dynamic | -3.6% | -8.7% | 5.0% | 41.3% | 8.4 |
| 2024 | C_regime_baseline | 7.1% | 2.5% | 4.6% | 35.0% | 7.1 |
| 2024 | D_regime_overlay | 9.3% | 4.9% | 4.4% | 32.8% | 6.6 |
| 2024 | E_shock_reversal | 9.8% | 4.9% | 4.9% | 36.1% | 7.3 |

- Gross excess positive rate: 27.5%
- Net excess positive rate: 22.5%
- ⚠️ Alpha does not exist even pre-cost. Factor pool is the root problem.

### Pre-Cost vs Post-Cost Detail

| Year | Strategy | Pre-Cost Excess | Post-Cost Excess | Cost Drag | Data Source |
|---:|---|---:|---:|---:|
| 2017 | A_5reversal | -18.7% | -23.3% | 4.6% | phase2_portfolio_values.parquet (gross_period_return) |
| 2017 | B_dynamic | -21.2% | -25.4% | 4.3% | phase2_portfolio_values.parquet (gross_period_return) |
| 2017 | C_regime_baseline | -17.6% | -21.8% | 4.2% | phase2_portfolio_values.parquet (gross_period_return) |
| 2017 | D_regime_overlay | -17.3% | -21.4% | 4.1% | phase2_portfolio_values.parquet (gross_period_return) |
| 2017 | E_shock_reversal | -21.7% | -25.8% | 4.1% | phase2_portfolio_values.parquet (gross_period_return) |
| 2018 | A_5reversal | -7.4% | -11.1% | 3.6% | phase2_portfolio_values.parquet (gross_period_return) |
| 2018 | B_dynamic | -6.8% | -10.1% | 3.3% | phase2_portfolio_values.parquet (gross_period_return) |
| 2018 | C_regime_baseline | -10.2% | -12.8% | 2.7% | phase2_portfolio_values.parquet (gross_period_return) |
| 2018 | D_regime_overlay | -9.5% | -12.2% | 2.7% | phase2_portfolio_values.parquet (gross_period_return) |
| 2018 | E_shock_reversal | -5.0% | -7.8% | 2.8% | phase2_portfolio_values.parquet (gross_period_return) |
| 2019 | A_5reversal | -4.4% | -10.0% | 5.6% | phase2_portfolio_values.parquet (gross_period_return) |
| 2019 | B_dynamic | -0.5% | -5.8% | 5.4% | phase2_portfolio_values.parquet (gross_period_return) |
| 2019 | C_regime_baseline | -11.8% | -17.1% | 5.3% | phase2_portfolio_values.parquet (gross_period_return) |
| 2019 | D_regime_overlay | -11.3% | -16.6% | 5.3% | phase2_portfolio_values.parquet (gross_period_return) |
| 2019 | E_shock_reversal | -9.0% | -14.4% | 5.4% | phase2_portfolio_values.parquet (gross_period_return) |
| 2020 | A_5reversal | -20.4% | -26.9% | 6.5% | phase2_portfolio_values.parquet (gross_period_return) |
| 2020 | B_dynamic | -14.2% | -20.0% | 5.8% | phase2_portfolio_values.parquet (gross_period_return) |
| 2020 | C_regime_baseline | -6.8% | -12.1% | 5.4% | phase2_portfolio_values.parquet (gross_period_return) |
| 2020 | D_regime_overlay | -2.0% | -7.3% | 5.2% | phase2_portfolio_values.parquet (gross_period_return) |
| 2020 | E_shock_reversal | -13.5% | -18.6% | 5.1% | phase2_portfolio_values.parquet (gross_period_return) |
| 2021 | A_5reversal | -5.5% | -9.3% | 3.7% | phase2_portfolio_values.parquet (gross_period_return) |
| 2021 | B_dynamic | -22.6% | -25.5% | 2.9% | phase2_portfolio_values.parquet (gross_period_return) |
| 2021 | C_regime_baseline | -1.9% | -6.0% | 4.1% | phase2_portfolio_values.parquet (gross_period_return) |
| 2021 | D_regime_overlay | -2.5% | -6.6% | 4.1% | phase2_portfolio_values.parquet (gross_period_return) |
| 2021 | E_shock_reversal | -4.6% | -8.5% | 3.9% | phase2_portfolio_values.parquet (gross_period_return) |
| 2022 | A_5reversal | 7.8% | 3.3% | 4.5% | phase2_portfolio_values.parquet (gross_period_return) |
| 2022 | B_dynamic | 4.6% | 0.4% | 4.1% | phase2_portfolio_values.parquet (gross_period_return) |
| 2022 | C_regime_baseline | 10.8% | 7.0% | 3.7% | phase2_portfolio_values.parquet (gross_period_return) |
| 2022 | D_regime_overlay | 12.0% | 8.3% | 3.6% | phase2_portfolio_values.parquet (gross_period_return) |
| 2022 | E_shock_reversal | 10.9% | 7.2% | 3.7% | phase2_portfolio_values.parquet (gross_period_return) |
| 2023 | A_5reversal | 4.7% | 0.7% | 4.0% | phase2_portfolio_values.parquet (gross_period_return) |
| 2023 | B_dynamic | 3.1% | -0.3% | 3.4% | phase2_portfolio_values.parquet (gross_period_return) |
| 2023 | C_regime_baseline | -1.9% | -5.3% | 3.4% | phase2_portfolio_values.parquet (gross_period_return) |
| 2023 | D_regime_overlay | 1.4% | -1.5% | 2.8% | phase2_portfolio_values.parquet (gross_period_return) |
| 2023 | E_shock_reversal | -3.8% | -7.2% | 3.3% | phase2_portfolio_values.parquet (gross_period_return) |
| 2024 | A_5reversal | -8.9% | -13.4% | 4.6% | phase2_portfolio_values.parquet (gross_period_return) |
| 2024 | B_dynamic | -3.6% | -8.7% | 5.0% | phase2_portfolio_values.parquet (gross_period_return) |
| 2024 | C_regime_baseline | 7.1% | 2.5% | 4.6% | phase2_portfolio_values.parquet (gross_period_return) |
| 2024 | D_regime_overlay | 9.3% | 4.9% | 4.4% | phase2_portfolio_values.parquet (gross_period_return) |
| 2024 | E_shock_reversal | 9.8% | 4.9% | 4.9% | phase2_portfolio_values.parquet (gross_period_return) |

## 7. Regime Router Scorecard

| Year | Strategy | Dominant Regime | Dominant Sleeve | Router Active |
|---:|---|---|---:|
| 2017 | C_regime_baseline | range_bound_prob | reversal_actual_weight | False |
| 2017 | D_regime_overlay | range_bound_prob | volume_price_actual_weight | True |
| 2017 | E_shock_reversal | range_bound_prob | reversal_actual_weight | False |
| 2018 | C_regime_baseline | range_bound_prob | reversal_actual_weight | False |
| 2018 | D_regime_overlay | trend_down_prob | defensive_actual_weight | True |
| 2018 | E_shock_reversal | range_bound_prob | defensive_actual_weight | False |
| 2019 | C_regime_baseline | range_bound_prob | defensive_actual_weight | False |
| 2019 | D_regime_overlay | range_bound_prob | defensive_actual_weight | True |
| 2019 | E_shock_reversal | range_bound_prob | defensive_actual_weight | False |
| 2020 | C_regime_baseline | range_bound_prob | reversal_actual_weight | False |
| 2020 | D_regime_overlay | range_bound_prob | reversal_actual_weight | True |
| 2020 | E_shock_reversal | range_bound_prob | reversal_actual_weight | False |
| 2021 | C_regime_baseline | range_bound_prob | reversal_actual_weight | False |
| 2021 | D_regime_overlay | range_bound_prob | reversal_actual_weight | True |
| 2021 | E_shock_reversal | range_bound_prob | defensive_actual_weight | False |
| 2022 | C_regime_baseline | range_bound_prob | defensive_actual_weight | False |
| 2022 | D_regime_overlay | range_bound_prob | defensive_actual_weight | True |
| 2022 | E_shock_reversal | range_bound_prob | defensive_actual_weight | False |
| 2023 | C_regime_baseline | range_bound_prob | reversal_actual_weight | False |
| 2023 | D_regime_overlay | range_bound_prob | defensive_actual_weight | True |
| 2023 | E_shock_reversal | range_bound_prob | reversal_actual_weight | False |
| 2024 | C_regime_baseline | range_bound_prob | reversal_actual_weight | False |
| 2024 | D_regime_overlay | range_bound_prob | defensive_actual_weight | True |
| 2024 | E_shock_reversal | range_bound_prob | defensive_actual_weight | False |
| 2026 | C_regime_baseline | range_bound_prob | reversal_actual_weight | False |
| 2026 | D_regime_overlay | range_bound_prob | reversal_actual_weight | True |
| 2026 | E_shock_reversal | range_bound_prob | reversal_actual_weight | False |

### Overlay Multiplier Summary
- **reversal**: mean=1.026, range=[0.930, 1.177]
- **momentum**: mean=1.023, range=[0.882, 1.122]
- **defensive**: mean=1.024, range=[0.898, 1.173]
- **value**: mean=1.012, range=[0.910, 1.126]
- **volume_price**: mean=1.052, range=[0.891, 1.163]

## 8. Sleeve Oracle & Opportunity Cost

- Periods with oracle data (status=OK): 1198

### Router Oracle Excluded Rows
- OUT_OF_BACKTEST_WINDOW: 652

### Oracle Sleeve Distribution
| Sleeve | N Periods as Oracle | Pct |
|---|---:|
| reversal | 283 | 23.6% |
| momentum | 276 | 23.0% |
| defensive | 219 | 18.3% |
| value | 318 | 26.5% |
| volume_price | 102 | 8.5% |

- Mean opportunity cost vs oracle: 1.21%
- Mean opportunity cost vs equal-weight: 0.00%
- Dominant sleeve equals oracle: 20.0%

### Overlay Predictiveness
- Sleeves with positive multiplier→return correlation: 0.0%

## 9. Diagnosis Summary

### Root Cause Classification

1. **原始因子无 alpha** — pre-cost gross excess is negative for most years.
2. **Top-bottom 有 alpha 但 long-only 无 alpha** — short side drives returns.
3. **Long-only 有 alpha 但成本吃掉** — gross excess positive, net excess negative.
4. **成本后仍有 alpha 但 regime/router 降低暴露** — net excess positive but regime misallocates.
5. **组合约束导致持仓偏离有效暴露** — constraints prevent alpha from reaching portfolio.

**Diagnosis: 原始因子无 alpha** (mean gross excess=-5.1%)

### Missing or Unavailable Diagnostics

- `rebalance_frequency_diagnostic.csv`: NOT_AVAILABLE (no multi-frequency runs exist)
- `topn_capacity_diagnostic.csv`: NOT_AVAILABLE (no multi-topN runs exist)


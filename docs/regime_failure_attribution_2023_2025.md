# Regime 失败归因：2023 / 2025

数据来源：已有 Phase 2 diagnostics，不重新回测。

## 年度结论

| 年份 | A超额 | B超额 | C超额 | C-A | C-B | 初步判断 |
|---:|---:|---:|---:|---:|---:|---|
| 2023 | 1.0% | -0.2% | -6.6% | -7.6% | -6.4% | C 明显输给 A，router/sleeve 暴露不适配 |
| 2025 | -36.3% | -29.7% | -35.4% | 0.9% | -5.7% | B 最好，C 接近 A 但未捕捉动态因子 |

## 月度相对收益

| 年月 | A | B | C | C-A | C-B | C主导Regime | C主导Sleeve |
|---:|---:|---:|---:|---:|---:|---|---|
| 202301 |  |  | 3.2% |  |  | range_bound_prob | defensive_weight |
| 202302 | -1.1% | -1.5% | -0.8% | 0.3% | 0.8% | range_bound_prob | reversal_weight |
| 202303 | -1.3% | -0.5% | -0.2% | 1.0% | 0.2% | range_bound_prob | reversal_weight |
| 202304 | 1.5% | 0.3% | 0.1% | -1.4% | -0.2% | range_bound_prob | reversal_weight |
| 202305 | -0.1% | -0.1% | -7.1% | -7.0% | -7.1% | range_bound_prob | reversal_weight |
| 202306 | -5.4% | -5.7% | -4.8% | 0.6% | 0.9% | range_bound_prob | reversal_weight |
| 202307 | 6.0% | 6.6% | 7.3% | 1.3% | 0.7% | range_bound_prob | reversal_weight |
| 202308 | -6.3% | -6.5% | -4.8% | 1.4% | 1.7% | range_bound_prob | reversal_weight |
| 202309 | -1.0% | -0.9% | -1.6% | -0.6% | -0.7% | range_bound_prob | reversal_weight |
| 202310 | -5.3% | -3.5% | -5.9% | -0.6% | -2.4% | range_bound_prob | defensive_weight |
| 202311 | -1.8% | -1.4% | -1.8% | 0.0% | -0.4% | trend_down_prob | defensive_weight |
| 202312 | -3.5% | -5.7% | -5.4% | -1.9% | 0.3% | trend_down_prob | defensive_weight |
| 202501 |  |  | 1.5% |  |  | range_bound_prob | reversal_weight |
| 202502 |  |  | 2.6% |  |  | range_bound_prob | reversal_weight |
| 202503 | -3.0% |  | 1.4% | 4.4% |  | range_bound_prob | reversal_weight |
| 202504 | -0.7% | 5.1% | 1.1% | 1.8% | -4.1% | range_bound_prob | volume_price_weight |
| 202505 | 0.8% | 0.4% | 1.9% | 1.1% | 1.4% | range_bound_prob |  |
| 202506 | -0.7% | -0.7% | 0.2% | 0.9% | 0.9% | range_bound_prob | reversal_weight |
| 202507 | 2.0% | 4.5% | 3.0% | 0.9% | -1.5% | range_bound_prob | reversal_weight |
| 202508 | 3.5% | 1.6% | -0.3% | -3.8% | -1.8% | range_bound_prob | reversal_weight |
| 202509 | -1.0% | 1.0% | -2.8% | -1.8% | -3.8% | trend_up_prob | volume_price_weight |
| 202510 | -3.1% | 0.6% | -2.9% | 0.2% | -3.5% | trend_up_prob | momentum_weight |
| 202511 | -8.7% | -10.3% | -7.8% | 0.9% | 2.5% | trend_up_prob | reversal_weight |
| 202512 | 0.4% | 2.1% | -0.2% | -0.6% | -2.3% | range_bound_prob | reversal_weight |

## C Regime 平均配置

| 年份 | 主导Regime均值最高 | 主导Sleeve均值最高 | reversal | momentum | defensive | value | volume_price |
|---:|---|---|---:|---:|---:|---:|---:|
| 2023 | range_bound_prob 46.2% | reversal_weight 30.9% | 30.9% | 7.7% | 27.5% | 15.8% | 18.1% |
| 2025 | range_bound_prob 40.9% | reversal_weight 31.0% | 31.0% | 14.0% | 13.6% | 18.3% | 23.1% |

## 持仓重合度

| 年份 | 对比 | C持仓重合率 | Jaccard |
|---:|---|---:|---:|
| 2023 | A 固定5反转 | 48.7% | 34.1% |
| 2023 | B 动态IC | 51.4% | 36.3% |
| 2025 | A 固定5反转 | 40.2% | 27.2% |
| 2025 | B 动态IC | 49.4% | 35.2% |

## C Regime 年度近似贡献 Top/Bottom

说明：个股贡献按 `期初权重 × 持有期个股收益` 近似估算，仅用于定位暴露来源；跨自然年持有期已排除，避免旧缓存复权基准不连续造成虚假贡献。

### 2023

Top contributors:

| 股票 | 贡献 | 平均权重 | 持有期数 |
|---|---:|---:|---:|
| 600383.SH | 0.6% | 2.0% | 11 |
| 600436.SH | 0.4% | 2.0% | 8 |
| 601021.SH | 0.4% | 2.0% | 5 |
| 603986.SH | 0.4% | 2.0% | 4 |
| 300223.SZ | 0.3% | 2.0% | 3 |
| 600029.SH | 0.3% | 2.0% | 10 |
| 002050.SZ | 0.3% | 2.0% | 3 |
| 600050.SH | 0.3% | 2.0% | 7 |

Bottom contributors:

| 股票 | 贡献 | 平均权重 | 持有期数 |
|---|---:|---:|---:|
| 300316.SZ | -0.8% | 2.0% | 12 |
| 600089.SH | -0.7% | 2.0% | 9 |
| 601009.SH | -0.7% | 2.0% | 36 |
| 603659.SH | -0.6% | 2.0% | 10 |
| 601838.SH | -0.5% | 2.0% | 25 |
| 601618.SH | -0.5% | 2.0% | 21 |
| 600926.SH | -0.5% | 2.0% | 31 |
| 000002.SZ | -0.5% | 2.0% | 19 |

### 2025

Top contributors:

| 股票 | 贡献 | 平均权重 | 持有期数 |
|---|---:|---:|---:|
| 002709.SZ | 1.0% | 2.0% | 8 |
| 600362.SH | 0.7% | 2.0% | 8 |
| 300442.SZ | 0.7% | 2.0% | 7 |
| 600089.SH | 0.6% | 2.0% | 14 |
| 601877.SH | 0.6% | 2.0% | 11 |
| 600489.SH | 0.6% | 2.0% | 5 |
| 603993.SH | 0.6% | 2.0% | 3 |
| 601100.SH | 0.5% | 2.0% | 6 |

Bottom contributors:

| 股票 | 贡献 | 平均权重 | 持有期数 |
|---|---:|---:|---:|
| 002594.SZ | -1.6% | 2.0% | 9 |
| 688036.SH | -0.7% | 2.0% | 12 |
| 603019.SH | -0.4% | 2.0% | 11 |
| 601360.SH | -0.4% | 2.0% | 4 |
| 600760.SH | -0.4% | 2.0% | 10 |
| 688981.SH | -0.4% | 2.0% | 10 |
| 300394.SZ | -0.4% | 2.0% | 5 |
| 002475.SZ | -0.4% | 2.0% | 8 |

## 诊断判断

1. 2023 不是简单的“动态不够”，因为 B 也没有优于 A；C 的问题更像是 router 将组合持续推向了不占优的 sleeve 暴露。
2. 2025 B 明显优于 A/C，说明全因子动态 IC 在该年比显式 regime router 更灵敏；C 的 sleeve 映射和权重平滑可能压慢了切换。
3. C 在两个年份的主导概率仍偏 `range_bound_prob`，平均最高 sleeve 仍偏 `reversal_weight`，这和“不同市场趋势使用不同策略”的目标还有距离。
4. 下一步参数网格应优先测试：降低 range_bound→reversal 权重、提高 trend/value 对 momentum/value sleeve 的穿透、放宽每周权重变化约束。

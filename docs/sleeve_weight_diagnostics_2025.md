# Sleeve 内部权重诊断：2025 Overlay

## 边界

- 固定使用已有 `less_reversal_faster_overlay` 回测配置。
- 只重算 sleeve 内部 IC 权重和选股暴露，不搜索参数、不改配置。
- 权重使用 `matured_ic_cutoff()`，只看 forward return 已成熟的历史 IC。
- 2025 结果只用于诊断，不作为直接调参或反向因子的依据。

## 样本

- Window: `20250101-20251224`
- Data window: `20240601-20251224`
- Target signal dates: 52
- Scoring signal dates: 82

## Sleeve 内部因子权重

| Sleeve | Factor | 活跃率 | 平均权重 | 平均绝对权重 | 正权重率 | 负权重率 | 平均ICIR | ICIR低于门槛率 | 方向不稳率 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| defensive | volatility_20_cs | 90.4% | 0.268 | 0.420 | 69.2% | 21.2% | 0.131 | 7.7% | 51.9% |
| defensive | volatility_60_cs | 92.3% | -0.047 | 0.386 | 48.1% | 44.2% | 0.001 | 5.8% | 48.1% |
| defensive | reversal_20_cs | 50.0% | 0.063 | 0.117 | 38.5% | 11.5% | 0.027 | 48.1% | 44.2% |
| momentum | momentum_60_cs | 82.7% | -0.287 | 0.307 | 5.8% | 76.9% | -0.140 | 15.4% | 36.5% |
| momentum | pv_divergence_20_cs | 71.2% | 0.116 | 0.297 | 46.2% | 25.0% | 0.085 | 25.0% | 40.4% |
| momentum | macd_12_26_9_cs | 73.1% | 0.054 | 0.236 | 40.4% | 32.7% | 0.036 | 26.9% | 38.5% |
| momentum | momentum_120_cs | 34.6% | -0.045 | 0.102 | 13.5% | 21.2% | -0.047 | 25.0% | 19.2% |
| reversal | reversal_5_cs | 76.9% | 0.302 | 0.337 | 67.3% | 9.6% | 0.175 | 17.3% | 32.7% |
| reversal | pv_divergence_20_cs | 75.0% | 0.163 | 0.298 | 50.0% | 25.0% | 0.085 | 25.0% | 40.4% |
| reversal | rsi_14_cs | 65.4% | -0.127 | 0.179 | 19.2% | 46.2% | -0.064 | 30.8% | 26.9% |
| reversal | reversal_20_cs | 51.9% | 0.056 | 0.090 | 40.4% | 11.5% | 0.027 | 48.1% | 44.2% |
| value | bp_cs | 75.0% | 0.297 | 0.345 | 71.2% | 3.8% | 0.139 | 23.1% | 23.1% |
| value | ep_cs | 82.7% | 0.286 | 0.321 | 76.9% | 5.8% | 0.118 | 17.3% | 17.3% |
| value | sp_cs | 57.7% | 0.056 | 0.199 | 36.5% | 21.2% | 0.011 | 34.6% | 32.7% |
| volume_price | momentum_60_cs | 84.6% | -0.281 | 0.295 | 5.8% | 78.8% | -0.140 | 15.4% | 36.5% |
| volume_price | volatility_20_cs | 92.3% | 0.180 | 0.283 | 71.2% | 21.2% | 0.131 | 7.7% | 51.9% |
| volume_price | pv_divergence_20_cs | 75.0% | 0.090 | 0.223 | 50.0% | 25.0% | 0.085 | 25.0% | 40.4% |
| volume_price | macd_12_26_9_cs | 73.1% | 0.017 | 0.199 | 40.4% | 32.7% | 0.036 | 26.9% | 38.5% |

## Top50 选股暴露

| Sleeve | Factor | 平均选中暴露 | 相对全域暴露 | 正暴露率 | 平均有效持仓数 |
|---|---|---:|---:|---:|---:|
| defensive | reversal_20_cs | 0.084 | 0.084 | 62.5% | 50.0 |
| defensive | volatility_20_cs | 0.032 | 0.032 | 54.2% | 50.0 |
| defensive | volatility_60_cs | -0.111 | -0.110 | 54.2% | 50.0 |
| momentum | pv_divergence_20_cs | 0.310 | 0.310 | 61.2% | 50.0 |
| momentum | macd_12_26_9_cs | 0.182 | 0.182 | 57.1% | 50.0 |
| momentum | momentum_120_cs | -0.134 | -0.134 | 38.1% | 49.8 |
| momentum | momentum_60_cs | -0.468 | -0.469 | 20.4% | 50.0 |
| reversal | reversal_5_cs | 0.619 | 0.619 | 76.6% | 50.0 |
| reversal | pv_divergence_20_cs | 0.494 | 0.494 | 68.1% | 50.0 |
| reversal | reversal_20_cs | 0.218 | 0.218 | 68.1% | 50.0 |
| reversal | rsi_14_cs | 0.151 | 0.151 | 63.8% | 50.0 |
| value | bp_cs | 1.393 | 1.390 | 91.1% | 50.0 |
| value | ep_cs | 1.288 | 1.295 | 91.1% | 50.0 |
| value | sp_cs | 0.650 | 0.652 | 86.7% | 50.0 |
| volume_price | volatility_20_cs | 0.386 | 0.386 | 82.7% | 50.0 |
| volume_price | pv_divergence_20_cs | 0.350 | 0.350 | 61.5% | 50.0 |
| volume_price | macd_12_26_9_cs | 0.137 | 0.137 | 59.6% | 50.0 |
| volume_price | momentum_60_cs | -0.369 | -0.369 | 36.5% | 50.0 |

## Phase1 与 Aligned IC 口径对照

这里专门核对 value 因子的矛盾：旧 Phase1 日志是直接用当期因子面板与 `fwd_ret_5d` 做全样本日频/原始面板评估；regime 诊断使用 weekly as-of aligned 因子、coverage gate、warmup 后的 2025 信号日。

| Factor | Phase1 Mean IC | Phase1 ICIR | Phase1正IC率 | Aligned Mean IC | Aligned ICIR | Aligned正IC率 | Top-Bottom超额 |
|---|---:|---:|---:|---:|---:|---:|---:|
| bp_cs | 0.087 | 0.424 | 63.6% | 0.006 | 0.024 | 48.1% | -26.7% |
| ep_cs | 0.107 | 0.486 | 63.6% | 0.009 | 0.036 | 48.1% | -15.5% |
| momentum_120_cs | 0.015 | 0.068 | 49.5% | 0.017 | 0.102 | 46.7% | 16.8% |
| momentum_60_cs | -0.009 | -0.043 | 54.0% | 0.006 | 0.028 | 65.4% | 25.0% |
| sp_cs | 0.078 | 0.469 | 63.6% | 0.005 | 0.031 | 48.1% | -16.5% |

## 诊断判断

- 单因子层面最值得关注的是 `momentum_60_cs`，Top-Bottom 年化超额 25.0%。
- 在 momentum sleeve 内，`momentum_60_cs` 平均权重 -0.287，活跃率 82.7%，平均 ICIR -0.140。
- value sleeve 中绝对权重最高的是 `bp_cs`，平均权重 0.297，但这只说明历史滚动 IC 权重如何下注，不等于 2025 Top50 经济收益有效。
- 结论仍保持保守：先解释权重和口径差异，再决定是否做跨年份 OOS 假设检验。

## 下一步验证方案

先把 2025 诊断转成冻结假设，再跨年份验证，避免用失败年份直接调参：

1. **H1：momentum sleeve 失败来自内部权重方向错配。** `momentum_60_cs` raw Top50 有效，但当前滚动 IC 权重多数时间给负权重；下一步只验证这个现象在 2017-2024 和 2026 YTD 是否反复出现。
2. **H2：value 因子的 Phase1 强 IC 不等于 weekly aligned Top50 alpha。** 先复现 Phase1 与 aligned 两套口径的差异来源，再决定 value sleeve 是否需要改造。
3. **H3：不要基于 2025 单年反向因子。** 任何方向约束、窗口调整、因子剔除都必须先写成固定候选配置，再用未参与设计的年份验证。

建议的下一批只读验证：

- 将本脚本扩展到 `2017-2024` 和 `2026 YTD`，输出同样的 weight/exposure/reconciliation 表。
- 对每一年检查 `momentum_60_cs` 的 raw Top-Bottom 与 sleeve 内平均权重方向是否一致。
- 对 value 因子检查 Phase1 原始面板 IC、weekly aligned IC、Top50 经济收益三者是否稳定同向。
- 只有当错配跨多年成立，才进入候选策略开发；否则继续停留在诊断层。

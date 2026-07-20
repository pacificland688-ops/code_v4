# Sleeve 内部权重诊断：20170101-20171231

## 边界

- 固定使用配置 `outputs\analysis\regime_grid_overlay_phase2_2025\configs\less_reversal_faster_overlay.yaml`。
- 只重算 sleeve 内部 IC 权重和选股暴露，不搜索参数、不改配置。
- 权重使用 `matured_ic_cutoff()`，只看 forward return 已成熟的历史 IC。
- 当前窗口结果只用于诊断，不作为直接调参或反向因子的依据。

## 样本

- Window: `20170101-20171231`
- Data window: `20160601-20171231`
- Target signal dates: 51
- Scoring signal dates: 81

## Sleeve 内部因子权重

| Sleeve | Factor | 活跃率 | 平均权重 | 平均绝对权重 | 正权重率 | 负权重率 | 平均ICIR | ICIR低于门槛率 | 方向不稳率 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| defensive | volatility_60_cs | 100.0% | 0.436 | 0.436 | 100.0% | 0.0% | 0.424 | 0.0% | 23.5% |
| defensive | volatility_20_cs | 92.2% | 0.422 | 0.422 | 92.2% | 0.0% | 0.429 | 7.8% | 29.4% |
| defensive | reversal_20_cs | 68.6% | -0.012 | 0.141 | 39.2% | 29.4% | 0.036 | 31.4% | 31.4% |
| momentum | pv_divergence_20_cs | 100.0% | 0.549 | 0.549 | 100.0% | 0.0% | 0.500 | 0.0% | 7.8% |
| momentum | macd_12_26_9_cs | 90.2% | -0.195 | 0.195 | 0.0% | 90.2% | -0.197 | 9.8% | 39.2% |
| momentum | momentum_60_cs | 86.3% | 0.104 | 0.188 | 64.7% | 21.6% | 0.132 | 13.7% | 33.3% |
| momentum | momentum_120_cs | 43.1% | 0.062 | 0.068 | 39.2% | 3.9% | 0.134 | 13.7% | 27.5% |
| reversal | pv_divergence_20_cs | 94.1% | 0.552 | 0.552 | 94.1% | 0.0% | 0.500 | 0.0% | 7.8% |
| reversal | reversal_5_cs | 90.2% | 0.206 | 0.206 | 90.2% | 0.0% | 0.223 | 9.8% | 37.3% |
| reversal | reversal_20_cs | 68.6% | 0.018 | 0.103 | 39.2% | 29.4% | 0.036 | 31.4% | 31.4% |
| reversal | rsi_14_cs | 64.7% | 0.065 | 0.081 | 56.9% | 7.8% | 0.082 | 35.3% | 41.2% |
| value | sp_cs | 84.3% | 0.275 | 0.314 | 78.4% | 5.9% | 0.312 | 5.9% | 35.3% |
| value | bp_cs | 78.4% | 0.017 | 0.294 | 47.1% | 31.4% | 0.244 | 21.6% | 33.3% |
| value | ep_cs | 82.4% | 0.155 | 0.294 | 58.8% | 23.5% | 0.245 | 17.6% | 23.5% |
| volume_price | pv_divergence_20_cs | 100.0% | 0.427 | 0.427 | 100.0% | 0.0% | 0.500 | 0.0% | 7.8% |
| volume_price | volatility_20_cs | 92.2% | 0.288 | 0.288 | 92.2% | 0.0% | 0.429 | 7.8% | 29.4% |
| volume_price | macd_12_26_9_cs | 90.2% | -0.143 | 0.143 | 0.0% | 90.2% | -0.197 | 9.8% | 39.2% |
| volume_price | momentum_60_cs | 86.3% | 0.059 | 0.142 | 64.7% | 21.6% | 0.132 | 13.7% | 33.3% |

## Top50 选股暴露

| Sleeve | Factor | 平均选中暴露 | 相对全域暴露 | 正暴露率 | 平均有效持仓数 |
|---|---|---:|---:|---:|---:|
| defensive | volatility_60_cs | 1.077 | 1.079 | 98.0% | 50.0 |
| defensive | volatility_20_cs | 1.039 | 1.041 | 96.1% | 50.0 |
| defensive | reversal_20_cs | 0.017 | 0.016 | 55.1% | 50.0 |
| momentum | pv_divergence_20_cs | 1.474 | 1.474 | 100.0% | 49.9 |
| momentum | momentum_120_cs | 0.525 | 0.526 | 86.7% | 45.3 |
| momentum | momentum_60_cs | 0.515 | 0.516 | 85.7% | 47.3 |
| momentum | macd_12_26_9_cs | -0.743 | -0.743 | 2.0% | 49.8 |
| reversal | pv_divergence_20_cs | 1.582 | 1.582 | 100.0% | 50.0 |
| reversal | reversal_20_cs | 0.962 | 0.962 | 100.0% | 49.7 |
| reversal | rsi_14_cs | 0.894 | 0.894 | 100.0% | 49.9 |
| reversal | reversal_5_cs | 0.680 | 0.681 | 100.0% | 50.0 |
| value | sp_cs | 0.936 | 0.935 | 82.6% | 50.0 |
| value | bp_cs | 0.643 | 0.635 | 78.3% | 50.0 |
| value | ep_cs | 0.580 | 0.580 | 73.9% | 50.0 |
| volume_price | pv_divergence_20_cs | 1.345 | 1.345 | 100.0% | 50.0 |
| volume_price | volatility_20_cs | 0.475 | 0.477 | 90.2% | 50.0 |
| volume_price | momentum_60_cs | 0.217 | 0.218 | 67.3% | 48.1 |
| volume_price | macd_12_26_9_cs | -0.499 | -0.499 | 4.1% | 49.6 |

## Phase1 与 Aligned IC 口径对照

这里专门核对 value 因子的矛盾：旧 Phase1 日志是直接用当期因子面板与 `fwd_ret_5d` 做全样本日频/原始面板评估；regime 诊断使用 weekly as-of aligned 因子、coverage gate、warmup 后的目标信号日。

| Factor | Phase1 Mean IC | Phase1 ICIR | Phase1正IC率 | Aligned Mean IC | Aligned ICIR | Aligned正IC率 | Top-Bottom超额 |
|---|---:|---:|---:|---:|---:|---:|---:|
| bp_cs |  |  |  | -0.015 | -0.086 | 40.0% | -2.7% |
| ep_cs |  |  |  | 0.003 | 0.019 | 58.0% | -4.2% |
| momentum_120_cs |  |  |  | 0.057 | 0.322 | 65.9% | 26.3% |
| momentum_60_cs |  |  |  | 0.027 | 0.147 | 62.5% | 14.6% |
| sp_cs |  |  |  | 0.023 | 0.208 | 62.0% | 0.1% |

## 诊断判断

- 单因子层面最值得关注的是 `momentum_120_cs`，Top-Bottom 年化超额 26.3%。
- 在 momentum sleeve 内，`momentum_60_cs` 平均权重 0.104，活跃率 86.3%，平均 ICIR 0.132。
- value sleeve 中绝对权重最高的是 `sp_cs`，平均权重 0.275，但这只说明历史滚动 IC 权重如何下注，不等于当前窗口 Top50 经济收益有效。
- 结论仍保持保守：先解释权重和口径差异，再决定是否做跨年份 OOS 假设检验。

## 下一步验证方案

先把单窗口诊断转成冻结假设，再跨年份验证，避免用失败年份直接调参：

1. **H1：momentum sleeve 失败来自内部权重方向错配。** `momentum_60_cs` raw Top50 有效，但当前滚动 IC 权重多数时间给负权重；下一步只验证这个现象是否跨年份反复出现。
2. **H2：value 因子的 Phase1 强 IC 不等于 weekly aligned Top50 alpha。** 先复现 Phase1 与 aligned 两套口径的差异来源，再决定 value sleeve 是否需要改造。
3. **H3：不要基于 2025 单年反向因子。** 任何方向约束、窗口调整、因子剔除都必须先写成固定候选配置，再用未参与设计的年份验证。

建议的下一批只读验证：

- 将本脚本扩展到 `2017-2024` 和 `2026 YTD`，输出同样的 weight/exposure/reconciliation 表。
- 对每一年检查 `momentum_60_cs` 的 raw Top-Bottom 与 sleeve 内平均权重方向是否一致。
- 对 value 因子检查 Phase1 原始面板 IC、weekly aligned IC、Top50 经济收益三者是否稳定同向。
- 只有当错配跨多年成立，才进入候选策略开发；否则继续停留在诊断层。

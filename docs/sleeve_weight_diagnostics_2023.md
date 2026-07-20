# Sleeve 内部权重诊断：20230101-20231222

## 边界

- 固定使用配置 `outputs\analysis\regime_grid_overlay_phase2_2025\configs\less_reversal_faster_overlay.yaml`。
- 只重算 sleeve 内部 IC 权重和选股暴露，不搜索参数、不改配置。
- 权重使用 `matured_ic_cutoff()`，只看 forward return 已成熟的历史 IC。
- 当前窗口结果只用于诊断，不作为直接调参或反向因子的依据。

## 样本

- Window: `20230101-20231222`
- Data window: `20220601-20231222`
- Target signal dates: 49
- Scoring signal dates: 79

## Sleeve 内部因子权重

| Sleeve | Factor | 活跃率 | 平均权重 | 平均绝对权重 | 正权重率 | 负权重率 | 平均ICIR | ICIR低于门槛率 | 方向不稳率 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| defensive | volatility_60_cs | 100.0% | 0.408 | 0.408 | 100.0% | 0.0% | 0.457 | 0.0% | 18.4% |
| defensive | volatility_20_cs | 100.0% | 0.404 | 0.404 | 100.0% | 0.0% | 0.453 | 0.0% | 16.3% |
| defensive | reversal_20_cs | 89.8% | 0.185 | 0.188 | 87.8% | 2.0% | 0.217 | 10.2% | 38.8% |
| momentum | macd_12_26_9_cs | 85.7% | -0.230 | 0.342 | 12.2% | 73.5% | -0.170 | 12.2% | 20.4% |
| momentum | pv_divergence_20_cs | 83.7% | 0.281 | 0.281 | 83.7% | 0.0% | 0.159 | 12.2% | 32.7% |
| momentum | momentum_60_cs | 67.3% | 0.040 | 0.167 | 42.9% | 24.5% | 0.016 | 22.4% | 46.9% |
| momentum | momentum_120_cs | 55.1% | 0.086 | 0.108 | 44.9% | 10.2% | 0.120 | 0.0% | 22.4% |
| reversal | reversal_20_cs | 89.8% | 0.358 | 0.365 | 87.8% | 2.0% | 0.217 | 10.2% | 38.8% |
| reversal | pv_divergence_20_cs | 87.8% | 0.259 | 0.259 | 87.8% | 0.0% | 0.159 | 12.2% | 32.7% |
| reversal | reversal_5_cs | 73.5% | -0.136 | 0.188 | 16.3% | 57.1% | -0.057 | 26.5% | 36.7% |
| reversal | rsi_14_cs | 79.6% | 0.042 | 0.188 | 55.1% | 24.5% | 0.064 | 20.4% | 40.8% |
| value | bp_cs | 100.0% | 0.394 | 0.394 | 100.0% | 0.0% | 0.316 | 0.0% | 28.6% |
| value | ep_cs | 100.0% | 0.336 | 0.336 | 100.0% | 0.0% | 0.284 | 0.0% | 32.7% |
| value | sp_cs | 93.9% | 0.269 | 0.269 | 93.9% | 0.0% | 0.252 | 6.1% | 38.8% |
| volume_price | volatility_20_cs | 98.0% | 0.519 | 0.519 | 98.0% | 0.0% | 0.453 | 0.0% | 16.3% |
| volume_price | macd_12_26_9_cs | 87.8% | -0.167 | 0.208 | 14.3% | 73.5% | -0.170 | 12.2% | 20.4% |
| volume_price | pv_divergence_20_cs | 87.8% | 0.158 | 0.158 | 87.8% | 0.0% | 0.159 | 12.2% | 32.7% |
| volume_price | momentum_60_cs | 69.4% | 0.023 | 0.094 | 44.9% | 24.5% | 0.016 | 22.4% | 46.9% |

## Top50 选股暴露

| Sleeve | Factor | 平均选中暴露 | 相对全域暴露 | 正暴露率 | 平均有效持仓数 |
|---|---|---:|---:|---:|---:|
| defensive | volatility_60_cs | 1.183 | 1.183 | 100.0% | 50.0 |
| defensive | volatility_20_cs | 1.114 | 1.114 | 100.0% | 50.0 |
| defensive | reversal_20_cs | 0.153 | 0.154 | 72.3% | 50.0 |
| momentum | pv_divergence_20_cs | 0.929 | 0.929 | 93.2% | 49.9 |
| momentum | momentum_120_cs | 0.503 | 0.503 | 79.5% | 48.1 |
| momentum | momentum_60_cs | 0.383 | 0.383 | 71.4% | 48.9 |
| momentum | macd_12_26_9_cs | -0.735 | -0.735 | 14.3% | 49.9 |
| reversal | pv_divergence_20_cs | 1.008 | 1.008 | 87.8% | 50.0 |
| reversal | reversal_20_cs | 0.836 | 0.837 | 78.7% | 50.0 |
| reversal | rsi_14_cs | 0.622 | 0.622 | 77.1% | 50.0 |
| reversal | reversal_5_cs | 0.117 | 0.117 | 65.3% | 50.0 |
| value | bp_cs | 1.711 | 1.707 | 100.0% | 50.0 |
| value | ep_cs | 1.543 | 1.542 | 100.0% | 50.0 |
| value | sp_cs | 1.235 | 1.235 | 100.0% | 50.0 |
| volume_price | volatility_20_cs | 0.882 | 0.882 | 100.0% | 50.0 |
| volume_price | pv_divergence_20_cs | 0.745 | 0.746 | 97.9% | 50.0 |
| volume_price | momentum_60_cs | 0.083 | 0.083 | 50.0% | 49.5 |
| volume_price | macd_12_26_9_cs | -0.442 | -0.441 | 21.7% | 49.9 |

## Phase1 与 Aligned IC 口径对照

这里专门核对 value 因子的矛盾：旧 Phase1 日志是直接用当期因子面板与 `fwd_ret_5d` 做全样本日频/原始面板评估；regime 诊断使用 weekly as-of aligned 因子、coverage gate、warmup 后的目标信号日。

| Factor | Phase1 Mean IC | Phase1 ICIR | Phase1正IC率 | Aligned Mean IC | Aligned ICIR | Aligned正IC率 | Top-Bottom超额 |
|---|---:|---:|---:|---:|---:|---:|---:|
| bp_cs | 0.165 | 1.173 | 90.9% | 0.068 | 0.311 | 59.2% | 37.5% |
| ep_cs | 0.076 | 0.554 | 63.6% | 0.050 | 0.279 | 61.2% | 17.2% |
| momentum_120_cs | 0.058 | 0.273 | 57.3% | 0.043 | 0.219 | 56.8% | 33.1% |
| momentum_60_cs | 0.024 | 0.116 | 57.0% | 0.011 | 0.058 | 55.3% | 26.8% |
| sp_cs | 0.076 | 0.561 | 81.8% | 0.043 | 0.252 | 59.2% | 22.1% |

## 诊断判断

- 单因子层面最值得关注的是 `momentum_120_cs`，Top-Bottom 年化超额 33.1%。
- 在 momentum sleeve 内，`momentum_60_cs` 平均权重 0.040，活跃率 67.3%，平均 ICIR 0.016。
- value sleeve 中绝对权重最高的是 `bp_cs`，平均权重 0.394，但这只说明历史滚动 IC 权重如何下注，不等于当前窗口 Top50 经济收益有效。
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

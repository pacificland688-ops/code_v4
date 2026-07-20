# Sleeve 内部权重诊断：20180101-20181231

## 边界

- 固定使用配置 `outputs\analysis\regime_grid_overlay_phase2_2025\configs\less_reversal_faster_overlay.yaml`。
- 只重算 sleeve 内部 IC 权重和选股暴露，不搜索参数、不改配置。
- 权重使用 `matured_ic_cutoff()`，只看 forward return 已成熟的历史 IC。
- 当前窗口结果只用于诊断，不作为直接调参或反向因子的依据。

## 样本

- Window: `20180101-20181231`
- Data window: `20170601-20181231`
- Target signal dates: 51
- Scoring signal dates: 81

## Sleeve 内部因子权重

| Sleeve | Factor | 活跃率 | 平均权重 | 平均绝对权重 | 正权重率 | 负权重率 | 平均ICIR | ICIR低于门槛率 | 方向不稳率 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| defensive | reversal_20_cs | 70.6% | 0.097 | 0.316 | 45.1% | 25.5% | 0.041 | 23.5% | 35.3% |
| defensive | volatility_60_cs | 84.3% | 0.116 | 0.301 | 52.9% | 31.4% | 0.043 | 15.7% | 37.3% |
| defensive | volatility_20_cs | 74.5% | 0.031 | 0.285 | 43.1% | 31.4% | 0.024 | 25.5% | 27.5% |
| momentum | pv_divergence_20_cs | 98.0% | 0.497 | 0.497 | 98.0% | 0.0% | 0.415 | 0.0% | 23.5% |
| momentum | momentum_60_cs | 86.3% | 0.212 | 0.212 | 86.3% | 0.0% | 0.165 | 13.7% | 27.5% |
| momentum | momentum_120_cs | 52.9% | 0.132 | 0.153 | 47.1% | 5.9% | 0.211 | 5.9% | 19.6% |
| momentum | macd_12_26_9_cs | 74.5% | -0.002 | 0.118 | 31.4% | 43.1% | -0.022 | 25.5% | 29.4% |
| reversal | pv_divergence_20_cs | 100.0% | 0.513 | 0.513 | 100.0% | 0.0% | 0.415 | 0.0% | 23.5% |
| reversal | reversal_5_cs | 78.4% | 0.182 | 0.210 | 64.7% | 13.7% | 0.160 | 21.6% | 35.3% |
| reversal | rsi_14_cs | 66.7% | -0.111 | 0.140 | 15.7% | 51.0% | -0.083 | 33.3% | 39.2% |
| reversal | reversal_20_cs | 76.5% | 0.031 | 0.137 | 49.0% | 27.5% | 0.041 | 23.5% | 35.3% |
| value | bp_cs | 92.2% | -0.159 | 0.426 | 35.3% | 56.9% | -0.042 | 3.9% | 27.5% |
| value | ep_cs | 86.3% | 0.017 | 0.259 | 43.1% | 43.1% | 0.030 | 13.7% | 13.7% |
| value | sp_cs | 84.3% | 0.152 | 0.256 | 62.7% | 21.6% | 0.090 | 13.7% | 35.3% |
| volume_price | pv_divergence_20_cs | 96.1% | 0.494 | 0.494 | 96.1% | 0.0% | 0.415 | 0.0% | 23.5% |
| volume_price | momentum_60_cs | 86.3% | 0.222 | 0.222 | 86.3% | 0.0% | 0.165 | 13.7% | 27.5% |
| volume_price | macd_12_26_9_cs | 74.5% | -0.021 | 0.124 | 31.4% | 43.1% | -0.022 | 25.5% | 29.4% |
| volume_price | volatility_20_cs | 74.5% | 0.057 | 0.120 | 43.1% | 31.4% | 0.024 | 25.5% | 27.5% |

## Top50 选股暴露

| Sleeve | Factor | 平均选中暴露 | 相对全域暴露 | 正暴露率 | 平均有效持仓数 |
|---|---|---:|---:|---:|---:|
| defensive | reversal_20_cs | 0.097 | 0.095 | 52.3% | 50.0 |
| defensive | volatility_60_cs | 0.088 | 0.089 | 55.6% | 50.0 |
| defensive | volatility_20_cs | 0.016 | 0.017 | 55.6% | 50.0 |
| momentum | pv_divergence_20_cs | 1.257 | 1.256 | 100.0% | 49.3 |
| momentum | momentum_60_cs | 0.657 | 0.657 | 93.8% | 48.3 |
| momentum | momentum_120_cs | 0.654 | 0.655 | 86.7% | 47.0 |
| momentum | macd_12_26_9_cs | -0.377 | -0.376 | 18.8% | 49.3 |
| reversal | pv_divergence_20_cs | 1.205 | 1.205 | 90.2% | 49.9 |
| reversal | reversal_20_cs | 0.586 | 0.585 | 77.6% | 49.6 |
| reversal | reversal_5_cs | 0.465 | 0.463 | 74.5% | 50.0 |
| reversal | rsi_14_cs | 0.408 | 0.407 | 78.0% | 49.8 |
| value | sp_cs | 0.347 | 0.347 | 54.2% | 50.0 |
| value | ep_cs | 0.133 | 0.136 | 50.0% | 50.0 |
| value | bp_cs | 0.009 | 0.008 | 50.0% | 50.0 |
| volume_price | pv_divergence_20_cs | 1.254 | 1.253 | 100.0% | 49.6 |
| volume_price | momentum_60_cs | 0.635 | 0.636 | 97.9% | 48.5 |
| volume_price | volatility_20_cs | 0.026 | 0.027 | 51.0% | 49.6 |
| volume_price | macd_12_26_9_cs | -0.408 | -0.406 | 19.1% | 49.5 |

## Phase1 与 Aligned IC 口径对照

这里专门核对 value 因子的矛盾：旧 Phase1 日志是直接用当期因子面板与 `fwd_ret_5d` 做全样本日频/原始面板评估；regime 诊断使用 weekly as-of aligned 因子、coverage gate、warmup 后的目标信号日。

| Factor | Phase1 Mean IC | Phase1 ICIR | Phase1正IC率 | Aligned Mean IC | Aligned ICIR | Aligned正IC率 | Top-Bottom超额 |
|---|---:|---:|---:|---:|---:|---:|---:|
| bp_cs | -0.023 | -0.095 | 36.4% | 0.022 | 0.110 | 50.0% | 11.3% |
| ep_cs | -0.024 | -0.157 | 36.4% | 0.018 | 0.115 | 60.0% | 7.3% |
| momentum_120_cs | 0.020 | 0.102 | 52.7% | 0.020 | 0.099 | 55.6% | -1.9% |
| momentum_60_cs | 0.018 | 0.102 | 57.1% | 0.025 | 0.133 | 60.4% | 0.4% |
| sp_cs | -0.019 | -0.112 | 36.4% | 0.018 | 0.116 | 60.0% | 3.4% |

## 诊断判断

- 单因子层面最值得关注的是 `momentum_60_cs`，Top-Bottom 年化超额 0.4%。
- 在 momentum sleeve 内，`momentum_60_cs` 平均权重 0.212，活跃率 86.3%，平均 ICIR 0.165。
- value sleeve 中绝对权重最高的是 `bp_cs`，平均权重 -0.159，但这只说明历史滚动 IC 权重如何下注，不等于当前窗口 Top50 经济收益有效。
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

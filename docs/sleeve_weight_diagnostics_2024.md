# Sleeve 内部权重诊断：20240101-20241231

## 边界

- 固定使用配置 `outputs\analysis\regime_grid_overlay_phase2_2025\configs\less_reversal_faster_overlay.yaml`。
- 只重算 sleeve 内部 IC 权重和选股暴露，不搜索参数、不改配置。
- 权重使用 `matured_ic_cutoff()`，只看 forward return 已成熟的历史 IC。
- 当前窗口结果只用于诊断，不作为直接调参或反向因子的依据。

## 样本

- Window: `20240101-20241231`
- Data window: `20230601-20241231`
- Target signal dates: 52
- Scoring signal dates: 82

## Sleeve 内部因子权重

| Sleeve | Factor | 活跃率 | 平均权重 | 平均绝对权重 | 正权重率 | 负权重率 | 平均ICIR | ICIR低于门槛率 | 方向不稳率 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| defensive | volatility_20_cs | 100.0% | 0.455 | 0.455 | 100.0% | 0.0% | 0.310 | 0.0% | 26.9% |
| defensive | volatility_60_cs | 100.0% | 0.449 | 0.449 | 100.0% | 0.0% | 0.302 | 0.0% | 23.1% |
| defensive | reversal_20_cs | 63.5% | -0.057 | 0.096 | 11.5% | 51.9% | -0.054 | 36.5% | 44.2% |
| momentum | pv_divergence_20_cs | 78.8% | 0.388 | 0.442 | 69.2% | 9.6% | 0.258 | 15.4% | 19.2% |
| momentum | momentum_60_cs | 67.3% | 0.010 | 0.176 | 50.0% | 17.3% | 0.059 | 30.8% | 36.5% |
| momentum | macd_12_26_9_cs | 61.5% | -0.111 | 0.159 | 25.0% | 36.5% | -0.026 | 36.5% | 46.2% |
| momentum | momentum_120_cs | 42.3% | 0.074 | 0.127 | 32.7% | 9.6% | 0.120 | 15.4% | 30.8% |
| reversal | pv_divergence_20_cs | 80.8% | 0.412 | 0.430 | 71.2% | 9.6% | 0.258 | 15.4% | 19.2% |
| reversal | reversal_5_cs | 75.0% | 0.128 | 0.223 | 55.8% | 19.2% | 0.053 | 21.2% | 36.5% |
| reversal | rsi_14_cs | 50.0% | -0.120 | 0.145 | 9.6% | 40.4% | -0.054 | 50.0% | 38.5% |
| reversal | reversal_20_cs | 63.5% | -0.085 | 0.125 | 11.5% | 51.9% | -0.054 | 36.5% | 44.2% |
| value | bp_cs | 94.2% | 0.403 | 0.403 | 94.2% | 0.0% | 0.219 | 5.8% | 19.2% |
| value | ep_cs | 88.5% | 0.298 | 0.298 | 88.5% | 0.0% | 0.181 | 11.5% | 25.0% |
| value | sp_cs | 84.6% | 0.174 | 0.261 | 65.4% | 19.2% | 0.125 | 11.5% | 36.5% |
| volume_price | volatility_20_cs | 98.1% | 0.417 | 0.417 | 98.1% | 0.0% | 0.310 | 0.0% | 26.9% |
| volume_price | pv_divergence_20_cs | 84.6% | 0.293 | 0.315 | 75.0% | 9.6% | 0.258 | 15.4% | 19.2% |
| volume_price | momentum_60_cs | 67.3% | 0.010 | 0.126 | 50.0% | 17.3% | 0.059 | 30.8% | 36.5% |
| volume_price | macd_12_26_9_cs | 63.5% | -0.090 | 0.123 | 25.0% | 38.5% | -0.026 | 36.5% | 46.2% |

## Top50 选股暴露

| Sleeve | Factor | 平均选中暴露 | 相对全域暴露 | 正暴露率 | 平均有效持仓数 |
|---|---|---:|---:|---:|---:|
| defensive | volatility_60_cs | 1.196 | 1.197 | 100.0% | 50.0 |
| defensive | volatility_20_cs | 1.193 | 1.194 | 100.0% | 50.0 |
| defensive | reversal_20_cs | -0.087 | -0.088 | 38.0% | 50.0 |
| momentum | pv_divergence_20_cs | 0.987 | 0.987 | 87.2% | 49.9 |
| momentum | momentum_120_cs | 0.331 | 0.331 | 76.7% | 48.6 |
| momentum | momentum_60_cs | 0.291 | 0.291 | 68.9% | 49.4 |
| momentum | macd_12_26_9_cs | -0.511 | -0.510 | 11.1% | 49.9 |
| reversal | pv_divergence_20_cs | 0.861 | 0.860 | 81.2% | 50.0 |
| reversal | reversal_5_cs | 0.234 | 0.234 | 68.8% | 50.0 |
| reversal | reversal_20_cs | 0.094 | 0.093 | 67.4% | 50.0 |
| reversal | rsi_14_cs | 0.077 | 0.076 | 66.0% | 50.0 |
| value | bp_cs | 1.654 | 1.653 | 100.0% | 50.0 |
| value | ep_cs | 1.479 | 1.475 | 100.0% | 50.0 |
| value | sp_cs | 0.977 | 0.976 | 98.0% | 50.0 |
| volume_price | pv_divergence_20_cs | 0.980 | 0.980 | 90.2% | 50.0 |
| volume_price | volatility_20_cs | 0.728 | 0.729 | 94.1% | 50.0 |
| volume_price | momentum_60_cs | 0.273 | 0.273 | 75.0% | 49.1 |
| volume_price | macd_12_26_9_cs | -0.374 | -0.374 | 22.4% | 50.0 |

## Phase1 与 Aligned IC 口径对照

这里专门核对 value 因子的矛盾：旧 Phase1 日志是直接用当期因子面板与 `fwd_ret_5d` 做全样本日频/原始面板评估；regime 诊断使用 weekly as-of aligned 因子、coverage gate、warmup 后的目标信号日。

| Factor | Phase1 Mean IC | Phase1 ICIR | Phase1正IC率 | Aligned Mean IC | Aligned ICIR | Aligned正IC率 | Top-Bottom超额 |
|---|---:|---:|---:|---:|---:|---:|---:|
| bp_cs | -0.036 | -0.227 | 50.0% | 0.053 | 0.295 | 65.4% | 13.6% |
| ep_cs | -0.005 | -0.038 | 41.7% | 0.046 | 0.265 | 65.4% | 1.2% |
| momentum_120_cs | 0.009 | 0.030 | 47.6% | -0.011 | -0.037 | 42.6% | -15.5% |
| momentum_60_cs | -0.021 | -0.077 | 47.1% | -0.023 | -0.087 | 46.9% | -13.6% |
| sp_cs | -0.004 | -0.025 | 33.3% | 0.027 | 0.154 | 59.6% | -2.2% |

## 诊断判断

- 单因子层面最值得关注的是 `momentum_60_cs`，Top-Bottom 年化超额 -13.6%。
- 在 momentum sleeve 内，`momentum_60_cs` 平均权重 0.010，活跃率 67.3%，平均 ICIR 0.059。
- value sleeve 中绝对权重最高的是 `bp_cs`，平均权重 0.403，但这只说明历史滚动 IC 权重如何下注，不等于当前窗口 Top50 经济收益有效。
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

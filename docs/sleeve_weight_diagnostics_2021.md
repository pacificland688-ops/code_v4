# Sleeve 内部权重诊断：20210101-20211231

## 边界

- 固定使用配置 `outputs\analysis\regime_grid_overlay_phase2_2025\configs\less_reversal_faster_overlay.yaml`。
- 只重算 sleeve 内部 IC 权重和选股暴露，不搜索参数、不改配置。
- 权重使用 `matured_ic_cutoff()`，只看 forward return 已成熟的历史 IC。
- 当前窗口结果只用于诊断，不作为直接调参或反向因子的依据。

## 样本

- Window: `20210101-20211231`
- Data window: `20200601-20211231`
- Target signal dates: 52
- Scoring signal dates: 83

## Sleeve 内部因子权重

| Sleeve | Factor | 活跃率 | 平均权重 | 平均绝对权重 | 正权重率 | 负权重率 | 平均ICIR | ICIR低于门槛率 | 方向不稳率 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| defensive | volatility_20_cs | 78.8% | 0.231 | 0.286 | 67.3% | 11.5% | 0.123 | 17.3% | 44.2% |
| defensive | reversal_20_cs | 75.0% | 0.187 | 0.279 | 65.4% | 9.6% | 0.117 | 11.5% | 36.5% |
| defensive | volatility_60_cs | 78.8% | 0.087 | 0.262 | 61.5% | 17.3% | 0.079 | 21.2% | 50.0% |
| momentum | momentum_60_cs | 82.7% | -0.198 | 0.346 | 26.9% | 55.8% | -0.046 | 13.5% | 38.5% |
| momentum | pv_divergence_20_cs | 88.5% | 0.169 | 0.327 | 53.8% | 34.6% | 0.125 | 7.7% | 32.7% |
| momentum | macd_12_26_9_cs | 69.2% | -0.157 | 0.157 | 0.0% | 69.2% | -0.104 | 30.8% | 38.5% |
| momentum | momentum_120_cs | 36.5% | 0.084 | 0.093 | 32.7% | 3.8% | 0.107 | 21.2% | 13.5% |
| reversal | pv_divergence_20_cs | 88.5% | 0.107 | 0.334 | 53.8% | 34.6% | 0.125 | 7.7% | 32.7% |
| reversal | reversal_20_cs | 88.5% | 0.188 | 0.226 | 76.9% | 11.5% | 0.117 | 11.5% | 36.5% |
| reversal | rsi_14_cs | 80.8% | 0.210 | 0.210 | 80.8% | 0.0% | 0.118 | 19.2% | 30.8% |
| reversal | reversal_5_cs | 75.0% | 0.184 | 0.191 | 73.1% | 1.9% | 0.111 | 25.0% | 23.1% |
| value | ep_cs | 76.9% | -0.101 | 0.311 | 40.4% | 36.5% | 0.002 | 23.1% | 46.2% |
| value | sp_cs | 73.1% | 0.105 | 0.277 | 48.1% | 25.0% | 0.061 | 25.0% | 65.4% |
| value | bp_cs | 63.5% | 0.149 | 0.258 | 50.0% | 13.5% | 0.066 | 30.8% | 51.9% |
| volume_price | momentum_60_cs | 86.5% | -0.170 | 0.333 | 26.9% | 59.6% | -0.046 | 13.5% | 38.5% |
| volume_price | pv_divergence_20_cs | 92.3% | 0.136 | 0.315 | 57.7% | 34.6% | 0.125 | 7.7% | 32.7% |
| volume_price | volatility_20_cs | 82.7% | 0.193 | 0.217 | 67.3% | 15.4% | 0.123 | 17.3% | 44.2% |
| volume_price | macd_12_26_9_cs | 69.2% | -0.135 | 0.135 | 0.0% | 69.2% | -0.104 | 30.8% | 38.5% |

## Top50 选股暴露

| Sleeve | Factor | 平均选中暴露 | 相对全域暴露 | 正暴露率 | 平均有效持仓数 |
|---|---|---:|---:|---:|---:|
| defensive | volatility_60_cs | 0.752 | 0.752 | 79.1% | 50.0 |
| defensive | volatility_20_cs | 0.727 | 0.728 | 79.1% | 50.0 |
| defensive | reversal_20_cs | 0.168 | 0.169 | 81.0% | 50.0 |
| momentum | pv_divergence_20_cs | 0.420 | 0.420 | 62.5% | 49.3 |
| momentum | momentum_120_cs | 0.111 | 0.111 | 57.1% | 47.3 |
| momentum | momentum_60_cs | 0.018 | 0.018 | 47.8% | 49.1 |
| momentum | macd_12_26_9_cs | -0.522 | -0.522 | 23.9% | 49.1 |
| reversal | rsi_14_cs | 0.948 | 0.948 | 90.0% | 49.8 |
| reversal | reversal_20_cs | 0.896 | 0.896 | 87.5% | 49.8 |
| reversal | reversal_5_cs | 0.813 | 0.813 | 96.0% | 50.0 |
| reversal | pv_divergence_20_cs | 0.780 | 0.780 | 82.0% | 49.8 |
| value | bp_cs | 0.704 | 0.693 | 61.4% | 50.0 |
| value | ep_cs | 0.561 | 0.555 | 59.1% | 50.0 |
| value | sp_cs | 0.490 | 0.483 | 61.4% | 50.0 |
| volume_price | pv_divergence_20_cs | 0.434 | 0.434 | 67.3% | 49.5 |
| volume_price | volatility_20_cs | 0.226 | 0.226 | 63.5% | 49.5 |
| volume_price | momentum_60_cs | -0.156 | -0.156 | 38.0% | 48.8 |
| volume_price | macd_12_26_9_cs | -0.409 | -0.409 | 18.4% | 49.0 |

## Phase1 与 Aligned IC 口径对照

这里专门核对 value 因子的矛盾：旧 Phase1 日志是直接用当期因子面板与 `fwd_ret_5d` 做全样本日频/原始面板评估；regime 诊断使用 weekly as-of aligned 因子、coverage gate、warmup 后的目标信号日。

| Factor | Phase1 Mean IC | Phase1 ICIR | Phase1正IC率 | Aligned Mean IC | Aligned ICIR | Aligned正IC率 | Top-Bottom超额 |
|---|---:|---:|---:|---:|---:|---:|---:|
| bp_cs | 0.103 | 0.391 | 45.5% | 0.038 | 0.142 | 43.1% | 18.0% |
| ep_cs | 0.092 | 0.428 | 45.5% | 0.023 | 0.095 | 47.1% | -7.3% |
| momentum_120_cs | 0.015 | 0.078 | 50.0% | -0.004 | -0.024 | 51.1% | 11.0% |
| momentum_60_cs | -0.017 | -0.078 | 49.6% | -0.042 | -0.201 | 49.0% | -25.5% |
| sp_cs | 0.123 | 0.806 | 63.6% | 0.022 | 0.107 | 47.1% | 20.5% |

## 诊断判断

- 单因子层面最值得关注的是 `momentum_120_cs`，Top-Bottom 年化超额 11.0%。
- 在 momentum sleeve 内，`momentum_60_cs` 平均权重 -0.198，活跃率 82.7%，平均 ICIR -0.046。
- value sleeve 中绝对权重最高的是 `ep_cs`，平均权重 -0.101，但这只说明历史滚动 IC 权重如何下注，不等于当前窗口 Top50 经济收益有效。
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

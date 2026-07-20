# Sleeve 内部权重诊断：20220101-20221231

## 边界

- 固定使用配置 `outputs\analysis\regime_grid_overlay_phase2_2025\configs\less_reversal_faster_overlay.yaml`。
- 只重算 sleeve 内部 IC 权重和选股暴露，不搜索参数、不改配置。
- 权重使用 `matured_ic_cutoff()`，只看 forward return 已成熟的历史 IC。
- 当前窗口结果只用于诊断，不作为直接调参或反向因子的依据。

## 样本

- Window: `20220101-20221231`
- Data window: `20210601-20221231`
- Target signal dates: 50
- Scoring signal dates: 81

## Sleeve 内部因子权重

| Sleeve | Factor | 活跃率 | 平均权重 | 平均绝对权重 | 正权重率 | 负权重率 | 平均ICIR | ICIR低于门槛率 | 方向不稳率 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| defensive | reversal_20_cs | 88.0% | 0.363 | 0.363 | 88.0% | 0.0% | 0.226 | 10.0% | 32.0% |
| defensive | volatility_20_cs | 86.0% | 0.160 | 0.310 | 70.0% | 16.0% | 0.184 | 10.0% | 32.0% |
| defensive | volatility_60_cs | 86.0% | 0.241 | 0.266 | 78.0% | 8.0% | 0.188 | 14.0% | 32.0% |
| momentum | pv_divergence_20_cs | 100.0% | 0.508 | 0.508 | 100.0% | 0.0% | 0.409 | 0.0% | 16.0% |
| momentum | momentum_60_cs | 96.0% | -0.200 | 0.262 | 14.0% | 82.0% | -0.193 | 4.0% | 24.0% |
| momentum | macd_12_26_9_cs | 86.0% | 0.042 | 0.161 | 52.0% | 34.0% | 0.035 | 14.0% | 30.0% |
| momentum | momentum_120_cs | 54.0% | -0.069 | 0.069 | 0.0% | 54.0% | -0.135 | 4.0% | 30.0% |
| reversal | pv_divergence_20_cs | 100.0% | 0.489 | 0.489 | 100.0% | 0.0% | 0.409 | 0.0% | 16.0% |
| reversal | reversal_20_cs | 90.0% | 0.205 | 0.205 | 90.0% | 0.0% | 0.226 | 10.0% | 32.0% |
| reversal | rsi_14_cs | 80.0% | 0.162 | 0.162 | 80.0% | 0.0% | 0.186 | 20.0% | 30.0% |
| reversal | reversal_5_cs | 94.0% | 0.049 | 0.143 | 54.0% | 40.0% | 0.073 | 6.0% | 50.0% |
| value | ep_cs | 82.0% | 0.119 | 0.303 | 62.0% | 20.0% | 0.095 | 18.0% | 30.0% |
| value | bp_cs | 78.0% | 0.239 | 0.295 | 66.0% | 12.0% | 0.124 | 16.0% | 34.0% |
| value | sp_cs | 76.0% | 0.094 | 0.242 | 56.0% | 20.0% | 0.078 | 24.0% | 30.0% |
| volume_price | pv_divergence_20_cs | 100.0% | 0.435 | 0.435 | 100.0% | 0.0% | 0.409 | 0.0% | 16.0% |
| volume_price | volatility_20_cs | 90.0% | 0.162 | 0.223 | 70.0% | 20.0% | 0.184 | 10.0% | 32.0% |
| volume_price | momentum_60_cs | 96.0% | -0.167 | 0.213 | 14.0% | 82.0% | -0.193 | 4.0% | 24.0% |
| volume_price | macd_12_26_9_cs | 86.0% | 0.044 | 0.129 | 52.0% | 34.0% | 0.035 | 14.0% | 30.0% |

## Top50 选股暴露

| Sleeve | Factor | 平均选中暴露 | 相对全域暴露 | 正暴露率 | 平均有效持仓数 |
|---|---|---:|---:|---:|---:|
| defensive | volatility_60_cs | 0.713 | 0.714 | 78.3% | 50.0 |
| defensive | volatility_20_cs | 0.607 | 0.607 | 76.6% | 50.0 |
| defensive | reversal_20_cs | 0.464 | 0.463 | 68.9% | 50.0 |
| momentum | pv_divergence_20_cs | 1.220 | 1.220 | 98.0% | 49.8 |
| momentum | macd_12_26_9_cs | -0.191 | -0.192 | 23.4% | 49.4 |
| momentum | momentum_120_cs | -0.267 | -0.267 | 26.7% | 48.1 |
| momentum | momentum_60_cs | -0.428 | -0.428 | 20.8% | 49.6 |
| reversal | pv_divergence_20_cs | 1.451 | 1.451 | 100.0% | 50.0 |
| reversal | reversal_20_cs | 1.170 | 1.170 | 100.0% | 50.0 |
| reversal | rsi_14_cs | 1.041 | 1.041 | 100.0% | 50.0 |
| reversal | reversal_5_cs | 0.621 | 0.621 | 94.0% | 50.0 |
| value | bp_cs | 1.101 | 1.087 | 76.2% | 50.0 |
| value | ep_cs | 1.088 | 1.082 | 76.2% | 50.0 |
| value | sp_cs | 0.769 | 0.765 | 76.2% | 50.0 |
| volume_price | pv_divergence_20_cs | 1.125 | 1.126 | 98.0% | 49.9 |
| volume_price | volatility_20_cs | 0.277 | 0.278 | 72.0% | 49.9 |
| volume_price | macd_12_26_9_cs | -0.127 | -0.127 | 25.5% | 49.5 |
| volume_price | momentum_60_cs | -0.268 | -0.268 | 22.9% | 49.6 |

## Phase1 与 Aligned IC 口径对照

这里专门核对 value 因子的矛盾：旧 Phase1 日志是直接用当期因子面板与 `fwd_ret_5d` 做全样本日频/原始面板评估；regime 诊断使用 weekly as-of aligned 因子、coverage gate、warmup 后的目标信号日。

| Factor | Phase1 Mean IC | Phase1 ICIR | Phase1正IC率 | Aligned Mean IC | Aligned ICIR | Aligned正IC率 | Top-Bottom超额 |
|---|---:|---:|---:|---:|---:|---:|---:|
| bp_cs | 0.062 | 0.182 | 45.5% | 0.034 | 0.128 | 55.1% | 26.6% |
| ep_cs | 0.045 | 0.144 | 45.5% | 0.024 | 0.092 | 51.0% | 16.2% |
| momentum_120_cs | -0.022 | -0.117 | 47.3% | -0.015 | -0.077 | 52.3% | -11.6% |
| momentum_60_cs | -0.038 | -0.205 | 43.0% | -0.042 | -0.217 | 42.6% | -46.5% |
| sp_cs | 0.042 | 0.148 | 45.5% | 0.014 | 0.066 | 44.9% | 14.4% |

## 诊断判断

- 单因子层面最值得关注的是 `momentum_120_cs`，Top-Bottom 年化超额 -11.6%。
- 在 momentum sleeve 内，`momentum_60_cs` 平均权重 -0.200，活跃率 96.0%，平均 ICIR -0.193。
- value sleeve 中绝对权重最高的是 `ep_cs`，平均权重 0.119，但这只说明历史滚动 IC 权重如何下注，不等于当前窗口 Top50 经济收益有效。
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

# Sleeve 内部权重诊断：20200101-20201231

## 边界

- 固定使用配置 `outputs\analysis\regime_grid_overlay_phase2_2025\configs\less_reversal_faster_overlay.yaml`。
- 只重算 sleeve 内部 IC 权重和选股暴露，不搜索参数、不改配置。
- 权重使用 `matured_ic_cutoff()`，只看 forward return 已成熟的历史 IC。
- 当前窗口结果只用于诊断，不作为直接调参或反向因子的依据。

## 样本

- Window: `20200101-20201231`
- Data window: `20190601-20201231`
- Target signal dates: 52
- Scoring signal dates: 82

## Sleeve 内部因子权重

| Sleeve | Factor | 活跃率 | 平均权重 | 平均绝对权重 | 正权重率 | 负权重率 | 平均ICIR | ICIR低于门槛率 | 方向不稳率 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| defensive | volatility_60_cs | 55.8% | -0.178 | 0.230 | 7.7% | 48.1% | -0.056 | 34.6% | 25.0% |
| defensive | volatility_20_cs | 53.8% | -0.151 | 0.206 | 7.7% | 46.2% | -0.052 | 38.5% | 23.1% |
| defensive | reversal_20_cs | 46.2% | -0.033 | 0.160 | 17.3% | 28.8% | -0.010 | 34.6% | 48.1% |
| momentum | pv_divergence_20_cs | 82.7% | 0.247 | 0.267 | 78.8% | 3.8% | 0.106 | 17.3% | 26.9% |
| momentum | momentum_60_cs | 75.0% | 0.184 | 0.236 | 63.5% | 11.5% | 0.125 | 21.2% | 30.8% |
| momentum | momentum_120_cs | 57.7% | 0.221 | 0.221 | 57.7% | 0.0% | 0.215 | 0.0% | 9.6% |
| momentum | macd_12_26_9_cs | 75.0% | 0.113 | 0.218 | 50.0% | 25.0% | 0.032 | 23.1% | 34.6% |
| reversal | reversal_5_cs | 84.6% | 0.346 | 0.363 | 82.7% | 1.9% | 0.168 | 9.6% | 34.6% |
| reversal | pv_divergence_20_cs | 82.7% | 0.236 | 0.255 | 78.8% | 3.8% | 0.106 | 17.3% | 26.9% |
| reversal | rsi_14_cs | 61.5% | -0.095 | 0.170 | 11.5% | 50.0% | -0.050 | 38.5% | 34.6% |
| reversal | reversal_20_cs | 65.4% | 0.031 | 0.155 | 28.8% | 36.5% | -0.010 | 34.6% | 48.1% |
| value | bp_cs | 100.0% | -0.384 | 0.384 | 0.0% | 100.0% | -0.307 | 0.0% | 30.8% |
| value | sp_cs | 92.3% | -0.382 | 0.382 | 0.0% | 92.3% | -0.305 | 7.7% | 34.6% |
| value | ep_cs | 76.9% | -0.220 | 0.233 | 1.9% | 75.0% | -0.202 | 23.1% | 28.8% |
| volume_price | momentum_60_cs | 78.8% | 0.271 | 0.319 | 67.3% | 11.5% | 0.125 | 21.2% | 30.8% |
| volume_price | pv_divergence_20_cs | 80.8% | 0.241 | 0.261 | 76.9% | 3.8% | 0.106 | 17.3% | 26.9% |
| volume_price | macd_12_26_9_cs | 76.9% | 0.100 | 0.248 | 51.9% | 25.0% | 0.032 | 23.1% | 34.6% |
| volume_price | volatility_20_cs | 61.5% | -0.103 | 0.152 | 11.5% | 50.0% | -0.052 | 38.5% | 23.1% |

## Top50 选股暴露

| Sleeve | Factor | 平均选中暴露 | 相对全域暴露 | 正暴露率 | 平均有效持仓数 |
|---|---|---:|---:|---:|---:|
| defensive | reversal_20_cs | -0.407 | -0.406 | 24.1% | 49.9 |
| defensive | volatility_60_cs | -1.063 | -1.062 | 16.7% | 49.9 |
| defensive | volatility_20_cs | -1.090 | -1.089 | 16.1% | 50.0 |
| momentum | momentum_120_cs | 1.084 | 1.084 | 95.3% | 46.9 |
| momentum | momentum_60_cs | 0.988 | 0.987 | 93.6% | 48.7 |
| momentum | pv_divergence_20_cs | 0.686 | 0.683 | 89.8% | 49.6 |
| momentum | macd_12_26_9_cs | -0.013 | -0.012 | 45.7% | 49.5 |
| reversal | pv_divergence_20_cs | 0.883 | 0.880 | 89.8% | 49.9 |
| reversal | reversal_5_cs | 0.808 | 0.808 | 91.8% | 50.0 |
| reversal | reversal_20_cs | 0.306 | 0.306 | 74.5% | 49.9 |
| reversal | rsi_14_cs | 0.284 | 0.283 | 73.5% | 49.9 |
| value | sp_cs | -0.875 | -0.878 | 0.0% | 50.0 |
| value | ep_cs | -0.906 | -0.909 | 1.9% | 50.0 |
| value | bp_cs | -1.014 | -1.021 | 1.9% | 50.0 |
| volume_price | momentum_60_cs | 0.884 | 0.884 | 83.7% | 47.1 |
| volume_price | pv_divergence_20_cs | 0.649 | 0.647 | 88.2% | 49.4 |
| volume_price | macd_12_26_9_cs | -0.030 | -0.029 | 47.9% | 49.8 |
| volume_price | volatility_20_cs | -0.780 | -0.776 | 3.9% | 49.4 |

## Phase1 与 Aligned IC 口径对照

这里专门核对 value 因子的矛盾：旧 Phase1 日志是直接用当期因子面板与 `fwd_ret_5d` 做全样本日频/原始面板评估；regime 诊断使用 weekly as-of aligned 因子、coverage gate、warmup 后的目标信号日。

| Factor | Phase1 Mean IC | Phase1 ICIR | Phase1正IC率 | Aligned Mean IC | Aligned ICIR | Aligned正IC率 | Top-Bottom超额 |
|---|---:|---:|---:|---:|---:|---:|---:|
| bp_cs | -0.141 | -0.504 | 27.3% | -0.080 | -0.317 | 36.0% | -51.4% |
| ep_cs | -0.126 | -0.585 | 18.2% | -0.061 | -0.259 | 40.0% | -48.6% |
| momentum_120_cs | 0.037 | 0.185 | 57.8% | 0.052 | 0.272 | 56.8% | 47.3% |
| momentum_60_cs | 0.028 | 0.161 | 58.8% | 0.038 | 0.220 | 58.3% | 40.3% |
| sp_cs | -0.094 | -0.597 | 36.4% | -0.049 | -0.251 | 40.0% | -28.2% |

## 诊断判断

- 单因子层面最值得关注的是 `momentum_120_cs`，Top-Bottom 年化超额 47.3%。
- 在 momentum sleeve 内，`momentum_60_cs` 平均权重 0.184，活跃率 75.0%，平均 ICIR 0.125。
- value sleeve 中绝对权重最高的是 `bp_cs`，平均权重 -0.384，但这只说明历史滚动 IC 权重如何下注，不等于当前窗口 Top50 经济收益有效。
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

# Sleeve 内部权重诊断：20190101-20191231

## 边界

- 固定使用配置 `outputs\analysis\regime_grid_overlay_phase2_2025\configs\less_reversal_faster_overlay.yaml`。
- 只重算 sleeve 内部 IC 权重和选股暴露，不搜索参数、不改配置。
- 权重使用 `matured_ic_cutoff()`，只看 forward return 已成熟的历史 IC。
- 当前窗口结果只用于诊断，不作为直接调参或反向因子的依据。

## 样本

- Window: `20190101-20191231`
- Data window: `20180601-20191231`
- Target signal dates: 52
- Scoring signal dates: 82

## Sleeve 内部因子权重

| Sleeve | Factor | 活跃率 | 平均权重 | 平均绝对权重 | 正权重率 | 负权重率 | 平均ICIR | ICIR低于门槛率 | 方向不稳率 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| defensive | reversal_20_cs | 90.4% | 0.389 | 0.389 | 90.4% | 0.0% | 0.300 | 1.9% | 28.8% |
| defensive | volatility_60_cs | 82.7% | 0.270 | 0.281 | 78.8% | 3.8% | 0.206 | 15.4% | 32.7% |
| defensive | volatility_20_cs | 80.8% | 0.170 | 0.233 | 69.2% | 11.5% | 0.184 | 19.2% | 36.5% |
| momentum | pv_divergence_20_cs | 88.5% | 0.542 | 0.542 | 88.5% | 0.0% | 0.503 | 0.0% | 15.4% |
| momentum | momentum_60_cs | 75.0% | 0.078 | 0.134 | 53.8% | 21.2% | 0.080 | 15.4% | 32.7% |
| momentum | macd_12_26_9_cs | 55.8% | 0.029 | 0.116 | 19.2% | 36.5% | -0.007 | 44.2% | 40.4% |
| momentum | momentum_120_cs | 51.9% | 0.077 | 0.093 | 44.2% | 7.7% | 0.128 | 3.8% | 19.2% |
| reversal | pv_divergence_20_cs | 100.0% | 0.416 | 0.416 | 100.0% | 0.0% | 0.503 | 0.0% | 15.4% |
| reversal | reversal_20_cs | 98.1% | 0.225 | 0.225 | 98.1% | 0.0% | 0.300 | 1.9% | 28.8% |
| reversal | rsi_14_cs | 96.2% | 0.183 | 0.215 | 88.5% | 7.7% | 0.282 | 3.8% | 28.8% |
| reversal | reversal_5_cs | 86.5% | 0.143 | 0.143 | 86.5% | 0.0% | 0.186 | 13.5% | 26.9% |
| value | bp_cs | 84.6% | -0.269 | 0.335 | 15.4% | 69.2% | -0.090 | 13.5% | 44.2% |
| value | sp_cs | 86.5% | -0.175 | 0.326 | 26.9% | 59.6% | -0.062 | 13.5% | 25.0% |
| value | ep_cs | 75.0% | 0.135 | 0.262 | 42.3% | 32.7% | 0.066 | 19.2% | 36.5% |
| volume_price | pv_divergence_20_cs | 100.0% | 0.577 | 0.577 | 100.0% | 0.0% | 0.503 | 0.0% | 15.4% |
| volume_price | volatility_20_cs | 80.8% | 0.155 | 0.191 | 69.2% | 11.5% | 0.184 | 19.2% | 36.5% |
| volume_price | momentum_60_cs | 75.0% | 0.095 | 0.138 | 53.8% | 21.2% | 0.080 | 15.4% | 32.7% |
| volume_price | macd_12_26_9_cs | 55.8% | 0.013 | 0.095 | 19.2% | 36.5% | -0.007 | 44.2% | 40.4% |

## Top50 选股暴露

| Sleeve | Factor | 平均选中暴露 | 相对全域暴露 | 正暴露率 | 平均有效持仓数 |
|---|---|---:|---:|---:|---:|
| defensive | volatility_60_cs | 0.750 | 0.754 | 87.0% | 50.0 |
| defensive | volatility_20_cs | 0.743 | 0.747 | 83.0% | 50.0 |
| defensive | reversal_20_cs | 0.643 | 0.644 | 84.4% | 50.0 |
| momentum | pv_divergence_20_cs | 1.397 | 1.397 | 100.0% | 49.9 |
| momentum | momentum_120_cs | 0.557 | 0.557 | 75.0% | 45.9 |
| momentum | momentum_60_cs | 0.455 | 0.454 | 77.3% | 47.9 |
| momentum | macd_12_26_9_cs | -0.264 | -0.264 | 22.2% | 49.7 |
| reversal | pv_divergence_20_cs | 1.441 | 1.441 | 100.0% | 50.0 |
| reversal | reversal_20_cs | 1.101 | 1.103 | 100.0% | 49.9 |
| reversal | rsi_14_cs | 1.090 | 1.091 | 100.0% | 50.0 |
| reversal | reversal_5_cs | 0.715 | 0.715 | 96.2% | 50.0 |
| value | ep_cs | 0.061 | 0.063 | 39.6% | 50.0 |
| value | sp_cs | -0.223 | -0.222 | 33.3% | 50.0 |
| value | bp_cs | -0.330 | -0.335 | 37.5% | 50.0 |
| volume_price | pv_divergence_20_cs | 1.431 | 1.431 | 100.0% | 50.0 |
| volume_price | momentum_60_cs | 0.329 | 0.329 | 80.0% | 48.7 |
| volume_price | volatility_20_cs | 0.120 | 0.123 | 65.4% | 50.0 |
| volume_price | macd_12_26_9_cs | -0.303 | -0.303 | 22.0% | 49.8 |

## Phase1 与 Aligned IC 口径对照

这里专门核对 value 因子的矛盾：旧 Phase1 日志是直接用当期因子面板与 `fwd_ret_5d` 做全样本日频/原始面板评估；regime 诊断使用 weekly as-of aligned 因子、coverage gate、warmup 后的目标信号日。

| Factor | Phase1 Mean IC | Phase1 ICIR | Phase1正IC率 | Aligned Mean IC | Aligned ICIR | Aligned正IC率 | Top-Bottom超额 |
|---|---:|---:|---:|---:|---:|---:|---:|
| bp_cs | 0.018 | 0.109 | 54.5% | -0.027 | -0.158 | 40.0% | -30.8% |
| ep_cs | 0.019 | 0.124 | 54.5% | 0.006 | 0.039 | 58.0% | -11.5% |
| momentum_120_cs | 0.026 | 0.202 | 60.7% | 0.011 | 0.082 | 61.4% | 6.6% |
| momentum_60_cs | 0.023 | 0.146 | 55.6% | 0.010 | 0.070 | 54.2% | 17.5% |
| sp_cs | -0.007 | -0.042 | 45.5% | -0.021 | -0.146 | 40.0% | -24.7% |

## 诊断判断

- 单因子层面最值得关注的是 `momentum_60_cs`，Top-Bottom 年化超额 17.5%。
- 在 momentum sleeve 内，`momentum_60_cs` 平均权重 0.078，活跃率 75.0%，平均 ICIR 0.080。
- value sleeve 中绝对权重最高的是 `bp_cs`，平均权重 -0.269，但这只说明历史滚动 IC 权重如何下注，不等于当前窗口 Top50 经济收益有效。
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

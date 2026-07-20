# Factors Candidate V4 R2 选择说明

生成日期：2026-06-19（更新：二次修复 F3 分析）
候选池：`configs/factors_candidate_v4_r2.yaml`
Gate 来源：`outputs/analysis/factor_quality_rebuild_v4/factor_quality_gate.csv`（2026-06-18 生成）
输入审计：`outputs/analysis/factor_quality_rebuild_v4/factor_input_audit.csv`

## 1. Gate PASS 状态

| 状态 | 数量 |
|---|---:|
| FAIL | 49 |
| DATA_MISSING | 14 |
| WATCH_NEUTRAL_UNAVAILABLE | 2 |
| SUPPORT | 1 |
| **PASS** | **0** |

**结论：NO_ALPHA_SOURCE — 零因子通过 gate。**

## 2. 硬性门禁 H2

按 `docs/strategy_v4_r2_unblock_fix_development_plan.md` §5：

> H2: gate PASS alpha factors < 3 → 停止，不进入候选池重建。

**判定：阻断。策略组装不可继续。**

## 3. 最接近 PASS 的因子

三个因子 gate 失败数 ≤5（最少）：

| 因子 | 失败数 | 硬失败 |
|---|---|---|
| `volatility_60_cs` | 2 | 0 |
| `volatility_20_cs` | 5 | 0 |
| `tail_risk_60d_cs` | 5 | 0 |

注：`volatility_60_cs` 在 r1 中为 WATCH_NEUTRAL_ONLY，r2 gate 重跑后变为 FAIL
（中性化覆盖率 4.88% < 70%）。仅 2 个软失败 — 是最接近 PASS 的因子。

## 4. Growth 因子

四个 growth 因子输入审计通过但 gate 失败：

| 因子 | 输入审计 | Gate | 失败数 |
|---|---|---|---|
| `revenue_growth_ttm_cs` | PASS | FAIL | 15 |
| `profit_growth_ttm_cs` | PASS | FAIL | 15 |
| `growth_stability_8q_cs` | PASS | FAIL | 12 |
| `earnings_acceleration_cs` | PASS | FAIL | 13 |

根因：PIT 过滤器将覆盖率限制在 < 1%。重键已修复（dup=0），但覆盖率过低导致无法进行有效 IC 校准。

## 5. Value 因子

ep、bp、sp、industry_relative_ep、industry_relative_bp 均因
`LEAKAGE_METADATA_MISSING`（data_lag_days=0）失败。
这是配置修复问题 — 需要正确的 data_lag_days 才能重新评估。

## 6. 决策

```
PASS alpha factors = 0 < 3 (min_gate_pass_alpha_factors)
→ NO_ALPHA_SOURCE
→ 停止 validation（H2 硬门禁）
→ 不生成正式 enabled_factors
→ 不运行 smoke/full validation
→ 不生成 GO/NO-GO
```

## 7. 解除阻断路径

需要至少 3 个因子通过 gate：

1. **Value 因子**：修复 ep/bp/sp 的 `data_lag_days` 配置后重跑 gate。
2. **Growth 因子**：调查 PIT 数据覆盖率 — 可能需要放宽 PIT 要求或使用替代数据源。
3. **Momentum/Technical**：改进因子定义 — 当前 IC/ICIR 在中国 A 股市场太弱。
4. **volatility_60_cs**：修复中性化覆盖率（当前 4.88%）— 可能需要更宽的股票池或替代中性化方法。

# V4 因子淘汰记录

生成日期：2026-06-14  
审核脚本：`scripts/factor_quality_rebuild.py --config configs/factor_quality_rebuild_v4.yaml`  
原则：所有被淘汰的因子必须有明确原因，不能静默缺失。

## 1. 已淘汰因子（来自 V2/V3）

| 因子 | 淘汰原因 | 证据 | 建议 |
|------|------|------|------|
| `reversal_20_cs` | ICIR < 0.20, 与 reversal_5_cs 冗余 | V3 audit: ICIR 0.767 but below 0.85 correlation threshold with reversal_5 | 永久淘汰，用 reversal_5_cs 替代 |
| `rsi_14_cs` | ICIR < 0.15, 近乎随机 | V3 audit: mean_rank_ic=0.008, pos_ic_years=3/8 | 永久淘汰 |
| `volatility_20_cs` | ICIR < 0.10, top quintile net excess < 0 | V3 audit: avg_long_only_top=-2.3% | 移至风险约束，不作为 alpha |
| `volatility_60_cs` | ICIR < 0.08, top quintile net excess < 0 | V3 audit: avg_long_only_top=-0.7% | 移至风险约束 |
| `momentum_60_cs` | ICIR < 0.02, near zero in trend markets | V3 audit: mean_rank_ic=0.000, ICIR=0.014 | 被 momentum_60_skip5_cs 替代 |
| `momentum_120_cs` | ICIR < 0.22, top quintile negative | V3 audit: avg_long_only_top=-2.1% | 被 momentum_120_skip20_cs 替代 |
| `macd_12_26_9_cs` | ICIR < 0.06, near zero in all markets | V3 audit: mean_rank_ic=-0.006, max_consecutive_negative=3 | 永久淘汰 |

## 2. 因数据不可用导致的预期淘汰

| 因子 | 预期淘汰原因 | 阻塞数据 | 优先级 |
|------|------|------|------|
| `accrual_quality_cs` | 需要资产负债表（应收账款）+ 现金流量表（OCF） | `balancesheet` API | P2 — 如果数据不可用则跳过 |
| `receivable_pressure_cs` | 需要应收账款变化数据 | `balancesheet` API | P2 — 同上 |
| `dividend_quality_cs` | 需要股息率数据 | `dividend` API | P2 — 同上 |
| `asset_turnover_ttm_cs` | 需要总资产数据 | `balancesheet` API 或 `fina_indicator` | P2 — 检查 fina_indicator 是否有此字段 |
| `growth_value_match_cs` | 复合因子（增长+估值），依赖其他因子先通过 gate | 间接依赖 | P2 — 后构建 |
| `valuation_reversion_3y_cs` | 需要 3 年估值历史分位 | 需要足够的 PE/PB 历史 | P2 — 2017 年前数据可能不完整 |

## 3. 预期淘汰规则

以下因子在质量 gate 中如果出现以下条件将被淘汰：

| 条件 | 阈值 | 说明 |
|------|------|------|
| validation mean rank IC | < 0.01 | 预测力不足 |
| validation ICIR | < 0.20 | 稳定性不足 |
| 正 IC 年数 | < 3/4 | 年份一致性不足 |
| 5d net spread after cost | <= 0 | 扣费后无净收益 |
| top quintile net excess | <= 0 | 多空组合无正超额 |
| cost resilience | < 50% | 成本侵蚀过大 |
| PIT audit | FAIL | 有 future leakage |
| 单年贡献集中度 | > 60% | 过度依赖单一年份 |

## 4. 淘汰后处理

- **永久淘汰**：因子定义和淘汰理由在此文件永久保留，不进入任何候选池。
- **数据阻塞**：因子进入 `blocked_factors` 列表，待数据就绪后可重新评估。
- **Gate 淘汰**：因子记录在此文件，包含具体失败维度和数值，供未来因子开发参考。

## 5. 淘汰汇总

截止 2026-06-14（gate 尚未实际运行）：

| 类别 | 淘汰数 | 说明 |
|------|------|------|
| V2/V3 已淘汰 | 7 | reversal_20, rsi_14, volatility_20/60, momentum_60/120, macd |
| 数据不可用预期 | 4-6 | accrual_quality, receivable_pressure, dividend_quality, asset_turnover 等 |
| Gate 预期淘汰 | TBD | 需实际运行 factor_quality_rebuild.py 后确定 |

**注意：** 本文件将在 M4 gate 实际运行后更新，填入具体的 gate 结果数值。

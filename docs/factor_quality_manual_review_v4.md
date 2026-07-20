# V4 因子质量人工复核列表

生成日期：2026-06-14  
审核范围：所有 PENDING_GATE 和 WATCH 状态的 V4 因子  
原则：人工复核不能只看统计，必须写经济理由、风险和预期使用方式。

## 1. 复核清单

| 序号 | 因子 | 优先级 | 状态 | 复核要点 |
|------|------|------|------|------|
| 1 | `roe_stability_8q_cs` | P0 | PENDING | 8 季度 ROE 数据在 2017-2020 年覆盖是否充足？ |
| 2 | `gross_margin_ttm_cs` | P0 | PENDING | 毛利率 TTM 在周期行业中是否有方向反转？ |
| 3 | `profitability_quality_cs` | P0 | PENDING | 综合质量评分是否因为一个维度主导而退化为单因子？ |
| 4 | `ocf_to_mktcap_cs` | P0 | PENDING | OCF 字段在 fina_indicator 中是否真实可用？ |
| 5 | `ocf_to_profit_cs` | P0 | PENDING | OCF/Profit < 0 的股票（负利润）如何处理？ |
| 6 | `fcf_yield_cs` | P0 | PENDING | FCF 字段是否存在？如不存在，能否用 OCF - capex 近似？ |
| 7 | `revenue_growth_ttm_cs` | P0 | PENDING | 收入为 0 或极端负增长如何处理？ |
| 8 | `profit_growth_ttm_cs` | P0 | PENDING | 利润从亏损转为盈利的增长率为 inf — 如何处理？ |
| 9 | `earnings_acceleration_cs` | P0 | PENDING | 二阶导在数据稀疏时噪声是否过大？ |
| 10 | `industry_relative_ep_cs` | P1 | PENDING | 行业内股票数 < 5 时行业排名是否可靠？ |
| 11 | `industry_relative_bp_cs` | P1 | PENDING | 负 PB（净资产为负）的股票如何处理？ |
| 12 | `quality_value_composite_cs` | P1 | PENDING | 复合因子是否退化为 value 或 quality 的简单代理？ |
| 13 | `industry_relative_momentum_60_cs` | P1 | PENDING | 行业内动量与全市场动量的差异是否足够大？ |
| 14 | `reversal_5_cs` (legacy) | WATCH | 已有 gate 结果 | 边际 ICIR — 为什么保留？经济理由是什么？ |

## 2. 经济理由模板

每个通过 gate 或被人工保留的因子必须填写：

```markdown
### factor_name_cs

**经济理由：** [为什么这个因子在中国 A 股市场应该有效]

**历史表现：** [calibration / validation 窗口的核心统计]

**风险与局限性：** [在什么市场环境中会失效]

**预期使用方式：** [在哪个 sleeve 中，与哪些因子互补，权重上限]

**PIT 审计状态：** [PASS / WARN / FAIL]

**人工保留理由（如适用）：** [如 gate 为 WATCH 但仍保留，必须写明理由]
```

## 3. 重点关注

### 3.1 PIT 风险因子

以下因子有较高的 PIT 风险，必须优先复核：

- `earnings_acceleration_cs`：需要 6+ 季度数据，2017 年初可能覆盖不足
- `ocf_to_profit_cs`：OCF 字段名不确定（可能是 `ocf`、`operating_cf`、`cf_sales`）
- `fcf_yield_cs`：FCF 字段可能不存在于 fina_indicator 中

### 3.2 相关性风险因子

以下因子对可能与现有因子高度相关，gate 中 clustering 可能需要处理：

- `industry_relative_ep_cs` vs `ep_cs`（行业相对 vs 全市场 EP）
- `gross_margin_ttm_cs` vs `profitability_quality_cs`（毛利率是后者的组成部分）
- `roe_stability_8q_cs` vs `profitability_quality_cs`（ROE 稳定性是后者的组成部分）
- `industry_relative_momentum_60_cs` vs `momentum_60_skip5_cs`（行业相对 vs 全市场动量）

### 3.3 覆盖风险因子

- 所有需要 8 季度数据的因子（`roe_stability_8q_cs`, `growth_stability_8q_cs`）在 2017 年初可能覆盖不足
- 现金流类因子完全依赖 `fina_indicator` 表的字段可用性

## 4. 复核流程

1. 运行 `factor_quality_rebuild.py --config factor_quality_rebuild_v4.yaml` 获得 gate 结果。
2. 对每个 PASS/WATCH 因子，按模板填写经济理由。
3. 对每个 FAIL 因子，确认淘汰理由无误。
4. 对 WATCH 因子，决定人工保留或降级为 FAIL。
5. 对相关性 cluster，确认保留的代表因子是 cluster 内最优的。
6. 更新 `factors_candidate_v4.yaml` 的 gate_status。

## 5. 复核判定

| 判定 | 门槛 | 后续动作 |
|------|------|------|
| 通过 | PASS gate 且经济理由充分 | 进入 `factors_candidate_v4.yaml` enabled list |
| 人工保留 | WATCH gate 但经济理由充分 + 风险可控 | 进入候选池但标记 `manual_retain` |
| 淘汰 | FAIL gate 或无经济理由 | 写入 `factor_rejection_log_v4.md` |

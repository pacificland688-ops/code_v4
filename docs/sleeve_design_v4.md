# V4 Sleeve 设计文档

生成日期：2026-06-14  
配置文件：`configs/regime_candidate_v4.yaml`  
基于因子池：`configs/factors_candidate_v4.yaml`

## 1. V4 Sleeve 总览

V4 重新设计了 6 个 sleeve，每个有明确经济含义和至少 2 个因子：

| # | Sleeve | 经济含义 | 目标市场 | 因子数 | vs V3 |
|------|------|------|------|------:|------|
| 1 | `quality_value` | 低估值 + 高质量甄别 | 所有市场（基准） | 7 | 替代原 `value` |
| 2 | `cashflow_quality` | 现金流验证盈利真实性 | 熊市、弱市 | 4 | **新增** |
| 3 | `growth_quality` | 成长但不过度追高 | 牛市、成长驱动 | 4 | **新增** |
| 4 | `risk_adjusted_momentum` | 风险调整后的趋势跟随 | 趋势市 | 7 | 替代原 `momentum` |
| 5 | `defensive_quality` | 弱市防御 + 品质筛选 | 熊市、高波动 | 6 | 增强原 `defensive` |
| 6 | `reversal` | 震荡市短期超跌反弹 | 震荡市 | 2 | 保留 |

**核心变更：**
- V3 的 6 个 sleeve（reversal, momentum, defensive, value, volume_price, shock_reversal）→ V4 的 6 个 sleeve
- 淘汰 `volume_price` 和 `shock_reversal`（单因子 sleeve，合并到相关 sleeve）
- 新增 `quality_value`、`cashflow_quality`、`growth_quality`
- 重命名/重构 `momentum` → `risk_adjusted_momentum`、`defensive` → `defensive_quality`

## 2. 各 Sleeve 详解

### 2.1 quality_value — 低估值 + 高质量

**经济含义：** 在估值便宜的股票中，用质量指标筛掉价值陷阱。核心逻辑：低 EP/BP 不是买入信号，低 EP/BP + 高 ROE 稳定性才是。

**因子组成：**
| 因子 | 角色 | 方向 |
|------|------|------|
| `ep_cs`, `bp_cs`, `sp_cs` | 估值基础 | + |
| `industry_relative_ep_cs`, `industry_relative_bp_cs` | 行业内估值比较 | + |
| `quality_value_composite_cs` | 质量-估值综合 | + |
| `roe_stability_8q_cs` | 盈利质量验证 | + |

**与 V3 `value` sleeve 的区别：** V3 value 只有 3 个因子（ep, bp, sp），没有质量甄别。

### 2.2 cashflow_quality — 现金流验证盈利

**经济含义：** 利润可以被会计操纵，但现金流很难。OCF/Profit > 1 的公司利润真实；FCF Yield 高的公司有真正的自由现金流。

**因子组成：**
| 因子 | 角色 | 方向 |
|------|------|------|
| `ocf_to_mktcap_cs` | 现金流角度的估值 | + |
| `ocf_to_profit_cs` | 利润真实性验证 | + |
| `fcf_yield_cs` | 自由现金流收益 | + |
| `profitability_quality_cs` | 综合质量 | + |

### 2.3 growth_quality — 成长但不过度追高

**经济含义：** 选出收入/利润在增长的公司，但避免纯 momentum 追逐。earnings_acceleration 捕捉拐点，growth_stability 淘汰波动大的伪成长。

**因子组成：**
| 因子 | 角色 | 方向 |
|------|------|------|
| `revenue_growth_ttm_cs` | 收入增长 | + |
| `profit_growth_ttm_cs` | 利润增长 | + |
| `earnings_acceleration_cs` | 增长拐点 | + |
| `growth_stability_8q_cs` | 增长质量 | + |

### 2.4 risk_adjusted_momentum — 趋势确认

**经济含义：** 动量在 A 股有效但不稳定。V4 用 skip-window（消除反转噪声）、波动率调整（惩罚高波动量）、成交量确认（验证趋势强度）来提高动量质量。

**因子组成：**
| 因子 | 角色 | 方向 |
|------|------|------|
| `momentum_60_skip5_cs` | 中期动量（跳过反转） | + |
| `momentum_120_skip20_cs` | 长期动量 | + |
| `risk_adjusted_momentum_60_cs` | 波动调整动量 | + |
| `volume_confirmed_momentum_cs` | 量价配合 | + |
| `trend_quality_cs` | 趋势质量 | + |
| `industry_relative_momentum_60_cs` | 行业内动量 | + |
| `pv_divergence_20_cs` | 量价背离 | + |

### 2.5 defensive_quality — 弱市防守

**经济含义：** 在下跌市中，高盈利质量 + 低波动 + 大市值的公司通常更抗跌。但"抗跌"不是目的，选出真正有品质的公司才是。

**因子组成：**
| 因子 | 角色 | 方向 |
|------|------|------|
| `profitability_quality_cs` | 盈利质量 | + |
| `roe_stability_8q_cs` | 盈利稳定 | + |
| `gross_margin_ttm_cs` | 定价权 | + |
| `volatility_60_cs` | 低波动 | -（越低越好） |
| `log_market_cap_cs` | 大市值偏好 | -（越大越好） |
| `industry_relative_quality_cs` | 行业内质量 | + |

### 2.6 reversal — 震荡市短期反转

**经济含义：** 保留原 reversal sleeve 的功能，在震荡市（range_bound regime）捕捉超跌反弹。V4 不在此 sleeve 中投入过多因子，因为短期反转信号半衰期极短。

**因子组成：**
| 因子 | 角色 | 方向 |
|------|------|------|
| `reversal_5_cs` | 5 日短期反转 | + |
| `pv_divergence_20_cs` | 量价背离 | + |

## 3. Regime 映射逻辑

### 3.1 Regime → Sleeve 权重

| Regime | 主 Sleeve | 权重 | 次 Sleeve | 权重 |
|------|------|------:|------|------:|
| `trend_up` | risk_adjusted_momentum | 35% | growth_quality | 30% |
| `trend_down` | defensive_quality | 45% | quality_value | 20% |
| `range_bound` | reversal + quality_value | 各 25% | cashflow_quality | 20% |
| `high_volatility` | defensive_quality | 50% | quality_value | 20% |
| `value_rotation` | quality_value | 40% | cashflow_quality | 25% |

### 3.2 设计原则

1. **不基于回测结果硬调**：权重基于经济逻辑，不是拟合。
2. **每个 regime 至少 2 个 active sleeve**（min_sleeves=2）。
3. **权重变化有平滑约束**（max_weekly_weight_change=0.15），避免剧烈切换。
4. **defensive_quality 在高波动和下行市场中权重最高**（符合直觉）。

## 4. Performance Overlay 决策

**V4 默认关闭 performance overlay。**

理由：
1. V3 已证明 overlay 改善有限（+0.92pp 平均），不能替代 alpha 创造。
2. V4 重点是新增 alpha 供给，overlay 会混淆改善来源。
3. 保留 no-overlay 对照，后续可准确度量 overlay 的纯边际贡献。
4. 如果 V4 no-overlay 已经达标，无需 overlay 增加复杂度。

**后续评估：** 如果 V4 no-overlay 达到 GO 门槛，可在 Phase 3（风险约束组合研究）中测试 overlay 的边际效应。

## 5. V3 → V4 Sleeve 变更汇总

| V3 Sleeve | V4 Sleeve | 变更内容 |
|------|------|------|
| `value` | `quality_value` | 新增 4 个质量/行业估值因子 |
| (不存在) | `cashflow_quality` | 全新，4 个现金流因子 |
| (不存在) | `growth_quality` | 全新，4 个成长因子 |
| `momentum` | `risk_adjusted_momentum` | 从 1 个因子扩展到 7 个（含跳过窗口、波动调整等） |
| `defensive` | `defensive_quality` | 从 2 个因子扩展到 6 个（加入质量维度） |
| `reversal` | `reversal` | 保留（2 因子） |
| `volume_price` | 合并到 `risk_adjusted_momentum` | `pv_divergence_20_cs` 移入动量 sleeve |
| `shock_reversal` | 移除 | 已证明收效有限 |

# V4 Alpha 因子定义与经济解释

生成日期：2026-06-14  
因子池：`configs/factors_alpha_v4_universe.yaml`（28 个因子，6 大类）  
原则：每个因子必须有公式、数据依赖和经济解释，不只靠统计。

## 1. 质量类（Quality）

### 1.1 `roe_stability_8q_cs` (P0)

**公式:**
```
ROE_stability = -std(ROE_t, ROE_{t-1}, ..., ROE_{t-7})
```
其中 ROE_q 为最近 8 个可用季度的 ROE（每季度公告日后生效）。

**经济解释:** ROE 波动越低的公司，盈利质量越高、经营越稳定。在弱市中（2023），盈利稳定的公司更抗跌。在价值陷阱中，低估值 + ROE 不稳定 = 风险信号。

**方向:** 正（ROE 越稳定 → 越值得持有）

**数据依赖:** `fina_indicator.roe`（至少需要 4 个季度数据）

### 1.2 `roa_ttm_cs` (P2)

**公式:**
```
ROA_TTM = 最近 4 季度净利润合计 / 最近季度总资产
```

**经济解释:** ROA 不受杠杆影响，比 ROE 更能反映经营效率。补充 ROE 在高杠杆公司上的偏差。

**数据依赖:** `fina_indicator.roa`（或 `income.n_income` + `balancesheet.total_assets`）

### 1.3 `gross_margin_ttm_cs` (P0)

**公式:**
```
GrossMargin_TTM = (最近 4 季度毛利合计) / (最近 4 季度收入合计)
```

**经济解释:** 毛利率反映定价权和成本控制。高毛利率公司在成本上升周期（2023-2024）中有更大缓冲。毛利率稳定性也是盈利质量的重要信号。

**数据依赖:** `fina_indicator.grossprofit_margin` 或 `income` 表

### 1.4 `net_margin_ttm_cs` (P2)

**公式:**
```
NetMargin_TTM = (最近 4 季度净利润合计) / (最近 4 季度收入合计)
```

**经济解释:** 净利率考虑了费用控制。毛利率高但净利率低的公司可能在销售/管理费用上效率不足。

### 1.5 `profitability_quality_cs` (P0)

**公式:**
```
Quality_Score = rank(gross_margin_ttm) + rank(net_margin_ttm) + rank(roe_ttm)
```

**经济解释:** 综合盈利质量评分，三个维度的平均排名。单维度可能被操纵，多维度综合更可靠。

### 1.6 `asset_turnover_ttm_cs` (P2)

**公式:**
```
AssetTurnover = 最近 4 季度收入合计 / 最近季度总资产
```

**经济解释:** 资产周转率是杜邦分解中的运营效率维度。高周转率意味着轻资产运营模式，通常在弱市中更灵活。

## 2. 现金流类（Cashflow）

### 2.1 `ocf_to_mktcap_cs` (P0)

**公式:**
```
OCF/MktCap = 最近 4 季度经营现金流合计 / 当前总市值
```

**经济解释:** 现金流角度的"估值"，类似 FCF yield 但使用更保守的经营现金流。高 OCF/MktCap 意味着公司产生大量现金相对其市值，是更可靠的"便宜"信号。

### 2.2 `ocf_to_profit_cs` (P0)

**公式:**
```
OCF/Profit = 最近 4 季度经营现金流合计 / 最近 4 季度净利润合计
```

**经济解释:**
- **> 1.0:** 利润有现金流支撑，盈利质量高。
- **< 0.5:** 利润主要来自应计项目，可能是"纸上利润"，应计操纵风险高。
- 在熊市中，OCF/Profit > 1 的公司更可能分红和回购。

### 2.3 `fcf_yield_cs` (P0)

**公式:**
```
FCF_Yield = (最近 4 季度经营现金流 - 资本支出) / 当前总市值
```

**经济解释:** 自由现金流收益率是估值最保守的度量。FCF 为负的公司即使是低 PE 也可能是价值陷阱。

### 2.4 `cashflow_stability_8q_cs` (P2)

**公式:**
```
CF_Stability = -std(OCF_{t}, OCF_{t-1}, ..., OCF_{t-7})
```

**经济解释:** 现金流稳定 → 经营可持续。高波动的经营现金流通常意味着周期性强或经营质量差。

### 2.5 `accrual_quality_cs` (P2)

**公式:**
```
Accrual_Quality = -(净利润_TTM - 经营现金流_TTM) / 总资产
```

**经济解释:** 应计项目越大（净利润远高于现金流），盈利质量越差。这是 Sloan (1996) 经典应计异象的核心。

### 2.6 `receivable_pressure_cs` (P2)

**公式:**
```
Receivable_Pressure = -(应收账款_q / 收入_q - 应收账款_{q-4} / 收入_{q-4})
```

**经济解释:** 应收账款/收入比率上升 → 客户付款变慢 → 现金流压力上升。是盈利质量恶化的领先指标。

## 3. 成长类（Growth）

### 3.1 `revenue_growth_ttm_cs` (P0)

**公式:**
```
Rev_Growth_TTM = (最近 4 季度收入合计 / 前 4 季度收入合计) - 1
```

**经济解释:** 收入增长是成长投资的核心。在 2017、2019 等成长驱动年份，收入增长是最直接的 alpha 来源。

### 3.2 `profit_growth_ttm_cs` (P0)

**公式:**
```
Profit_Growth_TTM = (最近 4 季度净利润合计 / 前 4 季度净利润合计) - 1
```

**经济解释:** 利润增长比收入增长更严格。收入增长但不赚钱的公司 = 烧钱换增长。

### 3.3 `growth_stability_8q_cs` (P1)

**公式:**
```
Growth_Stability = -std(Profit_Growth_{q}, ..., Profit_Growth_{q-7})
```

**经济解释:** 增长稳定性区分"持续增长"和"一次性暴增"。在 2021 年风格切换年中，增长稳定因子可以避免选中盈利波动大的伪成长股。

### 3.4 `growth_value_match_cs` (P2)

**公式:**
```
GV_Match = rank(revenue_growth_ttm) + rank(profit_growth_ttm) - rank(pe)
```

**经济解释:** 高增长但高 PE = 预期已被定价。高增长 + 合理 PE = 增长-估值匹配。避免单纯追高。

### 3.5 `earnings_acceleration_cs` (P0)

**公式:**
```
Earnings_Accel = (Profit_Growth_{TTM} - Profit_Growth_{TTM, 2q ago})
```

**经济解释:** 盈利增速的变化（二阶导）比盈利增速本身（一阶导）更早捕捉拐点。在转折市场（2019、2021）中尤其有价值。

## 4. 估值修复类（Value Repair）

### 4.1 `industry_relative_ep_cs` (P1)

**公式:**
```
IndRel_EP = rank_within_industry(EP)
            where EP = 1/PE
```

**经济解释:** 银行股天然低 PE，科技股天然高 PE。全市场排名会系统性偏袒某些行业。行业内排名消除了行业差异，更能反映公司相对同行的真实估值。

### 4.2 `industry_relative_bp_cs` (P1)

**公式:**
```
IndRel_BP = rank_within_industry(BP)
            where BP = 1/PB
```

### 4.3 `valuation_reversion_3y_cs` (P2)

**公式:**
```
Val_Reversion = -(当前 PE 分位 - 3 年 PE 均值)
```

**经济解释:** 估值均值回复 — PE 低于自身 3 年历史均值的公司有回复动力。比机械低 PE 更精细化。

### 4.4 `quality_value_composite_cs` (P1)

**公式:**
```
QV_Composite = rank(industry_relative_ep) + rank(roe_stability)
```

**经济解释:** 低估值 + 高质量 → 真正的"便宜好货"。避免低估值但质量差的价值陷阱。

### 4.5 `dividend_quality_cs` (P2)

**公式:**
```
Div_Quality = rank(div_yield) + rank(roe_stability) - rank(leverage)
```

**经济解释:** 高股息 + 盈利稳定 + 低负债 → 可持续的高分红。在 2024 年红利主题中，这个因子可以精确捕获优质红利股。

## 5. 行业相对强弱类（Industry Relative）

### 5.1 `industry_relative_momentum_60_cs` (P1)

**公式:**
```
IndRel_Mom = rank_within_industry(momentum_60_skip5)
```

**经济解释:** 行业内动量排名消除了行业动量效应。全市场动量往往只是行业轮动的代理变量。行业内排名是纯粹的公司层面信号。

### 5.2 `industry_relative_quality_cs` (P1)

**公式:**
```
IndRel_Quality = rank_within_industry(profitability_quality)
```

**经济解释:** 行业内质量排名 — 在同一个行业内选出运营最好的公司。

### 5.3 `industry_relative_growth_cs` (P2)

**公式:**
```
IndRel_Growth = rank_within_industry(revenue_growth_ttm + profit_growth_ttm)
```

### 5.4 `industry_relative_value_cs` (P2)

**公式:**
```
IndRel_Value = rank_within_industry(industry_relative_ep + industry_relative_bp)
```

## 6. 风险调整动量类（Risk-Adjusted Momentum）

### 6.1 `momentum_60_skip5_cs` (P2)

**公式:**
```
Mom_60_skip5 = (P_{t-5} / P_{t-60}) - 1
```

**经济解释:** 跳过最近 5 日消除短期反转噪声。标准 momentum 因子失败的一个主要原因是最近几天的反转效应吞噬了中期趋势信号。

### 6.2 `momentum_120_skip20_cs` (P2)

**公式:**
```
Mom_120_skip20 = (P_{t-20} / P_{t-120}) - 1
```

### 6.3 `risk_adjusted_momentum_60_cs` (P2)

**公式:**
```
RiskAdj_Mom = momentum_60 / std(daily_return, 60)
```

**经济解释:** 相同动量但波动率更低的股票 → 趋势更稳定。高波动动量往往是"假突破"。

### 6.4 `volume_confirmed_momentum_cs` (P2)

**公式:**
```
VolConf_Mom = momentum_60 × sign(vol_change_20)
              if abs(vol_change_20) > threshold else 0
```

**经济解释:** 放量上涨的动量比缩量上涨更可靠。缩量上涨可能是流动性幻觉。

### 6.5 `trend_quality_cs` (P2)

**公式:**
```
Trend_Quality = (P_t - MA_60) / std(P, 60) - |RSI - 50| / 50
```

**经济解释:** 趋势延续但避开极端拥挤（RSI 极端）。在趋势市中提供信号，但不在极端位置追入。

## 7. PIT 安全说明

所有标记为 `type: fundamental` 的因子必须使用以下 PIT 规则：

1. 财务数据使用 `ann_date`（公告日）作为 `available_date`，不使用报告期末 `end_date`。
2. 如果 `ann_date` 缺失，使用保守滞后规则（年报 +120 天，中报 +60 天，季报 +30 天）。
3. 因子值仅在 `available_date <= trade_date` 的交易日有效。
4. TTM 值使用最近 4 个可用季度的数据，每季度值在公告日后才可用。
5. 稳定性类因子（8 季度窗口）要求至少 4 个季度数据。

## 8. 因子命名规范

所有因子统一使用后缀 `_cs`（cross-sectional）表示经过横截面处理（winsorize + neutralize + standardize）。

命名模式：`{signal_name}_cs`

- `{signal_name}` = 描述信号来源（如 `roe_stability_8q`、`revenue_growth_ttm`）
- `_cs` = cross-sectionally processed

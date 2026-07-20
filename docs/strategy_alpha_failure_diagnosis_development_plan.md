# Strategy Alpha Failure Diagnosis & Development Plan

生成日期：2026-06-13  
前置文档：`docs/strategy_next_development_plan.md`、`docs/failure_year_monthly_attribution.md`、`docs/go_nogo_decision.md`、`docs/frozen_backtest_attribution.md`、`docs/strategy_v3_development_plan.md`
适用策略：`D_regime_overlay` / `E_candidate_v2` / `F_candidate_v3`（全部共享同一 alpha 池瓶颈）

## 1. 问题陈述

### 1.1 Alpha 层是当前最大瓶颈

失败归因已明确：Alpha 池质量不足是策略负超额的第一大来源（权重 ~50%），超过 regime router 问题（~25%）和组合构建摩擦（~15%）。

| 诊断结论 | 来源 |
|----------|------|
| 13 个因子中仅 3 个 value 因子稳定通过 IC 门槛 | `failure_year_monthly_attribution.md` §4.1 |
| 技术类因子（reversal/momentum/RSI/MACD/volatility）全部未通过 | 同上 |
| 基本面质量/成长因子（ROE/gross_margin/revenue_growth 等）全部被禁用 | `factors.yaml` |
| E_candidate_v2 收窄到 5 因子后平均超额仅 -1.2%，仍不足 | `go_nogo_decision.md` |
| V3 的 performance overlay 只能在已有 alpha 上调配，不能创造新 alpha | `strategy_v3_development_plan.md` |

### 1.2 不做 Alpha 修复的后果

即使 regime router 完美、组合构建零摩擦、交易成本为零，当前因子池的天花板仍然很低：

- 仅靠 3 个 value 因子，在成长驱动市场（2017、2019、2020）必然跑输
- value 因子在 2017-2024 的 IC 均值约 0.022–0.03，ICIR 约 0.28–0.35，本身只是"可接受"而非"强劲"
- 缺少质量因子意味着无法区分"真便宜"和"价值陷阱"
- 缺少有效动量因子意味着趋势市中完全依赖反转（恰好在趋势市失效）
- 防御因子（低波）从未真正贡献超额

### 1.3 本文档定位

本文档是 `strategy_next_development_plan.md` Phase C（因子和 sleeve 池重建）的深化执行方案，聚焦于一个核心问题：

> **为什么当前因子池的 alpha 无法支撑策略正超额？如何系统性地诊断和修复？**

与 V3 开发方案的关系：V3 是 overlay 层面的改进（上线 sleeve_performance_overlay），本文档是 alpha 层面的改进（提升底层因子质量）。两者并行——V3 改善 alpha 调配效率，本文档改善 alpha 供给质量。最终在候选冻结阶段汇合。

## 2. Alpha 失败诊断框架

### 2.1 三层诊断模型

每个因子的 alpha 失败必须在三个层面分别诊断，不能混为一谈：

```
Layer 1: 信号质量        →  因子原始信号是否有预测能力？
    ├── IC / ICIR / 正向率
    ├── 分年度稳定性
    ├── 不同市场状态下的条件 IC
    └── 因子自相关（衰减速度）

Layer 2: 信号可交易性    →  信号能否被实际交易捕获？
    ├── PIT 对齐（是否存在前视偏差）
    ├── 数据可用性（停牌日、缺失率、公告滞后）
    ├── 交易可行性（涨跌停、流动性、冲击成本）
    └── 换手频率与调仓周期是否匹配

Layer 3: 组合穿透力    →  信号是否能到达最终组合？
    ├── Factor → Sleeve Score 的 IC 加权是否准确
    ├── Sleeve → Composite Score 的 regime 映射是否保留 alpha
    ├── Composite → 持仓 的优化/约束是否吞噬信号
    └── 持仓 → 收益 的成本和延续是否侵蚀超额
```

### 2.2 因子分类矩阵

将每个因子归入以下四类之一：

| 类别 | 定义 | 行动 |
|------|------|------|
| **A. 确认 Alpha** | 三层全部通过，可进入 sleeve 池 | 保留并监控 |
| **B. 条件 Alpha** | 信号层通过，但交易或穿透有问题 | 修复交易/穿透瓶颈 |
| **C. 非 Alpha（风险/约束）** | 有预测力但方向为负，或只适合风控 | 移入风险模型或中性化 |
| **D. 无效因子** | 信号层就不通过，且无合理经济解释 | 降权或移除 |

### 2.3 诊断执行原则

1. **一次性诊断，不滚动调参。** 对每个因子用固定窗口（2017-2024）做完整诊断，不在诊断过程中调整因子定义。
2. **PIT 优先。** 任何因子在进入 Layer 2/3 前必须先通过 PIT 审计（`future_obs = 0`）。
3. **经济解释优先于统计显著。** IC 通过但无合理经济解释的因子，不进入 alpha 池。
4. **成本后收益才是真实收益。** Layer 2/3 的检验必须包含交易成本和流动性约束。
5. **区分失败年和成功年。** 因子在 2017-2024 中不能只在单一年份贡献全部收益。

## 3. 当前因子池逐因子诊断

### 3.1 技术类因子（当前 5 个 enabled + 4 个 disabled）

#### reversal_5_cs（当前 enabled）

| 维度 | 状态 | 详细 |
|------|------|------|
| IC mean (2017-2024) | ~0.015 | 未达 ≥0.02 门槛 |
| ICIR | ~0.18 | 未达 ≥0.30 门槛 |
| IC 正向率 | ~50% | 基本随机 |
| 分年表现 | 仅在震荡市中有效 | 2017/2019/2020 趋势市中为负贡献 |
| PIT 状态 | ✅ 通过 | 价格因子，无前视风险 |
| 可交易性 | ⚠️ 高换手 | 5 日反转换手率极高，受涨跌停限制 |
| 穿透力 | ⚠️ | 在 regime router 中被高配（range_bound 下 reversal=0.30），进一步放大弱点 |
| **分类** | **D. 无效因子**（或降为 B.条件，仅在 range-bound 生效） | |
| **建议** | 不作为独立 alpha sleeve 的主导因子。可保留为震荡市条件因子，但需要 regime 正确识别震荡市后再启用，而非默认高配 |

#### reversal_20_cs（当前 enabled）

| 维度 | 状态 | 详细 |
|------|------|------|
| IC mean | ~0.012 | 弱于 reversal_5 |
| ICIR | ~0.15 | 弱 |
| 其他 | 与 reversal_5 高度相似，衰减更慢但信号更弱 | |
| **分类** | **D. 无效因子** | |
| **建议** | 与 reversal_5 合并为一个中期反转因子，或直接移除 | |

#### rsi_14_cs（当前 enabled）

| 维度 | 状态 | 详细 |
|------|------|------|
| IC mean | ~0.010 | 极弱 |
| ICIR | ~0.12 | 极弱 |
| 经济解释 | RSI 在 A 股截面选股中缺乏理论支撑 | |
| **分类** | **D. 无效因子** | |
| **建议** | 移除。regime_candidate_v1 已将其从 reversal sleeve 移除，应扩展到所有 config | |

#### volatility_20_cs（当前 enabled）

| 维度 | 状态 | 详细 |
|------|------|------|
| IC mean | ~0.008 | 极弱 |
| ICIR | ~0.10 | 极弱 |
| 经济解释 | 低波异象在 A 股截面中存在但极不稳定 | |
| 分年表现 | 可能在下跌市提供保护，但不是 alpha 来源 | |
| **分类** | **C. 非 Alpha（风险约束）** | |
| **建议** | 从 alpha 池移出，改为组合风险约束（行业/市值中性化时保留低波暴露，或作为下跌市防御 sleeve 的风险因子而非 alpha 因子） | |

#### volatility_60_cs（当前 disabled）

| 维度 | 状态 | 详细 |
|------|------|------|
| 与 volatility_20 相似但更弱 | IC ~0.006, ICIR ~0.08 | |
| **分类** | **D. 无效因子** | |
| **建议** | 移除 | |

#### pv_divergence_20_cs（当前 enabled）

| 维度 | 状态 | 详细 |
|------|------|------|
| IC mean | ~0.020 | ⚠️ 边际通过（恰好踩线） |
| ICIR | ~0.25 | 未达 ≥0.30 门槛 |
| IC 正向率 | ~52% | 边际通过 |
| 经济解释 | 量价背离在 A 股有一定逻辑（主力资金行为） | |
| Overlay 表现 | 在 D 的 performance overlay 中 multiplier 最高（1.115），OK 比例 90% | |
| 分年表现 | 需要在诊断中拆解：是真实选股 alpha 还是与 reversal/value 的协方差 | |
| **分类** | **B. 条件 Alpha**（信号边际通过，需加强和纯化） | |
| **建议** | 保留但需要：(1) 验证是否在控制 value 和 reversal 后仍有独立 IC；(2) 测试更长窗口（如 40/60 日量价背离）；(3) 区分量价背离的类型（放量上涨后缩量回调 vs 放量下跌后缩量反弹） | |

#### momentum_60_cs / momentum_120_cs（当前 disabled，但 sleeve 中引用）

| 维度 | 状态 | 详细 |
|------|------|------|
| 当前状态 | disabled | 因 ICIR 低被禁用 |
| IC mean (momentum_120) | ~0.018 | 接近但仍低于 0.02 门槛 |
| ICIR | ~0.22 | 低于 0.30 门槛 |
| 经济解释 | A 股中期动量确实存在但弱于美股，且受风格切换和反转效应干扰 | |
| 问题假设 | 当前动量定义可能太简单（原始价格收益），未做风险调整或行业中性化 | |
| **分类** | **B. 条件 Alpha**（信号有方向但太弱，需改进定义） | |
| **建议** | 不要直接使用原始动量，改为：(1) 行业中性化后的动量（避免行业轮动干扰）；(2) 风险调整动量（收益/波动率，即夏普比）；(3) 残差动量（剔除市场和行业后的特质收益动量）。这些在 A 股文献中表现优于原始动量 | |

#### macd_12_26_9_cs（当前 disabled，但 sleeve 中引用）

| 维度 | 状态 | 详细 |
|------|------|------|
| 当前状态 | disabled | |
| 经济解释 | MACD 是时序指标，用于截面选股的理论支撑弱。当前截面标准化后等效于一个复杂的加权动量 | |
| **分类** | **D. 无效因子** | |
| **建议** | 移出 alpha 池。regime_candidate_v1 已将其从 momentum sleeve 移除 | |

#### turnover_5_cs / abnormal_turnover_20_cs（当前 disabled，不在 sleeve 中）

| 维度 | 状态 | 详细 |
|------|------|------|
| IC 表现 | 流动性因子的 A 股截面预测力通常为负（高换手→低收益） | |
| 经济解释 | 换手率在 A 股更多是风险代理而非 alpha 来源（散户偏好高换手股票推高价格后回归） | |
| **分类** | **C. 非 Alpha（可用于流动性约束或成本模型）** | |
| **建议** | 不进入 alpha 池。可用于：(1) 交易成本模型中的流动性折扣；(2) 换手约束的输入；(3) 选股池的流动性过滤 | |

### 3.2 基本面因子（全部 disabled）

#### ep_cs / bp_cs / sp_cs（当前 disabled，但 sleeve 中引用）

| 维度 | 状态 | 详细 |
|------|------|------|
| IC mean | ep: ~0.03, bp: ~0.025, sp: ~0.022 | ✅ 全部通过 ≥0.02 |
| ICIR | ep: ~0.35, bp: ~0.30, sp: ~0.28 | ⚠️ sp 边际 |
| IC 正向率 | ep: ~55%, bp: ~54%, sp: ~53% | ✅ 全部通过 ≥52% |
| 分年表现 | 在价值风格年份（2022）表现好，成长风格年份（2019/2020）表现弱 | 符合经济逻辑 |
| PIT 状态 | ⚠️ 需审计 | 当前使用 `ann_date` 还是 `f_ann_date`？是否有财报前视？ |
| 数据缺失 | ⚠️ 需审计 | 金融行业 PE/PB/PS 含义不同，缺失处理需确认 |
| 可交易性 | ✅ 低换手 | 基本面因子变化频率低（季报/中报/年报），交易成本低 |
| **分类** | **A. 确认 Alpha** | |
| **建议** | (1) 立即完成 PIT 审计和公告日期对齐；(2) 确认金融行业处理；(3) 重新启用并进入 candidate 因子池；(4) 考虑细分：ep_cs 可拆分为 trailing PE 和 forward PE（如可用分析师预期），bp_cs 可按行业调整 | |

#### roe_cs / gross_margin_cs（当前 disabled）

| 维度 | 状态 | 详细 |
|------|------|------|
| 当前状态 | disabled | 原因："data gaps cause coverage issues" |
| 经济解释 | ROE 和毛利率是质量因子的核心，在 A 股有大量文献支持 | |
| 未诊断 | IC/ICIR/分年表现均未计算 | — |
| PIT 问题 | ⚠️ 关键风险 | 财务报表的 `ann_date` 与 `f_ann_date` 差异大；需确认使用实际可用日期而非报告期结束日 |
| 覆盖率问题 | ⚠️ 需量化 | "coverage issues" 是模糊描述，需要量化：每期覆盖率是多少？哪些股票缺失？缺失是否系统性的（如某些行业/市值）？ |
| **分类** | **未诊断**（需先审计再分类） | |
| **建议** | 优先审计。毛利率的时效性优于 ROE（季报 vs 年报），可先行测试。对缺失数据使用行业中性填充或滞后一期值 | |

#### revenue_growth_cs / profit_growth_cs（当前 disabled）

| 维度 | 状态 | 详细 |
|------|------|------|
| 当前状态 | disabled | |
| 经济解释 | 成长因子在 A 股有正向预测力，但需要与价值因子配合使用 | |
| PIT 问题 | ⚠️ | 同比增速计算需要 4 个季度前的数据，需确认 PIT 可用性 |
| **分类** | **未诊断** | |
| **建议** | 审计后测试。注意：成长因子在 A 股与 value 因子通常为负相关，两者联合使用比单独使用更稳定 | |

#### leverage_cs（当前 disabled）

| 维度 | 状态 | 详细 |
|------|------|------|
| 经济解释 | 杠杆率在 A 股截面中通常为负相关（高杠杆→高财务风险→低收益） | |
| **分类** | **C. 非 Alpha（可用于风险约束或质量因子的子成分）** | |
| **建议** | 不单独进入 alpha 池。可纳入质量因子的构建（作为负向成分） | |

### 3.3 诊断汇总

| 因子 | 当前启用 | 分类 | 行动 |
|------|:---:|------|------|
| ep_cs | ❌ | A. 确认 Alpha | PIT 审计后重新启用 |
| bp_cs | ❌ | A. 确认 Alpha | PIT 审计后重新启用 |
| sp_cs | ❌ | A. 确认 Alpha（边际） | PIT 审计后重新启用 |
| pv_divergence_20_cs | ✅ | B. 条件 Alpha | 纯化：控制 value/reversal 后的独立 IC；测试更长窗口 |
| momentum_120_cs | ❌ | B. 条件 Alpha | 改进定义：行业中性化/风险调整/残差动量 |
| momentum_60_cs | ❌ | B. 条件 Alpha | 同上，作为备选 |
| reversal_5_cs | ✅ | D. 无效→条件 | 降为震荡市条件因子，不作为默认 alpha |
| reversal_20_cs | ✅ | D. 无效 | 合并或移除 |
| rsi_14_cs | ✅ | D. 无效 | 移除 |
| macd_12_26_9_cs | ❌ | D. 无效 | 移除 |
| volatility_20_cs | ✅ | C. 风险约束 | 移出 alpha 池，进入风险模型 |
| volatility_60_cs | ❌ | D. 无效 | 移除 |
| turnover_5_cs | ❌ | C. 风险约束 | 进入成本/流动性模型 |
| abnormal_turnover_20_cs | ❌ | C. 风险约束 | 进入成本/流动性模型 |
| roe_cs | ❌ | 未诊断 | 优先审计 |
| gross_margin_cs | ❌ | 未诊断 | 优先审计 |
| revenue_growth_cs | ❌ | 未诊断 | 审计后测试 |
| profit_growth_cs | ❌ | 未诊断 | 审计后测试 |
| leverage_cs | ❌ | C. 风险约束 | 纳入质量因子构建 |
| log_market_cap_cs | N/A | C. 风险约束 | 仅用于中性化，不进入 alpha |

**关键判断：当前 5 个 enabled 因子中，只有 pv_divergence_20 有保留价值（需改进）。reversal 应降级，volatility/rsi 应移除。真正的 alpha 来源（value + 质量）反而是 disabled 的。**

## 4. 诊断执行计划

### Phase D1：基本面因子 PIT 审计与重新启用

这是最高优先级的任务——当前 disabled 的 value 因子恰恰是唯一通过 IC 门槛的 alpha。

| ID | 任务 | 输入 | 产物 | 验证标准 |
|----|------|------|------|----------|
| D1.1 | 审计 ep_cs / bp_cs / sp_cs 的 PIT 对齐 | `fundamental.py` 中的数据源调用 | PIT 审计表 | `future_obs = 0`，`ann_date` 使用正确 |
| D1.2 | 量化基本面因子的覆盖率 | 2017-2024 每期覆盖率和缺失模式 | 覆盖率报告 | 分行业/市值的覆盖分布 |
| D1.3 | 审计金融行业 PE/PB/PS 的处理 | 当前代码逻辑 | 审计记录 | 确认使用 industry_neutral 或正确处理 |
| D1.4 | 修复 PIT 或覆盖率问题（如有） | D1.1-D1.3 的发现 | 代码修复 | 修复后重新审计通过 |
| D1.5 | 重新启用 ep/bp/sp 并重跑 Phase2 单年冒烟（2023） | D1.4 修复后的因子 | 2023 冒烟结果 | 无报错，manifest 完整 |

审计命令：

```powershell
# 1. 检查基本面因子的 PIT 使用
python -c "
from factors.fundamental import FundamentalFactorComputer
# 确认 ann_date vs f_ann_date 的使用
# 确认财报滞后处理
"

# 2. 计算覆盖率
python -c "
import pandas as pd
# 读取 ep_cs, bp_cs, sp_cs 缓存
# 输出每期股票数、缺失率
# 按行业、市值分组统计
"

# 3. 单因子 IC 评估
python -X utf8 scripts/eval_single_factor.py --factor ep_cs --start 20170101 --end 20241231
python -X utf8 scripts/eval_single_factor.py --factor bp_cs --start 20170101 --end 20241231
python -X utf8 scripts/eval_single_factor.py --factor sp_cs --start 20170101 --end 20241231
```

### Phase D2：技术因子深度诊断

| ID | 任务 | 说明 | 产物 |
|----|------|------|------|
| D2.1 | pv_divergence 纯化测试 | 控制 value (ep_cs) 和 reversal 后的条件 IC | 纯化 IC 表 |
| D2.2 | pv_divergence 窗口测试 | 测试 10/20/40/60 日窗口的 IC 表现 | 窗口对比表 |
| D2.3 | 动量改进方案对比 | 原始动量 vs 行业中性动量 vs 残差动量 vs 夏普比动量 | 方案对比报告 |
| D2.4 | reversal 条件有效性分析 | 仅在 range-bound 市场状态下的 IC 表现（使用事后已知 market state，仅用于诊断） | 条件 IC 表 |
| D2.5 | volatility 风险保护效果测试 | 在下跌月份的低波组合 vs 基准表现 | 风险保护证据 |

关键命令：

```powershell
# 纯化测试
python -c "
# 在控制 ep_cs 和 reversal_5_cs 后计算 pv_divergence_20 的条件 IC
# 使用 OLS: pv_divergence ~ ep_cs + reversal_5_cs，取残差的 IC
"

# 动量改进
python -c "
# 计算四种动量定义在 2017-2024 的 IC/ICIR 对比
# 1. raw: close / close.shift(120) - 1
# 2. ind_neutral: raw 对行业哑变量回归取残差
# 3. residual: raw 对 CSI300 和行业哑变量回归取残差
# 4. sharpe: raw / std(returns, 120)
"
```

### Phase D3：质量/成长因子审计与测试

| ID | 任务 | 说明 | 产物 |
|----|------|------|------|
| D3.1 | ROE 数据覆盖率审计 | 2017-2024 每期覆盖率、缺失模式 | 覆盖率报告 |
| D3.2 | gross_margin 数据覆盖率审计 | 同上。毛利率从利润表可得，覆盖率通常优于 ROE | 覆盖率报告 |
| D3.3 | 审计 PIT 日期使用 | `ann_date` vs `f_ann_date` vs `report_date` | PIT 审计表 |
| D3.4 | 设计缺失填补策略 | 行业中性、前值结转、混合策略对比 | 填补策略文档 |
| D3.5 | 单因子 IC 评估 | 对 PIT 正确的质量/成长因子做完整 IC 评估 | factor report |
| D3.6 | 质量因子组合测试 | ROE + gross_margin + (1-leverage) 等权 vs 单独使用 | 组合测试报告 |

### Phase D4：新因子候选（仅在 D1-D3 完成后）

| ID | 任务 | 经济假设 | 前提 |
|----|------|----------|------|
| D4.1 | 现金流质量因子 | 经营现金流/利润 > 1 的公司质量更高，未来收益更稳定 | D3 基本面数据审计通过 |
| D4.2 | 盈利稳定性因子 | ROE 或毛利率过去 8-12 季度的波动率越低，质量越高 | ROE/gross_margin 可用 |
| D4.3 | 价值+质量复合因子 | ep_cs × (1 + ROE_cs 的 rank) 或等权综合 | D1 + D3 完成 |
| D4.4 | 行业相对动量 | 股票动量 - 所属行业平均动量，纯化行业轮动干扰 | D2.3 动量改进有正面证据 |
| D4.5 | 分析师预期修正（如数据可用） | 盈利预期上修 → 未来正超额 | 需确认数据源 |

**每个新因子在进入候选池前必须通过：**
1. PIT 审计（`future_obs = 0`）
2. 2017-2024 全窗口单因子 IC 评估（满足 §5.1 门槛）
3. no-leakage 单测（`pytest` 中新增）
4. 成本后经济收益测试（考虑换手和冲击成本）

## 5. Alpha 质量门槛与测试体系

### 5.1 因子进入 Alpha 候选池的最低门槛（与 `strategy_next_development_plan.md` §5 对齐）

| 指标 | 门槛 | 测试方法 |
|------|:----:|----------|
| 2017-2024 mean IC | > 0.02 | `CrossSectionEvaluator` 的 Rank IC |
| ICIR | > 0.30 | IC mean / IC std |
| IC 正向率 | > 52% | 按周计算 IC>0 的周数占比 |
| Top-bottom 年化收益（成本前） | > 5% | 多空组合年化收益 |
| Top-bottom 年化收益（成本 2x 后） | > 0% | 扣除双边 0.3% 换手成本 |
| 失败年份贡献集中度 | 不集中在单一年份 | 每年 IC 贡献占比 < 50% |
| PIT 审计 | `future_obs = 0` | 专项审计脚本 |
| 最大单年 IC 为负 | 允许但需解释 | 如仅在 1/8 年为负 → 可接受 |
| 因子自相关 | 1 周自相关 > 0.85 | 确保调仓周期内信号不过快衰减 |

### 5.2 因子升级流程

```text
新因子 idea
    │
    ▼
PIT 审计 (future_obs = 0?)
    ├── ❌ → 修复数据源或 PIT 对齐
    └── ✅
         │
         ▼
单因子 IC 评估 (2017-2024)
    ├── ❌ 未达门槛 → 记录为 D 类（无效），存档假设
    └── ✅ 达到 §5.1 门槛
         │
         ▼
Layer 2 测试（可交易性）
    ├── 换手率测试
    ├── 涨跌停冲击测试
    └── 流动性过滤后 IC 变化
         │
         ▼
Layer 3 测试（穿透力）
    ├── Sleeve 集成测试（IC 加权是否保留信号）
    ├── Phase2 fast Top50 测试（信号→持仓的穿透率）
    └── Phase2 完整回测（2017-2024 全部年份）
         │
         ▼
候选池（可进入 frozen 验证）
```

### 5.3 测试文件要求

每个新因子或修订因子必须新增：

```text
tests/test_factor_{name}_no_leakage.py      # PIT 和 future_obs 测试
tests/test_factor_{name}_coverage.py        # 覆盖率和缺失模式测试
tests/test_factor_{name}_ic_threshold.py    # IC 门槛测试
```

## 6. Sleeve 池重建方案

### 6.1 当前 Sleeve 问题

| Sleeve | 当前因子 | 问题 |
|--------|----------|------|
| reversal | reversal_5, reversal_20, rsi_14, pv_divergence_20 | 核心因子 reversal 自身未过 IC 门槛；RSI 无效 |
| momentum | momentum_60, momentum_120, macd_12_26_9, pv_divergence_20 | 动量因子 disabled 且自身 IC 不足；MACD 无效 |
| defensive | volatility_20, volatility_60, reversal_20 | 低波不是 alpha；reversal_20 无效 |
| value | ep_cs, bp_cs, sp_cs | ✅ 当前最佳 sleeve，但因子全部 disabled |
| volume_price | pv_divergence_20, macd_12_26_9, momentum_60, volatility_20 | MACD/volatility 无效；动量 disabled |

### 6.2 重建后 Sleeve 定义（目标状态）

#### reversal sleeve（重构为"震荡市场条件 sleeve"）

```yaml
# 经济假设：反转效应主要在震荡市中有效
# 使用条件：仅当 regime 判定 range_bound 时启用
# 因子池（精简）：
reversal_sleeve:
  factors:
    - reversal_5_cs        # 保留但降权（如仅 0.5x）
    - pv_divergence_20_cs  # 量价背离在震荡市中同样有效
  condition: range_bound_only  # 仅当 range_bound_prob > threshold
  min_active_factors: 1
```

#### momentum sleeve（重构为"趋势市场动量 sleeve"）

```yaml
# 经济假设：A 股存在中期动量，但需要行业中性化后使用
# 因子池（替换）：
momentum_sleeve:
  factors:
    - residual_momentum_120_cs   # 残差动量（替代原始动量）
    - ind_neutral_momentum_60_cs # 行业中性动量
    - pv_divergence_20_cs        # 保留
  min_active_factors: 1
  # 移除：macd_12_26_9_cs（无效）
```

#### value sleeve（重新启用并增强）

```yaml
# 经济假设：低估值股票长期跑赢高估值，尤其在价值风格回归期
# 因子池：
value_sleeve:
  factors:
    - ep_cs
    - bp_cs
    - sp_cs
    # 候选增强（D4 完成后）：
    # - value_quality_composite_cs  # 价值+质量复合
  min_active_factors: 2  # 至少 2 个有效才参与
```

#### quality sleeve（新建）

```yaml
# 经济假设：高质量公司（高盈利、高稳定性、低杠杆）长期跑赢
# 仅在 D3 审计通过后启用
# 因子池（候选）：
quality_sleeve:
  factors:
    - roe_cs
    - gross_margin_cs
    - earnings_stability_cs   # D4.2
    - cashflow_quality_cs     # D4.1
  min_active_factors: 2
```

#### defensive sleeve（重构为"风险控制 sleeve"）

```yaml
# 经济假设：低波/低回撤在下跌市场中提供保护，但不是 alpha 来源
# 因子池（重构）：
defensive_sleeve:
  factors:
    - volatility_20_cs      # 从 alpha 转为风险信号
    - max_drawdown_60_cs    # 新增：60 日最大回撤（低回撤 = 好）
    - beta_cs               # 新增：市场 beta（低 beta = 好）
  # 此 sleeve 不预期产生正 alpha，目的是降低组合回撤
  alpha_source: false
  risk_control: true
```

#### volume_price sleeve（精简）

```yaml
# 经济假设：量价关系包含主力资金行为信息
# 因子池（精简）：
volume_price_sleeve:
  factors:
    - pv_divergence_20_cs
    # 候选（D2.2 后）：
    # - pv_divergence_40_cs   # 更长窗口量价背离
  min_active_factors: 1
  # 移除：macd_12_26_9_cs, momentum_60_cs, volatility_20_cs
```

### 6.3 Sleeve 重建阶段

| 阶段 | 内容 | 前置 |
|------|------|------|
| S1 | 重新启用 value sleeve（ep/bp/sp PIT 审计后） | D1 完成 |
| S2 | 精简 reversal/volume_price sleeve（移除无效因子） | D2 完成 |
| S3 | 重构 momentum sleeve（使用改进动量） | D2.3 完成 |
| S4 | 重构 defensive sleeve（从 alpha 转为风险控制） | D2.5 完成 |
| S5 | 新建 quality sleeve（质量因子审计和测试后） | D3 完成 |
| S6 | 候选增强因子进入各自 sleeve | D4 完成 |

## 7. Alpha→Sleeve→组合 穿透验证

### 7.1 穿透验证框架

修复 alpha 后必须验证信号能到达最终组合。每一层都要量化"信号衰减"。

```text
Factor IC (Layer 1 输出)
    │
    ▼  衰减来源：IC 加权误差、因子间相关性、sleeve 内部 noise
Sleeve Score IC (Layer 2 输入)
    │
    ▼  衰减来源：Regime 映射权重、overlay multiplier 偏差
Composite Score IC (Layer 2 输出)
    │
    ▼  衰减来源：Top50 截断、等权 vs 强度加权
Fast Top50 收益 (Layer 3 快照)
    │
    ▼  衰减来源：涨跌停、停牌、持仓延续、权重上限、成本
Phase2 完整组合收益 (Layer 3 终点)
```

### 7.2 穿透验证指标

| 指标 | 计算方式 | 期望 |
|------|----------|------|
| Factor→Sleeve 穿透率 | Sleeve Score IC / max(各因子 IC) | > 0.7 |
| Sleeve→Composite 穿透率 | Composite IC / Sleeve Score IC（加权） | > 0.6 |
| Composite→Fast 穿透率 | Fast 多空收益 / Composite IC 隐含收益 | > 0.5 |
| Fast→Phase2 穿透率 | Phase2 超额 / Fast 超额 | > 0.6 |
| 总穿透率 | Phase2 超额 / 理论因子 alpha | > 0.15 |

### 7.3 穿透验证命令

```powershell
# 生成穿透验证报告
python -X utf8 scripts/alpha_transmission_audit.py \
  --strategy E_candidate_v2 \
  --start 20170101 --end 20241231 \
  --output outputs/analysis/alpha_transmission/

# 该脚本应输出：
# 1. 每层 IC 对比
# 2. 每层衰减率
# 3. 按年/按市场状态的分段穿透率
# 4. 衰减最大的环节排名
```

如果该脚本尚不存在，需在 Phase 工程任务中新建。

## 8. 工程任务清单

### 8.1 新增脚本

| 脚本 | 用途 | 优先级 |
|------|------|--------|
| `scripts/audit_factor_pit.py` | 对任意因子做 PIT 审计（`future_obs`、公告日期、数据滞后） | P0 |
| `scripts/eval_single_factor.py` | 对单个因子做完整 Layer 1 评估（IC/ICIR/正向率/分年/分状态） | P0 |
| `scripts/audit_fundamental_coverage.py` | 基本面因子覆盖率和缺失模式审计 | P0 |
| `scripts/test_factor_condition_ic.py` | 计算条件 IC（控制其他因子后） | P1 |
| `scripts/alpha_transmission_audit.py` | 穿透验证：Factor→Sleeve→Composite→Fast→Phase2 | P1 |
| `scripts/build_residual_momentum.py` | 构建残差动量因子 | P1 |
| `scripts/build_quality_factors.py` | 构建质量因子（ROE/gross_margin/cashflow/stability） | P1 |

### 8.2 新增测试

| 测试文件 | 测试内容 | 优先级 |
|----------|----------|--------|
| `tests/test_factor_pit_audit.py` | 所有因子 PIT 审计的自动化测试 | P0 |
| `tests/test_factor_ep_bp_sp_no_leakage.py` | value 因子的 no-leakage 测试 | P0 |
| `tests/test_factor_quality_no_leakage.py` | 质量因子的 no-leakage 测试 | P0 |
| `tests/test_factor_ic_thresholds.py` | 所有候选因子的 IC 门槛自动化检查 | P0 |
| `tests/test_alpha_transmission.py` | 穿透验证的自动化测试 | P1 |

### 8.3 配置变更

| 文件 | 变更 | 阶段 |
|------|------|------|
| `configs/factors.yaml` | 重新启用 ep_cs, bp_cs, sp_cs；禁用 reversal_20_cs, rsi_14_cs, volatility_20_cs, volatility_60_cs, macd_12_26_9_cs | D1/D2 后 |
| `configs/factors_candidate_v2.yaml` | 新建：包含 value + improved momentum + pv_divergence + quality（候选） | S1-S6 后 |
| `configs/regime.yaml` | 更新 sleeve 因子列表，与 factors 保持一致 | S1-S6 后 |
| `configs/regime_candidate_v4.yaml` | 新建：使用重建后 sleeve + 更新 regime 映射 + performance overlay | 全部 D+S 完成后 |

## 9. 执行路线图

### 第一轮：审计与重新启用（预计 2-3 天）

```text
D1.1-D1.3: 基本面因子 PIT/覆盖率审计
D1.4:     修复发现的 PIT 问题
D1.5:     重新启用 value 因子，单年冒烟
D2.1:     pv_divergence 纯化测试
D2.4:     reversal 条件有效性
D2.5:     volatility 风险保护测试
```

产出：
- `docs/alpha_diagnosis_round1_value_pit.md` — value 因子 PIT 审计报告
- `docs/alpha_diagnosis_round1_technical.md` — 技术因子深度诊断报告
- `configs/factors.yaml` 更新（重新启用 value，降级/移除无效技术因子）

### 第二轮：因子改进与新因子（预计 3-5 天）

```text
D2.2:     pv_divergence 窗口优化
D2.3:     动量改进方案对比与选择
D3.1-D3.4: 质量因子审计
D3.5-D3.6: 质量因子单因子评估
D4.1-D4.2: 候选质量因子构建
```

产出：
- `docs/alpha_diagnosis_round2_momentum.md` — 动量因子改进报告
- `docs/alpha_diagnosis_round2_quality.md` — 质量因子审计和评估报告
- 新建/更新的因子构建脚本

### 第三轮：Sleeve 重建与候选配置（预计 2-3 天）

```text
S1-S6:     Sleeve 池逐步重建
穿透验证:    Factor→Sleeve→Composite→Phase2 全链路
候选配置:    factors_candidate_v2.yaml + regime_candidate_v4.yaml
单年冒烟:    2023 年测试
```

产出：
- `docs/alpha_sleeve_reconstruction.md` — Sleeve 重建报告
- `docs/alpha_transmission_audit.md` — 穿透验证报告
- `configs/factors_candidate_v2.yaml`
- `configs/regime_candidate_v4.yaml`

### 第四轮：冻结验证与决策（预计 2-3 天）

```text
全窗口复验:    2017-2024 + 2026 YTD（使用新候选配置）
V2 vs V4 对比: 量化 alpha 修复的边际贡献
GO/NO-GO 决策: 判断是否达到策略门槛
```

产出：
- `docs/candidate_v4_validation.md`
- `docs/candidate_v4_vs_v2_comparison.md`
- 更新的 `docs/go_nogo_decision.md`

## 10. 成功标准

### 10.1 Alpha 层成功标准

| 指标 | 当前状态（E_candidate_v2） | 目标（Alpha 修复后） |
|------|:--------------------------:|:--------------------:|
| 通过 IC 门槛的因子数 | 3（ep/bp/sp，但全部 disabled） | ≥ 6（value 3 + quality 2+ + pv_divergence 1+） |
| 启用因子中通过 IC 门槛的比例 | 1/5（仅 pv_divergence 边际通过） | ≥ 4/8 |
| Factor→Sleeve 穿透率 | 未测量 | > 0.7 |
| Sleeve→Phase2 总穿透率 | 未测量 | > 0.15 |
| Value factor 在成长市场的条件 IC | 负（2019/2020） | 仍可能为负但需有质量/动量因子对冲 |

### 10.2 策略层成功标准（与 `strategy_next_development_plan.md` §6.1 对齐）

| 指标 | E_candidate_v2 当前 | 目标 |
|------|:-------------------:|:----:|
| 2017-2024 平均年化超额 | -1.2% | > 2% |
| 正超额年份 | 3/8 | ≥ 5/8 |
| 平均 IR | -0.21 | > 0.30 |
| 最大单年超额亏损 | -15.8%（2017） | > -10% |
| 2026 YTD | -18.1%（NO-GO） | 不明显反向 |

### 10.3 阶段性 NO-GO 条件

以下情况出现时，应停止当前路线并重新评估：

1. **基本面 PIT 审计发现系统性前视偏差**，且无法通过 `ann_date` / `f_ann_date` 修正。
2. **质量因子覆盖率 < 50%**（即超过一半的股票在任何给定周没有有效质量因子值），且无法通过行业填充或前值结转修复。
3. **Alpha 修复后 E_candidate_v2 在 2017-2024 的多数年份恶化**（而非改善）。
4. **穿透验证发现 Factor→Phase2 衰减 > 90%**（即信号几乎无法到达组合），且衰减主因不是可修复的组合构建问题。

## 11. 与并行工作的协调

### 11.1 与 V3 开发的关系

| 维度 | V3 开发（`strategy_v3_development_plan.md`） | Alpha 修复（本文档） |
|------|----------------------------------------------|---------------------|
| 改进对象 | Overlay 层（sleeve_performance_overlay） | Alpha 层（因子池） |
| 因子池 | 复用 factors_candidate_v1（5 因子） | 重建因子池 |
| Regime 配置 | regime_candidate_v3 | 先用 V2 的 regime 映射，最终汇合到 candidate_v4 |
| 汇合点 | V3 复验完成后 | Alpha 修复完成后，在 candidate_v4 汇合 |

**建议顺序：**
1. 先完成 V3（F_candidate_v3）的复验和对比（预计 1-2 天）
2. 同时启动 Alpha 修复的 D1（基本面 PIT 审计）
3. V3 结论出来后，决定 performance overlay 是否进入 candidate_v4
4. Alpha 修复完成后，形成 candidate_v4（= 重建因子池 + 最终 regime 配置 + 可能的 performance overlay）

### 11.2 与现有候选的关系

| 候选 | 因子配置 | Regime 配置 | 状态 |
|------|----------|-------------|------|
| D_regime_overlay | factors.yaml（5 技术因子） | regime D（less_reversal_faster_overlay） | 基准，不修改 |
| E_candidate_v2 | factors_candidate_v1（5 因子） | regime_candidate_v2 | 当前最佳，不修改 |
| F_candidate_v3 | factors_candidate_v1（5 因子） | regime_candidate_v3（+perf overlay） | 复验中 |
| **G_candidate_v4** | **factors_candidate_v2（重建后因子池）** | **regime_candidate_v4** | **本文档目标产出** |

## 12. 风险与注意事项

1. **基本面数据质量风险。** A 股财务报表的 `ann_date` 和 `f_ann_date` 差异可能导致无意的前视。必须逐因子审计。
2. **质量因子覆盖率风险。** ROE 和毛利率在某些行业（金融）或某些时期（新上市）可能缺失严重。需在审计中量化，并设计合理的填补策略。
3. **动量因子在 A 股的结构性限制。** A 股散户主导、反转效应强，即使改进定义，动量因子的 alpha 也可能有限。如果 D2.3 的四种改进方案都未通过 IC 门槛，应接受动量在 A 股截面中不可用。
4. **不要过度拟合 2023/2025。** 诊断可以使用 2023/2025，但因子定义变更必须基于 2017-2022 的证据。
5. **禁用因子不等于删除代码。** 移除的因子定义和缓存应保留，以便未来复查或回滚。
6. **与 regime router 的交互。** 新因子进入 sleeve 后，regime router 的 sleeve 映射可能需要重新校准。但这应在因子池冻结后再做，不应同时调整。

---

## 附录 A：当前因子定义完整清单

（来源：`configs/factors.yaml` 和因子探索报告）

### 技术因子（13 个）

| 因子名 | 类别 | 窗口 | 方向 | 当前启用 | 分类建议 |
|--------|------|------|:---:|:---:|------|
| reversal_5 | reversal | 5d | + | ✅ | D→条件 |
| reversal_20 | reversal | 20d | + | ✅ | D |
| momentum_60 | momentum | 60d | + | ❌ | B（改进后） |
| momentum_120 | momentum | 120d | + | ❌ | B（改进后） |
| volatility_20 | volatility | 20d | - | ✅ | C |
| volatility_60 | volatility | 60d | - | ❌ | D |
| ivol_20 | volatility | 20d | - | ❌ | C |
| turnover_5 | liquidity | 5d | - | ❌ | C |
| abnormal_turnover_20 | liquidity | 20d | - | ❌ | C |
| pv_divergence_20 | price_volume | 20d | + | ✅ | B |
| rsi_14 | oscillator | 14d | - | ✅ | D |
| macd_12_26_9 | oscillator | 26d | + | ❌ | D |
| abnormal_drop_reversal_5 | shock | 5d | N/A | ❌ | 专项 |

### 基本面因子（8 个）

| 因子名 | 类别 | 方向 | 当前启用 | 分类建议 |
|--------|------|:---:|:---:|------|
| ep | value | + | ❌ | A |
| bp | value | + | ❌ | A |
| sp | value | + | ❌ | A |
| roe | quality | + | ❌ | 未诊断 |
| gross_margin | quality | + | ❌ | 未诊断 |
| revenue_growth | growth | + | ❌ | 未诊断 |
| profit_growth | growth | + | ❌ | 未诊断 |
| leverage | risk | - | ❌ | C |

### 中性化因子（1 个）

| 因子名 | 类别 | 方向 | 用途 |
|--------|------|:---:|------|
| log_market_cap | size | - | 仅用于截面中性化 |

## 附录 B：关键命令速查

```powershell
# === 诊断命令 ===

# PIT 审计
python -X utf8 scripts/audit_factor_pit.py --factor ep_cs --start 20170101 --end 20241231
python -X utf8 scripts/audit_factor_pit.py --factor roe_cs --start 20170101 --end 20241231

# 单因子评估
python -X utf8 scripts/eval_single_factor.py --factor ep_cs --start 20170101 --end 20241231 --output outputs/analysis/factor_diag/
python -X utf8 scripts/eval_single_factor.py --factor residual_momentum_120_cs --horizon 5 --output outputs/analysis/factor_diag/

# 覆盖率审计
python -X utf8 scripts/audit_fundamental_coverage.py --factor roe_cs --start 20170101 --end 20241231

# 条件 IC（控制其他因子后）
python -X utf8 scripts/test_factor_condition_ic.py --target pv_divergence_20_cs --controls ep_cs reversal_5_cs

# === 穿透验证 ===
python -X utf8 scripts/alpha_transmission_audit.py --strategy E_candidate_v2 --start 20170101 --end 20241231

# === 冒烟测试 ===
python -X utf8 scripts/frozen_backtest_validation.py --strategies G_candidate_v4 --years 2023 --force

# === 全窗口复验 ===
python -X utf8 scripts/frozen_backtest_validation.py --strategies G_candidate_v4 --force
```

---

本文档应与以下文档协同阅读：
- `docs/strategy_next_development_plan.md` — 总体开发框架和阶段划分
- `docs/strategy_v3_development_plan.md` — V3 performance overlay 开发方案
- `docs/failure_year_monthly_attribution.md` — D_regime_overlay 失败归因
- `docs/go_nogo_decision.md` — 当前 GO/NO-GO 决策状态
- `docs/factor_signal_alignment.md` — 因子信号口径统一（待产出）

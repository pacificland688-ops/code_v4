# 光刻胶主题恐慌修复开发方案

## 1. 目标

开发一个“光刻胶主题恐慌修复研究模块”，用于回答三个问题：

1. 光刻胶主题恐慌事件后，主题篮子是否存在可重复的修复效应。
2. 在只能买一只股票的账户约束下，top1 单票规则能否稳定捕捉该修复。
3. 只有主题篮子与 top1 单票路径同时通过验证时，才进入候选交易策略。

核心原则：

- 事件定义独立冻结。
- basket 和 top1 并行验收。
- 不能用 top1 表现反向调整 panic gate。
- 不能用当前产业认知污染历史股票池。
- 必须处理涨停买不到、跌停卖不出、停牌、跳空滑点和交易成本。

## 2. 预期开发产物

新增配置和脚本：

```text
configs/photoresist_universe.yaml
configs/photoresist_panic_research.yaml
scripts/build_photoresist_panic_events.py
scripts/evaluate_photoresist_panic_reversal.py
tests/test_photoresist_panic_events.py
tests/test_photoresist_panic_execution.py
```

输出目录：

```text
outputs/analysis/photoresist_panic/
  photoresist_universe_snapshot.csv
  photoresist_basket_daily.csv
  photoresist_panic_events.csv
  photoresist_forward_returns.csv
  photoresist_top1_trades.csv
  photoresist_contribution_diagnostics.csv
  photoresist_leave_one_out.csv
  photoresist_robustness.csv
  photoresist_panic_report.md
```

## 3. 股票池设计

股票池必须 point-in-time 化，采用粗分层，不做伪精确打分。

### 3.1 分层

```text
core:
  半导体光刻胶明确相关，进入核心篮子。

adjacent:
  显示光刻胶、PCB 光刻胶、泛感光材料，进入 broad 篮子，但不进入核心篮子。

mapping:
  半导体材料映射、产业链相关或概念弱相关，只做情绪观察，不进入核心篮子。
```

### 3.2 股票池字段

```text
ts_code
name
pool_type: core / adjacent / mapping
effective_start
effective_end
source_type: annual_report / announcement / concept_pit / manual_review
source_ref
pit_confidence: high / medium / low
```

主回测只使用 `pit_confidence != low` 的 `core` 股票。`market_perceived_pool` 只有在来源可审计、时间可追溯时才进入辅助回测；如果来源来自当前概念标签、事后研报或人工回忆，只能用于人工复盘，不能进入主回测。

## 4. 篮子构建

构建三类日度序列：

```text
core_basket:
  core 股票等权，单票权重上限 30%。

broad_basket:
  core + adjacent，core 权重优先，adjacent 降权。

mapping_sentiment_index:
  mapping 股票只做观察，不作为事件主依据。
```

每日输出字段：

```text
trade_date
basket_name
basket_ret_1d
basket_ret_3d
basket_ret_5d
basket_ret_10d
down_stock_ratio
median_amount_ratio_20d
large_drop_ratio
limit_down_ratio
limit_up_ratio
tradable_count
component_count
```

## 5. 基准指数

至少保留三类基准：

```text
market_benchmark:
  沪深300 / 中证全指 / 中证1000

growth_benchmark:
  创业板指 / 科创创业50

semiconductor_benchmark:
  中证半导体产业指数 931865，或本地可用半导体指数
```

核心比较对象是 `semiconductor_benchmark`，但它只能作为半导体大主题风险因子，不能替代光刻胶篮子本身。

## 6. 主事件定义

主 gate 只设一套，并在研究开始前冻结。

```text
panic_gate =
    core_basket_ret_5d < 0
    AND (
        core_basket_ret_5d <= -5%
        OR core_basket_ret_5d <= rolling_3y_quantile_10%
    )
    AND core_down_stock_ratio_5d >= 50%
```

gate 成立后再计算分层 score，不使用复杂连续权重作为第一版主定义。

## 7. 分层 panic score

每类只保留一个主指标，避免高度相关变量重复计分。

```text
severity_score:
  5日跌幅 <= -8%，或进入滚动3年最差5%。

breadth_score:
  下跌股票占比 >= 70%。

volume_score:
  成分股 amount_ratio_20d 中位数 >= 1.2。

relative_score:
  core_basket 相对半导体指数5日超额 <= -3%。

stress_score:
  单日跌幅超过7%的股票占比 >= 25%，或跌停压力显著。
```

事件强度：

```text
normal_panic:
  panic_gate 成立，score >= 2。

strong_panic:
  panic_gate 成立，score >= 3。

extreme_panic:
  panic_gate 成立，score >= 4。
```

辅助 gate 只保留 2 到 3 套 robustness 版本，必须报告所有结果，不允许只挑表现最好的一套。

## 8. 事件分类

事件环境分两类：

```text
semiconductor_systematic_panic:
  半导体指数同步大跌，光刻胶跟跌。

photoresist_specific_panic:
  半导体指数未明显恐慌，但光刻胶显著跑输。
```

个股 residual 不作为事件层，而作为选股和风控变量：

```text
stock_residual = stock_ret_5d - core_basket_ret_5d
```

分桶：

```text
mild_residual
medium_residual
severe_residual
limit_or_liquidity_stress_residual
```

重度 residual 默认先作为风险变量。只有在无跌停、无流动性枯竭、无结构化公告利空命中时，才进入单独分组测试。

## 9. Top1 单票规则

第一阶段并行测试四类 top1，不能根据结果反向调整事件定义。

```text
top1_strength:
  事件后在 core 池中选择相对 core_basket 最强、流动性合格的一只。

top1_mid_drop:
  选择跌幅居中、未跌停、未流动性失控的一只。

top1_liquidity_core:
  选择 core 池中20日成交额最高且满足事件下跌条件的一只。

top1_residual_bucket:
  在 residual 分桶中测试轻度、中度、重度 residual 的表现。
```

资格过滤：

```text
非 ST
非停牌
上市满 120 个交易日
过去20日日均成交额 >= 1亿，可参数化
事件日未封死跌停
买入日未一字涨停或不可成交
无连续跌停
```

`无明显利空` 不能进入主回测，除非已经有结构化公告数据，并且公告时间可 point-in-time 追溯。

## 10. 交易执行

所有交易必须 lag1。

```text
事件日 t 收盘后识别；
最早 t+1 成交；
如果使用修复确认，确认日 s 收盘后识别，最早 s+1 成交。
```

测试两组入场：

```text
direct_entry:
  事件后 t+1 直接入场。

confirmation_entry:
  事件后5日内首次出现：
    core_basket 当日上涨
    上涨股票占比 >= 50%
    候选股跑赢 core_basket
  则下一交易日入场。
```

退出规则：

```text
固定持有 5 / 10 / 20 个交易日。
辅助测试止盈 +8% / +12%。
辅助测试止损 -5% / 跌破事件低点。
```

交易约束：

```text
涨停买不到
跌停卖不出
停牌不可交易
开盘跳空滑点
20bp / 50bp / 100bp 成本敏感性
```

## 11. 评估指标

### 11.1 Basket 侧

```text
事件数量
事件簇数量
1/3/5/10/20日 forward return
相对半导体指数超额
胜率
按年份表现
按系统性恐慌 / 细分异常恐慌分组表现
```

### 11.2 Top1 侧

```text
成本后收益
胜率
最大不利波动 MAE
最大有利波动 MFE
单票交易次数
单票收益贡献占比
涨跌停处理后收益
停牌处理后收益
```

### 11.3 集中度诊断

```text
top_contributor_share
single_stock_trade_share
single_stock_pnl_share
leave-one-stock-out
leave-one-year-out
```

## 12. Go / No-Go

分三层判断。

### 12.1 event_GO

```text
basket 成本前后均显示修复倾向；
年份稳定性过半；
leave-one-stock-out 后不完全失效。
```

### 12.2 top1_GO

```text
至少一套预设 top1 规则成本后为正；
不是单一股票贡献；
涨跌停和停牌处理后结论不反转。
```

### 12.3 trade_GO

```text
event_GO 和 top1_GO 同时成立；
参数轻微变化不反转；
样本不是集中在单一年份或单一 regime。
```

失败分类：

```text
basket 有效，top1 无效:
  主题事件存在，但单票账户暂不可交易。

basket 无效，top1 有效:
  高度怀疑单票偶然或过拟合。

basket 无效，top1 无效:
  No-Go。

basket 有效，top1 有效:
  进入候选策略池。
```

## 13. 开发顺序

```text
Phase 1:
  数据盘点和 PIT 股票池配置。

Phase 2:
  构建 core / broad basket 日度序列。

Phase 3:
  生成 panic_gate 和 panic_score 事件表。

Phase 4:
  计算 basket forward return 和事件分组。

Phase 5:
  实现 top1 规则和交易执行约束。

Phase 6:
  输出集中度、leave-one-out、成本敏感性。

Phase 7:
  生成 markdown 报告。

Phase 8:
  补充测试，冻结主 gate 和辅助 gate 结果。
```

## 14. 测试要求

至少覆盖：

```text
PIT 股票池不使用 effective_start 之前的成分。
core / adjacent / mapping 分层不会互相污染。
panic_gate 在收益未明显下跌时不会误触发。
panic_score 只在 panic_gate 成立后计算事件强度。
事件识别和交易成交严格 lag1。
确认入场不会使用确认日收盘后同日成交。
涨停不可买入、跌停不可卖出、停牌不可交易。
leave-one-stock-out 输出完整。
top1 结果不会反向影响事件定义。
```

## 15. 主要风险

```text
样本过少，事件簇不足。
股票池 point-in-time 证据不足。
光刻胶主题被半导体 beta 或小盘成长 beta 淹没。
篮子收益由单一龙头贡献。
top1 结果来自单票偶然性。
涨跌停和停牌处理后收益反转。
主 gate 或辅助 gate 参数轻微变化后结论反转。
```

## 16. 最终原则

这项研究不以找到漂亮参数为目标，而以排除不可交易假象为目标。

最终判断必须同时满足：

```text
事件定义独立冻结；
basket 证明主题修复存在；
top1 证明单票账户可捕捉；
PIT 股票池和交易约束不引入未来函数；
集中度和 leave-one-out 不显示结果完全依赖单一股票或单一年份。
```

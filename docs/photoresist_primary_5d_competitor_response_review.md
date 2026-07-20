# primary_5d 竞争对手再反驳评审与正式裁决

## 1. 文档目的

本文审查竞争对手针对光刻胶恐慌修复正式开发方案的再反驳，明确应采纳的批评、需要修正的过度推断、primary_5d 的冻结边界，以及 Phase 0 和 Top1 的硬性退出条件。

本文是正式评审裁决，不覆盖既有阈值验证方案，也不代表策略已经可以实盘。

## 2. 总体结论

本轮反驳迫使方案正面回答两个此前处理不足的问题：

```text
1. 4只核心股中剔除1只后结论反转，还能否称为板块共同效应？
2. 如果Top1长期失败，研究何时必须终止？
```

修正后的总判断是：

> 当前不能声称已经证明稳健的光刻胶板块恐慌修复效应。此前的 Layer 1 应从 Statistical Event Effect 降级为“固定股票池篮子统计现象，尚待共同性和可交易性验证”。

但以下推断仍然过强：

```text
1. LOO反转不能单独证明信号不存在，只能证明成分稳健性未通过。
2. 2024或2025任一年度均值为负就立即终止，在每年仅数个事件时过度依赖噪声。
```

当前正式状态：

```text
primary_5d_formula: FROZEN
retrospective_last_trigger_research: DESCRIPTIVE_ONLY
sector_common_reversal_effect: UNPROVEN
live_first_trigger_effect: NOT_TESTED
tradable_basket_effect: NOT_TESTED
top1_capture: FAILED_CURRENT_RULES
account_trade: NO_GO
```

## 3. 最后触发日偏差

### 3.1 共识

当前历史研究把间隔不超过5个交易日的触发合并为事件簇，并用最后一个触发日作为 event_date。该时点需要等待未来数据才能确认，因此不能用于实时交易。

必须区分：

```text
panic_gate:
  当日是否触发 primary_5d，当日收盘即可计算。

retrospective_episode_date:
  事后确认的最后触发日，只用于历史事件整理。

live_signal_date:
  在线状态机中的首次触发日，用于正式可交易性验证。
```

### 3.2 对“偏差必然向上”的修正

最后触发日很可能形成乐观偏差，但不是数学必然：

1. 最后触发日不一定是事件最低点。
2. primary_5d 是滚动5日收益条件，不是当日创新低条件。
3. 市场可能反弹后仍因滚动窗口较差而再次触发。
4. 最后触发日后仍可能继续下跌。
5. 延后入场同时延后退出，收益差不只由入场价格决定。

准确结论是：最后触发日存在明确的事后时点选择，在均值回归策略中很可能形成乐观偏差；偏差方向和幅度必须通过 first-trigger 与 last-trigger 的逐事件配对检验确认。

Phase 0 必须输出：

```text
first_trigger_date
last_trigger_date
first_trigger_entry_price
last_trigger_entry_price
first_trigger_forward_return
last_trigger_forward_return
entry_price_difference
forward_return_difference
episode_low_date
first_trigger_to_low_drawdown
```

若 first-trigger 明显失效，则在线版本直接失败，不能继续用 last-trigger 结果支撑实盘开发。

## 4. 四只核心股与 LOO 反转

当前核心池只有晶瑞电材、南大光电、彤程新材、上海新阳。剔除彤程新材后，20日篮子结果转负。

这至少证明：当前结果尚未通过跨核心成分共同性检验，因此不能称为稳健的光刻胶板块修复效应。

此前 Layer 1 应改名为：

```text
Fixed-Universe Basket Pattern Under Audit
固定股票池篮子统计现象，尚待共同性验证
```

### 4.1 LOO 反转不能单独证明“信号不存在”

LOO 反转否定的是成分稳健的板块共同效应，但不能单独否定当前固定 PIT 篮子的历史条件性现象：

1. 彤程新材自2020年才进入 PIT 核心池，并非全历史固定25%权重。
2. 删除彤程新材不仅删除收益贡献，也改变篮子构成和有效事件。
3. 删除1只等于结构性重定义一个4只股票的篮子，不是微小扰动。
4. LOO 不能区分彤程是主题主要载体，还是偶然历史赢家。

### 4.2 必须新增的共同性诊断

对每个事件计算：

```text
事件后上涨股票占比
事件后跑赢931865.CSI的股票占比
个股事件后收益中位数
个股相对半导体超额中位数
个股事件收益的截面离散度
彤程新材与其他3只股票的事件收益相关性
彤程新材对篮子总收益的贡献占比
不含彤程时其他3只股票的方向一致性
```

板块共同效应至少应满足：

```text
median_stock_excess_20d > 0
AND majority_positive_ratio > 50%
AND majority_excess_positive_ratio > 50%
AND top_contributor_share 不超过冻结上限
AND 剔除任一股票后不发生全面方向反转
```

若均值为正，但中位数、多数上涨比例和多数超额不成立，应定性为 leader_driven_rebound，不能称为板块共同修复。

## 5. 防止四层体系成为研究逃逸舱

如果长期保持 Layer 1 有统计现象、Layer 2 不可交易、Layer 3 无法选股、Layer 4 账户不能执行，却不断开发新规则，分层就会退化成无限研究许可证。

### 5.1 Layer 1 必须可证伪

Layer 1 不能只看等权篮子均值，至少应同时检查：

```text
非重叠事件结果
相对半导体超额
个股中位数超额
多数成分方向一致性
收益贡献集中度
年份集中度
严格placebo
```

共同性检验失败时，sector_common_effect 必须标记为 FAILED。

### 5.2 下游失败必须降低策略研究优先级

应区分 scientific_status 与 strategy_status。允许保留：

```text
fixed_basket_pattern = OBSERVED
top1_capture = FAILED
single_stock_strategy_status = TERMINATED
```

即保留研究记录，但停止把它作为单票策略继续开发。

## 6. Phase 0 的性质与硬门槛

Phase 0 不是最终生产验收，而是决定是否值得进入 Top1 开发的硬性淘汰测试。primary_5d 是低频板块事件信号，不适合用传统 Rank IC、ICIR 作为主要标准；但原先“不转为明显负值”等表述确实必须量化。

### 6.1 Phase 0 主口径

```text
在线 first-trigger
bull/neutral 冻结候选状态
事件日可交易 basket
20日非重叠持有样本
100 bps 往返成本
相对 931865.CSI 超额
```

### 6.2 必须全部满足的继续开发条件

1. first-trigger 20日成本后平均收益大于0。
2. first-trigger 20日相对半导体平均超额大于0。
3. 非重叠事件收益中位数大于0。
4. 非重叠事件超额收益中位数大于0。
5. 超额胜率大于55%。
6. 严格 placebo p-value 小于等于0.10。
7. 个股超额收益中位数大于0。
8. 超过50%的核心股票在多数事件中呈正超额。
9. 剔除任一股票后不得从正向转为明显负向。
10. 2024和2025必须分别报告。

第9项建议冻结为：

```text
每个LOO组合的20日平均超额 >= -50 bps
```

最低经济幅度：

```text
20日平均成本后收益 >= 2%
20日平均相对半导体超额 >= 1%
```

若只是100 bps成本后略高于零、超额接近零或收益由单一股票贡献，则 Phase 0 失败。

### 6.3 年度门槛

不采纳“2024或2025任一年均值为负即终止”的绝对规则，因为每年只有少量非重叠事件，一个异常值可能决定年度均值。

采用：

```text
2024和2025不得同时为负
任一年度成本后平均收益不得低于 -3%
任一年度相对半导体超额不得低于 -2%
两年合并非重叠收益和超额必须为正
单一年份收益贡献不得超过总收益的70%
最差年度回撤必须在冻结风险预算内
```

具体阈值必须在查看 first-trigger 结果前冻结。

## 7. First-trigger 失败时的处理

Phase 0 可能直接否定整个单票开发方向。若 last-trigger 有效而 first-trigger 无效，说明历史结果依赖事后识别恐慌结束。

终止条件：

```text
若 first-trigger 在非重叠、bull/neutral、100 bps成本口径下：
  平均收益 <= 0
  OR 相对半导体超额 <= 0
  OR 严格placebo p-value > 0.10
则终止当前 primary_5d 单票开发。
```

不得通过等待确认、第二次触发或新增技术指标继续修改同一版本。任何新经济假设必须登记为新候选，并受版本上限控制。

## 8. 在线冷却状态机

状态机必须在结果出来前冻结。主版本采用 IDLE、ACTIVE、COOLDOWN。

### IDLE

```text
primary_5d 首次触发：
  记录 live_signal_date
  t+1按冻结执行规则入场
  转入ACTIVE
```

### ACTIVE

```text
固定持有期内：
  不加仓
  不换股
  不因更强触发重新入场
  更强触发只记录为 episode_intensity
```

允许更强触发换仓会增加择时自由度，并重新引入事后挑选低点的风险。

### COOLDOWN

```text
退出后必须连续5个交易日 primary_5d=False 才返回IDLE。
冷却期间再次触发则重置冷却计数，不产生新交易。
冷却结束后的下一交易日再次触发，视为新episode。
```

主版本冻结 cooldown=5。3日和10日只做事件计数敏感性分析，不得按收益挑选主参数。

## 9. Phase 0 通过后进入 Top1 的证据基础

Phase 0 必须证明：在线可复现、可交易、较高成本下，主题层面存在具有横截面共同性的正向超额。

只有同时满足以下条件才进入 Top1：

```text
效应不依赖最后触发日
效应不依赖不可交易成分
效应不依赖单一股票
效应不只是半导体Beta
效应在100 bps成本后仍有足够经济幅度
多数核心成分方向一致
```

## 10. Top1 开发上限和退出规则

### 10.1 版本预算

```text
最多允许2个正式Top1候选版本
每个版本最多3套预登记规则
不允许在同一历史区间无限重写
所有失败版本永久保留
```

### 10.2 Top1 成功标准

至少一套规则满足：

```text
bull/neutral 非重叠交易
100 bps往返成本后平均收益 > 0
收益中位数 > 0
相对半导体超额 > 0
前向样本方向稳定
单一股票收益贡献 < 50%
剔除任一股票后不转为明显负值
最大回撤在冻结预算内
```

### 10.3 强制终止条件

满足任一条件即终止单票方向：

1. 两个正式 Top1 版本均失败。
2. 所有规则在100 bps往返成本后非正。
3. 所有正收益规则均由单一股票贡献超过50%。
4. 冻结后的前向样本达到预设数量后仍无正超额。
5. Phase 0 后续滚动监控失效。

终止后不开发 Top1 v3/v4，不重新挑 primary_5d 阈值，不更换市场状态直到下一个独立研究周期。保留为描述性主题监控，并建议调整“只能买一只”的账户约束或放弃该方向。

## 11. 低频信号的用途边界

当前 bull/neutral 非重叠事件合计约26个，年均约3次。它不适合高频因子、高自由度机器学习、依赖大量交易快速收敛或要求逐年统计显著。

即使未来通过，也只能定位为：

```text
低频事件驱动信号
主题仓位辅助择时
人工复核候选
与其他独立信号组合后的触发条件
低容量、低风险预算策略
```

低频不等于无效，但意味着学习速度慢、单笔影响大，不适合作为账户主策略。

## 12. 最终裁决

### 12.1 应采纳的竞争对手意见

1. 当前 Layer 1 被保护得过度，应降级为待验证的固定篮子现象。
2. LOO 反转是阻断板块共同效应结论的重要证据。
3. Phase 0 必须设置明确、量化且有经济幅度的硬门槛。
4. first-trigger 失败必须能够直接终止单票开发。
5. cooldown 状态机必须预先冻结。
6. Top1 必须有版本上限和明确退出条件。

### 12.2 需要反驳或修正的意见

1. LOO 反转不能单独证明信号不存在，只能证明成分共同性未通过。
2. 最后触发日很可能乐观，但不能未经配对检验就断言偏差必然向上。
3. 低频事件策略不适合用传统截面 IC/ICIR 作为主验收标准。
4. 任一单年均值为负即终止，在每年仅数个事件时过度依赖噪声。
5. 低频不等于无效，但只适合低容量、低风险的辅助用途。

### 12.3 当前冻结边界

```text
primary_5d gate formula: FROZEN
retrospective episode event date: DESCRIPTIVE_ONLY
live first-trigger event: NOT_TESTED
sector common effect: UNPROVEN
tradable basket: NOT_TESTED
Top1 current rules: FAILED
Trade: NO_GO
```

### 12.4 下一步唯一合理工作

下一步不是继续优化 Top1，而是执行 Phase 0 硬性淘汰测试：

> 检验首次在线触发、可交易成分、bull/neutral、非重叠持有、100 bps往返成本和相对半导体超额下，是否同时通过收益幅度、严格placebo、成分共同性与年度风险门槛。

若任一核心门槛失败，则终止 primary_5d 的单票策略开发，不进入 Top1。

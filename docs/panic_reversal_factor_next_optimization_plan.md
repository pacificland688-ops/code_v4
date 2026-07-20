# Panic Reversal 因子后续优化方向与开发方案

## 1. 当前结论

本文档针对 `panic_drop_rev5_t05_bin_weekly_cs` 及其 A/B 事前预测器的后续优化制定方案。本文只描述后续优化内容、方向、原因、验证口径和验收标准，不包含代码实现。

当前已验证产出位于：

- `outputs/analysis/panic_reversal_gate/ab_pretrade_v2/panic_ab_pretrade_v2_manifest.json`
- `outputs/analysis/panic_reversal_gate/ab_pretrade_v2/panic_ab_pretrade_v2_report.md`
- `outputs/analysis/panic_reversal_gate/ab_pretrade_v2/panic_ab_pretrade_v2_strategy_compare.csv`
- `outputs/analysis/panic_reversal_gate/ab_pretrade_v2/panic_ab_pretrade_v2_diagnostics.csv`

当前 v2 结论为：

- `status`: `NO_PREDICTIVE_POWER`
- `production_eligible`: `false`
- `recommended_next_action`: `do_not_integrate; use diagnostics only`
- 主策略：`date_rank_top_10pct`
- 特征集：`price_only`
- 泄露控制：`label_available_plus_embargo`
- embargo：20 个交易日

核心指标：

- 平均 AUC：`0.6699`
- 主策略平均 A-rate lift：`+0.0033`
- 主策略平均 net spread lift：`-0.0032`
- 改善窗口：`1/3`
- 最小覆盖率：约 `10.05%`

因此，当前不能将该 A/B 预测器作为实盘过滤器、组合权重输入或个股选择器。

## 2. 因子本身的含义

`panic_drop_rev5_t05_bin_weekly_cs` 是一个价格技术事件因子，不是普通连续 alpha。

构造逻辑：

1. 对每只股票计算 5 日动量：

   ```text
   mom5 = adj_close_t / adj_close_{t-5} - 1
   ```

2. 当 `mom5 <= -0.05` 时，认为股票发生一次短期恐慌下跌事件。
3. 二值版本中：

   ```text
   event = 1.0
   non-event = 0.0
   ```

4. 当前主研究对象为周频版本，即在重平衡频率上保留事件信号。

它表达的是：某只股票在短期内发生了明显下跌，后续可能出现反弹、止跌或继续下杀。这个因子更像“事件触发器”，不是用来每天给全部股票排序的常规截面因子。

## 3. 为什么当前结果不能直接用于选股

当前模型有 A/B 分类信号，但不能证明它能稳定做个股选择。

已观察到的现象：

- 全局 `p_A` 分层较强，说明模型能区分不同市场环境下事件更容易成为 A 类还是 B 类。
- 但按同一天内部排序的 `date_rank_top_10pct` 效果很弱，甚至在部分年份伤害收益。
- `date_rank_top_10pct` 的平均 A-rate lift 只有 `+0.0033`，远低于可交易要求。
- `date_rank_top_10pct` 的平均 net spread lift 为 `-0.0032`，说明扣除基础成本口径后没有增益。
- 2022、2023、2024 三个有效窗口中只有 1 个窗口改善。

原因判断：

1. 模型最强的信息可能来自“跨日期概率水位”，而不是“同一天内哪只股票更好”。
2. `date_rank_top_10pct` 会把跨日期水位抹掉，只保留日内截面排序，所以把模型最有价值的部分去掉了。
3. 恐慌事件本身高度依赖市场状态。同一只股票是否反弹，往往取决于当时市场是否进入修复环境，而不是单只股票事件强弱。
4. 在 2024 这类 raw events 本身收益已经很好的年份，过度过滤反而可能排除高收益事件。
5. 固定阈值策略在部分年份表现更强，但覆盖率和阈值稳定性不足，不能直接作为上线依据。

结论：当前方向不应继续把它当作“个股选择器”强化，而应转为“恐慌事件篮子/市场状态门控”研究。

## 4. 后续优化总方向

后续优化应从以下目标重新定位：

```text
从：在同一天的恐慌股票里挑个股
转为：判断某一天或某一阶段是否适合参与恐慌下跌反转篮子
```

也就是说，重点不再问：

```text
今天这些 panic drop 股票里，哪 10% 最好？
```

而是问：

```text
今天的市场状态是否适合做 panic drop reversal？
今天这一批 panic drop 事件整体更像 A 路线还是 B 路线？
应当允许参与、降低仓位，还是完全阻断？
```

推荐的新研究产品形态：

- `panic_basket_daily_gate`
- 输出状态：`ALLOW` / `REDUCE` / `BLOCK`
- 作用范围：恐慌事件篮子或 panic reversal sleeve
- 不直接输出个股权重
- 不替代原组合模型
- 作为事件策略的日级风险开关或仓位门控

## 5. 优化方向一：从个股级预测改为日期级门控

### 5.1 要做什么

构建日级样本，而不是股票级样本。

每个交易日生成一条样本，描述当天市场里的 panic drop 事件状态，例如：

- 当天 panic drop 股票数量
- panic drop 股票占可交易股票比例
- panic drop 股票平均 5 日跌幅
- panic drop 股票跌幅分位数
- panic drop 股票行业分布
- panic drop 股票市值分布
- panic drop 股票流动性分布
- panic drop 股票后续 20 日平均收益
- panic drop 股票后续 20 日 A 类比例

模型目标从预测单个股票 A/B，改为预测当天 panic basket 是否值得参与。

### 5.2 为什么要做

当前结果显示，模型的有效信息更像“日期层面的环境信息”。

如果某一天市场整体修复，很多 panic drop 股票都会表现较好；如果某一天处于下跌加速或流动性收缩阶段，单个股票即使看起来跌得多，也可能继续走 B 路线。

因此，后续优化应先判断“哪一天适合做这个事件”，再考虑是否需要细化到股票层面。

### 5.3 推荐标签

建议同时设计多个日级标签，避免单一标签误导：

- `basket_mean_fwd_ret_20d`: 当天全部 panic drop 事件未来 20 日平均收益
- `basket_net_fwd_ret_20d`: 扣除交易成本后的未来 20 日平均收益
- `basket_a_rate_20d`: 当天 panic drop 事件中 A 类事件占比
- `basket_win_rate_20d`: 当天 panic drop 事件未来 20 日正收益比例
- `basket_top_half_ret_20d`: 当天按原始事件强度或已有模型分数筛选后，前半部分事件的平均收益

主标签建议使用：

```text
basket_net_fwd_ret_20d > 0
```

或：

```text
basket_a_rate_20d > rolling_train_median
```

选择原因：

- `basket_net_fwd_ret_20d > 0` 更贴近交易可用性。
- `basket_a_rate_20d > rolling_train_median` 更贴近 A/B 路线识别。
- 两者同时看，可以区分“分类正确但收益不够”和“收益有效但分类定义不稳定”。

## 6. 优化方向二：保留跨日期概率水位

### 6.1 要做什么

新方案中不能只使用日内排名，需要显式保留跨日期水平。

建议增加这些特征：

- 当天全部事件的 `p_A` 均值
- 当天全部事件的 `p_A` 中位数
- 当天全部事件的 `p_A` 75 分位数
- 当天全部事件的 `p_A` 90 分位数
- 当天 `p_A > 0.5` 的事件占比
- 当天 `p_A > 0.6` 的事件占比
- 当天 `p_A` 的离散度
- 当天 `p_A` 与过去 60 日自身分位数

### 6.2 为什么要做

当前 v2 的核心矛盾是：

- 全局分数分层看起来有效。
- 日内排序策略效果很弱。

这说明模型可能不是在同一天内挑股票，而是在识别某些日期整体更容易出现 A 路线。

如果继续使用 `date_rank_top_10pct`，就会把最关键的跨日期概率水位消除。后续必须保留 `p_A` 的绝对水平、历史分位和日级聚合信息。

## 7. 优化方向三：加入市场状态特征

### 7.1 要做什么

在日级 gate 中加入市场层面的价格、波动、宽度和流动性特征。

建议特征分组如下。

市场收益特征：

- 中证全指、沪深 300、中证 500、中证 1000 的 1 日、3 日、5 日、20 日收益
- 指数距离 20 日低点的位置
- 指数 20 日回撤
- 指数 5 日反弹幅度

市场宽度特征：

- 全市场上涨股票占比
- 全市场 5 日上涨股票占比
- 创 20 日新低股票占比
- 跌破 20 日均线股票占比
- 涨停/跌停家数
- 大跌股票占比，例如单日跌幅超过 5% 的股票占比

波动和冲击特征：

- 指数 5 日、10 日、20 日波动率
- 波动率短长比，例如 `vol_5d / vol_20d`
- 横截面收益离散度
- panic drop 事件数量相对过去 60 日分位

流动性特征：

- 全市场成交额变化
- panic 事件股票成交额变化
- panic 事件股票换手率变化
- 小市值 panic 事件占比
- 低流动性 panic 事件占比

行业扩散特征：

- panic 事件覆盖行业数量
- panic 事件最集中行业占比
- 行业间 panic 事件数量的 Herfindahl 指数
- 周期、消费、科技、金融等大类行业 panic 分布

### 7.2 为什么要做

恐慌下跌反转是否有效，通常取决于事件所处的市场环境。

同样是 5 日下跌超过 5%：

- 如果市场已经进入过度恐慌后修复，反转概率更高。
- 如果市场处于趋势性下杀初期，继续下跌概率更高。
- 如果 panic 事件集中在少数行业，可能是行业冲击。
- 如果 panic 事件扩散到全市场，可能是系统性风险。
- 如果成交额萎缩，反弹承接不足。
- 如果成交额放大且宽度改善，可能说明资金回流。

因此，仅靠个股自身过去价格路径很难稳定判断 A/B 路线。

## 8. 优化方向四：重新定义 A/B 路线

### 8.1 要做什么

当前 A/B 定义基于事件后收益路径，但后续需要明确 A/B 的交易含义。

建议至少保留三套标签并行比较：

1. 收益型 A/B：

   ```text
   A = 未来 20 日收益 >= retention_threshold
   B = 其他
   ```

2. 净收益型 A/B：

   ```text
   A = 未来 20 日收益 - cost >= 0
   B = 其他
   ```

3. 路径型 A/B：

   ```text
   A = 先止跌/反弹，且最大回撤受控
   B = 继续下杀或反弹失败
   ```

日级 gate 的标签建议优先用“净收益型”和“路径型”，而不是只看最终收益。

### 8.2 为什么要做

如果只用最终 20 日收益定义 A/B，可能会把两种完全不同的路径混在一起：

- 先大跌再反弹，最终为正。
- 先反弹后回落，最终为正。
- 持续震荡，最终小幅为正。

对交易来说，这些路径的风险完全不同。一个可用的 panic gate 不仅要判断最后是否赚钱，还要判断中间是否会承受不可接受的回撤。

因此，后续 A/B 定义必须补充路径维度。

## 9. 优化方向五：从固定阈值转为训练期冻结阈值

### 9.1 要做什么

如果继续使用阈值过滤，必须只在训练期估计阈值，并在测试期冻结执行。

可比较的阈值方案：

- 固定概率阈值：`p_A > 0.5`、`p_A > 0.6`
- 训练期分位阈值：训练期 top 10%、top 20%
- 日期级历史分位阈值：当天 basket score 超过过去 60/120 日训练期分位
- 状态型阈值：根据训练期定义 `ALLOW` / `REDUCE` / `BLOCK`

所有阈值必须遵守：

```text
阈值只能由 train window 得到
test window 不允许重新校准
```

### 9.2 为什么要做

当前策略对阈值很敏感：

- 固定 `0.60` 在部分年份表现强，但覆盖率不稳定。
- 训练期 top 分位在某些年份覆盖率过低。
- 日内排名覆盖率稳定，但收益提升不足。

这说明阈值本身存在 regime drift。后续必须把阈值稳定性作为研究对象，而不是用样本内最优阈值直接得出结论。

## 10. 优化方向六：事件篮子与原组合的接入方式

### 10.1 要做什么

后续不建议直接把该因子进入全市场 alpha 合成。推荐先作为 sleeve 或 gate 使用。

接入方式分三层：

1. 诊断层：

   - 只输出每日 panic 状态。
   - 不参与组合。
   - 用于观察市场环境和事件表现。

2. 门控层：

   - 对 panic reversal sleeve 输出 `ALLOW` / `REDUCE` / `BLOCK`。
   - 不改变其他 alpha 的权重。
   - 只影响 panic 事件相关策略是否启用。

3. 仓位层：

   - 在 `ALLOW` 时允许正常事件仓位。
   - 在 `REDUCE` 时降低事件仓位。
   - 在 `BLOCK` 时不参与 panic reversal。

不建议的接入方式：

- 不建议把 `p_A` 直接作为个股 alpha。
- 不建议把 `date_rank_top_10pct` 作为实盘股票池。
- 不建议把当前 A/B predictor 加入主组合打分。

### 10.2 为什么要做

当前证据只支持“市场状态有信息”，不支持“同日个股筛选有稳定信息”。

如果直接进入个股层 alpha 合成，可能会：

- 增加换手。
- 引入不稳定信号。
- 在弱市场中放大下跌风险。
- 在强修复市场中错过 raw event 本身的高收益。

先做门控，可以把该因子的使用范围限制在它最可能有效的层面。

## 11. 优化方向七：补充成本、容量和流动性验证

### 11.1 要做什么

后续必须补充事件篮子的交易可行性诊断。

建议输出：

- 每日事件数量
- 每日可交易事件数量
- 事件股票成交额中位数
- 事件股票成交额 25 分位数
- 事件股票市值中位数
- 事件股票停牌、涨跌停、ST 过滤后的覆盖率
- 估算买入冲击成本
- 估算卖出冲击成本
- 10bps、20bps、30bps 成本下的 basket net return
- `ALLOW` 状态下的容量估计
- `REDUCE` 和 `BLOCK` 状态下避免的亏损或机会损失

### 11.2 为什么要做

panic drop 事件天然容易集中在：

- 小市值股票
- 低流动性股票
- 下跌趋势股票
- 跌停或接近跌停股票

这些股票在回测中可能有价格收益，但实盘未必能成交，或者成交成本极高。

如果不加入成本和容量诊断，模型可能只是在选择“看起来能反弹但买不进去/卖不出来”的样本。

## 12. 优化方向八：前视和过拟合控制

### 12.1 前视控制

后续方案必须继续保留 v2 中已经修正的前视控制，并扩展到日级 gate：

- 训练样本必须经过 `label_available_date < test_start_trade_date` 过滤。
- 训练窗口和测试窗口之间保留 20 个交易日 embargo。
- 未来收益、未来路径、未来 A/B 标签不能进入特征。
- 所有 rolling 特征只允许使用 `t` 日收盘前或收盘后已知数据。
- 如果信号使用 `t` 日收盘价生成，交易收益必须从 `t+1` 执行开始计算。
- 所有阈值、分位、标准化参数必须只用训练期估计。

### 12.2 过拟合控制

后续方案必须限制自由度。

建议控制方式：

- 先冻结一个主标签，不允许反复换标签找最好结果。
- 先冻结一个主策略，例如 `panic_basket_daily_gate_v1`。
- 特征分组做 ablation，不允许一次性堆大量特征后只报告最好结果。
- walk-forward 中每个测试年只允许使用此前训练窗口。
- 至少报告 2022、2023、2024 三个有效样本外年份。
- 2025 如果数据不足，必须明确标记 `INSUFFICIENT_DATA`，不能补齐或外推。
- 多个阈值、多个标签、多个模型同时搜索时，必须报告多重检验风险。

### 12.3 为什么要做

该因子的候选空间很容易扩大：

- 3 个方向
- 3 个阈值
- 3 种编码
- 多个持有期
- 多个 A/B 标签
- 多个 gate 阈值
- 多类市场状态特征

如果不控制研究自由度，很容易得到样本内漂亮但样本外失效的结论。

## 13. 推荐开发阶段

### Phase 1：日级数据集与诊断

目标：

- 把股票级 panic 事件聚合成日期级 panic basket。
- 不训练复杂模型，只确认日级信息是否存在。

需要产出：

- `panic_basket_daily_samples.csv`
- `panic_basket_daily_diagnostics.csv`
- `panic_basket_daily_report.md`

核心检查：

- 每日事件数量分布
- 事件覆盖率分布
- basket 未来收益分布
- 不同年份的 basket A-rate
- 不同市场环境下 basket 表现
- 与原 v2 `p_A` 聚合分数的关系

通过标准：

- 日级 basket 标签不是极端稀疏。
- 2022、2023、2024 都有足够有效交易日。
- basket 表现存在可解释的状态差异。

### Phase 2：规则型 gate 原型

目标：

- 先用简单、可解释规则验证方向，不急于上机器学习模型。

候选规则：

- panic event count 处于历史高分位，且市场宽度开始修复。
- panic ratio 高，但指数距离 20 日低点不再创新低。
- panic basket 平均跌幅较大，但成交额放大。
- v2 聚合 `p_A` 高于训练期分位阈值。

需要产出：

- `panic_basket_gate_rule_compare.csv`
- `panic_basket_gate_rule_walkforward.csv`
- `panic_basket_gate_rule_report.md`

通过标准：

- `ALLOW` 状态下 basket net return 高于 raw basket。
- `BLOCK` 状态下能过滤明显亏损或低胜率时期。
- 规则在至少 2/3 个有效样本外年份方向一致。

### Phase 3：轻量模型 gate

目标：

- 在规则型 gate 有效后，再使用轻量模型。

推荐模型：

- Logistic Regression
- HistGradientBoostingClassifier
- RandomForest 仅作对照，不作为首选

不建议一开始使用复杂模型，原因是日期级样本数量有限，复杂模型容易过拟合。

需要产出：

- `panic_basket_gate_model_walkforward.csv`
- `panic_basket_gate_model_feature_importance.csv`
- `panic_basket_gate_model_calibration.csv`
- `panic_basket_gate_model_report.md`

通过标准：

- walk-forward AUC 不低于规则型 gate。
- `ALLOW` 的净收益提升为正。
- `BLOCK` 能减少亏损或降低回撤。
- 特征重要性稳定且可解释。

### Phase 4：与组合或 sleeve 联动验证

目标：

- 验证 gate 是否能改善实际策略，而不是只改善标签。

需要比较：

- raw panic reversal sleeve
- rule gate panic sleeve
- model gate panic sleeve
- no-panic baseline
- 原组合不接入 panic
- 原组合接入 panic sleeve
- 原组合接入 gated panic sleeve

需要产出：

- `panic_sleeve_gate_backtest_compare.csv`
- `panic_sleeve_gate_yearly_attribution.csv`
- `panic_sleeve_gate_drawdown_report.md`

通过标准：

- gated sleeve 的年化收益、回撤、收益回撤比至少有一项明显改善。
- 不能靠单一年份贡献全部收益。
- 换手、成本、容量没有明显恶化。

## 14. 推荐验收指标

### 14.1 研究层验收

最低要求：

- 样本外年份不少于 3 个有效窗口。
- `ALLOW` 状态覆盖率不能过低，建议不低于 10% 的 panic event days。
- `BLOCK` 状态必须能过滤掉低质量日期，而不是随机减少交易。
- `ALLOW` 相对 raw basket 的 net spread lift 为正。
- 至少 2/3 有效年份 net spread lift 为正。

建议目标：

- 平均 AUC > 0.58。
- 平均 PR-AUC 高于 base rate。
- `ALLOW` basket A-rate lift >= 3 pct。
- `ALLOW` basket net spread lift > 0。
- `BLOCK` 状态下 raw basket 表现明显弱于 `ALLOW`。

### 14.2 交易层验收

最低要求：

- 20bps 成本后仍为正收益提升。
- 日均事件数量足够支持组合构建。
- 单日最大事件集中行业占比不能长期过高。
- 低流动性股票占比不能过高。
- 加入 gate 后换手不能显著恶化。

建议目标：

- gated sleeve 回撤低于 raw sleeve。
- gated sleeve 的收益回撤比高于 raw sleeve。
- `BLOCK` 避免的亏损大于 `ALLOW` 错过的机会收益。

### 14.3 风控层验收

必须满足：

- 无前视字段进入训练。
- 阈值只在训练期确定。
- 标准化、分位数、行业映射等参数只用训练期或当时已知数据。
- 所有报告明确 `research_only` 或 `production_eligible` 状态。
- 未通过验收前不得接入主组合。

## 15. Go / No-Go 判定

### Go 条件

只有同时满足以下条件，才允许进入下一阶段集成研究：

- 日级 gate 在样本外至少 2/3 年份带来正 net spread lift。
- 平均 net spread lift > 0。
- `ALLOW` 状态覆盖率足够，不是极低样本偶然结果。
- 20bps 成本后仍有改善。
- 没有发现前视泄露。
- 多重检验后仍有合理统计稳定性。
- 与原组合联动后没有增加不可接受回撤。

### No-Go 条件

出现以下任一情况，应继续保持研究观察，不进入组合：

- `ALLOW` 只在单一年份有效。
- `ALLOW` 覆盖率过低，缺乏实盘容量。
- 日级 gate 只能提升 AUC，但不能提升净收益。
- `BLOCK` 不能过滤亏损日期。
- 成本后收益消失。
- 主要效果来自复杂模型或大量调参。
- walk-forward 结果明显弱于样本内结果。

## 16. 最终建议

当前最合理的后续方向不是继续优化 `date_rank_top_10pct` 个股筛选，而是将该因子升级为“panic basket daily gate”。

推荐优先级：

1. 先做日级 panic basket 数据集和诊断。
2. 再做简单规则型 gate。
3. 若规则型 gate 有效，再做轻量模型。
4. 最后才验证与 sleeve 或主组合的接入。

在没有完成上述验证前，该因子应保持以下定位：

```text
research_only = true
production_eligible = false
use_case = panic event diagnostic / panic basket gate research
not_use_case = stock selector / portfolio alpha / live filter
```


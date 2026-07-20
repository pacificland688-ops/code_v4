# Panic Reversal A/B 分类目的与完整方案

## 1. 背景

`panic reversal` 的初始目标不是再做一个普通反转因子，而是解决原 `reversal_20_vol_adj_weekly_cs` 的真实短板：

```text
在已经发生短期极端涨跌的股票里，区分：

A 类：短期跌过头或涨过头，后续形成有效修复/回落。
B 类：坏趋势里的短暂反抽/假回落，后续继续恶化。
```

早期诊断中，原始 A/B 标签只用：

```python
is_A = fwd_ret_5d > 0
```

这个定义只能判断 5 日内有没有短线反弹，无法判断反弹是否持续。坏趋势股票也可能出现短期技术性反抽，因此会把大量“假修复”误标为 A 类。

多轮优化的目的，是把判断从：

```text
5 日有没有反弹
```

升级为：

```text
短期极端反转之后，是否形成有效修复，还是只是坏趋势中的短暂反抽。
```

## 2. 方案目的

本方案的目的不是继续调高 5 日回测收益，而是建立一套更稳定的 A/B/M 分类框架，用来回答以下问题：

1. `panic reversal` 是否能识别有效修复，而不是只识别短线反抽。
2. 该事件信号能否作为 `reversal_5_cs` 的过滤、降权或风险解释工具。
3. 哪些 panic event 应该保留，哪些应该排除，哪些只能降权观察。
4. 因子的改善是否能形成行动闭环，而不只是报告指标变好。

当前最新验收结论是：

```text
事件收益：有效。
前视控制：通过。
多重检验：通过。
增量价值：最终 walk-forward selected 因子对 reversal_5_cs 增量不足。
当前状态：RESEARCH_ONLY，不建议直接作为独立 Alpha 入池。
```

因此下一阶段重点不是强行入池，而是验证 panic event 是否能形成有效 A/B 分类，并服务于过滤、降权或风险提示。

## 3. 当前因子定位

当前更准确的定位是：

```text
短期极端反转事件识别器。
```

适用场景：

- 解释 `reversal_5_cs` 的收益来源。
- 识别短期极端涨跌事件。
- 对普通反转信号做过滤或降权。
- 对坏趋势中的假反弹/假回落做风险提示。

暂不适用场景：

- 未经增量验证，直接作为独立新增 Alpha 入池。
- 只凭 `fwd_ret_5d` 判断因子成功。
- 把 MAE、giveback 等交易过程指标混入 A/B 主标签。

## 4. 核心原则

### 4.1 A/B 标签只判断修复真假

A/B/M 标签只回答：

```text
这次 panic event 后，是否形成有效修复/有效回落？
```

它不回答：

```text
这个修复过程是否好交易？
是否中间回撤很深？
是否适合重仓？
```

这些问题属于交易质量评估，应单独处理。

### 4.2 指标分层

硬标签只使用低冗余、可解释、计算成本低的核心指标：

- `fwd_ret_5d`
- `fwd_ret_20d`
- `new_low_20d`
- `new_high_20d`

辅助诊断不进入第一版硬标签：

- `fwd_ret_60d`
- `post_rebound_ret_5_to_20`
- `MAE_20d`
- `giveback_ratio`
- `positive_days_20d`
- `days_until_giveback`

其中：

```text
fwd_ret_20d / new_low_20d / new_high_20d：判断修复真假。
MAE / giveback / positive_days：判断交易质量。
```

## 5. A/B/M 标签定义

### 5.1 参数

第一版不锁死单一阈值，扫描以下 `retention_threshold`：

```text
0.2 / 0.3 / 0.5
```

含义：

```text
20 日收益至少保留 5 日短线收益的一定比例。
```

例如多头端：

```text
fwd_ret_5d = +10%
retention_threshold = 0.3
则 fwd_ret_20d 至少应 >= +3%，才算有效保留。
```

### 5.2 多头急跌侧：drop / long

用于识别：

```text
短期急跌后，哪些股票是真修复，哪些是假反弹或坏趋势。
```

A 类：有效修复

```text
fwd_ret_5d > 0
AND fwd_ret_20d > 0
AND fwd_ret_20d >= fwd_ret_5d * retention_threshold
AND new_low_20d = False
```

B 类：假修复/坏趋势

```text
fwd_ret_5d <= 0
OR (fwd_ret_5d > 0 AND fwd_ret_20d <= 0)
OR (fwd_ret_5d > 0 AND new_low_20d = True)
```

M 类：中间地带

```text
fwd_ret_5d > 0
AND fwd_ret_20d > 0
AND fwd_ret_20d < fwd_ret_5d * retention_threshold
AND new_low_20d = False
```

M 类表示：

```text
短线反弹了，20 日也没完全失败，但修复保留不足。
```

### 5.3 空头急涨侧：up / short

用于识别：

```text
短期急涨后，哪些股票是真回落，哪些是假回落或强趋势延续。
```

A 类：有效回落

```text
fwd_ret_5d < 0
AND fwd_ret_20d < 0
AND abs(fwd_ret_20d) >= abs(fwd_ret_5d) * retention_threshold
AND new_high_20d = False
```

B 类：假回落/强趋势

```text
fwd_ret_5d >= 0
OR (fwd_ret_5d < 0 AND fwd_ret_20d >= 0)
OR (fwd_ret_5d < 0 AND new_high_20d = True)
```

M 类：中间地带

```text
fwd_ret_5d < 0
AND fwd_ret_20d < 0
AND abs(fwd_ret_20d) < abs(fwd_ret_5d) * retention_threshold
AND new_high_20d = False
```

M 类表示：

```text
短线回落了，20 日也没完全失败，但回落保留不足。
```

### 5.4 对称因子：sym

`sym` 因子需要按事件方向拆开评价：

- `value > 0` 的样本按 long/drop 规则。
- `value < 0` 的样本按 short/up 规则。

不允许把 long 和 short 混在一个 A/B 标签里直接统计，否则会掩盖方向差异。

## 6. 核心指标定义

### 6.1 `fwd_ret_5d`

用途：

```text
判断是否发生短线反弹/短线回落。
```

定位：

```text
必要条件，不是充分条件。
```

多头端：

```text
fwd_ret_5d > 0 表示短线反弹。
```

空头端：

```text
fwd_ret_5d < 0 表示短线回落。
```

### 6.2 `fwd_ret_20d`

用途：

```text
判断短线反弹/回落是否延续到中期。
```

这是第一版 A/B 标签中最关键的新增指标。

多头端：

```text
fwd_ret_20d > 0 才能说明修复没有马上失败。
```

空头端：

```text
fwd_ret_20d < 0 才能说明急涨后的回落有延续。
```

### 6.3 `new_low_20d`

多头端使用：

```text
new_low_20d = min(close_t1 ... close_t20) < close_t0
```

用途：

```text
识别急跌后是否继续破位。
```

如果 5 日反弹了，但 20 日内又跌破触发日价格，则更像 B 类。

### 6.4 `new_high_20d`

空头端使用：

```text
new_high_20d = max(close_t1 ... close_t20) > close_t0
```

用途：

```text
识别急涨后是否继续上冲。
```

如果短线回落了，但 20 日内又突破触发日价格，则更像 B 类。

## 7. 辅助诊断指标

这些指标不进入第一版硬标签，只用于解释和二级质量评分。

### 7.1 `fwd_ret_60d`

用途：

```text
辅助观察更长周期是否恶化。
```

注意：

- 需要确认数据管线是否已有该列。
- 不作为第一版硬标签。
- 60 日跨度更长，容易混入基本面、行业和市场状态等外生因素。

### 7.2 `post_rebound_ret_5_to_20`

定义：

```text
post_rebound_ret_5_to_20 = close_t20 / close_t5 - 1
```

用途：

```text
诊断短线反弹后是否继续修复。
```

但它与 `fwd_ret_5d` 和 `fwd_ret_20d` 高度相关：

```text
1 + fwd_ret_20d = (1 + fwd_ret_5d) * (1 + post_rebound_ret_5_to_20)
```

因此只做诊断，不作为独立门槛。

### 7.3 `MAE_20d`

定义：

```text
MAE_20d = min(close_t1 ... close_t20) / close_t0 - 1
```

用途：

```text
评估交易过程中最大不利变动。
```

定位：

```text
交易质量指标，不是修复真假标签。
```

例如：

```text
fwd_ret_20d = +15%
MAE_20d = -12%
```

这可能仍是 A 类，因为最终有效修复；但交易质量差，因为中间回撤深。

### 7.4 `giveback_ratio`

定义：

```text
giveback_ratio = (peak_ret_0_to_20 - ret_20d) / peak_ret_0_to_20
```

用途：

```text
评估反弹后回吐程度。
```

第一版暂缓使用，原因：

- 需要计算 20 日路径峰值，计算成本高于端点收益。
- 与 `fwd_ret_20d + new_low_20d` 捕捉的失败模式可能重叠。

建议先做漏网分析：

```text
如果 A 类里仍有大量高 giveback 样本，再考虑引入。
```

### 7.5 `positive_days_20d`

用途：

```text
描述未来 20 日中有多少天站在触发价之上。
```

定位：

```text
描述性统计，不作为硬标签。
```

原因：

- 单日噪声大。
- 与 `fwd_ret_20d` 高度相关。

## 8. 行动闭环

A/B/M 分类必须对应可执行动作，否则只是描述性分析。

第一轮建议验证三种动作。

### 8.1 `A only`

规则：

```text
只保留 A 类，剔除 M 和 B。
```

目标：

```text
最大化信号纯度。
```

风险：

```text
覆盖率可能下降过多。
```

### 8.2 `A + 0.5M`

规则：

```text
A 类正常权重。
M 类半权重。
B 类剔除。
```

目标：

```text
在信号质量和覆盖率之间折中。
```

### 8.3 `exclude B`

规则：

```text
剔除 B 类，保留 A 和 M。
```

目标：

```text
减少假修复/坏趋势，同时保留更多股票池覆盖。
```

### 8.4 不建议第一轮做反向交易

B 类可以作为负面信号或风险提示，但不建议第一轮直接反向交易。

原因：

```text
B 类定义首先用于排除假阳性，不等价于可稳定做空。
```

## 9. 开发方案

### 9.1 扩展 A/B 诊断脚本

优先扩展现有：

```text
scripts/diagnose_ab_classification.py
```

或新增独立脚本：

```text
scripts/evaluate_panic_ab_classification.py
```

建议新增独立脚本，避免污染原始诊断逻辑。

### 9.2 数据输入

必需输入：

- panic factor value
- `fwd_ret_5d`
- `fwd_ret_20d`
- adjusted close path from `t0` to `t20`

如果 `fwd_ret_20d` 已在 `fwd_returns` 中存在，直接加载。

如果不存在，则从 `prices_adj` 计算：

```text
fwd_ret_20d = close_t20 / close_t0 - 1
```

### 9.3 路径指标计算

对每个 `(ts_code, trade_date)` 计算：

```text
future_min_20d = min(close_t1 ... close_t20)
future_max_20d = max(close_t1 ... close_t20)
new_low_20d = future_min_20d < close_t0
new_high_20d = future_max_20d > close_t0
```

辅助诊断可计算：

```text
post_rebound_ret_5_to_20
MAE_20d
giveback_ratio
positive_days_20d
```

但辅助指标不参与第一版 A/B/M 标签。

### 9.4 标签生成

对每个 retention threshold：

```text
0.2 / 0.3 / 0.5
```

分别生成：

- `ab_label_long`
- `ab_label_short`
- `ab_label_sym`

标签取值：

```text
A
B
M
UNCLASSIFIED
```

### 9.5 分方向评估

必须分别评估：

- `drop / long`
- `up / short`
- `sym_long_leg`
- `sym_short_leg`

不允许只看多头端。

### 9.6 行动策略评估

对每个 threshold 和方向评估：

- `A only`
- `A + 0.5M`
- `exclude B`

输出：

- 覆盖率
- A/B/M 占比
- mean forward return
- event net spread
- IC / ICIR
- 年度正收益数
- turnover proxy
- cost-adjusted net spread

## 10. 输出产物

新增输出目录沿用：

```text
outputs/analysis/panic_reversal_gate/
```

新增文件：

```text
panic_ab_label_summary.csv
panic_ab_by_year.csv
panic_ab_action_eval.csv
panic_ab_quality_diagnostics.csv
panic_ab_classification_report.md
```

### 10.1 `panic_ab_label_summary.csv`

建议字段：

- `factor`
- `direction`
- `signal_type`
- `retention_threshold`
- `label`
- `n_samples`
- `coverage`
- `mean_fwd_ret_5d`
- `mean_fwd_ret_20d`
- `new_low_rate_20d`
- `new_high_rate_20d`
- `mae_20d_mean`
- `giveback_ratio_mean`
- `positive_days_20d_mean`

### 10.2 `panic_ab_by_year.csv`

建议字段：

- `year`
- `factor`
- `direction`
- `retention_threshold`
- `label`
- `n_samples`
- `coverage`
- `mean_fwd_ret_20d`
- `label_rate`
- `new_low_rate_20d`
- `new_high_rate_20d`

### 10.3 `panic_ab_action_eval.csv`

建议字段：

- `factor`
- `direction`
- `retention_threshold`
- `action`
- `coverage`
- `gross_spread`
- `net_spread_20bps`
- `ic`
- `icir`
- `pos_years`
- `n_years`
- `turnover_proxy`

### 10.4 `panic_ab_quality_diagnostics.csv`

建议字段：

- `factor`
- `direction`
- `retention_threshold`
- `label`
- `mae_20d_mean`
- `mae_20d_p10`
- `giveback_ratio_mean`
- `giveback_ratio_p90`
- `positive_days_20d_mean`
- `post_rebound_ret_5_to_20_mean`

### 10.5 `panic_ab_classification_report.md`

报告必须包含：

- A/B/M 定义。
- retention threshold 扫描结果。
- long / short 分方向表现。
- 三种 action 的对比。
- 是否存在 A 类覆盖率过低问题。
- MAE/giveback 是否显示 A 类交易质量不足。
- 最终建议：
  - `A only`
  - `A + 0.5M`
  - `exclude B`
  - 或 `NO_ACTION`

## 11. 验收标准

### 11.1 标签有效性

- A/B/M 三类互斥。
- `UNCLASSIFIED` 占比应被报告。
- A 类覆盖率不能极端稀疏。
- A 类 `fwd_ret_20d` 应显著优于 B 类。
- 多头端 A 类 `new_low_20d` 发生率应低于 B 类。
- 空头端 A 类 `new_high_20d` 发生率应低于 B 类。

### 11.2 行动有效性

至少一个 action 应满足：

```text
net_spread_20bps > 原始 panic event
或 ICIR 提升
或 年度稳定性提升
```

同时覆盖率不能下降到不可交易水平。

### 11.3 分方向要求

必须分别给出：

- long/drop 结果
- short/up 结果
- sym 拆腿结果

如果只有 short/up 有效，最终方案应明确：

```text
只用于急涨回落事件，不用于急跌修复事件。
```

### 11.4 交易质量要求

MAE 和 giveback 不影响 A/B 标签，但必须报告。

如果 A 类存在：

```text
MAE 很深
giveback 很高
turnover 很高
```

则最终动作不能直接入池，只能降级为：

```text
RESEARCH_ONLY
或 risk overlay
```

## 12. 最终决策规则

第一轮 A/B 分类完成后，按以下规则决策：

```text
如果 A 类覆盖率过低：
    不采用 A only，优先评估 A + 0.5M 或 exclude B。

如果 A 类收益优于 B 类，但交易质量差：
    用作降权/过滤，不独立入池。

如果 A/B/M 无法明显拉开：
    保持 RESEARCH_ONLY。

如果 exclude B 明显提升原始 panic event：
    可作为 reversal_5_cs 的过滤器候选。

如果 selected factor 仍对 reversal_5_cs 无增量：
    不作为独立 Alpha 入池。
```

## 13. 推荐实施顺序

1. 新增 `evaluate_panic_ab_classification.py`。
2. 确认或计算 `fwd_ret_20d`。
3. 计算 `new_low_20d / new_high_20d`。
4. 生成 A/B/M 标签。
5. 扫描 `retention_threshold = 0.2 / 0.3 / 0.5`。
6. 分 long / short / sym leg 评估。
7. 评估 `A only / A + 0.5M / exclude B`。
8. 输出四个 CSV 和一份 markdown 报告。
9. 再决定是否进入过滤器开发，而不是直接入池。

## 14. 当前默认结论

在 A/B/M 分类验证完成前，`panic reversal` 的默认状态保持：

```text
RESEARCH_ONLY
```

当前不建议：

- 独立入池。
- 替代 `reversal_5_cs`。
- 直接作为组合权重信号。

当前可以：

- 作为短期极端反转事件诊断。
- 作为 `reversal_5_cs` 的候选过滤器研究对象。
- 作为风险提示或降权条件的研究对象。

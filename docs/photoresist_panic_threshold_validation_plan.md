# 光刻胶恐慌修复阈值验证开发方案

## 1. 目标

本方案用于扩展当前光刻胶恐慌修复研究，不是为了调参制造 `GO`，而是回答三个问题：

1. 当前 `panic_gate` 的 5 日收益阈值是否稳健。
2. 恐慌修复是否只在特定市场状态中有效。
3. 事件后收益是否显著优于随机非恐慌时点。

最终结论仍然分两层：

```text
event_GO:
  光刻胶主题 basket 恐慌后是否存在可重复修复效应。

top1_GO:
  只能买一只股票的账户是否能稳定捕捉该效应。

trade_GO:
  event_GO 和 top1_GO 同时成立，且成本、集中度、鲁棒性不过度脆弱。
```

## 2. 核心原则

1. 主事件定义必须独立冻结，不能根据 `top1` 表现反向调参。
2. 辅助阈值只做鲁棒性验证，必须报告全部结果，不能只挑最好的一组。
3. 时间序列不能随机交叉验证，必须使用 walk-forward 或样本外验证。
4. 市场状态、成交量、资金流只能先作为诊断层，不直接堆进主 `panic_gate`。
5. 显著性检验必须按事件簇抽样，避免连续恐慌日重复计数。

## 3. 当前基线

当前 BBB 修复后，全量验证结果为：

```text
event_GO = True
top1_GO = False
trade_GO = False
classification = basket_valid_top1_invalid
```

含义：

```text
光刻胶主题 basket 层面存在修复倾向；
但当前 top1 单票规则暂不可直接实盘。
```

本方案的目的不是马上优化 `top1`，而是先判断 `event_GO` 是否在多阈值、多市场状态和 placebo 检验下仍然可靠。

## 4. 数据范围

### 4.1 主数据

```text
股票行情:
  data/parquet/prices_adj
  字段: ts_code, trade_date, adj_close, close, pct_chg, amount, vol

复权因子:
  data/parquet/adj_factor

涨跌停:
  data/parquet/limit_status

停牌:
  data/parquet/suspend_status

股票状态:
  data/parquet/stock_status

指数:
  data/parquet/index_daily
```

### 4.2 可选实时补数

若本地数据未覆盖最新日期，可用 Tushare 临时拉取：

```text
daily:
  ts_code, trade_date, open, high, low, close, pre_close, change, pct_chg, vol, amount

adj_factor:
  ts_code, trade_date, adj_factor

index_daily:
  ts_code, trade_date, close, pct_chg
```

要求：

```text
1. 临时补数必须记录 source=tushare_live。
2. 不得静默混用未复权价格和复权价格。
3. 若只用于单票近期分析，可以不写入 parquet。
4. 若写入缓存，必须经过独立增量更新脚本和 manifest。
```

## 5. 样本划分

### 5.1 固定样本外划分

主报告使用：

```text
train_observation:
  2017-2021

validation:
  2022-2023

out_of_sample:
  2024-2026
```

用途：

```text
2017-2021:
  观察阈值行为和事件分布，不用来挑 top1 交易规则。

2022-2023:
  验证 panic_gate 是否仍能捕捉修复。

2024-2026:
  最终样本外检验。
```

### 5.2 Walk-forward 划分

辅助报告使用逐年滚动：

```text
train_window:
  过去 3 年

test_window:
  下一自然年

例:
  train 2017-2019 -> test 2020
  train 2018-2020 -> test 2021
  ...
```

要求：

```text
所有历史分位、市场状态阈值、placebo 分桶参数只能来自 test_date 之前的数据。
```

## 6. 主阈值和辅助阈值

### 6.1 主阈值

主 `panic_gate` 保持一套，作为主结论来源：

```text
primary_gate =
  core_basket_ret_5d < 0
  AND (
    core_basket_ret_5d <= -5%
    OR core_basket_ret_5d <= rolling_quantile_10%(past_250_trading_days)
  )
  AND down_stock_ratio_5d >= 50%
```

说明：

```text
1. rolling_quantile 必须 shift(1)，不能包含当日。
2. 该 gate 不根据 top1 表现调整。
3. 该 gate 是 event_GO 主判断口径。
```

### 6.2 辅助阈值

辅助阈值只做 robustness：

| gate_id | 窗口 | 绝对跌幅 | 历史分位 | 目的 |
|---|---:|---:|---:|---|
| relaxed_5d | 5 日 | -3% | 10% | 捕捉轻度恐慌 |
| primary_5d | 5 日 | -5% | 10% | 主口径 |
| strict_5d | 5 日 | -8% | 5% | 捕捉强恐慌 |
| strict_10d | 10 日 | -10% | 5% | 捕捉慢速杀跌 |

报告规则：

```text
1. 所有辅助 gate 都必须输出。
2. 不允许只展示收益最好的 gate。
3. 若只有单一 gate 有效，其余 gate 全部失效，则结论降级为 fragile。
```

### 6.3 历史窗口鲁棒性

对主 gate 增加两个历史分位窗口：

```text
rolling_quantile_window_days:
  250
  500
```

主结论仍使用 250 日。500 日只判断长期窗口下方向是否一致。

暂不实现指数加权分位，原因：

```text
1. 参数自由度更高。
2. 样本较少，容易过拟合。
3. 第一轮验证优先检查 250 vs 500 是否稳定。
```

## 7. 市场状态分层

### 7.1 目的

检验恐慌修复是否只是牛市 beta 反弹。

如果结果为：

```text
bull 有效
bear 无效
neutral 无效
```

则不能称为稳定恐慌修复，只能称为牛市回调修复。

### 7.2 市场状态定义

使用事前可计算规则：

```text
benchmark_index:
  primary: 000300.SH
  growth: 399006.SZ
  semiconductor: 931865.CSI
```

主状态使用 `000300.SH`：

```text
bull:
  index_close > MA120
  AND index_ret_60d > 0

bear:
  index_close < MA120
  AND index_ret_60d < 0

neutral:
  other
```

辅助状态使用 `399006.SZ` 和 `931865.CSI` 做对照：

```text
growth_regime:
  创业板状态

semiconductor_regime:
  中证半导体产业状态
```

### 7.3 输出统计

按状态分别输出：

```text
n_event_clusters
forward_ret_1d_mean
forward_ret_3d_mean
forward_ret_5d_mean
forward_ret_10d_mean
forward_ret_20d_mean
win_rate_5d
win_rate_20d
max_adverse_excursion
max_favorable_excursion
top1_rule_mean_net
```

## 8. 修复确认指标

### 8.1 价格确认

保留当前技术确认，但只作为分组，不进入主 gate：

```text
direct_entry:
  panic event 后 t+1 close 入场观察

first_positive_close:
  事件后 5 日内第一天 basket_ret_1d > 0

outperform_semiconductor:
  事件后 5 日内第一天 core_basket_ret_1d > semiconductor_ret_1d

recover_above_event_mid:
  收盘价高于事件日 high/low 中枢
```

### 8.2 成交量确认

新增成交量分组：

```text
panic_volume_group:
  high_panic_volume:
    panic_day_amount_ratio_20d >= 1.2

  normal_panic_volume:
    panic_day_amount_ratio_20d < 1.2

repair_volume_group:
  high_repair_volume:
    repair_day_amount_ratio_20d >= 1.0

  low_repair_volume:
    repair_day_amount_ratio_20d < 1.0
```

注意：

```text
成交量不是第一轮硬 gate。
有些有效修复表现为缩量止跌，不一定放量。
成交量先用于判断恐慌质量和修复质量。
```

### 8.3 资金流向

资金流向暂不进入主回测。

原因：

```text
1. 主力资金口径依赖数据商，复现性弱。
2. 北向资金对小票和主题股解释力有限。
3. 披露和可得性需要单独 PIT 校验。
4. 容易与价格和成交量重复计量。
```

可作为人工复盘字段：

```text
fund_flow_diagnostics:
  enabled: false
  status: optional_review_only
```

## 9. 显著性检验

### 9.1 Placebo 检验

目标：

```text
判断真实恐慌事件后的收益是否显著优于随机非恐慌时点。
```

抽样方法：

```text
1. 按 event_cluster 数量 N 抽样。
2. 从非恐慌交易日中随机抽 N 个日期。
3. 日期必须匹配年份和市场状态分布。
4. 可选匹配波动率分桶和成交量分桶。
5. 重复 1000 次。
```

输出：

```text
real_mean_forward_ret_20d
placebo_mean_forward_ret_20d_mean
placebo_mean_forward_ret_20d_std
mean_diff
percentile_rank
permutation_p_value
```

判定：

```text
p_value <= 0.10:
  weak_significance

p_value <= 0.05:
  significant

p_value > 0.10:
  not_significant
```

### 9.2 Bootstrap 检验

目标：

```text
估计真实事件收益均值的置信区间。
```

方法：

```text
1. 以事件簇为单位 bootstrap。
2. 重复 1000 次。
3. 计算 5/10/20 日 forward return 的均值置信区间。
```

输出：

```text
bootstrap_mean
ci_5pct
ci_95pct
ci_contains_zero
```

判定：

```text
若 20 日 net return 的 90% CI 下界仍 > 0，说明 basket 修复较稳。
若 CI 跨 0，只能保留观察结论。
```

## 10. Top1 单票验证保持独立

本方案不允许用 top1 结果反向修改事件定义。

但每套 gate 都要同步输出 top1 诊断：

```text
top1_strength
top1_mid_drop
top1_liquidity_core
```

每套 top1 必须满足：

```text
1. ret_5d < 0。
2. 非 ST。
3. 非停牌。
4. 事件日未跌停。
5. 入场日未涨停。
6. 上市满 120 个交易日。
7. 20 日均成交额达标。
```

输出：

```text
top1_forward_return_by_gate.csv
top1_rule_by_market_regime.csv
top1_contribution_concentration.csv
top1_leave_one_stock_out.csv
```

如果：

```text
event_GO = True
top1_GO = False
```

则结论仍然是：

```text
basket_valid_top1_invalid
主题存在修复，但单票账户暂不可交易。
```

## 11. 输出文件

建议新增目录：

```text
outputs/analysis/photoresist_panic_threshold_validation/
```

输出文件：

```text
photoresist_threshold_gate_compare.csv
photoresist_threshold_forward_returns.csv
photoresist_threshold_by_market_regime.csv
photoresist_threshold_volume_groups.csv
photoresist_threshold_walkforward.csv
photoresist_threshold_placebo_test.csv
photoresist_threshold_bootstrap_ci.csv
photoresist_threshold_top1_compare.csv
photoresist_threshold_manifest.json
photoresist_threshold_validation_report.md
```

### 11.1 gate compare 字段

```text
gate_id
ret_window_days
absolute_threshold
quantile_window_days
quantile_threshold
n_event_clusters
n_event_days
mean_fwd_ret_5d
mean_fwd_ret_10d
mean_fwd_ret_20d
win_rate_20d
mean_net_ret_20d
event_go_raw
event_go_after_significance
```

### 11.2 market regime 字段

```text
gate_id
market_regime
n_event_clusters
mean_fwd_ret_20d
win_rate_20d
mean_net_ret_20d
max_adverse_excursion_mean
```

### 11.3 placebo 字段

```text
gate_id
horizon_days
n_real_events
n_placebo_runs
real_mean_return
placebo_mean_return
placebo_std_return
mean_diff
permutation_p_value
significance_label
```

### 11.4 manifest 字段

```text
schema
date_range
primary_gate_id
auxiliary_gate_ids
sample_split
walkforward_config
market_regime_definition
placebo_config
bootstrap_config
data_sources_available
data_sources_used_in_computation
not_implemented_features
config_hash
generated_at
```

## 12. Go/No-Go 标准

### 12.1 event_GO 升级标准

`event_GO` 不再只看 basket 均值，应增加显著性约束：

```text
event_GO = True if:
  primary_gate mean_net_ret_20d > 0
  AND win_rate_20d > 50%
  AND market_regime 中至少 2 类非负，或明确标注 only_bull_effect
  AND placebo permutation_p_value <= 0.10
  AND bootstrap 90% CI 下界不显著为负
  AND basket LOO 不因剔除单一股票完全失效
```

如果主 gate 通过，但只在牛市有效：

```text
event_GO = conditional
event_GO_label = bull_only_repair
```

### 12.2 top1_GO 保持现有标准

```text
top1_GO = True if:
  至少一条 top1 规则成本后收益为正
  AND 单一股票贡献不过度集中
  AND leave-one-stock-out 后不完全失效
  AND 50bps 成本下不反转为明显负收益
  AND 年份集中度不过高
```

### 12.3 trade_GO

```text
trade_GO = event_GO == True AND top1_GO == True
```

若：

```text
event_GO = conditional
top1_GO = True
```

则：

```text
trade_GO = conditional
只能在对应 market_regime 下启用。
```

## 13. 开发阶段

### Phase 1：配置和数据结构

新增配置：

```yaml
threshold_validation:
  primary_gate_id: primary_5d
  auxiliary_gates:
    - relaxed_5d
    - strict_5d
    - strict_10d
  quantile_windows: [250, 500]
  report_all_gates: true

market_regime:
  primary_index: "000300.SH"
  ma_window: 120
  return_window: 60

significance_tests:
  placebo:
    n_runs: 1000
    match_by_year: true
    match_by_market_regime: true
  bootstrap:
    n_runs: 1000
    ci: 0.90
```

### Phase 2：多阈值事件生成

实现：

```text
build_threshold_gate_events()
```

要求：

```text
1. 复用现有 PIT universe 和 basket daily。
2. 每个 gate 输出独立 event_cluster_id。
3. rolling quantile 必须 shift(1)。
4. 事件聚类按交易日序号，不按 YYYYMMDD 差值。
```

### Phase 3：市场状态分层

实现：

```text
compute_market_regime()
attach_market_regime_to_events()
```

要求：

```text
1. 使用事件日已知指数数据。
2. MA 和收益计算不得使用未来数据。
3. 输出 bull/bear/neutral。
```

### Phase 4：成交量分组

实现：

```text
compute_volume_quality_groups()
```

要求：

```text
1. amount_ratio_20d 使用真实 rolling mean。
2. rolling mean 不需要 shift，因为成交额是当日收盘后确认，用于事件后分析。
3. 若用于交易入场条件，则必须 lag1。
```

### Phase 5：Placebo 和 Bootstrap

实现：

```text
run_placebo_tests()
run_bootstrap_ci()
```

要求：

```text
1. 以 event_cluster 为抽样单位。
2. placebo 日期不得与真实 panic event 日期重叠。
3. placebo 匹配年份和 market_regime。
4. 固定 random_seed 并写入 manifest。
```

### Phase 6：报告和 Go/No-Go

实现：

```text
generate_threshold_validation_report()
evaluate_threshold_go_nogo()
```

报告必须包含：

```text
1. 主 gate 结果。
2. 所有辅助 gate 结果。
3. 市场状态分层。
4. 成交量分组。
5. placebo / bootstrap 显著性。
6. top1 同步诊断。
7. 明确结论：GO / CONDITIONAL / NO-GO。
```

## 14. 测试计划

新增测试文件建议：

```text
tests/test_photoresist_threshold_validation.py
```

测试点：

```text
1. rolling quantile 不包含当日。
2. 多 gate 必须全部输出，不允许只输出 best gate。
3. market_regime 只使用事件日前可得数据。
4. placebo 抽样不包含真实事件日。
5. placebo 按年份和 market_regime 匹配。
6. bootstrap 以事件簇为单位。
7. 成交量分组字段完整。
8. report 包含所有 gate 的结果。
9. manifest 包含 config_hash、random_seed、data_sources_used。
10. event_GO 在 significance failure 时不能 PASS。
```

## 15. 验收标准

### 15.1 功能验收

```text
1. 所有新增输出文件存在且非空。
2. 主 gate 和辅助 gate 全部出现在报告中。
3. market_regime 分层统计完整。
4. placebo 和 bootstrap 结果完整。
5. top1 同步诊断仍然输出。
6. manifest 可复现。
```

### 15.2 研究验收

主结论必须明确归类：

```text
GO:
  主 gate 显著优于 placebo，跨状态不过度脆弱，top1 可交易。

CONDITIONAL:
  basket 有效但只在特定状态有效，或 top1 不稳定。

NO-GO:
  主 gate 不显著，或结果只来自单一股票/单一年份/单一阈值。
```

### 15.3 禁止项

```text
1. 不允许用 2024-2026 样本外结果选择阈值。
2. 不允许只报告表现最好的辅助 gate。
3. 不允许把资金流向纳入主 gate。
4. 不允许用 top1 结果反向修改 event gate。
5. 不允许在测试集重新估计阈值。
```

## 16. 最终定位

本方案完成后，光刻胶恐慌修复信号应被定位为：

```text
主题恐慌状态信号
+ 阈值鲁棒性诊断
+ 市场状态条件诊断
+ 显著性检验
+ 单票可交易性验收
```

如果结果仍然是：

```text
event_GO = True
top1_GO = False
```

则它只能作为：

```text
观察信号 / 组合层面环境因子 / 人工复盘触发器
```

不能作为：

```text
单票自动买入因子
```

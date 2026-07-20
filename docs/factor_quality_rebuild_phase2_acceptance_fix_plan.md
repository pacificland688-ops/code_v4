# Factor Quality Rebuild 二期验收整改开发方案

生成日期：2026-06-14

## 1. 背景与结论

本轮审核对象是 `Factor Quality Rebuild 二期整改` 的实际落地结果。现有实现已经补充了较多框架能力，包括因子级 `data_lag_days`、raw / mcap-neutral 双轨 gate、真实权重漂移换手、容量筛查、rolling window、相关性聚类、候选池输出等。

但审核结论是：**当前版本不通过最终验收**。

原因不是单测失败，而是几个核心验收点仍会直接扭曲最终 `PASS / WATCH / FAIL` 判断：

- fundamental 因子的 no-leakage 对齐使用了错误的交易日函数，可能把合法数据误判为未来函数。
- 容量筛查的成交额单位与配置阈值不一致，当前几乎确定把流动性放大为系统性 FAIL。
- coverage 仍按原始 `trade_date` 计算，没有按 `data_lag_days` 后的 `signal_date` 对齐。
- capacity hard fail 过早返回，导致 gate 只输出 `capacity: FAIL`，隐藏真实失败原因。
- 正式输出的 `factor_correlation_cluster.csv` 不可读。
- neutralization diagnostic 的核心字段仍为 `NaN`，无法支撑 raw / mcap-neutral 双轨判断。

本方案目标是把这些问题修到可验收状态，使二期输出的 gate 结论可以作为下一阶段因子修复、因子扩展和 sleeve 重建的可信输入。

## 2. 本次整改范围

### 2.1 范围内

本次只修复因子质量重建流水线的验收可靠性问题：

1. 修正 `first_trading_day_on_or_after` 交易日对齐语义。
2. 修正 fundamental 因子的 `data_lag_days` 对齐和 no-leakage 审计。
3. 修正 coverage 口径，使其基于 `signal_date` 与 forward universe。
4. 修正容量筛查成交额单位，统一 CNY 口径。
5. 调整 gate 失败原因收集逻辑，保留所有诊断项。
6. 修复空 correlation cluster CSV 的可读性。
7. 补齐 neutralization diagnostic 的 coverage 与 size beta。
8. 增加回归测试，覆盖本轮验收发现的盲区。
9. 重新生成正式产物和报告。

### 2.2 范围外

以下内容不在本次整改范围内：

- 不新增 alpha 因子。
- 不放宽 gate 阈值来制造 PASS。
- 不重建 sleeve / strategy。
- 不引入复杂冲击成本模型。
- 不把 2021-2024 从 primary validation 中移除。
- 不把 `log_market_cap_cs` 作为 alpha candidate。

## 3. 目标状态

整改完成后，流水线必须满足：

1. 对任意因子，`observation_date + data_lag_days` 不得晚于 forward return 起点。
2. fundamental 因子的 coverage、IC、分位收益、换手和容量均基于 lag 后的 `signal_date`。
3. capacity audit 中所有金额字段均明确为 CNY，不能混用万元和元。
4. gate 输出必须包含完整失败原因，而不是被第一个 hard fail 截断。
5. 所有输出 CSV 即使为空也必须 header-only 可读。
6. neutralization diagnostic 必须展示 raw 与 mcap-neutral 的核心差异，以及 neutralizer 覆盖率和 size beta。
7. `factor_candidate_pool.yaml` 中：
   - `eligible_factors` 只能包含最终 `PASS` 且非冗余的 alpha candidate。
   - `support_factors.neutralizers` 必须包含 `log_market_cap_cs`。
   - 空缓存基本面因子必须进入 `missing_data_factors` 或等价字段。
   - 若无可用 alpha，必须输出 `NO_ALPHA_SOURCE_FOUND`。

## 4. 关键口径定义

### 4.1 日期对齐口径

统一使用以下定义：

```text
observation_date = factor.trade_date
available_date = observation_date + data_lag_days
signal_date = first_trading_day_on_or_after(available_date)
forward_return = fwd_return(signal_date, signal_date + horizon)
```

判定规则：

```text
signal_date >= available_date
```

若任何已参与计算的样本违反该规则，应计入 `n_unmatured_rows_excluded`。若 unmatured 样本比例超过阈值，则 `no_leakage_status=FAIL`。

### 4.2 coverage 口径

coverage 必须定义为：

```text
coverage_pct(date) = |factor_signal_universe(date) ∩ forward_universe(date)| / |forward_universe(date)|
```

其中 `date` 必须是 `signal_date`，不是 raw factor 的 `observation_date`。

统计字段：

- `median_coverage_pct`：validation 窗口内日度 coverage 中位数。
- `min_yearly_coverage_pct`：validation 各年份日度 coverage 中位数的最小值。
- `median_daily_coverage`：validation 窗口内日度交集股票数中位数。
- `min_daily_coverage`：validation 窗口内日度交集股票数最小值。

### 4.3 容量金额口径

配置项 `min_median_amount_cny` 是 CNY。

若 `daily_basic` 使用 Tushare 风格字段：

- `total_mv`：万元。
- `circ_mv`：万元。
- `turnover_rate`：百分比。

则估算日成交额应为：

```text
estimated_amount_cny = circ_mv * 10000 * turnover_rate / 100
```

如果存在真实 `amount` 字段，需要先确认单位：

- 若 `amount` 为千元，则 `amount_cny = amount * 1000`。
- 若 `amount` 已为元，则直接使用。
- 代码中不得用未标注单位的金额列直接与 CNY 阈值比较。

### 4.4 gate 失败原因口径

hard gate 可以决定最终状态，但不能中断诊断收集。

正确流程：

```text
1. 收集 data availability / input audit / no-leakage / coverage / capacity / raw gate / neutral gate / turnover / rolling / trend 的全部诊断。
2. 将 hard fail 项标记到 hard_failures。
3. 将普通失败项标记到 soft_failures。
4. 根据 hard_failures 与 raw / neutral gate 组合映射 final status。
5. 输出完整 failure_reasons。
```

最终状态优先级：

1. `DATA_MISSING`
2. `FAIL`，如果存在 hard fail
3. `PASS`，如果 raw 与 neutral 均通过且无降级标签
4. `WATCH_SIZE_DEPENDENT`
5. `WATCH_NEUTRAL_ONLY`
6. `WATCH_IC_DECAY`
7. `WATCH_CAPACITY_CONSTRAINED`
8. `WATCH_CAPACITY_UNKNOWN`
9. `FAIL`

## 5. 开发任务拆解

## 5.1 P0：修正交易日 on-or-after 语义

### 问题

当前 `_build_aligned_panel` 使用：

```python
cal.next_trade_day(d, n=0)
```

但 `TradingCalendar.next_trade_day(date, n=0)` 对非交易日会返回前一交易日。例如：

```text
20240404 -> 20240403
```

这违反 `first_trading_day_on_or_after(available_date)` 语义，会制造错误的 unmatured rows。

### 修改方案

在 `data/calendar.py` 增加明确函数：

```python
def first_trade_day_on_or_after(self, date: int) -> int:
    """Return the first trading day >= date."""
```

实现要求：

- 如果 `date` 本身是交易日，返回 `date`。
- 如果 `date` 是非交易日，返回第一个大于该日期的交易日。
- 如果 `date` 超出交易日表尾部，返回 `date` 并由上层标记 `NOT_AVAILABLE` 或无法对齐。
- 不改变现有 `next_trade_day` 行为，避免影响其他模块。

在 `scripts/factor_quality_rebuild.py` 中：

```python
df_copy["signal_date"] = df_copy["available_date"].apply(
    lambda d: cal.first_trade_day_on_or_after(d)
)
```

### 测试

新增测试：

```text
20240403 -> 20240403
20240404 -> 20240408
20240405 -> 20240408
20240406 -> 20240408
20240407 -> 20240408
20240408 -> 20240408
```

验收标准：

- 非交易日不得回退到前一交易日。
- fundamental 因子 no-leakage 不再因错误回退产生假 FAIL。

## 5.2 P0：修正 no-leakage 对齐

### 问题

当前 no-leakage 的 `available_date -> signal_date` 可能回退，导致：

```text
signal_date < available_date
```

正式产物中 `ep_cs / bp_cs / sp_cs` 当前显示：

```text
5217/29084 rows have unmatured forward returns
```

该结论在交易日函数修正前不可信。

### 修改方案

在 `_build_aligned_panel` 中：

1. 保留 `observation_date`。
2. 计算 `available_date`。
3. 计算 `signal_date = first_trade_day_on_or_after(available_date)`。
4. merge forward return 时使用 `signal_date`。
5. no-leakage 检查使用 `signal_date >= available_date`。

输出 aligned panel 时建议保留调试字段：

- `observation_date`
- `available_date`
- `trade_date`，即 `signal_date`
- `_window`

如果下游只接受 `trade_date`，可以保留 `trade_date=signal_date`，但 audit 文件必须输出日期对齐统计。

新增 audit 字段：

- `data_lag_days`
- `min_observation_date`
- `max_observation_date`
- `min_available_date`
- `max_available_date`
- `min_signal_date`
- `max_signal_date`
- `n_unmatured_rows_excluded`

### 测试

新增构造样本：

- observation date 为非交易日前一天。
- `data_lag_days` 后落在节假日。
- forward return 只在节后第一个交易日可用。

期望：

- 样本应对齐到节后第一个交易日。
- `n_unmatured_rows_excluded=0`。
- `no_leakage_status=PASS`。

## 5.3 P0：修正容量金额单位

### 问题

当前估算逻辑：

```python
db_date["_est_amount"] = db_date["circ_mv"] * db_date["turnover_rate"] / 100.0
```

如果 `circ_mv` 是万元，则 `_est_amount` 仍是万元，但列名和阈值使用 CNY。这会导致所有因子被错误判为流动性不足。

### 修改方案

新增金额标准化函数：

```python
def _daily_basic_amount_cny(daily_basic: pd.DataFrame) -> pd.Series:
    ...
```

优先级：

1. 如果存在已知 CNY 字段，如 `amount_cny`，直接使用。
2. 如果存在 `amount`，根据配置 `amount_unit` 转为 CNY。
3. 如果存在 `circ_mv` 和 `turnover_rate`，使用：

```python
circ_mv_cny = circ_mv * 10000
amount_cny = circ_mv_cny * turnover_rate / 100
```

配置增加：

```yaml
capacity:
  daily_basic_mv_unit: "wan_cny"
  amount_unit: "auto"
```

输出字段统一命名为：

- `median_top_amount_cny`
- `median_bottom_amount_cny`
- `median_top_mcap_cny`
- `median_bottom_mcap_cny`

### 测试

新增测试：

```text
circ_mv=100000 万元
turnover_rate=2
expected_amount_cny=20,000,000
```

期望：

- `min_median_amount_cny=20,000,000` 时不应因单位错误 FAIL。
- 测试必须覆盖旧逻辑会失败、新逻辑会通过的情况。

## 5.4 P1：修正 coverage 计算

### 问题

当前 `_audit_factor_input` 在 raw factor `trade_date` 上计算 coverage。对 fundamental 因子，这是 observation date，不是 signal date。

正式产物中：

```text
ep_cs / bp_cs / sp_cs / log_market_cap_cs raw_rows ≈ 30453
median_coverage_pct = 0.0
input_audit_status = PASS
```

该组合本身就说明 coverage 口径不稳定：有数据但 coverage 为 0，却仍然 PASS。

### 修改方案

拆分 input audit 与 alignment coverage：

1. `_audit_factor_input` 只负责原始缓存质量：
   - empty cache
   - duplicate keys
   - missing rate
   - constant dates
   - extreme outlier rate

2. 新增或改造 coverage audit：

```python
def _compute_aligned_coverage(
    aligned: pd.DataFrame,
    fwd: pd.DataFrame,
    validation_years: list[int],
) -> dict:
    ...
```

基于 aligned panel 的 `trade_date`，即 `signal_date`，与 forward universe 计算。

3. gate 使用 aligned coverage，而不是 raw input coverage。

### 输出字段调整

`factor_input_audit.csv` 保留原始缓存字段：

- `raw_rows`
- `clean_rows`
- `duplicate_keys`
- `missing_rate`
- `input_audit_status`
- `input_audit_reason`
- `data_status`

`factor_alignment_audit.csv` 或新增 `factor_coverage_audit.csv` 输出：

- `median_coverage_pct`
- `min_yearly_coverage_pct`
- `median_daily_coverage`
- `min_daily_coverage`
- `coverage_denominator`
- `coverage_date_basis=signal_date`

### 测试

新增测试：

1. factor observation date 与 fwd trade date 不同，但 lag 后 signal date 匹配。
2. raw date coverage 为 0，signal date coverage 为 100%。
3. gate 必须使用 signal date coverage。

## 5.5 P1：gate 收集完整失败原因

### 问题

当前 `_apply_quality_gate` 中 capacity hard fail 直接 return。正式产物中大量因子只有：

```text
capacity: FAIL - liquidity/capacity insufficient
```

这会隐藏 IC、coverage、turnover、rolling window、neutralization 等真实失败原因，不利于后续因子修复。

### 修改方案

重构 `_apply_quality_gate`：

```python
hard_failures = []
soft_failures = []
warnings = []
gate_meta = {}

# collect all diagnostics first
# decide final status at the end
```

hard fail 项：

- `DATA_MISSING`
- `no_leakage != PASS`
- `capacity_status == FAIL`
- required metadata missing

soft fail 项：

- coverage 不足
- raw IC 不足
- neutral IC 不足
- net spread 不足
- net/gross ratio 不足
- rolling windows 不稳
- IC decay
- regime sensitivity

输出字段建议扩展：

- `quality_gate_status`
- `n_hard_failures`
- `n_soft_failures`
- `hard_failure_reasons`
- `soft_failure_reasons`
- `warning_reasons`
- `failure_reasons`，兼容旧字段，拼接全部原因

### 测试

新增测试：

同一个因子同时触发：

- capacity FAIL
- coverage FAIL
- raw IC FAIL
- neutral gate FAIL

期望：

- 最终状态为 `FAIL`。
- `failure_reasons` 同时包含全部失败项。
- 不允许因为 capacity 先失败而隐藏其他项。

## 5.6 P1：修复 correlation cluster 空 CSV 可读性

### 问题

当前正式产物：

```text
factor_correlation_cluster.csv size=5
pd.read_csv -> EmptyDataError
```

这说明正式产物未被正确刷新，或空 DataFrame 写出逻辑不稳定。

### 修改方案

定义固定 schema：

```python
CORRELATION_CLUSTER_COLUMNS = [
    "cluster_id",
    "factor",
    "representative",
    "redundant_to",
    "max_abs_corr_to_rep",
    "gate_score",
]
```

在 `_compute_correlation_clusters` 中：

- 若无 cluster，返回 `pd.DataFrame(columns=CORRELATION_CLUSTER_COLUMNS)`。
- 不在 write 阶段补写 header，避免写出顺序和编码问题。

写出时统一：

```python
correlation_clusters.to_csv(path, index=False, encoding="utf-8-sig")
```

### 测试

新增测试：

- 所有因子 FAIL 时，cluster DataFrame 为空但 columns 完整。
- 写入 CSV 后 `pd.read_csv` 不报错。
- `factor_candidate_pool.yaml` 在空 cluster 下仍正常生成。

## 5.7 P1：补齐 neutralization diagnostic

### 问题

当前 `_compute_neutralization_diagnostic` 中：

```python
"neutralizer_coverage_pct": NaN
"size_beta_mean": NaN
```

正式产物中这两列全空，无法判断 mcap-neutral 结果是否可信。

### 修改方案

在 `_neutralize_by_mcap` 或中性化阶段输出每个因子的诊断统计：

- neutralizer 覆盖率。
- 每日 OLS beta。
- 每日残差样本数。

建议返回：

```python
neutralized_df, neutralization_meta
```

`neutralization_meta` 包括：

- `neutralizer_coverage_pct`
- `size_beta_mean`
- `size_beta_std`
- `n_neutralized_dates`
- `n_skipped_dates`
- `skip_reason_top`

`_compute_neutralization_diagnostic` 读取 meta 填充字段。

### 计算规则

对每个交易日：

```text
coverage = count(factor ∩ log_mcap) / count(factor)
```

若 coverage < `min_neutralizer_coverage_pct` 或样本数 < `min_stocks`：

- 当日 neutralized value 置为 NaN。
- 计入 skipped dates。

否则做截面回归：

```text
factor_value = alpha + beta * log_market_cap_cs + residual
```

记录 beta。

### 测试

新增测试：

1. high coverage 下 `neutralizer_coverage_pct` 非空。
2. size-exposed factor 的 `size_beta_mean` 显著非零。
3. low coverage 下 `neutralization_status=NOT_AVAILABLE` 或当日跳过。

## 5.8 P2：重新生成正式产物并补充产物验收脚本

### 问题

当前单测通过，但正式产物仍不满足验收：

- `factor_correlation_cluster.csv` 不可读。
- capacity 全 FAIL 可能由单位错误导致。
- neutralization 字段全 NaN。
- gate reasons 信息不足。

说明测试没有覆盖产物级验收。

### 修改方案

新增轻量产物验收脚本：

```text
scripts/validate_factor_quality_outputs.py
```

检查：

1. 必需文件存在。
2. 所有 CSV 可被 `pd.read_csv` 读取。
3. 必需列存在。
4. `factor_quality_gate.csv` 不允许只有单一 `capacity: FAIL` 原因覆盖全部非缺失因子。
5. `factor_neutralization_diagnostic.csv` 中：
   - `neutralizer_coverage_pct` 对可中性化因子非全空。
   - `size_beta_mean` 对可中性化因子非全空。
6. `factor_capacity_audit.csv` 金额字段为 CNY，且数值量级合理。
7. `factor_candidate_pool.yaml` 满足接口契约。

### 验收命令

```powershell
python scripts/factor_quality_rebuild.py `
  --config configs/factor_quality_rebuild.yaml `
  --start 20170101 `
  --end 20241231 `
  --out-dir outputs/analysis/factor_quality_rebuild `
  --out-doc docs/factor_quality_rebuild_report.md

python scripts/validate_factor_quality_outputs.py `
  --out-dir outputs/analysis/factor_quality_rebuild
```

### 性能要求

全流程需要可运行到完成。建议先设定验收上限：

```text
全量 2017-2024 单次运行 <= 10 分钟
```

若超过，需要 profile：

- neutralization 是否逐因子重复 merge 过多。
- capacity 是否按日期循环反复过滤大表。
- rolling window 是否重复计算 IC。
- regime breakdown 是否重复扫描文件。

## 6. 测试计划

### 6.1 单元测试

文件：`tests/test_factor_quality_rebuild.py`

新增测试类建议：

1. `TestTradingCalendarOnOrAfter`
   - 验证交易日与非交易日 on-or-after 行为。

2. `TestLaggedAlignment`
   - fundamental factor lag 后落在节假日。
   - forward return 从节后第一个交易日开始。
   - 不应产生 unmatured rows。

3. `TestAlignedCoverage`
   - raw date coverage 为 0。
   - signal date coverage 为 100%。
   - gate 使用 signal date coverage。

4. `TestCapacityAmountUnit`
   - `circ_mv` 万元转 CNY。
   - `turnover_rate` 百分比转比例。
   - 阈值比较使用 CNY。

5. `TestGateReasonCollection`
   - capacity FAIL 不应阻断 coverage / IC / neutralization 原因。

6. `TestEmptyCorrelationClusterOutput`
   - 空 cluster DataFrame 有固定 columns。
   - 写出 CSV 可读。

7. `TestNeutralizationDiagnosticMeta`
   - neutralizer coverage 非空。
   - size beta 非空。
   - low coverage 正确跳过。

### 6.2 回归测试

运行：

```powershell
python -m pytest -q tests/test_factor_quality_rebuild.py
python -m pytest -q tests/test_factor_quality_rebuild.py tests/test_factor_alignment.py tests/test_factor_pruning.py tests/test_strategy_alpha_failure_diagnosis.py
```

通过标准：

- 所有测试通过。
- 不新增非预期 warning。
- 原有 candidate pool 接口不破坏。

### 6.3 产物验收测试

运行全流程后检查：

```powershell
python scripts/validate_factor_quality_outputs.py --out-dir outputs/analysis/factor_quality_rebuild
```

通过标准：

- 必需产物全部存在。
- 所有 CSV 可读。
- gate 文件包含完整失败原因。
- capacity 金额量级合理。
- neutralization diagnostic 关键字段非全空。
- `factor_candidate_pool.yaml` 满足契约。

## 7. 产物清单

整改完成后必须更新或生成：

```text
scripts/factor_quality_rebuild.py
data/calendar.py
configs/factor_quality_rebuild.yaml
tests/test_factor_quality_rebuild.py
scripts/validate_factor_quality_outputs.py
outputs/analysis/factor_quality_rebuild/factor_input_audit.csv
outputs/analysis/factor_quality_rebuild/factor_alignment_audit.csv
outputs/analysis/factor_quality_rebuild/factor_quality_gate.csv
outputs/analysis/factor_quality_rebuild/factor_candidate_pool.yaml
outputs/analysis/factor_quality_rebuild/factor_capacity_audit.csv
outputs/analysis/factor_quality_rebuild/factor_neutralization_diagnostic.csv
outputs/analysis/factor_quality_rebuild/factor_correlation_cluster.csv
docs/factor_quality_rebuild_report.md
```

## 8. 验收标准

### 8.1 代码验收

- `first_trade_day_on_or_after` 行为正确。
- no-leakage 对齐不再使用 `next_trade_day(n=0)`。
- coverage 使用 `signal_date`。
- capacity 金额统一 CNY。
- `_apply_quality_gate` 不再在 capacity fail 处提前 return。
- empty DataFrame 输出有固定 schema。
- neutralization diagnostic 不再硬编码核心字段为 NaN。

### 8.2 数据验收

- `ep_cs / bp_cs / sp_cs` 的 no-leakage 状态需要基于修正后的 on-or-after 逻辑重新计算。
- `factor_capacity_audit.csv` 不应因万元/CNY 单位错误导致系统性全 FAIL。
- `factor_correlation_cluster.csv` 即使为空也能被 `pd.read_csv` 正常读取。
- `factor_neutralization_diagnostic.csv` 中可中性化因子的 `neutralizer_coverage_pct` 与 `size_beta_mean` 不得全空。

### 8.3 结论验收

允许最终仍然是：

```text
eligible_factors = []
recommendation = NO_ALPHA_SOURCE_FOUND
```

但只有在以下条件满足后，该结论才可信：

- no-leakage 对齐正确。
- coverage 口径正确。
- capacity 单位正确。
- gate reasons 完整。
- 输出产物可读且字段完整。

如果修复后仍无 PASS，应接受“当前因子族没有证明正 alpha”的结论，并进入下一阶段因子质量重建，而不是继续在错误 gate 上调参。

## 9. 开发顺序

建议按以下顺序执行：

1. 实现 `first_trade_day_on_or_after` 并替换 no-leakage 对齐调用。
2. 修正 capacity 金额单位和配置口径。
3. 将 coverage 从 raw input audit 移到 aligned signal date audit。
4. 重构 `_apply_quality_gate`，完整收集失败原因。
5. 固定 correlation cluster schema。
6. 补齐 neutralization diagnostic meta。
7. 增加单元测试。
8. 增加产物验收脚本。
9. 跑全量 2017-2024 流水线。
10. 用产物验收脚本检查输出。
11. 更新 `docs/factor_quality_rebuild_report.md`。

## 10. 风险与注意事项

1. 修正 on-or-after 后，fundamental 因子的 aligned rows 可能变化，这是预期结果。
2. 修正 capacity 单位后，当前全部 capacity FAIL 的结论可能大幅变化，必须重新解释 gate。
3. coverage 迁移到 signal date 后，原 `factor_input_audit.csv` 字段含义会变化，报告中需要说明。
4. gate reason 变多后，CSV 字段可能更长，但这是必要诊断信息。
5. 如果全流程运行时间超过验收上限，不应跳过性能问题；需要 profile 后优化。

## 11. 最终交付说明

本次整改完成后，需要在最终审核中明确给出：

- 测试命令与结果。
- 全流程运行命令与耗时。
- 关键产物摘要。
- `ep_cs / bp_cs / sp_cs` 修正前后的 no-leakage 与 coverage 变化。
- capacity audit 修正前后的金额量级变化。
- candidate pool 最终状态。
- 若仍为 `NO_ALPHA_SOURCE_FOUND`，说明这是在修复验收缺陷后的可信结论。

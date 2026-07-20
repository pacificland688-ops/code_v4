# Panic Reversal 优化开发方案

## 1. 背景与结论

本方案针对 `panic reversal` 修复后代码审核中发现的问题制定。当前因子构造函数本身未发现直接使用未来收益或未来价格的问题，但诊断、验收和候选选择链条仍存在多处风险：

- P0 年份统计存在逐行循环 bug，可能严重放大正收益年份数。
- 正式 diagnostics 输出与 `panic_fast_check.py` 输出混用，当前产物不能作为验收依据。
- 成本/流动性诊断未实际执行。
- 交易时点口径未明确，存在使用收盘信号评估同日收盘后收益的前视/不可成交风险。
- 27 个候选同时扫描后择优，存在多重检验和样本内过拟合风险。
- regime 诊断使用全样本分位，只能作为诊断，不能作为硬开关依据。

优化目标不是继续调高回测表现，而是先让 gate、报告和样本外验证可信，再决定是否保留候选因子。

## 2. 开发目标

1. 修复 diagnostics 中会导致验收偏乐观的实现错误。
2. 明确并落地 `t+1` 执行收益口径，消除交易时点前视。
3. 补齐成本、流动性、冗余、稀疏性和 regime 诊断。
4. 将候选选择流程从全样本择优改为 walk-forward 或冻结 holdout 验证。
5. 明确 fast check 与正式 gate 的边界，防止调试脚本覆盖正式产物。

## 3. P0 任务：修复 Gate 正确性

### 3.1 修复年度循环 bug

涉及文件：

- `scripts/evaluate_panic_reversal_diagnostics.py`
- `scripts/panic_fast_check.py`

问题代码类型：

```python
for yr in sorted(df["trade_date"] // 10000):
```

该写法会按每一行样本循环年份，而不是按唯一年份循环。需要统一改为：

```python
years = sorted((df["trade_date"] // 10000).dropna().astype(int).unique())
for yr in years:
    ...
```

必须修复的位置：

- validation 年度正收益计数。
- cost/liquidity 年度分组。
- fast check 的 `val_pos_years`。

验收标准：

- `val_pos_years <= val_n_years` 永远成立。
- 2021-2024 验证窗口下，`val_pos_years` 最大值只能为 4。
- 新增单测覆盖逐行重复年份输入，确保不会重复计数。

### 3.2 正式 diagnostics 与 fast check 解耦

`panic_fast_check.py` 只能用于快速调试，不允许覆盖正式 gate 文件。

改动要求：

- `panic_fast_check.py` 输出改为：
  - `outputs/analysis/panic_reversal_gate/debug/panic_fast_check_summary.csv`
  - 或 `outputs/analysis/panic_reversal_gate/panic_fast_check_summary.csv`
- `panic_variant_summary.csv` 只能由 `evaluate_panic_reversal_diagnostics.py` 生成。
- 报告中明确标注 `diagnostic_source=full_gate_v2`。

验收标准：

- 运行 fast check 不会修改正式 `panic_variant_summary.csv`。
- 正式 summary 包含完整 v2 字段，不再只有 `dir/thr/sig/ic/icir/ev_net` 等简化列。

### 3.3 修复 P0 状态写入报告

当前 `p0_status` 只存在于 `p0_screen(summary)` 返回表中，没有 merge 回 `summary`，报告中会显示 `-`。

改动要求：

- `p0_screen` 返回 `factor, p0_status, p0_reason` 等字段。
- 生成报告前将 P0 状态左连接回 `summary`。
- 未通过候选填充为 `FAIL`，并写明失败原因。

验收标准：

- 报告中每个候选都有明确状态：`PASS_EVENT`、`PASS_RANK`、`EVENT_FILTER_ONLY` 或 `FAIL`。
- 报告不得出现全部状态为 `-` 的情况。

## 4. P0 任务：修复前视口径

### 4.1 新增 `t+1` 执行收益

当前 panic 因子使用 `close_t` 计算 `mom5`，如果直接用 `close_t -> close_{t+5}` 的 `fwd_ret_5d` 评估，就隐含同日收盘可成交，存在交易时点前视/不可成交风险。

正式 gate 应使用：

- `signal_date = t`：收盘后生成信号。
- `execution_date = next_trade_date(t)`。
- `fwd_ret_5d_exec_lag1 = close_{t+6} / close_{t+1} - 1`。

保留原始同日口径仅作研究对照：

- `fwd_ret_5d_close_to_close_same_day`
- `fwd_ret_5d_exec_lag1`

正式 P0/P1/P2 默认使用 `fwd_ret_5d_exec_lag1`。

验收标准：

- 报告显式显示 `execution_lag=1`。
- 所有正式 gate 指标默认使用 lag1 收益。
- 同日收益口径只能出现在 appendix 或对照表中，不参与最终 PASS 判定。

### 4.2 增加对齐校验

新增诊断检查：

- 因子 `trade_date` 是否为信号日期。
- `execution_date` 是否严格大于 `trade_date`。
- `return_start_date` 是否等于 `execution_date`。
- `return_end_date` 是否晚于 `execution_date` 5 个交易日。

验收标准：

- 若发现 `execution_date <= signal_date`，直接 FAIL。
- 输出 `panic_return_alignment_check.csv`。

## 5. P1 任务：补齐成本与流动性诊断

### 5.1 恢复成本/流动性分析

当前 `cost_liquidity_analysis(...)` 在 main 中被注释，导致 `panic_cost_liquidity.csv` 缺失或为空。

改动要求：

- 修复年度循环 bug 后恢复成本分析。
- 支持按候选因子输出年度成本和流动性统计。
- 避免在主循环中重复加载大表，必要时先预聚合 `daily_basic`。

必须输出字段：

- `factor`
- `year`
- `event_rate`
- `event_median_mv`
- `noevent_median_mv`
- `event_median_amount`
- `noevent_median_amount`
- `turnover_est`
- `signal_persist_1w`
- `signal_persist_2w`
- `signal_persist_3w`
- `net_spread_cost_10bps`
- `net_spread_cost_20bps`
- `net_spread_cost_30bps`
- `net_spread_mv_small`
- `net_spread_mv_mid`
- `net_spread_mv_large`

注意事项：

- `daily_basic` 同日字段只能作为诊断使用。
- 如果未来要用作交易过滤条件，必须使用 `t-1` 或交易前已知数据。

验收标准：

- `panic_cost_liquidity.csv` 非空。
- 每个候选至少有年度粒度记录。
- 报告中有成本压力测试汇总。

## 6. P1 任务：修复冗余相关性诊断

### 6.1 输出两套相关性

稀疏二值因子含大量 0，仅用全面板 Spearman 可能低估与 5 日反转因子的冗余。需要输出两套口径：

1. 全面板相关性：包含 0。
2. 事件样本相关性：只看 `panic value != 0`。

对比基准：

- `reversal_5_cs`
- `reversal_5_liquidity_adj_weekly_cs`
- `reversal_20_vol_adj_weekly_cs`

输出字段：

- `panic_factor`
- `baseline_factor`
- `corr_scope`: `full_panel` 或 `event_only`
- `mean_spearman_corr`
- `median_spearman_corr`
- `max_abs_corr`
- `n_dates`
- `n_common_rows`
- `reason`

验收标准：

- `mean_spearman_corr` 和 `max_abs_corr` 不能无故为空。
- 若为空，必须写明 `reason`，例如 `missing_baseline_factor`、`too_few_common_rows`、`constant_series`。
- P1 gate 使用 `event_only` 和 `full_panel` 两套结果共同判断冗余。

## 7. P1 任务：降低过拟合

### 7.1 加入冻结样本外验证

不得使用 2017-2024 全样本择优后再宣称有效。推荐先实现一个简单冻结切分：

- 2017-2020：候选选择期。
- 2021-2022：验证期。
- 2023-2024：最终 holdout。

选择规则：

- 只能在 2017-2020 上选择阈值、方向和信号编码。
- 2021-2022 只用于确认稳定性。
- 2023-2024 只做最终验收，不允许再调参。

验收标准：

- 报告分别展示 `train`、`validation`、`holdout` 指标。
- 最终推荐候选必须在冻结 holdout 下仍满足 gate。

### 7.2 加入 expanding walk-forward 验证

建议在冻结切分之外增加 walk-forward：

- train 2017-2020，test 2021。
- train 2017-2021，test 2022。
- train 2017-2022，test 2023。
- train 2017-2023，test 2024。

每个窗口流程：

1. 只用 train 窗口选择候选。
2. 冻结候选和参数。
3. 在下一年 test 窗口评估。

输出字段：

- `window_id`
- `train_start`
- `train_end`
- `test_start`
- `test_end`
- `selected_factor`
- `selection_metric`
- `test_net_spread`
- `test_icir`
- `test_event_rate`
- `test_pass`

验收标准：

- 输出 `panic_walkforward_validation.csv`。
- 报告展示 pass window 数量和 pass ratio。
- 若 walk-forward 表现明显弱于全样本，必须标记过拟合风险。

### 7.3 多重检验惩罚

27 个候选同时扫描，不能只看最佳候选。报告应新增：

- 候选总数。
- 最佳候选与候选中位数的差距。
- bootstrap 或 permutation 的经验 p-value。
- 简化 FDR 或 Bonferroni 标记。

最低实现要求：

- 对每个 rebalance date 打乱 `fwd_ret` 横截面，重复 500 次。
- 记录每次 27 个候选中的最大 net spread。
- 计算真实最佳候选超过 permutation max 分布的经验 p-value。

验收标准：

- 输出 `panic_multiple_testing_check.csv`。
- 若经验 p-value 不显著，报告不得给出强 PASS 结论。

## 8. P2 任务：regime 只做诊断

### 8.1 修复 regime 输出字段

当前代码将 `factor` 错写为 regime 来源。应改为：

```python
rd["factor"] = pf
rd["regime_source"] = rd_src
rd["diagnostic_only"] = True
```

如果继续使用全样本 70% 波动分位：

- 只能作为诊断。
- 不能作为硬开关参与最终收益提升。

验收标准：

- `panic_regime_diagnostic.csv` 中 `factor` 是真实因子名。
- `regime_source` 单独记录来源。
- 报告明确标记 regime 为 `diagnostic_only`。

### 8.2 v2 再考虑 regime 硬开关

只有当 walk-forward 中使用训练窗口单独估计 regime 阈值，并在测试窗口冻结执行时，才允许将 regime 作为硬开关。

本轮优化不做 regime 硬开关，只保留诊断。

## 9. P2 任务：补充文档说明

需要更新或新增设计说明，写清楚以下内容：

- 不继承 `vol_60d` 调整的原因：A/B 类波动率差异极小，且叠加 vol 过滤未改善 A-rate。
- 非事件设为 0，而不是 NaN 或行业均值回填的原因：这是稀疏事件信号，回填会注入噪声。
- 正式执行口径是 `signal close -> next trading day execution`。
- `panic_fast_check.py` 只用于调试，不作为 gate。
- 最终候选必须通过冻结 holdout 或 walk-forward。

## 10. 建议实施顺序

1. 修复年度循环 bug，并新增单测。
2. 解耦 fast check 输出，保护正式 gate 产物。
3. 修复 P0 状态写入报告。
4. 新增 `t+1` 执行收益并切换正式 gate 默认口径。
5. 恢复成本/流动性诊断。
6. 修复冗余相关性，增加 event-only 口径。
7. 修复 regime 输出字段，并标记 diagnostic-only。
8. 增加冻结 holdout 验证。
9. 增加 walk-forward 验证。
10. 增加多重检验诊断。
11. 重跑完整 diagnostics。
12. 基于新报告决定是否保留、降级或废弃 panic reversal 候选。

## 11. 最终验收标准

代码层：

- `python -m pytest tests/test_panic_reversal.py -q` 通过。
- 新增 diagnostics 单测通过：
  - 年份唯一计数。
  - fast check 不覆盖正式输出。
  - P0 状态写入报告。
  - lag1 收益对齐。
  - regime 字段正确。

数据产物层：

- `panic_variant_summary.csv` 由完整 gate 生成，字段完整。
- `panic_reversal_report.md` 更新时间与本次完整运行一致。
- `panic_cost_liquidity.csv` 非空。
- `panic_redundancy_corr.csv` 相关性字段非空或有明确 reason。
- `panic_walkforward_validation.csv` 非空。
- `panic_multiple_testing_check.csv` 非空。

风控层：

- 报告明确使用 `execution_lag=1`。
- `val_pos_years <= val_n_years`。
- 最终候选在 holdout 或 walk-forward 下仍扣成本为正。
- 与现有 5 日反转因子不存在不可接受的高冗余。
- 多重检验后仍具备可解释的统计稳定性。

## 12. Go / No-Go 判定

满足以下条件才允许进入候选池：

- lag1 口径下 20bps 成本后 net spread 为正。
- holdout 或 walk-forward 至少 3/4 年份为正，或 pass ratio 达到预设门槛。
- 事件覆盖率足以支持组合落地，且无连续空信号风险。
- event-only 冗余相关性未超过 0.6，或能证明有增量收益。
- 多重检验诊断未显示显著数据挖掘风险。

若不满足：

- 降级为研究观察因子；
- 或只保留为 panic event diagnostic，不进入组合权重合成。

# Alpha 失败归因二期整改开发方案

生成日期：2026-06-13
前置文档：`docs/strategy_alpha_failure_diagnosis_development_plan.md`
修复对象：`scripts/strategy_alpha_failure_diagnosis.py`、`tests/test_strategy_alpha_failure_diagnosis.py`

## 1. 整改目标

修复上一轮审核暴露的归因框架缺口：
- 严格因子保留门槛（不再因轻微正 IC 误保留弱因子）
- 真实 sleeve oracle / opportunity cost（不再输出 signal_date=0 的占位数据）
- 补齐组合构造诊断矩阵（pre_cost_vs_post_cost、rebalance_frequency、topn_capacity）
- 修正 benchmark common-calendar 评价（区分 calendar mismatch 和同 period return conflict）
- 修复报告模板残留、添加产物一致性检查

## 2. Key Changes

### 2.1 修复 factor retention gate

新增字段：`avg_long_only_top_excess`, `positive_long_only_top_years`, `avg_top_bottom_excess`, `positive_top_bottom_years`, `avg_decile_monotonicity`, `positive_monotonicity_years`, `avg_coverage`, `coverage_ok_years`, `retention_failure_reasons`

保留门槛：
- `positive_long_only_top_years >= 5`
- `avg_long_only_top_excess > 0`
- `positive_top_bottom_years >= 5`
- `avg_top_bottom_excess > 0`
- `positive_monotonicity_years >= 5`
- `mean_ic > 0`
- `positive_ic_years >= 5`
- `max_consecutive_negative_years < 3`
- `avg_coverage` 不为空

任何字段缺失 → `passes_retention_gate=False` + `retention_failure_reasons`。

### 2.2 实现真实 router oracle 与 opportunity cost

使用 `sleeve_weight_cross_year/year=YYYY/sleeve_scores/{sleeve}.parquet` 和 `fwd_returns.parquet` 中的 `fwd_ret_5d` 计算每期 sleeve return。

输出：`sleeve_hindsight_oracle.csv`、`router_opportunity_cost.csv`、`overlay_predictiveness.csv`

字段：`actual_sleeve_weights`, `actual_weighted_sleeve_return`, `oracle_best_sleeve`, `oracle_best_sleeve_return`, `equal_sleeve_return`, `opportunity_cost_vs_oracle`, `opportunity_cost_vs_equal`, `dominant_sleeve`, `dominant_sleeve_return`, `dominant_is_oracle`, `regime_label`, `signal_date`, `period_end`

数据不足时输出 `INSUFFICIENT_SLEEVE_RETURN_DATA` 标记。

### 2.3 补齐组合构造诊断矩阵

新增：`pre_cost_vs_post_cost.csv`、`rebalance_frequency_diagnostic.csv`（`NOT_AVAILABLE`）、`topn_capacity_diagnostic.csv`（`NOT_AVAILABLE`）

### 2.4 修正 benchmark common-calendar 评价

- 检测同 period_end 不同策略 benchmark return 冲突 → `BENCHMARK_RETURN_CONFLICT`
- investment gate 新增 `benchmark_calendar_status`、`excess_metric_reliable`、`calendar_failure_reasons`
- 若存在冲突，超额指标标记为不可信

### 2.5 修复报告与产物一致性

- 报告时间戳使用真实日期
- 无 `pd.Timestamp`、`strftime`、`← auto` 等模板残留
- 新增 `_check_artifact_consistency()` 检查所有预期产物

## 3. Test Plan

新增测试覆盖：
- 因子缺少 long_only_top_excess / decile_monotonicity / coverage 时 retention gate 不通过
- mean_ic > 0 但 top decile 超额为负时 retention gate 不通过
- router opportunity cost 包含 oracle 字段，signal_date/period_end 不全为 0
- 缺少 sleeve return 数据时 INSUFFICIENT_SLEEVE_RETURN_DATA
- benchmark 同一 period return 冲突 → BENCHMARK_RETURN_CONFLICT
- investment gate 在 benchmark 不可靠时标记 excess_metric_reliable=False
- 报告不含模板残留
- 产物检查函数

## 4. Acceptance Criteria

- `strategy_investment_gate.csv` 所有策略仍为 NO_GO
- `factor_alpha_scorecard_2017_2024.csv` 弱因子被正确排除
- `router_opportunity_cost.csv` 有真实 oracle 字段
- `benchmark_calendar_audit.csv` 区分 mismatch 和 conflict
- 报告无模板残留
- 所有测试通过

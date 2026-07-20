# Router Oracle `period_end=0` 修复开发方案

生成日期：2026-06-13
修复对象：`scripts/strategy_alpha_failure_diagnosis.py` `_build_router_opportunity_cost`

## 问题

`router_opportunity_cost.csv` 和 `sleeve_hindsight_oracle.csv` 中混入 `period_end=0` 且 `status=OK` 的行，原因是 sleeve_weights 包含 warmup 期 trade_date，这些日期不在 phase2 portfolio period_end map 中，`dict.get(signal_date, 0)` 返回默认值 0 但未被拦截。

## 修复

修改 `_build_router_opportunity_cost`：

1. `pe_map.get(signal_date)` 返回 `None`（不再用默认值 0）
2. `signal_date == 0` → `INVALID_SIGNAL_DATE`
3. `period_end is None or period_end == 0` → `OUT_OF_BACKTEST_WINDOW`
4. 只有通过检查的行才标记 `status="OK"`
5. `oracle_rows`（→ `sleeve_hindsight_oracle.csv`）只写 OK 行
6. `opp_rows`（→ `router_opportunity_cost.csv`）写所有行用于审计
7. 报告新增排除行统计

## 验证

```text
router_opportunity_cost.csv: 1850 rows (1198 OK + 652 OUT_OF_BACKTEST_WINDOW)
ok period_end zero: 0 ✅
ok signal_date zero: 0 ✅

sleeve_hindsight_oracle.csv: 1198 rows (all OK)
ok period_end zero: 0 ✅
```

## 测试

31 tests passed（新增 4 个 oracle warmup 测试）

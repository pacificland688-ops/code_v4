# Panic Basket Gate 最终验收剩余问题整改开发方案

## 1. 背景与当前状态

本文档针对 `panic_basket_daily_gate` 整改版审核后仍存在的问题制定最终验收整改方案。本文只描述开发方案、修复口径和验收标准，不包含代码实现。

上一轮整改已经基本修复以下问题：

- 日级 `basket_label_available_date` 已保留。
- walk-forward 已接入 `label_available_date + embargo` 审计。
- Phase 4 规则阈值已改为训练期冻结。
- `gate_label` 已不再作为策略列进入比较。
- `event_ratio` 已使用全市场分母，不再恒等于 1。
- ML 特征选择已改为训练期内完成。
- Go/No-Go 已按 primary strategy 判断。

当前验证结果：

- 测试：`97 passed, 5 skipped, 2 warnings`
- Phase 1-4 可重跑。
- Phase 2 主规则策略：`NO-GO`
- Phase 3 ML 事件日前瞻层面：`GO`
- Phase 4 真实路径近似模拟：`NO-GO`
- 最终状态仍必须保持：

```text
research_only = true
production_eligible = false
```

当前剩余问题集中在三类：

1. Phase 4 路径模拟仍是近似，不是真实组合 PnL。
2. embargo 使用的是 basket 样本日历，不是全市场交易日历。
3. 输出目录仍残留旧版 CSV，存在误用风险。

## 2. 总体目标

本轮整改目标不是提升收益，而是完成最终验收所需的口径收敛：

1. 将 Phase 4 从“近似路径模拟”升级为“基于事件成分股每日收益的真实路径回测”。
2. 将 embargo 日历改为全市场交易日历，确保审计口径与方案一致。
3. 清理或隔离旧产物，避免后续报告、脚本或人工读取旧文件。
4. 补充针对剩余问题的单测和产物验收检查。
5. 重跑 Phase 1-4 后重新给出最终 Go/No-Go。

完成后仍不代表直接上线。只有真实路径回测也通过，才允许进入下一阶段组合集成研究。

## 3. P0 修复一：Phase 4 真实路径回测

### 3.1 当前问题

当前 `scripts/build_panic_sleeve_gate_validation.py` 的路径模拟虽然已经拆分出 path simulation，但仍使用如下近似：

```text
daily_return = basket_mean_fwd_ret_20d / HOLDING_DAYS
```

这不是实际组合 PnL，原因是：

- 没有记录每个 `ALLOW` 事件日的具体股票成分。
- 没有使用成分股每日真实收益。
- 没有按实际持仓日期逐日更新 tranche。
- 成本被简化为每日扣除，而不是按建仓/平仓换手扣除。
- 无法计算真实仓位、换手、股票数量、容量和回撤。

该口径只能作为粗略诊断，不能作为最终路径验收。

### 3.2 修复目标

新增真实路径回测逻辑：

```text
每个 ALLOW basket day 生成一个 tranche。
tranche 在 exec_date 建仓。
tranche 持有 20 个交易日。
tranche 内股票为该 signal date 的 panic event 股票。
tranche 每日收益来自这些股票在实际持有日的日收益。
多个 tranche 重叠时，按活跃 tranche 数量或固定资本权重归一。
组合每日收益 = 所有 active tranche 加权每日收益 - 当日交易成本。
```

### 3.3 必须新增的中间数据

Phase 1 或 Phase 4 必须保留可回溯到股票级事件的信息。

建议新增股票级事件样本输出：

- `panic_basket_event_stock_samples.parquet`

必须包含字段：

- `signal_date`
- `exec_date`
- `exit_date`
- `ts_code`
- `factor_value`
- `basket_label_available_date`
- `fwd_ret_20d`
- `ab_label`
- `quality_pass_20d`

如果不想在 Phase 1 输出大文件，也可以在 Phase 4 重新从 factor、prices、gate signals 中构造成分，但必须输出最终的成分审计文件。

建议新增：

- `panic_sleeve_gate_tranche_constituents.parquet`

字段：

- `strategy`
- `window`
- `signal_date`
- `exec_date`
- `exit_date`
- `ts_code`
- `entry_price`
- `exit_price`
- `n_stocks_in_tranche`
- `stock_weight_in_tranche`
- `tranche_weight`

### 3.4 每日收益计算口径

股票日收益：

```text
stock_ret_{d} = adj_close_d / adj_close_{prev_trade_date} - 1
```

tranche 日收益：

```text
tranche_ret_d = mean(stock_ret_d of active constituent stocks)
```

组合日收益：

```text
portfolio_ret_d = sum(tranche_weight_d * tranche_ret_d) - trading_cost_d
```

权重建议先使用简单口径：

```text
active_tranche_count = 当日未到期 tranche 数量
tranche_weight = min(1 / active_tranche_count, 1 / max_tranches)
stock_weight_in_tranche = 1 / n_stocks_in_tranche
max_tranches = 20
```

如果 active tranche 数量小于 20，可以选择：

- 满仓归一：`tranche_weight = 1 / active_tranche_count`
- 固定资本占用：`tranche_weight = 1 / 20`

建议默认使用固定资本占用，更保守且更接近“每日最多开一笔、20 日持有”的资本占用逻辑。

### 3.5 成本口径

成本不得再按每日 active tranche 固定扣除。建议使用交易事件扣费：

```text
entry_cost = entry_turnover * cost_bps
exit_cost = exit_turnover * cost_bps
```

最低实现：

- 建仓日扣 `20bps * tranche_weight`
- 平仓日扣 `20bps * tranche_weight`

如果暂时无法精确计算个股换手，先按 tranche 权重估算，但必须在报告中明确。

### 3.6 必须输出

新增或替换以下产物：

- `panic_sleeve_gate_real_path_daily_returns.csv`
- `panic_sleeve_gate_real_path_compare.csv`
- `panic_sleeve_gate_real_path_yearly_attribution.csv`
- `panic_sleeve_gate_real_path_drawdown_report.md`
- `panic_sleeve_gate_tranche_constituents.parquet`
- `panic_sleeve_gate_tranche_audit.csv`

`panic_sleeve_gate_real_path_daily_returns.csv` 必须包含：

- `trade_date`
- `strategy`
- `daily_gross_return`
- `daily_cost`
- `daily_net_return`
- `active_tranches`
- `active_stocks`
- `gross_exposure`
- `turnover`
- `cum_net_return`
- `drawdown`

`panic_sleeve_gate_tranche_audit.csv` 必须包含：

- `strategy`
- `signal_date`
- `exec_date`
- `exit_date`
- `n_stocks`
- `entry_cost`
- `exit_cost`
- `tranche_fwd_ret_20d`
- `realized_path_ret`
- `path_vs_label_diff`

### 3.7 验收标准

必须满足：

- 路径回测不再使用 `basket_mean_fwd_ret_20d / HOLDING_DAYS` 作为每日收益。
- 每个 ALLOW 日期都能追溯到股票级成分。
- `exec_date > signal_date`。
- `exit_date` 晚于 `exec_date` 20 个交易日。
- 每日收益来自实际成分股日收益。
- `gross_exposure <= 1.0`，除非显式设计杠杆。
- `active_tranches <= 20`。
- 成本只在建仓/平仓或换手日扣除。
- 报告明确区分：

  ```text
  event_forward_validation
  real_path_simulation
  ```

只有 `real_path_simulation` 可以输出 annualized return、Sharpe、drawdown 和 cumulative return。

## 4. P1 修复二：使用全市场交易日历执行 embargo

### 4.1 当前问题

当前统一 split 已经执行 `label_available_date + embargo`，但传入的 calendar 来自 `daily_basket.trade_date`。由于 panic basket 是周频/事件日样本，calendar 实际不是全市场交易日历。

这会导致：

```text
embargo_days=20
```

被解释为约 20 个 basket 日期，而不是 20 个真实交易日。

当前偏保守，不构成前视泄露，但与方案和报告中的“20 个交易日 embargo”不一致。

### 4.2 修复要求

所有 Phase 2、Phase 3、Phase 4 的 `split_train_test` 必须传入全市场交易日历。

全市场交易日历来源优先级：

1. `prices_adj` 全市场 `trade_date`
2. 统一交易日历表，如果项目已有 calendar 数据
3. 指数行情交易日历

禁止使用：

```text
daily_basket.trade_date
```

作为 embargo 交易日历。

### 4.3 实现建议

在 `panic_gate_shared.py` 中新增或调整：

```text
load_market_calendar(root, start, end) -> np.ndarray
```

或者让调用方显式传入：

```text
market_calendar = build_trading_calendar(prices_adj)
```

同时在 audit 中新增：

- `calendar_source`
- `calendar_n_days`
- `embargo_cutoff_date`
- `calendar_is_full_market`

### 4.4 验收标准

必须满足：

- audit 中 `calendar_source = prices_adj_full_market` 或等价说明。
- `calendar_n_days` 应接近全市场交易日数量，而不是 408 个 basket day。
- `embargo_cutoff_date` 非空。
- `max_train_trade_date_after_filter <= embargo_cutoff_date`。
- 单测覆盖：当 basket 日期稀疏时，embargo 仍按全市场交易日计算。

## 5. P1 修复三：旧产物清理与防误用

### 5.1 当前问题

输出目录中仍残留旧版文件：

- `panic_sleeve_gate_backtest_compare.csv`
- `panic_sleeve_gate_daily_signals.csv`
- `panic_sleeve_gate_yearly_attribution.csv`

这些文件来自旧实现，时间戳早于整改版输出，且命名上容易被误认为当前有效产物。

### 5.2 修复要求

必须建立产物版本治理机制。

可选方案 A：移动旧产物

```text
outputs/analysis/panic_reversal_gate/daily_basket_v1/deprecated/
```

将旧文件移动进去，并生成：

- `deprecated_manifest.json`

记录：

- `file`
- `deprecated_reason`
- `deprecated_at`
- `replacement_file`

可选方案 B：每次运行前清理输出

在 Phase 4 开始前清理本脚本历史产物，但必须避免误删其他阶段输出。

推荐只清理白名单：

- `panic_sleeve_gate_backtest_compare.csv`
- `panic_sleeve_gate_daily_signals.csv`
- `panic_sleeve_gate_yearly_attribution.csv`

可选方案 C：输出新版本目录

例如：

```text
daily_basket_v2_real_path/
```

这是最干净的方案，但会增加后续路径迁移成本。

### 5.3 推荐方案

推荐采用 A + B：

1. 首次修复时将旧产物移动到 `deprecated/`。
2. 后续 Phase 4 每次运行前检查旧文件是否存在。
3. 如果存在，移动到 `deprecated/` 或报错阻断运行。
4. 报告和 manifest 中只引用新产物。

### 5.4 验收标准

必须满足：

- 主输出目录下不再出现旧版 `panic_sleeve_gate_backtest_compare.csv`。
- 主输出目录下不再出现旧版 `panic_sleeve_gate_daily_signals.csv`。
- 主输出目录下不再出现旧版 `panic_sleeve_gate_yearly_attribution.csv`。
- 如果保留旧文件，必须位于 `deprecated/` 且 manifest 明确 deprecated。
- 新报告不得引用旧文件。

## 6. P1 修复四：新增最终 manifest

### 6.1 当前问题

Phase 1 有 manifest，但 Phase 4 最终验收没有统一 machine-readable manifest 来表达最终结论。

### 6.2 修复要求

新增：

- `panic_basket_gate_final_manifest.json`

必须包含：

```json
{
  "schema": "panic_basket_gate.final_acceptance.v1",
  "research_only": true,
  "production_eligible": false,
  "final_status": "NO_GO",
  "primary_strategy": "gate_ml_logreg",
  "leakage_audit": "PASS",
  "threshold_audit": "PASS",
  "event_forward_status": "PASS_OR_FAIL",
  "real_path_status": "PASS_OR_FAIL",
  "block_reasons": [],
  "valid_output_files": [],
  "deprecated_output_files": []
}
```

### 6.3 Go/No-Go 口径

最终 `GO` 必须同时满足：

- leakage audit PASS
- threshold audit PASS
- primary strategy event-forward net spread lift > 0
- primary strategy real path cumulative return > 0
- primary strategy real path max drawdown 不恶化到预设阈值
- 至少 2/3 样本外年份 real path net return 为正
- 成本后仍为正
- 无旧产物误用风险

否则：

```text
final_status = NO_GO
production_eligible = false
```

## 7. P2 修复五：报告编码与可读性

### 7.1 当前问题

部分控制台输出和文件中仍有乱码字符，例如 `鈥?`、`Ён` 等。这不影响数值，但影响审核和复现可读性。

### 7.2 修复要求

逐步替换脚本注释、报告文案和 print 文本中的非 ASCII 装饰符。

建议统一：

- `->` 代替箭头
- `PASS` / `FAIL` 代替勾叉
- 普通横线分隔，避免 box drawing 字符
- Markdown 标题和表格保持 UTF-8

### 7.3 验收标准

必须满足：

- 新生成报告中无明显乱码。
- 控制台输出中无明显乱码。
- 不影响 CSV 字段名和数值。

## 8. P2 修复六：补充测试

### 8.1 必须新增或加强的测试

当前新增测试已有覆盖，但需要补充针对本轮剩余问题的测试。

建议新增：

- `tests/test_panic_basket_real_path.py`
- `tests/test_panic_gate_calendar_and_outputs.py`

最低测试点：

1. 真实路径回测不调用 `basket_mean_fwd_ret_20d / HOLDING_DAYS` 作为每日收益。
2. tranche constituent 能从 signal date 追溯到股票列表。
3. `exec_date > signal_date`。
4. `exit_date` 是 exec date 后第 20 个全市场交易日。
5. active tranches 不超过 20。
6. gross exposure 不超过 1。
7. 成本只在交易日或换手日扣除。
8. embargo 使用全市场交易日历，不使用 basket 日期。
9. 旧产物不会留在主输出目录。
10. final manifest 存在且状态与报告一致。

### 8.2 回归测试命令

修复后至少运行：

```text
python -m pytest tests/test_panic_reversal.py tests/test_panic_ab_pretrade_predictor.py tests/test_panic_basket_daily_gate.py tests/test_panic_basket_real_path.py tests/test_panic_gate_calendar_and_outputs.py -q
```

## 9. 重新运行流程

修复完成后按以下顺序执行：

1. 重建日级样本：

```text
python scripts/build_panic_basket_daily_gate.py
```

2. 重跑规则 gate：

```text
python scripts/build_panic_basket_rule_gate.py
```

3. 重跑 ML gate：

```text
python scripts/build_panic_basket_ml_gate.py
```

4. 重跑真实路径 sleeve 验证：

```text
python scripts/build_panic_sleeve_gate_validation.py
```

5. 跑测试：

```text
python -m pytest tests/test_panic_reversal.py tests/test_panic_ab_pretrade_predictor.py tests/test_panic_basket_daily_gate.py tests/test_panic_basket_real_path.py tests/test_panic_gate_calendar_and_outputs.py -q
```

## 10. 最终验收清单

### 10.1 数据口径

- `event_ratio` 使用全市场分母。
- `basket_label_available_date` 存在且用于训练过滤。
- `embargo_cutoff_date` 基于全市场交易日历。
- 所有 ALLOW tranche 都有股票级成分。

### 10.2 前视控制

- `max_train_label_available_date_after_filter < min_test_trade_date`。
- `max_train_trade_date_after_filter <= embargo_cutoff_date`。
- 阈值和模型只使用训练期。
- 特征选择只使用训练期。

### 10.3 路径回测

- 每日收益来自成分股实际日收益。
- 成本按建仓/平仓或换手扣除。
- `gross_exposure <= 1`。
- `active_tranches <= 20`。
- 输出每日收益、累计收益、回撤、仓位、换手、成本。

### 10.4 产物治理

- 旧版 CSV 不在主输出目录。
- final manifest 存在。
- 报告和 manifest 状态一致。
- 报告不引用 deprecated 文件。

### 10.5 最终判定

如果真实路径回测仍为负，则最终必须是：

```text
final_status = NO_GO
research_only = true
production_eligible = false
recommended_next_action = keep_as_diagnostic_or_research_only
```

如果真实路径回测转正，也不能直接上线，只能进入下一阶段：

```text
next_stage = full_portfolio_integration_research
```

## 11. 建议实施顺序

1. 先修复全市场交易日历和 audit 字段。
2. 清理或隔离旧产物。
3. 新增股票级 tranche constituent 输出。
4. 重写 Phase 4 real path simulation。
5. 新增 final manifest。
6. 修复报告乱码。
7. 新增测试。
8. 重跑 Phase 1-4。
9. 重新审核 final manifest、报告和核心 CSV。

## 12. 最终定位

本轮修复完成前，该因子仍只能定位为：

```text
use_case = panic event diagnostic / panic basket gate research
not_use_case = stock selector / direct portfolio alpha / production live filter
```

只有在真实路径回测、成本容量、组合集成、多重检验全部通过后，才允许讨论生产化。


# Panic Basket Daily Gate 审核问题整改开发方案

## 1. 背景与结论

本文档针对 `panic_basket_daily_gate` 方案完成后的审核问题制定整改开发方案。本文只描述修复目标、实现口径、验收标准和执行顺序，不包含代码实现。

当前已完成的新增脚本包括：

- `scripts/build_panic_basket_daily_gate.py`
- `scripts/build_panic_basket_rule_gate.py`
- `scripts/build_panic_basket_ml_gate.py`
- `scripts/build_panic_sleeve_gate_validation.py`

当前主要输出目录：

- `outputs/analysis/panic_reversal_gate/daily_basket_v1`

审核结论：

```text
当前版本不通过验收。
当前 GO 结论不能采信。
当前状态必须保持 research_only / production_eligible=false。
```

主要原因：

- walk-forward 训练未严格执行 `label_available_date + embargo`。
- Phase 4 规则 gate 存在测试集取阈值。
- Phase 4 误把 `gate_label` 当作可执行 gate 策略。
- `event_ratio` 构造错误，当前恒等于 1.0。
- ML 特征筛选在全样本上完成，存在测试期分布参与特征选择的问题。
- ML 报告用测试集选择 best model / threshold 后判断 GO。
- sleeve 验证把重叠 20 日前瞻收益当作逐日收益年化，不能视为真实组合 PnL。

整改目标不是让结果变好，而是让验证口径可信。修复完成后必须重新跑 Phase 1-4，并重新审核。

## 2. 总体整改原则

所有修复必须遵守以下原则：

1. 所有训练样本必须在测试窗口开始前已经知道标签。
2. 所有训练样本必须与测试窗口之间保留 embargo。
3. 所有阈值、分位、标准化、特征选择、模型选择只能使用训练期数据。
4. 测试集只能用于一次性评估，不能用于选择模型、阈值或策略。
5. 任何报告中的 `GO` 必须基于预先冻结的主策略，而不是测试集中表现最好的策略。
6. 未重新通过验收前，所有输出必须标记为 `research_only=true`、`production_eligible=false`。

## 3. P0 修复一：日级 label availability 与 embargo

### 3.1 问题

Phase 1 在股票事件层生成了 `label_available_date`，但日级 basket 聚合后没有保留该字段。Phase 2、Phase 3、Phase 4 在 walk-forward 中只按年份切训练/测试，没有使用：

```text
label_available_date < test_start_trade_date
```

也没有真正落实：

```text
训练样本距离 test_start 至少 20 个交易日 embargo
```

这会导致训练集中包含测试开始时还无法确认标签的样本，构成前视风险。

### 3.2 修复要求

在 Phase 1 日级样本中新增并保留：

- `max_event_label_available_date`
- `min_event_label_available_date`
- `n_events_label_available`
- `n_events_label_unavailable`
- `basket_label_available_date`

推荐口径：

```text
basket_label_available_date = max(label_available_date of all events in that daily basket)
```

原因：日级 basket 标签依赖当天所有事件的未来收益路径，只有最后一个事件标签可得后，整条日级标签才可用于训练。

在 Phase 2、Phase 3、Phase 4 的每个 walk-forward 窗口中，训练集必须改为：

```text
train_raw = years in train window
test_start_trade_date = first trading day of test year
train_label_available = basket_label_available_date < test_start_trade_date
embargo_cutoff_date = test_start_trade_date - 20 trading days
train_final = train_label_available and trade_date <= embargo_cutoff_date
```

如果 `basket_label_available_date` 缺失，该样本不得进入训练。

### 3.3 必须输出的审计字段

每个 walk-forward 窗口必须输出 leakage audit：

- `window`
- `test_start_trade_date`
- `train_rows_raw`
- `train_rows_after_label_availability`
- `label_unavailable_dropped_rows`
- `label_unavailable_dropped_pct`
- `train_rows_after_embargo`
- `embargo_dropped_rows`
- `embargo_dropped_pct`
- `max_train_trade_date_after_filter`
- `max_train_label_available_date_after_filter`
- `min_test_trade_date`
- `leakage_control_mode`
- `embargo_days`

建议输出文件：

- `panic_basket_gate_leakage_audit.csv`

### 3.4 验收标准

必须满足：

- 每个有效窗口都有 leakage audit 记录。
- `max_train_label_available_date_after_filter < min_test_trade_date`。
- `max_train_trade_date_after_filter <= embargo_cutoff_date`。
- 报告明确显示 `leakage_control=label_available_plus_embargo`。
- 若任一窗口违反上述条件，最终状态必须为 `NO-GO`。

## 4. P0 修复二：Phase 4 规则 gate 阈值必须训练期冻结

### 4.1 问题

Phase 4 当前规则 gate 使用：

```text
threshold = test_gates[col].quantile(0.80)
```

这等于在测试集上取 top 20% 阈值。虽然没有直接使用收益标签，但使用了测试窗口的分布信息，不符合预交易冻结规则，也会让覆盖率被人为固定。

### 4.2 修复要求

Phase 4 规则 gate 必须复用 Phase 2 的 walk-forward 阈值逻辑：

1. 在 train window 上计算规则分数。
2. 在 train window 上计算阈值。
3. 将阈值冻结后应用到 test window。

推荐输出每个窗口的阈值表：

- `window`
- `strategy`
- `score_column`
- `top_pct`
- `threshold_source`
- `threshold_value`
- `n_train_scores`
- `n_test_scores`

建议输出文件：

- `panic_sleeve_gate_threshold_audit.csv`

### 4.3 验收标准

必须满足：

- Phase 4 不允许出现基于 `test_gates[col].quantile(...)` 的阈值。
- 报告中必须写明阈值来源为 train window。
- Phase 4 的 rule gate 与 Phase 2 同名策略在同一窗口上的 allow 日期应一致。
- 若 Phase 4 规则 gate 覆盖率固定为接近 20%，需要确认是训练阈值自然产生，而不是测试集分位强行固定。

## 5. P1 修复三：排除 `gate_label` 等非策略列

### 5.1 问题

Phase 4 中 `gate_cols` 捕获所有 `gate_` 前缀列，导致 `gate_label` 也被当作 gate 策略评估，输出中出现无意义的 `gate_label` 策略。

### 5.2 修复要求

明确 gate 策略列白名单，不允许用前缀模糊匹配。

推荐白名单：

- `gate_rule_panic_intensity`
- `gate_rule_market_stress`
- `gate_rule_breadth`
- `gate_rule_liquidity`
- `gate_rule_composite`
- `gate_ml_logreg`

或者在生成 gate 时同时输出：

```text
GATE_STRATEGY_COLS = [...]
```

Phase 4 只能评估白名单列。

### 5.3 验收标准

必须满足：

- `panic_sleeve_gate_backtest_compare.csv` 中不得出现 `gate_label` 策略。
- `panic_sleeve_gate_yearly_attribution.csv` 中不得出现 `gate_label` 策略。
- 单测覆盖：含有 `gate_label` 列时，策略提取函数不会返回它。

## 6. P1 修复四：修正 `event_ratio`

### 6.1 问题

当前日级样本中 `event_ratio` 恒等于 1.0。原因是 `total_stocks` 来自 event-only 的 `stock_samples`，而不是当天全市场可交易股票数量。

这会导致：

- panic ratio 特征无效。
- panic intensity 诊断不完整。
- 市场恐慌扩散程度无法度量。

### 6.2 修复要求

Phase 1 构造 `event_ratio` 时，分母必须来自全市场当日可观察股票数，而不是事件样本数。

推荐口径：

```text
total_stocks = count distinct ts_code in prices_adj on trade_date
tradable_stocks = optional: after filters such as price valid / not suspended / not ST if data available
event_count = count panic events on trade_date
event_ratio = event_count / total_stocks
```

如果能获得交易状态、ST、涨跌停数据，则同时输出：

- `total_stocks_raw`
- `total_stocks_tradable`
- `event_ratio_raw`
- `event_ratio_tradable`

短期最小修复可以先使用 `prices_adj` 当日有有效 `adj_close` 的股票数作为分母。

### 6.3 验收标准

必须满足：

- `event_ratio` 不得恒等于 1.0。
- `event_ratio` 必须在 `[0, 1]` 区间。
- `event_count <= total_stocks`。
- 日级 diagnostics 报告 `avg_event_ratio`、分位数和年份分布。
- 单测覆盖：给定 100 只股票、10 个事件，`event_ratio=0.1`。

## 7. P1 修复五：ML 特征筛选必须在训练期内完成

### 7.1 问题

Phase 3 当前在 walk-forward 循环前执行：

```text
feature_cols = get_feature_columns(df)
```

其中缺失率过滤和方差排序使用了全样本，包括未来测试年份。这属于测试期分布参与特征选择，存在轻度前视和过拟合风险。

### 7.2 修复要求

特征筛选必须移动到每个 walk-forward 窗口内部：

```text
for each window:
    train_final = leakage-filtered train
    feature_cols = get_feature_columns(train_final)
    X_train = train_final[feature_cols]
    X_test = test[feature_cols]
```

所有以下操作都只能 fit 在训练期：

- 缺失率过滤
- 方差过滤
- 特征数量截断
- imputer
- scaler
- 模型

测试集只允许 transform / predict。

### 7.3 必须输出

新增特征审计表：

- `window`
- `model`
- `n_features`
- `feature_columns`
- `feature_selection_source`
- `max_missing_rate_train`
- `max_missing_rate_test`

建议输出文件：

- `panic_basket_gate_model_feature_audit.csv`

### 7.4 验收标准

必须满足：

- 每个窗口都有独立 `feature_columns`。
- `feature_selection_source=train_only`。
- 不允许在循环外用全样本确定最终特征。
- 单测覆盖：未来年份新增高方差列时，不应影响当前训练窗口的特征列表。

## 8. P1 修复六：GO 判定不能使用测试集择优策略

### 8.1 问题

当前 ML 报告按全测试窗口平均 `net_spread_lift` 排序，选择 best model / threshold 后再判断 `GO`。这会把测试集用于策略选择。

Phase 2 规则报告也存在类似问题：报告多个 top_pct 后，容易把表现最好的一个当结论。

### 8.2 修复要求

必须定义“主策略”和“候选策略”两层。

主策略在运行前固定，不允许根据测试表现选择。

建议冻结主策略：

```text
Phase 2 primary_rule_strategy = composite_top_50pct
Phase 3 primary_model = logreg
Phase 3 primary_gate_threshold = 0.60
Phase 4 primary_gate_strategy = gate_ml_logreg
```

注意：上述只是建议，最终应在代码配置中显式写入。无论选择哪个主策略，都必须在测试前冻结。

报告口径：

- `primary_strategy_result`: 用于 Go/No-Go。
- `candidate_strategy_compare`: 只作为研究附录。
- `best_strategy_in_test`: 必须标记为 diagnostics only，不能用于 Go。

### 8.3 验收标准

必须满足：

- manifest 中必须有 `primary_strategy`。
- Go/No-Go 只能基于 `primary_strategy`。
- 报告允许展示 best candidate，但必须标记 `diagnostic_only=true`。
- 如果 primary 不通过，即使某个候选通过，也不能整体标记 GO。

## 9. P1 修复七：sleeve 回测口径重做

### 9.1 问题

当前 Phase 4 把每个事件日的 20 日前瞻收益当作当天收益逐日累加，并年化：

```text
raw_daily = basket_mean_fwd_ret_20d - COST_BPS
annualized_return = raw_daily.mean() * 252
```

这不是实际组合 PnL。因为 20 日持有期收益高度重叠，不能当作独立日收益逐日累加。

### 9.2 修复方向

需要将 Phase 4 分成两个层次：

#### 层次 A：事件日标签验证

仍然可以保留：

- `basket_mean_fwd_ret_20d`
- `basket_net_fwd_ret_20d`
- `net_spread_lift`
- `A-rate lift`
- `win-rate lift`

但这些只能称为：

```text
event_day_forward_return_validation
```

不能称为：

```text
daily PnL / annualized return / Sharpe
```

#### 层次 B：组合 sleeve 模拟

若要模拟真实 sleeve，需要展开持仓路径：

1. 每个 `ALLOW` 事件日在 `exec_date` 建仓。
2. 每个事件持有 20 个交易日，或按既定退出规则退出。
3. 每天组合收益来自所有未到期事件的当日收益。
4. 多个事件重叠时，按资本分配规则控制总仓位。
5. 每日总仓位不得超过预设上限。
6. 成本在建仓和退出时扣除，而不是简单每个事件日扣一次。

建议最小可实现口径：

```text
每个 ALLOW basket day 建立一个等权 basket tranche。
每个 tranche 持有 20 个交易日。
组合每天最多持有 20 个活跃 tranche。
每个 active tranche 权重 = 1 / 20，或按 active tranche 数量归一。
每日 sleeve return = sum(active_tranche_daily_returns * weights) - turnover_cost。
```

### 9.3 必须输出

保留事件日验证：

- `panic_sleeve_gate_event_forward_compare.csv`

新增真实路径模拟：

- `panic_sleeve_gate_path_daily_returns.csv`
- `panic_sleeve_gate_path_compare.csv`
- `panic_sleeve_gate_path_yearly_attribution.csv`
- `panic_sleeve_gate_path_drawdown_report.md`

### 9.4 验收标准

必须满足：

- 报告中不得把 20 日前瞻收益均值年化为 daily Sharpe。
- 若没有路径模拟，只能输出 event-forward validation，不能输出 annualized return / Sharpe。
- 真实 sleeve path 必须包含每日收益、累计收益、回撤、仓位、换手、成本。
- Go/No-Go 中的组合层结论只能基于真实路径模拟。

## 10. P2 修复八：报告编码与可读性

### 10.1 问题

当前部分脚本和报告中出现乱码字符，例如箭头、勾叉或特殊符号在 Windows 控制台/文件中显示异常。

### 10.2 修复要求

报告和脚本注释统一使用 UTF-8，并优先使用 ASCII 符号。

建议替换：

- `→` 改为 `->`
- `✓` 改为 `PASS`
- `✗` 改为 `FAIL`
- `Δ` 改为 `delta`

### 10.3 验收标准

必须满足：

- 新报告在 Windows PowerShell 中读取无明显乱码。
- Markdown 中不出现异常替换字符。
- 不影响 CSV 字段名。

## 11. P2 修复九：补充单元测试与验收测试

### 11.1 当前缺口

现有测试通过：

```text
tests/test_panic_reversal.py
tests/test_panic_ab_pretrade_predictor.py
```

但没有覆盖新增脚本：

- `build_panic_basket_daily_gate.py`
- `build_panic_basket_rule_gate.py`
- `build_panic_basket_ml_gate.py`
- `build_panic_sleeve_gate_validation.py`

### 11.2 必须新增测试

建议新增：

- `tests/test_panic_basket_daily_gate.py`
- `tests/test_panic_basket_rule_gate.py`
- `tests/test_panic_basket_ml_gate.py`
- `tests/test_panic_sleeve_gate_validation.py`

最低测试覆盖：

1. `event_ratio` 使用全市场分母。
2. 日级 `basket_label_available_date` 使用事件最大标签可得日。
3. walk-forward 训练集过滤 `label_available_date < test_start`。
4. embargo 会剔除测试前 20 个交易日内的训练样本。
5. Phase 4 规则阈值来自训练期，不来自测试期。
6. `gate_label` 不会被识别为策略列。
7. ML 特征选择只用训练期。
8. primary strategy 不通过时，候选策略通过也不能整体 GO。
9. 没有真实路径模拟时，报告不得输出 annualized return / Sharpe。
10. 路径模拟中 active tranche 权重和总仓位不超过上限。

### 11.3 验收命令

修复后至少运行：

```text
python -m pytest tests/test_panic_reversal.py tests/test_panic_ab_pretrade_predictor.py -q
python -m pytest tests/test_panic_basket_daily_gate.py tests/test_panic_basket_rule_gate.py tests/test_panic_basket_ml_gate.py tests/test_panic_sleeve_gate_validation.py -q
```

## 12. 重新运行流程

修复完成后，按以下顺序重新运行：

1. Phase 1 日级样本：

   ```text
   python scripts/build_panic_basket_daily_gate.py
   ```

2. Phase 2 规则 gate：

   ```text
   python scripts/build_panic_basket_rule_gate.py
   ```

3. Phase 3 ML gate：

   ```text
   python scripts/build_panic_basket_ml_gate.py
   ```

4. Phase 4 sleeve 验证：

   ```text
   python scripts/build_panic_sleeve_gate_validation.py
   ```

5. 单元测试：

   ```text
   python -m pytest tests/test_panic_reversal.py tests/test_panic_ab_pretrade_predictor.py tests/test_panic_basket_daily_gate.py tests/test_panic_basket_rule_gate.py tests/test_panic_basket_ml_gate.py tests/test_panic_sleeve_gate_validation.py -q
   ```

## 13. 最终验收清单

### 13.1 数据与泄露

- `panic_basket_gate_leakage_audit.csv` 存在且非空。
- 所有窗口满足 `max_train_label_available_date < min_test_trade_date`。
- 所有窗口满足 20 交易日 embargo。
- 日级样本包含 `basket_label_available_date`。
- 训练集中没有未来标签不可得样本。

### 13.2 特征与阈值

- `event_ratio` 不恒等于 1。
- ML 特征选择来源为 `train_only`。
- Rule gate 阈值来源为 `train_only`。
- Phase 4 不使用测试集分位设定阈值。
- `gate_label` 不进入策略评估。

### 13.3 报告与结论

- Go/No-Go 只基于 primary strategy。
- 候选策略 best result 标记为 diagnostics only。
- 没有真实路径模拟时，不输出年化收益和 Sharpe。
- 若有路径模拟，必须输出每日路径、仓位、成本、回撤。
- manifest 明确：

  ```text
  research_only = true
  production_eligible = false
  leakage_control = label_available_plus_embargo
  primary_strategy = <frozen primary strategy>
  ```

### 13.4 最低通过条件

只有同时满足以下条件，才允许从“修复验证”进入下一轮研究：

- 无 P0 前视问题。
- 无测试集阈值选择。
- 无全样本特征选择。
- primary strategy 样本外净收益提升为正。
- primary strategy 至少 2/3 有效年份净收益提升为正。
- 真实路径 sleeve 不恶化最大回撤。
- 20bps 成本后仍有正贡献。

若任一 P0 项未满足，最终结论必须为：

```text
NO-GO
research_only = true
production_eligible = false
recommended_next_action = fix_leakage_and_rerun
```

## 14. 建议实施顺序

推荐按以下顺序修复，避免后续返工：

1. 修复 Phase 1 日级 `basket_label_available_date` 和 `event_ratio`。
2. 抽象统一 walk-forward split 函数，包含 label availability 和 embargo。
3. Phase 2 接入统一 split，并输出 leakage audit。
4. Phase 3 接入统一 split，并把特征选择移动到窗口内部。
5. Phase 4 复用 Phase 2/3 的冻结 gate 信号，不在测试集重新取阈值。
6. Phase 4 排除 `gate_label`，使用策略白名单。
7. 将事件日前瞻验证与真实路径 sleeve 模拟拆开。
8. 修复报告 Go/No-Go 逻辑，只基于 primary strategy。
9. 修复报告乱码和字段说明。
10. 新增单元测试。
11. 重跑 Phase 1-4。
12. 重新审核产物。

## 15. 最终定位

即使本轮整改完成，也不代表该因子可以直接上线。整改完成后的目标只是让研究结论可信。

修复后仍应保持：

```text
use_case = panic event diagnostic / panic basket gate research
not_use_case = stock selector / direct portfolio alpha / live production filter
```

只有在重新验收通过，并通过真实组合回测、成本容量验证和多重检验后，才允许讨论进入下一阶段集成。


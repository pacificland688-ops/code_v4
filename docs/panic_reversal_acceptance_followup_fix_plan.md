# Panic Reversal 验收失败后续修复方案

## 1. 当前验收结论

本轮审核结论为：不通过验收。

原因不是 panic reversal 因子构造本身出现硬前视，而是正式 gate、收益口径、成本诊断、regime 诊断、walk-forward 和多重检验仍未形成可信闭环。当前输出产物不能用于判断因子是否有效。

本方案只覆盖本轮验收失败后必须修复的事项。上一版总方案见：

- `docs/panic_reversal_optimization_development_plan.md`

## 2. 阻塞问题清单

### 2.1 正式 gate 未使用 t+1 执行收益

现状：

- `scripts/evaluate_panic_reversal_diagnostics.py` 仍从 `factor_name=fwd_returns` 读取 `fwd_ret_5d`。
- `panic_lag1_returns.parquet` 只被 `panic_fast_check.py` 和 `panic_walkforward_validate.py` 使用。
- 正式 `panic_reversal_report.md` 没有使用 `execution_lag=1` 口径。

风险：

- 因子信号依赖 `close_t`，若评估 `close_t -> close_{t+5}`，隐含同日收盘可交易。
- 交易时点前视风险未解除。

### 2.2 lag1 收益存在极端异常

现状：

- `panic_lag1_returns.parquet` 中 `fwd_ret_5d_exec_lag1` 最大值约 `9737.57`。
- `abs(return) > 1` 的样本约 `0.14%`。
- holdout 高收益明显受 2024 年末异常值驱动，例如 2024-12-27 附近多个样本出现数百倍到数千倍 5 日收益。

风险：

- walk-forward 和 holdout net spread 被异常值污染。
- 任何基于当前 lag1 收益的 PASS 结论都不可信。

### 2.3 成本/流动性诊断仍未执行

现状：

- `cost_liquidity_analysis(...)` 在 `evaluate_panic_reversal_diagnostics.py` 主循环中仍被注释。
- `panic_cost_liquidity.csv` 不存在。

风险：

- P1 成本压力测试未完成。
- 无法判断 filtered 样本是否集中在小市值、低成交额、高换手股票。

### 2.4 regime 输出字段仍错误

现状：

- `rd["factor"] = rd_src` 仍会把真实因子名覆盖为 regime 来源。
- 缺少 `regime_source`。
- 缺少 `diagnostic_only` 标记。

风险：

- `panic_regime_diagnostic.csv` 无法追溯到具体因子。
- 全样本分位 regime 可能被误用为硬开关，造成样本内过拟合。

### 2.5 正式产物未重跑

现状：

- `panic_reversal_report.md` 仍是旧报告，生成时间为 `2026-06-28 22:07:52`。
- `panic_variant_summary.csv` 仍是 fast check 简化列。
- 当前 summary 没有 `p0_status`。

风险：

- 验收人员看到的不是修复后正式 gate 结果。
- 旧报告仍包含旧口径下的 PASS 结论，容易误导决策。

### 2.6 多重检验产物缺失

现状：

- `panic_walkforward_validate.py` 声称输出 `panic_multiple_testing_check.csv`。
- 实际文件不存在。

风险：

- 27 个候选同时扫描后的数据挖掘风险没有被量化。
- 不能证明最佳候选不是多重检验噪声。

### 2.7 walk-forward 不是冻结选择口径

现状：

- `panic_walkforward_validation.csv` 每个窗口输出全部 27 个候选。
- 脚本只是打印 best，没有把每个窗口的冻结选择结果单独落表。
- `pass_ratio` 是所有候选行的均值，不是每个窗口选定候选的 pass ratio。

风险：

- walk-forward 结果仍带有候选池后验选择成分。
- 不能作为过拟合控制证据。

## 3. 修复目标

1. 正式 gate 默认使用清洗后的 `fwd_ret_5d_exec_lag1`。
2. lag1 收益生成逻辑通过数据质量审查，剔除或标记异常复权/边界样本。
3. 成本、流动性、冗余、regime、稀疏性、walk-forward、多重检验全部产出可信文件。
4. 正式 report 和 summary 由完整 gate 生成，不再混入 fast check 产物。
5. 最终结论只能基于清洗后的 lag1、冻结 walk-forward 和多重检验结果。

## 4. P0 修复：lag1 收益生成与清洗

### 4.1 修复收益生成脚本

涉及文件：

- `scripts/generate_exec_lag1_returns.py`

要求：

- 继续保留定义：`fwd_ret_5d_exec_lag1 = close_{t+6} / close_{t+1} - 1`。
- 增加收益质量过滤：
  - 删除或标记 `close_t1 <= 0`。
  - 删除或标记 `close_t6 <= 0`。
  - 删除或标记 `abs(fwd_ret_5d_exec_lag1) > 0.5` 的极端收益样本。
  - 单独输出被过滤样本到 `panic_lag1_return_outliers.csv`。
- 增加复权价格连续性检查：
  - 计算 `ret_1d = adj_close / adj_close.shift(1) - 1`。
  - 标记 `abs(ret_1d) > 0.3` 的异常跳变。
  - 若异常跳变落在 `t+1` 到 `t+6` 窗口内，该 forward return 标记为不可用。
- 增加样本边界检查：
  - 若 `t+1` 或 `t+6` 不存在，不能生成 lag1 return。
  - 年末最后若干交易日必须自然 drop，不允许跨缺失或异常数据计算。

输出：

- `panic_lag1_returns.parquet`
- `panic_lag1_return_outliers.csv`
- `panic_lag1_return_quality_summary.csv`
- `panic_return_alignment_check.csv`

验收标准：

- `fwd_ret_5d_exec_lag1` 最大值和最小值在合理范围内，建议默认 `[-0.5, 0.5]`。
- `abs(return) > 0.5` 的样本不进入正式 gate。
- outlier 文件非空时，报告必须显示过滤数量和过滤比例。
- 重新抽查 2024-12-27 异常样本，不得再进入正式收益表。

### 4.2 修复 alignment audit

现状中 `gap_days` 用整数日期相减，跨月/跨年会出现 `8873` 这类无意义数字。

要求：

- 改为真实 calendar day gap：

```python
gap_days = (pd.to_datetime(str(exec_date)) - pd.to_datetime(str(signal_date))).days
```

- 增加 `trade_day_gap`：
  - `execution_date` 必须是 `signal_date` 后第 1 个交易日。

验收标准：

- `execution_date > signal_date`。
- `trade_day_gap == 1`。
- `calendar_gap_days` 可因节假日大于 1，但不应再出现整数日期相减导致的异常值。

## 5. P0 修复：正式 gate 接入 lag1

涉及文件：

- `scripts/evaluate_panic_reversal_diagnostics.py`

要求：

- 新增 `load_exec_lag1_returns()`。
- 默认使用 `outputs/analysis/panic_reversal_gate/panic_lag1_returns.parquet`。
- 将收益列标准化为 `fwd_ret_5d` 供下游指标复用。
- 如果 lag1 文件不存在或质量检查失败，正式 gate 应直接退出失败，不允许 fallback 到 same-day。
- 报告中写明：
  - `execution_lag=1`
  - `return_col=fwd_ret_5d_exec_lag1`
  - `same_day_return_used=false`

验收标准：

- `panic_variant_summary.csv` 中包含 `execution_lag` 和 `return_col`。
- `panic_reversal_report.md` 中显示 `execution_lag=1`。
- 正式 gate 不再读取 same-day `factor_name=fwd_returns` 作为默认收益。

## 6. P0 修复：正式产物生成闭环

要求：

- 正式 gate 成功运行后必须生成并覆盖以下文件：
  - `panic_variant_summary.csv`
  - `panic_event_by_year.csv`
  - `panic_redundancy_corr.csv`
  - `panic_cost_liquidity.csv`
  - `panic_sparsity.csv`
  - `panic_regime_diagnostic.csv`
  - `panic_reversal_report.md`
- `panic_fast_check.py` 只能输出到 `debug/`，不得覆盖正式文件。

验收标准：

- `panic_reversal_report.md` 生成时间为本次运行时间。
- `panic_variant_summary.csv` 包含完整字段：
  - `factor`
  - `direction`
  - `threshold`
  - `signal_type`
  - `execution_lag`
  - `return_col`
  - `mean_rank_ic`
  - `icir`
  - `ev_net_spread`
  - `rk_net_spread`
  - `ev_val_net_spread`
  - `rk_val_net_spread`
  - `ev_val_pos_years`
  - `rk_val_pos_years`
  - `val_n_years`
  - `p0_status`
  - `p0_reason`
- `val_pos_years <= val_n_years`。

## 7. P1 修复：成本/流动性诊断

涉及文件：

- `scripts/evaluate_panic_reversal_diagnostics.py`

要求：

- 恢复 `cost_liquidity_analysis(...)`。
- 修复年度循环为 unique years。
- 输出 filtered vs unfiltered 的市值、成交额、换手和成本压力。

必需字段：

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

验收标准：

- `panic_cost_liquidity.csv` 存在且非空。
- 每个候选至少有年度记录。
- 报告中有成本压力测试汇总。

## 8. P1 修复：regime 诊断字段

涉及文件：

- `scripts/evaluate_panic_reversal_diagnostics.py`

要求：

```python
rd["factor"] = pf
rd["regime_source"] = rd_src
rd["diagnostic_only"] = True
```

不允许将全样本分位 regime 用作硬开关。

验收标准：

- `panic_regime_diagnostic.csv` 中 `factor` 是真实因子名。
- `regime_source` 单独记录。
- `diagnostic_only=true`。

## 9. P1 修复：严格 walk-forward

涉及文件：

- `scripts/panic_walkforward_validate.py`

要求：

- 每个窗口先在 train 内选择唯一候选。
- 冻结该候选后只在 test 年评估。
- 输出 per-window selected factor 表，而不是只输出 27 个候选全集。

新增输出：

- `panic_walkforward_candidates.csv`：每个窗口 27 个候选训练与测试明细。
- `panic_walkforward_selected.csv`：每个窗口冻结选择后的唯一候选。

`panic_walkforward_selected.csv` 字段：

- `window`
- `train_start`
- `train_end`
- `test_start`
- `test_end`
- `selected_factor`
- `selection_metric`
- `train_icir`
- `train_net_spread`
- `test_net_spread`
- `test_icir`
- `test_event_rate`
- `test_pass`

验收标准：

- 4 个 walk-forward 窗口应有 4 行 selected 结果。
- pass ratio 基于 selected 表计算，而不是 108 行候选全集。
- 报告中展示 selected pass ratio。

## 10. P1 修复：多重检验

涉及文件：

- `scripts/panic_walkforward_validate.py`

要求：

- 确保 `panic_multiple_testing_check.csv` 一定生成。
- permutation 应对每个候选使用其自身样本结构，不应只用一个 representative factor 的收益映射。
- 每次 permutation 在每个 `trade_date` 内打乱收益，计算 27 个候选的最大 net spread。
- 输出 permutation 分布摘要和 empirical p-value。

输出字段：

- `best_real_net_spread`
- `perm_max_mean`
- `perm_max_std`
- `perm_p95`
- `empirical_p_value`
- `n_candidates`
- `n_permutations`
- `random_seed`

验收标准：

- `panic_multiple_testing_check.csv` 存在且非空。
- `n_candidates=27`。
- `n_permutations >= 500`。
- 若 `empirical_p_value` 不显著，报告不得给出强 PASS。

## 11. P2 修复：测试补充

新增或扩展测试：

- `test_lag1_return_outlier_filter`
- `test_alignment_trade_day_gap`
- `test_formal_gate_uses_lag1_not_same_day`
- `test_cost_liquidity_output_non_empty`
- `test_regime_factor_and_source_fields`
- `test_walkforward_selected_one_factor_per_window`
- `test_multiple_testing_output_exists`
- `test_fast_check_does_not_overwrite_formal_summary`

验收标准：

- `python -m pytest tests/test_panic_reversal.py -q` 通过。
- 新增 diagnostics 测试通过。
- pandas warning 可暂不阻塞，但应记录。

## 12. 推荐执行顺序

1. 修复 `generate_exec_lag1_returns.py`，生成清洗后的 lag1 收益和 outlier 报告。
2. 修复 alignment audit 的 `calendar_gap_days` 和 `trade_day_gap`。
3. 修改 `evaluate_panic_reversal_diagnostics.py`，正式 gate 默认使用 lag1，禁止 fallback same-day。
4. 恢复成本/流动性诊断。
5. 修复 regime 字段。
6. 重跑正式 gate，确认 report 和 summary 更新时间正确。
7. 重写 walk-forward selected 输出。
8. 修复多重检验并确保文件落地。
9. 补测试。
10. 跑完整验收命令。

## 13. 最终验收命令

```powershell
python scripts/generate_exec_lag1_returns.py
python scripts/evaluate_panic_reversal_diagnostics.py
python scripts/panic_walkforward_validate.py
python -m pytest tests\test_panic_reversal.py -q
```

验收前必须检查：

```powershell
Get-ChildItem outputs\analysis\panic_reversal_gate
```

必需文件：

- `panic_lag1_returns.parquet`
- `panic_lag1_return_outliers.csv`
- `panic_lag1_return_quality_summary.csv`
- `panic_return_alignment_check.csv`
- `panic_variant_summary.csv`
- `panic_reversal_report.md`
- `panic_cost_liquidity.csv`
- `panic_redundancy_corr.csv`
- `panic_regime_diagnostic.csv`
- `panic_walkforward_candidates.csv`
- `panic_walkforward_selected.csv`
- `panic_multiple_testing_check.csv`

## 14. Go / No-Go 标准

满足以下全部条件才允许进入候选池：

- 正式 gate 使用 `execution_lag=1`。
- lag1 收益极端异常已过滤，正式收益范围通过质量检查。
- 20bps 成本后 net spread 在 holdout 或 selected walk-forward 下仍为正。
- selected walk-forward 至少 3/4 窗口通过，或达到预设 pass ratio。
- `panic_cost_liquidity.csv` 显示样本具备可交易性。
- 与现有 5 日反转因子的 event-only 冗余不过高。
- 多重检验 empirical p-value 支持非偶然发现。

若任一 P0/P1 项未完成：

- 不得将 panic reversal 标记为 PASS。
- 不得进入组合权重合成。
- 只能保留为研究观察因子或事件诊断工具。

# Shock Reversal 剩余验收闭环开发方案

生成日期：2026-06-12  
适用范围：`shock_reversal` 因子缓存生成、regime 接入预检、`E_shock_reversal` 冻结回测、最终验收报告  
当前结论：代码层 P0 修复已通过，但数据缓存与冻结回测产物仍缺失，整体仍为 No-Go。

## 1. 背景与当前状态

本方案承接 `docs/shock_reversal_acceptance_fix_plan.md` 的实现复核结果。最新审核确认：

1. `shock_reversal.cross_section` 专用配置路由已经修复。
2. `missing_method="drop"` 已真实生效，结构性 NaN 不再被横截面中位数补回。
3. 相关回归测试已通过，当前结果为 `79 passed`。
4. `abnormal_drop_reversal_5` 与 `abnormal_drop_reversal_5_cs` 的 parquet 缓存仍为空。
5. `outputs/validation/frozen_backtest/runs.csv` 中仍没有 `E_shock_reversal`。
6. 因缓存缺失，`configs/regime_shock_reversal.yaml` 当前会按预期硬失败，无法完成真实组合验证。

因此，后续开发重点不再是横截面代码修复，而是完成：

```text
生成 shock 因子缓存 -> 审计缓存覆盖 -> regime 预检通过 -> 跑 E_shock_reversal 冻结回测 -> 形成验收报告
```

## 2. 剩余问题清单

| ID | 优先级 | 问题 | 当前证据 | 阻塞影响 |
|---|---|---|---|---|
| P1-1 | P1 | `abnormal_drop_reversal_5` 缓存为空 | `rows=0, n_dates=0` | 无法生成或验证原始 shock 信号 |
| P1-2 | P1 | `abnormal_drop_reversal_5_cs` 缓存为空 | `rows=0, n_dates=0` | regime 无法加载 shock sleeve |
| P1-3 | P1 | `E_shock_reversal` 冻结回测产物缺失 | `runs.csv` 无对应记录，logs 无 `*E_shock*` | 无法证明边际贡献与成本后表现 |
| P1-4 | P1 | 缺少 shock 验收报告 | 无 `docs/shock_reversal_acceptance_report.md` | 无法完成 GO / NO-GO 决策 |
| P2-1 | P2 | 缺少缓存生成诊断落盘 | 无 `outputs/shock_reversal/` | 后续复核难以追溯 |

## 3. 已通过项确认

以下内容不需要重复返工，只需要在最终验收报告中引用：

| 检查项 | 当前结果 | 相关文件 |
|---|---|---|
| 专用配置路由 | 已支持 `section="shock_reversal"` | `factors/cross_section.py` |
| panel builder 路由 | shock 因子走 `self.shock_cs` | `factors/factor_panel.py` |
| 构建脚本路由 | `_cs_process` 使用专用 section | `scripts/build_shock_reversal_factor.py` |
| NaN 不回填 | 输入 10 个结构性 NaN，输出减少 10 行 | 本地探针 |
| 测试回归 | `79 passed` | `tests/test_shock_reversal.py` 等 |
| 缓存缺失硬失败 | regime 不再静默跳过 shock sleeve | `run_research.py` |

保留这些保护，不允许为了让回测跑通而降低缓存覆盖阈值或取消硬失败逻辑。

## 4. 阶段 A：运行前预检

### 4.1 目标

在生成缓存前确认代码和数据入口处于可执行状态，避免生成错误版本 `_cs` 缓存。

### 4.2 任务

| 任务 | 命令/文件 | 产物 |
|---|---|---|
| A-1 | 运行 shock 配置探针 | 控制台记录 `missing_method=drop` |
| A-2 | 运行 NaN 不回填探针 | 控制台记录输出行数减少 |
| A-3 | 运行相关测试 | `79 passed` 或更新后的全通过结果 |
| A-4 | 检查旧 shock 缓存目录 | 确认当前为空或准备重算 |

### 4.3 命令

```powershell
@'
from factors.cross_section import create_processor_from_config
p = create_processor_from_config("configs/factors_shock_reversal.yaml", section="shock_reversal")
print("missing_method=", p.missing_method)
print("neutralizers=", p.neutralizers)
'@ | python -
```

```powershell
python -m pytest -q tests/test_shock_reversal.py tests/test_regime_allocator.py tests/test_sleeve_performance_overlay.py tests/test_regime_config_validation.py tests/test_factor_alignment.py tests/test_regime_factor_universe.py tests/test_tradable_limit_rules.py
```

```powershell
Get-ChildItem data/parquet/factors -Directory |
  Where-Object { $_.Name -like "factor_name=abnormal_drop_reversal_5*" }
```

### 4.4 通过标准

```text
missing_method=drop
neutralizers=['log_market_cap']
测试全部通过
没有错误版本 shock 缓存需要保留
```

## 5. 阶段 B：生成 2017-2024 正式验证窗口因子缓存

### 5.1 目标

生成正式冻结验证所需的两个缓存：

```text
data/parquet/factors/factor_name=abnormal_drop_reversal_5/
data/parquet/factors/factor_name=abnormal_drop_reversal_5_cs/
```

### 5.2 任务

| 任务 | 文件/命令 | 说明 |
|---|---|---|
| B-1 | `scripts/build_shock_reversal_factor.py` | 使用 `--recompute` 重算 2017-2024 |
| B-2 | `abnormal_drop_reversal_5` | 生成原始因子缓存 |
| B-3 | `abnormal_drop_reversal_5_cs` | 使用 `missing_method=drop` 生成横截面缓存 |
| B-4 | 覆盖率检查 | 按 overall 与年度维度检查 rows、n_dates、平均股票数 |
| B-5 | 诊断落盘 | 生成覆盖率和过滤诊断文件 |

### 5.3 命令

```powershell
python scripts/build_shock_reversal_factor.py --start 20170101 --end 20241231 --recompute
```

覆盖率检查：

```powershell
@'
from data.panel_loader import get_loader
loader = get_loader()
for name in ["abnormal_drop_reversal_5", "abnormal_drop_reversal_5_cs"]:
    print(name, loader.factor_coverage(name, "20170101", "20241231"))
'@ | python -
```

目录检查：

```powershell
Get-ChildItem data/parquet/factors -Directory |
  Where-Object { $_.Name -like "factor_name=abnormal_drop_reversal_5*" } |
  Select-Object FullName, LastWriteTime
```

### 5.4 建议补充产物

如果当前脚本只写日志，不写 CSV，建议补一个轻量报告输出到：

```text
outputs/shock_reversal/coverage_2017_2024.csv
outputs/shock_reversal/filter_diagnostics_2017_2024.csv
outputs/shock_reversal/cs_processing_diagnostics_2017_2024.csv
```

覆盖率报告至少包含：

| 字段 | 含义 |
|---|---|
| `factor_name` | 因子名 |
| `year` | 年份，另设 `ALL` 汇总行 |
| `rows` | 总行数 |
| `n_dates` | 信号日期数 |
| `min_date` | 最早日期 |
| `max_date` | 最晚日期 |
| `avg_stocks_per_date` | 平均每期股票数 |
| `duplicates` | 重复键数量 |
| `status` | `OK` / `LOW_COVERAGE` / `FAIL` |

### 5.5 通过标准

1. 两个缓存目录真实存在。
2. 两个因子的 `rows > 0`，`n_dates > 0`。
3. `abnormal_drop_reversal_5_cs` 覆盖率满足 `run_research.py` 中 shock 硬失败阈值。
4. 平均每个信号日至少 30 只股票。
5. 无 `(ts_code, trade_date)` 重复。
6. 2017-2024 每年覆盖状态为 `OK`，若某年 `LOW` 必须解释原因。

## 6. 阶段 C：regime 接入预检

### 6.1 目标

确认缓存生成后，`configs/regime_shock_reversal.yaml` 能真实加载 `abnormal_drop_reversal_5_cs`，而不是静默跳过或继续硬失败。

### 6.2 命令

```powershell
@'
from data.panel_loader import get_loader
from run_research import _load_regime_config_safe, _select_regime_candidate_factors

loader = get_loader()
cfg = _load_regime_config_safe("configs/regime_shock_reversal.yaml")
factors = _select_regime_candidate_factors(loader, cfg, "20240101", "20241231")

print("n_factors=", len(factors))
print("has_shock=", "abnormal_drop_reversal_5_cs" in factors)
print([f for f in factors if f.startswith("abnormal_drop_reversal")])
'@ | python -
```

### 6.3 通过标准

```text
has_shock=True
abnormal_drop_reversal_5_cs 出现在候选因子列表中
无 RuntimeError
无 "will be skipped" 的 shock 因子警告
```

如果仍然失败，不允许绕过硬失败逻辑。必须回到阶段 B 修复缓存覆盖。

## 7. 阶段 D：运行 E_shock_reversal 冻结回测

### 7.1 目标

让 `E_shock_reversal` 在冻结验证矩阵中真实产生运行记录、日志和指标，而不是只在脚本中定义。

### 7.2 推荐命令

推荐直接更新默认冻结验证目录，并显式指定 A-E 策略，保留基线对照：

```powershell
python scripts/frozen_backtest_validation.py `
  --years 2017 2018 2019 2020 2021 2022 2023 2024 2026 `
  --strategies A_5reversal B_dynamic C_regime_baseline D_regime_overlay E_shock_reversal `
  --top-n 50 `
  --out-dir outputs/validation/frozen_backtest `
  --out-doc docs/frozen_backtest_validation.md
```

如只想先做 smoke 验证，可使用独立目录，避免覆盖默认 `runs.csv`：

```powershell
python scripts/frozen_backtest_validation.py `
  --years 2024 2026 `
  --strategies E_shock_reversal `
  --top-n 50 `
  --out-dir outputs/validation/frozen_backtest_shock_reversal_smoke `
  --out-doc docs/shock_reversal_smoke_validation.md
```

正式验收必须跑完整 2017-2024 与 2026 YTD 窗口。

### 7.3 运行后检查

```powershell
Select-String -Path outputs/validation/frozen_backtest/runs.csv -Pattern "E_shock_reversal"
```

```powershell
Get-ChildItem outputs/validation/frozen_backtest/logs -Filter "*E_shock*"
```

```powershell
Import-Csv outputs/validation/frozen_backtest/runs.csv |
  Where-Object { $_.strategy -eq "E_shock_reversal" } |
  Select-Object year, return_code, annualized_return, information_ratio, sharpe_ratio, max_drawdown, avg_turnover, go_nogo_overall
```

### 7.4 通过标准

1. `runs.csv` 中每个正式年份都有 `E_shock_reversal` 记录。
2. `return_code=0`。
3. logs 下存在对应 `E_shock_reversal` 日志。
4. 日志中没有 shock 缓存缺失、覆盖不足、因子跳过等错误。
5. 每年指标包含收益、回撤、IR、Sharpe、换手、成本字段。
6. 与 `C_regime_baseline`、`D_regime_overlay` 的对比可计算。

## 8. 阶段 E：提取 shock sleeve 行为诊断

### 8.1 目标

不仅证明回测跑通，还要证明 shock sleeve 在组合里真实活跃，并且不是权重一直为 0。

### 8.2 任务

| 任务 | 说明 |
|---|---|
| E-1 | 找到每个 `E_shock_reversal` run_dir |
| E-2 | 汇总 diagnostics 中的 `shock_reversal_weight` |
| E-3 | 统计 active dates、平均权重、最大权重、权重为 0 的日期占比 |
| E-4 | 检查 shock sleeve 对 period return 的边际贡献 |
| E-5 | 输出 `outputs/shock_reversal/sleeve_activity_2017_2026.csv` |

### 8.3 通过标准

1. `shock_reversal_weight` 平均值大于 0。
2. active dates 大于 0。
3. 权重行为与 `configs/regime_shock_reversal.yaml` 的 regime 权重设定一致。
4. 若权重长期为 0，必须解释是 allocator 约束、因子全空、还是 sleeve 配置未生效。

## 9. 阶段 F：生成最终验收报告

### 9.1 目标

新增最终报告：

```text
docs/shock_reversal_acceptance_report.md
```

### 9.2 报告结构

建议包含以下章节：

1. 结论摘要：GO / NO-GO。
2. 修复范围：配置路由、NaN 不回填、缓存生成、冻结回测。
3. 测试结果：命令、通过数量、失败数量。
4. 因子缓存覆盖率：raw 与 `_cs` 的年度表。
5. regime 预检结果：`abnormal_drop_reversal_5_cs` 是否进入候选因子池。
6. 冻结回测结果：`E_shock_reversal` 年度指标表。
7. 相对基线对比：相对 `C_regime_baseline` 与 `D_regime_overlay`。
8. shock sleeve 活跃度：平均权重、active dates、贡献。
9. 风险说明：流动性、停牌/ST/IPO过滤、成本、回撤年份。
10. 最终决策：保留、降权、继续观察或移除。

### 9.3 GO / NO-GO 建议标准

满足以下条件才允许 GO：

1. 2017-2024 缓存覆盖通过。
2. `E_shock_reversal` 所有正式年份 `return_code=0`。
3. shock sleeve 有真实 active dates，平均权重大于 0。
4. 成本后表现不显著劣于基线。
5. 最大回撤、换手、极端单期收益没有引入不可接受风险。
6. 所有结论可由 `outputs` 产物复现。

任一条件不满足，应保持 No-Go，并在报告中说明下一步是修数据、调配置还是放弃该 sleeve。

## 10. 最终验收清单

| 检查项 | 命令/文件 | 通过标准 |
|---|---|---|
| P0 保护未回归 | shock 配置探针 | `missing_method=drop` |
| 测试回归 | `python -m pytest -q ...` | 全部通过 |
| raw 缓存 | `loader.factor_coverage("abnormal_drop_reversal_5", ...)` | `rows>0`，`n_dates>0` |
| cs 缓存 | `loader.factor_coverage("abnormal_drop_reversal_5_cs", ...)` | 满足硬失败阈值 |
| regime 预检 | `_select_regime_candidate_factors` | `has_shock=True` |
| 冻结回测 | `outputs/validation/frozen_backtest/runs.csv` | 包含 `E_shock_reversal` |
| 回测日志 | `outputs/validation/frozen_backtest/logs` | 存在 `*E_shock*`，无错误 |
| sleeve 活跃度 | `outputs/shock_reversal/sleeve_activity_2017_2026.csv` | active dates > 0 |
| 验收报告 | `docs/shock_reversal_acceptance_report.md` | 有明确 GO / NO-GO |

## 11. 风险与注意事项

1. 不要在缓存为空时运行正式 `E_shock_reversal` 并将失败结果当作验收结果。
2. 不要为了通过回测而关闭 `run_research.py` 中的 shock 缓存硬失败。
3. 不要用 `outputs/runs/*/diagnostics` 中 `shock_reversal_weight=0.0` 的普通运行替代冻结回测验收。
4. 不要在看到冻结回测结果后反向修改 shock 因子参数；如需调参，应重新定义 discovery / validation / OOS 边界。
5. 若 `scripts/build_shock_reversal_factor.py` 失败，应先排查 universe、raw price、limit、suspend、namechange、amount 等上游数据，不要直接放宽过滤条件。

## 12. 建议执行顺序

```text
1. 阶段 A：预检 P0 保护与测试
2. 阶段 B：生成 2017-2024 raw 与 cs 缓存
3. 阶段 C：regime 预检，确认 shock 因子进入候选池
4. 阶段 D：运行完整冻结回测，产出 E_shock_reversal
5. 阶段 E：提取 shock sleeve 活跃度与贡献诊断
6. 阶段 F：写入 docs/shock_reversal_acceptance_report.md
7. 最终复核：根据报告给 GO / NO-GO
```

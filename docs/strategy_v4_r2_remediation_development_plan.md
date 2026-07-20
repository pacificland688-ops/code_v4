# Strategy V4-r2 返工修复开发方案

生成日期：2026-06-15  
来源报告：`docs/strategy_v4_r2_completion_review.md`  
适用范围：V4-r2 数据质量、factor gate、候选池、冻结验证、GO/NO-GO 全链路返工  
目标候选名：`G_candidate_v4_r2`

## 1. 背景与结论

V4-r2 当前未通过完成审核。现状不是“策略已可验收”，而是“配置草案与部分注册存在，但核心数据修复和验证链路未完成”。

审核发现的硬失败：

1. `audit_cache` 在 `2017-2024` 和 `2026 YTD` 两个窗口均为 `FAIL=5`。
2. 四个 growth 因子仍存在大量 `(ts_code, trade_date)` 重复键：
   - `revenue_growth_ttm_cs`
   - `profit_growth_ttm_cs`
   - `growth_stability_8q_cs`
   - `earnings_acceleration_cs`
3. V4 输入审计仍为 `PASS=8 / FAIL=23 / BLOCKED=23`。
4. factor gate 当前为 `PASS=0 / WATCH_NEUTRAL_ONLY=1 / FAIL=20 / DATA_MISSING=28`。
5. `configs/factors_candidate_v4_r2.yaml` 只启用 `volatility_60_cs`，且它是 `WATCH_NEUTRAL_ONLY`，不是正式 alpha PASS。
6. `configs/regime_candidate_v4_r2.yaml` 多个 alpha sleeve 为空，但 allocator 仍给空 sleeve 分配权重。
7. `outputs/validation/candidate_v4_r2/runs.csv` 和 `outputs/validation/candidate_v4_r2_smoke/runs.csv` 均缺失。
8. `docs/go_nogo_decision.md` 未覆盖 `G_candidate_v4_r2`。
9. `scripts/generate_go_nogo_decision.py` 顶部常量包含 r2，但 `main()` 的候选列表未纳入 r2。

本方案目标是把 V4-r2 从当前失败状态修复到可正式验收状态。修复完成前，禁止进入实盘或小资金试运行。

## 2. 总体目标

### 2.1 工程目标

1. 修复四个 growth 因子的重复键，使最终缓存按 `(ts_code, trade_date)` 唯一。
2. 让 `audit_cache.py` 在 `2017-2024` 和 `2026 YTD` 两个窗口均达到 `FAIL=0`。
3. 让拟进入候选池的因子在 `audit_alpha_inputs_v4.py` 中全部通过输入审计。
4. 重新运行 `factor_quality_rebuild.py`，生成真实、可复现的 gate 结果。
5. 只允许 input audit PASS 且 gate PASS 的 alpha 因子进入正式 `enabled_factors`。
6. 修复 r2 候选池、sleeve 和 allocator，使空 sleeve 不再被分配有效权重。
7. 修复 GO/NO-GO 脚本，使 `G_candidate_v4_r2` 成为正式必检候选。
8. 重新运行 r2 smoke 和完整冻结验证，生成完整 runs、报告、manifest。
9. 生成覆盖 r2 的正式 GO/NO-GO 文档和对比报告。

### 2.2 策略目标

V4-r2 修复后仍沿用原正式门槛，不降低标准：

| 指标 | GO 门槛 |
|---|---:|
| 2017-2024 平均年化超额 | > 2.0% |
| 2017-2024 中位数年化超额 | > 0.0% |
| 正超额年份 | >= 5/8 |
| 平均 IR | > 0.30 |
| 最大单年超额亏损 | > -10.0% |

补充要求：

| 项目 | 要求 |
|---|---|
| 相对 V3 胜出年份 | 建议 >= 5/8 |
| 相对 V3 平均年度超额差异 | > 0 |
| 2018、2019 | 不得无解释地大幅恶化 |
| 2026 YTD | 只作前瞻观察，不参与调参 |

## 3. 非目标

本轮不做：

1. 不进入实盘。
2. 不进入小资金试运行。
3. 不复用 `G_candidate_v4_r1` 作为新结果名。
4. 不覆盖 `outputs/validation/candidate_v4_r1/` 历史结果。
5. 不在 `audit_cache FAIL > 0` 时运行正式冻结验证。
6. 不在 `factor_quality_gate PASS=0` 时包装正式候选策略。
7. 不把 `WATCH_NEUTRAL_ONLY` 因子当成 alpha 通过证据。
8. 不把 input audit FAIL 或 gate FAIL/DATA_MISSING 的因子放进正式 enabled。

## 4. 当前失败状态基线

### 4.1 cache audit 基线

2017-2024：

```text
Total: 38 checks | PASS=32 | WARN=1 | FAIL=5
factor_cs_quality: FAIL, 26 factors checked; 4 with duplicates
```

| 因子 | rows | dates | dup | range |
|---|---:|---:|---:|---|
| `earnings_acceleration_cs` | 6385 | 468 | 3705 | 20180830-20241031 |
| `growth_stability_8q_cs` | 6385 | 468 | 3705 | 20180830-20241031 |
| `profit_growth_ttm_cs` | 6935 | 513 | 4355 | 20180316-20241031 |
| `revenue_growth_ttm_cs` | 6935 | 513 | 4355 | 20180316-20241031 |

2026 YTD：

```text
Total: 38 checks | PASS=33 | WARN=0 | FAIL=5
factor_cs_quality: FAIL, 26 factors checked; 4 with duplicates; 12 with <12 dates
```

| 因子 | rows | dates | dup | range |
|---|---:|---:|---:|---|
| `earnings_acceleration_cs` | 488 | 41 | 239 | 20260210-20260430 |
| `growth_stability_8q_cs` | 488 | 41 | 239 | 20260210-20260430 |
| `profit_growth_ttm_cs` | 488 | 41 | 239 | 20260210-20260430 |
| `revenue_growth_ttm_cs` | 488 | 41 | 239 | 20260210-20260430 |

### 4.2 alpha input audit 基线

```text
PASS: 8
WARN: 0
FAIL: 23
BLOCKED: 23
```

growth 失败原因：

| 因子 | 状态 | 失败原因 | total_rows | duplicate_count |
|---|---|---|---:|---:|
| `revenue_growth_ttm_cs` | FAIL | `HIGH_DUPLICATE_RATE:4355/11290` | 11290 | 4355 |
| `profit_growth_ttm_cs` | FAIL | `HIGH_DUPLICATE_RATE:4355/11290` | 11290 | 4355 |
| `growth_stability_8q_cs` | FAIL | `HIGH_DUPLICATE_RATE:3705/10090` | 10090 | 3705 |
| `earnings_acceleration_cs` | FAIL | `HIGH_DUPLICATE_RATE:3705/10090` | 10090 | 3705 |

### 4.3 factor gate 基线

```text
DATA_MISSING: 28
FAIL: 20
WATCH_NEUTRAL_ONLY: 1
PASS: 0
```

重点因子：

| 因子 | gate 状态 | 原因 |
|---|---|---|
| `revenue_growth_ttm_cs` | DATA_MISSING | factor cache empty |
| `profit_growth_ttm_cs` | DATA_MISSING | factor cache empty |
| `growth_stability_8q_cs` | DATA_MISSING | factor cache empty |
| `earnings_acceleration_cs` | DATA_MISSING | factor cache empty |
| `volatility_60_cs` | WATCH_NEUTRAL_ONLY | raw 下正超额年份不足 |

## 5. 总体里程碑

```text
R0 冻结失败基线
  -> R1 定位 growth 重复键来源
  -> R2 修复 growth PIT 展开与写入去重
  -> R3 重建 growth 因子缓存
  -> R4 通过 cache audit 与 alpha input audit
  -> R5 重新运行 factor quality gate
  -> R6 重建 r2 候选池与 sleeve/allocator
  -> R7 修复 GO/NO-GO r2 纳入逻辑
  -> R8 运行 r2 smoke 验证
  -> R9 运行 r2 完整冻结验证
  -> R10 生成 r2 对比报告与正式 GO/NO-GO
  -> R11 完成最终验收报告
```

硬性阻断：

```text
R4 未通过，不进入 R5。
R5 PASS alpha 因子不足，不进入 R6。
R6 候选池不合规，不进入 R8。
R8 smoke 不通过，不进入 R9。
R9 runs 不完整，不进入 R10。
R10 NO-GO，不进入实盘。
```

## 6. R0：冻结失败基线

目标：保留当前失败证据，避免修复过程中丢失对照。

任务：

| ID | 任务 | 产物 | 验收 |
|---|---|---|---|
| R0.1 | 保留当前审核报告 | `docs/strategy_v4_r2_completion_review.md` | 报告存在 |
| R0.2 | 保留当前输入审计输出 | `outputs/analysis/v4_alpha_inputs_review/` | 包含 `audit_summary.csv` |
| R0.3 | 记录当前 gate 状态 | `outputs/analysis/factor_quality_rebuild_v4/factor_quality_gate.csv` | 可复现 status counts |
| R0.4 | 确认不覆盖 r1 | `outputs/validation/candidate_v4_r1/` | 历史 runs 保留 |

## 7. R1：定位 growth 重复键来源

目标：确认重复键来自 PIT 展开、报告期选择、forward-fill、分区 append，还是多处叠加。

涉及文件：

```text
scripts/build_alpha_factors_v4.py
scripts/audit_alpha_inputs_v4.py
scripts/audit_cache.py
configs/factor_build_v4.yaml
```

建议新增诊断脚本：

```text
scripts/diagnose_growth_factor_duplicates.py
```

诊断输出：

```text
outputs/analysis/v4_r2_growth_duplicate_diagnosis/duplicate_summary.csv
outputs/analysis/v4_r2_growth_duplicate_diagnosis/duplicate_samples.csv
outputs/analysis/v4_r2_growth_duplicate_diagnosis/source_period_conflicts.csv
outputs/analysis/v4_r2_growth_duplicate_diagnosis/partition_overlap.csv
docs/v4_r2_growth_duplicate_root_cause.md
```

诊断要求：

1. 按 factor 输出重复键数量、重复行数量、重复率。
2. 对每个重复键展示 `ts_code`、`trade_date`、`available_date`、`source_period`、`ann_date`、`report_type`、`value`。
3. 判断同一 `(ts_code, trade_date)` 是否对应多个报告期。
4. 判断同一报告期是否有多个公告或修订记录。
5. 判断 parquet 分区是否存在 append 旧数据导致的跨文件重复。
6. 判断重复是否在 forward-fill 前已经存在，还是展开后才出现。

建议命令：

```powershell
python -X utf8 scripts\diagnose_growth_factor_duplicates.py `
  --factors revenue_growth_ttm_cs profit_growth_ttm_cs growth_stability_8q_cs earnings_acceleration_cs `
  --start 20170101 `
  --end 20241231 `
  --out outputs\analysis\v4_r2_growth_duplicate_diagnosis
```

验收标准：

```text
每个失败因子都有重复数量、样本和根因分类
明确最终去重规则
明确需要清理的目标缓存分区
```

## 8. R2：修复 growth PIT 展开与写入去重

目标：从构建逻辑上消除重复键，而不是在审计中忽略重复。

### 8.1 统一去重原则

最终输出必须满足：

```python
assert not df.duplicated(["ts_code", "trade_date"]).any()
```

推荐规则：

| 场景 | 处理规则 |
|---|---|
| 同一股票同一交易日多个报告期 | 只保留 `available_date <= trade_date` 且最新可用的 `source_period` |
| 同一报告期多个公告或修订 | 保留不晚于 `trade_date` 的最新 `available_date` |
| forward-fill 后重复 | 按 `(ts_code, trade_date)` 排序后保留最后一条有效记录 |
| 分区 append 旧数据 | 写入目标分区前清理对应 factor/date 分区，或使用 overwrite |
| 值完全相同的重复 | 仍必须去重，不允许多行保留 |

### 8.2 必改代码点

优先检查并修改：

```text
scripts/build_alpha_factors_v4.py
```

需要加入的能力：

1. growth 原始财报数据加载后，按 PIT 规则选择唯一可用记录。
2. TTM/8Q/acceleration 计算后，保留可追溯字段用于诊断。
3. trade_date 展开前检查源记录唯一性。
4. trade_date 展开后检查 `(ts_code, trade_date)` 唯一性。
5. 写 parquet 前执行唯一键断言。
6. 写入时采用覆盖目标分区，禁止 append 旧分区造成重复。

### 8.3 单测要求

新增或补强：

```text
tests/test_alpha_factors_v4.py
tests/test_growth_factor_pit_dedup_v4_r2.py
tests/test_audit_cache_factor_duplicates.py
```

测试场景：

1. 同一股票同一交易日有多个报告期，只保留最新可用报告期。
2. 同一报告期多次修订，只保留不晚于交易日的最新公告。
3. `available_date > trade_date` 的记录不得被使用。
4. forward-fill 后不能产生重复键。
5. 重新写入相同窗口不会 append 出重复分区。
6. 四个 growth 因子的输出均通过唯一键检查。

验收命令：

```powershell
python -X utf8 -m pytest tests\test_alpha_factors_v4.py tests\test_growth_factor_pit_dedup_v4_r2.py tests\test_audit_cache_factor_duplicates.py -q
```

验收标准：

```text
pytest 通过
所有构造样本无 future leakage
所有构造样本无重复键
```

## 9. R3：重建 growth 因子缓存

目标：清理旧重复缓存，重新生成 2017-2024 与 2026 YTD 的 growth 因子。

### 9.1 清理要求

清理范围只允许覆盖四个 growth 因子相关缓存分区：

```text
revenue_growth_ttm_cs
profit_growth_ttm_cs
growth_stability_8q_cs
earnings_acceleration_cs
```

禁止清理：

```text
outputs/validation/candidate_v4_r1/
outputs/validation/candidate_v4_r1_smoke/
outputs/validation/candidate_v2/
outputs/validation/candidate_v3/
```

### 9.2 重建命令

按项目脚本实际参数执行。若 `build_alpha_factors_v4.py` 支持 `--force`，推荐：

```powershell
python -X utf8 scripts\build_alpha_factors_v4.py --config configs\factor_build_v4.yaml --start 20170101 --end 20241231 --force
python -X utf8 scripts\build_alpha_factors_v4.py --config configs\factor_build_v4.yaml --start 20260101 --end 20260605 --force
```

如果脚本暂不支持按因子重建，应先补充参数：

```text
--factors revenue_growth_ttm_cs profit_growth_ttm_cs growth_stability_8q_cs earnings_acceleration_cs
--overwrite
```

验收标准：

```text
四个 growth 因子缓存存在
对应窗口内 dup=0
缓存覆盖年份与交易日范围符合预期
```

## 10. R4：通过 cache audit 与 alpha input audit

目标：数据质量达到冻结验证前置条件。

执行命令：

```powershell
python -X utf8 scripts\audit_cache.py --start 20170101 --end 20241231 --verbose
python -X utf8 scripts\audit_cache.py --start 20260101 --end 20260605 --verbose
python -X utf8 scripts\audit_alpha_inputs_v4.py --start 20170101 --end 20241231 --out outputs\analysis\v4_alpha_inputs
```

验收标准：

```text
2017-2024 audit_cache: FAIL=0
2026 YTD audit_cache: FAIL=0
revenue_growth_ttm_cs dup=0
profit_growth_ttm_cs dup=0
growth_stability_8q_cs dup=0
earnings_acceleration_cs dup=0
进入候选池的因子在 audit_alpha_inputs_v4 中必须 PASS
future_leakage_count=0
```

阻断规则：

```text
任一 audit_cache FAIL > 0，停止。
任一候选因子 input audit FAIL，停止。
```

## 11. R5：重新运行 factor quality gate

目标：基于修复后的真实缓存，重新评估所有候选因子质量。

执行命令：

```powershell
python -X utf8 scripts\factor_quality_rebuild.py `
  --config configs\factor_quality_rebuild_v4.yaml `
  --out-dir outputs\analysis\factor_quality_rebuild_v4 `
  --out-doc docs\factor_quality_rebuild_v4_report.md
```

必须输出：

```text
outputs/analysis/factor_quality_rebuild_v4/factor_quality_gate.csv
outputs/analysis/factor_quality_rebuild_v4/factor_candidate_pool.yaml
docs/factor_quality_rebuild_v4_report.md
docs/factor_rejection_log_v4.md
docs/factor_quality_manual_review_v4.md
```

候选准入规则：

| Gate 状态 | 是否可进入正式 alpha enabled | 说明 |
|---|---|---|
| PASS | 可以 | 需保留指标证据 |
| WATCH_NEUTRAL_ONLY | 不可作为 alpha；可作为 defensive/risk | 必须人工说明 |
| FAIL | 不可以 | 进入 rejection log |
| DATA_MISSING | 不可以 | 先修数据 |
| input audit FAIL | 不可以 | 优先级高于 gate |

验收标准：

```text
factor_quality_gate.csv 不再把已修复 growth 因子标为 DATA_MISSING
正式 alpha enabled 只能来自 PASS
若 PASS alpha 因子数量不足，停止策略组装
```

建议最低标准：

```text
PASS alpha factors >= 3 才允许进入候选池重建
PASS alpha factors >= 5 才建议进入正式冻结验证
```

如实际 PASS 因子不足，应输出 NO-GO 原因，不应强行包装 r2。

## 12. R6：重建 r2 候选池与 sleeve/allocator

目标：消除当前“只有 WATCH 因子、alpha sleeve 为空、allocator 仍分配空 sleeve”的问题。

### 12.1 候选池文件

目标文件：

```text
configs/factors_candidate_v4_r2.yaml
docs/factors_candidate_v4_r2_selection.md
```

生成规则：

1. 读取 `outputs/analysis/factor_quality_rebuild_v4/factor_quality_gate.csv`。
2. 读取 `outputs/analysis/v4_alpha_inputs/audit_summary.csv`。
3. 只选择 input audit PASS 且 gate PASS 的 alpha 因子进入 `enabled_factors`。
4. `WATCH_NEUTRAL_ONLY` 因子只进入 defensive/risk 说明，不进入 alpha enabled。
5. `FAIL`、`DATA_MISSING`、input audit FAIL 因子进入 `disabled_factors` 并记录原因。
6. 若 `enabled_factors` 为空，则不生成正式 r2 候选策略，直接输出阻断报告。

验收标准：

```text
enabled_factors 中无 FAIL
enabled_factors 中无 DATA_MISSING
enabled_factors 中无 input audit FAIL
enabled_factors 中至少包含一个正式 PASS alpha 因子
```

### 12.2 sleeve 与 allocator 文件

目标文件：

```text
configs/regime_candidate_v4_r2.yaml
docs/sleeve_design_v4_r2.md
```

要求：

1. 每个非空 sleeve 的因子必须存在于 `enabled_factors` 或明确标记为 neutralizer/risk。
2. 空 sleeve 的 allocator 权重必须为 0。
3. allocator 权重必须重新归一化到非空 sleeve。
4. `min_sleeves` 必须与实际非空 sleeve 数量一致。
5. defensive sleeve 可包含 `WATCH_NEUTRAL_ONLY`，但不得作为 alpha 通过证据。
6. 若只有 defensive sleeve 非空，不允许进入正式 alpha 冻结验证。

验收标准：

```text
所有 regime 下 sleeve 权重合计约等于 1.0
无空 sleeve 获得非零权重
无 FAIL/DATA_MISSING 因子出现在 sleeve
```

专项测试：

```powershell
python -X utf8 -m pytest tests\test_factor_candidate_v4_r2.py tests\test_regime_candidate_v4_r2_config.py -q
```

必要时新增测试：

```text
tests/test_candidate_v4_r2_gate_enforcement.py
tests/test_regime_candidate_v4_r2_allocator_non_empty.py
```

新增断言：

```text
enabled_factors 必须至少有一个 gate PASS alpha
空 sleeve 权重必须为 0
只有 WATCH/defensive 时不得标记为 formal candidate
```

## 13. R7：修复 GO/NO-GO r2 纳入逻辑

目标：确保正式 GO/NO-GO 必须覆盖 `G_candidate_v4_r2`，缺失 r2 runs 时拒绝生成。

涉及文件：

```text
scripts/generate_go_nogo_decision.py
tests/test_go_nogo_decision.py
tests/test_go_nogo_data_gate.py
```

当前问题：

```text
REQUIRED_CANDIDATE_STRATEGIES 包含 G_candidate_v4_r2
main() 的 candidate_strategies 仍只有 E_candidate_v2、F_candidate_v3、G_candidate_v4_r1
```

修复要求：

1. `main()` 的 `candidate_strategies` 必须包含 `G_candidate_v4_r2`。
2. 默认 `--runs` 应包含 r1 与 r2 的正式 runs 路径，或从 `REQUIRED_CANDIDATE_STRATEGIES` 自动推导。
3. 缺失 `G_candidate_v4_r2` validation 2017-2024 或 ytd 2026 时，正式模式必须失败。
4. `--allow-incomplete` 只能用于诊断，生成文档必须带 INCOMPLETE 标记。
5. `docs/go_nogo_decision.md` 必须包含 r2 年度对比、汇总、门槛检查、2026 YTD。

建议测试：

```powershell
python -X utf8 -m pytest tests\test_go_nogo_decision.py tests\test_go_nogo_data_gate.py -q
```

新增测试场景：

1. 缺少 `G_candidate_v4_r2` runs 时，正式生成失败。
2. r2 缺少年份时，正式生成失败。
3. 使用 `--allow-incomplete` 时文档标题或正文必须包含 `INCOMPLETE`。
4. 完整 r2 runs 存在时，文档必须出现 `G_candidate_v4_r2`。

## 14. R8：r2 smoke 验证

目标：在全量冻结验证前，用短窗口验证配置、manifest、运行链路和指标输出。

前置条件：

```text
R4 通过
R5 通过
R6 通过
R7 通过
```

执行命令：

```powershell
python -X utf8 scripts\frozen_backtest_validation.py `
  --strategies G_candidate_v4_r2 `
  --years 2024 2026 `
  --out-dir outputs\validation\candidate_v4_r2_smoke `
  --out-doc docs\_v4_r2_smoke.md `
  --force
```

验收标准：

```text
outputs/validation/candidate_v4_r2_smoke/runs.csv exists
runs.csv 包含 2024 validation 与 2026 ytd
return_code=0
data_quality_status 无硬失败
manifest 中 factors_config_sha256 与 regime_config_sha256 存在且匹配当前配置
docs/_v4_r2_smoke.md 存在
```

阻断规则：

```text
smoke 失败，不进入完整冻结验证。
```

## 15. R9：r2 完整冻结验证

目标：生成正式 out-of-sample 验收数据。

执行命令：

```powershell
python -X utf8 scripts\frozen_backtest_validation.py `
  --strategies G_candidate_v4_r2 `
  --years 2017 2018 2019 2020 2021 2022 2023 2024 2026 `
  --out-dir outputs\validation\candidate_v4_r2 `
  --out-doc docs\candidate_v4_r2_validation.md `
  --force
```

验收标准：

```text
outputs/validation/candidate_v4_r2/runs.csv exists
runs.csv 覆盖 validation: 2017-2024
runs.csv 覆盖 ytd: 2026
strategy 唯一值为 G_candidate_v4_r2
所有正式年份 return_code=0
manifest config hash 与当前 configs/factors_candidate_v4_r2.yaml、configs/regime_candidate_v4_r2.yaml 一致
```

禁止事项：

```text
不得使用 --reuse-existing 复用旧 manifest 不完整的 run 作为正式验收
不得使用 --allow-legacy-manifest 作为正式验收证据
不得覆盖 r1 输出目录
```

## 16. R10：正式对比报告与 GO/NO-GO

目标：生成覆盖 r2 的正式决策文档。

### 16.1 生成 GO/NO-GO

执行命令：

```powershell
python -X utf8 scripts\generate_go_nogo_decision.py `
  --runs `
    outputs\validation\frozen_backtest\runs.csv `
    outputs\validation\candidate_v2\runs.csv `
    outputs\validation\candidate_v3\runs.csv `
    outputs\validation\candidate_v4_r1\runs.csv `
    outputs\validation\candidate_v4_r2\runs.csv `
  --out docs\go_nogo_decision.md
```

验收标准：

```text
docs/go_nogo_decision.md 不含 INCOMPLETE
docs/go_nogo_decision.md 包含 G_candidate_v4_r2
G_candidate_v4_r2 覆盖 2017-2024 validation 与 2026 ytd
门槛检查全部从 runs.csv 生成
```

### 16.2 生成对比报告

目标文件：

```text
docs/candidate_v4_r2_vs_v3_comparison.md
docs/candidate_v4_r2_vs_v4_r1_comparison.md
docs/candidate_v4_r2_validation_summary.md
```

报告内容：

1. 年度超额对比。
2. 平均超额、中位数超额、正超额年份、IR、最大单年亏损。
3. 2018、2019 专项解释。
4. 2026 YTD 观察说明。
5. turnover、成本、最大回撤对比。
6. 相对 V3 与 r1 的改进或恶化归因。

## 17. R11：最终验收报告

目标：形成新的完成审核报告，替换当前失败结论。

目标文件：

```text
docs/strategy_v4_r2_completion_review.md
```

内容必须包括：

1. 数据审计命令与结果。
2. factor gate 状态汇总。
3. 候选池 enabled 因子与 gate/input audit 对照。
4. sleeve 与 allocator 合规性。
5. smoke 验证结果。
6. 完整冻结验证结果。
7. GO/NO-GO 结论。
8. 是否允许进入下一阶段。

正式通过标准：

```text
audit_cache FAIL=0
候选因子 input audit PASS
factor gate 至少存在正式 PASS alpha
候选池无 FAIL/DATA_MISSING/input FAIL
smoke runs 完整
full runs 完整
GO/NO-GO 覆盖 r2 且不含 INCOMPLETE
若策略指标未过门槛，结论仍为 NO-GO
```

## 18. 推荐执行顺序

### 第一阶段：数据修复

```powershell
python -X utf8 scripts\diagnose_growth_factor_duplicates.py --factors revenue_growth_ttm_cs profit_growth_ttm_cs growth_stability_8q_cs earnings_acceleration_cs --start 20170101 --end 20241231 --out outputs\analysis\v4_r2_growth_duplicate_diagnosis
python -X utf8 -m pytest tests\test_alpha_factors_v4.py tests\test_growth_factor_pit_dedup_v4_r2.py tests\test_audit_cache_factor_duplicates.py -q
python -X utf8 scripts\build_alpha_factors_v4.py --config configs\factor_build_v4.yaml --start 20170101 --end 20241231 --force
python -X utf8 scripts\build_alpha_factors_v4.py --config configs\factor_build_v4.yaml --start 20260101 --end 20260605 --force
```

### 第二阶段：审计与 gate

```powershell
python -X utf8 scripts\audit_cache.py --start 20170101 --end 20241231 --verbose
python -X utf8 scripts\audit_cache.py --start 20260101 --end 20260605 --verbose
python -X utf8 scripts\audit_alpha_inputs_v4.py --start 20170101 --end 20241231 --out outputs\analysis\v4_alpha_inputs
python -X utf8 scripts\factor_quality_rebuild.py --config configs\factor_quality_rebuild_v4.yaml --out-dir outputs\analysis\factor_quality_rebuild_v4 --out-doc docs\factor_quality_rebuild_v4_report.md
```

### 第三阶段：候选池与 GO/NO-GO 代码修复

```powershell
python -X utf8 -m pytest tests\test_factor_candidate_v4_r2.py tests\test_regime_candidate_v4_r2_config.py tests\test_go_nogo_decision.py tests\test_go_nogo_data_gate.py -q
```

### 第四阶段：冻结验证

```powershell
python -X utf8 scripts\frozen_backtest_validation.py --strategies G_candidate_v4_r2 --years 2024 2026 --out-dir outputs\validation\candidate_v4_r2_smoke --out-doc docs\_v4_r2_smoke.md --force
python -X utf8 scripts\frozen_backtest_validation.py --strategies G_candidate_v4_r2 --years 2017 2018 2019 2020 2021 2022 2023 2024 2026 --out-dir outputs\validation\candidate_v4_r2 --out-doc docs\candidate_v4_r2_validation.md --force
```

### 第五阶段：正式决策

```powershell
python -X utf8 scripts\generate_go_nogo_decision.py --runs outputs\validation\frozen_backtest\runs.csv outputs\validation\candidate_v2\runs.csv outputs\validation\candidate_v3\runs.csv outputs\validation\candidate_v4_r1\runs.csv outputs\validation\candidate_v4_r2\runs.csv --out docs\go_nogo_decision.md
python -X utf8 -m pytest -q
```

## 19. 风险与注意事项

| 风险 | 影响 | 应对 |
|---|---|---|
| 去重规则错误导致 future leakage | 回测结果虚高 | 严格使用 `available_date <= trade_date`，加单测 |
| 只在 audit 中忽略重复 | 数据问题被掩盖 | 必须在构建输出前唯一键断言 |
| 分区 append 旧数据 | 重建后重复仍存在 | 写入前清理目标分区或 overwrite |
| gate PASS 因子不足 | 无法形成 alpha 候选池 | 停止组装，不强行验证 |
| 空 sleeve 仍有权重 | 策略行为不可解释 | 空 sleeve 权重归零并归一化 |
| GO/NO-GO 未覆盖 r2 | 误判验收完成 | 修复脚本并加测试 |
| 复用旧 manifest | 正式验收不可信 | 正式验证使用 `--force` 新跑 |

## 20. 最终交付清单

### 代码与配置

```text
scripts/build_alpha_factors_v4.py
scripts/diagnose_growth_factor_duplicates.py
scripts/generate_go_nogo_decision.py
configs/factors_candidate_v4_r2.yaml
configs/regime_candidate_v4_r2.yaml
```

### 测试

```text
tests/test_growth_factor_pit_dedup_v4_r2.py
tests/test_audit_cache_factor_duplicates.py
tests/test_candidate_v4_r2_gate_enforcement.py
tests/test_regime_candidate_v4_r2_allocator_non_empty.py
tests/test_go_nogo_decision.py
tests/test_go_nogo_data_gate.py
```

### 审计与分析产物

```text
outputs/analysis/v4_r2_growth_duplicate_diagnosis/
outputs/analysis/v4_alpha_inputs/
outputs/analysis/factor_quality_rebuild_v4/
docs/v4_r2_growth_duplicate_root_cause.md
docs/factor_quality_rebuild_v4_report.md
docs/factors_candidate_v4_r2_selection.md
docs/sleeve_design_v4_r2.md
```

### 验证与决策产物

```text
outputs/validation/candidate_v4_r2_smoke/runs.csv
outputs/validation/candidate_v4_r2/runs.csv
docs/_v4_r2_smoke.md
docs/candidate_v4_r2_validation.md
docs/candidate_v4_r2_vs_v3_comparison.md
docs/candidate_v4_r2_vs_v4_r1_comparison.md
docs/go_nogo_decision.md
docs/strategy_v4_r2_completion_review.md
```

## 21. 最终完成定义

只有同时满足以下条件，才可认定 V4-r2 返工完成：

```text
1. audit_cache 2017-2024: FAIL=0
2. audit_cache 2026 YTD: FAIL=0
3. 四个 growth 因子 duplicate_count=0
4. 候选因子 input audit PASS
5. factor_quality_gate 中存在正式 PASS alpha
6. factors_candidate_v4_r2.yaml 无 FAIL/DATA_MISSING/input FAIL enabled
7. regime_candidate_v4_r2.yaml 无空 sleeve 非零权重
8. candidate_v4_r2_smoke/runs.csv 存在且通过
9. candidate_v4_r2/runs.csv 覆盖 2017-2024 + 2026
10. go_nogo_decision.md 包含 G_candidate_v4_r2 且不含 INCOMPLETE
11. 全量 pytest 通过
12. strategy_v4_r2_completion_review.md 给出明确 GO/NO-GO
```

若任一条件不满足，V4-r2 仍为未完成，不得进入实盘。


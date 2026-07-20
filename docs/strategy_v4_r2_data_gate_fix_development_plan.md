# Strategy V4-r2 数据质量与 Gate 修复开发方案

生成日期：2026-06-14  
前置文档：

- `docs/strategy_v4_r1_completion_review.md`
- `docs/strategy_v4_acceptance_fix_development_plan.md`
- `docs/strategy_v4_alpha_rebuild_development_plan.md`
- `docs/factor_quality_rebuild_v4_report.md`
- `docs/go_nogo_decision.md`

适用目标：基于 V4-r1 审核结果，修复 growth 因子重复键、V4 输入审计失败、factor quality gate 失效和候选池准入违规问题。只有修复完成后，才允许进入新的 `G_candidate_v4_r2` 冻结验证。

## 1. 当前问题摘要

V4-r1 已经补齐了正式冻结验证和 GO/NO-GO 链路，但仍不通过验收。

已通过：

| 项目 | 状态 |
|------|------|
| `G_candidate_v4_r1` 注册 | 通过 |
| `outputs/validation/candidate_v4_r1/runs.csv` | 存在，覆盖 2017-2024 + 2026 YTD |
| manifest 哈希 | 与当前配置一致 |
| GO/NO-GO 文档 | 已生成，不含 INCOMPLETE |
| 全量测试 | `718 passed, 20 warnings` |

未通过：

| 项目 | 当前状态 | 影响 |
|------|------|------|
| 缓存审计 | 2017-2024 和 2026 YTD 均 FAIL=5 | 冻结验证前置条件不满足 |
| growth 因子 | 4 个因子存在大量重复键 | 因子缓存不可用于正式候选 |
| V4 输入审计 | PASS=8，FAIL=23，BLOCKED=23 | alpha 输入修复未完成 |
| factor quality gate | 0 PASS，1 WATCH，20 FAIL，28 DATA_MISSING | 没有合格 alpha 候选池 |
| `factors_candidate_v4_r1.yaml` | enabled 中无 PASS 因子，且含审计失败因子 | 候选池准入违规 |
| `G_candidate_v4_r1` 表现 | 正式 NO-GO | 不可实盘 |

V4-r1 的正式策略结果：

```text
平均年化超额: -1.4%
中位数年化超额: 0.8%
正超额年份: 5/8
平均 IR: -0.36
最大单年超额亏损: -18.1%
正式判决: NO-GO
```

## 2. 修复目标

### 2.1 工程目标

1. 修复 4 个 growth 因子的重复 `(ts_code, trade_date)` 问题。
2. 使 `audit_cache.py` 在 2017-2024 与 2026 YTD 窗口达到 `FAIL=0`。
3. 使 `audit_alpha_inputs_v4.py` 中准备进入候选池的因子全部 `PASS`。
4. 重新运行 `factor_quality_rebuild.py`，形成可解释的 PASS/WATCH/FAIL 结果。
5. 重建候选池，禁止 gate FAIL 或输入审计 FAIL 因子直接进入正式候选。
6. 若候选池满足准入条件，注册 `G_candidate_v4_r2` 并完成完整冻结验证。
7. 生成正式对比报告、GO/NO-GO 文档和完成审核报告。

### 2.2 策略目标

V4-r2 不降低策略门槛：

| 指标 | GO 门槛 |
|------|------:|
| 2017-2024 平均年化超额 | > 2.0% |
| 2017-2024 中位数年化超额 | > 0.0% |
| 正超额年份 | >= 5/8 |
| 平均 IR | > 0.30 |
| 最大单年超额亏损 | > -10.0% |

V4-r2 还必须满足相对 V3 的基本改进要求：

| 指标 | 要求 |
|------|------|
| 相对 V3 胜出年份 | 建议 >= 5/8 |
| 相对 V3 平均年度超额差异 | > 0 |
| 2018、2019 不能大幅恶化 | 必须专项解释 |
| 2026 YTD | 仅观察，不调参 |

## 3. 非目标

本轮不做：

1. 不进入实盘。
2. 不进入小资金试运行。
3. 不复用 `G_candidate_v4_r1` 作为新结果名称。
4. 不用 `G_candidate_v4_lite` 替代正式候选。
5. 不在 `audit_cache FAIL > 0` 时运行正式冻结验证。
6. 不在 `factor_quality_gate PASS=0` 时继续包装候选策略。
7. 不把 `WATCH_NEUTRAL_ONLY` 因子当成 alpha 通过证据。
8. 不把输入审计 FAIL 的因子放入 `enabled_factors`。

## 4. 根因假设

### 4.1 Growth 因子重复键

失败因子：

```text
revenue_growth_ttm_cs
profit_growth_ttm_cs
growth_stability_8q_cs
earnings_acceleration_cs
```

2017-2024 审计结果：

```text
earnings_acceleration_cs rows=6385, dates=468, dup=3705
growth_stability_8q_cs  rows=6385, dates=468, dup=3705
profit_growth_ttm_cs    rows=6935, dates=513, dup=4355
revenue_growth_ttm_cs   rows=6935, dates=513, dup=4355
```

2026 YTD 审计结果：

```text
earnings_acceleration_cs rows=488, dates=41, dup=239
growth_stability_8q_cs  rows=488, dates=41, dup=239
profit_growth_ttm_cs    rows=488, dates=41, dup=239
revenue_growth_ttm_cs   rows=488, dates=41, dup=239
```

可能原因：

1. 同一股票同一交易日展开了多个报告期记录。
2. 公告日、报告期、交易日映射没有先排序去重。
3. 月度或日度 forward-fill 时重复写入。
4. 分区写入时 append 了旧数据，没有清理旧分区。
5. 因子构建脚本没有在最终输出前强制校验唯一键。

### 4.2 候选池绕过 gate

`factors_candidate_v4_r1.yaml` 中 enabled factors 没有任何 PASS 因子，说明候选池生成逻辑没有严格使用 gate 输出。

必须修复：

- 候选池生成必须读取 `factor_quality_gate.csv`。
- `PASS` 可进入 alpha 候选。
- `WATCH_NEUTRAL_ONLY` 只能进入风险/防御用途，且必须人工说明。
- `FAIL`、`DATA_MISSING`、输入审计 `FAIL` 不得进入正式 enabled。

## 5. 总体流程

```text
M0 归档 V4-r1 NO-GO
  -> M1 定位 growth 因子重复键
  -> M2 修复因子构建与缓存写入
  -> M3 重跑输入审计和缓存审计
  -> M4 重跑 factor quality gate
  -> M5 重建候选池与 sleeve
  -> M6 注册 G_candidate_v4_r2
  -> M7 冒烟测试与 manifest 校验
  -> M8 完整冻结验证
  -> M9 V4-r2 对比分析
  -> M10 正式 GO/NO-GO 与完成审核
```

硬性门禁：

```text
M3 未通过，不进入 M4。
M4 PASS 因子不足，不进入 M5。
M5 候选池不合规，不进入 M6。
M7 manifest 不一致，不进入 M8。
M10 NO-GO，不进入实盘。
```

## 6. 里程碑计划

### M0：归档 V4-r1

目标：明确 V4-r1 已经结束，结果为 NO-GO，后续使用 V4-r2 新候选名。

任务：

| ID | 任务 | 产物 | 验收 |
|----|------|------|------|
| M0.1 | 确认 V4-r1 审核报告 | `docs/strategy_v4_r1_completion_review.md` | 结论为 NO-GO |
| M0.2 | 在开发日志追加 V4-r1 关闭记录 | `docs/strategy_v4_development_log.md` | 记录 V4-r1 不再修改 |
| M0.3 | 保留 V4-r1 输出 | `outputs/validation/candidate_v4_r1/` | 不覆盖历史结果 |
| M0.4 | 定义新候选名 | `G_candidate_v4_r2` | 后续所有验证使用新名 |

验收标准：

- 不修改 V4-r1 历史 runs。
- 不覆盖 V4-r1 manifest。
- 文档中明确 V4-r1 为 NO-GO。

### M1：定位 growth 因子重复键

目标：找出重复键来源，形成修复前诊断报告。

新增建议脚本：

```text
scripts/diagnose_factor_duplicates.py
```

或在 `scripts/audit_alpha_inputs_v4.py` 中增加 duplicate 明细输出。

任务：

| ID | 任务 | 说明 | 产物 |
|----|------|------|------|
| M1.1 | 读取 4 个 growth 因子缓存 | 按 factor/year/month 分区扫描 | duplicate 明细 |
| M1.2 | 输出重复键样本 | 展示同一 `(ts_code, trade_date)` 的多条记录差异 | `outputs/analysis/v4_growth_duplicate_diagnosis/duplicate_samples.csv` |
| M1.3 | 判断重复来源 | 报告期重复、公告日重复、分区 append、forward-fill 重复 | `docs/v4_growth_duplicate_root_cause.md` |
| M1.4 | 增加单测夹具 | 构造多报告期同交易日样本 | `tests/test_alpha_factors_v4.py` |

建议命令：

```powershell
python -X utf8 scripts\diagnose_factor_duplicates.py --factors revenue_growth_ttm_cs profit_growth_ttm_cs growth_stability_8q_cs earnings_acceleration_cs --start 20170101 --end 20241231 --out outputs\analysis\v4_growth_duplicate_diagnosis
```

验收标准：

- 每个重复因子都有重复键数量、示例和根因。
- 明确最终去重规则。
- 不得只在 audit 里忽略重复。

### M2：修复 growth 因子构建

目标：修复重复键，并保证输出前强制唯一。

涉及文件：

```text
scripts/build_alpha_factors_v4.py
configs/factor_build_v4.yaml
tests/test_alpha_factors_v4.py
```

修复规则建议：

| 场景 | 去重规则 |
|------|------|
| 同股票同交易日多个报告期 | 选择 `available_date <= trade_date` 且最新的 `source_period` |
| 同报告期多个公告修订 | 选择最新 `available_date`，但不得晚于 `trade_date` |
| forward-fill 后重复 | 在展开后按 `(ts_code, trade_date)` 排序保留最后一条 |
| 分区 append 重复 | 写入前清理目标 factor/date 分区或使用覆盖写 |
| 值完全相同重复 | 仍必须去重，不能保留多行 |

必须增加最终断言：

```python
assert not df.duplicated(["ts_code", "trade_date"]).any()
```

任务：

| ID | 任务 | 验收 |
|----|------|------|
| M2.1 | 修复 growth 因子 PIT 展开逻辑 | 无 future leakage |
| M2.2 | 修复分区写入模式 | 重新构建不会 append 旧数据 |
| M2.3 | 增加输出前唯一键检查 | 重复键直接报错 |
| M2.4 | 增加单测覆盖重复报告期 | pytest 通过 |
| M2.5 | 重新生成 2017-2024 与 2026 YTD 因子缓存 | 4 个因子 dup=0 |

建议命令：

```powershell
python -X utf8 scripts\build_alpha_factors_v4.py --config configs\factor_build_v4.yaml --start 20170101 --end 20241231 --force
python -X utf8 scripts\build_alpha_factors_v4.py --config configs\factor_build_v4.yaml --start 20260101 --end 20260605 --force
python -X utf8 -m pytest tests\test_alpha_factors_v4.py tests\test_alpha_inputs_v4.py -q
```

验收标准：

```text
revenue_growth_ttm_cs dup=0
profit_growth_ttm_cs dup=0
growth_stability_8q_cs dup=0
earnings_acceleration_cs dup=0
```

### M3：重跑数据审计

目标：确认数据质量满足冻结验证前置条件。

命令：

```powershell
python -X utf8 scripts\audit_cache.py --start 20170101 --end 20241231 --verbose
python -X utf8 scripts\audit_cache.py --start 20260101 --end 20260605 --verbose
python -X utf8 scripts\audit_alpha_inputs_v4.py --start 20170101 --end 20241231 --out outputs\analysis\v4_alpha_inputs
```

验收标准：

| 审计 | 要求 |
|------|------|
| 2017-2024 `audit_cache` | FAIL=0 |
| 2026 YTD `audit_cache` | FAIL=0 |
| 进入候选池的因子 | `audit_alpha_inputs_v4` 必须 PASS |
| blocked 因子 | 必须有明确原因，不得进入 enabled |
| future leakage | 必须为 0 |

若 `audit_cache` 仍有 FAIL，停止后续流程。

### M4：重跑 factor quality gate

目标：让候选池基于真实 gate 结果，而不是手工绕过。

命令：

```powershell
python -X utf8 scripts\factor_quality_rebuild.py --config configs\factor_quality_rebuild_v4.yaml --out-dir outputs\analysis\factor_quality_rebuild_v4 --out-doc docs\factor_quality_rebuild_v4_report.md
```

必须输出：

```text
outputs/analysis/factor_quality_rebuild_v4/factor_quality_gate.csv
outputs/analysis/factor_quality_rebuild_v4/factor_candidate_pool.yaml
docs/factor_quality_rebuild_v4_report.md
docs/factor_rejection_log_v4.md
docs/factor_quality_manual_review_v4.md
```

候选因子准入规则：

| Gate 状态 | 是否可进入正式 alpha enabled | 说明 |
|------|------|------|
| PASS | 可以 | 需要保留指标证据 |
| WATCH_NEUTRAL_ONLY | 默认不进入 alpha；可进入 defensive/risk | 必须人工说明 |
| FAIL | 不可以 | 只能进入 rejection log |
| DATA_MISSING | 不可以 | 必须修复数据或移除 |
| 输入审计 FAIL | 不可以 | 优先级高于 gate |

验收标准：

- PASS 因子建议 >= 5。
- 如果 PASS 因子 < 5，停止策略组装。
- 若业务上必须人工保留 FAIL 因子，必须写入人工例外审批文档，并标记为非正式 alpha。

### M5：候选池与文档重建

目标：生成合规候选池，不再让 FAIL/DATA_MISSING 因子进入 enabled。

新增产物：

```text
configs/factors_candidate_v4_r2.yaml
docs/factors_candidate_v4_r2_selection.md
```

候选池生成逻辑建议：

1. 读取 `factor_quality_gate.csv`。
2. 读取 `audit_summary.csv`。
3. 交叉过滤：
   - 输入审计 PASS。
   - gate PASS。
   - 或 WATCH + 人工说明。
4. 输出 `enabled_factors`。
5. 输出 rejected factors 与原因。
6. 计算候选池 SHA256。

任务：

| ID | 任务 | 产物 |
|----|------|------|
| M5.1 | 生成候选池 | `configs/factors_candidate_v4_r2.yaml` |
| M5.2 | 生成选择说明 | `docs/factors_candidate_v4_r2_selection.md` |
| M5.3 | 更新淘汰日志 | `docs/factor_rejection_log_v4.md` |
| M5.4 | 增加候选池校验测试 | `tests/test_factor_candidate_v4_r2.py` |

验收标准：

- `enabled_factors` 中没有输入审计 FAIL 因子。
- `enabled_factors` 中没有 gate FAIL 因子。
- `enabled_factors` 中没有 DATA_MISSING 因子。
- WATCH 因子如果保留，文档中必须说明用途。

### M6：Sleeve/Regime 修订

目标：使 sleeve 结构与候选池一致，避免引用不存在或不合格因子。

新增产物：

```text
configs/regime_candidate_v4_r2.yaml
docs/sleeve_design_v4_r2.md
tests/test_regime_candidate_v4_r2_config.py
```

任务：

| ID | 任务 | 说明 |
|----|------|------|
| M6.1 | 根据 r2 候选池重建 sleeve | 不强行保留 r1 sleeve |
| M6.2 | 移除不合格因子引用 | 所有因子必须存在于 r2 enabled 或明确 legacy 对照 |
| M6.3 | 区分 alpha 与 defensive | WATCH 因子只能用于 defensive/risk |
| M6.4 | 默认关闭 overlay | 先验证 alpha 和 sleeve 本身 |
| M6.5 | 配置测试 | 权重和、未知因子、空 sleeve |

验收命令：

```powershell
python -X utf8 -m pytest tests\test_regime_candidate_v4_r2_config.py -q
```

### M7：注册 G_candidate_v4_r2

目标：建立新的冻结候选，不覆盖 V4-r1。

修改文件：

```text
scripts/frozen_backtest_validation.py
scripts/generate_go_nogo_decision.py
tests/test_frozen_backtest_validation.py
tests/test_go_nogo_decision.py
docs/strategy_v4_r2_freeze_spec.md
```

策略定义：

```python
"G_candidate_v4_r2": Strategy(
    name="G_candidate_v4_r2",
    label="Candidate v4 r2: data-clean alpha gate candidate",
    args=(
        "--factors-config", "configs/factors_candidate_v4_r2.yaml",
        "--strategy-mode", "regime",
        "--regime-config", "configs/regime_candidate_v4_r2.yaml",
    ),
)
```

验收命令：

```powershell
python -X utf8 -m pytest tests\test_frozen_backtest_validation.py tests\test_go_nogo_decision.py -q
```

验收标准：

- `G_candidate_v4_r2` 纳入完整性检查。
- `G_candidate_v4_r1` 保留历史，不作为最新候选。
- `G_candidate_v4_lite` 仍仅作为诊断对照。

### M8：冒烟测试

目标：确认 r2 配置可运行，manifest 与当前配置一致。

命令：

```powershell
python -X utf8 scripts\frozen_backtest_validation.py --strategies G_candidate_v4_r2 --years 2023 --force --out-dir outputs\validation\candidate_v4_r2_smoke --out-doc docs\_v4_r2_smoke.md
```

验收标准：

| 检查项 | 要求 |
|------|------|
| return_code | 0 |
| run_manifest.json | 存在 |
| factors_config_sha256 | 与 `configs/factors_candidate_v4_r2.yaml` 一致 |
| regime_config_sha256 | 与 `configs/regime_candidate_v4_r2.yaml` 一致 |
| factor_list_sha256 | 非空 |
| factor_list | 不含审计失败因子 |

### M9：完整冻结验证

目标：在数据和候选池合规后，完成正式回测。

命令：

```powershell
python -X utf8 scripts\frozen_backtest_validation.py --strategies G_candidate_v4_r2 --out-dir outputs\validation\candidate_v4_r2 --out-doc docs\candidate_v4_r2_validation.md --force
```

产物：

```text
outputs/validation/candidate_v4_r2/runs.csv
outputs/validation/candidate_v4_r2/runs_partial.csv
outputs/validation/candidate_v4_r2/logs/*.log
docs/candidate_v4_r2_validation.md
```

验收标准：

- `runs.csv` 包含 9 条 `G_candidate_v4_r2`。
- 8 个 validation 年份完整。
- 2026 YTD 单独标记。
- 所有 manifest 哈希与当前配置一致。
- 无 `NO_GO_DATA_INVALID`。
- 运行前后 `audit_cache FAIL=0`。

### M10：对比分析

目标：判断 V4-r2 是否真正优于 V3/V4-r1。

产物：

```text
docs/candidate_v4_r2_vs_v3_comparison.md
docs/candidate_v4_r2_vs_v4_r1_comparison.md
```

对比维度：

| 指标 | 说明 |
|------|------|
| 年度超额 | 每年对比 |
| 胜出年份 | V4-r2 相对 V3 和 V4-r1 |
| 平均超额差异 | 2017-2024 |
| IR 差异 | 每年和平均 |
| 换手差异 | 防止靠高换手提升收益 |
| 失败年份 | 重点看 2018、2019、2026 YTD |

验收标准：

- 相对 V3 胜出建议 >= 5/8。
- 平均超额差异必须为正。
- 不能只改善 2023/2024，同时大幅恶化 2018/2019。

### M11：正式 GO/NO-GO

目标：生成正式决策文档。

命令：

```powershell
python -X utf8 scripts\generate_go_nogo_decision.py --runs outputs\validation\frozen_backtest\runs.csv outputs\validation\candidate_v2\runs.csv outputs\validation\candidate_v3\runs.csv outputs\validation\candidate_v4_r2\runs.csv
```

产物：

```text
docs/go_nogo_decision.md
docs/strategy_v4_r2_completion_review.md
```

验收标准：

- `docs/go_nogo_decision.md` 不含 `INCOMPLETE`。
- 包含 `G_candidate_v4_r2`。
- 明确 GO 或 NO-GO。
- 若 NO-GO，不进入实盘。

## 7. 测试计划

### 7.1 局部测试

```powershell
python -X utf8 -m pytest tests\test_alpha_inputs_v4.py tests\test_alpha_factors_v4.py -q
python -X utf8 -m pytest tests\test_factor_quality_rebuild.py -q
python -X utf8 -m pytest tests\test_regime_candidate_v4_r2_config.py -q
python -X utf8 -m pytest tests\test_frozen_backtest_validation.py tests\test_go_nogo_decision.py -q
```

### 7.2 全量测试

```powershell
python -X utf8 -m pytest -q
```

全量测试必须在完整冻结验证前后各跑一次。

## 8. 数据质量验收清单

| 检查项 | 要求 |
|------|------|
| growth 因子重复键 | 0 |
| `audit_cache` 2017-2024 | FAIL=0 |
| `audit_cache` 2026 YTD | FAIL=0 |
| `audit_alpha_inputs_v4` | 候选池因子全部 PASS |
| future leakage | 0 |
| stale 规则 | 有文档说明 |
| 分区写入 | force 模式不 append 旧数据 |
| manifest | 配置哈希与当前文件一致 |

## 9. 候选池准入清单

| 检查项 | 要求 |
|------|------|
| enabled factors | 只包含输入审计 PASS 的因子 |
| gate status | alpha 因子必须 PASS |
| WATCH 因子 | 只能作为 risk/defensive，需人工说明 |
| FAIL 因子 | 不得进入 enabled |
| DATA_MISSING 因子 | 不得进入 enabled |
| 因子数量 | PASS 因子建议 >= 5 |
| 因子主题 | 至少覆盖两个 alpha 主题 |
| 选择文档 | `factors_candidate_v4_r2_selection.md` |

## 10. 退出条件

出现以下任一情况，停止 V4-r2 推进：

1. growth 因子重复键无法修复。
2. `audit_cache` 仍有 FAIL。
3. 输入审计中候选因子仍 FAIL。
4. factor gate 仍为 0 PASS。
5. 候选池只能由 FAIL/WATCH 因子组成。
6. 冒烟测试 manifest 不一致。
7. 完整冻结验证缺少年份。
8. V4-r2 相对 V3 仍整体恶化。

## 11. 实盘准入条件

V4-r2 即使完成工程验收，也必须满足以下条件才允许进入下一阶段研究：

```text
平均年化超额 > 2.0%
中位数年化超额 > 0.0%
正超额年份 >= 5/8
平均 IR > 0.30
最大单年超额亏损 > -10.0%
audit_cache FAIL=0
manifest 全部一致
GO/NO-GO 文档非 INCOMPLETE
```

若任一项不满足，结论仍为 NO-GO。

## 12. 最终交付清单

| 类型 | 文件 |
|------|------|
| 修复方案 | `docs/strategy_v4_r2_data_gate_fix_development_plan.md` |
| 重复键诊断 | `docs/v4_growth_duplicate_root_cause.md` |
| 候选池选择 | `docs/factors_candidate_v4_r2_selection.md` |
| Sleeve 设计 | `docs/sleeve_design_v4_r2.md` |
| 冻结规格 | `docs/strategy_v4_r2_freeze_spec.md` |
| 冒烟报告 | `docs/_v4_r2_smoke.md` |
| 验证报告 | `docs/candidate_v4_r2_validation.md` |
| 对比报告 | `docs/candidate_v4_r2_vs_v3_comparison.md` |
| 完成审核 | `docs/strategy_v4_r2_completion_review.md` |
| 因子配置 | `configs/factors_candidate_v4_r2.yaml` |
| Regime 配置 | `configs/regime_candidate_v4_r2.yaml` |
| 验证输出 | `outputs/validation/candidate_v4_r2/runs.csv` |

## 13. 结论

V4-r1 已经证明工程验证链路可以跑通，但也暴露出两个必须先解决的问题：

```text
1. growth 因子缓存存在重复键，数据质量不合格。
2. 候选池绕过 factor gate，没有任何 PASS 因子仍进入正式策略。
```

V4-r2 的开发重点不是继续调参，而是先修复数据和准入规则。只有在 `audit_cache FAIL=0`、候选池只包含合规因子、manifest 一致的前提下，V4-r2 的冻结验证结果才具备评审价值。

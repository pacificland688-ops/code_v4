# Strategy V4 验收修复开发方案

生成日期：2026-06-14  
前置文档：

- `docs/strategy_v4_alpha_rebuild_development_plan.md`
- `docs/strategy_v4_completion_review.md`
- `docs/strategy_v4_freeze_spec.md`
- `docs/factor_quality_rebuild_v4_report.md`
- `docs/go_nogo_decision.md`

适用目标：修复 V4 当前未通过验收的问题，使正式候选策略重新具备可复现冻结验证和 GO/NO-GO 决策条件。

## 1. 当前审核结论

V4 当前不通过验收。原因不是单一回测缺失，而是完整证据链断裂：

| 维度 | 当前状态 | 影响 |
|------|------|------|
| 正式候选 `G_candidate_v4` | 只有 partial/smoke，无完整 `runs.csv` | 不能生成正式 GO/NO-GO |
| `candidate_v4/runs.csv` | 不存在 | 无法完成 2017-2024 + 2026 YTD 冻结验证 |
| `candidate_v4_validation.md` | 不存在 | 缺少正式验证报告 |
| `candidate_v4_vs_v3_comparison.md` | 不存在 | 缺少正式 V4/V3 对比 |
| manifest | partial/smoke 与当前配置哈希不一致 | 当前结果不可作为冻结证据 |
| Alpha 输入审计 | 31 个因子中 23 个 FAIL/BLOCKED | 质量、现金流、成长因子数据未形成 |
| 因子质量 gate | 0 PASS，1 WATCH，20 FAIL，28 DATA_MISSING | 没有形成可用 V4 alpha 候选池 |
| `G_candidate_v4_lite` | 完整但 NO-GO | 只能作为诊断对照，不能替代正式 V4 |
| `docs/go_nogo_decision.md` | INCOMPLETE | 不能作为正式验收依据 |

因此，本方案将工作拆成两条线：

1. **证据链修复**：重新建立配置冻结、manifest、验证输出、GO/NO-GO 的一致性。
2. **Alpha 修复**：补齐 V4 新因子输入，重新跑 PIT 审计和 factor quality gate，形成真正可用的候选因子池。

## 2. 修复原则

### 2.1 不复用已失效冻结名

当前 `G_candidate_v4` 的 partial/smoke manifest 已与当前配置不一致。为避免混淆，修复后建议使用新候选名：

```text
G_candidate_v4_r1
```

如果坚持继续使用 `G_candidate_v4`，必须满足：

- 明确删除或归档旧 partial/smoke 结果。
- 重新生成所有 manifest。
- 文档中说明旧结果作废。

推荐方案是使用 `G_candidate_v4_r1`，保留历史记录，不覆盖已产生的证据。

### 2.2 先因子，后策略

当前 V4 的主要问题是 alpha 输入和 gate 失败。不能先补跑全窗口回测来“完成验收”。正确顺序是：

```text
数据输入审计 -> 因子构建 -> 因子质量 gate -> 候选池冻结 -> 策略冻结验证
```

### 2.3 不让 lite 版本替代正式候选

`G_candidate_v4_lite` 的定义是：

```text
configs/factors_candidate_v1.yaml + configs/regime_candidate_v4.yaml
```

它不是 V4 Alpha 重建，只能保留为诊断对照。所有正式验收指标必须基于 `factors_candidate_v4` 或修订后的 `factors_candidate_v4_r1`。

### 2.4 不使用 2026 YTD 调参

2026 YTD 只作为前瞻观察，不参与：

- 因子方向选择
- 因子 gate
- sleeve 权重调整
- regime 参数调整
- 候选策略准入均值

## 3. 修复目标

### 3.1 工程目标

1. 使 V4 输入审计输出稳定落到方案指定路径。
2. 修复或明确阻断质量、现金流、成长等核心因子。
3. 使 `factor_quality_rebuild_v4` 至少形成可解释的候选池。
4. 注册修订候选 `G_candidate_v4_r1`。
5. 完成 2017-2024 + 2026 YTD 冻结验证。
6. 生成正式 `candidate_v4_r1_validation.md`、对比文档和 GO/NO-GO 文档。

### 3.2 策略目标

修复后的候选必须达到或明确未达到以下门槛：

| 指标 | GO 门槛 |
|------|------:|
| 2017-2024 平均年化超额 | > 2.0% |
| 2017-2024 中位数年化超额 | > 0.0% |
| 正超额年份 | >= 5/8 |
| 平均 IR | > 0.30 |
| 最大单年超额亏损 | > -10.0% |

不允许通过降低门槛完成验收。

## 4. 非目标

本轮修复不做以下事项：

1. 不进入实盘。
2. 不进入小资金试运行。
3. 不以 `G_candidate_v4_lite` 作为正式 V4。
4. 不基于 2026 YTD 反向调参。
5. 不用不完整 GO/NO-GO 文档做决策。
6. 不在因子 gate 仍为 0 PASS 时继续包装正式候选。
7. 不把风险因子或 WATCH 因子伪装成正式 alpha 因子。

## 5. 里程碑计划

### M0：归档当前失败状态

目标：把当前 V4 失败状态固定下来，避免后续误用旧结果。

任务：

| ID | 任务 | 产物 | 验收 |
|----|------|------|------|
| M0.1 | 归档当前 incomplete GO/NO-GO | `docs/_review_go_nogo_decision_v4_incomplete.md` | 标题包含 INCOMPLETE |
| M0.2 | 标记 `G_candidate_v4` partial 结果为不可验收 | `docs/strategy_v4_completion_review.md` | 明确 manifest 不一致 |
| M0.3 | 在开发日志追加修复启动记录 | `docs/strategy_v4_development_log.md` | 记录当前阻断项和修复版本名 |
| M0.4 | 确认不使用 `candidate_v4_lite` 验收 | `docs/candidate_v4_lite_validation.md` 或补充说明 | 明确 lite 仅作诊断 |

验收标准：

- 任一文档中不得把 `G_candidate_v4_lite` 写成正式 V4 验收结论。
- 当前 `docs/go_nogo_decision.md` 的 INCOMPLETE 状态必须被保留或重新生成正式版本后替换。

### M1：V4 输入数据修复

目标：补齐或明确阻断 23 个 FAIL/BLOCKED 因子。

当前 blocked 因子：

```text
roe_stability_8q_cs
roa_ttm_cs
gross_margin_ttm_cs
net_margin_ttm_cs
profitability_quality_cs
asset_turnover_ttm_cs
ocf_to_mktcap_cs
ocf_to_profit_cs
fcf_yield_cs
cashflow_stability_8q_cs
accrual_quality_cs
receivable_pressure_cs
revenue_growth_ttm_cs
profit_growth_ttm_cs
growth_stability_8q_cs
growth_value_match_cs
earnings_acceleration_cs
valuation_reversion_3y_cs
quality_value_composite_cs
dividend_quality_cs
industry_relative_quality_cs
industry_relative_growth_cs
industry_relative_value_cs
```

任务：

| ID | 任务 | 说明 | 产物 |
|----|------|------|------|
| M1.1 | 检查数据源可用性 | 确认财务、现金流、利润表、资产负债表、分红等字段是否在本地缓存或 Tushare 可取 | `docs/v4_data_inventory.md` 更新 |
| M1.2 | 修复 Tushare 初始化问题 | 当前审计提示无法初始化 Tushare client，需要确认 token/env/config | `scripts/audit_alpha_inputs_v4.py` 审计不再跳过数据源检查 |
| M1.3 | 补齐基本面数据缓存 | 质量、成长、现金流字段应能覆盖 2017-2024 | `data/parquet/*` 对应缓存 |
| M1.4 | 定义保守 PIT 滞后 | 无公告日时使用保守 available_date，不允许报告期末直接生效 | `docs/v4_pit_alignment_rules.md` 更新 |
| M1.5 | 修复空因子构建 | 因子为空时必须给出明确原因，不能静默通过 | `scripts/build_alpha_factors_v4.py` |
| M1.6 | 重新运行输入审计 | 输出到方案指定路径 | `outputs/analysis/v4_alpha_inputs/` |

建议命令：

```powershell
python -X utf8 scripts\audit_alpha_inputs_v4.py --start 20170101 --end 20241231 --out outputs\analysis\v4_alpha_inputs
```

验收标准：

| 指标 | 要求 |
|------|------|
| 输入审计退出状态 | 无 future leakage |
| blocked 因子 | 有明确列表和原因 |
| 核心质量类因子 | 至少 3 个可用或明确阻断 |
| 核心现金流类因子 | 至少 2 个可用或明确阻断 |
| 核心成长类因子 | 至少 2 个可用或明确阻断 |
| 审计输出路径 | `outputs/analysis/v4_alpha_inputs/` |

如果质量、现金流、成长类数据无法补齐，本轮应停止“Alpha 重建”叙事，改为“技术/行业相对因子修复诊断”。

### M2：V4 因子构建修复

目标：让所有可用因子稳定生成缓存，且具备 PIT 追踪信息。

任务：

| ID | 任务 | 文件 | 验收 |
|----|------|------|------|
| M2.1 | 修复 V4 因子构建配置 | `configs/factor_build_v4.yaml` | build_order 与可用数据一致 |
| M2.2 | 修复候选全集配置 | `configs/factors_alpha_v4_universe.yaml` | 不包含无法解释或无数据来源的因子 |
| M2.3 | 重新生成因子缓存 | `scripts/build_alpha_factors_v4.py` | 可用因子写入 `data/parquet/factors/factor_name=*` |
| M2.4 | 为每个因子写 manifest | 构建输出 | 包含输入版本、配置哈希、PIT 规则 |
| M2.5 | 补充单测 | `tests/test_alpha_factors_v4.py` | 空数据、PIT、方向、公式均覆盖 |

建议命令：

```powershell
python -X utf8 scripts\build_alpha_factors_v4.py --config configs\factor_build_v4.yaml --start 20170101 --end 20241231 --force
python -X utf8 scripts\build_alpha_factors_v4.py --config configs\factor_build_v4.yaml --start 20260101 --end 20260605 --force
python -X utf8 -m pytest tests\test_alpha_factors_v4.py tests\test_alpha_inputs_v4.py -q
```

验收标准：

- 每个可用因子无重复 `(ts_code, trade_date)`。
- 每个基本面因子具备可解释的 `available_date` 或保守滞后。
- 空因子不得进入候选池。
- 2026 YTD 可缺少部分因子，但必须在审计报告中标记。

### M3：因子质量 Gate 重跑

目标：重新评估 V4 因子质量，只有通过 gate 的因子才能进入正式候选池。

任务：

| ID | 任务 | 产物 |
|----|------|------|
| M3.1 | 更新 gate 配置 | `configs/factor_quality_rebuild_v4.yaml` |
| M3.2 | 跑完整 factor quality rebuild | `outputs/analysis/factor_quality_rebuild_v4/` |
| M3.3 | 生成报告 | `docs/factor_quality_rebuild_v4_report.md` |
| M3.4 | 更新人工复核文档 | `docs/factor_quality_manual_review_v4.md` |
| M3.5 | 更新淘汰日志 | `docs/factor_rejection_log_v4.md` |

建议命令：

```powershell
python -X utf8 scripts\factor_quality_rebuild.py --config configs\factor_quality_rebuild_v4.yaml --out-dir outputs\analysis\factor_quality_rebuild_v4 --out-doc docs\factor_quality_rebuild_v4_report.md
```

硬性验收：

| 指标 | 要求 |
|------|------|
| PASS 因子数 | 建议 >= 5 |
| DATA_MISSING | 不得包含计划进入候选池的因子 |
| FAIL 因子 | 不得进入 `enabled_factors` |
| WATCH 因子 | 只能人工保留，必须写明用途 |
| 人工保留 | 必须区分 alpha、风险控制、组合约束 |

如果 PASS 因子仍不足 5 个：

```text
停止策略组装，不进入 M4-M7。
返回 M1/M2 继续修复数据和因子。
```

### M4：候选因子池重建

目标：生成修复后的正式候选因子池，避免当前 `factors_candidate_v4.yaml` 主要由旧因子组成的问题。

推荐产物：

```text
configs/factors_candidate_v4_r1.yaml
docs/factors_candidate_v4_r1_selection.md
```

任务：

| ID | 任务 | 说明 |
|----|------|------|
| M4.1 | 只纳入 PASS 因子 | gate 失败因子不能进入 enabled |
| M4.2 | 对 WATCH 因子单独标记 | 例如 `volatility_60_cs` 只能说明是防御/风险用途 |
| M4.3 | 移除空因子 | 所有 DATA_MISSING 不进入候选池 |
| M4.4 | 检查相关性 | 同 cluster 保留最优或经济解释最清晰者 |
| M4.5 | 固定候选池哈希 | 写入冻结说明 |

验收标准：

- `enabled_factors` 不得包含空因子。
- `enabled_factors` 不得包含未通过 gate 且无人工说明的因子。
- 候选池至少覆盖两个以上 alpha 主题；如果仍只有 value/technical，则不得称为完整 alpha 重建。

### M5：Regime/Sleeve 修订

目标：让 `regime_candidate_v4_r1.yaml` 与修复后的因子池一致。

推荐产物：

```text
configs/regime_candidate_v4_r1.yaml
docs/sleeve_design_v4_r1.md
tests/test_regime_candidate_v4_r1_config.py
```

任务：

| ID | 任务 | 说明 |
|----|------|------|
| M5.1 | 移除引用不存在或未启用的因子 | 当前 sleeve 中引用 `industry_relative_ep_cs` 等需要与候选池一致 |
| M5.2 | 重建 sleeve 结构 | 按 PASS 因子主题构建，不强行保留方案里的名称 |
| M5.3 | 区分 alpha sleeve 与防御 sleeve | 避免把低波/市值当作 alpha |
| M5.4 | 默认关闭 overlay | 先验证 alpha 重建本身 |
| M5.5 | 增加配置测试 | 检查未知因子、权重和、空 sleeve |

验收命令：

```powershell
python -X utf8 -m pytest tests\test_regime_candidate_v4_config.py -q
```

验收标准：

- `regime_candidate_v4_r1.yaml` 中所有因子必须存在于候选池或明确是 legacy 对照。
- 每个 sleeve 至少有 2 个有效因子；否则应降级为单因子诊断，不进入正式候选。
- overlay 关闭或有独立对照。

### M6：修订候选预注册

目标：注册新的冻结候选，保证后续结果与配置一一对应。

推荐候选：

```text
G_candidate_v4_r1
```

注册位置：

```text
scripts/frozen_backtest_validation.py
scripts/generate_go_nogo_decision.py
```

建议策略定义：

```python
"G_candidate_v4_r1": Strategy(
    name="G_candidate_v4_r1",
    label="Candidate v4 r1: repaired alpha rebuild + regime_candidate_v4_r1",
    args=(
        "--factors-config", "configs/factors_candidate_v4_r1.yaml",
        "--strategy-mode", "regime",
        "--regime-config", "configs/regime_candidate_v4_r1.yaml",
    ),
)
```

任务：

| ID | 任务 | 产物 |
|----|------|------|
| M6.1 | 注册策略 | `scripts/frozen_backtest_validation.py` |
| M6.2 | 纳入 GO/NO-GO 候选 | `scripts/generate_go_nogo_decision.py` |
| M6.3 | 更新冻结规格 | `docs/strategy_v4_r1_freeze_spec.md` |
| M6.4 | 更新测试 | `tests/test_frozen_backtest_validation.py`, `tests/test_go_nogo_decision.py` |

验收命令：

```powershell
python -X utf8 -m pytest tests\test_frozen_backtest_validation.py tests\test_go_nogo_decision.py -q
```

验收标准：

- 完整性检查要求 `G_candidate_v4_r1` 覆盖 2017-2024 + 2026。
- 不再把 `G_candidate_v4_lite` 当作正式候选要求。
- 若保留 lite，必须明确为 diagnostic strategy。

### M7：冒烟测试

目标：确认修订候选可运行、manifest 完整，但不用于调参。

建议命令：

```powershell
python -X utf8 scripts\frozen_backtest_validation.py --strategies G_candidate_v4_r1 --years 2023 --force --out-dir outputs\validation\candidate_v4_r1_smoke --out-doc docs\_v4_r1_smoke.md
```

验收标准：

| 检查项 | 要求 |
|------|------|
| return_code | 0 |
| run_manifest.json | 存在 |
| factors_config_sha256 | 与当前 `configs/factors_candidate_v4_r1.yaml` 一致 |
| regime_config_sha256 | 与当前 `configs/regime_candidate_v4_r1.yaml` 一致 |
| factor_list_sha256 | 非空 |
| factor_list | 与候选池一致 |

若 manifest 哈希不一致，立即停止，不进入完整冻结验证。

### M8：完整冻结验证

目标：完成正式全窗口验证。

建议命令：

```powershell
python -X utf8 scripts\frozen_backtest_validation.py --strategies G_candidate_v4_r1 --out-dir outputs\validation\candidate_v4_r1 --out-doc docs\candidate_v4_r1_validation.md --force
```

覆盖范围：

```text
2017 validation
2018 validation
2019 validation
2020 validation
2021 validation
2022 validation
2023 validation
2024 validation
2026 ytd
```

产物：

```text
outputs/validation/candidate_v4_r1/runs.csv
outputs/validation/candidate_v4_r1/runs_partial.csv
outputs/validation/candidate_v4_r1/logs/*.log
docs/candidate_v4_r1_validation.md
```

验收标准：

- `runs.csv` 包含 9 条 `G_candidate_v4_r1`。
- 8 个 validation 年份完整。
- 2026 YTD 单独标记。
- 所有 run_dir 存在。
- 所有 manifest 哈希与当前配置一致。
- 无 `NO_GO_DATA_INVALID` 正式记录。

### M9：V4-r1 对比分析

目标：明确修复后候选相对 V3、V4-lite 是否改善。

产物：

```text
docs/candidate_v4_r1_vs_v3_comparison.md
docs/candidate_v4_r1_vs_v4_lite_comparison.md
```

对比指标：

| 指标 | 要求 |
|------|------|
| 年度超额差异 | 每年列出 |
| 平均超额差异 | 2017-2024 |
| 胜出年份 | 至少与 V3 对比 |
| IR 差异 | 每年和均值 |
| 换手差异 | 避免靠换手换收益 |
| 2026 YTD | 仅观察 |

建议对比命令：

```powershell
python -X utf8 -c "import pandas as pd; v3=pd.read_csv('outputs/validation/candidate_v3/runs.csv'); r1=pd.read_csv('outputs/validation/candidate_v4_r1/runs.csv'); both=pd.concat([v3,r1]); print(both.pivot_table(index=['year','sample'], columns='strategy', values='annualized_excess_return'))"
```

验收标准：

- 若 V4-r1 不优于 V3 至少 5/8 年，不应推进。
- 若平均超额仍为负，不应推进。
- 若 2023/2024 改善但 2017/2019 大幅恶化，应判定结构性不稳定。

### M10：正式 GO/NO-GO 决策

目标：生成正式决策文档，而不是 INCOMPLETE 文档。

建议命令：

```powershell
python -X utf8 scripts\generate_go_nogo_decision.py --runs outputs\validation\frozen_backtest\runs.csv outputs\validation\candidate_v2\runs.csv outputs\validation\candidate_v3\runs.csv outputs\validation\candidate_v4_r1\runs.csv
```

产物：

```text
docs/go_nogo_decision.md
docs/strategy_v4_r1_completion_review.md
```

验收标准：

- `docs/go_nogo_decision.md` 标题不含 `INCOMPLETE`。
- 文档包含 `G_candidate_v4_r1`。
- 门槛检查完整。
- 若未达标，明确 NO-GO，不包装成“接近可实盘”。

## 6. 测试计划

### 6.1 必跑测试

局部测试：

```powershell
python -X utf8 -m pytest tests\test_alpha_inputs_v4.py tests\test_alpha_factors_v4.py -q
python -X utf8 -m pytest tests\test_factor_quality_rebuild.py -q
python -X utf8 -m pytest tests\test_regime_candidate_v4_config.py -q
python -X utf8 -m pytest tests\test_frozen_backtest_validation.py tests\test_go_nogo_decision.py -q
```

全量测试：

```powershell
python -X utf8 -m pytest -q
```

### 6.2 数据审计

```powershell
python -X utf8 scripts\audit_cache.py --start 20170101 --end 20241231 --verbose
python -X utf8 scripts\audit_cache.py --start 20260101 --end 20260605 --verbose
python -X utf8 scripts\audit_alpha_inputs_v4.py --start 20170101 --end 20241231 --out outputs\analysis\v4_alpha_inputs
```

验收：

- `audit_cache` 无 FAIL。
- `audit_alpha_inputs_v4` 无 future leakage。
- blocked 因子有明确处理。
- WARN 必须写入最终审核报告。

## 7. 文档产物清单

修复完成后应形成以下文档：

| 文档 | 说明 |
|------|------|
| `docs/strategy_v4_acceptance_fix_development_plan.md` | 本修复方案 |
| `docs/strategy_v4_development_log.md` | 追加修复过程 |
| `docs/v4_data_inventory.md` | 更新数据源状态 |
| `docs/v4_pit_alignment_rules.md` | 更新 PIT 规则 |
| `docs/factor_quality_rebuild_v4_report.md` | 重跑后的 gate 报告 |
| `docs/factors_candidate_v4_r1_selection.md` | 候选池选择说明 |
| `docs/sleeve_design_v4_r1.md` | 修订 sleeve 设计 |
| `docs/strategy_v4_r1_freeze_spec.md` | 修订候选冻结规格 |
| `docs/_v4_r1_smoke.md` | 冒烟报告 |
| `docs/candidate_v4_r1_validation.md` | 完整冻结验证报告 |
| `docs/candidate_v4_r1_vs_v3_comparison.md` | 与 V3 对比 |
| `docs/strategy_v4_r1_completion_review.md` | 修复完成审核 |
| `docs/go_nogo_decision.md` | 正式 GO/NO-GO |

## 8. 退出条件

出现以下任一情况，应停止本轮修复，不进入完整冻结验证：

1. V4 输入审计仍有核心因子大面积 BLOCKED。
2. factor quality gate 仍为 0 PASS。
3. 候选池只能由旧 V2/V3 因子组成。
4. manifest 哈希与当前配置不一致。
5. 冒烟测试失败或产生 `NO_GO_DATA_INVALID`。
6. 需要使用 2026 YTD 结果才能解释参数选择。

出现以下任一情况，应停止实盘推进：

1. V4-r1 平均年化超额 <= 2.0%。
2. 正超额年份 < 5/8。
3. 平均 IR <= 0.30。
4. 最大单年超额亏损 <= -10.0%。
5. V4-r1 相对 V3 只在少数年份改善。
6. 2023/2024 改善但 2017/2019 明显恶化，说明泛化不足。

## 9. 最终验收清单

| 检查项 | 要求 |
|------|------|
| 当前失败状态已归档 | 是 |
| `G_candidate_v4_lite` 未被当作正式候选 | 是 |
| 输入审计输出在指定目录 | `outputs/analysis/v4_alpha_inputs/` |
| 核心 blocked 因子已修复或明确阻断 | 是 |
| 因子 gate 形成可用候选池 | PASS 因子建议 >= 5 |
| 候选池无空因子 | 是 |
| regime/sleeve 与候选池一致 | 是 |
| 修订候选名明确 | 推荐 `G_candidate_v4_r1` |
| 冒烟 manifest 哈希一致 | 是 |
| 完整冻结验证覆盖 9 个窗口 | 是 |
| GO/NO-GO 文档非 INCOMPLETE | 是 |
| 完成审核文档生成 | 是 |

## 10. 结论

当前 V4 不应继续直接验收。修复工作的核心不是补一份文档，也不是补跑 `candidate_v4_lite`，而是：

```text
先修复 V4 Alpha 输入和因子 gate，
再使用新的冻结候选名重建 manifest 证据链，
最后完成正式全窗口冻结验证和 GO/NO-GO。
```

只有完成上述链路后，才能重新判断 V4 是否具备进入下一阶段风险约束组合研究的资格。

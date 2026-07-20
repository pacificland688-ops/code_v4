# Strategy V4-r2 解除阻断二次修复开发方案

生成日期：2026-06-19  
来源报告：`docs/strategy_v4_r2_unblock_completion_review.md`  
适用范围：V4-r2 gate、候选池、空 enabled 语义、smoke/full validation、manifest 校验与 GO/NO-GO 修复  
目标候选名：`G_candidate_v4_r2`

## 1. 背景与当前结论

上一轮解除阻断审核结论为：**不通过验收**。

已经解除的阻断：

1. growth 因子重复键已修复。
2. `audit_cache` 在 `2017-2024` 与 `2026 YTD` 两个窗口均达到 `FAIL=0`。
3. 全量测试通过。

仍未解除的阻断：

1. 正式 gate 文件 `outputs/analysis/factor_quality_rebuild_v4/factor_quality_gate.csv` 缺失。
2. 当前可见 gate 文件均无 PASS alpha 因子。
3. `configs/factors_candidate_v4_r2.yaml` 仍为 `enabled_factors: []`。
4. `configs/regime_candidate_v4_r2.yaml` 所有 sleeve 为空，`min_sleeves=0`。
5. `run_research.py` 仍把空 `enabled_factors` 解释为“不限制因子”，存在误用全量因子的风险。
6. smoke 验证产物缺失。
7. full validation 产物存在但 manifest hash 与当前配置不匹配，证据无效。
8. 当前 GO/NO-GO 基于无效 r2 runs，不能作为正式验收依据。

本方案目标是继续修复上述阻断。修复完成前，V4-r2 不得进入实盘或小资金试运行。

## 2. 当前验收基线

### 2.1 cache audit

已通过：

```text
2017-2024: Total 65 checks | PASS=64 | WARN=1 | FAIL=0
2026 YTD:  Total 65 checks | PASS=64 | WARN=1 | FAIL=0
```

四个 growth 因子均已达到 `dup=0`：

```text
revenue_growth_ttm_cs
profit_growth_ttm_cs
growth_stability_8q_cs
earnings_acceleration_cs
```

### 2.2 alpha input audit

当前结果：

```text
PASS: 13
WARN: 4
FAIL: 14
BLOCKED: 14
```

四个 growth 因子当前为 `WARN`：

| 因子 | 状态 | 主要原因 |
|---|---|---|
| `revenue_growth_ttm_cs` | WARN | stale 较高 |
| `profit_growth_ttm_cs` | WARN | stale 较高 |
| `growth_stability_8q_cs` | WARN | stale 较高 |
| `earnings_acceleration_cs` | WARN | stale 较高 |

### 2.3 factor gate

正式目标文件缺失：

```text
outputs/analysis/factor_quality_rebuild_v4/factor_quality_gate.csv
```

当前可见 gate 文件：

| 文件 | 状态汇总 | PASS |
|---|---|---:|
| `outputs/analysis/factor_quality_rebuild/factor_quality_gate.csv` | `FAIL=12 / DATA_MISSING=5 / SUPPORT=1` | 0 |
| `outputs/analysis/factor_quality_rebuild_v4_growth/factor_quality_gate.csv` | `FAIL=4` | 0 |

### 2.4 validation 证据

当前 full runs：

```text
outputs/validation/candidate_v4_r2/runs.csv
```

覆盖：

```text
validation: 2017-2024
ytd: 2026
return_code: 9/9 为 0
```

但全部 manifest hash 不匹配：

```text
manifest_mismatch_count: 9
```

因此当前 full runs 作废，不能作为正式验收依据。

## 3. 总体目标

### 3.1 工程目标

1. 恢复并稳定生成正式 V4 gate 文件。
2. 明确 gate PASS alpha 因子数量。
3. 修复空 `enabled_factors` 的运行语义。
4. 若 gate PASS alpha 因子 >= 3，重建 r2 候选池和 sleeve。
5. 若 gate PASS alpha 因子 < 3，明确输出 `NO_ALPHA_SOURCE`，停止 validation。
6. 重新运行 smoke validation。
7. 重新运行 full validation。
8. 对 full validation 做 manifest hash 校验。
9. 只基于 manifest 匹配的 runs 生成 GO/NO-GO。
10. 生成最终审核报告。

### 3.2 策略目标

不降低原 GO/NO-GO 门槛：

| 指标 | GO 门槛 |
|---|---:|
| 2017-2024 平均年化超额 | > 2.0% |
| 2017-2024 中位数年化超额 | > 0.0% |
| 正超额年份 | >= 5/8 |
| 平均 IR | > 0.30 |
| 最大单年超额亏损 | > -10.0% |

## 4. 非目标

本轮不做：

1. 不进入实盘。
2. 不进入小资金试运行。
3. 不覆盖 V4-r1 历史结果。
4. 不用旧 hash 的 r2 runs 作为正式验证证据。
5. 不在 gate PASS alpha 因子不足时强行包装候选池。
6. 不把 `WARN` 或 `WATCH_NEUTRAL_ONLY` 直接当成 alpha PASS。
7. 不把空 `enabled_factors` 当成全量因子运行。

## 5. 硬性门禁

```text
H0: audit_cache 两个窗口必须 FAIL=0。
H1: 正式 gate 文件必须存在。
H2: gate PASS alpha 因子 < 3 时停止，不进入候选池重建。
H3: enabled_factors 为空时，不允许运行正式 validation。
H4: 空 enabled_factors 不得被解释为全量因子。
H5: smoke validation 缺失或失败时，不进入 full validation。
H6: full validation manifest hash 不匹配时，runs 作废。
H7: GO/NO-GO 必须基于 manifest 匹配的当前 r2 runs。
H8: GO/NO-GO 为 NO-GO 时，不进入实盘。
```

## 6. 里程碑

```text
F0 固化失败基线
  -> F1 修复空 enabled_factors 语义
  -> F2 恢复正式 factor gate 产物
  -> F3 分析 gate PASS 因子数量
  -> F4 gate PASS >= 3 时重建候选池
  -> F5 重建 sleeve 与 allocator
  -> F6 新增 manifest 校验工具
  -> F7 运行 smoke validation
  -> F8 运行 full validation
  -> F9 校验 validation manifest
  -> F10 生成 GO/NO-GO 与对比报告
  -> F11 全量测试与最终审核
```

## 7. F0：固化失败基线

目标：保留当前失败证据，避免后续覆盖后无法追溯。

任务：

| ID | 任务 | 产物 | 验收 |
|---|---|---|---|
| F0.1 | 保留当前审核报告 | `docs/strategy_v4_r2_unblock_completion_review.md` | 文件存在 |
| F0.2 | 记录旧 r2 runs 无效 | `outputs/validation/candidate_v4_r2/runs.csv` | 9/9 manifest mismatch |
| F0.3 | 记录 gate 缺失状态 | `outputs/analysis/factor_quality_rebuild_v4/` | 目录缺少 `factor_quality_gate.csv` |
| F0.4 | 保留 input audit 结果 | `outputs/analysis/v4_alpha_inputs_review_verify_20260617/` | `PASS=13 / WARN=4 / FAIL=14` |

## 8. F1：修复空 enabled_factors 语义

目标：防止空候选池被误解释为全量因子池。

涉及文件：

```text
run_research.py
tests/test_factor_candidate_v4_r2.py
tests/test_candidate_v4_r2_gate_enforcement.py
tests/test_frozen_backtest_validation.py
```

当前风险代码：

```python
def _filter_enabled_factors(factor_names: list, enabled_factors: list = None):
    if not enabled_factors:
        return factor_names
```

修复要求：

```python
def _filter_enabled_factors(factor_names: list, enabled_factors: list | None = None):
    if enabled_factors is None:
        return factor_names
    return [f for f in factor_names if f in enabled_factors]
```

语义定义：

| `enabled_factors` | 含义 | 行为 |
|---|---|---|
| `None` | 未指定过滤 | 兼容旧行为，使用全部因子 |
| `[]` | 明确空候选池 | 返回空，不得使用全部因子 |
| 非空列表 | 正式候选池 | 只使用列表内因子 |

增加候选策略硬门禁：

```yaml
candidate_policy:
  formal_candidate: true
  require_non_empty_enabled_factors: true
  min_gate_pass_alpha_factors: 3
```

当 `formal_candidate=true` 且 `enabled_factors=[]`：

```text
run_research.py 必须报错或返回明确阻断状态
frozen_backtest_validation.py 不得生成正式 runs
```

测试要求：

```powershell
python -X utf8 -m pytest `
  tests\test_factor_candidate_v4_r2.py `
  tests\test_candidate_v4_r2_gate_enforcement.py `
  tests\test_frozen_backtest_validation.py `
  -q
```

验收标准：

```text
enabled_factors=[] 不再返回全部因子
formal candidate 空 enabled 运行失败
非 formal 配置不破坏旧行为
```

## 9. F2：恢复正式 factor gate 产物

目标：让 V4-r2 使用固定路径生成可复现的 gate 文件。

执行命令：

```powershell
python -X utf8 scripts\factor_quality_rebuild.py `
  --config configs\factor_quality_rebuild_v4.yaml `
  --out-dir outputs\analysis\factor_quality_rebuild_v4 `
  --out-doc docs\factor_quality_rebuild_v4_report.md `
  --profile-out outputs\analysis\factor_quality_rebuild_v4\profile.json
```

必须输出：

```text
outputs/analysis/factor_quality_rebuild_v4/factor_quality_gate.csv
outputs/analysis/factor_quality_rebuild_v4/factor_candidate_pool.yaml
docs/factor_quality_rebuild_v4_report.md
outputs/analysis/factor_quality_rebuild_v4/profile.json
```

验收命令：

```powershell
python -X utf8 -c "import pandas as pd; df=pd.read_csv('outputs/analysis/factor_quality_rebuild_v4/factor_quality_gate.csv'); print(df['quality_gate_status'].value_counts(dropna=False)); print(df[df['quality_gate_status'].eq('PASS')][['factor','quality_gate_status']])"
```

验收标准：

```text
factor_quality_gate.csv 存在
status counts 可读取
无使用旧目录 gate 文件冒充正式 gate
```

超时处理：

1. 若运行超时且无 CSV，检查 `profile.json` 或日志。
2. 定位耗时因子或阶段。
3. 不允许继续使用旧 gate 文件。

## 10. F3：分析 gate PASS 因子数量

目标：根据正式 gate 输出决定是否继续。

判定逻辑：

```text
if PASS alpha factors >= 3:
    进入 F4 候选池重建
else:
    输出 NO_ALPHA_SOURCE
    停止 validation
```

输出：

```text
docs/factor_quality_rebuild_v4_report.md
docs/factors_candidate_v4_r2_selection.md
```

分析内容：

1. PASS 因子列表。
2. FAIL 因子列表及失败原因。
3. DATA_MISSING 因子列表。
4. WARN/input audit WARN 因子是否允许人工复核。
5. growth 因子的 gate 状态。

验收标准：

```text
PASS alpha factors >= 3 才能继续
PASS alpha factors < 3 时不得生成正式 enabled_factors
```

## 11. F4：重建候选池

前置条件：

```text
正式 gate 文件存在
PASS alpha factors >= 3
```

目标文件：

```text
configs/factors_candidate_v4_r2.yaml
docs/factors_candidate_v4_r2_selection.md
```

准入规则：

| 条件 | 是否允许进入 enabled |
|---|---|
| input audit PASS + gate PASS | 允许 |
| input audit WARN + gate PASS | 需要人工复核说明 |
| gate FAIL | 禁止 |
| DATA_MISSING | 禁止 |
| input audit FAIL | 禁止 |
| WATCH_NEUTRAL_ONLY | 不可作为 alpha；可作为 defensive/risk |

配置要求：

```yaml
candidate_policy:
  formal_candidate: true
  require_non_empty_enabled_factors: true
  min_gate_pass_alpha_factors: 3

enabled_factors:
  - <gate PASS alpha factor 1>
  - <gate PASS alpha factor 2>
  - <gate PASS alpha factor 3>
```

验收标准：

```text
enabled_factors 非空
enabled_factors 数量 >= 3
每个 enabled factor 可追溯到 gate PASS
无 FAIL / DATA_MISSING / input FAIL
```

若 PASS 不足：

```text
enabled_factors 保持空
candidate_policy.formal_candidate=false 或 blocked_reason=NO_ALPHA_SOURCE
不得进入 F7/F8
```

## 12. F5：重建 sleeve 与 allocator

前置条件：

```text
enabled_factors 非空且合规
```

目标文件：

```text
configs/regime_candidate_v4_r2.yaml
docs/sleeve_design_v4_r2.md
```

规则：

1. sleeve 只能引用 `enabled_factors`、允许的 risk factor 或 neutralizer。
2. 空 sleeve 权重必须为 0。
3. 非空 sleeve 权重必须归一化。
4. `min_sleeves` 不得大于实际非空 sleeve 数。
5. 只有 defensive/risk sleeve 非空时，不得标记为正式 alpha 策略。

验收标准：

```text
所有非空 sleeve 至少 1 个有效因子
所有 regime 的权重合计约等于 1.0
空 sleeve 权重为 0
无 FAIL/DATA_MISSING 因子进入 sleeve
```

专项测试：

```powershell
python -X utf8 -m pytest `
  tests\test_factor_candidate_v4_r2.py `
  tests\test_regime_candidate_v4_r2_config.py `
  tests\test_candidate_v4_r2_gate_enforcement.py `
  -q
```

## 13. F6：新增 manifest 校验工具

目标：正式验证后自动判断 runs 是否与当前配置一致。

新增文件：

```text
scripts/validate_validation_manifest.py
tests/test_validate_validation_manifest.py
```

命令接口：

```powershell
python -X utf8 scripts\validate_validation_manifest.py `
  --runs outputs\validation\candidate_v4_r2\runs.csv `
  --factors-config configs\factors_candidate_v4_r2.yaml `
  --regime-config configs\regime_candidate_v4_r2.yaml `
  --required-validation-years 2017 2018 2019 2020 2021 2022 2023 2024 `
  --required-ytd-years 2026
```

校验项：

1. `runs.csv` 存在。
2. 年份覆盖完整。
3. `return_code=0`。
4. 每个 `run_dir` 存在 `run_manifest.json`。
5. `factors_config_sha256` 等于当前 factors config hash。
6. `regime_config_sha256` 等于当前 regime config hash。
7. `strategy` 唯一值为 `G_candidate_v4_r2`。

验收标准：

```text
任何一个 run hash 不匹配，脚本返回非 0
全部匹配时返回 0
```

## 14. F7：运行 smoke validation

前置条件：

```text
F1-F6 均通过
enabled_factors 非空
gate PASS alpha factors >= 3
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
docs/_v4_r2_smoke.md exists
覆盖 2024 validation 和 2026 ytd
return_code=0
manifest hash 与当前配置一致
```

## 15. F8：运行 full validation

前置条件：

```text
smoke validation 通过
```

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
validation 覆盖 2017-2024
ytd 覆盖 2026
return_code=0
```

禁止：

```text
不得复用旧 hash runs
不得用 --reuse-existing 作为正式验证
不得跳过 smoke
```

## 16. F9：校验 validation manifest

执行命令：

```powershell
python -X utf8 scripts\validate_validation_manifest.py `
  --runs outputs\validation\candidate_v4_r2\runs.csv `
  --factors-config configs\factors_candidate_v4_r2.yaml `
  --regime-config configs\regime_candidate_v4_r2.yaml `
  --required-validation-years 2017 2018 2019 2020 2021 2022 2023 2024 `
  --required-ytd-years 2026
```

验收标准：

```text
manifest_mismatch_count=0
missing_years=[]
return_code failures=0
```

若失败：

```text
runs.csv 作废
不得进入 GO/NO-GO
```

## 17. F10：生成 GO/NO-GO 与对比报告

前置条件：

```text
manifest 校验通过
```

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

必须更新：

```text
docs/go_nogo_decision.md
docs/candidate_v4_r2_validation_summary.md
docs/candidate_v4_r2_vs_v3_comparison.md
docs/candidate_v4_r2_vs_v4_r1_comparison.md
```

验收标准：

```text
go_nogo_decision.md 包含 G_candidate_v4_r2
go_nogo_decision.md 不含 INCOMPLETE
报告数据来自 manifest 匹配的当前 runs
```

## 18. F11：全量测试与最终审核

执行命令：

```powershell
python -X utf8 -m pytest -q
```

目标审核报告：

```text
docs/strategy_v4_r2_unblock_completion_review.md
```

报告必须包含：

1. cache audit 结果。
2. input audit 结果。
3. gate status counts。
4. PASS 因子列表。
5. candidate pool enabled 因子。
6. sleeve/allocator 合规性。
7. smoke validation 结果。
8. full validation 结果。
9. manifest 校验结果。
10. GO/NO-GO 结论。

## 19. 推荐执行顺序

### 阶段 A：语义与 gate 修复

```powershell
python -X utf8 -m pytest tests\test_factor_candidate_v4_r2.py tests\test_candidate_v4_r2_gate_enforcement.py tests\test_frozen_backtest_validation.py -q

python -X utf8 scripts\factor_quality_rebuild.py --config configs\factor_quality_rebuild_v4.yaml --out-dir outputs\analysis\factor_quality_rebuild_v4 --out-doc docs\factor_quality_rebuild_v4_report.md --profile-out outputs\analysis\factor_quality_rebuild_v4\profile.json
```

### 阶段 B：候选池与 sleeve

```powershell
python -X utf8 -m pytest tests\test_factor_candidate_v4_r2.py tests\test_regime_candidate_v4_r2_config.py tests\test_candidate_v4_r2_gate_enforcement.py -q
```

### 阶段 C：验证与 manifest

```powershell
python -X utf8 scripts\frozen_backtest_validation.py --strategies G_candidate_v4_r2 --years 2024 2026 --out-dir outputs\validation\candidate_v4_r2_smoke --out-doc docs\_v4_r2_smoke.md --force

python -X utf8 scripts\frozen_backtest_validation.py --strategies G_candidate_v4_r2 --years 2017 2018 2019 2020 2021 2022 2023 2024 2026 --out-dir outputs\validation\candidate_v4_r2 --out-doc docs\candidate_v4_r2_validation.md --force

python -X utf8 scripts\validate_validation_manifest.py --runs outputs\validation\candidate_v4_r2\runs.csv --factors-config configs\factors_candidate_v4_r2.yaml --regime-config configs\regime_candidate_v4_r2.yaml --required-validation-years 2017 2018 2019 2020 2021 2022 2023 2024 --required-ytd-years 2026
```

### 阶段 D：决策与最终测试

```powershell
python -X utf8 scripts\generate_go_nogo_decision.py --runs outputs\validation\frozen_backtest\runs.csv outputs\validation\candidate_v2\runs.csv outputs\validation\candidate_v3\runs.csv outputs\validation\candidate_v4_r1\runs.csv outputs\validation\candidate_v4_r2\runs.csv --out docs\go_nogo_decision.md

python -X utf8 -m pytest -q
```

## 20. 风险清单

| 风险 | 影响 | 处理 |
|---|---|---|
| gate 文件仍不落盘 | 无法判断 PASS 数 | profile 定位，禁止继续 |
| PASS 因子不足 | 候选池无法成立 | 输出 NO_ALPHA_SOURCE，停止 |
| 空 enabled 仍走全量因子 | 生成虚假回测 | 修复语义并加测试 |
| 旧 runs 被复用 | 验证证据无效 | 强制 hash 校验 |
| smoke 缺失 | full validation 缺少前置验证 | 必须先 smoke |
| WARN 因子误入 enabled | 准入不严 | 人工复核并记录 |
| GO/NO-GO 使用旧 runs | 决策失真 | 生成前校验 manifest |

## 21. 最终完成定义

只有同时满足以下条件，才可认定本轮二次修复完成：

```text
1. audit_cache 2017-2024 FAIL=0
2. audit_cache 2026 YTD FAIL=0
3. outputs/analysis/factor_quality_rebuild_v4/factor_quality_gate.csv 存在
4. gate PASS alpha factors >= 3
5. enabled_factors 非空且全部合规
6. run_research.py 空 enabled_factors 不再返回全部因子
7. regime_candidate_v4_r2.yaml 有合规非空 sleeve，权重归一
8. candidate_v4_r2_smoke/runs.csv 存在且 manifest 匹配
9. candidate_v4_r2/runs.csv 覆盖 2017-2024 + 2026
10. candidate_v4_r2/runs.csv manifest_mismatch_count=0
11. go_nogo_decision.md 覆盖 G_candidate_v4_r2 且不含 INCOMPLETE
12. 全量 pytest 通过
13. strategy_v4_r2_unblock_completion_review.md 给出明确 GO/NO-GO
```

若任一条件不满足，V4-r2 仍为阻断未解除，不得进入实盘。


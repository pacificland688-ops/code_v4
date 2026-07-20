# Strategy V4-r2 解除阻断开发方案

生成日期：2026-06-17  
来源依据：
- `docs/strategy_v4_r2_remediation_development_plan.md`
- `docs/strategy_v4_r2_completion_review.md`
- 2026-06-17 复核命令结果

适用目标：在 growth 重复键已修复的基础上，继续解除 V4-r2 的 gate、候选池、冻结验证和 GO/NO-GO 阻断。  
目标候选名：`G_candidate_v4_r2`

## 1. 当前状态结论

V4-r2 当前已经完成部分关键修复，但还没有解除全部阻断。

已解除：

1. growth 因子重复键阻断已解除。
2. `audit_cache` 在 `2017-2024` 与 `2026 YTD` 两个窗口均达到 `FAIL=0`。
3. `build_alpha_factors_v4.py` 已支持 `--factors` 参数，可按指定因子重建缓存。
4. `generate_go_nogo_decision.py` 已将 `G_candidate_v4_r2` 纳入正式候选列表。
5. 全量测试通过。

仍未解除：

1. factor gate 仍为 `PASS=0`，不满足候选池重建门槛。
2. 当前 `configs/factors_candidate_v4_r2.yaml` 的 `enabled_factors` 为空。
3. 当前 `configs/regime_candidate_v4_r2.yaml` 所有 sleeve 为空，`min_sleeves=0`。
4. 当前 `outputs/validation/candidate_v4_r2/runs.csv` 的 manifest hash 与当前配置不一致，不能作为正式验证证据。
5. `outputs/validation/candidate_v4_r2_smoke/runs.csv` 与 `docs/_v4_r2_smoke.md` 缺失。
6. `run_research.py` 对空 `enabled_factors` 的语义存在风险：空列表会被解释为“不限制因子”，可能导致空候选池仍使用非候选因子跑出结果。

当前正式判定：

```text
Data duplicate blocker: CLEARED
Cache audit blocker: CLEARED
Input audit blocker: PARTIAL
Factor gate blocker: NOT CLEARED
Candidate pool blocker: NOT CLEARED
Validation evidence blocker: NOT CLEARED
Production readiness: NO-GO
```

## 2. 复核基线

### 2.1 cache audit

复核命令：

```powershell
python -X utf8 scripts\audit_cache.py --start 20170101 --end 20241231 --verbose
python -X utf8 scripts\audit_cache.py --start 20260101 --end 20260605 --verbose
```

当前结果：

```text
2017-2024: Total 65 checks | PASS=64 | WARN=1 | FAIL=0
2026 YTD:  Total 65 checks | PASS=64 | WARN=1 | FAIL=0
```

四个 growth 因子在两个窗口均为 `dup=0`：

```text
revenue_growth_ttm_cs
profit_growth_ttm_cs
growth_stability_8q_cs
earnings_acceleration_cs
```

结论：重复键阻断已解除。

### 2.2 alpha input audit

复核命令：

```powershell
python -X utf8 scripts\audit_alpha_inputs_v4.py --start 20170101 --end 20241231 --out outputs\analysis\v4_alpha_inputs_review_20260617
```

当前结果：

```text
PASS: 13
WARN: 4
FAIL: 14
BLOCKED: 14
```

四个 growth 因子当前状态：

| 因子 | 状态 | 主要原因 |
|---|---|---|
| `revenue_growth_ttm_cs` | WARN | stale 较高 |
| `profit_growth_ttm_cs` | WARN | stale 较高 |
| `growth_stability_8q_cs` | WARN | stale 较高 |
| `earnings_acceleration_cs` | WARN | stale 较高 |

结论：growth 从 FAIL 修复为 WARN，但尚不能直接视为正式 PASS。

### 2.3 factor gate

当前最新正式 gate 文件：

```text
outputs/analysis/factor_quality_rebuild_v4/factor_quality_gate.csv
```

当前状态：

```text
FAIL: 25
DATA_MISSING: 24
PASS: 0
```

重点结论：

```text
gate PASS 因子数量 = 0
不满足“>= 3 个 PASS 因子再重建候选池和 sleeve”的门槛
```

### 2.4 r2 验证产物

当前存在：

```text
outputs/validation/candidate_v4_r2/runs.csv
docs/candidate_v4_r2_validation.md
docs/candidate_v4_r2_validation_summary.md
docs/candidate_v4_r2_vs_v3_comparison.md
docs/candidate_v4_r2_vs_v4_r1_comparison.md
```

但这些验证产物不能作为当前配置的正式证据，原因是 manifest hash 不匹配：

| 项目 | run manifest hash | 当前配置 hash | 是否一致 |
|---|---|---|---|
| `configs/factors_candidate_v4_r2.yaml` | `bef8a9ea5af4639bb829c3e53c0c20772b7b89d57a2661ccaf03b330077f4f95` | `87ca0529631329a56aa9b7e7ff65df3c4362b88fd9333794bdbe5893484ace37` | 否 |
| `configs/regime_candidate_v4_r2.yaml` | `98ee067235112c3c391bdfd65c61db532c315cfb8c72756c1bfaf2dd77e81433` | `1cdd6bc77f343d76b7582d3ac30e3689ee51d85787ec0c169d137e03bcaae2b9` | 否 |

当前缺失：

```text
outputs/validation/candidate_v4_r2_smoke/runs.csv
docs/_v4_r2_smoke.md
```

结论：冻结验证证据阻断未解除。

### 2.5 测试

专项测试：

```text
82 passed, 9 skipped
```

全量测试：

```text
793 passed, 12 skipped, 20 warnings
```

结论：工程测试通过，但不代表 gate 或策略验收通过。

## 3. 下一步方案可行性判断

对方提出的流程：

```text
1. 用改进后的代码重建 growth 因子缓存
2. 重新运行审计和 gate
3. 如果 gate 产生 >= 3 个 PASS 因子，再重建候选池和 sleeve，重新验证
```

总体判断：**方向可行，但必须补齐门禁与证据校验。**

需要补充：

1. 审计必须覆盖 `2017-2024` 和 `2026 YTD` 两个窗口。
2. gate 之前必须重新跑 `audit_alpha_inputs_v4.py`，不能只依赖 `audit_cache.py`。
3. gate 复跑必须确认输出落盘，并读取 status counts。
4. `PASS >= 3` 是继续重建候选池的最低条件，不满足则必须停止。
5. 重建候选池前必须修复空 `enabled_factors` 的运行语义风险。
6. 重新验证前必须先跑 smoke，再跑 full validation。
7. full validation 后必须校验 manifest hash 与当前配置一致。

## 4. 硬性门禁

后续所有开发必须遵守以下门禁：

```text
G0: audit_cache 两个窗口 FAIL=0，否则停止。
G1: 候选因子 input audit 不得为 FAIL，否则不得进入 enabled_factors。
G2: factor gate PASS < 3 时，停止候选池重建。
G3: enabled_factors 为空时，不允许运行正式 r2 validation。
G4: 空 sleeve 不得有非零权重。
G5: smoke validation 缺失或失败时，不允许运行 full validation。
G6: full validation manifest hash 不匹配时，runs 作废。
G7: GO/NO-GO 未覆盖 r2 或含 INCOMPLETE 时，不能作为正式验收依据。
G8: GO/NO-GO 为 NO-GO 时，不进入实盘。
```

## 5. 里程碑设计

```text
U0 固化当前阻断基线
  -> U1 重建 growth 因子缓存
  -> U2 重新运行 cache audit 与 input audit
  -> U3 重新运行 factor gate 并确认 PASS 数
  -> U4 修复空 enabled_factors 运行语义
  -> U5 gate PASS >= 3 后重建候选池
  -> U6 重建 regime sleeve 与 allocator
  -> U7 运行 smoke validation
  -> U8 运行 full validation
  -> U9 校验 manifest hash 与验证完整性
  -> U10 生成 GO/NO-GO 与对比报告
  -> U11 输出最终审核报告
```

## 6. U0：固化当前阻断基线

目标：保存当前状态，避免后续修复过程中混淆“数据修复已完成”和“gate 仍未通过”。

任务：

| ID | 任务 | 产物 | 验收 |
|---|---|---|---|
| U0.1 | 保存当前 cache audit 结果 | 本方案第 2.1 节 | 两个窗口 `FAIL=0` |
| U0.2 | 保存当前 input audit 结果 | `outputs/analysis/v4_alpha_inputs_review_20260617/` | `PASS=13 / WARN=4 / FAIL=14` |
| U0.3 | 保存当前 gate 结果 | `outputs/analysis/factor_quality_rebuild_v4/factor_quality_gate.csv` | `PASS=0` |
| U0.4 | 标记旧 r2 runs 非正式 | `outputs/validation/candidate_v4_r2/runs.csv` | manifest hash mismatch 已记录 |

## 7. U1：重建 growth 因子缓存

目标：用改进后的代码重新生成四个 growth 因子缓存，确保修复可复现。

执行命令：

```powershell
python -X utf8 scripts\build_alpha_factors_v4.py `
  --config configs\factor_build_v4.yaml `
  --factors revenue_growth_ttm_cs profit_growth_ttm_cs growth_stability_8q_cs earnings_acceleration_cs `
  --start 20170101 `
  --end 20241231 `
  --force

python -X utf8 scripts\build_alpha_factors_v4.py `
  --config configs\factor_build_v4.yaml `
  --factors revenue_growth_ttm_cs profit_growth_ttm_cs growth_stability_8q_cs earnings_acceleration_cs `
  --start 20260101 `
  --end 20260605 `
  --force
```

验收标准：

```text
四个 growth 因子缓存存在
2017-2024 dup=0
2026 YTD dup=0
future_leakage=0
```

## 8. U2：重新运行 cache audit 与 input audit

目标：确认数据质量和输入审计状态。

执行命令：

```powershell
python -X utf8 scripts\audit_cache.py --start 20170101 --end 20241231 --verbose
python -X utf8 scripts\audit_cache.py --start 20260101 --end 20260605 --verbose

python -X utf8 scripts\audit_alpha_inputs_v4.py `
  --start 20170101 `
  --end 20241231 `
  --out outputs\analysis\v4_alpha_inputs
```

验收标准：

```text
2017-2024 audit_cache FAIL=0
2026 YTD audit_cache FAIL=0
候选因子 input audit 不得为 FAIL
四个 growth 因子 duplicate_count=0
future_leakage_count=0
```

注意：

- input audit 为 `WARN` 的因子不得直接视为正式 PASS。
- 若 gate 或候选池准入要求必须 PASS，则 WARN 因子需要人工复核或继续修复 stale/coverage 问题。

## 9. U3：重新运行 factor gate

目标：用最新缓存和输入审计结果生成新的 gate 结果。

执行命令：

```powershell
python -X utf8 scripts\factor_quality_rebuild.py `
  --config configs\factor_quality_rebuild_v4.yaml `
  --out-dir outputs\analysis\factor_quality_rebuild_v4 `
  --out-doc docs\factor_quality_rebuild_v4_report.md
```

验收检查：

```powershell
python -X utf8 -c "import pandas as pd; df=pd.read_csv('outputs/analysis/factor_quality_rebuild_v4/factor_quality_gate.csv'); print(df['quality_gate_status'].value_counts(dropna=False)); print(df[df['quality_gate_status'].eq('PASS')][['factor','quality_gate_status']])"
```

验收标准：

```text
factor_quality_gate.csv 成功落盘
status counts 可读取
PASS alpha 因子数量 >= 3 才允许进入 U5
PASS alpha 因子数量 < 3 时停止，记录 NO_ALPHA_SOURCE
```

超时处理：

- 若 gate 运行超过预期但未输出 CSV，应保留日志并定位耗时因子。
- 不得使用旧 gate 文件冒充新结果。
- 建议必要时增加 `--profile-out`：

```powershell
python -X utf8 scripts\factor_quality_rebuild.py `
  --config configs\factor_quality_rebuild_v4.yaml `
  --out-dir outputs\analysis\factor_quality_rebuild_v4 `
  --out-doc docs\factor_quality_rebuild_v4_report.md `
  --profile-out outputs\analysis\factor_quality_rebuild_v4\profile.json
```

## 10. U4：修复空 enabled_factors 运行语义

目标：避免空候选池被运行系统解释为“使用全部因子”。

当前风险位置：

```text
run_research.py
```

当前风险逻辑：

```python
def _filter_enabled_factors(factor_names: list, enabled_factors: list = None):
    if not enabled_factors:
        return factor_names
```

问题：

- `enabled_factors=[]` 会返回全部 `factor_names`。
- 对正式候选池来说，空 enabled 应表示“没有可用 alpha 因子，应阻断运行”，而不是“不限制因子”。

修复要求：

1. 区分 `enabled_factors is None` 和 `enabled_factors == []`。
2. `None` 可保留旧行为：不限制因子。
3. 空列表应返回空列表，或在正式 candidate 配置下直接报错。
4. 增加对 `formal_candidate: true` 或 `candidate_name: G_candidate_v4_r2` 的硬性检查。
5. 当 enabled 为空且策略模式为正式候选时，冻结验证脚本必须失败，而不是产生可交易组合。

建议实现：

```python
def _filter_enabled_factors(factor_names: list, enabled_factors: list | None = None):
    if enabled_factors is None:
        return factor_names
    return [f for f in factor_names if f in enabled_factors]
```

同时在候选配置中增加：

```yaml
candidate_policy:
  formal_candidate: true
  require_non_empty_enabled_factors: true
  min_gate_pass_alpha_factors: 3
```

验收测试：

```text
tests/test_candidate_v4_r2_gate_enforcement.py
tests/test_factor_candidate_v4_r2.py
tests/test_frozen_backtest_validation.py
```

新增测试场景：

1. `enabled_factors=None` 时保留旧默认行为。
2. `enabled_factors=[]` 时不得返回全部因子。
3. formal candidate 且 enabled 为空时，validation 必须失败。
4. formal candidate 且 gate PASS < 3 时，validation 必须失败。

## 11. U5：gate PASS 后重建候选池

前置条件：

```text
factor_quality_gate PASS alpha factors >= 3
```

目标文件：

```text
configs/factors_candidate_v4_r2.yaml
docs/factors_candidate_v4_r2_selection.md
```

候选池准入规则：

| 因子状态 | 是否可进入 enabled |
|---|---|
| input audit PASS + gate PASS | 可以 |
| input audit WARN + gate PASS | 需要人工复核说明后才可进入 |
| WATCH_NEUTRAL_ONLY | 不可作为 alpha，可用于 defensive/risk |
| FAIL | 不可进入 |
| DATA_MISSING | 不可进入 |
| input audit FAIL | 不可进入 |

验收标准：

```text
enabled_factors 非空
enabled_factors 至少包含 3 个 gate PASS alpha 因子
enabled_factors 无 FAIL/DATA_MISSING/input FAIL
每个 enabled factor 都能在 gate 与 input audit 中追溯
```

如果 gate PASS < 3：

```text
不得重建正式候选池
保持 NO_ALPHA_SOURCE
输出阻断报告
```

## 12. U6：重建 regime sleeve 与 allocator

目标文件：

```text
configs/regime_candidate_v4_r2.yaml
docs/sleeve_design_v4_r2.md
```

重建规则：

1. 只把 enabled alpha 因子分配到相应 sleeve。
2. `WATCH_NEUTRAL_ONLY` 只能进入 defensive/risk，并必须有人工说明。
3. 空 sleeve 权重必须为 0。
4. 非空 sleeve 权重重新归一化。
5. `min_sleeves` 不得大于实际非空 sleeve 数。
6. 若只有 defensive sleeve 非空，不允许标记为正式 alpha 策略。

验收标准：

```text
所有非空 sleeve 的因子都在 enabled_factors 或 risk/neutralizer 白名单中
所有空 sleeve 权重为 0
每个 regime 的 sleeve 权重合计约等于 1.0
min_sleeves 合理
```

专项测试：

```powershell
python -X utf8 -m pytest `
  tests\test_factor_candidate_v4_r2.py `
  tests\test_regime_candidate_v4_r2_config.py `
  tests\test_candidate_v4_r2_gate_enforcement.py `
  -q
```

## 13. U7：运行 smoke validation

前置条件：

```text
U3 gate PASS >= 3
U4 空 enabled 语义已修复
U5 候选池合规
U6 sleeve/allocator 合规
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
runs 覆盖 2024 validation 与 2026 ytd
return_code=0
manifest hash 与当前 factors/regime 配置一致
```

阻断规则：

```text
smoke 缺失或失败，不进入 full validation。
```

## 14. U8：运行 full validation

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
strategy 唯一值为 G_candidate_v4_r2
所有年份 return_code=0
```

禁止事项：

```text
不得复用 manifest hash 不匹配的旧 runs
不得跳过 smoke 直接把 full validation 作为正式证据
不得在 enabled_factors 为空时运行正式 validation
```

## 15. U9：校验 manifest hash 与验证完整性

目标：确保 runs 与当前配置严格一致。

建议新增脚本：

```text
scripts/validate_validation_manifest.py
```

输入：

```text
outputs/validation/candidate_v4_r2/runs.csv
configs/factors_candidate_v4_r2.yaml
configs/regime_candidate_v4_r2.yaml
```

校验项：

1. 每个 run_dir 下存在 `run_manifest.json`。
2. `factors_config_sha256` 等于当前 `configs/factors_candidate_v4_r2.yaml` 的 SHA256。
3. `regime_config_sha256` 等于当前 `configs/regime_candidate_v4_r2.yaml` 的 SHA256。
4. 年份覆盖完整。
5. sample 标记正确。
6. return_code 均为 0。

验收命令示例：

```powershell
python -X utf8 scripts\validate_validation_manifest.py `
  --runs outputs\validation\candidate_v4_r2\runs.csv `
  --factors-config configs\factors_candidate_v4_r2.yaml `
  --regime-config configs\regime_candidate_v4_r2.yaml
```

验收标准：

```text
所有 manifest hash 匹配
无缺失年份
无失败 return_code
```

## 16. U10：生成 GO/NO-GO 与对比报告

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

必须生成或更新：

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
GO/NO-GO 指标全部来自当前 runs.csv
对比报告使用当前 manifest 匹配的 r2 runs
```

## 17. U11：输出最终审核报告

目标文件：

```text
docs/strategy_v4_r2_completion_review.md
```

报告必须包含：

1. cache audit 结果。
2. alpha input audit 结果。
3. factor gate status counts。
4. PASS 因子列表。
5. 候选池 enabled 因子与 gate/input audit 对照。
6. sleeve/allocator 合规性。
7. smoke validation 结果。
8. full validation 结果。
9. manifest hash 校验结果。
10. GO/NO-GO 判定。
11. 是否允许进入下一阶段。

最终判定规则：

```text
如果 gate PASS < 3: NO-GO, NO_ALPHA_SOURCE
如果 manifest hash 不匹配: NO-GO, VALIDATION_INVALID
如果策略指标不过门槛: NO-GO, PERFORMANCE_FAIL
只有 gate、候选池、validation、manifest、GO/NO-GO 全部通过，才可进入下一阶段讨论
```

## 18. 推荐执行顺序

### 阶段 A：数据与审计

```powershell
python -X utf8 scripts\build_alpha_factors_v4.py --config configs\factor_build_v4.yaml --factors revenue_growth_ttm_cs profit_growth_ttm_cs growth_stability_8q_cs earnings_acceleration_cs --start 20170101 --end 20241231 --force
python -X utf8 scripts\build_alpha_factors_v4.py --config configs\factor_build_v4.yaml --factors revenue_growth_ttm_cs profit_growth_ttm_cs growth_stability_8q_cs earnings_acceleration_cs --start 20260101 --end 20260605 --force
python -X utf8 scripts\audit_cache.py --start 20170101 --end 20241231 --verbose
python -X utf8 scripts\audit_cache.py --start 20260101 --end 20260605 --verbose
python -X utf8 scripts\audit_alpha_inputs_v4.py --start 20170101 --end 20241231 --out outputs\analysis\v4_alpha_inputs
```

### 阶段 B：gate 与门禁

```powershell
python -X utf8 scripts\factor_quality_rebuild.py --config configs\factor_quality_rebuild_v4.yaml --out-dir outputs\analysis\factor_quality_rebuild_v4 --out-doc docs\factor_quality_rebuild_v4_report.md
```

门禁：

```text
如果 PASS < 3，停止。
```

### 阶段 C：候选池与运行语义修复

```powershell
python -X utf8 -m pytest tests\test_candidate_v4_r2_gate_enforcement.py tests\test_factor_candidate_v4_r2.py tests\test_regime_candidate_v4_r2_config.py -q
```

门禁：

```text
enabled_factors 为空，不允许 validation。
空 sleeve 非零权重，不允许 validation。
```

### 阶段 D：验证与决策

```powershell
python -X utf8 scripts\frozen_backtest_validation.py --strategies G_candidate_v4_r2 --years 2024 2026 --out-dir outputs\validation\candidate_v4_r2_smoke --out-doc docs\_v4_r2_smoke.md --force
python -X utf8 scripts\frozen_backtest_validation.py --strategies G_candidate_v4_r2 --years 2017 2018 2019 2020 2021 2022 2023 2024 2026 --out-dir outputs\validation\candidate_v4_r2 --out-doc docs\candidate_v4_r2_validation.md --force
python -X utf8 scripts\generate_go_nogo_decision.py --runs outputs\validation\frozen_backtest\runs.csv outputs\validation\candidate_v2\runs.csv outputs\validation\candidate_v3\runs.csv outputs\validation\candidate_v4_r1\runs.csv outputs\validation\candidate_v4_r2\runs.csv --out docs\go_nogo_decision.md
python -X utf8 -m pytest -q
```

## 19. 风险清单

| 风险 | 影响 | 处理 |
|---|---|---|
| gate 长时间运行但不落盘 | 无法判断 PASS 数 | 增加 profile 输出，定位耗时步骤 |
| input audit WARN 被误当 PASS | 候选池准入不严 | WARN 必须人工复核或继续修复 |
| 空 enabled 被当成全量因子 | 生成虚假 r2 回测 | 修复 `run_research.py` 语义 |
| 旧 runs hash 不匹配 | 验证证据无效 | 重新 force 跑 smoke/full |
| 只有 defensive 因子 | 不是正式 alpha 策略 | 不允许包装为 alpha 候选 |
| PASS 因子不足 | 候选池无法成立 | 停止，输出 NO_ALPHA_SOURCE |
| GO/NO-GO 覆盖旧 runs | 决策失真 | 生成前校验 manifest |

## 20. 最终完成定义

只有同时满足以下条件，才可认定本轮“解除阻断”完成：

```text
1. 2017-2024 audit_cache FAIL=0
2. 2026 YTD audit_cache FAIL=0
3. 四个 growth 因子 dup=0
4. audit_alpha_inputs_v4 目标候选因子无 FAIL
5. factor_quality_gate PASS alpha 因子 >= 3
6. enabled_factors 非空，且全部可追溯为 gate/input 合规
7. 空 sleeve 权重为 0，非空 sleeve 权重归一
8. run_research.py 不再把空 enabled_factors 解释为全量因子
9. smoke validation 存在且通过
10. full validation 覆盖 2017-2024 + 2026
11. full validation manifest hash 与当前配置一致
12. go_nogo_decision.md 覆盖 G_candidate_v4_r2 且不含 INCOMPLETE
13. 全量 pytest 通过
14. strategy_v4_r2_completion_review.md 给出明确最终判定
```

若任一条件不满足，V4-r2 仍视为阻断未解除，不得进入实盘。


# 正式验收收口整改审核报告

生成日期：2026-06-12  
审核对象：`docs/development_audit_acceptance_closure_fix_plan.md` 对应整改交付  
审核结论：**不通过正式验收；严格复用保护、旧产物清理、测试和数据审计已通过，但候选 v2 完整冻结复验仍未执行，正式 GO/NO-GO 文档也未重新生成。**

## 1. 审核范围

本轮只审核正式验收收口方案中的剩余项：

1. 无哈希旧 manifest 是否被正式复用模式拒绝。
2. active 旧候选产物是否已清理。
3. `E_candidate_v2` 是否完成 2017-2024 validation + 2026 ytd 完整复验。
4. `candidate_v2_validation.md` 与 `go_nogo_decision.md` 是否已重新生成。
5. 测试、数据审计和 GO/NO-GO 生成流程是否满足验收标准。

## 2. 总体结论

| 项目 | 结果 | 说明 |
|---|---|---|
| 严格复用保护 | 通过 | targeted test 通过，探针未复用旧 run 而进入重跑路径 |
| active 旧候选产物清理 | 通过 | `outputs/validation/candidate_v2/runs.csv` 已不存在 |
| 旧文档过期标记 | 通过 | 旧文档已改名为 `.expired_20260612_192138.md` |
| targeted test | 通过 | `tests/test_frozen_backtest_validation.py`: 22 passed |
| 全量测试 | 通过 | `572 passed, 8 warnings` |
| 2017-2024 审计 | 关键通过 | `FAIL=0`，仍有 `adj_factor_coverage` WARN |
| 2026 YTD 审计 | 关键通过 | `FAIL=0`，仍有短样本 factor WARN |
| 候选 v2 完整复验 | 不通过 | active `outputs/validation/candidate_v2/runs.csv` 不存在 |
| `candidate_v2_validation.md` 刷新 | 不通过 | active 文档不存在，只有 expired 旧文档 |
| `go_nogo_decision.md` 刷新 | 不通过 | active 文档不存在，生成脚本因无候选 runs 拒绝输出 |

当前状态：

```text
工程收口代码：部分通过
正式验收：NO-GO
策略判定：等待候选 v2 完整复验后生成
```

## 3. 已通过项

### 3.1 严格复用保护已补上

文件：

```text
scripts/frozen_backtest_validation.py
tests/test_frozen_backtest_validation.py
```

已确认实现：

- `_manifest_matches` 增加 `allow_legacy_manifest: bool = False`。
- 严格模式下缺少以下字段会返回 False：
  - `factors_config_sha256`
  - `factor_list_sha256`
  - regime 模式下的 `regime_config_sha256`
- CLI 增加 `--allow-legacy-manifest`，并标明只用于诊断。

验证命令：

```powershell
python -X utf8 -m pytest tests\test_frozen_backtest_validation.py -q
```

结果：

```text
22 passed
```

行为探针：

```powershell
python -X utf8 scripts\frozen_backtest_validation.py --strategies E_candidate_v2 --years 2023 --reuse-existing --out-dir outputs\validation\_strict_reuse_probe --out-doc docs\_strict_reuse_probe.md
```

该探针没有直接复用旧无哈希 run，而是进入 2023 回测路径。命令因审核超时被停止，探针产物已清理：

```text
outputs/validation/_strict_reuse_probe
docs/_strict_reuse_probe.md
```

判断：

- 严格复用保护达到收口方案 M1 的目标。
- 正式复验仍应使用 `--force`，不依赖旧 run 复用。

### 3.2 active 旧候选产物已清理

检查结果：

```text
outputs/validation/candidate_v2/runs.csv: missing
outputs/validation/candidate_v2/runs_partial.csv: missing
```

归档目录存在：

```text
outputs/validation/candidate_v2/archive/runs_20260612_192132.csv
outputs/validation/candidate_v2/archive/runs_partial_20260612_192132.csv
outputs/validation/candidate_v2/archive/runs_20260612_183901.csv
```

旧文档已改名：

```text
docs/candidate_v2_validation.expired_20260612_192138.md
docs/go_nogo_decision.expired_20260612_192138.md
```

判断：

- M2 清理 active 旧产物已完成。
- 当前默认路径不再保留旧的 2023 单年候选结果。

### 3.3 测试通过

命令：

```powershell
python -X utf8 -m pytest -q
```

结果：

```text
572 passed, 8 warnings
```

判断：

- 全量测试通过。
- warnings 为既有 pandas/cvxpy/统计输入相关警告，本轮不作为阻断项。

### 3.4 数据审计关键项通过

历史窗口命令：

```powershell
python -X utf8 scripts\audit_cache.py --start 20170101 --end 20241231 --verbose
```

结果摘要：

```text
Total: 26 checks | PASS=25 | WARN=1 | FAIL=0
adj_factor_dedup PASS
adj_factor_coverage WARN: 87.6%
```

2026 YTD 命令：

```powershell
python -X utf8 scripts\audit_cache.py --start 20260101 --end 20260605 --verbose
```

结果摘要：

```text
Total: 26 checks | PASS=25 | WARN=1 | FAIL=0
factor_cs_quality WARN
adj_factor_dedup PASS
adj_factor_coverage PASS
```

判断：

- 两个审计窗口均 `FAIL=0`。
- WARN 需在最终验收中保留说明，但当前不是硬阻断。

## 4. 未通过项

### 4.1 候选 v2 完整冻结复验未执行

收口方案 M3 要求生成：

```text
outputs/validation/candidate_v2/runs.csv
outputs/validation/candidate_v2/runs_partial.csv
docs/candidate_v2_validation.md
```

当前检查：

```text
outputs/validation/candidate_v2/runs.csv: missing
docs/candidate_v2_validation.md: missing
```

日志也明确写着：

```text
M3-M5: 待用户执行
```

结论：

```text
M3 未完成，不能进入正式验收。
```

### 4.2 GO/NO-GO 文档未重新生成

命令：

```powershell
python -X utf8 scripts\generate_go_nogo_decision.py
```

结果：

```text
ERROR: Cannot generate GO/NO-GO decision — data incomplete:
  - E_candidate_v2: no runs found
```

判断：

- 生成脚本行为正确，拒绝不完整输入。
- 但因为候选 v2 复验产物不存在，正式 `docs/go_nogo_decision.md` 无法生成。

结论：

```text
M4 未完成。
```

### 4.3 manifest 可追溯性尚未形成正式证据

严格复用逻辑已经修好，但正式候选 v2 run 尚未生成，因此还不能验证：

```text
factors_config_sha256: non-empty
regime_config_sha256: non-empty
factor_list_sha256: non-empty
```

对每个正式候选年份是否都成立。

结论：

```text
manifest 可追溯能力已具备，但正式产物证据缺失。
```

## 5. 背景进程说明

审核期间发现另有一个非本轮审核启动的 `E_shock_reversal` 验证进程正在运行：

```text
scripts/frozen_backtest_validation.py --years 2017 ... 2026 --strategies E_shock_reversal ...
```

本轮未停止该任务。

本轮启动的 `_strict_reuse_probe` 探针进程因超时已停止，探针临时产物已清理。

## 6. 最终判定

本轮正式验收判定：

```text
NO-GO
```

原因：

1. 候选 v2 完整冻结复验未执行。
2. active `outputs/validation/candidate_v2/runs.csv` 不存在。
3. active `docs/candidate_v2_validation.md` 不存在。
4. active `docs/go_nogo_decision.md` 不存在。
5. 候选 v2 正式 run 的 manifest 哈希可追溯性尚无产物证据。

已完成进展：

1. 严格复用保护通过。
2. active 旧单年候选产物已清理。
3. 测试通过。
4. 数据审计关键项通过。
5. GO/NO-GO 脚本会正确拒绝不完整输入。

## 7. 下一步

只剩执行型收口，不建议继续改策略：

1. 确认没有其他高负载回测抢占资源。
2. 执行候选 v2 完整冻结复验：

```powershell
python -X utf8 scripts\frozen_backtest_validation.py --strategies E_candidate_v2 --out-dir outputs/validation/candidate_v2 --out-doc docs/candidate_v2_validation.md --force
```

3. 检查 `runs.csv`：

```powershell
Import-Csv outputs\validation\candidate_v2\runs.csv | Group-Object sample | Select-Object Count,Name
```

预期：

```text
validation: 8
ytd: 1
```

4. 检查每个 run manifest 的哈希字段非空。
5. 重新生成 GO/NO-GO 文档：

```powershell
python -X utf8 scripts\generate_go_nogo_decision.py
```

6. 重新执行最终验收。

# 最终执行闭环整改开发方案

生成日期：2026-06-12  
依据文档：`docs/development_audit_acceptance_closure_review.md`  
当前状态：代码收口项、严格复用保护、旧产物清理、测试和数据审计均已有进展；正式验收仍为 **NO-GO**，原因是候选 v2 完整冻结复验和最终文档生成尚未执行。

## 1. 背景

最新审核已经确认：

1. 严格复用保护通过：

```text
tests/test_frozen_backtest_validation.py: 22 passed
```

2. 全量测试通过：

```text
572 passed, 8 warnings
```

3. 数据审计关键项通过：

```text
2017-2024: FAIL=0
2026 YTD: FAIL=0
```

4. 旧 active 候选产物已清理：

```text
outputs/validation/candidate_v2/runs.csv: missing
outputs/validation/candidate_v2/runs_partial.csv: missing
```

5. 旧文档已标记为 expired：

```text
docs/candidate_v2_validation.expired_20260612_192138.md
docs/go_nogo_decision.expired_20260612_192138.md
```

但当前仍未完成：

1. `E_candidate_v2` 完整冻结复验。
2. `docs/candidate_v2_validation.md` 重新生成。
3. `docs/go_nogo_decision.md` 重新生成。
4. 正式候选 run manifest 哈希字段验证。
5. 最终验收审核报告。

## 2. 总体目标

本方案目标是把已完成的代码收口推进到真正验收闭环。

完成后必须满足：

| 目标 | 验收标准 |
|---|---|
| 完整复验 | `outputs/validation/candidate_v2/runs.csv` 覆盖 2017-2024 validation + 2026 ytd |
| 文档生成 | `docs/candidate_v2_validation.md` 和 `docs/go_nogo_decision.md` 存在且为本轮新生成 |
| 哈希可追溯 | 每个候选 run manifest 都有非空配置哈希和因子池哈希 |
| 因子池正确 | 每个候选 run 不包含旧弱因子 |
| 最终验收 | 测试、审计、GO/NO-GO 生成均通过 |

不再处理：

- 新策略开发。
- 新因子搜索。
- sleeve 参数调优。
- 用 2026 YTD 反向调参。

## 3. 当前剩余问题清单

| ID | 优先级 | 问题 | 当前证据 | 阻断原因 |
|---|---|---|---|---|
| P1-1 | P1 | 候选 v2 完整复验未执行 | `outputs/validation/candidate_v2/runs.csv` 不存在 | 无法计算完整跨年结果 |
| P1-2 | P1 | `candidate_v2_validation.md` 未生成 | active 文档不存在 | 候选验证报告缺失 |
| P1-3 | P1 | `go_nogo_decision.md` 未生成 | 生成脚本报 `E_candidate_v2: no runs found` | 正式策略判定缺失 |
| P1-4 | P1 | manifest 哈希没有正式产物证据 | 候选 run 尚未生成 | 不能证明配置可追溯 |
| P2-1 | P2 | 后台存在其他回测任务 | `E_shock_reversal` 进程正在运行 | 可能占用资源，影响复验耗时 |

## 4. M0：执行前资源与状态检查

### 4.1 目标

确保执行完整候选 v2 复验前，系统处于可控状态，避免并行重回测导致超时或资源争用。

### 4.2 检查后台进程

命令：

```powershell
Get-CimInstance Win32_Process -Filter "name = 'python.exe'" |
  Select-Object ProcessId,ParentProcessId,CommandLine |
  Format-List
```

判断规则：

- 如果仍有 `E_shock_reversal` 或其他长回测正在运行，建议等待其完成。
- 不建议在已有长回测占用 CPU/内存时启动 `E_candidate_v2` 全窗口复验。
- 除非明确确认是本轮无关僵尸进程，否则不要强制停止。

### 4.3 检查 active 候选目录

命令：

```powershell
Get-ChildItem outputs\validation\candidate_v2 -Force
```

预期：

```text
archive 目录存在
runs.csv 不存在
runs_partial.csv 不存在
```

若 active `runs.csv` 已重新出现但覆盖不完整，应先归档再重跑。

### 4.4 检查数据审计

命令：

```powershell
python -X utf8 scripts\audit_cache.py --start 20170101 --end 20241231 --verbose
python -X utf8 scripts\audit_cache.py --start 20260101 --end 20260605 --verbose
```

通过标准：

```text
FAIL=0
```

当前已知可接受 WARN：

- 2017-2024 `adj_factor_coverage WARN`
- 2026 YTD 短样本 `factor_cs_quality WARN`

## 5. M1：执行候选 v2 完整冻结复验

### 5.1 目标

用严格、可追溯、不可复用旧 run 的方式，生成候选 v2 完整验证结果。

### 5.2 正式命令

```powershell
python -X utf8 scripts\frozen_backtest_validation.py --strategies E_candidate_v2 --out-dir outputs/validation/candidate_v2 --out-doc docs/candidate_v2_validation.md --force
```

硬性要求：

- 必须使用 `--force`。
- 不得使用 `--reuse-existing`。
- 不得使用 `--skip-existing`。
- 不得使用 `--allow-legacy-manifest`。
- 不得在命令中额外指定 2025。

### 5.3 预期覆盖窗口

默认年份应为：

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

### 5.4 运行中监控

建议单独开窗口或日志监控：

```powershell
Get-ChildItem outputs\validation\candidate_v2\logs -File |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 5 Name,Length,LastWriteTime
```

查看最新日志：

```powershell
Get-ChildItem outputs\validation\candidate_v2\logs -File |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 1 |
  ForEach-Object { Get-Content $_.FullName -Tail 80 -Encoding UTF8 }
```

中途若失败：

1. 保留 `runs_partial.csv`。
2. 查看对应年份日志。
3. 不要手工补 `runs.csv`。
4. 修复失败原因后重新使用 `--force` 跑完整流程。

### 5.5 完成后产物

必须生成：

```text
outputs/validation/candidate_v2/runs.csv
outputs/validation/candidate_v2/runs_partial.csv
docs/candidate_v2_validation.md
outputs/validation/candidate_v2/logs/*.log
```

## 6. M2：验证候选 v2 runs.csv 完整性

### 6.1 覆盖数量检查

命令：

```powershell
Import-Csv outputs\validation\candidate_v2\runs.csv |
  Group-Object sample |
  Select-Object Count,Name
```

预期：

```text
8 validation
1 ytd
```

### 6.2 年份检查

命令：

```powershell
Import-Csv outputs\validation\candidate_v2\runs.csv |
  Select-Object year,sample,strategy,run_dir,annualized_excess_return,information_ratio,go_nogo_overall |
  Format-Table -AutoSize
```

必须满足：

- 年份包含 2017-2024、2026。
- `strategy` 全部为 `E_candidate_v2`。
- `run_dir` 全部非空且目录存在。
- `annualized_excess_return` 非空。
- `information_ratio` 非空。

### 6.3 缺失检查脚本

建议使用以下 PowerShell 片段：

```powershell
$rows = Import-Csv outputs\validation\candidate_v2\runs.csv
$validationYears = $rows | Where-Object { $_.sample -eq 'validation' } | ForEach-Object { [int]$_.year }
$ytdYears = $rows | Where-Object { $_.sample -eq 'ytd' } | ForEach-Object { [int]$_.year }
$missingValidation = @(2017,2018,2019,2020,2021,2022,2023,2024) | Where-Object { $_ -notin $validationYears }
$missingYtd = @(2026) | Where-Object { $_ -notin $ytdYears }
[pscustomobject]@{
  validation_count = $validationYears.Count
  ytd_count = $ytdYears.Count
  missing_validation = ($missingValidation -join ',')
  missing_ytd = ($missingYtd -join ',')
}
```

预期：

```text
validation_count: 8
ytd_count: 1
missing_validation: empty
missing_ytd: empty
```

## 7. M3：验证 manifest 哈希与因子池

### 7.1 目标

证明每个正式候选 run 都是新逻辑生成，且可追溯到当前配置。

### 7.2 哈希字段检查

命令：

```powershell
Import-Csv outputs\validation\candidate_v2\runs.csv | ForEach-Object {
  $manifest = Join-Path $_.run_dir "run_manifest.json"
  $j = Get-Content $manifest -Raw | ConvertFrom-Json
  [pscustomobject]@{
    year = $_.year
    sample = $_.sample
    run_id = $j.run_id
    factors_hash_ok = -not [string]::IsNullOrWhiteSpace($j.factors_config_sha256)
    regime_hash_ok = -not [string]::IsNullOrWhiteSpace($j.regime_config_sha256)
    factor_list_hash_ok = -not [string]::IsNullOrWhiteSpace($j.factor_list_sha256)
    factor_list = ($j.factor_list -join ",")
  }
} | Format-Table -AutoSize
```

通过标准：

```text
factors_hash_ok: True
regime_hash_ok: True
factor_list_hash_ok: True
```

### 7.3 旧弱因子排除检查

旧弱因子：

```text
momentum_120_cs
momentum_60_cs
reversal_20_cs
volatility_20_cs
```

检查命令：

```powershell
$bad = @('momentum_120_cs','momentum_60_cs','reversal_20_cs','volatility_20_cs')
Import-Csv outputs\validation\candidate_v2\runs.csv | ForEach-Object {
  $manifest = Join-Path $_.run_dir "run_manifest.json"
  $j = Get-Content $manifest -Raw | ConvertFrom-Json
  $presentBad = $j.factor_list | Where-Object { $_ -in $bad }
  [pscustomobject]@{
    year = $_.year
    run_id = $j.run_id
    has_old_weak_factor = ($presentBad.Count -gt 0)
    old_weak_factors = ($presentBad -join ",")
    factor_list = ($j.factor_list -join ",")
  }
} | Format-Table -AutoSize
```

通过标准：

```text
has_old_weak_factor: False
```

### 7.4 目标因子池检查

目标因子池：

```text
bp_cs
ep_cs
pv_divergence_20_cs
reversal_5_cs
sp_cs
```

每个 run 的 `factor_list` 应为上述集合，或至少不包含旧弱因子。若因数据覆盖导致某些目标因子在某年缺失，必须在 `candidate_v2_validation.md` 中说明原因。

## 8. M4：重新生成 GO/NO-GO 文档

### 8.1 前置条件

必须先通过：

- M2 runs.csv 完整性检查。
- M3 manifest 哈希与因子池检查。

### 8.2 生成命令

```powershell
python -X utf8 scripts\generate_go_nogo_decision.py
```

不得使用：

```text
--allow-incomplete
```

### 8.3 预期结果

生成：

```text
docs/go_nogo_decision.md
```

脚本退出码为 0。

文档必须满足：

1. 标题不包含 `INCOMPLETE`。
2. `E_candidate_v2` 不显示 `1/1`。
3. 年度表包含 `E_candidate_v2` 的 2017-2024。
4. 2026 YTD 前瞻观察非空。
5. 判定规则与 `runs.csv` 一致。

检查命令：

```powershell
Select-String -Path docs\go_nogo_decision.md -Pattern "INCOMPLETE|1/1|E_candidate_v2|2026 YTD"
```

## 9. M5：最终回归验证

### 9.1 必跑命令

```powershell
python -X utf8 -m pytest -q
python -X utf8 scripts\audit_cache.py --start 20170101 --end 20241231 --verbose
python -X utf8 scripts\audit_cache.py --start 20260101 --end 20260605 --verbose
python -X utf8 scripts\generate_go_nogo_decision.py
```

### 9.2 通过标准

| 检查 | 标准 |
|---|---|
| pytest | 全部通过 |
| 2017-2024 audit | `FAIL=0` |
| 2026 YTD audit | `FAIL=0` |
| GO/NO-GO 生成 | 退出码 0 |
| candidate runs | 8 validation + 1 ytd |
| manifest | 哈希字段非空 |
| 因子池 | 不含旧弱因子 |

### 9.3 可接受 WARN

当前可接受：

- 2017-2024 `adj_factor_coverage WARN`
- 2026 YTD `factor_cs_quality WARN`
- 测试中的 pandas/cvxpy/统计常量输入 warnings

所有 FAIL 都不可接受。

## 10. M6：最终验收审核报告

### 10.1 目标

形成最终审核文档，明确工程验收和策略判定。

### 10.2 建议文件

```text
docs/development_audit_final_acceptance_review.md
```

### 10.3 必须包含

1. 执行命令清单。
2. `pytest` 结果。
3. 两个 `audit_cache` 结果。
4. `runs.csv` 覆盖表。
5. 每个 run 的 manifest 哈希检查结果。
6. 旧弱因子排除检查结果。
7. `go_nogo_decision.md` 生成结果。
8. 最终判定：
   - 工程验收：GO 或 NO-GO
   - 策略判定：GO 或 NO-GO

## 11. 最终判定规则

工程验收 GO 必须同时满足：

```text
pytest: PASS
2017-2024 audit: FAIL=0
2026 YTD audit: FAIL=0
candidate_v2 runs.csv: 8 validation + 1 ytd
candidate run manifests: all hashes non-empty
candidate run manifests: no old weak factors
go_nogo_decision.md: generated successfully, not INCOMPLETE
```

否则：

```text
工程验收：NO-GO
```

策略判定不预设，以重新生成后的 `docs/go_nogo_decision.md` 为准。

## 12. 推荐执行顺序

1. 等待或确认其他长回测进程结束。
2. 跑 M0 状态检查。
3. 执行 M1 完整冻结复验。
4. 执行 M2 runs.csv 完整性检查。
5. 执行 M3 manifest 哈希和因子池检查。
6. 执行 M4 GO/NO-GO 文档生成。
7. 执行 M5 最终回归验证。
8. 编写 M6 最终验收审核报告。

当前不要再新增开发任务；核心是把已经具备的脚本能力跑出正式产物。

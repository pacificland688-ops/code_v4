# 正式验收收口整改开发方案

生成日期：2026-06-12  
依据文档：`docs/development_audit_followup_completion_review.md`  
当前状态：数据审计和测试已有明显进展，但正式验收仍为 **NO-GO**。本方案只处理剩余验收阻断项，不再扩展新策略、不调参、不新增候选。

## 1. 背景

上一轮整改完成后，审核确认以下内容已经通过：

1. 单元测试通过：

```text
570 passed, 8 warnings
```

2. 2017-2024 历史窗口数据审计关键项通过：

```text
Total: 25 checks | PASS=24 | WARN=1 | FAIL=0
adj_factor_dedup PASS
```

3. 2026 YTD 数据审计关键项通过：

```text
Total: 25 checks | PASS=24 | WARN=1 | FAIL=0
```

4. `scripts/generate_go_nogo_decision.py` 已能在候选数据不完整时拒绝生成正式 GO/NO-GO 文档。

但正式验收仍未通过，原因集中在 4 个硬点：

1. 候选 v2 完整冻结复验尚未执行。
2. 旧 active 候选产物仍停留在默认读取路径。
3. `candidate_v2_validation.md` 与 `go_nogo_decision.md` 仍是旧文档。
4. `--reuse-existing` 仍可复用无哈希旧 manifest，不满足正式验收可追溯要求。

## 2. 总体目标

完成本方案后，应达到：

| 目标 | 验收标准 |
|---|---|
| 严格复用保护 | 无哈希旧 run 在正式复用模式下不能匹配 |
| active 产物干净 | `outputs/validation/candidate_v2` 中不再保留旧单年 active `runs.csv` |
| 完整候选复验 | `E_candidate_v2` 覆盖 2017-2024 validation + 2026 ytd |
| 文档刷新 | `candidate_v2_validation.md` 和 `go_nogo_decision.md` 均由完整新产物生成 |
| manifest 可追溯 | 候选 v2 每个正式 run 都有非空配置哈希与因子池哈希 |

最终状态：

```text
工程验收：GO
策略判定：由重新生成的 go_nogo_decision.md 决定
```

## 3. 问题清单

| ID | 优先级 | 问题 | 当前证据 | 影响 |
|---|---|---|---|---|
| P1-1 | P1 | 候选 v2 完整复验未执行 | active `runs.csv` 只有 2023 一条 | 无法给出跨年策略判定 |
| P1-2 | P1 | 旧 active 产物未清理 | `outputs/validation/candidate_v2/runs.csv` 仍是 2026-06-11 旧文件 | 默认流程仍读取旧数据 |
| P1-3 | P1 | 文档未刷新 | `candidate_v2_validation.md`、`go_nogo_decision.md` 仍是旧内容 | 文档与当前代码状态不一致 |
| P1-4 | P1 | 无哈希旧 manifest 仍可复用 | `--reuse-existing` 探针复用了无哈希旧 run | 不能保证配置可追溯 |
| P2-1 | P2 | 旧 manifest 哈希字段未回填 | 历史 run 的哈希字段为空 | 历史产物不可作为正式证据 |

## 4. M1：修复严格 run 复用保护

### 4.1 目标

正式验收模式下，只有 manifest 完整且哈希匹配的 run 才能被 `--reuse-existing` 复用。

### 4.2 当前问题

`scripts/frozen_backtest_validation.py` 中 `_manifest_matches` 当前逻辑为：

```python
if manifest_fc_hash and current_fc_hash and manifest_fc_hash != current_fc_hash:
    return False
```

该逻辑只在 manifest 哈希字段存在时比对。旧 manifest 缺少哈希时不会失败。

测试中也存在兼容旧行为的用例：

```text
test_no_hash_fields_in_manifest_allows_match
```

这与正式验收目标冲突。

### 4.3 开发任务

| 任务 | 文件 | 说明 |
|---|---|---|
| M1.1 | `scripts/frozen_backtest_validation.py` | 为 `_manifest_matches` 增加 `allow_legacy_manifest: bool = False` 参数 |
| M1.2 | `scripts/frozen_backtest_validation.py` | 当 `check_hashes=True` 且 `allow_legacy_manifest=False` 时，缺少哈希字段直接返回 False |
| M1.3 | `scripts/frozen_backtest_validation.py` | CLI 新增 `--allow-legacy-manifest`，仅用于诊断兼容 |
| M1.4 | `scripts/frozen_backtest_validation.py` | `--reuse-existing` 默认启用严格哈希校验 |
| M1.5 | `tests/test_frozen_backtest_validation.py` | 修改旧测试：无哈希 manifest 默认不允许匹配 |
| M1.6 | `tests/test_frozen_backtest_validation.py` | 新增测试：显式 `allow_legacy_manifest=True` 才允许旧 manifest 匹配 |

### 4.4 建议实现

伪代码：

```python
def _require_manifest_hash(manifest: dict, key: str, label: str) -> str | None:
    value = manifest.get(key)
    if not value:
        return None
    return str(value)

def _manifest_matches(..., check_hashes: bool = True, allow_legacy_manifest: bool = False) -> bool:
    ...
    if check_hashes:
        required_hash_fields = [
            "factors_config_sha256",
            "factor_list_sha256",
        ]
        if expected_mode == "regime":
            required_hash_fields.append("regime_config_sha256")

        missing = [k for k in required_hash_fields if not manifest.get(k)]
        if missing and not allow_legacy_manifest:
            return False

        if missing and allow_legacy_manifest:
            return True

        if manifest["factors_config_sha256"] != _compute_file_sha256(expected_factors):
            return False

        if expected_mode == "regime" and manifest["regime_config_sha256"] != _compute_file_sha256(expected_regime):
            return False

        if manifest["factor_list_sha256"] != _compute_factor_list_hash(manifest.get("factor_list", [])):
            return False
```

注意：

- `allow_legacy_manifest=True` 只能用于临时诊断，不得用于正式验收命令。
- 帮助文本必须明确说明 legacy 复用不可作为正式验收依据。

### 4.5 验收命令

先跑针对性测试：

```powershell
python -X utf8 -m pytest tests\test_frozen_backtest_validation.py -q
```

再跑探针：

```powershell
python -X utf8 scripts\frozen_backtest_validation.py --strategies E_candidate_v2 --years 2023 --reuse-existing --out-dir outputs/validation/_reuse_probe --out-doc docs/_reuse_probe.md
```

预期：

```text
不得复用无哈希旧 run
```

如果该命令因为不复用而重新跑 2023，则说明严格复用保护生效。探针产物确认后应清理：

```powershell
Remove-Item -Recurse -Force outputs\validation\_reuse_probe
Remove-Item -Force docs\_reuse_probe.md
```

## 5. M2：清理 active 旧候选产物

### 5.1 目标

完整复验前，默认读取路径中不能再保留旧单年结果。

### 5.2 当前问题

以下文件仍是旧产物：

```text
outputs/validation/candidate_v2/runs.csv
outputs/validation/candidate_v2/runs_partial.csv
docs/candidate_v2_validation.md
docs/go_nogo_decision.md
```

其中 `runs.csv` 当前只有：

```text
2023 validation E_candidate_v2
```

### 5.3 开发任务

| 任务 | 文件/目录 | 说明 |
|---|---|---|
| M2.1 | `outputs/validation/candidate_v2/archive` | 将旧 `runs.csv`、`runs_partial.csv` 移入带时间戳归档 |
| M2.2 | `outputs/validation/candidate_v2` | 删除 active 旧 `runs.csv` 与 `runs_partial.csv` |
| M2.3 | `docs/candidate_v2_validation.md` | 完整重跑前可暂存为 `.expired.md`，完整重跑后覆盖 |
| M2.4 | `docs/go_nogo_decision.md` | 完整重跑前可暂存为 `.expired.md`，完整重跑后覆盖 |
| M2.5 | `docs/development_audit_followup_fix_log.md` | 记录归档文件名和时间 |

### 5.4 建议命令

```powershell
$ts = Get-Date -Format "yyyyMMdd_HHmmss"
New-Item -ItemType Directory -Force outputs\validation\candidate_v2\archive
Move-Item outputs\validation\candidate_v2\runs.csv outputs\validation\candidate_v2\archive\runs_$ts.csv
Move-Item outputs\validation\candidate_v2\runs_partial.csv outputs\validation\candidate_v2\archive\runs_partial_$ts.csv
```

文档可在完整重跑后直接覆盖。若需要先标记过期：

```powershell
Move-Item docs\candidate_v2_validation.md docs\candidate_v2_validation.expired_$ts.md
Move-Item docs\go_nogo_decision.md docs\go_nogo_decision.expired_$ts.md
```

### 5.5 验收命令

```powershell
Test-Path outputs\validation\candidate_v2\runs.csv
Test-Path outputs\validation\candidate_v2\runs_partial.csv
```

预期：

```text
False
False
```

如果后续立即执行完整复验，则复验完成后这两个文件应由新流程重新生成。

## 6. M3：执行候选 v2 完整冻结复验

### 6.1 目标

生成完整、可追溯、可用于 GO/NO-GO 的候选 v2 复验结果。

### 6.2 前置条件

必须先满足：

1. M1 严格复用保护通过。
2. M2 active 旧产物已清理。
3. 数据审计关键项通过：

```powershell
python -X utf8 scripts\audit_cache.py --start 20170101 --end 20241231 --verbose
python -X utf8 scripts\audit_cache.py --start 20260101 --end 20260605 --verbose
```

预期：

```text
FAIL=0
```

### 6.3 正式复验命令

```powershell
python -X utf8 scripts\frozen_backtest_validation.py --strategies E_candidate_v2 --out-dir outputs/validation/candidate_v2 --out-doc docs/candidate_v2_validation.md --force
```

说明：

- 必须使用 `--force`。
- 不得使用 `--allow-legacy-manifest`。
- 不得使用旧 `--skip-existing`。

### 6.4 必须覆盖年份

```text
validation:
- 2017
- 2018
- 2019
- 2020
- 2021
- 2022
- 2023
- 2024

ytd:
- 2026
```

### 6.5 产物要求

复验完成后必须存在：

```text
outputs/validation/candidate_v2/runs.csv
outputs/validation/candidate_v2/runs_partial.csv
docs/candidate_v2_validation.md
```

`runs.csv` 至少包含 9 条 `E_candidate_v2` 记录。

### 6.6 验收命令

```powershell
Import-Csv outputs\validation\candidate_v2\runs.csv |
  Group-Object sample |
  Select-Object Count,Name
```

预期：

```text
validation: 8
ytd: 1
```

检查年份：

```powershell
Import-Csv outputs\validation\candidate_v2\runs.csv |
  Select-Object year,sample,strategy,run_dir,annualized_excess_return,information_ratio,go_nogo_overall |
  Format-Table -AutoSize
```

预期：

- 年份覆盖完整。
- 每条记录 `run_dir` 非空。
- 每条记录关键指标非空。

### 6.7 manifest 哈希校验

每个候选 run 都必须有：

```text
factors_config_sha256
regime_config_sha256
factor_list_sha256
```

建议检查脚本：

```powershell
Import-Csv outputs\validation\candidate_v2\runs.csv | ForEach-Object {
  $manifest = Join-Path $_.run_dir "run_manifest.json"
  $j = Get-Content $manifest -Raw | ConvertFrom-Json
  [pscustomobject]@{
    year = $_.year
    run_id = $j.run_id
    factors_hash_ok = -not [string]::IsNullOrWhiteSpace($j.factors_config_sha256)
    regime_hash_ok = -not [string]::IsNullOrWhiteSpace($j.regime_config_sha256)
    factor_list_hash_ok = -not [string]::IsNullOrWhiteSpace($j.factor_list_sha256)
    factor_list = ($j.factor_list -join ",")
  }
} | Format-Table -AutoSize
```

预期：

- 三个 hash 字段全部为 True。
- `factor_list` 不包含：
  - `momentum_120_cs`
  - `momentum_60_cs`
  - `reversal_20_cs`
  - `volatility_20_cs`

## 7. M4：重新生成 GO/NO-GO 文档

### 7.1 目标

用完整候选复验产物重新生成正式决策文档。

### 7.2 前置条件

必须先完成 M3，且：

```text
outputs/validation/candidate_v2/runs.csv
```

覆盖完整年份。

### 7.3 生成命令

```powershell
python -X utf8 scripts\generate_go_nogo_decision.py
```

不得使用：

```text
--allow-incomplete
```

### 7.4 验收标准

`docs/go_nogo_decision.md` 必须满足：

1. 生成日期为本轮复验后的时间。
2. `E_candidate_v2` 不再显示 `1/1`。
3. 年度表中 `E_candidate_v2` 覆盖 2017-2024。
4. 2026 YTD 前瞻观察非空。
5. 文档标题不包含 `INCOMPLETE`。
6. 脚本退出码为 0。

检查命令：

```powershell
Select-String -Path docs\go_nogo_decision.md -Pattern "E_candidate_v2|1/1|INCOMPLETE|2026 YTD"
```

预期：

- 不应出现 `1/1`。
- 不应出现 `INCOMPLETE`。
- 应出现 2026 YTD 候选 v2 指标。

## 8. M5：最终回归验证

### 8.1 必跑命令

```powershell
python -X utf8 -m pytest -q
python -X utf8 scripts\audit_cache.py --start 20170101 --end 20241231 --verbose
python -X utf8 scripts\audit_cache.py --start 20260101 --end 20260605 --verbose
python -X utf8 scripts\generate_go_nogo_decision.py
```

### 8.2 通过标准

| 命令 | 标准 |
|---|---|
| `pytest` | 全部通过 |
| 2017-2024 audit | `FAIL=0` |
| 2026 YTD audit | `FAIL=0` |
| GO/NO-GO 生成 | 退出码 0，无 incomplete |

### 8.3 可接受 WARN

当前可接受：

1. `adj_factor_coverage WARN`，但需保留说明。
2. 2026 YTD 短样本因子覆盖 WARN。
3. pandas/cvxpy/统计输入相关测试 warnings。

若出现新的 FAIL，不得验收。

## 9. 交付清单

完成后必须交付：

| 交付物 | 要求 |
|---|---|
| `scripts/frozen_backtest_validation.py` | 严格复用保护，默认拒绝无哈希旧 manifest |
| `tests/test_frozen_backtest_validation.py` | 覆盖 strict/legacy 两种复用行为 |
| `outputs/validation/candidate_v2/runs.csv` | 9 条完整候选 v2 记录 |
| `docs/candidate_v2_validation.md` | 由完整复验生成 |
| `docs/go_nogo_decision.md` | 由完整输入生成，非 incomplete |
| `docs/development_audit_followup_fix_log.md` | 补充 M1-M4 执行命令、时间、结果 |
| `docs/development_audit_acceptance_closure_review.md` | 最终验收审核报告 |

## 10. 执行顺序

建议严格按顺序：

1. 修复无哈希旧 manifest 复用漏洞。
2. 更新相关测试并跑 targeted tests。
3. 清理 active 旧候选产物。
4. 跑数据审计确认 `FAIL=0`。
5. 使用 `--force` 执行候选 v2 完整复验。
6. 检查 `runs.csv` 年份覆盖和 manifest 哈希字段。
7. 重新生成 `go_nogo_decision.md`。
8. 跑最终回归命令。
9. 写最终验收审核报告。

## 11. 最终判定规则

工程验收 GO 必须同时满足：

```text
pytest: PASS
2017-2024 audit: FAIL=0
2026 YTD audit: FAIL=0
candidate_v2 runs.csv: 8 validation + 1 ytd
candidate run manifests: all hashes non-empty
go_nogo_decision.md: regenerated, complete, not INCOMPLETE
```

若任一项不满足：

```text
工程验收：NO-GO
```

策略是否 GO 不在本方案中预设，必须以重新生成的 `docs/go_nogo_decision.md` 为准。

# 遗留问题整改完成后审核验证报告

生成日期：2026-06-12  
审核对象：`docs/development_audit_followup_fix_plan.md` 对应整改交付  
审核结论：**不通过正式验收；M1/M2/M4/M5 有实质进展，但候选 v2 完整复验未执行，旧产物仍处于 active 路径，旧 run 复用保护仍不满足正式验收目标。**

## 1. 本轮审核范围

本轮审核验证以下内容：

1. 数据审计是否从 P0 FAIL 修复到可进入正式验证。
2. 测试套件是否通过。
3. 冻结验证脚本是否真正阻断旧 run 误复用。
4. 候选 v2 是否完成 2017-2024 validation + 2026 ytd 完整复验。
5. `candidate_v2_validation.md` 与 `go_nogo_decision.md` 是否已由完整产物重新生成。

## 2. 总体结论

| 项目 | 结果 | 说明 |
|---|---|---|
| 单元测试 | 通过 | `570 passed, 8 warnings` |
| 2017-2024 数据审计 | 关键通过 | `FAIL=0`，但 `adj_factor_coverage` 仍 WARN |
| 2026 YTD 数据审计 | 关键通过 | `FAIL=0`，但短样本因子覆盖 WARN |
| `adj_factor_dedup` | 通过 | 重复键已清零 |
| GO/NO-GO 输入完整性保护 | 通过 | 输入不完整时脚本拒绝生成 |
| 候选 v2 完整复验 | 不通过 | 当前 active `runs.csv` 仍只有 2023 一条 |
| 候选 v2 文档刷新 | 不通过 | `docs/candidate_v2_validation.md` 仍是旧 2023 单年内容 |
| GO/NO-GO 文档刷新 | 不通过 | `docs/go_nogo_decision.md` 仍是旧 `1/1` 内容 |
| 旧 run 复用保护 | 不通过 | `--reuse-existing` 仍允许无哈希旧 manifest 匹配 |
| 旧候选产物归档 | 不完全 | 归档副本存在，但 active 旧 `runs.csv` 仍留在默认读取路径 |

当前状态：

```text
工程整改：部分完成
正式验收：NO-GO
策略判定：等待完整复验后重新生成
```

## 3. 已验证通过项

### 3.1 测试套件通过

命令：

```powershell
python -X utf8 -m pytest -q
```

结果：

```text
570 passed, 8 warnings
```

判断：

- 新增测试文件已经纳入测试套件。
- warnings 与既有 pandas/cvxpy/统计常量输入相关，本轮不作为阻断项。

### 3.2 历史数据审计关键 FAIL 已清零

命令：

```powershell
python -X utf8 scripts\audit_cache.py --start 20170101 --end 20241231 --verbose
```

结果摘要：

```text
Total: 25 checks | PASS=24 | WARN=1 | FAIL=0
adj_factor_dedup PASS: 0 duplicates, 1702/1943 trade days (coverage=87.6%)
adj_factor_coverage WARN: adj_factor trade-day coverage=87.6% (1702/1943 days)
```

判断：

- 上一轮阻断正式验收的 `adj_factor_dedup FAIL` 已修复。
- 当前仍有 `adj_factor_coverage` WARN，低于完整交易日覆盖，但脚本判定为非 critical。
- 若后续策略结果异常，应优先复查这 12.4% 缺失交易日是否影响回测。

### 3.3 2026 YTD 数据审计关键 FAIL 为 0

命令：

```powershell
python -X utf8 scripts\audit_cache.py --start 20260101 --end 20260605 --verbose
```

结果摘要：

```text
Total: 25 checks | PASS=24 | WARN=1 | FAIL=0
factor_cs_quality WARN: 13 factors checked; 4 with <12 dates
adj_factor_dedup PASS
adj_factor_coverage PASS
```

判断：

- 2026 YTD 关键审计可进入观察口径。
- 短样本 WARN 符合 YTD 数据特点。

### 3.4 GO/NO-GO 生成脚本已能拒绝不完整输入

命令：

```powershell
python -X utf8 scripts\generate_go_nogo_decision.py
```

结果：

```text
ERROR: Cannot generate GO/NO-GO decision — data incomplete:
  - E_candidate_v2: missing validation years: [2017, 2018, 2019, 2020, 2021, 2022, 2024]
  - E_candidate_v2: missing ytd years: [2026]
```

判断：

- `scripts/generate_go_nogo_decision.py` 的完整性保护有效。
- 该脚本不会再基于当前缺失输入静默生成正式决策文档。

## 4. 未通过项

### 4.1 P1：候选 v2 完整冻结复验仍未执行

当前 active 文件：

```text
outputs/validation/candidate_v2/runs.csv
```

仍只有 1 条记录：

```text
year: 2023
sample: validation
strategy: E_candidate_v2
run_dir: outputs/runs/20230101_20231231_top50_20260611_192453
```

问题：

- 方案要求覆盖 `2017-2024 validation + 2026 ytd`。
- 当前缺少：
  - validation: 2017, 2018, 2019, 2020, 2021, 2022, 2024
  - ytd: 2026
- `docs/development_audit_followup_fix_log.md` 也明确写着 M3 为“运行待用户执行”。

结论：

```text
M3 未完成，候选 v2 完整复验不通过。
```

### 4.2 P1：旧候选验证产物仍留在 active 路径

观察：

```text
outputs/validation/candidate_v2/archive/runs_20260612_183901.csv
```

归档副本已存在，但：

```text
outputs/validation/candidate_v2/runs.csv
outputs/validation/candidate_v2/runs_partial.csv
```

仍留在 active 目录，且时间戳仍为 2026-06-11 23:22。

影响：

- 默认 `scripts/generate_go_nogo_decision.py` 会读取 `outputs/validation/candidate_v2/runs.csv`。
- 虽然新脚本会因输入不完整而失败，但 active 旧文件仍会干扰人工查看和后续自动流程。

整改要求：

- 在完整重跑前，active 旧 `runs.csv` 应删除、移动、或明确改名为 `INCOMPLETE/expired`。
- 完整重跑后再生成新的 active `runs.csv`。

### 4.3 P1：`candidate_v2_validation.md` 仍是旧单年文档

文件：

```text
docs/candidate_v2_validation.md
```

当前仍只包含：

```text
2023 validation E_candidate_v2
annualized_excess_return: 0.8%
```

问题：

- 文档时间戳仍是 2026-06-11 23:22。
- 没有 2017-2024 完整结果。
- 没有 2026 YTD 结果。

结论：

```text
候选 v2 验证报告未刷新，不可作为验收依据。
```

### 4.4 P1：`go_nogo_decision.md` 仍是旧决策文档

文件：

```text
docs/go_nogo_decision.md
```

当前仍显示：

```text
E_candidate_v2 Pos Years: 1/1
2026 YTD 前瞻观察为空
生成日期：2026-06-11 23:21
```

由于新版生成脚本已经拒绝不完整输入，说明该文档尚未重新生成。

结论：

```text
当前 GO/NO-GO 文档为过期产物，不可作为最终策略判定依据。
```

### 4.5 P1：旧 run 复用保护仍不满足正式验收目标

探针命令：

```powershell
python -X utf8 scripts\frozen_backtest_validation.py --strategies E_candidate_v2 --years 2023 --reuse-existing --out-dir outputs/validation/_audit_reuse_probe --out-doc docs/_audit_reuse_probe.md
```

结果：

```text
--reuse-existing: will reuse valid existing runs with matching config hashes.
  Reusing existing run: 20230101_20231231_top50_20260611_232212
```

被复用 run 的 manifest：

```text
factors_config_sha256:
regime_config_sha256:
factor_list_sha256:
factor_list: bp_cs, ep_cs, pv_divergence_20_cs, reversal_5_cs, sp_cs
```

问题：

- 旧 manifest 缺少哈希字段，仍被 `--reuse-existing` 接受。
- `scripts/frozen_backtest_validation.py` 中 `_manifest_matches` 只有在 manifest 哈希字段存在时才比对：

```text
if manifest_fc_hash and current_fc_hash and manifest_fc_hash != current_fc_hash:
    return False
```

- `tests/test_frozen_backtest_validation.py` 也明确包含“旧 manifest 无哈希仍允许匹配”的测试。

判断：

- 这满足向后兼容，但不满足正式验收的“配置内容哈希必须可追溯”目标。
- 在正式验收模式下，无哈希旧 run 应当拒绝复用。

整改要求：

1. 增加严格复用模式，正式验收默认开启。
2. `--reuse-existing` 在严格模式下必须要求以下字段非空且匹配：
   - `factors_config_sha256`
   - `regime_config_sha256`
   - `factor_list_sha256`
3. 如果保留旧 manifest 兼容，应只允许在显式 `--allow-legacy-manifest` 下使用。
4. 修改测试：无哈希 manifest 在正式复用模式下应返回 False。

### 4.6 P2：run manifest 哈希字段只对新 run 生效，旧 run 未回填

`run_research.py` 已新增：

```text
factors_config_sha256
regime_config_sha256
factor_list_sha256
```

但当前已存在的关键 run manifest 中这些字段为空，包括：

```text
outputs/runs/20260101_20260605_top50_20260612_002534/run_manifest.json
outputs/runs/20230101_20231231_top50_20260611_232212/run_manifest.json
outputs/runs/20230101_20231231_top50_20260611_192453/run_manifest.json
```

判断：

- 这是预期的历史产物问题，但必须通过强制重跑或显式回填解决。
- 对正式候选验证，推荐强制重跑，不建议回填旧 run 作为最终证据。

## 5. 验收判定

本轮判定：

```text
NO-GO
```

原因：

1. 候选 v2 完整复验未执行。
2. active `outputs/validation/candidate_v2/runs.csv` 仍为旧单年结果。
3. `docs/candidate_v2_validation.md` 和 `docs/go_nogo_decision.md` 仍是旧文档。
4. `--reuse-existing` 仍可能复用无哈希旧 manifest，不满足正式验收可追溯要求。

可以认可的进展：

1. `adj_factor_dedup` 已修复，历史窗口 `FAIL=0`。
2. 新增测试通过，测试数从 513 增至 570。
3. GO/NO-GO 生成脚本已经能拒绝不完整输入。
4. 默认冻结验证模式改为 fresh re-run，降低了误复用概率。

## 6. 下一步必须完成

### 6.1 修复严格复用逻辑

正式验收模式下，旧 manifest 缺少哈希字段必须视为不匹配。

建议新增参数：

```text
--allow-legacy-manifest
```

默认：

```text
allow_legacy_manifest = False
```

验收探针：

```powershell
python -X utf8 scripts\frozen_backtest_validation.py --strategies E_candidate_v2 --years 2023 --reuse-existing --out-dir outputs/validation/_audit_reuse_probe --out-doc docs/_audit_reuse_probe.md
```

预期：

```text
不得复用无哈希旧 run
```

### 6.2 清理 active 旧候选产物

处理以下文件：

```text
outputs/validation/candidate_v2/runs.csv
outputs/validation/candidate_v2/runs_partial.csv
docs/candidate_v2_validation.md
docs/go_nogo_decision.md
```

要求：

- 完整重跑前不得让旧 `runs.csv` 继续占据 active 路径。
- 旧文档应标记过期或等待完整重跑后覆盖生成。

### 6.3 执行候选 v2 完整冻结复验

命令：

```powershell
python -X utf8 scripts\frozen_backtest_validation.py --strategies E_candidate_v2 --out-dir outputs/validation/candidate_v2 --out-doc docs/candidate_v2_validation.md --force
```

必须生成：

```text
2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024 validation
2026 ytd
```

### 6.4 重新生成 GO/NO-GO 文档

命令：

```powershell
python -X utf8 scripts\generate_go_nogo_decision.py
```

预期：

- 不再报缺少年份。
- `E_candidate_v2` 不再显示 `1/1`。
- 2026 YTD 前瞻观察非空。

### 6.5 最终复验

最终验收命令：

```powershell
python -X utf8 -m pytest -q
python -X utf8 scripts\audit_cache.py --start 20170101 --end 20241231 --verbose
python -X utf8 scripts\audit_cache.py --start 20260101 --end 20260605 --verbose
python -X utf8 scripts\generate_go_nogo_decision.py
```

最终通过条件：

1. 测试通过。
2. 两个审计窗口 `FAIL=0`。
3. 候选 v2 `runs.csv` 覆盖完整年份。
4. 所有候选 run manifest 有非空哈希字段。
5. GO/NO-GO 文档由完整输入重新生成。

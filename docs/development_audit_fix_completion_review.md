# 开发方案完成后审核验证报告

生成日期：2026-06-12  
审核对象：`docs/development_audit_fix_plan.md` 所列整改完成后的当前项目状态  
审核结论：**不通过正式验收；代码测试通过，但数据审计、候选 v2 冻结复验和 GO/NO-GO 文档仍未闭环。**

## 1. 审核范围

本次审核只验证整改是否达到可验收状态，不继续调参，也不直接修复数据或策略代码。

重点检查：

1. 2017-2024 正式验证窗口缓存审计是否无 FAIL。
2. 候选 v2 的 `factors_candidate_v1 + regime_candidate_v2` 是否真实穿透到运行。
3. 候选 v2 是否完成 2017-2024 与 2026 YTD 的一键冻结复验。
4. `docs/candidate_v2_validation.md` 与 `docs/go_nogo_decision.md` 是否能追溯到完整 run 产物。
5. 测试套件是否通过。

## 2. 总体验收结论

| 项目 | 结果 | 说明 |
|---|---|---|
| 单元测试 | 通过 | `513 passed, 8 warnings` |
| 2026 YTD 候选 v2 直跑配置穿透 | 通过 | 最新 manifest 中候选因子池为 5 个目标因子 |
| 2026 YTD 缓存关键审计 | 基本通过 | `FAIL=0`，但存在 `factor_cs_quality` WARN |
| 2017-2024 正式验证缓存审计 | 不通过 | `adj_factor_dedup` 仍 FAIL |
| 候选 v2 冻结复验 | 不通过 | 当前 `candidate_v2/runs.csv` 只有 2023 一条记录 |
| GO/NO-GO 决策文档 | 不通过 | 只汇总候选 v2 的 1 年结果，且未包含最新 2026 YTD v2 直跑结果 |
| 一键验证复用逻辑 | 有风险 | `skip-existing` 默认开启，manifest 匹配不校验配置内容哈希 |

当前状态可以表述为：

> 整改已有明显进展，代码层和候选 v2 直接运行口径已经改善；但正式验证数据仍有硬失败，候选复验产物不完整且存在复用旧 run 的风险，因此不能宣布开发方案验收通过。

## 3. 已通过项

### 3.1 测试套件通过

命令：

```powershell
python -X utf8 -m pytest -q
```

结果：

```text
513 passed, 8 warnings
```

判断：

- 代码层测试通过。
- warnings 包括 pandas `SettingWithCopyWarning`、cvxpy ECOS 未来弃用提示、常量输入相关统计警告；本轮不作为阻断项。

### 3.2 候选 v2 直接运行配置已穿透

复核命令：

```powershell
python -X utf8 run_research.py phase2 --start 20260101 --end 20260605 --top-n 50 --no-recompute --factors-config configs/factors_candidate_v1.yaml --strategy-mode regime --regime-config configs/regime_candidate_v2.yaml
```

最新 run：

```text
run_id: 20260101_20260605_top50_20260612_002534
```

最新 `outputs/latest_run_manifest.json` 显示：

```text
factor_list:
- bp_cs
- ep_cs
- pv_divergence_20_cs
- reversal_5_cs
- sp_cs
```

判断：

- 最新直跑不再使用 `momentum_60_cs`、`momentum_120_cs`、`reversal_20_cs`、`volatility_20_cs` 等旧弱因子。
- `configs/regime_candidate_v2.yaml` 当前 sleeve 因子池与候选因子池口径基本一致。

### 3.3 2026 YTD 数据关键审计无 FAIL

命令：

```powershell
python -X utf8 scripts\audit_cache.py --start 20260101 --end 20260605
```

结果摘要：

```text
Total: 12 checks | PASS=11 | WARN=1 | FAIL=0
factor_cs_quality WARN: 13 factors checked; 4 with <12 dates
```

判断：

- 2026 YTD 关键数据审计无 FAIL。
- 由于存在 WARN，脚本本次返回非 0，但输出明确为 critical checks PASS。

## 4. 未通过项

### 4.1 P0：2017-2024 正式验证缓存审计仍失败

命令：

```powershell
python -X utf8 scripts\audit_cache.py --start 20170101 --end 20241231
```

结果摘要：

```text
Total: 12 checks | PASS=11 | WARN=0 | FAIL=1
adj_factor_dedup FAIL: 3 duplicate (ts_code, trade_date) rows
```

判断：

- `docs/development_audit_fix_plan.md` 明确要求 2017-2024 正式验证窗口 `audit_cache` 无 FAIL。
- 当前仍存在 `adj_factor_dedup` FAIL，正式冻结验证的数据健康门槛没有通过。
- 在该问题修复前，不建议把 2017-2024 跨年结果作为最终验收依据。

补充诊断：

逐 parquet 文件读取 `data/parquet/adj_factor` 后，发现重复集中在：

```text
ts_code: 000001.SZ
trade_date: 20240115
adj_factor: 1.0
source: data/parquet/adj_factor/year=2024 下多个 parquet 片段与 data.parquet 共存
```

该诊断与 `audit_cache` 的失败方向一致，说明 `year=2024` 分区仍存在多片重复写入或旧片段残留。

### 4.2 P1：候选 v2 冻结复验不完整

当前文件：

```text
outputs/validation/candidate_v2/runs.csv
```

实际只有 1 条记录：

```text
year: 2023
sample: validation
strategy: E_candidate_v2
run_dir: outputs/runs/20230101_20231231_top50_20260611_192453
annualized_excess_return: 0.008218370343317346
information_ratio: 0.11674496110297837
go_nogo_overall: GO
```

问题：

- 计划要求默认验证集为 2017-2024，2026 为 YTD 前瞻观察。
- 当前候选 v2 只覆盖 2023，缺少 2017、2018、2019、2020、2021、2022、2024 和 2026。
- `docs/candidate_v2_validation.md` 也只展示 2023 一年，不能代表完整冻结复验。

### 4.3 P1：候选 v2 的 2023 验证产物疑似为旧配置产物

`outputs/validation/candidate_v2/runs.csv` 中 2023 run 为：

```text
outputs/runs/20230101_20231231_top50_20260611_192453
```

该 run 的 `run_manifest.json` 显示因子池为：

```text
bp_cs
ep_cs
momentum_120_cs
momentum_60_cs
pv_divergence_20_cs
reversal_20_cs
reversal_5_cs
sp_cs
volatility_20_cs
```

但当前修复后的 `configs/regime_candidate_v2.yaml` sleeve 只引用：

```text
reversal_5_cs
pv_divergence_20_cs
ep_cs
bp_cs
sp_cs
```

判断：

- 2023 候选验证记录使用了旧因子池口径，不是修复后候选 v2 的可信验收产物。
- 该条记录不应继续作为候选 v2 最终 GO/NO-GO 的证据。

### 4.4 P1：一键验证脚本存在旧 run 复用风险

文件：

```text
scripts/frozen_backtest_validation.py
```

当前逻辑：

- `E_candidate_v2` 已注册，这是进展。
- `--skip-existing` 默认值为 `True`。
- `_manifest_matches` 只检查：
  - `start`
  - `end`
  - `top_n`
  - `strategy_mode`
  - `factors_config` 路径
  - `regime_config` 路径

缺口：

- 不校验配置文件内容哈希。
- 不校验实际 `factor_list` 是否等于当前候选配置所需因子池。
- 配置文件修改后，只要路径不变，旧 run 仍可能被视为可复用。

影响：

- 候选 v2 的验证结果可能混入修复前 run。
- 自动生成文档会继续把旧结果当作当前候选结果。

### 4.5 P1：GO/NO-GO 文档不具备最终验收可信度

文件：

```text
docs/go_nogo_decision.md
```

当前内容显示：

```text
E_candidate_v2: 0.8% annualized excess
Pos Years: 1/1
```

问题：

- 候选 v2 只汇总了 2023 一年，不是 2017-2024 完整验证。
- 2026 YTD 前瞻观察章节为空。
- 最新候选 v2 2026 YTD 直跑结果没有写入。

最新 2026 YTD 直跑结果为：

```text
run_id: 20260101_20260605_top50_20260612_002534
annualized_return: -15.27%
annualized_excess_return: -18.07%
information_ratio: -1.679
max_drawdown: -6.55%
status: NO-GO / UNSTABLE
```

判断：

- 当前 `go_nogo_decision.md` 是自动生成，但输入数据不完整。
- 自动生成不等于可信，必须先保证 `runs.csv` 覆盖完整且 run 口径正确。

## 5. 其他观察

### 5.1 当前目录不是 Git 仓库

命令：

```powershell
git status --short
```

结果：

```text
fatal: not a git repository (or any of the parent directories): .git
```

影响：

- 本轮无法用 `git diff` 精确核验开发改动边界。
- 审核只能基于当前文件状态、脚本逻辑和运行产物。

### 5.2 旧文档与当前状态存在错位

`docs/development_completion_audit.md` 的早期结论指出：

- 缓存审计失败。
- 因子清理未穿透到 regime sleeve。
- 候选 v2 未纳入一键验证脚本。

本轮复核后状态更新为：

- 因子清理直接运行口径已穿透。
- 候选 v2 已注册进验证脚本。
- 但缓存审计仍失败，候选冻结复验仍不完整，且旧 run 复用风险仍在。

## 6. 建议整改顺序

### 6.1 先修复 P0 数据审计

目标：

```text
python -X utf8 scripts\audit_cache.py --start 20170101 --end 20241231
```

必须达到：

```text
FAIL=0
```

建议动作：

1. 清理 `data/parquet/adj_factor/year=2024` 中多余碎片或重建整个 `adj_factor` 缓存。
2. 修复后重复运行 2017-2024 审计。
3. 保存修复命令和审计输出到文档，避免只保留口头结论。

### 6.2 修复冻结验证复用逻辑

建议至少完成一项：

1. 给 run manifest 写入 `factors_config_hash` 与 `regime_config_hash`，并在 `_manifest_matches` 中校验。
2. 给 `frozen_backtest_validation.py` 增加明确的 `--no-skip-existing` 或 `--force` 开关。
3. 对候选策略额外校验 manifest 中实际 `factor_list` 与当前配置解析结果一致。

验收标准：

- 修改配置内容后，旧 run 不会被误判为可复用。
- 候选 v2 的复验不会混入修复前结果。

### 6.3 重新跑候选 v2 完整冻结复验

建议在 P0 数据审计通过后执行：

```powershell
python -X utf8 scripts\frozen_backtest_validation.py --strategies E_candidate_v2 --out-dir outputs/validation/candidate_v2 --out-doc docs/candidate_v2_validation.md
```

必须覆盖：

```text
2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2026
```

验收标准：

- `outputs/validation/candidate_v2/runs.csv` 至少包含 9 条 `E_candidate_v2` 记录。
- 2017-2024 的 `sample` 为 validation。
- 2026 的 `sample` 为 ytd。
- 每条记录的 run manifest 均能证明使用修复后的配置内容或配置哈希。

### 6.4 重新生成 GO/NO-GO 文档

命令：

```powershell
python -X utf8 scripts\generate_go_nogo_decision.py
```

验收标准：

- `docs/go_nogo_decision.md` 中 `E_candidate_v2` 不再是 `1/1`。
- 2026 YTD 章节包含最新候选 v2 结果。
- 文档结论与 `runs.csv`、run manifest、latest metrics 一致。

## 7. 最终判定

本轮审核判定为：

```text
NO-GO
```

原因：

1. 2017-2024 正式验证缓存审计仍有 `adj_factor_dedup` FAIL。
2. 候选 v2 冻结复验只覆盖 2023，未完成完整验证窗口。
3. 现有 2023 候选验证 run 仍包含旧弱因子，不能代表修复后配置。
4. 一键验证默认复用旧 run，且不校验配置内容哈希。
5. GO/NO-GO 文档由不完整输入生成，未包含最新 2026 YTD 候选 v2 结果。

可以进入下一轮整改，但不应宣布当前开发方案正式验收通过。

# 开发方案完成度审核报告

生成日期：2026-06-11  
审核对象：`strategy_next_development_plan.md` 后续开发交付  
审核结论：**不通过正式验收；允许保留研究结论，需修复数据审计和候选验证链路后再复验。**

## 1. 审核摘要

本轮交付完成了计划中要求的大部分文档和候选配置，并且代码单元测试可复现通过。候选 `regime_candidate_v2 + factors_candidate_v1` 的 NO-GO 方向基本成立：2017-2024 平均年化超额仍为负，正超额年份不足，不能作为生产候选。

但正式验收存在三个硬问题：

1. 2017-2024 正式验证窗口的缓存审计失败。
2. `factors_candidate_v1` 的因子清理没有真正穿透到 `regime_candidate_v2` 的 sleeve 因子池。
3. `frozen_backtest_validation.py` 仍只覆盖 A/B/C/D 旧策略，未纳入候选 v2，候选验证尚不能一键复现。

因此当前状态应定义为：

> 开发分析交付基本完成，候选 v2 研究结论可信度中等；但验证链路未闭环，不能宣布开发方案正式验收通过。

## 2. 已验证通过项

### 2.1 文档交付

以下计划文档均已创建：

| 文档 | 状态 |
|---|---|
| `docs/failure_year_monthly_attribution.md` | 已存在 |
| `docs/factor_signal_alignment.md` | 已存在 |
| `docs/fast_vs_phase2_gap.md` | 已存在 |
| `docs/candidate_freeze_log.md` | 已存在 |
| `docs/go_nogo_decision.md` | 已存在 |
| `docs/frozen_backtest_validation.md` | 已刷新 |
| `docs/frozen_backtest_attribution.md` | 已刷新 |

### 2.2 候选配置交付

以下候选配置已创建：

| 配置 | 状态 |
|---|---|
| `configs/factors_candidate_v1.yaml` | 已存在 |
| `configs/regime_candidate_v1.yaml` | 已存在 |
| `configs/regime_candidate_v2.yaml` | 已存在 |
| `configs/regime_candidate_v3.yaml` | 已存在 |

### 2.3 测试套件

命令：

```powershell
pytest -q
```

结果：

```text
480 passed, 8 warnings
```

判断：代码层单元测试通过。warnings 主要为 pandas `SettingWithCopyWarning`、cvxpy ECOS 未来弃用提示、常量输入相关统计警告；暂不构成阻塞。

### 2.4 环境检查

命令：

```powershell
python scripts/check_env.py
```

结果：

```text
Verdict: WARN
System memory: 3.9GB available / 15.7GB total
```

判断：功能可用，但内存低于 4GB 推荐阈值。适合跑测试、缓存审计和短窗口；不建议直接跑多年全量重建。

### 2.5 legacy factor dry-run

命令：

```powershell
python scripts/migrate_factor_cache.py --dry-run
```

结果：

```text
0 files would be removed across 27 factors
```

判断：legacy factor coexistence 风险未复现。

## 3. 候选 v2 结果复核

候选：

- factors config：`configs/factors_candidate_v1.yaml`
- regime config：`configs/regime_candidate_v2.yaml`

已找到 2017-2024 共 8 条候选 v2 回测记录，且均有 phase2 metrics。

复核结果：

| 年份 | 年化收益 | 年化超额 | IR | 最大回撤 | 状态 |
|---:|---:|---:|---:|---:|---|
| 2017 | 1.98% | -16.84% | -2.22 | -7.96% | GO |
| 2018 | -35.32% | -9.48% | -0.58 | -33.92% | GO |
| 2019 | 16.46% | -14.87% | -2.11 | -16.87% | GO |
| 2020 | 9.06% | -13.67% | -0.95 | -23.18% | GO |
| 2021 | -16.95% | -9.03% | -0.72 | -27.28% | GO |
| 2022 | -13.42% | 8.69% | 0.70 | -21.36% | GO |
| 2023 | -14.39% | 0.82% | 0.12 | -19.28% | GO |
| 2024 | 29.36% | 6.05% | 0.43 | -12.46% | GO |

聚合复核：

| 指标 | 复核值 | 文档值 | 判断 |
|---|---:|---:|---|
| 平均年化超额 | -6.04% | -6.04% | 一致 |
| 中位数年化超额 | -9.25% | -9.27% | 基本一致 |
| 正超额年份 | 3/8 | 3/8 | 一致 |
| 平均 IR | -0.67 | -0.58 | 不一致，需修正文档 |
| 最差单年超额 | -16.84% | -16.8% | 一致 |

判断：`go_nogo_decision.md` 的 NO-GO 结论成立，但平均 IR 数字需要修正。

### 3.1 补充 2026 YTD 审核

原交付中未找到候选 v2 的 2026 YTD 记录。本次审核补跑：

```powershell
python -X utf8 run_research.py phase2 --start 20260101 --end 20260605 --top-n 50 --no-recompute --factors-config configs/factors_candidate_v1.yaml --strategy-mode regime --regime-config configs/regime_candidate_v2.yaml
```

结果：

| 指标 | 值 |
|---|---:|
| 年化收益 | 4.20% |
| 年化超额 | 4.58% |
| IR | 0.253 |
| 最大回撤 | -14.23% |
| 平均换手 | 41.64% |
| 样本数 | 20 周 |
| 状态 | NO-GO / UNSTABLE |

判断：2026 YTD 为正，但样本不足，仍只能作为观察项，不能作为上线证据。

## 4. 未通过项

### 4.1 P0：2017-2024 缓存审计失败

命令：

```powershell
python scripts/audit_cache.py --start 20170101 --end 20241231
```

结果：

```text
Total: 12 checks | PASS=9 | WARN=0 | FAIL=3
```

失败项：

| 检查 | 状态 | 摘要 |
|---|---|---|
| `adj_factor_dedup` | FAIL | 447 duplicate `(ts_code, trade_date)` rows |
| `adj_factor_coverage` | FAIL | adj_factor trade-day coverage=1.2% (23/1943 days) |
| `prices_adj_jumps` | FAIL | 6 extreme daily returns >5x, 8 extreme weekly returns >10x |

影响：

- 这是正式验证窗口的基础数据健康检查失败。
- 即使 Phase2 能跑出结果，也不能把当前 2017-2024 结果定义为完全验收通过。
- `go_nogo_decision.md` 中 “PIT 审计 ✅ / 验证链路 ✅” 的表述需要降级。

建议修复：

1. 先定位重复 `adj_factor` 所在年份、股票和分区。
2. 对 `adj_factor` 执行去重或重建，确保 `(ts_code, trade_date)` 唯一。
3. 复核 `prices_adj_jumps` 的 6 个日跳变和 8 个周跳变，是数据真实极端波动还是复权污染。
4. 修复后重跑：

```powershell
python scripts/audit_cache.py --start 20170101 --end 20241231
```

验收要求：FAIL=0。

### 4.2 P1：候选因子清理未穿透到 regime sleeve

`configs/factors_candidate_v1.yaml` 的 `enabled_factors` 只包含：

```yaml
ep_cs
bp_cs
sp_cs
reversal_5_cs
pv_divergence_20_cs
```

同时将以下因子标记为 disabled：

```yaml
reversal_20_cs
volatility_20_cs
momentum_60_cs
momentum_120_cs
```

但 `configs/regime_candidate_v2.yaml` 仍在 sleeve 中直接引用这些因子：

| 文件位置 | 问题 |
|---|---|
| `configs/regime_candidate_v2.yaml:42` | `reversal_20_cs` 仍在 reversal sleeve |
| `configs/regime_candidate_v2.yaml:47` | `momentum_60_cs` 仍在 momentum sleeve |
| `configs/regime_candidate_v2.yaml:48` | `momentum_120_cs` 仍在 momentum sleeve |
| `configs/regime_candidate_v2.yaml:53` | `volatility_20_cs` 仍在 defensive sleeve |
| `configs/regime_candidate_v2.yaml:64` | `volatility_20_cs` 仍在 volume_price sleeve |

实际运行日志也确认：

```text
Regime factor pool: 9 total declared, 9 cached, 0 missing
```

实际 `factor_list` 为：

```text
bp_cs, ep_cs, momentum_120_cs, momentum_60_cs, pv_divergence_20_cs,
reversal_20_cs, reversal_5_cs, sp_cs, volatility_20_cs
```

影响：

- v2 的结果不是“清理后 5 因子池”的结果，而是 regime config 直接声明的 9 因子 sleeve 结果。
- 文档中关于 `factors_candidate_v1` 已清理弱因子的部分需要补充说明：在 regime mode 下，sleeve 配置会重新引入因子。

建议修复：

1. 明确运行逻辑：regime mode 的因子池以 `strategy_sleeves.*.factors` 为准，还是受 `enabled_factors` 约束。
2. 若目标是真清理因子池，应从 `regime_candidate_v2.yaml` 中移除 disabled 因子。
3. 若目标是保留这些因子用于 sleeve 归因，则需要修正文档，不要称其为“已移除弱因子”。
4. 增加测试或脚本检查：候选 factors config 的 `disabled_factors` 不应出现在候选 regime config 的 sleeve 中，除非显式允许。

### 4.3 P1：候选 v2 未纳入一键冻结验证脚本

`scripts/frozen_backtest_validation.py` 当前 `STRATEGIES` 只包含：

- `A_5reversal`
- `B_dynamic`
- `C_regime_baseline`
- `D_regime_overlay`

候选 `regime_candidate_v2 + factors_candidate_v1` 未在该脚本中注册。

影响：

- `docs/go_nogo_decision.md` 的候选 v2 结果来自已有单年 run，而不是统一候选验证脚本产物。
- 计划中“冻结候选后一键复验”的链路尚未完成。

建议修复：

1. 在 `frozen_backtest_validation.py` 中增加候选策略：

```python
"E_candidate_v2": Strategy(
    name="E_candidate_v2",
    label="candidate_v2 factors_candidate_v1 + regime_candidate_v2",
    args=(
        "--factors-config",
        "configs/factors_candidate_v1.yaml",
        "--strategy-mode",
        "regime",
        "--regime-config",
        "configs/regime_candidate_v2.yaml",
    ),
)
```

2. 或新增独立脚本 `scripts/candidate_backtest_validation.py`。
3. 重新生成候选级别的 `runs.csv` 和报告，避免手工拼接。

### 4.4 P1：`outputs/validation_report.md` 仍是旧 FAIL

当前 `outputs/validation_report.md` 为：

```text
Generated: 2026-06-05 15:38
Overall: FAIL
audit_cache: FAIL
```

影响：

- 该文件与新文档中的“验证链路已完成”冲突。
- 后续读者如果只看 `validation_report.md`，会认为全流程仍失败。

建议：

1. 如果 validate 当前确实还不能跑通，则在 `go_nogo_decision.md` 明确写出该文件仍是旧 FAIL。
2. 如果应该代表最新状态，则必须重新运行 validate 并刷新它。
3. 在数据审计 FAIL 修复前，不建议把它改成 PASS。

### 4.5 P2：文档存在少量数字和口径不一致

发现：

- `docs/go_nogo_decision.md` 中 v2 平均 IR 写为 -0.58，复核为 -0.67。
- 候选 v2 原交付缺少 2026 YTD；本次审核已补跑，结果应补入文档。
- 部分文档中的 CSI300 年化收益与最新 run metrics 不完全一致，可能混用了不同策略窗口或不同 benchmark period。

建议：

- 用脚本从 run manifests 和 metrics 自动生成 GO/NO-GO 表，不手工维护关键指标。
- 指标表中增加 `run_id`，便于追溯。

## 5. 2026 YTD 缓存审计

命令：

```powershell
python scripts/audit_cache.py --start 20260101 --end 20260605
```

结果：

```text
Total: 12 checks | PASS=11 | WARN=1 | FAIL=0
```

唯一 WARN：

```text
factor_cs_quality: 13 factors checked; 4 with <12 dates
```

判断：

- 2026 YTD 的缓存健康基本可用。
- 但 2026 样本只有 20 周，指标仍为 `UNSTABLE`。

## 6. 最终验收结论

### 6.1 代码层

通过：

- 单元测试通过。
- 候选 v2 可运行。
- 2026 YTD 补跑成功。

### 6.2 数据层

不通过：

- 2017-2024 正式验证窗口 audit_cache 有 3 个 FAIL。
- 在修复前，不能把跨年验证声明为完全验收通过。

### 6.3 策略层

不通过生产：

- v2 平均年化超额仍为 -6.04%。
- 正超额年份只有 3/8。
- 平均 IR 为负。
- 2026 YTD 虽为正，但样本不足且仍为 NO-GO/UNSTABLE。

### 6.4 文档层

部分通过：

- 主文档和归因文档完整。
- 但需要修正候选因子池穿透、平均 IR、2026 YTD、旧 validation_report 等表述。

## 7. 建议的修复顺序

1. 修复 2017-2024 `audit_cache` FAIL。
2. 决定 regime candidate 是否必须遵守 `enabled_factors`。
3. 修正 `regime_candidate_v2.yaml` 或修正文档中的“因子清理”表述。
4. 将候选 v2 纳入一键冻结验证脚本。
5. 用脚本重建 `go_nogo_decision.md` 的指标表。
6. 刷新或明确废弃 `outputs/validation_report.md`。
7. 重新跑候选验证，生成最终验收报告。

## 8. 当前推荐判断

推荐接受以下结论：

- `regime_candidate_v2` 作为生产策略：**NO-GO**。
- `regime overlay` 方向作为研究路线：**保留，但暂停 allocator 层继续调参**。
- 下一步优先级：**先修数据审计和因子池穿透，再做因子池重建**。

不建议接受以下结论：

- “开发方案已全部验收通过”。
- “候选 v2 已完成一键冻结验证”。
- “factors_candidate_v1 的清理已经完全作用于实际 regime 回测”。

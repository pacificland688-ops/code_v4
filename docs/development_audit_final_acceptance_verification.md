# 最终执行闭环审核验证报告

生成日期：2026-06-13  
审核对象：`docs/development_audit_final_execution_fix_plan.md` 完成后的最终产物  
审核结论：**工程验收 GO；策略判定 NO-GO。**

## 1. 审核范围

本轮复核以下验收项：

1. `E_candidate_v2` 是否完成 2017-2024 validation + 2026 ytd 完整复验。
2. `runs.csv`、`candidate_v2_validation.md`、`go_nogo_decision.md` 是否重新生成。
3. 每个正式候选 run 的 manifest 是否具备配置哈希和因子池哈希。
4. 候选 run 是否排除旧弱因子。
5. 测试、数据审计和 GO/NO-GO 文档生成是否通过。

## 2. 总体结论

| 项目 | 结果 | 说明 |
|---|---|---|
| 候选 v2 完整复验 | 通过 | `8 validation + 1 ytd` |
| active `runs.csv` | 通过 | `outputs/validation/candidate_v2/runs.csv` 已生成 |
| 候选验证文档 | 通过 | `docs/candidate_v2_validation.md` 已生成 |
| GO/NO-GO 文档 | 通过 | `docs/go_nogo_decision.md` 已于 2026-06-13 09:40 重新生成 |
| manifest 哈希 | 通过 | 9 个 run 的配置哈希和因子池哈希均非空且匹配 |
| 旧弱因子排除 | 通过 | 9 个 run 均未包含旧弱因子 |
| 单元测试 | 通过 | `572 passed, 8 warnings` |
| 2017-2024 数据审计 | 关键通过 | `FAIL=0`，仍有 1 个可接受 WARN |
| 2026 YTD 数据审计 | 关键通过 | `FAIL=0`，仍有 1 个可接受 WARN |
| 策略门槛 | 不通过 | `E_candidate_v2` 未达到策略 GO 门槛 |

最终判定：

```text
工程验收：GO
策略判定：NO-GO
```

## 3. 候选 v2 复验覆盖

文件：

```text
outputs/validation/candidate_v2/runs.csv
```

覆盖结果：

| sample | count |
|---|---:|
| validation | 8 |
| ytd | 1 |

覆盖年份：

```text
2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2026
```

年度结果：

| year | sample | annualized_excess_return | information_ratio | go_nogo_overall |
|---:|---|---:|---:|---|
| 2017 | validation | -15.8% | -1.83 | GO |
| 2018 | validation | -3.1% | -0.19 | GO |
| 2019 | validation | -2.5% | -0.29 | GO |
| 2020 | validation | 8.6% | 0.66 | GO |
| 2021 | validation | 4.6% | 0.35 | GO |
| 2022 | validation | 7.2% | 0.50 | GO |
| 2023 | validation | -5.3% | -0.65 | GO |
| 2024 | validation | -3.3% | -0.25 | GO |
| 2026 | ytd | -18.1% | -1.68 | NO-GO |

说明：

- 表中的 `go_nogo_overall` 是单次 run 的数据/稳定性状态，不等同于策略最终门槛判定。
- 策略最终判定以 `docs/go_nogo_decision.md` 的跨年汇总为准。

## 4. manifest 哈希与因子池

复核方法：

- 逐条读取 `runs.csv` 的 `run_dir/run_manifest.json`。
- 重新计算当前 `factors_config` 与 `regime_config` 的 SHA256。
- 重新计算 `factor_list_sha256`。
- 检查旧弱因子是否出现在 `factor_list`。

结果：

```text
MANIFEST_CHECK_PASS
```

全部 9 个 run 均满足：

```text
factors_config_sha256: non-empty and matches current file
regime_config_sha256: non-empty and matches current file
factor_list_sha256: non-empty and matches manifest factor_list
```

全部 9 个 run 的因子池为：

```text
bp_cs
ep_cs
pv_divergence_20_cs
reversal_5_cs
sp_cs
```

以下旧弱因子均未出现：

```text
momentum_120_cs
momentum_60_cs
reversal_20_cs
volatility_20_cs
```

## 5. 文档生成验证

### 5.1 候选验证文档

文件：

```text
docs/candidate_v2_validation.md
```

状态：

- 已生成。
- 包含 2017-2024 validation 与 2026 ytd。
- 不再是旧的 2023 单年文档。

### 5.2 GO/NO-GO 决策文档

命令：

```powershell
python -X utf8 scripts\generate_go_nogo_decision.py
```

结果：

```text
Wrote D:\workspace\q_project\code_v4\docs\go_nogo_decision.md
```

文档状态：

```text
生成日期：2026-06-13 09:40
无 INCOMPLETE
无 1/1 误导性显示
E_candidate_v2 覆盖 2017-2024
2026 YTD 前瞻观察非空
```

## 6. 测试与数据审计

### 6.1 单元测试

命令：

```powershell
python -X utf8 -m pytest -q
```

结果：

```text
572 passed, 8 warnings
```

warnings 为既有可接受项：

- pandas `SettingWithCopyWarning`
- cvxpy ECOS deprecation warning
- 常量输入导致的 `spearmanr` 统计警告

### 6.2 2017-2024 数据审计

命令：

```powershell
python -X utf8 scripts\audit_cache.py --start 20170101 --end 20241231 --verbose
```

结果：

```text
Total: 26 checks | PASS=25 | WARN=1 | FAIL=0
```

WARN：

```text
adj_factor_coverage WARN: 87.6%
```

说明：

- 命令退出码为 1，原因是存在 WARN。
- 关键验收按 `FAIL=0` 判定通过。

### 6.3 2026 YTD 数据审计

命令：

```powershell
python -X utf8 scripts\audit_cache.py --start 20260101 --end 20260605 --verbose
```

结果：

```text
Total: 26 checks | PASS=25 | WARN=1 | FAIL=0
```

WARN：

```text
factor_cs_quality WARN: 4 factors with <12 dates
```

说明：

- 命令退出码为 1，原因是存在 WARN。
- YTD 短样本 WARN 可接受，关键验收按 `FAIL=0` 判定通过。

## 7. 策略判定

`docs/go_nogo_decision.md` 中 `E_candidate_v2` 的完整验证汇总：

| 指标 | 门槛 | 实际值 | 结果 |
|---|---:|---:|---|
| 平均年化超额 | > 2% | -1.2% | 不通过 |
| 中位数年化超额 | > 0% | -2.8% | 不通过 |
| 正超额年份 | >= 5 | 3/8 | 不通过 |
| 平均 IR | > 0.30 | -0.21 | 不通过 |
| 最大单年超额亏损 | > -10% | -15.8% | 不通过 |

2026 YTD 前瞻观察：

```text
年化超额：-18.1%
IR：-1.68
状态：NO-GO / UNSTABLE
```

策略最终判定：

```text
E_candidate_v2: NO-GO
```

## 8. 最终验收结论

工程验收条件：

| 条件 | 状态 |
|---|---|
| pytest 全部通过 | 通过 |
| 2017-2024 audit `FAIL=0` | 通过 |
| 2026 YTD audit `FAIL=0` | 通过 |
| candidate_v2 `runs.csv`: 8 validation + 1 ytd | 通过 |
| candidate run manifests: all hashes non-empty and matching | 通过 |
| candidate run manifests: no old weak factors | 通过 |
| `go_nogo_decision.md`: generated, not INCOMPLETE | 通过 |

结论：

```text
工程验收：GO
策略判定：NO-GO
```

后续建议：

1. 保留 `E_candidate_v2` 作为诊断候选，不升级为生产候选。
2. 不使用 2026 YTD 反向调参。
3. 若继续优化，应另立新方案，重新定义候选、验证窗口和 GO/NO-GO 门槛。

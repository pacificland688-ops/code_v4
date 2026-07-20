# Strategy V3 完成情况审核验证报告

生成日期：2026-06-13  
审核对象：`docs/strategy_v3_development_plan.md` 中定义的 `F_candidate_v3` 开发交付  
审核结论：工程主链路有条件通过，策略表现维持 NO-GO，不建议进入实盘。

## 1. 审核结论

### 1.1 总体判定

| 维度 | 判定 | 说明 |
|------|------|------|
| V3 策略注册 | 通过 | `F_candidate_v3` 已注册到冻结回测脚本，使用 `configs/factors_candidate_v1.yaml` 与 `configs/regime_candidate_v3.yaml` |
| 冻结回测覆盖 | 通过 | `outputs/validation/candidate_v3/runs.csv` 覆盖 2017-2024 验证年与 2026 YTD |
| Manifest 可追溯性 | 通过 | 9 个 run 的配置哈希与当前配置文件一致，因子池固定为 5 个目标因子 |
| GO/NO-GO 生成链路 | 通过 | 已重新生成 `docs/go_nogo_decision.md`，文档包含 `F_candidate_v3` |
| 测试回归 | 通过 | `pytest` 全量通过 |
| 缓存审计 | 有告警通过 | 2017-2024 与 2026 YTD 均无 FAIL，但各有 1 个 WARN |
| 开发方案交付完整性 | 部分通过 | 主产物存在，但缺少方案中列出的 `candidate_v3_vs_v2_comparison.md` 与 `strategy_v3_development_log.md` |
| 策略实盘准入 | 不通过 | `F_candidate_v3` 未达到正式 GO 门槛，仍为 NO-GO |

### 1.2 最重要结论

`F_candidate_v3` 相对 `E_candidate_v2` 有边际改善，但改善幅度不足以改变策略决策：

- 2017-2024 平均年化超额：`-0.3%`，低于 `> 2%` 门槛。
- 中位数年化超额：`-1.2%`，低于 `> 0%` 门槛。
- 正超额年份：`4/8`，低于 `>= 5/8` 门槛。
- 平均 IR：`-0.11`，低于 `> 0.30` 门槛。
- 最大单年超额亏损：`-15.0%`，低于 `> -10%` 门槛。

因此，本轮 V3 只能判定为“候选路线有轻微改善”，不能判定为“可实盘策略”。

## 2. 验证命令与结果

### 2.1 全量测试

命令：

```powershell
python -X utf8 -m pytest -q
```

结果：

```text
621 passed, 18 warnings in 154.42s
```

说明：

- 测试全部通过。
- 警告主要来自 pandas 行为变更、SettingWithCopyWarning、cvxpy ECOS 未来弃用提示、常量相关性提示。
- 未发现因 V3 接入导致的工程回归失败。

### 2.2 2017-2024 缓存审计

命令：

```powershell
python -X utf8 scripts\audit_cache.py --start 20170101 --end 20241231 --verbose
```

结果摘要：

```text
Total: 26 checks | PASS=25 | WARN=1 | FAIL=0
All critical checks PASS. Warnings may affect backtest quality.
```

告警项：

```text
adj_factor_coverage WARN
adj_factor trade-day coverage=87.6% (1702/1943 days)
```

说明：

- 无关键失败，满足继续使用冻结回测结果的基本条件。
- `adj_factor` 覆盖率不足 90%，可能影响复权价质量，需要作为回测质量风险留档。

### 2.3 2026 YTD 缓存审计

命令：

```powershell
python -X utf8 scripts\audit_cache.py --start 20260101 --end 20260605 --verbose
```

结果摘要：

```text
Total: 26 checks | PASS=25 | WARN=1 | FAIL=0
All critical checks PASS. Warnings may affect backtest quality.
```

告警项：

```text
factor_cs_quality WARN
14 factors checked; 4 with <12 dates
```

说明：

- 2026 YTD 样本本身较短，基本面类月度因子日期数少属于预期风险。
- 2026 YTD 只能用于前瞻观察，不应纳入调参依据。

### 2.4 GO/NO-GO 文档重生成

命令：

```powershell
python -X utf8 scripts\generate_go_nogo_decision.py --runs outputs\validation\frozen_backtest\runs.csv outputs\validation\candidate_v2\runs.csv outputs\validation\candidate_v3\runs.csv
```

结果：

```text
Wrote D:\workspace\q_project\code_v4\docs\go_nogo_decision.md
```

说明：

- 生成脚本执行成功。
- 重新生成后的 `docs/go_nogo_decision.md` 包含 `F_candidate_v3`。
- `F_candidate_v3` 判定仍为 `NO-GO`。

## 3. 交付物核对

### 3.1 已存在且通过核对的产物

| 产物 | 状态 | 说明 |
|------|------|------|
| `docs/strategy_v3_development_plan.md` | 存在 | V3 开发方案文档 |
| `outputs/validation/candidate_v3/runs.csv` | 存在 | 9 条 `F_candidate_v3` 记录 |
| `outputs/validation/candidate_v3/runs_partial.csv` | 存在 | 中间结果记录 |
| `docs/candidate_v3_validation.md` | 存在 | V3 冻结回测验证文档 |
| `docs/go_nogo_decision.md` | 存在 | 已重新生成，包含 V3 |
| `configs/regime_candidate_v3.yaml` | 存在 | V3 regime 配置 |
| `configs/factors_candidate_v1.yaml` | 存在 | V2/V3 共用候选因子池 |
| `scripts/frozen_backtest_validation.py` | 已接入 | 包含 `F_candidate_v3` 策略定义 |
| `scripts/generate_go_nogo_decision.py` | 已接入 | 候选策略包含 `E_candidate_v2` 与 `F_candidate_v3` |

### 3.2 缺失产物

| 方案要求产物 | 当前状态 | 影响 |
|------|------|------|
| `docs/candidate_v3_vs_v2_comparison.md` | 不存在 | V3 vs V2 的正式对比没有独立落档 |
| `docs/strategy_v3_development_log.md` | 不存在 | 开发执行日志没有独立落档 |

这两个缺口不影响回测主结果复现，但影响开发闭环完整性。建议补齐，至少将本报告中的 V2/V3 对比表拆分为正式比较文档，并补一份开发日志记录关键命令、时间点和结论。

## 4. 冻结回测覆盖核对

`outputs/validation/candidate_v3/runs.csv` 核对结果：

```text
记录数：9
策略：F_candidate_v3
validation 年份：2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024
ytd 年份：2026
```

结论：

- 覆盖范围满足开发方案 M1 要求。
- 未发现缺少年份。
- 未发现混入其他策略记录。

## 5. Manifest 与因子池核对

### 5.1 配置哈希

当前配置文件哈希：

```text
configs/factors_candidate_v1.yaml:
950f02e3f5693c3ef75897b85b7842485a846389717e655d23b8f25bf50554df

configs/regime_candidate_v3.yaml:
d30f189662e093a18f9f767a9ba9d172eafc63f1ff9ae60bedbbc3ca3f1460ed
```

核对结果：

- 9 个 V3 run 的 `factors_config_sha256` 均与当前 `configs/factors_candidate_v1.yaml` 一致。
- 9 个 V3 run 的 `regime_config_sha256` 均与当前 `configs/regime_candidate_v3.yaml` 一致。
- 9 个 V3 run 的 `factor_list_sha256` 均非空。
- 未发现 manifest 缺失。

### 5.2 因子池

9 个 V3 run 的因子池均为：

```text
bp_cs
ep_cs
pv_divergence_20_cs
reversal_5_cs
sp_cs
```

结论：

- 因子池与开发方案一致。
- 未发现旧弱因子重新进入 V3。
- V3 的实际实现范围是“在 V2 候选因子池上增加 regime_candidate_v3 performance overlay”，不是完整的新 alpha 因子重建。

## 6. V3 策略表现复核

### 6.1 年度表现

| 年份 | 样本 | 年化收益 | 年化超额 | IR | 最大回撤 | 平均换手 | 判定 |
|------|------|------:|------:|------:|------:|------:|------|
| 2017 | validation | 3.7% | -15.0% | -1.74 | -9.3% | 36.6% | GO |
| 2018 | validation | -31.2% | -3.3% | -0.21 | -32.8% | 29.2% | GO |
| 2019 | validation | 35.8% | 1.0% | 0.12 | -13.8% | 34.8% | GO |
| 2020 | validation | 37.8% | 9.3% | 0.69 | -17.8% | 35.5% | GO |
| 2021 | validation | -7.5% | 5.8% | 0.45 | -18.9% | 35.7% | GO |
| 2022 | validation | -14.3% | 8.1% | 0.57 | -23.7% | 32.4% | GO |
| 2023 | validation | -18.9% | -4.4% | -0.50 | -23.9% | 20.0% | GO |
| 2024 | validation | 17.3% | -3.7% | -0.28 | -14.2% | 22.0% | GO |
| 2026 | ytd | -15.5% | -18.3% | -1.71 | -6.6% | 40.2% | NO-GO |

注意：年度表里的 `go_nogo_overall` 是单次 run 数据质量和稳定性状态，不等同于策略整体准入判定。策略整体准入以 `docs/go_nogo_decision.md` 的跨年门槛为准。

### 6.2 跨年门槛

| 指标 | GO 门槛 | V3 实际 | 是否通过 |
|------|------:|------:|------|
| 平均年化超额 | > 2.0% | -0.3% | 未通过 |
| 中位数年化超额 | > 0.0% | -1.2% | 未通过 |
| 正超额年份 | >= 5/8 | 4/8 | 未通过 |
| 平均 IR | > 0.30 | -0.11 | 未通过 |
| 最大单年超额亏损 | > -10.0% | -15.0% | 未通过 |

结论：V3 未通过任何正式 GO 门槛，不能进入实盘。

## 7. V3 vs V2 对比

### 7.1 年度超额差异

| 年份 | E_candidate_v2 | F_candidate_v3 | V3 - V2 |
|------|------:|------:|------:|
| 2017 | -15.8% | -15.0% | +0.80pp |
| 2018 | -3.1% | -3.3% | -0.19pp |
| 2019 | -2.5% | 1.0% | +3.41pp |
| 2020 | 8.6% | 9.3% | +0.68pp |
| 2021 | 4.6% | 5.8% | +1.23pp |
| 2022 | 7.2% | 8.1% | +0.97pp |
| 2023 | -5.3% | -4.4% | +0.91pp |
| 2024 | -3.3% | -3.7% | -0.45pp |
| 2026 YTD | -18.1% | -18.3% | -0.24pp |

### 7.2 对比结论

- 2017-2024 验证窗口中，V3 相对 V2 在 `6/8` 年改善。
- V3 相对 V2 的平均年度超额改善约 `+0.92pp`。
- 正超额年份从 V2 的 `3/8` 提升到 V3 的 `4/8`。
- 但 V3 仍未达到正式门槛，且 2026 YTD 相对 V2 略差。

解释：

- `regime_candidate_v3` 的 performance overlay 对历史验证期有一定边际贡献。
- 贡献主要表现为多数年份小幅改善，而不是稳定把负超额年份扭转为正超额。
- 2017 的大幅负超额仍未解决，这是最大单年亏损门槛失败的核心来源。
- 2023、2024 仍为负超额，说明策略在近年环境中的稳定性不足。
- 2026 YTD 年化超额为 `-18.3%`，虽然样本不足，但方向上不能支持实盘推进。

## 8. 发现的问题与风险

### P1：策略仍不满足实盘 GO 门槛

V3 没有通过任何正式策略准入指标。即使相对 V2 有改善，也不能解释为策略已经可进入实盘。下一阶段应继续 alpha 重建和路由诊断，而不是在当前 V3 上直接推进交易。

### P1：开发方案交付文档不完整

方案中要求的以下文档不存在：

```text
docs/candidate_v3_vs_v2_comparison.md
docs/strategy_v3_development_log.md
```

这会影响后续复盘和责任链追踪。建议补齐后再将 V3 归档为完整开发闭环。

### P2：方案范围与更早的 alpha 重建方向存在偏差

本轮实际完成的是：

```text
factors_candidate_v1 + regime_candidate_v3 performance overlay
```

它不是完整的“扩展 Tushare 数据、开发质量/现金流/动量新因子、重建 alpha 池”的方案。若目标是解决全年不同周期不同趋势下的泛化问题，当前 V3 只是 overlay 试验，不足以承担完整优化目标。

### P2：缓存审计存在 WARN

2017-2024：

- `adj_factor_coverage` 为 `87.6%`，低于 90%。

2026 YTD：

- `factor_cs_quality` 提示 4 个因子少于 12 个日期。

这些不是阻断项，但应在报告中保留，避免后续将回测结果解释为无任何数据质量限制。

### P3：GO/NO-GO 汇总表字段名有轻微误导

`scripts/generate_go_nogo_decision.py` 中汇总表的 `Max DD` 实际使用的是 `avg_max_drawdown`，即各验证年最大回撤的平均值，不是所有年份中的最深回撤。建议后续将列名改为 `Avg Max DD`，或另加一列 `Worst Max DD`，避免阅读误解。

## 9. 审核建议

### 9.1 当前版本处理建议

1. 将 `F_candidate_v3` 标记为“已验证、NO-GO、可归档候选”。
2. 不进入实盘，不进入小资金试运行。
3. 不再基于 2026 YTD 做反向调参。
4. 补齐缺失文档：
   - `docs/candidate_v3_vs_v2_comparison.md`
   - `docs/strategy_v3_development_log.md`
5. 修正 GO/NO-GO 汇总表中 `Max DD` 的展示口径命名。

### 9.2 下一阶段优化方向

V3 的结果说明，单纯在现有 5 因子池上做 performance overlay 只能带来小幅改善，不能解决策略核心 alpha 弱的问题。下一阶段建议转向：

1. 重建 alpha 来源，而不是继续微调 overlay。
2. 扩展基本面、质量、现金流、盈利稳定性、估值修复、行业相对强弱等因子。
3. 对不同市场状态单独诊断：2017、2023、2024、2026 YTD 是重点失败样本。
4. 拆解 sleeve 层贡献，确认 value、reversal、volume_price 在不同 regime 下是否真的有正贡献。
5. 建立候选策略进入冻结验证前的预注册制度，避免 2026 YTD 或单一年份结果影响参数选择。

## 10. 最终判定

本次 V3 开发的核心工程链路已经完成并可复现，`F_candidate_v3` 的冻结验证、manifest、因子池、GO/NO-GO 生成链路均通过审核。

但是，开发方案的文档闭环不完整，且策略表现仍明显低于实盘准入标准。正式结论为：

```text
工程验收：有条件通过
策略准入：NO-GO
实盘建议：不进入实盘
后续方向：停止围绕当前 V3 做小幅调参，转向 alpha 重建与失败年份归因
```

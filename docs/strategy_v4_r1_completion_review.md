# Strategy V4-r1 完成情况审核验证报告

生成日期：2026-06-14  
审核对象：`docs/strategy_v4_acceptance_fix_development_plan.md`  
候选策略：`G_candidate_v4_r1`  
审核结论：**不通过验收**。V4-r1 已补齐正式冻结验证链路和 GO/NO-GO 生成链路，但数据质量、因子 gate、候选池合规性和策略表现均未达到验收要求。

## 1. 总体判定

| 维度 | 判定 | 说明 |
|------|------|------|
| 候选策略注册 | 通过 | `G_candidate_v4_r1` 已注册到冻结验证和 GO/NO-GO 脚本 |
| 完整冻结验证 | 通过 | `outputs/validation/candidate_v4_r1/runs.csv` 覆盖 2017-2024 + 2026 YTD |
| Manifest 可追溯性 | 通过 | 9 个正式 run 与当前 `factors_candidate_v4_r1.yaml`、`regime_candidate_v4_r1.yaml` 哈希一致 |
| GO/NO-GO 文档生成 | 通过 | `docs/go_nogo_decision.md` 已生成，且不含 `INCOMPLETE` |
| 全量测试 | 通过 | `718 passed, 20 warnings` |
| 缓存审计 | 不通过 | 2017-2024 与 2026 YTD 均存在 5 个 FAIL |
| V4 输入审计 | 不通过 | 31 个因子中 23 个 FAIL/BLOCKED |
| 因子质量 gate | 不通过 | `0 PASS`、`1 WATCH_NEUTRAL_ONLY`、`20 FAIL`、`28 DATA_MISSING` |
| 候选因子池合规 | 不通过 | `enabled_factors` 中没有 PASS 因子，且包含输入审计失败的 growth 因子 |
| 策略 GO/NO-GO | 不通过 | `G_candidate_v4_r1` 正式判决为 NO-GO |
| 文档闭环 | 不通过 | 多份修复方案要求的 V4-r1 文档缺失 |
| 实盘准入 | 不通过 | 不进入实盘，不进入小资金试运行 |

## 2. 已修复项

相对上一轮 V4 审核，以下链路已经补齐：

1. `G_candidate_v4_r1` 已注册。
2. `configs/factors_candidate_v4_r1.yaml` 存在。
3. `configs/regime_candidate_v4_r1.yaml` 存在。
4. `outputs/validation/candidate_v4_r1/runs.csv` 存在。
5. `docs/candidate_v4_r1_validation.md` 存在。
6. `outputs/validation/candidate_v4_r1_smoke/runs.csv` 存在。
7. 正式 `docs/go_nogo_decision.md` 已重新生成，不再是 INCOMPLETE。
8. 正式 run manifest 哈希与当前配置一致。

这些说明工程验证链路已经从“缺失正式 runs”推进到“可复现但结果不达标”。

## 3. 仍未通过的关键项

### 3.1 数据审计失败

2017-2024 缓存审计命令：

```powershell
python -X utf8 scripts\audit_cache.py --start 20170101 --end 20241231 --verbose
```

结果：

```text
Total: 38 checks | PASS=32 | WARN=1 | FAIL=5
```

失败项：

```text
factor_cs_quality              FAIL     26 factors checked; 4 with duplicates
factor:earnings_acceleration_cs FAIL     rows=6385, dates=468, dup=3705
factor:growth_stability_8q_cs  FAIL     rows=6385, dates=468, dup=3705
factor:profit_growth_ttm_cs    FAIL     rows=6935, dates=513, dup=4355
factor:revenue_growth_ttm_cs   FAIL     rows=6935, dates=513, dup=4355
```

2026 YTD 缓存审计命令：

```powershell
python -X utf8 scripts\audit_cache.py --start 20260101 --end 20260605 --verbose
```

结果：

```text
Total: 38 checks | PASS=33 | WARN=0 | FAIL=5
```

失败项：

```text
factor_cs_quality              FAIL     26 factors checked; 4 with duplicates; 12 with <12 dates
factor:earnings_acceleration_cs FAIL     rows=488, dates=41, dup=239
factor:growth_stability_8q_cs  FAIL     rows=488, dates=41, dup=239
factor:profit_growth_ttm_cs    FAIL     rows=488, dates=41, dup=239
factor:revenue_growth_ttm_cs   FAIL     rows=488, dates=41, dup=239
```

结论：当前数据缓存存在重复 `(ts_code, trade_date)`，违反冻结验证前置条件。即使策略结果可生成，也不能作为高可信验收结果。

### 3.2 V4 输入审计仍失败

命令：

```powershell
python -X utf8 scripts\audit_alpha_inputs_v4.py --start 20170101 --end 20241231 --out outputs\analysis\v4_alpha_inputs
```

结果：

```text
31 factors audited
PASS: 8
WARN: 0
FAIL: 23
BLOCKED: 23
```

主要失败类别：

| 类别 | 因子 | 失败原因 |
|------|------|------|
| 质量类 | `roe_stability_8q_cs`, `roa_ttm_cs`, `gross_margin_ttm_cs`, `net_margin_ttm_cs`, `profitability_quality_cs`, `asset_turnover_ttm_cs` | `empty_cache` |
| 现金流类 | `ocf_to_mktcap_cs`, `ocf_to_profit_cs`, `fcf_yield_cs`, `cashflow_stability_8q_cs`, `accrual_quality_cs`, `receivable_pressure_cs` | `empty_cache` |
| 成长类 | `revenue_growth_ttm_cs`, `profit_growth_ttm_cs`, `growth_stability_8q_cs`, `earnings_acceleration_cs` | `HIGH_DUPLICATE_RATE` |
| 复合类 | `growth_value_match_cs`, `valuation_reversion_3y_cs`, `quality_value_composite_cs`, `dividend_quality_cs`, `industry_relative_quality_cs`, `industry_relative_growth_cs`, `industry_relative_value_cs` | `empty_cache` |

结论：V4-r1 仍没有完成 alpha 输入修复。

### 3.3 因子质量 gate 未通过

`outputs/analysis/factor_quality_rebuild_v4/factor_quality_gate.csv` 汇总：

```text
DATA_MISSING: 28
FAIL: 20
WATCH_NEUTRAL_ONLY: 1
PASS: 0
```

唯一 WATCH 因子：

```text
volatility_60_cs: WATCH_NEUTRAL_ONLY
```

结论：没有任何因子正式通过 V4 quality gate。按修复方案要求，PASS 因子不足时应停止策略组装；当前继续形成 `factors_candidate_v4_r1.yaml` 不符合验收标准。

### 3.4 候选因子池不合规

`configs/factors_candidate_v4_r1.yaml` 当前 enabled factors：

```text
ep_cs
bp_cs
sp_cs
reversal_5_cs
pv_divergence_20_cs
revenue_growth_ttm_cs
profit_growth_ttm_cs
earnings_acceleration_cs
growth_stability_8q_cs
momentum_60_skip5_cs
momentum_120_skip20_cs
risk_adjusted_momentum_60_cs
volume_confirmed_momentum_cs
trend_quality_cs
industry_relative_ep_cs
industry_relative_bp_cs
industry_relative_momentum_60_cs
volatility_60_cs
log_market_cap_cs
```

这些因子的 gate 状态：

```text
ep_cs                          FAIL
bp_cs                          FAIL
sp_cs                          FAIL
reversal_5_cs                  FAIL
pv_divergence_20_cs            FAIL
revenue_growth_ttm_cs          DATA_MISSING / 输入审计重复键 FAIL
profit_growth_ttm_cs           DATA_MISSING / 输入审计重复键 FAIL
earnings_acceleration_cs       DATA_MISSING / 输入审计重复键 FAIL
growth_stability_8q_cs         DATA_MISSING / 输入审计重复键 FAIL
momentum_60_skip5_cs           FAIL
momentum_120_skip20_cs         FAIL
risk_adjusted_momentum_60_cs   FAIL
volume_confirmed_momentum_cs   FAIL
trend_quality_cs               FAIL
industry_relative_ep_cs        FAIL
industry_relative_bp_cs        FAIL
industry_relative_momentum_60_cs FAIL
volatility_60_cs               WATCH_NEUTRAL_ONLY
log_market_cap_cs              FAIL
```

结论：候选池没有任何 PASS 因子，且包含输入审计失败的 growth 因子。该候选池不能作为正式 alpha 重建成果。

## 4. V4-r1 冻结验证结果

`outputs/validation/candidate_v4_r1/runs.csv` 覆盖：

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

年度结果：

| 年份 | 样本 | 年化收益 | 年化超额 | IR | 最大回撤 | 平均换手 |
|------|------|------:|------:|------:|------:|------:|
| 2017 | validation | 5.3% | -13.7% | -2.16 | -8.0% | 32.5% |
| 2018 | validation | -37.1% | -12.3% | -0.95 | -35.4% | 24.3% |
| 2019 | validation | 12.9% | -18.1% | -2.37 | -18.8% | 21.6% |
| 2020 | validation | 47.6% | 16.4% | 1.07 | -15.5% | 24.5% |
| 2021 | validation | -9.5% | 1.4% | 0.10 | -27.1% | 33.1% |
| 2022 | validation | -20.3% | 0.2% | 0.01 | -27.7% | 13.1% |
| 2023 | validation | -6.7% | 9.5% | 1.06 | -18.2% | 10.6% |
| 2024 | validation | 27.6% | 5.1% | 0.38 | -13.5% | 10.8% |
| 2026 | ytd | -22.2% | -26.1% | -2.76 | -9.7% | 42.2% |

2017-2024 汇总：

```text
平均年化超额: -1.4%
中位数年化超额: 0.8%
正超额年份: 5/8
平均 IR: -0.36
最大单年超额亏损: -18.1%
```

正式 GO/NO-GO：

```text
判决: NO-GO
```

通过项：

- 中位数年化超额 > 0。
- 正超额年份达到 5/8。

未通过项：

- 平均年化超额仍为负。
- 平均 IR 为负。
- 最大单年超额亏损仍低于 -10% 门槛。

## 5. V4-r1 相对 V3

| 年份 | F_candidate_v3 | G_candidate_v4_r1 | r1 - v3 |
|------|------:|------:|------:|
| 2017 | -15.0% | -13.7% | +1.31pp |
| 2018 | -3.3% | -12.3% | -9.06pp |
| 2019 | 1.0% | -18.1% | -19.05pp |
| 2020 | 9.3% | 16.4% | +7.16pp |
| 2021 | 5.8% | 1.4% | -4.41pp |
| 2022 | 8.1% | 0.2% | -7.96pp |
| 2023 | -4.4% | 9.5% | +13.95pp |
| 2024 | -3.7% | 5.1% | +8.78pp |
| 2026 YTD | -18.3% | -26.1% | -7.83pp |

汇总：

```text
验证年胜出: 4/8
平均年度超额差异: -1.16pp
```

结论：V4-r1 改善了 2020、2023、2024，但显著恶化 2018、2019、2021、2022，整体弱于 V3。

## 6. Manifest 审核

正式 `candidate_v4_r1` 的 9 个 run：

```text
factors_config_path: configs/factors_candidate_v4_r1.yaml
regime_config_path: configs/regime_candidate_v4_r1.yaml
factors_config_sha256: 与当前配置一致
regime_config_sha256: 与当前配置一致
factor_list_sha256: 非空
```

manifest 结论：通过。

注意事项：

- 2017 run 的 factor_list 为 15 个因子。
- 2018-2024 run 的 factor_list 为 19 个因子。
- 2026 run 的 factor_list 为 11 个因子。

这种差异来自不同年份数据覆盖，不一定是 manifest 错误，但应在最终报告中解释。特别是 2026 YTD 的 V4 新技术因子大量缺失，会影响 YTD 可读性。

## 7. 文档缺口

修复方案要求的以下文档仍不存在：

```text
docs/candidate_v4_r1_vs_v3_comparison.md
docs/candidate_v4_r1_vs_v4_lite_comparison.md
docs/factors_candidate_v4_r1_selection.md
docs/sleeve_design_v4_r1.md
docs/strategy_v4_r1_freeze_spec.md
```

本报告已补齐：

```text
docs/strategy_v4_r1_completion_review.md
```

结论：文档闭环仍不完整。

## 8. 回归命令结果

### 8.1 全量测试

命令：

```powershell
python -X utf8 -m pytest -q
```

结果：

```text
718 passed, 20 warnings in 178.34s
```

### 8.2 缓存审计

2017-2024：

```text
Total: 38 checks | PASS=32 | WARN=1 | FAIL=5
```

2026 YTD：

```text
Total: 38 checks | PASS=33 | WARN=0 | FAIL=5
```

结论：不通过。growth 因子存在重复键。

### 8.3 输入审计

命令：

```powershell
python -X utf8 scripts\audit_alpha_inputs_v4.py --start 20170101 --end 20241231 --out outputs\analysis\v4_alpha_inputs
```

结果：

```text
PASS: 8
FAIL: 23
BLOCKED: 23
```

结论：不通过。

### 8.4 GO/NO-GO 生成

命令：

```powershell
python -X utf8 scripts\generate_go_nogo_decision.py --runs outputs\validation\frozen_backtest\runs.csv outputs\validation\candidate_v2\runs.csv outputs\validation\candidate_v3\runs.csv outputs\validation\candidate_v4_r1\runs.csv
```

结果：

```text
Wrote D:\workspace\q_project\code_v4\docs\go_nogo_decision.md
```

结论：生成成功，文档不含 INCOMPLETE，但 `G_candidate_v4_r1` 判决为 NO-GO。

## 9. 阻断问题

### P0：缓存审计 FAIL

以下因子存在重复键，必须先修复：

```text
revenue_growth_ttm_cs
profit_growth_ttm_cs
growth_stability_8q_cs
earnings_acceleration_cs
```

修复要求：

- 保证每个 `(ts_code, trade_date)` 唯一。
- 明确重复来源是季度公告重叠、月度展开重复，还是写缓存逻辑错误。
- 修复后重跑 `audit_cache.py`，必须 FAIL=0。

### P0：候选池违反 gate 规则

当前 `enabled_factors` 没有 PASS 因子。必须重新定义候选池规则：

- gate FAIL 因子不得直接进入正式 alpha 池。
- DATA_MISSING 或输入审计 FAIL 因子不得进入正式候选池。
- WATCH 因子只能作为风险/防御用途，不能作为 alpha 通过证据。

### P0：策略仍为 NO-GO

V4-r1 没有达到正式策略门槛，不能推进实盘。

### P1：Alpha 重建仍未达成

质量、现金流因子仍基本为空；成长因子有数据但重复键失败。当前版本更接近“部分 growth/technical 因子试验”，不是完整 Alpha 重建。

### P1：文档闭环不完整

缺少 V4-r1 选择说明、sleeve 设计、V3 对比、lite 对比、freeze spec。

## 10. 下一步建议

### 10.1 必须先修复数据

优先处理：

```text
revenue_growth_ttm_cs
profit_growth_ttm_cs
growth_stability_8q_cs
earnings_acceleration_cs
```

修复后必须跑：

```powershell
python -X utf8 scripts\audit_cache.py --start 20170101 --end 20241231 --verbose
python -X utf8 scripts\audit_cache.py --start 20260101 --end 20260605 --verbose
python -X utf8 scripts\audit_alpha_inputs_v4.py --start 20170101 --end 20241231 --out outputs\analysis\v4_alpha_inputs
```

硬性目标：

```text
audit_cache FAIL=0
audit_alpha_inputs_v4 中进入候选池的因子必须 PASS
```

### 10.2 重新跑 factor gate

修复数据后运行：

```powershell
python -X utf8 scripts\factor_quality_rebuild.py --config configs\factor_quality_rebuild_v4.yaml --out-dir outputs\analysis\factor_quality_rebuild_v4 --out-doc docs\factor_quality_rebuild_v4_report.md
```

如果 PASS 因子仍为 0，应停止策略组装。

### 10.3 重新构建候选池

候选池必须满足：

- 不含输入审计 FAIL 因子。
- 不含 DATA_MISSING 因子。
- 不含无人工说明的 gate FAIL 因子。
- WATCH 因子用途明确。

### 10.4 再考虑 V4-r2

若数据与 gate 修复后仍需要继续，应使用新候选名：

```text
G_candidate_v4_r2
```

不要覆盖当前 `G_candidate_v4_r1`，因为它已经有明确的 NO-GO 结果。

## 11. 最终判定

```text
工程链路：部分通过
正式冻结验证：通过
Manifest：通过
缓存审计：不通过
输入审计：不通过
因子 gate：不通过
策略表现：NO-GO
文档闭环：不完整
实盘建议：不进入实盘
```

正式结论：**V4-r1 不通过验收，应归档为 NO-GO 候选，下一步先修复 growth 因子重复键和候选池 gate 规则。**

# Strategy V4 完成情况审核验证报告

生成日期：2026-06-14  
审核对象：`docs/strategy_v4_alpha_rebuild_development_plan.md`  
审核结论：**不通过验收**。工程代码和测试基本通过，但 V4 方案定义的正式候选 `G_candidate_v4` 未完成全窗口冻结验证，正式 GO/NO-GO 决策不可生成，Alpha 重建目标也未达成。

## 1. 总体判定

| 维度 | 判定 | 说明 |
|------|------|------|
| V4 文件交付 | 部分通过 | 多数配置、脚本、测试、文档已存在，但缺少正式验证报告和 V4/V3 对比文档 |
| V3 缺口闭环 | 通过 | `candidate_v3_vs_v2_comparison.md` 与 `strategy_v3_development_log.md` 已补齐 |
| V4 策略注册 | 部分通过 | `G_candidate_v4` 与 `G_candidate_v4_lite` 均已注册 |
| 正式冻结验证 | 不通过 | `outputs/validation/candidate_v4/runs.csv` 不存在，只有 3 条 partial 记录 |
| Lite 诊断验证 | 通过但不可替代正式验收 | `G_candidate_v4_lite` 有 2017-2024 + 2026 YTD 完整结果，但不是方案定义的正式 V4 |
| Manifest 可追溯性 | 不通过 | `G_candidate_v4` partial/smoke manifest 与当前配置哈希不一致 |
| Alpha 输入审计 | 不通过 | 31 个 V4 因子中 23 个 FAIL/BLOCKED |
| 因子质量 gate | 不通过 | `0 PASS`、`1 WATCH_NEUTRAL_ONLY`、`20 FAIL`、`28 DATA_MISSING` |
| 全量测试 | 通过 | `718 passed, 20 warnings` |
| 缓存审计 | 有告警通过 | 2017-2024 与 2026 YTD 均无 FAIL，但各有 1 个 WARN |
| GO/NO-GO 正式生成 | 不通过 | 正式命令拒绝生成，原因是 `G_candidate_v4` 无完整 runs |
| 策略实盘准入 | 不通过 | 不具备实盘或小资金试运行条件 |

## 2. 关键结论

### 2.1 正式 V4 没有完成

方案定义的正式候选是：

```text
G_candidate_v4
configs/factors_candidate_v4.yaml
configs/regime_candidate_v4.yaml
outputs/validation/candidate_v4/runs.csv
docs/candidate_v4_validation.md
```

当前实际状态：

```text
outputs/validation/candidate_v4/runs.csv       不存在
docs/candidate_v4_validation.md                不存在
docs/candidate_v4_vs_v3_comparison.md          不存在
outputs/validation/candidate_v4/runs_partial.csv 仅 3 条记录：2017, 2018, 2019
```

因此，`G_candidate_v4` 没有完成 2017-2024 + 2026 YTD 的正式冻结验证，不能生成正式 GO/NO-GO 结论。

### 2.2 `G_candidate_v4_lite` 不能替代 `G_candidate_v4`

当前存在完整验证的是：

```text
outputs/validation/candidate_v4_lite/runs.csv
strategy = G_candidate_v4_lite
```

`G_candidate_v4_lite` 的定义是：

```text
V3 factors + V4 regime
```

它使用的是：

```text
configs/factors_candidate_v1.yaml
configs/regime_candidate_v4.yaml
```

这与方案定义的 V4 Alpha 重建不一致。它可以作为 regime 诊断或降级对照，但不能作为 `G_candidate_v4` 的正式验收结果。

### 2.3 Alpha 重建目标未达成

V4 方案的核心目标是扩展质量、现金流、成长、估值修复、行业相对强弱、风险调整动量等 alpha 因子，并筛出可进入候选池的稳定因子。

实际因子质量 gate 结果：

```text
PASS: 0
WATCH_NEUTRAL_ONLY: 1
FAIL: 20
DATA_MISSING: 28
```

V4 输入审计结果：

```text
31 factors audited
PASS: 8
FAIL: 23
BLOCKED: 23
```

主要缺口：

- 质量类因子大量为空。
- 现金流类因子大量为空。
- 成长类因子大量为空。
- 行业质量/成长/value 复合因子大量为空。
- 通过 gate 的正式 alpha 因子为 0。

因此，本轮不能判定为“Alpha 重建完成”。

## 3. 交付物核对

### 3.1 已存在产物

| 产物 | 状态 |
|------|------|
| `configs/factor_build_v4.yaml` | 存在 |
| `configs/factors_alpha_v4_universe.yaml` | 存在 |
| `configs/factor_quality_rebuild_v4.yaml` | 存在 |
| `configs/factors_candidate_v4.yaml` | 存在 |
| `configs/regime_candidate_v4.yaml` | 存在 |
| `scripts/audit_alpha_inputs_v4.py` | 存在 |
| `scripts/build_alpha_factors_v4.py` | 存在 |
| `tests/test_alpha_inputs_v4.py` | 存在 |
| `tests/test_alpha_factors_v4.py` | 存在 |
| `tests/test_regime_candidate_v4_config.py` | 存在 |
| `docs/v4_data_inventory.md` | 存在 |
| `docs/v4_pit_alignment_rules.md` | 存在 |
| `docs/alpha_factor_definitions_v4.md` | 存在 |
| `docs/failure_year_monthly_attribution_v4.md` | 存在 |
| `docs/strategy_failure_source_matrix_v4.md` | 存在 |
| `docs/alpha_rebuild_priority_list.md` | 存在 |
| `docs/factor_quality_rebuild_v4_report.md` | 存在 |
| `docs/factor_rejection_log_v4.md` | 存在 |
| `docs/sleeve_design_v4.md` | 存在 |
| `docs/strategy_v4_freeze_spec.md` | 存在 |
| `docs/strategy_v4_development_log.md` | 存在 |

### 3.2 缺失或不满足要求的产物

| 方案要求产物 | 当前状态 | 影响 |
|------|------|------|
| `outputs/validation/candidate_v4/runs.csv` | 不存在 | 无法做正式 V4 跨年验收 |
| `docs/candidate_v4_validation.md` | 不存在 | 缺少正式冻结验证报告 |
| `docs/candidate_v4_vs_v3_comparison.md` | 不存在 | 缺少正式 V4/V3 对比 |
| `docs/go_nogo_decision.md` | 存在但 INCOMPLETE | 当前文档明确提示 `G_candidate_v4: no runs found` |
| `outputs/analysis/v4_alpha_inputs/input_audit.csv` | 未按方案路径存在 | 本次复跑输出到 `outputs/analysis/v4_alpha_inputs_review/` |

## 4. 策略注册与验证输出

### 4.1 注册状态

`scripts/frozen_backtest_validation.py` 已注册：

```text
G_candidate_v4
G_candidate_v4_lite
```

`G_candidate_v4` 使用：

```text
configs/factors_candidate_v4.yaml
configs/regime_candidate_v4.yaml
```

`G_candidate_v4_lite` 使用：

```text
configs/factors_candidate_v1.yaml
configs/regime_candidate_v4.yaml
```

`scripts/generate_go_nogo_decision.py` 当前候选策略包含：

```text
E_candidate_v2
F_candidate_v3
G_candidate_v4
G_candidate_v4_lite
```

但正式完整性检查仍要求 `G_candidate_v4` 覆盖完整年份。由于 `G_candidate_v4` 无完整 runs，正式文档生成会被拒绝。

### 4.2 `G_candidate_v4` 当前 partial 结果

`outputs/validation/candidate_v4/runs_partial.csv` 仅包含：

| 年份 | 样本 | 年化超额 | IR | 平均换手 |
|------|------|------:|------:|------:|
| 2017 | validation | -16.8% | -2.82 | 36.0% |
| 2018 | validation | -7.2% | -0.55 | 28.4% |
| 2019 | validation | -18.9% | -2.81 | 27.7% |

这些结果不能代表正式 V4 全窗口表现，但已经显示前三个验证年明显弱于 GO 门槛。

### 4.3 `G_candidate_v4_lite` 完整结果

`outputs/validation/candidate_v4_lite/runs.csv` 覆盖完整：

```text
2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024 validation
2026 ytd
```

2017-2024 汇总：

| 指标 | V4-lite 实际 | GO 门槛 | 结论 |
|------|------:|------:|------|
| 平均年化超额 | -2.3% | > 2.0% | 未通过 |
| 中位数年化超额 | 0.5% | > 0.0% | 通过 |
| 正超额年份 | 4/8 | >= 5/8 | 未通过 |
| 平均 IR | -0.52 | > 0.30 | 未通过 |
| 最大单年超额亏损 | -18.9% | > -10.0% | 未通过 |

2026 YTD：

```text
年化超额：-28.2%
IR：-3.62
平均换手：55.7%
```

结论：即使使用 V4-lite 作为诊断候选，也仍是 NO-GO，并且 2026 YTD 明显恶化。

### 4.4 V4-lite 相对 V3

| 年份 | F_candidate_v3 | G_candidate_v4_lite | V4-lite - V3 |
|------|------:|------:|------:|
| 2017 | -15.0% | -16.8% | -1.81pp |
| 2018 | -3.3% | -7.2% | -3.96pp |
| 2019 | 1.0% | -18.9% | -19.85pp |
| 2020 | 9.3% | 11.8% | +2.55pp |
| 2021 | 5.8% | -0.6% | -6.34pp |
| 2022 | 8.1% | 4.6% | -3.51pp |
| 2023 | -4.4% | 7.1% | +11.47pp |
| 2024 | -3.7% | 1.6% | +5.30pp |
| 2026 YTD | -18.3% | -28.2% | -9.88pp |

汇总：

```text
验证年胜出：3/8
平均年度超额差异：-2.02pp
```

结论：V4-lite 改善了 2023/2024，但显著恶化 2017/2018/2019/2021/2022，整体弱于 V3。

## 5. Manifest 审核

### 5.1 `G_candidate_v4` partial/smoke manifest

`G_candidate_v4` partial 与 smoke 结果存在哈希不一致：

```text
outputs/validation/candidate_v4/runs_partial.csv:
2017, 2018, 2019 的 factors_config_sha256 与当前 configs/factors_candidate_v4.yaml 不一致

outputs/validation/candidate_v4_smoke/runs.csv:
2023 的 factors_config_sha256 与当前 configs/factors_candidate_v4.yaml 不一致
2023 的 regime_config_sha256 与当前 configs/regime_candidate_v4.yaml 不一致
```

影响：

- 这些结果不是当前配置的可复现验收结果。
- 冒烟结果不能作为当前冻结版本的证据。
- 如果继续推进，需要重新冻结配置并重新跑 `G_candidate_v4`。

### 5.2 `G_candidate_v4_lite` manifest

`G_candidate_v4_lite` 的 9 个 run manifest 与当前配置匹配：

```text
factors_config_path: configs/factors_candidate_v1.yaml
regime_config_path: configs/regime_candidate_v4.yaml
factor_list_sha256: 非空
```

但它使用的是 `factors_candidate_v1.yaml`，不是 `factors_candidate_v4.yaml`，因此只能作为 lite 诊断结果。

## 6. 因子池与 Alpha 审核

### 6.1 `factors_candidate_v4.yaml`

当前 enabled factors：

```text
ep_cs
bp_cs
sp_cs
reversal_5_cs
pv_divergence_20_cs
volatility_60_cs
log_market_cap_cs
```

这不是一个完整的 V4 alpha 重建池。它主要仍由 V2/V3 旧因子和 WATCH/风险类因子组成。

### 6.2 V4 新因子缓存

当前存在缓存的新因子主要为：

```text
industry_relative_bp_cs
industry_relative_ep_cs
industry_relative_momentum_60_cs
momentum_120_skip20_cs
momentum_60_skip5_cs
risk_adjusted_momentum_60_cs
trend_quality_cs
volume_confirmed_momentum_cs
```

质量、现金流、成长类核心因子多数没有缓存。

### 6.3 输入审计复跑结果

命令：

```powershell
python -X utf8 scripts\audit_alpha_inputs_v4.py --start 20170101 --end 20241231 --out outputs\analysis\v4_alpha_inputs_review
```

结果：

```text
31 factors audited
PASS: 8
WARN: 0
FAIL: 23
BLOCKED: 23
```

blocked 因子包括：

```text
roe_stability_8q_cs
roa_ttm_cs
gross_margin_ttm_cs
net_margin_ttm_cs
profitability_quality_cs
asset_turnover_ttm_cs
ocf_to_mktcap_cs
ocf_to_profit_cs
fcf_yield_cs
cashflow_stability_8q_cs
accrual_quality_cs
receivable_pressure_cs
revenue_growth_ttm_cs
profit_growth_ttm_cs
growth_stability_8q_cs
growth_value_match_cs
earnings_acceleration_cs
valuation_reversion_3y_cs
quality_value_composite_cs
dividend_quality_cs
industry_relative_quality_cs
industry_relative_growth_cs
industry_relative_value_cs
```

结论：V4 方案定义的质量、现金流、成长和复合因子没有形成可用数据基础。

### 6.4 因子质量 gate

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

结论：没有任何因子正式通过 V4 quality gate。按开发方案 M4 验收规则，PASS 因子不足 5 个时应停止策略组装，返回因子建设阶段。

## 7. 测试与审计命令

### 7.1 全量测试

命令：

```powershell
python -X utf8 -m pytest -q
```

结果：

```text
718 passed, 20 warnings in 52.65s
```

结论：工程测试通过。

### 7.2 2017-2024 缓存审计

命令：

```powershell
python -X utf8 scripts\audit_cache.py --start 20170101 --end 20241231 --verbose
```

结果：

```text
Total: 34 checks | PASS=33 | WARN=1 | FAIL=0
```

WARN：

```text
adj_factor_coverage: 87.6%
```

结论：无关键 FAIL，但仍需记录复权因子覆盖率告警。

### 7.3 2026 YTD 缓存审计

命令：

```powershell
python -X utf8 scripts\audit_cache.py --start 20260101 --end 20260605 --verbose
```

结果：

```text
Total: 34 checks | PASS=33 | WARN=1 | FAIL=0
```

WARN：

```text
factor_cs_quality: 22 factors checked; 12 with <12 dates
```

补充观察：多个 V4 新因子在 2026 YTD 缓存为 0 行，这进一步说明 YTD 只能作为观察，不能用于调参或验收。

### 7.4 正式 GO/NO-GO 生成

命令：

```powershell
python -X utf8 scripts\generate_go_nogo_decision.py --runs outputs\validation\frozen_backtest\runs.csv outputs\validation\candidate_v2\runs.csv outputs\validation\candidate_v3\runs.csv outputs\validation\candidate_v4\runs.csv
```

结果：

```text
ERROR: Cannot generate GO/NO-GO decision — data incomplete:
  - G_candidate_v4: no runs found
  - G_candidate_v4_lite: no runs found
```

结论：正式 V4 数据缺失时，脚本能够拒绝生成正式文档。这是正确行为，也证明 V4 正式验收未完成。

### 7.5 Lite 诊断 GO/NO-GO

命令：

```powershell
python -X utf8 scripts\generate_go_nogo_decision.py --runs outputs\validation\frozen_backtest\runs.csv outputs\validation\candidate_v2\runs.csv outputs\validation\candidate_v3\runs.csv outputs\validation\candidate_v4_lite\runs.csv --out docs\_review_go_nogo_decision_v4_incomplete.md --allow-incomplete
```

结果：

```text
Wrote docs\_review_go_nogo_decision_v4_incomplete.md
```

该文档明确标记：

```text
INCOMPLETE
G_candidate_v4: no runs found
```

结论：只能作为诊断文档，不能作为正式验收依据。

## 8. 主要问题

### P0：正式 V4 冻结验证未完成

`G_candidate_v4` 没有完整 `runs.csv`。这是阻断问题。没有 2017-2024 + 2026 YTD 完整结果，就不能做 GO/NO-GO。

### P0：Alpha 重建没有形成可用候选池

V4 方案要求新增质量、现金流、成长等 alpha 来源，但输入审计和质量 gate 均显示核心因子大面积缺失或失败。当前不能证明 V4 具有新增 alpha 供给。

### P0：`G_candidate_v4` manifest 与当前配置不一致

partial/smoke 结果的配置哈希不匹配当前文件。当前结果不能作为冻结验收证据。

### P1：`G_candidate_v4_lite` 被纳入文档，但容易与正式 V4 混淆

Lite 版本完整跑完，但它不是方案定义的正式 V4。需要在文档和脚本输出中明确：lite 是诊断对照，不是验收候选。

### P1：GO/NO-GO 当前处于 INCOMPLETE 状态

`docs/go_nogo_decision.md` 当前已标记为 INCOMPLETE，不能作为正式验收依据。

### P1：当前 V4-lite 表现弱于 V3

V4-lite 相对 V3 只赢 3/8 年，平均年度超额差异为 `-2.02pp`。即使作为降级候选，也不应推进。

### P2：2026 YTD 新因子覆盖不足

2026 YTD 审计中多个 V4 新因子为 0 行，YTD 结果只能观察，不能调参。

## 9. 验收结论

本次审核结论：

```text
工程测试：通过
V4 文件交付：部分通过
Alpha 输入审计：不通过
因子质量 gate：不通过
正式冻结验证：不通过
正式 GO/NO-GO：不通过
策略准入：NO-GO / 不可判定正式 V4
实盘建议：不进入实盘，不进入小资金试运行
```

正式判定：**V4 开发方案未完成验收**。

## 10. 下一步处理建议

### 10.1 立即停止事项

1. 不要把 `G_candidate_v4_lite` 当作 `G_candidate_v4` 验收。
2. 不要使用当前 `docs/go_nogo_decision.md` 作为正式决策依据，因为它是 INCOMPLETE。
3. 不要基于 2026 YTD 调参。
4. 不要进入实盘或小资金试运行。

### 10.2 必须补齐的工作

1. 先修复 V4 输入数据：
   - 质量类因子
   - 现金流类因子
   - 成长类因子
   - 复合质量/成长/价值因子
2. 重新运行：
   ```powershell
   python -X utf8 scripts\audit_alpha_inputs_v4.py --start 20170101 --end 20241231 --out outputs\analysis\v4_alpha_inputs
   ```
3. 重新运行 V4 因子质量 gate，要求至少形成足够 PASS 因子：
   ```powershell
   python -X utf8 scripts\factor_quality_rebuild.py --config configs\factor_quality_rebuild_v4.yaml --out-dir outputs\analysis\factor_quality_rebuild_v4 --out-doc docs\factor_quality_rebuild_v4_report.md
   ```
4. 如果 PASS 因子仍不足 5 个，停止策略组装，继续因子建设。
5. 如需继续 `G_candidate_v4`，必须重新冻结当前配置并完整重跑：
   ```powershell
   python -X utf8 scripts\frozen_backtest_validation.py --strategies G_candidate_v4 --out-dir outputs\validation\candidate_v4 --out-doc docs\candidate_v4_validation.md --force
   ```
6. 完整验证完成后再生成正式 GO/NO-GO：
   ```powershell
   python -X utf8 scripts\generate_go_nogo_decision.py --runs outputs\validation\frozen_backtest\runs.csv outputs\validation\candidate_v2\runs.csv outputs\validation\candidate_v3\runs.csv outputs\validation\candidate_v4\runs.csv
   ```

### 10.3 建议调整

如果短期内无法补齐质量/现金流/成长数据，建议不要继续称当前版本为 V4 Alpha 重建。更合适的命名是：

```text
G_candidate_v4_lite: V3 factors + V4 regime diagnostic
```

正式 `G_candidate_v4` 应保留给真正完成 alpha 输入、因子 gate、冻结验证的版本。

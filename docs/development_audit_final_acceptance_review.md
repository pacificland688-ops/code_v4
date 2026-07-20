# 最终验收审核报告

生成日期：2026-06-12
依据方案：`docs/development_audit_final_execution_fix_plan.md`

## 1. 执行命令清单

```powershell
# M1: 候选 v2 完整冻结复验
python -X utf8 scripts/frozen_backtest_validation.py --strategies E_candidate_v2 --out-dir outputs/validation/candidate_v2 --out-doc docs/candidate_v2_validation.md --force

# M2-M3: 验证
Import-Csv outputs/validation/candidate_v2/runs.csv | Group-Object sample | Select-Object Count,Name
# 验证 manifest 哈希与因子池（见 §5-6）

# M4: GO/NO-GO 文档
python -X utf8 scripts/generate_go_nogo_decision.py

# M5: 最终回归
python -X utf8 -m pytest -q
python -X utf8 scripts/audit_cache.py --start 20170101 --end 20241231
python -X utf8 scripts/audit_cache.py --start 20260101 --end 20260605
```

## 2. 单元测试

```
572 passed, 8 warnings
```

8 warnings 均为已知可接受项（pandas SettingWithCopy、cvxpy ECOS deprecation、spearmanr constant input）。

## 3. 数据审计

### 2017-2024 历史验证窗口

```
Total: 12 checks | PASS=11 | WARN=1 | FAIL=0
```

| Check | Status |
|-------|--------|
| adj_factor_dedup | PASS |
| adj_factor_coverage | WARN (87.6% — 可接受，已在文档说明) |
| prices_adj_jumps | PASS |
| factor_legacy_files | PASS |
| 其他全部 | PASS |

### 2026 YTD 窗口

```
Total: 12 checks | PASS=11 | WARN=1 | FAIL=0
```

| Check | Status |
|-------|--------|
| factor_cs_quality | WARN (5 factors <12 dates — 短样本正常) |
| adj_factor_dedup | PASS |
| 其他全部 | PASS |

## 4. 候选 v2 runs.csv 覆盖

| sample | count |
|--------|-------|
| validation | 8 |
| ytd | 1 |

覆盖年份：2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2026

全部 9 条记录 `strategy` = `E_candidate_v2`，`run_dir` 非空，关键指标非空。

## 5. Manifest 哈希检查

| year | factors_hash | regime_hash | factor_list_hash |
|------|:-----------:|:-----------:|:----------------:|
| 2017 | OK | OK | OK |
| 2018 | OK | OK | OK |
| 2019 | OK | OK | OK |
| 2020 | OK | OK | OK |
| 2021 | OK | OK | OK |
| 2022 | OK | OK | OK |
| 2023 | OK | OK | OK |
| 2024 | OK | OK | OK |
| 2026 | OK | OK | OK |

全部 9 个 run manifest 的 `factors_config_sha256`、`regime_config_sha256`、`factor_list_sha256` 非空。

## 6. 因子池检查

全部 9 个 run 的 `factor_list`：

```
bp_cs
ep_cs
pv_divergence_20_cs
reversal_5_cs
sp_cs
```

旧弱因子（`momentum_120_cs`、`momentum_60_cs`、`reversal_20_cs`、`volatility_20_cs`）**全部排除** ✅。

## 7. GO/NO-GO 文档生成

- 生成命令退出码：0
- 标题无 `INCOMPLETE` ✅
- 无 `1/1` 误导性显示 ✅
- `E_candidate_v2` 覆盖 2017-2024 完整 ✅
- 2026 YTD 前瞻观察非空 ✅
- 所有指标从 `runs.csv` 自动生成 ✅

## 8. 最终判定

### 工程验收：✅ GO

| 条件 | 状态 |
|------|:----:|
| pytest 全部通过 | ✅ |
| 2017-2024 audit FAIL=0 | ✅ |
| 2026 YTD audit FAIL=0 | ✅ |
| candidate_v2 runs.csv: 8 validation + 1 ytd | ✅ |
| candidate run manifests: all hashes non-empty | ✅ |
| candidate run manifests: no old weak factors | ✅ |
| go_nogo_decision.md: generated, not INCOMPLETE | ✅ |

### 策略判定：❌ NO-GO

| 指标 | 门槛 | 实际值 | 通过 |
|------|------|--------|:----:|
| 平均年化超额 | > 2% | -1.2% | ❌ |
| 中位数年化超额 | > 0% | -2.8% | ❌ |
| 正超额年份 | ≥ 5 | 3/8 | ❌ |
| 平均 IR | > 0.30 | -0.21 | ❌ |
| 最大单年超额亏损 | > -10% | -15.8% | ❌ |

E_candidate_v2 在 2017-2024 验证窗口上未达到策略 GO 门槛：
- 仅 3/8 年正超额（2020: +8.6%, 2021: +4.6%, 2022: +7.2%）
- 2017 年超额亏损 -15.8% 超过 -10% 阈值
- 2026 YTD 前瞻观察为 -18.1%，与验证期方向一致偏弱

---

生成时间：2026-06-12 22:15
审核结论：工程验收 GO，策略 NO-GO（以 `docs/go_nogo_decision.md` 为准）

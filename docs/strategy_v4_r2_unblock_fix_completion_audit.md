# Strategy V4-r2 解除阻断二次修复审核验证记录

生成日期：2026-06-19  
审核对象：`docs/strategy_v4_r2_unblock_fix_development_plan.md`  
结论：**部分通过，但不通过策略验收。V4-r2 仍为 NO-GO，不得进入实盘。**

## 1. 审核结论

本轮二次修复完成了工程层面的关键补丁：

- 空 `enabled_factors` 语义已修复。
- `candidate_policy` 门禁已加入。
- `scripts/validate_validation_manifest.py` 已新增。
- 正式 gate 文件已恢复生成。
- 全量测试通过。

但策略层面仍未解除核心阻断：

- `factor_quality_gate.csv` 中 **PASS=0**。
- `factor_candidate_pool.yaml` 中 `eligible_factors=[]`。
- `configs/factors_candidate_v4_r2.yaml` 中 `enabled_factors=[]`。
- `configs/regime_candidate_v4_r2.yaml` 所有 sleeve 为空。
- smoke validation 未运行。
- 当前 full validation runs 仍是旧配置 hash，manifest 校验失败。

最终状态：

```text
Engineering fixes: PASS
Data cache audit: PASS
Factor gate: FAIL
Candidate pool: BLOCKED
Smoke/full validation: BLOCKED
GO/NO-GO: NOT VALID FOR CURRENT CONFIG
Production readiness: NO-GO
```

## 2. 复核命令结果

### 2.1 cache audit

命令：

```powershell
python -X utf8 scripts\audit_cache.py --start 20170101 --end 20241231 --verbose
python -X utf8 scripts\audit_cache.py --start 20260101 --end 20260605 --verbose
```

结果：

```text
2017-2024: PASS=64 / WARN=1 / FAIL=0
2026 YTD:  PASS=64 / WARN=1 / FAIL=0
```

结论：数据重复键与 cache 质量阻断已解除。

### 2.2 alpha input audit

命令：

```powershell
python -X utf8 scripts\audit_alpha_inputs_v4.py --start 20170101 --end 20241231 --out outputs\analysis\v4_alpha_inputs_review_verify_20260619
```

结果：

```text
PASS: 13
WARN: 4
FAIL: 14
BLOCKED: 14
```

结论：输入审计仍不是全量通过，growth 因子为 WARN。

### 2.3 factor gate

文件：

```text
outputs/analysis/factor_quality_rebuild_v4/factor_quality_gate.csv
```

结果：

```text
FAIL: 49
DATA_MISSING: 14
WATCH_NEUTRAL_UNAVAILABLE: 2
SUPPORT: 1
PASS: 0
```

四个 growth 因子均为 FAIL：

```text
revenue_growth_ttm_cs: FAIL
profit_growth_ttm_cs: FAIL
growth_stability_8q_cs: FAIL
earnings_acceleration_cs: FAIL
```

结论：未满足 `PASS alpha factors >= 3` 门禁。

### 2.4 candidate pool 与 sleeve

当前候选池：

```text
eligible_factors: []
recommendation: NO_ALPHA_SOURCE_FOUND
```

当前 `configs/factors_candidate_v4_r2.yaml`：

```text
candidate_policy.formal_candidate: false
candidate_policy.blocked_reason: NO_ALPHA_SOURCE
enabled_factors: []
```

当前 `configs/regime_candidate_v4_r2.yaml`：

```text
defensive: []
growth: []
value: []
momentum: []
reversal: []
volume_price: []
min_sleeves: 0
all regime weight sums: 0.0
```

结论：候选池和 sleeve 被正确阻断，没有形成正式 alpha 策略。

### 2.5 manifest 校验

命令：

```powershell
python -X utf8 scripts\validate_validation_manifest.py --runs outputs\validation\candidate_v4_r2\runs.csv --factors-config configs\factors_candidate_v4_r2.yaml --regime-config configs\regime_candidate_v4_r2.yaml --required-validation-years 2017 2018 2019 2020 2021 2022 2023 2024 --required-ytd-years 2026
```

结果：

```text
VALIDATION FAILED
Manifest check: 9 runs, 0 missing, 18 hash mismatches
```

结论：现有 `candidate_v4_r2/runs.csv` 不是当前配置的正式验证证据。

### 2.6 smoke/full validation

当前状态：

```text
outputs/validation/candidate_v4_r2_smoke/runs.csv: MISSING
docs/_v4_r2_smoke.md: MISSING
outputs/validation/candidate_v4_r2/runs.csv: EXISTS, but manifest mismatch
```

结论：按门禁，当前不应继续 validation；已有 full runs 作废。

### 2.7 tests

专项测试：

```text
109 passed, 1 skipped
```

全量测试：

```text
850 passed, 12 skipped, 20 warnings
```

结论：工程测试通过。

## 3. 最终完成定义审核

| 条件 | 状态 |
|---|---|
| `audit_cache` 2017-2024 `FAIL=0` | PASS |
| `audit_cache` 2026 YTD `FAIL=0` | PASS |
| 正式 `factor_quality_gate.csv` 存在 | PASS |
| gate PASS alpha factors >= 3 | FAIL，当前 0 |
| `enabled_factors` 非空且合规 | FAIL，当前空 |
| 空 `enabled_factors` 不返回全量因子 | PASS |
| regime 有合规非空 sleeve | FAIL，全部为空 |
| smoke runs 存在且 manifest 匹配 | FAIL，缺失 |
| full runs 覆盖 2017-2024 + 2026 | INVALID，旧 hash |
| full runs manifest mismatch count = 0 | FAIL，当前 18 hash mismatches |
| GO/NO-GO 覆盖 r2 且不含 INCOMPLETE | INVALID，基于无效 runs |
| 全量 pytest 通过 | PASS |
| 审核给出明确 GO/NO-GO | PASS，NO-GO |

## 4. 后续建议

当前不是工程链路问题，而是 alpha 源问题。下一步不应继续包装 `G_candidate_v4_r2`，而应进入因子质量修复或新因子开发：

1. 修复 value 因子的 fundamental lag / leakage metadata。
2. 提升 growth 因子的覆盖率和有效横截面宽度。
3. 复核 `volatility_60_cs`、`low_volatility_60d_cs`、`residual_volatility_60d_cs` 的 neutralization 覆盖率。
4. 重新设计适用于 A 股全周期/多趋势的 alpha 因子。
5. 只有 gate PASS alpha factors >= 3 后，再恢复候选池、sleeve、smoke/full validation。

## 5. 最终判定

```text
V4-r2 unblock fix completion: PARTIAL
是否完成工程修复: 是
是否解除策略阻断: 否
是否允许候选池重建: 否
是否允许正式验证: 否
是否允许 GO/NO-GO 决策: 否
是否允许实盘: 否
```


# Strategy V4 Alpha 重建 开发日志

生成日期：2026-06-14  
候选策略：`G_candidate_v4`  
前置方案：`docs/strategy_v4_alpha_rebuild_development_plan.md`  
最终判定：**待冻结验证后确定**（配置已预注册）

## 1. 开发时间线

| 日期 | 阶段 | 关键活动 | 产物 |
|------|------|------|------|
| 2026-06-14 | M0 | V3 归档与缺口修复 | `candidate_v3_vs_v2_comparison.md`, `strategy_v3_development_log.md`, go_nogo drawdown 字段修正 |
| 2026-06-14 | M1 | 失败年份归因深化 | `failure_year_monthly_attribution_v4.md`, `strategy_failure_source_matrix_v4.md`, `alpha_rebuild_priority_list.md` |
| 2026-06-14 | M2 | 数据可用性与 PIT 审计 | `v4_data_inventory.md`, `v4_pit_alignment_rules.md`, `audit_alpha_inputs_v4.py`, `test_alpha_inputs_v4.py` |
| 2026-06-14 | M3 | 候选因子开发 | `factors_alpha_v4_universe.yaml`, `factor_build_v4.yaml`, `build_alpha_factors_v4.py`, `alpha_factor_definitions_v4.md`, `test_alpha_factors_v4.py` |
| 2026-06-14 | M4 | 因子质量 gate | `factor_quality_rebuild_v4.yaml`, `factors_candidate_v4.yaml`, `factor_rejection_log_v4.md`, `factor_quality_manual_review_v4.md` |
| 2026-06-14 | M5 | Sleeve/regime 重构 | `regime_candidate_v4.yaml`, `sleeve_design_v4.md`, `test_regime_candidate_v4_config.py` |
| 2026-06-14 | M6 | 策略预注册 | `G_candidate_v4` 注册到 `frozen_backtest_validation.py` 和 `generate_go_nogo_decision.py` |
| 2026-06-14 | M7 | 冻结验证就绪 | `strategy_v4_freeze_spec.md`（配置冻结，待运行完整回测） |
| 2026-06-14 | M8 | 开发日志 | 本文档 |

## 2. 关键命令（待执行）

### 2.1 冒烟测试
```powershell
python -X utf8 scripts\frozen_backtest_validation.py --strategies G_candidate_v4 --years 2023 --force --out-dir outputs\validation\candidate_v4_smoke --out-doc docs\_v4_smoke.md
```

### 2.2 完整冻结验证
```powershell
python -X utf8 scripts\frozen_backtest_validation.py --strategies G_candidate_v4 --out-dir outputs\validation\candidate_v4 --out-doc docs\candidate_v4_validation.md --force
```

### 2.3 GO/NO-GO 决策
```powershell
python -X utf8 scripts\generate_go_nogo_decision.py --runs outputs\validation\frozen_backtest\runs.csv outputs\validation\candidate_v2\runs.csv outputs\validation\candidate_v3\runs.csv outputs\validation\candidate_v4\runs.csv
```

### 2.4 数据审计
```powershell
python -X utf8 scripts\audit_cache.py --start 20170101 --end 20241231 --verbose
python -X utf8 scripts\audit_cache.py --start 20260101 --end 20260605 --verbose
python -X utf8 scripts\audit_alpha_inputs_v4.py --start 20170101 --end 20241231 --out outputs\analysis\v4_alpha_inputs
```

### 2.5 因子构建
```powershell
python -X utf8 scripts\build_alpha_factors_v4.py --config configs\factor_build_v4.yaml --start 20170101 --end 20241231 --force
python -X utf8 scripts\build_alpha_factors_v4.py --config configs\factor_build_v4.yaml --start 20260101 --end 20260605 --force
```

### 2.6 因子质量 gate
```powershell
python -X utf8 scripts\factor_quality_rebuild.py --config configs\factor_quality_rebuild_v4.yaml --out-dir outputs\analysis\factor_quality_rebuild_v4 --out-doc docs\factor_quality_rebuild_v4_report.md
```

## 3. V4 核心变更摘要

| 维度 | V3 | V4 | 变更幅度 |
|------|------|------|------|
| 因子池（候选） | 5 因子 | 17+ 因子（含 PENDING_GATE） | +240% |
| 因子类别 | 2 类（value + tech） | 6 类（quality + cashflow + growth + value_repair + industry_rel + risk_adj_mom） | +4 类 |
| Sleeve 数 | 6 | 6（重新定义） | 重构 |
| Performance overlay | 开启（strength=0.40） | **关闭** | 关闭 |
| PIT 审计 | 无 | 新增（`audit_alpha_inputs_v4.py`） | 新增 |
| 因子质量 gate | 已有 | 扩展至 V4 因子池（48 因子） | 扩展 |

## 4. 测试覆盖

| 测试文件 | 新增测试数 | 覆盖内容 |
|------|------:|------|
| `test_go_nogo_decision.py` | +3 | drawdown 字段 (Avg/Worst Max DD) |
| `test_alpha_inputs_v4.py` | +21 | PIT 安全、缺失数据、stale 检测、blocked factors |
| `test_alpha_factors_v4.py` | +32 | 因子公式、方向、PIT、CS 处理 |
| `test_regime_candidate_v4_config.py` | +13 | Sleeve 结构、权重和、配置合法性 |
| **合计** | **+69** | |

全量测试：690 passed, 18 warnings（2026-06-14）

## 5. 产物清单

### 配置文件（5 新 + 2 修改）
| 文件 | 状态 |
|------|------|
| `configs/factors_alpha_v4_universe.yaml` | ✅ 新建 |
| `configs/factor_build_v4.yaml` | ✅ 新建 |
| `configs/factor_quality_rebuild_v4.yaml` | ✅ 新建 |
| `configs/factors_candidate_v4.yaml` | ✅ 新建 |
| `configs/regime_candidate_v4.yaml` | ✅ 新建 |
| `scripts/frozen_backtest_validation.py` | ✅ 已修改（注册 G_candidate_v4） |
| `scripts/generate_go_nogo_decision.py` | ✅ 已修改（含 G_candidate_v4、修复 drawdown 字段） |

### 脚本文件（1 新）
| 文件 | 状态 |
|------|------|
| `scripts/build_alpha_factors_v4.py` | ✅ 新建 |
| `scripts/audit_alpha_inputs_v4.py` | ✅ 新建 |

### 测试文件（3 新 + 1 修改）
| 文件 | 状态 |
|------|------|
| `tests/test_alpha_inputs_v4.py` | ✅ 新建 |
| `tests/test_alpha_factors_v4.py` | ✅ 新建 |
| `tests/test_regime_candidate_v4_config.py` | ✅ 新建 |
| `tests/test_go_nogo_decision.py` | ✅ 已修改 |

### 文档文件（14 新）
| 文件 | 状态 |
|------|------|
| `docs/candidate_v3_vs_v2_comparison.md` | ✅ 新建 (M0) |
| `docs/strategy_v3_development_log.md` | ✅ 新建 (M0) |
| `docs/failure_year_monthly_attribution_v4.md` | ✅ 新建 (M1) |
| `docs/strategy_failure_source_matrix_v4.md` | ✅ 新建 (M1) |
| `docs/alpha_rebuild_priority_list.md` | ✅ 新建 (M1) |
| `docs/v4_data_inventory.md` | ✅ 新建 (M2) |
| `docs/v4_pit_alignment_rules.md` | ✅ 新建 (M2) |
| `docs/alpha_factor_definitions_v4.md` | ✅ 新建 (M3) |
| `docs/factor_quality_manual_review_v4.md` | ✅ 新建 (M4) |
| `docs/factor_rejection_log_v4.md` | ✅ 新建 (M4) |
| `docs/sleeve_design_v4.md` | ✅ 新建 (M5) |
| `docs/strategy_v4_freeze_spec.md` | ✅ 新建 (M6) |
| `docs/strategy_v4_development_log.md` | ✅ 本文档 (M8) |

## 6. 修复启动 (2026-06-14)

按照 `docs/strategy_v4_acceptance_fix_development_plan.md` 启动修复。

### 阻断项
- 23/31 个 V4 因子 DATA_MISSING（无 fina_indicator/income 数据）
- 因子质量 gate: 0 PASS
- `G_candidate_v4` 无完整 `runs.csv`, manifest 不一致
- GO/NO-GO 处于 INCOMPLETE 状态

### 修复版本
- 新候选名：`G_candidate_v4_r1`
- `G_candidate_v4` 废弃
- `G_candidate_v4_lite` 仅保留为诊断对照

### M0 归档（已完成）
- [x] 归档 INCOMPLETE GO/NO-GO → `docs/_review_go_nogo_decision_v4_incomplete.md`
- [x] 标记 G_candidate_v4 不可验收 → `docs/strategy_v4_completion_review.md`
- [x] 确认 lite 不用于正式验收
- [x] 追加本修复记录

### 下一步

1. **M1**: 修复 Tushare 基本面数据管道（fina_indicator, income）
2. **M2**: 重建全部 V4 因子缓存
3. **M3**: 重跑因子质量 gate
4. **M4**: 重建候选因子池（仅 PASS 因子）
5. **M5**: 修订 regime/sleeve 配置
6. **M6**: 注册 `G_candidate_v4_r1`
7. **M7**: 冒烟测试 (2023)
8. **M8**: 完整冻结验证 (2017-2024 + 2026 YTD)
9. **M9**: V4-r1 vs V3 对比分析
10. **M10**: 正式 GO/NO-GO 决策

---

## 7. V4-r1 完成与关闭 (2026-06-14)

### 7.1 V4-r1 结果摘要

| 日期 | 阶段 | 关键活动 | 产物 |
|------|------|------|------|
| 2026-06-14 | V4-r1 | 补齐正式冻结验证链路和 GO/NO-GO 生成链路 | `outputs/validation/candidate_v4_r1/runs.csv`, `docs/go_nogo_decision.md` |

### 7.2 V4-r1 审核结论

按照 `docs/strategy_v4_r1_completion_review.md` 审核：

```text
工程链路：部分通过
正式冻结验证：通过
Manifest：通过
缓存审计：不通过（4 个 growth 因子重复键，FAIL=5）
输入审计：不通过（PASS=8, FAIL=23, BLOCKED=23）
因子 gate：不通过（0 PASS, 1 WATCH, 20 FAIL, 28 DATA_MISSING）
候选因子池合规：不通过（enabled 中无 PASS 因子，含审计失败因子）
策略表现：NO-GO（平均年化超额 -1.4%，平均 IR -0.36）
文档闭环：不完整
实盘建议：不进入实盘
```

正式结论：**V4-r1 不通过验收，已归档为 NO-GO 候选。**

### 7.3 G_candidate_v4_r1 关闭记录

- [x] V4-r1 审核报告完成 → `docs/strategy_v4_r1_completion_review.md`
- [x] GO/NO-GO 正式判决为 NO-GO → `docs/go_nogo_decision.md`
- [x] `outputs/validation/candidate_v4_r1/` 保留，不覆盖
- [x] `G_candidate_v4_r1` 不再修改
- [x] 关闭日期：2026-06-14

### 7.4 根因诊断

V4-r1 暴露的两个核心问题：

1. **Growth 因子缓存存在重复键**：`revenue_growth_ttm_cs`, `profit_growth_ttm_cs`, `growth_stability_8q_cs`, `earnings_acceleration_cs` 在 PIT 展开时，同一 `(ts_code, trade_date)` 被多个 `available_date` 匹配，产生大量重复行。根因：`build_alpha_factors_v4.py` 的 PIT merge 未做去重。

2. **候选池绕过 factor gate**：`factors_candidate_v4_r1.yaml` 手工编写，未经 gate 过滤。0 个 PASS 因子进入 enabled，17 个 enabled 因子全部为 FAIL 或 DATA_MISSING。根因：候选池生成逻辑未读取 `factor_quality_gate.csv`。

### 7.5 V4-r2 启动

基于 V4-r1 审核结论，启动 V4-r2 修复：

- 新候选名：`G_candidate_v4_r2`
- 开发方案：`docs/strategy_v4_r2_data_gate_fix_development_plan.md`
- 目标：修复 growth 因子重复键 + 候选池 gate 规则，不调参

---

## 8. V4-r2 数据质量与 Gate 修复 (2026-06-15)

按照 `docs/strategy_v4_r2_data_gate_fix_development_plan.md` 启动修复。

### 8.1 启动状态

| 项目 | 状态 |
|------|------|
| V4-r1 归档 | ✅ 已关闭，NO-GO |
| V4-r2 开发方案 | ✅ 已生成 |
| 新候选名 | `G_candidate_v4_r2` |
| 目标 | 修复数据质量与 gate 规则，不调参 |

### 8.2 里程碑进度

| 里程碑 | 状态 | 日期 | 产物 |
|------|------|------|------|
| M0: 归档 V4-r1 | ✅ 完成 | 2026-06-15 | 开发日志更新 |
| M1: 定位 growth 重复键 | ✅ 完成 | 2026-06-15 | `scripts/diagnose_factor_duplicates.py`, `docs/v4_growth_duplicate_root_cause.md` |
| M2: 修复因子构建 | ✅ 完成 | 2026-06-15 | `scripts/build_alpha_factors_v4.py` (dedup + assertion), `tests/test_alpha_factors_v4.py` (PIT dedup tests) |
| M3: 重跑数据审计 | ⏳ 用户执行 | | 需先执行 M2.5（重建缓存） |
| M4: 重跑 factor gate | ⏳ 用户执行 | | 需先执行 M3 |
| M5: 重建候选池 | ✅ 完成 | 2026-06-15 | `configs/factors_candidate_v4_r2.yaml`, `docs/factors_candidate_v4_r2_selection.md`, `tests/test_factor_candidate_v4_r2.py` |
| M6: Sleeve/Regime 修订 | ✅ 完成 | 2026-06-15 | `configs/regime_candidate_v4_r2.yaml`, `docs/sleeve_design_v4_r2.md`, `tests/test_regime_candidate_v4_r2_config.py` |
| M7: 注册 G_candidate_v4_r2 | ✅ 完成 | 2026-06-15 | `scripts/frozen_backtest_validation.py`, `scripts/generate_go_nogo_decision.py`, `docs/strategy_v4_r2_freeze_spec.md` |
| M8: 冒烟测试 | ⏳ 用户执行 | | 需先执行 M3-M4 |
| M9: 完整冻结验证 | ⏳ 用户执行 | | 需先执行 M8 |
| M10: 对比分析 | ⏳ 用户执行 | | 需先执行 M9 |
| M11: 正式 GO/NO-GO | ⏳ 用户执行 | | 需先执行 M10 |

### 8.3 M1-M2 技术细节

#### 根因
`scripts/build_alpha_factors_v4.py` 第 799 行 PIT merge 按 `ts_code` 做 inner join，产生笛卡尔积。多家公司的多个 `available_date` 同时有效于同一 `trade_date`，产生大量重复 `(ts_code, trade_date)` 行。参见 `docs/v4_growth_duplicate_root_cause.md`。

#### 修复
在第 800 行 PIT 过滤后增加：
```python
df = df.sort_values(["ts_code", "trade_date", "available_date"])
df = df.drop_duplicates(["ts_code", "trade_date"], keep="last")
```
并在缓存写入前增加硬断言：
```python
assert not df.duplicated(["ts_code", "trade_date"]).any()
```

#### 诊断工具
`scripts/diagnose_factor_duplicates.py` 可按因子扫描重复键，输出分类统计和样本。

### 8.4 M5-M7 配置变更

| 维度 | V4-r1 | V4-r2 |
|------|------|------|
| 候选池 | 17 enabled（全部 FAIL/DATA_MISSING） | 1 enabled (volatility_60_cs, WATCH+documented) |
| 合规因子 | 0 PASS | 0 PASS + 1 WATCH (documented) |
| Growth sleeve | 4 因子（输入审计 FAIL） | 空（PENDING_GATE） |
| Momentum sleeve | 7 因子（全部 FAIL） | 空（全部 FAIL） |
| Value sleeve | 5 因子（全部 FAIL） | 空（全部 FAIL） |
| Defensive sleeve | 5 因子（含 FAIL） | 2 因子（WATCH + neutralizer） |
| Performance overlay | disabled | disabled |
| 策略注册 | G_candidate_v4_r1 | G_candidate_v4_r2 |

### 8.5 全量测试（V4-r2 初始）

```text
763 passed, 4 skipped, 19 warnings in 145.99s
```

新增测试：
- `tests/test_alpha_factors_v4.py`: +5 PIT dedup tests
- `tests/test_factor_candidate_v4_r2.py`: +12 candidate pool compliance tests
- `tests/test_regime_candidate_v4_r2_config.py`: +11 regime config validation tests

---

## 9. V4-r2 返工修复 (2026-06-15)

按照 `docs/strategy_v4_r2_remediation_development_plan.md` 执行返工修复。

### 9.1 返工原因

V4-r2 未通过完成审核（`docs/strategy_v4_r2_completion_review.md`），9 项硬失败：

1. `audit_cache` 两个窗口均为 `FAIL=5`
2. 四个 growth 因子仍存在重复键
3. V4 输入审计 `PASS=8 / FAIL=23 / BLOCKED=23`
4. factor gate `PASS=0 / WATCH=1 / FAIL=20 / DATA_MISSING=28`
5. 候选池仅启用 `volatility_60_cs`（WATCH，非 alpha PASS）
6. `regime_candidate_v4_r2.yaml` 空 sleeve 仍被分配非零权重
7. `outputs/validation/candidate_v4_r2/` 缺失
8. `go_nogo_decision.md` 未覆盖 r2
9. `main()` 候选列表未包含 `G_candidate_v4_r2`

### 9.2 返工进度

| 里程碑 | 状态 | 产物 |
|------|:---:|------|
| R0: 冻结失败基线 | ✅ | 保留审核报告与 gate 基线 |
| R1: 定位 growth 重复键 | ✅ | `scripts/diagnose_factor_duplicates.py` (enhanced) |
| R2: 修复 PIT 展开与去重 | ✅ | `scripts/build_alpha_factors_v4.py` (dedup + assertion) |
| R2: 单测补强 | ✅ | `tests/test_growth_factor_pit_dedup_v4_r2.py`, `tests/test_audit_cache_factor_duplicates.py` |
| R3: 重建 growth 缓存 | ⏳ 用户执行 | |
| R4: 通过 cache/input audit | ⏳ 用户执行 | |
| R5: 重跑 factor gate | ⏳ 用户执行 | |
| R6: 重建候选池 + allocator | ✅ | `configs/regime_candidate_v4_r2.yaml` (空 sleeve 权重归零), `tests/test_candidate_v4_r2_gate_enforcement.py` |
| R7: 修复 GO/NO-GO r2 | ✅ | `scripts/generate_go_nogo_decision.py` (main() 含 r2), `tests/test_go_nogo_decision.py` (+6 r2 inclusion tests) |
| R8: smoke 验证 | ⏳ 用户执行 | |
| R9: 完整冻结验证 | ⏳ 用户执行 | |
| R10: 对比报告 + GO/NO-GO | ⏳ 用户执行 | |
| R11: 最终验收报告 | ⏳ 用户执行 | |

### 9.3 R6 关键修复：Allocator 空 sleeve 权重归零

修复前：
```yaml
trend_up:
  defensive: 0.50
  growth: 0.20    # ← 空 sleeve 有非零权重
  momentum: 0.15  # ← 空 sleeve 有非零权重
  value: 0.10     # ← 空 sleeve 有非零权重
```

修复后：
```yaml
trend_up:
  defensive: 1.00  # 唯一非空 sleeve
  growth: 0.00
  momentum: 0.00
  value: 0.00
  volume_price: 0.00
  reversal: 0.00
```

### 9.4 R7 关键修复：GO/NO-GO r2 纳入

```python
# main() 修复前：
candidate_strategies = ["E_candidate_v2", "F_candidate_v3", "G_candidate_v4_r1"]

# main() 修复后：
candidate_strategies = ["E_candidate_v2", "F_candidate_v3", "G_candidate_v4_r1", "G_candidate_v4_r2"]
```

### 9.5 全量测试（返工后）

```text
793 passed, 12 skipped, 19 warnings in 168.48s
```

新增 30 个测试 (+30 from 763 baseline)：
- `tests/test_growth_factor_pit_dedup_v4_r2.py`: +9 PIT dedup scenarios (multi-report, ann_date revision, future leakage, all-4-factors)
- `tests/test_audit_cache_factor_duplicates.py`: +8 duplicate detection & threshold tests
- `tests/test_candidate_v4_r2_gate_enforcement.py`: +10 gate enforcement tests (FAIL exclusion, empty sleeve zero weight, defensive-only detection)
- `tests/test_go_nogo_decision.py`: +6 r2 inclusion tests (missing r2 rejection, year coverage, document content)

### 9.6 文件变更清单

| 类型 | 文件 | 变更 |
|------|------|------|
| 修复 | `scripts/generate_go_nogo_decision.py` | main() 含 G_candidate_v4_r2 |
| 修复 | `configs/regime_candidate_v4_r2.yaml` | Allocator 空 sleeve 权重归零 |
| 修复 | `scripts/build_alpha_factors_v4.py` | PIT dedup + 唯一键断言 + month分区清理 |
| 修复 | `scripts/audit_alpha_inputs_v4.py` | _load_factor_cache 支持 V4 year=*/part_*.parquet 格式 |
| 修复 | `scripts/factor_quality_rebuild.py` | _load_factor_cache_raw 支持 V4 格式 + value 列直接读取 |
| 修复 | `configs/factor_quality_rebuild_v4.yaml` | growth 因子添加 data_lag_days: 63 |
| 新增 | `tests/test_growth_factor_pit_dedup_v4_r2.py` | 9 tests |
| 新增 | `tests/test_audit_cache_factor_duplicates.py` | 8 tests |
| 新增 | `tests/test_candidate_v4_r2_gate_enforcement.py` | 10 tests |
| 修改 | `tests/test_go_nogo_decision.py` | +6 r2 inclusion tests |
| 保留 | `tests/test_go_nogo_data_gate.py` | 已有测试，未修改 |

---

## 10. V4-r2 执行结果 (2026-06-16)

### 10.1 R3-R5 执行摘要

| 步骤 | 状态 | 结果 |
|------|:---:|------|
| R3: 重建 growth 缓存 | ✅ | 4 因子重建完成，无 AssertionError，覆盖 2017-2024 + 2026 YTD |
| R4: audit_cache 2017-2024 | ✅ | **FAIL=0**（修复前 FAIL=5） |
| R4: audit_cache 2026 YTD | ✅ | **FAIL=0**（修复前 FAIL=5） |
| R4: growth dup=0 | ✅ | 4 因子均 CLEAN |
| R4: audit_alpha_inputs_v4 | ⚠️ | PASS=8, WARN=2, FAIL=21（growth 稳定/加速因子因股票覆盖不足 FAIL） |
| R5: factor quality gate | ❌ | **PASS=0, FAIL=25, DATA_MISSING=24** |

### 10.2 Gate 最终结果

```
FAIL: 25
  reversal_5_cs (14), reversal_20_cs (13), momentum_60_cs (14), momentum_120_cs (10)
  volatility_20_cs (5), volatility_60_cs (2), rsi_14_cs (12), macd_12_26_9_cs (15)
  pv_divergence_20_cs (12), ep_cs (8), bp_cs (8), sp_cs (8)
  log_market_cap_cs (10)
  revenue_growth_ttm_cs (10), profit_growth_ttm_cs (10)
  growth_stability_8q_cs (12), earnings_acceleration_cs (12)
  industry_relative_ep_cs (8), industry_relative_bp_cs (8), industry_relative_momentum_60_cs (12)
  momentum_60_skip5_cs (8), momentum_120_skip20_cs (12)
  risk_adjusted_momentum_60_cs (7), volume_confirmed_momentum_cs (14), trend_quality_cs (11)

DATA_MISSING: 24
  (28 个因子缺少底层数据 — fina_indicator/income 数据未覆盖)

PASS: 0
WATCH: 0
```

### 10.3 退出判定

根据 `strategy_v4_r2_remediation_development_plan.md` §21 退出条件：

| 条件 | 状态 |
|------|:---:|
| audit_cache FAIL=0 | ✅ |
| growth dup=0 | ✅ |
| factor gate PASS >= 3 | ❌ **0 PASS** |
| 候选池至少 1 个 PASS alpha | ❌ |

**判定：V4-r2 策略组装停止。**

原因不是数据质量问题（已全部修复），而是底层数据覆盖不足：
- income 数据仅覆盖 176 只股票，不足以支撑 alpha 因子
- growth_stability_8q_cs 仅 5 只股票，earnings_acceleration_cs 仅 1 只
- 即使 revenue/profit growth 有 176 只股票，IC 和 spread 指标仍不达标

### 10.4 全量测试

```text
792 passed, 12 skipped, 19 warnings
（1 失败为 test_data_pipeline 测试间状态污染，单独运行通过）
```

### 10.5 V4-r2 结论

**V4-r2 已完成数据质量修复（目标达成），但无法形成 alpha 策略（PASS=0）。**

下一步建议：
1. 扩展底层数据源（fina_indicator / income 覆盖更多 A 股标的）
2. 或接受当前数据覆盖下，V4 growth 因子不适合作为独立 alpha 来源
3. 考虑将 revenue_growth_ttm_cs / profit_growth_ttm_cs 降级为辅助/防御因子
4. 在数据源扩展后启动 V4-r3

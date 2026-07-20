# 开发方案完成后遗留问题整改日志

开始日期：2026-06-12
依据方案：`docs/development_audit_followup_fix_plan.md`

## 冻结基线

### 审核结论文档
- `docs/development_audit_fix_completion_review.md` — 保留为冻结证据

### 关键 run 记录

| 用途 | run_id | 说明 |
|------|--------|------|
| 最新 2026 YTD 候选 v2 | `20260101_20260605_top50_20260612_002534` | `factor_list` 已收敛到 5 个因子 |
| 旧 2023 候选 v2 (过期) | `20230101_20231231_top50_20260611_192453` | `factor_list` 包含旧弱因子，不得用于验收 |

### 冻结时状态

- `audit_cache --start 20170101 --end 20241231`: FAIL=1 (adj_factor_dedup)
- 候选 v2 冻结复验: 仅覆盖 2023 一年
- GO/NO-GO 文档: 基于不完整输入生成

### 旧弱因子 (存在于过期 run 中)

- `momentum_120_cs`
- `momentum_60_cs`
- `reversal_20_cs`
- `volatility_20_cs`

### 目标因子池 (候选 v2 正确配置)

- `bp_cs`
- `ep_cs`
- `pv_divergence_20_cs`
- `reversal_5_cs`
- `sp_cs`

---

## M0: 冻结当前状态 ✅

完成时间：2026-06-12

- 保留 `docs/development_audit_fix_completion_review.md`
- 创建 `docs/development_audit_followup_fix_plan.md`
- 创建本日志文件
- 记录关键 run_id

---

## M1: 修复 adj_factor 数据审计 ✅

完成时间：2026-06-12

### 代码变更
- `scripts/repair_adj_factor.py` — 重写：
  - `--years` 参数支持按年份筛选修复
  - 修复前输出重复键明细、来源文件、保留规则
  - 统一 schema（ts_code: string, trade_date: int32, adj_factor: float64, year: int32）
  - 临时目录 + 原子替换写入
  - 冲突检测：同键不同 adj_factor 值 → 拒绝修复并输出冲突明细
- `scripts/audit_cache.py` — `adj_factor_dedup` 增加 `--verbose` 明细输出（重复键、日期范围）
- `data/tushare_client.py` — adj_factor cache write 增加 `replace_partitions=True`（M1.6：防止碎片共存）

### 使用命令
```powershell
python -X utf8 scripts\repair_adj_factor.py --start 20170101 --end 20241231 --dry-run
python -X utf8 scripts\repair_adj_factor.py --start 20170101 --end 20241231 --years 2024
python -X utf8 scripts\audit_cache.py --start 20170101 --end 20241231 --verbose
```

---

## M2: 修复冻结验证旧 run 复用风险 ✅

完成时间：2026-06-12

### 代码变更
- `run_research.py`:
  - `_write_run_manifest` 增加 `factors_config_sha256`、`regime_config_sha256`、`factor_list_sha256`
  - 新增 `_compute_sha256()` 和 `_compute_factor_list_hash()` 工具函数
- `scripts/frozen_backtest_validation.py`:
  - `_manifest_matches` 增加 `check_hashes` 参数，校验配置内容哈希
  - CLI 新增 `--reuse-existing`、`--force` 标志
  - 默认行为改为不复用旧 run（fresh re-run）
  - `--skip-existing` 保留为向后兼容别名

### CLI 行为
- 默认: 不复用，全部重新执行
- `--reuse-existing`: 允许复用，但必须通过配置哈希和因子池校验
- `--force`: 强制忽略旧 run

---

## M3: 清理并准备重新生成候选 v2 复验产物 🔄

完成时间：2026-06-12（代码准备完成，运行待用户执行）

### 已完成
- 旧 `outputs/validation/candidate_v2/runs.csv` 已归档至 `archive/` 目录

### 待用户执行
```powershell
python -X utf8 scripts\frozen_backtest_validation.py --strategies E_candidate_v2 --out-dir outputs/validation/candidate_v2 --out-doc docs/candidate_v2_validation.md --force
```

---

## M4: 修复 GO/NO-GO 文档生成逻辑 ✅

完成时间：2026-06-12

### 代码变更
- `scripts/generate_go_nogo_decision.py`:
  - 新增 `check_completeness()` 函数，验证候选年份完整性
  - 新增 `--allow-incomplete` 参数（仅用于临时诊断）
  - 输入不完整时默认失败退出，带明确错误信息
  - 诊断版标题标记 `⚠️ INCOMPLETE`

### 完整性规则
- validation years: 2017-2024
- ytd years: 2026
- 候选策略: E_candidate_v2

---

## M5: 补齐测试与回归保护 ✅

完成时间：2026-06-12

### 新增测试文件
| 测试文件 | 覆盖点 | 用例数 |
|----------|--------|--------|
| `tests/test_repair_adj_factor.py` | 重复键去重、冲突值拒绝、schema 统一、dry-run、年份筛选 | 13 |
| `tests/test_audit_cache_adj_factor.py` | adj_factor_dedup 明细输出、FAIL/PASS 判定、verbose 模式 | 5 |
| `tests/test_frozen_backtest_validation.py` | SHA256 哈希、配置变更拒绝复用、hash 匹配允许复用、CLI 标志行为 | 15 |
| `tests/test_go_nogo_decision.py` | 年份完整性检查、缺失年份拒绝、--allow-incomplete、阈值评估 | 14 |

### 全量测试
```
570 passed, 8 warnings
```
（513 原有 + 57 新增，无回归）

---

# 正式验收收口整改日志

开始日期：2026-06-12
依据方案：`docs/development_audit_acceptance_closure_fix_plan.md`

## M1: 修复严格 run 复用保护 ✅

完成时间：2026-06-12

### 代码变更
- `scripts/frozen_backtest_validation.py`:
  - `_manifest_matches` 新增 `allow_legacy_manifest: bool = False` 参数
  - 严格模式（默认）：缺少必需哈希字段（`factors_config_sha256`、`factor_list_sha256`、regime 模式下的 `regime_config_sha256`）→ 直接返回 False
  - `allow_legacy_manifest=True` 时跳过哈希缺失检查（仅诊断用）
  - `_find_existing_run`、`_run_one` 传递 `allow_legacy_manifest` 参数
  - CLI 新增 `--allow-legacy-manifest` 标志，帮助文本明确警告不可用于正式验收
- `tests/test_frozen_backtest_validation.py`:
  - 旧 `test_no_hash_fields_in_manifest_allows_match` → 拆分为 3 个测试：
    - `test_no_hash_fields_rejected_by_default` — 严格模式拒绝无哈希 manifest
    - `test_legacy_manifest_allowed_with_flag` — `allow_legacy_manifest=True` 允许
    - `test_partial_hashes_rejected_in_strict_mode` — 部分缺失哈希也拒绝
  - `test_basic_match` 和 `test_config_hash_match_allows_reuse` 更新为包含完整哈希字段
- 测试: `22 passed` (frozen_backtest_validation)

### 验收命令
```powershell
python -X utf8 -m pytest tests\test_frozen_backtest_validation.py -q
python -X utf8 scripts\frozen_backtest_validation.py --strategies E_candidate_v2 --years 2023 --reuse-existing --out-dir outputs/validation/_reuse_probe --out-doc docs/_reuse_probe.md
```
预期：不得复用无哈希旧 run（应重新执行 2023）。

---

## M2: 清理 active 旧候选产物 ✅

完成时间：2026-06-12

### 已执行操作
- 旧 `outputs/validation/candidate_v2/runs.csv` → `archive/runs_20260612_192132.csv`
- 旧 `outputs/validation/candidate_v2/runs_partial.csv` → `archive/runs_partial_20260612_192132.csv`
- 旧 `docs/candidate_v2_validation.md` → `docs/candidate_v2_validation.expired_20260612_192138.md`
- 旧 `docs/go_nogo_decision.md` → `docs/go_nogo_decision.expired_20260612_192138.md`

### 验收
```text
Active runs.csv: 不存在 (False)
Active runs_partial.csv: 不存在 (False)
```

---

## M3-M5: 待用户执行

以下里程碑需要运行回测系统，无法由代码变更自动完成。

### M3: 执行候选 v2 完整冻结复验

前置条件：
1. M1 严格复用保护通过 ✅
2. M2 active 旧产物已清理 ✅
3. 数据审计 `FAIL=0`：需确认

```powershell
python -X utf8 scripts\audit_cache.py --start 20170101 --end 20241231 --verbose
python -X utf8 scripts\audit_cache.py --start 20260101 --end 20260605 --verbose
```

正式复验命令：
```powershell
python -X utf8 scripts\frozen_backtest_validation.py --strategies E_candidate_v2 --out-dir outputs/validation/candidate_v2 --out-doc docs/candidate_v2_validation.md --force
```

### M4: 重新生成 GO/NO-GO 文档

```powershell
python -X utf8 scripts\generate_go_nogo_decision.py
```

### M5: 最终回归验证

```powershell
python -X utf8 -m pytest -q
python -X utf8 scripts\audit_cache.py --start 20170101 --end 20241231 --verbose
python -X utf8 scripts\audit_cache.py --start 20260101 --end 20260605 --verbose
python -X utf8 scripts\generate_go_nogo_decision.py
```

---


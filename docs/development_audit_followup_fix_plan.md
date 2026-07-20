# 开发方案完成后遗留问题整改开发方案

生成日期：2026-06-12  
依据文档：`docs/development_audit_fix_completion_review.md`  
当前结论：上一轮整改有进展，但仍不满足正式验收。下一轮开发目标是补齐数据健康、冻结复验、run 可追溯和决策文档闭环，而不是继续调策略参数。

## 1. 背景

本轮审核确认了以下正向进展：

1. 单元测试通过：`513 passed, 8 warnings`。
2. 候选 v2 直接运行时，`configs/factors_candidate_v1.yaml + configs/regime_candidate_v2.yaml` 已真实穿透。
3. 最新 2026 YTD 候选 v2 run 的 `factor_list` 已收敛到目标 5 个因子：
   - `bp_cs`
   - `ep_cs`
   - `pv_divergence_20_cs`
   - `reversal_5_cs`
   - `sp_cs`

但正式验收仍被以下问题阻断：

1. 2017-2024 正式验证窗口 `audit_cache` 仍有 `adj_factor_dedup` FAIL。
2. 候选 v2 冻结复验只覆盖 2023 一年，没有覆盖完整验证窗口。
3. 当前 2023 候选 v2 run 仍包含旧弱因子，不能代表修复后的候选配置。
4. `frozen_backtest_validation.py` 默认复用旧 run，且 manifest 匹配不校验配置内容哈希。
5. `go_nogo_decision.md` 基于不完整输入生成，没有包含最新 2026 YTD 候选 v2 结果。

## 2. 总体目标

完成整改后，项目应满足：

| 目标 | 验收标准 |
|---|---|
| 数据健康闭环 | 2017-2024 `audit_cache` 无 FAIL |
| run 可追溯 | 每个冻结回测 run 能追溯配置路径、配置哈希和实际因子池 |
| 候选 v2 完整复验 | `E_candidate_v2` 覆盖 2017-2024 validation + 2026 ytd |
| 文档可信 | `candidate_v2_validation.md` 和 `go_nogo_decision.md` 全部由完整 runs.csv 自动生成 |
| 防回归 | 测试覆盖数据修复、配置哈希、旧 run 复用和文档输入完整性 |

非目标：

- 不在本轮继续搜索新因子或调 sleeve 参数。
- 不使用 2026 YTD 结果反向调参。
- 不将缺失年份的候选结果手工补入文档。

## 3. 问题清单与优先级

| ID | 优先级 | 问题 | 影响 | 责任模块 |
|---|---|---|---|---|
| P0-1 | P0 | `adj_factor` 在 2017-2024 窗口仍有重复键 | 正式验证数据健康未过关 | `data/parquet/adj_factor`、`scripts/repair_adj_factor.py`、`scripts/audit_cache.py` |
| P1-1 | P1 | 候选 v2 冻结复验不完整 | 无法判断跨年稳定性 | `scripts/frozen_backtest_validation.py`、`outputs/validation/candidate_v2` |
| P1-2 | P1 | 旧 run 复用逻辑不校验配置内容 | 修复后仍可能误用旧结果 | `scripts/frozen_backtest_validation.py`、run manifest 生成逻辑 |
| P1-3 | P1 | 2023 候选 run 使用旧因子池 | 候选 v2 文档证据失真 | `outputs/runs/*/run_manifest.json`、`outputs/validation/candidate_v2/runs.csv` |
| P1-4 | P1 | GO/NO-GO 文档输入不完整 | 自动生成文档仍可能误导 | `scripts/generate_go_nogo_decision.py` |
| P2-1 | P2 | 审计命令缺少机器可读明细 | 问题定位和复验效率低 | `scripts/audit_cache.py` |
| P2-2 | P2 | 当前目录不是 Git 仓库 | 无法用 diff 做变更边界审计 | 交付流程 |

## 4. 里程碑

### M0：冻结当前状态

目标：在修复前保留当前失败证据，避免后续无法解释指标变化。

任务：

1. 保留 `docs/development_audit_fix_completion_review.md`。
2. 将当前失败命令输出追加到整改记录或保存为日志文件。
3. 记录当前关键 run：
   - 最新 2026 YTD：`20260101_20260605_top50_20260612_002534`
   - 旧 2023 候选：`20230101_20231231_top50_20260611_192453`

产物：

- `docs/development_audit_followup_fix_plan.md`
- 后续建议新增 `docs/development_audit_followup_fix_log.md`

验收：

```powershell
Test-Path docs\development_audit_fix_completion_review.md
Test-Path docs\development_audit_followup_fix_plan.md
```

### M1：修复 2017-2024 `adj_factor` 数据审计

目标：让正式验证窗口数据健康先过关。

已知现象：

```text
python -X utf8 scripts\audit_cache.py --start 20170101 --end 20241231
Total: 12 checks | PASS=11 | WARN=0 | FAIL=1
adj_factor_dedup FAIL: 3 duplicate (ts_code, trade_date) rows
```

补充诊断显示重复集中在：

```text
ts_code: 000001.SZ
trade_date: 20240115
source: data/parquet/adj_factor/year=2024 下多个 parquet 片段与 data.parquet 共存
```

开发任务：

| 任务 | 文件/位置 | 说明 |
|---|---|---|
| M1.1 | `scripts/repair_adj_factor.py` | 增加只修复指定年份分区的能力，例如 `--years 2024` |
| M1.2 | `scripts/repair_adj_factor.py` | 修复前输出重复键、重复来源文件、保留规则 |
| M1.3 | `scripts/repair_adj_factor.py` | 写入时统一 schema，避免 `year` 分区字段类型冲突 |
| M1.4 | `scripts/repair_adj_factor.py` | 写入采用临时目录 + 原子替换，防止半写入 |
| M1.5 | `scripts/audit_cache.py` | 对 `adj_factor_dedup` 增加 `--verbose` 明细输出 |
| M1.6 | 数据层写入入口 | 排查产生碎片共存的写入路径，确保后续不会重复生成同类问题 |

建议实现规则：

1. 读取目标年份所有 parquet 文件。
2. 规范字段类型：
   - `ts_code`: string
   - `trade_date`: int 或统一可比较类型
   - `adj_factor`: float
3. 按 `(ts_code, trade_date)` 去重。
4. 同一键多条记录且 `adj_factor` 相同，保留一条。
5. 同一键多条记录但 `adj_factor` 不同，停止修复并输出冲突明细，不自动猜测。
6. 修复后目标年份分区只保留统一写入结果，避免 `data.parquet` 与碎片文件共存。

建议命令：

```powershell
python -X utf8 scripts\repair_adj_factor.py --start 20170101 --end 20241231 --dry-run
python -X utf8 scripts\repair_adj_factor.py --start 20170101 --end 20241231 --years 2024
python -X utf8 scripts\audit_cache.py --start 20170101 --end 20241231 --verbose
```

验收标准：

```text
Total: 12 checks | PASS=12 | WARN=0 | FAIL=0
```

最低要求：

```text
adj_factor_dedup PASS
adj_factor_coverage PASS
prices_adj_jumps PASS
```

### M2：修复冻结验证旧 run 复用风险

目标：配置变更后，验证脚本不能继续误用旧 run。

当前风险点：

`scripts/frozen_backtest_validation.py` 的 `_manifest_matches` 当前只匹配：

```text
start
end
top_n
strategy_mode
factors_config path
regime_config path
```

缺少：

```text
factors_config_hash
regime_config_hash
factor_list_hash
```

开发任务：

| 任务 | 文件 | 说明 |
|---|---|---|
| M2.1 | run manifest 生成逻辑 | 在 manifest 中写入配置文件 SHA256 |
| M2.2 | `scripts/frozen_backtest_validation.py` | `_manifest_matches` 校验配置哈希 |
| M2.3 | `scripts/frozen_backtest_validation.py` | 校验 manifest `factor_list` 与当前配置解析结果一致 |
| M2.4 | `scripts/frozen_backtest_validation.py` | 将 `--skip-existing` 改为显式选择，不允许默认静默复用 |
| M2.5 | `scripts/frozen_backtest_validation.py` | 增加 `--force` 或 `--no-reuse-existing`，强制重新跑 |
| M2.6 | tests | 增加配置变更后不复用旧 run 的回归测试 |

建议 manifest 字段：

```json
{
  "factors_config": "configs/factors_candidate_v1.yaml",
  "factors_config_sha256": "...",
  "regime_config": "configs/regime_candidate_v2.yaml",
  "regime_config_sha256": "...",
  "factor_list": ["bp_cs", "ep_cs", "pv_divergence_20_cs", "reversal_5_cs", "sp_cs"],
  "factor_list_sha256": "..."
}
```

建议 CLI 行为：

```text
默认：不复用旧 run，重新执行验证。
--reuse-existing：允许复用，但必须通过配置哈希和因子池校验。
--force：强制忽略旧 run。
```

如果为了兼容旧命令必须保留 `--skip-existing`：

1. 增加 `--no-skip-existing`。
2. 默认值改为 `False`，或在文档中明确该命令只是快速复查，不是正式验收。
3. 正式验收命令必须使用强制重跑口径。

验收测试建议：

```powershell
python -X utf8 -m pytest tests\test_frozen_backtest_validation.py -q
python -X utf8 -m pytest -q
```

测试用例至少覆盖：

1. 配置路径相同但内容哈希不同，旧 run 不匹配。
2. 配置哈希相同但 `factor_list` 不一致，旧 run 不匹配。
3. `--force` 时不查找旧 run。
4. `--reuse-existing` 时必须通过完整 manifest 校验。

### M3：清理并重新生成候选 v2 完整复验产物

目标：生成可信的 `E_candidate_v2` 完整冻结验证。

当前错误输入：

```text
outputs/validation/candidate_v2/runs.csv
```

问题：

- 只有 2023 一条。
- 该 2023 run 的 `factor_list` 包含旧弱因子：
  - `momentum_120_cs`
  - `momentum_60_cs`
  - `reversal_20_cs`
  - `volatility_20_cs`

开发任务：

| 任务 | 文件/位置 | 说明 |
|---|---|---|
| M3.1 | `outputs/validation/candidate_v2` | 将旧 `runs.csv` 标记为过期或移入归档目录 |
| M3.2 | `scripts/frozen_backtest_validation.py` | 使用修复后的强制重跑口径执行 `E_candidate_v2` |
| M3.3 | run manifest | 每个年份检查配置哈希和因子池 |
| M3.4 | `docs/candidate_v2_validation.md` | 重新生成完整候选验证文档 |
| M3.5 | 记录日志 | 保存每年 run_id 与关键指标 |

正式复验命令：

```powershell
python -X utf8 scripts\frozen_backtest_validation.py --strategies E_candidate_v2 --out-dir outputs/validation/candidate_v2 --out-doc docs/candidate_v2_validation.md --force
```

如果最终 CLI 采用 `--no-skip-existing`：

```powershell
python -X utf8 scripts\frozen_backtest_validation.py --strategies E_candidate_v2 --out-dir outputs/validation/candidate_v2 --out-doc docs/candidate_v2_validation.md --no-skip-existing
```

必须覆盖年份：

```text
2017
2018
2019
2020
2021
2022
2023
2024
2026
```

验收标准：

1. `outputs/validation/candidate_v2/runs.csv` 至少包含 9 条 `E_candidate_v2`。
2. 2017-2024 的 `sample` 全部为 `validation`。
3. 2026 的 `sample` 为 `ytd`。
4. 每条记录都有非空 `run_dir`、`annualized_excess_return`、`information_ratio`、`go_nogo_overall`。
5. 每个 run manifest 的 `factor_list` 不再包含旧弱因子。

检查命令：

```powershell
Import-Csv outputs\validation\candidate_v2\runs.csv | Group-Object strategy,sample | Format-Table Count,Name
Import-Csv outputs\validation\candidate_v2\runs.csv | Select-Object year,sample,strategy,run_dir,annualized_excess_return,information_ratio,go_nogo_overall | Format-Table -AutoSize
```

### M4：修复 GO/NO-GO 文档生成逻辑

目标：防止自动文档在输入不完整时生成看似可信的错误结论。

当前问题：

`docs/go_nogo_decision.md` 显示：

```text
E_candidate_v2 Pos Years: 1/1
2026 YTD 章节为空
```

开发任务：

| 任务 | 文件 | 说明 |
|---|---|---|
| M4.1 | `scripts/generate_go_nogo_decision.py` | 生成前检查候选验证年份完整性 |
| M4.2 | `scripts/generate_go_nogo_decision.py` | 若候选缺少年份，默认失败退出 |
| M4.3 | `scripts/generate_go_nogo_decision.py` | 增加 `--allow-incomplete` 仅用于临时诊断 |
| M4.4 | `scripts/generate_go_nogo_decision.py` | 2026 YTD 数据缺失时明确写入缺失原因或失败退出 |
| M4.5 | `docs/go_nogo_decision.md` | 用完整 `runs.csv` 重新生成 |

完整性规则：

```text
validation years required: 2017-2024
ytd years required: 2026
candidate required: E_candidate_v2
```

建议失败信息：

```text
E_candidate_v2 validation coverage incomplete:
missing validation years: 2017, 2018, 2019, 2020, 2021, 2022, 2024
missing ytd years: 2026
Refuse to generate GO/NO-GO decision without --allow-incomplete.
```

重新生成命令：

```powershell
python -X utf8 scripts\generate_go_nogo_decision.py
```

验收标准：

1. `docs/go_nogo_decision.md` 中 `E_candidate_v2` 不再显示 `1/1`。
2. 2026 YTD 章节包含候选 v2 最新结果。
3. 文档中的年度表、汇总表、门槛检查均可追溯到 `runs.csv`。
4. 输入不完整时脚本不生成最终决策文档。

### M5：补齐测试与回归保护

目标：让本轮问题不再靠人工审核才能发现。

建议新增或扩展测试：

| 测试文件 | 覆盖点 |
|---|---|
| `tests/test_repair_adj_factor.py` | 重复键去重、冲突值拒绝修复、schema 统一 |
| `tests/test_audit_cache_adj_factor.py` | `adj_factor_dedup` 明细输出和 FAIL/PASS 判定 |
| `tests/test_frozen_backtest_validation.py` | 配置哈希、因子池校验、强制重跑、不复用旧 run |
| `tests/test_go_nogo_decision.py` | 候选年份缺失时拒绝生成最终文档 |

必须通过：

```powershell
python -X utf8 -m pytest -q
```

可选增强：

```powershell
python -X utf8 scripts\check_env.py
python -X utf8 scripts\audit_cache.py --start 20170101 --end 20241231
python -X utf8 scripts\audit_cache.py --start 20260101 --end 20260605
```

## 5. 最终验收流程

完成开发后，按以下顺序验收：

### 5.1 环境检查

```powershell
python -X utf8 scripts\check_env.py
```

允许内存 WARN，但必须保证 Python 依赖和数据路径可用。

### 5.2 单元测试

```powershell
python -X utf8 -m pytest -q
```

标准：

```text
全部测试通过
```

### 5.3 历史验证窗口缓存审计

```powershell
python -X utf8 scripts\audit_cache.py --start 20170101 --end 20241231
```

标准：

```text
FAIL=0
```

### 5.4 2026 YTD 缓存审计

```powershell
python -X utf8 scripts\audit_cache.py --start 20260101 --end 20260605
```

标准：

```text
FAIL=0
```

允许 `factor_cs_quality` 因短样本产生 WARN，但必须在文档中说明。

### 5.5 候选 v2 完整冻结复验

```powershell
python -X utf8 scripts\frozen_backtest_validation.py --strategies E_candidate_v2 --out-dir outputs/validation/candidate_v2 --out-doc docs/candidate_v2_validation.md --force
```

标准：

```text
outputs/validation/candidate_v2/runs.csv contains:
- 2017-2024 validation
- 2026 ytd
```

### 5.6 决策文档生成

```powershell
python -X utf8 scripts\generate_go_nogo_decision.py
```

标准：

1. 不允许缺少年份时静默生成。
2. `E_candidate_v2` 汇总覆盖完整验证窗口。
3. 2026 YTD 章节非空。

## 6. GO / NO-GO 判定标准

整改通过不等于策略 GO。工程验收和策略判定分开：

### 6.1 工程验收 GO

必须全部满足：

1. `pytest` 通过。
2. 2017-2024 `audit_cache` 无 FAIL。
3. 候选 v2 复验覆盖完整年份。
4. 所有候选 run manifest 配置哈希和因子池校验通过。
5. GO/NO-GO 文档由完整数据自动生成。

### 6.2 策略 GO

继续沿用现有门槛：

| 指标 | 门槛 |
|---|---|
| 平均年化超额 | `> 2%` |
| 中位数年化超额 | `> 0%` |
| 正超额年份 | `>= 5` |
| 平均 IR | `> 0.30` |
| 最大单年超额亏损 | `> -10%` |

注意：

- 2026 YTD 只作为前瞻观察，不纳入 2017-2024 验证均值。
- 若 2026 YTD 与验证期明显反向，需要在文档中单独说明，不得据此调参。

## 7. 风险与回滚方案

### 7.1 数据修复风险

风险：

- 清理 parquet 碎片可能误删有效数据。
- 分区 schema 处理不一致可能导致读取失败。

控制：

1. 修复脚本必须先支持 `--dry-run`。
2. 修复前备份目标分区。
3. 修复后立即运行 `audit_cache`。
4. 若发现同键不同 `adj_factor`，停止并人工确认。

### 7.2 回测耗时风险

风险：

- 2017-2024 + 2026 完整复验耗时较长。

控制：

1. 先跑数据审计和脚本级测试。
2. 只在 P0 数据审计通过后启动完整复验。
3. 保存每年 partial CSV，失败时可定位到具体年份。

### 7.3 文档误导风险

风险：

- 自动文档若允许缺失输入，会再次生成 `1/1` 之类的误导性结论。

控制：

1. 默认严格校验年份覆盖。
2. 只有显式 `--allow-incomplete` 才允许生成诊断版。
3. 诊断版标题必须包含 `INCOMPLETE`。

## 8. 交付清单

开发完成后至少应交付：

| 交付物 | 要求 |
|---|---|
| `scripts/repair_adj_factor.py` | 支持 dry-run、年份选择、冲突检测、原子写入 |
| `scripts/audit_cache.py` | 能输出 `adj_factor` 重复明细 |
| `scripts/frozen_backtest_validation.py` | 支持配置哈希校验和强制重跑 |
| run manifest | 包含配置哈希与因子池哈希 |
| `scripts/generate_go_nogo_decision.py` | 缺失候选年份时拒绝生成正式文档 |
| `outputs/validation/candidate_v2/runs.csv` | 完整 2017-2024 + 2026 候选结果 |
| `docs/candidate_v2_validation.md` | 完整候选验证报告 |
| `docs/go_nogo_decision.md` | 完整 GO/NO-GO 决策报告 |
| tests | 覆盖本轮 P0/P1 问题 |

## 9. 建议执行顺序

1. 修复并验证 `adj_factor` 数据审计。
2. 加配置哈希和旧 run 复用保护。
3. 加 GO/NO-GO 输入完整性校验。
4. 补测试并跑全量测试。
5. 强制重跑候选 v2 完整冻结复验。
6. 重新生成 `candidate_v2_validation.md`。
7. 重新生成 `go_nogo_decision.md`。
8. 写最终整改完成报告。

## 10. 当前暂定判定

在完成本方案前，项目状态保持：

```text
工程验收：NO-GO
策略判定：等待完整复验后重新生成
```

不得使用当前 `outputs/validation/candidate_v2/runs.csv` 或当前 `docs/go_nogo_decision.md` 作为候选 v2 的最终验收依据。

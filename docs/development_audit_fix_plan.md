# 开发审核问题修复方案

生成日期：2026-06-11  
适用范围：`strategy_next_development_plan.md` 后续交付的审核修复  
当前结论：开发分析已基本完成，但正式验收未通过。必须先修复数据审计、候选配置穿透、一键验证和文档口径问题。

## 1. 总体目标

本方案目标不是继续调策略参数，而是把审核中暴露的工程和验证缺口补齐，让后续策略结论可以被稳定复现。

完成后的状态应满足：

1. 2017-2024 正式验证窗口 `audit_cache` 无 FAIL。
2. 候选因子池和 regime sleeve 因子池口径一致。
3. 候选 v2 能通过统一脚本一键复验。
4. `go_nogo_decision.md` 指标由脚本生成或可追溯到 run_id。
5. 旧的 `outputs/validation_report.md` 不再与当前结论冲突。
6. 修复后重新给出候选 v2 的最终 GO / NO-GO。

## 2. 问题清单

| ID | 优先级 | 问题 | 影响 | 当前判断 |
|---|---|---|---|---|
| P0-1 | P0 | 2017-2024 `audit_cache` 失败 | 正式验证窗口数据健康未通过 | 阻塞验收 |
| P1-1 | P1 | `factors_candidate_v1` 清理未穿透到 `regime_candidate_v2` | 候选实际运行因子池与文档不一致 | 阻塞候选解释 |
| P1-2 | P1 | 候选 v2 未纳入一键冻结验证脚本 | 不能一键复现候选验证 | 阻塞验证闭环 |
| P1-3 | P1 | `outputs/validation_report.md` 仍是旧 FAIL | 文档状态冲突 | 阻塞状态汇报 |
| P2-1 | P2 | `go_nogo_decision.md` 个别数字不一致 | 影响可信度 | 需修正 |
| P2-2 | P2 | 2026 YTD 候选 v2 结果未写入决策文档 | 观察样本缺失 | 需补充 |

## 3. P0-1：修复 2017-2024 缓存审计失败

### 3.1 现象

审核命令：

```powershell
python scripts/audit_cache.py --start 20170101 --end 20241231
```

当前结果：

```text
Total: 12 checks | PASS=9 | WARN=0 | FAIL=3
```

失败项：

| 检查项 | 失败内容 |
|---|---|
| `adj_factor_dedup` | 447 duplicate `(ts_code, trade_date)` rows |
| `adj_factor_coverage` | adj_factor trade-day coverage=1.2% (23/1943 days) |
| `prices_adj_jumps` | 6 extreme daily returns >5x, 8 extreme weekly returns >10x |

### 3.2 风险

该问题属于正式验证窗口的数据层硬失败。即使 Phase2 能跑出结果，2017-2024 的跨年验证也不能被视为完全可信。

可能影响：

- 复权价格污染导致个别股票收益异常。
- 因子计算、forward return、持仓收益出现虚假跳变。
- 候选 v2 与 D 的年度对比被数据异常扰动。

### 3.3 根因假设

优先排查以下原因：

1. `adj_factor` 分区写入时未合并去重，导致同一 `(ts_code, trade_date)` 重复。
2. 早期短窗口重建或 smoke 写入覆盖了宽窗口缓存。
3. `adj_factor` 只缓存了部分执行日，而不是完整交易日。
4. `prices_adj` 使用了不完整或重复的复权因子，产生极端跳变。

### 3.4 修复任务

| ID | 任务 | 文件/命令 | 产物 |
|---|---|---|---|
| P0-1.1 | 定位重复 `adj_factor` 明细 | 新增临时诊断或扩展 `audit_cache.py` | 重复股票、日期、分区清单 |
| P0-1.2 | 定位 `prices_adj` 极端跳变明细 | 扩展 `audit_cache.py` 输出异常股票和日期 | jumps 明细 CSV |
| P0-1.3 | 修复 `adj_factor` 去重逻辑 | `data/panel_loader.py` 或修复脚本 | `(ts_code, trade_date)` 唯一 |
| P0-1.4 | 必要时重建 2017-2024 `adj_factor` 和 `prices_adj` | `run_research.py phase0` 或修复脚本 | 覆盖率恢复 |
| P0-1.5 | 重新审计 | `audit_cache.py` | FAIL=0 |

### 3.5 建议实现

优先新增一个只读诊断命令，避免直接破坏缓存：

```powershell
python scripts/audit_cache.py --start 20170101 --end 20241231 --detail
```

如果 `audit_cache.py` 暂不支持 `--detail`，建议新增输出：

- `outputs/price_quality_failures/adj_factor_duplicates_2017_2024.csv`
- `outputs/price_quality_failures/adj_factor_missing_dates_2017_2024.csv`
- `outputs/price_quality_failures/prices_adj_extreme_jumps_2017_2024.csv`

重复修复规则：

1. 按 `(ts_code, trade_date)` 排序。
2. 同键重复时保留最新写入或非空字段最多的一条。
3. 重新派生 `year/month` 分区列。
4. 以分区合并写入方式替换，避免短窗口覆盖宽窗口。

### 3.6 验收标准

必须通过：

```powershell
python scripts/audit_cache.py --start 20170101 --end 20241231
```

目标结果：

```text
FAIL=0
adj_factor_dedup PASS
adj_factor_coverage PASS
prices_adj_jumps PASS
```

同时建议复核：

```powershell
python scripts/audit_cache.py --start 20260101 --end 20260605
```

目标：2026 YTD 仍无 FAIL。

## 4. P1-1：修复候选因子池未穿透问题

### 4.1 现象

`configs/factors_candidate_v1.yaml` 中 `enabled_factors` 为：

```yaml
enabled_factors:
  - ep_cs
  - bp_cs
  - sp_cs
  - reversal_5_cs
  - pv_divergence_20_cs
```

但 `configs/regime_candidate_v2.yaml` 中仍直接引用：

```yaml
reversal_20_cs
momentum_60_cs
momentum_120_cs
volatility_20_cs
```

实际运行日志显示：

```text
Regime factor pool: 9 total declared, 9 cached, 0 missing
```

### 4.2 影响

当前 v2 结果不是“清理后 5 因子池”的结果，而是 9 个 regime sleeve 因子的结果。

这会影响以下文档结论：

- `candidate_freeze_log.md` 中 “因子清理” 的表述。
- `go_nogo_decision.md` 中对 v2 失败原因的解释。
- `factor_signal_alignment.md` 中 “建议立即执行的配置变更” 与实际候选不一致。

### 4.3 需要先做的设计决策

必须先选择一种语义：

| 方案 | 说明 | 优点 | 缺点 | 推荐 |
|---|---|---|---|---|
| A | regime mode 严格遵守 `enabled_factors`，sleeve 中引用 disabled 因子时报错或跳过 | 口径一致 | 可能影响旧配置兼容 | 推荐 |
| B | regime mode 以 sleeve 声明为准，允许绕过 `enabled_factors` | 兼容当前实现 | 文档必须明确，容易误用 | 可接受 |
| C | 保留绕过，但新增显式白名单 `allow_disabled_in_sleeves` | 灵活 | 配置复杂 | 次选 |

建议采用方案 A：候选配置应严格遵守 `enabled_factors`，避免文档和运行不一致。

### 4.4 修复任务

| ID | 任务 | 文件 | 产物 |
|---|---|---|---|
| P1-1.1 | 明确 regime factor pool 构建规则 | `run_research.py` / alpha 相关模块 | 代码注释和测试 |
| P1-1.2 | 增加配置一致性检查 | `configs/factor_config.py` 或新 validator | disabled 因子不得进入 sleeve |
| P1-1.3 | 修正 `regime_candidate_v2.yaml` | `configs/regime_candidate_v2.yaml` | 真正清理后的 sleeve |
| P1-1.4 | 修正 `regime_candidate_v3.yaml` | `configs/regime_candidate_v3.yaml` | 同步语义 |
| P1-1.5 | 补测试 | `tests/test_regime_candidate_config.py` | 防止回归 |

### 4.5 推荐的 v2 sleeve 修正版

如果目标是真清理因子池，建议先用最小修正版：

```yaml
strategy_sleeves:
  reversal:
    factors:
      - reversal_5_cs
      - pv_divergence_20_cs

  momentum:
    factors:
      - pv_divergence_20_cs

  defensive:
    factors:
      - ep_cs
      - bp_cs

  value:
    factors:
      - ep_cs
      - bp_cs
      - sp_cs

  volume_price:
    factors:
      - pv_divergence_20_cs
```

注意：

- `defensive` 暂用 value 因子只是过渡方案，真正修复需要质量因子。
- 如果 sleeve 只有一个因子，应降低或关闭过强的 `coverage_gate`，否则容易出现空 sleeve。

### 4.6 验收标准

运行候选 v2 后，manifest 中 `factor_list` 不应包含 disabled 因子：

```text
reversal_20_cs
momentum_60_cs
momentum_120_cs
volatility_20_cs
volatility_60_cs
macd_12_26_9_cs
rsi_14_cs
```

检查命令建议：

```powershell
python -X utf8 run_research.py phase2 --start 20260101 --end 20260605 --top-n 50 --no-recompute --factors-config configs/factors_candidate_v1.yaml --strategy-mode regime --regime-config configs/regime_candidate_v2.yaml
```

然后检查：

```powershell
Get-Content outputs/latest_run_manifest.json
```

目标：

```json
"factor_list": ["bp_cs", "ep_cs", "pv_divergence_20_cs", "reversal_5_cs", "sp_cs"]
```

## 5. P1-2：将候选 v2 纳入一键冻结验证脚本

### 5.1 现象

`scripts/frozen_backtest_validation.py` 当前只注册：

- `A_5reversal`
- `B_dynamic`
- `C_regime_baseline`
- `D_regime_overlay`

没有候选 v2。

### 5.2 影响

候选 v2 的验证结果来自单年 run 收集，而不是统一脚本输出。后续难以复现、对比和更新。

### 5.3 修复任务

| ID | 任务 | 文件 | 产物 |
|---|---|---|---|
| P1-2.1 | 在验证脚本注册候选 v2 | `scripts/frozen_backtest_validation.py` | `E_candidate_v2` |
| P1-2.2 | 支持单独跑候选策略 | 同上 | `--strategies E_candidate_v2` |
| P1-2.3 | 输出候选专用报告 | docs 或 outputs | candidate validation report |
| P1-2.4 | 增加 run_id 追溯字段 | report writer | 每年可追溯 |

### 5.4 建议实现

新增策略：

```python
"E_candidate_v2": Strategy(
    name="E_candidate_v2",
    label="Candidate v2: factors_candidate_v1 + regime_candidate_v2",
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

建议不要覆盖原 A/B/C/D 报告，新增候选输出目录：

```powershell
python scripts/frozen_backtest_validation.py --strategies E_candidate_v2 --out-dir outputs/validation/candidate_v2 --out-doc docs/candidate_v2_validation.md
```

### 5.5 验收标准

必须能一键生成：

- `outputs/validation/candidate_v2/runs.csv`
- `docs/candidate_v2_validation.md`

且覆盖：

- 2017-2024 正式验证
- 2026 YTD 观察

## 6. P1-3：处理旧 `validation_report.md`

### 6.1 现象

当前文件：

```text
outputs/validation_report.md
Generated: 2026-06-05 15:38
Overall: FAIL
audit_cache: FAIL
```

### 6.2 影响

该文件会与最新文档中的“验证链路可复现”冲突。

### 6.3 修复路径

两个可选方案：

| 方案 | 做法 | 适用情况 |
|---|---|---|
| A | 修复数据审计后重新运行 validate，刷新该文件 | 推荐 |
| B | 明确标记该文件为旧报告，不作为当前状态 | 如果 validate 暂时成本太高 |

### 6.4 推荐方案

优先方案 A：

```powershell
python run_research.py validate --start 20170101 --end 20171231
```

若要覆盖 2017-2024，应新增或使用分段验证脚本，不建议一次性全窗口跑到内存风险过高。

如果暂时不能跑 validate，则在 `docs/go_nogo_decision.md` 和 README 中明确：

```text
outputs/validation_report.md is stale and reflects 2026-06-05 pre-fix status.
Current candidate validation is tracked in docs/candidate_v2_validation.md.
```

### 6.5 验收标准

最终必须满足其一：

1. `outputs/validation_report.md` 已刷新且无 FAIL。
2. 文档明确声明该报告已过期，并指向新验证报告。

## 7. P2-1：修正 GO/NO-GO 指标表

### 7.1 现象

`docs/go_nogo_decision.md` 中：

```text
平均 IR: v2 = -0.58
```

复核 2017-2024 run metrics 后：

```text
平均 IR: v2 ≈ -0.67
```

### 7.2 修复任务

| ID | 任务 | 文件 | 产物 |
|---|---|---|---|
| P2-1.1 | 用脚本重算 v2 指标 | 新脚本或 notebook | 聚合表 |
| P2-1.2 | 更新 `go_nogo_decision.md` | docs | 修正 IR |
| P2-1.3 | 每行补充 run_id | docs | 可追溯 |

### 7.3 推荐实现

新增脚本：

```text
scripts/generate_go_nogo_decision.py
```

输入：

- `outputs/validation/candidate_v2/runs.csv`
- `outputs/validation/frozen_backtest/runs.csv`

输出：

- `docs/go_nogo_decision.md`

原则：

- 不手工维护关键指标。
- 所有表格从 metrics 生成。
- 每个年度保留 run_id 或 run_dir。

## 8. P2-2：补充 2026 YTD 候选 v2 结果

### 8.1 已补跑结果

候选 v2 2026 YTD：

| 指标 | 值 |
|---|---:|
| 年化收益 | 4.20% |
| 年化超额 | 4.58% |
| IR | 0.253 |
| 最大回撤 | -14.23% |
| 平均换手 | 41.64% |
| 样本数 | 20 |
| 状态 | NO-GO / UNSTABLE |

### 8.2 文档修复

在 `docs/go_nogo_decision.md` 增加 2026 YTD 小节：

```text
2026 YTD is positive but unstable. It is not counted in validation gates.
```

并明确：

- 2026 不进入 2017-2024 验证均值。
- 2026 不能用于调参。
- 2026 只能作为前瞻观察。

## 9. 修复后的复验流程

### 9.1 最小复验流程

```powershell
python scripts/check_env.py
pytest -q
python scripts/migrate_factor_cache.py --dry-run
python scripts/audit_cache.py --start 20170101 --end 20241231
python scripts/audit_cache.py --start 20260101 --end 20260605
python scripts/frozen_backtest_validation.py --strategies E_candidate_v2 --out-dir outputs/validation/candidate_v2 --out-doc docs/candidate_v2_validation.md
python scripts/generate_go_nogo_decision.py
```

### 9.2 完整复验流程

完整复验应额外包含：

```powershell
python scripts/frozen_backtest_validation.py --out-dir outputs/validation/frozen_backtest --out-doc docs/frozen_backtest_validation.md
python scripts/frozen_backtest_attribution.py
python run_research.py validate --start 20170101 --end 20171231
```

是否运行完整 validate 取决于内存和时间预算。

## 10. 责任边界和完成定义

### 10.1 本轮修复完成定义

必须满足：

- P0-1 修复，2017-2024 audit 无 FAIL。
- P1-1 修复，候选实际 factor_list 与配置语义一致。
- P1-2 修复，候选 v2 可一键复验。
- P1-3 修复，旧 validation report 不再造成冲突。
- P2-1/P2-2 修复，GO/NO-GO 文档数字一致且含 2026 YTD。

### 10.2 完成后允许推进的工作

完成上述修复后，可以进入：

1. 因子池重建 Phase C。
2. 质量因子和新动量因子的 PIT 实现。
3. fast-vs-Phase2 组合构建修复。

### 10.3 未完成前禁止推进的工作

在 P0/P1 修复前，不建议：

- 宣布候选 v2 正式验收。
- 开始新一轮 allocator 参数网格。
- 基于当前 2017-2024 指标做生产决策。
- 将当前 `go_nogo_decision.md` 作为最终结论。

## 11. 推荐执行顺序

1. **先修数据。** 定位并修复 `adj_factor` 和 `prices_adj` 异常。
2. **再修配置语义。** 明确 regime sleeve 是否受 `enabled_factors` 约束。
3. **再修验证脚本。** 把候选 v2 纳入一键验证。
4. **再重跑候选。** 生成 candidate_v2 独立 runs 和报告。
5. **最后修文档。** 用脚本生成 GO/NO-GO，避免手工数字不一致。

## 12. 当前建议判断

当前不建议继续调策略。  
当前最重要的开发动作是：

```text
修数据审计 → 修配置穿透 → 修一键复验 → 重建 GO/NO-GO
```

只有这条链路打通后，后续因子池重建和策略迭代才有稳固地基。

# Strategy V3 开发方案

生成日期：2026-06-13  
前置文档：`docs/strategy_next_development_plan.md`、`docs/go_nogo_decision.md`、`docs/development_audit_final_acceptance_review.md`

## 1. 背景与现状

### 1.1 工程基础设施

工程验收已通过（GO），具备稳定开发条件：

```text
pytest:              572 passed, 8 warnings
2017-2024 audit:      PASS=11 WARN=1 FAIL=0
2026 YTD audit:       PASS=11 WARN=1 FAIL=0
严格复用保护:         必修哈希字段，无哈希旧 manifest 拒绝复用
文档生成完整性检查:    缺失年份拒绝生成正式文档
候选产物追溯:         manifest SHA256 + factor_list 哈希
```

### 1.2 策略状态（全部 NO-GO）

| Strategy | 平均年化超额 | 正超额年份 | 平均 IR | 判定 |
|----------|:----------:|:--------:|:------:|:----:|
| A_5reversal | -10.9% | 2/8 | -1.00 | ❌ |
| B_dynamic | -12.8% | 1/8 | -1.23 | ❌ |
| C_regime_baseline | -8.1% | 2/8 | -0.90 | ❌ |
| D_regime_overlay | -6.4% | 2/8 | -0.73 | ❌ |
| **E_candidate_v2** | **-1.2%** | **3/8** | **-0.21** | ❌ |

### 1.3 关键观察

E_candidate_v2（`factors_candidate_v1.yaml` + `regime_candidate_v2.yaml`）是当前最佳候选，相对 D 有明显改善：

| 对比 | 验证年胜率 | 平均超额差 |
|------|:--------:|:--------:|
| E2 - D | 6/8 | +5.2% |
| E2 - C | 6/8 | +6.9% |

但仍未通过策略门槛：平均超额 -1.2%（需 >2%）、正超额仅 3/8（需 ≥5）、2017 年超额亏损 -15.8%（需 >-10%）。

E_candidate_v2 的改善来自两个变化：
1. 因子池收窄到 5 个通过 IC 门槛的因子（bp_cs, ep_cs, sp_cs, reversal_5_cs, pv_divergence_20_cs）
2. Regime sleeve 映射调整（降低 reversal、提高 value/volume_price）

### 1.4 什么是 V3

V3 在 V2 基础上增加 **sleeve_performance_overlay**，配置已存在于 `configs/regime_candidate_v3.yaml`。

V3 与 V2 的差异：

| 维度 | V2 (regime_candidate_v2) | V3 (regime_candidate_v3) |
|------|--------------------------|--------------------------|
| sleeve_performance_overlay | 未启用 | **启用**，strength=0.40 |
| fundamental_max_stale | 63 交易日 | **45 交易日** |
| 其他配置 | 与 V2 相同 | 与 V2 相同 |

V3 的经济逻辑：regime router 根据市场状态分配 sleeve 权重，performance overlay 在此基础上根据各 sleeve **近期实际 IC 质量**进行第二层调权——"优者多得、劣者少得"。两层调节联合，理论上可以在 regime 判断正确但 sleeve 近期 alpha 衰减时更快收缩，或在 regime 判断保守但某 sleeve 近期持续有效时适度放大。

## 2. 总体目标

将 V3（`regime_candidate_v3.yaml` + `factors_candidate_v1.yaml`）从"已有配置但未验证"推进到"可被正式验证的候选"，并明确其相对 V2 是否有实质改善。

完成后必须回答：

1. V3 相对 V2 在 2017-2024 验证窗口是否有改善？
2. 改善来自 performance overlay 的哪部分机制（ICIR 调权 vs hit rate 调权，哪些 sleeve 受益，哪些受损）？
3. 2026 YTD 是否与验证期方向一致？
4. V3 是否达到策略 GO 门槛？若未达到，差距在哪里？

不再处理：

- 新因子开发（V3 沿用 factors_candidate_v1 的 5 因子池）
- Regime router 参数搜索（V3 沿用 V2 的 regime 映射）
- Sleeve 定义变更（V3 沿用 V2 的 sleeve 定义）
- 用 2026 YTD 结果反向调参

## 3. 配置定义

### 3.1 V3 策略入口

```powershell
python run_research.py phase2 \
  --factors-config configs/factors_candidate_v1.yaml \
  --strategy-mode regime \
  --regime-config configs/regime_candidate_v3.yaml \
  --top-n 50 --no-recompute \
  --start YYYYMMDD --end YYYYMMDD
```

### 3.2 V3 因子池（与 V2 相同）

```text
bp_cs
ep_cs
pv_divergence_20_cs
reversal_5_cs
sp_cs
```

### 3.3 Performance Overlay 参数

| 参数 | 值 | 说明 |
|------|----|------|
| lookback_months | 6 | 评估窗口 |
| horizon | 5 | 调仓频率（周） |
| icir_weight | 0.70 | ICIR 占质量评分 70% |
| hit_rate_weight | 0.30 | 命中率占 30% |
| strength | 0.40 | 保守强度（网格最佳为 0.50） |
| multiplier_min | 0.60 | 最差 sleeve 不低于 60% 基准权重 |
| multiplier_max | 1.60 | 最优 sleeve 不高于 160% 基准权重 |

### 3.4 V3 策略名

在 `frozen_backtest_validation.py` 中新增：

```python
"F_candidate_v3": Strategy(
    name="F_candidate_v3",
    label="Candidate v3: factors_candidate_v1 + regime_candidate_v3 (perf overlay)",
    args=(
        "--factors-config", "configs/factors_candidate_v1.yaml",
        "--strategy-mode", "regime",
        "--regime-config", "configs/regime_candidate_v3.yaml",
    ),
),
```

## 4. 里程碑

### M0：V3 策略注册与快速冒烟

目标：在正式全窗口复验前，先跑单年确保配置可运行、不报错。

任务：

| ID | 任务 | 说明 |
|----|------|------|
| M0.1 | 在 `frozen_backtest_validation.py` 注册 `F_candidate_v3` | 与 E_candidate_v2 共用 `factors_candidate_v1.yaml` |
| M0.2 | 单年冒烟测试（2023） | `--strategies F_candidate_v3 --years 2023 --force` |
| M0.3 | 确认 manifest 写入完整哈希 | 同 V2 标准 |

冒烟命令：

```powershell
python -X utf8 scripts\frozen_backtest_validation.py --strategies F_candidate_v3 --years 2023 --force --out-dir outputs/validation/candidate_v3_smoke --out-doc docs/_v3_smoke.md
```

验收：

- 2023 单年运行无报错，退出码 0
- `run_manifest.json` 包含 `factors_config_sha256`、`regime_config_sha256`、`factor_list_sha256`
- `factor_list` 为 5 个目标因子

### M1：V3 完整冻结复验

目标：生成 V3 在 2017-2024 验证窗口 + 2026 YTD 的完整结果。

前置条件：M0 通过。

正式命令：

```powershell
python -X utf8 scripts\frozen_backtest_validation.py --strategies F_candidate_v3 --out-dir outputs/validation/candidate_v3 --out-doc docs/candidate_v3_validation.md --force
```

覆盖年份：

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

产物：

```text
outputs/validation/candidate_v3/runs.csv
outputs/validation/candidate_v3/runs_partial.csv
docs/candidate_v3_validation.md
outputs/validation/candidate_v3/logs/*.log
```

验收：

- `runs.csv` 包含 9 条 `F_candidate_v3` 记录（8 validation + 1 ytd）
- 所有 `run_dir` 非空且目录存在
- manifest 哈希全部非空
- factor_list 全部为 5 个目标因子，无旧弱因子
- 2017-2024 audit `FAIL=0`

### M2：V3 vs V2 对比分析

目标：量化 V3 相对 V2 的改善（或恶化），解释 performance overlay 的边际贡献。

任务：

| ID | 任务 | 说明 |
|----|------|------|
| M2.1 | 合并 V2 和 V3 的 runs.csv | 跨策略对比 |
| M2.2 | 计算 V3 - V2 年度超额差 | 每年改善方向 |
| M2.3 | 统计 V3 相对 V2 的正超额年胜率 | 稳定性判断 |
| M2.4 | 比较 IR、回撤、换手、成本 | 综合质量判断 |
| M2.5 | 如果 V3 在任一年明显劣于 V2，定位原因 | 失败归因 |

对比命令：

```powershell
# 合并两个 runs.csv
python -c "
import pandas as pd
v2 = pd.read_csv('outputs/validation/candidate_v2/runs.csv')
v3 = pd.read_csv('outputs/validation/candidate_v3/runs.csv')
both = pd.concat([v2, v3], ignore_index=True)
piv = both.pivot_table(index='year', columns='strategy', values='annualized_excess_return')
piv['F3_minus_E2'] = piv['F_candidate_v3'] - piv['E_candidate_v2']
print(piv[['E_candidate_v2', 'F_candidate_v3', 'F3_minus_E2']].to_markdown())
"
```

验收：

- 明确 V3 相对 V2 在每年是改善还是恶化
- 如果 V3 在 5+/8 年改善，则认为 overlay 有正面贡献
- 如果 V3 在多数年恶化，写出失败假设并停止推进该路线

### M3：V3 GO/NO-GO 决策

目标：用完整 V3 验证结果生成正式决策文档，判断 V3 是否达到策略 GO 门槛。

前置条件：M1、M2 通过。

将 V3 的 `runs.csv` 纳入 GO/NO-GO 生成流程：

```powershell
python -X utf8 scripts\generate_go_nogo_decision.py --runs outputs/validation/frozen_backtest/runs.csv outputs/validation/candidate_v2/runs.csv outputs/validation/candidate_v3/runs.csv
```

V3 策略 GO 门槛（与 V2 相同）：

| 指标 | 门槛 |
|------|:----:|
| 2017-2024 平均年化超额 | > 2% |
| 中位数年化超额 | > 0% |
| 正超额年份 | ≥ 5/8 |
| 平均 IR | > 0.30 |
| 最大单年超额亏损 | > -10% |

验收：

- `docs/go_nogo_decision.md` 包含 `F_candidate_v3`
- 文档标题无 `INCOMPLETE`
- V3 的 GO/NO-GO 判定明确

### M4：V3 诊断归因（条件执行）

仅当 V3 仍为 NO-GO 且差距缩小（如平均超额在 -1% 到 +2% 之间）时执行。

目标：定位 V3 剩余负超额的来源，为 V4 提供方向。

任务：

| ID | 任务 | 说明 |
|----|------|------|
| M4.1 | V3 失败年份月度收益拆解 | 确认负超额集中在哪些月份 |
| M4.2 | V3 各 sleeve 的 overlay multiplier 时间序列 | 检查 overlay 是否在正确方向调权 |
| M4.3 | V3 vs V2 的换手和成本对比 | 确认 overlay 是否增加不必要的交易 |
| M4.4 | 如果 overlay 在多数年份 multiplier 接近 1.0，说明 strength=0.40 太保守 | 为 V4 提供 strength 调整方向 |

## 5. GO / NO-GO 判定流程

```text
M1 完整复验
    │
    ▼
V3 结果与 V2 对比 (M2)
    │
    ├── V3 在多数年份不优于 V2 → 停止 overlay 路线，回归因子池重建
    │
    └── V3 在多数年份优于 V2
         │
         ▼
    GO/NO-GO 决策 (M3)
         │
         ├── 达到策略 GO 门槛 → 进入 Phase 3/风险约束组合构建
         │
         ├── 接近门槛且差距缩小 → 诊断归因 (M4)，为 V4 提供方向
         │
         └── 差距仍大 → 停止 overlay 路线，回归因子池重建
```

## 6. 风险与回滚

### 6.1 Performance overlay 过拟合风险

Overlay 的 strength=0.40 是基于 2025 网格搜索选出的保守值（最佳为 0.50），但仍存在对 2025 过拟合的风险。

控制：
- V3 在 2017-2024 全部年份的表现才是真实证据
- 如果 2023/2025（诊断集）改善但 2017-2022 恶化，立即标记为过拟合

### 6.2 回滚方案

- 如果 V3 不优于 V2，回退到 V2 基线，转向因子池重建（Phase C of `strategy_next_development_plan.md`）
- V3 产物和配置保留为研究记录，不作为正式候选

### 6.3 资源

- 全窗口复验预计耗时 ~90 分钟（与 V2 复验经验一致）
- 建议在无其他重回测占用时执行

## 7. 交付清单

| 交付物 | 要求 |
|--------|------|
| `scripts/frozen_backtest_validation.py` | 新增 `F_candidate_v3` 策略注册 |
| `outputs/validation/candidate_v3/runs.csv` | 9 条 V3 记录 |
| `docs/candidate_v3_validation.md` | V3 验证报告 |
| `docs/candidate_v3_vs_v2_comparison.md` | V3 vs V2 对比分析 |
| `docs/go_nogo_decision.md` | 更新为包含 V3 |
| `docs/strategy_v3_development_log.md` | V3 开发日志 |

## 8. 执行顺序

```text
1. M0: 注册 F_candidate_v3 + 单年冒烟 (2023)
2. M0: 验证 manifest 哈希
3. M1: 全窗口冻结复验 (2017-2024 + 2026)
4. M1: 验证 runs.csv 完整性 + manifest 哈希 + 因子池
5. M2: V3 vs V2 对比分析
6. M3: GO/NO-GO 决策
7. M4: (条件) 诊断归因
```

---

当前工程状态：**工程验收 GO**。V3 开发在稳定基础设施上进行，风险可控。

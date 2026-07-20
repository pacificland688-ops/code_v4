# 策略开发综合问题清单

> 生成日期：2026-07-12
>
> 数据来源：覆盖 Phase 2 至 Phase 5 全部验证口径、策略 alpha 失败诊断、V4 失败来源矩阵、光刻胶恐慌修复分析、以及各阶段 gate 评估结果
>
> 关联文档：
> - `docs/strategy_alpha_failure_report.md` — 策略 alpha 失败诊断报告
> - `docs/strategy_failure_source_matrix_v4.md` — V4 策略失败来源矩阵
> - `docs/photoresist_primary_5d_analysis_and_issues.md` — 光刻胶恐慌修复问题清单
> - `outputs/phase5_failure_diagnostics.md` — Phase 5 失败诊断
> - `outputs/metrics_summary.json` — 全阶段指标汇总
> - `docs/strategy_alpha_failure_diagnosis_development_plan.md` — alpha 诊断开发计划

---

## 1. 文档目的

本文档汇总了从 2026 年 6 月至 7 月对 q_project 策略系统进行系统性分析后识别出的全部问题，涵盖：

- **策略层面**：alpha 因子质量、sleeve 聚合效率、regime router 映射
- **组合构建层面**：优化器稳定性、成本拖累、信号穿透
- **数据基础设施层面**：价格缓存、因子覆盖、数据质量
- **方法论层面**：验证框架设计、统计 power、治理机制

每个问题均附带严重程度、证据来源和当前处理状态。

---

## 2. 严重程度定义

| 级别 | 符号 | 定义 |
|------|:----:|------|
| 阻断级 | 🔴 | 不解决则策略无法通过任何 gate，或数据完全不可用 |
| 重大 | 🟠 | 影响结论可靠性，可能导致虚假通过或虚假失败 |
| 中等 | 🟡 | 影响开发效率或分析精度，但不直接导致错误决策 |
| 轻微 | 🔵 | 优化项，不阻塞当前里程碑 |

---

## 3. 问题总览矩阵

### 3.1 按维度统计

| 维度 | 🔴 阻断 | 🟠 重大 | 🟡 中等 | 🔵 轻微 | 合计 |
|------|:------:|:------:|:------:|:------:|:----:|
| Alpha / 因子质量 | 3 | 4 | 2 | 0 | 9 |
| Sleeve / 聚合 | 0 | 2 | 1 | 0 | 3 |
| Regime Router | 0 | 1 | 2 | 0 | 3 |
| 组合构建 / 优化器 | 2 | 2 | 1 | 0 | 5 |
| 数据基础设施 | 3 | 2 | 1 | 0 | 6 |
| 验证框架 / 方法论 | 2 | 5 | 3 | 1 | 11 |
| **合计** | **10** | **16** | **10** | **1** | **37** |

### 3.2 按优先级排序（Top 10）

| 优先级 | 编号 | 问题 | 级别 | 维度 |
|:------:|:----:|------|:----:|------|
| P0 | A1 | 所有策略族均为 NO-GO，gross excess 正值率仅 27.5% | 🔴 | Alpha |
| P0 | A2 | 12 个因子 0 个通过 strict retention gate | 🔴 | Alpha |
| P0 | D1 | 49 个 V4 因子 FAIL（growth 覆盖率 0%，value 元数据缺失） | 🔴 | 数据 |
| P0 | D2 | 优化器价格缓存覆盖率 0%，Phase 3 完全不可运行 | 🔴 | 数据 |
| P0 | C1 | 优化器 fallback rate 26.98%（OOS）且原因以 infeasible_config 为主 | 🔴 | 构建 |
| P1 | A3 | 缺失 growth/momentum/quality 因子，因子池结构失衡 | 🟠 | Alpha |
| P1 | D3 | Benchmark 日历错位（所有年份 spread > 50 bps） | 🟠 | 数据 |
| P1 | V1 | Phase 5 全部诊断数据缺失（无交易/持仓/组合价值数据） | 🔴 | 验证 |
| P1 | C2 | OOS (2025+) 超额 -16.5%，IR -1.05，换手 48% — 结构性恶化 | 🟠 | 构建 |
| P2 | A4 | Sleeve 内因子质量差异大（value ICIR 仅 0.074） | 🟠 | Sleeve |

---

## 4. Alpha / 因子质量问题

### A1 🔴 所有策略族均为 NO-GO

**来源**：`strategy_alpha_failure_report.md` §3

**现象**：2017-2024 共 8 年，5 个策略族（A_5reversal、B_dynamic、C_regime_baseline、D_regime_overlay、E_shock_reversal）全部不满足投资门槛：

| 策略 | 年均收益 | 年均超额 | 中位数超额 | 正收益年数 | 平均 IR | 最大亏损 | 判定 |
|------|:------:|:------:|:------:|:------:|:------:|:------:|:----:|
| A_5reversal | -9.6% | -11.7% | -12.1% | 2/8 | -0.81 | -26.9% | NO_GO |
| B_dynamic | -9.9% | -12.1% | -10.0% | 1/8 | -1.10 | -25.5% | NO_GO |
| C_regime_baseline | -7.3% | -9.5% | -10.0% | 1/8 | -0.70 | -25.0% | NO_GO |
| D_regime_overlay | -5.7% | -7.9% | -10.2% | 2/8 | -0.64 | -24.7% | NO_GO |
| E_shock_reversal | -8.1% | -10.2% | -10.0% | 2/8 | -0.72 | -28.9% | NO_GO |

**根因**：Gross excess 正值率仅 27.5%——即扣费前已有 72.5% 的年份 alpha 为负。**Alpha 在 pre-cost 层面即不存在。**

**处理状态**：已确认。V4 必须从根本上扩展因子池。

---

### A2 🔴 全部 12 个因子未通过 strict retention gate

**来源**：`strategy_alpha_failure_report.md` §4

**现象**：

| 因子 | 类型 | Mean IC | ICIR | Pos IC Yrs | LongOnly Top | 失败原因 |
|------|------|:------:|:----:|:---------:|:----------:|----------|
| `volatility_60_cs` | technical | 0.040 | 1.114 | 7/8 | -0.7% | LO top ≤ 0；缺 decile_monotonicity；缺 coverage |
| `pv_divergence_20_cs` | technical | 0.037 | 2.187 | 8/8 | 3.9% | 缺 decile_monotonicity；缺 coverage |
| `volatility_20_cs` | technical | 0.036 | 1.095 | 7/8 | -2.3% | LO top ≤ 0；缺 decile_monotonicity；缺 coverage |
| `momentum_120_cs` | technical | 0.019 | 0.670 | 5/8 | -2.1% | LO top ≤ 0；缺 decile_monotonicity；缺 coverage |
| `reversal_5_cs` | technical | 0.018 | 1.087 | 7/8 | 8.3% | 缺 decile_monotonicity；缺 coverage |
| `reversal_20_cs` | technical | 0.016 | 0.767 | 6/8 | -0.1% | LO top ≤ 0；缺 decile_monotonicity；缺 coverage |
| `ep_cs` | fundamental | 0.013 | 0.389 | 7/8 | -4.9% | LO top ≤ 0；TB excess ≤ 0；缺 coverage |
| `bp_cs` | fundamental | 0.012 | 0.235 | 5/8 | 0.0% | 缺 decile_monotonicity；缺 coverage |
| `sp_cs` | fundamental | 0.010 | 0.322 | 6/8 | -2.1% | LO top ≤ 0；缺 decile_monotonicity；缺 coverage |
| `rsi_14_cs` | technical | 0.008 | 0.404 | 3/8 | -4.0% | LO top ≤ 0；pos IC < 5/8；缺 coverage |
| `momentum_60_cs` | technical | 0.000 | 0.014 | 5/8 | -3.6% | LO top ≤ 0；缺 coverage |
| `macd_12_26_9_cs` | technical | -0.006 | -0.397 | 3/8 | -9.3% | Mean IC ≤ 0；consecutive neg ≥ 3；缺 coverage |

**共性问题**：
1. 全部 12 个因子缺少 decile_monotonicity 数据
2. 全部 12 个因子缺少 coverage 数据
3. 8/12 个因子 long-only top 收益 ≤ 0（top-bottom 有 alpha 但 long-only 无 alpha → short side 驱动收益）

**处理状态**：已确认。V4 需要新因子池，且需要补充 monotonicity 和 coverage 诊断。

---

### A3 🟠 因子池结构严重失衡

**来源**：`strategy_failure_source_matrix_v4.md` §3.1

**现象**：
- 现有因子池全部为 technical（波动率、反转、动量、MACD、RSI）+ 少量 fundamental（EP/BP/SP）
- **完全缺失**：growth（revenue_growth, profit_growth, earnings_acceleration）、quality（ROE stability, accruals, debt ratio）、cashflow（FCF yield, CFO variability）
- 2017 年成长行情中所有策略 gross excess 均为负（-17.3% 至 -21.7%），根因即缺少 growth/momentum 因子

**影响**：在任何 growth-driven 的市场环境中（2017、2019、2020），策略必然跑输。这不是参数优化能解决的，是因子覆盖面的结构性缺陷。

**处理状态**：V4 已启动因子池扩展（`docs/alpha_factor_definitions_v4.md`），但 49 个因子中大量 FAIL 于数据覆盖（见 D1）。

---

### A4 🟠 Sleeve 内因子质量差异过大

**来源**：`strategy_alpha_failure_report.md` §5

**现象**：

| Sleeve | N Years | Avg ICIR | Avg Hit Rate | Pos ICIR Years |
|--------|:------:|:------:|:------:|:------:|
| defensive | 8 | 0.174 | 56.3% | 7/8 |
| reversal | 8 | 0.150 | 55.5% | 8/8 |
| volume_price | 8 | 0.125 | 55.4% | 8/8 |
| momentum | 8 | 0.102 | 54.8% | 8/8 |
| value | 8 | **0.074** | 52.2% | **6/8** |

Value sleeve ICIR 仅 0.074，是最弱 sleeve。Sleeve 内因子质量差异大可能导致聚合时弱因子稀释强因子信号。

**处理状态**：V4 sleeve 重构中（`docs/sleeve_design_v4.md`），需确保每个 sleeve 至少 2 个高质量因子。

---

### A5 🟠 Top-bottom alpha 存在但 long-only 无 alpha

**来源**：`strategy_alpha_failure_report.md` §4（12 个因子中 8 个 LO top ≤ 0）

**现象**：多个因子（如 `reversal_5_cs` top-bottom 收益 24.7%，但 long-only top 仅 8.3%）表明 short side 是 alpha 的主要来源，但 A 股做空受限，这些因子的 alpha 无法在 long-only 组合中实现。

**处理状态**：需要在 V4 因子筛选时把 long-only 可行性作为硬性条件。

---

### A6 🟡 反转因子在趋势市中持续负贡献

**来源**：`strategy_failure_source_matrix_v4.md` §2.2（2020 年诊断）

**现象**：2020 年（趋势上涨市），反转因子（reversal_5_cs）成为负贡献的主要来源，regime router 未能有效降低反转 sleeve 的配置权重。

**处理状态**：需在 regime router 中增加趋势强度信号，在强趋势市中系统性降权反转 sleeve。

---

### A7 🟡 因子 IC 在 2025+ 衰减数据缺失

**来源**：`phase5_failure_diagnostics.json`（factor_decay_2025 部分）

**现象**：
- `factor_cs` post-2025 数据完全缺失（post_2025_n=0）
- 无法评估任何因子在 OOS 期间是否发生衰减

**处理状态**：需要 Phase 5 框架先产出有效数据后，才能进行 2025+ 衰减诊断。

---

## 5. Sleeve / 聚合问题

### S1 🟠 因子到 sleeve 的信号穿透未量化

**来源**：`strategy_failure_source_matrix_v4.md` §2.2（2023 年诊断）

**现象**：2023 年 D_regime_overlay 的 gross excess 为负（-1.5% net），但 overlay 相对 baseline 改善 +4.65pp。信号在 sleeve 聚合中存在明显衰减，但当前框架缺乏从单因子 IC → sleeve ICIR → composite return 的逐层穿透诊断。

**处理状态**：V4 保留 sleeve→composite→holding 穿透诊断能力（优先级 P1），但尚未实现。

---

### S2 🟠 Sleeve 权重偏防御，反弹时配置不足

**来源**：`strategy_failure_source_matrix_v4.md` §2.2（2023 年）

**现象**：2023 年三波反弹中 sleeve 权重偏 defensive/value，reversal 配置不足，导致反弹捕捉效率低。

**处理状态**：属于 regime router（R 维度）和 sleeve 设计的交叉问题。

---

### S3 🟡 Sleeve oracle 与 router 实际分配的错配率 80%

**来源**：`strategy_alpha_failure_report.md` §8

**现象**：
- Dominant sleeve 等于 oracle（hindsight 最优）的概率仅 20.0%
- 平均 opportunity cost vs oracle：1.21%
- Overlay 多因子乘数→收益相关性为 0%（即 overlay 乘数不包含预测信息）

**处理状态**：这是 regime router 的预测能力问题，详见 R 维度。

---

## 6. Regime Router 问题

### R1 🟠 Range_bound 概率系统性过高（≈60%）

**来源**：`strategy_alpha_failure_report.md` §7

**现象**：2017-2024 全部年份的主导 regime 均为 `range_bound_prob`，表明 regime 分类器对趋势市的识别能力不足。2017、2020 等强趋势年份中仍以 range_bound 为主导，导致反转/防御 sleeve 过度配置。

**处理状态**：V4 保留 router 架构但 default 先关闭 overlay（对照验证），见 `docs/strategy_v4_freeze_spec.md`。

---

### R2 🟡 Router 在风格切换年份（2021）滞后

**来源**：`strategy_failure_source_matrix_v4.md` §2.1

**现象**：2021 年风格切换时 router 存在明显滞后，导致 sleeve 权重与市场风格错配。

**处理状态**：优先级 P2，非 V4 核心。可考虑增加 regime transition probability 信号。

---

### R3 🟡 Router active vs passive 对照不完整

**来源**：`strategy_failure_source_matrix_v4.md` §2.2（2024 年）

**现象**：2024 年 V3 overlay 反而降低了表现（V3 -3.7% vs V2 -3.3%），说明 overlay 的近期表现追逐机制在风格稳定的年份可能过度拟合噪声。

**处理状态**：V4 需要做 active vs passive 的逐年对比，确认 overlay 是否真的有正贡献。

---

## 7. 组合构建 / 优化器问题

### C1 🔴 优化器 fallback rate 过高（OOS 26.98%）

**来源**：`outputs/metrics_summary.json`（phase5_recent_oos 口径）

**现象**：

| 指标 | Phase 5 Base (2016) | Phase 5 OOS (2025+) |
|------|:----:|:----:|
| optimizer_fallback_rate | 4.5% | **26.98%** |
| opt_n_total | 44 | 63 |
| opt_n_fallback | 2 | 17 |

**OOS fallback 原因分布**：
- `infeasible_config`：9 次
- `insufficient_return_obs`：7 次
- `OSQP solver failed`：1 次

**根因分析**：
- `infeasible_config`（53%）→ 约束过紧，可行域为空
- `insufficient_return_obs`（41%）→ mu_df 中的收益观测不足，可能因停牌或新股

**处理状态**：需要调整优化器约束（放宽 weight bounds 或 cardinality）或改进 mu_df 的缺失值处理。

---

### C2 🟠 OOS (2025+) 策略表现结构性恶化

**来源**：`outputs/metrics_summary.json`

**现象**：

| 指标 | Phase 5 IS (2016) | Phase 5 OOS (2025+) | Phase 2 OOS (2026 YTD) |
|------|:----:|:----:|:----:|
| annualized_excess_return | +1.2% | +1677.7% 异常 | **-16.5%** |
| information_ratio | +0.19 | +0.91 异常 | **-1.05** |
| sharpe_ratio | +0.42 | +0.66 | **-0.17** |
| max_drawdown | -8.9% | -10.2% | **-10.6%** |
| avg_turnover | 39.8% | 44.2% | **48.0%** |

**异常说明**：Phase 5 OOS 期间的超高收益（+1677%）来自 2016 配置在 2025+ 的异常表现（极短回测期 + 高杠杆 + 数据问题），不代表真实策略能力。Phase 2 OOS（2026 YTD）的 -16.5% 超额和 -1.05 IR 才是更可靠的 OOS 参考。

**处理状态**：Phase 5 框架本身数据缺失严重（见 V1），需先修复数据管道。

---

### C3 🟠 Gross→Net 衰减在部分年份显著

**来源**：`strategy_alpha_failure_report.md` §6

**现象**：全周期平均成本拖累约 3-5%，成本后 net excess 正值率仅 22.5%（vs gross 27.5%）。成本拖累虽非主因，但在高换手策略（A_5reversal、B_dynamic）中年化可达 4-6%。

**处理状态**：成本模型本身可控，但因子 alpha 太弱时成本就成了压垮骆驼的最后一根稻草。

---

### C4 🟡 信号穿透效率缺乏逐层量化

**来源**：`strategy_failure_source_matrix_v4.md` §2.2（2023 年诊断）

**现象**：2023 年暴露了信号到持仓的穿透问题（gross excess 为负但 overlay 改善 +4.65pp），但缺乏从 IC → sleeve weight → composite score → holding weight 的逐层归因。

**处理状态**：V4 保留诊断能力，优先级 P1。

---

## 8. 数据基础设施问题

### D1 🔴 V4 因子池大面积 FAIL（49 个因子数据不可用）

**来源**：`docs/factor_rejection_log_v4.md`、`docs/alpha_rebuild_priority_list.md`

**现象**：
- **Growth 类因子**：覆盖率 0%（底层数据源缺失）
- **Value 类因子**：`LEAKAGE_METADATA_MISSING`（元数据缺少发布日期，无法进行 PIT 对齐）
- **Quality 类因子**：部分依赖的财务报表数据不完整
- 49 个因子中大部分因数据覆盖或元数据问题被 rejection log 标记为 FAIL

**影响**：即使所有策略和框架问题都修复，没有可用因子也无法运行任何 gate。

**处理状态**：数据修复是 V4 最高优先级的前置任务（`docs/v4_data_inventory.md`）。

---

### D2 🔴 优化器价格缓存覆盖率 0%

**来源**：`outputs/latest_metrics_summary.json`

**现象**：

```json
{
  "phase3_optimized": {
    "status": "FAIL",
    "error": "OPTIMIZER_PRICE_CACHE_INSUFFICIENT",
    "coverage_ratio": 0.0,
    "expected_dates": 5,
    "actual_dates": 0,
    "first_missing_dates": ["20150104", "20150105", "20150106", "20150107", "20150108"]
  }
}
```

**根因**：优化器需要回溯一年的价格数据（2015），但价格缓存中该时段数据完全缺失。

**修复方法**：运行 `python run_research.py phase0 --start 20150101 --end 20161231`

**处理状态**：待执行。

---

### D3 🟠 Benchmark 日历错位（全部年份）

**来源**：`strategy_alpha_failure_report.md` §1

**现象**：

| 年份 | bm_spread_bps | calendar_status |
|:---:|---:|------|
| 2017 | 138.3 | BENCHMARK_CALENDAR_MISMATCH |
| 2018 | 292.9 | BENCHMARK_CALENDAR_MISMATCH |
| 2019 | **1329.8** | BENCHMARK_CALENDAR_MISMATCH |
| 2020 | 518.5 | BENCHMARK_CALENDAR_MISMATCH |
| 2021 | 718.4 | BENCHMARK_CALENDAR_MISMATCH |
| 2022 | 222.4 | BENCHMARK_CALENDAR_MISMATCH |
| 2023 | 443.7 | BENCHMARK_CALENDAR_MISMATCH |
| 2024 | 406.9 | BENCHMARK_CALENDAR_MISMATCH |
| 2026 | 681.6 | BENCHMARK_CALENDAR_MISMATCH |

全部 9/9 年存在日历错位（spread > 50 bps），其中 2019 年高达 1329.8 bps。虽然未检测到同期的 `BENCHMARK_RETURN_CONFLICT`（同一时期不同基准收益冲突），但日历不一致使得超额收益计算不够精确。

**处理状态**：已在 common calendar 基础上做归一化，但需要检查日历对齐逻辑。

---

### D4 🟠 因子 coverage 数据缺失（全部 12 个 V3 因子）

**来源**：`strategy_alpha_failure_report.md` §4

**现象**：全部 12 个 V3 因子缺少 coverage 诊断数据（coverage_ratio、n_covered_dates、n_expected_dates），导致无法评估因子在回测窗口内的实际可用性。

**处理状态**：V4 gate 中已加入 coverage 诊断（`docs/alpha_factor_definitions_v4.md`），但依赖 D1 数据修复。

---

### D5 🟡 Phase 5 因子稳定性分析仅分析 1 个因子

**来源**：`phase5_failure_diagnostics.json`（factor_stability 部分）

**现象**：`n_factors: 1`，仅分析了 `factor_cs`，其余因子因数据不可用被跳过。

**处理状态**：D1 修复后应扩展至全因子池。

---

## 9. 验证框架 / 方法论问题

### V1 🔴 Phase 5 全部诊断数据缺失

**来源**：`outputs/phase5_failure_diagnostics.md`

**现象**：

| 模块 | 状态 |
|------|------|
| Turnover Attribution | **DATA_MISSING** — No trade/holdings data available |
| Cost Attribution | **DATA_MISSING** — No portfolio value data |
| Fallback Attribution | **DATA_MISSING** — No optimizer runs recorded |
| Factor Stability | 仅 1 个因子有数据，所有 IC 值为 DATA_MISSING |
| OOS (2025+) Summary | **DATA_MISSING** |

**根因**：Phase 5 框架运行了但上游数据管道未产出有效输入。可能是 Phase 4（optimized backtest）失败导致 Phase 5 无数据可消费。

**处理状态**：需先修复 D2（价格缓存）使 Phase 3/4 产出有效数据，再重跑 Phase 5。

---

### V2 🔴 Phase 0 gate 允许过度乐观的统计推断

**来源**：`docs/photoresist_primary_5d_analysis_and_issues.md` §4.4

**现象**（以光刻胶 primary_5d 为例，但框架层面的问题具有一般性）：

1. **经济幅度门槛替代统计推断**：20 日平均收益 ≥ 2% 被作为硬性条件，但在 26 个事件中，标准差 15% → 均值标准误 2.94% → t-stat ≈ 0.68 → 单侧 p ≈ 0.25。即使观察到 2% 均值，也无法在常规统计水平上拒绝「真实均值为 0」。
2. **LOO 阈值 -50 bps 的语义矛盾**：完整篮子 +200 bps 且 LOO 组合 -49 bps → 通过，但超额方向已反转且 249 bps 变化由单一股票驱动。
3. **年度门槛过低**：允许一年亏损 -2.9% 通过，在年均 2-3 次频率下一次交易决定全年表现。

**影响**：这些设计缺陷可能在统计噪声中给出虚假的「通过」信号，对任何低频事件驱动型因子都有影响。

**处理状态**：已在 photoresist 分析中提出了具体修正建议。

---

### V3 🟠 Phase 0 gate 的参数空间缺乏 power 分析

**来源**：`docs/photoresist_primary_5d_analysis_and_issues.md` §5.1

**现象**：

| 约束 | 值 |
|------|----|
| bull/neutral 非重叠事件 | ≈ 26 个 |
| 年均交易次数 | ≈ 3 次 |
| 核心股票池 | 4 只 |
| OOS 年份 | 2 年（2024-2025） |

在此参数空间下：
- 统计显著性检验几乎不可能通过（样本不足）
- 经济幅度门槛的统计 power 不足
- 年度稳定性完全依赖少数交易

**建议**：gate 设计前必须计算所需的最小样本量和最小可检测效应量（MDE）。

---

### V4 🟠 Placebo 检验的排列空间在窄板块中不足

**来源**：`docs/photoresist_primary_5d_analysis_and_issues.md` §4.4.1

**现象**：在 4 只股票 × 26 个事件中：
- 股票层面随机化只有 4! = 24 种排列
- 最小可达 p-value = 1/24 ≈ 0.042
- p ≤ 0.10 的要求虽然能满足，但不是因为效应强，而是因为排列空间天然受限

**处理状态**：这是一个被忽视的技术细节，应在 gate 设计文档中明确记录排列空间限制。

---

### V5 🟠 最后触发日聚类存在隐性未来函数

**来源**：`docs/photoresist_primary_5d_analysis_and_issues.md` §4.1

**现象**（光刻胶分析中确认，对任何事件聚类方法都有一般性参考）：

- 回顾性 `event_date` 使用事件簇的最后一个触发日
- 该时点需要未来数据才能确认（不知道当前触发是否是最后一次）
- 在均值回归策略中大概率形成乐观偏差

**对方已接受**：新增 `live_signal_date`（首次触发日）作为正式交易时点，`retrospective_episode_date` 降级为描述性使用。

**处理状态**：我们自己的 panic/shock reversal 因子也应区分研究口径和实盘口径。

---

### V6 🟠 Phase 0 的 Go/No-Go 在 cooldown 参数不同时结论翻转无裁决规则

**来源**：`docs/photoresist_primary_5d_analysis_and_issues.md` §4.7

**现象**：cooldown 参数（5 vs 3 vs 10 个交易日）可能导致 Phase 0 通过/失败结论翻转。当前框架禁止「按收益挑选」，但没有规定不同 cooldown 导致结论翻转时的裁决规则。

**处理状态**：需要预定义裁决规则（如使用最保守的 cooldown 值，或要求所有候选值都通过）。

---

### V7 🟡 框架层级可能保护不可证伪的底层

**来源**：`docs/photoresist_primary_5d_analysis_and_issues.md` §4.3

**现象**：四层框架（Statistical → Tradable → Top1 → Account）允许 Layer 1 通过 + Layer 2/3 失败的无限循环——只要 Layer 1 的统计现象存在，就可以在每个新年度重新尝试 Layer 2 和 Layer 3。对方已区分 `scientific_status` 和 `strategy_status`，但未设时间上限。

**处理状态**：需要在框架中加入时间上限（如 2 年内 Layer 2 未通过则降级为纯研究观察）。

---

### V8 🟡 Gate 变体缺少版本预算

**来源**：`docs/photoresist_primary_5d_analysis_and_issues.md` §4.6

**现象**：对方限制了 Top1 版本（最多 2 个），但未限制 gate 公式自身的变体数量（如将 `absolute_threshold_pct` 从 -5.0 改为 -6.0 称为 `v2_candidate` 是否受预算约束不明确）。

**处理状态**：所有 gate 变体（包括参数 tuning）应纳入版本预算体系。

---

### V9 🟡 低频事件策略的验证框架缺乏针对性设计

**来源**：`docs/photoresist_primary_5d_analysis_and_issues.md` §5

**现象**：年均 3 次交易的策略，传统 IC/ICIR 框架不适用，但替代框架（事件研究法 + placebo + 共同性诊断）的样本量要求又极高。这是一个框架层面的空白。

**处理状态**：需要为低频事件驱动策略建立独立的验证框架。

---

### V10 🟡 多次查看 OOS 后仍声称「干净」

**来源**：`docs/photoresist_primary_5d_analysis_and_issues.md` §6.2

**现象**：在 OOS 数据（2024-2025）已被多次查看后，仍在 Phase 0 中使用相同的 OOS 年份做验证。这破坏了 OOS 的纯度。

**处理状态**：使用嵌套 walk-forward 或滚动 OOS 窗口，确保任何时候都有真正未被查看过的 OOS。

---

### V11 🔵 框架复杂度与样本量不匹配

**来源**：`docs/photoresist_primary_5d_analysis_and_issues.md` §5

**现象**：four-layer framework + 10 条硬性条件 + 状态机 + 版本预算 + 退出规则 → 应用于 4 只股票 + 26 个事件。框架设计本身是好的，但与样本量严重不匹配。

**处理状态**：框架复杂度应与样本量成比例。在 broad market（≥ 500 只）验证中这样的框架是合适的。

---

## 10. 光刻胶 panic 因子专项问题

（以下问题虽在 photoresist 分析中确认，但对我们自己的 panic reversal 因子开发有直接参考价值。）

### P1 🔴 板块共同效应尚未证明（LOO 反转）

**现象**：剔除彤程新材后 20 日篮子结果转负 → 当前结果依赖单一股票，不能称为板块共同修复效应。

**我们的应对**：panic reversal 因子应在 broad market（≥ 500 只）中验证，避免窄板块集中度问题。

### P2 🔴 单票约束与信号性质的结构性矛盾

**现象**：恐慌修复本质是 cross-sectional 的均值回归（买 10 只约 7 只反弹），单票选股将其降维为 idiosyncratic 赌博。

**我们的应对**：确保因子在组合层面验证，不做 Top 1 选股。

### P3 🟠 市场状态过滤存在选择偏差

**现象**：bull/neutral 启用、bear 禁用的决定发生在看到分层结果之后。

**我们的应对**：市场状态过滤规则必须在查看任何分层结果前冻结。

### P4 🟡 年均 3 次交易的经济价值待量化

**现象**：研究投入巨大（三轮辩论、四层框架、10 条条件），但潜在收益上限仅年化 3-9% 超额。

**我们的应对**：在策略立项前做研究成本 vs 潜在收益的评估。

---

## 11. V4 开发优先级矩阵

基于以上问题清单，推导 V4 的开发优先级：

| 优先级 | 维度 | 待解决问题 | 对应里程碑 |
|:------:|------|-----------|-----------|
| **P0** | 数据基础设施 | D1（因子数据）、D2（价格缓存） | M1（数据准备） |
| **P0** | Alpha / 因子 | A1（NO-GO）、A2（全部 FAIL）、A3（结构失衡） | M2-M4（因子开发+gate） |
| **P1** | 验证框架 | V1（Phase 5 缺失）、V2（统计推断） | M4（gate 框架） |
| **P1** | Sleeve 重构 | S1（信号穿透）、S2（反弹捕捉） | M5（sleeve/regime 重构） |
| **P1** | 组合构建 | C1（fallback）、C2（OOS 恶化） | M4（gate 框架） |
| **P2** | Regime Router | R1（range_bound 过高）、R2（滞后） | M5（不改变 router 架构） |
| **P2** | 方法论 | V3-V11 | 持续改进 |
| **P3** | 光刻胶 panic | P1-P4 | M6+（独立方向） |

---

## 12. 跨维度根因总结

### 12.1 根本原因链条

```text
数据基础设施缺失（D1, D2）
  → 新因子无法开发/验证（A3, A7）
    → 因子池停留在 V3 的 12 个全部 FAIL（A2）
      → gross excess 正值率仅 27.5%（A1）
        → 所有策略族 NO-GO
          → Phase 5 无有效数据产出（V1）
            → 无法进入 Go/No-Go 决策
```

### 12.2 不在当前范围的问题

以下问题确认存在但不属于 V4 修复范围：
- 光刻胶 primary_5d 的单票策略开发（属于独立方向）
- 高频交易/做市策略的基础设施
- 实时交易系统的延迟和吞吐量

---

## 13. 文档版本

| 版本 | 日期 | 变更 |
|------|------|------|
| v1.0 | 2026-07-12 | 初版——汇总 Phase 2-5 全部诊断、alpha 失败分析、V4 失败矩阵、光刻胶问题清单 |

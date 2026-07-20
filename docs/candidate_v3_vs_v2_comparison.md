# Candidate V3 vs V2 独立比较

生成日期：2026-06-14  
数据来源：`outputs/validation/candidate_v2/runs.csv`、`outputs/validation/candidate_v3/runs.csv`  
生成脚本：`scripts/generate_go_nogo_decision.py`

## 1. 概述

| 维度 | Candidate V2 (`E_candidate_v2`) | Candidate V3 (`F_candidate_v3`) |
|------|------|------|
| 因子池 | `configs/factors_candidate_v1.yaml`（5 因子） | `configs/factors_candidate_v1.yaml`（5 因子） |
| Regime 配置 | `configs/regime_candidate_v2.yaml` | `configs/regime_candidate_v3.yaml` |
| Performance Overlay | 未启用 | 启用，strength=0.40 |
| Fundamental max stale | 63 交易日 | 45 交易日（收紧） |
| 核心差异 | Sleeve cleanup + trend-sensitive allocator | V2 + sleeve_performance_overlay |

## 2. 年度超额对比

| Year | E_candidate_v2 | F_candidate_v3 | V3 - V2 差异 | V3 改善？ |
|------|------:|------:|------:|:------:|
| 2017 | -15.8% | -15.0% | +0.8pp | ✅ |
| 2018 | -3.1% | -3.3% | -0.2pp | ❌ |
| 2019 | -2.5% | 1.0% | +3.5pp | ✅ |
| 2020 | 8.6% | 9.3% | +0.7pp | ✅ |
| 2021 | 4.6% | 5.8% | +1.2pp | ✅ |
| 2022 | 7.2% | 8.1% | +0.9pp | ✅ |
| 2023 | -5.3% | -4.4% | +0.9pp | ✅ |
| 2024 | -3.3% | -3.7% | -0.4pp | ❌ |
| 2026 YTD | -18.1% | -18.3% | -0.2pp | ❌ |

- V3 改善年份：**6/8** 个验证年
- 平均年度超额改善：**+0.92pp**
- 正超额年份：V2 3/8 → V3 4/8（+1 年）

## 3. 汇总指标对比

| 指标 | V2 | V3 | 变化 | GO 门槛 |
|------|------:|------:|------:|------:|
| 平均年化超额 | -1.2% | -0.3% | +0.9pp | > 2.0% |
| 中位数年化超额 | -2.8% | -1.2% | +1.6pp | > 0.0% |
| 正超额年份 | 3/8 | 4/8 | +1 | >= 5/8 |
| 平均 IR | -0.21 | -0.11 | +0.10 | > 0.30 |
| 最大单年超额亏损 | -15.8% | -15.0% | +0.8pp | > -10.0% |
| 平均换手 | 30.8% | 30.8% | 不变 | 不高于 V3 |

## 4. 失败年份分析

### 共同失败年份

V2 和 V3 均在以下年份显著失败（超额 < -3%）：

| 年份 | V2 超额 | V3 超额 | V3 改善幅度 | 可能原因 |
|------|------:|------:|------:|------|
| 2017 | -15.8% | -15.0% | +0.8pp | 成长风格缺失、价值陷阱 |
| 2023 | -5.3% | -4.4% | +0.9pp | 弱市反弹失败、组合穿透 |
| 2024 | -3.3% | -3.7% | -0.4pp | 价值/红利/行业轮动捕捉不足 |

### 2018 和 2024 边际退化

- **2018**: V3 超额 -3.3% vs V2 -3.1%，overlay 在熊市中可能追逐近期"表现好"的 sleeve
- **2024**: V3 超额 -3.7% vs V2 -3.3%，overlay 未能在价值轮动中发挥正面作用

## 5. V3 改善来源分析

改善主要来自 performance overlay 的再分配能力，而不是新增 alpha 供给：

- V3 与 V2 使用相同的 5 因子池（`factors_candidate_v1.yaml`）
- V3 通过 `sleeve_performance_overlay` 根据近期 sleeve IC 质量动态调权
- 收紧 fundamental staleness（63→45 交易日）降低了过时财务数据的风险
- 但 alpha 来源本身没有改变 —— 底层因子池未扩展

## 6. 结论

1. **V3 相对 V2 有边际改善**：6/8 年改善，平均 +0.92pp，但改善幅度不足以通过任何 GO 门槛。
2. **改善不来自新增 alpha**：V3 的改善来自 overlay 的权重再分配，底层因子池相同。
3. **2017 仍是最差年份**：两者均在 -15% 以上，表明核心 alpha 问题未解决。
4. **近年（2023/2024）无实质改善**：V3 在这两年仍持续负超额。
5. **V4 需要从 alpha 供给侧重建**：扩展因子池、新增质量/现金流/成长类因子是唯一可行方向。

V3 的贡献是证明了 overlay 机制本身有效（6/8 年改善），但 alpha 池质量限制了其上限。这一结论直接支撑 V4 将重心从 overlay 调参转向 alpha 重建的决策。

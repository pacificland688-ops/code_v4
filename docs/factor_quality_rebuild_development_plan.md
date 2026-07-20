# Factor Quality Rebuild 开发方案

生成日期：2026-06-13

## 目标

系统审计现有 18 个因子，修复方向/对齐问题，淘汰无效因子，筛出扣费后仍有稳定 alpha 的候选因子，作为下一代 sleeve 和策略族输入。

## 新增文件

| 文件 | 说明 |
|------|------|
| `scripts/factor_quality_rebuild.py` | 主流水线：审计→方向→IC→分位收益→cost→聚类→gate |
| `configs/factor_quality_rebuild.yaml` | 18 因子候选池、窗口拆分、gate 阈值 |
| `tests/test_factor_quality_rebuild.py` | 18 个测试覆盖所有 gate 条件 |
| `docs/factor_quality_rebuild_report.md` | 自动生成报告 |

## 窗口拆分

- **2017-2020**：calibration（方向选择）
- **2021-2024**：validation（gate 判定）
- **2025-2026**：watch-only（不参与判定）

## 质量 Gate

| 维度 | 阈值 |
|------|:----:|
| Input audit | PASS（无重复、无常数、缺失率<50%） |
| Direction | calibration 内选定，validation 固定 |
| Mean rank IC (validation) | > 0.01 |
| ICIR | ≥ 0.20 |
| 正 IC 年数 | ≥ 3/4 |
| Net spread (5d, 20bps) | > 0 |
| 正 spread 年数 | ≥ 3/4 |
| Top quintile net excess | > 0 |
| Cost resilience (net/gross) | ≥ 50% |
| 单年集中度 | < 60% |

## 运行结果

```
0 PASS, 3 WATCH, 15 FAIL
WATCH: volatility_20_cs, volatility_60_cs, log_market_cap_cs
Recommendation: No PASS factors. WATCH factors require manual review before sleeve rebuild.
```

所有传统 alpha 因子（value/momentum/reversal 等）在 validation 窗口扣费后均无法通过 gate。

## 测试

- 18 个单测覆盖：IC、输入审计、方向审计、分位收益、quality gate、correlation clustering
- 73 个回归测试全部通过

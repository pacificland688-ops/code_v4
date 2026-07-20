# Regime 参数网格与完整复验：2023 / 2025

数据日期：2026-06-09

## 目标

验证“不同市场趋势使用不同策略”的 regime router 是否能修复 2023 / 2025 两个失败年份。重点不是找单年最优参数，而是判断降低 `range_bound -> reversal` 暴露、加快 sleeve 切换是否有稳定改善。

## 数据修复

2025 完整 Phase 2 一开始被价格质量门槛挡住：

- `prices_adj` 日跳变：7
- `prices_adj` 周跳变：17
- 根因：2025 `adj_factor` 曾经局部缺失/局部补入，导致同一年内复权口径断层

已执行：

- `python -X utf8 run_research.py phase0 --start 20250101 --end 20251231`
- `python -X utf8 run_research.py phase1 --start 20250101 --end 20251231 --recompute`

修复后验证：

- 2025 `prices_adj`：`status=OK`
- `n_daily_jumps=0`
- `n_weekly_jumps=0`
- `duplicates=0`
- `missing_ratio=0`

2025 Phase 1 重算后，价值因子仍是最强：

| 因子 | Mean IC | ICIR | IC正比例 | 结论 |
|---|---:|---:|---:|---|
| ep_cs | 0.1076 | 0.524 | 66.67% | PASS |
| sp_cs | 0.0741 | 0.469 | 58.33% | PASS |
| bp_cs | 0.0889 | 0.466 | 66.67% | PASS |
| reversal_5_cs | 0.0187 | 0.103 | 48.15% | FAIL |

## Fast 网格筛选

Fast 诊断引擎复用 regime composite 生成信号，再用本地 parquet 做简化等权 Top50 回测。它只用于筛方向，不能替代完整 Phase 2。

| 年份 | 配置 | 年化超额 | IR | 最大回撤 | reversal | momentum | defensive | value | volume_price |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2023 | baseline | -0.3% | -0.01 | -21.8% | 31.1% | 7.5% | 28.4% | 14.9% | 18.1% |
| 2023 | less_reversal_faster_switch | 1.5% | 0.26 | -21.0% | 24.4% | 9.6% | 28.5% | 17.3% | 20.2% |
| 2025 | baseline | -24.6% | -2.06 | -14.6% | 29.1% | 12.9% | 19.7% | 16.0% | 22.4% |
| 2025 | less_reversal_faster_switch | -21.9% | -1.82 | -14.1% | 22.7% | 14.8% | 19.2% | 18.7% | 24.5% |

Fast 结论：组合候选 `less_reversal_faster_switch` 同时改善 2023 和 2025，进入完整 Phase 2 复验。

## 完整 Phase 2 复验

同年闭合窗口：

- 2023：`20230101-20231222`
- 2025：`20250101-20251224`

| 年份 | 配置 | 年化收益 | 年化超额 | IR | 最大回撤 | 换手 | reversal | momentum | defensive | value | volume_price |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2023 | baseline | -22.09% | -5.46% | -0.83 | -24.43% | 39.92% | 31.1% | 7.5% | 28.4% | 14.9% | 18.1% |
| 2023 | less_reversal_faster_switch | -20.91% | -3.98% | -0.61 | -23.60% | 35.83% | 24.4% | 9.6% | 28.5% | 17.3% | 20.2% |
| 2025 | baseline | 2.36% | -18.72% | -1.87 | -16.91% | 50.16% | 25.8% | 14.5% | 24.8% | 13.2% | 21.6% |
| 2025 | less_reversal_faster_switch | 2.69% | -18.44% | -1.79 | -16.27% | 48.20% | 19.9% | 17.0% | 23.9% | 15.1% | 24.1% |

相对 baseline：

| 年份 | 年化超额变化 | IR变化 | 最大回撤变化 | 换手变化 |
|---:|---:|---:|---:|---:|
| 2023 | +1.48pct | +0.22 | +0.83pct | -4.09pct |
| 2025 | +0.28pct | +0.07 | +0.64pct | -1.96pct |

## 结论

`less_reversal_faster_switch` 方向正确，但不足以 Go-live。

它确实降低了反转暴露，并在完整 Phase 2 下改善了 2023 / 2025：

- 2023 改善比较明显：超额 +1.48pct，IR +0.22。
- 2025 改善很小：超额 +0.28pct，IR +0.07。
- 两年仍然都是负超额、负 IR。

关键诊断：问题不只是 regime mapping 参数。2025 重算后价值因子 ICIR 很强，但完整 Phase 2 里 `value_weight` 只有 15.1%，仍未充分穿透到组合。也就是说，当前 router 能“少犯一点错”，但还不能把强因子 sleeve 提到足够权重。

## 下一步

不建议继续大范围调 `regime_to_sleeve_weights`。优先做两件事：

1. 加一层 sleeve performance overlay：在 regime base weight 之上，根据每个 sleeve 过去 3/6 个月的 ICIR、收益/回撤、命中率做动态调节。
2. 对 2025 修复后的数据重跑 A/B/C 全策略对比，旧 2025 结果已经不能作为最终结论。

当前候选可以保留为 `C_regime_v2_candidate`，但只能进入下一轮全样本复验，不能直接替换生产配置。

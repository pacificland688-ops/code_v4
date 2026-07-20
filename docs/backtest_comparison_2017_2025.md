# 2017-2025 三策略回测验证报告

数据来源：`outputs/comparison/backtest_2017_2025/runs.csv`

对比对象：

- A 固定 5 反转：`configs/factors_5reversal.yaml`
- B 全因子动态 IC：`configs/factors_dynamic.yaml`
- C Regime 多 Sleeve：`configs/factors.yaml` + `configs/regime.yaml`

## 结论

这轮回测支持最初的问题判断：固定使用一套 5 个反转因子，不能通打 2017-2025 的市场环境。但它也说明，当前开发完成的 regime 多 sleeve 版本还不能直接判定为稳定 alpha。

C Regime 多 Sleeve 的平均年化超额为 -11.0%，好于 A 固定 5 反转的 -13.4%，也好于 B 全因子动态 IC 的 -14.7%。C 在 5/9 个年份胜出，并在 6/9 个年份跑赢 A。它的主要价值体现在 2020、2021、2022、2024 这类反转策略明显吃亏或市场状态变化较大的年份。

但 C 仍然是负平均超额，并且在 2018、2019、2023、2025 没有胜出。尤其 2023 年 A 超额 +1.0%，C 超额 -6.6%，C-A 为 -7.6%；2025 年 C 也没有解决大幅负超额问题。因此审核结论是：

**工程实现通过基础验证；策略效果进入参数诊断和 walk-forward 验证阶段；暂不建议 Go-live。**

## 年度结果

| 年份 | A 固定5反转超额 | B 动态IC超额 | C Regime超额 | 胜者 | C-A | 备注 |
|---:|---:|---:|---:|---|---:|---|
| 2017 | -20.1% | -22.3% | -18.6% | C Regime 多 Sleeve | +1.5% | regime 改善有限 |
| 2018 | -17.8% | -15.9% | -19.5% | B 全因子动态 IC | -1.7% | C 未改善 |
| 2019 | -7.7% | -3.7% | -13.6% | B 全因子动态 IC | -6.0% | C 明显落后 |
| 2020 | -22.9% | -15.3% | -8.7% | C Regime 多 Sleeve | +14.2% | regime 改善显著 |
| 2021 | -11.7% | -36.2% | -6.0% | C Regime 多 Sleeve | +5.7% | regime 改善有效 |
| 2022 | +5.7% | +1.3% | +9.4% | C Regime 多 Sleeve | +3.7% | C 胜出 |
| 2023 | +1.0% | -0.2% | -6.6% | A 固定 5 反转 | -7.6% | 需要重点诊断 |
| 2024 | -10.4% | -10.6% | +0.3% | C Regime 多 Sleeve | +10.7% | regime 改善显著 |
| 2025 | -36.3% | -29.7% | -35.4% | B 全因子动态 IC | +0.9% | C 接近 A，但不如 B |

## 汇总指标

| 策略 | 平均年化收益 | 平均年化超额 | 平均IR | 平均最大回撤 | 平均换手 | 正超额年份 | 年度胜出 |
|---|---:|---:|---:|---:|---:|---:|---:|
| A 固定 5 反转 | -9.9% | -13.4% | -1.23 | -20.3% | 48.7% | 2/9 | 1/9 |
| B 全因子动态 IC | -8.7% | -14.7% | -1.32 | -21.9% | 43.6% | 1/9 | 3/9 |
| C Regime 多 Sleeve | -4.1% | -11.0% | -1.12 | -21.2% | 42.4% | 2/9 | 5/9 |

## Regime 诊断

下表来自 C_regime run 中落盘的 `avg_regime_probs` 和 `avg_sleeve_weights`。这些诊断序列包含 warmup/OOS 过渡样本，适合解释 router 倾向，不应单独作为年度收益归因。

| 年份 | C 主导 Regime 概率 | C 主导 Sleeve 权重 | C 超额 | C-A | 诊断样本数 |
|---:|---|---|---:|---:|---:|
| 2017 | range_bound_prob 63.4% | reversal_weight 33.7% | -18.6% | +1.5% | 77 |
| 2018 | range_bound_prob 37.2% | reversal_weight 29.7% | -19.5% | -1.7% | 77 |
| 2019 | range_bound_prob 30.3% | defensive_weight 30.6% | -13.6% | -6.0% | 78 |
| 2020 | range_bound_prob 38.8% | reversal_weight 29.6% | -8.7% | +14.2% | 78 |
| 2021 | range_bound_prob 36.1% | reversal_weight 29.8% | -6.0% | +5.7% | 79 |
| 2022 | range_bound_prob 37.9% | defensive_weight 31.6% | +9.4% | +3.7% | 77 |
| 2023 | range_bound_prob 45.0% | reversal_weight 31.0% | -6.6% | -7.6% | 76 |
| 2024 | range_bound_prob 43.0% | reversal_weight 29.3% | +0.3% | +10.7% | 78 |
| 2025 | range_bound_prob 41.4% | reversal_weight 28.4% | -35.4% | +0.9% | 79 |

## 审核判断

1. A 固定 5 反转的问题被验证。9 年平均年化超额为 -13.4%，只有 2022、2023 两个正超额年份，2025 年超额为 -36.3%。
2. B 全因子动态 IC 不是充分解。它在 2018、2019、2025 优于 A，但 2021 明显崩坏，平均年化超额 -14.7%，弱于 A。
3. C Regime 多 Sleeve 是当前三者里方向最好的框架。它平均超额损失最小、年度胜出最多、平均换手最低，说明“不同市场状态使用不同 sleeve”的方向有价值。
4. C 仍未通过生产级策略验证。平均超额仍为负，且 2023、2025 两个关键失败样本必须解释清楚。
5. 当前 router 倾向偏保守。多数年份最高 regime 概率仍是 `range_bound_prob`，最高 sleeve 多数仍是 `reversal_weight`。这说明虽然架构从“单策略”变成了“多 sleeve”，但实际暴露可能仍然偏反转，没有真正充分切换到价值、趋势或防御。

## 下一步

1. 对 2023 和 2025 做归因拆解：按月输出 C 的 regime 概率、sleeve 权重、行业暴露、top holdings、相对基准收益，确认亏损来自 router 判断错误、sleeve 因子错误，还是组合约束导致的暴露偏差。
2. 做 walk-forward 参数网格：IC 窗口 3/6/12 月、sleeve 权重平滑半衰期、regime 概率温度、单 sleeve 上限。目标不是找最高收益，而是看 C-A 改善是否跨参数稳定。
3. 将 2026 YTD 单独跑成附录，不和 2017-2025 完整年度混合统计。
4. Go/No-Go 门槛建议设为：C 平均年化超额 > 0、C 胜出年份 >= 5/9、C-A 最差年份不低于 -5%、换手不高于 A，并且 2023/2025 失败原因有可解释修复。

## 2026 YTD 附录

2026 不能使用 `20261231` 作为结束日，因为本地 `prices_adj` 目前只覆盖到 2026-06-05，指数数据覆盖到 2026-06-08。实际 YTD 回测区间为 `20260101` 到 `20260605`。

修复前，三条策略都被 `NO_GO_DATA_INVALID` 拦截，异常来自 2026-02-27 的单期组合收益。根因是 `adj_factor/year=2026` 在 2026-03-06 前每天只有约 160-190 条记录，2026-03-09 起变成全覆盖；缺失复权因子的股票在前半段被补成 `adj_factor=1.0`，后半段切换为真实累计复权因子，导致 `adj_close` 在 2026-03-09 出现假跳变。例如：

| 股票 | 2026-03-02 close | 2026-03-09 close | 2026-03-02 adj_factor | 2026-03-09 adj_factor | 假收益 |
|---|---:|---:|---:|---:|---:|
| 000651.SZ | 37.20 | 37.33 | 1.0 | 230.3931 | +23020% |
| 600066.SH | 30.26 | 29.44 | 1.0 | 60.3874 | +5775% |
| 600653.SH | 1.91 | 1.89 | 1.0 | 10055.6396 | +994934% |

已完成修复：

- `adj_factor` 改为按交易日取全市场，避免 `start_date/end_date` 范围请求被 6000 行限制截断。
- Phase 0 使用真实月内交易日首尾作为复权因子请求边界，避免最终月份请求到未来交易日。
- Phase 0 在生成 `prices_adj` 前校验 `(ts_code, trade_date)` raw price 键是否都有复权因子。
- Phase 2 增加价格质量预检查，回测前拦截 `adj_close` 日/周跳变。
- `validate_adj_prices()` 的 raw/adj 比例检查改为“比例跳变”检查，不再把长期累计复权倍数大于 100 误判为错误。

修复后重新跑 `20260101` 到 `20260605`，产物位于 `outputs/comparison/backtest_2026_ytd_fixed/runs.csv`：

| 策略 | Run 目录 | 样本期数 | YTD总收益 | 年化收益 | 年化超额 | IR | 最大回撤 | Go/No-Go |
|---|---|---:|---:|---:|---:|---:|---:|---|
| A 固定 5 反转 | `outputs/runs/20260101_20260605_top50_20260609_094946` | 15 | +3.03% | +10.91% | +11.82% | 0.57 | -11.20% | NO-GO |
| B 全因子动态 IC | `outputs/runs/20260101_20260605_top50_20260609_095357` | 15 | +0.47% | +1.65% | +2.53% | 0.15 | -10.41% | NO-GO |
| C Regime 多 Sleeve | `outputs/runs/20260101_20260605_top50_20260609_095842` | 20 | +5.18% | +14.04% | +19.00% | 1.12 | -11.55% | NO-GO |

2026 YTD 修复后不再是数据无效，但仍不应和 2017-2025 完整年度混合统计。原因是样本不足 26 个周样本，系统仍标记为 `UNSTABLE`，三条策略整体为 `NO-GO`。在这个有限样本里，C Regime 多 Sleeve 暂时最好。

C_regime 的 2026 YTD router 倾向如下：`range_bound_prob` 平均 52.7%，`reversal_weight` 平均 34.4%，`volume_price_weight` 22.4%，`defensive_weight` 19.4%，`momentum_weight` 13.3%，`value_weight` 10.5%。即使修复数据后，当前 router 仍偏向震荡/反转暴露，这与正文中“实际切换力度不足”的判断一致。

## 复现命令

```powershell
python -X utf8 scripts/backtest_compare.py --years 2017 2018 2019 --tag backtest_2017_2025
python -X utf8 scripts/backtest_compare.py --years 2020 2021 2022 --tag backtest_2017_2025
python -X utf8 scripts/backtest_compare.py --years 2023 2024 2025 --tag backtest_2017_2025

# 2026 YTD 需使用真实可用行情结束日，不能用 20261231
python -X utf8 run_research.py phase0 --start 20260101 --end 20260605
python -X utf8 run_research.py phase1 --start 20260101 --end 20260605 --recompute
python -X utf8 run_research.py phase2 --start 20260101 --end 20260605 --top-n 50 --no-recompute --factors-config configs/factors_5reversal.yaml --strategy-mode factor_dynamic
python -X utf8 run_research.py phase2 --start 20260101 --end 20260605 --top-n 50 --no-recompute --factors-config configs/factors_dynamic.yaml --strategy-mode factor_dynamic
python -X utf8 run_research.py phase2 --start 20260101 --end 20260605 --top-n 50 --no-recompute --factors-config configs/factors.yaml --strategy-mode regime --regime-config configs/regime.yaml
```

关键产物：

- `outputs/comparison/backtest_2017_2025/runs.csv`
- `outputs/comparison/backtest_2017_2025/summary.md`
- `outputs/comparison/backtest_2026_ytd_fixed/runs.csv`
- `outputs/comparison/backtest_2026_ytd_fixed/summary.md`
- `outputs/runs/*/diagnostics/phase2_regime_probs.parquet`
- `outputs/runs/*/diagnostics/phase2_sleeve_weights.parquet`

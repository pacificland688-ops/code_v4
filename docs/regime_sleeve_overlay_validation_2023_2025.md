# Regime Sleeve Performance Overlay 验证：2023 / 2025

## 目的

上一轮完整 Phase 2 显示，`less_reversal_faster_switch` 能降低反转暴露，但 2025 价值因子强、组合仍然负超额，说明单靠静态 `regime -> sleeve` 映射不够。

本轮改造增加 `sleeve_performance_overlay`：在 regime 基础权重之上，根据每个 sleeve 近期已成熟的横截面 ICIR 和正 IC 命中率生成乘数，再交给 allocator 统一执行 floor、cap、min_sleeves 和平滑约束。

## 代码改动

- 新增 `alpha/sleeve_performance_overlay.py`
  - 计算每个 sleeve 的近期 realised IC。
  - 使用 `matured_ic_cutoff()`，只允许已成熟 forward return 进入窗口。
  - 输出 `{sleeve}_multiplier` 和长表 diagnostics。
- 修改 `alpha/regime_allocator.py`
  - `compute_sleeve_weights()` 新增可选 `sleeve_multipliers`。
  - 乘数在基础 mapping 后、约束和平滑前生效。
- 修改 `run_research.py`
  - `build_regime_composite()` 接入 overlay。
  - 诊断新增：
    - `phase2_sleeve_base_weights.parquet`
    - `phase2_sleeve_overlay_multipliers.parquet`
    - `phase2_sleeve_overlay_metrics.parquet`
- 修改 `configs/regime.yaml`
  - 新增 `sleeve_performance_overlay`，默认 `enabled: false`，保证 baseline 行为不变。
- 修改 `scripts/regime_parameter_grid.py`
  - 新增候选：
    - `performance_overlay`
    - `less_reversal_faster_overlay`
  - `runs.csv` 记录 overlay 平均乘数。

## 测试

已通过：

- `python -m py_compile alpha\sleeve_performance_overlay.py alpha\regime_allocator.py run_research.py scripts\regime_parameter_grid.py`
- `python -m pytest tests\test_sleeve_performance_overlay.py tests\test_regime_allocator.py tests\test_regime_no_leakage.py -q`
- `python -m pytest tests\test_regime_warmup_oos.py tests\test_regime_realistic_alignment_gate.py tests\test_regime_composite.py tests\test_regime_config_validation.py -q`
- `python -m pytest tests\test_diagnostic_artifacts.py tests\test_smoke_phase2_readonly.py -q`

合计覆盖：

- 正 IC sleeve 被放大，负 IC sleeve 被压缩。
- 历史不足时乘数保持中性。
- 修改未来 forward return 不影响当前乘数。
- allocator 未传乘数时保持旧行为。
- regime warmup、alignment、diagnostics 仍可用。

## Fast 诊断结果

Fast 引擎只用于筛方向，不替代完整 Phase 2。

| 年份 | 配置 | 年化超额 | IR | 最大回撤 | reversal | defensive | value | volume_price | reversal_x | value_x |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2023 | baseline | -0.3% | -0.01 | -21.8% | 31.1% | 28.4% | 14.9% | 18.1% |  |  |
| 2023 | less_reversal_faster_switch | +1.5% | +0.26 | -21.0% | 24.4% | 28.5% | 17.3% | 20.2% |  |  |
| 2023 | less_reversal_faster_overlay | +5.0% | +0.79 | -18.2% | 21.4% | 30.9% | 17.9% | 21.4% | 0.94 | 1.11 |
| 2025 | baseline | -24.6% | -2.06 | -14.6% | 29.1% | 19.7% | 16.0% | 22.4% |  |  |
| 2025 | less_reversal_faster_switch | -21.9% | -1.82 | -14.1% | 22.7% | 19.2% | 18.7% | 24.5% |  |  |
| 2025 | less_reversal_faster_overlay | -12.0% | -1.12 | -15.4% | 19.8% | 26.2% | 15.2% | 23.6% | 0.97 | 0.99 |

Fast 结论：overlay 对两个失败年都有方向性改善，尤其 2025 的简化 Top-N 回测改善很大。但 2025 的 `value_x` 平均只有 0.99，说明它并没有识别出“价值 sleeve 应该被显著放大”，而是更多放大了 defensive。

## 完整 Phase 2 结果

| 年份 | 配置 | 年化收益 | 年化超额 | IR | 最大回撤 | 换手 | reversal | defensive | value | volume_price | reversal_x | value_x |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2023 | baseline | -22.09% | -5.46% | -0.83 | -24.43% | 39.92% | 31.1% | 28.4% | 14.9% | 18.1% |  |  |
| 2023 | less_reversal_faster_switch | -20.91% | -3.98% | -0.61 | -23.60% | 35.83% | 24.4% | 28.5% | 17.3% | 20.2% |  |  |
| 2023 | less_reversal_faster_overlay | -18.27% | -0.71% | -0.11 | -20.65% | 31.92% | 21.4% | 30.9% | 17.9% | 21.4% | 0.94 | 1.11 |
| 2025 | baseline | +2.36% | -18.72% | -1.87 | -16.91% | 50.16% | 25.8% | 24.8% | 13.2% | 21.6% |  |  |
| 2025 | less_reversal_faster_switch | +2.69% | -18.44% | -1.79 | -16.27% | 48.20% | 19.9% | 23.9% | 15.1% | 24.1% |  |  |
| 2025 | less_reversal_faster_overlay | +2.53% | -18.55% | -1.73 | -16.91% | 47.73% | 19.8% | 26.2% | 15.2% | 23.6% | 0.97 | 0.99 |

## 判断

不建议 Go-live。

本轮 overlay 是正确的工程方向，但还不是充分修复：

- 2023 明显改善：相对上一轮最佳配置，年化超额从 -3.98% 提升到 -0.71%，IR 从 -0.61 提升到 -0.11，回撤和换手也下降。
- 2025 没有实质改善：相对上一轮最佳配置，年化超额从 -18.44% 变成 -18.55%，基本持平略差；IR 小幅改善但仍为 -1.73。
- Fast 与完整 Phase 2 在 2025 分歧很大，说明问题已经不只是 sleeve 权重。简化等权 Top50 能改善，但完整流程里的 tradable、持仓延续、成本、执行日、组合约束或基准暴露把改善吃掉了。

## 下一步

不要继续只调 `regime_to_sleeve_weights` 或 overlay 乘数参数。

下一步应做 2025 的 fast-vs-Phase2 差异归因：

1. 对同一 `less_reversal_faster_overlay` 配置，导出 fast Top50 与 Phase2 实际 holdings 的逐期交集、换手、行业、市值、beta、top holdings。
2. 拆解 2025 每周 period return：fast 选股收益、Phase2 持仓收益、基准收益、差异贡献。
3. 判断完整 Phase2 失败来自哪里：
   - 组合约束/持仓延续没有买到 fast 的高分股票。
   - 交易可行性过滤剔除了关键股票。
   - 行业/市值/beta 暴露与基准错配。
   - sleeve score 本身对完整持仓池有效，但 Top50 等权假设过强。
4. 只有确认差异来源后，才决定是修组合构建、调持仓缓冲，还是重新设计 sleeve 层 alpha。

本轮核心结论：动态 sleeve 权重能缓解 2023 的风格失配，但不能解决 2025。现在瓶颈已经从“市场趋势用不同策略”推进到“动态策略信号如何穿透到真实组合”。 

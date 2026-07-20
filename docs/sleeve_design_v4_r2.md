# Sleeve Design V4 R2 — Gate-Compliant Sleeve Architecture

生成日期：2026-06-15  
Regime 配置：`configs/regime_candidate_v4_r2.yaml`  
候选池：`configs/factors_candidate_v4_r2.yaml`

## 1. 设计原则

V4-r2 sleeve 设计遵循以下原则（按优先级）：

1. **不引用不合格因子**：所有 sleeve 因子必须存在于 r2 enabled_factors 或明确标记为 neutralizer。
2. **WATCH 因子仅用于 defensive**：`volatility_60_cs`（WATCH_NEUTRAL_ONLY）只能分配到 defensive sleeve。
3. **默认关闭 overlay**：per plan §6.4，先验证 alpha 和 sleeve 本身，不引入 sleeve_performance_overlay。
4. **空 sleeve 显式保留**：无合规因子的 sleeve 保留结构但标记为空，便于 M4 后填充。
5. **与 r1 可追踪差异**：每个变更都有明确原因。

## 2. 与 V4-r1 的差异

| 维度 | V4-r1 | V4-r2 | 变更原因 |
|------|------|------|------|
| value sleeve | ep_cs, bp_cs, sp_cs, industry_relative_ep_cs, industry_relative_bp_cs | 空（全部 FAIL） | gate FAIL (LEAKAGE_METADATA_MISSING) |
| growth sleeve | revenue_growth_ttm_cs, profit_growth_ttm_cs, earnings_acceleration_cs, growth_stability_8q_cs | 空（PENDING_GATE） | 输入审计 FAIL → 修复后待 M4 gate |
| momentum sleeve | momentum_60_skip5_cs, momentum_120_skip20_cs, risk_adjusted_momentum_60_cs, volume_confirmed_momentum_cs, trend_quality_cs, industry_relative_momentum_60_cs, pv_divergence_20_cs | 空（全部 FAIL） | gate FAIL（IC/ICIR 不足） |
| defensive sleeve | volatility_60_cs, log_market_cap_cs, ep_cs, bp_cs, industry_relative_ep_cs | volatility_60_cs, log_market_cap_cs | 移除 FAIL 因子，保留 WATCH + neutralizer |
| reversal sleeve | reversal_5_cs, pv_divergence_20_cs | 空（全部 FAIL） | gate FAIL |
| volume_price sleeve | pv_divergence_20_cs, volume_confirmed_momentum_cs, trend_quality_cs, industry_relative_momentum_60_cs | 空（全部 FAIL） | gate FAIL |
| performance_overlay | enabled: false | enabled: false | 维持关闭 |
| min_sleeves | 2 | 1 | 仅 defensive 有合规因子 |
| fundamental_factors | 10 个因子 | 1 个 (log_market_cap_cs) | 其他全部 FAIL |

## 3. Sleeve 状态矩阵

| Sleeve | 合规因子数 | 状态 | 说明 |
|------|------:|------|------|
| defensive | 2 (1 WATCH + 1 neutralizer) | ✅ 可用 | 唯一有合规因子的 sleeve |
| growth | 0 (4 PENDING_GATE) | ⏳ 待 M4 | 4 个 growth 因子等待 gate 重跑 |
| value | 0 | ❌ 空 | 所有 value 因子 FAIL |
| momentum | 0 | ❌ 空 | 所有 V4 momentum 因子 FAIL |
| reversal | 0 | ❌ 空 | 所有 reversal 因子 FAIL |
| volume_price | 0 | ❌ 空 | 所有 volume/price 因子 FAIL |

## 4. 当前局限

V4-r2 的 sleeve 架构面临一个根本性局限：**只有 defensive sleeve 有合规因子**。这意味着：

1. 策略实际上退化为一个 defensive-only 配置。
2. 这不是一个可接受的 alpha 策略。
3. M4 gate 重跑后，如果 growth 因子通过 gate，可以恢复 growth sleeve。
4. 如果 M4 后仍只有 defensive sleeve，应按开发方案退出条件停止。

## 5. M4 后更新计划

M4 gate 重跑后：

1. 将 PASS 的 growth 因子添加到 growth sleeve。
2. 如果其他类别有因子 PASS，添加对应 sleeve。
3. 更新 allocator 权重。
4. 更新 `fundamental_factors` 列表。
5. 更新本文档。

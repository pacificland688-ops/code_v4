# Factor Signal Alignment — 统一口径与去留判断

生成日期：2026-06-11  
目的：统一 Phase1 IC、weekly aligned IC、Top50 经济收益三层口径，给出因子去留的明确建议。

## 1. 三层口径定义

| 层次 | 指标 | 含义 | 当前状态 |
|------|------|------|---------|
| Phase1 IC | 横截面 rank IC (Spearman) | 因子排序与未来收益的相关性 | 仅 ep/bp/sp 通过门槛 |
| Weekly Aligned IC | PIT 对齐后周频 IC | 实际可用信号的预测能力 | 与 Phase1 一致（无前视泄漏） |
| Top50 经济收益 | Top-bottom 组合年化收益 | 选股策略实际可获取的收益 | 扣成本后更弱 |

## 2. 当前因子状态总表

### 2.1 因子通过情况

| 因子 | Sleeve | IC 均值 | ICIR | 正向率 | Top-Bottom 收益 | PIT 审计 | 判断 |
|------|--------|--------:|-----:|-------:|---------------:|---------|------|
| ep_cs | value | ~0.030 | ~0.35 | ~55% | 正(薄) | ✅ | **保留** |
| bp_cs | value | ~0.025 | ~0.30 | ~54% | 正(薄) | ✅ | **保留** |
| sp_cs | value | ~0.022 | ~0.28 | ~53% | 正(薄) | ✅ | **保留** |
| pv_divergence_20_cs | reversal/volume_price/momentum | ~0.020 | ~0.25 | ~52% | 近零 | ✅ | **保留（边际）** |
| reversal_5_cs | reversal | ~0.015 | ~0.18 | ~50% | 不稳定 | ✅ | **降权或移除** |
| reversal_20_cs | reversal/defensive | ~0.012 | ~0.15 | ~49% | 不稳定 | ✅ | **降权或移除** |
| momentum_120_cs | momentum | ~0.018 | ~0.22 | ~51% | 弱 | ✅ | **需要重设计** |
| momentum_60_cs | momentum/volume_price | ~0.015 | ~0.18 | ~50% | 弱 | ✅ | **需要重设计** |
| rsi_14_cs | reversal | ~0.010 | ~0.12 | ~50% | 近零 | ✅ | **移除** |
| volatility_20_cs | defensive/volume_price | ~0.008 | ~0.10 | ~49% | 负或无 | ✅ | **移出 alpha，改风险约束** |
| volatility_60_cs | defensive | ~0.006 | ~0.08 | ~48% | 负或无 | ✅ | **移出 alpha，改风险约束** |
| macd_12_26_9_cs | momentum/volume_price | ~0.005 | ~0.06 | ~48% | 近零 | ✅ | **移除** |

### 2.2 核心问题：Alpha 池过于依赖 3 个 Value 因子

当前 5 个 sleeve 共使用 12 个因子（去重后），但仅 3 个 value 因子通过 IC 门槛。其余 9 个因子要么 IC 弱，要么不稳定，要么只适合做风险约束。

**影响链：**
- range_bound 主导（60% prob） → 高配 reversal（45%） → reversal 因子 3/4 不通过 → 组合 alpha 被稀释
- trend_up 场景 → 动量主导（45%） → momentum 因子全部弱 → 即使趋势判断正确也抓不到收益
- defensive 场景 → 低波主导（45%） → vol 因子不适合作 alpha → 防御配置实际上在降低收益而非控制风险

## 3. 因子审计详细发现

### 3.1 Value 因子（ep_cs, bp_cs, sp_cs）

**优势：**
- IC 最稳定，3 因子均通过所有门槛。
- 在多数年份提供正（虽然薄）的 alpha。
- PIT 无泄漏。

**问题：**
- `factors.yaml` 中标记为 disabled（原因是 "Fundamental data gaps cause coverage issues"）。
- 当前 regime value sleeve 绕过了 `enabled_factors`，直接使用 `ep_cs, bp_cs, sp_cs`。
- 基本面数据按季更新，存在公告滞后（as-of lag 平均 15-16 天）。
- `factor_alignment.fundamental_max_stale_trading_days: 63` — 允许 63 天过期，可能导致用到过时的基本面数据。

**建议：**
1. 将 `ep_cs, bp_cs, sp_cs` 移回 `enabled_factors`。
2. 收紧 fundamental_max_stale_trading_days 至 45 天（约 2 个月）。
3. 使用 ann_date（公告日期）而非 report_date 作为 PIT 可用日期。
4. 增加 value 因子细分（如 ep_ttm vs ep_fy1, bp_latest vs bp_mrq）。

### 3.2 Reversal 因子（reversal_5_cs, reversal_20_cs）

**问题：**
- IC 正向率接近 50%（近乎随机）。
- 在趋势市中系统性地逆势操作。
- 2017、2019、2020 等强势年份中，高配 reversal 是 D 跑输的主因之一。

**建议：**
1. 将 reversal 从 alpha 候选降为 regime overlay 的可选 sleeve。
2. 仅在 range_bound 和高概率识别为震荡的周期中启动。
3. 与 momentum 信号交叉验证（若动量强于反转，则降低反转权重）。

### 3.3 Momentum 因子（momentum_60_cs, momentum_120_cs）

**问题：**
- IC 和 ICIR 均未通过门槛。
- 当前设计（60 天 / 120 天）可能不适合 A 股。
- 缺乏 skip_recent 处理（momentum_60 有 skip_recent=20 但 momentum_120 skip_recent=20 不够）。

**建议：**
1. 重新设计 momentum 因子：
   - 使用 3-12-1 结构（skip 1 month, measure 11 months），去掉最近一个月以消除短期反转效应。
   - 增加成交量和波动率调整的动量因子。
2. 在重新设计之前，将 momentum_60_cs 和 momentum_120_cs 从 sleeve 中移除。
3. 考虑用价格路径一致性（price path consistency）替代传统动量。

### 3.4 Volatility 因子（volatility_20_cs, volatility_60_cs）

**问题：**
- IC 和 ICIR 均极低（<0.10 ICIR）。
- 低波异象（low-vol anomaly）在 A 股的证据有限且不稳定。
- 当前同时作为 alpha 因子和风险控制工具使用，语义混乱。

**建议：**
1. 将 volatility 因子从 alpha 候选池中移除。
2. 在组合构建层作为风险约束使用（限制组合加权波动率与基准的偏离）。
3. 若保留在 defensive sleeve 中，将其角色从 "alpha 来源" 改为 "波动率排序（避雷）"。

### 3.5 Size 因子（log_market_cap_cs）

**状态：** 已正确用作 neutralizer 而非 alpha 因子。

**建议：** 保持不变。同时考虑增加市值约束（组合加权市值与 CSI300 的偏离限制）。

## 4. Factor-to-Sleeve 映射重构建议

### 4.1 当前映射问题

| Sleeve | 当前因子 | 有效因子 | 无效/弱因子 |
|--------|---------|---------|------------|
| reversal | reversal_5, reversal_20, rsi_14, pv_divergence_20 | 1 (pv) | 3 |
| momentum | momentum_60, momentum_120, macd, pv_divergence_20 | 1 (pv) | 3 |
| defensive | volatility_20, volatility_60, reversal_20 | 0 | 3 |
| value | ep, bp, sp | **3** | 0 |
| volume_price | pv_divergence_20, macd, momentum_60, volatility_20 | 1 (pv) | 3 |

**4/5 sleeve 主要依赖无效或弱因子！** 只有 value sleeve 的因子池质量是可靠的。

### 4.2 建议重构

| Sleeve | 新因子池 | 理由 |
|--------|---------|------|
| reversal | pv_divergence_20_cs, reversal_5_cs（仅当 momentum 弱时） | 缩小至有信号的因子 |
| momentum | **新 momentum 因子**, pv_divergence_20_cs | 重设计后使用 |
| defensive | **roe_cs, gross_margin_cs**（质量因子）, volatility_20_cs（风控） | 从 alpha 转向质量+风控 |
| value | ep_cs, bp_cs, sp_cs, **ep_ttm_cs, bp_mrq_cs** | 保持并扩展 |
| volume_price | pv_divergence_20_cs, **资金流因子（待设计）** | 当前仅 1 个有效因子 |

### 4.3 新因子候选

**优先级 P0（对当前策略最急需）：**

1. **质量因子组（roy, gross_margin, profit_stability）**
   - 当前 defensive sleeve 完全缺乏优质 alpha 来源
   - 质量因子通常与 value 因子低相关，提供分散化
   - 需要在 PIT 对齐后（使用 ann_date）再进入 alpha 池

2. **动量因子重设计（momentum_3_12_1）**
   - 跳过最近 1 月（skip_recent=20）
   - 使用 t-20 到 t-240（11 个月窗口）
   - 增加成交量确认

**优先级 P1（扩展 alpha 池）：**

3. **盈利质量因子（accruals, cash_flow_quality）**
   - 应计利润 / 现金流质量
   - A 股中盈利质量因子的实证支持

4. **分析师预期因子（earnings_revision, target_price_change）**
   - 需要获取分析师数据源

## 5. 建议立即执行的配置变更

### 5.1 最小可行变更（不新增因子，仅调整现有）

```yaml
# configs/factors.yaml: 将 value 因子从 disabled 移到 enabled
enabled_factors:
  - ep_cs
  - bp_cs
  - sp_cs
  - pv_divergence_20_cs

# configs/regime.yaml: 缩小无效因子在各 sleeve 中的使用
strategy_sleeves:
  reversal:
    factors:
      - pv_divergence_20_cs       # 移除 rsi_14, reversal_20, 仅保留有边际信号的
      - reversal_5_cs
  
  momentum:
    factors:
      - pv_divergence_20_cs       # 移除 momentum_60/120, macd (均未通过)
  
  defensive:
    factors:
      - volatility_20_cs           # 改为风控角色（低波不代表 alpha）
      - ep_cs                      # 增加价值暴露提供防御
      - bp_cs
  
  value:
    factors:
      - ep_cs
      - bp_cs
      - sp_cs
  
  volume_price:
    factors:
      - pv_divergence_20_cs       # 移除 macd, momentum_60, volatility_20
```

### 5.2 推荐候选配置

基于以上分析，建议 3 个候选配置：

1. **`factors_candidate_v1.yaml`**: 最小清理（移除明确无效因子，保留当前结构）
2. **`factors_candidate_v2.yaml`**: v1 + 质量因子（roe, gross_margin）进入 defensive sleeve
3. **`factors_candidate_v3.yaml`**: v2 + 动量因子重设计 + 价值因子细分

## 6. 验收标准

每个因子变更后必须通过：

| 检查 | 标准 |
|------|------|
| PIT 审计 | future_obs = 0 |
| IC 正向率 | ≥ 52%（单个因子） |
| ICIR | ≥ 0.30（单个因子） |
| 失败年份 IC | 不集中在单一年份 |
| 与现有因子相关性 | < 0.7（避免冗余） |
| Cost 2x | 收益不灾难性消失 |

# Candidate Freeze Log

生成日期：2026-06-11  
目的：记录每个候选配置的假设、冻结时间和验证结果。

## 候选概览

| 候选 | 文件 | 类型 | 变更范围 | 冻结日期 |
|------|------|------|---------|---------|
| v1 | `configs/factors_candidate_v1.yaml` | 因子清理 | 启用 value 因子，移除弱技术因子 | 2026-06-11 |
| v1 | `configs/regime_candidate_v1.yaml` | Sleeve 清理 | 移除 sleeve 中无效因子 | 2026-06-11 |
| v2 | `configs/regime_candidate_v2.yaml` | Allocator 调整 | 降低 reversal 权重，提升 value/trend | 2026-06-11 |
| v3 | `configs/regime_candidate_v3.yaml` | Overlay 启用 | v2 + sleeve_performance_overlay | 2026-06-11 |

## factors_candidate_v1

### 修改了什么
- 启用 `ep_cs, bp_cs, sp_cs` (从 disabled → enabled)
- 保留 `reversal_5_cs, pv_divergence_20_cs`
- 移除 `reversal_20_cs, rsi_14_cs, volatility_20_cs`
- enabled_factors: [ep_cs, bp_cs, sp_cs, reversal_5_cs, pv_divergence_20_cs]

### 为什么修改
- Value 因子是通过所有 IC 门槛的唯一稳定 alpha 来源
- 当前配置将它们放在 disabled 中（"fundamental data gaps"），但 regime value sleeve 仍在使用它们
- 技术因子中仅 pv_divergence_20 通过边际门槛
- Reversal_20 与 reversal_5 高度相关但 IC 更弱

### 预期改善
- 2017/2019/2021：减少弱因子的噪音稀释
- 所有年份：composite score 质量提升

### 可能伤害
- 2022：reversal 在偏熊市中提供了分散化，移除后可能降低防御多样化

### PIT/数据假设
- 不变

---

## regime_candidate_v1

### 修改了什么
- reversal sleeve: 移除 rsi_14_cs
- momentum sleeve: 移除 macd_12_26_9_cs
- defensive sleeve: 移除 volatility_60_cs, reversal_20_cs (仅保留 volatility_20_cs)
- volume_price sleeve: 移除 macd_12_26_9_cs, momentum_60_cs
- sleeve_composite.min_active_factors: 2→1 (某些 sleeve 只有 1-2 因子)

### 为什么修改
- 每个 sleeve 应只包含在该市场状态下有实证 alpha 的因子
- 4/5 sleeve 当前包含大量 IC 未通过门槛的因子
- 减少无效因子避免稀释 composite score

### 预期改善
- 所有年份：更干净的信号，更少的噪音

### 可能伤害
- Defensive sleeve 因子数从 3→1，可能在某些场景下不够稳健

### PIT/数据假设
- 不变

---

## regime_candidate_v2

### 修改了什么
- range_bound 映射: reversal 0.45→0.30, value 0.10→0.20, momentum 0.05→0.10
- trend_up 映射: reversal 0.10→0.05, volume_price 0.25→0.30, value 0.10→0.15
- trend_down 映射: defensive 0.45→0.50, value 0.20→0.25, reversal 0.20→0.10
- high_volatility 映射: defensive 0.50→0.55, reversal 0.20→0.10

### 为什么修改
- Range-bound 不应天然高配 reversal（2017/2019/2021 年教训）
- Value 因子在多数市场状态中提供正 alpha，应获得更高的基础权重
- Trend-up 场景中需要更果断的 momentum+volume_price 配置
- Reversal 在实证中仅在部分震荡市有效，不是全年稳定收益来源

### 预期改善
- 2017/2019：降低 reversal 拖累，value 在牛市中至少不反向
- 2021：更均衡的 sleeve 配置应对风格切换
- 2022：value 在熊市中相对稳健

### 可能伤害
- 在真正以 reversal 为主导的震荡市中，alpha 可能下降

### PIT/数据假设
- 不变

---

## regime_candidate_v3

### 修改了什么
- 启用 `sleeve_performance_overlay` (strength=0.40, 保守)
- 收紧 `fundamental_max_stale_trading_days`: 63→45

### 为什么修改
- Performance overlay 提供数据驱动的第二层调节
- 结合 regime router 判断和 sleeve 近期实际表现
- 保守 strength=0.40 降低过拟合风险（网格最佳为 0.50）
- 收紧基本面过期容忍度降低过时财务数据风险

### 预期改善
- 2021：风格切换时 overlay 可帮助更快调整
- 所有年份：use higher IC momentum for better sleeves

### 可能伤害
- 2018：若 overlay 在熊市中追逐近期 "表现好" 的策略，可能反向操作
- 增加复杂度，可能引入新的不稳定因素

### PIT/数据假设
- 不变（overlay 仅使用已成熟的 forward return）
- 收紧 staleness 可能略微减少 value 因子的覆盖率

---

## 验证计划

### 诊断集（2023/2025）
1. 对每个候选，先用 2023 和 2025 做诊断验证
2. 确认失败场景（2023 range-bound 高配 reversal、2025 fast vs Phase2 分歧）是否有改善
3. 不基于诊断集结果修改候选（仅确认方向正确）

### 正式验证（2017-2024 冻结）
1. 对诊断集中方向正确的候选，冻结后跑 2017-2024 全量
2. 跑 2026 YTD 前瞻观察
3. 产出 GO/NO-GO

### 验证命令模板
```powershell
# Diagnostic
python run_research.py phase2 --start 20230101 --end 20231231 --top-n 50 --no-recompute --factors-config configs/factors_candidate_v1.yaml --strategy-mode regime --regime-config configs/regime_candidate_v2.yaml

# Frozen validation
python run_research.py phase2 --start 20170101 --end 20171231 --top-n 50 --no-recompute --factors-config configs/factors_candidate_v1.yaml --strategy-mode regime --regime-config configs/regime_candidate_v2.yaml
```

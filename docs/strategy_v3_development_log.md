# Strategy V3 开发日志

生成日期：2026-06-14  
候选策略：`F_candidate_v3`  
前置计划：`docs/strategy_v3_development_plan.md`  
最终判定：**NO-GO**（未达到任何正式 GO 门槛）

## 1. 开发时间线

| 日期 | 阶段 | 关键活动 | 输入 | 输出 | 判定 |
|------|------|------|------|------|------|
| 2026-06-11 | 方案 | 制定 V3 开发计划 | V2 NO-GO 结论、regime grid 分析 | `docs/strategy_v3_development_plan.md` | 进入开发 |
| 2026-06-11 | 配置 | 创建 `regime_candidate_v3.yaml` | `regime_candidate_v2.yaml`、overlay grid 结果 | `configs/regime_candidate_v3.yaml` | 配置完成 |
| 2026-06-11 | 注册 | 注册 `F_candidate_v3` 到冻结回测脚本 | `regime_candidate_v3.yaml`、`factors_candidate_v1.yaml` | `frozen_backtest_validation.py` 更新 | 注册完成 |
| 2026-06-11 | 冒烟 | 单年冒烟回测 2023 | V3 配置 | `outputs/validation/candidate_v3_smoke/` | 可运行 |
| 2026-06-11~12 | 验证 | 2017-2024 + 2026 YTD 完整冻结验证 | V3 配置 | `outputs/validation/candidate_v3/runs.csv` | 验证完成 |
| 2026-06-12 | 审核 | V3 完成情况审核 | 全部产物 | `docs/strategy_v3_completion_review.md` | 工程通过，策略 NO-GO |
| 2026-06-13 | 决策 | 更新 GO/NO-GO 决策文档 | V3 runs.csv | `docs/go_nogo_decision.md` | NO-GO 确认 |
| 2026-06-14 | 归档 | 补齐 V3 vs V2 比较 + 开发日志 | 审核反馈 | `docs/candidate_v3_vs_v2_comparison.md`、本文档 | 归档完成 |

## 2. 关键命令记录

### 2.1 冒烟验证

```powershell
python -X utf8 scripts\frozen_backtest_validation.py --strategies F_candidate_v3 --years 2023 --force --out-dir outputs\validation\candidate_v3_smoke
```

结果：退出码 0，冒烟通过。

### 2.2 完整冻结验证

```powershell
python -X utf8 scripts\frozen_backtest_validation.py --strategies F_candidate_v3 --force
```

覆盖年份：2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2026

### 2.3 GO/NO-GO 决策生成

```powershell
python -X utf8 scripts\generate_go_nogo_decision.py --runs outputs\validation\frozen_backtest\runs.csv outputs\validation\candidate_v2\runs.csv outputs\validation\candidate_v3\runs.csv
```

### 2.4 全量测试

```powershell
python -X utf8 -m pytest -q
```

结果：621 passed, 18 warnings

### 2.5 缓存审计

```powershell
python -X utf8 scripts\audit_cache.py --start 20170101 --end 20241231 --verbose
python -X utf8 scripts\audit_cache.py --start 20260101 --end 20260605 --verbose
```

结果：无 FAIL，各有 WARN。

## 3. V3 配置核心变更

| 变更项 | V2 值 | V3 值 | 理由 |
|------|------|------|------|
| `sleeve_performance_overlay.enabled` | false | true | 启用数据驱动的 sleeve 权重调节 |
| `sleeve_performance_overlay.strength` | N/A | 0.40 | 保守强度，低于网格最佳 0.50 |
| `fundamental_max_stale_trading_days` | 63 | 45 | 收紧约 2 个月，降低财务数据过时风险 |

## 4. V3 验证结果摘要

| 指标 | V2 | V3 | GO 门槛 | 通过？ |
|------|------:|------:|------:|:------:|
| 平均年化超额 | -1.2% | -0.3% | > 2.0% | ❌ |
| 中位数年化超额 | -2.8% | -1.2% | > 0.0% | ❌ |
| 正超额年份 | 3/8 | 4/8 | >= 5/8 | ❌ |
| 平均 IR | -0.21 | -0.11 | > 0.30 | ❌ |
| 最大单年超额亏损 | -15.8% | -15.0% | > -10.0% | ❌ |

## 5. 阻塞问题与后续方向

### 阻塞问题

1. **底层 alpha 池质量不足**：现有 5 因子池（ep_cs, bp_cs, sp_cs, reversal_5_cs, pv_divergence_20_cs）无法覆盖全部市场环境
2. **2017 年根本性失败**：-15.0% 超额亏损，成长风格完全缺失
3. **2023/2024 持续负超额**：近年环境适应性不足
4. **overlay 改善有限**：再分配不能创造 alpha，只能优化配置

### 后续方向

- **V4 Alpha 重建**：扩展因子池（质量、现金流、成长、估值修复、行业相对强弱、风险调整动量）
- **不继续 overlay 调参**：V3 已证明此路有限
- **不降低门槛**：V4 沿用相同 GO 门槛

## 6. 产物清单

| 产物 | 路径 | 状态 |
|------|------|------|
| V3 配置 | `configs/regime_candidate_v3.yaml` | 已交付 |
| V3 策略注册 | `scripts/frozen_backtest_validation.py`（F_candidate_v3） | 已交付 |
| V3 冻结验证 | `outputs/validation/candidate_v3/runs.csv` | 已交付 |
| V3 完成审核 | `docs/strategy_v3_completion_review.md` | 已交付 |
| V3 vs V2 比较 | `docs/candidate_v3_vs_v2_comparison.md` | 已交付（2026-06-14 补齐） |
| V3 开发日志 | `docs/strategy_v3_development_log.md` | 本文档（2026-06-14 补齐） |
| GO/NO-GO 决策 | `docs/go_nogo_decision.md` | 已交付 |

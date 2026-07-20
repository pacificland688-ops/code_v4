# V4 Growth 因子重复键根因诊断报告

生成日期：2026-06-15  
诊断对象：`revenue_growth_ttm_cs`, `profit_growth_ttm_cs`, `growth_stability_8q_cs`, `earnings_acceleration_cs`  
诊断工具：`scripts/diagnose_factor_duplicates.py`

## 1. 问题摘要

2017-2024 缓存审计结果：

| 因子 | 总行数 | 日期数 | 重复行数 | 重复率 |
|------|------:|------:|------:|------:|
| earnings_acceleration_cs | 6,385 | 468 | 3,705 | 58.0% |
| growth_stability_8q_cs | 6,385 | 468 | 3,705 | 58.0% |
| profit_growth_ttm_cs | 6,935 | 513 | 4,355 | 62.8% |
| revenue_growth_ttm_cs | 6,935 | 513 | 4,355 | 62.8% |

2026 YTD 缓存审计结果：

| 因子 | 总行数 | 日期数 | 重复行数 | 重复率 |
|------|------:|------:|------:|------:|
| earnings_acceleration_cs | 488 | 41 | 239 | 49.0% |
| growth_stability_8q_cs | 488 | 41 | 239 | 49.0% |
| profit_growth_ttm_cs | 488 | 41 | 239 | 49.0% |
| revenue_growth_ttm_cs | 488 | 41 | 239 | 49.0% |

## 2. 根因分析

### 2.1 核心原因：PIT 展开后缺少去重

重复键来源于 `scripts/build_alpha_factors_v4.py` 第 796-802 行的 PIT（Point-in-Time）展开逻辑：

```python
# Line 797-800
if "available_date" in df.columns and not prices.empty:
    trade_dates = prices[["ts_code", "trade_date"]].drop_duplicates()
    df = df.merge(trade_dates, on="ts_code", how="inner")       # ① 笛卡尔积
    df = df[df["trade_date"] >= df["available_date"]]            # ② PIT 过滤
    df["pit_lag_days"] = df["trade_date"] - df["available_date"]
    df["is_stale"] = df["pit_lag_days"] > 63
```

问题链路：

1. **因子计算阶段**：`_compute_growth_ttm()` 按 `(ts_code, available_date)` 分组计算，每个分组输出一行。一家公司每季度发布一次财报，产生一个新的 `available_date`，因此每年有 4 行（4 个 `available_date`）。

2. **PIT 合并阶段**：第 799 行的 `merge(trade_dates, on="ts_code", how="inner")` 是对 `ts_code` 做 **inner join**，结果是一个 **笛卡尔积**：每个 `(ts_code, available_date)` 与该公司所有的 `trade_date` 配对。

3. **PIT 过滤阶段**：第 800 行 `df[df["trade_date"] >= df["available_date"]]` 过滤掉 `trade_date` 早于 `available_date` 的行（未来数据），但保留了所有 `trade_date >= available_date` 的行。

4. **重复产生**：对于任意 `trade_date = T`，所有满足 `available_date <= T` 的财报记录都会保留。例如：
   - Q1 报告 `available_date = 20200430`
   - Q2 报告 `available_date = 20200830`
   - Q3 报告 `available_date = 20201030`
   
   对于 `trade_date = 20201101`，三条记录都满足 `available_date <= trade_date`，因此产生 3 行。

5. **无去重步骤**：合并后没有任何 `.drop_duplicates(["ts_code", "trade_date"])` 调用。数据直接进入 CS 处理和缓存写入。

### 2.2 为什么影响特别大

Growth 因子的重复率 (~58%) 远高于普通因子，原因：

- **季度财报频率高**：每个 `available_date` 覆盖的 `trade_date` 范围很长（从公告日到下一季度公告日之前）。4 个季度的数据同时有效于大部分交易日，使得大部分 `(ts_code, trade_date)` 有 3-4 条记录。
- **min_quarters 参数宽松**：`growth_stability_8q_cs` 的 `min_quarters=5` 允许在数据不完整时继续计算，增加了半覆盖状态的记录数。
- **PIT lag 累积**：`available_date` 到 `end_date` 之间已有 30-120 天偏移，PIT 展开进一步拉长了有效期。

### 2.3 技术分类

| 重复场景 | 占比估计 | 说明 |
|------|------:|------|
| report_period_overlap | ~95% | 多个报告期的 `available_date` 同时有效于同一 `trade_date` |
| ann_date_revision | ~3% | 同一报告期多次公告修订，产生不同 `available_date` |
| identical_or_meta_dup | ~2% | 完全相同的数据行（仅 `pit_lag_days` 等元数据列不同） |

## 3. 修复方案

### 3.1 核心修复：PIT 展开后去重

在 `build_alpha_factors_v4.py` 第 800 行之后增加去重逻辑：

```python
# After PIT merge and filter (line 800):
df = df[df["trade_date"] >= df["available_date"]]

# NEW: Dedup — keep the most recent available_date per (ts_code, trade_date)
df = df.sort_values(["ts_code", "trade_date", "available_date"])
df = df.drop_duplicates(["ts_code", "trade_date"], keep="last")

df["pit_lag_days"] = df["trade_date"] - df["available_date"]
df["is_stale"] = df["pit_lag_days"] > 63
```

### 3.2 去重规则

| 场景 | 去重规则 | 实现 |
|------|------|------|
| 同股票同交易日多个报告期 | 选择 `available_date <= trade_date` 中最新的 `available_date` | `drop_duplicates(keep="last")` 按 `available_date` 排序后 |
| 同报告期多个公告修订 | 选择最新 `available_date` | 同上 |
| forward-fill 后重复 | 已在 PIT 展开时处理 | N/A（V4 不做 forward-fill） |
| 分区 append 重复 | `--force` 模式覆盖写，不 append | 已满足 |
| 值完全相同重复 | 仍必须去重，不能保留多行 | `drop_duplicates` 覆盖此场景 |

### 3.3 最终断言

在 `_write_factor_cache()` 调用前增加：

```python
assert not df.duplicated(["ts_code", "trade_date"]).any(), \
    f"FATAL: {fname} has {df.duplicated(['ts_code', 'trade_date']).sum()} duplicate (ts_code, trade_date) keys"
```

### 3.4 缓存清理

由于 V4 构建脚本使用 `year={YEAR}/part_{YEAR}.parquet` 覆盖写模式，使用 `--force` 重新构建即可自动覆盖旧数据。不需要单独清理步骤。

## 4. 验证命令

修复后运行：

```powershell
python -X utf8 scripts\build_alpha_factors_v4.py --config configs\factor_build_v4.yaml --start 20170101 --end 20241231 --force --factors revenue_growth_ttm_cs profit_growth_ttm_cs growth_stability_8q_cs earnings_acceleration_cs
python -X utf8 scripts\build_alpha_factors_v4.py --config configs\factor_build_v4.yaml --start 20260101 --end 20260605 --force --factors revenue_growth_ttm_cs profit_growth_ttm_cs growth_stability_8q_cs earnings_acceleration_cs
python -X utf8 scripts\diagnose_factor_duplicates.py --factors revenue_growth_ttm_cs profit_growth_ttm_cs growth_stability_8q_cs earnings_acceleration_cs --start 20170101 --end 20241231
```

预期结果：4 个因子均为 `CLEAN`，`dup_count = 0`。

## 5. 结论

Growth 因子重复键的根因是 **PIT 展开逻辑没有对 `(ts_code, trade_date)` 去重**。因子计算阶段按 `(ts_code, available_date)` 输出，PIT merge 将其展开到所有 `trade_date`，但在多个 `available_date` 同时有效的时间段内产生重复。修复只需在 PIT merge 后增加 `drop_duplicates` + `keep="last"` 并按 `available_date` 排序即可。

此修复同时适用于所有通过 PIT 展开的基本面因子，不限于 growth 因子。

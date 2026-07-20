# Factor Quality Rebuild V4 — Reproducibility Fix Plan

生成日期：2026-06-18

## 1. 背景与问题诊断

### 1.1 当前状态

V4 扩展因子质量重建流水线完成了主体开发，但存在多项可复现性问题：

- **V4 全量报告** (`factor_quality_rebuild_v4_report.md`, 2026-06-16) 显示 fundamental 因子的 `data_lag_days=0`，触发 `LEAKAGE_METADATA_MISSING`
- **V4 Growth 子集运行** (`outputs/analysis/factor_quality_rebuild_v4_growth/`, 2026-06-16) 显示 `date_semantics=observation_date`，与当前 `configs/factor_quality_rebuild_v4.yaml` 中的 `date_semantics=pit_aligned` 不一致
- **当前 V4 配置** (`configs/factor_quality_rebuild_v4.yaml`) 同时设置了 `date_semantics: pit_aligned` 和 `data_lag_days: 63`，两者语义矛盾

结论：**配置在多次运行之间被修改，但没有重新运行**。产出的 gate 结论不可信，因为无法确定它们对应哪个版本的配置。

### 1.2 核心问题

| 问题 | 严重度 | 影响 |
|---|---|---|
| `date_semantics` 字段仅记录不使用，对齐逻辑忽略 PIT 语义 | P0 | fundamental 因子的 no-leakage 状态不可信 |
| 配置与产出之间无追踪（无 checksum / 版本号） | P0 | 无法判断产出对应哪个配置版本 |
| 无随机种子设定，numpy/pandas 非确定性 | P1 | 同一配置两次运行结果可能不同 |
| `--start/--end` 与 config watch_only 窗口可能不一致 | P1 | watch 窗口数据静默为空 |
| fundamental 因子 `data_lag_days=0` 无警告 | P1 | 可能导致未来函数 |
| 运行元数据不完整（无环境信息、无配置路径） | P2 | 跨环境复现困难 |

### 1.3 `date_semantics` 语义定义

本文档确立以下术语定义（在所有代码和配置中统一）：

```text
observation_date 语义:
  factor.trade_date = 因子值被观测/计算的日期
  available_date = observation_date + data_lag_days（自然日）
  signal_date = first_trading_day_on_or_after(available_date)
  适用: 技术因子（价格/成交量，收盘后可立即使用）

pit_aligned 语义:
  factor.trade_date = 数据已经可用的日期（Point-In-Time 对齐）
  即: available_date = factor.trade_date（数据在该日期已可用）
  signal_date = first_trading_day_on_or_after(available_date)
  适用: 基本面因子（财务数据，trade_date 已经是财报发布日）
```

关键差异：
- `observation_date`: **需要加** `data_lag_days` 得到 `available_date`
- `pit_aligned`: **不需要加** `data_lag_days`，`available_date = trade_date`

当前 V4 配置矛盾：`date_semantics: pit_aligned` + `data_lag_days: 63` 同时存在。按 PIT 语义，`data_lag_days` 应为 0。如果需要 63 天 lag，则应使用 `observation_date` 语义。

## 2. 目标状态

修复完成后：

1. `date_semantics` 影响对齐逻辑：`pit_aligned` 跳过 data_lag 偏移
2. 每次运行在 `profile.json` 中记录配置 SHA256、运行时间戳、Python 环境
3. 通过 `--seed` 参数确保 numpy 可复现
4. 如果 config watch_only end > CLI `--end`，发出警告
5. fundamental + `observation_date` + `data_lag_days=0` 发出警告
6. `pit_aligned` + `data_lag_days > 0` 发出警告（语义矛盾）
7. V4 配置中的矛盾被修复

## 3. 修改方案

### 3.1 P0：`date_semantics` 对齐逻辑

**文件**: `scripts/factor_quality_rebuild.py`

**修改 `_build_aligned_panel`**:

```python
date_semantics = factor_cfg.get("date_semantics", "observation_date")

if date_semantics == "pit_aligned":
    # PIT-aligned: trade_date IS the available_date (no additional lag)
    df_copy["available_date"] = df_copy["trade_date"]
    if data_lag_days > 0:
        audit["alignment_warning"] = (
            f"pit_aligned with data_lag_days={data_lag_days} > 0 — "
            f"lag is ignored for pit_aligned factors"
        )
else:
    # observation_date: apply data_lag_days offset
    df_copy["available_date"] = df_copy["trade_date"].map(avail_map)
```

**修改 fundamental 因子检测逻辑** (移除原来的硬编码 `data_lag_days=0` 检测):

```python
# 原来:
# if factor_cfg.get("type") == "fundamental" and data_lag_days == 0 and fname != "log_market_cap_cs":
#     audit["no_leakage_status"] = "LEAKAGE_METADATA_MISSING"

# 改为: 警告但不阻断
if factor_cfg.get("type") == "fundamental" and date_semantics == "observation_date" and data_lag_days == 0:
    audit["alignment_warning"] = (
        "fundamental factor with observation_date semantics and data_lag_days=0 — "
        "potential look-ahead bias"
    )
```

### 3.2 P0：配置校验和追踪

**文件**: `scripts/factor_quality_rebuild.py`

新增辅助函数：

```python
import hashlib

def _config_checksum(config_path: Path) -> str:
    """Return SHA256 hex digest of config file."""
    return hashlib.sha256(config_path.read_bytes()).hexdigest()[:16]
```

在 profile.json 中记录：

```json
{
  "config_path": "configs/factor_quality_rebuild_v4.yaml",
  "config_sha256": "a1b2c3d4e5f6a7b8",
  "seed": 42,
  "started_at": "2026-06-18 14:30:00",
  "python_version": "3.11.9",
  "numpy_version": "1.26.4",
  "pandas_version": "2.2.2",
  ...
}
```

### 3.3 P1：确定性随机种子

**CLI 新增**:

```text
--seed SEED   Random seed for reproducibility (default: 42)
```

**实现**:

```python
import numpy as np
np.random.seed(args.seed)
```

同时确保 pandas 的 `pd.qcut` 等操作在相同 seed 下可复现（`qcut` 本身是确定性的，不需要额外种子）。

### 3.4 P1：数据范围校验

**新增校验**：

```python
watch_end_int = int(watch_end)
cli_end_int = int(args.end)
if watch_end_int > cli_end_int:
    print(
        f"[WARNING] Config watch_only.end={watch_end} > CLI --end={args.end}. "
        f"Watch window data will be incomplete. "
        f"Consider --end {watch_end}",
        flush=True,
    )
```

### 3.5 P1：配置矛盾检测

在处理每个因子之前，检测语义矛盾：

```python
def _validate_factor_config(factor_cfg: dict) -> list[str]:
    """Return list of config warnings for a factor."""
    warnings = []
    date_semantics = factor_cfg.get("date_semantics", "observation_date")
    data_lag_days = factor_cfg.get("data_lag_days", 0)
    ftype = factor_cfg.get("type", "")
    
    if date_semantics == "pit_aligned" and data_lag_days > 0:
        warnings.append(
            f"pit_aligned with data_lag_days={data_lag_days}>0 — "
            f"lag offset will NOT be applied for pit_aligned factors"
        )
    if ftype == "fundamental" and date_semantics == "observation_date" and data_lag_days == 0:
        warnings.append(
            "fundamental factor with observation_date + data_lag_days=0 — "
            "potential look-ahead bias"
        )
    return warnings
```

### 3.6 P2：V4 配置修复

修复 `configs/factor_quality_rebuild_v4.yaml` 中的矛盾：

**方案**: 将 fundamental 因子的 `date_semantics` 统一为 `observation_date`，保留 `data_lag_days: 63`。

这对应现实：因子值在某日期被计算（observation_date），财务数据有约 63 天的报告延迟。

或者反过来：保持 `pit_aligned`，将 `data_lag_days` 改为 0。

**推荐方案**: 改为 `observation_date` + `data_lag_days: 63`，因为：
1. 更符合代码现有的对齐逻辑
2. `observation_date` 是 v2 config 的默认值
3. 63 天 lag 对基本面因子是必要的

如果实际数据已经是 PIT 对齐的（trade_date 已经是报告日期），则使用 `pit_aligned` + `data_lag_days: 0`。

### 3.7 P2：运行元数据增强

在 profile.json 中新增：

```json
{
  "run_id": "20260618_143000",
  "config_path": "configs/factor_quality_rebuild_v4.yaml",
  "config_sha256": "a1b2c3d4e5f6a7b8",
  "cli_args": {
    "start": "20170101",
    "end": "20241231",
    "seed": 42
  },
  "environment": {
    "python_version": "3.11.9",
    "numpy_version": "1.26.4",
    "pandas_version": "2.2.2",
    "scipy_version": "1.13.0"
  },
  "run_summary": {
    "total_factors": 63,
    "data_missing": 28,
    "pass": 0,
    "fail": 35,
    "watch": 0,
    "support": 0
  },
  "started_at": "2026-06-18T14:30:00",
  "finished_at": "2026-06-18T14:36:30",
  "total_elapsed_sec": 390.5,
  "stages": [...],
  "config_warnings": [
    "factor X: pit_aligned with data_lag_days=63>0 — lag offset NOT applied",
    "config watch_only.end (20260605) > CLI --end (20241231)"
  ]
}
```

## 4. V4 配置修改

### 4.1 解决 `date_semantics` 矛盾

当前 V4 config 有 5 个 fundamental 因子使用了 `observation_date`（原 v2 遗留）和 43 个 fundamental 因子使用了 `pit_aligned`。

| 类别 | 因子数 | 当前 semantics | 当前 lag | 修复后 semantics | 修复后 lag |
|---|---|---|---|---|---|
| Legacy fundamental | 9 | pit_aligned | 63 | observation_date | 63 |
| V4 Quality | 6 | pit_aligned | 63 | observation_date | 63 |
| V4 Growth | 5 | pit_aligned | 63 | observation_date | 63 |
| V4 Cashflow | 6 | pit_aligned | 63 | observation_date | 63 |
| V4 Value Repair | 5 | pit_aligned | 63 | observation_date | 63 |
| V4 Industry Relative | 3 | pit_aligned | 63 | observation_date | 63 |
| V4 Technical (all) | ~23 | observation_date | 0 | observation_date | 0 |
| log_market_cap_cs | 1 | observation_date | 0 | observation_date | 0 |

**统一修复**: 所有 `pit_aligned` 改为 `observation_date`，保留 `data_lag_days` 不变。

### 4.2 watch_only 窗口调整

当前 `watch_only.end: "20260605"` 在数据范围外。修复方案：
- 保持 config 中的窗口定义（用于将来）
- 在代码中添加数据范围警告
- CLI 默认 `--end` 应覆盖 watch 窗口

## 5. 实现任务拆解

### Task 1: `date_semantics` 对齐逻辑
- 修改 `_build_aligned_panel` 中 available_date 计算
- `pit_aligned`: skip data_lag offset
- `observation_date`: apply data_lag offset (existing behavior)

### Task 2: 配置校验和与确定性
- 新增 `_config_checksum()` 
- 新增 `--seed` CLI 参数
- 设置 `np.random.seed(seed)`
- 在 profile.json 中记录完整元数据

### Task 3: 数据范围与配置校验
- 新增 `_validate_factor_config()` 警告收集
- 新增 watch window vs CLI end 范围校验
- 收集并在 profile 中输出所有 config_warnings

### Task 4: 修复 V4 配置矛盾
- 将所有 fundamental 因子的 `date_semantics` 从 `pit_aligned` 改为 `observation_date`

### Task 5: 验证
- 运行现有测试确保不破坏
- 对比修复前后 alignment audit 差异
- 验证 profile.json 包含所有新字段

## 6. 测试计划

### 6.1 单元测试

新增测试用例：

1. `test_pit_aligned_skips_data_lag` — pit_aligned 因子不应用 data_lag offset
2. `test_observation_date_applies_data_lag` — observation_date 因子正确应用 data_lag
3. `test_config_checksum_deterministic` — 相同配置生成相同 checksum
4. `test_seed_reproducibility` — 相同 seed 产生相同 gate 结果
5. `test_pit_aligned_with_lag_warns` — pit_aligned + data_lag>0 产生警告
6. `test_fundamental_observation_no_lag_warns` — fundamental + observation_date + lag=0 产生警告
7. `test_watch_window_beyond_cli_warns` — watch end > cli end 产生警告

### 6.2 回归测试

```powershell
python -m pytest -q tests/test_factor_quality_rebuild.py
python -m pytest -q tests/test_factor_quality_rebuild.py tests/test_factor_alignment.py tests/test_factor_pruning.py tests/test_strategy_alpha_failure_diagnosis.py
```

## 7. 验收标准

1. `date_semantics` 实际影响对齐逻辑（不只是记录）
2. `profile.json` 包含 `config_sha256`、`seed`、`environment`、`config_warnings`
3. 相同 config + 相同 seed 两次运行产生完全相同的 gate 结果
4. V4 config 中不再有 `pit_aligned` + `data_lag_days > 0` 的语义矛盾
5. watch 窗口超出数据范围时有明确警告
6. 现有测试全部通过
7. fundamental 因子不再因 `data_lag_days=0` 无警告静默通过

## 8. 产物清单

修改文件：

```text
scripts/factor_quality_rebuild.py       — 核心修复
configs/factor_quality_rebuild_v4.yaml  — 配置矛盾修复
docs/factor_quality_rebuild_v4_reproducibility_fix_plan.md — 本文档
```

新增 profile 字段：

```text
outputs/analysis/factor_quality_rebuild/profile.json → 新增字段
```

## 9. 风险与注意事项

1. **`date_semantics` 修复可能改变 aligned rows 数量** — 如果数据确实是 PIT 对齐的，改为 `observation_date` + `data_lag_days: 63` 会正确增加 lag，可能减少有效样本量。这是预期行为。

2. **如果数据实际已经是 PIT 对齐的** — `trade_date` 已经是报告发布日期，那么应使用 `pit_aligned` + `data_lag_days: 0`。需要确认实际数据语义。

3. **现有 V4 产出将变得过时** — 修复后必须重新运行全量流水线才能生成可信 gate 结论。

4. **`date_semantics` 默认值** — 如果因子配置未声明 `date_semantics`，默认 `observation_date`（向后兼容 v2 配置）。

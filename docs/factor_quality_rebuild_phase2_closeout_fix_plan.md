# Factor Quality Rebuild 二期最终收尾整改开发方案

生成日期：2026-06-14

## 1. 背景

`Factor Quality Rebuild` 二期最终验收整改已经完成主体开发。当前代码和正式产物已经修复了上一轮主要阻断项：

- mcap-neutral 低覆盖率不再标记为 `OK`。
- low coverage neutralization 不再允许产生 `WATCH_NEUTRAL_ONLY`。
- `volatility_60_cs` 已从 `WATCH_NEUTRAL_ONLY` 降为 `FAIL`。
- capacity 市值字段已经从万元修正为 CNY。
- capacity participation 已改为基于日度 leg amount sum 估算。
- 增强版 `scripts/validate_factor_quality_outputs.py` 支持 `--config`，并能校验 neutralization coverage/status、gate-neutralization 一致性、capacity CNY 量级和 participation 公式。
- 正式产物通过增强产物验收脚本。

但最终审核仍未闭环，原因有三项：

1. 全流程临时重跑在 `600s` 内未完成，不能证明当前流水线稳定可复现。
2. 产物验收脚本缺少独立测试文件，不能防止验收脚本自身回归。
3. capacity audit 对直接 `amount / vol / total_amount` 字段仍未按 `amount_unit` 做单位转换，当前数据未触发，但属于后续数据源切换风险。

本方案是二期最后一轮收尾整改方案。目标是把“正式产物看起来正确”推进到“代码、测试、全流程、产物验收均可复现通过”。

## 2. 当前状态

### 2.1 已通过

当前已验证：

```text
python -m pytest -q tests/test_factor_quality_rebuild.py
结果：46 passed

python -m pytest -q tests/test_factor_quality_rebuild.py tests/test_factor_alignment.py tests/test_factor_pruning.py tests/test_strategy_alpha_failure_diagnosis.py
结果：101 passed

python scripts/validate_factor_quality_outputs.py --out-dir outputs/analysis/factor_quality_rebuild --config configs/factor_quality_rebuild.yaml
结果：VALIDATION PASSED: 8/8 checks OK
```

正式产物摘要：

```text
factor_neutralization_diagnostic.csv:
  LOW_COVERAGE = 12
  OK = 1

factor_quality_gate.csv:
  FAIL = 12
  DATA_MISSING = 5
  SUPPORT = 1

factor_candidate_pool.yaml:
  eligible_factors = []
  recommendation = NO_ALPHA_SOURCE_FOUND
```

### 2.2 未通过

本轮审核执行全流程临时重跑：

```powershell
python scripts/factor_quality_rebuild.py `
  --config configs/factor_quality_rebuild.yaml `
  --start 20170101 `
  --end 20241231 `
  --out-dir <temp>/analysis `
  --out-doc <temp>/factor_quality_rebuild_report.md
```

结果：

```text
600.1s 未完成，进程已终止
```

因此最终验收不能关闭。

## 3. 整改目标

本轮整改完成后必须满足：

1. 全流程 `20170101-20241231` 可以稳定跑完。
2. 全流程耗时应有明确上限，建议初始验收阈值为 `<= 10 分钟`；若机器负载较高，允许记录环境并给出可复现性能数据，但不能无界运行。
3. 产物验收脚本具备独立测试，能证明它可以捕捉异常产物。
4. capacity audit 的所有金额来源都按配置统一到 CNY，不只修复当前数据触发路径。
5. 正式产物重新生成，并通过增强产物验收。
6. 若最终仍为 `NO_ALPHA_SOURCE_FOUND`，该结论可作为二期最终可信结论。

## 4. 非目标

本轮不做：

- 不新增 alpha 因子。
- 不放宽 gate 阈值。
- 不修改 2021-2024 primary validation 口径。
- 不重建 strategy 或 sleeve。
- 不引入复杂冲击成本模型。
- 不改变 candidate pool 契约。

## 5. P0：全流程超时与可复现性整改

### 5.1 问题

上一轮全流程曾在约 `421.1s` 完成，但本轮同类临时重跑在 `600s` 内未完成。当前不能判断是：

- 代码性能退化。
- 同机其他长进程造成资源竞争。
- 某个阶段缺少进度输出，实际仍在推进。
- 新增逻辑引入了高复杂度计算。
- 输出重定向导致 stdout 缓冲，看不到进度。

这会影响最终验收：二期流水线必须是可重复运行的，而不是依赖已有产物。

### 5.2 修改方案

#### 5.2.1 增加阶段级计时与 flush 日志

在 `scripts/factor_quality_rebuild.py` 中增加轻量计时工具：

```python
from contextlib import contextmanager
from time import perf_counter

@contextmanager
def timed_stage(name: str):
    t0 = perf_counter()
    print(f"[stage:start] {name}", flush=True)
    try:
        yield
    finally:
        elapsed = perf_counter() - t0
        print(f"[stage:end] {name} elapsed={elapsed:.1f}s", flush=True)
```

包裹以下阶段：

- load config/data
- factor input audit
- alignment
- neutralization
- direction audit
- IC by year
- quantile returns
- turnover cost
- IC trend
- rolling window gate
- capacity audit
- regime breakdown
- quality gate
- correlation clusters
- candidate pool
- output writing
- report writing

要求：

- 所有关键 `print` 加 `flush=True`。
- 失败或超时时，能从 stdout tail 看出卡在哪个阶段。

#### 5.2.2 增加 profile 输出

新增 CLI 参数：

```text
--profile-out outputs/analysis/factor_quality_rebuild/profile.json
```

输出结构：

```json
{
  "started_at": "...",
  "finished_at": "...",
  "total_elapsed_sec": 421.1,
  "stages": [
    {"name": "alignment", "elapsed_sec": 35.2},
    {"name": "neutralization", "elapsed_sec": 48.7}
  ]
}
```

若运行中断，也应尽可能在 finally 中写出已完成阶段。

#### 5.2.3 定位慢点

重点检查以下高风险阶段：

1. IC / Pearson / Spearman groupby apply  
   当前测试输出大量 `DataFrameGroupBy.apply` deprecation warning，说明相关阶段频繁 groupby apply。需要确认是否是主要耗时来源。

2. rolling window gate  
   如果每个窗口重复扫描和重复计算 IC，可缓存年度结果后复用。

3. regime breakdown  
   如果每个因子重复读取或重复 groupby，需要把 regime 数据一次性加载并复用。

4. neutralization  
   当前逐因子、逐日期 OLS。若 mcap 覆盖率大部分日期不足 70%，可以先按覆盖率过滤日期，避免无效回归准备开销。

5. capacity audit  
   当前按日期过滤 `daily_basic[daily_basic["trade_date"] == dt]`，如果 daily_basic 很大，可预先建立 `dict[int, DataFrame]` 或 MultiIndex。

### 5.3 优化建议

#### 5.3.1 预索引 daily_basic

当前 capacity 可能反复做：

```python
db_date = daily_basic[daily_basic["trade_date"] == dt]
```

建议在 capacity 阶段前构建：

```python
daily_basic_by_date = {
    int(dt): g for dt, g in daily_basic.groupby("trade_date", sort=False)
}
```

然后：

```python
db_date = daily_basic_by_date.get(int(dt))
```

#### 5.3.2 预索引 forward universe

alignment coverage 当前可能逐日期从 fwd groupby 并重复过滤 aligned。建议：

```python
fwd_universe_by_date = {
    dt: set(g["ts_code"]) for dt, g in fwd.groupby("trade_date")
}
```

aligned panel coverage 用 groupby 后 set intersection 计算，避免每日 `aligned[aligned["signal_date"] == sd]`。

#### 5.3.3 减少 repeated groupby apply

对 IC 计算，尽量改为：

- 先按 `trade_date` 切分必要列。
- 使用 `groupby(...)[["value", "fwd_return"]]`。
- 避免 groupby apply 返回复杂对象。

如果短期不重写算法，至少加阶段计时，明确是否需要进一步优化。

#### 5.3.4 neutralization 低覆盖快速跳过

对于每个日期：

```python
valid = g.dropna(subset=["value", "log_mcap"])
coverage = len(valid) / n_factor * 100
```

用真实交集数量计算 coverage，不使用 `min(n_factor, n_mcap)`。

如果 `coverage < min_coverage_pct`，直接跳过，不进入 OLS 准备。

### 5.4 验收标准

必须提供：

```text
全流程命令
退出码
总耗时
profile.json
最慢 5 个阶段
```

通过条件：

```text
全流程 exit code = 0
输出完整正式产物
增强产物验收脚本通过
总耗时 <= 600s
```

若因同机其他长任务导致耗时不可控，必须在低负载条件下复跑一次并记录进程环境。

## 6. P1：补齐产物验收脚本独立测试

### 6.1 问题

当前 `scripts/validate_factor_quality_outputs.py` 已增强，但缺少独立测试文件：

```text
tests/test_factor_quality_output_validation.py 不存在
```

这意味着验收脚本自身是否能拦截异常产物，没有测试保护。

### 6.2 新增测试文件

新增：

```text
tests/test_factor_quality_output_validation.py
```

测试对象：

- `scripts.validate_factor_quality_outputs.check_neutralization_validity`
- `scripts.validate_factor_quality_outputs.check_gate_neutralization_consistency`
- `scripts.validate_factor_quality_outputs.check_capacity_cny_scale`
- `scripts.validate_factor_quality_outputs.check_capacity_participation`
- `scripts.validate_factor_quality_outputs.check_candidate_pool_contract`

### 6.3 测试数据生成

使用 pytest `tmp_path` 构造最小产物目录：

```text
tmp_path/
  factor_neutralization_diagnostic.csv
  factor_quality_gate.csv
  factor_capacity_audit.csv
  factor_candidate_pool.yaml
```

只写测试函数需要的最小字段，不依赖真实 outputs。

### 6.4 必须覆盖的测试用例

#### 6.4.1 low coverage 但 status OK 必须失败

输入：

```csv
factor,neutralizer_coverage_pct,neutralization_status,neutralization_valid
foo_cs,5.0,OK,false
```

配置：

```yaml
neutralization:
  min_neutralizer_coverage_pct: 70
```

期望：

```text
check_neutralization_validity 返回 issue
```

#### 6.4.2 low coverage 但 status SIZE_DEPENDENT 必须失败

输入：

```csv
factor,neutralizer_coverage_pct,neutralization_status,neutralization_valid
foo_cs,5.0,SIZE_DEPENDENT,false
```

期望：

```text
返回 issue
```

#### 6.4.3 WATCH_NEUTRAL_ONLY 但 neutralization invalid 必须失败

输入 gate：

```csv
factor,quality_gate_status
foo_cs,WATCH_NEUTRAL_ONLY
```

输入 neutralization：

```csv
factor,neutralizer_coverage_pct,neutralization_status,neutralization_valid
foo_cs,5.0,LOW_COVERAGE,false
```

期望：

```text
check_gate_neutralization_consistency 返回 issue
```

#### 6.4.4 PASS 但 neutralization invalid 必须失败

输入 gate：

```csv
factor,quality_gate_status
foo_cs,PASS
```

配置：

```yaml
neutralization:
  require_valid_neutralization_for_neutral_gate: true
```

期望：

```text
返回 issue
```

#### 6.4.5 market cap 疑似万元口径必须失败

输入 capacity：

```csv
factor,year,median_market_cap_cny,median_top_amount_cny
foo_cs,2024,8758455,500000000
```

期望：

```text
check_capacity_cny_scale 返回 issue
```

#### 6.4.6 participation 公式不一致必须失败

输入：

```csv
factor,year,estimated_trade_cny_at_target_aum,median_leg_amount_sum_cny,participation_rate_at_target_aum
foo_cs,2024,50000000,1000000000,0.20
```

正确 participation 应为：

```text
50000000 / 1000000000 = 0.05
```

期望：

```text
返回 issue
```

#### 6.4.7 正常样例必须通过

构造：

```text
neutralizer_coverage_pct = 100
neutralization_status = OK
neutralization_valid = true
quality_gate_status = FAIL 或 PASS
median_market_cap_cny = 80_000_000_000
median_top_amount_cny = 500_000_000
estimated_trade_cny_at_target_aum = 50_000_000
median_leg_amount_sum_cny = 50_000_000_000
participation_rate_at_target_aum = 0.001
```

期望：

```text
所有 check 返回 []
```

### 6.5 验收命令

```powershell
python -m pytest -q tests/test_factor_quality_output_validation.py
```

并纳入回归集：

```powershell
python -m pytest -q `
  tests/test_factor_quality_rebuild.py `
  tests/test_factor_quality_output_validation.py `
  tests/test_factor_alignment.py `
  tests/test_factor_pruning.py `
  tests/test_strategy_alpha_failure_diagnosis.py
```

## 7. P1：修复 capacity 直接 amount 字段单位转换

### 7.1 问题

当前 capacity audit 主路径使用：

```python
_est_amount = circ_mv * turnover_rate * 100.0
```

这已经按 Tushare `circ_mv` 万元和 `turnover_rate` 百分比转换为 CNY。

但如果数据源存在以下字段：

```text
amount
vol
total_amount
```

当前代码仍直接使用原值，没有按配置 `amount_unit` 统一到 CNY。

当前正式数据没有触发该路径，所以产物没问题；但这是后续数据源切换时的隐性回归风险。

### 7.2 配置口径

在 `configs/factor_quality_rebuild.yaml` 中明确：

```yaml
capacity:
  amount_unit: "derived_from_circ_mv"
```

建议支持：

```text
derived_from_circ_mv
cny
yuan
thousand_cny
wan_cny
auto
```

其中：

- `derived_from_circ_mv`：忽略直接 amount 字段，统一使用 `circ_mv_cny * turnover_rate / 100`。
- `cny` / `yuan`：amount 已经是元。
- `thousand_cny`：amount 是千元。
- `wan_cny`：amount 是万元。
- `auto`：不建议默认使用；除非有数据源元信息，否则应报错或 WARN。

### 7.3 修改方案

新增函数：

```python
def _convert_amount_to_cny(series: pd.Series, amount_unit: str) -> pd.Series:
    if amount_unit in ("cny", "yuan"):
        return series
    if amount_unit == "thousand_cny":
        return series * 1000.0
    if amount_unit == "wan_cny":
        return series * 10000.0
    raise ValueError(f"Unsupported amount_unit: {amount_unit}")
```

新增函数：

```python
def _daily_basic_amount_cny(db_date: pd.DataFrame, capacity_cfg: dict) -> pd.Series:
    amount_unit = capacity_cfg.get("amount_unit", "derived_from_circ_mv")

    if amount_unit == "derived_from_circ_mv":
        circ_mv_cny = _market_cap_cny(db_date["circ_mv"], capacity_cfg)
        return circ_mv_cny * db_date["turnover_rate"] / 100.0

    amount_col = capacity_cfg.get("amount_column")
    if amount_col:
        return _convert_amount_to_cny(db_date[amount_col], amount_unit)

    for col in ["amount", "total_amount"]:
        if col in db_date.columns:
            return _convert_amount_to_cny(db_date[col], amount_unit)

    if "circ_mv" in db_date.columns and "turnover_rate" in db_date.columns:
        circ_mv_cny = _market_cap_cny(db_date["circ_mv"], capacity_cfg)
        return circ_mv_cny * db_date["turnover_rate"] / 100.0

    return pd.Series(np.nan, index=db_date.index)
```

注意：

- 不建议把 `vol` 当成交额。`vol` 常见含义是成交量，不是成交额。
- 若保留 `vol`，必须有明确配置 `amount_column: vol` 且 `amount_unit` 明确，否则不要自动使用。

### 7.4 修改 `_compute_capacity_audit`

替换当前直接字段读取逻辑：

```python
for amt_col in ["amount", "vol", "total_amount"]:
    ...
```

改为：

```python
db_date["_amount_cny"] = _daily_basic_amount_cny(db_date, capacity_cfg)
top_amt_series = db_date.loc[db_date["ts_code"].isin(top_codes), "_amount_cny"].dropna()
bot_amt_series = db_date.loc[db_date["ts_code"].isin(bot_codes), "_amount_cny"].dropna()
```

### 7.5 测试

新增测试：

1. `amount_unit=cny` 时不转换。
2. `amount_unit=thousand_cny` 时乘 `1000`。
3. `amount_unit=wan_cny` 时乘 `10000`。
4. `amount_unit=derived_from_circ_mv` 时忽略 `amount` 字段，使用 `circ_mv * 10000 * turnover_rate / 100`。
5. 未配置单位但存在 `amount` 字段时，不允许静默比较 CNY 阈值。

## 8. P2：修正 neutralization meta 行数口径

### 8.1 问题

当前 `_neutralize_by_mcap` 中：

```python
n_neut_rows = int(n_neut_dates > 0)
neut_row_count = sum(1 for r in results if r["value_mcap_neutral"].notna().sum() > 0)
raw_row_count = n_neut_dates + n_skip_dates
neutralized_row_coverage_pct = avg_coverage
```

其中：

- `n_neut_rows` 未使用。
- `neutralized_row_count` 实际是“有 neutralized 值的日期数”，不是行数。
- `raw_row_count` 实际是日期数，不是行数。
- `neutralized_row_coverage_pct` 复用了平均 coverage，不是真实行覆盖率。

当前 gate 主要依赖 coverage 和日期数，正式结论不受明显影响；但字段含义不严谨。

### 8.2 修改方案

改为真实行数：

```python
result_df = pd.concat(results, ignore_index=True)
raw_row_count = int(result_df["value_raw"].notna().sum())
neutralized_row_count = int(result_df["value_mcap_neutral"].notna().sum())
neutralized_row_coverage_pct = neutralized_row_count / raw_row_count * 100
```

如果担心内存，可以在循环中累计：

```python
raw_row_count += int(g["value"].notna().sum())
neutralized_row_count += int(g["value_mcap_neutral"].notna().sum())
```

### 8.3 测试

新增测试：

- 2 个日期，每日 100 行，其中 1 天 neutralized 成功。
- 期望 `raw_row_count=200`。
- 期望 `neutralized_row_count=100`。
- 期望 `neutralized_row_coverage_pct=50%`。

## 9. 验收流程

### 9.1 单测

```powershell
python -m pytest -q tests/test_factor_quality_rebuild.py
python -m pytest -q tests/test_factor_quality_output_validation.py
```

### 9.2 回归测试

```powershell
python -m pytest -q `
  tests/test_factor_quality_rebuild.py `
  tests/test_factor_quality_output_validation.py `
  tests/test_factor_alignment.py `
  tests/test_factor_pruning.py `
  tests/test_strategy_alpha_failure_diagnosis.py
```

### 9.3 全流程

建议在低负载环境运行，先确认无无关重型进程：

```powershell
Get-CimInstance Win32_Process -Filter "name = 'python.exe'" |
  Select-Object ProcessId,CreationDate,CommandLine
```

运行：

```powershell
python scripts/factor_quality_rebuild.py `
  --config configs/factor_quality_rebuild.yaml `
  --start 20170101 `
  --end 20241231 `
  --out-dir outputs/analysis/factor_quality_rebuild `
  --out-doc docs/factor_quality_rebuild_report.md `
  --profile-out outputs/analysis/factor_quality_rebuild/profile.json
```

### 9.4 产物验收

```powershell
python scripts/validate_factor_quality_outputs.py `
  --out-dir outputs/analysis/factor_quality_rebuild `
  --config configs/factor_quality_rebuild.yaml
```

## 10. 最终验收标准

必须同时满足：

```text
1. tests/test_factor_quality_rebuild.py 通过
2. tests/test_factor_quality_output_validation.py 通过
3. 回归集通过
4. 全流程 20170101-20241231 exit code = 0
5. 全流程耗时 <= 600s，或有明确 profile 证明慢点并经用户接受
6. validate_factor_quality_outputs.py --config 通过
7. factor_candidate_pool.yaml 契约正确
8. 所有 CSV 可读
9. 无 STUB
10. 若 eligible_factors 为空，recommendation 必须为 NO_ALPHA_SOURCE_FOUND
```

## 11. 预期最终产物

整改完成后应更新：

```text
scripts/factor_quality_rebuild.py
scripts/validate_factor_quality_outputs.py
configs/factor_quality_rebuild.yaml
tests/test_factor_quality_rebuild.py
tests/test_factor_quality_output_validation.py
outputs/analysis/factor_quality_rebuild/*.csv
outputs/analysis/factor_quality_rebuild/factor_candidate_pool.yaml
outputs/analysis/factor_quality_rebuild/profile.json
docs/factor_quality_rebuild_report.md
```

## 12. 最终判断规则

如果修复后：

```text
eligible_factors = []
recommendation = NO_ALPHA_SOURCE_FOUND
```

且全部测试、全流程、产物验收均通过，则接受该结论，二期可以关闭。

如果全流程仍超时，则不能关闭二期，需要继续性能定位。

如果产物验收脚本缺少测试，则不能关闭二期，因为验收脚本本身没有回归保护。

如果 direct amount 字段仍可能绕过 CNY 转换，则不能关闭数据口径整改。

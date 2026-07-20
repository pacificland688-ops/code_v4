# Factor Quality Rebuild 二期整改最终开发方案

生成日期：2026-06-14

## 1. 背景

`Factor Quality Rebuild` 初版已经实现了基础 IC、分位收益、方向校准、质量 gate 和候选池输出，但当前结果还不能作为下一阶段 sleeve/strategy 重建依据。

上一轮审核确认的主要问题：

- `factor_alignment_audit.csv`、`factor_turnover_cost.csv`、`factor_neutralization_diagnostic.csv`、`factor_regime_breakdown.csv` 仍是 `STUB`。
- `require_no_leakage: true` 没有进入最终 gate。
- 覆盖率 gate 没按配置百分比实现，当前只是粗略绝对数量判断。
- 扣费收益仍使用固定 `est_turnover = 0.20`，会扭曲技术因子和基本面因子的成本估计。
- `log_market_cap_cs` 被错误放进 WATCH alpha 候选池。
- `gate_basis: mcap_neutral` 语义不清，可能误杀 size-dependent alpha。
- 缺少 IC 衰减、rolling validation robustness、相关性去重、容量/流动性筛查。
- 5 个基本面因子缓存为空，不能被简单判定为 alpha 失败，应单独归类为 `DATA_MISSING`。

本方案是二期整改的最终开发方案。二期目标不是寻找新因子，也不是重建策略，而是把因子研究流水线修到“结论可信、可验收、可阻断下游”的状态。

## 2. 总体目标

二期完成后，`scripts/factor_quality_rebuild.py` 必须能够回答：

1. 每个因子是否存在未来函数风险。
2. 每个因子在 raw 与市值中性化后是否仍有稳定预测力。
3. 因子扣除真实或代理换手成本后是否还有净 alpha。
4. 因子是否只是 size exposure、是否 IC 衰减、是否只在特殊窗口有效。
5. 因子是否具备基本容量和流动性可交易性。
6. 哪些因子可以进入下一阶段 sleeve 重建，哪些只能 WATCH，哪些是数据缺失，哪些应淘汰。

二期完成前，当前策略族继续保持 `NO_GO`，不进入 sleeve/strategy 重建。

## 3. 核心设计结论

### 3.1 2021-2024 仍作为 primary validation

2021-2024 市场环境特殊，但这不能直接推出 gate 太严。二期不因为 `0 PASS` 主动放宽门槛。

处理方式：

- `2021-2024` 仍是 primary validation。
- 增加 rolling validation windows 作为稳健性检查。
- 若因子只在 primary 失败、其他窗口稳定，可标记 `WATCH_WINDOW_SENSITIVE`。
- 若多个窗口都失败，接受失败结论。

### 3.2 raw 与 mcap-neutral 双轨判定

不采用“mcap-neutral 是唯一裁判”的设计。市值中性化用于识别 alpha 来源，而不是静默覆盖 raw 结果。

最终状态规则：

| raw gate | mcap-neutral gate | hard gate | final status |
|---|---|---|---|
| PASS | PASS | PASS | PASS |
| PASS | FAIL | PASS | WATCH_SIZE_DEPENDENT |
| FAIL | PASS | PASS | WATCH_NEUTRAL_ONLY |
| FAIL | FAIL | PASS | FAIL |
| 任意 | 任意 | FAIL | FAIL |

说明：

- `WATCH_SIZE_DEPENDENT` 表示因子可能有信息，但主要依赖 size exposure，不允许直接进入 sleeve。
- `WATCH_NEUTRAL_ONLY` 表示 raw 不强，但去除 size 后有信号，需要人工复核。
- 只有最终 `PASS` 才能进入 `eligible_factors`。

### 3.3 no-leakage 必须使用因子级 data lag

不能只用全局 `technical/fundamental` 上限，也不能简单套 `trade_date - lag`。

统一语义：

```text
observation_date = factor.trade_date
available_date = observation_date + data_lag_days
signal_date = first_trading_day_on_or_after(available_date)
forward_return starts at signal_date
```

每个因子必须声明：

- `data_lag_days`
- `date_semantics`
- `role`

基本面因子若缺少 `data_lag_days`，直接 `LEAKAGE_METADATA_MISSING`，最终 gate 为 `FAIL`。

### 3.4 容量筛查采用可解释粗筛，不做伪精确冲击模型

二期必须加入容量/流动性筛查，但不引入复杂且参数拍脑袋的冲击成本模型。

二期只做：

- top/bottom 分位成交额中位数。
- top/bottom 分位市值中位数。
- 目标 AUM 下 participation rate 粗估。
- 低流动性股票占比。

容量结果影响 gate：

- `capacity_status=FAIL`：最终 `FAIL`。
- `capacity_status=WATCH`：`PASS` 降级为 `WATCH_CAPACITY_CONSTRAINED`。
- `capacity_status=NOT_AVAILABLE`：若配置要求保守处理，则 `PASS` 降级为 `WATCH_CAPACITY_UNKNOWN`。

### 3.5 IC 衰减是降级标签，不是一票否决

IC 衰减检查必须加，但不单独作为死刑。

规则：

- primary gate 已 `PASS`，但 IC 显著衰减，则降级 `WATCH_IC_DECAY`。
- `WATCH/FAIL` 不因为趋势改善自动升级。
- 报告必须展示 monthly IC、slope、p-value。

## 4. 配置修改

修改 `configs/factor_quality_rebuild.yaml`。

### 4.1 因子元数据

每个因子增加以下字段：

```yaml
- name: reversal_5_cs
  category: reversal
  type: technical
  role: alpha_candidate
  sign_hint: positive
  data_lag_days: 0
  date_semantics: observation_date
  tradable_weighting: equal_weight
```

字段定义：

| 字段 | 说明 |
|---|---|
| `role` | `alpha_candidate`、`neutralizer`、`support_only` |
| `data_lag_days` | 因子观测日到合法可交易信号日之间的最小自然日滞后 |
| `date_semantics` | 二期统一为 `observation_date` |
| `tradable_weighting` | `equal_weight` 或 `mcap_weight`，默认 `equal_weight` |

默认规则：

- 技术因子：`data_lag_days: 0`
- 基本面因子：`data_lag_days: 63`
- `log_market_cap_cs`：`role: neutralizer`
- 没有缓存的基本面因子保留配置，但输出为 `DATA_MISSING`

### 4.2 Gate basis

新增：

```yaml
gate_basis:
  raw_required: true
  neutralized_required_for_pass: true
  raw_pass_neutral_fail_status: WATCH_SIZE_DEPENDENT
  raw_fail_neutral_pass_status: WATCH_NEUTRAL_ONLY
```

### 4.3 Coverage 定义

明确分母：

```text
coverage_pct(date) = |factor_codes(date) ∩ fwd_return_codes(signal_date)| / |fwd_return_codes(signal_date)|
```

要求：

- coverage 不得超过 100%。
- validation median coverage `>= min_coverage_pct`。
- 每个 validation 年份 median coverage `>= min_single_year_coverage_pct`。
- input audit 中 `missing_rate > 20%` 直接 `INPUT_FAIL`。

### 4.4 Robustness 配置

```yaml
robustness:
  enable_ic_trend_check: true
  ic_decay_p_value: 0.10
  rolling_windows:
    - {name: "2018_2021", start: "20180101", end: "20211231"}
    - {name: "2019_2022", start: "20190101", end: "20221231"}
    - {name: "2020_2023", start: "20200101", end: "20231231"}
    - {name: "2021_2024", start: "20210101", end: "20241231", primary: true}
  min_pass_windows_for_strong_pass: 3
```

### 4.5 Capacity 配置

```yaml
capacity:
  enabled: true
  target_aum_cny: 1000000000
  max_participation_rate: 0.05
  min_median_amount_cny: 20000000
  capacity_watch_if_unavailable: true
```

### 4.6 Correlation 配置

```yaml
correlation:
  max_intra_cluster_corr: 0.85
  cluster_representative: gate_score
```

## 5. 实现方案

修改 `scripts/factor_quality_rebuild.py`。

### 5.1 移除 STUB 输出

删除当前对以下文件的 STUB 写法：

- `factor_alignment_audit.csv`
- `factor_turnover_cost.csv`
- `factor_neutralization_diagnostic.csv`
- `factor_regime_breakdown.csv`

缺少数据时输出：

- `NOT_AVAILABLE`
- `DATA_MISSING`
- `BLOCKED`

但不得再输出 `STUB`。

### 5.2 两阶段 factor loader

新增：

```python
_load_factor_cache_raw(...)
_clean_factor_panel(...)
```

流程：

1. raw loader 保留重复键、缺失、异常值。
2. input audit 使用 raw panel。
3. clean panel 只给 IC、分位收益、换手、相关性等后续计算使用。

`factor_input_audit.csv` 字段：

- `factor`
- `role`
- `raw_rows`
- `clean_rows`
- `duplicate_keys`
- `duplicate_key_rate`
- `missing_rate`
- `constant_dates`
- `extreme_outlier_rate`
- `median_coverage_pct`
- `min_yearly_coverage_pct`
- `data_status`: `OK / DATA_MISSING / INPUT_FAIL`
- `input_audit_reason`

### 5.3 因子级 no-leakage alignment

新增：

```python
_build_aligned_panel(factor_cfg, clean_df, fwd, trading_calendar)
_audit_alignment(aligned_panel, factor_cfg)
```

规则：

```text
observation_date = factor.trade_date
available_date = observation_date + data_lag_days
signal_date = first_trading_day_on_or_after(available_date)
fwd return 起点必须等于 signal_date
```

输出 `factor_alignment_audit.csv`：

- `factor`
- `role`
- `horizon`
- `data_lag_days`
- `n_observations`
- `n_aligned_rows`
- `n_unmatured_rows_excluded`
- `n_signal_dates`
- `calibration_rows`
- `validation_rows`
- `watch_rows`
- `median_coverage_pct`
- `min_yearly_coverage_pct`
- `no_leakage_status`: `PASS / FAIL / NOT_AVAILABLE`
- `alignment_reason`

Gate：

- `require_no_leakage=true` 且 `no_leakage_status != PASS` 时最终 `FAIL`。

### 5.4 raw 与 mcap-neutral 双指标

新增：

```python
_neutralize_by_mcap(aligned_panel, log_market_cap_panel)
```

日度流程：

1. 对齐 factor 与 `log_market_cap_cs`。
2. 若当天 neutralizer coverage `<70%`，该日 neutralization 输出 `NOT_AVAILABLE`。
3. OLS：`factor_value ~ const + log_market_cap_cs`。
4. 残差作为 `factor_value_mcap_neutral`。
5. raw 与 mcap-neutral 分别计算 IC、分位收益、换手成本、gate。

`factor_neutralization_diagnostic.csv` 字段：

- `factor`
- `neutralizer`
- `neutralizer_coverage_pct`
- `raw_mean_ic`
- `neutral_mean_ic`
- `raw_net_spread`
- `neutral_net_spread`
- `size_beta_mean`
- `size_dependency_flag`
- `neutralization_status`
- `neutralization_reason`

### 5.5 真实换手与成本

替换固定 `est_turnover = 0.20`。

新增：

```python
_compute_quantile_portfolios(...)
_compute_real_turnover_cost(...)
```

若有 `fwd_ret_1d`：

```text
drifted_w_t = normalize(w_t * (1 + ret_1d))
turnover_leg = sum(abs(drifted_w_t - w_t_next)) / 2
total_turnover = turnover_long + turnover_short
cost = total_turnover * single_side_bps / 10000
net_spread = gross_spread - cost
```

若无 `fwd_ret_1d`：

```text
overlap_ratio = |names_t ∩ names_t_next| / |names_t ∪ names_t_next|
turnover_proxy = 1 - overlap_ratio
cost_proxy = turnover_proxy * single_side_bps / 10000
```

输出 `factor_turnover_cost.csv`：

- `factor`
- `year`
- `basis`: `raw / mcap_neutral`
- `weighting`
- `avg_turnover_long`
- `avg_turnover_short`
- `avg_total_turnover`
- `gross_spread`
- `estimated_cost`
- `net_spread`
- `net_gross_ratio`
- `turnover_method`: `REAL_WEIGHT_DRIFT / OVERLAP_PROXY / NOT_AVAILABLE`

最终 gate 使用该表的 `net_spread` 与 `net_gross_ratio`。

### 5.6 IC 衰减趋势

新增：

```python
_compute_monthly_ic(...)
_compute_ic_trend(...)
```

对 validation 月度 IC 做线性趋势：

```python
slope, intercept, r_value, p_value, stderr = linregress(range(len(monthly_ic)), monthly_ic)
```

输出 `factor_ic_trend.csv`：

- `factor`
- `basis`
- `monthly_ic_count`
- `ic_trend_slope`
- `ic_trend_p_value`
- `ic_declining`

Gate：

- final `PASS` 且 `ic_declining=true` 时，降级 `WATCH_IC_DECAY`。

### 5.7 Rolling validation robustness

新增：

```python
_compute_rolling_window_gate(...)
```

窗口：

- `2018-2021`
- `2019-2022`
- `2020-2023`
- `2021-2024`

输出 `factor_rolling_window_gate.csv`：

- `factor`
- `window`
- `basis`
- `window_gate_status`
- `mean_ic`
- `icir`
- `net_spread`
- `positive_ic_years`
- `positive_spread_years`

Gate：

- primary window 仍是必要条件。
- primary PASS 但 rolling PASS 数 `<3`，降级 `WATCH_WINDOW_FRAGILE`。
- 多窗口稳定失败则保持 `FAIL`。

### 5.8 Correlation cluster 去重

当前 cluster 只写报告，不影响候选池。整改后必须影响 `eligible_factors`。

流程：

1. 只对 `role=alpha_candidate` 且非 hard-fail 因子聚类。
2. 使用 corrected direction 后的因子值。
3. `abs(corr) > 0.85` 进入同一 cluster。
4. 每个 cluster 只保留一个 representative。

`gate_score`：

```text
gate_score =
  status_score
  + 10 * mean_ic
  + 5 * icir
  + 100 * net_spread
  - 2 * avg_total_turnover
  + coverage_pct
```

输出 `factor_correlation_cluster.csv`：

- `cluster_id`
- `factor`
- `representative`
- `redundant_to`
- `max_abs_corr_to_rep`
- `gate_score`

非 representative 因子不得进入 `eligible_factors`。

### 5.9 容量/流动性筛查

新增：

```python
_load_daily_basic(...)
_compute_capacity_audit(...)
```

数据源：

1. 优先读 `data/parquet/daily_basic`。
2. 使用成交额、市值字段。
3. 若字段缺失，输出 `NOT_AVAILABLE`。

输出 `factor_capacity_audit.csv`：

- `factor`
- `year`
- `basis`
- `median_top_amount_cny`
- `median_bottom_amount_cny`
- `median_market_cap_cny`
- `low_liquidity_weight_pct`
- `estimated_capacity_cny`
- `participation_rate_at_target_aum`
- `capacity_status`: `PASS / WATCH / FAIL / NOT_AVAILABLE`
- `capacity_reason`

Gate：

- `FAIL`：最终 `FAIL`
- `WATCH`：`PASS` 降级 `WATCH_CAPACITY_CONSTRAINED`
- `NOT_AVAILABLE`：按配置降级 `WATCH_CAPACITY_UNKNOWN`

### 5.10 Regime breakdown

新增：

```python
_load_regime_labels(...)
_compute_regime_breakdown(...)
```

数据源优先级：

1. `outputs/runs/*/diagnostics/phase2_regime_probs.parquet`
2. 其他已有 regime summary 产物
3. 无可靠标签时输出 `NOT_AVAILABLE`

输出 `factor_regime_breakdown.csv`：

- `factor`
- `basis`
- `regime_label`
- `n_dates`
- `mean_ic`
- `icir`
- `net_spread`
- `regime_status`: `OK / NOT_AVAILABLE`

Regime breakdown 不作为二期 hard gate，但报告必须展示。

### 5.11 Candidate pool 契约

`factor_candidate_pool.yaml` 改为：

```yaml
generated: "2026-06-14 ..."
recommendation: "NO_ALPHA_SOURCE_FOUND"
eligible_factors: []
watch_factors_for_review: []
support_factors:
  neutralizers:
    - log_market_cap_cs
  redundant: []
missing_data_factors:
  - roe_cs
  - gross_margin_cs
  - profit_growth_cs
  - revenue_growth_cs
  - leverage_cs
fail_factors: []
```

规则：

- `eligible_factors` 只能包含：
  - `role=alpha_candidate`
  - `final_status=PASS`
  - `cluster_representative=true`
  - `capacity_status != FAIL`
- `WATCH_*` 永远不自动进入下一阶段 sleeve。
- `role=neutralizer` 永远不进入 `eligible_factors`。
- 无 eligible 因子时 recommendation 必须为 `NO_ALPHA_SOURCE_FOUND`。

## 6. 报告修改

更新 `docs/factor_quality_rebuild_report.md`。

必须包含：

1. 总览：`PASS / WATCH / FAIL / DATA_MISSING` 数量。
2. No-leakage audit：每个因子的 data lag、aligned rows、状态。
3. Raw vs mcap-neutral：IC、ICIR、net spread、size dependency。
4. Turnover/cost：真实换手或 overlap proxy、net/gross ratio。
5. IC trend：slope、p-value、是否衰减。
6. Rolling validation robustness：四个窗口结果。
7. Correlation clusters：代表因子与冗余因子。
8. Capacity audit：可交易性和容量状态。
9. Regime breakdown：不同 regime 下的表现。
10. Candidate pool：eligible、watch、support、missing data、fail。

报告不得出现 `STUB`。

## 7. 测试计划

补强 `tests/test_factor_quality_rebuild.py`。

### 7.1 P0 测试

- `test_no_stub_outputs`
- `test_loader_preserves_duplicate_keys_for_audit`
- `test_factor_level_data_lag_alignment`
- `test_no_leakage_failure_blocks_gate`
- `test_coverage_denominator_is_fwd_universe`
- `test_real_turnover_changes_net_spread`
- `test_log_market_cap_never_eligible`

### 7.2 P1 测试

- `test_raw_pass_neutral_fail_becomes_watch_size_dependent`
- `test_raw_fail_neutral_pass_becomes_watch_neutral_only`
- `test_empty_fundamental_cache_is_data_missing_not_alpha_fail`
- `test_cluster_dedup_keeps_only_representative`
- `test_ic_decline_downgrades_pass_to_watch`
- `test_rolling_window_fragile_downgrades_pass`
- `test_capacity_fail_blocks_pass`
- `test_report_has_no_stub_and_contains_no_alpha_source_found`

### 7.3 回归命令

```powershell
python -m pytest -q tests/test_factor_quality_rebuild.py
python -m pytest -q tests/test_factor_quality_rebuild.py tests/test_factor_alignment.py tests/test_factor_pruning.py tests/test_strategy_alpha_failure_diagnosis.py
```

## 8. 全流程验收命令

```powershell
python scripts/factor_quality_rebuild.py `
  --config configs/factor_quality_rebuild.yaml `
  --start 20170101 `
  --end 20241231 `
  --out-dir outputs/analysis/factor_quality_rebuild `
  --out-doc docs/factor_quality_rebuild_report.md
```

PowerShell 验收检查：

```powershell
$code = @'
from pathlib import Path
import pandas as pd
import yaml

base = Path("outputs/analysis/factor_quality_rebuild")
required = [
    "factor_alignment_audit.csv",
    "factor_turnover_cost.csv",
    "factor_neutralization_diagnostic.csv",
    "factor_regime_breakdown.csv",
    "factor_capacity_audit.csv",
    "factor_ic_trend.csv",
    "factor_rolling_window_gate.csv",
    "factor_quality_gate.csv",
]

for name in required:
    p = base / name
    assert p.exists(), f"missing {name}"
    df = pd.read_csv(p, encoding="utf-8-sig")
    assert "STUB" not in set(df.astype(str).stack()), name

pool = yaml.safe_load((base / "factor_candidate_pool.yaml").read_text(encoding="utf-8-sig"))
assert "log_market_cap_cs" not in pool.get("eligible_factors", [])
assert all(f not in pool.get("eligible_factors", []) for f in pool.get("watch_factors_for_review", []))
if not pool.get("eligible_factors"):
    assert pool.get("recommendation") == "NO_ALPHA_SOURCE_FOUND"

print("OK")
'@
$code | python -
```

## 9. 验收标准

- 全流程退出码为 0。
- 所有预期 CSV 存在，且不含 `STUB`。
- no-leakage 结果进入最终 gate。
- coverage 按 `|factor ∩ fwd| / |fwd|` 计算。
- `factor_turnover_cost.csv` 使用 `REAL_WEIGHT_DRIFT` 或 `OVERLAP_PROXY`。
- `factor_quality_gate.csv` 同时包含 raw、mcap-neutral 和 final status。
- `factor_candidate_pool.yaml`：
  - `eligible_factors` 不含 `log_market_cap_cs`。
  - `WATCH_*` 不进入 `eligible_factors`。
  - 每个 correlation cluster 最多一个 eligible representative。
  - 无 eligible 因子时 recommendation 为 `NO_ALPHA_SOURCE_FOUND`。
- 空缓存基本面因子进入 `missing_data_factors`。
- 容量 FAIL 的因子不得 PASS。
- IC 衰减因子不得保持裸 PASS，必须降级 WATCH。
- rolling validation 不稳健的因子不得保持裸 PASS。
- 新增测试和回归测试全部通过。

## 10. 不在本期范围

本期不做：

- 新因子研发。
- 基本面数据管道补数。
- sleeve 权重优化。
- router/regime overlay 调参。
- 策略实盘参数搜索。
- 精细化市场冲击成本模型。

说明：基本面缓存为空的问题需要单独开数据管道修复方案。本期只保证这些因子被正确标记为 `DATA_MISSING`，不被误判为 alpha 失败。

## 11. 二期完成后的决策规则

完成二期后：

- 若存在 `eligible_factors`：可以进入下一阶段 sleeve 重建方案。
- 若只有 `WATCH_*`：不得自动重建 sleeve，先做人工复核和约束设计。
- 若全是 `FAIL + DATA_MISSING`：输出 `NO_ALPHA_SOURCE_FOUND`，优先修数据管道或研发新因子。
- 若基本面因子大量 `DATA_MISSING`：先补基本面缓存，再重新运行因子 gate。

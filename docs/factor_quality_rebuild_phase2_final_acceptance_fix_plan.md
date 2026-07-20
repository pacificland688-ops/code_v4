# Factor Quality Rebuild 二期最终验收整改开发方案

生成日期：2026-06-14

## 1. 背景

`Factor Quality Rebuild 二期验收整改` 已经完成一轮开发，并通过了当前单测、回归测试、产物验收脚本和一次全流程临时重跑。

已确认修复的关键问题包括：

- `first_trade_day_on_or_after` 已实现，非交易日不再回退到上一交易日。
- `ep_cs / bp_cs / sp_cs` 的 no-leakage 已从旧版 FAIL 修正为 PASS，`n_unmatured_rows_excluded=0`。
- capacity 成交额主路径已经从万元口径修正到 CNY 口径。
- `factor_correlation_cluster.csv` 即使为空也可被 `pd.read_csv` 正常读取。
- gate 不再因为 capacity hard fail 过早 return，`failure_reasons` 已能输出多项失败原因。
- 全流程可以完成，最近一次临时重跑耗时约 `421.1s`。

但本轮审核仍然发现剩余验收阻断项。当前版本不建议作为最终验收通过版本，原因是：

1. mcap-neutral 覆盖率严重不足，却仍被标为 `OK` 并参与 gate。
2. capacity audit 的市值字段仍是万元口径，却命名为 CNY。
3. capacity participation 估算使用了错误的 top leg 数量口径。
4. 产物验收脚本过宽，无法防止上述问题回归。

本方案用于指导最后一轮整改。目标不是新增 alpha，也不是调整阈值制造 PASS，而是修正二期验收可靠性，使 gate 结论真正可用于下一阶段决策。

## 2. 当前审核结论

当前版本状态：

```text
单测 tests/test_factor_quality_rebuild.py: 46 passed
回归集: 101 passed
产物验收脚本: 8/8 passed
全流程临时重跑: 完成，约 421.1s
```

正式产物摘要：

```text
factor_quality_gate.csv:
  FAIL = 11
  DATA_MISSING = 5
  WATCH_NEUTRAL_ONLY = 1
  SUPPORT = 1

factor_candidate_pool.yaml:
  eligible_factors = []
  recommendation = NO_ALPHA_SOURCE_FOUND
  watch_factors_for_review = [volatility_60_cs]
  support_factors.neutralizers = [log_market_cap_cs]
```

当前 `NO_ALPHA_SOURCE_FOUND` 结论仍不能作为最终可信结论，主要因为 `WATCH_NEUTRAL_ONLY` 和 neutral gate 相关判断受到低 neutralizer 覆盖率影响。

## 3. 本次整改目标

整改完成后，必须满足：

1. mcap-neutral 指标只有在 neutralizer 覆盖率达标时才允许参与 gate。
2. neutralizer 覆盖率不足时，不允许产生 `WATCH_NEUTRAL_ONLY` 或 final `PASS`。
3. capacity audit 中所有带 `_cny` 后缀的金额字段都必须是真实 CNY 口径。
4. capacity participation 使用真实 top/bottom leg 持仓数量或日度组合成交额估算，不再使用成交额数值去重数量。
5. 产物验收脚本能捕捉：
   - neutralizer 覆盖率低于配置阈值但状态为 `OK`。
   - 市值字段万元/CNY 单位错误。
   - capacity 数值量级明显异常。
   - `WATCH_NEUTRAL_ONLY` 基于无效 neutralization 产生。
6. 全流程重新生成正式产物后，若仍为 `NO_ALPHA_SOURCE_FOUND`，该结论才可作为二期最终验收结论。

## 4. 非目标

本轮不做以下事项：

- 不新增因子。
- 不放宽 `min_mean_rank_ic`、`min_icir`、coverage、turnover 等 gate 阈值。
- 不改变 `2021-2024` 作为 primary validation 的设置。
- 不重建 sleeve 或 strategy。
- 不引入复杂冲击成本模型。
- 不将 `log_market_cap_cs` 放入 `eligible_factors`。

## 5. 问题 1：mcap-neutral 覆盖率不足但仍参与 gate

### 5.1 现象

当前 `configs/factor_quality_rebuild.yaml` 中配置：

```yaml
neutralization:
  min_neutralizer_coverage_pct: 70
```

但正式产物 `factor_neutralization_diagnostic.csv` 中，多数 alpha 因子的 neutralizer 覆盖率远低于 70%：

```text
reversal_5_cs:        4.88%
reversal_20_cs:       5.20%
momentum_60_cs:       5.21%
momentum_120_cs:      5.15%
volatility_20_cs:     4.98%
volatility_60_cs:     5.09%
rsi_14_cs:            5.07%
macd_12_26_9_cs:      5.25%
pv_divergence_20_cs:  4.98%
ep_cs:               15.93%
bp_cs:               15.93%
sp_cs:               15.93%
```

这些因子仍出现：

```text
neutralization_status = OK
```

并且 `volatility_60_cs` 被最终判定为：

```text
WATCH_NEUTRAL_ONLY
```

这说明 neutral gate 使用了低覆盖率的 mcap-neutral 指标，结论不可靠。

### 5.2 根因

当前 `_neutralize_by_mcap` 会按日跳过低覆盖率日期，但 `_compute_neutralization_diagnostic` 只根据 `neutral_mean_ic` 是否为 NaN 判断状态：

```python
neutral_status = "OK" if neut_meta else "OK"
if np.isnan(neutral_mean_ic):
    neutral_status = "NOT_AVAILABLE"
elif size_dependency:
    neutral_status = "SIZE_DEPENDENT"
```

缺少以下判断：

- `neutralizer_coverage_pct < min_neutralizer_coverage_pct`
- validation 窗口内有效 neutralized 日期数不足
- neutralized 样本覆盖不足
- skipped dates 比例过高

### 5.3 设计原则

neutralization 是诊断和 gate 的输入，不是可选装饰字段。若 neutralization 覆盖率不足，则：

- 可以保留 raw gate 结果。
- 可以输出 neutralization diagnostic。
- 不能把 neutral gate 当作有效 PASS。
- 不能产生 `WATCH_NEUTRAL_ONLY`。
- 若配置 `neutralized_required_for_pass: true`，则不能 final `PASS`。

### 5.4 状态定义

新增或明确 neutralization 状态：

| 状态 | 含义 | 是否允许参与 neutral gate |
|---|---|---|
| `OK` | 覆盖率、样本数、有效日期均达标 | 是 |
| `SIZE_DEPENDENT` | neutralization 有效，且 raw alpha 明显依赖 size | 是 |
| `LOW_COVERAGE` | 平均覆盖率或有效日期覆盖率不足 | 否 |
| `INSUFFICIENT_DATES` | validation 有效 neutralized 日期不足 | 否 |
| `NOT_AVAILABLE` | 无法生成 neutralized 指标 | 否 |
| `REGRESSION_FAILED` | 截面回归失败过多 | 否 |

建议将 `SIZE_DEPENDENT` 视为有效 neutralization 的一个诊断标签，而不是失败状态。

### 5.5 配置扩展

在 `configs/factor_quality_rebuild.yaml` 的 `neutralization` 下增加：

```yaml
neutralization:
  enabled: true
  min_neutralizer_coverage_pct: 70
  min_stocks: 30
  min_valid_neutralized_dates: 60
  max_skipped_date_pct: 50
  require_valid_neutralization_for_neutral_gate: true
```

字段说明：

- `min_valid_neutralized_dates`：validation 窗口内 neutralized 有效交易日数量下限。
- `max_skipped_date_pct`：中性化跳过日期比例上限。
- `require_valid_neutralization_for_neutral_gate`：若为 true，neutralization 无效时 neutral gate 自动视为不可用。

### 5.6 代码修改方案

修改 `scripts/factor_quality_rebuild.py`。

#### 5.6.1 `_neutralize_by_mcap` 返回更完整 meta

当前 meta 已有：

```python
neutralizer_coverage_pct
size_beta_mean
size_beta_std
n_neutralized_dates
n_skipped_dates
skip_reason_top
```

需要补充：

```python
neutralizer_coverage_median_pct
neutralizer_coverage_min_pct
neutralized_row_count
raw_row_count
neutralized_row_coverage_pct
skipped_date_pct
neutralization_valid
neutralization_invalid_reason
```

计算口径：

```text
neutralizer_coverage_pct = mean(daily_intersection_count / daily_factor_count)
neutralizer_coverage_median_pct = median(daily_intersection_count / daily_factor_count)
neutralized_row_coverage_pct = non_null(value_mcap_neutral) / non_null(value_raw)
skipped_date_pct = n_skipped_dates / (n_neutralized_dates + n_skipped_dates)
```

#### 5.6.2 `_compute_neutralization_diagnostic` 接收 neutralization 配置

当前函数只接收 `neut_meta`，但不知道阈值。需要传入 `neutralization_cfg` 或提前在 meta 中计算 `neutralization_valid`。

建议函数签名改为：

```python
def _compute_neutralization_diagnostic(
    factor_cfg: dict,
    ic_raw: list[dict],
    ic_neutral: list[dict],
    quant_raw: list[dict],
    quant_neutral: list[dict],
    val_years: list[int],
    neut_meta: dict,
    neutralization_cfg: dict,
) -> dict[str, Any]:
```

状态判断顺序：

```python
if not neut_meta or neut_meta["neutralized_row_count"] == 0:
    neutral_status = "NOT_AVAILABLE"
elif neut_meta["neutralizer_coverage_pct"] < min_neutralizer_coverage_pct:
    neutral_status = "LOW_COVERAGE"
elif neut_meta["n_neutralized_dates"] < min_valid_neutralized_dates:
    neutral_status = "INSUFFICIENT_DATES"
elif neut_meta["skipped_date_pct"] > max_skipped_date_pct:
    neutral_status = "LOW_COVERAGE"
elif regression_failed_too_often:
    neutral_status = "REGRESSION_FAILED"
elif size_dependency:
    neutral_status = "SIZE_DEPENDENT"
else:
    neutral_status = "OK"
```

输出字段增加：

```text
neutralization_status
neutralization_valid
neutralization_invalid_reason
neutralizer_coverage_pct
neutralizer_coverage_median_pct
neutralized_row_coverage_pct
n_neutralized_dates
n_skipped_dates
skipped_date_pct
size_beta_mean
size_beta_std
```

### 5.7 gate 修改方案

在 `_apply_quality_gate` 中增加 neutralization validity 输入。

建议新增参数：

```python
neutralization_diag: dict
```

或从已有 diagnostic map 中读取：

```python
neutral_status = neutralization_diag.get("neutralization_status")
neutral_valid = neutralization_diag.get("neutralization_valid", False)
```

规则：

```text
neutral_valid = neutralization_status in ("OK", "SIZE_DEPENDENT")
```

若 `require_valid_neutralization_for_neutral_gate=true` 且 `neutral_valid=false`：

- neutral gate 不得记为 PASS。
- neutral failures 增加：

```text
neutralization: LOW_COVERAGE, coverage=5.09% < 70%
```

状态映射调整：

| raw gate | neutral gate | neutral valid | final status |
|---|---|---|---|
| PASS | PASS | true | PASS |
| PASS | FAIL | true | WATCH_SIZE_DEPENDENT |
| FAIL | PASS | true | WATCH_NEUTRAL_ONLY |
| FAIL | FAIL | true | FAIL |
| PASS | unavailable | false | WATCH_NEUTRAL_UNAVAILABLE |
| FAIL | unavailable | false | FAIL |

注意：

- `WATCH_NEUTRAL_ONLY` 只有在 `neutral_valid=true` 且 neutral gate PASS 时允许出现。
- `WATCH_NEUTRAL_UNAVAILABLE` 不进入 `eligible_factors`。
- 若 `neutralized_required_for_pass=true`，raw PASS 但 neutral invalid 不能 final PASS。

### 5.8 测试

新增测试类：

```text
TestNeutralizationValidity
```

测试用例：

1. `neutralizer_coverage_pct=5 < 70` 时，`neutralization_status=LOW_COVERAGE`。
2. low coverage 下，即使 neutral IC 看起来通过，也不能产生 `WATCH_NEUTRAL_ONLY`。
3. raw PASS + neutral unavailable 时，final status 为 `WATCH_NEUTRAL_UNAVAILABLE`。
4. raw FAIL + neutral unavailable 时，final status 为 `FAIL`。
5. `WATCH_NEUTRAL_ONLY` 必须要求 `neutralization_valid=true`。

## 6. 问题 2：capacity 市值字段单位错误

### 6.1 现象

当前 `factor_capacity_audit.csv` 中：

```text
median_market_cap_cny 中位数约 8,758,455
```

该数值更像 Tushare `total_mv` 的万元口径，而不是 CNY。

如果是真实 CNY，则代表中位市值仅约 875 万元，不符合 A 股 top/bottom 分位样本的常识；如果是万元，则真实 CNY 应为：

```text
8,758,455 * 10,000 = 87,584,550,000 CNY
```

### 6.2 根因

当前代码对成交额做了单位转换：

```python
db_date["_est_amount"] = db_date["circ_mv"] * db_date["turnover_rate"] * 100.0
```

但对市值仍直接读取：

```python
top_mv = db_date[...]["total_mv"]
bot_mv = db_date[...]["total_mv"]
```

然后输出为：

```python
"median_market_cap_cny": med_mcap
```

### 6.3 修改方案

新增标准化函数：

```python
def _standardize_daily_basic_money_fields(
    daily_basic: pd.DataFrame,
    capacity_cfg: dict,
) -> pd.DataFrame:
    ...
```

或拆成两个函数：

```python
def _market_cap_cny(df: pd.DataFrame, capacity_cfg: dict) -> pd.Series:
    ...

def _amount_cny(df: pd.DataFrame, capacity_cfg: dict) -> pd.Series:
    ...
```

默认 Tushare 口径：

```yaml
capacity:
  daily_basic_mv_unit: "wan_cny"
  daily_basic_amount_unit: "auto"
```

转换规则：

```python
if daily_basic_mv_unit == "wan_cny":
    total_mv_cny = total_mv * 10000
    circ_mv_cny = circ_mv * 10000
elif daily_basic_mv_unit == "cny":
    total_mv_cny = total_mv
    circ_mv_cny = circ_mv
else:
    raise ValueError(...)
```

成交额估算：

```python
estimated_amount_cny = circ_mv_cny * turnover_rate / 100.0
```

输出字段：

```text
median_top_amount_cny
median_bottom_amount_cny
median_top_market_cap_cny
median_bottom_market_cap_cny
median_market_cap_cny
```

### 6.4 兼容性要求

如果未来数据源提供真实 `amount` 字段，不能直接使用未标单位的列。

需要配置：

```yaml
capacity:
  amount_column: null
  amount_unit: "auto"
```

建议规则：

- 若 `amount_column` 未配置，优先使用 `circ_mv_cny * turnover_rate / 100`。
- 若 `amount_column` 已配置，则按 `amount_unit` 转换。
- `amount_unit=auto` 只能在有明确数据源元信息时启用，否则报错或 WARN。

### 6.5 测试

新增测试类：

```text
TestCapacityMoneyUnits
```

测试用例：

1. `total_mv=1_000_000` 万元时，输出 `median_market_cap_cny=10_000_000_000`。
2. `circ_mv=100_000` 万元、`turnover_rate=2` 时，输出 `estimated_amount_cny=20_000_000`。
3. 所有 `_cny` 字段不得保留万元口径。
4. 当数据源单位配置为 `cny` 时，不重复乘 `10000`。

## 7. 问题 3：capacity participation 估算口径错误

### 7.1 现象

当前代码：

```python
n_top_stocks = len(set(top_amounts)) if top_amounts else 50
daily_capacity = med_top_amt * n_top_stocks
participation = target_aum / max(daily_capacity, 1)
```

这里 `top_amounts` 是所有日期 top leg 股票的成交额数值列表。`len(set(top_amounts))` 代表成交额数值的去重数量，不代表股票数量，也不代表组合可交易容量。

### 7.2 风险

该逻辑会使 capacity 估算依赖成交额数值是否重复，而不是：

- 每天 top leg 有多少只股票。
- 每天 top leg 总成交额是多少。
- 目标 AUM 对单边交易量的参与率是多少。

当前结果可能量级看似合理，但逻辑不可验收。

### 7.3 修改方案

按日计算 capacity，再跨日期取统计量。

对每个 `trade_date`：

```text
top_amount_sum_cny = sum(amount_cny for stocks in top quantile)
bottom_amount_sum_cny = sum(amount_cny for stocks in bottom quantile)
top_count = count(top quantile stocks)
bottom_count = count(bottom quantile stocks)
```

组合容量估算：

```text
daily_leg_capacity_cny = min(top_amount_sum_cny, bottom_amount_sum_cny) * max_participation_rate
```

目标 AUM 的参与率粗估：

```text
required_trade_cny = target_aum_cny * expected_daily_turnover
participation_rate = required_trade_cny / min(top_amount_sum_cny, bottom_amount_sum_cny)
```

如果暂时没有 `expected_daily_turnover`，可使用真实换手模块输出的平均单日换手或配置：

```yaml
capacity:
  expected_daily_turnover: null
  fallback_daily_turnover: 0.05
```

最低要求：

```text
participation_rate_at_target_aum = target_aum_cny * fallback_daily_turnover / median_leg_amount_sum_cny
```

不要再用：

```text
target_aum / (median_single_stock_amount * number_of_unique_amount_values)
```

### 7.4 推荐输出字段

`factor_capacity_audit.csv` 增加：

```text
median_top_count
median_bottom_count
median_top_amount_sum_cny
median_bottom_amount_sum_cny
median_leg_amount_sum_cny
assumed_daily_turnover
estimated_trade_cny_at_target_aum
participation_rate_at_target_aum
estimated_capacity_cny
```

字段解释：

- `median_top_amount_cny`：top leg 单只股票成交额中位数。
- `median_top_amount_sum_cny`：top leg 日度总成交额中位数。
- `estimated_capacity_cny`：按最大参与率和假设换手反推的可承载 AUM。

推荐公式：

```text
estimated_capacity_cny =
  median_leg_amount_sum_cny * max_participation_rate / assumed_daily_turnover
```

### 7.5 状态判定

capacity status 建议使用两个维度：

1. 单只股票流动性：

```text
median_top_amount_cny >= min_median_amount_cny
median_bottom_amount_cny >= min_median_amount_cny
```

2. 组合容量：

```text
participation_rate_at_target_aum <= max_participation_rate
```

状态规则：

```text
若单只股票流动性不足: FAIL
若组合参与率超限: WATCH
否则: PASS
```

### 7.6 测试

新增测试类：

```text
TestCapacityParticipation
```

测试用例：

1. top leg 每天 10 只股票，每只成交额 1000 万，日度总成交额 1 亿。
2. `target_aum=10 亿`，`assumed_daily_turnover=5%`，需交易 5000 万。
3. participation 应为 `50%`，若阈值 5%，应 `WATCH`。
4. 改为 top leg 日度总成交额 20 亿时，participation 为 `2.5%`，应 `PASS`。
5. 不允许使用 `len(set(top_amounts))` 参与 capacity 计算。

## 8. 问题 4：产物验收脚本过宽

### 8.1 现象

当前 `scripts/validate_factor_quality_outputs.py` 能通过：

```text
VALIDATION PASSED: 8/8 checks OK
```

但它没有发现：

- neutralizer 覆盖率只有约 5%，却标 `OK`。
- `median_market_cap_cny` 实际仍是万元量级。
- `WATCH_NEUTRAL_ONLY` 基于低覆盖率 neutralization 产生。

### 8.2 修改方案

增强 `scripts/validate_factor_quality_outputs.py`。

#### 8.2.1 读取配置

新增参数：

```powershell
python scripts/validate_factor_quality_outputs.py `
  --out-dir outputs/analysis/factor_quality_rebuild `
  --config configs/factor_quality_rebuild.yaml
```

读取：

```yaml
neutralization.min_neutralizer_coverage_pct
neutralization.min_valid_neutralized_dates
capacity.min_median_amount_cny
capacity.daily_basic_mv_unit
capacity.max_participation_rate
```

#### 8.2.2 neutralization 校验

规则：

```text
若 neutralizer_coverage_pct < min_neutralizer_coverage_pct:
  neutralization_status 不得为 OK 或 SIZE_DEPENDENT
```

```text
若 quality_gate_status == WATCH_NEUTRAL_ONLY:
  对应 factor 的 neutralization_status 必须在 [OK, SIZE_DEPENDENT]
  且 neutralizer_coverage_pct >= min_neutralizer_coverage_pct
```

```text
若 quality_gate_status == PASS:
  neutralization_status 必须有效
```

#### 8.2.3 capacity 单位校验

当前 `< 1000` 的检查太弱。建议增强为：

```text
median_market_cap_cny 必须明显大于 median_top_amount_cny 的合理下限关系
```

更直接的规则：

```text
若 median_market_cap_cny 的全体中位数 < 1e9:
  FAIL，疑似仍为万元口径
```

对 A 股全市场分位组合而言，市值中位数小于 10 亿 CNY 极不合理。该检查用于防单位错误，不作为投资判断。

同时检查：

```text
median_top_amount_cny 中位数应大于 min_median_amount_cny 的一定比例
```

#### 8.2.4 capacity participation 校验

如果产物中存在以下字段：

```text
median_leg_amount_sum_cny
assumed_daily_turnover
estimated_trade_cny_at_target_aum
participation_rate_at_target_aum
```

验收脚本应复算：

```text
estimated_trade_cny_at_target_aum =
  target_aum_cny * assumed_daily_turnover

participation_rate_at_target_aum =
  estimated_trade_cny_at_target_aum / median_leg_amount_sum_cny
```

允许小范围 rounding tolerance。

#### 8.2.5 gate 合法性校验

新增规则：

```text
WATCH_NEUTRAL_ONLY requires valid neutralization.
PASS requires valid neutralization when neutralized_required_for_pass=true.
SUPPORT factors must not appear in eligible_factors.
```

### 8.3 测试

新增测试文件或测试类：

```text
tests/test_factor_quality_output_validation.py
```

测试用例：

1. neutralizer coverage 5%，status OK，验收脚本必须 FAIL。
2. `WATCH_NEUTRAL_ONLY` 但 neutralization low coverage，验收脚本必须 FAIL。
3. `median_market_cap_cny=8_000_000`，验收脚本必须 FAIL。
4. participation 字段与公式不一致，验收脚本必须 FAIL。
5. 正常产物样例应 PASS。

## 9. 代码修改清单

### 9.1 `scripts/factor_quality_rebuild.py`

必须修改：

- `_neutralize_by_mcap`
- `_compute_neutralization_diagnostic`
- `_apply_quality_gate`
- `_compute_capacity_audit`
- 写出 `factor_neutralization_diagnostic.csv` 的字段 schema
- 写出 `factor_capacity_audit.csv` 的字段 schema

重点要求：

- neutralization validity 必须进入 gate。
- `WATCH_NEUTRAL_ONLY` 不得基于 invalid neutralization。
- capacity 所有 `_cny` 字段必须统一 CNY。
- participation 不得使用 `len(set(top_amounts))`。

### 9.2 `configs/factor_quality_rebuild.yaml`

增加或确认：

```yaml
neutralization:
  min_neutralizer_coverage_pct: 70
  min_stocks: 30
  min_valid_neutralized_dates: 60
  max_skipped_date_pct: 50
  require_valid_neutralization_for_neutral_gate: true

capacity:
  daily_basic_mv_unit: "wan_cny"
  amount_unit: "derived_from_circ_mv"
  assumed_daily_turnover: 0.05
```

如果 `assumed_daily_turnover` 可以从真实换手模块读取，则配置值只作为 fallback。

### 9.3 `scripts/validate_factor_quality_outputs.py`

必须修改：

- 支持 `--config`。
- 校验 neutralization coverage 与 status 一致性。
- 校验 gate 状态与 neutralization validity 一致性。
- 校验 market cap CNY 量级。
- 校验 participation 公式。

### 9.4 `tests/test_factor_quality_rebuild.py`

新增测试：

- neutralization low coverage 不允许 gate 通过。
- raw FAIL + neutral invalid 不允许 `WATCH_NEUTRAL_ONLY`。
- capacity market cap 万元转 CNY。
- capacity participation 使用日度 leg amount sum。

### 9.5 `tests/test_factor_quality_output_validation.py`

建议新增，专门测试产物验收脚本。

## 10. 实施顺序

建议按以下顺序开发：

1. 先修 `_neutralize_by_mcap` meta，让 neutralization validity 可被计算。
2. 修 `_compute_neutralization_diagnostic`，输出 `LOW_COVERAGE / INSUFFICIENT_DATES / NOT_AVAILABLE`。
3. 修 `_apply_quality_gate`，阻断 invalid neutral gate。
4. 修 `_compute_capacity_audit` 的市值 CNY 转换。
5. 修 `_compute_capacity_audit` 的 participation 估算。
6. 扩展产物验收脚本。
7. 增加单测和产物验收脚本测试。
8. 跑单测和回归测试。
9. 跑全流程重新生成正式产物。
10. 跑增强后的产物验收脚本。
11. 更新 `docs/factor_quality_rebuild_report.md`。

## 11. 验收命令

### 11.1 单测

```powershell
python -m pytest -q tests/test_factor_quality_rebuild.py
```

### 11.2 回归测试

```powershell
python -m pytest -q `
  tests/test_factor_quality_rebuild.py `
  tests/test_factor_alignment.py `
  tests/test_factor_pruning.py `
  tests/test_strategy_alpha_failure_diagnosis.py
```

如果新增 `tests/test_factor_quality_output_validation.py`：

```powershell
python -m pytest -q tests/test_factor_quality_output_validation.py
```

### 11.3 全流程

```powershell
python scripts/factor_quality_rebuild.py `
  --config configs/factor_quality_rebuild.yaml `
  --start 20170101 `
  --end 20241231 `
  --out-dir outputs/analysis/factor_quality_rebuild `
  --out-doc docs/factor_quality_rebuild_report.md
```

### 11.4 产物验收

```powershell
python scripts/validate_factor_quality_outputs.py `
  --out-dir outputs/analysis/factor_quality_rebuild `
  --config configs/factor_quality_rebuild.yaml
```

## 12. 验收标准

### 12.1 neutralization 验收

必须满足：

```text
若 neutralizer_coverage_pct < 70:
  neutralization_status in [LOW_COVERAGE, NOT_AVAILABLE, INSUFFICIENT_DATES]
```

必须禁止：

```text
neutralizer_coverage_pct < 70 且 neutralization_status = OK
neutralizer_coverage_pct < 70 且 quality_gate_status = WATCH_NEUTRAL_ONLY
neutralizer_coverage_pct < 70 且 quality_gate_status = PASS
```

### 12.2 capacity 验收

必须满足：

```text
median_market_cap_cny 是 CNY 口径
median_top_amount_cny 是 CNY 口径
median_bottom_amount_cny 是 CNY 口径
participation_rate_at_target_aum 可由输出字段复算
```

禁止：

```text
median_market_cap_cny 保留万元口径但字段名为 *_cny
使用 len(set(top_amounts)) 估算持仓股票数量
```

### 12.3 gate 验收

必须满足：

```text
WATCH_NEUTRAL_ONLY 只允许在 neutralization_valid=true 时出现
PASS 只允许在 neutralization_valid=true 且 raw/neutral 均通过时出现
invalid neutralization 必须写入 failure_reasons 或 warning_reasons
```

### 12.4 产物验收

必须满足：

```text
所有 CSV 可读
无 STUB
candidate pool 契约正确
neutralization coverage/status 一致
capacity 单位正确
participation 公式可复算
```

## 13. 预期结果变化

修复后，当前的 `volatility_60_cs` 很可能不再是 `WATCH_NEUTRAL_ONLY`，因为它的 mcap-neutral 覆盖率约 5%，低于 70%。

可能的新状态：

```text
volatility_60_cs = FAIL
```

或如果 raw gate 独立通过：

```text
volatility_60_cs = WATCH_NEUTRAL_UNAVAILABLE
```

最终候选池仍可能是：

```text
eligible_factors = []
recommendation = NO_ALPHA_SOURCE_FOUND
```

但只有在本轮修复后，这个结论才可被认为是二期最终可信结论。

## 14. 最终交付材料

整改完成后，最终审核需要提供：

1. 修改文件清单。
2. 单测和回归测试结果。
3. 全流程运行命令、耗时和退出状态。
4. 增强产物验收脚本结果。
5. `factor_neutralization_diagnostic.csv` 摘要：
   - coverage 分布
   - status 分布
   - invalid neutralization 数量
6. `factor_capacity_audit.csv` 摘要：
   - 成交额 CNY 量级
   - 市值 CNY 量级
   - participation 分布
7. `factor_quality_gate.csv` 摘要：
   - final status 分布
   - `WATCH_NEUTRAL_ONLY` 是否仍存在
   - 若存在，必须证明 neutralization valid
8. `factor_candidate_pool.yaml` 摘要。

## 15. 最终判断规则

整改完成后：

- 若增强验收脚本失败，二期不通过。
- 若存在 low coverage neutralization 仍参与 gate，二期不通过。
- 若 capacity `_cny` 字段仍混用万元，二期不通过。
- 若全流程无法完成，二期不通过。
- 若全部通过但仍无 eligible factors，接受 `NO_ALPHA_SOURCE_FOUND`，进入下一阶段因子质量重建。

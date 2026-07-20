# Shock Reversal 修复与验收开发方案

生成日期：2026-06-11  
适用范围：`shock_reversal` sleeve、`abnormal_drop_reversal_5_cs` 因子、regime 接入与冻结验证流程  
当前状态：未通过验收，需修复后重新生成因子并验证

## 1. 背景与结论

`docs/shock_reversal_development_plan.md` 的开发目标是新增独立 `shock_reversal` sleeve，用于捕捉“异常残差下跌后的可交易反转”机会。当前实现已经新增了因子计算模块、配置和 regime 配置，但审核发现核心过滤、数据源、横截面处理和验证链路尚未闭环。

当前结论：

```text
不建议验收。
当前实现只能视为代码初稿接入，不能证明 shock_reversal 已按方案可交易、PIT 安全、成本后有效。
```

必须先修复 P0/P1 问题，再重新生成 `abnormal_drop_reversal_5_cs` 缓存，最后执行 Phase1 单因子评估、Phase2 单因子组合回测和 `E_shock_reversal` 边际贡献验证。

## 2. 问题清单

### P0-1 跌停过滤语义错误

涉及文件：

```text
factors/shock_reversal.py
```

当前逻辑：

```python
code_limits["is_limit_down"] = code_limits["down_limit"].notna()
```

问题：

`stk_limit` / `limit_status` 是每日涨跌停价格表。普通交易日普通股票也会有 `down_limit` 价格，因此 `down_limit.notna()` 只能表示“有跌停价数据”，不能表示“发生跌停”。

影响：

当前实现会把大多数有 `limit_status` 数据的日期全部识别为跌停或近期跌停，从而将信号置 0。实际会系统性误杀 `shock_reversal` 因子。

修复方向：

需要加载 raw price 的 `open` / `close`，并用价格比较判断：

```python
is_limit_down_close = close <= down_limit * 1.001
is_limit_down_open = open <= down_limit * 1.001
```

第一版建议使用 `close` 做近期跌停过滤，因为因子在 `t` 日收盘后生成；执行可交易性可另用 `t+1 open` 约束。

### P0-2 过滤后的 NaN 会被横截面处理补回

涉及文件：

```text
factors/shock_reversal.py
factors/cross_section.py
configs/factors.yaml
configs/factors_shock_reversal.yaml
```

当前逻辑：

`shock_reversal` 对停牌、ST、新股、低流动性等设为 `NaN`，但通用横截面处理器默认会补缺失值：

```python
cross_sectional_median -> fillna(median)
industry_median -> fallback to cross-sectional median
```

影响：

本应被剔除的股票会在 cross-section 阶段被中位数补回，继续进入 `abnormal_drop_reversal_5_cs` 和后续组合。过滤语义失效。

修复方向：

对 `shock_reversal` 必须区分：

```text
结构性缺失/不可交易过滤：必须剔除，不能填补
普通数值缺失：可以按通用规则处理或剔除
```

建议第一版采用最保守方案：

```text
shock_reversal 横截面处理 missing_method = drop
并在 FactorPanelBuilder 中为该因子使用专用 CrossSectionProcessor
```

### P1-1 流动性过滤没有按方案生效

涉及文件：

```text
factors/shock_reversal.py
data/tushare_client.py
data/panel_loader.py
```

当前逻辑：

`ShockReversalComputer` 从 `daily_basic` 请求：

```python
fields=["ts_code", "trade_date", "turnover_rate", "circ_mv", "amount"]
```

问题：

当前项目的 `daily_basic` 明确是月末快照，不是日频数据。`amount` 应来自 `daily` / `prices_raw`，不是 `daily_basic`。本地实际查询也显示日内 `daily_basic` 多数日期为空。

影响：

`amount_20d`、`turnover_20d` 和横截面分位过滤未按方案运行，低流动性噪声仍可能进入信号。

修复方向：

第一版建议：

```text
amount_20d 使用 prices_raw.amount 的 20 日均值
turnover_20d 如果 daily_basic 只有月末快照，则暂不作为硬过滤，或改为最近可得 daily_basic as-of 值并在文档中明确
横截面 amount_rank_cs >= 0.3 必须真正执行
```

如需严格满足原方案，则需要补齐日频 `daily_basic`，但这会改变当前项目数据层假设，应单独评估缓存体量和抓取成本。

### P1-2 shock 配置没有进入实际因子生成路径

涉及文件：

```text
factors/factor_panel.py
factors/cross_section.py
configs/factors_shock_reversal.yaml
```

当前逻辑：

`FactorPanelBuilder.cs` 默认调用：

```python
create_processor_from_config()
```

而 `create_processor_from_config` 默认读取：

```text
configs/factors.yaml
```

影响：

`configs/factors_shock_reversal.yaml` 中为 shock 因子写的横截面参数不会自动生效。当前实际生成路径仍使用通用配置。

修复方向：

新增因子级 cross-section 配置路由：

```text
abnormal_drop_reversal_5 -> configs/factors_shock_reversal.yaml 的 shock_reversal.cross_section
其他因子 -> configs/factors.yaml 的 cross_section
```

实现上可在 `FactorPanelBuilder` 中增加 `_process_factor_cross_section(name, df)`，按因子名选择处理器。

### P1-3 regime 验证不会真正纳入 shock 因子

涉及文件：

```text
run_research.py
configs/regime_shock_reversal.yaml
scripts/frozen_backtest_validation.py
```

当前状态：

本地没有：

```text
data/parquet/factors/factor_name=abnormal_drop_reversal_5*
```

`run_research.py` 在 regime 模式下只加载已存在于 parquet 缓存的 processed factor。当前 `configs/regime_shock_reversal.yaml` 声明了 `abnormal_drop_reversal_5_cs`，但运行时会被跳过。

影响：

`E_shock_reversal` 即使运行，也可能只是“少一个 sleeve 的 baseline”，而不是对 shock sleeve 的真实验证。

修复方向：

在运行 `E_shock_reversal` 前增加硬性前置检查：

```text
若 regime 配置声明 abnormal_drop_reversal_5_cs，但缓存不存在或覆盖不足，则直接失败，不允许静默跳过。
```

### P2-1 allocator 和测试仍有 5 sleeve 假设

涉及文件：

```text
alpha/regime_allocator.py
alpha/regime_composite.py
alpha/strategy_sleeves.py
tests/test_regime_allocator.py
```

当前测试结果：

```text
49 passed, 2 failed
```

失败原因：

部分测试和注释仍按 5 个 sleeve 断言，例如默认 equal weight 仍期待 `0.2`，但加入 `shock_reversal` 后应为 `1/6`。

修复方向：

统一使用 `SLEEVE_NAMES` 动态生成断言，不再硬编码 5 个 sleeve 或 `0.2`。

## 3. 修复目标

### 必须达成

1. `abnormal_drop_reversal_5` 原始信号能正确保留非跌停异常下跌样本。
2. ST、停牌、新股、近期跌停、低流动性过滤在 processed factor 后仍然有效。
3. 流动性过滤至少正确使用日频 `prices_raw.amount` 的 20 日均值并做横截面分位过滤。
4. `abnormal_drop_reversal_5_cs` 能生成 parquet 缓存，并被 regime 模式真实加载。
5. `E_shock_reversal` 验证结果必须明确包含 `shock_reversal` sleeve 的有效日期、平均权重和贡献。
6. 相关测试全部通过。

### 暂不强求

第一版可以继续暂缓：

```text
财报公告窗口过滤
PIT 行业中性化
VWAP-to-VWAP 执行口径
overlay 动态乘数
```

但必须在文档和验收报告中明确标注为未启用，不能写成已完成。

## 4. 详细开发方案

### Step 1 修复跌停过滤

修改 `ShockReversalComputer._compute_batch`：

1. 加载 raw price：

```python
raw_price_df = self.loader.query_prices(
    start_date=start_date,
    end_date=end_date,
    ts_codes=ts_codes,
    fields=["ts_code", "trade_date", "open", "close", "amount"],
    price_type="raw",
)
```

2. 将 raw price 传入 `_compute_stock_factor`。

3. 修改 `_apply_limit_down_filter` 签名：

```python
def _apply_limit_down_filter(signal, code, limit_df, raw_price_df, params):
```

4. 用 raw close 判定近期跌停：

```python
merged = raw_price_df.merge(limit_df, on=["ts_code", "trade_date"], how="left")
merged["is_limit_down_close"] = (
    merged["close"].notna()
    & merged["down_limit"].notna()
    & (merged["close"] <= merged["down_limit"] * 1.001)
)
```

5. 最近 3 个交易日检查必须基于交易日序列，不允许用 `date_int - d <= 3` 这种自然数差值。

建议实现：

```python
flag = is_limit_down_close.reindex(signal.index).fillna(False)
recent = flag.rolling(window=lookback, min_periods=1).max().astype(bool)
signal[recent] = 0.0
```

### Step 2 修复过滤剔除语义

建议方案：

1. 对不可交易过滤使用 `NaN`。
2. shock 因子 cross-section 阶段必须 `missing_method="drop"`。
3. 横截面处理器输出不应补回已剔除股票。

实现选择：

```text
新增 create_processor_from_dict 或 create_processor_from_nested_config
FactorPanelBuilder 对 abnormal_drop_reversal_5 单独初始化处理器
```

示例：

```python
if name == "abnormal_drop_reversal_5":
    cs_df = self.shock_cs.process_factor(df, name)
else:
    cs_df = self.cs.process_factor(df, name)
```

`configs/factors_shock_reversal.yaml` 建议改为：

```yaml
cross_section:
  missing_method: "drop"
  neutralize: true
  neutralizers:
    - "log_market_cap"
  standardize_method: "zscore"
  min_stocks_for_cs: 30
```

### Step 3 修复流动性过滤

第一版实现要求：

1. `amount_20d` 使用 `prices_raw.amount`。
2. 对每个交易日做横截面 rank。
3. `amount_rank_cs < 0.3` 的信号设为 `NaN`，且后续不得补回。

建议新增方法：

```python
def _apply_cross_sectional_amount_filter(raw_factor_df, raw_price_df, params):
```

处理流程：

```text
raw_price_df 按 ts_code/trade_date 排序
每只股票计算 amount_20d
合并 raw_factor_df
按 trade_date 计算 amount_20d.rank(pct=True)
低于 min_liquidity_rank 的 factor 值设为 NaN
```

关于 `turnover_rate`：

如果仍只有月末 `daily_basic`，第一版建议：

```text
不把 turnover_20d 作为硬过滤
只在诊断报告中输出最近可得 turnover_rate 覆盖率
```

如后续补齐日频 `daily_basic`，再启用：

```text
turnover_rank_cs >= 0.3
```

### Step 4 修复 ST 与停牌历史窗口

当前 `_load_st_periods(client, start_date)` 只读取 `ann_date >= start_date` 的 namechange，可能漏掉更早进入 ST、当前窗口仍在 ST 的股票。

修复建议：

```python
nc = client.get_namechange(start_date="19900101", end_date=end_date, use_cache=True)
```

或者提供足够长 lookback：

```text
至少从 20000101 读取 namechange
```

停牌记录也应注意跨窗口停牌：

```text
suspend_date < start_date 且 resume_date > start_date 的记录也必须覆盖
```

如果 Tushare 缓存无法按 resume_date 反查，需在 Phase0 数据准备阶段拉取更早停牌记录，或在审核报告中明确停牌跨窗口过滤不完整。

### Step 5 让 shock 因子生成成为显式流程

新增或扩展脚本：

```text
scripts/build_shock_reversal_factor.py
```

最小功能：

```bash
python scripts/build_shock_reversal_factor.py --start 20170101 --end 20241231 --recompute
python scripts/build_shock_reversal_factor.py --start 20250101 --end 20251231 --recompute
python scripts/build_shock_reversal_factor.py --start 20260101 --end 20260605 --recompute
```

脚本应输出：

```text
raw rows
processed rows
n_dates
n_stocks
coverage by year
NaN/filter counts by reason
limit_down filtered count
liquidity filtered count
ST/suspend/new_stock filtered count
```

### Step 6 加强 regime 前置检查

修改 `_select_regime_candidate_factors` 或 `build_regime_composite`：

当 regime 配置包含 `shock_reversal` 且声明 `abnormal_drop_reversal_5_cs` 时：

```text
若缓存缺失，直接返回错误
若覆盖率低于阈值，直接返回错误
```

建议阈值：

```text
n_dates >= 70% 目标 signal dates
每个有效日期 n_stocks >= 30
```

错误信息应明确：

```text
shock_reversal declared but abnormal_drop_reversal_5_cs missing or insufficient coverage
```

### Step 7 更新 allocator 与测试

修改测试：

1. 将 “all five sleeves” 改为动态读取 `SLEEVE_NAMES`。
2. empty config equal weight 从 `0.2` 改为 `1 / len(SLEEVE_NAMES)`。
3. 补充 `shock_reversal` 权重测试：

```text
regime_shock_reversal.yaml 中 range_bound shock_reversal 权重最高
trend_down/high_volatility 中 shock_reversal 权重较低
当 shock_reversal sleeve 不可用时，allocator 会把权重重新分配给其他 sleeve
```

## 5. 测试计划

### 单元测试

新增测试文件：

```text
tests/test_shock_reversal.py
```

必须覆盖：

1. `down_limit.notna()` 不等于跌停。
2. raw close 高于 `down_limit` 时信号不应被置 0。
3. raw close 等于/低于 `down_limit * 1.001` 时最近 3 个交易日信号置 0。
4. 最近 3 日逻辑基于交易日序列，不基于 `YYYYMMDD` 数值差。
5. ST / 停牌 / 新股过滤产生的 `NaN` 在 shock 专用 cross-section 后不会被补回。
6. `amount_20d` 横截面低分位股票被剔除。
7. `abnormal_drop_reversal_5` 方向为正：残差异常下跌越严重，原始 severity 越高。

### 回归测试

运行：

```bash
python -m pytest -q tests/test_shock_reversal.py
python -m pytest -q tests/test_regime_allocator.py tests/test_sleeve_performance_overlay.py tests/test_regime_config_validation.py
python -m pytest -q tests/test_factor_alignment.py tests/test_regime_factor_universe.py tests/test_tradable_limit_rules.py
```

通过标准：

```text
全部通过
无 xfail 掩盖核心 shock_reversal 行为
```

### 数据覆盖检查

运行因子生成后检查：

```python
loader.factor_coverage("abnormal_drop_reversal_5", start, end)
loader.factor_coverage("abnormal_drop_reversal_5_cs", start, end)
```

最低要求：

```text
2017-2024 每年均有有效覆盖
每年 signal date 覆盖率 >= 70%
每个有效日期平均股票数 >= 100
```

## 6. 验证计划

### Phase1 单因子评估

评估因子：

```text
abnormal_drop_reversal_5_cs
```

对比基准：

```text
reversal_5_cs
reversal_20_cs
pv_divergence_20_cs
momentum_60_cs
```

窗口：

```text
forward_return_windows = 3, 5, 10
```

指标：

```text
mean IC
ICIR
IC positive rate
top-bottom spread
turnover
coverage
IC decay
```

最低通过标准：

```text
mean IC > 0.02
ICIR > 0.30
IC positive rate > 52%
top-bottom spread 成本后为正
```

### Phase1 分层诊断

必须输出：

```text
流动性分层
市值分层
regime 分层
跌停过滤前后
ST/停牌/新股过滤前后
成本前后
```

如无法完成行业分层，需说明原因：

```text
行业数据非 PIT，暂不纳入验收
```

### Phase2 单因子组合回测

参数固定：

```text
top_n = 50
rebalance = weekly
weight_max = 0.02
cost = 1x / 2x
```

目标：

```text
确认该因子可交易，而不是仅有 close-to-close 统计优势
```

### Phase3 加入当前 D 方案做边际贡献

对比：

```text
D_regime_overlay
E_shock_reversal
D + shock_reversal disabled by missing cache check
```

必须确认：

```text
E_shock_reversal 的 diagnostics 中 shock_reversal 不是 EMPTY
shock_reversal_weight 平均值 > 0
shock_reversal active dates > 0
```

核心指标：

```text
2017-2024 平均年化超额
2017-2024 中位数年化超额
正超额年份数量
最大回撤
换手
成本 2x 后表现
2026 YTD 只作观察，不作调参依据
```

## 7. 验收标准

### 代码验收

1. `tests/test_shock_reversal.py` 新增并通过。
2. allocator 相关测试全部通过。
3. `abnormal_drop_reversal_5` 和 `abnormal_drop_reversal_5_cs` 缓存覆盖 2017-2024。
4. `regime_shock_reversal.yaml` 声明但缓存缺失时会失败，而不是静默跳过。
5. shock 专用 cross-section 不会补回过滤后的 `NaN`。

### 研究验收

至少满足：

```text
Phase1 单因子通过 mean IC / ICIR / positive rate 门槛
中高流动性股票中仍有效
剔除跌停、停牌、ST、新股后收益不消失
成本后 top-bottom spread 为正
```

### 组合验收

加入当前策略后至少满足：

```text
2017-2024 平均或中位数超额改善
正超额年份不减少
最大回撤不恶化
成本 2x 后不崩
shock_reversal 不是普通 reversal 的无效重复
```

## 8. 建议提交顺序

### Commit 1：修复核心因子语义

内容：

```text
跌停过滤改为 raw close/open 比较
流动性过滤改为 prices_raw.amount
recent limit down 使用交易日 rolling
```

测试：

```text
tests/test_shock_reversal.py
```

### Commit 2：修复 cross-section 与配置路由

内容：

```text
shock 因子专用 missing_method=drop
FactorPanelBuilder 按因子选择 CrossSectionProcessor
```

测试：

```text
tests/test_shock_reversal.py
tests/test_factor_alignment.py
```

### Commit 3：修复 regime 接入和前置检查

内容：

```text
缺失 shock factor 缓存时 E_shock_reversal 失败
diagnostics 输出 shock sleeve active dates / average weight
```

测试：

```text
tests/test_regime_factor_universe.py
tests/test_regime_allocator.py
```

### Commit 4：生成因子和冻结验证报告

内容：

```text
生成 abnormal_drop_reversal_5 / abnormal_drop_reversal_5_cs
跑 Phase1/Phase2/E_shock_reversal
更新 docs 验证报告
```

## 9. 风险与注意事项

1. 不能用 2026 YTD 调参，只能观察。
2. 不能因为第一版结果不好而微调阈值。
3. 缓存中如果已有错误版本 `abnormal_drop_reversal_5*`，必须清理后重算。
4. 日频 `daily_basic` 是否补齐要单独决策，不能在实现中悄悄混用月末快照冒充日频数据。
5. 财报窗口过滤暂未启用时，验收报告必须明确，不得写成已满足。

## 10. 最终 Go / No-Go 判定

修复完成后，如果仍出现以下任一情况，应判定为 No-Go：

```text
mean IC 或 ICIR 不达标
收益只来自低流动性股票
跌停/停牌/ST/新股过滤后收益消失
成本后 top-bottom spread <= 0
shock_reversal 与普通 reversal 高度重合且无增量
加入组合后边际贡献为负
发现 PIT 或未来函数问题
```

只有在单因子、可交易性、成本后表现和组合边际贡献同时通过时，才允许继续保留 `shock_reversal` sleeve。

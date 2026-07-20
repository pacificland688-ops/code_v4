# Shock Reversal Sleeve 开发方案

生成日期：2026-06-11  
适用项目：`code_v4` 沪深300横截面多因子策略  
开发方向：新增独立 `shock_reversal` sleeve，构建“异常下跌后可交易反转”收益来源

## 1. 目标

新增一个独立 sleeve：

```text
shock_reversal
```

它不等同于已有普通短期反转因子。它要捕捉的是：

```text
非市场系统性下跌、非行业同步下跌、非基本面重大恶化、非低流动性噪声导致的短期异常下跌后的反转机会。
```

目标不是简单买“过去 5 日跌得最多”的股票，而是识别：

```text
在市场、波动、流动性、事件、跌停、停牌和交易成本约束下，仍然表现为异常下跌的可交易股票。
```

该 sleeve 应与现有收益来源并列：

```text
value
momentum
reversal
defensive
volume_price
shock_reversal
```

## 2. Alpha 假设

### 2.1 原始假设

如果一只沪深300成分股在短期内出现显著负向残差收益，且该下跌不能被市场、行业、财报重大利空、长期趋势恶化、停牌跌停或低流动性噪声解释，则该下跌更可能来自临时流动性冲击、止损盘、情绪过度反应或短期资金错配。

预测：

```text
这类股票未来 3 到 10 个交易日存在部分价格反转。
```

### 2.2 可证伪预测

该 Alpha 必须能被以下检验证伪：

1. 异常下跌分数越高，未来短期收益越高。
2. 中高流动性股票中仍然有效。
3. 扣除买卖价差、滑点、佣金和冲击成本后仍有正收益。
4. 震荡市中更强，强趋势下跌和高波动恐慌中更弱。
5. 剔除财报窗口、跌停、停牌和低流动性股票后，收益不应消失。
6. 换成 next-open 或 VWAP 执行口径后，收益不应完全消失。
7. 加入现有组合后有正的边际贡献，而不是只重复普通 `reversal_5_cs`。

如果上述检验持续否定原始逻辑，应降权、暂停或退役该 sleeve。

## 3. 防过拟合原则

### 3.1 禁止事项

开发过程中禁止：

```text
根据 2026 YTD 调参数
根据单一年份调参数
反复搜索 lookback、threshold、holding_period
把 2025 当最终 OOS
用未来收益决定因子方向
用调仓日之后才知道的数据
用当前指数成分股回填历史
只保留表现好的过滤条件，删除表现差的过滤条件
```

### 3.2 初始参数必须事前固定

第一版参数只允许使用以下预设值：

| 参数 | 初始值 | 含义 |
|---|---:|---|
| `residual_return_window` | 5 | 异常下跌观察窗口 |
| `beta_window` | 60 | 市场 beta 估计窗口 |
| `residual_vol_window` | 60 | 残差波动估计窗口 |
| `drop_z_threshold` | 1.5 | 异常下跌触发阈值 |
| `forward_return_windows` | 3, 5, 10 | 单因子评估窗口 |
| `min_liquidity_rank` | 0.3 | 流动性过滤分位 |
| `limit_down_lookback` | 3 | 近期跌停过滤窗口 |
| `trend_penalty_window` | 20 | 中期趋势惩罚窗口 |
| `earnings_blackout_days_after` | 3 | 财报公告后过滤天数 |

这些参数来自经济逻辑，不来自网格搜索。第一轮不得微调阈值。

### 3.3 样本用途

建议固定样本用途：

| 样本 | 用途 |
|---|---|
| 2017-2020 | 初始研究与逻辑检查 |
| 2021-2022 | 参数冻结前验证 |
| 2023-2024 | 正式样本外验证 |
| 2025 | 当前项目问题诊断集，不作为最终 OOS |
| 2026 YTD | 前瞻观察，不用于调参 |

如果沿用当前项目冻结验证口径，也必须保持：

| 样本 | 用途 |
|---|---|
| 2017-2024 | 冻结验证 |
| 2025 | 问题发现和诊断 |
| 2026 YTD | 前瞻观察 |

任何样本划分必须在实验前写死，不得根据结果临时改变。

## 4. 防未来数据原则

### 4.1 信号生成时点

默认采用：

```text
t 日收盘后计算因子
t+1 开盘或 VWAP 执行
```

因此，`t` 日因子只能使用 `t` 日及以前已经可得的数据。未来 3、5、10 日收益只能用于评估，不能参与因子计算、过滤、权重或参数选择。

### 4.2 财务和公告数据

所有财务数据必须按照 `ann_date` 对齐。

示例：

```text
某年报报告期为 2024-12-31，公告日为 2025-03-28。
则 2025-03-28 之前不能使用该年报数据。
```

不得使用报告期 `end_date` 直接对齐交易日。

### 4.3 指数成分股

股票池必须使用历史真实沪深300成分：

```text
Tushare index_weight, index_code = 000300.SH
```

不得使用当前沪深300成分回填历史，避免幸存者偏差。

## 5. Tushare 数据需求

回测需要的数据必须从 Tushare 获取并缓存。不得用未来数据或手工填补未知字段。

### 5.1 行情数据：`daily`

字段：

```text
ts_code
trade_date
open
high
low
close
pre_close
change
pct_chg
vol
amount
```

用途：

```text
个股日收益
5 日收益
20 日趋势
60 日波动
成交额过滤
调仓执行价格
```

### 5.2 复权因子：`adj_factor`

字段：

```text
ts_code
trade_date
adj_factor
```

用途：

```text
构建后复权 open、high、low、close
避免除权除息造成虚假异常下跌
```

### 5.3 指数行情：`index_daily`

参数：

```text
ts_code = 000300.SH
```

字段：

```text
trade_date
open
close
pct_chg
vol
amount
```

用途：

```text
沪深300收益
rolling beta
市场残差收益
benchmark return
```

### 5.4 沪深300历史成分：`index_weight`

参数：

```text
index_code = 000300.SH
```

字段：

```text
index_code
con_code
trade_date
weight
```

用途：

```text
构建 PIT 沪深300 universe
防止幸存者偏差
```

### 5.5 涨跌停数据：`stk_limit`

字段：

```text
ts_code
trade_date
up_limit
down_limit
```

用途：

```text
识别开盘涨停不可买
识别开盘跌停不可卖
识别近期跌停股票
过滤连续跌停异常下跌
```

### 5.6 停复牌数据：`suspend_d`

字段：

```text
ts_code
trade_date
suspend_type
```

用途：

```text
停牌股票不能调仓
复牌异常跳空需要单独标记
```

### 5.7 每日基础指标：`daily_basic`

字段：

```text
ts_code
trade_date
turnover_rate
turnover_rate_f
volume_ratio
pe
pb
ps
total_mv
circ_mv
```

用途：

```text
换手率过滤
成交活跃度过滤
市值中性化
风格暴露控制
```

### 5.8 股票基础信息：`stock_basic`

字段：

```text
ts_code
symbol
name
area
industry
market
list_date
```

用途：

```text
新股过滤
基础行业字段兜底
```

### 5.9 名称变更和 ST 标记：`namechange`

字段：

```text
ts_code
name
start_date
end_date
change_reason
```

用途：

```text
识别 ST 和 *ST 历史区间
避免把退市风险或重大经营风险误判成流动性冲击
```

### 5.10 财报公告数据

可选接口：

```text
income
balancesheet
cashflow
fina_indicator
```

关键字段：

```text
ts_code
ann_date
end_date
```

用途：

```text
财报公告窗口过滤
避免把财报暴雷误判成短期超跌
```

第一版如果财报过滤暂未完整接入，可以先预留接口，但不能使用未来财务字段。

## 6. 因子定义

新增因子：

```text
abnormal_drop_reversal_5_cs
```

所属 sleeve：

```text
shock_reversal
```

### 6.1 后复权价格

```text
adj_close_i,t = close_i,t * adj_factor_i,t
```

如需执行价格，可同步生成：

```text
adj_open_i,t = open_i,t * adj_factor_i,t
```

### 6.2 个股日收益

```text
ret_i,t = adj_close_i,t / adj_close_i,t-1 - 1
```

### 6.3 市场收益

```text
ret_mkt_t = index_close_t / index_close_t-1 - 1
```

### 6.4 rolling beta

过去 60 个交易日估计个股对沪深300的 beta：

```text
beta_i,t = Cov(ret_i, ret_mkt, 60) / Var(ret_mkt, 60)
```

注意：

```text
如果 t 日收盘后生成信号，可以使用 t 日收益。
如果改为 t 日盘前信号，则不能使用 t 日收益。
```

### 6.5 5 日市场残差收益

```text
ret_5_i,t = adj_close_i,t / adj_close_i,t-5 - 1
ret_5_mkt_t = index_close_t / index_close_t-5 - 1

resid_ret_5_i,t = ret_5_i,t - beta_i,t * ret_5_mkt_t
```

第一版先使用市场残差。行业残差可作为后续增强，但必须保证行业数据 PIT。

### 6.6 残差波动

```text
daily_resid_i,t = ret_i,t - beta_i,t * ret_mkt_t
resid_vol_60_i,t = std(daily_resid_i, 60)
```

### 6.7 异常下跌 z-score

```text
drop_z_i,t = - resid_ret_5_i,t / (resid_vol_60_i,t * sqrt(5))
```

含义：

```text
过去 5 日残差下跌，相当于自身正常残差波动的多少倍。
```

### 6.8 异常强度

```text
severity_i,t = max(0, drop_z_i,t - 1.5)
```

只有残差下跌超过 1.5 sigma，才认为存在异常下跌信号。

## 7. 过滤和惩罚

### 7.1 流动性过滤

计算：

```text
amount_20d = rolling_mean(amount, 20)
turnover_20d = rolling_mean(turnover_rate, 20)
```

横截面分位：

```text
amount_rank_cs
turnover_rank_cs
```

过滤条件：

```text
amount_rank_cs >= 0.3
turnover_rank_cs >= 0.3
```

目的：

```text
避免低流动性股票中的 bid-ask bounce、成交价跳动和不可交易假收益。
```

### 7.2 涨跌停过滤

使用 `stk_limit`。

可定义：

```text
is_limit_down_t = close_t <= down_limit_t * 1.001
```

或者对执行可行性使用：

```text
open_t <= down_limit_t * 1.001
```

过滤：

```text
最近 3 日出现 limit_down，则 signal = 0
```

原因：

```text
连续跌停往往不可交易，且更可能是真实利空。
```

### 7.3 停牌过滤

使用 `suspend_d`：

```text
停牌日 signal = NaN
复牌首日可标记为 high_risk，不进入异常反转买入
```

### 7.4 新股过滤

使用 `stock_basic.list_date`：

```text
上市不足 120 个自然日或 60 个交易日，signal = NaN
```

### 7.5 ST 过滤

使用 `namechange`：

```text
历史名称处于 ST 或 *ST 区间，signal = NaN
```

### 7.6 中期趋势惩罚

如果股票不是短期冲击，而是中期持续恶化，应降低信号。

计算：

```text
ret_20_i,t = adj_close_i,t / adj_close_i,t-20 - 1
ret_20_mkt_t = index_close_t / index_close_t-20 - 1
resid_ret_20_i,t = ret_20_i,t - beta_i,t * ret_20_mkt_t
```

第一版使用简单规则：

```text
如果 resid_ret_20_z < -2.0，则 signal *= 0.5
```

目的：

```text
中期持续恶化的股票，不应被简单当成临时冲击。
```

### 7.7 财报窗口过滤

如果公告数据可用：

```text
ann_date 当日到后 3 个交易日，signal = 0
```

原因：

```text
财报后的下跌可能是基本面重新定价，而不是短期流动性冲击。
```

## 8. 最终因子公式

第一版保持简单：

```text
raw_signal_i,t = severity_i,t
```

然后依次应用过滤：

```text
如果 liquidity_rank < 0.3:
    raw_signal = NaN

如果 recent_limit_down:
    raw_signal = 0

如果 suspended:
    raw_signal = NaN

如果 is_ST:
    raw_signal = NaN

如果 new_stock:
    raw_signal = NaN

如果 in_earnings_window:
    raw_signal = 0

如果 medium_term_downtrend:
    raw_signal *= 0.5
```

横截面处理：

```text
winsorize(raw_signal)
neutralize(raw_signal, log_market_cap)
industry_neutralize 如果 PIT 行业数据可靠
zscore by trade_date
```

输出：

```text
abnormal_drop_reversal_5_cs
```

方向：

```text
值越高，越看多。
```

## 9. 新增 sleeve 设计

### 9.1 sleeve 定义

新增：

```text
shock_reversal
```

与旧 `reversal` 的区别：

| Sleeve | 含义 |
|---|---|
| `reversal` | 普通短期反转，主要基于过去收益 |
| `shock_reversal` | 异常残差下跌后的可交易反转，带流动性、事件、跌停、趋势过滤 |

### 9.2 初始权重

第一版不得高配。建议低权重接入。

参考权重：

| Regime | `shock_reversal` 初始权重 |
|---|---:|
| `range_bound` | 0.10 |
| `trend_up` | 0.05 |
| `trend_down` | 0.02 |
| `high_volatility` | 0.03 |
| `value_rotation` | 0.05 |

经济假设：

```text
震荡市更适合异常反转；
趋势下跌和高波动环境谨慎；
新 sleeve 未充分验证前不能主导组合。
```

### 9.3 overlay 接入

第一版建议先静态低权重接入，不立即使用 overlay 乘数。

当单因子验证通过后，再让 `sleeve_performance_overlay` 单独监控：

```text
shock_reversal mature IC
shock_reversal hit rate
shock_reversal top-bottom spread
shock_reversal cost-adjusted return
```

随后生成：

```text
shock_reversal_multiplier
```

## 10. Regime 适配假设

### 10.1 适合增强的状态

```text
range_bound
成交活跃
波动中等
市场非单边下跌
指数不处于强趋势崩盘
```

### 10.2 需要压低的状态

```text
trend_down
high_volatility
市场连续大跌
跌停股票比例上升
流动性收缩
```

### 10.3 验证重点

必须验证：

```text
shock_reversal 在 range_bound 中是否强于其他 regime
shock_reversal 在 trend_down 和 high_volatility 中是否显著变弱
```

如果 regime 分层结果不符合假设，应降低它在 allocator 中的权重或暂缓接入主策略。

## 11. 评估流程

### 11.1 Phase1 单因子评估

先不进入组合，单独评估：

```text
abnormal_drop_reversal_5_cs
```

对比基准因子：

```text
reversal_5_cs
reversal_20_cs
pv_divergence_20_cs
momentum_60_cs
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

forward return 窗口：

```text
3d
5d
10d
```

预期：

```text
3 到 5 日较强；
10 日仍有部分效果；
20 日后不应成为主要收益来源。
```

### 11.2 分桶检验

必须做以下分桶：

```text
流动性分桶
市值分桶
行业分桶
regime 分桶
财报窗口 vs 非财报窗口
跌停过滤前后
成本前后
```

### 11.3 bid-ask bounce 检验

必须做执行口径对照：

```text
close-to-close
next-open-to-next-open
VWAP-to-VWAP 如果可得
剔除低流动性后
扣 spread proxy 后
```

如果只有 close-to-close 有效，其它口径失效，则该因子不能进入主策略。

### 11.4 单因子 Phase2

只用该因子跑组合：

```text
top_n = 50
rebalance = weekly
weight_max = 0.02
cost = 1x / 2x
```

目的：

```text
确认该因子是否可交易，不是为了直接上线。
```

### 11.5 加入当前 D 方案做边际贡献

对比：

```text
D 原版
D + shock_reversal 低权重
D + shock_reversal 替换部分普通 reversal
D + shock_reversal + overlay
```

核心指标：

```text
2017-2024 平均年化超额
2017-2024 中位数年化超额
正超额年份数量
最大回撤
换手
成本
2026 YTD 是否明显反向
```

## 12. 验收标准

### 12.1 单因子通过标准

至少满足：

| 指标 | 门槛 |
|---|---:|
| mean IC | > 0.02 |
| ICIR | > 0.30 |
| IC 正向率 | > 52% |
| top-bottom spread | 成本后为正 |
| 中高流动性桶 | 仍然有效 |
| 剔除财报和跌停后 | 收益不消失 |
| bid-ask bounce 检查 | 不依赖收盘价噪声 |
| PIT 审计 | `future_obs = 0` |

### 12.2 组合边际贡献标准

加入当前策略后，应满足：

```text
2017-2024 平均超额改善
中位数超额改善
正超额年份不减少
最大回撤不恶化
换手增加有收益补偿
成本 2x 后不崩
2026 YTD 不明显反向
```

## 13. 失效、暂停和退役规则

### 13.1 警戒条件

出现以下情况应降权或暂停新增仓位：

```text
连续 3 个月 IC <= 0
成本后 top-bottom spread <= 0
收益只来自低流动性股票
换手上升但收益下降
shock_reversal 与普通 reversal 高度重合但无增量
```

### 13.2 暂停条件

出现以下情况应暂停该 sleeve：

```text
连续 6 个月 IC 为负
高流动性桶完全无效
扣成本后长期为负
在 range_bound regime 中也持续失效
```

### 13.3 退役条件

出现以下情况应退役：

```text
2017-2024 多数年份负贡献
过滤事件、跌停和 bid-ask bounce 后收益消失
加入组合后边际贡献为负
无法解释收益来源
发现未来数据或 PIT 问题
```

## 14. 开发落地建议

建议新增或修改：

```text
factors/shock_reversal.py
configs/factors_shock_reversal.yaml
configs/regime_shock_reversal.yaml
alpha/regime_allocator.py
alpha/sleeve_performance_overlay.py
eval/cs_evaluator.py
scripts/frozen_backtest_validation.py
scripts/frozen_backtest_attribution.py
```

### 14.1 新因子模块

新增：

```text
factors/shock_reversal.py
```

职责：

```text
计算 abnormal_drop_reversal_5_cs
处理 beta、残差收益、残差波动、流动性过滤、跌停过滤、停牌过滤、趋势惩罚
```

### 14.2 因子配置

新增：

```text
configs/factors_shock_reversal.yaml
```

建议结构：

```yaml
shock_reversal:
  enabled: true
  factors:
    - abnormal_drop_reversal_5_cs
  params:
    residual_window: 5
    beta_window: 60
    vol_window: 60
    drop_z_threshold: 1.5
    min_liquidity_rank: 0.3
    limit_down_lookback: 3
    trend_window: 20
    earnings_blackout_days_after: 3
```

### 14.3 Regime 配置

新增：

```text
configs/regime_shock_reversal.yaml
```

建议在 allocator 中加入：

```yaml
allocator:
  sleeves:
    - reversal
    - momentum
    - defensive
    - value
    - volume_price
    - shock_reversal
```

初始权重必须低配，并写清楚经济假设。

## 15. 最小开发路线

### Step 1：数据准备

确认 Tushare 缓存有：

```text
daily
adj_factor
index_daily
index_weight
daily_basic
stk_limit
suspend_d
stock_basic
namechange
财报 ann_date 数据
```

缺什么数据就通过 Tushare 接口补齐，不用手工构造。

### Step 2：研究版因子

只生成：

```text
abnormal_drop_reversal_5_cs
```

不进入组合。

### Step 3：Phase1 评估

对比：

```text
reversal_5_cs
reversal_20_cs
```

如果没有明显优于普通反转，停止接入主组合。

### Step 4：单因子 Phase2

单独回测该因子。

如果扣成本后无效，停止。

### Step 5：加入 `shock_reversal` sleeve

低权重加入当前 D 策略，看边际贡献。

### Step 6：冻结复验

冻结配置后复验：

```text
2017-2024
2026 YTD 仅观察
```

2025 只作为问题诊断，不作为最终 OOS 证据。

## 16. 最终判断

这个开发方向只有在以下条件同时满足时，才值得继续：

```text
它不是普通 reversal 的重复
它不是低流动性幻觉
它不是财报利空误判
它不是 bid-ask bounce
它在成本后仍有收益
它在 range_bound regime 中更强
它加入组合后有正边际贡献
它不靠单一年份或单月贡献全部收益
```

一句话总结：

```text
shock_reversal 要证明自己捕捉的是“可交易的临时流动性冲击反转”，而不是“跌多了就赌反弹”。
```

如果证明不了，就不进入主策略。

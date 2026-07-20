# V4 PIT 对齐规则

生成日期：2026-06-14  
适用范围：所有 V4 新增基本面、财务、现金流类因子  
原则：先 PIT，再 IC — 未通过 PIT 审计的因子不得进入候选池。

## 1. 核心规则

### 规则 1：基本面因子必须使用公告日对齐

```
available_date = ann_date（公告日）
source_date   = f_ann_date（实际公告日，如有）或 end_date（报告期末）
trade_date    = 信号生成日（调仓日）
约束：ann_date <= trade_date（公告日后才可用于交易）
```

**禁止行为：** 使用报告期末（`end_date`）直接作为 `available_date` 来对齐。这会导致未来财报数据穿越到历史交易日。

### 规则 2：若公告日缺失，使用保守滞后

```
保守滞后规则：
- 年报（1231 截止）：次年 4 月 30 日前必须公告 → min(ann_date, end_date + 120 天)
- 中报（0630 截止）：当年 8 月 31 日前必须公告 → min(ann_date, end_date + 60 天)
- 季报（0331/0930 截止）：季末后 30 天 → min(ann_date, end_date + 30 天)

如果 ann_date 为 null：
- 年报 → end_date + 120
- 中报 → end_date + 60
- 季报 → end_date + 30
```

### 规则 3：禁止未来数据穿越

```python
# 每条因子记录的硬约束
assert available_date <= trade_date, \
    f"FUTURE_LEAKAGE: {factor_name} available_date={available_date} > trade_date={trade_date}"
```

### 规则 4：每个因子记录必须可追溯

```
必需审计字段：
- factor_name     : 因子名
- ts_code         : 股票代码
- trade_date      : 交易日期（信号生成日）
- source_period   : 数据来源报告期（如 20230630）
- source_date     : 数据来源日期（如 end_date=20230630）
- available_date  : 数据可用日期（公告日或保守滞后日期）
- value           : 因子值
- pit_lag_days    : trade_date - available_date（公告到使用的滞后期）
- is_stale        : 是否超过最大滞后容忍天数
```

## 2. 按数据类型的 PIT 规则

### 2.1 价格数据（已有，不变）

| 数据 | available_date | 最大滞后 | 备注 |
|------|------|------|------|
| `prices_adj` | `trade_date`（当日可用） | 0 天 | 收盘价在收盘后可用 |
| 成交量 | `trade_date` | 0 天 | |
| 复权因子 | `trade_date` | 0 天 | |

**V4 因子：** 所有技术类、动量类、行业相对强弱类因子均使用价格数据，无 PIT 风险。

### 2.2 日频基本面（daily_basic）

| 数据 | available_date | 最大滞后 | 备注 |
|------|------|------|------|
| PE, PB, PS | `trade_date`（日频更新） | 0 天 | 估值比率基于最新收盘价，日内可用 |
| total_mv | `trade_date` | 0 天 | |

**V4 因子：** `ep_cs`, `bp_cs`, `sp_cs`, `log_market_cap_cs` → 沿用现有逻辑，无新增 PIT 风险。

### 2.3 利润表数据（income）

| 数据 | available_date | 最大滞后容忍 | PIT 风险等级 |
|------|------|------|------|
| 营业收入 (revenue) | `ann_date` | 120 天（年报上限） | 🟡 中 |
| 净利润 (n_income) | `ann_date` | 120 天 | 🟡 中 |

**V4 因子：** `revenue_growth_ttm_cs`, `profit_growth_ttm_cs`, `earnings_acceleration_cs`

**TTM 计算规则：** 使用最近 4 个季度的收入/利润加总（或最近 1 个年报），但每期数据仅在公告日后可用。

```
ttm_value(trade_date) = sum of last 4 quarterly values
                        where ann_date(quarter) <= trade_date
                        and most recent period end_date is within 12 months of trade_date
```

### 2.4 财务指标数据（fina_indicator）

| 数据 | available_date | 最大滞后容忍 | PIT 风险等级 |
|------|------|------|------|
| ROE (roe) | `ann_date` | 120 天 | 🟡 中 |
| ROA (roa) | `ann_date` | 120 天 | 🟡 中 |
| 毛利率 (grossprofit_margin) | `ann_date` | 120 天 | 🟡 中 |
| 净利率 (netprofit_margin) | `ann_date` | 120 天 | 🟡 中 |
| 经营现金流相关 | `ann_date` | 120 天 | 🔴 高（字段名不确定） |

**V4 因子：** `roe_stability_8q_cs`, `roa_ttm_cs`, `gross_margin_ttm_cs`, `net_margin_ttm_cs`, `profitability_quality_cs`, `ocf_to_profit_cs`

**稳定性计算规则：**
```
roe_stability_8q = -std(ROE over last 8 available quarters)
                    where ann_date(quarter) <= trade_date
```

### 2.5 行业分类数据

| 数据 | available_date | 最大滞后 | PIT 风险等级 |
|------|------|------|------|
| 申万行业分类 | 发布日（实际可能与数据日同期） | 0 天（过于保守） | 🟢 低 |

**V4 因子：** 所有 `industry_relative_*` 因子。

## 3. V4 审计字段规范

每个 V4 基本面因子缓存必须包含以下字段：

```yaml
factor_name: "revenue_growth_ttm_cs"
ts_code: "000001.SZ"
trade_date: 20170103
source_period: "20160930"      # 最近可用季度报告期
source_date: 20160930          # 报告期结束日
available_date: 20161028       # 公告日
value: 0.0321                  # 因子值
pit_lag_days: 66               # trade_date - available_date
is_stale: false                # 是否超过最大容忍天数
```

## 4. PIT 审计检查项

审计脚本（`scripts/audit_alpha_inputs_v4.py`）将检查：

| 检查项 | 说明 | 严重级别 |
|------|------|------|
| `future_leakage` | `available_date > trade_date` 的记录 | FAIL |
| `missing_available_date` | `available_date` 为空的记录 | FAIL |
| `stale` | `pit_lag_days > max_tolerance` 的记录 | WARN |
| `missing_source_period` | 无法追溯到报告期 | WARN |
| `constant` | 因子值在多日保持不变 | WARN |
| `duplicate` | 同一 `(ts_code, trade_date)` 有多个因子值 | FAIL |
| `coverage` | 某日覆盖股票数低于阈值 | WARN |

## 5. PIT 不通过的处理

1. 如果某因子有 **future_leakage** 记录 → 该因子标记为 FAIL，说明 PIT 对齐实现有 bug。
2. 如果某因子有 **high stale rate**（>30% 的记录超过最大容忍天数）→ 标记为 WATCH，在经济解释中写明影响。
3. 如果某因子 **无公告日数据** → 进入 `blocked_factors`，不能进入候选池。
4. 如果某因子在 2017-2020 年 **coverage < 50%** → 标记覆盖不足，在 gate 中作为额外风险说明。

## 6. 实施要点

1. 所有 V4 基本面因子的计算函数必须接收 `ann_date` 作为 PIT 过滤器。
2. 因子缓存（parquet）必须包含 `available_date` 字段。
3. `build_alpha_factors_v4.py` 必须为每个因子生成 `factor_manifest.json`，记录输入数据版本和 PIT 规则。
4. 测试文件 `test_alpha_inputs_v4.py` 必须覆盖所有 PIT 检查项。

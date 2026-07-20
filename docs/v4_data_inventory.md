# V4 数据字段盘点

生成日期：2026-06-14  
数据来源：Tushare Pro API → 本地 Parquet 缓存  
审核范围：2017-01-01 至 2024-12-31（验证窗口）+ 2026-01-01 至 2026-06-05（YTD）

## 1. 已有数据表

| 数据表 | Tushare API | 本地路径 | 频率 | 最早可用 | 最近可用 |
|------|------|------|------|------|------|
| `prices_adj` | `pro.daily` | `data/parquet/prices_adj/` | 日频 | ~1990 | 2026-06 |
| `prices_raw` | `pro.daily` | `data/parquet/prices_raw/` | 日频 | ~1990 | 2026-06 |
| `adj_factor` | `pro.adj_factor` | `data/parquet/adj_factor/` | 日频 | ~1990 | 2026-06 |
| `daily_basic` | `pro.daily_basic` | `data/parquet/daily_basic/` | 日频 | ~2010 | 2026-06 |
| `index_weight` | `pro.index_weight` | `data/parquet/index_weight/` | 月频 | ~2010 | 2026-06 |
| `index_daily` | `pro.index_daily` | `data/parquet/index_daily/` | 日频 | ~1990 | 2026-06 |
| `limit_status` | `pro.limit_list` | `data/parquet/limit_status/` | 日频 | ~2010 | 2026-06 |
| `stock_status` | `pro.namechange` | `data/parquet/stock_status/` | 事件驱动 | ~1990 | 2026-06 |
| `trade_cal` | `pro.trade_cal` | `data/parquet/trade_cal/` | 日频 | ~1990 | 2026-12 |
| `fina_indicator` | `pro.fina_indicator` | Parquet 缓存 | 季频（基于公告日） | ~2010 | 2026 Q1 |
| `income` | `pro.income` | Parquet 缓存 | 季频（基于公告日） | ~2010 | 2026 Q1 |
| `industry_pit` | `pro.index_classify` | `data/parquet/industry_pit/` | 年报 | 2007 | 2025 |

## 2. 已有数据字段

### 2.1 daily_basic（日频基本面）

| 字段 | 类型 | 说明 | 覆盖 | 备注 |
|------|------|------|------|------|
| `ts_code` | str | 股票代码 | 全量 | |
| `trade_date` | int | 交易日 | 全量 | |
| `pe` | float32 | 市盈率 | 较好 | 负值表示亏损 |
| `pb` | float32 | 市净率 | 较好 | |
| `ps` | float32 | 市销率 | 较好 | |
| `total_mv` | float64 | 总市值 | 全量 | |
| `circ_mv` | float64 | 流通市值 | 全量 | |
| `turnover_rate` | float32 | 换手率 | 较好 | |

**已有 V2/V3 因子利用情况：** ep_cs (1/pe), bp_cs (1/pb), sp_cs (1/ps), log_market_cap_cs → 已全部在此表中。

### 2.2 fina_indicator（财务指标，季频，基于公告日）

| 字段 | 说明 | V4 用途 | 覆盖风险 |
|------|------|------|------|
| `roe` | ROE (净资产收益率) | `roe_stability_8q_cs`, `profitability_quality_cs` | 2017 年前可能覆盖率低 |
| `roa` | ROA (总资产收益率) | `roa_ttm_cs`, `profitability_quality_cs` | 同上 |
| `grossprofit_margin` | 毛利率 | `gross_margin_ttm_cs` | 2017 年前中等 |
| `netprofit_margin` | 净利率 | `net_margin_ttm_cs` | 同上 |
| `profit_dedt` | 扣非净利润 | 盈余质量检查 | 同上 |
| `eps` | 每股收益 | 辅助 | 较好 |
| `cf_sales` | 经营活动现金流/营收 | 无（不是标准字段，需确认） | — |
| `asset_turnover` | 可能不可用 | `asset_turnover_ttm_cs` | 待确认 |

**风险：** Tushare `fina_indicator` 字段列表需要运行时验证，部分字段可能在 2017 年前不可用。

### 2.3 income（利润表，季频，基于公告日）

| 字段 | 说明 | V4 用途 | 覆盖风险 |
|------|------|------|------|
| `revenue` | 营业收入 | `revenue_growth_ttm_cs` | 2017 年前中等 |
| `n_income` | 净利润 | `profit_growth_ttm_cs` | 同上 |
| `total_cogs` | 营业成本（可能不可用） | 毛利率计算 | 需确认 |

### 2.4 缺失但 V4 可能需要的数据

| 数据 | 说明 | 影响因子 | 替代方案 |
|------|------|------|------|
| 现金流量表 (`cashflow`) | 经营现金流、自由现金流 | `ocf_to_profit_cs`, `fcf_yield_cs` | 如 Tushare 不支持此 API，需要回退到 `fina_indicator` 中的现金流字段 |
| `balancesheet` | 应收账款、总资产、负债 | `accrual_quality_cs`, `receivable_pressure_cs` | 如不可用则这些因子进入 blocked list |
| 股息数据 | 股息率、股息支付记录 | `dividend_quality_cs` | Tushare `pro.dividend` 可能可用 |
| 公告日精确数据 | 与财报 `f_ann_date` 的差距 | PIT 对齐 | 已有 `ann_date` 字段可用 |

## 3. 数据覆盖评估

### 3.1 按因子类别

| 因子类别 | 数据源 | 覆盖评级 | 2017-2020 缺失风险 | 备注 |
|------|------|------|------|------|
| 成长类 | `income` (revenue, n_income) | 🟡 中等 | 小市值公司早期数据可能不完整 | 主要依赖利润表，CSI300 成分股覆盖率应较高 |
| 质量类 | `fina_indicator` (roe, roa, margins) | 🟡 中等 | 早期 ROE/毛利率等可能仅年报 | 需要至少 4 季度数据来构建 TTM |
| 现金流类 | `fina_indicator` 或 `cashflow` | 🔴 高风险 | 早期现金流数据覆盖可能很差 | **需要运行时审计** |
| 估值修复类 | `daily_basic` (pe, pb, ps) + 行业分类 | 🟢 低风险 | 已有数据完全覆盖 | 行业分类 2007 年起有 |
| 行业相对强弱 | 价格数据 + 行业分类 | 🟢 低风险 | 完全覆盖 | 价格数据全量 |
| 风险调整动量 | 价格数据 + 成交量 | 🟢 低风险 | 完全覆盖 | 全量价格数据 |

### 3.2 按时间段

| 时间段 | daily_basic | fina_indicator | income | 价格数据 |
|------|:---:|:---:|:---:|:---:|
| 2017-2019 | 🟢 全 | 🟡 部分 | 🟡 部分 | 🟢 全 |
| 2020-2022 | 🟢 全 | 🟢 较好 | 🟢 较好 | 🟢 全 |
| 2023-2024 | 🟢 全 | 🟢 全 | 🟢 全 | 🟢 全 |
| 2026 YTD | 🟢 全 | 🟡 Q1 数据 | 🟡 Q1 数据 | 🟢 全 |

## 4. Blocked Factors（数据不足无法构建）

以下因子因数据源不可用或覆盖不足，暂列入 blocked：

| 因子 | 阻塞原因 | 替代方案 | 解封条件 |
|------|------|------|------|
| `accrual_quality_cs` | 需要资产负债表（应收账款）、现金流量表（经营现金流） | 如 Tushare Pro 支持 `balancesheet` API → 可建 | 确认 Tushare `balancesheet` API 可用 |
| `receivable_pressure_cs` | 需要应收账款变化数据 | 同上 | 同上 |
| `cashflow_stability_8q_cs` | 需要 8 季度现金流量表 | 如现金流量表覆盖不足，用 `fina_indicator` 现金流字段替代 | 确认 `fina_indicator` 有现金流字段 |
| `asset_turnover_ttm_cs` | 需要总资产和收入数据（跨表） | 如 `fina_indicator` 有 `asset_turnover` 字段则直接用 | 运行时确认 |

## 5. 后续步骤

1. 用 `scripts/audit_alpha_inputs_v4.py`（M2.3）实际运行审计，确认各字段 2017-2024 的真实覆盖。
2. 不假设字段存在 — 脚本应检测字段缺失并报告。
3. 覆盖不足因子写入 `blocked_factors`，不静默缺失。

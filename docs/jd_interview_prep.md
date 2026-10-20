# 平安证券量化策略研究岗：用本仓库准备 JD

原则：每条 JD 只准备 **一个故事 + 两三个文件 + 一个数字**。不要背整个仓库。

冻结结果（面试可投屏）：
`outputs/frozen_runs/product_compare_2017_2024_ledger_v1/DECISION.md`

---

## 七日准备（每天 90 分钟）

| 天 | 主题 | 必读 |
|---|---|---|
| D1 | 30 秒定位 + 冻结表 | 本文件 §0、`DECISION.md` |
| D2 | 数据 PIT 与涨跌停 | `data/universe.py`、`data/tradable.py`、`data/industry.py` |
| D3 | 因子库与 IC | `factors/technical.py`、`factors/cross_section.py`、`eval/cs_evaluator.py` |
| D4 | 回测账户 | `products/weekly_long.py`、`backtest/execution.py`、`backtest/cost_model.py` |
| D5 | 裁决与冻结 | `products/metrics.py`、`scripts/run_frozen_product_compare.py` |
| D6 | 影子盘/事件 | `live/run_shadow.py`、`live/risk_gate.py`、`live/photoresist_panic/runner.py` |
| D7 | 缺口演练 | 算法交易、ETF 轮动、经纪赋能：只练「边界怎么说」 |

每天结束：对着镜子讲 3 分钟，再假装被追问 2 个问题。

---

## §0 开场（所有 JD 条款的总开关）

「我做的是 A 股日频可交易性研究平台。信号很普通：周频低波等权 top-50。真正做完的是账户约束和裁决纪律：T+1、涨跌停未知不可买、未成交留现金、费用从现金出。2017–2024 冻结重跑后，这些产品对照是数据不足，不是我宣布找到了 alpha。」

卡住就停。不要往下堆因子名字。

---

## JD-1 股票/ETF 策略研发全流程

**JD 原文要点：** 多因子、行业轮动、ETF 轮动、套利；因子→模型→回测→实盘。

**你有的：** 多因子主线 + 低波产品对照 + 行业/ETF 对照入口 + 影子盘。没有可交易的统计套利 book。

**30 秒：**  
全流程在仓库里是四段：`factors/` 算因子，`alpha/` 做加权和 regime，`products/weekly_long.py` 做 T+1 账户，`live/run_shadow.py` 做纸面。主线沪深300 多因子历史是 NO-GO；产品对照冻结后是 DATA_INSUFFICIENT。我把「没 alpha」和「数据不够判」分开了。

**必打开：**

1. `factors/cross_section.py` — 行业+市值中性  
2. `products/weekly_long.py` — 信号日 t，成交 t+1，持有到下次成交  
3. `outputs/frozen_runs/.../DECISION.md` — 300/500/1000/ETF 分类表  

**会问：** 行业轮动呢？  
答：对照入口要求申万 L1 指数，本地只有 `801050.SI`，所以记 ERROR，没有用 11 只杂指数冒充行业轮动。ETF 轮动做过 10 只、60 日动量，冻结后中位超额约 +0.2%，但仍因费用预算记数据不足；而且持仓几乎静态，不能当轮动产品讲。

**会问：** 套利呢？  
答：没有配对/残差 book。2018 做过滞后 beta 残差诊断，那是归因不是可交易中性策略。

**不要说：** 我有行业轮动和 ETF 轮动策略。

---

## JD-2 算法交易（VWAP/TWAP/IS）

**你有的：** 日频 VWAP 近似、IS 相对 VWAP 的评估；事件策略里的 AVWAP 是路径规则，不是 ped。

**30 秒：**  
执行层在 `backtest/execution.py`：T+1、整手、可买可卖、未成交留现金。成本在 `backtest/cost_model.py`：佣金、印花税、过户、5bp 滑点。IS 是成交价相对当日 VWAP 的评估指标，用来比较开盘 vs VWAP 口径，不是我训练了一个 VWAP 算法。

**必打开：** `backtest/cost_model.py` 头部注释（费率）、`backtest/execution.py` 的 `execute_rebalance`。

**边界句（背下来）：**  
「我没有做订单簿或动态 ped。若岗位以算法交易为主，这是我需要在岗上补的；我的强项是把执行约束写进研究账户。」

**不要说：** 我做过 AI-VWAP / 高频算法实盘。

---

## JD-3 因子库与数据模型

**你有的：** 量价+部分基本面、截面中性、parquet 分区缓存、DuckDB/PyArrow。没有 TensorFlow 生产模型（`alpha/ml_alpha.py` 是 sklearn）。

**30 秒：**  
原始数据 Tushare → `data/parquet/` 分区。因子在 `factors/technical.py`、`fundamental.py`，截面处理在 `cross_section.py`（行业、市值中性）。评估用 IC / ICIR / 分层。ML 是 sklearn GBDT，不是 TensorFlow。

**必打开：**

- `data/parquet_cache.py` 或 `data/panel_loader.py` — 怎么读分区  
- `factors/cross_section.py` 的 `neutralize`  
- `eval/cs_evaluator.py` — IC 怎么算  

**数字：** 冻结低波因子在信号日、5 日收益上 raw Rank IC 约 0.053、行业+市值中性后约 0.042。IC 在，不代表账户能赢指数。

**会问：** TensorFlow？  
答：生产路径用 sklearn；深度学习不是这套日频账户的瓶颈。

---

## JD-4 实盘监控与迭代

**你有的：** 影子盘、风控门、光刻胶日终监控、journal 幂等。没有券商 OMS 真单。

**30 秒：**  
`live/run_shadow.py`：信号 → 订单 → `RiskGate` → `paper_broker.execute_orders`，同一份订单贯穿。冻结里 384 个调仓日，WARN 184、BLOCK 200，说明门在拦，不是 n_warn=0。光刻胶在 `live/photoresist_panic/`：日终更新、质量门、journal 重启不重复写。

**必打开：** `live/risk_gate.py` 的 `check()` 列表；`live/photoresist_panic/journal.py`。

**会问：** 怎么根据风格调参？  
答：研究侧用冻结样本，不按情绪改规则。风格只做暴露和归因。盘中调参是投顾岗日常，不是我这套研究纪律。

---

## JD-5 经纪赋能

**你没有代码。** 准备的是翻译能力，不是假装做过沙龙。

**30 秒：**  
我没有给分公司做投顾培训。我能把研究结果翻译成配置语言：例如「中证1000 低波回测中位超额为正，但涨跌停数据覆盖不足 20%，不能对客户说这是可配置产品。」这正是合规投研该说的话。

**会问：** 产品推荐模型？  
答：仓库里没有。若需要，应在过了数据门的冻结身份上再做，而不是对失败回测拟合推荐分。

---

## JD-6 风控合规

**你有的：** 组合约束 + 操作门。没有监管报送系统。

**30 秒：**  
策略内：单票上限、行业偏离、换手帽、订单金额、数据缺失熔断（`live/risk_gate.py`）。账户内：未知涨跌停不可买、未成交留现金、费用必须有现金。操作上：迟到数据、重复信号、账实不符会 BLOCK。

**数字：** 未知涨跌停权重 300/500/1000 ≈ 32% / 59% / 84% —— 所以冻结全部 DATA_INSUFFICIENT。

**会问：** 合规？  
答：这是研究账户纪律，不是法律合规系统。券商合规要对接监控指标和销售适当性，那是入职后和合规部对齐的。

---

## 任职要求对照

| 要求 | 准备 |
|---|---|
| Python/Pandas/Numpy | 整库；现场可讲 `weekly_long.mark_holdings` |
| TensorFlow | 说 sklearn，不装懂 |
| 独立回测 | `products/` + `backtest/`，不是聚宽 |
| 数据库 | Parquet 分区 + DuckDB/PyArrow 扫描 |
| A 股规则 | T+1、整手、停牌、涨跌停、印花税只在卖出 |
| 3 年全流程 | 用本项目讲「研发-回测-影子-否定」；年限用真实工作经历补 |
| 高频/ETF 日内实盘 | 没有；主动说优先项不是我的主线 |

---

## 现场演示顺序（投屏 8 分钟）

1. `DECISION.md` 分类表（先结论）  
2. `products/weekly_long.py`：`hold_windows` + `mark_holdings` + 成交日 `post_trade` 权重  
3. `data/tradable.py`：限额 NaN / 缺行 → 不可买  
4. `products/metrics.py`：`go_reason` 分 PASS / NO_ALPHA / DATA_INSUFFICIENT  
5. 停。问面试官想看因子还是风控。

不要现场跑 2017–2024。

---

## 简历上可写的句子（对应 JD 用语）

- 独立搭建 A 股日频研究与回测：PIT 成分、T+1、涨跌停、成本与现金账户。  
- 建立冻结实验与数据门：将「经济失败」与「数据不足」分列，避免错误淘汰或错误上线。  
- 实现影子盘链路：信号-订单-风控-纸面成交，支持迟到数据与重复信号阻断。  

不要写：年化超额 X%；实盘盈利；TensorFlow 深度学习选股。

# 核心模块精读：从输入到应聘表达

所有路径相对仓库根目录。公式解释绑定下列具体实现；配置中的描述、函数注释、当前源码和冻结历史运行可能不同。重点差异另见 02_implementation_caveats.md。

## 1. 全流程与运行身份

入口 run_research.py 提供 phase0–phase5、smoke、all。README 对应：数据、因子与评价、MVP 回测、组合优化、ML、稳健性。先定位各 phase 函数，再追实际使用的构造函数和 kwargs。STRATEGY_PARAM_KEYS 统一部分换手与优化参数的传递，但不代表所有阶段都启用相同策略。

学会区分四种对象：

- 因子值：某股在某时点的特征。
- score：多特征合成后的排序分数。
- target_weights：希望持有的权重。
- executed_weights / fills：在该引擎假设和约束下形成的权重或成交。

反例：top50 的分数排序没有错，不代表涨停股票能买进；优化目标满足上限，不代表费用扣除后和价格漂移后权重仍满足同一上限。

阅读：run_research.py 的 _build_backtester、_strategy_kwargs_from_args、各 phase；configs/factors.yaml 的模式说明。训练要求：任选一个 phase，写出实际调用的五个函数，而不是只画目录图。

## 2. 数据管线、主键、单位和 PIT

入口：data/tushare_client.py、parquet_cache.py、panel_loader.py、calendar.py、universe.py、industry.py、adjust.py、tradable.py。

### 2.1 数据表该怎样认识

| 数据 | 常见键与时间 | 用途 | 学习时必须追踪 |
|---|---|---|---|
| raw OHLC、vol、amount | ts_code + trade_date | 成交参照、限价、量价 | 原始价格；本项目接口量纲 vol 为手、amount 为千元 |
| adj_factor 与 adj OHLC | ts_code + trade_date | 连续价格研究 | 复权因子覆盖和公司行动假设 |
| index_weight | 指数 + 快照日 + 股票 | 当时投资域/基准 | 快照日与 available_date |
| stock_basic、namechange | 股票与状态生效区间 | 上市、退市、ST | 不能仅用当前状态回填历史 |
| fina_indicator | 股票、ann_date、end_date | 财务因子 | 公告时间、报告期、修订版本 |
| trade_cal | 市场、日期、开市标记 | 时钟 | 交易日偏移不能用 YYYYMMDD 相减 |
| limits、suspend | 股票与日期/期间 | 可交易性 | 缺失不是“无涨跌停/未停牌” |
| 因子长表 | ts_code + trade_date + factor | 分析/模型 | 唯一性、覆盖、处理版本 |

ParquetCache 要读主键去重、分区合并、原子替换、锁及按股票检查覆盖；PanelLoader 要读 DuckDB/PyArrow 的日期和代码过滤、分块读写、宽表转换。数据库技能应从查询和数据组织说明，不能凭 requirements 中出现数据库包就宣称维护过生产数据库。

### 2.2 PIT 的三个不同问题

1. 股票何时属于可投资集合？universe.build_available_constituents 将快照按可用滞后映射，再由 pit_constituents_asof 选择 date 以前最近快照。
2. 财务值当时公布了吗？fundamental.compute_financial_factors 使用 ann_date <= signal_date，不能用报告期 end_date 当公布日。
3. 因子标签的未来收益形成了吗？这不是成分 PIT 能解决的，见第 4 节。

精度边界：日级 ann_date 不说明盘中几点公布；月度指数快照加一交易日也只是本项目可用性假设，不等于官方所有历史调整生效时点已被逐条还原。

### 2.3 复权与原始价格

PriceAdjuster 中 adj_price = raw_price × adj_factor。因子连续收益可用相同复权坐标，交易金额和交易所价格限制需要相应原始价格坐标。

例：除权前 20 元、因子 1；除权后 10 元、因子 2。复权价格均为 20，不应把原始价格下降 50% 当策略亏损。真实股数与权益变化还需要公司行动账户，不能只靠连续复权价格替代。

当前 adjust.py 的缺复权因子小比例分支会填 1；strict=True 不等于“任何缺失都报错”。具体问题见差异清单。

### 2.4 数据质量不是一个覆盖百分比

要分别检查股票覆盖、日期覆盖、内部缺口、因子覆盖、成交日限额覆盖和持仓权重覆盖。一只权重大且必须卖出的股票缺价，与许多不在投资域内的股票缺价，后果不同。

测试入口：test_pit_product_universe.py、test_index_weight_completeness.py、test_per_code_coverage.py、test_price_interior_gaps.py、test_adj_factor_cache_strict.py、test_tradable_limit_rules.py。

完成标准：解释“今日成分回填历史”“公告日与报告期混淆”“只验区间起止不验内部缺口”各会造成什么错误。

## 3. 因子构造与截面处理

入口：factors/technical.py、fundamental.py、cross_section.py、factor_panel.py。

### 3.1 必须会写出的实际公式

反转：rev_w(t) = -(P_t/P_(t-w)-1)。下跌越大，反转值越大；这是信号方向，不是已证明的 Alpha。

跳近期动量：mom_(w,s)(t) = P_(t-s)/P_(t-w-s)-1。代码注册 momentum_60 为 w=60、s=20，即 P_(t-20)/P_(t-80)-1，不能照 YAML 文字背成另一种窗口。

波动率：log_return_t = log(P_t/P_(t-1))，vol_w = rolling_std(log_return,w)，这里没有年化。sign=-1 意味着偏好低波；还要追 sign 在调用链何处应用，避免重复取负。

EP/BP：当前 daily_basic 路径对正 PE/PB 求倒数，非正值填 NaN。负盈利股票因此可能落入缺失处理，不能忽略由此造成的投资域差异。

财务字段：ROE、grossprofit_margin、netprofit_yoy、debt_to_assets 在当前计算器中的映射分别需要确认；函数 docstring 提到某因子不代表该函数确实生成它。

### 3.2 截面流程及原因

_process_single_date 的顺序：选择当日投资域 → 去极值 → 缺失处理 → 中性化 → 标准化。

MAD 去极值：m=median(x)，MAD=median(|x-m|)，按 m±k·MAD 截断。当前没有在此公式上额外乘 1.4826。MAD=0 时返回原序列。

中性化：用常数项、行业哑变量、log_market_cap 拟合 x，残差 e=x-Xβ 作为新因子。目的是研究扣除指定暴露后的截面信息，不等于账户行业中性或市场中性。

z-score：(e-mean(e))/std(e)，代码用 ddof=0。rank 模式返回百分位秩，不是同一尺度的 z-score。

重点：只有行业数据满足 has_pit_data 才进入行业项；没有可用解释变量、股票数不足或回归失败时可能返回原序列。因此须检查实际执行路径，不能只说“配置要求行业市值中性，所以已中性”。

测试入口：test_factor_alignment.py、test_factor_quality_rebuild.py、test_alpha_factors_v4.py、test_growth_factor_pit_dedup_v4_r2.py。

## 4. 标签、IC、因子组合和收益校准

入口：eval/cs_evaluator.py、alpha/time_utils.py、ic_weighting.py、factor_alignment.py、factor_gating.py、score_to_mu.py。

### 4.1 因子评价不等于账户评价

Rank IC_t = corr(rank(factor_i,t), rank(forward_return_i,t))，在同一截面上计算。compute_daily_ic 同时输出 Pearson 与 Spearman 相关、对应 p 值和样本数。

ic_summary 的 ICIR=mean(IC)/std(IC)，未年化，std 用 ddof=0。其 t_stat=mean(IC)/(std(IC)/sqrt(n)) 是代码里的简单统计量；不要把它直接当作考虑了多日重叠、自相关、多重试验的稳健显著性结论。

IC 正仍可能净收益差：最高分股票成交受阻、持仓约束、费用、价格坐标或持有期不同、基准暴露不同。分层收益也不自动对应某个可交易多空账户。

### 4.2 标签什么时候才可用

matured_ic_cutoff 要求 T+h < signal_date。以交易日下标表示：当前是 d10，h=5，最多使用 d4 的标签，因为它到 d9 形成；d5 的标签到 d10，按本实现严格不纳入。

三个边界不能混淆：特征在 T 可见、标签在 T+h 形成、用该标签更新权重发生在之后。把所有历史 IC 预先算好并不违规；在任一决策点使用尚未成熟的 IC 才是问题。

### 4.3 组合因子与模型输入

ICWeighting.compute_weights 先拿真实日历成熟边界，再筛 lookback 与最低观察数，只对 eligible factors 归一化。因子上限、负 IC 处理和不足因子回退要继续读该函数后半段及 _apply_hard_cap。

ScoreToMu 的 rolling_ic 分支：μ_i = score_i × rolling_IC × rolling_cross_section_return_vol。当前时点先从成熟历史计算 μ，再把当前 IC 记录给未来使用。少于 5 条成熟历史时 μ 为 0。

μ 与 Σ 的预测期限、风险厌恶系数尺度要在具体调用路径核对，不能看到公式维度相容就默认持有期一致。

测试入口：test_score_to_mu_no_leakage.py、test_ic_weighting_single_factor.py、test_factor_gating_dynamic.py。关键反例：改变未来标签不应改变过去权重；改变已经成熟的历史标签可以改变后续决策。

## 5. 机器学习与市场状态

入口：alpha/ml_alpha.py、regime_detector.py、strategy_sleeves.py、regime_allocator.py、regime_composite.py、validation/walk_forward.py。

### 5.1 ML 的实际链路

prepare_data 以内连接合并因子长表，样本键是 (trade_date,ts_code)，从 fwd_ret_hd 直接取 y。上游是否已经对标签做了排名或中性化需要另查；本函数没有自动做这些变换。

SUPPORTED_MODELS 是 random_forest 和 gradient_boosting。walk_forward_train 从 dates[0] 起扩展训练，按 n_retrain 重训，以 embargo_days 分隔；训练和测试调用 prepare_data。重要差异：purge_days 属性没有在该函数中用于删除重叠样本。

fold 内 test_ic 计算方式是把该 fold 的 y_test 与 y_pred_test 放一起求 Spearman，不能自动等同于“每日截面 Rank IC 的时间均值”。

面试回答模型选择时，要能说出输入、标签、时间切分、简单基线、过拟合风险和经济检验，不要只背树模型名称。

### 5.2 regime 是另一层研究假设

通用链路：市场特征 → 状态分数/概率 → 各策略 sleeve 权重 → sleeve 内股票评分 → 综合股票评分。先读所用 config，确认有哪些 sleeve、基础权重、上下限和平滑规则。

不要与 sector_panic/regime.py 混淆：后者区分市场尾部冲击、板块残差尾部冲击以及趋势状态；滚动 beta 与阈值使用过去数据。状态识别本身不是交易收益证据。

关键追问：如果因子本身没有信息，状态分配能凭空创造 Alpha 吗？不能据此推定；必须比较固定权重基线、状态分配与额外换手成本。

测试入口：test_regime_no_leakage.py、test_regime_allocator.py、test_regime_realistic_alignment_gate.py。历史结论入口 docs/strategy_family_go_nogo.md，不能混用不同 candidate 的成绩。

## 6. 组合优化与风险

入口：portfolio/optimizer.py、constraints.py、cov_estimator.py、optimized_weighting.py、risk.py。

基础目标：max μᵀw - (λ/2)wᵀΣw - γ||w-w_prev||₁。分别对应预期收益、方差风险和交易惩罚。cost-aware 参数还需要追上层入口，不能在基础公式中假装所有成本都已精确建模。

基础约束实现：权重和等于 leverage；long_only；单票上下限；不可交易股票冻结；半 L1 换手约束；行业偏离约束。

两个必须会推导的例子：

- 50 只、单票上限 2%、满仓，全部必须为 2%，优化几乎没有权重自由度。
- 30 只、单票上限 2%、满仓，最大总权重 60%，问题不可行，不能靠换求解器解决。

行业约束实际是 0.5×sum_g |industry_weight_g-benchmark_g| <= cap，而非每个行业各自偏离不超过 cap。持仓数量 min/max 在基础 QP 里没有作为精确基数约束实现，stock_deviation_max 属性也不能仅凭存在就认定生效。

协方差要学习宽表对齐、缺失、最低观察数、收缩与 PSD。当前 cov_estimator._ledoit_wolf 是含简化强度估计的实现，不应直接宣称等同标准库估计器。

优化失败的诊断：数据不足、资产数和上限不相容、冻结仓位导致不可行、数值问题、求解器问题；fallback 不应和成功优化混为一类。追 optimized_weighting 的 check_feasibility、solve_with_retries、relax_constraints_tiered、build_fallback_weights。

测试入口：test_optimizer_relaxation.py、test_benchmark_optimizer_pipeline.py、test_cost_aware_objective.py、test_turnover_controls.py。

## 7. 日频执行、费用、现金与净值

入口：backtest/execution.py、cost_model.py、portfolio_backtester.py；产品链路另看 products/weekly_long.py、metrics.py。

### 7.1 执行如何改变目标

execute_rebalance：并集对齐新旧标的 → 检查价格 → 对不可买/卖方向冻结 → 可交易目标只向下缩减预算、不向上补满 → 缩减买入预留费用 → 输出权重、费用、换手与现金。

缺价旧仓保留，缺价新买不买。未成交预算留现金，不能自动分给剩余股票。注意 mask 传入缺项时的默认值与上游完整性；本函数并非独立完备的实盘订单系统。

### 7.2 两条成本路径分开

通用 CostConfig 的默认值包括佣金率 0.00025、最低 5 元、卖出印花税 0.0005、过户费 0.00002、固定滑点 5bp。这些是当前代码参数，不是本材料对现实最新或全部历史法定费率的声明。要说“该次运行使用的费用假设”，并核对实际 config。

P1 事件共享账户是单边 0.005 的冻结比例费率，不能套用上述费率与最低佣金。

交易成本中整手取整并不自动保证 executed_weights 是由同一套真实整手成交反推的；当前基础权重路径有这一区别。t1_sell_restriction 也不能只看构造参数名，须看是否追踪每笔买入日期。

### 7.3 持有期间的收益与权重

若旧股票权重为 w_i，现金权重 c，区间股票收益 r_i，则账户增长倍数 G=c+Σw_i(1+r_i)，新权重为 w_i(1+r_i)/G。现金也要按 G 重标。

例：A/B 各 50%，A 翻倍、B 不变，净值从 1 到 1.5，权重变为 2/3 和 1/3。重新等权的股票半 L1 换手为 1/6。

products.mark_holdings 缺末价时沿用最后有效估值并记录缺口；复牌或补回有效价格后补记从最后有效价以来的收益。不能把每个缺价期间都永久记成零收益。

apply_cost_from_cash 从现金支付费用，不暗中削减股票；费用不够有 shortfall 状态。产品层把这类预算失败与部分数据失败共同记 DATA_INSUFFICIENT，解释时要拆开原因。

### 7.4 收益指标必须带口径

累计收益=V_end/V_start-1；最大回撤=min(V_t/running_max(V)-1)。P1 年化按自然日差：增长倍数^(365.25/elapsed_days)-1。

products 的 IR 用账户与基准收益差的均值/标准差，再乘 sqrt(实际年观察频数)。周频净值不能无条件乘 sqrt(252)。产品年度中位超额是各年策略收益减各年基准收益后的中位数，不是账户 CAGR，也不是净值之比的 CAGR。

测试入口：test_execution_missing_prices.py、test_weekly_long_holding.py、test_products_metrics.py、test_backtester_end_boundary.py。

## 8. 板块恐慌、事件聚类与修复确认

入口：sector_panic/backtest.py 的 build_signal_frame、cluster_first_triggers；component_repair_confirmation.py；冻结运行的源清单与 R7 面板。

### 8.1 恐慌不是单一“跌了 5%”

build_signal_frame 的实际 gate：板块窗口收益为负，且满足“绝对跌幅阈值或历史分位阈值”，同时满足下跌宽度。历史分位使用窗口收益 shift(1) 后滚动计算；下跌宽度是代码里的日下跌比例的窗口均值。

有色配置给出 5 日窗口、750 日分位窗、10% 分位、50% 下跌宽度等值；但这是特定配置，不能当全库唯一参数。旧配置 gate_type 字样不能替代阅读布尔表达式；P1 候选来源绑定冻结面板，不能拿当前脚本随意重造事件并混进同一评价。

聚类用于减少同轮连续信号重复计数，但“一个事件”仍不保证独立于其他板块同日事件。

### 8.2 修复确认的状态与信息时点

RepairConfirmationPolicy 默认冷却至少 2 个交易日、不创新低至少 2 日、观察窗口 10 日、突破后至少保持 1 日。追踪的状态包括 COOLDOWN、SELLING_PRESSURE_OFF、HIGHER_LOW_FORMED、REPAIR_BREAK、REPAIR_HELD。

逐日处理：缺失行情记数据失败；停牌不推进有效价格观察状态；创新低重置低点、higher low 和突破状态；形成更高低点后识别修复突破，再检查保持情况。AVWAP 累计 numerator+=daily_vwap×volume、denominator+=volume；必须保证价格坐标一致。

d0 是实际修复确认日，不是原始恐慌信号日。旧 E2 修复模块的 entry_lag 与 rebuild 的更晚复核/成交时钟要分开。P1 的真实输入适配层从冻结源证明确认快照，不是把旧成交清单直接当新买入指令。

测试入口：test_component_repair_confirmation.py、tests/sector_panic_rebuild/test_data_guard.py、test_e2_risk_inputs.py、test_contracts_and_governance.py。

## 9. 因果入场、代理撮合与退出

入口：sector_panic/rebuild/entry_policy.py、contracts.py、execution.py、risk_policy.py、event_engine.py。

### 9.1 入场公式与时钟

A_t=max(repair_level, signal_AVWAP_t)；扩展宽度 δ=min(0.08,1.0×NATR20)；买价上限 L_t=A_t(1+δ)。

默认确认价门：复核收盘高于确认收盘 C，且不低于 A_t，不高于 L_t，结构健康，输入有效。确认价不抬高上限。

d0+1 最早复核；当晚提交指向下一交易日，d0+2 最早成交；最后目标日 d0+5。偏移按交易日历，不按自然日。

数量在提交时按预算与限价冻结：q=B/[L(1+c_buy)]。次日更便宜成交时 q 不增加，余款留现金。

### 9.2 决策与撮合为何必须分开

次日价格可以判断前一晚订单是否成交，但不能反过来修改前一晚是否下单。提交后次日跌破确认价，只要仍满足撮合条件，应承担该成交路径，不能事后过滤亏损买入。

DAILY_CLOSE_PROXY：有有效价格和状态、方向未受阻、价格满足订单限价时按日收盘代理成交。它没有证明排队、盘口容量、实际集合竞价或券商回执。

### 9.3 止损、结构与义务

止损距离 d=max(0.05,2.5×信号日NATR20)，有效范围 (0,1)。绝对止损价在成交后为 P_fill(1-d)。这是收盘触发退出意图的规则，不保证成交价格恰好等于止损线。

结构破坏：跌破 higher_low；或跌破 panic_low；或同时跌破 repair_level 与 signal_AVWAP。双锚点分支是 AND。已有一个确定破坏可返回 broken；未确定破坏但必要输入缺失则 unknown，不能当 healthy。

退出排序口径要读完整函数：有工作卖单先保留既有意图；否则 STOP 优先；已有锁存意图保留；其后 NEW_EVENT、STRUCTURAL_FAILURE、MAX_HOLD_20D。简写优先级不能抹掉“已提交订单”和“已锁存意图”的条件。

卖出受阻继续保留持仓与退出义务。截止日无下一交易日时不虚构卖出，不把未完成路径当作收益为零的未入场。

测试入口：tests/sector_panic_rebuild/test_causal_orders.py、test_lifecycle_resume.py、test_execution_adapter.py、test_rebuild_review_regressions.py。

## 10. P1 共享资金账本

入口：portfolio_book.py、portfolio_driver.py、portfolio_full214_real.py；configs/sector_panic/portfolio_economic_contract_v1.yaml。

冻结关键规则：初始资金 1 研究单位，无外部入金/借款/现金利息；每单预算 0.05 初始资金，含买入费；最多 20 个名称槽位；同名有持仓或工作买单则不重复买；不做不足预算的比例配给。申请按 signal_date、sector、event_id、ts_code 排序，不按未来收益排序。

0.05 是固定初始资金预算，不是当前 NAV 的动态 5% 上限。P1 没有启用草稿中的策略 10%、行业 4%、单名 0.5% 母账户上限，也没有启用行业持仓上限。

三条恒等式：

- available_cash = total_cash - buy_reserve。
- NAV = total_cash + marked_position_value。
- buy_reserve 已包含在 total_cash 内，不能再次从 NAV 扣除。

当天顺序：新事件到达 → 卖单撮合 → 买单撮合 → 过期买单释放预留 → 持仓风险检查 → 卖出重试 → 当晚新申请 → 成功后日估值。

关键路径：

- 买入成交：扣实际含费支出，释放全部该单预留；固定数量进入持仓。
- 买入未成交到期：只释放预留，不扣实际交易费用。
- 卖出受阻：订单到期可重试，退出意图仍在，名称槽位不释放。
- 无解释的缺行情：驱动层恢复当日开始前检查点，留下失败诊断，不继续形成可用净值。
- 截止日未完成：保留工作订单和未排期退出义务，不强行造一笔清仓。

portfolio_driver.py 的类文档和合成限制不能用来断言整个 P1 没有真实历史回放。portfolio_full214_real.py 是另一个适配运行入口，要连同其源绑定和归档读取。

测试入口：test_portfolio_p1_book.py、test_portfolio_p1_driver.py、test_portfolio_p1_full214_audit.py、test_cash_reconciliation.py。

## 11. 验证、收益归因、亏损诊断和研究取舍

### 11.1 四类证据分别回答不同问题

工程：是否按照规则产生订单和正确记账？回放：预定候选是否完整处理？覆盖：受阻退出等关键真实路径出现过吗？经济：在指定账户和成本下是否值得继续研究？

E2 audit v4：工程 PASS、回放 COMPLETE，但真实 suspension_retry 缺覆盖，coverage 仍不足。后续 P1 做了经济描述不等于 E2 每个门自动升级。

未来信息测试的正确思路：改变未来数据，比较历史订单或权重是否不变。变异测试反过来故意注入“用未来信息、重复扣费、删掉应有订单”等错误，检查测试/审计能否抓住。

### 11.2 独立事件收益与账户收益

一个事件有正收益不代表共享账户同时有钱买入。事件平均、逐笔算术平均、组合累计、组合年化各有不同分母。214 事件、2140 候选键、281 成交交易、562 买卖成交腿、2141 交易日不能互换。

### 11.3 最新 P1 描述性结果

源：docs/sector_panic_p1_minimal_economic_review_20260924.md 与 p1_loss_diagnostic_v1_run03/report.md。

2017-04-18 至 2026-02-04：累计 +0.499383%，年化 +0.056626%，最大回撤 -10.894549%，平均收盘股票仓位 5.878501%。89 笔净盈利、192 笔净亏损。

固定成交毛利润 0.141215884749，费用 0.136222056432，净利润 0.004993828317，初始资金为 1。费用/毛利润约 96.46%。这是固定成交会计归因，不能当换费率后重新运行策略的结果。

亏损分类：182 笔毛亏损、10 笔费用转亏。另一个正交维度：125 笔从未出现正的估算净收盘收益，67 笔曾有正值后净亏损。不能将两套分类相加。路径浮盈不是当时可实现退出价格。

整个区间 RESEARCH_USED；基准未绑定；没有新的独立 OOS 结论；经济状态 INSUFFICIENT_EVIDENCE。停止推进当前独立账户版本是资源取舍，不证明所有未来市场都不可能有效。

### 11.4 归因与 benchmark

products/return_attribution.py 提供 Brinson、滞后 beta 残差和覆盖检查等入口。学习时分别追组合/基准行业权重、行业收益、交互项、原始权重覆盖；权重与收益区间必须一致。归因中的 residual 不是已可交易的套利组合。

## 12. 影子执行与监控

入口：live/signal_service.py → order_builder.py → risk_gate.py → paper_broker.py；run_shadow.py 与 gated_execution.py；另看 live/photoresist_panic/runner.py、state_machine.py、journal.py。

RiskGate 八类检查：单票权重、行业暴露、换手、订单金额、数据新鲜度、缺失数据、重复信号、book 与 inventory。任一 BLOCK 则总体 BLOCK，否则按 WARN/PASS 汇总。

run_gated_step 在 BLOCK 时不发送订单、返回原 book/cash；放行后将同一份经过检查的 orders 交给 broker。风控检查完又重造一份订单，会使检查与执行对象不一致。

PaperBroker 对有效开盘价格假定全量成交；slippage 按买卖方向调整，HIGH_SLIPPAGE 是对模拟成交的标记。notional_cny 是成交金额，旧别名 cost_cny 在这里不是手续费。

光刻胶状态机：IDLE 首触发进入 ACTIVE，默认最多 20 个交易日；之后 COOLDOWN，需要连续 5 个不触发交易日重新武装；重复日期不推进状态也不重复通知。区分逻辑幂等、文件原子替换、跨文件事务和外部通知重试，它们不是一回事，进一步读 journal/runner 对应测试。

测试入口：test_ops_fault_injection.py、test_shadow_execution_failure.py、test_paper_broker_summary.py、test_photoresist_live_state_machine.py、test_photoresist_live_runner_transactions.py、test_photoresist_live_notifications.py。

## 13. JD 中项目尚不能充分覆盖的内容

算法交易：当前 amount×10/vol 是日级 VWAP 估计，exec/vwap-1 是价格比较，AVWAP 是策略锚点；这些不构成分时 VWAP/TWAP/IS 执行算法。需要的补充知识应列清母单/子单、时间与成交量分配、到达价格、未完成量、方向、冲击及执行风险；没有数据和实现的部分如实说明。

ETF：先熟悉 products 的 ETF 价格、信号、调仓、费用与基准口径。指数不是可直接成交的 ETF；历史 ETF 投资域、上市日、成交规模、溢折价等是独立问题。股票上的成本和交易限制不可不加核验地复制到所有 ETF。实际交易规则要结合拟研究品种另行核实。

套利：市场中性需要明确多空腿、对冲比率、融资融券/工具、基差与执行风险；当前归因或统计相关不构成可交易套利 book。

业务表达：用“研究什么机会、怎样用资金、什么情形失效、当前证据到哪一步”解释项目。准备研究交流样稿，不虚构真实客户配置、培训或销售业绩。

合规：RiskGate 是研究与操作风险控制组件，不能代表适当性、权限、监管报送及完整券商合规体系。

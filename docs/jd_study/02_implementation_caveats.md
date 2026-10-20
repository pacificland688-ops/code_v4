# 实现差异与追问风险

日期：2026-09-25。以下为当前工作区源码静态核查发现，不代表已确认所有冻结历史运行受到影响。未在本次修改实现；历史影响需要绑定当时源码、配置和调用路径单独验证。

“熟悉项目”包括知道它未做什么、哪些注释不准确，不能把以下条目背成已修复能力。

| 编号 | 实际观察 | 面试中准确的说法与下一步定位 |
|---|---|---|
| C01 | technical._compute_momentum 取 P_(t-s)/P_(t-w-s)-1；YAML 的 momentum_60 文字公式不同 | 使用注册表的 w=60,s=20 解释当前公式；冻结因子产物须另查生成版本 |
| C02 | technical._compute_ivol 中 _rolling_corr 返回相关系数，beta=cov 实际赋的是相关；var_mkt 计算后未用 | 不能称该函数为正确的滚动 OLS 特质波动率；还需查注册与运行是否使用，不能推定所有因子结果失效 |
| C03 | adjust.compute_adj_prices 在缺因子比例未超过阈值时填 1，即使 strict=True；adj_pre_close 用当日因子近似 | 不宣称全链路对任何缺因子都严格报错，也不宣称完整公司行动账户 |
| C04 | universe.build_available_constituents 日历不可用时退回自然日加法 | 通用工具存在降级分支；正式运行应核对日历证据，不能声称无日历绝不生成可用日 |
| C05 | fundamental.compute_financial_factors 取公告日前最后记录，并按自然周五生成信号日期 | 必须检查修订/报告期冲突、交易日对齐和调用脚本；不能用该函数存在证明所有 PIT 问题解决 |
| C06 | cross_section._neutralize 在解释变量或样本不足、异常时可能返回原值 | “支持中性化”与“本次实际完成行业+市值中性化”分开 |
| C07 | ml_alpha.purge_days 仅构造保存，walk_forward_train 未用；实际是扩展训练+embargo 间隔 | 不背注释为完整 purge+embargo；是否有泄漏须看标签跨度与实际日期间隔 |
| C08 | ml_alpha.prepare_data 直接读 fwd_ret；walk_forward_train 的 fold IC 是合并样本相关 | 不称其自动做了标签截面排名，也不把 fold IC 当每日 IC 均值 |
| C09 | validation.walk_forward.generate_splits 中 d < test_start - purge_days 对 YYYYMMDD 整数减法；run 重构训练区间并未传递过滤后的 train_dates | 这是独立验证器的实现风险；不能由当前函数注释宣称严格标签重叠清除 |
| C10 | constraints 的 industry_deviation_max 是行业权重偏离的半 L1 总和；基数约束被跳过，stock_deviation_max 未在 build_constraints 使用 | 不说“每行业各 5%”“严格持仓 30–100”“单票相对基准约束全部已执行” |
| C11 | cov_estimator._ledoit_wolf 自写简化强度；optimized_weighting 可能另有协方差路径 | 按具体入口解释；不把函数名字当标准算法一致性证据 |
| C12 | ExecutionSimulator.t1_sell_restriction 仅保存；execute_rebalance 无逐笔持仓买入日期 | 周频信号延后成交，与普遍正确的可卖股份 T+1 管理不同 |
| C13 | compute_turnover_cost 取整股数计算费用，execute_rebalance 返回的权重未由这套取整股数反推 | 基础权重模拟不能宣称已完成严格整手现金股数核算；P1 又是归一化份额 |
| C14 | execute_rebalance 对传入 can_buy/can_sell 的缺索引填 True；上游 TradableMask 对未知限额是双向阻断 | 需证明上游 mask 对订单全集完整；“未知不可买”不能脱离调用条件解释 |
| C15 | cost_model 返回 one_way_turnover 累加 abs(dw)，execution 的 turnover 则除以 2 | 名称相同不代表同口径；写报告必须指明读哪个字段，初次建仓还涉及现金腿 |
| C16 | products.weekly_long 的 adv20 当前滚动含当日 amount；选用成交量相关滑点时须核对信息可用时点 | 事后成本代理与事前下单可得量不能混称，本次未评估所有运行影响 |
| C17 | products.metrics 把缺价、未知限额过多、费用现金不足共同归为 DATA_INSUFFICIENT | 面试说明具体原因；费用预留失败不等于市场数据缺失 |
| C18 | daily_vwap_from_raw 是日汇总价格估计；implementation_shortfall 返回 exec/vwap-1 | 当前代码不提供完整 IS 执行策略；卖出评价方向等也不能从函数名推断 |
| C19 | P1 固定每单预算 0.05、20 名称槽位、行业上限禁用；旧 scope 的母账户上限属于另一个未执行设计 | 不把草稿策略/行业/单名上限加到 P1 结果上 |
| C20 | risk_policy.primary_exit_reason 先处理 working_sell 和 existing_intent | 优先级 STOP→NEW_EVENT→结构→最长持有只是简写，需补订单及锁存条件 |
| C21 | PaperBroker 有有效价格时假定满额成交，cost_cny 为成交额旧别名 | 不能称真实成交率验证；不能把该字段加总为手续费 |
| C22 | 当前默认 Python 的 SciPy 导入提示要求 NumPy>=2，而环境为 NumPy1.26.4；requirements 又约束 NumPy<2 | 现场环境未准备好；不能通过盲目全局升级解决，也不应使用错误测试结果背书 |

## 怎样继续核对一项差异

1. 找调用者：rg 搜索函数名、参数名，区分测试和生产/研究脚本。
2. 找运行 manifest：确认该次运行绑定的源码和 config，而非用当前工作区猜历史。
3. 写最小反例：说明预期与实际差异；不改原冻结产物。
4. 找已有关联测试：是否只测注释描述以外的部分，还是确实能抓住这个错误？
5. 评估对本次应聘陈述的影响，明确“支持”“实际使用”“通过验证”三层证据。

## 已需要纠正的旧面试话术

- “完整实现了整手、T+1 真实账户”：改为按引擎分别说明权重模拟、纸面股数与 P1 研究份额。
- “ML 已完整防泄漏”：改为说明成熟标签门已经在哪些路径实现，哪些验证器仍有差异。
- “P1 只有独立事件账本”：后续已有共享资金回放，使用 9 月 24 日评价。
- “未知涨跌停仍是 32%/59%/84%”：这是旧版本数字；完整池 r8 已不同，但仍 DATA_INSUFFICIENT。
- “2024–2025 是锁定样本外”：后续使用记录把相关历史标为 RESEARCH_USED，不能恢复为干净 OOS。
- “部门要求什么我们就已经做了什么”：JD 的 ETF、AI 执行算法与真实实盘优先项，当前作品不能替代。

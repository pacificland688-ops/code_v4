# 快照政策 v0.1：时点、单位、修订与授权

2026-10-16。本文件是工程操作定义，状态为 PROPOSED_ENGINEERING_SPEC。它不冻结研究参数，不把 `freeze_timestamp` 写成非空，也不打开收益。策略参数继续保持 PROPOSED。1% 限价、EMA50 重置和 10 日研究期限不在本文件调整。

研究市场定义仍是历史时点沪深 300、日线、多头。正式样本仍是 2015-01-05 起预热、2018-01-01 至 2018-03-30 输出。合成案例可以使用更小的已声明范围，但必须同时写下父合同哈希和实际工程合同哈希。短数据本身不能缩短默认合同。

旧的日期型公告政策 ID 是 `DATE_ONLY_ANNOUNCEMENT_ASIA_SHANGHAI_END_OF_DAY`，状态保持 `PROPOSED_NOT_APPLIED`。来源定义不能把它改成已启用。只有日期的公告、`trade_date`、文件修改时间、下载时间和审核时间都不是历史 `available_at`。

## 模式与授权

`mode` 只允许 `SYNTHETIC` 或 `REAL`。命令、来源定义、审核件和快照四处必须相同。

合成审核件的 `review_kind` 只能是 `SYNTHETIC_DECLARATION`。它绑定案例编号和手工预期，不称为 `REAL_CERTIFIED`。`reviewed_at` 只表示审核或声明时间。

REAL 批准只来自项目固定文件 `momentum_pullback/evidence/approved_source_reviews.json`。输入包里的同名文件无效。本批该索引的 `entries` 必须为空。文件自称 `VERIFIED`、`PASS` 或 `real_events_permitted=true`，都不能授予 REAL 权限，也不能产生 `DATA_READY_FOR_ENGINEERING`。

哈希方向是：原始文件、证据和政策，再到 `source_manifest`，再到 `source_review_receipt`，再到以后的 `snapshot_manifest`。审核件不反向引用快照清单，也不把自身哈希写进被自身哈希的载荷。

## 信号时点与修订

沿用输入里显式带时区的 `signal_cutoff`。每个证券日期使用同一时刻，每个横截面只有一个截止时刻。合成手工案例使用 `18:00:00+08:00`。这个时刻不是供应商的真实发布时间。

只有 `available_at<=signal_cutoff` 的记录可以成为当天的已知值。晚于截止的记录可以留在审计来源里，但不能进入当天的选择结果。`available_at` 与生效日期分开判断。派生字段的可用时点取必要源事实可用时点的最大值；任一必要时间未知，派生字段仍未知。审核时间不参与这个最大值。

合法主键包含已声明的 `revision_id`。同一主键的完全相同记录和字段冲突记录都报 `DUPLICATE_OR_CONFLICTING_KEYS`。不同修订不是重复行。在截止时已可用的修订中，按来源定义声明的顺序取最大值，规则名是 `MAXIMUM_DECLARED_ORDER`。顺序键并列时报 `AMBIGUOUS_ASOF_REVISION`，不能按文件顺序或保留最后一条。对历史观测的晚到修订，本批采用新输入版本和完整回放，不在线修补已有 EMA 或事件状态。

`revision_id` 在全部取值为整数记号时按整数比较，否则按字符串比较。混合类型拒绝。

## 有效区间、单位和生命周期

归一化后的成分、ST 和行业区间是两端闭合。空的 `effective_to` 表示在已声明覆盖内尚未结束。来源若使用左闭右开，必须在政策中写下转换，并保留原端点。本批不从尚未可用的未来变更反推过去不知道的终点。先按 cutoff 选择已可用事实，再重建当时区间。

布尔列必须是布尔类型。字符串 `"False"` 不是假。未知事实用相应的 `*_known=false` 表示，不能靠占位布尔值冒充事实。

`amount_cny` 和 `circ_mv_cny` 只允许以下倍率，而且倍率只来自本政策，不来自来源定义自报的自由乘数：

- `CNY` 乘 1
- `THOUSAND_CNY` 乘 1000
- `TEN_THOUSAND_CNY` 乘 10000

其他单位、缺单位和与政策不一致的自报倍率报 `SOURCE_UNIT_UNVERIFIED` 或 `SOURCE_MANIFEST_INVALID`。价格尺度沿用调整后价格等于原始价格乘以存储因子，四个 OHLC 都检查，`rtol=0.00002`，`atol=0.00002`。因子必须有限且为正。不用价格比填缺因子，不采用未认证旁路，不做样本末日归一化。

已验证且在截止点前可用的全天停牌可以派生成交额 0，来源标记为 `VERIFIED_HALT_ZERO`。部分停牌、迟到停牌和未知缺失不填零。

本批只支持在特征起点已经上市、并且覆盖到输出终点的固定跟踪集合。需要上市前或退市后价格状态的输入报 `UNSUPPORTED_SECURITY_LIFECYCLE`。不能删掉该证券，也不能补一行未知后宣布已经支持。成分调出后仍保持 `track_identity=true`，`required_for_rank` 只属于当时候选。

## 消费者窗口与历史前缀

日历、原价、复权价、因子和上市跟踪状态覆盖特征起点至输出终点。成分和 ST 先按完整特征区间要求覆盖。行业和流通市值覆盖输出窗口及当时横截面，不为 EMA 预热补造无消费者的早期行业或市值。成交额覆盖输出起点前 19 个已声明市场日至输出终点。窗口外字段可以是 `NOT_REQUIRED`，不能编造 `available_at`。窗口内的明确未知保留为未知。缺行业、市值或 ADV20 不改变价格周期重置。

历史前缀包含：`trade_date<=cutoff` 的行情及修订；`available_at<=cutoff` 或 `effective_from<=cutoff` 的事件或参考记录；已消费日期上的日历和名册。只追加更晚的观测、更晚才生效且更晚才可用的事件、以及更晚的名册或日历时，前缀保持不变。政策、单位、端点或已消费源历史改变，则旧状态失效。晚到的历史修订视为历史源变化。

## 本批固定错误码

`SOURCE_MANIFEST_INVALID`、`SNAPSHOT_POLICY_INVALID`、`SNAPSHOT_MODE_MISMATCH`、`REVIEW_RECEIPT_UNTRUSTED`、`REVIEW_SCOPE_MISMATCH`、`SOURCE_UNIT_UNVERIFIED`、`AMBIGUOUS_ASOF_REVISION`、`AVAILABLE_AT_SOURCE_REJECTED`、`SNAPSHOT_COVERAGE_INCOMPLETE`、`SNAPSHOT_CONTENT_CHANGED`、`UNSUPPORTED_SECURITY_LIFECYCLE`、`SNAPSHOT_STATE_BINDING_MISSING`、`SNAPSHOT_PREFIX_MISMATCH`。

重复键、OHLC、尺度和名册继续使用已有错误码。读取路径必须落在调用方给出的允许根之内。解析后的实际路径若离开允许根，包括 Windows 目录联接，报 `SOURCE_MANIFEST_INVALID`。清单精确到文件，不使用目录通配符吸纳新文件。读取前后哈希不一致报 `SNAPSHOT_CONTENT_CHANGED`。

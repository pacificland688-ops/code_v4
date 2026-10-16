# v0.2 r3：就绪、左截断与完整名册

2026-10-14。本文件是 r2 之后的工程草案，不替换 r2 文本，也不升级任何 r2 运行、检查点或成果。`schema` 为 `momentum_pullback.engineering.v0_2.r2` 的合同一律拒绝，检查点 `momentum_pullback.checkpoint.v2` 一律拒绝续跑。状态仍为 `DRAFT` / `PROPOSED`，`freeze_timestamp=null`，`outcomes_enabled=false`。不生成收益，不搜索参数，不扩展股票池。

研究范围不变：历史时点沪深 300、日线、多头。输出窗口 2018-01-01 至 2018-03-30。预热起点沿用合同中的 `feature_origin`（当前 2015-01-05）。2018Q1 只作为工程样本。

## 价格就绪与重置

每个证券、每个市场日在收盘后计算两个布尔值。二者只依赖必要价格历史和 EMA，不把行业、流通市值或 ADV20 未就绪当作重置的附加条件。

`feature_ready` 在该日收盘后为真，当且仅当以下三项同时成立：

1. `price_history_known` 为真。自预热起点或已验证检查点以来，没有未知价格状态，也没有晚于信号截止才可用的价格。已验证的全天停牌不新增价格观测，也不打断这条已知历史。
2. EMA21 与 EMA50 都是有限正数，并且是在这条已知历史上按 `ema_adjust=false` 递推出来的。首个有效收盘把两条 EMA 初始化为该收盘；此后每个有效收盘按 `2/(span+1)` 更新。未知价格断层之后，EMA 数值可以留在状态里供审计，但不再视为可评估，`feature_ready` 为假。
3. 有效价格观测数达到 `min_price_observations`（150）。只计已交易、价格在信号截止前可用、且 OHLC 为正有限并满足高低关系的市场日。初始化那一根计入 1 次。

`reset_ready` 在该日为真，当且仅当 `feature_ready` 为真、当日 `price_known` 为真，且本根处理前 EMA 已经被前序有效收盘初始化。因此：

- 第一根上“收盘等于刚初始化的 EMA”不是重置，即使以后把 150 改成 1 也不允许用这根相等关系确认趋势重置。
- 就绪之前出现的 `close<=EMA50` 只用于预热 EMA，不写入 `reset_observed_at`，不把 `identity_known` 设为真，也不能在日后补当成种子。
- 就绪当天如果观测到 `close<=EMA50`，这是就绪后的真实观测，可以作为重置。比较使用当日更新后的 EMA。对 `adjust=false` 的递推，这等价于收盘小于或等于更新前的 EMA。
- 就绪之后仍须再看到一次真实的 `close<=EMA50` 才允许重置。检查点里已经验证过的身份、根、触碰编号和 EMA 是唯一允许直接带入的种子；不能靠改布尔标志或重放首根来制造。

`price_known` 只表示当日价格事实已知。它单独不能证明重置有效。

事件引擎在 `reset_ready` 为假时保持原身份：左截断继续是 `LEFT_CENSORED`，不记有效重置，不开根，不计触碰。已由检查点恢复的已知身份不被这根未就绪价格清除。`reset_ready` 为真且 `feature_ready` 为假的输入直接拒绝。

## 名册、分母与批次

排名分母不能由“这次读到的行情行”自证。调用方必须另行提交已审查的每日名册，列至少包括 `trade_date`、`ts_code`、`required_for_rank`、`track_identity`。

- `required_for_rank`：该日 PIT 候选池成员，排名前必须有对应行情行。缺整行时报 `REQUIRED_MEMBER_MISSING` 并中止排名。不得补一行零观测，也不得标成已知历史不足。
- `track_identity`：身份跟踪集合，含当时候选和已调出但仍需延续旧周期的证券。缺行时报 `IDENTITY_TRACKING_MEMBER_MISSING`。当前候选必须同时被跟踪；只要求排名、不要求跟踪的名册无效。
- 历史成员并集只用于把旧根和触碰编号继续算下去。它不进入候选池，也不把分母放大。调出期间身份和编号保留；重新调入时，没有新的有效重置就不能把触碰编号归零。
- 合法分母只在必需名册内部计算：当时是成员、ST 状态已知且不是 ST、价格历史已知、有效观测不少于 150、动量有限。已知历史不足可以排除并标 `KNOWN_INELIGIBLE`。历史未知或资格未知保持 `UNKNOWN`，并把当日 `rank_denominator_complete` 设为假。
- 没有名册时可以计算价格特征，也可以标出行内已知不合格，但不得宣布分母完整，也不得给出 `KNOWN_ELIGIBLE`。
- 股票批次只许计算各自的价格特征（`rank=false`）。全部必需证券到齐后，只做一次横截面排名和同一分母上的平均秩百分位。对完整名册的子集直接排名必须失败，不能各取前 20%。
- 横截面入口先检查证券与日期的业务键。完全相同的重复和字段互相冲突的重复都拒绝，不能任取一条。汇总后的行情键必须与当日跟踪名册一致；多出来的证券报 `CROSS_SECTION_SCOPE_MISMATCH`。
- 行情行里已知为成员的证券，必须属于当日 `required_for_rank`。否则报 `ROSTER_MEMBERSHIP_CONFLICT`。只跟踪、不参加排名的证券，行内 `is_member` 必须为假，不能借成员标志把分母放大。
- 排名完成后，分母中的行标记 `in_rank_denominator`，当日所有行写入同一个 `rank_denominator_hash`，并在这个集合上保存平均秩百分位。匹配只接受这个集合和这些百分位。集合不一致报 `MATCH_DENOMINATOR_MISMATCH`；百分位与同一集合上的重算不一致报 `MATCH_PERCENTILE_IDENTITY_MISMATCH`。

## 日历

认证日历是外部有序市场日列表，不是行情里出现过的日期集合。声称日历与认证日历任一端不一致，报 `CERTIFIED_CALENDAR_MISMATCH`。在认证日历上删掉一个市场日的全部观测，报网格或日历缺口，不能把剩下的短序列当成完整样本。

## 版本

本草案的运行使用检查点 `momentum_pullback.checkpoint.v4`。`momentum_pullback.checkpoint.v2` 与 `momentum_pullback.checkpoint.v3` 都不能续跑，也不能自动升级。

v4 在合同哈希、代码哈希、特征起点、已处理截止和已消费行情/日历之外，新增必需字段 `consumed_roster_hash`。它覆盖截止日及以前的名册行：`trade_date`、`ts_code`、`required_for_rank`、`track_identity`。改变其中任一历史记录，恢复旧状态会报 `CHECKPOINT_IDENTITY_MISMATCH`。只在截止日之后追加名册、行情或日历，已消费前缀保持不变，可以核对后续跑。不能靠修改布尔标志把未验证状态补成种子。

来源裁定的目录、台账、可行性报告、清单和隔离键文件作为一套发布。新内容先写在暂存位置；与已有五件套冲突时，在替换任何旧文件之前拒绝。五件套要么全部保持原哈希，要么全部是同一次运行的字节。相同输入的重复运行不改写已有字节。首次发布若在可捕获的 I/O 错误上中断，只删除本次新建且字节仍等于暂存身份的文件，然后报 `PUBLISH_INTERRUPTED`。身份对不上或删除失败的文件保留，并报 `PUBLISH_ROLLBACK_INCOMPLETE`；下一次运行不得把缺件的集合补齐，也不得改写留下来的字节。已有完整五件套仍在替换前拒绝。旁路因子与无效因子键是一对一关联；聚合后的重复键直接拒绝，不能拆成多条缺口，也不能保留最后一条。

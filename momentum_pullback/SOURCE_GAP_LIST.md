# 来源补齐清单

2026-10-16。实施方根据已发布的来源裁定编制，不改写五件套，不改写 `data/parquet`，不运行 `repair_adj_factor.py`，不采纳未认证旁路因子。本清单不是合同绑定文档，不改变运行身份。日期型公告政策保持 `PROPOSED_NOT_APPLIED`，不能把未知字段填成历史发布时间。下载时间、`trade_date` 和文件修改时间都不是公告可用时点。

真实路径维持 **SOURCE_UNAVAILABLE / DATA_BLOCKED**。输出窗口 2,477 行无效因子、44 只证券，事前范围仍是 **ELIGIBILITY_UNKNOWN**。台账 9,812 行 = 输出 2,477 + 预热 7,335。研究参数保持 PROPOSED，收益关闭。

已发布五件套在本清单编写时的身份如下。若后续重跑改变其中任一哈希，应先拒绝发布，而不是改这份清单去迁就新字节。

| 产物 | SHA-256 |
| --- | --- |
| `momentum_pullback/evidence/source_adjudication/source_catalog.json` | `c6b6b4001e582762f33835778b6e7f1fc242cd2f42147c2703e7911af4addf30` |
| `momentum_pullback/evidence/source_adjudication/factor_issue_ledger.parquet` | `23e7a121b65ac8cf8430ac5aab00c8eabc0d156ea8944dd37b0a315ac6a823dd` |
| `momentum_pullback/evidence/source_adjudication/source_feasibility_report.md` | `3e87a29d124853e71e6ec2f44e2796bd07869bcccf4328b265e8f60155c2c76f` |
| `momentum_pullback/evidence/source_adjudication/adjudication_manifest.json` | `de20e1aab3cad932833fa7a56c3df0a5890d376206cfdb0286269aad9e5f1062` |
| `data/research/momentum_pullback/source_adjudication_r3/unverified_sibling_factor_keys.parquet` | `28bd40e52f5f26e95f8f82b1471059c6ccaf39745f474d272bdafe99d19ff578` |

旁路键文件只含键和处理方式，不入库。责任栏里，实施方维护本清单，审核方认证后才能改状态。当前没有可提交的认证件。

## 优先项

### 1. PIT 成分公告可用时点与生效区间

| 项 | 内容 |
| --- | --- |
| 字段 | 成分事件的 `available_at`、`effective_from`、`effective_to`。不是 `index_weight.trade_date`，也不是权重本身。 |
| 需要覆盖 | 2015-01-05 至 2018-03-30 的历史时点沪深 300 每日应有名册，含调出后仍需跟踪的身份。 |
| 现有证据 | `index_weight` 观察到的年份分区是 2017–2026。预热年份 2015、2016 不在本地分区。窗口内 000300.SH 快照日为 20170126、20170228、20170331、20170428、20170531、20170630、20170731、20170831、20170929、20171031、20171130、20171229、20180131、20180228、20180330。每个快照 300 只。`pit_fields_present=false`，发布时间 UNKNOWN，用途是 `DESCRIPTIVE_ONLY_NOT_A_PIT_ROSTER`。输出窗口无效因子的 44 只证券里，出现在该未认证权重文件中的只数是 0。这个 0 不是“已证明池外”。 |
| 缺什么 | 带时区的公告可用时点，以及生效区间的端点约定。没有这两项，就不能把一行标成必要研究范围或已证明池外。 |
| 从哪里取得 | 当前 `data/parquet/index_weight` 没有这三列。需要一份可哈希的认证成分事件表。本清单不指定供应商，也不把权重行的成交日改写成公告时间。 |
| 现在能否取得 | 不能。 |
| 责任 | 实施方记录缺口；审核方核验证据后才允许改变 `ELIGIBILITY_UNKNOWN`。 |
| 状态 | **SOURCE_UNAVAILABLE / DATA_BLOCKED**。2,477 行继续 **ELIGIBILITY_UNKNOWN**。 |

### 2. 认证交易日历

| 项 | 内容 |
| --- | --- |
| 字段 | 认证市场日序列。合同绑定是 `MARKET_SESSION_NO_NATURAL_DAY_FALLBACK`。 |
| 需要覆盖 | 2015-01-05 至 2018-03-30。 |
| 现有证据 | 同一窗口内两份文件不一致。`trade_cal/cache.parquet` 942 行，`is_open` 为 0 和 1，交易所只有 SSE，SHA-256 `04cac58e7d0bc12b5b263d0d952c364bdf924b2c5361e99e3f2fba38bfab41a1`。`trade_cal/calendar.parquet` 791 行，`is_open` 只有 1，交易所只有 SSE，SHA-256 `e125b34da900ce8fa432f5b899f80158a5a3e6c8d9565a2f3b44df9f9d1b37b0`。两份都没有发布时间。 |
| 缺什么 | 哪一份是交易所会话日历的认证，以及认证范围是否只含 SSE。较短的那份不能自证为完整日历。 |
| 从哪里取得 | 两份本地文件互相矛盾，不能从其中选出认证日历。需要外部认证后的市场日列表，并与行情网格对照。 |
| 现在能否取得 | 不能。 |
| 责任 | 实施方保持两份文件只读；审核方认定认证件之前，日历门不通过。 |
| 状态 | **SOURCE_UNAVAILABLE / DATA_BLOCKED**。目录中的证据状态是 UNVERIFIED。 |

### 3. 2015 年起的完整预热价格

| 项 | 内容 |
| --- | --- |
| 字段 | `prices_adj` 的原始收盘与调整后收盘。完整预热还依赖第 1 项名册才能定义应有网格；本项先记录价格缓存本身不完整。 |
| 需要覆盖 | `feature_origin` 2015-01-05 至输出终点 2018-03-30。 |
| 现有证据 | 2015 年 12 个月文件都在目录的输入清单里，合计只有 1,361 行，且没有 `adj_factor` 列。这是整年缓存不完整，不是完整行情里的少量缺行。预热切片合计 1,049,646 行，其中缺因子列 1,361 行。输出窗口 137,594 行。公共缓存未被改写。 |
| 缺什么 | 从 2015-01-05 起、能对上将来认证名册的完整价格历史。缺列不能展开成零因子，也不能用调整后价格除以原始价格来补。 |
| 从哪里取得 | 现有 `data/parquet/prices_adj/year=2015` 不能提供完整年。补齐必须是可哈希、可追溯的新版本，写入隔离位置，原缓存保持只读。本次不下载、不回写。 |
| 现在能否取得 | 不能。2016–2018 的月文件存在，不能代替 2015 年。 |
| 责任 | 实施方不得用换年份绕开；审核方核对覆盖之后才允许进入真实预热。 |
| 状态 | **DATA_BLOCKED**。 |

## 随后补齐的证据

以下各项同样阻断真实快照。顺序放在三项优先项之后。

### 4. 因子尺度与可用性

| 项 | 内容 |
| --- | --- |
| 字段 | `prices_adj.adj_factor`。有限正因子按“调整后价格 = 原始价格 × 存储因子”核对，容差 rtol=2e-5、atol=2e-5。 |
| 需要覆盖 | 2015-01-05 至 2018-03-30 中，将来被认证名册纳入的每一行。 |
| 现有证据 | 有限正因子：输出窗口 135,117 行，尺度不一致 0 行，最小值 1.0，最大值 10055.64；预热 1,040,950 行，尺度不一致 0 行，最小值 0.969，最大值 10055.64。最大值远大于 1，所以不是样本末日归一成 1 的系数。无效因子全部是空值：输出 2,477 行、预热 7,335 行。发布时间和生效时间都是 UNKNOWN。 |
| 缺什么 | 因子的公告或供应商修订可用时点、生效区间，以及对 2,477 行的事前范围裁定。2015 年文件没有因子列。 |
| 从哪里取得 | 尺度关系已经能在现有有限因子上观察到，但这只是缓存观察，不是发布证明。旁路 `adj_factor` 对全部 9,812 个问题键给出有限正因子，且与已存调整后收盘一致，处理方式仍是 `DO_NOT_ADOPT_UNVERIFIED_SIBLING`。旁路没有 `announced_at` 或修订号。不运行修复脚本，不把旁路写回原缓存。 |
| 现在能否取得 | 认证后的发布时点现在不能取得。旁路数值存在，但是禁止采用。 |
| 责任 | 实施方保持原缓存和旁路隔离；审核方没有新的发布证据前，不把这些行改成可构建快照。 |
| 状态 | 有限因子行是 **OBSERVED_CACHE_ONLY**，发布证据仍缺失。无效行 **ELIGIBILITY_UNKNOWN**。旁路是 **UNVERIFIED_SIBLING_CACHE**，采用路径 **SOURCE_UNAVAILABLE**。 |

### 5. ST 与上市状态

| 项 | 内容 |
| --- | --- |
| 字段 | 历史时点 ST，以及上市/退市状态。合同绑定是 `PIT_ST_AND_VERIFIED_FULL_DAY_HALT` 的 ST 部分。 |
| 需要覆盖 | 2015-01-05 至 2018-03-30 的每个应有证券日。 |
| 现有证据 | `namechange.ann_date` 年份分区从 1990 到 2026 都有。它只有日期、没有时区，语义未认证，不是 ST 事件表。`start_date` / `end_date` 存在，端点约定未验证。`stock_status.list_status` 是一份当前状态提取，没有历史轴，也没有 as-of。 |
| 缺什么 | 带时区的 ST 可用时点和生效区间；可重建历史的上市状态。`ann_date` 不能复制进 `available_at`。 |
| 从哪里取得 | 这两张本地表都不能认证为 PIT ST。日期型公告政策即使将来生效，也只适用于已被认证且只有日期的公告，并且取该日 Asia/Shanghai 最后一微秒；该政策现在是 `PROPOSED_NOT_APPLIED`，不回填未知字段。 |
| 现在能否取得 | 不能。 |
| 责任 | 实施方不把名称变更日当成 ST 证明；审核方认证专门的 ST 事件后才放行。 |
| 状态 | **SOURCE_UNAVAILABLE / DATA_BLOCKED**。`namechange` 的目录状态是 UNVERIFIED，`stock_status` 是 SOURCE_UNAVAILABLE。 |

### 6. 全天停牌

| 项 | 内容 |
| --- | --- |
| 字段 | 已验证的全天停牌标志。合同用语不是本地 `suspend_type` 的原文字。 |
| 需要覆盖 | 2015-01-05 至 2018-03-30。已验证的全天停牌不新增价格观测，也不把成交额填成零以外的推断值；未验证停牌不能填零成交额。 |
| 现有证据 | `suspend_status` 年份分区覆盖 2015–2026。2015 年只观察到 month=4、6、7、8、9、10、11、12。没有发布时间，也没有按本合同词汇核对过的全天标志。 |
| 缺什么 | 停牌公告可用时点、全天与部分停牌的区分，以及 2015 年缺失月份是否代表“没有停牌”还是“缓存缺失”。当前不能区分。 |
| 从哪里取得 | 本地 `suspend_status` 不够。需要带发布时间、且能区分全天停牌的认证事件。本次不补下载。 |
| 现在能否取得 | 不能。 |
| 责任 | 实施方不把缺失月份当成已验证的无停牌；审核方认定全天标志后才允许派生零成交额。 |
| 状态 | **SOURCE_UNAVAILABLE / DATA_BLOCKED**。 |

### 7. 行业

| 项 | 内容 |
| --- | --- |
| 字段 | 行业代码的公告可用时点与生效区间。合同绑定是 `PUBLICATION_AVAILABLE_AND_EFFECTIVE_DATE`。 |
| 需要覆盖 | 2015-01-05 至 2018-03-30。匹配时行业缺失要阻断匹配，不清空已知价格周期。 |
| 现有证据 | `industry_member.effective_date` 的年份分区从 2016 起，不含 2015。没有 `available_at`。生效日的语义未验证。发布时间 UNKNOWN。 |
| 缺什么 | 可用时点、生效端点约定，以及 2015 预热段的行业成员。只有日期的 `effective_date` 不是盘中时间。 |
| 从哪里取得 | 本地行业表缺 2015，也缺可用时点。需要认证后的行业事件，而不是把 `effective_date` 提前到信号截止之前使用。 |
| 现在能否取得 | 不能。 |
| 责任 | 实施方保持 SOURCE_UNAVAILABLE；审核方核到覆盖预热起点的生效区间后才放行匹配协变量。 |
| 状态 | **SOURCE_UNAVAILABLE / DATA_BLOCKED**。生效列的目录状态是 FIELD_PRESENT_SEMANTICS_UNVERIFIED。 |

### 8. 流通市值与成交额

| 项 | 内容 |
| --- | --- |
| 字段 | `daily_basic.circ_mv` 与 `prices_raw.amount`。合同要求信号时点可得的流通市值，单位是 CNY。ADV20 是 20 个市场日，单位必须先认证。 |
| 需要覆盖 | 2015-01-05 至 2018-03-30 中匹配所需的协变量日。行业、市值和 ADV20 未就绪不作为价格周期重置的附加条件。 |
| 现有证据 | `daily_basic` 年份分区包含 2015–2026，但没有 `available_at`，缓存没有写出 CNY 或其他单位，所以没有做换算。`prices_raw.amount` 在工程窗口的月文件存在，没有货币单位字段，发布时间 UNKNOWN。 |
| 缺什么 | 市值单位、成交额单位、两者的可用时点。没有单位证据就不能换成合同里的 CNY。 |
| 从哪里取得 | 数值列在本地缓存里可以读到，单位和时点证据读不到。需要带来源单位和可用时点的认证字段。本次不按猜测把市值乘以或除以一个常数。 |
| 现在能否取得 | 作为认证字段不能取得。 |
| 责任 | 实施方不填单位、不把文件时间写成可用时点；审核方确认单位和时点后才允许进入归一化。 |
| 状态 | **SOURCE_UNAVAILABLE / DATA_BLOCKED**。市值与成交额的数值存在只说明 OBSERVED 或分区存在，不改变阻断。 |

## 明确不充当补齐的东西

- `PROPOSED_NOT_APPLIED`：若将来某份来源被认证且公告只有日期，可用时点取该日 Asia/Shanghai 的 23:59:59.999999，且不能用于更早的信号截止。这条政策不回填现在的 UNKNOWN。
- 未认证旁路因子、价格比、`repair_adj_factor.py`。
- 权重文件里的 0 只重合、文件下载时间、`trade_date`、mtime。
- 换年份、换板块，或把资格未知改成已证明池外。
- 删除静态拒绝、把许可标志改成 true，或只补列名。这些不能打开真实事件入口。

## 通过本清单之后才允许的下一步

合成快照和数据门可以用明确标注 SYNTHETIC 的输入继续开发。真实 2018Q1 事件与固定配对仍要等来源认证和快照门都通过。收益分析继续等待单独的 P3 条件。

## 获取入口、权限与责任（2026-10-16）

本段只登记仓库里已经存在的读取入口。本批没有调用这些入口，没有下载，没有检查外部令牌是否有效。分类只用四档：`LOCAL_ABSENT`、`EXTERNAL_NOT_INVESTIGATED`、`PERMISSION_INSUFFICIENT`、`OBTAINED_PENDING_REVIEW`。仓库没有登记外部联系人。数据负责人准备隔离目录中的新版本；审核方认证后才能改变阻断状态。令牌权限本批未核查，所以不把任何一项写成 `PERMISSION_INSUFFICIENT`。

### 1. PIT 成分

| 项 | 内容 |
| --- | --- |
| 获取入口 | `TushareClient.get_index_weight`（`data/tushare_client.py`）写入 `data/parquet/index_weight`。`UniverseBuilder.load`（`data/universe.py`）把快照日加默认 1 日滞后当作 `available_date`。该滞后是代码参数，不是公告时间。本地分区仍缺 2015 和 2016。 |
| 访问与授权 | 入口存在，但本批不调用、不读令牌。公告时点字段在本地缓存中不存在。外部接口能否提供带时区的公告时间和生效区间，尚未调查。 |
| 责任角色 | 数据负责人提出隔离取得申请。审核方核对公告时间与生效区间。无外部联系人登记。 |
| 所需日期 | 2015-01-05 至 2018-03-30 的每日应有名册，含调出后仍跟踪的证券。 |
| 下一步 | 单独授权后，把成分事件写到隔离目录，保留 `available_at`、`effective_from`、`effective_to`。不覆盖 `data/parquet`，不用 `trade_date` 填公告时间。 |
| 证据分类 | 公告时点与生效区间：`LOCAL_ABSENT`。外部能否提供：`EXTERNAL_NOT_INVESTIGATED`。 |
| 结论 | 仍是 SOURCE_UNAVAILABLE / DATA_BLOCKED。2,477 行继续 ELIGIBILITY_UNKNOWN。 |

### 2. 认证交易日历

| 项 | 内容 |
| --- | --- |
| 获取入口 | `TushareClient.get_trade_cal` 与 `data/calendar.py` 的缓存目录 `data/parquet/trade_cal`。本地同时有 `cache.parquet` 和 `calendar.parquet`。 |
| 访问与授权 | 两份文件都能读。没有任何一份带认证标记。本批不重新下载，也不在两份之间挑选胜者。 |
| 责任角色 | 数据负责人保持两份文件只读。审核方指定哪一份是交易所会话日历，以及范围是否只含 SSE。 |
| 所需日期 | 2015-01-05 至 2018-03-30。 |
| 下一步 | 取得一份可哈希的认证市场日列表，与行情网格对照。短文件不能自证。 |
| 证据分类 | 本地文件：已观察到，认证身份 `LOCAL_ABSENT`。哪一份可被认证：`EXTERNAL_NOT_INVESTIGATED`。 |
| 结论 | 仍是 SOURCE_UNAVAILABLE / DATA_BLOCKED。 |

### 3. 2015 年起的完整预热价格

| 项 | 内容 |
| --- | --- |
| 获取入口 | `TushareClient.get_daily` 与现有 `data/parquet/prices_adj` 月分区。2015 年 12 个文件已在来源目录的输入清单中，合计 1,361 行，没有 `adj_factor` 列。 |
| 访问与授权 | 本地不完整年可以读，但不能当作完整预热。本批不下载，不回写，不运行 `scripts/repair_adj_factor.py`。外部完整磁带是否可授权，尚未调查。 |
| 责任角色 | 数据负责人只准备隔离新版本。审核方核对覆盖后才允许进入真实预热。 |
| 所需日期 | 2015-01-05 至 2018-03-30，并且要对上将来的认证名册。 |
| 下一步 | 在隔离目录形成可哈希的完整价格版本。2016–2018 的月文件不能代替 2015 年。 |
| 证据分类 | 完整 2015 价格：`LOCAL_ABSENT`。外部补齐可能性：`EXTERNAL_NOT_INVESTIGATED`。 |
| 结论 | 仍是 DATA_BLOCKED。 |

### 4. 因子发布时点

| 项 | 内容 |
| --- | --- |
| 获取入口 | 有限因子已经在 `prices_adj.adj_factor`。旁路读取入口是 `TushareClient.get_adj_factor` 落到 `data/parquet/adj_factor`。修复脚本 `scripts/repair_adj_factor.py` 不是本项的允许入口。 |
| 访问与授权 | 尺度关系是本地观察，不是发布证明。旁路数值存在，处理方式仍是不采纳。发布时点外部来源尚未调查。 |
| 责任角色 | 实施方保持原缓存和旁路隔离。审核方见到发布证据后才改变台账处理。 |
| 所需日期 | 认证名册覆盖到的 2015-01-05 至 2018-03-30。输出窗口的 2,477 行仍待事前范围裁定。 |
| 下一步 | 为因子取得 `announced_at` 或修订号，以及生效区间。不从价格比推导，不把旁路写回。 |
| 证据分类 | 有限因子尺度：本地已观察，但发布时点 `LOCAL_ABSENT`。旁路采用：`LOCAL_ABSENT` 的认证。外部发布证据：`EXTERNAL_NOT_INVESTIGATED`。 |
| 结论 | 无效行继续 ELIGIBILITY_UNKNOWN。旁路继续 UNVERIFIED_SIBLING_CACHE。 |

### 5. ST 与上市状态

| 项 | 内容 |
| --- | --- |
| 获取入口 | `TushareClient.get_namechange` 与 `get_stock_basic`。本地表是 `namechange` 和单文件 `stock_status`。 |
| 访问与授权 | `ann_date` 只有日期。`stock_status` 没有历史轴。本批不把它们认证为 PIT ST，也不启用日期型公告政策。 |
| 责任角色 | 数据负责人寻找专门的 ST 事件，而不是复用名称变更日。审核方认证。 |
| 所需日期 | 2015-01-05 至 2018-03-30 的每个应有证券日。 |
| 下一步 | 隔离取得带时区可用时点和生效区间的 ST / 上市事件。 |
| 证据分类 | 已认证 PIT ST：`LOCAL_ABSENT`。外部事件表：`EXTERNAL_NOT_INVESTIGATED`。 |
| 结论 | 仍是 SOURCE_UNAVAILABLE / DATA_BLOCKED。 |

### 6. 全天停牌

| 项 | 内容 |
| --- | --- |
| 获取入口 | `TushareClient.get_suspend` 写入 `data/parquet/suspend_status`。2015 年本地月份不完整。 |
| 访问与授权 | 本地行没有按本合同词汇核对过的全天标志，也没有发布时间。本批不把缺失月份解释成没有停牌。 |
| 责任角色 | 数据负责人补充分月证据或明确缺失原因。审核方认定全天标志后，才允许派生成交额零。 |
| 所需日期 | 2015-01-05 至 2018-03-30。成交额消费者另按输出前 19 个市场日起算，这不降低停牌认证要求。 |
| 下一步 | 取得能区分全天与部分停牌、且带可用时点的事件。未验证行不填零。 |
| 证据分类 | 已验证全天停牌：`LOCAL_ABSENT`。外部分类字段：`EXTERNAL_NOT_INVESTIGATED`。 |
| 结论 | 仍是 SOURCE_UNAVAILABLE / DATA_BLOCKED。 |

### 7. 行业

| 项 | 内容 |
| --- | --- |
| 获取入口 | `TushareClient.get_industry` 与本地 `industry_member`。年份分区从 2016 开始，本地没有 2015。 |
| 访问与授权 | `effective_date` 存在，`available_at` 不存在。快照政策只把行业要求放在输出窗口，这不把 2015 的空缺变成已认证，也不缩短价格预热。 |
| 责任角色 | 数据负责人按消费者窗口准备输出期行业事件。审核方核对端点约定。 |
| 所需日期 | 真实匹配至少需要 2018-01-01 至 2018-03-30。2015 预热不要求行业。 |
| 下一步 | 为输出窗口取得可用时点和生效区间。不把 `effective_date` 提前到信号截止之前使用。 |
| 证据分类 | 2015 分区：`LOCAL_ABSENT`。输出窗口的可用时点：`LOCAL_ABSENT`。外部认证件：`EXTERNAL_NOT_INVESTIGATED`。 |
| 结论 | 仍是 SOURCE_UNAVAILABLE / DATA_BLOCKED。 |

### 8. 流通市值与成交额

| 项 | 内容 |
| --- | --- |
| 获取入口 | `TushareClient.get_daily_basic` 对应 `daily_basic.circ_mv`。`prices_raw.amount` 在价格月文件中。两者都没有单位元数据。 |
| 访问与授权 | 数值可以读到。单位和可用时点不能从列名猜出，也不能乘一个未写入政策的常数。本批政策里的 CNY / 千元 / 万元倍率只适用于已经声明单位的合成来源，不套用到这份公共缓存。 |
| 责任角色 | 数据负责人取得单位说明和可用时点。审核方确认后才允许换算成 CNY。 |
| 所需日期 | 市值覆盖输出窗口。成交额覆盖输出起点前 19 个认证市场日至输出终点。价格预热不因这两项缺失而失效。 |
| 下一步 | 在隔离字段中记录单位和 `available_at`。不按文件时间填可用时点。 |
| 证据分类 | 单位与时点：`LOCAL_ABSENT`。供应商单位说明：`EXTERNAL_NOT_INVESTIGATED`。数值本身不是 `OBTAINED_PENDING_REVIEW`，因为缺单位就不能进入认证字段。 |
| 结论 | 仍是 SOURCE_UNAVAILABLE / DATA_BLOCKED。 |

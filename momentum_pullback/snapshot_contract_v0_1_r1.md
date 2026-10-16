# 快照政策 v0.1 r1：事实选择、覆盖、源主键与接受标记

2026-10-16。本文件是 C 批工程修订，政策 ID 为 `momentum_pullback.snapshot_policy.v0_1_r1`。状态仍是 `PROPOSED_ENGINEERING_SPEC`。`parameter_status` 保持 `PROPOSED`，`freeze_timestamp` 保持空，`outcomes_enabled` 保持 false。EMA、动量、等待窗口、匹配、1% 拟定限价和 10 日拟定主检验都不在本文件调整。

v0.1 文件 `momentum_pullback/snapshot_contract_v0_1.md` 保留，不改写。新运行显式绑定本文件和 `configs/momentum_pullback/snapshot_policy_v0_1_r1.yaml`。本修订只澄清工程行为。它不授予 REAL 权限，也不构成策略有效或可交易的结论。

日期型公告政策 ID 仍是 `DATE_ONLY_ANNOUNCEMENT_ASIA_SHANGHAI_END_OF_DAY`，状态仍是 `PROPOSED_NOT_APPLIED`。

## 检查点代码身份

检查点结构保持 `momentum_pullback.checkpoint.v4`。本批不增加自动迁移。v2 和 v3 仍报 `CHECKPOINT_NOT_UPGRADABLE`。

恢复时，核心检查点的 `code_hash`、快照绑定的 `code_hash` 和当前进程的 `implementation_hash()` 必须相同。传给 `restore_checkpoint` 的期望代码身份来自当前运行。绑定与检查点互相一致只是必要条件。旧实现生成的自洽状态，即使合同、政策、来源和已消费前缀相同，也报 `CHECKPOINT_IDENTITY_MISMATCH`，细节为 `code_hash`，不返回可用状态。不为旧实现状态签出当前绑定。新实现产生新的 `implementation_hash` 后，旧运行目录不重写；需要时重新完整生成本批合成状态。

## 停牌事实

停牌先在完整来源上按业务键 `ts_code + trade_date`、`available_at<=signal_cutoff` 和 `MAXIMUM_DECLARED_ORDER` 选择一条修订，再判断所选记录。不得先滤掉 `FULL_DAY` 再在子集里选修订。

只有所选记录同时是 `fact_status=KNOWN` 且 `halt_scope=FULL_DAY`，才得到 `VERIFIED_FULL_DAY_HALT`，并派生成交额 0，来源标记 `VERIFIED_HALT_ZERO`。部分停牌、未知、迟到修订和截止后才可用的修订不能复活更早的全天停牌，也不能补足价格网格。已确认全天停牌不增加有效价格观测数。未知缺失不得获得同样的零成交额待遇。并列修订仍报 `AMBIGUOUS_ASOF_REVISION`。

来源不能表达的撤销状态不猜测。`halt_scope` 只接受 `FULL_DAY` 和 `PARTIAL_DAY`，其他值报 `SOURCE_MANIFEST_INVALID`。

## 行业覆盖

行业按实际可用值和两端闭合的有效区间计算。输出窗口内的空值、已过期区间、尚未生效区间、显式 `UNKNOWN` 和截止后才发布的值，分别记录证券、日期、字段和原因：`VALUE_ABSENT`、`INTERVAL_ENDED`、`NOT_YET_EFFECTIVE`、`EXPLICIT_UNKNOWN`、`LATE_EXCLUDED`。这些情况的匹配字段不得报告 `COMPLETE` 或 `unknown=0`。快照为 `SYNTHETIC_SNAPSHOT_PARTIAL`，完整冒烟入口不得签发 `SYNTHETIC_ENGINEERING_PASS`。

三个层次分开保留：价格数据可计算，首次身份可判断，匹配可评估。缺行业不改变价格周期、重置和触碰编号，也不替换控制股。窗口外不需要的行业仍是 `NOT_REQUIRED`。没有事件时仍按窗口报告字段覆盖，不用空事件表掩盖缺失。

## 报告兼容

`momentum_pullback.coverage_report.v1` 的 `COMPLETE / unknown=0` 只表示旧实现曾检查记录是否存在。它不能被解释为 r1 的值和有效区间覆盖。r1 快照内覆盖报告的 schema 是 `momentum_pullback.coverage_report.v2`，快照内数据门报告的 schema 是 `momentum_pullback.data_gate_report.v2`，并写明 `coverage_rule=VALUE_AND_EFFECTIVE_INTERVAL`。旧报告不迁移，也不升格为新版完整覆盖。

## 源主键

每个字段组的 `source_primary_key` 来自所选原始记录和该表已经校验过的主键声明。行情、成交额、市值和停牌通常是 `ts_code + trade_date + revision_id`。成分、ST 和行业通常是 `ts_code + effective_from + revision_id`。具体以来源声明和实表列为准。目标 `trade_date` 保留为 lineage 的独立列，不塞进事件源主键。

主键序列化为带字段名的规范 JSON 对象，键名排序，不使用无字段名的分隔符拼接。声明列缺失、空值或无法解析时报 `SOURCE_MANIFEST_INVALID`，原因 `PRIMARY_KEY_UNDECLARED`、`PRIMARY_KEY_COLUMN_MISSING` 或 `PRIMARY_KEY_UNRESOLVED`。重复主键继续使用 `DUPLICATE_OR_CONFLICTING_KEYS`。没有选中源行的未知事实把主键留空，并标明未知原因。派生的零成交额追踪到已确认停牌事实，不虚构一条原始成交额为零的记录。

## 输入身份与接受标记

冒烟在特征、事件、匹配和续跑计算之前固定输入字节。输入闭包包括快照清单、清单引用的实际工件、来源清单、审核件、原始表、当前政策、绑定文档、策略合同及绑定文档，以及实际消费的手工预期。至少包括 `normalized_panel.parquet`、`universe_daily.parquet`、`calendar.parquet`、`lineage.parquet`、覆盖报告和数据门报告。清单里的哈希不能代替这些文件的字节。

首次读取已不符合绑定时报 `SNAPSHOT_CONTENT_CHANGED`。身份固定之后的内容变化报 `INPUT_CONTENT_CHANGED_DURING_RUN`。

`acceptance_summary.json` 是该次冒烟目录里的唯一终态接受标记。计算成果、诊断、成果哈希和全部检查完成之后，才在同一文件系统内最后提交它。哈希索引排除自身和最终摘要。暂存摘要或普通诊断文件不能单独授予 PASS。失败时撤销本次接受资格并写 `blocked.json`。已有摘要不是跳过阻断的理由。本批不改写旧运行目录、来源五件套或原始输入。

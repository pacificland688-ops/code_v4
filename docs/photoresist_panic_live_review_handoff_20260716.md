# 光刻胶恐慌预警系统代码审查交接说明

> 交接日期：2026-07-16  
> 工作目录：`D:\workspace\q_project\code_v4`  
> 当前结论：P0/P1代码修复与回归已通过；正式股票池证据仍待人工审核，
> 影子期保持关闭，`TRADE_READY` 必须保持 `False`。

> 状态提示：第5-11节保留的是修复前审查现场与复现证据；当前结果以第12节为准。

## 1. 给新会话的任务说明

请基于本文件继续处理光刻胶 `primary_5d` 恐慌预警系统。

开始工作前必须：

1. 阅读本文件及相关实现，不要从头重新设计策略。
2. 保持 `primary_5d_frozen_v1` 的事件公式和阈值冻结，不得根据近期收益调参。
3. 优先修复本文 P0，再处理 P1；P0 未通过前不得开启 20 日影子期。
4. 修复必须补充对应的失败注入或独立运行测试，不能只依赖全仓测试通过。
5. 不得将系统改成自动交易系统，`trade_ready` 继续硬编码为 `False`。
6. 当前目录没有 Git 仓库元数据，不能依赖 `git diff` 判断改动范围。

## 2. 系统目标与定位

该系统用于在 A 股光刻胶核心股票池出现恐慌性下跌时，于收盘后输出研究预警：

- `PANIC_ALERT`：确认冻结的 `primary_5d` 恐慌事件是否触发。
- `REVERSAL_CANDIDATE`：仅在 bull/neutral 环境下提示条件性反转观察。
- `TRADE_READY=False`：不自动下单，也不表示单票交易规则已经验收。

冻结事件定义：

```text
篮子 5 日收益 < 0
AND（5 日收益 <= -5% OR 低于过去 250 日滚动 10% 分位）
AND 过去 5 日平均下跌股票占比 >= 50%
```

滚动分位使用 `shift(1)`，当日数据不得进入当日阈值。

## 3. 主要代码与配置

```text
live/photoresist_panic/
  common.py
  commonality.py
  data_updater.py
  journal.py
  notifier.py
  outcome_tracker.py
  quality_gate.py
  renderer.py
  reversal.py
  runner.py
  severity.py
  signal_engine.py
  state_machine.py
  universe.py

configs/photoresist_panic_live.yaml
configs/photoresist_universe_v2.yaml

scripts/run_photoresist_panic_alert.py
scripts/replay_photoresist_panic_alert.py

tests/test_photoresist_live_*.py
```

相关说明：

```text
docs/photoresist_panic_live_alert_system.md
docs/photoresist_panic_gap_fix_delivery.md
docs/photoresist_primary_5d_analysis_and_issues.md
```

## 4. 已确认关闭的问题

以下旧问题已经通过代码和实际数据核验，可视为已关闭，但修复时仍需防回归：

1. 日期运算不再使用 `YYYYMMDD + 1`，已改为真实日历运算。
2. `931865.CSI` 的 2026 年内部缺口已经补齐。
3. 最近 250 个交易日的指数与核心股连续性报告无未解释缺口。
4. 原 `+43.6%` 伪指数跳涨已消失；当前 2026 最大单日涨幅为 `9.6576%`。
5. 数据质量门能阻断“末日新鲜但中间缺失”的指数或个股数据。
6. 复权 OHLC 必须同时具备 `adj_open/adj_high/adj_low/adj_close`。
7. `require_amount_present=true` 时，amount 缺失会阻断而不是仅警告。
8. 成员口径已区分 `all_active_members` 和 `signal_eligible_members`。
9. 2026-07-15 上海新阳跌停虽然被 gate eligibility 排除，仍进入 P4 压力统计。
10. 当前 2026-07-15 输出已从旧错误的 P3 修正为 P4。
11. journal 已保存逐日 transition 快照，catch-up 不再用最终 state 覆盖历史 signal ID。

当前实际输出：

```text
日期：2026-07-15
质量门：NORMAL
active：4
signal eligible：3
跌停成员：上海新阳（300236.SZ）
恐慌等级：P4
shadow_enabled：false
trade_ready：false
```

## 5. P0 阻断问题

### P0-1 通知没有形成可恢复的 outbox

相关代码：

```text
live/photoresist_panic/runner.py:454-463
live/photoresist_panic/notifier.py:147-163
```

现状：

1. runner 先保存 state，再执行 manifest 和 webhook。
2. 如果在 state 保存后、首次 webhook 尝试前崩溃，重跑时 `pending_days=[]`、`transitions=[]`。
3. `retry_pending()` 只重试 delivery log 中已经出现的 `pending_retry`。
4. 从未尝试过的 journal 通知事实不会被自动发送，恐慌通知会永久丢失。
5. 首次发送失败后的重试只发送 `payload_summary`，实际正文退化为 `first_trigger` 等标题。

已复现：

```text
首次正文：# FULL ALERT\ncritical details
重试正文：first_trigger
从未尝试的通知：retry_pending 返回 0 条
```

修复要求：

- journal transition 必须可投影为 notification outbox。
- 每次运行比较“应通知 journal 事实”和 delivery ledger，而不是只处理本次 `transitions`。
- 保存可重建的通知 payload 或足够完整的事件快照。
- 重试必须发送原始完整正文。
- 新增 state 提交后、首次通知前崩溃的故障注入测试。
- 新增失败重试正文完全一致测试。

### P0-2 入场成分没有 append-only 冻结

相关代码：

```text
live/photoresist_panic/journal.py:160-175
live/photoresist_panic/runner.py:416-452
live/photoresist_panic/outcome_tracker.py:294-318
```

现状：

- journal 只记录 `SIGNAL_REGISTERED`，没有 `ENTRY_RESOLVED` 事实。
- runner 每次运行都根据当前行情、涨跌停和 ST 数据重新解析历史入场成分。
- 数据补录或修订后，同一 signal 的 `entry_component_codes` 和历史收益会改变。

已复现：补录某股票入场日涨停数据后，历史入场成分从 4 只变为 3 只。

修复要求：

- 下一交易日数据完整后，追加一次 `entry_resolved` journal 记录。
- 记录 signal ID、entry date、纳入成分、排除原因、数据版本或输入摘要。
- 一旦解析成功，普通重跑不得覆盖；更正必须使用显式 revision 记录。
- registry、entry eligibility 和 outcome 必须从冻结记录投影。

### P0-3 无解释行情缺失被当成停牌并输出 COMPLETE

相关代码：

```text
live/photoresist_panic/outcome_tracker.py:132-186
live/photoresist_panic/outcome_tracker.py:248-250
tests/test_photoresist_live_outcome_tradability.py:135-143
```

现状：

- `_valuation_grid()` 对所有缺失行情无条件 `ffill()`。
- 没有核对 suspend records、退市状态或数据缺口报告。
- 只要统一日历有 20 日，即使某成分长期没有真实行情，也会标记 `COMPLETE`。
- 当前测试明确允许“无停牌记录消失 30 日”仍为 COMPLETE，测试预期本身错误。

风险：陈旧价格会压低波动、最大亏损和回撤，产生虚假的正式 outcome。

修复要求：

- 只有存在可审计停牌记录的缺失日才允许前值估值。
- 无解释缺失必须输出 `OUTCOME_DATA_BLOCKED` 或 `INVALID_DATA_GAP`。
- 不能生成正式收益、命中率、MAE/MFE 或止盈止损结论。
- 增加逐日估值覆盖率和缺失原因字段。
- 修改现有错误测试并增加全成分缺失、部分缺失、复牌等场景。

## 6. P1 重大问题

### P1-1 COOLDOWN 中的严重度升级被吞掉

`state_machine.py:130-133` 在 COOLDOWN 触发时只返回 `cooldown_reset`，不更新 `max_severity`、不追加触发日期，也不发升级通知。

已复现：P2 进入 COOLDOWN 后遇到 P4，结果仍为 `max_severity=P2`、`emit_alert=False`。

正确语义：不创建新事件、不重复开仓，但 P2 到 P3/P4 的风险升级仍必须通知。

### P1-2 固定回放 40 日不能保证首次部署状态正确

`runner.py:335-340` 固定回放最后 40 个交易日。由于 COOLDOWN 可被触发无限次重置，事件总持续期没有 40 日上界。

修复方向：

- 从可证明的 IDLE/checkpoint 开始重放；或
- 回放完整可用在线历史；或
- 向后找到足以证明状态归零的连续无触发区间，并记录证明。

不得把“当前样本碰巧一致”当成算法保证。

### P1-3 30% 单票权重上限在三成分时失效

相关配置与代码：

```text
configs/photoresist_universe_v2.yaml:299-300
scripts/build_photoresist_panic_events.py:694-698
```

当前配置同时要求：

```text
max_single_weight: 0.30
min_components: 3
```

三只股票完全投资时单只最低权重为 33.33%，两项约束不可同时满足。当前算法 clip 到 30% 后再次归一化，最终仍为 33.33%。2026-07-15 已实际出现三只 eligible 成分。

该问题涉及冻结 gate 语义。不得直接覆盖 v1；必须选择并治理新版本，例如要求至少 4 只、允许现金权重或将上限调整为不低于 1/3。

### P1-4 重复键质量检查被生产加载器提前消除

相关代码：

```text
live/photoresist_panic/signal_engine.py:63-65
scripts/build_photoresist_panic_events.py:238-240
live/photoresist_panic/quality_gate.py:152-160
```

生产加载器先 `drop_duplicates()`，质量门随后才统计重复键。因此底层 parquet 即使重复，质量门也会显示通过；保留哪条记录还可能取决于文件顺序。

修复要求：在去重前生成原始重复键审计；发现重复时阻断或执行显式、确定性的修复。

### P1-5 Outcome 测试依赖测试收集顺序

单独运行：

```powershell
python -m pytest tests\test_photoresist_live_outcome_tradability.py -q
```

当前结果：

```text
9 failed, 3 passed
ModuleNotFoundError: No module named 'build_photoresist_panic_events'
```

全仓测试之所以通过，是其他测试先导入 `common.py` 并修改全局 `sys.path`。应将共享函数放入可正常导入的包模块，禁止依赖测试顺序和隐式路径污染。

### P1-6 入场流动性检查名不副实

`outcome_tracker.resolve_entry()` 只要求入场日 `amount > 0`，没有执行冻结 eligibility 的 20 日平均成交额门槛。事件日因低流动性被排除的股票，下一日只要有极少成交就可能进入“可交易 basket”。

修复时应明确：沿用冻结的 20 日成交额资格门槛，或单独冻结 outcome tradability 门槛；不能把 `amount > 0` 描述为流动性验收。

## 7. P2 治理与语义问题

1. `p4_requires_limit_down_or_volume: true` 未被 `severity.py` 使用，当前 breadth 单独即可升 P4。
2. DEGRADED 状态下一只股票停牌时，active breadth 的分母会缩小；成交量压力还可能使用停牌前最后一日数据。
3. 2026 股票池仍为 `confirmed_desk_research`，source URL 是通用入口，document hash、reviewer、reviewed_at 均为空。
4. `universe_status.pending_review` 只匹配包含 `pending` 的字符串，因此四只 `confirmed_desk_research` 股票不会出现在该列表中，虽然 alert 另有 review note。
5. delivery 文档声称 156 项专项测试通过，当前实际 `-k photoresist_live` 为 90 项，应修正文档统计口径。

## 8. 已执行验证

专项测试：

```powershell
python -m pytest tests -k photoresist_live -q
```

结果：

```text
90 passed, 1258 deselected
```

全仓测试：

```powershell
python -m pytest -q
```

结果：

```text
1329 passed, 19 skipped, 24 warnings
```

注意：全仓通过不能覆盖上述测试顺序依赖；Outcome 测试独立运行仍失败。

实际数据核验：

```text
data_gap_report：250 个交易日，unexplained_gaps=[]
931865.CSI：无重复键，当前数据截止 2026-07-15
2026 最大绝对单日涨跌幅：9.6576%
```

未完成项：完整历史状态与固定 40 日初始化状态的实际对比运行曾在 120 秒超时，未取得结果；但 COOLDOWN 可无限重置已经从状态机逻辑上证明固定 40 日不具备正确性保证。

## 9. 推荐实施顺序

```text
阶段 A：通知 outbox
  P0-1 journal -> outbox 投影
  完整 payload 重试
  state 提交后崩溃测试

阶段 B：Entry/Outcome 事实化
  P0-2 entry_resolved journal 事实
  P0-3 缺失日分类与 outcome 阻断
  P1-6 正式流动性口径

阶段 C：状态机恢复
  P1-1 COOLDOWN 严重度升级
  P1-2 可证明的初始化 checkpoint

阶段 D：数据与测试可信度
  P1-4 原始重复键审计
  P1-5 消除 sys.path/测试顺序依赖

阶段 E：冻结信号治理
  P1-3 权重上限矛盾单独立项
  如需改变 gate，创建新候选版本，不覆盖 primary_5d_frozen_v1

阶段 F：P2 审计闭环
  P4 配置语义
  股票池正式证据归档
  文档与测试数量校正
```

## 10. 验收门槛

P0/P1 修复后至少满足：

1. journal 中每条应通知事实最终都有 delivery terminal status，不允许“从未尝试”。
2. webhook 重试正文与首次正文完全一致。
3. entry resolution 只生成一次，普通重跑和数据补录不改变冻结结果。
4. 无解释缺失不能输出 COMPLETE 或正式 forward return。
5. COOLDOWN 内 P2 到 P3/P4 只升级通知，不产生新 signal ID。
6. 初始化结果可由完整重放或 checkpoint 证明，不依赖固定 40 日假设。
7. 生产 loader 的底层重复键能被质量门发现。
8. 每个 `test_photoresist_live_*.py` 均可独立运行通过。
9. 全仓测试继续通过。
10. 实际 2026-07-15 回放仍为 P4，且 4 active / 3 eligible / 1 limit-down 口径不回归。
11. `shadow_enabled=false`、`trade_ready=false`，直到全部 P0/P1 验收完成。

## 11. 新会话建议首条指令

```text
请阅读 docs/photoresist_panic_live_review_handoff_20260716.md，先复核代码现状和审查发现，不要修改冻结的 primary_5d。随后按 P0-1、P0-2、P0-3 顺序实施修复，每项都补故障注入测试和独立测试，并在完成后重新运行专项测试、独立 Outcome 测试和全仓测试。TRADE_READY 必须保持 False。
```

## 12. 2026-07-16 续作完成记录

本节覆盖并取代第5-11节中的“当前未修复”状态。冻结信号公式、阈值和
`primary_5d_frozen_v1` 均未修改。

### 12.1 P0 验收

1. 通知 outbox：每条应通知 journal 事实都携带完整 Markdown payload；运行时扫描
   全部 journal 与 delivery ledger 的差集。已通过“state提交后、首次webhook前崩溃”
   故障注入，以及失败重试正文逐字一致测试。
2. 入场冻结：下一交易日追加 `entry_resolution` 事实，记录成分、排除原因、输入摘要、
   数据版本和20日流动性检查。普通重跑不能覆盖，修订必须追加显式 revision。
3. Outcome 缺口：只有 `suspend_status` 明确记录的停牌日允许前值估值；无解释缺口
   输出 `OUTCOME_DATA_BLOCKED`，正式收益、MAE/MFE、止盈止损字段保持空值，并输出
   逐日估值覆盖率与缺口原因。

### 12.2 P1 验收

1. COOLDOWN 内 P2→P3/P4 会发 `severity_upgrade`，沿用原 signal ID，不创建新事件。
2. 首次初始化不再固定回放40日。系统寻找最近的可证明IDLE安静窗口并持久化完整
   checkpoint；找不到证明窗口时回放全部可用历史。
3. 生产股票/指数 loader 在质量门前不再去重；质量报告列出原始重复键与行数并阻断。
4. 所有 `test_photoresist_live_*.py` 已逐文件独立运行通过；Outcome 已改用包内共享函数，
   不再依赖其他测试先污染 `sys.path`。
5. 入场流动性沿用冻结 eligibility 的20日平均成交额门槛，历史不足时 fail closed。
6. frozen v1 的三成分/30%矛盾不做追溯改写：每日输出实际1/3权重及约束未满足审计；
   `configs/photoresist_basket_constraints_v2_candidate.yaml` 为至少4成分的未启用候选，
   必须另行回测审批并使用新 gate version。

### 12.3 P2 已关闭与剩余项

已关闭：

- `p4_requires_limit_down_or_volume=true` 已生效；广度只能作为附加证据，成交放大或
  跌停至少满足一项才从P3升P4。
- active breadth 使用固定active成员分母；停牌前成交额不再作为当日压力数据。
- `confirmed_desk_research` 现在进入 `pending_review`。
- 交付文档已校正初始化与测试统计。

仍需人工治理：2026核心池的正式来源归档、document hash、reviewer和reviewed_at。
不得自动把 `confirmed_desk_research` 改为 `approved`。

### 12.4 最终验证

```text
独立 Outcome：17 passed
逐个 live 测试文件：全部独立通过
live 专项：105 passed, 1259 deselected
全仓：1345 passed, 19 skipped, 24 warnings
```

隔离实际回放目录：

```text
outputs/live/photoresist_panic_alert_review_validation_20260716_final
```

2026-07-15 验证结果：

```text
初始化证明：2026-04-20至2026-05-26连续24个未触发交易日，checkpoint=IDLE
checkpoint后重放：33个交易日
质量门：NORMAL，原始股票/指数重复键均为0
active：4
signal eligible：3
跌停成员：上海新阳（300236.SZ）
恐慌等级：P4
entry_resolution事实：2条
Outcome无解释缺口：0，最低估值覆盖率：100%
shadow_enabled：false
trade_ready：false
```

影子期尚未启动。启动前仍需人工确认正式股票池证据治理和候选权重规则是否继续立项。

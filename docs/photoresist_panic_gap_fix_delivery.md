# 光刻胶实盘预警系统 — 缺口修复交付文档（v2）

> 状态：`RESEARCH_ONLY` + `SHADOW_DISABLED`。primary_5d 公式冻结未动，
> TRADE_READY 恒为 False。本文档覆盖修复计划的全部交付文档要求：
> 数据恢复记录、状态事务设计、成员口径说明、故障恢复手册、影子期验收报告模板。

---

## 1. 数据恢复与回填记录（2026-07-15 执行）

### 1.1 修复的缺陷

| 缺陷 | 根因 | 修复 |
|---|---|---|
| 931865.CSI 缺 2026-01-05 ~ 2026-06-05（100个交易日），缺口边缘产生 +43.6% 伪跳涨 | 旧更新器只看 max_date，不查窗口内连续性 | 逐证券 missing_dates → fetch_ranges 补齐 |
| index_daily 窗口内 492 行重复键（246 个键） | 历史多次写入未按分区去重 | `repair_duplicate_keys` 分区级 read-modify-write 去重 |
| `yyyymmdd + 1` 整数日期运算（20260131+1=20260132） | 无真实日历运算 | `yyyymmdd_add_days`（datetime + timedelta） |
| trade_cal 缓存约 1000 倍重复行导致 `[-250:]` 窗口坍缩成 1 天 | 缓存累积重复 | `expected_open_dates` 输出去重排序 |
| limit_status 每股缺 174 天 | 旧更新按整体 max_date | 逐证券补齐 |

### 1.2 回填后验证（计划 §3.4，全部通过）

```text
931865.CSI 2026年覆盖：127/127 交易日
重复键：0
close 推导收益 vs pct_chg：最大偏差 0.0
最大单日涨跌：9.66%（真实行情），43.6% 伪跳涨消除
全部核心股票最近250交易日：0 个无法解释缺口
```

### 1.3 输出

- `outputs/live/photoresist_panic_alert/data_gap_report.json` — 每次运行生成，
  逐证券列出缺失日、合法停牌日、无法解释缺口。
- 旧 v1 状态文件归档于 `outputs/live/photoresist_panic_alert/legacy_v1/`。

---

## 2. 状态事务设计说明

### 2.1 事实源：append-only journal

`panic_transition_journal.jsonl` 是系统唯一事实源。每条记录携带幂等键：

```text
gate_version + trade_date + signal_id + transition_kind
```

写入为 append + flush + fsync；重复键追加为 no-op。三类投影全部可由
journal 重建（`journal.rebuild_state / rebuild_registry / rebuild_history`）：

```text
panic_state.json          最后一条 transition 的内嵌快照
signals_registry.json     所有 is_new_event 记录（各自的 signal_id 与成员集合）
panic_alert_history.csv   全量确定性投影（每次运行整文件重写）
```

### 2.2 提交顺序（计划 §4.3）

```text
计算transition → 原子写journal → 写signal registry → 写history
→ 刷latest alert → 更新outcome → 最后原子提交state → webhook推送
```

state 永远最后提交。任何前置步骤失败 ⇒ `last_processed_date` 不推进 ⇒
下次运行重算同一批日期 ⇒ journal 幂等去重 ⇒ 投影重建 ⇒ 信号零丢失
（测试：`test_failure_before_state_commit_recovers_without_losing_signal`、
`test_rerun_after_crash_journal_dedupes`）。

### 2.3 Transition 快照（计划 §4.1）

每条 transition 携带当日完整快照：trade_date、signal_id、live_signal_date、
event_counter、state_before/after、kind、severity、triggered、is_new_event、
emit_alert、active_days_elapsed、cooldown_clear_count、max_severity、
active_member_codes、eligible_member_codes、excluded_components、
market_regime、component_status、alert_status。
**补跑结束后读取最终 state 解释历史日被禁止**——投影只用记录内快照
（测试：`test_historical_transitions_keep_their_own_snapshot`）。

### 2.4 运行锁（计划 §4.5）

`panic_runner.lock`：O_EXCL 创建，内容含 pid/host/run_id/started_at/恢复指引。
第二实例硬失败；>2h 陈旧锁记录原持有者后接管（journal 保证接管安全）。

---

## 3. 成员口径说明（计划 §5）

每日两个成员集合：

```text
all_active_members       PIT有效的全部核心成员（active_members(universe, day)）
signal_eligible_members  经冻结资格过滤（停牌/ST/流动性/跌停事件/连续跌停）
                         真正参与primary_5d basket的成员
```

- `signal_engine.eligibility_snapshot` 给出逐股排除原因，其纳入集合与冻结
  `filter_eligible_stocks` 逐一交叉验证（`test_eligibility_snapshot_matches_frozen_filter`）。
- 预警显示 `active_components / signal_components / excluded_components[{code,reason}]`。
- 共同性两套结果：`theme_commonality`（全部active，判断板块是否共跌）与
  `signal_commonality`（gate成员，说明信号由谁计算）。
- 严重度冻结分工：P2/P3 幅度腿 = 冻结 eligible basket 指标；
  **P3/P4 流动性压力腿 = 全部 active 成员**（跌停股被 gate 排除仍计入 P4）。
- 跌停判定 = 精确涨跌停价命中 OR 冻结代理（pct_chg<=-9.5，即资格过滤的
  "跌停事件"定义）——压力统计口径不得窄于排除口径。

### 2026-07-15 回归验证（计划验收，全部符合）

```text
primary gate参与成员：3        全部核心成员：4
上海新阳排除原因：limit_down_event_day（跌停事件）
theme down count：4/4          limit_down_count：1（300236.SZ）
严重度：P4（P3幅度腿 + 1只核心成员跌停）
```

初始化使用可证明 IDLE checkpoint（若找不到则完整历史回放），不再依赖固定
40 日假设。2026-07-15 验证从 2026-05-26 的 IDLE checkpoint 重放 33 日：
当前事件实际首触发于 **2026-07-08**（7-15为P3→P4升级日），且窗口内
存在已完结的前一事件（5-27触发 → 6-25冷却 → 7-02回IDLE，
前向20日净收益+27.8%但MAE -14.4%、第1日即触及-5%止损线，保守口径记为先止损）。

---

## 4. 前向 Outcome 口径（计划 §6）

- 两阶段注册：触发日 `SIGNAL_REGISTERED`（记录active成员）→ 次一交易日收盘
  `ENTRY_RESOLVED`（停牌/涨停买不进/ST/成交额/行情完整性过滤，冻结
  entry_component_codes，逐股原因写 `entry_eligibility.csv`）；
  可交易成员 <3 ⇒ `NO_TRADABLE_BASKET`，不计正式前向收益。
- 统一交易日网格估值：停牌日 close 沿用上一有效收盘，high/low=该收盘，
  复牌日落在正确的网格日（禁止"每只股票自己的第N条记录"）。
- 入场篮子20日冻结：缺失成员carry估值、分母不变，每日报告 `min_valued_components`。
- `target_hit_intraday` 更名 `component_high_upper_bound_hit`（成分最高价
  发生时间不同步，仅为上界）；保守主口径 = close-basis target hit。

---

## 5. 故障恢复手册

| 症状 | 处理 |
|---|---|
| 运行中途崩溃（state未提交） | 直接重跑。journal幂等，投影重建，信号不丢 |
| `panic_state.json` 损坏/被误改 | 自动：启动时与journal核对，不一致即重建并写 `state_recovery_report.json` |
| journal 某行损坏 | 硬失败（RuntimeError）。人工处理：删除损坏行之后的内容，重跑补算 |
| `panic_runner.lock` 残留 | <2h：等待或确认无实例后手动删除；>2h：自动接管并记录原持有者 |
| Webhook 发送失败 | 不影响信号事实；`notification_delivery_log.jsonl` 记 pending_retry，下次运行自动重试（≥5次后 gave_up） |
| 数据缺口 BLOCKED | 查 `data_gap_report.json`；合法停牌需suspend记录佐证；补数后重跑 |
| 首次部署/换目录 | 必须 `--initialize-state`（可证明IDLE checkpoint，否则完整历史回放；不补发历史通知）；`--fresh-start` 仅在明确接受可能漏掉进行中事件时使用（manifest 记录 possible_missed_active_event） |
| history/registry 与预期不符 | 以 journal 为准：`python -c "from live.photoresist_panic import journal; ..."` 重建比对 |

---

## 6. 影子期验收报告（模板 — 影子期于P0验收后启动）

验收窗口：连续 ≥20 个交易日（起始日：____）

| 验收项 | 目标 | 结果 |
|---|---|---|
| 自动运行成功天数 | 20/20 | |
| 重复推送次数 | 0（delivery log审计） | |
| 丢失transition | 0（journal连续性审计） | |
| 数据缺口阻断率 | 100%（BLOCKED记录 vs gap_report） | |
| journal重建一致性 | state/registry/history全部可重建一致 | |
| TRADE_READY | 全程False | |

审计命令：

```powershell
python -m pytest tests -k photoresist_live -q
python scripts\replay_photoresist_panic_alert.py --start 20190101 --end 20251231
```

---

## 7. 交付清单

新增/修改代码：`live/photoresist_panic/{data_updater,quality_gate,journal,
state_machine,runner,signal_engine,severity,commonality,outcome_tracker,
notifier,renderer,universe,common}.py`；配置 `photoresist_panic_live.yaml
(schema v2)`、`photoresist_universe_v2.yaml`（evidence字段）。

新增输出：`panic_transition_journal.jsonl`、`notification_delivery_log.jsonl`、
`entry_eligibility.csv`、`data_gap_report.json`、`state_recovery_report.json`、
`initialization_checkpoint_report.json`。

测试：`tests/test_photoresist_live_{data_updater,quality_gate,
runner_transactions,outcome_tradability,notifications,members,engines,
state_machine,universe}.py` — 2026-07-16 独立与专项口径共 105 项通过；
全仓 1345 项通过、19项跳过。

股票池证据治理：v2 2026成员含 document_id/title/publication_date/source_url/
document_sha256/reviewer/reviewed_at/review_status；`approved` 才可生产，
当前 `confirmed_desk_research` ⇒ 预警显式标注"未完成正式审核，仅供研究"。

# 光刻胶恐慌性下跌实盘预警系统（v1）

> 状态：`RESEARCH_ONLY`。系统只识别恐慌、解释严重程度、判断反转环境，
> 不自动交易、不输出确定买入指令。`TRADE_READY` 在 v1 恒为 `False`。

## 1. 三个独立状态

```text
PANIC_ALERT          已发生恐慌性下跌（冻结 primary_5d 触发）
REVERSAL_CANDIDATE   当前环境历史上更有利于反转（bull/neutral）
TRADE_READY          v1 恒为 False
```

## 2. 冻结内容

primary_5d 公式**不在本系统中重新实现**。在线引擎直接导入冻结研究实现
`scripts/validate_photoresist_panic_thresholds.build_threshold_gate`，并在
启动时校验 `configs/photoresist_panic_live.yaml:frozen_gate` 与
`configs/photoresist_panic_research.yaml:threshold_validation.gates.primary_5d`
完全一致，任何漂移直接启动失败（`common.validate_frozen_gate`）。

```text
历史分位窗口 250 交易日（严格 shift(1)，当日不进窗口）
历史分位 10% / 绝对跌幅 -5% / 广度窗口 5 日 / 广度门槛 50%
事件识别：当日收盘后；实盘信号日：首次触发日；最早执行日：下一交易日
```

## 3. 运行

```powershell
# 首次部署（必须显式选择初始化模式；生产用 --initialize-state）
python scripts\run_photoresist_panic_alert.py --initialize-state

# 每交易日 16:30 后（先增量更新 Tushare，再评估）
python scripts\run_photoresist_panic_alert.py

# 指定日期 / 只用本地数据
python scripts\run_photoresist_panic_alert.py --as-of 20260715 --no-refresh
```

退出码：`0` 正常产出状态；`2` 数据质量门阻断；`3` 运行失败（同样落盘
`latest_failure.json` 并走通知通道）；`4` 首次部署未指定初始化模式。

Windows 定时任务示例：

```powershell
schtasks /Create /TN PhotoresistPanicAlert /SC WEEKLY /D MON,TUE,WED,THU,FRI `
  /ST 16:35 /TR "python D:\workspace\q_project\code_v4\scripts\run_photoresist_panic_alert.py"
```

> v2 缺口修复（journal事务、成员口径、逐证券连续性、通知幂等等）见
> `docs/photoresist_panic_gap_fix_delivery.md` — 该文档为最新权威说明。

## 4. 模块结构（live/photoresist_panic/）

```text
data_updater.py     Tushare增量更新：prices_raw+adj_factor→prices_adj(后复权)、
                    index_daily(逐指数增量)、limit_status、suspend。
                    全部按月/年分区 read-modify-write 合并，4只股票的增量
                    更新绝不覆盖全市场历史分区。
quality_gate.py     数据质量门：股票行情必须到最新已收盘交易日、指数对齐、
                    成分完整性(4/4 NORMAL, 3/4 DEGRADED, <3 BLOCKED)、
                    重复键、复权价非空非负、成交额、涨跌停可用、250日预热。
universe.py         PIT股票池 v2 加载与完整性校验（区间不重叠、
                    announcement_date 门控、历史区间冻结）。
signal_engine.py    冻结 basket 构建 + 冻结 gate 应用 + 当日指标快照。
state_machine.py    IDLE/ACTIVE/COOLDOWN 首次触发状态机（见 §6）。
severity.py         P0-P4 恐慌等级（仅解释，不改变P2信号）。
reversal.py         市场状态(bull/neutral/bear, 冻结公式) + Wilson 95%区间。
commonality.py      成分共同性：SECTOR_WIDE/MIXED/STOCK_DRIVEN/INSUFFICIENT_DATA。
outcome_tracker.py  前向结果：5/10/20日、净赚5%目标、MAE/MFE(复权OHLC)、
                    止损路径、同日止盈止损保守口径+path_ambiguous标记。
renderer.py         Markdown/JSON 预警渲染。
notifier.py         控制台+文件通知，webhook(企业微信)预留，失败也通知。
runner.py           日度编排 + 漏跑日补处理(catch-up) + 幂等 + 审计落盘。
```

## 5. 股票池 v2（configs/photoresist_universe_v2.yaml）

- 历史区间（v1, 截止 20251231）逐字保留，不覆盖。
- 2026 区间为**新增条目**：`effective_start=20260101`，PIT 依据为
  2025三季报（`announcement_date=20251031`），2025年报（2026-04）复核确认；
  桌面研究确认四家公司半导体光刻胶业务持续、无退出。
- `active_members()` 按 `announcement_date <= trade_date` 门控，保证任一
  日期只使用当时已公开的信息。
- 快照与清单随每次运行输出：`photoresist_universe_v2_snapshot.csv`、
  `photoresist_universe_v2_manifest.json`。
- 超过 `effective_end` 且未建立新区间时，`strict_effective_end: true`
  直接 BLOCKED，不做静默 carry-forward。

## 6. 状态机

```text
IDLE     首次触发：记录 live_signal_date、发首次预警、进入 ACTIVE
ACTIVE   最长20交易日：不生成新事件；重复触发只更新强度；
         P2→P3/P4 升级发升级通知；绝不回改首次触发日
COOLDOWN 需连续5个交易日 primary_5d=False 才回 IDLE；
         期间再次触发重置计数、不生成新事件；P3/P4升级仍通知
```

- 状态持久化于 `panic_state.json`（原子写）。
- 同一日期重复运行 → `duplicate_run`：刷新 latest 文件，不重复发报、
  不追加历史。
- 漏跑多日后运行 → 自动按交易日逐日 catch-up，中间日转移写入历史
  （`alert_status=catch_up`）。

## 7. 恐慌等级（仅解释）

```text
P0 正常
P1 跌幅进入历史最差20%但未触发primary_5d
P2 primary_5d正式触发
P3 P2 且（5日跌幅<=-8% 或 历史最差5%）
P4 P3 且（放量>=1.5x 或 成分跌停）；广度>=75%为附加压力证据
```

当前 `p4_requires_limit_down_or_volume=true`，因此广度不能单独把P3升为P4。

## 8. 反转环境

市场状态冻结公式：沪深300 收盘 vs MA120 + 60日收益。
Bull → REVERSAL_CANDIDATE；Neutral → REVERSAL_CANDIDATE_LOW_SAMPLE；
Bear/unknown → REVERSAL_DISABLED（明确显示"禁止仅依据恐慌信号抄底"）。
STOCK_DRIVEN 时反转状态降级为 REVERSAL_CANDIDATE_DOWNGRADED。

历史参考只显示：样本数(21)、命中范围(14-16)、Wilson 95%区间(约45%-89%)、
证据等级，不显示确定概率。

## 9. 输出（outputs/live/photoresist_panic_alert/）

```text
latest_alert.json / latest_alert.md    最新预警
panic_alert_history.csv                信号审计（signal_id/run_id/config_hash/...）
panic_state.json                       状态机持久化
component_diagnostics.csv              成分诊断
data_quality_report.json               质量门明细
forward_outcomes.csv                   前向结果跟踪
signals_registry.json                  信号登记（用于前向跟踪）
live_manifest.json / runtime.log       运行清单与日志
replay/                                历史回放输出
```

## 10. 历史回放与验收

```powershell
python scripts\replay_photoresist_panic_alert.py --start 20190101 --end 20251231
```

- 2019-2025 回放：1510 交易日，236 个触发日，**37 个在线首次触发事件**；
  只读当日及以前数据；在线运行与回放共用同一核心 `runner.evaluate_day`；
  v2 基线 determinism_hash = `89200ba1982936f4`（v1 基线 `e2b14f61554b0192`，
  差异来自解释层：active成员P4口径与regime列；37个首次触发日期两版完全一致）。
- 单元测试：`tests/test_photoresist_live_state_machine.py`、
  `test_photoresist_live_quality_gate.py`、`test_photoresist_live_engines.py`
  （含 shift(1) 无未来函数测试、冻结公式漂移检测）、
  `test_photoresist_live_universe.py`。

## 11. 明确不做（v1）

自动下单、自动选定唯一股票、自动仓位、承诺反转概率、
根据新结果调整 primary_5d。
Phase 0 策略淘汰测试（研究层验收 §16.3）为后续独立工作，
未通过前 Top1 单票策略保持 NO_GO。

## 12. 影子运行

第一版上线后先运行 >=20 个交易日影子期：每日 16:30 后运行，
只发研究预警，不用于真实下单。影子期验收：
连续20交易日自动运行成功、数据过期100%阻断、同一信号不重复发送、
状态机回放结果一致、所有预警可追溯（history/manifest/config_hash）。

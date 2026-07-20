# 全流程验证剩余问题修复开发方案

## 1. 背景与目标

当前一年窗口全流程验证已经可以跑通：

```powershell
python run_research.py validate --start 20160101 --end 20161231
```

最近一次实测结果为 exit code `0`，并生成 `outputs/validation_report.md`，其中 `Overall: PASS`。但仍有几个不能忽略的问题：

- 短窗口 smoke 在 Phase 2 数据不足分支会触发 `NameError: name 'calendar' is not defined`。
- `limit_status` 的 Phase 0 写入策略会按执行日/样本日覆盖整个月分区，短窗口 smoke 可能降低已有生产缓存覆盖。
- README 和 `scripts/check_env.py` 仍推荐旧的一月 smoke 命令，会把用户引向已知失败路径。
- 相关测试只覆盖了局部公式/工具函数，没有覆盖真实 `run_smoke()` 错误分支和缓存覆盖不回退行为。

本方案目标是把当前状态从“一年 validate 可跑，但短窗口和缓存策略仍有隐患”推进到：

- 一年 `validate` 继续稳定通过。
- 短窗口 `smoke --start 20160101 --end 20160229` 不崩溃，短样本不足应被标记为 `DATA_INSUFFICIENT` 或 WARN，而不是 FAIL/异常。
- 短窗口 Phase 0 不再破坏已有更宽窗口的 `limit_status` 缓存覆盖。
- 文档和环境检查建议命令与真实可用入口一致。
- 测试覆盖真实失败路径，而不是只覆盖模拟公式。

## 2. 当前已通过能力

以下能力已实测通过，可作为回归基线：

```powershell
python scripts/check_env.py
pytest -q
python scripts/audit_cache.py --start 20160101 --end 20161231
python scripts/migrate_factor_cache.py --dry-run
python run_research.py phase2 --start 20160101 --end 20161231 --no-recompute
python run_research.py validate --start 20160101 --end 20161231
```

已验证结果：

- `pytest -q`：`128 passed`。
- 一年 `audit_cache`：8 项全部 PASS。
- `migrate_factor_cache.py --dry-run`：`0 files would be removed`。
- 一年 Phase 2：exit code `0`，Windows 控制台编码问题已修复。
- 一年 `validate`：exit code `0`，`Overall: PASS`。

这些能力在修复过程中必须保持不回退。

## 3. 问题一：短窗口 smoke 的 `calendar` 未定义

### 3.1 现象

命令：

```powershell
python run_research.py smoke --start 20160101 --end 20160229
```

Phase 0 已经能通过，`limit_status` 也无重复；但 Phase 2 因短窗口返回 `Insufficient returns` 后，`run_smoke()` 进入降级分支并崩溃：

```text
NameError: name 'calendar' is not defined
```

位置：

- `run_research.py` 的 `run_smoke()` 中 Phase 2 处理分支。
- 具体问题代码附近：

```python
n_signal = len(calendar.weekly_rebalance_dates(start_date, end_date))
n_trade_days = len(calendar.trade_days_between(int(start_date), int(end_date)))
```

该作用域内没有定义 `calendar`。

### 3.2 修复方案

在 `run_smoke()` 内统一创建并加载 calendar 对象，避免在不同分支里隐式依赖。

推荐实现：

```python
from data.calendar import get_calendar
calendar = get_calendar()
calendar.load(start_date=start_date, end_date=end_date)
```

放置位置建议：

- `run_smoke()` 初始化 `loader = get_loader()` 后立即加载。
- 后续 tradable limit 检查里不再重新命名为 `cal`，统一复用 `calendar`。

需要注意：

- 不要引入 Python 标准库 `calendar` 模块命名冲突。
- 如果 `calendar.load()` 已在全局单例里加载过更宽范围，重复调用必须保持现有行为不变。

### 3.3 短窗口 Phase 2 状态语义

短窗口数据不足不是代码错误。建议保留并修正当前逻辑：

```python
is_short_window = (
    fwd_cov2["n_dates"] < 16
    or n_signal < 6
    or n_trade_days < 60
)
```

当 `is_short_window=True`：

- `checks["phase2"] = "DATA_INSUFFICIENT"`
- 添加说明性 warning。
- smoke 总体不应 exit code `1`。

建议 exit code 策略：

- `0`：没有真实失败；允许短窗口 `DATA_INSUFFICIENT`，但 verdict 为 `WARN`。
- `1`：真实失败，例如 Phase 0 失败、缓存损坏、fwd_returns 重复、Phase2 在足够数据下失败。
- 如保留 `2` 作为 WARN 也可以，但需要 `validate` 和文档同步。当前 `run_smoke()` 实际返回 `0/1`，不建议在本轮额外扩大退出码语义，避免影响调用方。

## 4. 问题二：`limit_status` 短窗口写入污染生产缓存

### 4.1 现象

Phase 0 当前只为执行日和少量样本日预取 `stk_limit`，然后按月写入：

```python
_ldr.write_data(
    lim_month,
    "limit_status",
    partition_cols=["year", "month"],
    dedupe_keys=["ts_code", "trade_date"],
    replace_partitions=True,
)
```

这会删除整个 `year/month` 分区并写入当前短窗口采样数据。结果是：

- 先跑一年 validate，可得到一年执行日覆盖。
- 再跑两个月 smoke，1 月和 2 月分区会被短窗口采样数据替换。
- 之后一年 `audit_cache` 可能仍因执行日覆盖过阈值而 PASS，但缓存覆盖已经发生回退。

当前审计标准是执行日覆盖，不是完整交易日覆盖。因此一年 validate 可以通过，但缓存行为仍不够安全。

### 4.2 设计原则

`limit_status` 写入必须满足以下原则：

- 不允许短窗口运行破坏已有更宽窗口缓存。
- 不允许产生 `(ts_code, trade_date)` 重复。
- 对当前 Phase 2 需要的执行日必须覆盖。
- 如果选择“只缓存执行日/样本日”，必须在审计和文档里明确，不应伪装成完整交易日缓存。

### 4.3 推荐方案 A：分区合并写入

这是最小变更且适合当前代码结构的方案。

对每个受影响月份：

1. 读取该月现有 `limit_status` 分区数据。
2. 与本次新抓取的 `lim_month` 合并。
3. 按 `(ts_code, trade_date)` 去重，保留新数据。
4. 再用 `replace_partitions=True` 重写该月完整合并结果。

伪代码：

```python
def _merge_limit_status_month(loader, lim_month, year, month):
    month_start = f"{year}{month:02d}01"
    month_end = last_calendar_day_or_trade_day(year, month)

    existing = loader.query(
        "limit_status",
        start_date=month_start,
        end_date=month_end,
    )

    combined = pd.concat([existing, lim_month], ignore_index=True)
    combined = combined.drop_duplicates(["ts_code", "trade_date"], keep="last")
    combined["year"] = combined["trade_date"].astype(int) // 10000
    combined["month"] = (combined["trade_date"].astype(int) % 10000) // 100

    loader.write_data(
        combined,
        "limit_status",
        partition_cols=["year", "month"],
        dedupe_keys=["ts_code", "trade_date"],
        replace_partitions=True,
    )
```

实现细节：

- 月末日期可以用简单日历月末，也可以用交易日历最后一个交易日。这里只用于过滤缓存，日历月末足够。
- `existing` 读取出来可能已经带 `year/month`，合并前应统一重新派生，避免 schema 不一致。
- 如果 `existing` 为空，行为等价于当前写入。
- 合并写入后重新 query 当前窗口，确认 duplicates 为 0。

优点：

- 保留已有覆盖，不会被短窗口覆盖掉。
- 保持当前按月分区结构。
- 不要求一次性抓完整月全部交易日。

风险：

- 每次写入前读取现有月分区，开销略增，但 `limit_status` 月级数据规模可控。

### 4.4 方案 B：完整月抓取写入

另一种方案是 Phase 0 对涉及月份抓完整交易日 `stk_limit`，再 replace 整月分区。

优点：

- 语义简单，分区就是完整月。
- 审计可以升级为交易日完整覆盖。

缺点：

- API 调用明显增加。
- 短 smoke 会变慢。
- 对 Tushare 限频更敏感。

若当前项目重点是回测执行日约束，建议优先采用方案 A。

### 4.5 审计脚本增强

`scripts/audit_cache.py` 当前对 `limit_status` 只输出：

```text
0 dup, 67 dates, exec coverage=100.0%
```

建议增强 detail：

```text
0 dup, 67 cached dates, exec coverage=100.0%, trade-day coverage=27.5%
```

状态规则建议：

- `FAIL`：duplicates > 0。
- `FAIL`：exec coverage < 80%。
- `PASS`：exec coverage >= 80%，duplicates = 0。
- `WARN`：trade-day coverage < 90%，但 exec coverage PASS。提示“limit_status is execution-date scoped, not full-calendar cached”。

如果团队决定只要求执行日覆盖，则一年窗口出现 trade-day coverage 低不应阻塞 validate，但必须可见。

## 5. 问题三：README 和环境检查建议命令过时

### 5.1 当前问题

README 和 `scripts/check_env.py` 仍推荐：

```powershell
python run_research.py smoke --start 20160101 --end 20160131
```

该窗口存在 PIT universe 可用日不足问题，不应作为推荐 smoke。

### 5.2 README 更新方案

建议将 Quick Start 改成：

```powershell
# 1. Check environment
python scripts/check_env.py

# 2. Audit existing cache for the validation window
python scripts/audit_cache.py --start 20160101 --end 20161231

# 3. Full validation, one-year real-data pipeline
python run_research.py validate --start 20160101 --end 20161231
```

如果保留短窗口 smoke：

```powershell
# Optional short-window smoke.
# This may report DATA_INSUFFICIENT for Phase 2 because the window is too short.
python run_research.py smoke --start 20160101 --end 20160229
```

同时更新 Phase Reference：

- 增加 `validate` 行。
- 说明 `smoke` 是短窗口数据链路检查，不代表完整回测验证。
- 说明 `validate` 是当前推荐的端到端验证入口。

还应修复 README 中已有乱码，例如：

- `鈥?`
- `鈫?`
- `脳`

文档统一保存为 UTF-8。

### 5.3 `scripts/check_env.py` 更新方案

修改 runtime guidance 和 suggested command。

当前内存 WARN 时仍输出：

```text
SAFE: python run_research.py smoke --start 20160101 --end 20160131
```

建议改为：

```text
SAFE: python run_research.py smoke --start 20160101 --end 20160229
RECOMMENDED VALIDATION: python run_research.py validate --start 20160101 --end 20161231
```

对于内存 <4GB 的环境，需要更谨慎：

- `smoke` 可安全运行。
- 一年 `validate` 实测 peak memory 低，但耗时长；仍建议关闭占内存程序。
- 10 年全量 `all` 不建议在可用内存低时直接跑。

## 6. 问题四：测试覆盖不足

### 6.1 现有不足

当前测试文件中存在 smoke 状态分类测试，但它只测试了独立公式：

```python
is_short = (
    fwd_dates < 16
    or n_signal < 6
    or n_trade_days < 60
)
```

它没有调用真实 `run_smoke()`，所以没有捕获 `calendar` 未定义。

`limit_status` 测试验证了 replace 行为和去重逻辑，但没有覆盖“短窗口写入不应降低已有宽窗口覆盖”的场景。

### 6.2 新增测试：短窗口 smoke 真实分支

建议新增或扩展：

- `tests/test_smoke_short_window.py`

测试目标：

- mock `run_phase0()` 返回 0。
- mock `run_phase2()` 返回 1。
- mock `loader.factor_coverage()` 返回足够进入 Phase2 但短窗口不足。
- 调用真实 `run_smoke(args)`。
- 断言不抛 `NameError`。
- 断言返回码不是 1。
- 断言输出或内部状态包含 `DATA_INSUFFICIENT`。

如果直接 mock `run_smoke()` 依赖较多，可以先抽出 helper：

```python
def classify_phase2_failure(fwd_dates: int, signal_dates: int, trade_days: int) -> str:
    ...
```

然后：

- helper 单测覆盖公式。
- `run_smoke()` 分支单测至少覆盖 calendar 加载和不抛异常。

### 6.3 新增测试：limit_status 合并写入不回退

建议新增：

- `tests/test_limit_status_merge_write.py`

测试场景：

1. 构造临时 `PanelLoader`。
2. 写入某月 20 个交易日的完整 `limit_status` 模拟数据。
3. 模拟短窗口只抓该月 5 个执行日。
4. 调用新的合并写入 helper。
5. 验证最终该月仍有 20 个交易日。
6. 验证重复为 0。
7. 验证短窗口 5 个日期的数据被更新为新值。

关键断言：

```python
assert result["trade_date"].nunique() == 20
assert result.duplicated(["ts_code", "trade_date"]).sum() == 0
```

### 6.4 新增测试：audit detail 暴露 trade-day coverage

建议扩展 `audit_cache` 测试：

- 构造执行日覆盖 100%、交易日覆盖低的缓存。
- 断言审计不是 FAIL。
- 断言 detail 中包含 `trade-day coverage` 或类似字段。

## 7. 推荐开发步骤

### Step 1：修复 `run_smoke()` calendar 未定义

修改 `run_research.py`：

- 在 `run_smoke()` 初始化阶段加载 `calendar`。
- 替换后续局部 `cal` 变量为统一 `calendar`。
- 保证短窗口 Phase2 failure 分支能够执行到 `DATA_INSUFFICIENT`。

验证：

```powershell
python run_research.py smoke --start 20160101 --end 20160229
```

期望：

- 不出现 `NameError`。
- Phase 0 OK。
- Phase 2 `DATA_INSUFFICIENT` 或 WARN。
- exit code 不为 1。

### Step 2：实现 `limit_status` 月分区合并写入

修改位置：

- `run_research.py` Phase 0 `stk_limit` prefetch 写入段。
- 可选：抽到 `data/panel_loader.py` 或新 helper，便于测试。

建议 helper：

```python
def write_limit_status_merged(loader, lim_df, start_date=None, end_date=None):
    ...
```

验收重点：

- 短窗口写入不会降低已有月覆盖。
- duplicates 为 0。
- 一年 validate 仍 PASS。

### Step 3：增强 `audit_cache.py`

新增 `limit_status` 交易日覆盖展示：

- `cached_dates`
- `expected_trade_dates`
- `trade_day_coverage`
- `exec_coverage`

输出示例：

```text
limit_status PASS 0 dup, cached_dates=67, exec coverage=100.0%, trade-day coverage=27.5%
```

### Step 4：补测试

新增或修改测试：

```powershell
pytest tests/test_output_encoding.py -q
pytest tests/test_limit_status_cache.py -q
pytest tests/test_limit_status_cache_repair.py -q
pytest tests/test_smoke_short_window.py -q
pytest tests/test_limit_status_merge_write.py -q
```

最终跑全量：

```powershell
pytest -q
```

### Step 5：更新 README 和 check_env 建议

修改：

- `README.md`
- `scripts/check_env.py`

把推荐入口从旧一月 smoke 改为一年 validate，并把短窗口 smoke 标为 optional。

同时修复文档乱码。

### Step 6：完整回归

按顺序执行：

```powershell
pytest -q
python scripts/check_env.py
python scripts/audit_cache.py --start 20160101 --end 20161231
python scripts/migrate_factor_cache.py --dry-run
python run_research.py smoke --start 20160101 --end 20160229
python run_research.py phase2 --start 20160101 --end 20161231 --no-recompute
python run_research.py validate --start 20160101 --end 20161231
```

## 8. 验收标准

### 8.1 必须通过

- `pytest -q` 全部通过。
- `python scripts/audit_cache.py --start 20160101 --end 20161231` exit code `0`。
- `python scripts/migrate_factor_cache.py --dry-run` 显示 `0 files would be removed`。
- `python run_research.py smoke --start 20160101 --end 20160229` 不崩溃。
- `python run_research.py phase2 --start 20160101 --end 20161231 --no-recompute` exit code `0`。
- `python run_research.py validate --start 20160101 --end 20161231` exit code `0`。

### 8.2 smoke 验收

两个月 smoke 可接受：

- `Phase 0: OK`
- `Prices adj: OK`
- `Tradable limit: OK`
- `Fwd dups: OK`
- `Phase 2: DATA_INSUFFICIENT`
- `Verdict: WARN`

不可接受：

- `NameError`
- `Phase 0: FAIL`
- `limit_status duplicate`
- `fwd_returns duplicate`
- exit code `1`

### 8.3 缓存验收

在先跑一年 validate 后，再跑短窗口 smoke，再跑一年 audit：

```powershell
python run_research.py validate --start 20160101 --end 20161231
python run_research.py smoke --start 20160101 --end 20160229
python scripts/audit_cache.py --start 20160101 --end 20161231
```

要求：

- `limit_status` duplicates = 0。
- exec coverage 不下降。
- 如果实现了合并写入，cached trade dates 不应因为短窗口 smoke 减少。

### 8.4 文档验收

- README 不再推荐 `20160101-20160131` 作为主 smoke。
- README 包含 `validate` 命令。
- `scripts/check_env.py` suggested command 不再指向旧失败窗口。
- README 中无明显编码乱码。

## 9. 风险与取舍

### 9.1 内存风险

当前环境可用内存约 1.9GB，低于 4GB 建议阈值。一年 validate 已实测能跑，但 10 年全量不建议在低可用内存下直接启动。

建议仍保留 `check_env.py` 的内存 WARN，不要因为一年 validate 通过就降低警戒。

### 9.2 limit_status 覆盖语义

如果项目只要求回测执行日限价检查，则执行日覆盖是合理目标。若未来要做日频交易、日内风控或每日 tradable mask 评估，则必须升级到完整交易日覆盖。

当前建议：

- 短期采用合并写入，避免覆盖回退。
- 审计中明确展示执行日覆盖和交易日覆盖。
- 文档说明当前 `limit_status` 是 execution-date scoped cache。

### 9.3 validate 耗时

一年 validate 实测约 28-29 分钟。CI 或日常开发不应每次都跑完整 validate。

建议分层：

- 每次改动：`pytest -q`。
- 数据链路相关改动：`audit_cache` + 两个月 `smoke`。
- 发布/大改前：一年 `validate`。

## 10. 推荐完成后的最终命令集

日常快速检查：

```powershell
pytest -q
python scripts/audit_cache.py --start 20160101 --end 20161231
```

短窗口数据链路检查：

```powershell
python run_research.py smoke --start 20160101 --end 20160229
```

正式一年全流程验证：

```powershell
python run_research.py validate --start 20160101 --end 20161231
```

不建议直接作为首选入口：

```powershell
python run_research.py all --start 20160101
```

原因：

- `all` 没有 `validate` 的前置审计和汇总报告语义。
- 全量窗口更吃内存和时间。
- 当前推荐验证入口已经是 `validate`。

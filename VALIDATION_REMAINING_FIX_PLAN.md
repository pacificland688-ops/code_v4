# 剩余验证问题修复开发方案

## 1. 结论摘要

本轮审核确认，基础门禁仍然可用，但“剩余问题修复完成”的验收没有通过。

已通过：

```powershell
python scripts\check_env.py
pytest -q
python scripts\audit_cache.py --start 20160101 --end 20161231
python scripts\migrate_factor_cache.py --dry-run
```

当前结果：

- `pytest -q`：`128 passed, 5 warnings`
- 一年缓存审计：`PASS=8 | WARN=0 | FAIL=0`
- factor legacy dry-run：`0 files would be removed across 27 factors`
- 环境检查：无 FAIL，内存低于 4GB 阈值，仍为 WARN

未通过：

```powershell
python run_research.py smoke --start 20160101 --end 20160229
```

失败原因：

```text
NameError: name 'calendar' is not defined
```

同时，两个月 smoke 在失败前已执行 Phase 0，并改变了一年窗口的 `limit_status` 覆盖状态：

```text
smoke 前一年 limit_status: rows=193263, dates=67, dups=0
smoke 后一年 limit_status: rows=252254, dates=88, dups=0, exec coverage=91.8%
```

因此当前不能宣布短窗口 smoke 和缓存不回退问题已经修复。

## 2. 本方案目标

本方案只针对最新审核中仍未通过的内容，目标如下：

1. `python run_research.py smoke --start 20160101 --end 20160229` 不再崩溃。
2. 短窗口 Phase 2 数据不足时，应输出 `DATA_INSUFFICIENT` 或 WARN，而不是异常或 FAIL。
3. 短窗口 smoke/Phase 0 不应降低已有更宽窗口的 `limit_status` 缓存覆盖。
4. `audit_cache.py` 能明确展示 `limit_status` 的执行日覆盖和交易日覆盖。
5. README 和 `scripts/check_env.py` 不再推荐旧的 `20160101-20160131` smoke。
6. 新增测试能覆盖真实失败路径，而不是只覆盖模拟公式。

最终验收命令：

```powershell
pytest -q
python scripts\check_env.py
python scripts\audit_cache.py --start 20160101 --end 20161231
python scripts\migrate_factor_cache.py --dry-run
python run_research.py smoke --start 20160101 --end 20160229
python scripts\audit_cache.py --start 20160101 --end 20161231
python run_research.py phase2 --start 20160101 --end 20161231 --no-recompute
python run_research.py validate --start 20160101 --end 20161231
```

关键新增验收点：

- 两个月 smoke 不崩溃。
- 两个月 smoke 跑完后，一年 `limit_status` 执行日覆盖不下降。
- 一年 audit detail 能显示 trade-day coverage。

## 3. 问题一：短窗口 smoke 的 `calendar` 未定义

### 3.1 现象

命令：

```powershell
python run_research.py smoke --start 20160101 --end 20160229
```

运行到 Phase 2 短窗口数据不足分支时崩溃：

```text
Backtest failed: Insufficient returns. n_periods=3
NameError: name 'calendar' is not defined
```

问题代码位于 `run_research.py` 的 `run_smoke()` 中：

```python
n_signal = len(calendar.weekly_rebalance_dates(start_date, end_date))
n_trade_days = len(calendar.trade_days_between(
    int(start_date), int(end_date)
))
```

但该作用域没有定义 `calendar`。前面的 tradable 检查中定义的是局部变量 `cal`，且只在 `try` 块内部有效。

### 3.2 根因

当前 `run_smoke()` 对交易日历对象的使用不一致：

- tradable 检查中使用 `cal = get_calendar()`
- Phase 2 失败分类中使用 `calendar`
- `calendar` 从未在 `run_smoke()` 外层作用域定义

这说明短窗口 `rc2 == 1` 分支没有被真实测试覆盖。

### 3.3 修复设计

在 `run_smoke()` 初始化阶段统一创建并加载交易日历对象。

推荐修改位置：

```python
from data.panel_loader import MemoryMonitor, get_loader
from data.calendar import get_calendar

monitor = MemoryMonitor(max_memory_gb=8.0, warning_threshold_gb=6.0)
loader = get_loader()
calendar = get_calendar()
calendar.load(start_date=start_date, end_date=end_date)
```

后续所有 `run_smoke()` 内交易日历访问统一使用 `calendar`：

```python
trade_days = calendar.trade_days_between(int(start_date), int(end_date))
n_signal = len(calendar.weekly_rebalance_dates(start_date, end_date))
n_trade_days = len(calendar.trade_days_between(int(start_date), int(end_date)))
```

不要在内部重复定义 `cal`，避免后续再次出现命名分裂。

### 3.4 短窗口状态语义

Phase 2 返回 `1` 后，按窗口长度判断是否属于预期的数据不足：

```python
is_short_window = (
    fwd_cov2["n_dates"] < 16
    or n_signal < 6
    or n_trade_days < 60
)
```

当 `is_short_window=True`：

```python
checks["phase2"] = "DATA_INSUFFICIENT"
warnings.append(...)
```

最终：

- `has_failure` 不应被置为 `True`
- smoke verdict 应为 `WARN`
- exit code 建议为 `0`

如果团队希望 WARN 返回非零，可使用 `2`，但必须同步 `validate`、README 和运维脚本。本轮建议保持现有 `0/1` 语义，降低影响面。

### 3.5 必加测试

新增 `tests/test_smoke_short_window.py`。

测试目标：

- 调用真实 `run_smoke()`，至少覆盖 Phase 2 `rc2 == 1` 分支。
- mock 掉重型数据抓取和回测，避免真实网络/API。
- 断言不抛 `NameError`。
- 断言短窗口被分类为 `DATA_INSUFFICIENT`。

建议测试结构：

```python
def test_smoke_phase2_short_window_data_insufficient(monkeypatch, capsys):
    from run_research import run_smoke

    args = argparse.Namespace(
        start="20160101",
        end="20160229",
        recompute=False,
        no_recompute=False,
        dry_run=False,
        top_n=50,
        frequency="weekly",
    )

    monkeypatch.setattr("run_research.run_phase0", lambda args: 0)
    monkeypatch.setattr("run_research.run_phase2", lambda args: 1)
    # mock loader.factor_coverage, loader.query, calendar methods 等

    rc = run_smoke(args)
    assert rc == 0
    assert "DATA_INSUFFICIENT" in capsys.readouterr().out
```

如果直接 mock `run_smoke()` 依赖成本太高，可以先抽出 helper：

```python
def classify_phase2_failure(fwd_dates: int, signal_dates: int, trade_days: int) -> bool:
    return fwd_dates < 16 or signal_dates < 6 or trade_days < 60
```

但仍必须有一个测试覆盖真实 `run_smoke()` 访问 calendar 的路径。

## 4. 问题二：短窗口 Phase 0 会改变一年 `limit_status` 覆盖

### 4.1 现象

短窗口 smoke 运行前后，`limit_status` 覆盖发生变化。

运行前：

```text
20160101-20161231 rows=193263, dates=67, dups=0
```

运行两个月 smoke 后：

```text
20160101-20161231 rows=252254, dates=88, dups=0
month dates
1     20
2     16
3      1
4      5
...
12     6
```

一年审计仍然 PASS，但执行日覆盖降为：

```text
limit_status PASS 0 dup, 88 dates, exec coverage=91.8%
```

这说明短窗口 Phase 0 会改写生产缓存形态，且现有 audit 没有把该风险暴露为失败或警告。

### 4.2 根因

`run_phase0()` 中 `stk_limit` 预取逻辑按月写入：

```python
_ldr.write_data(
    lim_month,
    "limit_status",
    partition_cols=["year", "month"],
    dedupe_keys=["ts_code", "trade_date"],
    replace_partitions=True,
)
```

当前 `lim_month` 只包含：

- Phase 2 执行日
- 少量 sample days

但 `replace_partitions=True` 会替换整个 `year/month` 分区。因此短窗口运行会用局部采样数据覆盖该月已有完整或更宽覆盖数据。

### 4.3 修复原则

`limit_status` 写入应满足：

- 不产生重复 `(ts_code, trade_date)`
- 新数据优先于旧数据
- 短窗口写入不能删除同月已有其他日期
- 保持按 `year/month` 分区
- 审计能区分“执行日覆盖”和“完整交易日覆盖”

### 4.4 推荐实现：合并写入 helper

新增 helper，建议放在 `run_research.py` 或 `data/panel_loader.py`。

更推荐放在 `data/panel_loader.py` 或新模块 `data/limit_status_cache.py`，便于单元测试。

接口建议：

```python
def write_limit_status_merged(loader, lim_df: pd.DataFrame) -> int:
    """
    Merge new limit_status rows into existing year/month partitions.

    Rules:
    - derive year/month from trade_date
    - for each affected month, read existing partition data
    - concat existing + new month data
    - drop_duplicates(["ts_code", "trade_date"], keep="last")
    - replace the affected month partition with merged data
    - return number of rows written
    """
```

核心伪代码：

```python
def _normalize_limit_status_df(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["trade_date"] = df["trade_date"].astype(int)
    df["year"] = df["trade_date"] // 10000
    df["month"] = (df["trade_date"] % 10000) // 100
    return df


def _month_bounds(year: int, month: int) -> tuple[str, str]:
    start = f"{year}{month:02d}01"
    if month == 12:
        end = f"{year}1231"
    else:
        next_month = datetime(year, month + 1, 1)
        end_dt = next_month - timedelta(days=1)
        end = end_dt.strftime("%Y%m%d")
    return start, end


def write_limit_status_merged(loader, lim_df: pd.DataFrame) -> int:
    if lim_df.empty:
        return 0

    lim_df = _normalize_limit_status_df(lim_df)
    total_written = 0

    for (year, month), new_month in lim_df.groupby(["year", "month"]):
        month_start, month_end = _month_bounds(int(year), int(month))
        existing = loader.query(
            "limit_status",
            start_date=month_start,
            end_date=month_end,
        )

        if not existing.empty:
            existing = _normalize_limit_status_df(existing)
            combined = pd.concat([existing, new_month], ignore_index=True)
        else:
            combined = new_month.copy()

        combined = combined.drop_duplicates(["ts_code", "trade_date"], keep="last")
        combined = _normalize_limit_status_df(combined)

        loader.write_data(
            combined,
            "limit_status",
            partition_cols=["year", "month"],
            dedupe_keys=["ts_code", "trade_date"],
            replace_partitions=True,
        )
        total_written += len(combined)

    return total_written
```

在 `run_phase0()` 中替换直接写入：

```python
n_written = write_limit_status_merged(_ldr, lim_month)
n_lim_rows += len(lim_month)
logger.info(f"  limit_status merged write: input={len(lim_month)}, partition_rows={n_written}")
```

注意：

- `n_lim_rows` 建议统计本次新抓取行数，而不是合并后分区总行数。
- 日志中应区分 `new_rows` 和 `written_rows`，避免误解。
- 不要把 `prices_adj` 的 `replace_partitions=True` 改掉；本问题只针对 `limit_status`。

### 4.5 可选实现：完整月写入

如果希望 `limit_status` 缓存达到完整交易日覆盖，可改为对受影响月份抓完整交易日，再整月 replace。

优点：

- 分区语义简单，audit 可以严格要求 trade-day coverage。

缺点：

- API 调用量更大。
- smoke 运行更慢。
- 更依赖 Tushare 限频。

当前建议优先采用合并写入方案，保留执行日缓存策略，但避免覆盖回退。

### 4.6 必加测试：缓存不回退

新增 `tests/test_limit_status_merge_write.py`。

测试场景：

1. 使用临时 `PanelLoader`。
2. 写入 2016 年 1 月 20 个交易日的完整模拟 `limit_status`。
3. 构造短窗口新数据，只包含 5 个日期。
4. 调用 `write_limit_status_merged()`。
5. 读取 2016 年 1 月。
6. 断言日期数仍为 20。
7. 断言重复为 0。
8. 断言短窗口 5 个日期的数据已用新值覆盖。

关键断言：

```python
assert result["trade_date"].nunique() == 20
assert result.duplicated(["ts_code", "trade_date"]).sum() == 0
```

再增加跨月测试：

- 输入同时包含 1 月和 2 月数据。
- 只影响这两个月。
- 其他月份分区不被删除。

## 5. 问题三：`audit_cache.py` 可观测性不足

### 5.1 当前问题

`audit_cache.py` 当前只输出：

```text
limit_status PASS 0 dup, 88 dates, exec coverage=91.8%
```

这无法回答：

- 缓存覆盖了多少交易日？
- 是否只是执行日/样本日缓存？
- 短窗口运行后 trade-day coverage 是否下降？

### 5.2 修复设计

增强 `limit_status` 审计指标。

新增计算：

```python
trade_days = set(cal.trade_days_between(int(args.start), int(args.end)))
cached_dates = set(lim_df["trade_date"].astype(int).unique())
trade_day_coverage = len(cached_dates & trade_days) / len(trade_days)
```

输出 detail：

```text
0 dup, cached_dates=88/244, exec coverage=91.8%, trade-day coverage=36.1%
```

状态建议：

- `FAIL`：duplicates > 0
- `FAIL`：exec coverage < 80%
- `PASS`：duplicates = 0 且 exec coverage >= 80%
- `WARN`：trade-day coverage < 90%，但 exec coverage PASS，并明确说明“execution-date scoped cache”

如果担心一年 audit 因 trade-day coverage 变 WARN 影响现有 `validate`，可以提供参数：

```powershell
python scripts\audit_cache.py --start 20160101 --end 20161231 --limit-status-mode exec
python scripts\audit_cache.py --start 20160101 --end 20161231 --limit-status-mode full-calendar
```

默认建议：

- 当前项目默认 `exec`
- detail 始终显示 trade-day coverage
- `full-calendar` 模式下 trade-day coverage < 90% 为 FAIL

### 5.3 测试

新增或扩展 audit 测试：

- 构造 `limit_status` 执行日覆盖 100%、交易日覆盖 20% 的临时缓存。
- 断言默认模式不 FAIL。
- 断言输出 detail 包含 `trade-day coverage`。
- 在 `full-calendar` 模式下断言 FAIL。

## 6. 问题四：README 和 check_env 仍推荐旧命令

### 6.1 当前问题

README 仍推荐：

```powershell
python run_research.py smoke --start 20160101 --end 20160131
```

`scripts/check_env.py` 仍输出：

```text
SAFE: python run_research.py smoke --start 20160101 --end 20160131
Suggested next command:
  python run_research.py smoke --start 20160101 --end 20160131
```

该命令属于已知不可靠路径，不应再作为推荐入口。

### 6.2 README 修改方案

Quick Start 改为：

```powershell
# 1. Check environment
python scripts\check_env.py

# 2. Audit cache for the validation window
python scripts\audit_cache.py --start 20160101 --end 20161231

# 3. Run one-year full validation
python run_research.py validate --start 20160101 --end 20161231
```

新增 optional short smoke：

```powershell
# Optional: short-window smoke.
# Phase 2 may be DATA_INSUFFICIENT because the window is intentionally short.
python run_research.py smoke --start 20160101 --end 20160229
```

Phase Reference 增加 `validate`：

```markdown
| validate | `python run_research.py validate --start YYYYMMDD --end YYYYMMDD` | Recommended end-to-end validation with env check, cache audit, Phase 0-2, smoke, and Phase 3-5 dry-run |
```

同时修复 README 中乱码，例如：

- `鈥?`
- `鈫?`
- `脳`

### 6.3 check_env 修改方案

内存 WARN 时输出建议改为：

```text
- SAFE: dry-run, pytest, cache audit
- OPTIONAL: python run_research.py smoke --start 20160101 --end 20160229
- RECOMMENDED: python run_research.py validate --start 20160101 --end 20161231
- CAUTION: avoid 10yr full runs while available memory is below 4GB
```

内存 OK 时输出：

```text
- You can run: python run_research.py validate --start 20160101 --end 20161231
- Optional short smoke: python run_research.py smoke --start 20160101 --end 20160229
- Full range: python run_research.py all --start 20160101
```

Suggested next command：

```text
python scripts/audit_cache.py --start 20160101 --end 20161231
python run_research.py validate --start 20160101 --end 20161231
```

如果只允许一条 suggested command，优先推荐：

```powershell
python run_research.py validate --start 20160101 --end 20161231
```

## 7. 问题五：测试仍存在“结构性占位”而非真实验证

### 7.1 当前问题

已有测试中存在以下模式：

- 注释说“由代码审查验证”
- 只测试公式，不触发真实函数分支
- try/except 吞掉异常或没有断言真实行为

例如短窗口 smoke 当前仍然可以通过测试，但真实命令崩溃。这说明测试覆盖不足。

### 7.2 测试补强原则

每个修复点必须有至少一个会在旧代码上失败、新代码上通过的测试。

### 7.3 必补测试清单

#### 测试 A：真实 run_smoke 短窗口分支

文件：

```text
tests/test_smoke_short_window.py
```

旧代码预期失败：

- `NameError: calendar is not defined`

新代码预期：

- 不抛异常
- `Phase 2: DATA_INSUFFICIENT`
- 返回码为 `0` 或约定的 WARN 码

#### 测试 B：limit_status 合并写入不减少日期数

文件：

```text
tests/test_limit_status_merge_write.py
```

旧代码预期失败：

- `replace_partitions=True` 后日期数从 20 降为 5

新代码预期：

- 日期数保持 20
- 重复为 0
- 新数据覆盖旧数据

#### 测试 C：audit 输出 trade-day coverage

文件：

```text
tests/test_audit_cache_limit_status.py
```

旧代码预期失败：

- detail 不包含 trade-day coverage

新代码预期：

- detail 中包含 exec coverage 和 trade-day coverage

#### 测试 D：文档建议命令不包含旧窗口

文件：

```text
tests/test_docs_commands.py
```

断言：

```python
assert "20160131" not in readme_quick_start
assert "validate --start 20160101 --end 20161231" in readme
```

如果不想测试文档，可至少人工验收，但建议加入测试防回退。

## 8. 推荐实施顺序

### Step 1：修复 run_smoke 的 calendar

改动文件：

- `run_research.py`

完成后先跑：

```powershell
pytest tests\test_smoke_phase2_readonly.py -q
python run_research.py smoke --start 20160101 --end 20160229
```

预期：

- smoke 不抛 `NameError`
- 短窗口 Phase 2 是 `DATA_INSUFFICIENT`

### Step 2：实现 limit_status 合并写入

改动文件建议：

- `data/limit_status_cache.py` 或 `data/panel_loader.py`
- `run_research.py`

完成后跑：

```powershell
pytest tests\test_limit_status_cache.py tests\test_limit_status_cache_repair.py -q
pytest tests\test_limit_status_merge_write.py -q
```

再跑真实回归：

```powershell
python run_research.py validate --start 20160101 --end 20161231
python scripts\audit_cache.py --start 20160101 --end 20161231
python run_research.py smoke --start 20160101 --end 20160229
python scripts\audit_cache.py --start 20160101 --end 20161231
```

比较 smoke 前后一年的 `limit_status`：

- duplicates 必须保持 0
- exec coverage 不得下降
- cached dates 不得因短窗口减少

### Step 3：增强 audit_cache 输出

改动文件：

- `scripts/audit_cache.py`

完成后跑：

```powershell
python scripts\audit_cache.py --start 20160101 --end 20161231
```

预期 detail 包含：

```text
exec coverage=...
trade-day coverage=...
```

### Step 4：更新 README 和 check_env

改动文件：

- `README.md`
- `scripts/check_env.py`

完成后跑：

```powershell
python scripts\check_env.py
```

人工确认：

- 不再输出 `20160101 --end 20160131`
- 推荐 `validate --start 20160101 --end 20161231`

### Step 5：补测试并全量回归

最终：

```powershell
pytest -q
python scripts\check_env.py
python scripts\audit_cache.py --start 20160101 --end 20161231
python scripts\migrate_factor_cache.py --dry-run
python run_research.py smoke --start 20160101 --end 20160229
python scripts\audit_cache.py --start 20160101 --end 20161231
python run_research.py phase2 --start 20160101 --end 20161231 --no-recompute
python run_research.py validate --start 20160101 --end 20161231
```

## 9. 验收标准

### 9.1 基础验收

必须全部满足：

- `pytest -q` 通过
- `check_env.py` 无 FAIL
- 一年 `audit_cache` 无 FAIL
- factor migration dry-run 为 0

### 9.2 短窗口 smoke 验收

命令：

```powershell
python run_research.py smoke --start 20160101 --end 20160229
```

必须满足：

- 不抛异常
- 不出现 `NameError`
- `Phase 0: OK`
- `Tradable limit: OK`
- `Fwd dups: OK`
- `Phase 2: DATA_INSUFFICIENT` 或 `Phase 2: OK`
- 若 Phase 2 数据不足，verdict 应为 WARN，而不是 FAIL
- exit code 不为 `1`

### 9.3 缓存不回退验收

命令序列：

```powershell
python run_research.py validate --start 20160101 --end 20161231
python scripts\audit_cache.py --start 20160101 --end 20161231
python run_research.py smoke --start 20160101 --end 20160229
python scripts\audit_cache.py --start 20160101 --end 20161231
```

要求：

- smoke 后一年 `limit_status` duplicates 仍为 0
- smoke 后一年 exec coverage 不低于 smoke 前
- 如果实现合并写入，smoke 后 cached_dates 不应低于 smoke 前
- audit detail 显示 trade-day coverage

### 9.4 文档验收

必须满足：

- README Quick Start 不再推荐 `20160101-20160131`
- README 包含 `validate --start 20160101 --end 20161231`
- `check_env.py` suggested command 不再推荐旧一月 smoke
- README 无明显乱码

### 9.5 validate 验收

命令：

```powershell
python run_research.py validate --start 20160101 --end 20161231
```

必须满足：

- exit code `0`
- `outputs/validation_report.md` 存在
- `Overall: PASS`

## 10. 暂不建议做的事

在上述修复完成前，不建议：

- 把短窗口 smoke 纳入“已通过”结论。
- 直接跑 10 年全量 `all --start 20160101` 作为首选验证入口。
- 继续推荐 `20160101-20160131` smoke。
- 只跑一年 validate 就认为缓存不回退问题已解决，因为一年 validate 会重写缓存并掩盖短窗口污染。

## 11. 开发完成后的审核口径

修复完成后，审核时重点看三件事：

1. 两个月 smoke 是否真的不崩。
2. 两个月 smoke 是否不再降低一年 `limit_status` 覆盖。
3. 文档和 check_env 是否不再把用户带向旧失败命令。

如果这三项未通过，即使 `pytest` 和一年 `validate` 通过，也不能认定本轮剩余修复完成。

# 策略诊断全流程验收遗留问题修复开发方案

生成日期：2026-06-13
修复对象：终端 stdout 编码 + warmup 测试强度

## 问题 1：Windows GBK 控制台 UnicodeEncodeError

`artifact consistency check` 打印 `✅`/`❌`/`⚠️`，在默认 PowerShell/GBK 下触发 `UnicodeEncodeError`，退出码=1。

**修复**：stdout 统一改为 ASCII 安全格式（`[OK]`/`[FAIL]`/`[WARN]`），不改 markdown 报告。

## 问题 2：warmup 测试断言不够强

`test_oracle_marks_unmapped_signal_dates_out_of_window` 未强制断言：
- `OUT_OF_BACKTEST_WINDOW` 行非空
- warmup `signal_date` 存在于排除行中
- warmup `signal_date` 不存在于 OK 行

**修复**：三条断言全部加入，回归 `pe_map.get(signal_date, 0)` 时测试会失败。

## 验证

```text
python -m pytest -q tests/test_strategy_alpha_failure_diagnosis.py → 31 passed
python -m pytest -q [4 files] → 68 passed
全流程 python scripts/strategy_alpha_failure_diagnosis.py → exit 0

[OK] All expected CSV outputs exist
[OK] Reports exist
[OK] Reports have no template artifacts

OK period_end=0: 0, OK signal_date=0: 0
hindsight_oracle period_end=0: 0
All NO_GO: True
```

# Factor Quality Rebuild V4 Diagnostics Contract Fix Plan

## 1. 背景与目标

`factor_quality_rebuild_v4` 主流程已经通过完整重跑和产品级校验：

- Full V4 rebuild 成功完成。
- `validate_factor_quality_outputs.py --require-run-manifest --max-output-age-minutes 120` 已通过。
- 最新候选池合法输出 `NO_ALPHA_SOURCE_FOUND`。
- `log_market_cap_cs` 已正确进入 `support_factors.neutralizers`。

但审核仍发现 3 个诊断契约缺口：

1. `run_manifest.json` 在 `SUCCESS` 状态下丢失 `start_time`。
2. 无错误运行时没有创建 `run_errors.csv`。
3. `run_progress.csv`、`run_stage_timings.csv` 被发布到正式输出目录根层，和诊断文件保留在 `_run_<run_id>` 的设计不一致。

本次目标是补齐诊断契约，使 run manifest 和诊断文件真正可追溯、结构稳定、边界清晰。

## 2. 修复范围

本次只修改 V4 factor quality rebuild 的诊断与发布契约：

- 修复 `RunDiagnostics` manifest 生命周期。
- 启动时创建 header-only 诊断 CSV。
- 调整 publish 逻辑，避免把诊断 CSV 发布到 out-dir 根层。
- 增强 validator 对 manifest 字段完整性的校验。
- 补充对应单元测试和 smoke/full 回归验证。

不修改：

- factor gate 阈值。
- 因子计算逻辑。
- neutralization 逻辑。
- capacity / rolling / correlation 逻辑。
- 当前 `NO_ALPHA_SOURCE_FOUND` 结论。

## 3. 具体开发方案

### 3.1 修复 run_manifest 的 start_time 保留逻辑

当前问题：

- `RunDiagnostics.__init__()` 写入 `RUNNING` manifest 时有 `start_time`。
- `mark_success()` / `mark_failed()` 调用 `_write_manifest()` 重写文件。
- `_write_manifest()` 在非 `RUNNING` 状态下把 `start_time` 写成空字符串。

修复方式：

1. 在 `RunDiagnostics.__init__()` 中保存实例级字段：

```python
self.start_time = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
```

2. `_write_manifest()` 始终写入同一个 `self.start_time`：

```python
"start_time": self.start_time
```

3. `mark_success()` / `mark_failed()` 只更新：

- `status`
- `end_time`

4. `run_manifest.json` 必须满足：

```json
{
  "status": "SUCCESS",
  "start_time": "2026-06-18T16:28:43",
  "end_time": "2026-06-18T16:56:46"
}
```

5. `end_time >= start_time`，格式固定为 ISO-like `%Y-%m-%dT%H:%M:%S`。

### 3.2 启动时创建 header-only run_errors.csv

当前问题：

- `run_progress.csv` 和 `run_stage_timings.csv` 在有记录时创建。
- `run_errors.csv` 只有发生错误时创建。
- 无错误运行下文件不存在，不符合“诊断文件启动即创建”的契约。

修复方式：

在 `RunDiagnostics.__init__()` 中初始化 3 个 CSV：

- `run_progress.csv`
- `run_stage_timings.csv`
- `run_errors.csv`

实现建议：

```python
_write_csv_safe(self._progress_path, [], RUN_PROGRESS_COLUMNS)
_write_csv_safe(self._timings_path, [], RUN_STAGE_TIMINGS_COLUMNS)
_write_csv_safe(self._errors_path, [], RUN_ERRORS_COLUMNS)
```

要求：

- 无错误运行时 `run_errors.csv` 存在，只有 header，0 行。
- 有错误运行时 append 到同一个文件，不重复 header。
- progress/timings 也应从 header-only 文件开始 append，不破坏现有逻辑。

### 3.3 调整诊断 CSV 发布边界

当前问题：

- 发布阶段使用 `for src in run_dir.glob("*.csv")`。
- 这会把所有 CSV 发布到 out-dir 根层。
- 结果 `run_progress.csv`、`run_stage_timings.csv` 也出现在正式输出目录根层。

目标边界：

- 正式产物发布到 out-dir 根层。
- 诊断文件保留在 `_run_<run_id>` 内。

正式产物白名单：

```python
PUBLISH_CSVS = [
    "factor_input_audit.csv",
    "factor_direction_audit.csv",
    "factor_alignment_audit.csv",
    "factor_ic_by_year.csv",
    "factor_quantile_returns.csv",
    "factor_turnover_cost.csv",
    "factor_neutralization_diagnostic.csv",
    "factor_ic_trend.csv",
    "factor_rolling_window_gate.csv",
    "factor_correlation_cluster.csv",
    "factor_capacity_audit.csv",
    "factor_regime_breakdown.csv",
    "factor_quality_gate.csv",
]
```

发布逻辑改为：

```python
for name in PUBLISH_CSVS:
    src = run_dir / name
    if src.exists():
        shutil.copy2(src, out_dir / name)
```

不得发布到根层：

- `run_progress.csv`
- `run_stage_timings.csv`
- `run_errors.csv`
- partial CSV

保留发布：

- `factor_candidate_pool.yaml`
- `profile.json`
- report 到 `--out-doc`

可选：

- `profile.json` 仍可发布到 out-dir 根层，因为它是用户显式通过 `--profile-out` 指定的正式诊断摘要。

### 3.4 增强 validator 的 manifest 字段校验

修改 `scripts/validate_factor_quality_outputs.py` 的 `check_run_manifest()`：

新增校验：

- `run_manifest.json` 必须包含：
  - `run_id`
  - `config_path`
  - `config_sha256`
  - `seed`
  - `factor_count`
  - `out_dir`
  - `out_doc`
  - `start_time`
  - `end_time`
  - `status`
- `status == SUCCESS` 时：
  - `start_time` 非空。
  - `end_time` 非空。
  - `end_time >= start_time`。
- `config_sha256` 必须等于当前 config 文件 sha256 的前 16 位。

新增诊断文件存在性校验：

如果启用 `--require-run-manifest`，同时检查最新 `_run_<run_id>` 下存在：

- `run_progress.csv`
- `run_stage_timings.csv`
- `run_errors.csv`

并且三者可被 pandas 读取。

新增根目录污染校验：

如果启用 `--require-run-manifest`，out-dir 根层不应存在：

- `run_progress.csv`
- `run_stage_timings.csv`
- `run_errors.csv`

若存在，validator 应 FAIL，提示：

```text
diagnostic CSV leaked to output root: run_progress.csv
```

### 3.5 处理历史遗留根层诊断 CSV

由于当前已有历史运行可能在根层留下：

- `run_progress.csv`
- `run_stage_timings.csv`

修复后第一次正式发布前需要清理这些遗留文件。

推荐做法：

- 不在脚本中删除任意旧文件。
- 在 full rerun 验收前手动删除 out-dir 根层的诊断 CSV。
- 或在发布阶段仅删除已知诊断 CSV：

```python
for name in ["run_progress.csv", "run_stage_timings.csv", "run_errors.csv"]:
    stale = out_dir / name
    if stale.exists():
        stale.unlink()
```

推荐采用第二种方式，因为这是明确的历史污染清理，不会影响正式产物。

## 4. 测试方案

### 4.1 单元测试

新增或更新测试：

1. `test_run_manifest_preserves_start_time_on_success`
   - 初始化 `RunDiagnostics`。
   - 调用 `mark_success()`。
   - 断言 `start_time` 非空。
   - 断言 `end_time` 非空。
   - 断言 `end_time >= start_time`。

2. `test_run_manifest_preserves_start_time_on_failure`
   - 调用 `mark_failed()`。
   - 断言 `status == FAILED`。
   - 断言 `start_time` 非空。

3. `test_run_errors_created_header_only_on_start`
   - 初始化 `RunDiagnostics`。
   - 断言 `run_errors.csv` 存在。
   - 用 pandas 读取成功。
   - 断言行数为 0，columns 等于 `RUN_ERRORS_COLUMNS`。

4. `test_publish_does_not_copy_diagnostic_csv_to_root`
   - 构造 run_dir，包含正式 CSV 和诊断 CSV。
   - 调用发布 helper。
   - 断言正式 CSV 被复制。
   - 断言诊断 CSV 不在 out-dir 根层。

5. `test_validator_fails_empty_manifest_start_time`
   - 构造 `status=SUCCESS` 且 `start_time=""` 的 manifest。
   - 调用 `check_run_manifest()`。
   - 断言返回 issue。

6. `test_validator_fails_diagnostic_csv_leaked_to_root`
   - out-dir 根层放置 `run_progress.csv`。
   - 调用 require-run-manifest 校验。
   - 断言 FAIL。

### 4.2 回归测试

运行：

```bash
python -m pytest tests/test_factor_quality_rebuild.py tests/test_factor_quality_output_validation.py tests/test_v4_config_validation.py -q
```

验收：

- 全部通过。
- pandas deprecation warnings 暂不阻断。

### 4.3 Smoke 验收

运行：

```bash
python scripts/factor_quality_rebuild.py --config configs/factor_quality_rebuild_v4.yaml --out-dir outputs/analysis/factor_quality_rebuild_v4_smoke --out-doc docs/factor_quality_rebuild_v4_smoke_report.md --factor-include reversal_5_cs,volatility_60_cs,log_market_cap_cs --skip-capacity --skip-regime --profile-out outputs/analysis/factor_quality_rebuild_v4_smoke/profile.json
python scripts/validate_factor_quality_outputs.py --out-dir outputs/analysis/factor_quality_rebuild_v4_smoke --config configs/factor_quality_rebuild_v4.yaml --require-run-manifest --max-output-age-minutes 120
```

验收：

- validator 通过。
- 最新 `_run_* / run_manifest.json` 中 `start_time` 非空。
- 最新 `_run_* / run_errors.csv` 存在且可读。
- out-dir 根层不存在 `run_progress.csv`、`run_stage_timings.csv`、`run_errors.csv`。

### 4.4 Full V4 验收

运行：

```bash
python scripts/factor_quality_rebuild.py --config configs/factor_quality_rebuild_v4.yaml --out-dir outputs/analysis/factor_quality_rebuild_v4 --out-doc docs/factor_quality_rebuild_v4_report.md --profile-out outputs/analysis/factor_quality_rebuild_v4/profile.json
python scripts/validate_factor_quality_outputs.py --out-dir outputs/analysis/factor_quality_rebuild_v4 --config configs/factor_quality_rebuild_v4.yaml --require-run-manifest --max-output-age-minutes 120
```

验收：

- rebuild 退出码为 0。
- validator 通过。
- `run_manifest.status == SUCCESS`。
- `start_time`、`end_time` 非空且顺序正确。
- `run_progress.csv`、`run_stage_timings.csv`、`run_errors.csv` 只存在于最新 `_run_*` 目录内。
- 根层正式产物完整。

## 5. 验收标准

本次修复完成的判定标准：

- `run_manifest.json` 在 `SUCCESS` / `FAILED` 状态下都保留 `start_time`。
- 无错误运行也生成 header-only `run_errors.csv`。
- 诊断 CSV 不再泄漏到 out-dir 根层。
- validator 在 `--require-run-manifest` 下能捕获：
  - 空 `start_time`
  - 缺失诊断 CSV
  - 根层诊断 CSV 污染
- smoke 和 full V4 验收均通过。

## 6. 非目标

本次不处理：

- full rebuild 性能优化。
- pandas deprecation warning。
- factor alpha 质量改善。
- 基本面数据缺失。
- 策略层或 sleeve 层重建。


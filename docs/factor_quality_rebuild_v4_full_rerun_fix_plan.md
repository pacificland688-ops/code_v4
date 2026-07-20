# Factor Quality Rebuild V4 Full Rerun Fix Plan

## 1. 背景与目标

本方案用于修复 `factor_quality_rebuild_v4` 的产品级验收问题。上一轮审核显示，配置层和单测层已经基本修复，但完整重跑仍未通过：

- `configs/factor_quality_rebuild_v4.yaml` 已修正 `rolling_windows` 为 `start/end` schema。
- `log_market_cap_cs` 已正确声明为 `role: neutralizer`。
- 相关单测已通过：`89 passed`。
- 但 `outputs/analysis/factor_quality_rebuild_v4` 当前为空，validator 失败。
- 完整执行 `scripts/factor_quality_rebuild.py --config configs/factor_quality_rebuild_v4.yaml ...` 运行约 15 分钟后未生成任何验收产物。

本次目标不是继续调因子或策略，而是让 V4 factor quality pipeline 具备可复现、可诊断、可验收的完整重跑能力。

最终验收命令：

```bash
python scripts/factor_quality_rebuild.py --config configs/factor_quality_rebuild_v4.yaml --out-dir outputs/analysis/factor_quality_rebuild_v4 --out-doc docs/factor_quality_rebuild_v4_report.md
python scripts/validate_factor_quality_outputs.py --out-dir outputs/analysis/factor_quality_rebuild_v4 --config configs/factor_quality_rebuild_v4.yaml
```

最终验收标准：

- rebuild 命令退出码为 `0`。
- validator 输出 `VALIDATION PASSED: 8/8 checks OK`。
- `outputs/analysis/factor_quality_rebuild_v4` 包含全部必需 CSV 和 `factor_candidate_pool.yaml`。
- `docs/factor_quality_rebuild_v4_report.md` 为本轮重跑生成的新报告。
- `factor_candidate_pool.yaml` 中 `log_market_cap_cs` 只出现在 `support_factors.neutralizers`。

## 2. 问题拆解

### 2.1 当前阻塞

当前阻塞不是 rolling schema，也不是 neutralizer 配置，而是完整重跑不可验收：

- 输出目录无文件。
- validator 因文件缺失失败。
- 旧报告仍是历史产物，不能证明当前代码可复现。
- 脚本目前在末尾统一写盘；长时间运行中途失败或超时会留下空目录，缺少阶段性诊断产物。

### 2.2 高风险原因假设

需要按优先级验证以下原因：

1. **V4 因子数量过大导致运行时间不可控**
   - 当前 V4 配置约 66 个因子。
   - 每个非空因子会计算 raw/neutral IC、分位组合、真实换手、IC trend、neutralization。
   - 末尾还会执行 rolling、capacity、correlation、gate 和报告生成。

2. **脚本末尾统一落盘导致不可诊断**
   - 当前只有全部阶段跑完后才写 CSV。
   - 任一慢阶段或异常退出都会导致 out-dir 为空。

3. **部分阶段复杂度过高**
   - `_compute_real_turnover_cost`
   - `_compute_quantile_portfolios`
   - `_compute_capacity_audit`
   - `_compute_correlation_clusters`
   - 这些阶段在 66 因子规模下可能成为瓶颈。

4. **缺少 per-factor 进度日志落盘**
   - 控制台输出一旦超时中断，不易判断卡在哪个 factor 或阶段。
   - 当前没有 run manifest、stage progress 或 checkpoint。

## 3. 开发方案

### 3.1 增加运行诊断与阶段进度落盘

修改 `scripts/factor_quality_rebuild.py`，新增 run-level 诊断文件：

- `run_manifest.json`
- `run_progress.csv`
- `run_stage_timings.csv`
- `run_errors.csv`

`run_manifest.json` 字段：

- `run_id`
- `config_path`
- `config_sha256`
- `seed`
- `start_time`
- `end_time`
- `status`: `RUNNING / SUCCESS / FAILED`
- `factor_count`
- `out_dir`
- `out_doc`

`run_progress.csv` 每处理完一个 factor 追加一行：

- `run_id`
- `factor`
- `factor_index`
- `stage`
- `status`
- `elapsed_sec`
- `raw_rows`
- `aligned_rows`
- `message`

`run_stage_timings.csv` 每个大阶段结束追加一行：

- `run_id`
- `stage`
- `elapsed_sec`
- `status`
- `rows_out`

`run_errors.csv` 在捕获异常时追加：

- `run_id`
- `stage`
- `factor`
- `error_type`
- `error_message`
- `traceback`

实现要求：

- 这些诊断文件必须在脚本启动后立即创建。
- 每个 factor 完成后立即 flush 到磁盘。
- 顶层 `main()` 捕获异常并写入 `run_manifest.status=FAILED` 后再抛出或返回非零退出码。
- 正常结束时写入 `run_manifest.status=SUCCESS`。

### 3.2 将最终产物写入改为安全原子输出

避免半成品污染正式目录：

- 新增临时目录：`<out-dir>/_run_<run_id>/`
- 所有 CSV/YAML/report 先写入临时目录。
- 全部生成并通过内部完整性检查后，再复制或移动到 `<out-dir>` 根目录。
- 若运行失败，保留 `_run_<run_id>` 诊断目录，但不覆盖旧的正式产物。

目录结构：

```text
outputs/analysis/factor_quality_rebuild_v4/
  factor_quality_gate.csv
  factor_candidate_pool.yaml
  ...
  _run_20260618_123456/
    run_manifest.json
    run_progress.csv
    run_stage_timings.csv
    run_errors.csv
    partial/
```

如果正式目录当前为空，失败时仍至少保留 `_run_*` 诊断目录，便于定位。

### 3.3 增加阶段性 partial CSV checkpoint

每个 factor 处理完成后，将可增量落盘的数据写入 `_run_<run_id>/partial/`：

- `factor_input_audit.partial.csv`
- `factor_direction_audit.partial.csv`
- `factor_alignment_audit.partial.csv`
- `factor_ic_by_year.partial.csv`
- `factor_quantile_returns.partial.csv`
- `factor_turnover_cost.partial.csv`
- `factor_neutralization_diagnostic.partial.csv`
- `factor_ic_trend.partial.csv`

要求：

- partial CSV 必须有固定 header。
- 即使 factor 后续阶段失败，也能看到已完成 factor 的结果。
- 最终正式 CSV 仍使用完整聚合结果生成。

### 3.4 增加 smoke 模式用于快速验收流程

为 `scripts/factor_quality_rebuild.py` 增加参数：

```bash
--factor-limit N
--factor-include factor_a,factor_b
--skip-capacity
--skip-regime
--skip-correlation
```

用途：

- 快速验证 V4 配置、rolling schema、neutralizer 契约和 CSV 写盘链路。
- 不作为最终 alpha 结论，只作为 pipeline smoke test。

smoke 验收命令：

```bash
python scripts/factor_quality_rebuild.py --config configs/factor_quality_rebuild_v4.yaml --out-dir outputs/analysis/factor_quality_rebuild_v4_smoke --out-doc docs/factor_quality_rebuild_v4_smoke_report.md --factor-include reversal_5_cs,volatility_60_cs,log_market_cap_cs --skip-capacity --skip-regime
python scripts/validate_factor_quality_outputs.py --out-dir outputs/analysis/factor_quality_rebuild_v4_smoke --config configs/factor_quality_rebuild_v4.yaml
```

注意：

- 如果 validator 对 smoke 输出要求所有 capacity 数据存在，需要支持 header-only CSV。
- smoke 通过不代表 full rerun 通过。

### 3.5 定位性能瓶颈并设置阶段超时告警

在以下函数周围增加计时：

- `_load_factor_cache_raw`
- `_clean_factor_panel`
- `_build_aligned_panel`
- `_neutralize_by_mcap`
- `_audit_factor_direction`
- `_compute_ic_by_year`
- `_compute_quantile_portfolios`
- `_compute_real_turnover_cost`
- `_compute_quantile_returns`
- `_compute_ic_trend`
- `_compute_rolling_window_gate`
- `_compute_capacity_audit`
- `_compute_correlation_clusters`
- `_apply_quality_gate`

新增配置或常量：

```yaml
runtime:
  warn_stage_seconds: 300
  warn_factor_seconds: 600
```

行为：

- 单阶段超过 `warn_stage_seconds` 写入 `run_stage_timings.csv` 的 warning 字段。
- 单因子超过 `warn_factor_seconds` 写入 `run_progress.csv`。
- 不直接中断运行，只记录诊断信息。

### 3.6 降低 full rerun 的无效计算

在不改变最终 gate 语义的前提下减少无效计算：

1. 空缓存因子早退出
   - 当前已有早退出，保留。

2. `role=neutralizer` 不参与 alpha-only 成本和 gate 计算
   - `log_market_cap_cs` 只需要用于 neutralization diagnostic 和 support 输出。
   - 不应执行完整 alpha candidate 的 quantile、turnover、capacity gate。

3. `DATA_MISSING` 因子不参与 rolling/capacity/correlation。

4. 对没有足够 validation rows 的因子，跳过后续高成本阶段：
   - 若 `validation_rows == 0`，跳过 quantile、turnover、capacity。
   - gate 输出 `DATA_MISSING` 或 `FAIL`，原因写清楚。

5. capacity audit 只对可能进入 `PASS/WATCH` 的 alpha candidate 执行。
   - 若 raw/neutral gate 已明确 fail 且不可能被 capacity 改变结果，可跳过 capacity，并写 header-only 或 `NOT_EVALUATED` 行。

### 3.7 增强 validator 对完整重跑的验收

修改 `scripts/validate_factor_quality_outputs.py`，新增可选检查：

```bash
--require-run-manifest
--max-output-age-minutes 120
```

检查内容：

- `run_manifest.json` 存在。
- `status == SUCCESS`。
- `config_sha256` 与当前 config 文件一致。
- 必需产物的 mtime 晚于 `run_manifest.start_time`。
- 必需产物的 mtime 不早于本次运行开始时间。
- 没有只依赖旧报告或旧 CSV 的情况。

默认 validator 可保持兼容；V4 验收时必须启用这些参数。

最终验收命令建议改为：

```bash
python scripts/validate_factor_quality_outputs.py --out-dir outputs/analysis/factor_quality_rebuild_v4 --config configs/factor_quality_rebuild_v4.yaml --require-run-manifest --max-output-age-minutes 120
```

### 3.8 重新生成 V4 正式产物

修复后执行：

```bash
python scripts/factor_quality_rebuild.py --config configs/factor_quality_rebuild_v4.yaml --out-dir outputs/analysis/factor_quality_rebuild_v4 --out-doc docs/factor_quality_rebuild_v4_report.md --profile-out outputs/analysis/factor_quality_rebuild_v4/profile.json
```

完成后检查：

- `outputs/analysis/factor_quality_rebuild_v4/factor_quality_gate.csv`
- `outputs/analysis/factor_quality_rebuild_v4/factor_candidate_pool.yaml`
- `outputs/analysis/factor_quality_rebuild_v4/factor_rolling_window_gate.csv`
- `outputs/analysis/factor_quality_rebuild_v4/factor_capacity_audit.csv`
- `outputs/analysis/factor_quality_rebuild_v4/run_manifest.json`
- `docs/factor_quality_rebuild_v4_report.md`

候选池必须满足：

- `eligible_factors: []` 可以接受。
- `recommendation: NO_ALPHA_SOURCE_FOUND`。
- `support_factors.neutralizers` 包含 `log_market_cap_cs`。
- `log_market_cap_cs` 不得进入 `eligible_factors`、`fail_factors`、`watch_factors_for_review`。

## 4. 测试方案

### 4.1 单元测试

新增或更新测试：

- `test_run_manifest_created_on_start`
- `test_run_manifest_success_on_complete`
- `test_run_manifest_failed_on_exception`
- `test_run_progress_appends_per_factor`
- `test_partial_csv_has_header_when_no_rows`
- `test_output_written_to_run_dir_before_publish`
- `test_failed_run_does_not_publish_empty_outputs`
- `test_smoke_factor_include_limits_factor_universe`
- `test_skip_capacity_writes_header_only_capacity_csv`
- `test_validator_require_run_manifest_rejects_missing_manifest`
- `test_validator_rejects_stale_outputs_when_max_age_set`

### 4.2 回归测试

运行：

```bash
python -m pytest tests/test_factor_quality_rebuild.py tests/test_factor_quality_output_validation.py tests/test_v4_config_validation.py -q
```

验收：

- 全部通过。
- pandas deprecation warnings 暂不阻断。

### 4.3 Smoke 流程测试

运行：

```bash
python scripts/factor_quality_rebuild.py --config configs/factor_quality_rebuild_v4.yaml --out-dir outputs/analysis/factor_quality_rebuild_v4_smoke --out-doc docs/factor_quality_rebuild_v4_smoke_report.md --factor-include reversal_5_cs,volatility_60_cs,log_market_cap_cs --skip-capacity --skip-regime --profile-out outputs/analysis/factor_quality_rebuild_v4_smoke/profile.json
python scripts/validate_factor_quality_outputs.py --out-dir outputs/analysis/factor_quality_rebuild_v4_smoke --config configs/factor_quality_rebuild_v4.yaml --require-run-manifest
```

验收：

- smoke rebuild 退出码为 `0`。
- smoke validator 通过。
- run manifest 为 `SUCCESS`。
- 输出文件不是空目录。

### 4.4 Full V4 验收测试

运行：

```bash
python scripts/factor_quality_rebuild.py --config configs/factor_quality_rebuild_v4.yaml --out-dir outputs/analysis/factor_quality_rebuild_v4 --out-doc docs/factor_quality_rebuild_v4_report.md --profile-out outputs/analysis/factor_quality_rebuild_v4/profile.json
python scripts/validate_factor_quality_outputs.py --out-dir outputs/analysis/factor_quality_rebuild_v4 --config configs/factor_quality_rebuild_v4.yaml --require-run-manifest --max-output-age-minutes 120
```

验收：

- rebuild 退出码为 `0`。
- validator `8/8 PASS`。
- `run_manifest.status == SUCCESS`。
- `profile.json` 存在并记录各阶段耗时。
- `factor_candidate_pool.yaml` 契约正确。

## 5. 实施顺序

1. 增加 run manifest、progress、timing、error 诊断文件。
2. 增加安全原子输出目录 `_run_<run_id>`。
3. 增加 partial CSV checkpoint。
4. 增加 smoke 参数：`--factor-limit`、`--factor-include`、`--skip-capacity`、`--skip-regime`、`--skip-correlation`。
5. 增加性能计时和超时告警。
6. 优化无效计算跳过逻辑。
7. 增强 validator 的 run manifest 和新鲜度检查。
8. 补充单元测试。
9. 跑 smoke rebuild。
10. 跑 full V4 rebuild。
11. 跑 full validator 并更新报告。

## 6. 非目标

本次不处理以下问题：

- 不新增 alpha 因子。
- 不改变 gate 阈值。
- 不放宽 no-leakage、capacity、rolling robustness 标准。
- 不修复基本面底层数据缺失。
- 不启动策略 sleeve 或组合层重建。

如果最终仍然输出 `NO_ALPHA_SOURCE_FOUND`，只要 pipeline 可复现且候选池契约正确，就是合法结论。


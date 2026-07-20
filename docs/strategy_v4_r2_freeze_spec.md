# Strategy V4 R2 冻结规格

生成日期：2026-06-15  
策略名称：`G_candidate_v4_r2`  
前置：`docs/strategy_v4_r2_data_gate_fix_development_plan.md`

## 1. 策略定义

```python
"G_candidate_v4_r2": Strategy(
    name="G_candidate_v4_r2",
    label="Candidate v4 r2: data-clean gate-compliant alpha candidate",
    args=(
        "--factors-config", "configs/factors_candidate_v4_r2.yaml",
        "--strategy-mode", "regime",
        "--regime-config", "configs/regime_candidate_v4_r2.yaml",
    ),
)
```

## 2. 配置冻结

| 配置文件 | SHA256 | 说明 |
|------|------|------|
| `configs/factors_candidate_v4_r2.yaml` | 待计算 | 候选因子池（仅 gate-compliant） |
| `configs/regime_candidate_v4_r2.yaml` | 待计算 | Regime/sleeve 配置（gate-compliant） |

配置冻结规则：
- 冻结后不得修改 `factors_candidate_v4_r2.yaml` 和 `regime_candidate_v4_r2.yaml`。
- 若需修改，必须注册新候选名（如 `G_candidate_v4_r3`）。
- 修改后 manifest 哈希会变化，旧 run 标记为 `MANIFEST_STALE`。

## 3. 验证窗口

| 年份 | 样本类型 | 日期范围 |
|------|------|------|
| 2017 | validation | 20170101-20171231 |
| 2018 | validation | 20180101-20181231 |
| 2019 | validation | 20190101-20191231 |
| 2020 | validation | 20200101-20201231 |
| 2021 | validation | 20210101-20211231 |
| 2022 | validation | 20220101-20221231 |
| 2023 | validation | 20230101-20231231 |
| 2024 | validation | 20240101-20241231 |
| 2026 | ytd | 20260101-20260605 |

2025 年为 discovery 年份，不纳入验证。

## 4. 前置条件（硬性门禁）

以下条件必须全部满足才能运行正式冻结验证：

| 门禁 | 要求 | 验证方式 |
|------|------|------|
| 1. growth 因子重复键 | 0 | `scripts/diagnose_factor_duplicates.py` |
| 2. audit_cache 2017-2024 | FAIL=0 | `scripts/audit_cache.py --start 20170101 --end 20241231` |
| 3. audit_cache 2026 YTD | FAIL=0 | `scripts/audit_cache.py --start 20260101 --end 20260605` |
| 4. audit_alpha_inputs_v4 | 候选池因子全部 PASS | `scripts/audit_alpha_inputs_v4.py` |
| 5. factor_quality_gate | PASS 因子 >= 5（建议） | `scripts/factor_quality_rebuild.py` |
| 6. 候选池合规 | enabled 无 FAIL/DATA_MISSING/审计失败因子 | `tests/test_factor_candidate_v4_r2.py` |
| 7. 全量测试 | 全部通过 | `python -X utf8 -m pytest -q` |

## 5. 冒烟测试

```powershell
python -X utf8 scripts\frozen_backtest_validation.py --strategies G_candidate_v4_r2 --years 2023 --force --out-dir outputs\validation\candidate_v4_r2_smoke --out-doc docs\_v4_r2_smoke.md
```

验收标准：

| 检查项 | 要求 |
|------|------|
| return_code | 0 |
| run_manifest.json | 存在 |
| factors_config_sha256 | 与 `configs/factors_candidate_v4_r2.yaml` 一致 |
| regime_config_sha256 | 与 `configs/regime_candidate_v4_r2.yaml` 一致 |
| factor_list_sha256 | 非空 |
| factor_list | 不含审计失败因子 |

## 6. 完整冻结验证

```powershell
python -X utf8 scripts\frozen_backtest_validation.py --strategies G_candidate_v4_r2 --out-dir outputs\validation\candidate_v4_r2 --out-doc docs\candidate_v4_r2_validation.md --force
```

产物：

```text
outputs/validation/candidate_v4_r2/runs.csv
outputs/validation/candidate_v4_r2/runs_partial.csv
outputs/validation/candidate_v4_r2/logs/*.log
docs/candidate_v4_r2_validation.md
```

验收标准：

- `runs.csv` 包含 9 条 `G_candidate_v4_r2` 记录。
- 8 个 validation 年份完整。
- 2026 YTD 单独标记。
- 所有 manifest 哈希与当前配置一致。
- 无 `NO_GO_DATA_INVALID` 状态。
- 运行前后 `audit_cache FAIL=0`。

## 7. GO/NO-GO 决策

```powershell
python -X utf8 scripts\generate_go_nogo_decision.py --runs outputs\validation\frozen_backtest\runs.csv outputs\validation\candidate_v2\runs.csv outputs\validation\candidate_v3\runs.csv outputs\validation\candidate_v4_r1\runs.csv outputs\validation\candidate_v4_r2\runs.csv
```

## 8. 验收项

| 指标 | GO 门槛 | 说明 |
|------|------:|------|
| 平均年化超额 | > 2.0% | 2017-2024 |
| 中位数年化超额 | > 0.0% | 2017-2024 |
| 正超额年份 | >= 5/8 | |
| 平均 IR | > 0.30 | |
| 最大单年超额亏损 | > -10.0% | |
| audit_cache FAIL | = 0 | |
| manifest | 全部一致 | |
| GO/NO-GO | 非 INCOMPLETE | |

## 9. 禁止行为

1. 不修改 V4-r1 历史 runs。
2. 不覆盖 V4-r1 manifest。
3. 不将 FAIL/DATA_MISSING 因子放入 r2 enabled。
4. 不在 `audit_cache FAIL > 0` 时运行正式冻结验证。
5. 不在 `factor_quality_gate PASS=0` 时包装候选策略。
6. 不把 `WATCH_NEUTRAL_ONLY` 因子当成 alpha 通过证据。
7. 不把输入审计 FAIL 的因子放入 `enabled_factors`。
8. 不启用 `sleeve_performance_overlay`。

## 10. V4-r2 退出条件

出现以下任一情况，停止 V4-r2：

1. growth 因子重复键无法修复。
2. `audit_cache` 仍有 FAIL。
3. 输入审计中候选因子仍 FAIL。
4. factor gate 仍为 0 PASS。
5. 候选池只能由 FAIL/WATCH 因子组成。
6. 冒烟测试 manifest 不一致。
7. 完整冻结验证缺少年份。
8. V4-r2 相对 V3 仍整体恶化。

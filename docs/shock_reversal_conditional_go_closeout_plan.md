# Shock Reversal Conditional GO 收尾开发方案

生成日期：2026-06-12  
适用范围：`E_shock_reversal` 冻结验证审计链路、验收报告口径修正  
当前结论：功能与数据闭环已基本完成，状态为 **Conditional GO**。正式归档前需补齐冻结日志审计证据，并将报告中的 GO 表述收敛为“低权重保留观察”，避免被误读为策略升级通过。

## 1. 背景

上一轮审核确认：

1. `abnormal_drop_reversal_5` 与 `abnormal_drop_reversal_5_cs` 缓存已经生成，2017-2024 覆盖通过。
2. `configs/regime_shock_reversal.yaml` 预检通过，`abnormal_drop_reversal_5_cs` 已进入候选因子池。
3. `outputs/validation/frozen_backtest/runs.csv` 已包含 2017-2024 与 2026 的 `E_shock_reversal` 记录。
4. 每个 `E_shock_reversal` run_dir 的 manifest 均确认使用 `strategy_mode=regime`、`factors_config=configs/factors.yaml`、`regime_config=configs/regime_shock_reversal.yaml`。
5. diagnostics 中 `shock_reversal_weight` 大于 0，说明 sleeve 真实活跃。
6. 相关测试通过，结果为 `79 passed`。

但仍有两个收尾问题：

| ID | 优先级 | 问题 | 影响 |
|---|---|---|---|
| P2-1 | P2 | `outputs/validation/frozen_backtest/logs` 下缺少 `*E_shock*` 日志 | 与验收方案的日志审计清单不一致 |
| P2-2 | P2 | `docs/shock_reversal_acceptance_report.md` 中写成直接 `GO` | 容易被误读为可升级主策略，而非低权重观察通过 |

## 2. P2-1：补齐 E_shock_reversal 冻结日志审计链路

### 2.1 现象

当前 `runs.csv` 和 run_dir 是真实存在的，但日志目录缺少：

```text
outputs/validation/frozen_backtest/logs/*E_shock*
```

原因大概率是 `scripts/frozen_backtest_validation.py` 复用了已有 run。当前逻辑在找到 existing run 时直接返回：

```python
if existing is not None:
    print(f"  Reusing existing run: {existing.name}")
    return 0, existing
```

这会导致 `runs.csv` 有记录，但 `logs` 下没有本次策略对应日志。

### 2.2 开发任务

| 任务 | 文件 | 说明 |
|---|---|---|
| P2-1.1 | `scripts/frozen_backtest_validation.py` | 复用 existing run 时也写入审计日志 |
| P2-1.2 | `outputs/validation/frozen_backtest/logs` | 为每个 `E_shock_reversal` 年份生成日志文件 |
| P2-1.3 | `docs/shock_reversal_acceptance_report.md` | 在产物清单中引用日志文件或说明日志复用机制 |

### 2.3 建议实现

在 `_run_one` 中，先创建 `log_dir` 和 `log_path`，即使复用 existing run 也写入一份 reuse audit log：

```python
log_dir.mkdir(parents=True, exist_ok=True)
log_path = log_dir / f"{year}_{strategy.name}.log"

if reuse_existing:
    existing = _find_existing_run(...)
    if existing is not None:
        with log_path.open("w", encoding="utf-8") as fh:
            fh.write(f"Reusing existing run: {existing}\\n")
            fh.write(f"strategy={strategy.name}\\n")
            fh.write(f"year={year}\\n")
            fh.write(f"start={start}\\n")
            fh.write(f"end={end}\\n")
            fh.write(f"top_n={top_n}\\n")
            fh.write(f"args={' '.join(strategy.args)}\\n")
            fh.write("validated_by=frozen_backtest_validation.py\\n")
        return 0, existing
```

可进一步写入 manifest 关键信息：

```text
run_id
factors_config
factors_config_sha256
regime_config
regime_config_sha256
factor_list_sha256
metrics_summary path
diagnostics path
```

这样即使未重新执行 `run_research.py`，也能从 frozen validation 目录追溯到复用的 run_dir。

### 2.4 备选方案

如果不想改脚本，也可以显式重新运行 `E_shock_reversal`，强制生成日志。但当前脚本没有关闭 `--skip-existing` 的参数，因为 `--skip-existing` 目前是 `store_true` 且默认 `True`，不适合作为关闭复用的开关。因此更推荐修脚本的 reuse audit log。

### 2.5 验收命令

```powershell
python scripts/frozen_backtest_validation.py `
  --years 2017 2018 2019 2020 2021 2022 2023 2024 2026 `
  --strategies E_shock_reversal `
  --top-n 50 `
  --out-dir outputs/validation/frozen_backtest `
  --out-doc docs/frozen_backtest_validation.md
```

```powershell
Get-ChildItem outputs/validation/frozen_backtest/logs -Filter "*E_shock*"
```

```powershell
Select-String -Path outputs/validation/frozen_backtest/logs/*E_shock* `
  -Pattern "Reusing existing run|regime_shock_reversal|abnormal_drop_reversal_5_cs"
```

### 2.6 通过标准

1. logs 下存在 `2017_E_shock_reversal.log` 到 `2024_E_shock_reversal.log`，以及 2026 YTD 日志。
2. 每个日志能指向对应 run_dir。
3. 每个日志能说明使用的 regime config 是 `configs/regime_shock_reversal.yaml`。
4. 日志中无 shock 缓存缺失、覆盖不足、因子跳过等错误。
5. `runs.csv` 中的 run_dir 与日志指向一致。

## 3. P2-2：修正验收报告 GO 口径

### 3.1 现象

当前 `docs/shock_reversal_acceptance_report.md` 顶部和最终决策写成：

```text
最终结论: GO — 保留低权重接入，继续观察
```

但实际表现为：

1. 2017-2024 中，`E_shock_reversal` 相对 `D_regime_overlay` 年化收益平均低约 2.58pct。
2. 8 个正式年份中，`E_shock_reversal` 只有 3 年优于 `D_regime_overlay`。
3. 2026 YTD 为 `NO-GO`，虽然不参与调参决策，但需要继续观察。
4. 报告本身也写明“暂不升级为主策略候选”。

因此报告结论应收敛为：

```text
Conditional GO — 仅作为低权重观察 sleeve 保留，不升级为主策略候选
```

### 3.2 开发任务

| 任务 | 文件 | 说明 |
|---|---|---|
| P2-2.1 | `docs/shock_reversal_acceptance_report.md` | 顶部最终结论改为 Conditional GO |
| P2-2.2 | `docs/shock_reversal_acceptance_report.md` | 结论摘要中明确“不是策略升级 GO” |
| P2-2.3 | `docs/shock_reversal_acceptance_report.md` | 最终决策改为“低权重保留观察” |
| P2-2.4 | `docs/shock_reversal_acceptance_report.md` | 补充日志审计状态，说明已生成或复用审计日志 |

### 3.3 建议改法

顶部：

```text
**最终结论**: **Conditional GO** — 仅保留低权重观察，不升级为主策略候选
```

决策摘要：

```text
**决策**: **Conditional GO for low-weight observation**。
允许保留 `E_shock_reversal` 在冻结验证矩阵中继续观察；
不提升为主策略候选，不增加权重，不基于本次结果调参。
```

GO 条件检查中将“成本后表现不显著劣于基线”改为更精确：

```text
相对 D_regime_overlay 表现略弱，但低权重下未引入不可接受回撤；仅支持观察性保留。
```

### 3.4 验收标准

1. 全文不再出现容易误读的单独 `GO — 保留` 作为最终结论。
2. 明确写出 `Conditional GO`。
3. 明确写出“不升级为主策略候选”。
4. 明确写出“不增加权重、不调参”。
5. 明确写出 `E_shock_reversal` 相对 `D_regime_overlay` 无稳定超额。

## 4. 推荐实施顺序

1. 修改 `scripts/frozen_backtest_validation.py`，让复用 existing run 时写审计日志。
2. 运行只包含 `E_shock_reversal` 的 frozen validation，补齐 logs。
3. 检查 `runs.csv`、logs、run_dir manifest 是否一致。
4. 修改 `docs/shock_reversal_acceptance_report.md` 的结论口径。
5. 重新运行关键测试。
6. 做最终复核。

## 5. 回归测试

建议运行：

```powershell
python -m pytest -q tests/test_shock_reversal.py tests/test_regime_allocator.py tests/test_sleeve_performance_overlay.py tests/test_regime_config_validation.py tests/test_factor_alignment.py tests/test_regime_factor_universe.py tests/test_tradable_limit_rules.py
```

如果 `scripts/frozen_backtest_validation.py` 已有专门测试，应补充：

| 测试 | 断言 |
|---|---|
| reuse existing run writes log | 复用 run 时仍生成 `{year}_{strategy}.log` |
| reuse log contains manifest path | 日志包含 run_dir、regime_config、factor_list_sha256 |
| non-reuse execution still writes command log | 新执行路径不受影响 |

## 6. 最终验收清单

| 检查项 | 命令/文件 | 通过标准 |
|---|---|---|
| E 日志存在 | `Get-ChildItem ... -Filter "*E_shock*"` | 2017-2024 与 2026 均存在 |
| 日志可追溯 | `Select-String ... "regime_shock_reversal"` | 能定位 run_dir 和 config |
| runs 仍有效 | `runs.csv` | `E_shock_reversal` return_code=0 |
| manifest 一致 | 每个 run_dir `run_manifest.json` | `regime_config=configs/regime_shock_reversal.yaml` |
| 报告口径 | `docs/shock_reversal_acceptance_report.md` | `Conditional GO`，不升级，不调参 |
| 测试回归 | pytest 命令 | 全部通过 |

## 7. 完成后的最终状态

完成后，本轮 shock reversal 验收可正式归档为：

```text
Conditional GO:
  - 允许作为低权重观察 sleeve 保留
  - 不升级为主策略候选
  - 不增加权重
  - 不基于本次冻结验证结果调参
  - 2026 全年样本完成后重新评估
```

如补齐日志后发现 `runs.csv` 与 manifest 不一致，或 `E_shock_reversal` 日志显示缓存缺失、因子跳过，应立即回退为 No-Go，并重新排查缓存和 frozen validation 调度链路。

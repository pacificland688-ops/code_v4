# Strategy V4 冻结前规格说明

生成日期：2026-06-14  
候选策略：`G_candidate_v4`  
冻结原则：配置预注册后不得更改；验证结果不能用于修改配置。

## 1. 策略标识

| 属性 | 值 |
|------|------|
| 策略名 | `G_candidate_v4` |
| 标签 | "Candidate v4: alpha rebuild + regime_candidate_v4 (no overlay)" |
| 因子配置 | `configs/factors_candidate_v4.yaml` |
| Regime 配置 | `configs/regime_candidate_v4.yaml` |
| 策略模式 | `regime` |
| Performance overlay | **关闭**（`enabled: false`） |

## 2. 配置哈希（冻结时记录）

| 文件 | 预期冻结后 SHA256 |
|------|------|
| `configs/factors_candidate_v4.yaml` | 冻结时自动计算 |
| `configs/regime_candidate_v4.yaml` | 冻结时自动计算 |
| 因子列表（排序后） | 冻结时自动计算 |

## 3. 注册代码

```python
# scripts/frozen_backtest_validation.py
"G_candidate_v4": Strategy(
    name="G_candidate_v4",
    label="Candidate v4: alpha rebuild + regime_candidate_v4 (no overlay)",
    args=(
        "--factors-config", "configs/factors_candidate_v4.yaml",
        "--strategy-mode", "regime",
        "--regime-config", "configs/regime_candidate_v4.yaml",
    ),
)
```

## 4. 验证命令

### 4.1 冒烟测试（单年 2023）

```powershell
python -X utf8 scripts\frozen_backtest_validation.py --strategies G_candidate_v4 --years 2023 --force --out-dir outputs\validation\candidate_v4_smoke --out-doc docs\_v4_smoke.md
```

### 4.2 完整冻结验证

```powershell
python -X utf8 scripts\frozen_backtest_validation.py --strategies G_candidate_v4 --out-dir outputs\validation\candidate_v4 --out-doc docs\candidate_v4_validation.md --force
```

覆盖年份：2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2026

### 4.3 GO/NO-GO 决策

```powershell
python -X utf8 scripts\generate_go_nogo_decision.py --runs outputs\validation\frozen_backtest\runs.csv outputs\validation\candidate_v2\runs.csv outputs\validation\candidate_v3\runs.csv outputs\validation\candidate_v4\runs.csv
```

## 5. 验收标准

| 检查项 | 标准 |
|------|------|
| 冒烟退出码 | 0 |
| `run_manifest.json` 包含 factors/regime/factor_list 哈希 | 全部非空 |
| factor_list 与 `configs/factors_candidate_v4.yaml` 一致 | 完全匹配 |
| `runs.csv` 包含 9 条 `G_candidate_v4` 记录 | 8 validation + 1 ytd |
| 所有 manifest 哈希非空 | 是 |
| audit_cache 无 FAIL | 是 |
| 2026 YTD 单独标记，不纳入 validation 均值 | 是 |

## 6. 禁止行为

- ❌ 不基于冒烟结果调整配置
- ❌ 不基于 2026 YTD 结果调参
- ❌ 不降低 GO 门槛
- ❌ 不修改配置后使用同一 `G_candidate_v4` 名称

## 7. 冻结点

配置冻结于：2026-06-14

配置冻结后，只有在以下情况下才允许修改：
1. 发现配置 bug（如拼写错误、引用不存在的文件）
2. 明确记录修改内容和理由
3. 使用 `G_candidate_v4_r1`、`G_candidate_v4_r2` 等修订名

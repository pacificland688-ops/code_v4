# Shock Reversal 验收问题整改开发方案

生成日期：2026-06-12  
适用范围：`shock_reversal` sleeve、`abnormal_drop_reversal_5` / `abnormal_drop_reversal_5_cs` 因子缓存、冻结回测验收链路  
当前结论：不建议验收。代码局部修复已落地，相关测试为绿，但核心横截面配置未实际生效，因子缓存与冻结回测产物尚未闭环。

## 1. 背景与目标

本方案承接 `docs/shock_reversal_remediation_plan.md` 开发完成后的审核结果，目标不是继续调参，而是修复验收中暴露的工程与验证缺口，使 `shock_reversal` 能够被稳定、可复现、可审计地接入 regime 组合。

完成后应满足：

1. `shock_reversal` 专用横截面处理真实使用 `missing_method: drop`，结构性过滤后的股票不会被中位数补回。
2. `abnormal_drop_reversal_5` 与 `abnormal_drop_reversal_5_cs` 在 2017-2024 正式验证窗口内有完整可审计缓存。
3. `E_shock_reversal` 冻结回测产物存在，且可以证明 sleeve 的边际贡献、覆盖率、风险与成本后表现。
4. 单元测试和集成探针覆盖本次审核暴露的配置路由与 NaN 回填漏洞。
5. regime 在 shock 因子缺失或覆盖不足时继续硬失败，避免静默跳过 sleeve。

## 2. 问题清单

| ID | 优先级 | 问题 | 影响 | 当前判断 |
|---|---|---|---|---|
| P0-1 | P0 | `configs/factors_shock_reversal.yaml` 的 `shock_reversal.cross_section` 未被 `create_processor_from_config` 读取 | ST、停牌、IPO、低流动性等结构性过滤结果会被横截面中位数补回 | 阻塞验收 |
| P1-1 | P1 | `abnormal_drop_reversal_5` 与 `_cs` 本地 parquet 缓存覆盖为 0 | regime 无法真实加载 shock 因子，后续研究验证无法开始 | 阻塞验收 |
| P1-2 | P1 | 缺少 `E_shock_reversal` 冻结回测运行产物 | 无法证明 alpha、风险、覆盖率、边际贡献和成本后表现 | 阻塞验收 |
| P2-1 | P2 | 测试未覆盖专用配置读取和 NaN 不回填 | 当前测试绿但不能防止核心 bug 回归 | 必须补齐 |
| P2-2 | P2 | 部分注释/日志存在编码异常字符 | 影响审计可读性，严重时影响日志检索 | 建议同步清理 |

## 3. P0-1：修复 shock 专用横截面配置路由

### 3.1 现象

`configs/factors_shock_reversal.yaml` 中配置位置为：

```yaml
shock_reversal:
  cross_section:
    missing_method: "drop"
    neutralizers:
      - "log_market_cap"
```

但 `factors/cross_section.py:create_processor_from_config` 当前只读取顶层：

```python
cs = config.get("cross_section", {})
if not cs:
    return create_default_processor()
```

因此实际调用：

```python
create_processor_from_config("configs/factors_shock_reversal.yaml")
```

得到的是默认处理器：

```text
missing_method=industry_median
neutralizers=['industry', 'log_market_cap']
```

当输入包含结构性过滤产生的 NaN 时，默认处理器会将其补回，导致应剔除股票继续进入 `_cs` 因子。

### 3.2 开发任务

| 任务 | 文件 | 说明 |
|---|---|---|
| P0-1.1 | `factors/cross_section.py` | 扩展 `create_processor_from_config`，支持读取指定 section，例如 `shock_reversal.cross_section` |
| P0-1.2 | `factors/factor_panel.py` | `shock_cs` 调用时显式传入 `section="shock_reversal"`，并在初始化后断言 `missing_method == "drop"` |
| P0-1.3 | `scripts/build_shock_reversal_factor.py` | 构建脚本使用同一专用配置入口，避免脚本与 panel builder 行为分叉 |
| P0-1.4 | `configs/factors_shock_reversal.yaml` | 保持配置结构稳定；如改为顶层 `cross_section`，必须同步更新文档和调用方 |
| P0-1.5 | `tests/test_shock_reversal.py` 或新增测试文件 | 增加配置路由测试，验证读取后 `missing_method == "drop"` 且 neutralizers 不包含非 PIT 行业中性化 |

### 3.3 建议实现

推荐保留当前 YAML 结构，给配置加载器增加 section 参数：

```python
def create_processor_from_config(config_path="configs/factors.yaml", section=None):
    config = yaml.safe_load(...)
    if section:
        cs = config.get(section, {}).get("cross_section", {})
    else:
        cs = config.get("cross_section", {})
```

为了兼容旧调用，可采用优先级：

1. 显式 `section` 存在时，读取 `config[section]["cross_section"]`。
2. 未传 `section` 时，读取顶层 `cross_section`。
3. 两者都不存在时，返回默认处理器。

对 shock 场景不建议静默回退为默认处理器。若专用配置缺失，应抛出明确异常或在调用方强制校验：

```python
if cs.missing_method != "drop":
    raise RuntimeError("shock_reversal CS config must use missing_method='drop'")
```

### 3.4 验收标准

必须通过以下探针：

```powershell
@'
from factors.cross_section import create_processor_from_config
p = create_processor_from_config("configs/factors_shock_reversal.yaml", section="shock_reversal")
print(p.missing_method)
print(p.neutralizers)
'@ | python -
```

预期：

```text
drop
['log_market_cap']
```

必须通过 NaN 不回填探针：

```powershell
@'
import pandas as pd
import numpy as np
from factors.cross_section import create_processor_from_config

class DummyIndustry:
    has_pit_data = False

class DummyLoader:
    def read_factor(self, *args, **kwargs):
        return pd.DataFrame()
    def write_factor(self, *args, **kwargs):
        pass

p = create_processor_from_config("configs/factors_shock_reversal.yaml", section="shock_reversal")
p._loader = DummyLoader()
p._industry_classifier = DummyIndustry()

raw = pd.DataFrame({
    "ts_code": [f"S{i:03d}" for i in range(40)],
    "trade_date": [20240102] * 40,
    "abnormal_drop_reversal_5": [np.nan if i < 10 else float(i) for i in range(40)],
})

out = p.process_factor(raw, "abnormal_drop_reversal_5", save=False)
filtered = set(raw.loc[raw["abnormal_drop_reversal_5"].isna(), "ts_code"])
kept = set(out["ts_code"]) if not out.empty else set()

print("missing_method=", p.missing_method)
print("input_nan=", raw["abnormal_drop_reversal_5"].isna().sum())
print("output_rows=", len(out))
print("filtered_names_present=", len(filtered & kept))
'@ | python -
```

预期：

```text
missing_method= drop
input_nan= 10
output_rows= 30
filtered_names_present= 0
```

## 4. P1-1：生成并审计 shock 因子缓存

### 4.1 现象

当前本地覆盖检查结果为：

```text
abnormal_drop_reversal_5    rows=0, n_dates=0
abnormal_drop_reversal_5_cs rows=0, n_dates=0
```

这说明代码虽然已经接入，但正式验证窗口内没有可用缓存。

### 4.2 开发任务

| 任务 | 文件/命令 | 说明 |
|---|---|---|
| P1-1.1 | `scripts/build_shock_reversal_factor.py` | 先完成 P0-1 后再运行，避免生成错误 `_cs` 缓存 |
| P1-1.2 | `data/parquet/factors/factor_name=abnormal_drop_reversal_5/` | 生成原始 shock 因子缓存 |
| P1-1.3 | `data/parquet/factors/factor_name=abnormal_drop_reversal_5_cs/` | 生成横截面处理后因子缓存 |
| P1-1.4 | 新增或复用覆盖率报告 | 输出年度 rows、n_dates、min_date、max_date、平均股票数、NaN 剔除比例 |
| P1-1.5 | `run_research.py` | 保留 shock 因子缺失或覆盖不足时的硬失败逻辑 |

### 4.3 执行命令

修复 P0-1 并通过测试后，执行：

```powershell
python scripts/build_shock_reversal_factor.py --start 20170101 --end 20241231 --recompute
```

覆盖率检查：

```powershell
@'
from data.panel_loader import get_loader
loader = get_loader()
for name in ["abnormal_drop_reversal_5", "abnormal_drop_reversal_5_cs"]:
    print(name, loader.factor_coverage(name, "20170101", "20241231"))
'@ | python -
```

### 4.4 验收标准

1. 两个因子的 `rows > 0`，`n_dates > 0`。
2. `min_date <= 20170101` 或覆盖正式窗口起点附近首个可交易信号日。
3. `max_date >= 20241231` 附近最后一个可交易信号日。
4. `_cs` 因子平均每个信号日股票数不低于 regime 硬失败阈值。
5. `_cs` 输出中不包含 P0-1 探针中的结构性 NaN 股票。
6. 缓存生成命令、覆盖率结果和诊断摘要写入 `outputs` 下可追溯文件。

## 5. P1-2：完成 E_shock_reversal 冻结回测验收

### 5.1 现象

`scripts/frozen_backtest_validation.py` 已定义 `E_shock_reversal`，但当前 `outputs/validation/frozen_backtest/runs.csv` 和日志目录没有对应记录。

### 5.2 开发任务

| 任务 | 文件/命令 | 说明 |
|---|---|---|
| P1-2.1 | `configs/regime_shock_reversal.yaml` | 确认 sleeve 权重、因子名、候选池与缓存名称一致 |
| P1-2.2 | `scripts/frozen_backtest_validation.py` | 确认 `E_shock_reversal` 纳入可执行策略集合 |
| P1-2.3 | 冻结回测命令 | 运行包含 `E_shock_reversal` 的冻结验证 |
| P1-2.4 | `outputs/validation/frozen_backtest/` | 生成 runs、logs、metrics、diagnostics |
| P1-2.5 | 新增验收摘要文档 | 记录 `E_shock_reversal` 相对基线的收益、回撤、换手、成本后表现和 sleeve 权重行为 |

### 5.3 执行命令

根据脚本实际参数选择最小可复现命令。若支持单策略运行，优先执行：

```powershell
python scripts/frozen_backtest_validation.py --strategy E_shock_reversal
```

若脚本不支持单策略参数，则执行完整冻结验证：

```powershell
python scripts/frozen_backtest_validation.py
```

运行后检查：

```powershell
Select-String -Path outputs/validation/frozen_backtest/runs.csv -Pattern "E_shock_reversal"
Get-ChildItem outputs/validation/frozen_backtest/logs -Filter "*E_shock*"
```

### 5.4 验收标准

1. `runs.csv` 存在 `E_shock_reversal` 记录。
2. 日志目录存在对应运行日志，且无 shock 因子缺失、覆盖不足、静默跳过 sleeve 的错误。
3. 输出中可定位 run_id、起止日期、配置文件、因子缓存版本。
4. 指标至少包含：年化收益、最大回撤、Sharpe、换手、交易成本后收益、持仓数、shock sleeve 平均权重与活跃日期占比。
5. 与基线策略对比后形成 GO / NO-GO 结论，不允许只给“已运行”但无指标解释。

## 6. P2-1：补齐测试覆盖

### 6.1 当前缺口

现有测试可以覆盖部分跌停、ST、停牌、IPO、regime 硬失败等行为，但没有覆盖：

1. `configs/factors_shock_reversal.yaml` 的嵌套 `shock_reversal.cross_section` 是否被读取。
2. `missing_method` 是否为 `drop`。
3. 结构性 NaN 是否被剔除而不是补回。
4. `scripts/build_shock_reversal_factor.py` 与 `FactorPanelBuilder.shock_cs` 是否使用同一套专用处理器。

### 6.2 开发任务

| 任务 | 建议测试 | 断言 |
|---|---|---|
| P2-1.1 | `test_shock_cs_config_route_reads_nested_section` | `missing_method == "drop"`，`neutralizers == ["log_market_cap"]` |
| P2-1.2 | `test_shock_cs_drops_structural_nan` | 输入 40 行、10 行 NaN，输出 30 行，NaN 股票不再出现 |
| P2-1.3 | `test_factor_panel_uses_shock_specific_cs` | `FactorPanelBuilder().shock_cs.missing_method == "drop"` |
| P2-1.4 | `test_build_script_uses_shock_specific_cs` | 构建脚本初始化的处理器不回退到默认 `industry_median` |
| P2-1.5 | `test_regime_hard_fails_when_shock_cache_missing` | 保留当前硬失败行为 |

### 6.3 测试命令

```powershell
python -m pytest -q tests/test_shock_reversal.py tests/test_factor_alignment.py tests/test_regime_factor_universe.py tests/test_regime_config_validation.py
```

完整回归：

```powershell
python -m pytest -q tests/test_shock_reversal.py tests/test_regime_allocator.py tests/test_sleeve_performance_overlay.py tests/test_regime_config_validation.py tests/test_factor_alignment.py tests/test_regime_factor_universe.py tests/test_tradable_limit_rules.py
```

### 6.4 验收标准

1. 新增测试在修复前失败、修复后通过。
2. 原有 72 项相关测试继续通过。
3. 测试不依赖真实 Tushare 网络请求。
4. 测试使用小型 DataFrame 或 mock loader，能在本地快速稳定运行。

## 7. P2-2：清理编码异常与审计可读性

### 7.1 现象

部分文件中注释、日志或字符串显示为异常字符，例如 `鈥?`。这不一定影响核心计算，但会降低审核、日志检索和错误定位效率。

### 7.2 开发任务

| 任务 | 文件范围 | 说明 |
|---|---|---|
| P2-2.1 | `factors/shock_reversal.py` | 清理新增注释和 warning 文案中的异常字符 |
| P2-2.2 | `run_research.py` | 清理 shock 硬失败错误信息，确保日志可读 |
| P2-2.3 | `configs/factors_shock_reversal.yaml` | 清理中文注释编码异常，保留 UTF-8 |
| P2-2.4 | `scripts/build_shock_reversal_factor.py` | 清理 docstring 和日志文案 |

### 7.3 验收标准

1. 源码和配置中的核心注释可正常显示。
2. `RuntimeError` 信息可直接复制到排查命令中。
3. 不改变任何计算逻辑。

## 8. 推荐实施顺序

### 阶段 A：阻塞修复

1. 修复 `create_processor_from_config` 的 section 路由。
2. 修改 `FactorPanelBuilder.shock_cs` 和构建脚本，显式使用 `section="shock_reversal"`。
3. 增加 shock CS 安全断言，禁止静默回退为默认补值逻辑。
4. 补齐配置路由和 NaN 不回填测试。
5. 运行相关单元测试。

阶段 A 完成标准：

```text
shock CS missing_method = drop
结构性 NaN 不被补回
相关测试全部通过
```

### 阶段 B：缓存生成

1. 清理旧的 `abnormal_drop_reversal_5` 与 `_cs` 缓存。
2. 运行 `scripts/build_shock_reversal_factor.py --start 20170101 --end 20241231 --recompute`。
3. 输出覆盖率、年度分布、平均股票数、过滤诊断。
4. 验证 regime 选择器不再因 shock 缓存缺失而硬失败。

阶段 B 完成标准：

```text
abnormal_drop_reversal_5 / abnormal_drop_reversal_5_cs 均有 2017-2024 覆盖
regime shock sleeve 可加载，不静默跳过
```

### 阶段 C：冻结回测验收

1. 运行 `E_shock_reversal` 冻结回测。
2. 检查 runs、logs、metrics、diagnostics。
3. 与基线策略对比，输出边际贡献和风险说明。
4. 更新 GO / NO-GO 决策文档。

阶段 C 完成标准：

```text
outputs/validation/frozen_backtest/runs.csv 包含 E_shock_reversal
存在对应日志和指标产物
有明确 GO / NO-GO 结论
```

## 9. 最终验收清单

| 检查项 | 命令/文件 | 通过标准 |
|---|---|---|
| shock CS 配置读取 | `create_processor_from_config(..., section="shock_reversal")` | `missing_method=drop` |
| NaN 不回填 | 小型 DataFrame 探针 | 输入 10 个结构性 NaN，输出少 10 行 |
| 单元测试 | `python -m pytest -q ...` | 全部通过 |
| 因子缓存覆盖 | `loader.factor_coverage(...)` | rows 和 n_dates 均大于 0，覆盖 2017-2024 |
| regime 加载 | `_select_regime_candidate_factors(...)` | shock 缓存存在时通过，缺失时硬失败 |
| 冻结回测 | `outputs/validation/frozen_backtest/runs.csv` | 包含 `E_shock_reversal` |
| 日志产物 | `outputs/validation/frozen_backtest/logs` | 存在 `E_shock` 相关日志且无缺因子错误 |
| 决策文档 | GO / NO-GO 文档 | 明确说明是否验收 |

## 10. 风险与注意事项

1. 不要在 P0-1 修复前生成 `_cs` 缓存，否则会把错误补值逻辑固化到 parquet。
2. 不要为了让 regime 跑通而降低 shock 缓存覆盖率硬失败阈值。
3. 不要把结构性过滤 NaN 和普通缺失值混为一谈；第一版以 `drop` 为准，后续如要区分缺失类型，应增加显式字段。
4. 行业中性化必须确认 PIT 安全后再启用；当前 shock 专用配置建议只使用 `log_market_cap`。
5. 冻结回测只用于验收，不应在看到结果后反向微调 shock 参数。

## 11. 建议产物

完成开发后建议新增或更新以下产物：

```text
outputs/shock_reversal/coverage_2017_2024.csv
outputs/shock_reversal/filter_diagnostics_2017_2024.csv
outputs/shock_reversal/cs_processing_diagnostics_2017_2024.csv
outputs/validation/frozen_backtest/runs.csv
outputs/validation/frozen_backtest/logs/*E_shock*
docs/shock_reversal_acceptance_report.md
```

`docs/shock_reversal_acceptance_report.md` 应至少包含：

1. 修复 commit 或变更摘要。
2. P0/P1/P2 问题关闭情况。
3. 测试命令和结果。
4. 因子缓存覆盖率摘要。
5. `E_shock_reversal` 冻结回测指标。
6. 最终 GO / NO-GO 结论。

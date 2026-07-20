# 策略下一阶段开发文档

生成日期：2026-06-11  
适用项目：`code_v4` 沪深300横截面多因子策略  
当前主线：Phase 2 选股回测 + regime sleeve overlay + 冻结跨年验证

## 1. 结论摘要

当前项目已经完成从“单年可跑”到“冻结候选配置跨年份验证”的推进。最有希望的候选是：

- 策略：`D_regime_overlay`
- 配置：`outputs/analysis/regime_grid_overlay_phase2_2025/configs/less_reversal_faster_overlay.yaml`
- 入口：`python run_research.py phase2 ... --strategy-mode regime --regime-config ...`

但当前状态仍然是研究候选，不是生产候选。

核心判断如下：

1. `D_regime_overlay` 相对 `C_regime_baseline` 有稳定增量。2017-2024 验证年中，D 相对 C 有 7/8 年改善，平均年化超额改善约 1.70%。
2. D 自身仍未打穿完整年度验证。2017-2024 平均年化超额约 -6.37%，正超额年份只有 2/8。
3. 2026 YTD 观察为正，但样本不足。D 在 2026-01-01 至 2026-06-05 的年化超额约 +6.01%，IR 约 0.37，但只有 20 个周样本，被系统标记为 `UNSTABLE / NO-GO`。
4. 当前瓶颈不只是 regime 参数。因子层面只有 `ep_cs`、`bp_cs`、`sp_cs` 明确通过 IC 门槛，多数技术、动量、反转因子未通过。
5. 下一步不应继续盲目网格搜索。应先完成失败年份和失败月份归因，明确 alpha、router、组合构建、交易约束、成本哪一层吞掉收益。

## 2. 当前证据和产物

主要文档：

- `docs/frozen_backtest_validation.md`：冻结配置跨年验证主报告。
- `docs/frozen_backtest_attribution.md`：D 相对 C/A/B 的归因分析。
- `docs/regime_sleeve_overlay_validation_2023_2025.md`：overlay 设计、验证和 2023/2025 结论。
- `docs/regime_failure_attribution_2023_2025.md`：2023/2025 失败归因。
- `docs/sleeve_weight_cross_year.md`：sleeve 权重错配跨年核查。
- `outputs/validation/frozen_backtest/runs.csv`：2017-2024 与 2026 YTD 的冻结验证结果。
- `outputs/analysis/frozen_backtest_attribution/*.csv`：D-C 差异、sleeve 权重、overlay 质量、持仓风格暴露。

关键指标快照：

| 范围 | 策略 | 年化收益 | 年化超额 | IR | 最大回撤 | 状态 |
|---|---|---:|---:|---:|---:|---|
| 2017-2024 验证均值 | D_regime_overlay | -2.66% | -6.37% | -0.73 | -21.34% | 研究候选 |
| 2026 YTD | D_regime_overlay | 6.07% | 6.01% | 0.37 | -10.83% | NO-GO, UNSTABLE |

D 相对其他方案：

| 对比 | 验证年胜率 | 平均年化超额差 | 判断 |
|---|---:|---:|---|
| D - C | 7/8 | +1.70% | 有增量 |
| D - A | 5/8 | +4.56% | 有改善但不稳定 |
| B - A | 4/8 | -1.89% | 全因子动态 IC 路线未通过 |

## 3. 开发边界

### 3.1 数据集边界

后续所有实验必须明确样本用途：

| 样本 | 用途 | 说明 |
|---|---|---|
| 2017-2024 | 正式验证集 | 用于冻结策略验收，不允许按结果反复调参 |
| 2025 | 问题发现和候选形成集 | 已参与候选形成，不作为最终 OOS 验收 |
| 2026 YTD | 前瞻观察 | 样本不足，只能观察方向，不能用于定规则 |
| 2023/2025 | 失败归因集 | 可以用于定位问题，但不能直接作为上线证据 |

### 3.2 策略边界

本阶段目标不是快速上线，而是回答三个问题：

1. D 为什么多数年份能改善 C，但自身仍是负超额？
2. 失败来自底层 alpha、regime router、组合构建，还是交易执行约束？
3. 是否能形成一套冻结规则，在 2017-2024 多数年份和 2026 YTD 都不明显反向？

### 3.3 禁止事项

在完成归因前，禁止以下做法：

- 不继续扩大无约束参数网格。
- 不用 2026 YTD 调参。
- 不把 2025 当最终验证。
- 不只看年化收益，必须同时看超额、IR、回撤、换手、成本、样本稳定性。
- 不基于单一年份反转某个因子方向。

## 4. 下一阶段总体目标

下一阶段目标定义为：

> 将 `D_regime_overlay` 从“相对改善的研究候选”推进到“可被严格验证的候选体系”，或者明确判定该路线不值得继续投入。

阶段性目标：

1. 统一验证口径，刷新过期验证报告。
2. 找出 D 在 2017、2018、2019、2020、2021 负超额的主因。
3. 建立因子层、sleeve 层、组合层的可重复诊断流程。
4. 设计少量有经济含义的新候选规则。
5. 冻结候选后重新跑 2017-2024 验证和 2026 YTD 观察。
6. 给出 GO / NO-GO 决策。

## 5. 阶段拆分

## Phase A：验证链路收口

目标：先确保当前状态可信，避免旧报告、旧缓存或旧口径误导下一步开发。

任务清单：

| ID | 任务 | 产物 | 优先级 |
|---|---|---|---|
| A1 | 刷新环境、测试、缓存审计 | 最新测试日志 | P0 |
| A2 | 重新生成当前 `validation_report.md` | `outputs/validation_report.md` | P0 |
| A3 | 核查 `limit_status` 缓存覆盖和重复 | audit 输出 | P0 |
| A4 | 确认 `frozen_backtest_validation.py` 可一键复现 | `outputs/validation/frozen_backtest/runs.csv` | P0 |
| A5 | 标记旧报告和当前报告的口径差异 | 文档备注 | P1 |

建议命令：

```powershell
python scripts/check_env.py
pytest -q
python scripts/audit_cache.py --start 20170101 --end 20241231
python scripts/migrate_factor_cache.py --dry-run
python scripts/frozen_backtest_validation.py
python scripts/frozen_backtest_attribution.py
```

验收标准：

- `pytest -q` 全部通过。
- `audit_cache.py` 无 FAIL。
- 冻结验证脚本能完整写出 `outputs/validation/frozen_backtest/runs.csv`。
- PIT 暴露核验中 `future_obs = 0`。
- 文档明确 2025 和 2026 的样本用途。

## Phase B：失败年份归因

目标：解释 D 为什么仍然在多数年份负超额。

重点年份：

- 2017：指数强牛，D 绝对亏损，超额大幅为负。
- 2018：熊市，D 亏损接近指数，但仍未显著跑赢。
- 2019：策略绝对收益为正，但大幅跑输指数。
- 2020：策略绝对收益为正，但仍跑输强势指数。
- 2021：风格切换年份，D 绝对与超额均弱。

任务清单：

| ID | 任务 | 产物 | 优先级 |
|---|---|---|---|
| B1 | 年度月度收益拆解 | `docs/failure_year_monthly_attribution.md` | P0 |
| B2 | 每个失败年 Top/Bottom 个股贡献 | CSV + 文档 | P0 |
| B3 | 行业、市值、波动率、价值暴露归因 | `holdings_style_exposure` 扩展 | P0 |
| B4 | 与 CSI300 基准行业、市值暴露对比 | 暴露差异表 | P1 |
| B5 | fast Top50 与 Phase2 实际持仓差异 | 交集、Jaccard、收益差 | P0 |
| B6 | 交易约束影响拆解 | 涨跌停、停牌、持仓延续、成本 | P1 |

关键问题：

1. 失败年份是选股打分错了，还是打分正确但组合没有买到？
2. D 降低 reversal 后，是不是仍然在 range-bound 中过度暴露弱 sleeve？
3. 2019/2020 跑输强势指数，是因为缺少 beta/动量，还是价值和防御暴露拖累？
4. 2018/2021 熊市或切换期，defensive sleeve 是否真的提供保护？
5. 交易成本和换手是否把微弱 alpha 吃掉？

验收标准：

- 每个失败年能落到至少一个主要失败来源。
- 能区分 alpha 问题和组合构建问题。
- 归因不使用未来数据，不改参数。

## Phase C：因子和 sleeve 池重建

目标：提升底层 alpha 池质量。当前 overlay 只能分配已有 alpha，不能凭空产生收益。

当前因子状态：

| 因子组 | 当前状态 | 判断 |
|---|---|---|
| value: `ep_cs`, `bp_cs`, `sp_cs` | IC 和 ICIR 通过 | 保留并细分 |
| technical/reversal/momentum | 多数未过 IC 门槛 | 需要重审 |
| volatility | 当前表现偏弱 | 不能简单当 alpha |
| size: `log_market_cap_cs` | IC 为负 | 应作为风险暴露而非 alpha |

任务清单：

| ID | 任务 | 产物 | 优先级 |
|---|---|---|---|
| C1 | 统一 Phase1 IC、weekly aligned IC、Top50 经济收益口径 | `docs/factor_signal_alignment.md` | P0 |
| C2 | 对 value 因子做公告滞后、频率、缺失处理复核 | 因子审计表 | P0 |
| C3 | 重算失败年份的因子单因子表现 | 年度 factor report | P0 |
| C4 | 将 size、volatility 从 alpha 候选迁移到风险/约束候选 | 配置建议 | P1 |
| C5 | 设计新因子候选，但每次只新增小批量 | 新 factors config | P1 |
| C6 | 对每个新因子做 no-leakage 单测 | 测试文件 | P0 |

候选方向：

1. 价值类：
   - EP/BP/SP 分位组合稳定性。
   - 价值因子在牛市、熊市、震荡、市值风格切换中的有效性。
   - 基本面因子使用 `ann_date` 或可用日期，避免财报前视。
2. 质量类：
   - ROE、毛利率、盈利稳定性、现金流质量。
   - 先做 PIT 对齐，再进入 alpha 池。
3. 动量类：
   - 中期动量和短期反转分开处理。
   - 不基于单年反转方向。
   - 检查持有期收益与调仓频率是否匹配。
4. 防御类：
   - 低波、低回撤、低 beta 更适合风险控制或熊市 sleeve。
   - 不默认作为全年 alpha。
5. 量价类：
   - PV divergence 当前在 overlay 中有一定改善迹象。
   - 需要拆解是选股 alpha 还是风格暴露代理。

因子进入候选池的最低门槛：

| 指标 | 建议门槛 |
|---|---:|
| 2017-2024 mean IC | > 0.02 |
| ICIR | > 0.30 |
| IC 正向率 | > 52% |
| Top-bottom 年化收益 | 成本前后均不能明显为负 |
| 失败年份表现 | 不得集中在单一年份贡献全部收益 |
| PIT 审计 | future_obs = 0 |

## Phase D：Regime router 与 sleeve 映射重构

目标：让“不同周期、不同趋势使用不同策略”真正穿透到 sleeve 权重，而不是大多数时间停在 range-bound 和 reversal。

当前观察：

- 多个年份主导 regime 仍偏 `range_bound_prob`。
- D 通过降低 reversal、提高 value/volume_price/momentum 改善 C。
- overlay 在多数年份能改善，但不能彻底修复负超额。
- 2025 显示 B dynamic 比 regime router 更灵敏，说明显式 regime 可能切换过慢或映射太粗。

任务清单：

| ID | 任务 | 产物 | 优先级 |
|---|---|---|---|
| D1 | 统计每年每月 regime 概率和市场真实状态一致性 | regime calibration report | P0 |
| D2 | 检查 trend_up/trend_down/range/high_vol/value_rotation 的触发滞后 | 滞后分析表 | P0 |
| D3 | 将 sleeve 表现 overlay 与 regime 概率分开评估 | 两层归因表 | P0 |
| D4 | 设计少量可解释候选映射 | 2-3 个 frozen configs | P1 |
| D5 | 对候选映射先跑 fast，再跑完整 Phase2 | 对比报告 | P1 |

候选假设：

1. Range-bound 不应天然高配 reversal。当前历史显示 reversal 并非多数年份稳定收益来源。
2. Trend-up 中 momentum/volume_price 应更快穿透，但必须防止 2021/2024 错配。
3. Trend-down 中 defensive 不应只看低波，还要看相对基准行业和市值暴露。
4. Value rotation 不应只依赖市场状态，也要看 value sleeve 自身近期 mature IC 和 top-bottom 收益。
5. Overlay 乘数需要区分“近期 IC 好”和“实际组合能买到”的差异。

候选配置数量限制：

- 每轮最多 3 个新候选。
- 每个候选必须写清楚经济假设。
- 候选冻结后再跑验证，不边看边改。

## Phase E：组合构建和交易执行拆解

目标：确认完整 Phase2 是否把 fast 选股层的改善吃掉。

已知线索：

- 2025 fast 与完整 Phase2 分歧明显。
- 完整流程包含 tradable、持仓延续、成本、调仓、权重上限等约束。
- 当前 Phase3 优化报告显示 optimizer 没有真正运行，组合优化线还未闭环。

任务清单：

| ID | 任务 | 产物 | 优先级 |
|---|---|---|---|
| E1 | fast Top50 与 Phase2 holdings 逐期交集 | `fast_vs_phase2_overlap.csv` | P0 |
| E2 | 分解未买入高分股票的原因 | tradable/limit/suspend/buffer/cap | P0 |
| E3 | 拆解换手和成本对收益的拖累 | 成本归因表 | P0 |
| E4 | 测试 entry_rank / exit_rank / holding buffer | 小规模候选报告 | P1 |
| E5 | 修复或暂时下线 Phase3 optimizer 验证口径 | `optimization_report.md` 更新 | P1 |
| E6 | 检查行业、市值、beta 与基准偏离 | 风险暴露表 | P1 |

需要回答：

1. 若 fast Top50 有效，为什么 Phase2 没吃到？
2. 是交易不可行，还是持仓延续导致换手不足？
3. 是成本过高，还是选股收益本身太薄？
4. top_n=50 和 weight_max=2% 是否导致组合过于机械？
5. 是否需要从等权切换到风险约束或分数强度权重？

## Phase F：冻结候选和正式复验

目标：形成少数候选并做真正验证。

流程：

1. 基于 Phase B-E 形成候选规则。
2. 写出候选配置和假设说明。
3. 只允许在 2023/2025 诊断集验证“问题是否被修复”。
4. 冻结后跑 2017-2024。
5. 单独观察 2026 YTD。
6. 生成最终 GO / NO-GO。

候选命名建议：

```text
configs/factors_candidate_v1.yaml
configs/regime_candidate_v1.yaml
configs/regime_candidate_v2.yaml
configs/regime_candidate_v3.yaml
```

候选记录必须包含：

- 修改了什么。
- 为什么修改。
- 预期改善哪个失败场景。
- 可能伤害哪个年份或状态。
- 是否改变数据可用性或 PIT 假设。

正式复验命令模板：

```powershell
python run_research.py phase2 --start 20170101 --end 20171231 --top-n 50 --no-recompute --factors-config configs/factors.yaml --strategy-mode regime --regime-config configs/regime_candidate_v1.yaml
python run_research.py phase2 --start 20180101 --end 20181231 --top-n 50 --no-recompute --factors-config configs/factors.yaml --strategy-mode regime --regime-config configs/regime_candidate_v1.yaml
python run_research.py phase2 --start 20190101 --end 20191231 --top-n 50 --no-recompute --factors-config configs/factors.yaml --strategy-mode regime --regime-config configs/regime_candidate_v1.yaml
python run_research.py phase2 --start 20200101 --end 20201231 --top-n 50 --no-recompute --factors-config configs/factors.yaml --strategy-mode regime --regime-config configs/regime_candidate_v1.yaml
python run_research.py phase2 --start 20210101 --end 20211231 --top-n 50 --no-recompute --factors-config configs/factors.yaml --strategy-mode regime --regime-config configs/regime_candidate_v1.yaml
python run_research.py phase2 --start 20220101 --end 20221231 --top-n 50 --no-recompute --factors-config configs/factors.yaml --strategy-mode regime --regime-config configs/regime_candidate_v1.yaml
python run_research.py phase2 --start 20230101 --end 20231231 --top-n 50 --no-recompute --factors-config configs/factors.yaml --strategy-mode regime --regime-config configs/regime_candidate_v1.yaml
python run_research.py phase2 --start 20240101 --end 20241231 --top-n 50 --no-recompute --factors-config configs/factors.yaml --strategy-mode regime --regime-config configs/regime_candidate_v1.yaml
python run_research.py phase2 --start 20260101 --end 20260605 --top-n 50 --no-recompute --factors-config configs/factors.yaml --strategy-mode regime --regime-config configs/regime_candidate_v1.yaml
```

建议后续把上述重复命令固化进脚本，避免手工执行造成漏项。

## 6. GO / NO-GO 标准

### 6.1 硬性门槛

候选策略进入下一阶段至少应满足：

| 指标 | 门槛 |
|---|---:|
| 2017-2024 平均年化超额 | > 2% |
| 2017-2024 中位数年化超额 | > 0% |
| 正超额年份 | >= 5/8 |
| 平均 IR | > 0.30 |
| 最大单年超额亏损 | 不低于 -10% |
| 最大回撤 | 不明显劣于基准和当前 D |
| 平均换手 | 不高于当前 D 或有收益补偿 |
| 成本 2x | 仍保持非灾难性 |
| PIT 审计 | future_obs = 0 |
| 2026 YTD | 不明显反向，且标记为观察 |

### 6.2 软性门槛

以下不是单独否决项，但必须解释：

- 某一年收益主要来自单月或单只股票。
- 组合明显偏离沪深300行业或市值结构。
- 某个 sleeve 权重长期被 overlay 压到无效。
- fast 与 Phase2 长期大幅分歧。
- 因子 IC 通过但经济收益不通过。

### 6.3 NO-GO 条件

出现任一情况，应停止该候选：

- 验证集平均超额仍为负，且改善主要来自一个年份。
- 2023/2025 修复后，2017-2024 多数年份恶化。
- 成本 2x 后收益完全消失。
- 任何新因子存在 PIT 或 forward return 泄漏风险。
- 候选无法被固定配置复现。

## 7. 建议执行顺序

第一轮，收口和归因：

1. 跑 Phase A 验证链路。
2. 扩展 frozen attribution，重点输出失败年份月度、行业、市值、个股贡献。
3. 补 fast-vs-Phase2 差异归因。
4. 写 `docs/failure_year_monthly_attribution.md`。

第二轮，底层 alpha 修复：

1. 统一因子三层口径。
2. 重审 value、momentum、reversal、defensive 的 sleeve 定义。
3. 对明确无效因子降权、移出 alpha 或改为风险约束。
4. 只新增少量有 PIT 保证的新因子。

第三轮，候选策略冻结：

1. 形成 2-3 个候选配置。
2. 先用 2023/2025 做失败场景检查。
3. 冻结配置。
4. 跑 2017-2024 和 2026 YTD。
5. 生成候选对比报告。

第四轮，决策：

1. 若通过 GO 标准，进入 Phase 3 或风险约束组合构建。
2. 若只相对改善但绝对仍负，保留研究候选，继续因子池重建。
3. 若多数年份无改善，停止 regime overlay 路线，回到 factor dynamic 或新 alpha 方向。

## 8. 需要新增或完善的文档

建议新增：

| 文档 | 目的 |
|---|---|
| `docs/failure_year_monthly_attribution.md` | 解释 D 失败年份 |
| `docs/factor_signal_alignment.md` | 统一 IC、aligned IC、Top50 收益口径 |
| `docs/fast_vs_phase2_gap.md` | 解释简化回测和完整回测差异 |
| `docs/candidate_freeze_log.md` | 记录每个候选配置的假设和冻结时间 |
| `docs/go_nogo_decision.md` | 最终上线或停止路线判断 |

建议更新：

| 文档 | 更新内容 |
|---|---|
| `docs/frozen_backtest_validation.md` | 每次冻结验证后刷新 |
| `docs/frozen_backtest_attribution.md` | 补失败年份深度归因 |
| `README.md` | 等验证链路稳定后更新推荐命令 |
| `outputs/validation_report.md` | 清除旧 FAIL 状态造成的误导 |

## 9. 工程注意事项

1. Windows 控制台编码曾经造成日志读取问题，长任务建议使用 `python -X utf8`。
2. `outputs/validation_report.md` 当前可能是旧口径，不能单独作为最新状态。
3. `Phase3` 当前报告显示 optimizer 没有真正运行，不应把 Phase3 当已验证能力。
4. `2026` 样本不足，任何正收益都不能被当成稳定结论。
5. `2025` 已参与候选形成，只能用于诊断，不可作为最终 OOS。
6. 所有新增因子必须先过 no-leakage 和 PIT 审计。
7. 每次重跑 Phase0/缓存写入前，应确认不会降低已有宽窗口缓存覆盖。

## 10. 最近一次可执行 TODO

优先级最高的下一批工作：

| 顺序 | 任务 | 完成标志 |
|---:|---|---|
| 1 | 跑 `pytest -q`、`audit_cache.py`、`frozen_backtest_validation.py` | 三者无失败 |
| 2 | 刷新 `validation_report.md` 或标记旧报告失效 | 当前状态不再冲突 |
| 3 | 扩展失败年份归因脚本 | 能输出 2017-2021 的月度和个股贡献 |
| 4 | 产出 `factor_signal_alignment.md` | 因子去留有统一证据 |
| 5 | 产出 `fast_vs_phase2_gap.md` | 解释 fast 与 Phase2 差异 |
| 6 | 形成候选 v1-v3 | 每个候选有经济假设 |
| 7 | 跑冻结复验 | 有 2017-2024 + 2026 YTD 对照 |
| 8 | 写 GO/NO-GO | 明确继续、暂停或换方向 |

## 11. 当前推荐判断

推荐继续推进，但不要把当前 D 作为生产策略。

最优下一步不是继续调参数，而是做三件事：

1. 失败年份归因：确认 D 的负超额到底来自哪一层。
2. 因子池重建：提高底层 alpha 的可交易质量。
3. fast-vs-Phase2 拆解：确认信号是否能穿透到真实组合。

只有这三件事闭环后，再做候选配置冻结和跨年验证，才有机会真正回答“一个策略能否覆盖全年不同周期、不同趋势”。

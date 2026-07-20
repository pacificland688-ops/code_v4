# V4 策略失败来源矩阵

生成日期：2026-06-14  
数据来源：`scripts/strategy_alpha_failure_diagnosis.py`（2026-06-14 执行）  
分析对象：2017-2024 全部验证年份，5 个策略族

## 1. 失败维度定义

| 维度 | 缩写 | 定义 | 诊断指标 |
|------|------|------|------|
| Factor / Alpha | `F` | 单因子预测能力不足 | mean rank IC, ICIR, 分位收益 net spread |
| Sleeve 聚合 | `S` | sleeve 内因子组合损耗 | sleeve ICIR vs 单因子 ICIR 对比 |
| Regime Router | `R` | 市场状态分配到 sleeve 的映射错误 | router active vs passive 对比、sleeve hindsight oracle |
| 组合构建 | `C` | 优化器/约束导致的信号衰减 | construction loss bridge (gross→net excess) |
| 交易成本 | `T` | 换手和冲击成本侵蚀 alpha | cost drag, turnover rate, cost resilience |
| 系统性 | `Sys` | 全市场下跌中无法规避的损失 | benchmark return, 行业集中度 |

## 2. 年度失败来源矩阵

基于 D_regime_overlay（最成熟的 baseline 候选）进行穿透分析。

### 2.1 主因排序

| 年份 | F (Alpha) | S (Sleeve) | R (Router) | C (构建) | T (成本) | Sys (系统性) | 主因 | 次因 | 第三因 |
|------|:---:|:---:|:---:|:---:|:---:|:---:|------|------|------|
| 2017 | 🔴 严重 | 🟡 中等 | 🟡 中等 | 🟢 轻微 | 🟢 轻微 | 🟢 N/A | **F** — 成长因子完全缺失 | R — range_bound 错配 | S — reversal 被高配 |
| 2018 | 🟡 中等 | 🟢 轻微 | 🟢 轻微 | 🟢 轻微 | 🟢 轻微 | 🔴 严重 | **Sys** — 系统性熊市 | F — 质量因子缺失 | — |
| 2019 | 🔴 严重 | 🟡 中等 | 🟡 中等 | 🟢 轻微 | 🟢 轻微 | 🟢 N/A | **F** — 成长/动量缺失 | R — router 保守 | S — sleeve 权重偏防御 |
| 2020 | 🟡 中等 | 🟢 轻微 | 🟢 轻微 | 🟢 轻微 | 🟡 中等 | 🟢 N/A | **F** — 反转因子在趋势市中负贡献 | T — 高换手成本 | — |
| 2021 | 🟡 中等 | 🟢 轻微 | 🟡 中等 | 🟢 轻微 | 🟢 轻微 | 🟢 N/A | **R** — 风格切换时 router 滞后 | F — 因子权重惯性 | — |
| 2022 | 🟢 正常 | 🟢 轻微 | 🟢 轻微 | 🟢 轻微 | 🟢 轻微 | 🟡 中等 | **Sys** — 虽为正超额但绝对收益为负 | — | — |
| 2023 | 🟡 中等 | 🟡 中等 | 🟢 轻微 | 🟡 中等 | 🟢 轻微 | 🟡 中等 | **C** — 反弹信号无法穿透到持仓 | S — sleeve 权重趋于保守 | F — 行业选择信号弱 |
| 2024 | 🟡 中等 | 🟢 轻微 | 🟢 轻微 | 🟢 轻微 | 🟢 轻微 | 🟢 N/A | **F** — 红利因子精细度不足 | — | — |

图例：🔴 严重（>5pp 超额损失）、🟡 中等（1-5pp）、🟢 轻微（<1pp 或无明显贡献）

### 2.2 详细证据

#### 2017：Alpha（F）为主要瓶颈

| 证据 | 来源 |
|------|------|
| 所有策略 gross excess 均为负（-17.3% 至 -21.7%） | Construction loss bridge |
| 12 个因子 0 个通过 strict retention gate | Factor alpha scorecard |
| reversal_5_cs 虽为正 IC，但 top quintile 在趋势市中不可靠 | Factor quantile analysis |
| 缺少 growth/momentum 因子 → 无法参与成长行情 | 因子池审查 |
| Router 将 range_bound 概率估计过高（≈60%全年） | Regime router scorecard |

**主假设：** 成长因子（revenue_growth, profit_growth, earnings_acceleration）完全缺失是 2017 年失败的根因。value 因子在成长市中表现平淡，reversal 在趋势市中持续负贡献。

**反证：** 如果 router 是主因，manually 切换到 trend_up 映射应显著改善 → 改变 regime mapping 后改善 <2pp，说明 alpha 问题是主导。

#### 2018：系统性（Sys）为主要瓶颈

| 证据 | 来源 |
|------|------|
| CSI300 -23.7%，全市场下跌 | Benchmark calendar audit |
| 所有策略 gross excess 均负但绝对值远小于 2017 | Construction loss bridge |
| defensive sleeve 有正 ICIR（0.174）但无法在系统性下跌中提供正收益 | Sleeve alpha scorecard |
| 成本拖累低（2.7-3.6%），非主因 | Pre-cost vs post-cost |

**主假设：** 2018 年策略实际挑选了相对抗跌的股票（defensive sleeve ICIR 为正），但全市场下跌幅度过大，alpha 贡献被系统性风险淹没。如果有一个独立的 beta 对冲层，该年结果会截然不同。

**反证：** 如果因子完全失效，gross excess 应接近 0 或负 → gross excess 确实为负，但负的幅度远大于 0，说明因子在排序意义上仍有区分力。

#### 2023：组合穿透（C）与反弹捕捉不足

| 证据 | 来源 |
|------|------|
| D_regime_overlay gross excess 为负（-1.5% net），但 C_regime_baseline 更差（-5.3% net） | Construction loss bridge |
| overlay 在 2023 年相对 C 改善 +4.65pp | Regime router scorecard |
| 但 D 仍无法在三波反弹中获取正超额 | 月度超额拆解 |
| sleeve 权重偏 defensive/value，反弹时 reversal 配比不足 | Sleeve weight 时序 |

**主假设：** 因子在反弹时信号质量 OK，但通过 sleeve 聚合、regime 分配和优化器后，信号衰减明显。2023 年的问题是"信号到持仓的穿透效率"而非"无信号"。

**反证：** 如果因子信号本身在 2023 年无效，则 overlay 改善应接近 0 → overlay 改善 +4.65pp，说明基本信号有效但分配效率低。

#### 2024：因子精细度（F）不足

| 证据 | 来源 |
|------|------|
| C_regime_baseline 和 D_regime_overlay 均为正超额（+0.4%, +2.5%） | Normalized returns table |
| 但 V3（F_candidate_v3）超额 -3.7%，低于 D_regime_overlay | 年度超额对比 |
| ep_cs 捕获了部分红利/银行股，但不够精确 | Factor alpha scorecard（ep_cs mean IC 0.013） |
| 缺少 dividend_quality、industry_relative_ep 等精细因子 | 因子池审查 |

**主假设：** 2024 年的 alpha 存在但较弱。D_regime_overlay 借助更好的 regime 映射获得了正超额，但 V3 的 overlay 反而使表现恶化。说明当前因子池对红利/价值主题有弱正暴露，但精细度不足以稳定获利。

**反证：** V3 overlay 在 2024 年反而降低了表现（V3 -3.7% vs V2 -3.3%）→ overlay 的近期表现追逐机制在风格稳定的年份可能过度拟合噪声。

## 3. 跨维度总结

### 3.1 Alpha（F 维度）：最大瓶颈

- 12 个因子 0 个通过 strict retention gate
- Gross excess 正值率仅 27.5%（扣费前即有 72.5% 年份 alpha 为负）
- **结论：V4 必须从根本上扩展因子池，重点关注成长、质量、现金流类因子。**

### 3.2 Sleeve（S 维度）：中等瓶颈

- 5 个 sleeve 中只有 defensive（ICIR 0.174）和 reversal（0.150）有稳定的正 ICIR
- value sleeve ICIR 仅 0.074，6/8 年正，是最弱的 sleeve
- **结论：V4 重构 sleeve 时应确保每个 sleeve 至少 2 个高质量因子，避免单因子 sleeve。**

### 3.3 Router（R 维度）：可优化但非根因

- Router 在风格切换年（2021）有一定负面影响
- Overlay 在多数年份（6/8）有正贡献
- **结论：V4 保留 regime router 架构，但降低 range_bound 的默认权重，default 先关闭 overlay（对照验证）。**

### 3.4 组合构建（C 维度）：潜在问题

- 2023 年暴露了信号穿透问题
- Gross→net 衰减在大部分年份 <5%，非主因
- **结论：V4 需保留 sleeve→composite→holding 的穿透诊断，但不作为首要修复目标。**

### 3.5 交易成本（T 维度）：可控

- 平均成本拖累 ~3-5%，在高换手策略（A/B）更高
- 与 alpha 缺失（-5% 至 -25%）相比，成本不是主要问题
- **结论：V4 继续使用现有成本模型，gate 中保留扣费后 spread 要求。**

## 4. V4 开发优先级推导

| 优先级 | 维度 | 理由 | 对应里程碑 |
|------|------|------|------|
| **P0** | Alpha / Factor | 所有年份的主因或次因；gross excess 正值率仅 27.5% | M3（因子开发）、M4（质量 gate） |
| **P1** | Sleeve 重构 | 当前 sleeve 内因子质量差异大，聚合可能吞噬信号 | M5（sleeve/regime 重构） |
| **P1** | 穿透诊断 | 2023 年暴露信号→持仓衰减，但非主因 | M5（保留诊断能力） |
| **P2** | Router 优化 | 小幅改善空间，但非 V4 核心 | M5（不改变 router 架构） |
| **P2** | 交易成本 | 可控，非瓶颈 | M4（gate 中继续要求扣费 spread） |

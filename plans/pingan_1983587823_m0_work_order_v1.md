# 平安证券岗位补齐：第一步 M0 实施工单 v1

日期：2026-10-20。岗位：平安证券量化策略研究，1983587823。

工单标识：`pingan.1983587823.m0.work_order.v1`。上位方案：[完整实施方案 v1](C:/Users/cfz/Workspace/ProjectQ/code_v4/plans/pingan_1983587823_implementation_plan_v1.md:136) 的第 6 节。工作区：`C:\Users\cfz\Workspace\ProjectQ\code_v4`。

**交给实施人员的任务：完成范围、代码路径、研究身份、待决事项和履历证据登记，交付 8 个文件及一致性检查。做到 M0 结束，不执行 M1 环境安装、策略修复、训练或回测。**

本文件是交办规范；工单编写完成不代表 M0 已执行。以下目录、文件和字段均为要求实施人员生成的成果，不是已经存在的验收结果。

## 1. 目标与完成定义

完成后，下一位实施人员应能不依赖聊天记录，明确：

1. 本岗位补齐目标及本轮允许范围。
2. 哪些代码已有、哪些仅为规划、哪些历史结论继续有效。
3. 哪些来源和参数已经核实，哪些仍未知，以及未知事项具体阻断哪个阶段。
4. 什么代码/说明被检查过，检查时的文件身份是什么。
5. 本人学历、行业、实盘及协作经历处于何种核验状态。
6. M1 可据什么材料开展离线工程，哪些真实回放和经济判断尚不能启动。

M0 不以数据全部齐备、策略盈利或个人材料齐备为通过条件。通过标准是登记完整、证据可追溯、未知项不被隐藏、阶段边界自洽。M0 通过不等于研究参数冻结、数据就绪或实盘授权。

## 2. 实施责任与操作范围

实施人员负责读取源码和材料、登记事实、计算摘要、组织文件和自查。研究负责人负责确认研究参数、样本及评价协议；个人履历只能由本人提供或核验。上述职责可以由同一人承担，但每项确认仍应记录真实依据，不自动用实施人员身份代替研究或履历确认。

本工单允许：读取列明的本地文件和 Git 元数据；用系统已有 Python 标准库处理 JSON、摘要与元数据；在指定 M0 交付目录写登记文件；在 `plans/quant_plan.md` 追加实施进度。

本工单不包含：修改业务 Python、现有 YAML、历史结果或公共缓存；创建 `.venv-research`、安装/升级依赖；运行现有研究或抓取入口；联网补数、提交真实订单、启动模拟账户；改写旧研究身份或为新研究填入冻结时间。完整环境、通用校验程序和运行清单底座属于 M1。

遇到范围外事项，登记它影响的阶段及解决条件即可，不为完成 M0 提前开发后续模块。

## 3. 必读输入与检查深度

先读本工单及以下两个主文件：

- [完整实施方案](C:/Users/cfz/Workspace/ProjectQ/code_v4/plans/pingan_1983587823_implementation_plan_v1.md:1)。
- [本岗位评估](C:/Users/cfz/Workspace/ProjectQ/code_v4/reports/liepin_1983587823_research_fit_20261019.md:1)。

随后读取并登记以下相对路径；只检查文本、接口与既有归档，不执行文件：

```text
AGENTS.md
requirements.txt
pytest.ini
.gitignore
configs/sample_windows_v1.yaml
validation/sample_windows.py
configs/vehicle_compare_v1.yaml
scripts/run_product_backtests.py
products/weekly_long.py
products/metrics.py
scripts/run_frozen_product_compare.py
backtest/portfolio_backtester.py
backtest/execution.py
live/run_shadow.py
outputs/frozen_runs/product_compare_2017_2024_ledger_v6/DECISION.md
outputs/frozen_runs/product_compare_2017_2024_ledger_v6_fulluniv_r8/DECISION.md
outputs/analysis/sector_panic/rebuild_v1/p1_minimal_economic_review_20260924/metrics.json
momentum_pullback/README.md
```

必读文件缺失或无法读取时，不用空文本代替；在清单和 `handover.md` 中登记，未完成的必读核验不判为通过。文件实际内容与本工单所述现状不一致时，以本次读取为事实，登记差异和影响，不将旧描述强行写成当前结果。

本轮不要求扫描全部 Parquet。总方案中 8 个 ETF 年度文件、18,833 行及早期 9 代码的说明，只能标为已有记录；它不证明正式上市日期、逐日覆盖或公司行动完整。逐日数据审计留给 M2。

## 4. 交付目录与 8 个文件

创建独立批次目录：

```text
plans/pingan_1983587823_m0/<package_id>/
  scope.json
  path_map.json
  research_identity.json
  decision_log.json
  claims_register.json
  evidence_manifest.json
  checks.json
  handover.md
```

`package_id` 格式为 `m0-YYYYMMDDTHHMMSSZ`，使用实际 UTC 创建时间，8 个文件使用同一 ID；交易时间语义登记为 Asia/Shanghai。目标目录已存在则新建批次，不覆盖。工作目录先使用同一父目录下的暂存名，完成自查后再将整批目录提升为正式名称；`checks.json` 最后写入。

所有 JSON 为 UTF-8、标准 JSON，不使用 NaN、注释或占位字符串。未知值使用 `null` 并配状态和理由；缺必填字段与“字段存在但未知”是不同情况。

### 4.1 scope.json：工程范围

必填字段：`schema_version`、`package_id`、`job_id`、`milestone`、`target`、`mode`、`created_at`、`trading_timezone`、`scope_status`、`allowed_work`、`deferred_work`、`research_execution_allowed`、`economic_judgement_allowed`、`paper_trading_allowed`、`live_trading_allowed`、`research_freeze_timestamp`、`source_refs`。

固定范围值：

```json
{
  "schema_version": "pingan.m0.scope.v1",
  "job_id": "1983587823",
  "milestone": "M0",
  "target": "JOB_PORTFOLIO_V1",
  "mode": "OFFLINE",
  "trading_timezone": "Asia/Shanghai",
  "scope_status": "REGISTERED",
  "research_execution_allowed": false,
  "economic_judgement_allowed": false,
  "paper_trading_allowed": false,
  "live_trading_allowed": false,
  "research_freeze_timestamp": null
}
```

该示例仅展示固定值，正式文件还必须补齐全部必填字段。`allowed_work` 写本工单的登记、文本核验与摘要；`deferred_work` 明确列 M1—M8 的未执行工作。`source_refs` 指向上位方案和本工单的清单条目。

### 4.2 path_map.json：已有与拟建路径

顶层字段为 `schema_version=pingan.m0.paths.v1`、`package_id` 和 `routes`。每条路线含 `route_id`、`purpose`、`implementation_status`、`entry`、`call_chain`、`input_semantics`、`execution_semantics`、`known_limits`、`evidence_refs`、`next_stage`。

至少登记 4 条路线：

- `ETF_LEGACY_CLOSE_DIAGNOSTIC`：追踪 `scripts/run_product_backtests.py::run_etf` → `_etf_panel` → `products.weekly_long.run_index_weekly`。核对是否仅保留 close、60/20 评分及波动最小观测数、最多 4 只、按可见日期每 5 个交易日调仓、`exec_lag=1` 后实际取 close。不要把该路径写成开盘成交。
- `STOCK_PERIODIC_DIAGNOSTIC`：登记 `backtest/portfolio_backtester.py` 与 `backtest/execution.py` 的实际入口及相关函数，标注协方差截止、收益起点和 T+1 参数为静态待复现事项。M0 不将它们直接判为已证实缺陷或已修复。
- `ETF_CAUSAL_REPLAY_PLANNED`：引用总方案拟建的 ETF 适配器、信号与账本。文件尚不存在时明确 `implementation_status=NOT_IMPLEMENTED`，摘要为 null，不能把规划中的 CLI 当作可执行入口。
- `EXISTING_RESEARCH_CASE`：绑定板块 P1 归档的真实运行身份与指标文件，记录研究使用、经济证据不足和无实盘权限等实际字段。该路线用于案例整理，不重开参数搜索。

每项语义都区分“当前源码读取核实”“历史归档声明”和“拟建”。函数存在不等于路径已经通过运行验收，所有新运行检查保持未执行。

### 4.3 research_identity.json：研究身份与历史使用边界

顶层必填：`schema_version=pingan.m0.identity.v1`、`package_id`、`candidate_identity`、`status=DRAFT`、`freeze_timestamp=null`、`inherited_records`、`viewed_range_review_status`、`known_viewing_records`、`unresolved_items`、`can_claim_oos=false`、`can_approve_live=false`。

- `candidate_identity` 建议为 `pingan_etf_research_candidate_v1`，它是候选名，不宣称合同已冻结。
- `inherited_records` 原样摘录 `configs/sample_windows_v1.yaml` 与对应实现的身份、声明查看区间、原冻结日期及权限，附来源摘要和行号。旧身份的冻结日期不能填成新身份的冻结时间。
- 新身份的查看范围审查未完成时填 `viewed_range_review_status=PENDING_REVIEW`，保留已知查看记录；不得默认从旧配置日期之后立即拥有新 OOS。
- 存在其他已查看历史但未能核清时，记录未知项，保持 OOS 权限关闭。交付包创建时间、工单签认时间和研究冻结时间不得混用。

当前未知查看范围不阻断 M1 合成夹具和离线工程，阻断新的独立样本有效性宣称。登记不得覆盖原 sample_windows 文件或在研动量回调合同。

### 4.4 decision_log.json：决策与阶段阻断

顶层为 `schema_version=pingan.m0.decisions.v1`、`package_id`、`decisions`。每条必填 `decision_id`、`kind`、`subject`、`status`、`value`、`reason`、`owner_role`、`decided_by`、`decided_at`、`evidence_refs`、`blocks`、`resolution_condition`。

`kind` 使用 `ENGINEERING_SCOPE`、`SOURCE_FACT` 或 `RESEARCH_RULE`；状态使用 `CONFIRMED`、`PROPOSED`、`UNRESOLVED`、`DEFERRED`、`NOT_APPLICABLE`。

`CONFIRMED` 必须有真实依据、确认者、时间和明确值。仅有旧代码默认参数，最多证明旧代码事实；它不能自动确认新研究规则。未确认时 `decided_by/decided_at` 留 null，不以自动采集的操作系统用户名冒充本人或研究负责人批准。

至少登记以下 11 项，并写明逐项阻断：

1. `DEC-M0-01`：本轮求职作品集、离线与 M0 范围；范围不清影响 M0 本身。
2. `DEC-M0-02`：新旧身份、已查看区间与冻结关系；审查未完成阻断 OOS 宣称，不阻断 M1 离线基础。
3. `DEC-M0-03`：ETF 候选池及逐日资格来源；未核实阻断 M3 真实经济回放，不阻断 M2 审计。
4. `DEC-M0-04`：分红、份额折算、价格尺度与覆盖来源；未核实阻断相应真实经济回放。
5. `DEC-M0-05`：交易状态、日历、未知状态处理与历史可得性；缺来源阻断相应真实回放，不自动视为正常交易。
6. `DEC-M0-06`：费用、交易单位、价格步长与到账；未绑定阻断真实经济回放，允许 M1 手工账夹具。
7. `DEC-M0-07`：预提交限价、事前数量、预留、候选不足及未成交；提案可以登记，未冻结阻断 M3 真实研究回放，不阻断 M1 合成反例。
8. `DEC-M0-08`：研究区间、主基准、主指标与变体登记；未定稿阻断新的真实研究回放及择优评价。
9. `DEC-M0-09`：最低经济增量、统计与覆盖协议、试验预算；未冻结阻断 M4 经济通过判定，不把它扩大为 M1/M2 阻断。
10. `DEC-M0-10`：分时数据来源与权限；未具备时 M5 只能进入明确标注的合成工程演示，不阻断日频基础。
11. `DEC-M0-11`：TensorFlow 的实际任务与对照必要性；未定稿阻断 M7，不能假装已掌握或已有增量。

`blocks` 为阶段/能力及布尔值的明确映射，至少涵盖 `M1_OFFLINE_FOUNDATION`、`M2_OFFLINE_AUDIT`、`M3_REAL_RESEARCH_REPLAY`、`M4_ECONOMIC_ACCEPTANCE`、`M5_REAL_EXECUTION_STUDY`、`M7_ML_STUDY`、`NEW_OOS_CLAIM`。一项可以只阻断部分能力，不允许用“全部待确认”代替判断。

个人履历的未知项另入 claims，不与数据/工程阻断混用。新增参数提案一律登记来源和理由，不在 M0 根据收益选择数值。

### 4.5 claims_register.json：履历与本人贡献

顶层为 `schema_version=pingan.m0.claims.v1`、`package_id`、`claims`。至少分开登记学历/专业、证券基金量化年限、真实实盘、客户/培训协作、项目职责与独立贡献。

每项字段为 `claim_id`、`subject`、`status`、`claim_text`、`evidence_ref`、`disclosure_status`、`verified_by`、`verified_at`、`notes`。状态允许 `NOT_PROVIDED`、`SELF_REPORTED_UNVERIFIED`、`EVIDENCE_REFERENCED`、`VERIFIED_FOR_DISCLOSURE`、`NOT_APPLICABLE`。

没有提供时，状态为 `NOT_PROVIDED`、事实和证据字段为 null；这表示未知，不代表没有相关经历。不要以 Git 年份、数据跨度、代码量或 AI 生成文档证明行业年限。登记文件仅保存必要的核验状态和可披露索引，不将敏感个人证明复制到仓库。

### 4.6 evidence_manifest.json：本次检查的证据快照

顶层含 `schema_version=pingan.m0.evidence.v1`、`package_id`、`created_at`、`workspace_observation`、`source_files`、`package_files`、`excluded_from_digest`、`notes`。

- `workspace_observation` 登记工作区、Git HEAD/分支、选定输入的变更状态、remote 名称、CI 类型判断及现有解释器路径/版本。无 remote 或未确定 CI 可明确记录，不阻断本地 M1。
- `source_files` 包含本工单、总方案、最新评估及第 3 节必读文件。每项含相对路径、字节数、SHA256、检查时间、用途与 `read_status`。纳入实际读取的未提交文件，不仅记录 Git HEAD；额外输入也必须登记。
- `package_files` 包含 `scope.json`、`path_map.json`、`research_identity.json`、`decision_log.json`、`claims_register.json`、`handover.md` 的实际摘要。
- 清单本身及最后生成的 `checks.json` 不进入自身摘要闭环；`checks.json` 反向记录本清单 SHA256。`plans/quant_plan.md` 是可追加进度日志，不作为稳定消费输入锁定，理由写入 `excluded_from_digest`。

这是 **M0 文本检查与登记快照**，不是 M1 的完整运行输入锁，也不是 M2 的市场数据覆盖证明。禁止据此声称所有数据已冻结或可完整回测。

不得读取或摘要 `.env`、token 文件、账户配置及无关个人目录。Git remote 只记录名称和必要的托管类型；不输出可能含凭证的完整 URL。

### 4.7 checks.json：最后生成的自查结果

必填 `schema_version=pingan.m0.checks.v1`、`package_id`、`checked_at`、`manifest_sha256`、`status`、`checks`、`unresolved_summary`、`handover_eligibility`、`performed_by`。

`status` 为 `NOT_RUN`、`PASS` 或 `FAIL`。`checks` 对应第 7 节全部编号，每项含 `id`、`passed`、`evidence_refs`、`details`；尚未执行不能填通过。`handover_eligibility` 表达技术移交条件，不是自行启动下一阶段的授权。

`handover_eligibility` 各阶段值使用 `READY_FOR_HANDOVER`、`WAIT_PREREQUISITES` 或 `BLOCKED`，并附 `reason` 和 `remaining_prerequisites`。M0 全部合格时，M1 可记 `READY_FOR_HANDOVER`；正式 M2 审计仍须满足 M1 环境与输入条件，未核验这些前提时记 `WAIT_PREREQUISITES`。decision_log 中“不被某项未知阻断”也不代表该阶段所有前提都已满足。后续真实运行汇总各项决策及上游依赖，不能因 M0 PASS 自动设为可进入。

### 4.8 handover.md：实施回传说明

按以下顺序写：任务与范围；本次实际读取和执行的命令；已有/拟建路径；身份与查看历史；已确认事项；待决事项及阻断阶段；履历状态；输入差异和异常；M1 接手清单；本次未执行工作。

标清登记包通过与研究数据/经济状态的区别。事实、提案、未知项分开叙述；链接本批相对路径和必要源码，不把历史测试写成本次新测。

## 5. 执行顺序

### M0-01：建立只读基线

确认工作区与上位方案，读取第 3 节材料。记录必读输入实施前的字节数与 SHA256，后续用于确认源文件未被改写。只对列明输入读取 Git 状态，避免把整个工作区的无关临时文件混入证据。

可用的只读命令示例，先在项目根目录运行：

```powershell
Get-Location
git --no-optional-locks rev-parse --show-toplevel
git --no-optional-locks rev-parse HEAD
git --no-optional-locks branch --show-current
git remote
Get-Command python -ErrorAction SilentlyContinue | Select-Object Source
python -c "import sys; print(sys.executable); print(sys.version)"
```

无 Git HEAD、无解释器或文件无法读时如实登记；是否影响检查按具体任务判断，不制造成功结果。命令不得输出凭证或完整 remote URL。Python 依赖如需探查，只用 `importlib.metadata` 读分发元数据，不导入项目或第三方包，不安装缺包。

### M0-02：创建 scope 与 path_map

在全新暂存批次写范围与四条路径。读取实际函数体核对字段、价格和时钟，引用相对路径与当前行号。确认拟建文件是否存在；存在时核查来源和版本，不直接覆盖，也不继续写“尚未实现”。

### M0-03：登记研究身份

摘录既有身份，分别保存原身份冻结日期、已查看历史声明与新候选身份。保留新冻结时间 null 和关闭的 OOS/实盘权限。旧历史和停止推进的归档仅引用，不修改。

### M0-04：登记 11 项决策

逐项填写已知、提案、未知、责任角色、解决条件和阶段阻断。工程范围可依据已接受方案登记；研究数值与外部数据事实缺依据时保持未知，不要求先补齐全部来源才能完成 M0。

### M0-05：登记履历及交付元数据

未提供履历时保留未知。记录工作区、选定源码变更、已有解释器及 CI 条件；该记录不宣称环境已通过测试。完成 `handover.md` 的事实性说明。

### M0-06：生成清单并自查

先完成六个内容文件，再生成 evidence_manifest；复核源文件前后摘要一致、六个成果摘要一致。逐项执行第 7 节检查，在内存中准备 checks 的候选内容，核对字段和状态后最后写入；写后重新读取 8 个文件，确认格式、摘要和交付完整性，再判断能否提升目录。写后校验失败则该批不能以 PASS 移交。若必读输入在过程中变化，停止本次成功判定，记录失败原因并用新批次重新检查，不将前后不同版本拼成同一快照。

### M0-07：提交移交包

检查通过后完成目录提升，追加 `plans/quant_plan.md` 的 M0 实施记录，并按第 8 节回传。失败批次保留明确状态，不覆盖为成功。到此结束，不执行 M1 安装或运行拟建 CLI。

## 6. 典型未知项的处理

- 履历未提供：claims 为未知，M1 可接手；不能声称已符合三年从业要求。
- ETF 公司行动或状态来源未知：M2 继续审计；相应 M3 真实经济回放阻断。
- 限价、现金预算、基准或研究区间仅有提案：允许 M1 夹具，新的真实研究回放待合同冻结。
- 最低经济增量和统计协议未定：经济通过判定关闭，不把工程通过写成 Alpha 通过。
- 分时数据未具备：M5 真实执行效果研究阻断；日频基础不受其阻断，合成验证需另在对应阶段标明范围。
- 输入文件在本次检查中变动：本批自查失败，不能用“文件最后存在”代替同版性检查。

## 7. M0 验收清单

以下均是需要实施人员实际检查的项目，当前没有任何一项因本工单写好而自动通过：

- **M0-AC-01 文件与格式：** 8 文件齐全，JSON 可解析，版本正确，package_id 一致，job_id 仅为 1983587823；未知字段按约定表达。
- **M0-AC-02 范围：** mode 为 OFFLINE，四个运行/判定开关均为 false，新研究冻结时间为 null；允许与延后任务清楚。
- **M0-AC-03 路径：** 四条路线存在于登记中，已有、静态待复现和拟建状态分明；ETF 旧收盘代理未写成开盘成交。
- **M0-AC-04 研究身份：** 原身份与新身份分离，查看历史未被清零，没有因新的目录、日期或策略名称获得 OOS/实盘权限。
- **M0-AC-05 决策：** 11 项齐全、ID 唯一；所有 CONFIRMED 项具备真实值、依据、确认者和时间；提案未伪装成冻结规则。
- **M0-AC-06 阶段阻断：** 未知数据/研究事项阻断相应真实运行；履历、分时与 ML 等局部未知不被扩大成所有离线工作的阻断。
- **M0-AC-07 履历：** 缺资料时为 NOT_PROVIDED，未填“无经验”或虚构独立开发、实盘和客户经历；材料披露范围清楚。
- **M0-AC-08 输入证据：** 必读文件均实际核验，源码摘要覆盖读取的未提交内容；额外引用也登记，引用能定位。
- **M0-AC-09 摘要闭环：** 六个内容文件与清单一致，checks 中 manifest 摘要可复核；不要求 manifest 包含自身或 checks 摘要。
- **M0-AC-10 源文件与操作边界：** 必读输入前后摘要一致；没有业务修改、依赖安装、数据抓取、研究运行或旧结果覆盖。
- **M0-AC-11 真实执行状态：** handover 与 checks 同版，命令和验证如实记录，历史测试与本次检查不混用，未实施功能不生成成功结果。
- **M0-AC-12 移交：** handover 写明 M1 输入、待决条件、后续阻断和负责人角色；M0 PASS 未被表述为数据就绪、经济有效或自动进入下一阶段。

任一必须检查未执行或失败，则 checks 不得为 PASS。数据来源未知、履历未提供等允许的未决事项，若已经正确登记并隔离阶段，不导致 M0-AC 自动失败。

## 8. 实施人员回传格式

回传控制在一页摘要，附 8 文件目录及相对链接：

```text
工单：pingan.1983587823.m0.work_order.v1
交付批次：实际 package_id 与目录
M0 检查：PASS 或 FAIL；已执行/未执行检查及证据
输入快照：manifest 摘要、Git 信息、源文件是否保持一致
路径核对：已有路径、静态疑点、拟建路径各自的状态
身份边界：候选身份、原历史声明、新冻结时间与权限
待决事项：11 项状态汇总，每个未决项的阻断阶段和解决条件
履历：核验状态，不披露不必要个人细节
M1 移交：可接手的离线工作与仍受阻断的真实运行
未执行：安装、业务修复、数据获取、训练、回测、模拟/真实交易
```

预计投入为熟悉项目的实施人员 1—2 个有效工作日，包含阅读、登记和自查，不含外部事实补齐。该估计不作为必须填满全部研究参数的期限。

## 9. 可直接转发的执行指令

> 请在 `C:\Users\cfz\Workspace\ProjectQ\code_v4` 按本工单完成平安岗位 1983587823 的 M0。先读取总方案、岗位评估和必读输入，建立只读基线；在 `plans/pingan_1983587823_m0/<package_id>/` 交付规定的 8 个文件。逐条核实已有 ETF 收盘代理、股票周期静态疑点、拟建 ETF 路径和既有研究归档。新研究身份保持 DRAFT、冻结时间 null、OOS 和实盘权限关闭。11 项决策逐项登记责任、证据和阶段阻断，履历未提供保留未知。生成实际文件摘要并执行 12 项 M0 验收，最后写 checks 和回传摘要。不要修改业务代码、安装环境、获取新数据、运行训练/回测或进入 M1。未知来源允许登记，但不能放行相应真实研究或经济判定；M0 是否通过以本工单的一致性和边界验收为准。

## 10. 本次工单编写记录

2026-10-20 仅核对总方案、当前目录和必要参考文件的存在性。检查时 `research_delivery/`、拟建 ETF 三个业务文件、`.venv-research` 和 M0 交付目录均尚不存在；实施人员应在实际接手时复核，不把该记录当作实时状态。

本次没有创建 8 文件登记包，没有执行 M0 验收、环境安装或任何策略实验。工单正文与其链接检查属于方案编制质量检查，不能写入实施人员的 M0 PASS 证据。

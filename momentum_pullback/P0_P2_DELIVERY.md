# P0—P2 首批交付记录

2026-10-14。**P0 配置与隔离环境通过；P1/P2 核心逻辑通过合成工程验收；真实数据门阻断，未进入真实事件构建或 P3。** 研究参数维持 `DRAFT/PROPOSED`、`freeze_timestamp=null`，没有收益标签、收益分析、参数搜索、AVWAP 或股票池扩展。

审阅入口：[机器验收凭据](evidence/p0_p2_acceptance_20261014.json)、[统一草案配置](../configs/momentum_pullback/research_contract_v0_2.yaml)、[操作口径 r2](engineering_contract_v0_2_r2.md)、[70 项测试](../tests/momentum_pullback)。凭据绑定代码、合同、测试源码和实际结果文件内容，记录未实现及未验收的后续范围。

## 已交付的实现

- `contracts.py`：草案解释、重复配置键和文档绑定校验；收益入口关闭。检查点 v2 校验合同、代码、历史行情及交易日历前缀、处理截止点、预热起点和状态内容；改变输入或参数需新建草案运行。
- `runtime.py`：运行清单、合同快照、解释器/依赖/安装来源及实际 Parquet 往返；运行前记录输入哈希，完成后复核输入与实现未变。
- `data_adapter.py`：明确选定分区，禁止重复/冲突键、非法价格、OHLC 异常、非正/非有限因子、错位键集和非一对一连接；公共缓存没有被修补。
- `features.py`：价格观测窗口与市场日 ADV20 分开，只有已验证全天停牌派生零额；完整排名分母、公告可用时间及生效日期分别处理。输入为声明完整的市场日网格，金额/流通市值字段要求明确以 CNY 表示；尚未认证公共缓存的真实 PIT 快照接入。
- `event_engine.py`：趋势根、突破、触碰段和候选分开记录；未知根资格跨日传播，已知根的触碰编号不随排名恢复、再突破或超时清空。窗口外根保留，事件按触碰日期输出。
- `matching.py`：同日同业、三只不同对照、固定卡尺及距离/代码排序；输出失败原因、复用和协变量平衡，不读取未来收益或成交字段。
- `scripts/run_momentum_pullback.py`：合同检查、环境探测、离线审查、受数据门约束的真实事件入口及手工工程验收。研究收益、政策和共享账户命令返回阻断状态。

## 实际验收证据

隔离解释器为 `C:\Users\cfz\Workspace\ProjectQ\code_v4\.venv-pullback\Scripts\python.exe`，Python **3.11.9**；核心依赖为 numpy **1.26.4**、pandas **2.2.3**、pyarrow **18.1.0**。全部直接及间接依赖固定在 [requirements-p0.txt](requirements-p0.txt)。实际模块导入、带 UTC 时间及固定数据类型的 Parquet 写入/读回通过，wheel URL 与下载哈希保存在安装报告及环境凭据。未升级全局环境；不代表其他项目模块已在该环境验收。

首批测试 **70 passed，0 failed，0 errors，0 skipped**。覆盖重复/冲突及多对多防护、复权尺度、发布时间和生效时间、市场日 ADV20、排名分母缺失、未知身份传播、首次失败消耗编号、连续触碰、20/21 日边界、卡尺/距离同分、未来数据不能改配对、检查点不兼容/损坏和失败入口不输出真实事件。

独立手工输入与预期见 [casebook.py](casebook.py) 和 [hand_expected.json](fixtures/hand_expected.json)：150 个平价观测后，A/B/C/D 于 2017-12-29 建根；A 在 2018-01-02 为首次成功首触，1 月 3 日连续触碰不重复计数，1 月 4 日离开支撑，1 月 5 日为第二次。两事件各固定匹配 B/C/D，距离为零。输出 **4 个根、1 个首次候选、1 个后续候选、6 条配对**。这里的日期网格是声明的合成时钟，不能作为真实市场日历证据。

跨季度续跑保存 EMA、有效观测数、价格/波动窗口、ADV20 市场日窗口、趋势根、触碰次数及等待状态；先校验已消费历史和日历，再恢复。续跑与完整回放一致，并分别符合手工预期。两次独立运行的 **12 个计算成果文件 SHA-256 完全相同**；运行 ID 不同，内容身份相同。完整证据在：

- [首个手工运行](../data/research/momentum_pullback/hand_acceptance-e84f4c9c882a-36b069722a/acceptance_summary.json)
- [重复运行](../data/research/momentum_pullback/hand_acceptance-e84f4c9c882a-0bdca725a1/acceptance_summary.json)
- [测试 XML](../data/research/momentum_pullback/p0_env/pytest_acceptance.xml)

正常零事件、输出覆盖不足、身份未知、候选资格未知、匹配不可评估和真实数据阻断有不同状态。手工正例及预期避免“两个同样错误的实现互相证明”；仅有文件或仅有零事件不会获得成功结论。

## 2018Q1 真实数据阻断

固定输出区间为 2018-01-01 至 2018-03-30。读取原始价和复权价各 **137,594 行**，业务键唯一性及 OHLC 检查通过；这是缓存范围，尚不是已认证的沪深 300 样本。随后真实门失败：

- **2,477 行复权因子无效**，不通过价格比推导补齐。
- 成分数据缺 `announced_at / effective_from / effective_to`。
- 行业与市值数据缺所需 `available_at`。
- 完整市场日历、历史成分/ST/停牌资格和统一预热起点覆盖仍未认证；本轮没有完成全段预热质量审查。

[真实数据报告](../data/research/momentum_pullback/build_events-03282d1c621f-0871e2f3a3/data_gate_report.json)含逐文件行数、失败字段和无效因子样例；[入口阻断记录](../data/research/momentum_pullback/build_events-03282d1c621f-0871e2f3a3/blocked.json)对应退出码 **2**。本批次没有事件/匹配 Parquet，输入文件哈希保持不变。这是 **DATA_BLOCKED**，不是“没有信号”或“策略无效”。来源即使补齐字段，也需审查内容、时点与覆盖，不能只把配置改为允许运行。

## 复跑与下一步

在项目根目录执行：

```powershell
$pullbackPython = (Resolve-Path .\.venv-pullback\Scripts\python.exe).Path
& $pullbackPython scripts/run_momentum_pullback.py contract-check
& $pullbackPython scripts/run_momentum_pullback.py env-probe
& $pullbackPython scripts/run_momentum_pullback.py engineering-smoke
& $pullbackPython scripts/run_momentum_pullback.py build-events --offline --outcomes-disabled
# 当前真实数据命令返回 2，详情写入独立运行目录。

$pullbackTestTemp = Join-Path $PWD ('data/research/momentum_pullback/test_tmp_' + [guid]::NewGuid().ToString('N'))
if (Test-Path -LiteralPath $pullbackTestTemp) { throw 'Fresh test directory required' }
& $pullbackPython -m pytest tests/momentum_pullback -q -p no:cacheprovider --basetemp $pullbackTestTemp
```

默认系统临时目录及旧 pytest 缓存存在访问限制，测试使用独立新目录并关闭旧缓存；首次失败记录保留，没有修改全局权限。每次运行新建目录，旧草案结果不覆盖或升级。

下一步仅补齐原研究范围的因子与 PIT 来源证据、单位、日历及历史覆盖，并接入经审查的完整归一化快照，重新通过真实 P1 门后才生成真实 P2 事件/固定名单。公司行动时间字段已预留，具体应用顺序、竞价前订单校验、持仓及现金属于 P4 前验收；P3 还需冻结研究合同、研究区间、覆盖/功效门槛。合成通过不替代这些验收。

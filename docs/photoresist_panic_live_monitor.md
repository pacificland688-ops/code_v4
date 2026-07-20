# 光刻胶恐慌实盘提示工具

## 定位

该工具每天收盘后回答三个问题：

```text
1. 光刻胶核心篮子是否触发冻结的 primary_5d 恐慌条件？
2. 恐慌属于小幅但历史异常，还是绝对跌幅较大的踩踏？
3. 当前市场状态允许观察反转，还是只能提示继续下跌风险？
```

工具状态为 `RESEARCH_ONLY`，只生成提示，不生成自动买入订单。

## 严格运行

```powershell
python scripts\monitor_photoresist_panic.py --as-of 20260715
```

若本地行情过期或股票池有效期不足，会返回：

```text
BLOCKED
DATA_STALE
UNIVERSE_REVIEW_REQUIRED
```

严格模式不会静默使用陈旧数据或过期股票池。

## Tushare 临时补数

```powershell
python scripts\monitor_photoresist_panic.py `
  --as-of 20260715 `
  --refresh-tushare `
  --allow-universe-carry-forward
```

说明：

```text
--refresh-tushare:
  从Tushare在内存中补齐核心股票和指数行情，不改写冻结研究输出。

--allow-universe-carry-forward:
  临时沿用截止2025-12-31的核心池，只用于研究提示。
  输出始终保留“成员资格待人工复核”警告。
```

正式部署前应通过新年报或公告完成2026年成员资格复核，而不是长期依赖 carry-forward。

## 提示状态

```text
NORMAL:
  未出现异常下跌。

WEAKNESS_WATCH:
  处于历史较差区域，但未触发 primary_5d。

REVERSAL_WATCH:
  已触发恐慌，且市场为 bull/neutral，可观察反转。

PANIC_RISK_ONLY:
  已触发恐慌，但市场为 bear/unknown，不启用反转观察。

BLOCKED:
  数据或股票池审计不通过，禁止解释信号。
```

## 恐慌等级

```text
PANIC_L1:
  绝对跌幅小于5%，但进入过去250日极端分位。

PANIC_L2:
  5日跌幅达到5%。

PANIC_L3:
  5日跌幅达到8%，或进入历史最差5%。

PANIC_L4:
  5日跌幅达到10%，或同时满足最差1%分位和高下跌广度。
```

等级只描述恐慌强度，不代表等级越高越应该买入。

## 输出

```text
outputs/live/photoresist_panic/photoresist_panic_alert_latest.json
outputs/live/photoresist_panic/photoresist_panic_alert_latest.md
outputs/live/photoresist_panic/photoresist_panic_alert_YYYYMMDD.json
outputs/live/photoresist_panic/photoresist_panic_alert_YYYYMMDD.md
```

JSON适合后续接入企业微信、邮件或桌面通知；Markdown适合人工查看。

## 历史参考边界

当前历史参考是：

```text
在线首次触发
bull/neutral
t+1收盘入场
20日内收盘达到净收益5%
历史命中率约66.7%-76.2%
每条规则仅21笔
```

该数字不是下一次交易的确定概率。未命中交易历史上存在约13%-19%的最差亏损，且当前Top1和止损规则尚未通过正式验收。

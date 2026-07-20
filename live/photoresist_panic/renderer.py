"""Alert rendering: Markdown daily report + JSON payload assembly."""
from __future__ import annotations

import pandas as pd


def _fmt(value, spec: str = ".2%", default: str = "N/A") -> str:
    if value is None:
        return default
    try:
        return format(float(value), spec)
    except (TypeError, ValueError):
        return default


def _commonality_block(title: str, block: dict) -> list[str]:
    lines = [
        f"### {title}（{block.get('scope')}）",
        "",
        f"- 分类：**{block.get('classification')}**",
        f"- 篮子5日收益：{_fmt(block.get('basket_ret_5d'))}",
        f"- 下跌成分：{block.get('down_count')}/{block.get('n_valid_components')}",
        f"- 个股5日收益中位数：{_fmt(block.get('median_ret_5d'))}",
        f"- 最大贡献占比：{_fmt(block.get('max_contribution_share'), '.0%')}"
        f"（{block.get('max_contributor') or '—'}）",
    ]
    for note in block.get("notes", []):
        lines.append(f"- {note}")
    lines.append("")
    return lines


def render_markdown(alert: dict) -> str:
    """Human-readable close-of-day report."""
    metrics = alert.get("metrics", {})
    severity = alert.get("severity", {})
    reversal = alert.get("reversal", {})
    commonality = alert.get("commonality", {})
    theme = commonality.get("theme_commonality", {})
    signal = commonality.get("signal_commonality", {})
    membership = alert.get("membership", {})
    quality = alert.get("data_quality", {})
    state = alert.get("state", {})
    evidence = reversal.get("historical_evidence", {})

    level = severity.get("level", "P0")
    title_map = {
        "P0": "光刻胶恐慌监控 — 正常",
        "P1": "光刻胶弱恐慌观察 P1",
        "P2": "【光刻胶恐慌确认 P2】",
        "P3": "【光刻胶强恐慌 P3】",
        "P4": "【光刻胶极端流动性冲击 P4】",
    }
    excluded = membership.get("excluded_components", [])
    excluded_str = (
        "、".join(f"{e['ts_code']}({e['reason']})" for e in excluded)
        if excluded else "无"
    )
    lines = [
        f"# {title_map.get(level, '光刻胶恐慌监控')}",
        "",
        f"日期：{alert.get('event_date')}",
        f"生成时间：{alert.get('generated_at')}",
        f"数据状态：{quality.get('status')}，"
        f"{quality.get('components_present')}/{quality.get('components_expected')}成分有行情",
        f"信号状态：{alert.get('signal_phase')}（{state.get('state_before')} → "
        f"{state.get('state_after')}）",
        f"市场环境：{reversal.get('market_regime')}",
        f"反转状态：{reversal.get('reversal_status')}",
        "",
        "## 成员口径",
        "",
        f"- 全部有效核心成员 active_components：{membership.get('active_components')}",
        f"- 参与primary_5d信号成员 signal_components：{membership.get('signal_components')}",
        f"- 被资格过滤排除 excluded_components：{excluded_str}",
        "",
        "## 恐慌指标（冻结eligible basket口径）",
        "",
        f"- 篮子5日收益：{_fmt(metrics.get('basket_ret_5d'))}",
        f"- 历史10%分位阈值：{_fmt(metrics.get('rolling_quantile_10pct'))}",
        f"- 距10%分位距离：{_fmt(metrics.get('distance_to_quantile'))}",
        f"- 当前历史百分位：{_fmt(metrics.get('historical_percentile'), '.1%')}",
        f"- 下跌广度(5日, eligible)：{_fmt(metrics.get('down_breadth_5d'), '.0%')}",
        f"- 成交额放大倍数(eligible)：{_fmt(metrics.get('amount_ratio_20d'), '.2f')}",
        f"- 相对半导体5日超额：{_fmt(metrics.get('relative_vs_semiconductor_5d'))}",
        "",
        "## 流动性压力（全部active核心成员口径, P4依据）",
        "",
        f"- 跌停成分数量：{metrics.get('active_limit_down_count', 'N/A')}"
        f"（{ '、'.join(metrics.get('active_limit_down_codes') or []) or '—'}）",
        f"- 下跌广度(5日, active)：{_fmt(metrics.get('active_down_breadth_5d'), '.0%')}",
        f"- 广度成员覆盖率：{_fmt(metrics.get('active_breadth_member_coverage'), '.0%')}",
        f"- 成交额放大(active中位)：{_fmt(metrics.get('active_amount_ratio_20d'), '.2f')}",
        f"- 成交额成员覆盖率：{_fmt(metrics.get('active_amount_member_coverage'), '.0%')}",
        "",
        f"**恐慌等级 {level}**：{'；'.join(severity.get('reasons', []))}",
        "",
        "## 成分明细",
        "",
    ]
    components = pd.DataFrame(alert.get("components", []))
    if not components.empty:
        show = components[[
            c for c in ("ts_code", "name", "ret_5d", "pct_chg_1d",
                        "rel_vs_semi_5d", "amount_ratio_20d", "limit_down_today")
            if c in components.columns
        ]]
        lines.append(show.to_markdown(index=False, floatfmt=".4f"))
    else:
        lines.append("_无成分数据_")
    lines.extend(["", "## 成分共同性（两套口径）", ""])
    lines.extend(_commonality_block("主题共同性 theme_commonality", theme))
    lines.extend(_commonality_block("信号共同性 signal_commonality", signal))

    lines.extend(["## 反转环境", "", f"{reversal.get('explanation', '')}", ""])
    if evidence.get("sample_size"):
        hit_range = evidence.get("hits_range", ["?", "?"])
        ci = evidence.get("wilson_ci_95")
        lines.extend([
            f"- 历史相似样本：{evidence.get('label')}",
            f"- 样本数：{evidence.get('sample_size')}，"
            f"历史命中：{hit_range[0]}/{evidence.get('sample_size')}"
            f"至{hit_range[1]}/{evidence.get('sample_size')}",
            f"- Wilson 95%区间：约{_fmt(ci[0], '.0%')}-{_fmt(ci[1], '.0%')}"
            if ci else "- Wilson 95%区间：N/A",
            f"- 证据等级：{evidence.get('evidence_grade')}",
            f"- {evidence.get('note')}",
        ])
    if reversal.get("market_regime") == "bear":
        lines.extend([
            "",
            "> **Bear状态警示**：历史熊市修复优势未成立，禁止仅依据恐慌信号抄底。",
        ])

    lines.extend(["", "## 数据质量", ""])
    for warning in quality.get("warnings", []):
        lines.append(f"- 警告：{warning}")
    for blocker in quality.get("blockers", []):
        lines.append(f"- 阻断：{blocker}")
    if not quality.get("warnings") and not quality.get("blockers"):
        lines.append("- 全部检查通过")
    if alert.get("universe_review_note"):
        lines.append(f"- 审核提示：{alert['universe_review_note']}")

    lines.extend([
        "",
        "---",
        "",
        f"结论：{alert.get('conclusion', '')}",
        "",
        "状态输出：",
        f"- PANIC_ALERT：{alert.get('panic_alert')}",
        f"- REVERSAL_CANDIDATE：{alert.get('reversal_candidate')}",
        f"- TRADE_READY：{alert.get('trade_ready')}（恒为False，不构成自动买入指令）",
        "",
        f"signal_id：{alert.get('signal_id') or '—'}  |  run_id：{alert.get('run_id')}"
        f"  |  universe：{alert.get('universe_version')}"
        f"  |  config：{alert.get('config_hash')}",
    ])
    return "\n".join(lines)


def build_conclusion(alert: dict) -> str:
    quality_status = alert.get("data_quality", {}).get("status")
    if quality_status == "BLOCKED":
        return "数据质量未通过，今日不生成正式信号。"
    level = alert.get("severity", {}).get("level", "P0")
    reversal_status = alert.get("reversal", {}).get("reversal_status", "")
    if not alert.get("panic_alert"):
        return ("弱势观察中，未触发恐慌条件。" if level == "P1"
                else "未发生光刻胶恐慌性下跌。")
    if reversal_status.startswith("REVERSAL_CANDIDATE"):
        return "进入反转观察，不构成自动买入指令。"
    return "已确认恐慌，但当前环境不支持反转观察，仅提示下跌风险。"

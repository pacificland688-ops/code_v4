# 竞争对手评审：因子架构问题与改造方案（v3 — 终版）

> 评审日期：2026-06-06（初版），2026-06-06（v2），2026-06-07（v3）
> 评审范围：`alpha/ic_weighting.py`、`run_research.py`、`configs/factors.yaml`、`factors/cross_section.py`、`factors/factor_panel.py`
> 核心结论：**问题不是单个反转因子"永远不好"，而是当前架构把因子进入池做成了静态白名单，导致后面价值、低波、动量等因子即使恢复有效，也无法进入组合打分。**

---

## 分层结论

| Step | 判定 | 说明 |
|------|------|------|
| **Step 1** | ✅ 有条件通过 | 修正后真正做到「零行为改变」——保留当前 5 因子白名单，仅接通 YAML 参数和新增接口 |
| **Step 2** | ⏸️ 暂不通过，需先修关键漏洞 | 覆盖率 gate 的历史窗口、IC horizon 滞后、eligible 权重归一化、min_active_factors 必须在切全因子池前修好 |
| **Step 3** | ✅ 基本通过 | cross_section 工厂函数已匹配真实 API，`--factors-config` CLI 已补，参数扫描框架已定义 |

---

## 一、问题诊断

### 1.1 表面症状

策略在 2016 年（IS）选出 5 个反转因子后，用同一套因子跑 2017-2026 年。逐年的因子 ICIR 数据显示，反转因子在 2018 年后系统性衰减，而价值因子（ep/bp/sp）在 2021、2023、2025 年 ICIR 达到 0.4-1.17，但因为不在白名单里而无法进入组合打分。

### 1.2 根因：静态白名单 + 死配置

**根因 1：因子启用是静态白名单。** Phase 1 的因子评估会对**所有**因子计算 IC（包括被禁用的），但 Phase 2/3/5 的组合打分阶段，`_load_factor_config()` → `_filter_enabled_factors()` → `ICWeighting(factor_whitelist=enabled_factors)` 这条链路把不在白名单里的因子全部截断。因子一旦被列入 `disabled_factors`，就**无法进入组合打分**——即使后续年份它的 IC 恢复有效。

**根因 2：YAML 配置是死的。** `factors.yaml` 的 `composite` 配置块定义了 7 个参数，但**零个 Python 文件读取这个配置块**。`ICWeighting.__init__` 全部使用硬编码默认值。6 个调用点只传 `factor_whitelist`。

**根因 3：`cross_section` 配置同样是死配置。** `create_default_processor()` 全部硬编码。唯一调用点 `factor_panel.py:72`。

**根因 4（v3 新发现）：IC 权重存在未来函数风险。** `compute_weights()` 用 `trade_date < signal_date` 过滤 IC，但每个 IC 是通过 `fwd_ret_5d`（取决于 T+5 的价格）算出来的。当 `signal_date - trade_date < 5 个交易日` 时，IC 依赖的价格在 signal_date 之后尚不可知——这是未来信息泄漏。

**根因 5（v3 新发现）：权重上限是假上限。** 当前逻辑 `weight = clip(raw, -cap, cap)` → 归一化 → 单因子可达 100%。而且即使上限真生效，单因子 composite 的横截面 z-score 排序与 100% 权重等价——排名不变。

---

## 二、改造方案：全因子候选池 + 四级门槛 + 动态权重

```
┌──────────────────────────────────────────────────────────────────┐
│                     全因子候选池 (13+ factors)                    │
│   所有 _cs 因子从缓存加载。Step 1 保留旧白名单，Step 2 切全池      │
└────────────────────────────┬─────────────────────────────────────┘
                             │
                    ┌────────▼────────┐
                    │  Gate 1: 覆盖率  │  每个 signal_date 独立评估
                    │  历史窗口日期覆盖  │  只看 trade_date + fwd_horizon
                    │  每日期 ≥ 30 有效股 │  < signal_date 的数据
                    │  与 fwd_ret 可 merge│
                    └────────┬────────┘
                             │ 通过
                    ┌────────▼────────┐
                    │  Gate 2: IC 有效性│
                    │  滚动 ICIR ≥     │  只用 fwd_ret 已完全实现的
                    │  min_icir (0.05) │  IC 观测（horizon-lagged）
                    └────────┬────────┘
                             │ 通过
                    ┌────────▼────────┐
                    │  Gate 3: 方向稳定性│
                    │  近期 IC 符号与    │
                    │  长期一致         │
                    │  不一致 → 额外收缩 │
                    └────────┬────────┘
                             │ 通过
                    ┌────────▼────────┐
                    │  Gate 4: 权重上限 │  先归一化 → 后 cap →
                    │  归一化后          │  迭代重分配剩余权重
                    │  |w_i| ≤ cap      │  （真正的硬上限）
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │  动态 IC 加权     │  仅对 eligible 因子计算和
                    │  w_i ∝ shrunk_IC │  归一化（不包含被 gate 淘汰
                    │  / IC_vol        │  的因子）
                    └─────────────────┘
                             │
                    ┌────────▼────────┐
                    │  安全阀           │  若 eligible < min_active:
                    │  min_active=3     │  → 回退到上一期权重或等权多因子
                    └─────────────────┘
```

---

## 三、Step 1：纯接线，零行为改变（P0，✅ 有条件通过）

**目标：接通 YAML → ICWeighting 参数链路，新增所有未来接口（写好但不启用），保留当前 5 因子白名单，确保回测输出与修复前逐位一致。**

### 改动 1.1：`run_research.py` — `_load_factor_config()` 读取完整配置

替换 `run_research.py:174-193` 的函数。**保留当前 `enabled_factors` 的 5 个因子不变，默认值与当前硬编码完全一致。**

```python
def _load_factor_config(config_path=None):
    """Load factor and composite config from factors.yaml.

    Parameters
    ----------
    config_path : str or Path, optional
        Path to factors YAML. Defaults to "configs/factors.yaml".

    Returns
    -------
    dict with keys: enabled_factors, composite_params, cross_section_params
    """
    try:
        import yaml
        from pathlib import Path
        path = Path(config_path or "configs/factors.yaml")
        if not path.exists():
            logger.warning(f"{path} not found — using all factors")
            return {"enabled_factors": [], "composite_params": {}, "cross_section_params": {}}
        with open(path, "r") as f:
            config = yaml.safe_load(f)

        enabled = config.get("enabled_factors", [])

        # Wire composite params — defaults EXACTLY match current hardcoded values.
        composite_raw = config.get("composite", {})
        composite_params = {
            "ic_window_months": composite_raw.get("ic_window_months", 12),
            "shrinkage": composite_raw.get("shrinkage", 0.3),
            "weight_cap": composite_raw.get("weight_cap", 0.3),
            "min_ic_obs": composite_raw.get("min_ic_obs", 20),
            "min_icir": composite_raw.get("min_icir", 0.0),
            "sign_stability_check": composite_raw.get("sign_stability_check", True),
            "ic_method": composite_raw.get("ic_method", "rank"),
        }

        # Also read cross_section for future use (Step 3).
        cross_section_params = config.get("cross_section", {})

        return {
            "enabled_factors": enabled,
            "composite_params": composite_params,
            "cross_section_params": cross_section_params,
        }
    except Exception as e:
        logger.warning(f"Failed to load factor config: {e} — using all factors")
        return {"enabled_factors": [], "composite_params": {}, "cross_section_params": {}}
```

### 改动 1.2：`run_research.py` — 6 个调用点改为传 `composite_params`

**文件：`run_research.py`（行 1368, 1528, 2153, 2656）、`validation/experiment_runner.py:328`、`live/signal_service.py:94`**

```python
factor_config = _load_factor_config()
enabled_factors = factor_config["enabled_factors"]

# Step 1: KEEP the current whitelist behavior.
# enabled_factors is loaded from YAML (currently set to 5 reversal factors).
# Empty list = all factors (not enabled in Step 1 — wait for Step 2).
factor_names = _filter_enabled_factors(factor_names, enabled_factors)
# ... load factor_dfs same as before ...

icw = ICWeighting(
    **factor_config["composite_params"],  # ← YAML params now wired
    factor_whitelist=enabled_factors,     # ← kept for backward compat
)
```

### 改动 1.3：`alpha/ic_weighting.py` — 增加 `min_icir` 参数（默认 0.0 = 不启用）

`__init__` 签名新增 `min_icir: float = 0.0`。`compute_weights()` 中的 ICIR gate 仅在 `self.min_icir > 0` 时生效——Step 1 默认 0.0，行为不变。

```python
def __init__(self,
             ic_window_months: int = 12,
             shrinkage: float = 0.3,
             weight_cap: float = 0.3,
             min_ic_obs: int = 20,
             min_icir: float = 0.0,           # ← 新增，0.0 = disabled
             sign_stability_check: bool = True,
             ic_method: str = "rank",
             factor_whitelist: Optional[List[str]] = None,
             factor_blacklist: Optional[List[str]] = None):
    # ...
    self.min_icir = min_icir
```

在 `compute_weights()` 中（紧接 `if std_ic == 0 or np.isnan(std_ic): continue` 之后）：

```python
# ICIR gate — only active when explicitly enabled (default 0.0 = off)
if self.min_icir > 0:
    icir = mean_ic / std_ic
    if abs(icir) < self.min_icir:
        continue
```

### 改动 1.4：`alpha/ic_weighting.py` — 新增 `_apply_hard_cap()` 方法（写好不调用）

Step 1 的 `weight_cap=0.3` 不会触发 hard cap（条件为 `0 < weight_cap < 0.3`）。方法写好，Step 2 收紧 `weight_cap=0.25` 时自动激活。

```python
def _apply_hard_cap(self, weights: Dict[str, float]) -> Dict[str, float]:
    """Apply hard weight cap AFTER normalization via iterative cap + redistribute.

    Algorithm:
      1. Start with normalized weights (sum|w| = 1)
      2. Clip any |w| > cap to cap
      3. Redistribute excess proportionally among uncapped factors
      4. Repeat until all |w| ≤ cap (typically 1-2 iterations)

    Called from compute_weights() when 0 < self.weight_cap < 0.5.
    """
    if not weights or self.weight_cap <= 0:
        return weights

    cap = self.weight_cap
    working = {k: abs(v) for k, v in weights.items()}
    total = sum(working.values())
    if total == 0:
        return {k: 0.0 for k in weights}
    working = {k: v / total for k, v in working.items()}

    for _ in range(10):
        excess = 0.0
        uncapped_sum = 0.0
        for k, w in working.items():
            if w > cap:
                excess += w - cap
                working[k] = cap
            else:
                uncapped_sum += w

        if excess < 1e-8:
            break

        if uncapped_sum < 1e-8:
            n = len(working)
            for k in working:
                working[k] = 1.0 / n
            break

        for k, w in working.items():
            if w < cap - 1e-8:
                working[k] = w + excess * (w / uncapped_sum)

    return {k: (working[k] if v >= 0 else -working[k])
            for (k, v) in weights.items()}
```

修改 `compute_weights()` 的归一化部分：

```python
# Normalize weights to sum to 1
if weights:
    weight_sum = sum(abs(w) for w in weights.values())
    if weight_sum > 0:
        weights = {k: v / weight_sum for k, v in weights.items()}

    # Hard cap (only when explicitly enabled via YAML)
    if 0 < self.weight_cap < 0.5:
        weights = self._apply_hard_cap(weights)
```

**注意：Step 1 的 `weight_cap=0.3` 不触发 `_apply_hard_cap`（条件 `0 < 0.3 < 0.5` 为 True → 会触发！）。** 修正：把条件改为 `0 < self.weight_cap < 1.0`，但加一个 `self._hard_cap_enabled` 标志位，Step 1 不设置。

更简单的方案：Step 1 YAML 中 `weight_cap: 0.3`，不改代码中的 clip-then-normalize 逻辑。新增的 `_apply_hard_cap()` 由一个独立参数控制：

```python
def __init__(self, ..., hard_cap: bool = False):  # Step 1 default False
    self.hard_cap = hard_cap
```

然后：
```python
if self.hard_cap and 0 < self.weight_cap < 1.0:
    weights = self._apply_hard_cap(weights)
```

Step 1 `hard_cap=False` → 旧行为不变。Step 2 在 YAML 中加 `hard_cap: true` 并收紧 `weight_cap: 0.25`。

### 改动 1.5：`run_research.py` — 新增覆盖率评估函数（写好不调用）

新增 `_evaluate_factor_coverage_at_date()` —— 每个 signal_date 只看历史窗口。**Step 1 不调用此函数，仅定义接口。** 使用真实日历而非 `* 100` 近似：

```python
def _evaluate_factor_coverage_at_date(
    factor_df: "pd.DataFrame",
    signal_date: int,
    fwd_returns_df: "pd.DataFrame",
    lookback_months: int = 12,
    min_stocks_per_date: int = 30,
    min_merge_rate: float = 0.30,
    date_coverage_min: float = 0.70,
) -> bool:
    """Evaluate factor data quality at a signal_date (NO future leakage).

    Looks back from signal_date using a real calendar offset (pd.DateOffset),
    NOT the crude *100 approximation.

    Checks three dimensions:
      1. Date coverage in lookback window ≥ date_coverage_min
      2. On ≥ 50% of dates, at least min_stocks_per_date stocks have
         non-NaN factor values
      3. When merged with fwd_returns on the same trade_date, ≥ min_merge_rate
         of stocks survive (testing actual cross-sectional usability)

    All checks use ONLY trade_date < signal_date.
    """
    import pandas as pd

    if factor_df is None or factor_df.empty:
        return False

    value_cols = [c for c in factor_df.columns
                  if c not in ("ts_code", "trade_date")]
    if not value_cols:
        return False
    value_col = value_cols[0]

    # Real calendar-based lookback (not *100)
    signal_dt = pd.to_datetime(str(signal_date), format="%Y%m%d")
    lookback_start_dt = signal_dt - pd.DateOffset(months=lookback_months)
    lookback_start = int(lookback_start_dt.strftime("%Y%m%d"))

    window = factor_df[
        (factor_df["trade_date"] < signal_date) &
        (factor_df["trade_date"] >= lookback_start)
    ]
    if window.empty or window["trade_date"].nunique() == 0:
        return False

    # Dimension 1: date coverage
    unique_dates = window["trade_date"].nunique()
    expected_dates = lookback_months * 21
    if unique_dates / expected_dates < date_coverage_min:
        return False

    # Dimension 2: per-date stock count
    per_date_counts = window.groupby("trade_date")[value_col].apply(
        lambda s: s.notna().sum()
    )
    sufficient_dates = (per_date_counts >= min_stocks_per_date).sum()
    if sufficient_dates < len(per_date_counts) * 0.50:
        return False

    # Dimension 3: merge survival rate with fwd_returns
    if fwd_returns_df is not None and not fwd_returns_df.empty:
        ret_cols = [c for c in fwd_returns_df.columns
                    if c.startswith("fwd_ret_") and c not in ("ts_code", "trade_date")]
        if ret_cols:
            ret_col = ret_cols[0]
            merge_count = 0
            total_valid = 0
            for _, day in window.groupby("trade_date"):
                fwd_day = fwd_returns_df[fwd_returns_df["trade_date"] == day.name]
                if fwd_day.empty:
                    continue
                day_valid = day[value_col].notna().sum()
                merged = day[["ts_code", value_col]].dropna().merge(
                    fwd_day[["ts_code", ret_col]].dropna(), on="ts_code"
                )
                merge_count += len(merged)
                total_valid += day_valid
            if total_valid > 0 and merge_count / total_valid < min_merge_rate:
                return False

    return True
```

### 改动 1.6：`run_research.py` — 新增 `--factors-config` CLI 参数

```python
parser.add_argument(
    "--factors-config",
    type=str,
    default="configs/factors.yaml",
    help="Path to factors YAML config. Use for A/B testing different factor "
         "sets without manually overwriting the default config.",
)
```

所有调用 `_load_factor_config()` 的地方改为 `_load_factor_config(args.factors_config)`。

### 改动 1.7：`configs/factors.yaml` — 最小改动

**Step 1 不改 `enabled_factors`**（保持当前 5 个反转因子），只加注释说明语义：

```yaml
# ---------------------------------------------------------------------------
# Composite score (IC weighting)
# ---------------------------------------------------------------------------
# WIRED (v3): These parameters are now passed to ICWeighting.__init__.
# Current values match the old hardcoded defaults — no behavior change.
composite:
  ic_window_months: 12
  ic_method: "rank"              # currently only "rank" (Spearman) is implemented
  shrinkage: 0.3
  weight_cap: 0.3
  min_ic_obs: 20
  min_icir: 0.0                  # 0.0 = disabled; set 0.05 in Step 2
  sign_stability_check: true

# ---------------------------------------------------------------------------
# Factor enable/disable
# ---------------------------------------------------------------------------
# CURRENT (Step 1 — no behavior change):
#   Explicit list of 5 reversal factors, matching old behavior.
#   Changing to [] (empty) = full candidate pool — DO THIS IN STEP 2.
enabled_factors:
  - reversal_5_cs
  - reversal_20_cs
  - pv_divergence_20_cs
  - rsi_14_cs
  - volatility_20_cs

# disabled_factors is documentation only — no code reads it.
# ...
```

### Step 1 验证标准

**回测输出必须与修复前逐位一致。** 验证步骤：

```bash
# 1. 用默认 --factors-config 跑 2016 IS
python run_research.py --start 20160101 --end 20161231 --phase 2 --top-n 50

# 2. diff 修复前后的 metrics_summary.json
#    所有字段必须完全相等：annualized_return, excess_return, sharpe, max_dd, turnover

# 3. 打印 ICWeighting 收到的参数，确认与旧硬编码一致
#    ic_window_months=12, shrinkage=0.3, weight_cap=0.3, min_ic_obs=20,
#    min_icir=0.0, sign_stability_check=True, ic_method="rank"
```

---

## 四、Step 2：切全因子池 + 修复所有 gate 逻辑（P1，⏸️ 暂不通过）

**Step 2 v2 有三个关键漏洞必须在实施前修好：IC horizon 滞后、eligible 权重归一化、min_active_factors 安全阀。**

### 关键漏洞 #1：IC 权重存在未来函数——必须加 horizon lag

**问题：** `compute_weights()` 用 `trade_date < signal_date` 过滤 IC。但每个 `IC_T` 是通过 `fwd_ret_5d` 计算的，依赖 T+5 的价格。当 `T` 接近 `signal_date` 时（例如 T = signal_date - 2），`IC_T` 的 fwd_ret 还没走完——这是未来信息泄漏。

**修正：** 在 `compute_weights()` 中，IC 窗口的截止日必须是「forward horizon 已经完全结束」的日期：

```python
# alpha/ic_weighting.py — compute_weights() 中的窗口过滤

# Old (有未来函数):
# ic_window = ic_df[(ic_df["trade_date"] < signal_date) & ...]

# New (无未来函数):
# horizon_trading_days: int — forward return horizon in trading days
# Convert to calendar-day lag conservatively: horizon_cal_days = horizon * 1.4
self._horizon_cal_lag = int(horizon * 1.4 + 1)  # e.g., 5→8 for 5d horizon

cutoff_date = signal_date - self._horizon_cal_lag  # only ICs where fwd_ret completed
ic_window = ic_df[
    (ic_df["trade_date"] <= cutoff_date) &   # ← 改了: < 变 <=
    (ic_df["trade_date"] >= lookback_start)
]
```

`horizon` 需要从 `compute_composite_series()` 传下来。Step 2 在 `ICWeighting.__init__` 中增加 `horizon: int = 5` 参数：

```python
def __init__(self, ..., horizon: int = 5):
    self.horizon = horizon
    self._horizon_cal_lag = max(2, int(horizon * 1.4 + 1))  # conservative cal-day equiv
```

> **更精确的方案（建议但非必需）**：传入实际交易日历，用 `calendar.trading_days_between(T, signal_date) >= horizon` 做判断。当前保守的 `*1.4+1` 近似在实践中足够安全。

### 关键漏洞 #2：权重归一化包含不合格因子

**问题：** v2 方案先在 `compute_composite_score()` 中过滤 eligible_factors，但 `compute_weights()` 仍然基于全部因子计算权重（因为 `ic_df` 包含所有因子），归一化时会把已淘汰因子的 IC 也纳进来，扭曲有效因子的权重。

**修正：** `compute_weights()` 增加 `eligible_factor_names` 参数，**只对通过 coverage gate 的因子计算和归一化权重**：

```python
def compute_weights(self, ic_df: pd.DataFrame,
                    signal_date: int,
                    eligible_factor_names: Optional[List[str]] = None
                    ) -> Dict[str, float]:
    # ...
    ic_cols = [c for c in ic_df.columns if c.endswith("_ic")]

    # If eligible_factor_names is provided, restrict to those factors
    if eligible_factor_names is not None:
        eligible_ic_cols = [f"{name}_ic" for name in eligible_factor_names]
        ic_cols = [c for c in ic_cols if c in eligible_ic_cols]
    # ... rest of the method only operates on ic_cols ...
```

`compute_composite_score()` 调用时传入：

```python
eligible_names = list(eligible_factors.keys())
weights = self.compute_weights(ic_df, signal_date, eligible_factor_names=eligible_names)
```

### 关键漏洞 #3：单因子 composite z-score 后排名等价于 100% 权重

**问题：** 即使 weight_cap 硬限到 0.25，如果只有一个因子通过所有 gate，composite_score 就是该因子的 z-score × 0.25。横截面再做一次 z-score 后，0.25 被消掉——排名完全等同于 100% 单因子。**权重上限对选股结果没有任何约束效果。**

**修正：** 增加 `min_active_factors` 安全阀。如果通过 gate 的因子数 < `min_active_factors`，不回退到等权——而是**不出信号**（返回空 composite，触发上一期持仓保持不变）：

```python
# alpha/ic_weighting.py — compute_composite_score()

MIN_ACTIVE_FACTORS = 2  # minimum factors required to produce a signal

if len(eligible_factors) < MIN_ACTIVE_FACTORS:
    logger.warning(
        f"Only {len(eligible_factors)} factors passed gates at {signal_date} "
        f"(min={MIN_ACTIVE_FACTORS}). Returning empty — no signal."
    )
    return pd.DataFrame()  # backtester should freeze previous weights
```

> **更强的方案（Step 3 可考虑）**：不足时回退到等权多因子（所有通过 coverage gate 的因子等权），而不是完全不出信号。这提供了更平滑的降级。

### 改动 2.1：`configs/factors.yaml` — 切全因子池 + 启用 gate

```yaml
composite:
  ic_window_months: 6            # faster regime response (from 12)
  ic_method: "rank"              # Spearman rank IC
  shrinkage: 0.5                 # more conservative on small samples (from 0.3)
  weight_cap: 0.25               # Step 2: enable hard cap (from 0.3)
  hard_cap: true                 # Step 2: enable post-normalization hard cap
  min_ic_obs: 20
  min_icir: 0.05                 # Step 2: enable ICIR noise filter
  sign_stability_check: true
  horizon: 5                     # forward return horizon (for lag computation)

enabled_factors: []              # Step 2: FULL CANDIDATE POOL
```

### 改动 2.2：`alpha/ic_weighting.py` — 综合修改

汇总 Step 2 对 `ICWeighting` 的所有修改：

1. `__init__` 新增 `horizon: int = 5`、`hard_cap: bool = False`
2. `compute_weights()` 新增 `eligible_factor_names` 参数 + horizon lag
3. `compute_composite_score()` 接入历史覆盖率 gate + min_active_factors
4. `_apply_hard_cap()` 由 `self.hard_cap` 控制

### 改动 2.3：覆盖率 gate 接入回测循环

在 `compute_composite_score()` 中，对每个 signal_date：

```python
# Per-date coverage gate (historical window only)
eligible_factors = {}
for name, df in factor_dfs.items():
    if _evaluate_factor_coverage_at_date(
        df, signal_date, fwd_returns_df,
        lookback_months=self.ic_window_months,
    ):
        eligible_factors[name] = df

# Safety valve: if too few factors pass, return empty → no trade
if len(eligible_factors) < 2:  # MIN_ACTIVE_FACTORS
    return pd.DataFrame()

# Only pass eligible factors to weight computation
eligible_names = list(eligible_factors.keys())
weights = self.compute_weights(ic_df, signal_date,
                               eligible_factor_names=eligible_names)
```

---

## 五、Step 3：完善（P2，✅ 基本通过）

### 改动 3.1：`factors/cross_section.py` — 接入 YAML（修正工厂函数签名）

`CrossSectionProcessor.__init__` 的实际签名：

```python
def __init__(self,
             winsor_method="mad", mad_multiplier=5.0,
             quantile_lower=0.01, quantile_upper=0.99,
             missing_method="industry_median",
             neutralize=True,
             neutralizers=None,
             standardize_method="zscore",
             min_stocks=30):
```

**没有 `min_coverage` 和 `neutralize_method` 参数。** 新增工厂函数严格匹配：

```python
def create_processor_from_config(config_path="configs/factors.yaml"):
    """Create CrossSectionProcessor from YAML config.

    Reads cross_section section. Falls back to current hardcoded defaults
    for any missing keys. Signature exactly matches CrossSectionProcessor.__init__.
    """
    import yaml
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)
    cs = config.get("cross_section", {})
    return CrossSectionProcessor(
        winsor_method=cs.get("winsor_method", "mad"),
        mad_multiplier=cs.get("mad_multiplier", 5.0),
        quantile_lower=cs.get("quantile_lower", 0.01),
        quantile_upper=cs.get("quantile_upper", 0.99),
        missing_method=cs.get("missing_method", "industry_median"),
        neutralize=cs.get("neutralize", True),
        neutralizers=cs.get("neutralizers", ["industry", "log_market_cap"]),
        standardize_method=cs.get("standardize", "zscore"),
        min_stocks=cs.get("min_stocks_for_cs", 30),
    )
```

修改 `factors/factor_panel.py:72-73`：

```python
from factors.cross_section import (
    create_default_processor,
    create_processor_from_config,
)
try:
    self._cs = create_processor_from_config()
    logger.info("CrossSectionProcessor initialized from YAML config")
except Exception:
    self._cs = create_default_processor()
    logger.warning("Falling back to default CrossSectionProcessor")
```

### 改动 3.2：`ic_method` 参数处理

`compute_rolling_ic()` 当前固定使用 `spearmanr`。决定：**先不实现 Pearson（Rank IC 是行业标准，Pearson IC 对离群值敏感，实际很少用）。** 在 YAML 和代码中标注清楚：

```yaml
composite:
  ic_method: "rank"    # "rank" (Spearman) is the only implemented option.
                       # "pearson" is reserved for future use.
```

```python
# alpha/ic_weighting.py:compute_rolling_ic()
if self.ic_method not in ("rank",):
    logger.warning(f"ic_method='{self.ic_method}' not implemented; falling back to 'rank'")
# Use spearmanr (rank IC)
from scipy.stats import spearmanr
ic, _ = spearmanr(merged[factor_col], merged["fwd_ret"])
```

### 改动 3.3：A/B 对比框架

通过 `--factors-config` CLI 参数实现（Step 1 已加）：

```bash
# 方案 A（旧 — 固定 5 反转）
# 使用 factors_5reversal.yaml（enabled_factors: [reversal_5_cs, ...]）
python run_research.py --start 20170101 --end 20251231 \
    --phase 2 --top-n 50 \
    --factors-config configs/factors_5reversal.yaml

# 方案 B（新 — 全因子候选池）
# 使用默认 factors.yaml（enabled_factors: []）
python run_research.py --start 20170101 --end 20251231 \
    --phase 2 --top-n 50
```

配置文件 `configs/factors_5reversal.yaml` 的 `enabled_factors` 设为 5 个反转因子，其他部分与 `factors.yaml` 完全相同（通过 `#include` 注释约定或手动同步）。

### 改动 3.4：参数敏感性扫描

```yaml
# configs/phase5_factor_gating_experiments.yaml
experiments:
  - name: ic_window_sweep
    param: composite.ic_window_months
    values: [3, 6, 9, 12]
    
  - name: shrinkage_sweep
    param: composite.shrinkage
    values: [0.3, 0.5, 0.7]
    
  - name: weight_cap_sweep
    param: composite.weight_cap
    values: [0.20, 0.25, 0.30, 0.40]
    requires: composite.hard_cap = true
    
  - name: min_icir_sweep
    param: composite.min_icir
    values: [0.0, 0.03, 0.05, 0.10]
    
  - name: min_active_factors_sweep
    param: composite.min_active_factors
    values: [1, 2, 3]
```

---

## 六、实施优先级总表

| Step | 改动 | 代码量 | 改变策略行为？ | 风险 |
|------|------|--------|---------------|------|
| **Step 1** | `_load_factor_config()` 读完整配置 | ~30 行 | **否** | 低 |
| **Step 1** | 6 个调用点传 `composite_params` | ~10 行/处 | **否**（默认值 = 旧硬编码） | 低 |
| **Step 1** | `ICWeighting` 加 `min_icir`（默认 0.0） | ~6 行 | **否** | 低 |
| **Step 1** | `_apply_hard_cap()` 写好不调用 | ~40 行 | **否**（`hard_cap=False`） | 低 |
| **Step 1** | `_evaluate_factor_coverage_at_date()` 写好不调用 | ~70 行 | **否**（未接入） | 低 |
| **Step 1** | `--factors-config` CLI 参数 | ~5 行 | **否**（默认路径 = 原文件） | 低 |
| **Step 1** | YAML 加注释，`enabled_factors` 保持 5 个 | 0 行代码 | **否** | 低 |
| | | **~200 行总计** | | |
| **Step 2** | `ICWeighting` 加 `horizon`、`hard_cap` 参数 | ~8 行 | **是** | 中 |
| **Step 2** | `compute_weights()` horizon lag + eligible 过滤 | ~15 行 | **是** | 中 |
| **Step 2** | `compute_composite_score()` 接入 coverage gate | ~20 行 | **是** | 中 |
| **Step 2** | `min_active_factors` 安全阀 | ~8 行 | **是** | 低 |
| **Step 2** | YAML 切全因子池 + 收紧参数 | 改值 | **是** | 中 |
| | | **~55 行总计** | | |
| **Step 3** | cross_section YAML 接线 | ~25 行 | **是**（需重跑 Phase 1） | 中 |
| **Step 3** | `ic_method` 标注 | ~4 行 | 否 | 低 |
| **Step 3** | `factors_5reversal.yaml` 对照配置 | 新文件 | N/A（工具） | 低 |
| **Step 3** | 参数扫描配置 | YAML | N/A（验证） | 低 |

---

## 七、预期效果

| 年份 | 旧策略（5 反转） | Step 2 完成后预期 | 差异来源 |
|------|-----------------|-------------------|----------|
| 2017 | −28% 超额 | 改善 | momentum_120 IC 正，pv_divergence 稳定 |
| 2018 | −9% 超额 | 小幅改善 | vol_60 在熊市抗跌 |
| 2019 | −0.2% 超额 | 改善 | 多因子分散 |
| 2020 | −21% 超额 | **大幅改善** | momentum 权重上升，反转权重下降 |
| 2021 | +6.7% 超额 | 可能更好 | ep/sp/bp ICIR 远超反转 |
| 2022 | −15% 超额 | 小幅改善 | 分散降低波动 |
| 2023 | +6.3% 超额 | **大幅改善** | bp ICIR=1.17 拿到最高权重 |
| 2024 | 0% 超额 | 改善 | vol_60 拿到更多权重 |
| 2025 | −17% 超额 | **大幅改善** | ep ICIR=0.49，反转 ICIR≈0 |

---

## 附录 A：全部已知问题速查表

| # | 问题 | 文件:行 | 严重性 | 修复所在 |
|---|------|---------|--------|----------|
| 1 | YAML composite 死配置 | `run_research.py:174-193` | 中 | Step 1 |
| 2 | 硬白名单过滤因子 | `run_research.py:196-209` | 高 | Step 2 |
| 3 | ICWeighting 参数全硬编码 | `alpha/ic_weighting.py:34-49` | 中 | Step 1 |
| 4 | weight_cap 先 clip 后归一化 | `alpha/ic_weighting.py:198-206` | 中 | Step 1/2 |
| 5 | 单因子 z-score 等价 100% | `alpha/ic_weighting.py:275-283` | 高 | Step 2 |
| 6 | IC horizon 未来函数 | `alpha/ic_weighting.py:158-162` | **严重** | Step 2 |
| 7 | 覆盖率 gate 全回测窗口 | （v1/v2 旧方案已移除） | — | 已修复 |
| 8 | cross_section 死配置 | `factors/cross_section.py:454` | 低 | Step 3 |
| 9 | ic_method 死参数 | `alpha/ic_weighting.py:125` | 低 | Step 3 |
| 10 | `--factor-override` 不存在 | CLI | 低 | Step 1/3 |
| 11 | 工厂函数传不存在的参数 | （v2 旧方案已移除） | — | 已修复 |
| 12 | coverage gate 用 `*100` 近似月份 | （v3 改为 `pd.DateOffset`） | — | 已修复 |

## 附录 B：Step 1 可复现性验证清单

- [ ] 用 `--factors-config configs/factors.yaml`（默认）跑 2016 IS
- [ ] `metrics_summary.json` 的以下字段与修复前完全一致：
  - [ ] `annualized_return`
  - [ ] `annualized_excess_return`
  - [ ] `sharpe_ratio`
  - [ ] `information_ratio`
  - [ ] `max_drawdown`
  - [ ] `avg_turnover`
  - [ ] `total_cost_bps`
- [ ] 逐年的 2017-2026 Phase 2 回测也可复现
- [ ] `ICWeighting` 收到的参数日志与旧硬编码一致
- [ ] `--factors-config configs/factors_5reversal.yaml` 的行为与默认一致（配置内容相同）
